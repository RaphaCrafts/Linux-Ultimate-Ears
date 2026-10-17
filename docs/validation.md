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

34 automated tests passed in the final build.

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
