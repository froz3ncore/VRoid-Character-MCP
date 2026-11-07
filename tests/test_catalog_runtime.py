import asyncio
from copy import deepcopy

import pytest

from vroid_mcp.runtime import Runtime
from vroid_mcp.server import create_server


def snapshot():
    return {'model_token':'token','build':'a'*64,'builtin_complete':True,'custom_complete':True,
            'scope':'registered collection after observed OnUpdate',
            'areas':['face','body','hair','clothing'], 'rows':[
                {'kind':'builtin','id':'clothing/Tops/a','resource':'Clothing/Tops/N00/a',
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
        if op=='preset_preview_begin': return thumbnail(preset_id='clothing/Tops/a',resource_name='Clothing/Tops/N00/a')
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


@pytest.mark.parametrize('race',['newer-revision','recycled-preset-id'])
def test_icons_require_the_exact_scanned_resource_and_fingerprint(tmp_path,race):
    from test_preset_previews import thumbnail
    from vroid_mcp.preset_catalog import PresetCatalog
    r=Runtime(tmp_path);s=PresetCatalog(tmp_path/'preset_cache')
    async def settled(*args):return {'model_token':'token'}
    r._settle=settled
    async def native(op,args):
        if op=='preset_catalog_begin':return {'request_id':'scan'}
        if op=='preset_catalog_poll':return {'completed':True,**snapshot()}
        if op=='preset_catalog_release':
            if race=='newer-revision':
                newer=deepcopy(snapshot()['rows']);newer[0]['name']='A newer revision'
                s.sync(newer,{'build':'b'*64,'session':'other'},{'builtin':True,'custom':True})
            return {}
        if op=='preset_preview_begin':return thumbnail(preset_id='clothing/Tops/a',
            resource_name='Clothing/Tops/N00/REBOUND' if race=='recycled-preset-id' else 'Clothing/Tops/N00/a')
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
        if op=='preset_catalog_release':return {}
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
        if op=='preset_catalog_release':return {}
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
