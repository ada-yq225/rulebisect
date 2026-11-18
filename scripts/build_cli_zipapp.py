#!/usr/bin/env python3
"""Package the canonical CLI in a self-contained, reproducible Python .pyz."""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import stat
import sys
import zipfile

from build_skill_plugin import MODULES, _output_path, _regular


ENTRYPOINT = b"""import sys

if sys.version_info < (3, 11):
    sys.exit("RuleBisect requires Python 3.11 or newer.")

from rulebisect.cli import main

raise SystemExit(main())
"""


def build_zipapp(root: Path, output: Path) -> Path:
    root = root.resolve()
    package = root / 'rulebisect'
    if package.is_symlink() or not package.is_dir():
        raise ValueError(f'Missing or symlinked canonical package: {package}')
    output = _output_path(root, output)
    if output.suffix.lower() != '.pyz':
        raise ValueError('Choose a new output file ending in .pyz')
    if output.is_relative_to(package) or output.is_relative_to(root / '.git'):
        raise ValueError('Choose an output outside the engine and Git directories')

    # Build in memory so a failed source read never leaves a partial download.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        entries = {'__main__.py': ENTRYPOINT}
        for relative in ('LICENSE', *('rulebisect/' + name for name in MODULES)):
            source = root / relative
            _regular(source)
            entries[relative] = source.read_bytes()
        for name, data in sorted(entries.items()):
            # ZIP_STORED and fixed metadata keep bytes independent of zlib and time.
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)

    output.parent.mkdir(parents=True, exist_ok=True)
    stream = output.open('xb')
    try:
        with stream:
            stream.write(buffer.getbuffer())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1],
                        help='Source checkout (defaults to this script\'s repository)')
    parser.add_argument('--out', type=Path, required=True, help='New .pyz output file')
    args = parser.parse_args(argv)
    try:
        result = build_zipapp(args.root, args.out)
    except (OSError, ValueError) as error:
        print(f'Cannot build RuleBisect CLI: {error}', file=sys.stderr)
        return 2
    print(f'Created {result}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
