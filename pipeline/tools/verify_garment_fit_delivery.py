"""Cold compare a planned copy against every mesh/image/bone in its source."""
import argparse,bpy,hashlib,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fit_backend',ROOT/'blender-addons/vroid_xwear_direct/fit.py')
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--fitted',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);plan=json.loads(a.plan.read_text(encoding='utf8'))
source=Path(plan['source_blend']);assert fit.digest(source)==plan['source_sha256']
def snapshot():
    meshes={o.name:{'full':fit.fingerprint(o),'skin_uv_topology':fit.fingerprint(o,False),
        'positions':[list(v.co) for v in o.data.vertices]} for o in bpy.data.objects if o.type=='MESH'}
    images={i.name:hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in bpy.data.images if i.packed_file}
    rigs={o.name:[{'name':b.name,'parent':b.parent.name if b.parent else None,'head':list(b.head_local),
                   'tail':list(b.tail_local),'matrix':[list(r) for r in b.matrix_local]} for b in o.data.bones] for o in bpy.data.objects if o.type=='ARMATURE'}
    return meshes,images,rigs
bpy.ops.wm.open_mainfile(filepath=str(source));before,images,rigs=snapshot()
bpy.ops.wm.open_mainfile(filepath=str(a.fitted.resolve()));after,newimages,newrigs=snapshot()
assert before.keys()==after.keys() and images==newimages and rigs==newrigs
changed=0
for name,old in before.items():
    new=after[name];assert old['skin_uv_topology']==new['skin_uv_topology']
    expected={r['vertex']:r['position'] for r in plan['changes'].get(name,[])}
    assert len(old['positions'])==len(new['positions'])
    for i,(prior,actual) in enumerate(zip(old['positions'],new['positions'])):
        target=expected.get(i,prior)
        assert max(abs(x-y) for x,y in zip(target,actual))<1e-7
        if i in expected:changed+=1
assert fit.digest(source)==plan['source_sha256']
result={'passed':True,'source_unchanged':True,'meshes_compared':len(before),'packed_images_compared':len(images),
        'armatures_compared':len(rigs),'changed_vertices':changed,'all_other_vertices_uv_weights_topology_images_bones_unchanged':True,
        'fitted':str(a.fitted.resolve()),'fitted_sha256':fit.digest(a.fitted)}
fit.write_new(a.out,result);print('GARMENT_FIT_COLD_VERIFICATION '+json.dumps(result))
