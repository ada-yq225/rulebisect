"""Read configuration with useful errors, without changing or executing it."""
from __future__ import annotations

import json
from pathlib import Path


MAX_CONFIGURATION_DEPTH = 128


def parse_configuration(path: Path, source: bytes) -> dict:
    """Parse the caller's original bytes, preserving them for suite CAS checks."""
    path = Path(path)
    try:
        text = source.decode('utf-8')
    except UnicodeDecodeError as error:
        raise ValueError(f'Configuration is not UTF-8: {path}. Save this JSON file as UTF-8 and retry.') from error
    try:
        config = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f'Invalid configuration JSON: {path}, line {error.lineno}, column {error.colno}: '
            f'{error.msg}. Fix the JSON syntax at this location and retry.'
        ) from error
    except RecursionError as error:
        raise ValueError(
            f'Configuration JSON is nested too deeply: {path}. Simplify nested settings and retry.'
        ) from error
    if not isinstance(config, dict):
        raise ValueError(f'Configuration must be a JSON object: {path}. Use an object with named settings, or create one with rulebisect init --wizard.')
    # Decoder thresholds vary by Python version. Bound valid nested input before
    # downstream copying/validation can overflow recursion, using an iterative
    # walk that never depends on the interpreter's recursion limit.
    stack = [(config, 1)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_CONFIGURATION_DEPTH:
            raise ValueError(
                f'Configuration JSON is nested too deeply: {path}. '
                f'Keep nesting within {MAX_CONFIGURATION_DEPTH} levels; simplify nested settings and retry.'
            )
        children = value.values() if isinstance(value, dict) else value
        stack.extend((child, depth + 1) for child in children if isinstance(child, (dict, list)))
    return config


def load_configuration(path: Path) -> dict:
    """Read an existing UTF-8 JSON object; all input failures become ValueError."""
    path = Path(path)
    if path.is_dir():
        raise ValueError(f'Configuration path is a directory: {path}. Select a JSON file with --config PATH.')
    try:
        source = path.read_bytes()
    except FileNotFoundError as error:
        raise ValueError(f'Configuration file not found: {path}. Check the selected path and choose an existing file with --config PATH. For first-time setup, run rulebisect init --wizard in your repository.') from error
    except IsADirectoryError as error:
        raise ValueError(f'Configuration path is a directory: {path}. Select a JSON file with --config PATH.') from error
    except OSError as error:
        raise ValueError(f'Cannot read configuration: {path}. Check file permissions and select a readable JSON file with --config PATH.') from error
    return parse_configuration(path, source)
