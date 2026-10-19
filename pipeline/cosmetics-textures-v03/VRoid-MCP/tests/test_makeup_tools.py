"""Tool protocol regressions: fresh model/image guards precede native writes."""
import asyncio,base64,copy,hashlib
import pytest
from vroid_mcp.makeup_tools import register_makeup_tools
from vroid_mcp.texture_mapping import png_rgba
from vroid_mcp.bounded_paint import decode_rgba_png

class NativeFixture:
    def __init__(self,part='Cheek'):
        self.part=part;self.image={'transferable_id':'owned','image_id':'image'};self.region={'region_id':'region','native_type':'Native.'+part,'part':part}
        rgba=bytearray(32*32*4)
        for y in range(12,20):
            for x in range(10,18):rgba[(y*32+x)*4:(y*32+x+1)*4]=bytes([200,40,80,40])
        self.source=png_rgba(32,32,rgba);self.active_type=self.region['native_type'];self.writes=[]
    async def parameter_call(self,operation,args,mutating=False):
        assert args['expected_model']=='model'
        if operation=='list_texture_regions':return {'regions':[self.region]}
        if operation=='inspect_texture_canvas':return {'current_group_type':self.active_type,'images':[{'image':self.image}]}
        if operation=='export_texture_layer':return {'layer':{'image':self.image},'base64':base64.b64encode(self.source).decode()}
        if operation=='export_texture_surface':return {'meshes':[{'image':self.image,'uv0':[[.2,.2],[.8,.2],[.2,.8]],'submeshes':[{'triangles':[0,1,2]}]}]}
        if operation=='import_texture_layer':
            assert mutating;self.writes.append(args);return {'history_command_count':3,'layer':{'layer_id':'new'}}
        raise AssertionError(operation)

def register(tmp_path,part='Cheek'):
    (tmp_path/'saves').mkdir();tools={};runtime=NativeFixture(part)
    def decorator(**kwargs):
        def add(function):tools[function.__name__]=function;return function
        return add
    register_makeup_tools(decorator,runtime,tmp_path,None,None);return runtime,tools

def brush():return [{'points':[[.45,.5]],'radius':.12,'color':[.9,.2,.3,.5]}]

def test_preview_and_new_layer_paint_share_identical_pixels_without_touching_source(tmp_path):
    async def scenario():
        runtime,tools=register(tmp_path);original=runtime.source
        mask=await tools['export_makeup_region_mask']('model','region','source',1,0)
        args={'expected_model':'model','mask_id':mask['mask_id'],'expected_mask_sha256':mask['manifest_sha256'],'marks':brush()}
        preview=await tools['preview_makeup_marks'](**args);assert not runtime.writes and preview['model_modified'] is False
        paint=await tools['paint_makeup_marks'](**args,layer_name='test',opacity=.7)
        assert len(runtime.writes)==1 and runtime.source==original
        assert paint['preview']['png_sha256']==preview['png_sha256']
        assert runtime.writes[0]['opacity']==.7 and paint['saved'] is False
        w,h,pixels=decode_rgba_png(base64.b64decode(runtime.writes[0]['png_base64']))
        assert (w,h)==(32,32)
        assert all(not pixels[(y*32+x)*4+3] for y in range(h) for x in range(w) if not (10<=x<18 and 12<=y<20))
    asyncio.run(scenario())

@pytest.mark.parametrize('change',['source','canvas','model','mask_hash'])
def test_stale_reference_or_address_rejected_before_any_native_write(tmp_path,change):
    async def scenario():
        runtime,tools=register(tmp_path);mask=await tools['export_makeup_region_mask']('model','region','source',1,0)
        args={'expected_model':'model','mask_id':mask['mask_id'],'expected_mask_sha256':mask['manifest_sha256'],'marks':brush()}
        args.update(layer_name='test',opacity=1.)
        if change=='source':runtime.source=png_rgba(32,32,bytes([50])*(32*32*4))
        elif change=='canvas':runtime.active_type='Other'
        elif change=='model':args['expected_model']='new-model'
        else:args['expected_mask_sha256']='0'*64
        with pytest.raises(ValueError):await tools['paint_makeup_marks'](**args)
        assert runtime.writes==[]
    asyncio.run(scenario())

def test_oral_interior_is_not_a_lipstick_region(tmp_path):
    async def scenario():
        runtime,tools=register(tmp_path,'Mouth')
        with pytest.raises(ValueError,match='oral interior'):await tools['export_makeup_region_mask']('model','region','source',1,0)
        assert runtime.writes==[]
    asyncio.run(scenario())

def test_eyelid_uses_real_uv_coverage_and_rejects_expansion(tmp_path):
    async def scenario():
        runtime,tools=register(tmp_path,'Eyelid')
        with pytest.raises(ValueError):await tools['export_makeup_region_mask']('model','region','source',1,1)
        mask=await tools['export_makeup_region_mask']('model','region','source',1,0)
        assert 'UV-triangle' in mask['mode'] and mask['uv_geometry_sha256']
        assert mask['pixels']!=64 and not runtime.writes
    asyncio.run(scenario())

def test_reference_change_during_render_is_caught_at_the_write_boundary(tmp_path):
    async def scenario():
        runtime,tools=register(tmp_path);original_call=runtime.parameter_call;reads=0
        async def changing_reference(operation,args,mutating=False):
            nonlocal reads
            if operation=='export_texture_layer':
                reads+=1
                if reads==3:runtime.source=png_rgba(32,32,bytes([20])*(32*32*4))
            return await original_call(operation,args,mutating)
        runtime.parameter_call=changing_reference
        mask=await tools['export_makeup_region_mask']('model','region','source',1,0)
        with pytest.raises(ValueError,match='Reference layer changed'):
            await tools['paint_makeup_marks']('model',mask['mask_id'],mask['manifest_sha256'],brush(),'test',1.)
        assert reads==3 and not runtime.writes
    asyncio.run(scenario())
