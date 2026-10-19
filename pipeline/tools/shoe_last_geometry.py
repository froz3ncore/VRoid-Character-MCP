"""Smooth Mary Jane last: foot-derived outline, oval instep and continuous bowl."""
import math
import bpy
from mathutils import Vector
def upper(foot,outline_hull,CI,drop):
    center=Vector(((min(p.x for p in foot)+max(p.x for p in foot))/2,.006));N=72;vertices=[];faces=[];outer=[];inner=[]
    def cross(a,b):return a[0]*b[1]-a[1]*b[0]
    for i in range(N):
        angle=i*2*math.pi/N;direction=Vector((math.cos(angle),math.sin(angle)));hits=[]
        for p,q in zip(outline_hull,outline_hull[1:]+outline_hull[:1]):
            a=Vector(p);edge=Vector(q)-a;det=cross(direction,edge)
            if abs(det)<1e-12:continue
            t=cross(a-center,edge)/det;u=cross(a-center,direction)/det
            if t>0 and -1e-7<=u<=1.0000001:hits.append(t)
        assert hits;outer.append(center+direction*min(hits))
        radius=1/math.sqrt((direction.x/.029)**2+(direction.y/.048)**2);inner.append(center+direction*radius)
    # Lower outer ring, upper outer ring, then five curved bands to the oval rim.
    for ring in range(7):
        for i in range(N):
            edge=outer[i];bottom=-drop(edge.y)-.003
            t=max(0.,min(1.,(edge.y+.040)/.060));heel_weight=1-t*t*(3-2*t);outside=(bottom+.017)*(1-heel_weight)+.079*heel_weight
            if ring==0:p=Vector((edge.x,bottom,edge.y))
            else:
                t=(ring-1)/5;q=edge.lerp(inner[i],t);rim=.075-.30*(inner[i].y+.035)-drop(inner[i].y)
                y=outside*(1-t)+rim*t+.010*math.sin(math.pi*t);p=Vector((q.x,y,q.y))
            vertices.append(CI@p)
    center_bottom=sum(vertices[:N],Vector())/N;vertices.append(center_bottom)
    def face(ids,normal):
        if (vertices[ids[1]]-vertices[ids[0]]).cross(vertices[ids[2]]-vertices[ids[0]]).dot(CI.to_3x3()@normal)<0:ids.reverse()
        faces.append(ids)
    for i in range(N):face([i,(i+1)%N,7*N],Vector((0,-1,0)))
    for row in range(6):
        for i in range(N):
            ids=[row*N+i,row*N+(i+1)%N,(row+1)*N+(i+1)%N,(row+1)*N+i]
            normal=Vector((outer[i].x-center.x,0,outer[i].y-center.y)) if row==0 else Vector((0,1,0));face(ids,normal)
    mesh=bpy.data.meshes.new('Smooth oval-opening Mary Jane last');mesh.from_pydata(vertices,[],faces);mesh.update();return mesh,center
