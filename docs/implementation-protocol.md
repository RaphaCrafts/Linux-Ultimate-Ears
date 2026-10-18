# Implementation static evidence index

Static JADX/REA observations only. No speaker interaction was performed by this worker.

Later sections explicitly identify additional hardware observations.

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

## PartyUp mixing (0.1.7)

Native two-speaker balance: query0x019b →0x019c, setter0x019d with one signed
byte. Centre is00, left endpoint80, right endpoint7f. The phone slider maps
0..255 to signed -128..127. Linux uses this native control only for exactly one
confirmed receiver and performs a fresh balance query after each change.
Group volume synchronization reapplies the cached native balance for a pair.

Correction0.1.8: the balance register can accept/read back settings independently
of the channel mode. Android only exposes balance while in Stereo. Its Stereo
action sends the existing broadcast state with audio option0x50 (host left).
Linux now requires that confirmed mode for balance and offers an explicit mode
selector. Config query0x0414 →0x0415 returns state byte followed by audio option;
setter0x0413 writes both bytes. A register echo in Double Up is not evidence of
audible balance. Primary APK evidence: stereo action
`ev_4b81a34632779b18a63f7c47d4697980d7490a5a453610166afe16536f5fdbf6`,
conditional balance panel
`ev_fbd8e3e5d66bc907d3fcbed6fa39c6e770b19c7a28a10f683a5d1e77305c01dd`.

Receiver attribute Volume has ID0x001e. Query0x0420 and setter0x0422 return
queue ACKs; separate notifications0x0421/0x0423 contain MAC6, BE16 attribute,
delivery boolean, then the query value. Linux correlates host, receiver, event
and attribute, requires successful delivery and a bounded one-byte0..31 query
value before enabling writes, and reads back after a delivered write. Direct
control sessions use their existing validated16/32-step volume path instead.
Receiver controls are explicit user actions; automatic audio-time queries remain
disabled. Group volume synchronization invalidates cached receiver levels.

Static evidence IDs: balance setter
`ev_2f74072de10fc2abbde20c39b9cfd5d77476a6871cf9a27d126534064135d910`,
slider mapping `ev_14f6a63b5d233babddfd60aec0704c12660b632f1fd2e355247263f2d78df119`,
attribute enum `ev_845ee516a44ca8d45f28f1c0fe5f04c92ab9e08ba27fdf8de8637d00efb30651`,
query decoder `ev_2eb5ce0d4bd1ca48e246bb47eb9d3fc500bffc376bfd6149f5904a9419aa0e01`,
setter result decoder `ev_b608886515843087aeeaa0f8539e7c0050432b8fc65761844c673020ae0d1f8e`.

Hardware on2026-10-18: the MEGABOOM3 host confirmed balance00 →fe →00.
It rejected the static APK's one-byte attribute request format, accepted the
two-byte attribute query format but emitted no receiver-level completion.
Receiver proxy volume writing and three-speaker operation remain unverified;
the UI keeps unavailable receiver controls disabled rather than trusting an ACK.


Full selectors and evidence IDs are in [evidence-index.json](evidence-index.json), under `impl-` records.

Group status records include nearby devices as well as members. Only status8 (playing this broadcast) is treated as confirmed membership from a broadcast-status record. Add/remove completion notifications are correlated by host and receiver MAC, with status0 required and a 30-second timeout.

The Qt view uses relative signed levels for custom EQ. It does not claim calibrated dB units or reproduce every mobile preset. Legacy BLE wake is implemented for validated paired beacons; CPP remains outside this build.

## Finish detection

Legacy colour query `0x01be` returns `0x01bf` with an unsigned big-endian 16-bit
identifier. BOOM 3 base colours occupy 0x0110–0x0115, Denim/Cloud 0x011c/0x011d;
MEGABOOM 3 base colours occupy 0x0116–0x011b, Denim/Cloud 0x011e/0x011f.
Model-specific mappings are in `colours.py`; a code from another model is never
used to infer a finish. Unknown/malformed/unsupported colour data does not grant
control capabilities or choose a guessed packshot.

REA static evidence from the extracted APK (SHA-256
`018e9d6159311034327780480ee3798a7cdf31c5e7d174b6c496bf2254410e76`):

- Colour enum: `ev_9cd2a006f327c73fa28d7a20c0167da625c56e8c073f410664ed518f900b607a`.
- Query/result selection: `ev_53b4f389c1338b07d6130ec53b9248007aa44da0b6756341b8a1864ed0c4562a`.
- Unsigned-short parser: `ev_dc0efb33c2800422949c9f6c343c532c79c10c76118a7e38838d89316a94aa53`.

Hardware observation, 2026-10-18: the user's HUMBOLDT speaker returned `04 31`.
Its finish was identified from the user's supplied phone-app screenshot and
matched to the official Unicorn packshot. This mapping is recorded separately
from enum-derived mappings. Broader limited-edition mappings remain unknown;
commercial SKU identity is not claimed.

## BLE sleeping-speaker discovery and wake (0.1.4)

Search requests BlueZ interleaved `Transport=auto` discovery with duplicate
manufacturer updates. The app tracks fresh ManufacturerData signals, not cached
UUIDs or names, and expires wake availability after 45 seconds without a fresh
advertisement. Wake only targets a radio whose advertised Classic address exactly
matches a saved Linux pairing. No name-based radio association is used.

The physically observed MEGABOOM 3 packet has FE61, manufacturer company 3,
19 manufacturer bytes and a final 0x22 discriminator (semantic meaning unknown).
Colour is BE16 at0, battery/charging at2, volume at3, sleeping when byte4&e0 is0,
and Classic address at12..17. This layout and address relationship were checked
against two physical speakers; one was observed powered on and then switched
off by the user. Other layouts are rejected. The manufacturer MAC offset is
physical evidence, not a translated full-scan offset from the Android parser.

The Android legacy parser independently uses the same power mask on full-scan
byte18 (REA `ev_fd0f68847b9ef59f7e70417fb3644d0f53409c8a8e67fd7e937bc8d8af1bdefe`).
The ADK3 fallback does not decode the manufacturer layout
(`ev_3e9571529afa0c65718ee4bb171f732918a3a70c0f92e036d850e82c95fcfe2e`).
Do not substitute the distinct Wasp layout or apply full-scan MAC offsets.

Wake writes the Linux adapter's six address bytes in displayed order plus01 to
`c6d6dc0d-07f5-47ef-9b59-630622b01fd3`. The live characteristic advertised `write`,
so a request write was used. Production code checks the flags and only uses a
command write if write-without-response is advertised instead. Connect, discovery
and write waits are bounded. A successful write is followed by a real identified
Classic control connection before the UI reports success. Existing audio links
are not deliberately disconnected after a successful wake.

## Actual speaker renaming (0.1.5)

Query Bluetooth name0x016d →0x016e; Set Bluetooth name0x016f expects ACK. The
payload is trimmed UTF-8 followed by one NUL byte. Phone validation allows1–30
UTF-8 bytes excluding the terminator. The implementation rejects empty/control
characters, uses a bounded NUL decoder and performs a fresh query after the write.
Only after hardware readback is confirmed does it synchronize the selected
BlueZ Device1 Alias. A local alias failure is reported separately. An Alias write
alone is never considered a successful speaker rename.

REA static evidence:

- Setter `ev_628789b603f270153c7fa26f0cc784d03b594ab2d42bd44afb6377255de7544a`.
- UTF-8/NUL packing `ev_9e999ecb182f69564e964897f982566bfd814a59b9061bf689ffbe9a7798616f`.
- 30-byte validation `ev_669c6e938e15b88c76402034b272fa9b4d64751b81d90e960416241357388e2f`.
- Name parser `ev_5304cafa9276d86aabd601635e2013eaf32bfa15f70adc2f59c01a9396d4f7d2`.

Hardware validation reapplied the current name and verified actual readback,
preserving the user's speaker name. A changed Unicode name is covered by the
protocol-level fake peer, not claimed as a live hardware rename.

## Playback-safe polling (0.1.6)

BlueZ MediaTransport1.State active/pending/broadcasting is treated as streaming.
The app reads this locally over D-Bus; it does not acquire/release a transport or
change codecs. Optional remote battery/volume polls pause while any Bluetooth
media transport streams and resume once per minute at idle. Full state queries
remain on explicit Refresh/setting actions and initial connection. Classic
inquiry is avoided during streaming; wake failure never calls Device.Disconnect,
which affects all profiles rather than only the app's control socket.

References: [BlueZ MediaTransport API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.MediaTransport.rst),
[BlueZ Device API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Device.rst).
