# External beta acceptance / 外部试用验收

Source: **0.5.0.dev0 development snapshot** (npm `0.5.0-dev.0`), **99 tools**.

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

## Current local evidence / 当前本机证据

Current source: **0.5.0.dev0** (npm `0.5.0-dev.0`), **99 tools**. Current offline
regression on Python 3.10 and 3.12 reports **548 passed / 1 skipped**, nine JS
behavior suites and a 334-file source manifest. Five character/file-workflow
tools were added without changing the earlier 94 input schemas. The current hash
is `sha256:1d3022489c6ec413d57310cb7e3251a3128847a12faabd331766032ab286be34`.

Native evidence dated 2026-10-28 covers five domains, continuous same-process
body/texture/Dress-up editing through XRoid/VRM with cold persistence. Expanded
attached-editing/file-workflow runs passed 25 checks each for F00/M00, including
new-character replacement, absolute Save As/open, in-place save backup and cold
character persistence, current-character Dress-up entry and XWear/XRoid round
trips. The separate F00 lifecycle run passed 18 checks; earlier 17-check editing
runs remain historical evidence.
The test-owned Windows file picker opens/cancels; interrupted PNG completions
survive agent unload and a different client can review the surviving edit receipt.
Use `tools/check_continuous_editing.py`, `tools/check_attached_editing.py` and
`tools/check_attached_sessions.py` with their documented new/exclusive directories.
Pass `--xwear <compatible-accessory.xwear>` to `check_attached_editing.py` for
the complete 25-check run; omitting it skips XWear import and XRoid save/reopen.
See [ATTACHED_SESSION.md](ATTACHED_SESSION.md) for the command and file semantics.

当前已核构建的同进程解码崩溃路径已修复；旧失败报告保留为失败记录。真实连接验收使用
独立启动 profile，已检查原生未保存弹窗、进度锁、Windows 文件选择器打开／取消和服务
强退后的恢复。真实用户 profile、任意复杂人机同时编辑、所有保存／覆盖弹窗、长时间 GC 压力和系统崩溃
仍需独立验收。版本／文档修改仅重跑离线检查，不等同于重新运行这些原生流程。

The earlier public sample and 10-case F00 matrix retain their own dated evidence.
A three-view technical regression baseline was explicitly adopted on 2026-10-20;
final character art and independent-user acceptance are still pending. See
[REGRESSION.md](REGRESSION.md) for the controlled baseline's scope.

## CI scope / 持续集成范围

The Windows workflow defines Python 3.10/3.12 jobs for unit tests, MCP input
schemas, JS behavior and source-manifest verification on clean hosted checkouts.
It contains no VRoid and does not run native/visual E2E. A workflow file or a local
pass does not establish that CI ran for a newer commit.

The historical Python 3.12 import failure was fixed in `182a0d1` and its recorded
[run](https://github.com/froz3ncore/VRoid-Character-MCP/actions/runs/39386293369)
passed. Later commits need their own CI result; this page does not transfer that
old result to the current revision.

CI 是离线代码回归；原生运行、保存重开和视觉检查需要相应本机或外部证据。技术基准已
采用不等于外测通过，工作流存在也不等于当前提交的远程执行通过。
