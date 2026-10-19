import bpy,argparse,importlib.util,json,sys,hashlib,zipfile
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fit',ROOT/'blender-addons/vroid_xwear_direct/fit.py')
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--copy',type=Path,required=True)
p.add_argument('--source-package',type=Path,required=True);p.add_argument('--package',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);profile=json.loads(a.profile.read_text(encoding='utf8'))
def snapshot():
    rig=bpy.data.objects[profile['rig']];sb=rig.data.vrm_addon_extension.spring_bone1
    return {'meshes':{o.name:fit.fingerprint(o) for o in bpy.data.objects if o.type=='MESH'},
        'images':{i.name:hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in bpy.data.images if i.packed_file},
        'bones':[(b.name,b.parent.name if b.parent else None,list(b.head_local),list(b.tail_local)) for b in rig.data.bones],
        'colliders':[c.uuid for c in sb.colliders],
        'springs':{s.vrm_name:{'groups':[g.collider_group_uuid for g in s.collider_groups],
            'joints':[(j.node.bone_name,j.hit_radius,j.stiffness,j.gravity_power,j.drag_force,list(j.gravity_dir)) for j in s.joints]} for s in sb.springs},
        'sleeves':{o.name:{k:o.get(k) for k in ('vroid_sleeve_gather_baseline_v1','vroid_sleeve_gather_last_hash','vroid_sleeve_gather_parameters')} for o in bpy.data.objects if 'vroid_sleeve_gather_parameters' in o}}
assert fit.digest(profile['source_blend'])==profile['source_sha256']
bpy.ops.wm.open_mainfile(filepath=profile['source_blend']);before=snapshot()
bpy.ops.wm.open_mainfile(filepath=str(a.copy.resolve()));after=snapshot()
for key in ('meshes','images','bones','sleeves'):assert before[key]==after[key],key
assert after['colliders'][:len(before['colliders'])]==before['colliders'] and len(after['colliders'])==9
for name,old in before['springs'].items():
    new=after['springs'][name]
    if name not in profile['rear_springs']:assert old==new
    else:
        for index,(oldj,newj) in enumerate(zip(old['joints'],new['joints'])):
            expected=oldj[1] if index==0 and profile.get('preserve_root_radius',False) else profile['joint_hit_radius_m']
            assert oldj[0]==newj[0] and oldj[2:]==newj[2:] and abs(newj[1]-expected)<1e-6
def binary_payloads(path):
    with zipfile.ZipFile(path) as archive:
        return Counter(hashlib.sha256(archive.read(info)).hexdigest() for info in archive.infolist() if info.orig_filename.replace('\\','/').startswith(('Mesh/','Textures/')))
original=binary_payloads(a.source_package);assert original==binary_payloads(a.package)
result={'passed':True,'all_meshes_unchanged':len(before['meshes']),'packed_images_unchanged':len(before['images']),
        'rest_bones_and_sleeve_parameters_unchanged':True,'front_and_ribbon_springs_unchanged':True,
        'binary_mesh_texture_payloads_unchanged':sum(original.values()),'colliders':len(after['colliders']),
        'source_unchanged':fit.digest(profile['source_blend'])==profile['source_sha256'],'copy_sha256':fit.digest(a.copy)}
fit.write_new(a.out,result);print('REAR_CONTACT_COLD_VERIFICATION '+json.dumps(result))
