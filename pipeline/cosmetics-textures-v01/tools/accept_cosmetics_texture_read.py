"""Native read-only acceptance of semantic groups and raster addressing."""
import argparse,asyncio,json
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/cosmetics-texture-read-v01'
native.PROJECT=ROOT/'work/cosmetics-mcp-v01';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
async def main():
    OUT.mkdir(exist_ok=False);model=Path(json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json').read_text(encoding='utf8'))['save']['path'])
    async with native.client_for(model,'read') as (_,call):
        token=(await call('list_face_params'))['model_token'];r=await call('list_texture_regions',{'expected_model':token});(OUT/'regions.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
        for region in r['regions']:
            print(json.dumps({'part':region['part'],'images':len(region['editable_images']),'bindings':len(region['image_bindings'])}),flush=True)
            if region['editable_images']:
                layers=await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']});(OUT/(region['part']+'-layers.json')).write_text(json.dumps(layers,ensure_ascii=False,indent=2),encoding='utf8')
                if layers['layers']:
                    image=await call('export_texture_layer',{'expected_model':token,'region_id':region['region_id'],'layer_id':layers['layers'][0]['layer_id']});(OUT/(region['part']+'-export.json')).write_text(json.dumps(image,ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path);args=parser.parse_args()
    if args.out:OUT=args.out.resolve();native.OUT=OUT
    asyncio.run(main())
