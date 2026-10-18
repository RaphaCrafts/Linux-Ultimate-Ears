import asyncio
import time
import pytest
from dbus_next import Variant
from speakerstudio.ble import legacy_beacon, wake_payload, LEGACY_SERVICE, WAKE_CHARACTERISTIC
from speakerstudio.bluez import BlueZ

ADDRESS='02:11:22:33:44:55'
HOST='04:AA:BB:CC:DD:EE'
PATH='/org/bluez/hci0/dev_02_11_22_33_44_55'
ADAPTER='/org/bluez/hci0'


def beacon(sleeping=True):
    return bytes.fromhex('01196300')+bytes([0 if sleeping else 0x20,6])+bytes.fromhex(HOST.replace(':',''))+bytes.fromhex(ADDRESS.replace(':',''))+b'\x22'


def props(sleeping=True):
    return {'Address':ADDRESS,'Name':'MEGABOOM 3','Alias':'Living room','Paired':True,
            'Connected':False,'Adapter':ADAPTER,'UUIDs':[LEGACY_SERVICE],
            'ManufacturerData':{3:Variant('ay',beacon(sleeping))}}


def objects(sleeping=True):
    p=props(sleeping)
    return {PATH:{'org.bluez.Device1':{k:Variant('a{qv}' if k=='ManufacturerData' else 'as' if k=='UUIDs' else 'b' if isinstance(v,bool) else 's',v) for k,v in p.items()}},
            ADAPTER:{'org.bluez.Adapter1':{'Powered':Variant('b',True),'Address':Variant('s',HOST)}}}


def test_legacy_beacon_sleeping_and_strict_layout():
    assert legacy_beacon(props())=={'classic_address':ADDRESS,'colour_code':0x119,'sleeping':True}
    assert legacy_beacon(props(False))['sleeping'] is False
    for change in [dict(UUIDs=[]),dict(ManufacturerData={4:beacon()}),
                   dict(ManufacturerData={3:beacon()[:-1]}),dict(ManufacturerData={3:beacon()[:-1]+b'\x23'}),
                   dict(ManufacturerData={3:beacon()[:12]+b'\0'*6+b'\x22'})]:
        assert legacy_beacon(dict(props(),**change)) is None
    assert wake_payload(HOST)==bytes.fromhex('04aabbccddee01')
    with pytest.raises(ValueError):wake_payload('invalid')


def test_discovery_requires_fresh_exact_paired_classic_identity(monkeypatch):
    class Discovery(BlueZ):
        async def objects(self):return self.data
    async def scenario():
        b=Discovery();b.data=objects();b.last_seen[PATH]=time.monotonic()
        rows,_=await b.devices()
        assert len(rows)==1 and rows[0]['sleeping'] and rows[0]['wake_path']==PATH
        b.last_seen.clear();rows,_=await b.devices()
        assert rows[0]['sleeping'] is None and not rows[0]['wake_path']
        b.last_seen[PATH]=time.monotonic()
        b.data[PATH]['org.bluez.Device1']['Paired']=Variant('b',False)
        rows,_=await b.devices();assert not rows[0].get('wake_path')
        b.data=objects();data=beacon()[:12]+bytes.fromhex('021122334466')+b'\x22'
        b.data[PATH]['org.bluez.Device1']['ManufacturerData']=Variant('a{qv}',{3:Variant('ay',data)})
        rows,_=await b.devices();assert not rows[0].get('wake_path'),'Similar name must not merge radios'
    asyncio.run(scenario())


def test_wake_writes_only_target_characteristic_and_keeps_successful_connection():
    class Device:
        connected=False;disconnected=False
        async def call_connect(self):self.connected=True
        async def call_disconnect(self):self.disconnected=True
    class Characteristic:
        writes=[]
        async def call_write_value(self,data,options):self.writes.append((data,options['type'].value))
    class Wake(BlueZ):
        def __init__(self,flags):super().__init__();self.device=Device();self.characteristic=Characteristic();self.characteristic.writes=[];self.flags=flags
        async def devices(self):return ([{'address':ADDRESS,'paired':True,'wake_path':PATH,'adapter':ADAPTER,'bluez_connected':False}],[(ADAPTER,{'Powered':True,'Address':HOST})])
        async def interface(self,path,kind):return self.device if kind=='org.bluez.Device1' else self.characteristic
        async def objects(self):
            fields={'UUID':Variant('s',WAKE_CHARACTERISTIC),'Flags':Variant('as',self.flags)}
            return {'/org/bluez/hci0/dev_other/service1/char1':{'org.bluez.GattCharacteristic1':fields},PATH+'/service1/char1':{'org.bluez.GattCharacteristic1':fields}}
    async def scenario():
        b=Wake(['write']);await b.wake(ADDRESS)
        assert b.device.connected and not b.device.disconnected
        assert b.characteristic.writes==[(wake_payload(HOST),'request')]
        b=Wake(['write-without-response']);await b.wake(ADDRESS)
        assert b.characteristic.writes==[(wake_payload(HOST),'command')]
        b=Wake(['read'])
        with pytest.raises(RuntimeError):await b.wake(ADDRESS)
        assert not b.characteristic.writes and b.device.disconnected
    asyncio.run(scenario())
