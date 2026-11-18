"""Repository and index overrides inherited by Git hooks must not redirect trials."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rulebisect.cli import main
from rulebisect.experiment import Experiment
from rulebisect.setup import check_git_environment


class GitEnvironmentTests(unittest.TestCase):
    def test_repository_overrides_are_reported_without_values(self):
        for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE',
                     'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
            with self.subTest(name=name), patch.dict(os.environ, {name: 'private path'}):
                with self.assertRaisesRegex(ValueError, name) as raised:
                    check_git_environment()
                self.assertNotIn('private path', str(raised.exception))
        with patch.dict(os.environ, {'GIT_CONFIG_COUNT': '0', 'GIT_CONFIG_GLOBAL': '/unused'}):
            check_git_environment()

    def test_review_and_compare_refuse_index_redirection_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, output = root / 'project', root / 'evidence'
            repo.mkdir()
            (repo / 'AGENTS.md').write_bytes(b'One rule.\n')
            (repo / 'source.py').write_bytes(b'VALUE = 1\n')
            (repo / 'check.py').write_bytes(b'raise SystemExit(0)\n')
            config = {'instructions': ['AGENTS.md'], 'task': 'Keep VALUE', 'oracle': 'check.py',
                      'verify': ['{python}', '{oracle}']}
            (repo / '.rulebisect.json').write_text(json.dumps(config), encoding='utf-8')
            for command in [['init', '-q'], ['add', '.'],
                            ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid',
                             '-c', 'commit.gpgSign=false', 'commit', '-qm', 'baseline']]:
                subprocess.run(['git', *command], cwd=repo, check=True, capture_output=True)
            index = (repo / '.git/index').read_bytes()
            with patch.dict(os.environ, {'GIT_INDEX_FILE': str(root / 'absent')}):
                for cmd in [['review', '--json'], ['compare', '--base-ref', 'HEAD', '--model', 'fixture-model']]:
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = main([*cmd, '--repo', str(repo), '--out', str(output)])
                    self.assertEqual(code, 2)
                    self.assertIn('GIT_INDEX_FILE', err.getvalue())
                    self.assertNotIn(str(root / 'absent'), err.getvalue())
                    self.assertFalse(output.exists())
                engine = Experiment(repo, config, output, None, 2, 8, 10)
                with self.assertRaisesRegex(ValueError, 'GIT_INDEX_FILE'):
                    engine.prepare(check_codex=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(['review', '--json', '--repo', str(repo)]), 0)
            self.assertIn('source.py', json.loads(out.getvalue())['snapshot_inputs']['included_files'])
            self.assertEqual(index, (repo / '.git/index').read_bytes())
            self.assertFalse((root / 'absent').exists())
