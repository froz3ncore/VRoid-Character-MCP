"""MCP surface for ordinary-edit parts and native VRM export."""
from typing import Literal


def register(ready_tool, runtime, lab, read, edit):
    @ready_tool(annotations=read)
    async def list_parts(expected_model: str) -> dict:
        """List active native model parts with resource IDs and custom/modified flags.

        Includes registered closet custom_items and savable_types. Pass the fresh
        model_token; listed built-in or registered custom IDs work with replace_part.
        """
        return await runtime.list_parts(expected_model)

    @ready_tool(annotations=edit)
    async def replace_part(expected_model: str, part_id: str) -> dict:
        """Replace one built-in or registered closet part using the native loader.

        Registered custom IDs use native custom-item import. Unknown or old-version
        IDs are refused. Relist parts and parameters after replacement.
        Verified copies wait for native PNG callbacks before texture entry.
        Sessions without that decoder keep the conservative cold-reopen guard.
        """
        return await runtime.replace_part(expected_model, part_id)

    @ready_tool(annotations=edit)
    async def save_custom_items(expected_model: str, types: list[str] | None = None) -> dict:
        """Save worn parts as new custom items in the current VRoid profile's closet.

        types selects unique names from list_parts savable_types; None saves all.
        Verifies new files, ZIP integrity, metadata and native closet registration.
        Existing items are never overwritten. Attached mode uses that real
        window's profile and preserves its character file association/dirty flag.
        Partial/uncertain saves are not rolled back; inspect files before retrying.
        """
        return await runtime.save_custom_items(expected_model, types)

    @ready_tool(annotations=edit)
    async def export_vrm(expected_model: str, filename: str, version: Literal[0, 1] = 1,
                         title: str | None = None, author: str | None = None) -> dict:
        """Export the ordinary edit model using its native VRM metadata and settings.

        version 0 exports VRM 0.x, version 1 exports VRM 1.0. A new filename is
        written under lab/saves; existing files are refused. The model's native
        VRM title/name must be set in the model or supplied as title. Optional
        title/author override only the exported metadata; other permissions use
        the model's own settings. Container checks do not establish visual quality.
        """
        return await runtime.export_vrm(expected_model, filename, version, title, author)
