"""Package measured regional paint tools, native proofs and an independent editable makeup candidate."""
import ast,hashlib,json,shutil,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/cosmetics-texture-tools-v03';D=ROOT/'projects/whale-maid/diagnostics';N=D/'local-makeup-native-v02';C=D/'local-makeup-close-v04';G=D/'local-makeup-write-boundary-v01'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def asset(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def copy(p,name):
 target=OUT/'evidence'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);return asset(target)
assert not OUT.exists(),'Refuse to overwrite a completed delivery'
acceptance=read(N/'acceptance.json');close=read(C/'acceptance.json');assert acceptance['passed'] and close['passed'] and read(G/'acceptance.json')['passed']
assert read(G/'catalog.json')['tools']==read(N/'catalog.json')['tools']==85
pixels=read(N/'pixel-acceptance.json');assert all(p['paint_outside_mask_pixels']==0 and p['input_native_rgba_equal'] and p['native_cold_rgba_equal'] for p in pixels['parts'].values())
for label in ('original','candidate'):
 opened=read(C/(label+'-open.json'));closed=read(C/(label+'-closed.json'))
 assert opened['sha256']!=closed['sha256'] and closed['eye_pose']['restored'] and closed['eye_pose']['baked_vertex_max_change_m']>.001
tests=ET.parse(ROOT/'work/local-makeup-tests-final-20261019.xml').getroot().findall('testsuite');counts={k:sum(int(s.attrib.get(k,0)) for s in tests) for k in ('tests','failures','errors','skipped')};assert counts=={'tests':384,'failures':0,'errors':0,'skipped':1},counts
appearance=ROOT/'projects/whale-maid/accessory-refinement-v02';state=read(appearance/'WORKING_STATE.json');assert state['current_candidate']=='hem-align-v22'
protected=read(appearance/'hem-align-v22/final_delivery.json')['artifacts']
for record in protected.values():assert asset(Path(record['path']))['sha256']==record['sha256']
base=read(appearance/'chest-skirt-v17b/isolated-base-record.json')['save'];assert asset(Path(base['path']))['sha256']==base['sha256']
def functions(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(p.read_text(encoding='utf8'))) if isinstance(n,ast.AsyncFunctionDef) and n.decorator_list}
old=functions(ROOT/'work/cosmetics-integration-v01/before/vroid_mcp/server.py');current=functions(ROOT/'VRoid-MCP/vroid_mcp/server.py');assert len(old)==70 and all(current[n]==v for n,v in old.items())
OUT.mkdir();evidence={};recipe=[]
copy(ROOT/'projects/whale-maid/COSMETICS_WORKING_STATE.json','previous-cosmetics-working-state.json');copy(appearance/'WORKING_STATE.json','previous-appearance-working-state.json')
for name in ('acceptance','pixel-acceptance','saved','protected-face-materials-before','protected-face-materials-after'):
 evidence[name]=copy(N/(name+'.json'),name+'.json')
evidence['final-catalog']=copy(G/'catalog.json','final-tool-catalog.json');evidence['write-boundary']=copy(G/'acceptance.json','write-boundary-acceptance.json');evidence['closed-eye-readback']=copy(C/'acceptance.json','closed-eye-acceptance.json')
for item in acceptance['parts']:
 part=item['part'];mask=read(N/(part+'-mask.json'));preview=read(N/(part+'-preview.json'));marks=read(N/(part+'-marks.json'));layer=read(N/(part+'-native-layer.json'))
 for label,path in [('mask',mask['mask_path']),('reference-layer',mask['reference_path']),('overlay',preview['path']),('native-layer',layer['path'])]:evidence[part+'-'+label]=copy(Path(path),part+'/'+label+'.png')
 for label in ('mask','marks','painted','undo-layers','redo-layers','cold-layer'):evidence[part+'-'+label+'-record']=copy(N/(part+'-'+label+'.json'),part+'/'+label+'.json')
 recipe.append({'region_part':part,'reference_layer':'Relist native canvas layers and select the original base raster; do not reuse an old layer ID.','mask_options':{'alpha_threshold':mask['alpha_threshold'],'padding_px':mask['padding_px']},'expected_mask_png_sha256':mask['mask_png_sha256'],'image_dimensions':[mask['width'],mask['height']],'marks':marks,'layer_name':'MCP_local_makeup_'+part+'_v01','opacity':1.})
evidence['candidate']=copy(N/'bounded-makeup-not-production.vroid','bounded-makeup-candidate-v01.vroid')
for name in ('before-face_front','after-Cheek-face_front','after-MouthLine-face_front','after-Eyelid-face_front','cold-face_front','cold-face_three_quarter_left','cold-face_three_quarter_right'):evidence[name]=copy(N/(name+'.png'),name+'.png')
for name in ('original-open','original-closed','candidate-open','candidate-closed'):
 evidence[name]=copy(C/(name+'.png'),'detail/'+name+'.png');evidence[name+'-capture']=copy(C/(name+'.json'),'detail/'+name+'.json')
write(OUT/'makeup-recipe.json',{'schema':'vroid-bounded-makeup-recipe-v1','name':'Soft rose local makeup example v01','reference_base_sha256':base['sha256'],'candidate_only':True,'final_art_adopted':False,
 'replay_policy':'Open each freshly listed region with explicit native color baking if needed; export a fresh model/image-bound mask and verify dimensions plus mask PNG hash against this recipe before using these canvas coordinates. Preview first, then paint as new native layers. Never reuse previous model_token, region/image/layer/mask IDs or silently retarget another UV layout. Native color baking is separate from brush Undo.',
 'parts':recipe})
write(OUT/'visual-review.json',{'passed':True,'native_open_eye_front_and_oblique_images_actually_inspected':True,'native_closed_eye_original_and_candidate_actually_inspected':True,'cheek_and_lip_color_on_intended_face_regions':True,'eyelid_layer_pixels_and_native_eyeline_material_change_verified':True,'closed_eye_capture_uses_baked_native_geometry':True,'old_close_previews_not_adopted':True,'candidate_only':True,'final_art_adopted':False})
source_names=['VRoid-MCP/agent/textures.js','VRoid-MCP/vroid_mcp/texture_tools.py','VRoid-MCP/vroid_mcp/texture_targets.py','VRoid-MCP/vroid_mcp/texture_mapping.py','VRoid-MCP/vroid_mcp/texture_input.py','VRoid-MCP/vroid_mcp/bounded_paint.py','VRoid-MCP/vroid_mcp/makeup_tools.py','VRoid-MCP/vroid_mcp/server.py','VRoid-MCP/vroid_mcp/runtime.py','VRoid-MCP/tests/test_bounded_paint.py','VRoid-MCP/tests/test_makeup_tools.py','VRoid-MCP/tests/makeup_eye_pose_test.js','tools/clean_native_clothing.py','tools/probe_local_makeup_regions.py','tools/accept_local_makeup_tools.py','tools/review_local_makeup_close.py','tools/probe_makeup_eye_shapes.py','tools/verify_local_makeup_write_boundary.py','tools/check_local_makeup_pixels.py','tools/finalize_local_makeup_tools.py']
rows=[]
for name in source_names:
 p=ROOT/name;raw=p.read_bytes()
 if p.suffix=='.py':ast.parse(raw.decode('utf-8-sig'),filename=name)
 target=OUT/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);rows.append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
write(OUT/'source/source-snapshot.json',{'scope':'Local cosmetics painting v03. Independent integration/verification source; do not overwrite concurrent hair work or the shared global source manifest.','files':rows})
report=ROOT/'docs/局部面妆笔刷与遮罩_v03_2026-10-19.md'
delivery={'date':'2026-10-19','stage':'Bounded local face brushes/stamps, measured masks and editable soft-makeup candidate','native_tools':85,'previous_tools':82,'new_tools':['export_makeup_region_mask','preview_makeup_marks','paint_makeup_marks'],
 'extended_tools':['capture_texture_detail optional render-only eye closure','inspect_texture_renderers face blendshape identities/frame units'],
 'native_region_paint_acceptance':str(N/'acceptance.json'),'native_post_render_write_guard_acceptance':str(G/'acceptance.json'),'native_actual_closed_eye_acceptance':str(C/'acceptance.json'),'pixel_acceptance':pixels,
 'native_parts':acceptance['parts'],'protected_face_material_slots_unchanged':6,'old_masks_rejected_after_model_reopen':True,'reference_rechecked_immediately_before_native_write':True,
 'brushes':{'stamps':'Soft/hard ellipse, aspect and rotation, normalized RGBA','strokes':'Connected points with bounded dab sampling and maximum within-stroke coverage','mirror':'Canvas reflection including rotated brushes; no inferred anatomical mirror','antialias_samples_per_pixel':4,'model_write':'Generated RGBA PNG as NEW native history layer, not simulated desktop mouse drawing','native_3d_freehand_cursor_implemented':False},
 'python_tests':{'passed':383,'skipped':1,'new_tests':33,'report':str(ROOT/'work/local-makeup-tests-final-20261019.xml')},'js_regression_groups_passed':5,'source_pack_files':len(rows),'source_pack_manifest':str(OUT/'source/source-snapshot.json'),'source_pack_mirror':str(ROOT/'VRoid-MCP/pipeline/cosmetics-textures-v03'),
 'old_68_server_tool_asts_preserved':True,'hair_agent_modified_by_this_task':False,'shared_global_source_manifest_modified_by_this_task':False,'formal_appearance_candidate':'hem-align-v22','protected_artifact_hashes_verified':protected,
 'editable_makeup_candidate':evidence['candidate'],'makeup_recipe':str(OUT/'makeup-recipe.json'),'formal_art_applied':False,'whole_outfit_final_art_adopted':False,'godot_validated':False,
 'limitations':['Mouth is oral interior; the current lip tint is a bounded expansion of the existing MouthLine footprint, not full automatic anatomical lip segmentation.','Eyelid masks use its real native canvas UV geometry; the example is intentionally subtle. The visible renderer material is the eyeline atlas, not the face skin atlas.','Native color baking may alter the representation of base colors. It is explicit and precedes the independently undoable new brush layer.','Brush points are normalized top-left canvas coordinates. Fresh mask image/model/source checks are mandatory; masks are not portable session IDs.','This is bounded 2D raster painting imported through native layer history; native 3D freehand brush gestures and arbitrary artwork decal files are not implemented.','The new editable candidate is a standalone .vroid, not the production XRoid/VRM outfit. Style approval and later assembly integration remain pending.','Reload a long-running MCP connection to expose the updated 85-tool catalog; other sessions were not restarted.'],
 'next_step':'Add reusable makeup preset replay and layer visibility/opacity controls, then refine a chosen art style and verify it in the full outfit. Keep garment collisions paused.',
 'report':str(report),'evidence':evidence,'new_commit_or_push':False}
write(OUT/'final_delivery.json',delivery);write(ROOT/'projects/whale-maid/COSMETICS_WORKING_STATE.json',delivery)
state.update(native_tools=85,next_step=delivery['next_step'],cosmetics_texture_tools={'delivery':str(OUT/'final_delivery.json'),'stage':delivery['stage'],'new_tools_this_stage':3,'nail_masks_implemented':True,'local_makeup_brushes_implemented':True,'editable_independent_makeup_candidate':evidence['candidate'],'actual_makeup_applied_to_production':False},latest_cosmetics_validation={'python_passed':383,'python_skipped':1,'js_groups_passed':5,'production_artifacts_unchanged':True})
write(appearance/'WORKING_STATE.json',state)
report.write_text(f'''# 局部面妆笔刷与遮罩 v03（2026-10-19）

本轮交付了能预览、限制绘制范围、写入真实新图层的局部面妆工具，以及独立可编辑的淡妆候选。腮红、唇部外沿晕染和眼皮笔触均完成像素比对、撤销/重做、保存新文件及新进程重开。当前服装仍为 hem-align-v22；正式 Blender/XWear/XRoid/VRM 哈希核对保持，未将示范妆直接写入整套装配。

## 画板、部位和真实材质

| 原生画板 | 实际用途及遮罩来源 | 尺寸 | 原生渲染去向 |
|---|---|---|---|
| Cheek | 现有腮红层的真实透明范围，两块独立区域 | 1024×1024 | Face_00_SKIN |
| MouthLine | 现有外沿透明范围，可显式扩展；示范扩展 8px | 1024×1024 | Face_00_SKIN |
| Eyelid | 真实原生眼皮覆盖网格的 UV 三角形，260 点；不使用整张不透明底图作为遮罩 | 1024×256 | FaceEyeline_00_FACE |
| Mouth | **口腔内部**，不是口红区域；局部面妆工具拒绝此项 | 512×512 | FaceMouth_00_FACE |

三种遮罩都记录实际模型身份、原生 region/image/layer 地址、参考层哈希、尺寸和遮罩哈希；眼皮还记录实际 UV 几何摘要。更换模型、重开进程、改参考层或画板不匹配都会拒绝旧遮罩。生成笔触后、真正写入之前再复核一次参考，避免绘制期间引用变化。口红目前是唇部外沿局部晕染，不能称任意模型的完整嘴唇自动分割。

## 新工具与使用顺序

新增 3 个工具，实际 stdio **85**：

1. `export_makeup_region_mask`：从当前正确画板及参考层取得可绘制边界，输出各连通区域的范围和中心，便于决定落笔位置。
2. `preview_makeup_marks`：生成透明预览 PNG，不改模型。支持软/硬椭圆印章、连点笔触、旋转、长宽比、RGBA、画布镜像；镜像同时反射旋转角。点坐标是左上原点的归一化画布坐标，不是世界坐标或 Unity UV。
3. `paint_makeup_marks`：使用同一套生成逻辑，以真实原生命令新增图层，保留原层并报告历史命令数。允许控制新层透明度；不自动保存，也不模拟鼠标拖拽。

每像素四点抗锯齿；同一连续笔触内采用最大覆盖，避免加密采样后颜色意外变浓；不同笔触按输入顺序做透明叠加。每次最多 32 笔、4096 个采样印记，像素工作量和图像大小有限额；越界参数、NaN、空白/非局部透明参考和无命中笔触均在原生写入前拒绝。眼皮几何遮罩不能随意膨胀。

正确链路是：先列出当前区域，打开对应原生画板（需要保留 RGB 时显式 `bake_colors=True`），重新列出图层，导出新遮罩，预览，再绘制为新层。颜色烘焙是单独的前序操作；撤销新笔触只按该次返回的历史命令数处理。重开后重新取得模型/区域/层/遮罩 ID。

可复用的示范配方在 `{OUT/'makeup-recipe.json'}`，不固化旧会话 ID。重放时必须先核对新遮罩 PNG 哈希及尺寸；不能把这份画布坐标无条件套到另一套 UV 上。当前尚未封装预设管理/一键重放或图层显隐编辑工具，这是后续工作。

## 原生验证与视觉证据

- Cheek：遮罩 80984 像素，实际笔触 58732；MouthLine：遮罩 4154，笔触 3333；Eyelid：遮罩 189296，笔触 27354。三种笔触 PNG 与原生导出、冷重开导出都经独立 Pillow/NumPy RGBA 比对一致，遮罩外绘制均 **0**。
- 原生实际渲染贴图补验：唇部增加 3333 个变更像素、眼皮增加 26398 个变更像素，两者在对应遮罩之外的变更均 **0**。六个其他面部材质（口腔、虹膜、高光、眼白、眉毛、睫毛）PNG 哈希保持。
- 三个原有底层哈希分别保持；每种新图层都完成 Undo 删除、Redo 恢复及内容哈希验证。三类旧遮罩在新进程中均被拒绝。最终写入边界另在冷打开的候选副本中以透明测试层验证，立即撤销且没有保存。
- 最终候选的正面、左右斜面、睁闭眼原生图已检查。独立文件 `{evidence['candidate']['path']}`；浏览入口 `review.html`。它是工具示范与可继续调整的妆容候选，不是用户最终美术采用。

## 真正闭眼采集

旧 `preview_expression(Close)` 返回成功但画面仍睁眼；仅设置 SkinnedMeshRenderer 的形变权重同样会被相机本帧蒙皮缓存覆盖，因此 v01～v03 的闭眼过程图不采用。最终 v04 使用已读取的 Fcl_EYE_Close、左右 Close 身份及原生帧权重 100，实际 BakeMesh 得到约 38.49mm 的最大顶点变化，再用原材质、变换和层的临时静态渲染器给采集相机渲染。实际图已显示闭眼，睁闭眼 PNG 也不同；权重应用和恢复读回通过，采集前后全部形变权重相同，临时对象/相机/网格释放，原渲染器启用状态恢复。**这是仅供采集的临时原生烘焙网格，不是持久表情或动画资产。**

`capture_texture_detail` 增可选 `eye_closure`，默认 None 沿用普通采集；不修改表情定义，不保存模型。`inspect_texture_renderers` 可读实际面部形变名称、当前权重和原生帧单位，用于确认目标身份。

## 测试、过程和保护

383 Python 通过 / 1 权限跳过，新增 33 项（含 PNG 五种滤波、剪裁、混色、旋转镜像、笔触重复、资源身份、源变化与写入边界）；5 组 JS 回归及语法检查通过。本轮 {len(rows)} 份源码快照按哈希/语法核对，独立镜像在 `VRoid-MCP/pipeline/cosmetics-textures-v03/`；原有 68 个 server 工具函数 AST 保持。

首次区域探查误把 Lip 当作现有类别，读到 FaceSkin/Cheek 后停止、未保存；随后按实际 Mouth/MouthLine/Eyelid 读回。native-v01 误将眼皮实际使用的眼线材质也列入保护项，完整绘制后在最终检查中止、未保存；v02 按真实目标修正检查，验证眼皮只改自己的眼线图集、脸部皮肤图集保持。无不确定保存重试，所有过程保留。

本轮没有修改发束 agent/parameters.js，没有更新共享全局源码快照，没有切换 Blender、重启其他 lab 或提交推送。原生验证仅使用 lab-clothing-fit-v17。沙箱默认临时目录首轮测试失败后改用项目 TEMP，在授权运行环境完成测试；未修改系统权限/策略。整套最终美术采用及 Godot/AnotherMe 验收仍未完成，后裙碰撞继续暂停。
''',encoding='utf8')
html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>局部淡妆候选</title><style>body{font:16px system-ui;background:#eef1f5;color:#202b3d;max-width:1280px;margin:32px auto;padding:16px}img{max-width:100%;border-radius:14px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}figure{margin:0;background:#fff;padding:12px;border-radius:16px}figcaption{padding:8px 0}a{color:#275bb8}.compare{position:relative;max-width:720px;margin:auto}.compare img{display:block;width:100%}.before{position:absolute;inset:0;clip-path:inset(0 50% 0 0)}input{width:100%;margin:16px 0}</style><h1>局部淡妆候选</h1><p>软腮红、唇部外沿晕染与轻眼皮笔触。独立可编辑候选，正式装配未覆盖。</p><h2>绘制前后</h2><p>拖动滑块：左侧原版，右侧候选。</p><div class="compare"><img src="evidence/cold-face_front.png"><div class="before" id="before"><img src="evidence/before-face_front.png"></div></div><input type="range" min="0" max="100" value="50" oninput="document.getElementById('before').style.clipPath='inset(0 '+(100-this.value)+'% 0 0)'" aria-label="对照位置"><h2>保存重开 · 多角度</h2><div class="three">'''
for name,title in [('cold-face_three_quarter_left','斜前方'),('cold-face_front','正面'),('cold-face_three_quarter_right','另一侧')]:html+=f'<figure><img src="evidence/{name}.png"><figcaption>{title}</figcaption></figure>'
html+='</div><h2>实际闭眼采集</h2><div class="pair"><figure><img src="evidence/detail/original-closed.png"><figcaption>原版</figcaption></figure><figure><img src="evidence/detail/candidate-closed.png"><figcaption>候选 · 临时采集后恢复</figcaption></figure></div><h2>逐部位绘制资料</h2><div class="three">'
for part,title in [('Cheek','腮红'),('MouthLine','唇部外沿'),('Eyelid','眼皮')]:html+=f'<figure><img style="background:#ddd" src="evidence/{part}/overlay.png"><figcaption>{title} · <a href="evidence/{part}/mask.png">边界遮罩</a> · <a href="evidence/{part}/marks.json">绘制参数</a></figcaption></figure>'
html+='</div><p><a href="evidence/bounded-makeup-candidate-v01.vroid">可编辑候选模型</a> · <a href="makeup-recipe.json">可复用配方</a> · <a href="final_delivery.json">验证记录</a></p>'
(OUT/'review.html').write_text(html,encoding='utf8')
print(json.dumps({'delivered':True,'tools':85,'source_files':len(rows),'candidate_sha256':evidence['candidate']['sha256'],'report':str(report)},ensure_ascii=False))
