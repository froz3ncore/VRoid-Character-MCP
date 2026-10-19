"""Bake measured gait with sole contact IK into an independent GLB copy."""
import argparse,copy,hashlib,json,math,struct
from pathlib import Path
import numpy as np
from toein_gait_math import build_gait,contact_landmarks,shoe_surface_points,frame_world

def read_glb(path):
    data=path.read_bytes();assert data[:4]==b'glTF';n=struct.unpack_from('<I',data,12)[0];document=json.loads(data[20:20+n]);offset=20+n
    size,kind=struct.unpack_from('<I4s',data,offset);assert kind==b'BIN\0';return document,bytearray(data[offset+8:offset+8+size])
def encode_glb(d,b):
    d['buffers'][0]['byteLength']=len(b);j=json.dumps(d,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8');j+=b' '*((-len(j))%4);b+=b'\0'*((-len(b))%4)
    return struct.pack('<4sII',b'glTF',2,28+len(j)+len(b))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(b),b'BIN\0')+b
def quaternion(m):
    m=m[:3,:3];u,_,v=np.linalg.svd(m);m=u@v;t=np.trace(m)
    if t>0:
        s=math.sqrt(t+1)*2;q=[(m[2,1]-m[1,2])/s,(m[0,2]-m[2,0])/s,(m[1,0]-m[0,1])/s,s/4]
    else:
        i=int(np.argmax(np.diag(m)));j=(i+1)%3;k=(i+2)%3;s=math.sqrt(1+m[i,i]-m[j,j]-m[k,k])*2;q=[0.,0.,0.,0.];q[i]=s/4;q[j]=(m[j,i]+m[i,j])/s;q[k]=(m[k,i]+m[i,k])/s;q[3]=(m[k,j]-m[j,k])/s
    q=np.array(q);return q/np.linalg.norm(q)
def node_matrix(node):
    if 'matrix' in node:return np.array(node['matrix']).reshape(4,4).T
    x,y,z,w=node.get('rotation',[0,0,0,1]);m=np.eye(4);m[:3,:3]=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])@np.diag(node.get('scale',[1,1,1]));m[:3,3]=node.get('translation',[0,0,0]);return m
def rig_keys(frame):
    counts={};ids={}
    for n in frame['rig']['nodes']:
        i=counts.get(n['name'],0);counts[n['name']]=i+1;ids[n['id']]=n['name'] if i==0 else n['name']+'#'+str(i)
    return ids
def prefix(name):return name.split('__')[0]
def map_nodes(document,frames):
    first=frames[0];nodes={n['id']:n for n in first['rig']['nodes']};keys=rig_keys(first);mapping={};aliases=[]
    for r in first['rig']['renderers']:
        candidates=[n for n in document['nodes'] if 'skin' in n and (n.get('name')==r['name'] or prefix(n.get('name',''))==prefix(r['name']))]
        if not candidates:continue
        if len(candidates)!=1:raise ValueError('Ambiguous exported renderer '+r['name'])
        joints=document['skins'][candidates[0]['skin']]['joints'];by_name={}
        for j in joints:by_name.setdefault(document['nodes'][j].get('name',''),[]).append(j)
        for native_id in r['bone_ids']:
            native=nodes[native_id];choices=by_name.get(native['name'],[])
            if not choices:continue
            if len(choices)>1:raise ValueError('Ambiguous joint in renderer skin '+native['name'])
            index=choices[0];key=keys[native_id]
            if index in mapping and mapping[index]!=key:
                error=max(float(np.max(np.abs(frame_world(f)[mapping[index]]-frame_world(f)[key]))) for f in frames)
                if error>2e-5:raise ValueError('Conflicting animated skin joint '+native['name']+' '+str(error))
                aliases.append(dict(node=index,native_keys=[mapping[index],key],maximum_matrix_difference=error))
            else:mapping[index]=key
    for side in 'LR':
        for part in ['UpperLeg','LowerLeg','Foot','ToeBase']:
            wanted='J_Bip_'+side+'_'+part;assert len([i for i,k in mapping.items() if k==wanted])==1,wanted
    return mapping,aliases
def main(a):
    out=a.out.resolve();out.mkdir(exist_ok=False);source,original_bin=read_glb(a.source);doc=copy.deepcopy(source);binary=bytearray(original_bin)
    walk=json.loads((a.rig/'WALK00_F.json').read_text(encoding='utf8'));frames=walk['frames'];reference=json.loads(a.reference.read_text(encoding='utf8'))
    posed,root,diagnostics,profile=build_gait(frames,contact_landmarks(reference),a.foot_degrees,a.upper_degrees,shoe_surface_points(reference));mapping,aliases=map_nodes(doc,frames)
    assert min(v['shoe_floor_clearance_mm'] for row in diagnostics for v in row['sides'].values())>=1.49
    profile['keyframe_minimum_shoe_floor_clearance_mm']=1.5
    parent={child:i for i,node in enumerate(doc['nodes']) for child in node.get('children',[])};rest={}
    def world(i):
        if i not in rest:rest[i]=(world(parent[i]) if i in parent else np.eye(4))@node_matrix(doc['nodes'][i])
        return rest[i]
    for i in range(len(doc['nodes'])):world(i)
    mirror=np.diag([-1,1,1,1]);root_index=next(i for i,n in enumerate(doc['nodes']) if n.get('name')=='Root');source_world=[frame_world(f) for f in frames]
    def accessor(values,kind):
        array=np.asarray(values,dtype='<f4');assert np.isfinite(array).all()
        while len(binary)%4:binary.append(0)
        offset=len(binary);raw=array.tobytes();binary.extend(raw);view=len(doc['bufferViews']);doc['bufferViews'].append(dict(buffer=0,byteOffset=offset,byteLength=len(raw)))
        index=len(doc['accessors']);entry=dict(bufferView=view,componentType=5126,count=len(array),type=kind)
        if kind=='SCALAR':entry.update(min=[float(array.min())],max=[float(array.max())])
        doc['accessors'].append(entry);return index
    animations=[];verification=[]
    def bake(name,native_frames,root_motion=None):
        time_index=accessor([f['seconds'] for f in frames],'SCALAR');channels=[];samplers=[];locals_by_node={i:[] for i in mapping}
        if root_motion is not None:locals_by_node.setdefault(root_index,[])
        for fi,native in enumerate(native_frames):
            animated={i:mirror@native[key]@mirror for i,key in mapping.items()}
            if root_motion is not None:
                for m in animated.values():m[:3,3]+=np.array([-root_motion[fi,0],root_motion[fi,1],root_motion[fi,2]])
                animated[root_index]=rest[root_index].copy();animated[root_index][:3,3]+=np.array([-root_motion[fi,0],root_motion[fi,1],root_motion[fi,2]])
            for i in locals_by_node:
                p=parent.get(i);pm=animated.get(p,rest[p] if p is not None else np.eye(4));locals_by_node[i].append(np.linalg.inv(pm)@animated.get(i,rest[i]))
        for i,matrices in locals_by_node.items():
            for path,kind in [('translation','VEC3'),('rotation','VEC4')]:
                values=[m[:3,3] if path=='translation' else quaternion(m) for m in matrices]
                if path=='rotation':
                    for j in range(1,len(values)):
                        if np.dot(values[j-1],values[j])<0:values[j]=-values[j]
                output=accessor(values,kind);samplers.append(dict(input=time_index,output=output,interpolation='LINEAR'));channels.append(dict(sampler=len(samplers)-1,target=dict(node=i,path=path)))
        animations.append(dict(name=name,samplers=samplers,channels=channels,extras=dict(source='Measured native gait, independent baked copy',loop=True,root_motion=root_motion is not None)))
        verification.append(dict(animation=name,tracks=len(channels),frames=len(frames),duration=frames[-1]['seconds']))
    bake('Walk_Native_InPlace',source_world)
    bake('Walk_Native_RootMotion',source_world,root)
    bake('Walk_ToeIn_InPlace',posed)
    bake('Walk_ToeIn_RootMotion',posed,root)
    doc['animations']=animations;doc.setdefault('extras',{})['toe_in_gait']=profile
    path=out/'whale-maid-toein-walk-v04.glb';path.write_bytes(encode_glb(doc,binary))
    # Existing geometry, materials, textures, skins, nodes and original binary payload stay byte-for-byte/data-equal.
    reread,payload=read_glb(path)
    for key in ['meshes','materials','images','textures','skins','nodes']:assert reread[key]==source[key],key
    assert payload[:len(original_bin)]==original_bin
    assert all(v['reachable'] and v['sole_target_error_mm']<.01 for row in diagnostics for v in row['sides'].values())
    report=dict(passed=True,source=dict(path=str(a.source.resolve()),sha256=hashlib.sha256(a.source.read_bytes()).hexdigest()),artifact=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()),profile=profile,diagnostics=diagnostics,animations=verification,mapped_joints=len(mapping),native_alias_checks=aliases,source_node_map={str(i):key for i,key in mapping.items()},original_assets_preserved=True,godot_validated=False,scope='Baked full-outfit GLB copy with native and contact-aware toe-in walks. Original VRM stays unchanged. Root-motion viewer must accumulate cycle travel; in-place clip needs matching character motion.')
    (out/'build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    # Runtime expected matrices for an independent engine-side comparison.
    expected=[]
    for fi,native in enumerate(posed):expected.append(dict(seconds=frames[fi]['seconds'],bones={doc['nodes'][i]['name']:(mirror@native[key]@mirror).tolist() for i,key in mapping.items() if doc['nodes'][i]['name'] in ['J_Bip_C_Hips']+[f'J_Bip_{s}_{p}' for s in 'LR' for p in ['UpperLeg','LowerLeg','Foot','ToeBase']]}))
    (out/'expected-poses.json').write_text(json.dumps(expected),encoding='utf8');print(json.dumps(dict(passed=True,artifact=str(path),mapped_joints=len(mapping),animations=verification,travel=profile['travel_per_cycle_m'])),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--rig',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--foot-degrees',type=float,default=6);p.add_argument('--upper-degrees',type=float,default=2);main(p.parse_args())
