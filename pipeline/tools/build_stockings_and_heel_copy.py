"""Independent original-shoe adjustment and neutral stocking surface copy.

The stocking geometry, UVs and weights come from an actual native high-heel
Body capture, not a generated leg shape. Native fit must be accepted separately.
"""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)));CI=C.inverted()
SHA='4f26daa5e66b82ac44e2933ae5a84ee4ca26065dd5f773b1fccc3cc9f5879fe2'

def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)

def main(a):
    source=Path(bpy.data.filepath).resolve();assert not bpy.data.is_dirty and digest(source)==SHA
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists()
    reference=ROOT/'projects/whale-maid/accessory-refinement-v02/native-shoe-review-v12b/shoes-raw-reference.json'
    data=json.loads(reference.read_text(encoding='utf8'));assert data['pose_source']=='native_edit'
    body=next(m for m in data['base_meshes'] if m['name']=='Body');assert len(body['positions'])==6743
    mask_path=ROOT/'projects/whale-maid/accessory-refinement-v02/tripo-shoe-rigid-v12/arch-visible-low-occlusion-plan.json'
    mask=json.loads(mask_path.read_text(encoding='utf8'));hidden=set(mask['hidden_vertices']);assert len(hidden)==22
    inspection=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/stocking-material-inspection-v01/inspection.json').read_text(encoding='utf8'))
    assert digest(inspection['image'])==inspection['image_sha256']
    scope=load('stocking_scope',ROOT/'tools/verify_rear_mirror_sources.py');before=scope.read()
    objects_before={o.name:[list(r) for r in o.matrix_world] for o in bpy.data.objects}
    collection=bpy.data.collections['FITTED_服装工作副本'];rig=bpy.data.objects['WM_TargetVRoidRig_v01']
    shoes=[o for o in collection.all_objects if o.type=='MESH' and o.name.startswith('FIT_ACCESSORY_Shoe_')];assert len(shoes)==8
    delta=Vector((0,0,-.004))
    for obj in shoes:
        matrix=C@obj.matrix_world;inverse=matrix.inverted()
        for v in obj.data.vertices:v.co=inverse@(matrix@v.co+delta)
        obj.data.update()
    image=bpy.data.images.load(inspection['image'],check_existing=False);image.name='White tights original native composite v13';image.pack()
    material=bpy.data.materials.new('WM_WhiteStocking_NeutralShade_v13');material.use_nodes=True
    bsdf=next(n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED');bsdf.inputs['Roughness'].default_value=.7
    texture=material.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image
    material.node_tree.links.new(texture.outputs['Color'],bsdf.inputs['Base Color'])
    material['vroid_mcp_shade_color']=[.82,.85,.90,1.]
    wm=Matrix(body['world_matrix']);normal_matrix=wm.to_3x3().inverted().transposed()
    points=[wm@Vector(p) for p in body['positions']];normals=[(normal_matrix@Vector(n)).normalized() for n in body['normals']]
    names=[[data['bones'][body['bone_ids'][slot]]['name'] for slot in w['indices']] for w in body['weights']]
    rows=[]
    for side in ['L','R']:
        def eligible(i):
            mass=sum(w for n,w in zip(names[i],body['weights'][i]['weights']) if n.startswith('J_Bip_'+side+'_') and any(s in n for s in ['UpperLeg','LowerLeg','Foot','ToeBase']))
            return i not in hidden and mass>=.5 and points[i].y<.79
        faces=[body['triangles'][j:j+3] for j in range(0,len(body['triangles']),3) if all(eligible(i) for i in body['triangles'][j:j+3])]
        indices=sorted({i for face in faces for i in face});mapping={i:j for j,i in enumerate(indices)}
        vertices=[CI@(points[i]+normals[i]*.00035) for i in indices];polygons=[]
        for face in faces:
            ids=[mapping[i] for i in face];p=[vertices[i] for i in ids]
            expected=CI.to_3x3()@sum((normals[i] for i in face),Vector())
            if (p[1]-p[0]).cross(p[2]-p[0]).dot(expected)<0:ids.reverse()
            polygons.append(ids)
        mesh=bpy.data.meshes.new('Actual native high heel stocking surface '+side);mesh.from_pydata(vertices,[],polygons);mesh.update()
        mesh.materials.append(material);uv=mesh.uv_layers.new(name='NativeBodyUV')
        for loop in mesh.loops:uv.data[loop.index].uv=body['uv0'][indices[loop.vertex_index]]
        for face in mesh.polygons:face.use_smooth=True
        mesh.normals_split_custom_set_from_vertices([CI.to_3x3()@normals[i] for i in indices])
        obj=bpy.data.objects.new('FIT_NEW_WhiteStocking_'+side,mesh);collection.objects.link(obj)
        modifier=obj.modifiers.new('Actual native skin weights','ARMATURE');modifier.object=rig
        groups={}
        for vertex,original in enumerate(indices):
            w=body['weights'][original]
            for name,weight in zip(names[original],w['weights']):
                if weight<=1e-7:continue
                assert name in rig.data.bones,name
                if name not in groups:groups[name]=obj.vertex_groups.new(name=name)
                groups[name].add([vertex],weight,'REPLACE')
        mesh.calc_loop_triangles();rows.append({'mesh':obj.name,'original_body_indices':indices,'vertices':len(indices),'triangles':len(mesh.loop_triangles),'offset_m':.00035,'bones':sorted(groups)})
    after=scope.read();shoe_names={o.name for o in shoes};new_names={r['mesh'] for r in rows}
    for key in before:
        if key in ('meshes','weights'):
            assert set(after[key])==set(before[key])|new_names
            for name,value in before[key].items():
                if key=='meshes' and name in shoe_names:
                    assert {k:v for k,v in value.items() if k!='co'}=={k:v for k,v in after[key][name].items() if k!='co'}
                    matrix=C@bpy.data.objects[name].matrix_world
                    assert max((matrix@Vector(q)-matrix@Vector(p)-delta).length for p,q in zip(value['co'],after[key][name]['co']))<2e-7
                else:assert after[key][name]==value,(key,name)
        elif key=='images':
            assert all(after[key][n]==v for n,v in before[key].items()) and set(after[key])-set(before[key])=={image.name}
        else:assert after[key]==before[key],key
    assert all([list(r) for r in bpy.data.objects[n].matrix_world]==matrix for n,matrix in objects_before.items())
    out.mkdir(parents=True);stem='whale_maid_stockings_heel_v13';target=out/(stem+'.blend')
    preference=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=preference
    bpy.ops.wm.open_mainfile(filepath=str(target));assert scope.read()==after
    rig=bpy.data.objects['WM_TargetVRoidRig_v01']
    sb=rig.data.vrm_addon_extension.spring_bone1;enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.view_layer.update();export=load('stocking_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
        package=out/(stem+'.xwear');result=export.export_xwear(package,rig,[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'],item_name='Whale maid original shoes and neutral white stockings v13',author='Local creator',coordinate_matrix=C)
        write(package.with_suffix('.xwear.json'),result)
    finally:
        for p in rig.pose.bones:p.matrix_basis=poses[p.name]
        sb.enable_animation=enabled
    assert digest(source)==SHA
    write(out/'build.json',{'source':str(source),'source_sha256':SHA,'copy':str(target),'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),'native_reference':str(reference),'native_reference_sha256':digest(reference),'body_occlusion_plan':str(mask_path),'body_occlusion_plan_sha256':digest(mask_path),'body_texture':inspection,'stockings':rows,'additional_shoe_back_mm':4,'native_acceptance':False,'adopted':False,'scope':'8 original shoe parts translated together 4mm back; two separate white stocking surfaces copied from actual native Body, offset 0.35mm, same UV and weights. Underlying Body and face materials are not edited.'})
    print(json.dumps({'built':True,'out':str(out),'stockings':[(r['mesh'],r['vertices'],r['triangles']) for r in rows]}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
