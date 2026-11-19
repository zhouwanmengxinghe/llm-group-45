"""Build the minimal English submission with one report and runnable evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TEXT = {'.py', '.html', '.md', '.txt', '.toml', '.json', '.jsonl', '.csv',
        '.cmd', '.command', '.sh', '.ini', '.lock', '.conf', '.patch', '.svg'}
EXCLUDED = {'.git', '.venv', '__pycache__', '.pytest_cache'}


def selected_files():
    for name in ['README.md', 'AI_USE_DECLARATION.md', 'THIRD_PARTY.md',
                 'bootstrap.py', 'start.cmd', 'start.command', 'requirements-dev.txt',
                 'pytest.ini', 'configs/model.example.toml',
                 'docs/reports/PatchLab_Final_Report_EN_Illustrated.pdf',
                 'docs/reports/historical40-index.csv',
                 'ai_records/recoverable_project_prompts_en.md', 'ai_records/runtime_prompts.json',
                 'benchmarks/validation30-public-lock.json', 'benchmarks/final30-selection.json',
                 'benchmarks/reselected20-acceptance.json',
                 'examples/README.md', 'examples/run_examples.py',
                 'evaluation/README.md', 'evaluation/validation30-results.json',
                 'evaluation/development40-summary.json', 'evaluation/release-checks.json']:
        yield ROOT / name
    for name in ['patchlab', 'tests', 'examples/traces/live', 'evaluation/runtime',
                 'benchmarks/requests-network', 'benchmarks/test-runtime']:
        for base, dirs, files in os.walk(ROOT / name):
            dirs[:] = [d for d in dirs if d not in EXCLUDED]
            for filename in files:
                p = Path(base) / filename
                if p.suffix not in {'.pyc', '.pyo'}:
                    yield p


def submission_file(source):
    relative = source.relative_to(ROOT)
    name = relative.as_posix()
    if name == 'docs/reports/PatchLab_Final_Report_EN_Illustrated.pdf':
        return Path('Final_Report.pdf'), source.read_bytes()
    if name == 'docs/reports/historical40-index.csv':
        return Path('evaluation/development40-results.csv'), source.read_bytes()
    data = source.read_bytes()
    if name == 'README.md':
        text = data.decode('utf-8')
        navigation = '''## Start here

| Purpose | File or directory |
| --- | --- |
| Final report | `Final_Report.pdf` (the only report) |
| Run the application | `start.cmd` on Windows; `bash start.command` on macOS |
| Run the three required examples | `examples/README.md` |
| Actual example traces | `examples/traces/live/` (failure policy is explicitly scripted) |
| Experiment results and replay instructions | `evaluation/README.md` |
| AI-use declaration and prompts | `AI_USE_DECLARATION.md`, `ai_records/` |
| Source, checks and provenance | `patchlab/`, `tests/`, `THIRD_PARTY.md`, `RELEASE.json` |

'''
        text = text.replace('## Quick start\n', navigation + '## Quick start\n', 1)
        text = text.replace('See `docs/reports/Validation30_Report_EN.md` and `evaluation/` for per-task results and source hashes.',
                            'See `Final_Report.pdf` and `evaluation/` for per-task results and source hashes.')
        start = text.index('The final report is `docs/reports/')
        end = text.index('\n\n', start)
        text = text[:start] + ('The final report is `Final_Report.pdf`. Development prompts are in '
            '`ai_records/recoverable_project_prompts_en.md`; runtime prompts are separately exported '
            'in `ai_records/runtime_prompts.json`. The package contains the runnable system, required '
            'examples, actual traces, evaluation materials and AI-use declaration. Editing drafts, '
            'duplicate reports, private credentials and historical development task copies are excluded.') + text[end:]
        data = text.encode('utf-8')
    elif name == 'examples/README.md':
        text = data.decode('utf-8').replace('`traces/offline/` contains actual deterministic runs. ',
            'The default command generates fresh deterministic traces in the requested output directory. ')
        data = text.encode('utf-8')
    elif name == 'THIRD_PARTY.md':
        text = data.decode('utf-8').replace('QuixBugs supplies the small development tasks under `examples/quixbugs/`:',
            'QuixBugs supplied small development tasks (historical task copies are not bundled in this minimal submission):')
        data = text.encode('utf-8')
    elif name == 'evaluation/README.md':
        text = data.decode('utf-8')
        text = text.replace(' `validation30-results.csv` is the tabular export; `completion.json` confirms the completed cohort.', '')
        text = text.replace('The English result discussion is in `docs/reports/Validation30_Report_EN.md`.',
            'The result discussion and tables are in `Final_Report.pdf` at the submission root.')
        text = text.replace('`docs/reports/PatchLab_Final_Report_EN_Illustrated.pdf`', '`Final_Report.pdf`')
        text = text.replace('`docs/reports/historical40-index.json`', '`development40-results.csv`')
        data = text.encode('utf-8')
    elif name == 'benchmarks/requests-network/README.md':
        text = data.decode('utf-8')
        start = text.index('The final local grading used')
        end = text.index('\n\n```sh', start)
        text = text[:start] + ('Historical development grading used SWE-bench 5.0.2. '
            'This directory preserves its environment adapter and tested compatibility helpers. '
            'Large historical audit logs and image binaries are omitted. The submitted thirty-task '
            'scoring adapter and replay requirements are documented in `evaluation/README.md`.') + text[end:]
        data = text.encode('utf-8')
    return relative, data


def validate(path, data):
    if re.search(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', str(path)):
        raise ValueError(f'Non-English filename: {path}')
    if path.suffix in TEXT or path.name.startswith('Dockerfile'):
        text = data.decode('utf-8')
        inspected = text
        if path.suffix == '.json':
            try:
                inspected = str(json.loads(text))
            except json.JSONDecodeError:
                # Upstream QuixBugs fixtures use JSON Lines with a .json suffix.
                inspected = str([json.loads(line) for line in text.splitlines() if line.strip()])
        elif path.suffix == '.jsonl':
            inspected = str([json.loads(line) for line in text.splitlines() if line.strip()])
        if re.search(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', inspected):
            raise ValueError(f'Chinese text in submission file: {path}')
        if re.search(r'\bsk-[A-Za-z0-9_-]{20,}\b', inspected):
            raise ValueError(f'Possible credential in submission file: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='PatchLab_Group45_Submission')
    parser.add_argument('--replace', action='store_true', help='Rebuild this named ZIP from selected files without deleting local files.')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.name):
        raise ValueError('Use an ASCII release name without path separators.')
    target = ROOT / 'delivery' / args.name
    target.mkdir(parents=True, exist_ok=args.replace)
    records = {}
    for source in sorted(set(selected_files())):
        relative, data = submission_file(source)
        validate(relative, data)
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        records[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    manifest = {'release': args.name, 'built_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'Minimal English final report and runnable source submission',
                'language_check': 'No CJK ideographs in filenames or text; JSON escapes decoded',
                'excluded': ['private keys and provider configuration', 'Git metadata',
                             'private Chinese review drafts', 'historical raw runs',
                             'gold patches and withheld tests', 'virtual environments'],
                'sha256': records}
    (target / 'RELEASE.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    archive = target.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w' if args.replace else 'x', zipfile.ZIP_DEFLATED) as stream:
        for relative in sorted([*records, 'RELEASE.json']):
            stream.write(target / relative, Path(args.name) / relative)
    print(json.dumps({'directory': str(target), 'zip': str(archive), 'files': len(records) + 1,
                      'bytes': archive.stat().st_size}, indent=2))


if __name__ == '__main__':
    main()
