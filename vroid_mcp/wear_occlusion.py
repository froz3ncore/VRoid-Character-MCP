"""Identity, index and concurrency guards for native Body mesh occlusion."""
import hashlib,json,struct
def geometry_hash(positions,triangles):
    payload=b''.join(struct.pack('<3f',*p) for p in positions)+struct.pack('<'+'I'*len(triangles),*triangles)
    return hashlib.sha256(payload).hexdigest()
def describe(data):
    count=data['default_vertex_count'];ids=data['hidden_vertices']
    if data['renderer_name']!='Body' or type(count) is not int or not 1<=count<=100000:raise ValueError('Invalid native Body identity')
    if len(data['source_positions'])!=count:raise ValueError('Default mesh vertex count changed')
    validate_indices(ids,count)
    geometry=geometry_hash(data['source_positions'],data['source_triangles'])
    token=hashlib.sha256(json.dumps([data['wear_token'],data['renderer_id'],data['default_mesh_id'],geometry,ids],separators=(',',':')).encode()).hexdigest()
    return {k:v for k,v in data.items() if k not in ('source_positions','source_triangles')}|{'occlusion_token':token,'source_geometry_sha256':geometry,'default_triangle_count':len(data['source_triangles'])//3}
def validate_indices(ids,count):
    if not isinstance(ids,list) or len(ids)>min(2048,int(count*.2)) or any(type(i) is not int or not 0<=i<count for i in ids):raise ValueError('Body occlusion requires at most 20 percent / 2048 valid original vertex indices')
    if ids!=sorted(set(ids)):raise ValueError('Body occlusion indices must be sorted and distinct')
def prepare(data,expected_token,ids):
    state=describe(data)
    if state['occlusion_token']!=expected_token:raise ValueError('Body mesh or occlusion changed; inspect fresh state')
    validate_indices(ids,data['default_vertex_count'])
    return {'expected_wear':data['wear_token'],'renderer_id':data['renderer_id'],'default_mesh_id':data['default_mesh_id'],'expected_hidden_vertices':data['hidden_vertices'],'hidden_vertices':ids}
