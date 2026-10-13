from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rulebisect.setup import CONFIG_NAME, draft_instructions


class DraftConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='rulebisect-draft-config-')
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / 'project with spaces'
        self.repo.mkdir()
        self.agent = self.repo / 'AGENTS.md'
        self.agent.write_bytes(b'Automatic instructions.\n')
        self.selected = 'rules/Review Rules.md'
        self.rule = self.repo / self.selected
        self.rule.parent.mkdir()
        self.rule.write_bytes('自定义规则。\r\n\r\nKeep compatibility.\r\n'.encode('utf-8'))
        self.custom = self.root / 'custom experiment.json'
        self.write_config(self.custom, [self.selected])
        self.out = self.root / 'editable draft'
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True)
        subprocess.run(['git', 'add', 'AGENTS.md'], cwd=self.repo, check=True)

    def tearDown(self):
        self.temporary.cleanup()

    def write_config(self, path, selected):
        path.write_text(json.dumps({'instructions': selected, 'preserve_setting': '中文'},
                                   ensure_ascii=False), encoding='utf-8')

    def test_explicit_configuration_selects_exact_files_and_preserves_source(self):
        self.write_config(self.repo / CONFIG_NAME, ['AGENTS.md'])
        before = {path: path.read_bytes() for path in
                  (self.agent, self.rule, self.custom, self.repo / CONFIG_NAME)}
        with patch('subprocess.run', side_effect=AssertionError('Configured draft executes no commands')):
            target = draft_instructions(self.repo, self.out, config_path=self.custom)
        self.assertEqual(target, self.out)
        self.assertEqual((target / self.selected).read_bytes(), before[self.rule])
        self.assertFalse((target / 'AGENTS.md').exists())
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        (target / self.selected).write_text('Edited proposal.', encoding='utf-8')
        self.assertEqual(self.rule.read_bytes(), before[self.rule])

    def test_explicit_missing_config_never_falls_back_to_default_or_discovery(self):
        self.write_config(self.repo / CONFIG_NAME, ['AGENTS.md'])
        missing = self.root / 'missing configuration.json'
        with patch('rulebisect.setup.discover_instructions',
                   side_effect=AssertionError('Explicit config must not discover instructions')):
            with self.assertRaisesRegex(ValueError, 'Configuration file not found') as caught:
                draft_instructions(self.repo, self.out, config_path=missing)
        self.assertIn(str(missing), str(caught.exception))
        self.assertFalse(self.out.exists())

    def test_git_metadata_and_duplicate_paths_rejected_without_partial_output(self):
        for names in [['AGENTS.md', '.GiT/config'], ['AGENTS.md', './AGENTS.md']]:
            with self.subTest(names=names):
                self.write_config(self.custom, names)
                with self.assertRaises(ValueError):
                    draft_instructions(self.repo, self.out, config_path=self.custom)
                self.assertFalse(self.out.exists())

    def test_invalid_explicit_config_never_falls_back_or_creates_output(self):
        self.write_config(self.repo / CONFIG_NAME, ['AGENTS.md'])
        invalid = [(b'{\n "instructions": ?\n}', 'line 2'),
                   (b'[]', 'JSON object'), (b'\xff', 'UTF-8'),
                   (b'{"instructions": []}', 'Select instruction files'),
                   (b'{"instructions": "AGENTS.md"}', 'Select instruction files')]
        for source, reason in invalid:
            self.custom.write_bytes(source)
            with self.subTest(reason=reason), patch('rulebisect.setup.discover_instructions',
                    side_effect=AssertionError('Explicit config must not discover instructions')):
                with self.assertRaisesRegex(ValueError, reason):
                    draft_instructions(self.repo, self.out, config_path=self.custom)
            self.assertEqual(self.custom.read_bytes(), source)
            self.assertFalse(self.out.exists())
        with self.assertRaisesRegex(ValueError, 'path is a directory'):
            draft_instructions(self.repo, self.out, config_path=self.root)
        self.assertFalse(self.out.exists())

    def test_relative_custom_config_is_read_from_caller_working_directory(self):
        directory = self.root / 'configs'
        directory.mkdir()
        path = directory / 'experiment.json'
        self.write_config(path, [self.selected])
        with contextlib.chdir(self.root):
            draft_instructions(self.repo, self.out, config_path=Path('configs/experiment.json'))
        self.assertEqual((self.out / self.selected).read_bytes(), self.rule.read_bytes())
        self.assertFalse((self.repo / CONFIG_NAME).exists())

    def test_missing_later_instruction_leaves_no_partial_draft(self):
        self.write_config(self.custom, [self.selected, 'missing.md'])
        original = self.rule.read_bytes()
        with self.assertRaisesRegex(ValueError, 'missing.md'):
            draft_instructions(self.repo, self.out, config_path=self.custom)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.rule.read_bytes(), original)

    def test_default_config_and_discovery_still_work(self):
        configured = self.root / 'configured'
        self.write_config(self.repo / CONFIG_NAME, [self.selected])
        draft_instructions(self.repo, configured)
        self.assertEqual((configured / self.selected).read_bytes(), self.rule.read_bytes())
        self.assertFalse((configured / 'AGENTS.md').exists())
        (self.repo / CONFIG_NAME).unlink()
        discovered = self.root / 'discovered'
        draft_instructions(self.repo, discovered)
        self.assertEqual((discovered / 'AGENTS.md').read_bytes(), self.agent.read_bytes())
        self.assertFalse((discovered / self.selected).exists())

    def test_explicit_config_preserves_output_guards(self):
        self.out.mkdir()
        existing = self.out / 'keep.txt'
        existing.write_bytes(b'Existing evidence.')
        with self.assertRaisesRegex(ValueError, 'empty directory outside'):
            draft_instructions(self.repo, self.out, config_path=self.custom)
        self.assertEqual(existing.read_bytes(), b'Existing evidence.')
        inside = self.repo / 'draft'
        with self.assertRaisesRegex(ValueError, 'empty directory outside'):
            draft_instructions(self.repo, inside, config_path=self.custom)
        self.assertFalse(inside.exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX permission bits')
    def test_explicit_config_copies_readonly_source_as_editable(self):
        self.rule.chmod(0o400)
        original = self.rule.read_bytes()
        draft_instructions(self.repo, self.out, config_path=self.custom)
        copy = self.out / self.selected
        self.assertTrue(copy.stat().st_mode & 0o200)
        self.assertFalse(self.rule.stat().st_mode & 0o200)
        copy.write_bytes(b'Editable proposal.\n')
        self.assertEqual(self.rule.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
