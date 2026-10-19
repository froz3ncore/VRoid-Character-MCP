"""Eye-boundary mapping must tolerate UV movement and reject anatomy/UV ambiguity."""
import copy
import pytest
from vroid_mcp.face_regions import under_eye_mask

def face():
    p=[];uv=[];triangles=[]
    for y in range(27):
        for x in range(25):
            xx=-.12+.01*x;yy=1.4+.01*y
            p.append([xx,yy,.1-(xx/.12)**2*.05-((yy-1.53)/.13)**2*.02]);uv.append([x/24,y/26])
    for y in range(26):
        for x in range(24):
            if 12<=y<15 and (5<=x<9 or 15<=x<19):continue
            a=y*25+x;b=a+1;c=a+25;d=c+1;triangles.extend([a,b,c,b,d,c])
    mesh={'image':{'id':'face'},'positions':p,'uv0':uv,'submeshes':[{'triangles':triangles}]}
    return {'meshes':[mesh]},mesh['image']

def test_mask_tracks_uv_instead_of_fixed_image_boxes_and_returns_surface_guides():
    surface,image=face();mask,info=under_eye_mask(surface,image,128,128)
    assert len(info['eyes'])==2 and info['uv_sharing_checked']
    assert all(e['pixels']>8 and len(e['highlight_guide_canvas'])==5 and len(e['shadow_guide_canvas'])==5 for e in info['eyes'])
    altered=copy.deepcopy(surface)
    for p in altered['meshes'][0]['uv0']:p[0]=1-p[0]
    reflected,_=under_eye_mask(altered,image,128,128)
    assert reflected==b''.join(mask[y*128:(y+1)*128][::-1] for y in range(128))

def test_shared_left_right_uv_is_rejected():
    surface,image=face()
    for p in surface['meshes'][0]['uv0']:p[0]=abs(p[0]-.5)
    with pytest.raises(ValueError,match='UV'):under_eye_mask(surface,image,128,128)

@pytest.mark.parametrize('problem',['wrong_image','missing_eye','nonmanifold','nonfinite','degenerate_uv','wrong_scale'])
def test_unverified_mapping_is_rejected(problem):
    surface,image=face();mesh=surface['meshes'][0]
    if problem=='wrong_image':image={'id':'other'}
    elif problem=='missing_eye':
        for p in mesh['positions']:
            if p[0]>0:p[2]=-.2
    elif problem=='nonmanifold':mesh['submeshes'][0]['triangles'].extend(mesh['submeshes'][0]['triangles'][:3])
    elif problem=='nonfinite':mesh['positions'][0][0]=float('nan')
    elif problem=='degenerate_uv':mesh['uv0']=[[0,0] for _ in mesh['positions']]
    else:
        for p in mesh['positions']:p[0]*=1000
    with pytest.raises(ValueError):under_eye_mask(surface,image,128,128)
