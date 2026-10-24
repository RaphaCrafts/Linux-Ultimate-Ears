import asyncio
from dataclasses import asdict
import pytest
from speakerstudio.backend import Controller
from speakerstudio.models import Speaker
from speakerstudio.protocol import Message, ProtocolError, CommandError


HOST='00:11:22:33:44:55'
MEMBER='00:11:22:33:44:66'


def controller():
    c=Controller()
    s=Speaker(HOST,'/host','Host',connected=True,broadcast=3,audio_mode=0x50,members=[MEMBER],features={'balance':True})
    c.speakers[HOST]=s
    return c,s


def test_native_balance_endpoints_centre_and_confirmed_readback():
    async def scenario():
        c,s=controller()
        class Session:
            def __init__(self):self.value=0;self.writes=[];self.mode=0x50
            async def request(self,command,response=0,payload=b''):
                if command==0x414:return bytes([3,self.mode])
                if command==0x19d:self.value=payload[0];self.writes.append(payload)
                else:return bytes([self.value])
        session=Session();c.sessions[HOST]=session
        for position,expected in [(0,-128),(128,0),(255,127)]:
            await c._balance(HOST,position)
            assert s.balance==expected
        assert session.writes==[b'\x80',b'\0',b'\x7f']
        session.mode=0
        with pytest.raises(RuntimeError,match='Select Stereo'):await c._balance(HOST,0)
        assert s.audio_mode==0 and len(session.writes)==3
        s.members.append('third')
        with pytest.raises(RuntimeError):await c._balance(HOST,128)
        assert len(session.writes)==3
    asyncio.run(scenario())


def test_mode_switch_waits_for_new_receiver_handoff(monkeypatch):
    from speakerstudio import backend
    from types import SimpleNamespace
    waits=[]
    monkeypatch.setattr(backend,'time',SimpleNamespace(monotonic=lambda:10))
    async def sleep(delay):waits.append(delay)
    monkeypatch.setattr(backend.asyncio,'sleep',sleep)
    async def scenario():
        c,s=controller();c.group_ready_at[HOST]=16
        class Session:
            mode=0
            async def request(self,command,response=0,payload=b''):
                if command==0x414:return bytes([3,self.mode])
                if command==0x413:
                    assert waits==[6]
                    self.mode=payload[1]
        c.sessions[HOST]=Session()
        await c._party_mode(HOST,0x50)
        assert s.audio_mode==0x50 and waits==[6]
    asyncio.run(scenario())


def test_receiver_level_timeout_invalidates_only_its_stale_direct_controls():
    from types import SimpleNamespace
    async def scenario():
        c,host=controller()
        target=Speaker(MEMBER,'/receiver','Receiver',connected=True)
        c.speakers[MEMBER]=target
        closed=[]
        c.sessions[MEMBER]=SimpleNamespace(close=lambda:closed.append(True))
        async def read(address):
            if address==MEMBER:raise TimeoutError('stalled receiver')
            host.volume=40
        c._read_levels=read
        await c._group_levels(HOST)
        assert host.connected and host.members==[MEMBER] and host.volume==40
        assert closed and not target.connected and MEMBER not in c.sessions
        assert 'stopped responding' in host.member_info[MEMBER]['level_error']
    asyncio.run(scenario())


def test_stereo_mode_preserves_group_state_and_requires_fresh_confirmation():
    async def scenario():
        c,s=controller();s.audio_mode=0
        class Session:
            def __init__(self):self.mode=0;self.apply=True;self.writes=[]
            async def request(self,command,response=0,payload=b''):
                if command==0x414:return bytes([2,self.mode])
                if command==0x413:
                    self.writes.append(payload)
                    if self.apply:self.mode=payload[1]
        session=Session();c.sessions[HOST]=session
        await c._party_mode(HOST,0x50)
        assert session.writes==[b'\x02\x50'] and s.audio_mode==0x50
        assert s.members==[MEMBER] and s.broadcast==2
        await c._party_mode(HOST,0)
        assert s.audio_mode==0
        session.apply=False
        with pytest.raises(RuntimeError,match='did not switch'):await c._party_mode(HOST,0x50)
        assert s.audio_mode==0,'An ACK alone must not enable balance'
    asyncio.run(scenario())


def test_mode_transition_busy_read_does_not_resend_the_mode_setter():
    async def scenario():
        c,s=controller();s.audio_mode=0
        class Session:
            def __init__(self):self.mode=0;self.busy=False;self.setters=0
            async def request(self,command,response=0,payload=b''):
                if command==0x413:
                    self.mode=payload[1];self.busy=True;self.setters+=1
                elif command==0x414:
                    if self.busy:
                        self.busy=False
                        raise CommandError(command,9)
                    return bytes([3,self.mode])
        session=Session();c.sessions[HOST]=session
        await c._party_mode(HOST,0x50)
        assert session.setters==1 and s.audio_mode==0x50
    asyncio.run(scenario())


def test_proxy_level_requires_correlated_receiver_delivery_and_valid_value():
    async def scenario():
        c,s=controller();commands=[]
        class Session:
            async def request(self,command,response=0,payload=b''):
                commands.append((command,payload))
        c.sessions[HOST]=Session()
        task=asyncio.create_task(c._receiver_attribute(HOST,MEMBER))
        await asyncio.sleep(0)
        assert not task.done(),'The command ACK alone must not enable a level slider'
        prefix=bytes.fromhex(MEMBER.replace(':',''))+b'\x00\x1e\x01'
        assert not c._notification(HOST,Message(0x421,b'\0'*6+prefix[6:]+b'\x09'))
        assert not task.done()
        assert c._notification(HOST,Message(0x421,prefix+b'\x09'))
        assert await task==9 and s.member_info[MEMBER]['volume']==29
        assert commands==[(0x420,bytes.fromhex(MEMBER.replace(':',''))+b'\x00\x1e')]
        task=asyncio.create_task(c._receiver_attribute(HOST,MEMBER,8));await asyncio.sleep(0)
        assert not task.done()
        c._notification(HOST,Message(0x423,prefix))
        assert await task is True
        assert commands[-1][1].endswith(b'\x00\x1e\x08')
        task=asyncio.create_task(c._receiver_attribute(HOST,MEMBER));await asyncio.sleep(0)
        c._notification(HOST,Message(0x421,prefix+b'\xff'))
        with pytest.raises(ProtocolError):await task
        assert not c.group_waiters
        s.members=[]
        record=bytes.fromhex(MEMBER.replace(':',''))+b'\x64\x08\x01\x19'
        c._notification(HOST,Message(0x416,b'\x01'+record))
        assert 'volume' not in s.member_info[MEMBER],'Rejoining must discard the old level'
    asyncio.run(scenario())


def test_receiver_write_is_blocked_until_a_real_reading_and_after_group_loss():
    async def scenario():
        c,s=controller()
        with pytest.raises(RuntimeError):await c._member_volume(HOST,MEMBER,50)
        s.members=[]
        with pytest.raises(RuntimeError):await c._member_volume(HOST,MEMBER,50)
    asyncio.run(scenario())


def test_party_balance_large_group_levels_and_animation_states(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from speakerstudio.ui import Window
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);w.show();w.navigate('party');app.processEvents()
    host=w.devices[w.group_host]
    assert not w.balance_panel.isHidden() and w.balance_slider.isEnabled()
    w.party_action('party_mode',0)
    assert not w.balance_slider.isEnabled() and 'Select Stereo' in w.balance_readout.text()
    w.party_action('party_mode',0x50)
    assert w.balance_slider.isEnabled()
    w.balance_slider.setValue(0);w.send_balance()
    assert host['balance']==-128
    w.centre_balance();w.send_balance();assert host['balance']==0
    w.party_action('group_remove','demo-1');app.processEvents()
    assert w.party_link.mode=='ready'
    host.update(busy=True,operation='group_add',group_target='demo-1')
    w.render_party();assert w.party_link.mode=='joining' and 'Kitchen' in w.party_link.caption
    w.navigate('speaker');app.processEvents();assert not w.party_link.timer.isActive()
    host.update(busy=False,operation='',group_target='')
    w.party_action('group_add','demo-1')
    third=asdict(Speaker('demo-2','','Patio',model='boom-3',connected=True,volume=20,features={'group':True}))
    w.devices['demo-2']=third;host['members'].append('demo-2')
    w.navigate('party');w.render_party();app.processEvents()
    assert w.balance_panel.isHidden() and len(w.member_sliders)==3
    slider=w.member_sliders['demo-2'];slider.setSliderDown(True);slider.setValue(17)
    w.render_party();assert w.member_sliders['demo-2'] is slider
    slider.setSliderDown(False)
    w.send_member_level(w.group_host,'demo-2',17)
    assert host['member_info']['demo-2']['volume']==17
    for d in w.devices.values():d.update(connected=False,members=[],broadcast=0)
    w.render_party();assert w.group_host is None and w.party_link.mode=='idle'
    w.close()


def test_balance_edit_stays_smooth_through_busy_and_old_readbacks(tmp_path,monkeypatch):
    import copy
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from speakerstudio.ui import Window
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents()
    w.demo=False
    host=asdict(Speaker(HOST,'/host','Host',connected=True,broadcast=3,audio_mode=0x50,balance=0,members=[MEMBER],features={'group':True,'balance':True}))
    member=asdict(Speaker(MEMBER,'/member','Member'))
    calls=[];c.submit=lambda *args:calls.append(args)
    w.update_devices([copy.deepcopy(host),copy.deepcopy(member)]);w.navigate('party')
    card=w.party_grid.itemAt(0).widget()
    sidebar_item=w.list.item(0)
    assert w.party_mode_buttons[0x50].isChecked()
    for value in (160,190,200):
        w.balance_slider.setValue(value);w.balance_slider.sliderReleased.emit()
    assert not calls
    QTest.qWait(520)
    assert calls==[('balance',HOST,200)]
    host.update(busy=True,operation='balance')
    w.update_devices([copy.deepcopy(host),copy.deepcopy(member)])
    assert w.balance_slider.isEnabled() and w.balance_slider.value()==200
    assert w.party_grid.itemAt(0).widget() is card
    assert w.list.item(0) is sidebar_item
    w.balance_slider.setValue(240);w.balance_slider.sliderReleased.emit()
    host['balance']=72
    w.update_devices([copy.deepcopy(host),copy.deepcopy(member)])
    assert w.balance_slider.value()==240
    host.update(busy=False,operation='')
    w.update_devices([copy.deepcopy(host),copy.deepcopy(member)])
    assert w.balance_slider.value()==240
    QTest.qWait(520)
    assert calls==[('balance',HOST,200),('balance',HOST,240)]
    assert w.party_grid.itemAt(0).widget() is card
    assert w.list.item(0) is sidebar_item
    host.update(busy=True,operation='balance');w.update_devices([copy.deepcopy(host),copy.deepcopy(member)])
    host.update(busy=False,operation='',balance=112);w.update_devices([copy.deepcopy(host),copy.deepcopy(member)])
    assert w.balance_request is None and w.balance_slider.value()==240
    w.party_mode_buttons[0].click()
    assert calls[-1]==('party_mode',HOST,0)
    host['audio_mode']=0;w.update_devices([copy.deepcopy(host),copy.deepcopy(member)])
    assert w.party_mode_buttons[0].isChecked() and not w.balance_slider.isEnabled()
    w.close()


def test_unchanged_notifications_do_not_rebuild_or_emit_snapshots():
    c,s=controller();snapshots=[];c.changed.connect(snapshots.append)
    c.publish();c.publish()
    assert len(snapshots)==1
    assert c._notification(HOST,Message(0x19c,b'\xfe'))
    assert s.balance==-2 and len(snapshots)==2
    assert c._notification(HOST,Message(0x19c,b'\xfe'))
    assert len(snapshots)==2
    assert not c._notification(HOST,Message(0x19c,b'\x01\x02'))


def test_balance_waits_for_an_existing_control_operation_instead_of_dropping():
    async def scenario():
        c,s=controller();started=asyncio.Event();release=asyncio.Event();applied=[]
        async def refresh(address):started.set();await release.wait()
        async def balance(address,position):applied.append(position)
        c._refresh=refresh;c._balance=balance
        first=asyncio.create_task(c._perform('refresh',HOST));await started.wait()
        second=asyncio.create_task(c._perform('balance',HOST,180));await asyncio.sleep(0)
        assert not second.done() and not applied
        release.set();await asyncio.gather(first,second)
        assert applied==[180] and not s.busy
    asyncio.run(scenario())


def test_unsolicited_balance_is_acked_but_query_response_is_not():
    import socket
    from speakerstudio.protocol import LegacySession
    async def scenario():
        c,s=controller();client,peer=socket.socketpair();peer.setblocking(False)
        session=LegacySession(client,on_notification=lambda m:c._notification(HOST,m))
        loop=asyncio.get_running_loop()
        try:
            await loop.sock_sendall(peer,Message(0x19c,b'\xfe').encode())
            ack=await asyncio.wait_for(loop.sock_recv(peer,100),1)
            assert ack==Message(0,b'\x01\x9c\x00').encode() and s.balance==-2
            query=asyncio.create_task(session.request(0x19b,0x19c))
            assert await loop.sock_recv(peer,100)==Message(0x19b).encode()
            await loop.sock_sendall(peer,Message(0x19c,b'\0').encode())
            assert await query==b'\0'
            with pytest.raises(TimeoutError):await asyncio.wait_for(loop.sock_recv(peer,100),.03)
        finally:session.close();peer.close()
    asyncio.run(scenario())
