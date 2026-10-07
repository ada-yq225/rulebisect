from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

import test_rulebisect as base_tests
from rulebisect.cli import main
from rulebisect.core import split_rules
from rulebisect.experiment import Experiment
from rulebisect.setup import CONFIG_NAME, discover_instructions, init_config


class FeatureTests(unittest.TestCase):
    setUp = base_tests.IntegrationTests.setUp
    tearDown = base_tests.IntegrationTests.tearDown
    experiment = base_tests.IntegrationTests.experiment

    def test_init_check_wrapper_and_protected_tests(self):
        (self.repo / 'test_behavior.py').write_text('raise SystemExit(0)')
        subprocess.run(['git', '-c', 'core.fsmonitor=false', 'add', 'test_behavior.py'], cwd=self.repo, check=True)
        config_path = init_config(self.repo, 'Concrete task', 'python -c "raise SystemExit(0)"', 'selected-model')
        config = json.loads(config_path.read_text())
        self.assertEqual(config['instructions'], ['AGENTS.md'])
        self.assertIn('test_behavior.py', config['protected_files'])
        self.assertEqual(config['model'], 'selected-model')
        result = Experiment(self.repo, config, self.root / 'check', None, 2, 8, 10).check_initial()
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(json.loads((self.root / 'check/report.json').read_text())['trials'], [])

    def test_init_refuses_overwrite(self):
        target = init_config(self.repo, 'task', None, None, 'verify.py')
        original = target.read_bytes()
        with self.assertRaises(ValueError):
            init_config(self.repo, 'another task', None, None, 'verify.py')
        self.assertEqual(target.read_bytes(), original)

    def test_init_rejects_missing_oracle_without_side_effects(self):
        with self.assertRaises(ValueError):
            init_config(self.repo, 'task', None, None, '../outside.py')
        self.assertFalse((self.repo / CONFIG_NAME).exists())

    def test_override_selection(self):
        (self.repo / 'AGENTS.override.md').write_text('Override rules')
        self.assertEqual(discover_instructions(self.repo), ['AGENTS.override.md'])

    def test_plan_has_no_artifacts_or_model_calls(self):
        init_config(self.repo, 'task', None, None, 'verify.py')
        output = self.root / 'unused-output'
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(['plan', '--repo', str(self.repo), '--out', str(output), '--json'])
        self.assertEqual(code, 0)
        data = json.loads(stdout.getvalue())
        self.assertEqual(data['model_calls'], 0)
        self.assertEqual(data['units'], 5)
        self.assertFalse(output.exists())

    def test_resume_reuses_search_but_refreshes_baselines(self):
        previous = self.experiment(max_runs=8).execute()
        self.assertEqual(previous['status'], 'inconclusive')
        exp = self.experiment(max_runs=100)
        exp.out = self.root / 'resumed'
        exp.resume_from = self.root / 'evidence'
        report = exp.execute()
        self.assertEqual(report['status'], 'observed_1_minimal')
        self.assertEqual(report['candidate'], [1, 3])
        self.assertEqual(report['trials'][:8], previous['trials'])
        self.assertEqual(sum(v['phase'] == 'full-baseline' for v in report['evaluations']), 2)
        search_ids = [tuple(v['ids']) for v in report['evaluations'] if v['phase'] == 'search']
        self.assertEqual(len(search_ids), len(set(search_ids)))

    def test_resume_rejects_changed_source_before_runner(self):
        self.experiment(max_runs=8).execute()
        (self.repo / 'simulator.py').write_text('raise SystemExit(0)')
        exp = self.experiment(max_runs=100)
        exp.out = self.root / 'resumed'
        exp.resume_from = self.root / 'evidence'
        with self.assertRaisesRegex(ValueError, 'snapshot_sha256'):
            exp.prepare()
        self.assertEqual(exp.report['trials'], [])

    def test_resume_rejects_changed_oracle_role(self):
        self.experiment(max_runs=8).execute()
        self.config['protected_files'] = []
        exp = self.experiment(max_runs=100)
        exp.out = self.root / 'resumed'
        exp.resume_from = self.root / 'evidence'
        with self.assertRaisesRegex(ValueError, 'protected_files'):
            exp.prepare()

    def test_token_limit_stops_between_calls(self):
        exp = self.experiment()
        exp.max_tokens = 1
        original = exp.trial
        def trial(ids, phase):
            record = original(ids, phase)
            record['codex'] = {'reported_usage': [{'input_tokens': 10, 'output_tokens': 1, 'cached_input_tokens': 8}]}
            return record
        exp.trial = trial
        report = exp.execute()
        self.assertEqual(report['status'], 'inconclusive')
        self.assertEqual(len(report['trials']), 1)
        self.assertEqual(report['usage_totals']['input_tokens'], 10)
        self.assertIn('token limit', report['message'])

    def test_section_units_preserve_structure(self):
        text = '# One\n\nFirst paragraph.\n\nSecond paragraph.\n\n## Two\n\n```md\n# Not a heading\n```\n'
        units = split_rules('AGENTS.md', text, mode='section')
        self.assertEqual(len(units), 2)
        self.assertEqual(''.join(r.text for r in units), text)
        self.assertEqual(units[1].line, 7)
        self.assertEqual(len(split_rules('AGENTS.md', text, mode='file')), 1)

    def test_code_diff_preserved_after_workspace_cleanup(self):
        (self.repo / 'labels.py').write_text('original\n')
        subprocess.run(['git', '-c', 'core.fsmonitor=false', 'add', 'labels.py'], cwd=self.repo, check=True)
        report = self.experiment(code='from pathlib import Path; Path("labels.py").write_text("changed\\n"); Path("result.json").write_text(\'{"format":"modern"}\')').execute()
        self.assertEqual(report['status'], 'not_reproduced')
        diff = (self.root / 'evidence/trials/0001/changes.diff').read_text()
        self.assertIn('-original', diff)
        self.assertIn('+changed', diff)
        self.assertEqual((self.repo / 'labels.py').read_text(), 'original\n')

    def test_invalid_budget_type_is_actionable(self):
        exp = self.experiment()
        exp.repeats = '3'
        with self.assertRaisesRegex(ValueError, 'integers'):
            exp.prepare()

    def test_interrupt_counts_attempt_and_keeps_log(self):
        from unittest.mock import patch
        exp = self.experiment()
        with patch('rulebisect.experiment.run_process', side_effect=KeyboardInterrupt):
            report = exp.execute()
        self.assertEqual(report['status'], 'interrupted')
        self.assertEqual(len(report['trials']), 1)
        self.assertEqual(report['trials'][0]['state'], 'started')
        self.assertTrue((self.root / 'evidence/trials/0001/trial.json').exists())

    def test_setup_creates_dependency_before_verifier_without_changing_original(self):
        self.config['setup'] = ['{python}', '-c', 'from pathlib import Path; Path("dependency.txt").write_text("ready")']
        (self.repo / 'verify.py').write_text('from pathlib import Path\nraise SystemExit(0 if Path("dependency.txt").read_text() == "ready" else 2)')
        exp = self.experiment()
        result = exp.check_initial()
        self.assertEqual(result['exit_code'], 0)
        self.assertFalse((self.repo / 'dependency.txt').exists())
        self.assertTrue((exp.out / 'setup.log').is_file())

    def test_setup_failure_never_invokes_agent(self):
        from unittest.mock import patch
        self.config['setup'] = ['{python}', '-c', 'raise SystemExit(7)']
        exp = self.experiment()
        from rulebisect.runner import run_process
        with patch('rulebisect.experiment.run_process', wraps=run_process) as process:
            report = exp.execute()
        self.assertEqual(process.call_count, 1)
        self.assertEqual(report['status'], 'inconclusive')
        self.assertTrue(report['trials'][0]['agent']['skipped'])
        self.assertEqual(report['trials'][0]['setup']['exit_code'], 7)

    def test_setup_mutating_instructions_is_rejected_before_agent(self):
        self.config['setup'] = ['{python}', '-c', 'from pathlib import Path; Path("AGENTS.md").write_text("changed")']
        report = self.experiment().execute()
        self.assertTrue(report['trials'][0]['agent']['skipped'])
        self.assertIn('AGENTS.md', report['trials'][0]['setup']['changed_files'])

    def test_new_deleted_and_ignored_files_are_recorded_correctly(self):
        (self.repo / 'removed.txt').write_text('before without newline')
        (self.repo / '.gitignore').write_text('ignored.txt\n')
        subprocess.run(['git', 'add', 'removed.txt', '.gitignore'], cwd=self.repo, check=True)
        self.config['setup'] = ['{python}', '-c', 'from pathlib import Path; Path("dependency.txt").write_text("ready")']
        report = self.experiment(code='from pathlib import Path; Path("removed.txt").unlink(); Path("new.py").write_text("created"); Path("ignored.txt").write_text("ignored"); Path("result.json").write_text(\'{"format":"modern"}\')').execute()
        changes = report['trials'][0]['file_changes']
        self.assertIn({'path': 'new.py', 'kind': 'added'}, changes)
        self.assertIn({'path': 'removed.txt', 'kind': 'deleted'}, changes)
        self.assertNotIn('dependency.txt', report['trials'][0]['changed_files'])
        self.assertNotIn('ignored.txt', report['trials'][0]['changed_files'])
        diff = (self.root / 'evidence/trials/0001/changes.diff').read_text()
        self.assertIn('+created', diff)
        self.assertIn('-before without newline', diff)
        self.assertIn('No newline at end of file', diff)
        self.assertTrue((self.repo / 'removed.txt').exists())
        self.assertFalse((self.repo / 'new.py').exists())

    def test_resume_rejects_changed_setup(self):
        self.experiment(max_runs=8).execute()
        self.config['setup'] = ['{python}', '-c', 'pass']
        exp = self.experiment(max_runs=100)
        exp.out = self.root / 'resumed'
        exp.resume_from = self.root / 'evidence'
        with self.assertRaisesRegex(ValueError, 'setup changed'):
            exp.prepare()

    def test_init_setup_parsing_and_no_shell(self):
        path = init_config(self.repo, 'task', None, None, 'verify.py', setup='python -c "print(123)"')
        self.assertEqual(json.loads(path.read_text())['setup'], ['{python}', '-c', 'print(123)'])
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'shell operators'):
            init_config(self.repo, 'task', None, None, 'verify.py', setup='npm ci && npm test')
        self.assertFalse(path.exists())

    def test_setup_argument_shape_rejected_before_artifacts(self):
        for setup in ('npm ci', [''], [3]):
            self.config['setup'] = setup
            exp = self.experiment()
            with self.assertRaisesRegex(ValueError, 'setup must be'):
                exp.prepare()
            self.assertFalse(exp.out.exists())

    @unittest.skipIf(sys.platform == 'win32', 'Symlinks require platform privileges')
    def test_internal_symlink_ancestor_is_rejected(self):
        (self.repo / 'actual').mkdir()
        (self.repo / 'actual/rules.md').write_text('Rules')
        (self.repo / 'alias').symlink_to(self.repo / 'actual', target_is_directory=True)
        self.config['instructions'] = ['alias/rules.md']
        with self.assertRaisesRegex(ValueError, 'Symlinks'):
            self.experiment().prepare()

    def test_setup_timeout_stops_before_agent(self):
        self.config['setup'] = ['{python}', '-c', 'import time; time.sleep(30)']
        exp = self.experiment()
        exp.timeout = 1
        report = exp.execute()
        self.assertTrue(report['trials'][0]['agent']['skipped'])
        self.assertEqual(report['status'], 'inconclusive')

    def test_large_unchanged_file_is_not_reported_as_modified(self):
        (self.repo / 'large.txt').write_text('a' * 250000)
        subprocess.run(['git', 'add', 'large.txt'], cwd=self.repo, check=True)
        report = self.experiment(code='from pathlib import Path; Path("result.json").write_text(\'{"format":"modern"}\')').execute()
        self.assertNotIn('large.txt', report['trials'][0]['changed_files'])
