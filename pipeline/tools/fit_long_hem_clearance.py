"""One bounded, multi-pose lower-rear clearance experiment; never edits sources.

Uses frozen native skin matrices to fit source X/Z offsets, preserving every Y
coordinate. A smooth quadratic objective and hard 40 mm displacement disk
bound limit the patch. Predictions require fresh native captures.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from measure_exact_contact import (TriangleGrid, load_reference,
    pair_point_triangle_distance, winding_number)
from predict_weight_shift import skin_matrices, reconstruct


def nearest(points, body):
    triangles = np.asarray(body['positions'])[np.asarray(body['triangles']).reshape(-1,3)]
    grid = TriangleGrid(triangles,.1)
    closest, distances = [], []
    for point in points:
        ids = np.unique(grid.candidates(point,.15))
        if not len(ids):
            ids = np.arange(len(triangles))
        distance, positions = pair_point_triangle_distance(
            np.broadcast_to(point,(len(ids),3)), triangles[ids])
        k = int(np.argmin(distance))
        closest.append(positions[k]); distances.append(distance[k])
    return np.array(distances),np.array(closest),winding_number(points,triangles,chunk=128)


def rear_exit(point, direction, body_triangles):
    """Intersect the posed source-back ray with the body surface."""
    edge1=body_triangles[:,1]-body_triangles[:,0]
    edge2=body_triangles[:,2]-body_triangles[:,0]
    h=np.cross(np.broadcast_to(direction,edge2.shape),edge2)
    determinant=np.einsum('ij,ij->i',edge1,h)
    valid=np.abs(determinant)>1e-12
    inv=np.zeros_like(determinant);inv[valid]=1/determinant[valid]
    s=point-body_triangles[:,0]
    u=inv*np.einsum('ij,ij->i',s,h)
    q=np.cross(s,edge1)
    v=inv*(q@direction)
    t=inv*np.einsum('ij,ij->i',edge2,q)
    valid &= (u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)&(t>1e-7)
    if not valid.any():return None
    index=int(np.argmin(np.where(valid,t,np.inf)))
    normal=np.cross(edge1[index],edge2[index]);normal/=np.linalg.norm(normal)
    if normal@direction<0:normal=-normal
    return t[index],normal


def main(a):
    assert not a.out.exists()
    a.out.mkdir(parents=True)
    measurement = json.loads(a.contact.read_text(encoding='utf8'))
    references = [load_reference(p) for p in a.reference]
    first = references[0]['garments'][0]
    source = np.asarray(first['source_positions'])
    tris = np.asarray(first['triangles']).reshape(-1,3)
    keys = [tuple(np.round(p,6)) for p in source]
    base_source=source.copy()
    if a.base_nudges:
        adjustments=json.loads(a.base_nudges.read_text(encoding='utf8'))['nudges']
        shifts={tuple(np.round(r['source_position'],6)):
            np.asarray(r['new_source_position'])-r['source_position'] for r in adjustments}
        for index,key in enumerate(keys):
            if key in shifts:base_source[index]+=shifts[key]
    groups = {}
    for index,key in enumerate(keys):
        groups.setdefault(key,[]).append(index)
    # Front/waist and the original hem heights are protected.
    eligible = (source[:,1]<.55)&(source[:,1]>.35)&(source[:,2]<-.05)
    face_ids = set()
    inside_ids = set()
    for run in measurement['runs']:
        g = run['garments'][0]
        face_ids.update(i for i in g['tri_tri']['garment_faces'] if eligible[tris[i]].all())
        inside_ids.update(r['vertex'] for r in g['worst_inside_vertices'] if eligible[r['vertex']])
    core = {keys[i] for i in inside_ids}
    core.update(keys[i] for fi in face_ids for i in tris[fi])
    assert core
    mutable = set(core)
    # A single adjacent ring feathers the change into surrounding cloth.
    for tri in tris:
        if any(keys[i] in core for i in tri):
            mutable.update(keys[i] for i in tri if eligible[i])
    mutable = sorted(mutable)
    ids = {key:i for i,key in enumerate(mutable)}
    count = len(ids)
    laplacian = np.eye(count)
    edges = {tuple(sorted((keys[int(x)],keys[int(y)])))
             for tri in tris for x,y in zip(tri,np.roll(tri,-1)) if keys[int(x)]!=keys[int(y)]}
    for x,y in edges:
        ix,iy = ids.get(x),ids.get(y)
        if ix is not None:laplacian[ix,ix]+=3.
        if iy is not None:laplacian[iy,iy]+=3.
        if ix is not None and iy is not None:
            laplacian[ix,iy]-=3.;laplacian[iy,ix]-=3.
    hessian = np.kron(laplacian,np.eye(2))
    # Barycentric samples include edges and face interiors, not just vertices.
    samples = [([i],[1.]) for i in sorted(inside_ids)]
    for fi in sorted(face_ids):
        tri = tris[fi].tolist()
        for i in range(5):
            for j in range(5-i):
                samples.append((tri,[i/4,j/4,(4-i-j)/4]))
        samples.append((tri,[1/3,1/3,1/3]))
    sample_key = lambda s:tuple(sorted((keys[i],round(w,9)) for i,w in zip(*s) if w))
    samples = list({sample_key(s):s for s in samples}.values())
    rows, bounds, provenance = [], [], []
    reconstruction_errors = []
    for ref in references:
        data,g = ref['data'],ref['garments'][0]
        assert g['triangles']==first['triangles']
        assert np.max(np.abs(np.asarray(g['source_positions'])[eligible]-source[eligible])) < 1e-5
        names = [b['name'] for b in data['bones']]
        matrices = skin_matrices(data,g)
        assert all(len(e['indices'])<=4 for e in g['weights'])
        reconstructed = reconstruct(g,matrices,names)
        error = float(np.linalg.norm(reconstructed-g['positions'],axis=1).max())
        assert error < 1e-5,error
        reconstruction_errors.append(error)
        jacobians = []
        for entry in g['weights']:
            jacobians.append(sum((w*matrices[s][:3,[0,2]] for s,w in zip(entry['indices'],entry['weights'])),np.zeros((3,2))))
        positions = np.asarray(g['positions'])
        # D changes geometry only; these source offsets do not drive the solver.
        for index,(old,new) in enumerate(zip(source,base_source)):
            if np.array_equal(old,new):continue
            entry=g['weights'][index]
            jacobian=sum((w*matrices[s][:3,:3] for s,w in zip(entry['indices'],entry['weights'])),np.zeros((3,3)))
            positions[index]+=jacobian@(new-old)
        body_triangles=np.asarray(ref['body']['positions'])[np.asarray(ref['body']['triangles']).reshape(-1,3)]
        points = np.array([sum((positions[i]*w for i,w in zip(*sample)),np.zeros(3)) for sample in samples])
        distances,closest,windings = nearest(points,ref['body'])
        inside_count = 0
        for k,((indices,weights),point,distance,close,winding) in enumerate(zip(samples,points,distances,closest,windings)):
            if distance > .08:continue
            inside = winding > .55
            if .45<=winding<=.55:continue
            normal = close-point if inside else point-close
            length = np.linalg.norm(normal)
            if length<1e-9:continue
            normal /= length
            if inside:
                direction=sum((-weight*jacobians[index][:,1] for index,weight in zip(indices,weights)),np.zeros(3))
                exit_result=rear_exit(point,direction,body_triangles)
                if exit_result is None:
                    raise ValueError('Inside sample has no rear exit ray hit; do not fit ambiguous body region')
                exit_distance,normal=exit_result
                required=(normal@direction)*exit_distance+a.margin_mm/1000
            else:
                required=-distance+a.margin_mm/1000
            row = np.zeros(2*count)
            for index,weight in zip(indices,weights):
                group = ids.get(keys[index])
                if group is not None:row[2*group:2*group+2] += weight*(normal@jacobians[index])
            if np.linalg.norm(row)<1e-12:continue
            rows.append(row)
            bounds.append(required)
            inside_count+=int(inside)
            provenance.append({'reference':str(ref['path']),'sample':k,'inside':bool(inside),'distance_m':float(distance)})
        print(json.dumps({'reference':str(ref['path']),'sampled_inside':inside_count,'samples':len(samples),'reconstruction_error_m':error}),flush=True)
    contact_rows = len(rows)
    radius = a.max_mm/1000
    matrix,target = np.array(rows),np.array(bounds)
    # A bounded least-violation fit remains well defined when poses conflict.
    penalty=1000.
    lipschitz=float(np.linalg.eigvalsh(hessian+penalty*matrix.T@matrix)[-1])
    values=np.zeros(2*count);momentum=values.copy();acceleration=1.
    for iteration in range(2400):
        residual=np.maximum(target-matrix@momentum,0)
        gradient=hessian@momentum-penalty*(matrix.T@residual)
        next_values=(momentum-gradient/lipschitz).reshape(-1,2)
        next_values[:,1]=np.minimum(next_values[:,1],0.)
        lengths=np.linalg.norm(next_values,axis=1)
        next_values*=np.minimum(1.,radius/np.maximum(lengths,1e-30))[:,None]
        next_values=next_values.reshape(-1)
        change=float(np.abs(next_values-values).max())
        next_acceleration=(1+np.sqrt(1+4*acceleration**2))/2
        momentum=next_values+(acceleration-1)/next_acceleration*(next_values-values)
        values=next_values;acceleration=next_acceleration
        if iteration%400==0:print(json.dumps({'iteration':iteration,'max_violation_mm':float(np.maximum(target-matrix@values,0).max()*1000)}),flush=True)
        if iteration>400 and change<1e-9:break
    delta = values.reshape(-1,2)
    # No relaxation of the geometric bound if posed constraints conflict.
    lengths = np.linalg.norm(delta,axis=1)
    delta *= np.minimum(1.,radius/np.maximum(lengths,1e-30))[:,None]
    values = delta.reshape(-1)
    violation = float(np.maximum(target[:contact_rows]-matrix[:contact_rows]@values,0).max())
    nudges = []
    for key,index in ids.items():
        if np.linalg.norm(delta[index])<1e-6:continue
        vertex = groups[key][0]
        old = base_source[vertex]
        new = old+np.array([delta[index,0],0.,delta[index,1]])
        entry = first['weights'][vertex]
        slot = entry['indices'][int(np.argmax(entry['weights']))]
        nudges.append({'vertex':vertex,'source_position':old.tolist(),'new_source_position':new.tolist(),
            'depth_m':0.,'dominant_bone':references[0]['bone_names'][slot]})
    report = {'tool':'fit_long_hem_clearance','references':[str(p) for p in a.reference],
        'nudges':nudges,'mutable_source_positions':count,'sample_points':len(samples),
        'contact_constraints':contact_rows,'iterations':iteration+1,
        'method':'Smoothed least-violation fit to rear-exit planes, source X/Z only, rearward Z, hard displacement disk',
        'fitter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'base_nudges':str(a.base_nudges) if a.base_nudges else None,
        'remaining_linear_constraint_violation_m':violation,
        'max_source_move_mm':float(np.linalg.norm(delta,axis=1).max()*1000),
        'source_y_unchanged':True,'margin_mm':a.margin_mm,
        'skin_reconstruction_errors_m':reconstruction_errors,
        'constraint_provenance':provenance,'adopted':False,
        'scope':'Frozen skin transforms only; bounded experimental patch, not native or collision-free acceptance.'}
    (a.out/'fit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('nudges','constraint_provenance')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--reference',type=Path,action='append',required=True)
    parser.add_argument('--contact',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--base-nudges',type=Path)
    parser.add_argument('--margin-mm',type=float,default=3.)
    parser.add_argument('--max-mm',type=float,default=40.)
    args=parser.parse_args()
    assert 0<args.margin_mm<=5 and 0<args.max_mm<=40
    main(args)
