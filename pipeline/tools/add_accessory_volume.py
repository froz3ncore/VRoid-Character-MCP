"""Add visible volume outward, retaining the inward attachment surfaces."""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def build(out):
    source=Path(bpy.data.filepath).resolve();out=out.resolve();previous=json.loads((source.parent/'build.json').read_text(encoding='utf8'));source_sha=digest(source)
    assert previous['copy_sha256']==source_sha and not bpy.data.is_dirty and not out.exists()
    assert out.is_relative_to(ROOT/'projects/whale-maid')
    verifier=load('volume_scope',ROOT/'tools/verify_rear_mirror_sources.py');before=verifier.read();rows=[]
    def native(obj):return [C@obj.matrix_world@v.co for v in obj.data.vertices]
    def record(obj,old):
        new=native(obj);rows.append({'mesh':obj.name,'vertices':len(old),'maximum_move_mm':1000*max((a-b).length for a,b in zip(old,new))})
    body=bpy.data.objects['FIT_ACCESSORY_WhaleTail_Body'];old=native(body);inverse=(C@body.matrix_world).inverted();tip_shift=Vector()
    def interp(t):
        anchors=[(0,.030),(.25,.060),(.55,.075),(.8,.060),(1,.040)]
        for (x,a),(y,b) in zip(anchors,anchors[1:]):
            if x<=t<=y:return a+(b-a)*(t-x)/(y-x)
        raise ValueError(t)
    for ring in range(41):
        points=old[ring*24:(ring+1)*24];front=max(p.z for p in points);span=front-min(p.z for p in points);desired=interp(ring/40)
        assert span>.001
        for j,p in enumerate(points):
            q=p.copy();q.z=front-(front-p.z)*desired/span;body.data.vertices[ring*24+j].co=inverse@q
        if ring==40:
            current=native(body)[-24:];tip_shift=sum(current,Vector())/24-sum(points,Vector())/24
    body.data.update();record(body,old)
    def sheet(obj,rows_count,columns,profile,shift=Vector()):
        old=native(obj);count=(rows_count+1)*(columns+1);assert len(old)==2*count,(obj.name,len(old),count)
        inverse=(C@obj.matrix_world).inverted();depths=[];before_depth=[]
        for i in range(count):
            a,b=old[i],old[i+count];front=max(a.z,b.z);u=(i//(columns+1))/rows_count;v=2*(i%(columns+1))/columns-1;depth=profile(u,v)
            before_depth.append(abs(a.z-b.z));depths.append(depth)
            for index,p in ((i,a),(i+count,b)):
                q=p+shift;q.z=front+shift.z-(0 if p.z==front else depth);obj.data.vertices[index].co=inverse@q
        obj.data.update();record(obj,old);rows[-1].update(before_axis_span_mm=[1000*min(before_depth),1000*max(before_depth)],after_axis_span_mm=[1000*min(depths),1000*max(depths)])
    for side in ('L','R'):
        sheet(bpy.data.objects['FIT_ACCESSORY_WhaleTail_Fluke_'+side],28,14,lambda u,v:.006+.014*math.sin(math.pi*u)*(1-v*v),tip_shift)
        sheet(bpy.data.objects['FIT_ACCESSORY_Head_BackBow_Wing_'+side],18,10,lambda u,v:.006+.016*math.sin(math.pi*u)*(1-v*v))
        sheet(bpy.data.objects['FIT_ACCESSORY_Head_BackBow_Tail_'+side],18,10,lambda u,v:.003+.003*(1-v*v))
    sheet(bpy.data.objects['FIT_ACCESSORY_Head_BackBow_Knot'],10,8,lambda u,v:.018+.006*math.sin(math.pi*u)*(1-v*v))
    for side in ('N','P'):
        sheet(bpy.data.objects['FIT_NEW_BowWing_'+side],24,12,lambda u,v:.008+.022*math.sin(math.pi*u)*(1-v*v))
        sheet(bpy.data.objects['FIT_NEW_BowTail_'+side],40,10,lambda u,v:.004+.002*(1-v*v))
    sheet(bpy.data.objects['FIT_NEW_BowKnot'],12,12,lambda u,v:.020+.008*math.sin(math.pi*u)*(1-v*v))
    changed={r['mesh'] for r in rows};assert len(changed)==13
    def check():
        actual=verifier.read()
        for key in before:
            if key=='meshes':
                for name,data in before[key].items():
                    assert {k:v for k,v in data.items() if k!='co'}=={k:v for k,v in actual[key][name].items() if k!='co'},name
                    if name not in changed:assert data==actual[key][name],name
            else:assert before[key]==actual[key],key
    check();out.mkdir(parents=True);stem='whale_maid_accessories_volume_v06';target=out/(stem+'.blend');old_preference=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=old_preference
    bpy.ops.wm.open_mainfile(filepath=str(target));check()
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1;enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.view_layer.update();exporter=load('volume_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');package=out/(stem+'.xwear')
        meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];result=exporter.export_xwear(package,rig,meshes,item_name='Whale maid volumetric accessories v06',author='Local creator',coordinate_matrix=C);write(package.with_suffix('.xwear.json'),result)
    finally:
        for p in rig.pose.bones:p.matrix_basis=poses[p.name]
        sb.enable_animation=enabled
    assert digest(source)==source_sha
    report={**previous,'source':str(source),'source_sha256':source_sha,'copy':str(target),'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),'volume_changes':rows,'volume_change_scope':'13 whale tail / blue head bow / white waist bow meshes only; body-facing surfaces retained; flukes follow enlarged tube center','volume_cold_scope_check_passed':True,'original_topology_uv_weights_materials_images_bones_springs_colliders_preserved':True,'native_acceptance':False,'promoted':False,'shoe_fit_complete':False,'note':'Visible accessory volume candidate. Shoe heel/sole enclosure remains pending; whole outfit is not adopted.'}
    write(out/'build.json',report);print(json.dumps({'built':True,'changed_meshes':13,'out':str(out)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);build(p.parse_args(sys.argv[sys.argv.index('--')+1:]).out)
