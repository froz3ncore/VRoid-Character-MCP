"""Make and reopen an isolated native white-tights/Mary-Jane base."""
import asyncio,hashlib,json,shutil,uuid
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'projects/whale-maid/accessory-refinement-v02/footwear-base'
BASE=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']
CHOICES={'Shoes':'clothing/Shoes/none',
         'Socks':'clothing/Socks/bc8a75de2aca03eabfc21ff9215322a0a00f9cbc.transferablegroup'}
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,data):
    with (OUT/name).open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
async def main():
    OUT.mkdir(exist_ok=True);native.OUT=OUT
    assert not (OUT/'base-edit.json').exists(),'Saved edit exists; inspect and reopen it without applying again'
    assert digest(BASE['path'])==BASE['sha256']
    async with native.client_for(Path(BASE['path']),'footwear-edit') as (_,call):
        await asyncio.sleep(5);token=(await call('list_face_params'))['model_token']
        protected={d:await native.parameters(call,d) for d in ('face','body','colors')}
        selected={c:await native.selected(call,c) for c in ('InnerTop','InnerBottom','Onepiece','ArmAccessory')}
        applied=[]
        for category,ident in CHOICES.items():
            catalog=await call('list_clothing_presets',{'category':category,'limit':200})
            assert any(p['id']==ident for p in catalog['presets'])
            applied.append(await call('apply_clothing_preset',{'expected_model':token,'preset_id':ident}))
        params=await call('list_clothing_params');write('parameters-after-presets.json',params)
        # Keep the native foot anatomy; actual reference shoes are independent
        # fitted meshes in the XWear package, avoiding a flat preset substitute.
        changes=[];updated=None
        assert protected=={d:await native.parameters(call,d) for d in protected}
        assert selected=={c:await native.selected(call,c) for c in selected}
        for c,preset in CHOICES.items():assert await native.selected(call,c)==([] if preset.endswith('/none') else [preset])
        capture=await call('capture_review',{'expected_model':token,'views':['feet_front','feet_right','feet_back','legs_front'],'size':1024,'quality':'high'})
        # Ordinary capture_review returns paths; copy its native originals.
        for view,row in capture['images'].items():shutil.copy2(row['path'],OUT/('edited-'+view+'.png'))
        save=await call('save_as',{'expected_model':token,'filename':'whale-maid-maryjane-tights-'+uuid.uuid4().hex+'.vroid'})
        record={'source_base':BASE,'choices':CHOICES,'applied':applied,'heel_changes':changes,'heel_result':updated,'protected':protected,'protected_categories':selected,'save':save,'capture':capture}
        write('base-edit.json',record)
    async with native.client_for(Path(save['path']),'footwear-reopen') as (_,call):
        await asyncio.sleep(5);token=(await call('list_face_params'))['model_token']
        assert protected=={d:await native.parameters(call,d) for d in protected}
        assert selected=={c:await native.selected(call,c) for c in selected}
        for c,preset in CHOICES.items():assert await native.selected(call,c)==([] if preset.endswith('/none') else [preset])
        params=await call('list_clothing_params')
        capture=await call('capture_review',{'expected_model':token,'views':['feet_front','feet_right','feet_back','legs_front'],'size':1024,'quality':'high'})
        for view,row in capture['images'].items():shutil.copy2(row['path'],OUT/('reopened-'+view+'.png'))
        body=await call('capture_body_reference',{'expected_model':token,'label':'White sheer tights base; native shoes removed for custom fitted Mary Janes'})
        shutil.copy2(body['path'],OUT/'body-reference.json')
    assert digest(BASE['path'])==BASE['sha256'] and digest(save['path'])==save['sha256']
    shutil.copy2(save['path'],OUT/'whale_maid_maryjane_tights_base.vroid')
    record.update(passed=True,cold_reopen_passed=True,original_base_preserved=True,body_reference=body,reopen_capture=capture)
    write('base-acceptance.json',record)
    print(json.dumps({'passed':True,'save':save,'out':str(OUT)},ensure_ascii=False),flush=True)
if __name__=='__main__':asyncio.run(main())
