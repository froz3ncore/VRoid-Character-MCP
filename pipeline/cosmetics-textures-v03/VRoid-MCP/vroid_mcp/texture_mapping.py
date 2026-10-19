"""Measured renderer UV picking and conservative native nail-cap discovery."""
import hashlib,json,math,re,struct,zlib

def add(a,b):return [x+y for x,y in zip(a,b)]
def sub(a,b):return [x-y for x,y in zip(a,b)]
def mul(a,s):return [x*s for x in a]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def length(a):return math.sqrt(dot(a,a))
def unit(a):
    n=length(a)
    if n<1e-12:raise ValueError('A nonzero direction is required')
    return mul(a,1/n)
def point(m,p):return [sum(m[i][j]*p[j] for j in range(3))+m[i][3] for i in range(3)]
def vector3(v):
    if len(v)!=3 or not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in v):raise ValueError('Expected three finite numeric coordinates')
    return list(v)
def main_texture(renderer,slot=0):
    material=next((m for m in renderer['materials'] if m['slot']==slot),None)
    if not material:raise ValueError('No material for the sampled submesh')
    texture=next((t for t in material['textures'] if t['property']=='_MainTex' and t.get('instance_id') is not None),None)
    if not texture:raise ValueError('The material has no readable main texture')
    return material,texture

def pick_uv(reference,bindings,mesh_name,origin,direction,max_distance=5):
    origin=vector3(origin);direction=unit(vector3(direction))
    if not math.isfinite(max_distance) or not 0<max_distance<=20:raise ValueError('Distance must be finite and within 0..20 m')
    if reference['model_token']!=bindings['model_token']:raise ValueError('Model identity differs between geometry and material bindings')
    meshes=[m for m in reference['meshes'] if m['name']==mesh_name];renderers=[r for r in bindings['renderers'] if r['name']==mesh_name]
    if len(meshes)!=1 or len(renderers)!=1:raise ValueError('Requested native renderer is missing or ambiguous')
    mesh=meshes[0];renderer=renderers[0]
    vertices=[point(mesh['world_matrix'],v) for v in mesh['positions']];uv=mesh['uv0'];indices=mesh['triangles']
    if len(uv)!=len(vertices):raise ValueError('Native UV stream is missing or incomplete')
    counts=renderer['submesh_triangle_counts']
    if sum(counts)*3!=len(indices):raise ValueError('Submesh counts differ from the sampled index stream')
    hits=[];slot=0;limit=counts[0] if counts else 0
    for triangle in range(len(indices)//3):
        while triangle>=limit and slot+1<len(counts):slot+=1;limit+=counts[slot]
        ids=indices[3*triangle:3*triangle+3];a,b,c=[vertices[i] for i in ids];e1=sub(b,a);e2=sub(c,a);h=cross(direction,e2);det=dot(e1,h)
        if abs(det)<1e-12:continue
        offset=sub(origin,a);u=dot(offset,h)/det
        if not -1e-8<=u<=1+1e-8:continue
        q=cross(offset,e1);v=dot(direction,q)/det
        if v< -1e-8 or u+v>1+1e-8:continue
        distance=dot(e2,q)/det
        if not 0<distance<=max_distance:continue
        bary=[1-u-v,u,v];raw_uv=[sum(uv[i][k]*w for i,w in zip(ids,bary)) for k in range(2)]
        material,texture=main_texture(renderer,slot);mapped=[raw_uv[k]*texture['scale'][k]+texture['offset'][k] for k in range(2)]
        hits.append({'triangle':triangle,'indices':ids,'barycentric':bary,'distance_m':distance,'world_position':add(origin,mul(direction,distance)),
            'geometric_normal':unit(cross(e1,e2)),'winding_front_facing':det>0,'uv0':raw_uv,'texture_uv':mapped,
            'image_pixel_top_left':[mapped[0]*texture['width'],(1-mapped[1])*texture['height']],
            'material_slot':slot,'material_name':material['name'],'texture':texture})
    hits.sort(key=lambda h:(h['distance_m'],not h['winding_front_facing'],h['triangle']))
    return {'hit':bool(hits),'mesh_name':mesh_name,'nearest':hits[0] if hits else None,
        'coincident_hits':[h for h in hits if h['distance_m']<=hits[0]['distance_m']+1e-6][:16] if hits else [],
        'model_token':reference['model_token'],'scope':'Current baked renderer geometry. Texture pixels use top-left origin; UV is +V upward. Coincident faces are reported; winding is not a shader-culling assertion.'}

def discover_nails(reference,bindings):
    if reference['model_token']!=bindings['model_token']:raise ValueError('Model identity differs')
    meshes=[m for m in reference['meshes'] if m['name']=='Hand'];hands=[m for m in bindings['renderers'] if m['name']=='Hand']
    if len(meshes)!=1 or len(hands)!=1:raise ValueError('A unique native Hand renderer is required')
    mesh=meshes[0];hand=hands[0]
    if len(hand['materials'])!=1:raise ValueError('Hand has multiple materials; automatic nail mapping is unsupported')
    material,texture=main_texture(hand)
    if texture['offset']!=[0,0] or texture['scale']!=[1,1]:raise ValueError('Nonidentity Hand UV transform requires separate calibration')
    positions=[point(mesh['world_matrix'],v) for v in mesh['positions']];uv=mesh['uv0'];triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    if len(uv)!=len(positions):raise ValueError('Hand UV stream is incomplete')
    if any(len(v)!=2 or any(not math.isfinite(x) or not 0<=x<=1 for x in v) for v in uv):raise ValueError('Hand UV coordinates require finite values within 0..1')
    nodes={n['id']:n for n in reference['nodes']};bones=[nodes[i]['name'] for i in mesh['bone_nodes']];parent=list(range(len(positions)))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for a,b,c in triangles:parent[find(b)]=find(a);parent[find(c)]=find(a)
    groups={}
    for i in set(i for t in triangles for i in t):groups.setdefault(find(i),[]).append(i)
    candidates={}
    for ids in groups.values():
        targets=set();valid=True
        for i in ids:
            skin=[(bones[b],w) for b,w in zip(mesh['weights'][i]['indices'],mesh['weights'][i]['weights']) if w>1e-6]
            if len(skin)!=1 or skin[0][1]<1-1e-5 or not re.fullmatch(r'J_Bip_[LR]_(Thumb|Index|Middle|Ring|Little)3',skin[0][0]):valid=False;break
            targets.add(skin[0][0])
        if not valid or len(targets)!=1:continue
        ids=sorted(ids);iset=set(ids);faces=[(i,t) for i,t in enumerate(triangles) if t[0] in iset]
        if len(ids)<4 or len(faces)<2:continue
        normal=[0.,0.,0.];area=0.
        for _,(a,b,c) in faces:
            n=cross(sub(positions[b],positions[a]),sub(positions[c],positions[a]));normal=add(normal,n);area+=length(n)/2
        diameter=max(length(sub(positions[a],positions[b])) for a in ids for b in ids)
        if not .002<=diameter<=.04 or area<1e-8 or length(normal)<1e-10:continue
        center=[sum(positions[i][k] for i in ids)/len(ids) for k in range(3)]
        component={'vertex_ids':ids,'triangle_ids':[i for i,_ in faces],'triangles':[t for _,t in faces],
            'uv_triangles':[[uv[i] for i in t] for _,t in faces],'world_center':center,'normal':unit(normal),'diameter_m':diameter,'area_m2':area,
            'uv_bbox':[[min(uv[i][k] for i in ids) for k in range(2)],[max(uv[i][k] for i in ids) for k in range(2)]]}
        candidates.setdefault(next(iter(targets)),[]).append(component)
    nails=[]
    for side in ('L','R'):
        for finger in ('Thumb','Index','Middle','Ring','Little'):
            name=f'J_Bip_{side}_{finger}3';parts=candidates.get(name,[])
            if len(parts)!=2:raise ValueError(f'Unsupported or ambiguous nail topology for {name}: expected two isolated distal caps, found {len(parts)}')
            a,b=parts;opposed=dot(a['normal'],b['normal'])
            hausdorff=max(max(min(length(sub(positions[i],positions[j])) for j in b['vertex_ids']) for i in a['vertex_ids']),max(min(length(sub(positions[i],positions[j])) for j in a['vertex_ids']) for i in b['vertex_ids']))
            if opposed>-.95 or hausdorff>min(.002,.2*max(a['diameter_m'],b['diameter_m'])):raise ValueError(f'Unverified paired nail surfaces for {name}')
            nails.append({'id':side+'_'+finger,'side':'left' if side=='L' else 'right','finger':finger.lower(),'distal_bone':name,
                'islands':parts,'paired_normal_dot':opposed,'paired_surface_distance_mm':hausdorff*1000})
    all_faces=[i for n in nails for p in n['islands'] for i in p['triangle_ids']]
    if len(set(all_faces))!=len(all_faces):raise ValueError('Nail geometry overlaps across fingers')
    digest=hashlib.sha256(json.dumps({'mesh':mesh,'bone_names':bones},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'model_token':reference['model_token'],'geometry_sha256':digest,'renderer':'Hand','material_name':material['name'],'texture':texture,
        'nails':nails,'nail_count':10,'uv_island_count':20,'profile':'Paired isolated distal-bone caps; no fixed UV boxes or vertex counts',
        'status':'Geometry-derived candidate regions; verify a colored native preview before art adoption','scope':'Unknown/ambiguous hand topology is rejected. No automatic nail resizing, remeshing or color change.'}

def png_rgba(width,height,data):
    if len(data)!=width*height*4:raise ValueError('RGBA byte count mismatch')
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v)&0xffffffff)
    rows=b''.join(b'\0'+data[y*width*4:(y+1)*width*4] for y in range(height))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')

def raster_nails(mapping):
    w=mapping['texture']['width'];h=mapping['texture']['height']
    if not 1<=w<=4096 or not 1<=h<=4096 or w*h>4194304:raise ValueError('Texture resolution exceeds validated raster range')
    masks={};occupied={}
    for nail in mapping['nails']:
        mask=set()
        for island in nail['islands']:
            for tri in island['uv_triangles']:
                if len(tri)!=3 or any(len(p)!=2 or any(not math.isfinite(v) or not 0<=v<=1 for v in p) for p in tri):raise ValueError('Nail UV triangles require finite coordinates within 0..1')
                a,b,c=[(u*w,(1-v)*h) for u,v in tri];den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                if abs(den)<1e-10:continue
                for y in range(max(0,math.floor(min(p[1] for p in (a,b,c)))),min(h,math.ceil(max(p[1] for p in (a,b,c))))):
                    for x in range(max(0,math.floor(min(p[0] for p in (a,b,c)))),min(w,math.ceil(max(p[0] for p in (a,b,c))))):
                        xx=x+.5;yy=y+.5;u=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den;v=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den
                        if min(u,v,1-u-v)>=-1e-9:mask.add(y*w+x)
        if not mask:raise ValueError('Empty nail mask')
        for i in mask:
            if i in occupied and occupied[i]!=nail['id']:raise ValueError('UV sharing detected between distinct nails; separate calibration required')
            occupied[i]=nail['id']
        masks[nail['id']]=mask
    return masks
