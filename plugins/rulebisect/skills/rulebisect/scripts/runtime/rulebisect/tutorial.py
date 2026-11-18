"""Create an editable two-case Git project for the instruction review tutorial."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

from .setup import CONFIG_NAME


_BASELINE = """# Label conventions

Lowercase all labels. Preserve the original whitespace for every client.
"""

_PROPOSAL = """# Label conventions

Lowercase all labels. Strip surrounding whitespace for every client.
"""

_TASK = ('Implement normalize_label(value, client) in labels.py according to the '
         'repository label conventions. Both modern and legacy clients use this function.')

_SOURCE = '''def normalize_label(value: str, client: str) -> str:
    """Normalize a label for the named client."""
    return value.lower()
'''


def _verifier(client, expected):
    # A frozen oracle runs outside the workspace. Load the actual implementation
    # by path from its working directory, so it also works after distribution.
    return f'''from pathlib import Path
import runpy
import sys

try:
    normalize = runpy.run_path(str(Path.cwd() / "labels.py"))["normalize_label"]
    actual = normalize("  MiXeD  ", {client!r})
except Exception as error:
    print("Could not exercise labels.py:", error)
    sys.exit(2)
expected = {expected!r}
if actual != expected:
    print(f"Expected {{expected!r}}, got {{actual!r}} for the {client} client.")
    sys.exit(1)
print("Passed: {client} label contract")
'''


def create_tutorial(destination: Path) -> Path:
    """Create the baseline commit and working proposal in a strictly new directory."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f'Tutorial destination already exists: {destination}. Choose a new directory.')
    if not destination.parent.is_dir():
        raise ValueError(f'Tutorial parent directory does not exist: {destination.parent}')
    destination = destination.parent.resolve() / destination.name
    if any(part.casefold() == '.git' for part in destination.parts):
        raise ValueError('Choose a tutorial directory outside Git metadata.')

    config = {'task': _TASK, 'instructions': ['AGENTS.md'], 'oracle': 'verify_modern.py',
              'verify': ['{python}', '{oracle}'], 'protected_files': ['verify_modern.py', 'verify_legacy.py'],
              'repeats': 2, 'max_runs': 8, 'cases': [
                  {'id': 'modern'}, {'id': 'legacy', 'oracle': 'verify_legacy.py'}]}
    files = {'AGENTS.md': _BASELINE, 'labels.py': _SOURCE,
             'verify_modern.py': _verifier('modern', 'mixed'),
             'verify_legacy.py': _verifier('legacy', '  mixed  '),
             CONFIG_NAME: json.dumps(config, ensure_ascii=False, indent=2) + '\n',
             '.gitattributes': '* text eol=lf\n', '.gitignore': '__pycache__/\n*.pyc\n'}
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM='1',
               GIT_TERMINAL_PROMPT='0')

    with tempfile.TemporaryDirectory(prefix='.rulebisect-tutorial-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        repo, empty = stage / 'project', stage / 'empty'
        repo.mkdir()
        empty.mkdir()
        for name, source in files.items():
            (repo / name).write_text(source, encoding='utf-8', newline='\n')
        git = ['git', '-c', 'user.name=RuleBisect Tutorial', '-c', 'user.email=tutorial@example.invalid',
               '-c', 'commit.gpgSign=false', '-c', f'core.hooksPath={empty}',
               '-c', 'core.fsmonitor=false', '-c', f'core.attributesFile={os.devnull}',
               '-c', f'core.excludesFile={os.devnull}', '-c', 'init.defaultBranch=main']
        for arguments in (['init', '-q', f'--template={empty}'], ['add', '-f', '--', *files],
                          ['commit', '-q', '-m', 'Baseline label conventions']):
            result = subprocess.run([*git, *arguments], cwd=repo, env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, errors='replace', timeout=30)
            if result.returncode:
                raise ValueError(f'Could not create tutorial Git baseline: {result.stderr.strip()}')
        (repo / 'AGENTS.md').write_text(_PROPOSAL, encoding='utf-8', newline='\n')

        # mkdir exclusively reserves the name on every platform. A simultaneous
        # tutorial cannot replace an empty directory created by another caller.
        try:
            destination.mkdir()
        except FileExistsError as error:
            raise ValueError(f'Tutorial destination already exists: {destination}. Choose a new directory.') from error
        published = []
        try:
            for name in (*files, '.git'):
                (repo / name).rename(destination / name)
                published.append(name)
        except BaseException:
            for name in reversed(published):
                (destination / name).rename(repo / name)
            if not any(destination.iterdir()):
                destination.rmdir()
            raise
    return destination
