import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from speakerstudio.backend import Controller
from speakerstudio.ui import Window


def test_demo_is_offline_and_state_is_per_speaker(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    controller=Controller()
    window=Window(controller,demo=True)
    app.processEvents()
    assert not controller.isRunning()
    assert len(window.devices)==2
    first=window.selected
    window.send_eq(3)
    assert window.devices[first]['eq']==3
    second=next(k for k in window.devices if k!=first)
    window.open_speaker(second)
    assert window.devices[second]['eq']==0
    window.navigate('party')
    assert window.stack.currentWidget()==window.party_page
    window.navigate('eq')
    assert window.stack.currentWidget()==window.eq_page
    assert not window.photo.pixmap().isNull()
    window.close()


def test_demo_group_and_unsaved_custom_levels(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents()
    w.navigate('party')
    host=w.group_host
    assert w.devices[host]['members']==['demo-1']
    w.party_action('group_remove','demo-1')
    assert w.devices[host]['members']==[]
    w.party_action('group_add','demo-1')
    assert w.devices[host]['members']==['demo-1']
    w.open_speaker(host);w.navigate('eq')
    w.band_sliders[0].setValue(32)
    assert w.eq_dirty
    w.update_devices(list(w.devices.values()))
    assert w.band_sliders[0].value()==32, 'Background refresh must not erase edits'
    w.apply_custom()
    assert w.devices[host]['bands'][0]==32
    assert w.devices[host]['eq']==4
    w.close()


def test_paired_speaker_artwork_before_connection(tmp_path,monkeypatch):
    from dataclasses import asdict
    from speakerstudio.models import Speaker
    from PySide6.QtWidgets import QPushButton
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents()
    row=asdict(Speaker('demo-paired','','MEGABOOM 3',paired=True))
    w.update_devices([row])
    assert w.inferred_model(row)=='megaboom-3'
    assert not w.photo.pixmap().isNull()
    assert w.colour_select.currentText()=='Unicorn pink'
    assert w.battery_hint.text()=='Connect to check'
    assert not w.identify_button.isEnabled()
    assert not any('demo' in b.text().lower() for b in w.findChildren(QPushButton))
    w.colour_select.setCurrentText('Lagoon blue')
    w.update_devices([row])
    assert w.colour_select.currentText()=='Lagoon blue'
    row.update(connected=True,battery=30)
    w.update_devices([row])
    assert w.battery_meter.value()==30
    assert w.identify_button.isEnabled()
    w.close()
