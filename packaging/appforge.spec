# PyInstaller spec – run via scripts/build_appimage.sh (paths are relative to the repo root).
import glob, os
from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.getcwd())

binaries = []
# Qt 6.5+'s xcb plugin needs libxcb-cursor; bundle it if the build machine has it
# (Arch/KDE already ships it, but this makes the AppImage work on bare X11 setups too).
for pattern in ("/usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0*", "/usr/lib/libxcb-cursor.so.0*",
                "/usr/lib64/libxcb-cursor.so.0*"):
    for lib in glob.glob(pattern):
        if os.path.isfile(lib) and not os.path.islink(lib):
            binaries.append((lib, "."))
            break

EXCLUDES = [
    "tkinter", "unittest", "pydoc", "test", "PIL",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtNetwork",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtPrintSupport",
]

a = Analysis(
    [os.path.join(ROOT, "packaging", "entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=[(os.path.join(ROOT, "src", "appforge", "resources"), "appforge/resources")] + collect_data_files("certifi"),
    hiddenimports=["PySide6.QtSvg", "zstandard", "certifi"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="appforge", console=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="appforge")
