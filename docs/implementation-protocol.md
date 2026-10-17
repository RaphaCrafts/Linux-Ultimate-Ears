# Implementation static evidence index

Static JADX/REA observations only. No speaker interaction was performed by this worker.

Legacy presets: Out Loud0; Vocal1; Intimate2; Bass Boost3; Custom4. Other EQSetting enum names are not supported by legacy mapper.
Volume32 uses raw0..31; Volume16 raw0..15. Application seek bar uses raw levels; percent scaling is a Linux UI choice.
PowerOff sets MasterRemoteOff and expects ACK without command payload.
EQProfile consumes five signed bytes, ignores additional data. RD view translates signed values to slider progress with +128 and reverses with -128; exact display max remains unverified.
Expected responses are not ACKed. Successfully recognized notifications are ACKed.
Group add payload: six MAC bytes in displayed order plus mode byte (0 unknown,1 left,2 right,3 center). Remove payload: six MAC bytes.
Broadcast mode payload: state0 disabled,1 scan,2 broadcast,3 both; audio options0 DoubleUp,0x50 left,0x60 right,0x70 center,0x90 reverse right,0xa0 reverse left,0xb0 reverse center.
Group add/remove result event: six MAC bytes followed by status. Add status0 delivered,1 failed,3 double press needed,4 power on needed. Remove delivered iff status0.
Group status event: unsigned count then count10-byte records. Each: six MAC, big-endian16-bit packed state, big-endian16-bit colour. Packed: bit15 nonzero volume offset; bits14..8 battery; bits7..4 name revision; bits3..0 device status.
NotificationMask enum only exposes track-length bit1; no grouping-enable bit observed. Setter packs32-bit integer big-endian.


Full selectors and evidence IDs are in [evidence-index.json](evidence-index.json), under `impl-` records.

Group status records include nearby devices as well as members. Only status8 (playing this broadcast) is treated as confirmed membership from a broadcast-status record. Add/remove completion notifications are correlated by host and receiver MAC, with status0 required and a 30-second timeout.

The Qt view uses relative signed levels for custom EQ. It does not claim calibrated dB units or reproduce every mobile preset. Remote wake and CPP remain outside this build.
