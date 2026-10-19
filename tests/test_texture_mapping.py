"""Geometry targeting regressions independent of a particular VRoid topology."""
import copy,math,struct,zlib
import pytest
from vroid_mcp.texture_mapping import discover_nails,pick_uv,raster_nails,png_rgba,vector3,unit

IDENTITY=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]

def texture(slot=0):
    return {'slot':slot,'name':f'material-{slot}','textures':[{'property':'_MainTex','instance_id':42,'width':100,'height':100,'offset':[0,0],'scale':[1,1]}]}

def ray_scene():
    mesh={'name':'Hand','world_matrix':copy.deepcopy(IDENTITY),'positions':[[0,0,0],[1,0,0],[0,1,0],[0,0,-1],[1,0,-1],[0,1,-1]],'uv0':[[0,0],[1,0],[0,1]]*2,'triangles':[0,1,2,3,4,5]}
    return {'model_token':'test','meshes':[mesh]}, {'model_token':'test','renderers':[{'name':'Hand','materials':[texture(),texture(1)],'submesh_triangle_counts':[1,1]}]}

def nail_scene():
    mesh={'name':'Hand','world_matrix':copy.deepcopy(IDENTITY),'positions':[],'uv0':[],'triangles':[],'weights':[],'bone_nodes':[]}
    nodes=[]
    for number,(side,finger) in enumerate((s,f) for s in 'LR' for f in ('Thumb','Index','Middle','Ring','Little')):
        nodes.append({'id':number,'name':f'J_Bip_{side}_{finger}3'});mesh['bone_nodes'].append(number)
        for cap in range(2):
            start=len(mesh['positions']);x=number*.02;z=cap*.0001;u=number*.09+.01;v=cap*.1+.01
            mesh['positions'] += [[x,0,z],[x+.01,0,z],[x+.01,.01,z],[x,.01,z]]
            mesh['uv0'] += [[u,v],[u+.06,v],[u+.06,v+.06],[u,v+.06]]
            mesh['weights'] += [{'indices':[number,0,0,0],'weights':[1,0,0,0]} for _ in range(4)]
            mesh['triangles'] += [start+i for i in ([0,1,2,0,2,3] if cap==0 else [0,2,1,0,3,2])]
    return {'model_token':'test','meshes':[mesh],'nodes':nodes},{'model_token':'test','renderers':[{'name':'Hand','materials':[texture()],'submesh_triangle_counts':[40]}]}

def test_ray_barycentric_texture_transform_and_material_slot():
    ref,bindings=ray_scene();ref['meshes'][0]['world_matrix'][0][3]=2
    bindings['renderers'][0]['materials'][1]['textures'][0].update(offset=[.1,.2],scale=[.5,.25])
    hit=pick_uv(ref,bindings,'Hand',[2.25,.25,-.5],[0,0,-4])['nearest']
    assert hit['triangle']==1 and hit['material_slot']==1
    assert hit['distance_m']==pytest.approx(.5)
    assert hit['uv0']==pytest.approx([.25,.25])
    assert hit['texture_uv']==pytest.approx([.225,.2625])
    assert hit['image_pixel_top_left']==pytest.approx([22.5,73.75])

def test_ray_nearest_miss_limit_and_double_sided():
    ref,bindings=ray_scene()
    assert pick_uv(ref,bindings,'Hand',[.2,.2,1],[0,0,-1])['nearest']['triangle']==0
    assert not pick_uv(ref,bindings,'Hand',[.2,.2,1],[0,0,-1],.5)['hit']
    assert not pick_uv(ref,bindings,'Hand',[2,2,1],[0,0,-1])['hit']
    assert not pick_uv(ref,bindings,'Hand',[.2,.2,-.5],[0,0,1])['nearest']['winding_front_facing']

def test_coincident_faces_are_not_silently_merged():
    ref,bindings=ray_scene();ref['meshes'][0]['positions'][3:]=copy.deepcopy(ref['meshes'][0]['positions'][:3])
    assert len(pick_uv(ref,bindings,'Hand',[.2,.2,1],[0,0,-1])['coincident_hits'])==2

@pytest.mark.parametrize('change', ['token','submesh','duplicate','no_uv','no_texture'])
def test_invalid_geometry_or_binding_identity_rejected(change):
    ref,bindings=ray_scene()
    if change=='token':bindings['model_token']='other'
    elif change=='submesh':bindings['renderers'][0]['submesh_triangle_counts']=[1]
    elif change=='duplicate':ref['meshes'].append(copy.deepcopy(ref['meshes'][0]))
    elif change=='no_uv':ref['meshes'][0]['uv0']=[]
    else:bindings['renderers'][0]['materials'][0]['textures']=[]
    with pytest.raises(ValueError):pick_uv(ref,bindings,'Hand',[.2,.2,1],[0,0,-1])

@pytest.mark.parametrize('values', [[0,0],[0,0,True],[math.nan,0,0],[0,math.inf,0]])
def test_finite_vectors(values):
    with pytest.raises(ValueError):vector3(values)

def test_zero_direction():
    with pytest.raises(ValueError):unit([0,0,0])

def test_nails_derive_from_bones_components_and_winding_without_fixed_vertex_counts():
    ref,bindings=nail_scene();mapping=discover_nails(ref,bindings)
    assert mapping['nail_count']==10 and mapping['uv_island_count']==20
    assert all(len(p['vertex_ids'])==4 for n in mapping['nails'] for p in n['islands'])
    assert all(n['paired_normal_dot']==pytest.approx(-1) for n in mapping['nails'])
    masks=raster_nails(mapping)
    assert len(masks)==10 and sum(map(len,masks.values()))==len(set.union(*masks.values()))
    assert all(len(m)==72 for m in masks.values())

@pytest.mark.parametrize('change', ['token','material','transform','weight','missing_cap','winding','separation','nan_uv','outside_uv','duplicate'])
def test_unsupported_nails_rejected(change):
    ref,bindings=nail_scene();mesh=ref['meshes'][0];renderer=bindings['renderers'][0]
    if change=='token':bindings['model_token']='other'
    elif change=='material':renderer['materials'].append(texture(1))
    elif change=='transform':renderer['materials'][0]['textures'][0]['scale']=[-1,1]
    elif change=='weight':mesh['weights'][0]['weights']=[.5,.5,0,0]
    elif change=='missing_cap':mesh['triangles']=mesh['triangles'][6:]
    elif change=='winding':mesh['triangles'][6:12]=[4,5,6,4,6,7]
    elif change=='separation':
        for p in mesh['positions'][4:8]:p[2]+=.003
    elif change=='nan_uv':mesh['uv0'][0][0]=math.nan
    elif change=='outside_uv':mesh['uv0'][0][0]=1.1
    else:ref['meshes'].append(copy.deepcopy(mesh))
    with pytest.raises(ValueError):discover_nails(ref,bindings)

def test_nail_uv_overlap_rejected_and_top_left_pixel_origin():
    mapping=discover_nails(*nail_scene());masks=raster_nails(mapping)
    # Native low V islands must land near the bottom of a top-left-origin PNG.
    assert min(p//100 for p in masks['L_Thumb'])>=83
    mapping['nails'][1]['islands']=copy.deepcopy(mapping['nails'][0]['islands'])
    with pytest.raises(ValueError,match='UV sharing'):raster_nails(mapping)

@pytest.mark.parametrize('uv', [[[0,0],[1,0],[math.nan,1]], [[-1,0],[0,0],[0,1]]])
def test_raster_does_not_silently_clip_uncalibrated_uv(uv):
    with pytest.raises(ValueError):raster_nails({'texture':{'width':10,'height':10},'nails':[{'id':'a','islands':[{'uv_triangles':[uv]}]}]})

def test_png_roundtrip_struct_and_scanlines():
    data=bytes([10,20,30,40,50,60,70,80]);png=png_rgba(2,1,data)
    assert png[:8]==b'\x89PNG\r\n\x1a\n'
    offset=8;chunks={}
    while offset<len(png):
        n=struct.unpack('>I',png[offset:offset+4])[0];kind=png[offset+4:offset+8];payload=png[offset+8:offset+8+n]
        assert zlib.crc32(kind+payload)&0xffffffff==struct.unpack('>I',png[offset+8+n:offset+12+n])[0]
        chunks[kind]=payload;offset+=n+12
    assert struct.unpack('>IIBBBBB',chunks[b'IHDR'])==(2,1,8,6,0,0,0)
    assert zlib.decompress(chunks[b'IDAT'])==b'\0'+data
    with pytest.raises(ValueError):png_rgba(2,1,b'')
