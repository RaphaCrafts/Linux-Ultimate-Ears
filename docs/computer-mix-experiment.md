# Experimental workaround: Linux sends to both speakers

Native PartyUp still stutters on the tested MEGABOOM 3 pair with current firmware,
either speaker hosting, and either Linux or a phone as the source. A possible
workaround is to stop native PartyUp and let Linux send independently to each
speaker through separate Bluetooth audio connections.

This is a trial, not an established fix. It may replace stuttering with echo,
unequal latency or drift. Two Bluetooth audio streams also increase the Linux
adapter's radio workload. PipeWire's reported-latency compensation does not
measure the speakers' actual acoustic delay or guarantee synchronization.

The source helper is `scripts/computer_mix_trial.py`. It creates a temporary
PipeWire sink targeting exactly two existing Bluetooth outputs. It never changes
speaker settings, selects a default output, restarts audio services, writes a
configuration file, or modifies firmware. The owning process removes the virtual
output when it exits. The trial also stops if either speaker output disappears.

For a supervised listening test:

1. End PartyUp explicitly, then close the UE apps on the phone and computer.
2. Connect both speakers separately in Linux Bluetooth settings.
3. Run `.venv/bin/python scripts/computer_mix_trial.py --list` to identify their
   audio outputs. Saved pairings and control connections alone are insufficient.
4. Pass those two exact node names to the helper with `--speakers NAME1 NAME2`.
   It defaults to a three-minute trial, with a maximum of ten minutes.
5. Select **Speaker studio · Computer mix trial** in Linux Sound settings and
   play a downloaded track. Assess interruptions, echo and timing separately.
6. Select the original output when finished, then stop the trial with Ctrl+C
   or let it expire. The helper does not restore PartyUp; no group was changed
   by the helper in the first place.

Version0.1.13 adds a user-facing Computer mix panel. It selects the temporary
output on Start and restores the prior configured output on Stop or Quit, unless
the user has selected a different output meanwhile. The source helper remains
available for bounded developer trials and does not select an output itself.

Validation on 2026-10-18: installed PipeWire 1.0.5 contains the combine-stream
module. A silent runtime test created two virtual sinks and the combined sink,
confirmed output links to both targets, and verified that every temporary node
was removed afterward. Default audio metadata stayed unchanged. No speaker was
connected, no sound played and no acoustic synchronization was tested.

Primary references:

- [PipeWire combine-stream and latency compensation](https://docs.pipewire.org/page_module_combine_stream.html)
- [pw-cli process-local module ownership](https://docs.pipewire.org/page_man_pw-cli_1.html)


Live trial on2026-10-18: PINK3 was still hosting native Stereo PartyUp0350.
For the approved independent-playback comparison it was disabled to0050, then
both physical speakers obtained separate Linux A2DP outputs. The temporary mix
and both Bluetooth outputs reached running state with Spotify playing. PINK used
SBC and PURPLE used SBC-XQ. The user reported **smooth and well synchronised**.
The trial ended early when PipeWire appended a change array to its initial JSON
dump; a strict single-document parser rejected it. Cleanup removed the mix and
restored the saved configured output, verified from PipeWire metadata. Native
PartyUp remained off. The listened duration was shorter than the planned three
minutes; long-duration acoustic stability is not established.

The shared inventory reader now accepts the initial complete JSON array and
ignores appended delta arrays; each subsequent poll reads a fresh inventory.
Regression coverage includes the actual concatenated-document failure shape.
An integrated-core silent test subsequently verified both target routes,
monitoring and cleanup without selecting an output or interrupting real music.
Output selection/restoration is covered by automated lifecycle tests, including
preserving a manually changed output. AppImage launches system audio tools with
the original system library environment, excluding bundled Qt plugin paths.


Version 0.1.14 ends native PartyUp when opening Computer mix and checks again
before starting playback. It reads connected speakers, reconnects controls for
speakers with an audio link, and sends the existing ungroup command to native
hosts. A failed check or ungroup prevents the mix from starting. Both speakers
still need separate Linux audio outputs; missing outputs are explained in the
panel. The default mode is saved locally and opens the chosen controls from the
single sidebar PartyUp entry. Choosing a default does not start playback.

The panel now shows a short experimental warning. Automatic latency compensation
was already enabled through `combine.latency-compensate`: PipeWire uses delay
buffers to match the reported stream latencies. This does not measure acoustic
offset and is not a guarantee against drift, echo or Bluetooth interruptions.
No manual per-speaker delay calibration is implemented in this update.

Validation on 2026-10-23: automated tests cover automatic ungroup ordering,
failure preventing mix startup, and direct PartyUp connections. These new flows
have not been verified with physical speakers.


Version 0.1.16 integrates the method selector and group cards. Switching an
existing pair captures its addresses before ungrouping. It ends native hosts
first, connects each paired Classic device with BlueZ `ConnectProfile` for the
A2DP Sink service, verifies MediaTransport availability, and waits for exact
PipeWire outputs matching those addresses. It does not require a separate
receiver control session for Computer mix. Generic Bluetooth Connected state
alone is insufficient evidence of an audio output. Transient profile transitions
are retried. No pairing, trust setting or Bluetooth service is replaced.

Selecting Computer mix before dragging a paired speaker uses the same backend
transition. Native switching stops the owned mix, reconnects controls, joins the
selected speakers and restores the prior two-speaker channel mode when known.
Transitions are serialized; an error retains selection and makes retry available.
A failure after native teardown does not automatically recreate native PartyUp;
the user can retry or select Native PartyUp. Computer mix is limited to two
speakers, and larger selections are rejected before teardown.

Live inventory on 2026-10-23 showed the reported receiver paired without a direct
Linux audio transport while the host had a transport. This confirms the missing
handoff prerequisite; it does not prove that the receiver was currently in a
native group. Automated tests cover the new transition order and UI behavior.
The new full switching flow has not yet been listening-tested on physical
speakers. The existing latency compensation remains experimental.

BlueZ API reference: [Device ConnectProfile](https://bluez.readthedocs.io/en/latest/device-api/).


Version 0.1.17 adds independent Linux output volume controls on the speaker cards.
`wpctl get-volume` supplies volume/mute readback; `set-volume --limit 1.0` and an
explicit unmute implement a user's slider adjustment. Only outputs in the active
mix can be edited. Node IDs are resolved from a fresh inventory on every edit.
Normal volume settings remain after Stop; the existing output-default restoration
is unchanged. These controls adjust relative loudness, not left/right channel
assignment, and do not raise either speaker automatically when creating a mix.
Whether Linux output volume is synchronized to physical buttons depends on the
Bluetooth audio stack's hardware-volume support. Speaker Studio's native volume
controls remain the existing 16/32-step speaker protocol controls.

References: [WirePlumber volume commands](https://pipewire.pages.freedesktop.org/wireplumber/man/wpctl.html),
[Bluetooth hardware volume](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/bluetooth.html).
