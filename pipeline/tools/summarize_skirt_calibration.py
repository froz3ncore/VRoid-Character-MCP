"""Check saved parameters and collect evidence without modifying the assets."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/target-fit-v04'
def read(p):return json.loads(p.read_text(encoding='utf8'))
record=read(OUT/'final-wear/refined-wear-acceptance.json')
source=read(OUT/'source-calibration.json')
for key in ('source','target'):
    assert hashlib.sha256(Path(source[key]).read_bytes()).hexdigest()==source[key+'_sha256']
checks=0
for skeleton in record['reopen']['items'][0]['skeletons']:
    joints={b['name']:b['spring_joint'] for b in skeleton['bones'] if b['spring_joint']}
    for expected in source['changes']:
        actual=joints[expected['bone']]
        for native,field in [('stiffness','stiffness'),('gravity_power','gravity'),('drag','drag')]:
            assert abs(actual[native]-expected[field])<1e-6
        checks+=1
baseline=read(OUT/'baseline-native-poses/sit-reference.detail-diagnosis.json')['records'][0]
sit=read(OUT/'final-native-poses/sit-reference.diagnosis.json')['records'][0]
walk=read(OUT/'final-native-poses/walk-reference.diagnosis.json')['records'][0]
assert baseline['geometry_stream_sha256']==sit['geometry_stream_sha256']==walk['geometry_stream_sha256']
result={'version':'v04 experimental candidate','source_unchanged':True,'saved_parameter_checks':checks,
    'native_save_reopen_passed':record['cold_reopen_passed'],
    'main_source_geometry_uv_triangles_unchanged':True,
    'sitting_front_hem_p95_above_hips_m_before':baseline['front_hem_p95_above_hips_m'],
    'sitting_front_hem_p95_above_hips_m_after':sit['front_hem_p95_above_hips_m'],
    'sitting_main_penetration_screening_before':baseline['screening'],
    'sitting_main_penetration_screening_after':sit['screening'],
    'walk_main_penetration_screening':walk['screening'],
    'visual_acceptance':'Improved sitting hem height; walking skirt narrower. Knee/lace/shoulder issues remain. Not final collision acceptance.',
    'scope':'Main garment sample in two actual poses; no all-frame collision proof, VRM export or Godot validation'}
destination=OUT/'calibration-summary.json';assert not destination.exists()
destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if 'screening' not in k},ensure_ascii=False))

# Keep the portable source snapshot in sync with the external workspace layout.
pipeline=ROOT/'VRoid-MCP/pipeline';manifest=read(pipeline/'source-snapshot.json')
for name in ['capture_pose_fit_reference.py','diagnose_native_pose.py','make_spring_calibration_variants.py',
             'test_spring_calibration_native.py','save_calibrated_skirt.py','verify_calibrated_blend.py','summarize_skirt_calibration.py']:
    relative='tools/'+name;raw=(ROOT/relative).read_bytes();shutil.copy2(ROOT/relative,pipeline/relative)
    entry={'path':relative,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
           'git_lf_sha256':hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
    manifest['files']=[r for r in manifest['files'] if r['path']!=relative]+[entry]
manifest['files'].sort(key=lambda r:r['path'])
(pipeline/'source-snapshot.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
