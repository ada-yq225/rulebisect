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
