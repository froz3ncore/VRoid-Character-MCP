"""Bounded two-bone IK and contact-aware toe-in; input/output in native Unity world."""
import math
import numpy as np

def unit(v):
    n=np.linalg.norm(v)
    if n<1e-10:raise ValueError('Degenerate leg vector')
    return v/n
def yaw(degrees):
    a=math.radians(degrees);c,s=math.cos(a),math.sin(a)
    return np.array([[c,0,s],[0,1,0],[-s,0,c]])
def between(a,b):
    a,b=unit(a),unit(b);v=np.cross(a,b);c=float(np.dot(a,b))
    if c<-1+1e-8:
        axis=unit(np.cross(a,np.eye(3)[np.argmin(np.abs(a))]));return 2*np.outer(axis,axis)-np.eye(3)
    k=np.array([[0,-v[2],v[1]],[v[2],0,-v[0]],[-v[1],v[0],0]])
    return np.eye(3)+k+k@k/(1+c)
def solve_leg(hip,knee,ankle,target,pole_yaw):
    upper=np.linalg.norm(knee-hip);lower=np.linalg.norm(ankle-knee);axis=unit(target-hip);distance=np.linalg.norm(target-hip)
    reachable=bool(abs(upper-lower)+1e-6<=distance<=upper+lower-1e-6)
    d=float(np.clip(distance,abs(upper-lower)+1e-6,upper+lower-1e-6))
    pole=yaw(pole_yaw)@(knee-hip);pole=pole-axis*np.dot(pole,axis)
    if np.linalg.norm(pole)<1e-8:pole=np.cross(axis,[1,0,0])
    pole=unit(pole);along=(upper*upper-lower*lower+d*d)/(2*d);height=math.sqrt(max(0,upper*upper-along*along))
    new_knee=hip+axis*along+pole*height;new_ankle=hip+axis*d
    return new_knee,new_ankle,reachable
def smoothstep(x):return np.clip(x,0,1)**2*(3-2*np.clip(x,0,1))
def transform_points(matrix,points):return (np.c_[points,np.ones(len(points))]@matrix.T)[:,:3]

def frame_world(frame):
    values={};counts={}
    for n in frame['rig']['nodes']:
        name=n['name'];i=counts.get(name,0);counts[name]=i+1
        values[name if i==0 else name+'#'+str(i)]=np.array(n['world_matrix'],dtype=float)
    return values

def contact_landmarks(reference):
    body=next(m for m in reference['base_meshes'] if m['name']=='Body');bones={reference['bones'][i]['name']:np.array(reference['bones'][i]['world_matrix']) for i in body['bone_ids']}
    result={}
    for side in 'LR':
        main=next(m for m in reference['garments'] if m['name'].startswith('FIT_ACCESSORY_Shoe_'+side+'_T00'))
        world=transform_points(np.array(main['world_matrix']),np.array(main['positions']));z=world[:,2];parts=[]
        for mask in [z>np.quantile(z,.65),z<np.quantile(z,.2)]:
            p=world[mask];low=p[p[:,1]<p[:,1].min()+.002];parts.append(low.mean(axis=0))
        result[side]=transform_points(np.linalg.inv(bones['J_Bip_'+side+'_Foot']),np.array(parts))
    return result

def shoe_surface_points(reference):
    body=next(m for m in reference['base_meshes'] if m['name']=='Body');bones={reference['bones'][i]['name']:np.array(reference['bones'][i]['world_matrix']) for i in body['bone_ids']};result={}
    for side in 'LR':
        mesh=next(m for m in reference['garments'] if m['name'].startswith('FIT_ACCESSORY_Shoe_'+side+'_T00'))
        result[side]=transform_points(np.linalg.inv(bones['J_Bip_'+side+'_Foot']),transform_points(np.array(mesh['world_matrix']),np.array(mesh['positions'])))
    return result

def build_gait(frames,landmarks,foot_degrees=6,upper_degrees=2,shoe_surfaces=None):
    source=[frame_world(f) for f in frames];times=np.array([f['seconds'] for f in frames]);count=len(frames)
    soles={s:np.array([transform_points(w['J_Bip_'+s+'_Foot'],landmarks[s]) for w in source]) for s in 'LR'}
    heights={s:p[:,0,1] for s,p in soles.items()}
    # Infer stance from actual measured sole height, not an assumed half-cycle.
    ground=min(np.quantile(h,.12) for h in heights.values())
    velocities={s:np.gradient(np.array([w['J_Bip_'+s+'_Foot'][2,3] for w in source]),times) for s in 'LR'}
    weights={s:smoothstep((ground+.028-h)/.018)*smoothstep((-velocities[s]-.03)/.12) for s,h in heights.items()}
    # Integrate the currently supporting sole's backward motion into root travel.
    root=np.zeros((count,3));support=[]
    for i in range(1,count):
        strengths={s:min(weights[s][i-1],weights[s][i]) for s in 'LR'}
        side=max(strengths,key=strengths.get);support.append(side if strengths[side]>.25 else None)
        if strengths[side]>.25:
            delta=source[i-1]['J_Bip_'+side+'_Foot'][:3,3]-source[i]['J_Bip_'+side+'_Foot'][:3,3];delta[1]=0;delta[2]=max(0,delta[2])
            root[i]=root[i-1]+delta
        elif i>1:root[i]=root[i-1]+(root[i-1]-root[i-2])
        else:root[i]=root[i-1]
    travel=root[-1].copy()
    # Remove tiny lateral wander from root trajectory; ankle IK handles the remainder.
    root[:,0]=0;travel[0]=0
    targets={};contact_rows=[]
    for s in 'LR':
        points=soles[s]+root[:,None,:];pivots=[];anchor=None;active=False
        # Handle a stance interval crossing the cycle boundary with a repeated cycle.
        for i in range(-count+1,count):
            j=i%(count-1);cycle=math.floor(i/(count-1));p=points[j]+cycle*travel
            k=0;raw=p[k]
            if weights[s][j]>.05:
                if not active:anchor=raw.copy();anchor[1]=ground;active=True
                goal=anchor.copy()
            else:
                active=False;goal=raw.copy()
            if i>=0:pivots.append((goal,k))
        targets[s]=pivots[:count]
    outputs=[];diagnostics=[]
    # Explicitly apply FK after each change so every auxiliary descendant follows.
    node_names={};counts={}
    for n in frames[0]['rig']['nodes']:
        i=counts.get(n['name'],0);counts[n['name']]=i+1;node_names[n['id']]=n['name'] if i==0 else n['name']+'#'+str(i)
    parents={node_names[n['id']]:node_names.get(n['parent_id']) for n in frames[0]['rig']['nodes']}
    def hierarchy(world,changes):
        result={};visiting=set()
        def get(name):
            if name in result:return result[name]
            if name in visiting:raise ValueError('Rig cycle')
            visiting.add(name);parent=parents[name]
            if name in changes:m=changes[name]
            elif parent in world:m=get(parent)@np.linalg.inv(world[parent])@world[name]
            else:m=world[name].copy()
            result[name]=m;visiting.remove(name);return m
        for n in world:get(n)
        return result
    pelvis_drops=[]
    for i,world in enumerate(source):
        required=0.
        for s,sign in [('L',1),('R',-1)]:
            hip,knee,foot=[world[f'J_Bip_{s}_{p}'] for p in ['UpperLeg','LowerLeg','Foot']]
            h,k,f=hip[:3,3],knee[:3,3],foot[:3,3];goal,pivot=targets[s][i];rotation=yaw(sign*foot_degrees)@foot[:3,:3]
            raw=soles[s][i,pivot]+root[i];contact=raw+(goal-raw)*float(weights[s][i]);target=contact-root[i]-rotation@landmarks[s][pivot]
            if shoe_surfaces is not None:target[1]=max(target[1],ground+.0015-float((shoe_surfaces[s]@rotation.T)[:,1].min()))
            length=np.linalg.norm(k-h)+np.linalg.norm(f-k)-.0002;horizontal=np.linalg.norm((target-h)[[0,2]])
            if horizontal>=length:raise ValueError('Contact target beyond horizontal leg reach')
            max_hip_y=target[1]+math.sqrt(length*length-horizontal*horizontal)
            required=min(required,max_hip_y-h[1])
        pelvis_drops.append(required)
    # Anticipate low pelvis requirements with a bounded cyclic slope, avoiding pops.
    raw_drops=np.array(pelvis_drops);pelvis_drops=np.array([min(raw_drops[(i+j)%(count-1)]+.0015*abs(j) for j in range(-10,11)) for i in range(count)])
    if pelvis_drops.min()<-.015:raise ValueError('Contact requires more than 15mm pelvis adaptation')
    def under_hips(name):
        while name in parents:
            if name=='J_Bip_C_Hips':return True
            name=parents[name]
        return False
    for i,world in enumerate(source):
        world={name:m.copy() for name,m in world.items()}
        for name,m in world.items():
            if under_hips(name):m[1,3]+=pelvis_drops[i]
        changes={};row={'seconds':float(times[i]),'pelvis_drop_mm':float(pelvis_drops[i]*1000),'sides':{}}
        for s,sign in [('L',1),('R',-1)]:
            hip,knee,foot=[world[f'J_Bip_{s}_{p}'] for p in ['UpperLeg','LowerLeg','Foot']]
            h,k,f=hip[:3,3],knee[:3,3],foot[:3,3]
            # Pivot around a measured sole point, not the ankle; preserve heel pitch.
            goal,pivot=targets[s][i];foot_rotation=yaw(sign*foot_degrees)@foot[:3,:3]
            raw_contact=soles[s][i,pivot]+root[i]
            lock=float(weights[s][i]);contact=raw_contact+(goal-raw_contact)*lock
            target=contact-root[i]-foot_rotation@landmarks[s][pivot]
            lift=0.
            if shoe_surfaces is not None:
                lift=max(0.,ground+.0015-float((shoe_surfaces[s]@foot_rotation.T)[:,1].min())-target[1]);target[1]+=lift;contact[1]+=lift
            nk,nf,reachable=solve_leg(h,k,f,target,sign*upper_degrees)
            uh=hip.copy();uh[:3,:3]=between(k-h,nk-h)@hip[:3,:3]
            kl=knee.copy();kl[:3,:3]=between(f-k,nf-nk)@knee[:3,:3];kl[:3,3]=nk
            ft=foot.copy();ft[:3,:3]=foot_rotation;ft[:3,3]=nf
            changes.update({f'J_Bip_{s}_UpperLeg':uh,f'J_Bip_{s}_LowerLeg':kl,f'J_Bip_{s}_Foot':ft})
            actual=nf+foot_rotation@landmarks[s][pivot]+root[i]
            row['sides'][s]=dict(weight=lock,pivot=pivot,reachable=reachable,sole_target_error_mm=float(np.linalg.norm(actual-contact)*1000),plant_world=actual.tolist(),plant_target=contact.tolist(),ankle_correction_mm=float(np.linalg.norm(nf-f)*1000),floor_lift_mm=lift*1000,shoe_floor_clearance_mm=None if shoe_surfaces is None else float(((shoe_surfaces[s]@foot_rotation.T)[:,1].min()+nf[1]-ground)*1000),upper_length_error_mm=float(abs(np.linalg.norm(nk-h)-np.linalg.norm(k-h))*1000),lower_length_error_mm=float(abs(np.linalg.norm(nf-nk)-np.linalg.norm(f-k))*1000))
        outputs.append(hierarchy(world,changes));diagnostics.append(row)
    # Endpoint duplicates the first pose; root travel remains separately accumulated.
    outputs[-1]={k:v.copy() for k,v in outputs[0].items()};root[-1]=travel
    return outputs,root,diagnostics,dict(ground_estimate=float(ground),travel_per_cycle_m=travel.tolist(),duration=float(times[-1]),stance_weights={s:w.tolist() for s,w in weights.items()},landmarks={s:p.tolist() for s,p in landmarks.items()},foot_offset_degrees=foot_degrees,knee_pole_offset_degrees=upper_degrees)
