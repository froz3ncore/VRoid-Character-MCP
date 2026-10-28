# Rewrite plan: from fork to independent source

This is the historical 0.4.1 rewrite ledger (completed 2026-10-20). Its 86-tool
gate describes that snapshot. Current development has 99 tools; later additive
features use their own input-contract checks. Current status is in [SCOPE.md](SCOPE.md).

The upstream project this repository started from,
[Karylcode/VRoid-MCP](https://github.com/Karylcode/VRoid-MCP), was public with
**no license at the recorded baseline**: GitHub then reported `license: null` and the baseline commit
`9b264d3` contains no LICENSE, COPYING or NOTICE file. Public visibility is not
a license grant, so every inherited line is "all rights reserved" material and
cannot be relicensed or redistributed.

Adding a license file cannot fix that. The only honest route is to **replace
the inherited implementation**: rebuild the same behaviour from the recorded
contract (tool schemas, tests, documented native behaviour) and stop shipping
inherited text. This file is the ledger for that work. Upstream subsequently
licensed a later revision under MIT; the later adaptations and retained licence
are described in [LICENSING.md](LICENSING.md).

## What "rewritten" means here

Measured, not asserted:

    python tools/check_provenance.py

It reads `UPSTREAM.json`, loads each baseline blob from Git, and reports the
fraction of its non-trivial lines that still appear anywhere in the current
file. A path counts as rewritten when that fraction is **≤ 0.10** and the
behaviour gates below still pass. Trivial lines (braces, single words) are
ignored so the number reflects authorial expression, not syntax.

Inherited or deleted paths must not come back through a later commit; the
checker runs in CI-style form and fails the build above the threshold.

## Behaviour gates (the contract that must not drift)

Rewriting is only acceptable if nothing else changes. Four gates decide:

1. **Tool contract** — `tools/tool_manifest.py` reports the same 86 tools,
   parameters, required fields and `toolset_hash` as
   `tools/expected-tools.json`. A rewrite may change internals, never the
   published surface.
2. **Unit tests** — `pytest` stays at its current pass/skip count, no new
   failures.
3. **Native domains** — `tools/check_native_domains.py` passes for
   face-body, clothing-wear, texture-makeup, hair and VRM on a real lab.
4. **End to end** — `tools/e2e_clean_lab.py` still reaches an exported VRM that
   `tools/vrm_inspect.py` accepts.

Gates 1–2 run offline; gates 3–4 need an exclusive lab.

## Disposition of the 26 inherited paths

`ratio` is the residue at the start of the rewrite (2026-10-19, commit
`8c1e803`), from `tools/check_provenance.py`.

### Replaced with original modules (no inherited text)

| Path | Ratio | Replacement | Gate |
|---|---|---|---|
| `agent/bootstrap.js` | 0.98 | `agent/main_thread.js` rewritten from the recorded behaviour: version check, GC-handle retention, main-thread queue with timeout, singleton retention, background pin, model counter, `health`/`call` exports. | 3, 4 |
| `agent/isolate.js` | 1.00 | `agent/profile_guard.js` rewritten as a rule table over the same Win32 entry points: profile remapping, write blocking, child-process refusal, registry and known-folder remapping. | 3, 4 |
| `agent/operations.js` | 0.90 | split into `agent/model.js` (model/history/save/capture) and `agent/native.js` (dispatch table, shared helpers). | 3, 4 |
| `agent/parameters.js` | 0.99 | split into `agent/parameters.js` (typed bindings) and `agent/hair.js` (hair authoring). | 3, 4 |
| `vroid_mcp/server.py` | 0.95 | `vroid_mcp/server.py` keeps only the server factory; tool groups move to `vroid_mcp/tools_*.py`, registered per domain. | 1, 2 |
| `vroid_mcp/runtime.py` | 0.90 | split into `vroid_mcp/process.py` (launch/lifecycle), `vroid_mcp/bridge.py` (Frida calls), `vroid_mcp/artifacts.py` (paths, validation, saving). | 1, 2, 3 |
| `launch.py`, `prepare_lab.py`, `vroid_mcp/__init__.py` | 1.00 | rewritten entry points and lab preparation. | 2 |

### Rewritten in place (same filename, original content)

| Path | Ratio | Notes |
|---|---|---|
| `.gitignore`, `requirements.txt`, `pyproject.toml`, `package.json`, `package-lock.json` | 0.80–1.00 | project metadata; distribution renamed to `vroid-character-mcp` so nothing depends on the inherited package identity. |
| `README.md`, `README.zh-TW.md` | 0.90–0.96 | prose rewritten around this project's own workflow, scope and limitations. |
| `tests/test_review_policy.py`, `tests/test_save_policy.py` | 1.00 | same policies, original tests. |

### Removed (superseded by this project's own acceptance tooling)

| Path | Ratio | Why |
|---|---|---|
| `tests/extension_acceptance.py`, `tests/live_acceptance.py`, `tests/parameter_acceptance.py`, `tests/parameter_extras.py`, `tests/recovery_acceptance.py`, `tests/reopen_acceptance.py`, `tests/review_acceptance.py`, `tests/stdio_acceptance.py` | 1.00 | one-shot live scripts; `tools/check_native_domains.py`, `tools/e2e_clean_lab.py` and the `tests/*_acceptance.py` this project wrote replace them. |

## Order of work

1. Metadata and entry points (no runtime risk) — **done**.
2. `agent/profile_guard.js` and `agent/main_thread.js` — the isolation layer is
   security-relevant, so it is rewritten and verified natively early.
3. `vroid_mcp/server.py` split into per-domain tool modules — offline gate.
4. `vroid_mcp/runtime.py` split into process/bridge/artifacts — offline gate,
   then native gate.
5. `agent/operations.js` and `agent/parameters.js` — native gate plus the full
   end-to-end run.
6. README and the remaining tests.
7. Publish: fresh history (no inherited commits), MIT for the whole repository,
   `UPSTREAM.json` kept as an acknowledgement of the original project rather
   than a license claim, `LICENSING.md` rewritten to describe reimplementation.

## Status

| Step | State |
|---|---|
| 1. Metadata and entry points | done |
| 2. `agent/profile_guard.js` + `agent/main_thread.js` | done, native domains pass |
| 3. `vroid_mcp/server.py` split into per-domain modules | done: `tools_wear`, `tools_parameters`, `tools_hair`, `tools_accessories`, `tools_capture`; schemas byte-identical, 86 tools, same `toolset_hash` |
| 4. `vroid_mcp/runtime.py` split | done: `bridge.py` owns spawn/attach/call/settle/close, `lab_paths.py` the artifact policy, and the domain methods moved to `runtime_edit.py`, `runtime_capture.py` and `runtime_wear.py` as rewritten mixins (0.90 -> 0.00) |
| 5. `agent/operations.js` + `agent/parameters.js` split | done: both rewritten in place with the dispatch contract and factory keys unchanged (0.90 / 0.99 -> 0.00) |
| 6. README and remaining tests | README.md and README.zh-TW.md rewritten; the two policy tests were rewritten earlier |
| 7. Fresh-history MIT publish | pending |

### How the measurement reads now

`python tools/check_provenance.py` reports, on the current tree:

- **26 of 26** inherited paths rewritten, removed or structural: no inherited text remains.
- Nothing pending: the per-path pass and the cross-file pass are both empty.

- Both READMEs are fully replaced (0.00); `vroid_mcp/server.py` is at 0.07, where
  the remaining matches are the factory's public signature.
- No cross-file findings: the split did not move inherited lines into the new
  tool modules.

Per-path ratios are an ordered match, so boilerplate no longer inflates them. A
second pass searches every source file for distinctive baseline lines, which is
how code moved into a *new* module would be caught. Declarative files whose
lines are dictated by a tool schema (`package-lock.json`, `package.json`,
`requirements.txt`, `pyproject.toml`, `.gitignore`) are reported as
`structural` with the reason rather than being bent out of shape to pass a
threshold; dependency pins are facts, not prose.

Nothing in this plan changes the character work: the art pipeline, the
`.vroid`/`.xroid`/VRM assets and the acceptance evidence stay where they are.

