from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rulebisect.comparison import Comparison
from rulebisect.suite import add_case, list_cases, remove_case


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        (self.repo / 'AGENTS.md').write_text('Use modern output.\n', encoding='utf-8')
        (self.repo / 'verify.py').write_text('raise SystemExit(1)\n', encoding='utf-8')
        self.config_path = self.repo / '.rulebisect.json'
        self.config = {'task': 'Original task', 'instructions': ['AGENTS.md'],
                       'oracle': 'verify.py', 'verify': ['{python}', '{oracle}'],
                       'protected_files': ['verify.py'], 'repeats': 2, 'max_runs': 12,
                       'timeout': 15, 'setup': ['{python}', 'prepare.py'],
                       'future_setting': {'language': '中文', 'keep': [1, 2]}}
        self.write_config(self.config)

    def tearDown(self):
        self.temporary.cleanup()

    def write_config(self, config):
        self.config_path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')

    def read_config(self):
        return json.loads(self.config_path.read_text(encoding='utf-8'))

    def add(self, case_id='new_task', **options):
        return add_case(self.repo, self.config_path, case_id, options.pop('task', '新任务'),
                        **options)

    def test_adding_first_case_preserves_original_and_every_config_setting(self):
        with patch('subprocess.run', side_effect=AssertionError('adding must not execute commands')):
            result = self.add(check='python -m unittest test_new')
        configured = self.read_config()
        self.assertEqual(configured['cases'][0], {'id': 'task'})
        self.assertEqual({key: value for key, value in configured.items() if key != 'cases'}, self.config)
        self.assertEqual(result['case_count'], 2)
        self.assertTrue(result['generated_oracle'])
        self.assertEqual(result['verify'], ['{python}', '{oracle}'])
        self.assertEqual(result['oracle'], '.rulebisect/checks/new_task.py')
        listed = list_cases(self.config_path)
        self.assertEqual([case['id'] for case in listed], ['task', 'new_task'])
        self.assertEqual(listed[0]['task'], 'Original task')
        self.assertEqual(listed[0]['oracle'], 'verify.py')
        self.assertEqual(listed[1]['task'], '新任务')
        self.assertEqual(listed[1]['protected_files'], ['verify.py'])

    def test_existing_cases_are_preserved_and_oracle_is_not_modified(self):
        self.config['cases'] = [{'id': 'modern', 'task': 'Existing modern task',
                                 'protected_files': ['test_modern.py']}]
        self.write_config(self.config)
        (self.repo / 'test_modern.py').write_text('Existing protected test', encoding='utf-8')
        original = (self.repo / 'verify.py').read_bytes()
        result = self.add(oracle='./verify.py')
        self.assertFalse(result['generated_oracle'])
        self.assertEqual(result['oracle'], 'verify.py')
        self.assertEqual(self.read_config()['cases'][0], self.config['cases'][0])
        self.assertEqual((self.repo / 'verify.py').read_bytes(), original)
        self.assertFalse((self.repo / '.rulebisect').exists())

    def test_invalid_ids_commands_and_tasks_have_no_partial_output(self):
        original = self.config_path.read_bytes()
        for case_id in ('task', 'TASK', '../escape', 'CON', 'nul', 'COM1', '', 'x' * 65):
            with self.subTest(case_id=case_id), self.assertRaises(ValueError):
                self.add(case_id, check='python verify.py')
        for check in ('', 'echo first && echo second', 'echo first > result.txt', 'python "unclosed', '\0bad'):
            with self.subTest(check=check), self.assertRaises(ValueError):
                self.add(check=check)
        for options in ({}, {'check': 'python verify.py', 'oracle': 'verify.py'},
                        {'oracle': '../outside.py'}, {'oracle': 'missing.py'},
                        {'oracle': 'AGENTS.md'}, {'task': ' ', 'check': 'python verify.py'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.add(**options)
        self.assertEqual(self.config_path.read_bytes(), original)
        self.assertFalse((self.repo / '.rulebisect').exists())

    def test_casefold_duplicate_is_rejected_before_creating_wrapper(self):
        self.config['cases'] = [{'id': 'Modern'}]
        self.write_config(self.config)
        with self.assertRaises(ValueError):
            self.add('modern', check='python verify.py')
        self.assertFalse((self.repo / '.rulebisect').exists())

    def test_existing_generated_path_is_never_overwritten(self):
        path = self.repo / '.rulebisect/checks/new_task.py'
        path.parent.mkdir(parents=True)
        path.write_text('User-owned verifier', encoding='utf-8')
        original = self.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.add(check='python verify.py')
        self.assertEqual(path.read_text(encoding='utf-8'), 'User-owned verifier')
        self.assertEqual(self.config_path.read_bytes(), original)

    def test_existing_wrapper_name_is_reserved_across_case_variants(self):
        path = self.repo / '.rulebisect/checks/NEW_TASK.py'
        path.parent.mkdir(parents=True)
        path.write_text('User-owned verifier', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.add(check='python verify.py')
        self.assertEqual(path.read_text(encoding='utf-8'), 'User-owned verifier')
        self.assertNotIn('cases', self.read_config())

    def test_failed_atomic_write_rolls_back_only_generated_wrapper(self):
        user_file = self.repo / '.rulebisect/checks/keep.py'
        user_file.parent.mkdir(parents=True)
        user_file.write_text('User-owned file', encoding='utf-8')
        original = self.config_path.read_bytes()
        with patch('rulebisect.suite.os.replace', side_effect=OSError('write rejected')):
            with self.assertRaisesRegex(OSError, 'write rejected'):
                self.add(check='python verify.py')
        self.assertEqual(self.config_path.read_bytes(), original)
        self.assertFalse((user_file.parent / 'new_task.py').exists())
        self.assertEqual(user_file.read_text(encoding='utf-8'), 'User-owned file')
        self.assertFalse(list(self.repo.glob('.rulebisect.json.*.tmp')))

    def test_concurrent_config_edit_is_preserved_and_wrapper_rolled_back(self):
        from rulebisect import suite
        original_write = suite._write_config
        def write_changed(path, config, original):
            path.write_text('{"user_edit": true}', encoding='utf-8')
            original_write(path, config, original)
        with patch('rulebisect.suite._write_config', side_effect=write_changed):
            with self.assertRaisesRegex(ValueError, 'Config changed'):
                self.add(check='python verify.py')
        self.assertEqual(self.read_config(), {'user_edit': True})
        self.assertFalse((self.repo / '.rulebisect/checks/new_task.py').exists())

    def test_wrapper_uses_current_python_and_maps_check_exit_codes(self):
        executable = self.repo / 'record.py'
        executable.write_text('import sys\nfrom pathlib import Path\n'
                              'Path("python-used.txt").write_text(sys.executable, encoding="utf-8")\n'
                              'raise SystemExit(int(sys.argv[1]))\n', encoding='utf-8')
        for value in (0, 1, 7):
            result = self.add(f'exit_{value}', check=f'python3 record.py {value}')
            completed = subprocess.run([sys.executable, str(self.repo / result['oracle'])],
                                       cwd=self.repo, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, value if value in (0, 1) else 2)
            self.assertEqual((self.repo / 'python-used.txt').read_text(encoding='utf-8'), sys.executable)
        missing = self.add('missing_check', check='rulebisect-certainly-missing-check-command')
        completed = subprocess.run([sys.executable, str(self.repo / missing['oracle'])],
                                   cwd=self.repo, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 2)
        self.assertIn('Verifier setup error', completed.stderr)

    def test_remove_preserves_files_and_refuses_last_or_unknown_case(self):
        result = self.add(check='python verify.py')
        wrapper = self.repo / result['oracle']
        before = wrapper.read_bytes()
        removed = remove_case(self.config_path, 'new_task')
        self.assertEqual(removed['case_count'], 1)
        self.assertEqual(removed['oracle_preserved'], result['oracle'])
        self.assertEqual(wrapper.read_bytes(), before)
        self.assertEqual(self.read_config()['cases'], [{'id': 'task'}])
        original = self.config_path.read_bytes()
        for case_id in ('task', 'missing'):
            with self.assertRaises(ValueError):
                remove_case(self.config_path, case_id)
        self.assertEqual(self.config_path.read_bytes(), original)

    def test_invalid_existing_schema_is_never_rewritten(self):
        for config in ([], {'cases': []}, {'cases': [{'id': 'bad', 'model': 'unsupported'}]}):
            self.write_config(config)
            original = self.config_path.read_bytes()
            for operation in (lambda: list_cases(self.config_path),
                              lambda: self.add(check='python verify.py'),
                              lambda: remove_case(self.config_path, 'bad')):
                with self.assertRaises(ValueError):
                    operation()
            self.assertEqual(self.config_path.read_bytes(), original)
        self.assertFalse((self.repo / '.rulebisect').exists())

    def test_custom_external_config_preserves_every_setting(self):
        self.config_path = self.root / 'custom-experiment.json'
        self.write_config(self.config)
        self.add(oracle='verify.py')
        configured = self.read_config()
        self.assertEqual(configured['future_setting'], self.config['future_setting'])
        self.assertEqual(configured['setup'], self.config['setup'])
        self.assertEqual(configured['cases'][1]['task'], '新任务')
        self.assertFalse(list(self.root.glob('custom-experiment.json.*.tmp')))

    def test_comparison_protects_new_untracked_wrappers_in_every_arm(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True)
        subprocess.run(['git', 'add', 'AGENTS.md', 'verify.py'], cwd=self.repo, check=True)
        self.config.pop('setup')
        self.write_config(self.config)
        result = self.add(check='python verify.py')
        proposed = self.root / 'proposed'
        proposed.mkdir()
        (proposed / 'AGENTS.md').write_text('New instruction\n', encoding='utf-8')
        comparison = Comparison(self.repo, self.read_config(), self.root / 'evidence',
                                None, 2, 12, 10, proposed)
        plan = comparison.prepare(check_codex=False)
        self.assertEqual(plan['required_calls'], 8)
        for experiment in comparison.experiments.values():
            self.assertIn(result['oracle'], experiment.protected)
            self.assertIn(result['oracle'], experiment.blobs)
        self.assertFalse((self.root / 'evidence').exists())

    @unittest.skipIf(os.name == 'nt', 'Symlink creation may require Windows privileges')
    def test_symlinked_oracle_ancestors_and_wrapper_parents_are_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'verify.py').write_text('raise SystemExit(0)', encoding='utf-8')
        (self.repo / 'linked').symlink_to(outside, target_is_directory=True)
        (self.repo / '.rulebisect').symlink_to(outside, target_is_directory=True)
        original = self.config_path.read_bytes()
        for options in ({'oracle': 'linked/verify.py'}, {'check': 'python verify.py'}):
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                self.add(**options)
        self.assertEqual(self.config_path.read_bytes(), original)
        self.assertEqual([path.name for path in outside.iterdir()], ['verify.py'])

    @unittest.skipIf(os.name == 'nt', 'Symlink creation may require Windows privileges')
    def test_symlink_config_is_not_replaced(self):
        alias = self.repo / 'config-link.json'
        alias.symlink_to(self.config_path)
        original = self.config_path.read_bytes()
        for operation in (lambda: list_cases(alias),
                          lambda: add_case(self.repo, alias, 'new_task', 'New task', oracle='verify.py'),
                          lambda: remove_case(alias, 'task')):
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                operation()
        self.assertTrue(alias.is_symlink())
        self.assertEqual(self.config_path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
