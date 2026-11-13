"""Render review screenshots (offscreen). Usage: python scripts/screenshots.py OUTDIR"""
import os, sys, tempfile, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "src"), str(root / "tests")]
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
os.environ["APPFORGE_DATA_DIR"] = tempfile.mkdtemp()
from PySide6.QtWidgets import QApplication
import make_fixtures
from appforge.core.database import Database
from appforge.core.library import LibraryService
from appforge.core.paths import database_path, icons_dir
from appforge.ui import theme
from appforge.ui.main_window import MainWindow
from appforge.ui.dialogs import AddApplicationDialog, EditApplicationDialog

app = QApplication([]); theme.apply_theme(app)
fx = make_fixtures.build_default_set(Path(tempfile.mkdtemp()))
svc = LibraryService(Database(database_path()), icons_dir())
def pump(n=30):
    for _ in range(n): app.processEvents(); time.sleep(0.02)
w = MainWindow(svc); w.resize(1040, 640); w.show(); pump(); w.grab().save(str(out / "empty.png"))
for k in ("alpha", "beta", "gamma"): svc.add_application(str(fx[k]))
svc.add_application(str(fx["alpha"].parent / "Tools" / "gamma-tool.AppImage")) if False else None
e = svc.add_application(str(make_fixtures.build(Path(tempfile.mkdtemp()), "delta", "Delta Notes", None, "#1c7ed6", metainfo=False)))
Path(e.path).unlink()
fx["gamma"].chmod(0o644)
w.reload(); pump(); w.card_hover = w._cards[0]; w._cards[0]._reveal(True); pump(20)
w.grab().save(str(out / "library_light.png"))
d = AddApplicationDialog(svc, w, str(fx["beta"].parent / "BetaEmu.AppImage")); d.show(); pump(); d.repo_edit.setText("github.com/x/y"); pump(5)
d.grab().save(str(out / "add_dialog.png"))
ed = EditApplicationDialog(svc, svc.list_applications()[0], w); ed.show(); pump(5); ed.grab().save(str(out / "edit_dialog.png"))
# dark
theme.apply_theme(app); 
from appforge.ui import theme as T
app.setStyle("Fusion"); T._current = T.DARK; app.setPalette(T._palette(T.DARK)); app.setStyleSheet(T.stylesheet(T.DARK)); w.reload(); pump()
w._cards[0]._reveal(True); pump(20); w.grab().save(str(out / "library_dark.png"))
print("saved", sorted(p.name for p in out.iterdir()))
