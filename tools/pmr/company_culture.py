"""Company Culture: a HoI4-style trait tree on every company's panel (Pat, 2026-10-14).

Pat 02:03Z asked for a company sub-panel like Hearts of Iron IV's military-industrial organisations: prosperity
earns points, points buy a tree of bonuses, and a Methods list shows every recipe of the company's buildings. The
plan is /mnt/project-files/pmr/mio/PLAN.md; Pat answered its questions at 04:00Z and this module builds them.

How a bonus reaches the company's own levels and nobody else's (Pat 03:02Z, confirmed in game 03:51Z on the
Hudson's Bay Company): each bonus is a character trait on the company's executive with an `executive_modifier`,
which the engine "applies to building levels owned by the company that the character is the executive for"
(common/character_traits/character_traits.md), in proportion on part-owned buildings (Pat 03:56Z: seen in vanilla).

The tree, one fixed shape for every company (Pat 04:00Z):
  - Equipment, Refined Process I-III: every level the company owns uses fewer input goods
    (building_goods_input_mult, the key vanilla's trade_distance modifier uses on buildings).
  - People, Skilled Workforce I-III: fewer laborer jobs, a few engineer jobs in their place (Pat: "trade off
    laborers for engineers"). Net jobs -3 / -6 / -10%, one engineer for every four laborers cut.
  - Equipment and People exclude each other: the first tier bought locks the company to its column (Pat: lock).
  - Scale, Expanded Works I, II and Mass Production: +5 / +5 / +10% throughput on every level the company owns.
  - No charter bonus (Pat: remove it).
Node tiers cost 1, 2 and 3 points, so a finished tree is 12 points.

Equipment is matched to People company by company (Pat: "rough math for each company") on productivity, vanilla's
own measure of a building (value added per job) and the one that feeds company prosperity: People makes the same
goods with fewer jobs, Equipment makes them from fewer inputs, and each Equipment tier raises a level's value added
by as much as the People tier beside it raises its value added per job, at base prices. (Matched on profit instead,
steel and shipbuilding firms got Equipment tiers of 0.2%: the engineers People adds cost about three laborers'
wages each, so People saves little money, and an Equipment tier worth that little looked broken.) Where inputs are
very cheap (plantations) the cut would pass INPUT_CUT_MAX, and the column is scaled down to it. The numbers are the
average over the company's building types and each type's PMR recipes. calibrate() writes them, and the
per-company table goes to the report (CALIBRATION_MD).

Points (plan section 2): each month a company earns prosperity x (1 + employed levels / 50, capped at 2) funds; a
full bar (100 x (level + 1)^1.8 + 700, HoI4's curve) is one point and one Culture level. Prosperity and employed
levels are read with comparison ladders (company_prosperity, company_employed_levels; vanilla compares both).

State lives on the company (vanilla sets variables on companies, 05_prestige_goods.txt). The panel cannot be
shown to read a company's variables (no vanilla GUI uses Company.MakeScope), so every value the tab shows is
mirrored onto the executive, which it reads as Company.GetExecutive.MakeScope (vanilla uses Character.MakeScope),
and the buttons are character-scope scripted GUIs (vanilla journal_entry_sguis.txt has one). The scripted GUI
finds the company back as the owner's company whose executive is that character. A new executive is detected
monthly by a variable holding the company (pmr_cc_of) and gets the traits then.

Test builds also get a decision granting TEST_POINTS points to each of the player's companies (a first point takes
a company about fifteen months); drop it when Company Culture moves into the release.

Wiring into generate.py main(), test builds only until Pat ships it:

    import company_culture
    loc += company_culture.write_all(game, write, header, report)
"""
import glob
import os
import re

import pdx

TAB = 'pmr_culture'                 # InformationPanel tab id
OWN_GUI = 'gui/pmr_company_culture.gui'
PANEL_GUI = 'gui/company_panel.gui'
CALIBRATION_MD = '/mnt/project-files/pmr/mio/calibration.md'
CAL_VERSION = 1                     # bump to make every company re-read its numbers (pmr_cc_on)

# The tree (Pat 04:00Z). Line code, key, column name, node names, trait icons.
LINES = [
    (1, 'eq', 'Equipment', ('Refined Process I', 'Refined Process II', 'Refined Process III'),
     ('meticulous', 'engineer', 'innovative')),
    (2, 'pp', 'People', ('Skilled Workforce I', 'Skilled Workforce II', 'Skilled Workforce III'),
     ('tactful', 'erudite', 'charismatic')),
    (3, 'sc', 'Scale', ('Expanded Works I', 'Expanded Works II', 'Mass Production'),
     ('basic_entrepreneur', 'experienced_entrepreneur', 'expert_entrepreneur')),
]
EXCLUSIVE = {'eq': 'pp', 'pp': 'eq'}
TIER_COST = (1, 2, 3)               # points per tier (Pat 12:37Z: no queue, a click spends points already earned)
COLUMN_ICONS = {'eq': 'gfx/interface/icons/timed_modifier_icons/modifier_gear_positive.dds',
                'pp': 'gfx/interface/icons/pops_icons/engineers.dds',
                'sc': 'gfx/interface/icons/generic_icons/upgrade_arrow.dds'}
TRAIT_ICON = 'gfx/interface/icons/character_trait_icons/{}.dds'
EXCLUSIVE_ICON = 'gfx/interface/icons/generic_icons/warning.dds'
WHITE = 'gfx/interface/backgrounds/white.dds'

JOB_CUT = (0.03, 0.06, 0.10)        # People: net share of jobs cut per tier (Pat 04:00Z: 3 / 6 / 10%)
LABORERS_PER_ENGINEER = 4           # People: one engineer job added for every four laborer jobs cut
LABORER_CUT_MAX = 0.6
THROUGHPUT = (0.05, 0.10, 0.20)     # Scale: +5 / +5 / +10%, so 5, 10 and 20% in all
INPUT_CUT_MAX = 0.20                # Equipment: the most input goods tier III may cut

# Points (plan section 2)
PROSPERITY_LADDER = list(range(100, 0, -5))          # 100, 95 .. 5
SIZE_LADDER = [(n, 1 + n / 50) for n in range(50, 0, -5)]
MAX_LEVEL = 60


def point_cost(level):
    return round(100 * (level + 1) ** 1.8 + 700)


def short(company):
    return company[len('company_'):] if company.startswith('company_') else company


def fail(where, msg):
    raise SystemExit(f'company_culture: {where}: {msg}')


# ---------------------------------------------------------------------------------------------------------------
# Reading the game

def companies(game):
    """company key -> building_types, in file order."""
    out = {}
    for path in sorted(glob.glob(os.path.join(game, 'common', 'company_types', '*.txt'))):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and n.key and n.key.startswith('company_'):
                bt = pdx.get(n.value, 'building_types')
                out[n.key] = pdx.items(bt) if bt else []
    if len(out) < 100:
        fail('common/company_types', f'only {len(out)} company types found')
    return out


def goods_cost(game):
    cost = {}
    for path in glob.glob(os.path.join(game, 'common', 'goods', '*.txt')):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and pdx.get(n.value, 'cost'):
                cost[n.key] = float(pdx.get(n.value, 'cost').value)
    return cost


def pm_info(game):
    """production method key -> (texture, unlocking technologies)."""
    out = {}
    for path in glob.glob(os.path.join(game, 'common', 'production_methods', '*.txt')):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and n.key:
                tex = pdx.get(n.value, 'texture')
                ut = pdx.get(n.value, 'unlocking_technologies')
                out[n.key] = (tex.value if tex else None, pdx.items(ut) if ut else [])
    return out


# ---------------------------------------------------------------------------------------------------------------
# Rough productivity math (Pat 04:00Z)

def building_stats(blended, cost):
    """building type -> its recipes' average jobs, laborer jobs, input and output value per level."""
    by_b = {}
    for r in blended:
        by_b.setdefault(r['building'], []).append(r)
    out = {}
    for b, rs in by_b.items():
        tot = dict(W=0.0, Lab=0.0, I=0.0, O=0.0)
        for r in rs:
            emp = {k[len('building_employment_'):-len('_add')]: v for k, v in r['employment'].items()}
            tot['W'] += sum(emp.values())
            tot['Lab'] += emp.get('laborers', 0)
            for k, v in r['blend'].get('building_modifiers', {}).items():
                if k.startswith('goods_input_') and k.endswith('_add'):
                    tot['I'] += v * cost.get(k[len('goods_input_'):-len('_add')], 0)
                elif k.startswith('goods_output_') and k.endswith('_add'):
                    tot['O'] += v * cost.get(k[len('goods_output_'):-len('_add')], 0)
        out[b] = {k: v / len(rs) for k, v in tot.items()}
    return out


def tiers_for(m):
    """People and Equipment numbers for one company's average level, or None without laborers, inputs or value
    added. p: People's productivity gain (the same goods from fewer jobs); x: the Equipment input cut that adds as
    much value added at base prices; e: Equipment's gain once INPUT_CUT_MAX scales the column (p where it doesn't)."""
    if not m or m['Lab'] <= 0 or m['W'] <= 0 or m['I'] <= 0 or m['O'] <= m['I']:
        return None
    va = m['O'] - m['I']
    rows = []
    for c in JOB_CUT:
        cut = min(c * m['W'] * LABORERS_PER_ENGINEER / (LABORERS_PER_ENGINEER - 1), LABORER_CUT_MAX * m['Lab'])
        eng = cut / LABORERS_PER_ENGINEER
        net = cut - eng
        p = net / (m['W'] - net)
        rows.append({'l': cut / m['Lab'], 'a': eng, 'p': p, 'x': p * va / m['I']})
    scale = min(1.0, INPUT_CUT_MAX / rows[-1]['x'])
    for r in rows:
        r['x'] *= scale
        r['e'] = r['x'] * m['I'] / va
    return rows


def rounded(rows):
    out = []
    for r in rows:
        out.append({'l': max(round(r['l'], 2), 0.01), 'a': max(5 * round(r['a'] / 5), 5),
                    'p': round(r['p'], 3), 'e': round(r['e'], 3),
                    'x': min(max(round(r['x'], 3), 0.001), INPUT_CUT_MAX)})
    return out


def calibrate(comps, blended, cost):
    stats = building_stats(blended, cost)
    cal, fallback = {}, []
    for c, bts in comps.items():
        st = [stats[b] for b in bts if b in stats]
        m = {k: sum(s[k] for s in st) / len(st) for k in ('W', 'Lab', 'I', 'O')} if st else None
        rows = tiers_for(m)
        cal[c] = {'m': m, 'rows': rows}
        if rows is None:
            fallback.append(c)
    # Companies without laborers or recipe data (art academies, electrics) take the median company's numbers.
    have = sorted((v for v in cal.values() if v['rows']), key=lambda v: v['rows'][2]['x'])
    median = have[len(have) // 2]['rows']
    for c in fallback:
        cal[c]['rows'] = median
        cal[c]['fallback'] = True
    for c, v in cal.items():
        v['tiers'] = rounded(v['rows'])
        m = v['m']
        # The AI's column: People where the input bill is small against value added, Equipment where it is large.
        v['ai'] = 2 if (not m or m['O'] - m['I'] >= m['I']) else 1
    return cal


def calibration_md(cal, comps):
    lines = ['# Company Culture calibration (generated by tools/pmr/company_culture.py)', '',
             'Per company: the average level of its building types over their PMR recipes (jobs, laborer jobs, input '
             'and output value at base prices per week), then each tier of People (laborer jobs cut, engineer jobs '
             'added per level) with its productivity gain (the same goods from fewer jobs), and the Equipment input '
             'cut that adds as much value added at base prices. Where that cut would pass '
             f'{INPUT_CUT_MAX:.0%} at tier III, the Equipment column is scaled down and gains less ("Equipment gain"). '
             '"AI" is the column AI companies take. Companies marked * have no laborers or no recipe data and use the '
             'median company\'s numbers.', '',
             '| Company | Building types | Jobs | Laborers | Inputs £ | Outputs £ | People I / II / III | '
             'Equipment I / II / III | People gain | Equipment gain | AI |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for c in sorted(cal):
        v = cal[c]
        m = v['m'] or {}
        t = v['tiers']
        people = ' / '.join(f"-{r['l']:.0%} lab +{r['a']} eng" for r in t)
        equip = ' / '.join(f"-{r['x'] * 100:.1f}%" for r in t)
        gain = ' / '.join(f"+{r['p'] * 100:.1f}%" for r in t)
        egain = ' / '.join(f"+{r['e'] * 100:.1f}%" for r in t)
        lines.append(f"| {c}{' *' if v.get('fallback') else ''} | {', '.join(b[len('building_'):] for b in comps[c])} | "
                     f"{m.get('W', 0):.0f} | {m.get('Lab', 0):.0f} | {m.get('I', 0):.0f} | {m.get('O', 0):.0f} | "
                     f"{people} | {equip} | {gain} | {egain} | {'Equipment' if v['ai'] == 1 else 'People'} |")
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------------------------------------------
# Traits

def trait_key(line, company, t):
    return f'pmr_cc_sc_{t}' if line == 'sc' else f'pmr_cc_{line}_{short(company)}_{t}'


def trait(key, icon, mods):
    body = ''.join(f'\t\t{k} = {v}\n' for k, v in mods)
    return (f'{key} = {{\n\ttype = condition\n\ttexture = "{TRAIT_ICON.format(icon)}"\n\n'
            f'\texecutive_modifier = {{\n{body}\t}}\n\n'
            '\tpossible = { always = no }\n\tweight = { value = 0 }\n\tvalue = 0\n}\n')


def fmt(x):
    s = f'{x:.4f}'.rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'


def traits(cal):
    out = ['# Company Culture traits (company_culture.py). Each sits on a company\'s executive; its executive_modifier\n'
           '# applies to the building levels that company owns. Never random (possible no, weight 0, value 0).\n\n']
    icons = {key: icons for _c, key, _n, _names, icons in LINES}
    for t in (1, 2, 3):
        out.append(trait(trait_key('sc', None, t), icons['sc'][t - 1], [('building_throughput_add', fmt(THROUGHPUT[t - 1]))]))
    for c in sorted(cal):
        for t, r in enumerate(cal[c]['tiers'], 1):
            out.append(trait(trait_key('eq', c, t), icons['eq'][t - 1], [('building_goods_input_mult', fmt(-r['x']))]))
            out.append(trait(trait_key('pp', c, t), icons['pp'][t - 1],
                             [('building_employment_laborers_mult', fmt(-r['l'])),
                              ('building_employment_engineers_add', fmt(r['a']))]))
    return '\n'.join(out)


MODIFIER_TYPES = '''# Dynamic modifier types vanilla 1.14.5 does not define (the exe has the pattern building_employment_{}_mult; the
# Hudson's Bay probe confirmed this one in game, 2026-10-14).
building_employment_laborers_mult = {
	decimals = 0
	color = neutral
	percent = yes
	game_data = { ai_value = 0 }
}
'''


# ---------------------------------------------------------------------------------------------------------------
# Script

def ladder(trigger, steps, var, ind):
    """if/else_if chain setting local variable var to the first step whose trigger holds."""
    out = ''
    for i, (n, val) in enumerate(steps):
        kw = 'if' if i == 0 else 'else_if'
        out += f'{ind}{kw} = {{ limit = {{ {trigger} >= {n} }} set_local_variable = {{ name = {var} value = {fmt(val)} }} }}\n'
    return out


def log_line(rec, extra=''):
    return ('debug_log = "PMR;rec=' + rec + ';date=[TimeKeeper.GetCurrentDate.GetString];'
            'company=[THIS.GetCompany.GetNameNoFormatting];' + extra +
            "level=[THIS.Var('pmr_cc_level').GetValue|0];pts=[THIS.Var('pmr_cc_pts').GetValue|0];"
            "funds=[THIS.Var('pmr_cc_funds').GetValue|0];cost=[THIS.Var('pmr_cc_cost').GetValue|0];"
            "rate=[THIS.Var('pmr_cc_rate').GetValue|1];eq=[THIS.Var('pmr_cc_eq').GetValue|0];"
            "pp=[THIS.Var('pmr_cc_pp').GetValue|0];sc=[THIS.Var('pmr_cc_sc').GetValue|0]\"")


def player_log(rec, extra=''):
    return f'if = {{ limit = {{ owner = {{ is_player = yes }} }} {log_line(rec, extra)} }}'


NUMBERS = ('x', 'l', 'a', 'p', 'e')     # per company and tier, from calibrate() (tiers_for)
MIRRORED = (['pmr_cc_level', 'pmr_cc_pts', 'pmr_cc_funds', 'pmr_cc_cost', 'pmr_cc_rate', 'pmr_cc_pct', 'pmr_cc_mo',
             'pmr_cc_prosp', 'pmr_cc_size']
            + [f'pmr_cc_{k}' for _c, k, *_r in LINES]
            + [f'pmr_cc_pick_{k}' for _c, k, *_r in LINES]
            + [f'pmr_cc_st_{k}_{t}' for _c, k, *_r in LINES for t in (1, 2, 3)]
            + [f'pmr_cc_{n}{t}' for n in NUMBERS for t in (1, 2, 3)])


def effects(cal):
    o = []
    o.append('# Company Culture (company_culture.py). Company scope unless said otherwise. Variables on the company:\n'
             '# pmr_cc_on (calibration version), pmr_cc_funds, pmr_cc_level, pmr_cc_pts (unspent), pmr_cc_cost (funds for\n'
             '# the next point), pmr_cc_rate (funds last month), pmr_cc_eq / pp / sc (tier bought, 0-3),\n'
             '# pmr_cc_x/l/a/p/e1..3 (this company\'s numbers, from calibrate()).\n'
             '# Everything the tab shows is mirrored onto the executive (pmr_cc_mirror), which also holds pmr_cc_of, the\n'
             '# company its traits were set for.\n\n')
    # Init: the company's own numbers, by company type.
    chain = ''
    for i, c in enumerate(sorted(cal)):
        kw = 'if' if i == 0 else 'else_if'
        sets = ''.join(f'set_variable = {{ name = pmr_cc_{n}{t} value = {fmt(r[k])} }} '
                       for t, r in enumerate(cal[c]['tiers'], 1)
                       for n in NUMBERS for k in (n,))
        chain += (f'\t{kw} = {{\n\t\tlimit = {{ is_company_type = company_type:{c} }}\n'
                  f'\t\t{sets}\n\t\tset_variable = {{ name = pmr_cc_ail value = {cal[c]["ai"]} }}\n\t}}\n')
    median = sorted(cal.values(), key=lambda v: v['tiers'][2]['x'])[len(cal) // 2]['tiers']
    dsets = ''.join(f'set_variable = {{ name = pmr_cc_{n}{t} value = {fmt(r[k])} }} '
                    for t, r in enumerate(median, 1) for n in NUMBERS for k in (n,))
    o.append('# A company seen for the first time, or after CAL_VERSION changed: zero state where missing, the\n'
             '# company\'s numbers, its first cost. A company type PMR does not know (another mod) takes the median.\n'
             'pmr_cc_init = {\n'
             + ''.join(f'\tif = {{ limit = {{ NOT = {{ has_variable = {v} }} }} set_variable = {{ name = {v} value = 0 }} }}\n'
                       for v in ('pmr_cc_funds', 'pmr_cc_level', 'pmr_cc_pts', 'pmr_cc_rate', 'pmr_cc_eq',
                                 'pmr_cc_pp', 'pmr_cc_sc'))
             + chain + f'\telse = {{\n\t\t{dsets}\n\t\tset_variable = {{ name = pmr_cc_ail value = 2 }}\n\t}}\n'
             '\tif = {\n\t\tlimit = { NOT = { has_variable = pmr_cc_ai } }\n'
             '\t\t# the AI\'s column, a quarter of the time the other one\n'
             '\t\trandom_list = {\n\t\t\t3 = { set_variable = { name = pmr_cc_ai value = var:pmr_cc_ail } }\n'
             '\t\t\t1 = {\n\t\t\t\tif = { limit = { var:pmr_cc_ail = 1 } set_variable = { name = pmr_cc_ai value = 2 } }\n'
             '\t\t\t\telse = { set_variable = { name = pmr_cc_ai value = 1 } }\n\t\t\t}\n\t\t}\n\t}\n'
             f'\tset_variable = {{ name = pmr_cc_on value = {CAL_VERSION} }}\n'
             '\tpmr_cc_set_cost = yes\n}\n\n')
    # Cost of the next point.
    costs = ''.join(f'\t{"if" if L == 0 else "else_if"} = {{ limit = {{ var:pmr_cc_level <= {L} }} '
                    f'set_variable = {{ name = pmr_cc_cost value = {point_cost(L)} }} }}\n' for L in range(MAX_LEVEL))
    o.append('# Funds for the next point: 100 x (level + 1)^1.8 + 700, HoI4\'s curve.\n'
             'pmr_cc_set_cost = {\n' + costs
             + f'\telse = {{ set_variable = {{ name = pmr_cc_cost value = {point_cost(MAX_LEVEL)} }} }}\n}}\n\n')
    # Earning.
    o.append('# Monthly funds: prosperity x size, size = 1 + employed levels / 50 (at most 2), both read by ladder.\n'
             '# One point a month at most: the cheapest point costs more than a month can earn (800 > 200).\n'
             'pmr_cc_earn = {\n\tset_local_variable = { name = pmr_cc_p value = 0 }\n'
             + ladder('company_prosperity', [(n, n) for n in PROSPERITY_LADDER], 'pmr_cc_p', '\t')
             + '\tset_local_variable = { name = pmr_cc_s value = 1 }\n'
             + ladder('company_employed_levels', SIZE_LADDER, 'pmr_cc_s', '\t')
             + '\tset_variable = { name = pmr_cc_prosp value = local_var:pmr_cc_p }\n'
             '\tset_variable = { name = pmr_cc_size value = local_var:pmr_cc_s }\n'
             '\tset_variable = { name = pmr_cc_rate value = local_var:pmr_cc_p }\n'
             '\tchange_variable = { name = pmr_cc_rate multiply = local_var:pmr_cc_s }\n'
             '\tchange_variable = { name = pmr_cc_funds add = var:pmr_cc_rate }\n'
             '\tif = {\n\t\tlimit = { var:pmr_cc_funds >= var:pmr_cc_cost }\n'
             '\t\tchange_variable = { name = pmr_cc_funds subtract = var:pmr_cc_cost }\n'
             '\t\tchange_variable = { name = pmr_cc_level add = 1 }\n'
             '\t\tchange_variable = { name = pmr_cc_pts add = 1 }\n'
             '\t\tpmr_cc_set_cost = yes\n'
             f'\t\t{player_log("CC_POINT")}\n\t}}\n}}\n\n')
    # Triggers are in scripted triggers; buying.
    o.append('# Buy the next tier of line $L$ (eq, pp, sc): its cost in points, the tier, the traits.\n'
             'pmr_cc_buy = {\n'
             '\tif = { limit = { var:pmr_cc_$L$ = 0 } change_variable = { name = pmr_cc_pts subtract = 1 } }\n'
             '\telse_if = { limit = { var:pmr_cc_$L$ = 1 } change_variable = { name = pmr_cc_pts subtract = 2 } }\n'
             '\telse = { change_variable = { name = pmr_cc_pts subtract = 3 } }\n'
             '\tchange_variable = { name = pmr_cc_$L$ add = 1 }\n'
             '\tsave_scope_as = pmr_cc_co\n\tpmr_cc_apply = yes\n'
             f'\t{player_log("CC_BUY", "line=$L$;")}\n}}\n\n')
    # A click (scope:line from the GUI).
    click = ''
    for code, k, *_r in LINES:
        click += (f'\t{"if" if code == 1 else "else_if"} = {{\n'
                  f'\t\tlimit = {{\n\t\t\tscope:line = {code}\n\t\t\tpmr_cc_open_{k} = yes\n\t\t\tpmr_cc_afford = {{ L = {k} }}\n\t\t}}\n'
                  f'\t\tpmr_cc_buy = {{ L = {k} }}\n\t}}\n')
    o.append('# The player clicked the next node of line scope:line (1 Equipment, 2 People, 3 Scale): it is bought with\n'
             '# points already earned, or nothing happens (Pat 12:37Z: no queue).\n'
             'pmr_cc_click = {\n\tsave_scope_as = pmr_cc_co\n' + click + '\tpmr_cc_mirror = yes\n}\n\n')
    # AI.
    ai_line = ('\t\tif = {\n\t\t\tlimit = {\n\t\t\t\tpmr_cc_open_$L$ = yes\n\t\t\t\tpmr_cc_afford = { L = $L$ }\n'
               '\t\t\t\tvar:pmr_cc_$L$ <= var:pmr_cc_sc\n\t\t\t}\n\t\t\tpmr_cc_buy = { L = $L$ }\n\t\t}\n'
               '\t\telse_if = {\n\t\t\tlimit = { pmr_cc_open_sc = yes pmr_cc_afford = { L = sc } }\n'
               '\t\t\tpmr_cc_buy = { L = sc }\n\t\t}\n'
               '\t\telse_if = {\n\t\t\tlimit = { pmr_cc_open_$L$ = yes pmr_cc_afford = { L = $L$ } }\n'
               '\t\t\tpmr_cc_buy = { L = $L$ }\n\t\t}\n')
    o.append('# AI companies (Pat 04:00Z: yes) buy as soon as they can, their column (pmr_cc_ai) and Scale in turn.\n'
             'pmr_cc_ai_line = {\n\tif = {\n\t\tlimit = { var:pmr_cc_pts >= 1 }\n' + ai_line + '\t}\n}\n\n'
             'pmr_cc_ai_buy = {\n'
             '\tif = { limit = { var:pmr_cc_ai = 1 } pmr_cc_ai_line = { L = eq } pmr_cc_ai_line = { L = eq } }\n'
             '\telse = { pmr_cc_ai_line = { L = pp } pmr_cc_ai_line = { L = pp } }\n}\n\n')
    # Traits.
    line_fx = ('\tif = {\n\t\tlimit = { scope:pmr_cc_co = { var:pmr_cc_$L$ >= 3 } }\n'
               '\t\tif = { limit = { has_trait = $T1$ } remove_trait = $T1$ }\n'
               '\t\tif = { limit = { has_trait = $T2$ } remove_trait = $T2$ }\n'
               '\t\tif = { limit = { NOT = { has_trait = $T3$ } } add_trait = $T3$ }\n\t}\n'
               '\telse_if = {\n\t\tlimit = { scope:pmr_cc_co = { var:pmr_cc_$L$ = 2 } }\n'
               '\t\tif = { limit = { has_trait = $T1$ } remove_trait = $T1$ }\n'
               '\t\tif = { limit = { has_trait = $T3$ } remove_trait = $T3$ }\n'
               '\t\tif = { limit = { NOT = { has_trait = $T2$ } } add_trait = $T2$ }\n\t}\n'
               '\telse_if = {\n\t\tlimit = { scope:pmr_cc_co = { var:pmr_cc_$L$ = 1 } }\n'
               '\t\tif = { limit = { has_trait = $T2$ } remove_trait = $T2$ }\n'
               '\t\tif = { limit = { has_trait = $T3$ } remove_trait = $T3$ }\n'
               '\t\tif = { limit = { NOT = { has_trait = $T1$ } } add_trait = $T1$ }\n\t}\n'
               '\telse = {\n'
               '\t\tif = { limit = { has_trait = $T1$ } remove_trait = $T1$ }\n'
               '\t\tif = { limit = { has_trait = $T2$ } remove_trait = $T2$ }\n'
               '\t\tif = { limit = { has_trait = $T3$ } remove_trait = $T3$ }\n\t}\n')
    o.append('# Character scope (the executive), scope:pmr_cc_co the company: the trait of line $L$ for its tier, the\n'
             '# other tiers removed.\npmr_cc_line = {\n' + line_fx + '}\n\n')
    apply_chain = ''
    for i, c in enumerate(sorted(cal)):
        kw = 'if' if i == 0 else 'else_if'
        t = {k: [trait_key(k, c, n) for n in (1, 2, 3)] for k in ('eq', 'pp')}
        apply_chain += (f'\t\t{kw} = {{\n\t\t\tlimit = {{ scope:pmr_cc_co = {{ is_company_type = company_type:{c} }} }}\n'
                        f'\t\t\tpmr_cc_line = {{ L = eq T1 = {t["eq"][0]} T2 = {t["eq"][1]} T3 = {t["eq"][2]} }}\n'
                        f'\t\t\tpmr_cc_line = {{ L = pp T1 = {t["pp"][0]} T2 = {t["pp"][1]} T3 = {t["pp"][2]} }}\n\t\t}}\n')
    o.append('# The executive\'s traits for the company\'s tiers. scope:pmr_cc_co is the company. An executive who came\n'
             '# from another company with Culture traits loses them first (pmr_cc_strip).\n'
             'pmr_cc_apply = {\n\texecutive ?= {\n'
             '\t\tif = {\n\t\t\tlimit = {\n\t\t\t\thas_variable = pmr_cc_of\n\t\t\t\tNOT = { var:pmr_cc_of ?= scope:pmr_cc_co }\n\t\t\t}\n'
             '\t\t\tpmr_cc_strip = yes\n\t\t}\n'
             '\t\tset_variable = { name = pmr_cc_of value = scope:pmr_cc_co }\n'
             + apply_chain +
             '\t\tpmr_cc_line = { L = sc T1 = pmr_cc_sc_1 T2 = pmr_cc_sc_2 T3 = pmr_cc_sc_3 }\n\t}\n}\n\n')
    strip = ''.join(f'\tif = {{ limit = {{ has_trait = {trait_key(k, c, t)} }} remove_trait = {trait_key(k, c, t)} }}\n'
                    for c in sorted(cal) for k in ('eq', 'pp') for t in (1, 2, 3))
    strip += ''.join(f'\tif = {{ limit = {{ has_trait = pmr_cc_sc_{t} }} remove_trait = pmr_cc_sc_{t} }}\n' for t in (1, 2, 3))
    o.append('# Character scope: every Company Culture trait off. Runs only when an executive changes company and on\n'
             '# disbanding (Pat 04:00Z: a disbanded company loses its bonuses).\n'
             'pmr_cc_strip = {\n' + strip + '\tremove_variable = pmr_cc_of\n}\n\n')
    # Node states for the tab.
    states = ''
    for code, k, *_r in LINES:
        other = EXCLUSIVE.get(k)
        excl = f'var:pmr_cc_{other} > 0' if other else 'always = no'
        states += f'\tset_variable = {{ name = pmr_cc_pick_{k} value = 0 }}\n'
        for t in (1, 2, 3):
            st = f'pmr_cc_st_{k}_{t}'
            states += (f'\tif = {{ limit = {{ var:pmr_cc_{k} >= {t} }} set_variable = {{ name = {st} value = 4 }} }}\n'
                       f'\telse_if = {{ limit = {{ {excl} }} set_variable = {{ name = {st} value = 5 }} }}\n'
                       f'\telse_if = {{\n\t\tlimit = {{ var:pmr_cc_{k} = {t - 1} }}\n'
                       f'\t\tif = {{ limit = {{ var:pmr_cc_pts >= {TIER_COST[t - 1]} }} '
                       f'set_variable = {{ name = {st} value = 1 }} set_variable = {{ name = pmr_cc_pick_{k} value = 1 }} }}\n'
                       f'\t\telse = {{ set_variable = {{ name = {st} value = 2 }} }}\n\t}}\n'
                       f'\telse = {{ set_variable = {{ name = {st} value = 0 }} }}\n')
    copies = ''.join(f'\t\tif = {{ limit = {{ scope:pmr_cc_co = {{ has_variable = {v} }} }} '
                     f'set_variable = {{ name = {v} value = scope:pmr_cc_co.var:{v} }} }}\n'
                     f'\t\telse_if = {{ limit = {{ has_variable = {v} }} remove_variable = {v} }}\n' for v in MIRRORED)
    o.append('# The tab\'s numbers, mirrored onto the executive (the panel reads Company.GetExecutive.MakeScope). Node states\n'
             '# pmr_cc_st_<line>_<tier>: 0 a later tier, 1 next and affordable (a click buys it), 2 next but not enough\n'
             '# points yet, 4 bought, 5 ruled out by the other column. pmr_cc_pick_<line>: the line\'s next node can be bought.\n'
             'pmr_cc_mirror = {\n\tsave_scope_as = pmr_cc_co\n'
             + states +
             '\tset_variable = { name = pmr_cc_pct value = var:pmr_cc_funds }\n'
             '\tchange_variable = { name = pmr_cc_pct multiply = 100 }\n'
             '\tchange_variable = { name = pmr_cc_pct divide = var:pmr_cc_cost }\n'
             '\tif = {\n\t\tlimit = { var:pmr_cc_rate > 0 }\n'
             '\t\tset_variable = { name = pmr_cc_mo value = var:pmr_cc_cost }\n'
             '\t\tchange_variable = { name = pmr_cc_mo subtract = var:pmr_cc_funds }\n'
             '\t\tchange_variable = { name = pmr_cc_mo divide = var:pmr_cc_rate }\n'
             '\t\tchange_variable = { name = pmr_cc_mo add = 0.99 }\n'
             '\t\tround_variable = { name = pmr_cc_mo nearest = 1 }\n\t}\n'
             '\telse = { set_variable = { name = pmr_cc_mo value = -1 } }\n'
             '\texecutive ?= {\n' + copies + '\t}\n}\n\n')
    o.append('# Monthly, every company in the world (from each country\'s monthly pulse).\n'
             'pmr_cc_tick = {\n\tsave_scope_as = pmr_cc_co\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:pmr_cc_on ?= {CAL_VERSION} }} }}\n\t\tpmr_cc_init = yes\n\t}}\n'
             '\tpmr_cc_earn = yes\n'
             '\tif = {\n\t\tlimit = { owner = { is_player = no } }\n\t\tpmr_cc_ai_buy = yes\n\t}\n'
             '\tsave_scope_as = pmr_cc_co\n'
             '\tif = {\n\t\tlimit = { executive ?= { NOT = { var:pmr_cc_of ?= scope:pmr_cc_co } } }\n\t\tpmr_cc_apply = yes\n\t}\n'
             '\tpmr_cc_mirror = yes\n'
             f'\t{player_log("CC")}\n}}\n\n')
    o.append('# The tab was opened, a company was founded or the game started: bring it up to date without earning.\n'
             'pmr_cc_refresh = {\n\tsave_scope_as = pmr_cc_co\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:pmr_cc_on ?= {CAL_VERSION} }} }}\n\t\tpmr_cc_init = yes\n\t}}\n'
             '\tif = {\n\t\tlimit = { executive ?= { NOT = { var:pmr_cc_of ?= scope:pmr_cc_co } } }\n\t\tpmr_cc_apply = yes\n\t}\n'
             '\tpmr_cc_mirror = yes\n}\n\n')
    o.append('# Character scope (an executive, from the tab): the owner\'s company this character runs, scope:line kept.\n'
             'pmr_cc_with_company = {\n\tsave_scope_as = pmr_cc_exec\n'
             '\towner ?= {\n\t\tevery_company = {\n\t\t\tlimit = { executive ?= scope:pmr_cc_exec }\n\t\t\t$EFFECT$ = yes\n\t\t}\n\t}\n}\n\n')
    return ''.join(o)


def triggers():
    o = ['# Company Culture (company_culture.py). Company scope.\n\n'
         '# pmr_cc_open_<line>: the line has a tier left to buy and, for Equipment and People, the other column is\n'
         '# untouched (Pat 04:00Z: the first tier bought locks the company to its column).\n']
    for code, k, *_r in LINES:
        other = EXCLUSIVE.get(k)
        excl = f'\tvar:pmr_cc_{other} = 0\n' if other else ''
        o.append(f'pmr_cc_open_{k} = {{\n\tvar:pmr_cc_{k} < 3\n{excl}}}\n\n')
    o.append('# The points for line $L$\'s next tier (1, 2, 3).\n'
             'pmr_cc_afford = {\n\tOR = {\n'
             '\t\tAND = { var:pmr_cc_$L$ = 0 var:pmr_cc_pts >= 1 }\n'
             '\t\tAND = { var:pmr_cc_$L$ = 1 var:pmr_cc_pts >= 2 }\n'
             '\t\tAND = { var:pmr_cc_$L$ = 2 var:pmr_cc_pts >= 3 }\n\t}\n}\n\n')
    return ''.join(o)


def sguis():
    picks = ''.join(f'\t\t\tAND = {{ scope:line = {code} var:pmr_cc_pick_{k} ?= 1 }}\n' for code, k, *_r in LINES)
    return ('# Company Culture tab (company_culture.py). Character scope: the company\'s executive, as the panel reads\n'
            '# Company.GetExecutive.MakeScope. scope:line is the column clicked (1 Equipment, 2 People, 3 Scale).\n\n'
            'pmr_cc_pick_sgui = {\n\tscope = character\n\tsaved_scopes = { line }\n'
            '\tis_valid = {\n\t\towner ?= { is_player = yes }\n\t\tOR = {\n' + picks + '\t\t}\n\t}\n'
            '\teffect = {\n\t\tpmr_cc_with_company = { EFFECT = pmr_cc_click }\n\t}\n}\n\n'
            '# Opening the tab, or its Show button while the executive has no numbers yet (a new executive this month,\n'
            '# a save from before Company Culture), brings the company up to date.\n'
            'pmr_cc_refresh_sgui = {\n\tscope = character\n'
            '\teffect = {\n\t\tpmr_cc_with_company = { EFFECT = pmr_cc_refresh }\n\t}\n}\n')


ON_ACTIONS = '''# Company Culture (company_culture.py). Appended to vanilla on_actions the documented way.
on_game_started_after_lobby = { on_actions = { pmr_cc_game_started } }
on_monthly_pulse_country = { on_actions = { pmr_cc_monthly_country } }
on_company_established = { on_actions = { pmr_cc_on_company_established } }
on_company_disbanded = { on_actions = { pmr_cc_on_company_disbanded } }

# No root. Every company's numbers and tab from the first day, before any monthly pulse (in game 12:37Z the Hudson's
# Bay Company's tab read 0 / 0 with nothing to click until a month had passed).
pmr_cc_game_started = {
	effect = {
		every_country = {
			every_company = {
				pmr_cc_refresh = yes
			}
		}
	}
}

# Root = country. Every company earns, buys (AI companies) and keeps its executive's traits.
pmr_cc_monthly_country = {
	effect = {
		every_company = {
			pmr_cc_tick = yes
		}
	}
}

# Root = country, scope:company = the company founded: its numbers and tab at once.
pmr_cc_on_company_established = {
	effect = {
		scope:company ?= {
			pmr_cc_refresh = yes
		}
	}
}

# Root = country, scope:company = the company disbanded: its executive loses its Culture traits (Pat 04:00Z).
pmr_cc_on_company_disbanded = {
	effect = {
		scope:company ?= {
			executive ?= {
				pmr_cc_strip = yes
			}
		}
	}
}
'''

# Test build only: a point takes a company of prosperity 50 about fifteen months, too slow to try the tree.
TEST_POINTS = 6
TEST_DECISION = f'''# Company Culture test decision (test builds only). The AI never takes it. Gives each of the player's companies
# {TEST_POINTS} Culture points (not levels) and refreshes its tab. Writes PMR;rec=CC_TEST lines.
pmr_cc_test_points_decision = {{
	is_shown = {{ always = yes }}
	possible = {{ always = yes }}
	when_taken = {{
		every_company = {{
			save_scope_as = pmr_cc_co
			if = {{
				limit = {{ NOT = {{ var:pmr_cc_on ?= {CAL_VERSION} }} }}
				pmr_cc_init = yes
			}}
			change_variable = {{ name = pmr_cc_pts add = {TEST_POINTS} }}
			if = {{
				limit = {{ executive ?= {{ NOT = {{ var:pmr_cc_of ?= scope:pmr_cc_co }} }} }}
				pmr_cc_apply = yes
			}}
			pmr_cc_mirror = yes
			{{LOG}}
		}}
	}}
	ai_chance = {{ value = 0 }}
}}
'''


# ---------------------------------------------------------------------------------------------------------------
# Methods sub-heading (plan 1b, Pat 02:05Z; 04:00Z: the company's own building types)

def method_rows(report, pms, comps):
    """building type -> [(recipe key, texture, technologies)] for every PMR-treated type a company lists."""
    listed = {b for bts in comps.values() for b in bts}
    elec = {a['building']: a['electric_recipe'] for a in report['automation'] if a.get('electric_recipe')}
    rows = {}
    for t in report['treated']:
        b = t['building']
        if b not in listed:
            continue
        out, last = [], []
        for key in t['recipes']:
            if key in pms:
                tex, techs = pms[key]
                last = techs
            elif b in elec and key == elec[b]['key']:
                auto = elec[b]['automation']
                tex = pms.get(auto[0], (None, []))[0] if auto else None
                techs = sorted(set(last) | set(elec[b]['technologies']))
            else:
                fail('methods', f'{b}: no production method {key}')
            out.append((key, tex or 'gfx/interface/icons/generic_icons/mixed_icon_base.dds', techs))
        rows[b] = out
    untreated = sorted(listed - set(rows))
    return rows, untreated


def unlock_values(rows):
    out = ['# Company Culture Methods list (company_culture.py). Country scope.\n'
           '# pmr_cc_unl_<recipe>: 1 once the country has researched every technology the recipe needs.\n'
           '# pmr_cc_new_<b>: the newest recipe of the building type the country can run (its index, from 1).\n\n']
    seen = set()
    for b, recipes in sorted(rows.items()):
        for key, _tex, techs in recipes:
            if techs and key not in seen:
                seen.add(key)
                lim = ' '.join(f'has_technology_researched = {t}' for t in techs)
                out.append(f'pmr_cc_unl_{key} = {{\n\tvalue = 0\n\tif = {{\n\t\tlimit = {{ {lim} }}\n\t\tvalue = 1\n\t}}\n}}\n\n')
        body = '\tvalue = 1\n'
        for i, (key, _tex, techs) in enumerate(recipes, 1):
            if i > 1 and techs:
                lim = ' '.join(f'has_technology_researched = {t}' for t in techs)
                body += f'\tif = {{\n\t\tlimit = {{ {lim} }}\n\t\tvalue = {i}\n\t}}\n'
        out.append(f'pmr_cc_new_{b[len("building_"):]} = {{\n{body}}}\n\n')
    return ''.join(out)


# ---------------------------------------------------------------------------------------------------------------
# GUI

def V(name):
    return f"Character.MakeScope.Var('{name}').GetValue"


def EQ(name, n):
    return f"EqualTo_CFixedPoint({V(name)}, '(CFixedPoint){n}')"


def GT(name, n):
    return f"GreaterThan_CFixedPoint({V(name)}, '(CFixedPoint){n}')"


SG_SCOPE = 'GuiScope.SetRoot(Character.MakeScope)'
NODE_W, NODE_H, GAP = 168, 64, 18
LOCAL = 'Company.GetCountry.IsLocalPlayer'


def node(code, k, t, name, icon, ind):
    st = f'pmr_cc_st_{k}_{t}'
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    sg = f"GetScriptedGui('pmr_cc_pick_sgui')"
    scope = f"{SG_SCOPE}.AddScope('line', MakeScopeValue('(CFixedPoint){code}')).End"
    can = f"And({LOCAL}, And({EQ(st, 1)}, {sg}.IsValid({scope})))"

    def content(ii):
        lines = [(1, f'PMR_CC_NODE_BUY_{t}'), (2, f'PMR_CC_NODE_NEED_{t}'), (4, 'PMR_CC_NODE_OWNED'),
                 (5, f'PMR_CC_NODE_RULED_OUT_{k}'), (0, f'PMR_CC_COST_{t}')]
        out = (f'{ii}icon = {{\n{ii}\tposition = {{ 8 0 }}\n{ii}\tparentanchor = vcenter\n{ii}\tsize = {{ 44 44 }}\n'
               f'{ii}\ttexture = "{TRAIT_ICON.format(icon)}"\n{ii}\talwaystransparent = yes\n{ii}}}\n'
               f'{ii}textbox = {{\n{ii}\tposition = {{ 58 8 }}\n{ii}\tsize = {{ {NODE_W - 64} 24 }}\n'
               f'{ii}\tmultiline = no\n{ii}\talign = left|nobaseline\n{ii}\tfontsize_min = 12\n{ii}\telide = right\n'
               f'{ii}\ttext = "PMR_CC_NAME_{k}_{t}"\n{ii}\talwaystransparent = yes\n{ii}}}\n')
        for s, key in lines:
            out += (f'{ii}textbox = {{\n{ii}\tvisible = "[{EQ(st, s)}]"\n{ii}\tposition = {{ 58 34 }}\n'
                    f'{ii}\tsize = {{ {NODE_W - 64} 22 }}\n{ii}\talign = left|nobaseline\n{ii}\tusing = fontsize_small\n'
                    f'{ii}\ttext = "{key}"\n{ii}\talwaystransparent = yes\n{ii}}}\n')
        return out
    return (f'{ind}widget = {{\n{i1}size = {{ {NODE_W} {NODE_H} }}\n'
            # bought (Pat 12:37Z: the chosen tiers highlighted with a frame): a gold-tinted card inside the frame
            # vanilla draws round a selected building type (companies_panel.gui, highlighted_selected_square_selection)
            f'{i1}widget = {{\n{i2}visible = "[{EQ(st, 4)}]"\n{i2}size = {{ 100% 100% }}\n{i2}tooltip = "PMR_CC_TT_{k}_{t}"\n'
            f'{i2}background = {{\n{i3}using = entry_bg\n{i2}}}\n'
            f'{i2}icon = {{\n{i3}size = {{ 100% 100% }}\n{i3}texture = "{WHITE}"\n{i3}color = {{ 0.74 0.60 0.30 0.22 }}\n'
            f'{i3}alwaystransparent = yes\n{i2}}}\n'
            + content(i2) +
            f'{i2}icon = {{\n{i3}using = highlighted_selected_square_selection\n{i3}alwaystransparent = yes\n{i2}}}\n'
            f'{i1}}}\n'
            # every other state: a button, live only when the next tier is affordable
            f'{i1}button = {{\n{i2}visible = "[Not({EQ(st, 4)})]"\n{i2}using = default_button\n{i2}size = {{ 100% 100% }}\n'
            f'{i2}alpha = "[TransparentIfFalse(Not({EQ(st, 5)}))]"\n'
            f'{i2}enabled = "[{can}]"\n{i2}onclick = "[{sg}.Execute({scope})]"\n{i2}tooltip = "PMR_CC_TT_{k}_{t}"\n'
            + content(i2) + f'{i1}}}\n'
            f'{ind}}}\n')


def connector(ind):
    return (f'{ind}widget = {{\n{ind}\tsize = {{ {NODE_W} 12 }}\n{ind}\ticon = {{\n{ind}\t\tparentanchor = hcenter\n'
            f'{ind}\t\tsize = {{ 2 12 }}\n{ind}\t\ttexture = "{WHITE}"\n{ind}\t\tcolor = {{ 0.74 0.60 0.30 0.6 }}\n'
            f'{ind}\t\talwaystransparent = yes\n{ind}\t}}\n{ind}}}\n')


def column(code, k, title, names, icons, ind):
    i1 = ind + '\t'
    out = (f'{ind}flowcontainer = {{\n{i1}direction = vertical\n{i1}spacing = 0\n'
           f'{i1}widget = {{\n{i1}\tsize = {{ {NODE_W} 40 }}\n{i1}\ttooltip = "PMR_CC_COLUMN_TT_{k}"\n'
           f'{i1}\ticon = {{\n{i1}\t\tposition = {{ 4 0 }}\n{i1}\t\tparentanchor = vcenter\n{i1}\t\tsize = {{ 32 32 }}\n'
           f'{i1}\t\ttexture = "{COLUMN_ICONS[k]}"\n{i1}\t}}\n'
           f'{i1}\ttextbox = {{\n{i1}\t\tposition = {{ 42 0 }}\n{i1}\t\tparentanchor = vcenter\n{i1}\t\tautoresize = yes\n'
           f'{i1}\t\talign = left|nobaseline\n{i1}\t\tusing = fontsize_large\n{i1}\t\ttext = "PMR_CC_COLUMN_{k}"\n{i1}\t}}\n{i1}}}\n')
    for t in (1, 2, 3):
        out += node(code, k, t, names[t - 1], icons[t - 1], i1)
        if t < 3:
            out += connector(i1)
    return out + f'{ind}}}\n'


def text_row(key, ind, visible=None, w=520, small=False):
    vis = f'{ind}\tvisible = "[{visible}]"\n' if visible else ''
    font = f'{ind}\tusing = fontsize_small\n' if small else ''
    return (f'{ind}textbox = {{\n{vis}{ind}\tparentanchor = hcenter\n{ind}\tminimumsize = {{ {w} -1 }}\n'
            f'{ind}\tmaximumsize = {{ {w} -1 }}\n{ind}\tautoresize = yes\n{ind}\tmultiline = yes\n'
            f'{ind}\talign = left|nobaseline\n{font}{ind}\ttext = "{key}"\n{ind}}}\n')


def methods_block(b, recipes, ind):
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    sb = b[len('building_'):]
    country = 'Company.GetCountry.MakeScope'
    out = (f'{ind}flowcontainer = {{\n{i1}visible = "[ObjectsEqual(BuildingType.Self, GetBuildingType(\'{b}\').Self)]"\n'
           f'{i1}position = {{ 66 4 }}\n{i1}spacing = 6\n')
    for i, (key, tex, techs) in enumerate(recipes, 1):
        unl = (f"GreaterThan_CFixedPoint({country}.ScriptValue('pmr_cc_unl_{key}'), '(CFixedPoint)0')" if techs else None)
        newest = f"EqualTo_CFixedPoint({country}.ScriptValue('pmr_cc_new_{sb}'), '(CFixedPoint){i}')"
        share = f"GetPlayer.MakeScope.Var('pmr_c_sh_{i}_{sb}').GetValue"
        alpha = f'{i2}alpha = "[TransparentIfFalse({unl})]"\n' if unl else ''
        out += (f'{i1}widget = {{\n{i2}size = {{ 48 58 }}\n{i2}tooltip = "PMR_CC_PM_{key}"\n'
                f'{i2}icon = {{\n{i3}visible = "[{newest}]"\n{i3}size = {{ 48 48 }}\n{i3}texture = "{WHITE}"\n'
                f'{i3}color = {{ 0.74 0.60 0.30 0.55 }}\n{i3}alwaystransparent = yes\n{i2}}}\n'
                f'{i2}icon = {{\n{i3}position = {{ 4 4 }}\n{i3}size = {{ 40 40 }}\n{i3}texture = "{tex}"\n'
                + alpha.replace(i2, i3) + f'{i3}alwaystransparent = yes\n{i2}}}\n'
                f'{i2}textbox = {{\n{i3}visible = "[And({LOCAL}, GreaterThan_CFixedPoint({share}, \'(CFixedPoint)0\'))]"\n'
                f'{i3}position = {{ 0 46 }}\n{i3}size = {{ 48 14 }}\n{i3}align = hcenter|nobaseline\n{i3}using = fontsize_small\n'
                f'{i3}raw_text = "[{share}|%0]"\n{i3}alwaystransparent = yes\n{i2}}}\n{i1}}}\n')
    return out + f'{ind}}}\n'


def tab(rows, untreated):
    i1, i2, i3, i4 = '\t\t', '\t\t\t', '\t\t\t\t', '\t\t\t\t\t'
    cols = ''
    for n, (code, k, title, names, icons) in enumerate(LINES):
        cols += column(code, k, title, names, icons, i3)
        if n == 0:
            cols += (f'{i3}widget = {{\n{i4}size = {{ {GAP} 40 }}\n{i4}icon = {{\n{i4}\tparentanchor = center\n'
                     f'{i4}\tsize = {{ 18 18 }}\n{i4}\ttexture = "{EXCLUSIVE_ICON}"\n{i4}\ttooltip = "PMR_CC_EXCLUSIVE_TT"\n{i4}}}\n{i3}}}\n')
        elif n == 1:
            cols += f'{i3}widget = {{\n{i4}size = {{ {GAP} 40 }}\n{i3}}}\n'
    bar_value = f"FixedPointToFloat({V('pmr_cc_pct')})"
    # Every mirrored executive holds a cost (800 and up). Without one (a new executive this month, a save from
    # before Company Culture) the tab offers a button that reads the company in, instead of an empty tree.
    ready = GT('pmr_cc_cost', 0)
    refresh = "GetScriptedGui('pmr_cc_refresh_sgui')"
    show = (f'{i1}button = {{\n{i2}visible = "[Not({ready})]"\n{i2}parentanchor = hcenter\n{i2}using = default_button\n'
            f'{i2}size = {{ 300 40 }}\n{i2}text = "PMR_CC_SHOW"\n{i2}tooltip = "PMR_CC_SHOW_TT"\n'
            f'{i2}onclick = "[{refresh}.Execute({SG_SCOPE}.End)]"\n{i1}}}\n')
    header = (
        f'{i1}widget = {{\n{i2}visible = "[{ready}]"\n{i2}parentanchor = hcenter\n{i2}size = {{ 540 82 }}\n'
        f'{i2}background = {{\n{i3}using = entry_bg\n{i2}}}\n'
        f'{i2}textbox = {{\n{i3}position = {{ 16 10 }}\n{i3}autoresize = yes\n{i3}align = left|nobaseline\n'
        f'{i3}using = fontsize_xxl\n{i3}text = "PMR_CC_LEVEL"\n{i3}tooltip = "PMR_CC_LEVEL_TT"\n{i2}}}\n'
        f'{i2}textbox = {{\n{i3}position = {{ 16 48 }}\n{i3}autoresize = yes\n{i3}align = left|nobaseline\n'
        f'{i3}text = "PMR_CC_POINTS"\n{i3}tooltip = "PMR_CC_LEVEL_TT"\n{i2}}}\n'
        f'{i2}widget = {{\n{i3}position = {{ 220 12 }}\n{i3}size = {{ 300 30 }}\n{i3}tooltip = "PMR_CC_BAR_TT"\n'
        f'{i3}gold_progressbar_horizontal = {{\n{i4}size = {{ 100% 100% }}\n{i4}blockoverride "values" {{\n'
        f'{i4}\tmin = 0\n{i4}\tmax = 100\n{i4}\tvalue = "[{bar_value}]"\n{i4}}}\n{i3}}}\n'
        f'{i3}textbox = {{\n{i4}parentanchor = center\n{i4}autoresize = yes\n{i4}align = hcenter|nobaseline\n'
        f'{i4}text = "PMR_CC_BAR"\n{i4}alwaystransparent = yes\n{i3}}}\n{i2}}}\n'
        f'{i2}textbox = {{\n{i3}visible = "[{GT("pmr_cc_mo", 0)}]"\n{i3}position = {{ 220 50 }}\n{i3}size = {{ 300 22 }}\n'
        f'{i3}align = hcenter|nobaseline\n{i3}using = fontsize_small\n{i3}text = "PMR_CC_RATE"\n{i3}tooltip = "PMR_CC_BAR_TT"\n{i2}}}\n'
        f'{i2}textbox = {{\n{i3}visible = "[Not({GT("pmr_cc_mo", 0)})]"\n{i3}position = {{ 220 50 }}\n{i3}size = {{ 300 22 }}\n'
        f'{i3}align = hcenter|nobaseline\n{i3}using = fontsize_small\n{i3}text = "PMR_CC_RATE_NONE"\n{i3}tooltip = "PMR_CC_BAR_TT"\n{i2}}}\n'
        f'{i1}}}\n')
    tree = (f'{i1}default_header = {{\n{i2}blockoverride "text" {{\n{i3}text = "PMR_CC_TREE_HEADER"\n{i2}}}\n{i1}}}\n'
            f'{i1}flowcontainer = {{\n{i2}visible = "[{ready}]"\n{i2}parentanchor = hcenter\n{i2}direction = horizontal\n'
            f'{i2}spacing = 0\n' + cols + f'{i1}}}\n')
    methods =(f'{i1}default_header = {{\n{i2}blockoverride "text" {{\n{i3}text = "PMR_CC_METHODS_HEADER"\n{i2}}}\n{i1}}}\n'
               + text_row('PMR_CC_METHODS_INTRO', i1, small=True) +
               f'{i1}flowcontainer = {{\n{i2}parentanchor = hcenter\n{i2}direction = vertical\n{i2}spacing = 4\n'
               f'{i2}datamodel = "[Company.GetBuildingTypes]"\n{i2}item = {{\n'
               f'{i3}widget = {{\n{i4}size = {{ 540 66 }}\n{i4}background = {{\n{i4}\tusing = entry_bg\n{i4}}}\n'
               f'{i4}icon = {{\n{i4}\tposition = {{ 6 0 }}\n{i4}\tparentanchor = vcenter\n{i4}\tsize = {{ 54 54 }}\n'
               f'{i4}\ttexture = "[BuildingType.GetIcon]"\n{i4}\ttooltipwidget = {{\n{i4}\t\tFancyTooltip_BuildingType = {{}}\n{i4}\t}}\n{i4}}}\n'
               + ''.join(methods_block(b, rec, i4) for b, rec in sorted(rows.items()))
               + ''.join(f'{i4}textbox = {{\n{i4}\tvisible = "[ObjectsEqual(BuildingType.Self, GetBuildingType(\'{b}\').Self)]"\n'
                         f'{i4}\tposition = {{ 70 0 }}\n{i4}\tparentanchor = vcenter\n{i4}\tautoresize = yes\n'
                         f'{i4}\talign = left|nobaseline\n{i4}\ttext = "PMR_CC_METHODS_NONE"\n{i4}}}\n' for b in untreated)
               + f'{i3}}}\n{i2}}}\n{i1}}}\n')
    return ('# GENERATED by tools/pmr/company_culture.py\n'
            'types pmr_company_culture {\n'
            '\ttype company_panel_culture_tab = flowcontainer {\n'
            '\t\tdirection = vertical\n\t\tusing = default_list_position\n\t\tusing = default_content_fade\n'
            '\t\tspacing = 6\n\t\tmargin_bottom = 10\n\t\tminimumsize = { 540 -1 }\n'
            '\t\tdatacontext = "[Company.GetExecutive]"\n\n'
            + show + header + tree + methods +
            '\t}\n}\n')


def patch_panel(text):
    """company_panel.gui: a fourth tab, Company Culture, after Statistics."""
    where = PANEL_GUI
    anchor = '\t\t\t\tblockoverride "third_button_selected"\n\t\t\t\t{\n\t\t\t\t\ttext = "COMPANY_TAB_STATISTICS"\n\t\t\t\t}\n'
    if text.count(anchor) != 1:
        fail(where, 'the Statistics tab button block moved')
    refresh = f"GetScriptedGui('pmr_cc_refresh_sgui').Execute(GuiScope.SetRoot(Company.GetExecutive.MakeScope).End)"
    four = (
        '\n\t\t\t\t# PMR: Company Culture tab\n'
        '\t\t\t\tblockoverride "fourth_button"\n\t\t\t\t{\n\t\t\t\t\ttext = "PMR_CC_TAB"\n\t\t\t\t}\n'
        '\t\t\t\tblockoverride "fourth_button_tooltip"\n\t\t\t\t{\n\t\t\t\t\ttooltip = "PMR_CC_TAB_TT"\n\t\t\t\t}\n'
        f'\t\t\t\tblockoverride "fourth_button_click"\n\t\t\t\t{{\n\t\t\t\t\tonclick = "[InformationPanel.SelectTab(\'{TAB}\')]"\n'
        f'\t\t\t\t\tonclick = "[{refresh}]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "fourth_button_visibility"\n\t\t\t\t{{\n\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'{TAB}\')]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "fourth_button_visibility_checked"\n\t\t\t\t{{\n\t\t\t\t\tvisible = "[Not( InformationPanel.IsTabSelected(\'{TAB}\') )]"\n\t\t\t\t}}\n'
        '\t\t\t\tblockoverride "fourth_button_selected"\n\t\t\t\t{\n\t\t\t\t\ttext = "PMR_CC_TAB"\n\t\t\t\t}\n')
    text = text.replace(anchor, anchor + four)
    anchor2 = ('\t\t\t\tcompany_panel_statistics_tab = {\n'
               '\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'statistics\')]"\n\t\t\t\t}\n')
    if text.count(anchor2) != 1:
        fail(where, 'the Statistics tab contents moved')
    text = text.replace(anchor2, anchor2 + '\n\t\t\t\t# PMR: Company Culture tab\n\t\t\t\tcompany_panel_culture_tab = {\n'
                        f'\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'{TAB}\')]"\n\t\t\t\t}}\n')
    return text


# ---------------------------------------------------------------------------------------------------------------
# Text

def localization(cal, rows, pms_techs):
    def v(name, f):
        return f"[{V(name)}|{f}]"
    co = '[Company.GetNameNoFormatting]'
    loc = [
        ' PMR_CC_TAB:0 "Company Culture"',
        ' PMR_CC_TAB_TT:0 "#header Company Culture#!\\nWhat this company has learned to do better. Its prosperity earns Culture points, and points buy bonuses for every building level it owns."',
        f' PMR_CC_LEVEL:0 "Culture Level #v {v("pmr_cc_level", 0)}#!"',
        f' PMR_CC_POINTS:0 "#v {v("pmr_cc_pts", 0)}#! points to spend"',
        ' PMR_CC_LEVEL_TT:0 "#header Culture points#!\\nA company earns Culture points from its prosperity. Each point buys one tier of a column below; a tier costs as many points as its number (1, 2 or 3). The bonuses apply to the building levels this company owns, in proportion where it owns part of a building."',
        f' PMR_CC_BAR:0 "#v {v("pmr_cc_funds", 0)}#! / {v("pmr_cc_cost", 0)}"',
        f' PMR_CC_BAR_TT:0 "#header Next Culture point#!\\nEach month this company earns its prosperity (#v {v("pmr_cc_prosp", 0)}#!) times its size (#v ×{v("pmr_cc_size", 1)}#!, from its employed levels: one more tenth per 5 levels, at most ×2), so #v +{v("pmr_cc_rate", 0)}#! a month.\\n\\nA full bar gives one point and one Culture level, and each level needs more than the last."',
        f' PMR_CC_RATE:0 "+{v("pmr_cc_rate", 0)} a month, next point in about {v("pmr_cc_mo", 0)} months"',
        ' PMR_CC_RATE_NONE:0 "Earning nothing while its prosperity is 0"',
        ' PMR_CC_TREE_HEADER:0 "Culture"',
        ' PMR_CC_EXCLUSIVE_TT:0 "#header Equipment or People#!\\nA company focuses on its machinery or on its people. The first Equipment or People tier it buys rules out the other column."',
        ' PMR_CC_SHOW:0 "Show Company Culture"',
        ' PMR_CC_SHOW_TT:0 "This company\'s Culture has not been read in yet (a new executive this month, or a game started before Company Culture). Click to bring it up to date; it also updates on its own at the start of each month."',
        ' PMR_CC_COLUMN_eq:0 "Equipment"',
        ' PMR_CC_COLUMN_pp:0 "People"',
        ' PMR_CC_COLUMN_sc:0 "Scale"',
        ' PMR_CC_COLUMN_TT_eq:0 "#header Equipment#!\\nThe company invests in its machinery: every level it owns needs fewer input goods.\\n\\nEach tier raises productivity about as much as the People tier beside it, at base prices for this company\'s buildings, or less where inputs are so cheap that the cut would pass 20%. Rules out People."',
        ' PMR_CC_COLUMN_TT_pp:0 "#header People#!\\nThe company invests in its workforce: fewer laborer jobs on every level it owns, and a few engineer jobs in their place, so fewer jobs in all.\\n\\nEngineer jobs left empty lower output like any unfilled job. Rules out Equipment."',
        ' PMR_CC_COLUMN_TT_sc:0 "#header Scale#!\\nMore throughput on every level the company owns."',
        ' PMR_CC_NODE_OWNED:0 "#v Bought#!"',
        ' PMR_CC_NODE_RULED_OUT_eq:0 "Ruled out by People"',
        ' PMR_CC_NODE_RULED_OUT_pp:0 "Ruled out by Equipment"',
        ' PMR_CC_NODE_RULED_OUT_sc:0 ""',
        ' PMR_CC_METHODS_HEADER:0 "Methods"',
        ' PMR_CC_METHODS_INTRO:0 "Every recipe of this company\'s buildings, oldest to newest. Greyed: not yet researched. Gold: the newest one the country can run, which its levels retool to. Under each, the share of your levels running it."',
        ' PMR_CC_METHODS_NONE:0 "No recipes to retool"',
        f' pmr_cc_test_points_decision:0 "PMR test: {TEST_POINTS} Culture points for each of your companies"',
        f' pmr_cc_test_points_decision_desc:0 "Gives every company of yours {TEST_POINTS} Culture points to spend and refreshes its Company Culture tab, so the tree can be tried without waiting. Levels do not change."',
        ' building_employment_laborers_mult:0 "Laborer jobs"',
        ' building_employment_laborers_mult_desc:0 "Change to the laborer jobs of each building level."',
    ]
    for t in (1, 2, 3):
        pts = 'point' if t == 1 else 'points'
        loc += [f' PMR_CC_COST_{t}:0 "{t} {pts}"',
                f' PMR_CC_NODE_BUY_{t}:0 "#P Buy#!: {t} {pts}"',
                f' PMR_CC_NODE_NEED_{t}:0 "Needs {t} {pts}"']
    names = {k: n for _c, k, _col, n, _i in LINES}
    roman = ('I', 'II', 'III')
    for t in (1, 2, 3):
        x, l, a, p, e = (v(f'pmr_cc_x{t}', '%1'), v(f'pmr_cc_l{t}', '%0'), v(f'pmr_cc_a{t}', 0),
                         v(f'pmr_cc_p{t}', '%1'), v(f'pmr_cc_e{t}', '%1'))
        cut = int(JOB_CUT[t - 1] * 100)
        pts = 'point' if t == 1 else 'points'
        thr = int(THROUGHPUT[t - 1] * 100)
        loc += [
            f' PMR_CC_NAME_eq_{t}:0 "{names["eq"][t - 1]}"',
            f' PMR_CC_NAME_pp_{t}:0 "{names["pp"][t - 1]}"',
            f' PMR_CC_NAME_sc_{t}:0 "{names["sc"][t - 1]}"',
            f' PMR_CC_TT_eq_{t}:0 "#header {names["eq"][t - 1]}#!\\nEvery level {co} owns uses #v {x}#! fewer input goods.\\n\\n'
            f'About #v +{e}#! productivity at base prices ({names["pp"][t - 1]}: +{p}).\\n\\n'
            f'Costs #v {t}#! {pts}. Equipment rules out People for this company."',
            f' PMR_CC_TT_pp_{t}:0 "#header {names["pp"][t - 1]}#!\\nEvery level {co} owns has #v {l}#! fewer laborer jobs and #v {a}#! more engineer jobs: about {cut}% fewer jobs in all, so about #v +{p}#! productivity ({names["eq"][t - 1]}: +{e} at base prices). Engineer jobs left empty lower output like any unfilled job.\\n\\n'
            f'Costs #v {t}#! {pts}. People rules out Equipment for this company."',
            f' PMR_CC_TT_sc_{t}:0 "#header {names["sc"][t - 1]}#!\\nEvery level {co} owns has #v +{thr}%#! throughput in all.\\n\\nCosts #v {t}#! {pts}."',
        ]
    desc = {'eq': 'Company Culture, Equipment: the levels this executive\'s company owns use fewer input goods.',
            'pp': 'Company Culture, People: the levels this executive\'s company owns need fewer laborers and some engineers.',
            'sc': 'Company Culture, Scale: the levels this executive\'s company owns produce more.'}
    for t in (1, 2, 3):
        loc += [f' pmr_cc_sc_{t}:0 "{names["sc"][t - 1]}"', f' pmr_cc_sc_{t}_desc:0 "{desc["sc"]}"']
        for c in sorted(cal):
            for k in ('eq', 'pp'):
                key = trait_key(k, c, t)
                loc += [f' {key}:0 "{names[k][t - 1]}"', f' {key}_desc:0 "{desc[k]}"']
    done = set()
    for b, recipes in rows.items():
        for key, _tex, techs in recipes:
            if key in done:
                continue
            done.add(key)
            need = (('Needs ' + ', '.join(f'${tk}$' for tk in techs) + '.') if techs else 'Available from the start.')
            if key.startswith('pm_pmr_elec_'):
                need += ' Runs only where the state produces electricity.'
            loc.append(f' PMR_CC_PM_{key}:0 "#header ${key}$#!\\n{need}"')
    return loc


def write_all(game, write, header_text, report):
    """Writes every file of the feature (test builds for now) and returns its loc lines."""
    comps = companies(game)
    cost = goods_cost(game)
    pms = pm_info(game)
    cal = calibrate(comps, report['blended'], cost)
    rows, untreated = method_rows(report, pms, comps)
    write('common/character_traits/pmr_cc_traits.txt', header_text + traits(cal))
    write('common/modifier_type_definitions/pmr_cc_modifier_types.txt', header_text + MODIFIER_TYPES)
    write('common/scripted_effects/pmr_cc_effects.txt', header_text + effects(cal))
    write('common/scripted_triggers/pmr_cc_triggers.txt', header_text + triggers())
    write('common/scripted_guis/pmr_cc_sguis.txt', header_text + sguis())
    write('common/on_actions/pmr_cc_on_actions.txt', header_text + ON_ACTIONS)
    write('common/script_values/pmr_cc_values.txt', header_text + unlock_values(rows))
    write('common/decisions/pmr_cc_test_decisions.txt', header_text + TEST_DECISION.replace('{LOG}', log_line('CC_TEST')))
    write(PANEL_GUI, patch_panel(open(os.path.join(game, PANEL_GUI), encoding='utf-8-sig').read()), bom=False)
    write(OWN_GUI, tab(rows, untreated), bom=False)
    if os.path.isdir(os.path.dirname(CALIBRATION_MD)):
        with open(CALIBRATION_MD, 'w', encoding='utf-8') as f:
            f.write(calibration_md(cal, comps))
    report['company_culture'] = {'companies': len(cal), 'traits': 3 + 6 * len(cal),
                                 'fallback': sorted(c for c, v in cal.items() if v.get('fallback')),
                                 'method_rows': len(rows), 'untreated': untreated}
    print(f'company culture: {len(cal)} companies, {3 + 6 * len(cal)} traits, {len(rows)} building types in Methods '
          f'({len(untreated)} without recipes)')
    return localization(cal, rows, pms)
