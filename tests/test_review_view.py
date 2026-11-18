"""An offline review keeps untrusted diff data inert and the budget visible."""
import unittest
from html.parser import HTMLParser

from rulebisect.review import render_review, review_text


class Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.words = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.words.append(data)


class ReviewViewTests(unittest.TestCase):
    def setUp(self):
        self.sha = '8' * 40
        self.plan = {
            'instruction_sources': {'baseline': {'kind': 'git', 'ref': 'HEAD~1', 'commit': self.sha},
                                    'candidate': {'kind': 'worktree'}},
            'instruction_changes': [{'path': 'docs/<test>.md', 'changed': True, 'added_lines': 2, 'removed_lines': 1}],
            'cases': ['modern'], 'case_selection': {'selected': ['modern'], 'omitted': ['legacy']},
            'required_calls': 6, 'max_runs': 10, 'max_tokens': 9000, 'model': None,
        }

    def test_preview_preserves_sources_scope_budget_and_exact_command_as_text(self):
        command = 'python "my tool.pyz" compare --model "m & n"'
        diff = '--- a/docs/<test>.md\n+++ b/docs/<test>.md\n@@ -1 +1 @@\n-<script>leak()</script>\n+<img src=x>\n'
        document = Structure()
        document.feed(render_review(self.plan, diff, command))
        words = ''.join(document.words)
        for expected in [command, diff, self.sha, 'HEAD~1', 'Working tree', 'docs/<test>.md', 'legacy', 'modern',
                         '计划调用', '6', '10', '9000', 'Model calls made: 0. No results yet.', '执行时指定']:
            self.assertIn(expected, words)
        self.assertFalse(any(tag in {'script', 'img', 'link', 'iframe'} for tag, _ in document.tags))

    def test_directory_source_and_unchanged_empty_patch(self):
        self.plan['instruction_sources']['candidate'] = {'kind': 'directory', 'path': 'proposal <folder>'}
        self.plan['instruction_changes'][0].update(changed=False, added_lines=0, removed_lines=0)
        text = review_text(self.plan, 'run')
        self.assertIn('HEAD~1 @ ' + self.sha, text)
        self.assertIn('After: proposal <folder>', text)
        self.assertIn('0 of 1', text)
        page = render_review(self.plan, '', 'run')
        self.assertIn('Selected instruction files are identical', page)
        self.assertIn('proposal &lt;folder&gt;', page)

    def test_large_diffs_limit_both_rows_and_single_line_payload(self):
        for diff in ['+hello\n' * 2000, '+' + '界' * 300000]:
            page = render_review(self.plan, diff + 'END_MARKER', 'run')
            self.assertIn('Diff preview truncated.', page)
            self.assertNotIn('END_MARKER', page)
            self.assertLess(len(page), 125000)
            self.assertLessEqual(page.count('<span class="added">'), 600)
            self.assertIn('Run comparison', page)
