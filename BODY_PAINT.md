# Body paint, freckles, moles and toenails

These tools extend the existing mask and new-layer path. They do not replace
`export_makeup_region_mask` / `paint_makeup_marks` (cheek, mouth line, eyelid,
eyebrow, under-eye) or `export_nail_uv_map` (ten fingernails on the Hand mesh).

Nothing here was executed against a live VRoid Studio process in this change.
Offline tests cover clipping, alpha, seeds, placement and stale rejection.

## What already existed

- `list_texture_regions` / `inspect_texture_renderers` can see `BodySkin` and the
  Foot renderer, but they do not paint.
- `pick_texture_uv` can sample Face, Body, Hand or Foot. The hit is a coordinate,
  not a paint.
- Face makeup masks refuse `BodySkin`, `Mouth` (oral cavity) and whole `FaceSkin`
  except `area='under_eye'`.
- `export_nail_uv_map` requires `J_Bip_[LR]_(Thumb|Index|Middle|Ring|Little)3`
  on the Hand mesh. It is not a toenail tool.

## New flow

1. Open the BodySkin canvas with `open_texture_editor`.
2. `export_body_paint_mask`. The mask is that image's UV triangles. `shared_uv_pixels`
   counts pixels used by surfaces more than 2 cm apart. Those sides are not
   independent; `mirror_x` only mirrors the canvas.
3. Preview, then paint, with the same arguments:
   - `preview_body_marks` / `paint_body_marks` for strokes and stamps.
   - `preview_body_decal` / `paint_body_decal` for one PNG already in lab `saves/`.
     `scale` is the source width divided by the shorter canvas side. `rotation_deg`
     is clockwise about `center` in top-left canvas space. Source alpha is copied.
     An opaque pixel outside the mask is rejected. The source file is not rewritten.
   - `preview_freckles` / `paint_freckles` on a Cheek or BodySkin mask. `seed`
     repeats the placement. Eye, lip and lash masks are refused.
   - `preview_moles` / `paint_moles` on Cheek, under-eye FaceSkin, or BodySkin.
4. Each paint imports one new native layer. Undo `history_command_count`. The
   model is not saved.

## Toenails

`inspect_toenail_targets` reads the Foot renderer. It accepts only connected
components weighted exclusively to `J_Bip_[LR]_Toe0`..`Toe4` or, failing that,
one opposed cap pair on `J_Bip_[LR]_ToeBase`. The ToeBase result is one target
per foot (`L_toes` / `R_toes`) and `individual_toes_separable` is false.

If no such cap exists, the tool returns `separable: false` and a reason. It does
not invent UV boxes or call `export_nail_uv_map`.

When `separable` is true, open the canvas whose image matches the reported foot
texture size and call `preview_toenail_color` / `paint_toenail_color` with the
map id. Color is written only on those caps.

## Local acceptance

Use a new output directory and a disposable lab. This was not run here.

```powershell
python tools/check_native_domains.py --lab <prepared-lab> --json <new>/domains.json
```

Then, on F00 and again on M00:

1. `export_body_paint_mask` on BodySkin. Record `shared_uv_pixels`.
2. Preview and paint a small mark and a decal. Undo once per import. `save_as`,
   reopen, and confirm the new layer is still the only added pixels.
3. `preview_freckles` twice with the same seed and compare `png_sha256`.
4. `inspect_toenail_targets`. If `separable` is false, stop and keep the reason.
   Do not paint the foot from the hand nail map. If it is true, paint one target,
   undo, save, and cold-reopen.

Version allowlists and attached-session guards are unchanged.
