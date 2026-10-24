# Building Speaker studio

The main README is for users. This document is for contributors and maintainers.

## Run from source

Python 3.11+ on Linux, BlueZ (`bluetoothd`, `sdptool`) and the usual Qt desktop
libraries are required. Ubuntu: `sudo apt install python3-venv bluez libxcb-cursor0`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m pip install -e .
.venv/bin/python -m speakerstudio.app
# No Bluetooth access, simulated devices:
.venv/bin/python -m speakerstudio.app --demo
.venv/bin/python -m pytest -q
```

Run tests outside restrictive sandboxes which prohibit Unix socketpair traffic.
The protocol tests use local socketpairs, not Bluetooth hardware. GUI tests run
offscreen with temporary preferences. No unit test changes real speaker settings.

## AppImage

The current binary targets **x86_64 Linux**, built on Ubuntu/Zorin 24.04 with
Python 3.12. A bundled Python runtime does not remove glibc requirements. Treat
Ubuntu 24.04 or newer as the current baseline; other distributions and older
glibc versions require testing. No ARM build is supplied.

The builder includes PySide6/Qt, Python, dbus-next, images, licences, the X11
cursor library and `sdptool`. The cursor library must be installed on the build
host (`libxcb-cursor0`), or extracted under
`.local/tools/xcb/usr/lib/x86_64-linux-gnu/` using `apt-get download` and `dpkg-deb -x`.
BlueZ itself and the desktop session remain host services. No root application
or background service is installed. Desktop pairing stays in system Bluetooth
settings. RFCOMM channel discovery searches the speaker's SPP service rather
than assuming channel 1. Source and helper build metadata accompany the bundle.

Download official packaging tools into ignored local storage:

```bash
mkdir -p .local/tools
curl -fL -o .local/tools/appimagetool \
  https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
curl -fL -o .local/tools/runtime-x86_64 \
  https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64
chmod +x .local/tools/appimagetool
scripts/build_appimage.sh
```

The builder verifies pinned hashes of the two upstream artifacts. The upstream
`continuous` URLs can change; if a hash fails, obtain the matching artifact or
review the new release and deliberately update the pins. Never bypass the check.
Qt/Python wheels and their dependencies should be obtained from the same
requirements/build record when reproducing a particular binary.

The script runs tests, builds a PyInstaller one-directory application, verifies
its images offscreen, packages a type-2 AppImage and smoke-tests the AppImage
using its extract-and-run mode. It writes `downloads/Speaker-Studio-x86_64.AppImage`
and `downloads/SHA256SUMS`. The GitHub size limit is 100 MiB per file; if a future
build exceeds it, use a GitHub Release asset and update the README download URL.
Do not commit an unusable pointer or claim an unverified build succeeded.

## Implementation boundaries

### Windows source launcher

Run `Speaker-Studio.bat` from the repository root. The standard-library bootstrap
creates `.venv-windows` and installs an editable copy of the project. A hash of
`pyproject.toml` or a changed repository location triggers dependency setup again;
otherwise startup needs no package download. Keep the repository's assets beside
its source. This is a source launcher, not a standalone executable distribution.

`windows.py` implements paired Classic inventory and SPP discovery/connection
using [PyWinRT](https://pywinrt.readthedocs.io/en/latest/installing/). The transport
follows Microsoft's [RFCOMM client sample](https://github.com/microsoft/Windows-universal-samples/blob/main/Samples/BluetoothRfcommChat/cs/Scenario1_ChatClient.xaml.cs):
resolve the serial-port service, open a StreamSocket, and read partial frames
using DataReader. The worker initializes its own multithreaded COM apartment.
Windows settings use an INI file rather than the registry, allowing isolated
test settings and ordinary per-user storage. Bluetooth identifiers stay local.

Run `Speaker-Studio.bat --smoke-test` to check the UI and assets, or install pytest
in a development environment and run `python -m pytest -q`. Windows tests cover
SPP API selection, failed-connection cleanup, async frame dispatch and timeout,
and disabling Linux Computer mix. Windows BLE discovery uses an active
advertisement watcher, hands callbacks to the asyncio worker, and decodes the
same FE61 manufacturer layout as Linux. Only a fresh, validated beacon matched
to a paired Classic address enables wake. GATT discovery must find the exact
writable wake characteristic; the payload contains the Windows adapter address.
The controller verifies RFCOMM identity/readback after wake. A custom Windows
name does not hide a speaker matched through its validated beacon. Recognized
pairings remain visible for the session after the pre-wake beacon is invalidated.

Worker shutdown cancels and drains native reads before closing its COM apartment.
Do not repeatedly cancel a WinRT reader while it waits for native cancellation
completion. See [Windows validation](windows-validation.md) for physical results
and the receiver proxy-level and listening-test limits. A new receiver handoff
settles for six seconds before switching modes. Windows releases the receiver's
direct control stream after joining, since it can silently stall in native
receiver mode. Receiver read timeouts invalidate only that direct connection.

### Shared controller

The packet codec, asynchronous controller, BlueZ integration and Qt UI are
separate modules. Requests are serialized per speaker. Timed-out sessions close
rather than reusing a stream where late responses could satisfy a new request.
Only verified legacy model identities unlock controls. Artwork choice is a
local preference and never selects a protocol. Unknown/CPP devices must not
receive guessed legacy writes. Source research remains under `docs/`.

Battery display matches the Android rounding convention. Device addresses and
preferences remain on the user's machine; no telemetry or cloud account exists.
The application does not route music itself. Audio remains managed by the Linux
desktop's sound settings and player.

## Check a packaged build against hardware

For maintainers, a read-only diagnostic uses the same BlueZ discovery, bundled
SDP helper, protocol transport and controller as the window:

```bash
./downloads/Speaker-Studio-x86_64.AppImage --check-speaker YOUR_BLUETOOTH_ADDRESS
```

It connects to an already-paired, powered-on speaker, prints sanitized readings,
and disconnects without changing settings. Do not post actual addresses in
issues. Use `--appimage-extract-and-run` first if FUSE is unavailable.
