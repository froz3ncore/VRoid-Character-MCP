"""Body-skin masks, decals, freckles, moles and conservative toenail discovery.

Painting reuses bounded_paint.render_marks. This module only measures where
pixels may land and rejects placements that leave the measured mask.
"""
import hashlib, json, math, random, re
from collections import Counter
from .bounded_paint import decode_rgba_png, render_marks
from .texture_mapping import add, cross, length, point, raster_nails, sub, unit

MAX_PIXELS = 4194304
MAX_WORK = 8000000
SHARED_DISTANCE_M = 0.02


def _barycentric(a, b, c, x, y):
    den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(den) < 1e-12:
        return None
    u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / den
    v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / den
    w = 1 - u - v
    if min(u, v, w) < -1e-8:
        return None
    return (u, v, w)


def raster_body_mask(meshes, image, width, height):
    """Raster UV triangles for one canvas image. Shared pixels are those hit by surfaces more than 2 cm apart."""
    if not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height > MAX_PIXELS:
        raise ValueError('Unsupported body texture resolution')
    selected = [m for m in meshes if m.get('image') == image]
    if not selected:
        raise ValueError('No body overlay mesh uses this canvas image')
    mask = bytearray(width * height)
    owners = {}
    shared = set()
    work = 0
    triangles = 0
    for mesh in selected:
        positions = mesh.get('positions') or []
        uv = mesh.get('uv0') or []
        if not positions or len(positions) != len(uv) or len(positions) > 100000:
            raise ValueError('Body overlay vertex and UV counts disagree')
        indices = [i for sub in mesh.get('submeshes') or [] for i in sub.get('triangles') or []]
        if len(indices) % 3 or len(indices) > 300000:
            raise ValueError('Invalid body triangle stream')
        for index in indices:
            if not isinstance(index, int) or not 0 <= index < len(positions):
                raise ValueError('Body triangle index is outside the vertex stream')
        for start in range(0, len(indices), 3):
            ids = indices[start:start + 3]
            tex = []
            world = []
            for i in ids:
                u, v = uv[i]
                p = positions[i]
                if len(p) != 3 or len((u, v)) != 2 or any(not math.isfinite(n) for n in (*p, u, v)) or not 0 <= u <= 1 or not 0 <= v <= 1:
                    raise ValueError('Body UV or position is not finite and inside 0..1')
                tex.append((u * width, (1 - v) * height))
                world.append(p)
            triangles += 1
            xmin = max(0, math.floor(min(p[0] for p in tex)))
            xmax = min(width, math.ceil(max(p[0] for p in tex)))
            ymin = max(0, math.floor(min(p[1] for p in tex)))
            ymax = min(height, math.ceil(max(p[1] for p in tex)))
            work += max(0, xmax - xmin) * max(0, ymax - ymin)
            if work > MAX_WORK:
                raise ValueError('Body rasterization exceeds the work limit')
            for y in range(ymin, ymax):
                for x in range(xmin, xmax):
                    weights = _barycentric(*tex, x + .5, y + .5)
                    if weights is None:
                        continue
                    pos = [sum(p[k] * w for p, w in zip(world, weights)) for k in range(3)]
                    pixel = y * width + x
                    previous = owners.get(pixel)
                    if previous is not None and math.dist(previous, pos) > SHARED_DISTANCE_M:
                        shared.add(pixel)
                    elif previous is None:
                        owners[pixel] = pos
                    mask[pixel] = 255
    if not any(mask):
        raise ValueError('Body canvas has no paintable UV coverage')
    return bytes(mask), {
        'pixels': sum(a > 0 for a in mask),
        'triangle_count': triangles,
        'shared_uv_pixels': len(shared),
        'anatomical_sides_independent': len(shared) == 0,
        'coordinate_system': 'Normalized canvas x-right/y-down, origin top-left. Not Unity UV and not a left/right body side.',
        'shared_uv_rule': 'A pixel covered by surfaces more than 2 cm apart is shared. Painting it changes every surface that uses it; mirror_x only reflects the canvas.',
    }


def _fit_decal(width, height, mask, source, center, scale, rotation_deg):
    sw, sh, rgba = source
    if not (isinstance(center, (list, tuple)) and len(center) == 2):
        raise ValueError('Decal center needs normalized x and y')
    cx, cy = center
    for value, lo, hi in ((cx, 0, 1), (cy, 0, 1), (scale, 0.02, 1), (rotation_deg, -180, 180)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError('Decal placement is outside its finite range')
    dest_cx = cx * width
    dest_cy = cy * height
    # scale is the source width as a fraction of the shorter destination side.
    dest_w = scale * min(width, height)
    uniform = dest_w / sw
    angle = math.radians(rotation_deg)
    cos = math.cos(angle)
    sin = math.sin(angle)
    out = bytearray(width * height * 4)
    opaque = clipped = written = 0
    # Scan the full projected rectangle, including pixels outside the canvas.
    # Clamping first would silently discard opaque pixels before validation.
    dest_h = uniform * sh
    half_x = (abs(cos) * dest_w + abs(sin) * dest_h) / 2
    half_y = (abs(sin) * dest_w + abs(cos) * dest_h) / 2
    x0, x1 = math.floor(dest_cx - half_x), math.ceil(dest_cx + half_x)
    y0, y1 = math.floor(dest_cy - half_y), math.ceil(dest_cy + half_y)
    if (x1 - x0) * (y1 - y0) > MAX_WORK:
        raise ValueError('Decal placement exceeds the bounded pixel-work limit')
    for y in range(y0, y1):
        for x in range(x0, x1):
            dx = (x + .5) - dest_cx
            dy = (y + .5) - dest_cy
            # Inverse of a clockwise canvas rotation (y down).
            lx = dx * cos + dy * sin
            ly = -dx * sin + dy * cos
            sx = sw / 2 + lx / uniform
            sy = sh / 2 + ly / uniform
            if not (0 <= sx < sw and 0 <= sy < sh):
                continue
            sample = rgba[(int(sy) * sw + int(sx)) * 4:(int(sy) * sw + int(sx)) * 4 + 4]
            if sample[3] == 0:
                continue
            opaque += 1
            if not (0 <= x < width and 0 <= y < height) or not mask[y * width + x]:
                clipped += 1
                continue
            out[(y * width + x) * 4:(y * width + x) * 4 + 4] = sample
            written += 1
    if opaque == 0:
        raise ValueError('Decal has no opaque pixels')
    if clipped:
        raise ValueError('Decal does not fit inside the measured mask; it would paint outside the body UV coverage')
    if written == 0:
        raise ValueError('Decal misses the measured mask')
    return out, {'opaque_pixels': opaque, 'clipped_pixels': clipped, 'written_pixels': written,
                 'placement': {'center': [cx, cy], 'scale': scale, 'rotation_deg': rotation_deg,
                               'scale_meaning': 'Source width divided by the shorter destination side',
                               'rotation_meaning': 'Clockwise degrees in top-left canvas space, about the decal center',
                               'alpha': 'Source alpha is copied; destination pixels outside the mask stay transparent'}}


def composite_decal(width, height, mask, png_bytes, center, scale, rotation_deg):
    source = decode_rgba_png(png_bytes)
    raw, stats = _fit_decal(width, height, mask, source, center, scale, rotation_deg)
    from .texture_mapping import png_rgba
    return png_rgba(width, height, raw), stats


def freckle_marks(width, height, mask, seed, count, radius, color, min_spacing):
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**31 - 1:
        raise ValueError('Freckle seed must be an integer from 0 through 2^31-1')
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 256:
        raise ValueError('Freckle count must be 1..256')
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius) or not 0.002 <= radius <= 0.02:
        raise ValueError('Freckle radius must be 0.002..0.02 of the shorter side')
    if isinstance(min_spacing, bool) or not isinstance(min_spacing, (int, float)) or not math.isfinite(min_spacing) or not radius * 2 <= min_spacing <= 0.2:
        raise ValueError('Freckle spacing must be at least two radii and at most 0.2')
    if not isinstance(color, (list, tuple)) or len(color) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in color):
        raise ValueError('Freckle color needs four normalized channels')
    pixels = [i for i, alpha in enumerate(mask) if alpha]
    rng = random.Random(seed)
    order = pixels[:]
    rng.shuffle(order)
    spacing = min_spacing * min(width, height)
    chosen = []
    for index in order:
        y, x = divmod(index, width)
        if all((x - cx) ** 2 + (y - cy) ** 2 >= spacing * spacing for cx, cy in chosen):
            chosen.append((x + .5, y + .5))
            if len(chosen) == count:
                break
    if len(chosen) != count:
        raise ValueError('Cannot place that many freckles inside the mask at this spacing and seed')
    marks = [{'kind': 'stamp', 'points': [[x / width, y / height]], 'radius': radius, 'hardness': 0.2,
              'color': list(color), 'mirror_x': False} for x, y in chosen]
    png, stats = render_marks(width, height, mask, marks, limit=256)
    stats.update(seed=seed, count=count, reproducible=True)
    return png, stats, marks


def mole_marks(width, height, mask, moles):
    if not isinstance(moles, list) or not 1 <= len(moles) <= 32:
        raise ValueError('Use 1..32 moles')
    marks = []
    for mole in moles:
        if not isinstance(mole, dict) or set(mole) - {'point', 'radius', 'color'}:
            raise ValueError('A mole needs point, radius and color')
        point = mole['point']
        radius = mole['radius']
        color = mole['color']
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError('A mole point needs normalized x and y')
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not 0.002 <= radius <= 0.03:
            raise ValueError('Mole radius must be 0.002..0.03 of the shorter side')
        marks.append({'kind': 'stamp', 'points': [list(point)], 'radius': radius, 'hardness': 0.85,
                      'color': list(color), 'mirror_x': False})
    png, stats = render_marks(width, height, mask, marks)
    return png, stats, marks


def discover_toenails(reference, bindings):
    """Return separable targets or an explicit refusal. Never invents UV boxes."""
    refusal = {'separable': False, 'individual_toes_separable': False, 'targets': [], 'shared_uv': False}
    if reference.get('model_token') != bindings.get('model_token'):
        return {**refusal, 'reason': 'MODEL_IDENTITY_MISMATCH'}
    meshes = [m for m in reference.get('meshes') or [] if m.get('name') == 'Foot']
    renderers = [m for m in bindings.get('renderers') or [] if m.get('name') == 'Foot']
    if len(meshes) != 1 or len(renderers) != 1:
        return {**refusal, 'reason': 'FOOT_RENDERER_MISSING_OR_AMBIGUOUS',
                'detail': 'Toenails are not inferred from the hand nail map or from body-skin UV boxes.'}
    mesh = meshes[0]
    foot = renderers[0]
    materials = foot.get('materials') or []
    if len(materials) != 1:
        return {**refusal, 'reason': 'FOOT_MATERIAL_AMBIGUOUS'}
    textures = [t for t in materials[0].get('textures') or [] if t.get('property') == '_MainTex' and t.get('instance_id') is not None]
    if len(textures) != 1:
        return {**refusal, 'reason': 'FOOT_MAIN_TEXTURE_UNREADABLE'}
    texture = textures[0]
    if texture.get('offset') != [0, 0] or texture.get('scale') != [1, 1]:
        return {**refusal, 'reason': 'FOOT_UV_TRANSFORM_UNCALIBRATED'}
    positions = [point(mesh['world_matrix'], v) for v in mesh.get('positions') or []]
    uv = mesh.get('uv0') or []
    raw = mesh.get('triangles') or []
    if len(uv) != len(positions) or len(raw) % 3:
        return {**refusal, 'reason': 'FOOT_UV_STREAM_INCOMPLETE'}
    triangles = [raw[i:i + 3] for i in range(0, len(raw), 3)]
    nodes = {n['id']: n['name'] for n in reference.get('nodes') or []}
    try:
        bones = [nodes[i] for i in mesh.get('bone_nodes') or []]
    except KeyError:
        return {**refusal, 'reason': 'FOOT_BONE_NAMES_UNAVAILABLE'}
    weights = mesh.get('weights') or []
    if len(weights) != len(positions):
        return {**refusal, 'reason': 'FOOT_WEIGHTS_INCOMPLETE'}
    per_toe = re.compile(r'^J_Bip_([LR])_Toe([0-4])$')
    toe_base = re.compile(r'^J_Bip_([LR])_ToeBase$')
    parent = list(range(len(positions)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, c in triangles:
        parent[find(b)] = find(a)
        parent[find(c)] = find(a)
    groups = {}
    for i in {i for tri in triangles for i in tri}:
        groups.setdefault(find(i), []).append(i)
    candidates = {}
    for ids in groups.values():
        targets = set()
        valid = True
        for i in ids:
            skin = [(bones[b], w) for b, w in zip(weights[i]['indices'], weights[i]['weights']) if w > 1e-6]
            if len(skin) != 1 or skin[0][1] < 1 - 1e-5:
                valid = False
                break
            name = skin[0][0]
            if not (per_toe.fullmatch(name) or toe_base.fullmatch(name)):
                valid = False
                break
            targets.add(name)
        if not valid or len(targets) != 1:
            continue
        bone = next(iter(targets))
        owned = set(ids)
        faces = [(i, t) for i, t in enumerate(triangles) if set(t) <= owned]
        if len(ids) < 4 or len(faces) < 2:
            continue
        normal = [0., 0., 0.]
        area = 0.
        for _, (a, b, c) in faces:
            n = cross(sub(positions[b], positions[a]), sub(positions[c], positions[a]))
            normal = add(normal, n)
            area += length(n) / 2
        diameter = max(length(sub(positions[a], positions[b])) for a in ids for b in ids)
        if not 0.002 <= diameter <= 0.03 or area < 1e-8 or length(normal) < 1e-10:
            continue
        candidates.setdefault(bone, []).append({
            'vertex_ids': sorted(ids),
            'triangles': [t for _, t in faces],
            'uv_triangles': [[uv[i] for i in t] for _, t in faces],
            'normal': unit(normal),
            'diameter_m': diameter,
        })
    if not candidates:
        return {**refusal, 'reason': 'NO_ISOLATED_TOENAIL_CAPS',
                'detail': 'No paired cap was weighted only to a toe bone. ToeBase alone does not identify five toenails, and guessed UV coordinates are not used.'}
    individual = any(per_toe.fullmatch(name) for name in candidates)
    if individual and any(toe_base.fullmatch(name) for name in candidates):
        return {**refusal, 'reason': 'MIXED_TOE_BONE_SCHEMES'}
    targets = []
    if individual:
        for side in 'LR':
            for index in range(5):
                bone = f'J_Bip_{side}_Toe{index}'
                parts = candidates.get(bone)
                if not parts:
                    return {**refusal, 'reason': 'INCOMPLETE_PER_TOE_SET', 'detail': f'Missing {bone}'}
                paired = _paired(parts, positions)
                if paired is None:
                    return {**refusal, 'reason': 'UNPAIRED_TOENAIL_CAP', 'detail': bone}
                targets.append({'id': f"{'L' if side == 'L' else 'R'}_toe{index}", 'bone': bone, 'islands': paired})
    else:
        for side in 'LR':
            bone = f'J_Bip_{side}_ToeBase'
            parts = candidates.get(bone, [])
            paired = _paired(parts, positions)
            if paired is None:
                return {**refusal, 'reason': 'TOEBASE_CAPS_NOT_A_SEPARABLE_NAIL',
                        'detail': f'{bone} did not yield exactly one opposed cap pair isolated from the rest of the foot.'}
            targets.append({'id': f"{'L' if side == 'L' else 'R'}_toes", 'bone': bone, 'islands': paired,
                            'covers': 'all toes on this side; individual toenails are not separate'})
    from .texture_mapping import raster_nails
    try:
        masks = raster_nails({'texture': texture, 'nails': [{'id': t['id'], 'islands': t['islands']} for t in targets]})
    except ValueError as error:
        return {**refusal, 'reason': 'TOENAIL_UV_NOT_INDEPENDENT', 'detail': str(error)}
    digest = hashlib.sha256(json.dumps({'positions': mesh.get('positions'), 'world_matrix': mesh['world_matrix'],
                                       'uv': uv, 'triangles': raw, 'bones': bones, 'weights': weights,
                                       'texture': {key: texture[key] for key in ('width', 'height', 'offset', 'scale')}},
                                       sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    nails = [{'id': t['id'], 'islands': t['islands']} for t in targets]
    return {'separable': True, 'individual_toes_separable': individual, 'shared_uv': False,
            'anatomical_sides_independent': True, 'targets': [{'id': t['id'], 'bone': t['bone'], 'pixels': len(masks[t['id']]),
                                                              'covers': t.get('covers', 'one measured toe cap')} for t in targets],
            'nails': nails,
            'texture': {'width': texture['width'], 'height': texture['height']},
            'geometry_sha256': digest, 'reason': None,
            'scope': 'Hand nail discovery is not reused. Only isolated Foot caps with exclusive toe-bone weights are paintable.'}


def _paired(parts, positions):
    if len(parts) != 2:
        return None
    a, b = parts
    opposed = sum(x * y for x, y in zip(a['normal'], b['normal']))
    if opposed > -0.95:
        return None
    hausdorff = max(
        max(min(length(sub(positions[i], positions[j])) for j in b['vertex_ids']) for i in a['vertex_ids']),
        max(min(length(sub(positions[i], positions[j])) for j in a['vertex_ids']) for i in b['vertex_ids']))
    if hausdorff > min(0.002, 0.2 * max(a['diameter_m'], b['diameter_m'])):
        return None
    return parts


def bind_toenail_canvas(reference, surface, images, found):
    """Prove a direct Foot-to-canvas mapping; refuse atlases or posed mismatches.

    Size/material identity alone cannot prove an editable UV address. Require
    each cap triangle's positions, UVs and named skin weights to agree, and
    reject other canvas surfaces sharing any target pixel.
    """
    if reference.get('model_token') != surface.get('model_token') or not found['separable']:
        raise ValueError('Foot/canvas model identity mismatch')
    foot = next(m for m in reference['meshes'] if m['name'] == 'Foot')
    nodes = {n['id']: n['name'] for n in reference['nodes']}
    foot_bones = [nodes[i] for i in foot['bone_nodes']]
    positions = [point(foot['world_matrix'], p) for p in foot['positions']]

    def bone_name(row):
        if row.get('name'):
            return row['name']
        fields = row.get('fields', [])
        values = [f['value'] for f in fields if f['name'] == '<Value>k__BackingField']
        if row.get('native_type') == 'VRoidCore.Common.Types.ResolvedBoneId' and values == [row.get('identity')]:
            return values[0]
        raise ValueError('Unverified canvas bone identity')

    def vertex(mesh, bones, points, index):
        weight = mesh['weights'][index]
        skin = tuple(sorted((bones[b], round(w, 6)) for b, w in zip(weight['indices'], weight['weights']) if w > 1e-6))
        values = [*points[index], *mesh['uv0'][index]]
        if len(values) != 5 or any(not math.isfinite(v) for v in values):
            raise ValueError('Invalid canvas vertex')
        return tuple(round(v, 6) for v in values), skin

    def signature(mesh, bones, points, tri):
        return tuple(sorted(vertex(mesh, bones, points, i) for i in tri))

    wanted = Counter(signature(foot, foot_bones, positions, tri)
                     for nail in found['nails'] for island in nail['islands'] for tri in island['triangles'])
    width, height = found['texture']['width'], found['texture']['height']
    masks = raster_nails({'texture': found['texture'], 'nails': found['nails']})
    target_pixels = set().union(*masks.values())
    cap_indices = Counter(tuple(sorted(tri)) for nail in found['nails']
                          for island in nail['islands'] for tri in island['triangles'])
    source_other = []
    for start in range(0, len(foot['triangles']), 3):
        tri = foot['triangles'][start:start + 3]
        key = tuple(sorted(tri))
        if cap_indices[key] > 0:
            cap_indices[key] -= 1
        else:
            source_other.append([foot['uv0'][i] for i in tri])
    matches = []
    work = 0
    for image in images:
        meshes = [m for m in surface.get('meshes', []) if m.get('image') == image]
        remaining = wanted.copy()
        other_triangles = source_other[:]
        try:
            for mesh in meshes:
                bones = [bone_name(b) for b in mesh['bone_ids']]
                indices = [i for submesh in mesh['submeshes'] for i in submesh['triangles']]
                if len(indices) % 3:
                    raise ValueError('Invalid canvas triangle stream')
                for start in range(0, len(indices), 3):
                    tri = indices[start:start + 3]
                    key = signature(mesh, bones, mesh['positions'], tri)
                    if remaining[key] > 0:
                        remaining[key] -= 1
                    else:
                        other_triangles.append([mesh['uv0'][i] for i in tri])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if any(remaining.values()):
            continue
        shared = False
        for tri in other_triangles:
            tex = [(u * width, (1 - v) * height) for u, v in tri]
            x0, x1 = max(0, math.floor(min(p[0] for p in tex))), min(width, math.ceil(max(p[0] for p in tex)))
            y0, y1 = max(0, math.floor(min(p[1] for p in tex))), min(height, math.ceil(max(p[1] for p in tex)))
            work += max(0, x1 - x0) * max(0, y1 - y0)
            if work > MAX_WORK:
                raise ValueError('Foot/canvas correspondence exceeds the bounded work limit')
            if any(y * width + x in target_pixels and _barycentric(*tex, x + .5, y + .5) is not None
                   for y in range(y0, y1) for x in range(x0, x1)):
                shared = True
                break
        if not shared:
            matches.append(image)
    if len(matches) != 1:
        raise ValueError('Foot UV correspondence requires one exact canvas image with unshared cap pixels; matching texture size is insufficient')
    return matches[0]
