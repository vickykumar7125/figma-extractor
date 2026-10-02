# figma-extractor audit

Baseline: GitHub `main` at `d4e8886` (`Harden extraction against real corpora and keep screen roles accurate.`). The local source tree is that commit. No local source is newer than GitHub.

Evidence: `out/` (direct `extract`, intermediates kept) and `corpus-review/` (same extractor, one numbered workdir per file, plus `report.json`). The two trees match. Examples below use `out/`.

This document is analysis only. It does not change the extractor.

## Pipeline map

```text
.fig or Figma REST
  -> decode (fig-kiwi or REST normalize)     extracted/nodes.ndjson + blobs
  -> structure (one pass over ndjson)        pages.json, screens.json, components.json,
                                              component-sets.json, structure/*.md, text-content.json
  -> tokens (second pass)                    tokens/*
  -> images (third pass + blob materialize)  assets/images + manifest.json
  -> trees (fourth pass, full index in RAM)  trees/*.json, trees/index.json
  -> split (rewrites screens + trees)        extra crop/board trees
  -> flow (walks every tree again)           ui-flow.json, LLM.md, screens.json roles
```

| Stage | Input | Output | Loss | Duplication | Determinism |
| --- | --- | --- | --- | --- | --- |
| Decode | kiwi chunks or REST JSON | ndjson of raw nodes, blobs | unsupported message fields never logged | none | node order follows the file |
| Structure | ndjson | slim nodes, top-level screens | props reduced to name/type; no overrides | slim node also exists in ndjson | screens sorted by page, then node count |
| Tokens | style and variable nodes | CSS values grouped by the first `/` in the style name | variable bindings on ordinary nodes are not attached | colors also in `tokens.css` | insertion order of styles |
| Images | `source/images` or blobs | hashed files + manifest | vectors are not assets | raster copied, not linked from the tree by path | files sorted; 12-char stem collision disambiguated |
| Trees | full node index | nested screen JSON | see section C | instances expanded in place | children sorted by `parentIndex.position` |
| Split | trees | more trees, rewritten `screens.json` | original board tree is replaced | child geometry copied into a new root | candidate slug order |
| Flow | trees + screens | roles, regions, guessed routes, static `LLM.md` | no prototype edges | text and component ids copied into `ui-flow.json` | routes sorted by path |

`LLM.md` is a fixed string (`flow.llm_guide`). All 12 corpus files share one hash. It does not name the file, the screen count, or missing data.

There is no `schema_version` on any artifact.

## A. Architecture

`extract()` in `src/figma_extractor/api.py` is the only pipeline. Deliverables land at the output root (`design_dir` is an alias of that root). `source/` and `extracted/` are deleted unless `--keep-intermediates`.

Local and remote share the later stages. Remote download (`remote.py`) normalizes REST JSON into the same ndjson, and skips image refs that are not safe filenames or that fail HTTP. Local `.fig` files either unzip to `canvas.fig` or are bare fig-kiwi (Rocket, Poco). Images that live only in blobs are materialized into `source/images` before the asset copy (Rocket 29, Poco 90). That is why the corpus probe counted `embeddedImages=0` while the manifest was non-empty.

One process holds every decoded node while building trees (`TreeBuilder`). Each screen walk expands instances up to 60,000 nodes and depth 60, then `split_screen_boards` may replace that screen with many crops. Flow then BFS-walks each tree again, capped at 800 nodes.

## B. Extraction subsystems

### Documents

- `.fig` ZIP and bare fig-kiwi are decoded offline. Kiwi versions in this corpus run from v1 (Rocket, 2020) through v75 (CreBiz).
- Remote REST is a second front door into the same ndjson.
- Pages are `CANVAS` nodes. `pages.json` keeps id, slugs, visibility, type counts, and top-level frames.
- A screen is a top-level `FRAME`, `SECTION`, `INSTANCE`, or `COMPONENT` on a canvas. Tiny instances under 320×320 are skipped. Nested frames are not screens until split promotes them.

### Layout on a tree node

Present and usable: `x`, `y` (parent-relative translation `m02`/`m12` only), `w`, `h`, `layout.dir` (`row`/`column`), `gap`, `pad`, `justify`, `align`, `wrap`, `grow`, `absolute`, `hugMain`, `hugCross`, `clip`.

`layout.pad` is an unlabeled 4-tuple in this order: `stackVerticalPadding`, `stackPaddingRight`, `stackPaddingBottom`, `stackHorizontalPadding`. `LLM.md` says to map it to CSS padding. CSS order is top, right, bottom, left. The stored order is not documented in the JSON.

Absent from trees, present on raw nodes in Vuexy (first 12,000 nodes): `horizontalConstraint` and `verticalConstraint` on 11,866 nodes, `layoutGrids` on 4,115, `variableConsumptionMap` on 3,445. Min/max size, overflow, and the rest of the transform (scale and rotation) are not copied. Auto-layout participation is therefore partial: a flex container can be rebuilt, a constrained or rotated child cannot.

### Paint, type, effects

Solids, image paints (hash + scale mode), and gradients (stops, linear angle) are normalized to CSS-like objects. Effects become `shadows` (`drop`, `inner`, `blur`, `backdrop`), with blur radius capped at 24. Blend modes are a small map. Opacity is kept when not 1. Style ids (`inheritFillStyleID`, `inheritTextStyleID`, `inheritEffectStyleID`) are dropped, so a tree color is not linked to a token except by an LLM matching hex strings, which is what `LLM.md` tells it to do.

### Text

`text.content`, weight (from font style name when `derivedTextData` is missing), family, size, line height, letter spacing, alignment, underline, case, and `singleLine`. No text-style id. Truncation and max-lines are not recorded.

### Components

`components.json` is one row per `SYMBOL`: id, name, key, page, size, layout mode, parsed `Key=Value` props, `variantOf` / `variantOfId`. `component-sets.json` groups children of `isStateGroup` nodes into `axes` and `variants`. Pre-2021 files (Rocket, kiwi v1) have hundreds of symbols and zero state groups, so sets are empty even though names look like variants. Component property definitions are reduced to `{name, type}`. Assignments and refs on instances (`componentPropRefs` on 2,110 of the Vuexy sample nodes) do not appear on tree nodes.

Instances are expanded. The tree keeps `instanceOf` and inlines the master, with overrides applied from `symbolOverrides` then `derivedSymbolData`. If the master has no auto-layout, the code assigns `"layout": null` (see the Icon Button crop). Nested instances are expanded again until a repeated symbol id stops the walk. Detached instances are not classified. There is no “was overridden” flag, only the flattened result.

### Split

`split_screen_boards` replaces a tall board with one tree per nested UI, and `promote_crops` lifts mid-size named frames into their own screens. That is why Rocket goes from 148 top-level frames to 408 trees, Modernize from 19 to 180, and Vuexy from 452 to 696. The original board file is not kept. A crop of a component specimen is then a screen.

`out/vuexy-.../trees/buttons__material-icon-button__icon-button__crop.json` is a 731×570 frame named “Icon Button”. Its children are 24 `SYMBOL` nodes (variant specimens: Size, Font Size, Color, Hover), each wrapping the same star `INSTANCE`. That is a sticker sheet, not a product screen. Flow still assigns it a role and may invent a route.

### Tokens

Explicit paint, text, and effect styles become JSON plus `tokens.css`. Variables are resolved per mode into `tokens/variables.json` (Vuexy: 265). Nothing is marked `EXPLICIT` vs `DERIVED`. Spacing, radius, and elevation scales are not inferred. That is the right default: the corpus does not justify inventing a 4/8/16 scale. Color grouping is the first slash segment or `"Default"`, which is a naming convention, not a semantic role.

### Assets

Only rasters. Manifest fields: `file`, `hash`, `mime`, `bytes`, `width`, `height`, `usageCount`, `usedBy[{node,name,page}]`. Zero `.svg` files in all 12 extracts. Vectors stay inside trees as SVG `d` strings.

### Flow and roles

`infer_role` is keyword matching on page and screen name. Roles seen: `page`, `dashboard`, `list`, `form`, `detail`, `auth`, `settings`, `dialog`, `empty`, `marketing`, `component-gallery`, `other`. There is no confidence and no evidence list. `"home"` maps to `dashboard`, so Modernize’s 180 split screens include 170 dashboards. `"list"` / `"table"` / `"index"` map to `list`, so RouteX has 19 list screens. Regions are name regexes on the root’s children and grandchildren, plus a flag scan. `suggestedRoutes` are slug guesses. `LLM.md` says so. Prototype data is not read. Vuexy’s ndjson contains `prototypeInteractions`; CreBiz’s does not. Those interactions never reach `ui-flow.json`.

### Screen record after flow

`screens.json` fields: `id`, `name`, `type`, `page`, `pageId`, `width`, `height`, `nodeCount`, `renderNodes`, `slug`, `tree`, `role`, `regions`. No route on the screen itself (routes live only in `suggestedRoutes`). No viewport class, no confidence.

## C. Schema audit

Tree node, when present:

```text
id, type, name, w, h, x, y,
opacity, blend, fills, stroke{paints,weight,align}, shadows,
radius, layout{dir,gap,pad,justify,align,wrap},
grow, absolute, hugMain, hugCross, clip,
mask, maskType, booleanOp, paths, strokePaths, text, instanceOf, children,
pageBackground
```

CreBiz trees actually use those keys and little else. Quality of a simple marketing file is good: 12 screens, 12 trees, text and auto-layout and paths on 91/103 vectors.

Weaknesses an LLM hits immediately:

1. `type` is the Figma enum. There is no semantic type beside it.
2. `layout: null` is stored. Omitted would be clearer.
3. `pad` is unlabeled.
4. Geometry paths are inlined and repeated. In the Icon Button crop the same star outline appears 8 times per size.
5. Across the 8 largest Vuexy trees: 13,074 `VECTOR` nodes, 2,072 with fill paths, 83 distinct path prefixes. The other vectors are stroke-only or empty of geometry in the tree even though raw nodes almost all have `strokeGeometry`.
6. Stroke cap, join, and dash exist on raw nodes (11,772 of 12,000 Vuexy nodes have `strokeCap`) and are not on `stroke`.
7. No stable cross-file id. Ids are Figma guids (`session:local`), which are stable per file. Asset stems are truncated hashes.
8. No provenance. A CSS color does not say whether it came from a style, a variable, or a raw paint.
9. JSON key order follows dict insertion, not a sorted schema. `orjson` does not sort keys. Walk order makes repeated runs match today; a field insertion would reshuffle files.

## D. Corpus coverage matrix

Twelve files, kiwi v1–v75. Counts are from `out/`.

| Feature | Supported | Quality on this corpus | Loss | Proposed action |
| --- | --- | --- | --- | --- |
| Pages / canvases | Yes | Good | Low | Keep `pages.json` |
| Top-level screens | Yes | Good on CreBiz, readmin | Medium | Keep, tag confidence after split |
| Board split | Yes | Rocket 148→408, Modernize 19→180, Vuexy 452→696 | High: specimen sheets become screens; source board deleted | Keep split, retain the pre-split tree, mark crops |
| Auto-layout | Yes | Good when `stackMode` is set | Medium: no min/max, no grid details | Add normalized constraint and sizing fields |
| Constraints | In raw only | Vuexy: almost every node | High | Copy through; do not invent breakpoints |
| Variables | Vuexy only | 265 resolved values | High in trees: paints are unbound | Keep token files; add style/variable refs on nodes |
| Explicit styles | Yes, when the file has them | Rocket, Vuexy, Modernize, CreBiz | Low for the style catalog | Mark `kind: explicit` |
| Inferred spacing tokens | No | — | None invented (correct) | Do not add without evidence thresholds |
| Components | Yes | Vuexy 6,055 symbols, 88 sets | Medium: prop refs dropped; Rocket has symbols but no sets | Emit prop defs and instance assignments |
| Variant axes | Yes for `isStateGroup` | Good on Vuexy | High on kiwi v1 | Document, do not invent axes from loose names |
| Instance expansion | Yes | Correct nesting | High duplication of vectors | Reference a shared vector/component body |
| Raster assets | Yes | Manifest matches files | Low | Keep; link tree image paints to `file` |
| SVG / vectors | Path `d` inside trees only | Icon Button crop has full outlines | High: no asset, no stroke caps, many vectors without `d` | Deduped `assets/svg` plus structured commands |
| Masks / booleans | Partial | `mask`, `booleanOp`; boolean children dropped when a path exists | Medium | Keep; record that children were omitted because the outline is resolved |
| Text | Yes | CreBiz 664 text nodes | Low | Add style ref |
| Roles | Keyword | Modernize 170/180 `dashboard`; Vuexy 293 `page` | High false confidence | Evidence + confidence; narrower keywords |
| Prototype interactions | In Vuexy raw | Not in any output | High | Normalize into flow as source facts, separate from guessed routes |
| `LLM.md` | Static template | Identical for 12 files | High | Generate per extract |
| Responsive breakpoints | No evidence stored | — | Constraints dropped | Represent constraints; do not invent 768/1024 |

Empty structure pages (node count 0) still render a heading. Vuexy has 7, including `atoms.md`, `misc.md`, and a page titled a run of dots. readmin and Poco emit an empty “Internal Only Canvas”.

## E. SVG and vector audit

Vectors are already decoded. `PathStore` turns `fillGeometry` / `strokeGeometry` blob commands into `{d, rule}` on `VECTOR`, `ELLIPSE`, `STAR`, `BOOLEAN_OPERATION`, `RECTANGLE`, and similar. The Icon Button crop shows a complete even-odd star path, a fill color, and a size. An SVG can be generated from data the extractor already has.

What is still lost or unusable:

- No `assets/svg` (or icons, logos, illustrations). Every consumer re-derives SVG from a deep tree.
- The same master vector is copied into every instance. Reconstruction cannot say “this is `star-fill`, used 24 times”.
- `strokeCap`, `strokeJoin`, dash, and per-side stroke weights are on the raw node and omitted from `stroke`.
- Many vectors in large Vuexy trees have neither `paths` nor a usable outline in the JSON, while raw `strokeGeometry` is nearly universal. Stroke-only icons (Tabler-style) are the likely gap. They must be confirmed per node before a converter drops them.
- Boolean operations keep `booleanOp` and the resolved outline, and skip operand children. That is correct for silhouette, and it must stay labeled so an agent does not expect the operands.
- Transforms other than translation are dropped, so a rotated icon path is in the wrong orientation if the rotation lived in `m00`/`m01`/`m10`/`m11`.
- Image paints inside vectors stay as hashes, which is right. Rasterizing those paints would be a regression.
- Gradients on vectors are the generic paint object. A dedicated SVG serializer has to map that object; it should not invent a second gradient model.

Recommended representations, in order, without replacing the tree:

1. Raw geometry stays in `extracted/` (already true when intermediates are kept).
2. A normalized vector record: source node id, bounds, fill paths, stroke paths, stroke attrs, paint refs.
3. A generated SVG document only for records that are icon-like (small, repeated, or named like an icon) or explicitly referenced by many instances.
4. The tree node keeps `assetId` and, when the outline is unique to that node, may still inline `paths` so one file remains enough for a rare shape.

Dedup key: hash of the path commands plus paint and stroke, not the instance id. The star in the crop is one asset at three scales, not 24 assets.

## F. LLM readiness

An agent can, today, for a CreBiz-sized file:

- List screens, sizes, and file paths (`screens.json`, `ui-flow.json`).
- Walk a tree and emit flex, text, fills, radii, and simple inline SVG.
- Look up a component set’s axes when `isStateGroup` exists.
- Find raster files by manifest hash.

An agent cannot reliably:

- Tell a product screen from a crop of variant stickers (Icon Button).
- Know whether a role is evidence or a keyword hit (`home` → dashboard).
- Follow a real click. Routes like `/02-cdesign/studio` are slugs.
- Bind a fill to a token without string-matching colors.
- Reuse an icon without copying path text out of every instance.
- Know what was dropped when the 60,000-node budget ends. The walk returns a partial tree and does not set a flag. `LLM.md` mentions skipped screens but the tree itself is silent.
- Answer “what is inferred” versus “what was in the file”.
- Rebuild responsive behavior from constraints that were decoded and then discarded.
- Use `LLM.md` as an index of this file. It is the same page for Vuexy and CreBiz.

Locality is the other gap. One screen is `screens.json` row + `trees/<slug>.json` + slices of `ui-flow.json` + `components.json` + `tokens.css` + `assets/manifest.json`. That matches the current `LLM.md` read order, and it is too many joins for a 27 MB tree that mostly repeats icons.

## G. Information-loss report

Dropped after a successful decode (not an error):

| Source field | Where seen | Not in |
| --- | --- | --- |
| `horizontalConstraint`, `verticalConstraint` | nearly all Vuexy nodes | trees |
| `layoutGrids` | 4,115 / 12,000 Vuexy sample | trees, tokens |
| `variableConsumptionMap` | 3,445 / 12,000 | tree paints |
| `inherit*StyleID` | thousands of text and fill nodes | tree nodes |
| `componentPropRefs`, `componentPropAssignments` | instances and symbols | trees |
| `strokeCap`, `strokeJoin`, dash, individual weights | almost every stroked node | `stroke` |
| Full transform matrix | every positioned node | `x`/`y` only |
| `prototypeInteractions` | Vuexy ndjson | `ui-flow.json` |
| `exportSettings` | CreBiz, 19 nodes | unused |
| Node budget exhaustion | possible on huge frames | no diagnostic |
| Pre-split board tree | every split screen | deleted when rewritten |

Resolved on purpose (keep, but label): boolean operands omitted when the outline exists; invisible nodes omitted; blur radius clamped to 24.

## H. Duplication report

- Instance subtrees repeat master geometry in every screen that uses the master. The star path is the small case; icon sheets are the large case.
- `screens.json`, `ui-flow.json` pages, and `trees/index.json` repeat id, name, size, slug, and role.
- `tokens.css` repeats `color-styles.json`, `typography.json`, and `effects.json`.
- `COMPONENTS.md` repeats `component-sets.json`.
- `STRUCTURE.md` and `structure/<page>.md` outline the same tree the JSON trees describe, truncated by depth, and empty pages still get a file.
- `corpus-review/` and `out/` are two copies of the same 12 extracts. Keep `out/` as the review corpus. `corpus-review/` is the harness workdir and can be discarded between runs.

The CSS and markdown views are useful derived artifacts if they stay derived. The instance clones and the triple screen index are the copies that hurt.

## I. Semantic layer proposal

Do not replace `type`. Add an optional sibling object so old readers still see `FRAME`.

```json
{
  "type": "FRAME",
  "semantic": {
    "kind": "card",
    "confidence": 0.9,
    "evidence": ["repeated sibling", "radius", "contained text and media"],
    "source": "name+geometry"
  }
}
```

`kind` is a closed vocabulary the classifier owns (`screen`, `section`, `header`, `nav`, `sidebar`, `footer`, `card`, `button`, `icon-button`, `input`, `image`, `icon`, `component-gallery`, and the rest of the requested list only when a rule exists). `confidence` is required whenever `kind` is set. Name-only matches stay at or below 0.6 and must list the keyword. Geometry-plus-name matches can go higher. No match means the object is absent, not `kind: "unknown"` with a fake score.

Classification must be a pure function of the normalized node plus its immediate parent and siblings, so it stays deterministic and testable. The Icon Button crop should come out `component-gallery` or `specimens`, with evidence `["child types are SYMBOL", "names contain size=/hover="]`, not as a page route.

Roles on screens use the same shape. The current string role can remain for compatibility and be copied from `semantic.kind` when confidence is high enough; otherwise `role` stays `page` and `semantic` carries the low-confidence guess.

## J. Output schema proposal

Keep the current root files. Add fields. Add a small number of new files. Do not move `trees/` into a new tree of directories in the first schema bump.

`schema_version` on `trees/index.json`, `ui-flow.json`, and a new `manifest.json` at the output root. Version `1` is the current shape. Version `2` is additive.

Version 2 additions:

- Root `manifest.json`: file name, kiwi or REST source, schema version, counts, paths to the indexes, list of diagnostics. This replaces the job `LLM.md` is failing to do.
- `diagnostics/unsupported.json` and `diagnostics/truncated.json`: node id, field or reason. Empty arrays when nothing was dropped.
- Tree node: `constraints` (`horizontal`, `vertical`) when the raw fields exist; `stroke.cap`, `stroke.join`, `stroke.dash` when present; `styleRefs` (`fill`, `text`, `effect`) as ids; `variables` as id refs from `variableConsumptionMap`; `semantic` as in section I; omit keys whose value is null.
- `layout.padding`: `{top, right, bottom, left}` while still writing `pad` with the current tuple until consumers migrate.
- Vector nodes that share a hash: `vectorRef` pointing at `assets/vectors.json`, SVG written under `assets/svg/<id>.svg` only for deduped, closed records. Unique one-off paths stay inline.
- `screens/<slug>/screen.json`: a bundle that references the existing tree, the screen’s asset ids, component ids, text snippets, role evidence, and route. It does not copy the tree body.
- `flows/interactions.json` only when prototype records exist. `suggestedRoutes` stays labeled `inferred: true`.

Screen bundles are an index, not a second canonical tree. The canonical screen geometry remains `trees/*.json`.

## K. Migration plan

1. Publish the current keys as schema 1. Do not rename `instanceOf`, `layout.dir`, or `role`.
2. Schema 2 adds keys and files only. Readers that ignore unknown keys keep working.
3. `layout.pad` remains until a corpus test proves `layout.padding` matches it for the four raw fields.
4. Split continues to write the current crop filenames. Add `origin: "crop"|"board-child"|"top-level"` and `sourceScreenId` on the screen record. Optionally write the pre-split tree to `trees/boards/` so the specimen sheet is recoverable. Do not delete the current crop trees in the same change that adds bundles.
5. `LLM.md` gains a generated summary at the top and keeps the static read-order below it, so old instructions do not vanish.
6. Component sets stay empty for files with no `isStateGroup`. Do not synthesize axes from Rocket’s name paths in the compatibility window; a later phase can add `namePath` as derived and clearly marked.
7. Remote extract and local extract must emit the same schema version.

## L. Testing strategy

`tests/test_fig_corpus.py` already checks deliverables, canvas counts, conditional tokens, symbol counts, state groups, text, asset bytes, and guid-shaped `usedBy`. It passes on this corpus when intermediates are removed. Extend it, do not replace it.

Add assertions that can run against `out/` without re-extracting, plus a small checked-in fixture so CI does not depend on the external drive:

- Schema 1 keys still exist on CreBiz’s first screen and tree root.
- Icon Button crop is tagged as specimens, not a high-confidence product screen, once classification exists.
- A deduped star asset has `usage` covering the instances in that crop, and the SVG path equals the stored `d`.
- Constraint fields on a Vuexy node survive into the tree when present on the raw node (compare one guid in `nodes.ndjson` and the tree).
- `suggestedRoutes` entries with no prototype source carry `inferred: true`.
- Files with zero prototype records do not gain fake interactions.
- Re-extract of CreBiz is byte-identical for `trees/*.json` (already the intent of `--determinism`).
- A node over the budget sets a truncation diagnostic and still writes the partial tree.
- Rocket (no `isStateGroup`) still has an empty `component-sets.json`.
- Zero `.svg` is not an invariant. Once SVG export exists, a fixture vector must produce a file and CreBiz’s count must be non-zero if it has repeated icons.

## M. Implementation roadmap

Work in this order. Each step is independently shippable and keeps schema 1 readable.

1. Diagnostics and schema version. Record silent drops (budget, missing geometry, skipped image refs). Generate the per-file part of `LLM.md` and `manifest.json`.
2. Normalize layout metadata the decode already has: padding object, constraints, full stroke attrs, style and variable refs. No new classifiers.
3. Screen identity. `origin` and `sourceScreenId`. Tighten role keywords (`home`, `view`, `index`) and attach evidence. Stop treating SYMBOL-only crops as primary product screens in the default route list.
4. Vector assets. Dedup path geometry, emit SVG for shared icons, point instances at `vectorRef`. Leave one-off paths inline.
5. Prototype interactions as a separate file when the raw field exists.
6. Screen bundle `screens/<slug>/screen.json` composed from steps 2–5, references only.
7. Semantic classifier for the closed set that has tests (button, icon, card, nav, field, gallery). Everything else stays untagged.
8. Only then consider spacing-scale inference, and only with a documented frequency threshold and `kind: inferred`.

Phases 1–4 answer the reconstruction questions that the current corpus already contains data for. Phases 5–8 add judgment, which must stay labeled.

## Answers the extractor can and cannot give

| Question | Now | After phases 1–4 |
| --- | --- | --- |
| What screens exist? | Yes, including crops mixed in | Yes, with origin |
| Role of each screen? | Keyword, often wrong | Keyword plus evidence and confidence |
| Route? | Slug guess, documented as such | Guess labeled inferred; real links only from prototypes |
| Regions? | Name regex, two levels | Same, plus evidence |
| Reusable components and variants? | Yes when Figma recorded a state group | Plus prop refs on instances |
| Which instance uses which component? | `instanceOf` | Same, without copied geometry |
| Tokens? | Explicit styles and variables | Same, plus refs on nodes |
| SVG? | Inline `d` only | Shared SVG assets |
| Hierarchy and layout? | Yes for flex and parent-relative x/y | Plus constraints and real stroke |
| Responsive rules? | No | Constraints only, no invented breakpoints |
| Text? | Yes | Yes, with style ref |
| Interactions? | No | Yes where the file has prototypes |
| What is inferred or missing? | No | Diagnostics and `inferred` flags |
| Rebuild without a screenshot? | Partly, for simple flex screens | For flex screens, icons, and tokens; still not for unpublished breakpoints |
