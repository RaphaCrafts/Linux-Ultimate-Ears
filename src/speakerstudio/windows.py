"""Windows Bluetooth inventory and WinRT RFCOMM transport.

Uses the same legacy commands as Linux. Pairing and audio routing stay in
Windows Settings; BLE remote wake and PipeWire Computer mix are not exposed.
"""
import asyncio
import re
from winrt.runtime import init_apartment, uninit_apartment, ApartmentType

from winrt.windows.devices.bluetooth import BluetoothDevice, BluetoothCacheMode
from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId
from winrt.windows.devices.enumeration import DeviceInformation
from winrt.windows.networking.sockets import StreamSocket
from winrt.windows.storage.streams import DataReader, DataWriter, InputStreamOptions


def format_address(value):
    return ':'.join(f'{value:012X}'[i:i+2] for i in range(0, 12, 2))


class WindowsBluetooth:
    def __init__(self):
        self.manager = None
        self.known_models = {}

    async def start(self):
        init_apartment(ApartmentType.MULTI_THREADED)
        self.manager = True

    async def devices(self):
        # Enumerate saved Classic pairings, never infer pairing from a BLE name.
        infos = await DeviceInformation.find_all_async_aqs_filter(BluetoothDevice.get_device_selector_from_pairing_state(True))
        rows = []
        for info in infos:
            device = await BluetoothDevice.from_id_async(info.id)
            if device is None:
                continue
            try:
                address = format_address(device.bluetooth_address)
                if not (any(n in device.name.upper() for n in ('BOOM', 'ULTIMATE EARS')) or address in self.known_models):
                    continue
                rows.append(dict(address=address, path=info.id, name=device.name,
                                 paired=info.pairing.is_paired,
                                 # A2DP state is not a reliable control-link signal.
                                 bluez_connected=False, audio_connected=False,
                                 audio_active=False, sleeping=None))
            finally:
                device.close()
        return rows, []

    async def scan(self, duration=12, le_only=False):
        # Refresh paired inventory only. Users discover/pair in Windows Settings.
        await self.devices()

    async def audio_streaming(self):
        # Unknown audio state: defer optional background control queries.
        return True

    async def set_alias(self, path, name):
        raise RuntimeError('Windows manages the local Bluetooth label in Settings.')

    async def wake(self, address):
        raise RuntimeError('Remote wake is not available on Windows. Use the speaker’s power button.')

    async def connect_audio(self, address):
        raise RuntimeError('Select the speaker in Windows Sound settings.')

    async def close(self):
        if self.manager:
            uninit_apartment()
        self.manager = None


class WindowsStream:
    """Small async byte-stream adapter for the shared LegacySession codec."""
    def __init__(self, socket, device, service):
        self.socket, self.device, self.service = socket, device, service
        self.reader = DataReader(socket.input_stream)
        self.reader.input_stream_options = InputStreamOptions.PARTIAL
        self.writer = DataWriter(socket.output_stream)
        self.closed = False

    def setblocking(self, blocking):
        pass  # WinRT operations are always awaited.

    async def recv_async(self, count):
        loaded = await self.reader.load_async(count)
        buffer = bytearray(loaded)
        self.reader.read_bytes(buffer)
        return bytes(buffer)

    async def send_async(self, data):
        self.writer.write_bytes(data)
        written = await self.writer.store_async()
        if written != len(data):
            raise ConnectionError('Windows could not send the complete speaker command.')

    def close(self):
        if self.closed:
            return
        self.closed = True
        for resource in (self.socket, self.reader, self.writer, self.service, self.device):
            try:
                resource.close()
            except OSError:
                pass


async def rfcomm_channel(address):
    """Keep the controller's discovery interface; Windows resolves SPP itself."""
    if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', address):
        raise ValueError('Invalid Bluetooth address')
    return None


async def open_rfcomm(address, channel=None):
    await rfcomm_channel(address)
    device = service = socket = None
    try:
        device = await asyncio.wait_for(BluetoothDevice.from_bluetooth_address_async(int(address.replace(':', ''), 16)), 15)
        if device is None:
            raise ConnectionError('Pair the speaker in Windows Bluetooth settings first.')
        result = await asyncio.wait_for(device.get_rfcomm_services_for_id_with_cache_mode_async(
            RfcommServiceId.serial_port, BluetoothCacheMode.UNCACHED), 20)
        if len(result.services) != 1:
            for candidate in result.services:
                candidate.close()
            raise ConnectionError('Speaker control service unavailable. Turn it on, keep it nearby and close other UE apps.')
        service = result.services[0]
        socket = StreamSocket()
        await asyncio.wait_for(socket.connect_async(service.connection_host_name, service.connection_service_name), 15)
        return WindowsStream(socket, device, service)
    except BaseException:
        for resource in (socket, service, device):
            if resource is not None:
                resource.close()
        raise
