"""A local animation of discovery/joining; never drives Bluetooth commands."""
import math
import time
import json
from PySide6.QtCore import Qt, QTimer, QMimeData, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QDrag
from PySide6.QtWidgets import QWidget, QFrame, QApplication


SPEAKER_MIME='application/x-speaker-studio-party-member'


class SpeakerDragCard(QFrame):
    """Drag a known receiver; child buttons remain usable with keyboard/click."""
    draggingChanged=Signal(bool)
    def __init__(self, host, address, image, parent=None):
        super().__init__(parent)
        self.host,self.address,self.image=host,address,image
        self.origin=None
        self.setObjectName('panel')
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:self.origin=event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.origin is not None and event.buttons()&Qt.LeftButton and (event.position().toPoint()-self.origin).manhattanLength()>=QApplication.startDragDistance():
            self.origin=None
            mime=QMimeData()
            mime.setData(SPEAKER_MIME,json.dumps({'host':self.host,'receiver':self.address}).encode())
            drag=QDrag(self);drag.setMimeData(mime)
            if not self.image.isNull():drag.setPixmap(self.image.scaled(64,100,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            self.draggingChanged.emit(True)
            try:drag.exec(Qt.MoveAction)
            finally:self.draggingChanged.emit(False)
        else:super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        self.origin=None
        super().mouseReleaseEvent(event)


class PartyPlayArea(QFrame):
    joinRequested=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.host=None;self.receivers=set()
        self.setAcceptDrops(True)
        self.setAccessibleName('PartyUp play area. Drag a ready speaker here to join.')
        self.highlight(False)

    def set_targets(self,host,receivers):
        self.host=host;self.receivers=set(receivers)

    def receiver_from(self,mime):
        if not mime.hasFormat(SPEAKER_MIME):return None
        try:data=json.loads(bytes(mime.data(SPEAKER_MIME)))
        except (ValueError,UnicodeDecodeError):return None
        if not isinstance(data,dict) or data.get('host')!=self.host:return None
        receiver=data.get('receiver')
        return receiver if isinstance(receiver,str) and receiver in self.receivers else None

    def highlight(self,active):
        self.setStyleSheet('PartyPlayArea { border: 2px '+('solid #12b5d3; background: rgba(18,181,211,24);' if active else 'dashed #53636a;')+' border-radius: 20px; }')

    def dragEnterEvent(self,event):
        if self.receiver_from(event.mimeData()):
            event.setDropAction(Qt.MoveAction);event.accept();self.highlight(True)
        else:event.ignore()

    def dragMoveEvent(self,event):
        if self.receiver_from(event.mimeData()):event.setDropAction(Qt.MoveAction);event.accept()
        else:event.ignore()

    def dragLeaveEvent(self,event):
        self.highlight(False);event.accept()

    def dropEvent(self,event):
        receiver=self.receiver_from(event.mimeData());self.highlight(False)
        if receiver:
            event.setDropAction(Qt.MoveAction);event.accept();self.joinRequested.emit(receiver)
        else:event.ignore()


class PartyLink(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = 'idle'
        self.caption = ''
        self.images = (QPixmap(), QPixmap())
        self.started = time.monotonic()
        self.setFixedHeight(104)
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.tick)

    def set_state(self, mode, caption, images):
        changed = (mode, caption) != (self.mode, self.caption)
        self.mode, self.caption, self.images = mode, caption, images
        self.setAccessibleName(caption)
        if changed:
            self.started = time.monotonic()
            if self.isVisible() and mode in ('ready', 'joining'):
                self.timer.start()
        if mode not in ('ready', 'joining'):
            self.timer.stop()
        self.update()

    def tick(self):
        if self.mode == 'ready' and time.monotonic()-self.started > 2:
            self.timer.stop()
        self.update()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        if self.mode == 'joining' or self.mode == 'ready' and time.monotonic()-self.started < 2:
            self.timer.start()
        super().showEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        middle = self.width()/2
        left, right, y = middle-95, middle+95, 31
        color = QColor('#12b5d3') if self.mode != 'idle' else self.palette().color(self.foregroundRole())
        painter.setPen(QPen(color, 2, Qt.DashLine if self.mode in ('ready','joining') else Qt.SolidLine))
        painter.drawLine(int(left+20), y, int(right-20), y)
        if self.mode == 'joining':
            phase = (time.monotonic()-self.started) % 1.4 / 1.4
            painter.setBrush(color)
            painter.drawEllipse(int(left+24+phase*(right-left-48))-4, y-4, 8, 8)
        for x, image in zip((left,right),self.images):
            if not image.isNull():
                scaled=image.scaled(38,52,Qt.KeepAspectRatio,Qt.SmoothTransformation)
                painter.drawPixmap(int(x-scaled.width()/2),5,scaled)
            else:
                painter.drawRoundedRect(int(x)-9,9,18,44,5,5)
        if self.mode == 'ready' and self.timer.isActive():
            radius=24+4*math.sin((time.monotonic()-self.started)*math.pi)
            painter.drawEllipse(int(right-radius),int(y-radius),int(radius*2),int(radius*2))
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(0,68,self.width(),30,Qt.AlignCenter,self.caption)
