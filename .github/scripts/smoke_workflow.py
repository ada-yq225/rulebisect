"""Exercise the installed package from outside the source checkout; no model calls."""
import json
from pathlib import Path
import re
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

with tempfile.TemporaryDirectory(prefix='rulebisect-installed-assertions-') as directory:
    root = Path(directory)
    repo = root / 'private-repository'
    repo.mkdir()
    output_name = 'private-result.json'
    initial_task = 'private-task-initial: produce the intended structured output.'
    case_id = 'private-case-second'
    second_task = 'private-task-second: use the intended output format.'
    expected_name = 'private-expected-name'
    (repo / 'AGENTS.md').write_text('Use the requested structured output.\n', encoding='utf-8')
    (repo / output_name).write_text(
        json.dumps({'format': 'legacy', 'items': [{'name': 'wrong', 'enabled': False}]}),
        encoding='utf-8')
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)

    def assertion_cli(arguments, answers=None, expected_exit=0):
        command = [sys.executable, '-m', 'rulebisect', *arguments]
        if arguments[0] != 'share':
            command += ['--repo', str(repo)]
        result = subprocess.run(command, cwd=root, input=answers,
                                text=True, capture_output=True)
        assert result.returncode == expected_exit, (result.returncode, result.stdout, result.stderr)
        print(result.stdout)
        return result.stdout

    literal = json.dumps({'name': expected_name, 'enabled': True})
    assertion_cli(['init', '--wizard'],
                  f'{initial_task}\n:json\n{output_name}\n/items/0\n{literal}\n\n\n')
    checks_path = root / 'private-acceptance.json'
    checks_path.write_text(json.dumps([
        {'type': 'json_equals', 'path': output_name, 'pointer': '/format', 'value': 'modern'}
    ]), encoding='utf-8')
    assertion_cli(['case', 'add', case_id, '--task', second_task,
                   '--assertions', str(checks_path)])
    cases = json.loads(assertion_cli(['case', 'list', '--json']))
    assert [case['id'] for case in cases] == ['task', case_id]
    saved_verifiers = {case['oracle']: (repo / case['oracle']).read_bytes() for case in cases}
    # Criteria are compiled into standalone verifiers, not reread from this input.
    checks_path.write_text('[]\n', encoding='utf-8')
    evidence = root / 'private-evidence'
    assertion_cli(['check', '--all', '--out', str(evidence)])
    report = json.loads((evidence / 'report.json').read_text(encoding='utf-8'))
    assert report['status'] == 'checks_completed' and report['runner'] == 'verifier_only'
    assert [case['outcome'] for case in report['cases']] == ['fail', 'fail']
    assert not report['trials']
    assert all((repo / name).read_bytes() == source for name, source in saved_verifiers.items())

    summary_path = root / 'public-summary.html'
    assertion_cli(['share', str(evidence), '--out', str(summary_path)])
    page = summary_path.read_text(encoding='utf-8')
    encoded = re.search(r'<script type="application/json" id="rulebisect-summary">(.*?)</script>',
                        page, re.S)
    assert encoded, 'Missing machine-readable public summary'
    summary = json.loads(encoded.group(1))
    assert summary['format'] == 'rulebisect-public-summary-v1'
    assert summary['kind'] == 'checks' and summary['source'] == 'verifier_only'
    assert summary['status'] == 'checks_completed' and summary['executions'] == 0
    assert summary['cases'] == 2 and summary['checks']['fail'] == 2
    for private in (initial_task, second_task, case_id, output_name, expected_name,
                    str(repo), str(evidence), str(checks_path), root.name):
        assert private not in page, f'Private fixture text leaked into summary: {private}'

    # Invalid acceptance criteria fail before changing configuration or writing an oracle.
    original_config = (repo / '.rulebisect.json').read_bytes()
    malformed = root / 'malformed-acceptance.json'
    malformed.write_text(json.dumps([
        {'type': 'file_matches', 'path': output_name, 'pattern': '['}
    ]), encoding='utf-8')
    assertion_cli(['case', 'add', 'malformed', '--task', 'Reject this invalid criterion.',
                   '--assertions', str(malformed)], expected_exit=2)
    assert (repo / '.rulebisect.json').read_bytes() == original_config
    assert not (repo / '.rulebisect' / 'checks' / 'malformed.py').exists()
print('Installed no-code assertions and sharing workflow passed; no Codex/model calls.')
