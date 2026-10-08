#!/usr/bin/env python3
"""Extract real report nodes for mock-DOM checks; this does not render HTML."""
from __future__ import annotations

import argparse
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import sys


class Document(HTMLParser):
    VOID = frozenset({'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                      'link', 'meta', 'param', 'source', 'track', 'wbr'})

    def __init__(self, content: str):
        super().__init__(convert_charrefs=True)
        self.nodes = [{'key': 0, 'tag': 'document', 'attrs': {}, 'parent': None, 'parts': []}]
        self.stack = [0]
        self.feed(content)
        self.close()

    def handle_starttag(self, tag, attrs):
        key = len(self.nodes)
        node = {'key': key, 'tag': tag, 'attrs': dict(attrs), 'parent': self.stack[-1], 'parts': []}
        self.nodes[self.stack[-1]]['parts'].append(key)
        self.nodes.append(node)
        if tag not in self.VOID:
            self.stack.append(key)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.nodes[self.stack[index]]['tag'] == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, data):
        self.nodes[self.stack[-1]]['parts'].append(data)

    def text(self, key):
        return ''.join(self.text(part) if isinstance(part, int) else part
                       for part in self.nodes[key]['parts'])

    def fixture(self):
        # Only searchable nodes and controls need descendant text. Avoid copying
        # all code/log previews into every large ancestor in the JSON fixture.
        results = []
        for node in self.nodes[1:]:
            attrs = node['attrs']
            classes = (attrs.get('class') or '').split()
            wants_text = (node['tag'] in ('script', 'button', 'option', 'a') or attrs.get('id')
                          or any(name in classes for name in ('rule-card', 'evidence-card')))
            results.append({key: node[key] for key in ('key', 'tag', 'attrs', 'parent')}
                           | {'text': self.text(node['key']) if wants_text else ''})
        return results


def current_script() -> str:
    """Read the fixed source constant with ast; never execute code from the HTML."""
    path = Path(__file__).resolve().parents[1] / 'rulebisect' / 'ui.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'SCRIPT'
                                                     for target in statement.targets):
            value = ast.literal_eval(statement.value)
            if isinstance(value, str):
                return value
    raise ValueError('Cannot find the fixed report SCRIPT in rulebisect/ui.py')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    args = parser.parse_args(argv)
    document = Document(args.html.read_text(encoding='utf-8'))
    scripts = [node for node in document.nodes if node['tag'] == 'script']
    if len(scripts) != 1 or 'src' in scripts[0]['attrs']:
        raise ValueError('Expected one fixed inline report script; share summaries do not use controls')
    script = document.text(scripts[0]['key'])
    if script != current_script():
        raise ValueError('Report controls differ from current ui.py; regenerate this report before checking')
    ids = [node['attrs']['id'] for node in document.nodes if node['attrs'].get('id')]
    if len(ids) != len(set(ids)):
        raise ValueError('Report contains duplicate element IDs')
    if sum(node['tag'] == 'html' for node in document.nodes) != 1 or sum(node['tag'] == 'body' for node in document.nodes) != 1:
        raise ValueError('Report must contain exactly one html and body element')
    print(json.dumps({'nodes': document.fixture(), 'script': script}, ensure_ascii=True, separators=(',', ':')))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RecursionError) as error:
        print(f'report_dom_fixture: {error}', file=sys.stderr)
        raise SystemExit(2)
