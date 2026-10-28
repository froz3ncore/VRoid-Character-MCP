# Installation diagnostics and recovery / 安装诊断与恢复

Current source: **0.5.0.dev0 development snapshot** (npm `0.5.0-dev.0`), **103 tools**.
Current capabilities and dated acceptance scope: [SCOPE.md](SCOPE.md).

Run from the repository with the **same Python interpreter used by the MCP
client**. Diagnostics use the standard library, so missing Python packages can
be reported before the server imports them.

在仓库目录，用 MCP 客户端实际配置的 Python 执行。诊断入口只依赖标准库，
因此即使缺少 MCP／Frida，也能输出问题与处理步骤。

```powershell
# Before copying an installation / 复制安装前
& .\.venv\Scripts\python.exe .\tools\doctor.py --source "C:\Program Files\VRoid Studio"

# Before connecting an existing lab / 连接已有副本前
& .\.venv\Scripts\python.exe .\tools\doctor.py --lab "D:\VRoid-Character-Lab"

# Optional new JSON report; existing files are refused / 可选输出新报告，不覆盖旧文件
& .\.venv\Scripts\python.exe .\tools\doctor.py --lab "D:\VRoid-Character-Lab" --json .\doctor-result.json
```

Exit codes: **0** preflight passed, **1** a check blocked startup, **2** invalid
arguments or report I/O failed. `--format json` prints the structured report.
Reports include local paths; review them before posting them publicly.

退出码：**0** 预检通过，**1** 有启动阻碍，**2** 参数或报告读写错误。
`--format json` 可直接输出 JSON。报告包含本机路径，公开分享前请检查内容。

Diagnostics do not start VRoid, inject code, save models, clear registry keys,
or rewrite lock files. Existing lock bytes are briefly tested with an OS lock
and immediately released. Availability is a snapshot, not a reservation.
An all-pass result does not verify native injection, directory write access,
visual quality, saving or the full E2E workflow.

诊断不启动 VRoid、不注入、不保存模型、不清理注册表、不改写锁文件；只短暂测试
已有锁的操作系统字节锁并立即释放。副本空闲只是当时的状态，不会替你预占。
预检通过也不代表已验证注入、目录写权限、外观、保存或完整 E2E。

| Check / 检查项 | Recovery / 处理方式 |
|---|---|
| `dependency.frida`, `dependency.mcp`, `dependency.imports` | 用同一个解释器重新安装 `requirements.txt`，确认客户端没有指向另一个 Python。Install requirements with the client's interpreter. |
| `dependency.bridge` | 在仓库根目录运行 `npm ci`。Run `npm ci` in the repository. |
| `environment.asyncio` | 在允许本机回环连接的普通终端重跑。受限环境可能卡在 Python 事件循环创建阶段，超时本身不证明项目有错。Retry in a normal terminal with local loopback permitted. |
| `paths.physical`, `application.build` | 使用完整、受支持的 VRoid 2.14.0 安装，新建独立 lab；不要绕过哈希白名单。Use a complete supported installation and create a new lab. |
| `lab.ownership` | 使用另一个 lab，或从拥有它的客户端正常关闭服务；不要删除锁文件、按进程名终止全部 VRoid。Use another lab or close the owning client normally. |
| `registry.closet` | 先按下文备份，再明确执行恢复；读取权限错误也会阻止启动。Back up first; unreadable registry state also blocks startup. |

The [official VRoid page](https://vroid.com/en/studio) provides a **Past versions**
entry. Match the supported binary hashes in
[`supported_builds.py`](vroid_mcp/supported_builds.py), rather than trusting a
version label alone. Do not replace app files inside a lab with saved work;
prepare a new lab with `prepare_lab.py --source <installation> --lab <new-directory>`.
Historical evidence labs without `app/` should retain their saves and logs.

官网有 **Past versions** 入口；版本号相同也需要通过二进制哈希检查。不要在已有
保存和证据的 lab 里混换程序。缺少 `app/` 的历史验证目录应保留原记录，用新目录准备副本。

## Known crash registry key / 已知崩溃注册表键

The affected key is `HKCU\SOFTWARE\Classes\vroid.closet`. If diagnostics report
it present, stop the affected copy and review the change before explicitly
running this recovery command. It exports a backup to the lab's `crash-guard/`
before attempting removal. A failure to back up prevents removal. If registry
access is denied, retain the error and use a terminal with the required access.

仅当诊断报告该键存在时，先停止受影响副本，再明确执行以下恢复命令。程序先导出到
lab 的 `crash-guard/`，备份失败不会删除。权限不足时保留错误并在具备权限的终端处理。
诊断本身即使检测到 `VROID_MCP_CLEAR_CLOSET_KEY=1`，也不会触发删除。

```powershell
& .\.venv\Scripts\python.exe -m vroid_mcp.closet_guard --lab "D:\VRoid-Character-Lab" --clear
& .\.venv\Scripts\python.exe .\tools\doctor.py --lab "D:\VRoid-Character-Lab"
```

## Continuous editing / 连续编辑

On the validated build, MCP-owned copies decode PNGs on Unity's main thread
using VRoid's synchronous decoder, then deliver the original success/error
callbacks in a later frame. Inputs and results are retained until callback
delivery. The original asynchronous worker used a NativeArray view of a
Texture2D buffer; the reproduced access violation was inside its background
PNG-writing path. The replacement avoids that cross-thread storage lifetime.
It does not resample images or patch installation files.

`get_status.png_decoder` reports installation, mode, pending callbacks, decoded
counts and fatal errors. Model readiness and transitions wait for pending
callbacks. Body edits, texture editing and Dress-up can share one copy process.
The former empty Mesh Collider warning also occurs on successful transitions;
it is not sufficient evidence of a fatal mesh-cache defect.

当前已核构建的独立副本可连续改体型、编辑纹理及进入换装；不用通过重开进程规避本次
已复现的 PNG 解码崩溃。每帧最多处理四个解码请求，仍转发原生错误回调；内部失败会
阻止后续操作，不把失败当成功。兼容的真实窗口连接使用 VRoid 自己持有的完成回调；
已提交回调不依赖 MCP 存活。连接时等待旧解码任务结束，模态弹窗会阻止写入。
更新源码后需正常关闭旧 MCP 服务并重新载入 agent；先保存需保留的修改。

Reproduce through real MCP stdio on an exclusive prepared lab:

```powershell
& .\.venv\Scripts\python.exe .\tools\check_continuous_editing.py `
  --lab "D:\VRoid-Character-Lab" --out "D:\Continuous-Editing-F00" --variant F00 --cycles 5
```

The primary sequence stays in one process through body edits, four available
texture regions per cycle, diagnostic layer import, saving, Dress-up, XRoid and
VRM export. It checks exact renderer-to-VRM face-texture RGBA and independently
parses the VRM. Only afterwards does a second process verify saved body values
and layer pixels. Generated files have unique names; output must be new.
M00 uses its actually available regions, not assumed F00-only categories.

## Fallback texture-to-Dress-up guard / 未验证会话的换装守卫

`WEAR_NEW_PROCESS_REQUIRED` is retained for sessions without the validated
decoder. Once that MCP process has confirmed texture-editor
entry, `open_wear_project` is refused before the native transition, even after
closing the texture editor or loading another model. Reads and saving remain
available. `get_status.wear_transition_guard` explains the state.

Close the texture editor, save to a **new** `.vroid` if there are changes to keep,
and close the owning session normally. Start a fresh session without entering the
texture editor, list its new wear token, and open the confirmed saved file in
Dress-up. Nothing automatically restarts or discards unsaved work. The public
sample performs cold texture verification and Dress-up in separate processes.

未安装或未验证解码修复的会话进入过纹理编辑器后，会拒绝直接进入换装。
需要保留的修改先另存新文件，正常关闭所属会话，再用新进程、新 wear token 打开
确认保存的文件。此为未验证会话的保守回退；正常加载当前解码修复的独立副本不走此限制。

## Disconnected or uncertain edits / 断连或写入结果不确定

`TEXTURE_EDITOR_REOPEN_REQUIRED` is a fallback sequence guard. After a
confirmed body-parameter edit through `set_body_params`, `set_parameters`
(`domain=body`) or `set_height`, entering texture editing is refused before the
native call when the decoder fix has not been verified. Reads, capture and saving remain available. This conservatively
covers all body sliders, not only height. No-op writes do not trip it; Undo does
not prove the native overlay cache was rebuilt and does not clear it. It tracks
MCP-observed edits, not manual edits outside the session.

遇到此错误时，先另存新的 `.vroid`，正常关闭所属客户端的 MCP 服务，再以该文件通过
`--model` 启动新进程。不要丢弃未保存内容。原文件必须已在该 lab 内。优先把妆容安排
在体型调整之前。守卫保守覆盖所有体型滑杆；它不是原生缺陷已被修复的声明。

```powershell
# After saving a new file and closing its owning client / 另存并关闭所属客户端后
& .\.venv\Scripts\python.exe .\launch.py --lab "D:\VRoid-Character-Lab" --model "D:\VRoid-Character-Lab\saves\saved-copy.vroid"
```

1. Stop sending edits. A timeout does not show whether the original write ran.
2. Preserve `runs/`, `Player.log`, bridge logs and existing saved files. Do not
   assume an unconfirmed save succeeded, and do not retry it automatically.
3. Use `get_status` if still available. When edits are blocked, inspect the last
   confirmed saved copy separately. Unsaved work may not be recoverable.
4. Only after the operator explicitly accepts losing unsaved changes, use
   `restart_session(discard_unsaved=true)`. It recreates this client's copy;
   it does not safely resume the interrupted write or reopen every current state.
5. Relist the model/wear tokens and parameter/layer IDs. Old tokens, masks and
   in-memory identities must be discarded; reconstruct from confirmed evidence.

写入超时后先停止操作，保留日志和已有存档；不要把未确认的保存当成成功，也不要
自动重试。仍可读取时先取 `get_status`。只有操作者明确接受丢弃未保存内容后，才可
调用 `restart_session(discard_unsaved=true)`；重启不等于恢复未确认写入。随后重新获取
模型／装配 token、参数和图层身份，重新导出遮罩。

## Validation boundaries / 验证边界

For an attached user-opened window, a forcibly killed MCP host does not
automatically close VRoid. With the current attachment lease, start a new MCP
host, call `attach_open_vroid` on that same process, relist model state, and
detach normally to restore its pre-attachment background flag. The new model
token invalidates old requests. Recovery does not prove an interrupted write
completed or undo it. Another live host is refused; detach it through its own
client first. No saved character files are rewritten by lease recovery.

连接现有窗口时，若 MCP 服务被强制终止，当前版本会保留进程内恢复记录。重启 MCP、
连接同一 VRoid 进程、重新列出并检查模型状态，之后正常断开即可恢复连接前的后台设置。
后台设置在重新连接前可能仍为开启。不要重放结果未确认的写入；新连接需要新 token。
仍在运行的另一服务不会被抢占，请先通过原客户端断开。该恢复不覆盖旧版无记录的连接、
操作中途丢失的结果或系统崩溃。

若中断发生在真实窗口写入中，`get_status.attached_state.pending_edit` 会保留工具名称及
派发次数，并阻止新写入。先用只读工具核对参数、图层和新增文件，再调用
`get_attached_state` 取得新鲜的 `recovery_token`，交给 `acknowledge_attached_state`。
手动编辑、模型或文件关联变化会使旧凭据失效；弹窗／原生任务未结束时无法确认。
确认只恢复后续编辑，不重试、回滚或认定中断操作成功。记录属于 VRoid 进程，换客户端
仍可读取；VRoid／系统退出后不保留。详见 [ATTACHED_SESSION.md](ATTACHED_SESSION.md)。

人物文件操作失败时同时核对窗口与磁盘：`save_as` 只生成副本并保留原关联；
`save_character_as` 另存后才关联新文件，关联失败时新文件可能已经存在；
`save_character` 原位保存前保留核验过的备份，失败信息会给出原文件与备份路径。
不要直接覆盖或删除这些文件。`open_current_in_wear` 的切换失败也可能已经生成角色
副本；先检查返回信息中的路径和实际画面，再按上述流程检查、确认中断记录。
确认恢复只解除后续编辑限制，不证明原文件保存完整或自动恢复备份。

`tools/run_checks.ps1 -Native` runs read-only domain checks on an exclusive
prepared lab. Saving, cold reopening and exporting are tested separately by
`tools/e2e_clean_lab.py`, which requires a new lab and caller-provided XWear.
Doctor is a preflight for both; it is not a replacement for either.

`-Native` 是独占副本上的各领域只读检查。保存、新进程重开、导出由另一个 E2E
脚本验证；doctor 只是这些流程的启动预检。
