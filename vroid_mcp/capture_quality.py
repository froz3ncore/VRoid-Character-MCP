"""Bound screenshot GPU work; requested output size remains unchanged."""
import math
import base64

def quality_plan(size: int, quality: str = 'balanced', *, width=None, height=None, msaa=None, ssaa=None) -> dict:
    if type(size) is not int or not 256 <= size <= 2048:
        raise ValueError('Capture size must be 256..2048')
    if quality not in ('legacy', 'balanced', 'high'):
        raise ValueError('Capture quality must be legacy, balanced or high')
    if (width is None) != (height is None):
        raise ValueError('Capture width and height must be paired')
    w, h = (size, size) if width is None else (width, height)
    if any(type(v) is not int or not 256 <= v <= 2048 for v in (w, h)):
        raise ValueError('Capture dimensions must be 256..2048')
    if msaa is not None and (type(msaa) is not int or msaa not in (1, 2, 4)):
        raise ValueError('MSAA must be 1, 2 or 4')
    if ssaa is not None and (type(ssaa) is not int or ssaa not in (1, 2, 3)):
        raise ValueError('SSAA must be 1, 2 or 3')
    scale = ssaa if ssaa is not None else (2 if quality == 'high' else 1)
    effective = min(scale, math.sqrt(8_000_000 / (w * h)))
    rw, rh = math.floor(w * effective), math.floor(h * effective)
    return dict(quality=quality, output_size=size, render_size=rw,
                output_width=w, output_height=h, render_width=rw, render_height=rh,
                requested_scale=scale, effective_scale=rw/w,
                effective_scale_x=rw/w, effective_scale_y=rh/h,
                requested_msaa=msaa if msaa is not None else (1 if quality == 'legacy' else 4),
                pixel_budget=8_000_000, clamped=rw != w * scale or rh != h * scale)

def decode_capture(result: dict, size: int, quality: str, **overrides) -> bytes:
    plan=quality_plan(size,quality,**overrides)
    metadata=result['quality']
    if any(metadata.get(key)!=value for key,value in plan.items()):
        raise ValueError('Native capture quality plan mismatch')
    samples=metadata.get('msaa_samples')
    if type(samples) is not int or samples not in (1,2,4) or samples>plan['requested_msaa']:
        raise ValueError('Invalid native MSAA readback')
    data=base64.b64decode(result['base64'],validate=True)
    if (len(data)<24 or data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR'
        or (int.from_bytes(data[16:20],'big'),int.from_bytes(data[20:24],'big'))!=(plan['output_width'],plan['output_height'])
        or (result.get('width'),result.get('height'))!=(plan['output_width'],plan['output_height'])):
        raise ValueError('Unexpected native PNG capture resolution')
    return data
