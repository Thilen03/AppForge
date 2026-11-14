"""v0.5.2: application-menu category and per-app environment variables."""
import os
import sys
from pathlib import Path

import pytest

from appforge.core.desktop import render_entry
from appforge.core.envvars import EnvVarError, parse_env_text
from appforge.core.library import LibraryError
from appforge.core.models import AppEntry
from appforge.services import launcher

sys.path.insert(0, str(Path(__file__).parent))
from test_desktop import make_app, parse_exec, read_entry_from_text  # noqa: E402


def test_parse_env_text():
    env = parse_env_text("A=1\n\n# comment\nexport B=two words\nC=x=y\nA=3\n")
    assert env == {"B": "two words", "C": "x=y", "A": "3"}
    assert list(env) == ["B", "C", "A"]          # a repeated name moves to the end


@pytest.mark.parametrize("bad", ["NOEQUALS", "1BAD=x", "A B=x", "=x", "OK=1\nBAD-NAME=2"])
def test_parse_env_text_rejects_bad_lines(bad):
    with pytest.raises(EnvVarError):
        parse_env_text(bad)


def test_menu_category_replaces_main_categories_but_keeps_extras(service, tmp_path):
    entry, _ = make_app(service, tmp_path, categories="Utility;Qt;")
    assert read_entry_from_text(render_entry(entry))["Categories"] == "Utility;Qt;"   # automatic
    entry.metadata["menu_category"] = "Game"
    assert read_entry_from_text(render_entry(entry))["Categories"] == "Game;Qt;"


def test_menu_category_without_app_categories(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    entry.metadata["menu_category"] = "Graphics"
    assert read_entry_from_text(render_entry(entry))["Categories"] == "Graphics;"


def test_invalid_stored_menu_category_is_ignored(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    entry.metadata["menu_category"] = "Bogus"
    assert read_entry_from_text(render_entry(entry))["Categories"] == "Utility;"


def test_exec_uses_env_prefix(service, tmp_path):
    entry, target = make_app(service, tmp_path, desktop_exec="app %U")
    entry.metadata["env_vars"] = {"QT_QPA_PLATFORM": "xcb", "GREETING": "hello world $x"}
    argv = parse_exec(read_entry_from_text(render_entry(entry))["Exec"])
    assert argv == ["env", "QT_QPA_PLATFORM=xcb", "GREETING=hello world $x", str(target), "%U"]


def test_add_and_update_application_store_and_sync(service, tmp_path):
    target = tmp_path / "apps" / "Tool.sh"
    target.parent.mkdir()
    target.write_text("#!/bin/sh\necho hi\n")
    target.chmod(0o755)
    entry = service.add_application(str(target), integrate_desktop=True, menu_category="Development",
                                    env_vars={"FOO": "bar"})
    assert entry.metadata["menu_category"] == "Development" and entry.metadata["env_vars"] == {"FOO": "bar"}
    data = read_entry_from_text(service.desktop.entry_path(entry.id).read_text("utf-8"))
    assert data["Categories"].startswith("Development;") and parse_exec(data["Exec"])[:2] == ["env", "FOO=bar"]

    entry = service.update_application(entry.id, menu_category=None, env_vars={})
    assert "menu_category" not in entry.metadata and "env_vars" not in entry.metadata
    data = read_entry_from_text(service.desktop.entry_path(entry.id).read_text("utf-8"))
    assert parse_exec(data["Exec"])[0] == str(target) and data["Categories"] == "Utility;"

    # leaving the arguments out leaves the stored values alone
    entry = service.update_application(entry.id, menu_category="Office", env_vars={"A": "1"})
    entry = service.update_application(entry.id, name="Renamed")
    assert entry.metadata["menu_category"] == "Office" and entry.metadata["env_vars"] == {"A": "1"}


def test_library_rejects_invalid_input(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    with pytest.raises(LibraryError):
        service.update_application(entry.id, menu_category="Bogus")
    with pytest.raises(LibraryError):
        service.update_application(entry.id, env_vars={"1BAD": "x"})


def test_launch_applies_env_vars(service, tmp_path, data_dir, monkeypatch):
    out = tmp_path / "out.txt"
    script = tmp_path / "run.sh"
    script.write_text(f'#!/bin/sh\nprintf "%s|%s" "$APPFORGE_TEST_VAR" "$APPDIR" > "{out}"\n')
    script.chmod(0o755)
    monkeypatch.setenv("APPDIR", "/leaky")
    entry = AppEntry(name="Run", path=str(script), format="executable",
                     metadata={"env_vars": {"APPFORGE_TEST_VAR": "hello world"}})
    handle = launcher.launch(entry)
    handle.process.wait(timeout=10)
    assert out.read_text() == "hello world|"       # variable set, leaky AppImage var still stripped
