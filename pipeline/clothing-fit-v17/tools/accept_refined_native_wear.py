"""Import the refined garment once; save and verify in a fresh native MCP process."""
import asyncio,hashlib,json,shutil,sys,uuid
from pathlib import Path
import clean_native_clothing as native

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'projects/whale-maid/target-fit-v02'
native.OUT=OUT
PACKAGE=OUT/'whale_maid_fitted_refined_v03.xwear'
BASE_RECORD=ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json'
BASE=json.loads(BASE_RECORD.read_text(encoding='utf8'))['save']
EDIT=OUT/'refined-wear-edit.json'
DELIVERED_NAME='whale_maid_refined_wear_v02.xroid'
INITIAL_SETTLE_SECONDS=0.
GEOMETRY_ONLY=False
BODY_OCCLUSION_PLAN=None
STARTUP_MODEL=None
HIDE_NATIVE_SHOES=False
SOURCE_WEAR_RECORD=None

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')

async def main():
    assert digest(BASE['path'])==BASE['sha256']
    manifest=json.loads(PACKAGE.with_suffix('.xwear.json').read_text(encoding='utf8'))
    package_hash=digest(PACKAGE)
    expected_triangles=sum(m['triangles'] for m in manifest['meshes'])
    mask_plan=json.loads(BODY_OCCLUSION_PLAN.read_text(encoding='utf8')) if BODY_OCCLUSION_PLAN else None
    source_wear=json.loads(SOURCE_WEAR_RECORD.read_text(encoding='utf8')) if SOURCE_WEAR_RECORD else None
    if source_wear:
        assert source_wear.get('passed') and source_wear.get('cold_reopen_passed')
        assert source_wear['package_sha256']==package_hash and digest(source_wear['save']['path'])==source_wear['save']['sha256']
    if '--reopen-only' not in sys.argv:
        assert not EDIT.exists(),'A saved edit exists: inspect it, then use --reopen-only'
        # Independent candidates may share a display filename. Content-addressed
        # staging prevents importing a previous candidate's native cached package.
        staged=native.LAB/'saves'/(PACKAGE.stem+'-'+package_hash[:12]+'.xwear')
        if not staged.exists():shutil.copy2(PACKAGE,staged)
        assert digest(staged)==package_hash
        async with native.client_for(STARTUP_MODEL or Path(BASE['path']),'refined-wear-edit') as (_,call):
            await call('list_face_params')
            if INITIAL_SETTLE_SECONDS:await asyncio.sleep(INITIAL_SETTLE_SECONDS)
            status=await call('get_wear_status')
            open_path=source_wear['save']['path'] if source_wear else BASE['path']
            status=await call('open_wear_project',{'filename':Path(open_path).name,'expected_wear':status['wear_token'],'discard_unsaved':True})
            if not source_wear:status=await call('import_xwear',{'filename':staged.name,'expected_wear':status['wear_token']})
            native_shoe_result=None
            if HIDE_NATIVE_SHOES:
                shoe_state=await call('inspect_wear_native_shoes',{'expected_wear':status['wear_token']})
                native_shoe_result=await call('set_wear_native_shoes_visible',{'expected_wear':status['wear_token'],'expected_visibility_token':shoe_state['visibility_token'],'visible':False})
                assert not native_shoe_result['visible'] and native_shoe_result['current_triangle_count']==0
            mask_result=None
            if mask_plan:
                mask_state=await call('inspect_wear_body_occlusion',{'expected_wear':status['wear_token']})
                assert mask_state['source_geometry_sha256']==mask_plan['source_geometry_sha256']
                assert mask_state['default_vertex_count']==mask_plan['default_vertex_count'] and not mask_state['hidden_vertices']
                mask_result=await call('set_wear_body_occlusion',{'expected_wear':status['wear_token'],'expected_occlusion_token':mask_state['occlusion_token'],'hidden_vertices':mask_plan['hidden_vertices']})
            snap=await call('get_wear_snapshot',{'expected_wear':status['wear_token']})
            save=await call('save_wear_project',{'filename':'whale-maid-refined-'+uuid.uuid4().hex+'.xroid','expected_wear':status['wear_token']})
            write(EDIT,{'save':save,'edit':snap,'package_sha256':package_hash,'base_record':str(BASE_RECORD),
                'body_occlusion_plan':str(BODY_OCCLUSION_PLAN) if BODY_OCCLUSION_PLAN else None,'body_occlusion_plan_sha256':digest(BODY_OCCLUSION_PLAN) if BODY_OCCLUSION_PLAN else None,'body_occlusion_result':mask_result,
                'hide_native_shoes':HIDE_NATIVE_SHOES,'native_shoe_visibility_result':native_shoe_result,
                'source_wear_save':source_wear['save'] if source_wear else None})
    record=json.loads(EDIT.read_text(encoding='utf8'))
    assert record.get('base_record',str(BASE_RECORD))==str(BASE_RECORD),'Saved edit uses another base record'
    assert record['package_sha256']==package_hash and digest(record['save']['path'])==record['save']['sha256']
    assert record.get('body_occlusion_plan_sha256')==(digest(BODY_OCCLUSION_PLAN) if BODY_OCCLUSION_PLAN else None),'Saved edit uses another occlusion plan'
    assert record.get('hide_native_shoes',False)==HIDE_NATIVE_SHOES,'Saved edit uses another native shoe visibility setting'
    assert record.get('source_wear_save')==(source_wear['save'] if source_wear else None),'Saved edit uses another source assembly'
    async with native.client_for(STARTUP_MODEL or Path(BASE['path']),'refined-wear-reopen') as (client,call):
        await call('list_face_params')
        if INITIAL_SETTLE_SECONDS:await asyncio.sleep(INITIAL_SETTLE_SECONDS)
        status=await call('get_wear_status')
        status=await call('open_wear_project',{'filename':Path(record['save']['path']).name,'expected_wear':status['wear_token'],'discard_unsaved':True})
        token=status['wear_token'];snap=await call('get_wear_snapshot',{'expected_wear':token})
        if HIDE_NATIVE_SHOES:
            cold_shoes=await call('inspect_wear_native_shoes',{'expected_wear':token})
            assert not cold_shoes['visible'] and cold_shoes['current_triangle_count']==0
            record['native_shoe_visibility_cold']=cold_shoes
            record['native_shoe_hidden_cold_passed']=True
        if mask_plan:
            cold_mask=await call('inspect_wear_body_occlusion',{'expected_wear':token})
            assert cold_mask['hidden_vertices']==mask_plan['hidden_vertices'] and cold_mask['source_geometry_sha256']==mask_plan['source_geometry_sha256']
            record['body_occlusion_cold_reopen']=cold_mask
        assert snap['base_model']==record['edit']['base_model']
        assert len(snap['items'])==1
        item=snap['items'][0]
        meshes=[r for inst in item['instances'] for r in inst['renderers']]
        assert len(meshes)==len(manifest['meshes']) and sum(r['triangles'] for r in meshes)==expected_triangles
        assert all(sum(bool(b['spring_joint']) for b in s['bones'])==manifest['spring']['joints'] and len(s['colliders'])==manifest['spring']['colliders'] for s in item['skeletons'])
        assert any(r['name']=='Body' and r['active'] and r['enabled'] for r in snap['base_model']['renderers'])
        capture=None if GEOMETRY_ONLY else await call('capture_wear_review',{'expected_wear':token,'views':['front','side','back'],'size':1024})
        names=[r['name'] for r in meshes if r['name'].startswith(('FIT_T001','FIT_T007','FIT_T008','FIT_T011','FIT_T022'))]
        assert len(names)==5
        ref=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names})
        ref_dest=OUT/'actual_refined_wear_reference.json';assert not ref_dest.exists();shutil.copy2(ref['path'],ref_dest)
        assert digest(ref_dest)==ref['sha256']
        record.update(passed=True,reopen=snap,reopen_capture=capture,reference=ref,tools=len((await client.list_tools()).tools),triangles=expected_triangles)
    target=OUT/DELIVERED_NAME;assert not target.exists();shutil.copy2(record['save']['path'],target)
    assert digest(BASE['path'])==BASE['sha256'] and digest(PACKAGE)==package_hash
    if source_wear:assert digest(source_wear['save']['path'])==source_wear['save']['sha256']
    record.update(base_unchanged=True,package_unchanged=True,cold_reopen_passed=True,delivered_xroid=str(target),image_capture_skipped=GEOMETRY_ONLY)
    write(OUT/'refined-wear-acceptance.json',record)
    print(json.dumps({'passed':True,'meshes':len(manifest['meshes']),'triangles':expected_triangles,'tools':record['tools'],'xroid':str(target)},ensure_ascii=False),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    parser.add_argument('--package',default=PACKAGE.name);parser.add_argument('--delivered-name',default=DELIVERED_NAME)
    parser.add_argument('--reopen-only',action='store_true')
    parser.add_argument('--initial-settle-seconds',type=float,default=0.)
    parser.add_argument('--base-record',type=Path,default=ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json')
    parser.add_argument('--geometry-only',action='store_true',help='Use real snapshot/reference checks without screenshots')
    parser.add_argument('--body-occlusion-plan',type=Path,help='Explicit guarded original Body vertex mask for this independent assembly')
    parser.add_argument('--startup-model',type=Path,help='Optional separate owned .vroid to initialize before opening the explicit target base')
    parser.add_argument('--hide-native-shoes',action='store_true',help='Hide only guarded native shoe Cloth; keep its template and Foot shape')
    parser.add_argument('--source-wear-record',type=Path,help='Start from an already cold-validated assembly with this exact package, without reimporting')
    args=parser.parse_args()
    OUT=args.out.resolve();PACKAGE=OUT/args.package;EDIT=OUT/'refined-wear-edit.json';DELIVERED_NAME=args.delivered_name;native.OUT=OUT
    INITIAL_SETTLE_SECONDS=args.initial_settle_seconds
    GEOMETRY_ONLY=args.geometry_only
    HIDE_NATIVE_SHOES=args.hide_native_shoes
    SOURCE_WEAR_RECORD=args.source_wear_record.resolve() if args.source_wear_record else None
    if SOURCE_WEAR_RECORD:assert SOURCE_WEAR_RECORD.is_relative_to(ROOT/'projects/whale-maid') and SOURCE_WEAR_RECORD.is_file()
    BODY_OCCLUSION_PLAN=args.body_occlusion_plan.resolve() if args.body_occlusion_plan else None
    STARTUP_MODEL=args.startup_model.resolve() if args.startup_model else None
    if STARTUP_MODEL:assert STARTUP_MODEL.is_relative_to(native.LAB) and STARTUP_MODEL.suffix=='.vroid' and STARTUP_MODEL.is_file()
    if BODY_OCCLUSION_PLAN:assert BODY_OCCLUSION_PLAN.is_relative_to(ROOT/'projects/whale-maid') and BODY_OCCLUSION_PLAN.is_file()
    BASE_RECORD=args.base_record.resolve()
    assert BASE_RECORD.is_relative_to(ROOT/'projects/whale-maid')
    base_record=json.loads(BASE_RECORD.read_text(encoding='utf8'))
    assert base_record['cold_reopen_passed'] and base_record['passed']
    BASE=base_record['save']
    assert 0<=INITIAL_SETTLE_SECONDS<=10
    assert OUT.is_relative_to(ROOT/'projects/whale-maid') and PACKAGE.parent==OUT
    assert Path(DELIVERED_NAME).name==DELIVERED_NAME and DELIVERED_NAME.endswith('.xroid')
    asyncio.run(main())
