"""Create resource-unique parameter variants; mesh and texture bytes stay identical."""
import json,zipfile,re,uuid,hashlib
from pathlib import Path
from verify_textured_xwear import verify
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'projects/whale-maid/target-fit-v03/final-wear/whale_maid_bow_textured_v05.xwear'
OUT=ROOT/'projects/whale-maid/target-fit-v04/calibration-v02'
CONFIGS={'soft_front':{'rings':[0,1,2,10,11],'stiffness':.25,'gravity':.30,'drag':.65},
         'soft_all':{'rings':list(range(12)),'stiffness':.45,'gravity':.18,'drag':.70},
         'graded_all':{'rings':list(range(12)),'stiffness':.65,'gravity':.12,'drag':.65,'distal_stiffness':.12,'distal_gravity':.28}}

def main():
    OUT.mkdir(exist_ok=False)
    original_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest();manifest=json.loads(SOURCE.with_suffix('.xwear.json').read_text(encoding='utf8'))
    pattern=re.compile(r'\b[0-9a-f]{32}\b');result=[]
    with zipfile.ZipFile(SOURCE) as source:
        original={info.orig_filename:source.read(info) for info in source.infolist()}
    for label,config in CONFIGS.items():
        mapping={}
        def replace(match):return mapping.setdefault(match.group(),uuid.uuid4().hex)
        payloads=dict(original);changed=0
        for name,raw in original.items():
            if not name.replace('\\','/').startswith('Body/XResources/'):continue
            resource=json.loads(raw)
            for component in resource['Components']:
                if 'AnythingJson' not in component:continue
                sb=json.loads(component['AnythingJson'])
                for spring in sb['SpringItems']:
                    # SpringNames in the export are explicit and stable.
                    name_field=next((k for k in ('Name','Comment') if k in spring),None)
                    if name_field is None:raise ValueError('Missing native spring name')
                    spring_name=spring[name_field]
                    if not spring_name.startswith('Skirt_') or int(spring_name.split('_')[-1]) not in config['rings']:continue
                    for segment,index in enumerate(spring['JointIndexes']):
                        joint=sb['JointItems'][index]
                        joint['StiffnessForce']=config.get('distal_stiffness',config['stiffness']) if segment>=2 else config['stiffness']
                        joint['GravityPower']=config.get('distal_gravity',config['gravity']) if segment>=2 else config['gravity']
                        joint['DragForce']=config['drag'];changed+=1
                component['AnythingJson']=json.dumps(sb,separators=(',',':'))
            payloads[name]=json.dumps(resource,separators=(',',':')).encode()
        assert changed>0
        path=OUT/(label+'-v02.xwear');binary_checks=0
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as target:
            for name,raw in payloads.items():
                binary=name.replace('\\','/').startswith(('Mesh/','Textures/'))
                converted=raw if binary else pattern.sub(replace,raw.decode('utf8')).encode()
                new_name=pattern.sub(replace,name);entry=zipfile.ZipInfo(new_name)
                entry.filename=entry.orig_filename=new_name;entry.compress_type=zipfile.ZIP_DEFLATED
                target.writestr(entry,converted)
                if binary:assert converted==original[name];binary_checks+=1
        checked=verify(path);copy=dict(manifest);copy['path']=str(path);copy['calibration']=config;copy['sha256']=checked['sha256']
        with zipfile.ZipFile(path) as check:
            assert 'Body\\XItem.json\\XItem.json' in {i.orig_filename for i in check.infolist()}
        path.with_suffix('.xwear.json').write_text(json.dumps(copy,ensure_ascii=False,indent=2),encoding='utf8')
        path.with_suffix('.package-validation.json').write_text(json.dumps(checked,ensure_ascii=False,indent=2),encoding='utf8')
        result.append({'label':label,'path':str(path),'config':config,'changed_joints':changed,'binary_payloads_unchanged':binary_checks,'sha256':checked['sha256']})
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==original_hash
    (OUT/'variants.json').write_text(json.dumps({'source':str(SOURCE),'source_sha256':original_hash,'variants':result},indent=2),encoding='utf8')
    print(json.dumps([{'label':r['label'],'changed_joints':r['changed_joints'],'binary_payloads_unchanged':r['binary_payloads_unchanged']} for r in result]))
if __name__=='__main__':main()
