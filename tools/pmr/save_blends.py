"""Where a game has taken PMR's trade-offs: reads a text Victoria 3 save and prints, per building type
and trade-off group, the level-weighted shares now and where each building is heading (its
best-paying option at its state's prices, none below the dead band), plus a TRADE_PRELOAD for
generate.py. Pat, 2026-10-13: new games start each trade-off near where games take it.

    python3 save_blends.py <save.v3> [--mod pmr/ProductionMethodRework]

The option map comes from the generated mod's GENERATION_REPORT.json and the dead bands from its
pmr_effects.txt (the `pmr_gap > X` of each pmr_xstep_<gi>_<b>). Shares are read from each building's
active share digits (tens pm_pmr_x_<b>_<j>_<10t> plus units pm_pmr_xu_<b>_<j>_<u>), values and
availability from its state's variables (pmr_xv_<j>_<b>, pmr_xav_<j>_<b>). The save must be plain text (Victoria 3 writes these unless ironman
or compressed saves are on); it streams the file, so a 200 MB save takes a few seconds.
"""
import argparse
import collections
import json
import os
import re

SECTIONS = ('states', 'building_manager', 'country_manager')


def read_save(path):
    state_re = re.compile(r'^(\d+)=\{$')
    pm_re = re.compile(r'"pm_pmr_xu?_[a-z_]+?_(\d+)_(\d+)"')   # tens and units digits add up
    states, buildings, countries = {}, [], {}
    section = cur = flag = None
    depth = 0
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            d0 = depth
            depth += line.count('{') - line.count('}')
            if d0 == 0:
                key = line.split('=', 1)[0]
                section = key if key in SECTIONS else None
                cur = None
                continue
            if section is None:
                continue
            m = state_re.match(line) if d0 == 2 else None
            if m:
                cur = {'id': int(m.group(1))}
                if section == 'states':
                    states[cur['id']] = cur
                elif section == 'building_manager':
                    buildings.append(cur)
                else:
                    countries[cur['id']] = cur
                continue
            if cur is None:
                continue
            s = line.strip()
            if section == 'states':
                if line.startswith('\tcountry='):
                    cur['country'] = int(s.split('=')[1])
                elif line.startswith('\tregion='):
                    cur['region'] = s.split('=')[1].strip('"')
                elif s.startswith('flag='):
                    flag = s[5:] if s.startswith('flag=pmr_x') else None
                    if flag:
                        cur.setdefault('vars', {})[flag] = 0.0   # a zero value has no identity line
                elif flag and s.startswith('identity='):
                    raw = int(s.split('=')[1])
                    if raw >= 2 ** 63:
                        raw -= 2 ** 64
                    cur['vars'][flag] = raw / 100000
                    flag = None
            elif section == 'building_manager':
                if line.startswith('\tbuilding='):
                    cur['type'] = s.split('=')[1].strip('"')
                elif line.startswith('\tlevels='):
                    cur['levels'] = int(s.split('=')[1])
                elif line.startswith('\tstate='):
                    cur['state'] = int(s.split('=')[1])
                elif line.startswith('\tproduction_methods='):
                    cur['x'] = collections.Counter()
                    for j, n in pm_re.findall(line):
                        cur['x'][int(j)] += int(n)
            elif line.startswith('\tdefinition='):
                cur['tag'] = s.split('=')[1].strip('"')
    return states, buildings, countries


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('save')
    ap.add_argument('--mod', default=os.path.join(os.path.dirname(__file__), '..', '..', 'pmr', 'ProductionMethodRework'))
    args = ap.parse_args()
    report = json.load(open(os.path.join(args.mod, 'GENERATION_REPORT.json')))
    fx = os.path.join(args.mod, 'common', 'scripted_effects')
    effects = ''.join(open(os.path.join(fx, f), encoding='utf-8-sig').read()   # pmr_effects.txt and its parts
                      for f in sorted(os.listdir(fx)) if re.fullmatch(r'pmr_effects(_\d+)?\.txt', f))
    groups = collections.defaultdict(list)   # building -> [(gi, group, [(j, key)])]
    for g in report['options']:
        if g['mode'] == 'market':
            b = g['building'][len('building_'):]
            groups[b].append((len(groups[b]) + 1, g['group'], [(o['j'], o['key']) for o in g['options']]))
    band = {}
    for m in re.finditer(r'^pmr_xstep_(\d+)_([a-z_]+) = \{.*?var:pmr_gap > ([0-9.]+)', effects, re.M | re.S):
        band[(m.group(2), int(m.group(1)))] = float(m.group(3))

    states, buildings, countries = read_save(args.save)
    now, heading = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    levels, count = collections.Counter(), collections.Counter()
    for bld in buildings:
        b = bld.get('type', '')[len('building_'):]
        if b not in groups or not bld.get('x'):
            continue
        st = states.get(bld.get('state'), {})
        v = st.get('vars', {})
        lv = bld.get('levels', 0)
        for gi, group, opts in groups[b]:
            k = (b, gi)
            levels[k] += lv
            count[k] += 1
            now[k][None] += (100 - sum(bld['x'].get(j, 0) for j, _ in opts)) * lv
            best, best_v = None, 0.0
            for j, key in opts:
                now[k][key] += bld['x'].get(j, 0) * lv
                val = v.get(f'pmr_xv_{j}_{b}')
                if v.get(f'pmr_xav_{j}_{b}') == 1 and val is not None and val > best_v:
                    best, best_v = key, val
            heading[k][best if best_v > band.get(k, 0) else None] += 100 * lv
    print(f'{len(states)} states, {len(buildings)} buildings, {len(countries)} countries')
    preload = collections.defaultdict(dict)
    for k in sorted(levels):
        lv = levels[k] or 1
        fmt = lambda c: ', '.join(f'{key or "none"} {c[key] / lv:.0f}' for key in sorted(c, key=lambda x: x or ''))   # noqa: E731
        print(f'{k[0]} {groups[k[0]][k[1] - 1][1]}: {count[k]} buildings, {levels[k]} levels\n'
              f'  now      {fmt(now[k])}\n  heading  {fmt(heading[k])}')
        for key, n in heading[k].items():
            if key and round(n / lv):
                preload[f'building_{k[0]}'][key] = round(n / lv)
    print('\nTRADE_PRELOAD = ' + json.dumps(preload, indent=4))


if __name__ == '__main__':
    main()
