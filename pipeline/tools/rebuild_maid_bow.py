"""Editable clean bow construction on a new fitting copy through Blender MCP."""
import bpy,bmesh,json,math,hashlib
from pathlib import Path
from mathutils import Vector
ROOT=Path('D:/vroidmcp');OUT=ROOT/'projects/whale-maid/target-fit-v03'
SOURCE=ROOT/'projects/whale-maid/target-fit-v02/whale_maid_target_fit_v02.blend'
TARGET=OUT/'whale_maid_target_fit_v03.blend'
RIG='WM_TargetVRoidRig_v01'

def sheet(name,func,rows,columns,weights,material):
    vertices=[];faces=[];uv=[]
    for side in range(2):
        for i in range(rows+1):
            for j in range(columns+1):
                u=i/rows;v=j/columns
                p=Vector(func(u,2*v-1));p.x+=side*.0025
                vertices.append(tuple(p));uv.append((u,v))
    count=(rows+1)*(columns+1)
    for side in range(2):
        base=side*count
        for i in range(rows):
            for j in range(columns):
                a=base+i*(columns+1)+j;b=a+columns+1
                face=(a,a+1,b+1,b)
                faces.append(face if side==0 else face[::-1])
    perimeter=list(range(columns+1))+[i*(columns+1)+columns for i in range(1,rows+1)]+[
        rows*(columns+1)+j for j in range(columns-1,-1,-1)]+[i*(columns+1) for i in range(rows-1,0,-1)]
    for a,b in zip(perimeter,perimeter[1:]+perimeter[:1]):faces.append((a,b,b+count,a+count))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.data.collections['FITTED_服装工作副本'].objects.link(obj)
    mesh.materials.append(material);layer=mesh.uv_layers.new(name='UVMap')
    for loop in mesh.loops:layer.data[loop.index].uv=uv[loop.vertex_index]
    groups={}
    for i in range(len(vertices)):
        u=(i%count)//(columns+1)/rows
        for bone,w in weights(u).items():
            if bone not in groups:groups[bone]=obj.vertex_groups.new(name=bone)
            groups[bone].add([i],w,'REPLACE')
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    for p in mesh.polygons:p.use_smooth=True
    modifier=obj.modifiers.new('Native target skin','ARMATURE');modifier.object=bpy.data.objects[RIG]
    obj.parent=bpy.data.objects[RIG]
    obj['fit_source_id']=-1;obj['semantic_group']='12_重建白色腰后蝴蝶结';obj['construction']='closed fabric surface with UV and normalized skin weights'
    return obj

def body_hash():
    return hashlib.sha256(json.dumps({o.name:[list(v.co) for v in o.data.vertices] for o in bpy.data.objects if o.name.startswith('REF_VRoid_')},sort_keys=True).encode()).hexdigest()

def rebuild():
    if Path(bpy.data.filepath)!=SOURCE or bpy.data.is_dirty:raise RuntimeError('Expected unmodified saved v02 source')
    if TARGET.exists():raise FileExistsError('Refusing to overwrite v03; inspect existing result')
    OUT.mkdir(exist_ok=True);before=body_hash();source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    old=bpy.context.preferences.filepaths.save_version
    rig=bpy.data.objects[RIG];sb=rig.data.vrm_addon_extension.spring_bone1
    try:
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=str(TARGET),compress=True,relative_remap=False)
        sb.enable_animation=False
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.view_layer.update()
        fitted=bpy.data.collections['FITTED_服装工作副本']
        archive=bpy.data.collections.new('ARCHIVE_v02_旧腰后蝴蝶结_保留');bpy.context.scene.collection.children.link(archive)
        retired=[o for o in fitted.objects if '腰后蝴蝶结与带片片段' in o.name]
        assert len(retired)==9
        for o in retired:archive.objects.link(o);fitted.objects.unlink(o)
        archive.hide_viewport=True;archive.hide_render=True
        mat=bpy.data.materials.new('WM_WhiteBow_Satin');mat.use_nodes=True
        node=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        node.inputs['Base Color'].default_value=(.88,.9,.965,1);node.inputs['Roughness'].default_value=.7
        made=[]
        for sign,label in [(-1,'N'),(1,'P')]:
            def wing(u,v,sign=sign):
                return (-.123-.025*math.sin(math.pi*u)*(1-v*v),sign*(.014+.148*u),
                    .993+.017*math.sin(math.pi*u)+v*(.012+.044*math.sin(math.pi*u/2)))
            made.append(sheet('FIT_NEW_BowWing_'+label,wing,24,12,lambda u:{'J_Bip_C_Hips':1.},mat))
            def tail(u,v,sign=sign):
                return (-.13-.145*u-.009*math.sin(3*math.pi*u)*(1-v*v),
                    sign*(.034+.084*u)+v*(.025+.012*u),.978-.255*u+.036*u**12*(1-abs(v)))
            def skin(u,label=label):
                t=min(2.999,u*3);i=int(t);f=t-i
                w={f'WM_BackRibbon_{label}_{i:02d}':1-f,f'WM_BackRibbon_{label}_{i+1:02d}':f}
                hip=max(0,1-u/.15)*.65
                return {**{k:v*(1-hip) for k,v in w.items() if v>1e-8},**({'J_Bip_C_Hips':hip} if hip>0 else {})}
            made.append(sheet('FIT_NEW_BowTail_'+label,tail,40,10,skin,mat))
        def knot(u,v):
            return (-.152-.008*math.cos(v*math.pi/2)*math.sin(math.pi*u),v*.025,.966+.055*u)
        made.append(sheet('FIT_NEW_BowKnot',knot,12,12,lambda u:{'J_Bip_C_Hips':1.},mat))
        assert body_hash()==before and hashlib.sha256(SOURCE.read_bytes()).hexdigest()==source_hash
        sb.enable_animation=True;bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
        bpy.ops.wm.save_as_mainfile(filepath=str(TARGET),compress=True,relative_remap=False)
        result={'source':str(SOURCE),'source_sha256':source_hash,'target':str(TARGET),'body_unchanged':True,
            'archived_parts':[o.name for o in retired],'new_parts':[o.name for o in made],
            'fitted_meshes':len(fitted.objects),'spring_chains':len(sb.springs),'spring_joints':sum(len(s.joints) for s in sb.springs),
            'scope':'Editable bow reconstruction; native wearing and animation acceptance pending'}
        (OUT/'bow-rebuild.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(result,ensure_ascii=False))
    finally:bpy.context.preferences.filepaths.save_version=old
