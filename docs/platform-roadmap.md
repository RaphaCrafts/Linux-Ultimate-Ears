# Platform scope

Updated 2026-10-24.

- **Linux:** primary desktop application. Version 0.1.18 reconciles Computer Mix
  on refresh/startup and releases a stale default route after speaker loss. A mix
  starts only through an explicit action with two distinct available outputs.
- **Android:** native phone interface and the same documented legacy speaker
  control commands. See the [feature matrix](../android/README.md). Physical
  long-duration phone validation and a public-API-compatible BLE wake solution
  remain open. A ZenFone 11 Ultra completed a two-speaker host-mediated join
  and initial smooth playback check in 0.3.1; see [Android validation](android-validation.md).
  **Phone mix & wake** shows the current Android media routes and opens the
  system output controls. Independent streaming depends on the phone's
  multi-output support.
- **Windows:** experimental desktop source launch via `Speaker-Studio.bat`.
  The shared Qt interface and legacy command codec use native WinRT RFCOMM;
  dependencies install in `.venv-windows` on first launch. Pairing and music
  output selection use Windows Settings. Search refreshes saved Classic
  pairings and supported BLE sleep signals. Remote wake and a power-off/wake/
  reconnect cycle passed on a physical MEGABOOM 3. A real pair also passed native
  PartyUp, Stereo/Double Up, balance, and group-volume command checks. Audible
  Stereo routing and balance were user-confirmed. Other models, receiver proxy
  levels, and long playback synchronization remain unverified; see the
  [Windows validation report](windows-validation.md). Experimental Windows
  Computer Mix mirrors a selected WASAPI output to other render endpoints.
  There is no standalone Windows executable release yet.
