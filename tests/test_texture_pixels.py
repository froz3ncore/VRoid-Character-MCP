import pytest

from vroid_mcp.bounded_paint import decode_rgba_png
from vroid_mcp.texture_mapping import png_rgba
from vroid_mcp.texture_pixels import recolor_png


PIXELS = bytes([120, 80, 40, 0, 12, 100, 200, 77, 255, 128, 5, 255])


def test_multiply_preserves_alpha_including_transparent_rgb_and_blends_strength():
    png = png_rgba(3, 1, PIXELS)
    result = recolor_png(png, [0.5, 0.25, 1], 'multiply', 0.5)
    assert decode_rgba_png(result)[2] == bytes([90, 50, 40, 0, 9, 63, 200, 77, 191, 80, 5, 255])
    assert recolor_png(png, [0.1, 0.2, 0.3], 'multiply', 0) == png


def test_colorize_uses_hsv_unit_value_then_luminance_scaling_and_clipping():
    # Requested red brightness is discarded; base=(1,0,0), baseLum=.299.
    png = png_rgba(3, 1, PIXELS)
    result = decode_rgba_png(recolor_png(png, [0.2, 0, 0], 'colorize', 1))[2]
    assert result == bytes([255, 0, 0, 0, 255, 0, 0, 77, 255, 0, 0, 255])
    gray = decode_rgba_png(recolor_png(png, [0, 0, 0], 'colorize', 1))[2]
    assert gray == bytes([87, 87, 87, 0, 85, 85, 85, 77, 152, 152, 152, 255])


@pytest.mark.parametrize('color,mode,strength', [([1, 0], 'multiply', 1), ([2, 0, 0], 'multiply', 1),
    ([float('nan'), 0, 0], 'multiply', 1), ([1, 0, 0], 'other', 1),
    ([1, 0, 0], 'multiply', -1), ([1, 0, 0], 'multiply', float('inf'))])
def test_invalid_pixel_arguments_are_rejected(color, mode, strength):
    with pytest.raises(ValueError):
        recolor_png(png_rgba(3, 1, PIXELS), color, mode, strength)
