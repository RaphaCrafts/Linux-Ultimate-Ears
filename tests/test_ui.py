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


def test_partyup_always_allows_return_and_discards_stale_group_view(tmp_path,monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents();w.navigate('party')
    item=w.list.currentItem()
    w.list.itemClicked.emit(item)
    assert w.page=='speaker' and w.selected==item.data(Qt.UserRole)
    w.navigate('party')
    for d in w.devices.values():d.update(connected=False,busy=False,members=[],broadcast=0)
    w.group_debounce.start();w.update_devices(list(w.devices.values()))
    assert w.group_host is None and not w.ungroup_button.isEnabled()
    assert not w.group_debounce.isActive() and w.group_volume_label.text()=='—'
    assert all('Saved · disconnected' in w.list.item(i).text() for i in range(w.list.count()))
    back=next(b for b in w.findChildren(QPushButton) if b.text()=='Back to speaker')
    assert back.isEnabled();back.click();assert w.page=='speaker'
    w.close()


def test_sleeping_speaker_has_turn_on_control(tmp_path,monkeypatch):
    from dataclasses import asdict
    from speakerstudio.models import Speaker
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents()
    row=asdict(Speaker('demo-sleep','','MEGABOOM 3',paired=True,wake_available=True,sleeping=True))
    w.update_devices([row])
    assert w.power_button.text()=='Turn on' and w.power_button.isEnabled()
    assert 'Sleeping' in w.list.item(0).text()
    row['wake_available']=False;row['sleeping']=None;w.update_devices([row])
    assert not w.power_button.isEnabled()
    w.close()


def test_detected_finish_and_model_survive_app_restart(tmp_path,monkeypatch):
    from dataclasses import asdict
    from speakerstudio.models import Speaker
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    first=Window(Controller(),demo=True);app.processEvents()
    known=asdict(Speaker('demo-remember','','Living room',model='megaboom-3',colour='Unicorn pink',colour_code=0x431))
    first.update_devices([known]);first.close()
    second=Window(Controller(),demo=True);app.processEvents()
    offline=asdict(Speaker('demo-remember','','Living room',paired=True))
    second.update_devices([offline])
    assert second.devices['demo-remember']['model']=='megaboom-3'
    assert second.image_path(second.devices['demo-remember']).name=='megaboom-3-unicorn-pink.webp'
    assert second.finish_hint.text().startswith('Remembered: Unicorn pink')
    assert not offline['model'] and not offline['colour'],'Snapshots must not be mutated'
    second.colour_select.setCurrentText('Generic MEGABOOM 3')
    second.update_devices([offline]);assert second.image_path(second.devices['demo-remember']).name=='megaboom.svg'
    second.close()


def test_bluetooth_link_is_not_presented_as_fully_disconnected(tmp_path,monkeypatch):
    from dataclasses import asdict
    from speakerstudio.models import Speaker
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents()
    row=asdict(Speaker('demo-status','','MEGABOOM 3',paired=True,bluez_connected=True,audio_connected=True))
    w.update_devices([row]);assert 'Bluetooth audio connected' in w.connection_label.text()
    assert 'Disconnected' not in w.connection_label.text()
    row.update(busy=True,operation='wake');w.update_devices([row])
    assert w.connect_button.text()=='Cancel' and w.connect_button.isEnabled()
    row.update(busy=False,operation='',error='The speaker did not reply')
    w.update_devices([row]);assert w.device_error.text()=='The speaker did not reply'
    assert w.photo.height()==240
    w.close()


def test_active_group_without_inventory_is_not_shown_as_empty(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents()
    w.navigate('party')
    host=w.devices[w.group_host]
    host.update(broadcast=2,members=[],group_status_known=False)
    w.demo=False
    w.render()
    assert 'waiting for member details' in w.party_info.text()
    assert w.ungroup_button.isEnabled()
    assert 'End group' in w.group_status.text()
    host['group_status_known']=True
    w.render()
    assert '0 group members' in w.party_info.text()
    w.close()


def test_read_existing_group_connects_audio_host_not_selected_receiver(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    controller=Controller();w=Window(controller,demo=True);app.processEvents()
    host=next(iter(w.devices));receiver=next(a for a in w.devices if a!=host)
    w.devices[host].update(audio_connected=True,audio_active=True,paired=True,connected=False)
    w.selected=receiver;w.demo=False
    sent=[];monkeypatch.setattr(controller,'submit',lambda *args:sent.append(args))
    w.read_existing_group()
    assert sent==[('connect',host)] and w.group_host==host
    w.devices[host]['connected']=True
    w.read_existing_group()
    assert sent[-1]==('refresh',host)
    w.close()


def test_refresh_available_offline_and_party_connect_stays_on_page(tmp_path,monkeypatch):
    from dataclasses import asdict
    from PySide6.QtWidgets import QPushButton
    from speakerstudio.models import Speaker
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents()
    row=asdict(Speaker('demo-sleep','','Sleeping',paired=True,wake_available=True,sleeping=True))
    w.update_devices([row]);w.navigate('party')
    assert w.refresh_button.isEnabled()
    action=next(b for b in w.party_page.findChildren(QPushButton) if b.text()=='Wake & connect')
    calls=[];c.submit=lambda *args:calls.append(args)
    w.demo=False
    action.click();assert calls[-1]==('connect','demo-sleep') and w.page=='party'
    w.refresh_button.click();assert calls[-1]==('refresh_all',)
    w.demo=True;w.close()


def test_eq_reset_and_saved_party_default(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QPushButton
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents();w.navigate('eq')
    w.send_eq(3);w.band_sliders[0].setValue(32)
    w.reset_eq.click()
    assert w.devices[w.selected]['eq']==0 and not w.eq_dirty
    assert 'party' not in w.tabs
    assert len([b for b in w.findChildren(QPushButton) if b.text()=='PartyUp'])==1
    w.method_buttons['computer'].click()
    w.open_party();assert w.page=='party' and w.playback_method=='computer'
    w.close()
    second=Window(Controller(),demo=True);app.processEvents()
    assert second.playback_method=='computer'
    second.close()


def test_builtin_edits_become_drafts_and_reset_restores_baseline(tmp_path,monkeypatch):
    from speakerstudio.equalizer import PREVIEW_CURVES, preview_bands
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents();w.navigate('eq')
    original=dict(PREVIEW_CURVES)
    for code in range(4):
        w.send_eq(code)
        assert [slider.value() for slider in w.band_sliders]==preview_bands(code)
        w.band_sliders[0].setValue(50)
        assert w.eq_preset.currentText()=='Custom draft'
        assert w.preset.currentData()=='draft' and w.eq_dirty
        assert w.devices[w.selected]['eq']==code, 'Drafting must not change the playing preset'
        w.update_devices(list(w.devices.values()))
        assert w.eq_preset.currentData()=='draft' and w.band_sliders[0].value()==50
        w.apply_custom()
        assert w.devices[w.selected]['eq']==4 and not w.eq_dirty
        w.send_eq(code)
        assert [slider.value() for slider in w.band_sliders]==preview_bands(code)
    assert dict(PREVIEW_CURVES)==original
    w.reset_eq.click()
    assert w.eq_preset.currentData()==0 and [s.value() for s in w.band_sliders]==[0]*5
    w.close()


def test_named_profiles_survive_restart_and_edits_preserve_saved_copy(tmp_path,monkeypatch):
    from speakerstudio.equalizer import load_profiles
    from speakerstudio.ui import QInputDialog
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents();w.navigate('eq')
    w.band_sliders[0].setValue(53)
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**kw:('Late night',True))
    w.save_eq.click()
    key=w.eq_preset.currentData();saved=load_profiles(w.settings)[key]
    assert saved['name']=='Late night' and saved['bands']==[53,0,0,0,0]
    w.band_sliders[0].setValue(77)
    assert w.eq_preset.currentData()=='draft'
    assert load_profiles(w.settings)[key]==saved
    w.send_eq(0)
    w.set_eq_preset(w.eq_preset.findData(key))
    assert w.devices[w.selected]['eq']==4 and w.devices[w.selected]['bands']==saved['bands']
    assert w.eq_preset.currentText()=='Late night'
    assert w.band_outputs[0].text()=='+42%'
    w.close()
    second=Window(Controller(),demo=True);app.processEvents()
    assert second.eq_preset.findData(key)>=0
    second.choose_eq_profile(key)
    assert second.devices[second.selected]['bands']==saved['bands']
    second.close()


def test_custom_apply_keeps_draft_during_old_busy_snapshots(tmp_path,monkeypatch):
    from copy import deepcopy
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents();w.navigate('eq')
    w.band_sliders[0].setValue(42)
    sent=[];w.command=lambda *args:sent.append(args)
    w.apply_custom();assert sent==[('custom_eq',[42,0,0,0,0])]
    rows=deepcopy(list(w.devices.values()))
    selected=next(d for d in rows if d['address']==w.selected)
    selected.update(busy=True,operation='custom_eq')
    w.update_devices(rows)
    assert w.eq_dirty and w.band_sliders[0].value()==42
    selected.update(busy=False,operation='',eq=4,bands=[42,0,0,0,0])
    w.update_devices(rows)
    assert not w.eq_dirty and w.eq_preset.currentData()==4
    w.close()
