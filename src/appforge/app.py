"""Application bootstrap."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import APP_DISPLAY_NAME, APP_ID, __version__
from .core.database import Database
from .core.library import LibraryService
from .core.paths import data_dir, database_path, icons_dir


def _setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        data_dir() / "appforge.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, handlers=[handler, logging.StreamHandler()],
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "appforge", "resources", name)
    return os.path.join(os.path.dirname(__file__), "resources", name)


def _teardown(app, window) -> None:
    """Destroy the window (and its thread pools) deterministically, before the QApplication goes."""
    import gc

    window._quitting = True      # really close (don't just hide to the tray)
    window.close()
    for pool in (window.check_pool, window.install_pool):
        pool.waitForDone(3000)
    window.deleteLater()
    app.processEvents()
    del window
    gc.collect()


def _selftest(path: str | None) -> int:
    """Headless smoke test used to verify packaged builds: ``appforge --selftest [file.AppImage]``."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from .core.library import inspect_file
    from .ui import theme
    from .ui.icons import app_pixmap
    from .ui.main_window import MainWindow

    os.environ["APPFORGE_DATA_DIR"] = tempfile.mkdtemp(prefix="appforge-selftest-")
    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)
    svg = resource_path("appforge.svg")
    assert not app_pixmap(svg, "x", 64).isNull(), "SVG rendering failed"
    db = Database(database_path())
    service = LibraryService(db, icons_dir())
    if path:
        md = inspect_file(path)
        print(f"name={md.name_suggestion!r} version={md.version!r} icon={md.icon_ext} "
              f"icon_bytes={len(md.icon_data or b'')} warnings={md.warnings}")
        added = service.add_application(path, metadata=md, integrate_desktop=True)
        launcher_file = service.desktop.entry_path(added.id)
        assert service.desktop_enabled(added) and launcher_file.is_file(), "launcher creation failed"
        assert str(Path(added.path)) in launcher_file.read_text("utf-8"), "launcher doesn't point at the app"
        print("launcher ok:", launcher_file.name)
    from .core.organize import category_of
    from .core.settings import AppSettings
    from .core.updates.providers import parse_source
    assert AppSettings(db).check_interval_hours >= 1 and parse_source("https://codeberg.org/o/r")
    if path:
        print("category:", category_of(added))
    window = MainWindow(service)
    window.show()
    app.processEvents()
    assert len(window._cards) == (1 if path else 0)
    if os.environ.get("APPFORGE_SELFTEST_NET"):
        import urllib.error
        from .core.updates.net import urlopen
        try:
            with urlopen("https://github.com/", timeout=20) as r:
                print("https ok: HTTP", r.status)
        except urllib.error.HTTPError as exc:   # an HTTP status still proves TLS verification worked
            print("https ok: HTTP", exc.code)
        except Exception as exc:  # noqa: BLE001
            print("https FAILED:", exc)
            _teardown(app, window)
            db.close()
            return 1
    print("selftest ok", "platform=" + app.platformName(), "dir=" + str(Path(database_path()).parent))
    _teardown(app, window)
    db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--selftest" in argv:
        rest = argv[argv.index("--selftest") + 1:]
        return _selftest(rest[0] if rest else None)
    if getattr(sys, "frozen", False):
        os.environ["_AF_BUNDLED"] = "1"  # see services.launcher.clean_environment
    _setup_logging()

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_ID)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(resource_path("appforge.png")))

    from .ui import theme
    from .ui.main_window import MainWindow

    theme.apply_theme(app)
    app.styleHints().colorSchemeChanged.connect(lambda *_: theme.apply_theme(app))

    db = Database(database_path())
    service = LibraryService(db, icons_dir())
    try:   # repair / adopt / clean up application-menu launchers (cheap: a few tiny files)
        report = service.sync_desktop_entries()
        if report.changed or report.failed:
            logging.getLogger(__name__).info(
                "Launcher sync: repaired=%s adopted=%s removed=%s failed=%s",
                report.repaired, report.adopted, report.removed, report.failed)
    except Exception:  # noqa: BLE001 - never block startup on launcher housekeeping
        logging.getLogger(__name__).warning("Launcher sync failed", exc_info=True)
    window = MainWindow(service, auto_check=True, tray_icon=app.windowIcon())
    window.show()
    code = app.exec()
    _teardown(app, window)
    db.close()
    return code
