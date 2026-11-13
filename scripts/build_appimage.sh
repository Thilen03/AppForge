#!/usr/bin/env bash
# Build AppForge into a self-contained AppImage.  Output: dist/AppForge-<version>-x86_64.AppImage
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
VERSION="$(python3 -c 'import re,pathlib;print(re.search(r"__version__ = \"(.+?)\"",pathlib.Path("src/appforge/__init__.py").read_text()).group(1))')"
ARCH="${ARCH:-x86_64}"
BUILD="$ROOT/build"
VENV="$ROOT/.venv-build"
OUT="$ROOT/dist/AppForge-${VERSION}-${ARCH}.AppImage"

echo "==> Python build environment"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r requirements-build.txt

echo "==> PyInstaller bundle"
rm -rf "$BUILD/dist" "$BUILD/work"
"$VENV/bin/pyinstaller" --noconfirm --clean --distpath "$BUILD/dist" --workpath "$BUILD/work" packaging/appforge.spec

echo "==> Assemble AppDir"
APPDIR="$BUILD/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$BUILD/dist/appforge" "$APPDIR/usr/lib/appforge"
install -m755 packaging/AppRun "$APPDIR/AppRun"
cp packaging/appforge.desktop "$APPDIR/appforge.desktop"
cp src/appforge/resources/appforge.png "$APPDIR/appforge.png"
cp src/appforge/resources/appforge.png "$APPDIR/.DirIcon"
cp src/appforge/resources/appforge.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/appforge.png"

echo "==> appimagetool"
TOOL="$(command -v appimagetool || true)"
if [ -z "$TOOL" ]; then
  TOOL="$BUILD/tools/appimagetool"
  if [ ! -x "$TOOL" ]; then
    mkdir -p "$BUILD/tools"
    curl -fL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$TOOL"
  fi
fi
mkdir -p "$ROOT/dist"
# EXTRACT_AND_RUN lets appimagetool itself run where FUSE is unavailable (containers, CI).
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$OUT"
chmod +x "$OUT"
echo "==> Built $OUT ($(du -h "$OUT" | cut -f1))"
