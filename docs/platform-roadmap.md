# Platform scope

Updated 2026-10-24.

- **Linux:** primary desktop application. Version 0.1.18 reconciles Computer Mix
  on refresh/startup and releases a stale default route after speaker loss. A mix
  starts only through an explicit action with two distinct available outputs.
- **Android:** native phone interface and the same documented legacy speaker
  control commands. See the [feature matrix](../android/README.md). Physical
  phone validation and a public-API-compatible BLE wake solution remain open.
  Computer Mix depends on Linux PipeWire and is not portable as implemented.
- **Windows:** parked at the user's request. No Windows implementation or release
  is part of this change. Future work must first assess Windows Bluetooth control
  access, native audio routing and packaging; Linux PipeWire cannot be assumed.
