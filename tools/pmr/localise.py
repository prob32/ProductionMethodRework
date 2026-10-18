"""PMR's text in the game's other languages (Pat, 2026-10-18 14:37Z: all ten, #3).

The generator writes PMR's English text; this module turns it into each other language from a translation table,
tools/pmr/translations/<lang>.json, one entry per distinct line of text. A loc value is cut at its `\\n` line breaks and
each line is masked: `$key$` references, `[data functions]` and digit runs become {0}, {1}, ... in order, so the 15 000
"(18% of levels)" methods are one entry, "{0} ({1}% of levels)". The table maps that masked English line to its
translation, which may reorder the placeholders and must keep every one of them, and the line's text formatting
(`#bold `...`#!`) and icons (`@money!`). A line the table lacks stays English, so new text never shows a raw key;
a translation that breaks those rules stops the build.

    python tools/pmr/localise.py --game <game folder>             # per language: lines translated, lines missing
    python tools/pmr/localise.py --game <game folder> --missing german

Both read a fresh English build (generate.py into a temporary folder).
"""
import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(HERE, 'translations')
LOC_LINE = re.compile(r'^ (\S+?):0 "(.*)"$')
PLACEHOLDER = re.compile(r'\{(\d+)\}')
FORMAT_OPEN = re.compile(r'#[A-Za-z_]+ ')
ICON = re.compile(r'@[a-z_]+!')


def mask(text):
    """One line of loc text as (template, tokens): references, data functions and numbers become {n}."""
    toks, out, i = [], [], 0
    while i < len(text):
        c = text[i]
        if c == '$':
            j = text.index('$', i + 1) + 1
        elif c == '[':
            depth, j = 0, i
            while True:
                depth += {'[': 1, ']': -1}.get(text[j], 0)
                j += 1
                if depth == 0:
                    break
        elif c.isdigit():
            j = i + 1
            while j < len(text) and (text[j].isdigit() or (text[j] in '.,' and text[j + 1:j + 2].isdigit())):
                j += 1
        else:
            if c in '{}':
                raise ValueError(f'brace in loc text: {text}')
            out.append(c)
            i += 1
            continue
        toks.append(text[i:j])
        out.append('{%d}' % (len(toks) - 1))
        i = j
    return ''.join(out), toks


def needs_words(template):
    """Whether a masked line has any words to translate (not just numbers, references and formatting)."""
    return bool(re.search(r'[A-Za-z]', ICON.sub('', FORMAT_OPEN.sub('', PLACEHOLDER.sub('', template)))))


def problems(english, translated):
    """Why a translation cannot stand in for its English line, or an empty list."""
    out = []
    if sorted(PLACEHOLDER.findall(english)) != sorted(PLACEHOLDER.findall(translated)):
        out.append('placeholders differ')
    if sorted(FORMAT_OPEN.findall(english)) != sorted(FORMAT_OPEN.findall(translated)):
        out.append('formatting codes differ')
    if english.count('#!') != translated.count('#!'):
        out.append('#! count differs')
    if sorted(ICON.findall(english)) != sorted(ICON.findall(translated)):
        out.append('icons differ')
    if re.search(r'["$\[\]\n]|\\', translated):
        out.append('contains " $ [ ] or a backslash')
    if english[:1] == ' ' and translated[:1] != ' ':
        out.append('leading space lost')
    if not translated.strip():
        out.append('empty')
    return out


def load(lang):
    path = os.path.join(TABLES, f'{lang}.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        table = json.load(f)
    bad = [f'  {en!r}: {", ".join(p)}' for en, tr in table.items() for p in [problems(en, tr)] if p]
    if bad:
        raise SystemExit(f'{path}: {len(bad)} translations break the line they translate:\n' + '\n'.join(bad))
    return table


def tables():
    """Every language that has a table, with its table."""
    return {f[:-5]: load(f[:-5]) for f in sorted(os.listdir(TABLES)) if f.endswith('.json')} \
        if os.path.isdir(TABLES) else {}


def translate_text(text, table, missing=None):
    """One loc value in the table's language; lines the table lacks stay English and are counted in `missing`."""
    parts = []
    for part in text.split('\\n'):
        template, toks = mask(part)
        if template in table:
            part = PLACEHOLDER.sub(lambda t: toks[int(t.group(1))], table[template])
        elif missing is not None and needs_words(template):
            missing[template] += 1
        parts.append(part)
    return '\\n'.join(parts)


def translate(loc, lang, missing=None):
    """The loc lines (` KEY:0 "text"`) in `lang`."""
    table = load(lang)
    out = []
    for line in loc:
        m = LOC_LINE.match(line)
        out.append(f' {m.group(1)}:0 "{translate_text(m.group(2), table, missing)}"' if m else line)
    return out


def templates(loc):
    """Every distinct masked line with words in it, in first-seen order, with the first key that uses it."""
    seen = {}
    for line in loc:
        m = LOC_LINE.match(line)
        if m:
            for part in m.group(2).split('\\n'):
                template = mask(part)[0]
                if needs_words(template):
                    seen.setdefault(template, m.group(1))
    return seen


def main():
    import argparse
    import subprocess
    import tempfile
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--game', required=True)
    ap.add_argument('--missing', metavar='LANG', help='print the English lines LANG has no translation for')
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['python3', os.path.join(HERE, 'generate.py'), '--game', args.game, '--out', tmp,
                        '--test-name', 'Localise'], check=True, stdout=subprocess.DEVNULL)
        with open(os.path.join(tmp, 'localization', 'english', 'pmr_l_english.yml'), encoding='utf-8-sig') as f:
            loc = f.read().splitlines()[1:]
    lines = templates(loc)
    import generate
    for lang in generate.OTHER_LANGUAGES:
        table = load(lang)
        lacking = [t for t in lines if t not in table]
        print(f'{lang:13s} {len(lines) - len(lacking)} of {len(lines)} lines translated, '
              f'{len(set(table) - set(lines))} table entries no longer used')
        if lang == args.missing:
            for t in lacking:
                print(f'    {lines[t]}: {t}')


if __name__ == '__main__':
    main()
