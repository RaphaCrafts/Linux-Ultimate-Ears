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


def output_for_address(objects,address):
    """Resolve an exact Classic address, never an alias or substring."""
    prefix='bluez_output.'+address.upper().replace(':','_')+'.'
    return next((name for name in speaker_sinks(objects) if name.upper().startswith(prefix.upper())),None)


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

    def reconcile(self):
        """Validate a running mix, or release a dead previous session's route.

        Never start a mix during discovery. Only an explicit group action may
        claim the default output. Do not interfere with another healthy instance.
        """
        if self.active:
            self.check()
            return
        rows=snapshot()
        current=configured_output(rows)
        name=(current or {}).get('value',{}).get('name','')
        if not re.fullmatch(r'speaker_studio_mix_[0-9a-f]{32}',name):return
        exists=any(o.get('info',{}).get('props',{}).get('node.name')==name for o in rows)
        if exists and len(speaker_sinks(rows))>=2:return
        # The previous process's saved output is unavailable. Clear only our
        # configured route so WirePlumber can choose an available physical sink.
        subprocess.run(['pw-metadata','-n','default','-d','0','default.configured.audio.sink'],
                       check=True,timeout=2,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=system_env())
        return True

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

    @staticmethod
    def _volume(node_id):
        output=subprocess.check_output(['wpctl','get-volume',str(node_id)],text=True,timeout=2,env={**system_env(),'LC_ALL':'C'})
        match=re.fullmatch(r'Volume:\s+(\d+(?:\.\d+)?)\s*(\[MUTED\])?\s*',output.strip())
        if not match:raise RuntimeError('Linux returned an unreadable volume level.')
        return {'volume':max(0,min(100,round(float(match[1])*100))),'muted':bool(match[2])}

    def _output_node(self,name,rows):
        if not self.active or name not in self.names:raise RuntimeError('This speaker is not in the active Computer mix.')
        if name not in speaker_sinks(rows):raise RuntimeError('The speaker audio output disconnected. Reconnect it before adjusting volume.')
        node=next(o for o in rows if o.get('type')=='PipeWire:Interface:Node' and o.get('info',{}).get('props',{}).get('node.name')==name and o.get('info',{}).get('props',{}).get('media.class')=='Audio/Sink')
        if type(node.get('id')) is not int or node['id']<0:raise RuntimeError('Invalid Linux audio output ID.')
        return node['id']

    def levels(self):
        if not self.active:return {}
        rows=snapshot()
        levels={}
        for name in self.names:
            try:levels[name]=self._volume(self._output_node(name,rows))
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
                levels[name]={'error':'Could not read this speaker’s Linux volume. Refresh to try again.'}
        return levels

    def set_volume(self,name,percent):
        if type(percent) is not int or not 0<=percent<=100:raise ValueError('Choose a volume between 0 and 100%.')
        if not self.active or name not in self.names:raise RuntimeError('This speaker is not in the active Computer mix.')
        # Resolve a fresh node ID on every change: IDs may change on reconnect.
        node_id=self._output_node(name,snapshot())
        subprocess.run(['wpctl','set-volume','--limit','1.0',str(node_id),f'{percent}%'],check=True,timeout=2,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=system_env())
        # Explicit slider adjustment also releases a mute set in Sound settings.
        subprocess.run(['wpctl','set-mute',str(node_id),'0'],check=True,timeout=2,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=system_env())
        return self._volume(node_id)

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
                rows=snapshot(timeout=1)
                current=configured_output(rows)
                # Respect a different output the user selected during playback.
                if current and current.get('value',{}).get('name')==self.node_name:
                    previous_name=(self.previous or {}).get('value',{}).get('name','')
                    # A disconnected Bluetooth output or an earlier virtual mix
                    # would leave the laptop silent again. Let policy choose.
                    available={o.get('info',{}).get('props',{}).get('node.name') for o in rows}
                    if self.previous and previous_name in available and not previous_name.startswith('speaker_studio_mix_'):
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


