"""Category framing adapted from mcjo79 preset_cache.py/config/framing.json (MIT).

Distance is a region-span multiplier, never metres. Consumers must use measured
min/max model bounds; full-body fitting ignores regional fields without losing
the requested values. Geometry and actual capture belong to situation capture.
"""
from copy import deepcopy
import math
import re


def category(value):
    if (not isinstance(value, str) or len(value) > 160 or not re.fullmatch(
            r'(?:Clothing|Hair|Face|Body|Skin|Attachment|Overlay|VRoid|Custom)(?:/[A-Za-z0-9_.-]+)*', value)
            or any(p in ('.', '..') for p in value.split('/'))):
        raise ValueError('INVALID_CATALOG_CATEGORY')
    return value


def profile(top=0, bottom=1, half=None, distance=3.3, yaw=0, fit='region'):
    return dict(top=top, bottom=bottom, half=half, distance=distance, yaw=yaw, fit=fit)


# Exact source defaults. Stronger region/full-body geometry is a target contract.
_DEFAULTS = {
    'Clothing/Tops': profile(.12,.62), 'Clothing/Onepiece': profile(.12,.85),
    'VRoid/ClothingSet': profile(0,1,None,4.2,fit='full-body'),
    'Clothing/InnerTop': profile(.12,.45,.2), 'Clothing/Bottoms': profile(.4,.8,.22),
    'Clothing/InnerBottom': profile(.4,.65,.22), 'Clothing/Socks': profile(.5,1,.22),
    'Clothing/Shoes': profile(.8,1,.22,yaw=45),
    'Clothing/AccessoryNeck': profile(.1,.35,.18), 'Clothing/AccessoryArm': profile(.15,.5,None,yaw=45),
    'Attachment': profile(0,.4,.25), 'Hair': profile(0,.32,.2),
    'Hair/AllHair': profile(0,.8,.3,3.5,135), 'Hair/Back': profile(0,.6,.3,3.5,180),
    'Hair/Tied': profile(0,.6,.3,3.5,180), 'VRoid/HairSet': profile(0,.7,.3,3.5,135),
    'VRoid/Body': profile(0,1,None,3.8,fit='full-body'),
    'Face': profile(.02,.2,.12), 'Overlay': profile(.02,.2,.12),
    'VRoid/FaceSet': profile(.02,.2,.12), 'VRoid/EyeSet': profile(.06,.16,.1),
    'VRoid/EyeballSet': profile(.06,.16,.1),
}

_CUSTOM_EQUIV = {
    'Tops':'Clothing/Tops','Bottoms':'Clothing/Bottoms','Onepiece':'Clothing/Onepiece',
    'Socks':'Clothing/Socks','Shoes':'Clothing/Shoes','InnerTop':'Clothing/InnerTop',
    'InnerBottom':'Clothing/InnerBottom','ArmAccessory':'Clothing/AccessoryArm',
    'NeckAccessory':'Clothing/AccessoryNeck','AllHair':'Hair/AllHair','HairFront':'Hair',
    'HairBack':'Hair/Back','BaseHair':'Hair','BodySkin':'VRoid/Body',
}


def defaults():
    return deepcopy(_DEFAULTS)


def validate(value):
    if not isinstance(value, dict) or set(value) != set(profile()):
        raise ValueError('INVALID_FRAMING_FIELDS')
    for key in ('top', 'bottom', 'distance', 'yaw', 'half'):
        number = value[key]
        if key == 'half' and number is None:
            continue
        if isinstance(number, bool) or not isinstance(number, (int,float)) or not math.isfinite(number):
            raise ValueError('INVALID_FRAMING_NUMBER')
    if (not 0 <= value['top'] < value['bottom'] <= 1
            or value['half'] is not None and not 0 < value['half'] <= 1
            or not .1 <= value['distance'] <= 100 or not -360 <= value['yaw'] <= 360
            or value['fit'] not in ('region', 'full-body')):
        raise ValueError('INVALID_FRAMING_RANGE')
    return deepcopy(value)


def resolve(requested, overrides):
    requested = category(requested)
    candidates = [requested]
    if requested.startswith('Custom/'):
        slot = requested.split('/', 1)[1]
        if slot in _CUSTOM_EQUIV:candidates.append(_CUSTOM_EQUIV[slot])
    candidates += [c.split('/')[0] for c in candidates.copy()]
    for candidate in candidates:
        if candidate in overrides or candidate in _DEFAULTS:
            result = validate(overrides.get(candidate, _DEFAULTS.get(candidate)))
            return dict(result, category=requested, resolved_category=candidate,
                        source='override' if candidate in overrides else 'default',
                        distance_unit='region-span multiplier',
                        inactive_fields=['top','bottom','half'] if result['fit'] == 'full-body' else [])
    return dict(profile(), category=requested, resolved_category=None, source='fallback',
                distance_unit='region-span multiplier', inactive_fields=[])
