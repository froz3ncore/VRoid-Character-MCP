from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageChops
import json

OUT=Path(r'D:\vroidmcp\projects\whale-maid\tripo-source\cloth-springs-v01')
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16)
files=sorted((OUT/'preview-frames').glob('*.png'))
assert len(files)==41
frames=[]
for p in files:
    source=Image.open(p).convert('RGB')
    im=Image.new('RGB',(source.width,source.height+66),(31,37,44))
    im.paste(source,(0,40));d=ImageDraw.Draw(im)
    d.text((18,6),'服装弹簧骨 · VRM 求解器实际输出',font=font,fill='white')
    d.text((18,source.height+43),f'正面 / 背面    帧 {int(p.stem):03d}/121    仅服装物理预览；未适配 VRoid 身体',font=small,fill=(205,216,230))
    frames.append(im)
palette=frames[0].quantize(colors=256)
gifframes=[f.quantize(palette=palette) for f in frames]
gifpath=OUT/'服装弹簧骨预览.gif'
gifframes[0].save(gifpath,save_all=True,append_images=gifframes[1:],duration=[100]*40+[700],loop=0,optimize=False,disposal=2)
sheet=Image.new('RGB',(1000,800),(31,37,44));draw=ImageDraw.Draw(sheet)
for tile,index in enumerate([0,10,20,30]):
    frame=frames[index].resize((500,383),Image.Resampling.LANCZOS)
    sheet.paste(frame,((tile%2)*500,(tile//2)*400))
sheet.save(OUT/'服装摆动对比.png')
check=Image.open(gifpath)
assert check.n_frames==41
assert ImageChops.difference(frames[0],frames[20]).getbbox()
(OUT/'preview_media_validation.json').write_text(json.dumps({'success':True,'gif_frames':check.n_frames,'frame_duration_ms':100,'last_frame_duration_ms':700,'derived_from':'baked output of 121-frame live VRM solver run','source_views':['+X front','-X back']},indent=2),encoding='utf-8')
print(str(gifpath))
