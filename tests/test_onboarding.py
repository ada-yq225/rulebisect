from __future__ import annotations

import json
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

    def wizard(self, answers):
        answers = iter(answers)
        return run_wizard(self.repo, input_fn=lambda _: next(answers), print_fn=self.messages.append)

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

    def test_missing_instructions_and_existing_wrapper_refused_without_prompts(self):
        (self.repo / 'AGENTS.md').unlink()
        with self.assertRaisesRegex(ValueError, 'No AGENTS.md'):
            run_wizard(self.repo, input_fn=lambda _: self.fail('Must not prompt'))
        (self.repo / 'AGENTS.md').write_text('Rules', encoding='utf-8')
        (self.repo / '.rulebisect-verify.py').write_text('original', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            run_wizard(self.repo, input_fn=lambda _: self.fail('Must not prompt'))
        self.assertFalse((self.repo / CONFIG_NAME).exists())


if __name__ == '__main__':
    unittest.main()
