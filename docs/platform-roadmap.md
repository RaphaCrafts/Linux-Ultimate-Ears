# Platform scope

Updated 2026-10-24.

- **Linux:** primary desktop application. Version 0.1.18 reconciles Computer Mix
  on refresh/startup and releases a stale default route after speaker loss. A mix
  starts only through an explicit action with two distinct available outputs.
- **Android:** native phone interface and the same documented legacy speaker
  control commands. See the [feature matrix](../android/README.md). Physical
  phone validation and a public-API-compatible BLE wake solution remain open.
  Computer Mix depends on Linux PipeWire and is not portable as implemented.
- **Windows:** experimental desktop source launch via `Speaker-Studio.bat`.
  The shared Qt interface and legacy command codec use native WinRT RFCOMM;
  dependencies install in `.venv-windows` on first launch. Pairing and music
  output selection use Windows Settings. Search refreshes saved Classic
  pairings. Computer mix and BLE remote wake are unavailable. Windows physical
  speaker validation remains open; Linux hardware results do not verify this
  transport. There is no standalone Windows executable release yet.
