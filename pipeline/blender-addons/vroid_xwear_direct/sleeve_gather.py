"""Reversible upper-sleeve opening gathering, callable through Blender MCP.

Only existing sleeve vertices and their weights change. No lining panels, new
meshes, topology changes, texture edits, body edits or shape keys are introduced.
"""
import bpy,json,hashlib,math
from collections import defaultdict
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform
BASE='vroid_sleeve_gather_baseline_v1';LAST='vroid_sleeve_gather_last_hash';PARAMS='vroid_sleeve_gather_parameters'

def state(obj):
    return {'positions':[list(v.co) for v in obj.data.vertices],
        'weights':[{obj.vertex_groups[g.group].name:g.weight for g in v.groups} for v in obj.data.vertices],
        'groups':[g.name for g in obj.vertex_groups],
        'polygons':[list(p.vertices) for p in obj.data.polygons],
        'uv':[[list(v.uv) for v in layer.data] for layer in obj.data.uv_layers]}

def fingerprint(obj):return hashlib.sha256(json.dumps(state(obj),sort_keys=True).encode()).hexdigest()

def inspect_cuff(mesh_name,rig_name,start_bone,end_bone):
    obj=bpy.data.objects[mesh_name];rig=bpy.data.objects[rig_name]
    if obj.type!='MESH' or rig.type!='ARMATURE':raise ValueError('Expected sleeve mesh and target armature')
    axis=rig.data.bones[end_bone].head_local-rig.data.bones[start_bone].head_local
    if axis.length<.05:raise ValueError('Arm axis too short')
    return {'mesh':mesh_name,'rig':rig_name,'fingerprint':fingerprint(obj),'vertices':len(obj.data.vertices),
        'arm_length_m':axis.length,'parameters':json.loads(obj[PARAMS]) if PARAMS in obj else None,
        'baseline_available':BASE in obj,'writes_scene':False}

def _set_geometry(obj,positions,weights,group_order=None):
    for name in (group_order or []):
        if not obj.vertex_groups.get(name):obj.vertex_groups.new(name=name)
    for vertex,point,skin in zip(obj.data.vertices,positions,weights):
        vertex.co=point
        for group in obj.vertex_groups:group.remove([vertex.index])
        for name,weight in skin.items():
            group=obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
            if weight>0:group.add([vertex.index],weight,'REPLACE')
    if group_order is not None:
        for group in list(obj.vertex_groups):
            if group.name not in group_order:obj.vertex_groups.remove(group)
    obj.data.update()

def gather_cuff(mesh_name,rig_name,body_name,start_bone,end_bone,expected_fingerprint,
                tightness=.95,opening_fraction=.33,transition_fraction=.14,clearance_m=.003,max_move_m=.04):
    info=inspect_cuff(mesh_name,rig_name,start_bone,end_bone)
    if info['fingerprint']!=expected_fingerprint:raise ValueError('Sleeve changed; inspect before writing')
    for name,value,lo,hi in [('tightness',tightness,0,1),('opening_fraction',opening_fraction,0,1),
        ('transition_fraction',transition_fraction,.01,.5),('clearance_m',clearance_m,.001,.015),('max_move_m',max_move_m,.001,.05)]:
        if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('Invalid '+name)
    obj=bpy.data.objects[mesh_name];body=bpy.data.objects[body_name];rig=bpy.data.objects[rig_name]
    if obj.data.users!=1 or obj.data.shape_keys:raise ValueError('Use a unique sleeve mesh without shape keys')
    if obj.matrix_world!=rig.matrix_world or body.matrix_world!=rig.matrix_world:raise ValueError('Sleeve/body/rig must share reference space')
    if any(abs(x-1)>1e-6 for x in rig.matrix_world.to_scale()) or abs(bpy.context.scene.unit_settings.scale_length-1)>1e-6:
        raise ValueError('Gathering currently requires unit rig scale and metre scene units')
    if len(obj.modifiers)!=1 or obj.modifiers[0].type!='ARMATURE' or obj.modifiers[0].object!=rig:raise ValueError('Unexpected sleeve modifier stack')
    if LAST in obj and obj[LAST]!=info['fingerprint']:raise ValueError('Sleeve edited after gathering; refusing stale baseline')
    current=state(obj);baseline=json.loads(obj[BASE]) if BASE in obj else current
    if current['polygons']!=baseline['polygons'] or current['uv']!=baseline['uv']:raise ValueError('Sleeve topology or UV changed')
    start=rig.data.bones[start_bone].head_local.copy();axis=rig.data.bones[end_bone].head_local-start
    length=axis.length;axis.normalize()
    points=[v.co.copy() for v in body.data.vertices];faces=[tuple(p.vertices) for p in body.data.polygons]
    tree=BVHTree.FromPolygons(points,faces,all_triangles=True)
    body_weights=[{body.vertex_groups[g.group].name:g.weight for g in v.groups} for v in body.data.vertices]
    positions=[];weights=[];affected=[];radii=[];maximum=0.
    for i,(raw,prior) in enumerate(zip(baseline['positions'],baseline['weights'])):
        point=Vector(raw);t=(point-start).dot(axis)/length
        if t>=opening_fraction+transition_fraction or tightness==0:
            positions.append(raw);weights.append(prior);continue
        q=max(0,min(1,(t-opening_fraction)/transition_fraction));influence=tightness*(1-q*q*(3-2*q))
        centre=start+axis*t*length;radial=point-centre;radius=radial.length
        if radius<1e-6:raise ValueError('Sleeve vertex lies on arm axis')
        direction=radial.normalized();hit,normal,index,distance=tree.ray_cast(centre,direction,.12)
        if hit is None or not .008<=distance<=.09:raise ValueError('Cannot identify local arm surface')
        target_radius=min(radius,distance+clearance_m)
        target=centre+direction*(radius+(target_radius-radius)*influence)
        delta=(target-point).length
        if delta>max_move_m+1e-7:raise ValueError('Gather exceeds configured movement bound')
        a,b,c=faces[index]
        bary=barycentric_transform(hit,points[a],points[b],points[c],Vector((1,0,0)),Vector((0,1,0)),Vector((0,0,1)))
        fractions=[max(0,x) for x in bary];total=sum(fractions)
        if total<1e-6:raise ValueError('Invalid arm triangle interpolation')
        skin=defaultdict(float)
        for name,weight in prior.items():skin[name]+=weight*(1-influence)
        for vertex,fraction in zip((a,b,c),fractions):
            for name,weight in body_weights[vertex].items():skin[name]+=weight*influence*fraction/total
        keep=sorted(((name,w) for name,w in skin.items() if w>1e-7),key=lambda x:-x[1])[:4];total=sum(w for _,w in keep)
        if not total or any(name not in rig.data.bones for name,_ in keep):raise ValueError('Invalid gathered sleeve skin weights')
        positions.append(list(target));weights.append({name:w/total for name,w in keep})
        affected.append(i);maximum=max(maximum,delta);radii.append({'before':radius,'after':(target-centre).length,'arm':distance})
    parameters={'tightness':tightness,'opening_fraction':opening_fraction,'transition_fraction':transition_fraction,
        'clearance_m':clearance_m,'max_move_m':max_move_m,'start_bone':start_bone,'end_bone':end_bone}
    previous={name:obj.get(name) for name in (BASE,LAST,PARAMS)}
    try:
        _set_geometry(obj,positions,weights,baseline['groups'] if tightness==0 else None)
        actual=state(obj)
        if actual['uv']!=baseline['uv'] or actual['polygons']!=baseline['polygons'] or len(actual['positions'])!=len(baseline['positions']):
            raise RuntimeError('Sleeve topology or UV changed during gathering')
        obj[BASE]=json.dumps(baseline,separators=(',',':'));obj[PARAMS]=json.dumps(parameters,separators=(',',':'))
        obj[LAST]=fingerprint(obj)
    except Exception:
        _set_geometry(obj,current['positions'],current['weights'],current['groups'])
        for name,value in previous.items():
            if value is None:
                if name in obj:del obj[name]
            else:obj[name]=value
        raise
    return {'changed':obj[LAST]!=info['fingerprint'],'mesh':mesh_name,'affected_vertices':len(affected),
        'max_move_m':maximum,'fingerprint':obj[LAST],'parameters':parameters,'vertex_count':len(positions),'vertex_count_unchanged':True,
        'topology_uv_preserved':True,'radial_before_mean_m':sum(r['before'] for r in radii)/len(radii) if radii else None,
        'radial_after_mean_m':sum(r['after'] for r in radii)/len(radii) if radii else None,
        'native_acceptance':False}

class VROIDMCP_OT_gather_sleeve(bpy.types.Operator):
    bl_idname='vroid_mcp.gather_sleeve_cuff';bl_label='Gather sleeve opening'
    mesh_name:bpy.props.StringProperty();rig_name:bpy.props.StringProperty();body_name:bpy.props.StringProperty()
    start_bone:bpy.props.StringProperty();end_bone:bpy.props.StringProperty();expected_fingerprint:bpy.props.StringProperty()
    tightness:bpy.props.FloatProperty(default=.95,min=0,max=1)
    opening_fraction:bpy.props.FloatProperty(default=.33,min=0,max=1)
    transition_fraction:bpy.props.FloatProperty(default=.14,min=.01,max=.5)
    clearance_m:bpy.props.FloatProperty(default=.003,min=.001,max=.015)
    def execute(self,context):
        try:print(json.dumps(gather_cuff(self.mesh_name,self.rig_name,self.body_name,self.start_bone,self.end_bone,self.expected_fingerprint,self.tightness,self.opening_fraction,self.transition_fraction,self.clearance_m),ensure_ascii=False))
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

def register():bpy.utils.register_class(VROIDMCP_OT_gather_sleeve)
def unregister():bpy.utils.unregister_class(VROIDMCP_OT_gather_sleeve)
