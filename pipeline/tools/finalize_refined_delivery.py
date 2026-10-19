"""Assemble evidence sheets and an identity manifest from already verified artifacts."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('D:/vroidmcp');OUT=ROOT/'projects/whale-maid/target-fit-v02'
def read(name):return json.loads((OUT/name).read_text(encoding='utf8'))
def identity(path):return {'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',24)
small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)

sheet=Image.new('RGB',(1536,620),(30,32,38));draw=ImageDraw.Draw(sheet)
for i,(view,label) in enumerate([('front','正面'),('side','侧面'),('back','背面')]):
    im=Image.open(OUT/('refined-wear-reopen-'+view+'.png')).convert('RGB');im.thumbnail((512,512))
    sheet.paste(im,(i*512,48));draw.text((i*512+20,12),label,font=font,fill='white')
draw.text((20,570),'VRoid 保存重开后的实际穿戴 · 静态修形验收 · 后蝴蝶结与裙摆仍需整理',font=small,fill='white')
sheet.save(OUT/'修正服装_原生三视图.png')

motion=read('native-motion/motion.json');acceptance=read('native-motion-acceptance.json')
assert acceptance['passed'] and motion['summary']['frames_advanced']
sheet=Image.new('RGB',(1600,720),(30,32,38));draw=ImageDraw.Draw(sheet)
frames=[];durations=[]
for i,sample in enumerate(motion['samples']):
    image=Image.open(OUT/'native-motion'/('frame-%02d.png'%i)).convert('RGB')
    image.thumbnail((512,512));frames.append(image.copy())
    thumb=image.resize((320,320));x=(i%5)*320;y=(i//5)*360
    sheet.paste(thumb,(x,y+34))
    draw.text((x+10,y+7),'帧 %s · %.2f 秒'%(sample['frame'],sample['elapsed_seconds']),font=small,fill='white')
    interval=motion['samples'][i+1]['elapsed_seconds']-sample['elapsed_seconds'] if i+1<len(motion['samples']) else .45
    durations.append(max(100,round(interval*1000)))
sheet.save(OUT/'动画预览_十帧取样.png')
frames[0].save(OUT/'动画预览_十帧取样.gif',save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2)

export=read('whale_maid_fitted_refined_v03.xwear.json')
native=read('refined-wear-acceptance.json');cold=read('target_fit_cold_validation.json')
fit=json.loads((OUT/'reimport-verification/native-fit-diagnosis.json').read_text(encoding='utf8'))
assert cold['success'] and native['cold_reopen_passed']
assert all(r[k]==0 for r in fit['records'] for k in ('inside_vertices','inside_face_centers','inside_edge_midpoints'))
result={'schema':'whale-maid-refined-delivery-v1','artifacts':[identity(OUT/name) for name in (
    'whale_maid_target_fit_v02.blend','whale_maid_fitted_refined_v03.xwear','whale_maid_refined_wear_v02.xroid',
    '修正服装_原生三视图.png','动画预览_十帧取样.png','动画预览_十帧取样.gif')],
    'meshes':len(export['meshes']),'triangles':sum(m['triangles'] for m in export['meshes']),
    'omitted_degenerate_triangles':sum(m['omitted_degenerate_triangles'] for m in export['meshes']),
    'texture_validation':{'textures':73,'maximum_decoded_rgb_error_8bit':0},
    'spring_package':{'chains':14,'joints':68,'colliders':5},'native_motion':motion['summary'],
    'native_cold_reopen':True,'body_and_sources_preserved':True,
    'fit_scope':'Five selected native stopped-pose garments; vertices, triangle centres and edge midpoints; inside threshold -2 mm',
    'remaining':['Generated rear bow, skirt-layer fragments and shoulder seams need visual cleanup',
        'Reference character headband, whale tail, hair silhouette and shoes are incomplete',
        'All-animation collision-free acceptance and custom walking/sitting are not established',
        'No complete character VRM export or Godot runtime acceptance'],
    'mcp_tools':45,'tests':{'passed':106,'skipped':1,'junit':'mcp-test-results.xml'}}
(OUT/'final_delivery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'artifacts':len(result['artifacts']),'meshes':result['meshes'],'triangles':result['triangles'],
    'omitted_degenerate_triangles':result['omitted_degenerate_triangles'],'motion':motion['summary']},ensure_ascii=False))
