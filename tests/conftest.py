import os
import socket
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

import make_fixtures  # noqa: E402


@pytest.fixture
def local_tcp():
    """Skip real HTTP tests only when the host forbids local TCP sockets."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(('127.0.0.1', 0))
    except PermissionError as exc:
        pytest.skip(f'Local TCP sockets are prohibited: {exc}')


@pytest.fixture
def local_unix(tmp_path):
    """The process handoff test also needs Unix sockets for multiprocessing."""
    path = str(tmp_path / 'probe.sock')
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.bind(path)
    except PermissionError as exc:
        pytest.skip(f'Local Unix sockets are prohibited: {exc}')
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory):
    if not Path(make_fixtures.APPIMAGETOOL).exists():
        pytest.skip("appimagetool not available to build fixtures")
    return make_fixtures.build_default_set(tmp_path_factory.mktemp("fx"))


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TUXSHELF_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture()
def service(data_dir):
    from tuxshelf.core.database import Database
    from tuxshelf.core.library import LibraryService
    from tuxshelf.core.paths import database_path, icons_dir
    db = Database(database_path())
    yield LibraryService(db, icons_dir())
    db.close()
