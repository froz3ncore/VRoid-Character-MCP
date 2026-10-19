from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image
from mcp.types import ToolAnnotations, TextContent, ImageContent
from pydantic import BaseModel, Field, StrictInt, StrictBool

from .runtime import Runtime
from .texture_tools import register_texture_tools


class FaceChange(BaseModel):
    id: str
    value: float = Field(strict=True, allow_inf_nan=False)


class ParameterChange(BaseModel):
    id: str
    value: bool | float | str | list[float] | list[list[float]]


class HairColorChange(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    color: list[float] = Field(min_length=4, max_length=4)


def create_server(lab: Path, variant: str, model_file: Path | None = None) -> FastMCP:
    runtime = Runtime(lab)
    initialized = False
    operation_lock = asyncio.Lock()

    async def initialize_runtime():
        nonlocal runtime, initialized
        if initialized:
            return
        try:
            await asyncio.to_thread(runtime.start)
            await runtime.initialize(variant, model_file)
            initialized = True
        except BaseException:
            await asyncio.to_thread(runtime.close)
            runtime = Runtime(lab)
            raise

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield runtime
        finally:
            await asyncio.to_thread(runtime.close)

    mcp = FastMCP('VRoid Character MCP', lifespan=lifespan,
        instructions='Controls a disposable VRoid Studio copy through native methods. '
        'Call list_face_params first and use its model_token as expected_model. '
        'Use list_parameters for colors, expressions, general, accessories and hair. '
        'Use list_hair_nodes(category) then its node id as scope for hair parameters. '
        'Use list_accessories then instance id as scope for accessory parameters. '
        'Parameter types include float, int, bool, enum index, RGBA color, vector3, quaternion and curve control points. '
        'Use set_height for a measured centimeter target. '
        'Use capture_review before and after edits for native multi-view images and parameter comparisons; inspect the images before judging appearance. '
        'For Dress-up call get_wear_status, then open_wear_project/import_xwear with expected_wear; '
        'use set_wear_fit/set_wear_animation and save_wear_project for XRoid. Relist after imports. '
        'Use get_wear_snapshot and capture_wear_review for actual assembly data and visual acceptance; stop preview first. '
        'Ordinary parameter editing and capture_review are not assembly controls. '
        'List the relevant parameters or presets before applying them. Relist clothing parameters after changing clothes. '
        'Preset lists include descriptive English names when known; preserve native IDs. '
        'Parameter lists retain native labels and write IDs, and add semantic bindings plus exact-key English name corrections when known. '
        'Semantic keys can repeat and are not write IDs; relist before editing after a preset change. '
        'Colors expose actual binding values, mixed aggregate state and shared aliases. '
        'Use separate native left/right eye IDs for heterochromia; BothEyes writes both. '
        'Check affected_parameter_ids before editing shared colors. '
        'Use preview_presets with 1-6 IDs for native thumbnails before choosing a preset. '
        'export_wear_vrm exports the actual Dress-up assembly with restrictive native metadata defaults. '
        'No desktop input or freehand brush painting. Texture tools support native region/layer/UV export and PNG-layer import. '
        'A batch follows VRoid native history and can require multiple undo steps.')
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    edit = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    def ready_tool(**options):
        """Publish the catalog immediately; start Unity only on the first tool call."""
        def register(function):
            @wraps(function)
            async def ready(*args, **kwargs):
                async with operation_lock:
                    await initialize_runtime()
                    return await function(*args, **kwargs)
            return mcp.tool(**options)(ready)
        return register

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    async def restart_session(discard_unsaved: bool = False) -> dict:
        """Recreate only this MCP-owned VRoid copy, discarding its unsaved changes.

        Requires explicit discard_unsaved=true. Save first when possible; do not use
        this to silently discard a user's work. A new model_token invalidates old IDs.
        Works after COPY_DISCONNECTED or an uncertain native call. Never touches other VRoid processes.
        """
        nonlocal runtime, initialized
        if not discard_unsaved:
            raise ValueError('Explicit discard_unsaved=true required; this discards the MCP copy unsaved changes')
        async with operation_lock:
            await asyncio.to_thread(runtime.close)
            runtime = Runtime(lab)
            initialized = False
            await initialize_runtime()
            return await runtime.status()

    @ready_tool(annotations=read)
    async def get_status() -> dict:
        """Check the copy, current model, background processing, and model update state."""
        return await runtime.status()

    @ready_tool(annotations=edit)
    async def capture_body_reference(expected_model: str, label: str = Field(default='',max_length=80)) -> dict:
        """Save validated current body/face meshes, skin weights and skeleton for clothing fitting.

        Uses a fresh model_token. Native body stays unchanged; only an artifact is written
        under this lab's saves/ with a unique filename. Current edit-pose vertices, Unity
        coordinates and bone matrices are explicit. No textures, hair, clothing or VRM export.
        """
        return await runtime.capture_body_reference(expected_model,label)

    @ready_tool(annotations=read)
    async def get_wear_status() -> dict:
        """Read Dress-up activity, wear_token, item IDs, mesh names, fit values and animation state.

        Use wear_token as expected_wear for all Dress-up edits. Ordinary model tokens
        and screenshots are separate and do not validate the assembled outfit.
        """
        return await runtime.wear_status()

    @ready_tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False))
    async def open_wear_project(filename: str, expected_wear: str, discard_unsaved: bool = False) -> dict:
        """Open a .vroid base or .xroid assembly already in this lab's saves/ in Dress-up.

        Requires discard_unsaved=true to explicitly replace the copy's current edit.
        Returns a new wear_token and native items after the load task completes.
        """
        return await runtime.open_wear_project(filename,expected_wear,discard_unsaved)

    @ready_tool(annotations=read)
    async def get_wear_snapshot(expected_wear: str) -> dict:
        """Read actual Dress-up item renderers, texture dimensions, skin bones and VRM spring components.

        Requires fresh wear_token and stopped preview. Reports instantiated data;
        component presence alone does not prove visual fit or simulated movement.
        """
        return await runtime.wear_snapshot(expected_wear)

    @ready_tool(annotations=read)
    async def inspect_wear_body_occlusion(expected_wear: str) -> dict:
        """Read native Body mesh active marks, default geometry hash and fresh occlusion token.

        Vertex indices refer to the original default Body mesh, never compacted posed
        meshes. Use a matching source_geometry_sha256 from a captured reference.
        This does not modify the model or infer which body regions should be hidden.
        """
        return await runtime.inspect_wear_body_occlusion(expected_wear)

    @ready_tool(annotations=edit)
    async def set_wear_body_occlusion(expected_wear: str,expected_occlusion_token: str,hidden_vertices: list[StrictInt]=Field(max_length=2048)) -> dict:
        """Replace native Body hidden-vertex marks on an independent Dress-up copy.

        Requires a fresh inspection token and sorted distinct original default mesh
        indices; limited to 20 percent / 2048 vertices. Keep existing hidden indices
        when adding regions. Empty list restores the default Body mesh. Uses native
        mesh history; does not modify the .vroid source or garment geometry.
        Stops on stale identity or uncertain writes. Save/reopen, visible seams,
        animation and VRM export must be verified separately.
        """
        return await runtime.set_wear_body_occlusion(expected_wear,expected_occlusion_token,hidden_vertices)

    @ready_tool(annotations=read)
    async def inspect_wear_native_shoes(expected_wear: str) -> dict:
        """Inspect a separate native shoe-only Cloth renderer and its saved visibility marks. Rejects mixed clothing materials."""
        return await runtime.inspect_wear_native_shoes(expected_wear)

    @ready_tool(annotations=edit)
    async def set_wear_native_shoes_visible(expected_wear: str,expected_visibility_token: str,visible: StrictBool) -> dict:
        """Hide/show only the separately identified native shoe surface using persistent native mesh marks. Preserves body Foot geometry and imported XWear; save/reopen is separate."""
        return await runtime.set_wear_native_shoes_visible(expected_wear,expected_visibility_token,visible)

    @ready_tool(annotations=edit)
    async def export_wear_vrm(filename: str, expected_wear: str,
                              title: str = Field(min_length=1,max_length=160),
                              author: str = Field(min_length=1,max_length=160),
                              version: str = Field(default='1.0',min_length=1,max_length=160)) -> dict:
        """Export the actual Dress-up assembly as a new self-contained VRM 1.0 file.

        Stop preview and restore the default clip first. Filename-only destination
        under this lab's saves; refuses overwrite. Title and author must be explicit.
        Uses restrictive native metadata defaults (only author, noncommercial,
        no redistribution or modification); release licensing is a separate decision.
        Checks actual task completion, embedded resources, skins and spring references,
        then restores export mode. No automatic retries on uncertain writes.
        File validity does not certify visual fit, collisions or Godot runtime.
        """
        return await runtime.export_wear_vrm(filename,expected_wear,title,author,version)

    @ready_tool(annotations=edit)
    async def capture_wear_review(expected_wear: str, views: list[str] | None = None,
                                   size: int = Field(default=768,ge=256,le=2048),
                                   quality: Literal['legacy','balanced','high'] = 'balanced') -> list[TextContent | ImageContent]:
        """Capture 1-6 assembled Dress-up views and save a snapshot manifest.

        Legacy: front/side/back/three_quarter. Regional: REGION_ANGLE, where REGION is
        body/face/head/upper/legs/feet and ANGLE is front/back/left/right/three_quarter_left/three_quarter_right.
        Left/right are observer sides from the front. One batch shares measured bounds.

        Stop preview and use a fresh wear_token. Does not use ordinary avatar screenshots.
        Returns native images; inspect them before judging appearance or fit.
        """
        manifest,images=await runtime.capture_wear_review(expected_wear,views if views is not None else ['front','side','back'],size,quality)
        return [TextContent(type='text',text=json.dumps(manifest,ensure_ascii=False)),
                *[Image(data=data,format='png').to_image_content() for data in images]]

    @ready_tool(annotations=edit)
    async def capture_wear_reference(expected_wear: str, item_id: str, mesh_names: list[str] | None = None, preview: bool = False, include_base_meshes: bool = False, base_mesh_names: list[str]|None=None) -> dict:
        """Save actual Dress-up body and garment BakeMesh geometry for fitting diagnostics.

        Choose item ID and optional mesh names from get_wear_snapshot. Includes original
        positions, skin weights, bindposes and current bone matrices for inverse fitting.
        Default captures stopped edit geometry. preview=true requires active native
        animation and captures its actual synthesized body and garment pose together.
        include_base_meshes adds actual base Body/Face/Hair skin/bones and a separate
        Foot mesh when present; combined Body/Foot renderers are identified explicitly.
        base_mesh_names can restrict this to Body plus Foot/Face/Hair to avoid unrelated data.
        Unique JSON under lab saves; does not edit geometry or export VRM.
        """
        return await runtime.capture_wear_reference(expected_wear,item_id,mesh_names,preview,include_base_meshes,base_mesh_names)

    @ready_tool(annotations=read)
    async def inspect_wear_fit_context(expected_wear: str,item_id: str,mesh_names: list[str]=Field(min_length=1,max_length=16),
                                       region: Literal['feet','waist_back','head','whole_body']='feet',preview: bool=False,
                                       sample_limit: int=Field(default=256,ge=32,le=2048),target_mesh_name: str|None=None) -> dict:
        """Measure both actual base anatomy and wearable 3D geometry in one native pose.

        Returns world bounds, bone-registration offsets, bidirectional sampled exact
        surface distances and inward-ray thickness estimates. Raw JSON includes original
        and posed vertices, normals, topology, UVs, weights and actual bone matrices.
        Also saves a static diagnostic GLB with distinct anatomy/garment materials.
        Choose fresh item/mesh IDs from get_wear_snapshot. No screenshots or model edits.
        Optional target_mesh_name (included in mesh_names) compares other parts against
        that garment, e.g. a tail/bow against the actual main dress surface.
        Unsigned distances and intentional openings do not certify penetration/collision.
        preview=true requires active native playback; otherwise stop animation first.
        """
        return await runtime.inspect_wear_fit_context(expected_wear,item_id,mesh_names,region,preview,sample_limit,target_mesh_name)

    @ready_tool(annotations=read)
    async def sample_wear_preview_rig(expected_wear:str)->dict:
        """Read current synthesized preview bone matrices, local TRS and ancestry, without images.

        Requires active native preview and a fresh wear token. Pair with hold for
        deterministic animation sampling. Does not change poses or export an animation.
        """
        return await runtime.sample_wear_preview_rig(expected_wear)

    @ready_tool(annotations=read)
    async def list_wear_preview_clips(expected_wear: str) -> dict:
        """List allowlisted native body motions/poses with session-local IDs; no asset export."""
        return await runtime.wear_preview_clips(expected_wear)

    @ready_tool(annotations=edit)
    async def select_wear_preview_clip(expected_wear: str, clip_id: str | None = None) -> dict:
        """Temporarily select a native body motion/pose for the first Dress-up preview segment.

        Start/stop default preview once to initialize its timeline. Requires stopped
        playback and a fresh listed clip ID. Uses a cloned playable asset in memory;
        null restores default. Stop and restore default before saving/opening a model.
        No animation asset is written into XWear/XRoid or exported.
        """
        return await runtime.select_wear_preview_clip(expected_wear,clip_id)

    @ready_tool(annotations=edit)
    async def hold_wear_preview_pose(expected_wear: str,clip_id: str,
                                       seconds: float = Field(ge=0,le=60,allow_inf_nan=False)) -> dict:
        """Pause and evaluate a selected native preview clip for repeatable contact tests.

        Select a listed clip and start playback first. Time is within that clip's
        first timeline segment. This player strips managed Pause/Evaluate wrappers;
        registered engine bindings are checked before use. Spring physics can
        continue; measure actual body drift with motion capture. Use capture_wear_reference(preview=true),
        then stop preview and restore the default clip before saving. Session-only.
        """
        return await runtime.hold_wear_preview_pose(expected_wear,clip_id,seconds)

    @ready_tool(annotations=edit)
    async def capture_wear_motion(expected_wear: str,
                                  samples: int = Field(default=8,ge=3,le=16),
                                  interval_seconds: float = Field(default=.25,ge=.1,le=2,allow_inf_nan=False),
                                  view: str = 'front',
                                  size: int = Field(default=768,ge=256,le=1024),
                                  quality: Literal['legacy','balanced','high'] = 'balanced') -> dict:
        """Save consecutive native Dress-up preview images and measured skeleton transforms.

        Views also accept REGION_ANGLE (body/face/head/upper/legs/feet with
        front/back/left/right/three_quarter_left/three_quarter_right). Sides are observer-relative.
        Start animation explicitly first. Uses the actual preview animator root, fixed
        framing and frame IDs. Leaves playback running; stop it before saving or fitting.
        Motion and spring rotation observations are not a collision-free certification.
        """
        return await runtime.capture_wear_motion(expected_wear,samples,interval_seconds,view,size,quality)

    @ready_tool(annotations=edit)
    async def import_xwear(filename: str,expected_wear: str) -> dict:
        """Import an existing .xwear from this lab's saves/, return verified new item IDs.

        No automatic fitting or body deletion. Temporary fit-alert options in the
        disposable profile are restored after completion. Relist with the new wear_token.
        """
        return await runtime.import_xwear(filename,expected_wear)

    @ready_tool(annotations=edit)
    async def set_wear_fit(expected_wear: str,item_id: str,
                           fit_y: float = Field(ge=0,le=2,allow_inf_nan=False),
                           fit_z: float = Field(ge=0,le=2,allow_inf_nan=False)) -> dict:
        """Set native vertical/depth fit from a fresh get_wear_status item, then read back.

        Stop animation first. Range 0..2 matches the tested sliders. This does not
        prove collision-free clothing; inspect appearance and movement separately.
        """
        return await runtime.wear_edit('set_wear_fit',{'expected_wear':expected_wear,
            'item_id':item_id,'fit_y':fit_y,'fit_z':fit_z})

    @ready_tool(annotations=edit)
    async def set_wear_animation(expected_wear: str,playing: bool) -> dict:
        """Set the built-in Dress-up preview playing state idempotently; no desktop input."""
        return await runtime.wear_edit('set_wear_animation',{'expected_wear':expected_wear,'playing':playing})

    @ready_tool(annotations=edit)
    async def pose_wear_preview_legs(expected_wear:str,clip_id:str,
                                     seconds:float=Field(ge=0,le=60,allow_inf_nan=False),
                                     upper_leg_inward_degrees:float=Field(default=3,ge=0,le=6,allow_inf_nan=False),
                                     foot_inward_degrees:float=Field(default=8,ge=0,le=12,allow_inf_nan=False))->dict:
        """Freeze selected native clip and pose both legs/feet inward on the preview clone.

        World-Y yaw preserves existing heel pitch. Foot yaw is total, not additive to
        upper-leg yaw. Session-only sampled pose; not continuous animation or a saved
        .vroidpose/XRoid pose. Stop/select/hold restores offsets; source edit rig is untouched.
        Requires unique native J_Bip leg rig; rejects unsupported rigs before rotation.
        """
        return await runtime.pose_wear_preview_legs(expected_wear,clip_id,seconds,upper_leg_inward_degrees,foot_inward_degrees)

    @ready_tool(annotations=edit)
    async def save_wear_project(filename: str,expected_wear: str) -> dict:
        """Save an XRoid assembly under saves/ without overwriting; verify archive and return hash.

        Requires stopped animation. Save/reopen proves persistence, not VRM/Godot readiness.
        """
        return await runtime.save_wear_project(filename,expected_wear)

    @ready_tool(annotations=read)
    async def list_parameters(domain:Literal['face','body','clothing','colors','expressions','general','hair','hair_bones','accessories','photo'],
                              scope:str|None=None,category:str|None=None,offset:int=Field(default=0,ge=0),limit:int=Field(default=200,ge=1,le=500))->dict:
        """List typed native controls with values, units/ranges/options. Hair requires category + node scope.

        Accessories require instance scope. Expressions optionally use an expression ID as scope.
        Colors use RGBA 0..1. Read every next_offset page when discovering controls.
        General covers outline, rim light, shading, gaze limits and spring amplitude.
        Native shape controls add semantic_key/group/bindings and translation_key.
        name provides an exact-key English correction when known; label remains native.
        Missing bindings are explicit. Semantic keys may repeat and never replace write IDs.
        Colors add native_value, mixed, color_bindings, shared_groups, alias_of and affected_parameter_ids.
        A mixed aggregate (e.g. BothEyes for heterochromia) has value=null; use the separate side IDs.
        Left/right mean the native UI controls; raw binding key names can use the opposite side.
        """
        return await runtime.parameter_call('list_parameters',{'domain':domain,'scope':scope,'category':category,'offset':offset,'limit':limit})

    @ready_tool(annotations=edit)
    async def set_parameters(expected_model:str,domain:Literal['face','body','clothing','colors','expressions','general','hair','hair_bones','accessories','photo'],
                             changes:list[ParameterChange],scope:str|None=None,category:str|None=None)->dict:
        """Set 1-64 typed parameters from a fresh list_parameters result; all values validate before writes.

        Hair requires category and node scope. Accessories require instance scope. Native history supports Undo.
        Curves are arrays of [x,y] control points, quaternions [x,y,z,w], vectors [x,y,z], colors [r,g,b,a].
        A native error can leave a partial batch: inspect ok/applied/error. Preset or structure changes require relisting.
        Color batches reject overlapping targets (BothEyes plus one eye, or duplicate shared aliases).
        Separate left and right eyes can be set together. Writing BothEyes explicitly unifies them.
        Color results include settled affected_parameters and per-write verification from every binding.
        """
        return await runtime.parameter_call('set_parameters',{'expected_model':expected_model,'domain':domain,
            'changes':[c.model_dump() for c in changes],'scope':scope,'category':category},True)

    @ready_tool(annotations=read)
    async def list_presets(area:Literal['face','body','hair','clothing'],category:str|None=None,offset:int=Field(default=0,ge=0),limit:int=Field(default=100,ge=1,le=200))->dict:
        """List owned presets with stable IDs, original labels and descriptive English names when known."""
        return await runtime.list_presets(area,category,offset,limit)

    @ready_tool(annotations=read)
    async def preview_presets(expected_model:str,area:Literal['face','body','hair','clothing'],
                              preset_ids:list[str]=Field(min_length=1,max_length=6)) -> list[TextContent | ImageContent]:
        """Return native thumbnails for 1-6 distinct owned IDs from a fresh preset list.

        Requires model_token from list_face_params. Returns a manifest plus inline PNGs
        identified by preset_id/name, in requested order. Does not apply a preset, edit
        the character or save files. Clear options and unavailable previews report an
        explicit per-item error. Unknown IDs and stale model tokens reject the request.
        Images show the preset's native thumbnail, not its fit on the current character.
        """
        manifest,images=await runtime.preview_presets(expected_model,area,preset_ids)
        content=[TextContent(type='text',text=json.dumps(manifest,ensure_ascii=False))]
        names={p['id']:p['name'] for p in manifest['presets']}
        for preset_id,data in images:
            content.append(TextContent(type='text',text=json.dumps({'preset_id':preset_id,'name':names[preset_id]},ensure_ascii=False)))
            content.append(Image(data=data,format='png').to_image_content())
        return content

    @ready_tool(annotations=edit)
    async def apply_preset(expected_model:str,area:Literal['face','body','hair','clothing'],preset_id:str)->dict:
        """Apply an owned native preset from list_presets. Relist parameters after structural changes."""
        return await runtime.apply_preset(area,expected_model,preset_id)

    @ready_tool(annotations=read)
    async def list_hair_nodes(category:str='HairFront')->dict:
        """List groups and strands in HairFront, HairBack, AllHair, HairTied, HairSideburns, HairAhoge or HairHanege.

        Use a returned id as scope with list_parameters(domain='hair',category=...).
        """
        return await runtime.parameter_call('list_hair_nodes',{'category':category})

    @ready_tool(annotations=read)
    async def list_hair_bone_groups(category:str='HairFront')->dict:
        """List hair physics groups. list_parameters(domain='hair_bones',category=...) exposes bone count, root rate, stiffness, gravity and radius."""
        return await runtime.parameter_call('list_hair_bone_groups',{'category':category})

    @ready_tool(annotations=edit)
    async def generate_hair_bones(expected_model:str,category:str='HairFront')->dict:
        """Generate native hair bone groups using hair_bones/generation parameters. Existing grouping can be replaced; native Undo supported."""
        return await runtime.parameter_call('generate_hair_bones',{'expected_model':expected_model,'category':category},True)

    @ready_tool(annotations=edit)
    async def edit_hair_structure(expected_model:str,category:str,action:Literal['add_procedural','add_brush','remove'],node_id:str|None=None)->dict:
        """Create a procedural hair group (add_procedural), create a hand-drawn
        brush hair group guide (add_brush), or remove a group/strand. Native Undo
        supported. Hand-drawn strand control points are edited with
        move_hair_strand_point. No freehand pen input. Returns all group IDs so
        the added node can be identified from a fresh list_hair_nodes."""
        return await runtime.parameter_call('edit_hair_structure',{'expected_model':expected_model,'category':category,'action':action,'node_id':node_id},True)

    @ready_tool(annotations=read)
    async def list_hair_strand_points(expected_model: str, category: str, node_id: str) -> dict:
        """List the 3D spine control points of one hand-drawn hair strand:
        index, point, normal and UV for each control point. Read-only; use a
        strand ID from list_hair_nodes (not a group ID)."""
        return await runtime.parameter_call('list_hair_strand_points',
            {'expected_model': expected_model, 'category': category, 'node_id': node_id})

    @ready_tool(annotations=edit)
    async def move_hair_strand_point(expected_model: str, category: str, node_id: str, index: int = Field(ge=0, le=511),
                                     point: list[float] = Field(min_length=3, max_length=3),
                                     normal: list[float] = Field(default_factory=lambda: [0.0, 1.0, 0.0], min_length=3, max_length=3),
                                     uv: list[float] = Field(default_factory=lambda: [0.0, 0.0], min_length=2, max_length=2)) -> dict:
        """Move one control point of a hand-drawn hair strand (brush strands
        only). point/normal are local-space XYZ floats, uv is UV floats. Native
        Undo supported. The command result and the re-read control point are
        returned; read the strand again with list_hair_strand_points."""
        return await runtime.parameter_call('move_hair_strand_point',
            {'expected_model': expected_model, 'category': category, 'node_id': node_id, 'index': index,
             'point': point, 'normal': normal, 'uv': uv}, True)

    @ready_tool(annotations=read)
    async def list_hair_color_elements(expected_model: str, category: str, node_id: str) -> dict:
        """Scan the model's transferable groups and list every editable COLOR
        element (group key, element key, owning transferable id) together with
        the candidate element keys. Use a group key as the address argument of
        set_hair_color. Read-only."""
        return await runtime.parameter_call('list_hair_color_elements',
            {'expected_model': expected_model, 'category': category, 'node_id': node_id})

    @ready_tool(annotations=edit)
    async def set_hair_color(expected_model: str, category: str, node_id: str,
                             changes: list[HairColorChange] = Field(min_length=1, max_length=8),
                             address: str = Field(min_length=1, max_length=200)) -> dict:
        """Set editable hair colour elements by key as RGBA floats 0..1, using a
        transferable-group key from list_hair_color_elements as the address.
        Returns before/after values per change. Native Undo supported; verify
        the visual effect with screenshot."""
        return await runtime.parameter_call('set_hair_color',
            {'expected_model': expected_model, 'category': category, 'node_id': node_id,
             'changes': [c.model_dump() for c in changes], 'address': address}, True)

    @ready_tool(annotations=edit)
    async def duplicate_hair_strand(expected_model: str, category: str, node_id: str) -> dict:
        """Duplicate one hand-drawn hair strand within its group (brush strands
        only), for building hair layering. Native Undo supported. Returns the
        IDs of the added nodes so the copy can be edited immediately."""
        return await runtime.parameter_call('duplicate_hair_strand',
            {'expected_model': expected_model, 'category': category, 'node_id': node_id}, True)

    @ready_tool(annotations=read)
    async def list_hair_materials(expected_model: str, category: str = 'HairFront') -> dict:
        """List shared hair materials (strand texture assets) with their IDs and
        main colors, from the live material thumbnail collection."""
        return await runtime.parameter_call('list_hair_materials',
            {'expected_model': expected_model, 'category': category})

    @ready_tool(annotations=edit)
    async def set_hair_material(expected_model: str, category: str, node_id: str, shared_material_id: str = Field(min_length=1, max_length=200)) -> dict:
        """Assign a shared hair material (strand texture) to one hair group or
        hand-drawn strand, using an ID from list_hair_materials. Native Undo
        supported. Returns the material ID read back after the write; false in
        applied means the read-back differs from the request."""
        return await runtime.parameter_call('set_hair_material',
            {'expected_model': expected_model, 'category': category, 'node_id': node_id,
             'shared_material_id': shared_material_id}, True)

    @ready_tool(annotations=read)
    async def inspect_native_api(class_name: str = Field(min_length=1, max_length=160),
                                 assembly: Literal['VRoid.Studio', 'VRoidCore', 'VRoid.UI', 'UnityEngine.CoreModule', 'VRM10'] = 'VRoid.Studio',
                                 filter: str | None = Field(default=None, max_length=80)) -> dict:
        """List native API metadata for one managed class: declared methods with
        parameter/return type names and fields with types. Read-only discovery aid
        used to extend this tool set; never invokes caller-supplied code. Pass a
        substring filter to bound output (capped at 400 methods / 200 fields)."""
        return await runtime.parameter_call('inspect_native_api',
            {'class_name': class_name, 'assembly': assembly, 'filter': filter})

    @ready_tool(annotations=read)
    async def search_native_classes(assembly: Literal['VRoid.Studio', 'VRoidCore', 'VRoid.UI', 'UnityEngine.CoreModule', 'VRM10'] = 'VRoid.Studio',
                                    substring: str = Field(min_length=3, max_length=80)) -> dict:
        """List full class names in one native assembly whose name contains a
        substring (at least 3 characters, capped at 100 matches). Read-only
        discovery aid for finding exact class names before inspect_native_api."""
        return await runtime.parameter_call('search_native_classes',
            {'assembly': assembly, 'substring': substring})

    @ready_tool(annotations=read)
    async def list_accessory_templates()->dict:
        """List accessory templates across glasses, animal ears, tails and hats."""
        return await runtime.parameter_call('list_accessory_templates')

    @ready_tool(annotations=read)
    async def list_accessories()->dict:
        """List worn accessory instance IDs. Use an id as scope for accessory parameters."""
        return await runtime.parameter_call('list_accessories')

    @ready_tool(annotations=edit)
    async def edit_accessories(expected_model:str,action:Literal['add','remove','duplicate'],template_id:str|None=None,instance_id:str|None=None)->dict:
        """Add a template, remove or duplicate a worn accessory. Relist instances and parameters afterwards."""
        return await runtime.parameter_call('edit_accessories',{'expected_model':expected_model,'action':action,'template_id':template_id,'instance_id':instance_id},True)

    @ready_tool(annotations=read)
    async def list_expressions()->dict:
        """List expression IDs. Definition weights are under list_parameters(domain='expressions',scope=id)."""
        return await runtime.parameter_call('list_expressions')

    @ready_tool(annotations=edit)
    async def set_preview_mode(expected_model:str,mode:Literal['photo','edit'])->dict:
        """Enter native photo preview or return to model editing. Photo parameters are session-only, not saved in .vroid.

        Use list_parameters(domain='photo') for poses, hand poses, lighting, wind, effects and gaze.
        Return to edit before editing/saving the character. No mouse/keyboard automation.
        """
        return await runtime.parameter_call('set_preview_mode',{'expected_model':expected_model,'mode':mode},True)

    @ready_tool(annotations=edit)
    async def set_photo_camera(expected_model:str,position:list[float],target:list[float])->dict:
        """Set photo camera position and look-at target as [x,y,z] meters, then screenshot(view='photo')."""
        return await runtime.parameter_call('set_photo_camera',{'expected_model':expected_model,'position':position,'target':target},True)

    @ready_tool(annotations=edit)
    async def preview_expression(expected_model:str,expression:str|None=None)->dict:
        """Preview an expression by ID; null resets the visual preview. This does not change expression weights."""
        return await runtime.parameter_call('preview_expression',{'expected_model':expected_model,'expression':expression},True)

    @ready_tool(annotations=read)
    async def get_height()->dict:
        """Read native VRoid height in centimeters, label and current live measurement."""
        return await runtime.parameter_call('get_height')

    @ready_tool(annotations=edit)
    async def set_height(expected_model:str,centimeters:float=Field(ge=20,le=400,allow_inf_nan=False),tolerance_cm:float=Field(default=.05,ge=.01,le=.5))->dict:
        """Adjust whole-body size and verify native measured height within tolerance. Preserves relative proportions.

        Native reachable range varies by model. Non-convergence restores the initial scale; native errors
        require inspecting current state. Solver steps use native history.
        Hair and other proportions may affect VRoid's measured height, so call this after styling the model.
        """
        return await runtime.set_height(expected_model,centimeters,tolerance_cm)

    @ready_tool(annotations=read)
    async def list_face_params() -> dict:
        """List UI face sliders, localized labels, ranges, current values, aliases and model_token."""
        return await runtime.list_face_params()

    @ready_tool(annotations=edit)
    async def set_face_params(expected_model: str, changes: list[FaceChange]) -> dict:
        """Set 1-64 face sliders. All values are validated first; duplicate aliases are rejected.

        Only the model matching expected_model may change. Native execution failures can
        produce a partial result; inspect applied and error before doing further work.
        """
        return await runtime.set_face_params(expected_model,[item.model_dump() for item in changes])

    @ready_tool(annotations=read)
    async def list_body_params() -> dict:
        """List body proportions, height and limb sliders, ranges, values and model_token."""
        return await runtime.list_params('body')

    @ready_tool(annotations=edit)
    async def set_body_params(expected_model: str, changes: list[FaceChange]) -> dict:
        """Set 1-64 body parameters from list_body_params through native VRoid history."""
        return await runtime.set_params('body',expected_model,[item.model_dump() for item in changes])

    @ready_tool(annotations=read)
    async def list_clothing_params() -> dict:
        """List shape sliders on currently worn clothes. IDs change when garments change."""
        return await runtime.list_params('clothing')

    @ready_tool(annotations=edit)
    async def set_clothing_params(expected_model: str, changes: list[FaceChange]) -> dict:
        """Set garment shape sliders from a fresh list_clothing_params result."""
        return await runtime.set_params('clothing',expected_model,[item.model_dump() for item in changes])

    @ready_tool(annotations=read)
    async def list_hair_presets(category: str|None=None, offset: int=Field(default=0,ge=0),limit:int=Field(default=100,ge=1,le=200)) -> dict:
        """List owned hairstyles/parts with stable IDs, pagination and descriptive English names when known."""
        return await runtime.list_presets('hair',category,offset,limit)

    @ready_tool(annotations=edit)
    async def apply_hair_preset(expected_model: str,preset_id: str) -> dict:
        """Apply an owned hairstyle or hair part from list_hair_presets; native history supports Undo."""
        return await runtime.apply_preset('hair',expected_model,preset_id)

    @ready_tool(annotations=read)
    async def list_clothing_presets(category: str|None=None, offset: int=Field(default=0,ge=0),limit:int=Field(default=100,ge=1,le=200)) -> dict:
        """List owned built-in outfits, tops, bottoms, shoes and other clothing categories."""
        return await runtime.list_presets('clothing',category,offset,limit)

    @ready_tool(annotations=edit)
    async def apply_clothing_preset(expected_model: str,preset_id: str) -> dict:
        """Apply a clothing preset. It can replace conflicting garments; relist clothing sliders afterwards."""
        return await runtime.apply_preset('clothing',expected_model,preset_id)

    @ready_tool(annotations=read)
    async def list_shoe_templates(expected_model: str) -> dict:
        """List actual native shoe construction templates, including high heels, without changing model data."""
        return await runtime.list_shoe_templates(expected_model)

    @ready_tool(annotations=edit)
    async def add_shoe_template(expected_model: str,template_id: str) -> dict:
        """Create native shoes from a freshly listed template. Requires no existing native Shoes group; never retries uncertain changes."""
        return await runtime.add_shoe_template(expected_model,template_id)

    @ready_tool(annotations=edit)
    async def undo(expected_model: str, steps: int = Field(default=1,ge=1,le=32)) -> dict:
        """Undo native history for any area. Returns face parameters; relist other areas to inspect them."""
        return await runtime.history('undo',expected_model,steps)

    @ready_tool(annotations=edit)
    async def redo(expected_model: str, steps: int = Field(default=1,ge=1,le=32)) -> dict:
        """Redo native history for any area. Returns face parameters; relist other areas to inspect them."""
        return await runtime.history('redo',expected_model,steps)

    @ready_tool(annotations=read)
    async def screenshot(expected_model: str, view: str = 'front', size: int = Field(default=512,ge=256,le=2048),
                         quality: Literal['legacy','balanced','high'] = 'balanced') -> Image:
        """Return native PNG; photo for posed preview.

        Legacy views: front/side/back/three_quarter and full_ variants. Regional views:
        REGION_ANGLE, with body/face/head/upper/legs/feet and
        front/back/left/right/three_quarter_left/three_quarter_right; e.g. face_left.
        Left/right mean observer sides from the front. Regional views require edit mode.

        Quality: legacy=single sample, balanced=4x MSAA, high=4x MSAA + 2x render scale.
        Internal render capped at 8M pixels; output remains size 256..2048. GPU can reduce MSAA.
        Use capture_review for effective-quality metadata. Photo camera settings are restored after capture.
        """
        return Image(data=await runtime.screenshot(view,expected_model,size,quality),format='png')

    @ready_tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False))
    async def capture_review(expected_model: str, label: str = Field(default='',max_length=80),
                             views: list[str] | None = None, size: int = Field(default=1024,ge=256,le=2048),
                             baseline_id: str | None = None,
                             quality: Literal['legacy','balanced','high'] = 'balanced') -> list[TextContent | ImageContent]:
        """Capture 1-6 native model views for AI visual inspection and save PNGs + numeric state under lab/reviews.

        Defaults: front, three_quarter, full_front, full_back. Requires edit mode.
        Also accepts REGION_ANGLE as documented in screenshot. Regional batches share bounds;
        same-model baselines lock those bounds, while another model gets fresh bounds. Returns images directly,
        paths, model height, capture_id and a visual checklist; no OCR, clicks, automated beauty scoring,
        or automatic collision verdict. Pass baseline_id from an earlier review with identical views/size
        to get before/after images and face/body/clothing/color parameter differences. Hair geometry
        changes must be inspected visually. Different model tokens are reported explicitly.
        Does not edit or save the character; it writes only review artifacts and hides editor guides.
        """
        selected=views if views is not None else ['front','three_quarter','full_front','full_back']
        manifest,images=await runtime.capture_review(expected_model,selected,size,label,baseline_id,quality)
        summary={k:v for k,v in manifest.items() if k!='state'}
        summary['height']=manifest['state']['height']
        content=[TextContent(type='text',text=json.dumps(summary,ensure_ascii=False))]
        for caption,data in images:
            content.append(TextContent(type='text',text=caption))
            content.append(Image(data=data,format='png').to_image_content())
        return content

    @ready_tool(annotations=edit)
    async def save_as(expected_model: str, filename: str) -> dict:
        """Save a new .vroid file under the lab's saves/ folder. Existing files are never overwritten."""
        return await runtime.save_as(filename,expected_model)

    register_texture_tools(ready_tool,runtime,lab,read,edit)
    return mcp


def main() -> None:
    parser=argparse.ArgumentParser(description='Local VRoid character MCP; always launches a designated copy.')
    parser.add_argument('--lab',required=True,type=Path,help='Directory containing a physical app/VRoidStudio.exe copy')
    parser.add_argument('--variant',choices=['F00','M00'],default='F00')
    parser.add_argument('--model',type=Path,help='Optional .vroid already inside the lab; otherwise creates a new model')
    args=parser.parse_args()
    create_server(args.lab,args.variant,args.model).run(transport='stdio')


if __name__=='__main__':main()
