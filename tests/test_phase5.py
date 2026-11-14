"""Phase 5: settings, providers (GitLab/Codeberg), categories/filtering, executables, notifications.

Pure core logic: no real AppImages and no Qt needed.
"""
import http.server
import json
import os
import threading
import time
import urllib.error
from pathlib import Path

import pytest

from appforge.core.database import Database
from appforge.core.formats import FORMATS, detect_format, get_format
from appforge.core.formats.executable import ExecutableFormat, executable_kind
from appforge.core.library import LibraryError, normalize_repo
from appforge.core.models import AppEntry, UpdateStatus
from appforge.core.organize import (
    ALL, ATTENTION, SORT_RECENT, SORT_STATUS, UNLINKED, UPDATES, Filter, categories_in_use,
    category_of, category_suggestions, derived_category, matches, sort_entries,
)
from appforge.core.settings import AppSettings
from appforge.core.updates import installer
from appforge.core.updates.assets import choose_asset, is_executable_name
from appforge.core.updates.checker import check_for_update
from appforge.core.updates.github import Asset, GitHubError, Release
from appforge.core.updates.providers import (
    ForgejoClient, GitLabClient, SelfHostedClient, client_for, parse_source,
)
from appforge.core.updates.service import NOTIFIED_KEY, UpdateService
from appforge.services.notifier import summarize_updates

ELF = b"\x7fELF" + b"\x02\x01\x01" + b"\x00" * 600


# ------------------------------------------------------------------------------- settings
def test_settings_defaults_roundtrip_and_clamping(service, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    s = AppSettings(service.db)
    assert s.auto_check is True and s.notifications is True and s.run_in_background is False
    assert s.check_interval_hours == 6 and s.check_interval_seconds == 6 * 3600
    s.auto_check, s.notifications, s.run_in_background = False, False, True
    s.check_interval_hours = 12
    s2 = AppSettings(service.db)
    assert (s2.auto_check, s2.notifications, s2.run_in_background, s2.check_interval_hours) == (False, False, True, 12)
    s.check_interval_hours = 0
    assert s.check_interval_hours == 1
    service.db.set_setting("check_interval_hours", "garbage")
    assert s.check_interval_hours == 6


def test_github_token_settings_precedence_and_validation(service, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    s = AppSettings(service.db)
    assert s.token_source() == "environment" and s.effective_github_token() == "env-token"
    s.set_github_token("  ghp_abc123  ")
    assert s.github_token == "ghp_abc123" and s.token_source() == "settings"
    assert s.effective_github_token() == "ghp_abc123"
    assert (os.stat(service.db.path).st_mode & 0o777) == 0o600
    with pytest.raises(ValueError):
        s.set_github_token("has space")
    with pytest.raises(ValueError):
        s.set_github_token("tok\nen")
    s.set_github_token("")
    assert s.token_source() == "environment"
    monkeypatch.delenv("GITHUB_TOKEN")
    assert s.token_source() == "none" and s.effective_github_token() is None


# ------------------------------------------------------------------------------- source parsing
@pytest.mark.parametrize("text,expected", [
    ("https://github.com/o/r", ("github", "o", "r")),
    ("o/r", ("github", "o", "r")),
    ("git@github.com:o/r.git", ("github", "o", "r")),
    ("https://gitlab.com/g/p", ("gitlab", "g", "p")),
    ("https://gitlab.com/g/sub/p/-/releases", ("gitlab", "g/sub", "p")),
    ("gitlab.com/g/p.git", ("gitlab", "g", "p")),
    ("https://codeberg.org/o/r/releases/tag/v1", ("codeberg", "o", "r")),
    ("git@codeberg.org:o/r.git", ("codeberg", "o", "r")),
])
def test_parse_source_ok(text, expected):
    ref = parse_source(text)
    assert (ref.provider, ref.owner, ref.name) == expected


@pytest.mark.parametrize("text", ["", "   ", "notarepo", "https://example.com/onlyone",
                                  "http://git.example.dev/o/r", "https://user:pw@git.example.dev/o/r",
                                  "https://github.com/onlyowner", "https://gitlab.com/onlyone",
                                  "https://github.com/../r", "ftp://github.com/o/r", "https://github.com/o r/x"])
def test_parse_source_bad(text):
    assert parse_source(text) is None


def test_normalize_repo_accepts_all_providers_and_rejects_others():
    assert normalize_repo("o/r") == "https://github.com/o/r"
    assert normalize_repo("https://gitlab.com/g/s/p/-/tags") == "https://gitlab.com/g/s/p"
    assert normalize_repo("codeberg.org/o/r") == "https://codeberg.org/o/r"
    assert normalize_repo("  ") is None and normalize_repo(None) is None
    assert normalize_repo("https://git.magicbean.dev/MagicBeanDev/Longshot.git") == \
        "https://git.magicbean.dev/MagicBeanDev/Longshot"
    with pytest.raises(LibraryError, match="GitLab"):
        normalize_repo("http://example.com/a/b")          # self-hosted servers must use https


# ------------------------------------------------------------------------------- provider clients
class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self, *a):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(payload, seen):
    def opener(req, timeout=None):
        seen.append(req)
        if isinstance(payload, Exception):
            raise payload
        return FakeResp(payload)
    return opener


def test_gitlab_client_maps_releases_and_drops_unsafe_links():
    seen = []
    payload = [
        {"tag_name": "v2.0.0", "name": "Two", "upcoming_release": False, "released_at": "2026-01-01",
         "_links": {"self": "https://gitlab.com/g/s/p/-/releases/v2.0.0"},
         "assets": {"links": [
             {"name": "Linux AppImage", "direct_asset_url": "https://gitlab.com/g/s/p/-/releases/v2.0.0/downloads/App-2.0.0-x86_64.AppImage"},
             {"name": "evil", "url": "http://insecure.example/App.AppImage"},
             {"name": "local", "url": "file:///etc/passwd"}],
             "sources": [{"format": "zip", "url": "https://gitlab.com/x.zip"}]}},
        {"tag_name": "v3.0.0-rc1", "assets": {"links": []}},
        {"tag_name": "v1.0", "upcoming_release": True, "assets": {"links": []}},
        "junk",
    ]
    rels = GitLabClient(opener=opener_for(payload, seen)).releases("g/s", "p")
    assert "/api/v4/projects/g%2Fs%2Fp/releases" in seen[0].full_url
    assert [r.tag for r in rels] == ["v2.0.0", "v3.0.0-rc1", "v1.0"]
    assert [a.name for a in rels[0].assets] == ["App-2.0.0-x86_64.AppImage"]      # only the https file
    assert rels[0].html_url.endswith("/releases/v2.0.0")
    assert not rels[0].prerelease and rels[1].prerelease and rels[2].prerelease
    assert "Authorization" not in {k.title() for k in seen[0].headers}


def test_forgejo_client_maps_releases():
    seen = []
    payload = [{"tag_name": "v1.2", "prerelease": False, "draft": False, "html_url": "https://codeberg.org/o/r/releases/tag/v1.2",
                "assets": [{"name": "r-1.2-x86_64.AppImage", "size": 9, "browser_download_url": "https://codeberg.org/o/r/releases/download/v1.2/r-1.2-x86_64.AppImage"},
                           {"name": "plain", "browser_download_url": "http://insecure/x"}]}]
    rels = ForgejoClient(opener=opener_for(payload, seen)).releases("o", "r")
    assert seen[0].full_url.startswith("https://codeberg.org/api/v1/repos/o/r/releases")
    assert rels[0].assets[0].size == 9 and len(rels[0].assets) == 1


def test_provider_errors_are_mapped():
    import urllib.error
    def err(code):
        return urllib.error.HTTPError("u", code, "x", {}, None)
    for client_cls in (GitLabClient, ForgejoClient):
        with pytest.raises(GitHubError) as ei:
            client_cls(opener=opener_for(err(404), [])).releases("o", "r")
        assert ei.value.kind == "not_found"
        with pytest.raises(GitHubError) as ei:
            client_cls(opener=opener_for(err(429), [])).releases("o", "r")
        assert ei.value.kind == "rate_limit"
        with pytest.raises(GitHubError) as ei:
            client_cls(opener=opener_for(urllib.error.URLError("down"), [])).releases("o", "r")
        assert ei.value.kind == "network"
        with pytest.raises(GitHubError) as ei:
            client_cls(opener=opener_for({"not": "a list"}, [])).releases("o", "r")
        assert ei.value.kind == "invalid"


def test_client_for_gives_the_token_only_to_github():
    gh = client_for(parse_source("o/r"), "secret")
    assert gh.token == "secret"
    assert not hasattr(client_for(parse_source("https://gitlab.com/g/p"), "secret"), "token")
    assert not hasattr(client_for(parse_source("https://codeberg.org/o/r"), "secret"), "token")


def test_checker_routes_by_provider_and_uses_injected_client():
    class Fake:
        def __init__(self):
            self.calls = []

        def releases(self, owner, name, per_page=30):
            self.calls.append((owner, name))
            return [Release("v2.0.0", assets=[Asset("App-2.0.0-x86_64.AppImage", "https://x/a", 5)])]
    fake = Fake()
    out = check_for_update(repo_url="https://gitlab.com/g/s/p", installed_version="1.0.0",
                           current_filename="App.AppImage", app_name="App", client=fake)
    assert out.status is UpdateStatus.UPDATE_AVAILABLE and fake.calls == [("g/s", "p")]
    bad = check_for_update(repo_url="https://example.com/a/b", installed_version="1", current_filename="a",
                           app_name="a", client=fake)
    assert bad.status is UpdateStatus.FAILED and "isn't valid" in bad.message


# ------------------------------------------------------------------------------- executables
def make_exec(dirp: Path, name, data=ELF, mode=0o755):
    dirp.mkdir(parents=True, exist_ok=True)
    p = dirp / name
    p.write_bytes(data)
    p.chmod(mode)
    return p


def test_executable_detection(tmp_path):
    elf = make_exec(tmp_path, "ripgrep-14.1.0-x86_64-linux")
    script = make_exec(tmp_path, "backup.sh", b"#!/bin/sh\necho hi\n")
    text = make_exec(tmp_path, "notes.txt", b"hello there")
    appimage_named = make_exec(tmp_path, "Foo.AppImage")
    assert executable_kind(elf) == "elf" and executable_kind(script) == "script"
    assert executable_kind(text) is None and executable_kind(tmp_path) is None
    assert executable_kind(appimage_named) is None                 # AppImages stay AppImages
    assert detect_format(elf).id == "executable" and detect_format(script).id == "executable"
    assert detect_format(appimage_named).id == "appimage"
    assert detect_format(text) is None
    assert get_format("executable").display_name == "Executable"
    assert [f.id for f in FORMATS] == ["appimage", "executable"]


def test_executable_metadata_has_name_version_and_no_execution(tmp_path):
    p = make_exec(tmp_path, "ripgrep-14.1.0-x86_64.bin")
    md = ExecutableFormat().extract_metadata(p)
    assert md.name_suggestion == "ripgrep" and md.version == "14.1.0"
    assert md.icon_data is None and md.extra["executable_kind"] == "elf" and not md.warnings
    md2 = ExecutableFormat().extract_metadata(make_exec(tmp_path, "mytool.sh", b"#!/bin/sh\n"))
    assert md2.name_suggestion == "mytool" and md2.version is None and md2.warnings


def test_add_executable_to_library_and_launch_command(service, tmp_path):
    p = make_exec(tmp_path / "bin", "tool-1.2.3-linux-amd64")
    e = service.add_application(str(p))
    assert e.format == "executable" and e.name == "tool" and e.installed_version == "1.2.3"
    assert get_format(e.format).launch_command(p) == [str(p)]
    with pytest.raises(LibraryError, match="can't use this file"):
        service.add_application(str(make_exec(tmp_path, "readme.txt", b"just text")))


def test_executable_launcher_entry_renders(service, tmp_path):
    p = make_exec(tmp_path / "bin", "tool-1.2.3")
    e = service.add_application(str(p), integrate_desktop=True)
    text = service.desktop.entry_path(e.id).read_text("utf-8")
    assert f"Exec={p}" in text and "Categories=Utility;" in text


def test_is_executable_name_filters_archives_and_other_platforms():
    for ok in ("tool-linux-amd64", "tool_1.2_linux_x86_64", "tool", "tool-x86_64-unknown-linux-musl"):
        assert is_executable_name(ok), ok
    for bad in ("tool-linux-amd64.tar.gz", "tool.zip", "tool_1.2_amd64.deb", "tool-darwin-arm64",
                "tool-windows-amd64.exe", "tool.sha256", "checksums.txt", "tool.AppImage", "tool-linux.sig",
                "install.sh", "tool-macos"):
        assert not is_executable_name(bad), bad


def test_choose_asset_for_executables():
    rel = Release("v1", assets=[Asset(n, "https://x/" + n) for n in (
        "tool-linux-amd64", "tool-linux-arm64", "tool-darwin-amd64", "tool-linux-amd64.tar.gz",
        "tool-windows-amd64.exe", "checksums.txt")])
    c = choose_asset(rel, current_filename="tool", app_name="tool", arch="x86_64", format_id="executable")
    assert c.asset.name == "tool-linux-amd64" and not c.ambiguous
    only_archives = Release("v1", assets=[Asset("tool.tar.gz", "https://x/t"), Asset("tool.zip", "https://x/z")])
    assert choose_asset(only_archives, current_filename="tool", app_name="tool", arch="x86_64",
                        format_id="executable") is None
    # AppImage behaviour is untouched
    ai = Release("v1", assets=[Asset("tool-linux-amd64", "https://x/a")])
    assert choose_asset(ai, current_filename="Tool.AppImage", app_name="Tool", arch="x86_64") is None


def test_checker_reports_executable_specific_message():
    class Fake:
        def releases(self, owner, name, per_page=30):
            return [Release("v2", assets=[Asset("tool.tar.gz", "https://x/t")])]
    out = check_for_update(repo_url="o/r", installed_version="1", current_filename="tool", app_name="tool",
                           client=Fake(), format_id="executable")
    assert out.status is UpdateStatus.UNAVAILABLE and "executable" in out.message


class _Server:
    def __init__(self, routes):
        outer = routes

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = outer.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_install_executable_update_validates_backs_up_with_bak_suffix(tmp_path):
    target = make_exec(tmp_path / "bin", "tool", ELF + b"old")
    new = ELF + b"new-version"
    srv = _Server({"/tool-linux-amd64": new, "/page": b"<html>not a binary, just a long enough page</html>"})
    try:
        asset = {"name": "tool-linux-amd64", "url": srv.url + "/tool-linux-amd64", "size": len(new), "digest": None}
        res = installer.install_update(target, asset, [asset], old_version="1.0", format_id="executable")
        assert target.read_bytes() == new and os.access(target, os.X_OK)
        bk = Path(res.backup_path)
        assert bk.name == "tool-1.0.bak" and bk.parent.name == ".tool.backups" and bk.read_bytes().endswith(b"old")
        html = {"name": "page", "url": srv.url + "/page", "size": 0, "digest": None}
        with pytest.raises(installer.InstallError, match="not a Linux executable"):
            installer.install_update(target, html, [html], old_version="2.0", format_id="executable")
        assert target.read_bytes() == new                                  # untouched
        assert not list(target.parent.glob(".tool.*.part"))
    finally:
        srv.close()


def test_rollback_of_an_executable_uses_bak_backups(service, tmp_path):
    from appforge.core.backups import BackupService, is_backup_file
    p = make_exec(tmp_path / "bin", "tool", ELF + b"v2")
    e = service.add_application(str(p))
    bdir = p.parent / ".tool.backups"
    bdir.mkdir()
    old = bdir / "tool-1.0.bak"
    old.write_bytes(ELF + b"v1")
    assert is_backup_file(old) and not is_backup_file(p)
    b = BackupService(service)
    recs = b.list_backups(e.id)                                          # adopted from disk
    assert [r.version for r in recs] == ["1.0"]
    res = b.rollback(e.id, str(old))
    assert p.read_bytes().endswith(b"v1") and res.saved_version == e.installed_version
    names = sorted(r.path.rsplit("/", 1)[1] for r in b.list_backups(e.id))
    assert len(names) == 1 and names[0].endswith(".bak")
    bad = bdir / "tool-0.1.bak"
    bad.write_bytes(b"<html>nope nope nope nope nope</html>")
    with pytest.raises(LibraryError, match="can't be restored"):
        b.rollback(e.id, str(bad))


# ------------------------------------------------------------------------------- categories
def entry(name, **kw):
    meta = kw.pop("metadata", {})
    return AppEntry(name=name, path=kw.pop("path", f"/opt/{name}.AppImage"), metadata=meta, **kw)


def test_category_derivation_and_user_override():
    assert derived_category(entry("a", metadata={"categories": "Utility;Development;IDE;"})) == "Development"
    assert derived_category(entry("a", metadata={"categories": "AudioVideo;Player;"})) == "Multimedia"
    assert derived_category(entry("a", metadata={"categories": "Qt;"})) == "Other"
    assert derived_category(entry("a")) == "Other"
    e = entry("a", metadata={"categories": "Game;", "category": "  Work   stuff "})
    assert category_of(e) == "Work stuff"
    assert category_of(entry("b", metadata={"categories": "Game;"})) == "Games"


def test_categories_in_use_and_suggestions():
    apps = [entry("a", metadata={"categories": "Game;"}), entry("b"), entry("c", metadata={"category": "Zeta"}),
            entry("d", metadata={"category": "alpha"})]
    assert categories_in_use(apps) == ["alpha", "Games", "Zeta", "Other"]
    sug = category_suggestions(apps)
    assert sug[-1] == "Other" and "Zeta" in sug and "Development" in sug and sug.count("Other") == 1


def test_set_category_via_service_and_it_survives_refresh(service, tmp_path):
    p = make_exec(tmp_path, "tool-1.0")
    e = service.add_application(str(p))
    e = service.update_application(e.id, category="  Tools I like ")
    assert e.metadata["category"] == "Tools I like"
    e = service.refresh_metadata(e.id)
    assert category_of(e) == "Tools I like"
    e = service.update_application(e.id, category="")
    assert "category" not in e.metadata and category_of(e) == "Other"
    e = service.update_application(e.id, name="Renamed")             # untouched when not passed
    assert e.name == "Renamed"


# ------------------------------------------------------------------------------- filtering / sorting
def test_filter_matching():
    up = entry("Alpha", update_status=UpdateStatus.UPDATE_AVAILABLE, github_repo="https://github.com/o/a",
               metadata={"categories": "Development;"})
    ok = entry("Beta", update_status=UpdateStatus.UP_TO_DATE, github_repo="https://github.com/o/b")
    bad = entry("Gamma", update_status=UpdateStatus.FAILED, github_repo="https://github.com/o/c")
    free = entry("Delta")
    healthy = lambda e: True                                                       # noqa: E731
    f = lambda **k: [e.name for e in (up, ok, bad, free) if matches(e, Filter(**k), file_ok=healthy)]  # noqa: E731
    assert f() == ["Alpha", "Beta", "Gamma", "Delta"] and not Filter().active
    assert f(query="alp") == ["Alpha"] and f(query="  ") == ["Alpha", "Beta", "Gamma", "Delta"]
    assert f(query="development") == ["Alpha"]                                     # category is searchable
    assert f(status=UPDATES) == ["Alpha"]
    assert f(status=ATTENTION) == ["Gamma"]                                        # failed update
    assert f(status=UNLINKED) == ["Delta"]
    assert f(category="Development") == ["Alpha"] and f(category="Other") == ["Beta", "Gamma", "Delta"]
    assert Filter(category="x").active and Filter(status=UPDATES).active
    assert [e.name for e in (up, ok) if matches(e, Filter(status=ATTENTION), file_ok=lambda e: e is not up)] == ["Alpha"]
    assert f(query="alp", status=UPDATES, category="Development") == ["Alpha"]
    assert f(query="alp", status=UNLINKED) == []


def test_sorting():
    a = entry("beta", added_at=100, update_status=UpdateStatus.UP_TO_DATE)
    b = entry("Alpha", added_at=300, update_status=UpdateStatus.UPDATE_AVAILABLE)
    c = entry("gamma", added_at=200, update_status=UpdateStatus.FAILED)
    assert [e.name for e in sort_entries([a, b, c])] == ["Alpha", "beta", "gamma"]
    assert [e.name for e in sort_entries([a, b, c], SORT_RECENT)] == ["Alpha", "gamma", "beta"]
    assert [e.name for e in sort_entries([a, b, c], SORT_STATUS)] == ["Alpha", "gamma", "beta"]
    assert [e.name for e in sort_entries([a, b, c], "bogus")] == ["Alpha", "beta", "gamma"]


# ------------------------------------------------------------------------------- notifications
def avail(service, tmp_path, name="app", latest="2.0"):
    p = make_exec(tmp_path / name, f"{name}-1.0")
    e = service.add_application(str(p), github_repo="o/r")
    e.update_status, e.latest_version = UpdateStatus.UPDATE_AVAILABLE, latest
    service.db.update(e)
    return service.db.get(e.id)


def test_notify_once_per_version(service, tmp_path):
    svc = UpdateService(service)
    e = avail(service, tmp_path)
    assert svc.should_notify(e) and [x.id for x in svc.pending_notifications()] == [e.id]
    svc.mark_notified(e.id)
    e = service.get(e.id)
    assert e.metadata[NOTIFIED_KEY] == "2.0" and not svc.should_notify(e) and svc.pending_notifications() == []
    e.latest_version = "2.1"                                    # a newer release -> notify again
    service.db.update(e)
    assert svc.should_notify(service.get(e.id))
    e = service.get(e.id)
    e.update_status = UpdateStatus.UP_TO_DATE
    assert not svc.should_notify(e)
    assert not svc.should_notify(entry("x", update_status=UpdateStatus.UPDATE_AVAILABLE))   # no version


def test_notified_marker_survives_a_new_check_result(service, tmp_path):
    from appforge.core.updates.checker import CheckOutcome
    svc = UpdateService(service)
    e = avail(service, tmp_path)
    svc.mark_notified(e.id)
    outcome = CheckOutcome(UpdateStatus.UPDATE_AVAILABLE, latest_version="2.0", tag="v2.0",
                           asset={"name": "a", "url": "u", "size": 1, "digest": None})
    e = svc.apply_check(e.id, outcome)
    assert not svc.should_notify(e)


def test_summarize_updates_text_is_plain_and_bounded():
    one = entry("My App", installed_version="1.0", latest_version="1.1")
    title, body = summarize_updates([one])
    assert title == "Update available for My App" and "1.0" in body and "1.1" in body
    many = [entry(f"App{i}\n\x07", latest_version=f"{i}.0") for i in range(7)]
    title, body = summarize_updates(many)
    assert title == "7 application updates available" and "and 3 more" in body
    assert "\x07" not in body and body.count("\n") == 4
    long_t, _ = summarize_updates([entry("x" * 300, latest_version="1")])
    assert len(long_t) < 100


# ------------------------------------------------------------------------- self-hosted servers (0.5.4)
@pytest.mark.parametrize("text,expected", [
    ("https://git.magicbean.dev/MagicBeanDev/Longshot", ("git.magicbean.dev", "MagicBeanDev", "Longshot")),
    ("git.magicbean.dev/MagicBeanDev/Longshot.git", ("git.magicbean.dev", "MagicBeanDev", "Longshot")),
    ("https://git.magicbean.dev/MagicBeanDev/Longshot/releases/tag/v1",
     ("git.magicbean.dev", "MagicBeanDev", "Longshot")),
    ("git@git.magicbean.dev:MagicBeanDev/Longshot.git", ("git.magicbean.dev", "MagicBeanDev", "Longshot")),
    ("https://git.example.dev:3000/o/r/src/branch/main", ("git.example.dev:3000", "o", "r")),
    ("https://git.example.dev/group/sub/proj", ("git.example.dev", "group/sub", "proj")),
])
def test_parse_source_accepts_self_hosted_servers(text, expected):
    ref = parse_source(text)
    assert ref.provider == "custom" and (ref.host, ref.owner, ref.name) == expected
    assert ref.url == f"https://{expected[0]}/{expected[1]}/{expected[2]}"


def test_self_hosted_client_probes_forgejo_then_gitlab_and_remembers():
    forgejo = [{"tag_name": "v1.0", "assets": [
        {"name": "A.AppImage", "browser_download_url": "https://git.x.dev/a/A.AppImage", "size": 3}]}]
    seen = []

    def fn(req, timeout=None):
        seen.append(req.full_url)
        if "/api/v1/" in req.full_url:
            return FakeResp(forgejo)
        raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)

    c = SelfHostedClient("git.x.dev", opener=fn)
    assert [r.tag for r in c.releases("o", "r")] == ["v1.0"]
    c.releases("o", "r")
    assert len(seen) == 2 and all("/api/v1/" in u for u in seen)

    gl = [{"tag_name": "v2", "assets": {"links": [{"name": "x", "direct_asset_url": "https://h/B.AppImage"}]}}]
    seen.clear()

    def fn2(req, timeout=None):
        seen.append(req.full_url)
        if "/api/v4/" in req.full_url:
            return FakeResp(gl)
        raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)

    assert [r.tag for r in SelfHostedClient("git.x.dev", opener=fn2).releases("g/s", "p")] == ["v2"]
    assert "g%2Fs%2Fp" in seen[-1]


def test_self_hosted_client_reports_unknown_servers_and_network_errors():
    def nf(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
    with pytest.raises(GitHubError) as e:
        SelfHostedClient("git.x.dev", opener=nf).releases("o", "r")
    assert e.value.kind == "not_found" and "git.x.dev" in str(e.value)

    calls = []

    def down(req, timeout=None):
        calls.append(1)
        raise urllib.error.URLError("boom")
    with pytest.raises(GitHubError) as e:
        SelfHostedClient("git.x.dev", opener=down).releases("o", "r")
    assert e.value.kind == "network" and len(calls) == 1      # no pointless second probe


def test_client_for_custom_host_never_gets_the_github_token():
    c = client_for(parse_source("https://git.magicbean.dev/MagicBeanDev/Longshot"), "secret")
    assert isinstance(c, SelfHostedClient) and not hasattr(c, "token")
