"""Portable distribution contracts, including execution outside the checkout."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


CHECKOUT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('rulebisect_skill_builder', CHECKOUT / 'scripts/build_skill_plugin.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class SkillPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='rulebisect-package-')
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'rulebisect').mkdir()
        for name in builder.MODULES:
            shutil.copyfile(CHECKOUT / 'rulebisect' / name, self.source / 'rulebisect' / name)
        shutil.copyfile(CHECKOUT / 'LICENSE', self.source / 'LICENSE')
        self.plugin = self.source / builder.PLUGIN
        for relative in builder.METADATA_FILES:
            target = self.plugin / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(CHECKOUT / builder.PLUGIN / relative, target)

    def tearDown(self):
        self.temporary.cleanup()

    def symlink(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable')

    def archive(self, name='plugin.zip', *, skill_only=False):
        return builder.build_archive(self.source, self.root / name, skill_only=skill_only)

    def extract(self, archive, name='outside checkout'):
        outside = self.root / name
        outside.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(outside)
        return outside

    def launch(self, launcher, *args, cwd=None, env=None):
        return subprocess.run([sys.executable, str(launcher), *map(str, args)],
                              cwd=cwd or self.root, env=env, capture_output=True,
                              text=True, timeout=60)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def version(self):
        # Compare source data without importing another engine into the launcher.
        text = (self.source / 'rulebisect/__init__.py').read_text(encoding='utf-8')
        return text.split('__version__ = ', 1)[1].splitlines()[0].strip('"\' ')

    def test_sync_copies_only_fixed_modules_and_exact_license(self):
        (self.source / 'rulebisect/auth.json').write_text('ACCOUNT_MUST_NOT_SHIP', encoding='utf-8')
        (self.source / 'rulebisect/.env').write_text('PRIVATE_ENV_MUST_NOT_SHIP', encoding='utf-8')
        (self.source / 'rulebisect/__pycache__').mkdir()
        metadata_before = {path: (self.plugin / path).read_bytes() for path in builder.METADATA_FILES}
        builder.sync_runtime(self.source)
        builder.check_package(self.source)
        package = self.plugin / builder.RUNTIME / 'rulebisect'
        self.assertEqual({path.name for path in package.iterdir()}, set(builder.MODULES))
        for name in builder.MODULES:
            self.assertEqual((package / name).read_bytes(), (self.source / 'rulebisect' / name).read_bytes())
        for relative in (Path('LICENSE'), builder.SKILL / 'LICENSE', builder.RUNTIME / 'LICENSE'):
            self.assertEqual((self.plugin / relative).read_bytes(), (self.source / 'LICENSE').read_bytes())
        self.assertEqual(metadata_before, {path: (self.plugin / path).read_bytes() for path in builder.METADATA_FILES})

    def test_check_is_read_only_and_reports_drift(self):
        builder.sync_runtime(self.source)
        snapshot = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in self.plugin.rglob('*') if path.is_file()}
        builder.check_package(self.source)
        self.assertEqual(snapshot, {path: (path.read_bytes(), path.stat().st_mtime_ns)
                                   for path in snapshot})
        canonical = self.source / 'rulebisect/__init__.py'
        canonical.write_bytes(canonical.read_bytes() + b'\n# canonical changed\n')
        with self.assertRaisesRegex(ValueError, 'differs from canonical'):
            builder.check_package(self.source)
        self.assertEqual(snapshot, {path: (path.read_bytes(), path.stat().st_mtime_ns)
                                   for path in snapshot})

    def test_unknown_vendor_files_and_source_modules_fail_before_sync(self):
        builder.sync_runtime(self.source)
        original = (self.plugin / builder.RUNTIME / 'rulebisect/__init__.py').read_bytes()
        for relative in (builder.RUNTIME / 'rulebisect/extra.py', builder.RUNTIME / 'auth.json',
                         Path('credentials.json'), Path('skills/rulebisect/references/extra.md')):
            with self.subTest(relative=relative):
                path = self.plugin / relative
                path.write_text('PRIVATE_EXTRA', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'unexpected file'):
                    builder.sync_runtime(self.source)
                with self.assertRaisesRegex(ValueError, 'unexpected file'):
                    builder.check_package(self.source)
                self.assertEqual((self.plugin / builder.RUNTIME / 'rulebisect/__init__.py').read_bytes(), original)
                path.unlink()
        (self.source / 'rulebisect/unreviewed.py').write_text('NEW_MODULE', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'explicit packaging allowlist'):
            builder.sync_runtime(self.source)

    def test_source_and_bundle_symlinks_are_rejected(self):
        builder.sync_runtime(self.source)
        for path in (self.source / 'rulebisect/ui.py', self.plugin / 'assets/rulebisect.svg',
                     self.plugin / builder.RUNTIME / 'rulebisect/ui.py'):
            with self.subTest(path=path):
                saved = path.read_bytes()
                outside = self.root / 'outside-file'
                outside.write_bytes(saved)
                path.unlink()
                self.symlink(path, outside)
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    builder.build_archive(self.source, self.root / 'unsafe.zip')
                self.assertFalse((self.root / 'unsafe.zip').exists())
                path.unlink()
                path.write_bytes(saved)

    def test_plugin_ancestor_symlink_is_rejected_before_writing(self):
        external = self.root / 'external-plugins'
        (self.source / 'plugins').rename(external)
        self.symlink(self.source / 'plugins', external, directory=True)
        with self.assertRaisesRegex(ValueError, 'directory component.*symlink'):
            builder.build_archive(self.source, self.root / 'unsafe.zip')
        self.assertFalse((self.root / 'unsafe.zip').exists())
        self.assertFalse((external / 'rulebisect' / builder.RUNTIME).exists())

    def test_archive_is_deterministic_and_has_only_portable_allowlisted_paths(self):
        first = self.archive('first.zip')
        for path in self.plugin.rglob('*'):
            if path.is_file():
                os.utime(path, (1_800_000_000, 1_800_000_000))
                path.chmod(0o600)
        second = self.archive('second.zip')
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as bundle:
            expected = {path.as_posix() for path in builder.PACKAGE_FILES}
            self.assertEqual(set(bundle.namelist()), expected)
            self.assertEqual(bundle.namelist(), sorted(bundle.namelist()))
            self.assertIn('plugin.json', expected)
            self.assertIn('assets/rulebisect.svg', expected)
            self.assertNotIn('.plugin/plugin.json', expected)
            for info in bundle.infolist():
                self.assertFalse(Path(info.filename).is_absolute())
                self.assertNotIn('..', Path(info.filename).parts)
                self.assertNotIn('\\', info.filename)
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertTrue(stat.S_ISREG(info.external_attr >> 16))
            self.assertEqual(bundle.read('LICENSE'), (self.source / 'LICENSE').read_bytes())
            metadata = json.loads(bundle.read('plugin.json'))
            self.assertEqual(metadata['version'], '0.1.0')
            self.assertNotEqual(metadata['version'], self.version())

    def test_archive_never_overwrites_or_writes_inside_bundle(self):
        occupied = self.root / 'occupied.zip'
        occupied.write_bytes(b'KEEP_EXISTING')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            builder.build_archive(self.source, occupied)
        self.assertEqual(occupied.read_bytes(), b'KEEP_EXISTING')
        self.assertFalse((self.plugin / builder.RUNTIME).exists(), 'No sync on rejected output')
        broken = self.root / 'broken.zip'
        self.symlink(broken, self.root / 'missing')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            builder.build_archive(self.source, broken)
        outside = self.root / 'destination'
        outside.mkdir()
        linked_directory = self.root / 'linked-destination'
        self.symlink(linked_directory, outside, directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            builder.build_archive(self.source, linked_directory / 'unsafe.zip')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            builder.build_archive(self.source, linked_directory / 'nested/unsafe.zip')
        self.assertFalse((outside / 'unsafe.zip').exists())
        with self.assertRaisesRegex(ValueError, 'outside the plugin'):
            builder.build_archive(self.source, self.plugin / 'recursive.zip')

    def test_interrupted_archive_is_removed(self):
        output = self.root / 'interrupted.zip'
        with patch.object(zipfile.ZipFile, 'writestr', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                builder.build_archive(self.source, output)
        self.assertFalse(output.exists())
        builder.check_package(self.source)

    def test_zip_launcher_ignores_cwd_pythonpath_and_does_not_write_bytecode(self):
        outside = self.extract(self.archive())
        launcher = outside / builder.LAUNCHER
        marker = outside / 'IMPORTED_UNBUNDLED_CODE'
        poison = f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\nraise RuntimeError('host package imported')\n"
        (outside / 'rulebisect').mkdir()
        (outside / 'rulebisect/__init__.py').write_text(poison, encoding='utf-8')
        (outside / 'json.py').write_text(poison, encoding='utf-8')
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(outside), str(CHECKOUT))))
        result = self.launch(launcher, '--version', cwd=outside, env=env)
        self.assert_ok(result)
        self.assertEqual(result.stdout.strip(), self.version())
        self.assertFalse(marker.exists())
        self.assertFalse(list((outside / builder.RUNTIME).rglob('__pycache__')))
        self.assertFalse((outside / builder.SKILL / 'scripts/runtime').is_symlink())

    def test_missing_or_extra_runtime_never_falls_back_to_installed_engine(self):
        outside = self.extract(self.archive())
        launcher = outside / builder.LAUNCHER
        runtime = outside / builder.RUNTIME
        env = dict(os.environ, PYTHONPATH=str(CHECKOUT))
        for problem in ('extra', 'missing'):
            with self.subTest(problem=problem):
                if problem == 'extra':
                    (runtime / 'rulebisect/extra.py').write_text('UNREVIEWED', encoding='utf-8')
                else:
                    shutil.rmtree(runtime)
                result = self.launch(launcher, '--version', cwd=CHECKOUT, env=env)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('Bundled RuleBisect runtime', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertNotIn(self.version(), result.stdout)
        self.assertFalse(runtime.exists(), 'Launcher must never fetch or regenerate missing engine')

    def test_launcher_rejects_symlinked_engine_before_import(self):
        outside = self.extract(self.archive())
        launcher = outside / builder.LAUNCHER
        package = outside / builder.RUNTIME / 'rulebisect'
        external = self.root / 'external-engine'
        package.rename(external)
        marker = self.root / 'LINKED_ENGINE_MUST_NOT_IMPORT'
        (external / '__init__.py').write_text(
            f'from pathlib import Path\nPath({str(marker)!r}).write_text("called")\n', encoding='utf-8')
        self.symlink(package, external, directory=True)
        result = self.launch(launcher, '--version', cwd=outside)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('symlinked', result.stderr)
        self.assertFalse(marker.exists())

    def test_standalone_skill_has_metadata_license_and_working_launcher(self):
        archive = self.archive('skill.zip', skill_only=True)
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
            self.assertIn('SKILL.md', names)
            self.assertIn('agents/openai.yaml', names)
            self.assertIn('scripts/rulebisect_cli.py', names)
            self.assertIn('LICENSE', names)
            self.assertIn('scripts/runtime/LICENSE', names)
            self.assertEqual({name for name in names if name.startswith('references/')},
                             {'references/experiments.md', 'references/assertions.md', 'references/evidence.md'})
            self.assertNotIn('plugin.json', names)
            self.assertNotIn('assets/rulebisect.svg', names)
        outside = self.extract(archive, name='standalone skill')
        result = self.launch(outside / 'scripts/rulebisect_cli.py', '--version', cwd=outside)
        self.assert_ok(result)
        self.assertEqual(result.stdout.strip(), self.version())

    def test_extracted_bundle_runs_regression_fix_and_assertion_check_without_codex(self):
        outside = self.extract(self.archive())
        launcher = outside / builder.LAUNCHER
        no_model = self.root / 'fake bin'
        no_model.mkdir()
        marker = self.root / 'CODEX_MUST_NOT_RUN'
        fake_codex = no_model / 'codex'
        fake_codex.write_text(f'#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).write_text("called")\nraise SystemExit(99)\n', encoding='utf-8')
        fake_codex.chmod(0o755)
        env = dict(os.environ, PATH=str(no_model) + os.pathsep + os.environ.get('PATH', ''),
                   PYTHONPATH=str(CHECKOUT))
        for scenario, status in (('regression', 'regressions_observed'), ('fix', 'no_regressions_observed')):
            with self.subTest(scenario=scenario):
                evidence = outside / f'{scenario} evidence'
                result = self.launch(launcher, 'demo', '--scenario', scenario, '--out', evidence,
                                     cwd=outside, env=env)
                self.assert_ok(result)
                report = json.loads((evidence / 'report.json').read_text(encoding='utf-8'))
                self.assertEqual(report['status'], status)
                self.assertEqual(report['version'], self.version())
                self.assertEqual(report['runner'], 'simulation')
                self.assertEqual(len(report['trials']), 8)
                self.assertTrue((evidence / 'report.html').is_file())
        repo = outside / 'user repository'
        repo.mkdir()
        (repo / 'AGENTS.md').write_text('Produce modern JSON.\n', encoding='utf-8')
        (repo / 'result.json').write_text('{"format":"modern"}', encoding='utf-8')
        subprocess.run(['git', 'init', '-q'], cwd=repo, check=True, env=env)
        subprocess.run(['git', 'add', '.'], cwd=repo, check=True, env=env)
        criteria = outside / 'frozen checks.json'
        criteria.write_text(json.dumps([{'type': 'json_equals', 'path': 'result.json',
                                         'pointer': '/format', 'value': 'modern'}]), encoding='utf-8')
        self.assert_ok(self.launch(launcher, 'init', '--repo', repo, '--task', 'Produce modern JSON.',
                                  '--assertions', criteria, cwd=outside, env=env))
        criteria.write_text('[]', encoding='utf-8')
        evidence = outside / 'checks evidence'
        self.assert_ok(self.launch(launcher, 'check', '--repo', repo, '--all', '--out', evidence,
                                  cwd=outside, env=env))
        report = json.loads((evidence / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['version'], self.version())
        self.assertEqual(report['kind'], 'checks')
        self.assertEqual(report['runner'], 'verifier_only')
        self.assertEqual(report['trials'], [])
        self.assertEqual([case['outcome'] for case in report['cases']], ['pass'])
        self.assert_ok(self.launch(launcher, 'doctor', '--repo', repo, '--offline', cwd=outside, env=env))
        self.assertFalse(marker.exists(), 'Zero-model paths must never invoke Codex')
        self.assertFalse(list((outside / builder.RUNTIME).rglob('__pycache__')))
        builder.check_package(self.source)


if __name__ == '__main__':
    unittest.main()
