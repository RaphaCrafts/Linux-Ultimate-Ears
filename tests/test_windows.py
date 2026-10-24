"""Windows API boundaries and the shared codec over a WinRT-style stream."""
import asyncio
import sys
import time
import json
from types import SimpleNamespace
import pytest
from speakerstudio.protocol import LegacySession, Message


def test_async_transport_correlates_replies_notifications_and_timeout():
    class Stream:
        def __init__(self):
            self.incoming = asyncio.Queue()
            self.writes = []
            self.closed = False
        def setblocking(self, value):pass
        def close(self):self.closed = True
        async def recv_async(self, count):return await self.incoming.get()
        async def send_async(self, data):self.writes.append(data)

    async def scenario():
        stream = Stream()
        events = []
        session = LegacySession(stream, on_notification=lambda m: events.append(m) or True)
        request = asyncio.create_task(session.request(0x16d, 0x16e))
        await asyncio.sleep(0)
        response = Message(0x16e, b'Living room').encode()
        await stream.incoming.put(response[:2])
        await stream.incoming.put(response[2:] + Message(0x443).encode())
        assert await request == b'Living room'
        assert events == [Message(0x443)]
        assert stream.writes == [Message(0x16d).encode(), Message(0, b'\x04\x43\0').encode()]
        with pytest.raises(TimeoutError):
            await session.request(0x177, 0x178, timeout=.01)
        assert session.closed and stream.closed
    asyncio.run(scenario())


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows WinRT projection')
def test_windows_spp_discovery_connect_and_failure_cleanup(monkeypatch):
    from speakerstudio import windows as w
    resources = []
    class Resource:
        closed = False
        def close(self):self.closed = True
    service = Resource()
    service.connection_host_name = 'host'
    service.connection_service_name = 'service'
    service.protection_level = 3
    class Device(Resource):
        async def get_rfcomm_services_for_id_with_cache_mode_async(self, service_id, cache):
            assert service_id.as_short_id() == 0x1101
            assert cache == w.BluetoothCacheMode.UNCACHED
            return SimpleNamespace(services=[service],error=w.BluetoothError.SUCCESS)
    device = Device()
    async def from_address(value):
        assert value == 0x001122334455
        return device
    class Socket(Resource):
        async def connect_with_protection_level_async(self, host, name, protection):
            assert (host, name) == ('host', 'service')
            assert protection == 3
    monkeypatch.setattr(w, 'BluetoothDevice', SimpleNamespace(from_bluetooth_address_async=from_address))
    monkeypatch.setattr(w, 'StreamSocket', Socket)
    monkeypatch.setattr(w, 'WindowsStream', lambda *args: resources.extend(args) or 'stream')
    assert asyncio.run(w.open_rfcomm('00:11:22:33:44:55')) == 'stream'
    assert resources[1:] == [device, service]
    async def fail(self, *args):raise OSError('radio unavailable')
    monkeypatch.setattr(Socket, 'connect_with_protection_level_async', fail)
    with pytest.raises(OSError):asyncio.run(w.open_rfcomm('00:11:22:33:44:55'))
    assert device.closed and service.closed
    with pytest.raises(ValueError):asyncio.run(w.open_rfcomm('invalid'))


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows backend selection')
def test_windows_rejects_computer_mix_before_touching_speakers():
    from speakerstudio.backend import Controller
    controller = Controller()
    states = []
    controller.computer_mix_changed.connect(states.append)
    asyncio.run(controller._perform('group_method', 'computer', 'host', 'member'))
    assert 'only on Linux' in states[-1]['error']


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows interface')
def test_windows_ui_uses_native_party_and_disables_computer_mix():
    from PySide6.QtWidgets import QApplication
    from speakerstudio.backend import Controller
    from speakerstudio.preferences import device_settings
    from speakerstudio.ui import Window
    settings = device_settings()
    settings.setValue('party/default', 'computer')
    app = QApplication.instance() or QApplication([])
    controller = Controller()
    controller.start = lambda: None
    window = Window(controller)
    try:
        app.processEvents()
        window.open_party()
        assert window.playback_method == 'native'
        assert not window.method_buttons['computer'].isEnabled()
        assert window.mode_label.text() == 'Windows'
    finally:
        window.close()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows WinRT projection')
def test_windows_inventory_uses_endpoint_pairing_and_expires_wake(monkeypatch):
    from speakerstudio import windows as w
    address='00:11:22:33:44:55'
    class Device:
        name='MEGABOOM 3'
        bluetooth_address=0x001122334455
        device_information=SimpleNamespace(pairing=SimpleNamespace(is_paired=True))
        closed=False
        def close(self):self.closed=True
    device=Device()
    async def find(selector):
        return [SimpleNamespace(id='interface',pairing=SimpleNamespace(is_paired=False))]
    async def from_id(value):return device
    monkeypatch.setattr(w,'DeviceInformation',SimpleNamespace(find_all_async_aqs_filter=find))
    monkeypatch.setattr(w,'BluetoothDevice',SimpleNamespace(get_device_selector_from_pairing_state=lambda p:'paired',from_id_async=from_id))
    backend=w.WindowsBluetooth()
    backend.beacons[address]={'seen':time.monotonic(),'ble_address':42,'sleeping':True}
    rows,_=asyncio.run(backend.devices())
    assert rows[0]['paired'] and device.closed
    assert rows[0]['sleeping'] is True and rows[0]['wake_path']=='42'
    backend.beacons[address]['seen']-=46
    rows,_=asyncio.run(backend.devices())
    assert 'wake_path' not in rows[0] and not backend.beacons
    device.name='Garden'
    rows,_=asyncio.run(backend.devices())
    assert len(rows)==1, 'Keep recognized pairings after wake even when Windows resolves a custom name'
    device.device_information.pairing.is_paired=False
    backend.beacons[address]={'seen':time.monotonic(),'ble_address':42,'sleeping':True}
    rows,_=asyncio.run(backend.devices())
    assert not rows[0]['paired'] and 'wake_path' not in rows[0]


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows BLE projection')
def test_windows_beacon_requires_valid_payload_and_service(monkeypatch):
    from speakerstudio import windows as w
    from uuid import UUID
    data=bytearray(19)
    data[2]=50;data[3]=12;data[12:18]=bytes.fromhex('001122334455');data[18]=0x22
    writer=w.DataWriter();writer.write_bytes(data);buffer=writer.detach_buffer();writer.close()
    args=SimpleNamespace(bluetooth_address=123,bluetooth_address_type=0,
        advertisement=SimpleNamespace(service_uuids=[],manufacturer_data=[SimpleNamespace(company_id=3,data=buffer)]))
    b=w.WindowsBluetooth();b.advertisement_received(args)
    assert not b.beacons
    args.advertisement.service_uuids=[UUID(w.LEGACY_SERVICE)]
    b.advertisement_received(args)
    assert b.beacons['00:11:22:33:44:55']['sleeping'] is True
    b.beacons.clear()
    args.advertisement.manufacturer_data=[SimpleNamespace(company_id=4,data=buffer)]
    b.advertisement_received(args)
    assert not b.beacons


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows GATT projection')
@pytest.mark.parametrize('write_without_response',[False,True])
def test_windows_wake_uses_exact_characteristic_host_payload_and_cleanup(monkeypatch,write_without_response):
    from speakerstudio import windows as w
    address='00:11:22:33:44:55'
    flags=w.GattCharacteristicProperties
    writes=[]
    class Characteristic:
        characteristic_properties=flags.WRITE_WITHOUT_RESPONSE if write_without_response else flags.WRITE
        async def write_value_with_option_async(self,buffer,option):
            writes.append((w.buffer_bytes(buffer),option))
            return w.GattCommunicationStatus.SUCCESS
    class Service:
        closed=False
        async def get_characteristics_for_uuid_with_cache_mode_async(self,uuid,cache):
            assert str(uuid)==w.WAKE_CHARACTERISTIC
            return SimpleNamespace(status=w.GattCommunicationStatus.SUCCESS,characteristics=[Characteristic()])
        def close(self):self.closed=True
    service=Service()
    class Device:
        closed=False
        async def get_gatt_services_with_cache_mode_async(self,cache):
            return SimpleNamespace(status=w.GattCommunicationStatus.SUCCESS,services=[service])
        def close(self):self.closed=True
    device=Device()
    async def adapter():return SimpleNamespace(bluetooth_address=0xAABBCCDDEEFF)
    async def from_address(ble,kind):
        assert (ble,kind)==(123,0)
        return device
    monkeypatch.setattr(w,'BluetoothAdapter',SimpleNamespace(get_default_async=adapter))
    monkeypatch.setattr(w,'BluetoothLEDevice',SimpleNamespace(from_bluetooth_address_with_bluetooth_address_type_async=from_address))
    b=w.WindowsBluetooth()
    async def rows():return [{'address':address,'wake_path':'123'}],[]
    b.devices=rows
    b.beacons[address]={'ble_address':123,'address_type':0,'sleeping':True,'seen':time.monotonic()}
    asyncio.run(b.wake(address))
    assert writes==[(bytes.fromhex('AABBCCDDEEFF01'),w.GattWriteOption.WRITE_WITHOUT_RESPONSE if write_without_response else w.GattWriteOption.WRITE_WITH_RESPONSE)]
    assert device.closed and service.closed and not b.beacons
    async def no_rows():return [],[]
    b.devices=no_rows
    with pytest.raises(RuntimeError,match='recent supported BLE'):asyncio.run(b.wake(address))
    assert len(writes)==1


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows interface')
def test_windows_read_existing_group_works_without_audio_inventory():
    from PySide6.QtWidgets import QApplication
    from speakerstudio.backend import Controller
    from speakerstudio.ui import Window
    app=QApplication.instance() or QApplication([])
    c=Controller();w=Window(c,demo=True);app.processEvents()
    sent=[];c.submit=lambda *args:sent.append(args)
    w.demo=False
    try:
        w.group_host=None
        w.devices[w.selected].update(connected=False,paired=True,audio_connected=False,busy=False)
        w.render_party()
        assert w.read_group_button.isEnabled()
        w.read_existing_group()
        assert sent==[('connect',w.selected)]
    finally:w.close()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows native PartyUp')
def test_windows_native_group_does_not_fail_on_linux_audio_routing():
    from speakerstudio.backend import Controller
    from speakerstudio.models import Speaker
    c=Controller();states=[];c.computer_mix_changed.connect(states.append)
    c.speakers={a:Speaker(a,'',a,paired=True,connected=True) for a in ('host','receiver')}
    async def inventory():pass
    async def controls(*args):pass
    async def join(host,receiver):c.speakers[host].members=[receiver]
    async def no_audio(*args):raise AssertionError('Windows must not call Linux audio routing')
    c.refresh_devices=inventory;c._group_controls=controls;c._group_add=join
    c.bluez=SimpleNamespace(connect_audio=no_audio)
    asyncio.run(c._group_method('native',json.dumps(['host','receiver'])))
    assert states[-1]['error']=='' and not states[-1]['switching']


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows receiver handoff')
def test_windows_join_releases_receiver_socket_without_losing_host_membership():
    from speakerstudio.backend import Controller
    from speakerstudio.models import Speaker
    async def scenario():
        host='00:11:22:33:44:55';receiver='00:11:22:33:44:66'
        c=Controller();c.loop=asyncio.get_running_loop();closed=[]
        c.speakers={a:Speaker(a,'',a,connected=True,features={'group':True}) for a in (host,receiver)}
        class HostSession:
            async def request(self,command,response=0,payload=b''):
                if command==0x414:return b'\x03\x00'
                if command==0x417:
                    c._notification(host,Message(0x418,bytes.fromhex(receiver.replace(':',''))+b'\0'))
        c.sessions={host:HostSession(),receiver:SimpleNamespace(close=lambda:closed.append(True))}
        await c._group_add(host,receiver)
        assert closed and receiver not in c.sessions and not c.speakers[receiver].connected
        assert not c.speakers[receiver].error
        assert c.speakers[host].connected and c.speakers[host].members==[receiver]
        assert c.group_ready_at[host]>time.monotonic()
    asyncio.run(scenario())


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows BLE projection')
def test_windows_cancelled_scan_stops_and_unregisters_watcher(monkeypatch):
    from speakerstudio import windows as w
    watchers=[]
    class Watcher:
        stopped=False
        removed=False
        def __init__(self):watchers.append(self)
        def add_received(self,callback):return 9
        def start(self):pass
        def stop(self):self.stopped=True
        def remove_received(self,token):assert token==9;self.removed=True
    monkeypatch.setattr(w,'BluetoothLEAdvertisementWatcher',Watcher)
    async def scenario():
        b=w.WindowsBluetooth()
        task=asyncio.create_task(b.scan(60))
        await asyncio.sleep(0)
        assert b.watcher is watchers[0]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert b.watcher is None and watchers[0].stopped and watchers[0].removed
    asyncio.run(scenario())


def test_shutdown_drains_cancelled_reader_once_before_bluetooth_close():
    from threading import Event
    from PySide6.QtWidgets import QApplication
    from speakerstudio.backend import Controller
    app=QApplication.instance() or QApplication([])
    c=Controller();started=Event();events=[]
    async def reader():
        try:await asyncio.sleep(60)
        except asyncio.CancelledError:
            await asyncio.sleep(.02)
            events.append('reader drained')
            raise
    async def close_bluetooth():events.append('Bluetooth closed')
    async def startup():
        task=asyncio.create_task(reader())
        c.sessions['test']=SimpleNamespace(close=task.cancel)
        c.bluez=SimpleNamespace(close=close_bluetooth)
        await asyncio.sleep(0)
        started.set()
        await asyncio.sleep(60)
    c._startup=startup
    c.start()
    try:
        assert started.wait(2)
    finally:c.shutdown()
    assert not c.isRunning()
    assert events==['reader drained','Bluetooth closed']
