import os
import time
from pathlib import Path

import pytest

from appforge.core.database import Database
from appforge.core.formats.appimage import suggest_name_from_filename, version_from_filename
from appforge.core.github_url import parse_repo
from appforge.core.library import FileState, LibraryError, LibraryService, file_state, inspect_file
from appforge.core.paths import database_path, icons_dir
from appforge.services import launcher


def test_name_and_version_from_filename():
    assert suggest_name_from_filename("Dolphin-Emu-5.0-x86_64.AppImage") == "Dolphin Emu"
    assert suggest_name_from_filename("balenaEtcher-1.18.11-x64.AppImage") == "balenaEtcher"
    assert version_from_filename("krita-5.2.2-x86_64.appimage") == "5.2.2"
    assert version_from_filename("nightly.AppImage") is None


@pytest.mark.parametrize("text,expected", [
    ("https://github.com/owner/repo", ("owner", "repo")),
    ("github.com/owner/repo.git", ("owner", "repo")),
    ("https://github.com/owner/repo/releases/latest", ("owner", "repo")),
    ("git@github.com:owner/repo.git", ("owner", "repo")),
    ("owner/my.repo-name", ("owner", "my.repo-name")),
])
def test_parse_repo_ok(text, expected):
    assert tuple(parse_repo(text)) == expected


@pytest.mark.parametrize("text", ["", "https://gitlab.com/a/b", "notarepo", "https://github.com/onlyowner"])
def test_parse_repo_bad(text):
    assert parse_repo(text) is None


def test_extract_metadata_desktop_version_and_icon(fixtures):
    md = inspect_file(fixtures["alpha"])
    assert md.name_suggestion == "Alpha Editor"
    assert md.version == "2.3.1" and md.extra["version_source"] == "desktop"
    assert md.icon_ext == "png" and md.icon_data.startswith(b"\x89PNG")
    assert md.description == "Fixture app Alpha Editor"


def test_extract_metadata_falls_back_to_metainfo_release(fixtures):
    md = inspect_file(fixtures["beta"])
    assert md.version == "1.4.2" and md.extra["version_source"] == "metainfo"


def test_inspect_rejects_non_appimage(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    with pytest.raises(LibraryError):
        inspect_file(f)
    with pytest.raises(LibraryError):
        inspect_file(tmp_path / "missing.AppImage")


def test_add_preserves_location_and_persists(fixtures, data_dir):
    db = Database(database_path())
    svc = LibraryService(db, icons_dir())
    before = fixtures["alpha"].stat().st_mtime_ns
    entry = svc.add_application(str(fixtures["alpha"]), github_repo="github.com/o/r")
    assert entry.path == str(fixtures["alpha"])          # not moved / copied
    assert fixtures["alpha"].exists() and fixtures["alpha"].stat().st_mtime_ns == before
    assert entry.github_repo == "https://github.com/o/r"
    assert Path(entry.icon_path).is_file()
    db.close()

    # simulate an app restart
    db2 = Database(database_path())
    again = LibraryService(db2, icons_dir()).list_applications()
    assert [a.name for a in again] == ["Alpha Editor"]
    assert again[0].installed_version == "2.3.1" and again[0].github_repo == "https://github.com/o/r"
    db2.close()


def test_duplicate_and_invalid_repo(fixtures, service):
    service.add_application(str(fixtures["alpha"]))
    with pytest.raises(LibraryError):
        service.add_application(str(fixtures["alpha"]))
    with pytest.raises(LibraryError):
        service.add_application(str(fixtures["beta"]), github_repo="not a repo")


def test_edit_rename_repo_version(fixtures, service):
    e = service.add_application(str(fixtures["alpha"]))
    e = service.update_application(e.id, name="My Editor", github_repo="o/r", installed_version="9.9")
    assert (e.name, e.github_repo, e.installed_version) == ("My Editor", "https://github.com/o/r", "9.9")
    e = service.update_application(e.id, github_repo=None)       # remove association
    assert e.github_repo is None
    with pytest.raises(LibraryError):
        service.update_application(e.id, name="  ")


def test_missing_file_and_relink(fixtures, service, tmp_path):
    import shutil
    moved_src = tmp_path / "copy.AppImage"
    shutil.copy(fixtures["alpha"], moved_src)
    e = service.add_application(str(moved_src))
    assert file_state(e) is FileState.OK
    new = tmp_path / "elsewhere"
    new.mkdir()
    moved_src.rename(new / "copy.AppImage")
    assert file_state(e) is FileState.MISSING
    with pytest.raises(launcher.LaunchError) as ei:
        launcher.launch(e)
    assert ei.value.state is FileState.MISSING
    e = service.update_application(e.id, path=str(new / "copy.AppImage"))
    assert file_state(e) is FileState.OK


def test_remove_keeps_file_and_deletes_icon(fixtures, service):
    e = service.add_application(str(fixtures["alpha"]))
    icon = Path(e.icon_path)
    service.remove_application(e.id)
    assert fixtures["alpha"].exists() and not icon.exists()
    assert service.list_applications() == []


def test_launch_and_not_executable(fixtures, service, tmp_path):
    import shutil
    p = tmp_path / "L.AppImage"
    shutil.copy(fixtures["alpha"], p)
    e = service.add_application(str(p))
    h = launcher.launch(e)
    time.sleep(0.5)
    assert "started" in h.log_tail() or h.early_exit_code() is None
    h.process.wait(timeout=10)
    p.chmod(0o644)
    with pytest.raises(launcher.LaunchError) as ei:
        launcher.launch(e)
    assert ei.value.state is FileState.NOT_EXECUTABLE
    launcher.make_executable(p)
    assert os.access(p, os.X_OK)


def test_launch_reports_early_failure(fixtures, service):
    e = service.add_application(str(fixtures["gamma"]))
    h = launcher.launch(e)
    h.process.wait(timeout=10)
    assert h.early_exit_code() == 3 and "boom" in h.log_tail()


def test_clean_environment_restores_ld_library_path():
    env = launcher.clean_environment({"LD_LIBRARY_PATH": "/bundle", "LD_LIBRARY_PATH_ORIG": "/usr/lib",
                                      "APPDIR": "/x", "_AF_BUNDLED": "1", "HOME": "/h"})
    assert env == {"LD_LIBRARY_PATH": "/usr/lib", "HOME": "/h"}
    env = launcher.clean_environment({"LD_LIBRARY_PATH": "/bundle", "_AF_BUNDLED": "1"})
    assert "LD_LIBRARY_PATH" not in env
