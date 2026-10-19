"""Read-only cold reopen of a previously saved, hash-verified outfit in a private lab."""
import asyncio,hashlib,json,sys
from pathlib import Path
ROOT=Path('D:/vroidmcp');sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as native
native.PROJECT=ROOT/'work/clothing-mcp-v17b';native.LAB=ROOT/'lab-clothing-fit-v17'
OUT=ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b';native.OUT=OUT
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
async def main():
    record=json.loads((OUT/'refined-wear-edit.json').read_text(encoding='utf8'));base_record=OUT/'isolated-base-record.json';base=json.loads(base_record.read_text(encoding='utf8'))['save']
    path=native.LAB/'saves'/Path(record['save']['path']).name;assert digest(path)==record['save']['sha256'];manifest=json.loads((OUT/'whale_maid_chest_skirt_v17b.xwear.json').read_text(encoding='utf8'));triangles=sum(g['triangles'] for g in manifest['meshes'])
    async with native.client_for(Path(base['path']),'private-lab-reopen') as (client,call):
        await call('list_face_params');await asyncio.sleep(10);state=await call('get_wear_status')
        state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':path.name,'discard_unsaved':True});token=state['wear_token']
        snap=await call('get_wear_snapshot',{'expected_wear':token});assert snap['base_model']==record['edit']['base_model'] and len(snap['items'])==1
        meshes=[r for inst in snap['items'][0]['instances'] for r in inst['renderers']];assert len(meshes)==97 and sum(m['triangles'] for m in meshes)==triangles
        mask=await call('inspect_wear_body_occlusion',{'expected_wear':token})
        plan=json.loads((OUT.parent/'tripo-shoe-rigid-v12/arch-visible-low-occlusion-plan.json').read_text(encoding='utf8'))
        assert mask['hidden_vertices']==plan['hidden_vertices'] and mask['source_geometry_sha256']==plan['source_geometry_sha256']
        shoes=await call('inspect_wear_native_shoes',{'expected_wear':token});assert not shoes['visible'] and shoes['current_triangle_count']==0
        shot=await call('capture_wear_review',{'expected_wear':token,'views':['front','body_right','back'],'size':1024,'quality':'high'})
        output={**record,'save':{**record['save'],'path':str(path)},'base_record':str(base_record),'passed':True,'cold_reopen_passed':True,'reopen':snap,'reopen_capture':shot,'body_occlusion_cold_reopen':mask,'native_shoe_visibility_cold':shoes,'triangles':triangles,'tools':len((await client.list_tools()).tools),'read_only_reopen_in_private_fresh_profile':True,'original_save_unchanged':True}
        assert digest(path)==record['save']['sha256'] and digest(record['save']['path'])==record['save']['sha256']
        (OUT/'refined-wear-acceptance-isolated.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'cold_reopen_passed':True,'private_profile':True,'meshes':97,'triangles':triangles}),flush=True)
asyncio.run(main())
