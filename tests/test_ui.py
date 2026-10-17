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
    assert w.colour_select.currentText()=='Automatic · Generic'
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


def test_generic_artwork_for_unknown_finish_and_missing_image(tmp_path,monkeypatch):
    from dataclasses import asdict
    from speakerstudio.models import Speaker, ARTWORK_MODELS
    from PySide6.QtGui import QPixmap
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents()
    for model in (*ARTWORK_MODELS,'megaboom','boom-2','boom','megaboom-5','unlisted'):
        row=asdict(Speaker('demo-fallback','',model.upper(),model=model,paired=True))
        w.settings.setValue('colour/demo-fallback','Unlisted limited edition')
        w.update_devices([row])
        assert 'generic' in str(w.image_path(row))
        assert not w.photo.pixmap().isNull(),model
        assert w.colour_select.currentText()=='Automatic · Generic'
    row['model']='megaboom-3'
    w.settings.setValue('colour/demo-fallback','Missing packshot')
    w.catalogue.append({'model':'megaboom-3','colour':'Missing packshot','file':'does-not-exist.webp'})
    assert w.image_path(row).name=='megaboom.svg'
    w.settings.setValue('colour/demo-fallback','Unicorn pink')
    assert w.image_path(row).name=='megaboom-3-unicorn-pink.webp'
    w.settings.setValue('colour/demo-fallback','Generic MEGABOOM 3')
    assert w.image_path(row).name=='megaboom.svg'
    assert not QPixmap(str(w.image_path(row))).isNull()
    w.close()


def test_automatic_colour_and_manual_override(tmp_path,monkeypatch):
    from dataclasses import asdict
    from speakerstudio.models import Speaker
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents()
    row=asdict(Speaker('demo-auto','','MEGABOOM 3',model='megaboom-3',colour='Unicorn pink',colour_code=0x431))
    w.update_devices([row])
    assert w.image_path(row).name=='megaboom-3-unicorn-pink.webp'
    assert w.colour_select.currentText()=='Automatic · Unicorn pink'
    w.colour_select.setCurrentText('Generic MEGABOOM 3')
    w.update_devices([row])
    assert w.image_path(row).name=='megaboom.svg'
    w.colour_select.setCurrentIndex(0)
    assert w.settings.value('colour/demo-auto')=='automatic'
    assert w.image_path(row).name=='megaboom-3-unicorn-pink.webp'
    w.close()


def test_tray_hide_restore_and_no_tray_fallback(tmp_path,monkeypatch):
    from speakerstudio.ui import QSystemTrayIcon
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents();w.show()
    assert not w.tray.icon().isNull()
    assert max(size.width() for size in w.windowIcon().availableSizes())<=256
    assert [a.text() for a in w.tray_menu.actions() if not a.isSeparator()]==['Show Speaker studio','Hide window','Quit']
    monkeypatch.setattr(QSystemTrayIcon,'isSystemTrayAvailable',lambda:False)
    w.hide_to_tray();assert w.isVisible()
    monkeypatch.setattr(QSystemTrayIcon,'isSystemTrayAvailable',lambda:True)
    w.hide_to_tray();assert not w.isVisible()
    w.restore_window();assert w.isVisible()
    w.close();assert not w.tray.isVisible()
