"""Refine only four rear radial intervals; preserve all geometry and textures."""
import argparse,importlib.util,json,sys
from collections import defaultdict
from pathlib import Path
import bpy
from mathutils import Matrix
ROOT=Path(__file__).resolve().parents[1]

def build(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    assert Path(bpy.data.filepath).resolve()==source and not bpy.data.is_dirty and not out.exists()
    assert out.is_relative_to(ROOT/'projects/whale-maid')
    spec=importlib.util.spec_from_file_location('fit',ROOT/'blender-addons/vroid_xwear_direct/fit.py');fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
    spec=importlib.util.spec_from_file_location('xwear',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    original=fit.digest(source);rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1
    assert len(sb.springs)==14 and len(sb.colliders)==5
    def geometry():
        return {o.name:{'positions':[list(v.co) for v in o.data.vertices],'faces':[list(p.vertices) for p in o.data.polygons],
            'uv':[[list(v.uv) for v in uv.data] for uv in o.data.uv_layers]} for o in bpy.data.objects if o.type=='MESH'}
    before=geometry()
    import hashlib
    images={i.name:hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in bpy.data.images if i.packed_file}
    for obj in bpy.context.selected_objects:obj.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        for lower in range(4,8):
            new_index=lower+8
            for segment in range(5):
                a,b=(rig.data.edit_bones['WM_Skirt_%02d_%02d'%(ring,segment)] for ring in (lower,lower+1))
                bone=rig.data.edit_bones.new('WM_Skirt_%02d_%02d'%(new_index,segment))
                bone.head=(a.head+b.head)*.5;bone.tail=(a.tail+b.tail)*.5;bone.roll=(a.roll+b.roll)*.5
                bone.use_deform=segment<4
                bone.parent=rig.data.edit_bones['J_Bip_C_Hips'] if segment==0 else rig.data.edit_bones['WM_Skirt_%02d_%02d'%(new_index,segment-1)]
    finally:bpy.ops.object.mode_set(mode='OBJECT')
    originals={s.vrm_name:s for s in sb.springs}
    for lower in range(4,8):
        spring=sb.add_spring();spring.vrm_name='Skirt_%02d'%(lower+8)
        prior=originals['Skirt_%02d'%lower]
        for group in prior.collider_groups:spring.add_collider_group().collider_group_uuid=group.collider_group_uuid
        for i,j in enumerate(prior.joints):
            joint=spring.add_joint();joint.node.bone_name='WM_Skirt_%02d_%02d'%(lower+8,i)
            for field in ('stiffness','gravity_power','drag_force','hit_radius','gravity_dir'):setattr(joint,field,getattr(j,field))
    changed={}
    for obj in bpy.data.collections['FITTED_服装工作副本'].all_objects:
        if obj.type!='MESH':continue
        for vertex in obj.data.vertices:
            weights={obj.vertex_groups[g.group].name:g.weight for g in vertex.groups if g.weight>1e-7}
            if not weights or any(not n.startswith('WM_Skirt_') for n in weights):continue
            rings=defaultdict(float)
            for n,w in weights.items():rings[int(n.split('_')[2])]+=w
            keys=sorted(rings)
            if len(keys)!=2 or keys[1]!=keys[0]+1 or keys[0] not in range(4,8):continue
            lower=keys[0];mix=rings[keys[1]]/sum(rings.values())
            radial=[(lower,1-2*mix),(lower+8,2*mix)] if mix<=.5 else [(lower+8,2-2*mix),(lower+1,2*mix-1)]
            q=sum(w*int(n.rsplit('_',1)[1]) for n,w in weights.items());index=int(q);fraction=q-index
            new=defaultdict(float)
            for ring,rw in radial:
                for segment,lw in [(index,1-fraction),(min(index+1,3),fraction)]:new['WM_Skirt_%02d_%02d'%(ring,segment)]+=rw*lw
            new={n:w for n,w in new.items() if w>1e-7};assert len(new)<=4 and abs(sum(new.values())-1)<1e-5
            for g in list(vertex.groups):obj.vertex_groups[g.group].remove([vertex.index])
            for name,w in new.items():
                group=obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name);group.add([vertex.index],w,'REPLACE')
            changed[obj.name]=changed.get(obj.name,0)+1
    sb.fixup();assert geometry()==before
    assert images=={i.name:hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in bpy.data.images if i.packed_file}
    out.mkdir(parents=True,exist_ok=False);target=out/'whale_maid_rear_dense_v03.blend'
    old=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        assert 'FINISHED' in bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=old
    meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(meshes)==69
    enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for pose in rig.pose.bones:pose.matrix_basis.identity()
        bpy.context.view_layer.update();package=out/'whale_maid_rear_dense_v03.xwear'
        manifest=exporter.export_xwear(package,rig,meshes,item_name='Rear radial refinement experiment',author='Local test asset',coordinate_matrix=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1))))
        manifest.update(source_blend=str(target),source_sha256=fit.digest(target),experimental=True)
        fit.write_new(package.with_suffix('.xwear.json'),manifest)
    finally:
        for pose in rig.pose.bones:pose.matrix_basis=poses[pose.name]
        sb.enable_animation=enabled
    report={'source':str(source),'source_sha256':original,'copy':str(target),'copy_sha256':fit.digest(target),
        'added_rear_chains':4,'added_joints':20,'changed_weight_vertices':changed,'geometry_and_textures_unchanged':True,
        'package':str(package),'native_acceptance':False,'adopted':False}
    fit.write_new(out/'build.json',report);assert fit.digest(source)==original;return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);print(json.dumps(build(a.source,a.out),ensure_ascii=False))
