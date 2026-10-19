# Licensing and project ancestry

VRoid Character MCP is maintained at
https://github.com/froz3ncore/VRoid-Character-MCP.

## Status: reimplementation complete

This repository began as a fork of
[Karylcode/VRoid-MCP](https://github.com/Karylcode/VRoid-MCP), which is public
but carries **no licence**: GitHub reports `license: null` and the baseline
commit `9b264d3` contains no LICENSE, COPYING or NOTICE file. Public visibility
is not a grant, so inherited code could not simply be relicensed.

The inherited implementation has therefore been **replaced**. All 26 baseline
paths recorded in [UPSTREAM.json](UPSTREAM.json) are now rewritten, removed or
reduced to declarative configuration, and `tools/check_provenance.py` measures
that claim rather than asserting it: it compares every baseline blob with the
current file (ordered line matching) and separately searches the whole source
tree for inherited lines that were moved into new modules. Both passes are
empty, and nothing above the 0.10 threshold remains.

The rewrite was behaviour-driven: the published tool contract (86 tools and
their JSON schemas) was captured before each step and compared afterwards, with
unit tests, the read-only native domain check and a clean-lab run to an exported
VRM as the other gates. `REWRITE.md` records the order and the gates.

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

Development assets - character models, textures, Blender sources and acceptance
images - stay local and are excluded from this repository.
