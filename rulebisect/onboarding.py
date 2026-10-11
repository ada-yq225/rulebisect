"""Guided local configuration; suggestions never execute project commands."""
from __future__ import annotations

import ast
import heapq
import json
import os
import re
import shlex
import stat
import tomllib
from pathlib import Path

from .setup import CONFIG_NAME, _repository_file, discover_instructions, git_root, init_config
from .assertions import validate_assertions


_MANIFEST_LIMIT = 256 * 1024
_TEST_FILE_LIMIT = 64
_TEST_READ_LIMIT = 1024 * 1024
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


def _pytest_dependency(value) -> bool:
    """Match the dependency name, rather than plugins or prose mentioning it."""
    return isinstance(value, str) and bool(re.match(
        r'^\s*pytest(?=\s*(?:[<>=!~;\[@]|$))', value, flags=re.IGNORECASE))


def _pytest_manifest(manifest: dict | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    tool = manifest.get('tool')
    tool = tool if isinstance(tool, dict) else {}
    if isinstance(tool.get('pytest'), dict):
        return True
    project = manifest.get('project')
    project = project if isinstance(project, dict) else {}
    dependency_lists = [project.get('dependencies')]
    for groups in (project.get('optional-dependencies'), manifest.get('dependency-groups')):
        if isinstance(groups, dict):
            dependency_lists.extend(groups.values())
    pdm = tool.get('pdm')
    if isinstance(pdm, dict) and isinstance(pdm.get('dev-dependencies'), dict):
        dependency_lists.extend(pdm['dev-dependencies'].values())
    if any(isinstance(values, list) and any(_pytest_dependency(value) for value in values)
           for values in dependency_lists):
        return True
    poetry = tool.get('poetry')
    if isinstance(poetry, dict):
        dependencies = [poetry.get('dependencies'), poetry.get('dev-dependencies')]
        groups = poetry.get('group')
        if isinstance(groups, dict):
            dependencies.extend(group.get('dependencies') for group in groups.values()
                                if isinstance(group, dict))
        return any(isinstance(group, dict) and any(
            isinstance(name, str) and name.lower() == 'pytest'
            and isinstance(value, (str, dict)) for name, value in group.items())
            for group in dependencies)
    return False


def _test_framework_evidence(tree: ast.Module) -> tuple[bool, bool, bool]:
    """Recognize imports and collectable definitions without importing a module."""
    module_aliases = {}
    testcase_aliases = set()
    pytest_imported = False
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {'unittest', 'unittest.case'}:
                    module_aliases[alias.asname or 'unittest'] = alias.name if alias.asname else 'unittest'
                if alias.name == 'pytest' or alias.name.startswith('pytest.'):
                    pytest_imported = True
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module in {'unittest', 'unittest.case'}:
                testcase_aliases.update(alias.asname or alias.name for alias in node.names
                                        if alias.name == 'TestCase')
            if node.level == 0 and node.module and (node.module == 'pytest'
                                                    or node.module.startswith('pytest.')):
                pytest_imported = True

    def testcase_base(node):
        if isinstance(node, ast.Name):
            return node.id in testcase_aliases
        attributes = []
        while isinstance(node, ast.Attribute):
            attributes.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name) or node.id not in module_aliases:
            return False
        name = '.'.join([module_aliases[node.id], *reversed(attributes)])
        return name in {'unittest.TestCase', 'unittest.case.TestCase'}

    function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    pytest_functions = any(isinstance(node, function_types) and node.name.startswith('test_')
                           for node in tree.body)
    unittest_found = False
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        is_unittest = any(testcase_base(base) for base in node.bases)
        unittest_found = unittest_found or is_unittest
        if (is_unittest and any(isinstance(child, function_types) and child.name.startswith('test')
                                for child in node.body)) or (
                node.name.startswith('Test') and any(
                    isinstance(child, function_types) and child.name.startswith('test_')
                    for child in node.body)):
            pytest_functions = True
    return pytest_imported, pytest_functions, unittest_found


def _python_test_framework(repo: Path) -> str | None:
    """Sample direct tests/test*.py files within fixed read and file budgets."""
    tests = repo / 'tests'
    try:
        if tests.is_symlink() or not tests.is_dir():
            return None
        files = heapq.nsmallest(_TEST_FILE_LIMIT,
                               (path for path in tests.iterdir()
                                if path.name.startswith('test') and path.suffix == '.py'),
                               key=lambda path: path.name)
    except OSError:
        return None
    remaining = _TEST_READ_LIMIT
    pytest_imported = pytest_functions = unittest_found = False
    for path in files:
        if remaining <= 0:
            break
        try:
            if path.is_symlink() or not path.is_file():
                continue
            flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            with os.fdopen(os.open(path, flags), 'rb') as stream:
                metadata = os.fstat(stream.fileno())
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MANIFEST_LIMIT
                        or metadata.st_size > remaining):
                    continue
                source = stream.read(metadata.st_size)
                remaining -= len(source)
                if len(source) != metadata.st_size or path.is_symlink():
                    continue
            tree = ast.parse(source, filename=path.name)
        except (OSError, SyntaxError, ValueError, UnicodeError, RecursionError):
            continue
        imports, functions, unittest_case = _test_framework_evidence(tree)
        pytest_imported = pytest_imported or imports
        pytest_functions = pytest_functions or functions
        unittest_found = unittest_found or unittest_case
        if pytest_imported and pytest_functions:
            return 'pytest'
    return 'unittest' if unittest_found else None


def command_suggestions(repo: Path) -> list[dict[str, str]]:
    """Suggest commands from local manifests, without asserting they work.

    The order is stable for repositories containing multiple languages. A
    suggestion is a starting point: the user must select or replace it.
    """
    repo = Path(repo)
    suggestions = []
    try:
        pytest_configured = _pytest_manifest(_toml_manifest(repo / 'pyproject.toml'))
    except RecursionError:
        pytest_configured = False
    framework = 'pytest' if pytest_configured else _python_test_framework(repo)
    if framework == 'pytest':
        reason = ('pyproject.toml declares pytest configuration or dependencies.' if pytest_configured
                  else 'Local test files import pytest and define test functions.')
        suggestions.append({'label': 'Python pytest', 'command': 'python -m pytest',
                            'reason': reason + ' Confirm its test collection and dependencies.'})
    elif framework == 'unittest':
        suggestions.append({'label': 'Python unittest',
                            'command': 'python -m unittest discover -s tests',
                            'reason': 'Local test files define unittest.TestCase subclasses; confirm their test collection.'})
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


def run_wizard(repo: Path, input_fn=input, print_fn=print, *,
               instructions: list[str] | None = None) -> Path:
    """Collect task/check details, then create config and a verifier wrapper.

    Every answer is collected and validated before init_config writes files.
    EOF and Ctrl-C leave the repository untouched.
    Explicit instruction files replace automatic discovery and are validated
    before the first prompt, using the same path restrictions as initialization.
    """
    repo = git_root(Path(repo))
    config_path = repo / CONFIG_NAME
    if config_path.exists() or config_path.is_symlink():
        raise ValueError(f'{CONFIG_NAME} already exists; edit it rather than overwriting.')
    selected = discover_instructions(repo) if instructions is None else instructions
    if instructions is None and not selected:
        raise ValueError('No AGENTS.md found. Use init --wizard --instructions FILE to select an existing instruction/Skill file.')
    if not isinstance(selected, list) or not selected:
        raise ValueError('--instructions requires a non-empty list of repository-relative file paths')
    instructions = [_repository_file(repo, name, 'Instruction') for name in selected]
    if len(set(instructions)) != len(instructions):
        raise ValueError('Duplicate instruction files are unsupported')
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
