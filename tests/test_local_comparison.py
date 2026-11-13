import pytest
from pydantic import ValidationError

from vroid_mcp.local_comparison import Comparison
from vroid_mcp.server import INSTRUCTIONS


def test_comparison_requires_one_category():
    Comparison.model_validate({
        'preset_ids': ['face/eyes/a', 'face/eyes/b'],
        'views': ['face_front'],
    })
    with pytest.raises(ValidationError):
        Comparison.model_validate({'preset_ids': ['face/eyes/a', 'hair/front/b']})
    with pytest.raises(ValidationError):
        Comparison.model_validate({
            'preset_ids': ['face/eyes/a', 'face/eyes/b'],
            'views': ['front'],
        })


def test_initialize_guidance_covers_layered_clothing():
    assert 'list_clothing_templates' in INSTRUCTIONS
    assert 'add_clothing_template' in INSTRUCTIONS
    assert 'include_images=false' in INSTRUCTIONS
    assert 'InnerTop' in INSTRUCTIONS
