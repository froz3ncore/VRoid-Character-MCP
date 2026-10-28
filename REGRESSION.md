# Visual regression and bounded coverage / 视觉回归与覆盖范围

## Native repeatability / 原生静态复采

Use an exclusive prepared lab and a saved `.vroid` inside its `saves/` folder.
This starts one owned process, captures front/back/face, locks the first capture's
framing for the second capture, and compares exact decoded RGBA pixels. It does
not save the input. The source model and application hashes are recorded.

使用空闲的已准备副本及其 `saves/` 内的 `.vroid`。脚本启动专用进程，先采集正面、
背面和面部，再锁定第一次的取景复采，比较解码后的 RGBA。输入模型不保存，记录其
哈希和应用二进制哈希。新采集本身只是静态复采证据，不能自动成为已采用基准。

The maintainer explicitly approved a three-view, 512×512 F00 technical baseline
on 2026-10-20 (`body_front`, `body_back`, `face_front`). Its approval fixes the
model/build/render conditions and hashes; the package remains local. This is
technical regression approval, not final character art or independent acceptance.
Other machines or changed capture conditions need their own reviewed baseline.

2026-10-20 已人工采用 512×512 的 F00 正面／背面／面部三视图作为技术基准；采用记录
固定模型、构建、渲染条件与哈希，完整包保留在本机。这不等于角色最终美术采用或外测通过。
其他机器或采集条件改变时，需要另行评审对应基准。

```powershell
& .\.venv\Scripts\python.exe .\tools\check_visual_capture.py `
  --lab "D:\VRoid-Sample-Lab" `
  --model "D:\VRoid-Sample-Lab\saves\e2e-clean-lab.vroid" `
  --out "D:\VRoid-Static-Repeatability"
```

## Compare captures / 比较已采集图像

```powershell
& .\.venv\Scripts\python.exe .\tools\visual_regression.py `
  --baseline "D:\Capture-Baseline\review.json" `
  --candidate "D:\Capture-Candidate\review.json" `
  --out "D:\VRoid-Visual-Comparison"
```

Defaults are strict: pixel tolerance **0**, allowed changed ratio **0**. Explicit
`--pixel-tolerance <0..255>` and `--max-changed-ratio <0..1>` can describe a
reviewed tolerance. Do not increase them merely to turn a real regression green.
Exit codes: **0** within thresholds, **1** changes exceed thresholds, **2** inputs
cannot be compared or output cannot be created. No baseline is overwritten.

默认逐像素严格相等；可明确设置阈值，但不能为了消除真实回归而放宽。退出码 0 表示
所选阈值内，1 表示超阈值，2 表示输入不具备可比性或输出失败。脚本不覆盖基准。

Images must be adjacent to their native capture manifest; folder copies can be
compared on another machine without following old absolute paths. PNG hashes,
view sets, dimensions, effective MSAA, supersampling settings and verified camera
position/target/orientation/FOV are checked. Volatile frame IDs, process pointers
and render duration are not comparison criteria. Different camera readbacks are
refused, not silently registered or rescaled.

脚本核对 PNG 哈希、视图集合、尺寸、实际抗锯齿、渲染尺寸和已验证的相机位置／朝向／
FOV。帧号、进程指针、渲染耗时不作为匹配条件。取景不一致时拒绝，不自动对齐或缩放。

`review.html` displays before/after/difference; `report.json` contains changed
pixel counts/ratios and absolute channel deltas. An optional `--regions regions.json`
adds up to eight named rectangular regions per view; whole-image metrics remain.
For example, a normalized canvas rectangle (x right, y down):

```json
{"face_front": {"central_face": [0.25, 0.25, 0.75, 0.75]}}
```

These rectangles are caller-selected inspection areas, not automatic anatomical
masks. Lighting, source model, pose, driver and build must also be controlled.
Matching metadata is not proof that every environmental condition was identical.
Hair simulation may vary. Image change detection does not establish art quality,
collision freedom or game-engine physics.

区域框由调用者指定，不是自动解剖定位。光照、源模型、姿态、驱动和构建也需要控制；
元数据一致不证明全部环境一致。发丝物理可能随帧变化。图像变化检查不证明美术质量、
无穿插或引擎物理通过。

## F00 height/top matrix / F00 身高与上衣矩阵

After the [public sample](PUBLIC_SAMPLE.md), the same exclusive lab can run:

```powershell
& .\.venv\Scripts\python.exe .\tools\run_matrix.py `
  --lab "D:\VRoid-Sample-Lab" `
  --xwear "D:\VRoid-Sample-Results\asset\sample-badge.xwear" `
  --out "D:\VRoid-Height-Tops-Matrix"
```

The matrix selects two actual owned native `Tops` presets and runs targets at
the newly created F00 model's initial height **-8 / -2 / +6 cm**. Each of six
cases uses new model processes and distinct filenames, paints makeup before
body edits, applies hair before final live-height calibration, saves, cold reopens,
checks face/layer and live-height/scale persistence, imports the
sample accessory, saves assembly, exports VRM, independently parses it and
captures native views. Existing app/saves are not replaced. The first failure
stops the matrix; partial reports are retained. The input XWear hash is checked.
Cold texture verification and Dress-up/export still run in separate processes
to test saved-state persistence independently. Same-process transition coverage
is supplied separately by `tools/check_continuous_editing.py`; verified decoders
no longer require the old process boundary. See [RECOVERY.md](RECOVERY.md).

矩阵是“3 个身高目标 × 2 件实际原生上衣”，每组均走保存、冷重开、配件导入和导出。
它不覆盖 M00、任意体型比例、未知拓扑或复杂外部裙装。旧版所谓约 1.4 cm 重开漂移
混入了保存前换发型的变化；现以保存前后和冷重开的实时身高（0.05 cm）及缩放参数
（1e-6）验收，已移除旧 2 cm 宽限。界面缓存读数另记，不参与实时测量比较。

身高顺序对照可独立复现（会在独占测试 lab 中新增四个模型，输出目录必须不存在）：

```powershell
& .\.venv\Scripts\python.exe .\tools\check_height_persistence.py `
  --lab "D:\VRoid-Sample-Lab" --out "D:\VRoid-Height-Diagnosis"
```

包含旧顺序对照，以及 151.8 / 157.8 / 165.8 cm 三个先换发型再校准的冷重开检查。

Add `--include-proportions` to the matrix command for **10 cases**: the six
height/top cases plus narrow-shoulder/long-torso and broad-shoulder/long-leg
profiles at the medium target, each with both Tops. These use four explicitly
bounded native sliders (shoulder width, torso length, leg length, waist size).
Every edited proportion is read back and checked after cold reopen within 1e-6;
height is calibrated last and checked separately. This remains F00 coverage.

矩阵加 `--include-proportions` 可扩展为 10 组：保留原有 6 组，再增加窄肩长躯干和
宽肩长腿两种比例，各配两件上衣。调整肩宽、躯干长、腿长、腰部大小四个实际原生
参数，冷重开逐项核对；身高最后独立校准。不等于 M00 或任意体型全覆盖。
