# Reproducible sample / 可复现样例

This sample generates its own small orange diagnostic accessory. It does not
require the private clothing or character files used in earlier demonstrations.
The generated Blender source is retained alongside the XWear. It is a test
fixture, not finished clothing or a visual-fit benchmark.

The workflow uses separate processes for editing/saving, cold texture verification,
and Dress-up/export to verify saved-state persistence independently. The reproduced
transition crash has been addressed for verified decoders; same-process evidence
is provided by `tools/check_continuous_editing.py`. The sample does not discard
unsaved work or automatically retry an uncertain write.

样例会自行生成一个橙色小配件，并保留 `.blend` 源文件和 XWear，不依赖历史展示中的
私人角色或服装。这个配件用于检验蒙皮、导入与导出，不代表成品服装或贴合验收。

## Run / 运行

Install the repository's Python/npm dependencies, your own supported VRoid Studio
2.14.0 installation, and Blender 4.2 or newer. Run in a normal terminal that
permits local loopback. The new lab requires space for a full application copy.
`--lab` and `--out` must both be new directories, separate from each other, the
repository and source installation. No live Blender session is used.

安装仓库依赖、兼容的 VRoid Studio 和 Blender 4.2+ 后，在允许本机回环连接的普通终端
运行。副本需要完整程序的磁盘空间。两个输出目录都必须是新目录，不能互相包含，也
不能与仓库或源安装互相包含。脚本使用单独的后台 Blender，不接触正在编辑的场景。

```powershell
& .\.venv\Scripts\python.exe .\tools\run_sample.py `
  --source "C:\Program Files\VRoid Studio" `
  --blender "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe" `
  --lab "D:\VRoid-Sample-Lab" `
  --out "D:\VRoid-Sample-Results"
```

The command checks the installation, generates the asset, prepares the lab, then
starts successive MCP-owned VRoid processes for those separate phases. It creates a native base model,
adds a Cheek layer, changes a face parameter and height, applies a native hair
preset, saves, cold reopens, checks layer PNG and parameter persistence, imports
the generated accessory in Dress-up, saves `.xroid`, exports VRM and parses it
independently. It also captures the edited model, reopened model and assembly.

命令依次预检、生成配件、准备新副本，再用各阶段独立进程完成底模→妆容→参数／身高→
发型→保存→冷重开→换装导入→保存装配→VRM 导出→独立解析，并保留编辑后、重开后及
装配的原生截图。冷重开会核对妆容 PNG 哈希，不能仅凭图层名称判定成功。

## Evidence / 证据

| Output / 输出 | Meaning / 含义 |
|---|---|
| `sample.json` | Overall result and exact stage logs / 总结果与阶段日志 |
| `doctor.json` | Dependency, binary and environment preflight / 安装与环境预检 |
| `asset/sample-badge.blend`, `.xwear`, `asset.json` | Original editable source, export and generator hashes / 可编辑源文件、导出及生成器哈希 |
| `e2e.json` | Native steps, hashes, live-height/scale persistence, independent VRM findings and review paths / 实际步骤、哈希、实时身高及缩放持久化、独立解析与截图路径 |
| Lab `saves/`, `reviews/`, `runs/` | Saved models, captured images and native/bridge logs / 模型、截图及原生日志 |

Exit codes: **0** all stages passed, **1** a stage failed, **2** input paths were
rejected before output creation. Failed outputs are kept. Choose new directories
for a new attempt, inspect the failing stage, and never automatically replay an
uncertain native write. Recovery is described in [RECOVERY.md](RECOVERY.md).

退出码：0 全通过；1 某阶段失败；2 路径预检拒绝。失败目录保留，用新目录重跑，先检查
失败日志，不自动重试结果不确定的原生写入。恢复见 [RECOVERY.md](RECOVERY.md)。

Exact VRM, `.vroid` and `.xroid` hashes are recorded for that run; generated IDs
can differ across runs. Hair is applied before final live-height calibration;
save/reopen must preserve live height within 0.05 cm and body scale within 1e-6.
A passing run does not mean collision-free clothing, full VRM specification conformance,
game-engine physics, or independent external-user acceptance. Native presets
and generated avatars retain their own terms; the source generator and its
original badge geometry are MIT, not a grant of rights over those other assets.

文件中含生成的身份值，跨运行不承诺二进制哈希相同。先换发型再校准，保存和冷重开
必须保持实时身高（0.05 cm 容差）与缩放参数（1e-6 容差）。服装碰撞、规范全认证、引擎物理和外部用户
复现仍需另验。生成器和自制配件几何采用 MIT；原生预设及角色仍遵循其自身条款。
