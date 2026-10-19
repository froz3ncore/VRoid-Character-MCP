# VRoid Character MCP

[English](README.md) · [简体中文](README.zh-CN.md) · **繁體中文**

本地 MCP 伺服器：只驅動**一份可丟棄的 VRoid Studio 副本**，透過應用程式自己的
managed API 操作角色參數、貼圖與局部妝造、髮束、換裝組裝與 VRM 匯出，共 **86 個工具**。
不使用滑鼠自動化、OCR 或螢幕抓取。

狀態：**0.4.1 開發版**。工具層已收口並在乾淨 lab 上端到端驗證；角色美術
（正式 v22 裝配、鞋、坐姿裙擺）是另一條工作線。範圍見 [SCOPE.md](SCOPE.md)。

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

`prepare_lab.py` 把支援的 VRoid Studio 安裝複製成一個 lab。伺服器只啟動那份副本，
使用獨立 profile、獨立登錄鍵與自己的 `TEMP`，以 Frida 附加，並在 Unity 主執行緒呼叫
managed 方法；不會附加到你原本開著的 VRoid。

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

- **身高無法精確往返**：`set_height` 在會話內達到目標，重開後本版量到約高 1.4cm；
  端到端報告會記錄漂移，不隱藏。
- **逐束發色不可見**：`Level1BaseHair_*` 色彩通道可讀回，但 640×640 渲染 0 像素變化；
  全域 `colors/Hair/All` 則有 24.6% 變化，因此只支援全域發色。
- **M00** 沒有 F00 的等價覆蓋。
- **後裙碰撞暫停且未解決**，不會當作不存在。
- Godot 匯入、材質與物理需要另做引擎端驗證。

## 授權與來源

本倉庫最初 fork 自 `Karylcode/VRoid-MCP`，該專案公開但**沒有任何授權**：
GitHub 顯示 `license: null`，baseline 提交內也沒有授權檔。公開可見不等於授權，
因此繼承實作是被**替換**而不是重新授權。

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
