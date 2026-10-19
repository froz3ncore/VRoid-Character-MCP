"""Accessory, expression and photo-preview tools.

Photo preview is session-only: it changes what the viewport shows, never the
saved .vroid file. Return to edit mode before editing or saving.
"""

from __future__ import annotations

from typing import Literal


def register(ready_tool, runtime, lab, read, edit):
    """Publish the accessory, expression and photo tools."""

    @ready_tool(annotations=read)
    async def list_accessory_templates() -> dict:
        """List the accessory templates: glasses, animal ears, tails and hats."""
        return await runtime.parameter_call('list_accessory_templates')

    @ready_tool(annotations=read)
    async def list_accessories() -> dict:
        """List the worn accessory instance ids; an id is the scope for accessory parameters."""
        return await runtime.parameter_call('list_accessories')

    @ready_tool(annotations=edit)
    async def edit_accessories(expected_model: str, action: Literal['add', 'remove', 'duplicate'],
                               template_id: str | None = None, instance_id: str | None = None) -> dict:
        """Add a template, or remove or duplicate a worn accessory.

        Relist the instances and their parameters afterwards.
        """
        return await runtime.parameter_call('edit_accessories',
                                            {'expected_model': expected_model, 'action': action,
                                             'template_id': template_id, 'instance_id': instance_id}, True)

    @ready_tool(annotations=read)
    async def list_expressions() -> dict:
        """List expression ids; their definition weights are under list_parameters(domain='expressions', scope=id)."""
        return await runtime.parameter_call('list_expressions')

    @ready_tool(annotations=edit)
    async def set_preview_mode(expected_model: str, mode: Literal['photo', 'edit']) -> dict:
        """Enter native photo preview or return to model editing.

        Photo parameters are session-only and are not saved into .vroid. Use
        list_parameters(domain='photo') for poses, hand poses, lighting, wind,
        effects and gaze. Return to edit before editing or saving the character.
        No mouse or keyboard automation is involved.
        """
        return await runtime.parameter_call('set_preview_mode',
                                            {'expected_model': expected_model, 'mode': mode}, True)

    @ready_tool(annotations=edit)
    async def set_photo_camera(expected_model: str, position: list[float], target: list[float]) -> dict:
        """Set the photo camera position and look-at target as [x,y,z] metres, then screenshot(view='photo')."""
        return await runtime.parameter_call('set_photo_camera',
                                            {'expected_model': expected_model, 'position': position,
                                             'target': target}, True)

    @ready_tool(annotations=edit)
    async def preview_expression(expected_model: str, expression: str | None = None) -> dict:
        """Preview an expression by id; null clears the visual preview.

        Expression weights are not modified.
        """
        return await runtime.parameter_call('preview_expression',
                                            {'expected_model': expected_model, 'expression': expression}, True)
