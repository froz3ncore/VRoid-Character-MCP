# Native raster-layer management

Source: **0.5.0.dev0**, **103 MCP tools**. Four new tools add raster-layer
renaming, deletion, ordering and blend modes. Folder/group editing remains
unfinished; the returned `folder_editing_supported` is `false`.

## Read before editing

1. Obtain a fresh `model_token`, call `list_texture_regions` and open the intended
   region with `open_texture_editor`. Layer management requires that matching
   native canvas in ordinary character editing.
2. Call `list_texture_layers`. Each layer has `layer_id` and `state_sha256`.
   Each `images` entry has `image_id`, `layer_ids` and `stack_sha256`.
   **Order is bottom to top**: the last layer is the uppermost layer.
3. Take blend IDs from `composition_modes`, which enumerates the native UI's
   actual choices and translated labels. Keep the exact IDs, including native
   spelling; do not send an invented numeric mode or translated label.
4. Relist after each edit, import, Undo/Redo or model reopen. Layer hashes guard
   metadata; image stack hashes also guard the complete layer order and membership.
   The native write boundary checks the supplied metadata again, after preflight.

| Tool | Required fresh state | Behavior |
|---|---|---|
| `rename_texture_layer` | `expected_state_sha256` | Changes one layer's name, preserving its PNG and stack position. Name is 1–80 characters, contains text and has no control characters. |
| `delete_texture_layer` | `expected_state_sha256`, `expected_stack_sha256` | Removes one layer through native history; refuses the image's last raster layer. Undo restores its pixels. |
| `reorder_texture_layers` | `image_id`, `expected_stack_sha256`, full `layer_ids` | Sets the complete order of one image, bottom to top. Accepts a permutation of all its current IDs, up to 256 layers; refuses missing, duplicate or foreign-image IDs. |
| `set_texture_layer_blend` | `expected_state_sha256`, `composition_mode` | Changes one layer's native composition mode, preserving its source PNG. |

Every tool also requires `expected_model` and `region_id`. Layer-specific tools
require `layer_id`. A successful change uses one native history command; unchanged
names, order or blend mode return zero commands. Existing visibility and opacity
editing remains available through `set_texture_layer_state`.

These operations do not save. Close the canvas before `save_as`,
`save_character_as` or other screen/file changes. Use the appropriate save
semantics in [ATTACHED_SESSION.md](ATTACHED_SESSION.md). In an attached window,
dialogs block writes and interrupted edits require state review as described in
[RECOVERY.md](RECOVERY.md). A native command or readback failure is uncertain;
inspect the actual layers and files before continuing.

## Grouping boundary

The inspected 2.14.0 binary contains `LayerGroup`, `LayerTree` and group path
types in its data model. Its texture editor exposes raster-layer view models
and the verified rename/delete/order/blend commands. No native create-folder,
move-into-folder or ungroup command was found in those inspected editing APIs.
Data types alone do not establish a working editor lifecycle or Undo/Redo.
Disposable snapshot-command experiments also failed to enter the intended
group mutation path. Their outputs are not grouping acceptance evidence.

Native folder creation, membership, group properties, Undo/Redo and persistence
are **not implemented or accepted**. The four new mutation tools reject an image
whose root contains non-raster nodes, protecting an existing grouped tree from a
flat reorder/delete operation. This is the MCP implementation's current boundary,
not a claim that the entire file format cannot represent groups.

## Reproduce the native checks

Use an exclusive prepared lab and a **new** evidence directory:

```powershell
& .\.venv\Scripts\python.exe .\tools\check_texture_layers.py `
  --lab "D:\VRoid-Character-Lab" --variant F00 `
  --out "D:\VRoid-Layer-Check-F00"
```

Repeat with `--variant M00` and another new evidence directory. The script creates
test layers/files in the lab and drives the real MCP stdio interface. It verifies
native Undo/Redo, unchanged source RGBA, actual renderer texture changes from
order/blend edits, and saved/cold-reopened order, names, blend modes and pixels.

On the validated standalone 2.14.0 build, F00 and M00 each passed **11 checks**
on 2026-10-28. Both exposed all **26 native blend modes** for write/readback;
order and a representative blend change were also checked against the actual
renderer texture. This does not establish all 26 blend equations independently.
Offline regression reports **564 passed / 1 skipped** on Python 3.10 and 3.12,
with **10 JS behavior suites**. Full-model, real-profile and independent-user
acceptance retain the boundaries in [SCOPE.md](SCOPE.md).
