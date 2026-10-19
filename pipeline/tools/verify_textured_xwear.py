"""Independent reader checks ZIP payloads, binary skin data and spring references."""
import io, json, math, struct, sys, zipfile, hashlib
from pathlib import Path

def mesh_info(payload):
    stream=io.BytesIO(payload)
    def ints(n=1):return struct.unpack('<'+'i'*n,stream.read(4*n))
    def floats(n):return struct.unpack('<'+'f'*n,stream.read(4*n))
    version=ints()[0];length=0;shift=0
    while True:
        b=stream.read(1)[0];length|=(b&127)<<shift
        if not b&128:break
        shift+=7
    name=stream.read(length).decode('utf8');count=ints()[0]
    positions=[]
    for width in (3,3,4,4,2,2,2,2):
        n=ints()[0];values=[floats(width) for _ in range(n)]
        assert all(math.isfinite(x) for v in values for x in v)
        if not positions:positions=values
        if width==3:assert n==count
    weights=[]
    for _ in range(ints()[0]):weights.append((floats(4),ints(4)))
    bones=ints()[0];matrices=[floats(16) for _ in range(bones)]
    assert len(weights)==count
    for ws,js in weights:
        assert min(ws)>=0 and abs(sum(ws)-1)<1e-5
        assert all(0<=j<bones for w,j in zip(ws,js) if w>0)
    triangles=0
    for _ in range(ints()[0]):
        topology,n=ints(2);indices=ints(n)
        assert topology==0 and n%3==0 and all(0<=i<count for i in indices)
        triangles+=n//3
    assert ints(2)==(0,0) and stream.read()==b''
    return {'name':name,'vertices':count,'triangles':triangles,'bones':bones,
            'bounds':[[min(p[a] for p in positions),max(p[a] for p in positions)] for a in range(3)]}

def verify(path):
    with zipfile.ZipFile(path) as archive:
        read=lambda name: archive.read(name.replace('\\','/'))
        assert archive.testzip() is None
        names=archive.namelist();assert len(set(names))==len(names)
        item=json.loads(read('Body\\XItem.json\\XItem.json'))
        textures=item['XResourceTextures'];texture_ids={t['Guid'] for t in textures}
        for t in textures:
            png=read('Textures\\'+t['Guid']+'.png')
            assert png[:8]==b'\x89PNG\r\n\x1a\n'
            width,height=struct.unpack('>II',png[16:24]);p=t['TextureParam']
            assert (width,height)==(p['width'],p['height'])
        for material in item['XResourceMaterials']:
            assert set(material['referencedTextureGuids'])<=texture_ids
            for p in material['ShaderProperties']:
                if 'TextureGuid' in p:assert p['TextureGuid'] in texture_ids
        meshes=[];spring_counts=[]
        for info in item['XResourceInfoList']:
            resource=json.loads(read('Body\\XResources\\'+info['Guid']))
            nodes={}
            def walk(node):
                assert node['Guid'] not in nodes;nodes[node['Guid']]=node
                for c in node['Children']:walk(c)
            walk(resource['RootGameObject'])
            assert set(resource['TextureGuids'])<=texture_ids
            for c in resource['Components']:
                assert c['GameObjectGuid'] in nodes
                if 'MeshGuid' in c:
                    mi=mesh_info(read('Mesh\\'+c['MeshGuid']))
                    assert mi['bones']==len(c['Bones'])
                    assert all(b['BoneGuid'] in nodes for b in c['Bones'])
                    meshes.append(mi)
                if 'AnythingJson' in c:
                    sb=json.loads(c['AnythingJson']);refs={r['key']:r['referenceGuid'] for r in c['ReferenceGuidStores']}
                    assert len(refs)==len(c['ReferenceGuidStores']) and set(refs.values())<=set(nodes)
                    for i in range(len(sb['JointItems'])):assert 'Vrm1Joint_'+str(i) in refs
                    for i in range(len(sb['ColliderItems'])):assert 'Vrm1Collider_'+str(i) in refs
                    for s in sb['SpringItems']:
                        assert all(0<=i<len(sb['JointItems']) for i in s['JointIndexes'])
                        assert all(0<=i<len(sb['ColliderGroupItems']) for i in s['ColliderGroupIndexes'])
                    for g in sb['ColliderGroupItems']:assert all(0<=i<len(sb['ColliderItems']) for i in g['ColliderIndexes'])
                    spring_counts.append({'springs':len(sb['SpringItems']),'joints':len(sb['JointItems']),'colliders':len(sb['ColliderItems'])})
        return {'passed':True,'path':str(path),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                'textures':len(textures),'meshes':meshes,'spring_counts':spring_counts,
                'scope':'ZIP, PNG dimensions, binary meshes, normalized weights and references; native import separate'}
if __name__=='__main__':
    path=Path(sys.argv[1]);result=verify(path)
    path.with_suffix('.package-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'meshes':len(result['meshes']),'textures':result['textures'],'spring':result['spring_counts']}))
