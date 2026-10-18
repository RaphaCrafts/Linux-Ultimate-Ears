"""Per-user Linux launcher registration for a portable AppImage."""
import os
import shlex
from pathlib import Path

APP_ID = 'speaker-studio'


def quote_exec(path):
    """Quote one Exec argument through desktop-entry and Exec escaping layers."""
    value = str(path)
    if any(c in value for c in '\n\r\0'):
        raise ValueError('The AppImage path contains an unsupported control character')
    for character in ('\\', '"', '`', '$'):
        value = value.replace(character, '\\'+character)
    value = value.replace('%', '%%')
    # The desktop-entry string layer is decoded before Exec argument parsing.
    return '"' + value.replace('\\', '\\\\') + '"'



def register_appimage(icon_path, environ=None):
    """Install only our launcher/icon, pointing at the persistent AppImage file.

    Source runs and packaging checks do not register a launcher. Reopening a moved
    AppImage updates its location. No elevated privileges or external installer are used.
    """
    env = os.environ if environ is None else environ
    image = env.get('APPIMAGE')
    if not image or not Path(image).is_file():
        return None
    image = Path(image).resolve()
    quote_exec(image)  # Reject control characters before writing any files.
    data = Path(env.get('XDG_DATA_HOME') or Path.home()/'.local/share')
    if not data.is_absolute():
        data = Path.home()/'.local/share'
    icons = data/'icons/hicolor/512x512/apps'
    apps = data/'applications'
    launcher = apps/(APP_ID+'.desktop')
    if launcher.exists() and 'X-SpeakerStudio-Managed=true' not in launcher.read_text().splitlines():
        raise ValueError('An existing speaker-studio shortcut is not managed by this app')
    wrapper = data/APP_ID/'launch'
    launch_script = '#!/bin/sh\nexec '+shlex.quote(str(image))+' "$@"\n'
    icon_data = Path(icon_path).read_bytes()
    # A pre-existing hicolor cache can hide newly installed icons from GNOME's
    # dock. This stable, per-user absolute path bypasses that stale cache.
    icon = icons/(APP_ID+'.png')
    entry = ('[Desktop Entry]\nType=Application\nName=Speaker studio\n'
             'Comment=Control your Ultimate Ears speakers\n'
             f'Exec=/bin/sh {quote_exec(wrapper)}\nIcon={icon}\n'
             'Categories=AudioVideo;Audio;Utility;\nTerminal=false\n'
             f'StartupWMClass={APP_ID}\nX-SpeakerStudio-Managed=true\n')
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(launch_script)
    wrapper.chmod(0o700)
    icons.mkdir(parents=True, exist_ok=True)
    apps.mkdir(parents=True, exist_ok=True)
    launcher = apps/(APP_ID+'.desktop')
    if not icon.exists() or icon.read_bytes()!=icon_data:
        icon.write_bytes(icon_data)
    if not launcher.exists() or launcher.read_text()!=entry:
        launcher.write_text(entry)
    return launcher
