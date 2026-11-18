import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rulebisect.revisions import read_revision


class RevisionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'commit.gpgSign', 'false')
        self.path = 'rules with spaces/[arch].md'
        target = self.repo / self.path
        target.parent.mkdir()
        target.write_bytes(b'Original\r\n')
        (target.parent / 'a.md').write_bytes(b'Other\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'original')
        self.first = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('tag', 'v-old')
        target.write_bytes(b'New\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'new')

    def git(self, *args, data=None):
        return subprocess.run(['git', *args], cwd=self.repo, input=data, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def test_pinned_revision_and_literal_blob_preserve_index_and_working_tree(self):
        target = self.repo / self.path
        target.write_bytes(b'Staged')
        self.git('add', '--', self.path)
        target.write_bytes(b'Unstaged')
        index = self.repo / '.git' / 'index'
        original = index.read_bytes()
        self.git('branch', 'my/rules', self.first)
        for ref in ['HEAD~1', 'HEAD^', 'v-old', 'my/rules', self.first]:
            with self.subTest(ref=ref):
                metadata, blobs = read_revision(self.repo, ref, [self.path])
                self.assertEqual(metadata, {'kind': 'git', 'ref': ref, 'commit': self.first})
                self.assertEqual(blobs, {self.path: b'Original\r\n'})
        self.assertEqual(index.read_bytes(), original)
        self.assertEqual(target.read_bytes(), b'Unstaged')

    def test_ref_move_after_resolution_does_not_mix_versions(self):
        self.git('branch', 'moving', self.first)
        original = subprocess.run
        calls = []
        def move_between_reads(argv, **kwargs):
            calls.append(argv)
            if 'ls-tree' in argv:
                original(['git', 'branch', '-f', 'moving', 'HEAD'], cwd=self.repo, check=True)
            return original(argv, **kwargs)
        with patch('rulebisect.revisions.subprocess.run', side_effect=move_between_reads):
            metadata, blobs = read_revision(self.repo, 'moving', [self.path])
        self.assertEqual(sum('rev-parse' in call for call in calls), 1)
        self.assertEqual(metadata['commit'], self.first)
        self.assertEqual(blobs[self.path], b'Original\r\n')

    def test_invalid_inputs_and_missing_revision(self):
        for ref in ['--help', 'HEAD:rules', '../HEAD', 'HEAD..HEAD', ':/message', 'invalid ref', 'missing-branch']:
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, 'revision'):
                read_revision(self.repo, ref, [self.path])
        for path in ['../file', '.GiT/HEAD', '/AGENTS.md', 'D:/AGENTS.md', 'missing', 'rules with spaces']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                read_revision(self.repo, 'HEAD', [path])

    def test_mode_and_encoding_are_validated_in_commit(self):
        oid = self.git('hash-object', '-w', '--stdin', data=b'/some/file').decode().strip()
        self.git('update-index', '--add', '--cacheinfo', f'120000,{oid},linked')
        self.git('update-index', '--add', '--cacheinfo', f'160000,{self.first},submodule')
        (self.repo / 'binary').write_bytes(b'\xff\xfe')
        self.git('add', 'binary')
        self.git('commit', '-qm', 'nonregular entries')
        for name in ['linked', 'submodule']:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'regular file'):
                read_revision(self.repo, 'HEAD', [name])
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            read_revision(self.repo, 'HEAD', ['binary'])

    def test_read_commands_disable_remote_transports_and_ignore_replace_objects(self):
        original = subprocess.run
        def check_env(args, **kwargs):
            self.assertEqual(kwargs['env']['GIT_ALLOW_PROTOCOL'], '')
            self.assertEqual(kwargs['env']['GIT_NO_LAZY_FETCH'], '1')
            self.assertEqual(kwargs['env']['GIT_NO_REPLACE_OBJECTS'], '1')
            return original(args, **kwargs)
        with patch.dict(os.environ, {'GIT_DIR': '/unused'}), patch(
                'rulebisect.revisions.subprocess.run', side_effect=check_env):
            metadata, _ = read_revision(self.repo, 'v-old', [self.path])
        self.assertEqual(metadata['commit'], self.first)
