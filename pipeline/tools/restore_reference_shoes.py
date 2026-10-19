"""Extract reviewed dark shoe surfaces and original strap/buckle parts.

The generated legs/stockings stay in the source collection. New fitted copies
contain only the shoe material region, with interpolated UVs at the boundary.
"""
import bpy,bmesh,json,math
from pathlib import Path
import numpy as np
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)));CI=C.inverted()
RIG='WM_TargetVRoidRig_v01'
def restore():
    manifest=json.loads((ROOT/'projects/whale-maid/tripo-source/parts_manifest_v01.json').read_text(encoding='utf8'))
    fitted=bpy.data.collections['FITTED_服装工作副本'];rig=bpy.data.objects[RIG]
    made=[];reports=[]
    for record in manifest['parts']:
        ident=record['source_id'];mixed=ident in (4,5)
        if not mixed and not record['collection'].startswith('14_'):continue
        original=bpy.data.objects[record['object']];points=[original.matrix_world@v.co for v in original.data.vertices]
        center=Vector(tuple((min(p[k] for p in points)+max(p[k] for p in points))/2 for k in range(3)))
        anchor=(Vector(record['bounds'][0])+Vector(record['bounds'][1]))/2
        points=[C@(p+anchor-center) for p in points]
        sign=1 if sum(p.x for p in points)>0 else -1;side='R' if sign>0 else 'L'
        native=rig.data.bones['J_Bip_'+side+'_Foot'];foot_x=(C@rig.matrix_world@native.head_local).x
        # Match length/width to the captured target foot rather than importing
        # the generated leg. Raised origin compensates the removed mule lift.
        def fit(p):return CI@Vector(((p.x-sign*.050)*1.6+foot_x,p.y*1.35+.020,p.z*1.70-.019))
        if mixed:
            image=next(n.image for m in original.data.materials for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image)
            pixels=np.empty(len(image.pixels),dtype=np.float32);image.pixels.foreach_get(pixels);pixels=pixels.reshape(image.size[1],image.size[0],4)
            def luma(uv):
                x=int(max(0,min(image.size[0]-1,uv[0]*image.size[0])));y=int(max(0,min(image.size[1]-1,uv[1]*image.size[1])))
                return float(pixels[y,x,:3]@np.array([.2126,.7152,.0722]))
            vertices=[];faces=[];uvs=[];kept=0
            for face in original.data.polygons:
                polygon=[(points[original.data.loops[li].vertex_index],original.data.uv_layers.active.data[li].uv.copy()) for li in face.loop_indices]
                def clip(items,value):
                    result=[]
                    for a,b in zip(items,items[1:]+items[:1]):
                        av,bv=value(a),value(b)
                        if av>=0:result.append(a)
                        if (av>=0)!=(bv>=0):
                            t=av/(av-bv);result.append((a[0].lerp(b[0],t),a[1].lerp(b[1],t)))
                    return result
                polygon=clip(polygon,lambda a:.09-a[0].y)
                if len(polygon)<3:continue
                polygon=clip(polygon,lambda a:.42-luma(a[1]))
                if len(polygon)<3:continue
                uv=sum((p[1] for p in polygon),Vector((0,0)))/len(polygon)
                if luma(uv)>.50:continue
                kept+=1;start=len(vertices)
                vertices.extend(fit(p) for p,u in polygon);uvs.extend(tuple(u) for p,u in polygon)
                faces.append(tuple(range(start,len(vertices))))
            assert kept>100 and len(vertices)>300,(ident,kept)
            data=bpy.data.meshes.new('Extracted shoe '+str(ident));data.from_pydata(vertices,[],faces);data.update()
            for material in original.data.materials:data.materials.append(material)
            uv=data.uv_layers.new(name='OriginalUV_clipped')
            for loop in data.loops:uv.data[loop.index].uv=uvs[loop.vertex_index]
            # Join shared geometric seams while retaining per-loop UVs.
            bm=bmesh.new();bm.from_mesh(data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free()
        else:
            data=original.data.copy()
            for v,p in zip(data.vertices,points):v.co=fit(p)
            kept=len(data.polygons)
        name='FIT_ACCESSORY_Shoe_'+side+'_T%03d'%ident
        obj=bpy.data.objects.new(name,data);fitted.objects.link(obj);obj.parent=rig
        group=obj.vertex_groups.new(name='J_Bip_'+side+'_Foot');group.add(list(range(len(data.vertices))),1.,'REPLACE')
        modifier=obj.modifiers.new('Actual target foot','ARMATURE');modifier.object=rig
        for p in data.polygons:p.use_smooth=True
        obj['fit_source_id']=ident;obj['semantic_group']='17_还原玛丽珍高跟鞋';obj['source_leg_geometry_excluded']=True
        data.calc_loop_triangles();made.append(obj)
        reports.append({'mesh':name,'source_part':ident,'source_polygons':len(original.data.polygons),'retained_shoe_polygons':kept,'vertices':len(data.vertices),'triangles':len(data.loop_triangles),'skin_bone':group.name,'mixed_leg_material_removed':mixed,'uv_material_preserved':True})
    assert len(made)==8
    return made,reports
