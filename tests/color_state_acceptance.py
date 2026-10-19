"""Native heterochromia, aggregate/shared state, history and cold reopen."""
import argparse,asyncio,json,sys,uuid
from pathlib import Path
from capture_quality_acceptance import dump,digest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as lifecycle

IRIS='colors/Iris/';LEFT=IRIS+'LeftEye';RIGHT=IRIS+'RightEye';BOTH=IRIS+'BothEyes'
def close(a,b):return len(a)==len(b) and all(abs(x-y)<1e-6 for x,y in zip(a,b))
def states(rows):return {p['id']:{k:p[k] for k in ('value','mixed','color_signature','alias_of','is_shared','color_bindings')} for p in rows}
async def colors(call,limit=500,offset=0):return (await call('list_parameters',{'domain':'colors','limit':limit,'offset':offset}))['parameters']
async def write(call,token,changes):
    r=await call('set_parameters',{'expected_model':token,'domain':'colors','changes':[{'id':i,'value':v} for i,v in changes]})
    assert r['ok'] and r['settled'] and r['color_verification_status']=='complete',r
    assert all(p['verified'] for p in r['applied']),r
    return r

async def main(args):
    out=args.output.resolve();out.mkdir(exist_ok=args.reopen_only);lifecycle.OUT=out
    source=lifecycle.LAB/'saves'/lifecycle.SOURCE;sha=digest(source)
    if args.reopen_only:
        record=json.loads((out/'saved.json').read_text(encoding='utf8'))
        assert digest(record['save']['path'])==record['save']['sha256']
    else:
        async with lifecycle.client_for(source,'edit') as (_,call):
            token=(await call('list_face_params'))['model_token']
            shapes={d:await call('list_'+d+'_params') for d in ('face','body','clothing')}
            initial=await colors(call);index={p['id']:p for p in initial}
            assert len(initial)==25
            prior=json.loads((ROOT/'evidence/color-state-probe-v03/colors.json').read_text(encoding='utf8'))['parameters']
            assert {p['id']:(p['label'],p['value'],p['editable']) for p in initial}=={p['id']:(p['label'],p['value'],p['editable']) for p in prior}
            assert sum(p['color_binding_status']=='complete' for p in initial)==24
            assert index[BOTH]['mixed'] is False and index[BOTH]['is_aggregate']
            assert not index[LEFT]['is_shared'] and not index[RIGHT]['is_shared']
            # Pagination must preserve relationships to IDs on other pages.
            paged=await colors(call,limit=1)
            assert len(paged)==1 and paged[0]['affected_parameter_ids']==initial[0]['affected_parameter_ids']
            right_only=await write(call,token,[(RIGHT,[.95,.2,.1,1])])
            rows=await colors(call);by={p['id']:p for p in rows}
            assert close(by[LEFT]['value'],index[LEFT]['value'])
            assert by[BOTH]['mixed'] is True and by[BOTH]['value'] is None
            assert {p['id'] for p in right_only['affected_parameters']}=={RIGHT,BOTH}
            await call('undo',{'expected_model':token});assert states(await colors(call))==states(initial)
            eye_write=await write(call,token,[(LEFT,[.95,.52,.08,1]),(RIGHT,[.12,.35,.92,1])])
            hetero=await colors(call);assert next(p for p in hetero if p['id']==BOTH)['mixed'] is True
            for changes in ([(BOTH,[.1,.2,.3,1]),(LEFT,[.2,.3,.4,1])],
                            [('colors/FaceSkin/MainColor',[.9,.8,.7,1]),('colors/BodySkin/MainColor',[.8,.7,.6,1])]):
                await call('set_parameters',{'expected_model':token,'domain':'colors','changes':[{'id':i,'value':v} for i,v in changes]},error=True)
                assert states(await colors(call))==states(hetero)
            await call('set_parameters',{'expected_model':'stale','domain':'colors','changes':[{'id':LEFT,'value':[1,0,0,1]}]},error=True)
            await call('set_parameters',{'expected_model':token,'domain':'colors','changes':[{'id':LEFT,'value':[1,0,0,1]},{'id':RIGHT,'value':[2,0,0,1]}]},error=True)
            assert states(await colors(call))==states(hetero)
            unified=await write(call,token,[(BOTH,[.12,.65,.28,1])])
            assert all(close(p['value'],[.12,.65,.28,1]) for p in await colors(call) if p['id'].startswith(IRIS))
            await call('undo',{'expected_model':token});assert states(await colors(call))==states(hetero)
            skin=await write(call,token,[('colors/FaceSkin/MainColor',[.94,.86,.80,1])])
            expected={'colors/'+g+'/MainColor' for g in ('FaceSkin','BodySkin','Eyelid','NoseLighting')}
            assert {p['id'] for p in skin['affected_parameters']}==expected
            assert all(p['is_shared'] and len(p['alias_ids'])==3 and len(p['shared_groups'])==4 for p in skin['affected_parameters'])
            assert all(close(p['value'],[.94,.86,.80,1]) for p in skin['affected_parameters'])
            await call('undo',{'expected_model':token});assert states(await colors(call))==states(hetero)
            assert shapes=={d:await call('list_'+d+'_params') for d in shapes}
            # A real Iris preset change must not leave stale color accessor state.
            catalog=await call('list_presets',{'area':'face'})
            dump(out/'preset-categories.json',catalog['categories'])
            category=next(c['id'] for c in catalog['categories'] if c['id']=='Eye')
            presets=await call('list_presets',{'area':'face','category':category,'limit':200})
            preset=next(p for p in presets['presets'] if not p.get('clear') and not p.get('selected'))
            await call('apply_preset',{'expected_model':token,'area':'face','preset_id':preset['id']})
            relisted=await colors(call)
            assert all(p['color_binding_status']=='complete' for p in relisted if p['id'].startswith(IRIS))
            dump(out/'after-preset.json',relisted)
            # Native eye presets can reset their colors/history. Relist and
            # explicitly set the desired sides on the new resource; never
            # assume one Undo preserves a former preset's color values.
            await write(call,token,[(LEFT,[.95,.52,.08,1]),(RIGHT,[.12,.35,.92,1])])
            restored=await colors(call);assert states(restored)==states(hetero)
            assert {p['id']:p['value'] for p in initial if not p['id'].startswith(IRIS)}=={p['id']:p['value'] for p in hetero if not p['id'].startswith(IRIS)}
            review=await call('capture_review',{'expected_model':token,'views':['front'],'size':1024,'quality':'high','label':'Native heterochromia state acceptance'})
            (out/'heterochromia.png').write_bytes(Path(review['images']['front']['path']).read_bytes())
            record={'initial':initial,'heterochromia':hetero,'right_only_result':right_only,'eyes_result':eye_write,'unify_result':unified,'shared_skin_result':skin,
                    'source':str(source),'source_sha256':sha,'preset_relisted':preset['id'],'colors_explicitly_restored_after_preset':True,'review':review}
            record['save']=await call('save_as',{'expected_model':token,'filename':'heterochromia-state-'+uuid.uuid4().hex+'.vroid'})
            dump(out/'saved.json',record)
            print(json.dumps({'phase':'saved','path':record['save']['path']}),flush=True)
    async with lifecycle.client_for(Path(record['save']['path']),'reopen') as (_,call):
        token=(await call('list_face_params'))['model_token']
        reopened=await colors(call);assert states(reopened)==states(record['heterochromia'])
        review=await call('capture_review',{'expected_model':token,'views':['front'],'size':1024,'quality':'high'})
        (out/'heterochromia-reopened.png').write_bytes(Path(review['images']['front']['path']).read_bytes())
        record['reopened']=reopened;record['reopen_review']=review
    # Same binding/aggregate/alias state under English labels, in another owned process.
    original=lifecycle.StdioServerParameters
    def english(**kw):
        kw['args']=[str(Path(__file__).with_name('parameter_semantics_locale_server.py')),*kw['args'][2:]]
        return original(**kw)
    preference=lifecycle.LAB/'profile/AppData/LocalLow/pixiv/VRoid Studio/preferences/editoroption.xml';prefs=preference.read_bytes()
    lifecycle.StdioServerParameters=english
    try:
        async with lifecycle.client_for(Path(record['save']['path']),'english') as (_,call):
            await call('list_face_params');rows=await colors(call)
            assert states(rows)==states(record['heterochromia'])
            record['english_labels_changed']=sum(a['label']!=b['label'] for a,b in zip(rows,record['heterochromia']))
            assert record['english_labels_changed']>0
            dump(out/'english.json',rows)
    finally:
        lifecycle.StdioServerParameters=original
        if preference.read_bytes()!=prefs:preference.write_bytes(prefs)
    record.update(passed=True,cold_reopen_passed=True,source_unchanged=digest(source)==sha,saved_copy_unchanged=digest(record['save']['path'])==record['save']['sha256'])
    assert record['source_unchanged'] and record['saved_copy_unchanged']
    dump(out/'acceptance.json',record)
    print(json.dumps({'passed':True,'output':str(out),'english_labels_changed':record['english_labels_changed']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen-only',action='store_true')
    asyncio.run(main(p.parse_args()))
