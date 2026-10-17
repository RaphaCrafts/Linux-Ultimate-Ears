import asyncio
import socket
import pytest
from speakerstudio.protocol import Message, Decoder, LegacySession, ProtocolError, CommandError, battery_percent


def test_fragmentation_and_multiple_frames():
    frames=[Message(0x176,b'abc'),Message(0,b'\x01\x8d\x00'),Message(0x443)]
    wire=b''.join(m.encode() for m in frames)
    for split in range(len(wire)+1):
        decoder=Decoder()
        assert decoder.feed(wire[:split])+decoder.feed(wire[split:])==frames
    decoder=Decoder()
    output=[]
    for byte in wire:output+=decoder.feed(bytes([byte]))
    assert output==frames


def test_frame_bounds_and_bad_length():
    assert len(Message(65535,bytes(253)).encode())==256
    with pytest.raises(ValueError):Message(65536).encode()
    with pytest.raises(ValueError):Message(1,bytes(254)).encode()
    with pytest.raises(ProtocolError):Decoder().feed(b'\x01\x00')


@pytest.mark.parametrize('raw,expected',[(0,10),(11,10),(12,12),(19,19),(29,20),(89,80),(95,90),(96,100),(100,100)])
def test_battery_display(raw,expected):
    assert battery_percent(raw)==expected


def test_ack_correlation_and_stream_dispatch():
    async def scenario():
        client,server=socket.socketpair()
        server.setblocking(False)
        notifications=[]
        session=LegacySession(client,on_notification=notifications.append)
        async def peer():
            wire=await asyncio.get_running_loop().sock_recv(server,1024)
            assert wire==Message(0x18d,b'\x08').encode()
            # An unrelated ACK and notification must not complete this write.
            await asyncio.get_running_loop().sock_sendall(server,Message(0,b'\x01\x79\x00').encode()+Message(0x443).encode())
            await asyncio.sleep(.01)
            assert session.pending and not session.pending[2].done()
            await asyncio.get_running_loop().sock_sendall(server,Message(0,b'\x01\x8d\x00').encode())
        task=asyncio.create_task(peer())
        assert await session.request(0x18d,payload=b'\x08')==b'\x01\x8d\x00'
        await task
        assert Message(0x443) in notifications
        session.close();server.close()
    asyncio.run(scenario())


def test_timeout_invalidates_connection():
    async def scenario():
        client,server=socket.socketpair()
        session=LegacySession(client)
        with pytest.raises(TimeoutError):await session.request(0x175,0x176,timeout=.02)
        assert session.closed
        with pytest.raises(ConnectionError):await session.request(0x175,0x176)
        server.close()
    asyncio.run(scenario())


def test_unsupported_error_is_explicit():
    async def scenario():
        client,server=socket.socketpair();server.setblocking(False)
        session=LegacySession(client)
        async def peer():
            await asyncio.get_running_loop().sock_recv(server,1024)
            await asyncio.get_running_loop().sock_sendall(server,Message(0,b'\x00\x01\x01').encode())
        task=asyncio.create_task(peer())
        with pytest.raises(CommandError) as error:await session.request(1,2)
        assert error.value.status==1
        assert not session.closed
        await task;session.close();server.close()
    asyncio.run(scenario())


def test_only_processed_notifications_are_acknowledged():
    async def scenario():
        client,server=socket.socketpair();server.setblocking(False)
        session=LegacySession(client,on_notification=lambda m:m.command==0x418)
        message=Message(0x418,b'\0'*7)
        await asyncio.get_running_loop().sock_sendall(server,message.encode())
        ack=await asyncio.wait_for(asyncio.get_running_loop().sock_recv(server,1024),1)
        assert ack==Message(0,b'\x04\x18\x00').encode()
        await asyncio.get_running_loop().sock_sendall(server,Message(0x444).encode())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.get_running_loop().sock_recv(server,1024),.02)
        session.close();server.close()
    asyncio.run(scenario())
