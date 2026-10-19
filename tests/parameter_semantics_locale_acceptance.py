"""Verify native keys and exact name corrections across Chinese/English labels."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

from parameter_semantics_acceptance import lists,values,validate,digest,dump

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as lifecycle


async def run(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);lifecycle.OUT=out
    baseline=json.loads(args.baseline.read_text(encoding='utf-8'))['initial']
    original=lifecycle.StdioServerParameters
    def parameters(**kwargs):
        kwargs['args']=['-u',str(Path(__file__).with_name('parameter_semantics_locale_server.py'))]+kwargs['args'][2:]
        return original(**kwargs)
    lifecycle.StdioServerParameters=parameters
    model=lifecycle.LAB/'saves/whale_maid_03_test_base.vroid';before=digest(model)
    preference=lifecycle.LAB/'profile/AppData/LocalLow/pixiv/VRoid Studio/preferences/editoroption.xml'
    preference_bytes=preference.read_bytes()
    try:
        async with lifecycle.client_for(model,'english') as (_,call):
            english=await lists(call);coverage=validate(english)
            assert values(english)==values(baseline)
            changed=[]
            fields=('semantic_key','semantic_group','semantic_kind','semantic_bindings','translation_key')
            for area,data in english.items():
                previous={p['id']:p for p in baseline[area]['parameters']}
                assert set(previous)=={p['id'] for p in data['parameters']}
                for p in data['parameters']:
                    old=previous[p['id']]
                    assert all(p[k]==old[k] for k in fields)
                    if p['name_source']=='brainrom_correction':assert p['name']==old['name']
                    if p['label']!=old['label']:changed.append({'id':p['id'],'chinese_label':old['label'],'english_label':p['label'],'name':p['name'],'key':p['semantic_key']})
            assert changed,'Locale switch did not change any native labels'
            dump(out/'english.json',english)
            record={'passed':True,'coverage':coverage,'changed_native_labels':len(changed),'examples':changed[:10],
                    'semantic_bindings_identical':True,'values_unchanged':True}
    finally:
        # Only this disposable lab's preference file; restore exact pre-test bytes if touched.
        if preference.read_bytes()!=preference_bytes:preference.write_bytes(preference_bytes)
    assert digest(model)==before
    record.update(source_unchanged=True,preference_restored=True)
    dump(out/'acceptance.json',record)
    print(json.dumps({'passed':True,'changed_native_labels':len(changed),'output':str(out)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    asyncio.run(run(parser.parse_args()))
