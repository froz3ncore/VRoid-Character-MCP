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
from pydantic import Field


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
                         size: int = Field(default=512, ge=256, le=2048),
                         quality: Literal['legacy', 'balanced', 'high'] = 'balanced') -> Image:
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
        Photo camera settings are restored after the capture.
        """
        return Image(data=await runtime.screenshot(view, expected_model, size, quality), format='png')

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
