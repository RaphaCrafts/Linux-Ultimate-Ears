# First release validation

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

54 automated tests passed in the final build.

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
