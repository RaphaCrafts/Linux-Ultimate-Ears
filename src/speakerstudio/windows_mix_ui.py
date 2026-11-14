"""Controls for an explicitly selected Windows loopback source and outputs."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

from .windows_mix import WindowsMix


class WindowsMixDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Windows Computer mix · experimental')
        self.resize(570, 480)
        self.mix = None
        layout = QVBoxLayout(self)
        instructions = QLabel(
            'End native PartyUp and connect the speakers separately in Windows. '
            'Play music through the source output. The mix mirrors that output '
            'to the checked devices while this window is open.'
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        source_label = QLabel('Source output')
        layout.addWidget(source_label)
        self.source = QComboBox()
        self.source.setAccessibleName('Source output')
        layout.addWidget(self.source)
        layout.addWidget(QLabel('Additional speaker outputs'))
        self.destinations = QListWidget()
        self.destinations.setAccessibleName('Additional speaker outputs')
        layout.addWidget(self.destinations, 1)
        self.message = QLabel()
        self.message.setTextFormat(Qt.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        actions = QHBoxLayout()
        self.refresh = QPushButton('Refresh outputs')
        self.refresh.clicked.connect(self.refresh_outputs)
        self.start = QPushButton('Start mix')
        self.start.clicked.connect(self.start_mix)
        self.stop = QPushButton('Stop mix')
        self.stop.clicked.connect(self.stop_mix)
        for action in (self.refresh, self.start, self.stop):
            actions.addWidget(action)
        layout.addLayout(actions)
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self.check_mix)
        self.source.currentIndexChanged.connect(self.update_controls)
        self.destinations.itemChanged.connect(self.update_controls)
        self.finished.connect(self.release)
        self.refresh_outputs()

    def refresh_outputs(self):
        self.release()
        self.source.clear()
        self.destinations.clear()
        try:
            mix = WindowsMix()
            mix.__enter__()
            self.mix = mix
            devices = mix.outputs()
            default = mix.default_output()
            self.source.addItem('Select the output playing your music', None)
            for index, device in devices.items():
                label = device['name']
                if sum(row['name'] == label for row in devices.values()) > 1:
                    label = f'{label} ({index})'
                self.source.addItem(label, index)
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, index)
                item.setCheckState(Qt.Unchecked)
                self.destinations.addItem(item)
            if default in devices:
                self.source.setCurrentIndex(self.source.findData(default))
            self.message.setText('Choose a source and additional outputs.' if len(devices) >= 2
                                 else 'Connect another Windows audio output, then refresh.')
        except (OSError, ValueError, RuntimeError) as error:
            self.release()
            self.message.setText(f'Could not list Windows audio outputs. {error}')
        self.update_controls()

    def selected_outputs(self):
        items = [self.destinations.item(index) for index in range(self.destinations.count())]
        return [item.data(Qt.UserRole) for item in items
                if item.checkState() == Qt.Checked and item.data(Qt.UserRole) != self.source.currentData()]

    def update_controls(self):
        running = self.mix is not None and self.mix.running
        source = self.source.currentData()
        self.destinations.blockSignals(True)
        for index in range(self.destinations.count()):
            item = self.destinations.item(index)
            if item.data(Qt.UserRole) == source:
                item.setCheckState(Qt.Unchecked)
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEnabled)
        self.destinations.blockSignals(False)
        self.source.setEnabled(not running)
        self.destinations.setEnabled(not running)
        self.refresh.setEnabled(not running)
        self.start.setEnabled(self.mix is not None and not running and source is not None and bool(self.selected_outputs()))
        self.stop.setEnabled(running)

    def start_mix(self):
        try:
            self.mix.start(self.source.currentData(), self.selected_outputs())
            self.message.setText('Mix active. Bluetooth delay and timing may vary between outputs.')
            self.timer.start()
        except (OSError, ValueError, RuntimeError) as error:
            self.message.setText(str(error))
        self.update_controls()

    def check_mix(self):
        try:
            self.mix.check()
        except (OSError, RuntimeError, ValueError) as error:
            self.stop_mix()
            self.message.setText(f'Mix stopped. {error}')

    def stop_mix(self):
        self.timer.stop()
        try:
            self.mix.stop()
            self.message.setText('Mix stopped.')
        except RuntimeError as error:
            self.message.setText(str(error))
        self.update_controls()

    def release(self):
        self.timer.stop()
        if self.mix is not None:
            mix, self.mix = self.mix, None
            try:
                mix.__exit__(None, None, None)
            except (OSError, RuntimeError) as error:
                self.message.setText(str(error))
