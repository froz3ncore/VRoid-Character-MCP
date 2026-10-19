"""Configuration-driven, bounded fitting backend callable through Blender MCP.

References are actual native snapshots. Plans never mutate a scene; applying a
plan writes a new .blend copy and restores in-memory coordinates afterwards.
The nearest-normal test is screening, not a closed-surface collision proof.
"""
import hashlib
import json
import math
from pathlib import Path
from collections import defaultdict
import bpy
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

SCHEMA = 'vroid-garment-fit-profile-v1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(obj, positions=True):
    mesh=obj.data
    data={'polygons':[list(p.vertices) for p in mesh.polygons],
          'uv':[[list(v.uv) for v in layer.data] for layer in mesh.uv_layers],
          'groups':[g.name for g in obj.vertex_groups],
          'weights':[[(g.group,g.weight) for g in v.groups] for v in mesh.vertices],
          'world':[list(r) for r in obj.matrix_world]}
    if positions:data['positions']=[list(v.co) for v in mesh.vertices]
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def write_new(path, data):
    path=Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:
        json.dump(data,stream,ensure_ascii=False,indent=2,allow_nan=False)
    return {'path':str(path),'sha256':digest(path)}


def load_profile(path):
    path=Path(path).resolve();p=json.loads(path.read_text(encoding='utf8'))
    if p.get('schema')!=SCHEMA:raise ValueError('Unknown fit profile schema')
    source=Path(p['source_blend']).resolve()
    if Path(bpy.data.filepath).resolve()!=source or bpy.data.is_dirty:
        raise ValueError('Open the exact saved source before planning or applying')
    if digest(source)!=p['source_sha256']:raise ValueError('Source file hash changed')
    names=p['meshes']
    if not names or len(set(names))!=len(names) or len(names)>128:raise ValueError('Explicit distinct mesh names required')
    rig=bpy.data.objects.get(p['rig'])
    if not rig or rig.type!='ARMATURE':raise ValueError('Target rig missing')
    rows=p['coordinate_matrix']
    if len(rows)!=4 or any(len(r)!=4 for r in rows) or not all(type(x) in (int,float) and math.isfinite(x) for r in rows for x in r):raise ValueError('Invalid coordinate matrix')
    if any(abs(rows[3][i]-(1 if i==3 else 0))>1e-7 for i in range(4)):raise ValueError('Non-affine coordinate matrix')
    coord=Matrix(rows)
    if abs(coord.to_3x3().determinant())<1e-8:raise ValueError('Coordinate matrix is singular')
    cfg=p['limits']
    for name in ('clearance_m','inside_threshold_m','max_surface_distance_m','max_displacement_m'):
        if type(cfg[name]) not in (int,float) or not math.isfinite(cfg[name]) or cfg[name]<=0:raise ValueError('Invalid fit bound: '+name)
    if cfg['max_displacement_m']>.025 or cfg['clearance_m']>.02:raise ValueError('Fit bounds exceed conservative limits')
    if type(cfg['iterations']) is not int or not 1<=cfg['iterations']<=20:raise ValueError('Invalid iteration count')
    bounds=p['source_height_range_m']
    if len(bounds)!=2 or not all(math.isfinite(x) for x in bounds) or bounds[0]>=bounds[1]:raise ValueError('Invalid source height range')
    for name in names:
        obj=bpy.data.objects.get(name)
        if not obj or obj.type!='MESH' or obj.data.users!=1:raise ValueError('Missing or shared garment mesh: '+name)
        mods=[m for m in obj.modifiers if m.type=='ARMATURE']
        if len(obj.modifiers)!=1 or len(mods)!=1 or mods[0].object!=rig:raise ValueError('Garment needs exactly the target armature modifier')
        if not obj.data.uv_layers.active or obj.data.shape_keys:raise ValueError('UV0 required; shape keys not supported')
        for v in obj.data.vertices:
            groups=[g for g in v.groups if g.weight>1e-7]
            if any(not math.isfinite(g.weight) or g.weight<0 for g in v.groups) or not groups or len(groups)>4 or abs(sum(g.weight for g in groups)-1)>1e-4:
                raise ValueError('Unnormalized or unsupported skin weights')
            if any(obj.vertex_groups[g.group].name not in rig.data.bones for g in groups):raise ValueError('Unknown skin bone')
    return p,coord,rig


def inspect_binding(profile_path):
    p,coord,rig=load_profile(profile_path)
    return {'source':p['source_blend'],'source_sha256':p['source_sha256'],'rig':rig.name,
            'meshes':[{'name':name,'vertices':len(bpy.data.objects[name].data.vertices),
                       'fingerprint':fingerprint(bpy.data.objects[name])} for name in p['meshes']],
            'references':len(p['references']),'limits':p['limits'],'writes_scene':False}


def export_map(obj,coord):
    mesh=obj.data;mesh.calc_loop_triangles();cache={};indices=[];uvs=[]
    transform=coord@obj.matrix_world;normal=transform.to_3x3().inverted().transposed()
    for tri in mesh.loop_triangles:
        if tri.area<=1e-12:continue
        loops=list(tri.loops)
        if transform.to_3x3().determinant()<0:loops.reverse()
        for i in loops:
            loop=mesh.loops[i];uv=tuple(mesh.uv_layers.active.data[i].uv)
            n=tuple((normal@mesh.corner_normals[i].vector).normalized());key=(loop.vertex_index,uv,n)
            if key not in cache:cache[key]=len(indices);indices.append(loop.vertex_index);uvs.append(uv)
    return indices,uvs


class Surface:
    def __init__(self,body):
        world=Matrix(body['world_matrix']);normal=world.to_3x3().inverted().transposed()
        self.points=[world@Vector(p) for p in body['positions']]
        self.normals=[(normal@Vector(n)).normalized() for n in body['normals']]
        self.faces=[tuple(body['triangles'][i:i+3]) for i in range(0,len(body['triangles']),3)]
        self.tree=BVHTree.FromPolygons(self.points,self.faces,all_triangles=True)

    def nearest(self,point):
        q,_,index,distance=self.tree.find_nearest(point)
        if q is None:raise ValueError('Body surface lookup failed')
        a,b,c=self.faces[index]
        normal=barycentric_transform(q,self.points[a],self.points[b],self.points[c],self.normals[a],self.normals[b],self.normals[c]).normalized()
        if normal.length<.5:raise ValueError('Ambiguous interpolated body normal')
        return normal,(point-q).dot(normal),distance


def contexts(p,coord):
    result=[]
    for reference in p['references']:
        path=Path(reference['path']).resolve()
        if digest(path)!=reference['sha256']:raise ValueError('Native reference changed')
        data=json.loads(path.read_text(encoding='utf8'))
        if data.get('schema')!='vroid-wear-reference-v1' or data.get('pose_source') not in ('native_edit','native_preview'):
            raise ValueError('Expected actual native pose reference')
        by_name={g['name']:g for g in data['garments']};surface=Surface(data['body'])
        for name in p['meshes']:
            if name not in by_name:raise ValueError('Selected garment not in native reference')
            obj=bpy.data.objects[name];g=by_name[name];mapping,uvs=export_map(obj,coord)
            if len(mapping)!=len(g['positions']):raise ValueError('Export vertex count changed')
            transform=coord@obj.matrix_world
            heights=[(transform@v.co).y for v in obj.data.vertices];lo,hi=p['source_height_range_m']
            selected={i for i,h in enumerate(heights) if lo<=h<=hi}
            if not selected:raise ValueError('No garment vertices in configured region')
            # VRoid's preview synthesizer can canonicalize upper-body rest poses.
            # Only a region whose source coordinates AND skin reconstruction match
            # the saved Blender source is eligible. Never infer a global mapping.
            source_error=max(((transform@obj.data.vertices[index].co)-Vector(raw)).length for index,raw in zip(mapping,g['source_positions']) if index in selected)
            uv_error=max(abs(a-b) for uv,raw in zip(uvs,g['uv0']) for a,b in zip(uv,raw))
            if source_error>2e-6 or uv_error>1e-6:raise ValueError(f'Native/source geometry correspondence failed: {reference["label"]}, source={source_error}, uv={uv_error}')
            native_bones={data['bones'][i]['name']:Matrix(data['bones'][i]['world_matrix'])@Matrix(bind) for i,bind in zip(g['bone_ids'],g['bindposes'])}
            if len(native_bones)!=len(g['bone_ids']):raise ValueError('Ambiguous native bone identity')
            for index,w in zip(mapping,g['weights']):
                if index not in selected:continue
                expected={obj.vertex_groups[x.group].name:x.weight for x in obj.data.vertices[index].groups if x.weight>1e-7}
                actual=defaultdict(float)
                for bone,weight in zip(w['indices'],w['weights']):
                    if weight>1e-7:actual[data['bones'][g['bone_ids'][bone]]['name']]+=weight
                if set(expected)!=set(actual) or any(abs(expected[name]-actual[name])>1e-5 for name in expected):raise ValueError('Native/source skin weight correspondence failed')
            matrices=[]
            for v in obj.data.vertices:
                matrix=Matrix(((0,0,0,0),)*4)
                for group in v.groups:
                    if group.weight>1e-7:
                        bone=obj.vertex_groups[group.group].name
                        if bone not in native_bones:raise ValueError('Native skin bone missing: '+bone)
                        matrix+=native_bones[bone]*group.weight
                matrices.append(matrix@transform)
            world=Matrix(g['world_matrix'])
            reconstruction=max((matrices[index]@obj.data.vertices[index].co-world@Vector(raw)).length for index,raw in zip(mapping,g['positions']) if index in selected)
            if reconstruction>2e-5:raise ValueError('Native skin reconstruction failed')
            triangles=[tuple(mapping[i] for i in g['triangles'][k:k+3]) for k in range(0,len(g['triangles']),3)]
            triangles=list(dict.fromkeys(tuple(sorted(t)) for t in triangles))
            edges=sorted({tuple(sorted((a,b))) for tri in triangles for a,b in zip(tri,tri[1:]+tri[:1])})
            samples=[('vertex',(i,)) for i in sorted(selected)]
            samples += [('face',t) for t in triangles if all(i in selected for i in t)]
            samples += [('edge',e) for e in edges if all(i in selected for i in e)]
            result.append({'label':reference['label'],'name':name,'surface':surface,'matrices':matrices,
                'samples':samples,'selected':selected,'source_error_m':source_error,'reconstruction_error_m':reconstruction,
                'pose_source':data['pose_source'],'clip':data.get('selected_preview_clip'),'frame':data['frame']})
    return result


def screen(context,coords,limits):
    posed=[m@v for m,v in zip(context['matrices'],coords)]
    counts=defaultdict(int);bad=[];deepest=0.
    for kind,ids in context['samples']:
        point=sum((posed[i] for i in ids),Vector())/len(ids)
        normal,signed,distance=context['surface'].nearest(point)
        if signed < -limits['inside_threshold_m'] and distance<limits['max_surface_distance_m']:
            counts[kind]+=1;deepest=max(deepest,-signed)
            bad.append({'kind':kind,'vertices':list(ids),'depth_m':-signed,'world_position':list(point)})
    return {'label':context['label'],'mesh':context['name'],'pose_source':context['pose_source'],
            'clip':context['clip'],'frame':context['frame'],'selected_vertices':len(context['selected']),
            'inside':dict(counts),'deepest_m':deepest,'worst_samples':sorted(bad,key=lambda b:-b['depth_m'])[:20],
            'source_error_m':context['source_error_m'],'skin_reconstruction_error_m':context['reconstruction_error_m']}


def plan_fit(profile_path,report_path,solve=False):
    """Read-only analysis or a bounded multi-pose plan; writes one new JSON artifact."""
    p,coord,rig=load_profile(profile_path);refs=contexts(p,coord);cfg=p['limits']
    original={name:[v.co.copy() for v in bpy.data.objects[name].data.vertices] for name in p['meshes']}
    current={name:[v.copy() for v in points] for name,points in original.items()}
    before=[screen(c,current[c['name']],cfg) for c in refs]
    # Deep intersections are outside this tool's local correction scope. Freeze
    # every involved vertex across poses instead of distorting their neighbours.
    blocked=defaultdict(set)
    for context in refs:
        points=current[context['name']];matrices=context['matrices']
        for _,ids in context['samples']:
            point=sum((matrices[i]@points[i] for i in ids),Vector())/len(ids)
            _,signed,distance=context['surface'].nearest(point)
            if signed < -cfg['max_displacement_m']*.9 and distance<cfg['max_surface_distance_m']:
                blocked[context['name']].update(ids)
    steps=[]
    if solve:
        for iteration in range(cfg['iterations']):
            projected=0
            for context in refs:
                points=current[context['name']];matrices=context['matrices'];obj=bpy.data.objects[context['name']]
                world_linear=obj.matrix_world.to_3x3();world_inverse=world_linear.inverted()
                for _,ids in context['samples']:
                    point=sum((matrices[i]@points[i] for i in ids),Vector())/len(ids)
                    normal,signed,distance=context['surface'].nearest(point)
                    if signed>=cfg['clearance_m'] or distance>=cfg['max_surface_distance_m']:continue
                    # Position-based projection in source coordinates, split over all
                    # involved vertices. Each vertex's total world delta is bounded.
                    gradients=[matrices[i].to_3x3().transposed()@normal/len(ids) if i not in blocked[context['name']] else Vector() for i in ids]
                    den=sum(g.length_squared for g in gradients)
                    if den<1e-12:continue
                    scale=(cfg['clearance_m']-signed)*.55/den
                    for i,gradient in zip(ids,gradients):
                        candidate=points[i]+gradient*scale
                        delta=world_linear@(candidate-original[context['name']][i])
                        if delta.length>cfg['max_displacement_m']:delta*=cfg['max_displacement_m']/delta.length
                        points[i]=original[context['name']][i]+world_inverse@delta
                    projected+=1
            steps.append({'iteration':iteration,'projected_constraints':projected})
            if not projected:break
    # Retain only a bounded line-search result that does not worsen any supplied
    # pose's penetration count or deepest sample. Never silently trade walking
    # regressions for a sitting improvement.
    accepted=not solve;after=before;accepted_scale=0.
    if solve:
        for alpha in (1.,.75,.5,.25,.1):
            trial={name:[a+(b-a)*alpha for a,b in zip(original[name],points)] for name,points in current.items()}
            assessed=[screen(c,trial[c['name']],cfg) for c in refs]
            safe=all(sum(a['inside'].values())<=sum(b['inside'].values()) and a['deepest_m']<=b['deepest_m']+1e-5 for a,b in zip(assessed,before))
            improves=any(sum(a['inside'].values())<sum(b['inside'].values()) for a,b in zip(assessed,before))
            if safe and improves:current=trial;after=assessed;accepted=True;accepted_scale=alpha;break
        if not accepted:current=original;after=before
    changes={};maximum=0.
    for name,points in current.items():
        obj=bpy.data.objects[name];changes[name]=[]
        for i,(a,b) in enumerate(zip(original[name],points)):
            distance=(obj.matrix_world.to_3x3()@(b-a)).length
            if distance>1e-7:changes[name].append({'vertex':i,'position':list(b)});maximum=max(maximum,distance)
    report={'schema':'vroid-garment-fit-plan-v1','profile_path':str(Path(profile_path).resolve()),
        'profile_sha256':digest(profile_path),'source_blend':p['source_blend'],'source_sha256':p['source_sha256'],
        'mode':'bounded_plan' if solve else 'analysis','before':before,'predicted_after':after,
        'quality_gate':{'accepted':accepted,'scale':accepted_scale,'blocked_deep_vertices':{name:len(ids) for name,ids in blocked.items()},
                        'reason':'No sampled pose count/depth regression' if accepted else 'No bounded solution improved counts without a pose regression'},
        'fingerprints':{name:fingerprint(bpy.data.objects[name]) for name in p['meshes']},
        'changes':changes,'max_displacement_m':maximum,'steps':steps,'writes_scene':False,
        'scope':'Nearest-normal screening in supplied native frames. Frozen captured spring transforms; reimport/motion validation required.'}
    return {**write_new(report_path,report),'mode':report['mode'],'moved_vertices':sum(map(len,changes.values())),
            'quality_gate':report['quality_gate'],
            'max_displacement_m':maximum,'before':[{k:v for k,v in r.items() if k!='worst_samples'} for r in before],
            'predicted_after':[{k:v for k,v in r.items() if k!='worst_samples'} for r in report['predicted_after']]}


def apply_fit(plan_path,destination):
    """Validate a plan in full, save a separate copy, restore the current scene."""
    plan=json.loads(Path(plan_path).read_text(encoding='utf8'));destination=Path(destination).resolve()
    if plan.get('schema')!='vroid-garment-fit-plan-v1' or plan.get('mode')!='bounded_plan':raise ValueError('Expected a bounded plan')
    if not plan.get('quality_gate',{}).get('accepted'):raise ValueError('Plan failed multi-pose quality gate')
    if destination.suffix.lower()!='.blend' or destination.exists():raise ValueError('Choose a new .blend destination')
    if digest(plan['profile_path'])!=plan['profile_sha256']:raise ValueError('Profile changed')
    p,coord,rig=load_profile(plan['profile_path'])
    if plan['source_sha256']!=p['source_sha256'] or set(plan['changes'])!=set(p['meshes']):raise ValueError('Plan source identity mismatch')
    originals={}
    for name,changes in plan['changes'].items():
        obj=bpy.data.objects[name]
        if fingerprint(obj)!=plan['fingerprints'][name]:raise ValueError('Mesh identity changed: '+name)
        seen=set();originals[name]={}
        lo,hi=p['source_height_range_m']
        for change in changes:
            i=change['vertex'];position=change['position']
            if type(i) is not int or i in seen or not 0<=i<len(obj.data.vertices):raise ValueError('Invalid plan vertex')
            if len(position)!=3 or not all(math.isfinite(x) for x in position):raise ValueError('Nonfinite plan position')
            v=obj.data.vertices[i];height=(coord@obj.matrix_world@v.co).y
            if not lo<=height<=hi:raise ValueError('Change outside selected region')
            if (obj.matrix_world.to_3x3()@(Vector(position)-v.co)).length>p['limits']['max_displacement_m']+1e-6:raise ValueError('Plan exceeds displacement bound')
            seen.add(i);originals[name][i]=v.co.copy()
    preserved={name:fingerprint(bpy.data.objects[name],False) for name in originals}
    destination.parent.mkdir(parents=True,exist_ok=True)
    old=bpy.context.preferences.filepaths.save_version
    try:
        for name,changes in plan['changes'].items():
            for change in changes:bpy.data.objects[name].data.vertices[change['vertex']].co=change['position']
            bpy.data.objects[name].data.update()
        if any(fingerprint(bpy.data.objects[name],False)!=expected for name,expected in preserved.items()):raise ValueError('Topology/UV/weights changed')
        bpy.context.preferences.filepaths.save_version=0
        result=bpy.ops.wm.save_as_mainfile(filepath=str(destination),copy=True,compress=True,relative_remap=False)
        if 'FINISHED' not in result or not destination.is_file():raise RuntimeError('Save not confirmed')
    finally:
        bpy.context.preferences.filepaths.save_version=old
        for name,points in originals.items():
            for i,point in points.items():bpy.data.objects[name].data.vertices[i].co=point
            bpy.data.objects[name].data.update()
    if digest(p['source_blend'])!=p['source_sha256']:raise RuntimeError('Source file changed')
    return {'saved':True,'path':str(destination),'sha256':digest(destination),'source_unchanged':True,
            'scene_positions_restored':True,'moved_vertices':sum(map(len,originals.values())),
            'native_acceptance':False,'plan_sha256':digest(plan_path)}


class VROIDMCP_OT_plan_fit(bpy.types.Operator):
    bl_idname='vroid_mcp.plan_garment_fit';bl_label='Plan garment fit from native poses'
    profile_path:StringProperty();report_path:StringProperty()
    def execute(self,context):
        try:print(json.dumps(plan_fit(self.profile_path,self.report_path,solve=True),ensure_ascii=False))
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}


class VROIDMCP_OT_analyze_fit(bpy.types.Operator):
    bl_idname='vroid_mcp.analyze_garment_fit';bl_label='Analyze garment fit from native poses'
    profile_path:StringProperty();report_path:StringProperty()
    def execute(self,context):
        try:print(json.dumps(plan_fit(self.profile_path,self.report_path,solve=False),ensure_ascii=False))
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}


class VROIDMCP_OT_apply_fit(bpy.types.Operator):
    bl_idname='vroid_mcp.apply_garment_fit';bl_label='Save bounded fit as a separate source'
    plan_path:StringProperty();destination:StringProperty()
    def execute(self,context):
        try:print(json.dumps(apply_fit(self.plan_path,self.destination),ensure_ascii=False))
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}


CLASSES=(VROIDMCP_OT_analyze_fit,VROIDMCP_OT_plan_fit,VROIDMCP_OT_apply_fit)
def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
