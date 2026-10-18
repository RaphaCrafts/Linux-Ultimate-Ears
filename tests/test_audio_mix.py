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
               [metadata('speaker_studio_mix_abc')]])
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
    assert not d.start.isEnabled()
    d.confirm.setChecked(True);assert d.start.isEnabled()
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


def test_backend_rejects_mix_when_native_group_is_known_active(monkeypatch):
    import asyncio
    from speakerstudio.backend import Controller
    from speakerstudio.models import Speaker
    async def scenario():
        c=Controller();states=[];c.computer_mix_changed.connect(states.append)
        c.speakers['00:11:22:33:44:55']=Speaker('00:11:22:33:44:55','','Host',connected=True,broadcast=3)
        monkeypatch.setattr(c.computer_mix,'start',lambda *a:pytest.fail('Native group must be ended first'))
        await c._computer_mix_start(json.dumps([LEFT,RIGHT]))
        assert states and 'End native PartyUp' in states[-1]['error']
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
