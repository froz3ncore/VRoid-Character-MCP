"""Fit shoe/foot footprint centerlines with bounded yaw and translation only."""
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import world,triangles

def sections(surface,stations):
    edges=np.concatenate((surface[:,[0,1]],surface[:,[1,2]],surface[:,[2,0]]))
    a,b=edges[:,0],edges[:,1];dz=b[:,2]-a[:,2]
    rows=[]
    for z in stations:
        select=(abs(dz)>1e-10)&(np.minimum(a[:,2],b[:,2])<=z)&(np.maximum(a[:,2],b[:,2])>=z)
        x=a[select,0]+(z-a[select,2])*(b[select,0]-a[select,0])/dz[select]
        assert len(x)>2,(z,len(x))
        rows.append([float(x.min()),float(x.max())])
    return np.array(rows)

def transform(points,matrix):return points@matrix[:3,:3].T+matrix[:3,3]
def rigid(pivot,degrees,translation):
    a=math.radians(degrees);c,s=math.cos(a),math.sin(a)
    m=np.eye(4);m[:3,:3]=[[c,0,s],[0,1,0],[-s,0,c]]
    m[:3,3]=pivot-m[:3,:3]@pivot+translation
    return m

def main(a):
    data=json.loads(a.reference.read_text(encoding='utf8'));assert data['pose_source']=='native_edit'
    body=next(m for m in data['base_meshes'] if m['name']=='Body');bp=np.array(world(body));bi={data['bones'][i]['name']:np.array(data['bones'][i]['world_matrix'])[:3,3] for i in body['bone_ids']}
    names=[data['bones'][i]['name'] for i in body['bone_ids']];bt=np.array(body['triangles']).reshape(-1,3);results=[]
    for side,part,sign in [('L','005',-1),('R','004',1)]:
        foot,toe='J_Bip_'+side+'_Foot','J_Bip_'+side+'_ToeBase';pivot=bi[foot]
        use=np.array([sum(v for slot,v in zip(w['indices'],w['weights']) if names[slot] in (foot,toe))>=.35 and p[1]<=pivot[1]+.005 for p,w in zip(bp,body['weights'])])
        foot_surface=bp[bt[np.all(use[bt],axis=1)]];foot_points=bp[use]
        zmin,zmax=foot_points[:,2].min(),foot_points[:,2].max();stations=np.linspace(zmin+(zmax-zmin)*.18,zmin+(zmax-zmin)*.82,9)
        fs=sections(foot_surface,stations);fc=fs.mean(axis=1)
        shoe=next(m for m in data['garments'] if m['name']=='FIT_ACCESSORY_Shoe_'+side+'_T'+part)
        sp=np.array(world(shoe));st=np.array(triangles(shoe,sp.tolist()));original=sections(st,stations);before=float(np.sqrt(np.mean((original.mean(axis=1)-fc)**2))*1000)
        candidates=[]
        for magnitude in np.arange(4,14.001,.25):
            yaw=float(sign*magnitude)
            initial=rigid(pivot,yaw,np.zeros(3));rp=transform(sp,initial);rt=transform(st.reshape(-1,3),initial).reshape(-1,3,3)
            # Preserve the already-tested rear envelope, allowing only 0.2mm
            # numerical/shape tolerance; this is a guard, not enclosure proof.
            mandatory_back=min(0.,sp[:,2].min()-rp[:,2].min()+.0002)
            for extra_back in [0.,-.001,-.002]:
                dz=mandatory_back+extra_back
                surface=rt+np.array([0,0,dz]);ss=sections(surface,stations);dx=float(np.mean(fc-ss.mean(axis=1)))
                ss[:,0]+=dx;ss[:,1]+=dx;delta=ss.mean(axis=1)-fc
                rms=float(np.sqrt(np.mean(delta**2))*1000)
                width_margin=np.minimum(fs[:,0]-ss[:,0],ss[:,1]-fs[:,1])*1000
                penalty=float(np.mean(np.maximum(0.,-width_margin)**2))
                score=rms*rms+penalty*.1+(dz*1000)**2*.002
                matrix=rigid(pivot,yaw,np.array([dx,0,dz]));actual=transform(sp,matrix)
                candidates.append({'yaw_degrees':yaw,'translation_m':[dx,0,dz],'score':score,'centerline_rms_mm':rms,'minimum_sampled_lateral_margin_mm':float(width_margin.min()),'posterior_bbox_margin_mm':float((zmin-actual[:,2].min())*1000),'native_transform':matrix.tolist(),'shoe_sections_x_m':ss.tolist()})
        candidates.sort(key=lambda r:r['score']);best=candidates[0]
        assert abs(best['translation_m'][0])<.015 and abs(best['translation_m'][2])<.006
        assert best['centerline_rms_mm']<before*.45,(side,before,best)
        before_heading=math.degrees(math.atan(float(np.polyfit(stations,original.mean(axis=1),1)[0])))
        target_heading=math.degrees(math.atan(float(np.polyfit(stations,fc,1)[0])))
        after_heading=math.degrees(math.atan(float(np.polyfit(stations,np.mean(best['shoe_sections_x_m'],axis=1),1)[0])))
        results.append({'side':side,'main_mesh':shoe['name'],'foot_pivot_m':pivot.tolist(),'stations_z_m':stations.tolist(),'foot_sections_x_m':fs.tolist(),'original_shoe_sections_x_m':original.tolist(),'before_centerline_rms_mm':before,'foot_centerline_heading_degrees':target_heading,'before_shoe_centerline_heading_degrees':before_heading,'after_shoe_centerline_heading_degrees':after_heading,'chosen':best,'top_candidates':candidates[:5]})
    result={'schema':'shoe-rigid-heading-plan-v1','reference':str(a.reference.resolve()),'reference_sha256':hashlib.sha256(a.reference.read_bytes()).hexdigest(),'rows':results,'scope':'Actual captured Body-foot and main-shoe silhouette centerlines at nine shared transverse sections. Bounded yaw and lateral translation; rear envelope guarded. No scale, shoe remodeling, body mask or pose changes. Cross-sections and bbox guards do not certify closed shoe coverage.'}
    with a.out.open('x',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps([{k:r[k] for k in ['side','before_centerline_rms_mm','foot_centerline_heading_degrees','before_shoe_centerline_heading_degrees','after_shoe_centerline_heading_degrees']}|{'yaw':r['chosen']['yaw_degrees'],'translation_mm':[x*1000 for x in r['chosen']['translation_m']],'rms_mm':r['chosen']['centerline_rms_mm']} for r in results]),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
