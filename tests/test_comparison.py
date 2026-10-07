from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from unittest.mock import patch

import test_rulebisect as fixtures
from rulebisect.cli import main
from rulebisect.comparison import Comparison
from rulebisect.history import history, latest_report


class ComparisonTests(unittest.TestCase):
    setUp = fixtures.IntegrationTests.setUp
    tearDown = fixtures.IntegrationTests.tearDown

    def comparison(self, text='', **options):
        candidate = self.root / 'proposed'
        candidate.mkdir(exist_ok=True)
        (candidate / 'AGENTS.md').write_text(text)
        return Comparison(self.repo, self.config, self.root / 'comparison', None,
                          2, options.pop('max_runs', 12), 10, candidate,
                          runner=options.pop('runner', [sys.executable, 'simulator.py']), **options)

    def test_improvement_and_regression_are_not_hidden_by_average(self):
        (self.repo / 'legacy.py').write_text('import json\nfrom pathlib import Path\nraise SystemExit(0 if json.loads(Path("result.json").read_text())["format"] == "legacy" else 1)')
        self.config['cases'] = [{'id': 'modern'}, {'id': 'legacy', 'oracle': 'legacy.py'}]
        original = (self.repo / 'AGENTS.md').read_bytes()
        exp = self.comparison()
        report = exp.execute()
        self.assertEqual(report['status'], 'regressions_observed')
        self.assertEqual([c['verdict'] for c in report['cases']], ['improvement', 'regression'])
        self.assertEqual(len(report['trials']), 8)
        self.assertEqual([t['arm'] for t in report['trials'][:4]], ['baseline', 'candidate', 'candidate', 'baseline'])
        self.assertEqual((self.repo / 'AGENTS.md').read_bytes(), original)
        self.assertFalse((self.repo / 'result.json').exists())
        page = (exp.out / 'report.html').read_text()
        self.assertIn('回退 / Regression', page)
        self.assertIn('cases/modern/candidate/trials/0001/verify.log', page)
        self.assertIn('after/result.json', page)
        self.assertIn('modern', (exp.out / 'report.md').read_text())
        self.assertTrue(all('legacy.py' in child.protected for child in exp.experiments.values()))

    def test_candidate_passes_without_claiming_causality(self):
        report = self.comparison().execute()
        self.assertEqual(report['status'], 'no_regressions_observed')
        self.assertEqual(report['cases'][0]['verdict'], 'improvement')
        self.assertEqual(report['cases'][0]['candidate']['pass'], 2)
        self.assertTrue((self.root / 'comparison/proposed/AGENTS.md').is_file())
        self.assertIn('Not a guarantee', report['message'])

    def test_both_failed_is_not_a_validated_fix(self):
        report = self.comparison(text=(self.repo / 'AGENTS.md').read_text()).execute()
        self.assertEqual(report['status'], 'candidate_failed')
        self.assertEqual(report['cases'][0]['verdict'], 'unchanged_fail')

    def test_plan_has_no_model_calls_or_artifacts(self):
        exp = self.comparison()
        with patch('rulebisect.experiment.run_process', side_effect=AssertionError('must not execute')):
            result = exp.prepare()
        self.assertEqual(result['required_calls'], 4)
        self.assertEqual(result['model_calls'], 0)
        self.assertFalse(exp.out.exists())

    def test_underfunded_suite_is_rejected_before_calling_codex(self):
        self.config['cases'] = [{'id': 'one'}, {'id': 'two'}]
        exp = self.comparison(max_runs=4)
        with self.assertRaisesRegex(ValueError, 'needs 8 calls'):
            exp.prepare()
        self.assertFalse(exp.out.exists())

    def test_duplicate_or_unsafe_ids_and_invalid_tokens_are_rejected(self):
        for cases in ([{'id': '../escape'}], [{'id': 'same'}, {'id': 'same'}], [{'id': 'Modern'}, {'id': 'modern'}], [{'id': 'CON'}], [{'id': 'task', 'model': 'other'}]):
            self.config['cases'] = cases
            with self.assertRaises(ValueError):
                self.comparison().prepare()
        self.config.pop('cases')
        with self.assertRaisesRegex(ValueError, 'max-tokens'):
            self.comparison(max_tokens='bad').prepare()

    def test_setup_error_counts_attempt_but_stops_agent(self):
        self.config['setup'] = ['{python}', '-c', 'raise SystemExit(2)']
        report = self.comparison().execute()
        self.assertEqual(report['status'], 'inconclusive')
        self.assertEqual(len(report['trials']), 1)
        self.assertTrue(report['trials'][0]['agent']['skipped'])

    def test_mixed_observations_are_inconclusive(self):
        from rulebisect.runner import run_process
        calls = 0
        def noisy(argv, workspace, log, timeout, stdin=None):
            nonlocal calls
            if log.name == 'verify.log':
                calls += 1
                log.write_text('simulated mixed observations')
                return {'exit_code': 0 if calls == 1 else 1}
            return run_process(argv, workspace, log, timeout, stdin)
        with patch('rulebisect.experiment.run_process', side_effect=noisy):
            report = self.comparison().execute()
        self.assertEqual(report['status'], 'inconclusive')
        self.assertEqual(report['cases'][0]['baseline']['outcome'], 'unstable')
        self.assertEqual(report['cases'][0]['verdict'], 'pending')

    def test_token_cap_is_shared_between_arms(self):
        exp = self.comparison(max_tokens=1)
        exp.prepare()
        baseline = exp.experiments['task', 'baseline']
        original = baseline.trial
        def trial(ids, phase):
            record = original(ids, phase)
            record['codex'] = {'reported_usage': [{'input_tokens': 10, 'output_tokens': 1}]}
            return record
        with patch.object(Comparison, 'prepare', return_value={}), patch.object(baseline, 'trial', side_effect=trial):
            report = exp.execute()
        self.assertEqual(len(report['trials']), 1)
        self.assertEqual(report['status'], 'inconclusive')

    def test_cli_compare_plan_and_history_latest(self):
        exp = self.comparison()
        config_path = self.repo / '.rulebisect.json'
        config_path.write_text(json.dumps(self.config))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['compare', '--repo', str(self.repo), '--candidate', str(exp.candidate), '--plan'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['required_calls'], 6)
        root = self.repo.parent / '.rulebisect-runs' / self.repo.name
        for name, kind, status, timestamp in [('old', 'reduction', 'interrupted', '2026-10-06'), ('new', 'comparison', 'no_regressions_observed', '2026-10-07')]:
            directory = root / name
            directory.mkdir(parents=True)
            (directory / 'report.json').write_text(json.dumps({'kind': kind, 'status': status, 'created_at': timestamp, 'runner': 'codex', 'trials': [{}]}))
        broken = root / 'broken'
        broken.mkdir()
        (broken / 'report.json').write_text('invalid json')
        self.assertEqual(len(history(self.repo)['runs']), 2)
        self.assertEqual(len(history(self.repo)['warnings']), 1)
        self.assertEqual(latest_report(self.repo).name, 'new')
        self.assertEqual(latest_report(self.repo, resumable=True).name, 'old')

    def test_source_change_during_suite_preparation_is_rejected(self):
        from rulebisect.experiment import Experiment
        original = Experiment.prepare
        def prepare(exp, **kwargs):
            result = original(exp, **kwargs)
            if exp.out.name == 'baseline':
                (self.repo / 'simulator.py').write_text('changed during preparation')
            return result
        exp = self.comparison()
        with patch.object(Experiment, 'prepare', prepare), self.assertRaisesRegex(ValueError, 'Source changed'):
            exp.prepare()
        self.assertFalse(exp.out.exists())

    def test_interruption_retains_started_attempt(self):
        exp = self.comparison()
        with patch('rulebisect.experiment.run_process', side_effect=KeyboardInterrupt):
            report = exp.execute()
        self.assertEqual(report['status'], 'interrupted')
        self.assertEqual(len(report['trials']), 1)
        self.assertEqual(report['trials'][0]['state'], 'started')

    def test_draft_preserves_original_and_refuses_overwrite(self):
        from rulebisect.setup import draft_instructions
        original = (self.repo / 'AGENTS.md').read_bytes()
        target = self.root / 'draft'
        draft_instructions(self.repo, target)
        self.assertEqual((target / 'AGENTS.md').read_bytes(), original)
        (target / 'AGENTS.md').write_text('editable proposed rule')
        self.assertEqual((self.repo / 'AGENTS.md').read_bytes(), original)
        with self.assertRaises(ValueError):
            draft_instructions(self.repo, target)

    def test_draft_invalid_path_has_no_partial_output(self):
        from rulebisect.setup import draft_instructions
        (self.repo / '.rulebisect.json').write_text(json.dumps({'instructions': ['AGENTS.md', '../outside']}))
        target = self.root / 'draft'
        with self.assertRaises(ValueError):
            draft_instructions(self.repo, target)
        self.assertFalse(target.exists())

    def test_verifier_generated_files_are_not_agent_changes(self):
        (self.repo / 'verify.py').write_text('from pathlib import Path\nPath("verifier-output.txt").write_text("check output")\nraise SystemExit(0)')
        report = self.comparison().execute()
        self.assertTrue(all('verifier-output.txt' not in t['changed_files'] for t in report['trials']))
