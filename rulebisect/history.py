"""Read lightweight summaries without walking raw logs or invoking Codex."""
from __future__ import annotations

import json
from pathlib import Path


def history(repo: Path):
    root = repo.resolve().parent / '.rulebisect-runs' / repo.name
    records, warnings = [], []
    if root.is_dir() and not root.is_symlink():
        for directory in root.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            path = directory / 'report.json'
            if not path.is_file() or path.is_symlink():
                continue
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(value, dict) or not isinstance(value.get('created_at'), str) or not isinstance(value.get('status'), str) or not isinstance(value.get('trials'), list):
                    raise ValueError('missing or invalid report timestamp/status/trials')
                records.append({'path': str(directory), 'created_at': value['created_at'],
                                'kind': value.get('kind', 'reduction'), 'status': value.get('status'),
                                'runner': value.get('runner'), 'runs': len(value.get('trials', [])), 'model': value.get('requested_model')})
            except (ValueError, OSError, TypeError) as error:
                warnings.append(f'{directory.name}: {error}')
    return {'runs': sorted(records, key=lambda record: (record['created_at'], record['path']), reverse=True), 'warnings': warnings,
            'root': str(root), 'model_calls': 0}


def latest_report(repo, resumable=False):
    records = history(repo)['runs']
    if resumable:
        records = [r for r in records if r['kind'] == 'reduction' and r['status'] not in ('pending', 'running', 'check_only') and r['runner'] == 'codex' and r['runs']]
    if not records:
        raise ValueError('No matching evidence in the default history directory; provide an explicit path for --out runs')
    return Path(records[0]['path'])
