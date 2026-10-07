from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from . import __version__
from .comparison import Comparison
from .history import history, latest_report
from .core import split_rules
from .demo import run_demo, run_comparison_demo
from .experiment import Experiment
from .report import write_report
from .setup import CONFIG_NAME, discover_instructions, doctor, draft_instructions, git_root, init_config


def default_output(repo: Path, purpose='run') -> Path:
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    return repo.parent / '.rulebisect-runs' / repo.name / f'{purpose}-{stamp}'


def add_experiment_options(parser):
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--config', type=Path, help=f'Default: repository/{CONFIG_NAME}')
    parser.add_argument('--out', type=Path, help='Default: a new evidence directory outside your repository')
    parser.add_argument('--model', help='Use this model, or the model saved by init')
    parser.add_argument('--repeats', type=int)
    parser.add_argument('--max-runs', type=int, help='Total execution cap, including old runs when resuming')
    parser.add_argument('--max-tokens', type=int, help='Stop before the next call after reported tokens reach this limit; not a billing cap')
    parser.add_argument('--timeout', type=int)
    parser.add_argument('--unit-mode', choices=['paragraph', 'section', 'file'])


def experiment_from(args):
    repo = git_root(args.repo)
    config_path = args.config or repo / CONFIG_NAME
    if not config_path.is_file():
        raise ValueError(f'Config missing: {config_path}. Start with rulebisect init --task "..." --check "..." --model MODEL')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('Config must be a JSON object')
    if args.unit_mode:
        config['unit_mode'] = args.unit_mode
    model = args.model or config.get('model')
    repeats = args.repeats if args.repeats is not None else config.get('repeats', 3)
    max_runs = args.max_runs if args.max_runs is not None else config.get('max_runs', 60)
    timeout = args.timeout if args.timeout is not None else config.get('timeout', 300)
    max_tokens = args.max_tokens if args.max_tokens is not None else config.get('max_tokens')
    out = args.out or default_output(repo, args.command)
    resume_from = latest_report(repo, resumable=True) if args.command == 'resume' and getattr(args, 'latest', False) else getattr(args, 'from_report', None)
    if resume_from is not None and resume_from.is_file():
        resume_from = resume_from.parent
    if args.command == 'compare':
        return Comparison(repo, config, out, model, repeats, max_runs, timeout, args.candidate, max_tokens=max_tokens)
    return Experiment(repo, config, out, model, repeats, max_runs, timeout,
                      resume_from=resume_from, max_tokens=max_tokens)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='RuleBisect — investigate Codex instruction failures. MIT / local-first.')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    demo = commands.add_parser('demo', help='Try a deterministic simulator without Codex or tokens')
    demo.add_argument('--out', type=Path, help='Default: a new demo directory in the current directory')
    demo.add_argument('--scenario', choices=['reduce', 'regression', 'fix'], default='reduce',
                      help='Reduce failing rules, catch a regression, or validate a scoped fix')
    demo.add_argument('--open', action='store_true', help='Open the local HTML report')
    init = commands.add_parser('init', help='Discover instructions and generate config + trusted check wrapper')
    init.add_argument('--repo', type=Path, default=Path.cwd())
    init.add_argument('--task', required=True)
    init.add_argument('--model')
    init.add_argument('--setup', help='Quoted environment command executed before every trial, e.g. "npm ci"')
    verifier = init.add_mutually_exclusive_group(required=True)
    verifier.add_argument('--check', help='Quoted command, e.g. "python -m unittest discover -s tests"; no shell expansion')
    verifier.add_argument('--oracle', help='Existing repository-relative Python verifier (exit 0/1/2+)')
    init.add_argument('--instructions', nargs='+', help='Override automatic AGENTS.md selection; Skills are opt-in')
    doc = commands.add_parser('doctor', help='Check Python, Git, Codex and login without model calls')
    doc.add_argument('--repo', type=Path, default=Path.cwd())
    doc.add_argument('--json', action='store_true')
    doc.add_argument('--offline', action='store_true', help='Validate repository inputs without checking Codex or login')
    doc.add_argument('--config', type=Path, help='Use a custom experiment config')
    doc.add_argument('--proposed', type=Path, help='Also validate a proposed instruction directory and exact comparison budget')
    inspect = commands.add_parser('inspect', help='Inspect the instruction units; no model calls')
    inspect.add_argument('files', nargs='*', type=Path)
    inspect.add_argument('--repo', type=Path, default=Path.cwd())
    inspect.add_argument('--unit-mode', choices=['paragraph', 'section', 'file'], default='paragraph')
    inspect.add_argument('--json', action='store_true')
    plan = commands.add_parser('plan', help='Validate snapshot/config and preview experiment scope; no model calls')
    add_experiment_options(plan)
    plan.add_argument('--json', action='store_true')
    check = commands.add_parser('check', help='Test the verifier on a fresh initial snapshot; no model calls')
    add_experiment_options(check)
    run = commands.add_parser('run', help='Run an experiment using your local Codex login and quota')
    add_experiment_options(run)
    run.add_argument('--open', action='store_true', help='Open the completed HTML report')
    resume = commands.add_parser('resume', help='Reuse stable search evidence after matching snapshot/settings')
    add_experiment_options(resume)
    source = resume.add_mutually_exclusive_group(required=True)
    source.add_argument('--from', dest='from_report', type=Path)
    source.add_argument('--latest', action='store_true', help='Latest model experiment in the default history directory')
    resume.add_argument('--open', action='store_true')
    render = commands.add_parser('report', help='Regenerate readable HTML/Markdown from saved evidence')
    render.add_argument('path', type=Path, nargs='?')
    render.add_argument('--latest', action='store_true')
    render.add_argument('--repo', type=Path, default=Path.cwd())
    render.add_argument('--open', action='store_true')
    compare = commands.add_parser('compare', help='Validate proposed instructions against one or more tasks before applying')
    add_experiment_options(compare)
    compare.add_argument('--proposed', '--candidate', dest='candidate', type=Path, required=True, help='Directory containing replacements at the selected instruction paths')
    compare.add_argument('--plan', action='store_true', help='Validate and show exact planned calls without Codex or artifacts')
    compare.add_argument('--open', action='store_true')
    draft = commands.add_parser('draft', help='Copy selected instructions outside the repo for editing and comparison')
    draft.add_argument('--repo', type=Path, default=Path.cwd())
    draft.add_argument('--out', type=Path, required=True)
    hist = commands.add_parser('history', help='List evidence in the default output directory; no model calls')
    hist.add_argument('--repo', type=Path, default=Path.cwd())
    hist.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'draft':
            repo = git_root(args.repo)
            result = draft_instructions(repo, args.out)
            print(f'Edit instructions in: {result}\nThen: rulebisect compare --repo "{repo}" --proposed "{result}" --plan\nOriginal instructions preserved; no model calls.')
            return 0
        if args.command == 'history':
            result = history(git_root(args.repo))
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                for record in result['runs']:
                    print(f"{record['created_at']}  {record['kind']}  {record['status']}  {record['runs']} calls\n  {record['path']}")
                for warning in result['warnings']:
                    print(f'Skipped unreadable evidence: {warning}', file=sys.stderr)
                if not result['runs']:
                    print('No saved runs in the default output directory.')
            return 0
        if args.command == 'init':
            repo = git_root(args.repo)
            path = init_config(repo, args.task, args.check, args.model, args.oracle, args.instructions, args.setup)
            print(f'Created {path}\nNext: rulebisect plan\nThen: rulebisect check (test the verifier without Codex)\nFinally: rulebisect run')
            if not args.model:
                print('Choose --model MODEL when running, or add model to the config.')
            print('Tracked test files were added to protected_files. Review this list and the selected instruction files.')
            return 0
        if args.command == 'doctor':
            result = doctor(args.repo, offline=args.offline, config_path=args.config, proposed=args.proposed)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                for value in result['checks']:
                    print(f"{'OK' if value['ok'] else 'FIX'}  {value['name']}: {value['detail']}")
                for warning in result['warnings']:
                    print(f'NOTE  {warning}')
                if result['scope']:
                    scope = result['scope']
                    print(f"Cases: {', '.join(scope['cases'])}; comparison calls: {scope.get('required_calls', scope.get('comparison_calls'))}; cap: {scope['max_runs']}")
                print('No model calls; setup and verifier not executed / 不消耗模型额度，不执行验证器')
            return 0 if result['ok'] else 2
        if args.command == 'inspect':
            files = args.files
            if not files:
                repo = git_root(args.repo)
                files = [repo / name for name in discover_instructions(repo)]
            units = []
            for path in files:
                units.extend(split_rules(str(path), path.read_bytes().decode('utf-8'), len(units), args.unit_mode))
            if not units:
                raise ValueError('No units found; specify instruction files explicitly.')
            if args.json:
                print(json.dumps([r.to_dict() for r in units], ensure_ascii=False, indent=2))
            else:
                for rule in units:
                    print(f'#{rule.id}  {rule.path}:{rule.line}\n{rule.text.rstrip()}\n')
                print(f'{len(units)} units. No model calls.')
            return 0
        if args.command == 'report':
            if bool(args.path) == bool(args.latest):
                raise ValueError('Choose report PATH or report --latest --repo PATH')
            path = latest_report(git_root(args.repo)) if args.latest else args.path
            out = path.parent if path.is_file() else path
            report = json.loads((out / 'report.json').read_text(encoding='utf-8'))
            write_report(out, report)
        elif args.command == 'demo':
            print('DETERMINISTIC SIMULATION — no Codex or model call', flush=True)
            out = args.out or Path.cwd() / f"rulebisect-demo-{args.scenario}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
            report = (run_demo(out) if args.scenario == 'reduce' else
                      run_comparison_demo(out, fixed=args.scenario == 'fix'))
            expected = {'reduce': 'observed_1_minimal', 'regression': 'regressions_observed',
                        'fix': 'no_regressions_observed'}[args.scenario]
            if report['status'] != expected:
                raise ValueError(f"Demo did not produce its expected result ({expected}); inspect {out}")
            print('Demo completed as expected. Simulation executions are not model calls.')
        else:
            experiment = experiment_from(args)
            out = experiment.out
            if args.command == 'compare' and args.plan:
                print(json.dumps(experiment.prepare(), ensure_ascii=False, indent=2))
                return 0
            if args.command == 'plan':
                experiment.prepare(materialize=False, check_codex=False)
                n = len(experiment.rules)
                result = {'model': experiment.model, 'instruction_files': experiment.instruction_paths,
                          'units': n, 'unit_mode': experiment.report['unit_mode'], 'snapshot_files': len(experiment.blobs),
                          'snapshot_bytes': sum(len(v[0]) for v in experiment.blobs.values()),
                          'protected_files': experiment.protected, 'setup': experiment.config.get('setup', []), 'repeats': experiment.repeats,
                          'minimum_baseline_calls': 2 * experiment.repeats, 'max_runs': experiment.max_runs,
                          'confirmation_calls_if_all_units_retained': (n + 1) * experiment.repeats,
                          'max_tokens': experiment.max_tokens, 'output': str(out), 'model_calls': 0}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                if not args.json:
                    print('No model calls. Actual runs depend on results; the run cap may stop before confirmation.')
                return 0
            if args.command == 'check':
                result = experiment.check_initial()
                print(f'Verifier on original snapshot: {result}\nNo Codex calls. Log: {out / "check.log"}')
                return 0 if result.get('exit_code') in (0, 1) else 2
            if not experiment.model:
                raise ValueError('Choose --model MODEL, or save model with init --model MODEL.')
            print(f'Using your local Codex login. Model: {experiment.model}; total run cap: {experiment.max_runs}.\nEvidence: {out}', flush=True)
            report = experiment.execute()
        print(f"\n{report['status']}: {report['message']}\nReport: {out.resolve() / 'report.html'}")
        if getattr(args, 'open', False):
            webbrowser.open((out.resolve() / 'report.html').as_uri())
        return 0 if report['status'] in ('observed_1_minimal', 'no_regressions_observed') or args.command in ('report', 'demo') else 2
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'rulebisect: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
