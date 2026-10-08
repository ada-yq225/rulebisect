"""Local setup helpers; no model calls."""
from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


CONFIG_NAME = '.rulebisect.json'


def git_root(path: Path) -> Path:
    result = subprocess.run(['git', '-c', 'core.fsmonitor=false', 'rev-parse', '--show-toplevel'],
                            cwd=path, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise ValueError('Not inside a Git repository. Run git init and git add for the fixture first.')
    return Path(result.stdout.strip()).resolve()


def tracked_files(repo: Path) -> list[str]:
    result = subprocess.run(['git', '-c', 'core.fsmonitor=false', 'ls-files', '-z'], cwd=repo,
                            capture_output=True, timeout=10, check=True)
    return [name for name in result.stdout.decode().split('\0') if name]


def discover_instructions(repo: Path) -> list[str]:
    names = set(tracked_files(repo))
    names.update(name for name in ['AGENTS.md', 'AGENTS.override.md'] if (repo / name).is_file())
    candidates = {name for name in names if Path(name).name in ('AGENTS.md', 'AGENTS.override.md')
                  and (repo / name).is_file() and not (repo / name).is_symlink()}
    return sorted(name for name in candidates if Path(name).name == 'AGENTS.override.md'
                  or str(Path(name).with_name('AGENTS.override.md')) not in candidates)


def _repository_file(repo: Path, name: str, label: str) -> str:
    """Match experiment path restrictions before initialization creates any files."""
    if not isinstance(name, str) or not name:
        raise ValueError(f'{label} requires a nonempty repository-relative file path')
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts or any(part.casefold() == '.git' for part in relative.parts):
        raise ValueError(f'{label} must be an existing repository-relative file: {name}')
    target = repo / relative
    if any((repo / Path(*relative.parts[:index])).is_symlink()
           for index in range(1, len(relative.parts) + 1)):
        raise ValueError(f'{label} files and their parent directories must not be symlinks: {name}')
    if not target.is_file() or not target.resolve().is_relative_to(repo):
        raise ValueError(f'{label} file is missing or outside the repository: {name}')
    return relative.as_posix()


def init_config(repo: Path, task: str, check: str | None, model: str | None,
                oracle: str | None = None, instructions: list[str] | None = None, setup: str | None = None,
                assertions: list[dict] | None = None) -> Path:
    repo = repo.resolve()
    path = repo / CONFIG_NAME
    if path.exists() or path.is_symlink():
        raise ValueError(f'{CONFIG_NAME} already exists; edit it rather than overwriting.')
    if not isinstance(task, str) or not task.strip():
        raise ValueError('Provide a concrete --task.')
    if sum(value is not None for value in (check, oracle, assertions)) != 1:
        raise ValueError('Choose exactly one of --check, --oracle or --assertions.')
    setup_argv = shlex.split(setup) if setup is not None else []
    if setup is not None and (not setup_argv or any(v in ('&&', '||', ';', '|', '>', '>>', '<') for v in setup_argv)):
        raise ValueError('--setup requires a command without shell operators; use a script for multiple steps.')
    if setup_argv and setup_argv[0] in ('python', 'python3'):
        setup_argv[0] = '{python}'
    selected = instructions if instructions is not None else discover_instructions(repo)
    if not isinstance(selected, list) or not selected:
        raise ValueError('No AGENTS.md found. Use --instructions to select an existing instruction/Skill file.')
    selected = [_repository_file(repo, name, 'Instruction') for name in selected]
    if len(set(selected)) != len(selected):
        raise ValueError('Duplicate instruction files are unsupported')
    names = tracked_files(repo)
    protected = [name for name in names if (Path(name).name.startswith(('test_', 'test.'))
                  or Path(name).name.endswith(('_test.py', '.test.ts', '.test.js', '.spec.ts', '.spec.js')))
                 and name not in selected and (repo / name).is_file()]
    source = None
    if oracle is None:
        oracle = '.rulebisect-verify.py'
        oracle_path = repo / oracle
        if oracle_path.exists() or oracle_path.is_symlink():
            raise ValueError(f'{oracle} already exists; use --oracle or rename it.')
        if assertions is not None:
            from .assertions import build_oracle
            source = build_oracle(assertions)
        else:
            argv = shlex.split(check)
            if not argv:
                raise ValueError('--check must be a command, not empty text.')
            if any(value in ('&&', '||', ';', '|', '>', '>>', '<') for value in argv):
                raise ValueError('Shell operators are unsupported. Use --oracle for multiple checks.')
            source = '''# Generated by RuleBisect. Runs your trusted check without a shell.
import subprocess
import sys
COMMAND = CHECK_ARGUMENTS
if COMMAND[0] in ('python', 'python3'):
    COMMAND[0] = sys.executable
try:
    result = subprocess.run(COMMAND)
except OSError as error:
    print('Verifier setup error:', error, file=sys.stderr)
    sys.exit(2)
# Exit 1 is a behavioral failure; other codes are infrastructure errors.
sys.exit(result.returncode if result.returncode in (0, 1) else 2)
'''.replace('CHECK_ARGUMENTS', repr(argv))
    else:
        oracle = _repository_file(repo, oracle, '--oracle')
    if oracle in selected:
        raise ValueError('The oracle cannot also be an instruction file.')
    config = {'task': task, 'instructions': selected, 'oracle': oracle,
              'verify': ['{python}', '{oracle}'], 'protected_files': sorted(set(protected + [oracle])),
              'repeats': 3, 'max_runs': 60, 'timeout': 300, 'unit_mode': 'paragraph'}
    if setup_argv:
        config['setup'] = setup_argv
    if model:
        config['model'] = model
    encoded = json.dumps(config, ensure_ascii=False, indent=2) + '\n'
    created = []
    try:
        if source is not None:
            with oracle_path.open('x', encoding='utf-8', newline='\n') as stream:
                created.append(oracle_path)
                stream.write(source)
        # Exclusive creation protects files added while the prompts/validation ran.
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            created.append(path)
            stream.write(encoded)
    except BaseException:
        for created_path in reversed(created):
            created_path.unlink(missing_ok=True)
        raise
    return path


def validate_configuration(repo: Path, config_path: Path, proposed: Path | None = None) -> dict:
    """Reuse experiment validation without executing setup, verifier, or model commands."""
    from .comparison import Comparison, suite_cases
    from .experiment import Experiment

    config = json.loads(config_path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('Config must be a JSON object')
    out = repo.parent / f'rulebisect-preflight-{uuid.uuid4().hex}'
    settings = (config.get('model'), config.get('repeats', 3),
                config.get('max_runs', 60), config.get('timeout', 300))
    if proposed is not None:
        comparison = Comparison(repo, config, out, *settings, proposed,
                                max_tokens=config.get('max_tokens'))
        scope = comparison.prepare(check_codex=False)
    else:
        cases = suite_cases(config)
        for name, case in cases:
            experiment = Experiment(repo, case, out, *settings,
                                    max_tokens=config.get('max_tokens'))
            try:
                experiment.prepare(materialize=False, check_codex=False)
            except (ValueError, OSError) as error:
                raise ValueError(f'Case {name}: {error}') from error
        scope = {'instruction_files': experiment.instruction_paths, 'units': len(experiment.rules),
                 'snapshot_files': len(experiment.blobs), 'cases': [name for name, _ in cases],
                 'comparison_calls': len(cases) * 2 * experiment.repeats,
                 'max_runs': experiment.max_runs, 'model_calls': 0}
    return scope


def doctor(repo: Path, *, offline: bool = False, config_path: Path | None = None,
           proposed: Path | None = None) -> dict:
    checks, warnings, scope = [], [], None
    def add(name, ok, detail):
        checks.append({'name': name, 'ok': ok, 'detail': detail})
    add('Python', sys.version_info >= (3, 11), sys.version.split()[0])
    add('Git executable', shutil.which('git') is not None, shutil.which('git') or 'Install Git')
    try:
        root = git_root(repo)
        add('Git repository', True, str(root))
        config = config_path or root / CONFIG_NAME
        add('Experiment config', config.is_file(), str(config) if config.is_file() else 'Run rulebisect init')
        if config.is_file():
            try:
                scope = validate_configuration(root, config, proposed)
                add('Experiment inputs', True, 'Snapshot, instruction files, verifier roles and budgets validated')
                configured = json.loads(config.read_text(encoding='utf-8'))
                if not configured.get('model'):
                    warnings.append('No saved model; choose --model MODEL when running.')
                if proposed is None and scope['comparison_calls'] > scope['max_runs']:
                    warnings.append(f"Comparison needs {scope['comparison_calls']} calls; saved max_runs is {scope['max_runs']}. Increase it before compare.")
                if scope.get('setup') or configured.get('setup'):
                    warnings.append('Setup was validated but not executed; use rulebisect check to test the environment.')
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                add('Experiment inputs', False, str(error))
        else:
            files = discover_instructions(root)
            add('Instruction files', bool(files), ', '.join(files) or 'None found; select files with init --instructions')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        add('Git repository', False, str(error))
    if not offline:
        if not shutil.which('codex'):
            add('Codex executable', False, 'Install the Codex CLI, or use doctor --offline to check only repository inputs')
        else:
            try:
                version = subprocess.run(['codex', '--version'], capture_output=True, text=True, timeout=10, check=True)
                add('Codex version', True, version.stdout.strip())
                help_text = subprocess.run(['codex', 'exec', '--help'], capture_output=True, text=True, timeout=10, check=True).stdout
                missing = [flag for flag in ['--json', '--ephemeral', '--ignore-user-config'] if flag not in help_text]
                add('Codex flags', not missing, 'Supported' if not missing else 'Update Codex; missing ' + ', '.join(missing))
                auth = subprocess.run(['codex', 'login', 'status'], capture_output=True, timeout=10)
                # Never print authentication output, which may include an API-key hint.
                add('Codex authentication', auth.returncode == 0, 'Logged in' if auth.returncode == 0 else 'Run codex login')
            except (OSError, subprocess.SubprocessError) as error:
                add('Codex check', False, str(error))
    return {'ok': all(c['ok'] for c in checks), 'checks': checks, 'warnings': warnings,
            'scope': scope, 'offline': offline, 'model_calls': 0,
            'executed_setup': False, 'executed_verifier': False}


def draft_instructions(repo: Path, out: Path) -> Path:
    """Create an editable instruction copy without changing the experiment baseline."""
    repo, out = repo.resolve(), out.resolve()
    if out.is_relative_to(repo) or (out.exists() and any(out.iterdir())):
        raise ValueError('Draft output must be an empty directory outside the repository')
    path = repo / CONFIG_NAME
    if path.is_file():
        config = json.loads(path.read_text(encoding='utf-8'))
        selected = config.get('instructions') if isinstance(config, dict) else None
    else:
        selected = discover_instructions(repo)
    if not isinstance(selected, list) or not selected or any(not isinstance(name, str) or not name for name in selected):
        raise ValueError('Select instruction files with init first')
    files = {}
    for name in selected:
        relative = Path(name)
        target = repo / relative
        if relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts or any((repo / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)) or not target.is_file():
            raise ValueError(f'Instruction file missing, unsafe or symlinked: {name}')
        files[name] = (target.read_bytes(), target.stat().st_mode & 0o777)
    for name, (content, mode) in files.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(mode | 0o200)  # The draft stays editable even if source instructions are read-only.
    return out
