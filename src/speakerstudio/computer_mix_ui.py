"""Explicit independent-playback controls, separate from native PartyUp."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QCheckBox, QScrollArea, QWidget, QLayout, QFrame


class ComputerMixDialog(QDialog):
    def __init__(self,controller,parent=None,demo=False,state=None):
        super().__init__(parent)
        self.setObjectName('computerMixDialog');self.setWindowTitle('Computer mix · experimental')
        self.resize(600,650);self.setMinimumSize(520,420)
        self.controller=controller;self.demo=demo;self.running=False
        outer=QVBoxLayout(self)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame)
        content=QWidget();layout=QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        layout.setContentsMargins(24,24,24,24);layout.setSpacing(14)
        scroll.setWidget(content);outer.addWidget(scroll)
        def label(value):
            widget=QLabel(value);widget.setTextFormat(Qt.PlainText);widget.setWordWrap(True)
            widget.ensurePolished();widget.setMinimumHeight(widget.heightForWidth(440))
            layout.addWidget(widget);return widget
        label('Play without PartyUp').setObjectName('section')
        label('Linux sends the same stereo audio directly to two speakers, bypassing their PartyUp link. This is experimental: some setups may still have echo, drift or interruptions.')
        label('First end native PartyUp. Connect both speakers separately in Linux Bluetooth settings, then refresh outputs. Your phone’s Bluetooth should be off for this comparison.')
        self.refresh=QPushButton('Refresh outputs');self.refresh.clicked.connect(lambda:self.controller.submit('computer_mix_outputs'))
        layout.addWidget(self.refresh)
        self.outputs=[]
        for caption in ('First speaker','Second speaker'):
            label(caption)
            combo=QComboBox();combo.setAccessibleName(caption+' audio output');combo.currentIndexChanged.connect(self.enabled_state)
            self.outputs.append(combo);layout.addWidget(combo)
        self.confirm=QCheckBox('Native PartyUp is off')
        self.confirm.toggled.connect(self.enabled_state);layout.addWidget(self.confirm)
        self.message=label('Refresh outputs to find connected speakers.')
        row=QHBoxLayout()
        self.start=QPushButton('Start Computer mix');self.start.clicked.connect(self.start_mix)
        self.stop=QPushButton('Stop and restore output');self.stop.clicked.connect(lambda:self.controller.submit('computer_mix_stop'))
        row.addWidget(self.start);row.addWidget(self.stop);layout.addLayout(row)
        label('Start selects Computer mix as Linux’s output. Stop or Quit removes it and restores the previous output unless you chose another one. Closing this panel or hiding the app keeps playback running. Firmware is not changed.')
        done=QPushButton('Done');done.clicked.connect(self.close);layout.addWidget(done)
        controller.computer_mix_changed.connect(self.update_state)
        self.update_state(state or {'running':False,'outputs':[],'error':''})
        if not demo:controller.submit('computer_mix_outputs')

    def enabled_state(self,*args):
        if not hasattr(self,'start'):return
        names=[combo.currentData() for combo in self.outputs]
        valid=all(names) and names[0]!=names[1]
        self.start.setEnabled(bool(valid and self.confirm.isChecked() and not self.running and not self.demo))
        self.stop.setEnabled(self.running and not self.demo)
        for combo in self.outputs:combo.setEnabled(not self.running)
        self.confirm.setEnabled(not self.running)

    def update_state(self,state):
        self.running=state['running']
        for index,combo in enumerate(self.outputs):
            selected=combo.currentData();combo.blockSignals(True);combo.clear()
            for output in state.get('outputs',[]):combo.addItem(output['label'],output['name'])
            found=combo.findData(selected)
            combo.setCurrentIndex(found if found>=0 else min(index,combo.count()-1))
            combo.blockSignals(False)
        self.message.setText(state.get('error') or ('Computer mix is playing independently from Linux.' if self.running else 'Choose two outputs, then start.' if len(state.get('outputs',[]))>=2 else 'Two separate Bluetooth audio outputs are required. Connect both in Linux, then refresh.'))
        self.enabled_state()

    def start_mix(self):
        if not self.start.isEnabled():return
        self.start.setEnabled(False);self.message.setText('Starting Computer mix…')
        self.controller.submit('computer_mix_start',json.dumps([combo.currentData() for combo in self.outputs]))
