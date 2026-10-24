# Windows feature audit

Date: 2026-10-24. Environment: Windows x64, Python 3.13, Qt 6.8.3,
PyWinRT 3.2.1. No Bluetooth addresses are included in this report.

The automated suite passes **143 tests**, with one AppImage POSIX-path test
skipped on Windows. Dependency consistency, the batch launcher, native window
rendering, and the real Qt Bluetooth worker were checked separately.

## Physical speaker checks

A MEGABOOM 3 identified itself as `HUMBOLDT`, firmware `1.6.45`. Tests used
same-value writes wherever possible. Its original volume, name, stored custom
bands, and Vocal preset were preserved/restored. Writing stored custom bands
automatically selects Custom on this firmware; Vocal was explicitly restored
and read back afterward. These checks verify command/response behavior, not
every possible setting or the audible effect of each curve.

| Feature | Windows result |
| --- | --- |
| Pairing inventory | Verified against the endpoint's actual pairing flag. The enumeration interface flag can incorrectly be false. |
| Sleeping-speaker discovery | Two validated FE61 signals matched exact saved Classic pairings, including custom speaker names. |
| Remote wake | GATT write followed by successful RFCOMM identity and state readback on a physical MEGABOOM 3. |
| Power off and wake again | Verified power-off command, fresh sleeping beacon, BLE wake, and successful control reconnection. |
| Model, firmware, battery, volume, EQ, custom bands | Read successfully, including repeated refresh. |
| Volume setting | Same-level write and readback passed. |
| Built-in sound profile | Same-preset write and readback passed; original Vocal preset restored after the custom-band test. |
| Custom EQ | Existing stored bytes reapplied and read back. Listening and arbitrary new curves remain unverified. |
| Rename | Existing name reapplied and read back. Windows manages its local Bluetooth label separately. |
| Battery announcement | Command acknowledged. Human confirmation of the audible announcement remains separate. |
| Disconnect and reconnect | Verified without removing pairing. |
| Artwork and remembered model | Real finish readback, persisted appearance, and native UI rendering checked. |
| Live worker shutdown | Native window connected through its QThread worker and closed with a live RFCOMM reader, without errors or a remaining worker thread. |
| Native PartyUp | Real MEGABOOM 3 pair: join, membership status, member removal, and ending the group passed. |
| Stereo / Double Up | Both modes were set and read back on the real pair. The user confirmed the left-only tone came from the purple host and the right-only tone from the pink receiver. Native handoff needs settling time after a new join. |
| Stereo balance | Position writes/readback passed. With audio sent to both channels, the user confirmed that full-left emphasis played through the purple host and full-right emphasis through the pink receiver. The original setting was restored. |
| Group volume | Master level and synchronization command acknowledged on the real pair; both original standalone levels were subsequently restored and verified. |
| Individual levels | Host direct control works. The grouped receiver relinquishes direct control; its host proxy did not provide a confirmed level on this firmware, so no unconfirmed receiver write was attempted. |
| Music output | The user selected the purple host in Windows Sound settings and confirmed all four short stereo/balance tones matched the expected purple/pink/purple/pink sequence. Long-duration music synchronization, latency, and drift were not measured. |
| Computer mix | Linux PipeWire feature; disabled on Windows. |

## Initial connection failure and follow-up

The other matched paired speaker exposed a Serial Port service while awake,
but Windows RFCOMM connection failed with `WSAENETUNREACH` (network unreachable).
Windows reported a saved pairing, successful SPP discovery, and `ALLOWED` access.
Refreshing that speaker's Windows pairing resolved the failure; both units then
connected and identified as MEGABOOM 3. The exact cause of the old pairing's
failure was not established.

With both units initially off, the purple unit again woke and completed control
readback. The pink unit's wake request was accepted and three fresh BLE scans
reported it awake even while its old Classic pairing was failing. Awake BLE
state alone did not verify working controls. The purple unit was powered off
again after that pass. After re-pairing, both units connected and the pair
completed the group-control checks above. The test group was ended and both
original volume levels were restored and read back.

For the listening check, the user selected the purple unit as Windows output.
Four quiet tones tested left-only routing, right-only routing, both-channel
audio with full-left balance, and both-channel audio with full-right balance.
The first playback was missed because the user was wearing headphones; it was
replayed. The user then confirmed that all four tones came from the expected
purple/pink/purple/pink speakers. The balance setting was restored and the test
group was ended. This is an audible routing/balance check, not a long playback
stability or synchronization measurement.

Switching mode immediately after joining could drop the new receiver. Waiting
six seconds for handoff kept membership stable in the subsequent physical trial.
The controller now observes that settling interval before a mode change.
Windows can also retain an apparently connected receiver control socket that
stalls after native handoff. The app releases that direct stream after joining,
uses host group controls, and handles a stale direct-level timeout without
invalidating the host. Receiver proxy confirmation remains a firmware limitation.

## Fixes covered by the audit

- Use `BluetoothDevice.device_information.pairing`, rather than the enumeration
  interface's pairing flag, to decide whether controls may connect.
- Match renamed speakers using validated BLE manufacturer data and the exact
  saved Classic address. Expire wake signals after 45 seconds; reject unrelated
  manufacturer IDs, layouts, and known incompatible model names.
- Discover the exact GATT wake UUID, select the characteristic's supported write
  mode, and use the local Bluetooth adapter's address in the documented payload.
  A successful GATT write is followed by control connection/identity verification.
- Allow Read existing group on the selected paired Windows speaker without
  requiring Linux A2DP inventory. Native PartyUp setup does not invoke Linux
  audio routing; users choose the host in Windows Sound settings.
- Drain cancellation of native reads before COM teardown and stop/unregister
  cancelled BLE scans. Regression coverage checks single cancellation and cleanup.
- Reinstall the editable source package if the repository directory moves.
- Settle a fresh receiver handoff before switching modes, release its stale
  direct Windows stream, and contain receiver-level timeouts to that receiver.

BLE API usage follows Microsoft's [GATT client documentation](https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/gatt-client)
and PyWinRT's [event/threading and async guidance](https://pywinrt.readthedocs.io/en/latest/types/).
Packet evidence remains in [implementation-protocol.md](implementation-protocol.md).
