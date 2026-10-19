import copy,json,math,random,struct
import pytest
from vroid_mcp.wear_fit import Surface,closest,glb,inspect,norm2,sub,thickness,ray_triangle

I=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
def sample():
    body={'name':'Body','renderer_id':'base','world_matrix':copy.deepcopy(I),'positions':[[-.1,0,0],[.1,0,0],[0,.2,0]],'normals':[[0,0,1]]*3,'triangles':[0,1,2],
          'source_positions':[[-.1,0,0],[.1,0,0],[0,.2,0]],'weights':[{'indices':[0,0,0,0],'weights':[1,0,0,0]} for _ in range(3)],'bone_ids':[1]}
    shoe=copy.deepcopy(body);shoe.update(name='Shoe_R',renderer_id='shoe',bone_ids=[0]);shoe['positions']=[[x,y,z+.01] for x,y,z in shoe['positions']]
    matrix=copy.deepcopy(I);matrix[0][3]=.06
    return {'wear_token':'wear-1','item_id':'item-1','frame':123,'pose_source':'native_edit','body':body,'base_meshes':[body],'base_foot_source':'Body (combined; no separate Foot renderer)','garments':[shoe],
            'bones':[{'name':'J_Bip_R_Foot','world_matrix':matrix},{'name':'J_Bip_R_Foot','world_matrix':copy.deepcopy(I)}]}

@pytest.mark.parametrize('point,expected',[((.2,.2,1),1.),((2,0,0),1.),((-.5,-.5,0),math.sqrt(.5))])
def test_exact_point_triangle_distance(point,expected):
    tri=((0,0,0),(1,0,0),(0,1,0));assert math.sqrt(norm2(sub(point,closest(point,tri))))==pytest.approx(expected)

def test_bvh_matches_independent_exhaustive_search():
    rng=random.Random(519);faces=[tuple(tuple(rng.uniform(-1,1) for _ in range(3)) for _ in range(3)) for _ in range(150)];surface=Surface(faces)
    for _ in range(60):
        point=tuple(rng.uniform(-2,2) for _ in range(3));expected=min(math.sqrt(norm2(sub(point,closest(point,t)))) for t in faces)
        assert surface.distance(point)==pytest.approx(expected,abs=1e-12)

def test_world_transform_and_bone_registration_are_distinct():
    data=sample();report,debug=inspect(data,sample_limit=32);shoe=report['garments'][0]
    assert shoe['garment_to_target_surface']['median_mm']==pytest.approx(10.)
    assert report['targets'][0]['target_to_garments_surface']['median_mm']==pytest.approx(10.)
    assert shoe['bone_alignment'][0]['distance_mm']==pytest.approx(60.)
    assert shoe['renderer_id']=='shoe' and report['model_modified'] is False and report['frame']==123
    data['garments'][0]['world_matrix'][2][3]=.02
    assert inspect(data,sample_limit=32)[0]['garments'][0]['garment_to_target_surface']['median_mm']==pytest.approx(30.)

def test_visible_body_mask_is_reported_without_claiming_enclosure():
    data=sample();data['base_body_occlusion']={'default_vertex_count':20,'hidden_vertex_count':2,'hidden_original_vertex_indices':[1,2]}
    report,_=inspect(data,sample_limit=32)
    assert report['base_body_occlusion']==data['base_body_occlusion']
    assert not report['collision_free_certified']
    assert any('fewer samples' in warning for warning in report['interpretation'])

def test_ray_and_closed_sheet_thickness():
    front=[(-1,-1,.001),(1,-1,.001),(1,1,.001),(-1,1,.001)];back=[(x,y,-.001) for x,y,z in front]
    mesh={'positions':front+back,'normals':[[0,0,1]]*4+[[0,0,-1]]*4,'triangles':[0,1,2,0,2,3,4,6,5,4,7,6],'world_matrix':copy.deepcopy(I)}
    result=thickness(mesh,mesh['positions'],32)
    assert result['valid_hits']==8
    assert result['opposite_surface_span']['median_mm']==pytest.approx(2.,abs=1e-6)
    assert ray_triangle((0,0,1),(0,0,-1),(front[0],front[1],front[2]))==pytest.approx(.999)

def test_glb_contains_measured_geometry_and_no_animation():
    report,debug=inspect(sample(),sample_limit=32);raw=glb(debug);magic,version,length=struct.unpack_from('<4sII',raw)
    assert (magic,version,length)==(b'glTF',2,len(raw));count=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+count])
    assert len(doc['meshes'])==2 and 'animations' not in doc
    assert sum(a['count'] for a in doc['accessors'])==6
    assert {m['name'] for m in doc['meshes']}=={'target_R','Shoe_R'}

@pytest.mark.parametrize('region,limit',[('unknown',32),('feet',True),('feet',31),('feet',2049)])
def test_invalid_measurement_request_rejected(region,limit):
    with pytest.raises(ValueError):inspect(sample(),region,limit)

def test_missing_actual_base_context_is_an_error():
    data=sample();data['base_meshes']=[]
    with pytest.raises(ValueError,match='Actual base skin context'):inspect(data)

def test_explicit_garment_target_uses_actual_geometry():
    data=sample();reference=copy.deepcopy(data['garments'][0]);reference['name']='Dress';reference['positions']=[[x,y,z-.01] for x,y,z in reference['positions']];data['garments'].append(reference)
    report,debug=inspect(data,'waist_back',32,'Dress')
    assert report['comparison_target']=='Dress' and len(report['garments'])==1
    assert report['garments'][0]['garment_to_target_surface']['median_mm']==pytest.approx(10.)

def test_unknown_garment_target_rejected():
    with pytest.raises(ValueError,match='target mesh'):inspect(sample(),target_mesh_name='Missing')

def test_only_readonly_geometry_capture_gets_the_extended_timeout(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from vroid_mcp.runtime import Runtime
    r=Runtime.__new__(Runtime);r.dead=False;r.uncertain=False;r.script=SimpleNamespace(exports_sync=SimpleNamespace(call=lambda op,args:op))
    original=asyncio.wait_for;seen=[]
    async def observe(coro,timeout):seen.append(timeout);return await original(coro,timeout)
    monkeypatch.setattr(asyncio,'wait_for',observe)
    assert asyncio.run(r._call('capture_wear_reference'))=='capture_wear_reference'
    assert asyncio.run(r._call('set_parameters'))=='set_parameters'
    assert seen==[120,30]
