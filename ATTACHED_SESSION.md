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
parameters; a cold reopen is required before texture editing. `save_custom_items`
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
