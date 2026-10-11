import contextlib
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_rulebisect as fixtures
from rulebisect.cli import main
from rulebisect.setup import CONFIG_NAME
from rulebisect.status import workspace_status


class StatusTests(unittest.TestCase):
    setUp = fixtures.IntegrationTests.setUp
    tearDown = fixtures.IntegrationTests.tearDown

    def cli(self, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(list(arguments))
        return code, output.getvalue(), errors.getvalue()

    def test_no_arguments_offers_entry_points_without_repository_or_commands(self):
        with patch('rulebisect.cli.git_root', side_effect=AssertionError('No repository inspection')):
            code, output, errors = self.cli()
        self.assertEqual(code, 0)
        self.assertFalse(errors)
        self.assertIn('rulebisect status', output)
        self.assertIn('rulebisect demo', output)

    def test_cli_wizard_uses_custom_rules_without_an_agents_file(self):
        (self.repo / 'AGENTS.md').rename(self.repo / 'rules with spaces.md')
        before = (self.repo / 'rules with spaces.md').read_bytes()
        completed = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'rulebisect', 'init', '--wizard',
                                    '--repo', str(self.repo), '--instructions', 'rules with spaces.md'],
                                   input='Keep the contract\npython verify.py\n\n\n',
                                   capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        config = json.loads((self.repo / CONFIG_NAME).read_text(encoding='utf-8'))
        self.assertEqual(config['instructions'], ['rules with spaces.md'])
        self.assertEqual(before, (self.repo / 'rules with spaces.md').read_bytes())
        self.assertFalse((self.repo / 'result.json').exists())

    def test_unconfigured_repository_and_custom_instruction_guidance(self):
        result = workspace_status(self.repo)
        self.assertEqual(result['state'], 'needs_configuration')
        self.assertIn('--wizard', result['next_steps'][0]['argv'])
        self.assertFalse((self.repo / CONFIG_NAME).exists())
        (self.repo / 'AGENTS.md').unlink()
        result = workspace_status(self.repo)
        self.assertEqual(result['state'], 'needs_instructions')
        self.assertIn('--instructions', result['next_steps'][0]['argv'])
        self.assertEqual(result['model_calls'], 0)

    def test_configured_status_validates_without_running_commands_or_writing(self):
        (self.repo / CONFIG_NAME).write_text(json.dumps(self.config), encoding='utf-8')
        before = {p.name: p.read_bytes() for p in self.repo.iterdir() if p.is_file()}
        with patch('rulebisect.experiment.run_process', side_effect=AssertionError('No execution')), \
             patch('subprocess.run', wraps=subprocess.run) as commands:
            code, output, errors = self.cli('status', '--repo', str(self.repo), '--json')
        self.assertEqual(code, 0, errors)
        result = json.loads(output)
        self.assertEqual(result['state'], 'configured')
        self.assertEqual(result['cases'], ['task'])
        self.assertEqual(result['budget'], {'repeats': 3, 'max_runs': 60, 'comparison_calls': 6})
        self.assertFalse(result['executed_setup'])
        self.assertFalse(result['executed_verifier'])
        self.assertEqual(result['model_calls'], 0)
        self.assertTrue(all(call.args[0][0] == 'git' for call in commands.call_args_list))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.repo.iterdir() if p.is_file()})
        self.assertFalse((self.root / '.rulebisect-runs').exists())

    def test_custom_config_path_and_repo_are_preserved_in_suggestions(self):
        custom = self.root / 'custom settings.json'
        custom.write_text(json.dumps(self.config), encoding='utf-8')
        result = workspace_status(self.repo, custom)
        for step in result['next_steps']:
            arguments = step['argv']
            self.assertEqual(arguments[arguments.index('--repo') + 1], str(self.repo.resolve()))
            self.assertEqual(arguments[arguments.index('--config') + 1], str(custom))
        custom.unlink()
        result = workspace_status(self.repo, custom)
        self.assertEqual(result['state'], 'needs_attention')
        self.assertEqual(result['next_steps'][0]['argv'][1], 'doctor')
        self.assertIn(str(custom), result['next_steps'][0]['argv'])
        self.assertFalse((self.repo / CONFIG_NAME).exists())

    def test_bad_configuration_returns_structured_attention_and_exact_path(self):
        custom = self.root / 'broken config.json'
        custom.write_text('{"task": }', encoding='utf-8')
        code, output, errors = self.cli('status', '--repo', str(self.repo), '--config', str(custom), '--json')
        self.assertEqual(code, 2)
        self.assertFalse(errors)
        result = json.loads(output)
        self.assertEqual(result['state'], 'needs_attention')
        self.assertTrue(any(str(custom) in item['detail'] for item in result['checks'] if not item['ok']))
        self.assertIsNone(result['budget'])

    def test_saved_evidence_is_an_entry_point_without_asserting_current_success(self):
        (self.repo / CONFIG_NAME).write_text(json.dumps(self.config), encoding='utf-8')
        saved = self.root / '.rulebisect-runs' / self.repo.name / 'old report'
        saved.mkdir(parents=True)
        report = {'created_at': '2026-01-01T00:00:00', 'kind': 'comparison',
                  'status': 'no_regressions_observed', 'trials': [], 'runner': 'codex'}
        (saved / 'report.json').write_text(json.dumps(report), encoding='utf-8')
        code, output, errors = self.cli('status', '--repo', str(self.repo))
        self.assertEqual(code, 0, errors)
        self.assertIn(str(saved), output)
        self.assertIn('older snapshot', output)
        self.assertIn('does not validate current inputs', output)
        self.assertIn('rulebisect check --all', output)
        self.assertNotIn('rulebisect run', output)

    def test_unreadable_optional_history_preserves_status_json_and_next_steps(self):
        (self.repo / CONFIG_NAME).write_text(json.dumps(self.config), encoding='utf-8')
        history_root = self.repo.resolve().parent / '.rulebisect-runs' / self.repo.name
        history_root.mkdir(parents=True)
        original_iterdir = type(history_root).iterdir
        def read_directory(path):
            if path == history_root:
                raise PermissionError('Saved evidence is unreadable')
            return original_iterdir(path)
        before = (self.repo / CONFIG_NAME).read_bytes()
        with patch.object(type(history_root), 'iterdir', read_directory):
            code, output, errors = self.cli('status', '--repo', str(self.repo), '--json')
        self.assertEqual(code, 0, errors)
        result = json.loads(output)
        self.assertEqual(result['state'], 'configured')
        self.assertIsNone(result['latest_report'])
        self.assertTrue(result['history_warnings'])
        self.assertEqual(result['next_steps'][0]['argv'][1:3], ['check', '--all'])
        self.assertEqual(before, (self.repo / CONFIG_NAME).read_bytes())
        self.assertFalse(any(history_root.iterdir()))

    def test_non_repository_status_reports_next_step_without_creating_git_files(self):
        code, output, errors = self.cli('status', '--repo', str(self.root), '--json')
        self.assertEqual(code, 2)
        self.assertFalse(errors)
        result = json.loads(output)
        self.assertIsNone(result['repository'])
        self.assertEqual(result['next_steps'][0]['argv'][1], 'demo')
        self.assertFalse((self.root / '.git').exists())
