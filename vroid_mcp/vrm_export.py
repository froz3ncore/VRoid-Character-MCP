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


def validate_vrm(path: Path) -> dict:
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
    if 'VRMC_vrm' not in extensions or extensions['VRMC_vrm'].get('specVersion')!='1.0':raise ValueError('VRM 1.0 extension missing')
    meta=extensions['VRMC_vrm'].get('meta',{})
    if not meta.get('name') or not meta.get('authors'):raise ValueError('VRM metadata incomplete')
    buffers=data.get('buffers',[])
    if len(buffers)!=1 or 'uri' in buffers[0] or not 0<buffers[0]['byteLength']<=len(binary):raise ValueError('Expected one embedded buffer')
    views=data.get('bufferViews',[])
    for view in views:
        if view.get('buffer',0)!=0 or view.get('byteOffset',0)<0 or view.get('byteLength',0)<=0 or view.get('byteOffset',0)+view['byteLength']>buffers[0]['byteLength']:
            raise ValueError('Buffer view outside embedded payload')
    def index(value,items,kind):
        if type(value) is not int or not 0<=value<len(items):raise ValueError('Invalid '+kind+' index')
    nodes=data.get('nodes',[]);meshes=data.get('meshes',[]);skins=data.get('skins',[]);accessors=data.get('accessors',[])
    if not nodes or not meshes or not skins:raise ValueError('Skinned avatar data missing')
    for a in accessors:
        if 'bufferView' in a:index(a['bufferView'],views,'accessor buffer view')
        if type(a.get('count')) is not int or a['count']<=0:raise ValueError('Invalid accessor count')
    for node in nodes:
        if 'mesh' in node:index(node['mesh'],meshes,'node mesh')
        if 'skin' in node:index(node['skin'],skins,'node skin')
        for child in node.get('children',[]):index(child,nodes,'child node')
    for skin in skins:
        if not skin.get('joints'):raise ValueError('Skin without joints')
        for joint in skin['joints']:index(joint,nodes,'skin joint')
        if 'inverseBindMatrices' in skin:index(skin['inverseBindMatrices'],accessors,'bind matrix accessor')
    materials=data.get('materials',[]);triangles=0
    for mesh in meshes:
        for primitive in mesh.get('primitives',[]):
            for accessor in primitive.get('attributes',{}).values():index(accessor,accessors,'attribute accessor')
            if 'indices' in primitive:
                index(primitive['indices'],accessors,'triangle accessor')
                if primitive.get('mode',4)==4:triangles+=accessors[primitive['indices']]['count']//3
            if 'material' in primitive:index(primitive['material'],materials,'material')
    images=data.get('images',[])
    for image in images:
        if 'uri' in image or 'bufferView' not in image:raise ValueError('Expected embedded texture image')
        index(image['bufferView'],views,'image buffer view')
    for texture in data.get('textures',[]):
        if 'source' in texture:index(texture['source'],images,'texture image')
    spring=extensions.get('VRMC_springBone',{})
    colliders=spring.get('colliders',[]);groups=spring.get('colliderGroups',[]);springs=spring.get('springs',[])
    for collider in colliders:index(collider['node'],nodes,'collider node')
    for group in groups:
        for collider in group.get('colliders',[]):index(collider,colliders,'collider group')
    for chain in springs:
        for joint in chain.get('joints',[]):index(joint['node'],nodes,'spring joint node')
        for group in chain.get('colliderGroups',[]):index(group,groups,'spring collider group')
        if 'center' in chain:index(chain['center'],nodes,'spring center')
    for bone in extensions['VRMC_vrm'].get('humanoid',{}).get('humanBones',{}).values():index(bone['node'],nodes,'humanoid bone')
    return {'format':'VRM1','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'meshes':len(meshes),'skins':len(skins),
        'materials':len(materials),'images':len(images),'triangles':triangles,'springs':len(springs),'colliders':len(colliders),
        'collider_groups':len(groups),'spring_names':[s.get('name','') for s in springs],
        'extensions':list(extensions),'metadata':meta,'self_contained':True,
        'scope':'Container and resource-reference checks; visual fit, animation and engine runtime require separate acceptance'}
