from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json
OUT=Path(r'D:\vroidmcp\projects\whale-maid\target-fit-v01')
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20);small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16)
frames=[]
cases=[('rest','站立'),('arms_forward','抬臂'),('step','迈步'),('seated_joint_pose','90° 坐姿关节')]
for name,label in cases:
    canvas=Image.new('RGB',(720,520),(31,37,44));draw=ImageDraw.Draw(canvas)
    draw.text((16,5),'真实 VRoid 身体 · 服装适配：'+label,font=font,fill='white')
    for i,view in enumerate(['front','side']):
        image=Image.open(OUT/'pose-review'/f'{name}_{view}.png').convert('RGB').resize((360,450),Image.Resampling.LANCZOS)
        canvas.paste(image,(i*360,38))
    draw.text((16,493),'灰模身体参考 / 正面与侧面 / 固定姿势检查，非连续动画',font=small,fill=(205,216,230))
    frames.append(canvas)
palette=frames[0].quantize(colors=256)
gif=[im.quantize(palette=palette) for im in frames]
gif[0].save(OUT/'真实身体服装姿势预览.gif',save_all=True,append_images=gif[1:],duration=1800,loop=0,optimize=False,disposal=2)
sheet=Image.new('RGB',(1440,1040),(31,37,44))
for i,im in enumerate(frames):sheet.paste(im,((i%2)*720,(i//2)*520))
sheet.save(OUT/'服装适配姿势检查.png')
check=Image.open(OUT/'真实身体服装姿势预览.gif');assert check.n_frames==4
(OUT/'media_validation.json').write_text(json.dumps({'success':True,'gif_frames':4,'duration_ms_per_frame':1800,'scope':'Static solved pose screenshots, not continuous movement video'},indent=2),encoding='utf-8')
print('TARGET_REVIEW_MEDIA_READY')
