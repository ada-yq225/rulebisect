"""Exercise the installed package from outside the source checkout; no model calls."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).resolve() / 'examples' / 'instruction-regression'
with tempfile.TemporaryDirectory(prefix='rulebisect-installed-workflow-') as directory:
    root = Path(directory)
    repo = root / 'repo'
    repo.mkdir()
    for name in ('AGENTS.md', 'labels.py', 'compatibility.py', 'verify_modern.py', 'verify_legacy.py', '.gitignore'):
        shutil.copy2(source / name, repo / name)
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    def cli(arguments, answers=None):
        result = subprocess.run([sys.executable, '-m', 'rulebisect', *arguments, '--repo', str(repo)],
                                cwd=root, input=answers, text=True, capture_output=True, check=True)
        print(result.stdout)
        return result.stdout
    cli(['init', '--wizard'], 'Implement normalize_label in labels.py.\npython verify_modern.py\n\n\n')
    cli(['case', 'add', 'legacy', '--task', 'Implement the compatibility contract.', '--oracle', 'verify_legacy.py'])
    cases = json.loads(cli(['case', 'list', '--json']))
    assert [case['id'] for case in cases] == ['task', 'legacy']
    cli(['check', '--all', '--out', str(root / 'checks')])
    report = json.loads((root / 'checks' / 'report.json').read_text(encoding='utf-8'))
    assert report['status'] == 'checks_completed'
    assert [case['outcome'] for case in report['cases']] == ['fail', 'fail']
    assert not report['trials'] and report['runner'] == 'verifier_only'
    cli(['draft', '--out', str(root / 'proposed')])
    plan = json.loads(cli(['compare', '--proposed', str(root / 'proposed'), '--cases', 'legacy', '--plan']))
    assert plan['required_calls'] == 6 and plan['model_calls'] == 0
    assert plan['case_selection']['omitted'] == ['task']
    cli(['case', 'remove', 'legacy'])
    assert len(json.loads(cli(['case', 'list', '--json']))) == 1
print('Installed guided workflow passed; no Codex/model calls.')
