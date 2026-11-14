"""Build tiny but *real* AppImages for tests (needs appimagetool + mksquashfs)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
# Search order: $APPIMAGETOOL, PATH, the copy scripts/build_appimage.sh downloads.
APPIMAGETOOL = (os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
                or str(_REPO / "build" / "tools" / "appimagetool"))


def _png(path: Path, color: str, size: int = 128):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QColor, QImage  # QImage needs no QApplication
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(QColor(color))
    img.save(str(path))


def build(dest_dir: Path, name: str, display: str, version: str | None, color: str,
          run_script: str = "echo started; sleep 1", filename: str | None = None,
          metainfo: bool = True) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    appdir = dest_dir / f"{name}.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    appdir.mkdir(parents=True)
    run = appdir / "AppRun"
    run.write_text(f"#!/bin/sh\n{run_script}\n")
    run.chmod(0o755)
    extra = f"X-AppImage-Version={version}\n" if version else ""
    (appdir / f"{name}.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName={display}\nComment=Fixture app {display}\n"
        f"Exec={name}\nIcon={name}\nCategories=Utility;\n{extra}")
    _png(appdir / f"{name}.png", color)
    if metainfo and not version:
        mi = appdir / "usr/share/metainfo"
        mi.mkdir(parents=True)
        (mi / f"{name}.appdata.xml").write_text(
            '<component><id>x.y</id><name>Meta Name</name><releases>'
            '<release version="0.9" date="2023-01-01"/><release version="1.4.2" date="2024-05-01"/>'
            '</releases></component>')
    out = dest_dir / (filename or f"{display}-x86_64.AppImage")
    env = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    subprocess.run([APPIMAGETOOL, "--no-appstream", str(appdir), str(out)], check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(appdir)
    return out


def build_default_set(dest: Path) -> dict[str, Path]:
    return {
        "alpha": build(dest, "alpha", "Alpha Editor", "2.3.1", "#e8590c", filename="Alpha-Editor-2.3.1-x86_64.AppImage"),
        "beta": build(dest / "Games/Emulators", "beta", "Beta Emu", None, "#2f9e44", filename="BetaEmu.AppImage"),
        "gamma": build(dest / "Tools", "gamma", "Gamma Tool", "0.5.0", "#7048e8",
                       run_script="echo boom >&2; exit 3", filename="gamma-tool.AppImage"),
    }


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/af-fixtures")
    for k, v in build_default_set(out).items():
        print(k, v)
