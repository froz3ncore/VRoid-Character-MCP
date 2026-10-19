"""Prepare native review contact sheet and portable delivery manifest."""
import hashlib,json,os,zipfile
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/xwear-textured-v01'
name='whale_maid_fitted_full_v02.xwear'
native=json.loads((OUT/(name+'.native-acceptance.json')).read_text(encoding='utf8'))
export=json.loads((OUT/(name+'.json')).read_text(encoding='utf8'))
summary=native['cold_reopen']['summary']
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22);small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
sheet=Image.new('RGB',(1536,668),'#f5f6fa');draw=ImageDraw.Draw(sheet)
draw.text((20,12),'VRoid 原生换装三视图 · 保存后独立进程重开',font=font,fill='#162030')
draw.text((20,44),'73 网格 / 73 张贴图 / 68 个弹簧关节 / 5 个碰撞体',font=small,fill='#334055')
for index,(view,label) in enumerate([('front','正面'),('side','侧面'),('back','背面')]):
    source=OUT/(name+'.reopen.'+view+'.png')
    sheet.paste(Image.open(source).convert('RGB').resize((512,512),Image.Resampling.LANCZOS),(index*512,76))
    draw.text((index*512+20,592),label,font=small,fill='#162030')
draw.text((20,632),'仍叠有原模板服装；本图验证穿戴管线，不代表最终角色质量。',font=small,fill='#7a3a22')
sheet.save(OUT/'VRoid原生换装三视图.png')
cache=Path(native['edit']['save']['cache_path']);relative=cache.relative_to(ROOT/'lab-test/profile')
original=Path(os.environ['USERPROFILE'])/relative
assert not original.exists(),'The successful run created a cache outside lab-test'
with zipfile.ZipFile(OUT/'whale_maid_fitted_full_v02.xroid') as archive:
    assert archive.testzip() is None
    entries=[{'name':i.filename,'bytes':i.file_size} for i in archive.infolist()]
report={'passed':True,'native_tools':native['edit']['tools'],'meshes':summary['renderers'],
  'triangles':summary['triangles'],'textures':len(summary['textures']),
  'spring_chains_in_package':export['spring']['springs'],'instantiated_joints':len(summary['spring_joints']),
  'instantiated_colliders':len(summary['colliders']),
  'omitted_degenerate_triangles':sum(m['omitted_degenerate_triangles'] for m in export['meshes']),
  'preview':native['edit']['preview'],'source_vroid_unchanged':native['source_unchanged'],
  'save_cache_scoped_to_lab':True,'successful_run_original_profile_cache_absent':True,'xroid_entries':entries,
  'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
      for p in [OUT/name,OUT/'whale_maid_fitted_full_v02.xroid',OUT/'VRoid原生换装三视图.png']},
  'limits':['Old template clothing remains underneath','No continuous visual physics acceptance',
            'Animation time getter unavailable in this build; readiness verified by native director and animator objects',
            'No VRM export or Godot runtime acceptance']}
(OUT/'final_delivery.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('files','xroid_entries','limits')},ensure_ascii=False))
