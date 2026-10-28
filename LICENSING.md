# Licensing and project ancestry

VRoid Character MCP is maintained at
https://github.com/froz3ncore/VRoid-Character-MCP.

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
VRM as the other gates. `REWRITE.md` records the order and the gates. The current
103-tool development contract and acceptance scope are described in [SCOPE.md](SCOPE.md).

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
