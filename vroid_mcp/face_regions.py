"""Conservative under-eye bands from native FaceSkin eye-hole boundaries, never fixed UV boxes."""
import collections,math

def triangles_for(surface,image):
    meshes=[m for m in surface['meshes'] if m['image']==image]
    if len(meshes)!=1:raise ValueError('A unique matching native face overlay is required')
    mesh=meshes[0];positions=mesh['positions'];uv=mesh['uv0']
    if not 3<=len(positions)<=10000 or len(positions)!=len(uv):raise ValueError('Unsupported face overlay vertex count')
    for p,t in zip(positions,uv):
        if len(p)!=3 or any(not math.isfinite(v) for v in p) or len(t)!=2 or any(not math.isfinite(v) or not 0<=v<=1 for v in t):raise ValueError('Invalid face position or UV stream')
    indices=[i for sub in mesh['submeshes'] for i in sub['triangles']]
    if len(indices)%3 or len(indices)>60000 or any(not isinstance(i,int) or not 0<=i<len(positions) for i in indices):raise ValueError('Invalid face triangle stream')
    return mesh,[indices[j:j+3] for j in range(0,len(indices),3)]

def eye_boundaries(mesh,triangles):
    positions=mesh['positions'];lookup={};weld=[];points=[]
    for p in positions:
        key=tuple(round(v,6) for v in p)
        if key not in lookup:lookup[key]=len(points);points.append(p)
        weld.append(lookup[key])
    edges=collections.Counter()
    for tri in triangles:
        a,b,c=[weld[i] for i in tri]
        if len({a,b,c})!=3:continue
        for x,y in ((a,b),(b,c),(c,a)):edges[tuple(sorted((x,y)))]+=1
    if any(n>2 for n in edges.values()):raise ValueError('Nonmanifold face boundary is unsupported')
    adjacency=collections.defaultdict(set)
    for (a,b),n in edges.items():
        if n==1:adjacency[a].add(b);adjacency[b].add(a)
    if any(len(v)!=2 for v in adjacency.values()):raise ValueError('Face openings must form unambiguous closed loops')
    pending=set(adjacency);loops=[]
    while pending:
        first=min(pending);loop=[first];previous=None;current=first
        while True:
            next_id=min(v for v in adjacency[current] if v!=previous)
            if next_id==first:break
            if next_id not in pending or next_id in loop:raise ValueError('Broken face boundary loop')
            loop.append(next_id);previous,current=current,next_id
        pending.difference_update(loop);loops.append([points[i] for i in loop])
    low=[min(p[k] for p in positions) for k in range(3)];high=[max(p[k] for p in positions) for k in range(3)]
    span=high[0]-low[0];center=(high[0]+low[0])/2;candidates=[]
    if not .08<=span<=.5:raise ValueError('Uncalibrated native face scale or axes')
    for loop in loops:
        lo=[min(p[k] for p in loop) for k in range(3)];hi=[max(p[k] for p in loop) for k in range(3)];width=hi[0]-lo[0];height=hi[1]-lo[1]
        one_side=hi[0]<center-.015*span or lo[0]>center+.015*span
        if one_side and .08*span<=width<=.35*span and .15*width<=height<=1.1*width and lo[2]>(low[2]+high[2])/2:
            candidates.append({'loop':loop,'bbox':[lo,hi],'width':width,'side':'native_x_negative' if hi[0]<center else 'native_x_positive'})
    if len(candidates)!=2 or len({e['side'] for e in candidates})!=2:raise ValueError('Expected exactly one verified eye opening on each native X side')
    candidates.sort(key=lambda e:e['bbox'][0][0]);a,b=candidates
    if abs(a['width']/b['width']-1)>.25 or abs(sum(p[1] for p in a['loop'])/len(a['loop'])-sum(p[1] for p in b['loop'])/len(b['loop']))>max(a['width'],b['width'])*.3:raise ValueError('Ambiguous or strongly asymmetric eye openings require separate calibration')
    return candidates

def lower_y(eye,x):
    values=[];loop=eye['loop']
    for a,b in zip(loop,loop[1:]+loop[:1]):
        if min(a[0],b[0])-1e-10<=x<=max(a[0],b[0])+1e-10 and abs(a[0]-b[0])>1e-12:
            t=(x-a[0])/(b[0]-a[0]);values.append(a[1]+t*(b[1]-a[1]))
    if not values:raise ValueError('Cannot interpolate the lower eye boundary')
    return min(values)

def barycentric(a,b,c,x,y):
    den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(den)<1e-14:return None
    u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den;v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den
    return [u,v,1-u-v] if min(u,v,1-u-v)>=-1e-9 else None

def under_eye_mask(surface,image,width,height):
    if not 1<=width<=4096 or not 1<=height<=4096 or width*height>4194304:raise ValueError('Unsupported face texture resolution')
    mesh,triangles=triangles_for(surface,image);eyes=eye_boundaries(mesh,triangles);positions=mesh['positions'];uv=mesh['uv0']
    def member(p):
        for number,eye in enumerate(eyes):
            lo,hi=eye['bbox'];w=eye['width']
            if not lo[0]+w*.04<=p[0]<=hi[0]-w*.04 or not lo[1]-w*.30<=p[1]<=hi[1] or p[2]<lo[2]-.05*w:continue
            depth=lower_y(eye,p[0])-p[1]
            if .015*w<=depth<=.30*w:return number
        return None
    projected=[[(uv[i][0]*width,(1-uv[i][1])*height) for i in tri] for tri in triangles]
    selected={};by_eye=[set(),set()];work=0
    for tri,tex in zip(triangles,projected):
        p=[positions[i] for i in tri]
        if not any(max(v[0] for v in p)>=e['bbox'][0][0] and min(v[0] for v in p)<=e['bbox'][1][0] and max(v[1] for v in p)>=e['bbox'][0][1]-.3*e['width'] and min(v[1] for v in p)<=e['bbox'][1][1] and max(v[2] for v in p)>=e['bbox'][0][2]-.05*e['width'] for e in eyes):continue
        xmin=max(0,math.floor(min(v[0] for v in tex)));xmax=min(width,math.ceil(max(v[0] for v in tex)));ymin=max(0,math.floor(min(v[1] for v in tex)));ymax=min(height,math.ceil(max(v[1] for v in tex)))
        work+=(xmax-xmin)*(ymax-ymin)
        if work>8000000:raise ValueError('Face rasterization exceeds the work limit')
        for y in range(ymin,ymax):
            for x in range(xmin,xmax):
                weights=barycentric(*tex,x+.5,y+.5)
                if weights is None:continue
                pos=[sum(v[k]*w for v,w in zip(p,weights)) for k in range(3)];number=member(pos)
                if number is None:continue
                pixel=y*width+x
                if pixel in selected and pixel not in by_eye[number]:raise ValueError('Shared UV pixels across eyes require separate calibration')
                selected[pixel]=pos;by_eye[number].add(pixel)
    if any(len(p)<8 for p in by_eye) or len(selected)>width*height*.08:raise ValueError('Empty or excessive under-eye paint region')
    # Check ALL face triangles: the selected UV addresses must not paint another part of the skin.
    rows=collections.defaultdict(list)
    for pixel in selected:y,x=divmod(pixel,width);rows[y].append(x)
    for tri,tex in zip(triangles,projected):
        xmin=min(v[0] for v in tex);xmax=max(v[0] for v in tex);ymin=min(v[1] for v in tex);ymax=max(v[1] for v in tex)
        for y,xs in rows.items():
            if not ymin<=y+.5<=ymax:continue
            for x in xs:
                if not xmin<=x+.5<=xmax:continue
                weights=barycentric(*tex,x+.5,y+.5)
                if weights is None:continue
                p=[sum(positions[i][k]*w for i,w in zip(tri,weights)) for k in range(3)]
                if math.dist(p,selected[y*width+x])>1e-5:raise ValueError('Under-eye UV overlaps another face surface; separate calibration required')
    def guide(eye,depth):
        result=[]
        for fraction in (.12,.3,.5,.7,.88):
            x=eye['bbox'][0][0]+eye['width']*fraction;y=lower_y(eye,x)-eye['width']*depth;hits=[]
            for ids in triangles:
                points=[positions[i] for i in ids];weights=barycentric(*points,x,y)
                if weights is None:continue
                pos=[sum(p[k]*w for p,w in zip(points,weights)) for k in range(3)]
                if member(pos) is None:continue
                hits.append((pos[2],[sum(uv[i][0]*w for i,w in zip(ids,weights)),1-sum(uv[i][1]*w for i,w in zip(ids,weights))]))
            if not hits:raise ValueError('Cannot map the under-eye guide to the editable canvas')
            result.append(max(hits,key=lambda h:h[0])[1])
        return result
    mask=bytearray(width*height)
    for pixel in selected:mask[pixel]=255
    for number,eye in enumerate(eyes):
        eye['pixels']=len(by_eye[number]);eye['highlight_guide_canvas']=guide(eye,.055);eye['shadow_guide_canvas']=guide(eye,.16)
    return bytes(mask),{'profile':'Native upright FaceSkin, two closed eye holes, +Y up/+Z front; unknown or ambiguous topology rejected','depth_below_lower_lid_eye_width_fraction':[.015,.30],'horizontal_inset_eye_width_fraction':.04,'uv_sharing_checked':True,'eyes':eyes,'scope':'Conservative skin strip below the actual eye opening; a painting aid for under-eye shadow/highlight, not automatic eye-bag shape segmentation.'}
