"""Exact garment-vs-body penetration measurement for paused native pose references.

Reads one or more ``reference.json`` captures produced by the native wear tools
(``capture_wear_reference`` style exports: posed BakeMesh for body and garment)
and measures, without Blender or the native client:

* per garment vertex: exact distance to the body surface and a generalized
  winding number against the body triangle set (inside / outside / uncertain),
* triangle-triangle intersections between the garment surface and the body
  surface (faces that genuinely cross the body, not just near-normal samples),
* per spring-chain weight mass of the penetrating vertices.

This closes the evidence gap recorded in docs/后裙v03与VRM_Godot验收_2026-10-17.md
("nearest-normal screening is not exact cloth collision proof").  It is a
measurement tool only: it never edits garments, textures or the native client.

Requires numpy.  Usage:

    python tools/measure_exact_contact.py --self-test
    python tools/measure_exact_contact.py --reference REF.json [...] --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# geometry kernels (numpy, deterministic)
# ---------------------------------------------------------------------------


def pair_point_triangle_distance(points: np.ndarray, tris: np.ndarray):
    """Distance from points[i] to triangle tris[i] for N pairs.

    points: (N,3), tris: (N,3,3).  Returns (dist (N,), closest (N,3)).
    """
    a = tris[:, 0]
    b = tris[:, 1]
    c = tris[:, 2]
    ab = b - a
    ac = c - a
    ap = points - a
    d1 = np.einsum("ij,ij->i", ap, ab)
    d2 = np.einsum("ij,ij->i", ap, ac)
    bp = points - b
    d3 = np.einsum("ij,ij->i", bp, ab)
    d4 = np.einsum("ij,ij->i", bp, ac)
    cp = points - c
    d5 = np.einsum("ij,ij->i", cp, ab)
    d6 = np.einsum("ij,ij->i", cp, ac)

    closest = np.empty_like(points)
    done = np.zeros(len(points), dtype=bool)

    # region A (vertex a)
    m = (d1 <= 0.0) & (d2 <= 0.0)
    closest[m] = a[m]
    done |= m
    # region B (vertex b)
    m = (~done) & (d3 >= 0.0) & (d4 <= d3)
    closest[m] = b[m]
    done |= m
    # region C (vertex c)
    m = (~done) & (d6 >= 0.0) & (d5 <= d6)
    closest[m] = c[m]
    done |= m
    # edge AB
    vc = d1 * d4 - d3 * d2
    m = (~done) & (vc <= 0.0) & (d1 >= 0.0) & (d3 <= 0.0)
    if np.any(m):
        v = (d1[m] / (d1[m] - d3[m]))[:, None]
        closest[m] = a[m] + v * ab[m]
    done |= m
    # edge AC
    vb = d5 * d2 - d1 * d6
    m = (~done) & (vb <= 0.0) & (d2 >= 0.0) & (d6 <= 0.0)
    if np.any(m):
        w = (d2[m] / (d2[m] - d6[m]))[:, None]
        closest[m] = a[m] + w * ac[m]
    done |= m
    # edge BC
    va = d3 * d6 - d5 * d4
    m = (~done) & (va <= 0.0) & ((d4 - d3) >= 0.0) & ((d5 - d6) >= 0.0)
    if np.any(m):
        w = ((d4[m] - d3[m]) / ((d4[m] - d3[m]) + (d5[m] - d6[m])))[:, None]
        closest[m] = b[m] + w * (c[m] - b[m])
    done |= m
    # interior
    m = ~done
    if np.any(m):
        denom = 1.0 / (va[m] + vb[m] + vc[m])
        v = (vb[m] * denom)[:, None]
        w = (vc[m] * denom)[:, None]
        closest[m] = a[m] + v * ab[m] + w * ac[m]
    dist = np.linalg.norm(points - closest, axis=1)
    return dist, closest


def point_triangle_distance(points: np.ndarray, tri: np.ndarray):
    """Distance from points (N,3) to a single triangle tri (3,3)."""
    return pair_point_triangle_distance(points, np.repeat(tri[None, :, :], len(points), axis=0))


def winding_number(points: np.ndarray, tris: np.ndarray, chunk: int = 256) -> np.ndarray:
    """Generalized winding number of each point w.r.t. a closed triangle mesh.

    Solid-angle summation; ~O(len(points) * len(tris)).
    """
    out = np.zeros(len(points), dtype=np.float64)
    v0 = tris[:, 0][None, :, :]
    v1 = tris[:, 1][None, :, :]
    v2 = tris[:, 2][None, :, :]
    for start in range(0, len(points), chunk):
        p = points[start:start + chunk][:, None, :]
        a = v0 - p
        b = v1 - p
        c = v2 - p
        la = np.linalg.norm(a, axis=2)
        lb = np.linalg.norm(b, axis=2)
        lc = np.linalg.norm(c, axis=2)
        num = np.einsum("ijk,ijk->ij", a, np.cross(b, c))
        den = (
            la * lb * lc
            + np.einsum("ijk,ijk->ij", a, b) * lc
            + np.einsum("ijk,ijk->ij", b, c) * la
            + np.einsum("ijk,ijk->ij", c, a) * lb
        )
        out[start:start + chunk] = np.arctan2(num, den).sum(axis=1) / (2.0 * math.pi)
    return out


def tri_tri_intersect(t1: np.ndarray, t2: np.ndarray) -> bool:
    """Plane-section intervals, with a real 2D overlap test when coplanar.

    Touching counts as contact. Degenerate faces are rejected explicitly rather
    than reporting every zero-area pair as intersecting.
    """
    def plane(tri):
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        return n, -float(n @ tri[0])

    n1, d1 = plane(t1)
    if np.linalg.norm(n1) < 1e-18:
        raise ValueError('Degenerate first triangle in intersection test')
    dv2 = t2 @ n1 + d1
    scale = float(np.linalg.norm(n1)) * 1e-9
    if np.all(dv2 > scale) or np.all(dv2 < -scale):
        return False
    n2, d2 = plane(t2)
    if np.linalg.norm(n2) < 1e-18:
        raise ValueError('Degenerate second triangle in intersection test')
    dv1 = t1 @ n2 + d2
    scale2 = float(np.linalg.norm(n2)) * 1e-9
    if np.all(dv1 > scale2) or np.all(dv1 < -scale2):
        return False
    if np.all(np.abs(dv2) <= scale) and np.all(np.abs(dv1) <= scale2):
        keep = [i for i in range(3) if i != int(np.argmax(np.abs(n1)))]
        a, b = t1[:, keep], t2[:, keep]
        for tri in (a, b):
            for i in range(3):
                edge = tri[(i+1) % 3] - tri[i]
                axis = np.array([-edge[1], edge[0]])
                length = np.linalg.norm(axis)
                if length == 0:
                    continue
                pa, pb = a @ (axis/length), b @ (axis/length)
                if pa.max() < pb.min()-1e-9 or pb.max() < pa.min()-1e-9:
                    return False
        return True
    direction = np.cross(n1, n2)
    axis = int(np.argmax(np.abs(direction)))

    def interval(tri, dv, tolerance):
        pts = tri[:, axis]
        # Only points ON the other plane belong to the section interval.
        # An off-plane vertex on its own side is not an interval endpoint.
        section = [pts[i] for i in range(3) if abs(dv[i]) <= tolerance]
        for i in range(3):
            j = (i+1) % 3
            if (dv[i] > tolerance and dv[j] < -tolerance) or (dv[j] > tolerance and dv[i] < -tolerance):
                section.append(pts[i] + (pts[j]-pts[i])*dv[i]/(dv[i]-dv[j]))
        assert section, 'Plane-section interval missing'
        return min(section), max(section)

    lo1, hi1 = interval(t1, dv1, scale2)
    lo2, hi2 = interval(t2, dv2, scale)
    eps = 1e-12
    return not (hi1 < lo2 - eps or hi2 < lo1 - eps)


# ---------------------------------------------------------------------------
# reference loading and analysis
# ---------------------------------------------------------------------------


def load_reference(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf8"))
    body = data.get("body") or {}
    garments = data.get("garments") or []
    if not body.get("triangles") or not garments:
        raise ValueError(f"{path}: missing posed body/garment mesh data")
    bones = [b.get("name", "") for b in data.get("bones", [])]
    return {"path": path, "data": data, "body": body, "garments": garments, "bone_names": bones}


def vertex_weight_map(garment: dict, bone_names: list, index: int) -> dict:
    entry = garment["weights"][index]
    out = {}
    for slot, weight in zip(entry.get("indices", []), entry.get("weights", [])):
        name = bone_names[slot] if 0 <= slot < len(bone_names) else f"#{slot}"
        out[name] = out.get(name, 0.0) + float(weight)
    return out


class TriangleGrid:
    """Uniform grid over triangle AABBs for cheap near-vertex queries."""

    def __init__(self, tris: np.ndarray, cell: float):
        self.tris = tris
        self.cell = cell
        self.min = tris.reshape(-1, 3).min(axis=0) - cell
        self.max = tris.reshape(-1, 3).max(axis=0) + cell
        dims = np.maximum(np.ceil((self.max - self.min) / cell).astype(int), 1)
        self.dims = dims
        self.cells = {}
        lo = tris.min(axis=1)
        hi = tris.max(axis=1)
        i0 = np.floor((lo - self.min) / cell).astype(int)
        i1 = np.floor((hi - self.min) / cell).astype(int)
        for t in range(len(tris)):
            for x in range(i0[t, 0], i1[t, 0] + 1):
                for y in range(i0[t, 1], i1[t, 1] + 1):
                    for z in range(i0[t, 2], i1[t, 2] + 1):
                        self.cells.setdefault((x, y, z), []).append(t)

    def candidates(self, point: np.ndarray, radius: float):
        i0 = np.floor((point - radius - self.min) / self.cell).astype(int)
        i1 = np.floor((point + radius - self.min) / self.cell).astype(int)
        found = []
        for x in range(i0[0], i1[0] + 1):
            for y in range(i0[1], i1[1] + 1):
                for z in range(i0[2], i1[2] + 1):
                    found.extend(self.cells.get((x, y, z), ()))
        return found

    def candidates_aabb(self, lo: np.ndarray, hi: np.ndarray):
        """Visit every grid cell overlapped by the box, including both ends."""
        i0 = np.floor((lo-self.min) / self.cell).astype(int)
        i1 = np.floor((hi-self.min) / self.cell).astype(int)
        found = set()
        for x in range(i0[0], i1[0]+1):
            for y in range(i0[1], i1[1]+1):
                for z in range(i0[2], i1[2]+1):
                    found.update(self.cells.get((x,y,z), ()))
        return found


def analyse(reference: dict, region: str, distance_limit: float, report_limit: int,
            do_tri_tri: bool, winding_chunk: int, log) -> dict:
    t0 = time.time()
    body = reference["body"]
    body_tris = np.asarray(body["triangles"], dtype=np.int64).reshape(-1, 3)
    body_pos = np.asarray(body["positions"], dtype=np.float64)
    bones = reference["bone_names"]
    result = {
        "reference": str(reference["path"]),
        "pose_source": reference["data"].get("pose_source"),
        "frame": reference["data"].get("frame"),
        "garments": [],
    }
    for gi, garment in enumerate(reference["garments"]):
        g_pos = np.asarray(garment["positions"], dtype=np.float64)
        g_src = np.asarray(garment.get("source_positions", garment["positions"]), dtype=np.float64)
        g_tris = np.asarray(garment["triangles"], dtype=np.int64).reshape(-1, 3)
        n_vert = len(g_pos)

        region_mask = np.ones(n_vert, dtype=bool)
        region_name = "all"
        if region in ("rear", "front"):
            rings = set(range(4,10)) if region == 'rear' else {0,1,2,10,11}
            region_name = "rear skirt chains WM_Skirt_04..09" if region == 'rear' else "front skirt chains WM_Skirt_00,01,02,10,11"
            keep = np.zeros(n_vert, dtype=bool)
            for i in range(n_vert):
                for name in vertex_weight_map(garment, bones, i):
                    if name.startswith("WM_Skirt_"):
                        ring = name[len("WM_Skirt_"):].split("_", 1)[0]
                        if ring.isdigit() and int(ring) in rings:
                            keep[i] = True
                            break
            region_mask = keep
        region_index = np.nonzero(region_mask)[0]

        body_tri_pos = body_pos[body_tris]
        grid = TriangleGrid(body_tri_pos, cell=0.1)
        distances = np.full(n_vert, np.inf)
        closest = np.zeros((n_vert, 3))
        pair_points = []
        pair_tris = []
        pair_index = []
        pair_budget = 2_000_000

        def flush_pairs():
            if not pair_points:
                return
            all_points = np.concatenate(pair_points)
            all_tris = np.concatenate(pair_tris)
            all_index = np.concatenate(pair_index)
            pair_dist, pair_closest = pair_point_triangle_distance(all_points, all_tris)
            order = np.lexsort((pair_dist, all_index))
            sorted_index = all_index[order]
            sorted_dist = pair_dist[order]
            first = np.zeros(len(sorted_index), dtype=bool)
            first[0] = True
            first[1:] = sorted_index[1:] != sorted_index[:-1]
            pick = order[first]
            vi_pick = sorted_index[first]
            improved = sorted_dist[first] < distances[vi_pick]
            distances[vi_pick[improved]] = sorted_dist[first][improved]
            closest[vi_pick[improved]] = pair_closest[pick][improved]
            pair_points.clear()
            pair_tris.clear()
            pair_index.clear()

        pending = 0
        for vi in region_index:
            cand = grid.candidates(g_pos[vi], distance_limit + 0.1)
            if not cand:
                continue
            cand = np.asarray(sorted(set(cand)), dtype=np.int64)
            pair_points.append(np.repeat(g_pos[vi][None, :], len(cand), axis=0))
            pair_tris.append(body_tri_pos[cand])
            pair_index.append(np.full(len(cand), vi, dtype=np.int64))
            pending += len(cand)
            if pending >= pair_budget:
                flush_pairs()
                pending = 0
        flush_pairs()
        if len(region_index):
            log(f"    distance done ({time.time() - t0:.0f}s)")

        near_mask = region_mask & (distances < distance_limit)
        near_index = np.nonzero(near_mask)[0]
        windings = np.full(n_vert, np.nan)
        if len(near_index):
            log(f"    winding number for {len(near_index)} near vertices vs {len(body_tris)} body triangles")
            windings[near_index] = winding_number(g_pos[near_index], body_tri_pos, chunk=winding_chunk)

        inside, uncertain, outside = [], [], []
        for vi in near_index:
            w = float(windings[vi])
            record = {
                "vertex": int(vi),
                "source_vertex_nearest": g_src[vi].round(6).tolist(),
                "position": g_pos[vi].round(6).tolist(),
                "nearest_body_point": closest[vi].round(6).tolist(),
                "depth_m": float(distances[vi]),
                "winding": round(w, 6),
                "weights": {k: round(v, 6) for k, v in sorted(
                    vertex_weight_map(garment, bones, vi).items(), key=lambda kv: -kv[1])},
            }
            if w > 0.55:
                inside.append(record)
            elif w < 0.45:
                outside.append(record)
            else:
                uncertain.append(record)
        inside.sort(key=lambda r: -r["depth_m"])
        uncertain.sort(key=lambda r: -r["depth_m"])

        chain_mass = {}
        for record in inside:
            for name, weight in record["weights"].items():
                chain = name.rsplit("_", 1)[0] if name.startswith("WM_Skirt_") else name
                chain_mass[chain] = chain_mass.get(chain, 0.0) + weight

        tri_tri = {"performed": do_tri_tri, "checked_pairs": 0, "intersections": 0,
                   "garment_faces": [], "sample": []}
        if do_tri_tri:
            log("    triangle-triangle intersection pass")
            body_grid = TriangleGrid(body_tri_pos, cell=0.1)
            face_hits = set()
            checked = 0
            body_valid = np.linalg.norm(np.cross(body_tri_pos[:,1]-body_tri_pos[:,0],
                                                 body_tri_pos[:,2]-body_tri_pos[:,0]), axis=1) >= 1e-18
            skipped_garment = []
            for fi, tri in enumerate(g_tris):
                verts = g_pos[tri]
                if not np.any(region_mask[tri]):
                    continue
                if np.linalg.norm(np.cross(verts[1]-verts[0], verts[2]-verts[0])) < 1e-18:
                    skipped_garment.append(fi)
                    continue
                lo = verts.min(axis=0)
                hi = verts.max(axis=0)
                cand = body_grid.candidates_aabb(lo, hi)
                for bt in cand:
                    if not body_valid[bt]:
                        continue
                    btri = body_pos[body_tris[bt]]
                    if np.any(verts.min(axis=0) > btri.max(axis=0)) or np.any(verts.max(axis=0) < btri.min(axis=0)):
                        continue
                    checked += 1
                    if tri_tri_intersect(verts, btri):
                        face_hits.add(int(fi))
                        if len(tri_tri["sample"]) < report_limit:
                            tri_tri["sample"].append({"garment_face": int(fi),
                                                      "body_face": int(bt),
                                                      "garment_vertices": tri.tolist()})
                if (fi + 1) % 2000 == 0:
                    log(f"    tri-tri {fi + 1}/{len(g_tris)} garment faces ({time.time() - t0:.0f}s)")
            tri_tri["checked_pairs"] = checked
            tri_tri["intersections"] = len(face_hits)
            tri_tri["garment_faces"] = sorted(face_hits)[:report_limit]
            tri_tri["degenerate_body_faces_excluded"] = int((~body_valid).sum())
            tri_tri["degenerate_region_garment_faces_excluded"] = skipped_garment

        result["garments"].append({
            "name": garment.get("name"),
            "region": region_name,
            "region_vertices": int(len(region_index)),
            "vertices_total": int(n_vert),
            "near_vertices": int(len(near_index)),
            "inside_count": len(inside),
            "uncertain_count": len(uncertain),
            "outside_near_count": len(outside),
            "max_depth_m": round(max([r["depth_m"] for r in inside], default=0.0), 6),
            "sum_depth_m": round(sum(r["depth_m"] for r in inside), 6),
            "chain_weight_mass_inside": {k: round(v, 4) for k, v in sorted(
                chain_mass.items(), key=lambda kv: -kv[1])},
            "worst_inside_vertices": inside[:report_limit],
            "uncertain_vertices": uncertain[:report_limit],
            "tri_tri": tri_tri,
        })
    result["seconds"] = round(time.time() - t0, 1)
    return result


# ---------------------------------------------------------------------------
# self test
# ---------------------------------------------------------------------------


def self_test() -> int:
    failures = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + ((" :: " + detail) if detail else ""))
        if not ok:
            failures.append(name)

    # unit sphere as body (icosphere-like via recursive subdivision of a cube)
    def unit_sphere(subdiv=3):
        verts = []
        tris = []

        def norm(v):
            n = np.linalg.norm(v)
            return v / n

        corners = [np.array(v, dtype=float) for v in (
            (-1, -1, -1), (-1, -1, 1), (-1, 1, -1), (-1, 1, 1),
            (1, -1, -1), (1, -1, 1), (1, 1, -1), (1, 1, 1))]
        faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5),
                 (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6),
                 (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]

        def midpoint(a, b, cache):
            key = (min(a, b), max(a, b))
            if key in cache:
                return cache[key]
            verts.append(norm(0.5 * (verts[a] + verts[b])))
            cache[key] = len(verts) - 1
            return cache[key]

        for c in corners:
            verts.append(norm(c))
        for _ in range(subdiv):
            cache = {}
            new_tris = []
            for a, b, c in faces:
                ab = midpoint(a, b, cache)
                bc = midpoint(b, c, cache)
                ca = midpoint(c, a, cache)
                new_tris += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
            faces = new_tris
        return np.array(verts), np.array(faces)

    verts, tris = unit_sphere()
    # winding: inside -> ~1, outside -> ~0
    probes = np.array([[0, 0, 0], [0.5, 0, 0], [0, 0, 1.5], [2, 2, 2], [0, 0, -0.99]], dtype=float)
    w = winding_number(probes, verts[tris])
    check("winding inside>0.9", bool(w[0] > 0.9 and w[1] > 0.9 and w[4] > 0.9), str(w))
    check("winding outside<0.1", bool(w[2] < 0.1 and w[3] < 0.1), str(w))

    # distance to sphere surface
    d, _ = point_triangle_distance(np.array([[0, 0, 0.0]]), verts[tris][0])
    pts = np.array([[0, 0, 0], [0, 0, 1.5], [1.0, 0, 0]], dtype=float)
    best = []
    for p in pts:
        ds = []
        for t in verts[tris]:
            dd, _ = point_triangle_distance(p[None, :], t)
            ds.append(float(dd[0]))
        best.append(min(ds))
    check("distance centre~1", abs(best[0] - 1.0) < 0.05, str(best))
    check("distance outside 0.5", abs(best[1] - 0.5) < 0.05, str(best))
    check("distance surface ~0", best[2] < 0.05, str(best))

    # triangle-triangle
    big = np.array([[-1, -1, 0], [1, -1, 0], [0, 1, 0]], dtype=float)
    crossing = np.array([[0, 0, -1], [0, 0, 1], [0.5, 0.2, 1]], dtype=float)
    separate = np.array([[0, 0, 5], [0, 0, 6], [0.5, 0.2, 6]], dtype=float)
    check("tri-tri crossing", tri_tri_intersect(big, crossing))
    check("tri-tri separate", not tri_tri_intersect(big, separate))
    a = np.array([[0,0,0], [2,0,0], [0,2,0]], dtype=float)
    b = np.array([[2,2,0], [2,1.1,0], [1.1,2,0]], dtype=float)
    check("coplanar disjoint with overlapping AABBs", not tri_tri_intersect(a, b))
    check("coplanar contained", tri_tri_intersect(a, a*.2+.1*np.array([1,1,0])))
    check("coplanar edge touch", tri_tri_intersect(a, np.array([[2,0,0],[3,0,0],[2,1,0]], dtype=float)))
    grid = TriangleGrid(np.array([[[0,0,0],[.01,0,0],[0,.01,0]],
                                  [[.101,0,0],[.102,0,0],[.101,.01,0]]]), .1)
    check("AABB includes cell beyond narrow boundary", 1 in grid.candidates_aabb(
        np.array([.099,0,0]), np.array([.101,.01,0])))
    # Plane sections [0,2] and [2.5,3] are disjoint, although the off-plane
    # solo vertex at x=10 would falsely enlarge the old interval to [0,10].
    section_a = np.array([[10,0,1], [-10,0,-1], [-6,0,-1]], dtype=float)
    section_b = np.array([[2.5,-1,0], [3,-1,0], [2.5,1,0]], dtype=float)
    check("off-plane vertex excluded from interval", not tri_tri_intersect(section_a, section_b))
    check("shared vertex contact", tri_tri_intersect(big, np.array([[0,1,0],[0,2,1],[1,2,1]], dtype=float)))
    for factor in (1., .001):
        offset = np.array([2., -4., 3.])
        check("coplanar disjoint translated/scaled %s" % factor,
              not tri_tri_intersect(a*factor+offset, b*factor+offset))
    try:
        tri_tri_intersect(np.zeros((3,3)), big)
    except ValueError:
        check("degenerate face rejected", True)
    else:
        check("degenerate face rejected", False)

    print("SELF-TEST", "OK" if not failures else "FAILED: " + ", ".join(failures))
    return 1 if failures else 0


# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--reference", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--region", choices=["all", "rear", "front"], default="rear")
    ap.add_argument("--distance-limit", type=float, default=0.15)
    ap.add_argument("--report-limit", type=int, default=200)
    ap.add_argument("--winding-chunk", type=int, default=256)
    ap.add_argument("--no-tri-tri", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.reference or not args.out:
        ap.error("--reference and --out are required unless --self-test")

    def log(message):
        print(message, flush=True)

    runs = []
    for path in args.reference:
        log(f"[measure_exact_contact] {path}")
        ref = load_reference(path)
        runs.append(analyse(ref, args.region, args.distance_limit, args.report_limit,
                            not args.no_tri_tri, args.winding_chunk, log))
    payload = {
        "tool": "measure_exact_contact",
        "version": 2,
        "method": {
            "inside_test": "generalized winding number over the full posed body triangle set",
            "depth": "exact point-triangle distance to the posed body surface",
            "crossing": "Plane-section intervals with coplanar 2D separating axes, AABB prefilter; degenerate faces rejected",
            "region": args.region,
            "distance_limit_m": args.distance_limit,
        },
        "scope": "Static posed BakeMesh measurement; not a solver or full-motion certification",
        "runs": runs,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf8")
    for run in runs:
        for garment in run["garments"]:
            log("  %s | inside=%d uncertain=%d max_depth=%.4f tri_tri=%d (%.1fs)" % (
                Path(run["reference"]).parent.name, garment["inside_count"], garment["uncertain_count"],
                garment["max_depth_m"], garment["tri_tri"]["intersections"], run["seconds"]))
    log(f"[measure_exact_contact] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
