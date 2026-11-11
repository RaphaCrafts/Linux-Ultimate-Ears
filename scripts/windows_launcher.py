"""Bootstrap an isolated Windows source install, then run the desktop app."""
import hashlib
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import venv


def main(log):
    if sys.platform != 'win32' or not (3, 11) <= sys.version_info[:2] < (3, 15):
        raise RuntimeError('Speaker studio needs Python 3.11 through 3.14 on Windows.')
    root = Path(__file__).resolve().parents[1]
    environment = root / '.venv-windows'
    python = environment / 'Scripts' / 'python.exe'
    if not python.exists():
        print('Setting up Speaker studio. First launch requires internet access.', file=log, flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    # Editable installs point at an absolute source directory. Reinstall after
    # the repository moves, even when its requirements have not changed.
    fingerprint = hashlib.sha256(str(root).encode() + (root / 'pyproject.toml').read_bytes()).hexdigest()
    marker = environment / 'speaker-studio-installed'
    if not marker.exists() or marker.read_text() != fingerprint:
        subprocess.run([str(python), '-m', 'pip', 'install', '-e', str(root)], check=True,
                       stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        marker.write_text(fingerprint)
    pythonw = environment / 'Scripts' / 'pythonw.exe'
    return subprocess.call([str(pythonw), '-m', 'speakerstudio.app', *sys.argv[1:]], cwd=root,
                           env={**os.environ, 'PYTHONUTF8': '1'}, stdout=log, stderr=subprocess.STDOUT)


if __name__ == '__main__':
    log_path = Path(__file__).resolve().parents[1] / '.local' / 'windows-launcher.log'
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('a', encoding='utf-8') as log:
            result = main(log)
            if result:
                raise RuntimeError(f'Speaker studio exited with code {result}.')
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        ctypes.windll.user32.MessageBoxW(None, f'Could not start Speaker studio: {error}\n\nDetails: {log_path}',
                                        'Speaker studio', 0x10)
        raise SystemExit(1)
