import asyncio
from speakerstudio.backend import Controller
from speakerstudio.models import Speaker
from speakerstudio.protocol import CommandError


class FakeSession:
    def __init__(self,unsupported32=False,busy32=False):
        self.broadcast=0;self.commands=[];self.unsupported32=unsupported32;self.busy32=busy32
    async def request(self,command,response=0,payload=b''):
        self.commands.append((command,response,payload))
        if command==0x413:self.broadcast=payload[0]
        if command==0x414:return bytes([self.broadcast,0])
        if command==0x18e:
            if self.unsupported32:raise CommandError(command,1)
            if self.busy32:raise CommandError(command,9)
        return {3:b'\x01\x06\x2d',0x175:b'\0'*4+b'\x1d'+b'\0'*7,
                0x18e:b'\x08',0x191:b'\x08',0x177:b'\x04',0x188:b'\x98\x99\xed\x2e\x51\x01',0x414:b'\x00\x00'}.get(command,b'\0'*3)


def setup(session):
    controller=Controller()
    s=Speaker('test','/test','Test',connected=True)
    controller.speakers={'test':s};controller.sessions={'test':session}
    return controller,s


def test_volume_31_and_15_step_normalization_and_fallback():
    async def scenario():
        session=FakeSession();controller,s=setup(session)
        await controller._read_state('test')
        assert s.volume_steps==31 and s.volume==26
        session=FakeSession(unsupported32=True);controller,s=setup(session)
        await controller._read_state('test')
        assert s.volume_steps==15 and s.volume==53
        assert any(c[0]==0x191 for c in session.commands)
    asyncio.run(scenario())


def test_busy_does_not_fall_back_to_wrong_volume_protocol():
    async def scenario():
        session=FakeSession(busy32=True);controller,s=setup(session)
        try:await controller._read_state('test')
        except CommandError as e:assert e.status==9
        else:raise AssertionError('Busy error swallowed')
        assert not any(c[0]==0x191 for c in session.commands)
    asyncio.run(scenario())


def test_maximum_volume_never_sends_32_or_16():
    async def scenario():
        session=FakeSession();controller,s=setup(session)
        s.volume_steps=31
        await controller._volume('test',100)
        assert session.commands[0]==(0x18d,0,b'\x1f')
        session.commands.clear();s.volume_steps=15
        await controller._volume('test',100)
        assert session.commands[0]==(0x190,0,b'\x0f')
    asyncio.run(scenario())


def test_group_add_requires_matching_completion_not_only_ack():
    from speakerstudio.protocol import Message
    async def scenario():
        host='00:11:22:33:44:55';target='00:11:22:33:44:66'
        controller=Controller();controller.loop=asyncio.get_running_loop()
        controller.speakers={a:Speaker(a,'/test',a,connected=True,features={'group':True}) for a in [host,target]}
        session=FakeSession();controller.sessions={host:session}
        task=asyncio.create_task(controller._group_add(host,target))
        await asyncio.sleep(.01)
        assert not task.done(), 'Initial ACK must not mark the receiver joined'
        assert controller.speakers[host].members==[]
        assert (0x417,0,bytes.fromhex('001122334466')+b'\0') in session.commands
        controller._notification(host,Message(0x418,bytes.fromhex('001122334466')+b'\0'))
        await task
        assert target in controller.speakers[host].members
    asyncio.run(scenario())


def test_group_failure_never_claims_membership():
    from speakerstudio.protocol import Message
    async def scenario():
        host='00:11:22:33:44:55';target='00:11:22:33:44:66'
        controller=Controller();controller.loop=asyncio.get_running_loop()
        controller.speakers={a:Speaker(a,'/test',a,connected=True,features={'group':True}) for a in [host,target]}
        controller.sessions={host:FakeSession()}
        task=asyncio.create_task(controller._group_add(host,target))
        await asyncio.sleep(.01)
        controller._notification(host,Message(0x418,bytes.fromhex('001122334466')+b'\4'))
        try:await task
        except RuntimeError as e:assert 'Turn on' in str(e)
        else:raise AssertionError('Failed group result accepted')
        assert controller.speakers[host].members==[]
        assert controller.group_waiters=={}
    asyncio.run(scenario())


def test_broadcast_records_distinguish_group_members_from_nearby():
    from speakerstudio.protocol import Message
    c,s=setup(FakeSession())
    # Nearby streaming from a different source must not appear in this group.
    nearby=bytes.fromhex('001122334466')+b'\x3c\x03\x00\x00'
    member=bytes.fromhex('001122334477')+b'\x50\x08\x00\x00'
    assert c._notification('test',Message(0x416,b'\2'+nearby+member)) is True
    assert s.members==['00:11:22:33:44:77']
    assert s.member_info['00:11:22:33:44:77']['battery']==80
    assert c._notification('test',Message(0x416,b'\2'+member)) is False
    assert s.members==['00:11:22:33:44:77']


def test_custom_eq_signed_bytes_and_preset_selection():
    async def scenario():
        session=FakeSession();c,s=setup(session)
        await c._custom_eq('test',[-128,-1,0,1,127])
        assert session.commands[0]==(0x18a,0,b'\x80\xff\x00\x01\x7f')
        assert session.commands[1]==(0x179,0,b'\x04')
        assert s.bands==[-104,-103,-19,46,81]
        for invalid in ([0]*4,[0,0,0,0,128]):
            try:await c._custom_eq('test',invalid)
            except ValueError:pass
            else:raise AssertionError('Invalid EQ accepted')
    asyncio.run(scenario())


def test_known_cpp_models_are_rejected_before_opening_legacy_transport(monkeypatch):
    import speakerstudio.backend as backend
    async def forbidden(address):
        raise AssertionError('Must not send legacy queries to a known CPP model')
    monkeypatch.setattr(backend,'rfcomm_channel',forbidden)
    async def scenario():
        for model in ['MEGABOOM 4','BOOM 4','EPICBOOM','EVERBOOM','HYPERBOOM','WONDERBOOM 4']:
            c=Controller();c.speakers={'test':Speaker('test','/test',model,paired=True)}
            try:await c._connect('test')
            except RuntimeError as e:assert 'not supported' in str(e)
            else:raise AssertionError('Unsupported model accepted')
    asyncio.run(scenario())
