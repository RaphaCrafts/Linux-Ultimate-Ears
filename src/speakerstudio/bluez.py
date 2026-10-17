"""BlueZ device discovery and RFCOMM service discovery. No root helper or daemon."""
import asyncio
import os
from pathlib import Path
import re
import shutil
import sys
from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

SPP_UUID = '00001101-0000-1000-8000-00805f9b34fb'


def sdp_executable():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    bundled = root / 'helpers' / 'sdptool'
    return str(bundled) if bundled.exists() else shutil.which('sdptool')


async def rfcomm_channel(address):
    if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', address):
        raise ValueError('Invalid Bluetooth address')
    binary = sdp_executable()
    if not binary:
        raise RuntimeError('Bluetooth service helper is missing. Please use the AppImage.')
    process = await asyncio.create_subprocess_exec(binary, 'search', '--bdaddr', address, 'SP',
                                                   stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE,
                                                   env={**os.environ, 'LC_ALL': 'C'})
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 20)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    channels = set(int(n) for n in re.findall(rb'Channel:\s*(\d+)', stdout))
    if process.returncode or len(channels) != 1:
        raise ConnectionError('Speaker not reachable. Turn it on, move it nearby, and close the phone app.')
    channel = channels.pop()
    if not 1 <= channel <= 30:
        raise ConnectionError('Speaker advertised an invalid control channel')
    return channel


class BlueZ:
    def __init__(self):
        self.bus = None
        self.manager = None
        self.scanning = False

    async def start(self):
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self.bus.introspect('org.bluez', '/')
        self.manager = self.bus.get_proxy_object('org.bluez', '/', introspection).get_interface('org.freedesktop.DBus.ObjectManager')

    async def objects(self):
        return await self.manager.call_get_managed_objects()

    async def interface(self, path, interface):
        info = await self.bus.introspect('org.bluez', path)
        return self.bus.get_proxy_object('org.bluez', path, info).get_interface(interface)

    async def devices(self):
        objects = await self.objects()
        devices = []
        adapters = []
        for path, interfaces in objects.items():
            if 'org.bluez.Adapter1' in interfaces:
                adapters.append((path, {k: v.value for k, v in interfaces['org.bluez.Adapter1'].items()}))
            props = interfaces.get('org.bluez.Device1')
            if not props:
                continue
            p = {k: v.value for k, v in props.items()}
            name = p.get('Alias') or p.get('Name') or ''
            uuids = p.get('UUIDs', [])
            known_name = any(n in name.upper() for n in ('BOOM', 'ULTIMATE EARS'))
            logitech_spp = SPP_UUID in uuids and 'v000A' in p.get('Modalias', '')
            if known_name or logitech_spp:
                devices.append({'address': p['Address'], 'path': path, 'name': name,
                                'paired': p.get('Paired', False), 'bluez_connected': p.get('Connected', False)})
        return devices, adapters

    async def scan(self, duration=12):
        if self.scanning:
            return
        self.scanning = True
        started = []
        try:
            _, adapters = await self.devices()
            if not adapters:
                raise RuntimeError('No Bluetooth adapter found. Connect an adapter and try again.')
            for path, props in adapters:
                if not props.get('Powered'):
                    properties = await self.interface(path, 'org.freedesktop.DBus.Properties')
                    await properties.call_set('org.bluez.Adapter1', 'Powered', Variant('b', True))
                adapter = await self.interface(path, 'org.bluez.Adapter1')
                await adapter.call_start_discovery()
                started.append(adapter)
            await asyncio.sleep(duration)
        finally:
            for adapter in started:
                try:
                    await adapter.call_stop_discovery()
                except Exception:
                    pass
            self.scanning = False

    async def close(self):
        if self.bus:
            self.bus.disconnect()
