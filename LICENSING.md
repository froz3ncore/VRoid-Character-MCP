# Licensing and project ancestry

This is [froz3ncore VRoid Character MCP](https://github.com/froz3ncore/VRoid-Character-MCP).
The community capability migration incorporates MIT-licensed work from the
[BunnyBlack fork](https://github.com/BunnyBlack/VRoid-Character-MCP), originally
adapted from mcjo79, and from shamsievartyom. Pinned sources and notices follow below.

## Status: reimplementation complete

This repository began as a fork of
[Karylcode/VRoid-MCP](https://github.com/Karylcode/VRoid-MCP), which is public
whose baseline commit `9b264d3` contained no LICENSE, COPYING or NOTICE file,
and whose GitHub API then reported `license: null`. Public visibility
is not a grant, so inherited code could not simply be relicensed.

The inherited implementation has therefore been **replaced**. All 26 baseline
paths recorded in [UPSTREAM.json](UPSTREAM.json) are now rewritten, removed or
reduced to declarative configuration, and `tools/check_provenance.py` measures
that claim rather than asserting it: it compares every baseline blob with the
current file (ordered line matching) and separately searches the whole source
tree for inherited lines that were moved into new modules. No path exceeded the
rewrite threshold and no cross-file moved-code findings remained at the original
audit; see the recorded results in REWRITE.md.

Upstream subsequently added an MIT licence in October 2026. The later commit
`baaa94e2fdc0419c68cb83b0ecc0b61fcc5661dd` is the source for parts of the
ordinary-edit exporter, part operations, late-attachment and isolation changes.
Its copyright and MIT text are retained in
[licenses/karylcode-upstream-20261023.txt](licenses/karylcode-upstream-20261023.txt).
The old baseline's former licensing status is not a statement about the licence
of the later revision.

The historical rewrite was behaviour-driven: its then-published tool contract (86 tools and
their JSON schemas) was captured before each step and compared afterwards, with
unit tests, the read-only native domain check and a clean-lab run to an exported
VRM as the other gates. `REWRITE.md` records the order and the gates. The later
103-tool upstream baseline and its acceptance scope are described in [SCOPE.md](SCOPE.md).

## What the licence covers

[LICENSE](LICENSE) is the standard MIT text, unmodified, and covers the code in
this repository. It does not grant rights to VRoid Studio, the VRM format, or
any character produced with this tool; those keep their own terms.

`UPSTREAM.json` is kept as a **record of the original project and of what was
replaced** - an acknowledgement, not a licence claim, and not a statement that
upstream code is redistributable. Anyone reusing this repository should treat
upstream material on its own terms.

## Third-party material

The adapted brainrom/vroid-studio-mcp preset labels and algorithms keep their
existing MIT licences and attribution in the five directories listed in
[NOTICE](NOTICE). Their notices are not replaced by this repository's copyright
statement. Dependencies (`frida`, `mcp`, `frida-il2cpp-bridge`) retain their own
licences.

Character models, texture source assets, Blender sources and full acceptance
archives stay local. The selected native screenshots under `assets/showcase/`
are included as visual documentation; see that directory's README and
SOURCES.json for their origins. They are excluded from the code's MIT grant
and do not convey a licence to the characters, clothing or VRoid Studio.

## mcjo79 capability migration

The migration reference is [mcjo79/vroid-mcp](https://github.com/mcjo79/vroid-mcp)
at commit `0dc7d5eb3cf27f7f943713960cac1b65f479a876`, whose MIT notice names
Copyright (c) 2026 mcjo79 and vroid-mcp contributors. Its complete LICENSE is
preserved by file-level copy in
[licenses/mcjo79-0dc7d5e.txt](licenses/mcjo79-0dc7d5e.txt).
[MIGRATION.md](MIGRATION.md) records source files, destination ownership and
per-capability implementation/verification state. Runtime adaptations include
ordinary export options, group and material editing, hair controls, camera
capture, preset catalog storage and framing. The matrix distinguishes those
adaptations from existing target behavior and records the limits of verification.

The Python MCP, Frida and JavaScript architecture remains the control kernel.
The source BepInEx/Harmony/HTTP runtime is not incorporated. This attribution
does not replace the brainrom or Karylcode notices, change the historic
unlicensed-baseline record, or grant rights to VRoid binaries, native preset
images, user custom items or generated character assets. Catalog images must
remain local unless separately licensed for redistribution.

## Community fork adaptations

[BunnyBlack/VRoid-Character-MCP](https://github.com/BunnyBlack/VRoid-Character-MCP)
`feat/mcjo79-capability-migration` at `c19aeff09c3200f6755013f6d28a476d91f7b7f6`
is the integration this repository adopted for the mcjo79 migration. That fork
remains MIT. Its Steam 2.16.0 assembly admission was not adopted; this
repository keeps the guarded pixiv-signed 2.16.0 allowlist.

[shamsievartyom/VRoid-Character-MCP](https://github.com/shamsievartyom/VRoid-Character-MCP)
`main` at `cb71a749f7045176154850a121a0d5081197ec37`, Copyright (c) 2026
Shamsiev Artem, is MIT as a fork of this repository. Clothing template tools,
clothing texture-editor modes, compact canvas IDs, optional image-free review
captures, `client_repl.py`, the preset comparison report and the reference
workflow text are adapted from that revision. The client does not clear the
installed protocol association.
