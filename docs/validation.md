# First release validation

## Linux pairing recovery (2026-10-29)

Both saved MEGABOOM 3 pairings were discoverable but rejected RFCOMM control
connections with `PermissionError(13)`. Linux audio connection attempts also
failed. Removing and recreating each pairing restored audio transports and
successful model, firmware, battery, volume and EQ reads through the published
AppImage. The original cause of the invalid pairings was not established;
Windows/Linux key replacement remains a possible explanation.

The controller now explains the possible pairing mismatch on Linux control
permission failures and stops retrying that failure within the same click.
Regression coverage verifies one connection attempt, visible recovery guidance,
and cleared connection/busy state. The suite passes 134 tests with 11 Windows-only
tests skipped on Linux. No pairing-key synchronization has been performed.

Validation date: 2026-10-18. No Bluetooth address is recorded here.

## Real hardware

A paired **MEGABOOM 3**, identity `HUMBOLDT`, firmware **1.6.45** was reached from
Linux using its advertised Serial Port service and an RFCOMM control socket.

Verified live:

- Service discovery and connection from the application implementation.
- Model and firmware identification, battery and current volume readings.
- EQ preset readback and capability-query response.
- The complete Qt background-worker / BlueZ / transport / model path.
- Volume write/ACK/readback by reapplying the existing raw volume value.
- EQ write/ACK/readback by reapplying the existing preset code.
- Custom five-band EQ write/ACK/readback by reapplying the existing stored bytes.
- Broadcast configuration query (returned inactive state).

Those same-value write tests preserved the user's settings. They do not prove
all volume/preset combinations, every command, every firmware or other models.
Battery display follows the app's stepped convention. Firmware and model
identification are read from the speaker, not the selected product image.

The **built AppImage itself** also passed a real-speaker diagnostic through its
bundled Bluetooth helper and Python/Qt runtime. Its normal FUSE-backed execution,
X11 window startup and extract-and-run fallback were checked on the build host.

## Automated checks

64 automated tests passed in the final build.

Protocol tests cover arbitrary stream fragmentation and concatenation, malformed
lengths and encoding bounds, ACK correlation, unsupported-command errors,
notification dispatch, connection invalidation after a timeout, battery rounding,
31/15-step volume normalization and fallback restricted to unsupported replies.

Offscreen Qt tests verify demo mode does not start Bluetooth, speaker EQ state
is separate, images load, and navigation works. Packaging checks exercise the
native window and bundled images before and after AppImage construction.

The native screenshot in the README shows actual MEGABOOM 3 readings. Product
colour was chosen locally for the screenshot; colour does not determine control
compatibility.

## Current limits

Only one physical speaker was available. Multi-speaker behavior requires
additional hardware tests; add/remove and notification parsing are covered
with deterministic simulated peer responses. Custom EQ uses five signed byte levels, confirmed against the vendor parser
and its +/-128 view offset. The UI presents relative levels, not an assumed
calibrated dB mapping. CPP control, firmware updates, phone playlist integrations,
remote wake and alarms are not claimed by this first build.

## Interface update 0.1.1

Fixed case-insensitive artwork matching for paired speakers before a control
connection exists. Added the official historical Unicorn pink MEGABOOM 3
packshot, a battery charge bar and explicit disconnected battery guidance.
Removed the demo entry from the user interface. A regression test covers the
paired/disconnected state, colour persistence and charge display. The packaging
smoke check now loads every catalogued image and a model inferred from its name.

## Artwork and icon update 0.1.2

Expanded to 39 official colour packshots across eight models. Collection preserves
existing files and records failed pages/probes. Exhaustive historical or future
variant coverage is not claimed. Original neutral SVG illustrations provide
family-specific defaults and missing/unreadable-file fallbacks. An additional
UI regression covers known, older and unlisted model families, unknown finishes,
explicit Generic selection and a missing packshot. Packaging checks load all
packshots, all generic illustrations and the original blue app icon.

## Colour and desktop integration 0.1.3

Read-only testing on the real HUMBOLDT MEGABOOM 3 returned colour code 0x0431.
The integrated controller resolves this to Unicorn pink, with current battery,
volume and EQ reads preserved. Known base BOOM 3/MEGABOOM 3 colour mappings were
recovered statically with REA; only this physical finish is hardware-verified.
Tests cover unknown, malformed and unsupported colour replies, model scoping,
automatic selection and manual override.

Live X11 checks confirmed WM_CLASS and _GTK_APPLICATION_ID both match
`speaker-studio`, nonempty _NET_WM_ICON pixel data, and an available tray host
with the tray icon visible through Qt. The icon supplies sizes through 256px:
a lone 512px PNG exceeded this host's X11 request limit and published empty icon
data. The actual desktop launcher parser (GIO) launched temporary harmless test
executables whose filenames include spaces, quotes, dollar signs, backticks,
backslashes and percent signs. Persistent launcher tests also cover moved
AppImages and preservation of unrelated shortcuts. Tray tests verify explicit
hide/restore, cleanup and refusal to hide when no tray is available. These checks
do not establish tray rendering on every Linux desktop.

The final AppImage repeated the real-speaker colour diagnostic successfully.
A normal packaged launch using a temporary XDG data directory created a valid
persistent launcher and published the matching X11 app identity and icon pixels.

## Bluetooth, PartyUp and wake update 0.1.4

Regression tests cover real BlueZ link-loss transitions, adapter power-off,
unpairing/removal, pending PartyUp completion cancellation, explicit disconnect
while busy, and a stale initial profile snapshot. Speaker clicks and the always
available Back to speaker action leave PartyUp. Disconnected group UI clears
volume/debounce state and distinguishes saved pairing from a live connection.
The Bluetooth worker retries after service failures rather than silently stopping.

BLE tests reject unknown/truncated packets, invalid identities, stale beacons and
name-only association. They check the host-address payload, target characteristic
scope, advertised GATT write flags and cleanup on failures. UI tests cover the
sleeping-speaker Turn on action and expiry of wake availability.

Live 2026-10-18: two paired MEGABOOM 3 beacons were observed. The user turned off
the Ultraviolet purple unit, its Connected property changed to false, and its
manufacturer power byte changed20 to00. The implementation found exactly one
sleeping validated radio, wrote the legacy wake command and connected through
Classic control. Readback confirmed HUMBOLDT, firmware1.6.45, Ultraviolet purple,
battery100 and connected/awake state. The other (Unicorn pink) speaker was not
sent a power command. No live new PartyUp group was created for this update;
group-disconnect behavior is covered by deterministic tests.

The final AppImage passed normal startup/offline image checks and a read-only
diagnostic of the woken purple speaker through its bundled transport runtime.

## Appearance, rename and connection update 0.1.5

Per-speaker detected colour/model storage survives an app restart and keeps
manual overrides separate. Tests cover renamed/offline speakers retaining the
correct packshot, Bluetooth audio links without control sockets, error retention,
cancelled connections and a smaller240px speaker image. Cached verified models
also keep discovery and wake available after a device is renamed.

Connect performs a short shared BLE discovery when needed before deciding
between direct control connection and targeted wake. Concurrent requests share
one scan rather than returning prematurely from an in-progress search. Completed
wake requests discard the pre-wake beacon; a verified control connection cannot
be labelled asleep. Transient connection setup is protected from stale BlueZ
link transitions, while unpairing/adapter power-off still invalidate controls.

Live test: purple was directly reachable; pink initially failed Classic service
discovery. The revised Connect path detected the sleeping pink speaker and woke
it. Both control connections then succeeded concurrently in the same controller.
Purple also had an audio transport; pink had a Bluetooth link and app controls
without an audio transport, now explicitly distinguished in the UI.

The real pink speaker accepted a same-current-name SetName and fresh readback,
with its original name preserved. UTF-8 payloads, trimming, limits, malformed
responses and post-readback alias synchronization are also tested offline.

The rebuilt AppImage passed normal startup/image checks and a real-speaker
read-only diagnostic. Native screenshots show both control connections active
with the compact tile, actual detected artwork and Rename action.

## Playback stability update 0.1.6

Found application behaviors capable of disrupting playback: full setting queries
every15seconds; automatic Classic inquiry when a speaker had a Bluetooth link
but no audio transport; and Device.Disconnect on a failed wake, which can tear
down an audio connection established by another client. These observations do not
prove which one caused every reported audible dropout. Host journals also record
WirePlumber codec/profile switching errors, without packet-level correlation.

The update defers automatic speaker queries while any local BlueZ media transport
is active, pending or broadcasting, including unrelated audio devices. Unknown
D-Bus audio state also defers them. Idle automatic refresh is limited to battery
and volume once a minute. Manual controls and Refresh remain explicit actions.
Already-linked devices bypass discovery. Automatic sleep searches use LE only;
manual Search uses LE while Bluetooth audio is active. Wake no longer invokes
Device.Disconnect on failures, and awake units do not receive generic
Device.Connect or wake writes. A temporary local inventory failure preserves
healthy RFCOMM sessions until an actual socket or link loss is observed.

Regression tests cover silent background polls during streaming, reduced idle
queries, active/idle transport detection, LE scan filtering, absence of generic
profile connects for awake speakers, no failed-wake disconnect, and preservation
of healthy sessions after local inventory errors. Subjective listening and longer
hardware stability remain separate from these deterministic checks.

A passive check on the user's Linux host observed an active Bluetooth audio
transport in all eight samples over approximately16seconds. Calling the revised
automatic poll sent zero speaker commands. This checked the live playback gate
without opening a new speaker control connection or changing audio settings;
it does not establish absence of audible dropouts over a longer listening session.

Follow-up with the user's old app closed and music playing: the revised controller
opened a real control connection to the actively streaming UE speaker. Across
15 samples over30seconds, audio remained active and both the BlueZ link and
RFCOMM control session remained connected in every sample. Automatic polls sent
zero commands after initial connection/readback. No audio settings were changed.
The test closed only its own control socket afterwards. This short observation
does not replace longer subjective listening.

## PartyUp balance and desktop icon update 0.1.7

The running X11 window advertised WM_CLASS speaker-studio and the correct
multi-size window icon. The user's hicolor icon cache predated the installed
packshot icon. The managed desktop entry now references a stable absolute icon
path, bypassing that cache, and launcher identity hints are set before Qt starts.
Normal AppImage startup updated the user's managed launcher. Gio resolved its
icon as a FileIcon at the installed PNG path, and a live taskbar capture visually
confirmed the blue speaker icon instead of the generic gear. Only the temporary
test instance was closed. Both two- and three-speaker preview screenshots were
rendered and visually inspected; they are explicitly marked as simulated data.

Live MEGABOOM 3 pair: the purple host was broadcasting to the pink receiver.
Native balance query returned00, a small SetTWSBalance change read backfe, and
restoration read back the exact original00. Host volume remained29percent.
A separate Classic control connection to the receiving pink speaker was not
reachable while grouped. Its proxy level query accepted a two-byte attribute ID
but did not emit a confirmed level, so no proxy volume write was attempted.
The shorter attribute format from static Android setter code was rejected with
an unexpected-size error. That firmware cannot be claimed to support the proxy
level path. Larger-group layout and correlation/error handling are tested offline;
three-speaker operation and receiver proxy volume writes are not hardware verified.

Tests cover native balance encoding/endpoints, exactly-two membership validation,
receiver ACK versus delivery/readback, unmatched notifications, malformed levels,
blocked writes without a reading, group loss, two/three-speaker layouts, dragging
through background updates, and animation states/timer suspension when hidden.

## Stereo balance prerequisite update 0.1.8

User reported that balance produced no audible change. The previous hardware
test established only register write/readback, not sound attenuation. Static
inspection now confirms that the Android view only shows its balance panel in
stereo mode, and its Stereo action sets BroadcastAudioOptions.STEREO_LEFT0x50.
Linux previously always created Double Up groups with audio option00 and did not
retain or expose this second broadcast-configuration byte.

The app now stores and displays the actual playback mode, provides explicit
Double Up/Stereo selection for a pair, preserves the current broadcast-state
byte when switching, and requires a fresh matching mode readback. Balance is
disabled in Double Up. Every balance action rechecks the actual mode and refuses
to write if another app changed it. Tests cover mode prerequisites, successful
and ignored mode switches, preserved group membership, and UI mode changes.
Audible effect still requires a listening test; register acceptance alone is not
reported as confirmation of working acoustic balance.

## Mode buttons, smooth controls and unsolicited updates 0.1.9

Playback mode now uses checked Double Up/Stereo buttons. Unchanged controller
snapshots are suppressed; sidebar items and PartyUp cards are retained when their
displayed content is unchanged. Balance remains interactive while its request
finishes. A450ms trailing debounce combines quick releases/keyboard adjustments;
only one request is in flight, the latest edit waits for it, and old readbacks
cannot replace a newer edit. Navigation and loss of group/mode cancel queued edits.

Live40-second playback observations with the old app closed: before the fix,
three unsolicited0x019c balance readings were unhandled, with17 recognized group
status messages. After recognizing and acknowledging valid unsolicited balance
readings, one such reading and15 group messages were all handled. Both checks
had20/20 active-audio and connected-control samples, zero setting queries after
setup and only notification ACKs transmitted. Expected query responses continue
to complete their requests without notification ACKs, as covered by socket tests.

The user still heard stutters during testing and confirmed they continued after
all apps and the test control connection were closed. Thus the remaining audible
stutter is not fixed by these UI/control changes. Playback used standard SBC,
adapter discovery was off and Wi-Fi was on5180MHz. Short PipeWire playback error
counter checks and recent audio/Bluetooth/adapter logs showed no corresponding
playback errors. These observations do not locate the remaining wireless/audio fault.

Regression tests cover stable widget identity, quick-edit coalescing, queued edits
during an in-flight request, stale readbacks, live-mode button state, duplicate
snapshot suppression, and actual socket ACK versus query-response behavior.

A live PartyUp-off comparison exposed transient Busy replies to configuration
reads after the mode setter had already succeeded. The pair was restored with
fresh confirmation of its original0350 configuration,44 balance and09 host
volume. Configuration reads now retry bounded Busy responses without resending
the mode setter. A regression test verifies that a transition needing another
read still sends exactly one setter. This reduces misleading mode failures and
avoids restarting the same transition; it is not a claim that all wireless
stuttering has been resolved.

Further listening comparisons: the user reported PURPLE3 alone was smoother,
while both Stereo and Double Up initially stuttered with the pair. Temporarily
changing0350 to0250 stopped speaker-side discovery while preserving Stereo,
balance44 and host volume09. The user initially reported similar stutters, then
said they may have been brief and requested more assessment time. At their
explicit request,0250 was reapplied, verified and left in place without a timed
revert; all test control sockets were closed. Sustained listening confirmation
is pending. These native search settings are distinct from Linux adapter discovery.

The backend also waits for an already-running control operation rather than
silently dropping a raced balance request. A regression covers this completion
path so the UI cannot wait forever for a request the worker discarded.

## Existing group status and receiver channel 0.1.10

- Android static analysis traced PartyUp's explicit RIGHT receiver assignment
  through the legacy mapper. Join payload now uses channel2 rather than UNKNOWN0.
- Live MEGABOOM3 pair: RIGHT join completed successfully, broadcast-only Stereo
  confirmed0250, then controls closed for40seconds. User still heard stuttering.
  Finally restored and verified original0050 (PURPLE3 alone), without a volume
  setter. No audible fix claimed. No member-status notifications arrived during
  this short test, so reconnecting cannot assume an empty group from silence.
- Active broadcasts without inventory now say member details are pending;
  End group stays usable. Scan-only configuration clears stale memberships.
- Read existing group reconnects the Linux audio host, independent of the
  selected receiver, with no automatic search or regroup command.
- Regression coverage includes unknown versus confirmed-empty inventory,
  scan-only invalidation and audio-host reconnection selection.


## Drag-and-drop and existing-host selection 0.1.11

Read-only live check on2026-10-18: PURPLE3 reported broadcasting state3, audio
mode0, and two matching0x0416 notifications with PINK3 in status8 (playing this
broadcast). No speaker setting or group membership was changed. The test
control connection was closed afterward. This establishes an existing group
independently of the receiver's own Classic control availability.

- PartyUp prefers a broadcasting host, then an active Linux audio speaker, and
  excludes known group receivers from its host selector. Reversed-order UI
  regression reproduces the old incorrect receiver selection.
- Join reads current host configuration before setting broadcast mode, avoiding
  a restart from stale local state. Confirmed members make repeated joins a
  no-op. A status8 inventory confirms a pending join without requiring0x0418;
  nearby status3 cannot confirm it. Full firmware/EQ refresh was removed from
  the join completion path.
- A native Qt drag moves a ready card to a highlighted play area. MIME carries
  host and receiver; current eligibility rejects stale-host and unknown drops.
  Drop and button share the same command and wait for hardware confirmation.
- Joining previews and inline errors keep progress visible. Confirmed receivers
  have a PartyUp sidebar label. Superseded cards hide before deferred deletion
  so they do not overlap new cards during updates. Drag sources are retained
  during nested Qt drag events, then rendering catches up afterward.
- Offscreen UI captures verify the ready shelf, two-speaker balance and larger
  group layout. Screenshots use simulated devices. Native drag/drop events,
  button dispatch, stale-host rejection and asynchronous membership completion
  are covered by automated regression tests. No live regroup was performed;
  audio stuttering is not claimed fixed.


## Firmware information and official update guidance 0.1.12

The per-speaker Firmware dialog displays installed, last-read or unknown version
state without claiming an online update check. Manual reading sends only the
existing firmware query3/response4, with no setter or group change. The official
UE app link and update instructions follow Logitech’s documented mobile update
path; no supported Linux flashing interface was established. No firmware files,
version catalogue, downgrade controls or installation commands are included.
Release app controls uses the existing control-only disconnect; its label states
that audio and native PartyUp can continue. Demo controls never send commands.
Automated checks verify exact query traffic, group preservation, cached/unknown
labels, button dispatch and disabled disconnected/busy/demo actions. No hardware
firmware installation or new speaker-setting change was performed.


## Independent Computer mix playback 0.1.13

The approved live trial bypassed native PartyUp and routed Spotify to two real
Linux A2DP speaker outputs. Both outputs and the combine sink were observed
running. The user reported smooth, well-synchronised sound. The trial ended
early because pw-dump appended a JSON change array; the supervisor verified
removal of the temporary output and restoration of the original configured
output. Native PartyUp remained off. This was a short listening check, not proof
of long-duration synchronization or support across hardware and distributions.

The shared reader handles appended change arrays. The app now offers an explicit
Computer mix panel, requires two separate Linux outputs and acknowledgement
that native PartyUp is off, and guards against simultaneous native grouping.
The process-owned mix is stopped on Quit, output disappearance or process loss.
On uncertain local inventory errors it leaves healthy playback alone. Restoration
respects an output manually selected by the user while the mix was running.
The GUI remains on the Qt thread; PipeWire work runs in the backend worker.
System tools receive the original library environment when packaged.

Integrated-core validation with silent virtual sinks verified two target routes
and cleanup, deliberately skipping default selection so current music continued.
Automated checks cover snapshot parsing, start/stop restoration, user output
changes, failed restoration cleanup, native-mode guards and dialog dispatch.
The panel was visually checked for readable wrapping and scrolling.

The build now smoke-tests a separate AppImage file before atomically replacing
its published path, avoiding Linux's Text-file-busy error when the previous
AppImage is still running. Shutdown waits for bounded audio-tool operations
before disposing of the Qt worker. The final regression suite has88passing tests.

Computer mix actions remain available during a Bluetooth-inventory outage, so
Stop can restore audio without waiting for BlueZ to recover. Native Bluetooth
actions still require a ready Bluetooth service.


## EQ profiles, 0.1.15 (2026-10-23)

Regression coverage verifies all four built-ins survive edits and custom applies,
slider movement immediately becomes a draft without sending a command, baseline
reset clears the draft, and saved named profiles survive reopening the app.
Saved profiles cannot overwrite built-in names or other saved names. Subsequent
edits preserve the original saved bands. Old busy snapshots cannot erase a
pending custom apply. Malformed stored profiles are ignored. Existing backend
tests verify custom writes use the custom EQ slot (preset code 4).

Built-in preview curves retain their existing shapes. They are not measured
speaker coefficients; draft sliders start from these illustrative previews.
Physical-speaker listening and persistence of custom bands on hardware have not
been revalidated for this update.


## Integrated group methods, 0.1.16 (2026-10-23)

Tests cover a native receiver without either a control or Linux audio link,
native teardown before direct audio connection, exact output matching, connection
failure retaining selection, retry success, native group reconstruction after
stopping the mix, selection validation before teardown, serialized transitions,
and a Bluetooth startup failure clearing the UI's pending state. UI tests cover
mode switching with a disconnected receiver, dragging a paired receiver in
Computer mix mode and retry without losing group cards. BlueZ tests verify the
A2DP profile is requested even when generic Connected is already true and that
transient profile errors are retried rather than reported as success.

The revised view was rendered offscreen for visual inspection. Live inventory
confirmed the reported receiver lacked a direct Linux transport. Full hardware
switching and listening remain unverified for this release.


## Individual volumes and stable slider feedback, 0.1.17 (2026-10-23)

Computer mix volume controls resolve a fresh PipeWire node ID for an exact,
participating Bluetooth output on each edit. Tests cover independent output
selection, reconnecting node IDs, mute readback and explicit unmute on adjustment,
0–100% bounds, unavailable output handling, no writes after stopping the mix,
and operation without a BlueZ inventory or speaker control socket. Level reads
are local PipeWire operations; they do not add RFCOMM polling during playback.

UI tests cover vertical native pair controls, per-output dispatch, background
readbacks preserving edits, and acknowledgement of the actual level even when
it is quantized. The main speaker slider and native member sliders hold pending
values until the corresponding command completes; rapid volume requests wait
for an active command rather than being dropped. Unavailable backend submission
restores the last actual level. Group-volume changes retain their existing
synchronization behavior. Physical button events and forced system-wide hardware
volume synchronization are not introduced in this update.

A silent PipeWire runtime trial created two temporary null sinks without changing
the configured playback output. The new helpers set their volumes to 23% and
71%, changed only the first to 48%, and verified the second stayed at 71%. Both
temporary sinks were removed afterward. No physical speaker volumes were changed
by this trial. Both revised group views were rendered offscreen for visual QA.
Native receiver proxy volume retains its earlier hardware-verification limits.

## Experimental Windows desktop (2026-10-24)

On Windows with Python 3.13 x64 / PyWinRT 3.2.1, the audited suite passes **143 tests**;
one AppImage desktop-entry test is skipped because it asserts POSIX paths.
The Linux Computer mix backend test explicitly simulates the Linux platform.
Additional tests cover the asynchronous stream adapter, fragmented response and
notification handling, timeout closure, SPP service selection, failed connection
cleanup, and the Windows interface's disabled Computer mix option.

The real `Speaker-Studio.bat --smoke-test` successfully created its isolated
environment, installed dependencies and verified the Qt window and bundled
artwork. A native Windows rendering was also visually checked, including system
fonts and speaker artwork. Native Windows paired-device enumeration from the
background worker succeeded and found a UE
speaker. The follow-up audit fixed endpoint pairing detection, added BLE wake,
and verified a physical MEGABOOM 3 through the real Windows worker and interface.
Readings, same-value settings writes, disconnect/reconnect, and a complete
power-off/sleep-detection/BLE-wake/reconnect cycle passed. Refreshing the other
speaker's Windows pairing resolved its RFCOMM failure. The physical pair then
passed PartyUp join/removal, Stereo/Double Up mode readback, balance, and group
volume checks. The user confirmed audible Stereo routing and left/right balance
using quiet test tones. Receiver proxy levels and long playback synchronization
remain unverified. Computer mix remains Linux-only. The detailed
[Windows report](windows-validation.md) separates physical, automated, and
unverified behavior. Device-identifier diagnostics remain in ignored `.local/`.

## Automatic mix cleanup and Android redesign (2026-10-24)

Linux regression coverage includes stopping an owned mix and clearing group state
on explicit refresh after audio output loss, releasing a previous session's stale
configured mix route with zero or one Bluetooth output, keeping a healthy second
instance or user-selected output untouched, refusing to restore a disconnected
Bluetooth sink, and leaving audio alone on an uncertain PipeWire inventory read.
The final Linux suite passes all 129 tests; Android passes 19 JVM tests.
Automatic cleanup resets the visible group method to native PartyUp; discovery
never starts another mix. The AppImage is rebuilt with the fix.

Android 0.2.0 adds the speaker control paths and phone interface described in its
[feature matrix](../android/README.md). JVM tests additionally cover UTF-8 name
limits and malformed names, rename readback mismatch, signed balance notifications,
stereo balance validation/readback, stereo balance retained across group-volume
changes, and refusing writes to unconfirmed receiver levels. Phone previews use a
fake transport injected by an emulator-only instrumentation APK. They do not
certify Android Bluetooth behavior. Physical Android validation remains pending.
