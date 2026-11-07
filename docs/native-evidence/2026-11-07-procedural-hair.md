# Procedural hair binding identity: static evidence

Only the pixiv-signed standalone VRoid Studio 2.14.0 assembly with SHA-256
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
Bounds are read from the live native control, rather than embedded constants.

The pinned frida-il2cpp-bridge 0.14.0 maps the actual `System.Delegate.method_ptr`
field's native signed-integer type to NativePointer. Pointer `.equals` therefore
compares code addresses directly. Nested class matching uses `class.name` and
`class.declaringClass`, avoiding assumptions about `type.name` nesting separators.

These facts establish static control identity. Native dispatch ABI, actual
Undo/Redo, save/reopen behavior, regeneration and visual acceptance remain
unverified. Compiler-generated method ordinals must never be reused on another
assembly digest merely because the names happen to agree.
