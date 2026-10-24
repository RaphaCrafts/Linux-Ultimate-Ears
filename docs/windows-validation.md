# Windows feature audit

Date: 2026-10-24. Environment: Windows x64, Python 3.13, Qt 6.8.3,
PyWinRT 3.2.1. No Bluetooth addresses are included in this report.

The automated suite passes **140 tests**, with one AppImage POSIX-path test
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
| Native PartyUp, stereo, balance, individual receiver levels | Shared protocol/controller tests pass; physical Windows two-speaker behavior remains unverified. |
| Music output | Select the speaker/host in Windows Sound settings. Audio streaming and audible synchronization were not measured. |
| Computer mix | Linux PipeWire feature; disabled on Windows. |

## Remaining hardware limitation

The other matched paired speaker exposed a Serial Port service while awake,
but Windows RFCOMM connection failed with `WSAENETUNREACH` (network unreachable).
The cause has not been established. Do not treat this as a verified PartyUp
setup or assume that all saved pairings can currently connect. Check competing
UE apps/audio sources and Windows Bluetooth connectivity before further tests.

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

BLE API usage follows Microsoft's [GATT client documentation](https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/gatt-client)
and PyWinRT's [event/threading and async guidance](https://pywinrt.readthedocs.io/en/latest/types/).
Packet evidence remains in [implementation-protocol.md](implementation-protocol.md).
