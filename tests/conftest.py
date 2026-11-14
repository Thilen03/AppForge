import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

import make_fixtures  # noqa: E402


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory):
    if not Path(make_fixtures.APPIMAGETOOL).exists():
        pytest.skip("appimagetool not available to build fixtures")
    return make_fixtures.build_default_set(tmp_path_factory.mktemp("fx"))


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APPFORGE_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture()
def service(data_dir):
    from appforge.core.database import Database
    from appforge.core.library import LibraryService
    from appforge.core.paths import database_path, icons_dir
    db = Database(database_path())
    yield LibraryService(db, icons_dir())
    db.close()
