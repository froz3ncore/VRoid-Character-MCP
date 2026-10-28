# VRoid Character MCP

**English** · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

A local MCP server that normally drives **one disposable copy of VRoid Studio** through
the application's own managed API, with optional attachment to an existing session. It exposes 92 tools for character
parameters, textures and local makeup, hair authoring, Dress-up assembly and
VRM export — with no mouse automation, no OCR and no screen scraping.

Status: **0.4.1 development**. The earlier 86-tool baseline was verified end to
end on a clean lab; the new attached-session and ordinary-export features are
under independent verification. Character art and sitting-skirt fit remain
separate work. See [SCOPE.md](SCOPE.md).

Validated copies support body, texture and Dress-up editing in one process.
Native PNG decoding runs on Unity's main thread with deferred callbacks to avoid
the reproduced asynchronous buffer-lifetime crash. Transitions wait for pending
callbacks; attached windows keep their conservative restrictions. See [recovery](RECOVERY.md).

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

Before connecting a prepared lab, run
`.venv\Scripts\python.exe tools\doctor.py --lab <lab-directory>` with your
client's interpreter. This checks dependencies, supported binaries, the local
async environment, ownership and the known crash key without launching VRoid.
See [diagnostics and recovery](RECOVERY.md) for reports, limits and recovery.
The [public sample](PUBLIC_SAMPLE.md) generates its own test accessory and
reproduces editing, cold reopening and VRM export without private outfit assets.
See [visual regression and coverage](REGRESSION.md) and
[external beta acceptance](BETA_TESTING.md) for the next validation layers.

`prepare_lab.py` copies a supported VRoid Studio installation into a lab
directory. By default the server launches that copy, with a private profile, a private
registry key and its own `TEMP`, attaches with Frida, and calls managed methods
on Unity's main thread. `attach_open_vroid` can explicitly connect an existing
user-opened process. Edits then affect the user's unsaved model and profile;
the copy's isolation guard is not loaded. `detach_open_vroid` leaves it running.
Save in VRoid itself. Because the preceding manual edit history is unknown,
entering the texture editor or switching into Dress-up is refused in attached mode.
Ordinary VRM export writes under lab/saves. Isolated copies can save new custom
items with file and closet checks; attached sessions refuse custom-item saves.
See [existing sessions and ordinary export](ATTACHED_SESSION.md).

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

## Blender, VRM and XWear add-ons

External clothing needs mesh preparation, fitting and skinning before it becomes
a wearable package. These components have different roles:

| Component | Runs in | Role |
|---|---|---|
| [VRM format / VRM Add-on for Blender](https://github.com/saturday06/VRM-Addon-for-Blender) | Blender | Import a reference VRM; edit humanoid mappings, MToon and VRM SpringBone data |
| [Direct XWear 0.2.0, included here](pipeline/blender-addons/vroid_xwear_direct/) | Blender | Export prepared, skinned garment meshes as a restricted experimental XWear package |
| [Official XWear Packager](https://vroid.pixiv.help/hc/en-us/articles/38903414455449-How-to-install-the-XWear-Packager) | Unity / VCC | An alternative official route to converting clothing to XWear |

For Blender 4.2+, find **VRM format** under `Preferences → Get Extensions`.
Package this repository's `vroid_xwear_direct` folder as a ZIP and install it
through `Preferences → Add-ons → Install from Disk`. After enabling it, use
`File → Export → Direct XWear — Experimental (.xwear)`.

The flow is: reference VRM + external clothing → Blender fitting/skinning →
XWear export → VRoid Dress-up → XRoid save / VRM export. The direct writer
supports a limited opaque-material/rest-skinning/spring subset, not animation,
morphs, full PBR or transparent materials. The official Unity packager is an
alternative, not a prerequisite of the direct Blender route.

See the [Blender/XWear setup guide (Simplified Chinese)](BLENDER_SETUP.zh-CN.md)
for exact packaging commands, export checks and troubleshooting. Add-ons are
not installed by pip. Ordinary MCP editing or importing an existing XWear does
not require the entire Blender preparation workflow.

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

Current development validation: **502 Python tests passed / 1 skipped** on
Python 3.10 and 3.12, six JS suites, a 79.1 s fresh-lab public sample and a
10-case height/proportion/Tops matrix. All 30 saved/cold rendered views matched
exact RGBA. These are tool checks; human baseline approval and external-user
acceptance remain pending. See [regression scope](REGRESSION.md).

- **Calibrate height after styling.** Hair changes the native measured height.
  The earlier ~1.4 cm "reopen drift" compared a pre-hair value with a post-hair
  model; the change had already happened before saving. The solver now uses
  `live_centimeters` (`GetBodyHeight`), since UI `centimeters` can be cached.
  E2E checks target/live-height within 0.05 cm and preserved scale across cold reopen.
- **Per-strand hair colour is not visible.** Writing the `Level1BaseHair_*` colour
  channels reads back but changes 0 of 640x640 rendered pixels; global hair
  colour (`colors/Hair/All`) changes 24.6%. Only global colour is supported.
- **M00** has not received the coverage F00 has.
- **Continuous editing requires the validated decoder.** Copies expose its state
  in `get_status.png_decoder`; attached sessions retain their restrictions.
- **Rear-skirt collision is paused and unresolved**; it is not assumed away.
- Godot import, materials and physics require separate engine-side validation.

## Licensing and provenance

This repository began as a fork of `Karylcode/VRoid-MCP`; the historical baseline
had no licence and its inherited implementation was replaced. A later upstream
revision is MIT licensed and portions have since been adapted with attribution.

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
| `tools/TOOLS.md` | generated reference for all 92 tools |
| `SCOPE.md` | must-do, may-skip and out-of-scope for 0.4.x |
| `REWRITE.md` | rewrite ledger and provenance gates |
| `CHANGELOG.md` | release notes |
