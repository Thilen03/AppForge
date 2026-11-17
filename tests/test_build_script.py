"""Run build setup with stale console launchers; stop before any real bundling."""
from pathlib import Path
import shutil
import subprocess


def test_build_uses_python_modules_after_directory_rename(tmp_path):
    root = tmp_path / 'TuxShelf renamed'
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    script = scripts / 'build_appimage.sh'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'scripts/build_appimage.sh', script)
    package = root / 'src/tuxshelf'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('__version__ = "0.6.7"\n')
    binaries = root / '.venv-build/bin'
    binaries.mkdir(parents=True)
    # An existing environment's console scripts still point at its old home.
    for name in ('pip', 'pyinstaller'):
        launcher = binaries / name
        launcher.write_text('#!/nonexistent/old-appforge/bin/python3\n')
        launcher.chmod(0o755)
    interpreter = binaries / 'python3'
    interpreter.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$(dirname "$0")/calls"
if [ "$1" = -m ] && [ "$2" = pip ]; then exit 0; fi
if [ "$1" = -m ] && [ "$2" = PyInstaller ]; then exit 42; fi
exit 99
''')
    interpreter.chmod(0o755)
    result = subprocess.run(['bash', str(script)], capture_output=True, text=True)
    assert result.returncode == 42, result.stdout + result.stderr
    calls = (binaries / 'calls').read_text().splitlines()
    assert calls[:2] == ['-m pip install -q --upgrade pip',
                         '-m pip install -q -r requirements-build.txt']
    assert calls[2].startswith('-m PyInstaller --noconfirm --clean ')
    assert 'bad interpreter' not in result.stderr
    assert not (root / 'dist').exists()
