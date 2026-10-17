# Ultimate Ears Android control logic

This is the initial static interoperability investigation, performed on
2026-10-17 against `com.logitech.ueboom` **7.22.0.355**, extracted from the
user-authorized connected phone. No Linux controller or interface has been
implemented yet. No control packets were sent to a speaker.

The APK SHA-256 is
`018e9d6159311034327780480ee3798a7cdf31c5e7d174b6c496bf2254410e76`.
REA 6.5.0 with JADX headless MCP 0.7.1 recovered 17,343 class declarations.
All findings below are static observations or explicitly labeled design
inferences. They do not establish live hardware compatibility.

## Architecture recovered from the app

The app separates its UI and services from `com.logitech.ue.centurion`, a
speaker control library. That library has discovery, connection, protocol,
request queues, response parsing, notifications, feature providers, caches,
and higher-level grouping controllers.

There are **Legacy** and **CPP** device families. Bluetooth Classic SPP carries
control messages; BLE has discovery and wake/control roles. The main Linux
implementation should preserve these distinctions instead of assuming one BLE
service controls every feature. Audio streaming is a separate concern from
sending speaker control messages.

Evidence selectors and complete evidence IDs appear in
[evidence-index.json](evidence-index.json). References such as `spp-open.json`
below identify ignored local REA records, not files hosted by this repository.

## Legacy Bluetooth Classic transport and framing

`SPPConnection.openSocket` opens an Android **insecure RFCOMM** socket using the
standard SPP service UUID `00001101-0000-1000-8000-00805f9b34fb` and connects it.
The service UUID is established by the static initializer, not guessed from a
Bluetooth scan. Evidence: `spp-init.json`, `spp-open.json`.

`CenturionMessage.buildCommandData` constructs:

```text
[length: u8][command: u16 big endian][payload: length-2 bytes]
```

The length byte counts command bytes plus payload, excluding itself. A query
with no payload is three bytes. The representable payload limit is 253 bytes;
the Java builder casts to byte without enforcing that bound, so an independent
implementation should reject oversize input. There is no checksum or sequence
field in this observed legacy message format. `UtilsKt.getByte` and
`twoBytesToInt` verify the command byte order. Evidence: `message-build.json`,
`message-parse.json`, `byte-order.json`, `parse-order.json`.

Examples derived from that builder and the recovered enum, **not captured
speaker traffic**:

```text
02 00 01       query protocol version
02 00 03       query firmware version
02 01 75       query charging information
02 01 6d       query Bluetooth name
02 01 8e       query 32-step volume
03 01 8d 08    set 32-step volume argument to 8
```

`CenturionConductor.processMessage` requires at least three bytes and verifies
that the first byte equals the remaining size. It processes matching errors,
expected replies, then notifications; otherwise it reports an unexpected
message. Evidence: `process-message.json`, `check-expected.json`.

An ACK is command `0x0000`, payload `[original command high byte, low byte,
status]`. Status `0` means OK; other recovered values include unrecognized
command (1), wrong length (2), out of range (3), timeout (4), no peer (5), peer
not connected (6), value unavailable (7), command failure (8), and busy (9).
The error check correlates ACK payload command IDs to the current request.
Evidence: `ack.json`, `check-error.json`, `ack-codes.json`.

**Transport caveat:** the decompiled `onDataReceived` concatenated-message loop
contains a suspicious reversed comparison. That is unresolved static evidence,
not a trustworthy template. Implement stream reassembly from the verified
length format; test split and concatenated RFCOMM reads, invalid sizes and
notifications interleaved with responses. Verify raw DEX and captures before
claiming equivalence to the original receive loop.

## Recovered legacy controls

The [complete catalogue](legacy-command-catalog.json) contains **166 enum
entries**, including `UNKNOWN=-1`. Their presence does not prove support on a
particular speaker, and most catalogue payloads are not yet fully decoded.

| Feature | Query / response | Set / action | What this pass establishes |
| --- | --- | --- | --- |
| Protocol | `0001` / `0002` | — | Numeric command IDs |
| Firmware | `0003` / `0004` | — | Numeric command IDs |
| Device ID | `0006` / `0007` | — | Numeric command IDs |
| Speaker name | `016d` / `016e` | `016f` | Query handler and IDs; exact write encoding still pending |
| Charging / battery | `0175` / `0176` | `016b` announcement | Charging request and payload parser traced |
| EQ preset | `0177` / `0178` | `0179` | Setter uses one mapped preset byte and expects ACK |
| EQ table | `0188` / `0189` | `018a` | Five ordered band bytes; signedness/ranges still pending |
| 32-step volume | `018e` / `018f` | `018d` | Setter writes one byte |
| Earlier volume | `0191` / `0192` | `0190` | Setter writes one byte; fallback path exists |
| Capabilities | `019e` / `019f` | — | Numeric IDs; full query/response semantics pending |
| Power off | — | `01b6` master / `01b2` slave | IDs; wake uses separate BLE path |
| BLE state | `01b7` / `01b8` | `01b9` | IDs |
| Notifications mask | `0208` / `0209` | `0207` | IDs; full mask decoding pending |
| PartyUp broadcast | `0414` / `0415` | `0413` | Higher-level asynchronous grouping flow traced |
| PartyUp membership | — | `0417` add / `0419` remove | Completion notifications `0418` / `041a` |
| PartyUp volume sync | — | `041b` | ID; full synchronization policy pending |
| Alarm | `017e` / `017f` | `0180` | IDs; time/flags and phone scheduling still pending |

Command numbers are hexadecimal. Evidence: `commands.json`; the exporter
resolves initializer registers to distinguish enum ordinals from wire codes.

`LegacySPPDevice.setVolume` tries the 32-step setter then falls back to its
16-step path through `doOnUnsupported`. Reads use the analogous strategy.
Fallback should be tied to actual unsupported-command behavior, not applied to
all connection errors. Do not assume all speakers accept the same volume range.
Evidence: `set-volume.json`, `get-volume.json`, `volume32-set.json`,
`volume16-set.json`.

`setEQSetting` takes both a preset and a profile, but the traced legacy setter
serializes only the mapped preset byte and updates the cache. Custom EQ uses a
separate path: `setCustomEQ` sends `EQProfile.getBands()` with `SetEQTable` and
expects ACK. The byte order is bass, mid-bass, mid, mid-treble, treble. Exact gain
ranges, signedness and model-dependent behavior still need validation
(`feat-eq-method.json`, `feat-eq-bands.json`). A UI selection alone must not imply the entire custom profile
was uploaded. Evidence: `set-eq.json`, `eq-set-payload.json`.

`getBatteryInfo` derives a generic battery model from legacy charging info.
The full `ChargingInfo` parser consumes at least twelve payload bytes:
temperature at 0–1, voltage at 2–3, raw charge at 4, flags at 5, average current
at 6–7, time-to-empty at 8–9, and count at 10–11. Multi-byte fields are read big
endian. An alternate constructor mode reads charge from byte 0 only. Raw charge
must pass through the app's normalization before displaying a percentage.
The normalization maps raw values above 95 to 100, 90–95 to 90, 20–89 to the
lower ten, 12–19 unchanged, and below 12 to 10. This is a display convention,
not a precision battery measurement. Evidence: `battery.json`,
`charging-request.json`, `charging-parse.json`, `battery-normalize.json`,
`battery-scale.json`.

## BLE discovery and remote wake

Legacy `BLEUtilsKt.powerOnLegacyDevice(BLEConnection, MAC)` writes seven bytes:
`[six-byte host Bluetooth MAC][01]` to characteristic
`c6d6dc0d-07f5-47ef-9b59-630622b01fd3`. The MAC bytes follow their displayed order
(`AA:BB:CC:DD:EE:FF` becomes `aa bb cc dd ee ff`). The host identity is the
computer/phone initiating the connection, not the speaker's address. Triggering
a Classic connection uses the same host bytes followed by `03`, or `04` for the
forced path. Other enum values include deep sleep `00` and off `02`.
Evidence: `ble-legacy-wake.json`, `ble-legacy-connect.json`,
`ble-command-code.json`, `ble-mac-bytes.json`, `ble-mac-get.json`.

CPP wake uses `[AUID bytes][ff]` on characteristic
`5e9bf2a8-f93f-4481-a67e-3b2f4a07891a`. The default overload supplies six `02`
bytes, yielding `02 02 02 02 02 02 ff`. Another CPP enum value is authentication
`42`. The default constant is observed in this APK; it does not prove every
speaker accepts unauthenticated wake or that provisioning is unnecessary.
Evidence: `ble-cpp-wake.json`, `ble-cpp-default-auid.json`,
`ble-characteristics-code.json`, `ble-cpp-power-code.json`.

The connection ultimately calls RxBle `writeCharacteristic(uuid, bytes)`;
this pass did not establish an explicit GATT write type. Determine supported
write properties from the live characteristic rather than assuming write
without response. Evidence: `ble-connection-write-call.json`.

Discovery starts with an unfiltered BLE scan and then classifies advertisement
bytes. The scan handler tries CPP, legacy BOOM-family advertisements and an
ADK3 fallback. Advertisements provide battery, volume, power and Classic
address information, so the BLE address must not automatically be reused as
the Classic SPP address. Evidence: `ble-scan-options.json`, `ble-on-scan.json`,
`ble-ad-layout.json`, `ble-cpp-ad-layout.json`.

The inspected legacy parser reads charge/charging from byte 16, volume from
17, power-related bits from 18, Classic address from 43–48, color from 49 and
broadcast address from 50–55. The CPP parser uses Classic address bytes 44–49
and broadcast address bytes 20–25. These offsets refer to the full scan record
passed to the app's parser, not simply the manufacturer-data value exposed by
BlueZ. BlueZ's structured advertisement fields will need explicit mapping.
The legacy minimum-length check does not cover every later read; implement
strict bounds checks. Magic constants and all advertisement variants remain
incompletely characterized.

## CPP message body

`CPPMessage.buildCommandData` produces a different inner message body:

```text
[feature: u8][function ID: upper nibble | software ID: lower nibble][payload...]
```

Both IDs are masked to four bits. The constructor decodes the same layout.
This is the **inner body**, not a verified description of its complete SPP/BLE
transport envelope. It must not be parsed using the legacy length/command
format. Evidence: `feat-cpp-build.json`, `feat-cpp-parse.json`.

CPP has separate feature/function abstractions for battery, volume, EQ, power,
remote power and grouping. Full feature IDs, function tables, capability
negotiation and outer framing remain future work. This pass establishes why a
separate codec is needed, not complete support for CPP devices.

## Model and firmware selection

The app's `DeviceType` enum assigns numeric hardware codes and a device family.
For example:

| Retail family | Internal identifier | Numeric code | Protocol group |
| --- | --- | --- | --- |
| Original MEGABOOM | Titus | 3 | Legacy |
| BOOM 2 | Maximus | 4 | Legacy |
| BOOM 3 | Mendocino | 8 | Legacy |
| MEGABOOM 3 | Humboldt | 9 | Legacy |
| BOOM 3 variant | MendocinoCR | 11 | CPP |
| MEGABOOM 4 | HumboldtPlus | 12 | CPP |
| EPICBOOM | Puccini | 13 | CPP |
| EVERBOOM | Chopin | 41 | CPP |
| BOOM 4 | MendocinoPlus | 48 | CPP |
| HYPERBOOM variants | MotorCity / MotorCityPlus | 10 / 49 | CPP |

These names/codes describe the inspected app, not tested devices. Do not select
a codec solely from the retail name. Evidence: `feat-types-init.json`.

Model-specific feature providers combine feature support and minimum firmware
versions. The inspected Titus and MenHum providers treat unlisted features as
available, while listed entries require supported status, a nonempty minimum
version and sufficiently new firmware. That permissive default is an observed
app behavior, not proof that every unlisted feature works. A Linux client should
surface verified capabilities and handle unsupported-command replies.

## PartyUp and event-driven state

`XupController` marks an added receiver CONNECTING and queues an `XupAddCommand`.
The command calls `Device.addReceiverToBroadcast`, has busy-retry behavior and
then waits for a matching receiver-added event. The traced completion path
takes one matching event with a **30-second timeout**. A command ACK is therefore
not sufficient evidence that a speaker joined the group. Evidence:
`feat-xup-add-method.json`, `feat-xup-add-command.json` and the corresponding
lambda records indexed alongside them.

Design implication: keep request/response correlation, a notification dispatcher,
per-speaker state, and an explicit grouping state machine. Expose pending,
completed, failed and timed-out states to the future UI.

## Proposed Linux boundary (design inference)

1. Use BlueZ for discovery, pairing/trust state and BLE GATT access. Discover
   the Classic SPP service's RFCOMM channel instead of assuming channel 1.
2. Separate Legacy and CPP codecs behind a common speaker API. Preserve numeric
   hardware ID, protocol version, firmware and capabilities in the device model.
3. Serialize state-changing requests as required, correlate replies, apply
   bounded timeouts, and dispatch unsolicited events independently.
4. Keep speaker battery, volume, EQ, power and grouping logic independent of the
   eventual desktop toolkit. Mark cached values stale on disconnect.
5. Let the Linux audio stack handle normal audio routing. Phone music providers,
   Android alarm scheduling and app account integrations need separate product
   decisions; they are not automatically reproduced by Bluetooth commands.

This pass intentionally does not choose a UI toolkit or draw screens.

## Remaining validation before claiming parity

- Identify the actual speaker model, hardware ID and firmware from live data.
- Confirm SPP service/channel discovery and benign queries on Linux hardware.
- Capture and compare known request/reply pairs; test packet fragmentation,
  notification ACKs, reconnect behavior and command timing.
- Validate BLE wake identity requirements and adapter-address handling.
- Finish CPP payloads, custom EQ gain ranges, alarm semantics, grouping teardown,
  cache invalidation, button events and notification masks.
- Audit firmware-update logic separately before implementing OTA. Firmware and
  flash-related enum entries are research inventory, not an implemented feature.
- Test each claimed speaker family and firmware; static enum presence is not a
  compatibility matrix.

The current outcome is a reusable protocol map and evidence baseline for the
next design discussion, not a completed reverse engineering of every feature.
