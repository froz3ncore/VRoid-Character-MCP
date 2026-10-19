"""Identity and shoe-only material guards for persistent native shoe hiding."""
import hashlib,json,re
from .wear_occlusion import geometry_hash

def describe(data):
    count=data['default_vertex_count'];hidden=data['hidden_vertices']
    if data['renderer_name']!='Cloth' or type(count) is not int or not 1<=count<=10000:raise ValueError('Native shoe-only renderer required')
    materials=data['material_names']
    if not materials or any(not isinstance(n,str) or not re.search(r'_Shoes_\d+_CLOTH$',n) for n in materials):raise ValueError('Mixed or non-shoe materials cannot be hidden')
    if len(data['source_positions'])!=count:raise ValueError('Native shoe geometry changed')
    if hidden not in ([],list(range(count))):raise ValueError('Partial shoe mask must not be overwritten')
    geometry=geometry_hash(data['source_positions'],data['source_triangles'])
    token=hashlib.sha256(json.dumps([data['wear_token'],data['renderer_id'],data['default_mesh_id'],geometry,materials,hidden],separators=(',',':')).encode()).hexdigest()
    return {k:v for k,v in data.items() if k not in ('source_positions','source_triangles')}|{'visibility_token':token,'source_geometry_sha256':geometry,'visible':not hidden}

def prepare(data,expected_token,visible):
    state=describe(data)
    if type(visible) is not bool:raise ValueError('visible must be a boolean')
    if state['visibility_token']!=expected_token:raise ValueError('Native shoe geometry, identity or visibility changed; inspect fresh state')
    return {'expected_wear':data['wear_token'],'renderer_id':data['renderer_id'],'default_mesh_id':data['default_mesh_id'],
            'expected_hidden_vertices':data['hidden_vertices'],'hidden_vertices':[] if visible else list(range(data['default_vertex_count']))}
