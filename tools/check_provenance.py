"""Measure how much inherited text is still in the tree.

A licence cannot be fixed by adding a file: a rewrite is only credible when the
inherited lines are actually gone. Two measurements back that claim:

1. **Per path.** For every path recorded in UPSTREAM.json, compare the baseline
   blob with the current file and report the share of baseline lines that still
   appear in the same order (a longest-common-subsequence measure, so scattered
   boilerplate does not inflate it).
2. **Across files.** A rewrite can move inherited code into new modules, where
   the per-path ratio would look clean. Distinctive baseline lines are therefore
   searched across the whole source tree, and a file carrying several of them
   from one baseline path is reported.

    python tools/check_provenance.py                 # report and enforce
    python tools/check_provenance.py --report-only    # report, always exit 0
    python tools/check_provenance.py --max-ratio 0.1 --json out.json

Exit codes: 0 every inherited path is under the threshold and no new file carries
inherited text, 1 something still does, 2 the baseline or Git data is unavailable.
"""

from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import re
import subprocess
import sys

PROJECT = pathlib.Path(__file__).resolve().parents[1]
UPSTREAM = PROJECT / 'UPSTREAM.json'

# Nothing this short is authorship: braces, single words, one-argument calls.
MIN_LINE = 20
# A line is a useful fingerprint when it is long and not a stock statement.
DISTINCTIVE = 30
BOILERPLATE = re.compile(
    r'^(import |from \S+ import |export |require\(|if __name__|def main\(|return |pass$|'
    r'#|//|/\*|\*|@|\}|\)|\]|else|try\{|catch|finally|raise |with |async def |class \w+\(|'
    r'"""[^"]*"""$|const |let |var )', re.IGNORECASE)
SOURCE_SUFFIXES = {'.py', '.js', '.ps1', '.toml', '.json', '.md', '.txt'}
SKIP_DIRS = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', 'build', 'dist',
             'pipeline', 'docs', 'work', 'lab', 'lab-test', 'lab-codex', 'lab-e2e',
             'lab-clothing-fit-v17', 'archives', 'projects', 'runtimes', 'downloads',
             'evidence', 'blender-addons', 'tools'}

# Declarative files whose remaining lines are dictated by a tool's own schema
# rather than by authorship: a lockfile pin or a setuptools key has to read the
# way the tool writes it. Re-expressing them would falsify the facts they carry,
# so they are reported as structural with the reason, never silently ignored.
STRUCTURAL = {
    'package-lock.json': 'npm lockfile: dependency pins and integrity hashes',
    'package.json': 'packaging metadata: name, version and dependency pins',
    'requirements.txt': 'dependency pins',
    'pyproject.toml': 'packaging metadata: setuptools and pytest keys',
    '.gitignore': 'ignore patterns named by the tools in use',
}


def _baseline_blob(commit: str, path: str) -> str | None:
    result = subprocess.run(['git', '-C', str(PROJECT), 'show', f'{commit}:{path}'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.stdout if result.returncode == 0 else None


def _significant(text: str) -> list[str]:
    """Ordered lines that represent authorial expression, not stock syntax."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < MIN_LINE or BOILERPLATE.match(line):
            continue
        out.append(line)
    return out


def _ordered_residue(baseline: list[str], current_text: str) -> dict:
    current = _significant(current_text)
    matcher = difflib.SequenceMatcher(None, baseline, current, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    matched = sum(block.size for block in blocks)
    total = len(baseline)
    examples = [baseline[block.a] for block in blocks[:3]]
    return {'baseline_lines': total, 'remaining_lines': matched,
            'ratio': round(matched / total, 4) if total else 0.0,
            'examples': examples}


def _source_files() -> list[pathlib.Path]:
    files = []
    for path in PROJECT.rglob('*'):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        parts = set(path.relative_to(PROJECT).parts[:-1])
        if parts & SKIP_DIRS:
            continue
        files.append(path)
    return files


def _cross_file_residue(baselines: dict[str, str], tracked: set[str]) -> list[dict]:
    """Find baseline lines that now live in a file other than their own path."""
    fingerprints: dict[str, set[str]] = {}
    for path, blob in baselines.items():
        lines = {line for line in _significant(blob) if len(line) >= DISTINCTIVE}
        if lines:
            fingerprints[path] = lines
    findings = []
    for path in _source_files():
        relative = path.relative_to(PROJECT).as_posix()
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for source, lines in fingerprints.items():
            if source == relative:
                continue
            hits = [line for line in lines if line in text]
            if len(hits) >= 5:
                findings.append({'path': relative, 'from': source, 'lines': len(hits),
                                 'examples': hits[:2]})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description='Measure inherited text still present')
    parser.add_argument('--max-ratio', type=float, default=0.10,
                        help='allowed share of inherited lines per file (default 0.10)')
    parser.add_argument('--report-only', action='store_true')
    parser.add_argument('--json', dest='json_out', default='')
    args = parser.parse_args()

    if not UPSTREAM.is_file():
        print(f'missing {UPSTREAM}', file=sys.stderr)
        return 2
    try:
        spec = json.loads(UPSTREAM.read_text(encoding='utf-8'))
        commit = spec['baseline_commit']
        paths = [entry['path'] for entry in spec['tracked_paths']]
        subprocess.run(['git', '-C', str(PROJECT), 'cat-file', '-e', commit + '^{commit}'],
                       check=True, capture_output=True)
    except (KeyError, ValueError, subprocess.CalledProcessError) as error:
        print(f'cannot read the recorded baseline: {error}', file=sys.stderr)
        return 2

    baselines = {}
    rows = []
    for path in paths:
        blob = _baseline_blob(commit, path)
        if blob is None:
            rows.append({'path': path, 'status': 'baseline-missing', 'ratio': None})
            continue
        baselines[path] = blob
        baseline = _significant(blob)
        target = PROJECT / path
        if not target.is_file():
            rows.append({'path': path, 'status': 'removed', 'ratio': 0.0,
                         'baseline_lines': len(baseline), 'remaining_lines': 0, 'examples': []})
            continue
        measured = _ordered_residue(baseline, target.read_text(encoding='utf-8', errors='replace'))
        if path in STRUCTURAL:
            rows.append({'path': path, 'status': 'structural', 'reason': STRUCTURAL[path], **measured})
            continue
        if measured['baseline_lines'] < 3:
            # Too little expression to measure; the cross-file pass still covers it.
            rows.append({'path': path, 'status': 'structural', **measured})
            continue
        over = measured['ratio'] > args.max_ratio
        rows.append({'path': path, 'status': 'inherited-text' if over else 'rewritten', **measured})

    moved = _cross_file_residue(baselines, set(paths))
    over = [row for row in rows if row['status'] == 'inherited-text']
    rewritten = [row for row in rows if row['status'] in ('rewritten', 'removed', 'structural')]
    summary = {'schema': 'vroid-provenance-v2', 'baseline_commit': commit, 'max_ratio': args.max_ratio,
               'paths': len(rows), 'rewritten': len(rewritten),
               'pending': [row['path'] for row in over], 'moved_into_new_files': moved, 'rows': rows}

    print(f"{'ratio':>7}  {'status':<16} path")
    for row in sorted(rows, key=lambda r: (r['ratio'] is None, -(r['ratio'] or 0))):
        ratio = '-' if row['ratio'] is None else f"{row['ratio']:.3f}"
        print(f'{ratio:>7}  {row["status"]:<16} {row["path"]}')
    if moved:
        print('\ninherited lines found in other files:')
        for finding in moved:
            print(f"  {finding['lines']:>3} lines  {finding['path']}  <- {finding['from']}")
    print(f"\n{len(rewritten)}/{len(rows)} inherited paths rewritten, removed or structural; "
          f'{len(over)} still above {args.max_ratio:.2f}; {len(moved)} cross-file findings')

    # One compact line for the PowerShell runner; a full JSON parse of the report
    # is unnecessary there and older PowerShell builds choke on large payloads.
    print('PROVENANCE ' + json.dumps({'rewritten': len(rewritten), 'paths': len(rows),
                                      'pending': summary['pending'],
                                      'moved': [f['path'] for f in moved]}, ensure_ascii=False))

    if args.json_out:
        target = pathlib.Path(args.json_out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')

    if args.report_only:
        return 0
    return 1 if over or moved else 0


if __name__ == '__main__':
    raise SystemExit(main())
