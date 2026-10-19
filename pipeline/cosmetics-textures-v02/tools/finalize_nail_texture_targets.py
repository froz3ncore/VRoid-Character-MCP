"""Package evidenced nail targeting independently of the production outfit."""
import ast,hashlib,json,shutil,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/cosmetics-texture-tools-v02';D=ROOT/'projects/whale-maid/diagnostics';N=D/'nail-targets-baked-color-v02';V=D/'nail-visibility-v01'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def asset(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def copy(p,name):
    target=OUT/'evidence'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);return asset(target)
assert not OUT.exists(),'Do not overwrite a completed delivery'
OUT.mkdir();assert read(N/'acceptance.json')['passed'] and read(V/'acceptance.json')['passed']
assert read(N/'pixel-comparison.json')['equal'] and read(V/'catalog.json')['tools']==82
diff=read(V/'texture-composition-diff.json');assert diff['changed_pixels']==diff['mask_pixels']==24988 and diff['changed_outside_nail_masks']==0
ownership=read(D/'nail-targets-native-v05/surface-ownership.json');assert ownership['passed']
mapping=read(N/'nail-map.json');record=read(N/'map-export.json')
for side in ('left','right'):
    hit=read(N/('pick-'+side+'.json'))['nearest'];nail=next(n for n in mapping['nails'] if n['side']==side and n['finger']=='index')
    assert hit['triangle'] in [i for p in nail['islands'] for i in p['triangle_ids']]
tests=ET.parse(ROOT/'work/nail-targets-tests-final-20261019.xml').getroot().findall('testsuite');counts={k:sum(int(s.attrib.get(k,0)) for s in tests) for k in ('tests','failures','errors','skipped')}
assert counts=={'tests':351,'failures':0,'errors':0,'skipped':1}
appearance=ROOT/'projects/whale-maid/accessory-refinement-v02';state=read(appearance/'WORKING_STATE.json');assert state['current_candidate']=='hem-align-v22'
protected=read(appearance/'hem-align-v22/final_delivery.json')['artifacts']
for p in protected.values():assert asset(Path(p['path']))['sha256']==p['sha256']
def functions(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(p.read_text(encoding='utf8'))) if isinstance(n,ast.AsyncFunctionDef) and n.decorator_list}
old=functions(ROOT/'work/cosmetics-integration-v01/before/vroid_mcp/server.py');current=functions(ROOT/'VRoid-MCP/vroid_mcp/server.py');assert len(old)==70 and all(current[n]==v for n,v in old.items())
evidence={}
for name in ('acceptance','pixel-comparison','catalog','pick-left','pick-right','saved'):
    evidence[name]=copy(N/(name+'.json'),name+'.json')
for name in ('acceptance','texture-composition-diff','baked-base-control','baked-base-with-overlay','bindings'):
    evidence['visibility-'+name]=copy(V/(name+'.json'),'visibility-'+name+'.json')
evidence['ownership']=copy(D/'nail-targets-native-v05/surface-ownership.json','surface-ownership.json')
evidence['nail-map']=copy(N/'nail-map.json','nail-map.json')
evidence['overlay']=copy(Path(record['diagnostic_overlay']['path']),'diagnostic-overlay.png')
for mask in record['masks']:evidence[mask['nail_id']+'-mask']=copy(Path(mask['path']),'masks/'+mask['nail_id']+'.png')
for side in ('left','right'):
    for phase in ('before','after','cold'):evidence[phase+'-'+side]=copy(N/(phase+'-'+side+'.png'),phase+'-'+side+'.png')
for nail in mapping['nails']:evidence[nail['id']]=copy(V/(nail['id']+'.png'),'closeups/'+nail['id']+'.png')
for kind in ('Hand','Foot','Body'):
    result=read(V/('rendered-'+kind+'.json'));evidence['rendered-'+kind]=copy(Path(result['path']),'rendered-'+kind+'.png')
evidence['base-layer']=copy(Path(read(V/'baked-base-control.json')['path']),'baked-base-layer.png')
evidence['layer-export']=copy(Path(read(N/'native-layer-export.json')['path']),'native-layer-export.png')
evidence['diagnostic-vroid']=copy(N/'diagnostic-nails-not-production.vroid','diagnostic-nails-not-production.vroid')
copy(ROOT/'projects/whale-maid/COSMETICS_WORKING_STATE.json','previous-cosmetics-working-state.json');copy(appearance/'WORKING_STATE.json','previous-appearance-working-state.json')
write(OUT/'visual-review.json',{'passed':True,'native_images_actually_inspected':12,'all_ten_fingers_visible_in_individual_closeups':True,'colors_on_nails_not_knuckles':True,'foot_uv_overlap_pixels':0,'changed_outside_nail_masks':0,'diagnostic_only':True,'final_art_adopted':False})
source_names=['VRoid-MCP/agent/textures.js','VRoid-MCP/agent/operations.js','VRoid-MCP/vroid_mcp/texture_tools.py','VRoid-MCP/vroid_mcp/texture_targets.py','VRoid-MCP/vroid_mcp/texture_mapping.py','VRoid-MCP/vroid_mcp/texture_input.py','VRoid-MCP/vroid_mcp/server.py','VRoid-MCP/vroid_mcp/runtime.py','VRoid-MCP/tests/test_texture_input.py','VRoid-MCP/tests/test_texture_mapping.py',
    'tools/clean_native_clothing.py','tools/probe_hand_texture_bindings.py','tools/accept_nail_texture_targets.py','tools/review_nail_texture_sides.py','tools/verify_nail_native_visibility.py','tools/check_nail_surface_ownership.py','tools/check_nail_composite_pixels.py','tools/finalize_nail_texture_targets.py']
rows=[]
for name in source_names:
    p=ROOT/name;raw=p.read_bytes()
    if p.suffix=='.py':ast.parse(raw.decode('utf-8-sig'),filename=name)
    target=OUT/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);rows.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
write(OUT/'source/source-snapshot.json',{'scope':'Cosmetics v02 integration and validation source; not a replacement for unrelated hair work. Global snapshot manifest is not modified by this task.','files':rows})
report=ROOT/'docs/手部贴图归属与十指甲面UV定位_v02_2026-10-19.md'
delivery={'date':'2026-10-19','stage':'Measured ten-finger nail UV masks, rendered texture ownership, native RGB import and visual save/reopen acceptance','native_tools':82,'previous_tools':77,
    'new_tools':['inspect_texture_renderers','export_renderer_texture','pick_texture_uv','export_nail_uv_map','capture_texture_detail'],'nails':10,'uv_islands':20,'mask_pixels':24988,
    'native_ray_samples':2,'ray_hits_verified_on_index_nail_triangles':True,'foot_uv_overlap_pixels':0,'editable_overlay_uv_vertex_max_error':0.0,'rendered_texture_changed_outside_nail_masks':0,
    'native_layer_rgba_matches_input':True,'native_save_reopen_passed':True,'existing_baked_layer_unchanged_by_import':True,'native_closeups_actually_reviewed':10,
    'python_tests':{'passed':350,'skipped':1,'report':str(ROOT/'work/nail-targets-tests-final-20261019.xml')},'js_regression_groups_passed':4,
    'source_pack_files':len(rows),'source_pack_manifest':str(OUT/'source/source-snapshot.json'),'source_pack_mirror':str(ROOT/'VRoid-MCP/pipeline/cosmetics-textures-v02'),
    'old_68_server_tools_ast_preserved':True,'hair_agent_modified_by_this_task':False,'shared_global_source_manifest_modified_by_this_task':False,
    'formal_appearance_candidate':'hem-align-v22','protected_artifact_hashes_verified':protected,'formal_art_applied':False,'diagnostic_art_only_in_independent_vroid':True,
    'native_color_baking_required_for_current_body_skin_rgb':True,'native_png_cpu_cache_issue_corrected':True,'freehand_brush_strokes_implemented':False,
    'limitations':['Nail-cap discovery supports the measured paired distal-bone topology; unknown or ambiguous topology and cross-finger UV sharing are rejected.','Renderer UV picking identifies texture coordinates and material slots; arbitrary model editable-image transforms still require calibration.','Color baking intentionally creates a colored editable base; it is opt-in, independent from adding a new overlay.','No final makeup/nail design or application to production XRoid/VRM; no Godot validation.','Reload the long-running MCP connection to see 82 tools; no other development session was restarted.'],
    'next_step':'Build bounded local makeup/nail painting and stamp operations on validated image addresses and masks, then create an independent art candidate. Do not resume garment collision work automatically.',
    'report':str(report),'evidence':evidence,'new_commit_or_push':False}
write(OUT/'final_delivery.json',delivery);write(ROOT/'projects/whale-maid/COSMETICS_WORKING_STATE.json',delivery)
state.update(native_tools=82,next_step=delivery['next_step'],cosmetics_texture_tools={'delivery':str(OUT/'final_delivery.json'),'stage':delivery['stage'],'new_tools_this_stage':5,'actual_makeup_applied_to_production':False,'nail_masks_implemented':True,'visible_diagnostic_nails_save_reopen_passed':True,'model_ray_to_uv_implemented':True},latest_cosmetics_validation={'python_passed':350,'python_skipped':1,'js_groups_passed':4,'production_artifacts_unchanged':True})
write(appearance/'WORKING_STATE.json',state)
report.write_text(f'''# 手部贴图归属与十指甲面 UV 定位 v02（2026-10-19）

本轮已把“知道该画哪里”推进到实际原生显示：十指甲面可独立寻址，彩色诊断图层在保存新文件、新进程重开后仍准确显示。它是工具验收，尚未制作正式美甲款式，也没有覆盖当前 v22 服装、XRoid 或 VRM。

## 部位对应与交付

实际 Hand 为 1580 顶点 / 2302 三角面；与 Body、Foot 在同一采样中共享 N00_000_00_Body_00_SKIN 材质和 2048×2048 主贴图。不能只靠共享材质判断画板地址，因此又核对了实际 BodySkin 覆盖网格：20 片甲面所有 UV 顶点在该覆盖网格里均有精确对应，最大差 0。每根手指有两片反向小表面，按实际末节手指骨、连通性、形状大小及成对距离识别，未使用固定 UV 框或固定顶点数。

- 10 张逐指遮罩 / 20 UV 岛 / 24988 像素；左右指甲没有共用像素。
- 对全部遮罩像素中心核对 Foot 三角面：重叠 **0**。不是脚趾美甲。
- 实际渲染贴图与独立“只烘焙肤色”对照比较：改变 **24988** 像素，恰为全部甲面遮罩；遮罩外改变 **0**。导入没有改动已有烘焙底层，原生层导出哈希相同。
- 左右食指真实射线拾取命中对应甲面三角形，返回重心坐标、材质槽、实际纹理尺寸、UV 与左上原点像素坐标；10 张逐指近景和两张冷重开双手图均已实际查看。
- 原生图层导入前后 RGBA 逐像素一致（11 色含透明背景），保存重开后导出 PNG 哈希保持。独立 `.vroid` 仅用于诊断；源底模及 v22 Blender/XWear/XRoid/VRM 哈希全部保持。

入口：`{OUT/'final_delivery.json'}`；可视浏览 `review.html`。证据、逐指 PNG 遮罩、甲面三角形/骨骼/UV 数据和诊断测试副本在 evidence/。

## 新增及修正的工具

新增 5 工具，实际 stdio **82**：`inspect_texture_renderers` 读模型实际材质/贴图身份；`export_renderer_texture` 导出真实渲染主贴图；`pick_texture_uv` 从实际三维射线定位三角面/UV；`export_nail_uv_map` 导出逐指遮罩；`capture_texture_detail` 用临时相机采局部近景，结束后释放。

`open_texture_editor` 新增显式 `bake_colors=True`：使用原生“把颜色应用到纹理”创建已带肤色的编辑底图。当前 BodySkin 若保持灰度皮肤重着色链路，新图层 RGB 会被重新染成肤色，造成“贴图里有颜色、手上看不到”。这是本轮真正的显示原因。默认仍不自动烘焙；调用者应先确定编辑部位，再选择是否烘焙、重新列出图层和图像地址。图层导入要求正确原生画板已打开，并确保新增层置顶；返回实际历史命令数量。

另修正原生纹理 CPU 缓存问题：先前 CreateTexture2D/EncodeToPNG 曾导出整张 0xCD 像素。现在图层直接从原生 ComposeTiles 取 RGBA，再使用原生 PNG 编码；输入 PNG 先用原生 CPU 解码，生成明确的 Color 数组后交给历史命令。单纯前后导出哈希相等不足以证明成功，本轮加入输入/输出 RGBA 比较、实际渲染贴图比较及冷重开画面。

## 过程版本与限制

v01/v03/v05 等早期数据回读成功不等于可见美甲；它们没有通过本轮最终显示验收。v02 GPU 读回尝试仍无正确像素；v04 在排序接口字段预检不全时中止、未保存。上下翻转对照在烘焙后会把颜色落到手指根部，明确不采用；正确方向是最终 baked-color-v02。全部独立过程原位保留，无不确定保存重试。图层排序并非最终显示原因，置顶检查只作为导入保证。

v01 面妆基础报告关于导出 PNG 哈希的证明现由本报告补正：旧证据不能作为真实像素正确的结论，旧图片保留为过程资料。脸部局部妆容遮罩、受限笔刷/印章、正式妆造风格仍待开发；本轮未声称已完成面妆或通用任意模型美甲。

350 Python 通过 / 1 权限跳过，新增 28 项几何与光线/UV/遮罩回归；4 组 JS 和新增 JS 语法检查通过。{len(rows)} 份源码快照已核对；原有 68 个 server 工具函数 AST 保持。本轮未改发束 agent/parameters.js，不更新共享全局源码快照，不重启其他开发会话；未提交推送。当前长驻 MCP 需重载连接才能显示新目录。
''',encoding='utf8')
html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>十指甲面定位验证</title><style>body{font:16px system-ui;background:#eef1f5;color:#202c3d;max-width:1300px;margin:32px auto;padding:16px}img{max-width:100%;border-radius:12px}.hands{display:grid;grid-template-columns:1fr 1fr;gap:16px}.fingers{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}figure{margin:0;background:white;padding:10px;border-radius:14px}figcaption{padding:8px 0}a{color:#2459ac}</style><h1>十指甲面定位验证</h1><p>独立工具测试副本。颜色用于分辨每根手指，并非正式美甲设计。</p><p>保存重开通过；十指甲面之外，实际渲染贴图改变 0 像素；脚部 UV 重叠 0。</p><div class="hands">'''
for side,title in [('left','左手'),('right','右手')]:html+=f'<figure><img src="evidence/cold-{side}.png"><figcaption>{title} · 新进程重开</figcaption></figure>'
html+='</div><h2>逐指近景</h2><div class="fingers">'
for nail in mapping['nails']:
    label=('左' if nail['id'][0]=='L' else '右')+{'thumb':'拇指','index':'食指','middle':'中指','ring':'无名指','little':'小指'}[nail['finger']]
    html+=f'<figure><img src="evidence/closeups/{nail["id"]}.png"><figcaption>{label} · <a href="evidence/masks/{nail["id"]}.png">遮罩</a></figcaption></figure>'
html+='</div><p><a href="evidence/diagnostic-nails-not-production.vroid">独立测试模型</a> · <a href="final_delivery.json">验证记录</a></p>'
(OUT/'review.html').write_text(html,encoding='utf8')
print(json.dumps({'delivered':True,'tools':82,'nails':10,'source_files':len(rows),'report':str(report)},ensure_ascii=False))
