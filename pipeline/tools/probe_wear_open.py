"""Minimal native probe: open the clean-wear base project and report where it dies.

Usage (needs the same environment as tools/accept_refined_native_wear.py):

    python tools/probe_wear_open.py --out RUNDIR

Prints each step so a crash shows exactly which call was in flight.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import clean_native_clothing as native

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / 'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']


async def main(out: Path):
    native.OUT = out
    print('BASE', BASE['path'], flush=True)
    async with native.client_for(Path(BASE['path']), 'probe-wear-open') as (client, call):
        print('STEP get_wear_status', flush=True)
        status = await call('get_wear_status')
        print('  wear_token', status.get('wear_token', '')[:8], flush=True)
        print('STEP open_wear_project', flush=True)
        status = await call('open_wear_project', {
            'filename': Path(BASE['path']).name,
            'expected_wear': status['wear_token'],
            'discard_unsaved': True,
        })
        print('  opened ok', flush=True)
        print('STEP get_wear_snapshot', flush=True)
        snap = await call('get_wear_snapshot', {'expected_wear': status['wear_token']})
        print('  items', len(snap.get('items', [])), 'tools', len((await client.list_tools()).tools), flush=True)
    print('PROBE_OK', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    asyncio.run(main(args.out.resolve()))
