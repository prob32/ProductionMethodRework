"""Every test run's PMR log lines and saves, filed by build, in one SQLite database (Pat 2026-10-30 12:35Z: "track every
single save log we do by build version so we can track and patch number across many stats").

    python3 runs.py ingest <log files or dirs>... [--build qN] [--note TEXT]
    python3 runs.py save <text save> [--run RUN]
    python3 runs.py runs
    python3 runs.py compare BUDGET fexp [--country NAME | --sum] [--runs RUN,RUN]
    python3 runs.py build qN --commit SHA [--installed UTC] [--manifest PATH] [--summary TEXT]

The database is RUNS_DB (shared project folder) unless --db names another. A test build made with
generate.py --build qN logs a BUILD line (build, commit, mod version) at game start and once a game year, and keeps
pmr_build / pmr_build_first in its saves; older logs take --build.

Runs: a LOADED line (a new game) starts a run; so does a BUILD line naming another build than the run's, or the game
date going back more than a month (a save loaded). A run is named <build>-<n>. Lines are kept once (payload and clock),
so the same rotated debug.log can be ingested again and again. The game version and playset come from the debug.log
header lines when a raw debug.log is ingested.
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys

RUNS_DB = '/mnt/project-files/pmr/runs/runs.db'
START = datetime.date(1836, 1, 30)   # an observer game's yearly checks count from here (observer-q88/ingest.py)
LINE = re.compile(r'^(?:\[(\d\d:\d\d:\d\d)\])?.*?(PMR;rec=([A-Z_0-9]+);.*)$')
GAME_VERSION = re.compile(r'Feeding game version into checksum: (\S+)')
MOD_LINE = re.compile(r'\]: Mod (.+?) \((\S+)\) version \S+ successfully matched game version')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS builds (build TEXT PRIMARY KEY, commit_sha TEXT, version TEXT, installed TEXT,
    manifest TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS runs (run TEXT PRIMARY KEY, build TEXT, n INT, kind TEXT, game_version TEXT, mods TEXT,
    first_date TEXT, last_date TEXT, lines INT DEFAULT 0, ingested TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS lines (id INTEGER PRIMARY KEY, run TEXT, clock TEXT, rec TEXT, date TEXT, country TEXT,
    payload TEXT, key TEXT UNIQUE);
CREATE INDEX IF NOT EXISTS lines_run_rec ON lines (run, rec);
CREATE TABLE IF NOT EXISTS stats (run TEXT, rec TEXT, year INT, date TEXT, country TEXT, field TEXT, value REAL,
    PRIMARY KEY (run, rec, year, country, field));
CREATE TABLE IF NOT EXISTS saves (file TEXT, sha1 TEXT PRIMARY KEY, size INT, date TEXT, run TEXT, build INT,
    build_first INT, registered TEXT);
CREATE TABLE IF NOT EXISTS save_budget (sha1 TEXT, country TEXT, field TEXT, value REAL,
    PRIMARY KEY (sha1, country, field));
'''
YEARLY = ('ARMY', 'BUDGET')   # one line a country a game year: filed by year in stats as well


def connect(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def fields(payload):
    return dict(kv.split('=', 1) for kv in payload.split(';')[1:] if '=' in kv)


def iso(date):
    try:
        return datetime.datetime.strptime(date.strip(), '%B %d, %Y').date()
    except ValueError:
        return None


def num(x):
    try:
        return float(x.replace(',', ''))
    except (AttributeError, ValueError):
        return None


def log_files(paths):
    """Files in the order they were written: debug.5.log .. debug.1.log, debug.log, then anything else by name."""
    out = []
    for p in paths:
        out += sorted(glob.glob(os.path.join(p, '*.log'))) if os.path.isdir(p) else [p]
    def order(f):
        m = re.fullmatch(r'debug(?:\.(\d))?\.log', os.path.basename(f))
        return (0, -int(m[1] or 0)) if m else (1, os.path.basename(f))
    return sorted(dict.fromkeys(out), key=order)


def current_run(db):
    row = db.execute('SELECT run, build, n, last_date FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
    return list(row) if row else None


def new_run(db, build, kind, header, note):
    build = build or 'unknown'
    n = db.execute('SELECT COALESCE(MAX(n), 0) + 1 FROM runs WHERE build = ?', (build,)).fetchone()[0]
    run = f'{build}-{n}'
    db.execute('INSERT INTO runs (run, build, n, kind, game_version, mods, ingested, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
               (run, build, n, kind, header.get('version'), json.dumps(header.get('mods', [])) if header.get('mods') else None,
                datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), note))
    return [run, build, n, None]


def ingest(db, paths, build=None, note=None):
    cur = current_run(db)
    header, mods, added = {}, [], 0
    for path in log_files(paths):
        for raw in open(path, encoding='utf-8', errors='replace'):
            m = MOD_LINE.search(raw)   # the playset's mods come a few lines before the game version
            if m:
                mods.append(m[1])
                continue
            m = GAME_VERSION.search(raw)
            if m:
                header, mods = {'version': m[1], 'mods': mods}, []
                continue
            m = LINE.match(raw.rstrip('\n'))
            if not m:
                continue
            clock, payload, rec = m[1] or '', m[2], m[3]
            key = hashlib.sha1(f'{clock}|{payload}'.encode()).hexdigest()
            if db.execute('SELECT 1 FROM lines WHERE key = ?', (key,)).fetchone():
                continue
            f = fields(payload)
            d = iso(f.get('date', ''))
            tag = f.get('build') if rec == 'BUILD' else None
            if rec == 'LOADED' or cur is None:
                cur = new_run(db, tag or build, 'new game' if rec == 'LOADED' else 'from logs', header, note)
            elif tag and cur[1] not in (tag, 'unknown') or (d and cur[3] and d < cur[3] - datetime.timedelta(days=31)):
                cur = new_run(db, tag or cur[1], 'loaded save', header, note)
            if tag and cur[1] == 'unknown':   # the LOADED line came first: the BUILD line names the run's build
                cur = rename_run(db, cur, tag)
            if rec == 'BUILD' and tag and not db.execute('SELECT 1 FROM builds WHERE build = ?', (tag,)).fetchone():
                db.execute('INSERT INTO builds (build, commit_sha, version) VALUES (?, ?, ?)', (tag, f.get('commit'), f.get('version')))
            db.execute('INSERT INTO lines (run, clock, rec, date, country, payload, key) VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (cur[0], clock, rec, d.isoformat() if d else None, f.get('country'), payload, key))
            if rec in YEARLY and d:
                year = 1836 + round((d - START).days / 365.25)
                for k, v in f.items():
                    if k not in ('date', 'country') and num(v) is not None:
                        db.execute('INSERT OR REPLACE INTO stats VALUES (?, ?, ?, ?, ?, ?, ?)',
                                   (cur[0], rec, year, d.isoformat(), f.get('country', ''), k, num(v)))
            if d:
                cur[3] = max(cur[3], d) if cur[3] else d
                db.execute('UPDATE runs SET first_date = COALESCE(MIN(first_date, ?), ?), last_date = ? WHERE run = ?',
                           (d.isoformat(), d.isoformat(), cur[3].isoformat(), cur[0]))
            db.execute('UPDATE runs SET lines = lines + 1 WHERE run = ?', (cur[0],))
            added += 1
    db.commit()
    return added


def rename_run(db, cur, build):
    n = db.execute('SELECT COALESCE(MAX(n), 0) + 1 FROM runs WHERE build = ?', (build,)).fetchone()[0]
    run = f'{build}-{n}'
    for t in ('runs', 'lines', 'stats'):
        db.execute(f'UPDATE {t} SET run = ? WHERE run = ?', (run, cur[0]))
    db.execute('UPDATE runs SET build = ?, n = ? WHERE run = ?', (build, n, run))
    return [run, build, n, cur[3]]


def show_runs(db):
    for r in db.execute('SELECT r.run, r.kind, r.first_date, r.last_date, r.lines, r.game_version, b.commit_sha, r.note '
                        'FROM runs r LEFT JOIN builds b ON b.build = r.build ORDER BY r.rowid'):
        print(' | '.join('' if x is None else str(x) for x in r))


def compare(db, rec, field, country=None, total=False, runs=None):
    runs = runs or [r for (r,) in db.execute('SELECT DISTINCT run FROM stats WHERE rec = ? AND field = ? ORDER BY run', (rec, field))]
    if country:
        q, args = 'SELECT year, value FROM stats WHERE run = ? AND rec = ? AND field = ? AND country = ?', (rec, field, country)
    else:
        q, args = ('SELECT year, ' + ('SUM' if total else 'AVG') + '(value) FROM stats WHERE run = ? AND rec = ? AND field = ? '
                   'GROUP BY year'), (rec, field)
    table = {r: dict(db.execute(q, (r,) + args).fetchall()) for r in runs}
    years = sorted({y for t in table.values() for y in t})
    print('year | ' + ' | '.join(runs))
    for y in years:
        print(f'{y} | ' + ' | '.join('' if table[r].get(y) is None else f'{table[r][y]:,.2f}' for r in runs))


def register_save(db, path, run=None):
    """A text save: its date, the build stamp (pmr_build, pmr_build_first) and every country's weekly budget lines."""
    h, size = hashlib.sha1(), os.path.getsize(path)
    date = build = first = None
    budgets, cid, depth, inside, cur = {}, None, 0, False, None
    with open(path, 'rb') as fb:
        for chunk in iter(lambda: fb.read(1 << 24), b''):
            h.update(chunk)
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            s = line.strip()
            if date is None and line.startswith('date='):
                date = s.split('=')[1]
            if s.startswith('name="pmr_build"') or s.startswith('name=pmr_build'):
                pending = 'pmr_build_first' if 'pmr_build_first' in s else 'pmr_build'
                nxt = next(f, '').strip()
                v = num(nxt.split('=', 1)[1]) if nxt.startswith('value=') else None
                if pending == 'pmr_build':
                    build = v
                else:
                    first = v
                continue
            if not inside:
                if line.startswith('country_manager={'):
                    inside, depth = True, 1
                continue
            d0 = depth
            depth += line.count('{') - line.count('}')
            if depth <= 0:
                inside = False
                continue
            if d0 == 2:
                m = re.match(r'^(\d+)=\{', s)
                cur = {} if m else None
                if m:
                    budgets[m[1]] = cur
            elif cur is not None and d0 == 3 and s.startswith('definition='):
                cur['tag'] = s.split('=', 1)[1].strip('"')
            elif cur is not None and d0 == 4:
                for k in ('weekly_expenses', 'weekly_income'):
                    if s.startswith(k + '={'):
                        cur[k] = [float(x) for x in s.split('{')[1].split('}')[0].split()]
                for k in ('money', 'principal', 'investment_pool'):
                    if s.startswith(k + '='):
                        cur[k] = num(s.split('=')[1])
    sha = h.hexdigest()
    db.execute('INSERT OR REPLACE INTO saves VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
               (os.path.basename(path), sha, size, date, run, build, first,
                datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')))
    for c in budgets.values():
        tag = c.get('tag')
        if not tag or 'weekly_income' not in c:
            continue
        rows = {'income': sum(c['weekly_income']), 'expenses': sum(c.get('weekly_expenses', [])),
                **{f'income_{i}': v for i, v in enumerate(c['weekly_income'])},
                **{f'expenses_{i}': v for i, v in enumerate(c.get('weekly_expenses', []))},
                **{k: c[k] for k in ('money', 'principal', 'investment_pool') if c.get(k) is not None}}
        db.executemany('INSERT OR REPLACE INTO save_budget VALUES (?, ?, ?, ?)', [(sha, tag, k, v) for k, v in rows.items()])
    db.commit()
    return date, build, first, len(budgets)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--db', default=RUNS_DB)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('ingest'); p.add_argument('paths', nargs='+'); p.add_argument('--build'); p.add_argument('--note')
    p = sub.add_parser('save'); p.add_argument('path'); p.add_argument('--run')
    sub.add_parser('runs')
    p = sub.add_parser('compare'); p.add_argument('rec'); p.add_argument('field'); p.add_argument('--country')
    p.add_argument('--sum', action='store_true'); p.add_argument('--runs')
    p = sub.add_parser('build'); p.add_argument('build'); p.add_argument('--commit', required=True)
    p.add_argument('--installed'); p.add_argument('--manifest'); p.add_argument('--summary'); p.add_argument('--version')
    a = ap.parse_args()
    db = connect(a.db)
    if a.cmd == 'ingest':
        print('lines added', ingest(db, a.paths, a.build, a.note))
        show_runs(db)
    elif a.cmd == 'save':
        print('save', register_save(db, a.path, a.run))
    elif a.cmd == 'runs':
        show_runs(db)
    elif a.cmd == 'compare':
        compare(db, a.rec, a.field, a.country, a.sum, a.runs.split(',') if a.runs else None)
    elif a.cmd == 'build':
        db.execute('INSERT OR REPLACE INTO builds VALUES (?, ?, ?, ?, ?, ?)',
                   (a.build, a.commit, a.version, a.installed, a.manifest, a.summary))
        db.commit()


if __name__ == '__main__':
    sys.exit(main())
