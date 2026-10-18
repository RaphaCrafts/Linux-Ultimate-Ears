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
