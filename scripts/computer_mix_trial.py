#!/usr/bin/env python3
"""Reversible PipeWire experiment; never configures speakers or selects output.

End native PartyUp and connect both speakers separately in Linux first.
This creates a temporary output; select it manually in Sound settings.
The process owns the output, so stopping it removes the virtual sink.
"""
import argparse
import json
import re
import shutil
import subprocess
import time
import uuid


def snapshot():
    return json.loads(subprocess.check_output(['pw-dump'],text=True,timeout=8))


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
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def run(names,duration):
    if not set(names)<=speaker_sinks(snapshot()).keys():
        raise RuntimeError('Both speakers must have separate Linux audio outputs before starting.')
    node_name='speaker_studio_trial_'+uuid.uuid4().hex
    args=json.dumps(configuration(names,node_name),ensure_ascii=True)
    process=subprocess.Popen(['pw-cli','--monitor','load-module','libpipewire-module-combine-stream',args],
                             stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+8
        while True:
            if process.poll() is not None:
                raise RuntimeError('PipeWire could not start the trial: '+process.stderr.read()[:500])
            objects=snapshot()
            if any(o.get('info',{}).get('props',{}).get('node.name')==node_name for o in objects):break
            if time.monotonic()>deadline:raise RuntimeError('The temporary audio output did not appear.')
            time.sleep(.2)
        print('Temporary output ready: Speaker studio · Computer mix trial',flush=True)
        print('Select it in Linux Sound settings. Native PartyUp must be off.',flush=True)
        print('Reported-latency compensation is enabled; audible sync and drift remain unverified.',flush=True)
        print(f'The output will be removed after {duration} seconds, or press Ctrl+C to stop.',flush=True)
        deadline=time.monotonic()+duration
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('The audio trial stopped unexpectedly.')
            if not set(names)<=speaker_sinks(snapshot()).keys():
                raise RuntimeError('A speaker output disappeared; stopping the trial.')
            time.sleep(1)
    finally:
        stop(process)
        if process.stderr:process.stderr.close()
        print('Trial process stopped. Its temporary output is removed; no persistent configuration was written.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list',action='store_true',help='List existing Bluetooth audio outputs without changing anything')
    parser.add_argument('--speakers',nargs=2,metavar='NODE_NAME')
    parser.add_argument('--duration',type=int,default=180)
    args=parser.parse_args()
    if not shutil.which('pw-cli') or not shutil.which('pw-dump'):parser.error('PipeWire command-line tools are required.')
    if args.list:
        sinks=speaker_sinks(snapshot())
        print(json.dumps(sinks,indent=2))
        if not sinks:print('No Bluetooth audio outputs. Connect the speakers separately in Linux first.')
        return 0
    if not args.speakers:parser.error('Use --list, then --speakers with two listed node names.')
    if not 10<=args.duration<=600:parser.error('Duration must be between 10 and 600 seconds.')
    try:run(args.speakers,args.duration)
    except KeyboardInterrupt:return 0
    except (RuntimeError,ValueError,subprocess.SubprocessError,OSError) as error:
        print(str(error));return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
