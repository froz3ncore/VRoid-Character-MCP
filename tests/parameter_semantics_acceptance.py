"""Real native list/write/preset/save/reopen regression in the exclusive lab-test."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as lifecycle


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')


async def lists(call):
    result={}
    for area in ('face','body','clothing'):
        result[area]=await call('list_'+area+'_params')
    return result


def values(data):return {a:{p['id']:p['value'] for p in r['parameters']} for a,r in data.items()}


def signatures(data):
    return {a:{p['id']:{k:p[k] for k in ('semantic_key','semantic_group','semantic_kind','semantic_bindings','translation_key','name','name_source','label')}
               for p in r['parameters']} for a,r in data.items()}


def validate(data):
    coverage={}
    for area,r in data.items():
        for p in r['parameters']:
            if p['semantic_status']=='complete':
                assert p['semantic_key']=='|'.join(b['key'] for b in p['semantic_bindings'])
                roles=[b['role'] for b in p['semantic_bindings']]
                assert roles==(['negative','positive'] if p['semantic_kind']=='combined' else ['value'])
            else:assert p['semantic_key'] is None
            if p['name_source']=='brainrom_correction':assert p['name_key']==p['translation_key'] and p['name_language']=='en'
            else:assert p['name']==p['label'] and p['name_key'] is None
        coverage[area]={'total':len(r['parameters']),'semantic_complete':sum(p['semantic_status']=='complete' for p in r['parameters']),
                        'corrected':sum(p['name_source']=='brainrom_correction' for p in r['parameters']),
                        'combined':sum(p['semantic_kind']=='combined' for p in r['parameters'])}
    return coverage


async def typed(call,domain,scope=None):
    rows=[];offset=0
    while True:
        r=await call('list_parameters',{'domain':domain,'scope':scope,'offset':offset,'limit':500})
        rows.extend(r['parameters'])
        if r['next_offset'] is None:return rows
        offset=r['next_offset']


async def run(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=args.reopen_only);lifecycle.OUT=out
    source=lifecycle.LAB/'saves/whale_maid_03_test_base.vroid';source_hash=digest(source)
    if args.reopen_only:
        record=json.loads((out/'saved.json').read_text(encoding='utf-8'))
        assert digest(record['save']['path'])==record['save']['sha256']
    else:
        async with lifecycle.client_for(source,'edit') as (client,call):
            initial=await lists(call);token=initial['face']['model_token'];coverage=validate(initial)
            dump(out/'initial.json',initial)
            print(json.dumps({'phase':'listed','coverage':coverage},ensure_ascii=True),flush=True)
            assert all(p['semantic_status']=='complete' for a in ('face','body','clothing') for p in initial[a]['parameters'])
            # Compare the additive fields against the pre-change native probe, not just this implementation.
            prior=json.loads((ROOT/'work/parameter-semantics-probe-v02/parameters.json').read_text(encoding='utf-8'))
            for area in initial:
                old={p['id']:p for p in prior[area]['parameters']}
                for p in initial[area]['parameters']:
                    assert all(p[k]==old[p['id']][k] for k in ('label','value','min','max','editable','type','category_key'))
                by_id={p['id']:p for p in await typed(call,area)}
                assert all(by_id[p['id']]['semantic_key']==p['semantic_key'] and by_id[p['id']]['name']==p['name'] for p in initial[area]['parameters'])
            # Every other typed domain remains readable; unsupported metadata never invents keys.
            extra={}
            for domain in ('colors','general','expressions'):
                rows=await typed(call,domain);extra[domain]=len(rows)
            instances=(await call('list_accessories'))['instances']
            extra['accessories']=sum([len(await typed(call,'accessories',p['id'])) for p in instances])
            names={p['name'] for p in initial['face']['parameters']}
            assert 'Nose Height' in names and 'Nostril Width' in names
            combined_blend=[p for r in initial.values() for p in r['parameters'] if p['type']=='CombinedBlendShapeTransformParameterViewModel']
            assert combined_blend and all(p['semantic_status']=='complete' for p in combined_blend)
            # Same visible label need not mean the same parameter. Keep native write IDs distinct.
            groups={}
            for p in initial['clothing']['parameters']:groups.setdefault(p['label'],[]).append(p)
            duplicate_groups=[rows for rows in groups.values() if len(rows)>1]
            assert duplicate_groups
            dump(out/'same-name-examples.json',duplicate_groups[:3])
            target=next(p for p in initial['face']['parameters'] if p['name']=='Nose Height' and p['editable'])
            for bad in (
                {'expected_model':token,'changes':[{'id':target['semantic_key'],'value':target['value']}]},
                {'expected_model':'stale','changes':[{'id':target['id'],'value':target['value']}]},
                {'expected_model':token,'changes':[{'id':target['id'],'value':target['value']}]*2},
            ):
                assert (await client.call_tool('set_face_params',bad)).isError
            assert values(await lists(call))==values(initial)
            value=target['value']+.03 if target['value']+.03<=target['max'] else target['value']-.03
            edited=await call('set_face_params',{'expected_model':token,'changes':[{'id':target['id'],'value':value}]})
            assert edited['ok']
            changed=await lists(call);assert signatures(changed)==signatures(initial)
            assert abs(next(p['value'] for p in changed['face']['parameters'] if p['id']==target['id'])-value)<1e-5
            restored=await call('undo',{'expected_model':token})
            assert all('name' in p for p in restored['parameters'])
            assert values(await lists(call))==values(initial)
            print(json.dumps({'phase':'write_and_undo_passed','id':target['id'],'name':target['name']}),flush=True)
            catalog=await call('list_presets',{'area':'face'})
            category=next(c['id'] for c in catalog['categories'] if 'nose' in c['id'].lower())
            presets=await call('list_presets',{'area':'face','category':category,'limit':200})
            preset=next(p for p in presets['presets'] if not p.get('clear') and not p.get('selected'))
            await call('apply_preset',{'expected_model':token,'area':'face','preset_id':preset['id']})
            after_preset=await lists(call);validate(after_preset)
            assert signatures(after_preset)==signatures(initial)
            await call('undo',{'expected_model':token});assert values(await lists(call))==values(initial)
            print(json.dumps({'phase':'preset_switch_passed','preset_id':preset['id']}),flush=True)
            record={'source':str(source),'source_sha256':source_hash,'coverage':coverage,'initial':initial,
                    'extra_domains':extra,'write_and_undo_passed':True,'preset_switch_passed':True,
                    'legacy_fields_preserved':True,'validation_rejections':3,'same_name_groups':len(duplicate_groups)}
            saved=await call('save_as',{'expected_model':token,'filename':'parameter-semantics-'+uuid.uuid4().hex+'.vroid'})
            record['save']=saved;dump(out/'saved.json',record)
            print(json.dumps({'phase':'saved','path':saved['path']}),flush=True)
    async with lifecycle.client_for(Path(record['save']['path']),'reopen') as (_,call):
        data=await lists(call);validate(data)
        assert signatures(data)==signatures(record['initial']) and values(data)==values(record['initial'])
        record.update(cold_reopen_passed=True,source_unchanged=digest(record['source'])==record['source_sha256'],passed=True)
        assert record['source_unchanged'];dump(out/'acceptance.json',record)
    print(json.dumps({'passed':True,'coverage':record['coverage'],'cold_reopen':True,'output':str(out)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reopen-only',action='store_true')
    asyncio.run(run(parser.parse_args()))
