# Speaker artwork

39 retrieved colour variants across eight model families, downloaded from the
official Ultimate Ears asset server. Product packshots are transparent WebP,
up to 600px (the original catalogue uses 320px).

This is a best-effort catalogue, not a guarantee of every historical, regional,
limited edition or future finish. The app always offers a **Generic** illustration
for the speaker family. It uses that illustration when no finish has been chosen,
a saved finish is absent from the catalogue, or a packshot is missing/unreadable.
Generic artwork also covers older BOOM/MEGABOOM speakers, and an unknown speaker
has a universal fallback. A selected finish is a local preference and does not
change the model identity or control compatibility.

`manifest.json` records model, colour, regional SKU where available, exact official
source/download URLs, file size and SHA-256. Current colours come from official
product-page structured data. Additional historical colours use verified official
CDN filenames; they are not claims of current shop availability. Unavailable
filenames and failed listing fetches are recorded separately. No product packshot
was synthesized or recoloured.

## Retrieved finishes

- MEGABOOM 3: Sunset red, Night black, Lagoon blue, Ultraviolet purple, Unicorn pink, Moon, Dusk, Seashell peach, Denim, Cloud, Urban magenta.
- BOOM 3: Lagoon blue, Night black, Sunset red, Ultraviolet purple, Unicorn pink, Moon, Dusk, Seashell peach, Denim, Cloud.
- MEGABOOM 4: Cobalt Blue, Enchanting Lilac, Active Black, Raspberry Red.
- BOOM 4: Raspberry Red, Enchanting Lilac, Active Black, Cobalt Blue.
- EVERBOOM: Charcoal Black, Azure Blue.
- EPICBOOM: Charcoal Black, Cotton White.
- HYPERBOOM: Black.
- WONDERBOOM 4: Active Black, Joyous Bright, Hyper Pink, Cobalt Blue, Sand.

Historical Jungle grey packshots could not be retrieved from the probed official
filenames; choose Generic for those finishes. Additional unknown variants should
also use Generic. Artwork availability does not imply Linux control support.

## Refresh the catalogue

```bash
python3 scripts/fetch_product_images.py --legacy-colours
```

The standard-library downloader preserves previously retrieved files and records
unavailable images rather than substituting another model. Inspect the manifest
after each refresh; upstream listings and URLs can change.

Product images and trademarks belong to Logitech / Ultimate Ears. No open-source
licence is asserted for their packshots. `generic/*.svg` contains original neutral
illustrations distributed under this repository's GPL-3.0 licence.
