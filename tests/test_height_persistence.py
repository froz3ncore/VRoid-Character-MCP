import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import e2e_clean_lab as e2e


def test_checkpoint_keeps_cached_ui_separate_from_live_geometry():
    async def call(name):
        if name == 'get_height':
            return {'centimeters': 159.26326, 'live_centimeters': 159.20933}
        return {'parameters': [{'id': 'body/WholeBody/002', 'value': -.023498}]}
    reading = asyncio.run(e2e.height_checkpoint(call))
    assert reading == {'live_cm': 159.20933, 'ui_cm': 159.26326, 'scale': -.023498}
    e2e.verify_height(reading, target_cm=159.20933)


@pytest.mark.parametrize('changed', [
    {'live_cm': 159.20933, 'ui_cm': 159.20933, 'scale': -.04},
    {'live_cm': 157.8, 'ui_cm': 157.8, 'scale': -.02},
])
def test_reopen_cannot_hide_geometry_or_scale_changes_in_two_cm_allowance(changed):
    expected = {'live_cm': 157.8, 'ui_cm': 157.8, 'scale': -.04}
    with pytest.raises(RuntimeError):
        e2e.verify_height(changed, expected=expected)


def test_stale_ui_on_reopen_does_not_masquerade_as_persistence_failure():
    before = {'live_cm': 151.800048, 'ui_cm': 151.800048, 'scale': -.11108661}
    after = {**before, 'ui_cm': 151.851486}
    e2e.verify_height(after, expected=before, target_cm=151.8)


def test_styling_change_must_fail_target_check_even_if_it_precedes_save():
    with pytest.raises(RuntimeError, match='missed target'):
        e2e.verify_height({'live_cm': 159.20933, 'ui_cm': 159.20933, 'scale': -.023498},
                          target_cm=157.8)


@pytest.mark.parametrize('field', ['live_cm', 'ui_cm', 'scale'])
def test_nonfinite_checkpoint_is_rejected(field):
    reading = {'live_cm': 157.8, 'ui_cm': 157.8, 'scale': -.04, field: float('nan')}
    with pytest.raises(RuntimeError, match='non-finite'):
        e2e.verify_height(reading, target_cm=157.8)
