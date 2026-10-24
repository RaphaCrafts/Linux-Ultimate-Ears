import io
import json
from types import SimpleNamespace
import pytest
from speakerstudio import audio_mix as mix

LEFT='bluez_output.00_11_22_33_44_55.1'
RIGHT='bluez_output.00_11_22_33_44_66.1'


def metadata(name):
    return {'type':'PipeWire:Interface:Metadata','props':{'metadata.name':'default'},
            'metadata':[{'key':'default.configured.audio.sink','value':{'name':name},'type':'Spa:String:JSON'}]}


def node(name,id=1):
    return {'id':id,'type':'PipeWire:Interface:Node','info':{'props':{'media.class':'Audio/Sink','node.name':name}}}


class Process:
    terminated=False
    def poll(self):return 0 if self.terminated else None
    def terminate(self):self.terminated=True
    def wait(self,timeout):return 0


def test_snapshot_accepts_appended_change_arrays(monkeypatch):
    initial=[node(LEFT)]
    text='\n'+json.dumps(initial)+'\n'+json.dumps([{'id':1,'info':{'state':'running'}}])
    monkeypatch.setattr(mix.subprocess,'check_output',lambda *a,**kw:text)
    assert mix.snapshot()==initial


def test_appimage_environment_restores_system_libraries(monkeypatch):
    monkeypatch.setenv('LD_LIBRARY_PATH','/app/bundled')
    monkeypatch.setenv('LD_LIBRARY_PATH_ORIG','/system/original')
    monkeypatch.setenv('QT_PLUGIN_PATH','/app/plugins')
    env=mix.system_env()
    assert env['LD_LIBRARY_PATH']=='/system/original' and 'QT_PLUGIN_PATH' not in env
    monkeypatch.delenv('LD_LIBRARY_PATH_ORIG');monkeypatch.setattr(mix.sys,'frozen',True,raising=False)
    assert 'LD_LIBRARY_PATH' not in mix.system_env()


def test_start_stop_selects_and_restores_output(monkeypatch):
    process=Process();calls=[]
    monkeypatch.setattr(mix.uuid,'uuid4',lambda:SimpleNamespace(hex='abc'))
    rows=iter([[node(LEFT),node(RIGHT,2),metadata('original')],
               [node(LEFT),node(RIGHT,2),node('speaker_studio_mix_abc',10)],
               [node('original',3),metadata('speaker_studio_mix_abc')]])
    monkeypatch.setattr(mix,'snapshot',lambda **kw:next(rows))
    monkeypatch.setattr(mix.subprocess,'Popen',lambda *a,**kw:process)
    monkeypatch.setattr(mix.subprocess,'run',lambda command,**kw:calls.append(command))
    monkeypatch.setattr(mix.shutil,'which',lambda name:'/usr/bin/'+name)
    c=mix.ComputerMix();c.start([LEFT,RIGHT]);assert c.active
    assert calls==[['wpctl','set-default','10']]
    c.stop()
    assert not c.active and process.terminated and c.log is None
    assert calls[-1][:5]==['pw-metadata','-n','default','0','default.configured.audio.sink']
    assert json.loads(calls[-1][5])=={'name':'original'}


def test_stop_respects_user_output_change(monkeypatch):
    c=mix.ComputerMix();c.process=Process();c.selected=True;c.node_name='ours'
    monkeypatch.setattr(mix,'snapshot',lambda **kw:[metadata('user-chosen')])
    monkeypatch.setattr(mix.subprocess,'run',lambda *a,**kw:pytest.fail('Must not override a user-selected output'))
    c.stop();assert not c.active


def test_failed_restore_still_removes_owned_process(monkeypatch):
    c=mix.ComputerMix();process=Process();c.process=process;c.selected=True
    monkeypatch.setattr(mix,'snapshot',lambda **kw:(_ for _ in ()).throw(OSError('Daemon unavailable')))
    with pytest.raises(RuntimeError,match='could not be restored'):c.stop()
    assert process.terminated and not c.active


def test_dialog_dispatch_and_native_controls_blocked(tmp_path,monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen');monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    from PySide6.QtWidgets import QApplication
    from speakerstudio.backend import Controller
    from speakerstudio.computer_mix_ui import ComputerMixDialog
    from speakerstudio.ui import Window
    app=QApplication.instance() or QApplication([])
    c=Controller();calls=[];monkeypatch.setattr(c,'submit',lambda *args:calls.append(args))
    state={'running':False,'outputs':[{'name':LEFT,'label':'First'},{'name':RIGHT,'label':'Second'}],'error':''}
    d=ComputerMixDialog(c,state=state)
    assert calls[-1]==('computer_mix_prepare',)
    assert d.start.isEnabled()
    d.start.click();assert calls[-1]==('computer_mix_start',json.dumps([LEFT,RIGHT]))
    d.update_state({**state,'running':True});assert d.stop.isEnabled() and not d.start.isEnabled()
    d.stop.click();assert calls[-1]==('computer_mix_stop',)
    w=Window(c,demo=True);app.processEvents();w.navigate('party')
    w.update_computer_mix({**state,'running':True});before=list(w.devices[w.group_host]['members'])
    w.party_action('group_remove',before[0]);assert w.devices[w.group_host]['members']==before
    assert 'Stop Computer mix' in w.notice.text()
    d.close();w.close()


def test_backend_rejects_native_group_when_mix_is_running():
    import asyncio
    from speakerstudio.backend import Controller
    from speakerstudio.models import Speaker
    async def scenario():
        c=Controller();c.computer_mix.process=Process()
        c.speakers['host']=Speaker('host','','Host',connected=True)
        errors=[];c.error.connect(errors.append)
        await c._perform('group_add','host','receiver')
        assert errors and 'Stop Computer mix' in errors[0]
        assert c.speakers['host'].broadcast==0
        c.computer_mix.process=None
    asyncio.run(scenario())


def test_backend_ends_native_group_before_starting_mix(monkeypatch):
    import asyncio
    from speakerstudio.backend import Controller
    from speakerstudio.models import Speaker
    async def scenario():
        c=Controller();states=[];calls=[];c.computer_mix_changed.connect(states.append)
        host=Speaker('00:11:22:33:44:55','','Host',connected=True,broadcast=3)
        c.speakers[host.address]=host
        async def refresh():pass
        async def read(address):calls.append('read')
        async def ungroup(address):calls.append('ungroup');host.broadcast=0
        c.refresh_devices=refresh;c._refresh=read;c._ungroup=ungroup
        monkeypatch.setattr(c.computer_mix,'start',lambda names:calls.append('start'))
        await c._computer_mix_start(json.dumps([LEFT,RIGHT]))
        assert calls==['read','ungroup','start'] and not states[-1]['error']
        host.broadcast=3
        async def failure(address):raise RuntimeError('No response')
        c._ungroup=failure;calls.clear()
        await c._computer_mix_start(json.dumps([LEFT,RIGHT]))
        assert calls==['read'] and 'Could not end native PartyUp' in states[-1]['error']
        assert not c.mix_preparing
    asyncio.run(scenario())


def test_mix_stop_remains_available_without_bluetooth_inventory():
    from speakerstudio.backend import Controller
    c=Controller();scheduled=[];errors=[];c.error.connect(errors.append)
    class Loop:
        def is_running(self):return True
        def call_soon_threadsafe(self,callback):scheduled.append(callback)
    c.loop=Loop();c.bluez=None
    c.submit('computer_mix_stop')
    assert len(scheduled)==1 and not errors
    c.submit('connect','speaker')
    assert len(scheduled)==1 and errors


@pytest.mark.parametrize('rows', [[], [node(LEFT)]])
def test_reconcile_releases_previous_session_route_without_two_speakers(monkeypatch,rows):
    name='speaker_studio_mix_'+'a'*32
    calls=[]
    monkeypatch.setattr(mix,'snapshot',lambda **kw:rows+[node(name,10),metadata(name)])
    monkeypatch.setattr(mix.subprocess,'run',lambda command,**kw:calls.append(command))
    c=mix.ComputerMix();c.reconcile()
    assert calls==[['pw-metadata','-n','default','-d','0','default.configured.audio.sink']]
    assert not c.active


def test_reconcile_leaves_healthy_other_instance_and_user_route_alone(monkeypatch):
    name='speaker_studio_mix_'+'a'*32
    monkeypatch.setattr(mix.subprocess,'run',lambda *a,**kw:pytest.fail('Must respect healthy or user routes'))
    monkeypatch.setattr(mix,'snapshot',lambda **kw:[node(LEFT),node(RIGHT),node(name),metadata(name)])
    mix.ComputerMix().reconcile()
    monkeypatch.setattr(mix,'snapshot',lambda **kw:[metadata('user-speakers')])
    mix.ComputerMix().reconcile()


def test_stop_does_not_restore_disconnected_bluetooth_output(monkeypatch):
    c=mix.ComputerMix();c.process=Process();c.selected=True;c.node_name='ours';c.previous=metadata(LEFT)['metadata'][0]
    calls=[]
    monkeypatch.setattr(mix,'snapshot',lambda **kw:[metadata('ours')])
    monkeypatch.setattr(mix.subprocess,'run',lambda command,**kw:calls.append(command))
    c.stop()
    assert calls==[['pw-metadata','-n','default','-d','0','default.configured.audio.sink']]
    assert not c.active


def test_explicit_refresh_stops_mix_and_clears_group_when_outputs_disappear(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from speakerstudio.backend import Controller
    async def scenario():
        c=Controller();c.computer_mix.process=Process();c.computer_mix.names=[LEFT,RIGHT]
        c.mix_members=['host','receiver'];c.mix_levels={'host':{'volume':50}}
        states=[];c.computer_mix_changed.connect(states.append)
        monkeypatch.setattr(mix,'snapshot',lambda **kw:[])
        async def devices():return [],[]
        c.bluez=SimpleNamespace(devices=devices)
        await c._refresh_all()
        assert not c.computer_mix.active and c.mix_members==[] and c.mix_levels=={}
        assert not states[-1]['running'] and states[-1]['members']==[]
        await c._refresh_all()  # Discovery never restarts a group.
        assert not c.computer_mix.active
    asyncio.run(scenario())


def test_uncertain_inventory_does_not_stop_active_mix(monkeypatch):
    from speakerstudio.backend import Controller
    c=Controller();c.computer_mix.process=Process();c.computer_mix.names=[LEFT,RIGHT]
    monkeypatch.setattr(mix,'snapshot',lambda **kw:(_ for _ in ()).throw(OSError('Daemon unavailable')))
    c._reconcile_computer_mix()
    assert c.computer_mix.active
    c.computer_mix.process=None


def test_automatic_mix_cleanup_resets_visible_group_method(tmp_path,monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen');monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    from PySide6.QtWidgets import QApplication
    from speakerstudio.backend import Controller
    from speakerstudio.ui import Window
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents();w.navigate('party')
    w.update_computer_mix({'running':True,'method':'computer','members':[w.group_host,'demo-1'],'outputs':[]})
    assert w.playback_method=='computer'
    w.update_computer_mix({'running':False,'method':'native','members':[],'outputs':[],'reset':True})
    assert w.playback_method=='native' and w.computer_group==[]
    assert w.method_buttons['native'].isChecked()
    w.close()


def test_disconnected_bluez_inventory_stops_even_lingering_audio_nodes(monkeypatch):
    import asyncio
    from speakerstudio.backend import Controller
    async def scenario():
        c=Controller();c.computer_mix.process=Process();c.computer_mix.names=[LEFT,RIGHT];c.computer_mix.node_name='ours'
        c.playback_method='computer';c.mix_members=['host','receiver']
        monkeypatch.setattr(mix,'snapshot',lambda **kw:[node(LEFT),node(RIGHT),node('ours')])
        async def devices():return [],[]
        c.bluez=SimpleNamespace(devices=devices)
        await c.refresh_devices()
        assert not c.computer_mix.active and c.playback_method=='native' and not c.mix_members
    asyncio.run(scenario())
