import pytest
from speakerstudio.naming import encode_name,decode_name
from speakerstudio.protocol import ProtocolError


def test_names_are_trimmed_nul_terminated_utf8_and_byte_limited():
    assert encode_name('  Café  ')==b'Caf\xc3\xa9\0'
    assert encode_name('é'*15)==('é'*15).encode()+b'\0'
    for name in ('','  ','A\0B','A\nB','é'*16,'a'*31):
        with pytest.raises(ValueError):encode_name(name)
    assert decode_name(b'Caf\xc3\xa9\0ignored')=='Café'
    for payload in (b'no terminator',b'\xff\0',b'\0',b'a\nb\0'):
        with pytest.raises(ProtocolError):decode_name(payload)
