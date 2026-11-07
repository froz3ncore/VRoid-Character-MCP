"""Exact group write contracts. No label resolution or scalar unit conversion."""
import math
import struct


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def item_readback(changes, applied, parameters):
    """Compare the command's actual Single input with the settled native model."""
    written = {entry['id'] for entry in applied}
    receipts = []
    for change in changes:
        if change['units'] != 'native_item_blendshape' or change['id'] not in written:
            continue
        matches = [row for row in parameters if row['id'] == change['id']]
        row = matches[0] if len(matches)==1 else {}
        after = row.get('value')
        expected = struct.unpack('<f', struct.pack('<f',change['value']))[0]
        verified = (row.get('item_slider') is True and row.get('editable') is True
                    and row.get('units') == change['units'] and finite(after) and after == expected)
        receipts.append(dict(id=change['id'],requested=change['value'],expected_single=expected,
                             actual=after,verified=verified))
    return receipts


def change_shape(change):
    if not isinstance(change, dict) or change.keys() != {'id', 'type', 'units', 'value'}:
        raise ValueError('INVALID_GROUP_CHANGE_FIELDS: expected id, type, units and value')
    value, kind = change['value'], change['type']
    if not isinstance(change['id'], str) or not isinstance(change['units'], str):
        raise ValueError('INVALID_GROUP_CHANGE_FIELDS')
    if not (kind == 'bool' and type(value) is bool or kind == 'float' and finite(value)
            or kind == 'color' and isinstance(value, list) and len(value) == 4
            and all(finite(v) and 0 <= v <= 1 for v in value)):
        raise ValueError('INVALID_TYPED_NATIVE_VALUE')
    return change


def validate_changes(parameters, changes):
    if not isinstance(changes, list) or not 1 <= len(changes) <= 64:
        raise ValueError('BATCH_SIZE: 1..64')
    index = {}
    for row in parameters:
        index.setdefault(row['id'], []).append(row)
    seen = set()
    for change in changes:
        change_shape(change)
        if len(index.get(change['id'], [])) != 1:
            raise ValueError('UNKNOWN_OR_AMBIGUOUS_BINDING: relist exact IDs')
        row = index[change['id']][0]
        if not row.get('editable'):
            raise ValueError('BINDING_UNSUPPORTED: ' + str(row.get('unsupported_reason')))
        if change.get('type') != row['type'] or change.get('units') != row['units']:
            raise ValueError('BINDING_TYPE_OR_UNITS_MISMATCH')
        keys = set(row.get('binding_keys') or [row['id']])
        if keys & seen:
            raise ValueError('OVERLAPPING_BINDINGS')
        seen.update(keys)
        value, kind = change.get('value'), row['type']
        if kind == 'float' and not (finite(row.get('min')) and finite(row.get('max'))
                                    and row['min'] <= value <= row['max']):
            raise ValueError('INVALID_TYPED_NATIVE_VALUE: ' + row['id'])
    return changes
