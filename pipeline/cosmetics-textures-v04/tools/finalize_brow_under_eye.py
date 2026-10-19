"""Package isolated v04 eyebrow/under-eye tooling and native evidence without adopting production art."""
import ast,hashlib,json,shutil,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/cosmetics-texture-tools-v04';N=ROOT/'projects/whale-maid/diagnostics/brow-under-eye-native-v02'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def asset(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
assert not OUT.exists(),'Completed delivery must not be overwritten'
acceptance=read(N/'acceptance.json');pixels=read(N/'pixel-acceptance.json');assert acceptance['passed'] and pixels['passed'];assert read(N/'catalog.json')['count']==85
for p in pixels['parts'].values():assert p['rendered_changed_outside_mask']==p['paint_outside_mask']==0 and p['input_native_cold_rgba_equal'] and p['rendered_cold_rgba_equal']
for key in ('source','saved'):assert asset(Path(acceptance[key]['path']))['sha256']==acceptance[key]['sha256']
suite=ET.parse(ROOT/'work/brow-under-eye-tests-final-20261019.xml').getroot().findall('testsuite');counts={k:sum(int(s.attrib.get(k,0)) for s in suite) for k in ('tests','failures','errors','skipped')};assert counts=={'tests':395,'failures':0,'errors':0,'skipped':1}
appearance=ROOT/'projects/whale-maid/accessory-refinement-v02';state=read(appearance/'WORKING_STATE.json');assert state['current_candidate']=='hem-align-v22'
protected=read(appearance/'hem-align-v22/final_delivery.json')['artifacts']
for r in protected.values():assert asset(Path(r['path']))['sha256']==r['sha256']
OUT.mkdir();evidence={}
def copy(p,name):
 target=OUT/'evidence'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);return asset(target)
copy(ROOT/'projects/whale-maid/COSMETICS_WORKING_STATE.json','previous-cosmetics-working-state.json');copy(appearance/'WORKING_STATE.json','previous-appearance-working-state.json')
for p in N.iterdir():
 if p.suffix in ('.json','.png','.vroid'):evidence[p.name]=copy(p,p.name)
write(OUT/'visual-review.json',{'passed':True,'actual_native_images_inspected':['before-open','after-FaceSkin','cold-open','cold-closed','candidate-left','candidate-right'],'brow_tint_preserves_original_shape':True,'under_eye_shadow_highlight_on_skin':True,'v01_stronger_example_retained_not_selected':True,'candidate_only':True,'final_art_adopted':False})
parts=[]
for part in ('Eyebrow','FaceSkin'):
 mask=read(N/(part+'-mask.json'));marks=read(N/(part+'-marks.json'))
 parts.append({'part':part,'area':mask['area'],'mask_options':{'alpha_threshold':1,'padding_px':0,'area':mask['area']},'expected_mask_png_sha256':mask['mask_png_sha256'],'image_dimensions':[mask['width'],mask['height']],'marks':marks,'opacity':1.})
write(OUT/'makeup-recipe.json',{'schema':'vroid-bounded-makeup-recipe-v1','name':'Brow tint and soft under-eye shadow/highlight v04','reference_base_sha256':acceptance['source']['sha256'],'candidate_only':True,'parts':parts,'replay_policy':'Relist region/layers, explicitly bake colors if necessary, export a FRESH mask, check dimensions and mask PNG hash before replaying these canvas coordinates. For a different face shape or UV use newly exported guide points instead. Never reuse old native IDs. Preview before painting a new layer.'})
names=['VRoid-MCP/agent/textures.js']+['VRoid-MCP/vroid_mcp/'+n+'.py' for n in ('texture_tools','texture_targets','texture_mapping','texture_input','bounded_paint','makeup_tools','face_regions','server','runtime')]+['VRoid-MCP/tests/'+n for n in ('test_face_regions.py','test_makeup_tools.py','test_bounded_paint.py','makeup_eye_pose_test.js')]+['tools/'+n+'.py' for n in ('clean_native_clothing','probe_brow_under_eye','accept_brow_under_eye','check_brow_under_eye_pixels','finalize_brow_under_eye')]
rows=[]
for name in names:
 p=ROOT/name;raw=p.read_bytes()
 if p.suffix=='.py':ast.parse(raw.decode('utf-8-sig'),filename=name)
 target=OUT/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);rows.append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
write(OUT/'source/source-snapshot.json',{'scope':'Cosmetics texture tools v04 isolated source pack; no global manifest or hair source replacement.','files':rows})
report=ROOT/'docs/眉毛与眼下纹理绘制_v04_2026-10-19.md'
delivery={'date':'2026-10-19','stage':'Eyebrow alpha-bound brush and geometry-derived FaceSkin under-eye painting','native_tools':85,'new_tools_this_stage':0,'extended_tool':'export_makeup_region_mask: Eyebrow and explicit FaceSkin area=under_eye','editable_makeup_candidate':evidence['brow-under-eye-candidate.vroid'],'source_makeup_candidate':acceptance['source'],'formal_appearance_candidate':'hem-align-v22','formal_art_applied':False,'whole_outfit_final_art_adopted':False,'godot_validated':False,'python_tests':{'passed':394,'skipped':1,'report':str(ROOT/'work/brow-under-eye-tests-final-20261019.xml')},'js_regression_groups_passed':5,'parts':acceptance['parts'],'pixel_acceptance':pixels,'other_face_materials_unchanged':6,'save_reopen_passed':True,'protected_artifact_hashes_verified':protected,'source_pack_files':len(rows),'source_pack_manifest':str(OUT/'source/source-snapshot.json'),'source_pack_mirror':str(ROOT/'VRoid-MCP/pipeline/cosmetics-textures-v04'),'report':str(report),'review':str(OUT/'review.html'),'makeup_recipe':str(OUT/'makeup-recipe.json'),'evidence':evidence,'limitations':['Eyebrow painting is clipped to current reference alpha, with optional bounded padding; automatic eyebrow shape replacement is not implemented.','Under-eye is a conservative face-skin band below actual paired eye openings, not automatic eye-bag shape segmentation. It paints 2D shadow/highlight, without new geometry.','Under-eye mapping requires the verified upright native FaceSkin topology/axes; missing or ambiguous eye holes, strong asymmetry or UV sharing are rejected.','Fresh masks are tied to model/image/layer/source/UV and actual face positions. Stale IDs and changed faces require re-export.','Existing layer visibility/opacity editing, preset manager and native 3D freehand painting remain pending.','This independent .vroid demo has not been applied to production XRoid/VRM or integrated into Godot.','Reload MCP to expose the updated mask schema; tool count remains 85.'],'next_step':'Add existing layer visibility/opacity editing and guarded preset replay, then refine the user-selected makeup style and verify full outfit integration.','hair_source_modified_by_this_task':False,'shared_global_source_manifest_modified_by_this_task':False,'new_commit_or_push':False}
write(OUT/'final_delivery.json',delivery);write(ROOT/'projects/whale-maid/COSMETICS_WORKING_STATE.json',delivery)
state.update(native_tools=85,next_step=delivery['next_step'],cosmetics_texture_tools={'delivery':str(OUT/'final_delivery.json'),'stage':delivery['stage'],'new_tools_this_stage':0,'nail_masks_implemented':True,'local_makeup_brushes_implemented':True,'eyebrow_brushes_implemented':True,'under_eye_brushes_implemented':True,'editable_independent_makeup_candidate':delivery['editable_makeup_candidate'],'actual_makeup_applied_to_production':False},latest_cosmetics_validation={'python_passed':394,'python_skipped':1,'js_groups_passed':5,'production_artifacts_unchanged':True})
write(appearance/'WORKING_STATE.json',state)
html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>眉毛与眼下绘制候选</title><style>body{font:16px system-ui;background:#edf0f5;color:#263044;max-width:1200px;margin:28px auto;padding:16px}img{width:100%;border-radius:12px}.pair,.three{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.three{grid-template-columns:repeat(3,1fr)}figure{margin:0;background:white;border-radius:16px;padding:12px}figcaption{padding:8px 0}a{color:#305bb0}.compare{position:relative;max-width:760px;margin:auto}.compare img{display:block}.before{position:absolute;inset:0;clip-path:inset(0 50% 0 0)}input{width:100%;margin:16px 0}.texture{background:#ddd}</style><h1>眉毛与眼下绘制候选</h1><p>保留眉形的轻改色，以及下眼部阴影与高光。独立可编辑示范，尚未应用到整套服装。</p><h2>绘制前后</h2><p>拖动滑块：左侧原版，右侧候选。</p><div class="compare"><img src="evidence/cold-open.png"><div class="before" id="before"><img src="evidence/before-open.png"></div></div><input type="range" min="0" max="100" value="50" aria-label="前后对照" oninput="document.getElementById('before').style.clipPath='inset(0 '+(100-this.value)+'% 0 0)'"><h2>多角度与闭眼</h2><div class="three">'''
for name,title in [('candidate-left','侧前方'),('cold-closed','闭眼 · 保存重开'),('candidate-right','另一侧')]:html+=f'<figure><img src="evidence/{name}.png"><figcaption>{title}</figcaption></figure>'
html+='</div><h2>绘制范围与笔触</h2><div class="pair">'
for part,title in [('Eyebrow','眉毛'),('FaceSkin','眼下皮肤')]:html+=f'<figure><img class="texture" src="evidence/{part}-overlay.png"><figcaption>{title} · <a href="evidence/{part}-mask.png">范围遮罩</a> · <a href="evidence/{part}-marks.json">绘制参数</a></figcaption></figure>'
html+='</div><p><a href="evidence/brow-under-eye-candidate.vroid">可编辑候选</a> · <a href="makeup-recipe.json">示范配方</a> · <a href="final_delivery.json">验证记录</a></p>'
(OUT/'review.html').write_text(html,encoding='utf8')
report.write_text(f'''# 眉毛与眼下纹理绘制 v04（2026-10-19）

眉毛已接入局部笔刷；眼袋/卧蚕可通过实际下眼部皮肤范围绘制阴影与高光。已在原生 VRoid 独立副本完成新增层、Undo/Redo、保存新文件及新进程重开，并实际查看正面、左右斜面及闭眼图。本候选仅作为工具与妆容示范，不覆盖正式 XRoid/VRM。服装仍 hem-align-v22，四种正式资产哈希保持。

## 定位与接口

扩展原有 `export_makeup_region_mask`，工具数保持 **85**；需要重载长驻 MCP 才能看到新参数。

| 画板 | 参数 | 遮罩来源 | 验证尺寸 |
|---|---|---|---|
| Eyebrow | area=region | 当前参考眉毛层的真实 alpha，支持分辨率限制内的可选小范围扩展 | 1024×256 |
| FaceSkin | area=under_eye | 真实面部眼眶开口的下缘，通过脸部表面三角形映射到编辑 UV | 1024×1024 |

眉毛保留现有轮廓，允许改色、局部加深及笔触；这不是自动替换眉形。下眼部定位焊接面部边界后识别左右两个独立、近似对应的眼眶开口，本例各 24 个边界点。不是拿 Eyelid 眼皮图集冒充眼下皮肤，也没有写死 UV 框或顶点编号。眼眶下缘按横向位置插值，限定在眼宽 1.5%～30% 以下、左右内收 4% 的皮肤带，再逐像素通过实际 FaceSkin UV 三角形回算面部位置。额外检查全部面部三角形，拒绝目标 UV 同时映射其他脸部表面的情况。

返回每侧阴影与高光的画布路径，方便按部位落笔。范围遮罩是保守的眼下皮肤绘制辅助，不是自动眼袋形状分割；当前原生坐标为 +Y 向上/+Z 向前，未知网格、眼眶缺失、明显不对称或 UV 共用会拒绝。绘制的是二维纹理，未修改眼袋/卧蚕几何。

FaceSkin 必须显式选择 under_eye，不允许以整张脸作默认遮罩；下眼部遮罩不能再扩张。遮罩沿用模型、画板、图片、参考层哈希及 UV 身份检查，并新增实际面部坐标摘要；即使 UV 不变，脸型改变也会拒绝旧范围。生成笔触后、真正写入前再次核对。坐标仍为左上原点归一化画布坐标。

## 原生证据

- 眉毛：遮罩内绘制 **9817** 像素，实际渲染贴图变化 **9736**；眼下：遮罩 **11070** 像素，笔触 **5190**，实际渲染变化 **4202**。两者实际渲染贴图及笔触的遮罩外变化均 **0**。Pillow/NumPy 独立比对输入、原生导出和冷重开导出 RGBA 完全一致，冷重开渲染图集也完全一致。
- 眉毛实际改变 FaceBrow 材质，眼下改变 Face_SKIN；其余六个面部材质（口腔、虹膜、高光、眼白、睫毛、眼线/眼皮）PNG 哈希保持。原有底层分别保持，两个新增图层 Undo/Redo 均通过；新进程拒绝旧遮罩。
- 睁眼、闭眼及斜面实际图均已检查；闭眼使用前一阶段验证的临时原生 BakeMesh 采集方式，采集结束恢复形变及渲染器。新候选 `{delivery['editable_makeup_candidate']['path']}`，SHA256 `{delivery['editable_makeup_candidate']['sha256']}`。
- 浏览 `review.html` 拖动前后对照，`makeup-recipe.json` 保存示范参数。重放必须重新列区/层、导出遮罩并核尺寸和遮罩哈希；不同脸型应采用新返回的路径，不能直接套用旧画布坐标。还没有预设管理器或既有层显隐/透明度编辑工具。

## 验证与保护

394 Python 通过、1 权限跳过，新增 11 项包含 UV 镜像重定位、UV 共用、缺眼眶、非流形、非法数值、退化 UV、错误比例及改变脸型后拒绝旧遮罩。5 组 JS 回归通过。{len(rows)} 份独立源码快照在 source/，镜像为 VRoid-MCP/pipeline/cosmetics-textures-v04，不更新共享全局源码清单。

最初 probe-v01 启动请求的文件不在 lab 中，被明确拒绝，未启动模型或保存；probe-v02 改用已有 lab 内候选，只读采集完成。native-v01 完成技术验证但眼下示范偏浓，保留对照；native-v02 降低强度并靠近眼下，完成完整独立保存重开，选作本轮示范。没有重试不确定保存。两个版本都只是独立候选，不是用户最终美术采用。

本轮仅修改 cosmetics 模块、测试、工具脚本及本线文档/状态；没有修改发束 agent/parameters.js，没有操作其他 lab、切换 live Blender、提交推送或进行 Godot 集成。后裙碰撞仍暂停。下一步可补既有图层显隐/透明度与受检预设重放，再按用户风格细化并进整套验证。
''',encoding='utf8')
print(json.dumps({'delivered':True,'source_files':len(rows),'candidate':delivery['editable_makeup_candidate'],'report':str(report)},ensure_ascii=False))
