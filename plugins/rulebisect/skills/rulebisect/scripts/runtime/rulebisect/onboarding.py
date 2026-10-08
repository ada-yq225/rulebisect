"""Guided local configuration; suggestions never execute project commands."""
from __future__ import annotations

import json
import re
import shlex
import tomllib
from pathlib import Path

from .setup import CONFIG_NAME, discover_instructions, git_root, init_config
from .assertions import validate_assertions


_MANIFEST_LIMIT = 256 * 1024
_SHELL_OPERATORS = {'&&', '||', ';', '|', '>', '>>', '<'}


def _manifest_text(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MANIFEST_LIMIT:
            return None
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return None


def _toml_manifest(path: Path) -> dict | None:
    source = _manifest_text(path)
    if source is None:
        return None
    try:
        return tomllib.loads(source)
    except tomllib.TOMLDecodeError:
        return None


def command_suggestions(repo: Path) -> list[dict[str, str]]:
    """Suggest commands from local manifests, without asserting they work.

    The order is stable for repositories containing multiple languages. A
    suggestion is a starting point: the user must select or replace it.
    """
    repo = Path(repo)
    suggestions = []
    python_manifest = (_toml_manifest(repo / 'pyproject.toml') is not None
                       or _manifest_text(repo / 'setup.py') is not None
                       or _manifest_text(repo / 'setup.cfg') is not None)
    tests = repo / 'tests'
    if python_manifest and tests.is_dir() and not tests.is_symlink():
        suggestions.append({'label': 'Python unittest',
                            'command': 'python -m unittest discover -s tests',
                            'reason': 'Python manifest and tests/ found; confirm these tests use unittest.'})
    source = _manifest_text(repo / 'package.json')
    if source is not None:
        try:
            package = json.loads(source)
        except (ValueError, RecursionError):
            package = None
        scripts = package.get('scripts') if isinstance(package, dict) else None
        test = scripts.get('test') if isinstance(scripts, dict) else None
        if isinstance(test, str) and test.strip() and 'no test specified' not in test.lower():
            suggestions.append({'label': 'npm test', 'command': 'npm test',
                                'reason': 'package.json has a test script; confirm its behavior and dependencies.'})
    cargo = _toml_manifest(repo / 'Cargo.toml')
    if cargo and (isinstance(cargo.get('package'), dict) or isinstance(cargo.get('workspace'), dict)):
        suggestions.append({'label': 'Cargo test', 'command': 'cargo test',
                            'reason': 'Cargo.toml declares a package or workspace.'})
    go = _manifest_text(repo / 'go.mod')
    if go and re.search(r'^\s*module\s+\S+', go, flags=re.MULTILINE):
        suggestions.append({'label': 'Go test', 'command': 'go test ./...',
                            'reason': 'go.mod declares a module.'})
    return suggestions


def _command(value: str, label: str) -> str:
    """Validate the same command form accepted by init_config."""
    try:
        argv = shlex.split(value)
    except ValueError as error:
        raise ValueError(f'{label}: {error}') from error
    if not argv or any(part in _SHELL_OPERATORS for part in argv):
        raise ValueError(f'{label} must be a command without shell operators; use a script for multiple steps.')
    return value


def _builtin_assertions(kind, input_fn):
    path = input_fn('Output file path inside the repository: ').strip()
    if kind == ':exists':
        spec = [{'type': 'file_exists', 'path': path}]
    elif kind == ':contains':
        spec = [{'type': 'file_contains', 'path': path,
                 'text': input_fn('Required text (exact substring): ')}]
    else:
        pointer = input_fn('JSON pointer (e.g. /format; Enter for whole document): ')
        value = json.loads(input_fn('Expected JSON value (e.g. "modern", true, 42): '))
        spec = [{'type': 'json_equals', 'path': path, 'pointer': pointer, 'value': value}]
    return validate_assertions(spec)


def run_wizard(repo: Path, input_fn=input, print_fn=print) -> Path:
    """Collect task/check details, then create config and a verifier wrapper.

    Every answer is collected and validated before init_config writes files.
    EOF and Ctrl-C leave the repository untouched.
    """
    repo = git_root(Path(repo))
    config_path = repo / CONFIG_NAME
    if config_path.exists() or config_path.is_symlink():
        raise ValueError(f'{CONFIG_NAME} already exists; edit it rather than overwriting.')
    instructions = discover_instructions(repo)
    if not instructions:
        raise ValueError('No AGENTS.md found. Add an instruction file, or use init --instructions FILE to select one.')
    wrapper = repo / '.rulebisect-verify.py'
    if wrapper.exists() or wrapper.is_symlink():
        raise ValueError('.rulebisect-verify.py already exists; use init --oracle to select your existing verifier.')
    print_fn('RuleBisect setup — no model calls, installations or test commands.')
    print_fn('Selected instruction files:\n' + '\n'.join(f'  {name}' for name in instructions))
    print_fn('Use one concrete task with an observable test result. A check exits 0 for pass, 1 for failure, 2+ for setup errors.')
    suggestions = command_suggestions(repo)
    try:
        task = ''
        while not task:
            task = input_fn('Task Codex should perform: ').strip()
            if not task:
                print_fn('Enter a concrete task; this cannot be empty.')
        if suggestions:
            print_fn('Possible checks — choose explicitly; these have not been run:')
            for number, suggestion in enumerate(suggestions, 1):
                print_fn(f"  {number}. {suggestion['command']}\n     {suggestion['reason']}")
        print_fn('Built-in checks: :exists, :contains, :json. Or use @FILE for a saved JSON assertion list.')
        check, assertions = None, None
        while check is None and assertions is None:
            answer = input_fn('Check command, suggestion number or built-in check: ').strip()
            if answer.isdecimal():
                number = int(answer)
                if not 1 <= number <= len(suggestions):
                    print_fn('Choose a listed number or enter your own command.')
                    continue
                answer = suggestions[number - 1]['command']
            try:
                if answer in (':exists', ':contains', ':json'):
                    assertions = _builtin_assertions(answer, input_fn)
                elif answer.startswith('@'):
                    assertions = validate_assertions(json.loads(Path(answer[1:]).read_text(encoding='utf-8')))
                else:
                    check = _command(answer, 'Check')
            except RecursionError:
                print_fn('Assertions JSON is nested too deeply; use a flat list of output checks.')
            except (ValueError, OSError) as error:
                print_fn(str(error))
        setup = None
        while True:
            answer = input_fn('Optional setup command before each trial (Enter to skip): ').strip()
            if not answer:
                break
            try:
                setup = _command(answer, 'Setup')
                break
            except ValueError as error:
                print_fn(str(error))
        model = input_fn('Optional Codex model (Enter to choose when running): ').strip() or None
        check_label = check if assertions is None else f'{len(assertions)} built-in output assertions'
        print_fn(f'Task: {task}\nCheck: {check_label}\nSetup: {setup or "none"}\nModel: {model or "choose when running"}')
    except (EOFError, KeyboardInterrupt) as error:
        raise ValueError('Setup cancelled; no files written.') from error
    path = init_config(repo, task, check, model, instructions=instructions, setup=setup, assertions=assertions)
    print_fn(f'Created {path}')
    quoted_repo = shlex.quote(str(repo))
    print_fn(f'Next: rulebisect doctor --offline --repo {quoted_repo}\nThen: rulebisect check --all --open --repo {quoted_repo}')
    print_fn('Review protected_files and instructions in the config before running Codex.')
    if assertions is not None:
        print_fn('Assertions are frozen in the generated verifier; editing an input JSON does not change saved criteria.')
    return path
