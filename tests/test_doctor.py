import contextlib
import io
import json
import subprocess
import unittest
from unittest.mock import patch

import test_rulebisect as fixtures
from rulebisect.cli import main
from rulebisect.setup import CONFIG_NAME, doctor


class DoctorTests(unittest.TestCase):
    setUp = fixtures.IntegrationTests.setUp
    tearDown = fixtures.IntegrationTests.tearDown

    def save(self, **changes):
        config = dict(self.config, **changes)
        (self.repo / CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        return config

    def test_offline_validates_without_codex_or_executing_commands(self):
        self.save(setup=['nonexistent-setup-command'])
        original = subprocess.run
        calls = []
        def track(argv, *args, **kwargs):
            calls.append(argv)
            return original(argv, *args, **kwargs)
        with patch('rulebisect.setup.subprocess.run', side_effect=track):
            result = doctor(self.repo, offline=True)
        self.assertTrue(result['ok'], result)
        self.assertTrue(all(argv[0] == 'git' for argv in calls))
        self.assertFalse(list(self.root.glob('rulebisect-preflight-*')))
        self.assertEqual(result['scope']['cases'], ['task'])
        self.assertEqual(result['model_calls'], 0)
        self.assertFalse(result['executed_setup'])
        self.assertFalse(result['executed_verifier'])
        self.assertTrue(any('not executed' in text for text in result['warnings']))

    def test_rejects_invalid_config_inputs(self):
        for changes in ({'oracle': 'missing.py'}, {'repeats': 'three'},
                        {'verify': 'python verify.py'}, {'unit_mode': 'unknown'},
                        {'protected_files': ['../outside']}, {'instructions': ['AGENTS.md', 'AGENTS.md']}):
            with self.subTest(changes=changes):
                self.save(**changes)
                result = doctor(self.repo, offline=True)
                self.assertFalse(result['ok'])
                self.assertTrue(any(c['name'] == 'Experiment inputs' and not c['ok'] for c in result['checks']))

    def test_bad_json_and_nonobject_are_actionable(self):
        for text in ('{', '[]'):
            (self.repo / CONFIG_NAME).write_text(text, encoding='utf-8')
            self.assertFalse(doctor(self.repo, offline=True)['ok'])

    def test_all_suite_cases_checked(self):
        self.save(cases=[{'id': 'first'}, {'id': 'second', 'oracle': 'missing.py'}])
        result = doctor(self.repo, offline=True)
        self.assertFalse(result['ok'])
        self.assertIn('Case second', result['checks'][-1]['detail'])

    def test_comparison_scope_and_budget(self):
        self.save(repeats=2, max_runs=4, cases=[{'id': 'one'}, {'id': 'two'}])
        result = doctor(self.repo, offline=True)
        self.assertTrue(result['ok'])
        self.assertEqual(result['scope']['comparison_calls'], 8)
        self.assertTrue(any('needs 8 calls' in warning for warning in result['warnings']))
        proposed = self.root / 'proposed'
        proposed.mkdir()
        (proposed / 'AGENTS.md').write_text('Changed rules')
        result = doctor(self.repo, offline=True, proposed=proposed)
        self.assertFalse(result['ok'])
        self.assertIn('needs 8 calls', result['checks'][-1]['detail'])
        self.save(repeats=2, max_runs=8, cases=[{'id': 'one'}, {'id': 'two'}])
        result = doctor(self.repo, offline=True, proposed=proposed)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['scope']['required_calls'], 8)

    def test_custom_config_cli_and_no_mutation(self):
        custom = self.repo / 'custom.json'
        content = json.dumps(self.config)
        custom.write_text(content, encoding='utf-8')
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(['doctor', '--repo', str(self.repo), '--offline', '--config', str(custom), '--json'])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertTrue(result['offline'])
        self.assertEqual(custom.read_text(encoding='utf-8'), content)
        self.assertFalse((self.repo / CONFIG_NAME).exists())

    def test_auth_output_never_exposed(self):
        self.save()
        original = subprocess.run
        def fake(argv, *args, **kwargs):
            if argv[0] != 'codex':
                return original(argv, *args, **kwargs)
            output = '--json --ephemeral --ignore-user-config' if argv[1] == 'exec' else 'PRIVATE_AUTH_SECRET' if argv[1] == 'login' else 'codex fixture-version'
            return subprocess.CompletedProcess(argv, 0, output, '')
        with patch('rulebisect.setup.shutil.which', return_value='/fake/executable'), patch('rulebisect.setup.subprocess.run', side_effect=fake):
            result = doctor(self.repo)
        self.assertTrue(result['ok'])
        self.assertNotIn('PRIVATE_AUTH_SECRET', json.dumps(result))
