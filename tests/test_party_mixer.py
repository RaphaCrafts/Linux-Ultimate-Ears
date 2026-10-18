import asyncio
from dataclasses import asdict
import pytest
from speakerstudio.backend import Controller
from speakerstudio.models import Speaker
from speakerstudio.protocol import Message, ProtocolError


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
    w.centre_balance();assert host['balance']==0
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
