"""Desktop entry point and offline packaging checks."""
import argparse
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from . import __version__
from .backend import Controller
from .ui import Window, asset_root


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
    app=QApplication(sys.argv[:1])
    app.setApplicationName('Speaker studio')
    app.setDesktopFileName('speaker-studio')
    app.setOrganizationName('RaphaCrafts')
    app.setStyle('Fusion')
    window=Window(Controller(),demo=args.demo or args.smoke_test)
    available=app.primaryScreen().availableGeometry()
    window.resize(min(1080,available.width()-40),min(810,available.height()-60))
    window.show()
    if args.smoke_test or args.screenshot:
        def check():
            if args.screenshot:window.grab().save(args.screenshot)
            if args.smoke_test:
                from PySide6.QtGui import QPixmap
                valid=not QPixmap(str(asset_root()/'speakers/megaboom-3-ultraviolet-purple.webp')).isNull()
                print('Speaker studio UI and bundled images: '+('OK' if valid else 'FAILED'),flush=True)
                window.close()
                app.exit(0 if valid else 1)
        QTimer.singleShot(600,check)
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
