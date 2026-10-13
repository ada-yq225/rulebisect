from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from . import __version__
from .configuration import load_configuration
from .comparison import Comparison, select_cases
from .checks import SuiteCheck
from .onboarding import run_wizard
from .suite import add_case, list_cases, remove_case
from .assertions import validate_assertions
from .share import export_summary
from .history import history, latest_report
from .status import format_command, print_status, workspace_status
from .core import split_rules
from .demo import run_demo, run_comparison_demo
from .experiment import Experiment
from .report import write_report
from .setup import CONFIG_NAME, _repository_file, discover_instructions, doctor, draft_instructions, git_root, init_config, snapshot_warnings


def default_output(repo: Path, purpose='run') -> Path:
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    return repo.parent / '.rulebisect-runs' / repo.name / f'{purpose}-{stamp}'


def load_assertions(path):
    if path is None:
        return None
    try:
        spec = json.loads(path.read_text(encoding='utf-8'))
    except RecursionError as error:
        raise ValueError('Assertions JSON is nested too deeply; use a flat list of output checks.') from error
    return validate_assertions(spec)


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
    config = load_configuration(config_path)
    if args.unit_mode:
        config['unit_mode'] = args.unit_mode
    if args.command == 'compare' or (args.command == 'check' and getattr(args, 'all', False)):
        config = select_cases(config, getattr(args, 'cases', None))
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
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(f'RuleBisect {__version__} — debug Codex rules and catch instruction regressions.\n'
              '\nTry a simulation:  rulebisect demo --scenario regression --open\n'
              'See your next step: rulebisect status\n'
              'Set up a task:      rulebisect init --wizard\n'
              'All commands:       rulebisect --help\n'
              '\nThese entry points make no model calls. Real run/compare/resume executions use your Codex account.')
        return 0
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
    init.add_argument('--task')
    init.add_argument('--wizard', action='store_true', help='Guided output checks or test commands; no model calls')
    init.add_argument('--model')
    init.add_argument('--setup', help='Quoted environment command executed before every trial, e.g. "npm ci"')
    verifier = init.add_mutually_exclusive_group()
    verifier.add_argument('--check', help='Quoted command, e.g. "python -m unittest discover -s tests"; no shell expansion')
    verifier.add_argument('--oracle', help='Existing standalone repository-relative Python verifier (exit 0/1/2+); use --check for project imports')
    verifier.add_argument('--assertions', type=Path, help='JSON output checks; compile an independent verifier without writing Python')
    init.add_argument('--instructions', nargs='+', help='Override automatic AGENTS.md selection; Skills are opt-in')
    init.add_argument('--include', nargs='+', metavar='FILE', help='Include exact repository-relative baseline files without Git staging; no directory recursion or glob expansion')
    doc = commands.add_parser('doctor', help='Check Python, Git, Codex and login without model calls')
    doc.add_argument('--repo', type=Path, default=Path.cwd())
    doc.add_argument('--json', action='store_true')
    doc.add_argument('--offline', action='store_true', help='Validate repository inputs without checking Codex or login')
    doc.add_argument('--config', type=Path, help='Use a custom experiment config')
    doc.add_argument('--proposed', type=Path, help='Also validate a proposed instruction directory and exact comparison budget')
    status = commands.add_parser('status', help='Show offline input readiness, saved evidence and next steps; no model calls')
    status.add_argument('--repo', type=Path, default=Path.cwd())
    status.add_argument('--config', type=Path, help='Use a custom experiment config')
    status.add_argument('--json', action='store_true', help='Print readiness and suggested argument arrays')
    inspect = commands.add_parser('inspect', help='Inspect the instruction units; no model calls')
    inspect.add_argument('files', nargs='*', type=Path)
    inspect.add_argument('--repo', type=Path, default=Path.cwd())
    inspect.add_argument('--config', type=Path, help='Inspect saved instruction selection; default: repository/.rulebisect.json if present')
    inspect.add_argument('--unit-mode', choices=['paragraph', 'section', 'file'], help='Override saved mode; default: paragraph when no configuration is selected')
    inspect.add_argument('--json', action='store_true')
    plan = commands.add_parser('plan', help='Validate snapshot/config and preview experiment scope; no model calls')
    add_experiment_options(plan)
    plan.add_argument('--json', action='store_true')
    check = commands.add_parser('check', help='Test the verifier on a fresh initial snapshot; no model calls')
    add_experiment_options(check)
    check.add_argument('--all', action='store_true', help='Check setup and verifier for every suite case without Codex')
    check.add_argument('--cases', nargs='+', help='Select case ids when using --all')
    check.add_argument('--open', action='store_true')
    check.add_argument('--require-pass', action='store_true', help='Exit 1 for behavior failures, 2 for execution errors; default accepts initial behavior failures')
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
    compare.add_argument('--cases', nargs='+', help='Run only these case ids; omitted tasks remain explicitly untested')
    case = commands.add_parser('case', help='Save, list and remove regression cases without editing JSON')
    case_commands = case.add_subparsers(dest='case_command', required=True)
    for name in ('list', 'add', 'remove'):
        action = case_commands.add_parser(name)
        action.add_argument('--repo', type=Path, default=Path.cwd())
        action.add_argument('--config', type=Path)
        if name == 'list':
            action.add_argument('--json', action='store_true')
        else:
            action.add_argument('id')
        if name == 'add':
            action.add_argument('--task', required=True)
            verification = action.add_mutually_exclusive_group(required=True)
            verification.add_argument('--check', help='Trusted command; saved but not executed')
            verification.add_argument('--oracle', help='Existing standalone repository-relative verifier; use --check for project imports')
            verification.add_argument('--assertions', type=Path, help='JSON list of deterministic file/text/JSON checks')
    share = commands.add_parser('share', help='Export a standalone summary that excludes tasks, code, identifiers and logs')
    share.add_argument('path', type=Path, help='Saved evidence directory or report.json')
    share.add_argument('--out', type=Path, required=True, help='New HTML file outside the evidence directory; no upload')
    draft = commands.add_parser('draft', help='Copy selected instructions outside the repo for editing and comparison')
    draft.add_argument('--repo', type=Path, default=Path.cwd())
    draft.add_argument('--config', type=Path, help='Use the same custom configuration as plan and compare')
    draft.add_argument('--out', type=Path, required=True)
    hist = commands.add_parser('history', help='List evidence in the default output directory; no model calls')
    hist.add_argument('--repo', type=Path, default=Path.cwd())
    hist.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'status':
            result = workspace_status(args.repo, args.config)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print_status(result)
            return 0 if result['ok'] else 2
        if args.command == 'share':
            path = export_summary(args.path, args.out)
            print(f'Summary saved: {path}\nIncludes aggregate outcomes only; no tasks, code, names or logs. Review before sharing. No upload or model calls.')
            return 0
        if args.command == 'case':
            repo = git_root(args.repo)
            path = args.config or repo / CONFIG_NAME
            if args.case_command == 'list':
                values = list_cases(path)
                if args.json:
                    print(json.dumps(values, ensure_ascii=False, indent=2))
                else:
                    for value in values:
                        print(f"{value['id']}: {value['task']}\n  verifier: {value['oracle']}")
                    print(f'{len(values)} cases. No model calls.')
            elif args.case_command == 'add':
                result = add_case(repo, path, args.id, args.task, check=args.check, oracle=args.oracle,
                                  assertions=load_assertions(args.assertions))
                print(f"Saved case {result['id']}. Next: rulebisect check --all --repo \"{repo}\" --config \"{path}\"\nNo model calls; verifier was saved without execution.")
                if args.assertions:
                    print('Assertions are frozen in the generated verifier; editing the input JSON does not change saved criteria.')
            else:
                remove_case(path, args.id)
                print(f'Removed case {args.id}; verifier files preserved. No model calls.')
            return 0
        if args.command == 'draft':
            repo = git_root(args.repo)
            result = draft_instructions(repo, args.out, config_path=args.config)
            command = ['rulebisect', 'compare', '--repo', str(repo), '--proposed', str(result), '--plan']
            if args.config is not None:
                command += ['--config', str(args.config.absolute())]
            print(f'Edit instructions in: {result}\nThen: {format_command(command)}\nOriginal instructions preserved; no model calls.')
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
            if args.wizard:
                if any((args.task, args.check, args.oracle, args.assertions, args.model, args.setup)):
                    raise ValueError('Use init --wizard --repo PATH [--instructions FILE ...] [--include FILE ...], or provide explicit init options without --wizard')
                run_wizard(repo, instructions=args.instructions, include_files=args.include)
                return 0
            if not args.task or not (args.check or args.oracle or args.assertions):
                raise ValueError('Use init --wizard, or provide --task and --check/--oracle/--assertions')
            path = init_config(repo, args.task, args.check, args.model, args.oracle, args.instructions, args.setup,
                               assertions=load_assertions(args.assertions), include_files=args.include)
            print(f'Created {path}\nNext: {format_command(["rulebisect", "status", "--repo", str(repo)])}')
            if not args.model:
                print('Choose --model MODEL when running, or add model to the config.')
            print('Tracked test files were added to protected_files. Review this list and the selected instruction files.')
            if args.assertions:
                print('Assertions are frozen in the generated verifier; editing the input JSON does not change saved criteria.')
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
            unit_mode = args.unit_mode or 'paragraph'
            if files and args.config is not None:
                raise ValueError('Choose explicit instruction files or --config, not both.')
            if not files:
                repo = git_root(args.repo)
                path = args.config or repo / CONFIG_NAME
                if args.config is not None or path.exists() or path.is_symlink():
                    config = load_configuration(path)
                    if args.unit_mode is None:
                        unit_mode = config.get('unit_mode', 'paragraph')
                    names = config.get('instructions')
                    if not isinstance(names, list) or not names:
                        raise ValueError('Config requires an explicit instructions list')
                    names = [_repository_file(repo, name, 'Instruction') for name in names]
                    if len(set(names)) != len(names):
                        raise ValueError('Duplicate instruction files are unsupported')
                else:
                    names = discover_instructions(repo)
                files = [repo / name for name in names]
            units = []
            for path in files:
                units.extend(split_rules(str(path), path.read_bytes().decode('utf-8'), len(units), unit_mode))
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
                          'snapshot_inputs': experiment.report['snapshot_inputs'],
                          'protected_files': experiment.protected, 'setup': experiment.config.get('setup', []), 'repeats': experiment.repeats,
                          'minimum_baseline_calls': 2 * experiment.repeats, 'max_runs': experiment.max_runs,
                          'confirmation_calls_if_all_units_retained': (n + 1) * experiment.repeats,
                          'max_tokens': experiment.max_tokens, 'output': str(out), 'model_calls': 0}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                if not args.json:
                    for warning in snapshot_warnings(result['snapshot_inputs']):
                        print(f'NOTE  {warning}')
                    print('No model calls. Actual runs depend on results; the run cap may stop before confirmation.')
                return 0
            if args.command == 'check':
                if args.cases and not args.all:
                    raise ValueError('Use check --all --cases ID ... to check selected suite cases')
                if args.all:
                    config = dict(experiment.config, model=experiment.model, repeats=experiment.repeats,
                                  max_runs=experiment.max_runs, timeout=experiment.timeout, max_tokens=experiment.max_tokens)
                    report = SuiteCheck(experiment.repo, config, out).execute()
                    for warning in snapshot_warnings(report.get('snapshot_inputs', {})):
                        print(f'NOTE  {warning}')
                    counts = {outcome: sum(case['outcome'] == outcome for case in report['cases'])
                              for outcome in ('pass', 'fail', 'error', 'pending')}
                    print(f"Checks: {counts['pass']} passed, {counts['fail']} behavior failures, {counts['error']} execution errors, {counts['pending']} pending.")
                    omitted = report.get('case_selection', {}).get('omitted', [])
                    if omitted:
                        print(f"Untested cases: {', '.join(omitted)}")
                    for case in report['cases']:
                        if case['outcome'] in ('fail', 'error'):
                            print(f"  {case['id']} details: {out / 'cases' / case['id'] / 'report.html'}")
                    print(f"{report['status']}: {report['message']}\nReport: {out / 'report.html'}")
                    if args.open:
                        webbrowser.open((out.resolve() / 'report.html').as_uri())
                    if report['status'] != 'checks_completed':
                        return 2
                    return 1 if args.require_pass and counts['fail'] else 0
                result = experiment.check_initial()
                for warning in snapshot_warnings(experiment.report.get('snapshot_inputs', {})):
                    print(f'NOTE  {warning}')
                code = result.get('exit_code')
                outcome = 'passed' if code == 0 else 'behavior failure' if code == 1 else 'execution error'
                print(f'Initial snapshot: {outcome} (exit {code}).')
                if code == 1:
                    print('Behavior failures can be expected before the task is implemented; inspect the check before running Codex.')
                elif code != 0:
                    print('Fix setup or the verifier before running Codex.')
                if result.get('reason'):
                    print(result['reason'])
                print(f'No Codex calls. Report: {out / "report.html"}\nLogs: {out}')
                if args.open:
                    webbrowser.open((out.resolve() / 'report.html').as_uri())
                return (1 if args.require_pass and code == 1 else 0) if code in (0, 1) else 2
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
