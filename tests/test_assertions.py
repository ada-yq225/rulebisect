import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rulebisect.assertions import MAX_OUTPUT_BYTES, build_oracle, evaluate_assertions, validate_assertions


class AssertionsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='rulebisect-assertions-')
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
        return path

    def oracle(self, checks):
        # -I removes both the current package and PYTHONPATH from import lookup.
        path = self.write('standalone_oracle.py', build_oracle(checks))
        return subprocess.run([sys.executable, '-I', str(path)], cwd=self.root,
                              capture_output=True, text=True, encoding='utf-8', timeout=10)

    def test_all_six_checks_in_generated_isolated_oracle(self):
        self.write('nested/结果.txt', 'Welcome\n你好\nID=42\n')
        self.write('result.json', json.dumps({'format': 'modern', 'values': [1, True, None]}))
        checks = [
            {'type': 'file_exists', 'path': 'nested/结果.txt'},
            {'type': 'file_absent', 'path': 'nested/missing.txt'},
            {'type': 'file_contains', 'path': 'nested/结果.txt', 'text': '你好'},
            {'type': 'file_not_contains', 'path': 'nested/结果.txt', 'text': 'legacy'},
            {'type': 'file_matches', 'path': 'nested/结果.txt', 'pattern': r'(?m)^ID=\d+$'},
            {'type': 'json_equals', 'path': 'result.json', 'pointer': '/values/1', 'value': True},
        ]
        result = self.oracle(checks)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('PASS ['), 6)
        self.assertNotIn('你好', result.stdout)
        self.assertNotIn('Welcome', result.stdout)

    def test_validation_requires_strict_nonempty_list(self):
        invalid = [None, {}, [], 'checks', [True], [{'type': True, 'path': 'output'}],
                   [{'type': 'unknown', 'path': 'output'}],
                   [{'type': 'file_exists'}],
                   [{'type': 'file_exists', 'path': 'output', 'text': 'extra'}],
                   [{'type': 'file_contains', 'path': 'output', 'text': ''}],
                   [{'type': 'file_contains', 'path': 'output', 'text': False}],
                   [{'type': 'file_matches', 'path': 'output', 'pattern': '('}],
                   [{'type': 'file_matches', 'path': 'output', 'pattern': 'x{999999999999999999999}'}],
                   [{'type': 'file_matches', 'path': 'output', 'pattern': '(' * 2000}],
                   [{'type': 'json_equals', 'path': 'output', 'pointer': False, 'value': 1}]]
        for spec in invalid:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_assertions(spec)

    def test_invalid_paths_are_rejected_on_every_platform(self):
        paths = ['', ' ', '.', '..', '/etc/passwd', 'a/../secret', './a', 'a//b', 'a/',
                 '.git/config', 'a/.GIT/config', 'C:/secret', 'C:secret', '\\\\host\\secret',
                 'a\\secret', 'a:stream', 'a\x00b', 'a\nb', 'a\ud800b']
        for path in paths:
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_assertions([{'type': 'file_exists', 'path': path}])
        self.assertEqual(validate_assertions([{'type': 'file_exists', 'path': 'folder with spaces/a.txt'}])[0]['path'],
                         'folder with spaces/a.txt')

    def test_invalid_pointer_and_non_json_values(self):
        for pointer in ('relative', '#/a', '/a~', '/a~2', '/a~01~'):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                validate_assertions([{'type': 'json_equals', 'path': 'out', 'pointer': pointer, 'value': 1}])
        cyclic = []
        cyclic.append(cyclic)
        for value in (float('nan'), float('inf'), -float('inf'), {'x': float('inf')},
                      (1, 2), {1: 'not a JSON key'}, b'bytes', {1, 2}, cyclic):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                validate_assertions([{'type': 'json_equals', 'path': 'out', 'pointer': '', 'value': value}])

    def test_validated_spec_is_independent_of_input(self):
        spec = [{'type': 'json_equals', 'path': 'out', 'pointer': '', 'value': {'nested': [1]}}]
        validated = validate_assertions(spec)
        validated[0]['value']['nested'].append(2)
        self.assertEqual(spec[0]['value'], {'nested': [1]})

    def test_pointer_escapes_root_arrays_and_empty_keys(self):
        value = {'a/b': {'~': ['first', {'': 'found'}]}, '': None, '01': 'object key'}
        self.write('result.json', json.dumps(value))
        expected = [('', value), ('/a~1b/~0/0', 'first'), ('/a~1b/~0/1/', 'found'),
                    ('/', None), ('/01', 'object key')]
        checks = [{'type': 'json_equals', 'path': 'result.json', 'pointer': pointer, 'value': item}
                  for pointer, item in expected]
        self.assertEqual([item['outcome'] for item in evaluate_assertions(checks, self.root)], ['pass'] * 5)
        self.assertEqual(self.oracle(checks).returncode, 0)

    def test_missing_and_invalid_array_pointer_are_behavior_failures(self):
        self.write('result.json', '[0, 1]')
        checks = [{'type': 'json_equals', 'path': 'result.json', 'pointer': pointer, 'value': 1}
                  for pointer in ('/2', '/01', '/-', '/-1', '/key', '/' + '9' * 5000)]
        results = evaluate_assertions(checks, self.root)
        self.assertTrue(all(item['outcome'] == 'fail' for item in results))
        self.assertTrue(all(item['reason'] == 'JSON pointer is not present' for item in results))
        self.assertEqual(self.oracle(checks).returncode, 1)

    def test_json_booleans_are_distinct_from_numbers_recursively(self):
        fixtures = [(True, 1, 'fail'), (False, 0, 'fail'), (1, True, 'fail'),
                    ([True], [1], 'fail'), ({'a': False}, {'a': 0}, 'fail'),
                    (1, 1.0, 'pass'), (1, '1', 'fail'), (None, None, 'pass')]
        checks = []
        for index, (actual, expected, _) in enumerate(fixtures):
            self.write(f'{index}.json', json.dumps(actual))
            checks.append({'type': 'json_equals', 'path': f'{index}.json', 'pointer': '', 'value': expected})
        self.assertEqual([item['outcome'] for item in evaluate_assertions(checks, self.root)],
                         [item[2] for item in fixtures])

    def test_missing_required_outputs_fail_and_absent_outputs_pass(self):
        checks = [{'type': 'file_exists', 'path': 'missing/output.txt'},
                  {'type': 'file_absent', 'path': 'missing/output.txt'},
                  {'type': 'file_not_contains', 'path': 'missing.txt', 'text': 'anything'}]
        self.assertEqual([item['outcome'] for item in evaluate_assertions(checks, self.root)], ['fail', 'pass', 'fail'])
        self.assertEqual(self.oracle(checks).returncode, 1)

    def test_text_check_failures_do_not_disclose_contents_or_values(self):
        self.write('output.txt', 'private-content-ABC\nsecret-forbidden-text\n')
        self.write('result.json', '{"secret": "actual-private-value"}')
        checks = [{'type': 'file_contains', 'path': 'output.txt', 'text': 'expected-private-text'},
                  {'type': 'file_not_contains', 'path': 'output.txt', 'text': 'secret-forbidden-text'},
                  {'type': 'file_matches', 'path': 'output.txt', 'pattern': 'secret-pattern-XYZ'},
                  {'type': 'json_equals', 'path': 'result.json', 'pointer': '/secret', 'value': 'expected-private-value'}]
        result = self.oracle(checks)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count('FAIL ['), 4)
        for private in ('private-content-ABC', 'secret-forbidden-text', 'expected-private-text',
                        'secret-pattern-XYZ', 'actual-private-value', 'expected-private-value'):
            self.assertNotIn(private, result.stdout + result.stderr)

    def test_invalid_utf8_and_json_are_behavior_failures(self):
        self.write('invalid.txt', b'\xff\xfe')
        checks = [{'type': 'file_contains', 'path': 'invalid.txt', 'text': 'x'}]
        for index, text in enumerate(('{', 'NaN', 'Infinity', '-Infinity', '1e999', '{"x":NaN}', '{"x":}')):
            self.write(f'invalid{index}.json', text)
            checks.append({'type': 'json_equals', 'path': f'invalid{index}.json', 'pointer': '', 'value': 1})
        self.assertTrue(all(item['outcome'] == 'fail' for item in evaluate_assertions(checks, self.root)))
        self.assertEqual(self.oracle(checks).returncode, 1)

    def test_directories_and_nondirectory_ancestors_are_infrastructure_errors(self):
        (self.root / 'directory').mkdir()
        self.write('plain.txt', 'one')
        checks = [{'type': 'file_exists', 'path': 'directory'},
                  {'type': 'file_absent', 'path': 'directory'},
                  {'type': 'file_exists', 'path': 'plain.txt/child'}]
        self.assertEqual([item['outcome'] for item in evaluate_assertions(checks, self.root)], ['error'] * 3)
        self.assertEqual(self.oracle(checks).returncode, 2)

    def test_oversize_outputs_are_errors_at_inspection_and_after_growth(self):
        self.write('large.txt', b'x' * (MAX_OUTPUT_BYTES + 1))
        checks = [{'type': 'file_contains', 'path': 'large.txt', 'text': 'x'},
                  {'type': 'file_exists', 'path': 'large.txt'}]
        self.assertEqual([item['outcome'] for item in evaluate_assertions(checks, self.root)], ['error', 'error'])
        self.assertEqual(self.oracle(checks).returncode, 2)
        self.write('large.txt', 'x')
        with patch('rulebisect.assertions._read_output', side_effect=OSError('Output exceeds the 2 MiB limit')):
            self.assertEqual(evaluate_assertions(checks[:1], self.root)[0]['outcome'], 'error')

    def test_binary_file_can_pass_existence_check_without_being_decoded(self):
        self.write('binary.bin', b'\x00\xff')
        self.assertEqual(self.oracle([{'type': 'file_exists', 'path': 'binary.bin'}]).returncode, 0)

    def test_io_failure_does_not_stop_other_checks(self):
        self.write('output.txt', 'one')
        checks = [{'type': 'file_contains', 'path': 'output.txt', 'text': 'one'},
                  {'type': 'file_exists', 'path': 'output.txt'}]
        with patch('rulebisect.assertions._read_output', side_effect=PermissionError('private path details')):
            results = evaluate_assertions(checks, self.root)
        self.assertEqual([item['outcome'] for item in results], ['error', 'pass'])
        self.assertNotIn('private path details', results[0]['reason'])

    def test_every_check_runs_and_errors_take_exit_precedence(self):
        self.write('output.txt', 'one')
        (self.root / 'directory').mkdir()
        checks = [{'type': 'file_exists', 'path': 'missing'},
                  {'type': 'file_exists', 'path': 'directory'},
                  {'type': 'file_exists', 'path': 'output.txt'}]
        result = self.oracle(checks)
        self.assertEqual(result.returncode, 2)
        self.assertIn('FAIL [1]', result.stdout)
        self.assertIn('ERROR [2]', result.stdout)
        self.assertIn('PASS [3]', result.stdout)

    def test_symlink_outputs_and_ancestors_are_errors(self):
        self.write('target.txt', 'private outside contents')
        (self.root / 'real').mkdir()
        self.write('real/output.txt', 'private outside contents')
        try:
            (self.root / 'link.txt').symlink_to(self.root / 'target.txt')
            (self.root / 'linked-folder').symlink_to(self.root / 'real', target_is_directory=True)
            (self.root / 'broken.txt').symlink_to(self.root / 'missing.txt')
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Symlinks unavailable: {type(error).__name__}')
        checks = [{'type': 'file_exists', 'path': 'link.txt'},
                  {'type': 'file_contains', 'path': 'linked-folder/output.txt', 'text': 'private'},
                  {'type': 'file_absent', 'path': 'broken.txt'}]
        result = self.oracle(checks)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.count('ERROR ['), 3)
        self.assertNotIn('private outside contents', result.stdout)

    def test_missing_or_symlink_root_is_an_infrastructure_error(self):
        check = [{'type': 'file_exists', 'path': 'output.txt'}]
        self.assertEqual(evaluate_assertions(check, self.root / 'missing')[0]['outcome'], 'error')
        try:
            (self.root / 'root-link').symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Symlinks unavailable: {type(error).__name__}')
        self.assertEqual(evaluate_assertions(check, self.root / 'root-link')[0]['outcome'], 'error')

    def test_expected_values_are_safely_frozen_in_generated_source(self):
        unusual = '\"); __import__("os").remove("keep.txt"); #\n\\literal\u2603'
        self.write('keep.txt', 'keep')
        self.write('output.txt', unusual)
        result = self.oracle([{'type': 'file_contains', 'path': 'output.txt', 'text': unusual}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'keep.txt').exists())
        self.assertNotIn(unusual, result.stdout)


if __name__ == '__main__':
    unittest.main()
