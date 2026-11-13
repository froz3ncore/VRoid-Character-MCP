from typing import Literal

from pydantic import StrictBool


def register(mcp, transition, destructive):
    @mcp.tool(annotations=destructive)
    async def return_to_main_menu(expected_model: str, discard_unsaved: StrictBool = False) -> dict:
        """Return the active edit model to its native menu. A dirty model requires explicit discard."""
        return await transition('return_to_main_menu', dict(expected_model=expected_model, discard_unsaved=discard_unsaved))

    @mcp.tool(annotations=destructive)
    async def exit_vroid(expected_model: str, discard_unsaved: StrictBool = False, close_attached: StrictBool = False) -> dict:
        """Gracefully exit this exact edit session. An attached real window requires close_attached=true."""
        return await transition('exit_vroid', dict(expected_model=expected_model, discard_unsaved=discard_unsaved,
                                                   close_attached=close_attached))

    @mcp.tool(annotations=destructive)
    async def create_from_menu(expected_menu: str, variant: Literal['F00','M00'] = 'F00',
                               confirm_attached: StrictBool = False) -> dict:
        """Create a template in the same process using its current menu_token. Confirm an attached window."""
        return await transition('create_from_menu', dict(expected_menu=expected_menu, variant=variant, confirm_attached=confirm_attached))

    @mcp.tool(annotations=destructive)
    async def open_from_menu(expected_menu: str, filename: str, confirm_attached: StrictBool = False) -> dict:
        """Open an existing lab saves filename or attached absolute .vroid using the current menu_token."""
        return await transition('open_from_menu', dict(expected_menu=expected_menu, filename=filename, confirm_attached=confirm_attached))
