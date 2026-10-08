#!/usr/bin/env python3
"""Launch only this skill's bundled RuleBisect engine, without installation."""
from __future__ import annotations

import os
import sys


def _windows_argument(value: str) -> str:
    """Quote one argv value for Windows CRT without importing bootstrap helpers."""
    result = ['"']
    backslashes = 0
    for character in value:
        if character == '\\':
            backslashes += 1
            continue
        if character == '"':
            result.append('\\' * (2 * backslashes + 1))
        else:
            result.append('\\' * backslashes)
        result.append(character)
        backslashes = 0
    # Backslashes preceding the closing quote must also be escaped. Always
    # quoting preserves empty values, spaces, quotes and terminal backslashes.
    result.append('\\' * (2 * backslashes))
    result.append('"')
    return ''.join(result)


if __name__ == '__main__' and (not sys.flags.isolated or not sys.flags.utf8_mode):
    if sys.version_info < (3, 11):
        print('RuleBisect requires Python 3.11 or newer.', file=sys.stderr)
        raise SystemExit(2)
    # Ignore PYTHONPATH, the current directory and user site packages before
    # importing any engine modules. Use UTF-8 for bilingual redirected output
    # even when Windows or the parent environment selects an ASCII code page.
    # Preserve the user's arguments and cwd.
    try:
        arguments = [sys.executable, '-I', '-X', 'utf8', os.path.abspath(__file__), *sys.argv[1:]]
        if os.name == 'nt':
            # Windows execv can detach the child and loses CRT argument quoting.
            # Wait explicitly and return the isolated child's actual exit code.
            status = os.spawnv(os.P_WAIT, sys.executable,
                               [_windows_argument(value) for value in arguments])
            raise SystemExit(status)
        os.execv(sys.executable, arguments)
    except OSError as error:
        print(f'Cannot start isolated RuleBisect Python: {error}', file=sys.stderr)
        raise SystemExit(2)

from pathlib import Path


RUNTIME_MODULES = (
    '__init__.py', '__main__.py', 'assertions.py', 'checks.py', 'cli.py',
    'comparison.py', 'core.py', 'demo.py', 'experiment.py', 'history.py',
    'onboarding.py', 'report.py', 'report_ui.py', 'runner.py', 'setup.py',
    'share.py', 'suite.py', 'ui.py',
)


def bundled_runtime() -> Path:
    entrypoint = Path(__file__)
    if entrypoint.is_symlink() or entrypoint.parent.is_symlink():
        raise ValueError('Skill scripts must not be symlinks')
    scripts = entrypoint.parent.resolve()
    runtime = scripts / 'runtime'
    package = runtime / 'rulebisect'
    if runtime.is_symlink() or package.is_symlink() or not package.is_dir():
        raise ValueError('Bundled RuleBisect runtime is missing or symlinked; reinstall the complete skill')
    names = set()
    for child in package.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError('Bundled RuleBisect runtime contains an unsupported entry')
        names.add(child.name)
    if names != set(RUNTIME_MODULES):
        raise ValueError('Bundled RuleBisect runtime is incomplete or contains extra files; reinstall the complete skill')
    license_path = runtime / 'LICENSE'
    if license_path.is_symlink() or not license_path.is_file():
        raise ValueError('Bundled RuleBisect license is missing or symlinked; reinstall the complete skill')
    if any(child.is_symlink() or child.name not in ('rulebisect', 'LICENSE') for child in runtime.iterdir()):
        raise ValueError('Bundled RuleBisect runtime contains an unsupported entry')
    return runtime


def main(argv=None) -> int:
    if sys.version_info < (3, 11):
        print('RuleBisect requires Python 3.11 or newer.', file=sys.stderr)
        return 2
    try:
        runtime = bundled_runtime()
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(runtime))
        import rulebisect
        if Path(rulebisect.__file__).resolve() != runtime / 'rulebisect' / '__init__.py':
            raise ValueError('A different RuleBisect engine is already loaded; launch this script in a fresh Python process')
        from rulebisect.cli import main as engine_main
    except (ImportError, OSError, ValueError) as error:
        print(f'rulebisect skill: {error}', file=sys.stderr)
        return 2
    return engine_main(sys.argv[1:] if argv is None else argv)


if __name__ == '__main__':
    raise SystemExit(main())
