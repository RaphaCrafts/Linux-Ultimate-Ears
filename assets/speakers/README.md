# Official product packshots

26 retrieved colour variants across eight models. The images were downloaded
from Ultimate Ears' public asset server at a UI-sized 320px maximum dimension,
in transparent WebP format. They are product artwork, not proof of Linux device
support or an exhaustive list of historical colours.

`manifest.json` records each model, colour label, regional SKU where available,
source page, exact source/download URL, file size and SHA-256. Current colours
come from official product-page structured data. Additional BOOM 3/MEGABOOM 3
colours come from verified historical official CDN filenames, explicitly marked
as such; they are not assertions of current availability. No colours were
synthesized or recoloured. Individual pixels may differ from the Android app's
own assets, camera photos, and real hardware under different lighting.

The current catalogue contains:

- BOOM 3 and MEGABOOM 3: Night black, Lagoon blue, Sunset red, Ultraviolet purple.
- BOOM 4 and MEGABOOM 4: Active Black, Cobalt Blue, Raspberry Red, Enchanting Lilac.
- EVERBOOM: Charcoal Black, Azure Blue.
- EPICBOOM: Charcoal Black, Cotton White.
- HYPERBOOM: Black.
- WONDERBOOM 4: Active Black, Joyous Bright, Hyper Pink, Cobalt Blue, Sand.

WONDERBOOM artwork is included for visual identification only. Do not infer
PartyUp or BOOM-app control support from its presence. Other historical models,
limited editions, regional variants and additional HYPERBOOM colours remain
outside this collection.

Reproduce from the repository root:

```bash
python3 scripts/fetch_product_images.py --legacy-colours
```

The script requires Python's standard library and internet access. It checks the
WebP signature and records unavailable images rather than substituting another
model or recolouring one. Inspect the manifest after every run: the live shop
and CDN can change, so future collection counts may differ.

Images and trademarks belong to Logitech / Ultimate Ears. No open-source image
licence is asserted or granted by this repository.
