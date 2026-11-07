"""Offline cache tools register without the app-start decorator."""
import json
from typing import Annotated, Literal

from mcp.server.fastmcp import Image
from mcp.types import ImageContent, TextContent
from pydantic import Field, StrictBool, StrictInt

from .preset_catalog import PresetCatalog

Number = Annotated[float, Field(strict=True)]


def register(mcp, ready_tool, runtime, lab, read, edit):
    store=PresetCatalog(lab/'preset_cache')

    @ready_tool(annotations=read)
    async def vroid_measure(expected_model: str) -> dict:
        """Read current owned model bounds/enabled renderer count and optional scoped humanoid landmarks.

        Reports native height separately from renderer vertical extent and the
        source's ground-dependent maxY*100 convention. Does not capture an image.
        """
        return await runtime.measure_model(expected_model)

    @ready_tool(annotations=edit, owned_disposable=True)
    async def build_preset_thumbnails(expected_model: str, category: str,
                                      disposable_model: StrictBool=False, refresh: StrictBool=False,
                                      limit: Annotated[int,Field(strict=True,ge=1,le=20000)] | None=None) -> dict:
        """Strip native removable slots and capture tested resources in an explicitly disposable owned copy.

        Saves a unique restoration snapshot first. Restores only when native
        work and ownership remain known; returns a fresh token and restoration
        evidence. Undo history, original dirty/file association and neutral
        anatomy are not preserved guarantees. Failed rows are never published.
        """
        return await runtime.build_preset_thumbnails(expected_model,category,disposable_model,refresh,limit)

    @mcp.tool(annotations=read)
    async def search_preset_cache(query: str='', category: str | None=None, kind: Literal['builtin','custom'] | None=None,
                                  annotated_only: StrictBool=False, include_locked: StrictBool=False, status: str | None=None,
                                  include_removed: StrictBool=False, limit: StrictInt=50,
                                  owned: StrictBool | None=None) -> list[dict]:
        """Search offline with ALL query words and exact combined filters; never starts VRoid.

        owned=None keeps either ownership; true/false is an independent exact
        predicate applied before limit. include_locked controls usability only.
        """
        return store.search(query,category,kind,annotated_only,include_locked,status,include_removed,limit,owned)

    @mcp.tool(annotations=edit)
    async def annotate_preset_cache(key: str, author: str, label: str | None=None, description: str | None=None,
                                    tags: list[str] | None=None, colors: list[str] | None=None, replace: StrictBool=False) -> dict:
        """Annotate offline; manual label wins. Append tags/colors, or replace including empty lists."""
        return store.annotate(key,author,label,description,tags,colors,replace)

    @ready_tool(annotations=read)
    async def sync_preset_cache(expected_model: Annotated[str,Field(strict=True,min_length=1,max_length=1024,pattern=r'\S')],
                                icons: StrictBool=False,
                                icon_limit: Annotated[int,Field(strict=True,ge=1,le=200)] | None=None) -> dict:
        """Synchronize bounded full native selectable/catalog streams and observed registered custom items.

        Requires a fresh model token. Partial custom observation preserves missing
        records as unknown. Icons require fresh owned selectable identity, use
        native-icon provenance and are bounded to 1..200 (default 50) per call.
        """
        return await runtime.sync_preset_cache(expected_model,icons,icon_limit)

    @mcp.tool(annotations=read, structured_output=False)
    async def preset_thumbnail(key: str) -> list[TextContent | ImageContent]:
        """Read a verified offline PNG with actual situation/native-icon provenance; never starts VRoid."""
        metadata,data=store.resolve_image(key)
        return [TextContent(type='text',text=json.dumps(metadata,ensure_ascii=False)),
                Image(data=data,format='png').to_image_content()]

    @mcp.tool(annotations=read)
    async def get_preset_framing(category: str | None=None) -> dict:
        """Read immutable category defaults plus local overrides without starting VRoid.

        top/bottom are downward model-height fractions, half is horizontal
        half-width/model-height (null=projected bounds), distance multiplies
        region span, yaw is degrees. Full-body makes top/bottom/half inactive.
        """
        return store.get_framing(category)

    @mcp.tool(annotations=edit)
    async def set_preset_framing(category: str, top: Number | None=None, bottom: Number | None=None,
                                distance: Number | None=None, yaw: Number | None=None,
                                fit: Literal['region','full-body'] | None=None,
                                half: Number | None=None, clear_half: StrictBool=False) -> dict:
        """Persist category override offline. clear_half=true selects full projected width.

        Preserve requested regional fields for full-body, where capture must
        contain all projected model-bound corners. 0<=top<bottom<=1,
        0<half<=1, .1<=distance<=100, -360<=yaw<=360. Capture reports any
        effective distance adjustment needed for full-body containment.
        """
        fields={k:v for k,v in dict(top=top,bottom=bottom,distance=distance,yaw=yaw,fit=fit,half=half).items() if v is not None}
        if clear_half:
            if half is not None: raise ValueError('HALF_AND_CLEAR_HALF_CONFLICT')
            fields['half']=None
        return store.set_framing(category,**fields)

    @mcp.tool(annotations=edit)
    async def reset_preset_framing(category: str | None=None) -> dict:
        """Remove one/all local framing overrides offline, preserving committed defaults."""
        return store.reset_framing(category)
