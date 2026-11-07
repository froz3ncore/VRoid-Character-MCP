# Procedural hair binding identity: static evidence

This record describes the original 2.14.0 mapping. The subsequent
[2.16.0 audit](2026-11-07-vroid-216.md) records separate mappings for that release.
Of the two 2.14.0 packages, only the pixiv-signed standalone assembly with SHA-256
`ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296`
has a verified procedural descriptor. The existing global supported-build
allowlist is unchanged. The other allowlisted assembly, `793eb5fc...`, is
explicitly unsupported for this descriptor until separately mapped.

The official package was signature-checked and inspected without installing,
launching or loading its native code. Installer SHA-256:
`d59ad962cebcaa3375b7add4c457f653b4b82d1b554b3040ce1b092caea18f38`.
Extracted metadata SHA-256:
`5c018d995e25b59677c9c4bb9171746d742ca94d9ed9c236b972ebca65493b8e`.
Neither native binaries nor copied native method bodies are distributed here.

The owner is
`VRoid.Studio.HairEditor.DesignEditor.HairGroup.ViewModel.ProceduralHairGroupPropertyViewModel`.
Its `_engine` and `_proceduralHairGroupPath` establish the exact owner.
Nested closure `<>c__DisplayClass7_0` has field `a` referencing nested
`Accessor`, which independently carries `_engine` and `_proceduralHairGroupPath`.

| Property | Native getter | Native setter | Setter's native managed modifier | Verified backing field |
| --- | --- | --- | --- | --- |
| Length (Single) | `<CreateGroups>b__41`, RVA `0x33d0fe0` | `<CreateGroups>b__42`, RVA `0x33d1020` | `<>c__DisplayClass7_15.<CreateGroups>b__97`, RVA `0x33d2500` | `ProceduralFormParameterSet.<Length>k__BackingField`, offset 16 |
| HairCount (Int32) | `<CreateGroups>b__51`, RVA `0x33d15d0` | `<CreateGroups>b__52`, RVA `0x33d1600` | `<>c__DisplayClass7_20.<CreateGroups>b__102`, RVA `0x33d25f0` | `ProceduralFormParameterSet.<HairCount>k__BackingField`, offset 36 |

Both getter routes call `Accessor.Get`, then use
`ProceduralHairGroupParameterSet.<ProceduralFormParameterSet>k__BackingField`
(offset 48). Both setter routes use `Accessor.Set` and native managed modifiers.
Those modifiers can be retained by native history. The implementation calls
the existing VM `set_Value`; it creates no JS-owned managed history delegate.

The exact FloatParameterViewModel/IntParameterViewModel classes in namespace
`VRoid.Studio.HairEditor.DesignEditor.Parameter.ViewModel` carry `_getter`,
`_setter`, native min/max and value methods. Their base owns native `validator`.
At runtime both delegate code pointers must match the verified reflected
methods, both delegate targets must be the same closure instance, their declaring
class must be the current property class, and both engine/path owners must match.
Item positions, localized labels and current-value coincidence are unused.
Existing, exact native UI-owned properties provide their live ranges. Looking
up the current DesignEditor.Property does not create a property or alter selection.
Its engine, model, file, action handler and exact procedural path are checked.

For an unselected or hidden path, the descriptor can instead use the verified
native managed modifier directly. The signed CreateGroups body supplies immutable
UI bounds: Length min `Math.fround(0.1)`, max `1`, precision `3`; HairCount min
`1`, max `20`. These are explicitly labeled static native UI bounds for this
assembly. Values are converted to Single before range admission, so JSON `0.1`
is accepted at the true native minimum. The ordinary VM and static routes must
not be generalized to another assembly digest.

The fallback allocates the existing native capture class, initializes its exact
typed `v` field, and calls the real native Action constructor with that capture
and the verified native modifier MethodInfo handle. It validates the closed
Action Invoke signature, target and native code pointer before constructing
`ModifyProceduralHairGroupParameterSetCommand(key, path, action, reuseStrands)`.
The subsequent paired audit traced the UI keys and flags on this build and
2.16.0. Length supplies `"ProceduralLength", true`; HairCount supplies
`"HairCount", false`.
This follows the pinned bridge's native delegate constructor ABI without creating
or substituting any JS callback. Native history owns the managed Action/capture.
The exact active-owner binding and native GetIsPathValidQuery are checked before
dispatch; neither an Accessor nor guide/property constructor is required.

Direct property construction is deliberately unused: its constructor subscribes
to engine updates, and CreateGroups also creates material listeners. Releasing
a pin would not unregister those subscriptions after a partial constructor.
No temporary property, subscription observer or process-wide hook is installed.

Each requested procedural scalar is dispatched as one step, settled, and read
from the real configured parameter set before another step begins. Immediate
publication is not assumed. A genuine uncertain invocation stops the sequence.
Receipts distinguish VM setter calls from explicit native command calls; merged
history/undo-entry deltas remain unobserved.

The pinned frida-il2cpp-bridge 0.14.0 maps the actual `System.Delegate.method_ptr`
field's native signed-integer type to NativePointer. Pointer `.equals` therefore
compares code addresses directly. Nested class matching uses `class.name` and
`class.declaringClass`, avoiding assumptions about `type.name` nesting separators.

These facts establish static control identity. Native dispatch ABI, actual
Undo/Redo, save/reopen behavior, regeneration and visual acceptance remain
unverified. Compiler-generated method ordinals must never be reused on another
assembly digest merely because the names happen to agree.
