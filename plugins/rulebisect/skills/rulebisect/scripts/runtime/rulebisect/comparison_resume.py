"""Validate and reuse a completed prefix of a token-limited comparison."""
from __future__ import annotations

import copy
import json
import stat
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .comparison import trial_schedule, update_case
from .core import digest
from .report import token_cap_stop, token_totals, write_report
from .runner import codex_metadata


def require(condition, detail):
    if not condition:
        raise ValueError(f'Cannot continue comparison: {detail}.')


def evidence_root(path):
    path = Path(path).absolute()
    require(not path.is_symlink(), 'the source must not be a symlink')
    root = path if path.is_dir() else path.parent
    require(path.is_dir() or path.name == 'report.json', 'choose the evidence directory or its report.json')
    require(not root.is_symlink() and root.is_dir(), 'the evidence directory is missing or symlinked')
    return root.resolve()


def checked_path(root, relative, *, directory=False):
    # Callers supply generated relative paths, never an artifact path from JSON.
    relative = Path(relative)
    require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe evidence path')
    target = root
    for part in relative.parts:
        target = target / part
        require(not target.is_symlink(), f'symlinked evidence {relative}')
    if directory:
        require(target.is_dir(), f'missing evidence directory {relative}')
    else:
        require(target.is_file(), f'missing or non-regular evidence file {relative}')
        info = target.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, f'unsupported evidence file {relative}')
    return target


def parse_object(data, relative):
    try:
        result = json.loads(data.decode('utf-8'))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError(f'Cannot continue comparison: invalid JSON in {relative}.') from error
    require(isinstance(result, dict), f'expected an object in {relative}')
    pending = [(result, 0)]
    while pending:
        value, depth = pending.pop()
        require(depth <= 64, f'evidence JSON is nested too deeply in {relative}')
        children = value.values() if isinstance(value, dict) else value
        pending.extend((child, depth + 1) for child in children if isinstance(child, (dict, list)))
    return result


def read_prior_report(path: Path) -> dict:
    root = evidence_root(path)
    return parse_object(checked_path(root, 'report.json').read_bytes(), 'report.json')


def check_fields(previous, current, keys, location):
    for key in keys:
        require(key in previous and previous[key] == current.get(key), f'{location} {key} changed')


@dataclass
class Checkpoint:
    root: Path
    metadata: dict
    trials: list
    cases: list
    arm_trials: dict
    files: dict
    trial_files: list

    def restore(self, comparison):
        # Copy only the known files of validated trials. Check the bytes again
        # before any new model call and never follow paths stored in a report.
        for relative in ['report.json', *self.trial_files]:
            data = checked_path(self.root, relative).read_bytes()
            require(digest(data) == self.files[relative], f'evidence changed during continuation: {relative}')
            target = comparison.out / ('previous-report.json' if relative == 'report.json' else relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
        receipt = {'source': self.metadata, 'source_files_sha256': self.files}
        with (comparison.out / 'continuation.json').open('x', encoding='utf-8') as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        for key, exp in comparison.experiments.items():
            exp.report['trials'] = self.arm_trials[key]
            write_report(exp.out, exp.report)
        comparison.report.update(trials=self.trials, cases=self.cases)


def load_checkpoint(comp, fingerprint_for, check_codex):
    root = evidence_root(comp.continue_from)
    require(not (root.is_relative_to(comp.out) or comp.out.is_relative_to(root)),
            'choose a new output directory outside the previous evidence')
    files, trial_files = {}, []

    def read(relative):
        name = Path(relative).as_posix()
        data = checked_path(root, relative).read_bytes()
        files[name] = digest(data)
        return data

    def load(relative):
        return parse_object(read(relative), relative)

    def entries(relative):
        return {p.name for p in checked_path(root, relative, directory=True).iterdir()}

    previous = load('report.json')
    version = previous.get('version')
    require(version in (__version__, '0.11.0'), 'unsupported engine version')
    require(token_cap_stop(previous),
            'only a comparison stopped between trials by its reported token cap can continue')
    old_cap = previous.get('max_tokens')
    require(type(old_cap) is int and old_cap > 0, 'missing original token cap')
    require(type(comp.max_tokens) is int and comp.max_tokens > old_cap,
            'choose a new max-tokens value above the previous cap')
    require(previous.get('review_fingerprint') == fingerprint_for(version, old_cap),
            'reviewed inputs changed since the previous comparison')
    base_keys = ('schema_version', 'runner', 'requested_model', 'snapshot_sha256', 'source_snapshot_sha256', 'file_modes', 'snapshot',
                 'rules', 'task', 'verify', 'oracle', 'protected_files', 'setup', 'repeats',
                 'timeout_seconds', 'unit_mode', 'max_runs')
    check_fields(previous, comp.report, (*base_keys, 'required_calls', 'case_selection',
                 'candidate_snapshot_sha256', 'candidate_instruction_hashes', 'instruction_changes'), 'comparison')
    sources = previous.get('instruction_sources')
    require(isinstance(sources, dict), 'missing instruction sources')
    for arm, current in comp.report['instruction_sources'].items():
        old = sources.get(arm)
        require(isinstance(old, dict) and old.get('kind') == current['kind'], f'{arm} instruction source changed')
        if current['kind'] == 'git':
            require(old.get('commit') == current['commit'], f'{arm} instruction source commit changed')
        if current['kind'] == 'directory':
            require(old.get('path') == current['path'], f'{arm} instruction source directory changed')
    if comp.runner is not None or check_codex:
        check_fields(previous, comp.report, ('agent_command',), 'comparison')
        if comp.runner is None:
            check_fields(previous, comp.report, ('codex_version',), 'comparison')
    if comp.runner is None:
        require(bool(previous.get('codex_version')), 'original Codex CLI version is missing')

    records = previous.get('trials')
    require(isinstance(records, list) and 0 < len(records) < comp.report['required_calls'],
            'expected a nonempty, incomplete trial prefix')
    cases = copy.deepcopy(comp.report['cases'])
    require(entries('cases') == {case['id'] for case in cases}, 'case evidence does not match the selected cases')
    groups = defaultdict(list)
    # Limit iteration to recorded calls; the planned budget may be large.
    for index, ((case, arm), trial) in enumerate(zip(trial_schedule(cases, comp.repeats), records), 1):
        name = case['id']
        group = groups[name, arm]
        local_number = len(group) + 1
        artifact = f'cases/{name}/{arm}/trials/{local_number:04d}'
        require(isinstance(trial, dict) and trial.get('case') == name and trial.get('arm') == arm
                and trial.get('phase') == arm and trial.get('number') == index
                and trial.get('artifacts') == artifact, f'trial {index} is not the scheduled prefix')
        require(trial.get('state') == 'completed' and trial.get('outcome') in ('pass', 'fail'),
                f'trial {index} is incomplete or inconclusive')
        local = load(f'{artifact}/trial.json')
        projected = dict(local, number=index, artifacts=artifact, case=name, arm=arm)
        require(local.get('number') == local_number and local.get('artifacts') == f'trials/{local_number:04d}'
                and projected == trial, f'trial {index} disagrees with trial.json')
        exp = comp.experiments[name, arm]
        require(local.get('ids') == [rule.id for rule in exp.rules]
                and isinstance(local.get('setup'), dict) and local['setup'].get('exit_code') == 0
                and isinstance(local.get('agent'), dict) and local['agent'].get('status') == 'completed'
                and local['agent'].get('exit_code') == 0, f'trial {index} execution did not complete')
        required = {'trial.json', 'agent.log'}
        if exp.report['setup']:
            required.add('setup.log')
        protected = local.get('changed_protected_files')
        require(isinstance(protected, list) and all(path in exp.protected for path in protected),
                f'trial {index} protected-file evidence changed')
        if protected:
            require(local['outcome'] == 'fail' and local.get('reason') == 'Protected file changed'
                    and 'verifier' not in local, f'trial {index} protected-file outcome is inconsistent')
        else:
            required.add('verify.log')
            verify = local.get('verifier')
            require(isinstance(verify, dict) and verify.get('status') == 'completed'
                    and verify.get('exit_code') == (0 if local['outcome'] == 'pass' else 1),
                    f'trial {index} verifier outcome is inconsistent')
        names = entries(artifact)
        require(required <= names <= required | {'changes.diff'}, f'unexpected or missing evidence in {artifact}')
        for filename in sorted(names):
            relative = f'{artifact}/{filename}'
            if filename != 'trial.json':
                read(relative)
            trial_files.append(relative)
        if comp.runner is None or 'codex' in local:
            try:
                metadata = codex_metadata(checked_path(root, f'{artifact}/agent.log'))
            except (ValueError, RecursionError) as error:
                raise ValueError(f'Cannot continue comparison: invalid Codex log in {artifact}.') from error
            require(metadata == local.get('codex'), f'trial {index} Codex log does not match recorded usage')
            for event in metadata['reported_usage']:
                require(isinstance(event, dict) and all(
                    type(event[key]) is int and event[key] >= 0 for key in ('input_tokens', 'output_tokens', 'cached_input_tokens')
                    if key in event), f'trial {index} contains invalid reported usage')
        group.append(local)
        require(update_case(case, arm, group, comp.repeats) != 'unstable', f'trial {index} has unstable observations')

    require(cases == previous.get('cases'), 'per-case outcomes disagree with the trial records')
    totals = token_totals({'trials': records})
    require(totals == previous.get('usage_totals'), 'reported usage totals disagree with the trials')
    spent = totals['input_tokens'] + totals['output_tokens']
    before = token_totals({'trials': records[:-1]})
    require(before['input_tokens'] + before['output_tokens'] < old_cap <= spent,
            'the original token cap was not reached at the end of this prefix')
    require(comp.max_tokens > spent, f'new max-tokens must exceed the {spent} tokens already reported')
    for case in cases:
        name = case['id']
        require(entries(f'cases/{name}') == {'baseline', 'candidate'}, f'unexpected arm evidence for {name}')
        for arm in ('baseline', 'candidate'):
            exp = comp.experiments[name, arm]
            child = f'cases/{name}/{arm}'
            saved = load(f'{child}/report.json')
            check_fields(saved, exp.report, base_keys, child)
            require(saved.get('instruction_source') == sources[arm], f'{child} instruction source disagrees with the comparison')
            for key in ('version', 'codex_version', 'agent_command', 'max_tokens'):
                require(saved.get(key) == previous.get(key), f'{child} {key} differs from the comparison')
            local_records = groups[name, arm]
            require(saved.get('trials') == local_records and saved.get('usage_totals') == token_totals(saved),
                    f'{child} has unaccounted or inconsistent attempts')
            expected = {f'{number:04d}' for number in range(1, len(local_records) + 1)}
            require(entries(f'{child}/trials') == expected, f'{child} contains an unaccounted trial directory')
            oracle = exp.oracle_name
            require(read(f'{child}/oracle/{Path(oracle).name}') == exp.blobs[oracle][0], f'{child} oracle bytes changed')

    candidate = comp.experiments[cases[0]['id'], 'candidate']
    for path in candidate.instruction_paths:
        require(read(f'proposed/{path}') == candidate.blobs[path][0], f'proposed rules changed in {path}')
    require(read('proposed.patch') == comp.instruction_diff().encode('utf-8'), 'proposed instruction patch changed')
    metadata = {'source': str(root), 'source_version': version, 'report_sha256': files['report.json'],
                'previous_review_fingerprint': previous['review_fingerprint'], 'previous_max_tokens': old_cap,
                'reported_tokens_before': spent, 'reused_trials': len(records),
                'remaining_calls': comp.report['required_calls'] - len(records), 'manifest': 'continuation.json'}
    return Checkpoint(root, metadata, records, cases, groups, files, trial_files)
