"""Verify real engine playback, including inter-key shoe-floor clearance."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from toein_gait_math import shoe_surface_points
def load(p):return json.loads(p.read_text(encoding='utf8'))
def main(a):
    build=load(a.project/'build.json');keys=load(a.project/'key-check.json');runtime=load(a.project/'runtime-samples.json');assert keys['passed'] and runtime['continuous_playback'] and runtime['cycles_observed']>=3
    reference=load(a.reference);surfaces=shoe_surface_points(reference);rows=build['diagnostics'];times=np.array([r['seconds'] for r in rows]);profile=build['profile'];ground=profile['ground_estimate'];side_results={}
    for side in 'LR':
        points=surfaces[side].copy();points[:,0]*=-1;clearances=[];target_errors=[];stance_errors=[];groups={}
        for f in runtime['frames']:
            matrix=np.array(f['foot_matrices'][side]).reshape(3,4);world=points@matrix[:,:3].T+matrix[:,3];clearances.append(float(world[:,1].min()-ground)*1000)
            actual=np.array(f['feet'][side]);target=np.array([np.interp(f['phase'],times,[r['sides'][side]['plant_target'][axis] for r in rows]) for axis in range(3)]);target[0]*=-1;target[2]+=f['cycle']*profile['travel_per_cycle_m'][2]
            error=float(np.linalg.norm(actual-target)*1000);target_errors.append(error);weight=float(np.interp(f['phase'],times,[r['sides'][side]['weight'] for r in rows]))
            if weight>.999:
                stance_errors.append(error);segment=0 if f['phase']<profile['duration']/2 else 1;groups.setdefault((f['cycle'],segment),[]).append(actual[[0,2]])
        span=max((float(np.linalg.norm(np.ptp(np.array(v),axis=0))*1000) for v in groups.values() if len(v)>1),default=0.)
        result=dict(minimum_entire_shoe_floor_clearance_mm=min(clearances),maximum_contact_target_error_mm=max(target_errors),maximum_strong_stance_target_error_mm=max(stance_errors),maximum_strong_stance_horizontal_span_mm=span,measured_shoe_vertices=len(points),strong_stance_samples=len(stance_errors))
        assert result['minimum_entire_shoe_floor_clearance_mm']>=0,(side,result)
        assert result['maximum_strong_stance_target_error_mm']<1,(side,result)
        # Between keys, an airborne sole follows quaternion interpolation, not
        # a straight line between world-point targets. Record that discrepancy;
        # require the 1mm lock only during full stance, plus zero floor penetration
        # across every measured frame. Key poses have independent engine checks.
        assert span<1,(side,result)
        side_results[side]=result
    report=dict(passed=True,source_artifact_sha256=hashlib.sha256((a.project/'avatar.glb').read_bytes()).hexdigest(),key_pose_comparisons=keys['comparisons'],maximum_key_pose_error_mm=keys['maximum_position_error_mm'],actual_rendered_frames=len(runtime['frames']),cycles_observed=runtime['cycles_observed'],sides=side_results,scope='Actual standalone Godot generic-GLB animation playback and source rigid shoe vertices transformed by measured runtime Foot matrices. No godot-vrm importer, VRM physics, AnotherMe integration, cloth/body collision or arbitrary terrain certificate.')
    with (a.out or a.project/'runtime-acceptance.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path);main(p.parse_args())
