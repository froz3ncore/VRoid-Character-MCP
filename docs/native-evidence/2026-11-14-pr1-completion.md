# PR #1: native completion, 2026-11-14

This supplements the [initial checkpoint](2026-11-13-pr1-acceptance.md).
The previously refused custom-item application and situation-image publication
now complete on signed standalone 2.14/2.16. Menu and interruption paths were
exercised in disposable windows. These results support merging the community
capabilities; they do not create a stable release or certify every model,
profile, image, VRM consumer or long-running manual editing sequence.

## Fixed causes

* A `FileCustomItemModel` in the native file registry is registered even when
  its resource has not yet entered the lazily populated asset storage. Catalog
  rows now distinguish `registration_scope=native_file_registry` from
  `asset_storage_registered`. Exact file generation, bytes, metadata, native
  resource/revision and unique selectable option are still required.
* Deserialization uses managed exception propagation. Current saved items can
  require native BodySuitsV2 in-memory normalization. Raw and normalized root,
  type, resource and revision must all match; source files are never converted
  or overwritten. Application retains the actual `OnSelected()` Task through
  registration, selection, terminal completion and distinct quiet frames.
  Fault/cancellation is not a successful membership receipt.
* Clear-option types belong to the native category model. Reading that owner
  fixes removal of optional shoes/bottoms. A Level0 ClothingSet may remain only
  with proven zero active transferable content; clearing children may retire
  the empty index. Unknown/new/content-bearing indices refuse publication.
* The native default InnerTop/InnerBottom cannot be cleared. Only exact,
  unmodified builtin base garments may remain and are listed in image metadata.
  Custom, changed or unknown mandatory garments still refuse. Required anatomy
  and snapshot restoration remain independently checked.

## Native evidence

All paths below are relative to `D:/vroidmcp/work/`, outside the source package.
Failed attempts remain alongside the successful evidence. No user model,
texture or generated preview is bundled in this commit.

| Build/fixture | Successful receipt | Coverage |
| --- | --- | --- |
| 2.16 F00 | `pr1-completion-20261114/catalog-f00-v03/checks.json` | Six catalog checks: native sync/icon, annotation, framing reset, byte-identical project-copy application, stable-key application, cold offline search/help without native startup |
| 2.16 M00 | `pr1-completion-20261114/catalog-m00-v03/checks.json` | Same six checks |
| 2.14 F00 | `pr1-completion-20261114/214-catalog-f00-v01/checks.json` | Same six checks |
| 2.16 F00/M00 | `pr1-completion-20261114/situation-f00-v03/checks.json`, `situation-m00-v04/checks.json` | One actual garment image published each, then pinned snapshot restored with fresh engine/token and verified original inventory |
| 2.14 F00 | `pr1-completion-20261114/214-situation-f00-v01/checks.json` | Image publication and snapshot restoration |
| 2.14 F00 menu | `pr1-completion-20261114/menu-214-f00-v03/checks.json` | Return, create M00, stale-menu refusal, reopen saved F00 with face value 0.37 in the same PID, graceful exit |
| 2.16 F00 attached | `pr1-community-f00-v06/checks.json` | Four cancelled native operations, retained pins, refusal while pending, fresh review/ack without replay, unpublished interrupted export, resumed save, cold reopen |
| 2.16 M00 attached | `pr1-community-m00-v02/checks.json` | Same interruption checks plus explicit graceful exit and stopped status without implicit relaunch |
| 2.16 F00 host loss | `pr1-community-forced-f00-v02/checks.json` | Four cancellation checks, then host exit during a final native import; target survives, replacement refuses owner handoff, confirmed saved state survives a fresh process |

2.16 assembly: `c8daa116938b40896e3a09208bbde71604a92d5ca6d86f9ff8b89fea3c1a5ad2`;
metadata: `089fe945572695f0592e04abaae096c54f7ea74a382a3ce68440e0425b8486b8`.
2.14 assembly: `ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296`.
Steam admission and supported-build descriptors are unchanged.

Actual F00, M00 and 2.14 image pixels were inspected: nonblank garments, upright
orientation, coherent proportions and retained default base garments. This is
fixture-specific image evidence, not garment-fit or aesthetic approval.

## Repeatable interruption fixture

`tools/check_community_workflows.py --source <signed-app> --out <NEW-folder>
--variant F00|M00` creates a new physical app/profile, startup guard and owned
external window. It exercises the public MCP transport and sends real MCP
cancellation notifications after dispatch of menu import, custom loading,
custom selection and ordinary VRM export.

The test delays only the agent's observation of the genuine retained Task's
completion. Native work/results/exceptions are unchanged. The dispatch record
includes whether native work had already completed and the observation count.
This makes pending-state testing deterministic; it is not evidence of slow
physical disk I/O or a native allocator failure. The optional `--force-host-exit`
terminates only the fixture host after a final dispatched import.

This attached-window bootstrap was validated on 2.16. Two extra fresh 2.14
attempts did not pass its startup precondition: the test-only raw new-model
fixture entered native legacy-editor initialization and subsequent status calls
reported `MAIN_THREAD_TIMEOUT: not executed`. Neither reached cancellation
dispatch. Their profiles/logs remain in `pr1-community-214-f00-v01`/`v02`;
2.14 cancellation/host-loss coverage is not claimed. The separate 2.14 owned-copy
catalog, thumbnail and menu receipts above passed through the production startup.

The forced-host run passed with a genuine incomplete import Task at dispatch.
The target stayed alive, and a replacement host refused review with
`ATTACHED_NATIVE_WORK_OWNER_LOST`. This is conservative refusal, not automatic
recovery of a lost native owner. Check and save in VRoid, close that window
normally, then start from a confirmed file; do not replay the interrupted write.

While observations are pending, review/ack and detach refuse and source files
cannot be opened for writing. An export dialog can trigger the earlier
`ATTACHED_UI_BLOCKED` guard. Once released, fresh review/ack permits editing
without replay; actual association, face values, membership and source hashes
are checked. Export staging may contain a real VRM, but cancellation does not
publish the requested final filename. A new save is reopened in a fresh process
and checked for face value 0.42 and the applied custom-group ID.

Fresh isolated profiles initially show agreements. The test-only bootstrap
prepares `ModelSelection` after returning to the start screen; it neither
accepts nor persists agreements. This proves the menu-ready workflow, not the
consent flow. Production initial-setup guards remain in place. Cleanup holds an
exact process handle and can stop only the fixture process, avoiding PID reuse.

## Offline checks and limits

Python 3.10 and 3.12: **1202 passed, 2 skipped** each. Reports:
`pr1-completion-20261114/pytest-all-v01.log` and `pytest312.log`.
The 145-tool input-schema hash remains
`sha256:a20221b7ac83b6a2895d913ae3f5e9def862c4ecf4ad1ffc70c181db52485f94`.
All 43 JavaScript behavior scripts and agent syntax checks passed, as did the
145-tool generated reference and the 26/26 rewrite check (zero cross-file hits).
`pr1-completion-20261114/delivery-checks/checks.json` records these independently
of the Python runs. The source manifest is verified separately after documentation.

Earlier failed fixtures remain diagnostic evidence: initial task-hook attempts
did not observe the retained wrapper; an absolute export filename was refused;
read-only startup timeouts were retried only when explicitly not executed;
transient busy review/ack required a fresh review; an export dialog exercised
the earlier UI guard. No uncertain write was retried to obtain a pass.

The domain checklist still defines broader optional/manual coverage, including
all visual combinations, every historical build, large-catalog image runs,
native allocation failures and import/motion in independent VRM consumers.
Do not infer those results from a passing GLB parser or from this merge.
