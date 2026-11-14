import hashlib
import http.server
import io
import json
import os
import shutil
import threading
import urllib.error
from pathlib import Path

import pytest

import make_fixtures
from appforge.core.models import UpdateStatus
from appforge.core.updates import installer
from appforge.core.updates.assets import choose_asset
from appforge.core.updates.checker import check_for_update
from appforge.core.updates.github import Asset, GitHubClient, GitHubError, Release
from appforge.core.updates.service import UpdateService, can_update, pattern_from_asset


# ---------------------------------------------------------------- asset selection
def rel(*names, tag="v2.0.0"):
    return Release(tag=tag, assets=[Asset(n, f"https://x/{n}", 1000) for n in names])


def test_choose_asset_ignores_sources_checksums_and_other_arch():
    r = rel("App-2.0.0-aarch64.AppImage", "App-2.0.0-x86_64.AppImage", "App-2.0.0-x86_64.AppImage.zsync",
            "App-2.0.0.tar.gz", "App-2.0.0-x86_64.AppImage.sha256", "Source code.zip")
    c = choose_asset(r, current_filename="App.AppImage", app_name="App", arch="x86_64")
    assert c.asset.name == "App-2.0.0-x86_64.AppImage" and not c.ambiguous


def test_choose_asset_ambiguous_and_pattern_resolves_it():
    r = rel("App-2.0.0-x86_64.AppImage", "App-2.0.0-x86_64-gtk2.AppImage")
    c = choose_asset(r, current_filename="App.AppImage", app_name="App", arch="x86_64")
    assert c.ambiguous and len(c.candidates) == 2
    pat = pattern_from_asset("App-1.9.0-x86_64-gtk2.AppImage", "v1.9.0")
    assert pat == "App-*-x86_64-gtk2.AppImage"
    c = choose_asset(r, current_filename="App.AppImage", app_name="App", pattern=pat, arch="x86_64")
    assert c.asset.name.endswith("gtk2.AppImage") and not c.ambiguous


def test_choose_asset_none_when_only_wrong_arch_or_no_appimage():
    assert choose_asset(rel("App-arm64.AppImage"), current_filename="a", app_name="a", arch="x86_64") is None
    assert choose_asset(rel("App.tar.gz", "App.deb"), current_filename="a", app_name="a", arch="x86_64") is None


# ---------------------------------------------------------------- GitHub client
class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


RELEASES_JSON = [
    {"tag_name": "v3.0.0-rc1", "prerelease": True, "draft": False, "html_url": "u3", "assets": [
        {"name": "App-3.0.0-rc1-x86_64.AppImage", "browser_download_url": "https://x/rc", "size": 5}]},
    {"tag_name": "v2.0.0", "prerelease": False, "draft": False, "html_url": "u2", "published_at": "2024-01-01T00:00:00Z",
     "assets": [{"name": "App-2.0.0-x86_64.AppImage", "browser_download_url": "https://x/a", "size": 10,
                 "digest": "sha256:" + "ab" * 32}]},
    {"tag_name": "v1.0.0", "prerelease": False, "draft": False, "assets": []},
]


def client_returning(data):
    return GitHubClient(token="", opener=lambda req, timeout=None: FakeResp(json.dumps(data).encode()))


def test_client_parses_releases_and_sends_headers():
    seen = {}
    def opener(req, timeout=None):
        seen["req"] = req
        return FakeResp(json.dumps(RELEASES_JSON).encode())
    rels = GitHubClient(token="tok", opener=opener).releases("o", "r")
    assert [r.tag for r in rels] == ["v3.0.0-rc1", "v2.0.0", "v1.0.0"]
    assert rels[1].assets[0].digest.startswith("sha256:")
    assert seen["req"].full_url == "https://api.github.com/repos/o/r/releases?per_page=30"
    assert seen["req"].get_header("Authorization") == "Bearer tok"
    assert "AppForge" in seen["req"].get_header("User-agent")


@pytest.mark.parametrize("code,headers,kind", [(404, {}, "not_found"), (403, {"X-RateLimit-Remaining": "0"}, "rate_limit"),
                                               (500, {}, "http")])
def test_client_error_mapping(code, headers, kind):
    def opener(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "x", headers, None)
    with pytest.raises(GitHubError) as ei:
        GitHubClient(token="", opener=opener).releases("o", "r")
    assert ei.value.kind == kind


def test_client_network_error():
    def opener(req, timeout=None):
        raise urllib.error.URLError("no route")
    with pytest.raises(GitHubError) as ei:
        GitHubClient(token="", opener=opener).releases("o", "r")
    assert ei.value.kind == "network"


# ---------------------------------------------------------------- checker
def check(installed, data=RELEASES_JSON, **kw):
    return check_for_update(repo_url="https://github.com/o/r", installed_version=installed,
                            current_filename="App.AppImage", app_name="App",
                            client=client_returning(data), **kw)


def test_check_update_available_skips_prerelease():
    o = check("1.5.0")
    assert o.status is UpdateStatus.UPDATE_AVAILABLE and o.latest_version == "2.0.0"
    assert o.asset["name"] == "App-2.0.0-x86_64.AppImage"


def test_check_with_prereleases_included():
    assert check("2.0.0", include_prereleases=True).latest_version == "3.0.0-rc1"


def test_check_up_to_date_unknown_and_incomparable():
    assert check("2.0.0").status is UpdateStatus.UP_TO_DATE
    assert check("2.1").status is UpdateStatus.UP_TO_DATE
    o = check(None)
    assert o.status is UpdateStatus.UNAVAILABLE and o.latest_version == "2.0.0"
    assert check("nightly").status is UpdateStatus.UNAVAILABLE


def test_check_failure_and_no_assets():
    def boom(req, timeout=None):
        raise urllib.error.URLError("down")
    o = check_for_update(repo_url="o/r", installed_version="1", current_filename="a", app_name="a",
                         client=GitHubClient(token="", opener=boom))
    assert o.status is UpdateStatus.FAILED and "reach" in o.message
    o = check("1.0", data=[{"tag_name": "v2", "assets": []}])
    assert o.status is UpdateStatus.UNAVAILABLE and "No AppImage" in o.message
    assert check("1.0", data=[]).status is UpdateStatus.UNAVAILABLE


# ---------------------------------------------------------------- installer (real HTTP server)
@pytest.fixture(scope="module")
def new_appimage(tmp_path_factory, fixtures):
    return make_fixtures.build(tmp_path_factory.mktemp("new"), "alpha", "Alpha Editor", "9.9.9", "#000000",
                               filename="new.AppImage")


class Server:
    def __init__(self, routes):
        self.routes = routes
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                item = outer.routes.get(self.path)
                if item is None:
                    self.send_error(404); return
                body, claimed = item if isinstance(item, tuple) else (item, None)
                self.send_response(200)
                self.send_header("Content-Length", str(claimed if claimed is not None else len(body)))
                self.end_headers()
                self.wfile.write(body)
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture()
def world(tmp_path, fixtures, new_appimage):
    app_dir = tmp_path / "Emulators"
    app_dir.mkdir()
    target = app_dir / "Dolphin.AppImage"
    shutil.copy(fixtures["alpha"], target)
    target.chmod(0o750)
    new_bytes = new_appimage.read_bytes()
    routes = {"/new.AppImage": new_bytes}
    srv = Server(routes)
    yield target, new_bytes, routes, srv
    srv.close()


def asset_for(srv, new_bytes, digest=True, name="new.AppImage"):
    return {"name": name, "url": f"{srv.url}/{name}", "size": len(new_bytes),
            "digest": ("sha256:" + hashlib.sha256(new_bytes).hexdigest()) if digest else None}


def no_leftovers(target):
    return not list(target.parent.glob(".*.part"))


def test_install_success_preserves_name_mode_and_backs_up(world):
    target, new_bytes, routes, srv = world
    old_bytes = target.read_bytes()
    seen = []
    res = installer.install_update(target, asset_for(srv, new_bytes), [], old_version="2.3.1",
                                   progress=lambda d, t: seen.append((d, t)))
    assert target.read_bytes() == new_bytes and target.name == "Dolphin.AppImage"
    assert os.access(target, os.X_OK) and (target.stat().st_mode & 0o777) == 0o751  # 0o750 | x
    bk = Path(res.backup_path)
    assert bk.parent.name == ".Dolphin.backups" and bk.name == "Dolphin-2.3.1.AppImage"
    assert bk.read_bytes() == old_bytes
    assert res.checksum == "verified (sha256)" and no_leftovers(target)
    assert seen and seen[-1][0] == len(new_bytes)
    # a second update keeps *both* backups
    res2 = installer.install_update(target, asset_for(srv, new_bytes), [], old_version="2.3.1")
    assert Path(res2.backup_path).name == "Dolphin-2.3.1-2.AppImage" and bk.exists()


def test_install_checksum_from_sidecar_and_sums_file(world):
    target, new_bytes, routes, srv = world
    h = hashlib.sha256(new_bytes).hexdigest()
    routes["/new.AppImage.sha256"] = f"{h}  new.AppImage\n".encode()
    a = asset_for(srv, new_bytes, digest=False)
    side = {"name": "new.AppImage.sha256", "url": srv.url + "/new.AppImage.sha256"}
    assert installer.install_update(target, a, [a, side], old_version="1").checksum == "verified (sha256)"
    routes["/SHA256SUMS"] = f"{'0'*64}  other.AppImage\n{h} *new.AppImage\n".encode()
    sums = {"name": "SHA256SUMS", "url": srv.url + "/SHA256SUMS"}
    assert installer.install_update(target, a, [a, sums], old_version="1").checksum == "verified (sha256)"
    assert installer.install_update(target, a, [a], old_version="1").checksum == "not available"


def test_checksum_mismatch_leaves_everything_untouched(world):
    target, new_bytes, routes, srv = world
    old = target.read_bytes()
    a = asset_for(srv, new_bytes)
    a["digest"] = "sha256:" + "0" * 64
    with pytest.raises(installer.InstallError, match="Checksum mismatch"):
        installer.install_update(target, a, [], old_version="1")
    assert target.read_bytes() == old and no_leftovers(target)
    assert not (target.parent / ".Dolphin.backups").exists()


def test_truncated_download_is_rejected(world):
    target, new_bytes, routes, srv = world
    old = target.read_bytes()
    routes["/cut.AppImage"] = (new_bytes[: len(new_bytes) // 2], len(new_bytes))   # promises more than it sends
    a = asset_for(srv, new_bytes, digest=False, name="cut.AppImage")
    with pytest.raises(installer.InstallError):
        installer.install_update(target, a, [], old_version="1")
    assert target.read_bytes() == old and no_leftovers(target)


def test_invalid_file_is_rejected(world):
    target, new_bytes, routes, srv = world
    old = target.read_bytes()
    routes["/junk.AppImage"] = b"<html>not found page</html>" * 20000
    a = {"name": "junk.AppImage", "url": srv.url + "/junk.AppImage", "size": 0, "digest": None}
    with pytest.raises(installer.InstallError, match="not a valid AppImage"):
        installer.install_update(target, a, [], old_version="1")
    assert target.read_bytes() == old and no_leftovers(target)


def test_http_error_and_cancel(world):
    target, new_bytes, routes, srv = world
    old = target.read_bytes()
    with pytest.raises(installer.InstallError, match="404"):
        installer.install_update(target, {"name": "x", "url": srv.url + "/missing", "size": 0}, [], old_version="1")
    ev = threading.Event()
    ev.set()
    with pytest.raises(installer.InstallCancelled):
        installer.install_update(target, asset_for(srv, new_bytes), [], old_version="1", cancel=ev)
    assert target.read_bytes() == old and no_leftovers(target)


def test_stale_part_files_are_cleaned(world):
    target, new_bytes, routes, srv = world
    stale = target.parent / f".{target.name}.abc123.part"
    stale.write_bytes(b"x")
    os.utime(stale, (1, 1))
    installer.install_update(target, asset_for(srv, new_bytes), [], old_version="1")
    assert not stale.exists()


def test_parse_checksum_formats():
    h = "a" * 64
    assert installer._parse_checksum_text(h + "\n", "f") == h
    assert installer._parse_checksum_text(f"{h}  f\n", "f") == h
    assert installer._parse_checksum_text(f"SHA256 (f) = {h}\n", "f") == h
    assert installer._parse_checksum_text(f"{h}  g\n", "f") is None


# ---------------------------------------------------------------- UpdateService + DB
def test_service_flow_check_install_and_version_source(service, fixtures, world):
    target, new_bytes, routes, srv = world
    e = service.add_application(str(target), github_repo="o/r")
    us = UpdateService(service)
    o = check("2.3.1")
    assert o.status is UpdateStatus.UP_TO_DATE
    o = check("1.0")
    e = us.apply_check(e.id, o)
    assert e.update_status is UpdateStatus.UPDATE_AVAILABLE and e.latest_version == "2.0.0" and can_update(e)
    a = asset_for(srv, new_bytes)
    res = installer.install_update(target, a, [], old_version=e.installed_version)
    e = us.apply_install(e.id, res, "v2.0.0")
    assert e.installed_version == "2.0.0" and e.update_status is UpdateStatus.UP_TO_DATE
    assert e.metadata["installed_version_source"] == "github_release"
    assert e.backup_info["backups"][0]["version"] == "2.3.1"
    # re-reading the file must not replace the release-derived version with the file's embedded 9.9.9
    assert service.refresh_metadata(e.id).installed_version == "2.0.0"
    assert service.refresh_metadata(e.id, overwrite_version=True).installed_version == "9.9.9"


def test_service_failure_keeps_retry_and_repo_change_resets(service, fixtures):
    e = service.add_application(str(fixtures["alpha"]), github_repo="o/r")
    us = UpdateService(service)
    e = us.apply_check(e.id, check("1.0"))
    e = us.apply_install_failure(e.id, "boom")
    assert e.update_status is UpdateStatus.FAILED and can_update(e)       # retry possible
    e = us.apply_check(e.id, check("1.0"))
    assert e.update_status is UpdateStatus.UPDATE_AVAILABLE
    e = service.update_application(e.id, github_repo="https://github.com/other/repo")
    assert e.update_status is UpdateStatus.UNAVAILABLE and e.latest_version is None
    e = service.update_application(e.id, settings={"include_prereleases": True, "asset_pattern": "A-*.AppImage"})
    assert e.metadata["include_prereleases"] is True and e.metadata["asset_pattern"] == "A-*.AppImage"
    e = service.update_application(e.id, settings={"include_prereleases": False, "asset_pattern": ""})
    assert "include_prereleases" not in e.metadata and "asset_pattern" not in e.metadata


def test_failed_check_does_not_offer_update(service, fixtures):
    e = service.add_application(str(fixtures["alpha"]), github_repo="o/r")
    us = UpdateService(service)
    e = us.apply_check(e.id, check("2.0.0"))               # up to date, has asset info
    from appforge.core.updates.checker import CheckOutcome
    e = us.apply_check(e.id, CheckOutcome(UpdateStatus.FAILED, "offline"))
    assert e.update_status is UpdateStatus.FAILED and not can_update(e)
