"""Read saved target-body and accessory coordinates without editing a source."""
import bpy,json,sys,importlib.util
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
out=Path(sys.argv[sys.argv.index('--')+1])
rows=[]
for obj in bpy.data.objects:
    if obj.type!='MESH':continue
    if not obj.name.startswith(('FIT_NEW_Bow','FIT_ACCESSORY_Whale','REF_VRoid_')):continue
    points=[C@obj.matrix_world@v.co for v in obj.data.vertices]
    row={'name':obj.name,'vertices':len(points),'bounds':[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)]}
    if obj.name.startswith('REF_VRoid_'):
        row['waist_slices']=[{'height':height,'points':len(ps),'back_z':min((p.z for p in ps),default=None),'front_z':max((p.z for p in ps),default=None)} for height in (.95,.98,1.,1.02) for ps in [[p for p in points if abs(p.x)<.035 and abs(p.y-height)<.012]]]
        row['feet']=[{'side':s,'points':[list(p) for p in points if p.y<.13 and (p.x>0 if s=='P' else p.x<0)]} for s in ('P','N')]
    rows.append(row)
rig=bpy.data.objects['WM_TargetVRoidRig_v01']
bones={b.name:{'head':list(C@rig.matrix_world@b.head_local),'tail':list(C@rig.matrix_world@b.tail_local)} for b in rig.data.bones if any(k in b.name for k in ('Foot','Toes','Hips','BackRibbon'))}
out.parent.mkdir(parents=True,exist_ok=True)
with out.open('x',encoding='utf8') as f:json.dump({'source':bpy.data.filepath,'dirty':bpy.data.is_dirty,'objects':rows,'bones':bones},f,ensure_ascii=False,indent=2)
print(json.dumps({'out':str(out),'meshes':len(rows)}))
