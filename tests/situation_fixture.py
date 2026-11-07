"""Nonblank 512 native-double raster and independently constructed optical receipt."""
import math
from vroid_mcp.texture_mapping import png_rgba


def subject_png():
    pixels=bytearray(b'\xf4\xf4\xf4\xff'*(512*512))
    for y in range(80,440):
        for x in range(205,307):
            if y>180 or (x-256)**2+(y-130)**2<2500:
                i=(y*512+x)*4;pixels[i:i+4]=bytes((45+y%80,65,120+x%80,255))
    return png_rgba(512,512,bytes(pixels))


def optical_proof(profile):
    # Scene box [2,1,-8]..[4,3,-4], symmetric 30 degree perspective.
    H=2;full=profile['fit']=='full-body';top=3 if full else 3-profile['top']*H
    bottom=1 if full else 3-profile['bottom']*H;rad=math.radians(profile['yaw'])
    n=[math.sin(rad),0,math.cos(rad)];right=[-n[2],0,n[0]];forward=[-n[0],0,-n[2]]
    width=abs(n[2])+2*abs(n[0]) if full or profile['half'] is None else profile['half']*H
    depth=abs(n[0])+2*abs(n[2]);span=max(top-bottom,.14*H)*1.1
    distance=max(profile['distance']*span,(depth+max(width,(top-bottom)/2)/math.tan(math.pi/12))*1.000001,depth+.02)
    target=[3,(top+bottom)/2,-6];near=.01;far=max(1000,distance+depth+H+1);f=1/math.tan(math.pi/12)
    matrix=[f,0,0,0,0,f,0,0,0,0,-(far+near)/(far-near),-2*far*near/(far-near),0,0,-1,0]
    return dict(schema='vroid-situation-framing-v1',requested_profile=profile,source_root_id='owned',
        source_renderer_count=3,source_bounds={'min':[2,1,-8],'max':[4,3,-4]},
        camera_readback_verified=True,projection_verified=True,containment_verified=True,
        projection='perspective',projection_matrix=matrix,aspect=1,fov_degrees=30,near_clip=near,far_clip=far,
        source_span=span,region_world_top=top,region_world_bottom=bottom,effective_half_width=width,
        requested_distance=profile['distance']*span,requested_distance_multiplier=profile['distance'],
        effective_distance_multiplier=distance/span,distance=distance,target=target,
        position=[target[i]+n[i]*distance for i in range(3)],forward=forward,right_vector=right,up_vector=[0,1,0],
        yaw_degrees=profile['yaw'],fit=profile['fit'],inactive_fields=['top','bottom','half'] if full else [])
