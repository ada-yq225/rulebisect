"""User journeys for explicit baseline inputs and configured instruction selection."""
import contextlib
import io
import json
import subprocess
import unittest
import unicodedata
from unittest.mock import patch

import test_rulebisect as fixtures
from rulebisect.cli import main
from rulebisect.onboarding import run_wizard
from rulebisect.setup import CONFIG_NAME, init_config


class InputWorkflowTests(unittest.TestCase):
    setUp = fixtures.IntegrationTests.setUp
    tearDown = fixtures.IntegrationTests.tearDown

    def cli(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(list(args))
        return code, output.getvalue(), errors.getvalue()

    def test_explicit_source_survives_all_offline_workflows_without_staging(self):
        (self.repo / 'new module.py').write_text('VALUE = 42\n', encoding='utf-8')
        (self.repo / 'not selected.txt').write_text('outside the experiment\n', encoding='utf-8')
        index = subprocess.check_output(['git', 'ls-files', '-z'], cwd=self.repo)
        code, _, errors = self.cli('init', '--repo', str(self.repo), '--task', 'Keep the input',
                                  '--check', 'python "new module.py"', '--include', 'new module.py')
        self.assertEqual(code, 0, errors)
        saved = json.loads((self.repo / CONFIG_NAME).read_text(encoding='utf-8'))
        self.assertEqual(saved['include_files'], ['new module.py'])
        self.assertNotIn('new module.py', saved['protected_files'])
        for args in [('status', '--json'), ('doctor', '--offline', '--json'), ('plan', '--json')]:
            code, output, errors = self.cli(*args, '--repo', str(self.repo))
            self.assertEqual(code, 0, errors)
            result = json.loads(output)
            snapshot = result.get('scope', result)['snapshot_inputs']
            self.assertIn('new module.py', snapshot['included_files'])
            self.assertIn('not selected.txt', snapshot['excluded_untracked'])
            self.assertNotIn('new module.py', snapshot['excluded_untracked'])
        for extra in [[], ['--all']]:
            code, output, errors = self.cli('check', *extra, '--require-pass', '--repo', str(self.repo))
            self.assertEqual(code, 0, output + errors)
            self.assertIn('not selected.txt', output)
        self.assertEqual(index, subprocess.check_output(['git', 'ls-files', '-z'], cwd=self.repo))
        self.assertEqual((self.repo / 'new module.py').read_text(encoding='utf-8'), 'VALUE = 42\n')

    def test_bad_include_fails_before_prompts_or_generated_files(self):
        for included in [['missing.py'], ['../outside.py'], ['.git/config'], ['verify.py', './verify.py']]:
            with self.subTest(included=included):
                with self.assertRaises(ValueError):
                    init_config(self.repo, 'Task', 'python verify.py', None, include_files=included)
                with patch('builtins.input', side_effect=AssertionError('No prompt')):
                    with self.assertRaises(ValueError):
                        run_wizard(self.repo, input_fn=lambda _: self.fail('Prompted'), include_files=included)
                self.assertFalse((self.repo / CONFIG_NAME).exists())
                self.assertFalse((self.repo / '.rulebisect-verify.py').exists())

    def test_incorrect_include_component_case_fails_init_and_wizard_before_writes(self):
        folder = self.repo / 'Inputs'
        folder.mkdir()
        (folder / 'NewHelper.py').write_text('VALUE = 42\n', encoding='utf-8')
        for included in [['Inputs/newhelper.py'], ['inputs/NewHelper.py'], ['inputs/newhelper.py']]:
            with self.subTest(included=included):
                with self.assertRaisesRegex(ValueError, 'incorrect casing') as caught:
                    init_config(self.repo, 'Task', 'python verify.py', None, include_files=included)
                self.assertIn('Inputs/NewHelper.py', str(caught.exception))
                with self.assertRaisesRegex(ValueError, 'incorrect casing'):
                    run_wizard(self.repo, input_fn=lambda _: self.fail('Prompted'), include_files=included)
                self.assertFalse((self.repo / CONFIG_NAME).exists())
                self.assertFalse((self.repo / '.rulebisect-verify.py').exists())

    def test_unicode_literal_inputs_survive_init_and_prepare_without_false_omissions(self):
        folder = self.repo / '资料'
        folder.mkdir()
        (folder / 'café[1].py').write_text('VALUE = 42\n', encoding='utf-8')
        include = '资料/café[1].py'
        path = init_config(self.repo, 'Keep Unicode input.', 'python verify.py', None,
                           include_files=['./' + include])
        saved = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(saved['include_files'], [include])
        code, output, errors = self.cli('plan', '--repo', str(self.repo), '--json')
        self.assertEqual(code, 0, errors)
        inputs = json.loads(output)['snapshot_inputs']
        self.assertIn(include, inputs['included_files'])
        self.assertEqual(inputs['extra_files'], [include])
        self.assertNotIn(include, inputs['excluded_untracked'])
        equivalent = unicodedata.normalize('NFD', include)
        if (self.repo / equivalent).is_file():
            from rulebisect.setup import validate_included_files
            self.assertEqual(validate_included_files(self.repo.resolve(), [equivalent]), [equivalent])

    def test_wizard_preserves_explicit_input_and_does_not_execute_it(self):
        (self.repo / 'input.txt').write_text('initial', encoding='utf-8')
        answers = iter(['Keep input', 'python -c "raise SystemExit(0)"', '', ''])
        with patch('rulebisect.experiment.run_process', side_effect=AssertionError('No execution')):
            path = run_wizard(self.repo, input_fn=lambda _: next(answers), print_fn=lambda _: None,
                              include_files=['input.txt'])
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['include_files'], ['input.txt'])

    def test_inspect_uses_default_selection_and_saved_unit_mode(self):
        (self.repo / 'custom rules.md').write_text('One paragraph.\n\nTwo paragraphs.\n', encoding='utf-8')
        config = dict(self.config, instructions=['custom rules.md'], unit_mode='file')
        (self.repo / CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        code, output, errors = self.cli('inspect', '--repo', str(self.repo), '--json')
        self.assertEqual(code, 0, errors)
        rules = json.loads(output)
        self.assertEqual(len(rules), 1)
        self.assertTrue(rules[0]['path'].endswith('custom rules.md'))
        code, output, errors = self.cli('inspect', '--repo', str(self.repo), '--unit-mode', 'paragraph', '--json')
        self.assertEqual(code, 0, errors)
        self.assertEqual(len(json.loads(output)), 2)
        config['unit_mode'] = None
        (self.repo / CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        code, output, errors = self.cli('inspect', '--repo', str(self.repo), '--json')
        self.assertEqual(code, 2)
        self.assertIn('unit_mode', errors)

    def test_custom_config_inspect_draft_compare_preserve_selection(self):
        (self.repo / 'custom rules.md').write_text('Use these rules.\n', encoding='utf-8')
        path = self.root / 'custom settings.json'
        path.write_text(json.dumps(dict(self.config, instructions=['custom rules.md'])), encoding='utf-8')
        code, output, errors = self.cli('inspect', '--repo', str(self.repo), '--config', str(path), '--json')
        self.assertEqual(code, 0, errors)
        self.assertTrue(all(rule['path'].endswith('custom rules.md') for rule in json.loads(output)))
        proposal = self.root / 'proposal'
        code, output, errors = self.cli('draft', '--repo', str(self.repo), '--config', str(path), '--out', str(proposal))
        self.assertEqual(code, 0, errors)
        self.assertIn('--config', output)
        self.assertIn('custom settings.json', output)
        code, output, errors = self.cli('compare', '--repo', str(self.repo), '--config', str(path),
                                      '--proposed', str(proposal), '--plan')
        self.assertEqual(code, 0, errors)
        plan = json.loads(output)
        self.assertEqual(plan['instruction_files'], ['custom rules.md'])
        self.assertIn('custom rules.md', plan['snapshot_inputs']['included_files'])

    def test_inspect_explicit_missing_config_and_conflicting_inputs_do_not_fallback(self):
        missing = self.root / 'missing.json'
        for args in [[], [str(self.repo / 'AGENTS.md')]]:
            code, output, errors = self.cli('inspect', *args, '--repo', str(self.repo), '--config', str(missing))
            self.assertEqual(code, 2)
            self.assertFalse(output)
            self.assertTrue(errors)

    def test_doctor_snapshot_matches_full_suite_check_oracle_union(self):
        (self.repo / 'other oracle.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
        config = dict(self.config, cases=[{'id': 'first'}, {'id': 'second', 'oracle': 'other oracle.py'}])
        (self.repo / CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        code, output, errors = self.cli('doctor', '--offline', '--repo', str(self.repo), '--json')
        self.assertEqual(code, 0, errors)
        expected = json.loads(output)['scope']['snapshot_inputs']
        evidence = self.root / 'checks'
        code, output, errors = self.cli('check', '--all', '--repo', str(self.repo), '--out', str(evidence))
        self.assertEqual(code, 0, output + errors)
        report = json.loads((evidence / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(expected, report['snapshot_inputs'])
