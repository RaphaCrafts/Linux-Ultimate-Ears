"""Firmware information and official mobile updater guidance; no flashing path."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget, QLayout, QFrame

OFFICIAL_APP_URL='https://www.ultimateears.com/en-us/discover/c/apps'


class FirmwareDialog(QDialog):
    def __init__(self,speaker,controller,parent=None,demo=False):
        super().__init__(parent)
        self.setObjectName('firmwareDialog')
        self.address=speaker['address'];self.controller=controller;self.demo=demo
        self.setWindowTitle('Speaker firmware')
        self.resize(580,680)
        self.setMinimumSize(500,420)
        outer=QVBoxLayout(self)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame)
        content=QWidget();layout=QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        scroll.setWidget(content);outer.addWidget(scroll)
        layout.setContentsMargins(24,24,24,24);layout.setSpacing(14)
        self.name=self.label('',layout);self.name.setObjectName('section')
        self.version=self.label('',layout)
        self.label('Update availability: check in the official UE | BOOM phone app.',layout)
        self.label('Speaker studio reads your installed version. Firmware installation is handled by the official UE app on Android or iPhone.',layout)
        instructions=self.label('To update your speaker:\n\n1. Finish listening and end PartyUp.\n2. Release Speaker studio’s app controls below.\n3. Connect your phone to this speaker and open UE | BOOM. Check its speaker settings for an offered update and follow the app’s power and connection instructions.\n4. Reconnect here afterward and read the installed version again.',layout)
        instructions.setMinimumHeight(190)
        self.label('No firmware update is guaranteed risk-free. Keep the speaker powered and do not interrupt an update. Updating is not a guaranteed fix for PartyUp stuttering.',layout)
        self.error=self.label('',layout);self.error.setStyleSheet('color: #f28b82;')
        row=QHBoxLayout()
        self.read=QPushButton('Read installed version')
        self.read.clicked.connect(lambda:self.controller.submit('firmware',self.address))
        self.release=QPushButton('Release app controls')
        self.release.clicked.connect(lambda:self.controller.submit('disconnect',self.address))
        row.addWidget(self.read);row.addWidget(self.release);layout.addLayout(row)
        self.label('Releasing controls leaves Bluetooth audio and any PartyUp group running.',layout)
        official=QPushButton('Open official UE app page')
        official.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(OFFICIAL_APP_URL)))
        layout.addWidget(official)
        close=QPushButton('Done');close.clicked.connect(self.close);layout.addWidget(close)
        self.update_speaker(speaker)

    @staticmethod
    def label(value,layout):
        label=QLabel(value);label.setWordWrap(True);label.setTextFormat(Qt.PlainText)
        layout.addWidget(label);return label

    def update_speaker(self,speaker):
        self.name.setText(speaker['name'])
        connected=speaker.get('connected',False)
        version=speaker.get('firmware')
        self.version.setText('Simulated firmware · demo' if self.demo else ('Installed version: ' if connected else 'Last read version: ')+version if version else 'Installed version: connect speaker controls to read it.')
        enabled=connected and not speaker.get('busy') and not self.demo
        self.read.setEnabled(bool(enabled));self.release.setEnabled(bool(enabled))
        if not speaker.get('busy'):
            self.error.setText(speaker.get('error',''))
        self.error.setVisible(bool(self.error.text()))
