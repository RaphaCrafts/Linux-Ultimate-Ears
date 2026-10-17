# Speaker studio design direction

The user chose Speaker studio from the initial alternatives. Their Android app
screenshots inform the large model/colour-matched product image, prominent
battery and power controls, dedicated PartyUp view, and five-band EQ curves.

The revised concept has three navigation destinations:

- **Speaker:** selected device, colour-correct packshot, battery, locator sound,
  remote power, volume, EQ preview and a link to its group.
- **PartyUp:** group host and members, per-device batteries and volume values,
  group volume, remove/ungroup actions, and a separate nearby-speaker area.
  Adding shows a pending state before confirmed membership. The production
  implementation must confirm via protocol notifications, not the initial ACK.
- **Equalizer:** a curve plus five accessible sliders. Names drawn from the
  screenshots include Signature, Bass boost, Cramped spaces and Podcast/Vocal.
  Signature is visually flat. Other curve shapes are illustrative
  interpretations of screenshots; displayed dB values are not recovered device
  parameters. Each speaker owns its own EQ state.

The appearance picker explores eight model families and their retrieved colours.
It changes presentation in the concept, not hardware identity. Production must
select actual hardware/model/colour data and retain user override for unknown
colours. Group membership and nearby discovery must remain visually distinct.

All preview devices, battery levels and control outcomes are simulated. The
screenshots are inspiration; their depicted 30% battery is not a live reading.
No device commands, music playback, phone settings or account actions occur.
The in-conversation preview remains in the chat's visualization directory; this
repository stores the reusable image catalogue and design direction.

See [the asset catalogue](../assets/speakers/README.md) and its attributed source
manifest. It does not constitute a compatibility matrix. WONDERBOOM is artwork
only, not a claim of PartyUp or BOOM-app support.
