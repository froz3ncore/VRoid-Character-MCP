"""Native MCP shoe-template measurement and saved replacement/cold reopen."""
import argparse,asyncio,hashlib,json,math,shutil,uuid
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
BASE_RECORD=ROOT/'projects/whale-maid/accessory-refinement-v02/footwear-base/base-acceptance.json'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def describe(data):
    foot=next(m for m in data['meshes'] if m['name']=='Foot');matrix=foot['world_matrix']
    points=[[sum(matrix[i][j]*p[j] for j in range(3))+matrix[i][3] for i in range(3)] for p in foot['positions']]
    nodes={n['name']:n for n in data['nodes']};out={}
    for side in ['L','R']:
        selected=[p for p in points if p[0]*(1 if side=='R' else -1)>0]
        zmin=min(p[2] for p in selected);zmax=max(p[2] for p in selected);length=zmax-zmin
        def band(lo,hi):
            ps=[p for p in selected if lo<=p[2]<=hi];ys=sorted(p[1] for p in ps)
            return {'vertices':len(ps),'min_y_mm':ys[0]*1000,'lower_quartile_y_mm':ys[len(ys)//4]*1000,'median_y_mm':ys[len(ys)//2]*1000}
        heel=band(zmin,zmin+length*.25);toe=band(zmax-length*.25,zmax);arch=band(zmin+length*.35,zmin+length*.65)
        bones={name:[n['world_matrix'][i][3] for i in range(3)] for name,n in nodes.items() if name in ['J_Bip_'+side+'_Foot','J_Bip_'+side+'_ToeBase']}
        out[side]={'heel':heel,'toe':toe,'arch':arch,'heel_minus_toe_min_mm':heel['min_y_mm']-toe['min_y_mm'],'bones':bones}
    return {'height_cm':data['height_cm'],'foot_vertices':len(points),'foot_triangles':len(foot['triangles'])//3,'sides':out}

async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists();out.mkdir(parents=True);native.OUT=out
    base=json.loads(BASE_RECORD.read_text(encoding='utf8'))['save'];assert digest(base['path'])==base['sha256']
    async with native.client_for(Path(base['path']),'high-heel-template') as (client,call):
        token=(await call('list_face_params'))['model_token'];await asyncio.sleep(5)
        catalog=await call('list_shoe_templates',{'expected_model':token});write(out/'catalog.json',catalog)
        print(json.dumps({'template_count':len(catalog['templates']),'catalog':str(out/'catalog.json')},ensure_ascii=False),flush=True)
        if a.mode=='catalog':return
        assert a.template_id in {t['id'] for t in catalog['templates']}
        protected={d:await native.parameters(call,d) for d in ['face','body','colors']};rows=[]
        async def capture(label):
            ref=await call('capture_body_reference',{'expected_model':token,'label':label});dest=out/(label+'.json');shutil.copy2(ref['path'],dest)
            row={'case':label,'reference':str(dest),**describe(json.loads(dest.read_text(encoding='utf8')))};rows.append(row);print(json.dumps({'case':label,'height_cm':row['height_cm'],'R':row['sides']['R']},ensure_ascii=False),flush=True)
        await capture('barefoot')
        added=await call('add_shoe_template',{'expected_model':token,'template_id':a.template_id});write(out/'native-template-add.json',added);assert added['ok'],added
        listing=await call('list_clothing_params');write(out/'heel-parameters.json',listing)
        await capture('native-heel-default')
        review=await call('capture_review',{'expected_model':token,'views':['feet_right'],'size':768,'quality':'high'})
        for view,row in review['images'].items():shutil.copy2(row['path'],out/('native-heel-'+view+'.png'))
        if a.high is not None:
            matches=[p for p in listing['parameters'] if p.get('semantic_key','').endswith('Shoes.High') and not p.get('alias_of')]
            assert len(matches)==1,matches
            result=await call('set_clothing_params',{'expected_model':token,'changes':[{'id':matches[0]['id'],'value':a.high}]});write(out/'high-change.json',result)
            await capture('native-heel-high')
        with_heel=await call('save_as',{'expected_model':token,'filename':'native-high-heel-template-'+uuid.uuid4().hex+'.vroid'});write(out/'heel-save.json',with_heel)
        cleared=await call('apply_clothing_preset',{'expected_model':token,'preset_id':'clothing/Shoes/none'});write(out/'clear-native-shoes.json',cleared)
        await capture('removed-same-process')
        assert protected=={d:await native.parameters(call,d) for d in protected}
        save=await call('save_as',{'expected_model':token,'filename':'native-heel-removed-'+uuid.uuid4().hex+'.vroid'});write(out/'removed-save.json',save)
        write(out/'measurement.json',{'source':base,'template_id':a.template_id,'added':added,'cases':rows,'heel_save':with_heel,'removed_save':save,'protected_parameters_preserved':True,'native_tools':len((await client.list_tools()).tools)})
    if a.mode=='measure':
        assert digest(base['path'])==base['sha256']
        return
    # A fresh editor reads the removed-shoes save before entering Dress-up.
    async with native.client_for(Path(save['path']),'high-heel-cold-reopen') as (_,call):
        token=(await call('list_face_params'))['model_token'];await asyncio.sleep(5)
        ref=await call('capture_body_reference',{'expected_model':token,'label':'removed-shoes-cold-reopen'});dest=out/'removed-cold-reopen.json';shutil.copy2(ref['path'],dest)
        cold=describe(json.loads(dest.read_text(encoding='utf8')));write(out/'cold-reopen-measurement.json',cold)
        assert protected=={d:await native.parameters(call,d) for d in protected}
        assert await native.selected(call,'Shoes')==[]
        state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(save['path']).name,'discard_unsaved':True})
        package=ROOT/'projects/whale-maid/accessory-refinement-v02/tripo-shoe-repair-v11b/whale_maid_tripo_shoe_repair_v11.xwear';package_hash=digest(package);staged=native.LAB/'saves'/(package.stem+'-'+package_hash[:12]+'.xwear');assert digest(staged)==package_hash
        state=await call('import_xwear',{'expected_wear':state['wear_token'],'filename':staged.name});snapshot=await call('get_wear_snapshot',{'expected_wear':state['wear_token']});item=snapshot['items'][0]
        names=[r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith('FIT_ACCESSORY_Shoe_')];assert len(names)==8
        ref=await call('capture_wear_reference',{'expected_wear':state['wear_token'],'item_id':item['id'],'mesh_names':names,'include_base_meshes':True,'base_mesh_names':['Body','Foot']});shutil.copy2(ref['path'],out/'tripo-wear-reference.json')
        assembled=await call('save_wear_project',{'expected_wear':state['wear_token'],'filename':'native-heel-tripo-replacement-'+uuid.uuid4().hex+'.xroid'});write(out/'tripo-save.json',assembled)
    async with native.client_for(Path(save['path']),'high-heel-tripo-cold-reopen') as (_,call):
        await call('list_face_params');state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(assembled['path']).name,'discard_unsaved':True});snapshot=await call('get_wear_snapshot',{'expected_wear':state['wear_token']});item=snapshot['items'][0]
        names=[r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith('FIT_ACCESSORY_Shoe_')]
        report=await call('inspect_wear_fit_context',{'expected_wear':state['wear_token'],'item_id':item['id'],'mesh_names':names,'region':'feet','sample_limit':128})
        for source,target in [(report['raw_reference']['path'],'tripo-cold-reference.json'),(report['report_path'],'tripo-fit.json'),(report['debug_glb']['path'],'tripo-fit.glb')]:shutil.copy2(source,out/target)
    assert digest(base['path'])==base['sha256'] and digest(package)==package_hash
    write(out/'acceptance.json',{'passed':True,'scope':'Native template foot shape, removal, .vroid cold reopen and Tripo replacement .xroid cold reopen; not a shoe-fit or animation success certificate.','source_unchanged':True,'template_id':a.template_id,'base_cold_reopen':cold,'save':assembled,'wear_fit_report':str(out/'tripo-fit.json')})
    print(json.dumps({'passed':True,'out':str(out),'R_cold':cold['sides']['R']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--mode',choices=['catalog','measure','test'],default='catalog');p.add_argument('--template-id');p.add_argument('--high',type=float);asyncio.run(main(p.parse_args()))
