"""Read-only original-face provenance and extraction-loss audit in Blender."""
import argparse, hashlib, json, sys
from pathlib import Path
import bpy, bmesh, numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))

def original_points(record):
    obj=bpy.data.objects[record['object']]
    points=[obj.matrix_world@v.co for v in obj.data.vertices]
    center=Vector(tuple((min(p[k] for p in points)+max(p[k] for p in points))/2 for k in range(3)))
    anchor=(Vector(record['bounds'][0])+Vector(record['bounds'][1]))/2
    return [C@(p+anchor-center) for p in points]

def image_sampler(obj):
    image=next(n.image for m in obj.data.materials for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image)
    pixels=np.empty(len(image.pixels),dtype=np.float32);image.pixels.foreach_get(pixels)
    pixels=pixels.reshape(image.size[1],image.size[0],4)
    def luma(uv):
        x=int(max(0,min(image.size[0]-1,uv[0]*image.size[0])))
        y=int(max(0,min(image.size[1]-1,uv[1]*image.size[1])))
        return float(pixels[y,x,:3]@np.array([.2126,.7152,.0722]))
    return luma

def topology(mesh):
    bm=bmesh.new();bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6)
    result={'vertices_welded':len(bm.verts),'faces':len(bm.faces),
            'boundary_edges':sum(e.is_boundary for e in bm.edges),
            'nonmanifold_nonboundary_edges':sum(not e.is_manifold and not e.is_boundary for e in bm.edges)}
    remaining={e for e in bm.edges if e.is_boundary};loops=[]
    while remaining:
        pending=[remaining.pop()];component=[]
        while pending:
            edge=pending.pop();component.append(edge)
            for v in edge.verts:
                for other in v.link_edges:
                    if other in remaining:remaining.remove(other);pending.append(other)
        vertices={v for edge in component for v in edge.verts}
        loops.append({'edges':len(component),'perimeter_m':sum(e.calc_length() for e in component),
            'bounds_local':[[min(v.co[k] for v in vertices) for k in range(3)],[max(v.co[k] for v in vertices) for k in range(3)]],
            'closed_simple':all(sum(e in component for e in v.link_edges)==2 for v in vertices)})
    result['boundary_components']=loops
    bm.free();return result

def audit(out):
    source=Path(bpy.data.filepath);sha=hashlib.sha256(source.read_bytes()).hexdigest()
    manifest=json.loads((ROOT/'projects/whale-maid/tripo-source/parts_manifest_v01.json').read_text(encoding='utf8'))
    rebase=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/candidate-e/build.json').read_text(encoding='utf8'))
    rows=[]
    for record in manifest['parts']:
        if record['source_id'] not in (4,5):continue
        side='R' if record['source_id']==4 else 'L';sign=1 if side=='R' else -1
        obj=bpy.data.objects[record['object']];points=original_points(record);luma=image_sampler(obj)
        fitted=bpy.data.objects['FIT_ACCESSORY_Shoe_'+side+'_T%03d'%record['source_id']]
        fp=[C@fitted.matrix_world@v.co for v in fitted.data.vertices]
        tree=BVHTree.FromPolygons(fp,[tuple(p.vertices) for p in fitted.data.polygons])
        bone='J_Bip_'+side+'_Foot';old=Matrix(rebase['bones_before'][bone]);new=Matrix(rebase['bones_after'][bone]);transform=new@old.inverted()
        foot_x=old.translation.x
        def fit(p):return transform@Vector(((p.x-sign*.050)*1.6+foot_x,p.y*1.35+.020,p.z*1.70-.019))
        faces=[]
        for face in obj.data.polygons:
            ps=[points[v] for v in face.vertices];center=sum(ps,Vector())/len(ps)
            uv=[obj.data.uv_layers.active.data[li].uv.copy() for li in face.loop_indices]
            samples=[center]+[p*.8+center*.2 for p in ps]
            distances=[tree.find_nearest(fit(p))[3] for p in samples]
            faces.append({'face':face.index,'centroid_original_native':list(center),'centroid_fitted_native':list(fit(center)),
                'min_height':min(p.y for p in ps),'max_height':max(p.y for p in ps),
                'luma_corners':[luma(u) for u in uv],'luma_center':luma(sum(uv,Vector((0,0)))/len(uv)),
                'nearest_fitted_mm':[d*1000 for d in distances],
                'all_samples_missing_over_0_1mm':min(distances)>.0001,
                'any_sample_missing_over_0_1mm':max(distances)>.0001})
        low=[f for f in faces if f['max_height']<.045]
        rows.append({'side':side,'original':record['object'],'fitted':fitted.name,
            'original_topology':topology(obj.data),'fitted_topology':topology(fitted.data),
            'original_below_45mm_faces':len(low),
            'below_45mm_any_missing_faces':sum(f['any_sample_missing_over_0_1mm'] for f in low),
            'below_45mm_all_missing_faces':sum(f['all_samples_missing_over_0_1mm'] for f in low),
            'faces':faces})
    assert hashlib.sha256(source.read_bytes()).hexdigest()==sha and not bpy.data.is_dirty
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf8') as f:json.dump({'source':str(source),'sha256':sha,'source_unchanged':True,'rows':rows},f,ensure_ascii=False,indent=2)
    print(json.dumps([{k:v for k,v in r.items() if k!='faces'} for r in rows]),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    audit(p.parse_args(sys.argv[sys.argv.index('--')+1:]).out)
