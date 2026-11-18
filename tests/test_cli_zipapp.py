"""Downloadable CLI contracts, exercised by running the archive outside the checkout."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile


CHECKOUT = Path(__file__).resolve().parents[1]


class CliZipappTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='rulebisect-zipapp-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.archive = self.root / 'download folder' / 'RuleBisect CLI.pyz'

    def build(self, target=None, source=CHECKOUT):
        return subprocess.run(
            [sys.executable, '-X', 'utf8', str(CHECKOUT / 'scripts/build_cli_zipapp.py'),
             '--root', str(source), '--out', str(target or self.archive)],
            cwd=self.root, capture_output=True, text=True, encoding='utf-8', timeout=30)

    def launch(self, *args, env=None):
        return subprocess.run(
            [sys.executable, '-I', '-X', 'utf8', str(self.archive), *map(str, args)],
            cwd=self.root, env=env, capture_output=True, text=True, encoding='utf-8', timeout=90)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_reproducible_contents_and_existing_output_preserved(self):
        source = self.root / 'copy'
        package = source / 'rulebisect'
        package.mkdir(parents=True)
        expected = {'LICENSE', '__main__.py'}
        for module in (CHECKOUT / 'rulebisect').glob('*.py'):
            shutil.copyfile(module, package / module.name)
            expected.add('rulebisect/' + module.name)
        shutil.copyfile(CHECKOUT / 'LICENSE', source / 'LICENSE')
        (package / '.env').write_bytes(b'LOCAL_ONLY')
        (package / 'local_extension.py').write_bytes(b'LOCAL_ONLY')
        (package / '__pycache__').mkdir()
        (package / '__pycache__/x.pyc').write_bytes(b'LOCAL_ONLY')
        self.assert_ok(self.build(source=source))
        second = self.root / 'another name.pyz'
        self.assert_ok(self.build(second))
        self.assertEqual(self.archive.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(self.archive) as bundle:
            self.assertEqual(set(bundle.namelist()), expected)
            for name in expected - {'__main__.py'}:
                self.assertEqual(bundle.read(name), (source / name).read_bytes())

        self.archive.write_bytes(b'My previous download.')
        self.assertEqual(self.build().returncode, 2)
        self.assertEqual(self.archive.read_bytes(), b'My previous download.')
        (package / 'cli.py').unlink()
        failed_target = self.root / 'partial.pyz'
        self.assertEqual(self.build(failed_target, source).returncode, 2)
        self.assertFalse(failed_target.exists())

    def test_runs_version_and_regression_demo_without_an_installed_package(self):
        self.assert_ok(self.build())
        decoy = self.root / 'rulebisect'
        decoy.mkdir()
        (decoy / '__init__.py').write_text('raise RuntimeError("Used the checkout instead of the archive")\n',
                                           encoding='utf-8')
        env = dict(os.environ, PYTHONPATH=str(self.root))
        result = self.launch('--version', env=env)
        self.assert_ok(result)
        project = tomllib.loads((CHECKOUT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
        self.assertEqual(result.stdout.strip(), project['version'])
        evidence = self.root / 'demo evidence'
        self.assert_ok(self.launch('demo', '--scenario', 'regression', '--out', evidence, env=env))
        report = json.loads((evidence / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual((report['runner'], report['status']), ('simulation', 'regressions_observed'))
        self.assertEqual(len(report['trials']), 8)
        self.assertTrue((evidence / 'report.html').is_file())

    def test_suggested_command_reuses_downloaded_archive_outside_checkout(self):
        self.assert_ok(self.build())
        repo = self.root / 'existing project'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
        (repo / 'AGENTS.md').write_bytes(b'Preserve whitespace.\n')
        subprocess.run(['git', 'add', 'AGENTS.md'], cwd=repo, check=True)
        result = self.launch('status', '--repo', repo, '--json')
        self.assertEqual(result.returncode, 2, result.stderr)
        status = json.loads(result.stdout)
        self.assertEqual(status['state'], 'needs_configuration')
        argv = status['next_steps'][0]['argv']
        self.assertTrue(os.path.samefile(argv[0], sys.executable))
        self.assertEqual(argv[1:4], ['-I', '-X', 'utf8'])
        self.assertEqual(Path(argv[4]).resolve(), self.archive)
        self.assertEqual(argv[5:8], ['init', '--wizard', '--repo'])
        self.assertEqual(Path(argv[8]).resolve(), repo)
        # A new CLI process can consume the suggested argv in another directory.
        help_result = subprocess.run([*argv, '--help'], cwd=self.root, capture_output=True,
                                     text=True, encoding='utf-8', timeout=30)
        self.assert_ok(help_result)
        self.assertIn('--instructions', help_result.stdout)
