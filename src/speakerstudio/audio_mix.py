"""Temporary, process-owned PipeWire mix. No firmware or Bluetooth setters."""
import json
import re
import subprocess
import time
import uuid
import tempfile
import os
import sys
import shutil


def system_env():
    env=os.environ.copy()
    if getattr(sys,'frozen',False) or 'LD_LIBRARY_PATH_ORIG' in env:
        original=env.get('LD_LIBRARY_PATH_ORIG')
        if original is None:env.pop('LD_LIBRARY_PATH',None)
        else:env['LD_LIBRARY_PATH']=original
    for key in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QML2_IMPORT_PATH'):env.pop(key,None)
    return env


def snapshot(timeout=3):
    output=subprocess.check_output(['pw-dump'],text=True,timeout=timeout,env=system_env())
    # PipeWire 1.0.5 can append change arrays before the initial dump exits.
    # Use the initial complete inventory, rather than treating deltas as a
    # second full snapshot. The next poll takes a fresh complete inventory.
    objects,_=json.JSONDecoder().raw_decode(output.lstrip())
    if not isinstance(objects,list):raise ValueError('Invalid PipeWire inventory')
    return objects


def speaker_sinks(objects):
    result={}
    for obj in objects:
        props=obj.get('info',{}).get('props',{})
        name=props.get('node.name','')
        if (obj.get('type')=='PipeWire:Interface:Node' and props.get('media.class')=='Audio/Sink'
                and re.fullmatch(r'bluez_output\.[0-9A-Fa-f_.:]+',name)):
            result[name]=props.get('node.description',name)
    return result


def configuration(names,node_name):
    if len(names)!=2 or len(set(names))!=2:raise ValueError('Choose two different speaker outputs.')
    if any(not re.fullmatch(r'bluez_output\.[0-9A-Fa-f_.:]+',name) for name in names):
        raise ValueError('This experiment accepts only exact Bluetooth output names.')
    return {
        'combine.mode':'sink','node.name':node_name,
        'node.description':'Speaker studio · Computer mix trial',
        'combine.latency-compensate':True,
        'combine.props':{'audio.position':['FL','FR'],'node.virtual':True,'priority.session':0},
        'stream.props':{'node.passive':True},
        'stream.rules':[{'matches':[{'media.class':'Audio/Sink','node.name':name}],
                         'actions':{'create-stream':{}}} for name in names],
    }


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=1)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=1)


def configured_output(objects):
    for obj in objects:
        if obj.get('type')=='PipeWire:Interface:Metadata' and obj.get('props',{}).get('metadata.name')=='default':
            return next((m for m in obj.get('metadata',[]) if m.get('key')=='default.configured.audio.sink'),None)
    return None


class ComputerMix:
    def __init__(self):
        self.process=None;self.names=[];self.node_name='';self.previous=None
        self.selected=False;self.log=None

    @property
    def active(self):return self.process is not None

    def start(self,names):
        if self.active:raise RuntimeError('Stop the current Computer mix first.')
        if any(not shutil.which(tool) for tool in ('pw-cli','pw-dump','wpctl','pw-metadata')):raise RuntimeError('Computer mix requires PipeWire tools and WirePlumber (wpctl) installed on Linux.')
        rows=snapshot()
        if not set(names)<=speaker_sinks(rows).keys():raise RuntimeError('Connect both speakers separately in Linux Bluetooth settings, then refresh outputs.')
        self.node_name='speaker_studio_mix_'+uuid.uuid4().hex
        cfg=configuration(names,self.node_name)
        cfg['node.description']='Speaker studio · Computer mix'
        self.previous=configured_output(rows);self.names=list(names)
        self.log=tempfile.TemporaryFile(mode='w+t')
        try:
            self.process=subprocess.Popen(['pw-cli','--monitor','load-module','libpipewire-module-combine-stream',json.dumps(cfg)],stdout=subprocess.DEVNULL,stderr=self.log,env=system_env())
            deadline=time.monotonic()+5
            while True:
                if self.process.poll() is not None:
                    self.log.seek(0)
                    raise RuntimeError('Could not start Computer mix. '+self.log.read()[:300])
                rows=snapshot()
                node=next((o for o in rows if o.get('info',{}).get('props',{}).get('node.name')==self.node_name),None)
                if node:break
                if time.monotonic()>=deadline:raise RuntimeError('The Computer mix output did not appear.')
                time.sleep(.1)
            self.selected=True
            subprocess.run(['wpctl','set-default',str(node['id'])],check=True,timeout=2,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=system_env())
        except Exception:
            self.stop()
            raise

    def check(self):
        if not self.active:return
        if self.process.poll() is not None:raise RuntimeError('Computer mix stopped unexpectedly.')
        rows=snapshot()
        if not set(self.names)<=speaker_sinks(rows).keys():raise RuntimeError('A speaker audio output disconnected. Computer mix has stopped.')
        if not any(o.get('info',{}).get('props',{}).get('node.name')==self.node_name for o in rows):raise RuntimeError('The Computer mix output disappeared.')

    def stop(self):
        error=None
        try:
            if self.selected:
                current=configured_output(snapshot(timeout=1))
                # Respect a different output the user selected during playback.
                if current and current.get('value',{}).get('name')==self.node_name:
                    if self.previous:
                        command=['pw-metadata','-n','default','0','default.configured.audio.sink',json.dumps(self.previous['value']),self.previous.get('type','Spa:String:JSON')]
                    else:command=['pw-metadata','-n','default','-d','0','default.configured.audio.sink']
                    subprocess.run(command,check=True,timeout=1,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=system_env())
        except Exception as e:error=e
        finally:
            try:
                if self.process:stop(self.process)
            finally:
                self.process=None;self.selected=False;self.names=[]
                if self.log:self.log.close();self.log=None
        if error:raise RuntimeError('Computer mix stopped, but the previous output could not be restored. Choose an output in Linux Sound settings.') from error


