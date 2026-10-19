"""Experimental standalone Blender writer for a restricted XWear v2 subset.

Original implementation. No pixiv executable code or assets are bundled.
Supports rest-pose skinning, UV0, opaque colors/direct base-color images,
and the XWear VRM 1 spring addon representation. Native acceptance is separate.
"""
import bpy
import io
import json
import math
import os
import struct
import uuid
import zipfile
import hashlib
import tempfile
from array import array
from pathlib import Path
from mathutils import Matrix, Vector
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, EnumProperty

bl_info = {'name':'VRoid MCP — Direct XWear (Experimental)', 'author':'VRoid MCP local prototype',
           'version':(0,2,0), 'blender':(4,2,0), 'category':'Import-Export',
           'description':'Restricted direct XWear writer; interoperability testing only'}

ASSEMBLY = 'XWear.IO.Runtime'
COORD = Matrix(((-1,0,0,0),(0,0,1,0),(0,-1,0,0),(0,0,0,1)))
HUMANOID = {'Hips':0,'LeftUpperLeg':1,'RightUpperLeg':2,'LeftLowerLeg':3,'RightLowerLeg':4,
            'LeftFoot':5,'RightFoot':6,'Spine':7,'Chest':8,'Neck':9,'Head':10,
            'LeftShoulder':11,'RightShoulder':12,'LeftUpperArm':13,'RightUpperArm':14,
            'LeftLowerArm':15,'RightLowerArm':16,'LeftHand':17,'RightHand':18,
            'LeftToes':19,'RightToes':20,'UpperChest':54}


def identifier():
    return uuid.uuid4().hex


def typed(type_name, **fields):
    return {'$type':'XWear.IO.Runtime.'+type_name+', '+ASSEMBLY, **fields}


def xyz(v):
    return dict(zip(('x','y','z'), map(float,v)))


def node(name, matrix, index, node_id=None):
    q = matrix.to_quaternion()
    return {'Guid':node_id or identifier(), 'Name':name, 'Tag':'Untagged', 'Layer':0,
            'ActiveSelf':True, 'Children':[], 'Transform':{
                'Name':name, 'Position':xyz(matrix.translation),
                'Rotation':dict(zip(('x','y','z','w'),(q.x,q.y,q.z,q.w))),
                'Scale':xyz(matrix.to_scale()), 'LocalPosition':xyz((0,0,0)),
                'LocalRotation':{'x':0,'y':0,'z':0,'w':1},'LocalScale':xyz((1,1,1)), 'Index':index}}


def image_resource(image, texture_cache, payloads):
    if image.source not in ('FILE', 'GENERATED') or image.is_dirty:
        raise ValueError('Save image edits and use a single image file: '+image.name)
    if image.colorspace_settings.name != 'sRGB':
        raise ValueError('Base color image must use sRGB: '+image.name)
    width,height=map(int,image.size)
    if min(width,height)<1 or max(width,height)>8192:
        raise ValueError('Image dimensions outside 1..8192: '+image.name)
    data=bytes(image.packed_file.data) if image.packed_file else None
    if data is None and image.source=='FILE':
        source=Path(bpy.path.abspath(image.filepath,library=image.library))
        if source.is_file():data=source.read_bytes()
    if not data or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        # Saving a temporary copy leaves original image paths/settings/packed bytes intact.
        copy=bpy.data.images.new('XWear temporary PNG',width=width,height=height,alpha=True)
        try:
            copy.colorspace_settings.name=image.colorspace_settings.name
            pixels=array('f',[0.0])*(width*height*4)
            image.pixels.foreach_get(pixels);copy.pixels.foreach_set(pixels)
            copy.update()
            with tempfile.TemporaryDirectory(prefix='xwear-image-') as folder:
                copy.filepath_raw=str(Path(folder)/'texture.png');copy.file_format='PNG'
                copy.save();data=Path(copy.filepath_raw).read_bytes()
        finally:bpy.data.images.remove(copy)
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('PNG encoding failed: '+image.name)
    digest=hashlib.sha256(data).hexdigest()
    if digest in texture_cache:return texture_cache[digest]['Guid']
    guid=identifier()
    texture=typed('Textures.XResourceTexture',Name=image.name,Guid=guid,
        TextureParam=typed('Textures.Texture2DParam',name=image.name,width=width,height=height,
            anisoLevel=1,wrapMode=0,wrapModeU=0,wrapModeV=0,wrapModeW=0,mipMapCount=1,
            graphicsFormat=8,dimension=2,linear=False,textureType=1,depth=0,textureFormat=4),
        TextureImportSettings={'textureType':0,'shapeType':1,'sRGBTexture':True,
            'streamingMipmaps':False,'mipmapEnabled':False,'crunchedCompression':False,
            'compressionQuality':0,'maxTextureSize':max(width,height),'isNormal':False,
            'alphaIsTransparency':False,'wrapMode':0,'filterMode':1})
    texture_cache[digest]=texture;payloads['Textures\\'+guid+'.png']=data
    return guid


def material_resource(material, texture_cache=None, payloads=None):
    color = list(material.diffuse_color) if material else [.9,.9,.9,1]
    texture=None
    if material and material.use_nodes:
        output=next((n for n in material.node_tree.nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output),None)
        if not output or not output.inputs['Surface'].is_linked:
            raise ValueError('Material has no connected output: '+material.name)
        bsdf=output.inputs['Surface'].links[0].from_node
        if bsdf.type!='BSDF_PRINCIPLED':raise ValueError('Only direct Principled materials supported: '+material.name)
        if bsdf:
            if bsdf.inputs['Alpha'].is_linked or bsdf.inputs['Alpha'].default_value<.999:
                raise ValueError('Transparent materials require a future exporter version')
            for key in ('Normal','Emission Color'):
                if bsdf.inputs[key].is_linked:
                    n=bsdf.inputs[key].links[0].from_node
                    # Tripo imports an empty Normal Map node, which has no effect.
                    if key!='Normal' or n.type!='NORMAL_MAP' or n.inputs['Color'].is_linked:
                        raise ValueError('Unsupported linked '+key+': '+material.name)
            if bsdf.inputs['Base Color'].is_linked:
                link=bsdf.inputs['Base Color'].links[0];n=link.from_node
                if n.type!='TEX_IMAGE' or not n.image or link.from_socket.name!='Color':
                    raise ValueError('Base color must be a direct image Color link: '+material.name)
                if n.inputs['Vector'].is_linked or n.extension!='REPEAT' or n.projection!='FLAT':
                    raise ValueError('Only default UV0 image sampling supported: '+material.name)
                if texture_cache is None or payloads is None:raise ValueError('Texture export context required')
                texture=image_resource(n.image,texture_cache,payloads);color=[1,1,1,1]
            else:color = list(bsdf.inputs['Base Color'].default_value)
    if color[3] < .999:
        raise ValueError('Transparent materials require a future exporter version')
    def tint(prop, rgba):
        return typed('Materials.Shader.ShaderColorProperty', PropertyName=prop,
                     Color=dict(zip(('r','g','b','a'),rgba)))
    def scalar(prop, value):
        return typed('Materials.Shader.ShaderFloatProperty', PropertyName=prop, Value=value)
    shade_color=color
    if material and 'vroid_mcp_shade_color' in material:
        shade_color=list(material['vroid_mcp_shade_color'])
        if len(shade_color)!=4 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or not 0<=v<=1 for v in shade_color) or shade_color[3]<.999:
            raise ValueError('vroid_mcp_shade_color requires opaque linear RGBA floats in 0..1: '+material.name)
        # This opt-in property is LINEAR RGBA. Native XWear color loading and
        # native VRM export each apply an sRGB->linear conversion (verified by
        # material round-trip). Encode twice on the wire to retain the requested
        # linear VRM shade. Existing materials keep their historical behavior.
        def srgb(value):return 12.92*value if value<=.0031308 else 1.055*value**(1/2.4)-.055
        shade_color=[srgb(srgb(v)) for v in shade_color[:3]]+[shade_color[3]]
    properties=[tint('_Color',color),tint('_ShadeColor',shade_color),scalar('_CullMode',0),
                scalar('_BlendMode',0),scalar('_ZWrite',1),scalar('_OutlineWidth',0)]
    if texture:
        properties.extend(typed('Materials.Shader.ShaderTextureProperty',PropertyName=p,TextureGuid=texture)
                          for p in ('_MainTex','_ShadeTexture'))
    return {'Name':material.name if material else 'WhiteCloth', 'Guid':identifier(),
            'ShaderName':'VRM/MToon', 'ShaderProperties':[
                *properties],
            'MaterialTags':[], 'ShaderKeywords':[], 'RenderQueue':2000,
            'referencedTextureGuids':[texture] if texture else []}


def humanoid_mapping(armature):
    result={}
    extension=getattr(armature.data,'vrm_addon_extension',None)
    if extension:
        for human,bone in extension.vrm1.humanoid.human_bones.human_bone_name_to_human_bone().items():
            name=human.value[0].upper()+human.value[1:]
            if name in HUMANOID and bone.node.bone_name:
                result[bone.node.bone_name]=HUMANOID[name]
    if not result:
        result={name:HUMANOID[name] for name in HUMANOID if name in armature.data.bones}
    if len(set(result.values()))!=len(result):raise ValueError('Ambiguous humanoid mapping')
    if 0 not in result.values():raise ValueError('A Hips humanoid assignment is required')
    return result


def spring_resource(armature, root, bone_ids, bone_nodes, bone_world, coord, next_index):
    extension=getattr(armature.data,'vrm_addon_extension',None)
    spring=getattr(extension,'spring_bone1',None)
    if not spring or not spring.springs:return None,{'springs':0,'joints':0,'colliders':0}
    if any(abs(v-1)>1e-6 for v in armature.matrix_world.to_scale()):
        raise ValueError('Spring export requires unit armature scale')
    refs=[];joints=[];joint_by_bone={};colliders=[];groups=[];springs=[]
    def ref(key,bone):
        if bone not in bone_ids:raise ValueError('Missing spring reference bone: '+bone)
        refs.append({'key':key,'referenceGuid':bone_ids[bone]})
    collider_ids={}
    for c in spring.colliders:
        i=len(colliders);collider_ids[c.uuid]=i
        # Keep wearable colliders on unique child objects. Components directly on
        # humanoid nodes can be lost when VRoid merges those nodes into its base rig.
        name='WM_XWearCollider_'+str(i);helper=node(name,bone_world[c.node.bone_name],next_index+i)
        bone_nodes[c.node.bone_name]['Children'].append(helper)
        refs.append({'key':'Vrm1Collider_'+str(i),'referenceGuid':helper['Guid']})
        if c.shape_type not in ('Sphere','Capsule'):raise ValueError('Only sphere/capsule spring colliders supported')
        shape=c.shape.sphere if c.shape_type=='Sphere' else c.shape.capsule
        colliders.append({'ColliderType':0 if c.shape_type=='Sphere' else 1,
            'Offset':xyz(coord.to_3x3() @ Vector(shape.offset)),
            'Radius':float(shape.radius),
            'Tail':xyz(coord.to_3x3() @ Vector(shape.tail)) if c.shape_type=='Capsule' else xyz((0,0,0)),
            'Normal':xyz((0,0,0))})
    group_ids={}
    for g in spring.collider_groups:
        i=len(groups);group_ids[g.uuid]=i
        helper=node('WM_XWearColliderGroup_'+str(i),Matrix.Identity(4),next_index+len(colliders)+i)
        root['Children'].append(helper)
        refs.append({'key':'Vrm1ColliderGroup_'+str(i),'referenceGuid':helper['Guid']})
        groups.append({'Name':g.vrm_name,'ColliderIndexes':[collider_ids[c.collider_uuid] for c in g.colliders]})
    for s in spring.springs:
        indexes=[]
        for j in s.joints:
            bone=j.node.bone_name
            item={'StiffnessForce':float(j.stiffness),'GravityPower':float(j.gravity_power),
                'GravityDir':xyz(coord.to_3x3() @ Vector(j.gravity_dir)),
                'DragForce':float(j.drag_force),'JointRadius':float(j.hit_radius)}
            if bone not in joint_by_bone:
                i=len(joints);joint_by_bone[bone]=i;joints.append(item);ref('Vrm1Joint_'+str(i),bone)
            elif joints[joint_by_bone[bone]]!=item:raise ValueError('Conflicting spring settings on '+bone)
            indexes.append(joint_by_bone[bone])
        center=''
        if s.center.bone_name:
            center='Vrm1SpringCenter_'+str(len(springs));ref(center,s.center.bone_name)
        springs.append({'Name':s.vrm_name,'JointIndexes':indexes,
            'ColliderGroupIndexes':[group_ids[g.collider_group_uuid] for g in s.collider_groups],
            'CenterReferenceKey':center})
    data={'Version':1,'SpringItems':springs,'JointItems':joints,'ColliderItems':colliders,'ColliderGroupItems':groups}
    component=typed('Components.Anything.XResourceAnythingJson',AnythingName='Vrm1InstanceAddon',
        GameObjectGuid=root['Guid'],ComponentType=12,
        AnythingJson=json.dumps(data,separators=(',',':'),allow_nan=False),ReferenceGuidStores=refs,
        ClassFullName='UniVRM10.Vrm10Instance',AssemblyFullName='VRM10, Version=0.0.0.0, Culture=neutral, PublicKeyToken=null')
    return component,{'springs':len(springs),'joints':len(joints),'colliders':len(colliders)}


def binary_mesh(name, positions, normals, uvs, weights, bindposes, submeshes):
    # Little-endian mesh payload. Arrays carry element counts, not byte counts.
    out = io.BytesIO()
    def ints(*values):
        out.write(struct.pack('<'+'i'*len(values), *values))
    def floats(values):
        values = list(values)
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Non-finite mesh data')
        out.write(struct.pack('<'+'f'*len(values),*values))
    data = name.encode('utf8')
    ints(0)
    length = len(data)
    while length >= 128:
        out.write(bytes([(length & 127)|128])); length >>= 7
    out.write(bytes([length])); out.write(data)
    ints(len(positions))
    for array in (positions,normals):
        ints(len(array))
        for value in array: floats(value)
    ints(0,0)  # no tangents, no vertex colors
    ints(len(uvs))
    for value in uvs: floats(value)
    ints(0,0,0)  # UV1..3 absent
    ints(len(weights))
    for values, indices in weights:
        floats(values); ints(*indices)
    ints(len(bindposes))
    for matrix in bindposes:
        floats(matrix[row][col] for col in range(4) for row in range(4))
    ints(len(submeshes))
    for indices in submeshes:
        ints(0,len(indices),*indices)  # triangles
    ints(0,0)  # no blend shapes and no current morph weights
    return out.getvalue()


def export_xwear(filepath, armature, meshes, item_name='Original apron', author='Local creator', coordinate_matrix=None):
    path = Path(filepath)
    if path.suffix.lower() != '.xwear': raise ValueError('Expected .xwear destination')
    if path.exists(): raise FileExistsError('Choose a new export filename: '+str(path))
    if not armature or armature.type != 'ARMATURE': raise ValueError('Select one armature')
    if not meshes: raise ValueError('No skinned meshes selected')
    if armature.data.pose_position != 'REST':
        # An unchanged POSE skeleton is also allowed, but an actual posed skeleton is not.
        if any(abs(b.matrix_basis[r][c]-(1 if r==c else 0))>1e-6
               for b in armature.pose.bones for r in range(4) for c in range(4)):
            raise ValueError('Return armature to rest pose before export')
    bones = list(armature.data.bones)
    if len(bones)>1024: raise ValueError('Limit: 1024 skeleton nodes')
    coord=coordinate_matrix if coordinate_matrix is not None else COORD
    if not isinstance(coord,Matrix) or len(coord)!=4:raise ValueError('Expected 4x4 coordinate matrix')
    if any(abs(coord[3][i]-(1 if i==3 else 0))>1e-6 for i in range(4)) or coord.translation.length>1e-6:
        raise ValueError('Coordinate matrix must have no translation and an affine last row')
    orthogonal=coord.to_3x3().transposed() @ coord.to_3x3()
    if any(abs(orthogonal[r][c]-(1 if r==c else 0))>1e-6 for r in range(3) for c in range(3)):
        raise ValueError('Coordinate matrix must be orthonormal; apply scale to the rig first')
    human_map=humanoid_mapping(armature)
    bone_ids = {b.name:identifier() for b in bones}
    bone_indices = {b.name:i for i,b in enumerate(bones)}
    hips=next(name for name,value in human_map.items() if value==0)
    root = node(item_name,Matrix.Identity(4),0)
    bone_world = {b.name:coord @ armature.matrix_world @ b.matrix_local @ coord.inverted() for b in bones}
    bone_nodes = {b.name:node(b.name,bone_world[b.name],i+1,bone_ids[b.name]) for i,b in enumerate(bones)}
    for b in bones:
        parent = bone_nodes[b.parent.name] if b.parent else root
        parent['Children'].append(bone_nodes[b.name])
    resources, components, payloads, details, textures = {}, [], {}, [], {}
    for obj in meshes:
        if obj.type != 'MESH': raise ValueError('Expected mesh objects')
        if obj.data.shape_keys and len(obj.data.shape_keys.key_blocks)>1:
            raise ValueError('Morph targets are not supported: '+obj.name)
        modifiers = [m for m in obj.modifiers if m.show_viewport]
        if len(modifiers)!=1 or modifiers[0].type!='ARMATURE' or modifiers[0].object!=armature:
            raise ValueError('Apply non-armature modifiers first: '+obj.name)
        data = obj.data
        if not data.uv_layers.active: raise ValueError('Missing UV: '+obj.name)
        data.calc_loop_triangles()
        slots = list(data.materials) or [None]
        mats = []
        for material in slots:
            key = material.name if material else '__default__'
            if key not in resources: resources[key] = material_resource(material,textures,payloads)
            mats.append(resources[key]['Guid'])
        geometry = [[],[],[],[]]
        positions,normals,uvs,weights = geometry
        submeshes = [[] for _ in slots]
        vertex_cache = {}
        vertex_weights = {}
        skipped_degenerate=0
        for v in data.vertices:
            influences = [(bone_indices[obj.vertex_groups[g.group].name],g.weight) for g in v.groups
                          if obj.vertex_groups[g.group].name in bone_indices and g.weight>1e-8]
            if not influences or len(influences)>4:
                raise ValueError('Need 1..4 positive bone influences per vertex: '+obj.name)
            total = sum(w for _,w in influences)
            influences.sort(key=lambda x:(-x[1],x[0]))
            vi = [i for i,_ in influences]+[0]*(4-len(influences))
            vw = [w/total for _,w in influences]+[0.]*(4-len(influences))
            vertex_weights[v.index] = (vw,vi)
        normal_matrix = (coord @ obj.matrix_world).to_3x3().inverted().transposed()
        for tri in data.loop_triangles:
            if tri.area <= 1e-12:
                skipped_degenerate+=1
                continue
            dest = submeshes[tri.material_index]
            loops=list(tri.loops)
            if (coord @ obj.matrix_world).to_3x3().determinant()<0:loops.reverse()
            for loop_index in loops:
                loop = data.loops[loop_index]
                vertex = data.vertices[loop.vertex_index]
                uv = tuple(data.uv_layers.active.data[loop_index].uv)
                normal = tuple((normal_matrix @ data.corner_normals[loop_index].vector).normalized())
                key = (vertex.index,uv,normal)
                if key not in vertex_cache:
                    vertex_cache[key] = len(positions)
                    positions.append(tuple(coord @ obj.matrix_world @ vertex.co))
                    normals.append(normal); uvs.append(uv); weights.append(vertex_weights[vertex.index])
                dest.append(vertex_cache[key])
        if not positions:raise ValueError('No non-degenerate triangles: '+obj.name)
        mesh_id = identifier()
        bindposes = [bone_world[b.name].inverted() for b in bones]
        payloads['Mesh\\'+mesh_id] = binary_mesh(obj.name,positions,normals,uvs,weights,bindposes,submeshes)
        child = node(obj.name,Matrix.Identity(4),len(bones)+len(components)+1)
        root['Children'].append(child)
        components.append(typed('Components.Meshes.XResourceSkinnedMeshRenderer',
            MeshGuid=mesh_id,GameObjectGuid=child['Guid'],ComponentType=1,
            Mesh={'Name':obj.name,'Guid':mesh_id,'IndexFormat':1 if len(positions)>65535 else 0,
                  'VertexCount':len(positions),'BoneCount':len(bones)},
            RootBoneGuid=bone_ids[hips],Bones=[{'Index':i,'BoneGuid':bone_ids[b.name]} for i,b in enumerate(bones)],
            RefMaterialGuids=mats))
        details.append({'name':obj.name,'vertices':len(positions),
                        'triangles':sum(len(s)//3 for s in submeshes),'omitted_degenerate_triangles':skipped_degenerate})
    resource_id = identifier()
    spring_component,spring_summary=spring_resource(armature,root,bone_ids,bone_nodes,bone_world,coord,len(bones)+len(meshes)+1)
    if spring_component:components.append(spring_component)
    material_list = list(resources.values())
    resource = {'Name':item_name,'Guid':resource_id,'RootGameObject':root,'Components':components,
        'XResourceHumanoidMap':{'HumanoidBones':[{'HumanBodyBones':value,'BoneGuid':bone_ids[name]}
                                              for name,value in human_map.items()], 'AvatarDefine':None},
        'MaterialGuids':[m['Guid'] for m in material_list],'TextureGuids':[t['Guid'] for t in textures.values()]}
    item = {'XItemVersion':2,'XResourceMaterials':material_list,'XResourceTextures':list(textures.values()),
        'XResourceInfoList':[{'Guid':resource_id,'Type':1,'License':{'contents':[
            {'itemName':item_name,'licenseType':0,'author':author,'licenseUrls':[]}]}}]}
    for key,value in [('Body\\XItem.json\\XItem.json',item),('Body\\XResources\\'+resource_id,resource)]:
        payloads[key] = json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf8')
    # The published v2 archiver's XItem path is a folder plus XItem.json.
    # Native-reader acceptance will decide whether this interpretation is correct.
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name(path.name+'.'+identifier()+'.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,data in payloads.items():
                # Python normalizes backslashes in ZipInfo.__init__ on Windows;
                # this native format uses literal backslashes in entry keys.
                entry = zipfile.ZipInfo(name)
                entry.filename = entry.orig_filename = name
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry,data)
        if path.exists(): raise FileExistsError(str(path))
        os.rename(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()
    return {'path':str(path),'resource_guid':resource_id,'meshes':details,'bones':len(bones),
            'textures':len(textures),'spring':spring_summary,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'limitations':['opaque colors or direct sRGB base-color images','no morphs/animation/PBR maps','native validation required']}


class EXPORT_SCENE_OT_vroid_mcp_xwear(bpy.types.Operator,ExportHelper):
    bl_idname = 'export_scene.vroid_mcp_xwear'
    bl_label = 'Direct XWear (Experimental)'
    filename_ext = '.xwear'
    filter_glob: StringProperty(default='*.xwear',options={'HIDDEN'})
    item_name: StringProperty(name='Item name',default='Original garment')
    creator: StringProperty(name='Creator',default='Local creator')
    front_axis: EnumProperty(name='Character front',items=[
        ('NEGATIVE_Y','-Y (standard Blender)','Character faces Blender -Y'),
        ('POSITIVE_X','+X (captured VRoid reference)','Character faces Blender +X')],default='NEGATIVE_Y')

    def execute(self,context):
        rigs = [o for o in context.selected_objects if o.type=='ARMATURE']
        meshes = [o for o in context.selected_objects if o.type=='MESH']
        try:
            if len(rigs)!=1: raise ValueError('Select exactly one armature and its garment meshes')
            coord=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1))) if self.front_axis=='POSITIVE_X' else COORD
            export_xwear(self.filepath,rigs[0],meshes,self.item_name,self.creator,coordinate_matrix=coord)
        except Exception as error:
            self.report({'ERROR'},str(error)); return {'CANCELLED'}
        self.report({'INFO'},'Experimental XWear written; validate in VRoid before use')
        return {'FINISHED'}


def menu(self,context):
    self.layout.operator(EXPORT_SCENE_OT_vroid_mcp_xwear.bl_idname,text='Direct XWear — Experimental (.xwear)')


def register():
    bpy.utils.register_class(EXPORT_SCENE_OT_vroid_mcp_xwear)
    bpy.types.TOPBAR_MT_file_export.append(menu)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu)
    bpy.utils.unregister_class(EXPORT_SCENE_OT_vroid_mcp_xwear)
