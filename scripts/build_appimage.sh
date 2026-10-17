#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
python_bin="${SPEAKER_STUDIO_PYTHON:-$project_root/.venv/bin/python}"
appimage_tool="$project_root/.local/tools/appimagetool"
runtime="$project_root/.local/tools/runtime-x86_64"
[[ "$(uname -m)" == x86_64 ]] || { echo 'This build targets x86_64 Linux.' >&2; exit 1; }
[[ -x "$appimage_tool" && -f "$runtime" ]] || { echo 'Download the verified AppImage tools described in docs/development.md.' >&2; exit 1; }
printf '%s  %s\n' 95cbe7cce9717fce90c484e34052ee7c7f1d7635b33c12525b4776826a7d29b6 "$appimage_tool" | sha256sum -c -
printf '%s  %s\n' 156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074 "$runtime" | sha256sum -c -
sdp_helper="$(command -v sdptool)"
cursor_lib="$project_root/.local/tools/xcb/usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0"
if [[ ! -f "$cursor_lib" ]]; then
  cursor_lib="$(ldconfig -p | awk '/libxcb-cursor.so.0/{print $NF; exit}')"
fi
[[ -f "$cursor_lib" ]] || { echo 'Install libxcb-cursor0 for building (or extract it locally as described in the developer guide).' >&2; exit 1; }
"$python_bin" -m pytest -q
"$python_bin" -m PyInstaller --noconfirm --clean --onedir --name speaker-studio \
  --paths src --add-data 'assets:assets' --add-data 'LICENSE:licences' \
  --add-data 'packaging/licenses:licences' --add-data 'packaging/THIRD_PARTY_NOTICES.md:licences' \
  --copy-metadata dbus-next --copy-metadata PySide6-Essentials --copy-metadata shiboken6 \
  --add-binary "$sdp_helper:helpers" --add-binary "$cursor_lib:." packaging/launcher.py
appdir="$project_root/build/SpeakerStudio.AppDir"
mkdir -p "$appdir/usr/lib" "$project_root/downloads"
cp -a dist/speaker-studio "$appdir/usr/lib/"
cp packaging/AppRun "$appdir/AppRun"
cp packaging/speaker-studio.desktop "$appdir/speaker-studio.desktop"
cp assets/speaker-studio.svg "$appdir/speaker-studio.svg"
cp assets/speaker-studio.png "$appdir/speaker-studio.png"
cp assets/speaker-studio.png "$appdir/.DirIcon"
"$python_bin" - <<'PY'
import json,platform,subprocess
from pathlib import Path
info={'python':platform.python_version(),'platform':platform.platform(),
      'glibc':platform.libc_ver(),'bluez':subprocess.check_output(['bluetoothctl','--version'],text=True).strip(),
      'dependencies':subprocess.check_output(['.venv/bin/python','-m','pip','freeze'],text=True).splitlines()}
Path('build/SpeakerStudio.AppDir/usr/lib/speaker-studio/_internal/licences/BUILD-INFO.json').write_text(json.dumps(info,indent=2)+'\n')
PY
QT_QPA_PLATFORM=offscreen "$appdir/AppRun" --smoke-test
ARCH=x86_64 "$appimage_tool" --appimage-extract-and-run --runtime-file "$runtime" \
  "$appdir" "$project_root/downloads/Speaker-Studio-x86_64.AppImage"
chmod +x downloads/Speaker-Studio-x86_64.AppImage
(cd downloads && sha256sum Speaker-Studio-x86_64.AppImage > SHA256SUMS)
QT_QPA_PLATFORM=offscreen downloads/Speaker-Studio-x86_64.AppImage --appimage-extract-and-run --smoke-test
ls -lh downloads/Speaker-Studio-x86_64.AppImage
