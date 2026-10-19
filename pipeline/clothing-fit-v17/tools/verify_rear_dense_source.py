"""Cold read of saved candidate and baseline; never saves either Blender source."""
import argparse, hashlib, json, sys
from pathlib import Path
import bpy

def read():
    rig=bpy.data.objects['WM_TargetVRoidRig_v01']
    sb=rig.data.vrm_addon_extension.spring_bone1
    meshes={}
    weights={}
    for obj in bpy.data.objects:
        if obj.type!='MESH':continue
        meshes[obj.name]={'co':[list(v.co) for v in obj.data.vertices],
            'faces':[list(p.vertices) for p in obj.data.polygons],
            'uv':[[list(v.uv) for v in uv.data] for uv in obj.data.uv_layers],
            'materials':[m.name if m else None for m in obj.data.materials]}
        weights[obj.name]=[{obj.vertex_groups[g.group].name:g.weight for g in v.groups if g.weight>1e-7} for v in obj.data.vertices]
    return {'meshes':meshes,'weights':weights,
        'images':{i.name:hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in bpy.data.images if i.packed_file},
        'bones':{b.name:{'head':list(b.head_local),'tail':list(b.tail_local),
            'matrix':[list(row) for row in b.matrix_local],'deform':b.use_deform,
            'parent':b.parent.name if b.parent else None} for b in rig.data.bones},
        'springs':{s.vrm_name:{'center':s.center.bone_name,
            'groups':[g.collider_group_uuid for g in s.collider_groups],
            'joints':[{'bone':j.node.bone_name,'stiffness':j.stiffness,'gravity':j.gravity_power,
                'dir':list(j.gravity_dir),'drag':j.drag_force,'radius':j.hit_radius} for j in s.joints]} for s in sb.springs},
        'colliders':len(sb.colliders)}

def main(a):
    candidate=Path(bpy.data.filepath).resolve()
    candidate_hash=hashlib.sha256(candidate.read_bytes()).hexdigest()
    actual=read()
    baseline=a.baseline.resolve()
    baseline_hash=hashlib.sha256(baseline.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(baseline))
    old=read()
    assert old['meshes']==actual['meshes'] and old['images']==actual['images']
    assert all(actual['bones'][name]==bone for name,bone in old['bones'].items())
    assert all(actual['springs'][name]==spring for name,spring in old['springs'].items())
    new_bones=set(actual['bones'])-set(old['bones'])
    expected={'WM_Skirt_%02d_%02d'%(ring,segment) for ring in range(12,16) for segment in range(5)}
    assert new_bones==expected and actual['colliders']==old['colliders']==5
    assert set(actual['springs'])-set(old['springs'])=={'Skirt_%02d'%i for i in range(12,16)}
    changed={}
    for name,vertices in old['weights'].items():
        for index,(prior,after) in enumerate(zip(vertices,actual['weights'][name])):
            if prior==after:continue
            assert all(n.startswith('WM_Skirt_') and int(n.split('_')[2]) in range(4,9) for n in prior)
            assert all(n.startswith('WM_Skirt_') and int(n.split('_')[2]) in (4,5,6,7,8,12,13,14,15) for n in after)
            assert len(after)<=4 and abs(sum(after.values())-1)<1e-5
            changed[name]=changed.get(name,0)+1
    assert hashlib.sha256(candidate.read_bytes()).hexdigest()==candidate_hash
    assert hashlib.sha256(baseline.read_bytes()).hexdigest()==baseline_hash
    result={'cold_source_check_passed':True,'baseline':str(baseline),'baseline_sha256':baseline_hash,
        'candidate':str(candidate),'candidate_sha256':candidate_hash,'geometry_uv_materials_images_unchanged':True,
        'original_bones_springs_unchanged':True,'added_rear_bones':sorted(new_bones),
        'changed_weight_vertices':changed,'springs':len(actual['springs']),
        'joints':sum(len(s['joints']) for s in actual['springs'].values()),'colliders':actual['colliders'],
        'adopted':False,'collision_free':False}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
