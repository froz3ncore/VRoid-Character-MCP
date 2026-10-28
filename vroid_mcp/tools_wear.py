"""Dress-up (wear) tools: assembly, fitting, preview motion and VRM export.

Everything here works on the synthesized assembly, not on the ordinary edit
model. Callers pass `expected_wear`, a token from `get_wear_status`, and every
write is refused when that token is stale.
"""

from __future__ import annotations

import json
from typing import Literal

from mcp.server.fastmcp.utilities.types import Image
from mcp.types import ImageContent, TextContent, ToolAnnotations
from pydantic import Field, StrictBool, StrictInt


def register(ready_tool, runtime, lab, read, edit):
    """Publish the Dress-up tools on the server that owns `runtime`."""

    destructive = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

    @ready_tool(annotations=read)
    async def get_wear_status() -> dict:
        """Report whether Dress-up is active, plus the wear token, item ids, mesh names, fit values and animation state.

        Take the returned wear_token as expected_wear for every other Dress-up
        call. A model token from ordinary editing does not identify an assembly.
        """
        return await runtime.wear_status()

    @ready_tool(annotations=destructive)
    async def open_wear_project(filename: str, expected_wear: str, discard_unsaved: bool = False) -> dict:
        """Open a .vroid base or .xroid assembly in Dress-up.

        Attached sessions accept absolute input paths; plain filenames and copy
        sessions use this lab's saves/ directory.

        This replaces whatever the disposable copy currently holds, so it requires
        discard_unsaved=true. Returns a new wear token and the native items once
        the load task has finished.
        """
        return await runtime.open_wear_project(filename, expected_wear, discard_unsaved)

    @ready_tool(annotations=destructive)
    async def open_current_in_wear(expected_model: str, expected_wear: str, filename: str,
                                   switch_to_wear: bool = False) -> dict:
        """Save the current character to a new .vroid and open that copy in Dress-up.

        Requires switch_to_wear=true. This changes screens and replaces the
        current edit session after saving; close any active texture canvas first.
        The original associated file is not overwritten. If the transition fails,
        inspect the window and the named saved file before attempting anything else.
        """
        if not switch_to_wear:
            raise ValueError('EXPLICIT_SWITCH_TO_WEAR_REQUIRED')
        current_wear = await runtime.wear_status()
        if current_wear['wear_token'] != expected_wear:
            raise ValueError('STALE_WEAR: call get_wear_status')
        before = await runtime.status()
        if before.get('model_token') != expected_model:
            raise ValueError('STALE_MODEL: list parameters again')
        saved = await runtime.save_as(filename, expected_model)
        try:
            guard = None
            if before.get('mode') == 'attached':
                after = await runtime.status()
                old, new = before['attached_state'], after['attached_state']
                if (after.get('model_token') != expected_model or
                        any(old.get(k) != new.get(k) for k in ('history_revision', 'file_path', 'unsaved'))):
                    raise RuntimeError('CHARACTER_CHANGED_DURING_SNAPSHOT')
                guard = {'expected_model': expected_model, 'expected_history_revision': new['history_revision']}
            opened = await runtime.open_wear_project(filename, expected_wear, True, guard)
        except Exception as error:
            raise RuntimeError('SAVED_COPY_TRANSITION_UNCERTAIN: inspect the window and saved copy at '
                               + saved['path'] + '; do not retry blindly') from error
        return {'saved_character': saved, 'wear': opened}

    @ready_tool(annotations=read)
    async def get_wear_snapshot(expected_wear: str) -> dict:
        """Read the instantiated assembly: item renderers, texture sizes, skin bones and VRM spring components.

        Requires a fresh wear token and a stopped preview. Presence of a component
        says nothing about visual fit or simulated motion.
        """
        return await runtime.wear_snapshot(expected_wear)

    @ready_tool(annotations=read)
    async def inspect_wear_body_occlusion(expected_wear: str) -> dict:
        """Read the native Body active-vertex marks together with their identity hash.

        Indices always address the original default Body mesh, never a compacted
        posed mesh, so capture a matching reference before writing. This is a
        read: it does not decide which anatomy should be hidden.
        """
        return await runtime.inspect_wear_body_occlusion(expected_wear)

    @ready_tool(annotations=edit)
    async def set_wear_body_occlusion(expected_wear: str, expected_occlusion_token: str,
                                      hidden_vertices: list[StrictInt] = Field(max_length=2048)) -> dict:
        """Replace the hidden-vertex marks on the Dress-up copy's Body mesh.

        Needs the token from a fresh inspection, sorted distinct original-mesh
        indices, and stays within 2048 vertices or 20 percent. Pass an empty list
        to restore the default Body. The native mesh history records the change;
        the .vroid source and the garments are untouched. Save/reopen, seams,
        animation and VRM export each need their own check, and a stale token or
        an uncertain write stops the call.
        """
        return await runtime.set_wear_body_occlusion(expected_wear, expected_occlusion_token, hidden_vertices)

    @ready_tool(annotations=read)
    async def inspect_wear_native_shoes(expected_wear: str) -> dict:
        """Find the separate native shoe-only Cloth renderer and read its saved visibility marks.

        Mixed clothing materials are rejected: only a renderer whose materials are
        all native shoes qualifies.
        """
        return await runtime.inspect_wear_native_shoes(expected_wear)

    @ready_tool(annotations=edit)
    async def set_wear_native_shoes_visible(expected_wear: str, expected_visibility_token: str,
                                            visible: StrictBool) -> dict:
        """Show or hide only the native shoe surface through persistent mesh marks.

        Body Foot geometry and the imported XWear stay as they are; save/reopen is
        a separate check.
        """
        return await runtime.set_wear_native_shoes_visible(expected_wear, expected_visibility_token, visible)

    @ready_tool(annotations=edit)
    async def export_wear_vrm(filename: str, expected_wear: str,
                              title: str = Field(min_length=1, max_length=160),
                              author: str = Field(min_length=1, max_length=160),
                              version: str = Field(default='1.0', min_length=1, max_length=160)) -> dict:
        """Export the actual Dress-up assembly as a new self-contained VRM 1.0 file.

        Stop the preview and restore the default clip first. The destination is a
        filename under this lab's saves/ and is never overwritten; title and author
        are required. Metadata keeps the native restrictive defaults (author,
        noncommercial, no redistribution or modification), so releasing the result
        is a separate licensing decision. Completion, embedded resources, skins and
        spring references are checked before publication. A valid file does not
        certify visual fit, collision behaviour or a Godot import.
        """
        return await runtime.export_wear_vrm(filename, expected_wear, title, author, version)

    @ready_tool(annotations=edit)
    async def capture_wear_review(expected_wear: str, views: list[str] | None = None,
                                  size: int = Field(default=768, ge=256, le=2048),
                                  quality: Literal['legacy', 'balanced', 'high'] = 'balanced'
                                  ) -> list[TextContent | ImageContent]:
        """Capture 1-6 assembled Dress-up views and save a snapshot manifest.

        Views are either the legacy front/side/back/three_quarter set or
        REGION_ANGLE, where REGION is body/face/head/upper/legs/feet and ANGLE is
        front/back/left/right/three_quarter_left/three_quarter_right. Left and
        right are observer sides seen from the front, and one batch shares the
        measured bounds. Stop the preview and pass a fresh wear token. The images
        come back inline; look at them before judging appearance or fit.
        """
        manifest, images = await runtime.capture_wear_review(
            expected_wear, views if views is not None else ['front', 'side', 'back'], size, quality)
        return [TextContent(type='text', text=json.dumps(manifest, ensure_ascii=False)),
                *[Image(data=data, format='png').to_image_content() for data in images]]

    @ready_tool(annotations=edit)
    async def capture_wear_reference(expected_wear: str, item_id: str, mesh_names: list[str] | None = None,
                                     preview: bool = False, include_base_meshes: bool = False,
                                     base_mesh_names: list[str] | None = None) -> dict:
        """Save the actual Dress-up body and garment BakeMesh geometry for fitting diagnostics.

        Pick the item and mesh names from get_wear_snapshot. The artifact carries
        original positions, skin weights, bindposes and current bone matrices, so
        a fit can be inverted without editing the body. By default it records the
        stopped edit pose; preview=true requires running native playback and
        records the synthesized body and garment in the same pose. With
        include_base_meshes it also stores the base Body/Face/Hair skin and bones,
        plus a separate Foot mesh when the model has one; base_mesh_names narrows
        that to Body plus Foot/Face/Hair. A unique JSON file under saves/ is
        written; geometry is not edited and no VRM is produced.
        """
        return await runtime.capture_wear_reference(expected_wear, item_id, mesh_names, preview,
                                                    include_base_meshes, base_mesh_names)

    @ready_tool(annotations=read)
    async def inspect_wear_fit_context(expected_wear: str, item_id: str,
                                       mesh_names: list[str] = Field(min_length=1, max_length=16),
                                       region: Literal['feet', 'waist_back', 'head', 'whole_body'] = 'feet',
                                       preview: bool = False,
                                       sample_limit: int = Field(default=256, ge=32, le=2048),
                                       target_mesh_name: str | None = None) -> dict:
        """Measure the base anatomy and the wearable geometry together in one native pose.

        Returns world bounds, bone-registration offsets, bidirectional sampled
        exact surface distances and inward-ray thickness estimates. The raw JSON
        keeps original and posed vertices, normals, topology, UVs, weights and the
        actual bone matrices, and a static diagnostic GLB is written with anatomy
        and garment materials kept distinct. Take item and mesh ids from a fresh
        get_wear_snapshot. Optional target_mesh_name (also present in mesh_names)
        measures other parts against that garment, for example a tail or bow against
        the main dress surface. preview=true requires active native playback.
        Unsigned distances and intentional openings do not certify penetration.
        """
        return await runtime.inspect_wear_fit_context(expected_wear, item_id, mesh_names, region,
                                                      preview, sample_limit, target_mesh_name)

    @ready_tool(annotations=read)
    async def sample_wear_preview_rig(expected_wear: str) -> dict:
        """Read the current synthesized preview rig: bone world matrices, local TRS and ancestry.

        Requires active native preview and a fresh wear token. Pair it with a held
        pose for deterministic sampling. Poses are not modified and no animation is
        exported.
        """
        return await runtime.sample_wear_preview_rig(expected_wear)

    @ready_tool(annotations=read)
    async def list_wear_preview_clips(expected_wear: str) -> dict:
        """List the allowlisted native body motions and poses with session-local ids.

        Ids are valid for this session only; nothing is exported as an asset.
        """
        return await runtime.wear_preview_clips(expected_wear)

    @ready_tool(annotations=edit)
    async def select_wear_preview_clip(expected_wear: str, clip_id: str | None = None) -> dict:
        """Choose a native motion or pose for the first Dress-up preview segment.

        Start and stop the default preview once so its timeline exists. Requires
        stopped playback and an id from a fresh list. The clip is cloned in memory
        and does not modify the model; null restores the default. Restore the
        default before saving or opening a model. No animation asset is written
        into XWear/XRoid.
        """
        return await runtime.select_wear_preview_clip(expected_wear, clip_id)

    @ready_tool(annotations=edit)
    async def hold_wear_preview_pose(expected_wear: str, clip_id: str,
                                     seconds: float = Field(ge=0, le=60, allow_inf_nan=False)) -> dict:
        """Pause a selected native clip at a given time for repeatable contact tests.

        Select a listed clip and start playback first; the time lies within that
        clip's first timeline segment. The player strips the managed Pause/Evaluate
        wrappers and checks the registered engine bindings before using them. Spring
        physics can keep running, so measure actual drift with a motion capture.
        Follow with capture_wear_reference(preview=true), then stop the preview and
        restore the default clip before saving. Session-only.
        """
        return await runtime.hold_wear_preview_pose(expected_wear, clip_id, seconds)

    @ready_tool(annotations=edit)
    async def capture_wear_motion(expected_wear: str,
                                  samples: int = Field(default=8, ge=3, le=16),
                                  interval_seconds: float = Field(default=.25, ge=.1, le=2, allow_inf_nan=False),
                                  view: str = 'front',
                                  size: int = Field(default=768, ge=256, le=1024),
                                  quality: Literal['legacy', 'balanced', 'high'] = 'balanced') -> dict:
        """Save consecutive preview images together with measured skeleton transforms.

        The view also accepts REGION_ANGLE (body/face/head/upper/legs/feet with
        front/back/left/right/three_quarter_left/three_quarter_right), with sides
        observed from the front. Start playback explicitly first. Frames come from
        the actual preview animator root with fixed framing and frame ids, and
        playback keeps running afterwards: stop it before fitting or saving.
        Movement and spring rotations are observations, not a collision clearance.
        """
        return await runtime.capture_wear_motion(expected_wear, samples, interval_seconds, view, size, quality)

    @ready_tool(annotations=edit)
    async def import_xwear(filename: str, expected_wear: str) -> dict:
        """Import a .xwear and return verified new item ids.

        Attached sessions also accept an absolute input path; otherwise use lab saves/.

        Nothing is fitted automatically and no body geometry is deleted. Fit-alert
        options changed in the target profile are restored afterwards. Relist
        with the new wear token.
        """
        return await runtime.import_xwear(filename, expected_wear)

    @ready_tool(annotations=edit)
    async def set_wear_fit(expected_wear: str, item_id: str,
                           fit_y: float = Field(ge=0, le=2, allow_inf_nan=False),
                           fit_z: float = Field(ge=0, le=2, allow_inf_nan=False)) -> dict:
        """Set the native vertical and depth fit for one item and read the values back.

        Stop animation first. The 0..2 range matches the sliders this project has
        tested. A successful write says nothing about collision-free clothing:
        inspect appearance and movement separately.
        """
        return await runtime.wear_edit('set_wear_fit', {'expected_wear': expected_wear,
                                                        'item_id': item_id, 'fit_y': fit_y, 'fit_z': fit_z})

    @ready_tool(annotations=edit)
    async def set_wear_animation(expected_wear: str, playing: bool) -> dict:
        """Start or stop the built-in preview idempotently, without desktop input."""
        return await runtime.wear_edit('set_wear_animation', {'expected_wear': expected_wear, 'playing': playing})

    @ready_tool(annotations=edit)
    async def pose_wear_preview_legs(expected_wear: str, clip_id: str,
                                     seconds: float = Field(ge=0, le=60, allow_inf_nan=False),
                                     upper_leg_inward_degrees: float = Field(default=3, ge=0, le=6,
                                                                            allow_inf_nan=False),
                                     foot_inward_degrees: float = Field(default=8, ge=0, le=12,
                                                                        allow_inf_nan=False)) -> dict:
        """Freeze a selected clip and rotate both legs and feet inward on the preview clone.

        The rotation is world-Y yaw, so the existing heel pitch is preserved. Foot
        yaw is the total offset and is not added to the upper-leg yaw. This is a
        session-only sampled pose, not continuous animation and not a saved
        .vroidpose or XRoid pose. Stopping or re-selecting restores the offsets and
        the source edit rig is untouched. The call needs the unique native J_Bip leg
        rig and rejects anything else before rotating.
        """
        return await runtime.pose_wear_preview_legs(expected_wear, clip_id, seconds,
                                                    upper_leg_inward_degrees, foot_inward_degrees)

    @ready_tool(annotations=edit)
    async def save_wear_project(filename: str, expected_wear: str) -> dict:
        """Save the assembly as a new XRoid archive without overwriting.

        Attached sessions accept absolute paths in existing directories;
        otherwise use a filename under lab saves/.

        Requires stopped animation. The archive is verified and its hash returned.
        A successful save proves persistence, not VRM or Godot readiness.
        """
        return await runtime.save_wear_project(filename, expected_wear)
