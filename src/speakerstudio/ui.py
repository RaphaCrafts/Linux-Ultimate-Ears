"""Native Speaker studio window. Bluetooth work always runs off the GUI thread."""
import json
import os
import shutil
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QSettings, QSize, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QListWidget, QListWidgetItem, QFrame, QSlider, QComboBox, QStackedWidget,
    QScrollArea, QMessageBox, QMenu, QApplication, QProgressBar, QSystemTrayIcon, QInputDialog)
from PySide6.QtCore import QProcess, QProcessEnvironment
from . import __version__
from .preferences import restore_appearance
from .party_visual import PartyLink, PartyPlayArea, SpeakerDragCard
from .firmware import FirmwareDialog
from .computer_mix_ui import ComputerMixDialog


def asset_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / 'assets'


def app_icon():
    # Publish several small sizes: a lone 512px icon can exceed X11's request
    # limit and leave the taskbar icon empty, especially with display scaling.
    source = QPixmap(str(asset_root()/'speaker-studio.png'))
    icon = QIcon()
    for size in (16,24,32,48,64,128,256):
        icon.addPixmap(source.scaled(size,size,Qt.KeepAspectRatio,Qt.SmoothTransformation))
    return icon


def text(value, kind=''):
    widget = QLabel(value)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    if kind:
        widget.setObjectName(kind)
    return widget


def button(label, callback, primary=False):
    widget = QPushButton(label)
    if primary:
        widget.setObjectName('primary')
    widget.clicked.connect(callback)
    return widget


def panel(layout=None):
    widget = QFrame()
    widget.setObjectName('panel')
    if layout:
        widget.setLayout(layout)
    return widget


class Curve(QWidget):
    def __init__(self):
        super().__init__()
        self.bands = [0]*5
        self.scale = 12
        self.setMinimumHeight(135)
        self.setAccessibleName('Five-band equalizer curve')

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        points = [(15+i*(w-30)/4, h/2-b*(h-30)/(self.scale*2)) for i,b in enumerate(self.bands)]
        p.setPen(QPen(QColor('#d7d9d3'), 1))
        for x,y in points:
            p.drawLine(int(x), 12, int(x), h-12)
        path = QPainterPath()
        path.moveTo(*points[0])
        for (x0,y0),(x,y) in zip(points,points[1:]):
            mid = (x0+x)/2
            path.cubicTo(mid,y0,mid,y,x,y)
        p.setPen(QPen(QColor('#12b5d3'), 2))
        p.drawPath(path)
        p.setBrush(QColor('#12b5d3'))
        for x,y in points:
            p.drawEllipse(int(x)-4,int(y)-4,8,8)


class Window(QMainWindow):
    def __init__(self, controller, demo=False):
        super().__init__()
        self.controller = controller
        self.demo = demo
        self.devices = {}
        self.last_devices_signature = None
        self.sidebar_signature = None
        self.selected = None
        self.page = 'speaker'
        self.group_host = None
        self.balance_request = None
        self.balance_request_seen = False
        self.balance_dirty = False
        self.party_grid_signature = None
        self.party_card_actions = []
        self.eq_dirty = False
        self.settings = QSettings('RaphaCrafts', 'SpeakerStudio')
        self.catalogue = json.loads((asset_root()/'speakers/manifest.json').read_text())['images']
        self.setWindowTitle('Speaker studio')
        self.setWindowIcon(app_icon())
        self.resize(1000, 760)
        self.setMinimumSize(800, 640)
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(0)
        header = QFrame()
        header.setObjectName('header')
        row = QHBoxLayout(header)
        row.setContentsMargins(24,16,24,16)
        row.addWidget(text('Speaker studio', 'brand'))
        row.addWidget(text('for Ultimate Ears', 'muted'))
        row.addStretch()
        self.mode_label = text('DEMO — no Bluetooth controls' if demo else 'Linux', 'muted')
        row.addWidget(self.mode_label)
        menu_button = QPushButton('☰')
        menu_button.setAccessibleName('Application menu')
        menu = QMenu(menu_button)
        menu.addAction('Bluetooth settings', self.bluetooth_settings)
        menu.addAction('How to use Speaker studio', lambda: QDesktopServices.openUrl(QUrl('https://github.com/RaphaCrafts/Linux-Ultimate-Ears#readme')))
        menu.addAction('About', self.about)
        menu.addAction('Quit', self.quit_app)
        menu.addSeparator()
        for name in ('System', 'Light', 'Dark'):
            menu.addAction(name+' appearance', lambda n=name:self.set_theme(n.lower()))
        menu_button.setMenu(menu)
        row.addWidget(menu_button)
        outer.addWidget(header)
        body = QHBoxLayout()
        body.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(190)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(13,23,13,20)
        side.addWidget(text('YOUR SPEAKERS','eyebrow'))
        self.list = QListWidget()
        self.list.setIconSize(QSize(28,54))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentItemChanged.connect(self.select)
        self.list.itemClicked.connect(lambda item:self.open_speaker(item.data(Qt.UserRole)))
        side.addWidget(self.list)
        side.addWidget(button('Search for speakers', self.scan, True))
        side.addWidget(button('Bluetooth settings', self.bluetooth_settings))
        side.addWidget(button('PartyUp', self.open_party))
        side.addWidget(text('Independent app by RaphaCrafts','muted'))
        body.addWidget(sidebar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(22,18,22,16)
        nav = QHBoxLayout()
        self.tabs = {}
        for key,label in [('speaker','Speaker'),('eq','Equalizer')]:
            tab = button(label, lambda checked=False,k=key:self.navigate(k))
            tab.setCheckable(True)
            self.tabs[key] = tab
            nav.addWidget(tab)
        nav.addStretch()
        self.refresh_button = button('Refresh', self.refresh)
        nav.addWidget(self.refresh_button)
        main.addLayout(nav)
        self.stack = QStackedWidget()
        self.empty = self.build_empty()
        self.speaker_page = self.build_speaker()
        self.party_page = self.build_party()
        self.eq_page = self.build_eq()
        for widget in [self.empty,self.speaker_page,self.party_page,self.eq_page]:
            self.stack.addWidget(widget)
        main.addWidget(self.stack)
        main.addStretch()
        self.notice = text('Turn on your speaker to get started.' if not demo else 'Demo mode. All readings and controls are simulated.','muted')
        main.addWidget(self.notice)
        scroll.setWidget(content)
        body.addWidget(scroll,1)
        outer.addLayout(body,1)
        self.setCentralWidget(container)
        self.setup_tray()
        controller.changed.connect(self.update_devices)
        controller.status.connect(self.show_status)
        controller.error.connect(self.show_error)
        self.computer_mix_state={'running':False,'outputs':[],'error':''}
        controller.computer_mix_changed.connect(self.update_computer_mix)
        self.set_theme(self.settings.value('theme','system'))
        self.navigate('speaker')
        self.poll = QTimer(self)
        self.poll.setInterval(60000)
        self.poll.timeout.connect(self.refresh_quietly)
        if demo:
            QTimer.singleShot(0,self.load_demo)
        else:
            controller.start()
            self.poll.start()

    def set_theme(self, mode):
        self.settings.setValue('theme',mode)
        dark = mode=='dark' or mode=='system' and QApplication.palette().window().color().lightness()<128
        bg,fg,surface,muted,line,soft = ('#1b1d20','#f3f1eb','#27292d','#b0b3aa','#3b3e40','#343433') if dark else ('#f4f3f0','#242622','#ffffff','#72756f','#e4e5df','#eeece8')
        self.setStyleSheet(f'''
QWidget {{font-family: sans-serif; font-size:14px; color:{fg};}}
QMainWindow, QScrollArea, QScrollArea>QWidget>QWidget {{background:{bg};}}
QDialog#firmwareDialog {{background:{bg};}}
QDialog#computerMixDialog {{background:{bg};}}
QLabel {{background:transparent;}} QLabel#brand {{font-size:19px;font-weight:600;}}
QLabel#title {{font-size:29px;font-weight:600;}} QLabel#section {{font-size:17px;font-weight:600;}}
QLabel#muted {{color:{muted};font-size:12px;}} QLabel#eyebrow {{color:{muted};font-size:11px;}}
QFrame#header {{border-bottom:1px solid {line};background:{bg};}}
QFrame#sidebar {{border-right:1px solid {line};background:{bg};}}
QFrame#panel {{background:{surface};border:1px solid {line};border-radius:16px;}}
QFrame#hero {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {soft},stop:1 {'#302932' if dark else '#f0e4ee'});border:1px solid {line};border-radius:18px;}}
QPushButton {{background:{surface};border:1px solid {line};border-radius:8px;padding:9px 12px;}}
QPushButton:hover {{border-color:#12b5d3;}} QPushButton:checked {{background:{soft};border-color:#12b5d3;}} QPushButton#primary {{background:#12b5d3;color:#102b31;border-color:#12b5d3;font-weight:600;}}
QPushButton:disabled {{color:{muted};background:{soft};border-color:{line};}}
QPushButton#playbackMode:checked, QPushButton#playbackMode:checked:disabled {{background:#12b5d3;color:#102b31;border-color:#12b5d3;font-weight:600;}}
QPushButton:focus {{border:2px solid #12b5d3;}}
QListWidget {{border:0;background:transparent;outline:none;}} QListWidget::item {{padding:8px 5px;margin-bottom:4px;border-radius:10px;}}
QListWidget::item:selected {{background:{surface};color:{fg};}}
QComboBox {{background:{surface};border:1px solid {line};border-radius:8px;padding:8px;min-height:20px;}}
QComboBox QAbstractItemView {{background:{surface};color:{fg};selection-background-color:#12b5d3;selection-color:#151515;}}
QProgressBar {{background:{line};border:0;border-radius:4px;}}
QSlider::groove:horizontal {{height:5px;background:{line};border-radius:2px;}}
QSlider::sub-page:horizontal {{background:#12b5d3;border-radius:2px;}}
QSlider::handle:horizontal {{background:#12b5d3;width:16px;height:16px;margin:-6px 0;border-radius:8px;}}
QSlider::groove:vertical {{width:5px;background:{line};}}
QSlider::handle:vertical {{background:#12b5d3;height:14px;margin:0 -5px;border-radius:7px;}}
QSlider:disabled {{opacity:.5;}}
QMenu {{background:{surface};border:1px solid {line};}} QMenu::item {{padding:9px 20px;}}
''')

    def build_empty(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addStretch()
        heading = text('Your sound, on Linux.','title')
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)
        copy = text('Turn on your speaker, pair it in your desktop’s Bluetooth settings,\nthen select it in the sidebar and connect.','muted')
        copy.setAlignment(Qt.AlignCenter)
        layout.addWidget(copy)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button('Search for speakers',self.scan,True))
        row.addWidget(button('Bluetooth settings',self.bluetooth_settings))
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        return widget

    def build_speaker(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0,20,0,0)
        heading = QHBoxLayout()
        names = QVBoxLayout()
        self.model_label = text('','eyebrow')
        self.name_label = text('','title')
        self.connection_label = text('','muted')
        for label in [self.model_label,self.name_label,self.connection_label]:names.addWidget(label)
        heading.addLayout(names,1)
        heading.addWidget(button('Firmware',self.show_firmware))
        self.rename_button = button('Rename',self.rename_speaker)
        heading.addWidget(self.rename_button)
        self.connect_button = button('Connect',self.connect,True)
        heading.addWidget(self.connect_button)
        layout.addLayout(heading)
        self.device_error = text('','muted')
        self.device_error.setVisible(False)
        layout.addWidget(self.device_error)
        columns = QHBoxLayout()
        hero = QFrame()
        hero.setObjectName('hero')
        hero.setMaximumWidth(320)
        image_layout = QVBoxLayout(hero)
        image_layout.setContentsMargins(15,15,15,15)
        image_layout.addWidget(text('ULTIMATE EARS','eyebrow'))
        self.photo = QLabel()
        self.photo.setTextFormat(Qt.PlainText)
        self.photo.setAlignment(Qt.AlignCenter)
        self.photo.setFixedHeight(240)
        image_layout.addWidget(self.photo)
        self.battery_label = text('Battery —','section')
        battery_row = QHBoxLayout()
        battery_row.addWidget(self.battery_label)
        battery_row.addStretch()
        self.battery_hint = text('Connect to check', 'muted')
        battery_row.addWidget(self.battery_hint)
        image_layout.addLayout(battery_row)
        self.battery_meter = QProgressBar()
        self.battery_meter.setRange(0,100)
        self.battery_meter.setTextVisible(False)
        self.battery_meter.setFixedHeight(8)
        self.battery_meter.setAccessibleName('Battery charge')
        image_layout.addWidget(self.battery_meter)
        image_layout.addSpacing(12)
        image_layout.addWidget(text('SPEAKER FINISH','eyebrow'))
        self.colour_select = QComboBox()
        self.colour_select.setAccessibleName('Speaker colour')
        self.colour_select.currentTextChanged.connect(self.choose_colour)
        image_layout.addWidget(self.colour_select)
        self.finish_hint = text('Connect to detect the finish, or choose it below.','muted')
        image_layout.addWidget(self.finish_hint)
        columns.addWidget(hero,1)
        controls = QVBoxLayout()
        vol = QVBoxLayout()
        vol.setContentsMargins(19,19,19,19)
        top = QHBoxLayout()
        top.addWidget(text('Volume','section'))
        top.addStretch()
        self.volume_label = text('—','section')
        top.addWidget(self.volume_label)
        vol.addLayout(top)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0,100)
        self.volume.setAccessibleName('Speaker volume')
        self.volume.valueChanged.connect(lambda value:self.volume_label.setText(f'{value}%'))
        self.volume.sliderReleased.connect(self.set_volume)
        self.volume.actionTriggered.connect(self.keyboard_volume)
        self.volume_debounce = QTimer(self)
        self.volume_debounce.setSingleShot(True)
        self.volume_debounce.setInterval(350)
        self.volume_debounce.timeout.connect(self.set_volume)
        vol.addWidget(self.volume)
        controls.addWidget(panel(vol))
        eq_layout = QVBoxLayout()
        eq_layout.setContentsMargins(19,19,19,19)
        eq_layout.addWidget(text('Equalizer','section'))
        self.preset = QComboBox()
        self.preset.setAccessibleName('Equalizer preset')
        self.preset.activated.connect(self.set_preset)
        eq_layout.addWidget(self.preset)
        self.mini_curve = Curve()
        self.mini_curve.setMinimumHeight(90)
        self.mini_curve.setMaximumHeight(110)
        eq_layout.addWidget(self.mini_curve)
        eq_layout.addWidget(button('Open equalizer',lambda:self.navigate('eq')))
        controls.addWidget(panel(eq_layout))
        self.identify_button = button('Hear battery level',lambda:self.command('identify'))
        self.power_button = button('Power off',self.power_off)
        actions = QHBoxLayout()
        actions.addWidget(self.identify_button,1)
        actions.addWidget(self.power_button)
        controls.addLayout(actions)
        controls.addWidget(text('Hear the charge spoken aloud by your speaker.','muted'))
        controls.addStretch()
        columns.addLayout(controls,2)
        layout.addLayout(columns)
        layout.addStretch()
        return widget

    def build_party(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0,20,0,0)
        party_heading = QHBoxLayout()
        party_heading.addWidget(text('PartyUp','title'),1)
        self.read_group_button=button('Read existing group',self.read_existing_group)
        party_heading.addWidget(self.read_group_button)
        party_heading.addWidget(button('Back to speaker',lambda:self.navigate('speaker')))
        layout.addLayout(party_heading)
        preference=QHBoxLayout()
        preference.addWidget(text('Default PartyUp mode','muted'))
        self.party_default=QComboBox()
        self.party_default.addItem('Native PartyUp','native')
        self.party_default.addItem('Computer mix · experimental','computer')
        self.party_default.setCurrentIndex(max(0,self.party_default.findData(self.settings.value('party/default','native'))))
        self.party_default.activated.connect(lambda index:self.settings.setValue('party/default',self.party_default.itemData(index)))
        preference.addWidget(self.party_default)
        layout.addLayout(preference)
        alternative=QHBoxLayout()
        self.computer_mix_hint=text('Alternative: send audio directly from Linux to two speakers.','muted')
        alternative.addWidget(self.computer_mix_hint,1)
        alternative.addWidget(button('Computer mix · experimental',self.show_computer_mix))
        layout.addLayout(alternative)
        self.native_party_controls=QWidget()
        layout.addWidget(self.native_party_controls)
        layout.addStretch()
        layout=QVBoxLayout(self.native_party_controls)
        layout.setContentsMargins(0,0,0,0)
        self.party_info = text('Connect a supported speaker to manage its group.','muted')
        layout.addWidget(self.party_info)
        self.party_error=text('','muted')
        self.party_error.setStyleSheet('color: #f28b82;')
        layout.addWidget(self.party_error)
        controls = QHBoxLayout()
        controls.addWidget(text('Host speaker','muted'))
        self.host_select = QComboBox()
        self.host_select.setAccessibleName('PartyUp host speaker')
        self.host_select.activated.connect(self.choose_host)
        controls.addWidget(self.host_select,1)
        self.ungroup_button = button('End group',lambda:self.party_action('ungroup'))
        controls.addWidget(self.ungroup_button)
        layout.addLayout(controls)
        group_vol = QHBoxLayout()
        group_vol.addWidget(text('Group volume','section'))
        self.group_volume = QSlider(Qt.Horizontal)
        self.group_volume.setRange(0,100)
        self.group_volume.setAccessibleName('PartyUp group volume')
        self.group_volume.sliderReleased.connect(lambda:self.party_action('group_volume',self.group_volume.value()))
        self.group_debounce = QTimer(self)
        self.group_debounce.setSingleShot(True)
        self.group_debounce.setInterval(350)
        self.group_debounce.timeout.connect(lambda:self.party_action('group_volume',self.group_volume.value()))
        self.group_volume.actionTriggered.connect(lambda action:self.group_debounce.start() if not self.group_volume.isSliderDown() else None)
        self.group_volume.valueChanged.connect(lambda v:self.group_volume_label.setText(f'{v}%'))
        self.group_volume_label = text('—','muted')
        group_vol.addWidget(self.group_volume,1)
        group_vol.addWidget(self.group_volume_label)
        layout.addLayout(group_vol)
        self.party_link=PartyLink()
        layout.addWidget(self.party_link)
        self.balance_panel=QWidget()
        self.party_mode_row=QWidget()
        mode_layout=QHBoxLayout(self.party_mode_row)
        mode_layout.setContentsMargins(0,0,0,0)
        mode_layout.addWidget(text('Playback mode','section'))
        self.party_mode_buttons={}
        for mode,label,hint in [(0,'Double Up','Both speakers play the full sound'),(0x50,'Stereo','Host plays left; member plays right')]:
            option=button(label,lambda checked=False,m=mode:self.choose_party_mode(m))
            option.setCheckable(True)
            option.setObjectName('playbackMode')
            option.setToolTip(hint)
            option.setAccessibleName(label+' playback mode')
            self.party_mode_buttons[mode]=option
            mode_layout.addWidget(option)
        mode_layout.addStretch()
        layout.addWidget(self.party_mode_row)
        balance_layout=QVBoxLayout(self.balance_panel)
        balance_layout.setContentsMargins(0,0,0,0)
        balance_layout.addWidget(text('Speaker balance','section'))
        labels=QHBoxLayout()
        self.balance_left=text('Host','muted')
        self.balance_readout=text('Equal emphasis','muted')
        self.balance_readout.setAlignment(Qt.AlignCenter)
        self.balance_right=text('Other speaker','muted')
        self.balance_right.setAlignment(Qt.AlignRight)
        labels.addWidget(self.balance_left,1)
        labels.addWidget(self.balance_readout,1)
        labels.addWidget(self.balance_right,1)
        balance_layout.addLayout(labels)
        balance_row=QHBoxLayout()
        self.balance_slider=QSlider(Qt.Horizontal)
        self.balance_slider.setRange(0,255)
        self.balance_slider.setValue(128)
        self.balance_slider.setAccessibleName('Balance between the two PartyUp speakers')
        self.balance_slider.valueChanged.connect(self.describe_balance)
        self.balance_timer=QTimer(self)
        self.balance_timer.setSingleShot(True)
        self.balance_timer.setInterval(450)
        self.balance_timer.timeout.connect(self.send_balance)
        self.balance_slider.sliderPressed.connect(self.balance_timer.stop)
        self.balance_slider.sliderReleased.connect(self.schedule_balance)
        self.balance_slider.actionTriggered.connect(lambda action:self.schedule_balance() if not self.balance_slider.isSliderDown() else None)
        balance_row.addWidget(self.balance_slider,1)
        self.balance_centre=button('Centre',lambda:self.centre_balance())
        balance_row.addWidget(self.balance_centre)
        balance_layout.addLayout(balance_row)
        layout.addWidget(self.balance_panel)
        levels_row=QHBoxLayout()
        self.levels_hint=text('Individual speaker volumes','muted')
        self.levels_refresh=button('Refresh speaker levels',lambda:self.party_action('group_levels'))
        levels_row.addWidget(self.levels_hint,1)
        levels_row.addWidget(self.levels_refresh)
        layout.addLayout(levels_row)
        self.member_sliders={}
        self.member_timers={}
        self.mix_signature=None
        self.party_dragging=False
        self.play_area=PartyPlayArea()
        self.play_area.joinRequested.connect(self.join_speaker)
        play_layout=QVBoxLayout(self.play_area)
        play_layout.setContentsMargins(18,16,18,16)
        play_layout.addWidget(text('Playing together','section'))
        self.play_hint=text('Drag a ready speaker into this area, or use its Add to group button.','muted')
        play_layout.addWidget(self.play_hint)
        self.party_grid = QGridLayout()
        for column in range(3):self.party_grid.setColumnStretch(column,1)
        play_layout.addLayout(self.party_grid)
        layout.addWidget(self.play_area)
        layout.addWidget(text('Available speakers','section'))
        layout.addWidget(text('Drag a speaker above to join the music.','muted'))
        self.available_grid=QGridLayout()
        for column in range(3):self.available_grid.setColumnStretch(column,1)
        layout.addLayout(self.available_grid)
        self.group_status = text('','muted')
        layout.addWidget(self.group_status)
        layout.addStretch()
        return widget

    def build_eq(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0,20,0,0)
        layout.addWidget(text('Make it sound like you.','title'))
        self.eq_copy = text('','muted')
        layout.addWidget(self.eq_copy)
        inner = QVBoxLayout()
        inner.setContentsMargins(24,24,24,24)
        self.eq_preset = QComboBox()
        self.eq_preset.setAccessibleName('Sound profile')
        self.eq_preset.activated.connect(self.set_eq_preset)
        inner.addWidget(self.eq_preset)
        self.curve = Curve()
        self.curve.setMinimumHeight(210)
        inner.addWidget(self.curve)
        bands = QHBoxLayout()
        self.band_sliders = []
        self.band_outputs = []
        for i,name in enumerate(['Bass','Mid-bass','Mid','Mid-high','Treble']):
            col = QVBoxLayout()
            out = text('0','muted')
            out.setAlignment(Qt.AlignCenter)
            slider = QSlider(Qt.Vertical)
            slider.setRange(-128,127)
            slider.setAccessibleName(name+' gain')
            slider.setMinimumHeight(100)
            slider.valueChanged.connect(lambda value,label=out:self.band_changed(label,value))
            col.addWidget(out)
            col.addWidget(slider,alignment=Qt.AlignHCenter)
            label = text(name,'muted')
            label.setAlignment(Qt.AlignCenter)
            col.addWidget(label)
            bands.addLayout(col)
            self.band_sliders.append(slider)
            self.band_outputs.append(out)
        inner.addLayout(bands)
        self.apply_eq = button('Apply custom EQ',self.apply_custom,True)
        inner.addWidget(self.apply_eq)
        self.reset_eq=button('Reset to Out loud',lambda:self.send_eq(0))
        inner.addWidget(self.reset_eq)
        self.custom_note = text('','muted')
        inner.addWidget(self.custom_note)
        layout.addWidget(panel(inner))
        layout.addStretch()
        return widget

    def band_changed(self, label, value):
        label.setText(f'{round(value*100/(128 if value < 0 else 127)):+d}%')
        self.eq_dirty = True
        self.curve.scale = 128
        self.curve.bands = [s.value() for s in self.band_sliders]
        self.curve.update()

    def select(self, current, previous):
        if current:self.open_speaker(current.data(Qt.UserRole))

    def open_party(self):
        self.navigate('party')
        if self.settings.value('party/default','native')=='computer':self.show_computer_mix()

    def navigate(self, page):
        if page!='party':
            self.group_debounce.stop()
            self.cancel_balance()
            for timer in self.member_timers.values():timer.stop()
        self.page = page
        for key,tab in self.tabs.items():tab.setChecked(key==page)
        self.render()

    def update_devices(self, devices):
        if devices and self.demo != all(d['address'].startswith('demo-') for d in devices):
            return
        devices = [restore_appearance(d,self.settings) for d in devices]
        updated={d['address']:d for d in devices}
        signature=json.dumps(updated,sort_keys=True)
        if signature==self.last_devices_signature:return
        self.last_devices_signature=signature
        self.devices = updated
        firmware_dialog=getattr(self,'firmware_dialog',None)
        if firmware_dialog:
            speaker=updated.get(firmware_dialog.address)
            if speaker:firmware_dialog.update_speaker(speaker)
            else:firmware_dialog.update_speaker({'name':'Speaker unavailable','connected':False})
        if self.balance_request:
            host=self.devices.get(self.balance_request[0],{})
            if not host.get('connected') or host.get('audio_mode')!=0x50 or len(host.get('members',[]))!=1:
                self.cancel_balance()
            elif host.get('busy') and host.get('operation')=='balance':
                self.balance_request_seen=True
            elif self.balance_request_seen and not host.get('busy'):
                self.balance_request=None
                self.balance_request_seen=False
                if self.balance_dirty:self.balance_timer.start()
        selected = self.selected
        rows=[]
        grouped={a for host in devices if host.get('broadcast',0)&2 for a in host.get('members',[])}
        for d in devices:
            state = 'Waking…' if d['busy'] and d.get('operation')=='wake' else 'Connecting controls…' if d['busy'] and d.get('operation')=='connect' else 'Controls ready' if d['connected'] else 'Audio linked' if d.get('audio_connected') else 'Bluetooth linked' if d.get('bluez_connected') else 'Sleeping · wake available' if d.get('sleeping') and d.get('wake_available') else 'Saved · disconnected' if d['paired'] else 'Not paired'
            if d['address'] in grouped:state='In PartyUp'
            rows.append((d,state,self.image_path(d)))
        sidebar_signature=tuple((d['address'],d['name'],state,str(image)) for d,state,image in rows)
        if sidebar_signature!=self.sidebar_signature:
            self.sidebar_signature=sidebar_signature
            self.list.blockSignals(True)
            self.list.clear()
            for d,state,image in rows:
                item = QListWidgetItem(f"{d['name']}\n{state}")
                item.setToolTip(d['name']+' · '+state)
                item.setData(Qt.UserRole,d['address'])
                if image:item.setIcon(QIcon(str(image)))
                item.setSizeHint(QSize(150,64))
                self.list.addItem(item)
                if d['address']==selected:self.list.setCurrentItem(item)
            if selected not in self.devices:
                self.selected = devices[0]['address'] if devices else None
                if devices:self.list.setCurrentRow(0)
            self.list.blockSignals(False)
        self.render()

    def inferred_model(self, d):
        if d.get('model'):return d['model']
        name = ''.join(c for c in d['name'].upper() if c.isalnum())
        for model in ['megaboom-4','megaboom-3','boom-4','boom-3','epicboom','everboom','hyperboom','wonderboom-4','wonderboom-3','wonderboom-2','wonderboom','megaboom','boom-2','boom']:
            if model.replace('-','').upper() in name:return model
        return ''

    def generic_path(self, model):
        family = next((f for f in ('megaboom','hyperboom','everboom','epicboom','wonderboom','boom') if model.startswith(f)), 'speaker')
        return asset_root()/'speakers/generic'/(family+'.svg')

    def artwork_variants(self, d):
        model = self.inferred_model(d)
        label = 'Generic '+(model.upper().replace('-',' ') if model else 'speaker')
        generic = {'model':model, 'colour':label, 'path':self.generic_path(model)}
        records = [r for r in self.catalogue if r['model']==model]
        detected = next((r for r in records if r['colour']==d.get('colour')),generic)
        automatic = dict(detected, colour='Automatic · '+(d.get('colour') or 'Generic'))
        return [automatic, generic] + records

    @staticmethod
    def default_artwork(variants):
        return variants[0]

    def image_path(self,d):
        variants = self.artwork_variants(d)
        colour = self.settings.value('colour/'+d['address'],'')
        record = next((r for r in variants if r['colour']==colour),self.default_artwork(variants))
        path = record.get('path') or asset_root()/'speakers'/record['file']
        # Missing or unreadable packshots always fall back to the neutral family art.
        return path if not QPixmap(str(path)).isNull() else self.generic_path(self.inferred_model(d))

    def render(self):
        d = self.devices.get(self.selected)
        self.refresh_button.setEnabled(True)
        if self.page=='party':
            self.stack.setCurrentWidget(self.party_page)
            self.render_party()
            return
        if not d:
            self.stack.setCurrentWidget(self.empty)
            return
        active = d['connected'] and not d['busy']
        self.stack.setCurrentWidget(self.eq_page if self.page=='eq' else self.speaker_page)
        self.model_label.setText(d.get('model','').upper().replace('-',' ') or 'ULTIMATE EARS')
        self.name_label.setText(d['name'])
        pending = d['busy'] and d.get('operation') in ('connect','wake')
        if pending:
            status = 'Waking and connecting…' if d['operation']=='wake' else 'Connecting speaker controls…'
        elif d['connected']:
            status = 'Controls connected' + (' · Bluetooth audio connected' if d.get('audio_connected') else ' · audio not linked')
        elif d.get('audio_connected'):
            status = 'Bluetooth audio connected · connect controls to adjust the speaker'
        elif d.get('bluez_connected'):
            status = 'Bluetooth linked · speaker controls not connected'
        elif d.get('sleeping') and d.get('wake_available'):
            status = 'Sleeping nearby · ready to wake and connect'
        else:
            status = 'Not connected · pairing saved in Linux' if d['paired'] else 'Pair in Bluetooth settings first'
        if d.get('firmware') and d['connected']:status+=' · Firmware '+d['firmware']
        self.connection_label.setText(status)
        self.device_error.setText(d.get('error',''))
        self.device_error.setVisible(bool(d.get('error')) and not d['busy'])
        self.rename_button.setEnabled(active and not pending and (self.demo or d['features'].get('rename',False)))
        self.rename_button.setToolTip('Change the name stored on the speaker' if active else 'Connect speaker controls to rename it')
        self.connect_button.setText('Cancel' if pending else 'Disconnect controls' if d['connected'] else 'Wake & connect' if d.get('sleeping') and d.get('wake_available') else 'Connect controls')
        self.connect_button.setEnabled(pending or not d['busy'] and d['paired'])
        charge = d['battery']
        self.battery_label.setText(f'Battery {charge}%' if charge is not None else 'Battery')
        self.battery_hint.setText('Low charge' if charge is not None and charge<=20 else 'Charge remaining' if charge is not None else 'Connect to check')
        self.battery_meter.setValue(charge if charge is not None else 0)
        self.battery_meter.setEnabled(charge is not None)
        self.battery_meter.setStyleSheet('QProgressBar::chunk {background:'+('#efab59' if charge is not None and charge<=20 else '#12b5d3')+';border-radius:4px;}')
        if not self.volume.isSliderDown() and not self.volume_debounce.isActive():
            self.volume.blockSignals(True)
            self.volume.setValue(d['volume'] or 0)
            self.volume.blockSignals(False)
            self.volume_label.setText(f"{d['volume']}%" if d['volume'] is not None else '—')
        self.volume.setEnabled(active and d['volume'] is not None)
        self.identify_button.setEnabled(active)
        self.power_button.setText('Power off' if d['connected'] else 'Turn on')
        self.power_button.setEnabled(active and d['features'].get('power',False) or not d['connected'] and not d['busy'] and d.get('wake_available',False) and d.get('sleeping') is True)
        self.power_button.setToolTip('Wake over Bluetooth Low Energy' if not d['connected'] and d.get('wake_available') else 'Search for nearby sleeping speakers first' if not d['connected'] else 'Turn off this speaker')
        variants = self.artwork_variants(d)
        self.colour_select.blockSignals(True)
        self.colour_select.clear()
        self.colour_select.addItems([r['colour'] for r in variants])
        saved = self.settings.value('colour/'+d['address'],'')
        record = next((r for r in variants if r['colour']==saved),self.default_artwork(variants))
        if record:self.colour_select.setCurrentText(record['colour'])
        self.colour_select.setVisible(bool(variants))
        self.colour_select.blockSignals(False)
        self.finish_hint.setText(('Remembered: ' if d.get('remembered_colour') else 'Detected: ')+d['colour']+'. You can choose a different finish.' if d.get('colour') else 'Finish not recognized. Choose a finish or use Generic.' if d.get('colour_code') is not None else 'Connect to detect the finish, or choose it below.')
        image = self.image_path(d)
        if image:
            self.photo.setPixmap(QPixmap(str(image)).scaled(220,240,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        else:
            self.photo.clear()
            self.photo.setText('Ultimate Ears\n'+d['name'])
        self.eq_copy.setText('Sound for '+d['name']+' · Preset curves are illustrative; Custom shows stored levels.')
        self.preset.blockSignals(True)
        self.eq_preset.blockSignals(True)
        for select in [self.preset,self.eq_preset]:
            select.clear()
            for name,code in self.preset_options():select.addItem(name,code)
            index = select.findData(d['eq'])
            if index<0:select.insertItem(0,'Custom (speaker setting)' if d['eq']==4 else 'Current speaker setting',d['eq']);index=0
            select.setCurrentIndex(index)
            select.setEnabled(active and d['features'].get('eq_write',False))
        self.preset.blockSignals(False)
        self.eq_preset.blockSignals(False)
        custom = active and d['features'].get('custom_eq',False)
        self.reset_eq.setEnabled(active and d['features'].get('eq_write',False))
        self.apply_eq.setEnabled(custom)
        for slider in self.band_sliders:slider.setEnabled(custom)
        self.custom_note.setText('Relative levels: less (−) or more (+). Apply when ready.' if custom else 'Custom bands are not available for this speaker in this release.')
        self.render_curves(d)

    @staticmethod
    def preset_options():
        return [('Out loud',0),('Vocal',1),('Intimate',2),('Bass boost',3),('Custom',4)]

    def render_curves(self,d):
        shapes = {0:[0,0,0,0,0],3:[3,4,0,-4,-4],2:[0,-2,-4,0,0],1:[-4,0,1,2,1]}
        self.mini_curve.setVisible(self.demo or d['eq'] in shapes or d.get('bands') is not None)
        self.curve.setVisible(self.demo or d['eq'] in shapes or d.get('bands') is not None)
        self.mini_curve.setToolTip('Illustrative preset curve; not a measurement from the speaker')
        self.curve.setToolTip('Illustrative preset curve; not a measurement from the speaker')
        actual = d.get('bands') if d['eq']==4 else None
        self.mini_curve.scale = 128 if actual is not None else 12
        self.curve.scale = self.mini_curve.scale
        self.mini_curve.bands = actual if actual is not None else shapes.get(d['eq'],[0]*5)
        self.mini_curve.update()
        if not self.eq_dirty and not any(s.isSliderDown() for s in self.band_sliders):
            self.curve.bands = self.mini_curve.bands
            if d.get('bands') is not None:
                for slider,output,value in zip(self.band_sliders,self.band_outputs,d['bands']):
                    if not slider.hasFocus():
                        slider.blockSignals(True)
                        slider.setValue(value)
                        slider.blockSignals(False)
                        output.setText(f'{round(value*100/(128 if value<0 else 127)):+d}%')
                self.curve.scale = 128
            self.curve.update()

    def choose_host(self,index):
        self.group_debounce.stop()
        self.cancel_balance()
        self.group_host=self.host_select.itemData(index)
        self.render_party()

    def read_existing_group(self):
        candidates=[d for d in self.devices.values() if d.get('audio_connected') and d.get('paired') and not d.get('busy')]
        candidates.sort(key=lambda d:not d.get('audio_active'))
        if not candidates:return
        host=candidates[0]
        self.group_host=host['address']
        if self.demo:self.render_party();return
        self.controller.submit('refresh' if host['connected'] else 'connect',host['address'])

    def party_action(self,action,*args):
        if getattr(self,'computer_mix_state',{}).get('running'):
            self.show_status('Stop Computer mix before using native PartyUp controls.')
            return
        if not self.group_host:return
        if self.demo:
            host=self.devices[self.group_host]
            if action=='group_add' and args[0] not in host['members']:
                host['members'].append(args[0]);host['broadcast']=3
            elif action=='group_remove':host['members']=[m for m in host['members'] if m!=args[0]]
            elif action=='ungroup':host['members']=[];host['broadcast']=0
            elif action=='group_volume':host['volume']=args[0]
            elif action=='balance':host['balance']=args[0]-128
            elif action=='party_mode':host['audio_mode']=args[0]
            elif action=='member_volume':
                if args[0]==self.group_host:host['volume']=args[1]
                else:host.setdefault('member_info',{}).setdefault(args[0],{})['volume']=args[1]
            elif action=='group_levels':
                for address in host['members']:
                    host.setdefault('member_info',{}).setdefault(address,{})['volume']=self.devices.get(address,{}).get('volume',0)
            self.render_party()
            self.show_status('Demo group updated. No Bluetooth commands sent.')
        else:
            self.controller.submit(action,self.group_host,*args)

    def join_speaker(self,address):
        host=self.devices.get(self.group_host,{})
        target=self.devices.get(address,{})
        if not host or host.get('busy') or target.get('busy'):return
        if address==self.group_host or address in host.get('members',[]):return
        if not target.get('connected') or not target.get('features',{}).get('group') or target.get('broadcast',0)&2:return
        self.show_status('Joining '+target['name']+'…')
        self.party_action('group_add',address)

    def party_drag_changed(self,dragging):
        self.party_dragging=dragging
        if not dragging:QTimer.singleShot(0,self.render_party)

    def describe_balance(self,value):
        amount=round(abs(value-128)*100/(128 if value<128 else 127))
        self.balance_readout.setText('Equal emphasis' if not amount else f'{amount}% toward '+(self.balance_left.text() if value<128 else self.balance_right.text()))

    def send_balance(self):
        self.balance_timer.stop()
        host=self.devices.get(self.group_host,{})
        if not host.get('connected') or host.get('audio_mode')!=0x50 or len(host.get('members',[]))!=1:
            self.cancel_balance()
            return
        if host.get('busy') or self.balance_request:
            self.balance_dirty=True
            self.balance_timer.start()
            return
        self.balance_dirty=False
        if not self.demo:
            self.balance_request=(self.group_host,self.balance_slider.value())
            self.balance_request_seen=False
        self.party_action('balance',self.balance_slider.value())

    def schedule_balance(self):
        self.balance_dirty=True
        self.balance_timer.start()

    def cancel_balance(self):
        self.balance_timer.stop()
        self.balance_dirty=False
        self.balance_request=None
        self.balance_request_seen=False

    def choose_party_mode(self,mode):
        self.cancel_balance()
        self.party_action('party_mode',mode)

    def centre_balance(self):
        self.balance_slider.setValue(128)
        self.schedule_balance()

    def render_party(self):
        computer_mix_active=getattr(self,'computer_mix_state',{}).get('running',False)
        self.native_party_controls.setVisible(not computer_mix_active)
        if computer_mix_active:
            self.cancel_balance();self.group_debounce.stop()
            self.party_link.timer.stop()
            return
        self.read_group_button.setEnabled(any(d.get('audio_connected') and d.get('paired') and not d.get('busy') for d in self.devices.values()))
        current=self.devices.get(self.group_host)
        signature=(self.group_host,tuple(current.get('members',[]))) if current else None
        if current and current['connected'] and signature==self.mix_signature:
            if any(s.isSliderDown() for s in self.member_sliders.values()) or any(t.isActive() for t in self.member_timers.values()):return
        receivers={a for d in self.devices.values() if d.get('broadcast',0)&2 for a in d.get('members',[])}
        connected=[d for d in self.devices.values() if d['connected'] and d['features'].get('group') and d['address'] not in receivers]
        connected.sort(key=lambda d:(not bool(d.get('broadcast',0)&2),not d.get('audio_active',False),not d.get('audio_connected',False)))
        self.host_select.blockSignals(True)
        self.host_select.clear()
        for d in connected:self.host_select.addItem(d['name'],d['address'])
        if self.group_host not in [d['address'] for d in connected] or connected and connected[0].get('broadcast',0)&2 and not self.devices[self.group_host].get('broadcast',0)&2:
            self.group_host=connected[0]['address'] if connected else None
        if self.group_host:self.host_select.setCurrentIndex(self.host_select.findData(self.group_host))
        self.host_select.blockSignals(False)
        host=self.devices.get(self.group_host)
        error=host.get('error','') if host else ''
        self.party_error.setText(error);self.party_error.setVisible(bool(error))
        allowed=[d['address'] for d in self.devices.values() if host and d['address']!=host['address'] and d['address'] not in host.get('members',[]) and d['connected'] and d['features'].get('group') and not d['busy'] and not host['busy'] and not (d.get('broadcast',0)&2)]
        self.play_area.set_targets(self.group_host,allowed)
        if self.party_dragging:return
        multiple=bool(host and host.get('broadcast',0)&2 and len(host.get('members',[]))>=2)
        self.levels_hint.setVisible(multiple)
        self.levels_refresh.setVisible(multiple)
        self.levels_refresh.setEnabled(bool(host and not host['busy']))
        self.levels_hint.setText('Individual volumes · changing group volume synchronizes all speakers')
        paired_view=bool(host and host.get('broadcast',0)&2 and len(host.get('members',[]))==1)
        self.balance_panel.setVisible(paired_view)
        self.party_mode_row.setVisible(paired_view)
        mode=host.get('audio_mode') if host else None
        for value,option in self.party_mode_buttons.items():
            option.setChecked(mode==value)
            option.setEnabled(bool(paired_view and not host['busy'] and mode!=value))
        usable=bool(paired_view and host['features'].get('balance') and mode==0x50 and (not host['busy'] or host.get('operation')=='balance'))
        self.balance_slider.setEnabled(usable)
        self.balance_centre.setEnabled(usable)
        if paired_view:
            member=self.devices.get(host['members'][0],{})
            self.balance_left.setText(host['name'])
            self.balance_right.setText(member.get('name','Group member'))
            if not self.balance_slider.isSliderDown() and not self.balance_dirty and not self.balance_request:
                self.balance_slider.setValue((host.get('balance') or 0)+128)
            if not host['features'].get('balance'):self.balance_readout.setText('Balance unavailable')
            elif mode!=0x50:self.balance_readout.setText('Select Stereo above to use balance')
            else:self.describe_balance(self.balance_slider.value())
        self.ungroup_button.setEnabled(bool(host and host.get('broadcast',0)&2 and not host['busy']))
        self.group_volume.setEnabled(bool(host and host.get('broadcast',0)&2 and not host['busy']))
        if host and not self.group_volume.isSliderDown():
            self.group_volume.setValue(host['volume'] or 0)
        self.host_select.setEnabled(bool(connected))
        if not host:
            self.cancel_balance()
            self.party_link.set_state('idle','Connect a speaker to start PartyUp',(QPixmap(),QPixmap()))
            self.party_link.hide()
            self.group_debounce.stop()
            self.group_volume.blockSignals(True)
            self.group_volume.setValue(0)
            self.group_volume.blockSignals(False)
            self.group_volume_label.setText('—')
            self.party_info.setText('Connect a speaker below to start PartyUp.')
            self.group_status.setText('Bluetooth disconnection does not necessarily end the group on the speakers.')
            self.clear_party_cards()
            for i,d in enumerate(self.devices.values()):
                box=QVBoxLayout()
                box.addWidget(text(d['name'],'section'))
                box.addWidget(self.party_connect_button(d))
                self.available_grid.addWidget(panel(box),i//3,i%3)
            self.play_hint.setText('Use Read existing group to reconnect to the speaker playing from Linux.')
            return
        members=host.get('members',[])
        active=bool(host.get('broadcast',0)&2)
        awaiting_members=active and not members and not host.get('group_status_known',False)
        self.group_status.setText('Demo group. No real devices are changed.' if self.demo else 'PartyUp continues when you quit the app. Use End group to stop it.' if active else 'Choose another connected speaker above to play together.')
        self.party_info.setText(f"Host: {host['name']} · PartyUp active · waiting for member details" if awaiting_members else f"Host: {host['name']} · {len(members)} group members" if active else 'Choose a host, then add another connected speaker.')
        displayed=[host['address']]+members
        available=[d for d in self.devices.values() if d['address'] not in displayed]
        target=self.devices.get(host.get('group_target'))
        joining=bool(target and host['busy'] and host.get('operation')=='group_add')
        self.play_hint.setText('Waiting for '+target['name']+' to confirm joining…' if joining else 'PartyUp is running. Drag another ready speaker here to join.' if active else 'Your host is ready. Drag a speaker here to start playing together.')
        other=target if joining else self.devices.get(members[0]) if members else next((d for d in available if d['address'] in allowed),None)
        images=tuple(QPixmap(str(self.image_path(d))) if d else QPixmap() for d in (host,other))
        mode='joining' if joining else 'linked' if members else 'ready' if other else 'idle'
        caption=f"Joining {other['name']}…" if joining else f'{len(displayed)} speakers playing together' if members else f"{other['name']} is ready to join" if other else 'Connect another speaker to play together'
        if awaiting_members and not joining:caption='PartyUp is active on the speaker; member details have not arrived yet'
        self.party_link.set_state(mode,caption,images)
        self.party_link.setVisible(mode in ('ready','joining'))
        for action,address in self.party_card_actions:
            action_target=self.devices.get(address,{})
            action.setEnabled(not host['busy'] and not action_target.get('busy',False) and (address in members or address in allowed))
        card_busy=host['busy'] and host.get('operation')!='balance'
        grid_signature=(host['address'],tuple(members),card_busy,host.get('group_target') if joining else None,
            tuple((d['address'],d['name'],d['connected'],d['battery'],d['volume'],d.get('broadcast',0),d['busy'] if d['address']!=host['address'] else card_busy,str(self.image_path(d))) for d in self.devices.values()),
            json.dumps(host.get('member_info',{}),sort_keys=True))
        if grid_signature==self.party_grid_signature:return
        self.clear_party_cards()
        self.party_grid_signature=grid_signature
        self.mix_signature=signature
        if joining and target['address'] not in displayed:displayed.append(target['address'])
        for i,address in enumerate(displayed):
            d=self.devices.get(address)
            metadata=host.get('member_info',{}).get(address,{})
            box=QVBoxLayout();box.setContentsMargins(16,16,16,16)
            pending=joining and address==target['address'] and address not in members
            box.addWidget(text('Host' if i==0 else 'Joining…' if pending else 'Group member','eyebrow'))
            box.addWidget(text(d['name'] if d else 'Speaker in group','section'))
            photo=QLabel();photo.setAlignment(Qt.AlignCenter)
            photo.setFixedHeight(105)
            image=self.image_path(d) if d else self.generic_path('')
            if image:photo.setPixmap(QPixmap(str(image)).scaled(80,105,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            if multiple:
                level_row=QHBoxLayout()
                level_row.addWidget(photo,1)
                slider=QSlider(Qt.Vertical)
                slider.setRange(0,100)
                slider.setFixedHeight(120)
                slider.setAccessibleName('Volume for '+(d['name'] if d else 'group member'))
                level=d.get('volume') if i==0 or d and d['connected'] else metadata.get('volume')
                slider.setValue(level if level is not None else 0)
                slider.setEnabled(level is not None and not host['busy'])
                self.member_sliders[address]=slider
                level_row.addWidget(slider)
                box.addLayout(level_row)
                output=text(f'Volume {level}%' if level is not None else 'Refresh levels to adjust','muted')
                slider.valueChanged.connect(lambda v,label=output:label.setText(f'Volume {v}%'))
                box.addWidget(output)
                if metadata.get('level_error'):output.setText('Individual level unavailable')
                timer=QTimer(slider)
                timer.setSingleShot(True);timer.setInterval(350)
                self.member_timers[address]=timer
                timer.timeout.connect(lambda a=address,s=slider,h=self.group_host:self.send_member_level(h,a,s.value()))
                slider.sliderReleased.connect(lambda a=address,s=slider,t=timer,h=self.group_host:(t.stop(),self.send_member_level(h,a,s.value())))
                slider.actionTriggered.connect(lambda action,s=slider,t=timer:t.start() if not s.isSliderDown() else None)
            else:box.addWidget(photo)
            battery=metadata.get('battery',d.get('battery') if d else None)
            if battery is None and d:battery=d.get('battery')
            box.addWidget(text(f'Battery {battery}%' if battery is not None else 'Battery —','muted'))
            if i==0:
                box.addWidget(button('Open speaker',lambda checked=False,a=address:self.open_speaker(a)))
            elif not pending:
                remove=button('Remove from group',lambda checked=False,a=address:self.party_action('group_remove',a))
                remove.setEnabled(not host['busy']);box.addWidget(remove)
                self.party_card_actions.append((remove,address))
            card=panel(box);card.setMinimumHeight(300 if multiple else 250)
            self.party_grid.addWidget(card,i//3,i%3)
        available=[d for d in available if d['address'] not in displayed]
        if not available:self.available_grid.addWidget(text('No other speakers found. Use Search for speakers to look for more.','muted'),0,0,1,3)
        for i,d in enumerate(available):
            box=QVBoxLayout();box.setContentsMargins(13,13,13,13)
            box.addWidget(text(d['name'],'section'))
            image=self.image_path(d)
            if image:
                thumb=QLabel()
                thumb.setPixmap(QPixmap(str(image)).scaled(38,62,Qt.KeepAspectRatio,Qt.SmoothTransformation))
                thumb.setAlignment(Qt.AlignCenter)
                box.addWidget(thumb)
            eligible=d['address'] in allowed
            if d['connected'] and d['features'].get('group'):
                box.addWidget(text('Drag to play area' if eligible else 'Speaker busy' if d['busy'] else 'End its group first' if d.get('broadcast',0)&2 else 'Waiting for host','muted'))
                action=button('Add to group',lambda checked=False,a=d['address']:self.join_speaker(a),True)
                action.setEnabled(eligible)
                self.party_card_actions.append((action,d['address']))
            else:
                action=self.party_connect_button(d)
            box.addWidget(action)
            card=SpeakerDragCard(host['address'],d['address'],QPixmap(str(image))) if eligible else panel()
            if eligible:card.draggingChanged.connect(self.party_drag_changed)
            card.setLayout(box)
            card.setMinimumHeight(190)
            self.available_grid.addWidget(card,i//3,i%3)

    def party_connect_button(self,d):
        caption='Connecting…' if d['busy'] else 'Wake & connect' if d.get('sleeping') and d.get('wake_available') else 'Connect first'
        action=button(caption,lambda checked=False,a=d['address']:self.connect_party_speaker(a))
        action.setEnabled(d['paired'] and not d['busy'])
        return action

    def connect_party_speaker(self,address):
        if self.demo:
            self.devices[address]['connected']=True
            self.update_devices(list(self.devices.values()))
        else:self.controller.submit('connect',address)

    def clear_party_cards(self):
        self.member_sliders={}
        self.member_timers={}
        self.party_card_actions=[]
        self.party_grid_signature=None
        for grid in (self.party_grid,self.available_grid):
            while grid.count():
                item=grid.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()

    def send_member_level(self,host,address,value):
        if self.group_host==host:self.party_action('member_volume',address,value)

    def open_speaker(self,address):
        self.selected=address
        self.eq_dirty=False
        self.volume_debounce.stop()
        self.group_debounce.stop()
        self.balance_timer.stop()
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            item=self.list.item(i)
            if item.data(Qt.UserRole)==address:self.list.setCurrentItem(item);break
        self.list.blockSignals(False)
        self.navigate('speaker')

    def command(self,action,*args):
        if not self.selected:return
        if self.demo:
            if action=='custom_eq':
                self.devices[self.selected]['bands']=list(args[0])
                self.devices[self.selected]['eq']=4
                self.render()
            self.show_status(f'Demo: {action.replace("_"," ")}')
            return
        self.controller.submit(action,self.selected,*args)

    def scan(self):
        if self.demo:self.show_status('Demo speakers are already visible.');return
        self.controller.submit('scan')

    def connect(self):
        self.volume_debounce.stop()
        if self.demo:
            d=self.devices[self.selected];d['connected']=not d['connected'];self.update_devices(list(self.devices.values()));return
        d=self.devices[self.selected]
        self.command('disconnect' if d['connected'] or d['busy'] else 'wake' if d.get('sleeping') and d.get('wake_available') else 'connect')

    def rename_speaker(self):
        if not self.selected:return
        d=self.devices[self.selected]
        name,ok=QInputDialog.getText(self,'Rename speaker','Name saved on the speaker:',text=d['name'])
        if ok and name.strip()!=d['name']:
            if self.demo:
                self.devices[self.selected]['name']=name.strip();self.update_devices(list(self.devices.values()))
            else:self.command('rename',name)

    def keyboard_volume(self, action):
        if not self.volume.isSliderDown():self.volume_debounce.start()

    def set_volume(self):
        self.volume_debounce.stop()
        if self.demo:
            self.devices[self.selected]['volume']=self.volume.value();return
        self.command('volume',self.volume.value())

    def set_preset(self,index):
        code=self.preset.itemData(index)
        if code is not None:self.send_eq(code)

    def set_eq_preset(self,index):
        code=self.eq_preset.itemData(index)
        if code is not None:self.send_eq(code)

    def send_eq(self,code):
        self.eq_dirty = False
        if self.demo:self.devices[self.selected]['eq']=code;self.render();return
        self.command('eq',code)

    def apply_custom(self):
        values=[s.value() for s in self.band_sliders]
        self.eq_dirty = False
        self.command('custom_eq',values)

    def power_off(self):
        if not self.selected:return
        if not self.devices[self.selected]['connected']:
            self.command('wake')
            return
        reply=QMessageBox.question(self,'Power off speaker','Turn off this speaker? If Bluetooth Smart is enabled, search for speakers to wake it again.')
        if reply==QMessageBox.Yes:
            if self.demo:self.devices[self.selected]['connected']=False;self.render();return
            self.command('power')

    def refresh(self):
        if self.demo:self.show_status('Demo readings refreshed.');return
        self.controller.submit('refresh_all')

    def refresh_quietly(self):
        if self.demo:return
        if any(d.get('audio_active') for d in self.devices.values()):return
        for d in self.devices.values():
            if d['connected'] and not d['busy']:self.controller.submit('poll',d['address'])

    def choose_colour(self,colour):
        if self.selected and colour:
            self.settings.setValue('colour/'+self.selected,'automatic' if colour.startswith('Automatic · ') else colour)
            self.render()

    def show_status(self,message):
        self.notice.setText(message)

    def show_firmware(self):
        speaker=self.devices.get(self.selected)
        if not speaker:return
        previous=getattr(self,'firmware_dialog',None)
        if previous:
            previous.close()
            previous.deleteLater()
        self.firmware_dialog=FirmwareDialog(speaker,self.controller,self,self.demo)
        self.firmware_dialog.show()

    def update_computer_mix(self,state):
        self.computer_mix_state=state
        self.computer_mix_hint.setText('Computer mix is on · native PartyUp is bypassed.' if state['running'] else state.get('error') or 'Alternative: send audio directly from Linux to two speakers.')
        if state.get('error'):self.show_error(state['error'])
        self.render_party()

    def show_computer_mix(self):
        previous=getattr(self,'computer_mix_dialog',None)
        if previous:
            previous.close();previous.deleteLater()
        self.computer_mix_dialog=ComputerMixDialog(self.controller,self,self.demo,self.computer_mix_state)
        self.computer_mix_dialog.show()

    def show_error(self,message):
        self.notice.setText(message)
        self.notice.setToolTip(message)

    def bluetooth_settings(self):
        for program,args in [('gnome-control-center',['bluetooth']),('blueman-manager',[]),('systemsettings',['kcm_bluetooth']),('kcmshell6',['kcm_bluetooth'])]:
            binary=shutil.which(program)
            if binary:
                environment=QProcessEnvironment.systemEnvironment()
                original=os.environ.get('LD_LIBRARY_PATH_ORIG')
                if original is None:environment.remove('LD_LIBRARY_PATH')
                else:environment.insert('LD_LIBRARY_PATH',original)
                for name in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QML2_IMPORT_PATH'):
                    environment.remove(name)
                process=QProcess()
                process.setProgram(binary)
                process.setArguments(args)
                process.setProcessEnvironment(environment)
                started,pid=process.startDetached()
                if started:return

        QMessageBox.information(self,'Bluetooth settings','Open Bluetooth settings from your desktop’s system menu and pair your speaker there.')

    def load_demo(self):
        from .models import Speaker
        from dataclasses import asdict
        data=[]
        for i,(name,model,battery,volume) in enumerate([('Living room','megaboom-3',30,25),('Kitchen','boom-3',60,38)]):
            s=Speaker(f'demo-{i}','',name,model=model,paired=True,connected=True,battery=battery,volume=volume,eq=0,bands=[0]*5,firmware='Demo',features={'eq_write':True,'custom_eq':True,'power':True})
            data.append(asdict(s))
        data[0]['members']=['demo-1'];data[0]['broadcast']=3
        for d in data:d['features'].update(group=True,balance=True)
        data[0]['balance']=0
        data[0]['audio_mode']=0x50
        self.update_devices(data)
        self.show_status('Demo mode. All readings and controls are simulated.')

    def about(self):
        QMessageBox.about(self,'About Speaker studio',f'Speaker studio {__version__}\nAn independent Linux app by RaphaCrafts.\nNot affiliated with Logitech or Ultimate Ears.\n\nSource and licences are included with the download.\nSpeaker images belong to Logitech / Ultimate Ears.')

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(),self)
        self.tray.setToolTip('Speaker studio')
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction('Show Speaker studio',self.restore_window)
        self.hide_action = self.tray_menu.addAction('Hide window',self.hide_to_tray)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction('Quit',self.quit_app)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        QApplication.instance().aboutToQuit.connect(self.cleanup)

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick):
            self.restore_window()

    def hide_to_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.show_status('Your desktop does not currently provide a system tray. You can minimize the window instead.')

    def cleanup(self):
        self.poll.stop()
        self.volume_debounce.stop()
        self.group_debounce.stop()
        self.cancel_balance()
        for timer in self.member_timers.values():timer.stop()
        self.party_link.timer.stop()
        self.tray.hide()
        if self.controller.isRunning():self.controller.shutdown()

    def quit_app(self):
        self.cleanup()
        QApplication.instance().quit()

    def closeEvent(self,event):
        # Closing quits; hiding is explicit, so no invisible background process
        # remains on desktops that do not provide a tray.
        self.cleanup()
        event.accept()
