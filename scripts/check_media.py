#!/usr/bin/env python3
"""Decode and validate repository GIF demos; Pillow is a development dependency."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys


MAX_BYTES = 3_000_000
MIN_FRAME_MS = 20
MAX_FRAME_MS = 10_000
MAX_TOTAL_MS = 120_000


@dataclass(frozen=True)
class GifStats:
    width: int
    height: int
    frames: int
    size_bytes: int
    duration_ms: int


def parse_size(value: str) -> tuple[int, int]:
    if not re.fullmatch(r'[1-9][0-9]*x[1-9][0-9]*', value):
        raise argparse.ArgumentTypeError('Expected positive canvas dimensions, for example 1200x720')
    width, height = value.split('x')
    try:
        return int(width), int(height)
    except ValueError as error:
        raise argparse.ArgumentTypeError('Canvas dimensions are too large') from error


def check_gif(path: Path, image_module, expected_size: tuple[int, int] | None = None) -> GifStats:
    """Load every frame, retaining only current-frame image data and scalar stats."""
    size_bytes = path.stat().st_size
    if size_bytes >= MAX_BYTES:
        raise ValueError(f'file is {size_bytes:,} bytes; keep each GIF below {MAX_BYTES:,} bytes (3 MB)')
    with image_module.open(path) as image:
        if image.format != 'GIF':
            raise ValueError('file contents are not GIF data')
        canvas = image.size
        if any(type(dimension) is not int or dimension < 1 for dimension in canvas):
            raise ValueError('GIF canvas must have positive dimensions')
        if expected_size is not None and canvas != expected_size:
            raise ValueError(f'canvas is {canvas[0]}x{canvas[1]}; expected {expected_size[0]}x{expected_size[1]}')
        if image.info.get('loop') != 0:
            raise ValueError('GIF must loop indefinitely (loop=0)')
        frames = getattr(image, 'n_frames', 1)
        if frames <= 1:
            raise ValueError('GIF must contain more than one frame')
        duration_ms = 0
        for index in range(frames):
            image.seek(index)
            image.load()  # Force decoding; metadata-only verification misses damaged frame data.
            if image.size != canvas:
                raise ValueError(f'frame {index + 1} changes the canvas dimensions')
            duration = image.info.get('duration')
            if type(duration) is not int or not MIN_FRAME_MS <= duration <= MAX_FRAME_MS:
                raise ValueError(f'frame {index + 1} needs a duration of {MIN_FRAME_MS}–{MAX_FRAME_MS} ms')
            duration_ms += duration
            if duration_ms > MAX_TOTAL_MS:
                raise ValueError(f'one animation cycle exceeds {MAX_TOTAL_MS / 1000:.0f} seconds; shorten the pacing')
    return GifStats(canvas[0], canvas[1], frames, size_bytes, duration_ms)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate and fully decode offline GIF workflow demos. No model calls.')
    parser.add_argument('gifs', nargs='+', type=Path, help='One or more generated GIF files')
    parser.add_argument('--size', type=parse_size, metavar='WIDTHxHEIGHT', help='Require an exact canvas size for every GIF')
    args = parser.parse_args(argv)
    try:
        from PIL import Image
    except ImportError:
        print('check_media: Pillow is an optional development dependency. Install it with: python -m pip install Pillow', file=sys.stderr)
        return 2
    failures = 0
    for path in args.gifs:
        try:
            stats = check_gif(path, Image, args.size)
        except (OSError, EOFError, ValueError, Image.DecompressionBombError) as error:
            print(f'FAIL {path}: {error}', file=sys.stderr)
            failures += 1
            continue
        print(f'OK {path}: {stats.width}x{stats.height} · {stats.frames} frames · '
              f'{stats.size_bytes:,} bytes · {stats.duration_ms / 1000:.2f}s/cycle · loop=0')
    if failures:
        print(f'{failures}/{len(args.gifs)} GIFs failed validation.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
