"""Deterministic RGBA canvas marks, clipped to a measured region; no image dependency."""
import math,struct,zlib
from .texture_mapping import png_rgba

MAX_PIXELS=4194304
MAX_WORK=8000000

def decode_rgba_png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data)>16*1024*1024:raise ValueError('Expected a bounded PNG')
    offset=8;payload=[];header=None;ended=False
    while offset<len(data):
        if offset+12>len(data):raise ValueError('Truncated PNG chunk')
        n=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8];end=offset+8+n
        if end+4>len(data):raise ValueError('Truncated PNG payload')
        value=data[offset+8:end]
        if zlib.crc32(kind+value)&0xffffffff!=struct.unpack('>I',data[end:end+4])[0]:raise ValueError('PNG checksum mismatch')
        if kind==b'IHDR':
            if header is not None or offset!=8 or n!=13:raise ValueError('Invalid PNG header')
            header=struct.unpack('>IIBBBBB',value);w,h,depth,color,compression,filtering,interlace=header
            if not 1<=w<=4096 or not 1<=h<=4096 or w*h>MAX_PIXELS or (depth,color,compression,filtering,interlace)!=(8,6,0,0,0):raise ValueError('Only noninterlaced RGBA8 native layer PNGs are supported')
        elif kind==b'IDAT':payload.append(value)
        elif kind==b'IEND':
            if n or end+4!=len(data):raise ValueError('Invalid PNG ending')
            ended=True;break
        elif kind in (b'acTL',b'fcTL',b'fdAT') or not kind[0]&32:raise ValueError('Unsupported critical or animated PNG chunk')
        offset=end+4
    if header is None or not ended or not payload:raise ValueError('Incomplete PNG')
    expected=(w*4+1)*h;decoder=zlib.decompressobj();raw=decoder.decompress(b''.join(payload),expected+1)
    if len(raw)!=expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:raise ValueError('Unexpected PNG decompressed size')
    stride=w*4;result=bytearray(w*h*4);previous=bytearray(stride)
    for y in range(h):
        kind=raw[y*(stride+1)];row=bytearray(raw[y*(stride+1)+1:(y+1)*(stride+1)])
        if kind>4:raise ValueError('Unsupported PNG filter')
        for x in range(stride):
            a=row[x-4] if x>=4 else 0;b=previous[x];c=previous[x-4] if x>=4 else 0
            if kind==1:predict=a
            elif kind==2:predict=b
            elif kind==3:predict=(a+b)//2
            elif kind==4:
                p=a+b-c;pa=abs(p-a);pb=abs(p-b);pc=abs(p-c);predict=a if pa<=pb and pa<=pc else b if pb<=pc else c
            else:predict=0
            row[x]=(row[x]+predict)&255
        result[y*stride:(y+1)*stride]=row;previous=row
    return w,h,bytes(result)

def alpha_mask(width,height,rgba,threshold=1,padding=0):
    if not isinstance(threshold,int) or not 1<=threshold<=255 or not isinstance(padding,int) or not 0<=padding<=min(16,int(min(width,height)*.02)):raise ValueError('Invalid alpha threshold or padding')
    if len(rgba)!=width*height*4:raise ValueError('RGBA size mismatch')
    source=[i for i in range(width*height) if rgba[i*4+3]>=threshold]
    if not source or len(source)>width*height*.25:raise ValueError('The reference is empty or not a localized transparent makeup footprint')
    offsets=[(x,y) for y in range(-padding,padding+1) for x in range(-padding,padding+1) if x*x+y*y<=padding*padding]
    if len(source)*len(offsets)>MAX_WORK:raise ValueError('Mask expansion exceeds the bounded work limit')
    mask=bytearray(width*height)
    for i in source:
        y,x=divmod(i,width)
        for dx,dy in offsets:
            xx=x+dx;yy=y+dy
            if 0<=xx<width and 0<=yy<height:mask[yy*width+xx]=255
    return bytes(mask)

def describe_mask(width,height,mask):
    active={i for i,a in enumerate(mask) if a};components=[]
    if not active:raise ValueError('Empty mask')
    while active:
        first=active.pop();pending=[first];xs=[];ys=[]
        while pending:
            i=pending.pop();y,x=divmod(i,width);xs.append(x);ys.append(y)
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                xx=x+dx;yy=y+dy;j=yy*width+xx
                if 0<=xx<width and 0<=yy<height and j in active:active.remove(j);pending.append(j)
        components.append({'pixels':len(xs),'bbox_top_left':[min(xs),min(ys),max(xs)+1,max(ys)+1],
            'center_canvas':[sum(xs)/len(xs)/width,sum(ys)/len(ys)/height]})
    components.sort(key=lambda c:c['pixels'],reverse=True)
    return {'pixels':sum(c['pixels'] for c in components),'component_count':len(components),'components':components[:64],'coordinate_system':'Normalized canvas x-right/y-down, origin top-left. These are not world coordinates or Unity UV.'}

def validate_marks(marks):
    if not isinstance(marks,list) or not 1<=len(marks)<=32:raise ValueError('Use 1..32 marks')
    normalized=[]
    def number(x,lo,hi):
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not lo<=x<=hi:raise ValueError('Mark parameter is outside its finite validated range')
        return x
    for mark in marks:
        if set(mark)-{'kind','points','radius','aspect','rotation_deg','hardness','color','mirror_x'}:raise ValueError('Unknown mark property')
        kind=mark.get('kind','stamp');points=mark.get('points');color=mark.get('color')
        if kind not in ('stamp','stroke') or not isinstance(points,list) or not 1<=len(points)<=128 or (kind=='stamp' and len(points)!=1) or (kind=='stroke' and len(points)<2):raise ValueError('A stamp needs one point; a stroke needs 2..128 points')
        if not isinstance(color,(list,tuple)) or len(color)!=4:raise ValueError('A mark needs normalized RGBA')
        if any(not isinstance(p,(list,tuple)) or len(p)!=2 for p in points):raise ValueError('A canvas point needs x/y')
        points=[[number(v,0,1) for v in p] for p in points]
        mirror=mark.get('mirror_x',False)
        if not isinstance(mirror,bool):raise ValueError('mirror_x must be boolean')
        normalized.append({'kind':kind,'points':points,'radius':number(mark.get('radius',.025),.002,.25),'aspect':number(mark.get('aspect',1),.25,4),
            'rotation_deg':number(mark.get('rotation_deg',0),-180,180),'hardness':number(mark.get('hardness',0),0,1),'color':[number(v,0,1) for v in color],'mirror_x':mirror})
    return normalized

def render_marks(width,height,mask,marks):
    if not 1<=width<=4096 or not 1<=height<=4096 or width*height>MAX_PIXELS or len(mask)!=width*height:raise ValueError('Invalid measured mask dimensions')
    marks=validate_marks(marks);plans=[];work=0;dabs_total=0
    for mark in marks:
        radius=mark['radius']*min(width,height);rx=radius*mark['aspect'];ry=radius;angle=math.radians(mark['rotation_deg']);cs=math.cos(angle);sn=math.sin(angle)
        ex=abs(rx*cs)+abs(ry*sn)+1;ey=abs(rx*sn)+abs(ry*cs)+1;points=[(p[0]*width,p[1]*height) for p in mark['points']];dabs=[points[0]]
        for a,b in zip(points,points[1:]):
            count=max(1,math.ceil(math.dist(a,b)/max(.5,min(rx,ry)*.3)))
            if count+len(dabs)>4096:raise ValueError('Stroke is too long or dense')
            dabs.extend((a[0]+(b[0]-a[0])*i/count,a[1]+(b[1]-a[1])*i/count) for i in range(1,count+1))
        original=dabs;dabs=[(x,y,1) for x,y in original]
        if mark['mirror_x']:dabs+=[(width-x,y,-1) for x,y in original]
        dabs_total+=len(dabs)
        if dabs_total>4096:raise ValueError('Too many brush dabs')
        bounds=[]
        for x,y,_ in dabs:
            box=(max(0,math.floor(x-ex)),max(0,math.floor(y-ey)),min(width,math.ceil(x+ex)),min(height,math.ceil(y+ey)))
            work+=(box[2]-box[0])*(box[3]-box[1]);bounds.append(box)
        if work>MAX_WORK:raise ValueError('Painting exceeds the bounded pixel-work limit')
        plans.append((mark,dabs,bounds,rx,ry,cs,sn))
    rgba=bytearray(width*height*4)
    for mark,dabs,bounds,rx,ry,cs,sn in plans:
        cover={};hardness=mark['hardness']
        for (cx,cy,reflection),box in zip(dabs,bounds):
            for y in range(box[1],box[3]):
                for x in range(box[0],box[2]):
                    index=y*width+x
                    if not mask[index]:continue
                    samples=0.
                    for ox,oy in ((.25,.25),(.75,.25),(.25,.75),(.75,.75)):
                        dx=x+ox-cx;dy=y+oy-cy;ss=sn*reflection;r=math.hypot((cs*dx+ss*dy)/rx,(-ss*dx+cs*dy)/ry)
                        if r>=1:continue
                        if r<=hardness or hardness==1:value=1.
                        else:t=(1-r)/(1-hardness);value=t*t*(3-2*t)
                        samples+=value/4
                    if samples>cover.get(index,0):cover[index]=samples
        red,green,blue,alpha=mark['color']
        for i,coverage in cover.items():
            a=alpha*coverage*mask[i]/255;old=rgba[i*4+3]/255;out=a+old*(1-a)
            if out<=0:continue
            for channel,color in enumerate((red,green,blue)):rgba[i*4+channel]=round((color*a+rgba[i*4+channel]/255*old*(1-a))/out*255)
            rgba[i*4+3]=round(out*255)
    count=sum(a>0 for a in rgba[3::4])
    if not count:raise ValueError('Marks miss the measured mask or are fully transparent')
    return png_rgba(width,height,rgba),{'painted_pixels':count,'outside_mask_pixels':0,'marks':len(marks),'brush_dabs':dabs_total,'pixel_work':work,'antialias_samples':4,
        'within_stroke_overlap':'Maximum coverage, independent of dab density','between_marks_blending':'Straight-alpha source over, marks in order','coordinate_system':'Normalized canvas x-right/y-down; mirror_x reflects the canvas, not an inferred anatomical side'}
