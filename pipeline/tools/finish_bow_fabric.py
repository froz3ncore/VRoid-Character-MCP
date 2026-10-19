"""Bake UV-driven cloth folds with Blender, then adhere four floating trim patches."""
import bpy,json,math
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path('D:/vroidmcp');OUT=ROOT/'projects/whale-maid/target-fit-v03'

def finish():
    assert Path(bpy.data.filepath)==OUT/'whale_maid_target_fit_v03.blend'
    result_path=OUT/'fabric-and-trim.json'
    if result_path.exists():raise FileExistsError('Already finished; inspect before repeating edits')
    scene=bpy.context.scene;rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1
    mat=bpy.data.materials['WM_WhiteBow_Satin'];nodes=mat.node_tree.nodes;links=mat.node_tree.links
    selected=list(bpy.context.selected_objects);active=bpy.context.view_layer.objects.active;engine=scene.render.engine
    poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones};enabled=sb.enable_animation
    temp=None;mesh=None;temporary_material=None
    try:
        sb.enable_animation=False
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.view_layer.update()
        temporary_material=bpy.data.materials.new('TEMP_WhiteClothBake');temporary_material.use_nodes=True
        n=temporary_material.node_tree.nodes;n.clear();l=temporary_material.node_tree.links
        uv=n.new('ShaderNodeTexCoord');sep=n.new('ShaderNodeSeparateXYZ');l.new(uv.outputs['UV'],sep.inputs[0])
        mul=n.new('ShaderNodeMath');mul.operation='MULTIPLY';mul.inputs[1].default_value=math.pi*6;l.new(sep.outputs['Y'],mul.inputs[0])
        cosine=n.new('ShaderNodeMath');cosine.operation='COSINE';l.new(mul.outputs[0],cosine.inputs[0])
        amplitude=n.new('ShaderNodeMath');amplitude.operation='MULTIPLY';amplitude.inputs[1].default_value=.12;l.new(cosine.outputs[0],amplitude.inputs[0])
        base=n.new('ShaderNodeMath');base.operation='ADD';base.inputs[1].default_value=.72;l.new(amplitude.outputs[0],base.inputs[0])
        emit=n.new('ShaderNodeEmission');l.new(base.outputs[0],emit.inputs['Color'])
        output=n.new('ShaderNodeOutputMaterial');l.new(emit.outputs[0],output.inputs['Surface'])
        image=bpy.data.images.new('WM_WhiteBow_FoldTexture',width=512,height=512,alpha=False)
        image.colorspace_settings.name='sRGB';target=n.new('ShaderNodeTexImage');target.image=image;n.active=target
        mesh=bpy.data.meshes.new('TEMP_ClothBakePlane');mesh.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[],[(0,1,2,3)])
        uv_layer=mesh.uv_layers.new(name='UVMap')
        for loop in mesh.loops:uv_layer.data[loop.index].uv=[(0,0),(1,0),(1,1),(0,1)][loop.vertex_index]
        temp=bpy.data.objects.new('TEMP_ClothBakePlane',mesh);scene.collection.objects.link(temp);mesh.materials.append(temporary_material)
        for o in bpy.context.selected_objects:o.select_set(False)
        temp.select_set(True);bpy.context.view_layer.objects.active=temp
        try:scene.render.engine='CYCLES'
        except TypeError as error:raise RuntimeError('Cycles bake unavailable: '+str(error))
        scene.cycles.samples=1;scene.render.bake.use_clear=True;scene.render.bake.margin=0
        bpy.ops.object.bake(type='EMIT')
        image.filepath_raw=str(OUT/'white_bow_fold_texture.png');image.file_format='PNG';image.save();image.pack()
        principled=next(n for n in nodes if n.type=='BSDF_PRINCIPLED');texture=nodes.new('ShaderNodeTexImage');texture.image=image
        links.new(texture.outputs['Color'],principled.inputs['Base Color'])
        main=next(o for o in bpy.data.collections['FITTED_服装工作副本'].objects if o.get('fit_source_id')==1)
        points=[main.matrix_world@v.co for v in main.data.vertices];bvh=BVHTree.FromPolygons(points,[tuple(p.vertices) for p in main.data.polygons])
        corrections=[]
        for o in bpy.data.collections['FITTED_服装工作副本'].objects:
            if o.get('fit_source_id') not in {128,130,131,139}:continue
            inv=o.matrix_world.inverted();moved=0;maximum=0.
            for v in o.data.vertices:
                p=o.matrix_world@v.co;q,n,_,distance=bvh.find_nearest(p)
                if distance>.024:continue
                if (p-q).dot(n)<0:n=-n
                new=q+n*.0025;maximum=max(maximum,(new-p).length);v.co=inv@new;moved+=1
            o.data.update();corrections.append({'name':o.name,'vertices_adjusted':moved,'maximum_move_m':maximum})
        result={'texture':str(OUT/'white_bow_fold_texture.png'),'method':'UV procedural emission bake in Blender; source textures unmodified',
            'trim_patches':corrections,'scope':'Four small floating trim patches attached to skirt surface; larger lace silhouettes preserved'}
        result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(result,ensure_ascii=False))
    finally:
        scene.render.engine=engine
        if temp:bpy.data.objects.remove(temp,do_unlink=True)
        if mesh and mesh.users==0:bpy.data.meshes.remove(mesh)
        if temporary_material and temporary_material.users==0:bpy.data.materials.remove(temporary_material)
        for o in bpy.context.selected_objects:o.select_set(False)
        for o in selected:o.select_set(True)
        bpy.context.view_layer.objects.active=active
        for p in rig.pose.bones:p.matrix_basis=poses[p.name]
        sb.enable_animation=enabled;bpy.context.view_layer.update()
    old=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath,compress=True,relative_remap=False)
    finally:bpy.context.preferences.filepaths.save_version=old
