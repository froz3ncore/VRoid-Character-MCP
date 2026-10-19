"""Parse a .vrm file independently of VRoid Studio and report its content.

The tool layer hands a VRM to the next stage, so the last step of acceptance
must not trust the exporter's own report: this reads the GLB container and the
VRM JSON chunk directly and lists what a consumer would actually find.

    python tools/vrm_inspect.py path/to/character.vrm [--json out.json]

Supports VRM 0.x (``VRM`` extension) and VRM 1.0 (``VRMC_vrm``).
Checks structural references and a delivery profile, not complete glTF/VRM
schema compliance or visual/physics acceptance. The default profile requires
expressions and spring chains; explicitly allow their absence when appropriate.
Exits 1 on structural/profile errors, 2 on an unreadable container.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import sys

GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A

REQUIRED_HUMANOID = ['hips', 'spine', 'head', 'leftUpperArm', 'rightUpperArm',
                     'leftLowerArm', 'rightLowerArm', 'leftHand', 'rightHand',
                     'leftUpperLeg', 'rightUpperLeg', 'leftLowerLeg', 'rightLowerLeg',
                     'leftFoot', 'rightFoot']
# Required roles: vrm-c/vrm-specification, VRMC_vrm-1.0 humanBones schema.


def read_glb(path: pathlib.Path) -> dict:
    raw = path.read_bytes()
    if len(raw) < 20:
        raise ValueError('file is too small to be a GLB')
    magic, version, length = struct.unpack_from('<III', raw, 0)
    if magic != GLB_MAGIC or version != 2:
        raise ValueError('not a GLB 2 container (bad magic/version)')
    if length != len(raw):
        raise ValueError(f'declared length {length} != file size {len(raw)}')
    offset = 12
    document = None
    kinds = []
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError('truncated GLB chunk header')
        chunk_length, chunk_type = struct.unpack_from('<II', raw, offset)
        if chunk_length % 4:
            raise ValueError('unaligned GLB chunk length')
        body = raw[offset + 8: offset + 8 + chunk_length]
        if len(body) != chunk_length:
            raise ValueError('truncated GLB chunk')
        if not kinds and chunk_type != JSON_CHUNK:
            raise ValueError('first GLB chunk must be JSON')
        if chunk_type in (JSON_CHUNK, 0x004E4942) and chunk_type in kinds:
            raise ValueError('duplicate GLB JSON/BIN chunk')
        if chunk_type == JSON_CHUNK:
            document = json.loads(body.decode('utf-8'))
        kinds.append(chunk_type)
        offset += 8 + chunk_length
    if not isinstance(document, dict):
        raise ValueError('GLB JSON must be an object')
    return document


def humanoid(vrm: dict, version: str, nodes: list) -> dict:
    problems = []
    if version == '1.0':
        bones = (vrm.get('humanoid') or {}).get('humanBones') or {}
        if not isinstance(bones, dict):
            bones = {}; problems.append('VRM1 humanBones must be an object')
        pairs = list(bones.items())
    else:
        bones = (vrm.get('humanoid') or {}).get('humanBones') or []
        if not isinstance(bones, list):
            bones = []; problems.append('VRM0 humanBones must be an array')
        pairs = [(b.get('bone'), b) if isinstance(b, dict) else (None, {}) for b in bones]
    names = []; used = {}
    for name, bone in pairs:
        if not isinstance(name, str) or not name:
            problems.append('invalid humanoid role'); continue
        if name in names:
            problems.append('duplicate humanoid role: ' + name)
        names.append(name)
        node = bone.get('node') if isinstance(bone, dict) else None
        if type(node) is not int or not 0 <= node < len(nodes):
            problems.append('invalid humanoid node: ' + name)
        elif node in used:
            problems.append(f'humanoid roles {used[node]} and {name} share a node')
        else:
            used[node] = name
    return {'count': len(names), 'bones': names,
            'missing_required': sorted(set(REQUIRED_HUMANOID) - set(names)),
            'invalid_references': problems}


def expressions(vrm: dict, version: str) -> dict:
    if version == '1.0':
        preset = ((vrm.get('expressions') or {}).get('preset')) or {}
        custom = ((vrm.get('expressions') or {}).get('custom')) or {}
        return {'preset': sorted(preset), 'custom': sorted(custom)}
    groups = ((vrm.get('blendShapeMaster') or {}).get('blendShapeGroups')) or []
    return {'preset': sorted(g.get('presetName', '') for g in groups if g.get('presetName') not in (None, '', 'unknown')),
            'custom': sorted(g.get('name', '') for g in groups if g.get('presetName') in (None, '', 'unknown'))}


def reference_findings(doc: dict, vrm: dict, version: str) -> list[str]:
    errors = []; nodes = doc.get('nodes') or []; meshes = doc.get('meshes') or []
    def index(value, items, label):
        valid = type(value) is int and 0 <= value < len(items)
        if not valid: errors.append('invalid ' + label + ' index')
        return valid
    def morph(mesh, target):
        if not index(mesh, meshes, 'expression mesh'): return
        primitives = meshes[mesh].get('primitives') or []
        if not primitives: errors.append('expression mesh has no primitives')
        for primitive in primitives: index(target, primitive.get('targets') or [], 'expression morph target')
    for node in nodes:
        for child in node.get('children') or []: index(child, nodes, 'child node')
        if 'mesh' in node: index(node['mesh'], meshes, 'node mesh')
    if version == '1.0':
        expression = vrm.get('expressions') or {}
        for group in ('preset', 'custom'):
            for item in (expression.get(group) or {}).values():
                for bind in item.get('morphTargetBinds') or []:
                    node = bind.get('node')
                    if index(node, nodes, 'expression node'): morph(nodes[node].get('mesh'), bind.get('index'))
        spring = (doc.get('extensions') or {}).get('VRMC_springBone') or {}
        colliders = spring.get('colliders') or []; groups = spring.get('colliderGroups') or []
        for collider in colliders: index(collider.get('node'), nodes, 'collider node')
        for group in groups:
            for collider in group.get('colliders') or []: index(collider, colliders, 'collider group')
        for chain in spring.get('springs') or []:
            joints = chain.get('joints') or []
            if not joints: errors.append('spring chain has no joints')
            for joint in joints: index(joint.get('node'), nodes, 'spring joint')
            if 'center' in chain: index(chain['center'], nodes, 'spring center')
            for group in chain.get('colliderGroups') or []: index(group, groups, 'spring collider group')
    else:
        for group in (vrm.get('blendShapeMaster') or {}).get('blendShapeGroups') or []:
            for bind in group.get('binds') or []: morph(bind.get('mesh'), bind.get('index'))
        spring = vrm.get('secondaryAnimation') or {}; colliders = spring.get('colliderGroups') or []
        for collider in colliders: index(collider.get('node'), nodes, 'collider group node')
        for chain in spring.get('boneGroups') or []:
            bones = chain.get('bones') or []
            if not bones: errors.append('spring bone group has no bones')
            for node in bones: index(node, nodes, 'spring bone')
            if chain.get('center', -1) != -1: index(chain['center'], nodes, 'spring center')
            for collider in chain.get('colliderGroups') or []: index(collider, colliders, 'spring collider group')
    return errors


def springs(doc: dict, vrm: dict, version: str) -> dict:
    if version == '1.0':
        ext = (doc.get('extensions') or {}).get('VRMC_springBone') or {}
        chains = ext.get('springs') or []
        colliders = ext.get('colliders') or []
        joints = sum(len(c.get('joints') or []) for c in chains)
        return {'chains': len(chains), 'joints': joints, 'colliders': len(colliders)}
    groups = ((vrm.get('secondaryAnimation') or {}).get('boneGroups')) or []
    colliders = ((vrm.get('secondaryAnimation') or {}).get('colliderGroups')) or []
    joints = sum(len(g.get('bones') or []) for g in groups)
    return {'chains': len(groups), 'joints': joints, 'colliders': len(colliders)}


def inspect(path: pathlib.Path, *, allow_no_expressions: bool = False, allow_no_springs: bool = False) -> dict:
    doc = read_glb(path)
    extensions = doc.get('extensions') or {}
    if 'VRMC_vrm' in extensions:
        version, vrm = '1.0', extensions['VRMC_vrm']
    elif 'VRM' in extensions:
        version, vrm = '0.0', extensions['VRM']
    else:
        raise ValueError('no VRM or VRMC_vrm extension in the GLB')
    meta = vrm.get('meta') or {}
    nodes = doc.get('nodes') or []
    hum = humanoid(vrm, version, nodes)
    exp = expressions(vrm, version)
    spring = springs(doc, vrm, version)
    findings: list[str] = list(hum['invalid_references'])
    warnings: list[str] = []
    findings.extend(reference_findings(doc, vrm, version))
    if (doc.get('asset') or {}).get('version') != '2.0':
        findings.append('glTF asset.version must be 2.0')
    if version == '1.0' and vrm.get('specVersion') != '1.0':
        findings.append('unsupported VRMC_vrm specVersion')
    if hum['missing_required']:
        findings.append('humanoid is missing required bones: ' + ', '.join(hum['missing_required']))
    if not exp['preset'] and not exp['custom']:
        (warnings if allow_no_expressions else findings).append('no expressions found')
    if spring['chains'] == 0:
        (warnings if allow_no_springs else findings).append('no spring bone chains found')
    return {
        'schema': 'vroid-vrm-inspect-v2',
        'path': str(path),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'size_bytes': path.stat().st_size,
        'gltf_asset': (doc.get('asset') or {}).get('version'),
        'vrm_version': version,
        'spec_version': vrm.get('specVersion') or vrm.get('exporterVersion'),
        'title': meta.get('name') or meta.get('title'),
        'author': meta.get('authors') or meta.get('author'),
        'meshes': len(doc.get('meshes') or []),
        'materials': len(doc.get('materials') or []),
        'images': len(doc.get('images') or []),
        'nodes': len(doc.get('nodes') or []),
        'skins': len(doc.get('skins') or []),
        'humanoid': hum,
        'expressions': exp,
        'spring_bone': spring,
        'findings': findings,
        'warnings': warnings,
        'ok': not findings,
        'profile': {'require_expressions': not allow_no_expressions, 'require_springs': not allow_no_springs},
        'scope': 'Structural references and delivery-profile checks; not complete VRM/glTF schema compliance, visual or physics acceptance',
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Parse a VRM file without VRoid Studio')
    parser.add_argument('path', help='.vrm file')
    parser.add_argument('--json', dest='json_out', default='', help='write the report here')
    parser.add_argument('--allow-no-expressions', action='store_true', help='allow an avatar without expressions, reported as a warning')
    parser.add_argument('--allow-no-springs', action='store_true', help='allow an avatar without spring chains, reported as a warning')
    args = parser.parse_args(argv)
    path = pathlib.Path(args.path)
    if not path.is_file():
        print(f'not a file: {path}', file=sys.stderr)
        return 2
    try:
        report = inspect(path, allow_no_expressions=args.allow_no_expressions, allow_no_springs=args.allow_no_springs)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, struct.error) as error:
        print(f'cannot parse {path}: {error}', file=sys.stderr)
        return 2
    if args.json_out:
        pathlib.Path(args.json_out).write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n',
                                               encoding='utf-8')
    print(json.dumps({k: report[k] for k in
                      ('vrm_version', 'title', 'humanoid', 'expressions', 'spring_bone', 'findings', 'warnings', 'ok')},
                     ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
