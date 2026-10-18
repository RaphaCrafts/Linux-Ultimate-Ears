"""NUL-terminated UTF-8 legacy speaker names."""
from .protocol import ProtocolError

# Verified phone-app limit, excluding the NUL terminator.
MAX_NAME_BYTES = 30


def encode_name(name):
    value=name.strip()
    if not value or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('Enter a speaker name without control characters.')
    data=value.encode('utf-8')
    if len(data)>MAX_NAME_BYTES:
        raise ValueError(f'Speaker names can use up to {MAX_NAME_BYTES} UTF-8 bytes.')
    return data+b'\0'


def decode_name(payload):
    end=payload.find(b'\0')
    if end<0:raise ProtocolError('Speaker name response is missing its terminator')
    try:value=payload[:end].decode('utf-8')
    except UnicodeDecodeError as error:raise ProtocolError('Speaker returned an invalid UTF-8 name') from error
    if not value or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ProtocolError('Speaker returned an invalid name')
    return value
