"""MCP surface for ordinary-edit parts and native VRM export."""
from typing import Literal


def register(ready_tool, runtime, lab, read, edit):
    @ready_tool(annotations=read)
    async def list_parts(expected_model: str) -> dict:
        """List active native model parts with resource IDs and custom/modified flags.

        Pass the fresh model_token. Built-in IDs may be used with replace_part.
        """
        return await runtime.list_parts(expected_model)

    @ready_tool(annotations=edit)
    async def replace_part(expected_model: str, part_id: str) -> dict:
        """Replace one catalog-verified built-in transferable group using native history.

        Closet custom IDs and unknown or old-version IDs are refused because the
        native loader can crash. Relist parts and parameters after replacement.
        A fresh process is required before entering the texture editor afterwards.
        """
        return await runtime.replace_part(expected_model, part_id)

    @ready_tool(annotations=edit)
    async def save_custom_items(expected_model: str, types: list[str] | None = None) -> dict:
        """Unavailable: save worn parts as custom items in VRoid's own interface.

        The native save request has not produced a verifiable saved item in an
        isolated test. This tool refuses before sending any native save request.
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
