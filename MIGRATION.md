# mcjo79 capability migration and provenance

Reference date: 2026-11-06. Source: [mcjo79/vroid-mcp](https://github.com/mcjo79/vroid-mcp)
at `0dc7d5eb3cf27f7f943713960cac1b65f479a876`; target baseline:
`b02b108ab4a8b4333ecf206a199a7a0403aa7ffe`. Work is on
`feat/mcjo79-capability-migration`, following the versioned
[design](docs/superpowers/specs/2026-11-06-mcjo79-migration-design.md) and
[plan](docs/superpowers/plans/2026-11-06-mcjo79-migration.md).

## Evidence and state vocabulary

This is the complete 53-tool inventory from `mcp_server/vroid_mcp.py:160-661`.
Task 1 fixes deterministic scratch handling and records provenance. Future
runtime adaptations are **planned**, including rows with existing core primitives.
Existing means a comparable target operation was found in source inspection;
Partial means a contract or implementation gap remains; Gap means no public
target equivalent was found. None of these terms establish migrated native parity.

The read-only capability and export audits were kept in workspace temp as
`audit-capabilities.md` and `audit-export.md`; their substantive mappings and
limits are carried below so this versioned record stands alone. Later tasks
must update affected rows with the commit, focused tests and remaining gates.
Task 1 Python/JS/schema checks establish an offline baseline only. Actual
native execution, Undo/Redo, save/reopen, export-artifact and visual acceptance
remain separate gates. No new migration-native acceptance has been performed.

Task 1 offline baseline: 571 Python tests passed with 9 existing Pydantic
`Field(min/max)` deprecation warnings; all 10 JavaScript behavior suites and
syntax checks for 19 agent files passed. The unchanged tool manifest contains
103 tools with hash
`sha256:3b47ec7ac16f35281107105113d22416f19bf94e5afacfe6bd80f4f379537e5d`.
The source manifest reports the expected 10 changed tracked source files and
is intentionally left for Task 10 regeneration. Local logs live in project
temp; this baseline does not upgrade any planned adaptation row to complete.

## Architecture and safeguards retained

- Keep Python MCP, the Frida bridge and JavaScript IL2CPP main-thread dispatch.
  Do not install a second BepInEx/Harmony/HTTP or GUI-input control kernel.
- Keep supported-build checks, fresh model identities, session serialization,
  native history, attached/copy ownership and lab-scoped no-overwrite artifacts.
- Validate before side effects; use exact native bindings and units. A raw
  source key, normalized scalar or fuzzy label is not an established write ID.
- Native completion needs bounded state/task polling. An uncertain dispatch
  retains its barrier/handles and must not be retried or cleaned up blindly.
- Catalog reads work offline. Scans retain annotations and unknown custom
  records. Situation imagery uses an acknowledged disposable owned-copy model.
- The installed Steam assembly hash
  `3334b166e298682eeda1ca1c5ca568b12f7085b76cc629668fe8b192af816bd8`
  is unsupported. Do not start/attach it or add its hash merely for acceptance.

## All source tools and domain owners

Owner names identify implementation responsibility in the plan. Baseline-only
rows still require Task 10 field/contract audit; no alias is promised.

| # | Source tool | Domain owner | Existing behavior, planned target mapping and differences | Verification state |
| --- | --- | --- | --- | --- |
| 1 | `vroid_help` | Help/batch/lifecycle (Task 9) | Planned: `get_help` and MCP help resources. Gap. Target has server instructions and generated tool docs, but no callable multilingual/topic manual. Add help plus focused MCP resources from a target-native reference; preserve English identifiers and translated prose. Source topics and FR/JA/ZH dictionaries are reusable under MIT. | Planned adaptation; offline/native parity unverified. |
| 2 | `vroid_batch` | Help/batch/lifecycle (Task 9) | Planned: `run_batch`. Gap. `set_parameters` batches only typed writes in one domain; it is not a heterogeneous tool runner. Add serialized dispatch through existing validated handlers, bounded 1-200 operations, no recursion, stop-on-error default true, explicit partial results and no rollback, image count/byte caps. Hold a session gate without recursively reacquiring it. Never bypass attached uncertainty or stale-model guards. | Planned adaptation; offline/native parity unverified. |
| 3 | `vroid_status` | Session baseline (Task 10 audit) | Existing `get_status`, plus `get_attached_state`. Preserve mode, model token, ready/updating/busy, dirty and current file fields; audit field-level parity rather than returning an alias with an incompatible response. | Comparable baseline only; field audit pending; native unverified. |
| 4 | `vroid_create` | Session baseline (Task 10 audit) | Existing `new_character(variant=F00/M00)` with explicit model/discard guards. Source female/male translates to variants; source requires model menu while target can perform guarded replacement. Keep target guard. | Comparable baseline only; field audit pending; native unverified. |
| 5 | `vroid_open` | Session baseline (Task 10 audit) | Existing `open_character(filename, expected_model, discard_unsaved)`; attached file IO allows absolute paths, copy file IO is constrained. Source arbitrary absolute path must not silently bypass copy ownership policy. | Comparable baseline only; field audit pending; native unverified. |
| 6 | `vroid_save` | Session baseline (Task 10 audit) | Existing `save_character` and `save_character_as(path)` for attached sessions, `save_as(filename)` for owned copy. Preserve target overwrite/path policies and return actual file/hash evidence. Source path optional is only a convenience dispatcher. | Comparable baseline only; field audit pending; native unverified. |
| 7 | `vroid_export_vrm` | Ordinary VRM (Task 2) | Implemented source adaptation: `export_vrm` adds model_version/options/leave. Twelve strict options overlay observed native settings; omitted options never reset settings. Preserves stored metadata/permissions, integer VRM0/1 selection, model identity, staged no-overwrite publication and separate XWear path. Fresh preview -> staged apply -> reopen -> readback, at most one settings reapplication with effective values/warnings. Signature-derived native TaskCompletionSource<bool> and typed setters; task false/fault/cancel, possible dispatch failure or timeout never publishes or auto-retries. Retains handles until successful task, stable file and consecutive quiet preview polls; uncertainty forbids navigation/release. Both versions receive complete GLB chunk and embedded resource-reference checks. | Offline Python orchestration/validation and executable JS native doubles verified in Task 2. Native compatibility, actual reduction, delayed cleanup survival and visual/engine acceptance remain unverified. |
| 8 | `vroid_export_vrm_options` | Ordinary VRM (Task 2) | Implemented `get_vrm_export_options`: actual settings plus native choice indices, translated labels and managed values. Annotated as an edit because it enters a native screen; leave=True by default, explicit False keeps it open. Four consecutive idle polls require PreviewAvatar, no preview blocker/queued work and no model updating. Export leave=None preserves prior screen ownership; explicit leave controls are honored only when safe. Uncertain job status is inspectable without permitting cleanup/retry. | Offline lifecycle/readback/native-double tests verified in Task 2. Native option combinations and screen cleanup survival require a supported disposable lab. |
| 9 | `vroid_main_menu` | Help/batch/lifecycle (Task 9) | Planned: `return_to_main_menu`. Gap. Existing `new_character`/`open_character` contain native exit sequencing internally; `restart_session` recreates a process and is not return-to-menu. Expose guarded native menu transition, dirty refusal unless explicit discard, wait until edit root is inactive, invalidate model IDs. | Planned adaptation; offline/native parity unverified. |
| 10 | `vroid_exit` | Help/batch/lifecycle (Task 9) | Planned: `exit_vroid`. Gap. Detach leaves the process alive; restart creates another copy. Add graceful native quit, dirty/discard handling, response-before-exit and owned-copy vs attached rules. Do not implement as process kill. | Planned adaptation; offline/native parity unverified. |
| 11 | `vroid_framing_get` | Catalog/framing (Task 7) | Planned: `get_preset_framing`. Gap. Target measured regional capture framing and baseline locks are not a persistent category thumbnail configuration. Add read of shipped defaults merged with local overrides: top, bottom, half, distance, yaw, fit, resolved category/fallback. | Planned adaptation; offline/native parity unverified. |
| 12 | `vroid_framing_set` | Catalog/framing (Task 7) | Planned: `set_preset_framing`. Gap. Add validated category-level overrides in lab-local catalog/config; fractions 0-1, top < bottom, nullable half, distance/yaw/fit limits; keep committed defaults immutable. Feed these settings to situation thumbnail capture. | Planned adaptation; offline/native parity unverified. |
| 13 | `vroid_framing_reset` | Catalog/framing (Task 7) | Planned: `reset_preset_framing`. Gap. Remove one/all local overrides atomically and report effective defaults. Do not mutate ordinary capture baseline data. | Planned adaptation; offline/native parity unverified. |
| 14 | `vroid_list_groups` | Groups/parts/presets (Task 3) | `list_groups` merges exact active/leaf/stored identities, native type/resource/revision, topology fingerprint, discovery errors and exact native clear-option removal evidence. | Offline contracts and native doubles verified (Task 3); supported-binary/native acceptance unverified. |
| 15 | `vroid_get_params` | Groups/parts/presets (Task 3) | `list_group_parameters` exposes exact typed and raw bone/blendshape/color/unsupported enum entries. Reuses typed writers only with full group/path/template evidence; raw unknown scalar ranges and Bool/Float history writes remain explicitly unsupported. | Offline exact/stale/typed contracts verified (Task 3); native layouts/ranges require supported lab. |
| 16 | `vroid_get_item_params` | Groups/parts/presets (Task 3) | Group listing includes stored non-leaf groups. Group parameter discovery uses GetTransferableGroupBlendShapesQuery and worn GetClothingQuery colors, exact path/template ownership and native units. Conflicting source 0..1/0..100 prose is never used as a conversion. | Offline native-query doubles verified (Task 3); actual garment/accessory coverage and renderer material identity unverified. |
| 17 | `vroid_sections` | Groups/parts/presets (Task 3) | `list_sections` maps known full native group types to active-leaf sections and reports unknown types unclassified. Explicit group discovery facade, not actual UI navigation or every available preset category. | Offline section contract verified (Task 3); native acceptance unverified. |
| 18 | `vroid_categories` | Groups/parts/presets (Task 3) | `list_categories(section)` returns full native type IDs, distinct labels and every matching active group ID. Parameter-only active groups remain visible; native preset categories stay in list_presets. | Offline identity/ambiguity contract verified (Task 3); native acceptance unverified. |
| 19 | `vroid_enter` | Groups/parts/presets (Task 3) | `enter_category` resolves exact section/native category IDs to group controls. Multiple groups produce explicit ambiguity; ui_navigation=false. No fuzzy label writes or desktop input. | Offline facade and ambiguity checks verified (Task 3); no UI navigation claim. |
| 20 | `vroid_set_param` | Groups/parts/presets (Task 3) | `set_group_parameters` requires fresh exact {id,type,units,value} rows, validates every value/overlap/native command contract before first write, and returns partial application plus settled actual readback. Hex/fuzzy convenience input is deliberately not a write contract. | Offline strict value/overlap/cancellation and native doubles verified (Task 3); history/save/reopen native gates remain. |
| 21 | `vroid_set_blendshape` | Groups/parts/presets (Task 3) | Exact group-bound single/paired/template blendshape VM writers use actual native min/max and units. Source-proven native SetBlendShapeTransformParameterCommand adapter exists, but uncovered unknown-range raw controls are read-only pending metadata. | Offline typed reuse/template descriptors and raw refusal verified (Task 3); unsupported raw-range contracts remain explicit. |
| 22 | `vroid_set_bone` | Groups/parts/presets (Task 3) | Exact combined bone VM controls preserve opposing-half behavior. Native SetBoneTransformParameterCommand adapter follows source native generic dictionary shape; uncovered raw bone ranges/history contracts fail closed rather than guessing normalized units. | Offline pair/stale/type guards verified (Task 3); supported native command/VM behavior unverified. |
| 23 | `vroid_set_color` | Groups/parts/presets (Task 3) | Raw/worn exact owner+ColorPath/TemplateColorPath RGBA values use source SetColorParameterCommand history and readback; overlap aliases stay explicit. Shared binding identity is reported separately from unknown actual renderer/material identity. | Offline native generic Color ABI, prevalidation and readback doubles verified (Task 3); visual/material acceptance unverified. |
| 24 | `vroid_colorize` | Textures/materials (Task 4) | `colorize` composes global/texture/both within one exact active group, with exact material/layer filters, shared-binding/raster deduplication, conversion receipts, refreshed paths, per-target readbacks and stop-on-uncertainty partial results. Known BaseColor completion continues with unavailable readback explicitly labelled; no synthetic rollback or rendered-color claim. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 25 | `vroid_list_layers` | Textures/materials (Task 4) | `list_texture_layers` preserves group/image/node identities and additionally accepts exact query-derived shared material regions returned by `inspect_hair_materials`/`begin_hair_edit`. Conversion settles native PNG work and re-enumerates layers; existing canvas-only edits retain their guards. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 26 | `vroid_recolor_layer` | Textures/materials (Task 4) | `recolor_texture_layer` implements source multiply and HSV-unit-value/luminance colorize with strength in [0,1], alpha-byte preservation and explicit round-half-up RGBA8 publication. Current PNG hash, exact layer/image, metadata, dimensions and native-boundary current pixels guard replacement; returned PNG hashes describe actual readback. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 27 | `vroid_export_layer` | Textures/materials (Task 4) | `export_texture_layer` retains lab review publication and actual PNG SHA-256. The same native ComposeTiles/PNGUtil path now supports query-derived shared material image regions, without adding a guessed canvas navigation route. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 28 | `vroid_import_layer` | Textures/materials (Task 4) | `replace_texture_layer` replaces only an existing exact raster through LoadImageToEditableImageRasterLayerCommand. Input PNG/current layer hashes, dimensions, exact image/layer, metadata/order and boundary pixel snapshots are checked. One command preserves nonpixel state; existing new-overlay import and cosmetics canvas checks remain compatible. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 29 | `vroid_list_hair_materials` | Textures/materials (Task 4) | Canonical `list_hair_materials` now includes active native section channels and exact image bindings, alongside legacy thumbnail fields; `inspect_hair_materials` exposes active ownership and deduplicated global base overlays. MaterialColor preserves its actual section path; shared path IDs and native query metadata must resolve exactly. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 30 | `vroid_set_hair_color` | Textures/materials (Task 4) | `set_hair_material_color` writes exact section MaterialColor paths through SetMaterialColorCommand with immediate/post-settle GetMaterialColorQuery verification. BaseColor uses global SetBaseColorCommand, reports unavailable exact readback and never substitutes HairSetColor. Neither getter verification nor known command completion claims visible acceptance. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 31 | `vroid_list_hair_groups` | Hair groups (Task 5) | `list_hair_groups(expected_model, category=None)` maps all active native leaves through exact category transferable types, including siblings absent from the selected editor, without changing selection. One complete membership-only inventory avoids removal catalogs; group discovery is linear, read-only geometry pins are released per group, and group/aggregate point work is bounded. Concrete paths include brush grouplet identity; tagged material references read only their selected native arm. Counts and mean control-point polyline lengths use native control-point coordinates, independently of rendered spline length and procedural Length. | Offline algorithm/native-double/runtime tests verified; supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 32 | `vroid_set_procedural_hair` | Hair groups (Task 5) | Only exact assembly `ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296` has verified bindings. A matching existing UI-owned property supplies true native b41/b42 Length and b51/b52 HairCount controls with live bounds. Other paths, including hidden siblings, use native managed captures b97/b102 and the real Action/ModifyProceduralHairGroupParameterSetCommand constructor, with exact owner/path validity checks and statically proved native UI bounds (Length Single 0.1..1, HairCount 1..20). No property or JS history delegate is created. Single conversion precedes range validation; all requested values are admitted before writes, then each scalar is settled/read back before the next. `793eb5fc...` remains unsupported for this descriptor. Receipts distinguish setter calls, explicit command calls and unknown merged history entries. Geometry remains separate from Length. See [static evidence](docs/native-evidence/2026-11-07-procedural-hair.md). | Static native identity and offline algorithm/native-double/runtime tests verified; supported native dispatch ABI, actual Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 33 | `vroid_scale_brush_hair` | Hair groups (Task 5) | Nonroot points scale about their own original root, finite factor (0,10]. Whole boxed ControlPoint copies preserve unknown fields, normal/UV and materials. Captured owner/full strand identity is checked with minimal native lookups before invocation; constructors and rejected ownership checks do not count as command attempts. Actual coordinates must equal intended Math.fround components exactly. Completed calls, verified points and genuinely changed geometry are separate; definite prewrite rejection preserves usability, whereas partial/invoked-uncertain work blocks replay. | Offline algorithm/native-double/runtime tests verified; supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 34 | `vroid_clone_brush_hair` | Hair groups (Task 5) | One CloneBrushHairGroupCommand is scoped to the exact source transferable/captured owner. The original must remain present and exactly one new brush group under that same transferable/owner must appear; unrelated same-category additions are never translated. Full child/group/grouplet identities and source-copy material/guide/geometry are checked. Every offset point, including zero-offset clone coordinates, has exact Single readback; receipts return new IDs and distinguish completed native calls from verified changed points and unknown undo entries. Offsets use native control-point coordinates, without world conversion. Ambiguous/partial work is never retried blindly. | Offline algorithm/native-double/runtime tests verified; supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 35 | `vroid_undo` | Session baseline (Task 10 audit) | Existing `undo(expected_model, steps)` is stronger bounded multi-step native history. Relist IDs/state after structural changes. | Comparable baseline only; field audit pending; native unverified. |
| 36 | `vroid_redo` | Session baseline (Task 10 audit) | Existing `redo(expected_model, steps)`; same caveat. | Comparable baseline only; field audit pending; native unverified. |
| 37 | `vroid_screenshot` | Camera/preview/capture (Task 6) | Implemented paired rectangular output, explicit MSAA 1/2/4 and SSAA 1/2/3, aspect-aware fixed/regional framing and preserved square/photo/review defaults. `current_editor` copies the owned live camera pose and verifies an aspect-adapted projection that contains the source view without crop or distorted proportions. `clean=False` uses an identity-checked one-shot Unity end-of-frame backbuffer read at actual screen dimensions/quality, rejects clean-render overrides and never falls back. `screenshot_metadata` returns image plus effective plan/framing/provenance without duplicated base64. | Task 6 offline math/runtime/native doubles verified; live native callback, UI/color/orientation, image and cleanup acceptance unverified. |
| 38 | `vroid_list_presets` | Groups/parts/presets (Task 3) | `list_presets` adds case-insensitive ID/resource search and owned_only=False locked metadata while preserving owned-only defaults. Separate all-category PlayFab catalog pages expose price/set/usable/locked, exact selectable IDs, nonselectable catalog-only IDs and explicit completeness/next_offset. | Offline search/catalog pagination/ownership doubles verified (Task 3); catalog discovery never authorizes locked application. |
| 39 | `vroid_apply_preset` | Groups/parts/presets (Task 3) | Optional preserve_material invokes the proven native flag for owned simple built-ins; clear/custom/set/unknown-set options are refused. Snapshots/restores/readbacks only exact compatible color-owner/resource/revision/path identities; each binding reports preserved/restored/incompatible/unverified. all_materials_preserved remains false. | Offline preserve flag, actual color restoration and incompatibility doubles verified (Task 3); texture/raster/material coverage and native appearance unverified. |
| 40 | `vroid_clothing_colors` | Textures/materials (Task 4) | Reuses Task 3 worn-color query bindings and exact owner/ColorPath/TemplateColorPath history writes in composed colorize, with binding deduplication and post-settle color readback. Query-derived color sharing is kept separate from unestablished renderer material identity. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 41 | `vroid_begin_clothing_edit` | Textures/materials (Task 4) | `begin_clothing_edit` requires complete actual active ownership, executes source BeginClothingAdvancedEditCommand(ids,group,"Layer"), waits for native readiness/PNG callbacks and returns fresh layer/image IDs. Explicit screen_entered=false; no unproven clothing canvas route is added. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |
| 42 | `vroid_measure` | Groups/parts/presets (Task 3) | Existing `get_height()` returns native label and current live centimeters, preferable to source `boundsMaxY*100`. Verify measurement convention when comparing source results, hair/footwear included as applicable. | Comparable baseline only; field audit pending; native unverified. |
| 43 | `vroid_set_body_size` | Groups/parts/presets (Task 3) | `set_body_size` separately zeros global scale and solves gender-specific FigureHeight/FigureSlender with native VM bounds and live GetBodyHeight feedback. Optional source BMI-to-waist is labeled heuristic, not measured mass. Exact gender/group/pair evidence required; failed convergence restores all snapshotted pairs when state is known and reports restoration failure/uncertainty. | Offline invalid-input, feedback, nonconvergence/restoration/cancellation contracts verified (Task 3); actual supported-model sizing unverified. |
| 44 | `vroid_preset_cache_search` | Catalog/framing (Task 7) | Planned: `search_preset_cache`. Gap. Shipped English label overlays are not a dynamic offline persistent catalog. Add preset/custom entries, stable resource/revision keys, tokenized all-word search over labels/descriptions/tags/colors, category/kind/owned/annotated/status/removed filters and preview provenance. Cache reads must work while app is offline. | Planned adaptation; offline/native parity unverified. |
| 45 | `vroid_preset_cache_annotate` | Catalog/framing (Task 7) | Planned: `annotate_preset_cache`. Gap. Add author/date history, manual label priority, append/replace semantics for description/tags/colors, atomic writes and concurrency lock; scan must retain annotations and removed entries. Bound strings/lists and prevent accidental cache escape. | Planned adaptation; offline/native parity unverified. |
| 46 | `vroid_preset_thumbnail` | Catalog/framing (Task 7) | Planned: `preset_thumbnail`. Partial. Target `preview_presets` supplies native thumbnails for 1-6 fresh owned preset IDs, without applying anything. Source resolves stable catalog keys offline, prefers situation thumbnail then native icon, including custom item icon extraction. Add catalog image resolution with bounded validated paths and kind/provenance; keep native vs on-mannequin distinction. | Planned adaptation; offline/native parity unverified. |
| 47 | `vroid_preset_cache_sync` | Catalog/framing (Task 7) | Planned: `sync_preset_cache`. Gap. Enumerate all preset pages/categories and registered custom closet revisions; keep first/last seen, fingerprints, new/changed/removed/returned, source build/session and persistent native icons. Unknown custom enumeration must not mark every custom removed. No avatar mutation is needed for native icon sync. | Planned adaptation; offline/native parity unverified. |
| 48 | `vroid_preset_cache_build` | Situation thumbnails (Task 8) | Planned: `build_preset_thumbnails`. Gap. Native thumbnail read is not situation capture. Source strips clothing/underwear/hair, applies tested item, frames and captures, then tries restoration and warns it is not guaranteed identical. Implement in a disposable isolated mannequin/session, never silently strip a user's live model. Record tested slot, retained/removed parts, orientation, framing, dimensions, source and hash; return incomplete rows on failure. | Planned adaptation; offline/native parity unverified. |
| 49 | `vroid_camera` | Camera/preview/capture (Task 6) | `editor_camera` implements get/angles/relative rotate/zoom/pan/reset/named native mode/projection toggle/custom, with bounded typed inputs and terminal motion polling. Exact active edit-root/engine/bus/face/controller ownership; distinct single-camera and instantiated multi-group alternatives, rejecting ambiguous active primaries. Reads actual owned camera projection/FOV/orthographic size; unavailable pan/zoom scalars stay unavailable. Pan/zoom are native deltas. Existing photo controls remain separate. | Task 6 offline action/ownership/enum/settled-readback tests verified; native movement/visible framing unverified. |
| 50 | `vroid_apply_custom` | Groups/parts/presets (Task 3) | `apply_custom_item(filename)` validates bounded safe ZIP metadata and matches an already registered path/resource/custom-resource/revision using byte and metadata identity. Native load/deserialization/root/type/revision/no-migration preflight precedes exact registered option selection. Windows source pin survives uncertainty. No arbitrary registration, profile copying or migration; later catalog wrappers must resolve keys to this validated file/identity. | Offline ZIP/byte/registry/native-compatibility doubles verified (Task 3); full native-format acceptance remains gated by supported lab. |
| 51 | `vroid_remove_item` | Groups/parts/presets (Task 3) | `remove_items` resolves exact group ID/full native type and prevalidates all requested groups against exact native clear capability. Uses RemoveTransferableGroupAndChildren, polls requested-group absence and returns remaining inventory/per-group partial outcomes. Missing capability is nonremovable; no invented descendant registry or short-suffix remove-all. | Offline mandatory/stale/partial failure and native command doubles verified (Task 3); descendant identities not independently established; native acceptance unverified. |
| 52 | `vroid_face_preview` | Camera/preview/capture (Task 6) | `face_preview` lists/filter raw current-model face shapes and applies 0..100 weights, explicit reset-to-zero or snapshot restore with readback. Exact name wins; ambiguous suffixes fail before any setter. Current active edit-root/engine/bus/ModelOrigin/renderer/mesh identities are checked; no scene scan or saved-expression command. Tracked identity/weights are checked at clean current/fixed capture and app-frame pickup; animation/rebuild can invalidate them. Named `preview_expression` remains separate. | Task 6 offline native/ambiguity/reset/restore/stale-state tests verified; actual deformation, rebuild and visual acceptance unverified. |
| 53 | `vroid_begin_hair_edit` | Textures/materials (Task 4) | `begin_hair_edit` validates an actually worn shared material, executes source BeginHairMaterialAdvancedEditCommand(path,"Layer",true), settles PNG work and returns fresh query-derived material/image/layer mappings. Explicit screen_entered=false; shared ownership is not inferred from an unrelated hair group. | Offline pixel/runtime/native-boundary behavioral tests verified (Task 4); supported native ABI, Undo/Redo, save/reopen and visual acceptance remain unverified. |

## Source files, destination ownership and MIT attribution

Source copyright: **Copyright (c) 2026 mcjo79 and vroid-mcp contributors**.
The complete source `LICENSE` is preserved by file-level copy in
[licenses/mcjo79-0dc7d5e.txt](licenses/mcjo79-0dc7d5e.txt); see also
[NOTICE](NOTICE) and [LICENSING.md](LICENSING.md). All paths below are
relative to that fixed source revision unless marked target. This table is
a transfer ledger: documentation/reference adaptation is recorded now;
runtime destinations are planned until their implementation commit is recorded.

| Source files/reference | Intended destination/owner | Transfer state at Task 1 |
| --- | --- | --- |
| `LICENSE` | `licenses/mcjo79-0dc7d5e.txt`, NOTICE, LICENSING.md | Full MIT text copied; provenance added. |
| `mcp_server/vroid_mcp.py` (tool schemas/dispatch), `README.md`, `docs/AGENT_REFERENCE_EN.md` | This 53-row matrix and domain contracts | Capability/reference documentation adapted; no source runtime copied. |
| `VRoidMcpBridge/VrmExport.cs`; read-only API references in `FileLifecycle.cs`, `LifecycleHooks.cs`, `HttpBridge.cs` | `vroid_mcp/runtime_ordinary.py`, `vrm_export.py`, `vrm_options.py`, `tools_ordinary.py`, `agent/vrm_export.js`, metadata integration in `ordinary_extensions.js`, explicit module ordering/status inspection in `bridge.py` (Task 2) | Adapted settings/lifecycle/native post-dialog API behavior at fixed source revision `0dc7d5eb3cf27f7f943713960cac1b65f479a876`; MIT notice retained in `licenses/mcjo79-0dc7d5e.txt`. No HTTP/Harmony/BepInEx runtime transferred. Commit subject: `feat: migrate native VRM export settings`. Offline tests only; native acceptance remains open. |
| `VRoidMcpBridge/VRoidApi.cs`, `Catalog.cs`, `Presets.cs`, `CustomItems.cs`, `ClothingSliders.cs`, `AdvancedEdit.cs`; silhouette dispatch in `mcp_server/vroid_mcp.py` | `agent/groups.js`, preset/registry extensions and focused Python group/silhouette/custom-file modules (Task 3) | Implemented source adapters with offline contracts; unknown ranges/history/layouts remain explicit. No guessed aliases or weight-as-mass claims; native acceptance unverified. |
| `VRoidMcpBridge/Textures.cs`, `AdvancedEdit.cs`, `Hair.cs`; colorize composition in `mcp_server/vroid_mcp.py` | Texture/material runtime, pixel helpers and JS (Task 4) | Adapted conversion, exact material discovery/commands, existing-raster replacement history and source recolor algorithms; MIT notice retained in `licenses/mcjo79-0dc7d5e.txt`. Native acceptance unverified. |
| `VRoidMcpBridge/HairShape.cs` | `agent/hair_groups.js`, `runtime_hair.py`, `tools_hair.py` and narrow parameter/group/operation composition (Task 5) | Adapted concrete group queries, native control-point polyline statistics, root-relative group scale, native whole-group clone/offset and exact procedural scalar/query behavior from fixed source revision `0dc7d5eb3cf27f7f943713960cac1b65f479a876`; MIT notice retained in `licenses/mcjo79-0dc7d5e.txt`. No BepInEx runtime or JS-owned managed modifier transferred. Independently derived checksum-scoped VM/native-managed-modifier descriptors in `agent/hair_procedural.js` and `agent/hair_procedural_fallback.js`, including verified immutable native UI bounds and Action constructor ABI, are recorded in the versioned native-evidence note; native binaries and method bodies are not included. |
| `VRoidMcpBridge/CameraView.cs`, `FacePreview.cs`, `PreviewCapture.cs`; screenshot portion of `VRoidApi.cs` | `agent/editor_preview.js`, `editor_capture.js`, `app_frame.js`, capture-quality/framing/operation composition; Python `runtime_preview.py`, capture runtime/quality/tools (Task 6) | Adapted native actions/raw-face/rectangular render behavior from fixed mcjo79 revision. MIT notice retained in `licenses/mcjo79-0dc7d5e.txt`; existing brainrom capture notices retained. Supported-build ownership and one-shot Awaitable end-frame backbuffer route were independently derived from ed65 metadata/static control flow; no ScreenCapture wrapper exists there. No BepInEx, managed callback history, desktop input or second control kernel. |
| `mcp_server/preset_cache.py`; catalog/preset/custom metadata native references | `preset_catalog.py`, `catalog_framing.py`, `tools_catalog.py` and gallery orchestration (Tasks 7-8) | Planned storage/search/annotation/framing and disposable situation images; no native images vendored. |
| `mcp_server/help_i18n.py`, `tool_i18n.py`, `prompts.py`, `docs/AGENT_REFERENCE_EN.md`, batch/help dispatch; `FileLifecycle.cs`, `ContextState.cs`, `LifecycleHooks.cs` | Help/resources, batch/session gate and guarded menu/exit (Task 9) | Planned selective prose/behavior adaptation; target schemas stay authoritative. |
| `Plugin.cs`, `HttpBridge.cs`, `Interop.cs`, BepInEx/Harmony build/runtime and source MCP JSON-RPC transport | None | Do not incorporate the second control kernel; native API references may inform Frida adaptations with provenance. |

Task 1 scratch changes are local regression fixes in the target check runners,
not mcjo79 runtime-derived code. Subsequent transfers must narrow the relevant
source paths above to the actual adapted files and list the destination commit.

## Other candidate dispositions

| Candidate | Useful material and disposition | Provenance/verification limit |
| --- | --- | --- |
| brainrom/vroid-studio-mcp | Retain already adapted labels, paired/mixed color semantics, capture quality/framing. Further useful patterns are readiness-driven completion, queue health, exact disambiguated keys, combined stock/custom listing and signal-driven tests. Do not copy its BepInEx/Harmony transport/build. | Existing adapted revision `a6b0719d01fa6cac9a857956907243d9916390b2`; Copyright (c) 2026 Ilya Chelyadin and vroid-studio-mcp contributors, MIT. Keep the five existing per-data-directory LICENSE/NOTICE/source hashes. New material needs its own exact revision/file record; no new code copied in Task 1. |
| Karylcode/VRoid-MCP | Historical Python/Frida relative; target already exceeds its published 42-tool scope in several domains. No independent wholesale feature migration recommended. Only narrowly justified later MIT material may be reused. | Preserve historic unlicensed baseline `9b264d3ad3a33bea2e18e91a0476e395246a6be6` record in UPSTREAM.json. Later MIT revision `baaa94e2fdc0419c68cb83b0ecc0b61fcc5661dd`, Copyright (c) 2026 Karylcode, already has `licenses/karylcode-upstream-20261023.txt`. Do not restore rewritten baseline code or recast its former licence status. |
| nhodges/mcp-vroid | Linux/Hyprland/Wine pointer/OCR stack does not transfer to Windows background-native Frida. Fresh-screenshot coordinate spaces, window identity and post-action visual confirmation are conceptual QA ideas only. No code migration recommended. | Copyright (c) 2026 Nuri Hodges, MIT, observed in read-only snapshot. Snapshot commit not verified; no commit is invented. GUI/OCR fallback requires a separately requested workflow. |

## Required later acceptance

Use a supported disposable lab and keep exact source/build/fixture hashes.
Per-domain offline tests are required but cannot prove IL2CPP marshaling,
native history or visible effect. Native texture acceptance must compare RGBA
pixels and appearance through Undo/Redo and save/reopen; hair acceptance must
check root invariance, group IDs, offsets and materials; preview/camera/capture
must verify native state, cleanup and image provenance without foreground input.
Menu/exit need dirty/discard and ownership checks. Catalog imagery needs exact
remaining-slot/framing evidence and explicit restore/discard results.

Ordinary export acceptance additionally needs VRM0 and VRM1, baseline and one
changed option at a time, actual mesh/material/image/bone counts, metadata,
two consecutive exports, explicit leave behavior, boolean task completion,
stable valid output, healthy process after delayed exit and Player.log review.
Cold import/render and visual/motion inspection remain separate acceptance gates.
The source export notes are historical evidence of its implementation only.

## Task 3 implementation boundary

Implemented nine group/body tools plus backward-compatible preset search and
preserve-material options on the feature branch. Tests cover exact bindings,
paired controls, stale group revisions, all-before-write validation, raw native
history ABI checks, registered current-format preflight and uncertain cancellation.
Raw floats without independently discovered native bounds remain explicit read-only
rows. Unsupported native Bool/Float history constructors are not invented.

Source adapters are `agent/groups.js`, the registry metadata addition to
`agent/ordinary_extensions.js`, preset metadata in `agent/operations.js`, and
`vroid_mcp/runtime_groups.py`, `silhouette.py`, `custom_item_file.py` and
`group_validation.py`, exposed by `tools_groups.py`. Adapted source files are
VRoidApi.cs, ClothingSliders.cs, AdvancedEdit.cs, Presets.cs, CustomItems.cs,
Catalog.cs and the section/silhouette algorithms in mcp_server/vroid_mcp.py at
the pinned source commit; the MIT notice in licenses/mcjo79-0dc7d5e.txt applies.

Native dictionaries are inflated with path interfaces and actual value types;
no fake managed key/value structs or guessed raw Bool/Float commands are used.
Raw history command counts are exact on successful raw dispatches. Native VM
internal command counts remain unknown, rather than being equated with one undo.
Preservation reports incomplete material coverage even when all known colors match.
Removal verifies the requested group and returns a fresh full inventory; the native
child-removal command does not establish a separately discovered descendant list.

Offline Python/native-double checks do not establish supported-binary compatibility,
Undo/Redo, save/reopen, actual garment/accessory coverage, native file-format acceptance,
export or visual quality. The installed unsupported app was not launched or attached.
Task 10 owns final tool and source manifest regeneration.

## Task 6 implementation boundary

Task 6 adds `editor_camera`, `face_preview` and `screenshot_metadata`, and extends
the existing image-returning `screenshot` without changing its square/view/quality
defaults. Camera inputs are finite and bounded; unrelated action arguments are
rejected. Native enum values are resolved by name. Motion completion is polled,
and loss/cancellation after a preview mutation retains the uncertainty barrier.
Raw preview weights are renderer state only, with explicit zero-reset versus
original-weight restore. Ambiguous suffixes reject instead of the source's
multiple-match broadcast. Snapshot restore refuses changed renderer/mesh identity.

Clean sides stay within 256..2048 and internal work within 8,000,000 pixels;
budget clamping preserves aspect with reported per-axis rounding. MSAA accepts
1/2/4 and reports the created GPU texture's actual downgrade. Rectangular new
paths do not clear UI selection or hide controllers. The old default fixed/photo
preparation remains compatible. Photo camera configuration/target/enabled state,
temporary cameras, render targets and CPU textures have explicit finally cleanup.
`current_editor` uses a cloned camera with exact copied/read-back world pose.
Projection rows 0/1 are scaled by min(1,A/B) and min(1,B/A), where A is the live
source pixel aspect and B is the final output aspect. This expands the frustum
to contain the source view while keeping projected subject proportions; the live
matrix is unchanged. Source/effective matrices, clip scale, actual full render
viewport and per-axis final resampling are reported separately. Projected square
and circle tests cover portrait/landscape source/output, perspective/orthographic
and rounded SSAA cap dimensions. Fixed views instead retain their vertical FOV
while adapting the matrix to output aspect. The supported ed65 binary strips
`set_aspect`, so only actual supported projection-matrix APIs are used.
[Unity 6 documents that Camera.targetTexture renders to the whole texture and
ignores rect/pixelRect](https://docs.unity3d.com/ja/current/ScriptReference/Camera-targetTexture.html);
no viewport-based letterbox assumption is used.

Multi-rig camera selection uses the exact bus-owned rig's instantiated-group
dictionary keys and requires one active enabled primary. Multiple candidates fail
closed; the template is never treated as authoritative current projection. A
single attached camera is a separate valid route, with no required multi-rig.
Editor/photo controllers must be distinct. The active screen and current-face
renderer must match the exact model scope on every use.

The allowlisted ed65 binary has no managed ScreenCapture class. Application frame
capture instead wires Unity's idempotent Awaitable gate and installs a bounded,
main-thread-only one-shot on `OnEndOfFrame.onLeave`, then reads the actual screen
backbuffer with `ReadPixels`. No ordinary frame-pump sampling, clean-render
fallback, UI change, desktop focus or input is used. Native screen area over 8M
is refused. App MSAA is explicitly the live QualitySettings value, not a claim of
GPU RenderTexture verification; SSAA remains application-owned. Hooks, textures,
active render target and retained results have success/error/timeout/teardown
cleanup. No model-history callbacks are retained.

Offline evidence: 834 Python tests passed, including 113 focused host/capture/
attached regressions; five new JavaScript behavior/native-double suites and five
affected existing suites passed. This proves the contracts under doubles, not
IL2CPP marshaling, live active-view selection, end-frame pixel freshness, complete
screen UI, native color/orientation, rendered facial deformation, preservation
after native rebuilds, or visual quality. No VRoid process was launched/attached,
registry changed, build allowed, or installed service modified. Task 10 owns final
manifest regeneration; a supported disposable native lab remains required.
