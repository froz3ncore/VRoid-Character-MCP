"""Parameter, preset, height and history tools for ordinary model editing.

These operate on the edit model; Dress-up has its own module. Every write takes
a model token from `list_face_params` and is rejected when the token is stale.
"""

from __future__ import annotations

import json
from typing import Literal

from mcp.server.fastmcp.utilities.types import Image
from mcp.types import ImageContent, TextContent, ToolAnnotations
from pydantic import Field

from .tool_models import FaceChange, ParameterChange

DOMAINS = Literal['face', 'body', 'clothing', 'colors', 'expressions', 'general',
                  'hair', 'hair_bones', 'accessories', 'photo']
AREAS = Literal['face', 'body', 'hair', 'clothing']


def register(ready_tool, runtime, lab, read, edit):
    """Publish the parameter and preset tools on the server that owns `runtime`."""

    @ready_tool(annotations=read)
    async def list_parameters(domain: DOMAINS,
                              scope: str | None = None, category: str | None = None,
                              offset: int = Field(default=0, ge=0),
                              limit: int = Field(default=200, ge=1, le=500)) -> dict:
        """List typed native controls with their values, units, ranges and options.

        Hair needs a category and a node scope, accessories an instance scope, and
        expressions may take an expression id as scope. Colors are RGBA in 0..1.
        Read every next_offset page before concluding a control is missing. The
        general domain covers outline, rim light, shading, gaze limits and spring
        amplitude. Shape controls add semantic_key/group/bindings and a
        translation_key; `name` is an exact-key English correction while `label`
        stays native. Missing bindings are reported instead of guessed, and a
        semantic key may repeat across controls and is never a write id. Colors add
        native_value, mixed, color_bindings, shared_groups, alias_of and
        affected_parameter_ids; a mixed aggregate such as BothEyes has a null value,
        so use the separate side ids. Left and right follow the native UI controls,
        which can be the opposite of the raw binding key names.
        """
        return await runtime.parameter_call('list_parameters',
                                            {'domain': domain, 'scope': scope, 'category': category,
                                             'offset': offset, 'limit': limit})

    @ready_tool(annotations=edit)
    async def set_parameters(expected_model: str, domain: DOMAINS,
                             changes: list[ParameterChange], scope: str | None = None,
                             category: str | None = None) -> dict:
        """Write 1-64 typed parameters taken from a fresh list_parameters result.

        Every value is validated before anything is written, and native history can
        undo the batch. Value shapes: curve [x,y] control points, quaternion
        [x,y,z,w], vector [x,y,z], color [r,g,b,a]. Hair needs category and node
        scope, accessories an instance scope. A native error can leave a partial
        batch, so inspect ok/applied/error. Changing a preset or the hair structure
        means relisting. Color batches reject overlapping targets (BothEyes together
        with one eye, or a duplicated shared alias) while separate eyes may be set in
        one call; writing BothEyes unifies them. Color results include settled
        affected_parameters and a per-write verification from each binding.
        """
        return await runtime.parameter_call('set_parameters',
                                            {'expected_model': expected_model, 'domain': domain,
                                             'changes': [item.model_dump() for item in changes],
                                             'scope': scope, 'category': category}, True)

    @ready_tool(annotations=read)
    async def list_presets(area: AREAS, category: str | None = None,
                           offset: int = Field(default=0, ge=0),
                           limit: int = Field(default=100, ge=1, le=200)) -> dict:
        """List owned presets with stable ids, native labels and English names where known."""
        return await runtime.list_presets(area, category, offset, limit)

    @ready_tool(annotations=read)
    async def preview_presets(expected_model: str, area: AREAS,
                              preset_ids: list[str] = Field(min_length=1, max_length=6)
                              ) -> list[TextContent | ImageContent]:
        """Return native thumbnails for 1-6 distinct ids from a fresh preset list.

        Needs the model token from list_face_params. The response is a manifest plus
        inline PNGs keyed by preset_id and name, in the requested order. Nothing is
        applied, edited or saved. Empty option lists and unavailable previews appear
        as per-item errors; unknown ids and a stale token reject the whole request.
        The images are the presets' own thumbnails, not their fit on this character.
        """
        manifest, images = await runtime.preview_presets(expected_model, area, preset_ids)
        content = [TextContent(type='text', text=json.dumps(manifest, ensure_ascii=False))]
        names = {preset['id']: preset['name'] for preset in manifest['presets']}
        for preset_id, data in images:
            content.append(TextContent(type='text', text=json.dumps(
                {'preset_id': preset_id, 'name': names[preset_id]}, ensure_ascii=False)))
            content.append(Image(data=data, format='png').to_image_content())
        return content

    @ready_tool(annotations=edit)
    async def apply_preset(expected_model: str, area: AREAS, preset_id: str) -> dict:
        """Apply an owned native preset; relist parameters after a structural change."""
        return await runtime.apply_preset(area, expected_model, preset_id)

    @ready_tool(annotations=read)
    async def list_face_params() -> dict:
        """List the UI face sliders with labels, ranges, current values, aliases and the model token."""
        return await runtime.list_face_params()

    @ready_tool(annotations=edit)
    async def set_face_params(expected_model: str, changes: list[FaceChange]) -> dict:
        """Write 1-64 face sliders after validating every value and rejecting duplicate aliases.

        Only the model behind expected_model may change. A native failure can leave a
        partial batch, so read `applied` and `error` before continuing.
        """
        return await runtime.set_face_params(expected_model, [item.model_dump() for item in changes])

    @ready_tool(annotations=read)
    async def list_body_params() -> dict:
        """List the body proportions, height and limb sliders with ranges, values and the model token."""
        return await runtime.list_params('body')

    @ready_tool(annotations=edit)
    async def set_body_params(expected_model: str, changes: list[FaceChange]) -> dict:
        """Write 1-64 body parameters from a fresh list_body_params result through native history."""
        return await runtime.set_params('body', expected_model, [item.model_dump() for item in changes])

    @ready_tool(annotations=read)
    async def list_clothing_params() -> dict:
        """List the shape sliders of the garments currently worn; ids change with the garment."""
        return await runtime.list_params('clothing')

    @ready_tool(annotations=edit)
    async def set_clothing_params(expected_model: str, changes: list[FaceChange]) -> dict:
        """Write garment shape sliders from a fresh list_clothing_params result."""
        return await runtime.set_params('clothing', expected_model, [item.model_dump() for item in changes])

    @ready_tool(annotations=read)
    async def list_hair_presets(category: str | None = None, offset: int = Field(default=0, ge=0),
                                limit: int = Field(default=100, ge=1, le=200)) -> dict:
        """List owned hairstyles and hair parts with stable ids, pagination and English names."""
        return await runtime.list_presets('hair', category, offset, limit)

    @ready_tool(annotations=edit)
    async def apply_hair_preset(expected_model: str, preset_id: str) -> dict:
        """Apply an owned hairstyle or hair part; native history can undo it."""
        return await runtime.apply_preset('hair', expected_model, preset_id)

    @ready_tool(annotations=read)
    async def list_clothing_presets(category: str | None = None, offset: int = Field(default=0, ge=0),
                                    limit: int = Field(default=100, ge=1, le=200)) -> dict:
        """List owned outfits, tops, bottoms, shoes and the other clothing categories."""
        return await runtime.list_presets('clothing', category, offset, limit)

    @ready_tool(annotations=edit)
    async def apply_clothing_preset(expected_model: str, preset_id: str) -> dict:
        """Apply a clothing preset; it may replace conflicting garments, so relist the sliders afterwards."""
        return await runtime.apply_preset('clothing', expected_model, preset_id)

    @ready_tool(annotations=read)
    async def list_shoe_templates(expected_model: str) -> dict:
        """List the native shoe construction templates, including high heels, without changing the model."""
        return await runtime.list_shoe_templates(expected_model)

    @ready_tool(annotations=edit)
    async def add_shoe_template(expected_model: str, template_id: str) -> dict:
        """Create native shoes from a freshly listed template.

        Requires that no native Shoes group exists yet, and never retries an
        uncertain change.
        """
        return await runtime.add_shoe_template(expected_model, template_id)

    @ready_tool(annotations=read)
    async def get_height() -> dict:
        """Read the current native height as live_centimeters.

        Use live_centimeters (GetBodyHeight) for calibration and save/reopen
        comparisons. centimeters and label are cached UI values and may lag;
        their difference is not evidence of lost saved scale.
        """
        return await runtime.parameter_call('get_height')

    @ready_tool(annotations=edit)
    async def set_height(expected_model: str,
                         centimeters: float = Field(ge=20, le=400, allow_inf_nan=False),
                         tolerance_cm: float = Field(default=.05, ge=.01, le=.5)) -> dict:
        """Scale the whole body to a measured centimeter target and verify it within tolerance.

        Relative proportions are preserved. The reachable range depends on the model;
        when the solver does not converge the initial scale is restored, and a native
        error means the current state must be inspected. Solver steps go through
        native history. Hair and other proportions affect the measured height, so
        call this after styling.
        """
        return await runtime.set_height(expected_model, centimeters, tolerance_cm)

    @ready_tool(annotations=edit)
    async def undo(expected_model: str, steps: int = Field(default=1, ge=1, le=32)) -> dict:
        """Undo native history; the response returns face parameters, so relist other areas to inspect them."""
        return await runtime.history('undo', expected_model, steps)

    @ready_tool(annotations=edit)
    async def redo(expected_model: str, steps: int = Field(default=1, ge=1, le=32)) -> dict:
        """Redo native history; the response returns face parameters, so relist other areas to inspect them."""
        return await runtime.history('redo', expected_model, steps)

    @ready_tool(annotations=edit)
    async def save_as(expected_model: str, filename: str) -> dict:
        """Save a new .vroid copy; an existing file is never overwritten.

        In an attached window this makes a copy and preserves the original
        character file association and unsaved flag; it does not save in place.
        Attached windows accept absolute paths in existing directories; plain
        filenames and copy sessions use lab saves/.
        """
        return await runtime.save_as(filename, expected_model)

    @ready_tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    async def open_character(expected_model: str, filename: str, discard_unsaved: bool = False) -> dict:
        """Open a .vroid in ordinary editing, using a lab filename or an attached absolute path.

        Requires discard_unsaved=true and replaces the current character. Save
        any work first; the opened file becomes the window's associated file.
        """
        return await runtime.replace_character(expected_model, discard_unsaved, filename=filename)

    @ready_tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    async def save_character(expected_model: str) -> dict:
        """Save the attached character over its associated .vroid using native SaveSync.

        First preserves the original bytes in a new lab backup. Requires an
        existing associated file; untitled characters must use save_character_as first.
        Failure is uncertain: inspect the original and backup before another save.
        """
        return await runtime.save_character(expected_model)

    @ready_tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    async def new_character(expected_model: str, variant: Literal['F00','M00'] = 'F00',
                            discard_unsaved: bool = False) -> dict:
        """Replace the attached ordinary character through the native new-character transition.

        Requires discard_unsaved=true. Save current work before replacement.
        """
        return await runtime.new_character(expected_model, variant, discard_unsaved)

    @ready_tool(annotations=edit)
    async def save_character_as(expected_model: str, path: str) -> dict:
        """Save the attached character to a new .vroid and associate the window with it.

        Accepts an absolute path in an existing directory, or a lab saves filename.
        Never overwrites. If the character changes before association, inspect the
        new file and window before retrying.
        """
        return await runtime.save_character_as(expected_model, path)
