"""Validate a self-contained native VRM1 output before publishing its filename."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct


def export_metadata(title: str, author: str, version: str) -> dict:
    values={'title':title,'author':author,'version':version}
    for name,value in values.items():
        if not isinstance(value,str) or not value.strip() or len(value)>160 or any(ord(c)<32 or ord(c)==127 for c in value):
            raise ValueError('Nonempty export metadata without control characters required: '+name)
    return values


def validate_vrm(path: Path, vrm_version: int = 1) -> dict:
    raw=path.read_bytes()
    if len(raw)<28:raise ValueError('Native VRM output is truncated')
    magic,version,total=struct.unpack_from('<4sII',raw)
    if magic!=b'glTF' or version!=2 or total!=len(raw):raise ValueError('Invalid GLB header or length')
    chunks=[];offset=12
    while offset<len(raw):
        if offset+8>len(raw):raise ValueError('Truncated GLB chunk header')
        size,kind=struct.unpack_from('<I4s',raw,offset);offset+=8
        if size%4 or offset+size>len(raw):raise ValueError('Invalid GLB chunk length')
        chunks.append((kind,raw[offset:offset+size]));offset+=size
    if len(chunks)!=2 or chunks[0][0]!=b'JSON' or chunks[1][0]!=b'BIN\x00':raise ValueError('Expected embedded JSON and BIN chunks')
    data=json.loads(chunks[0][1]);binary=chunks[1][1]
    extensions=data.get('extensions',{})
    extension='VRMC_vrm' if vrm_version==1 else 'VRM'
    expected='1.0' if vrm_version==1 else '0.0'
    if extension not in extensions or extensions[extension].get('specVersion')!=expected:raise ValueError('VRM extension missing or version mismatch: '+extension)
    meta=extensions[extension].get('meta',{})
    if vrm_version==1:
        if not meta.get('name') or not meta.get('authors'):raise ValueError('VRM metadata incomplete')
    elif not meta.get('title') or not meta.get('author'):raise ValueError('VRM0 metadata incomplete')
    buffers=data.get('buffers',[])
    if (len(buffers)!=1 or 'uri' in buffers[0] or type(buffers[0].get('byteLength')) is not int
            or not 0<buffers[0]['byteLength']<=len(binary)
            or len(binary)-buffers[0]['byteLength']>3):raise ValueError('Expected one embedded buffer')
    views=data.get('bufferViews',[])
    for view in views:
        if (type(view.get('buffer',0)) is not int or view.get('buffer',0)!=0
                or type(view.get('byteOffset',0)) is not int or type(view.get('byteLength')) is not int
                or view.get('byteOffset',0)<0 or view.get('byteLength',0)<=0
                or view.get('byteOffset',0)+view['byteLength']>buffers[0]['byteLength']):
            raise ValueError('Buffer view outside embedded payload')
    def index(value,items,kind):
        if type(value) is not int or not 0<=value<len(items):raise ValueError('Invalid '+kind+' index')
    nodes=data.get('nodes',[]);meshes=data.get('meshes',[]);skins=data.get('skins',[]);accessors=data.get('accessors',[])
    if not nodes or not meshes or not skins:raise ValueError('Skinned avatar data missing')
    for a in accessors:
        if 'bufferView' in a:index(a['bufferView'],views,'accessor buffer view')
        if type(a.get('count')) is not int or a['count']<=0:raise ValueError('Invalid accessor count')
        if 'sparse' in a:
            sparse=a['sparse']
            if type(sparse.get('count')) is not int or not 0<sparse['count']<=a['count']:raise ValueError('Invalid sparse count')
            for kind in ('indices','values'):index(sparse[kind]['bufferView'],views,'sparse '+kind+' buffer view')
    for node in nodes:
        if 'mesh' in node:index(node['mesh'],meshes,'node mesh')
        if 'skin' in node:index(node['skin'],skins,'node skin')
        for child in node.get('children',[]):index(child,nodes,'child node')
    for skin in skins:
        if not skin.get('joints'):raise ValueError('Skin without joints')
        for joint in skin['joints']:index(joint,nodes,'skin joint')
        if 'inverseBindMatrices' in skin:index(skin['inverseBindMatrices'],accessors,'bind matrix accessor')
        if 'skeleton' in skin:index(skin['skeleton'],nodes,'skin skeleton')
    materials=data.get('materials',[]);triangles=0
    for mesh in meshes:
        for primitive in mesh.get('primitives',[]):
            for accessor in primitive.get('attributes',{}).values():index(accessor,accessors,'attribute accessor')
            for target in primitive.get('targets',[]):
                for accessor in target.values():index(accessor,accessors,'morph target accessor')
            if 'indices' in primitive:
                index(primitive['indices'],accessors,'triangle accessor')
                if primitive.get('mode',4)==4:triangles+=accessors[primitive['indices']]['count']//3
            if 'material' in primitive:index(primitive['material'],materials,'material')
    images=data.get('images',[])
    for image in images:
        if 'uri' in image or 'bufferView' not in image:raise ValueError('Expected embedded texture image')
        index(image['bufferView'],views,'image buffer view')
    textures=data.get('textures',[])
    for texture in textures:
        if 'source' in texture:index(texture['source'],images,'texture image')
        if 'sampler' in texture:index(texture['sampler'],data.get('samplers',[]),'texture sampler')
    def texture_infos(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key.endswith('Texture') and isinstance(item,dict) and 'index' in item:index(item['index'],textures,'material texture')
                texture_infos(item)
        elif isinstance(value,list):
            for item in value:texture_infos(item)
    texture_infos(materials)
    scenes=data.get('scenes',[])
    for scene in scenes:
        for node in scene.get('nodes',[]):index(node,nodes,'scene node')
    if 'scene' in data:index(data['scene'],scenes,'default scene')
    for animation in data.get('animations',[]):
        samplers=animation.get('samplers',[])
        for sampler in samplers:
            index(sampler['input'],accessors,'animation input');index(sampler['output'],accessors,'animation output')
        for channel in animation.get('channels',[]):
            index(channel['sampler'],samplers,'animation sampler')
            if 'node' in channel.get('target',{}):index(channel['target']['node'],nodes,'animation node')
    spring=extensions.get('VRMC_springBone',{})
    colliders=spring.get('colliders',[]);groups=spring.get('colliderGroups',[]);springs=spring.get('springs',[])
    for collider in colliders:index(collider['node'],nodes,'collider node')
    for group in groups:
        for collider in group.get('colliders',[]):index(collider,colliders,'collider group')
    for chain in springs:
        for joint in chain.get('joints',[]):index(joint['node'],nodes,'spring joint node')
        for group in chain.get('colliderGroups',[]):index(group,groups,'spring collider group')
        if 'center' in chain:index(chain['center'],nodes,'spring center')
    if vrm_version==1:
        for bone in extensions[extension].get('humanoid',{}).get('humanBones',{}).values():index(bone['node'],nodes,'humanoid bone')
        if 'thumbnailImage' in meta:index(meta['thumbnailImage'],images,'VRM1 thumbnail image')
        for annotation in extensions[extension].get('firstPerson',{}).get('meshAnnotations',[]):index(annotation['node'],nodes,'VRM1 first person node')
        expressions=extensions[extension].get('expressions',{})
        for kind in ('preset','custom'):
            for expression in expressions.get(kind,{}).values():
                for bind in expression.get('morphTargetBinds',[]):
                    index(bind['node'],nodes,'VRM1 expression node')
                    mesh=nodes[bind['node']].get('mesh')
                    index(mesh,meshes,'VRM1 expression mesh')
                    for primitive in meshes[mesh].get('primitives',[]):index(bind['index'],primitive.get('targets',[]),'VRM1 morph target')
                for bind in expression.get('materialColorBinds',[])+expression.get('textureTransformBinds',[]):index(bind['material'],materials,'VRM1 expression material')
    else:
        for bone in extensions[extension].get('humanoid',{}).get('humanBones',[]):index(bone['node'],nodes,'humanoid bone')
        # Official UniVRM's VRM0 format documents -1 as no first-person
        # bone/target mesh. Material textures instead use absent properties
        # for unset slots; their present values must index glTF textures.
        def first_person_index(value,items,kind):
            if type(value) is int and value==-1:return
            index(value,items,kind)
        first_person=extensions[extension].get('firstPerson',{})
        if 'firstPersonBone' in first_person:first_person_index(first_person['firstPersonBone'],nodes,'VRM0 first person bone')
        for annotation in first_person.get('meshAnnotations',[]):
            if 'mesh' in annotation:first_person_index(annotation['mesh'],meshes,'VRM0 first person mesh')
        for material in extensions[extension].get('materialProperties',[]):
            for texture in material.get('textureProperties',{}).values():index(texture,textures,'VRM0 material texture')
        secondary=extensions[extension].get('secondaryAnimation',{})
        collider_groups=secondary.get('colliderGroups',[])
        for group in collider_groups:index(group['node'],nodes,'VRM0 collider node')
        for group in secondary.get('boneGroups',[]):
            for bone in group.get('bones',[]):index(bone,nodes,'VRM0 spring bone')
            for collider in group.get('colliderGroups',[]):index(collider,collider_groups,'VRM0 collider group')
            if group.get('center',-1)!=-1:index(group['center'],nodes,'VRM0 spring center')
        for group in extensions[extension].get('blendShapeMaster',{}).get('blendShapeGroups',[]):
            for bind in group.get('binds',[]):
                index(bind['mesh'],meshes,'VRM0 blendshape mesh')
                targets=meshes[bind['mesh']].get('primitives',[])
                if any(type(bind.get('index')) is not int or not 0<=bind['index']<len(p.get('targets',[])) for p in targets):
                    raise ValueError('Invalid VRM0 blendshape target index')
        if meta.get('texture',-1)!=-1:index(meta['texture'],data.get('textures',[]),'VRM0 thumbnail texture')
    return {'format':'VRM1' if vrm_version==1 else 'VRM0','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'meshes':len(meshes),'skins':len(skins),
        'materials':len(materials),'images':len(images),'triangles':triangles,'springs':len(springs),'colliders':len(colliders),
        'collider_groups':len(groups),'spring_names':[s.get('name','') for s in springs],
        'extensions':list(extensions),'metadata':meta,'self_contained':True,
        'scope':'Container and resource-reference checks; visual fit, animation and engine runtime require separate acceptance'}
