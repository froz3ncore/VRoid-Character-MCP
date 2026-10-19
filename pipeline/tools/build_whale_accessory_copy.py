"""Reference-led appearance additions on a protected sleeve-cuff source copy.

Callable through Blender MCP or the background Blender CLI. Preserves the
existing garment/physics and adds a rigid hip-following whale tail plus the
ten retained Tripo head-accessory parts, fitted to the actual target head.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import struct
import sys
import zlib
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[1]
COORD=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
INVERSE=COORD.inverted()
RIG='WM_TargetVRoidRig_v01'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def png(path,pixels):
    height,width=pixels.shape[:2]
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=b''.join(b'\0'+row.tobytes() for row in pixels)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+
                     chunk(b'IDAT',zlib.compress(raw,6))+chunk(b'IEND',b''))


def tail_material(out,fluke=False):
    size=1024
    y,x=np.mgrid[0:size,0:size]/(size-1)
    if fluke:
        tip=x
        edge=np.abs(2*y-1)**5
        light=np.clip(.12+.52*tip+.22*edge,0,1)
    else:
        tip=y
        edge=(.5+.5*np.cos(2*np.pi*x))**5
        light=np.clip(.08+.38*tip+.18*edge,0,1)
    dark=np.array([30.,57.,126.]);pale=np.array([105.,172.,235.])
    rgb=dark+(pale-dark)*light[...,None]
    # Pale, sparse elongated flecks along the blue rim, as in the references.
    rng=np.random.default_rng(413 if fluke else 219)
    for _ in range(32 if fluke else 24):
        if fluke:
            cx=rng.uniform(.3,.95);cy=rng.choice([rng.uniform(.06,.2),rng.uniform(.8,.94)])
            sx,sy=rng.uniform(.004,.011),rng.uniform(.01,.025)
        else:
            cx=rng.choice([rng.uniform(.04,.15),rng.uniform(.85,.96)]);cy=rng.uniform(.25,.96)
            sx,sy=rng.uniform(.005,.012),rng.uniform(.008,.022)
        mask=((x-cx)/sx)**2+((y-cy)/sy)**2<1
        rgb[mask]=rgb[mask]*.3+np.array([165.,211.,247.])*.7
    pixels=np.concatenate((np.clip(rgb,0,255).astype(np.uint8),np.full((size,size,1),255,dtype=np.uint8)),axis=2)
    path=out/('whale_fluke_blue_v01.png' if fluke else 'whale_tail_blue_v01.png')
    png(path,pixels)
    image=bpy.data.images.load(str(path),check_existing=False);image.pack()
    material=bpy.data.materials.new('WM_Accessory_Fluke_Blue' if fluke else 'WM_Accessory_Tail_Blue')
    material.use_nodes=True
    shader=next(n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    shader.inputs['Roughness'].default_value=.64
    texture=material.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image
    material.node_tree.links.new(texture.outputs['Color'],shader.inputs['Base Color'])
    return material


def bind(obj,bone):
    for modifier in list(obj.modifiers):obj.modifiers.remove(modifier)
    for group in list(obj.vertex_groups):obj.vertex_groups.remove(group)
    group=obj.vertex_groups.new(name=bone);group.add(list(range(len(obj.data.vertices))),1.,'REPLACE')
    obj.parent=bpy.data.objects[RIG];obj.matrix_parent_inverse=Matrix.Identity(4);obj.matrix_world=Matrix.Identity(4)
    modifier=obj.modifiers.new('Actual VRoid skeleton','ARMATURE');modifier.object=bpy.data.objects[RIG]
    obj.hide_render=False;obj.hide_viewport=False;obj.hide_set(False)


def mesh(name,vertices,faces,uvs,material,bone='J_Bip_C_Hips'):
    data=bpy.data.meshes.new(name)
    data.from_pydata([INVERSE@Vector(v) for v in vertices],[],faces);data.update()
    obj=bpy.data.objects.new(name,data);bpy.data.collections['FITTED_服装工作副本'].objects.link(obj)
    data.materials.append(material)
    layer=data.uv_layers.new(name='UVMap')
    for polygon in data.polygons:
        seam='_WhaleTail_Body' in name and len(polygon.vertices)==4 and max(uvs[i][0] for i in polygon.vertices)-min(uvs[i][0] for i in polygon.vertices)>.5
        for loop_index in polygon.loop_indices:
            uv=uvs[data.loops[loop_index].vertex_index]
            layer.data[loop_index].uv=(uv[0]+1 if seam and uv[0]<.5 else uv[0],uv[1])
    bm=bmesh.new();bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free()
    for polygon in data.polygons:polygon.use_smooth=True
    bind(obj,bone)
    obj['fit_source_id']=-1001;obj['semantic_group']='15_鲸尾配饰'
    obj['construction']='New closed mesh from reference; rigid hip-following appearance stage'
    return obj


def make_tail(out):
    body_material,fluke_material=tail_material(out),tail_material(out,True)
    made=[];vertices=[];uvs=[];faces=[]
    rows,columns=40,24
    controls=np.array([[0.,.958,-.135],[-.022,.855,-.18],[-.078,.735,-.245],[-.118,.62,-.32],[-.104,.535,-.35]])
    for i in range(rows+1):
        t=i/rows;u=min(3.999999,t*4);k=int(u);f=u-k
        # Cubic Catmull-Rom curve; local endpoints do not overshoot attachment.
        p0,p1,p2,p3=(controls[max(0,min(4,j))] for j in (k-1,k,k+1,k+2))
        center=.5*((2*p1)+(-p0+p2)*f+(2*p0-5*p1+4*p2-p3)*f*f+(-p0+3*p1-3*p2+p3)*f*f*f)
        width=float(np.interp(t,[0,.25,.5,.75,1],[.027,.052,.069,.049,.022]))
        depth=float(np.interp(t,[0,.5,1],[.009,.018,.009]))
        for j in range(columns):
            angle=2*math.pi*j/columns
            vertices.append((center+np.array([width*math.cos(angle),0,depth*math.sin(angle)])).tolist())
            uvs.append((j/columns,t))
    for i in range(rows):
        for j in range(columns):
            a=i*columns+j;b=i*columns+(j+1)%columns
            faces.append((a,b,b+columns,a+columns))
    for i in (0,rows):
        ids=list(range(i*columns,(i+1)*columns))
        faces.append(tuple(ids[::-1] if i==0 else ids))
    made.append(mesh('FIT_ACCESSORY_WhaleTail_Body',vertices,faces,uvs,body_material))
    joint=Vector((-.104,.535,-.35))
    for sign,label in ((-1,'L'),(1,'R')):
        vertices=[];faces=[];uvs=[];r,c=28,14
        for side in (-1,1):
            for i in range(r+1):
                u=i/r
                center=joint+Vector((sign*(.012+.204*u),-.19*u+.035*math.sin(math.pi*u),-.045*u))
                # A broad swept lobe, narrow at the root and pointed at its tip.
                width=.0015+.062*math.sin(math.pi*u)**.85+.012*(1-u)**4
                cross=Vector((sign*.48,.88,0))
                for j in range(c+1):
                    v=2*j/c-1
                    point=center+cross*(v*width)
                    point.z+=side*(.0015+.006*math.sin(math.pi*u)*(1-v*v))
                    vertices.append(list(point));uvs.append((u,j/c))
        count=(r+1)*(c+1)
        for side in range(2):
            for i in range(r):
                for j in range(c):
                    a=side*count+i*(c+1)+j;b=a+c+1
                    faces.append((a,a+1,b+1,b) if side==0 else (a,b,b+1,a+1))
        perimeter=list(range(c+1))+[i*(c+1)+c for i in range(1,r+1)]+[r*(c+1)+j for j in range(c-1,-1,-1)]+[i*(c+1) for i in range(r-1,0,-1)]
        for x,y in zip(perimeter,perimeter[1:]+perimeter[:1]):faces.append((x,y,y+count,x+count))
        made.append(mesh('FIT_ACCESSORY_WhaleTail_Fluke_'+label,vertices,faces,uvs,fluke_material))
    return made


def restore_head():
    manifest=json.loads((ROOT/'projects/whale-maid/tripo-source/parts_manifest_v01.json').read_text(encoding='utf8'))
    parts=[p for p in manifest['parts'] if p['collection'].startswith('10_')]
    fitted=bpy.data.collections['FITTED_服装工作副本']
    cap=next(p for p in parts if p['source_id']==6)
    def native_bounds(bounds):
        lo,hi=bounds
        return Vector((-hi[1],lo[2],lo[0])),Vector((-lo[1],hi[2],hi[0]))
    cap_lo,cap_hi=native_bounds(cap['bounds']);anchor=(cap_lo+cap_hi)/2
    target=Vector((0.,1.607,-.025));scale=1.8
    made=[];changes=[]
    for record in parts:
        original=bpy.data.objects[record['object']]
        points=[COORD@original.matrix_world@v.co for v in original.data.vertices]
        lo=Vector(tuple(min(p[j] for p in points) for j in range(3)))
        hi=Vector(tuple(max(p[j] for p in points) for j in range(3)))
        canonical_lo,canonical_hi=native_bounds(record['bounds'])
        assert max(abs(a-b) for a,b in zip(hi-lo,canonical_hi-canonical_lo))<2e-6
        # The archived source rig has displaced object origins; restore the
        # exact reviewed source placement before fitting the complete group.
        translation=(canonical_lo+canonical_hi-lo-hi)/2
        obj=original.copy();obj.data=original.data.copy();obj.name='FIT_ACCESSORY_Head_T%03d'%record['source_id']
        fitted.objects.link(obj)
        for vertex,point in zip(obj.data.vertices,points):vertex.co=INVERSE@(target+(point+translation-anchor)*scale)
        bind(obj,'J_Bip_C_Head')
        obj['fit_source_id']=record['source_id'];obj['reference_only']=False
        obj['appearance_source']='Preserved reviewed Tripo head accessory, original UV/material'
        made.append(obj);changes.append({'source':original.name,'copy':obj.name,'original_source_origin_restored':list(translation)})
    return made,{'source_group_anchor':list(anchor),'target_anchor':list(target),'scale':scale,'parts':changes}


def make_back_bow(out):
    size=512;y,x=np.mgrid[0:size,0:size]/(size-1)
    light=np.clip(.22+.48*(1-(2*y-1)**2)+.10*np.sin(x*math.pi*4),0,1)
    rgb=np.array([27.,74.,143.])+(np.array([76.,153.,220.])-np.array([27.,74.,143.]))*light[...,None]
    path=out/'blue_head_bow_v02.png'
    png(path,np.concatenate((rgb.astype(np.uint8),np.full((size,size,1),255,dtype=np.uint8)),axis=2))
    image=bpy.data.images.load(str(path),check_existing=False);image.pack()
    material=bpy.data.materials.new('WM_Accessory_BackHeadBow_Blue');material.use_nodes=True
    shader=next(n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    shader.inputs['Roughness'].default_value=.7
    texture=material.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image
    material.node_tree.links.new(texture.outputs['Color'],shader.inputs['Base Color'])
    def fabric(name,func,rows=18,columns=10):
        vertices=[];faces=[];uvs=[]
        for side in (-1,1):
            for i in range(rows+1):
                for j in range(columns+1):
                    point=Vector(func(i/rows,2*j/columns-1));point.z+=side*.001
                    vertices.append(list(point));uvs.append((i/rows,j/columns))
        count=(rows+1)*(columns+1)
        for side in range(2):
            for i in range(rows):
                for j in range(columns):
                    a=side*count+i*(columns+1)+j;b=a+columns+1
                    faces.append((a,a+1,b+1,b) if side==0 else (a,b,b+1,a+1))
        perimeter=list(range(columns+1))+[i*(columns+1)+columns for i in range(1,rows+1)]+[rows*(columns+1)+j for j in range(columns-1,-1,-1)]+[i*(columns+1) for i in range(rows-1,0,-1)]
        for a,b in zip(perimeter,perimeter[1:]+perimeter[:1]):faces.append((a,b,b+count,a+count))
        obj=mesh(name,vertices,faces,uvs,material,'J_Bip_C_Head')
        obj['semantic_group']='16_后脑蓝色蝴蝶结';obj['construction']='Reference back-head bow; rigid Head binding'
        return obj
    made=[]
    for sign,label in ((-1,'L'),(1,'R')):
        made.append(fabric('FIT_ACCESSORY_Head_BackBow_Wing_'+label,
            lambda u,v,s=sign:(s*(.006+.056*u),1.492+.008*math.sin(math.pi*u)+v*(.010+.022*math.sin(math.pi*u/2)),
                              -.18-.009*math.sin(math.pi*u)*(1-v*v))))
        made.append(fabric('FIT_ACCESSORY_Head_BackBow_Tail_'+label,
            lambda u,v,s=sign:(s*(.012+.023*u)+v*.012,1.48-.068*u+.012*u**10*(1-abs(v)),
                              -.178-.004*math.sin(3*math.pi*u)*(1-v*v))))
    made.append(fabric('FIT_ACCESSORY_Head_BackBow_Knot',
        lambda u,v:(v*.009,1.474+.035*u,-.196-.002*math.sin(math.pi*u)*(1-v*v)),10,8))
    return made


def build(source,out,include_back_bow=False,stem='whale_maid_accessories_v01',mirror_tail=False):
    source,out=source.resolve(),out.resolve()
    assert Path(bpy.data.filepath).resolve()==source and not bpy.data.is_dirty
    assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='9390b4423fae8a4e121304c607f3497b8f579f16a3ca27325c30ab1c5b600b2e'
    verifier=module('source_verify',ROOT/'tools/verify_rear_mirror_sources.py')
    exporter=module('xwear',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
    fit=module('fit',ROOT/'blender-addons/vroid_xwear_direct/fit.py')
    original=verifier.read();source_hash=fit.digest(source)
    out.mkdir(parents=True)
    tail=make_tail(out)
    if mirror_tail:
        for obj in tail:
            for vertex in obj.data.vertices:vertex.co.y=-vertex.co.y
            bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free()
    head,head_fit=restore_head()
    back_bow=make_back_bow(out) if include_back_bow else []
    added=[o.name for o in tail+head+back_bow]
    def verify():
        actual=verifier.read()
        for key in original:
            if key in ('meshes','weights','images'):
                assert all(actual[key][name]==value for name,value in original[key].items()),key
            else:assert actual[key]==original[key],key
        assert set(actual['meshes'])-set(original['meshes'])==set(added)
        return actual
    verify()
    assert stem.replace('_','').isalnum() and stem.isascii()
    target=out/(stem+'.blend')
    old=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        assert 'FINISHED' in bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=old
    bpy.ops.wm.open_mainfile(filepath=str(target));verify()
    rig=bpy.data.objects[RIG];spring=rig.data.vrm_addon_extension.spring_bone1
    enabled=spring.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        spring.enable_animation=False
        for pose in rig.pose.bones:pose.matrix_basis.identity()
        bpy.context.view_layer.update()
        meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH']
        assert len(meshes)==69+len(added)
        package=out/(stem+'.xwear')
        exported=exporter.export_xwear(package,rig,meshes,item_name=stem+' appearance restoration',author='Local creator',coordinate_matrix=COORD)
        exported.update(source_blend=str(target),source_sha256=fit.digest(target),appearance_candidate=True)
        fit.write_new(package.with_suffix('.xwear.json'),exported)
        # Disposable render scenes; no saved source is modified by the preview.
        review=module('review',ROOT/'tools/review_target_cloth.py');review.OUT=out
        for view in ('front','back','side'):review.render_pose('appearance',view)
    finally:
        for pose in rig.pose.bones:pose.matrix_basis=poses[pose.name]
        spring.enable_animation=enabled
    assert fit.digest(source)==source_hash
    report={'source':str(source),'source_sha256':source_hash,'copy':str(target),'copy_sha256':fit.digest(target),
        'package':str(package),'package_sha256':fit.digest(package),'added_meshes':added,'head_fitting':head_fit,
        'existing_meshes_weights_uv_materials_images_bones_physics_unchanged':True,
        'cold_source_check_passed':True,'tail_binding':'Rigid Hips follow; no tail spring simulation added',
        'head_binding':'Actual target Head bone','back_head_bow_added':include_back_bow,'tail_mirrored_to_reference_back_view':mirror_tail,
        'fitted_meshes':69+len(added),'native_acceptance':False,'adopted':False}
    fit.write_new(out/'build.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--include-back-bow',action='store_true');parser.add_argument('--stem',default='whale_maid_accessories_v01')
    parser.add_argument('--mirror-tail',action='store_true')
    a=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);build(a.source,a.out,a.include_back_bow,a.stem,a.mirror_tail)
