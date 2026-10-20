"""Compare verified regional capture manifests and write a portable image report.

Rejects mismatched camera readbacks or GPU settings before comparing pixels.
Thresholds measure unexpected image changes, not artistic quality. Baselines
are caller-selected candidates; this command never approves or replaces one.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vroid_mcp.bounded_paint import decode_rgba_png
from vroid_mcp.capture_views import REGIONAL_VIEWS
from vroid_mcp.texture_mapping import png_rgba

QUALITY_KEYS = ('quality', 'output_size', 'render_size', 'msaa_samples')
CAMERA_KEYS = ('position', 'target', 'fov_degrees', 'forward', 'right_vector', 'yaw_degrees')


def close(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= 1e-5
    return a == b


def load_capture(path):
    path = Path(path)
    manifest = json.loads(path.read_text(encoding='utf8'))
    records = manifest['images']
    kind = 'wear' if manifest.get('schema') == 'vroid-wear-review-v1' else 'model'
    records = {r['view']: r for r in records} if isinstance(records, list) else records
    if not isinstance(records, dict) or not 1 <= len(records) <= 6:
        raise ValueError('Expected 1-6 captured regional views')
    loaded = {}
    for view, record in records.items():
        if view not in REGIONAL_VIEWS:
            raise ValueError('Only regional views with camera readbacks are comparable')
        # Adjacent images make a copied capture folder portable; recorded
        # machine-specific absolute paths are intentionally not followed.
        image = path.parent / (view + '.png')
        if image.resolve() != image.absolute():
            raise ValueError('Capture images must not be links')
        raw = image.read_bytes()
        if hashlib.sha256(raw).hexdigest() != record.get('sha256'):
            raise ValueError('Capture PNG hash mismatch: ' + view)
        w, h, rgba = decode_rgba_png(raw)
        quality, framing = record.get('quality', {}), record.get('framing', {})
        if any(key not in quality for key in QUALITY_KEYS) or quality['output_size'] != w or h != w:
            raise ValueError('Missing or inconsistent capture quality: ' + view)
        if framing.get('camera_readback_verified') is not True or any(key not in framing for key in CAMERA_KEYS):
            raise ValueError('Verified camera readback is required: ' + view)
        def finite(value):
            return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
        if (any(not isinstance(framing[key], list) or len(framing[key]) != 3
                or not all(finite(v) for v in framing[key])
                for key in ('position', 'target', 'forward', 'right_vector'))
                or not finite(framing['fov_degrees']) or not 0 < framing['fov_degrees'] < 180
                or not finite(framing['yaw_degrees'])):
            raise ValueError('Invalid numeric camera readback: ' + view)
        loaded[view] = {'raw': raw, 'rgba': rgba, 'width': w, 'height': h,
                        'quality': quality, 'framing': framing}
    return kind, loaded


def statistics(a, b, width, height, rect, tolerance):
    x0, y0, x1, y1 = rect
    count, changed, total_delta, maximum = 0, 0, 0, 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = (y * width + x) * 4
            delta = [abs(a[i + c] - b[i + c]) for c in range(4)]
            peak = max(delta)
            count += 1
            changed += peak > tolerance
            total_delta += sum(delta)
            maximum = max(maximum, peak)
    return {'rect_pixels': list(rect), 'pixels': count, 'changed_pixels': changed,
            'changed_ratio': changed / count, 'mean_absolute_rgba_delta': total_delta / (count * 4),
            'max_channel_delta': maximum}


def compare(baseline, candidate, out, *, tolerance=0, max_changed_ratio=0, regions=None):
    if type(tolerance) is not int or not 0 <= tolerance <= 255:
        raise ValueError('Pixel tolerance must be an integer in 0..255')
    if isinstance(max_changed_ratio, bool) or not math.isfinite(max_changed_ratio) or not 0 <= max_changed_ratio <= 1:
        raise ValueError('Changed ratio must be finite and in 0..1')
    out = Path(out)
    if out.exists():
        raise FileExistsError('Choose a new output directory')
    kind_a, a = load_capture(baseline)
    kind_b, b = load_capture(candidate)
    if kind_a != kind_b or set(a) != set(b):
        raise ValueError('Capture kind and view set must match')
    regions = {} if regions is None else regions
    if not isinstance(regions, dict) or set(regions) - set(a):
        raise ValueError('Region configuration must address captured views')
    results, artifacts = {}, {}
    for view, before in a.items():
        after = b[view]
        if (before['width'], before['height']) != (after['width'], after['height']):
            raise ValueError('Image dimensions differ: ' + view)
        for key in QUALITY_KEYS:
            if before['quality'][key] != after['quality'][key]:
                raise ValueError('Incompatible GPU capture setting: ' + key)
        for key in CAMERA_KEYS:
            if not close(before['framing'][key], after['framing'][key]):
                raise ValueError('Incompatible camera readback: ' + view + '/' + key)
        w, h = before['width'], before['height']
        rects = {'full_image': (0, 0, w, h)}
        extra = regions.get(view, {})
        if not isinstance(extra, dict) or len(extra) > 8:
            raise ValueError('Each view requires a mapping of region names to normalized rectangles')
        for name, rect in extra.items():
            if not isinstance(name, str) or not name or name == 'full_image' or not isinstance(rect, list) or len(rect) != 4:
                raise ValueError('Invalid region name or rectangle')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in rect):
                raise ValueError('Region coordinates must be finite numbers')
            if not 0 <= rect[0] < rect[2] <= 1 or not 0 <= rect[1] < rect[3] <= 1:
                raise ValueError('Regions use normalized canvas x-right/y-down rectangles')
            value = (int(rect[0] * w), int(rect[1] * h), math.ceil(rect[2] * w), math.ceil(rect[3] * h))
            rects[name] = value
        metrics = {name: statistics(before['rgba'], after['rgba'], w, h, rect, tolerance)
                   for name, rect in rects.items()}
        for entry in metrics.values():
            entry['within_threshold'] = entry['changed_ratio'] <= max_changed_ratio
        results[view] = metrics
        difference = bytearray(w * h * 4)
        for i in range(0, len(difference), 4):
            delta = max(abs(before['rgba'][i + c] - after['rgba'][i + c]) for c in range(4))
            difference[i:i + 4] = bytes((delta, 0, 0, 255))
        artifacts[view] = (before['raw'], after['raw'], png_rgba(w, h, difference))
    passed = all(entry['within_threshold'] for metrics in results.values() for entry in metrics.values())
    report = {'schema': 'vroid-visual-regression-v1', 'baseline': str(baseline),
              'candidate': str(candidate), 'pixel_tolerance': tolerance,
              'max_changed_ratio': max_changed_ratio, 'results': results,
              'within_threshold': passed, 'baseline_approval': 'caller_selected_not_automatically_adopted',
              'scope': 'RGBA image changes under matching available camera/GPU metadata. '
                       'Lighting, driver, source model, app build and pose must be controlled by the caller. '
                       'Not an artistic score, collision proof or engine physics acceptance.'}
    out.mkdir(parents=True, exist_ok=False)
    sections = []
    for view, images in artifacts.items():
        for name, data in zip(('before', 'after', 'difference'), images):
            (out / f'{view}-{name}.png').write_bytes(data)
        sections.append(f'<h2>{html.escape(view)}</h2><div class="images">' + ''.join(
            f'<figure><img src="{view}-{name}.png"><figcaption>{name}</figcaption></figure>'
            for name in ('before', 'after', 'difference')) + '</div>')
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    (out / 'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Visual regression</title>'
        '<style>body{font:16px sans-serif;background:#20242a;color:#eee;margin:24px}.images{display:flex;flex-wrap:wrap}'
        'figure{margin:8px}img{max-width:28vw;min-width:180px}figcaption{padding:8px}</style>'
        '<h1>Visual regression / 图像变化检查</h1><p>'
        + ('Within selected thresholds' if passed else 'Review required: image changes exceed thresholds')
        + '</p><p>Caller-selected baseline; this report does not approve character art. '
          'Red intensity shows maximum channel change; see report.json for full/region metrics.</p>'
        + ''.join(sections), encoding='utf8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--pixel-tolerance', type=int, default=0)
    parser.add_argument('--max-changed-ratio', type=float, default=0)
    parser.add_argument('--regions', type=Path)
    args = parser.parse_args()
    try:
        regions = json.loads(args.regions.read_text(encoding='utf8')) if args.regions else None
        result = compare(args.baseline, args.candidate, args.out,
                         tolerance=args.pixel_tolerance, max_changed_ratio=args.max_changed_ratio,
                         regions=regions)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('VISUAL_COMPARISON_REFUSED: ' + str(error), file=sys.stderr)
        return 2
    print(json.dumps({'within_threshold': result['within_threshold'], 'report': str(args.out / 'report.json')}))
    return 0 if result['within_threshold'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
