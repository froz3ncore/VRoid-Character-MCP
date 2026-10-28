# VRoid Character MCP

[English](README.md) · [简体中文](README.zh-CN.md) · **繁體中文**

本地 MCP 伺服器：預設驅動**一份可丟棄的 VRoid Studio 副本**，也可明確連接已開啟的 VRoid；透過
managed API 操作角色參數、貼圖與局部妝造、髮束、換裝組裝與 VRM 匯出，共 **92 個工具**。
不使用滑鼠自動化、OCR 或螢幕抓取。

狀態：**0.4.1 開發版**。原有 86 工具基準已在乾淨 lab 上端到端驗證；新加入的
既有工作階段與普通匯出功能另行驗證。角色美術是另一條工作線。範圍見 [SCOPE.md](SCOPE.md)。

確認體型參數改變後，會提前拒絕進入貼圖編輯器以避開已知原生崩潰路徑；先另存新檔，
再冷重開。讀取與保存仍可用，見 [恢復步驟](RECOVERY.md)。

## 效果展示

以下為 2026-10-19 開發驗證中的原生截圖。服裝與妝容是不同驗證場景的候選，尚未合併為最終角色；坐姿裙擺與穿插問題仍保留。

| 服裝裝配 | 局部妝容：保存重開 |
|:---:|:---:|
| ![原生換裝中的整套服裝正面預覽](assets/showcase/outfit-front.png) | ![眉色與眼下陰影高光繪製後的原生臉部近景](assets/showcase/makeup-after.png) |

完整的妝容前後對照、閉眼檢查與手指美甲近景見 [簡體中文圖文說明](README.zh-CN.md#效果展示)，來源與展示範圍見 [截圖說明](assets/showcase/README.md)。

## 不是什麼

- 非 pixiv／VRoid 官方產品，也無隸屬關係。
- 不是沙箱。agent 只保護這份可丟棄副本不寫出自己目錄，那是本機防護，不是作業系統邊界。
- 不構成 VRoid Studio、VRM 格式或任何產出角色的授權。見 [LICENSING.md](LICENSING.md)。

## 運作方式

連接已準備的副本前，用客戶端相同的解譯器執行
`.venv\Scripts\python.exe tools\doctor.py --lab <副本目錄>`。
診斷不啟動 VRoid，會檢查依賴、支援構建、非同步環境、副本占用與已知崩潰鍵。
報告、檢查範圍與恢復步驟見 [安裝診斷與恢復](RECOVERY.md)。
另有 [可重現最小樣例](PUBLIC_SAMPLE.md)，自行產生測試配件並保留 Blender 原始檔，
在新副本中驗證保存、冷重開與 VRM 匯出，不依賴私人展示服裝。
另見 [視覺回歸與覆蓋矩陣](REGRESSION.md) 與 [外部試用驗收](BETA_TESTING.md)。

`prepare_lab.py` 把支援的 VRoid Studio 安裝複製成一個 lab。預設伺服器啟動那份副本，
使用獨立 profile、獨立登錄鍵與自己的 `TEMP`，以 Frida 附加，並在 Unity 主執行緒呼叫
managed 方法。`attach_open_vroid` 可明確連接已開啟的 VRoid，編輯直接作用於真實角色與 profile，
不載入副本隔離守衛；請在 VRoid 中保存。斷開不會關閉視窗。因連接前的編輯歷史未知，
連接模式禁止進入貼圖編輯與切換進入換裝。普通編輯可匯出 VRM 0.x/1.0；獨立副本可保存新的自訂物件並核驗檔案與衣櫃登記，真實連接模式仍拒絕該保存。
連接和部件操作詳見 [既有工作階段與普通匯出](ATTACHED_SESSION.md)。

- `agent/profile_guard.js`：把使用者 profile 重導進 lab，並拒絕指向 lab 外的寫入、複製與子程序。
- `agent/main_thread.js`：主執行緒佇列、GC handle 保留與編輯器單例。
- `vroid_mcp/tools_*.py`：對外工具面，依領域分模組。
- `vroid_mcp/runtime.py`：程序生命週期、原生呼叫與產物檢查。

## 需求

- Windows。
- VRoid Studio **2.14.0**（Unity 6000.0.62f1）；其他版本會被拒絕，原生綁定與版本相關。
- Python 3.10+、Git、Node.js 與 npm（用於 Frida bridge 依賴與 JavaScript 檢查）。

## 安裝

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
.\.venv\Scripts\python.exe prepare_lab.py --source "C:\Program Files\VRoid Studio" --lab D:\vroidmcp\lab-test
~~~

來源安裝只會被讀取；已存在的 lab 不會被覆蓋。一個 lab 同時只能有一個伺服器佔用，
第二個會被拒絕並指出持有鎖的程序。

## 連接 MCP 客戶端

~~~json
{
  "mcpServers": {
    "vroid": {
      "command": "D:\\vroidmcp\\VRoid-MCP\\.venv\\Scripts\\python.exe",
      "args": ["D:\\vroidmcp\\VRoid-MCP\\launch.py", "--lab", "D:\\vroidmcp\\lab-test"]
    }
  }
}
~~~

## Blender、VRM 與 XWear 插件

外部衣飾要先整理網格、對位和綁定，再交給 VRoid 換裝。這幾個工具各自負責不同步驟：

| 工具 | 安裝位置 | 用途 |
|---|---|---|
| [VRM format / VRM Add-on for Blender](https://github.com/saturday06/VRM-Addon-for-Blender) | Blender | 導入參考 VRM、編輯 Humanoid 映射、MToon 與 VRM SpringBone |
| [本專案 Direct XWear 0.2.0](pipeline/blender-addons/vroid_xwear_direct/) | Blender | 將已綁定的衣飾匯出成受限的實驗性 `.xwear` |
| [官方 XWear Packager](https://vroid.pixiv.help/hc/en-us/articles/38903414455449-How-to-install-the-XWear-Packager) | Unity／VCC | 官方 XWear 轉換路線，可按需求選擇 |

Blender 4.2+ 可在 `Preferences → Get Extensions` 安裝 **VRM format**。本專案 Direct XWear 從原始碼打包成 ZIP，再用 `Add-ons → Install from Disk` 安裝；匯出菜單為 `File → Export → Direct XWear — Experimental (.xwear)`。

完整流程：參考 VRM 與外部網格 → Blender 對位／綁定 → 匯出 XWear → VRoid 換裝 → 保存 XRoid／匯出 VRM。直出器不支援完整 PBR、透明材質、morph 或動畫，也不自動修復權重或穿插。

打包、安裝、匯出前檢查及排錯詳見 [Blender／XWear 接入指南（簡中）](BLENDER_SETUP.zh-CN.md)。只用 MCP 編輯角色或導入現成 XWear 時，不需要安裝全部插件。

## 工作流

1. `list_face_params` 取得 `model_token`，之後作為 `expected_model`。
2. 先讀再寫：`list_parameters`、`list_hair_nodes`、`list_clothing_params`。
3. 用 `set_face_params`／`set_parameters`／`set_height` 寫入並回讀。
4. 用 `capture_review` 前後對照，並且真的看圖。
5. `save_as` 在 lab 的 `saves/` 另存新 `.vroid`。

換裝：`get_wear_status` → `open_wear_project` → `import_xwear` → `set_wear_fit`
→ `save_wear_project` → `export_wear_vrm`。換裝與一般編輯互不相通，各有自己的 token。

貼圖與妝造同樣走原生：列 region／layer、開啟對應畫板，再用原生歷史新增 PNG 圖層或
受限筆刷；換裝開啟時這些工具會拒絕執行。

## 驗證

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Manifest
~~~

會把 `TEMP`/`TMP` 固定到 `work\temp`，跑單元測試、工具 schema smoke、JavaScript
行為檢查與原始碼清單，輸出 `checks.json` 與 exit code。加 `-Native` 會對空閒 lab
每域跑一個唯讀呼叫（會啟動 VRoid）；加 `-Provenance` 會強制重寫比例門檻。

完整證明是乾淨 lab 端到端跑到匯出 VRM，再用 `tools/vrm_inspect.py` 獨立解析
（直接讀 GLB 與 VRM JSON chunk，不採信匯出器自己的報告）。指令見英文版 README。

## 已知限制

目前開發樹在 Python 3.10／3.12 均為 **502 通過、1 跳過**，六組 JS 通過；
全新副本樣例 79.1 秒、10 組身高／身體比例／上衣矩陣 793.5 秒通過。
30 張儲存前後原生視圖逐像素一致；人工基準確認與獨立外測仍待進行。

- **身高須在造型完成後校準**：髮型會改變原生測量。此前約 1.4 cm 的「重開漂移」
  實際發生在儲存前換髮型時，舊驗收比較了不同造型。現用即時 `live_centimeters`
  校準，儲存與冷重開按 0.05 cm 容差及縮放參數核對；`centimeters` 可能是滯後的介面快取。
- **逐束發色不可見**：`Level1BaseHair_*` 色彩通道可讀回，但 640×640 渲染 0 像素變化；
  全域 `colors/Hair/All` 則有 24.6% 變化，因此只支援全域發色。
- **M00** 沒有 F00 的等價覆蓋。
- **獨立副本支援連續編輯**：已核構建使用主執行緒原生 PNG 解碼與延後回呼，修復已重現的非同步解碼崩潰路徑；改體型、編輯紋理及進入換裝可使用同一進程。真實連接模式的限制仍保留，詳見[恢復步驟](RECOVERY.md)。
- **後裙碰撞暫停且未解決**，不會當作不存在。
- Godot 匯入、材質與物理需要另做引擎端驗證。

## 授權與來源

本倉庫最初 fork 自 `Karylcode/VRoid-MCP`，當時的 baseline 沒有授權檔，繼承實作因此被替換。
上游後續版本採用 MIT 授權；本次部分功能依該版本適配並保留其授權與出處。

- [LICENSE](LICENSE)：本倉庫原創程式碼的授權。
- [LICENSING.md](LICENSING.md)：範圍與仍被排除的部分。
- [UPSTREAM.json](UPSTREAM.json)：重寫度量的 26 條基線路徑。
- [REWRITE.md](REWRITE.md)：重寫台賬、行為閘門與進度。
- 內建的 preset／label 資料保留各自的 MIT 授權與出處，見 `vroid_mcp/data/*/LICENSE` 與 `NOTICE`。

`tools/check_provenance.py` 量測進度：逐路徑回報仍按序存在的基線行比例，並額外檢查
繼承行是否被搬進新模組。

## 目錄

工具細節見 [tools/TOOLS.md](tools/TOOLS.md)（由 live schema 產生），版本說明見
[CHANGELOG.md](CHANGELOG.md)，範圍見 [SCOPE.md](SCOPE.md)，重寫進度見 [REWRITE.md](REWRITE.md)。
