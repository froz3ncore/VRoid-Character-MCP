"""Compare decoded PNG pixels with every packed source image (Pillow runtime)."""
import hashlib,io,json,sys,zipfile
from pathlib import Path
from PIL import Image,ImageChops
path=Path(sys.argv[1]);export=json.loads(path.with_suffix(path.suffix+'.json').read_text(encoding='utf8'))
checks=[]
with zipfile.ZipFile(path) as archive:
    item=json.loads(archive.read('Body/XItem.json/XItem.json'))
    for texture in item['XResourceTextures']:
        source=export['source_textures'][texture['Name']];original=Path(source['path']).read_bytes()
        assert hashlib.sha256(original).hexdigest()==source['sha256']
        source_image=Image.open(io.BytesIO(original)).convert('RGB')
        output_image=Image.open(io.BytesIO(archive.read('Textures/'+texture['Guid']+'.png'))).convert('RGB')
        assert source_image.size==output_image.size
        extrema=ImageChops.difference(source_image,output_image).getextrema()
        maximum=max(high for low,high in extrema)
        assert maximum==0,(texture['Name'],extrema)
        checks.append({'name':texture['Name'],'size':list(output_image.size),'max_rgb_error_8bit':maximum,
            'decoded_rgb_sha256':hashlib.sha256(output_image.tobytes()).hexdigest()})
result={'passed':True,'textures':len(checks),'max_rgb_error_8bit':0,'checks':checks}
path.with_suffix('.texture-pixel-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
