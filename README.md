# VRoid Character MCP

**English** · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

A local MCP server that drives **one disposable copy of VRoid Studio** through
the application's own managed API. It exposes 86 tools for character
parameters, textures and local makeup, hair authoring, Dress-up assembly and
VRM export — with no mouse automation, no OCR and no screen scraping.

Status: **0.4.1 development**. The tool layer is closed and verified end to end
on a clean lab; the character art (formal v22 assembly, shoes, sitting skirt) is
a separate line of work. See [SCOPE.md](SCOPE.md) for what 0.4.x includes and
what it deliberately does not.

## In action

These are native screenshots from development validation on **2026-10-19**,
not generated mockups. The outfit and makeup are separate work-in-progress
candidates, not a single final avatar. [Image sources and scope](assets/showcase/README.md).

| Dress-up assembly | Native walking preview frame |
|:---:|:---:|
| ![Native full-outfit front view](assets/showcase/outfit-front.png) | ![The same outfit during a native walk preview](assets/showcase/outfit-walk.png) |

The clothing comes from an external modeling and rigging workflow. MCP imports,
adjusts, reviews, saves and exports it; seated-skirt intersections remain unresolved.

| Before eyebrow and under-eye painting | After painting, saved and reopened |
|:---:|:---:|
| ![Before local makeup painting](assets/showcase/makeup-before.png) | ![Eyebrow tint and under-eye shading after a cold reopen](assets/showcase/makeup-after.png) |

The makeup example preserves the eyebrow shape and adds bounded 2D shading below
the eyes. Native layer pixels, Undo/Redo and save/reopen were checked.

| Left index fingernail | Right thumbnail |
|:---:|:---:|
| ![Blue fingernail localization test](assets/showcase/nail-index.png) | ![Orange thumbnail localization test](assets/showcase/nail-thumb.png) |

These diagnostic colours demonstrate hand-nail masks and RGB texture import;
they are not a finished nail-art design. More detail, including a closed-eye
check, is in the [Chinese walkthrough](README.zh-CN.md#效果展示).

## What it is not

- Not an official pixiv/VRoid product and not affiliated with it.
- Not a sandbox. The agent guards the disposable copy against writing outside
  its own directory, but that is a local safeguard, not an OS boundary.
- Not a licence for VRoid Studio, the VRM format or any character produced with
  it. See [LICENSING.md](LICENSING.md).

## How it works

`prepare_lab.py` copies a supported VRoid Studio installation into a lab
directory. The server launches only that copy, with a private profile, a private
registry key and its own `TEMP`, attaches with Frida, and calls managed methods
on Unity's main thread. Nothing is attached to a VRoid instance you started
yourself.

- `agent/profile_guard.js` — remaps the machine profile into the lab and refuses
  writes, copies or child processes that point outside it.
- `agent/main_thread.js` — the main-thread queue, GC handle retention and editor
  singletons.
- `vroid_mcp/tools_*.py` — the published tool surface, one module per domain.
- `vroid_mcp/runtime.py` — process lifecycle, native calls and artifact checks.

## Requirements

- Windows.
- VRoid Studio **2.14.0** (Unity 6000.0.62f1). Other builds are rejected: the
  native bindings are version-specific.
- Python 3.10+, Git, Node.js and npm (for the Frida bridge dependency and JavaScript checks).

## Install

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install                     # frida-il2cpp-bridge for the agent
.\.venv\Scripts\python.exe prepare_lab.py --source "C:\Program Files\VRoid Studio" --lab D:\vroidmcp\lab-test
~~~

`prepare_lab.py` copies and hash-verifies the installation. The source install is
only read; an existing lab is never replaced.

## Connect an MCP client

Register a stdio server that runs `launch.py` with the lab:

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

One lab can be owned by one server at a time. A second server is refused and the
message names the process that holds the lock.

## Workflow

1. `list_face_params` → keep the returned `model_token` as `expected_model`.
2. Read before writing: `list_parameters`, `list_hair_nodes`, `list_clothing_params`.
3. Write with `set_face_params` / `set_parameters` / `set_height` and re-read.
4. Inspect with `capture_review` before and after; look at the images.
5. `save_as` writes a new `.vroid` under the lab's `saves/`.

For an outfit: `get_wear_status` → `open_wear_project` → `import_xwear` →
`set_wear_fit` → `save_wear_project` → `export_wear_vrm`. Dress-up is independent
of ordinary editing and has its own token.

Textures and makeup are native too: list regions and layers, open the matching
canvas, and add PNG layers or bounded stamps through native history. Those tools
refuse to run while a Dress-up assembly is open.

## Verify a checkout

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Manifest
~~~

This pins `TEMP`/`TMP` into `work\temp`, runs the unit tests, the tool-schema
smoke against `tools/expected-tools.json`, the JavaScript behaviour checks and
the source manifest, and writes `checks.json` with an exit code. Add `-Native`
to exercise one read-only call per domain against a free lab (it launches VRoid),
and `-Provenance` to enforce the rewrite threshold described below.

The full proof is a clean-lab run that ends in an exported VRM:

~~~powershell
& .\.venv\Scripts\python.exe .\tools\e2e_clean_lab.py `
    --source "C:\Program Files\VRoid Studio" --lab D:\vroidmcp\lab-e2e `
    --xwear <outfit.xwear> --json .\work\e2e.json
& .\.venv\Scripts\python.exe .\tools\vrm_inspect.py .\lab-e2e\saves\e2e-clean-lab.vrm
~~~

`vrm_inspect.py` parses the GLB and the VRM JSON chunk directly, so the exporter's
own report is not the evidence.

## Known limitations

- **Height is not exact across save/reopen.** `set_height` reaches the target in
  session; the reopened file measures about 1.4 cm higher in this build. The
  clean-lab report records the drift instead of hiding it.
- **Per-strand hair colour is not visible.** Writing the `Level1BaseHair_*` colour
  channels reads back but changes 0 of 640x640 rendered pixels; global hair
  colour (`colors/Hair/All`) changes 24.6%. Only global colour is supported.
- **M00** has not received the coverage F00 has.
- **Rear-skirt collision is paused and unresolved**; it is not assumed away.
- Godot import, materials and physics require separate engine-side validation.

## Licensing and provenance

This repository began as a fork of `Karylcode/VRoid-MCP`, which is public but
carries **no licence**: `license: null` on GitHub and no licence file in the
baseline commit. Public visibility is not a grant, so the inherited
implementation has been replaced in this development line rather than relicensed.

- [LICENSE](LICENSE) covers the original code in this repository.
- [LICENSING.md](LICENSING.md) states the scope and what is still excluded.
- [UPSTREAM.json](UPSTREAM.json) records the 26 baseline paths this rewrite is
  measured against.
- [REWRITE.md](REWRITE.md) is the ledger: how "rewritten" is measured, which
  behaviour gates must hold, and how far the replacement has progressed.
- Bundled preset and label data keeps its own MIT notices under
  `vroid_mcp/data/*/LICENSE` and `NOTICE`.

`tools/check_provenance.py` measures the progress: it reports, per inherited
path, the share of baseline lines still present in order, plus a cross-file pass
that finds inherited lines moved into new modules.

## Source layout

| Path | Purpose |
|---|---|
| `launch.py` | stdio entry point |
| `prepare_lab.py` | verified installation copy |
| `vroid_mcp/server.py` | server factory, lifecycle gate, session tools |
| `vroid_mcp/tools_*.py` | tool surface by domain |
| `vroid_mcp/texture_tools.py` | texture, layer and makeup tools |
| `vroid_mcp/runtime.py` | process lifecycle, native calls, artifacts |
| `vroid_mcp/closet_guard.py` | refuses to launch while the crash registry key exists |
| `vroid_mcp/lab_lock.py` | one owning process per lab, with its PID |
| `vroid_mcp/runtime_handle.py` | indirection so a restarted session reaches every tool |
| `agent/profile_guard.js` | profile remapping and outside-write refusal |
| `agent/main_thread.js` | main-thread queue and retained objects |
| `agent/operations.js` | model, history, saving and capture dispatch |
| `agent/parameters.js` | typed parameter bindings |
| `tools/run_checks.ps1` | one-command acceptance with a JSON report |
| `tools/TOOLS.md` | generated reference for all 86 tools |
| `SCOPE.md` | must-do, may-skip and out-of-scope for 0.4.x |
| `REWRITE.md` | rewrite ledger and provenance gates |
| `CHANGELOG.md` | release notes |
