"""Analytic Blender tests: plane penetration, bounds, identity and safe copies."""
import bpy,importlib.util,json,hashlib,sys,math
from pathlib import Path
from mathutils import Matrix
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(sys.argv[sys.argv.index('--out')+1]).resolve() if '--out' in sys.argv else ROOT/'work/garment-fit-tests-v01'
OUT.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('fit_backend',ROOT/'blender-addons/vroid_xwear_direct/fit.py')
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
arm=bpy.data.armatures.new('TestRig');rig=bpy.data.objects.new('TestRig',arm);bpy.context.collection.objects.link(rig)
rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
bone=arm.edit_bones.new('Root');bone.head=(0,0,0);bone.tail=(0,1,0)
bpy.ops.object.mode_set(mode='OBJECT')
mesh=bpy.data.meshes.new('TestGarment');mesh.from_pydata([(-.1,.3,-.002),(.1,.3,-.002),(0,.5,-.002)],[],[(0,1,2)])
obj=bpy.data.objects.new('TestGarment',mesh);bpy.context.collection.objects.link(obj)
uv=mesh.uv_layers.new();obj.vertex_groups.new(name='Root').add([0,1,2],1,'REPLACE')
mod=obj.modifiers.new('Skin','ARMATURE');mod.object=rig
source=OUT/'source.blend';bpy.ops.wm.save_as_mainfile(filepath=str(source))
profile={'schema':fit.SCHEMA,'source_blend':str(source),'source_sha256':fit.digest(source),'rig':rig.name,'meshes':[obj.name],
 'coordinate_matrix':[list(r) for r in Matrix.Identity(4)],'source_height_range_m':[.2,.6],
 'limits':{'clearance_m':.004,'inside_threshold_m':.001,'max_surface_distance_m':.12,'max_displacement_m':.01,'iterations':6},'references':[]}
mapping,uvs=fit.export_map(obj,Matrix.Identity(4))
garment={'name':obj.name,'positions':[list(mesh.vertices[i].co) for i in mapping],'source_positions':[list(mesh.vertices[i].co) for i in mapping],
 'uv0':[list(u) for u in uvs],'world_matrix':[list(r) for r in Matrix.Identity(4)],'bone_ids':[0],
 'bindposes':[[list(r) for r in Matrix.Identity(4)]],'triangles':[0,1,2],
 'weights':[{'indices':[0,0,0,0],'weights':[1,0,0,0]} for _ in mapping]}
body={'positions':[[-2,-2,0],[2,-2,0],[2,2,0],[-2,2,0]],'normals':[[0,0,1]]*4,'triangles':[0,1,2,0,2,3],'world_matrix':[list(r) for r in Matrix.Identity(4)]}
data={'schema':'vroid-wear-reference-v1','pose_source':'native_preview','frame':1,'selected_preview_clip':{'name':'analytic_plane'},
 'body':body,'garments':[garment],'bones':[{'name':'Root','world_matrix':[list(r) for r in Matrix.Identity(4)]}]}
ref=OUT/'native.json';ref.write_text(json.dumps(data),encoding='utf8')
profile['references']=[{'label':'analytic','path':str(ref),'sha256':fit.digest(ref)}]
pp=OUT/'profile.json';pp.write_text(json.dumps(profile),encoding='utf8')
before=fit.fingerprint(obj);plan=OUT/'plan.json'
result=fit.plan_fit(pp,plan,solve=True)
assert result['before'][0]['inside']=={'vertex':3,'face':1,'edge':3}
assert result['predicted_after'][0]['inside']=={} and result['max_displacement_m']<=.01+1e-6
assert fit.fingerprint(obj)==before and fit.digest(source)==profile['source_sha256']
saved=fit.apply_fit(plan,OUT/'fitted.blend');assert saved['saved'] and fit.fingerprint(obj)==before
checks=4
def rejects(action,match):
    global checks
    try:action()
    except ValueError as error:assert match in str(error),(match,str(error));checks+=1
    else:raise AssertionError('Expected refusal: '+match)
rejects(lambda:fit.apply_fit(plan,OUT/'fitted.blend'),'new .blend')
original=ref.read_bytes();ref.write_text('{}',encoding='utf8')
rejects(lambda:fit.plan_fit(pp,OUT/'bad-ref.json',True),'reference changed');ref.write_bytes(original)
bad=json.loads(plan.read_text());bad['changes'][obj.name][0]['position'][2]=1.
badpath=OUT/'unbounded.json';badpath.write_text(json.dumps(bad),encoding='utf8')
rejects(lambda:fit.apply_fit(badpath,OUT/'bad.blend'),'displacement bound')
assert not (OUT/'bad.blend').exists() and fit.fingerprint(obj)==before
bad['changes'][obj.name][0]['position'][2]=float('nan');badpath.write_text(json.dumps(bad),encoding='utf8')
rejects(lambda:fit.apply_fit(badpath,OUT/'nan.blend'),'Nonfinite')
assert fit.fingerprint(obj)==before
bad=json.loads(plan.read_text());bad['quality_gate']['accepted']=False;badpath.write_text(json.dumps(bad),encoding='utf8')
rejects(lambda:fit.apply_fit(badpath,OUT/'rejected.blend'),'quality gate')
data['garments'][0]['source_positions'][0][0]+=.01
ref2=OUT/'wrong-source.json';ref2.write_text(json.dumps(data),encoding='utf8')
profile2=json.loads(pp.read_text());profile2['references']=[{'label':'wrong','path':str(ref2),'sha256':fit.digest(ref2)}]
pp3=OUT/'wrong-source-profile.json';pp3.write_text(json.dumps(profile2),encoding='utf8')
rejects(lambda:fit.plan_fit(pp3,OUT/'wrong-source-plan.json',True),'correspondence failed')
profile3=json.loads(pp.read_text());profile3['coordinate_matrix'][0][0]=float('nan')
pp4=OUT/'nonfinite-matrix.json';pp4.write_text(json.dumps(profile3),encoding='utf8')
rejects(lambda:fit.inspect_binding(pp4),'coordinate matrix')
data2=json.loads(original);data2['bones'][0]['name']='WrongBone'
ref3=OUT/'wrong-skin.json';ref3.write_text(json.dumps(data2),encoding='utf8')
profile4=json.loads(pp.read_text());profile4['references']=[{'label':'wrong-skin','path':str(ref3),'sha256':fit.digest(ref3)}]
pp5=OUT/'wrong-skin-profile.json';pp5.write_text(json.dumps(profile4),encoding='utf8')
rejects(lambda:fit.plan_fit(pp5,OUT/'wrong-skin-plan.json',True),'skin weight correspondence')
# A conflicting pose can never move beyond the configured rest-space bound.
profile['limits']['max_displacement_m']=.001;pp2=OUT/'small-bound.json';pp2.write_text(json.dumps(profile),encoding='utf8')
small=fit.plan_fit(pp2,OUT/'small-plan.json',True)
assert small['max_displacement_m']<=.001+1e-6 and small['predicted_after'][0]['inside']
assert not small['quality_gate']['accepted'] and small['moved_vertices']==0
checks+=1
fit.register();assert bpy.ops.vroid_mcp.plan_garment_fit.get_rna_type();fit.unregister();checks+=1
(OUT/'test-results.json').write_text(json.dumps({'passed':True,'checks':checks,'source_unchanged':True,'coordinates_restored':True}),encoding='utf8')
print('GARMENT_FIT_TESTS_OK',checks)
