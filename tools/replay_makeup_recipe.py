"""Preflight every makeup region before replaying a recipe into an isolated lab.

No input model is overwritten. A failed preflight applies no brush layers;
failed edits never publish a saved candidate. Explicit --apply --bake-colors
--save-as creates ONE new .vroid, then verifies its layers in a new process.
No native writes or uncertain saves are automatically retried.
"""
from __future__ import annotations
import argparse,asyncio,hashlib,json,os,re,sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from vroid_mcp.makeup_tools import CanvasMark
from vroid_mcp.bounded_paint import decode_rgba_png
from vroid_mcp.texture_layer_state import state_digest

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def error_summary(error):
    children=getattr(error,'exceptions',None)
    return '; '.join(error_summary(child) for child in children) if children else str(error)
def read_recipe(path):
    recipe=json.loads(path.read_text(encoding='utf8'))
    if recipe.get('schema')!='vroid-bounded-makeup-recipe-v1':raise ValueError('Unknown recipe schema')
    if not re.fullmatch(r'[a-f0-9]{64}',recipe.get('reference_base_sha256','')):raise ValueError('Recipe requires an exact input-model SHA256')
    parts=recipe.get('parts');normalized=[];names=set();regions=set()
    if not isinstance(parts,list) or not 1<=len(parts)<=8:raise ValueError('Recipe must contain 1..8 parts')
    for number,part in enumerate(parts):
        region=part.get('part',part.get('region_part'));options=part.get('mask_options',{});area=options.get('area',part.get('area','region'))
        if region not in ('Cheek','MouthLine','Eyelid','Eyebrow','FaceSkin') or area not in ('region','under_eye') or (region=='FaceSkin')!=(area=='under_eye'):raise ValueError('Unsupported recipe region/area')
        if region in regions:raise ValueError('Use one combined marks entry per region')
        regions.add(region)
        if set(options)-{'area','alpha_threshold','padding_px'}:raise ValueError('Unknown mask option')
        dims=part.get('image_dimensions');mask_hash=part.get('expected_mask_png_sha256','')
        if not isinstance(dims,list) or len(dims)!=2 or any(type(v) is not int or not 1<=v<=4096 for v in dims) or dims[0]*dims[1]>4194304 or not re.fullmatch(r'[a-f0-9]{64}',mask_hash):raise ValueError('Recipe requires bounded dimensions and an exact mask hash')
        marks=part.get('marks')
        if not isinstance(marks,list) or not 1<=len(marks)<=32:raise ValueError('Recipe must contain 1..32 marks per part')
        marks=[CanvasMark.model_validate(m).model_dump() for m in marks]
        name=part.get('layer_name',f'MCP_recipe_{region}_{number+1}')
        opacity=part.get('opacity',1.)
        if not isinstance(name,str) or not 1<=len(name)<=80 or name in names or type(opacity) not in (int,float) or not 0<=opacity<=1:raise ValueError('Invalid or duplicate recipe layer settings')
        names.add(name)
        alpha=options.get('alpha_threshold',1);padding=options.get('padding_px',0)
        if type(alpha) is not int or not 1<=alpha<=255 or type(padding) is not int or not 0<=padding<=16:raise ValueError('Invalid recipe mask parameters')
        normalized.append({'part':region,'area':area,'image_dimensions':dims,'mask_hash':mask_hash,'alpha_threshold':alpha,'padding_px':padding,'marks':marks,'layer_name':name,'opacity':opacity,'reference_layer_name':part.get('reference_layer_name')})
    return recipe,normalized

@asynccontextmanager
async def client_for(lab,model,out,label):
    env=dict(os.environ,TEMP=str(out/'temp'),TMP=str(out/'temp'),VROID_MCP_CLEAR_CLOSET_KEY='0')
    (out/'temp').mkdir(exist_ok=True)
    params=StdioServerParameters(command=sys.executable,args=['-m','vroid_mcp.server','--lab',str(lab),'--model',str(model)],cwd=str(PROJECT),env=env)
    with (out/(label+'.log')).open('w',encoding='utf8') as log:
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=240)) as client:
                async def call(name,args=None):
                    result=await client.call_tool(name,args or {})
                    if result.isError:raise RuntimeError(name+': '+str(result.content))
                    return result.structuredContent or json.loads(result.content[0].text)
                await client.initialize();yield call

async def replay(args,recipe,parts,report):
    source_hash=sha(args.model)
    if source_hash!=recipe['reference_base_sha256']:raise ValueError('Input-model hash does not match the recipe reference; retargeting requires a new recipe')
    prepared=[];applied=[];report['saved']=None
    async with client_for(args.lab,args.model,args.out,'preflight-and-apply') as call:
        token=(await call('list_face_params'))['model_token']
        # All masks/dimensions/source layers and previews must succeed BEFORE any brush write.
        for part in parts:
            regions=(await call('list_texture_regions',{'expected_model':token}))['regions'];matches=[r for r in regions if r['part']==part['part']]
            if len(matches)!=1:raise ValueError('Missing or ambiguous region: '+part['part'])
            rid=matches[0]['region_id'];await call('open_texture_editor',{'expected_model':token,'region_id':rid,'bake_colors':args.bake_colors})
            try:
                layers=(await call('list_texture_layers',{'expected_model':token,'region_id':rid}))['layers']
                if any(l['Name']==part['layer_name'] for l in layers):raise ValueError('Recipe layer already exists; refusing duplicate application')
                references=[l for l in layers if l['Name']==part['reference_layer_name']] if part['reference_layer_name'] else layers
                if len(references)!=1:raise ValueError('Select one unambiguous reference_layer_name in the recipe for '+part['part'])
                mask=await call('export_makeup_region_mask',{'expected_model':token,'region_id':rid,'layer_id':references[0]['layer_id'],'alpha_threshold':part['alpha_threshold'],'padding_px':part['padding_px'],'area':part['area']})
                if [mask['width'],mask['height']]!=part['image_dimensions'] or mask['mask_png_sha256']!=part['mask_hash']:raise ValueError('Recipe mask or dimensions mismatch for '+part['part'])
                brush={'expected_model':token,'mask_id':mask['mask_id'],'expected_mask_sha256':mask['manifest_sha256'],'marks':part['marks']}
                preview=await call('preview_makeup_marks',brush)
                originals={l['layer_id']:(await call('export_texture_layer',{'expected_model':token,'region_id':rid,'layer_id':l['layer_id']}))['sha256'] for l in layers}
                prepared.append({'part':part,'rid':rid,'brush':brush,'preview':preview,'layers':layers,'originals':originals})
                report['preflight'].append({'part':part['part'],'mask_hash':mask['mask_png_sha256'],'dimensions':part['image_dimensions'],'preview_path':preview['path'],'passed':True})
            finally:await call('close_texture_editor',{'expected_model':token})
        report['all_parts_preflight_passed']=True
        if not args.apply:return
        for entry in prepared:
            part=entry['part'];rid=entry['rid'];await call('open_texture_editor',{'expected_model':token,'region_id':rid})
            try:
                current=(await call('list_texture_layers',{'expected_model':token,'region_id':rid}))['layers']
                if [state_digest(l) for l in current]!=[state_digest(l) for l in entry['layers']]:raise ValueError('Layer metadata changed after preflight')
                painted=await call('paint_makeup_marks',{**entry['brush'],'layer_name':part['layer_name'],'opacity':part['opacity']});layer=painted['native_import']['layer']
                exported=await call('export_texture_layer',{'expected_model':token,'region_id':rid,'layer_id':layer['layer_id']})
                if decode_rgba_png(Path(exported['path']).read_bytes())!=decode_rgba_png(Path(entry['preview']['path']).read_bytes()):raise ValueError('Native layer pixels differ from preview')
                for lid,expected in entry['originals'].items():
                    if (await call('export_texture_layer',{'expected_model':token,'region_id':rid,'layer_id':lid}))['sha256']!=expected:raise ValueError('An existing layer changed')
                applied.append({'part':part['part'],'layer_name':part['layer_name'],'png_sha256':exported['sha256'],'opacity':part['opacity'],'history_commands':painted['native_import']['history_command_count']})
                report['applied_parts']=list(applied)
            finally:await call('close_texture_editor',{'expected_model':token})
        report['save_attempted']=True
        report['saved']=await call('save_as',{'expected_model':token,'filename':args.save_as})
    if sha(args.model)!=source_hash:raise ValueError('Source model changed')
    saved=report['saved'];assert sha(saved['path'])==saved['sha256']
    async with client_for(args.lab,Path(saved['path']),args.out,'cold-verification') as call:
        token=(await call('list_face_params'))['model_token']
        for item in applied:
            regions=(await call('list_texture_regions',{'expected_model':token}))['regions'];rid=next(r['region_id'] for r in regions if r['part']==item['part'])
            layers=(await call('list_texture_layers',{'expected_model':token,'region_id':rid}))['layers'];matches=[l for l in layers if l['Name']==item['layer_name']]
            if len(matches)!=1 or abs(matches[0]['Opacity']-item['opacity'])>1e-6 or matches[0]['Visibility'] is not True:raise ValueError('Reopened layer metadata mismatch')
            exported=await call('export_texture_layer',{'expected_model':token,'region_id':rid,'layer_id':matches[0]['layer_id']})
            if exported['sha256']!=item['png_sha256']:raise ValueError('Reopened layer pixels mismatch')
    report['cold_verification_passed']=True;report['source_unchanged']=sha(args.model)==source_hash

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('lab','model','recipe','out'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--bake-colors',action='store_true');parser.add_argument('--save-as',default='');args=parser.parse_args(argv)
    args.lab=args.lab.resolve();args.model=args.model.resolve();args.out=args.out.resolve()
    if args.out.exists():parser.error('Output directory must be new')
    if not args.model.is_file() or args.model.suffix.lower()!='.vroid' or args.lab not in args.model.parents:parser.error('Use an existing .vroid physically inside the target lab')
    if args.apply and (not args.bake_colors or not args.save_as or Path(args.save_as).name!=args.save_as or not args.save_as.endswith('.vroid')):parser.error('Applying requires --bake-colors and --save-as <new-filename.vroid>')
    if args.apply and (args.lab/'saves'/args.save_as).exists():parser.error('Candidate filename already exists')
    args.out.mkdir(parents=True);report={'schema':'vroid-makeup-replay-v1','ok':False,'saved':None,'preflight':[],'applied_parts':[],'save_attempted':False,'apply_requested':args.apply,'color_baking_requested':args.bake_colors}
    source_hash=sha(args.model)
    try:
        recipe,parts=read_recipe(args.recipe);asyncio.run(replay(args,recipe,parts,report))
        report['source_unchanged']=sha(args.model)==source_hash
        if not report['source_unchanged']:raise ValueError('Source model changed')
        report['ok']=True;code=0
    except Exception as error:report['error']=error_summary(error);report['source_unchanged']=sha(args.model)==source_hash;code=1
    report['exit_code']=code
    (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'ok':report['ok'],'saved':report['saved'],'report':str(args.out/'report.json'),'error':report.get('error')},ensure_ascii=False));return code

if __name__=='__main__':raise SystemExit(main())
