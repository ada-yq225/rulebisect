"""Repeated before/after checks for instruction changes, using independent verifiers."""
from __future__ import annotations

import copy
import difflib
import io
import json
import re
import subprocess
from pathlib import Path

from . import __version__
from .core import StopSearch, digest
from .experiment import Experiment
from .report import token_totals, write_report
from .revisions import read_revision


def suite_cases(config):
    values = config.get('cases', [{'id': 'task'}])
    if not isinstance(values, list) or not values:
        raise ValueError('cases must be a non-empty list')
    result, seen = [], set()
    for case in values:
        if not isinstance(case, dict) or set(case) - {'id', 'task', 'oracle', 'verify', 'protected_files'}:
            raise ValueError('Each case supports id, task, oracle, verify and protected_files only')
        name = case.get('id')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name) or name.casefold() in seen or re.fullmatch(r'con|prn|aux|nul|com[1-9]|lpt[1-9]', name, re.I):
            raise ValueError('Case ids must be unique portable names (letters, digits, underscore, dash; max 64)')
        seen.add(name.casefold())
        merged = copy.deepcopy(config)
        merged.pop('cases', None)
        merged.update({key: value for key, value in case.items() if key != 'id'})
        result.append((name, merged))
    return result


def select_cases(config, names=None):
    """Select an explicit subset while retaining its scope in saved evidence."""
    all_cases = suite_cases(config)
    available = [name for name, _ in all_cases]
    selected = available if names is None else list(names)
    if not selected or len(set(selected)) != len(selected) or any(name not in available for name in selected):
        raise ValueError('Choose unique case ids from: ' + ', '.join(available))
    result = copy.deepcopy(config)
    values = result.get('cases', [{'id': 'task'}])
    result['cases'] = [case for case in values if case['id'] in selected]
    # Filtering changes calls, not the available verifier/dependency snapshot.
    protected = set()
    for _, case in all_cases:
        files = case.get('protected_files', [])
        if not isinstance(files, list) or any(not isinstance(v, str) for v in files):
            raise ValueError('protected_files must be a list of paths')
        oracle = case.get('oracle')
        if not isinstance(oracle, str):
            raise ValueError('Every case requires an oracle')
        protected.update(files)
        protected.add(oracle)
    for case in result['cases']:
        case['protected_files'] = sorted(protected)
    result['_case_selection'] = {'available': available, 'selected': [case['id'] for case in result['cases']],
                                 'omitted': [name for name in available if name not in selected]}
    return result


def load_candidate(root, instructions):
    root = root.resolve()
    if not root.is_dir():
        raise ValueError('Candidate must be a directory containing the selected instruction paths')
    result = {}
    for name in instructions:
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts:
            raise ValueError(f'Unsafe candidate path: {name}')
        target = root / relative
        if any((root / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)) or not target.is_file():
            raise ValueError(f'Candidate instruction missing or symlinked: {name}')
        data = target.read_bytes()
        data.decode('utf-8')
        result[name] = data
    return result


class Comparison:
    def __init__(self, repo, config, out, model, repeats, max_runs, timeout,
                 candidate=None, max_tokens=None, runner=None, *, base_ref=None, proposed_ref=None, expected_inputs=None):
        self.repo, self.config, self.out = repo.resolve(), config, out.resolve()
        self.model, self.repeats, self.max_runs, self.timeout = model, repeats, max_runs, timeout
        self.candidate, self.max_tokens, self.runner = candidate, max_tokens, runner
        self.base_ref, self.proposed_ref = base_ref, proposed_ref
        self.expected_inputs = expected_inputs
        if candidate is not None and proposed_ref is not None:
            raise ValueError('Choose one candidate source: --proposed DIRECTORY or --proposed-ref REV.')
        if candidate is None and base_ref is None and proposed_ref is None:
            raise ValueError('Choose --base-ref REV, --proposed-ref REV or --proposed DIRECTORY.')
        self.experiments = {}

    def _instruction_sources(self, exp):
        selected = self.config.get('instructions')
        if not isinstance(selected, list) or not selected:
            raise ValueError('Config requires an explicit instructions list')
        paths = [exp.relative(path) for path in selected]
        working_tree = ({'kind': 'worktree'}, None)
        baseline = working_tree if self.base_ref is None else read_revision(self.repo, self.base_ref, paths)
        if self.proposed_ref is not None:
            candidate = (baseline if self.proposed_ref == self.base_ref
                         else read_revision(self.repo, self.proposed_ref, paths))
        elif self.candidate is not None:
            candidate = ({'kind': 'directory', 'path': str(self.candidate.resolve())},
                         load_candidate(self.candidate, paths))
        else:
            candidate = working_tree
        return {'baseline': baseline, 'candidate': candidate}

    def _describe_changes(self, before, after):
        changes, patch = [], []
        for path in before.instruction_paths:
            old, new = before.blobs[path][0], after.blobs[path][0]
            added = removed = 0
            if old != new:
                # Split on LF only, so CRLF and final-newline changes survive.
                old_lines = [line.decode('utf-8') for line in io.BytesIO(old)]
                new_lines = [line.decode('utf-8') for line in io.BytesIO(new)]
                headers = ['a/' + path, 'b/' + path]
                if any(c in path for c in ('\n', '\r', '\t', '"', '\\')):
                    headers = [json.dumps(name, ensure_ascii=False) for name in headers]
                for index, line in enumerate(difflib.unified_diff(old_lines, new_lines, *headers)):
                    if index >= 2:  # Skip file headers, regardless of the line content.
                        added += line.startswith('+')
                        removed += line.startswith('-')
                    patch.append(line)
                    if not line.endswith('\n'):
                        patch.append('\n\\ No newline at end of file\n')
            changes.append({'path': path, 'changed': old != new, 'added_lines': added,
                            'removed_lines': removed, 'before_sha256': digest(old), 'after_sha256': digest(new)})
        self._patch = ''.join(patch)
        return changes

    def _review_fingerprint(self, baseline, candidate, cases, selection):
        """Identify effective comparison inputs independent of their source labels."""
        checks = []
        for name, _ in cases:
            frozen = self.experiments[name, 'baseline'].report
            checks.append({'id': name, 'task': frozen['task'], 'oracle': frozen['oracle'],
                           'verify': frozen['verify'], 'setup': frozen['setup'],
                           'protected_files': sorted(frozen['protected_files'])})
        inputs = {'format': 1, 'engine_version': __version__,
                  'baseline_snapshot': baseline.report['snapshot_sha256'],
                  'candidate_snapshot': candidate.report['snapshot_sha256'],
                  'instruction_files': baseline.instruction_paths, 'case_selection': selection,
                  'checks': checks, 'unit_mode': baseline.report['unit_mode'],
                  'repeats': self.repeats, 'timeout': self.timeout,
                  'max_runs': self.max_runs, 'max_tokens': self.max_tokens}
        return digest(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode('utf-8'))

    def instruction_diff(self) -> str:
        """Unified diff of the frozen rule bytes from the most recent successful prepare."""
        return self._patch

    def prepare(self, check_codex=False):
        cases = suite_cases(self.config)
        # Protect all case verifiers in every arm, including untracked verifiers.
        protected = set()
        for _, config in cases:
            files = config.get('protected_files', [])
            if not isinstance(files, list) or any(not isinstance(v, str) for v in files):
                raise ValueError('protected_files must be a list of paths')
            oracle = config.get('oracle')
            if not isinstance(oracle, str):
                raise ValueError('Each case needs an oracle (or inherit the top-level oracle)')
            protected.update(files)
            protected.add(oracle)
        first = None
        for name, config in cases:
            config['protected_files'] = sorted(protected)
            for arm in ('baseline', 'candidate'):
                exp = Experiment(self.repo, config, self.out / 'cases' / name / arm,
                                 self.model, self.repeats, self.max_runs, self.timeout, runner=self.runner, max_tokens=self.max_tokens)
                if first is None:
                    sources = self._instruction_sources(exp)
                source_info, overrides = sources[arm]
                exp.prepare(materialize=False, check_codex=check_codex and first is None,
                            instruction_overrides=overrides, allow_empty=True)
                exp.report['instruction_source'] = source_info
                if first is None:
                    first = exp
                if exp.report['source_snapshot_sha256'] != first.report['source_snapshot_sha256']:
                    raise ValueError('Source changed while preparing the suite; retry on a stable repository')
                exp.report['codex_version'] = first.report.get('codex_version')
                exp.progress = lambda record, name=name, arm=arm: print(f"  run {len(self.report['trials']) + 1}/{self.max_runs}: {name}/{arm} -> {record['outcome']}", flush=True)
                self.experiments[name, arm] = exp
        # Validate the parent separately: children have not written anything yet.
        if self.out.is_relative_to(self.repo) or (self.out.exists() and any(self.out.iterdir())):
            raise ValueError('Comparison output must be a new empty directory outside the repository')
        required = len(cases) * 2 * self.repeats
        if self.max_runs < required:
            raise ValueError(f'Comparison needs {required} calls ({len(cases)} cases × 2 variants × {self.repeats} repeats); increase max-runs or reduce the suite')
        # Freeze candidate content once. All arms must use exactly the same proposed files.
        candidate_hash = self.experiments[cases[0][0], 'candidate'].report['snapshot_sha256']
        if any(exp.report['snapshot_sha256'] != candidate_hash for (name, arm), exp in self.experiments.items() if arm == 'candidate'):
            raise ValueError('Candidate changed while preparing the suite; retry with stable files')
        candidate = self.experiments[cases[0][0], 'candidate']
        self.report = copy.deepcopy(first.report)
        self.report['instruction_sources'] = {arm: metadata for arm, (metadata, _) in sources.items()}
        self.report['instruction_changes'] = self._describe_changes(first, candidate)
        self.report.update(kind='comparison', limitations=['Finite repeated independent checks, not statistical confidence or causal attribution.', 'Only selected instruction contents vary; external context and model routing remain unpinned.', 'No guarantee on tasks or environments outside the chosen suite.'], candidate=[], trials=[], evaluations=[], cases=[],
                           status='pending', message='Prepared before/after comparison.', max_runs=self.max_runs,
                           max_tokens=self.max_tokens, candidate_snapshot_sha256=candidate_hash,
                           required_calls=required, candidate_instruction_hashes={name: digest(value[0]) for name, value in self.experiments[cases[0][0], 'candidate'].blobs.items() if name in first.instruction_paths})
        self.report['case_selection'] = copy.deepcopy(self.config.get('_case_selection',
            {'available': [name for name, _ in cases], 'selected': [name for name, _ in cases], 'omitted': []}))
        fingerprint = self._review_fingerprint(first, candidate, cases, self.report['case_selection'])
        if self.expected_inputs is not None and self.expected_inputs != fingerprint:
            raise ValueError('Reviewed inputs changed; run rulebisect review again.')
        self.report['review_fingerprint'] = fingerprint
        for name, config in cases:
            self.report['cases'].append({'id': name, 'task': config['task'], 'oracle': config['oracle'], 'baseline': None, 'candidate': None, 'verdict': 'pending'})
        return {'cases': [name for name, _ in cases], 'variants': ['baseline', 'candidate'],
                'instruction_files': first.instruction_paths, 'required_calls': required,
                'max_runs': self.max_runs, 'max_tokens': self.max_tokens, 'model': self.model,
                'snapshot_sha256': first.report['snapshot_sha256'], 'candidate_snapshot_sha256': candidate_hash,
                'snapshot_inputs': first.report['snapshot_inputs'],
                'setup': self.config.get('setup', []), 'output': str(self.out), 'model_calls': 0,
                'case_selection': self.report['case_selection'],
                'review_fingerprint': fingerprint,
                'instruction_sources': self.report['instruction_sources'],
                'instruction_changes': self.report['instruction_changes']}

    def record_trial(self, exp, case, arm):
        before = len(exp.report['trials'])
        try:
            return exp.trial(None, arm)
        finally:
            if len(exp.report['trials']) > before:
                record = copy.deepcopy(exp.report['trials'][-1])
                record.update(number=len(self.report['trials']) + 1, case=case, arm=arm,
                              artifacts=f'cases/{case}/{arm}/{record["artifacts"]}')
                self.report['trials'].append(record)
                write_report(self.out, self.report)

    def execute(self):
        self.prepare(check_codex=True)
        for exp in self.experiments.values():
            exp.materialize()
        proposed = next(exp for (name, arm), exp in self.experiments.items() if arm == 'candidate')
        for name in proposed.instruction_paths:
            target = self.out / 'proposed' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(proposed.blobs[name][0])
        (self.out / 'proposed.patch').write_bytes(self.instruction_diff().encode('utf-8'))
        self.report['status'] = 'running'
        write_report(self.out, self.report)
        try:
            for case in self.report['cases']:
                observations = {'baseline': [], 'candidate': []}
                usage = {'baseline': [], 'candidate': []}
                for repeat in range(self.repeats):
                    # Alternate arm order to reduce a systematic first/last timing bias.
                    arms = ('baseline', 'candidate') if repeat % 2 == 0 else ('candidate', 'baseline')
                    for arm in arms:
                        totals = token_totals(self.report)
                        if self.max_tokens is not None and totals['input_tokens'] + totals['output_tokens'] >= self.max_tokens:
                            raise StopSearch('Reported token cap reached before the next call; comparison incomplete. Not a billing cap.')
                        if len(self.report['trials']) >= self.max_runs:
                            raise StopSearch('Execution cap reached; comparison incomplete.')
                        record = self.record_trial(self.experiments[case['id'], arm], case['id'], arm)
                        observations[arm].append(record['outcome'])
                        usage[arm].append(record)
                        counts = {key: observations[arm].count(key) for key in ('pass', 'fail', 'error')}
                        outcome = 'error' if counts['error'] else 'unstable' if counts['pass'] and counts['fail'] else observations[arm][0] if len(observations[arm]) == self.repeats else 'incomplete'
                        totals = token_totals({'trials': usage[arm]})
                        case[arm] = {**counts, 'outcome': outcome, 'reported_tokens': totals['input_tokens'] + totals['output_tokens'], 'usage_reported_runs': totals['reported_runs']}
                        write_report(self.out, self.report)
                        if outcome in ('error', 'unstable'):
                            raise StopSearch(f'{case["id"]}/{arm}: {outcome}; no reliable before/after conclusion.')
                before, after = case['baseline']['outcome'], case['candidate']['outcome']
                case['verdict'] = 'regression' if (before, after) == ('pass', 'fail') else 'improvement' if (before, after) == ('fail', 'pass') else 'unchanged_pass' if after == 'pass' else 'unchanged_fail'
                write_report(self.out, self.report)
            verdicts = [case['verdict'] for case in self.report['cases']]
            if 'regression' in verdicts:
                self.report.update(status='regressions_observed', message='At least one previously passing task failed under the proposed instructions. Review before applying.')
            elif 'unchanged_fail' in verdicts:
                self.report.update(status='candidate_failed', message='The proposed instructions still failed at least one task. This suite does not validate the fix.')
            else:
                self.report.update(status='no_regressions_observed', message='Every candidate task passed every repetition; no regression observed in this finite suite. Not a guarantee on other tasks.')
        except (StopSearch, OSError, ValueError, subprocess.SubprocessError) as error:
            self.report.update(status='inconclusive', message=str(error))
        except KeyboardInterrupt:
            self.report.update(status='interrupted', message='Comparison interrupted; partial evidence retained. Compare again in a new output directory.')
        finally:
            write_report(self.out, self.report)
        return self.report
