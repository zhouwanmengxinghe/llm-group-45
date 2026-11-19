"""Build an English-only, credential-free source snapshot with a hash manifest."""
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
    for name in ['README.md', 'HANDOFF.md', 'AI_USE_DECLARATION.md', 'THIRD_PARTY.md',
                 'bootstrap.py', 'start.cmd', 'start.command', 'requirements-dev.txt',
                 'pytest.ini', '.gitignore', '.gitattributes', 'configs/model.example.toml',
                 'docs/reports/Validation30_Report_EN.md',
                 'docs/reports/PatchLab_Final_Report_EN_Illustrated.docx',
                 'docs/reports/PatchLab_Final_Report_EN_Illustrated.pdf',
                 'docs/reports/PatchLab_Final_Report_EN_Illustrated.md',
                 'docs/reports/translation-provenance.json',
                 'docs/reports/historical40-index.json', 'docs/reports/historical40-index.csv',
                 'docs/reports/figures/architecture_en.png', 'docs/reports/figures/architecture_en.svg',
                 'docs/reports/figures/repair_loop_en.png', 'docs/reports/figures/repair_loop_en.svg',
                 'ai_records/recoverable_project_prompts_en.md', 'ai_records/runtime_prompts.json',
                 'benchmarks/validation30-public-lock.json', 'benchmarks/final30-selection.json',
                 'benchmarks/reselected20-acceptance.json']:
        yield ROOT / name
    for name in ['patchlab', 'tests', 'examples', 'docker', 'evaluation',
                 'scripts', 'benchmarks/requests-network', 'benchmarks/test-runtime']:
        for base, dirs, files in os.walk(ROOT / name):
            dirs[:] = [d for d in dirs if d not in EXCLUDED]
            for filename in files:
                p = Path(base) / filename
                if p.suffix not in {'.pyc', '.pyo'}:
                    yield p


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
    parser.add_argument('--name', default='PatchLab_Group45_Submission_20261119')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.name):
        raise ValueError('Use an ASCII release name without path separators.')
    target = ROOT / 'delivery' / args.name
    target.mkdir(parents=True, exist_ok=False)
    records = {}
    for source in sorted(set(selected_files())):
        relative = source.relative_to(ROOT)
        data = source.read_bytes()
        validate(relative, data)
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        records[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    manifest = {'release': args.name, 'built_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'English final report and runnable source submission snapshot',
                'language_check': 'No CJK ideographs in filenames or text; JSON escapes decoded',
                'excluded': ['private keys and provider configuration', 'Git metadata',
                             'private Chinese review drafts', 'historical raw runs',
                             'gold patches and withheld tests', 'virtual environments'],
                'sha256': records}
    (target / 'RELEASE.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    archive = target.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as stream:
        for path in sorted(target.rglob('*')):
            if path.is_file():
                stream.write(path, Path(args.name) / path.relative_to(target))
    print(json.dumps({'directory': str(target), 'zip': str(archive), 'files': len(records) + 1,
                      'bytes': archive.stat().st_size}, indent=2))


if __name__ == '__main__':
    main()
