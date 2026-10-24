"""Bootstrap an isolated Windows source install, then run the desktop app."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    if sys.platform != 'win32' or sys.version_info < (3, 11):
        print('Speaker studio needs Python 3.11 or newer on Windows.')
        return 1
    root = Path(__file__).resolve().parents[1]
    environment = root / '.venv-windows'
    python = environment / 'Scripts' / 'python.exe'
    if not python.exists():
        print('Setting up Speaker studio. First launch requires internet access.', flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    fingerprint = hashlib.sha256((root / 'pyproject.toml').read_bytes()).hexdigest()
    marker = environment / 'speaker-studio-installed'
    if not marker.exists() or marker.read_text() != fingerprint:
        subprocess.run([str(python), '-m', 'pip', 'install', '-e', str(root)], check=True)
        marker.write_text(fingerprint)
    # Keep the console available for installation/Bluetooth error messages.
    return subprocess.call([str(python), '-m', 'speakerstudio.app', *sys.argv[1:]], cwd=root,
                           env={**os.environ, 'PYTHONUTF8': '1'})


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        print('Could not start Speaker studio: ' + str(error))
        raise SystemExit(1)
