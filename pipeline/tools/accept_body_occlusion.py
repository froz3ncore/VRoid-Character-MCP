"""Exercise the guarded native Body occlusion MCP and cold-save persistence."""
import argparse,asyncio,hashlib,json,sys
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_occlusion import geometry_hash
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir(exist_ok=False);native.OUT=out
    record=json.loads(a.record.read_text(encoding='utf8'));source=record['save'];base=json.loads(Path(record['base_record']).read_text(encoding='utf8'))['save']
    reference=json.loads(a.reference.read_text(encoding='utf8'));body=next(m for m in reference['base_meshes'] if m['name']=='Body');expected_hash=geometry_hash(body['source_positions'],body['triangles'])
    assert digest(source['path'])==source['sha256'];chosen=[i for i,p in enumerate(body['positions']) if p[0]>.045 and p[1]<.012 and p[2]>.045][:12];assert chosen
    async with native.client_for(Path(base['path']),'body-mask-native') as (client,call):
        await asyncio.sleep(10);status=await call('get_wear_status');status=await call('open_wear_project',{'expected_wear':status['wear_token'],'filename':Path(source['path']).name,'discard_unsaved':True});token=status['wear_token']
        before=await call('inspect_wear_body_occlusion',{'expected_wear':token});write(out/'before.json',before)
        assert before['source_geometry_sha256']==expected_hash and not before['hidden_vertices']
        changed=await call('set_wear_body_occlusion',{'expected_wear':token,'expected_occlusion_token':before['occlusion_token'],'hidden_vertices':chosen});write(out/'changed.json',changed)
        after=await call('inspect_wear_body_occlusion',{'expected_wear':token});assert after['hidden_vertices']==chosen and after['current_vertex_count']<before['current_vertex_count']
        save=await call('save_wear_project',{'expected_wear':token,'filename':'body-occlusion-probe-v01.xroid'});write(out/'saved-edit.json',{'save':save,'expected_hidden_vertices':chosen,'source_geometry_sha256':expected_hash})
        reset=await call('set_wear_body_occlusion',{'expected_wear':token,'expected_occlusion_token':after['occlusion_token'],'hidden_vertices':[]})
        restored=await call('inspect_wear_body_occlusion',{'expected_wear':token});assert not restored['hidden_vertices'] and restored['current_vertex_count']==before['current_vertex_count'];write(out/'restored-unsaved.json',restored)
    async with native.client_for(Path(base['path']),'body-mask-cold-reopen') as (_,call):
        await asyncio.sleep(10);status=await call('get_wear_status');status=await call('open_wear_project',{'expected_wear':status['wear_token'],'filename':Path(save['path']).name,'discard_unsaved':True})
        cold=await call('inspect_wear_body_occlusion',{'expected_wear':status['wear_token']});write(out/'cold-reopen.json',cold)
        assert cold['source_geometry_sha256']==expected_hash and cold['hidden_vertices']==chosen and cold['current_vertex_count']==after['current_vertex_count']
    assert digest(source['path'])==source['sha256'] and digest(save['path'])==save['sha256']
    write(out/'acceptance.json',{'passed':True,'source_unchanged':True,'source':source,'save':save,'hidden_vertices':chosen,'reset_verified':True,'cold_reopen_passed':True})
    print(json.dumps({'passed':True,'hidden_vertices':len(chosen),'cold_reopen_passed':True}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True);asyncio.run(main(p.parse_args()))
