# Changelog

## 0.5.0.dev0 — 2026-10-28 (development snapshot)

Python package/runtime: `0.5.0.dev0`; npm agent/lockfile: `0.5.0-dev.0`.
The source snapshot exposes **103 tools**. No new stable release or release tag
is created. Local validation and independent external-user acceptance are separate.

### Existing-window editing and recovery

- Added explicit attachment/detachment, ordinary VRM 0.x/1.0 export, native part
  listing/replacement and new custom-item saves, followed by two state-review
  tools: `get_attached_state` and `acknowledge_attached_state`. The 86-tool
  historical baseline grew first to 92, then to 94; the five file-workflow tools
  below brought it to 99. Four raster-layer tools now bring it to 103, preserving
  all earlier 99 input schemas.
- Added `open_character` and `open_current_in_wear`; attached `save_as`,
  `import_xwear`, and new XRoid saving are supported. Character in-place saving
  and new-character replacement were completed with `save_character`,
  `save_character_as` and `new_character`. The new flow exits through the native
  start-screen callback before creating the replacement; early deinitialization
  crashed, and direct initialization skipped the exit lifecycle. Save in place
  verifies a byte-identical backup first. Attached character/XWear/XRoid IO accepts
  explicit absolute paths; copy mode retains lab-only paths.
- Compatible attached windows support texture editing and explicit-discard
  file-based Dress-up entry. Custom items use the target window's native closet
  with file/ZIP/metadata/registration checks, preserving character file association
  and a prior dirty flag. File-based Dress-up entry requires explicit discard;
  `open_current_in_wear` first saves a new character copy and checks for changes.
- Native dialogs, notifications, progress locks, popup blockers and incompatible
  canvas operations refuse writes. A disabled Windows owner reports unavailable
  state before RPC submission; the test-owned file picker opens/cancels correctly.
- A target-process lease restores background state on normal detach and recovers
  a verified dead host on reconnect; another live host is refused. Edit receipts
  survive host exit, including attachment from another client lab. Reads remain
  available; an unchanged reviewed state must be acknowledged before resuming.
  No interrupted operation is replayed or certified by acknowledgment. Background
  restoration requires reconnect/detach after forced exit; receipts do not survive
  VRoid or Windows exit.

### Native raster-layer management

- Added `rename_texture_layer`, `delete_texture_layer`, `reorder_texture_layers`
  and `set_texture_layer_blend`. Matching-canvas checks and native-boundary
  metadata checks guard each edit; deletion/order also require a current image
  stack hash. Complete bottom-to-top permutations preserve other layers and
  reject duplicate, missing or foreign-image IDs. Last-layer deletion is refused.
- `list_texture_layers` now returns per-image order/hash data and the native UI's
  26 composition modes. Native history handles Undo/Redo, same-value changes
  create no command, and source PNG pixels are preserved. See
  [TEXTURE_LAYERS.md](TEXTURE_LAYERS.md) for use and reproduction.
- F00/M00 each passed 11 layer-specific checks through real MCP stdio, including
  actual renderer composition changes and cold-reopened names/order/blend/pixels.
  Group/folder editing is unfinished: native data types and snapshot experiments
  did not establish a usable history command. The four new tools reject grouped
  image roots; experimental group code remains outside the product.

### Continuous editing and reproducibility

- Mapped the reproduced native access violation to PNGUtil's worker writing a
  NativeArray view into Texture2D storage. Empty Mesh Collider warnings also occur
  in successful runs and are not treated as proof of a fatal mesh-cache defect.
- Owned copies use native synchronous PNG decoding on Unity's main thread,
  retain inputs/results and defer original callbacks (four requests per frame).
  Attached windows post native completion closures owned by Unity, with GC-safe
  references, so queued completions survive agent unload. Legacy workers must
  finish before attached transitions; no installation binaries are modified.
- Verified decoders allow same-process body/texture/Dress-up editing; fallback
  guards remain for unverified sessions. Public-sample/matrix process separation
  now verifies persistence independently, rather than indicating an unfixed crash.
- Height calibration uses live measurement after styling. The earlier ~1.4 cm
  comparison mixed pre-hair and post-hair models; saved/cold live height and scale
  are checked separately. Added diagnostics, generated public accessory sample,
  native capture comparison and bounded F00 height/proportion/Tops matrix.
- Unified package metadata, three READMEs, scope/recovery/acceptance descriptions
  and generated tool reference. Reclassified the recovery tools under session
  tools. The tool reference now includes its source version.

### Validation and remaining scope

- Latest code suite: **564 passed / 1 skipped on Python 3.10 and 3.12**, ten JS behavior
  suites, 340-file source manifest, provenance and the 103-tool input hash
  `sha256:3b47ec7ac16f35281107105113d22416f19bf94e5afacfe6bd80f4f379537e5d`.
  Both interpreters were checked for this snapshot; earlier counts remain historical.
- Native evidence dated 2026-10-28: five domains passed; F00/M00 each completed
  20 body-to-texture entries, same-process Dress-up/XRoid/VRM, exact exported
  texture pixels and cold persistence checks. The expanded attached editing/file
  workflow passed 26 checks per variant, including repeated new-character
  replacement, absolute Save As/open, backup-verified in-place saving and cold
  persistence, current-character Dress-up entry, XWear import and XRoid save/reopen.
  The separate F00 lifecycle run passed 18, including normal/forced host exit,
  live-owner refusal and preserved unsaved work. Interrupted-import testing
  verifies queued managed completions after agent unload and cross-client review.
  Earlier 17-check attached runs remain historical records.
- Historical public sample and 10-case F00 matrix passed; all 30 saved/cold views
  matched exact RGBA. A three-view technical baseline was explicitly approved on
  2026-10-20; that is not final character-art adoption or independent acceptance.
- Controlled native fixtures use isolated startup profiles. Real user profiles,
  arbitrary simultaneous manual editing, every native save/overwrite dialog,
  long-running GC stress, full M00 parity and OS-crash recovery are not certified. Global visible hair
  colour is supported; per-strand visible colour is not. Rear-skirt collision
  remains paused/unresolved, and game-engine rendering/physics require separate
  acceptance. Independent external-user testing remains pending.
- Layer-specific and expanded attached runs have their own dated records.
  Documentation-only edits do not imply that all earlier native/sample/matrix
  evidence was rerun for this snapshot.

## Historical versions

The entries below describe their recorded snapshots. Their tool counts, test
counts, licence state and limitations do not describe the current development tree.

## 0.4.1 — 2026-10-20

Independent reimplementation of the tool layer. The published tool contract is
unchanged — still **86 tools** with the same JSON schemas and
`toolset_hash: sha256:69101bb6…` — but no text from the original fork remains.

### Why

The upstream project this repository started from is public without a licence
(`license: null`, no licence file in the baseline commit), so its code could not
be relicensed. Rather than ship unlicensed code, the implementation was
replaced. `tools/check_provenance.py` measures the result: 26 of 26 baseline
paths rewritten, removed or reduced to declarative configuration, nothing above
the 0.10 threshold, and no inherited lines moved into new modules.

### What changed structurally

- `vroid_mcp/server.py` is only the factory, the first-call gate and the two
  session tools; the domains live in `tools_wear`, `tools_parameters`,
  `tools_hair`, `tools_accessories` and `tools_capture`.
- `vroid_mcp/runtime.py` keeps state and delegation; `bridge.py` owns the
  process and Frida protocol, `lab_paths.py` the artifact policy, and
  `runtime_edit`, `runtime_capture`, `runtime_wear` the domain operations.
- `agent/profile_guard.js` and `agent/main_thread.js` replace the previous
  guard and bridge; `agent/operations.js` and `agent/parameters.js` are
  rewritten in place with their factory keys and operation names preserved.
- `LICENSE` is MIT for this repository, `LICENSING.md` describes the
  reimplementation, and `UPSTREAM.json` remains as provenance/acknowledgement.
- Distribution renamed to `vroid-character-mcp`.

### Verified on this tree

445 unit tests pass, 1 skipped; five JavaScript behaviour suites; the read-only
native domain check (face-body, clothing-wear, texture-makeup, hair, VRM); and a
clean-lab run of 133.6 s that saves the model, reopens it in a new process,
imports the v22 outfit, exports a VRM and parses it independently (53 humanoid
bones, 13 expressions, 41 spring chains, 110 joints, 33 colliders, no findings).

### Known limitations (unchanged)

Height still drifts about 1.4 cm across save/reopen; per-strand hair colour
remains invisible and only global hair colour is supported; M00 has no
equivalent coverage; rear-skirt collision stays paused and unresolved.

## Repository independence — 2026-10-19

- Established VRoid Character MCP as a separately maintained project at
  `froz3ncore/VRoid-Character-MCP`, preserving complete source history and the old fork.
- Added MIT licensing for original contributions controlled by froz3ncore.
  Inherited portions remain excluded pending upstream authorization; this is
  not a blanket MIT grant over the combined project. Added LICENSING.md and
  a baseline inventory in UPSTREAM.json; third-party notices remain intact.
- Kept package names, entry points, versions and historical tags unchanged
  for compatibility with existing MCP installations.
- Made the source manifest portable across Git LF/CRLF checkout conversion:
  v2 hashes normalized LF bytes; historical v1 checks keep exact-byte semantics.

## Historical precursor to 0.4.1 — 2026-10-19 (publication then pending)

- Added guarded existing-layer visibility/opacity editing, native history,
  stale-metadata checks and idempotent zero-command updates.
- Added checked recipe CLI replay: exact base/mask/dimension preflight for ALL
  parts before brush writes; preserve original layers, save once, reopen and
  verify native pixels/state. Failed preflight saves nothing; uncertain native
  writes are not retried. No graphical manager or automatic retargeting.
- Fixed independent VRM inspection: full GLB chunk stream, 15 required roles,
  node bounds and duplicate mappings, expression morph and spring references,
  and consistent failing findings. Explicit allow-no options produce warnings
  for avatars that intentionally have no expressions or spring chains.
- The check runner now executes the five JS behavior regressions in addition
  to syntax checks. Native layer edits and recipe replay have separate real
  save/reopen proofs; source models and production v22 assets are preserved.
- Corrected completion claims: the original 0.4.0 milestone omitted two Must
  items, now implemented and verified in this development line.
- Removed the unverified repository-wide MIT declaration. The maintainer
  confirmed upstream permission is not yet established. Third-party licenses
  and notices remain unchanged; independent publication remains pending.
- Original local v0.4.0 tag is unchanged. This is a development version, not
  a new public release or adoption of the candidate character art.

## 0.4.0 — 2026-10-19 (historical local checkpoint)

This checkpoint collected 85 tools, a reproducible check runner and a clean-lab
export run. Subsequent review found it did not close every Must item and the
independent parser's success checks were too broad; see the development fixes above.
Character art (formal v22 assets, shoes, sitting skirt) is not part of this
release; see `SCOPE.md`.

### Acceptance on this baseline

- `tools/run_checks.ps1`: 398 passed / 1 skipped, tool set matches the baseline
  (85 tools, `sha256:128f4106...`), JS syntax clean.
- `tools/e2e_clean_lab.py` in 91.9 s: new lab -> base model -> bounded Cheek
  makeup layer (native history 3 commands, layers 1 -> 2) -> face slider
  0.5 -> height 157.8 cm -> hair preset (38 front nodes) -> save 5.17 MB .vroid
  -> reopen in a new process (face slider 0.5, makeup layer present, 38 nodes)
  -> Dress-up import of `hem-align-v22` -> save 50.36 MB .xroid -> export VRM
  -> independent parse: VRM 1.0, 53 humanoid bones, 13 expressions,
  41 spring chains / 110 joints / 33 colliders, 101 meshes and materials,
  110 images, no findings.

### Added

- **One-command acceptance** — `tools/run_checks.ps1` pins TEMP/TMP, runs the
  unit tests, the 85-tool schema smoke, JavaScript syntax checks and, with
  `-Native`, a read-only per-domain native check. Writes a JSON report and
  returns 0/1. The 139 setup errors seen with a plain `pytest` were an
  unwritable TEMP, not assertion failures: 398 passed / 1 skipped (symlink
  privilege).
- **Tool set identity** — `tools/tool_manifest.py` freezes names, parameters
  and required flags in `tools/expected-tools.json` with a `toolset_hash`;
  `get_status` now returns `tool_count` and `toolset_hash` so a long-lived
  client can see that it cached an older tool list.
- **Native domain smoke** — `tools/check_native_domains.py` exercises
  face-body, clothing-wear, texture-makeup, hair and VRM against one lab
  without writing to the model.
- **Independent VRM parser** — `tools/vrm_inspect.py` reads the GLB container
  and the VRM JSON chunk directly (humanoid bones, expressions, spring chains,
  colliders, meshes, materials, images) so acceptance does not trust the
  exporter's own report.
- **Crash-key guard** — `vroid_mcp/closet_guard.py` checks
  `HKCU\SOFTWARE\Classes\vroid.closet` before the process is spawned and stops
  with `VROID_CLOSET_CRASH_KEY` instead of dying mid-run with an uncertain
  save. It backs the key up to the lab and prints the exact removal command
  when this process may not write the registry.
- **Lab owner identity** — `vroid_mcp/lab_lock.py` records the owning PID in
  the lab lock, clears it on clean release, and names the owner when a second
  server tries the same lab.
- **Tool reference** — `tools/TOOLS.md`, generated by `tools/gen_tool_docs.py`
  from the live schemas (parameters, defaults, annotations, and each tool's
  own description with its preconditions and failure modes).
- **Scope freeze** — `SCOPE.md` records must-do, may-skip and out-of-scope
  items, including the decision rule for per-strand hair colour.

### Changed

- Texture paint, region masks and makeup layers (`agent/textures.js`,
  `vroid_mcp/texture_*.py`, `bounded_paint.py`, `face_regions.py`,
  `makeup_tools.py`) are part of the tool surface; texture tools refuse to run
  while a Dress-up assembly is open.
- Hair authoring: strand control points, duplication, shared material
  assignment and colour elements, plus native API introspection.
- Body occlusion and native shoe visibility are exposed as inspect/set pairs
  that require a fresh identity token and refuse stale masks.
- Native shoe templates are listed and added through `list_shoe_templates` /
  `add_shoe_template` with a before/after active-group check.
- The Blender XWear exporter honours an opt-in `vroid_mcp_shade_color` linear
  RGBA attribute for materials that need an exact VRM shade.
- Version 0.3.2 -> 0.4.0 in `pyproject.toml`, `package.json` and
  `package-lock.json`.
- README points at `SCOPE.md`, `tools/TOOLS.md` and `tools/run_checks.ps1`
  instead of the stale 0.3.2 test count.

### Fixed

- `get_status` used to describe only the model; the tool-set identity is now
  part of the same response.
- A stale `.mcp-owner.lock` containing only a zero sentinel no longer looks
  like a live owner.
- README's "26 unit tests" claim is replaced by the real, reproducible count.

### Known limitations

- Per-strand hair colour is **downgraded to global hair colour**, with evidence:
  writing the five `Level1BaseHair_*` colour channels of a hand-drawn hair group
  reads back exactly but changes **0 of 640x640 pixels**, while the global
  `colors/Hair/All` parameter changes **24.6%** of them. `SCOPE.md` records the
  measurement and `work/spike-hair/` holds both reports.
- Whole-body height does not survive save/reopen exactly: `set_height` reaches
  the target in-session (157.8 cm), the reopened file reads 159.209 cm
  (drift 1.409 cm). The clean-lab run records this drift instead of hiding it;
  a face slider is the exact persistence witness (0.5 -> 0.5).
- Layer visibility/opacity for existing layers and checked makeup-recipe
  replay are the remaining must-do items in `SCOPE.md`; neither is in 0.4.0.
- Rear-skirt collision stays paused and unresolved; it is not silently
  assumed away.
- M00 has not received the coverage F00 has.
- Godot import, materials and physics require separate engine-side validation.

## 0.3.2 and earlier

Historical entries live with the local development reports under `docs/`
(kept out of the repository by request). The last pushed baseline before this
release was `7c72045` (native VRM export and pose-matched 3D wear inspection).
