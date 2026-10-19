"""Extend only custom shoe quarters/outsoles around the measured native feet.

This preserves the source design, topology and UVs. It is a limited enclosure
candidate, not a high-heel posture or all-surface collision fix.
"""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):
    with p.open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
def smooth(x):
    x=max(0.,min(1.,x));return x*x*(3-2*x)
def build(a):
    source=Path(bpy.data.filepath).resolve();sha=digest(source);previous=json.loads((source.parent/'build.json').read_text(encoding='utf8'))
    assert previous['copy_sha256']==sha and not bpy.data.is_dirty
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists()
    raw=json.loads(a.reference.read_text(encoding='utf8'));assert raw['pose_source']=='native_edit'
    sys.path.insert(0,str(ROOT/'VRoid-MCP'));from vroid_mcp.wear_fit import selected_surface,bounds
    feet,bones=selected_surface(raw,'feet');rig=bpy.data.objects['WM_TargetVRoidRig_v01']
    check=load('shoe_scope',ROOT/'tools/verify_rear_mirror_sources.py');before=check.read();rows=[]
    for obj in bpy.data.collections['FITTED_服装工作副本'].all_objects:
        if not obj.name.startswith('FIT_ACCESSORY_Shoe_'):continue
        side=obj.name.split('_')[3];bone='J_Bip_'+side+'_Foot';sign=1 if side=='R' else -1
        origin=Vector([r[3] for r in bones[bone]['world_matrix'][:3]])
        source_bone=C@rig.matrix_world@rig.data.bones[bone].matrix_local@C.inverted()
        assert (source_bone.translation-origin).length<2e-5,'Recalibrate source against this actual foot before fitting'
        to_native=C@obj.matrix_world;inverse=to_native.inverted();old=[to_native@v.co for v in obj.data.vertices];maximum=0.
        for vertex,p in zip(obj.data.vertices,old):
            q=p.copy()
            # Preserve the vamp/instep opening. Extend the rear quarter locally,
            # add lateral clearance, and lower only the lowest outsole band.
            q.z-=.016*smooth((.030-p.z)/.0965)
            q.x+=sign*.006*smooth((sign*(p.x-origin.x)-.012)/.024)
            q.y-=.008*smooth((.024-p.y)/.022)
            maximum=max(maximum,(q-p).length);vertex.co=inverse@q
        obj.data.update();new=[to_native@v.co for v in obj.data.vertices]
        rows.append({'mesh':obj.name,'vertices':len(old),'maximum_move_mm':maximum*1000,'before_bounds_native_m':bounds(old),'after_bounds_native_m':bounds(new),'actual_foot_bounds_native_m':bounds(feet[side]['points'])})
    changed={r['mesh'] for r in rows};assert len(changed)==8
    def verify():
        actual=check.read()
        for key in before:
            if key=='meshes':
                for name,data in before[key].items():
                    assert {k:v for k,v in data.items() if k!='co'}=={k:v for k,v in actual[key][name].items() if k!='co'},name
                    if name not in changed:assert data==actual[key][name],name
            else:assert before[key]==actual[key],key
    verify();out.mkdir(parents=True);stem='whale_maid_shoe_envelope_v07';target=out/(stem+'.blend')
    pref=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=pref
    bpy.ops.wm.open_mainfile(filepath=str(target));verify()
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1;enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.view_layer.update();export=load('shoe_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');package=out/(stem+'.xwear')
        result=export.export_xwear(package,rig,[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'],item_name='Whale maid shoe enclosure v07',author='Local creator',coordinate_matrix=C)
        write(package.with_suffix('.xwear.json'),result)
    finally:
        for p in rig.pose.bones:p.matrix_basis=poses[p.name]
        sb.enable_animation=enabled
    assert digest(source)==sha
    report={**previous,'source':str(source),'source_sha256':sha,'copy':str(target),'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),'shoe_envelope_changes':rows,'actual_native_reference':str(a.reference),'actual_native_reference_sha256':digest(a.reference),'native_acceptance':False,'promoted':False,'shoe_fit_complete':False,'note':'Local rear/lateral/outsole enclosure candidate only. Native high-heel posture, arch and complete shoe appearance remain pending.'}
    write(out/'build.json',report);print(json.dumps({'built':True,'changed_meshes':len(rows),'out':str(out)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True);build(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
