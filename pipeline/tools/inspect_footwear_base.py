"""Read native footwear choices and parameters from an isolated saved base."""
import asyncio,json,shutil
from pathlib import Path
import clean_native_clothing as native

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'projects/whale-maid/accessory-refinement-v02/inspection-native'

async def main():
    OUT.mkdir(parents=True,exist_ok=False);native.OUT=OUT
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']
    async with native.client_for(Path(base['path']),'footwear-inspect') as (_,call):
        await asyncio.sleep(5)
        token=(await call('list_face_params'))['model_token']
        result={'model_token':token,'source_base':base}
        for category in ('Shoes','Socks'):
            result[category]=await call('list_clothing_presets',{'category':category,'limit':200})
        for domain in ('clothing','colors'):
            values=[];offset=0
            while True:
                data=await call('list_parameters',{'domain':domain,'offset':offset,'limit':500})
                values.extend(data['parameters'])
                if data.get('next_offset') is None:break
                offset=data['next_offset']
            result[domain]=values
        # Read-only native preset thumbnails, preserving the base selection.
        for category in ('Shoes','Socks'):
            choices=[p['id'] for p in result[category]['presets'] if not p['id'].endswith('/none')]
            for start in range(0,len(choices),6):
                data=await call('preview_presets',{'expected_model':token,'area':'clothing','preset_ids':choices[start:start+6]})
                result[category+'_previews_%d'%start]=data
        (OUT/'inspection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'completed':True,'out':str(OUT),'shoe_choices':len(result['Shoes']['presets']),'sock_choices':len(result['Socks']['presets'])}),flush=True)

if __name__=='__main__':asyncio.run(main())
