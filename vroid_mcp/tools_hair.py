"""Hair authoring tools, plus the read-only native API introspection helpers.

Covers hand-drawn strand control points, shared strand materials, colour
elements and the bone groups. Freehand pen input is not part of this surface:
a strand is created through `edit_hair_structure` and then edited point by point.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .tool_models import HairColorChange

CATEGORIES = ('HairFront', 'HairBack', 'AllHair', 'HairTied', 'HairSideburns', 'HairAhoge', 'HairHanege')
ASSEMBLIES = Literal['VRoid.Studio', 'VRoidCore', 'VRoid.UI', 'UnityEngine.CoreModule', 'VRM10']


def register(ready_tool, runtime, lab, read, edit):
    """Publish the hair authoring and introspection tools."""

    @ready_tool(annotations=read)
    async def list_hair_nodes(category: str = 'HairFront') -> dict:
        """List the groups and strands of one hair category.

        Categories: HairFront, HairBack, AllHair, HairTied, HairSideburns, HairAhoge
        and HairHanege. A returned id is the scope for
        list_parameters(domain='hair', category=...).
        """
        return await runtime.parameter_call('list_hair_nodes', {'category': category})

    @ready_tool(annotations=read)
    async def list_hair_bone_groups(category: str = 'HairFront') -> dict:
        """List the hair physics groups.

        list_parameters(domain='hair_bones', category=...) exposes bone count, root
        rate, stiffness, gravity and radius for them.
        """
        return await runtime.parameter_call('list_hair_bone_groups', {'category': category})

    @ready_tool(annotations=edit)
    async def generate_hair_bones(expected_model: str, category: str = 'HairFront') -> dict:
        """Generate native hair bone groups from the hair_bones/generation parameters.

        Existing grouping can be replaced. Native history can undo it.
        """
        return await runtime.parameter_call('generate_hair_bones',
                                            {'expected_model': expected_model, 'category': category}, True)

    @ready_tool(annotations=edit)
    async def edit_hair_structure(expected_model: str, category: str,
                                  action: Literal['add_procedural', 'add_brush', 'remove'],
                                  node_id: str | None = None) -> dict:
        """Create or remove a hair node.

        add_procedural creates a procedural group, add_brush creates a hand-drawn
        brush group guide, and remove deletes the group or strand identified by
        node_id. Native history can undo it. Hand-drawn strand points are then edited
        with move_hair_strand_point; there is no freehand pen input. Every group id
        is returned so a freshly added node can be found from list_hair_nodes.
        """
        return await runtime.parameter_call('edit_hair_structure',
                                            {'expected_model': expected_model, 'category': category,
                                             'action': action, 'node_id': node_id}, True)

    @ready_tool(annotations=read)
    async def list_hair_strand_points(expected_model: str, category: str, node_id: str) -> dict:
        """List the 3D spine control points of one hand-drawn strand.

        Each entry carries index, point, normal and UV. Read-only. The node id must
        be a strand from list_hair_nodes, not a group.
        """
        return await runtime.parameter_call('list_hair_strand_points',
                                            {'expected_model': expected_model, 'category': category,
                                             'node_id': node_id})

    @ready_tool(annotations=edit)
    async def move_hair_strand_point(expected_model: str, category: str, node_id: str,
                                     index: int = Field(ge=0, le=511),
                                     point: list[float] = Field(min_length=3, max_length=3),
                                     normal: list[float] = Field(default_factory=lambda: [0.0, 1.0, 0.0],
                                                                 min_length=3, max_length=3),
                                     uv: list[float] = Field(default_factory=lambda: [0.0, 0.0],
                                                             min_length=2, max_length=2)) -> dict:
        """Move one control point of a hand-drawn strand (brush strands only).

        point and normal are local-space XYZ floats and uv is a UV pair. Native
        history can undo it. Both the command result and the re-read control point
        are returned; read the strand again with list_hair_strand_points.
        """
        return await runtime.parameter_call('move_hair_strand_point',
                                            {'expected_model': expected_model, 'category': category,
                                             'node_id': node_id, 'index': index, 'point': point,
                                             'normal': normal, 'uv': uv}, True)

    @ready_tool(annotations=read)
    async def list_hair_color_elements(expected_model: str, category: str, node_id: str) -> dict:
        """List the editable COLOR elements found in the model's transferable groups.

        Each entry reports the owning group key, the element key and the transferable
        id, together with the candidate element keys. Use a group key as the address
        argument of set_hair_color. Read-only.
        """
        return await runtime.parameter_call('list_hair_color_elements',
                                            {'expected_model': expected_model, 'category': category,
                                             'node_id': node_id})

    @ready_tool(annotations=edit)
    async def set_hair_color(expected_model: str, category: str, node_id: str,
                             changes: list[HairColorChange] = Field(min_length=1, max_length=8),
                             address: str = Field(min_length=1, max_length=200)) -> dict:
        """Write hair colour elements as RGBA floats in 0..1.

        Use a transferable-group key from list_hair_color_elements as the address.
        Before and after values are returned per change and native history can undo
        the write. A successful write is not proof that the rendered colour changed:
        check the image. For this build the per-group `Level1BaseHair_*` channels read
        back but do not drive the visible hand-drawn render; global hair colour is
        `set_parameters(domain='colors', id='colors/Hair/All')`.
        """
        return await runtime.parameter_call('set_hair_color',
                                            {'expected_model': expected_model, 'category': category,
                                             'node_id': node_id,
                                             'changes': [item.model_dump() for item in changes],
                                             'address': address}, True)

    @ready_tool(annotations=edit)
    async def duplicate_hair_strand(expected_model: str, category: str, node_id: str) -> dict:
        """Duplicate one hand-drawn strand inside its group, which builds hair layering.

        Brush strands only. Native history can undo it. The added node ids are
        returned so the copy can be edited straight away.
        """
        return await runtime.parameter_call('duplicate_hair_strand',
                                            {'expected_model': expected_model, 'category': category,
                                             'node_id': node_id}, True)

    @ready_tool(annotations=read)
    async def list_hair_materials(expected_model: str, category: str = 'HairFront') -> dict:
        """List the shared hair materials with their ids and main colours.

        The list comes from the live material thumbnail collection.
        """
        return await runtime.parameter_call('list_hair_materials',
                                            {'expected_model': expected_model, 'category': category})

    @ready_tool(annotations=edit)
    async def set_hair_material(expected_model: str, category: str, node_id: str,
                                shared_material_id: str = Field(min_length=1, max_length=200)) -> dict:
        """Assign a shared hair material to one group or hand-drawn strand.

        Take the id from list_hair_materials. Native history can undo it. The
        material id is read back after the write; `applied: false` means the
        read-back differs from the request.
        """
        return await runtime.parameter_call('set_hair_material',
                                            {'expected_model': expected_model, 'category': category,
                                             'node_id': node_id, 'shared_material_id': shared_material_id}, True)

    @ready_tool(annotations=read)
    async def inspect_native_api(class_name: str = Field(min_length=1, max_length=160),
                                 assembly: ASSEMBLIES = 'VRoid.Studio',
                                 filter: str | None = Field(default=None, max_length=80)) -> dict:
        """List one managed class's declared methods (with parameter and return types) and typed fields.

        A read-only discovery aid for extending this tool set; caller-supplied code is
        never executed. Pass a substring filter to bound the output, which is capped
        at 400 methods and 200 fields.
        """
        return await runtime.parameter_call('inspect_native_api',
                                            {'class_name': class_name, 'assembly': assembly, 'filter': filter})

    @ready_tool(annotations=read)
    async def search_native_classes(assembly: ASSEMBLIES = 'VRoid.Studio',
                                    substring: str = Field(min_length=3, max_length=80)) -> dict:
        """List full class names in one managed assembly whose name contains a substring.

        The substring needs at least three characters and the result is capped at 100
        matches. Read-only: use it to find the exact name for inspect_native_api.
        """
        return await runtime.parameter_call('search_native_classes',
                                            {'assembly': assembly, 'substring': substring})
