#!/usr/bin/env python3
"""Sync and package the offline RuleBisect skill, using an explicit file list.

Default: refresh the bundled engine. --check is read-only. --out creates a
deterministic portable plugin ZIP; --skill-only omits plugin-level metadata.
No dependency installation, credentials, configuration, or network is needed.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import zipfile


MODULES = (
    '__init__.py', '__main__.py', 'assertions.py', 'checks.py', 'cli.py',
    'comparison.py', 'core.py', 'demo.py', 'experiment.py', 'history.py',
    'onboarding.py', 'report.py', 'report_ui.py', 'runner.py', 'setup.py',
    'share.py', 'suite.py', 'ui.py',
)
PLUGIN = Path('plugins/rulebisect')
SKILL = Path('skills/rulebisect')
RUNTIME = SKILL / 'scripts/runtime'
LAUNCHER = SKILL / 'scripts/rulebisect_cli.py'
METADATA_FILES = (
    Path('plugin.json'), Path('assets/rulebisect.svg'), SKILL / 'SKILL.md',
    SKILL / 'agents/openai.yaml', LAUNCHER,
    SKILL / 'references/experiments.md', SKILL / 'references/assertions.md',
    SKILL / 'references/evidence.md',
)
VENDOR_FILES = (Path('LICENSE'), SKILL / 'LICENSE', RUNTIME / 'LICENSE',
                *(RUNTIME / 'rulebisect' / name for name in MODULES))
PACKAGE_FILES = tuple(sorted((*METADATA_FILES, *VENDOR_FILES), key=lambda path: path.as_posix()))
_EPOCH = (1980, 1, 1, 0, 0, 0)


def _plugin_directory(root: Path) -> Path:
    current = root
    for part in PLUGIN.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f'Plugin directory component must not be a symlink: {current}')
    return current


def _regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Required regular file is missing or symlinked: {path}')


def _audit_tree(directory: Path, *, complete: bool) -> None:
    """Reject unknown entries rather than silently including or deleting them."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f'Plugin directory is missing or symlinked: {directory}')
    files = set(PACKAGE_FILES)
    directories = {parent for path in files for parent in path.parents if parent != Path('.')}
    found = set()

    def visit(current: Path) -> None:
        for entry in sorted(current.iterdir()):
            relative = entry.relative_to(directory)
            if entry.is_symlink():
                raise ValueError(f'Plugin contains a symlink: {relative}')
            mode = entry.stat().st_mode
            if stat.S_ISDIR(mode):
                if relative not in directories:
                    raise ValueError(f'Plugin contains an unexpected directory: {relative}')
                visit(entry)
            elif stat.S_ISREG(mode):
                if relative not in files:
                    raise ValueError(f'Plugin contains an unexpected file: {relative}')
                found.add(relative)
            else:
                raise ValueError(f'Plugin contains a nonregular entry: {relative}')

    visit(directory)
    required = files if complete else set(METADATA_FILES)
    missing = required - found
    if missing:
        raise ValueError('Plugin files are missing: ' + ', '.join(str(path) for path in sorted(missing)))


def _source_payload(root: Path) -> dict[Path, bytes]:
    package = root / 'rulebisect'
    if package.is_symlink() or not package.is_dir():
        raise ValueError('Canonical rulebisect directory is missing or symlinked')
    modules = {path.name for path in package.iterdir() if path.suffix == '.py'}
    if modules != set(MODULES):
        raise ValueError('Canonical Python modules changed; update the explicit packaging allowlist')
    payload = {}
    for name in MODULES:
        path = package / name
        _regular(path)
        payload[RUNTIME / 'rulebisect' / name] = path.read_bytes()
    _regular(root / 'LICENSE')
    license_bytes = (root / 'LICENSE').read_bytes()
    payload[Path('LICENSE')] = license_bytes
    payload[SKILL / 'LICENSE'] = license_bytes
    payload[RUNTIME / 'LICENSE'] = license_bytes
    return payload


def _validate_metadata(directory: Path) -> None:
    try:
        metadata = json.loads((directory / 'plugin.json').read_text(encoding='utf-8'))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError(f'Invalid plugin.json: {error}') from error
    if not isinstance(metadata, dict) or metadata.get('name') != 'rulebisect':
        raise ValueError('plugin.json must describe the rulebisect plugin')
    if not all(isinstance(metadata.get(field), str) and metadata[field].strip()
               for field in ('version', 'description', 'license')):
        raise ValueError('plugin.json needs version, description, and license metadata')
    # The launcher and builder must agree on the complete engine. Read syntax;
    # never import package code while preparing a distribution.
    tree = ast.parse((directory / LAUNCHER).read_text(encoding='utf-8'))
    assignment = next((node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == 'RUNTIME_MODULES'
                               for target in node.targets)), None)
    if assignment is None or ast.literal_eval(assignment.value) != MODULES:
        raise ValueError('Launcher runtime allowlist differs from the builder')
    skill = (directory / SKILL / 'SKILL.md').read_text(encoding='utf-8')
    if not skill.startswith('---\n') or '\nname: rulebisect\n' not in skill:
        raise ValueError('SKILL.md needs rulebisect frontmatter metadata')


def check_package(root: Path) -> None:
    """Read-only verification of metadata, file boundaries, and vendor bytes."""
    root = Path(root).resolve()
    directory = _plugin_directory(root)
    _audit_tree(directory, complete=True)
    _validate_metadata(directory)
    for relative, expected in _source_payload(root).items():
        if (directory / relative).read_bytes() != expected:
            raise ValueError(f'Bundled file differs from canonical source: {relative}; run the builder to sync it')


def sync_runtime(root: Path) -> None:
    """Replace only the known runtime and license files; preserve skill metadata."""
    root = Path(root).resolve()
    directory = _plugin_directory(root)
    # Collect and validate everything before any write, including stale extras.
    _audit_tree(directory, complete=False)
    _validate_metadata(directory)
    payload = _source_payload(root)
    for relative, data in payload.items():
        target = directory / relative
        if target.exists() and target.read_bytes() == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='.rulebisect-build-', dir=target.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    check_package(root)


def _output_path(root: Path, output: Path) -> Path:
    requested = Path(output).expanduser().absolute()
    # Accept macOS's system aliases, but never follow a user-created output link.
    system_aliases = {Path('/tmp'): Path('/private/tmp'), Path('/var'): Path('/private/var')}
    for component in (requested, *requested.parents):
        if component.is_symlink() and system_aliases.get(component) != component.resolve():
            raise ValueError('Archive path or output directory must not be a symlink')
    output = requested.parent.resolve() / requested.name
    plugin = (root / PLUGIN).resolve()
    if output == plugin or plugin in output.parents:
        raise ValueError('Archive output must be outside the plugin source directory')
    if output.exists():
        raise ValueError(f'Archive already exists; choose a new path: {output}')
    return output


def build_archive(root: Path, output: Path, *, skill_only: bool = False) -> Path:
    """Create a reproducible archive exclusively, with no source checkout paths."""
    root = Path(root).resolve()
    output = _output_path(root, output)
    sync_runtime(root)
    directory = _plugin_directory(root)
    entries = {}
    for relative in PACKAGE_FILES:
        if skill_only:
            if relative == Path('LICENSE'):
                name = 'LICENSE'
            elif SKILL in relative.parents:
                name = relative.relative_to(SKILL).as_posix()
            else:
                continue
        else:
            name = relative.as_posix()
        entries[name] = (directory / relative).read_bytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with output.open('xb') as stream:
            created = True
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
                for name, data in sorted(entries.items()):
                    info = zipfile.ZipInfo(name, date_time=_EPOCH)
                    info.create_system = 3
                    executable = name.endswith('/rulebisect_cli.py') or name == 'scripts/rulebisect_cli.py'
                    info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
                    archive.writestr(info, data)
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1],
                        help='Source checkout (default: this script\'s repository)')
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument('--check', action='store_true', help='Read-only verification; do not sync')
    operation.add_argument('--out', type=Path, help='Create a new deterministic ZIP; never overwrite')
    parser.add_argument('--skill-only', action='store_true', help='Build a standalone skill ZIP instead of a plugin')
    args = parser.parse_args(argv)
    if args.skill_only and not args.out:
        parser.error('--skill-only requires --out')
    try:
        if args.check:
            check_package(args.root)
            print('RuleBisect skill package matches canonical source; no files changed.')
        elif args.out:
            print(f'Created {build_archive(args.root, args.out, skill_only=args.skill_only)}')
        else:
            sync_runtime(args.root)
            print('RuleBisect bundled runtime and MIT license are up to date.')
    except (OSError, ValueError, SyntaxError, UnicodeError) as error:
        print(f'Cannot build RuleBisect skill: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
