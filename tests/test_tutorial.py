"""Exercise the working tutorial as an independent local Git project."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rulebisect.setup import CONFIG_NAME
from rulebisect.tutorial import create_tutorial


class TutorialTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.target = self.root / 'try rules here'

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'core.fsmonitor=false', *args], cwd=self.target).decode()

    def test_editable_project_has_committed_baseline_and_two_distinct_contracts(self):
        self.assertEqual(create_tutorial(self.target), self.target)
        self.assertEqual(self.git('diff', '--name-only'), 'AGENTS.md\n')
        self.assertFalse(self.git('diff', '--cached', '--name-only'))
        self.assertNotEqual(self.git('show', 'HEAD:AGENTS.md'), (self.target / 'AGENTS.md').read_text())
        config = json.loads((self.target / CONFIG_NAME).read_text(encoding='utf-8'))
        self.assertIsNone(config.get('model'))
        self.assertEqual((config['repeats'], config['max_runs']), (2, 8))
        self.assertEqual([case['id'] for case in config['cases']], ['modern', 'legacy'])
        def check(client):
            return subprocess.run([sys.executable, '-I', str(self.target / f'verify_{client}.py')],
                                  cwd=self.target, capture_output=True).returncode
        self.assertEqual([check('modern'), check('legacy')], [1, 0])
        (self.target / 'labels.py').write_text(
            'def normalize_label(value, client):\n    return value.lower().strip()\n', encoding='utf-8')
        self.assertEqual([check('modern'), check('legacy')], [0, 1])

    def test_existing_paths_and_metadata_stay_untouched(self):
        self.target.mkdir()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            create_tutorial(self.target)
        self.assertEqual(list(self.target.iterdir()), [])
        occupied = self.root / 'existing file'
        occupied.write_bytes(b'Keep this')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            create_tutorial(occupied)
        self.assertEqual(occupied.read_bytes(), b'Keep this')
        with self.assertRaisesRegex(ValueError, 'Git metadata'):
            create_tutorial(self.root / '.git')

    def test_existing_symlink_refused(self):
        try:
            self.target.symlink_to(self.root / 'missing directory', target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation unavailable')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            create_tutorial(self.target)
        self.assertTrue(self.target.is_symlink())

    def test_concurrent_creators_publish_only_one_complete_project(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create_tutorial, self.target) for _ in range(2)]
            errors = [f.exception() for f in futures]
        self.assertEqual(sum(error is None for error in errors), 1)
        self.assertEqual(sum(isinstance(error, ValueError) for error in errors), 1)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD').strip(), '1')
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_git_failure_or_partial_publication_leaves_no_output(self):
        with patch('rulebisect.tutorial.subprocess.run',
                   return_value=subprocess.CompletedProcess(['git'], 1, '', 'failed')):
            with self.assertRaisesRegex(ValueError, 'failed'):
                create_tutorial(self.target)
        self.assertEqual(list(self.root.iterdir()), [])
        original = Path.rename
        def fail_once(path, target):
            if target == self.target / 'labels.py':
                raise OSError('Disk error')
            return original(path, target)
        with patch.object(Path, 'rename', fail_once), self.assertRaisesRegex(OSError, 'Disk error'):
            create_tutorial(self.target)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_user_git_redirections_configuration_and_templates_cannot_affect_creation(self):
        hooks = self.root / 'hooks'
        hooks.mkdir()
        (hooks / 'pre-commit').write_text('#!/bin/sh\nexit 1\n', encoding='utf-8')
        (hooks / 'pre-commit').chmod(0o755)
        template = self.root / 'templates'
        template.mkdir()
        (template / 'marker').write_text('extra', encoding='utf-8')
        home = self.root / 'home'
        home.mkdir()
        global_config = home / '.gitconfig'
        global_config.write_text(
            f'[core]\n hooksPath = "{hooks.as_posix()}"\n[commit]\n gpgSign = true\n', encoding='utf-8')
        elsewhere = self.root / 'external-git'
        env = {'GIT_DIR': str(elsewhere), 'GIT_WORK_TREE': str(self.root), 'GIT_INDEX_FILE': str(self.root / 'index'),
               'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.hooksPath', 'GIT_CONFIG_VALUE_0': str(hooks),
               'GIT_TEMPLATE_DIR': str(template), 'GIT_CONFIG_GLOBAL': str(global_config), 'HOME': str(home)}
        original = global_config.read_bytes()
        with patch.dict(os.environ, env):
            create_tutorial(self.target)
        self.assertFalse(elsewhere.exists())
        self.assertFalse((self.root / 'index').exists())
        self.assertFalse((self.target / '.git/marker').exists())
        self.assertFalse((self.target / '.git/worktrees').exists())
        self.assertEqual(global_config.read_bytes(), original)
        self.assertEqual(self.git('log', '-1', '--format=%ae').strip(), 'tutorial@example.invalid')
