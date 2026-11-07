"""Exercise the registered FastMCP argument parser and heterogeneous batch."""
import asyncio

import pytest

from vroid_mcp import server


def test_published_writes_refuse_malformed_input_before_any_prefix(tmp_path, monkeypatch):
    writes = []
    class Copy:
        mode = 'copy'
        dead = uncertain = False
        def __init__(self, lab): pass
        def start(self): pass
        async def initialize(self, *args): pass
        async def set_hair_material_color(self, *args):
            writes.append(args)
            return {'ok': True}
        async def set_group_parameters(self, *args):
            writes.append(args)
            return {'ok': True}
        async def colorize(self, *args):
            writes.append(args)
            return {'ok': True}
    monkeypatch.setattr(server, 'Runtime', Copy)
    mcp = server.create_server(tmp_path, 'F00')
    valid = dict(tool='set_hair_material_color', args=dict(expected_model='M', material_id='H',
                                                           key='diffuse', color=[0, 0.5, 1]))
    row = dict(id='P', type='float', units='native_vm', value=.25)
    invalid = [
        (valid['tool'], {**valid['args'], 'color': [True, '0.5', False]}),
        (valid['tool'], {**valid['args'], 'dry_run': True}),
        ('set_group_parameters', dict(expected_model='M', group_id='G', changes=[row, {**row, 'dry_run': True}])),
        ('colorize', dict(expected_model='M', target='global', group_id='G', color=[1,1,1], strength='0.5')),
    ]
    async def scenario():
        for name, args in invalid:
            with pytest.raises(Exception): await mcp.call_tool(name, args)
            with pytest.raises(Exception):
                await mcp.call_tool('run_batch', dict(operations=[valid, dict(tool=name, args=args)]))
            assert not writes
        await mcp.call_tool(valid['tool'], {**valid['args'], 'color': '[0,0.5,1]'})
        assert len(writes) == 1 and writes[0][-1] == [0,.5,1]
    asyncio.run(scenario())
