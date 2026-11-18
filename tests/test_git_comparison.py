"""Verify rule-only Git comparisons against frozen working-tree code."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rulebisect.comparison import Comparison
from rulebisect.experiment import Experiment
from rulebisect.revisions import read_revision


class GitComparisonTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.repo = self.root / 'project'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'user.name', 'Test Runner')
        self.git('config', 'user.email', 'test@example.invalid')
        self.rules = self.repo / 'AGENTS.md'
        self.rules.write_bytes(b'Keep spaces.\r\n')
        self.stable = self.repo / 'More rules.md'
        self.stable.write_bytes(b'Use the current input.\n')
        self.data = self.repo / 'input.txt'
        self.data.write_bytes(b'from old code')
        (self.repo / 'runner.py').write_bytes(
            b"from pathlib import Path\n"
            b"data = Path('input.txt').read_bytes()\n"
            b"keep = Path('AGENTS.md').read_bytes().startswith(b'Keep')\n"
            b"Path('result.txt').write_bytes(data if keep else data.strip())\n")
        (self.repo / 'verify.py').write_bytes(
            b"from pathlib import Path\n"
            b"raise SystemExit(0 if Path('result.txt').read_bytes() == b' live code ' else 1)\n")
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.old = self.git('rev-parse', 'HEAD').decode().strip()
        self.rules.write_bytes(b'Strip spaces.')
        self.git('add', 'AGENTS.md')
        self.git('commit', '-qm', 'proposed')
        self.new = self.git('rev-parse', 'HEAD').decode().strip()
        self.rules.write_bytes(b'Dirty rules from working tree.\n')
        self.data.write_bytes(b'staged input')
        self.git('add', 'input.txt')
        self.data.write_bytes(b' live code ')
        self.config = {'task': 'Keep the input contract', 'instructions': ['AGENTS.md', 'More rules.md'],
                       'oracle': 'verify.py', 'verify': ['{python}', '{oracle}'], 'protected_files': ['runner.py']}
        self.out = self.root / 'results'

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo)

    def comparison(self, **options):
        return Comparison(self.repo, self.config, self.out, None, 2, 8, 15,
                          runner=[sys.executable, 'runner.py'], **options)

    def test_dirty_source_is_constant_while_selected_rules_compare_two_commits(self):
        before_index = (self.repo / '.git/index').read_bytes()
        before_files = {path.name: path.read_bytes() for path in self.repo.iterdir() if path.is_file()}
        comparison = self.comparison(base_ref='HEAD~1', proposed_ref='HEAD')
        with contextlib.redirect_stdout(io.StringIO()):
            report = comparison.execute()
        self.assertEqual(report['status'], 'regressions_observed')
        self.assertEqual([case['verdict'] for case in report['cases']], ['regression'])
        self.assertEqual(len(report['trials']), 4)
        self.assertEqual(report['runner'], 'simulation')
        sources = report['instruction_sources']
        self.assertEqual(sources, {'baseline': {'kind': 'git', 'ref': 'HEAD~1', 'commit': self.old},
                                   'candidate': {'kind': 'git', 'ref': 'HEAD', 'commit': self.new}})
        for arm in ('baseline', 'candidate'):
            exp = comparison.experiments['task', arm]
            self.assertEqual(exp.blobs['input.txt'][0], b' live code ')
            self.assertEqual(exp.report['instruction_source'], sources[arm])
        self.assertEqual(report['instruction_changes'], [
            {'path': 'AGENTS.md', 'changed': True, 'added_lines': 1, 'removed_lines': 1,
             'before_sha256': hashlib.sha256(b'Keep spaces.\r\n').hexdigest(),
             'after_sha256': hashlib.sha256(b'Strip spaces.').hexdigest()},
            {'path': 'More rules.md', 'changed': False, 'added_lines': 0, 'removed_lines': 0,
             'before_sha256': hashlib.sha256(self.stable.read_bytes()).hexdigest(),
             'after_sha256': hashlib.sha256(self.stable.read_bytes()).hexdigest()}])
        patch_bytes = (self.out / 'proposed.patch').read_bytes()
        self.assertEqual(patch_bytes, comparison.instruction_diff().encode('utf-8'))
        self.assertIn(b'-Keep spaces.\r\n+Strip spaces.\n\\ No newline at end of file\n', patch_bytes)
        self.assertEqual((self.out / 'proposed/AGENTS.md').read_bytes(), b'Strip spaces.')
        saved = json.loads((self.out / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['instruction_sources'], sources)
        self.assertEqual(saved['instruction_changes'], report['instruction_changes'])
        self.assertEqual(before_files, {path.name: path.read_bytes() for path in self.repo.iterdir() if path.is_file()})
        self.assertEqual(before_index, (self.repo / '.git/index').read_bytes())
        self.assertEqual(self.git('rev-parse', 'HEAD').decode().strip(), self.new)

    def test_all_source_pairings_and_frozen_plan_diff(self):
        directory = self.root / 'directory with spaces'
        directory.mkdir()
        (directory / 'AGENTS.md').write_bytes(b'Directory rules.\n')
        (directory / self.stable.name).write_bytes(self.stable.read_bytes())
        pairs = [
            ({'base_ref': 'HEAD'}, ('git', 'worktree'), b'Strip spaces.', self.rules.read_bytes()),
            ({'proposed_ref': 'HEAD~1'}, ('worktree', 'git'), self.rules.read_bytes(), b'Keep spaces.\r\n'),
            ({'base_ref': 'HEAD~1', 'candidate': directory}, ('git', 'directory'), b'Keep spaces.\r\n', b'Directory rules.\n'),
            ({'candidate': directory}, ('worktree', 'directory'), self.rules.read_bytes(), b'Directory rules.\n'),
        ]
        for options, kinds, old, new in pairs:
            with self.subTest(kinds=kinds):
                comparison = self.comparison(**options)
                plan = comparison.prepare()
                sources = plan['instruction_sources']
                self.assertEqual((sources['baseline']['kind'], sources['candidate']['kind']), kinds)
                if kinds[1] == 'directory':
                    self.assertEqual(sources['candidate']['path'], str(directory))
                change = plan['instruction_changes'][0]
                self.assertEqual((change['before_sha256'], change['after_sha256']),
                                 tuple(hashlib.sha256(data).hexdigest() for data in (old, new)))
                self.assertEqual(plan['model_calls'], 0)
                self.assertFalse(self.out.exists())
        patch_text = comparison.instruction_diff()
        (directory / 'AGENTS.md').write_bytes(b'Changed after plan.\n')
        self.assertEqual(comparison.instruction_diff(), patch_text)
        self.assertIn('+Directory rules.', patch_text)

    def test_same_ref_is_read_once_across_both_arms_and_multiple_cases(self):
        self.config['cases'] = [{'id': 'first'}, {'id': 'second'}]
        with patch('rulebisect.comparison.read_revision', wraps=read_revision) as reader:
            comparison = self.comparison(base_ref='HEAD', proposed_ref='HEAD')
            plan = comparison.prepare()
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(plan['snapshot_sha256'], plan['candidate_snapshot_sha256'])
        self.assertEqual(plan['required_calls'], 8)
        self.assertEqual(comparison.instruction_diff(), '')
        self.assertTrue(all(not change['changed'] for change in plan['instruction_changes']))

    def test_review_fingerprint_binds_effective_rules_tasks_and_budget(self):
        expected = self.comparison(base_ref='HEAD~1').prepare()['review_fingerprint']
        self.assertRegex(expected, r'^[0-9a-f]{64}$')
        matching = self.comparison(base_ref=self.old, expected_inputs=expected)
        matching.model = 'model selected later'
        self.assertEqual(matching.prepare()['review_fingerprint'], expected)
        for setting, value in [('task', 'Another task'), ('setup', ['{python}', '-V']),
                               ('unit_mode', 'section'), ('cases', [{'id': 'changed-case'}])]:
            with self.subTest(setting=setting), patch.dict(self.config, {setting: value}):
                with patch('rulebisect.experiment.run_process', side_effect=AssertionError('Executed')), \
                        self.assertRaisesRegex(ValueError, 'Reviewed inputs changed'):
                    self.comparison(base_ref='HEAD~1', expected_inputs=expected).execute()
            self.assertFalse(self.out.exists())
        matching.max_runs = 6
        with self.assertRaisesRegex(ValueError, 'Reviewed inputs changed'):
            matching.prepare()
        self.rules.write_bytes(b'Unreviewed edits')
        with patch('rulebisect.experiment.run_process', side_effect=AssertionError('Executed')), \
                self.assertRaisesRegex(ValueError, 'Reviewed inputs changed'):
            self.comparison(base_ref='HEAD~1', expected_inputs=expected).execute()
        self.assertFalse(self.out.exists())

    def test_whitespace_only_file_reaches_verifier_byte_for_byte(self):
        self.rules.write_bytes(b' \t\r\n')
        (self.repo / 'verify.py').write_text(
            "from pathlib import Path\nraise SystemExit(Path('AGENTS.md').read_bytes() != b' \\t\\r\\n')\n",
            encoding='utf-8')
        self.config['setup'] = ['{python}', '-c', 'pass']
        check = Experiment(self.repo, self.config, self.root / 'check', None, 2, 8, 15)
        check.prepare(materialize=True, check_codex=False)
        self.assertEqual(check.check_initial(prepared=True)['exit_code'], 0)
        empty_control = self.root / 'empty-control'
        empty_control.mkdir()
        check.workspace(empty_control, [])
        self.assertEqual((empty_control / 'AGENTS.md').read_bytes(), b'')
        self.assertEqual((empty_control / self.stable.name).read_bytes(), b'')
        with contextlib.redirect_stdout(io.StringIO()):
            report = self.comparison(proposed_ref='HEAD').execute()
        self.assertEqual(report['status'], 'regressions_observed')
        self.assertEqual(report['instruction_changes'][0]['before_sha256'], hashlib.sha256(b' \t\r\n').hexdigest())

    def test_ambiguous_or_missing_sources_fail_before_execution(self):
        for options in ({}, {'candidate': self.repo, 'proposed_ref': 'HEAD'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.comparison(**options).prepare()
            self.assertFalse(self.out.exists())
