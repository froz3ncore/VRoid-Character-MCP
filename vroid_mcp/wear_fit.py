"""Pose-matched, read-only 3D context for a native base and wearable meshes.

Standard-library geometry only. Distances are exact point-to-triangle distances
on deterministic samples, not a closed-volume or all-animation collision test.
"""
from __future__ import annotations
import heapq,json,math,struct

def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def mul(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def norm2(a):return dot(a,a)
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def transform(p,m):return tuple(sum(m[i][j]*p[j] for j in range(3))+m[i][3] for i in range(3))
def world(mesh):return [transform(p,mesh['world_matrix']) for p in mesh['positions']]
def bounds(points):return {'min':[min(p[k] for p in points) for k in range(3)],'max':[max(p[k] for p in points) for k in range(3)]}
def center(box):return [(a+b)/2 for a,b in zip(box['min'],box['max'])]
def triangles(mesh,points):return [tuple(points[i] for i in mesh['triangles'][j:j+3]) for j in range(0,len(mesh['triangles']),3)]
def closest(p,triangle):
    a,b,c=triangle;ab=sub(b,a);ac=sub(c,a);ap=sub(p,a);d1=dot(ab,ap);d2=dot(ac,ap)
    if d1<=0 and d2<=0:return a
    bp=sub(p,b);d3=dot(ab,bp);d4=dot(ac,bp)
    if d3>=0 and d4<=d3:return b
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:return add(a,mul(ab,d1/(d1-d3)))
    cp=sub(p,c);d5=dot(ab,cp);d6=dot(ac,cp)
    if d6>=0 and d5<=d6:return c
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:return add(a,mul(ac,d2/(d2-d6)))
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:return add(b,mul(sub(c,b),(d4-d3)/(d4-d3+d5-d6)))
    den=va+vb+vc
    if abs(den)<1e-24:
        def segment(x,y):
            direction=sub(y,x);t=max(0.,min(1.,dot(sub(p,x),direction)/max(norm2(direction),1e-30)));return add(x,mul(direction,t))
        return min((segment(a,b),segment(b,c),segment(c,a)),key=lambda q:norm2(sub(p,q)))
    return add(a,add(mul(ab,vb/den),mul(ac,vc/den)))
def box_distance2(p,box):return sum(max(lo-x,0,x-hi)**2 for x,lo,hi in zip(p,box['min'],box['max']))
def ray_box(origin,direction,box):
    near,far=0.,math.inf
    for p,d,lo,hi in zip(origin,direction,box['min'],box['max']):
        if abs(d)<1e-15:
            if p<lo or p>hi:return None
        else:
            a,b=(lo-p)/d,(hi-p)/d;near=max(near,min(a,b));far=min(far,max(a,b))
            if far<near:return None
    return near
def ray_triangle(origin,direction,triangle):
    a,b,c=triangle;e1,e2=sub(b,a),sub(c,a);h=cross(direction,e2);det=dot(e1,h)
    if abs(det)<1e-14:return None
    s=sub(origin,a);u=dot(s,h)/det
    if u< -1e-7 or u>1.0000001:return None
    q=cross(s,e1);v=dot(direction,q)/det
    if v< -1e-7 or u+v>1.0000001:return None
    t=dot(e2,q)/det
    return t if t>1e-6 else None
class Surface:
    def __init__(self,faces):
        if not faces:raise ValueError('Empty comparison surface')
        self.faces=faces;self.nodes=[]
        def build(ids):
            box=bounds([p for i in ids for p in faces[i]]);index=len(self.nodes);self.nodes.append(None)
            if len(ids)<=12:self.nodes[index]=(box,ids,None,None)
            else:
                axis=max(range(3),key=lambda k:box['max'][k]-box['min'][k]);ids.sort(key=lambda i:sum(p[axis] for p in faces[i]));mid=len(ids)//2
                left,right=build(ids[:mid]),build(ids[mid:]);self.nodes[index]=(box,None,left,right)
            return index
        build(list(range(len(faces))))
    def distance(self,p):
        best=math.inf;queue=[(0.,0)]
        while queue:
            bound,index=heapq.heappop(queue)
            if bound>best:continue
            box,ids,left,right=self.nodes[index]
            if ids is not None:
                for i in ids:best=min(best,norm2(sub(p,closest(p,self.faces[i]))))
            else:
                for child in (left,right):
                    distance=box_distance2(p,self.nodes[child][0])
                    if distance<=best:heapq.heappush(queue,(distance,child))
        return math.sqrt(best)
    def ray(self,origin,direction):
        bound=ray_box(origin,direction,self.nodes[0][0])
        if bound is None:return None
        best=math.inf;queue=[(bound,0)]
        while queue:
            bound,index=heapq.heappop(queue)
            if bound>best:continue
            box,ids,left,right=self.nodes[index]
            if ids is not None:
                for i in ids:
                    distance=ray_triangle(origin,direction,self.faces[i])
                    if distance is not None:best=min(best,distance)
            else:
                for child in (left,right):
                    hit=ray_box(origin,direction,self.nodes[child][0])
                    if hit is not None and hit<=best:heapq.heappush(queue,(hit,child))
        return best if math.isfinite(best) else None
def thickness(mesh,points,limit):
    surface=Surface(triangles(mesh,points));m=mesh['world_matrix'];values=[];attempts=0
    # Inverse-transpose normal transform via cofactor rows (uniform determinant
    # scale cancels at normalization). Handles rotation and nonuniform scale.
    rows=[m[i][:3] for i in range(3)];cofactor=[cross(rows[1],rows[2]),cross(rows[2],rows[0]),cross(rows[0],rows[1])]
    determinant=dot(rows[0],cofactor[0]);sign=1. if determinant>=0 else -1.
    for i in sample(list(range(len(points))),min(128,limit)):
        n=tuple(sign*dot(row,mesh['normals'][i]) for row in cofactor);length=math.sqrt(norm2(n))
        if length<1e-12:continue
        n=mul(n,1/length);attempts+=1;hit=surface.ray(add(points[i],mul(n,-1e-5)),mul(n,-1.))
        if hit is not None:values.append(hit+1e-5)
    return {'method':'First opposite surface hit along inward transformed vertex normal','attempted_rays':attempts,'valid_hits':len(values),'normal_hit_fraction':len(values)/attempts if attempts else 0.,'low_hit_fraction':len(values)<attempts*.5,'opposite_surface_span':stats(values),'limitation':'Measures a normal cross-section span. Low hit fractions are not a reliable thickness estimate. Open shoe cavities, curvature, folds and seams affect the estimate; this is not material wall thickness or a universal thickness certificate.'}
def sample(points,limit):
    if len(points)<=limit:return points
    return [points[i*(len(points)-1)//(limit-1)] for i in range(limit)]
def stats(values):
    values=sorted(values)
    if not values:return None
    def percentile(f):
        i=(len(values)-1)*f;a=int(i);b=min(a+1,len(values)-1);return (values[a]*(b-i)+values[b]*(i-a)) if a!=b else values[a]
    return {'samples':len(values),'min_mm':1000*values[0],'median_mm':1000*percentile(.5),'p95_mm':1000*percentile(.95),'max_mm':1000*values[-1],'samples_farther_than_3mm':sum(x>.003 for x in values)}
def foot_side(name):
    for side in ('L','R'):
        if name in ('J_Bip_'+side+'_Foot','J_Bip_'+side+'_ToeBase'):return side
    return None
def selected_surface(data,region):
    base=data.get('base_meshes',[])
    if not base:raise ValueError('Actual base skin context required; recapture with include_base_meshes=true')
    regions={};base_bones={}
    for mesh in base:
        points=world(mesh)
        for ident in mesh['bone_ids']:
            bone=data['bones'][ident];base_bones[bone['name']]=bone
        if region=='feet':
            if mesh['name'] not in ('Body','Foot'):continue
            for side in ('L','R'):
                mask=[]
                for w in mesh['weights']:
                    mass=sum(weight for slot,weight in zip(w['indices'],w['weights']) if foot_side(data['bones'][mesh['bone_ids'][slot]]['name'])==side)
                    mask.append(mass>=.35)
                if not any(mask):continue
                entry=regions.setdefault(side,{'points':[],'triangles':[]});entry['points'].extend(p for p,keep in zip(points,mask) if keep)
                entry['triangles'].extend(tuple(points[i] for i in mesh['triangles'][j:j+3]) for j in range(0,len(mesh['triangles']),3) if all(mask[i] for i in mesh['triangles'][j:j+3]))
        else:
            hips=base_bones.get('J_Bip_C_Hips');origin=[r[3] for r in hips['world_matrix'][:3]] if hips else (0,.9,0)
            if region=='waist_back' and mesh['name']!='Body':continue
            if region=='head' and mesh['name'] not in ('Face','Hair'):continue
            head=base_bones.get('J_Bip_C_Head');head_y=head['world_matrix'][1][3] if head else origin[1]+.47
            mask=[True if region=='whole_body' else p[1]>=head_y-.05 if region=='head' else abs(p[0]-origin[0])<.20 and origin[1]-.03<=p[1]<=origin[1]+.20 and p[2]<origin[2] for p in points]
            entry=regions.setdefault('head' if region=='head' else 'back' if region=='waist_back' else 'body',{'points':[],'triangles':[]});entry['points'].extend(p for p,keep in zip(points,mask) if keep)
            entry['triangles'].extend(tuple(points[i] for i in mesh['triangles'][j:j+3]) for j in range(0,len(mesh['triangles']),3) if all(mask[i] for i in mesh['triangles'][j:j+3]))
    regions={k:v for k,v in regions.items() if v['points'] and v['triangles']}
    if not regions:raise ValueError('No actual skinned base geometry for requested region')
    return regions,base_bones
def inspect(data,region='feet',sample_limit=256,target_mesh_name=None):
    if region not in ('feet','waist_back','head','whole_body'):raise ValueError('Unsupported fit region')
    if type(sample_limit) is not int or not 32<=sample_limit<=2048:raise ValueError('sample_limit must be 32..2048')
    regions,base_bones=selected_surface(data,'whole_body' if target_mesh_name is not None else region)
    if target_mesh_name is not None:
        references=[m for m in data['garments'] if m['name']==target_mesh_name]
        if len(references)!=1:raise ValueError('Choose one actual target mesh from the selected garment names')
        reference=references[0];points=world(reference);regions={'garment_reference':{'points':points,'triangles':triangles(reference,points)}}
    surfaces={k:Surface(v['triangles']) for k,v in regions.items()};rows=[];debug=[]
    for key,body in regions.items():debug.append(('target_'+key,body['triangles'],'body'))
    union={key:[] for key in regions}
    for mesh in data['garments']:
        if mesh['name']==target_mesh_name:continue
        points=world(mesh);box=bounds(points);mid=center(box);mass={side:0. for side in ('L','R')}
        used={}
        for w in mesh['weights']:
            for slot,weight in zip(w['indices'],w['weights']):
                if weight<=1e-7:continue
                name=data['bones'][mesh['bone_ids'][slot]]['name'];used[name]=used.get(name,0.)+weight
                if foot_side(name):mass[foot_side(name)]+=weight
        key=max(mass,key=mass.get) if region=='feet' and target_mesh_name is None and max(mass.values())>0 else min(regions,key=lambda k:norm2(sub(mid,center(bounds(regions[k]['points'])))))
        if key not in regions:raise ValueError('Wearable foot binding has no corresponding actual base region: '+key)
        body_box=bounds(regions[key]['points']);faces=triangles(mesh,points);union[key].extend(faces);debug.append((mesh['name'],faces,'garment'))
        bone_offsets=[]
        for ident in mesh['bone_ids']:
            bone=data['bones'][ident];name=bone['name']
            if name not in used or name not in base_bones:continue
            a=[r[3] for r in bone['world_matrix'][:3]];b=[r[3] for r in base_bones[name]['world_matrix'][:3]];delta=mul(sub(a,b),1000)
            bone_offsets.append({'bone':name,'delta_xyz_mm':list(delta),'distance_mm':math.sqrt(norm2(delta))})
        offsets=[(1000*(a-b)) for a,b in zip(mid,center(body_box))]
        rows.append({'name':mesh['name'],'renderer_id':mesh.get('renderer_id'),'target_region':key,'vertices':len(points),'triangles':len(faces),'bounds_world_m':box,'size_mm':mul(sub(box['max'],box['min']),1000),'bounds_center_offset_xyz_mm':offsets,'target_bbox_margins_mm':{axis:[1000*(body_box['min'][k]-box['min'][k]),1000*(box['max'][k]-body_box['max'][k])] for k,axis in enumerate(('x','y','z'))},'used_bone_weight_mass':used,'bone_alignment':bone_offsets,'garment_to_target_surface':stats([surfaces[key].distance(p) for p in sample(points,sample_limit)]),'thickness':thickness(mesh,points,sample_limit),'source_to_actual_max_vertex_displacement_mm':max(math.sqrt(norm2(sub(a,transform(b,mesh['world_matrix']))))*1000 for a,b in zip(points,mesh['source_positions']))})
    targets=[]
    for key,body in regions.items():
        if not union[key]:continue
        shoe_surface=Surface(union[key]);points=sample(body['points'],sample_limit);box=bounds(body['points'])
        bands={}
        if region=='feet' and target_mesh_name is None:
            for label,predicate in [('toe',lambda p:p[2]>=box['max'][2]-.045),('heel',lambda p:p[2]<=box['min'][2]+.035),('sole',lambda p:p[1]<=box['min'][1]+.012)]:
                bands[label]=stats([shoe_surface.distance(p) for p in points if predicate(p)])
        targets.append({'region':key,'vertices':len(body['points']),'triangles':len(body['triangles']),'bounds_world_m':box,'target_to_garments_surface':stats([shoe_surface.distance(p) for p in points]),'anatomical_bands':bands})
    return {'schema':'vroid-wear-fit-context-v1','wear_token':data['wear_token'],'item_id':data['item_id'],'frame':data['frame'],'pose_source':data['pose_source'],'selected_preview_clip':data.get('selected_preview_clip'),'coordinate_system':'Actual renderer-local BakeMesh transformed to Unity world; metres; +Y up, +Z front','region':region,'comparison_target':target_mesh_name or 'actual_base_anatomy','base_foot_source':data.get('base_foot_source'),'base_body_occlusion':data.get('base_body_occlusion'),'sampling':'Deterministic uniform vertex-index samples; exact nearest triangle distance using BVH','sample_limit_per_surface':sample_limit,'targets':targets,'garments':rows,'model_modified':False,'collision_free_certified':False,'interpretation':['Negative bbox margin means target bounds extend beyond garment bounds on that axis.','Surface distances are unsigned; shoe openings are intentional and are not automatic failures.','Bone offsets diagnose registration separately from geometry shape.','Source-to-actual displacement includes normal pose/retargeting and is not alone an error.','Body masks remove anatomy from the visible reference; fewer samples after masking do not prove improved shoe enclosure.']},debug
def glb(meshes):
    document={'asset':{'version':'2.0','generator':'VRoid MCP fit context (static measured geometry)'},'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'materials':[{'name':'Measured target anatomy','pbrMetallicRoughness':{'baseColorFactor':[.05,.8,.85,.45],'metallicFactor':0.,'roughnessFactor':.7},'alphaMode':'BLEND','doubleSided':True},{'name':'Measured wearable','pbrMetallicRoughness':{'baseColorFactor':[.08,.1,.28,1.],'metallicFactor':0.,'roughnessFactor':.6},'doubleSided':True}],'buffers':[{'byteLength':0}],'bufferViews':[],'accessors':[],'extras':{'source':'Actual native pose snapshot','units':'metres','native_to_gltf':'x=-native_x; y=native_y; z=native_z','animation':False}}
    binary=bytearray()
    for name,faces,kind in meshes:
        points=[(-p[0],p[1],p[2]) for tri in faces for p in (tri[0],tri[2],tri[1])]
        if not points:continue
        while len(binary)%4:binary.append(0)
        offset=len(binary)
        for p in points:binary.extend(struct.pack('<3f',*p))
        view=len(document['bufferViews']);document['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(points)*12,'target':34962})
        accessor=len(document['accessors']);box=bounds(points);document['accessors'].append({'bufferView':view,'componentType':5126,'count':len(points),'type':'VEC3','min':box['min'],'max':box['max']})
        node=len(document['nodes']);document['scenes'][0]['nodes'].append(node);document['nodes'].append({'name':name,'mesh':len(document['meshes'])});document['meshes'].append({'name':name,'primitives':[{'attributes':{'POSITION':accessor},'mode':4,'material':0 if kind=='body' else 1}]})
    document['buffers'][0]['byteLength']=len(binary);j=json.dumps(document,separators=(',',':'),allow_nan=False).encode()
    j+=b' '*((-len(j))%4);binary.extend(b'\0'*((-len(binary))%4));length=12+8+len(j)+8+len(binary)
    return struct.pack('<4sII',b'glTF',2,length)+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(binary),b'BIN\0')+binary
