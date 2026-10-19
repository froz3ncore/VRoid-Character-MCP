"""Compose native evidence and record visual limitations separately from MCP success."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('D:/vroidmcp');OUT=ROOT/'projects/whale-maid/target-fit-v03';WEAR=OUT/'final-wear'
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',21)
small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16)
record=json.loads((WEAR/'named-motion-acceptance.json').read_text(encoding='utf8'))
record['available_native_clips']=record.pop('available_humanoid_clips',record.get('available_native_clips'))
record['visual_review_required']=False
record['visual_review']={'walk':'Native walking and spring movement observed; lace fragments and seams still need refinement',
    'sit':'Needs correction: front skirt folds too rigidly and rises too high; not accepted as final sitting fit'}
(WEAR/'named-motion-acceptance.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')

for case,label in [('walk','原生走路'),('sit','原生坐姿（前裙折叠待修）')]:
    folder=WEAR/('native-'+case);manifest=json.loads((folder/'motion.json').read_text(encoding='utf8'))
    sheet=Image.new('RGB',(1280,704),(28,30,36));draw=ImageDraw.Draw(sheet);frames=[];durations=[]
    for i,sample in enumerate(manifest['samples']):
        image=Image.open(folder/('frame-%02d.png'%i)).convert('RGB');frames.append(image.resize((512,512)))
        x=(i%4)*320;y=(i//4)*352;sheet.paste(image.resize((320,320)),(x,y+32))
        draw.text((x+8,y+6),'%s · 帧 %s'%(label,sample['frame']),font=small,fill='white')
        duration=manifest['samples'][i+1]['elapsed_seconds']-sample['elapsed_seconds'] if i+1<len(manifest['samples']) else .45
        durations.append(max(100,round(duration*1000)))
    sheet.save(OUT/(case+'-原生取样.png'))
    frames[0].save(OUT/(case+'-原生取样.gif'),save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2)

sheet=Image.new('RGB',(1600,462),(28,30,36));draw=ImageDraw.Draw(sheet)
paths=[ROOT/'projects/whale-maid/target-fit-v02/refined-wear-reopen-back.png',WEAR/'refined-wear-reopen-back.png',WEAR/'native-walk/frame-03.png',WEAR/'native-sit/frame-07.png']
labels=['旧腰后蝴蝶结','重建白色蝴蝶结','原生走路取样','原生坐姿 · 前裙待修']
for i,(path,label) in enumerate(zip(paths,labels)):
    im=Image.open(path).convert('RGB')
    if i<2:im=im.crop((292,350,732,790))
    sheet.paste(im.resize((400,400)),(i*400,40));draw.text((i*400+10,8),label,font=font,fill='white')
sheet.save(OUT/'蝴蝶结改进与动作验收.png')

def identity(path):return {'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
export=json.loads((WEAR/'whale_maid_bow_textured_v05.xwear.json').read_text(encoding='utf8'))
result={'date':'2026-10-15','artifacts':[identity(path) for path in [OUT/'whale_maid_target_fit_v03.blend',
    WEAR/'whale_maid_bow_textured_v05.xwear',WEAR/'whale_maid_bow_textured_v03.xroid',OUT/'white_bow_fold_texture.png',
    OUT/'蝴蝶结改进与动作验收.png',OUT/'walk-原生取样.gif',OUT/'sit-原生取样.gif']],
    'meshes':len(export['meshes']),'triangles':sum(m['triangles'] for m in export['meshes']),
    'textures':len(export['source_textures']),'omitted_degenerate_triangles':sum(m['omitted_degenerate_triangles'] for m in export['meshes']),
    'springs':{'chains':14,'joints':68,'colliders':5},'mcp_tools':47,
    'cold_blender':json.loads((OUT/'target_fit_cold_validation.json').read_text(encoding='utf8')),
    'native_save_reopen':True,'native_visual_review':record['visual_review'],'tests':{'passed':115,'skipped':1},
    'next':'Correct front skirt thigh-follow strategy and rerun the same native sitting test; shoulder seams and large lace fragments remain',
    'boundaries':['No all-animation collision-free certification','No complete character VRM export or Godot runtime acceptance']}
(OUT/'final_delivery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:result[k] for k in ['meshes','triangles','textures','omitted_degenerate_triangles','mcp_tools','native_visual_review']},ensure_ascii=False))
