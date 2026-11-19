"""Shared Linux/Windows PartyUp policy, without a native Bluetooth device."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from speakerstudio import backend
from speakerstudio.backend import Controller
from speakerstudio.models import Speaker
from speakerstudio.protocol import CommandError, Message

HOST='00:11:22:33:44:55'
RECEIVER='00:11:22:33:44:66'


def rig(monkeypatch,platform):
    c=Controller()
    monkeypatch.setattr(backend,'sys',SimpleNamespace(platform=platform))
    host=Speaker(HOST,'/host','Host',paired=True,connected=True,features={'group':True})
    receiver=Speaker(RECEIVER,'/receiver','Receiver',paired=True)
    c.speakers={HOST:host,RECEIVER:receiver}
    return c,host,receiver


@pytest.mark.parametrize('platform',['linux','win32'])
def test_native_switch_only_opens_host_controls(monkeypatch,platform):
    async def scenario():
        c,host,receiver=rig(monkeypatch,platform);c.loop=asyncio.get_running_loop();calls=[]
        class Session:
            closed=False
            async def request(self,command,response=0,payload=b''):
                calls.append(('wire',command,payload))
                if command==0x414:return bytes([host.broadcast,0])
                if command==0x413:host.broadcast=payload[0]
                if command==0x417:c._notification(HOST,Message(0x418,bytes.fromhex(RECEIVER.replace(':',''))+b'\0'))
        c.sessions[HOST]=Session()
        async def inventory():pass
        async def controls(address,refresh=False):
            assert address==HOST,'A receiver must not need its own control socket'
            calls.append(('controls',address))
        async def audio(address):calls.append(('audio',address))
        c.refresh_devices=inventory;c._group_controls=controls;c.bluez=SimpleNamespace(connect_audio=audio)
        async def outputs(addresses):return ['host-output']
        c._recover_group_outputs=outputs
        monkeypatch.setattr(backend,'select_output',lambda name:calls.append(('route',name)))
        await c._group_method('native',json.dumps([HOST,RECEIVER]))
        assert host.members==[RECEIVER] and host.broadcast==3 and not host.error
        assert not receiver.connected and RECEIVER not in c.sessions
        assert ('wire',0x417,bytes.fromhex(RECEIVER.replace(':',''))+b'\2') in calls
        assert ('audio',HOST) in calls if platform=='linux' else not any(row[0]=='audio' for row in calls)
    asyncio.run(scenario())


@pytest.mark.parametrize('platform',['linux','win32'])
@pytest.mark.parametrize('action',['add','group_volume'])
def test_mutations_wait_for_handoff_before_sending(monkeypatch,platform,action):
    async def scenario():
        c,host,_=rig(monkeypatch,platform);c.loop=asyncio.get_running_loop();waits=[]
        monkeypatch.setattr(backend,'time',SimpleNamespace(monotonic=lambda:10))
        async def pause(delay):waits.append(delay)
        monkeypatch.setattr(backend.asyncio,'sleep',pause)
        c.group_ready_at[HOST]=16;host.broadcast=3;host.audio_mode=0
        class Session:
            async def request(self,command,response=0,payload=b''):
                assert waits==[6]
                if command==0x414:return b'\3\0'
                if command==0x417:c._notification(HOST,Message(0x418,bytes.fromhex(RECEIVER.replace(':',''))+b'\0'))
        c.sessions[HOST]=Session()
        async def volume(*args):assert waits==[6]
        c._volume=volume
        if action=='add':await c._group_add(HOST,RECEIVER)
        else:await c._group_volume(HOST,55)
        assert waits==[6]
    asyncio.run(scenario())


@pytest.mark.parametrize('platform',['linux','win32'])
def test_selected_mode_is_not_rewritten(monkeypatch,platform):
    async def scenario():
        c,host,_=rig(monkeypatch,platform);host.broadcast=3;host.members=[RECEIVER];commands=[]
        class Session:
            async def request(self,command,response=0,payload=b''):
                commands.append(command)
                assert command==0x414,'No broadcast write for an already selected mode'
                return b'\3\x50'
        c.sessions[HOST]=Session();await c._party_mode(HOST,0x50)
        assert commands==[0x414] and host.audio_mode==0x50
    asyncio.run(scenario())


def test_third_speaker_waits_for_double_up_confirmation_and_settling(monkeypatch):
    async def scenario():
        c,host,receiver=rig(monkeypatch,'win32')
        c.loop=asyncio.get_running_loop()
        third='00:11:22:33:44:77'
        c.speakers[third]=Speaker(third,'','Third',paired=True)
        host.broadcast=3;host.members=[receiver.address]
        reads=iter([b'\3\x50',b'\3\x50',b'\3\0'])
        calls=[]
        async def pause(delay):calls.append(delay)
        monkeypatch.setattr(backend.asyncio,'sleep',pause)
        class Session:
            async def request(self,command,response=0,payload=b''):
                calls.append((command,payload))
                if command==0x414:return next(reads)
                if command==0x417:c._notification(HOST,Message(0x418,payload[:6]+b'\0'))
        c.sessions[HOST]=Session()
        await c._group_add(HOST,third)
        assert host.members==[RECEIVER,third] and host.audio_mode==0
        assert calls[:6]==[(0x414,b''),(0x413,b'\3\0'),(0x414,b''),.25,(0x414,b''),pytest.approx(6,abs=.01)]
        assert calls[6][0]==0x417
    asyncio.run(scenario())


@pytest.mark.parametrize('platform',['linux','win32'])
def test_group_sync_preserves_pre_notification_balance(monkeypatch,platform):
    async def scenario():
        c,host,_=rig(monkeypatch,platform);host.broadcast=3;host.audio_mode=0x50;host.members=[RECEIVER];host.balance=-20;commands=[]
        async def volume(*args):pass
        c._volume=volume
        class Session:
            async def request(self,command,response=0,payload=b''):
                commands.append((command,payload))
                if command==0x41b:c._notification(HOST,Message(0x19c,b'\0'))
                if command==0x19b:return b'\xec'
        c.sessions[HOST]=Session();await c._group_volume(HOST,55)
        assert commands==[(0x41b,b''),(0x19d,b'\xec'),(0x19b,b'')]
        assert host.balance==-20
    asyncio.run(scenario())


@pytest.mark.parametrize('platform',['linux','win32'])
def test_duplicate_result_is_recognized_without_reviving_removed_member(monkeypatch,platform):
    c,host,_=rig(monkeypatch,platform);host.members=[RECEIVER]
    level=bytes.fromhex(RECEIVER.replace(':',''))+b'\0\x1e\1\x10'
    assert c._notification(HOST,Message(0x421,level))
    assert c._notification(HOST,Message(0x421,level))
    assert host.member_info[RECEIVER]['volume']==52
    assert c._notification(HOST,Message(0x41a,bytes.fromhex(RECEIVER.replace(':',''))+b'\0'))
    assert c._notification(HOST,Message(0x421,level))
    assert host.members==[] and RECEIVER not in host.member_info
    assert not c._notification(HOST,Message(0x421,level[:-1]+b'\xff'))


@pytest.mark.parametrize('platform',['linux','win32'])
@pytest.mark.parametrize('operation',['join','remove','proxy'])
def test_unconfirmed_completion_invalidates_host_controls(monkeypatch,platform,operation):
    async def scenario():
        c,host,_=rig(monkeypatch,platform);c.loop=asyncio.get_running_loop();host.broadcast=3;host.audio_mode=0;commands=[]
        if operation!='join':host.members=[RECEIVER]
        class Session:
            closed=False
            def close(self):self.closed=True
            async def request(self,command,response=0,payload=b''):
                commands.append(command)
                if command==0x414:return b'\3\0'
        session=Session();c.sessions[HOST]=session
        async def expire(future,timeout):future.cancel();raise TimeoutError
        monkeypatch.setattr(backend.asyncio,'wait_for',expire)
        with pytest.raises(RuntimeError,match='Reconnect'):
            if operation=='join':await c._group_add(HOST,RECEIVER)
            elif operation=='remove':await c._group_remove(HOST,RECEIVER)
            else:await c._receiver_attribute(HOST,RECEIVER)
        assert session.closed and not host.connected and HOST not in c.sessions
        assert not c.group_waiters
        assert 0x413 not in commands,'Closing controls must not end the audio group'
    asyncio.run(scenario())


def test_busy_retry_is_bounded_and_other_rejections_are_not_retried(monkeypatch):
    async def scenario():
        c=Controller();calls=[];pauses=[]
        async def pause(delay):pauses.append(delay)
        monkeypatch.setattr(backend.asyncio,'sleep',pause)
        class Session:
            status=9
            async def request(self,command,**kwargs):calls.append(command);raise CommandError(command,self.status)
        session=Session()
        with pytest.raises(CommandError):await c._busy_request(session,0x413,b'\3\0')
        assert calls==[0x413]*3 and pauses==[.3,.6]
        calls.clear();pauses.clear();session.status=3
        with pytest.raises(CommandError):await c._busy_request(session,0x413,b'\3\0')
        assert calls==[0x413] and not pauses
    asyncio.run(scenario())


@pytest.mark.parametrize('platform',['linux','win32'])
def test_sleeping_receiver_wakes_without_requiring_its_control_socket(monkeypatch,platform):
    async def scenario():
        c,host,receiver=rig(monkeypatch,platform);c.loop=asyncio.get_running_loop();calls=[]
        receiver.sleeping=True;receiver.wake_available=True
        async def wake(address):calls.append(('wake',address));assert receiver.sleeping
        async def pause(delay):calls.append(('pause',delay))
        c.bluez=SimpleNamespace(wake=wake)
        monkeypatch.setattr(backend.asyncio,'sleep',pause)
        class Session:
            async def request(self,command,response=0,payload=b''):
                calls.append(('wire',command))
                if command==0x414:return b'\3\0'
                if command==0x417:
                    assert receiver.sleeping,'Wake write alone must not claim success'
                    c._notification(HOST,Message(0x418,bytes.fromhex(RECEIVER.replace(':',''))+b'\0'))
        c.sessions[HOST]=Session();await c._group_add(HOST,RECEIVER)
        assert calls[:2]==[('wake',RECEIVER),('pause',1)]
        assert host.members==[RECEIVER] and receiver.sleeping is False and not receiver.connected
    asyncio.run(scenario())


@pytest.mark.parametrize('platform',['linux','win32'])
def test_drag_join_releases_receiver_before_host_reconfiguration(monkeypatch,platform):
    async def scenario():
        c,host,receiver=rig(monkeypatch,platform);c.loop=asyncio.get_running_loop()
        receiver.connected=True;calls=[]
        class ReceiverSession:
            def close(self):calls.append('release receiver')
        class HostSession:
            async def request(self,command,response=0,payload=b''):
                calls.append(command)
                if command==0x414:return bytes([host.broadcast,0])
                assert RECEIVER not in c.sessions and not receiver.connected
                if command==0x413:host.broadcast=payload[0]
                if command==0x417:c._notification(HOST,Message(0x418,payload[:6]+b'\0'))
        c.sessions={HOST:HostSession(),RECEIVER:ReceiverSession()}
        await c._group_add(HOST,RECEIVER)
        assert calls.index('release receiver')<calls.index(0x413)<calls.index(0x417)
        assert host.connected and host.members==[RECEIVER] and not receiver.error
    asyncio.run(scenario())


@pytest.mark.parametrize('completion_state',['pending','completed','absent'])
def test_late_join_results_do_not_revive_members_removed_by_inventory(completion_state):
    async def scenario():
        c=Controller();host=Speaker(HOST,'','Host',connected=True,broadcast=3)
        c.speakers[HOST]=host
        result=Message(0x418,bytes.fromhex(RECEIVER.replace(':',''))+b'\0')
        future=asyncio.get_running_loop().create_future()
        if completion_state!='absent':c.group_waiters[(HOST,0x418,RECEIVER)]=future
        if completion_state=='completed':future.set_result(True)
        assert c._notification(HOST,result)
        assert host.members==([RECEIVER] if completion_state=='pending' else [])
        # A subsequent authoritative inventory reports that nobody is playing.
        assert c._notification(HOST,Message(0x416,b'\0'))
        snapshots=[];c.changed.connect(snapshots.append)
        for _ in range(3):
            assert c._notification(HOST,result),'Retransmissions still require ACKs'
            assert host.members==[]
        assert not snapshots,'Late completions must not make the cards oscillate'
    asyncio.run(scenario())


def test_flapping_inventory_retains_ordered_roster_without_claiming_playback():
    c=Controller();third='00:11:22:33:44:77'
    host=Speaker(HOST,'','Host',connected=True,broadcast=3)
    c.speakers[HOST]=host
    def inventory(rows):
        records=b''.join(bytes.fromhex(mac.replace(':',''))+bytes([60,state,0,0]) for mac,state in rows)
        assert c._notification(HOST,Message(0x416,bytes([len(rows)])+records))
    inventory([(RECEIVER,8),(third,8)])
    assert host.group_roster==[RECEIVER,third]
    for _ in range(3):
        inventory([(RECEIVER,3),(third,3)])
        assert host.members==[] and host.group_roster==[RECEIVER,third]
        inventory([(third,8),(RECEIVER,8)])
        assert host.members==[third,RECEIVER] and host.group_roster==[RECEIVER,third]
    assert c._notification(HOST,Message(0x41a,bytes.fromhex(RECEIVER.replace(':',''))+b'\0'))
    assert host.group_roster==[third] and RECEIVER not in host.members
    c.invalidate(host)
    assert host.group_roster==[] and host.members==[]


def test_rejected_join_keeps_selected_slot_without_automatic_retry(monkeypatch):
    async def scenario():
        c,host,_=rig(monkeypatch,'win32');c.loop=asyncio.get_running_loop()
        host.broadcast=3;host.audio_mode=0;commands=[]
        class Session:
            async def request(self,command,response=0,payload=b''):
                commands.append(command)
                if command==0x414:return b'\3\0'
                if command==0x417:c._notification(HOST,Message(0x418,payload[:6]+b'\4'))
        c.sessions[HOST]=Session()
        with pytest.raises(RuntimeError,match='Turn on'):
            await c._group_add(HOST,RECEIVER)
        assert host.members==[] and host.group_roster==[RECEIVER]
        assert commands==[0x414,0x417]
        await c._group_remove(HOST,RECEIVER)
        assert host.group_roster==[]
        assert commands==[0x414,0x417],'Removing an unconfirmed selection needs no radio command'
    asyncio.run(scenario())
