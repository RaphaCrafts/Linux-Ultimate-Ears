"""BlueZ device discovery and RFCOMM service discovery. No root helper or daemon."""
import asyncio
import os
from pathlib import Path
import re
import shutil
import sys
import time
from dbus_next import BusType, Variant, Message, MessageType
from dbus_next.aio import MessageBus

from .ble import legacy_beacon, WAKE_CHARACTERISTIC, wake_payload

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
        self.scan_finished = asyncio.Event()
        self.scan_finished.set()
        self.last_seen = {}
        self.known_models = {}

    async def start(self):
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self.bus.introspect('org.bluez', '/')
        self.manager = self.bus.get_proxy_object('org.bluez', '/', introspection).get_interface('org.freedesktop.DBus.ObjectManager')
        self.manager.on_interfaces_added(self._interfaces_added)
        self.bus.add_message_handler(self._properties_changed)
        await self.bus.call(Message(destination='org.freedesktop.DBus',path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',member='AddMatch',signature='s',body=["type='signal',sender='org.bluez',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged'"]))

    def _interfaces_added(self,path,interfaces):
        props=interfaces.get('org.bluez.Device1',{})
        if 'ManufacturerData' in props:self.last_seen[path]=time.monotonic()

    def _properties_changed(self,message):
        if (message.message_type==MessageType.SIGNAL and message.path and message.path.startswith('/org/bluez/')
                and message.interface=='org.freedesktop.DBus.Properties' and message.member=='PropertiesChanged'
                and len(message.body)==3 and message.body[0]=='org.bluez.Device1'):
            if 'ManufacturerData' in message.body[1]:
                self.last_seen[message.path]=time.monotonic()

    async def objects(self):
        return await self.manager.call_get_managed_objects()

    async def interface(self, path, interface):
        info = await self.bus.introspect('org.bluez', path)
        return self.bus.get_proxy_object('org.bluez', path, info).get_interface(interface)

    @staticmethod
    def active_audio_paths(objects):
        paths=set()
        for interfaces in objects.values():
            transport=interfaces.get('org.bluez.MediaTransport1',{})
            if transport.get('State') and transport['State'].value in ('active','pending','broadcasting') and 'Device' in transport:
                paths.add(transport['Device'].value)
        return paths

    async def audio_streaming(self):
        # Inventory is local D-Bus traffic, not a radio inquiry. On uncertainty,
        # defer optional background commands rather than risk interrupting audio.
        try:return bool(self.active_audio_paths(await self.objects()))
        except Exception:return True

    async def devices(self):
        objects = await self.objects()
        devices = []
        adapters = []
        active_audio_paths=self.active_audio_paths(objects)
        audio_paths={interfaces['org.bluez.MediaTransport1']['Device'].value for interfaces in objects.values() if 'org.bluez.MediaTransport1' in interfaces and 'Device' in interfaces['org.bluez.MediaTransport1']}
        for path, interfaces in objects.items():
            if 'org.bluez.Adapter1' in interfaces:
                adapters.append((path, {k: v.value for k, v in interfaces['org.bluez.Adapter1'].items()}))
            props = interfaces.get('org.bluez.Device1')
            if not props:
                continue
            p = {k: v.value for k, v in props.items()}
            name = p.get('Alias') or p.get('Name') or ''
            uuids = p.get('UUIDs', [])
            known_name = any(n in (name+' '+p.get('Name','')).upper() for n in ('BOOM', 'ULTIMATE EARS'))
            logitech_spp = SPP_UUID in uuids and 'v000A' in p.get('Modalias', '')
            if known_name or logitech_spp or p.get('Address') in self.known_models:
                devices.append({'address': p['Address'], 'path': path, 'name': name,
                                'paired': p.get('Paired', False), 'bluez_connected': p.get('Connected', False),
                                'adapter': p.get('Adapter',''), 'audio_connected':path in audio_paths,'audio_active':path in active_audio_paths})
        by_address={d['address']:d for d in devices}
        for path,interfaces in objects.items():
            props=interfaces.get('org.bluez.Device1')
            if not props:continue
            p={k:v.value for k,v in props.items()}
            beacon=legacy_beacon(p)
            if not beacon:continue
            row=by_address.get(beacon['classic_address'])
            # Wake only an identified, already-paired Classic speaker. Never
            # associate two radios using a similar name or a guessed MAC.
            if not row or not row['paired']:continue
            name=(row['name']+' '+p.get('Name','')).upper().replace(' ','').replace('-','')
            supported=(self.known_models.get(row['address']) in ('megaboom-3','boom-3','boom-2') or any(m in name for m in ('MEGABOOM3','BOOM3','BOOM2'))) and 'BOOM4' not in name
            fresh=time.monotonic()-self.last_seen.get(path,float('-inf'))<45
            row.update(wake_path=path if fresh and supported else '',
                       sleeping=beacon['sleeping'] if fresh else None,
                       advertised_colour=beacon['colour_code'])
        return devices, adapters

    async def scan(self, duration=12, le_only=False):
        if self.scanning:
            await asyncio.wait_for(self.scan_finished.wait(),20)
            return
        self.scanning = True
        self.scan_finished.clear()
        started = []
        try:
            _, adapters = await self.devices()
            # Classic inquiry can compete with A2DP playback on the adapter.
            transport='le' if le_only or await self.audio_streaming() else 'auto'
            if not adapters:
                raise RuntimeError('No Bluetooth adapter found. Connect an adapter and try again.')
            for path, props in adapters:
                if not props.get('Powered'):
                    properties = await self.interface(path, 'org.freedesktop.DBus.Properties')
                    await properties.call_set('org.bluez.Adapter1', 'Powered', Variant('b', True))
                adapter = await self.interface(path, 'org.bluez.Adapter1')
                await adapter.call_set_discovery_filter({'Transport':Variant('s',transport),'DuplicateData':Variant('b',True)})
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
            self.scan_finished.set()

    async def set_alias(self,path,name):
        properties=await self.interface(path,'org.freedesktop.DBus.Properties')
        await asyncio.wait_for(properties.call_set('org.bluez.Device1','Alias',Variant('s',name)),5)

    async def wake(self, classic_address):
        # Refresh first: cached manufacturer bytes are not proof of proximity.
        rows,adapters=await self.devices()
        row=next((r for r in rows if r['address']==classic_address),None)
        if not row or not row.get('wake_path') or not row['paired']:
            raise RuntimeError('Search again with the speaker nearby. Remote wake needs a recent BLE signal and a saved Linux pairing.')
        adapter=next((p for path,p in adapters if path==row.get('adapter')),None)
        if not adapter or not adapter.get('Powered'):
            raise RuntimeError('Turn on Bluetooth before waking the speaker.')
        payload=wake_payload(adapter.get('Address',''))
        if row.get('sleeping') is not True:
            # An awake unit needs only its existing Classic control channel.
            # Device.Connect() can open other profiles and change bearer.
            return
        path=row['wake_path']
        device=await self.interface(path,'org.bluez.Device1')
        await asyncio.wait_for(device.call_connect(),20)
        for _ in range(40):
            objects=await self.objects()
            for characteristic,interfaces in objects.items():
                props=interfaces.get('org.bluez.GattCharacteristic1')
                if not props or not characteristic.startswith(path+'/'):continue
                p={k:v.value for k,v in props.items()}
                if p.get('UUID','').lower()!=WAKE_CHARACTERISTIC:continue
                flags=p.get('Flags',[])
                kind='request' if 'write' in flags else 'command' if 'write-without-response' in flags else None
                if not kind:raise RuntimeError('The speaker’s wake characteristic is not writable.')
                proxy=await self.interface(characteristic,'org.bluez.GattCharacteristic1')
                await asyncio.wait_for(proxy.call_write_value(payload,{'type':Variant('s',kind)}),5)
                self.last_seen.pop(path,None)  # The pre-wake sleep beacon is now stale.
                return
            await asyncio.sleep(.25)
        raise RuntimeError('The speaker did not expose its BLE wake service. Check Bluetooth Smart in the phone app.')

    async def close(self):
        if self.bus:
            self.bus.disconnect()
