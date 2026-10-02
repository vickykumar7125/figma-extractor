# 07 — Asset pipeline

## Objective

One manifest that covers rasters and vector assets, with stable ids and screen usage, without duplicating bytes.

## Context

`docs/redesign/AUDIT.md` sections B and H. Raster manifest fields today: `file`, `hash`, `mime`, `bytes`, `width`, `height`, `usageCount`, `usedBy`. Tree image paints store `hash` and `scaleMode` but not the manifest `file`. Blobs materialize Rocket and Poco images that are not stored as zip entries. Remote downloads already skip unsafe refs.

## Existing implementation to inspect

`extract/images.py` `build_images`, `materialize_from_blobs`, `collect_image_refs`. `remote.py` `safe_image_name`. Prompt 06 vector records.

## Files and folders to inspect

`out/CreBiz/assets/manifest.json` (18 images), `out/Poco Admin/assets`, `out/readmin/assets` (55 copied, 53 referenced).

## Constraints

Do not rename existing image files (12-character stem plus extension, de-duplicated). Do not drop `usedBy`. Categories are only those with evidence: `raster`, `svg`, `vector`. Do not assign `logo` or `avatar` unless `semantic.kind` already says so. `icon` category follows prompt 03 or 06, otherwise leave category as `svg` or `vector`.

## Required analysis

Show one tree image paint hash and the manifest row it should join. Note readmin’s unreferenced files and keep them in the manifest with `usageCount: 0`.

## Required implementation

- Add `id` and `kind` on each manifest row. Raster `kind` is `raster`.
- Add `file` onto image paint objects in the tree when the hash matches.
- Append vector rows from prompt 06 into the same manifest or a clearly referenced `assets/vectors.json` linked from `manifest.json`. One index, not two competing catalogs.
- Hash remains the dedup key for rasters.

## Required tests

- CreBiz manifest length stays 18 and every `file` exists with the same byte size.
- Every tree image paint with a hash either resolves to a manifest row or is listed in diagnostics.
- Poco still materializes blob images.
- Filenames unchanged across two runs.

## Required outputs

Unified asset index and tree paints that point at files.

## Acceptance criteria

From one screen tree, the image and shared SVG paths are recoverable without scanning the whole `assets/` directory.

## Do-not-break rules

Preserve manifest byte checks in `tests/test_fig_corpus.py`. Do not fetch remote URLs in unit tests. Safe filename rules in `remote.py` stay. No duplicate copies of raster bytes inside JSON.
