"""Async Bluetooth worker separated from the Qt GUI thread."""
import asyncio
from dataclasses import asdict
import socket
import json
import subprocess
import sys
import time
from PySide6.QtCore import QThread, Signal
if sys.platform == 'win32':
    from .windows import WindowsBluetooth as BlueZ, rfcomm_channel, open_rfcomm
else:
    from .bluez import BlueZ, rfcomm_channel
    from .protocol import open_rfcomm
from .models import Speaker, LEGACY_MODELS
from .colours import finish_name
from .naming import encode_name, decode_name
from .preferences import remembered_model, remembered_models
from .protocol import LegacySession, CommandError, ProtocolError, battery_percent
from .audio_mix import ComputerMix, snapshot as audio_snapshot, speaker_sinks, output_for_address


class Controller(QThread):
    changed = Signal(object)
    status = Signal(str)
    error = Signal(str)
    ready = Signal()
    computer_mix_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.loop = None
        self.bluez = None
        self.speakers = {}
        self.sessions = {}
        self.tasks = set()
        self.group_waiters = {}
        self.waking = set()
        self.connecting = set()
        self.operations = {}
        self.stopping = False
        self.last_snapshot = None
        self.computer_mix=ComputerMix()
        self.mix_outputs=[]
        self.mix_levels={}
        self.mix_preparing=False
        self.group_switching=False
        self.group_switch_task=None
        self.mix_members=[]
        self.playback_method='native'
        self.native_group_modes={}
        self.group_ready_at={}

    def run(self):
        self.stopping = False
        self.last_snapshot = None
        self.sessions.clear()
        self.group_waiters.clear()
        self.waking.clear()
        self.connecting.clear()
        self.operations.clear()
        self.group_ready_at.clear()
        self.speakers.clear()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self._startup())
        self.ready.emit()
        try:self.loop.run_forever()
        finally:
            try:self.computer_mix.stop()
            except Exception as error:self.error.emit(str(error))
        tasks = asyncio.all_tasks(self.loop)
        for task in tasks:
            if not task.cancelling():task.cancel()
        self.loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        self.loop.close()

    async def _startup(self):
        last_error = ''
        while not self.stopping:
            try:
                if not self.bluez:
                    self.bluez = BlueZ()
                    await asyncio.wait_for(self.bluez.start(),10)
                await self.refresh_devices()
                last_error = ''
            except asyncio.CancelledError:
                return
            except Exception as e:
                # A failed local inventory read is not evidence that a healthy
                # RFCOMM socket or audio link disappeared. The socket reader and
                # confirmed BlueZ state changes handle actual disconnections.
                message = f'Bluetooth is unavailable. Check that Bluetooth is enabled. {e}'
                if message!=last_error:self.error.emit(message)
                last_error = message
                if self.bluez:await self.bluez.close()
                self.bluez = None
                self._reconcile_computer_mix()
            if self.computer_mix.active and not self.group_switching:
                await self._computer_mix_levels()
            await asyncio.sleep(3)

    def submit(self, action, *args):
        mix_action=action in ('computer_mix_outputs','computer_mix_start','computer_mix_stop','computer_mix_prepare','computer_mix_levels','computer_mix_volume')
        if not self.loop or not self.loop.is_running() or not mix_action and (not self.bluez or not self.bluez.manager):
            message='Bluetooth is still starting. Please try again in a moment.'
            self.error.emit(message)
            if action=='group_method':self.publish_computer_mix(message)
            return False
        def launch():
            task = self.loop.create_task(self._perform(action, *args))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        self.loop.call_soon_threadsafe(launch)
        return True

    async def _perform(self, action, *args):
        if sys.platform == 'win32' and (action.startswith('computer_mix_') or action == 'group_method' and args[0] == 'computer'):
            self.publish_computer_mix('Computer mix is available only on Linux. Choose Native PartyUp on Windows.')
            return
        address = args[0] if not action.startswith('computer_mix_') and args and args[0] in self.speakers else None
        speaker = self.speakers.get(address)
        if action=='disconnect' and speaker:
            await self._disconnect(address)
            self.publish()
            return
        if speaker and speaker.busy:
            if action in ('balance','volume','member_volume'):
                active=self.operations.get(address)
                if active and active is not asyncio.current_task():
                    await asyncio.wait({active})
                    return await self._perform(action,*args)
            return
        if speaker:
            if action=='connect' and speaker.sleeping and speaker.wake_available:action='wake'
            if action=='connect':self.connecting.add(address)
            speaker.busy = True
            speaker.operation = action
            speaker.group_target = args[1] if action=='group_add' and len(args)>1 else ''
            speaker.error = ''
            self.operations[address] = asyncio.current_task()
            self.publish()
        try:
            if self.group_switching and self.group_switch_task is not asyncio.current_task() and action in ('group_add','group_remove','ungroup','party_mode','balance','group_volume','computer_mix_start','computer_mix_prepare','computer_mix_stop'):
                raise RuntimeError('Wait for the playback mode switch to finish.')
            if (self.computer_mix.active or self.mix_preparing) and action in ('group_add','party_mode','balance','group_volume'):
                raise RuntimeError('Stop Computer mix before using native PartyUp controls.')
            if action == 'scan':
                self.status.emit('Looking for nearby and sleeping speakers…')
                await self.bluez.scan()
                await self.refresh_devices()
                self.status.emit('Search complete. Select a speaker to connect or turn on.')
            else:
                if speaker and not speaker.connected and action not in ('connect','disconnect','wake'):
                    raise ConnectionError('Connect the speaker before changing its settings.')
                if action=='connect':await self._connect_or_wake(*args)
                else:await getattr(self, '_' + action)(*args)
        except Exception as e:
            message = str(e) or 'Could not communicate with the speaker.'
            if isinstance(e,TimeoutError):
                message = 'Speaker controls did not reply. Close other UE apps, keep the speaker nearby and try again.'
            if speaker:speaker.error=message
            self.error.emit((speaker.name+': ' if speaker else '')+message)
        finally:
            if speaker:
                if action=='connect':self.connecting.discard(address)
                if self.operations.get(address) is asyncio.current_task():
                    self.operations.pop(address,None)
                    speaker.busy = False
                    speaker.operation = ''
                    speaker.group_target = ''
                session = self.sessions.get(address)
                if session and session.closed:
                    self.sessions.pop(address, None)
                    self.invalidate(speaker)
                if action=='volume' and len(args)>2:speaker.volume_revision=args[2]
                if action=='member_volume' and len(args)>3:
                    receiver,revision=args[1],args[3]
                    speaker.member_info.setdefault(receiver,{})['volume_revision']=revision
                    target=self.speakers.get(receiver)
                    if target:target.volume_revision=revision
                self.publish()

    def publish(self):
        snapshot=[asdict(s) for s in self.speakers.values()]
        if snapshot!=self.last_snapshot:
            self.last_snapshot=snapshot
            self.changed.emit(snapshot)

    @staticmethod
    def invalidate(speaker):
        speaker.group_target = ''
        speaker.connected = False
        speaker.battery = None
        speaker.volume = None
        speaker.eq = None
        speaker.members = []
        speaker.group_status_known = False
        speaker.bands = None
        speaker.broadcast = 0
        speaker.audio_mode = None
        speaker.balance = None
        speaker.member_info = {}

    async def refresh_devices(self):
        self._reconcile_computer_mix()
        if hasattr(self.bluez,'known_models'):
            self.bluez.known_models.update(remembered_models())
            self.bluez.known_models.update({a:s.model for a,s in self.speakers.items() if s.model})
        rows, adapters = await self.bluez.devices()
        powered = {path:props.get('Powered',False) for path,props in adapters}
        present = set()
        for row in rows:
            address = row['address']
            present.add(address)
            if address not in self.speakers:
                self.speakers[address] = Speaker(address, row['path'], row['name'], paired=row['paired'],model=remembered_model(address))
            s = self.speakers[address]
            linked = row.get('bluez_connected',False)
            # Raw RFCOMM ownership is not identical to a desktop audio profile.
            # Observe an actual BlueZ link-loss transition, unpairing or adapter
            # power-off; do not discard a new control connection from a stale
            # initial Connected=False snapshot.
            lost = (s.bluez_connected and not linked and address not in self.waking and address not in self.connecting or not row['paired'] or
                    row.get('adapter') in powered and not powered[row['adapter']])
            s.paired, s.name, s.path = row['paired'], s.device_name or row['name'], row['path']
            s.bluez_connected = linked
            s.audio_connected = row.get('audio_connected',False)
            s.audio_active = row.get('audio_active',False)
            s.wake_available = bool(row.get('wake_path'))
            s.sleeping = False if s.connected else row.get('sleeping')
            if lost and (s.connected or address in self.sessions or s.busy):
                self._lost(address,'Bluetooth disconnected')
        for address,s in self.speakers.items():
            if address not in present:
                s.paired = False
                s.bluez_connected = False
                s.audio_connected = False
                s.audio_active = False
                s.wake_available = False
                s.sleeping = None
                if s.connected or address in self.sessions or s.busy:
                    self._lost(address,'Speaker is no longer available in Bluetooth')
        if self.computer_mix.active and not self.group_switching and not any(s.audio_connected for s in self.speakers.values()):
            self._stop_lost_computer_mix('No speaker audio is connected. Computer mix has stopped.')
        self.publish()

    def _reconcile_computer_mix(self):
        try:
            if self.computer_mix.reconcile() and not self.group_switching:
                self.mix_members=[]
                self.mix_levels={}
                self.playback_method='native'
                self.publish_computer_mix(reset=True)
        except (OSError,ValueError,subprocess.SubprocessError):
            # A failed inventory read is not proof of a disconnect.
            return
        except RuntimeError as error:
            self._stop_lost_computer_mix(str(error))

    def _stop_lost_computer_mix(self,message):
        try:self.computer_mix.stop()
        except Exception as error:message=str(error)
        self.mix_members=[]
        self.mix_levels={}
        self.playback_method='native'
        self.publish_computer_mix(message,reset=True)

    def _lost(self, address, reason, interrupt=True):
        self.group_ready_at.pop(address,None)
        task=self.operations.pop(address,None) if interrupt else None
        if task and task is not asyncio.current_task() and not task.done():task.cancel()
        session = self.sessions.pop(address,None)
        if session:session.close()
        for key,future in list(self.group_waiters.items()):
            if key[0]==address:
                if not future.done():future.set_exception(ConnectionError('Bluetooth disconnected. Reconnect to manage PartyUp.'))
                self.group_waiters.pop(key,None)
        speaker = self.speakers.get(address)
        if speaker:
            self.invalidate(speaker)
            if interrupt:
                speaker.busy = False
                speaker.operation = ''
            speaker.error = 'Speaker controls disconnected. Reconnect to read the speaker and manage PartyUp.'
            self.publish()

    async def _wake(self, address):
        self.waking.add(address)
        try:
            s=self.speakers[address]
            if not s.paired or not s.wake_available:
                raise RuntimeError('Search for speakers to find a recent sleeping-speaker signal first.')
            self.status.emit('Waking '+s.name+'…')
            await self.bluez.wake(address)
            # A successful GATT write is only a request. Establish and identify the
            # Classic control connection before reporting that the speaker is awake.
            last_error=None
            for _ in range(4):
                await asyncio.sleep(1)
                try:
                    await self._connect(address)
                    s.sleeping=False
                    self.status.emit(s.name+' is on and connected')
                    return
                except (OSError,TimeoutError) as error:last_error=error
            raise ConnectionError('The wake request was sent, but the speaker did not become reachable. Try its power button or check Bluetooth Smart in the phone app.') from last_error

        finally:
            self.waking.discard(address)

    async def _connect_or_wake(self,address):
        s=self.speakers[address]
        if not s.bluez_connected and s.sleeping is None:
            self.status.emit('Checking for a sleeping-speaker signal from '+s.name+'…')
            await self.bluez.scan(4,le_only=True)
            await self.refresh_devices()
        if s.sleeping and s.wake_available:
            s.operation='wake'
            self.publish()
            await self._wake(address)
        else:
            try:await self._connect(address)
            except (OSError,TimeoutError):
                # A cached awake beacon or first RFCOMM attempt can be stale.
                # Retry within this click, and rediscover wake support if needed.
                if not s.bluez_connected:
                    await self.bluez.scan(4,le_only=True)
                    await self.refresh_devices()
                if s.sleeping and s.wake_available:await self._wake(address)
                else:
                    await asyncio.sleep(1)
                    await self._connect(address)

    async def _connect(self, address):
        already_connecting=address in self.connecting
        self.connecting.add(address)
        try:
            await self._connect_controls(address)
        finally:
            if not already_connecting:self.connecting.discard(address)

    async def _connect_controls(self, address):
        speaker = self.speakers[address]
        name = speaker.name.upper().replace(' ', '').replace('-', '')
        if any(model in name for model in ('BOOM4','EPICBOOM','EVERBOOM','HYPERBOOM','WONDERBOOM')):
            raise RuntimeError('This model is not supported for control in this first release.')
        if not speaker.paired:
            raise RuntimeError('Pair this speaker in your desktop’s Bluetooth settings, then search again.')
        if address in self.sessions:
            self.sessions.pop(address).close()
        self.invalidate(speaker)
        self.status.emit(f'Connecting to {speaker.name}…')
        channel = await rfcomm_channel(address)
        session = LegacySession(await open_rfcomm(address, channel),
                                on_notification=lambda message: self._notification(address, message),
                                on_disconnect=lambda reason: self._lost(address, reason, interrupt=False))
        self.sessions[address] = session
        try:
            identity = (await session.request(6, 7)).rstrip(b'\0').decode('ascii', errors='strict')
            if identity not in LEGACY_MODELS:
                raise RuntimeError('This speaker model is not supported in this first release. BOOM 3 and MEGABOOM 3 are the initial targets.')
            speaker.identity = identity
            speaker.model = LEGACY_MODELS[identity]
            speaker.connected = True
            speaker.error = ''
            speaker.features = {'power': True, 'eq_write': True}
            await self._read_state(address)
            self.status.emit(f'Connected to {speaker.name}')
        except BaseException:
            session.close()
            if self.sessions.get(address) is session:
                self.sessions.pop(address, None)
                self.invalidate(speaker)
            raise

    async def _broadcast_config(self,session):
        # A mode setter is queued before the speaker finishes reconfiguring.
        # Retry only the read; resending the setter would restart that transition.
        for attempt in range(8):
            try:return await session.request(0x414,0x415)
            except CommandError as error:
                if error.status!=9 or attempt==7:raise
                await asyncio.sleep(.35*(1+min(attempt,2)))

    async def _read(self, speaker, command, reply, feature):
        if speaker.features.get(feature) is False:
            return None
        try:
            session=self.sessions[speaker.address]
            payload = await self._broadcast_config(session) if command==0x414 else await session.request(command, reply)
            speaker.features[feature] = True
            return payload
        except CommandError as error:
            if error.status == 1:
                speaker.features[feature] = False
                return None
            raise

    async def _read_state(self, address):
        s = self.speakers[address]
        if 'rename' not in s.features:
            data = await self._read(s, 0x16d, 0x16e, 'rename')
            if data is not None:
                try:s.device_name = s.name = decode_name(data)
                except ProtocolError:s.features['rename']=False
        data = await self._read(s, 3, 4, 'firmware')
        if data:
            s.firmware = '.'.join(str(n) for n in data)
        if 'colour' not in s.features:
            data = await self._read(s, 0x1be, 0x1bf, 'colour')
            if data is not None:
                if len(data)==2:
                    s.colour_code = int.from_bytes(data,'big')
                    s.colour = finish_name(s.model,s.colour_code)
                else:
                    s.features['colour'] = False
                    s.colour_code = None
                    s.colour = ''
        await self._read_levels(address)
        data = await self._read(s, 0x177, 0x178, 'eq')
        if data is not None:
            if len(data) != 1:
                raise ProtocolError('Invalid equalizer reading')
            s.eq = data[0]
        s.features['eq_write'] = s.features.get('eq', False)
        data = await self._read(s, 0x188, 0x189, 'custom_eq')
        if data is not None:
            if len(data) < 5:
                s.features['custom_eq'] = False
                s.bands = None
            else:
                s.bands = [v - 256 if v >= 128 else v for v in data[:5]]
        data = await self._read(s, 0x414, 0x415, 'group')
        if data is not None:
            if len(data) < 2 or data[0] > 3:
                s.features['group'] = False
            else:
                s.broadcast = data[0]
                s.audio_mode = data[1]
                if not (s.broadcast & 2):
                    s.members = []
                    s.member_info = {}
                    s.group_status_known = False
        if s.broadcast & 2:
            data = await self._read(s,0x19b,0x19c,'balance')
            if data is not None:
                if len(data)!=1:
                    s.features['balance']=False
                    s.balance=None
                else:s.balance=int.from_bytes(data,'big',signed=True)
        self.publish()

    async def _read_levels(self,address):
        s=self.speakers[address]
        data = await self._read(s, 0x175, 0x176, 'battery')
        if data is not None:
            if len(data) < 12:
                raise ProtocolError('Incomplete battery reading')
            s.battery = battery_percent(data[4])
        try:
            data = await self.sessions[address].request(0x18e, 0x18f)
            s.volume_steps = 31
        except CommandError as error:
            if error.status != 1:
                raise
            data = await self.sessions[address].request(0x191, 0x192)
            s.volume_steps = 15
        if len(data) != 1 or data[0] > s.volume_steps:
            raise ProtocolError('Invalid speaker volume reading')
        s.volume = round(data[0] * 100 / s.volume_steps)

    async def _poll(self,address):
        if await self.bluez.audio_streaming():return
        await self._read_levels(address)
        self.publish()

    async def _refresh_all(self):
        await self.refresh_devices()
        for address,speaker in list(self.speakers.items()):
            if speaker.connected and not speaker.busy:
                await self._perform('refresh',address)
        self.publish()
        self.status.emit('Connection status refreshed')

    async def _refresh(self, address):
        try:await self._read_state(address)
        except (OSError,TimeoutError):
            self._lost(address,'Speaker did not reply to refresh')
            raise
        self.status.emit('Speaker readings refreshed')

    async def _firmware(self,address):
        speaker=self.speakers[address]
        data=await self._read(speaker,3,4,'firmware')
        if not data:raise ProtocolError('The speaker did not provide its firmware version.')
        speaker.firmware='.'.join(str(n) for n in data)
        self.publish()
        self.status.emit('Installed firmware version read. Check update availability in the official UE app.')

    def publish_computer_mix(self,error='',reset=False):
        self.mix_error=error
        self.computer_mix_changed.emit({'running':self.computer_mix.active,'outputs':self.mix_outputs,'error':error,
            'members':list(self.mix_members),'method':self.playback_method,'switching':self.group_switching,
            'reset':reset,
            'levels':{address:dict(level) for address,level in self.mix_levels.items()}})

    def _mix_output_name(self,address):
        prefix='BLUEZ_OUTPUT.'+address.upper().replace(':','_')+'.'
        return next((name for name in self.computer_mix.names if name.upper().startswith(prefix)),None)

    async def _computer_mix_levels(self):
        if not self.computer_mix.active or self.group_switching:return
        try:
            levels=self.computer_mix.levels()
            self.mix_levels={address:levels.get(self._mix_output_name(address),{'error':'Speaker audio output unavailable.'}) for address in self.mix_members}
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            self.mix_levels={address:{'error':'Could not read Linux volume. Refresh to try again.'} for address in self.mix_members}
        self.publish_computer_mix(getattr(self,'mix_error',''))

    async def _computer_mix_volume(self,address,percent):
        try:
            if self.group_switching:raise RuntimeError('Wait for the playback mode switch to finish.')
            if address not in self.mix_members or not self.computer_mix.active:
                raise RuntimeError('Start Computer mix with this speaker before changing its volume.')
            name=self._mix_output_name(address)
            if not name:raise RuntimeError('The selected speaker has no output in this Computer mix.')
            self.mix_levels[address]={**self.computer_mix.set_volume(name,percent),'requested_volume':percent}
        except Exception as error:
            self.mix_levels[address]={'error':str(error) or 'Could not adjust the speaker volume. Refresh and try again.'}
        self.publish_computer_mix(getattr(self,'mix_error',''))

    async def _group_method(self,method,addresses_json):
        """Keep group intent while changing both the speaker link and Linux audio."""
        if self.group_switching:
            self.error.emit('A playback mode switch is already running.')
            return
        was_running=self.computer_mix.active
        previous_members=list(self.mix_members)
        previous_method=self.playback_method
        try:
            addresses=json.loads(addresses_json)
            if method not in ('native','computer') or not isinstance(addresses,list) or not addresses or any(not isinstance(a,str) for a in addresses) or len(set(addresses))!=len(addresses):
                raise ValueError('Choose a host and different speakers for the group.')
            if method=='computer' and len(addresses)!=2:
                raise ValueError('Computer mix currently supports exactly two speakers.')
            if method=='computer' and self.computer_mix.active:
                if addresses==self.mix_members:
                    self.publish_computer_mix()
                    return
                raise RuntimeError('Stop the current Computer mix before changing its speakers.')
            # Acquire ownership before the first await: two inventory reads may
            # otherwise resume into overlapping mode transitions.
            self.group_switching=True
            self.group_switch_task=asyncio.current_task()
            self.mix_members=list(addresses)
            self.mix_levels={}
            self.playback_method=method
            self.publish_computer_mix()
            await self.refresh_devices()
            for address in addresses:
                if address not in self.speakers or not self.speakers[address].paired:
                    raise RuntimeError('A selected speaker is not paired. Pair it in Bluetooth settings before switching.')
                if self.speakers[address].busy:raise RuntimeError(self.speakers[address].name+' is busy. Wait for it to finish.')
            if method=='computer':
                # End native hosts first: a receiver may have no direct Linux link
                # until its speaker-to-speaker PartyUp connection has been released.
                for address in addresses:
                    speaker=self.speakers[address]
                    if speaker.connected or speaker.audio_connected or speaker.broadcast&2:
                        await self._group_controls(address,refresh=True)
                        if speaker.broadcast&2:
                            if speaker.audio_mode in (0,0x50):self.native_group_modes[address]=speaker.audio_mode
                            await self._perform('ungroup',address)
                            if speaker.error or speaker.broadcast&2:
                                raise RuntimeError('Could not end PartyUp on '+speaker.name+'. '+speaker.error)
                for address in addresses:
                    speaker=self.speakers[address]
                    self.status.emit('Connecting Linux audio to '+speaker.name+'…')
                    if speaker.sleeping and speaker.wake_available:await self._group_controls(address)
                    try:await self.bluez.connect_audio(address)
                    except Exception as error:raise ConnectionError(speaker.name+': '+str(error)) from error
                names=await self._wait_group_outputs(addresses)
                self.computer_mix.start(names)
            else:
                self.computer_mix.stop()
                for address in addresses:await self._group_controls(address)
                host=addresses[0]
                for address in addresses[1:]:
                    await self._perform('group_add',host,address)
                    if self.speakers[host].error or address not in self.speakers[host].members:
                        raise RuntimeError('Could not join '+self.speakers[address].name+' to PartyUp. '+self.speakers[host].error)
                if len(addresses)==2 and host in self.native_group_modes:
                    await self._perform('party_mode',host,self.native_group_modes[host])
                    if self.speakers[host].error:raise RuntimeError(self.speakers[host].error)
                if sys.platform=='win32':
                    self.status.emit('PartyUp is configured. Select the host speaker in Windows Sound settings for music.')
                else:
                    await self.bluez.connect_audio(host)
            await self.refresh_devices()
            self.status.emit('Computer mix is on' if method=='computer' else 'Native PartyUp is on. Select its host in Windows Sound settings for music.' if sys.platform=='win32' else 'Native PartyUp is on')
        except asyncio.CancelledError:
            if was_running and self.computer_mix.active:
                self.mix_members=previous_members;self.playback_method=previous_method
            self.publish_computer_mix('The mode switch was interrupted by a speaker disconnect. Retry the switch.')
            raise
        except Exception as error:
            if was_running and self.computer_mix.active:
                self.mix_members=previous_members;self.playback_method=previous_method
            self.publish_computer_mix(str(error))
            self.error.emit(str(error))
        finally:
            if self.group_switch_task is asyncio.current_task():
                self.group_switching=False
                self.group_switch_task=None
                # Keep any error until the next explicit attempt.
                self.publish_computer_mix(getattr(self,'mix_error',''))

    async def _group_controls(self,address,refresh=False):
        speaker=self.speakers[address]
        if not speaker.connected or refresh:
            await self._perform('refresh' if speaker.connected else 'connect',address)
            if not speaker.connected:await self._perform('connect',address)
            if not speaker.connected or speaker.error:
                raise ConnectionError('Could not connect controls for '+speaker.name+'. '+speaker.error)

    async def _wait_group_outputs(self,addresses):
        for _ in range(20):
            rows=audio_snapshot()
            names=[output_for_address(rows,address) for address in addresses]
            if all(names):
                self.mix_outputs=[{'name':name,'label':self.speakers[address].name} for name,address in zip(names,addresses)]
                return names
            await asyncio.sleep(.25)
        missing=[self.speakers[address].name for address,name in zip(addresses,names) if not name]
        raise ConnectionError('Linux audio output did not appear for '+', '.join(missing)+'. Retry the switch.')

    async def _computer_mix_outputs(self):
        try:
            sinks=speaker_sinks(audio_snapshot())
            self.mix_outputs=[]
            for name,label in sinks.items():
                speaker=next((s for s in self.speakers.values() if name.upper().startswith('BLUEZ_OUTPUT.'+s.address.replace(':','_')+'.')),None)
                self.mix_outputs.append({'name':name,'label':speaker.name if speaker else label})
            self.publish_computer_mix()
        except Exception:
            self.publish_computer_mix('Could not read Linux audio outputs. PipeWire tools pw-cli, pw-dump and wpctl are required.')

    async def _prepare_computer_mix(self):
        if self.computer_mix.active:return
        if self.mix_preparing:raise RuntimeError('Computer mix is still preparing. Try again in a moment.')
        self.mix_preparing=True
        try:
            await self.refresh_devices()
            for speaker in list(self.speakers.values()):
                if not (speaker.connected or speaker.audio_connected or speaker.broadcast&2):continue
                if speaker.busy:raise RuntimeError(speaker.name+' is busy. Wait for it to finish.')
                await self._perform('refresh' if speaker.connected else 'connect',speaker.address)
                if not speaker.connected or speaker.error:
                    raise RuntimeError('Could not check native PartyUp on '+speaker.name+'. '+speaker.error)
                if speaker.broadcast&2:
                    await self._perform('ungroup',speaker.address)
                    if speaker.error or speaker.broadcast&2:
                        raise RuntimeError('Could not end native PartyUp on '+speaker.name+'. '+speaker.error)
        finally:self.mix_preparing=False

    async def _computer_mix_prepare(self):
        try:
            await self._prepare_computer_mix()
            await self._computer_mix_outputs()
        except Exception as error:self.publish_computer_mix(str(error))

    async def _computer_mix_start(self,names_json):
        try:
            names=json.loads(names_json)
            from .audio_mix import configuration
            configuration(names,'validation')
            await self._prepare_computer_mix()
            self.computer_mix.start(names)
            self.playback_method='computer'
            self.publish_computer_mix()
            self.status.emit('Computer mix is on. Linux is sending audio directly to both speakers.')
        except Exception as error:self.publish_computer_mix(str(error))

    async def _computer_mix_stop(self):
        try:
            self.computer_mix.stop()
            self.mix_members=[]
            self.mix_levels={}
            self.publish_computer_mix()
            self.status.emit('Computer mix stopped. The previous output was restored unless you selected a different one.')
        except Exception as error:self.publish_computer_mix(str(error))

    async def _rename(self,address,name):
        s=self.speakers[address]
        payload=encode_name(name)
        if not s.features.get('rename'):
            raise RuntimeError('This speaker did not provide a valid name. Reconnect and try again.')
        session=self.sessions[address]
        await session.request(0x16f,payload=payload)
        actual=decode_name(await session.request(0x16d,0x16e))
        s.device_name=s.name=actual
        if actual!=name.strip():
            raise RuntimeError('The speaker stored the name as '+actual+'. Check the name and try again.')
        try:await self.bluez.set_alias(s.path,actual)
        except Exception:
            s.error='The speaker was renamed. Your desktop’s Bluetooth label may update after reconnecting.'
        self.status.emit('Speaker renamed to '+actual)
        self.publish()

    async def _volume(self, address, percent, revision=None):
        s = self.speakers[address]
        raw = round(max(0, min(100, int(percent))) * s.volume_steps / 100)
        await self.sessions[address].request(0x18d if s.volume_steps == 31 else 0x190, payload=bytes([raw]))
        await self._read_levels(address)
        self.publish()
        self.status.emit('Volume updated')

    async def _eq(self, address, code):
        if code not in (0, 1, 2, 3, 4):
            raise ValueError('Choose one of the supported speaker presets')
        await self.sessions[address].request(0x179, payload=bytes([code]))
        await self._read_state(address)
        self.status.emit('Sound profile updated')

    async def _custom_eq(self, address, bands):
        if len(bands) != 5 or any(not isinstance(v, int) or not -128 <= v <= 127 for v in bands):
            raise ValueError('Five valid equalizer levels are required')
        await self.sessions[address].request(0x18a, payload=bytes(v & 255 for v in bands))
        await self.sessions[address].request(0x179, payload=b'\x04')
        await self._read_state(address)
        self.status.emit('Custom equalizer updated')

    async def _identify(self, address):
        await self.sessions[address].request(0x16b)
        self.status.emit('The speaker is announcing its battery level')

    async def _power(self, address):
        await self.sessions[address].request(0x1b6)
        await self._disconnect(address)
        self.status.emit('Speaker powered off. Search for speakers to find its remote wake signal.')

    async def _disconnect(self, address):
        self._lost(address,'Disconnected from speaker controls')
        self.speakers[address].error = ''
        self.status.emit('Disconnected from speaker controls. Pairing is still saved in Bluetooth settings.')

    async def _busy_request(self, session, command, payload):
        for attempt in range(3):
            try:
                return await session.request(command, payload=payload)
            except CommandError as error:
                if error.status != 9 or attempt == 2:
                    raise
                await asyncio.sleep(.3 * (attempt + 1))

    async def _group_add(self, address, receiver):
        host = self.speakers[address]
        if receiver in host.members:
            self.status.emit('This speaker is already playing in the group.')
            return
        target = self.speakers.get(receiver)
        if receiver == address or not target or not target.connected:
            raise RuntimeError('Connect the other speaker first, then add it to PartyUp.')
        if not host.features.get('group') or not target.features.get('group'):
            raise RuntimeError('PartyUp is unavailable on one of these speakers.')
        if target.broadcast & 2:
            raise RuntimeError('End the other speaker’s group before adding it here.')
        key = (address, 0x418, receiver)
        future = self.loop.create_future()
        self.group_waiters[key] = future
        try:
            session = self.sessions[address]
            data=await self._broadcast_config(session)
            if len(data)!=2 or data[0]>3:raise ProtocolError('Invalid PartyUp mode reading')
            host.broadcast,host.audio_mode=data
            # A status update may have confirmed this receiver during the read.
            if receiver in host.members:
                self.status.emit('This speaker is already playing in the group.')
                return
            if not (host.broadcast & 2):
                await self._busy_request(session, 0x413, b'\x03\x00')
                data = await self._broadcast_config(session)
                if len(data) >= 2:
                    host.broadcast = data[0]
            # Android assigns the receiver RIGHT, including in Double Up.
            # UNKNOWN is not the channel requested by its PartyUp presenter.
            await self._busy_request(session, 0x417, bytes.fromhex(receiver.replace(':','')) + b'\x02')
            self.status.emit('Waiting for the speaker to join PartyUp…')
            await asyncio.wait_for(future, 30)
            # Receiver handoff can still be settling after the join ACK/status.
            # Switching the host's mode immediately can drop the fresh member.
            self.group_ready_at[address]=time.monotonic()+6
            if sys.platform=='win32' and receiver in self.sessions:
                # This firmware relinquishes its direct Classic controls when
                # becoming a native receiver. Do not retain a silently stalled
                # Windows stream; group controls go through the host instead.
                self._lost(receiver,'Using the host for PartyUp controls',interrupt=False)
                target.error=''
            self.publish()
            self.status.emit('Speaker joined PartyUp')
        finally:
            self.group_waiters.pop(key, None)
            if not future.done():
                future.cancel()

    async def _group_remove(self, address, receiver):
        key = (address, 0x41a, receiver)
        future = self.loop.create_future()
        self.group_waiters[key] = future
        try:
            await self._busy_request(self.sessions[address], 0x419, bytes.fromhex(receiver.replace(':','')))
            await asyncio.wait_for(future, 30)
            await self._read_state(address)
            self.status.emit('Speaker removed from PartyUp')
        finally:
            self.group_waiters.pop(key, None)
            if not future.done():
                future.cancel()

    async def _ungroup(self, address):
        await self._busy_request(self.sessions[address], 0x413, b'\x00\x00')
        await self._broadcast_config(self.sessions[address])
        await self._read_state(address)
        self.status.emit('PartyUp ended')

    async def _group_volume(self, address, percent):
        await self._volume(address, percent)
        await self.sessions[address].request(0x41b)
        s=self.speakers[address]
        for metadata in s.member_info.values():metadata.pop('volume',None)
        if len(s.members)==1 and s.audio_mode==0x50 and s.balance is not None:
            await self.sessions[address].request(0x19d,payload=bytes([s.balance&255]))
        self.status.emit('Group volume synchronized')

    async def _balance(self,address,position):
        s=self.speakers[address]
        if not s.broadcast&2 or len(s.members)!=1:
            raise RuntimeError('Balance requires exactly two speakers in PartyUp.')
        if not s.features.get('balance'):
            raise RuntimeError('This speaker does not support balance control.')
        if not isinstance(position,int) or not 0<=position<=255:
            raise ValueError('Invalid balance position')
        # The register can echo writes in Double Up without an audible effect.
        # Check the actual channel mode, not just acceptance of the balance byte.
        configuration=await self._broadcast_config(self.sessions[address])
        if len(configuration)!=2 or configuration[0]>3:raise ProtocolError('Invalid PartyUp mode reading')
        s.broadcast,s.audio_mode=configuration
        if not s.broadcast&2 or s.audio_mode!=0x50:
            if not s.broadcast&2:s.members=[]
            self.publish()
            raise RuntimeError('Select Stereo (host left, member right) before adjusting balance.')
        await self.sessions[address].request(0x19d,payload=bytes([(position-128)&255]))
        data=await self.sessions[address].request(0x19b,0x19c)
        if len(data)!=1:raise ProtocolError('Invalid balance reading')
        s.balance=int.from_bytes(data,'big',signed=True)
        self.publish()
        self.status.emit('Speaker balance updated')

    async def _party_mode(self,address,mode):
        s=self.speakers[address]
        if mode not in (0,0x50):raise ValueError('Unsupported PartyUp playback mode')
        delay=self.group_ready_at.get(address,0)-time.monotonic()
        if delay>0:
            self.status.emit('Waiting for the new PartyUp connection to settle…')
            await asyncio.sleep(delay)
        if not s.broadcast&2 or len(s.members)!=1:
            raise RuntimeError('Playback mode requires exactly two speakers in PartyUp.')
        session=self.sessions[address]
        configuration=await self._broadcast_config(session)
        if len(configuration)!=2 or configuration[0]>3:raise ProtocolError('Invalid PartyUp mode reading')
        s.broadcast,s.audio_mode=configuration
        if not s.broadcast&2:
            s.members=[]
            self.publish()
            raise RuntimeError('The PartyUp group is no longer broadcasting.')
        await self._busy_request(session,0x413,bytes([configuration[0],mode]))
        confirmed=await self._broadcast_config(session)
        if len(confirmed)!=2 or confirmed[0] not in (2,3):raise ProtocolError('Invalid PartyUp mode reading')
        s.broadcast,s.audio_mode=confirmed
        self.publish()
        if s.audio_mode!=mode:
            raise RuntimeError('The speaker did not switch playback mode. Keep the matching pair connected and try again.')
        self.status.emit('Stereo enabled: host plays left, member plays right. Balance is available.' if mode else 'Double Up enabled: both speakers play the full sound.')

    async def _receiver_attribute(self,address,receiver,write=None):
        """An ACK means queued, not delivered. Correlate the receiver result."""
        host=self.speakers[address]
        if not host.broadcast&2 or receiver not in host.members:
            raise RuntimeError('This speaker is no longer in the PartyUp group.')
        event=0x421 if write is None else 0x423
        key=(address,event,receiver,0x1e)
        future=asyncio.get_running_loop().create_future()
        self.group_waiters[key]=future
        payload=bytes.fromhex(receiver.replace(':',''))+b'\x00\x1e'
        if write is not None:payload+=bytes([write])
        try:
            await self.sessions[address].request(0x420 if write is None else 0x422,payload=payload)
            try:return await asyncio.wait_for(future,8)
            except TimeoutError:
                raise RuntimeError('This speaker did not confirm its individual level. Group volume and two-speaker balance remain available.') from None
        finally:
            self.group_waiters.pop(key,None)
            if not future.done():future.cancel()

    async def _group_levels(self,address):
        host=self.speakers[address]
        await self._read_levels(address)
        failures=[]
        for receiver in list(host.members):
            target=self.speakers.get(receiver)
            try:
                if target and target.connected and receiver in self.sessions:
                    await self._read_levels(receiver)
                    host.member_info.setdefault(receiver,{})['volume']=target.volume
                else:await self._receiver_attribute(address,receiver)
            except (OSError,TimeoutError) as error:
                # A receiver may relinquish its Classic socket during PartyUp
                # without Windows immediately reporting the link loss.
                self._lost(receiver,'Receiver control channel stopped responding',interrupt=False)
                metadata=host.member_info.setdefault(receiver,{})
                metadata.pop('volume',None)
                metadata['level_error']='The receiver’s direct controls stopped responding. Refresh levels to try the host proxy; group volume and stereo balance remain available.'
                failures.append(error)
            except (RuntimeError,CommandError) as error:
                metadata=host.member_info.setdefault(receiver,{})
                metadata.pop('volume',None)
                metadata['level_error']=str(error)
                failures.append(error)
            self.publish()
        self.status.emit('Individual levels refreshed' if not failures else 'Some speakers do not expose an individual level. Use group volume or balance for those speakers.')

    async def _member_volume(self,address,receiver,percent,revision=None):
        host=self.speakers[address]
        if not host.broadcast&2 or receiver not in [address]+host.members:
            raise RuntimeError('This speaker is no longer in the PartyUp group.')
        if not isinstance(percent,int) or not 0<=percent<=100:raise ValueError('Invalid speaker level')
        target=self.speakers.get(receiver)
        if target and target.connected and receiver in self.sessions:
            await self._volume(receiver,percent)
            if receiver!=address:host.member_info.setdefault(receiver,{})['volume']=target.volume
        else:
            # Require a real level before enabling writes on the proxy path.
            if host.member_info.get(receiver,{}).get('volume') is None:
                raise RuntimeError('Refresh speaker levels before adjusting this speaker.')
            await self._receiver_attribute(address,receiver,round(percent*31/100))
            await self._receiver_attribute(address,receiver)
        self.publish()
        self.status.emit('Individual speaker level updated')

    def _notification(self, address, message):
        s = self.speakers.get(address)
        if not s:
            return False
        if message.command == 0x443:
            self._lost(address, 'Speaker powered off')
            return True
        payload = message.payload
        if message.command==0x19c:
            # The speaker also pushes this reading without a pending query.
            # Recognize and ACK it so it does not keep retrying the update.
            if len(payload)!=1:return False
            s.balance=int.from_bytes(payload,'big',signed=True)
            self.publish()
            return True
        if message.command in (0x421,0x423):
            if len(payload)<9 or payload[8] not in (0,1):return False
            receiver=':'.join(f'{v:02X}' for v in payload[:6])
            attribute=int.from_bytes(payload[6:8],'big')
            key=(address,message.command,receiver,attribute)
            future=self.group_waiters.get(key)
            if not future or future.done():return False
            if not payload[8]:future.set_exception(RuntimeError('The receiver rejected its individual level command.'))
            elif message.command==0x421:
                if len(payload)!=10 or payload[9]>31:
                    future.set_exception(ProtocolError('Unsupported receiver volume reading'))
                else:
                    s.member_info.setdefault(receiver,{})['volume']=round(payload[9]*100/31)
                    s.member_info[receiver].pop('level_error',None)
                    future.set_result(payload[9])
            else:future.set_result(True)
            self.publish()
            return True
        if message.command in (0x418, 0x41a):
            if len(payload) < 7:
                return False
            receiver = ':'.join(f'{v:02X}' for v in payload[:6])
            success = payload[6] == 0
            future = self.group_waiters.get((address, message.command, receiver))
            if future and not future.done():
                if success:
                    future.set_result(True)
                else:
                    reason = {1:'Could not connect to the other speaker.',3:'Press the other speaker’s pairing button twice, then try again.',4:'Turn on the other speaker, then try again.'}.get(payload[6],'The speaker could not complete the PartyUp change.')
                    future.set_exception(RuntimeError(reason))
            if success:
                if message.command == 0x418 and receiver not in s.members:
                    s.members.append(receiver)
                if message.command == 0x41a:
                    s.members = [m for m in s.members if m != receiver]
                self.publish()
            return True
        if message.command == 0x416:
            if not payload or len(payload) < 1 + payload[0] * 10:
                return False
            members = []
            member_info = {}
            for offset in range(1, 1 + payload[0] * 10, 10):
                mac = ':'.join(f'{v:02X}' for v in payload[offset:offset+6])
                packed = int.from_bytes(payload[offset+6:offset+8], 'big')
                if (packed & 15) == 8:
                    members.append(mac)
                raw_battery = (packed >> 8) & 127
                member_info[mac] = {**s.member_info.get(mac,{}),'battery': battery_percent(raw_battery) if raw_battery <= 100 else None}
                if mac not in s.members or (packed&15)!=8:
                    member_info[mac].pop('volume',None)
                    member_info[mac].pop('level_error',None)
            s.members = members
            s.member_info = member_info
            s.group_status_known = True
            # Some firmware reports membership before (or without) a separate
            # add completion. Actual playing-this-broadcast status is enough.
            for receiver in members:
                future=self.group_waiters.get((address,0x418,receiver))
                if future and not future.done():future.set_result(True)
            self.publish()
            return True
        return False

    def shutdown(self):
        self.stopping = True
        if self.loop and self.loop.is_running():
            async def finish():
                try:self.computer_mix.stop()
                except Exception as error:self.error.emit(str(error))
                for session in self.sessions.values():
                    session.close()
                # WinRT cancellation waits for native completion. Cancelling a
                # reader twice can abandon that wait and leave a callback aimed
                # at an already closed event loop. Drain workers before COM exit.
                pending=[task for task in asyncio.all_tasks(self.loop) if task is not asyncio.current_task()]
                for task in pending:
                    if not task.cancelling():task.cancel()
                await asyncio.gather(*pending,return_exceptions=True)
                if self.bluez:
                    await self.bluez.close()
                self.loop.stop()
            asyncio.run_coroutine_threadsafe(finish(), self.loop)
        # Allow the bounded PipeWire startup/read timeouts to finish before
        # cleanup, rather than destroying a running Qt worker during app exit.
        self.wait(15000)
