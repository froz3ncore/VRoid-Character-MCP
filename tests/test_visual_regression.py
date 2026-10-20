import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from vroid_mcp.texture_mapping import png_rgba

spec = importlib.util.spec_from_file_location('visual_regression',
    Path(__file__).resolve().parents[1] / 'tools/visual_regression.py')
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)


def capture(folder, pixels=None, **changes):
    folder.mkdir()
    raw = png_rgba(4, 4, pixels if pixels is not None else bytes([0, 0, 0, 255]) * 16)
    (folder / 'body_front.png').write_bytes(raw)
    framing = {'camera_readback_verified': True, 'position': [0, 1, 3], 'target': [0, 1, 0],
               'fov_degrees': 30, 'forward': [0, 0, -1], 'right_vector': [-1, 0, 0], 'yaw_degrees': 0}
    quality = {'quality': 'balanced', 'output_size': 4, 'render_size': 4, 'msaa_samples': 4}
    record = {'path': 'X:/old-machine/body_front.png', 'sha256': hashlib.sha256(raw).hexdigest(),
              'quality': quality, 'framing': framing}
    for key, value in changes.items():
        if key in framing: framing[key] = value
        else: quality[key] = value
    path = folder / 'review.json'
    path.write_text(json.dumps({'images': {'body_front': record}}), encoding='utf8')
    return path


def test_copied_captures_are_portable_and_output_is_independent_of_input_paths(tmp_path):
    a = capture(tmp_path / 'a')
    b = capture(tmp_path / 'b', render_and_encode_ms=99)
    result = visual.compare(a, b, tmp_path / 'out')
    assert result['within_threshold']
    assert result['results']['body_front']['full_image']['changed_pixels'] == 0
    assert (tmp_path / 'out/review.html').is_file()
    assert (tmp_path / 'out/body_front-before.png').read_bytes() == (a.parent / 'body_front.png').read_bytes()


def test_one_pixel_change_has_exact_metric_and_exceeds_strict_threshold(tmp_path):
    a = capture(tmp_path / 'a')
    pixels = bytearray([0, 0, 0, 255] * 16)
    pixels[0] = 100
    b = capture(tmp_path / 'b', bytes(pixels))
    result = visual.compare(a, b, tmp_path / 'out')
    metrics = result['results']['body_front']['full_image']
    assert metrics['changed_pixels'] == 1 and metrics['changed_ratio'] == 1 / 16
    assert metrics['max_channel_delta'] == 100
    assert metrics['mean_absolute_rgba_delta'] == 100 / 64
    assert not result['within_threshold']


def test_roi_can_detect_a_local_regression_hidden_by_global_ratio(tmp_path):
    a = capture(tmp_path / 'a')
    pixels = bytearray([0, 0, 0, 255] * 16)
    pixels[0] = 100
    b = capture(tmp_path / 'b', bytes(pixels))
    result = visual.compare(a, b, tmp_path / 'out', max_changed_ratio=.2,
                            regions={'body_front': {'detail': [0, 0, .25, .25]}})
    assert result['results']['body_front']['full_image']['within_threshold']
    assert not result['results']['body_front']['detail']['within_threshold']
    assert not result['within_threshold']


@pytest.mark.parametrize('change', [{'fov_degrees': 35}, {'position': [0, 1, 4]},
                                   {'msaa_samples': 2}, {'camera_readback_verified': False},
                                   {'target': [0, float('nan'), 0]}])
def test_incompatible_or_unverified_metadata_is_rejected_before_output(tmp_path, change):
    a, b = capture(tmp_path / 'a'), capture(tmp_path / 'b', **change)
    with pytest.raises(ValueError):
        visual.compare(a, b, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_tampered_png_is_not_accepted_as_a_new_visual_baseline(tmp_path):
    a, b = capture(tmp_path / 'a'), capture(tmp_path / 'b')
    (b.parent / 'body_front.png').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash mismatch'):
        visual.compare(a, b, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_existing_output_is_never_replaced(tmp_path):
    a, b = capture(tmp_path / 'a'), capture(tmp_path / 'b')
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'keep').write_bytes(b'keep')
    with pytest.raises(FileExistsError):
        visual.compare(a, b, out)
    assert (out / 'keep').read_bytes() == b'keep'


@pytest.mark.parametrize('rect', [[0, 0, 0, 1], [0, 0, 2, 1], [True, 0, 1, 1]])
def test_invalid_regions_are_refused_before_outputs(tmp_path, rect):
    a, b = capture(tmp_path / 'a'), capture(tmp_path / 'b')
    with pytest.raises(ValueError):
        visual.compare(a, b, tmp_path / 'out', regions={'body_front': {'detail': rect}})
    assert not (tmp_path / 'out').exists()
