"""Conservative decoding of the FE61 legacy beacon exposed by BlueZ.

The 19-byte manufacturer layout below was checked against both physical
MEGABOOM 3s, including an on-to-sleep transition. Reject other layouts rather
than treating the Android full-scan offsets as manufacturer offsets.
"""
import re

LEGACY_SERVICE = '0000fe61-0000-1000-8000-00805f9b34fb'
WAKE_CHARACTERISTIC = 'c6d6dc0d-07f5-47ef-9b59-630622b01fd3'
MAC_PATTERN = r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}'


def legacy_beacon(properties):
    if LEGACY_SERVICE not in [v.lower() for v in properties.get('UUIDs',[])]:
        return None
    data = properties.get('ManufacturerData',{}).get(3)
    if hasattr(data,'value'):data=data.value
    if not isinstance(data,(bytes,bytearray)) or len(data)!=19:
        return None
    # 0x22 is an observed discriminator, not a known semantic type. Other values use Generic artwork
    # and no remote-wake capability until their layout is verified.
    if data[18]!=0x22 or data[2]&127>100 or data[3]>31:
        return None
    classic = data[12:18]
    if classic in (bytes(6),b'\xff'*6) or classic[0]&1:
        return None
    return {'classic_address':':'.join(f'{v:02X}' for v in classic),
            'colour_code':int.from_bytes(data[:2],'big'),
            'sleeping':not bool(data[4]&0xe0)}


def wake_payload(host_address):
    if not re.fullmatch(MAC_PATTERN,host_address):
        raise ValueError('Bluetooth adapter address is invalid')
    return bytes.fromhex(host_address.replace(':',''))+b'\x01'
