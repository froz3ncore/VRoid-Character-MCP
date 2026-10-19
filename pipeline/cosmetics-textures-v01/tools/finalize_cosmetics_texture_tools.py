"""Collect verified cosmetics capability evidence without changing the art baseline."""
import ast,hashlib,json,shutil,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/cosmetics-texture-tools-v01'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def asset(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def copy(p,name):
 target=OUT/'evidence'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);return asset(target)

if OUT.exists():assert not any(OUT.iterdir()),'Refuse to overwrite a completed delivery'
else:OUT.mkdir()
D=ROOT/'projects/whale-maid/diagnostics'
face=D/'cosmetics-face-map-v01';body=D/'cosmetics-body-map-v02'
catalog=read(face/'tool-catalog.json');assert catalog['tools']==77
roundtrip=read(D/'cosmetics-integrated-roundtrip-v01/acceptance.json');body_roundtrip=read(D/'cosmetics-body-texture-roundtrip-v01b/acceptance.json');assert roundtrip['passed'] and body_roundtrip['passed']
assert (D/'cosmetics-integrated-roundtrip-v01/undo-layers.json').is_file() and (D/'cosmetics-integrated-roundtrip-v01/redo-layers.json').is_file()
tests=ET.parse(ROOT/'work/cosmetics-texture-tests-final-20261019.xml').getroot();suites=tests.findall('testsuite');counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')};assert counts=={'tests':323,'failures':0,'errors':0,'skipped':1},counts

# Existing tool implementations, including all hair authoring tools, remain identical.
before=ROOT/'work/cosmetics-integration-v01/before/vroid_mcp/server.py';after=ROOT/'VRoid-MCP/vroid_mcp/server.py'
def tools(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(p.read_text(encoding='utf8'))) if isinstance(n,ast.AsyncFunctionDef) and n.decorator_list}
old=tools(before);current=tools(after);assert all(current[n]==v for n,v in old.items());assert len(old)==70 # 68 tools plus lifespan and ready wrapper
isolation=read(ROOT/'work/cosmetics-mcp-v01/SOURCE_ISOLATION.json')
hair_current=asset(ROOT/'VRoid-MCP/agent/parameters.js')['sha256']
hair_changed_elsewhere=hair_current!=isolation['files']['agent/parameters.js']

evidence={}
for label,folder in [('face',face),('body',body)]:
 for record,filename in [('uv-guide','uv-guide.png'),('surface','surface.json'),('layer-export-0','base-layer.png')]:
  entry=read(folder/(record+'.json'));p=Path(entry['path']);assert asset(p)['sha256']==entry['sha256'];evidence[label+'_'+record]=copy(p,label+'-'+filename)
 evidence[label+'_canvas']=copy(folder/'canvas.json',label+'-canvas.json')
 surface=read(Path(read(folder/'surface.json')['path']));assert all(len(m['positions'])==len(m['uv0'])==len(m['weights']) for m in surface['meshes'])
 for m in surface['meshes']:
  assert all(b.get('identity') or b.get('name') for b in m['bone_ids'])
 evidence[label+'_vertices']=sum(len(m['positions']) for m in surface['meshes'])

source_names=['VRoid-MCP/agent/textures.js','VRoid-MCP/agent/operations.js','VRoid-MCP/vroid_mcp/texture_tools.py','VRoid-MCP/vroid_mcp/texture_input.py','VRoid-MCP/vroid_mcp/server.py','VRoid-MCP/vroid_mcp/runtime.py','VRoid-MCP/tests/test_texture_input.py',
 'tools/probe_makeup_nail_controls.py','tools/probe_cosmetics_texture_api.py','tools/inspect_cosmetics_api_batch.py','tools/accept_cosmetics_texture_read.py','tools/accept_cosmetics_canvas.py','tools/accept_cosmetics_texture_roundtrip.py','tools/finalize_cosmetics_texture_tools.py']
source_rows=[]
for name in source_names:
 p=ROOT/name;data=p.read_bytes()
 if p.suffix=='.py':ast.parse(data.decode('utf-8-sig'),filename=name)
 target=OUT/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 source_rows.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'git_lf_sha256':hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()})
write(OUT/'source/source-snapshot.json',{'scope':'Cosmetics tool integration and validation source pack. Shared global/hair snapshot manifest left unchanged. Do not replace later source files blindly; see preserved before hashes.','files':source_rows})

appearance=ROOT/'projects/whale-maid/accessory-refinement-v02';state=read(appearance/'WORKING_STATE.json');assert state['current_candidate']=='hem-align-v22' and asset(Path(state['source']['path']))['sha256']==state['source']['sha256']
copy(appearance/'WORKING_STATE.json','previous-appearance-working-state.json')
report=ROOT/'docs/面妆美甲纹理工具基础链路_v01_2026-10-19.md'
delivery={'date':'2026-10-19','stage':'Native cosmetics texture I/O and exact canvas mapping foundation','new_tools':['list_texture_regions','open_texture_editor','inspect_texture_canvas','list_texture_layers','export_texture_layer','import_texture_layer','export_texture_guide','export_texture_surface','close_texture_editor'],
 'native_tools':77,'previous_tools':68,'existing_tool_implementations_unchanged':68,'hair_agent_modified_by_this_task':False,'concurrent_hair_source_changes_observed':hair_changed_elsewhere,'hair_source_current_sha256':hair_current,'evidence':evidence,
 'native_cheek_import_undo_redo_save_reopen':str(D/'cosmetics-integrated-roundtrip-v01/acceptance.json'),'native_body_import_save_reopen':str(D/'cosmetics-body-texture-roundtrip-v01b/acceptance.json'),
 'python_tests':{'passed':322,'skipped':1,'report':str(ROOT/'work/cosmetics-texture-tests-final-20261019.xml')},'js_regression_groups_passed':4,
 'source_pack_files':len(source_rows),'source_pack_manifest':str(OUT/'source/source-snapshot.json'),'shared_global_source_manifest_modified':False,
 'formal_appearance_candidate':'hem-align-v22','formal_appearance_source_unchanged':True,'actual_makeup_or_nail_art_applied':False,
 'freehand_brush_strokes_implemented':False,'automatic_nail_masks_implemented':False,'model_point_to_uv_pick_implemented':False,
 'limitations':['Native canvas mapping and UV guides are real; semantic masks for lips/cheeks/nails are not automatically inferred.','Finger-specific nail masks, left/right UV sharing calibration and world-point/ray UV picking remain next.','Native 2D/3D brush entry points were discovered but not exposed as painting tools.','No formal makeup/nail art or Godot acceptance; independent invisible test layers only.','Current long-running MCP connection must reload to expose the updated tool catalog; no other session was restarted.'],
 'next_step':'Calibrated model-point/triangle-to-UV picking, finger/nail masks, then bounded native brush/stamp edits with roundtrip and visual acceptance. Additional garment trim work is lower priority.',
 'report':str(report),'new_commit_or_push':False}
write(OUT/'final_delivery.json',delivery)
state.update(native_tools=77,development_priority='cosmetics texture tooling before further clothing ornament geometry',cosmetics_texture_tools={'delivery':str(OUT/'final_delivery.json'),'stage':delivery['stage'],'new_tools':9,'actual_makeup_applied':False,'nail_masks_implemented':False},user_overlap_decision='Accepted for now; defer clothing intersections/cloth solving to later Godot work; not a blocker for cosmetics tools')
write(appearance/'WORKING_STATE.json',state)
write(ROOT/'projects/whale-maid/COSMETICS_WORKING_STATE.json',delivery)
report.write_text(f'''# 面妆与美甲纹理工具基础链路 v01（2026-10-19）

用户明确优先级：服装目前够用，穿插暂不阻塞，后续可在 Godot 处理；接下来优先建设能识别贴图部位、UV 和图层的妆造工具，而非继续增加服饰几何。

## 已落地

新增 9 个 MCP 工具，主目录实际 **77** 个（此前实际为 68，AGENTS.md 的 65 为较旧记录）。原 68 个工具函数 AST 与合入前完全一致；仅以独立模块接入新纹理能力。本任务未修改发束 agent/parameters.js；观察到该文件有独立发型开发更新，已原位保留，不能声称其相对早期冻结源哈希不变。

| 能力 | 本轮状态 |
|---|---|
| 部位寻址 | 实际读取 transferable group/type、editable image 和图层 ID；没有启用的部位不虚构图层 |
| 原生画板 | 可打开脸部/身体纹理编辑页并读取当前类别、图像、引用纹理路径 |
| 图层 | 可列出名称、透明度、可见性、混合模式，导出真实原图 PNG |
| 写回 | 校验文件位置、PNG 尺寸和输入哈希后，以新图层导入，保留旧层 |
| UV 对应 | 导出同一原生画板的 UV 导引及其实际网格、三角面、UV、蒙皮和骨骼身份 |
| 历史与持久化 | 腮红 3 个命令的撤销/重做、保存新文件及新进程重开通过；身体贴图导入/保存重开通过 |

原生 face overlay **{evidence['face_vertices']}** 点，body overlay **{evidence['body_vertices']}** 点；它们与 editable image 的关联来自真实画板，并非把整张皮肤贴图笼统称为妆容。surface.json 是纹理编辑器覆盖网格坐标，不应当作实际世界/动作坐标。

## 证据与限制

- 入口：`{OUT/'final_delivery.json'}`；图像、UV 导引、网格在 evidence/；所有测试副本独立，正式服装仍为 v22，源哈希核对未变。
- 腮红原图→新透明测试层→原生导出→保存重开→再次导出，PNG SHA256 一致；身体贴图同样通过。测试层 opacity=0，**不是已经画好了妆或指甲**。
- 322 Python 通过 / 1 权限跳过，4 组 JS 通过。最初两次沙箱内异步测试被 Windows 回环 socketpair 阻塞；停止本任务这两次测试进程后，在授权环境重跑通过，未修改系统策略。
- 源码包 {len(source_rows)} 文件做哈希/AST 核对，另有 JS 语法核对；共享全局/发束快照清单未改，独立快照见 source/。未提交推送，未切换 Blender、未修改当前 XRoid/VRM。
- UV 导引为黑色透明线条，查看时需要白色/棋盘背景；PNG 本身保留透明度。

## 还缺什么

下一步是模型点/三角面与 UV 的校准拾取、指甲及局部妆容的语义遮罩、左右镜像/UV 共用关系，然后再封装限幅的笔刷/印章。原生二维/三维笔触入口确实存在，但本轮未封装为可绘画工具。没有独立美甲分类的证据，不能把类名 thumbnail 中的 nail 命中当成美甲 API。

腮红、嘴唇、眼周等可以利用本轮的原图/UV/图层链路制作贴图；若当前模型尚未启用对应原生项，先用已有预设工具创建再重新列区域。指甲仍需逐指甲面定位，不声称已能自动精确美甲。Godot 布料解算和最终妆造验收均未在本轮进行。

当前长驻连接需要重载后才能显示新增目录；本轮只在隔离应用中验证，没有重启其他开发会话。
''',encoding='utf8')

html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>纹理部位与 UV 核查</title><style>body{font:16px system-ui;background:#eceff4;color:#172033;margin:32px}section{display:inline-block;vertical-align:top;width:46%;background:white;padding:16px;margin:1%}img{width:100%;background:white}small{display:block}a{color:#2459b4}</style><h1>原生画板的贴图与 UV</h1><p>这些是实际导出资料，用于定位和工具验证；不是已经完成的妆造。</p>'''
for label,title in [('face','脸部'),('body','身体')]:
 html+=f'<section><h2>{title}</h2><p>原生 UV 导引（白色背景显示透明黑线）</p><img src="evidence/{label}-uv-guide.png"><p>原生底图层</p><img src="evidence/{label}-base-layer.png"><a href="evidence/{label}-surface.json">查看实际网格与 UV 数据</a></section>'
(OUT/'review.html').write_text(html,encoding='utf8')
print(json.dumps({'delivered':True,'native_tools':77,'new_tools':9,'source_pack_files':len(source_rows),'report':str(report)},ensure_ascii=False))
