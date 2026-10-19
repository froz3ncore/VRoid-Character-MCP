"""Saved-source skin/components and measured native geometry review; no source writes."""
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector

C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
def main(a):
    out=a.out.resolve();out.mkdir(exist_ok=False);source=Path(bpy.data.filepath);sha=hashlib.sha256(source.read_bytes()).hexdigest();meshes=[]
    for o in bpy.data.collections['FITTED_服装工作副本'].all_objects:
        if o.type!='MESH':continue
        p=[C@o.matrix_world@v.co for v in o.data.vertices];groups={};zones={}
        for v,q in zip(o.data.vertices,p):
            zone='torso' if q.y>1.1 and abs(q.x)<.20 else 'skirt' if .38<q.y<1.0 else 'other'
            for g in v.groups:
                n=o.vertex_groups[g.group].name;groups[n]=groups.get(n,0)+g.weight;zones.setdefault(zone,{})[n]=zones.setdefault(zone,{}).get(n,0)+g.weight
        row={'name':o.name,'vertices':len(p),'bounds':[[min(q[i] for q in p),max(q[i] for q in p)] for i in range(3)],'weight_mass':groups,'zones':zones,'materials':[m.name for m in o.data.materials]}
        if o.name.startswith('FIT_T001'):
            parents=list(range(len(p)))
            def find(i):
                while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
                return i
            for e in o.data.edges:parents[find(e.vertices[0])]=find(e.vertices[1])
            comps={}
            for i,q in enumerate(p):comps.setdefault(find(i),[]).append(i)
            row['components']=[{'vertices':len(ids),'bounds':[[min(p[j][i] for j in ids),max(p[j][i] for j in ids)] for i in range(3)]} for ids in sorted(comps.values(),key=len,reverse=True)]
        meshes.append(row)
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];bones=[{'name':b.name,'parent':b.parent.name if b.parent else None,'head':list(C@rig.matrix_world@b.head_local),'tail':list(C@rig.matrix_world@b.tail_local)} for b in rig.data.bones if b.name.startswith(('WM_Skirt','WM_BackRibbon'))]
    (out/'binding.json').write_text(json.dumps({'source':str(source),'sha256':sha,'meshes':meshes,'bones':bones},ensure_ascii=False,indent=2),encoding='utf8')
    for f in a.reference:
        d=json.loads(f.read_text(encoding='utf8'))
        if a.use_source_edit:
            assert d['pose_source']=='native_edit'
            rig.data.vrm_addon_extension.spring_bone1.enable_animation=False
            for p in rig.pose.bones:p.matrix_basis.identity()
            bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();garments=[]
            for obj in bpy.data.collections['FITTED_服装工作副本'].all_objects:
                if obj.type!='MESH':continue
                mesh=bpy.data.meshes.new_from_object(obj.evaluated_get(deps),depsgraph=deps);mesh.calc_loop_triangles()
                garments.append({'name':obj.name,'world_matrix':[list(r) for r in Matrix.Identity(4)],'positions':[list(C@obj.matrix_world@v.co) for v in mesh.vertices],
                    'triangles':[int(i) for t in mesh.loop_triangles for i in reversed(t.vertices)]})
            d['garments']=garments
        scene=bpy.data.scenes.new('MEASURED_NATIVE_GEOMETRY')
        scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.light='STUDIO';scene.display.shading.color_type='OBJECT';scene.display.shading.show_shadows=False;scene.display.shading.show_cavity=True;scene.display.shading.cavity_type='BOTH'
        scene.display.shading.background_type='WORLD';scene.world=bpy.data.worlds.new('DiagnosisBackground');scene.world.color=(.12,.12,.14)
        scene.render.resolution_x=1000;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
        for g in [d['body']]+d['garments']:
            if g['name'].startswith(('FIT_ACCESSORY_Head','FIT_NEW_Bow','FIT_ACCESSORY_WhaleTail')):continue
            m=Matrix(g['world_matrix']);points=[C.inverted()@m@Vector(p) for p in g['positions']];faces=[list(reversed(g['triangles'][i:i+3])) for i in range(0,len(g['triangles']),3)]
            mesh=bpy.data.meshes.new(g['name']);mesh.from_pydata(points,[],faces);mesh.update();obj=bpy.data.objects.new(g['name'],mesh);scene.collection.objects.link(obj)
            obj.color=(.95,.36,.18,1) if g is d['body'] else (.28,.47,.72,1)
            for poly in mesh.polygons:poly.use_smooth=True
        camdata=bpy.data.cameras.new('DiagnosisCamera');cam=bpy.data.objects.new('DiagnosisCamera',camdata);scene.collection.objects.link(cam);scene.camera=cam;camdata.type='ORTHO'
        for name,center,scale,axis in [('chest-side',(0,1.24,.03),.40,(1,0,.1)),('chest-threequarter',(0,1.24,.03),.40,(1,0,1)),('chest-front',(0,1.24,.03),.40,(0,0,1)),('skirt-side',(0,.75,.10),.85,(1,0,.1))]:
            target=C.inverted()@Vector(center);v=C.inverted().to_3x3()@Vector(axis).normalized();cam.location=target+v*4;cam.rotation_euler=(-v).to_track_quat('-Z','Y').to_euler();camdata.ortho_scale=scale
            scene.render.filepath=str(out/(f.stem+'-'+name+'.png'));bpy.ops.render.render(write_still=True,scene=scene.name)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
    print(json.dumps({'read_only_inspection':True,'meshes':len(meshes),'bones':len(bones)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--reference',type=Path,action='append',default=[]);p.add_argument('--use-source-edit',action='store_true');main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
