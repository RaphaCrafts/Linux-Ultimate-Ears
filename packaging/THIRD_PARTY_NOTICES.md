# Third-party components

Speaker studio is independent of Logitech / Ultimate Ears.

- **Speaker studio source:** GPL-3.0-or-later. See the repository LICENSE.
- **Qt for Python / PySide6, shiboken6 and Qt libraries:** LGPL-3.0, GPL and/or
  applicable upstream terms. Shared libraries remain dynamically loaded and
  replaceable after AppImage extraction. Corresponding upstream source:
  https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/
  and https://download.qt.io/archive/qt/6.8/6.8.3/single/ . LGPL text is included.
- **Python:** Python Software Foundation licence; included Python metadata and
  https://www.python.org/downloads/source/ .
- **dbus-next 0.2.3:** MIT; https://github.com/altdesktop/python-dbus-next .
- **PyInstaller bootloader:** GPL with its application distribution exception;
  https://pyinstaller.org/en/stable/license.html .
- **BlueZ sdptool helper:** GPL-2.0-or-later; unmodified system binary bundled
  for service discovery. Source: https://www.bluez.org/download/ and the host
  distribution's matching BlueZ source package. Exact build versions appear in
  the included BUILD-INFO.json. GPL-2.0 text is included.
- **X11/XCB cursor and bundled XCB libraries:** upstream permissive licences;
  Ubuntu package copyright notices are included with the bundle. Source:
  https://xcb.freedesktop.org/ .
- **AppImage runtime:** upstream type2 runtime and associated bundled notices:
  https://github.com/AppImage/type2-runtime . The packaging tool is not part of
  the application payload.
- **Product images:** Logitech / Ultimate Ears. No open-source licence is
  asserted for these images; assets/speakers/manifest.json contains provenance.

The AppImage can be extracted with --appimage-extract. Third-party shared
libraries are not statically linked into the application. Source is distributed
alongside the AppImage in the public repository, with no device addresses or
research APKs required to rebuild the application.
