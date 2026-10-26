# Local reference renders

This directory is the offline image source for `ascii2skin`.  Nothing in the
package downloads or refreshes it at runtime.

## Layout

```
refs/
  <pattern_id>__<weapon_id>/
    <seed>.webp          # pattern.wiki render, re-encoded at WebP q=80
    <seed>.thumb64.webp  # 64x64 thumbnail used by the decoder
```

- Seeds: `32..126` (printable ASCII), 2660 unique renders after de-duplicating
  the M4A4 | Daybreak entry (29 challenge positions, 28 unique skins).
- Skins: the 29 challenge entries in `ascii2skin/skins.py` (28 unique
  directories; M4A4 | Daybreak appears twice in the challenge order).
- CS2 renders: 1920x1440 WebP, watermarked strip at the bottom.
- CS:GO renders: 1000x750 WebP, watermarked strip at the bottom.
- `PatternWikiRefs` crops the watermark strip on load, producing the same
  `1920x1296` / `1000x649` images used by the challenge attachments.
- `thumb64.png` is also accepted for custom galleries; the bundled gallery
  ships WebP thumbnails to keep the repository small.

## Provenance

Fetched once from `https://pattern.wiki/skin/<pattern_id>/<weapon_id>/` and
`https://static.pattern.wiki/img/<sha1>` on 2026-10-26.  `_sources.json`
records the seed -> original image hash mapping for every skin.

The bundled WebP files were re-encoded at quality 80 on 2026-10-26 to keep the
repository small.  Dimensions are unchanged, but the pixels are no longer
byte-identical to the pattern.wiki originals; the 29 challenge images match
with an average mean absolute error of about 0.43 (max 1.51), and Seed
decoding is still exact.  Avoid re-encoding them again lossily.

## Use another gallery

Keep the same layout and point the CLI at it:

```bash
uv run ascii2skin refs --refs /path/to/refs
uv run ascii2skin encode 'flag{...}' -o out --refs /path/to/refs
```

Or set `ASCII2SKIN_REFS=/path/to/refs`.
