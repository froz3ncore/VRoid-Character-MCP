"""Group-bound native discovery and validated editing tools."""
from typing import Annotated, Literal
from pydantic import Field

PhysicalValue = Annotated[float, Field(strict=True)]


def register(ready_tool, runtime, lab, read, edit):
    @ready_tool(annotations=read)
    async def list_groups(expected_model: str) -> dict:
        """List exact active/leaf/stored group identities, revisions and native removal evidence."""
        return await runtime.list_groups(expected_model)

    @ready_tool(annotations=read)
    async def list_group_parameters(expected_model: str, group_id: str, kind: str | None = None) -> dict:
        """List exact typed/raw/item bindings, native units and unsupported-write reasons.

        Relist after any preset/topology change. IDs bind model/group revisions;
        semantic keys and translated labels are not write addresses. Raw item
        ranges remain unknown unless a full path matches actual native VM metadata.
        """
        return await runtime.list_group_parameters(expected_model, group_id, kind)

    @ready_tool(annotations=edit)
    async def set_group_parameters(expected_model: str, group_id: str, changes: list[dict]) -> dict:
        """Write exact {id,type,units,value} rows from a fresh group parameter list.

        Every row validates before the first native command. Batches can require
        multiple undo steps; partial errors include actual settled readback.
        """
        return await runtime.set_group_parameters(expected_model, group_id, changes)

    @ready_tool(annotations=read)
    async def list_sections(expected_model: str) -> dict:
        """List group-bound sections; unknown native types stay explicitly unclassified."""
        return await runtime.list_sections(expected_model)

    @ready_tool(annotations=read)
    async def list_categories(expected_model: str, section: str | None = None) -> dict:
        """List exact native group categories and every matching group ID."""
        return await runtime.list_categories(expected_model, section)

    @ready_tool(annotations=read)
    async def enter_category(expected_model: str, section: str, category: str) -> dict:
        """Return unambiguous group-bound controls; this facade does not navigate the UI."""
        return await runtime.enter_category(expected_model, section, category)

    @ready_tool(annotations=edit)
    async def remove_items(expected_model: str, group: str) -> dict:
        """Remove an exact group ID/full type with native clear evidence and per-group readback.

        Mandatory/unknown-removability groups are refused before any removal.
        Timeout/cancellation leaves the session uncertain; do not blindly retry.
        """
        return await runtime.remove_items(expected_model, group)

    @ready_tool(annotations=edit)
    async def apply_custom_item(expected_model: str, filename: str) -> dict:
        """Apply a validated current-format file matching an already registered closet item.

        Copy paths stay in the lab input policy; attached paths may be absolute.
        A project copy needs exact byte/metadata identity with the registered file.
        No registry entries or profile files are created. Native load/deserialization
        and migration checks precede selection; unsupported migrations are refused.
        """
        return await runtime.apply_custom_item(expected_model, filename)

    @ready_tool(annotations=edit)
    async def apply_custom_item_by_key(expected_model: str, key: str) -> dict:
        """Apply a current custom key from search_preset_cache to the expected active model.

        Both session modes require the same live registered file, revisions and bytes.
        """
        return await runtime.apply_custom_item_by_key(expected_model, key)

    @ready_tool(annotations=edit)
    async def set_body_size(expected_model: str, height_cm: PhysicalValue, weight_kg: PhysicalValue | None = None,
                            variant: Literal['F00','M00'] = 'F00') -> dict:
        """Solve silhouette FigureHeight/FigureSlender with live native height feedback.

        F00/M00 requires actual editable gender-specific paired bindings. Global
        proportional scale is zeroed; set_height keeps its existing solver. Weight
        applies the source BMI/waist heuristic, never measured mass. Failures restore
        all snapshotted pairs when native state is known, reporting restoration errors.
        """
        return await runtime.set_body_size(expected_model, height_cm, weight_kg, variant)
