from __future__ import annotations

import ast
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rulebisect.onboarding import command_suggestions, run_wizard
from rulebisect.setup import CONFIG_NAME


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / 'project with spaces'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True)
        (self.repo / 'AGENTS.md').write_text('Keep compatibility.\n', encoding='utf-8')
        subprocess.run(['git', 'add', 'AGENTS.md'], cwd=self.repo, check=True)
        self.messages = []

    def tearDown(self):
        self.temporary.cleanup()

    def wizard(self, answers, **options):
        answers = iter(answers)
        return run_wizard(self.repo, input_fn=lambda _: next(answers), print_fn=self.messages.append,
                          **options)

    def assert_unconfigured(self):
        self.assertFalse((self.repo / CONFIG_NAME).exists())
        self.assertFalse((self.repo / '.rulebisect-verify.py').exists())

    def test_custom_check_creates_config_without_executing_it(self):
        marker = self.repo / 'must-not-exist'
        check = f'python -c "from pathlib import Path; Path({str(marker)!r}).touch()"'
        self.wizard(['Preserve the API', check, '', ''])
        config = json.loads((self.repo / CONFIG_NAME).read_text(encoding='utf-8'))
        self.assertEqual(config['task'], 'Preserve the API')
        self.assertEqual(config['instructions'], ['AGENTS.md'])
        self.assertNotIn('model', config)
        self.assertNotIn('setup', config)
        self.assertFalse(marker.exists())
        self.assertIn('COMMAND =', (self.repo / '.rulebisect-verify.py').read_text(encoding='utf-8'))
        self.assertTrue(any('doctor --offline' in message for message in self.messages))

    def test_existing_config_refused_before_first_prompt(self):
        config = self.repo / CONFIG_NAME
        config.write_text('original', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            run_wizard(self.repo, input_fn=lambda _: self.fail('Must not prompt'), print_fn=self.messages.append)
        self.assertEqual(config.read_text(encoding='utf-8'), 'original')

    def test_cancel_and_interrupt_write_nothing_at_any_prompt(self):
        complete = ['Task', 'python verify.py', '', '']
        for error_type in (EOFError, KeyboardInterrupt):
            for position in range(len(complete)):
                with self.subTest(error=error_type.__name__, position=position):
                    answers = iter(complete[:position])
                    def ask(_):
                        try:
                            return next(answers)
                        except StopIteration:
                            raise error_type
                    with self.assertRaisesRegex(ValueError, 'cancelled'):
                        run_wizard(self.repo, input_fn=ask, print_fn=self.messages.append)
                    self.assert_unconfigured()

    def test_blank_task_and_invalid_commands_reprompt_before_writes(self):
        self.wizard([' ', 'Make output stable', '', '99', 'python -c "bad',
                     'npm test && npm run lint', 'python verify.py',
                     'npm ci | cat', 'python setup.py', 'test-model'])
        config = json.loads((self.repo / CONFIG_NAME).read_text(encoding='utf-8'))
        self.assertEqual(config['setup'], ['{python}', 'setup.py'])
        self.assertEqual(config['model'], 'test-model')
        self.assertTrue(any('cannot be empty' in message for message in self.messages))
        self.assertTrue(any('shell operators' in message for message in self.messages))

    def test_explicit_manifest_suggestion_selected(self):
        (self.repo / 'package.json').write_text(json.dumps({'scripts': {'test': 'node verify.js'}}), encoding='utf-8')
        self.wizard(['Keep JS API stable', '1', 'npm ci', 'example-model'])
        wrapper = (self.repo / '.rulebisect-verify.py').read_text(encoding='utf-8')
        self.assertIn("COMMAND = ['npm', 'test']", wrapper)
        config = json.loads((self.repo / CONFIG_NAME).read_text(encoding='utf-8'))
        self.assertEqual(config['setup'], ['npm', 'ci'])
        self.assertTrue(any('have not been run' in message for message in self.messages))

    def test_manifest_suggestions_are_stable_without_command_execution(self):
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_checks.py').write_text(
            'import unittest\nclass Checks(unittest.TestCase):\n'
            '    def test_value(self):\n        self.assertTrue(True)\n', encoding='utf-8')
        manifests = {'pyproject.toml': '[project]\nname = "example"\n',
                     'package.json': '{"scripts": {"test": "node --test"}}',
                     'Cargo.toml': '[workspace]\nmembers = []\n',
                     'go.mod': 'module example.com/project\n\ngo 1.22\n'}
        for name, source in manifests.items():
            (self.repo / name).write_text(source, encoding='utf-8')
        with patch('subprocess.run', side_effect=AssertionError('No commands during suggestions')):
            suggestions = command_suggestions(self.repo)
        self.assertEqual([item['command'] for item in suggestions],
                         ['python -m unittest discover -s tests', 'npm test', 'cargo test', 'go test ./...'])

    def _write_test(self, source, name='test_checks.py'):
        tests = self.repo / 'tests'
        tests.mkdir(exist_ok=True)
        path = tests / name
        path.write_text(source, encoding='utf-8')
        return path

    def test_unknown_python_framework_is_not_guessed_from_manifests(self):
        self._write_test('def test_value():\n    assert True\n')
        for name, source in {'pyproject.toml': '[project]\nname = "example"\n',
                             'setup.py': 'from setuptools import setup\nsetup()\n',
                             'setup.cfg': '[metadata]\nname = example\n'}.items():
            (self.repo / name).write_text(source, encoding='utf-8')
        self.assertEqual(command_suggestions(self.repo), [])

    def test_pytest_imports_and_functions_select_pytest_without_a_manifest(self):
        sources = [
            'import pytest\ndef test_value():\n    assert True\n',
            'from pytest import raises\ndef test_value():\n    assert True\n',
            'import pytest as checks\nclass TestValue:\n'
            '    def test_value(self):\n        assert True\n',
        ]
        for source in sources:
            with self.subTest(source=source):
                self._write_test(source)
                self.assertEqual([item['command'] for item in command_suggestions(self.repo)],
                                 ['python -m pytest'])

    def test_explicit_pytest_configuration_and_dependency_groups_select_pytest(self):
        # These functions are real pytest tests, but contain no identifying imports.
        self._write_test('def test_value():\n    assert True\n')
        self.assertEqual(command_suggestions(self.repo), [])
        manifests = [
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
            '[project]\nname = "example"\ndependencies = ["PyTest[example]>=8"]\n',
            '[project.optional-dependencies]\ntest = ["pytest; python_version >= \'3.11\'"]\n',
            '[dependency-groups]\ntest = ["pytest>=8"]\n',
            '[tool.poetry.dependencies]\npytest = "^8"\n',
            '[tool.poetry.dev-dependencies]\npytest = {version = "^8"}\n',
            '[tool.poetry.group.test.dependencies]\npytest = "^8"\n',
            '[tool.pdm.dev-dependencies]\ntest = ["pytest>=8"]\n',
        ]
        for source in manifests:
            with self.subTest(manifest=source):
                (self.repo / 'pyproject.toml').write_text(source, encoding='utf-8')
                self.assertEqual([item['command'] for item in command_suggestions(self.repo)],
                                 ['python -m pytest'])

    def test_pytest_plugins_prose_and_invalid_dependency_shapes_do_not_guess(self):
        self._write_test('def test_value():\n    assert True\n')
        manifests = [
            '[project]\ndescription = "pytest is useful"\n'
            'dependencies = ["pytest-cov", "my-pytest", "pytests"]\n',
            '[tool.other]\nrunner = "pytest"\n',
            '[project]\ndependencies = "pytest"\n',
            '[dependency-groups]\ntest = {pytest = "8"}\n',
            '[tool]\npytest = "not a configuration table"\n',
            '[tool.poetry.dependencies]\npytest = false\n',
        ]
        for source in manifests:
            with self.subTest(manifest=source):
                (self.repo / 'pyproject.toml').write_text(source, encoding='utf-8')
                self.assertEqual(command_suggestions(self.repo), [])

    def test_unittest_testcase_import_aliases_select_unittest(self):
        aliases = [
            ('import unittest', 'unittest.TestCase'),
            ('import unittest as checks', 'checks.TestCase'),
            ('from unittest import TestCase', 'TestCase'),
            ('from unittest import TestCase as BaseCase', 'BaseCase'),
            ('import unittest.case as checks', 'checks.TestCase'),
            ('from unittest.case import TestCase as BaseCase', 'BaseCase'),
        ]
        for imported, base in aliases:
            with self.subTest(imported=imported):
                self._write_test(f'{imported}\nclass Checks({base}):\n'
                                 '    def test_value(self):\n        self.assertTrue(True)\n')
                self.assertEqual([item['command'] for item in command_suggestions(self.repo)],
                                 ['python -m unittest discover -s tests'])
        self._write_test('from another_framework import TestCase\n'
                         'class Checks(TestCase):\n    def test_value(self):\n        pass\n')
        self.assertEqual(command_suggestions(self.repo), [])

    def test_mixed_pytest_and_unittest_suggests_pytest_only(self):
        self._write_test('import unittest\nclass Checks(unittest.TestCase):\n'
                         '    def test_value(self):\n        self.assertTrue(True)\n', 'test_a_unit.py')
        self._write_test('import pytest\ndef test_value():\n    assert True\n', 'test_b_pytest.py')
        self.assertEqual([item['command'] for item in command_suggestions(self.repo)],
                         ['python -m pytest'])

    def test_bad_syntax_is_ignored_and_other_real_tests_are_recognized(self):
        self._write_test('import pytest\ndef test_broken(:\n', 'test_a_broken.py')
        self._write_test('import unittest\nclass Checks(unittest.TestCase):\n'
                         '    def test_value(self):\n        self.assertTrue(True)\n', 'test_b_unit.py')
        self.assertEqual([item['command'] for item in command_suggestions(self.repo)],
                         ['python -m unittest discover -s tests'])

    def test_suggestions_never_execute_malicious_top_level_test_or_setup_code(self):
        marker = self.repo / 'must-not-exist'
        hostile = f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n'
        (self.repo / 'setup.py').write_text(hostile, encoding='utf-8')
        self._write_test(hostile + 'import pytest\ndef test_value():\n    assert True\n')
        with patch('subprocess.run', side_effect=AssertionError('No commands during suggestions')):
            self.assertEqual([item['command'] for item in command_suggestions(self.repo)],
                             ['python -m pytest'])
        self.assertFalse(marker.exists())

    def test_framework_scan_ignores_nested_and_non_test_files(self):
        tests = self.repo / 'tests'
        (tests / 'nested').mkdir(parents=True)
        source = 'import pytest\ndef test_value():\n    assert True\n'
        (tests / 'nested/test_checks.py').write_text(source, encoding='utf-8')
        (tests / 'helper.py').write_text(source, encoding='utf-8')
        self.assertEqual(command_suggestions(self.repo), [])

    def test_framework_scan_refuses_symlinked_files_and_test_directory(self):
        outside = Path(self.temporary.name) / 'outside-tests'
        outside.mkdir()
        source = outside / 'test_checks.py'
        source.write_text('import pytest\ndef test_value():\n    assert True\n', encoding='utf-8')
        tests = self.repo / 'tests'
        tests.mkdir()
        link = tests / 'test_checks.py'
        try:
            link.symlink_to(source)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation is unavailable')
        self.assertEqual(command_suggestions(self.repo), [])
        link.unlink()
        tests.rmdir()
        tests.symlink_to(outside, target_is_directory=True)
        self.assertEqual(command_suggestions(self.repo), [])

    def test_framework_scan_reads_at_most_64_files_in_stable_name_order(self):
        source = 'import unittest\nclass Checks(unittest.TestCase):\n'
        source += '    def test_value(self):\n        self.assertTrue(True)\n'
        for number in range(65):
            self._write_test(source if number == 64 else '# No known framework.\n',
                             f'test_{number:02}.py')
        with patch('rulebisect.onboarding.ast.parse', wraps=ast.parse) as parse:
            self.assertEqual(command_suggestions(self.repo), [])
            self.assertLessEqual(parse.call_count, 64)
        self._write_test(source, 'test_63.py')
        self.assertEqual([item['command'] for item in command_suggestions(self.repo)],
                         ['python -m unittest discover -s tests'])

    def test_framework_scan_read_budget_is_one_mibibyte(self):
        padded = b'#' + b'x' * (256 * 1024 - 2) + b'\n'
        self.assertEqual(len(padded), 256 * 1024)
        tests = self.repo / 'tests'
        tests.mkdir()
        for number in range(4):
            path = tests / f'test_{number:02}.py'
            path.write_bytes(padded)
            self.assertEqual(path.stat().st_size, 256 * 1024)
        self._write_test('import pytest\ndef test_value():\n    assert True\n', 'test_04.py')
        with patch('rulebisect.onboarding.ast.parse', wraps=ast.parse) as parse:
            self.assertEqual(command_suggestions(self.repo), [])
            self.assertEqual(sum(len(call.args[0]) for call in parse.call_args_list), 1024 * 1024)

    def test_framework_scan_skips_files_larger_than_256_kibibytes(self):
        self._write_test('import pytest\ndef test_value():\n    assert True\n#' + 'x' * (256 * 1024),
                         'test_a_oversized.py')
        self._write_test('import unittest\nclass Checks(unittest.TestCase):\n'
                         '    def test_value(self):\n        self.assertTrue(True)\n', 'test_b_unit.py')
        with patch('rulebisect.onboarding.ast.parse', wraps=ast.parse) as parse:
            self.assertEqual([item['command'] for item in command_suggestions(self.repo)],
                             ['python -m unittest discover -s tests'])
            self.assertTrue(all(len(call.args[0]) <= 256 * 1024 for call in parse.call_args_list))

    def test_invalid_or_irrelevant_manifests_do_not_crash_or_suggest(self):
        (self.repo / 'tests').mkdir()
        for name in ('pyproject.toml', 'Cargo.toml', 'package.json', 'go.mod'):
            (self.repo / name).write_text('not a valid manifest', encoding='utf-8')
        self.assertEqual(command_suggestions(self.repo), [])
        for package in ([], {'scripts': []}, {'scripts': {'test': 1}},
                        {'scripts': {'test': ''}},
                        {'scripts': {'test': 'echo "Error: no test specified" && exit 1'}}):
            (self.repo / 'package.json').write_text(json.dumps(package), encoding='utf-8')
            self.assertEqual(command_suggestions(self.repo), [])
        (self.repo / 'package.json').write_bytes(b'\xff')
        self.assertEqual(command_suggestions(self.repo), [])
        (self.repo / 'package.json').write_text(' ' * (256 * 1024 + 1), encoding='utf-8')
        self.assertEqual(command_suggestions(self.repo), [])

    def test_nested_git_path_uses_root_and_override_discovery(self):
        nested = self.repo / 'src'
        nested.mkdir()
        (self.repo / 'AGENTS.override.md').write_text('Override', encoding='utf-8')
        (nested / 'AGENTS.md').write_text('Nested rules', encoding='utf-8')
        subprocess.run(['git', 'add', 'src/AGENTS.md'], cwd=self.repo, check=True)
        answers = iter(['Keep API', 'python verify.py', '', ''])
        path = run_wizard(nested, input_fn=lambda _: next(answers), print_fn=self.messages.append)
        config = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(path.parent, self.repo.resolve())
        self.assertEqual(config['instructions'], ['AGENTS.override.md', 'src/AGENTS.md'])

    def test_explicit_nested_and_space_paths_work_without_agents(self):
        (self.repo / 'AGENTS.md').unlink()
        paths = ['rules/Review Rules.md', 'skills/format/SKILL.md']
        originals = {}
        for name in paths:
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('Use the selected instruction.\n', encoding='utf-8')
            originals[name] = target.read_bytes()
        answers = iter(['Preserve formatting', 'python verify.py', '', ''])
        # Keep the old positional input/print hooks compatible with the new option.
        run_wizard(self.repo, lambda _: next(answers), self.messages.append,
                   instructions=['./rules/Review Rules.md', 'skills/format/SKILL.md'])
        config = json.loads((self.repo / CONFIG_NAME).read_text(encoding='utf-8'))
        self.assertEqual(config['instructions'], paths)
        self.assertFalse((self.repo / 'AGENTS.md').exists())
        self.assertEqual({name: (self.repo / name).read_bytes() for name in paths}, originals)
        self.assertTrue(any(all(name in message for name in paths) for message in self.messages))

    def test_explicit_selection_replaces_automatic_discovery(self):
        (self.repo / 'AGENTS.override.md').write_text('Automatic override.\n', encoding='utf-8')
        (self.repo / 'rules.md').write_text('Selected rules.\n', encoding='utf-8')
        with patch('rulebisect.onboarding.discover_instructions',
                   side_effect=AssertionError('Explicit files must not trigger discovery')):
            self.wizard(['Task', 'python verify.py', '', ''], instructions=['rules.md'])
        config = json.loads((self.repo / CONFIG_NAME).read_text(encoding='utf-8'))
        self.assertEqual(config['instructions'], ['rules.md'])

    def test_invalid_explicit_selection_refused_before_prompts_without_writes(self):
        before = {path.name: path.read_bytes() for path in self.repo.iterdir() if path.is_file()}
        invalid = [[], 'AGENTS.md', ['AGENTS.md', './AGENTS.md'], ['missing.md'],
                   ['../AGENTS.md'], [str((self.repo / 'AGENTS.md').resolve())],
                   ['.git/config'], ['.GIT/config'], [''], [None], ['.']]
        for instructions in invalid:
            with self.subTest(instructions=instructions), self.assertRaises(ValueError):
                run_wizard(self.repo, input_fn=lambda _: self.fail('Must not prompt'),
                           print_fn=self.messages.append, instructions=instructions)
            self.assert_unconfigured()
            self.assertEqual({path.name: path.read_bytes() for path in self.repo.iterdir() if path.is_file()}, before)
        self.assertEqual(self.messages, [])

    def test_explicit_selection_cancellation_never_creates_or_edits_files(self):
        rules = self.repo / 'custom.md'
        rules.write_text('Original selected rules.\n', encoding='utf-8')
        original = rules.read_bytes()
        complete = ['Task', 'python verify.py', '', '']
        for error_type in (EOFError, KeyboardInterrupt):
            for position in range(len(complete)):
                with self.subTest(error=error_type.__name__, position=position):
                    answers = iter(complete[:position])
                    def ask(_):
                        try:
                            return next(answers)
                        except StopIteration:
                            raise error_type
                    with self.assertRaisesRegex(ValueError, 'cancelled'):
                        run_wizard(self.repo, input_fn=ask, print_fn=self.messages.append,
                                   instructions=['custom.md'])
                    self.assert_unconfigured()
                    self.assertEqual(rules.read_bytes(), original)

    @unittest.skipIf(os.name == 'nt', 'Symlink creation may require Windows privileges')
    def test_symlinked_explicit_and_discovered_paths_rejected_before_prompts(self):
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        rule = outside / 'AGENTS.md'
        rule.write_text('Outside instructions.\n', encoding='utf-8')
        original = rule.read_bytes()
        (self.repo / 'linked.md').symlink_to(rule)
        (self.repo / 'linked').symlink_to(outside, target_is_directory=True)
        for instructions in (['linked.md'], ['linked/AGENTS.md']):
            with self.subTest(instructions=instructions), self.assertRaisesRegex(ValueError, 'symlinks'):
                run_wizard(self.repo, input_fn=lambda _: self.fail('Must not prompt'),
                           print_fn=self.messages.append, instructions=instructions)
            self.assert_unconfigured()
        # Track a real nested file before its parent is replaced by a symlink.
        (self.repo / 'linked').unlink()
        (self.repo / 'linked').mkdir()
        (self.repo / 'linked/AGENTS.md').write_text('Tracked instructions.\n', encoding='utf-8')
        subprocess.run(['git', 'add', 'linked/AGENTS.md'], cwd=self.repo, check=True)
        (self.repo / 'linked/AGENTS.md').unlink()
        (self.repo / 'linked').rmdir()
        (self.repo / 'linked').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            run_wizard(self.repo, input_fn=lambda _: self.fail('Must not prompt'), print_fn=self.messages.append)
        self.assert_unconfigured()
        self.assertEqual(rule.read_bytes(), original)
        self.assertEqual(self.messages, [])

    def test_missing_instructions_and_existing_wrapper_refused_without_prompts(self):
        (self.repo / 'AGENTS.md').unlink()
        with self.assertRaisesRegex(ValueError, 'init --wizard --instructions FILE'):
            run_wizard(self.repo, input_fn=lambda _: self.fail('Must not prompt'))
        (self.repo / 'AGENTS.md').write_text('Rules', encoding='utf-8')
        (self.repo / '.rulebisect-verify.py').write_text('original', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            run_wizard(self.repo, input_fn=lambda _: self.fail('Must not prompt'))
        self.assertFalse((self.repo / CONFIG_NAME).exists())


if __name__ == '__main__':
    unittest.main()
