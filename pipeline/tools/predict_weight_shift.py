"""Predict the exact-contact effect of localized skin-weight shifts, offline.

Loads a paused pose ``reference.json`` (posed BakeMesh + bones + bindposes),
recomputes the posed garment with modified vertex weights and writes a new
reference-format JSON that ``tools/measure_exact_contact.py`` can measure.

The skinning reconstruction is validated against the captured posed positions
before any modification (the same check the native skinning diagnosis used).

Weight-shift rules are declarative:

* ``--shift-hips-to-spring FRACTION``: for every vertex carrying J_Bip_C_Hips
  weight, move FRACTION of that weight onto its co-weighted spring bones
  proportionally (leaves vertices without spring weights untouched).
* ``--vertex N --from BONE --to BONE --amount F``: single explicit move.

Requires numpy.  Usage:

    python tools/predict_weight_shift.py --reference REF.json \
        --shift-hips-to-spring 0.75 --out PREDICTED.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


def mat4(rows) -> np.ndarray:
    return np.asarray(rows, dtype=np.float64)


def skin_matrices(reference, garment) -> list:
    """(N,4,4) skin matrix per bone slot used by this garment."""
    bindposes = [mat4(b) for b in garment["bindposes"]]
    bones = reference["bones"]
    matrices = []
    for slot in garment["bone_ids"]:
        world = mat4(bones[slot]["world_matrix"])
        matrices.append(world @ bindposes[slot])
    return matrices


def reconstruct(garment, matrices, bone_names, weights_override=None):
    positions = np.asarray(garment["source_positions"], dtype=np.float64)
    out = np.zeros_like(positions)
    for index in range(len(positions)):
        entry = (weights_override or garment["weights"])[index]
        point = np.append(positions[index], 1.0)
        acc = np.zeros(3)
        for slot, weight in zip(entry["indices"], entry["weights"]):
            if weight <= 0.0:
                continue
            acc += weight * (matrices[slot] @ point)[:3]
        out[index] = acc
    return out


def shift_hips_to_spring(garment, bone_names, fraction, restrict_dominant=None,
                         target_joint_offset=0, vertex_allow=None):
    """Return per-vertex weight dicts with hips weight moved onto spring bones."""
    overrides = []
    moved = 0
    for index, entry in enumerate(garment["weights"]):
        merged = defaultdict(float)
        for slot, weight in zip(entry["indices"], entry["weights"]):
            merged[bone_names[slot]] += float(weight)
        hips = merged.get("J_Bip_C_Hips", 0.0)
        springs = {n: w for n, w in merged.items() if n.startswith("WM_Skirt_") and w > 0.0}
        dominant = max(merged.items(), key=lambda kv: kv[1])[0]
        eligible = hips > 0.0 and bool(springs)
        if vertex_allow is not None and index not in vertex_allow:
            eligible = False
        if restrict_dominant is not None and dominant != restrict_dominant:
            eligible = False
        if eligible:
            moved += 1
            spring_total = sum(springs.values())
            merged["J_Bip_C_Hips"] = hips * (1.0 - fraction)
            add = hips * fraction
            for name, weight in springs.items():
                merged[name] = weight + add * (weight / spring_total)
            if target_joint_offset:
                shifted = defaultdict(float)
                spring_names = set(springs)
                for name, weight in merged.items():
                    if name in spring_names and weight > 0.0:
                        chain, joint = name.rsplit("_", 1)
                        target = min(int(joint) + target_joint_offset, 4)
                        shifted["%s_%02d" % (chain, target)] += weight
                    else:
                        shifted[name] += weight
                merged = shifted
        final = {n: w for n, w in merged.items() if w > 1e-7}
        names = sorted(final)
        overrides.append({"indices": [bone_names.index(n) for n in names],
                          "weights": [final[n] for n in names]})
    return overrides, moved


def load_inside_records(exact_path, wanted_reference):
    """Inside-vertex records of one reference from an exact-contact run."""
    exact = json.loads(exact_path.read_text(encoding="utf8"))
    records = []
    wanted = str(Path(wanted_reference).resolve()).lower()
    for run in exact["runs"]:
        if str(Path(run["reference"]).resolve()).lower() != wanted:
            continue
        for garment in run["garments"]:
            for vertex in garment["worst_inside_vertices"]:
                records.append(vertex)
    return records


def nudge_source_vertices(garment, matrices, bone_names, records, margin_m):
    """Move source vertices outward along the posed outward direction.

    Posed direction (nearest body point -> posed position points inward) is
    mapped back to source space through the inverse skin matrix of the
    dominant bone.  Returns (moved_count, max_source_move_m).
    """
    source = np.asarray(garment["source_positions"], dtype=np.float64).copy()
    moved = 0
    max_move = 0.0
    manifest = []
    for record in records:
        index = record["vertex"]
        if index >= len(source):
            continue
        original = source[index].copy()
        posed_outward = np.asarray(record["nearest_body_point"], dtype=float) - \
            np.asarray(record["position"], dtype=float)
        norm = float(np.linalg.norm(posed_outward))
        if norm < 1e-12:
            continue
        posed_outward /= norm
        delta = posed_outward * (float(record["depth_m"]) + margin_m)
        weights = record["weights"]
        dominant = max(weights.items(), key=lambda kv: kv[1])[0]
        try:
            slot = bone_names.index(dominant)
        except ValueError:
            continue
        inverse = np.linalg.inv(matrices[slot])
        source_delta = (inverse @ np.append(delta, 0.0))[:3]
        source[index] += source_delta
        moved += 1
        move = float(np.linalg.norm(source_delta))
        max_move = max(max_move, move)
        manifest.append({
            "vertex": index,
            "source_position": original.tolist(),
            "new_source_position": source[index].tolist(),
            "source_move_mm": move * 1000,
            "depth_m": record["depth_m"],
            "dominant_bone": dominant,
        })
    garment["source_positions"] = source.tolist()
    return moved, max_move, manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shift-hips-to-spring", type=float, default=0.0)
    ap.add_argument("--restrict-dominant", default=None)
    ap.add_argument("--target-joint-offset", type=int, default=0)
    ap.add_argument("--nudge-margin-mm", type=float, default=0.0,
                    help="push inside vertices from --vertices-from-exact outward by depth+margin")
    ap.add_argument("--apply-modified-from", type=Path, default=None,
                    help="previous prediction output; reuse its source positions and weights as-is")
    ap.add_argument("--vertices-from-exact", type=Path, default=None,
                    help="exact-contact JSON; only its inside vertices for this reference are shifted")
    ap.add_argument("--report-limit", type=int, default=200)
    args = ap.parse_args(argv)

    reference = json.loads(args.reference.read_text(encoding="utf8"))
    bone_names = [b.get("name", "") for b in reference["bones"]]
    report = {"tool": "predict_weight_shift", "reference": str(args.reference), "garments": []}
    modified_source = None
    if args.apply_modified_from:
        modified_source = json.loads(args.apply_modified_from.read_text(encoding="utf8"))["garments"]

    allow = None
    inside_records = []
    if args.vertices_from_exact:
        inside_records = load_inside_records(args.vertices_from_exact, args.reference)
        allow = set(record["vertex"] for record in inside_records)
        print("restricted to %d inside vertices from %s" % (len(allow), args.vertices_from_exact))

    for garment_index, garment in enumerate(reference["garments"]):
        matrices = skin_matrices(reference, garment)
        captured = np.asarray(garment["positions"], dtype=np.float64)
        if modified_source is not None:
            source_entry = modified_source[garment_index]
            if len(source_entry["source_positions"]) != len(garment["source_positions"]):
                raise ValueError("garment %d vertex count differs from modified source" % garment_index)
            garment["source_positions"] = source_entry["source_positions"]
            garment["weights"] = source_entry["weights"]
            base = captured
            error = float("nan")
        else:
            base = reconstruct(garment, matrices, bone_names)
            error = float(np.linalg.norm(base - captured, axis=1).max())
        moved = 0
        overrides = None
        nudge_moved = 0
        nudge_max = 0.0
        if modified_source is None and args.nudge_margin_mm > 0.0 and inside_records:
            nudge_moved, nudge_max, nudge_manifest = nudge_source_vertices(
                garment, matrices, bone_names, inside_records, args.nudge_margin_mm / 1000.0)
            report.setdefault("nudges", []).extend(nudge_manifest)
        if modified_source is None and args.shift_hips_to_spring > 0.0:
            overrides, moved = shift_hips_to_spring(
                garment, bone_names, args.shift_hips_to_spring,
                restrict_dominant=args.restrict_dominant,
                target_joint_offset=args.target_joint_offset,
                vertex_allow=allow)
        predicted = reconstruct(garment, matrices, bone_names, overrides)
        garment["positions"] = predicted.tolist()
        if overrides:
            garment["weights"] = overrides
        delta = np.linalg.norm(predicted - base, axis=1)
        report["garments"].append({
            "name": garment.get("name"),
            "skin_reconstruction_error_m": error,
            "vertices": len(captured),
            "modified_vertices": moved,
            "nudged_vertices": nudge_moved,
            "nudge_max_source_move_mm": nudge_max * 1000,
            "prediction_max_move_mm": float(delta.max() * 1000),
            "prediction_mean_move_mm": float(delta.mean() * 1000),
        })
        print("%s: reconstruction_error=%.3e weight_moved=%d nudged=%d max_move=%.2fmm" % (
            garment.get("name"), error, moved, nudge_moved, delta.max() * 1000))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reference, ensure_ascii=False), encoding="utf8")
    args.out.with_suffix(".report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print("wrote", args.out)
    ok = all((err := g["skin_reconstruction_error_m"]) != err or err < 1e-4
             for g in report["garments"])
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
