"""Exercise native motion capture through stdio MCP, with explicit playback ownership."""
import asyncio,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/target-fit-v02'
native.OUT=OUT
VIEW='three_quarter'
async def main():
    record=json.loads((OUT/'refined-wear-acceptance.json').read_text(encoding='utf8'))
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']['path']
    saved=Path(record['save']['path']);before=hashlib.sha256(saved.read_bytes()).hexdigest()
    async with native.client_for(Path(base),'motion-acceptance') as (client,call):
        catalog=await client.list_tools();assert 'capture_wear_motion' in {t.name for t in catalog.tools}
        status=await call('get_wear_status')
        status=await call('open_wear_project',{'filename':saved.name,'expected_wear':status['wear_token'],'discard_unsaved':True})
        token=status['wear_token']
        await call('capture_wear_motion',{'expected_wear':token},True)
        started=await call('set_wear_animation',{'expected_wear':token,'playing':True})
        try:
            await call('capture_wear_motion',{'expected_wear':'stale'},True)
            captured=await call('capture_wear_motion',{'expected_wear':token,'samples':10,'interval_seconds':.25,'view':VIEW,'size':768})
            assert 'samples' not in captured and len(captured['images'])==10
            evidence=json.loads(Path(captured['manifest_path']).read_text(encoding='utf8'))
            folder=OUT/'native-motion';assert not folder.exists();folder.mkdir()
            for i,sample in enumerate(evidence['samples']):shutil.copy2(sample['path'],folder/('frame-%02d.png'%i))
            shutil.copy2(captured['manifest_path'],folder/'motion.json')
            assert captured['summary']['finite_transforms'] and captured['summary']['frames_advanced']
            assert captured['summary']['native_bone_motion_observed']
            result={'passed':True,'tools':len(catalog.tools),'started':started,'motion':captured['summary'],'stale_and_stopped_rejected':True,
                'excluded_edit_renderer_count':evidence['samples'][0]['excluded_edit_renderer_count'],
                'preview_renderer_count':len(evidence['samples'][0]['renderers']),
                'scope':'MCP sampling and observed transforms; images require separate visual review'}
        finally:
            stopped=await call('set_wear_animation',{'expected_wear':token,'playing':False})
            assert not stopped['animation_playing']
        after=await call('capture_wear_review',{'expected_wear':token,'views':['front'],'size':768})
        result['post_motion_static_capture']=after['images'][0]
    assert hashlib.sha256(saved.read_bytes()).hexdigest()==before
    result.update(saved_xroid_unchanged=True)
    (OUT/'native-motion-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    parser.add_argument('--view',choices=['front','side','back','three_quarter'],default=VIEW);args=parser.parse_args()
    OUT=args.out.resolve();VIEW=args.view;native.OUT=OUT
    assert OUT.is_relative_to(ROOT/'projects/whale-maid')
    asyncio.run(main())
