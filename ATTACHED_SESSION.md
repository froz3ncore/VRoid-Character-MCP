# Existing VRoid sessions, parts and ordinary VRM export

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
reconnect and detach normally; recovery is not immediate. Confirmed unsaved
edits survived the controlled idle-host termination test. An interrupted edit
or export still has an uncertain result and must not be replayed blindly.
This recovery applies to leases written by this version; older agents did not
record this state. Unknown/corrupt ownership records are refused, not guessed.

Prior manual edits are not observable to this server. To preserve the existing
workaround for native body/texture and texture/Dress-up crashes, attached mode
refuses `open_texture_editor` and `open_wear_project`. File-based Dress-up save
and import operations are also refused to avoid repointing the user's file.
For those operations, save and reopen in an isolated copy.

Obtain the current model token with `list_face_params`. `list_parts` enumerates
active transferable groups, their type, native ID and resource identity.
`list_parts` also returns registered closet `custom_items` and `savable_types`.
`replace_part` accepts catalog-verified built-ins and registered closet IDs; unknown
IDs are rejected before the native loader. Custom items use native closet selection. Already
active parts are reported as a no-op. After replacement, re-list parts and
parameters. Verified copies await native PNG callbacks before further editing;
attached sessions still refuse texture entry. `save_custom_items`
saves new items into the isolated copy profile, optionally restricted to unique
`types` from `savable_types`. It verifies new files, ZIP integrity, root metadata
and native closet registration. Existing items are never overwritten. Attached
sessions are refused. Failed or partial batches are uncertain: inspect the closet
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

F00 and M00 each passed 18 checks on the supported 2.14.0 build. This
does not establish full M00 editing coverage, modal-dialog handling, multiple
human users, or recovery of edits interrupted mid-call or a host OS crash.
Independent real-profile acceptance remains pending in BETA_TESTING.md.
