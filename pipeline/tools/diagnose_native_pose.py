"""Measure a captured native pose without editing Blender or a character source."""
import argparse,json,hashlib,math,sys
from pathlib import Path
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

def diagnose(path,suffix='.diagnosis.json'):
    data=json.loads(path.read_text(encoding='utf8'));body=data['body'];world=Matrix(body['world_matrix'])
    normal=world.to_3x3().inverted().transposed();points=[world@Vector(p) for p in body['positions']]
    normals=[(normal@Vector(n)).normalized() for n in body['normals']]
    faces=[tuple(body['triangles'][i:i+3]) for i in range(0,len(body['triangles']),3)]
    bvh=BVHTree.FromPolygons(points,faces,all_triangles=True)
    def signed(p):
        q,_,index,distance=bvh.find_nearest(p);a,b,c=faces[index]
        n=barycentric_transform(q,points[a],points[b],points[c],normals[a],normals[b],normals[c]).normalized()
        return (p-q).dot(n),distance
    hips=next(b for b in data['bones'] if b['name']=='J_Bip_C_Hips')['world_matrix'][1][3]
    knees=[b['world_matrix'][1][3] for b in data['bones'] if b['name'] in ('J_Bip_L_LowerLeg','J_Bip_R_LowerLeg')]
    records=[]
    for garment in data['garments']:
        world=Matrix(garment['world_matrix']);posed=[world@Vector(p) for p in garment['positions']]
        centers=[];center_heights=[];edges=set();heights=[s[1] for s in garment['source_positions']]
        for offset in range(0,len(garment['triangles']),3):
            ids=garment['triangles'][offset:offset+3];centers.append(sum((posed[i] for i in ids),Vector())/3)
            center_heights.append(sum(heights[i] for i in ids)/3)
            for a,b in zip(ids,ids[1:]+ids[:1]):edges.add(tuple(sorted((a,b))))
        counts={};deepest=0.
        for label,samples,source_heights in [('vertices',posed,heights),('face_centres',centers,center_heights),
            ('edge_midpoints',[(posed[a]+posed[b])*.5 for a,b in edges],[(heights[a]+heights[b])*.5 for a,b in edges])]:
            bad=[];lower=[];upper=[]
            for p,height in zip(samples,source_heights):
                value,distance=signed(p)
                if value<-.003 and distance<.12:
                    bad.append(-value);(lower if height<.93 else upper).append(-value)
            counts[label]={'samples':len(samples),'inside':len(bad),'max_depth_m':max(bad,default=0),
                'lower_inside':len(lower),'lower_max_depth_m':max(lower,default=0),'upper_inside':len(upper),'upper_max_depth_m':max(upper,default=0)}
            deepest=max(deepest,max(bad,default=0))
        hem=sorted(p.y for p,s in zip(posed,garment['source_positions']) if s[2]>.12 and s[1]<.60)
        shape=hashlib.sha256(json.dumps({k:garment[k] for k in ('source_positions','uv0','triangles')},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        skin=[Matrix(data['bones'][i]['world_matrix'])@Matrix(bind) for i,bind in zip(garment['bone_ids'],garment['bindposes'])]
        reconstruction=0.
        for p,raw,w in zip(posed,garment['source_positions'],garment['weights']):
            matrix=Matrix(((0,0,0,0),)*4)
            for index,weight in zip(w['indices'],w['weights']):
                if weight:matrix+=skin[index]*weight
            reconstruction=max(reconstruction,(p-matrix@Vector(raw)).length)
        records.append({'name':garment['name'],'geometry_stream_sha256':shape,'screening':counts,'deepest_penetration_m':deepest,
            'max_skin_reconstruction_error_m':reconstruction,'front_hem_samples':len(hem),'front_hem_max_y_m':max(hem,default=0),'front_hem_p95_y_m':hem[min(len(hem)-1,int(len(hem)*.95))] if hem else None,
            'front_hem_p95_above_hips_m':hem[min(len(hem)-1,int(len(hem)*.95))]-hips if hem else None})
    result={'reference':str(path),'pose_source':data['pose_source'],'clip':data.get('selected_preview_clip'),'frame':data['frame'],
        'hips_y_m':hips,'knees_y_m':knees,'records':records,'scope':'One actual native pose; nearest-surface normals, 3 mm penetration threshold; not exact closed-surface or all-frame collision proof'}
    destination=path.with_suffix(suffix)
    if destination.exists():raise FileExistsError('Do not overwrite diagnosis evidence')
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser=argparse.ArgumentParser();parser.add_argument('--suffix',default='.diagnosis.json');parser.add_argument('paths',nargs='+',type=Path);parsed=parser.parse_args(args)
    for path in parsed.paths:diagnose(path,parsed.suffix)
