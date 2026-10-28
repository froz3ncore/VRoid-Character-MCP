# Changelog

## Unreleased — existing sessions, model parts and ordinary VRM export

- Optional attachment to an already-open supported VRoid process; detach leaves
  it running and reports background-setting restoration. Copy ownership, real
  user profiles, known native transition limits and unsaved edits are explicit.
- Ordinary editing exports VRM 0.x or 1.0 with existing native permissions and
  optional output title/author; new filenames are staged and checked. Active
  transferable parts can be listed and catalog-verified built-in parts replaced.
  Custom-item save verifies new files, ZIP integrity, root metadata and native
  closet registration in isolated copies; attached sessions remain refused.
  Registered custom IDs are listed with parts and use native closet selection.
- Extended the profile guard and default native-call interception based on the
  later MIT-licensed Karylcode upstream; see LICENSE notices and ATTACHED_SESSION.md.
  Process-local guards remain narrower than an OS sandbox.
- Empty and stale model tokens are rejected before screenshot preparation.
- Six new tools extend the 86-tool baseline to 92; the contract change is intentional.

## Unreleased — reproducibility and recovery

- Verified follow-up: 502 Python tests passed / 1 skipped on Python 3.10 and
  3.12; six JS suites; unchanged 86-tool input contract. A new public sample
  completed in 79.1 s. The 10-case height/proportion/Tops matrix completed in
  793.5 s with live height, scale, authored proportions and makeup preserved;
  independent VRM findings empty. All 30 saved/cold rendered views matched
  exact RGBA. Human golden-image approval and two independent users remain pending.
- Python 3.12 CI fix: exception-group regression uses the built-in type on
  Python 3.11+ and the existing transport backport on Python 3.10, preserving
  the nested-error assertion without adding an unnecessary runtime dependency.
- Optional F00 proportion matrix adds two shoulder/torso/leg/waist profiles with
  both native Tops (10 total cases), including cold parameter-persistence checks.
- Conservative texture-to-Dress-up boundary: confirmed texture entry blocks
  later `open_wear_project` in that process. Saving/reads remain available;
  the public sample and matrix verify saved textures and perform assembly in
  separate processes. The intermittent native crash root cause remains open.
- Corrected the earlier ~1.4 cm "save/reopen height drift" diagnosis: the old
  E2E calibrated before changing hair, then compared different styled models.
  Controlled measurements show the change before save and unchanged live height
  and body scale after cold reopen. Historical reports below retain their original
  numbers; their persistence interpretation is superseded by this correction.
- Height solver now uses live `GetBodyHeight` rather than cached `BodyHeightValue`.
  E2E applies hair before calibration, compares pre-save/post-save/cold live height
  within 0.05 cm and scale within 1e-6, replacing the misleading 2 cm allowance.
  Added a reproducible four-case native order/persistence diagnostic.
- Standard-library installation doctor with bounded async/import probes, exact
  build checks and non-rewriting lock inspection. Diagnostic mode never clears
  registry keys, even when the runtime auto-clear environment variable is set.
- Public sample with original generated badge geometry, retained Blender source,
  PNG cold-reopen checks, native views and VRM export; no private outfit inputs.
- E2E temporary files now belong to the lab, for both parent and child processes.
- Confirmed body edits now block known-dangerous texture-editor entry until a
  cold reopen; saving and reading remain available. This is a conservative
  workaround for VRoid's native overlay cache.
- Fixed parameter adapter regressions found by real multi-view capture: a local
  colour model shadowed the model accessor, and batch colour validation received
  the wrong entry shape. Added a composed adapter regression.
- Regional render comparison with PNG integrity, camera/GPU compatibility gates,
  whole-image and named rectangle metrics, difference images and portable HTML.
- Bounded F00 height/top integration matrix and Windows offline CI workflow.
  External-user acceptance and human golden-image approval remain pending.
- Native follow-up: three corrected height targets retained live measurements
  and scale across cold reopen. An additional same-process texture-check to
  Dress-up transition crashed in native code and remains unresolved; a fresh
  process opened the same saved model and completed assembly/save/VRM parsing.
  The failed same-process run is not counted as a complete E2E pass.

The MCP input contract remains 86 tools; hairstyle-dependent height measurement, limited M00 and
hair-colour coverage, paused skirt collision and engine-validation limits remain.

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

## 0.4.1 development — local validation, publication pending

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
