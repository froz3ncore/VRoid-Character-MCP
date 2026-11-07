import asyncio
from copy import deepcopy

import pytest

from vroid_mcp.runtime import Runtime
from vroid_mcp.server import create_server


def snapshot():
    return {'model_token':'token','build':'a'*64,'builtin_complete':True,'custom_complete':True,
            'scope':'registered collection after observed OnUpdate',
            'areas':['face','body','hair','clothing'], 'rows':[
                {'kind':'builtin','id':'canon-a','resource':'Clothing/Tops/N00/a',
                 'category':'Clothing/Tops','owned':True,'usable':True,'selectable':True,
                 'area':'clothing','selectable_preset_ids':['clothing/Tops/a']},
                {'kind':'builtin','id':'locked-id','resource':'Clothing/Tops/N00/z',
                 'category':'Clothing/Tops','owned':False,'usable':False,'selectable':False,
                 'selectable_preset_ids':[]}], 'errors':[]}


def test_native_snapshot_sync_and_bounded_icons(tmp_path):
    from test_preset_previews import thumbnail
    r = Runtime(tmp_path); calls=[]
    async def settled(*args): return {'model_token':'token'}
    r._settle=settled
    async def native(op,args):
        calls.append((op,args))
        if op=='preset_catalog_begin': return {'request_id':'scan'}
        if op=='preset_catalog_poll': return {'completed':True, **snapshot()}
        if op=='preset_catalog_release': return {'released':True}
        if op=='preset_preview_begin': return thumbnail(preset_id='clothing/Tops/a',transferable_id='canon-a',resource_name='Clothing/Tops/N00/a')
        raise AssertionError(op)
    r._call=native
    result=asyncio.run(r.sync_preset_cache('token',icons=True,icon_limit=1))
    assert result['observed']==2 and result['images']==1
    from vroid_mcp.preset_catalog import PresetCatalog
    s=PresetCatalog(tmp_path/'preset_cache')
    assert len(s.search(include_locked=True))==2
    assert s.resolve_image(s.search()[0]['key'])[0]['kind']=='native-icon'
    assert len([op for op,args in calls if op=='preset_preview_begin'])==1
    assert calls[-2][0]=='preset_catalog_release'


@pytest.mark.parametrize('race',['newer-revision','recycled-preset-id','recycled-native-id'])
def test_icons_require_the_exact_scanned_resource_and_fingerprint(tmp_path,race):
    from test_preset_previews import thumbnail
    from vroid_mcp.preset_catalog import PresetCatalog
    r=Runtime(tmp_path);s=PresetCatalog(tmp_path/'preset_cache')
    async def settled(*args):return {'model_token':'token'}
    r._settle=settled
    async def native(op,args):
        if op=='preset_catalog_begin':return {'request_id':'scan'}
        if op=='preset_catalog_poll':return {'completed':True,**snapshot()}
        if op=='preset_preview_begin':
            if race=='newer-revision':
                newer=deepcopy(snapshot()['rows']);newer[0]['name']='A newer revision'
                s.sync(newer,{'build':'b'*64,'session':'other'},{'builtin':True,'custom':True})
            return thumbnail(preset_id='clothing/Tops/a',
                transferable_id='foreign' if race=='recycled-native-id' else 'canon-a',
                resource_name='Clothing/Tops/N00/REBOUND' if race=='recycled-preset-id' else 'Clothing/Tops/N00/a')
        if op=='preset_catalog_release':return {'released':True}
        raise AssertionError(op)
    r._call=native
    with pytest.raises(ValueError):asyncio.run(r.sync_preset_cache('token',icons=True,icon_limit=1))
    assert all(not r['images'] for r in s.search())


def test_missing_native_icons_count_toward_attempt_limit(tmp_path):
    r=Runtime(tmp_path); attempted=[]
    async def settled(*args):return {'model_token':'token'}
    r._settle=settled
    async def native(op,args):
        if op=='preset_catalog_begin':return {'request_id':'scan'}
        if op=='preset_catalog_poll':
            result=snapshot(); extra=deepcopy(result['rows'][0]);extra.update(id='clothing/Tops/b',resource='Clothing/Tops/N00/b',selectable_preset_ids=['clothing/Tops/b'])
            result['rows'].append(extra);return {'completed':True,**result}
        if op=='preset_catalog_release':return {'released':True}
        if op=='preset_preview_begin':
            attempted.append(args['preset_id']);return {'completed':True,'ok':False,'model_token':'token','preset_id':args['preset_id'],'error':'missing'}
        raise AssertionError(op)
    r._call=native
    result=asyncio.run(r.sync_preset_cache('token',icons=True,icon_limit=1))
    assert result['images']==0 and len(attempted)==1


@pytest.mark.parametrize('changes', [ {'model_token':'other'}, {'builtin_complete':False},
    {'areas':['face']}, {'rows':snapshot()['rows']*2} ])
def test_incomplete_or_inconsistent_native_snapshot_does_not_publish(tmp_path,changes):
    r=Runtime(tmp_path); writes=[]
    async def settled(*args): return {'model_token':'token'}
    r._settle=settled
    async def native(op,args):
        if op=='preset_catalog_begin': return {'request_id':'scan'}
        if op=='preset_catalog_poll': return {'completed':True,**snapshot(),**changes}
        if op=='preset_catalog_release': return {'released':True}
        writes.append(op)
    r._call=native
    with pytest.raises((ValueError,RuntimeError)): asyncio.run(r.sync_preset_cache('token'))
    assert not (tmp_path/'preset_cache'/'catalog.json').exists() and not writes


@pytest.mark.parametrize('args',[('',False,None),('token','yes',None),('token',True,0),('token',True,True),('token',True,201)])
def test_sync_validates_before_any_native_work(tmp_path,args):
    r=Runtime(tmp_path)
    async def forbidden(*args):raise AssertionError('native work before validation')
    r._call=r._settle=forbidden
    with pytest.raises(ValueError): asyncio.run(r.sync_preset_cache(*args))


def test_partial_custom_scan_preserves_previous_records_unknown(tmp_path):
    from test_preset_catalog import custom, SOURCE
    from vroid_mcp.preset_catalog import PresetCatalog
    s=PresetCatalog(tmp_path/'preset_cache'); s.sync([custom()],SOURCE,{'builtin':True,'custom':True})
    r=Runtime(tmp_path)
    async def settled(*args):return {'model_token':'token'}
    r._settle=settled
    async def native(op,args):
        if op=='preset_catalog_begin':return {'request_id':'scan'}
        if op=='preset_catalog_poll':return {'completed':True,**snapshot(),'custom_complete':False,'errors':['one observation failed']}
        if op=='preset_catalog_release':return {'released':True}
    r._call=native
    result=asyncio.run(r.sync_preset_cache('token'))
    assert result['complete']['custom'] is False and s.search(kind='custom')[0]['status']=='unknown'


def test_all_offline_tools_and_schema_listing_never_start_runtime(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('offline startup')
    monkeypatch.setattr(Runtime,'start',forbidden)
    server=create_server(tmp_path/'absent','F00')
    from vroid_mcp.preset_catalog import PresetCatalog
    from test_preset_catalog import row,SOURCE
    s=PresetCatalog(tmp_path/'absent'/'preset_cache')
    async def check():
        tools=await server.list_tools()
        assert {'search_preset_cache','annotate_preset_cache','sync_preset_cache','preset_thumbnail',
                'get_preset_framing','set_preset_framing','reset_preset_framing'} <= {t.name for t in tools}
        assert not (tmp_path/'absent').exists()
        await server.call_tool('search_preset_cache',{})
        await server.call_tool('get_preset_framing',{'category':'Hair/Back'})
        assert not (tmp_path/'absent').exists()
        s.sync([row()],SOURCE,{'builtin':True,'custom':True}); key=s.search()[0]['key']
        await server.call_tool('annotate_preset_cache',{'key':key,'author':'Me','label':'Pretty'})
        await server.call_tool('set_preset_framing',{'category':'Hair/Back','yaw':90})
        await server.call_tool('reset_preset_framing',{'category':'Hair/Back'})
        from test_preset_previews import png
        s.publish_image(key,png(),{'kind':'native-icon','source':'test'},s.get(key)['fingerprint'])
        result=await server.call_tool('preset_thumbnail',{'key':key})
        content=result[0] if isinstance(result,tuple) else result
        assert sum(c.type=='image' for c in content)==1
        if isinstance(result,tuple): assert result[1] is None
    asyncio.run(check())


def test_new_metadata_image_tools_do_not_duplicate_structured_payload(tmp_path):
    import base64,json
    from mcp.types import ImageContent,TextContent
    from test_preset_previews import png
    server=create_server(tmp_path/'absent','F00')
    marker=base64.b64encode(png()).decode('ascii')
    content=[TextContent(type='text',text='fixture'),ImageContent(type='image',data=marker,mimeType='image/png')]
    for name in ('preset_thumbnail','screenshot_metadata'):
        converted=server._tool_manager.get_tool(name).fn_metadata.convert_result(content)
        blocks,structured=converted if isinstance(converted,tuple) else (converted,None)
        assert sum(b.type=='image' for b in blocks)==1
        assert marker not in json.dumps(structured)
    # Existing structured consumers retain their baseline wire schema. Task 9
    # batch must remove duplicate legacy structured image data in its own envelope.
    assert server._tool_manager.get_tool('capture_review').fn_metadata.output_schema is not None


@pytest.mark.parametrize('args',[{'expected_model':''},{'expected_model':'   '},
    {'expected_model':'token','icons':'yes'},{'expected_model':'token','icon_limit':True},
    {'expected_model':'token','icon_limit':0}])
def test_invalid_public_sync_schema_rejects_before_app_start(tmp_path,monkeypatch,args):
    def forbidden(*args):raise AssertionError('app-started-before-validation')
    monkeypatch.setattr(Runtime,'start',forbidden)
    server=create_server(tmp_path/'absent','F00')
    with pytest.raises(Exception) as error:asyncio.run(server.call_tool('sync_preset_cache',args))
    assert 'app-started-before-validation' not in str(error.value)
    assert not (tmp_path/'absent').exists()


@pytest.mark.parametrize('icons',[False,True])
def test_release_owner_failure_never_publishes_removals(tmp_path,icons):
    from vroid_mcp.preset_catalog import PresetCatalog
    from test_preset_catalog import row,SOURCE
    s=PresetCatalog(tmp_path/'preset_cache');s.sync([row()],SOURCE,{'builtin':True,'custom':True});before=s.path.read_bytes()
    r=Runtime(tmp_path);releases=[]
    async def settled(*args):return {'model_token':'token'}
    async def native(op,args):
        if op=='preset_catalog_begin':return {'request_id':'scan'}
        if op=='preset_catalog_poll':return {'completed':True,**snapshot(),'rows':[]}
        if op=='preset_catalog_release':releases.append(op);raise ValueError('CATALOG_OWNER_CHANGED')
        raise AssertionError(op)
    r._settle,r._call=settled,native
    with pytest.raises(ValueError,match='OWNER_CHANGED'):asyncio.run(r.sync_preset_cache('token',icons))
    assert s.path.read_bytes()==before and len(releases)==1


def test_native_receipt_is_finished_before_archive_work(tmp_path,monkeypatch):
    from vroid_mcp import runtime_catalog
    from test_preset_catalog import custom
    r=Runtime(tmp_path);clock=[0];released=[]
    async def settled(*args):return {'model_token':'token'}
    root = tmp_path/'profile'; root.mkdir()
    path = root/'item.vroidcustomitem'; path.touch()
    item=custom(str(path));item.update(group_type='Tops',registered=True,custom_revision='1',resource_name='group/A')
    async def native(op,args):
        if op=='preset_catalog_begin':return {'request_id':'scan'}
        if op=='preset_catalog_poll':return {'completed':True,**snapshot(),'rows':[item], 'base_path':str(root)}
        if op=='preset_catalog_release':
            assert clock[0]<10;released.append(op);return {'released':True}
        raise AssertionError(op)
    def inspect(path, *, registered_generation):
        assert released;clock[0]=20
        return {'sha256':'a'*64,'metadata':{'rootTransferableGroupId':item['id'],'rootTransferableGroupTypeId':'Tops'}}
    monkeypatch.setattr(runtime_catalog,'inspect_custom_item',inspect)
    r._settle,r._call=settled,native
    assert asyncio.run(r.sync_preset_cache('token'))['observed']==1 and len(released)==1


@pytest.mark.parametrize('owned,include_locked,query,expected',[
    (None,False,'soft','A-free'),(True,False,'soft','B-owned'),(True,True,'soft','B-owned'),
    (False,False,'soft','A-free'),(False,True,'paid soft','C-paid'),(False,False,'paid soft',None)])
def test_public_owned_predicate_combines_before_limit(tmp_path,owned,include_locked,query,expected):
    from vroid_mcp.preset_catalog import PresetCatalog
    from test_preset_catalog import row,SOURCE
    s=PresetCatalog(tmp_path/'preset_cache');rows=[]
    for resource,own,usable in [('A-free',False,True),('B-owned',True,True),('C-paid',False,False)]:
        item=row(resource);item.update(owned=own,usable=usable);rows.append(item)
    s.sync(rows,SOURCE,{'builtin':True,'custom':True})
    for item in rows:s.annotate(item['resource'],'Me',description='paid soft' if item['resource']=='C-paid' else 'soft')
    server=create_server(tmp_path,'F00')
    args=dict(owned=owned,include_locked=include_locked,query=query,category='Clothing/Tops',kind='builtin',annotated_only=True,status='new',limit=1)
    result=asyncio.run(server._tool_manager.get_tool('search_preset_cache').run(args))
    assert [r['key'] for r in result]==([] if expected is None else [expected])


@pytest.mark.parametrize('owned',['true',1,0,[],{}])
def test_public_ownership_predicate_is_strict(tmp_path,owned):
    server=create_server(tmp_path,'F00')
    with pytest.raises(Exception):asyncio.run(server._tool_manager.get_tool('search_preset_cache').run({'owned':owned}))
