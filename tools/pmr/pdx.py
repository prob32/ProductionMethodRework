"""Minimal Clausewitz/Jomini script reader for the PMR generator.

Reads enough of the script grammar to walk buildings, production method groups
and production methods: ``key = value``, ``key = { ... }``, bare list items,
comparison operators, quoted strings and ``#`` comments. Every node keeps the
character span it came from, so the generator can rewrite vanilla files by
cutting spans out of the original text instead of re-printing them. That keeps
every line PMR does not touch byte-identical to vanilla.
"""

import re

_TOKEN = re.compile(
    r'\s+|#[^\n]*|"(?:[^"\\]|\\.)*"|[{}]|<=|>=|!=|\?=|==|[=<>]|[^\s{}=<>#"!?]+'
)


class Node:
    __slots__ = ('key', 'op', 'value', 'start', 'end')

    def __init__(self, key, op, value, start, end):
        self.key, self.op, self.value, self.start, self.end = key, op, value, start, end

    @property
    def is_block(self):
        return isinstance(self.value, list)

    def __repr__(self):
        return f'Node({self.key!r}, {self.op!r}, {"[...]" if self.is_block else self.value!r})'


def _tokens(text):
    pos = 0
    out = []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(f'unreadable script at offset {pos}: {text[pos:pos + 40]!r}')
        tok = m.group(0)
        if not (tok.isspace() or tok.startswith('#')):
            out.append((tok, m.start(), m.end()))
        pos = m.end()
    return out


_OPS = {'=', '<', '>', '<=', '>=', '!=', '?=', '=='}


def parse(text):
    """Parse a whole file into a list of Nodes."""
    if text.startswith('﻿'):
        text = text[1:]
    toks = _tokens(text)
    nodes, i = _block(toks, 0, top=True)
    return nodes


def _block(toks, i, top=False):
    nodes = []
    while i < len(toks):
        tok, s, e = toks[i]
        if tok == '}':
            if top:
                raise ValueError(f'unbalanced }} at offset {s}')
            return nodes, i
        if tok == '{':
            # anonymous block (list of blocks)
            inner, j = _block(toks, i + 1)
            nodes.append(Node(None, None, inner, s, toks[j][2]))
            i = j + 1
            continue
        if i + 1 < len(toks) and toks[i + 1][0] in _OPS:
            op = toks[i + 1][0]
            vtok, vs, ve = toks[i + 2]
            if vtok == '{':
                inner, j = _block(toks, i + 3)
                nodes.append(Node(tok, op, inner, s, toks[j][2]))
                i = j + 1
            else:
                nodes.append(Node(tok, op, vtok.strip('"'), s, ve))
                i += 3
            continue
        nodes.append(Node(None, None, tok.strip('"'), s, e))  # bare list item
        i += 1
    if not top:
        raise ValueError('unterminated block')
    return nodes, i


def get(nodes, key):
    for n in nodes:
        if n.key == key:
            return n
    return None


def get_all(nodes, key):
    return [n for n in nodes if n.key == key]


def items(node):
    """Bare list items of a block, e.g. production_method_groups = { a b c }."""
    return [n.value for n in node.value if n.key is None and not isinstance(n.value, list)]


def strip_bom(text):
    return text[1:] if text.startswith('﻿') else text
