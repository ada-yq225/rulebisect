import contextlib
import io
import json
import subprocess
import sys
import unittest

import test_rulebisect as fixtures
from rulebisect.cli import main
from rulebisect.experiment import Experiment
from rulebisect.onboarding import run_wizard
from rulebisect.setup import CONFIG_NAME, init_config
from rulebisect.suite import add_case


class AssertionWorkflowTests(unittest.TestCase):
    setUp = fixtures.IntegrationTests.setUp
    tearDown = fixtures.IntegrationTests.tearDown

    def checks(self):
        return [{'type': 'json_equals', 'path': 'result.json', 'pointer': '/format', 'value': 'modern'}]

    def test_reduction_uses_standalone_frozen_assertions(self):
        config_path = init_config(self.repo, 'Produce the modern result.', None, None, assertions=self.checks())
        config = json.loads(config_path.read_text(encoding='utf-8'))
        with contextlib.redirect_stdout(io.StringIO()):
            report = Experiment(self.repo, config, self.root / 'evidence', None, 2, 90, 10,
                                runner=[sys.executable, 'simulator.py']).execute()
        self.assertEqual(report['status'], 'observed_1_minimal')
        self.assertEqual(report['candidate'], [1, 3])
        self.assertFalse((self.repo / 'result.json').exists())
        self.assertIn('json_equals', (self.root / 'evidence/trials/0001/verify.log').read_text(encoding='utf-8'))

    def test_cli_init_and_case_compile_json_without_model_calls(self):
        spec = self.root / 'checks.json'
        spec.write_text(json.dumps(self.checks()), encoding='utf-8')
        out = self.root / 'initial'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['init', '--repo', str(self.repo), '--task', 'Produce JSON.', '--assertions', str(spec)]), 0)
            self.assertEqual(main(['case', 'add', 'no-extra-file', '--repo', str(self.repo), '--task', 'Keep outputs clean.',
                                   '--assertions', str(spec)]), 0)
            # The input file may change; saved checks remain the originally compiled literal.
            spec.write_text('[]', encoding='utf-8')
            self.assertEqual(main(['check', '--repo', str(self.repo), '--all', '--out', str(out)]), 0)
        report = json.loads((out / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual([case['outcome'] for case in report['cases']], ['fail', 'fail'])
        self.assertEqual(report['trials'], [])
        self.assertTrue((self.repo / '.rulebisect/checks/no-extra-file.py').is_file())

    def test_invalid_assertions_do_not_write_any_configuration(self):
        for spec in ([], [{'type': 'file_exists', 'path': '../outside'}]):
            with self.assertRaises(ValueError):
                init_config(self.repo, 'Task', None, None, assertions=spec)
            self.assertFalse((self.repo / CONFIG_NAME).exists())
            self.assertFalse((self.repo / '.rulebisect-verify.py').exists())
        config_path = init_config(self.repo, 'Task', None, None, oracle='verify.py')
        before = config_path.read_bytes()
        with self.assertRaises(ValueError):
            add_case(self.repo, config_path, 'bad', 'Task', assertions=[])
        self.assertEqual(config_path.read_bytes(), before)
        self.assertFalse((self.repo / '.rulebisect').exists())

    def test_builtin_wizard_requires_no_python_check_script(self):
        answers = iter(['Produce modern JSON.', ':json', 'result.json', '/format', '"modern"', '', ''])
        messages = []
        run_wizard(self.repo, input_fn=lambda _: next(answers), print_fn=messages.append)
        config = json.loads((self.repo / CONFIG_NAME).read_text(encoding='utf-8'))
        oracle = self.repo / config['oracle']
        (self.repo / 'result.json').write_text('{"format":"modern"}', encoding='utf-8')
        result = subprocess.run([sys.executable, str(oracle)], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(any('frozen' in message for message in messages))

    def test_wizard_assertion_cancel_before_write(self):
        answers = iter(['Task', ':json', 'result.json'])
        def ask(_):
            try:
                return next(answers)
            except StopIteration:
                raise EOFError
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            run_wizard(self.repo, input_fn=ask, print_fn=lambda _: None)
        self.assertFalse((self.repo / CONFIG_NAME).exists())
        self.assertFalse((self.repo / '.rulebisect-verify.py').exists())
