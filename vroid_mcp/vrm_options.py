"""Ordinary VRM option contract (native choices are discovered, never guessed)."""
SLIDERS = frozenset(('hair_smoothness', 'hair', 'face', 'body', 'outfit', 'hair_bones'))
FLAGS = frozenset(('delete_transparent', 'hair_cross_section', 'combine_hair'))
CHOICES = frozenset(('material_mode', 'texture_mode', 'atlas_resolution'))


def validate_options(options, choices=None):
    if options is None:
        return None
    if type(options) is not dict:
        raise ValueError('options must be an object')
    for key, value in options.items():
        if key in FLAGS:
            valid = type(value) is bool
        elif key in SLIDERS:
            valid = type(value) is int and 0 <= value <= 100
        elif key in CHOICES:
            valid = type(value) is int and value >= 0
            if valid and choices is not None:
                valid = any(item['index'] == value for item in choices.get(key, []))
        else:
            valid = False
        if not valid:
            raise ValueError('Invalid VRM export option: ' + str(key))
    return dict(options)
