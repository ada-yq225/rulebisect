"""Product report contracts: semantics, local evidence, and truthful status text."""
from __future__ import annotations

import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

from rulebisect.report import write_report
from rulebisect.share import export_summary


class Element:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []
        self.data = []

    def descendants(self, tag=None):
        for child in self.children:
            if tag is None or child.tag == tag:
                yield child
            yield from child.descendants(tag)

    def text(self):
        return ' '.join(self.data + [child.text() for child in self.children])

    def classes(self):
        return self.attrs.get('class', '').split()


class Document(HTMLParser):
    VOID = frozenset({'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'})

    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.root = Element('document', [])
        self.stack = [self.root]
        self.feed(content)
        self.close()

    def handle_starttag(self, tag, attrs):
        element = Element(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(element)
        if tag not in self.VOID:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Element(tag, attrs, self.stack[-1]))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, data):
        self.stack[-1].data.append(data)

    def elements(self, tag=None):
        return list(self.root.descendants(tag))

    def by_id(self, value):
        return next((node for node in self.elements() if node.attrs.get('id') == value), None)

    def visible_text(self):
        def visit(node):
            if node.tag in ('script', 'style'):
                return ''
            return ' '.join(node.data + [visit(child) for child in node.children])
        return visit(self.root)


class ReportUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.out = self.root / 'evidence'
        self.out.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def report(self, **options):
        report = {
            'schema_version': 1, 'version': '0.6.0', 'runner': 'codex',
            'status': 'observed_1_minimal', 'message': 'Observed failing candidate; review the evidence.',
            'created_at': '2026-10-08T12:00:00Z', 'task': 'Produce modern JSON output.',
            'requested_model': 'test-model', 'codex_version': 'test-cli',
            'snapshot_sha256': 'fixture-snapshot', 'repeats': 2, 'max_runs': 12,
            'max_tokens': None, 'timeout_seconds': 15, 'unit_mode': 'paragraph',
            'protected_files': ['verify.py'], 'setup': [],
            'rules': [{'id': 0, 'path': 'AGENTS.md', 'line': 1, 'text': 'Use modern output.\n'},
                      {'id': 1, 'path': 'AGENTS.md', 'line': 3, 'text': 'Preserve compatibility.\n'}],
            'candidate': [0],
            'evaluations': [{'phase': 'full-baseline', 'ids': [0, 1], 'pass': 0, 'fail': 2,
                             'error': 0, 'outcome': 'fail'},
                            {'phase': 'empty-control', 'ids': [], 'pass': 2, 'fail': 0,
                             'error': 0, 'outcome': 'pass'}],
            'trials': [],
        }
        report.update(options)
        return report

    def trial(self, number, **options):
        trial = {'number': number, 'phase': 'confirmation', 'outcome': 'fail',
                 'state': 'completed', 'artifacts': f'trials/{number:04d}',
                 'reason': '', 'changed_files': ['result.json'],
                 'codex': {'reported_usage': [{'input_tokens': 100, 'output_tokens': 5,
                                              'cached_input_tokens': 50}]}}
        trial.update(options)
        return trial

    def artifacts(self, trial, *names):
        path = self.out / trial['artifacts']
        path.mkdir(parents=True, exist_ok=True)
        (path / 'trial.json').write_text(json.dumps(trial), encoding='utf-8')
        for name in names:
            (path / name).write_text('Local evidence\n', encoding='utf-8')
        return path

    def render(self, report):
        write_report(self.out, copy.deepcopy(report))
        return Document((self.out / 'report.html').read_text(encoding='utf-8'))

    def assert_named(self, document, element):
        name = element.attrs.get('aria-label', '').strip()
        if element.tag == 'button':
            name = name or element.text().strip()
        labels = [node.text().strip() for node in document.elements('label')
                  if node.attrs.get('for') == element.attrs.get('id')]
        labelled_by = element.attrs.get('aria-labelledby', '').split()
        names = [document.by_id(value).text().strip() for value in labelled_by if document.by_id(value)]
        self.assertTrue(name or any(labels) or any(names), f'Unnamed {element.tag}: {element.attrs}')

    def assert_semantics(self, document):
        self.assertEqual(len(document.elements('h1')), 1)
        mains = document.elements('main')
        self.assertEqual(len(mains), 1)
        self.assertEqual(mains[0].attrs.get('id'), 'main-content')
        self.assertEqual(document.elements('html')[0].attrs.get('lang'), 'en')
        self.assertTrue(any(node.attrs.get('name') == 'viewport' for node in document.elements('meta')))
        ids = [node.attrs['id'] for node in document.elements() if node.attrs.get('id')]
        self.assertEqual(len(ids), len(set(ids)), 'Duplicate document IDs')
        for node in document.elements():
            for attr in ('aria-labelledby', 'aria-describedby', 'aria-controls'):
                for target in node.attrs.get(attr, '').split():
                    self.assertIsNotNone(document.by_id(target), f'Broken {attr}: {target}')
            self.assertNotIn('onclick', node.attrs)
            if 'tabindex' in node.attrs:
                self.assertLessEqual(int(node.attrs['tabindex']), 0)
        for table in document.elements('table'):
            captions = list(table.descendants('caption'))
            self.assertTrue(any(node.text().strip() for node in captions), 'Table lacks a caption')
            headers = list(table.descendants('th'))
            self.assertTrue(headers, 'Table lacks headers')
            self.assertTrue(any(node.attrs.get('scope') == 'col' for node in headers))
            self.assertTrue(all(node.attrs.get('scope') in ('col', 'row') for node in headers))

    def assert_local_resources(self, document):
        for element in document.elements():
            for attr in ('src', 'href'):
                if attr not in element.attrs:
                    continue
                value = element.attrs[attr]
                parsed = urlsplit(value)
                self.assertFalse(parsed.scheme or parsed.netloc, f'Nonlocal {attr}: {value}')
                if value.startswith('#'):
                    self.assertIsNotNone(document.by_id(value[1:]), f'Broken section link: {value}')
                    continue
                path = unquote(parsed.path)
                self.assertFalse(parsed.query or parsed.fragment, f'Unexpected URL delimiters: {value}')
                self.assertFalse(Path(path).is_absolute())
                self.assertNotIn('..', Path(path.replace('\\', '/')).parts)
                self.assertNotIn('\\', path)
                if path:
                    self.assertTrue((self.out / path).is_file(), f'Link points to nonexistent evidence: {value}')
        css = ' '.join(node.text() for node in document.elements('style'))
        self.assertNotIn('@import', css)
        self.assertNotIn('http:', css)
        self.assertNotIn('https:', css)
        for script in document.elements('script'):
            self.assertNotIn('src', script.attrs)

    def test_semantic_report_navigation_and_progressive_header_controls(self):
        trial = self.trial(1)
        self.artifacts(trial, 'verify.log')
        document = self.render(self.report(trials=[trial]))
        self.assert_semantics(document)
        self.assert_local_resources(document)
        for section in ('overview', 'instructions', 'ledger', 'runs', 'settings'):
            self.assertIsNotNone(document.by_id(section))
        self.assertIsNone(document.by_id('case-results'))
        navigation_links = [node.attrs.get('href') for nav in document.elements('nav') for node in nav.descendants('a')]
        for section in ('overview', 'instructions', 'ledger', 'runs', 'settings'):
            self.assertIn('#' + section, navigation_links)
        for identifier, tag in (('theme-toggle', 'button'), ('language-select', 'select')):
            element = document.by_id(identifier)
            self.assertIsNotNone(element)
            self.assertEqual(element.tag, tag)
            self.assert_named(document, element)
            ancestors = [element]
            while ancestors[-1].parent:
                ancestors.append(ancestors[-1].parent)
            self.assertTrue(any('js-control' in node.classes() and 'hidden' in node.attrs for node in ancestors),
                            'JS-only controls must start hidden for offline progressive rendering')

    def test_rule_and_run_controls_have_names_and_expose_initial_evidence(self):
        trials = [self.trial(1), self.trial(2, phase='empty-control', outcome='pass'),
                  self.trial(3, phase='search', outcome='error', case='modern')]
        for trial in trials:
            self.artifacts(trial)
        document = self.render(self.report(trials=trials))
        for identifier in ('all', 'kept', 'search', 'run-search', 'outcome-filter',
                           'phase-filter', 'case-filter', 'reset-filters'):
            element = document.by_id(identifier)
            self.assertIsNotNone(element, identifier)
            self.assert_named(document, element)
        self.assertEqual(document.by_id('all').attrs.get('aria-pressed'), 'true')
        self.assertEqual(document.by_id('kept').attrs.get('aria-pressed'), 'false')
        live = document.by_id('visible-runs')
        self.assertIsNotNone(live)
        self.assertTrue(live.attrs.get('aria-live') in ('polite', 'assertive') or live.attrs.get('role') == 'status')
        self.assertIn('3', live.text())
        cards = [node for node in document.elements() if 'evidence-card' in node.classes()]
        self.assertEqual(len(cards), 3)
        for number, card in enumerate(cards, 1):
            self.assertEqual(card.attrs.get('id'), f'run-{number}')
            self.assertEqual(card.attrs.get('data-outcome'), trials[number - 1]['outcome'])
            self.assertEqual(card.attrs.get('data-phase'), trials[number - 1]['phase'])
            self.assertEqual(card.attrs.get('data-case'), trials[number - 1].get('case', ''))
            self.assertNotIn('hidden', card.attrs)

    def test_hostile_report_fields_remain_text_without_creating_markup(self):
        hostile = '</pre><img id="injected-image" src="https://invalid.example/secret" onerror="alert(1)"><script id="injected-script">alert(2)</script>'
        trial = self.trial(1, phase=hostile, reason=hostile, case=hostile, changed_files=[hostile])
        path = self.artifacts(trial, 'changes.diff')
        (path / 'changes.diff').write_text(hostile, encoding='utf-8')
        document = self.render(self.report(message=hostile, task=hostile, requested_model=hostile,
                              setup=[hostile], protected_files=[hostile],
                              rules=[{'id': 0, 'path': hostile, 'line': 1, 'text': hostile}],
                              candidate=[0], trials=[trial], evaluations=[]))
        self.assertIsNone(document.by_id('injected-image'))
        self.assertIsNone(document.by_id('injected-script'))
        self.assertIn(hostile, document.visible_text())
        for element in document.elements():
            self.assertFalse(any(name.startswith('on') for name in element.attrs), element.attrs)
        self.assert_local_resources(document)

    def comparison(self, status='regressions_observed'):
        trials = [self.trial(1, case='modern', arm='baseline', phase='baseline', outcome='fail'),
                  self.trial(2, case='modern', arm='candidate', phase='candidate', outcome='pass'),
                  self.trial(3, case='legacy', arm='baseline', phase='baseline', outcome='pass'),
                  self.trial(4, case='legacy', arm='candidate', phase='candidate', outcome='fail')]
        for trial in trials:
            trial['artifacts'] = f'cases/{trial["case"]}/{trial["arm"]}/trials/0001'
            self.artifacts(trial, 'verify.log')
        arm = lambda outcome: {'pass': 2 if outcome == 'pass' else 0, 'fail': 2 if outcome == 'fail' else 0,
                               'error': 0, 'outcome': outcome, 'reported_tokens': 210, 'usage_reported_runs': 2}
        cases = [{'id': 'modern', 'task': 'Modern task', 'oracle': 'verify_modern.py',
                  'baseline': arm('fail'), 'candidate': arm('pass'), 'verdict': 'improvement'},
                 {'id': 'legacy', 'task': 'Legacy task', 'oracle': 'verify_legacy.py',
                  'baseline': arm('pass'), 'candidate': arm('fail'), 'verdict': 'regression'}]
        (self.out / 'proposed.patch').write_text('Proposed instruction diff\n', encoding='utf-8')
        return self.report(kind='comparison', status=status, cases=cases, trials=trials,
                           candidate=[], evaluations=[], rules=[])

    def test_case_results_show_both_improvements_and_regressions_and_link_runs(self):
        document = self.render(self.comparison())
        self.assert_semantics(document)
        self.assert_local_resources(document)
        self.assertIsNotNone(document.by_id('case-results'))
        self.assertIsNone(document.by_id('instructions'))
        self.assertIsNone(document.by_id('ledger'))
        text = document.visible_text()
        self.assertIn('回退 / Regression', text)
        self.assertIn('改善 / Improvement', text)
        self.assertIn('modern', text)
        self.assertIn('legacy', text)
        links = [node.attrs.get('href') for node in document.elements('a')]
        self.assertIn('#run-1', links)
        self.assertIn('#run-3', links)
        self.assertIn('cases/modern/candidate/trials/0001/verify.log', links)

    def test_incomplete_compare_next_step_does_not_offer_unsupported_resume(self):
        report = self.comparison(status='inconclusive')
        report['message'] = 'Partial evidence only.'
        document = self.render(report)
        overview = document.by_id('overview')
        self.assertIsNotNone(overview)
        text = overview.text().lower()
        self.assertIn('compare', text)
        self.assertNotIn('rulebisect resume', text)

    def test_simulation_unknown_usage_and_omitted_cases_stay_explicit(self):
        trial = self.trial(1, codex={})
        self.artifacts(trial)
        report = self.report(runner='simulation', requested_model=None, trials=[trial],
                             case_selection={'available': ['visible', 'uncovered'],
                                             'selected': ['visible'], 'omitted': ['uncovered']})
        document = self.render(report)
        text = document.visible_text().lower()
        self.assertIn('simulation', text)
        self.assertIn('partial suite', text)
        self.assertIn('uncovered', text)
        self.assertTrue(any(value in text for value in ('not reported', 'unknown', '未上报')))

    def test_verifier_only_report_displays_results_and_zero_model_calls(self):
        child = self.out / 'cases' / 'behavior'
        child.mkdir(parents=True)
        (child / 'report.html').write_text('<html><title>Child report</title></html>', encoding='utf-8')
        document = self.render(self.report(kind='checks', status='checks_completed', runner='verifier_only',
                              requested_model=None, evaluations=[], rules=[], candidate=[],
                              cases=[{'id': 'behavior', 'outcome': 'fail', 'result': {'exit_code': 1}}]))
        self.assert_semantics(document)
        self.assert_local_resources(document)
        text = document.visible_text()
        self.assertIn('not invoked', text)
        self.assertIn('fail', text)
        self.assertIn('1', text)
        self.assertIn('Model calls', text)
        self.assertIn('0', text)
        self.assertNotIn('proposed.patch', [node.attrs.get('href') for node in document.elements('a')])

    def test_invalid_artifact_prefixes_never_create_links_or_read_diffs(self):
        prefixes = ['javascript:alert(1)', 'https:invalid.example', '//invalid.example', '../outside',
                    'trials/../outside', 'trials\\0001', 'trials/0001?secret',
                    'trials/0001#secret', 'trials/%2e%2e/private']
        outside = self.root / 'outside'
        outside.mkdir()
        sentinel = 'OUTSIDE_DIFF_MUST_NOT_BE_READ'
        (outside / 'changes.diff').write_text(sentinel, encoding='utf-8')
        for index, prefix in enumerate(prefixes, 1):
            with self.subTest(prefix=prefix):
                document = self.render(self.report(trials=[self.trial(index, artifacts=prefix)]))
                self.assert_local_resources(document)
                self.assertNotIn(sentinel, document.visible_text())
                self.assertFalse(any(prefix in node.attrs.get('href', '') for node in document.elements('a')))

    def test_single_verifier_check_has_a_case_result_and_existing_log(self):
        (self.out / 'check.log').write_text('Expected missing output\n', encoding='utf-8')
        document = self.render(self.report(kind='check', status='check_only', runner='verifier_only',
                              requested_model=None, trials=[], rules=[], candidate=[], evaluations=[],
                              verifier_check={'exit_code': 1, 'status': 'completed'}))
        self.assert_semantics(document)
        self.assert_local_resources(document)
        self.assertIsNotNone(document.by_id('case-results'))
        self.assertIsNone(document.by_id('instructions'))
        self.assertIsNone(document.by_id('ledger'))
        text = document.by_id('case-results').text()
        self.assertIn('Initial snapshot', text)
        self.assertIn('Fail', text)
        self.assertIn('1', text)
        self.assertIn('check.log', [node.attrs.get('href') for node in document.elements('a')])
        self.assertIn('not invoked', document.visible_text())

    def test_modified_case_id_cannot_link_evidence_outside_the_report(self):
        external = self.root / 'outside'
        external.mkdir()
        (external / 'report.html').write_text('Private external report', encoding='utf-8')
        for identifier in ('../../outside', 'javascript:alert(1)', 'task?query', 'task#fragment'):
            with self.subTest(case=identifier):
                document = self.render(self.report(kind='checks', status='checks_completed', runner='verifier_only',
                                      cases=[{'id': identifier, 'outcome': 'fail', 'result': {'exit_code': 1}}],
                                      trials=[], rules=[], candidate=[], evaluations=[]))
                self.assert_local_resources(document)
                links = [node.attrs.get('href') for node in document.elements('a')]
                self.assertNotIn(f'cases/{identifier}/report.html', links)

    def test_diff_symlink_and_symlink_ancestor_are_never_read_or_linked(self):
        trial = self.trial(1)
        artifact = self.artifacts(trial, 'verify.log')
        outside = self.root / 'outside'
        outside.mkdir()
        sentinel = 'PRIVATE_OUTSIDE_DIFF'
        (outside / 'changes.diff').write_text(sentinel, encoding='utf-8')
        try:
            (artifact / 'changes.diff').symlink_to(outside / 'changes.diff')
            (self.out / 'linked').symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable')
        for value in (trial, self.trial(2, artifacts='linked')):
            with self.subTest(artifacts=value['artifacts']):
                document = self.render(self.report(trials=[value]))
                self.assertNotIn(sentinel, document.visible_text())
                self.assertFalse(any(node.attrs.get('href', '').endswith('/changes.diff')
                                     for node in document.elements('a')))
                self.assert_local_resources(document)

    def test_absent_optional_artifacts_are_not_download_links(self):
        trial = self.trial(1)
        self.artifacts(trial)
        document = self.render(self.report(trials=[trial]))
        self.assert_local_resources(document)
        links = [node.attrs.get('href') for node in document.elements('a')]
        self.assertIn('trials/0001/trial.json', links)
        for name in ('agent.log', 'setup.log', 'verify.log', 'changes.diff', 'candidate.patch', 'proposed.patch'):
            self.assertFalse(any(value.endswith(name) for value in links), name)

    def test_public_summary_redesign_keeps_whitelist_and_no_active_resources(self):
        secret = 'PRIVATE_SUMMARY_MARKER_123456789'
        report = self.report(message=secret, task=secret, requested_model=secret, created_at=secret,
                             protected_files=[secret], setup=[secret],
                             rules=[{'id': 0, 'path': secret, 'line': 1, 'text': secret}],
                             candidate=[0], case_selection={'omitted': [secret]})
        write_report(self.out, report)
        target = export_summary(self.out, self.root / 'public.html')
        content = target.read_text(encoding='utf-8')
        document = Document(content)
        self.assertNotIn(secret, content)
        self.assertEqual(len(document.elements('h1')), 1)
        self.assertFalse(document.elements('a'))
        self.assertFalse(any('src' in node.attrs or 'href' in node.attrs for node in document.elements()))
        scripts = document.elements('script')
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0].attrs.get('type'), 'application/json')
        self.assertEqual(scripts[0].attrs.get('id'), 'rulebisect-summary')
        summary = json.loads(scripts[0].text())
        self.assertEqual(summary['omitted_cases'], 1)
        self.assertEqual(summary['candidate_units'], 1)
        self.assertIn('Recorded trials / 试验次数', document.visible_text())


if __name__ == '__main__':
    unittest.main()
