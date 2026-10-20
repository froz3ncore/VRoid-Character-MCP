"""Reproduce a public sample without private character assets or a live Blender.

Creates a diagnostic asset in an independent background Blender, then runs the
existing native edit/save/cold-reopen/Dress-up/VRM E2E in a new disposable lab.
Both --out and --lab must be new, separate directories outside the source and
repository. Failed runs are retained for inspection, never automatically retried.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def validate_paths(source: Path, lab: Path, out: Path, repo: Path = ROOT):
    for target in (lab, out):
        if target.exists():
            raise FileExistsError('Choose a new directory: ' + str(target))
        for protected in (source, repo):
            if target == protected or target.is_relative_to(protected) or protected.is_relative_to(target):
                raise ValueError('Output/lab must be separate from source and repository: ' + str(target))
    if lab == out or lab.is_relative_to(out) or out.is_relative_to(lab):
        raise ValueError('Lab and sample output directories must be separate')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'lab', 'out', 'blender'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args(argv)
    source, lab, out, blender = (getattr(args, key).resolve()
                                  for key in ('source', 'lab', 'out', 'blender'))
    try:
        validate_paths(source, lab, out)
        if not blender.is_file():
            raise FileNotFoundError('Blender executable is missing: ' + str(blender))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'vroid-public-sample-run-v1', 'source': str(source),
              'lab': str(lab), 'out': str(out), 'stages': [], 'ok': False,
              'scope': 'Same-machine reproducibility; not independent user acceptance or art adoption'}

    def stage(name, argv, timeout=None):
        print('SAMPLE_STAGE ' + name, flush=True)
        path = out / (name + '.log')
        with path.open('x', encoding='utf8') as log:
            result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=timeout, env={**os.environ, 'PYTHONUTF8': '1',
                                                          'PYTHONIOENCODING': 'utf-8'})
        report['stages'].append({'name': name, 'exit_code': result.returncode, 'log': str(path)})
        if result.returncode:
            raise RuntimeError(name + ' failed; see ' + str(path))

    code = 1
    try:
        stage('doctor', [sys.executable, str(ROOT / 'tools/doctor.py'), '--source', str(source),
                         '--json', str(out / 'doctor.json')], 25)
        stage('asset', [str(blender), '--background', '--factory-startup', '--disable-autoexec',
                        '--threads', '1', '--python-exit-code', '1',
                        '--python', str(ROOT / 'tools/build_sample_asset.py'),
                        '--', '--out', str(out / 'asset')], 120)
        stage('e2e', [sys.executable, str(ROOT / 'tools/e2e_clean_lab.py'), '--source', str(source),
                      '--lab', str(lab), '--xwear', str(out / 'asset/sample-badge.xwear'),
                      '--capture-reviews', '--json', str(out / 'e2e.json')])
        report['e2e'] = json.loads((out / 'e2e.json').read_text(encoding='utf8'))
        if not report['e2e'].get('ok'):
            raise RuntimeError('E2E did not produce a passing report')
        report['ok'] = True
        code = 0
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        report['exit_code'] = code
        (out / 'sample.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print('SAMPLE_REPORT ' + str(out / 'sample.json'))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
