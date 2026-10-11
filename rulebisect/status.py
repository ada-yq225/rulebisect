"""Offline workspace guidance, without executing configured commands."""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from .configuration import load_configuration
from .history import history
from .setup import CONFIG_NAME, doctor


def format_command(arguments: list[str]) -> str:
    """Format suggested commands for the platform's documented shell."""
    if os.name != 'nt':
        return shlex.join(arguments)
    # PowerShell single quotes preserve spaces, dollar signs and backticks.
    return ' '.join(value if re.fullmatch(r'[A-Za-z0-9_./:=+-]+', value)
                    else "'" + value.replace("'", "''") + "'" for value in arguments)


def workspace_status(repo: Path, config_path: Path | None = None) -> dict:
    """Reuse offline preflight; saved evidence is an entry point, not readiness proof."""
    result = doctor(repo, offline=True, config_path=config_path)
    result.update(state='needs_attention', repository=None, config=None,
                  instructions=[], cases=[], model=None, budget=None,
                  latest_report=None, history_warnings=[], next_steps=[])
    repository_check = next((value for value in result['checks']
                             if value['name'] == 'Git repository' and value['ok']), None)
    if repository_check is None:
        result['next_steps'] = [{'label': 'Try a simulation, or choose an existing Git repository',
                                'argv': ['rulebisect', 'demo', '--scenario', 'regression']}]
        return result
    root = Path(repository_check['detail'])
    config = Path(config_path).absolute() if config_path is not None else root / CONFIG_NAME
    result.update(repository=str(root), config=str(config))
    common = ['--repo', str(root)]
    if config_path is not None:
        common += ['--config', str(config)]
    try:
        saved = history(root)
    except OSError as error:
        saved = {'runs': [], 'warnings': [f'Cannot read saved evidence: {error}']}
    result['latest_report'] = saved['runs'][0] if saved['runs'] else None
    result['history_warnings'] = saved['warnings']
    if not config.exists() and not config.is_symlink() and config_path is None:
        found = next((value['ok'] for value in result['checks']
                      if value['name'] == 'Instruction files'), False)
        result['state'] = 'needs_configuration' if found else 'needs_instructions'
        command = ['rulebisect', 'init', '--wizard', '--repo', str(root)]
        if not found:
            command += ['--instructions', 'PATH_TO_YOUR_RULES']
        result['next_steps'] = [{'label': 'Configure a concrete task and an independent check'
                                if found else 'Select an existing instruction file; replace PATH_TO_YOUR_RULES',
                                'argv': command}]
    elif result['ok']:
        configured = load_configuration(config)
        scope = result['scope']
        result.update(state='configured', instructions=scope['instruction_files'],
                      cases=scope['cases'], model=configured.get('model'),
                      budget={'repeats': configured.get('repeats', 3),
                              'max_runs': scope['max_runs'],
                              'comparison_calls': scope['comparison_calls']})
        result['next_steps'] = [
            {'label': 'Exercise setup and verifiers on fresh initial snapshots',
             'argv': ['rulebisect', 'check', '--all', *common]},
            {'label': 'Review the reduction scope and execution cap before model calls',
             'argv': ['rulebisect', 'plan', *common]},
        ]
    else:
        result['next_steps'] = [{'label': 'Fix the inputs reported above, then recheck',
                                'argv': ['rulebisect', 'doctor', '--offline', *common]}]
    return result


def print_status(result: dict) -> None:
    labels = {'configured': 'Configuration valid — check the environment next',
              'needs_configuration': 'Choose a task and check to get started',
              'needs_instructions': 'Select the instruction file you want to investigate',
              'needs_attention': 'Inputs need attention'}
    print(labels[result['state']])
    if result['repository']:
        print(f"Repository: {result['repository']}\nConfig: {result['config']}")
    if result['state'] == 'configured':
        budget = result['budget']
        print(f"Instructions: {', '.join(result['instructions'])}\nCases: {', '.join(result['cases'])}")
        print(f"Model: {result['model'] or 'choose --model when running'}; repeats: {budget['repeats']}; execution cap: {budget['max_runs']}")
        print(f"Full comparison: {budget['comparison_calls']} planned model calls; reduction uses a variable number of calls.")
    else:
        for value in result['checks']:
            if not value['ok']:
                print(f"FIX  {value['name']}: {value['detail']}")
    for warning in [*result['warnings'], *result['history_warnings']]:
        print(f'NOTE  {warning}')
    latest = result['latest_report']
    if latest:
        print(f"Latest saved evidence: {latest['kind']} / {latest['status']} ({latest['created_at']})")
        print('This may describe an older snapshot; it does not validate current inputs.')
        print('  ' + format_command(['rulebisect', 'report', latest['path'], '--open']))
    for step in result['next_steps']:
        print(f"\n{step['label']}:\n  {format_command(step['argv'])}")
    print('\nNo model calls, setup or verifier execution. Status does not check Codex login or prove that tests pass.')
