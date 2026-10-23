import asyncio
import json
from types import SimpleNamespace
import pytest
from speakerstudio import audio_mix as mix
from speakerstudio.backend import Controller
from speakerstudio.models import Speaker

FIRST='00:11:22:33:44:55'
SECOND='00:11:22:33:44:66'
LEFT='bluez_output.00_11_22_33_44_55.1'
RIGHT='bluez_output.00_11_22_33_44_66.1'


def node(name,id):
    return {'id':id,'type':'PipeWire:Interface:Node','info':{'props':{'media.class':'Audio/Sink','node.name':name}}}


def active():
    c=mix.ComputerMix();c.process=object();c.names=[LEFT,RIGHT]
    return c


def test_output_volume_controls_use_fresh_exact_node_and_do_not_touch_other_speaker(monkeypatch):
    c=active();commands=[];ids=iter([27,48])
    monkeypatch.setattr(mix,'snapshot',lambda:[node(LEFT,next(ids)),node(RIGHT,99)])
    monkeypatch.setattr(mix.subprocess,'run',lambda args,**kw:commands.append(args))
    monkeypatch.setattr(mix.subprocess,'check_output',lambda args,**kw:'Volume: 0.35\n')
    assert c.set_volume(LEFT,35)=={'volume':35,'muted':False}
    c.set_volume(LEFT,35)
    assert commands==[
        ['wpctl','set-volume','--limit','1.0','27','35%'],['wpctl','set-mute','27','0'],
        ['wpctl','set-volume','--limit','1.0','48','35%'],['wpctl','set-mute','48','0']]
    for invalid in (-1,101,True,23.5,'40'):
        with pytest.raises(ValueError):c.set_volume(LEFT,invalid)
    with pytest.raises(RuntimeError):c.set_volume('unknown',20)


def test_volume_reading_handles_muted_unavailable_and_amplified_outputs(monkeypatch):
    c=active()
    monkeypatch.setattr(mix,'snapshot',lambda:[node(LEFT,4),node(RIGHT,5)])
    def read(args,**kw):
        assert kw['env']['LC_ALL']=='C'
        return 'Volume: 0.60 [MUTED]\n' if args[-1]=='4' else 'Volume: 1.20\n'
    monkeypatch.setattr(mix.subprocess,'check_output',read)
    assert c.levels()=={LEFT:{'volume':60,'muted':True},RIGHT:{'volume':100,'muted':False}}
    monkeypatch.setattr(mix,'snapshot',lambda:[node(RIGHT,6)])
    levels=c.levels();assert levels[LEFT]['error'] and levels[RIGHT]['volume']==100
    with pytest.raises(RuntimeError,match='disconnected'):c.set_volume(LEFT,40)
    c.process=None
    assert c.levels()=={}
    with pytest.raises(RuntimeError):c.set_volume(RIGHT,40)


def test_backend_output_volume_does_not_require_control_connection_or_bluez():
    async def scenario():
        c=Controller();calls=[];states=[];c.computer_mix_changed.connect(states.append)
        c.speakers[FIRST]=Speaker(FIRST,'','First',connected=False)
        def set_volume(name,value):calls.append((name,value));return {'volume':value,'muted':False}
        c.computer_mix=SimpleNamespace(active=True,names=[LEFT,RIGHT],set_volume=set_volume,
            levels=lambda:{LEFT:{'volume':42,'muted':False},RIGHT:{'volume':70,'muted':False}})
        c.mix_members=[FIRST,SECOND]
        await c._perform('computer_mix_volume',FIRST,42)
        assert calls==[(LEFT,42)] and not c.speakers[FIRST].busy
        assert states[-1]['levels'][FIRST]['volume']==42
        assert states[-1]['levels'][FIRST]['requested_volume']==42
        await c._computer_mix_levels()
        assert states[-1]['levels'][SECOND]['volume']==70
        await c._perform('computer_mix_volume','other',30)
        assert calls==[(LEFT,42)] and states[-1]['levels']['other']['error']
        c.group_switching=True
        await c._perform('computer_mix_volume',FIRST,80)
        assert calls==[(LEFT,42)] and states[-1]['levels'][FIRST]['error']
    asyncio.run(scenario())


def test_mix_volume_submission_remains_available_when_bluetooth_inventory_is_down():
    c=Controller();scheduled=[]
    c.loop=SimpleNamespace(is_running=lambda:True,call_soon_threadsafe=scheduled.append)
    c.submit('computer_mix_volume',FIRST,50);c.submit('computer_mix_levels')
    assert len(scheduled)==2


def test_slider_dispatch_and_stale_readbacks_preserve_edits(tmp_path,monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from speakerstudio.ui import Window
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents();w.navigate('party');w.choose_group_method('computer')
    members=list(w.computer_group);first,second=members
    state={'running':True,'method':'computer','members':members,'switching':False,'outputs':[],'error':'',
        'levels':{first:{'volume':25,'muted':False},second:{'volume':75,'muted':False}}}
    w.update_computer_mix(state)
    left,right=w.computer_sliders[first],w.computer_sliders[second]
    assert left.value()==25 and right.value()==75 and left.isEnabled()
    assert not w.levels_refresh.isHidden()
    calls=[];c.submit=lambda *args:calls.append(args);w.demo=False
    left.setValue(40);w.send_computer_level(first)
    assert calls==[('computer_mix_volume',first,40)]
    w.update_computer_mix(state)
    assert w.computer_sliders[first] is left and left.value()==40 and right.value()==75
    acknowledged={**state,'levels':{**state['levels'],first:{'volume':39,'muted':False,'requested_volume':40}}}
    w.update_computer_mix(acknowledged)
    assert left.value()==39 and first not in w.computer_level_pending
    assert '39%' in w.computer_outputs[first].text()
    w.levels_refresh.click();assert calls[-1]==('computer_mix_levels',)
    w.update_computer_mix({**state,'running':False})
    assert not w.computer_sliders[first].isEnabled()
    before=list(calls);w.send_computer_level(first);assert calls==before
    w.demo=True;w.close()


def test_volume_read_failure_keeps_mix_running_and_reports_card_error(monkeypatch):
    async def scenario():
        c=Controller();states=[];c.computer_mix_changed.connect(states.append)
        def failed():raise OSError('PipeWire busy')
        c.computer_mix=SimpleNamespace(active=True,names=[LEFT,RIGHT],levels=failed)
        c.mix_members=[FIRST,SECOND]
        await c._computer_mix_levels()
        assert states[-1]['running'] and not states[-1]['error']
        assert states[-1]['levels'][FIRST]['error']
    asyncio.run(scenario())


def test_native_pair_has_vertical_volume_controls_without_opening_speaker_page(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from speakerstudio.ui import Window
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents();w.navigate('party')
    host=w.group_host
    assert set(w.member_sliders)=={host,'demo-1'}
    assert all(s.orientation()==Qt.Vertical for s in w.member_sliders.values())
    calls=[];c.submit=lambda *args:calls.append(args);w.demo=False
    w.member_sliders['demo-1'].setValue(47)
    w.member_sliders['demo-1'].sliderReleased.emit()
    assert calls[-1][:4]==('member_volume',host,'demo-1',47) and w.page=='party'
    w.demo=True;w.close()


def test_main_volume_holds_latest_request_through_old_busy_snapshots(monkeypatch):
    from copy import deepcopy
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from speakerstudio.ui import Window
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents()
    calls=[];c.submit=lambda *args:calls.append(args);w.demo=False
    selected=w.selected
    w.volume.setValue(61);w.set_volume();first_revision=calls[-1][-1]
    assert calls[-1][:3]==('volume',selected,61)
    current=deepcopy(w.devices[selected]);current.update(busy=True,operation='volume',volume=25)
    w.devices[selected]=current;w.render()
    assert w.volume.value()==61 and w.volume.isEnabled()
    w.volume.setValue(82);w.set_volume();last_revision=calls[-1][-1]
    assert last_revision!=first_revision
    current.update(busy=False,operation='',volume=61,volume_revision=first_revision);w.render()
    assert w.volume.value()==82 and w.volume_request
    current.update(busy=True,operation='volume');w.render()
    assert w.volume.value()==82
    current.update(busy=False,operation='',volume=81,volume_revision=last_revision);w.render()
    assert w.volume.value()==81 and not w.volume_request
    w.demo=True;w.close()


def test_backend_queues_volume_requests_and_acknowledges_the_correct_revision():
    async def scenario():
        c=Controller();speaker=Speaker(FIRST,'','Speaker',connected=True,volume=20)
        c.speakers[FIRST]=speaker;started=asyncio.Event();release=asyncio.Event();writes=[]
        async def volume(address,value,revision=None):
            writes.append((value,revision))
            if value==40:started.set();await release.wait()
            speaker.volume=value
        c._volume=volume
        first=asyncio.create_task(c._perform('volume',FIRST,40,'first'))
        await started.wait()
        second=asyncio.create_task(c._perform('volume',FIRST,70,'second'))
        await asyncio.sleep(0);assert writes==[(40,'first')]
        release.set();await asyncio.gather(first,second)
        assert writes==[(40,'first'),(70,'second')]
        assert speaker.volume==70 and speaker.volume_revision=='second' and not speaker.busy
    asyncio.run(scenario())



def test_main_volume_rejected_submission_restores_actual_level(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from speakerstudio.ui import Window
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents();actual=w.devices[w.selected]['volume']
    c.submit=lambda *args:False;w.demo=False
    w.volume.setValue(80);w.set_volume()
    assert w.volume_request is None and w.volume.value()==actual
    w.demo=True;w.close()


def test_native_card_volume_holds_target_until_its_own_readback(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from speakerstudio.ui import Window
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents();w.navigate('party')
    host=w.group_host;target='demo-1';calls=[];c.submit=lambda *args:calls.append(args);w.demo=False
    w.send_member_level(host,target,71);revision=calls[-1][-1]
    w.devices[host].update(busy=True,operation='member_volume');w.render_party()
    assert w.member_sliders[target].value()==71
    w.devices[target].update(volume=68,volume_revision=revision)
    w.devices[host].update(busy=False,operation='');w.render_party()
    assert w.member_sliders[target].value()==68 and target not in w.native_level_pending
    w.demo=True;w.close()
