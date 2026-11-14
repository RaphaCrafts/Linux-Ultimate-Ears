import asyncio
import json
from types import SimpleNamespace
import pytest
from speakerstudio.backend import Controller
from speakerstudio.models import Speaker
from speakerstudio.bluez import BlueZ,A2DP_SINK_UUID
from speakerstudio.audio_mix import output_for_address

HOST='00:11:22:33:44:55'
RECEIVER='00:11:22:33:44:66'
THIRD='00:11:22:33:44:77'


def node(address,id=1):
    return {'id':id,'type':'PipeWire:Interface:Node','info':{'props':{
        'media.class':'Audio/Sink','node.name':'bluez_output.'+address.replace(':','_')+'.1'}}}


class Mix:
    active=False
    def __init__(self,calls):self.calls=calls
    def start(self,names):self.calls.append(('start',names));self.active=True
    def stop(self):self.calls.append(('stop',));self.active=False


def setup(monkeypatch):
    c=Controller();calls=[];c.computer_mix=Mix(calls)
    monkeypatch.setattr('speakerstudio.backend.select_output',lambda name:calls.append(('route',name)))
    host=Speaker(HOST,'/host','Pink',paired=True,connected=True,audio_connected=True,broadcast=3,members=[RECEIVER],features={'group':True})
    receiver=Speaker(RECEIVER,'/receiver','Purple',paired=True,connected=False)
    c.speakers={HOST:host,RECEIVER:receiver}
    async def refresh():calls.append(('inventory',))
    async def controls(address,refresh=False):calls.append(('controls',address));c.speakers[address].connected=True
    async def ungroup(address):
        calls.append(('ungroup',address));host.broadcast=0;host.members=[]
    async def audio(address):calls.append(('audio',address));c.speakers[address].audio_connected=True
    c.refresh_devices=refresh;c._group_controls=controls;c._ungroup=ungroup
    c.bluez=SimpleNamespace(connect_audio=audio)
    monkeypatch.setattr('speakerstudio.backend.audio_snapshot',lambda:[node(HOST),node(RECEIVER,2)])
    return c,calls,host,receiver


def test_switch_connects_receiver_audio_after_ungroup_and_keeps_members(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch);states=[];c.computer_mix_changed.connect(states.append)
        c.speakers[THIRD]=Speaker(THIRD,'/third','Third',paired=True)
        monkeypatch.setattr('speakerstudio.backend.audio_snapshot',lambda:[node(HOST),node(RECEIVER,2),node(THIRD,3)])
        assert not receiver.connected and not receiver.audio_connected
        await c._group_method('computer',json.dumps([HOST,RECEIVER,THIRD]))
        assert c.computer_mix.active and not c.group_switching
        assert calls.index(('ungroup',HOST))<calls.index(('audio',RECEIVER))
        assert ('controls',RECEIVER) not in calls, 'Computer mix needs audio, not a receiver RFCOMM socket'
        assert ('audio',THIRD) in calls
        assert calls[-2]==('start',[output_for_address([node(address)],address) for address in (HOST,RECEIVER,THIRD)])
        assert states[-1]['members']==[HOST,RECEIVER,THIRD] and states[-1]['running']
        assert not states[-1]['error'] and host.members==[]
    asyncio.run(scenario())


def test_failed_receiver_connection_keeps_selection_and_allows_retry(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch);states=[];c.computer_mix_changed.connect(states.append)
        original=c.bluez.connect_audio
        async def failure(address):
            if address==RECEIVER:raise ConnectionError('Not reachable')
            await original(address)
        c.bluez.connect_audio=failure
        await c._group_method('computer',json.dumps([HOST,RECEIVER]))
        assert not c.computer_mix.active and not c.group_switching
        assert states[-1]['members']==[HOST,RECEIVER] and 'Purple' in states[-1]['error']
        assert not any(row[0]=='start' for row in calls)
        c.bluez.connect_audio=original
        await c._group_method('computer',json.dumps([HOST,RECEIVER]))
        assert states[-1]['running'] and not states[-1]['error']
    asyncio.run(scenario())


def test_native_switch_stops_mix_before_rebuilding_group(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch)
        c.computer_mix.active=True;host.broadcast=0;host.members=[]
        async def join(address,target):calls.append(('join',target));host.members.append(target);host.broadcast=3
        c._group_add=join
        await c._group_method('native',json.dumps([HOST,RECEIVER]))
        assert calls.index(('stop',))<calls.index(('join',RECEIVER))
        assert not c.computer_mix.active and host.members==[RECEIVER]
    asyncio.run(scenario())


def test_invalid_selection_does_not_break_native_playback(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch)
        await c._group_method('computer',json.dumps([HOST,RECEIVER,'unknown']))
        assert calls==[('inventory',)] and host.broadcast==3 and host.members==[RECEIVER]
        assert not c.group_switching
    asyncio.run(scenario())


def test_output_matching_uses_exact_address_not_name():
    rows=[node(HOST),node(RECEIVER,2)]
    assert output_for_address(rows,RECEIVER)==rows[1]['info']['props']['node.name']
    assert output_for_address(rows,'00:11:22:33:44:6') is None


def test_bluez_connects_a2dp_even_when_generic_link_is_already_up():
    async def scenario():
        calls=[]
        class Audio(BlueZ):
            linked=False
            async def devices(self):return [{'address':RECEIVER,'path':'/paired','paired':True,'bluez_connected':True,'audio_connected':self.linked}],[]
            async def interface(self,path,kind):assert path=='/paired';return self
            async def call_connect_profile(self,uuid):calls.append(uuid);self.linked=True
        b=Audio();await b.connect_audio(RECEIVER)
        assert calls==[A2DP_SINK_UUID]
        await b.connect_audio(RECEIVER);assert len(calls)==1
        with pytest.raises(RuntimeError,match='Pair'):await b.connect_audio('unknown')
    asyncio.run(scenario())


def test_computer_toggle_and_drag_allow_three_speakers_before_start(tmp_path,monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen');monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    from PySide6.QtWidgets import QApplication
    from speakerstudio.ui import Window
    from speakerstudio.party_visual import SpeakerDragCard
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents();w.navigate('party')
    host=w.devices[w.group_host];receiver=w.devices['demo-1']
    third={**receiver,'address':'demo-third','name':'Third'}
    w.devices[third['address']]=third
    host.update(members=[],broadcast=0);receiver.update(connected=False,audio_connected=False)
    w.render_party();w.method_buttons['computer'].click()
    assert not w.computer_mix_state['running']
    card=w.available_grid.itemAt(0).widget()
    assert isinstance(card,SpeakerDragCard)
    calls=[];c.submit=lambda *args:calls.append(args);w.demo=False
    w.join_speaker(receiver['address'])
    w.join_speaker(third['address'])
    assert calls==[] and not w.start_computer_group.isHidden()
    addresses=[host['address'],receiver['address'],third['address']]
    w.start_computer_group.click()
    assert calls==[('group_method','computer',json.dumps(addresses))]
    assert not host['members'] and w.computer_mix_state['switching']
    assert w.computer_group==addresses
    w.update_computer_mix({'running':True,'method':'computer','members':list(w.computer_group),'outputs':[],'error':'','switching':False})
    assert w.party_grid.count()==3 and not w.native_party_controls.isHidden()
    w.method_buttons['native'].click()
    assert calls[-1]==('group_method','native',json.dumps(addresses))
    w.demo=True;w.close()


def test_switch_owns_transition_before_inventory_yields(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch);entered=asyncio.Event();release=asyncio.Event()
        async def slow_inventory():entered.set();await release.wait()
        c.refresh_devices=slow_inventory
        first=asyncio.create_task(c._group_method('computer',json.dumps([HOST,RECEIVER])))
        await entered.wait()
        await c._group_method('native',json.dumps([HOST,RECEIVER]))
        assert c.group_switching and c.playback_method=='computer'
        release.set();await first
        assert c.computer_mix.active and not any(row[0]=='stop' for row in calls)
    asyncio.run(scenario())


def test_unavailable_backend_returns_mode_state_instead_of_leaving_ui_pending():
    c=Controller();states=[];c.computer_mix_changed.connect(states.append)
    c.submit('group_method','computer',json.dumps([HOST,RECEIVER]))
    assert states and not states[-1]['switching'] and states[-1]['error']


def test_toggle_native_group_keeps_receiver_without_direct_connection(tmp_path,monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen');monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    from PySide6.QtWidgets import QApplication
    from speakerstudio.ui import Window
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents();w.navigate('party')
    host=w.group_host;w.devices['demo-1'].update(connected=False,audio_connected=False)
    w.render_party();calls=[];c.submit=lambda *args:calls.append(args);w.demo=False
    w.method_buttons['computer'].click()
    assert calls==[('group_method','computer',json.dumps([host,'demo-1']))]
    assert w.computer_group==[host,'demo-1'] and w.party_grid.count()==2
    w.update_computer_mix({'method':'computer','members':[host,'demo-1'],'running':False,'switching':False,'error':'Purple could not connect','outputs':[]})
    assert not w.retry_group.isHidden() and w.party_grid.count()==2
    w.retry_group.click();assert calls[-1]==calls[0]
    w.demo=True;w.close()


def test_bluez_retries_profile_transition_instead_of_trusting_connected_flag(monkeypatch):
    async def scenario():
        calls=[];real_sleep=asyncio.sleep
        async def fast_sleep(seconds):await real_sleep(0)
        monkeypatch.setattr('speakerstudio.bluez.asyncio.sleep',fast_sleep)
        class Audio(BlueZ):
            linked=False
            async def devices(self):return [{'address':RECEIVER,'path':'/paired','paired':True,'bluez_connected':True,'audio_connected':self.linked}],[]
            async def interface(self,*args):return self
            async def call_connect_profile(self,uuid):
                calls.append(uuid)
                if len(calls)==1:raise RuntimeError('Profile transition in progress')
                self.linked=True
        b=Audio();await b.connect_audio(RECEIVER)
        assert calls==[A2DP_SINK_UUID,A2DP_SINK_UUID]
    asyncio.run(scenario())


def test_failed_native_preflight_preserves_running_mix_identity(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch);states=[];c.computer_mix_changed.connect(states.append)
        c.computer_mix.active=True;c.playback_method='computer';c.mix_members=[HOST,RECEIVER]
        await c._group_method('native',json.dumps([HOST,'not-paired']))
        assert c.computer_mix.active and c.mix_members==[HOST,RECEIVER]
        assert states[-1]['method']=='computer' and states[-1]['error']
        assert not any(row[0]=='stop' for row in calls)
    asyncio.run(scenario())


def test_native_round_trip_restores_prior_stereo_mode(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch);host.audio_mode=0x50
        await c._group_method('computer',json.dumps([HOST,RECEIVER]))
        async def join(address,target):host.members=[target];host.broadcast=3
        async def mode(address,value):calls.append(('mode',value));host.audio_mode=value
        c._group_add=join;c._party_mode=mode
        await c._group_method('native',json.dumps([HOST,RECEIVER]))
        assert ('mode',0x50) in calls and not c.computer_mix.active
    asyncio.run(scenario())


def test_computer_switch_never_probes_receiver_with_lingering_audio(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch)
        receiver.audio_connected=True;receiver.connected=True
        await c._group_method('computer',json.dumps([HOST,RECEIVER]))
        assert c.computer_mix.active
        assert ('controls',RECEIVER) not in calls
        assert not receiver.connected and not receiver.error
    asyncio.run(scenario())


def test_native_switch_explicitly_routes_audio_to_host(monkeypatch):
    monkeypatch.setattr('speakerstudio.backend.sys',SimpleNamespace(platform='linux'))
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch)
        async def join(address,target):host.members=[target];host.broadcast=3
        c._group_add=join
        await c._group_method('native',json.dumps([HOST,RECEIVER]))
        assert calls.index(('audio',HOST))<calls.index(('route',node(HOST)['info']['props']['node.name']))
    asyncio.run(scenario())


def test_missing_output_recovers_only_affected_profile_once(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch)
        monkeypatch.setattr('speakerstudio.backend.audio_snapshot',lambda:[node(HOST)])
        attempts=[]
        async def outputs(addresses):
            attempts.append(list(addresses))
            if len(attempts)==1:raise ConnectionError('Missing receiver')
            return ['host-output','receiver-output']
        async def disconnect(address):calls.append(('disconnect_audio',address))
        c._wait_group_outputs=outputs;c.bluez.disconnect_audio=disconnect
        assert await c._recover_group_outputs([HOST,RECEIVER])==['host-output','receiver-output']
        assert ('disconnect_audio',RECEIVER) in calls and ('audio',RECEIVER) in calls
        assert ('disconnect_audio',HOST) not in calls and not c.connecting
        assert len(attempts)==2
    asyncio.run(scenario())


def test_ungroup_waits_for_confirmed_standalone_before_reading_state(monkeypatch):
    async def scenario():
        c=Controller();calls=[];readings=iter([b'\x03\x00',b'\x02\x00',b'\x00\x00'])
        class Session:
            async def request(self,command,response=0,payload=b''):
                calls.append((command,payload))
                if command==0x414:return next(readings)
        c.sessions[HOST]=Session()
        async def read(address):calls.append(('read',address))
        async def sleep(delay):pass
        c._read_state=read
        monkeypatch.setattr('speakerstudio.backend.asyncio.sleep',sleep)
        await c._ungroup(HOST)
        assert calls==[(0x413,b'\0\0'),(0x414,b''),(0x414,b''),(0x414,b''),('read',HOST)]
    asyncio.run(scenario())


def test_background_reconciliation_does_not_interrupt_mode_switch(monkeypatch):
    c=Controller();c.group_switching=True
    monkeypatch.setattr(c.computer_mix,'reconcile',lambda:pytest.fail('Transition owns audio cleanup'))
    c._reconcile_computer_mix()


def test_stale_host_controls_are_reopened_before_mode_change():
    async def scenario():
        c=Controller();host=Speaker(HOST,'/host','Host',paired=True,connected=True)
        c.speakers[HOST]=host;calls=[]
        async def refresh(address):calls.append('refresh');raise RuntimeError('Stale control channel')
        async def connect(address):calls.append('connect');host.connected=True
        c._refresh=refresh;c._connect_or_wake=connect
        await c._group_controls(HOST,refresh=True)
        assert calls==['refresh','connect'] and host.connected and not host.error
    asyncio.run(scenario())


def test_bluez_profile_recovery_waits_for_disconnect_before_reconnect(monkeypatch):
    async def scenario():
        calls=[]
        class Audio(BlueZ):
            polls=0
            async def devices(self):
                self.polls+=1
                return [{'address':RECEIVER,'path':'/paired','paired':True,'audio_connected':self.polls<3}],[]
            async def interface(self,*args):return self
            async def call_disconnect_profile(self,uuid):calls.append(uuid)
        async def sleep(delay):pass
        monkeypatch.setattr('speakerstudio.bluez.asyncio.sleep',sleep)
        b=Audio();await b.disconnect_audio(RECEIVER)
        assert b.polls==3 and calls==[A2DP_SINK_UUID]
    asyncio.run(scenario())


def test_unconfirmed_ungroup_fails_without_resending_setter(monkeypatch):
    async def scenario():
        c=Controller();calls=[]
        class Session:
            async def request(self,command,response=0,payload=b''):
                calls.append(command)
                if command==0x414:return b'\x03\x00'
        c.sessions[HOST]=Session()
        async def sleep(delay):pass
        monkeypatch.setattr('speakerstudio.backend.asyncio.sleep',sleep)
        with pytest.raises(RuntimeError,match='not finished ending'):await c._ungroup(HOST)
        assert calls.count(0x413)==1 and calls.count(0x414)==20
    asyncio.run(scenario())


def test_failed_audio_profile_reopens_only_affected_device(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch)
        original=c.bluez.connect_audio
        async def audio(address):
            if address==RECEIVER:raise ConnectionError('Operation already in progress')
            await original(address)
        async def reconnect(address):
            assert address in c.connecting and not c.speakers[address].connected
            calls.append(('reconnect',address))
        c.bluez.connect_audio=audio;c.bluez.reconnect_audio=reconnect
        await c._group_method('computer',json.dumps([HOST,RECEIVER]))
        assert c.computer_mix.active and not c.mix_error
        assert calls.count(('reconnect',RECEIVER))==1 and ('reconnect',HOST) not in calls
        assert not c.connecting
    asyncio.run(scenario())


def test_computer_retry_accepts_receiver_audio_without_controls(monkeypatch):
    async def scenario():
        c,calls,host,receiver=setup(monkeypatch)
        host.broadcast=0;host.members=[]
        receiver.audio_connected=True;receiver.error='Previous control connection failed'
        await c._group_method('computer',json.dumps([HOST,RECEIVER]))
        assert c.computer_mix.active and ('controls',RECEIVER) not in calls
    asyncio.run(scenario())


def test_bluez_waits_for_in_progress_audio_handoff(monkeypatch):
    async def scenario():
        sleeps=[];calls=[]
        class Audio(BlueZ):
            async def devices(self):return [{'address':RECEIVER,'path':'/paired','paired':True,'audio_connected':len(sleeps)>=24}],[]
            async def interface(self,*args):return self
            async def call_connect_profile(self,uuid):calls.append(uuid);raise RuntimeError('InProgress')
        async def sleep(delay):sleeps.append(delay)
        monkeypatch.setattr('speakerstudio.bluez.asyncio.sleep',sleep)
        await Audio().connect_audio(RECEIVER)
        assert len(sleeps)==24 and calls==[A2DP_SINK_UUID]
    asyncio.run(scenario())


def test_bluez_reconnect_waits_for_device_release_and_keeps_pairing(monkeypatch):
    async def scenario():
        calls=[]
        class Audio(BlueZ):
            linked=True;polls=0
            async def devices(self):
                self.polls+=1
                return [{'address':RECEIVER,'path':'/paired','paired':True,'bluez_connected':self.polls<3}],[]
            async def interface(self,*args):return self
            async def call_disconnect(self):calls.append('disconnect')
            async def connect_audio(self,address):
                assert address==RECEIVER and self.polls>=3
                calls.append('audio')
        async def sleep(delay):pass
        monkeypatch.setattr('speakerstudio.bluez.asyncio.sleep',sleep)
        await Audio().reconnect_audio(RECEIVER)
        assert calls==['disconnect','audio']
    asyncio.run(scenario())
