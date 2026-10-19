"""Cold source checks plus idempotence, reset and refusal tests on real sleeves."""
import bpy,importlib.util,argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'blender-addons/vroid_xwear_direct'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
fit=load('fit','fit.py');sleeve=load('sleeve','sleeve_gather.py')
p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--gathered',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);profile=json.loads(a.profile.read_text(encoding='utf8'));names={r['mesh'] for r in profile['cuffs']}
assert fit.digest(profile['source_blend'])==profile['source_sha256']
def snapshot():
    return {'meshes':{o.name:fit.fingerprint(o) for o in bpy.data.objects if o.type=='MESH'},
        'images':{i.name:hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in bpy.data.images if i.packed_file},
        'bones':{o.name:[(b.name,b.parent.name if b.parent else None,list(b.head_local),list(b.tail_local)) for b in o.data.bones] for o in bpy.data.objects if o.type=='ARMATURE'}}
bpy.ops.wm.open_mainfile(filepath=profile['source_blend']);before=snapshot();originals={n:sleeve.state(bpy.data.objects[n]) for n in names}
bpy.ops.wm.open_mainfile(filepath=str(a.gathered.resolve()));after=snapshot()
assert before['meshes'].keys()==after['meshes'].keys() and before['images']==after['images'] and before['bones']==after['bones']
assert all(value==after['meshes'][name] for name,value in before['meshes'].items() if name not in names)
results=[]
for cuff in profile['cuffs']:
    obj=bpy.data.objects[cuff['mesh']];old=originals[obj.name];current=sleeve.state(obj)
    assert old['uv']==current['uv'] and old['polygons']==current['polygons'] and len(old['positions'])==len(current['positions'])
    assert json.loads(obj[sleeve.BASE])==old and json.loads(obj[sleeve.PARAMS])['tightness']==profile['parameters']['tightness']
    for v in obj.data.vertices:
        skin=[g for g in v.groups if g.weight>1e-7]
        assert skin and len(skin)<=4 and abs(sum(g.weight for g in skin)-1)<1e-5
    ident=sleeve.fingerprint(obj)
    args=(obj.name,profile['rig'],profile['body_mesh'],cuff['start_bone'],cuff['end_bone'])
    repeated=sleeve.gather_cuff(*args,ident,**profile['parameters']);assert not repeated['changed']
    # Invalid/stale requests must preserve actual positions and weights.
    try:sleeve.gather_cuff(*args,'stale',**profile['parameters'])
    except ValueError:pass
    else:raise AssertionError('Stale geometry was accepted')
    bad=dict(profile['parameters']);bad['tightness']=float('nan')
    try:sleeve.gather_cuff(*args,ident,**bad)
    except ValueError:pass
    else:raise AssertionError('Nonfinite strength was accepted')
    assert sleeve.fingerprint(obj)==ident
    zero=dict(profile['parameters']);zero['tightness']=0.
    sleeve.gather_cuff(*args,ident,**zero);assert sleeve.state(obj)==old
    results.append({'mesh':obj.name,'topology_uv_preserved':True,'parameters_persisted':True,
        'repeat_idempotent':True,'zero_restores_original_geometry_and_weights':True,'invalid_requests_preserve_geometry':True})
sleeve.register();assert bpy.ops.vroid_mcp.gather_sleeve_cuff.get_rna_type();sleeve.unregister()
assert fit.digest(profile['source_blend'])==profile['source_sha256']
result={'passed':True,'mesh_count_unchanged':len(before['meshes']),'other_meshes_unchanged':len(before['meshes'])-len(names),
    'packed_images_unchanged':len(before['images']),'bones_unchanged':True,'source_unchanged':True,'cuffs':results,'gathered_sha256':fit.digest(a.gathered)}
fit.write_new(a.out,result);print('SLEEVE_GATHER_VERIFIED '+json.dumps(result,ensure_ascii=False))
