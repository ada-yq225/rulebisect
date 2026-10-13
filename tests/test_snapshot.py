"""Explicit snapshot inputs, bounded omission previews, and immutable sources."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unicodedata
from unittest.mock import patch

from rulebisect.checks import SuiteCheck
from rulebisect.comparison import Comparison, select_cases
from rulebisect.experiment import Experiment
from rulebisect.setup import init_config
from rulebisect.configuration import load_configuration


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='rulebisect-snapshot-')
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        (self.repo / 'AGENTS.md').write_text('Keep the output contract.\n', encoding='utf-8')
        (self.repo / 'verify.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True)
        subprocess.run(['git', 'add', 'AGENTS.md', 'verify.py'], cwd=self.repo, check=True)
        self.config = {'task': 'Preserve output behavior.', 'instructions': ['AGENTS.md'],
                       'oracle': 'verify.py', 'verify': ['{python}', '{oracle}'],
                       'protected_files': ['verify.py'], 'repeats': 2, 'max_runs': 8, 'timeout': 10}

    def tearDown(self):
        self.temporary.cleanup()

    def experiment(self, name='evidence', config=None, runner=None):
        return Experiment(self.repo, copy.deepcopy(self.config if config is None else config),
                          self.root / name, None, 2, 8, 10, runner=runner)

    def prepare(self, **options):
        experiment = self.experiment(**options)
        experiment.prepare(materialize=False, check_codex=False)
        return experiment

    def originals(self):
        return {path.relative_to(self.repo).as_posix(): path.read_bytes()
                for path in self.repo.rglob('*')
                if path.is_file() and '.git' not in path.relative_to(self.repo).parts}

    def symlink(self, path, target, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation is unavailable on this filesystem')

    def test_default_snapshot_explains_omitted_untracked_files_without_reading_them(self):
        missing = self.repo / 'new_source.py'
        missing.write_bytes(b'PRIVATE_UNTRACKED_CONTENT')
        original_read, reads = Path.read_bytes, []
        def read(path):
            reads.append(path)
            if path == missing:
                self.fail('Snapshot previews must never read excluded file content')
            return original_read(path)
        with patch('pathlib.Path.read_bytes', read):
            experiment = self.prepare()
        self.assertNotIn('new_source.py', experiment.blobs)
        inputs = experiment.report['snapshot_inputs']
        self.assertEqual(inputs, {'included_files': ['AGENTS.md', 'verify.py'], 'extra_files': [],
                                  'excluded_untracked': ['new_source.py'], 'excluded_untracked_count': 1,
                                  'excluded_untracked_truncated': False})
        self.assertNotIn('PRIVATE_UNTRACKED_CONTENT', str(experiment.report))
        self.assertEqual(set(reads), {self.repo / 'AGENTS.md', self.repo / 'verify.py'})
        self.assertFalse(experiment.out.exists())

    def test_explicit_files_are_normalized_frozen_and_included_in_hashes(self):
        path = self.repo / 'data[1].json'
        path.write_bytes(b'{"value":1}')
        mode = path.stat().st_mode & 0o777
        self.config['include_files'] = ['./data[1].json']
        before = self.originals()
        index = (self.repo / '.git/index').read_bytes()
        experiment = self.prepare()
        initial_hash = experiment.report['snapshot_sha256']
        self.assertEqual(experiment.blobs['data[1].json'], (b'{"value":1}', mode))
        self.assertEqual(experiment.report['file_modes']['data[1].json'], mode)
        self.assertEqual(experiment.report['snapshot_inputs']['extra_files'], ['data[1].json'])
        self.assertEqual(experiment.report['snapshot_inputs']['excluded_untracked_count'], 0)
        self.assertNotIn('data[1].json', experiment.protected)
        self.assertEqual(self.originals(), before)
        self.assertEqual((self.repo / '.git/index').read_bytes(), index)
        path.write_bytes(b'{"value":2}')
        workspace = self.root / 'fresh workspace'
        workspace.mkdir()
        experiment.workspace(workspace, [rule.id for rule in experiment.rules])
        self.assertEqual((workspace / 'data[1].json').read_bytes(), b'{"value":1}')
        next_experiment = self.prepare(name='next evidence')
        self.assertNotEqual(next_experiment.report['snapshot_sha256'], initial_hash)

    def test_preview_is_bounded_but_count_is_exact_and_already_copied_files_are_removed(self):
        names = [f'new-{number:02}.txt' for number in range(31)]
        for name in names:
            (self.repo / name).write_bytes(b'not read unless selected')
        self.config['include_files'] = ['new-00.txt']
        inputs = self.prepare().report['snapshot_inputs']
        self.assertEqual(inputs['excluded_untracked_count'], 30)
        self.assertEqual(inputs['excluded_untracked'], names[1:21])
        self.assertTrue(inputs['excluded_untracked_truncated'])
        self.assertEqual(inputs['extra_files'], ['new-00.txt'])
        self.assertIn('new-00.txt', inputs['included_files'])

    def test_unicode_alias_preview_does_not_hide_distinct_files(self):
        composed = 'café.py'
        decomposed = unicodedata.normalize('NFD', composed)
        path = self.repo / composed
        path.write_bytes(b'fixture')
        alias = self.repo / decomposed
        normalization_insensitive = alias.exists()
        if not normalization_insensitive:
            # Distinct Linux entries can even be hardlinks. Do not hide the
            # omitted path merely because normalized names and inodes match.
            os.link(path, alias)
        self.config['include_files'] = [decomposed]
        inputs = self.prepare().report['snapshot_inputs']
        if normalization_insensitive:
            self.assertNotIn(composed, inputs['excluded_untracked'])
            self.assertEqual(inputs['excluded_untracked_count'], 0)
        else:
            self.assertIn(composed, inputs['excluded_untracked'])
            self.assertEqual(inputs['excluded_untracked_count'], 1)

    def test_unicode_alias_of_tracked_snapshot_file_is_rejected(self):
        composed = 'café.py'
        decomposed = unicodedata.normalize('NFD', composed)
        (self.repo / composed).write_bytes(b'fixture')
        if not (self.repo / decomposed).exists():
            os.link(self.repo / composed, self.repo / decomposed)
        subprocess.run(['git', 'add', composed], cwd=self.repo, check=True)
        self.config['include_files'] = [decomposed]
        with self.assertRaisesRegex(ValueError, 'Unicode normalization'):
            self.prepare()
        with self.assertRaisesRegex(ValueError, 'Unicode normalization'):
            init_config(self.repo, 'Task', 'python -c pass', None, include_files=[decomposed])
        self.assertFalse((self.repo / '.rulebisect.json').exists())

    def test_non_utf8_omitted_names_are_display_only_and_counts_use_original_bytes(self):
        # Replay Linux Git output: some filesystems reject these filename bytes.
        included = 'copied-input-é.txt'
        (self.repo / included).write_bytes(b'fixture input')
        self.config['include_files'] = [included]
        output = (b'AGENTS.md\0verify.py\0' + included.encode('utf-8') + b'\0'
                  + b'raw-\xff.txt\0raw-\\xff.txt\0raw-\xff.txt\0')
        real_run, real_read = subprocess.run, Path.read_bytes
        read_paths = []

        def git_output(arguments, *args, **options):
            if '--others' in arguments:
                return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr=b'')
            return real_run(arguments, *args, **options)

        def read_snapshot(path):
            read_paths.append(path)
            self.assertIn(path, {self.repo / 'AGENTS.md', self.repo / 'verify.py', self.repo / included})
            return real_read(path)

        with patch('rulebisect.experiment.subprocess.run', side_effect=git_output), \
                patch.object(Path, 'read_bytes', read_snapshot):
            inputs = self.prepare().report['snapshot_inputs']
        self.assertEqual(inputs['excluded_untracked_count'], 2)
        self.assertEqual(inputs['excluded_untracked'], [r'raw-\xff.txt', r'raw-\xff.txt'])
        self.assertFalse(inputs['excluded_untracked_truncated'])
        self.assertEqual(set(read_paths),
                         {self.repo / 'AGENTS.md', self.repo / 'verify.py', self.repo / included})
        encoded = json.dumps(inputs, ensure_ascii=False).encode('utf-8')
        self.assertEqual(json.loads(encoded)['excluded_untracked_count'], 2)

    def test_ignored_files_require_explicit_inclusion_and_are_not_in_untracked_preview(self):
        (self.repo / '.gitignore').write_text('ignored-fixture.txt\n', encoding='utf-8')
        subprocess.run(['git', 'add', '.gitignore'], cwd=self.repo, check=True)
        (self.repo / 'ignored-fixture.txt').write_bytes(b'fixture input')
        default = self.prepare()
        self.assertNotIn('ignored-fixture.txt', default.blobs)
        self.assertEqual(default.report['snapshot_inputs']['excluded_untracked_count'], 0)
        self.config['include_files'] = ['ignored-fixture.txt']
        included = self.prepare(name='explicit ignored')
        self.assertEqual(included.blobs['ignored-fixture.txt'][0], b'fixture input')
        self.assertEqual(included.report['snapshot_inputs']['extra_files'], ['ignored-fixture.txt'])

    def test_selected_instructions_and_untracked_protected_files_are_not_reported_as_omitted(self):
        (self.repo / 'rules.md').write_text('Use the contract.\n', encoding='utf-8')
        (self.repo / 'protected-helper.py').write_text('VALUE = 1\n', encoding='utf-8')
        self.config['instructions'] = ['rules.md']
        self.config['protected_files'].append('protected-helper.py')
        inputs = self.prepare().report['snapshot_inputs']
        self.assertEqual(inputs['excluded_untracked'], [])
        self.assertEqual(inputs['excluded_untracked_count'], 0)
        self.assertEqual(inputs['extra_files'], [])
        self.assertIn('rules.md', inputs['included_files'])
        self.assertIn('protected-helper.py', inputs['included_files'])

    def test_include_field_and_entries_are_validated_before_artifacts(self):
        for value in (None, True, 'source.py', {}, [None], [1], [''], ['missing.py'], ['*.py']):
            with self.subTest(value=value):
                self.config['include_files'] = value
                experiment = self.experiment()
                with self.assertRaisesRegex(ValueError, 'include_files'):
                    experiment.prepare(materialize=False, check_codex=False)
                self.assertFalse(experiment.out.exists())
        self.assertFalse((self.root / 'evidence').exists())

    def test_directory_and_nonregular_include_are_rejected(self):
        (self.repo / 'directory').mkdir()
        for name in ('.', 'directory'):
            with self.subTest(name=name):
                self.config['include_files'] = [name]
                with self.assertRaisesRegex(ValueError, 'not a regular file'):
                    self.prepare()
        if hasattr(os, 'mkfifo'):
            os.mkfifo(self.repo / 'pipe')
            self.config['include_files'] = ['pipe']
            with self.assertRaisesRegex(ValueError, 'not a regular file'):
                self.prepare()

    def test_unsafe_and_git_metadata_paths_are_rejected(self):
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'outside')
        for name in (str(outside), '../outside.txt', '.git/config', '.GiT/config', 'nested/.GIT/config'):
            with self.subTest(name=name):
                self.config['include_files'] = [name]
                with self.assertRaisesRegex(ValueError, 'include_files'):
                    self.prepare()

    def test_normalized_and_case_insensitive_duplicate_includes_are_rejected(self):
        (self.repo / 'source.py').write_bytes(b'VALUE = 1\n')
        for names in (['source.py', 'source.py'], ['source.py', './source.py'], ['source.py', 'SOURCE.py']):
            with self.subTest(names=names):
                self.config['include_files'] = names
                with self.assertRaisesRegex(ValueError, 'Duplicate include_files'):
                    self.prepare()

    def test_tracked_include_does_not_duplicate_content(self):
        original = self.prepare()
        self.config['include_files'] = ['AGENTS.md']
        included = self.prepare(name='tracked include')
        self.assertEqual(included.report['snapshot_sha256'], original.report['snapshot_sha256'])
        self.assertEqual(included.report['snapshot_inputs']['included_files'], ['AGENTS.md', 'verify.py'])
        self.assertEqual(included.report['snapshot_inputs']['extra_files'], ['AGENTS.md'])

    def test_case_alias_of_snapshot_file_is_rejected_when_filesystem_resolves_it(self):
        # A same-inode alias on POSIX also lets this verify the portability guard
        # without relying on a case-insensitive filesystem in every CI job.
        alias = self.repo / 'agents.md'
        if not alias.exists():
            os.link(self.repo / 'AGENTS.md', alias)
        self.config['include_files'] = ['agents.md']
        with self.assertRaisesRegex(ValueError, 'differs only by case|incorrect casing'):
            self.prepare()

    def test_explicit_include_rejects_incorrect_case_of_each_component(self):
        folder = self.repo / 'Inputs'
        folder.mkdir()
        path = folder / 'NewHelper.py'
        path.write_bytes(b'VALUE = 42\n')
        before, index = self.originals(), (self.repo / '.git/index').read_bytes()
        for value in ('Inputs/newhelper.py', 'inputs/NewHelper.py', 'inputs/newhelper.py'):
            with self.subTest(value=value):
                self.config['include_files'] = [value]
                with self.assertRaisesRegex(ValueError, 'incorrect casing') as caught:
                    self.prepare()
                self.assertIn('Inputs/NewHelper.py', str(caught.exception))
                self.assertFalse((self.root / 'evidence').exists())
        self.config['include_files'] = ['./Inputs/NewHelper.py']
        inputs = self.prepare().report['snapshot_inputs']
        self.assertEqual(inputs['extra_files'], ['Inputs/NewHelper.py'])
        self.assertIn('Inputs/NewHelper.py', inputs['included_files'])
        self.assertNotIn('Inputs/NewHelper.py', inputs['excluded_untracked'])
        self.assertEqual(self.originals(), before)
        self.assertEqual((self.repo / '.git/index').read_bytes(), index)

    def test_case_insensitive_filesystem_does_not_rename_untracked_include(self):
        path = self.repo / 'NewHelper.py'
        path.write_bytes(b'VALUE = 42\n')
        if not (self.repo / 'newhelper.py').is_file():
            self.skipTest('Requires a case-insensitive filesystem')
        self.config['include_files'] = ['newhelper.py']
        with self.assertRaisesRegex(ValueError, 'incorrect casing') as caught:
            self.prepare()
        self.assertIn('NewHelper.py', str(caught.exception))
        self.config['include_files'] = ['NewHelper.py']
        inputs = self.prepare().report['snapshot_inputs']
        self.assertEqual(inputs['extra_files'], ['NewHelper.py'])
        self.assertEqual(inputs['excluded_untracked_count'], 0)

    def test_symlink_files_and_ancestors_are_rejected(self):
        folder = self.repo / 'real'
        folder.mkdir()
        (folder / 'fixture.txt').write_bytes(b'fixture')
        self.symlink(self.repo / 'file-link', folder / 'fixture.txt')
        self.symlink(self.repo / 'folder-link', folder, directory=True)
        for name in ('file-link', 'folder-link/fixture.txt'):
            with self.subTest(name=name):
                self.config['include_files'] = [name]
                with self.assertRaisesRegex(ValueError, 'Symlinks'):
                    self.prepare()

    def test_included_sources_remain_mutable_unless_separately_protected(self):
        (self.repo / 'input.txt').write_bytes(b'before')
        runner = [sys.executable, '-c', 'from pathlib import Path; Path("input.txt").write_bytes(b"after")']
        for protect in (False, True):
            config = copy.deepcopy(self.config)
            config['include_files'] = ['input.txt']
            if protect:
                config['protected_files'].append('input.txt')
            experiment = self.experiment(name=f'mutable-{protect}', config=config, runner=runner)
            experiment.prepare(check_codex=False)
            with contextlib.redirect_stdout(io.StringIO()):
                record = experiment.trial([rule.id for rule in experiment.rules], 'fixture')
            self.assertEqual(record['outcome'], 'fail' if protect else 'pass')
            self.assertIn('input.txt', record['changed_files'])
            if protect:
                self.assertEqual(record['reason'], 'Protected file changed')
            self.assertEqual((self.repo / 'input.txt').read_bytes(), b'before')

    def test_include_fixes_untracked_import_check_without_changing_source_or_index(self):
        (self.repo / 'new_helper.py').write_text('VALUE = 42\n', encoding='utf-8')
        check = 'python -c "import new_helper; raise SystemExit(0 if new_helper.VALUE == 42 else 1)"'
        config_path = init_config(self.repo, 'Preserve module behavior.', check, None)
        config = load_configuration(config_path)
        original = self.originals()
        index = (self.repo / '.git/index').read_bytes()
        local = subprocess.run([sys.executable, '-B', '-c', 'import new_helper; assert new_helper.VALUE == 42'],
                               cwd=self.repo, capture_output=True, check=False)
        self.assertEqual(local.returncode, 0, local.stderr)
        missing = self.experiment(name='missing helper check', config=config)
        result = missing.check_initial()
        self.assertEqual(result['exit_code'], 1)
        self.assertIn('new_helper.py', missing.report['snapshot_inputs']['excluded_untracked'])
        self.assertIn('ModuleNotFoundError', (missing.out / 'check.log').read_text(encoding='utf-8'))
        config['include_files'] = ['new_helper.py']
        included = self.experiment(name='included helper check', config=config)
        self.assertEqual(included.check_initial()['exit_code'], 0)
        self.assertIn('new_helper.py', included.report['snapshot_inputs']['included_files'])
        self.assertNotIn('new_helper.py', included.protected)
        self.assertEqual(self.originals(), original)
        self.assertEqual((self.repo / '.git/index').read_bytes(), index)

    def test_check_and_compare_use_identical_inclusion_hashes_even_for_filtered_cases(self):
        (self.repo / 'fixture.txt').write_bytes(b'initial contract')
        (self.repo / 'second-oracle.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
        self.config['include_files'] = ['fixture.txt']
        self.config['cases'] = [{'id': 'first'}, {'id': 'second', 'oracle': 'second-oracle.py'}]
        full, selected = select_cases(self.config), select_cases(self.config, ['first'])
        index = (self.repo / '.git/index').read_bytes()
        original = self.originals()
        with contextlib.redirect_stdout(io.StringIO()):
            checks = SuiteCheck(self.repo, full, self.root / 'full checks').execute()
            subset = SuiteCheck(self.repo, selected, self.root / 'selected checks').execute()
        self.assertEqual(checks['snapshot_sha256'], subset['snapshot_sha256'])
        proposed = self.root / 'proposed'
        proposed.mkdir()
        (proposed / 'AGENTS.md').write_text('Revise the instruction only.\n', encoding='utf-8')
        comparison = Comparison(self.repo, full, self.root / 'comparison', None, 2, 8, 10, proposed)
        plan = comparison.prepare()
        self.assertEqual(plan['snapshot_sha256'], checks['snapshot_sha256'])
        for experiment in comparison.experiments.values():
            self.assertEqual(experiment.blobs['fixture.txt'][0], b'initial contract')
            self.assertEqual(experiment.report['source_snapshot_sha256'], checks['source_snapshot_sha256'])
            self.assertEqual(experiment.report['snapshot_inputs'], checks['snapshot_inputs'])
        self.assertEqual(self.originals(), original)
        self.assertEqual((self.repo / '.git/index').read_bytes(), index)
        self.assertFalse(comparison.out.exists())


if __name__ == '__main__':
    unittest.main()
