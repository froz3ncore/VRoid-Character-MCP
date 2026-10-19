"""Read actual exported VRM geometry counts and material/image preservation."""
import argparse, hashlib, json, struct
from pathlib import Path


def read(path):
    raw=path.read_bytes()
    assert raw[:4]==b'glTF' and struct.unpack_from('<I',raw,8)[0]==len(raw)
    length=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+length])
    offset=20+length
    assert raw[offset+4:offset+8]==b'BIN\0'
    return doc,raw[offset+8:]


def palette(doc, binary):
    rows={}
    for mat in doc['materials']:
        pbr=mat.get('pbrMetallicRoughness',{})
        index=pbr.get('baseColorTexture',{}).get('index')
        image_hash=None
        if index is not None:
            image=doc['images'][doc['textures'][index]['source']]
            view=doc['bufferViews'][image['bufferView']]
            start=view.get('byteOffset',0)
            image_hash=hashlib.sha256(binary[start:start+view['byteLength']]).hexdigest()
        rows[mat['name']]={'base_color_factor':pbr.get('baseColorFactor'), 'shade_color_factor':mat.get('extensions',{}).get('VRMC_materials_mtoon',{}).get('shadeColorFactor'), 'base_texture_sha256':image_hash,'alpha_mode':mat.get('alphaMode','OPAQUE')}
    return rows


def main(a):
    previous,previous_bin=read(a.previous)
    doc,binary=read(a.vrm)
    old,new=palette(previous,previous_bin),palette(doc,binary)
    assert old==new,'Exported material colors/base image bytes changed'
    stocking=new['WM_WhiteStocking_NeutralShade_v13']
    shade_error=max(abs(x-y) for x,y in zip(stocking['shade_color_factor'],[.82,.85,.9]))
    assert shade_error<1e-6
    rows=[]
    for node in doc['nodes']:
        if 'mesh' not in node:
            continue
        tris=sum(doc['accessors'][p['indices']]['count']//3 for p in doc['meshes'][node['mesh']]['primitives'])
        rows.append({'node':node.get('name',''),'triangles':tris})
    assert sum(r['triangles'] for r in rows if r['node']=='Body')==11580
    fitted=[r for r in rows if r['node'].startswith('FIT_')]
    assert len(fitted)==a.fitted_nodes and sum(r['triangles'] for r in fitted)==a.fitted_triangles
    native=[p for mesh in doc['meshes'] for p in mesh['primitives'] if '_Shoes_' in doc['materials'][p['material']].get('name','') and doc['accessors'][p['indices']]['count']>0]
    assert not native
    report={'passed':True,'vrm':str(a.vrm.resolve()),'previous_vrm':str(a.previous.resolve()),'compared_materials':len(new),'base_color_shade_factors_and_base_texture_png_hashes_unchanged':True,'stocking_shade_error':shade_error,'body_triangles':11580,'native_shoe_triangles':0,'fitted_nodes':len(fitted),'fitted_triangles':sum(r['triangles'] for r in fitted),'geometry':rows,'godot_validated':False,'scope':'Actual VRM content and material/color preservation; no Godot runtime or all-motion collision acceptance.'}
    with a.out.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:report[k] for k in ['passed','compared_materials','stocking_shade_error','fitted_nodes','fitted_triangles']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--previous',type=Path,required=True)
    p.add_argument('--vrm',type=Path,required=True)
    p.add_argument('--fitted-triangles',type=int,required=True)
    p.add_argument('--fitted-nodes',type=int,default=97)
    p.add_argument('--out',type=Path,required=True)
    main(p.parse_args())
