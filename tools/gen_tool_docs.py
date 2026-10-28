"""Generate the current tool reference from the live tool schemas.

The reference must not drift from the code, so it is generated rather than
hand-written: names, parameter order, required flags, defaults, types and
annotations all come from the same FastMCP objects the server exposes, and
each entry carries the tool's own docstring, which states prerequisites and
failure modes.

    python tools/gen_tool_docs.py --out <scratch>/TOOLS.md
    python tools/gen_tool_docs.py            # writes tools/TOOLS.md

This interpreter cannot always write inside the repository, so on failure use
--out with a scratch path and copy the file in.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import typing

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from vroid_mcp import toolset  # noqa: E402
from vroid_mcp import __version__  # noqa: E402
from vroid_mcp.server import create_server  # noqa: E402

DOMAINS = [
    ('Session and status', ['restart_session', 'get_status', 'attach_open_vroid', 'detach_open_vroid',
                            'get_attached_state', 'acknowledge_attached_state']),
    ('Parameters, presets and saving', ['list_parameters', 'set_parameters', 'list_presets', 'preview_presets',
                                        'apply_preset', 'list_face_params', 'set_face_params', 'list_body_params',
                                        'set_body_params', 'list_clothing_params', 'set_clothing_params',
                                        'list_hair_presets', 'apply_hair_preset', 'list_clothing_presets',
                                        'apply_clothing_preset', 'list_shoe_templates', 'add_shoe_template',
                                        'get_height', 'set_height', 'undo', 'redo', 'save_as', 'open_character',
                                        'save_character', 'save_character_as', 'new_character',
                                        'list_parts', 'replace_part', 'save_custom_items', 'export_vrm']),
    ('Hair authoring', ['list_hair_nodes', 'list_hair_bone_groups', 'generate_hair_bones', 'edit_hair_structure',
                        'list_hair_strand_points', 'move_hair_strand_point', 'duplicate_hair_strand',
                        'list_hair_color_elements', 'set_hair_color', 'list_hair_materials', 'set_hair_material']),
    ('Accessories, expressions and preview', ['list_accessory_templates', 'list_accessories', 'edit_accessories',
                                              'list_expressions', 'set_preview_mode', 'set_photo_camera',
                                              'preview_expression']),
    ('Capture and review', ['screenshot', 'capture_review', 'capture_body_reference']),
    ('Texture and makeup', ['inspect_texture_renderers', 'list_texture_regions', 'list_texture_layers',
                            'open_texture_editor', 'inspect_texture_canvas', 'close_texture_editor',
                            'export_texture_layer', 'export_texture_guide', 'export_texture_surface',
                            'import_texture_layer', 'set_texture_layer_state', 'rename_texture_layer',
                            'delete_texture_layer', 'reorder_texture_layers', 'set_texture_layer_blend',
                            'export_renderer_texture', 'pick_texture_uv',
                            'export_nail_uv_map', 'capture_texture_detail', 'export_makeup_region_mask',
                            'preview_makeup_marks', 'paint_makeup_marks']),
    ('Dress-up (wear) assembly', ['get_wear_status', 'open_wear_project', 'open_current_in_wear', 'import_xwear', 'get_wear_snapshot',
                                  'set_wear_fit', 'inspect_wear_body_occlusion', 'set_wear_body_occlusion',
                                  'inspect_wear_native_shoes', 'set_wear_native_shoes_visible',
                                  'inspect_wear_fit_context', 'capture_wear_reference', 'capture_wear_review',
                                  'capture_wear_motion', 'list_wear_preview_clips', 'select_wear_preview_clip',
                                  'hold_wear_preview_pose', 'sample_wear_preview_rig', 'pose_wear_preview_legs',
                                  'set_wear_animation', 'save_wear_project', 'export_wear_vrm']),
    ('Native introspection', ['inspect_native_api', 'search_native_classes']),
]


def _type_name(schema: dict) -> str:
    if not isinstance(schema, dict):
        return 'any'
    if '$ref' in schema:
        return str(schema['$ref']).rsplit('/', 1)[-1]
    for key in ('anyOf', 'oneOf'):
        if key in schema:
            return ' | '.join(_type_name(part) for part in schema[key])
    if schema.get('type') == 'array':
        return 'list[' + _type_name(schema.get('items', {})) + ']'
    return str(schema.get('type', 'any'))


def _default(schema: dict) -> str:
    for part in ([schema] + list(schema.get('anyOf') or []) + list(schema.get('oneOf') or [])):
        if 'default' in part:
            value = part['default']
            return json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else f"`{value}`"
    return ''


def _annotations(tool) -> str:
    if not tool.annotations:
        return 'edit'
    labels = []
    for name, label in (('readOnlyHint', 'read-only'), ('destructiveHint', 'destructive'),
                        ('idempotentHint', 'idempotent'), ('openWorldHint', 'open-world')):
        if getattr(tool.annotations, name, None):
            labels.append(label)
    return ', '.join(labels) or 'edit'


def render(tools: list) -> str:
    base = toolset.fingerprint(tools)
    by_name = {tool.name: tool for tool in tools}
    lines = ['# VRoid Character MCP — tool reference', '',
             f'Generated by `tools/gen_tool_docs.py` from the live schemas. '
             f'**{base["tool_count"]} tools**, `{base["toolset_hash"]}`.', '',
             f'Source version: **{__version__}**. Release and acceptance status: [SCOPE.md](../SCOPE.md). '
             'Session ownership and restrictions: [ATTACHED_SESSION.md](../ATTACHED_SESSION.md).', '',
             'Every entry lists the parameter order the server publishes, which parameters are required, '
             'the published default, the tool annotations, and the tool description. Descriptions carry the '
             'preconditions and failure modes that matter. Native batches can report partial applied changes; '
             'inspect those results and never blindly retry an uncertain edit.', '',
             'Regenerate after changing a tool:', '',
             '~~~powershell',
             'python tools/gen_tool_docs.py --out <scratch>/TOOLS.md   # then copy to tools/TOOLS.md',
             'powershell -NoProfile -File tools/run_checks.ps1 -Manifest # checks schemas and source',
             '~~~', '',
             '## Contents', '']
    covered = []
    for title, names in DOMAINS:
        present = [name for name in names if name in by_name]
        covered += present
        anchor = title.lower().replace(' ', '-').replace(',', '').replace('(', '').replace(')', '')
        lines.append(f'- [{title}](#{anchor}) — {len(present)} tools')
    extra = [name for name in sorted(by_name) if name not in covered]
    if extra:
        lines.append(f'- [Unclassified](#unclassified) — {len(extra)} tools')
    lines.append('')

    def section(title: str, names: list[str]) -> None:
        lines.extend([f'## {title}', ''])
        for name in names:
            tool = by_name[name]
            schema = tool.inputSchema or {}
            props = schema.get('properties') or {}
            required = set(schema.get('required') or [])
            lines.append(f'### `{name}`')
            lines.append('')
            lines.append(f'- annotations: {_annotations(tool)}')
            if props:
                lines.append('- parameters:')
                for param, prop in props.items():
                    flag = '**required**' if param in required else 'optional'
                    default = _default(prop)
                    suffix = f', default {default}' if default else ''
                    lines.append(f'  - `{param}` — {_type_name(prop)} ({flag}{suffix})')
            else:
                lines.append('- parameters: none')
            description = (tool.description or '').strip()
            if description:
                lines.append('')
                for paragraph in description.split('\n'):
                    lines.append(paragraph.strip())
            lines.append('')

    for title, names in DOMAINS:
        present = [name for name in names if name in by_name]
        if present:
            section(title, present)
    if extra:
        section('Unclassified', extra)
    return '\n'.join(lines).rstrip() + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate the tool reference')
    parser.add_argument('--out', default=str(PROJECT / 'tools' / 'TOOLS.md'))
    args = parser.parse_args()
    server = create_server(PROJECT / 'lab', 'F00', None)
    tools = asyncio.run(server.list_tools())
    text = render(tools)
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    print(f'wrote {target} ({len(tools)} tools, {len(text)} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
