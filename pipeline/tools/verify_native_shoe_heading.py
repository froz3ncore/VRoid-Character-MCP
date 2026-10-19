"""Actual imported shoe rigid fit, unchanged other garments and motion stability."""
import argparse, itertools, json, math, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'));sys.path.insert(0,str(ROOT/'tools'))
from vroid_mcp.wear_fit import world,triangles,Surface
from plan_shoe_heading_fit import sections,transform

def point_error(a,b,a_surface=None,b_surface=None,events=None):
    a,b=np.asarray(a),np.asarray(b)
    if a.shape==b.shape:
        direct=float(np.max(np.linalg.norm(a-b,axis=1)))
        if direct<2e-6:return direct
    def directed(p,q,surface_factory):
        size=1e-5;cells={}
        for point in q:
            key=tuple(np.floor(point/size).astype(int));cells.setdefault(key,[]).append(point)
        maximum=0.;surface=None
        for point in p:
            key=np.floor(point/size).astype(int)
            choices=[x for d in itertools.product((-1,0,1),repeat=3) for x in cells.get(tuple(key+np.array(d)),[])]
            distance=float(np.min(np.linalg.norm(np.array(choices)-point,axis=1))) if choices else math.inf
            if distance>2e-6 and surface_factory is not None:
                if surface is None:surface=surface_factory()
                distance=surface.distance(point)
                if events is not None:events.append({'point':point.tolist(),'surface_distance_mm':distance*1000,'reason':'Retriangulation/degenerate filtering omitted a previously exported vertex; verify its location against the actual triangle surface at the same strict tolerance.'})
            assert math.isfinite(distance),'Native geometry point missing from rigidly predicted surface'
            maximum=max(maximum,distance)
        return maximum
    return max(directed(a,b,b_surface),directed(b,a,a_surface))

def main(a):
    old=json.loads(a.before.read_text(encoding='utf8'));new=json.loads(a.after.read_text(encoding='utf8'));build=json.loads(a.build.read_text(encoding='utf8'));plan=json.loads(Path(build['heading_plan']).read_text(encoding='utf8'))
    assert old['pose_source']==new['pose_source']=='native_edit'
    original={m['name']:m for m in old['garments']};current={m['name']:m for m in new['garments']}
    assert original.keys()==current.keys() and len(current)==97
    body=next(m for m in new['base_meshes'] if m['name']=='Body');oldbody=next(m for m in old['base_meshes'] if m['name']=='Body')
    body_error=point_error(world(body),world(oldbody));assert body_error<2e-6
    assert new['base_body_occlusion']==old['base_body_occlusion'] and new['base_native_shoes']['triangle_count']==0
    shoes=[];preserved=[];surface_checks=[]
    for name,mesh in current.items():
        if name in build['native_transforms']:
            matrix=np.array(build['native_transforms'][name]);expected=transform(np.array(world(original[name])),matrix)
            predicted_triangles=transform(np.array(triangles(original[name],world(original[name]))).reshape(-1,3),matrix).reshape(-1,3,3).tolist()
            events=[]
            error=point_error(world(mesh),expected,a_surface=lambda:Surface(triangles(mesh,world(mesh))),b_surface=lambda:Surface(predicted_triangles),events=events);assert error<2e-6,(name,error)
            if events:surface_checks.append({'mesh':name,'checks':events})
            shoes.append({'mesh':name,'maximum_actual_rigid_fit_error_mm':error*1000,'before_vertices':len(original[name]['positions']),'after_vertices':len(mesh['positions'])})
        else:
            error=point_error(world(mesh),world(original[name]));assert error<2e-6,(name,error)
            preserved.append({'mesh':name,'maximum_actual_surface_difference_mm':error*1000})
    assert len(shoes)==8 and len(preserved)==89
    headings=[]
    for row in plan['rows']:
        mesh=current[row['main_mesh']];surface=np.array(triangles(mesh,world(mesh)));stations=np.array(row['stations_z_m']);foot=np.array(row['foot_sections_x_m']);actual=sections(surface,stations)
        fc,sc=foot.mean(axis=1),actual.mean(axis=1);rms=float(np.sqrt(np.mean((sc-fc)**2))*1000)
        axis=math.degrees(math.atan(float(np.polyfit(stations,sc,1)[0])));delta=axis-row['foot_centerline_heading_degrees']
        assert rms<1 and abs(delta)<1,(row['side'],rms,delta)
        headings.append({'side':row['side'],'before_centerline_rms_mm':row['before_centerline_rms_mm'],'actual_centerline_rms_mm':rms,'foot_axis_degrees':row['foot_centerline_heading_degrees'],'actual_shoe_axis_degrees':axis,'actual_axis_difference_degrees':delta,'sampled_lateral_margin_min_mm':float(np.minimum(foot[:,0]-actual[:,0],actual[:,1]-foot[:,1]).min()*1000)})
    canonical={new['bones'][i]['name']:np.array(new['bones'][i]['world_matrix']) for i in body['bone_ids']};motions=[]
    for path in a.pose:
        data=json.loads(path.read_text(encoding='utf8'));pb=next(m for m in data['base_meshes'] if m['name']=='Body');bones={data['bones'][i]['name']:np.array(data['bones'][i]['world_matrix']) for i in pb['bone_ids']};rows=[]
        for mesh in data['garments']:
            if not mesh['name'].startswith('FIT_ACCESSORY_Shoe_'):continue
            side=mesh['name'].split('_')[3];bone='J_Bip_'+side+'_Foot';matrix=canonical[bone]@np.linalg.inv(bones[bone]);points=transform(np.array(world(mesh)),matrix)
            error=point_error(points,world(current[mesh['name']]));assert error<1e-5,(path,mesh['name'],error)
            rows.append({'mesh':mesh['name'],'maximum_foot_relative_shape_drift_mm':error*1000})
        assert len(rows)==8
        motions.append({'reference':str(path.resolve()),'frame':data['frame'],'rows':rows})
    report={'passed':True,'before':str(a.before.resolve()),'after':str(a.after.resolve()),'body_world_max_delta_mm':body_error*1000,'shoe_rigid_fit':shoes,'retriangulated_vertex_surface_checks':surface_checks,'preserved_89_garment_surfaces':preserved,'centerline_heading':headings,'motion':motions,'scope':'Actual native edit-pose surfaces: prescribed rigid shoe fit and other 89 garments/Body preserved. Native sampled shoe motion stability in each base Foot frame. No full enclosure/all-motion collision or adopted toe-in stance claim.'}
    with a.out.open('x',encoding='utf8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'heading':headings,'motion_cases':len(motions),'maximum_motion_drift_mm':max((r['maximum_foot_relative_shape_drift_mm'] for s in motions for r in s['rows']),default=None)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--pose',type=Path,action='append',default=[]);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
