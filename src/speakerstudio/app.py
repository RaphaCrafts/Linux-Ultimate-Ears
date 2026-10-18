"""Desktop entry point and offline packaging checks."""
import argparse
import os
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from . import __version__
from .backend import Controller
from .ui import Window, asset_root, app_icon


def main():
    parser=argparse.ArgumentParser(description='Speaker studio for Ultimate Ears on Linux')
    parser.add_argument('--version',action='version',version=__version__)
    parser.add_argument('--demo',action='store_true',help='Explore the app without controlling Bluetooth devices')
    parser.add_argument('--smoke-test',action='store_true',help='Check packaged UI and images without accessing Bluetooth')
    parser.add_argument('--screenshot',help=argparse.SUPPRESS)
    parser.add_argument('--check-speaker',metavar='ADDRESS',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.check_speaker:
        from PySide6.QtCore import QCoreApplication
        from .diagnostics import check_speaker
        application=QCoreApplication(sys.argv[:1])
        return check_speaker(args.check_speaker)
    desktop_error = ''
    if not (args.demo or args.smoke_test or args.screenshot):
        from .desktop import register_appimage
        try:
            launcher=register_appimage(asset_root()/'speaker-studio.png')
            if launcher:
                os.environ['BAMF_DESKTOP_FILE_HINT']=str(launcher)
                os.environ['GIO_LAUNCHED_DESKTOP_FILE']=str(launcher)
        except (OSError,ValueError) as error:desktop_error = str(error)
    app=QApplication(['speaker-studio'])
    app.setApplicationName('speaker-studio')
    app.setApplicationDisplayName('Speaker studio')
    app.setWindowIcon(app_icon())
    app.setDesktopFileName('speaker-studio')
    app.setOrganizationName('RaphaCrafts')
    app.setStyle('Fusion')
    window=Window(Controller(),demo=args.demo or args.smoke_test)
    if desktop_error:window.show_status('Could not add the app-menu shortcut: '+desktop_error)
    available=app.primaryScreen().availableGeometry()
    window.resize(min(1000,available.width()-40),min(760,available.height()-60))
    window.show()
    if args.smoke_test or args.screenshot:
        def check():
            if args.screenshot:window.grab().save(args.screenshot)
            if args.smoke_test:
                from PySide6.QtGui import QPixmap
                valid=all(not QPixmap(str(asset_root()/'speakers'/r['file'])).isNull() for r in window.catalogue)
                valid=valid and all(not QPixmap(str(p)).isNull() for p in (asset_root()/'speakers/generic').glob('*.svg'))
                valid=valid and not window.windowIcon().isNull()
                from dataclasses import asdict
                from .models import Speaker
                window.update_devices([asdict(Speaker('demo-packaging','','MEGABOOM 3',paired=True))])
                valid=valid and not window.photo.pixmap().isNull() and window.colour_select.count()>0
                print('Speaker studio UI and bundled images: '+('OK' if valid else 'FAILED'),flush=True)
                window.close()
                app.exit(0 if valid else 1)
        QTimer.singleShot(600,check)
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
