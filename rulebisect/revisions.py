"""Read selected instruction blobs from one immutable, local Git commit."""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import re
import subprocess


def read_revision(repo: Path, ref: str, instructions: list[str]) -> tuple[dict, dict[str, bytes]]:
    """Resolve a revision once and read its regular instruction files by blob ID."""
    if (not isinstance(ref, str) or not re.fullmatch(
            r'(?:@|[\w.+-]+(?:/[\w.+-]+)*)(?:[~^][0-9]*)*', ref)
            or ref.startswith('-') or '..' in ref
            or any(part.startswith('.') for part in ref.split('/'))):
        raise ValueError(f'Invalid Git revision {ref!r}. Use a branch, tag, commit ID or HEAD~1.')

    if not isinstance(instructions, list) or not instructions:
        raise ValueError('Select at least one repository-relative instruction file.')
    paths = []
    for name in instructions:
        if not isinstance(name, str) or not name or '\x00' in name:
            raise ValueError('Instruction paths must be nonempty strings.')
        path = Path(name)
        if (path.is_absolute() or PureWindowsPath(name).anchor or not path.parts
                or '..' in path.parts or any(part.casefold() == '.git' for part in path.parts)):
            raise ValueError(f'Expected a repository-relative instruction path: {name!r}')
        paths.append(path.as_posix())
    if len(set(paths)) != len(paths):
        raise ValueError('Duplicate instruction paths are unsupported.')

    env = os.environ.copy()
    for variable in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY',
                     'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_INDEX_FILE', 'GIT_SHALLOW_FILE'):
        env.pop(variable, None)
    # Disallow all transports as a fallback on Git versions without lazy-fetch control.
    env.update(GIT_NO_LAZY_FETCH='1', GIT_ALLOW_PROTOCOL='', GIT_NO_REPLACE_OBJECTS='1',
               GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')

    def git(args: list[str], failure: str) -> bytes:
        try:
            result = subprocess.run(['git', '--literal-pathspecs', *args], cwd=repo,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=env, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError(f'{failure}: {error}') from error
        if result.returncode:
            raise ValueError(failure)
        return result.stdout

    commit = git(['rev-parse', '--verify', '--end-of-options', ref + '^{commit}'],
                 f'Cannot resolve Git revision {ref!r} to a local commit.').strip().decode('ascii')
    if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', commit):
        raise ValueError(f'Invalid commit ID returned for Git revision {ref!r}.')

    blobs = {}
    for name in paths:
        entry = git(['ls-tree', '-z', '--full-tree', commit, '--', name],
                    f'Cannot inspect {name!r} at {commit}. Its Git objects must be available locally.')
        if not entry:
            raise ValueError(f'Instruction file {name!r} is missing at {commit}. Select a revision containing this path.')
        header, _, recorded_path = entry.removesuffix(b'\0').partition(b'\t')
        fields = header.split()
        if (recorded_path != name.encode('utf-8') or len(fields) != 3
                or fields[0] not in (b'100644', b'100755') or fields[1] != b'blob'):
            raise ValueError(f'Instruction {name!r} at {commit} must be a regular file.')
        data = git(['cat-file', 'blob', fields[2].decode('ascii')],
                   f'Cannot read instruction {name!r} at {commit}. Its blob must be available locally.')
        try:
            data.decode('utf-8')
        except UnicodeDecodeError as error:
            raise ValueError(f'Instruction {name!r} at {commit} must be UTF-8 text.') from error
        blobs[name] = data

    return {'kind': 'git', 'ref': ref, 'commit': commit}, blobs
