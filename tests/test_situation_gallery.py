"""Gallery failures exercise real persistence and orchestration with a native double."""
import asyncio
import base64
from copy import deepcopy
import hashlib
from pathlib import Path
import zipfile
import json

import pytest

from vroid_mcp.runtime import Runtime
from vroid_mcp.preset_catalog import PresetCatalog
from vroid_mcp.server import create_server
from vroid_mcp.capture_quality import quality_plan
from test_catalog_runtime import snapshot
from test_preset_previews import png
from situation_fixture import subject_png, optical_proof


def group(id, type, removable=True, resource=None):
    return dict(id=id,type='TransferableGroupType.N00.Level1.'+type,active=True,active_leaf=True,removable=removable,
                resource_name=resource or id,revision='1',fingerprint=id,updated_since_last_revision=False)


class Native:
    def __init__(self, lab, failure=None):
        self.runtime=Runtime(lab); self.runtime.owns_process=True
        self.runtime._call=self.call; self.runtime._settle=self.settle; self.runtime._task=self.task
        self.token='token';self.engine='engine-old';self.file_path='';self.failure=failure;self.calls=[];self.rows=snapshot()['rows'][:1]
        self.groups=[group('skin','BodySkin',False),group('base','BaseHair',False),
                     group('top','Tops'),group('under','InnerBottom'),group('hair','HairFront'),group('hat','Hat')]
        self.removed=[];self.saved=None;self.capture_count=0;self.imports=0;self.saved_groups=None

    async def settle(self,*args):return {'model_token':self.token,'engine_id':self.engine,'file_path':self.file_path}
    async def task(self,*args):return None
    async def call(self,op,args=None):
        self.calls.append((op,deepcopy(args)))
        if op=='preset_catalog_begin':return {'request_id':'catalog'}
        if op=='preset_catalog_poll':return {'completed':True,**snapshot(),'rows':self.rows}
        if op=='preset_catalog_release':return {'released':True}
        if op=='save_as':
            if self.failure=='snapshot':raise RuntimeError('snapshot failed')
            self.saved=Path(args['path'])
            self.saved_groups=deepcopy(self.groups)
            with zipfile.ZipFile(self.saved,'w') as z:z.writestr('model',b'original-model'*40)
            return {'saved':True,'model_token':self.token}
        if op=='list_groups':
            value={'model_token':self.token,'membership_complete':True,'groups':deepcopy(self.groups)}
            if args.get('situation_candidate'):
                candidate=args['situation_candidate'];row=next(r for r in self.rows if r['id']==candidate['id'])
                g=group(row['id'],'Tops',resource=row.get('resource_name',row['resource']))
                g.update(type=row.get('group_type',g['type']),revision=row.get('revision','1'))
                value['situation_definition']={'verified':True,'root':g,'members':[g],'revision_verified':True}
            if args.get('situation_root'):
                root=args['situation_root'];g=next(g for g in self.groups if g['id']==root['id'])
                value['situation_membership']={'verified':True,'root':deepcopy(g),'members':[deepcopy(g)],'revision_verified':True}
            return value
        if op=='remove_group':
            if self.failure=='strip':raise RuntimeError('strip uncertain')
            self.removed.append(args['group_id'])
            self.groups=[g for g in self.groups if g['id']!=args['group_id']]
            return {'frame':1,'expected_removed_ids':[args['group_id']]}
        if op=='list_presets':
            return {'model_token':self.token,'next_offset':None,'presets':[
                {'id':r['selectable_preset_ids'][0],'resource_name':r['resource'],'transferable_id':r['id'],
                 'owned':True} for r in self.rows]}
        if op=='apply_preset':
            row=next(r for r in self.rows if args['preset_id'] in r['selectable_preset_ids'])
            self.groups=[g for g in self.groups if g['type']!='TransferableGroupType.N00.Level1.Tops']
            self.groups.append(group(row['id'],'Tops',resource=row['resource']))
            if self.failure=='remaining':self.groups.append(group('alien','Glasses'))
            return {'frame':2}
        if op=='preset_state':return {'model_token':self.token,'selected':True,'active_groups':deepcopy(self.groups)}
        if op=='screenshot':
            self.capture_count+=1
            if self.failure=='image':raise ValueError('invalid image')
            if self.failure=='model-change':self.token='foreign'
            if self.failure=='snapshot-substitution':
                saved=next((self.runtime.lab/'saves').glob('situation-*.vroid'))
                with zipfile.ZipFile(saved,'w') as z:z.writestr('model',b'substituted-valid-archive'*40)
            return {'model_token':self.token,'base64':base64.b64encode(subject_png()).decode(),
                    'width':512,'height':512,'quality':{**quality_plan(512,'balanced'),'msaa_samples':4},
                    'provenance':'clean_fixed_camera_render',
                    'framing':optical_proof(args['situation_framing'])}
        if op=='replace_with_file':
            if self.failure=='restore':raise RuntimeError('restore uncertain')
            self.token='fresh';self.imports+=1;self.engine='engine-restored-'+str(self.imports);self.file_path=args['path']
            self.groups=deepcopy(self.saved_groups)
            return {'task_id':'restoration'}
        raise AssertionError(op)


def run(native,**kwargs):
    async def build():return await asyncio.wait_for(native.runtime.build_preset_thumbnails(
        'token','Clothing/Tops',disposable_model=True,**kwargs),3)
    return asyncio.run(build())


def test_gallery_is_implemented():
    assert callable(getattr(Runtime,'build_preset_thumbnails',None)), 'missing isolated gallery orchestration'


@pytest.mark.parametrize('mode,ack',[('attached',True),('copy',False)])
def test_gallery_rejects_before_initialization_or_attached_receipts(tmp_path,monkeypatch,mode,ack):
    import vroid_mcp.server as module
    original=Runtime.__init__
    def init(self,*a,**k):original(self,*a,**k);self.mode=mode
    def forbidden(*args,**kwargs):raise AssertionError('must reject before startup')
    monkeypatch.setattr(Runtime,'__init__',init);monkeypatch.setattr(Runtime,'start',forbidden)
    server=module.create_server(tmp_path,'F00')
    async def check():
        tool=server._tool_manager.get_tool('build_preset_thumbnails')
        assert tool is not None
        with pytest.raises(ValueError,match='DISPOSABLE|OWNED_COPY'):
            await tool.fn(expected_model='token',category='Clothing/Tops',disposable_model=ack)
    asyncio.run(check())


def test_gallery_saves_strips_verifies_frames_publishes_and_restores(tmp_path):
    n=Native(tmp_path);result=run(n)
    assert result['restore']['state']=='restored' and result['model_token']=='fresh'
    assert result['processed']==1 and not result['errors']
    assert set(n.removed)=={'under','hair','hat'}
    ops=[op for op,args in n.calls];assert ops.index('save_as')<ops.index('remove_group')
    s=PresetCatalog(tmp_path/'preset_cache');metadata,data=s.resolve_image(n.rows[0]['resource'])
    assert metadata['kind']=='situation' and metadata['verified'] is True
    assert metadata['tested']['resource']==n.rows[0]['resource'] and metadata['tested']['revision']=='1'
    assert metadata['framing']['requested_profile']['top']==.12
    assert metadata['sha256']==hashlib.sha256(data).hexdigest()
    assert {g['id'] for g in metadata['retained_slots']}=={'skin','base','canon-a'}
    assert metadata['mannequin']=='current anatomy with verified removable slots stripped'
    assert metadata['build']=='a'*64 and metadata['captured_at']


@pytest.mark.parametrize('failure,state,published',[
    ('snapshot','not-created',False),('strip','skipped-uncertain',False),
    ('remaining','restored',False),('image','restored',False),('restore','failed',True),
    ('model-change','skipped-model-changed',False)])
def test_gallery_failure_evidence_and_safe_restoration(tmp_path,failure,state,published):
    n=Native(tmp_path,failure);result=run(n)
    assert result['restore']['state']==state and result['errors']
    assert bool(result['processed']) is published
    if state in ('skipped-uncertain','skipped-model-changed','snapshot-changed','not-created'):
        assert not any(op=='replace_with_file' for op,args in n.calls)
    if not published:
        assert all(not r['images'] for r in PresetCatalog(tmp_path/'preset_cache').search())


def test_gallery_selection_exceeds_search_page_and_icons_do_not_skip(tmp_path):
    n=Native(tmp_path)
    n.rows=[dict(n.rows[0],id=f'item-{i:03}',resource=f'Clothing/Tops/N00/{i:03}',
            selectable_preset_ids=[f'clothing/Tops/{i:03}']) for i in range(205)]
    s=PresetCatalog(tmp_path/'preset_cache');s.sync(n.rows,{'build':'a'*64,'session':'token'}, {'builtin':True,'custom':True})
    framing=s.get_framing('Clothing/Tops')
    from vroid_mcp.preset_catalog import capture_identity
    from vroid_mcp.situation_proof import raster_evidence,definition
    image=subject_png();raster=raster_evidence(image);catalog=s._load()
    for index,row in enumerate(n.rows[:204]):
        r=catalog['presets'][row['resource']];g=group(r['id'],'Tops',resource=r['resource'])
        member={'verified':True,'revision_verified':True,'root':g,'members':[g]}
        provenance={'kind':'situation','verified':True,'requested_framing':framing,'build':'a'*64,
            'source':'clean_fixed_camera_render','framing':optical_proof(framing),'quality':{**quality_plan(512),'msaa_samples':4},
            'capture_input':capture_identity(r),'raster':raster,'membership':member,'native_definition':definition(member),
            'tested':{'kind':'builtin','resource':r['resource'],'id':g['id'],'type':g['type'],'revision':'1','group_resource':r['resource']}}
        if index==0:template=s.publish_image(r['key'],image,provenance,r['fingerprint'])
        r['images']['situation']={**template,**provenance,'fingerprint':r['fingerprint']}
    with s.locked():s._write(s.path,catalog)
    last=s.get(n.rows[-1]['resource']);s.publish_image(last['key'],png(),{'kind':'native-icon','source':'native'},last['fingerprint'])
    result=run(n,limit=1)
    assert result['processed']==1 and result['skipped']==204
    assert result['rows'][0]['key']==n.rows[-1]['resource']


@pytest.mark.parametrize('refresh,changed',[(True,False),(False,True)])
def test_gallery_refresh_and_new_framing_render_again(tmp_path,refresh,changed):
    n=Native(tmp_path);run(n);n.token='token'
    if changed:PresetCatalog(tmp_path/'preset_cache').set_framing('Clothing/Tops',yaw=90)
    result=run(n,refresh=refresh)
    assert result['processed']==1 and n.capture_count==2


def test_gallery_cannot_retain_unproven_optional_accessory_as_required_baseline(tmp_path):
    n=Native(tmp_path);n.groups.append(group('unremovable-hat','Hat',False))
    result=run(n)
    assert not result['processed'] and result['errors']
    assert n.capture_count==0 and result['restore']['state']=='restored'


def test_gallery_does_not_strip_required_face_even_with_native_clear(tmp_path):
    n=Native(tmp_path);n.groups.append(group('iris','Iris',True))
    result=run(n)
    assert result['processed']==1 and 'iris' not in n.removed


def test_custom_gallery_binds_custom_and_group_resource_names_before_dispatch(tmp_path):
    n=Native(tmp_path);profile=tmp_path/'profile';profile.mkdir()
    path=profile/'registered.vroidcustomitem';type='TransferableGroupType.N00.Level1.Tops'
    meta={'rootTransferableGroupId':'custom-root','rootTransferableGroupTypeId':type}
    with zipfile.ZipFile(path,'w') as z:z.writestr('v1customitem/meta.json',json.dumps(meta))
    registered=dict(path=str(path),id='custom-root',group_type=type,resource_name='user/group',revision='g1',
                    custom_resource_name='user/custom',custom_revision='c1',registered=True)
    n.rows=[dict(kind='custom',resource='user/custom',category='Custom/Tops',owned=True,usable=True,selectable=True,
        id='custom-root',revision='g1',custom_revision='c1',resource_name='user/group',group_type=type,path=str(path),registered=True)]
    original=n.call
    async def native(op,args=None):
        if op=='custom_item_state':return dict(model_token=n.token,files=[registered],base_path=str(profile))
        if op=='custom_item_validate_begin':return dict(model_token=n.token,request_id='custom',completed=True,compatible=True)
        if op=='apply_registered_custom_item':
            n.groups=[g for g in n.groups if g['type']!=type]
            n.groups.append(dict(group('custom-root','Tops',resource='user/group'),revision='g1'));return {'frame':3}
        if op=='custom_item_application_state':return dict(model_token=n.token,completed=True)
        if op=='custom_item_validate_release':return {'released':True}
        return await original(op,args)
    n.runtime._call=native
    async def build():return await n.runtime.build_preset_thumbnails('token','Custom/Tops',True)
    result=asyncio.run(build())
    assert result['processed']==1 and not result['errors']
    image,_=PresetCatalog(tmp_path/'preset_cache').resolve_image(result['rows'][0]['key'])
    assert image['tested']['resource']=='user/custom' and image['tested']['revision']=='g1'
    assert image['tested']['custom_revision']=='c1'


def test_gallery_holds_actual_server_gate_until_restore_without_lock_recursion(tmp_path,monkeypatch):
    import vroid_mcp.server as module
    n=Native(tmp_path);entered=asyncio.Event();release=asyncio.Event();history=[];original=n.call
    async def call(op,args=None):
        if op=='save_as':entered.set();await release.wait()
        if op=='get_height':history.append(n.token);return {'model_token':n.token,'live_centimeters':170}
        return await original(op,args)
    n.runtime._call=call;n.runtime.start=lambda:None
    async def init(*args):return {'model_token':'token'}
    n.runtime.initialize=init
    monkeypatch.setattr(module,'Runtime',lambda lab:n.runtime)
    server=module.create_server(tmp_path,'F00')
    async def check():
        task=asyncio.create_task(server._tool_manager.get_tool('build_preset_thumbnails').fn(
            expected_model='token',category='Clothing/Tops',disposable_model=True))
        await asyncio.wait_for(entered.wait(),2)
        read=asyncio.create_task(server._tool_manager.get_tool('get_height').fn())
        await asyncio.sleep(0)
        assert not history and not read.done()
        release.set();result=await asyncio.wait_for(task,3);await read
        assert result['restore']['state']=='restored' and history==['fresh']
    asyncio.run(check())


@pytest.mark.parametrize('change',[
    {'provenance':'native_thumbnail'},
    {'framing':{'schema':'vroid-situation-framing-v1','camera_readback_verified':False}},
    {'framing':{'schema':'vroid-situation-framing-v1','camera_readback_verified':True,
                'source_renderer_count':0}},
])
def test_gallery_rejects_nonrender_or_incomplete_geometry_proof(tmp_path,change):
    n=Native(tmp_path);original=n.call
    async def native(op,args=None):
        value=await original(op,args)
        if op=='screenshot':
            for k,v in change.items():value[k]={**value[k],**v} if isinstance(v,dict) else v
        return value
    n.runtime._call=native;result=run(n)
    assert not result['processed'] and result['restore']['state']=='restored'


@pytest.mark.parametrize('field,value',[('category','../bad'),('expected_model',''),('limit',True),('refresh','yes')])
def test_gallery_invalid_arguments_do_not_initialize(tmp_path,monkeypatch,field,value):
    monkeypatch.setattr(Runtime,'start',lambda *a:(_ for _ in ()).throw(AssertionError('startup before validation')))
    server=create_server(tmp_path,'F00')
    args=dict(expected_model='token',category='Clothing/Tops',disposable_model=True)
    args[field]=value
    with pytest.raises(ValueError):asyncio.run(server._tool_manager.get_tool('build_preset_thumbnails').fn(**args))


def test_gallery_compare_and_swap_failure_preserves_capture_evidence(tmp_path):
    n=Native(tmp_path);original=n.call
    async def native(op,args=None):
        result=await original(op,args)
        if op=='screenshot':
            s=PresetCatalog(tmp_path/'preset_cache')
            s.sync([dict(n.rows[0],name='changed')],{'build':'a'*64,'session':'token'}, {'builtin':True,'custom':True})
        return result
    n.runtime._call=native;result=run(n)
    assert result['processed']==0 and result['restore']['state']=='restored'
    assert Path(result['rows'][0]['capture_path']).is_file()
    assert 'CATALOG_IMAGE_IDENTITY_STALE' in str(result['errors'])


@pytest.mark.parametrize('valid',[True,False])
def test_gallery_set_needs_root_bound_direct_member_certificate(tmp_path,valid):
    n=Native(tmp_path);n.rows[0]['is_set_item']=True;original=n.call
    async def native(op,args=None):
        value=await original(op,args)
        if op=='list_groups' and args.get('situation_candidate'):
            g=group('canon-a','ClothingSet',resource=n.rows[0]['resource']);child=group('set-top','Tops',resource='set/top')
            value['situation_definition']={'verified':True,'revision_verified':True,'root':g,'members':[g,child]}
        if op=='apply_preset':
            n.groups[-1]['type']='TransferableGroupType.N00.Level1.ClothingSet'
            n.groups.append(group('set-top','Tops',resource='set/top'))
        if op=='list_groups' and args.get('situation_root'):
            value['situation_membership']={'verified':valid,'root':deepcopy(args['situation_root']),
                'members':deepcopy(n.groups[-2:]),'revision_verified':True,'error':None if valid else 'RecommendedTransferableGroup'}
            value['situation_membership']['root']['updated_since_last_revision']=False
        return value
    n.runtime._call=native;result=run(n)
    assert result['processed']==int(valid) and result['restore']['state']=='restored'
    if not valid:
        assert n.capture_count==0 and result['rows'][0]['membership']['verified'] is False


def test_snapshot_is_write_pinned_during_uncertain_native_import(tmp_path):
    import os
    if os.name!='nt':pytest.skip('Windows file-sharing protection')
    n=Native(tmp_path,'restore');result=run(n)
    assert n.runtime.uncertain and result['restore']['state']=='failed'
    path=Path(result['snapshot']['path'])
    try:
        with pytest.raises(OSError):path.write_bytes(b'substitute')
    finally:
        for pin in n.runtime._pending_custom_item_pins:pin.__exit__(None,None,None)
        n.runtime._pending_custom_item_pins=[]


def test_measurement_is_read_only_and_returns_native_and_geometry_separately(tmp_path):
    n=Native(tmp_path);calls=[]
    async def native(op,args):
        calls.append(op)
        if op=='capture_framing_reference':return {'model_token':'token','renderer_count':1,
            'bounds':{'min':[2,1,-8],'max':[4,3,-4]},'vertical_span_m':2,'renderer_extent_cm':200,
            'source_grounded_max_y_cm':300,'horizontal_center':[3,-6],
            'landmarks':{'Head':{'available':False},'LeftFoot':{'available':False}}}
        if op=='get_height':return {'model_token':'token','live_centimeters':170,'label':'170cm'}
        raise AssertionError(op)
    n.runtime._call=native
    result=asyncio.run(n.runtime.measure_model('token'))
    assert result['vertical_span_m']==2 and result['native_height']['live_centimeters']==170
    assert calls==['capture_framing_reference','get_height']


def test_gallery_rejects_incomplete_inventory_on_membership_certificate_read(tmp_path):
    n=Native(tmp_path);original=n.call
    async def native(op,args=None):
        value=await original(op,args)
        if op=='list_groups' and args.get('situation_root'):value['membership_complete']=False
        return value
    n.runtime._call=native;result=run(n)
    assert result['processed']==0 and n.capture_count==0
    assert result['restore']['state']=='restored'
