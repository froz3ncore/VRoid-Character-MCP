# mcjo79 Capability Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the useful behavior of all 53 mcjo79 tools into the BunnyBlack Python/Frida fork, with explicit mappings, tests, provenance and workspace instructions.

**Architecture:** Keep FastMCP, per-domain runtime modules and the IL2CPP main-thread bridge. Add domain modules for actual missing capabilities, preserve existing public tools and copy/attached guards, and reuse one session gate for composite operations. A persistent catalog is host-side and works offline; native mutations retain exact IDs and completion readbacks.

**Tech Stack:** Python >=3.10, mcp==1.30.0, frida==17.16.0, JavaScript, pytest, Node; Windows PowerShell for orchestration only.

**Spec:** `docs/superpowers/specs/2026-11-06-mcjo79-migration-design.md`.

## Global Constraints

- The design is binding. Preserve supported-build checks, model identity, session serialization, native undo/history semantics, no-overwrite publication and copy/attached ownership. Unknown or uncertain native work must not be retried automatically.
- Source revision is mcjo79/vroid-mcp `0dc7d5eb3cf27f7f943713960cac1b65f479a876`; base target is `b02b108ab4a8b4333ecf206a199a7a0403aa7ffe`. Record adapted source files and MIT notices.
- Use feature branch `feat/mcjo79-capability-migration` in the explicitly requested fresh `tools/VRoid-Character-MCP` checkout. Preserve main. Commit per task; review before proceeding. No merge or installed-app changes.
- Temporary files, environments, caches, logs, review artifacts and pytest data stay under the relevant project's temp directory. No temporary file on C:.
- Authored/modified text is UTF-8 without BOM and CRLF. Preserve byte-pinned inherited data; do not mass-rewrite untouched sources. Check encoding and question-mark loss before delivery.
- Keep existing contracts backward compatible. New tool names need not copy the `vroid_` prefix. Similar primitives and mock tests do not establish native feature equivalence.
- Native readiness must come from actual state/completion polling with bounded deadlines; fixed sleeps alone do not establish completion. Validate arguments before side effects.
- Do not start or attach to the installed unsupported Steam build. Its assembly is `3334b166e298682eeda1ca1c5ca568b12f7085b76cc629668fe8b192af816bd8`. Native acceptance remains explicitly unverified until a supported disposable lab exists.

## Review Focus

- Composite calls must not reacquire their own non-reentrant session gate or allow a second task to interleave; covered by Tasks 8 and 9.
- A timeout or exception after native dispatch may still mutate later; retained handles, uncertainty barriers and cleanup ordering are covered by Tasks 2, 4, 5 and 9.
- Catalog refresh, failed custom scans and concurrent writers must preserve annotations and evidence; covered by Tasks 7 and 8.
- Exact IDs, different parameter units, stale topology and shared material/paired controls must never become guessed writes; covered by Tasks 3, 4 and 5.
- Rectangular render budgets, untrusted PNG/ZIP inputs, paths, reused settings and partial file output need behavioral boundary tests; covered by Tasks 2, 3, 4, 6 and 7.

## Execution environment and evidence

Repository: `E:/Repo/VRoidRepo/tools/VRoid-Character-MCP`. Source: `E:/Repo/VRoidRepo/temp/mcjo79-vroid-mcp`. Python: `E:/Repo/VRoidRepo/temp/venv/Scripts/python.exe`. Logs/runner: `E:/Repo/VRoidRepo/temp/run_logged.py`. Task workspace: `temp/sdd/2026-11-06-mcjo79-migration/` in the target repo, with `progress.md`, task briefs/reports and unique review packages. This location deliberately overrides the skill's `.superpowers` scratch default to satisfy the user.

A minimal `asyncio.run(asyncio.sleep(0))` hangs in the Windows sandbox and immediately succeeds outside it. Python async tests therefore run with justified sandbox escalation, with all TEMP/TMP/TMPDIR and output paths still inside this project's temp. The first unsandboxed baseline was 564 passed / 1 failed (`test_e2e_parent_and_child_share_lab_scoped_temp_even_after_host_temp_was_cached`): configure_scratch changes TEMP/TMP but not inherited TMPDIR. Preserve that log; fix in Task 1. No production behavior has changed yet.

Focused test command convention: `<python> <workspace>/temp/run_logged.py task-N-<stage>.log <python> -m pytest <named tests> -q -p no:cacheprovider --basetemp=<workspace>/temp/task-N-<stage>`. JS: `node tests/<name>_test.js`. Use unique test folders per stage and do not overwrite earlier evidence.

---

### Task 1: Reproducible baseline and migration provenance

**Files:** Modify `tools/e2e_clean_lab.py`, `tests/test_public_sample.py`, `.gitignore`, `NOTICE`, `LICENSING.md`; create `licenses/mcjo79-0dc7d5e.txt` and `MIGRATION.md`.

**Interfaces:** Retain `configure_scratch(lab) -> Path`, including its current returned subdirectory. MIGRATION.md contains 53 source-tool rows, domain ownership, planned target mapping and verification state, plus dispositions for brainrom/Karylcode/nhodges. Later tasks update their rows.

- [ ] Strengthen the existing failing scratch test to explicitly set TMPDIR and a cached tempfile.tempdir. Verify the failure before implementation; assert all three environment variables and parent/child `tempfile.gettempdir()` equal the returned project path.
- [ ] Fix configure_scratch to consistently set TEMP, TMP and TMPDIR and reset Python's cached directory without writing outside the supplied lab. Audit other check entrypoints for the same concrete inherited-variable failure and fix only relevant instances with coverage.
- [ ] Preserve the source MIT license by file-level copy and add provenance covering the source revision/files. Create the full migration matrix using the two read-only audits in workspace temp. Keep intentionally stronger target safeguards explicit; do not mark future implementation complete.
- [ ] Run the focused test and full Python baseline, then existing JS behavior tests and current tool manifest. Record exact totals; a source manifest may legitimately drift because these source changes are new and will be regenerated in Task 10.
- [ ] Verify UTF-8/CRLF for changed files and commit `fix: make migration test scratch deterministic` with provenance/docs included as appropriate separate documentation commit.

### Task 2: Native export options and reliable ordinary VRM completion

**Files:** Modify `vroid_mcp/tools_ordinary.py`, `vroid_mcp/runtime_ordinary.py`, `vroid_mcp/vrm_export.py`, `agent/ordinary_extensions.js`, `agent/operations.js`, `vroid_mcp/bridge.py` if needed; add focused export options/runtime tests and JS behavior test. A new `agent/vrm_export.js` / Python export-options module is allowed for cohesion, with explicit bridge module ordering.

**Interfaces:** Extend `export_vrm(expected_model, filename, version=1, title=None, author=None, model_version=None, options=None, leave=None)`. `options` is a strict validated optional object containing the 12 names in Spec F. Add `get_vrm_export_options(expected_model, leave=True)`. Return effective settings, requested values, warnings and existing artifact fields. No-options calls preserve previous behavior.

- [ ] Add failing tests for integer slider boundaries 0/100; reject bool, fraction, -1/101, unknown keys, invalid choice indices and metadata before native mutation. Add orchestration tests for stale model, exact application/reopen/readback order, one retry maximum, explicit leave true/false and default ownership behavior.
- [ ] Implement settings discovery/application from source VrmExport.cs. Preserve native metadata/permission construction. Wait for actual preview state, including PreviewAvatar, update blockers and queued preview work, through consecutive idle samples.
- [ ] Use signature-derived native TaskCompletionSource<bool> with OnVRM1SettingChanged/OnVRMSettingChanged and retained objects. Tests must cover false/fault/cancel, start exceptions after possible dispatch, timeout, stable file, and no navigation/release/retry while outcome is uncertain.
- [ ] Validate complete GLB chunks and embedded resource references for both VRM versions before publication; keep version-specific metadata checks and XWear validation compatible. Test malformed later chunks, version mismatch, missing/external buffers or images and out-of-range indices.
- [ ] Add JS behavioral tests that execute settings setters/readbacks and task state transitions, not only source-text assertions. Run focused Python/JS and existing ordinary/XWear export regressions. Update matrix and commit `feat: migrate native VRM export settings`.

### Task 3: Exact group discovery, parts, presets and silhouette sizing

**Files:** Create `vroid_mcp/tools_groups.py`, `agent/groups.js` and focused tests; extend `runtime_edit.py` or new `runtime_groups.py`, `runtime.py`, `server.py`, `bridge.py`, `operations.js` as needed. Extend `tools_parameters.py` preset options without breaking prior signatures.

**Interfaces:** Add `list_groups(expected_model)`, `list_group_parameters(expected_model, group_id, kind=None)`, `set_group_parameters(expected_model, group_id, changes)`, `list_sections(expected_model)`, `list_categories(expected_model, section=None)`, `enter_category(expected_model, section, category)`, `remove_items(expected_model, group)`, `apply_custom_item(expected_model, filename)` and `set_body_size(expected_model, height_cm, weight_kg=None, variant='F00')`. Public changes carry exact binding ID, typed value and native units. Existing catalog keys resolve to validated file/resource through later catalog wrappers.

- [ ] Add failing tests for exact and ambiguous bindings, paired controls, bool/float/color validation, nonexistent/stale groups, mandatory/nonremovable groups and per-group partial failures. Confirm no writes before all changes validate.
- [ ] Implement real native group/query/command adapters from source VRoidApi.cs. Return raw/native and target binding IDs with units, never guessed fuzzy writes. Reuse existing typed controls where truly equivalent; expose uncovered raw blendshape/bone/color/item keys explicitly.
- [ ] Extend preset listing for search and locked metadata while preserving owned-only defaults and refusing locked application. Add preserve_material as an explicit optional application mode with compatible material/color snapshot, actual restoration readback and partial/incompatible results.
- [ ] Validate project-scoped `.vroidcustomitem` ZIP metadata and format/type before native application; reject traversal, malformed archive, stale resource and incompatible revision. Add generic group removal using the exact native command and verify remaining groups.
- [ ] Implement silhouette FigureHeight/FigureSlender solver separately from set_height. Use explicit variant, native bounds and measured height feedback. Optional weight maps to the documented source BMI/waist heuristic; return `weight_is_heuristic` and actual written/read-back controls. Test invalid inputs, nonconvergence and failed restoration.
- [ ] Run focused tests plus existing parameter/preset/custom-item regressions and JS group behavior. Update matrix and commit `feat: migrate group and preset editing workflows`.

### Task 4: Clothing/hair texture editing, raster replacement and recolor

**Files:** Extend `vroid_mcp/texture_tools.py`, `agent/textures.js` or focused texture module, `agent/parameters.js` material discovery as needed; add pure pixel helper and runtime/JS tests. Register through existing domains; no new transport.

**Interfaces:** Add `begin_clothing_edit(expected_model, group_id)`, `begin_hair_edit(expected_model, material_id)`, `replace_texture_layer(expected_model, region_id, image_id, layer_id, filename, expected_png_sha256, expected_layer_sha256)`, `recolor_texture_layer(expected_model, region_id, image_id, layer_id, color, mode='multiply', strength=1, expected_layer_sha256=...)`, `set_hair_material_color(expected_model, material_id, key, color)` and `colorize(expected_model, target, color, ...filters)`. Use existing layer identity/state contracts, adding required expected state where current APIs demand it.

- [ ] Write failing pixel tests using nonuniform RGBA fixtures: alpha stays byte-identical; strength=0 leaves bytes/pixels unchanged; multiply and luminance-colorize have independently calculated expected values. Reject invalid color, strength, PNG/hash/dimensions before native writes.
- [ ] Implement actual clothing and shared hair-material conversion/entry using source native APIs; wait for callback readiness and verify fresh canvas/image identity. Extend allowed entry types by exact route, not by removing the cosmetics guard wholesale.
- [ ] Replace existing raster data using native history while preserving layer name/state/order. Test stale layer/canvas, wrong image, changed source hash, imported image mismatch, partial native completion and Undo/Redo command sequence with behavioral doubles.
- [ ] Expose shared hair material channels/base overlays and worn garment colors via precise bindings. Compose global/material and raster colorize with filters and per-target results; stop immediately on uncertainty and mark partial work without synthetic rollback claims.
- [ ] Run pixel/runtime/JS tests and existing layer/makeup/callback tests. Update matrix and commit `feat: migrate native texture recolor and replacement`.

### Task 5: Brush group transforms and procedural hair parity

**Files:** Extend `tools_hair.py`, add focused `agent/hair_groups.js` and tests, update bridge/operations registration as required. Reuse existing strand/guide and typed parameter APIs.

**Interfaces:** Add `list_hair_groups(expected_model, category=None)`, `set_procedural_hair(expected_model, category, scope, length=None, hair_count=None)`, `scale_brush_hair(expected_model, category, scope, factor)`, `clone_brush_hair(expected_model, category, scope, offset)`; list returns exact category/scope, type, strand count and measured length. Offsets are finite XYZ metres; factor must be finite and 0<factor<=10.

- [ ] Add behavioral tests proving each strand root is unchanged, all remaining points scale about its own root, normal/UV/material data is preserved and invalid input performs zero commands. Cover multiple strands and non-origin roots.
- [ ] Implement group clone with native CloneBrushHairGroupCommand, detect the new group ID, offset all points and return exact new IDs. Test no clone/ambiguous clone, partial point-command failure and identity invalidation; do not substitute duplicate_hair_strand.
- [ ] Enumerate/validate true procedural Length/HairCount bindings, use actual native ranges and read back after settling. Add aggregate stats from actual geometry, not a naming heuristic.
- [ ] Run focused Python/JS plus existing hair tests; update matrix and commit `feat: migrate brush group and procedural hair operations`.

### Task 6: Editor camera, temporary facial preview and rectangular capture

**Files:** Extend `tools_capture.py`, `runtime_capture.py`, `capture_quality.py`, `agent/capture_quality.js`, capture operations; add `agent/editor_preview.js`, Python surface and focused behavior tests.

**Interfaces:** Add `editor_camera(expected_model, action, ...typed action arguments)`, `face_preview(expected_model, name=None, weight=100, filter=None)` with explicit reset, and extend screenshot with optional paired width/height, msaa, ssaa and clean=True while preserving size/view/quality defaults. Expose effective capture plan/provenance through a metadata-returning companion or existing review result; image-returning callers remain compatible.

- [ ] Test camera get/angles/rotate/zoom/pan/reset/mode/projection/custom against native doubles with exact readback, finite/bounded arguments and invalid-action rejection before side effects. Preserve photo-camera behavior.
- [ ] Implement raw facial blendshape list/filter/weight/reset without changing saved expression data. Test multiple matching shapes, exact vs suffix ambiguity policy, reset, stale preview renderer and no saved model command.
- [ ] Test 640x1024 and 1024x640 capture plans, side bounds 256..2048 and internal pixel cap 8,000,000 including SSAA. Reject partial dimensions, unsupported MSAA/SSAA and invalid numbers. Verify effective downgrade metadata when GPU cannot supply requested MSAA.
- [ ] Implement rectangular native clean render and native Unity application-frame capture for clean=False with no desktop input/focus. Restore temporary cameras/render targets/UI visibility in all failure paths and distinguish provenance.
- [ ] Run capture math/runtime/JS and existing screenshot/regional/quality tests; update matrix and commit `feat: migrate editor camera and capture controls`.

### Task 7: Offline catalog, native synchronization and category framing

**Files:** Add `vroid_mcp/preset_catalog.py`, `tools_catalog.py`, `catalog_framing.py`, catalog/runtime tests and defaults; extend preset/native preview/custom metadata enumeration as needed. Register offline tools without the app-start wrapper and online sync with ready_tool.

**Interfaces:** `PresetCatalog(root)` stores `catalog.json` and validated image metadata. Add `search_preset_cache(query='', category=None, kind=None, annotated_only=False, include_locked=False, status=None, include_removed=False, limit=50)`, `annotate_preset_cache(key, author, label=None, description=None, tags=None, colors=None, replace=False)`, `sync_preset_cache(expected_model, icons=False, icon_limit=None)`, `preset_thumbnail(key)`, `get_preset_framing(category=None)`, `set_preset_framing(category, ...fields)`, `reset_preset_framing(category=None)`. Default persistent root is lab/preset_cache; scratch is lab/temp.

- [ ] Test scans with stable resources/new model tokens, new/changed/removed/returned custom revisions, manual label priority, append/replace tags/colors and retained annotation history. A failed/incomplete custom scan must preserve custom records as unknown, not removed.
- [ ] Test all-word search and combined filters/limits, invalid categories/inputs, duplicate IDs/resources, corrupted catalog, concurrent writes and lock timeout. Atomic failure must leave prior bytes intact; no stale lock auto-deletion or catalog truncation.
- [ ] Implement native sync across every pagination page/category and current-format custom items. Retain source build/session and fingerprints. Icon fetching must validate PNG identity/size/path and keep native-icon provenance. Offline search/annotate/thumbnail/help tests must prove Runtime.start is never called.
- [ ] Implement framing defaults/overrides with exact validation from Spec A, fallback resolution and reset-one/reset-all. Test defaults immutable and resolved settings persist across a fresh store instance.
- [ ] Run focused tests plus existing preset preview tests; update matrix and commit `feat: add persistent preset catalog and framing`.

### Task 8: Isolated situation thumbnail production

**Files:** Add focused gallery orchestration in `runtime_catalog.py` or separate module, extend tools_catalog and native capture framing only as needed; add orchestration/failure tests.

**Interfaces:** `build_preset_thumbnails(expected_model, category, disposable_model=False, refresh=False, limit=None)` returns processed rows, errors, restore state and fresh model token. It consumes Tasks 3, 5, 6 and 7, never calls public ready wrappers recursively.

- [ ] Test attached mode and missing disposable_model acknowledgement reject before snapshot/mutation. Test required save snapshot, selected-slot-only verification, framing consumption and exact image provenance. A native icon cannot satisfy a situation-image test.
- [ ] Implement owned-copy snapshot, stripping actual removable clothes/accessories/underwear/hair except required/tested slots, apply preset/custom resource, verify active groups, capture configured category orientation/crop/fit and store bytes/hash with tested revision.
- [ ] Restore the saved model on normal/failure paths when native state is known safe; report new identity and no promise to preserve undo/file association. On uncertainty do not issue further mutations. Test snapshot failure, strip failure, wrong remaining slots, image failure, restore failure and model change mid-loop.
- [ ] Honor refresh/limit and publish successful rows atomically only with verified capture; preserve incomplete evidence without labeling neutral mannequin. Test whole workflow holds session exclusivity without runtime-lock recursion.
- [ ] Run focused gallery/catalog/native-double tests; update matrix and commit `feat: build isolated preset situation thumbnails`.

### Task 9: Guarded menu/exit, heterogeneous batch and callable help

**Files:** Add `vroid_mcp/batch.py`, `tools_help.py`/help resources, lifecycle methods in existing runtime and native operations, refactor `server.py` session-gate ownership without changing existing tools; add lifecycle/batch/protocol tests.

**Interfaces:** `return_to_main_menu(expected_model, discard_unsaved=False)`, `exit_vroid(expected_model, discard_unsaved=False, close_attached=False)`, `run_batch(operations, stop_on_error=True, include_images=True)`, `get_help(topic='overview', language='en')` and MCP resource help topics. Batch operations are `{tool: str, args: dict}` and use actual published schemas/handlers.

- [ ] Test menu/exit dirty refusal, explicit discard, attached close acknowledgement, native graceful quit (no process kill), response/completion ordering and stale-token invalidation. Explicit exit must leave the server in a stopped state until an explicit new-session action, not auto-launch on the next read.
- [ ] Test 1..200 batch boundaries, unknown tool/non-object args/nested batch, schema validation, lifecycle exclusions, stop/continue, partial result fields and immediate stop on uncertain/dead runtime. Prevalidation of all tool names/shapes precedes mutation; live identity is checked at each call.
- [ ] Introduce task-owned gate borrowing for composed calls; a child asyncio task must not inherit ownership to bypass the lock. Exercise interleaving with a concurrent client and existing attached receipts. No recursive ready-tool deadlock, and no alternate validation/write path.
- [ ] Normalize batch images as MCP content with at most 8 images / 16 MiB and no base64 duplication in result text. Test errors returned as data and as exceptions, omitted images and exact executed/failed/stopped_at counts.
- [ ] Add topic help/resources derived from actual current tool schemas, target usage and migration map. Include useful Chinese guidance and explicit language fallback; offline calls must not launch the app. Preserve existing initialize/tools/list contract.
- [ ] Run focused tests and existing server/attached/history tests. Update matrix and commit `feat: add guarded session workflows and batch tools`.

### Task 10: Integrated verification, documentation and delivery

**Files:** Update `README.md`, `README.zh-CN.md`, `CHANGELOG.md`, `REGRESSION.md`, `MIGRATION.md`, `tools/TOOLS.md`, `tools/expected-tools.json`, `pipeline/source-manifest.json`, documentation generators only where needed for CRLF; add native migration acceptance checklist under docs/superpowers. Update workspace root Agents.md; keep CLAUDE.md exact.

**Interfaces:** All 53 source tools have a final, evidence-backed disposition; new schemas/docs/manifest agree. Native acceptance is a separate explicit gate, with read-only preflight identifying the actual unsupported installed assembly.

- [ ] Audit every matrix row against implementation and focused evidence; fill real omissions rather than changing the spec to match partial work. Document intentional stronger safety semantics, unavailable native verification and any supported source behavior deliberately replaced by an equivalent target flow.
- [ ] Generate tool schema/reference and source manifests with UTF-8/CRLF for authored text. Preserve pinned inherited label bytes and source provenance. Run schema and source checks against final contents, not an earlier commit.
- [ ] Run the full Python suite, every JS behavior regression plus syntax checks, and a real stdio initialize/tools/list/ping/help/offline-cache round trip. Verify no VRoid launch for offline tools. Record logs/JSON under project temp.
- [ ] Write native acceptance checklist with exact setup requirements, per-domain fixtures/actions, failure and timeout cases, output readbacks, Undo/Redo/save/reopen and visual checks. Record current installed hash and unsupported preflight; do not execute native actions on it or report mocked native acceptance.
- [ ] Validate changed text encoding/CRLF, mojibake/replacement characters and suspicious ASCII question loss; run git diff --check. Verify tools/temp/dev layout, origin/upstream, feature branch and root prompts. Remove only task-created disposable build artifacts outside temp after resolving/checking exact paths; keep logs and audits for review.
- [ ] Commit final docs/evidence metadata, obtain whole-branch code review, fix confirmed issues and rerun affected checks. Push the feature branch and create a draft PR when authorized network/auth permits; keep main unmerged. Final completion audit must inspect actual files/tests/Git/PR state and state native limitations precisely.
