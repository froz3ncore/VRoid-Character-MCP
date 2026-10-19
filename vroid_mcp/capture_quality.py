"""Bound screenshot GPU work; requested output size remains unchanged."""
import math
import base64

def quality_plan(size: int, quality: str = 'balanced') -> dict:
    if type(size) is not int or not 256 <= size <= 2048:
        raise ValueError('Capture size must be 256..2048')
    if quality not in ('legacy', 'balanced', 'high'):
        raise ValueError('Capture quality must be legacy, balanced or high')
    scale = 2 if quality == 'high' else 1
    side = min(size * scale, math.isqrt(8_000_000))
    return dict(quality=quality, output_size=size, render_size=side,
                requested_scale=scale, effective_scale=side/size,
                requested_msaa=1 if quality == 'legacy' else 4,
                pixel_budget=8_000_000, clamped=side != size * scale)

def decode_capture(result: dict, size: int, quality: str) -> bytes:
    plan=quality_plan(size,quality)
    metadata=result['quality']
    if any(metadata.get(key)!=value for key,value in plan.items()):
        raise ValueError('Native capture quality plan mismatch')
    samples=metadata.get('msaa_samples')
    if type(samples) is not int or samples not in (1,2,4) or samples>plan['requested_msaa']:
        raise ValueError('Invalid native MSAA readback')
    data=base64.b64decode(result['base64'],validate=True)
    if (len(data)<24 or data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR'
        or (int.from_bytes(data[16:20],'big'),int.from_bytes(data[20:24],'big'))!=(size,size)
        or (result.get('width'),result.get('height'))!=(size,size)):
        raise ValueError('Unexpected native PNG capture resolution')
    return data
