"""A completed prefix can be reused once, with its original evidence intact."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import test_rulebisect as fixtures
from rulebisect.comparison import Comparison
from rulebisect.comparison_resume import read_prior_report
from rulebisect.experiment import Experiment
from rulebisect.runner import run_process


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        fixtures.IntegrationTests.setUp(self)
        self.root = self.root.resolve()
        self.repo = self.repo.resolve()
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'baseline')
        self.commit = self.git('rev-parse', 'HEAD')
        (self.repo / 'AGENTS.md').write_text('', encoding='utf-8')
        self.calls = []
        self.cli_version = 'fixture CLI 1'
        original_prepare = Experiment.prepare

        def offline_prepare(exp, *, check_codex, **kwargs):
            # Use the native Codex report format, with both preflight and the
            # agent process replaced. The repository verifier still runs.
            original_prepare(exp, check_codex=False, **kwargs)
            if check_codex:
                exp.report['codex_version'] = self.cli_version

        def offline_process(argv, cwd, log, timeout, stdin=None):
            if stdin is None:
                return run_process(argv, cwd, log, timeout)
            self.calls.append((cwd / 'AGENTS.md').read_bytes())
            result = run_process([sys.executable, 'simulator.py'], cwd, log, timeout)
            event = {'model': 'fixture', 'usage': {'input_tokens': 80, 'output_tokens': 8, 'cached_input_tokens': 60}}
            with log.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(event) + '\n')
            return result

        self.enterContext(patch.object(Experiment, 'prepare', offline_prepare))
        self.enterContext(patch('rulebisect.experiment.run_process', side_effect=offline_process))

    tearDown = fixtures.IntegrationTests.tearDown

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True).strip()

    def build(self, output='old', *, limit=100, old=None, **options):
        return Comparison(self.repo, self.config, self.root / output, options.pop('model', 'fixture'), 2,
                          options.pop('max_runs', 4), 10, base_ref=options.pop('base_ref', self.commit),
                          max_tokens=limit, continue_from=old, **options)

    def stopped(self, *, legacy=False, **kwargs):
        comparison = self.build(base_ref='HEAD', **kwargs)
        if legacy:
            with patch('rulebisect.comparison.__version__', '0.11.0'), patch('rulebisect.experiment.__version__', '0.11.0'):
                report = comparison.execute()
            report.pop('stop_reason')
            (comparison.out / 'report.json').write_text(json.dumps(report), encoding='utf-8')
        else:
            report = comparison.execute()
            self.assertEqual(report['stop_reason'], 'token_cap')
        self.assertEqual(report['status'], 'inconclusive')
        return comparison.out

    def assert_rejected(self, comparison, pattern):
        calls = len(self.calls)
        with self.assertRaisesRegex(ValueError, pattern):
            comparison.execute()
        self.assertEqual(len(self.calls), calls)
        self.assertFalse(comparison.out.exists())

    def tree_hashes(self, root):
        return {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.rglob('*') if path.is_file()}

    def test_legacy_continuation_reuses_two_trials_with_original_logs(self):
        old = self.stopped(legacy=True)
        hashes = self.tree_hashes(old)
        continued = self.build('new', limit=400, old=old / 'report.json')
        plan = continued.prepare()
        self.assertEqual(plan['model_calls'], 0)
        self.assertFalse(continued.out.exists())
        self.assertEqual(plan['continuation']['reused_trials'], 2)
        self.assertEqual(plan['continuation']['remaining_calls'], 2)
        self.assertEqual(plan['continuation']['reported_tokens_before'], 176)
        report = continued.execute()
        self.assertEqual(report['status'], 'no_regressions_observed')
        self.assertNotIn('stop_reason', report)
        self.assertEqual(report['cases'][0]['verdict'], 'improvement')
        self.assertEqual([r['arm'] for r in report['trials']], ['baseline', 'candidate', 'candidate', 'baseline'])
        self.assertEqual([bool(data) for data in self.calls], [True, False, False, True])
        self.assertEqual(report['usage_totals'], {'input_tokens': 320, 'output_tokens': 32,
                                                  'cached_input_tokens': 240, 'reported_runs': 4})
        self.assertEqual(self.tree_hashes(old), hashes)
        self.assertEqual(report['continuation']['report_sha256'], hashes[Path('report.json')])
        self.assertEqual((continued.out / 'previous-report.json').read_bytes(), (old / 'report.json').read_bytes())
        receipt = json.loads((continued.out / 'continuation.json').read_text())
        for relative, sha in receipt['source_files_sha256'].items():
            self.assertEqual(sha, hashes[Path(relative)])
        for index, trial in enumerate(report['trials']):
            artifact = Path(trial['artifacts'])
            self.assertTrue((continued.out / artifact / 'trial.json').is_file())
            if index < 2:
                self.assertEqual(self.tree_hashes(old / artifact), self.tree_hashes(continued.out / artifact))

    def test_second_continuation_uses_cumulative_budget_and_remaining_order(self):
        first = self.stopped()
        middle = self.build('middle', limit=200, old=first)
        result = middle.execute()
        self.assertEqual(result['stop_reason'], 'token_cap')
        self.assertEqual(result['usage_totals']['reported_runs'], 3)
        end = self.build('final', limit=270, old=middle.out).execute()
        self.assertEqual(end['continuation']['reused_trials'], 3)
        self.assertEqual(end['usage_totals']['reported_runs'], 4)
        self.assertEqual(end['status'], 'no_regressions_observed')
        self.assertEqual(len(self.calls), 4)

    def test_prefix_spanning_cases_preserves_finished_case_and_setup_logs(self):
        self.config['cases'] = [{'id': 'first'}, {'id': 'second', 'task': 'another task'}]
        self.config['setup'] = ['{python}', '-c', 'print("setup")']
        old = self.stopped(limit=400, max_runs=8)
        continued = self.build('more', old=old, limit=800, max_runs=8)
        result = continued.execute()
        self.assertEqual(result['continuation']['reused_trials'], 5)
        self.assertEqual(result['continuation']['remaining_calls'], 3)
        self.assertEqual(result['usage_totals']['reported_runs'], 8)
        self.assertEqual([case['verdict'] for case in result['cases']], ['improvement', 'improvement'])
        self.assertEqual(len(self.calls), 8)
        for trial in result['trials'][:5]:
            setup_log = Path(trial['artifacts']) / 'setup.log'
            self.assertEqual((continued.out / setup_log).read_bytes(), (old / setup_log).read_bytes())

    def test_same_rules_in_different_commit_are_not_the_same_source(self):
        old = self.stopped()
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'another revision')
        self.assert_rejected(self.build('ref', old=old, limit=400, base_ref='HEAD'), 'source commit')
        self.assertEqual(self.build('exact', old=old, limit=400).prepare()['continuation']['reused_trials'], 2)

    def test_changed_scope_model_version_code_or_limits_stop_before_calls(self):
        old = self.stopped()
        for opts, error in [({'limit': 100}, 'previous cap'), ({'limit': 176}, '176'),
                            ({'model': 'other'}, 'requested_model'), ({'max_runs': 5}, 'inputs changed')]:
            with self.subTest(opts=opts):
                self.assert_rejected(self.build('rejected', old=old, **({'limit': 400} | opts)), error)
        self.cli_version = 'fixture CLI 2'
        self.assert_rejected(self.build('rejected', old=old, limit=400), 'codex_version')
        self.cli_version = 'fixture CLI 1'
        with patch.dict(self.config, {'task': 'different task'}):
            self.assert_rejected(self.build('rejected', old=old, limit=400), 'inputs changed')
        (self.repo / 'verify.py').write_text('raise SystemExit(0)')
        self.assert_rejected(self.build('rejected', old=old, limit=400), 'inputs changed')

    def test_incomplete_unsafe_or_unaccounted_evidence_stops_before_calls(self):
        old = self.stopped()
        relative = Path('cases/task/candidate/trials/0001')
        files = [(Path('report.json'), lambda doc: doc['trials'][1].update(artifacts='../other'), 'scheduled prefix'),
                 (Path('report.json'), lambda doc: doc.update(stop_reason='interrupted'), 'between trials'),
                 (Path('report.json'), lambda doc: doc['usage_totals'].update(input_tokens=0), 'usage totals'),
                 (relative / 'trial.json', lambda doc: doc.update(state='started'), 'trial.json'),
                 (Path('cases/task/candidate/report.json'), lambda doc: doc['trials'].append({}), 'unaccounted')]
        for path, change, error in files:
            with self.subTest(path=path, error=error):
                target = old / path
                saved = target.read_bytes()
                doc = json.loads(saved)
                change(doc)
                target.write_text(json.dumps(doc))
                self.assert_rejected(self.build('rejected', old=old, limit=400), error)
                target.write_bytes(saved)
        extra = old / relative.parent / '0002'
        extra.mkdir()
        self.assert_rejected(self.build('rejected', old=old, limit=400), 'unaccounted trial directory')
        extra.rmdir()
        log = old / relative / 'agent.log'
        saved = log.read_bytes()
        log.write_text('different log\n')
        self.assert_rejected(self.build('rejected', old=old, limit=400), 'Codex log')
        log.write_bytes(saved)
        (old / relative / 'verify.log').unlink()
        self.assert_rejected(self.build('rejected', old=old, limit=400), 'missing evidence')

    def test_nested_output_and_excessively_nested_json_fail_offline(self):
        old = self.stopped()
        self.assert_rejected(self.build('old/nested', old=old, limit=400), 'outside the previous')
        (old / 'report.json').write_text('{"deep":' + '[' * 1500 + '0' + ']' * 1500 + '}')
        with self.assertRaisesRegex(ValueError, 'invalid JSON|deeply'):
            read_prior_report(old)

    def test_symlinked_source_and_log_rejected(self):
        old = self.stopped()
        alias = self.root / 'alias'
        try:
            alias.symlink_to(old, target_is_directory=True)
        except OSError:
            self.skipTest('Symlinks unavailable')
        self.assert_rejected(self.build('rejected', old=alias, limit=400), 'symlink')
        log = old / 'cases/task/candidate/trials/0001/agent.log'
        target = self.root / 'outside.log'
        log.rename(target)
        log.symlink_to(target)
        self.assert_rejected(self.build('rejected', old=old, limit=400), 'symlink')

    def test_two_simultaneous_continuations_claim_one_output(self):
        old = self.stopped()
        barrier = threading.Barrier(2)
        original = Comparison.prepare

        def prepare(comp, *args, **kwargs):
            result = original(comp, *args, **kwargs)
            barrier.wait(timeout=10)
            return result

        def execute():
            try:
                return self.build('shared', old=old, limit=400).execute()['status']
            except ValueError as error:
                return str(error)

        with patch.object(Comparison, 'prepare', prepare), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: execute(), range(2)))
        self.assertIn('no_regressions_observed', results)
        self.assertTrue(any('already in use' in result for result in results))
        self.assertEqual(len(self.calls), 4)
