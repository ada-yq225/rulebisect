"""Repeated before/after checks for instruction changes, using independent verifiers."""
from __future__ import annotations

import copy
import difflib
import json
import re
import subprocess
from pathlib import Path

from .core import StopSearch, digest
from .experiment import Experiment
from .report import token_totals, write_report


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
                 candidate, max_tokens=None, runner=None):
        self.repo, self.config, self.out = repo.resolve(), config, out.resolve()
        self.model, self.repeats, self.max_runs, self.timeout = model, repeats, max_runs, timeout
        self.candidate, self.max_tokens, self.runner = candidate, max_tokens, runner
        self.experiments = {}

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
        first, proposed = None, None
        for name, config in cases:
            config['protected_files'] = sorted(protected)
            for arm in ('baseline', 'candidate'):
                exp = Experiment(self.repo, config, self.out / 'cases' / name / arm,
                                 self.model, self.repeats, self.max_runs, self.timeout, runner=self.runner, max_tokens=self.max_tokens)
                if proposed is None and first is not None:
                    proposed = load_candidate(self.candidate, first.instruction_paths)
                overrides = proposed if arm == 'candidate' else None
                exp.prepare(materialize=False, check_codex=check_codex and first is None,
                            instruction_overrides=overrides, allow_empty=True)
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
        self.report = copy.deepcopy(first.report)
        self.report.update(kind='comparison', limitations=['Finite repeated independent checks, not statistical confidence or causal attribution.', 'Only selected instruction contents vary; external context and model routing remain unpinned.', 'No guarantee on tasks or environments outside the chosen suite.'], candidate=[], trials=[], evaluations=[], cases=[],
                           status='pending', message='Prepared before/after comparison.', max_runs=self.max_runs,
                           max_tokens=self.max_tokens, candidate_snapshot_sha256=candidate_hash,
                           required_calls=required, candidate_instruction_hashes={name: digest(value[0]) for name, value in self.experiments[cases[0][0], 'candidate'].blobs.items() if name in first.instruction_paths})
        for name, config in cases:
            self.report['cases'].append({'id': name, 'task': config['task'], 'oracle': config['oracle'], 'baseline': None, 'candidate': None, 'verdict': 'pending'})
        return {'cases': [name for name, _ in cases], 'variants': ['baseline', 'candidate'],
                'instruction_files': first.instruction_paths, 'required_calls': required,
                'max_runs': self.max_runs, 'max_tokens': self.max_tokens, 'model': self.model,
                'snapshot_sha256': first.report['snapshot_sha256'], 'candidate_snapshot_sha256': candidate_hash,
                'setup': self.config.get('setup', []), 'output': str(self.out), 'model_calls': 0}

    def record_trial(self, exp, case, arm):
        before = len(exp.report['trials'])
        try:
            return exp.trial([r.id for r in exp.rules], arm)
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
        original = next(exp for (name, arm), exp in self.experiments.items() if arm == 'baseline')
        patch = []
        for name in proposed.instruction_paths:
            target = self.out / 'proposed' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(proposed.blobs[name][0])
            for line in difflib.unified_diff(original.blobs[name][0].decode('utf-8').splitlines(True), proposed.blobs[name][0].decode('utf-8').splitlines(True), fromfile='a/' + name, tofile='b/' + name):
                patch.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
        (self.out / 'proposed.patch').write_text(''.join(patch), encoding='utf-8')
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
