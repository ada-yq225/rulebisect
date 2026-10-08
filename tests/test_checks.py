import contextlib
import io
import json
import subprocess
import unittest
from unittest.mock import patch

import test_rulebisect as fixtures
from rulebisect.checks import SuiteCheck
from rulebisect.comparison import Comparison, select_cases
from rulebisect.cli import main
from rulebisect.setup import CONFIG_NAME


class ChecksTests(unittest.TestCase):
    setUp = fixtures.IntegrationTests.setUp
    tearDown = fixtures.IntegrationTests.tearDown

    def make_config(self, codes=(0, 1)):
        config = dict(self.config)
        config['cases'] = []
        for index, code in enumerate(codes):
            name = f'case{index}'
            oracle = f'{name}.py'
            (self.repo / oracle).write_text(f'raise SystemExit({code})', encoding='utf-8')
            config['cases'].append({'id': name, 'oracle': oracle})
        return config

    def test_all_verifiers_and_initial_behavior_failures(self):
        config = self.make_config()
        before = {p.name: p.read_bytes() for p in self.repo.iterdir() if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()):
            report = SuiteCheck(self.repo, config, self.root / 'checks').execute()
        self.assertEqual(report['status'], 'checks_completed')
        self.assertEqual([c['outcome'] for c in report['cases']], ['pass', 'fail'])
        self.assertEqual(report['trials'], [])
        self.assertEqual(report['runner'], 'verifier_only')
        self.assertIsNone(report['requested_model'])
        self.assertEqual({p.name: p.read_bytes() for p in self.repo.iterdir() if p.is_file()}, before)
        for name in ('case0', 'case1'):
            child = json.loads((self.root / f'checks/cases/{name}/report.json').read_text(encoding='utf-8'))
            self.assertTrue(all(c['oracle'] in child['protected_files'] for c in config['cases']))
        html = (self.root / 'checks/report.html').read_text(encoding='utf-8')
        self.assertIn('cases/case1/report.html', html)
        self.assertIn('not invoked', html)
        self.assertNotIn('proposed.patch', html)

    def test_infrastructure_failure_continues_other_cases(self):
        with contextlib.redirect_stdout(io.StringIO()):
            report = SuiteCheck(self.repo, self.make_config((2, 0)), self.root / 'checks').execute()
        self.assertEqual(report['status'], 'checks_failed')
        self.assertEqual([c['outcome'] for c in report['cases']], ['error', 'pass'])

    def test_invalid_later_case_has_no_artifacts_or_commands(self):
        config = self.make_config()
        config['cases'][1]['oracle'] = 'missing.py'
        out = self.root / 'checks'
        with patch('rulebisect.experiment.run_process') as runner:
            with self.assertRaises(ValueError):
                SuiteCheck(self.repo, config, out).execute()
        runner.assert_not_called()
        self.assertFalse(out.exists())

    def test_each_verifier_uses_fresh_workspace(self):
        config = self.make_config((0, 0))
        (self.repo / 'case0.py').write_text('from pathlib import Path\nPath("marker.txt").write_text("one")', encoding='utf-8')
        (self.repo / 'case1.py').write_text('from pathlib import Path\nraise SystemExit(2 if Path("marker.txt").exists() else 0)', encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            report = SuiteCheck(self.repo, config, self.root / 'checks').execute()
        self.assertEqual(report['status'], 'checks_completed')
        self.assertFalse((self.repo / 'marker.txt').exists())

    def test_cli_all_and_subset_disclose_omissions(self):
        (self.repo / CONFIG_NAME).write_text(json.dumps(self.make_config()), encoding='utf-8')
        out = self.root / 'checks'
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(['check', '--repo', str(self.repo), '--all', '--cases', 'case1', '--out', str(out)])
        self.assertEqual(code, 0)
        report = json.loads((out / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['case_selection']['omitted'], ['case0'])
        self.assertIn('Partial suite', (out / 'report.html').read_text(encoding='utf-8'))
        self.assertIn('case0', (out / 'issue.md').read_text(encoding='utf-8'))
        self.assertFalse((out / 'cases/case0').exists())

    def test_filtered_comparison_exact_budget_and_invalid_selection(self):
        config = self.make_config()
        for names in ([], ['missing'], ['case0', 'case0']):
            with self.assertRaises(ValueError):
                select_cases(config, names)
        proposed = self.root / 'proposed'; proposed.mkdir()
        (proposed / 'AGENTS.md').write_text('new rules')
        selected = select_cases(config, ['case0'])
        plan = Comparison(self.repo, selected, self.root / 'comparison', None, 2, 4, 10, proposed).prepare()
        self.assertEqual(plan['required_calls'], 4)
        self.assertEqual(plan['case_selection']['omitted'], ['case1'])
        self.assertFalse((self.root / 'comparison').exists())
        self.assertEqual(len(config['cases']), 2)

    def test_filter_preserves_omitted_untracked_oracles_and_snapshot(self):
        config = self.make_config((0, 0))
        (self.repo / 'case0.py').write_text('from pathlib import Path\nraise SystemExit(0 if Path("case1.py").is_file() else 2)', encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            full = SuiteCheck(self.repo, select_cases(config), self.root / 'full').execute()
            subset = SuiteCheck(self.repo, select_cases(config, ['case0']), self.root / 'subset').execute()
        self.assertEqual(subset['status'], 'checks_completed')
        self.assertEqual(full['snapshot_sha256'], subset['snapshot_sha256'])
        self.assertIn('case1.py', subset['protected_files'])
