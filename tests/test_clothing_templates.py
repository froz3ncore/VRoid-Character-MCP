import asyncio

import pytest

from vroid_mcp.runtime import Runtime


@pytest.mark.parametrize(('parts', 'images', 'confirmed'), [
    (['base', 'overlay'], ['base-image', 'overlay-image'], True),
    (['base'], ['base-image'], False),
    (['overlay'], ['overlay-image'], False),
    (['base', 'overlay'], ['overlay-image'], False),
])
def test_add_template_confirms_append_without_replacement(parts, images, confirmed):
    async def exercise():
        runtime = Runtime.__new__(Runtime)
        runtime.lock = asyncio.Lock()
        calls = []

        async def settled_for(token, frame=-1):
            assert token == 'model'

        async def call(name, args):
            calls.append(name)
            assert args['region_id'] == 'tops'
            if name == 'add_clothing_template':
                return {'frame': 1, 'before': {
                    'transferable_ids': ['base'], 'images': [{'image_id': 'base-image'}],
                }}
            assert name == 'clothing_template_state'
            return {'model_token': 'model', 'transferable_ids': parts,
                    'images': [{'image_id': image} for image in images]}

        runtime._settled_for = settled_for
        runtime._call = call
        result = await runtime.add_clothing_template('model', 'tops', 'shirt')
        assert calls == ['add_clothing_template', 'clothing_template_state']
        assert result['ok'] is confirmed and result['retry_safe'] is False
        if confirmed:
            assert result['added_images'] == [{'image_id': 'overlay-image'}]

    asyncio.run(exercise())
