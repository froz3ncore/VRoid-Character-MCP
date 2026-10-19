"""Pixel, mask and validation regressions for bounded local painting."""
import copy,hashlib,json,math,struct,zlib
import pytest
from vroid_mcp.bounded_paint import decode_rgba_png,alpha_mask,describe_mask,render_marks,validate_marks
from vroid_mcp.texture_mapping import png_rgba
from vroid_mcp.makeup_tools import CanvasMark,load_mask

def mark(**changes):return {'kind':'stamp','points':[[.5,.5]],'radius':.15,'color':[.8,.2,.4,.6],**changes}
def rendered(marks,mask=None,w=64,h=64):
    data,stats=render_marks(w,h,mask if mask is not None else bytes([255])*(w*h),marks)
    _,_,rgba=decode_rgba_png(data);return rgba,stats

@pytest.mark.parametrize('filter_kind',range(5))
def test_decode_native_rgba_png_filters(filter_kind):
    width,height=4,3;rgba=bytes((i*37)%256 for i in range(width*height*4));rows=[];previous=bytes(width*4)
    for y in range(height):
        row=rgba[y*width*4:(y+1)*width*4];filtered=[]
        for x,value in enumerate(row):
            a=row[x-4] if x>=4 else 0;b=previous[x];c=previous[x-4] if x>=4 else 0;p=a+b-c
            pa,pb,pc=abs(p-a),abs(p-b),abs(p-c);paeth=a if pa<=pb and pa<=pc else b if pb<=pc else c
            predict=[0,a,b,(a+b)//2,paeth][filter_kind];filtered.append((value-predict)&255)
        rows.append(bytes([filter_kind])+bytes(filtered));previous=row
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v)&0xffffffff)
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
    assert decode_rgba_png(data)==(width,height,rgba)

def test_png_crc_truncation_and_decompression_size_are_checked():
    png=png_rgba(2,1,bytes(range(8)));assert decode_rgba_png(png)[2]==bytes(range(8))
    for bad in (png[:-2],png+b'extra',png[:40]+bytes([png[40]^1])+png[41:],b'fake'):
        with pytest.raises(ValueError):decode_rgba_png(bad)

def test_alpha_mask_is_circular_and_localized_with_measured_components():
    rgba=bytearray(100*100*4);rgba[4*(50*100+30)+3]=12;rgba[4*(50*100+70)+3]=200
    mask=alpha_mask(100,100,rgba,threshold=10,padding=2);stats=describe_mask(100,100,mask)
    assert stats['pixels']==26 and stats['component_count']==2
    assert mask[50*100+32] and not mask[52*100+32]
    assert len(alpha_mask(100,100,rgba,threshold=100,padding=0).replace(b'\0',b''))==1

def test_unlocalized_empty_and_excessive_expansion_masks_rejected():
    for data in (bytes(100*100*4),bytes([255])*(100*100*4)):
        with pytest.raises(ValueError):alpha_mask(100,100,data)
    with pytest.raises(ValueError):alpha_mask(100,100,bytes(100*100*4),padding=3)

def test_stamp_is_antialiased_soft_and_strictly_clipped():
    mask=bytes([255 if i%64<32 else 0 for i in range(4096)]);rgba,stats=rendered([mark()],mask)
    assert stats['outside_mask_pixels']==0 and stats['painted_pixels']>0
    assert all(rgba[i*4+3]==0 for i in range(4096) if not mask[i])
    alpha=rgba[3::4];assert max(alpha)<=153 and len(set(alpha))>20

def test_rotated_ellipse_and_stroke_reflect_across_canvas():
    rgba,_=rendered([mark(points=[[.25,.5]],aspect=1.8,rotation_deg=38,mirror_x=True)])
    for y in range(64):
        for x in range(32):assert rgba[(y*64+x)*4:(y*64+x+1)*4]==rgba[(y*64+63-x)*4:(y*64+64-x)*4]

def test_stroke_fills_segments_without_opacity_piling_on_repeated_dabs():
    a,_=rendered([mark(kind='stroke',points=[[.2,.5],[.8,.5]],radius=.05)])
    b,_=rendered([mark(kind='stroke',points=[[.2,.5],[.8,.5],[.2,.5],[.8,.5]],radius=.05)])
    assert a==b
    assert all(a[(32*64+x)*4+3]>0 for x in range(14,50))

def test_source_over_color_order():
    rgba,_=rendered([mark(color=[1,0,0,.5],hardness=1),mark(color=[0,1,0,.5],hardness=1)])
    pixel=rgba[(32*64+32)*4:(32*64+32)*4+4]
    assert all(abs(a-b)<=1 for a,b in zip(pixel,[85,170,0,191]))

@pytest.mark.parametrize('changes',[{'radius':math.nan},{'radius':0},{'aspect':5},{'hardness':-1},{'color':[1,1,True,1]}, {'points':[[1.1,.5]]},{'points':[[.5]]},{'kind':'fill'},{'points':[[.2,.2],[.4,.4]]},{'mirror_x':'true'},{'unexpected':True}])
def test_invalid_mark_arguments_rejected_before_paint(changes):
    with pytest.raises(ValueError):validate_marks([mark(**changes)])
    with pytest.raises(ValueError):CanvasMark(**mark(**changes))

def test_bounded_work_limit_and_off_mask_marks():
    with pytest.raises(ValueError,match='work limit'):render_marks(2048,2048,bytes([255])*(2048*2048),[mark(radius=.25,aspect=4)]*32)
    with pytest.raises(ValueError,match='miss'):rendered([mark(points=[[.01,.01]],radius=.005)],bytes(4096))

def test_mask_artifact_identity_and_pixel_hash_are_required(tmp_path):
    identifier='a'*32;folder=tmp_path/'reviews'/('makeup-mask-'+identifier);folder.mkdir(parents=True);png=png_rgba(2,1,bytes([255,255,255,255,0,0,0,0]));(folder/'mask.png').write_bytes(png)
    manifest={'model_token':'current','width':2,'height':1,'mask_png_sha256':hashlib.sha256(png).hexdigest()};data=json.dumps(manifest).encode();(folder/'manifest.json').write_bytes(data);sha=hashlib.sha256(data).hexdigest()
    assert load_mask(tmp_path,identifier,sha,'current')[1]==bytes([255,0])
    for ident,expected,token in [('../escape',sha,'current'),(identifier,'0'*64,'current'),(identifier,sha,'stale')]:
        with pytest.raises(ValueError):load_mask(tmp_path,ident,expected,token)
    (folder/'mask.png').write_bytes(png+b'changed')
    with pytest.raises(ValueError):load_mask(tmp_path,identifier,sha,'current')
