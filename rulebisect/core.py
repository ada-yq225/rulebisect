from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from typing import Callable


@dataclass(frozen=True)
class Rule:
    id: int
    path: str
    line: int
    text: str

    def to_dict(self):
        return asdict(self)


def split_rules(path: str, text: str, start: int = 0, mode: str = 'paragraph') -> list[Rule]:
    """Paragraph units; keep fenced code together and preserve every original byte."""
    if mode == 'file':
        return [Rule(start, path, 1, text)] if text.strip() else []
    if mode not in ('paragraph', 'section'):
        raise ValueError('unit_mode must be paragraph, section or file')
    rules, chunk = [], []
    first, fence = 1, None
    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence) and not line[marker.end():].strip():
                fence = None
        if mode == 'section' and fence is None and re.match(r'^ {0,3}#{1,6}\s+\S', line) and any(part.strip() for part in chunk):
            rules.append(Rule(start + len(rules), path, first, ''.join(chunk)))
            chunk = []
            first = line_number
        chunk.append(line)
        if mode == 'paragraph' and not line.strip() and fence is None:
            if any(part.strip() for part in chunk):
                rules.append(Rule(start + len(rules), path, first, "".join(chunk)))
                chunk = []
                first = line_number + 1
    if chunk:
        if any(part.strip() for part in chunk):
            rules.append(Rule(start + len(rules), path, first, "".join(chunk)))
        elif rules:
            old = rules[-1]
            rules[-1] = Rule(old.id, old.path, old.line, old.text + "".join(chunk))
    return rules


class StopSearch(Exception):
    pass


def reduce_failure(ids: list[int], evaluate: Callable[[list[int]], str]) -> list[int]:
    """Find a candidate with ddmin. The experiment separately confirms it afresh."""
    current, divisions = list(ids), 2
    while len(current) >= 2:
        width = math.ceil(len(current) / divisions)
        chunks = [current[i:i + width] for i in range(0, len(current), width)]
        candidates = [[x for x in current if x not in chunk] for chunk in chunks] + chunks
        reduced = False
        for candidate in candidates:
            if candidate and candidate != current and evaluate(candidate) == "fail":
                current = candidate
                divisions = max(2, divisions - 1)
                reduced = True
                break
        if reduced:
            continue
        if divisions >= len(current):
            break
        divisions = min(len(current), divisions * 2)
    # Cache reuse is intentionally permitted in the search, not in confirmation.
    return current


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
