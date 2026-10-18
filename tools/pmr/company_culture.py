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
CAL_VERSION = 2                     # bump to make every company re-read its numbers (pmr_cc_on); 2: Workforce lines

# The tree. Pat 04:00Z: Production (Equipment or People, and Scale). Pat 2026-10-18 13:23Z: laid out like the tech
# tree, with more people options (wage targets). Each line is a column of tiers bought in order; its tier is the
# company variable pmr_cc_<key>. code is the scope:line value the tab's click passes; cost is points per tier (Pat
# 12:37Z: no queue, a click spends points already earned); needs lists (line, tier) bought before tier 1.
class Line:
    def __init__(self, code, key, section, title, names, icons, cost, needs=()):
        self.code, self.key, self.section, self.title = code, key, section, title
        self.names, self.icons, self.cost, self.needs = names, icons, cost, needs
        self.tiers = len(names)


def _icons(*names):
    return tuple(f'gfx/interface/icons/{n}.dds' for n in names)


LINES = [
    Line(1, 'eq', 'pr', 'Equipment', ('Refined Process I', 'Refined Process II', 'Refined Process III'),
         _icons('character_trait_icons/meticulous', 'character_trait_icons/engineer', 'character_trait_icons/innovative'),
         (1, 2, 3)),
    Line(2, 'pp', 'pr', 'People', ('Skilled Workforce I', 'Skilled Workforce II', 'Skilled Workforce III'),
         _icons('character_trait_icons/tactful', 'character_trait_icons/erudite', 'character_trait_icons/charismatic'),
         (1, 2, 3)),
    Line(3, 'sc', 'pr', 'Scale', ('Expanded Works I', 'Expanded Works II', 'Mass Production'),
         _icons('character_trait_icons/basic_entrepreneur', 'character_trait_icons/experienced_entrepreneur',
                'character_trait_icons/expert_entrepreneur'), (1, 2, 3)),
    Line(4, 'fw', 'wf', 'Fair Wages', ('Fair Wages', 'Living Wage', 'Profit Sharing'),
         _icons('law_icons/wage_controls', 'sol_icons/secure', 'law_icons/cooperative_ownership'), (1, 2, 3)),
    Line(5, 'tp', 'wf', 'Tight Payroll', ('Tight Payroll', 'Combination Clauses'),
         _icons('law_icons/laissez_faire', 'law_icons/combination_acts'), (1, 2)),
    Line(6, 'ho', 'wf', 'Housing', ('Company Housing', 'Model Dwellings'),
         _icons('law_icons/poor_laws', 'sol_icons/prosperous'), (1, 2)),
    Line(7, 'sf', 'wf', 'Safety', ('Safety Rules', 'Safety Inspectors'),
         _icons('institution_icons/workplace_safety', 'law_icons/worker_protections'), (1, 2)),
    Line(8, 'ct', 'wf', 'Company Town', ('Company Town',), _icons('law_icons/corporate_state'), (3,),
         (('ho', 2), ('sf', 2))),
]
BY_KEY = {ln.key: ln for ln in LINES}
SECTIONS = (('pr', 'Production'), ('wf', 'Workforce'))
EXCLUSIVE = {'eq': 'pp', 'pp': 'eq', 'fw': 'tp', 'tp': 'fw'}
COMPANY_LINES = ('eq', 'pp')        # numbers calibrated per company type; the other lines' traits are shared
EXCLUSIVE_ICON = 'gfx/interface/icons/generic_icons/warning.dds'
WHITE = 'gfx/interface/backgrounds/white.dds'

JOB_CUT = (0.03, 0.06, 0.10)        # People: net share of jobs cut per tier (Pat 04:00Z: 3 / 6 / 10%)
LABORERS_PER_ENGINEER = 4           # People: one engineer job added for every four laborer jobs cut
LABORER_CUT_MAX = 0.6
THROUGHPUT = (0.05, 0.10, 0.20)     # Scale: +5 / +5 / +10%, so 5, 10 and 20% in all
INPUT_CUT_MAX = 0.20                # Equipment: the most input goods tier III may cut

# The order AI companies buy in: col is their own column (Equipment or People), pay the wage line that goes with it.
AI_ORDER = [('col', 1), ('sc', 1), ('ho', 1), ('col', 2), ('sc', 2), ('sf', 1), ('pay', 1), ('ho', 2), ('col', 3),
            ('sc', 3), ('sf', 2), ('pay', 2), ('pay', 3), ('ct', 1)]

# Workforce (Pat 2026-10-18 13:23Z: "things more related to people such as wage target modifiers"). Every key is a
# vanilla 1.14.5 building modifier: building_minimum_wage_mult is the one shown as "Building Wage Target" (laws use
# +0.10 / +0.15), building_working_conditions_mult already rides executive_modifier on a vanilla personality trait
# (-0.10), the job attractiveness and per-profession standard of living keys are used on vanilla plantation methods,
# and building_company_worker_dividends_add ("Company Workforce Dividends") on vanilla company HQ methods (+0.25)
# and the cooperative ownership law (+0.75).
# Totals per tier: a tier's trait replaces the one before.
WORKERS = ('laborers', 'farmers', 'machinists', 'clerks', 'engineers', 'shopkeepers')
WORKFORCE = {
    ('fw', 1): [('building_minimum_wage_mult', 0.10)],
    ('fw', 2): [('building_minimum_wage_mult', 0.20), ('building_job_attractiveness_mult', 0.20)],
    ('fw', 3): [('building_minimum_wage_mult', 0.20), ('building_job_attractiveness_mult', 0.20),
                ('building_company_worker_dividends_add', 0.15)],
    ('tp', 1): [('building_minimum_wage_mult', -0.10)],
    ('tp', 2): [('building_minimum_wage_mult', -0.20)],
    ('ho', 1): [(f'building_{p}_standard_of_living_add', 1) for p in WORKERS],
    ('ho', 2): [(f'building_{p}_standard_of_living_add', 2) for p in WORKERS],
    ('sf', 1): [('building_working_conditions_mult', -0.10)],
    ('sf', 2): [('building_working_conditions_mult', -0.20)],
    ('ct', 1): [(f'building_{p}_standard_of_living_add', 1) for p in WORKERS]
               + [('building_job_attractiveness_mult', 0.15)],
}

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
    return f'pmr_cc_{line}_{short(company)}_{t}' if line in COMPANY_LINES else f'pmr_cc_{line}_{t}'


def trait(key, icon, mods):
    body = ''.join(f'\t\t{k} = {v}\n' for k, v in mods)
    return (f'{key} = {{\n\ttype = condition\n\ttexture = "{icon}"\n\n'
            f'\texecutive_modifier = {{\n{body}\t}}\n\n'
            '\tpossible = { always = no }\n\tweight = { value = 0 }\n\tvalue = 0\n}\n')


def fmt(x):
    s = f'{x:.4f}'.rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'


def traits(cal):
    out = ['# Company Culture traits (company_culture.py). Each sits on a company\'s executive; its executive_modifier\n'
           '# applies to the building levels that company owns. Never random (possible no, weight 0, value 0).\n\n']
    icons = {ln.key: ln.icons for ln in LINES}
    for t in (1, 2, 3):
        out.append(trait(trait_key('sc', None, t), icons['sc'][t - 1], [('building_throughput_add', fmt(THROUGHPUT[t - 1]))]))
    for (k, t), mods in WORKFORCE.items():
        out.append(trait(trait_key(k, None, t), icons[k][t - 1], [(m, fmt(v)) for m, v in mods]))
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
            "rate=[THIS.Var('pmr_cc_rate').GetValue|1];"
            + ';'.join(f"{ln.key}=[THIS.Var('pmr_cc_{ln.key}').GetValue|0]" for ln in LINES) + '"')


def player_log(rec, extra=''):
    return f'if = {{ limit = {{ owner = {{ is_player = yes }} }} {log_line(rec, extra)} }}'


NUMBERS = ('x', 'l', 'a', 'p', 'e')     # per company and tier, from calibrate() (tiers_for)
MIRRORED = (['pmr_cc_level', 'pmr_cc_pts', 'pmr_cc_funds', 'pmr_cc_cost', 'pmr_cc_rate', 'pmr_cc_pct', 'pmr_cc_mo',
             'pmr_cc_prosp', 'pmr_cc_size']
            + [f'pmr_cc_{ln.key}' for ln in LINES]
            + [f'pmr_cc_pick_{ln.key}' for ln in LINES]
            + [f'pmr_cc_st_{ln.key}_{t}' for ln in LINES for t in range(1, ln.tiers + 1)]
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
                       for v in ['pmr_cc_funds', 'pmr_cc_level', 'pmr_cc_pts', 'pmr_cc_rate']
                       + [f'pmr_cc_{ln.key}' for ln in LINES])
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
    pay = ''
    for ln in LINES:
        chain = ''.join(f'\t{"if" if t == 0 else "else_if"} = {{ limit = {{ var:pmr_cc_{ln.key} = {t} }} '
                        f'change_variable = {{ name = pmr_cc_pts subtract = {c} }} }}\n'
                        for t, c in enumerate(ln.cost))
        pay += f'pmr_cc_pay_{ln.key} = {{\n{chain}}}\n\n'
    o.append('# The points for the next tier of each line, taken when it is bought.\n' + pay)
    o.append('# Buy the next tier of line $L$: its cost in points, the tier, the traits.\n'
             'pmr_cc_buy = {\n'
             '\tpmr_cc_pay_$L$ = yes\n'
             '\tchange_variable = { name = pmr_cc_$L$ add = 1 }\n'
             '\tsave_scope_as = pmr_cc_co\n\tpmr_cc_apply = yes\n'
             f'\t{player_log("CC_BUY", "line=$L$;")}\n}}\n\n')
    # A click (scope:line from the GUI).
    click = ''
    for i, ln in enumerate(LINES):
        click += (f'\t{"if" if i == 0 else "else_if"} = {{\n'
                  f'\t\tlimit = {{\n\t\t\tscope:line = {ln.code}\n\t\t\tpmr_cc_open_{ln.key} = yes\n'
                  f'\t\t\tpmr_cc_afford = {{ L = {ln.key} }}\n\t\t}}\n'
                  f'\t\tpmr_cc_buy = {{ L = {ln.key} }}\n\t}}\n')
    codes = ', '.join(f'{ln.code} {ln.title}' for ln in LINES)
    o.append(f'# The player clicked the next node of line scope:line ({codes}): it is bought with\n'
             '# points already earned, or nothing happens (Pat 12:37Z: no queue).\n'
             'pmr_cc_click = {\n\tsave_scope_as = pmr_cc_co\n' + click + '\tpmr_cc_mirror = yes\n}\n\n')
    # AI: one fixed order per column. A step already bought, or closed to the company, is passed over; the first
    # step still open is bought when affordable, otherwise the company saves for it.
    def ai_chain(col, wage, ind):
        out = ''
        for i, (k, t) in enumerate(AI_ORDER):
            k = {'col': col, 'pay': wage}.get(k, k)
            out += (f'{ind}{"if" if i == 0 else "else_if"} = {{\n{ind}\tlimit = {{ var:pmr_cc_{k} < {t} pmr_cc_open_{k} = yes }}\n'
                    f'{ind}\tif = {{ limit = {{ pmr_cc_afford = {{ L = {k} }} }} pmr_cc_buy = {{ L = {k} }} }}\n{ind}}}\n')
        return out
    o.append('# AI companies (Pat 04:00Z: yes) buy along a fixed order as soon as they can afford the next step:\n'
             '# Equipment companies (pmr_cc_ai 1) take Tight Payroll, People companies Fair Wages.\n'
             'pmr_cc_ai_step = {\n\tif = {\n\t\tlimit = { var:pmr_cc_ai = 1 }\n'
             + ai_chain('eq', 'tp', '\t\t')
             + '\t}\n\telse = {\n'
             + ai_chain('pp', 'fw', '\t\t')
             + '\t}\n}\n\n'
             'pmr_cc_ai_buy = {\n\tpmr_cc_ai_step = yes\n\tpmr_cc_ai_step = yes\n}\n\n')
    # Traits: the trait of each line for its tier, the other tiers removed.
    def line_fx(k, keys):
        out = ''
        for t in range(len(keys), 0, -1):
            kw = 'if' if t == len(keys) else 'else_if'
            cond = f'var:pmr_cc_{k} >= {t}' if t == len(keys) else f'var:pmr_cc_{k} = {t}'
            out += f'\t{kw} = {{\n\t\tlimit = {{ scope:pmr_cc_co = {{ {cond} }} }}\n'
            out += ''.join(f'\t\tif = {{ limit = {{ has_trait = {o_} }} remove_trait = {o_} }}\n'
                           for n, o_ in enumerate(keys, 1) if n != t)
            out += f'\t\tif = {{ limit = {{ NOT = {{ has_trait = {keys[t - 1]} }} }} add_trait = {keys[t - 1]} }}\n\t}}\n'
        out += '\telse = {\n' + ''.join(f'\t\tif = {{ limit = {{ has_trait = {o_} }} remove_trait = {o_} }}\n'
                                         for o_ in keys) + '\t}\n'
        return out
    o.append('# Character scope (the executive), scope:pmr_cc_co the company: the trait of a three-tier line $L$ for its\n'
             '# tier, the other tiers removed.\npmr_cc_line = {\n'
             + line_fx('$L$', ['$T1$', '$T2$', '$T3$']) + '}\n\n')
    shared = ''
    for ln in LINES:
        if ln.key not in COMPANY_LINES:
            shared += f'pmr_cc_line_{ln.key} = {{\n' + line_fx(ln.key, [trait_key(ln.key, None, t) for t in
                                                                       range(1, ln.tiers + 1)]) + '}\n\n'
    o.append('# The same for each line whose traits every company shares.\n' + shared)
    apply_chain = ''
    for i, c in enumerate(sorted(cal)):
        kw = 'if' if i == 0 else 'else_if'
        t = {k: [trait_key(k, c, n) for n in (1, 2, 3)] for k in COMPANY_LINES}
        apply_chain += (f'\t\t{kw} = {{\n\t\t\tlimit = {{ scope:pmr_cc_co = {{ is_company_type = company_type:{c} }} }}\n'
                        f'\t\t\tpmr_cc_line = {{ L = eq T1 = {t["eq"][0]} T2 = {t["eq"][1]} T3 = {t["eq"][2]} }}\n'
                        f'\t\t\tpmr_cc_line = {{ L = pp T1 = {t["pp"][0]} T2 = {t["pp"][1]} T3 = {t["pp"][2]} }}\n\t\t}}\n')
    o.append('# The executive\'s traits for the company\'s tiers. scope:pmr_cc_co is the company. An executive who came\n'
             '# from another company with Culture traits loses them first (pmr_cc_strip).\n'
             'pmr_cc_apply = {\n\texecutive ?= {\n'
             '\t\tif = {\n\t\t\tlimit = {\n\t\t\t\thas_variable = pmr_cc_of\n\t\t\t\tNOT = { var:pmr_cc_of ?= scope:pmr_cc_co }\n\t\t\t}\n'
             '\t\t\tpmr_cc_strip = yes\n\t\t}\n'
             '\t\tset_variable = { name = pmr_cc_of value = scope:pmr_cc_co }\n'
             + apply_chain
             + ''.join(f'\t\tpmr_cc_line_{ln.key} = yes\n' for ln in LINES if ln.key not in COMPANY_LINES)
             + '\t}\n}\n\n')
    strip = ''.join(f'\tif = {{ limit = {{ has_trait = {trait_key(k, c, t)} }} remove_trait = {trait_key(k, c, t)} }}\n'
                    for c in sorted(cal) for k in COMPANY_LINES for t in (1, 2, 3))
    strip += ''.join(f'\tif = {{ limit = {{ has_trait = {trait_key(ln.key, None, t)} }} '
                     f'remove_trait = {trait_key(ln.key, None, t)} }}\n'
                     for ln in LINES if ln.key not in COMPANY_LINES for t in range(1, ln.tiers + 1))
    o.append('# Character scope: every Company Culture trait off. Runs only when an executive changes company and on\n'
             '# disbanding (Pat 04:00Z: a disbanded company loses its bonuses).\n'
             'pmr_cc_strip = {\n' + strip + '\tremove_variable = pmr_cc_of\n}\n\n')
    # Node states for the tab.
    states = ''
    for ln in LINES:
        k = ln.key
        other = EXCLUSIVE.get(k)
        excl = f'var:pmr_cc_{other} > 0' if other else 'always = no'
        needs = ''.join(f' var:pmr_cc_{nk} >= {nt}' for nk, nt in ln.needs)
        states += f'\tset_variable = {{ name = pmr_cc_pick_{k} value = 0 }}\n'
        for t in range(1, ln.tiers + 1):
            st = f'pmr_cc_st_{k}_{t}'
            states += (f'\tif = {{ limit = {{ var:pmr_cc_{k} >= {t} }} set_variable = {{ name = {st} value = 4 }} }}\n'
                       f'\telse_if = {{ limit = {{ {excl} }} set_variable = {{ name = {st} value = 5 }} }}\n'
                       f'\telse_if = {{\n\t\tlimit = {{ var:pmr_cc_{k} = {t - 1}{needs if t == 1 else ""} }}\n'
                       f'\t\tif = {{ limit = {{ var:pmr_cc_pts >= {ln.cost[t - 1]} }} '
                       f'set_variable = {{ name = {st} value = 1 }} set_variable = {{ name = pmr_cc_pick_{k} value = 1 }} }}\n'
                       f'\t\telse = {{ set_variable = {{ name = {st} value = 2 }} }}\n\t}}\n'
                       f'\telse = {{ set_variable = {{ name = {st} value = 0 }} }}\n')
    copies = ''.join(f'\t\tif = {{ limit = {{ scope:pmr_cc_co = {{ has_variable = {v} }} }} '
                     f'set_variable = {{ name = {v} value = scope:pmr_cc_co.var:{v} }} }}\n'
                     f'\t\telse_if = {{ limit = {{ has_variable = {v} }} remove_variable = {v} }}\n' for v in MIRRORED)
    o.append('# The tab\'s numbers, mirrored onto the executive (the panel reads Company.GetExecutive.MakeScope). Node states\n'
             '# pmr_cc_st_<line>_<tier>: 0 locked (a later tier, or its needs not bought), 1 next and affordable (a click buys it), 2 next but not enough\n'
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
         '# pmr_cc_open_<line>: the line has a tier left to buy, its needs are bought, and for an exclusive pair\n'
         '# (Equipment or People, Fair Wages or Tight Payroll) the other line is untouched (Pat 04:00Z: the first tier\n'
         '# bought locks the company to its column).\n']
    for ln in LINES:
        other = EXCLUSIVE.get(ln.key)
        body = f'\tvar:pmr_cc_{ln.key} < {ln.tiers}\n'
        body += f'\tvar:pmr_cc_{other} = 0\n' if other else ''
        body += ''.join(f'\tvar:pmr_cc_{nk} >= {nt}\n' for nk, nt in ln.needs)
        o.append(f'pmr_cc_open_{ln.key} = {{\n{body}}}\n\n')
    o.append('# The points for the next tier of each line.\n')
    for ln in LINES:
        alts = ''.join(f'\t\tAND = {{ var:pmr_cc_{ln.key} = {t} var:pmr_cc_pts >= {c} }}\n' for t, c in enumerate(ln.cost))
        o.append(f'pmr_cc_afford_{ln.key} = {{\n\tOR = {{\n{alts}\t}}\n}}\n\n')
    o.append('# The points for line $L$\'s next tier.\npmr_cc_afford = {\n\tpmr_cc_afford_$L$ = yes\n}\n\n')
    return ''.join(o)


def sguis():
    picks = ''.join(f'\t\t\tAND = {{ scope:line = {ln.code} var:pmr_cc_pick_{ln.key} ?= 1 }}\n' for ln in LINES)
    return ('# Company Culture tab (company_culture.py). Character scope: the company\'s executive, as the panel reads\n'
            '# Company.GetExecutive.MakeScope. scope:line is the line clicked (Line.code in company_culture.py).\n\n'
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

SG_SCOPE = 'GuiScope.SetRoot(Character.MakeScope)'
LOCAL = 'Company.GetCountry.IsLocalPlayer'

# The tree, drawn with the tech tree's pieces (gui/tech_tree.gui; Pat 2026-10-18 13:23Z: "utilize the tech tree UI
# and selectors"): each node is the tech's round frame over its icon, with the tech's backgrounds for each state, its
# era badge (here the node's cost) and its researched tick, joined by lines in the tech tree's spline colours. The
# tech node is 465 wide; stacked frame-over-card nodes let four columns fit the company panel.
CARD_W, CARD_H, CARD_TOP = 128, 150, 36    # node, and where its card starts under the frame
FRAME, ICON = 84, 60
COL_STEP, ROW_STEP = 136, 174
BUS_Y, TOP = 30, 44                        # the line joining a section's columns; the first row of nodes
TREE_W = 536
# tech_tree.gui techtree_spline: a border line (width 8, alpha 0.6) under a core line (width 4, alpha 0.8). Across the
# line the textures are a fixed colour profile, so horizontal lines use them as they are and vertical ones use their
# colours (sampled from the 1.14.5 files) on a plain strip.
LINE_TEX = {'done': 'research_done', 'active': 'researching', 'locked': 'research_locked'}
LINE_RGB = {'done': ('0.94 0.80 0.60', '0.50 0.41 0.28'),
            'active': ('0.61 0.80 0.91', '0.44 0.68 0.76'),
            'locked': ('0.43 0.52 0.54', '0.43 0.52 0.54')}


def _reindent(text, base):
    """Indents generated GUI text by brace depth."""
    out, depth = [], 0
    for raw in text.split('\n'):
        line = raw.strip()
        if not line:
            continue
        if line.startswith('}'):
            depth -= 1
        out.append(base + '\t' * depth + line)
        depth += line.count('{') - line.count('}') + (1 if line.startswith('}') else 0)
    return '\n'.join(out) + '\n'


def V(name):
    return f"Character.MakeScope.Var('{name}').GetValue"


def EQ(name, n):
    return f"EqualTo_CFixedPoint({V(name)}, '(CFixedPoint){n}')"


def GT(name, n):
    return f"GreaterThan_CFixedPoint({V(name)}, '(CFixedPoint){n}')"


def line_modes(st):
    """visible expressions for a line drawn into the node whose state variable is st."""
    done, active = EQ(st, 4), f'Or({EQ(st, 1)}, {EQ(st, 2)})'
    return {'done': done, 'active': active, 'locked': f'Not(Or({done}, {active}))'}


def vline(x, y0, y1, st):
    out = ''
    for mode, vis in line_modes(st).items():
        border, core = LINE_RGB[mode]
        out += (f'icon = {{\nvisible = "[{vis}]"\nposition = {{ {x - 4} {y0} }}\nsize = {{ 8 {y1 - y0} }}\n'
                f'texture = "{WHITE}"\ncolor = {{ {border} 0.6 }}\nalwaystransparent = yes\n}}\n'
                f'icon = {{\nvisible = "[{vis}]"\nposition = {{ {x - 2} {y0} }}\nsize = {{ 4 {y1 - y0} }}\n'
                f'texture = "{WHITE}"\ncolor = {{ {core} 0.8 }}\nalwaystransparent = yes\n}}\n')
    return out


def hline(x0, x1, y, st=None):
    modes = line_modes(st) if st else {'locked': None}
    out = ''
    for mode, vis in modes.items():
        v = f'visible = "[{vis}]"\n' if vis else ''
        out += (f'icon = {{\n{v}position = {{ {x0} {y - 4} }}\nsize = {{ {x1 - x0} 8 }}\n'
                f'texture = "gfx/interface/tech_tree/tech_line_border_{LINE_TEX[mode]}.dds"\nalpha = 0.6\nalwaystransparent = yes\n}}\n'
                f'icon = {{\n{v}position = {{ {x0} {y - 2} }}\nsize = {{ {x1 - x0} 4 }}\n'
                f'texture = "gfx/interface/tech_tree/tech_line_{LINE_TEX[mode]}.dds"\nalpha = 0.8\nalwaystransparent = yes\n}}\n')
    return out


def node(ln, t, x, y):
    k = ln.key
    st = f'pmr_cc_st_{k}_{t}'
    cost = ln.cost[t - 1]
    icon = ln.icons[t - 1]
    tt = f'tooltip = "PMR_CC_TT_{k}_{t}"\n'
    sg = "GetScriptedGui('pmr_cc_pick_sgui')"
    scope = f"{SG_SCOPE}.AddScope('line', MakeScopeValue('(CFixedPoint){ln.code}')).End"
    can = f"And({LOCAL}, And({EQ(st, 1)}, {sg}.IsValid({scope})))"
    click = f'enabled = "[{can}]"\nonclick = "[{sg}.Execute({scope})]"\n'
    locked = f'Or({EQ(st, 0)}, {EQ(st, 5)})'
    card = f'position = {{ 0 {CARD_TOP} }}\nsize = {{ {CARD_W} {CARD_H - CARD_TOP} }}\n'
    fx, fy = (CARD_W - FRAME) // 2, 0
    ix, iy = (CARD_W - ICON) // 2, (FRAME - ICON) // 2
    out = (f'widget = {{\nposition = {{ {x} {y} }}\nsize = {{ {CARD_W} {CARD_H} }}\n'
           # can buy: the tech's glow under an action button with its shimmer (CAN RESEARCH)
           f'widget = {{\nvisible = "[{EQ(st, 1)}]"\nsize = {{ {CARD_W + 30} 70 }}\nparentanchor = bottom|hcenter\n'
           f'position = {{ 0 -10 }}\nusing = ui_event_glow_animation_looping\n}}\n'
           f'button = {{\nvisible = "[{EQ(st, 1)}]"\n{card}using = default_button_action\nusing = shimmer\n'
           f'using = technology_confirm_button_sound\n{click}{tt}}}\n'
           # next, not enough points yet: the tech's greyed action button (LOCKED RESEARCH BUTTON)
           f'button = {{\nvisible = "[{EQ(st, 2)}]"\n{card}using = default_button_action\ncolor = {{ 0.4 0.4 0.4 1 }}\n'
           f'enabled = no\n{tt}}}\n'
           # bought: the tech's paper (HAS RESEARCHED), in the gold frame Pat chose for bought tiers (12:37Z)
           f'widget = {{\nvisible = "[{EQ(st, 4)}]"\n{card}{tt}background = {{\nusing = paper_bg\n}}\n'
           f'icon = {{\nusing = highlighted_selected_square_selection\nalwaystransparent = yes\n}}\n}}\n'
           # locked or ruled out: the tech's dark card (CAN'T RESEARCH)
           f'widget = {{\nvisible = "[{locked}]"\n{card}{tt}background = {{\nusing = entry_fancy_header_colored\n'
           f'using = dark_area\n}}\n}}\n'
           # the round frame and icon; a buyable node's icon is a button, like the tech icon
           f'icon = {{\nvisible = "[Not({locked})]"\nposition = {{ {fx} {fy} }}\nsize = {{ {FRAME} {FRAME} }}\n'
           f'texture = "gfx/interface/backgrounds/round_frame_dec.dds"\nalwaystransparent = yes\n}}\n'
           f'icon = {{\nvisible = "[{locked}]"\nposition = {{ {fx} {fy} }}\nsize = {{ {FRAME} {FRAME} }}\n'
           f'texture = "gfx/interface/backgrounds/round_frame_dec.dds"\ncolor = {{ 0.5 0.5 0.5 1 }}\nalwaystransparent = yes\n}}\n'
           f'icon = {{\nvisible = "[And(Not({locked}), Not({EQ(st, 1)}))]"\nposition = {{ {ix} {iy} }}\n'
           f'size = {{ {ICON} {ICON} }}\ntexture = "{icon}"\n{tt}}}\n'
           f'icon = {{\nvisible = "[{locked}]"\nposition = {{ {ix} {iy} }}\nsize = {{ {ICON} {ICON} }}\n'
           f'texture = "{icon}"\ncolor = {{ 0.4 0.4 0.4 1 }}\n{tt}}}\n'
           f'button = {{\nvisible = "[{EQ(st, 1)}]"\nposition = {{ {ix} {iy} }}\nsize = {{ {ICON} {ICON} }}\n'
           f'texture = "{icon}"\nusing = technology_confirm_button_sound\n{click}{tt}}}\n'
           # cost, where the tech shows its era; the tech's tick once bought
           f'widget = {{\nvisible = "[Not({EQ(st, 4)})]"\nposition = {{ 12 52 }}\nsize = {{ 34 34 }}\n'
           f'tooltip = "PMR_CC_COST_TT_{cost}"\nicon = {{\nsize = {{ 100% 100% }}\n'
           f'texture = "gfx/interface/backgrounds/round_button_bg.dds"\n}}\n'
           f'textbox = {{\nparentanchor = center\nautoresize = yes\nalign = center|nobaseline\nusing = fontsize_xl\n'
           f'raw_text = "{cost}"\nalwaystransparent = yes\n}}\n}}\n'
           f'widget = {{\nvisible = "[{EQ(st, 4)}]"\nposition = {{ {CARD_W - 46} 52 }}\nsize = {{ 34 34 }}\n'
           f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "gfx/interface/backgrounds/round_button_bg.dds"\n}}\n'
           f'icon = {{\nsize = {{ 80% 80% }}\nparentanchor = center\n'
           f'texture = "gfx/interface/icons/generic_icons/green_checkmark.dds"\n}}\n}}\n'
           + (f'icon = {{\nvisible = "[{EQ(st, 5)}]"\nposition = {{ {CARD_W - 42} 54 }}\nsize = {{ 28 28 }}\n'
              f'texture = "{EXCLUSIVE_ICON}"\ntooltip = "PMR_CC_EXCLUSIVE_TT_{k}"\n}}\n' if k in EXCLUSIVE else '') +
           f'textbox = {{\nposition = {{ 4 86 }}\nsize = {{ {CARD_W - 8} 38 }}\nmultiline = yes\nalign = hcenter|nobaseline\n'
           f'fontsize_min = 12\nelide = right\ntext = "PMR_CC_NAME_{k}_{t}"\nalwaystransparent = yes\n}}\n')
    for s, key in ((1, f'PMR_CC_NODE_BUY_{cost}'), (2, f'PMR_CC_NODE_NEED_{cost}'), (4, 'PMR_CC_NODE_OWNED'),
                   (5, f'PMR_CC_NODE_RULED_OUT_{k}'), (0, f'PMR_CC_NODE_LOCKED_{k}_{t}')):
        out += (f'textbox = {{\nvisible = "[{EQ(st, s)}]"\nposition = {{ 4 124 }}\nsize = {{ {CARD_W - 8} 22 }}\n'
                f'align = hcenter|nobaseline\nusing = fontsize_small\ntext = "{key}"\nalwaystransparent = yes\n}}\n')
    return out + '}\n'


def layout(section):
    """(line, tier) -> top-left of its node, and the section's height. Columns are the lines without needs, centred;
    a line with needs sits below and between the lines it needs."""
    cols = [ln for ln in LINES if ln.section == section and not ln.needs]
    left = (TREE_W - (len(cols) * COL_STEP - (COL_STEP - CARD_W))) // 2
    pos = {}
    for i, ln in enumerate(cols):
        for t in range(1, ln.tiers + 1):
            pos[(ln.key, t)] = (left + i * COL_STEP, TOP + (t - 1) * ROW_STEP)
    for ln in LINES:
        if ln.section == section and ln.needs:
            xs = [pos[(nk, nt)][0] for nk, nt in ln.needs]
            row = max(pos[(nk, nt)][1] for nk, nt in ln.needs) + ROW_STEP
            for t in range(1, ln.tiers + 1):
                pos[(ln.key, t)] = (sum(xs) // len(xs), row + (t - 1) * ROW_STEP)
    height = max(y for _x, y in pos.values()) + CARD_H
    return cols, pos, height


def tree(section, ready):
    cols, pos, height = layout(section)
    mid = CARD_W // 2
    out = f'widget = {{\nvisible = "[{ready}]"\nparentanchor = hcenter\nsize = {{ {TREE_W} {height} }}\n'
    # column titles, the line joining them, and an exclusive pair's mark on the line between them
    centres = [pos[(ln.key, 1)][0] + mid for ln in cols]
    for ln, cx in zip(cols, centres):
        out += (f'textbox = {{\nposition = {{ {cx - mid} 0 }}\nsize = {{ {CARD_W} 22 }}\nalign = hcenter|nobaseline\n'
                f'text = "PMR_CC_COLUMN_{ln.key}"\ntooltip = "PMR_CC_COLUMN_TT_{ln.key}"\n}}\n')
    out += hline(centres[0], centres[-1], BUS_Y)
    for (a, ca), (b, cb) in zip(zip(cols, centres), zip(cols[1:], centres[1:])):
        if EXCLUSIVE.get(a.key) == b.key:
            out += (f'icon = {{\nposition = {{ {(ca + cb) // 2 - 12} {BUS_Y - 12} }}\nsize = {{ 24 24 }}\n'
                    f'texture = "{EXCLUSIVE_ICON}"\ntooltip = "PMR_CC_EXCLUSIVE_TT_{a.key}"\n}}\n')
    for ln, cx in zip(cols, centres):
        out += vline(cx, BUS_Y + 4, TOP, f'pmr_cc_st_{ln.key}_1')
    for ln in LINES:
        if ln.section != section:
            continue
        for t in range(2, ln.tiers + 1):
            x, y = pos[(ln.key, t - 1)]
            out += vline(x + mid, y + CARD_H, pos[(ln.key, t)][1], f'pmr_cc_st_{ln.key}_{t}')
        if ln.needs:
            x1, y1 = pos[(ln.key, 1)]
            st = f'pmr_cc_st_{ln.key}_1'
            bottoms = [(pos[n][0] + mid, pos[n][1] + CARD_H) for n in ln.needs]
            ym = max(b for _x, b in bottoms) + 12
            for bx, by in bottoms:
                out += vline(bx, by, ym, st)
            out += hline(min(bx for bx, _b in bottoms) - 4, max(bx for bx, _b in bottoms) + 4, ym, st)
            out += vline(x1 + mid, ym, y1, st)
    for (k, t), (x, y) in pos.items():
        out += node(BY_KEY[k], t, x, y)
    return out + '}\n'


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
    trees = ''.join(f'{i1}default_header = {{\n{i2}blockoverride "text" {{\n{i3}text = "PMR_CC_SECTION_{sec}"\n'
                    f'{i2}}}\n{i1}}}\n' + _reindent(tree(sec, ready), i1) for sec, _title in SECTIONS)
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
            + show + header + trees + methods +
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
        ' PMR_CC_LEVEL_TT:0 "#header Culture points#!\\nA company earns Culture points from its prosperity and spends them on the trees below; each node shows its cost in points. The bonuses apply to the building levels this company owns, in proportion where it owns part of a building."',
        f' PMR_CC_BAR:0 "#v {v("pmr_cc_funds", 0)}#! / {v("pmr_cc_cost", 0)}"',
        f' PMR_CC_BAR_TT:0 "#header Next Culture point#!\\nEach month this company earns its prosperity (#v {v("pmr_cc_prosp", 0)}#!) times its size (#v ×{v("pmr_cc_size", 1)}#!, from its employed levels: one more tenth per 5 levels, at most ×2), so #v +{v("pmr_cc_rate", 0)}#! a month.\\n\\nA full bar gives one point and one Culture level, and each level needs more than the last."',
        f' PMR_CC_RATE:0 "+{v("pmr_cc_rate", 0)} a month, next point in about {v("pmr_cc_mo", 0)} months"',
        ' PMR_CC_RATE_NONE:0 "Earning nothing while its prosperity is 0"',
        ' PMR_CC_SECTION_pr:0 "Production"',
        ' PMR_CC_SECTION_wf:0 "Workforce"',
        ' PMR_CC_EXCLUSIVE_TT_eq:0 "#header Equipment or People#!\\nA company focuses on its machinery or on its people. The first Equipment or People tier it buys rules out the other column."',
        ' PMR_CC_EXCLUSIVE_TT_pp:0 "$PMR_CC_EXCLUSIVE_TT_eq$"',
        ' PMR_CC_EXCLUSIVE_TT_fw:0 "#header Fair Wages or Tight Payroll#!\\nA company sets its pay above or below what its buildings would otherwise aim for. The first Fair Wages or Tight Payroll tier it buys rules out the other column."',
        ' PMR_CC_EXCLUSIVE_TT_tp:0 "$PMR_CC_EXCLUSIVE_TT_fw$"',
        ' PMR_CC_SHOW:0 "Show Company Culture"',
        ' PMR_CC_SHOW_TT:0 "This company\'s Culture has not been read in yet (a new executive this month, or a game started before Company Culture). Click to bring it up to date; it also updates on its own at the start of each month."',
        ' PMR_CC_COLUMN_eq:0 "Equipment"',
        ' PMR_CC_COLUMN_pp:0 "People"',
        ' PMR_CC_COLUMN_sc:0 "Scale"',
        ' PMR_CC_COLUMN_TT_eq:0 "#header Equipment#!\\nThe company invests in its machinery: every level it owns needs fewer input goods.\\n\\nEach tier raises productivity about as much as the People tier beside it, at base prices for this company\'s buildings, or less where inputs are so cheap that the cut would pass 20%. Rules out People."',
        ' PMR_CC_COLUMN_TT_pp:0 "#header People#!\\nThe company invests in its workforce: fewer laborer jobs on every level it owns, and a few engineer jobs in their place, so fewer jobs in all.\\n\\nEngineer jobs left empty lower output like any unfilled job. Rules out Equipment."',
        ' PMR_CC_COLUMN_TT_sc:0 "#header Scale#!\\nMore throughput on every level the company owns."',
        ' PMR_CC_COLUMN_fw:0 "Fair Wages"',
        ' PMR_CC_COLUMN_tp:0 "Tight Payroll"',
        ' PMR_CC_COLUMN_ho:0 "Housing"',
        ' PMR_CC_COLUMN_sf:0 "Safety"',
        ' PMR_CC_COLUMN_TT_fw:0 "#header Fair Wages#!\\nThe company aims to pay more: a higher wage target on every level it owns, so its workers grow wealthier and its jobs fill more easily. Rules out Tight Payroll."',
        ' PMR_CC_COLUMN_TT_tp:0 "#header Tight Payroll#!\\nThe company aims to pay less: a lower wage target on every level it owns, so more of its earnings go to profit. Rules out Fair Wages."',
        ' PMR_CC_COLUMN_TT_ho:0 "#header Housing#!\\nThe company houses its workers: a higher standard of living for the workers on every level it owns."',
        ' PMR_CC_COLUMN_TT_sf:0 "#header Safety#!\\nThe company makes its workplaces safer on every level it owns."',
        ' PMR_CC_NODE_OWNED:0 "#v Bought#!"',
        ' PMR_CC_NODE_RULED_OUT_eq:0 "Ruled out by People"',
        ' PMR_CC_NODE_RULED_OUT_pp:0 "Ruled out by Equipment"',
        ' PMR_CC_NODE_RULED_OUT_sc:0 ""',
        ' PMR_CC_NODE_RULED_OUT_fw:0 "Ruled out by Tight Payroll"',
        ' PMR_CC_NODE_RULED_OUT_tp:0 "Ruled out by Fair Wages"',
        ' PMR_CC_NODE_RULED_OUT_ho:0 ""',
        ' PMR_CC_NODE_RULED_OUT_sf:0 ""',
        ' PMR_CC_NODE_RULED_OUT_ct:0 ""',
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
                f' PMR_CC_COST_TT_{t}:0 "Costs #v {t}#! Culture {pts}."',
                f' PMR_CC_NODE_BUY_{t}:0 "#P Buy#!: {t} {pts}"',
                f' PMR_CC_NODE_NEED_{t}:0 "Needs {t} {pts}"']
    names = {ln.key: ln.names for ln in LINES}
    for ln in LINES:
        for t in range(1, ln.tiers + 1):
            if t > 1:
                after = names[ln.key][t - 2]
            else:
                after = ' and '.join(BY_KEY[nk].names[nt - 1] for nk, nt in ln.needs)
            loc.append(f' PMR_CC_NODE_LOCKED_{ln.key}_{t}:0 "{"After " + after if after else ""}"')
    workers = 'laborers, farmers, machinists, clerks, engineers and shopkeepers'
    wf_tt = {
        ('fw', 1): ('Wage target #v +10%#! on every level {co} owns: its buildings aim for higher pay, so its workers grow wealthier over time.', 'Rules out Tight Payroll.'),
        ('fw', 2): ('Wage target #v +20%#! and job attractiveness #v +20%#! on every level {co} owns: higher pay, and its jobs draw workers more easily.', 'Rules out Tight Payroll.'),
        ('fw', 3): ('As Living Wage, and the workforce on every level {co} owns is paid #v +15%#! of its dividends.', 'Rules out Tight Payroll.'),
        ('tp', 1): ('Wage target #v -10%#! on every level {co} owns: its buildings aim for lower pay, so more of their earnings are profit.', 'Rules out Fair Wages.'),
        ('tp', 2): ('Wage target #v -20%#! on every level {co} owns.', 'Rules out Fair Wages.'),
        ('ho', 1): ('Standard of living #v +1#! for the ' + workers + ' working on every level {co} owns.', ''),
        ('ho', 2): ('Standard of living #v +2#! for the ' + workers + ' working on every level {co} owns.', ''),
        ('sf', 1): ('Dangerous working conditions #v -10%#! on every level {co} owns.', ''),
        ('sf', 2): ('Dangerous working conditions #v -20%#! on every level {co} owns.', ''),
        ('ct', 1): ('Standard of living a further #v +1#! for its workers, and job attractiveness #v +15%#!, on every level {co} owns.', 'Needs Model Dwellings and Safety Inspectors.'),
    }
    exec_co = "this executive's company"
    for (k, t), (body, tail) in wf_tt.items():
        c = BY_KEY[k].cost[t - 1]
        pts = 'point' if c == 1 else 'points'
        loc += [f' PMR_CC_NAME_{k}_{t}:0 "{names[k][t - 1]}"',
                f' PMR_CC_TT_{k}_{t}:0 "#header {names[k][t - 1]}#!\\n{body.format(co=co)}\\n\\nCosts #v {c}#! {pts}.'
                + (f' {tail}' if tail else '') + '"',
                f' {trait_key(k, None, t)}:0 "{names[k][t - 1]}"',
                f' {trait_key(k, None, t)}_desc:0 "Company Culture, Workforce: {body.format(co=exec_co)}"']
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
    n_traits = 3 + len(WORKFORCE) + 6 * len(cal)
    report['company_culture'] = {'companies': len(cal), 'traits': n_traits,
                                 'fallback': sorted(c for c, v in cal.items() if v.get('fallback')),
                                 'method_rows': len(rows), 'untreated': untreated}
    print(f'company culture: {len(cal)} companies, {n_traits} traits, {len(rows)} building types in Methods '
          f'({len(untreated)} without recipes)')
    return localization(cal, rows, pms)
