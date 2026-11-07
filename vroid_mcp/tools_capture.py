"""Capture and review tools for quiet ordinary-model inspection.

`capture_review` is the multi-view review used for before/after comparison; it
writes PNGs and a numeric state file under the lab, and never edits or saves the
character. `screenshot` returns one PNG, including photo-preview views.
"""

from __future__ import annotations

import json
from typing import Literal

from mcp.server.fastmcp.utilities.types import Image
from mcp.types import ImageContent, TextContent, ToolAnnotations
from pydantic import Field, StrictBool, StrictFloat, StrictInt


def register(ready_tool, runtime, lab, read, edit):
    """Publish the capture and review tools."""

    @ready_tool(annotations=edit)
    async def capture_body_reference(expected_model: str,
                                     label: str = Field(default='', max_length=80)) -> dict:
        """Save the current body and face geometry, skeleton and skin weights for clothing fitting.

        Uses a fresh model token. The native body is not changed; one uniquely named
        JSON artifact is written under this lab's saves/. Edit-pose vertices, Unity
        coordinates and bone matrices are stated explicitly. No textures, hair,
        clothing or VRM export.
        """
        return await runtime.capture_body_reference(expected_model, label)

    @ready_tool(annotations=read)
    async def screenshot(expected_model: str, view: str = 'front',
                         size: StrictInt = Field(default=512, ge=256, le=2048),
                         quality: Literal['legacy', 'balanced', 'high'] = 'balanced',
                         width: StrictInt | None = None, height: StrictInt | None = None,
                         msaa: StrictInt | None = None, ssaa: StrictInt | None = None, clean: StrictBool = True) -> Image:
        """Return one native PNG; use the photo view for a posed preview.

        Legacy views are front/side/back/three_quarter plus the full_ variants.
        Regional views are REGION_ANGLE with REGION in
        body/face/head/upper/legs/feet and ANGLE in
        front/back/left/right/three_quarter_left/three_quarter_right (for example
        face_left); left and right are observer sides seen from the front, and
        regional views need edit mode. Quality: legacy is a single sample, balanced
        adds 4x MSAA, high adds 4x MSAA with a 2x render scale. Internal rendering is
        capped at 8M pixels while the output stays within 256..2048, and the GPU may
        reduce MSAA. Use capture_review when the effective quality metadata matters.
        Optional paired width/height are 256..2048; MSAA accepts 1/2/4 and SSAA
        accepts 1/2/3. current_editor preserves the active edit camera pose and fits
        its projected view without crop or changed subject proportions. clean=False
        accepts the default view or current_editor and default render
        arguments; it reads Unity's actual application framebuffer at end of frame,
        including UI, with native dimensions/quality. It never focuses the desktop
        and never falls back between capture modes. Photo settings are restored.
        Clean cameras exclude native auxiliary guide layers without changing UI
        selection. Fixed/regional/current-editor clones preserve selected hair on
        its native Outline layer. Bone material overrides must be cleared manually;
        live photo capture also requires hair selection to be cleared. An unavailable
        guide-isolation binding fails explicitly before render or selection changes.
        """
        return Image(data=await runtime.screenshot(view, expected_model, size, quality,
            width=width, height=height, msaa=msaa, ssaa=ssaa, clean=clean), format='png')

    @ready_tool(annotations=read)
    async def screenshot_metadata(expected_model: str, view: str = 'front', size: StrictInt = 512,
                         quality: Literal['legacy', 'balanced', 'high'] = 'balanced',
                         width: StrictInt | None = None, height: StrictInt | None = None,
                         msaa: StrictInt | None = None, ssaa: StrictInt | None = None, clean: StrictBool = True
                         ) -> list[TextContent | ImageContent]:
        """Return a screenshot plus effective dimensions, quality, framing and provenance.

        Uses the same bounded capture contract as screenshot; base64 is carried only
        by the image block. Native/visual acceptance is separate from metadata.
        """
        data, metadata = await runtime.screenshot_with_metadata(view, expected_model, size, quality,
            width=width, height=height, msaa=msaa, ssaa=ssaa, clean=clean)
        return [TextContent(type='text', text=json.dumps(metadata, ensure_ascii=False)),
                Image(data=data, format='png').to_image_content()]

    @ready_tool(annotations=edit)
    async def editor_camera(expected_model: str, action: Literal['get', 'angles', 'rotate', 'zoom', 'pan',
                            'reset', 'mode', 'projection', 'custom'] = 'get',
                            angles: list[StrictFloat] | None = None, delta: StrictFloat | None = None,
                            pan: list[StrictFloat] | None = None, mode: str | None = None,
                            position: list[StrictFloat] | None = None, center: list[StrictFloat] | None = None) -> dict:
        """Read/change the current model's edit camera; photo camera is separate.

        angles and rotate use [x,y] degrees (bounded +/-36000). Zoom delta and pan
        [x,y] are native input deltas (+/-1000), with no physical-unit conversion.
        custom requires position/center vectors (+/-10000 native coordinates).
        mode accepts Front/Right/Top/Reverse/RotateUp/RotateLeft/RotateRight/RotateDown.
        projection toggles the actual projection. Animated modes poll to completion.
        Saved model/history is unchanged. Multi-camera ambiguity is refused.
        Get is read-only; known prewrite rejections return ok=False without leaving
        an edit receipt. Unknown or post-invocation failures retain uncertainty.
        """
        return await runtime.editor_camera(expected_model, action, angles=angles, delta=delta, pan=pan,
            mode=mode, position=position, center=center)

    @ready_tool(annotations=edit)
    async def face_preview(expected_model: str, name: str | None = None, weight: StrictFloat = 100,
                           filter: str | None = None, reset: StrictBool = False, restore: StrictBool = False) -> dict:
        """List/filter or temporarily set raw current-face blendshape weights (0..100).

        Exact case-insensitive name wins; suffix matches must be unique. reset zeros
        the scoped face only; restore reapplies the original snapshot with readback.
        Renderer/mesh identity and weights are checked at capture. Rebuilds/animation
        can replace preview state. Does not modify saved expression definitions.
        Successful restore releases tracking; the next preview snapshots its new
        baseline. Listing is read-only. Known prewrite refusal is distinguishable
        from an uncertain/partial invocation and never requires a blind retry.
        """
        return await runtime.face_preview(expected_model, name, weight, filter, reset=reset, restore=restore)

    @ready_tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    async def capture_review(expected_model: str, label: str = Field(default='', max_length=80),
                             views: list[str] | None = None, size: int = Field(default=1024, ge=256, le=2048),
                             baseline_id: str | None = None,
                             quality: Literal['legacy', 'balanced', 'high'] = 'balanced'
                             ) -> list[TextContent | ImageContent]:
        """Capture 1-6 native views for visual inspection and save the PNGs plus numeric state.

        Defaults to front, three_quarter, full_front and full_back, and requires edit
        mode. REGION_ANGLE views work as documented for screenshot; one regional batch
        shares its measured bounds, and a baseline from the same model locks those
        bounds while another model gets fresh ones. The response carries the images,
        their paths, the model height, the capture id and a visual checklist. There is
        no OCR, no click automation, no beauty scoring and no automatic collision
        verdict. Passing baseline_id from an earlier capture with the same views and
        size yields before/after images and parameter differences for face, body,
        clothing and colour; hair geometry changes still need visual inspection, and a
        different model token is called out explicitly. The character is not edited or
        saved: only review artifacts are written and the editor guides are hidden.
        """
        selected = views if views is not None else ['front', 'three_quarter', 'full_front', 'full_back']
        manifest, images = await runtime.capture_review(expected_model, selected, size, label,
                                                        baseline_id, quality)
        summary = {key: value for key, value in manifest.items() if key != 'state'}
        summary['height'] = manifest['state']['height']
        content = [TextContent(type='text', text=json.dumps(summary, ensure_ascii=False))]
        for caption, data in images:
            content.append(TextContent(type='text', text=caption))
            content.append(Image(data=data, format='png').to_image_content())
        return content
