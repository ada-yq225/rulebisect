from __future__ import annotations

import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from rulebisect.cli import main
from rulebisect.share import MAX_COUNT, export_summary


class PublicSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.evidence = self.root / 'private-evidence'
        self.evidence.mkdir()
        self.report_path = self.evidence / 'report.json'
        self.out = self.root / 'summary.html'
        self.secret = 'TOP_SECRET_PRIVATE_TOKEN_0123456789'

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, report):
        self.report_path.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')

    def summary(self):
        text = self.out.read_text(encoding='utf-8')
        encoded = re.search(r'<script type="application/json" id="rulebisect-summary">(.*?)</script>', text, re.S).group(1)
        return json.loads(encoded), text

    def trial(self, outcome='pass', usage=None):
        return {'outcome': outcome, 'codex': {'reported_usage': [] if usage is None else [usage]}}

    def test_whitelist_excludes_private_fields_everywhere(self):
        secret = self.secret
        report = {'version': '0.5.0', 'kind': 'comparison', 'status': 'regressions_observed',
                  'runner': 'codex', 'max_runs': 12, 'repeats': 2,
                  'message': secret, 'task': secret, 'created_at': secret,
                  'requested_model': secret, 'repo': secret, 'snapshot': {secret: secret},
                  'instructions': [secret], 'verify': [secret], 'protected_files': [secret],
                  'case_selection': {'available': [secret], 'selected': [secret], 'omitted': [secret]},
                  'rules': [{'id': secret, 'path': secret, 'line': secret, 'text': secret}],
                  'candidate': [secret], 'setup': secret, 'limitations': [secret],
                  'cases': [{'id': secret, 'task': secret, 'oracle': secret, 'verdict': 'regression',
                             'baseline': {'pass': 2, 'fail': 0, 'error': 0, 'outcome': secret},
                             'candidate': {'pass': 0, 'fail': 2, 'error': 0, 'outcome': secret}}],
                  'trials': [{**self.trial('fail', {'input_tokens': 100, 'output_tokens': 3, 'cached_input_tokens': 50}),
                              'case': secret, 'arm': secret, 'reason': secret, 'agent': {secret: secret},
                              'file_changes': [{'path': secret}], 'artifacts': secret, 'logs': secret}]}
        self.write(report)
        result = export_summary(self.evidence, self.out)
        summary, text = self.summary()
        self.assertEqual(result, self.out)
        self.assertNotIn(secret, text)
        self.assertNotIn('https:', text)
        self.assertNotIn('href=', text)
        self.assertEqual(summary['verdicts']['regression'], 1)
        self.assertEqual(summary['omitted_cases'], 1)
        self.assertEqual(summary['variants']['candidate']['fail'], 2)
        self.assertEqual(summary['usage']['input_tokens'], 100)
        self.assertEqual(summary['usage']['reported_runs'], 1)
        self.assertEqual(summary['source'], 'codex')

    def test_unknown_and_hostile_strings_never_render(self):
        hostile = '</script><script>alert("' + self.secret + '")</script>'
        self.write({'version': hostile, 'kind': hostile, 'status': hostile, 'runner': hostile,
                    'message': hostile, 'max_runs': hostile, 'repeats': hostile,
                    'trials': [{'outcome': hostile, 'codex': {'reported_usage': [hostile]}}],
                    'cases': [{'verdict': hostile}]})
        export_summary(self.report_path, self.out)
        summary, text = self.summary()
        self.assertNotIn(hostile, text)
        self.assertNotIn(self.secret, text)
        self.assertEqual(summary['version'], 'unknown')
        self.assertEqual(summary['kind'], 'unknown')
        self.assertEqual(summary['status'], 'unknown')
        self.assertEqual(summary['source'], 'unknown')
        self.assertIsNone(summary['max_runs'])
        self.assertEqual(summary['observations']['unknown'], 1)
        self.assertEqual(summary['usage']['missing_runs'], 1)
        self.assertEqual(summary['usage']['invalid_usage_runs'], 1)

    def test_reduction_counts_only_not_rule_content_or_candidate_ids(self):
        self.write({'version': '0.5.0', 'status': 'observed_1_minimal', 'runner': 'simulation',
                    'trials': [self.trial('fail'), self.trial('pass')], 'max_runs': 10, 'repeats': 2,
                    'rules': [{'id': self.secret, 'text': self.secret, 'path': self.secret}] * 5,
                    'candidate': [self.secret, self.secret]})
        export_summary(self.report_path, self.out)
        summary, text = self.summary()
        self.assertEqual(summary['kind'], 'reduction')
        self.assertEqual(summary['instruction_units'], 5)
        self.assertEqual(summary['candidate_units'], 2)
        self.assertEqual(summary['source'], 'simulation')
        self.assertEqual(summary['usage']['missing_runs'], 2)
        self.assertIn('not a validated fix', text)
        self.assertNotIn(self.secret, text)

    def test_usage_missing_invalid_and_multiple_events_are_visible(self):
        trials = [self.trial(usage={'input_tokens': 4, 'output_tokens': 2, 'cached_input_tokens': 1}),
                  self.trial(usage={'input_tokens': -2, 'output_tokens': True, 'cached_input_tokens': MAX_COUNT + 1}),
                  {'codex': {'reported_usage': [{'input_tokens': 0}, {'output_tokens': 3}]}},
                  {'codex': self.secret}, {'codex': {'reported_usage': self.secret}}, None]
        self.write({'trials': trials, 'max_runs': True, 'repeats': -1})
        export_summary(self.report_path, self.out)
        summary, _ = self.summary()
        self.assertEqual(summary['executions'], 6)
        self.assertEqual(summary['usage'], {'input_tokens': 4, 'output_tokens': 5,
                         'cached_input_tokens': 1, 'reported_runs': 2,
                         'missing_runs': 4, 'partial_usage_runs': 0, 'invalid_usage_runs': 2})
        self.assertIsNone(summary['max_runs'])
        self.assertIsNone(summary['repeats'])

    def test_partial_usage_is_explicit_instead_of_assuming_missing_fields_zero(self):
        self.write({'trials': [self.trial(usage={'input_tokens': 10})]})
        export_summary(self.report_path, self.out)
        summary, text = self.summary()
        self.assertEqual(summary['usage']['partial_usage_runs'], 1)
        self.assertEqual(summary['usage']['missing_runs'], 0)
        self.assertIn('Missing or partial usage is unknown', text)

    def test_aggregated_tokens_stay_bounded(self):
        self.write({'trials': [self.trial(usage={'input_tokens': MAX_COUNT}), self.trial(usage={'input_tokens': 1})]})
        export_summary(self.report_path, self.out)
        summary, _ = self.summary()
        self.assertEqual(summary['usage']['input_tokens'], MAX_COUNT)
        self.assertEqual(summary['usage']['invalid_usage_runs'], 1)
        self.assertEqual(summary['usage']['missing_runs'], 1)

    def test_comparison_counts_normalize_nonintegers_and_pending(self):
        self.write({'kind': 'comparison', 'status': 'inconclusive', 'cases': [
            {'verdict': 'improvement', 'baseline': {'pass': True, 'fail': -4, 'error': self.secret},
             'candidate': {'pass': 2, 'fail': 0, 'error': 1}},
            {'verdict': 'pending', 'baseline': None, 'candidate': None},
            {'verdict': self.secret, 'baseline': self.secret}, None]})
        export_summary(self.report_path, self.out)
        summary, text = self.summary()
        self.assertEqual(summary['cases'], 4)
        self.assertEqual(summary['verdicts']['improvement'], 1)
        self.assertEqual(summary['verdicts']['pending'], 1)
        self.assertEqual(summary['verdicts']['unknown'], 2)
        self.assertEqual(summary['variants']['baseline'], {'pass': 0, 'fail': 0, 'error': 0})
        self.assertEqual(summary['variants']['candidate'], {'pass': 2, 'fail': 0, 'error': 1})
        self.assertNotIn(self.secret, text)

    def test_suite_and_single_check_support_no_model_usage(self):
        self.write({'kind': 'checks', 'status': 'checks_completed', 'runner': 'verifier_only',
                    'cases': [{'id': self.secret, 'outcome': value, 'result': {'log': self.secret}}
                              for value in ('pass', 'fail', 'error', 'pending')], 'trials': []})
        export_summary(self.report_path, self.out)
        summary, text = self.summary()
        self.assertEqual(summary['checks'], {'pass': 1, 'fail': 1, 'error': 1, 'pending': 1, 'unknown': 0})
        self.assertEqual(summary['usage']['reported_runs'], 0)
        self.assertEqual(summary['executions'], 0)
        self.assertIn('Recorded trials / 试验次数', text)
        self.assertNotIn('Executions / 执行次数', text)
        self.assertNotIn(self.secret, text)
        self.out.unlink()
        self.write({'kind': 'check', 'status': 'check_only', 'verifier_check': {'exit_code': 1, 'reason': self.secret}})
        export_summary(self.report_path, self.out)
        summary, text = self.summary()
        self.assertEqual(summary['checks']['fail'], 1)
        self.assertNotIn(self.secret, text)

    def test_existing_output_is_unchanged(self):
        self.write({'trials': []})
        self.out.write_text('keep me', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            export_summary(self.report_path, self.out)
        self.assertEqual(self.out.read_text(encoding='utf-8'), 'keep me')
        self.assertEqual(list(self.root.glob('.rulebisect-summary-*')), [])

    def test_malformed_json_or_arrays_write_nothing(self):
        for value in ([], {'trials': {}}, {'cases': self.secret}, {'rules': {}}, {'candidate': {}}):
            self.write(value)
            with self.subTest(value=type(value).__name__), self.assertRaises(ValueError):
                export_summary(self.report_path, self.out)
            self.assertFalse(self.out.exists())
        self.report_path.write_text('{invalid', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'valid UTF-8 JSON'):
            export_summary(self.report_path, self.out)
        self.assertFalse(self.out.exists())

    def test_missing_source_invalid_destination_and_evidence_destination_rejected(self):
        with self.assertRaisesRegex(ValueError, 'not found'):
            export_summary(self.report_path, self.out)
        self.write({'trials': []})
        for target in (self.evidence / 'summary.html', self.evidence / 'nested' / 'summary.html',
                       self.root / 'summary.txt', self.root / 'absent' / 'summary.html'):
            with self.subTest(target=target.name), self.assertRaises(ValueError):
                export_summary(self.report_path, target)
            self.assertFalse(target.exists())

    def test_atomic_publication_does_not_overwrite_racing_output(self):
        self.write({'trials': []})
        real_link = os.link
        def racing_link(source, target):
            Path(target).write_text('another process', encoding='utf-8')
            return real_link(source, target)
        with patch('rulebisect.share.os.link', side_effect=racing_link):
            with self.assertRaisesRegex(ValueError, 'already exists'):
                export_summary(self.report_path, self.out)
        self.assertEqual(self.out.read_text(encoding='utf-8'), 'another process')
        self.assertEqual(list(self.root.glob('.rulebisect-summary-*')), [])

    def test_failure_during_atomic_publication_removes_temp_file(self):
        self.write({'trials': []})
        with patch('rulebisect.share.os.link', side_effect=OSError('unavailable filesystem')):
            with self.assertRaises(OSError):
                export_summary(self.report_path, self.out)
        self.assertFalse(self.out.exists())
        self.assertEqual(list(self.root.glob('.rulebisect-summary-*')), [])

    def test_cli_symlink_loops_return_actionable_error_without_traceback(self):
        self.write({'trials': []})
        loop = self.root / 'loop'
        try:
            loop.symlink_to(loop, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable')
        values = [(loop / 'report.json', self.out, 'Saved report not found'),
                  (self.report_path, loop / 'summary.html', 'output parent')]
        for source, out, message in values:
            with self.subTest(message=message), redirect_stderr(io.StringIO()) as captured:
                self.assertEqual(main(['share', str(source), '--out', str(out)]), 2)
            self.assertIn(message, captured.getvalue())
            self.assertNotIn('Traceback', captured.getvalue())
            self.assertFalse(self.out.exists())
        self.assertEqual(list(self.root.glob('.rulebisect-summary-*')), [])

    def test_symlinks_and_aliased_evidence_output_rejected(self):
        self.write({'trials': []})
        linked_source = self.root / 'linked.json'
        try:
            linked_source.symlink_to(self.report_path)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            export_summary(linked_source, self.out)
        self.out.symlink_to(self.root / 'absent.html')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            export_summary(self.report_path, self.out)
        self.assertTrue(self.out.is_symlink())
        alias = self.root / 'evidence-alias'
        alias.symlink_to(self.evidence, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'outside'):
            export_summary(self.report_path, alias / 'summary.html')
        self.assertFalse((self.evidence / 'summary.html').exists())


if __name__ == '__main__':
    unittest.main()
