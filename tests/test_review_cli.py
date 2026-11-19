"""Carry an offline rule review to the comparison CLI and recheck its scope."""
import contextlib
from argparse import Namespace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rulebisect.cli import main, restore_compare_options
from rulebisect.tutorial import create_tutorial


class ReviewCLITests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.repo = create_tutorial(self.root / 'review project')

    def cli(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main([str(arg) for arg in args])
        return code, output.getvalue(), errors.getvalue()

    def test_review_command_roundtrip_with_subset_and_pinned_inputs(self):
        evidence = self.root / 'future experiment'
        page = self.root / 'rule changes.html'
        custom = self.repo / '.rulebisect.json'
        with patch('rulebisect.experiment.run_process', side_effect=AssertionError('unexpected execution')):
            result, output, error = self.cli('review', '--repo', self.repo, '--config', custom, '--cases',
                                              'modern', '--html', page, '--diff', '--json',
                                              '--out', evidence, '--max-tokens', '1200')
            self.assertEqual(result, 0, error)
            plan = json.loads(output)
            self.assertEqual(plan['required_calls'], 4)
            self.assertEqual(plan['case_selection']['omitted'], ['legacy'])
            self.assertIn('AGENTS.md', plan['diff'])
            self.assertIn(plan['review_fingerprint'], page.read_text(encoding='utf-8'))
            command = plan['next_argv'][1:]
            self.assertIn(plan['instruction_sources']['baseline']['commit'], command)
            code, output, error = self.cli(*command, '--plan')
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(output)['review_fingerprint'], plan['review_fingerprint'])
            (self.repo / 'labels.py').write_text('def normalize_label(value, client): return value\n')
            code, _, error = self.cli(*command, '--plan')
            self.assertEqual(code, 2)
            self.assertIn('Reviewed inputs changed', error)
            self.assertFalse(evidence.exists())

    def test_review_preserves_existing_page_and_repository(self):
        page = self.root / 'review.html'
        page.write_bytes(b'previous report')
        for target in [page, self.repo / 'new.html']:
            with self.subTest(target=target):
                code, _, _ = self.cli('review', '--repo', self.repo, '--html', target)
                self.assertEqual(code, 2)
        self.assertEqual(page.read_bytes(), b'previous report')
        self.assertFalse((self.repo / 'new.html').exists())

    def test_preview_of_identical_commits_reports_zero_changes(self):
        code, output, error = self.cli('review', '--repo', self.repo, '--proposed-ref', 'HEAD', '--json', '--diff')
        self.assertEqual(code, 0, error)
        preview = json.loads(output)
        self.assertFalse(any(change['changed'] for change in preview['instruction_changes']))
        self.assertEqual(preview['diff'], '')
        self.assertEqual(preview['model_calls'], 0)

    def test_continue_restores_pinned_sources_subset_and_execution_settings(self):
        report = {'kind': 'comparison', 'requested_model': 'chosen-model', 'repeats': 3,
                  'max_runs': 12, 'unit_mode': 'section', 'timeout_seconds': 45,
                  'case_selection': {'selected': ['modern']},
                  'instruction_sources': {'baseline': {'kind': 'git', 'commit': 'a' * 40, 'ref': 'main'},
                                          'candidate': {'kind': 'git', 'commit': 'b' * 40, 'ref': 'proposal'}}}
        args = Namespace(continue_from=self.root, max_tokens=2000, base_ref=None, proposed_ref=None,
                         candidate=None, model=None, repeats=None, max_runs=None, unit_mode=None,
                         timeout=None, cases=None)
        with patch('rulebisect.comparison_resume.read_prior_report', return_value=report):
            restore_compare_options(args)
            self.assertEqual((args.base_ref, args.proposed_ref), ('a' * 40, 'b' * 40))
            self.assertEqual((args.model, args.repeats, args.max_runs, args.timeout, args.unit_mode,
                              args.cases, args.max_tokens), ('chosen-model', 3, 12, 45, 'section', ['modern'], 2000))
            report['instruction_sources']['candidate'] = {'kind': 'directory', 'path': '/untrusted/location'}
            with self.assertRaisesRegex(ValueError, '--proposed DIRECTORY'):
                restore_compare_options(args)
            self.assertIsNone(args.candidate)

    def test_continuation_requires_explicit_new_token_threshold(self):
        code, _, error = self.cli('compare', '--repo', self.repo, '--continue-from', self.root, '--plan')
        self.assertEqual(code, 2)
        self.assertIn('--max-tokens', error)
