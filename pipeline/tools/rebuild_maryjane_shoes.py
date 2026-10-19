"""Rebuild closed shoe uppers and arched block-heel soles from real foot geometry.

The original v06 source remains immutable. A native Body occlusion plan is saved
separately: it is not silently applied to a .vroid file or certified by Blender.
"""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1];C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)));CI=C.inverted()
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def write(p,data):
    with p.open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
def smooth(t):
    t=max(0.,min(1.,t));return t*t*(3-2*t)
def drop(z):return .025*smooth((z+.015)/.115)
def opening(z):
    knots=[(-.10,.075),(-.030,.075),(.010,.031),(.035,.041),(.060,.100),(.16,.100)]
    for (a,x),(b,y) in zip(knots,knots[1:]):
        if a<=z<=b:return x+(y-x)*(z-a)/(b-a)
    raise ValueError(z)
def convex_hull(points):
    points=sorted(set(points))
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    low=[];high=[]
    for p in points:
        while len(low)>=2 and cross(low[-2],low[-1],p)<=0:low.pop()
        low.append(p)
    for p in reversed(points):
        while len(high)>=2 and cross(high[-2],high[-1],p)<=0:high.pop()
        high.append(p)
    return low[:-1]+high[:-1]
def resample(poly,count=72):
    segments=[math.dist(a,b) for a,b in zip(poly,poly[1:]+poly[:1])];total=sum(segments);result=[]
    for n in range(count):
        d=n*total/count
        for i,length in enumerate(segments):
            if d<=length:
                a,b=poly[i],poly[(i+1)%len(poly)];t=d/length;result.append(tuple(x+(y-x)*t for x,y in zip(a,b)));break
            d-=length
    assert len(result)==count;return result
def material(name,color,roughness):
    m=bpy.data.materials.new(name);m.use_nodes=True;n=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');n.inputs['Base Color'].default_value=(*color,1);n.inputs['Roughness'].default_value=roughness;return m
def finish_mesh(mesh):
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    remaining=set(bm.faces)
    while remaining:
        pending=[remaining.pop()];component=[]
        while pending:
            face=pending.pop();component.append(face)
            for edge in face.edges:
                for neighbor in edge.link_faces:
                    if neighbor in remaining:remaining.remove(neighbor);pending.append(neighbor)
        if all(edge.is_manifold for face in component for edge in face.edges):
            verts={v for face in component for v in face.verts};origin=sum((v.co for v in verts),Vector())/len(verts);volume=0.
            for face in component:
                p=[v.co-origin for v in face.verts]
                volume+=sum(p[0].dot(p[i].cross(p[i+1]))/6 for i in range(1,len(p)-1))
            if volume<0:bmesh.ops.reverse_faces(bm,faces=component)
    bm.to_mesh(mesh);bm.free();mesh.update()
def build(a):
    source=Path(bpy.data.filepath).resolve();source_sha=digest(source);previous=json.loads((source.parent/'build.json').read_text(encoding='utf8'));assert previous['copy_sha256']==source_sha and not bpy.data.is_dirty
    out=a.out.resolve();assert not out.exists() and out.is_relative_to(ROOT/'projects/whale-maid')
    data=json.loads(a.reference.read_text(encoding='utf8'));assert data['pose_source']=='native_edit';base=next(m for m in data['base_meshes'] if m['name']=='Body')
    sys.path.insert(0,str(ROOT/'VRoid-MCP'));from vroid_mcp.wear_fit import world,foot_side;from vroid_mcp.wear_occlusion import geometry_hash
    positions=[Vector(p) for p in world(base)];wm=Matrix(base['world_matrix']);normal_matrix=wm.to_3x3().inverted().transposed();normals=[(normal_matrix@Vector(n)).normalized() for n in base['normals']]
    side_masks={}
    for side in ('L','R'):
        side_masks[side]=[sum(w for j,w in zip(entry['indices'],entry['weights']) if foot_side(data['bones'][base['bone_ids'][j]]['name'])==side)>=.35 for entry in base['weights']]
    scope=load('shoe_rebuild_scope',ROOT/'tools/verify_rear_mirror_sources.py');before=scope.read();fitted=bpy.data.collections['FITTED_服装工作副本'];rig=bpy.data.objects['WM_TargetVRoidRig_v01']
    navy=material('WM_MaryJane_Navy_v09' if a.clean_last else 'WM_MaryJane_Navy_v08',(.15,.20,.38) if a.clean_last else (.015,.022,.058),.26);solemat=material('WM_MaryJane_Outsole_v09' if a.clean_last else 'WM_MaryJane_Outsole_v08',(.055,.070,.13) if a.clean_last else (.006,.009,.022),.42)
    rows=[];hidden=[]
    for side in ('L','R'):
        selected=side_masks[side];foot=[p for p,keep in zip(positions,selected) if keep];vertices=[];faces=[]
        for i in range(0,len(base['triangles']),3):
            ids=base['triangles'][i:i+3]
            if not all(selected[j] for j in ids):continue
            poly=[(positions[j],normals[j]) for j in ids];clipped=[]
            for x,y in zip(poly,poly[1:]+poly[:1]):
                av=opening(x[0].z)-x[0].y;bv=opening(y[0].z)-y[0].y
                if av>=0:clipped.append(x)
                if (av>=0)!=(bv>=0):
                    t=av/(av-bv);clipped.append((x[0].lerp(y[0],t),x[1].lerp(y[1],t).normalized()))
            if len(clipped)<3:continue
            start=len(vertices)
            for p,n in clipped:
                q=p+n*.003;q.y-=drop(p.z);vertices.append(CI@q)
            order=list(range(start,len(vertices)));normal=CI.to_3x3()@sum((n for p,n in clipped),Vector())
            if (vertices[order[1]]-vertices[order[0]]).cross(vertices[order[2]]-vertices[order[0]]).dot(normal)<0:order.reverse()
            faces.append(order)
        mesh=bpy.data.meshes.new('Continuous Mary Jane upper '+side);mesh.from_pydata(vertices,[],faces);finish_mesh(mesh)
        if a.clean_last:
            last=load('smooth_shoe_last',ROOT/'tools/shoe_last_geometry.py');hull=convex_hull([(positions[i].x+normals[i].x*.005,positions[i].z+normals[i].z*.005) for i,keep in enumerate(selected) if keep]);mesh,center=last.upper(foot,hull,CI,drop);finish_mesh(mesh)
        temp=bpy.data.objects.new('Temporary upper construction',mesh);bpy.context.scene.collection.objects.link(temp)
        for o in bpy.context.selected_objects:o.select_set(False)
        temp.select_set(True);bpy.context.view_layer.objects.active=temp
        sub=temp.modifiers.new('Round shoe last','SUBSURF');sub.levels=1;bpy.ops.object.modifier_apply(modifier=sub.name)
        solid=temp.modifiers.new('Leather material volume','SOLIDIFY');solid.thickness=.0018;solid.offset=-1.;solid.use_even_offset=True;bpy.ops.object.modifier_apply(modifier=solid.name)
        mesh=temp.data.copy();bpy.data.objects.remove(temp,do_unlink=True);finish_mesh(mesh)
        mesh.materials.append(navy);mesh.materials.append(solemat)
        # A continuous closed outsole has a 45 mm block heel, a raised arch,
        # and a thinner toe platform. Hidden native toe/sole geometry is handled
        # by a separate saved native mask, preserving white exposed insteps.
        outline=[]
        for i,keep in enumerate(selected):
            if keep:
                p=positions[i]+normals[i]*.004;outline.append((p.x,p.z))
        contour=resample(convex_hull(outline));sole_points=[]
        for layer in (0,1):
            for x,z in contour:
                nearby=sorted(foot,key=lambda p:abs(p.z-z))[:10];top=(-drop(z)-.001) if a.clean_last else min(p.y for p in nearby)-drop(z)-.001
                t=max(0.,min(1.,(z+.035)/.080));bottom=min(top-.006,-.045+.038*math.sin(math.pi*t)**2)
                sole_points.append(CI@Vector((x,top if layer==0 else bottom,z)))
        n=len(contour);top_center=sum(sole_points[:n],Vector())/n;bottom_center=sum(sole_points[n:],Vector())/n
        sole_points.extend([top_center,bottom_center]);sole_faces=[[i,(i+1)%n,2*n] for i in range(n)]+[[i+n,2*n+1,(i+1)%n+n] for i in range(n)]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
        sole=bpy.data.meshes.new('Arched block heel sole '+side);sole.from_pydata(sole_points,[],sole_faces);finish_mesh(sole)
        if a.union_sole:
            sole.materials.append(navy);sole.materials.append(solemat)
            for face in sole.polygons:face.material_index=1
            operand=bpy.data.objects.new('Temporary outsole union',sole);bpy.context.scene.collection.objects.link(operand)
            union=bpy.data.objects.new('Temporary continuous shoe',mesh);bpy.context.scene.collection.objects.link(union)
            for obj in bpy.context.selected_objects:obj.select_set(False)
            union.select_set(True);bpy.context.view_layer.objects.active=union;mod=union.modifiers.new('Continuous outsole upper union','BOOLEAN');mod.operation='UNION';mod.solver='EXACT';mod.object=operand;bpy.ops.object.modifier_apply(modifier=mod.name)
            mesh=union.data.copy();bpy.data.objects.remove(union,do_unlink=True);bpy.data.objects.remove(operand,do_unlink=True);finish_mesh(mesh)
        else:
            bm=bmesh.new();bm.from_mesh(mesh);count=len(bm.faces);bm.from_mesh(sole)
            for face in list(bm.faces)[count:]:face.material_index=1
            bm.to_mesh(mesh);bm.free()
        for p in mesh.polygons:p.use_smooth=p.material_index==0
        name='FIT_ACCESSORY_Shoe_'+side+('_T004' if side=='R' else '_T005');obj=bpy.data.objects[name];assert obj.matrix_world==Matrix.Identity(4)
        obj.data=mesh;obj.vertex_groups.clear();group=obj.vertex_groups.new(name='J_Bip_'+side+'_Foot');group.add(list(range(len(mesh.vertices))),1.,'REPLACE')
        uv=mesh.uv_layers.new(name='ShoePlanar_v08');native=[C@v.co for v in mesh.vertices];xmin=min(p.x for p in native);zmin=min(p.z for p in native);dx=max(p.x for p in native)-xmin;dz=max(p.z for p in native)-zmin
        for loop in mesh.loops:
            p=native[loop.vertex_index];uv.data[loop.index].uv=((p.x-xmin)/dx,(p.z-zmin)/dz)
        mesh.calc_loop_triangles();bm=bmesh.new();bm.from_mesh(mesh);bad=sum(not e.is_manifold for e in bm.edges);volume=bm.calc_volume(signed=False);bm.free();assert not bad,(name,bad)
        rows.append({'mesh':name,'vertices':len(mesh.vertices),'triangles':len(mesh.loop_triangles),'nonmanifold_edges':bad,'material_volume_m3':volume,'continuous_upper_sole_union':a.union_sole,'components':'Continuous union with intended open instep' if a.union_sole else 'Closed leather upper plus closed arched outsole; intended open instep'})
        if a.clean_last:
            hidden.extend(i for i,keep in enumerate(selected) if keep and positions[i].y<.060 and (positions[i].y<.020 or ((positions[i].x-center.x)/.032)**2+((positions[i].z-center.y)/.052)**2>1.))
        else:hidden.extend(i for i,keep in enumerate(selected) if keep and positions[i].y<opening(positions[i].z)-.010)
    # Preserve the original six strap/gold parts, following the small local
    # shoe last bend. No head, tail, outfit or skeleton geometry changes.
    for obj in fitted.all_objects:
        if not obj.name.startswith('FIT_ACCESSORY_Shoe_') or obj.name.endswith(('T004','T005')):continue
        transform=C@obj.matrix_world;inverse=transform.inverted()
        for v in obj.data.vertices:
            p=transform@v.co;p.y-=drop(p.z);v.co=inverse@p
        obj.data.update()
    if a.clean_last:
        for side in ('L','R'):
            names=['FIT_ACCESSORY_Shoe_'+side+'_T'+n for n in (('030','054') if side=='R' else ('031','052'))];ring=bpy.data.objects[names[0]];anchor=sum((C@ring.matrix_world@v.co for v in ring.data.vertices),Vector())/len(ring.data.vertices)
            foot=[p for p,k in zip(positions,side_masks[side]) if k];target=anchor.copy();target.x=(max(p.x for p in foot)+.003 if side=='R' else min(p.x for p in foot)-.003);target.y-=.010
            for name in names:
                obj=bpy.data.objects[name];transform=C@obj.matrix_world;inverse=transform.inverted()
                for v in obj.data.vertices:v.co=inverse@(target+(transform@v.co-anchor)*.65)
                obj.data.update()
            strap=bpy.data.objects['FIT_ACCESSORY_Shoe_'+side+('_T085' if side=='R' else '_T086')];transform=C@strap.matrix_world;inverse=transform.inverted()
            for v in strap.data.vertices:
                p=transform@v.co;p.y-=.012;v.co=inverse@p
            strap.data.update()
    hidden=sorted(set(hidden));assert hidden and len(hidden)<len(positions)*.2
    changed={o.name for o in fitted.all_objects if o.name.startswith('FIT_ACCESSORY_Shoe_')};assert len(changed)==8
    def protect():
        actual=scope.read()
        for key in before:
            if key in ('meshes','weights'):
                for name,value in before[key].items():
                    if name not in changed:assert actual[key][name]==value,name
            else:assert actual[key]==before[key],key
    protect();out.mkdir(parents=True);stem=a.stem or ('whale_maid_maryjane_rebuilt_v09' if a.clean_last else 'whale_maid_maryjane_rebuilt_v08');assert all(c.isalnum() or c in '_-' for c in stem);target=out/(stem+'.blend');pref=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=pref
    bpy.ops.wm.open_mainfile(filepath=str(target));protect();rig=bpy.data.objects['WM_TargetVRoidRig_v01'];fitted=bpy.data.collections['FITTED_服装工作副本'];sb=rig.data.vrm_addon_extension.spring_bone1;enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.view_layer.update();export=load('rebuilt_shoe_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');package=out/(stem+'.xwear')
        result=export.export_xwear(package,rig,[o for o in fitted.all_objects if o.type=='MESH'],item_name=stem.replace('_',' '),author='Local creator',coordinate_matrix=C);write(package.with_suffix('.xwear.json'),result)
    finally:
        for p in rig.pose.bones:p.matrix_basis=poses[p.name]
        sb.enable_animation=enabled
    assert digest(source)==source_sha
    write(out/'body-occlusion-plan.json',{'source_reference':str(a.reference),'source_reference_sha256':digest(a.reference),'default_vertex_count':len(positions),'source_geometry_sha256':geometry_hash(base['source_positions'],base['triangles']),'hidden_vertices':hidden,'scope':'Only Foot/Toe-weighted vertices inside the designed shoe-covered region; clean last retains upper ankle and an expanded oval instep seam, v08 retains a 10mm height seam; .vroid source untouched; apply only through guarded native tool and verify cold reopen.'})
    write(out/'build.json',{**previous,'source':str(source),'source_sha256':source_sha,'copy':str(target),'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),'shoe_rebuild':rows,'changed_shoe_meshes':sorted(changed),'body_occlusion_vertices':len(hidden),'original_topology_uv_weights_materials_images_bones_springs_colliders_preserved':False,'protected_other_meshes_bones_physics_images_preserved':True,'main_shoe_topology_uv_materials_explicitly_rebuilt':True,'native_acceptance':False,'promoted':False,'shoe_fit_complete':False,'note':'Rebuilt shoes require native body occlusion, saved persistence, geometry and appearance acceptance. Inherited volume-stage records describe the earlier stage, not changes to the 13 accessories in this build.'})
    print(json.dumps({'built':True,'main_closed_shoes':rows,'body_occlusion_vertices':len(hidden),'out':str(out)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--clean-last',action='store_true');p.add_argument('--union-sole',action='store_true');p.add_argument('--stem');build(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
