# Existing VRoid sessions, parts and ordinary VRM export

Current source: **0.5.0.dev0 development snapshot** (npm `0.5.0-dev.0`),
**94 tools**. Local native evidence is dated 2026-10-28; independent external-user
acceptance remains pending. Version/documentation changes alone do not rerun
that native evidence.

The default session is still a dedicated lab copy. `attach_open_vroid(pid=None)`
explicitly switches to a compatible VRoid Studio process the user opened. It
validates the `GameAssembly.dll` allowlist and excludes managed MCP labs. If
more than one eligible process is found, provide its PID. A running owned copy
is not closed unless `discard_copy_unsaved=true` is explicitly supplied; save
that copy first.

An attached session operates on the user's actual open model and profile. The
copy's profile guard is **not** installed. Changes use VRoid's native history;
save from VRoid itself. `save_as`, opening another file and creating a new model
are refused in attached mode. `detach_open_vroid` releases the connection without
closing the user's process; its result reports whether background settings were
restored. `restart_session` also detaches rather than killing an attached process.

Attachment records the original background flag and a Windows handle to the
owning MCP host in the target's process-local environment. A second live host
using this lease protocol is refused. If the host was forcibly terminated, a
new attachment verifies the old process handle, restores its saved flag, and
starts a fresh lease. The adoption result reports `recovered_previous_host`.
The handle identifies the original process even if Windows later reuses its PID.
Normal detach restores the pre-attachment flag and removes the lease.

After a forced host exit, background execution may remain enabled until you
reconnect and detach normally; recovery is not immediate. An interrupted edit
or export has an uncertain result and must not be replayed blindly.
This recovery applies to leases written by this version; older agents did not
record this state. Unknown/corrupt ownership records are refused, not guessed.

Compatible attached windows support native texture entry and layer editing,
including models with prior unsaved body/face edits and an already-open canvas.
Late attachment installs main-thread PNG decoding and posts the original native
completion closure to Unity's managed synchronization context. Submitted callbacks
retain their textures independently of the agent and can finish after host exit.
Attachment waits for already-running original PNG worker Tasks before enabling
transitions. Detach restores the original decoder entry for future requests.

`open_wear_project` can switch the attached window into Dress-up using a selected
`.vroid`/`.xroid` under the client lab's saves directory. It still requires a
fresh wear token and explicit `discard_unsaved=true`: it loads that file, rather
than saving or silently transferring the current unsaved model. Close the canvas
first. Character `save_as`, `open_model`, `new_model`, XRoid save and XWear import
remain refused in attached mode because their existing implementations change
file ownership or depend on the copy's profile guard.

Native dialogs, notification dialogs, progress locks and popup blockers refuse
writes. An active texture canvas refuses geometry and unrelated screen changes.
A disabled Unity owner window (for example, a Windows file dialog) refuses RPC
submission; status reports `current_state_unavailable` rather than a confirmed
model. Finish the dialog in VRoid; the server never clicks it on your behalf.

Every attached public edit records its tool name and dispatch count in the target
process's environment before editing, and clears the receipt after verification.
It contains no image payloads or model files. If the host dies or a dispatched edit
fails, the receipt survives and blocks writes on reattachment, including from a
different client lab. Read-only parameter/layer inspection remains available.
Use `get_attached_state`, inspect actual parameters, layers and created files, then
pass its fresh `recovery_token` to `acknowledge_attached_state`. Changes to native
history, model identity or file association invalidate the review; busy/modal
states cannot be acknowledged. Acknowledgment only unblocks further edits: it
does not retry, undo or certify the interrupted operation. The receipt survives
host exit, not VRoid or Windows exit; old agents did not create it.

Obtain the current model token with `list_face_params`. `list_parts` enumerates
active transferable groups, their type, native ID and resource identity.
`list_parts` also returns registered closet `custom_items` and `savable_types`.
`replace_part` accepts catalog-verified built-ins and registered closet IDs; unknown
IDs are rejected before the native loader. Custom items use native closet selection. Already
active parts are reported as a no-op. After replacement, re-list parts and
parameters. Verified sessions await native PNG callbacks before further editing.
`save_custom_items` saves new items into the current VRoid profile, optionally restricted to unique
`types` from `savable_types`. It verifies new files, ZIP integrity, root metadata
and native closet registration. Existing items are never overwritten. Attached
mode pins the native closet root and writes into the target window's profile,
preserving the associated character filename and an existing unsaved flag.
It does not save the character file. Failed or partial batches are uncertain: inspect the closet
before retrying. Save results include file paths, IDs, sizes and SHA-256 hashes.

`export_vrm` exports an ordinary edit model in VRM 0.x (`version=0`) or 1.0
(`version=1`) to a new filename in `lab/saves`. It uses the model's existing
native export permissions and other metadata; optional `title` and `author`
override only the output name and author. Output is first staged, structurally
checked for the requested VRM extension, and then published without overwriting
an existing filename. A timed-out native export is uncertain: do not repeat it
blindly. Container checks are not complete VRM, visual or engine validation.

## Reproduce attachment lifecycle checks

Run this against a supported installation and a **new** output directory:

```powershell
& .\.venv\Scripts\python.exe .\tools\check_attached_sessions.py `
  --source "C:\Program Files\VRoid Studio" `
  --out "D:\VRoid-Attachment-Check-F00" --variant F00
```

Use `--variant M00` with another new output directory for the second model type.
The script copies and hashes the source installation, creates an isolated test
profile, and drives a test-owned external process through the real MCP stdio
interface. It never selects an existing user window. The startup fixture guard
belongs to the test; the attached MCP agent itself still has no profile guard.

Native checks cover home-screen attachment, creating a model after attachment,
same-PID idempotence, face edits and Undo/Redo, refused operations, detach and
reattach with unsaved edits, stale-token refusal, normal client EOF cleanup,
new-client recovery, live-host contention, forced Python-host termination,
subsequent lease recovery, attached restart, and target-process termination. Background
policy is measured before attachment and again after detach and normal EOF.
Results go to `checks.json`; application and server logs stay under the output.

`tools/check_attached_editing.py` takes the same arguments and a different NEW
output directory. It covers a preexisting file and unsaved edits, native unsaved
dialogs/progress locks, a disabled OS owner, a real Windows file picker and its
cancellation, repeated texture entry, exact layer
pixels and Undo/Redo, custom item saving, stale review rejection, interruption
mid-import with pending managed PNG completions, cross-client recovery and
explicit-discard Dress-up entry. Its delayed response and native sleep are
fixture-only fault injection; product code contains neither.

These controlled checks do not establish all M00 editing features, arbitrary
native dialogs, unscripted simultaneous human interaction, or host/target OS
crash recovery. The file picker is shown by a test helper with the Unity window
as owner; it is not every VRoid-specific picker or save/overwrite prompt.
Independent real-profile acceptance remains pending in BETA_TESTING.md.

On the supported 2.14.0 build, F00 and M00 each passed all 17 attached-editing
checks. The updated F00 lifecycle replay also passed all 18 checks. Offline
regression reports 545 passed / 1 skipped and nine JS behavior suites; the two
recovery tools bring the exposed set to 94. All 92 earlier input schemas retain
their original combined hash (`sha256:a6cf58ccc25f4db7b224500d9806d75acf277baf034f57a33e90a108339e8034`).
