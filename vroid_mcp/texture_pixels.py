"""Source luminance/multiply math; explicit round-half-up RGBA8 publication.

Adapted from mcjo79/vroid-mcp Textures.cs, MIT, revision 0dc7d5e.
Native Color[] quantization is unverified; actual readback is always returned.
"""
import colorsys
import math

from .bounded_paint import decode_rgba_png
from .texture_mapping import png_rgba


def validate_color(color):
    if (not isinstance(color, (list, tuple)) or len(color) not in (3, 4)
            or any(isinstance(v, bool) or not isinstance(v, (int, float))
                   or not math.isfinite(v) or not 0 <= v <= 1 for v in color)):
        raise ValueError('Color requires three or four finite channels in [0,1]')
    return list(color) if len(color) == 4 else [*color, 1]


def validate_recolor(color, mode, strength):
    color = validate_color(color)
    if mode not in ('multiply', 'colorize'):
        raise ValueError('Mode must be multiply or colorize')
    if (isinstance(strength, bool) or not isinstance(strength, (int, float))
            or not math.isfinite(strength) or not 0 <= strength <= 1):
        raise ValueError('Strength must be finite and in [0,1]')
    return color


def recolor_png(data, color, mode='multiply', strength=1):
    color = validate_recolor(color, mode, strength)
    width, height, source = decode_rgba_png(data)
    if strength == 0:
        return data
    h, s, _ = colorsys.rgb_to_hsv(*color[:3])
    base = colorsys.hsv_to_rgb(h, s, 1)
    weights = (.299, .587, .114)
    base_lum = sum(v*w for v, w in zip(base, weights))
    output = bytearray(source)
    for i in range(0, len(source), 4):
        rgb = [v/255 for v in source[i:i+3]]
        if mode == 'multiply':
            target = [a*b for a, b in zip(rgb, color)]
        else:
            lum = sum(v*w for v, w in zip(rgb, weights))
            k = lum/base_lum if base_lum > .0001 else 0
            target = [min(1, max(0, v*k)) for v in base]
        for j in range(3):
            output[i+j] = math.floor((rgb[j]+strength*(target[j]-rgb[j]))*255+.5)
    return png_rgba(width, height, output)
