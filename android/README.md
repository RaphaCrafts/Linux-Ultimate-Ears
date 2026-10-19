# Speaker Studio for Android

A small native Android companion for the Linux Speaker Studio project. It uses
original Java code and the same documented legacy control protocol. The dark
cards, cyan accents, Speaker / PartyUp navigation and speaker illustration adapt
the desktop design. No vendor APK code or product photography is bundled.

## Open in Android Studio

1. Open **this `android` folder**, not the repository root.
2. Use Android Studio Ladybug (2024.2.1) or newer. Select its bundled full JDK
   (17 or 21) as the Gradle JDK in Settings → Build Tools → Gradle.
3. Allow Gradle sync and install Android SDK Platform 35 and Build Tools 34.0.0
   if requested. The Gradle wrapper is included (8.10.2); AGP is pinned to 8.7.3.
4. Run the `app` configuration on a physical Android phone (Android 8.0+).
   The first connection on Android 12+ requests Nearby devices permission.

Command line, with a full JDK and `ANDROID_HOME` pointing to your SDK:

```sh
./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

The installable debug APK is `app/build/outputs/apk/debug/app-debug.apk`.
`local.properties`, IDE files, SDK paths, build outputs and signing keys are
ignored. Android Studio can generate your own release signing configuration.

## Play through two or more speakers

1. Turn on each speaker and pair it in Android Bluetooth settings. Close the
   official UE app and other controllers that may own its control channel.
2. Connect Android **media audio to the intended host speaker**. This app opens
   a separate RFCOMM control socket; it does not select or claim the media route.
3. In Speaker Studio choose that host, then **Add a paired speaker** for each
   receiver. Pairing lists may include unrelated devices; actual protocol
   identity and grouping capability are checked before sending group commands.
4. Wait for each confirmed join. If instructed, press the receiver's Bluetooth
   button twice and retry. A queue ACK alone never marks a join successful.
5. Use **Double Up** for full sound on all speakers. **Stereo** assigns the host
   left and one receiver right, and requires a complete report confirming exactly
   one receiver. Switch to Double Up before adding another speaker.
6. Play music from your usual media app. **Release controls for listening**, or
   simply leave the app, to close the control channel and preserve the group.
   **End group** explicitly stops the native broadcast.

The app does not poll during playback. Refresh requests are explicit. Returning
from Settings, backgrounding or rotating the activity releases controls; reconnect
to read configuration again. An existing broadcasting host remains endable even
if its complete member inventory has not arrived. The legacy protocol supplies
inventory through unsolicited `0x0416` reports; no undocumented inventory query is
invented. If no report arrives, Stereo remains disabled and the UI says that full
member details are pending.

## Compatibility and limits

- Primary targets: **MEGABOOM 3 and BOOM 3**. Legacy identities for original BOOM,
  BOOM 2 and MEGABOOM are recognized, with PartyUp enabled only after a successful
  configuration query. Identity recognition is not hardware certification.
- BOOM 4, MEGABOOM 4, WONDERBOOM, EVERBOOM, EPICBOOM and HYPERBOOM are outside this
  implementation. Names and artwork never grant compatibility.
- This uses **native PartyUp**: one Bluetooth media stream to a host that relays
  audio to its receivers. It does not implement the Linux PipeWire Computer mix
  experiment or independent phone-to-many A2DP streams. No private Android audio
  APIs or reflection are used. Phone-specific Dual Audio features are separate.
- No maximum receiver count is claimed. Firmware/model compatibility determines
  the native limit. Android operation, stereo audio and groups of three or more
  **have not been verified on physical hardware** in this task. Earlier Linux
  observations with two MEGABOOM 3 units are documented separately; they do not
  establish Android audio quality or fix previously reported stuttering.
- This first Android version focuses on grouping and volume. EQ, firmware,
  individual receiver levels, BLE wake, renaming and balance editing are omitted.
- No network permission, account, telemetry, background service or stored device
  address log. Android's saved pairings remain managed by the operating system.

## Implementation and validation

`Protocol` handles framing, hardware identity and group inventory. `LegacySession`
serializes requests and acknowledges only recognized notifications. A command
timeout closes the stream to prevent late response reuse. `SpeakerController`
validates receivers before joining, correlates group notifications by command and
receiver address, and distinguishes completion from a queue ACK. A 30-second
unconfirmed group change closes controls; reconnect and inspect before retrying.
The controller uses the documented SPP UUID through Android service discovery,
not a hardcoded RFCOMM channel.

JVM tests exercise fragmented/coalesced frames, malformed inventory, playing-only
membership, identity rejection, ACK/query separation, unrelated ACKs, error
responses, timeouts, unsolicited balance ACKs and disconnects. Tests do not
substitute for a real Bluetooth radio. No emulator or physical phone was connected
for this task; runtime layout, permission flows and speaker audio need a device run.

For the hardware check, confirm the media route, join two speakers, verify both
play music in Double Up, verify distinct left/right audio in Stereo, release
controls and listen for dropouts, remove/rejoin a receiver, reconnect to an existing
group, then try a third speaker in Double Up. Also test permission denial, Bluetooth
off, an unreachable receiver and an interrupted join. Keep captures containing
addresses under ignored `.local/` as required by the repository research policy.

Protocol background: [implementation evidence](../docs/implementation-protocol.md)
and [research](../docs/protocol-research.md).
Android references: [RFCOMM client connections](https://developer.android.com/develop/connectivity/bluetooth/connect-bluetooth-devices),
[permissions](https://developer.android.com/develop/connectivity/bluetooth/bt-permissions),
and [AGP 8.7 compatibility](https://developer.android.com/build/releases/agp-8-7-0-release-notes).

The project is distributed under the repository's GPL-3.0 license. The unmodified
Gradle wrapper is Apache-2.0 licensed; see [Gradle wrapper licensing](https://github.com/gradle/gradle/blob/v8.10.2/LICENSE).

Validation on 2026-10-19: debug APK assembly, all 12 JVM tests, and Android lint
passed using the installed Android SDK and a full JDK 21. Lint retains one
`OldTargetApi` advisory because this first build deliberately targets API 35;
there are no lint errors. The project is intended for local Android Studio builds,
not asserted to meet future Play Store target-level requirements.
