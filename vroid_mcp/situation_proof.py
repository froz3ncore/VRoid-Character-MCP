"""Independent bounded checks of actual situation optics, native identity and raster."""
import math
import struct
import zlib

from .preset_catalog import validate_png


def identity(group):
    return tuple(group.get(k) for k in ('id','type','resource_name','revision','updated_since_last_revision'))


def definition(value, version=True):
    if (not isinstance(value,dict) or value.get('verified') is not True
            or not isinstance(value.get('root'),dict)):
        raise ValueError('SITUATION_DEFINITION_UNVERIFIED')
    root=value['root'];keys=('id','type','resource_name')
    if any(not isinstance(root.get(k),str) or not root[k] for k in keys):
        raise ValueError('SITUATION_DEFINITION_IDENTITY_UNAVAILABLE')
    if not version:return {k:root[k] for k in keys}
    members=value.get('members')
    if (value.get('revision_verified') is not True or not isinstance(members,list)
            or not 1<=len(members)<=512 or len({g.get('id') for g in members})!=len(members)):
        raise ValueError('SITUATION_MEMBER_VERSION_UNPROVEN')
    normalized=[]
    for group in members:
        if (any(not isinstance(group.get(k),str) or not group[k] for k in (*keys,'revision'))
                or group.get('updated_since_last_revision') is not False):
            raise ValueError('SITUATION_MEMBER_VERSION_UNPROVEN')
        normalized.append({k:group[k] for k in (*keys,'revision','updated_since_last_revision')})
    normalized.sort(key=lambda g:g['id'])
    if identity(root) not in {identity(g) for g in normalized}:raise ValueError('SITUATION_ROOT_VERSION_UNPROVEN')
    return {'root':{k:root[k] for k in (*keys,'revision','updated_since_last_revision')},'members':normalized}


def capture_proof(effective,requested,width=512,height=512):
    def vector(value,count):
        return isinstance(value,list) and len(value)==count and all(type(v) in (float,int) and math.isfinite(v) for v in value)
    def near(a,b):return abs(a-b)<=1e-4*max(1,abs(b))
    if (not isinstance(effective,dict) or effective.get('schema')!='vroid-situation-framing-v1'
            or effective.get('requested_profile')!=requested
            or any(effective.get(k) is not True for k in ('camera_readback_verified','projection_verified','containment_verified'))
            or effective.get('projection')!='perspective'
            or type(effective.get('source_renderer_count')) is not int or not 1<=effective['source_renderer_count']<=4096
            or not isinstance(effective.get('source_root_id'),str) or not effective['source_root_id']):
        raise ValueError('SITUATION_FRAMING_UNVERIFIED')
    bounds=effective.get('source_bounds',{});lo,hi=bounds.get('min'),bounds.get('max')
    if not vector(lo,3) or not vector(hi,3) or any(a>=b for a,b in zip(lo,hi)):
        raise ValueError('SITUATION_BOUNDS_UNVERIFIED')
    names=('aspect','fov_degrees','near_clip','far_clip','distance','source_span','region_world_top',
           'region_world_bottom','effective_half_width','requested_distance','requested_distance_multiplier',
           'effective_distance_multiplier','yaw_degrees')
    if any(type(effective.get(k)) not in (int,float) or not math.isfinite(effective[k]) for k in names):
        raise ValueError('SITUATION_OPTICS_INCOMPLETE')
    for k in ('position','target','forward','right_vector','up_vector'):
        if not vector(effective.get(k),3):raise ValueError('SITUATION_POSE_INCOMPLETE')
    matrix=effective.get('projection_matrix')
    if not vector(matrix,16):raise ValueError('SITUATION_PROJECTION_UNVERIFIED')
    aspect=width/height;n=effective['near_clip'];far=effective['far_clip'];d=effective['distance']
    if (not near(effective['aspect'],aspect) or not near(effective['fov_degrees'],30)
            or not near(n,.01) or far<=n or n<=0 or d<=0):raise ValueError('SITUATION_CLIP_OR_ASPECT_MISMATCH')
    f=1/math.tan(math.pi/12)
    expected=[f/aspect,0,0,0,0,f,0,0,0,0,-(far+n)/(far-n),-2*far*n/(far-n),0,0,-1,0]
    if any(not near(a,b) for a,b in zip(matrix,expected)):raise ValueError('SITUATION_PROJECTION_MISMATCH')
    H=hi[1]-lo[1]
    if H<.1:raise ValueError('SITUATION_BOUNDS_UNVERIFIED')
    full=requested['fit']=='full-body';top=hi[1] if full else hi[1]-requested['top']*H
    bottom=lo[1] if full else hi[1]-requested['bottom']*H
    c=[(a+b)/2 for a,b in zip(lo,hi)];rad=math.radians(requested['yaw']);normal=[math.sin(rad),0,math.cos(rad)]
    right=[-normal[2],0,normal[0]];forward=[-v for v in normal];target=[c[0],(top+bottom)/2,c[2]]
    ex=[(b-a)/2 for a,b in zip(lo,hi)];depth=abs(normal[0])*ex[0]+abs(normal[2])*ex[2]
    half=abs(normal[2])*ex[0]+abs(normal[0])*ex[2] if full or requested['half'] is None else requested['half']*H
    span=max(top-bottom,.14*H)*1.1
    requested_distance=requested['distance']*span
    required=depth+max(half/aspect,(top-bottom)/2)/math.tan(math.pi/12)
    intended=max(requested_distance,required*1.000001,depth+.02)
    if not near(d,intended):raise ValueError('SITUATION_EFFECTIVE_DISTANCE_MISMATCH')
    adjusted=effective.get('distance_adjusted');reason=effective.get('adjustment_reason')
    # The branch must be true outside Float32-scale boundary ambiguity. Tiny
    # containment padding can straddle that boundary without a visible change.
    if (type(adjusted) is not bool or not near(max(required*1.000001,depth+.02),requested_distance) and adjusted is not (intended>requested_distance)
            or adjusted and reason!='perspective region containment including model depth'
            or not adjusted and reason is not None):
        raise ValueError('SITUATION_DISTANCE_ADJUSTMENT_MISMATCH')
    if not near(far,max(1000,intended+depth+H+1)):raise ValueError('SITUATION_CLIP_OR_ASPECT_MISMATCH')
    for key,want in [('target',target),('position',[target[i]+normal[i]*intended for i in range(3)]),
                     ('right_vector',right),('forward',forward),('up_vector',[0,1,0])]:
        if any(not near(a,b) for a,b in zip(effective[key],want)):raise ValueError('SITUATION_POSE_MISMATCH')
    for key,want in [('source_span',span),('region_world_top',top),('region_world_bottom',bottom),
                     ('effective_half_width',half),('requested_distance',requested_distance),
                     ('requested_distance_multiplier',requested['distance']),('effective_distance_multiplier',intended/span),
                     ('yaw_degrees',requested['yaw'])]:
        if not near(effective[key],want):raise ValueError('SITUATION_REGION_OR_DISTANCE_MISMATCH')
    if (effective.get('fit')!=requested['fit'] or effective.get('inactive_fields')!=(['top','bottom','half'] if full else [])
            or d+1e-5<requested['distance']*span):raise ValueError('SITUATION_FIT_MISMATCH')
    points=([x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])) if full else (
        [target[i]+right[i]*u+normal[i]*v+(y-target[1] if i==1 else 0) for i in range(3)]
        for u in (-half,half) for y in (bottom,top) for v in (-depth,depth))
    # Use returned actual camera pose and matrix, not just the planner distance.
    for point in points:
        rel=[point[i]-effective['position'][i] for i in range(3)]
        q=[sum(rel[i]*effective[k][i] for i in range(3)) for k in ('right_vector','up_vector','forward')]
        if not n<q[2]<far:raise ValueError('SITUATION_CORNER_CLIPPED')
        camera=[q[0],q[1],-q[2],1]
        clip=[sum(matrix[i*4+j]*camera[j] for j in range(4)) for i in range(4)]
        if clip[3]<=0 or any(abs(clip[i]/clip[3])>1.0001 for i in range(3)):
            raise ValueError('SITUATION_CORNER_CLIPPED')


def raster_evidence(data):
    info=validate_png(data)
    if (info['width'],info['height'])!=(512,512):raise ValueError('SITUATION_RASTER_SIZE_MISMATCH')
    offset=8;payload=[];channels=4 if data[25]==6 else 3
    while offset<len(data):
        size=struct.unpack('>I',data[offset:offset+4])[0]
        if data[offset+4:offset+8]==b'IDAT':payload.append(data[offset+8:offset+8+size])
        offset+=size+12
    raw=zlib.decompress(b''.join(payload));stride=512*channels;prior=bytearray(stride);hist={};visible=0
    for y in range(512):
        kind=raw[y*(stride+1)];row=bytearray(raw[y*(stride+1)+1:(y+1)*(stride+1)])
        for x in range(stride):
            a=row[x-channels] if x>=channels else 0;b=prior[x];c=prior[x-channels] if x>=channels else 0
            if kind==1:predict=a
            elif kind==2:predict=b
            elif kind==3:predict=(a+b)//2
            elif kind==4:
                p=a+b-c;pa,pb,pc=abs(p-a),abs(p-b),abs(p-c);predict=a if pa<=pb and pa<=pc else b if pb<=pc else c
            else:predict=0
            row[x]=(row[x]+predict)&255
        for x in range(0,stride,channels):
            transparent=channels==4 and row[x+3]==0
            if not transparent:visible+=1
            color=b'\0\0\0\0' if transparent else bytes(row[x:x+channels])
            hist[color]=hist.get(color,0)+1
        prior=row
    different=512*512-max(hist.values(),default=0)
    if visible<64 or different<64:raise ValueError('SITUATION_EMPTY_OR_UNIFORM_RASTER')
    colors=sum(1 for color in hist if channels==3 or color[3]!=0)
    return {'verified':True,'visible_pixels':visible,'nonmodal_pixels':different,'distinct_visible_colors':colors,
            'sha256':info['sha256'],'scope':'reject empty/transparent/uniform raster; subject identity and appearance require visual acceptance'}
