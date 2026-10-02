# 04 — Screen extraction

## Objective

Separate top-level screens, board children, and promoted crops, and stop presenting component specimen crops as the primary site map.

## Context

`docs/redesign/AUDIT.md` sections B and D. `split_screen_boards` replaces the board tree. Rocket 148→408, Modernize 19→180, Vuexy 452→696. The Icon Button crop is a sticker sheet of symbols.

## Existing implementation to inspect

`extract/structure.py` screen filter (top-level frame, section, large instance/component, 320px minimum). `extract/split.py` `is_crop_frame`, `promote_crops`, `split_targets`, `split_screen_boards`.

## Files and folders to inspect

`out/vuexy-.../screens.json`, the Icon Button tree, `out/CreBiz/screens.json` (12 screens, no split), `out/Rocket – Admin Dashboard [Light]/screens.json`.

## Constraints

Keep current crop files and slugs so existing `tree` paths still resolve. Do not delete pre-split information. Do not raise the screen count further.

## Required analysis

For Vuexy, count screens whose root children are mostly `SYMBOL` or whose names contain `Size=` / `Hover=`. Those are the specimens. Count CreBiz to show a file that should not change cardinality.

## Required implementation

On each screen record add `origin` (`top-level`, `board-child`, or `crop`) and `sourceScreenId` when the tree was split from another frame. Keep the pre-split tree under `trees/boards/<slug>.json` and point at it from the board screen. Leave the current split trees in `trees/`.

Default `suggestedRoutes` and the primary screen list used by `LLM.md` exclude `origin=crop` screens whose semantic kind is specimens or component-gallery. They remain in `screens.json` and on disk.

## Required tests

- CreBiz still has 12 trees at the historical paths plus any new `trees/boards` only when a board existed (expect none).
- Icon Button crop has `origin` of `crop`, `sourceScreenId` set, and is absent from the primary route list.
- Rocket tree files that exist today are still written.
- `screens.json` rows still have `id`, `slug`, `tree`, `width`, `height`.

## Required outputs

`origin`, `sourceScreenId`, `trees/boards/` when a board was split, filtered primary route list.

## Acceptance criteria

A consumer can list product screens without the sticker sheets, and can still open the sticker sheet by path.

## Do-not-break rules

Do not change crop slug algorithm in the same change as the new fields. Preserve `split` summary counts. No guessed routes added for specimens. Inspect `split.py` before editing the heuristic thresholds.
