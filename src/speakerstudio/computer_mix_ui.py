"""Explicit independent-playback controls, separate from native PartyUp."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QWidget, QLayout, QFrame


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
        label('Computer mix').setObjectName('section')
        label('Experimental: may have echo, drift or interruptions. Automatic timing compensation is enabled.')
        label('Native PartyUp ends automatically. Connect the speakers in Linux Bluetooth settings if their outputs are missing.')
        self.refresh=QPushButton('Refresh outputs');self.refresh.clicked.connect(lambda:self.controller.submit('computer_mix_outputs'))
        layout.addWidget(self.refresh)
        self.outputs=QListWidget()
        self.outputs.setAccessibleName('Speaker audio outputs')
        self.outputs.itemChanged.connect(self.enabled_state)
        layout.addWidget(self.outputs)
        self.message=label('Refresh outputs to find connected speakers.')
        row=QHBoxLayout()
        self.start=QPushButton('Start Computer mix');self.start.clicked.connect(self.start_mix)
        self.stop=QPushButton('Stop and restore output');self.stop.clicked.connect(lambda:self.controller.submit('computer_mix_stop'))
        row.addWidget(self.start);row.addWidget(self.stop);layout.addLayout(row)
        label('Closing this panel keeps music playing. Stop restores your previous output.')
        done=QPushButton('Done');done.clicked.connect(self.close);layout.addWidget(done)
        controller.computer_mix_changed.connect(self.update_state)
        self.update_state(state or {'running':False,'outputs':[],'error':''})
        if not demo:controller.submit('computer_mix_prepare')

    def enabled_state(self,*args):
        self.start.setEnabled(len(self.selected_outputs())>=2 and not self.running and not self.demo)
        self.stop.setEnabled(self.running and not self.demo)
        self.outputs.setEnabled(not self.running)

    def selected_outputs(self):
        items=[self.outputs.item(i) for i in range(self.outputs.count())]
        return [item.data(Qt.UserRole) for item in items if item.checkState()==Qt.Checked]

    def update_state(self,state):
        self.running=state['running']
        selected=set(self.selected_outputs())
        outputs=state.get('outputs',[])
        if not self.outputs.count() and len(outputs)==2:
            selected={output['name'] for output in outputs}
        self.outputs.blockSignals(True)
        self.outputs.clear()
        for output in outputs:
            item=QListWidgetItem(output['label'])
            item.setData(Qt.UserRole,output['name'])
            item.setCheckState(Qt.Checked if output['name'] in selected else Qt.Unchecked)
            self.outputs.addItem(item)
        self.outputs.blockSignals(False)
        self.message.setText(state.get('error') or ('Computer mix is playing independently from Linux.' if self.running else 'Choose at least two outputs, then start.' if len(outputs)>=2 else 'Connect at least two separate Bluetooth audio outputs in Linux, then refresh.'))
        self.enabled_state()

    def start_mix(self):
        if not self.start.isEnabled():return
        self.start.setEnabled(False);self.message.setText('Starting Computer mix…')
        self.controller.submit('computer_mix_start',json.dumps(self.selected_outputs()))
