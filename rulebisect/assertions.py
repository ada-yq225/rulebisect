"""Deterministic output checks and portable, dependency-free oracle generation."""
from __future__ import annotations

import copy
import inspect
import json
import math
import os
import re
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath


MAX_OUTPUT_BYTES = 2 * 1024 * 1024
_FIELDS = {
    'file_exists': {'type', 'path'},
    'file_absent': {'type', 'path'},
    'file_contains': {'type', 'path', 'text'},
    'file_not_contains': {'type', 'path', 'text'},
    'file_matches': {'type', 'path', 'pattern'},
    'json_equals': {'type', 'path', 'pointer', 'value'},
}


def _validate_path(value: object) -> str:
    if not isinstance(value, str) or not value or not value.strip():
        raise ValueError('Assertion path must be a nonempty repository-relative path')
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise ValueError('Assertion path must contain valid Unicode') from error
    parts = value.split('/')
    if (PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive
            or '\\' in value or ':' in value or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(part in ('', '.', '..') or part.casefold() == '.git' for part in parts)):
        raise ValueError('Assertion paths must be relative, use /, and exclude .. and .git')
    return value


def _validate_json(value: object) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
    elif isinstance(value, list):
        for item in value:
            _validate_json(item)
        return
    elif isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_json(item)
        return
    raise ValueError('Assertion values must be JSON values with finite numbers')


def _pointer_tokens(pointer: str) -> list[str]:
    if pointer == '':
        return []
    if not pointer.startswith('/') or re.search(r'~(?![01])', pointer):
        raise ValueError('JSON pointer must be empty or an RFC 6901 pointer beginning with /')
    return [part.replace('~1', '/').replace('~0', '~') for part in pointer[1:].split('/')]


def validate_assertions(spec: object) -> list[dict]:
    """Validate a nonempty strict JSON assertion list and return an independent copy."""
    if not isinstance(spec, list) or not spec:
        raise ValueError('assertions must be a nonempty list')
    for index, check in enumerate(spec, 1):
        if not isinstance(check, dict):
            raise ValueError(f'Assertion {index} must be an object')
        kind = check.get('type')
        if not isinstance(kind, str) or kind not in _FIELDS:
            raise ValueError(f'Assertion {index} has an unsupported type')
        if set(check) != _FIELDS[kind]:
            fields = ', '.join(sorted(_FIELDS[kind]))
            raise ValueError(f'Assertion {index} ({kind}) requires exactly these fields: {fields}')
        _validate_path(check['path'])
        field = 'text' if kind in ('file_contains', 'file_not_contains') else 'pattern' if kind == 'file_matches' else None
        if field and (not isinstance(check[field], str) or not check[field]):
            raise ValueError(f'Assertion {index} requires a nonempty {field} string')
        if kind == 'file_matches':
            try:
                re.compile(check['pattern'])
            except (re.error, OverflowError, RecursionError) as error:
                raise ValueError(f'Assertion {index} has an invalid regular expression: {error}') from error
        if kind == 'json_equals':
            if not isinstance(check['pointer'], str):
                raise ValueError(f'Assertion {index} requires a JSON pointer string')
            _pointer_tokens(check['pointer'])
            try:
                _validate_json(check['value'])
            except RecursionError as error:
                raise ValueError(f'Assertion {index} JSON value is nested too deeply') from error
    try:
        return copy.deepcopy(spec)
    except RecursionError as error:
        raise ValueError('Assertion JSON values are nested too deeply') from error


def _output_file(root: Path, relative: str) -> tuple[Path, os.stat_result | None]:
    """Inspect components before reading; absent ancestors mean an absent output."""
    path = root
    try:
        root_info = root.lstat()
    except OSError as error:
        raise OSError('Output root cannot be inspected') from error
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise OSError('Output root must be a real directory')
    parts = relative.split('/')
    for index, part in enumerate(parts):
        path = path / part
        try:
            info = path.lstat()
        except FileNotFoundError:
            return path, None
        if stat.S_ISLNK(info.st_mode):
            raise OSError('Symlink output paths are unsupported')
        if index < len(parts) - 1:
            if not stat.S_ISDIR(info.st_mode):
                raise OSError('Output ancestor is not a directory')
        elif not stat.S_ISREG(info.st_mode):
            raise OSError('Output must be a regular file')
    if info.st_size > MAX_OUTPUT_BYTES:
        raise OSError('Output exceeds the 2 MiB limit')
    return path, info


def _read_output(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_OUTPUT_BYTES:
            raise OSError('Output must be a regular file no larger than 2 MiB')
        data = stream.read(MAX_OUTPUT_BYTES + 1)
    if len(data) > MAX_OUTPUT_BYTES:
        raise OSError('Output exceeds the 2 MiB limit')
    return data


def _json_equal(actual: object, expected: object) -> bool:
    # Python treats True == 1, but JSON booleans and JSON numbers are distinct.
    if isinstance(actual, bool) or isinstance(expected, bool):
        return isinstance(actual, bool) and isinstance(expected, bool) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_json_equal(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_json_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _json_pointer(value: object, pointer: str) -> object:
    for token in _pointer_tokens(pointer):
        if isinstance(value, dict):
            if token not in value:
                raise LookupError('JSON pointer is not present')
            value = value[token]
        elif isinstance(value, list) and re.fullmatch(r'0|[1-9][0-9]*', token):
            try:
                # Avoid Python's integer digit limit for unbounded array-index strings.
                if len(token) > len(str(len(value))):
                    raise LookupError('JSON pointer is not present')
                value = value[int(token)]
            except IndexError as error:
                raise LookupError('JSON pointer is not present') from error
        else:
            raise LookupError('JSON pointer is not present')
    return value


def _reject_constant(value: str) -> None:
    raise ValueError('Nonfinite numbers are not JSON values')


def _evaluate_one(check: dict, root: Path) -> tuple[str, str]:
    kind = check['type']
    try:
        path, info = _output_file(root, check['path'])
        if kind == 'file_absent':
            return ('pass', 'output is absent') if info is None else ('fail', 'output unexpectedly exists')
        if info is None:
            return 'fail', 'required output is missing'
        if kind == 'file_exists':
            return 'pass', 'output exists'
        try:
            text = _read_output(path).decode('utf-8')
        except UnicodeError:
            return 'fail', 'output is not valid UTF-8'
        if kind == 'file_contains':
            passed = check['text'] in text
            return ('pass', 'required text is present') if passed else ('fail', 'required text is missing')
        if kind == 'file_not_contains':
            passed = check['text'] not in text
            return ('pass', 'forbidden text is absent') if passed else ('fail', 'forbidden text is present')
        if kind == 'file_matches':
            passed = re.search(check['pattern'], text) is not None
            return ('pass', 'pattern matches') if passed else ('fail', 'pattern does not match')
        try:
            actual = json.loads(text, parse_constant=_reject_constant)
            _validate_json(actual)
        except (ValueError, RecursionError):
            return 'fail', 'output is not valid JSON'
        try:
            actual = _json_pointer(actual, check['pointer'])
        except LookupError:
            return 'fail', 'JSON pointer is not present'
        try:
            passed = _json_equal(actual, check['value'])
        except RecursionError:
            return 'fail', 'JSON nesting exceeds the verifier limit'
        return ('pass', 'JSON value matches') if passed else ('fail', 'JSON value does not match')
    except FileNotFoundError:
        # A previously present output can disappear between inspection and reading.
        return 'fail', 'required output is missing'
    except OSError as error:
        if str(error).startswith(('Output ', 'Symlink ')):
            return 'error', str(error)
        return 'error', f'cannot inspect or read output ({type(error).__name__})'


def evaluate_assertions(spec: object, root: Path) -> list[dict]:
    """Run every check and return one-based results without output contents or values."""
    checks = validate_assertions(spec)
    results = []
    for index, check in enumerate(checks, 1):
        outcome, reason = _evaluate_one(check, Path(root))
        results.append({'index': index, 'type': check['type'], 'path': check['path'],
                        'outcome': outcome, 'reason': reason})
    return results


def _main(spec: object) -> None:
    results = evaluate_assertions(spec, Path.cwd())
    for result in results:
        path = json.dumps(result['path'], ensure_ascii=True)
        print(f"{result['outcome'].upper()} [{result['index']}] {result['type']} {path}: {result['reason']}")
    raise SystemExit(2 if any(item['outcome'] == 'error' for item in results)
                     else 1 if any(item['outcome'] == 'fail' for item in results) else 0)


def build_oracle(spec: object) -> str:
    """Return a self-contained Python verifier with the validated checks frozen inside."""
    checks = validate_assertions(spec)
    imports = ('from __future__ import annotations\n'
               'import copy, json, math, os, re, stat\n'
               'from pathlib import Path, PurePosixPath, PureWindowsPath\n')
    functions = (_validate_path, _validate_json, _pointer_tokens, validate_assertions,
                 _output_file, _read_output, _json_equal, _json_pointer,
                 _reject_constant, _evaluate_one, evaluate_assertions, _main)
    source = '\n\n'.join(inspect.getsource(function) for function in functions)
    encoded = repr(json.dumps(checks, ensure_ascii=True, allow_nan=False))
    fields = {kind: sorted(names) for kind, names in _FIELDS.items()}
    return (f'# Generated by RuleBisect. Standard-library verifier; no Codex calls.\n{imports}\n'
            f'MAX_OUTPUT_BYTES = {MAX_OUTPUT_BYTES}\n'
            f'_FIELDS = {{kind: set(names) for kind, names in {fields!r}.items()}}\n\n{source}\n\n'
            f'if __name__ == "__main__":\n    _main(json.loads({encoded}))\n')
