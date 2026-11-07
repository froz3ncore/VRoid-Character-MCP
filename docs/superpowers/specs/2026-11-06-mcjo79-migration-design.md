# mcjo79 capability migration design

## Intent and authority

The user has forked froz3ncore/VRoid-Character-MCP as BunnyBlack/VRoid-Character-MCP and requested a local checkout in tools, a mcjo79 reference checkout in temp, a written plan followed by implementation, conventional Git and superpowers development, a dev directory for future projects, and workspace Agents.md plus CLAUDE.md containing @Agents.md. The objective is an extensible tool that a capable model can improve while using it. This is a capability migration into the existing runtime, not a deployment or a change of native backend.

The user explicitly requested planning followed by execution. Routine implementation decisions below are the implementer's proposals within that authorization; no additional design approval gate is imposed. Implementation happens on feat/mcjo79-capability-migration in the fresh tools checkout, preserving main. Temporary planning/review/testing data lives under project temp, overriding skills' default scratch locations.

## Fixed inputs and current state

- Target origin: https://github.com/BunnyBlack/VRoid-Character-MCP.git, base b02b108ab4a8b4333ecf206a199a7a0403aa7ffe.
- Target upstream: https://github.com/froz3ncore/VRoid-Character-MCP.git.
- Primary source: https://github.com/mcjo79/vroid-mcp.git, commit 0dc7d5eb3cf27f7f943713960cac1b65f479a876, MIT.
- Target already has 103 tools, Python FastMCP, runtime domain mixins, a Frida IL2CPP main-thread bridge, model tokens, copy/attached ownership, native history and uncertainty barriers.
- Target already exports ordinary VRM 0/1, edits typed parameters, supplies native preset icons and extensive cosmetics, captures, hair primitives and XWear operations. Similar primitives do not prove source feature equivalence.
- Source has 53 tools. Every one must appear in MIGRATION.md with target mapping, implementation disposition, tests and native-verification status. Source-prefixed aliases and byte-identical response contracts are not required. Missing useful behavior must be implemented, not hidden by aliases or a broad claim of equivalence.
- At baseline, installed Steam build 26267394 (`3334b166...`) was not one of the two supported 2.14.0 assemblies. The requested **2.16.0** addition now has a [separate build compatibility task](../plans/2026-11-07-vroid-216-compatibility.md). Preserve existing 2.14.0 behavior and require positive build/channel/ABI evidence before admitting a new binary. No installed app files or active user models are changed by this migration.

## Approach

Use target-native Python/Frida modules and adapt source native queries, commands and host-side algorithms. Keep one transport, one session gate and one model identity policy. A second BepInEx/HTTP backend would duplicate lifecycle, deployment and safety responsibilities; wholesale source aliases would conceal different semantics. Neither is needed for this migration.

brainrom contributes existing and newly considered readiness, exact-binding and deterministic validation patterns, with its existing source notices preserved. Karylcode's inspected later MIT feature surface is already covered by the target; do not resurrect rewritten historical code. nhodges supplies useful post-action visual-check ideas, but its Linux pointer/OCR backend is not incorporated into a Windows native server. These dispositions belong in MIGRATION.md.

## Global constraints

- Preserve Python >=3.10, frida==17.16.0 and mcp==1.30.0 unless a concrete incompatibility requires an explicit recorded change.
- Preserve supported-build checks, model identity, session serialization, native undo/history semantics, no-overwrite publication and copy/attached ownership. Unknown or uncertain native work must not be retried automatically.
- Validate all user input before native mutation; reject bool-as-int, NaN/infinity, wrong shapes, unknown keys and ambiguous identifiers. Resolve native members from inspected source/signatures, never fabricated type names.
- Temporary files, environments, caches, logs, review artifacts and pytest data stay under the relevant project's temp directory. No temporary file on C:. Persistent catalog/assets stay under the lab/project, never in the installed app or user profile by default.
- Authored/modified text is UTF-8 without BOM and CRLF. Preserve byte-pinned inherited data; do not mass-rewrite untouched sources. Check encoding and question-mark loss before delivery.
- Preserve MIT notices and record source repository, fixed revision, adapted files and destination modules. Native assets and generated thumbnails are local data, not redistributable code assets.
- Native unit doubles prove orchestration/algorithms, not IL2CPP binary compatibility, visual quality, save/reopen or engine acceptance. Report those layers separately.

## Capability requirements

### A. Persistent catalog and framing

Provide a lab-local persistent catalog of built-in presets and registered custom items, keyed by stable resource identity rather than model tokens. Preserve manual label, description, tags, colors, annotation author/time and history across scans, including removed and returned entries. Track source build/session, first/last seen, revision/fingerprint and new/changed/removed status. An incomplete/failed custom scan must not mark every custom item removed.

Offline search and annotation must not start VRoid. Search uses all query words and category, kind, ownership, annotation, status and removed filters with bounded results. Writes are atomic and mutually exclusive across processes; malformed catalogs fail without overwriting evidence. Scratch/locks use the catalog's project temp. Native and situation previews carry distinct provenance; image paths and bytes are validated before display.

Expose category framing get/set/reset with immutable defaults and local overrides. Fields are top and bottom as fractions measured downward from model top, nullable half as a fraction of model height, distance as a dimensionless multiplier of the computed region span, yaw in degrees and fit=region|full-body. Source frame_region multiplies distance by span; it is not an absolute metre value. Use actual model min/max bounds rather than assuming the bottom is world y=0. Validate 0<=top<bottom<=1, half null or 0<half<=1, 0.1<=distance<=100, -360<=yaw<=360. Reset affects overrides only. Framing is consumed by situation captures, not merely stored.

For region fit, H=maxY-minY, world top=maxY-top*H and world bottom=maxY-bottom*H. Numeric half specifies the horizontal half-width divided by H about the model's projected center at the requested yaw; null selects the full projected horizontal bounds. Preserve aspect when fitting or cropping this region. Full-body fit contains every projected model-bound corner and uses the whole model: stored top/bottom/half are explicitly inactive in effective capture metadata. Treat distance as the requested span multiplier; report requested/effective values and any adjustment needed for full-body containment rather than silently clipping. The source alternate crop_model establishes the half-width interpretation, but its active crop_center path ignores numeric half and its full-body behavior is largely a label. These stronger target semantics need geometry tests for translated bounds, nonfront yaw, distinct numeric half values, aspect preservation and full-body containment.

### B. Exact discovery, parts and body controls

Expose active transferable groups, section/category discovery, raw bound blendshape/bone/color/item parameters and group-filtered edits with exact native IDs and units. Prefer existing typed controls when they expose the same binding, but include an exact native query/command adapter for real uncovered bindings. Ambiguous labels must not become writes. Refresh IDs after topology/preset changes. Include worn garment colors and shared material identities.

Extend native preset listing/catalog discovery for search and locked metadata without enabling locked application. Support resolving a validated current-format .vroidcustomitem file or catalog key to an already registered native item, with exact registered path/resource/revision, ZIP metadata and native type checks. Source CustomItems.cs requires an existing FileCustomItemModel; it does not register arbitrary files. A project copy may identify a registered item only through matching bytes and metadata, and must not silently create a registry entry. Generic removal resolves real group IDs/types, refuses mandatory/nonremovable groups, returns per-group outcomes and verifies removal. Preserve-material preset application snapshots/restores compatible exact material state with explicit incompatibility results.

Keep set_height's existing proportional solver. Add explicit silhouette body-size behavior for the source FigureHeight/FigureSlender algorithm, with gender/variant matching and optional BMI-derived waist adjustment clearly labeled heuristic, never measured body mass. Validate physical inputs, use actual native binding ranges, solve/read back height, and report partial application/restoration failures.

### C. Native texture and color behavior

Add clothing and shared hair-material preset-to-editable conversion through the source BeginClothingAdvancedEditCommand and BeginHairMaterialAdvancedEditCommand, followed by native PNG callback readiness and fresh image/layer enumeration. These commands establish conversion, not navigation to a texture canvas; return screen_entered=false unless an independent native navigation route is established. Shared hair images come from GetHairMaterialQuery texture sections. Preserve existing cosmetics-only open_texture_editor checks.

Add direct model-addressed replacement of an existing raster layer, preserving name, ordering and nonpixel state. Require exact model/layer/image identity, expected current PNG hash, input PNG hash and matching dimensions, and recheck the current content at the native write boundary; use native raster history commands. This direct source route does not require an unproven active-canvas navigation. Existing canvas-based operations keep their guards. Add alpha-preserving multiply and source luminance/colorize recoloring with strength in [0,1]. Reuse existing PNG handling where possible. Return actual hashes and history/readback evidence.

Expose exact shared hair material color channels/base overlays and per-garment colors. BaseColor IDs are global even when listed within material sections; deduplicate them and distinguish unavailable exact-key readback from verified material readback. Do not substitute aggregate HairSetColor as arbitrary base-ID evidence. Colorize composes typed global/material writes and selected raster recolors (global|texture|both), with material/layer filters and per-target results. Stop on uncertain native work; do not claim visible change from a getter alone. Existing new-overlay import stays compatible.

### D. Hair group operations

Provide aggregate group discovery with brush/procedural classification, strand counts and control-point polyline lengths. Label these lengths and clone offsets as native control-point coordinates, not rendered arc length or world metres: source HairShape.cs applies no guide transform. Confirm procedural Length/HairCount through real native controls/commands with bounds and readback, without equating its Length scalar to measured geometry. Scale every point except each strand root about that root; preserve normal/UV and material identity. Clone a whole brush group using the source native CloneBrushHairGroupCommand, then apply finite XYZ offsets in the declared native coordinate space to all cloned points. Return new IDs, actual affected strands/points/history count and partial failure status. Do not substitute strand duplication or guide scaling.

### E. Camera, preview and capture

Add editor camera get/angles/relative rotate/zoom/pan/reset/native mode/projection/custom using actual editor camera API with state readback. Bind camera discovery to the current editor/model identity, refusing ambiguous global camera matches. Source projection is a toggle, and pan/zoom deltas are native inputs with unestablished physical units; do not invent absolute projection setters or unit conversions. Report actual available camera state and unavailable fields honestly. Preserve existing photo camera tools. Add temporary raw facial blendshape list/filter/weight/reset behavior scoped to current model preview renderers without modifying saved expression definitions; include preview identity and restoration/reset evidence, and do not scan or reset unrelated scene renderers.

Extend screenshot in a backward-compatible way for rectangular dimensions and explicit bounded MSAA/SSAA controls on clean avatar renders. Keep the existing 256..2048 side limits and 8,000,000-pixel internal render cap. Preserve fixed-view defaults and add an explicit current-editor view using the verified live camera, so editor camera actions can affect a requested capture. Distinguish clean avatar render from Unity application-frame capture; implement the latter only through native capture, with no desktop focus, mouse or keyboard automation. Application-frame capture uses actual native screen dimensions and quality, not requested clean-render overrides; reject incompatible overrides rather than misreporting them. Never silently fall back from clean render to application frame. Return effective dimensions/quality/projection/framing and provenance metadata where applicable.

Rectangular current-editor captures must preserve the character's apparent proportions. If the source view and requested image differ in aspect ratio, fit the source projection into an undistorted viewport or use an explicitly reported aspect-correct projection on the clone. Keep source state unchanged and distinguish source, target and effective framing. Test projected geometry at differing aspects rather than treating matrix equality as sufficient.

### F. Ordinary VRM export

Extend existing export_vrm, retaining integer version 0|1 and staging/no-overwrite. Add optional model_version, explicit leave control and an optional validated options object: delete_transparent, hair_cross_section, hair_smoothness, hair, face, body, outfit, material_mode, combine_hair, texture_mode, atlas_resolution, hair_bones. Sliders are strict integers 0..100; choices must be validated against native option lists. Omitted options preserve existing behavior; a supplied options object overlays observed native settings and returns requested/effective values and warnings.

Expose get_vrm_export_options(expected_model, leave=true), returning actual native choice labels/values and settings. Screen transitions are documented and annotated as edits. Preserve stored VRM metadata/permissions while overriding title/author/model_version only when supplied.

Implement source-required fresh reopen, staged settings application, preview quiet checks and one bounded reapply/readback if VRoid changes settings. Use native OnVRM1SettingChanged/OnVRMSettingChanged with signature-derived TaskCompletionSource<bool>, retained through completion. Check actual bool result, faults/cancellation and stable complete output. A potentially dispatched failure/timeout marks uncertainty, retains necessary handles and does not pop screens or auto-retry. Default leave=None preserves prior screen ownership behavior; explicit true/false is honored safely. Query defaults leave=true.

Validate both GLB chunks/resource references and correct VRM version before publishing, while keeping visual/engine acceptance separate. Keep XWear export behavior separate and regression-tested.

### G. Situation thumbnails

Expose the current model geometry used for framing as a read-only measurement. `vroid_measure` returns renderer count, XYZ bounds, horizontal center, vertical span and optional humanoid Head and LeftFoot world Y in addition to a nominal height. Preserve the target's existing native `get_height` contract. Report renderer extent as maxY-minY and distinguish it from the source's ground-dependent maxY*100 calculation. Only use owned current-model renderers and, if available, the current model's proven humanoid landmarks; report absent or ambiguous landmarks as unavailable. A capture is not required to measure.

Sync all catalog pages and custom revisions; optionally cache validated native icons. Build source-style on-mannequin thumbnails in an owned disposable copy only, rejecting attached sessions before mutation. Require an explicit disposable-model acknowledgement. Save a unique restoration snapshot before edits and restore via that saved model in finally when native state is safe; return the resulting fresh token and restoration state, never promise original undo history or file association.

Strip removable clothes/accessories/underwear and hair except the tested/required slots; apply one tested item, verify active groups, capture using the configured framing, and record retained/removed slots, orientation, tested resource/revision, image size/hash, source build and capture time. Do not label a partially stripped character as a neutral mannequin. Failed/uncertain rows retain evidence and are not published as successful. Native icons remain a distinct fallback and cannot be relabeled as situation captures.

### H. Session operations, batch and help

Add guarded return-to-main-menu and graceful native exit. Refuse unsaved discard without explicit acknowledgement. Menu returns after edit root is inactive and invalidates old tokens. Exit is copy-owned by default; explicitly targeting an attached real window requires an additional close-attached acknowledgement. Never kill an unrelated process or silently restart after an explicit exit.

Returning to the model menu must leave a usable same-session path to create either template or open an allowed existing `.vroid`. When no model is open, use a freshly verified menu/session identity instead of accepting a missing token as permission to replace a model. Confirm the active menu again immediately before dispatch; retain copy/attached path, acknowledgement and fresh-model identity guards. Preserve existing guarded replacement and save APIs. Status should expose the file association, dirty flag, model type/editing and undo/redo availability in both modes when observed; distinguish unavailable from false, and path presence from authorization for in-place saving. Undo/redo should refuse a step with no native history before dispatch and accurately report any completed prefix while preserving existing successful readback.

Add run_batch(operations, stop_on_error=true, include_images=true), with 1..200 ordered calls. Reuse the same published tool argument validation, handlers, session serialization and attached receipts. Reject nested batches and lifecycle transitions that invalidate batch/session ownership. Prevalidate the entire shape and tool names; still validate live model IDs per operation. Report requested/executed/failed/stopped_at and explicit nontransactional partial results. Continue mode applies to ordinary validation/operation failures, never uncertain/dead state. Bound image output to 8 images and 16 MiB and do not duplicate base64 in text. One batch owns the session gate without deadlocking nested ready wrappers.

Add callable topic help and MCP resource documents describing actual target capabilities and the migration mapping, with English identifiers and useful Chinese guidance. Offline help does not start VRoid. Reuse generated tool schemas rather than hand-maintaining another divergent tool registry.

## Verification and delivery

Run baseline tests before behavior changes. Each task uses meaningful failing tests then implementation and focused regression; review each task and the whole branch. Tests must execute algorithms/state machines with native doubles rather than only checking source strings. Regenerate tool docs, expected schema and source manifests after all contract changes. Exercise a real stdio initialize/tools/list/help/offline-cache round trip without launching VRoid. Run Python regressions, JS syntax and behavior tests, schema/source checks, diff checks and UTF-8/CRLF/mojibake checks.

Provide a reusable native acceptance entry/checklist for every migrated native domain on an allowlisted disposable installation. Detect the current unsupported build and report native acceptance unavailable; do not falsify success by mocking the binary, deleting checks, or silently extending support. This delivery can establish code migration and offline contracts; live binary/visual acceptance remains explicitly unproven unless a supported lab is actually available and used.

Deliver local commits on the feature branch and, when network/auth permits, a pushed feature branch and draft PR to BunnyBlack. Do not merge into main without authorization. Final report names the commits/PR, implemented capability groups, tests and native limitations. Root Agents.md documents final directory/workflow facts; CLAUDE.md contains exactly @Agents.md plus a newline. dev remains available for future independent VRoid projects.
