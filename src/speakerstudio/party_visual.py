"""A local animation of discovery/joining; never drives Bluetooth commands."""
import math
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


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
