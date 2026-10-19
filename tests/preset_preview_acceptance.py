"""Native stdio acceptance, exclusively through clean_native_clothing.client_for.

Requires the local lab-test fixture. Writes only new evidence and a new .vroid.
After a confirmed save, --reopen-only reuses saved.json without repeating the save.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as lifecycle


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


async def catalog(call,area):
    presets=[];offset=0
    while True:
        r=await call('list_presets',{'area':area,'offset':offset,'limit':200})
        presets.extend(r['presets'])
        if r['next_offset'] is None:break
        offset=r['next_offset']
    return presets


async def state(call):
    values={}
    for area in ('face','body'):
        r=await call('list_'+area+'_params')
        values[area]={p['id']:p['value'] for p in r['parameters']}
    colors=await call('list_parameters',{'domain':'colors','limit':500})
    assert colors.get('next_offset') is None
    values['colors']={p['id']:p['value'] for p in colors['parameters']}
    values['selected']={a:[p['id'] for p in await catalog(call,a) if p.get('selected')] for a in ('face','body','hair','clothing')}
    return values


async def preview(client,token,area,ids,out,label):
    result=await client.call_tool('preview_presets',{'expected_model':token,'area':area,'preset_ids':ids})
    assert not result.isError,str(result)
    manifest=json.loads(result.content[0].text)
    dump(out/(label+'-manifest.json'),manifest)
    assert manifest['model_token']==token and [p['id'] for p in manifest['presets']]==ids
    images=[];caption=None
    for block in result.content[1:]:
        if block.type=='text':caption=json.loads(block.text)
        if block.type=='image':
            data=base64.b64decode(block.data,validate=True)
            item=next(p for p in manifest['presets'] if p['id']==caption['preset_id'])
            assert item['ok'] and caption['name']==item['name'] and item['sha256']==hashlib.sha256(data).hexdigest()
            assert data[:8]==b'\x89PNG\r\n\x1a\n' and data[-8:-4]==b'IEND'
            assert (int.from_bytes(data[16:20],'big'),int.from_bytes(data[20:24],'big'))==(item['width'],item['height'])
            path=out/(label+'-'+str(len(images))+'.png');path.write_bytes(data)
            images.append({'preset_id':item['id'],'name':item['name'],'path':str(path),'sha256':item['sha256'],'source':item['source']})
    assert len(images)==sum(bool(p['ok']) for p in manifest['presets'])
    return {'manifest':manifest,'images':images}


async def run(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=args.reopen_only)
    lifecycle.OUT=out
    if args.fallback:
        original=lifecycle.StdioServerParameters
        def fallback_server(**kwargs):
            kwargs['args']=['-u',str(Path(__file__).with_name('preset_preview_fallback_server.py'))]+kwargs['args'][2:]
            return original(**kwargs)
        lifecycle.StdioServerParameters=fallback_server
    source=args.model.resolve();source_hash=digest(source)
    if args.reopen_only:
        record=json.loads((out/'saved.json').read_text(encoding='utf-8'))
        assert digest(record['save']['path'])==record['save']['sha256']
    else:
        async with lifecycle.client_for(source,'edit') as (client,call):
            tools=(await client.list_tools()).tools
            assert any(t.name=='preview_presets' for t in tools)
            print(json.dumps({'phase':'connected','tools':len(tools)}),flush=True)
            token=(await call('list_face_params'))['model_token']
            before=await state(call);previews={};choices={};coverage={}
            for area in ('face','body','hair','clothing'):
                presets=await catalog(call,area)
                coverage[area]={'presets':len(presets),'named':sum(p['name_source']=='brainrom_labels' for p in presets)}
                preferred={'face':['Iris','Eye'],'body':[],'hair':['HairFront','HairSet'],'clothing':['Shoes','Tops']}[area]
                real=[p for p in presets if not p.get('clear')]
                ordered=sorted(real,key=lambda p:next((i for i,c in enumerate(preferred) if c.lower() in p['category'].lower()),len(preferred)))
                ids=[p['id'] for p in ordered[:1 if args.probe else 3]]
                choices[area]=ids
                previews[area]=await preview(client,token,area,ids,out,'edit-'+area)
                print(json.dumps({'phase':'preview','area':area,**coverage[area],
                    'items':[{k:p.get(k) for k in ('id','name','ok','source','error','detail','direct_error')} for p in previews[area]['manifest']['presets']]},ensure_ascii=True),flush=True)
                assert all(p['ok'] for p in previews[area]['manifest']['presets']),previews[area]['manifest']
                if args.fallback:assert all(p['source']=='native_preview' for p in previews[area]['manifest']['presets'])
            # Check clear/real mixed responses, validation and session identity through MCP.
            hair=await catalog(call,'hair');clear=next(p for p in hair if p.get('clear'))
            mixed=await preview(client,token,'hair',[clear['id'],choices['hair'][0]],out,'edit-mixed')
            assert mixed['manifest']['presets'][0]['error']=='NO_PREVIEW_CLEAR' and len(mixed['images'])==1
            for bad in (
                {'expected_model':'stale-token','area':'hair','preset_ids':choices['hair']},
                {'expected_model':token,'area':'hair','preset_ids':['hair/not-a-real-preset']},
                {'expected_model':token,'area':'hair','preset_ids':[choices['hair'][0]]*2},
                {'expected_model':token,'area':'hair','preset_ids':['clothing/not-this-area']},
            ):
                assert (await client.call_tool('preview_presets',bad)).isError
            after=await state(call);assert before==after,'Preview changed native parameters or selected presets'
            record={'source':str(source),'source_sha256':source_hash,'coverage':coverage,'choices':choices,
                    'before':before,'previews':previews,'mixed':mixed,'preview_did_not_change_character':True,
                    'validation_rejections':4,'tools':len(tools)}
            dump(out/'edit.json',record)
            if args.probe:
                assert digest(source)==source_hash
                print(json.dumps({'probe_passed':True,'output':str(out)}),flush=True)
                return
            saved=await call('save_as',{'expected_model':token,'filename':'preset-preview-'+uuid.uuid4().hex+'.vroid'})
            record['save']=saved;dump(out/'saved.json',record)
            print(json.dumps({'phase':'saved','path':saved['path']}),flush=True)
    async with lifecycle.client_for(Path(record['save']['path']),'reopen') as (client,call):
        token=(await call('list_face_params'))['model_token']
        assert await state(call)==record['before'],'Saved/reopened character differs'
        reopened={}
        for area,ids in record['choices'].items():
            reopened[area]=await preview(client,token,area,ids,out,'reopen-'+area)
            original=record['previews'][area]['images']
            assert [(p['preset_id'],p['name'],p['sha256']) for p in reopened[area]['images']]==[(p['preset_id'],p['name'],p['sha256']) for p in original]
        record.update(reopened=reopened,cold_reopen_passed=True,source_unchanged=digest(record['source'])==record['source_sha256'],passed=True)
        assert record['source_unchanged']
        dump(out/'acceptance.json',record)
    print(json.dumps({'passed':True,'output':str(out),'images':sum(len(p['images']) for p in record['previews'].values()),'cold_reopen':True}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',type=Path,default=lifecycle.LAB/'saves/whale_maid_03_test_base.vroid')
    parser.add_argument('--probe',action='store_true')
    parser.add_argument('--reopen-only',action='store_true')
    parser.add_argument('--fallback',action='store_true',help='Force the native preview path in the test-owned process only')
    asyncio.run(run(parser.parse_args()))
