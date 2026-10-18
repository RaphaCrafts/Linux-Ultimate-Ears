import importlib.util
from pathlib import Path
from types import SimpleNamespace
import io
import pytest

spec=importlib.util.spec_from_file_location('computer_mix_trial',Path(__file__).parents[1]/'scripts/computer_mix_trial.py')
trial=importlib.util.module_from_spec(spec);spec.loader.exec_module(trial)
LEFT='bluez_output.00_11_22_33_44_55.1'
RIGHT='bluez_output.00_11_22_33_44_66.1'


def node(name,id=1,kind='Audio/Sink'):
    return {'id':id,'type':'PipeWire:Interface:Node','info':{'props':{'node.name':name,'media.class':kind,'node.description':name}}}


def test_discovery_only_accepts_bluetooth_audio_sinks():
    rows=[node(LEFT),node(RIGHT,2),node('alsa_output.internal'),node('bluez_input.00_11_22_33_44_55.1',kind='Audio/Source'),{}]
    assert set(trial.speaker_sinks(rows))=={LEFT,RIGHT}


def test_exact_targets_cannot_match_unrelated_outputs():
    cfg=trial.configuration([LEFT,RIGHT],'temporary-test')
    assert cfg['combine.latency-compensate'] is True
    assert [rule['matches'] for rule in cfg['stream.rules']]==[
        [{'media.class':'Audio/Sink','node.name':LEFT}],
        [{'media.class':'Audio/Sink','node.name':RIGHT}]]
    for names in ([LEFT,LEFT],[LEFT,'~bluez_output.*'],[LEFT,'other"; quit'],[LEFT]):
        with pytest.raises(ValueError):trial.configuration(names,'test')


def test_missing_speaker_prevents_module_loading(monkeypatch):
    monkeypatch.setattr(trial,'snapshot',lambda:[node(LEFT)])
    monkeypatch.setattr(trial.subprocess,'Popen',lambda *a,**kw:pytest.fail('Must not load a module with a missing speaker'))
    with pytest.raises(RuntimeError,match='Both speakers'):trial.run([LEFT,RIGHT],10)


def test_connection_loss_terminates_only_the_owned_module(monkeypatch):
    rows=iter([[node(LEFT),node(RIGHT,2)],
               [node(LEFT),node(RIGHT,2),node('speaker_studio_trial_abc',3)],
               [node(LEFT)]])
    monkeypatch.setattr(trial,'snapshot',lambda:next(rows))
    monkeypatch.setattr(trial.uuid,'uuid4',lambda:SimpleNamespace(hex='abc'))
    class Process:
        stderr=io.StringIO('');terminated=False
        def poll(self):return 0 if self.terminated else None
        def terminate(self):self.terminated=True
        def wait(self,timeout):return 0
    process=Process();commands=[]
    def popen(command,**kwargs):commands.append(command);return process
    monkeypatch.setattr(trial.subprocess,'Popen',popen)
    with pytest.raises(RuntimeError,match='disappeared'):trial.run([LEFT,RIGHT],10)
    assert process.terminated and process.stderr.closed
    assert len(commands)==1 and commands[0][:4]==['pw-cli','--monitor','load-module','libpipewire-module-combine-stream']
