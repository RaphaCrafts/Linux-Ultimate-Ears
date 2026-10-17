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
