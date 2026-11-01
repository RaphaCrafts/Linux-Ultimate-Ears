# Android validation

## ZenFone 11 Ultra, 2026-11-01

Device: ASUS AI2401, Android 16 / API 36. Raw USB-debugging diagnostics and
captures remain in ignored `.local/android-phone-research/`. No root, firmware
modification, Bluetooth reset or removal of pairings was used.

### Independent phone streams

The Bluetooth service reported a maximum of five connected audio devices. A
USB-debugging helper, running as shell UID 2000, connected the two paired UE
speakers through A2DP simultaneously. However, AudioManager exposed only one
A2DP output. Multiple connections did not establish multiple audio streams.

The shell account had `MODIFY_AUDIO_ROUTING` and `BLUETOOTH_PRIVILEGED`. A request
to `AudioManager.setPreferredDevicesForStrategy` for both speaker addresses and
the media strategy returned false. Audio policy logged an unsupported device
selection and error -22; preferred-device readback remained empty. The original
empty preference was preserved. Thus ordinary API permission restrictions were
not the only obstacle in this test.

A separate exploratory Classic L2CAP connection to AVDTP PSM 25 failed during
local socket initialization. No AVDTP discovery reply or custom audio stream
was obtained. Both original A2DP connections were restored and verified.
This failed experiment does not establish that every possible custom transport
is impossible, nor does it validate a Shizuku-based streaming implementation.

**Independent Phone Mix remains unimplemented.** Android's privileged combined
routing interface and an application's ordinary per-track device preference
are distinct APIs. The official references are [combined audio routing](https://source.android.com/docs/core/audio/combined-audio-routing)
and [AudioTrack routing](https://developer.android.com/reference/android/media/AudioTrack#setPreferredDevice(android.media.AudioDeviceInfo)).

### Failed receiver join and 0.3.1 fix

With 0.3.0, adding the purple receiver from a session with the pink host failed
with `read failed, socket might closed or timeout, read ret: -1`. The app's
host connection succeeded. Its subsequent receiver SPP service lookup completed
without a usable server channel (`scn: 0`), before any host add request was sent.
The code required a separate receiver control session to validate identity and
configuration before issuing the actual host-side join. That prerequisite
blocked the join in this case. The diagnostics do not establish why the
receiver's SPP service was unavailable.

Version 0.3.1 sends the join through the already connected, capability-checked
host. It does not open a receiver control socket. Membership still requires a
successful correlated receiver completion or a host inventory record reporting
that receiver as playing this broadcast. A queue ACK is insufficient. Receiver
compatibility/admission is decided by the host; the app no longer claims to
have independently queried the receiver's model or configuration before joining.

On the physical phone after installing 0.3.1, the app displayed the pink host
and purple receiver with a returned receiver battery reading and Double Up
selected. The user reported **both speakers playing smoothly so far**. This
establishes a successful join and initial listening check, not long-duration
stability or proof that all previous stutters had the same cause.

### Additional control-path changes

- A successful join starts a six-second settling window before another add,
  playback-mode change or group-volume synchronization. This carries over the
  desktop's existing handoff precaution; it is not a measured firmware constant.
- Selecting an already active mode reads the configuration but does not rewrite
  the live broadcast configuration.
- Group mutations retry only an explicit BUSY rejection, at most three attempts
  with 300/600 ms backoff. Timeouts and other rejections are not retried. There
  is no automatic regrouping or periodic remote polling.
- Valid duplicate/unsolicited receiver-level results are acknowledged even
  without a waiting request. Only valid levels for current members update the
  cache; late results cannot recreate removed members. This correction is
  regression-tested, not established as the cause of an audible dropout.

APK assembly, 28 JVM tests and lint passed for 0.3.2. The only lint advisory remains
`OldTargetApi`. Emulator navigation, primary controls, stereo inventory gating
and settings smoke checks passed. Tests include host-only joins, waiting beyond
the queue ACK, handoff timing, mode no-ops, busy backoff, permanent rejection and
duplicate-result acknowledgements. They do not simulate acoustic synchronization.

### UE-only directory in 0.3.2

The main connection list now shows recognized UE model names and locally
remembered speakers. A successful supported-host connection or confirmed
PartyUp membership records the address in app-private preferences. Custom names
therefore remain visible on later sessions. Names suggest devices for discovery;
they never establish model support or authorize controls. Unrecognized custom
names can be selected once through **Add paired speaker**. Unrelated bonded
devices stay out of the main list, with no active Bluetooth scan or new permission.
On the physical phone, both custom-named speakers were present in the private
remembered directory after installing 0.3.2.
Tests cover recognized model names, unrelated device names and confirmed custom
names. Remembered entries are intersected with Android's current bonded devices,
so removed pairings do not remain as disconnected ghost entries.

## Next listening checks

Use the same downloaded track and speaker placement for comparisons. Start with
Double Up, then test Stereo after the join settles. Compare ordinary listening
with controls connected against **Release controls**, without recreating the
group between observations. Record elapsed time, whether one or both speakers
cut out, and whether the phone's audio output changes. Keep other controllers
closed during a comparison.

Earlier Linux observations include stuttering with all control sessions closed;
see [protocol observations](implementation-protocol.md) and the
[Computer Mix experiment](computer-mix-experiment.md). App-side improvements
cannot be assumed to repair buffering or synchronization inside speaker firmware.

## UI and appearance update, 0.4.0

Speakers and Mix have been merged into one **Speakers** tab. It keeps the former
Mix flow, showing one large speaker card when standalone and shared group volume,
compact member cards and playback options when broadcasting. Sound is the only
other tab. Old saved Mix navigation restores to Speakers.

The host finish is queried once on control connection using documented
0x01be/0x01bf. A BUSY or unsupported finish reply leaves appearance optional;
known colours already saved locally are retained. Group inventories now retain
their unsigned 16-bit finish codes. BOOM 3 and MEGABOOM 3 mappings match the
[finish evidence](implementation-protocol.md#finish-detection). Unknown codes
remain neutral, and no new model capability is inferred from an appearance.

Detected finishes and manual palette overrides are separate app-private values
keyed by speaker address. Manual choices take priority until the user selects
Detected colour. There is no colour write to the speaker and no new remote poll.
Unknown or missing finish data does not overwrite a saved valid finish.

Shared cards display speaker role, coloured artwork, a battery icon and percentage,
and individual volume where a real level is available. Group volume remains a
host-referenced synchronization control, not an average of individual sliders.
Unavailable readings show a dash. Low battery has an amber/red visual indicator;
charging is not asserted because it is not currently represented in the controller.

The custom EQ preview shows the saved/draft curve, explicitly distinguished from
an active built-in preset. Its signed relative -100..+100 display preserves the
original -128..127 wire range and does not claim calibrated dB. A flat reset is
local until Apply. Native SeekBars remain the accessible editing controls.

Validation: 31 JVM tests, APK assembly and lint passed (the existing OldTargetApi
warning remains). The emulator smoke check passed colour persistence/manual
priority, unavailable finish retention, low/unknown battery states, EQ drafts
across tabs, accessible EQ and volume edits, long names, the colour picker and
stereo gating. Layouts were also visually checked at 1.3× system font size.
Screenshots use simulated readings.

The 0.4.0 APK was installed on the connected ZenFone with app data preserved.
Reconnecting to the existing pink host read its finish as 0x0431 (Unicorn pink);
the receiver inventory supplied 0x0119 (Purple). Both were displayed and saved
in the private appearance directory. No group membership, volume or EQ write
was performed for that appearance check. Actual EQ edits and manual colour
selection were exercised in the fake-transport emulator, not asserted as new
physical-speaker audio validation.
