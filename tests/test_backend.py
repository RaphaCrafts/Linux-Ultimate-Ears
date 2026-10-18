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


def test_colour_detection_is_read_only_cached_and_model_scoped():
    from speakerstudio.colours import finish_name
    class ColourSession(FakeSession):
        async def request(self,command,response=0,payload=b''):
            if command==0x1be:
                self.commands.append((command,response,payload));return b'\x04\x31'
            return await super().request(command,response,payload)
    async def scenario():
        session=ColourSession();c,s=setup(session);s.model='megaboom-3'
        await c._read_state('test');await c._read_state('test')
        assert s.colour_code==0x431 and s.colour=='Unicorn pink'
        assert [r for r in session.commands if r[0]==0x1be]==[(0x1be,0x1bf,b'')]
        assert finish_name('boom-3',0x431)==''
        assert finish_name('megaboom-3',0xffff)==''
        assert finish_name('boom-3',0x112)=='Lagoon blue'
    asyncio.run(scenario())


def test_unknown_or_unsupported_colour_does_not_prevent_controls():
    class ColourSession(FakeSession):
        def __init__(self,payload):super().__init__();self.payload=payload
        async def request(self,command,response=0,payload=b''):
            if command==0x1be:
                if self.payload is None:raise CommandError(command,1)
                return self.payload
            return await super().request(command,response,payload)
    async def scenario():
        for payload in (None,b'\xff\xff',b'\x01'):
            c,s=setup(ColourSession(payload));s.model='megaboom-3'
            await c._read_state('test')
            assert s.colour=='' and s.volume==26
    asyncio.run(scenario())


def test_bluez_link_loss_clears_group_and_releases_pending_actions():
    class ClosableSession(FakeSession):
        closed=False
        def close(self):self.closed=True
    class Devices:
        async def devices(self):
            return ([{'address':'test','path':'/test','name':'MEGABOOM 3','paired':True,
                      'bluez_connected':False,'adapter':'/adapter'}],[('/adapter',{'Powered':True})])
    async def scenario():
        session=ClosableSession();c,s=setup(session)
        s.bluez_connected=True;s.busy=True;s.broadcast=3;s.members=['other']
        c.bluez=Devices()
        waiter=asyncio.get_running_loop().create_future();c.group_waiters[('test',0x418,'other')]=waiter
        await c.refresh_devices()
        assert not s.connected and not s.busy and not s.members and s.broadcast==0
        assert s.paired, 'A disconnect must not pretend to remove a Linux pairing'
        assert session.closed and 'test' not in c.sessions and not c.group_waiters
        try:await waiter
        except ConnectionError:pass
        else:raise AssertionError('PartyUp operation was left waiting')
    asyncio.run(scenario())


def test_adapter_off_unpair_and_removed_device_invalidate_controls():
    class ClosableSession(FakeSession):
        closed=False
        def close(self):self.closed=True
    class Devices:
        def __init__(self,rows,power=True):self.rows=rows;self.power=power
        async def devices(self):return self.rows,[('/adapter',{'Powered':self.power})]
    async def scenario():
        row={'address':'test','path':'/test','name':'Speaker','paired':True,'bluez_connected':False,'adapter':'/adapter'}
        for rows,power in [([row],False),([dict(row,paired=False)],True),([],True)]:
            session=ClosableSession();c,s=setup(session);c.bluez=Devices(rows,power)
            await c.refresh_devices()
            assert not s.connected and session.closed
            if not rows or not rows[0]['paired']:assert not s.paired
        session=ClosableSession();c,s=setup(session);c.bluez=Devices([row])
        await c.refresh_devices()
        assert s.connected and not session.closed,'Initial Connected=False may be a stale profile snapshot'
        s.busy=True
        await c._perform('disconnect','test')
        assert not s.connected and not s.busy and session.closed
    asyncio.run(scenario())


def test_wake_transition_keeps_busy_state_but_adapter_off_still_invalidates():
    class ClosableSession(FakeSession):
        closed=False
        def close(self):self.closed=True
    class Devices:
        power=True
        async def devices(self):
            return ([{'address':'test','path':'/test','name':'MEGABOOM 3','paired':True,
                      'bluez_connected':False,'adapter':'/adapter'}],[('/adapter',{'Powered':self.power})])
    async def scenario():
        session=ClosableSession();c,s=setup(session);c.bluez=Devices()
        c.waking.add('test');s.busy=True;s.bluez_connected=True
        await c.refresh_devices()
        assert s.busy and s.connected and not session.closed
        c.bluez.power=False
        await c.refresh_devices()
        assert not s.busy and not s.connected and session.closed
    asyncio.run(scenario())


def test_connect_detects_sleep_without_prior_search_and_preserves_per_speaker_errors():
    class Discovery:
        async def scan(self,duration):assert duration==4
    async def scenario():
        c=Controller();c.bluez=Discovery()
        a=Speaker('a','/a','Speaker A',paired=True)
        b=Speaker('b','/b','Speaker B',paired=True)
        c.speakers={'a':a,'b':b}
        async def refresh():a.sleeping=True;a.wake_available=True
        async def wake(address):assert address=='a';a.connected=True
        async def connect(address):raise ConnectionError('A different app has the connection')
        c.refresh_devices=refresh;c._wake=wake;c._connect=connect
        await asyncio.gather(c._perform('connect','a'),c._perform('connect','b'))
        assert a.connected and not a.busy and not a.error
        assert 'different app' in b.error and not b.busy
        assert not c.operations
    asyncio.run(scenario())


def test_cancel_connection_stops_pending_task_and_clears_busy_state():
    async def scenario():
        c=Controller();s=Speaker('a','/a','Speaker',paired=True);c.speakers={'a':s}
        started=asyncio.Event();stopped=asyncio.Event()
        async def pending(address):
            started.set()
            try:await asyncio.Event().wait()
            finally:stopped.set()
        c._connect_or_wake=pending
        task=asyncio.create_task(c._perform('connect','a'));await started.wait()
        assert s.busy and s.operation=='connect'
        await c._perform('disconnect','a')
        try:await task
        except asyncio.CancelledError:pass
        assert stopped.is_set() and not s.busy and not s.connected and s.operation==''
    asyncio.run(scenario())


def test_rename_changes_speaker_then_reads_back_before_alias_sync():
    class Names(FakeSession):
        def __init__(self):super().__init__();self.name='Old name';self.closed=False
        async def request(self,command,response=0,payload=b''):
            self.commands.append((command,response,payload))
            if command==0x16f:self.name=payload[:-1].decode('utf-8');return b'\0'
            if command==0x16d:return self.name.encode()+b'\0'
    class Aliases:
        async def set_alias(self,path,name):self.value=(path,name)
    async def scenario():
        session=Names();c,s=setup(session);s.features['rename']=True;c.bluez=Aliases()
        await c._rename('test',' Café ')
        assert session.commands==[(0x16f,0,b'Caf\xc3\xa9\0'),(0x16d,0x16e,b'')]
        assert s.name==s.device_name=='Café' and c.bluez.value==('/test','Café')
        session.commands.clear()
        try:await c._rename('test','x'*31)
        except ValueError:pass
        else:raise AssertionError('Invalid name was accepted')
        assert not session.commands
    asyncio.run(scenario())
