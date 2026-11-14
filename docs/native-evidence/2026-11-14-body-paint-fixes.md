# Body paint fixes, 2026-11-14

The first 2.16 M00 acceptance failed once during new-layer import and once
during Undo (`Transferable () not found`, only two of three history commands
completed). These attempts remain in `work/body-paint-accept-20261114/`.
The saves-directory creation fix already present in the worktree is retained.

## Changes

- Native import keeps the exact image-path owner alive across PNG decoding and
  Color-array allocation, keeps the import command alive through construction
  and dispatch, and unboxes value-type paths when required by the native ABI.
  The inspected 2.14 `EditableImagePath` derives from `Object`: retaining its
  managed owner is essential here; the unboxing branch handles value-type
  paths only. All temporary GC handles are released on success and failure.
- Decals scan their complete rotated projection. Opaque pixels outside the
  canvas are rejected before publication or native writes. Transparent padding
  can extend outside the canvas; source RGBA and the pixel-work limit remain.
- A toenail target needs a unique native editable image with matching cap
  positions, UVs and named skin weights. Texture dimensions alone cannot select
  the destination. Pixels shared with other Foot or editable-canvas surfaces,
  unknown bone identities, atlas remapping and changed bindings are refused.
  Dimensions and correspondence are checked again just before native import.
- Foot map fingerprints include transforms, skin weights and texture geometry
  without depending on transient rendered-texture object IDs. The source
  manifest now includes BODY_PAINT.md and the import regression test.

## Checks

- Python: **1228 passed, 2 skipped** (`unit-final.log`).
- JavaScript: **37 agent files, 44 behavior suites**, all passed.
- MCP: **157 tools**, unchanged input-schema fingerprint
  `sha256:1b915b574b30020415d1ae99ed58b2190b92fc96f19be11025a48a1e30f5d77c`.
- Regression cases execute the actual native import operation with GC-sensitive
  path/command doubles, exercise class/boxed/value-type arguments and cleanup,
  and verify off-canvas/rotated decals, transparent padding, foreign/ambiguous
  image addresses, UV/bone changes, shared pixels and changes before import.

All receipts below are relative to `work/body-paint-fixes-20261114/`, outside
the source package. Tests use new disposable labs and new saves.

| Build / fixture | Receipt | Status |
| --- | --- | --- |
| 2.16 M00, first fix run | `native216-v01.json` | Pass |
| 2.16 F00 and M00, independent repeat | `native216-v02.json` | Pass |
| 2.14 F00 and M00 | `native214-v01.json` | Pass |

Each passed fixture imports a mark and a decal, compares native exported RGBA
with the preview, completes all three Undo and Redo commands for each import,
preserves the base raster and source PNG, saves a new VROID and cold-reopens it
in another process with identical authored-layer pixels. Local verification
also checks the saved file hashes and ZIP CRCs.

## Boundaries

The standard F00/M00 Foot fixtures report `NO_ISOLATED_TOENAIL_CAPS` and do not
paint toenails. Positive direct-mapping and wrong-canvas refusal checks use
offline fixtures; arbitrary custom Foot topology has no native success claim.
Freckles and moles have preview checks here; they are not separate complete
native paint/persistence acceptances. These tests do not certify final rendered
appearance, VRM export, real user profiles or long-running manual sessions.
No existing user model is overwritten, and no stable release is created.
