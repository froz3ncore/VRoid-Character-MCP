# External beta acceptance / 外部试用验收

Status: **ready for independent testing; external acceptance pending**. A local
clean checkout, CI, or another process on the developer's machine is not an
independent user's reproduction. No stable release is certified by this page.

状态：**已准备外测流程，第三方验收待进行**。开发者本机的新进程、干净目录和 CI
都不能替代外部用户复现。本页不宣称稳定版本已通过验收。

## Tester task / 试用者任务

Use a clean checkout or source archive, Windows x64, your own supported VRoid
2.14.0 installation and Blender. Follow the README without copying the
developer's environment or using private demonstration assets:

1. Install Python/npm dependencies; record interpreter, OS and Blender versions.
2. Run [doctor](RECOVERY.md); retain `doctor-result.json`. Unknown builds should
   be refused. Keep the original installation and character files unchanged.
3. Run [the public sample](PUBLIC_SAMPLE.md) into new lab/output directories.
4. Open the produced `.vroid` / `.xroid` in your isolated copy and inspect the
   actual makeup layer and orange diagnostic accessory. Record what is visible.
5. Run [static repeatability](REGRESSION.md) and inspect before/after/difference.
6. Report the first blocking step verbatim, how much help was required, and
   whether the recovery instructions were sufficient. Preserve failed logs.

试用者按 README 从干净目录开始，先诊断，再运行公开样例，实际打开保存文件和查看
截图，最后复采比较。记录第一个阻碍、完整错误、是否需要额外帮助及恢复说明是否
有效；不要让开发者事后修改日志来补成通过。

## Return record / 反馈记录

Copy and fill the JSON below locally. Remove private paths/names from a copy
before sharing. Do not upload character models, source textures, profiles or
VRoid binaries by default; logs may also contain local identifiers.

```json
{
  "schema": "vroid-external-beta-acceptance-v1",
  "tester_alias": "",
  "source_revision_or_archive_sha256": "",
  "machine_environment": {"windows": "", "python": "", "blender": ""},
  "developer_environment_reused": false,
  "doctor": {"exit_code": null, "report_attached": false},
  "public_sample": {"exit_code": null, "report_attached": false},
  "saved_model_opened": false,
  "makeup_layer_observed": false,
  "diagnostic_accessory_observed": false,
  "repeatability_report_reviewed": false,
  "first_blocking_step": null,
  "exact_error": null,
  "help_required": "",
  "recovery_result": "",
  "accepted_by_tester": false
}
```

Before calling this stable: obtain at least **two independent tester records**,
resolve or explicitly document every blocking installation/data-loss issue,
and review actual saved outputs. Keep hairstyle-dependent height measurement, limited M00 support,
global-only visible hair colour, unfinished skirt collision and engine physics
boundaries explicit. Functional acceptance and character-art adoption are separate.

稳定版前至少需要两份独立试用记录，并处理或明确标注安装阻碍和保存风险，实际检查
产物。发型影响身高测量、M00 范围、逐束可见发色、裙摆碰撞和引擎物理边界继续保留。工具验收
与角色最终美术采用分别记录。

## CI scope / 持续集成范围

Historical native verification (before the decoder fix): the corrected hair-first height tests passed at
151.8 / 157.8 / 165.8 cm with unchanged live height and scale after cold reopen.
An additional same-process chain passed texture persistence checks, then crashed
in native code while opening Dress-up (`script has been destroyed`). Opening the
same hash-verified saved model in a fresh process, without texture-editor entry,
completed XWear assembly, XRoid save and independently parsed VRM export. The
same-process transition remains unresolved; this run is not a full E2E pass.
The current workaround refuses that transition after confirmed texture entry;
the sample and matrix use a separate fresh process for Dress-up/export.

本轮先换发型再校准的三个身高目标均保持；额外同进程链路在纹理核验后进入换装时
发生原生崩溃。相同哈希底模在新进程中、不进入纹理编辑器时，装配、保存和 VRM
独立解析通过。原崩溃尚未定位，不把该次完整 E2E 标成通过。
当前守卫会提前拒绝同进程切换；公开样例与矩阵把换装和导出放在新的独立进程中。

2026-10-28 superseding result: the reproduced async PNG buffer-writing failure
is addressed in managed copies by main-thread native decoding and deferred
callbacks. F00 and M00 each passed 20 body-to-texture entries, same-process
Dress-up/XRoid/VRM export, exact renderer-to-VRM face-texture pixels and a later
cold persistence check. Use tools/check_continuous_editing.py. The earlier failed
run remains a failure; independent-user acceptance is still pending.

上段为历史失败与旧规避。本次修复后，已验证独立副本可在同一进程连续编辑及导出；
真实连接模式另有受控验收：tools/check_attached_editing.py 检查既有未保存状态、原生弹窗、
禁用 Windows 主窗口、纹理像素与撤销、自定义物品以及编辑中断后的回调／操作记录恢复。
该测试使用独立启动 profile；已核对测试文件选择器打开／取消，真实用户 profile、任意原生保存／覆盖弹窗、
任意复杂人机同时编辑和系统崩溃仍需独立验收。外部用户仍需独立复验，不能把开发者本机通过当成外测通过。

The Windows workflow runs unit tests, MCP input-schema checks, JS behaviour and
source-manifest verification on clean hosted checkouts. It retains reports on
failure as well as success. It does not contain VRoid or run native/visual E2E.
Workflow setup follows [GitHub's Python testing documentation](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).

CI 是离线代码回归；原生副本、VRoid 保存和截图仍需要独立的本机／外部验收。工作流
文件存在不等于已经在 GitHub 上执行通过。

The Python 3.12 backport-import failure was reproduced locally and fixed.
[Run 39386293369](https://github.com/froz3ncore/VRoid-Character-MCP/actions/runs/39386293369)
passed for the CI/transition fix (`182a0d1`); later commits require their own
Actions result. Current local 3.10/3.12 checks report 502 passed / 1 skipped.
The fresh public sample and expanded 10-case native matrix also passed; human
baseline approval and independent-user acceptance remain pending.
