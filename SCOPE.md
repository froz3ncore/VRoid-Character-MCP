# SCOPE — 工具层验收与发布状态（0.4.1 开发版）

本文件区分功能验收和对外发布；保留原 0.4.0 冻结范围的必做项，不通过删减要求宣称完成。
角色层（正式 v22 资产、鞋、坐姿、VRM 内容检查）不在本文件范围内，只作为工具层的端到端验收场景。

历史基线：`91fb34c` / `checkpoint-toolset-20261019`，85 工具。
当前开发版：92 工具。公开主仓库为 `froz3ncore/VRoid-Character-MCP`，默认 `main` 使用独立历史；旧开发历史仅在本地保留。新功能适配了后续 MIT 授权的上游版本，第三方许可和声明见 LICENSE／LICENSING.md／NOTICE／UPSTREAM.json。

新增连接现有 VRoid、普通编辑 VRM 0.x/1.0 导出、模型部件查看及替换。连接时操作真实会话，文件及衣柜仍属于用户；因为连接前的纹理和体型编辑历史不可知，连接模式禁止进入纹理编辑器及切换进入换装。独立副本支持保存新的自定义物品并核验文件与衣柜登记，真实连接模式仍拒绝该保存。详见工具参考。

## 必须做（Must）

2026-10-28 连续编辑更新：独立副本的异步 PNG 写入崩溃路径已通过主线程原生解码、
输入/结果持有及延后回调修复；已验证副本不再要求体型→纹理→换装之间重开进程。
见 RECOVERY.md 与 tools/check_continuous_editing.py。连接真实窗口仍保留历史未知限制。

后续可复现与恢复改进已加入开发树：`tools/doctor.py`、公开自制配件样例、体型编辑后
画板冷重开守卫、区域图像比较与身高／原生上衣矩阵。说明见 RECOVERY.md、PUBLIC_SAMPLE.md、
REGRESSION.md；外部用户验收和人工金标准采用仍待进行，见 BETA_TESTING.md。

| 能力 | 验收 | 当前状态 |
|---|---|---|
| 既有图层显隐/透明度 | 改既有层→读回→保存→新进程重开；Undo/Redo | 已实现 `set_texture_layer_state`。原生显隐、淡化、两命令 Undo/Redo、无操作零命令、旧状态拒绝及冷重开通过；像素/其他层保持 |
| 妆容预设受检重放 | 同一 recipe 在新 lab 重放，逐项核实际像素/层状态；失败不发布半成品 | 已实现 `tools/replay_makeup_recipe.py`。新 lab 两部位重放/保存/冷重开逐像素通过；第二部位错误遮罩导致零笔触写入、零保存；只支持精确底模/遮罩匹配，不自动迁移 |
| 逐束发色或明确降级 | 有实际像素变化证据 | 已明确降级为全局发色，逐束仍不承诺 |
| 一条命令验收 | 单元、工具 schema、JS 行为、清单，JSON + exit code | `tools/run_checks.ps1`；新增五组 JS 行为回归，语法检查不能替代行为测试 |
| 稳定性三件套 | 启动检测、单实例锁、工具身份 | 原有保护保留；本轮未清理注册表、未操作其他会话 |
| 发布工程 | 开发版本/说明/工具参考/清单一致；明确许可与来源 | 0.4.1 独立实现已公开发布，代码采用 MIT；第三方许可与来源独立保留，功能及美术验收边界不变 |

## 可以不做（Won't do in 0.4.0, kept for later)

- 头发 Clone / Smooth / SetCurve：API 已发现未封装，工程量不是研究项，等角色发型真正需要时再做。
- 自定义发丝贴图注册：未探明且只在特定发型上才有价值。
- M00 全覆盖：F00 是主验证目标；M00 只做不崩溃、不误写入，不承诺等价能力。
- 图层混合模式、分组、文件夹：先有显隐/透明度即可满足调妆。
- 妆容预设的图形化编辑/预览器：CLI 重放够用。

## 明确不做（Out of scope）

- 原生 3D 自由笔刷：所有绘制都是"生成透明 PNG + 走真实原生新增图层/历史命令"，不是模拟鼠标，也不是三维笔刷。
- 任意材质注册：只允许已核实的共享发材质/换装材质，不接受调用方任意材质。
- 动画资产导出：预览姿势是会话内状态，不写成 `.vroidpose`/动画资产。
- Godot 材质与物理：需单独做引擎端验证，工具层只负责交出一个可解析的 VRM。
- 后裙碰撞：继续暂停，交付里写明"未解决"，不默认它不存在。

## 逐束发色：判定结果（2026-10-19 已裁决）

已知事实（`work/hair-color-keys-v01/`、`hair-api-signatures-v03…v09/`）：

- `Model.SetColorParameter(groupId, ColorPath, Color)` + `SetBoolParameter` 门控读回精确，运行正常。
- `Level1BaseHair_*` 五个通道可寻址，但**不驱动**可见手绘发渲染。
- 可见发色在共享发材质（实测主色 `[0.19,0.28,0.53]`）；手绘发组元素是 `Template_<sha1>` 型。
- 材质颜色值寻址未解：80 种 GetColorParameter 组合与 colorKey 字段读取均已排除。

spike 实测（`work/spike-hair/report.json`、`work/spike-hair/colors-report.json`）：

| 路线 | 写入结果 | 可见渲染变化 | 判定 |
|---|---|---|---|
| 逐束：`Level1BaseHair_MaterialColor/ShadeColor/OverlayColor/EmissionColor/OutlineColor` 五通道设为品红 | 读回成功（5 项） | **0 像素**（640×640，changed_ratio 0.0） | 不支持 |
| 全局：`colors/Hair/All` 参数设为品红 | 读回成功 | **100922 像素 / 24.6%**，mean_abs_delta 68.4 | 支持 |

结论：

- **逐束发色降级**：0.4.0 只支持**全局发色**，用 `set_parameters(domain='colors', id='colors/Hair/All')`。SCOPE 勾掉"必须做"里的逐束项，README/TOOLS 的限制章节写清楚。
- 全局发色**不新增工具**，现有颜色参数接口已够；但需要把"读回 ≠ 可见"这条写进文档，避免下次又把读回当成功。
- 若将来必须逐束：下一步只有共享发材质颜色寻址（`EditableElementColorAccessor` / `BeginHairMaterialAdvancedEditCommand`），属于 0.5.0 的研究项，不阻塞收口。


## 什么算"工具层做完"

1. `tools/run_checks.ps1` 一条命令：TEMP 固定、单元测试、85 工具 schema/注册 smoke、分域原生验收（face/body、clothing/wear、texture/makeup、hair、VRM export），输出 JSON 报告与 exit code。
2. 干净 lab 端到端：新建 lab → 起 server → 载入底模 → 参数 → 换装 → 妆容/美甲 → 头发 → 保存 → 重开 → 导出 VRM → 独立解析，全程不手改文件、不临时改源码。
3. 版本 0.4.0 + CHANGELOG + LICENSE + 85 工具参考 + 快照 manifest + tag。

VRM 导出成功仅是必要条件。全部 Must 的验收证据及发布授权都满足，才能宣称工具层已正式交付。新检查器拒绝无效骨位/表情/弹簧引用并区分必需项与显式允许的缺项；仍不是完整 glTF/VRM 规范认证。旧 E2E 的 +1.409cm 比较混入了保存前换发型造成的测量变化，不能作为持久化故障证据。现先完成造型再按实时身高校准，以保存前、保存后及冷重开的同口径测量和缩放参数验收。Godot 导入、材质与物理需单独验证。

## 角色层（另计，不在本文件关闭）

1. 妆容/美甲/发型合并进正式 v22，重出 XRoid/VRM；
2. 鞋贴合（原 Tripo 面 + 局部修补/遮挡，不重建）；
3. 坐姿裙摆碎裂/穿插；
4. 正式 VRM 内容检查补 humanoid/表情/SpringBone 覆盖。

后裙碰撞维持暂停；交付文档必须写"未解决"。
