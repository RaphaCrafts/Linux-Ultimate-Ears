"""Windows Bluetooth inventory and WinRT RFCOMM transport.

Uses the same legacy commands and validated BLE wake payload as Linux.
Pairing and audio routing stay in Windows Settings. Computer mix is Linux-only.
"""
import asyncio
import re
import time
from uuid import UUID
from winrt.runtime import init_apartment, uninit_apartment, ApartmentType

from winrt.windows.devices.bluetooth import BluetoothDevice, BluetoothCacheMode, BluetoothAdapter, BluetoothLEDevice, BluetoothError
from winrt.windows.devices.bluetooth.advertisement import BluetoothLEAdvertisementWatcher, BluetoothLEScanningMode, BluetoothLEAdvertisementWatcherStatus
from winrt.windows.devices.bluetooth.genericattributeprofile import GattCommunicationStatus, GattCharacteristicProperties, GattWriteOption
from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId
from winrt.windows.devices.enumeration import DeviceInformation
from winrt.windows.networking.sockets import StreamSocket
from winrt.windows.storage.streams import DataReader, DataWriter, InputStreamOptions
from .ble import legacy_beacon, wake_payload, LEGACY_SERVICE, WAKE_CHARACTERISTIC


def buffer_bytes(buffer):
    reader = DataReader.from_buffer(buffer)
    try:
        data = bytearray(reader.unconsumed_buffer_length)
        reader.read_bytes(data)
        return bytes(data)
    finally:
        reader.close()


def format_address(value):
    return ':'.join(f'{value:012X}'[i:i+2] for i in range(0, 12, 2))


class WindowsBluetooth:
    def __init__(self):
        self.manager = None
        self.known_models = {}
        self.recognized_addresses = set()
        self.beacons = {}
        self.service_seen = {}
        self.scan_lock = asyncio.Lock()
        self.watcher = None

    async def start(self):
        init_apartment(ApartmentType.MULTI_THREADED)
        self.manager = True

    async def devices(self):
        # Enumerate saved Classic pairings, never infer pairing from a BLE name.
        now = time.monotonic()
        self.beacons = {a:b for a,b in self.beacons.items() if now-b['seen']<45}
        infos = await DeviceInformation.find_all_async_aqs_filter(BluetoothDevice.get_device_selector_from_pairing_state(True))
        rows = []
        for info in infos:
            device = await BluetoothDevice.from_id_async(info.id)
            if device is None:
                continue
            try:
                address = format_address(device.bluetooth_address)
                if not (any(n in device.name.upper() for n in ('BOOM', 'ULTIMATE EARS')) or address in self.known_models or address in self.beacons or address in self.recognized_addresses):
                    continue
                paired = device.device_information.pairing.is_paired
                if paired:
                    self.recognized_addresses.add(address)
                rows.append(dict(address=address, path=info.id, name=device.name,
                                 # The enumeration entry describes a device
                                 # interface; its pairing flag can be False for
                                 # an actually paired Classic endpoint.
                                 paired=paired,
                                 # A2DP state is not a reliable control-link signal.
                                 bluez_connected=False, audio_connected=False,
                                 audio_active=False, sleeping=None))
            finally:
                device.close()
        for row in rows:
            beacon = self.beacons.get(row['address'])
            name = row['name'].upper().replace(' ','').replace('-','')
            model = self.known_models.get(row['address'])
            # A fresh FE61/19-byte/0x22 beacon also identifies a renamed UE
            # endpoint before its model can be read. Reject known incompatible
            # models, and require the exact writable wake UUID before sending.
            supported = (not model or model in ('megaboom-3','boom-3','boom-2')) and not any(
                n in name for n in ('BOOM4','WONDERBOOM','EPICBOOM','EVERBOOM','HYPERBOOM'))
            if beacon and row['paired'] and supported:
                row.update(wake_path=str(beacon['ble_address']), sleeping=beacon['sleeping'])
        return rows, []

    def advertisement_received(self, args):
        now = time.monotonic()
        address = args.bluetooth_address
        advertisement = args.advertisement
        self.service_seen = {a:t for a,t in self.service_seen.items() if now-t<45}
        if UUID(LEGACY_SERVICE) in advertisement.service_uuids:
            self.service_seen[address] = now
        if address not in self.service_seen:
            return
        manufacturer = {item.company_id:buffer_bytes(item.data) for item in advertisement.manufacturer_data}
        beacon = legacy_beacon({'UUIDs':[LEGACY_SERVICE], 'ManufacturerData':manufacturer})
        if beacon:
            self.beacons[beacon['classic_address']] = {**beacon, 'ble_address':address,
                'address_type':args.bluetooth_address_type, 'seen':now}

    async def scan(self, duration=12, le_only=False):
        async with self.scan_lock:
            loop = asyncio.get_running_loop()
            watcher = BluetoothLEAdvertisementWatcher()
            watcher.scanning_mode = BluetoothLEScanningMode.ACTIVE
            self.watcher = watcher
            def deliver(args):
                if self.watcher is watcher:
                    self.advertisement_received(args)
            def received(sender, args):
                if not loop.is_closed():loop.call_soon_threadsafe(deliver,args)
            token = watcher.add_received(received)
            try:
                watcher.start()
                await asyncio.sleep(duration)
                if watcher.status == BluetoothLEAdvertisementWatcherStatus.ABORTED:
                    raise RuntimeError('Windows BLE search failed. Turn on Bluetooth and check that the adapter supports Bluetooth Low Energy.')
            finally:
                self.watcher = None
                watcher.stop()
                watcher.remove_received(token)

    async def audio_streaming(self):
        # Unknown audio state: defer optional background control queries.
        return True

    async def set_alias(self, path, name):
        raise RuntimeError('Windows manages the local Bluetooth label in Settings.')

    async def wake(self, address):
        rows,_ = await self.devices()
        row = next((r for r in rows if r['address']==address),None)
        if not row or not row.get('wake_path'):
            raise RuntimeError('Search again near the speaker. Remote wake needs a recent supported BLE signal and saved Windows pairing.')
        beacon = self.beacons[address]
        if not beacon['sleeping']:
            return
        device = None
        services = []
        try:
            async with asyncio.timeout(30):
                adapter = await BluetoothAdapter.get_default_async()
                if adapter is None:
                    raise RuntimeError('No Windows Bluetooth adapter is available.')
                payload = wake_payload(format_address(adapter.bluetooth_address))
                device = await BluetoothLEDevice.from_bluetooth_address_with_bluetooth_address_type_async(
                    beacon['ble_address'],beacon['address_type'])
                if device is None:
                    raise ConnectionError('The speaker’s BLE signal is no longer reachable. Search again.')
                result = await device.get_gatt_services_with_cache_mode_async(BluetoothCacheMode.UNCACHED)
                services = list(result.services)
                if result.status != GattCommunicationStatus.SUCCESS:
                    raise ConnectionError('Windows could not access the speaker’s wake services: '+result.status.name)
                for service in services:
                    result = await service.get_characteristics_for_uuid_with_cache_mode_async(UUID(WAKE_CHARACTERISTIC),BluetoothCacheMode.UNCACHED)
                    if result.status != GattCommunicationStatus.SUCCESS:
                        continue
                    for characteristic in result.characteristics:
                        flags = characteristic.characteristic_properties
                        option = (GattWriteOption.WRITE_WITH_RESPONSE if flags & GattCharacteristicProperties.WRITE else
                                  GattWriteOption.WRITE_WITHOUT_RESPONSE if flags & GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE else None)
                        if option is None:
                            continue
                        writer = DataWriter()
                        try:
                            writer.write_bytes(payload)
                            status = await characteristic.write_value_with_option_async(writer.detach_buffer(),option)
                        finally:
                            writer.close()
                        if status != GattCommunicationStatus.SUCCESS:
                            raise ConnectionError('Windows could not send remote wake: '+status.name)
                        self.beacons.pop(address,None)
                        return
                raise RuntimeError('The speaker did not expose its writable wake characteristic. Check Bluetooth Smart in the UE phone app.')
        finally:
            for service in services:service.close()
            if device is not None:device.close()

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
        if result.error != BluetoothError.SUCCESS:
            raise ConnectionError('Windows could not discover the speaker control service: '+result.error.name)
        if len(result.services) != 1:
            for candidate in result.services:
                candidate.close()
            raise ConnectionError('Speaker control service unavailable. Turn it on, keep it nearby and close other UE apps.')
        service = result.services[0]
        socket = StreamSocket()
        await asyncio.wait_for(socket.connect_with_protection_level_async(
            service.connection_host_name, service.connection_service_name, service.protection_level), 15)
        return WindowsStream(socket, device, service)
    except BaseException:
        for resource in (socket, service, device):
            if resource is not None:
                resource.close()
        raise
