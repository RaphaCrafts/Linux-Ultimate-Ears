"""Windows API boundaries and the shared codec over a WinRT-style stream."""
import asyncio
import sys
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
    class Device(Resource):
        async def get_rfcomm_services_for_id_with_cache_mode_async(self, service_id, cache):
            assert service_id.as_short_id() == 0x1101
            assert cache == w.BluetoothCacheMode.UNCACHED
            return SimpleNamespace(services=[service])
    device = Device()
    async def from_address(value):
        assert value == 0x001122334455
        return device
    class Socket(Resource):
        async def connect_async(self, host, name):
            assert (host, name) == ('host', 'service')
    monkeypatch.setattr(w, 'BluetoothDevice', SimpleNamespace(from_bluetooth_address_async=from_address))
    monkeypatch.setattr(w, 'StreamSocket', Socket)
    monkeypatch.setattr(w, 'WindowsStream', lambda *args: resources.extend(args) or 'stream')
    assert asyncio.run(w.open_rfcomm('00:11:22:33:44:55')) == 'stream'
    assert resources[1:] == [device, service]
    async def fail(self, *args):raise OSError('radio unavailable')
    monkeypatch.setattr(Socket, 'connect_async', fail)
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
