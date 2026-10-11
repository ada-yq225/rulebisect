"""Useful configuration failures and preservation across read/edit commands."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_rulebisect as fixtures
from rulebisect.cli import main
from rulebisect.configuration import MAX_CONFIGURATION_DEPTH, load_configuration, parse_configuration
from rulebisect.setup import CONFIG_NAME, doctor, draft_instructions
from rulebisect.suite import _load_config, add_case, list_cases


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.path = self.root / 'custom configuration.json'

    def tearDown(self):
        self.temporary.cleanup()

    def test_valid_configuration_preserves_bytes_and_unknown_settings(self):
        expected = {'task': '中文 task', 'future_setting': {'items': [False, 1, None]}}
        source = (json.dumps(expected, ensure_ascii=False, indent=3) + '\r\n').encode('utf-8')
        self.path.write_bytes(source)
        with patch('pathlib.Path.read_bytes', side_effect=AssertionError('parse must not reread files')):
            self.assertEqual(parse_configuration(self.path, source), expected)
        self.assertEqual(load_configuration(self.path), expected)
        self.assertEqual(self.path.read_bytes(), source)

    def test_missing_and_directory_paths_explain_which_file_to_select(self):
        for path, reason in ((self.path, 'not found'), (self.root, 'directory')):
            with self.subTest(path=path), self.assertRaises(ValueError) as caught:
                load_configuration(path)
            self.assertIn(str(path), str(caught.exception))
            self.assertIn(reason, str(caught.exception))
            self.assertIn('--config', str(caught.exception))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_real_json_syntax_error_includes_custom_path_line_and_column(self):
        source = b'{\n  "task": "PRIVATE_VALUE_MUST_NOT_APPEAR",\n  "bad": ?\n}\n'
        self.path.write_bytes(source)
        with self.assertRaises(ValueError) as caught:
            load_configuration(self.path)
        message = str(caught.exception)
        self.assertIn(str(self.path), message)
        self.assertIn('line 3', message)
        self.assertIn('column 10', message)
        self.assertIn('Fix the JSON syntax', message)
        self.assertNotIn('PRIVATE_VALUE_MUST_NOT_APPEAR', message)
        self.assertEqual(self.path.read_bytes(), source)

    def test_invalid_utf8_has_path_and_save_instruction(self):
        source = b'{"task":"PRIVATE_VALUE\xff"}'
        self.path.write_bytes(source)
        with self.assertRaises(ValueError) as caught:
            load_configuration(self.path)
        message = str(caught.exception)
        self.assertIn(str(self.path), message)
        self.assertIn('UTF-8', message)
        self.assertIn('Save', message)
        self.assertNotIn('PRIVATE_VALUE', message)
        self.assertEqual(self.path.read_bytes(), source)

    def test_nonobject_roots_explain_expected_shape_without_echoing_values(self):
        for value in ([], None, True, 42, 'PRIVATE_STRING'):
            source = json.dumps(value).encode('utf-8')
            self.path.write_bytes(source)
            with self.subTest(value=value), self.assertRaises(ValueError) as caught:
                load_configuration(self.path)
            message = str(caught.exception)
            self.assertIn(str(self.path), message)
            self.assertIn('JSON object', message)
            self.assertIn('named settings', message)
            self.assertNotIn('PRIVATE_STRING', message)
            self.assertEqual(self.path.read_bytes(), source)

    def test_real_deep_object_is_rejected_before_downstream_copying(self):
        # This finite depth decodes on supported Python versions, while its
        # nesting would become unsafe to copy if accepted without a bound.
        depth = MAX_CONFIGURATION_DEPTH * 5
        source = b'{"future_setting":' + b'[' * depth + b'0' + b']' * depth + b'}'
        self.path.write_bytes(source)
        with self.assertRaises(ValueError) as caught:
            load_configuration(self.path)
        self.assertIn(str(self.path), str(caught.exception))
        self.assertIn('nested too deeply', str(caught.exception))
        self.assertIn(str(MAX_CONFIGURATION_DEPTH), str(caught.exception))
        self.assertEqual(self.path.read_bytes(), source)
        allowed = b'{"future_setting":' + b'[' * (MAX_CONFIGURATION_DEPTH - 1) + b'0' + b']' * (MAX_CONFIGURATION_DEPTH - 1) + b'}'
        self.assertIsInstance(parse_configuration(self.path, allowed), dict)

    def test_decoder_recursion_error_is_actionable_independent_of_python_threshold(self):
        self.path.write_bytes(b'{"task":"small fixture"}')
        with patch('rulebisect.configuration.json.loads', side_effect=RecursionError('decoder recursion')):
            with self.assertRaises(ValueError) as caught:
                load_configuration(self.path)
        self.assertIn(str(self.path), str(caught.exception))
        self.assertIn('Simplify nested settings', str(caught.exception))
        self.assertEqual(self.path.read_bytes(), b'{"task":"small fixture"}')

    def test_read_permission_failure_is_converted_to_actionable_value_error(self):
        with patch('pathlib.Path.read_bytes', side_effect=PermissionError('permission fixture')):
            with self.assertRaises(ValueError) as caught:
                load_configuration(self.path)
        self.assertIn(str(self.path), str(caught.exception))
        self.assertIn('permissions', str(caught.exception))
        self.assertIn('--config', str(caught.exception))
        self.assertFalse(self.path.exists())


class ConfigurationIntegrationTests(unittest.TestCase):
    tearDown = fixtures.IntegrationTests.tearDown

    def setUp(self):
        fixtures.IntegrationTests.setUp(self)
        self.root = self.root.resolve()
        self.repo = self.repo.resolve()

    def snapshot(self):
        return {path.relative_to(self.repo).as_posix(): path.read_bytes()
                for path in self.repo.rglob('*') if path.is_file() and '.git' not in path.relative_to(self.repo).parts}

    def git_only(self, calls):
        original = subprocess.run
        def run(argv, *args, **kwargs):
            calls.append(argv)
            self.assertEqual(argv[0], 'git', 'Configuration inspection must not execute commands or models')
            return original(argv, *args, **kwargs)
        return run

    def test_doctor_cli_json_reports_bad_custom_file_without_writes_or_commands(self):
        custom = self.root / 'custom experiment.json'
        source = b'{\n  "task": "private",\n  "bad": ?\n}\n'
        custom.write_bytes(source)
        before = self.snapshot()
        stdout, stderr, calls = io.StringIO(), io.StringIO(), []
        with patch('subprocess.run', side_effect=self.git_only(calls)), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(['doctor', '--repo', str(self.repo), '--offline', '--config', str(custom), '--json'])
        self.assertEqual(code, 2)
        result = json.loads(stdout.getvalue())
        failure = next(check for check in result['checks'] if check['name'] == 'Experiment inputs')
        self.assertFalse(failure['ok'])
        self.assertIn(str(custom), failure['detail'])
        self.assertIn('line 3', failure['detail'])
        self.assertIn('column 10', failure['detail'])
        self.assertEqual(stderr.getvalue(), '')
        self.assertEqual(result['model_calls'], 0)
        self.assertFalse(result['executed_setup'])
        self.assertFalse(result['executed_verifier'])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(custom.read_bytes(), source)
        self.assertFalse(list(self.root.glob('rulebisect-preflight-*')))

    def test_doctor_explicit_missing_or_directory_config_names_actual_problem(self):
        before = self.snapshot()
        for path, reason in ((self.root / 'missing custom.json', 'not found'), (self.root, 'directory')):
            with self.subTest(path=path):
                result = doctor(self.repo, offline=True, config_path=path)
                failure = next(check for check in result['checks'] if check['name'] == 'Experiment config')
                self.assertFalse(failure['ok'])
                self.assertIn(str(path), failure['detail'])
                self.assertIn(reason, failure['detail'])
                self.assertIn('--config', failure['detail'])
                self.assertNotIn('Instruction files', [check['name'] for check in result['checks']])
        self.assertEqual(self.snapshot(), before)

    def test_doctor_default_missing_config_keeps_discovery_guidance(self):
        result = doctor(self.repo, offline=True)
        self.assertFalse(result['ok'])
        failure = next(check for check in result['checks'] if check['name'] == 'Experiment config')
        self.assertIn(str(self.repo / CONFIG_NAME), failure['detail'])
        self.assertIn('init --wizard', failure['detail'])
        self.assertTrue(next(check for check in result['checks'] if check['name'] == 'Instruction files')['ok'])

    def test_case_parse_retains_exact_once_read_source_for_cas(self):
        path = self.repo / CONFIG_NAME
        source = (json.dumps(self.config, indent=3).replace('\n', '\r\n') + '\r\n').encode('utf-8')
        path.write_bytes(source)
        original_read, reads = Path.read_bytes, []
        def read(current):
            reads.append(current)
            return original_read(current)
        with patch('pathlib.Path.read_bytes', read):
            loaded_path, configured, original = _load_config(path)
        self.assertEqual(reads, [loaded_path])
        self.assertEqual(configured, self.config)
        self.assertEqual(original, source)
        self.assertEqual(path.read_bytes(), source)
        self.assertEqual(list_cases(path)[0]['id'], 'task')

    def test_bad_case_configuration_never_creates_wrapper_or_rewrites_source(self):
        path = self.repo / CONFIG_NAME
        for source, reason in ((b'[]', 'JSON object'), (b'{"task":"\xff"}', 'UTF-8'),
                               (b'{\n "task": ?\n}', 'line 2')):
            path.write_bytes(source)
            before = self.snapshot()
            with self.subTest(source=source), self.assertRaises(ValueError) as caught:
                add_case(self.repo, path, 'new', 'Task', check='command-must-not-execute')
            self.assertIn(str(path.resolve()), str(caught.exception))
            self.assertIn(reason, str(caught.exception))
            self.assertEqual(self.snapshot(), before)
            self.assertFalse((self.repo / '.rulebisect').exists())

    def test_decoder_recursion_is_safe_for_cli_doctor_case_and_draft(self):
        path = self.repo / CONFIG_NAME
        source = json.dumps(self.config).encode('utf-8')
        path.write_bytes(source)
        before = self.snapshot()
        original_loads = json.loads
        def decode(value, *args, **kwargs):
            if value == source.decode('utf-8'):
                raise RecursionError('decoder fixture')
            return original_loads(value, *args, **kwargs)
        operations = [['doctor', '--repo', str(self.repo), '--offline', '--json'],
                      ['case', 'add', 'new', '--repo', str(self.repo), '--task', 'Task', '--check', 'command-must-not-execute']]
        for arguments in operations:
            stdout, stderr, calls = io.StringIO(), io.StringIO(), []
            with self.subTest(command=arguments[0]), patch('rulebisect.configuration.json.loads', side_effect=decode), patch('subprocess.run', side_effect=self.git_only(calls)), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(arguments)
            self.assertEqual(code, 2)
            combined = stdout.getvalue() + stderr.getvalue()
            self.assertIn('nested too deeply', combined)
            self.assertIn(str(path.resolve()), combined)
            self.assertNotIn('Traceback', combined)
            self.assertEqual(self.snapshot(), before)
        output = self.root / 'draft'
        with patch('rulebisect.configuration.json.loads', side_effect=decode):
            with self.assertRaisesRegex(ValueError, 'nested too deeply'):
                draft_instructions(self.repo, output)
        self.assertFalse(output.exists())
        self.assertFalse((self.repo / '.rulebisect').exists())
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
