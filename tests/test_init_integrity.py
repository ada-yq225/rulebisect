import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rulebisect.cli import main
from rulebisect.onboarding import run_wizard
from rulebisect.setup import CONFIG_NAME, init_config


class InitIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='rulebisect-init-')
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True)
        (self.repo / 'AGENTS.md').write_text('Preserve useful outputs.\n', encoding='utf-8')
        (self.repo / 'verify.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
        subprocess.run(['git', 'add', 'AGENTS.md', 'verify.py'], cwd=self.repo, check=True)
        self.config = self.repo / CONFIG_NAME
        self.wrapper = self.repo / '.rulebisect-verify.py'
        self.checks = [{'type': 'file_exists', 'path': 'result.txt'}]

    def tearDown(self):
        self.temporary.cleanup()

    def initialize(self, **options):
        return init_config(self.repo, 'Write an observable result.', None, None,
                           assertions=options.pop('assertions', self.checks), **options)

    def assert_unconfigured(self):
        self.assertFalse(self.config.exists())
        self.assertFalse(self.wrapper.exists())

    def symlink(self, target, link, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Symlinks unavailable: {type(error).__name__}')

    def test_broken_config_symlink_is_preserved_and_never_followed(self):
        external = self.root / 'external-config.json'
        self.symlink(external, self.config)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.initialize()
        self.assertTrue(self.config.is_symlink())
        self.assertFalse(external.exists())
        self.assertFalse(self.wrapper.exists())

    def test_failed_config_open_removes_only_the_new_wrapper_and_allows_retry(self):
        original_open = Path.open
        def fail_config(path, mode='r', *args, **kwargs):
            if path == self.config and mode == 'x':
                raise OSError('configuration write unavailable')
            return original_open(path, mode, *args, **kwargs)
        with patch('pathlib.Path.open', fail_config), self.assertRaisesRegex(OSError, 'unavailable'):
            self.initialize()
        self.assert_unconfigured()
        self.assertTrue(self.initialize().is_file())

    def test_partial_config_write_errors_and_interrupts_are_rolled_back(self):
        original_open = Path.open
        for error_type in (OSError, KeyboardInterrupt):
            with self.subTest(error=error_type.__name__):
                class FailingWriter:
                    def __init__(self, stream):
                        self.stream = stream
                    def __enter__(self):
                        self.stream.__enter__()
                        return self
                    def __exit__(self, *arguments):
                        return self.stream.__exit__(*arguments)
                    def write(self, content):
                        self.stream.write(content[:10])
                        raise error_type('interrupted configuration write')
                def fail_write(path, mode='r', *args, **kwargs):
                    stream = original_open(path, mode, *args, **kwargs)
                    return FailingWriter(stream) if path == self.config and mode == 'x' else stream
                with patch('pathlib.Path.open', fail_write), self.assertRaises(error_type):
                    self.initialize()
                self.assert_unconfigured()

    def test_existing_oracle_is_preserved_when_config_creation_fails(self):
        original_open = Path.open
        original = (self.repo / 'verify.py').read_bytes()
        def fail_config(path, mode='r', *args, **kwargs):
            if path == self.config and mode == 'x':
                raise KeyboardInterrupt
            return original_open(path, mode, *args, **kwargs)
        with patch('pathlib.Path.open', fail_config), self.assertRaises(KeyboardInterrupt):
            init_config(self.repo, 'Task', None, None, oracle='verify.py')
        self.assertEqual((self.repo / 'verify.py').read_bytes(), original)
        self.assert_unconfigured()

    def test_config_created_during_initialization_is_not_overwritten_or_removed(self):
        original_open = Path.open
        user_content = '{"user": "intervening configuration"}'
        def create_config_first(path, mode='r', *args, **kwargs):
            if path == self.config and mode == 'x':
                with original_open(path, 'w', encoding='utf-8') as stream:
                    stream.write(user_content)
            return original_open(path, mode, *args, **kwargs)
        with patch('pathlib.Path.open', create_config_first), self.assertRaises(FileExistsError):
            self.initialize()
        self.assertEqual(self.config.read_text(encoding='utf-8'), user_content)
        self.assertFalse(self.wrapper.exists())

    def test_wrapper_created_during_initialization_is_not_overwritten_or_removed(self):
        original_open = Path.open
        user_content = '# user-owned verifier\n'
        def create_wrapper_first(path, mode='r', *args, **kwargs):
            if path == self.wrapper and mode == 'x':
                with original_open(path, 'w', encoding='utf-8') as stream:
                    stream.write(user_content)
            return original_open(path, mode, *args, **kwargs)
        with patch('pathlib.Path.open', create_wrapper_first), self.assertRaises(FileExistsError):
            self.initialize()
        self.assertEqual(self.wrapper.read_text(encoding='utf-8'), user_content)
        self.assertFalse(self.config.exists())

    def test_instruction_and_oracle_symlink_ancestors_fail_before_writes(self):
        directory = self.repo / 'real'
        directory.mkdir()
        (directory / 'AGENTS.md').write_text('Real rules.\n', encoding='utf-8')
        (directory / 'verify.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
        self.symlink(directory, self.repo / 'alias', directory=True)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            self.initialize(instructions=['alias/AGENTS.md'])
        self.assert_unconfigured()
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            init_config(self.repo, 'Task', None, None, oracle='alias/verify.py')
        self.assert_unconfigured()

    def test_git_paths_and_normalized_role_overlap_fail_before_writes(self):
        with self.assertRaisesRegex(ValueError, 'repository-relative'):
            self.initialize(instructions=['.git/config'])
        with self.assertRaisesRegex(ValueError, 'cannot also be'):
            init_config(self.repo, 'Task', None, None, oracle='./AGENTS.md', instructions=['AGENTS.md'])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.initialize(instructions=['AGENTS.md', './AGENTS.md'])
        self.assert_unconfigured()

    def test_deep_json_cli_init_and_case_fail_cleanly_without_changes(self):
        source = self.root / 'deep.json'
        source.write_text('[' * 2000 + '0' + ']' * 2000, encoding='utf-8')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = main(['init', '--repo', str(self.repo), '--task', 'Task', '--assertions', str(source)])
        self.assertEqual(code, 2)
        self.assertIn('nested too deeply', stderr.getvalue())
        self.assertNotIn('Traceback', stderr.getvalue())
        self.assert_unconfigured()
        init_config(self.repo, 'Task', None, None, oracle='verify.py')
        original = self.config.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = main(['case', 'add', 'new', '--repo', str(self.repo), '--task', 'Task', '--assertions', str(source)])
        self.assertEqual(code, 2)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse((self.repo / '.rulebisect').exists())

    def test_wizard_reprompts_after_deep_assertions_file(self):
        source = self.root / 'deep.json'
        source.write_text('[' * 2000 + '0' + ']' * 2000, encoding='utf-8')
        answers = iter(['Task', '@' + str(source), ':exists', 'result.txt', '', ''])
        messages = []
        run_wizard(self.repo, input_fn=lambda _: next(answers), print_fn=messages.append)
        self.assertTrue(any('nested too deeply' in message for message in messages))
        config = json.loads(self.config.read_text(encoding='utf-8'))
        self.assertEqual(config['oracle'], '.rulebisect-verify.py')
        self.assertIn('file_exists', self.wrapper.read_text(encoding='utf-8'))

    def test_wizard_reprompts_after_deep_builtin_json_value(self):
        deep = '[' * 2000 + '0' + ']' * 2000
        answers = iter(['Task', ':json', 'result.json', '', deep, ':exists', 'result.txt', '', ''])
        messages = []
        run_wizard(self.repo, input_fn=lambda _: next(answers), print_fn=messages.append)
        self.assertTrue(any('nested too deeply' in message for message in messages))
        self.assertIn('file_exists', self.wrapper.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
