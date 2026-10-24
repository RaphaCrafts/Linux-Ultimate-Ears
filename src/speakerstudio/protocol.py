"""Original legacy Centurion codec and serialized request transport.

See docs/protocol-research.md for APK evidence. No vendor code is included.
"""
import asyncio
from dataclasses import dataclass
import socket
import struct


class ProtocolError(Exception):
    pass


class CommandError(ProtocolError):
    def __init__(self, command, status):
        self.command, self.status = command, status
        labels = {1: 'This speaker does not support that control', 2: 'Unexpected command size',
                  3: 'Setting outside the speaker’s allowed range', 4: 'Speaker timed out',
                  5: 'Other speaker not found', 6: 'Other speaker not connected',
                  7: 'Setting unavailable', 8: 'Speaker rejected the command', 9: 'Speaker is busy'}
        super().__init__(labels.get(status, f'Speaker returned error {status}'))


@dataclass(frozen=True)
class Message:
    command: int
    payload: bytes = b''

    def encode(self):
        if not 0 <= self.command <= 65535 or len(self.payload) > 253:
            raise ValueError('Command or payload exceeds legacy frame limits')
        return bytes([len(self.payload) + 2]) + struct.pack('>H', self.command) + self.payload


class Decoder:
    """Reassembles arbitrarily split or concatenated RFCOMM stream frames."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        while self.buffer:
            length = self.buffer[0]
            if length < 2:
                raise ProtocolError('Invalid frame length from speaker')
            if len(self.buffer) < length + 1:
                break
            frame = bytes(self.buffer[1:length + 1])
            del self.buffer[:length + 1]
            messages.append(Message(int.from_bytes(frame[:2], 'big'), frame[2:]))
        return messages


def battery_percent(raw):
    if not 0 <= raw <= 100:
        raise ProtocolError('Invalid battery reading')
    if raw > 95:
        return 100
    if raw >= 90:
        return 90
    if raw >= 20:
        return raw // 10 * 10
    return raw if raw >= 12 else 10


class LegacySession:
    """One outstanding request; timeout closes the stream to prevent late-reply reuse."""
    def __init__(self, sock, on_notification=None, on_disconnect=None):
        self.sock = sock
        self.sock.setblocking(False)
        self.loop = asyncio.get_running_loop()
        self.decoder = Decoder()
        self.lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()
        self.pending = None
        self.closed = False
        self.on_notification = on_notification
        self.on_disconnect = on_disconnect
        self.reader = asyncio.create_task(self._read())

    async def send(self, message):
        if self.closed:
            raise ConnectionError('Speaker disconnected')
        async with self.write_lock:
            if hasattr(self.sock, 'send_async'):
                await self.sock.send_async(message.encode())
            else:
                await self.loop.sock_sendall(self.sock, message.encode())

    async def request(self, command, response=0, payload=b'', timeout=5):
        async with self.lock:
            future = self.loop.create_future()
            self.pending = (command, response, future)
            try:
                await self.send(Message(command, payload))
                return await asyncio.wait_for(future, timeout)
            except (TimeoutError, asyncio.CancelledError):
                self.close()
                raise
            finally:
                self.pending = None

    async def _read(self):
        try:
            while not self.closed:
                data = (await self.sock.recv_async(4096) if hasattr(self.sock, 'recv_async')
                        else await self.loop.sock_recv(self.sock, 4096))
                if not data:
                    raise ConnectionError('Speaker disconnected')
                for message in self.decoder.feed(data):
                    matched = False
                    if self.pending:
                        command, response, future = self.pending
                        if not future.done():
                            if message.command == 0 and len(message.payload) == 3:
                                ack_command = int.from_bytes(message.payload[:2], 'big')
                                if ack_command == command:
                                    status = message.payload[2]
                                    if status:
                                        future.set_exception(CommandError(command, status))
                                        matched = True
                                    elif response == 0:
                                        future.set_result(message.payload)
                                        matched = True
                            elif message.command == response:
                                future.set_result(message.payload)
                                matched = True
                    if not matched and self.on_notification:
                        processed = self.on_notification(message)
                        if processed is True and message.command != 0:
                            await self.send(Message(0, struct.pack('>H', message.command) + b'\x00'))
        except asyncio.CancelledError:
            pass
        except Exception as error:
            if self.pending and not self.pending[2].done():
                self.pending[2].set_exception(error)
            self.close()
            if self.on_disconnect:
                self.on_disconnect(str(error))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.sock.close()
        if self.reader is not asyncio.current_task():
            self.reader.cancel()
        if self.pending and not self.pending[2].done():
            self.pending[2].set_exception(ConnectionError('Speaker connection closed'))


async def open_rfcomm(address, channel):
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.setblocking(False)
    try:
        await asyncio.wait_for(asyncio.get_running_loop().sock_connect(sock, (address, channel)), 15)
        return sock
    except BaseException:
        sock.close()
        raise
