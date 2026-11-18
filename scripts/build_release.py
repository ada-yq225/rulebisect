#!/usr/bin/env python3
"""Build the four public downloads and their SHA-256 manifest in a new directory."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path, help='A new directory outside the checkout')
    output = parser.parse_args().out.absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT):
        parser.error('Choose a new output directory outside the source checkout.')
    if not output.parent.is_dir():
        parser.error('The parent directory must already exist.')
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    plugin = json.loads((ROOT / 'plugins/rulebisect/plugin.json').read_text(encoding='utf-8'))
    engine_version, skill_version = project['version'], plugin['version']
    wheel = f'rulebisect-{engine_version}-py3-none-any.whl'

    def run(*args, **kwargs):
        return subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, check=True, **kwargs)

    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        packages = Path(staging) / 'packages'
        packages.mkdir()
        run('scripts/build_skill_plugin.py', '--check')
        run('-m', 'pip', 'wheel', '--no-index', '--no-deps', '--no-build-isolation', '.', '--wheel-dir', packages)
        run('scripts/build_cli_zipapp.py', '--out', packages / 'rulebisect.pyz')
        for flavor, flags in [('skill', ['--skill-only']), ('plugin', [])]:
            run('scripts/build_skill_plugin.py', *flags, '--out', packages / f'rulebisect-{flavor}-{skill_version}.zip')
        version = run('-I', packages / 'rulebisect.pyz', '--version', capture_output=True, text=True).stdout.strip()
        if version != engine_version or not (packages / wheel).is_file():
            raise ValueError('Engine version and distribution metadata disagree.')
        sums = []
        for path in sorted(packages.iterdir()):
            with ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise ValueError(f'Invalid archive: {path.name}')
            sums.append(f'{sha256(path.read_bytes()).hexdigest()}  {path.name}')
        (packages / 'SHA256SUMS').write_text('\n'.join(sums) + '\n', encoding='ascii', newline='\n')
        packages.rename(output)
    print(f'Delivery files: {output}')


if __name__ == '__main__':
    main()
