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
