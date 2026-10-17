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
    QScrollArea, QMessageBox, QMenu, QApplication, QProgressBar, QSystemTrayIcon)
from PySide6.QtCore import QProcess, QProcessEnvironment
from . import __version__


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
        self.selected = None
        self.page = 'speaker'
        self.group_host = None
        self.eq_dirty = False
        self.settings = QSettings('RaphaCrafts', 'SpeakerStudio')
        self.catalogue = json.loads((asset_root()/'speakers/manifest.json').read_text())['images']
        self.setWindowTitle('Speaker studio')
        self.setWindowIcon(app_icon())
        self.resize(1080, 810)
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
        sidebar.setFixedWidth(205)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(13,23,13,20)
        side.addWidget(text('YOUR SPEAKERS','eyebrow'))
        self.list = QListWidget()
        self.list.setIconSize(QSize(28,54))
        self.list.currentItemChanged.connect(self.select)
        side.addWidget(self.list)
        side.addWidget(button('Search for speakers', self.scan, True))
        side.addWidget(button('Bluetooth settings', self.bluetooth_settings))
        side.addWidget(button('PartyUp', lambda:self.navigate('party')))
        side.addWidget(text('Independent app by RaphaCrafts','muted'))
        body.addWidget(sidebar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(27,22,27,20)
        nav = QHBoxLayout()
        self.tabs = {}
        for key,label in [('speaker','Speaker'),('party','PartyUp'),('eq','Equalizer')]:
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
        self.set_theme(self.settings.value('theme','system'))
        self.navigate('speaker')
        self.poll = QTimer(self)
        self.poll.setInterval(15000)
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
        self.connect_button = button('Connect',self.connect,True)
        heading.addWidget(self.connect_button)
        layout.addLayout(heading)
        columns = QHBoxLayout()
        hero = QFrame()
        hero.setObjectName('hero')
        image_layout = QVBoxLayout(hero)
        image_layout.setContentsMargins(18,18,18,18)
        image_layout.addWidget(text('ULTIMATE EARS','eyebrow'))
        self.photo = QLabel()
        self.photo.setTextFormat(Qt.PlainText)
        self.photo.setAlignment(Qt.AlignCenter)
        self.photo.setMinimumHeight(320)
        image_layout.addWidget(self.photo,1)
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
        columns.addLayout(controls,1)
        layout.addLayout(columns)
        footer = QHBoxLayout()
        footer.addWidget(text('More speakers, one soundtrack.','section'),1)
        footer.addWidget(button('View PartyUp',lambda:self.navigate('party'),True))
        layout.addLayout(footer)
        return widget

    def build_party(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0,20,0,0)
        layout.addWidget(text('PartyUp','title'))
        self.party_info = text('Connect a supported speaker to manage its group.','muted')
        layout.addWidget(self.party_info)
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
        self.party_grid = QGridLayout()
        layout.addLayout(self.party_grid)
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
        if current:
            self.selected = current.data(Qt.UserRole)
            self.eq_dirty = False
            self.volume_debounce.stop()
            self.render()

    def navigate(self, page):
        self.page = page
        for key,tab in self.tabs.items():tab.setChecked(key==page)
        self.render()

    def update_devices(self, devices):
        if devices and self.demo != all(d['address'].startswith('demo-') for d in devices):
            return
        self.devices = {d['address']:d for d in devices}
        selected = self.selected
        self.list.blockSignals(True)
        self.list.clear()
        for d in devices:
            state = 'Connected' if d['connected'] else 'Paired' if d['paired'] else 'Pair in Bluetooth settings'
            item = QListWidgetItem(f"{d['name']}\n{state}")
            item.setData(Qt.UserRole,d['address'])
            image = self.image_path(d)
            if image:item.setIcon(QIcon(str(image)))
            item.setSizeHint(QSize(170,70))
            self.list.addItem(item)
            if d['address']==selected:self.list.setCurrentItem(item)
        if selected not in self.devices and devices:
            self.selected = devices[0]['address']
            self.list.setCurrentRow(0)
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
        if self.page=='party':
            self.stack.setCurrentWidget(self.party_page)
            self.render_party()
            return
        if not d:
            self.stack.setCurrentWidget(self.empty)
            self.refresh_button.setEnabled(False)
            return
        active = d['connected'] and not d['busy']
        self.refresh_button.setEnabled(active)
        self.stack.setCurrentWidget(self.eq_page if self.page=='eq' else self.speaker_page)
        self.model_label.setText(d.get('model','').upper().replace('-',' ') or 'ULTIMATE EARS')
        self.name_label.setText(d['name'])
        status = 'Connecting…' if d['busy'] and not d['connected'] else 'Connected' if d['connected'] else 'Ready to connect' if d['paired'] else 'Pair in Bluetooth settings first'
        if d.get('firmware') and d['connected']:status+=' · Firmware '+d['firmware']
        self.connection_label.setText(status)
        self.connect_button.setText('Disconnect' if d['connected'] else 'Connect')
        self.connect_button.setEnabled(not d['busy'] and d['paired'])
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
        self.power_button.setEnabled(active and d['features'].get('power',False))
        variants = self.artwork_variants(d)
        self.colour_select.blockSignals(True)
        self.colour_select.clear()
        self.colour_select.addItems([r['colour'] for r in variants])
        saved = self.settings.value('colour/'+d['address'],'')
        record = next((r for r in variants if r['colour']==saved),self.default_artwork(variants))
        if record:self.colour_select.setCurrentText(record['colour'])
        self.colour_select.setVisible(bool(variants))
        self.colour_select.blockSignals(False)
        self.finish_hint.setText('Detected: '+d['colour']+'. You can choose a different finish.' if d.get('colour') else 'Finish not recognized. Choose a finish or use Generic.' if d.get('colour_code') is not None else 'Connect to detect the finish, or choose it below.')
        image = self.image_path(d)
        if image:
            self.photo.setPixmap(QPixmap(str(image)).scaled(320,370,Qt.KeepAspectRatio,Qt.SmoothTransformation))
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
        self.group_host=self.host_select.itemData(index)
        self.render_party()

    def party_action(self,action,*args):
        if not self.group_host:return
        if self.demo:
            host=self.devices[self.group_host]
            if action=='group_add' and args[0] not in host['members']:
                host['members'].append(args[0]);host['broadcast']=3
            elif action=='group_remove':host['members']=[m for m in host['members'] if m!=args[0]]
            elif action=='ungroup':host['members']=[];host['broadcast']=0
            elif action=='group_volume':host['volume']=args[0]
            self.render_party()
            self.show_status('Demo group updated. No Bluetooth commands sent.')
        else:
            self.controller.submit(action,self.group_host,*args)

    def render_party(self):
        while self.party_grid.count():
            item=self.party_grid.takeAt(0)
            if item.widget():item.widget().deleteLater()
        connected=[d for d in self.devices.values() if d['connected'] and d['features'].get('group')]
        self.host_select.blockSignals(True)
        self.host_select.clear()
        for d in connected:self.host_select.addItem(d['name'],d['address'])
        if self.group_host not in [d['address'] for d in connected]:
            self.group_host=connected[0]['address'] if connected else None
        if self.group_host:self.host_select.setCurrentIndex(self.host_select.findData(self.group_host))
        self.host_select.blockSignals(False)
        host=self.devices.get(self.group_host)
        self.ungroup_button.setEnabled(bool(host and host.get('broadcast',0)&2 and not host['busy']))
        self.group_volume.setEnabled(bool(host and host.get('broadcast',0)&2 and not host['busy']))
        if host and not self.group_volume.isSliderDown():
            self.group_volume.setValue(host['volume'] or 0)
        if not host:
            self.party_info.setText('Connect a supported speaker from the Speaker page to begin.')
            self.group_status.setText('Only speakers that support PartyUp can host a group.')
            return
        members=host.get('members',[])
        active=bool(host.get('broadcast',0)&2)
        self.party_info.setText(f"Host: {host['name']} · {len(members)} group members" if active else 'Choose a host, then add another connected speaker.')
        displayed=[host['address']]+members
        for i,address in enumerate(displayed):
            d=self.devices.get(address)
            metadata=host.get('member_info',{}).get(address,{})
            box=QVBoxLayout();box.setContentsMargins(16,16,16,16)
            box.addWidget(text('Host' if i==0 else 'Group member','eyebrow'))
            box.addWidget(text(d['name'] if d else 'Speaker in group','section'))
            photo=QLabel();photo.setAlignment(Qt.AlignCenter)
            image=self.image_path(d) if d else self.generic_path('')
            if image:photo.setPixmap(QPixmap(str(image)).scaled(100,135,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            box.addWidget(photo)
            battery=metadata.get('battery',d.get('battery') if d else None)
            if battery is None and d:battery=d.get('battery')
            box.addWidget(text(f'Battery {battery}%' if battery is not None else 'Battery —','muted'))
            if i==0:
                box.addWidget(button('Open speaker',lambda checked=False,a=address:self.open_speaker(a)))
            else:
                remove=button('Remove from group',lambda checked=False,a=address:self.party_action('group_remove',a))
                remove.setEnabled(not host['busy']);box.addWidget(remove)
            self.party_grid.addWidget(panel(box),i//3,i%3)
        row=(len(displayed)+2)//3
        self.party_grid.addWidget(text('Other speakers','section'),row,0,1,3)
        available=[d for d in self.devices.values() if d['address'] not in displayed]
        for i,d in enumerate(available):
            box=QVBoxLayout();box.setContentsMargins(13,13,13,13)
            box.addWidget(text(d['name'],'section'))
            if d['connected'] and d['features'].get('group'):
                action=button('Add to group',lambda checked=False,a=d['address']:self.party_action('group_add',a),True)
                action.setEnabled(not host['busy'] and not d['busy'])
            else:
                action=button('Connect first',lambda checked=False,a=d['address']:self.open_speaker(a))
            box.addWidget(action)
            self.party_grid.addWidget(panel(box),row+1+i//3,i%3)
        self.group_status.setText('Demo group. No real devices are changed.' if self.demo else 'Choose another connected speaker above to play together.')

    def open_speaker(self,address):
        self.selected=address
        self.eq_dirty=False
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
        self.command('disconnect' if self.devices[self.selected]['connected'] else 'connect')

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
        reply=QMessageBox.question(self,'Power off speaker','Turn off this speaker? Use its power button to turn it on again.')
        if reply==QMessageBox.Yes:
            if self.demo:self.devices[self.selected]['connected']=False;self.render();return
            self.command('power')

    def refresh(self):
        if self.demo:self.show_status('Demo readings refreshed.');return
        self.command('refresh')

    def refresh_quietly(self):
        if self.demo:return
        for d in self.devices.values():
            if d['connected'] and not d['busy']:self.controller.submit('refresh',d['address'])

    def choose_colour(self,colour):
        if self.selected and colour:
            self.settings.setValue('colour/'+self.selected,'automatic' if colour.startswith('Automatic · ') else colour)
            self.render()

    def show_status(self,message):
        self.notice.setText(message)

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
        for d in data:d['features']['group']=True
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
