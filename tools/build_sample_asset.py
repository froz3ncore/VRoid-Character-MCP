"""Run in a new background Blender process to build an original diagnostic badge.

blender --background --factory-startup --disable-autoexec --python tools/build_sample_asset.py -- --out <new-dir>
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    exporter_path = repo / 'pipeline/blender-addons/vroid_xwear_direct/__init__.py'
    spec = importlib.util.spec_from_file_location('sample_xwear_exporter', exporter_path)
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)

    # This process starts from factory settings. Only its own default objects
    # are removed; the user's live Blender process is never contacted.
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    data = bpy.data.armatures.new('SampleRig')
    rig = bpy.data.objects.new('SampleRig', data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    hips = data.edit_bones.new('Hips')
    hips.head, hips.tail = (0, .9, 0), (0, 1.0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')
    data.pose_position = 'REST'

    # Coordinates are native +Y up / +Z front, exported with an identity basis.
    # This simple off-centre block tests skinning/import, not anatomical fit.
    bpy.ops.mesh.primitive_cube_add(size=.08, location=(.23, .95, .18))
    mesh = bpy.context.object
    mesh.name = 'MCP_sample_badge'
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    group = mesh.vertex_groups.new(name='Hips')
    group.add(list(range(len(mesh.data.vertices))), 1, 'REPLACE')
    modifier = mesh.modifiers.new('Sample skin', 'ARMATURE')
    modifier.object = rig
    material = bpy.data.materials.new('Sample orange')
    material.diffuse_color = (.9, .25, .04, 1)
    material.use_nodes = True
    material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = material.diffuse_color
    mesh.data.materials.append(material)
    assert mesh.data.uv_layers.active
    blend = out / 'sample-badge.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    xwear = out / 'sample-badge.xwear'
    exported = exporter.export_xwear(xwear, rig, [mesh], item_name='MCP sample badge',
                                     author='VRoid Character MCP contributors',
                                     coordinate_matrix=Matrix.Identity(4))
    report = {'schema': 'vroid-public-sample-asset-v1', 'blender': bpy.app.version_string,
              'original_geometry': True, 'third_party_assets': False,
              'purpose': 'Diagnostic rigid accessory, not finished character clothing',
              'asset_license': 'MIT', 'mesh': {'vertices': len(mesh.data.vertices),
              'triangles': 12, 'bones': 1}, 'export': exported,
              'files': {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                                'bytes': p.stat().st_size} for p in (blend, xwear)},
              'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'exporter_sha256': hashlib.sha256(exporter_path.read_bytes()).hexdigest()}
    (out / 'asset.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print('SAMPLE_ASSET_CREATED ' + str(xwear))


if __name__ == '__main__':
    main()
