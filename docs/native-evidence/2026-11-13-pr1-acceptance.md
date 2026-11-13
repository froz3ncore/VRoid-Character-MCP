# PR #1: partial local native acceptance, 2026-11-13

Reviewed [PR #1](https://github.com/froz3ncore/VRoid-Character-MCP/pull/1)
at `7112e9974c2d604b211288c60b84abc0b41835fd`, against main
`ac777decc76846970d2dd764ec623f0a92b49fd5`. Fixes are on the PR branch.
This is a development snapshot, not a stable release or complete acceptance of
all 145 tools. The PR has not been merged as part of this review.

## Environment and offline evidence

- Windows, Python 3.10.20 and 3.12, Frida 17.16.0, bridge 0.14.0.
- Fresh physical copies of the pixiv-signed standalone builds. 2.16 assembly
  `c8daa116938b40896e3a09208bbde71604a92d5ca6d86f9ff8b89fea3c1a5ad2`, metadata
  `089fe945572695f0592e04abaae096c54f7ea74a382a3ce68440e0425b8486b8`.
  2.14 assembly `ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296`.
  Admission and any metadata pin remain enforced by `supported_builds.py`.
- Steam 2.16 remains outside the Python allowlist. No new build admission,
  global protocol deletion, user-window editing or user-profile adoption.
- Original PR offline result: 1184 passed, 2 skipped on local Python 3.10.
  After the regression additions: **1190 passed, 2 skipped** on both Python
  versions. JavaScript has 43 suites; the final run includes the corrected
  ownership double for independent control-point copies. The original failed
  JavaScript run is retained separately from the subsequent successful run.
- **145 tools**, unchanged input-schema identity:
  `sha256:a20221b7ac83b6a2895d913ae3f5e9def862c4ecf4ad1ffc70c181db52485f94`.
  Provenance remains 26/26 within the recorded rewrite rules. This metric is
  separate from the pinned MIT notices for the newly adapted community code.

Detailed JSON receipts, PNGs, model files and failed runs remain local under the
review evidence directory `work/pr1-20261113/`, with attached fixtures in
`work/pr1-att-f00-v01/` and `work/pr1-att-m00-v01/`. They are not published assets
or additions to the code's MIT grant. `delivery.json` indexes their paths and
hashes. Failed fixtures are retained, including test-input mistakes.

## Defects corrected during native testing

1. **Startup timing.** Calling `Application.version` immediately after
   `il2cpp_init` could access Unity state before it existed (`0x3e0`). Product
   verification now runs on the first queued real-frame dispatch, before any
   read, write or attachment adoption. The identity check remains mandatory.
2. **Hair category addressing.** The real category model has
   `transferableGroupType`, not the assumed `transferableTypes` field. Active
   leaves now resolve through their actual owning group. Empty hair parts use
   the native editor's static transferable-type inventory, with an exact
   category/group check. Fresh empty models and preset-populated models work.
3. **VRM option ABI.** Hair-bone reduction is a property, not the assumed
   public field. Its enum is boxed and temporarily rooted before `ToString`.
   Both option readback and actual VRM0/VRM1 exports were exercised.
4. **Existing raster replacement.** Python PNG decoding yields top-down rows;
   the native tile/flip-enabled PNG path uses bottom-up rows. The content guard
   now compares the same orientation. Layer paths are rooted across large
   pixel allocations, and value-type paths are unboxed for the raw invocation.
   Previously this sequence first falsely reported stale pixels, then exposed
   a null transferable key during command dispatch.
5. **Body sizing.** The native FigureHeight/FigureSlender negative/positive
   roles were reversed in the solver's binding expectation. The solver now
   follows the observed roles and independently verifies the current model
   variant; the presence of editable gender controls alone is insufficient.
6. **Returning to the start screen.** A fresh profile can reach
   `InitialAgreements`, rather than `ModelSelection`. That completed return
   previously timed out and poisoned the session. Status now reports
   `start_screen_mode` and `menu_ready`; no selection token is issued on the
   agreements page. Initial setup is not accepted automatically.
7. **Situation preflight.** The observed mandatory FaceShape, EyeSurrounding
   and FixedPreset slots are retained under the exact native namespace. Unknown
   namespaces still refuse. This lets preflight reach the remaining removal
   capability gate; it does not establish successful thumbnail generation.

Hair commands also copy the complete queried control-point value before changing
it, preserving the query box and opaque fields. A previous combined scale+clone
test exhausted native undo history before reaching the original scale. Immediate
Undo/Redo for each operation now passes; commands are still per point and do not
promise one-step or unlimited history.

## Bounded native results

| Area | Observed result | Evidence directory or file |
| --- | --- | --- |
| Continuous editing, 2.16 F00/M00 | Three cycles across four texture regions after body edits; same-PID Dress-up/XRoid/VRM chain and exact cold pixel/body persistence passed | `continuous-f00-v02`, `continuous-m00-v01` |
| Continuous editing, signed 2.14 F00 | The same three-cycle/four-region chain, XRoid/VRM and cold pixel/body persistence passed on the compatibility build | `continuous-214-f00-final` |
| Attached 2.16, disposable F00/M00 windows | **27 checks each passed**: unsaved adoption, modal/progress/file-picker refusal, repeated body-to-texture entry, exact layer history, host interruption and cross-client recovery, in-place save/cold reopen, XWear import and XRoid reopen | `../pr1-att-f00-v01`, `../pr1-att-m00-v01` |
| Signed 2.14 and 2.16 domain smoke | Face/body, clothing/wear, textures, empty-model hair and independent VRM parsing passed | `native-214-v02.json`, `native-216-final.json` |
| Group parameters | Exact Iris VM binding, visible deformation, Undo/Redo and cold readback passed on both builds | `groups-f00-v01`, `214-groups-f00-v01` |
| VRM options | Hair smoothness/bone options and combine-hair override, metadata overrides, consecutive VRM0/VRM1 exports and subsequent editing passed on both builds; independent structural findings empty | `export-f00-v01`, `214-export-f00-v01` |
| Clothing canvas/template/raster | InnerTop compact IDs, native template addition with existing images preserved, asymmetric RGBA import, replacement, Undo/Redo, recolor with unchanged alpha/other layers, save/cold decoded-pixel equality passed | `clothing-f00-v05` |
| Shared hair material and brush groups | Visible shared-material tint, whole-group scaling and clone/offset readback, immediate native Undo/Redo for each operation and cold geometry/material persistence passed | `hair-m00-v06`; F00 tint/cold evidence also in `hair-f00-v01` |
| Procedural hair | Exact Length/HairCount controls, generated strand count, Undo/Redo and cold persistence passed | `procedural-m00-v01` |
| Body size | F00 target 159 cm: 158.9903 cm; M00 target 171 cm: 170.9510 cm. These fixtures had zero observed live-height delta after cold reopen; 2.14 F00 also passed | `size-f00-v04`, `size-m00-v07`, `214-size-f00-v01` |
| Preview/camera/capture | Actual closed-eye pixels reviewed; reset/restore and camera angle/pan/zoom/projection/reset preserve saved parameters/history. Portrait 640x1024 and application-frame UI pixels reviewed | `camera-f00-v01`, `discovery-v02` |
| Batch | Whole-plan preflight before writes, ordered success, partial failure without rollback, safe continuation and eight-image cap passed | `batch-f00-v01` |
| Catalog/offline | Builtin scan, bounded native icon, local annotation and framing override/reset exercised. Cold annotated search and Chinese help made zero native startup attempts | `catalog-m00-v06` (partial), `offline-f00-v01` |
| Start screen | Return to InitialAgreements completed with no false ModelSelection token | `session-f00-v05` |

The clothing result proves decoded pixels and persistence. Existing outer clothes
can obscure InnerTop, so its screenshots do not prove an exposed recolored
garment. Shared hair tint is not independent per-strand color. Model groups are
not texture-layer folders. Structural VRM parsing is not another consumer's
rendering, motion or physics acceptance. The measured sizing fixtures do not
establish exact persistence for every legacy height/proportion workflow.

## Remaining native acceptance gates

- **Registered custom application:** the saved current-format Iris file was
  observed with complete native IDs/revisions but `registered=false` from
  `CheckIfIsRegisteredInAssetStorage`. `apply_custom_item` refused before native
  application with `CUSTOM_ITEM_REGISTRY_IDENTITY_UNAVAILABLE`. Do not weaken
  this guard or claim that a saved/observed file has already entered asset
  storage. Neither project-copy application nor application by cached key is
  accepted on this fixture. Next reproduce the native registration/category
  route with pinned bytes and exact selectable identity.
- **Situation thumbnails:** one Tops candidate reached the removal gate, but
  default clothing slots had no proven exact native clear capability. It
  returned `SITUATION_FORBIDDEN_SLOT_NOT_REMOVABLE`, published **zero** images,
  and successfully restored its pinned snapshot with `uncertain=false`.
  Successful stripping, candidate publication and its visual framing remain
  unaccepted. Do not bypass mandatory-slot or identity checks to obtain a PNG.
- **ModelSelection create/open and graceful exit:** the fresh profile reached
  the agreements screen, so the native menu-token create/open/exit sequence
  remains unrun with a completed initial setup. Offline identity, stale-token,
  discard and exit-watch fault tests remain separate evidence.
- The attached checks above cover the established editing/recovery fixture.
  Interrupted ordinary VRM export, menu import and registered-custom loading
  introduced by this PR still need their own native cancellation tests.
- No real user profile, long-duration leak campaign, Steam runtime, full option
  matrix, independent VRM consumer or external-user acceptance was performed.

Keep the PR unmerged while deciding and completing these remaining feature gates.
The full procedure remains in the [native acceptance checklist](../superpowers/native-migration-acceptance.md).
