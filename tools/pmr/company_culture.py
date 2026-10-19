"""Company Culture: two trees and a board on every company (Pat, 2026-10-19 14:43Z, in place of the 10-18 wheel).

The spec is /mnt/project-files/pmr/company-rework/SPEC.md (the build thread's, from Pat's 14:43Z, 14:44Z, 14:50Z and
14:58Z messages). This module builds the lines, their script and their text; cc_tree.py draws the full-screen window
and subsidiaries.py the subsidiaries. Test builds only until Pat ships it.

The window splits 70 / 30 (Pat 14:43Z): the Expansion and Engineering trees on the left, the board on the right (the
company's executive and its subsidiaries' executives; the bylaws come next). Each tree is a root, its principle,
and three levels under it (Pat 14:58Z: "3 levels deep + their parent principle so 4 total"). Expansion's levels are two
branches of which a company takes one: Vertical (Vertical Integration founds the supply subsidiary, the industries
making the key building's inputs; then an input cut with the Trade charter, throughput with the Monopoly charter) or
Horizontal (Diversification founds the sister subsidiary, the other industries of the key building's class, and opens
the Industry charter; then the Investment charter, then throughput with the Colonization charter). Engineering has no
special production methods any more: throughput, output of the company's main goods a notch stronger, and its
prestige goods at the third level. The key building is the company's building type with the highest output value.

How a bonus reaches the company's own levels and nobody else's (confirmed in game 2026-10-14 03:51Z): each bonus is a
character trait on the company's executive with an executive_modifier, which the engine applies to the building levels
the company owns. A subsidiary's executive carries one trait, Subsidiary, and none of its parent's (Pat 15:48Z): half
its parent's tree throughput, less half the country's Company Throughput Bonus (Pat 14:43Z "half of the throughput and
construction bonus", 15:48Z "use the executive traits to nerf subsidiaries throughput buffs by half"), in whole
percent, kept in step monthly (pmr_cc_sub_sync, pmr_sb_thr). The construction bonus is the country's and can't be cut
for one company (Pat 15:48Z: "that's fine").

Points (unchanged since 10-14): each month a company earns prosperity x (1 + employed levels / 50, capped at 2)
funds; a full bar (COST_SCALE x (100 x (level + 1)^1.8 + 700), HoI4's curve) is one point. A subsidiary earns none
and buys nothing.

State lives on the company; every value the window shows is mirrored onto the executive (the panel reads
Company.GetExecutive.MakeScope), and the clicks are character-scope scripted GUIs that find the company back as the
owner's company whose executive is that character.

Wiring into generate.py main(), test builds only:

    import company_culture
    cc_plan = company_culture.plan(game, {bk: plain recipes}, goods_cost, goods_tex)
    loc += company_culture.write_all(game, write, header, report, cc_plan, args.out)
"""
import glob
import os
import re

import pdx
import bylaws
import cc_tree
import company_panel
import subsidiaries

TAB = 'pmr_culture'                 # InformationPanel tab id
OWN_GUI = 'gui/pmr_company_culture.gui'
PANEL_GUI = 'gui/company_panel.gui'
CHARTER_FILE = 'common/company_charter_types/00_company_charter_types.txt'
CAL_VERSION = 9                     # bump to make every company re-read its numbers (pmr_cc_on); 4: the wheel;
                                    # 5: a grant per goods line; 6: the subsidiary bundles; 7: the two trees (an older
                                    # company's nodes are points again); 8: q45 (the trees' nodes kept); 9: q49, the
                                    # type's id for the board's wealth (pmr_cc_k_id)
TREES_SINCE = 7                     # a company read in before this gets its nodes back as points

# ---------------------------------------------------------------------------------------------------------------
# Numbers Pat hasn't confirmed (SPEC.md sections 2 and 3): named so they are easy to change.
ROOT_INPUT = 0.02                   # Expansion's root: input goods (the 10-18 founding culture's)
ROOT_THROUGHPUT = 0.03              # Engineering's root: throughput (the same)
INPUT_CUT = 0.10                    # Supply Contracts
THROUGHPUT = 0.10                   # Captive Supply, Market Reach, Process Engineering
EOS_LEVELS = 10                     # Regional Headquarters: economy of scale cap
OUTPUT = (0.12, 0.16)               # Precision Manufacturing, Hallmark Goods: output of the company's main goods
# Research grants (Pat 15:54Z: "each engineering tier should cost a research grant and have that green progress bar
# to grant the benefit. the next tier needs to be locked until the current tiers progress is complete"): buying an
# Engineering tier (points, as before) starts its grant; the owner's investment pool pays GRANT_COST per level the
# company employs every week, a week it can't cover waits, and after GRANT_WEEKS paid weeks the tier is the company's.
# Pat 17:42Z: "lvl 1 engineering should require culture points and research grant": Engineering's root too.
GRANTS = ('er', 'en')
GRANT_WEEKS = 52
GRANT_COST = {'er': (250,), 'en': (500, 1000, 1500)}   # £ per employed level a week, by tier (Pat 2026-10-18 22:28Z,
                                                     # 10-19 00:06Z; q35's); the root's is PMR's pick
LV_LADDER = list(range(100, 20, -5)) + list(range(20, 0, -1))   # employed levels, for a grant's cost
GRANT_VARS = ['pmr_rg_t', 'pmr_rg_w', 'pmr_rg_pay', 'pmr_rg_next', 'pmr_rg_ok', 'pmr_rg_paid']   # on the company;
# pmr_rg_t is the running grant's node (Line.node; 1-3, Process Engineering's tiers, before q48)
HALF = 0.5                          # a subsidiary's share of its parent's throughput and of the country's company bonus
SUB_RANGE = (-40, 15)               # the Subsidiary trait's net throughput, whole percent

# Points
COST_SCALE = 1.25                   # Pat 15:53Z: "10 years on average to finish a tree": a tree's 6 points cost 13,639
                                    # funds, 10 years at 114 a month, the mean rate of the player's companies in the q38
                                    # to q44 logs (EIC 193, Hudson's Bay 128, Ruhr 99, Krupp 74, Dollfus-Mieg 60)
PROSPERITY_LADDER = list(range(100, 0, -5))          # 100, 95 .. 5
SIZE_LADDER = [(n, 1 + n / 50) for n in range(50, 0, -5)]
MAX_LEVEL = 60
TEST_POINTS = 12                    # every level of both trees

INVENTION = 'gfx/interface/icons/invention_icons/{}.dds'
PM_ICON = 'gfx/interface/icons/production_method_icons/{}.dds'
SUB_ICON = INVENTION.format('joint_stock_companies')


def point_cost(level):
    return round(COST_SCALE * (100 * (level + 1) ** 1.8 + 700))


def short(key):
    for p in ('company_', 'building_'):
        if key.startswith(p):
            return key[len(p):]
    return key


def fail(where, msg):
    raise SystemExit(f'company_culture: {where}: {msg}')


def fmt(x):
    s = f'{x:.4f}'.rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'


# ---------------------------------------------------------------------------------------------------------------
# The lines

class Line:
    """A line of tiers bought in order; its tier is the company variable pmr_cc_<key>. tree: 'exp' or 'eng'. root: the
    tree's root (its principle), which the tree's other lines need. sub: the subsidiary its first tier founds (1
    vertical, 2 horizontal; subsidiaries.NUMS). charters: tier -> the vanilla charter type that tier opens. Each node
    (line, tier) has the click code 10 x code + tier (scope:line)."""
    def __init__(self, code, key, tree, names, icons, cost, root=False, sub=0, charters=None):
        self.code, self.key, self.tree, self.names, self.icons, self.cost = code, key, tree, names, icons, cost
        self.root, self.sub, self.charters = root, sub, charters or {}
        self.tiers = len(cost)

    def node(self, t):
        return 10 * self.code + t


LINES = [
    Line(1, 'xr', 'exp', ('Expansion',), (INVENTION.format('manufacturies'),), (1,), root=True),   # 1 point (Pat 18:30Z)
    Line(2, 'vx', 'exp', ('Vertical Integration', 'Supply Contracts', 'Captive Supply'),
         (INVENTION.format('corporate_charters'), INVENTION.format('international_diplomacy'),
          INVENTION.format('shaft_mining')), (1, 2, 3), sub=1,
         charters={2: 'trade_charter', 3: 'monopoly_charter'}),
    Line(3, 'hx', 'exp', ('Diversification', 'Regional Headquarters', 'Market Reach'),
         (INVENTION.format('corporate_management'), PM_ICON.format('skyscraper_trade_nexus'),
          INVENTION.format('international_trade')), (1, 2, 3), sub=2,
         charters={1: 'industry_charter', 2: 'investment_charter', 3: 'colonization_charter'}),
    Line(4, 'er', 'eng', ('Engineering',), (INVENTION.format('mechanical_tools'),), (1,), root=True),
    Line(5, 'en', 'eng', ('Process Engineering', 'Precision Manufacturing', 'Hallmark Goods'),
         (INVENTION.format('conveyers'), PM_ICON.format('precision_tools'), INVENTION.format('crystal_glass')),
         (1, 2, 3)),
]
BY_KEY = {ln.key: ln for ln in LINES}
KEYS = [ln.key for ln in LINES]
# Engineering's second tier by the company's trade (Pat 17:55Z: an opium company's bonus is not "Precision
# Manufacturing"): (name, icon, building groups); a company takes the first whose groups hold its key building's group
# or the nearest parent, else the first. pmr_cc_k_sec is the 1-based row.
SECTORS = (
    ('Precision Manufacturing', PM_ICON.format('precision_tools'), ()),
    ('Crop Science', PM_ICON.format('improved_fertilizer'), ('bg_agriculture', 'bg_plantations', 'bg_rubber')),
    ('Selective Breeding', PM_ICON.format('intensive_grazing'), ('bg_ranching',)),
    ('Deep Prospecting', INVENTION.format('prospecting_tech'), ('bg_mining', 'bg_gold_fields', 'bg_oil_extraction')),
    ('Scientific Forestry', PM_ICON.format('hardwood_selection'), ('bg_logging',)),
    ('Fleet Outfitting', PM_ICON.format('steam_trawlers'), ('bg_fishing', 'bg_whaling')),
    ('Systems Engineering', INVENTION.format('logistics_tech'), ('bg_infrastructure', 'bg_power', 'bg_trade')),
    ('Fine Craftsmanship', PM_ICON.format('realist_art'), ('bg_arts',)),
)
SECTOR_NODE = ('en', 2)


def sector(chain):
    """The SECTORS row (1-based) for a building's group chain, nearest group first."""
    for grp in chain or []:
        for i, (_n, _i, grps) in enumerate(SECTORS, 1):
            if grp in grps:
                return i
    return 1
ROOT_OF = {'exp': 'xr', 'eng': 'er'}
RIVAL = {'vx': 'hx', 'hx': 'vx'}      # Pat 14:43Z: "only one can be picked"
CHARTER_AT = {c: (ln.key, t) for ln in LINES for t, c in ln.charters.items()}
NODES = [(ln, t) for ln in LINES for t in range(1, ln.tiers + 1)]

# Traits of every company: (line, tier) -> executive modifiers. A tier's trait replaces the one before, so each holds
# the line's bonuses up to it. A subsidiary's executive carries none of them, only the Subsidiary trait (sub_traits).
THR, INP, EOS = 'building_throughput_add', 'building_goods_input_mult', 'building_economy_of_scale_level_cap_add'
TRAITS = {
    ('xr', 1): [(INP, -ROOT_INPUT)],
    ('er', 1): [(THR, ROOT_THROUGHPUT)],
    ('vx', 2): [(INP, -INPUT_CUT)],
    ('vx', 3): [(INP, -INPUT_CUT), (THR, THROUGHPUT)],
    ('hx', 2): [(EOS, EOS_LEVELS)],
    ('hx', 3): [(EOS, EOS_LEVELS), (THR, THROUGHPUT)],
    ('en', 1): [(THR, THROUGHPUT)],
}


def trait_key(k, t):
    return f'pmr_cc_{k}_{t}'


def sub_key(n):
    return f'pmr_sb_thr_{"m" if n < 0 else "p"}{abs(n)}'


SUB_TRAITS = [n for n in range(SUB_RANGE[0], SUB_RANGE[1] + 1) if n]   # 0: no trait


# ---------------------------------------------------------------------------------------------------------------
# Reading the game

def companies(game):
    """company key -> (building_types, prestige variables its prestige_goods_trigger reads, has prestige goods), in
    file order."""
    out = {}
    for path in sorted(glob.glob(os.path.join(game, 'common', 'company_types', '*.txt'))):
        text = open(path, encoding='utf-8-sig').read()
        for n in pdx.parse(text):
            if n.is_block and n.key and n.key.startswith('company_'):
                bt = pdx.get(n.value, 'building_types')
                pt = pdx.get(n.value, 'prestige_goods_trigger')
                pvars = []
                if pt:
                    def walk(nodes):
                        for x in nodes:
                            if x.key == 'has_variable' and not x.is_block and re.fullmatch(r'prestige_good_\w+_var', x.value):
                                pvars.append(x.value)
                            elif x.is_block:
                                walk(x.value)
                    walk(pt.value)
                pg = bool(pdx.get(n.value, 'possible_prestige_goods')) or bool(pvars)
                out[n.key] = (pdx.items(bt) if bt else [], sorted(set(pvars)), pg)
    if len(out) < 100:
        fail('common/company_types', f'only {len(out)} company types found')
    return out


def building_groups(game):
    """building key -> its building group and that group's parents, nearest first."""
    parent = {}
    for path in glob.glob(os.path.join(game, 'common', 'building_groups', '*.txt')):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and n.key:
                p = pdx.get(n.value, 'parent_group')
                parent[n.key] = p.value if p else None
    out = {}
    for path in glob.glob(os.path.join(game, 'common', 'buildings', '*.txt')):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and n.key:
                g = pdx.get(n.value, 'building_group')
                chain, x = [], g.value if g else None
                while x and x not in chain:
                    chain.append(x)
                    x = parent.get(x)
                out[n.key] = chain
    return out


def goods_kinds(game):
    """good -> its category (staple, industrial, luxury, military)."""
    out = {}
    for path in glob.glob(os.path.join(game, 'common', 'goods', '*.txt')):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and n.key:
                c = pdx.get(n.value, 'category')
                out[n.key] = c.value if c else None
    return out


class Plan:
    """What the generator decides per company type (plan())."""
    def __init__(self):
        self.comp = {}         # company -> {'key', 'eg', 'pvars', 'pg', 'sb': [vertical list, horizontal list]}
        self.goods = []        # every good a company's Precision Manufacturing names, 1-based
        self.goods_tex = {}    # good -> its icon (vanilla's goods texture)
        self.good_sec = {}     # good -> the SECTORS row of the building making it (its output traits' name)
        self.sb_types = []     # every building type a subsidiary lists, 1-based (subsidiaries.plan_types)
        self.sb_icon, self.sb_points, self.sb_prices = {}, {}, []


RAILWAY = 'building_railway'
RAIL_GROUPS = {'bg_mining', 'bg_logging', 'bg_oil_extraction', 'bg_plantations', 'bg_rubber'}


def plan(game, plain, goods_cost, goods_tex=None):
    """plain: building -> its plain PMR recipes (generate.Recipe). Picks each company's key building (its type with the
    highest output value), the goods Precision Manufacturing raises (the key building's main good, then the next
    type's), and its subsidiaries' industries: the building making each input of the key building, by value, and the
    other building types of the key building's group, by output value; each the company's own aside, and only types
    some vanilla company lists (so a company can own them)."""
    comps = companies(game)
    groups = building_groups(game)
    kind = goods_kinds(game)
    p = Plan()
    p.goods_tex = dict(goods_tex or {})

    def avg(rs, attr):
        tot = {}
        for r in rs:
            for g, q in getattr(r, attr).items():
                tot[g] = tot.get(g, 0) + q * goods_cost.get(g, 0)
        return {g: v / len(rs) for g, v in tot.items() if v > 0}

    out_val = {bk: avg(rs, 'outputs') for bk, rs in plain.items() if rs}
    in_val = {bk: avg(rs, 'inputs') for bk, rs in plain.items() if rs}
    main = {bk: max(v.items(), key=lambda kv: kv[1]) for bk, v in out_val.items() if v}
    total = {bk: sum(v.values()) for bk, v in out_val.items()}
    ownable = {b for bts, _pv, _pg in comps.values() for b in bts if b in main}
    maker, side = {}, {}
    for bk, (good, _v) in main.items():
        if bk in ownable:
            maker.setdefault(good, []).append(bk)
    for bk, v in out_val.items():
        if bk in ownable:
            for good in v:
                side.setdefault(good, []).append(bk)
    for good, bks in side.items():
        maker.setdefault(good, bks)   # a good no building makes first: whoever makes it beside its main good
    for c, (bts, pvars, pg) in comps.items():
        ranked = sorted((b for b in bts if b in main), key=lambda b: -total[b])
        key = ranked[0] if ranked else None
        eg = []
        for b in ranked:
            if main[b][0] not in eg:
                eg.append(main[b][0])
        vert, horiz = [], []
        if key:
            for good in sorted(in_val.get(key, {}), key=lambda g: -in_val[key][g]):
                mk = [x for x in sorted(maker.get(good, []), key=lambda x: -out_val[x].get(good, 0)) if x not in bts]
                if mk and mk[0] not in vert:
                    vert.append(mk[0])
            # Pat 17:50Z: a resource or plantation company's Vertical Integration includes railways
            if (RAIL_GROUPS & set(groups.get(key) or []) and RAILWAY in ownable and RAILWAY not in bts
                    and RAILWAY not in vert):
                vert = vert[:subsidiaries.SB_SIZE - 1] + [RAILWAY]
            # the key building's class, else its parent class and so on (Pat 15:51Z: "always something for
            # horizontal diversification"; a logging company widens to all extraction)
            for grp in groups.get(key) or []:
                horiz = sorted((b for b in ownable if b not in bts and grp in (groups.get(b) or [])),
                               key=lambda b: (-total[b], b))   # ties by name: ownable is a set
                if horiz:
                    break
            if not horiz:
                # no other ownable type in its classes (power plants, art academies): the industries using its main
                # good, else those making goods of its kind (fine art: other luxuries), else the nearest by output value
                good = main[key][0]
                rest = sorted(b for b in ownable if b not in bts and b not in vert)
                kin = lambda b: sum(v for g, v in out_val[b].items() if kind.get(g) == kind.get(good))  # noqa: E731
                horiz = (sorted((b for b in rest if good in in_val.get(b, {})), key=lambda b: (-in_val[b][good], b))
                         or sorted((b for b in rest if kin(b) > 0), key=lambda b: (-kin(b), b))
                         or sorted(rest, key=lambda b: (abs(total[b] - total[key]), b)))
        for b in ranked:
            p.good_sec.setdefault(main[b][0], sector(groups.get(b)))
        p.comp[c] = {'key': key, 'eg': eg[:2], 'pvars': pvars, 'pg': pg, 'sec': sector(groups.get(key)) if key else 1,
                     'bts': sorted(b for b in bts if b in groups),
                     'sb': [vert[:subsidiaries.SB_SIZE], horiz[:subsidiaries.SB_SIZE]]}
    subsidiaries.plan_types(p, game)
    p.goods = sorted({g for v in p.comp.values() for g in v['eg']})
    return p


def gi(p, good):
    return p.goods.index(good) + 1 if good else 0


# ---------------------------------------------------------------------------------------------------------------
# Traits

def trait(key, icon, mods):
    body = ''.join(f'\t\t{k} = {fmt(v)}\n' for k, v in mods)
    return (f'{key} = {{\n\ttype = condition\n\ttexture = "{icon}"\n\n'
            f'\texecutive_modifier = {{\n{body}\t}}\n\n'
            '\tpossible = { always = no }\n\tweight = { value = 0 }\n\tvalue = 0\n}\n')


def output_traits(p):
    """(trait key, icon, modifiers, condition on the company) for Precision Manufacturing and Hallmark Goods: each
    tier's output of one of the company's main goods, picked by the company variables pmr_cc_k_eg1 / eg2."""
    out = []
    for g in p.goods:
        n = gi(p, g)
        for t, val in zip((2, 3), OUTPUT):
            icon = SECTORS[p.good_sec.get(g, 1) - 1][1] if (('en', t) == SECTOR_NODE) else BY_KEY['en'].icons[t - 1]
            out.append((f'pmr_cc_eo_{g}_{t}', icon, [(f'goods_output_{g}_mult', val)],
                        f'var:pmr_cc_en = {t} OR = {{ var:pmr_cc_k_eg1 = {n} var:pmr_cc_k_eg2 = {n} }}'))
    return out


def all_traits(p):
    """Every Company Culture trait key."""
    return ([trait_key(k, t) for k, t in TRAITS] + [sub_key(n) for n in SUB_TRAITS] + [key for key, *_r in output_traits(p)]
            + bylaws.trait_keys())


def traits(p):
    out = ['# Company Culture traits (company_culture.py). Each sits on a company\'s executive; its executive_modifier\n'
           '# applies to the building levels that company owns. Never random (possible no, weight 0, value 0). A\n'
           '# subsidiary\'s executive holds one pmr_sb_thr_ trait only: its throughput in whole percent (pmr_sb_thr).\n\n']
    for (k, t), mods in TRAITS.items():
        out.append(trait(trait_key(k, t), BY_KEY[k].icons[t - 1], mods))
    for n in SUB_TRAITS:
        out.append(trait(sub_key(n), SUB_ICON, [(THR, n / 100)]))
    for key, icon, mods, _w in output_traits(p):
        out.append(trait(key, icon, mods))
    return '\n'.join(out)


def vanilla_modifier_types(game):
    keys = set()
    for path in glob.glob(os.path.join(game, 'common', 'modifier_type_definitions', '*.txt')):
        keys |= set(re.findall(r'^(\w+)\s*=\s*\{', open(path, encoding='utf-8-sig').read(), re.M))
    return keys


def goods_mults(p):
    return sorted(f'goods_output_{g}_mult' for g in p.goods)


def modifier_types(p, game):
    have = vanilla_modifier_types(game)
    if not {'goods_output_hardwood_mult', THR, INP, EOS} <= have:
        fail('common/modifier_type_definitions', 'vanilla\'s modifier types not found')
    out = ['# The per-good output multipliers the traits use: the engine looks them up by the pattern\n'
           '# goods_output_{}_mult, but an undefined one loads empty ("Unknown modifier type"). Vanilla defines some;\n'
           '# these are the rest, styled as vanilla\'s.\n']
    for k in goods_mults(p):
        if k not in have:
            out.append(f'{k} = {{\n\tdecimals = 1\n\tcolor = good\n\tpercent = yes\n\tgame_data = {{ ai_value = 0 }}\n}}\n')
    return '\n'.join(out)


def goods_mult_loc(p, game):
    """Names for the goods modifier types modifier_types() adds: vanilla's own name of the matching _add type, so
    every language reads its own (else the good's name)."""
    have, names = vanilla_modifier_types(game), set()
    for path in glob.glob(os.path.join(game, 'localization', 'english', '*.yml')):
        names |= set(re.findall(r'^ (goods_\w+_add):', open(path, encoding='utf-8-sig').read(), re.M))
    out = []
    for k in goods_mults(p):
        if k in have:
            continue
        add = k[:-len('_mult')] + '_add'
        if add in names:
            out.append(f' {k}:0 "${add}$"')
        else:
            g = k[len('goods_output_'):-len('_mult')]
            out.append(f' {k}:0 "@{g}! ${g}$ ($concept_output_goods$)"')
        out.append(f' {k}_desc:0 ""')
    return out


# ---------------------------------------------------------------------------------------------------------------
# Script

def ladder(trigger, steps, var, ind):
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
            + ';'.join(f"{k}=[THIS.Var('pmr_cc_{k}').GetValue|0]" for k in KEYS) + '"')


def player_log(rec, extra=''):
    return f'if = {{ limit = {{ owner ?= {{ is_player = yes }} }} {log_line(rec, extra)} }}'


KVARS = ['pmr_cc_k_eg1', 'pmr_cc_k_eg2', 'pmr_cc_k_pg', 'pmr_cc_k_sec', 'pmr_cc_k_id'] + subsidiaries.KVARS
PARENT_VARS = [f'pmr_cc_p{k}' for k in KEYS]          # a subsidiary's copy of its parent's tiers
STATE_VARS = [f'pmr_cc_st_{ln.key}_{t}' for ln, t in NODES]
MIRRORED = (['pmr_cc_level', 'pmr_cc_pts', 'pmr_cc_funds', 'pmr_cc_cost', 'pmr_cc_rate', 'pmr_cc_pct', 'pmr_cc_mth',
             'pmr_cc_prosp', 'pmr_cc_size'] + [f'pmr_cc_{k}' for k in KEYS] + STATE_VARS + KVARS
            + subsidiaries.MIRRORED + GRANT_VARS + bylaws.MIRRORED)


def ready(ln, t):
    """Node (ln, t) is next, points, pool and branches aside: the tier before it, and the tree's root for a first
    tier."""
    c = [f'var:pmr_cc_{ln.key} = {t - 1}']
    if t == 1 and not ln.root:
        c.append(f'var:pmr_cc_{ROOT_OF[ln.tree]} = 1')
    return ' '.join(c)


def na(ln):
    """A branch with nothing to found: the company's key building has no input makers, or no other industry in its
    class or any class above it."""
    return f'var:pmr_cc_k_sbp{ln.sub} = 0' if ln.sub else None


def ruled(ln):
    return f'var:pmr_cc_{RIVAL[ln.key]} >= 1' if ln.key in RIVAL else None


def grant_derive():
    """Appended to pmr_cc_derive (company scope, scope:pmr_cc_gco): the next Engineering tier's weekly grant
    (pmr_rg_next: GRANT_COST per employed level, at least one) and whether it can start (pmr_rg_ok: none running and a
    week in the owner's investment pool)."""
    tiers = [(k, t, c) for k in GRANTS for t, c in enumerate(GRANT_COST[k])]
    nxt = ''.join(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ var:pmr_cc_{k} = {t} }} '
                  f'set_variable = {{ name = pmr_rg_next value = {c} }} }}\n' for j, (k, t, c) in enumerate(tiers))
    old = BY_KEY['en'].node(0)
    return ('\t# Engineering\'s next research grant (company_culture.py, GRANT_COST per employed level a week)\n'
            f'\t# a grant read in from before q48 runs a Process Engineering tier by its number\n'
            f'\tif = {{ limit = {{ var:pmr_rg_t > 0 var:pmr_rg_t < 10 }} change_variable = {{ name = pmr_rg_t add = {old} }} }}\n'
            '\tset_local_variable = { name = pmr_rg_lv value = 1 }\n'
            + ladder('company_employed_levels', [(n, n) for n in LV_LADDER], 'pmr_rg_lv', '\t')
            + '\tset_variable = { name = pmr_rg_next value = 0 }\n' + nxt
            + '\tchange_variable = { name = pmr_rg_next multiply = local_var:pmr_rg_lv }\n'
            '\tset_variable = { name = pmr_rg_ok value = 0 }\n'
            '\tif = { limit = { var:pmr_rg_t = 0 var:pmr_rg_next > 0 '
            'owner ?= { investment_pool >= scope:pmr_cc_gco.var:pmr_rg_next } } set_variable = { name = pmr_rg_ok value = 1 } }\n')


def grant_effects(done):
    """pmr_rg_week (the weekly payment) and pmr_rg_done (the tier granted; done: line -> what buying its tier did
    before)."""
    grant = ''.join(f'\t{"if" if j == 0 else "else_if"} = {{\n\t\tlimit = {{ var:pmr_rg_t >= {BY_KEY[k].node(1)} '
                    f'var:pmr_rg_t <= {BY_KEY[k].node(BY_KEY[k].tiers)} }}\n'
                    f'\t\tchange_variable = {{ name = pmr_cc_{k} add = 1 }}\n' + done.get(k, '') + '\t}\n'
                    for j, k in enumerate(GRANTS))
    wlog = ("tier=[THIS.Var('pmr_rg_t').GetValue|0];w=[THIS.Var('pmr_rg_w').GetValue|0];"
            "pay=[THIS.Var('pmr_rg_pay').GetValue|0];paid=[THIS.Var('pmr_rg_paid').GetValue|0];")
    return ('# Weekly (pmr_cc.1) while an Engineering research grant runs (pmr_rg_t its tier): the owner\'s investment pool pays\n'
            f'# pmr_rg_pay, or the week waits; after {GRANT_WEEKS} paid weeks the tier is granted (pmr_rg_done).\n'
            'pmr_rg_week = {\n\tsave_scope_as = pmr_cc_gco\n'
            '\tif = {\n\t\tlimit = { owner ?= { investment_pool >= scope:pmr_cc_gco.var:pmr_rg_pay } }\n'
            '\t\tchange_variable = { name = pmr_rg_pay multiply = -1 }\n'
            '\t\towner = { add_investment_pool = scope:pmr_cc_gco.var:pmr_rg_pay }\n'
            '\t\tchange_variable = { name = pmr_rg_pay multiply = -1 }\n'
            '\t\tchange_variable = { name = pmr_rg_w add = 1 }\n'
            '\t\towner = { change_variable = { name = pmr_cc_rweek add = scope:pmr_cc_gco.var:pmr_rg_pay } }\n'
            '\t\tset_variable = { name = pmr_rg_paid value = 1 }\n\t}\n'
            '\telse = { set_variable = { name = pmr_rg_paid value = 0 } }\n'
            f'\t{player_log("CC_GRANT_WEEK", wlog)}\n'
            f'\tif = {{\n\t\tlimit = {{ var:pmr_rg_w >= {GRANT_WEEKS} }}\n\t\tpmr_rg_done = yes\n\t}}\n'
            '\tif = { limit = { owner ?= { is_player = yes } } pmr_cc_mirror = yes }\n}\n\n'
            '# The research grant is paid: its tier is the company\'s, and the next one can be bought.\n'
            f'pmr_rg_done = {{\n\t{player_log("CC_GRANT_DONE", wlog)}\n' + grant
            + '\tset_variable = { name = pmr_rg_t value = 0 }\n\tset_variable = { name = pmr_rg_w value = 0 }\n'
            '\tset_variable = { name = pmr_rg_pay value = 0 }\n'
            '\tpmr_cc_after_buy = yes\n}\n\n')


def effects(p):
    o = []
    o.append('# Company Culture (company_culture.py). Company scope unless said otherwise. Variables on the company:\n'
             '# pmr_cc_on (calibration version), pmr_cc_funds, pmr_cc_level, pmr_cc_pts (unspent), pmr_cc_cost (funds for\n'
             '# the next point), pmr_cc_rate (funds last month), pmr_cc_<line> (tier completed), pmr_cc_k_* (the company\n'
             '# type\'s numbers: main goods, prestige goods, subsidiaries), pmr_cc_p<line> (a subsidiary\'s copy of its\n'
             '# parent\'s tiers). Everything the window shows is mirrored onto the executive (pmr_cc_mirror), which also\n'
             '# holds pmr_cc_of, the company its traits were set for.\n\n')
    # Init: the company type's numbers.
    chain = ''
    for i, (c, v) in enumerate(sorted(p.comp.items())):
        eg = v['eg']
        vals = {'pmr_cc_k_eg1': gi(p, eg[0]) if eg else 0, 'pmr_cc_k_eg2': gi(p, eg[1]) if len(eg) > 1 else 0,
                'pmr_cc_k_pg': 1 if v['pg'] else 0, 'pmr_cc_k_sec': v['sec'], 'pmr_cc_k_id': i + 1,
                **subsidiaries.kvals(p, v)}
        sets = ' '.join(f'set_variable = {{ name = {k} value = {x} }}' for k, x in vals.items() if x)
        if sets:
            chain += f'\t{"if" if not chain else "else_if"} = {{\n\t\tlimit = {{ is_company_type = company_type:{c} }}\n\t\t{sets}\n\t}}\n'
    zero_k = ''.join(f'\tset_variable = {{ name = {k} value = 0 }}\n' for k in KVARS)
    zero = (['pmr_cc_funds', 'pmr_cc_level', 'pmr_cc_pts', 'pmr_cc_rate'] + [f'pmr_cc_{k}' for k in KEYS] + PARENT_VARS
            + subsidiaries.ZERO + GRANT_VARS)
    o.append('# A company seen for the first time, or after CAL_VERSION changed: zero state where missing, the company\n'
             '# type\'s numbers, its cost. A company read in by an older Company Culture (the 10-18 wheel) gets its\n'
             '# points back for the nodes it had: one per level, as earned; a subsidiary being paid for starts over.\n'
             'pmr_cc_init = {\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_cc_on has_variable = pmr_cc_level var:pmr_cc_on < {TREES_SINCE} }}\n'
             '\t\tset_variable = { name = pmr_cc_pts value = var:pmr_cc_level }\n'
             + ''.join(f'\t\tset_variable = {{ name = pmr_cc_{k} value = 0 }}\n' for k in KEYS)
             + ''.join(f'\t\tset_variable = {{ name = {x} value = 0 }}\n' for x in ('pmr_sb_pick', 'pmr_sb_w', 'pmr_sb_pay'))
             + '\t\texecutive ?= { pmr_cc_strip = yes }\n\t}\n'
             + ''.join(f'\tif = {{ limit = {{ NOT = {{ has_variable = {x} }} }} set_variable = {{ name = {x} value = 0 }} }}\n'
                       for x in zero)
             + zero_k + chain
             + '\tif = { limit = { has_variable = pmr_sb_sig } remove_variable = pmr_sb_sig }   # a subsidiary re-applies\n'
             + f'\tset_variable = {{ name = pmr_cc_on value = {CAL_VERSION} }}\n'
             '\tpmr_cc_set_cost = yes\n\tpmr_cc_derive = yes\n'
             '\t# a subsidiary being paid for pays this build\'s price from now on\n'
             + ''.join(f'\tif = {{ limit = {{ var:pmr_sb_pick = {n} }} set_variable = {{ name = pmr_sb_pay value = var:pmr_sb_pay{n} }} }}\n'
                       for n in subsidiaries.NUMS)
             + '}\n\n')
    # Cost of the next point.
    costs = ''.join(f'\t{"if" if L == 0 else "else_if"} = {{ limit = {{ var:pmr_cc_level <= {L} }} '
                    f'set_variable = {{ name = pmr_cc_cost value = {point_cost(L)} }} }}\n' for L in range(MAX_LEVEL))
    o.append(f'# Funds for the next point: {COST_SCALE} x (100 x (level + 1)^1.8 + 700), HoI4\'s curve.\n'
             'pmr_cc_set_cost = {\n' + costs
             + f'\telse = {{ set_variable = {{ name = pmr_cc_cost value = {point_cost(MAX_LEVEL)} }} }}\n}}\n\n')
    o.append('# Monthly funds: prosperity x size, size = 1 + employed levels / 50 (at most 2), both read by ladder.\n'
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
    o.append('# Numbers derived from the tiers and the owner: the subsidiaries\' weekly costs (subsidiaries.derive).\n'
             'pmr_cc_derive = {\n\tsave_scope_as = pmr_cc_gco\n' + subsidiaries.derive(p.sb_prices) + grant_derive() + '}\n\n')
    # Buy, per line.
    pchain = ''
    for c, v in sorted(p.comp.items()):
        if v['pvars']:
            pchain += (f'\t\t{"if" if not pchain else "else_if"} = {{ limit = {{ is_company_type = company_type:{c} }} '
                       + ' '.join(f'set_variable = {x}' for x in v['pvars']) + ' }\n')
    done = {}
    for ln in LINES:
        k = ln.key
        pay = ''.join(f'\t{"if" if t == 0 else "else_if"} = {{ limit = {{ var:pmr_cc_{k} = {t} }} '
                      f'change_variable = {{ name = pmr_cc_pts subtract = {c} }} }}\n' for t, c in enumerate(ln.cost) if c)
        take = f'\tchange_variable = {{ name = pmr_cc_{k} add = 1 }}\n'
        if ln.sub:
            take += (f'\t# its subsidiary\'s payments start, unless it already has one (a save from before the trees)\n'
                     f'\tif = {{ limit = {{ var:pmr_cc_{k} = 1 var:pmr_sb_d{ln.sub} = 0 }} pmr_sb_start = {{ N = {ln.sub} }} }}\n')
        if k == 'en':
            done[k] = ('\t\t# Hallmark Goods: the variable its prestige goods wait for (05_prestige_goods, or PMR\'s own:\n'
                       '\t\t# generate.py gives the companies vanilla lets make them whenever prosperous a trigger on\n'
                       '\t\t# pmr_cc_hallmark)\n'
                       f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_cc_{k} = 3 }}\n\t\t\tset_variable = pmr_cc_hallmark\n'
                       + pchain.replace('\n\t', '\n\t\t').replace('\t', '\t\t', 1) + '\t\t}\n')
        if k in GRANTS:
            take = ('\t# the tier\'s research grant starts (pmr_rg_t its node); the tier is the company\'s when it is paid\n'
                    '\t# (pmr_rg_week)\n'
                    f'\tset_variable = {{ name = pmr_rg_t value = var:pmr_cc_{k} }}\n'
                    f'\tchange_variable = {{ name = pmr_rg_t add = {ln.node(1)} }}\n'
                    '\tset_variable = { name = pmr_rg_w value = 0 }\n'
                    '\tset_variable = { name = pmr_rg_pay value = var:pmr_rg_next }\n'
                    '\towner ?= { pmr_cc_gclock = yes }\n')
        o.append(f'pmr_cc_buy_{k} = {{\n{pay}{take}\tpmr_cc_after_buy = yes\n'
                 f'\t{player_log("CC_BUY", f"line={k};")}\n}}\n\n')
    o.append(grant_effects(done))
    o.append('# After a node: the derived numbers, the executive\'s traits, and its subsidiaries\' Subsidiary traits.\n'
             'pmr_cc_after_buy = {\n\tpmr_cc_derive = yes\n\tsave_scope_as = pmr_cc_co\n\tpmr_cc_apply = yes\n'
             '\tevery_in_list = {\n\t\tvariable = pmr_subs\n\t\tpmr_cc_sub_sync = yes\n\t}\n\tsave_scope_as = pmr_cc_co\n}\n\n')
    o.append('# The owner\'s investment pool, to the nearest £16, into var $V$ (scope:pmr_cc_gco = this company): the log\'s\n'
             '# reading, since [GetPlayer.GetInvestmentPool] in a debug_log printed 0 (q31). A pool below 0 reads 0.\n'
             'pmr_cc_pool_read = {\n\tset_variable = { name = $V$ value = 0 }\n'
             + ''.join(f'\tset_variable = {{ name = pmr_cc_pt value = var:$V$ }} change_variable = {{ name = pmr_cc_pt add = {2 ** e} }} '
                       'if = { limit = { owner ?= { investment_pool >= scope:pmr_cc_gco.var:pmr_cc_pt } } '
                       'set_variable = { name = $V$ value = var:pmr_cc_pt } }\n' for e in range(26, 3, -1))
             + '}\n\n'
             '# Country scope: starts the weekly clock (pmr_cc.1) unless it is running. pmr_cc_gclock outlives a week by two\n'
             '# days, so a live clock is never started twice; the monthly pulse restarts a broken chain.\n'
             'pmr_cc_gclock = {\n\tif = {\n\t\tlimit = { NOT = { has_variable = pmr_cc_gclock } }\n'
             '\t\tset_variable = { name = pmr_cc_gclock days = 9 }\n\t\ttrigger_event = { id = pmr_cc.1 days = 7 }\n\t}\n}\n\n')
    # A click.
    click = ''
    for ln, t in NODES:
        click += (f'\t{"if" if not click else "else_if"} = {{\n\t\tlimit = {{ scope:line = {ln.node(t)} var:pmr_cc_{ln.key} = {t - 1} '
                  f'pmr_cc_open_{ln.key} = yes pmr_cc_afford_{ln.key} = yes }}\n\t\tpmr_cc_buy_{ln.key} = yes\n\t}}\n')
        if ln.sub and t == 1:
            click += (f'\telse_if = {{\n\t\tlimit = {{ scope:line = {ln.node(t)} pmr_sb_again_{ln.sub} = yes }}\n'
                      f'\t\tpmr_sb_start = {{ N = {ln.sub} }}\n\t}}\n')
    o.append('# The player clicked node scope:line (Line.node in company_culture.py): it is bought with points already earned,\n'
             '# or a subsidiary that went is paid for again, or nothing happens (Pat 12:37Z: no queue).\n'
             'pmr_cc_click = {\n\tsave_scope_as = pmr_cc_co\n\tpmr_cc_derive = yes\n' + click + '\tpmr_cc_mirror = yes\n}\n\n')
    # AI.
    def step(k, t, kw='else_if'):
        return (f'\t{kw} = {{\n\t\tlimit = {{ var:pmr_cc_{k} = {t - 1} pmr_cc_open_{k} = yes }}\n'
                f'\t\tif = {{ limit = {{ pmr_cc_afford_{k} = yes }} pmr_cc_buy_{k} = yes }}\n\t}}\n')
    steps = ('\tif = {\n\t\tlimit = { var:pmr_cc_vx = 0 var:pmr_cc_hx = 0 pmr_cc_open_vx = yes pmr_cc_open_hx = yes }\n'
             '\t\tif = {\n\t\t\tlimit = { var:pmr_cc_pts >= 1 }\n'
             '\t\t\trandom_list = {\n\t\t\t\t1 = { pmr_cc_buy_vx = yes }\n\t\t\t\t1 = { pmr_cc_buy_hx = yes }\n\t\t\t}\n\t\t}\n\t}\n'
             + step('vx', 1) + step('hx', 1)
             + ''.join(step(k, t) for k, t in AI_ORDER))
    o.append('# AI companies: both roots when affordable and a gone subsidiary paid for again at once; with points, Vertical or Horizontal\n'
             '# at random where both are open (the investment pool holding a week of the subsidiary), then the first open step\n'
             '# of AI_ORDER, bought when affordable, otherwise saved for.\n'
             'pmr_cc_ai_step = {\n' + steps + '}\n\n'
             'pmr_cc_ai_buy = {\n'
             '\tif = { limit = { pmr_cc_open_xr = yes pmr_cc_afford_xr = yes } pmr_cc_buy_xr = yes }\n'
             '\tif = { limit = { pmr_cc_open_er = yes pmr_cc_afford_er = yes } pmr_cc_buy_er = yes }\n'
             + ''.join(f'\tif = {{ limit = {{ pmr_sb_again_{n} = yes }} pmr_sb_start = {{ N = {n} }} }}\n' for n in subsidiaries.NUMS)
             + '\tif = {\n\t\tlimit = { var:pmr_cc_pts >= 1 }\n\t\tpmr_cc_ai_step = yes\n'
             '\t\tif = { limit = { var:pmr_cc_pts >= 1 } pmr_cc_ai_step = yes }\n\t}\n}\n\n')
    # Traits on the executive.
    def line_fx(k, table, var):
        tiers = sorted(t for kk, t in table if kk == k)
        keys = {t: trait_key(k, t) for t in tiers}
        out = ''
        for n, t in enumerate(reversed(tiers)):
            cond = f'var:{var} >= {t}' if n == 0 else f'var:{var} = {t}'
            out += f'\t\t{"if" if n == 0 else "else_if"} = {{\n\t\t\tlimit = {{ scope:pmr_cc_co = {{ {cond} }} }}\n'
            out += ''.join(f'\t\t\tif = {{ limit = {{ has_trait = {x} }} remove_trait = {x} }}\n'
                           for u, x in keys.items() if u != t)
            out += f'\t\t\tif = {{ limit = {{ NOT = {{ has_trait = {keys[t]} }} }} add_trait = {keys[t]} }}\n\t\t}}\n'
        out += '\t\telse = {\n' + ''.join(f'\t\t\tif = {{ limit = {{ has_trait = {x} }} remove_trait = {x} }}\n'
                                          for x in keys.values()) + '\t\t}\n'
        return out
    full = ''.join(f'\t\t# {k}\n' + line_fx(k, TRAITS, f'pmr_cc_{k}') for k in dict.fromkeys(k for k, _t in TRAITS))
    sub = ('\t\t# Subsidiary (pmr_sb_thr, a subsidiary\'s only)\n'
           + ''.join(f'\t\tif = {{ limit = {{ has_trait = {sub_key(n)} NOT = {{ scope:pmr_cc_co = {{ var:pmr_sb_thr ?= {n} }} }} }} '
                     f'remove_trait = {sub_key(n)} }}\n' for n in SUB_TRAITS)
           + ''.join(f'\t\tif = {{ limit = {{ NOT = {{ has_trait = {sub_key(n)} }} scope:pmr_cc_co = {{ var:pmr_sb_thr ?= {n} }} }} '
                     f'add_trait = {sub_key(n)} }}\n' for n in SUB_TRAITS))
    keyed = ''.join(f'\t\tif = {{ limit = {{ has_trait = {key} NOT = {{ scope:pmr_cc_co = {{ {w} }} }} }} remove_trait = {key} }}\n'
                    f'\t\tif = {{ limit = {{ NOT = {{ has_trait = {key} }} scope:pmr_cc_co = {{ {w} }} }} add_trait = {key} }}\n'
                    for key, _i, _m, w in output_traits(p))
    o.append('# The executive\'s traits for the company\'s tiers, or for a subsidiary the Subsidiary trait. An executive\n'
             '# who came from another company with Culture traits loses them first (pmr_cc_strip). Company scope.\n'
             'pmr_cc_apply = {\n\tsave_scope_as = pmr_cc_co\n' + bylaws.src_scope('\t') + '\texecutive ?= {\n'
             '\t\tif = {\n\t\t\tlimit = {\n\t\t\t\thas_variable = pmr_cc_of\n\t\t\t\tNOT = { var:pmr_cc_of ?= scope:pmr_cc_co }\n\t\t\t}\n'
             '\t\t\tpmr_cc_strip = yes\n\t\t}\n'
             '\t\tset_variable = { name = pmr_cc_of value = scope:pmr_cc_co }\n'
             + full + keyed + sub + bylaws.apply_traits('\t\t') + '\t}\n}\n\n')
    o.append('# Character scope: every Company Culture trait off. When an executive changes company and on disbanding.\n'
             'pmr_cc_strip = {\n' + ''.join(f'\tif = {{ limit = {{ has_trait = {x} }} remove_trait = {x} }}\n' for x in all_traits(p))
             + '\tremove_variable = pmr_cc_of\n}\n\n')
    sub_log = ("parent=[THIS.Var('pmr_parent').GetCompany.GetNameNoFormatting];"
               + ''.join(f"p{k}=[THIS.Var('pmr_cc_p{k}').GetValue|0];" for k in KEYS)
               + "thr=[THIS.Var('pmr_sb_thr').GetValue|0];country=[THIS.Var('pmr_sb_cthr').GetValue|2];")
    # the parent's tree throughput by its tiers, in percent: each line's highest tier with a trait holds the line's
    tree = ''
    for k in dict.fromkeys(k for k, _t in TRAITS):
        tiers = sorted((t for kk, t in TRAITS if kk == k and any(m == THR for m, _v in TRAITS[(kk, t)])), reverse=True)
        for i, t in enumerate(tiers):
            thr = sum(v for m, v in TRAITS[(k, t)] if m == THR) * 100 * HALF
            tree += (f'\t{"if" if i == 0 else "else_if"} = {{ limit = {{ var:pmr_cc_p{k} >= {t} }} '
                     f'change_variable = {{ name = pmr_sb_thr add = {fmt(thr)} }} }}\n')
    o.append('# A subsidiary (pmr_sub; monthly, and when its parent buys a node): its copy of the parent\'s tiers, read once the\n'
             '# parent is read in at this CAL_VERSION, and its Subsidiary trait: half the parent\'s tree throughput less half\n'
             '# the country\'s Company Throughput Bonus, in whole percent (pmr_sb_thr; pmr_sb_cthr the country\'s, in percent).\n'
             'pmr_cc_sub_sync = {\n\tsave_scope_as = pmr_cc_co\n\tclear_saved_scope = pmr_cc_par\n'
             '\tvar:pmr_parent ?= { save_scope_as = pmr_cc_par }\n'
             f'\tif = {{\n\t\tlimit = {{ scope:pmr_cc_par ?= {{ var:pmr_cc_on ?= {CAL_VERSION} }} }}\n'
             + ''.join(f'\t\tset_variable = {{ name = pmr_cc_p{k} value = scope:pmr_cc_par.var:pmr_cc_{k} }}\n' for k in KEYS)
             + '\t}\n\telse = {\n' + ''.join(f'\t\tset_variable = {{ name = pmr_cc_p{k} value = 0 }}\n' for k in KEYS) + '\t}\n'
             '\tset_variable = { name = pmr_sb_thr value = 0 }\n' + tree
             + '\tset_variable = { name = pmr_sb_cthr value = owner.modifier:country_company_throughput_bonus_add }\n'
             '\tchange_variable = { name = pmr_sb_cthr multiply = 100 }\n'
             f'\tset_local_variable = {{ name = pmr_sb_c value = var:pmr_sb_cthr }}\n'
             f'\tchange_local_variable = {{ name = pmr_sb_c multiply = {fmt(HALF)} }}\n'
             '\tchange_variable = { name = pmr_sb_thr subtract = local_var:pmr_sb_c }\n'
             '\tround_variable = { name = pmr_sb_thr nearest = 1 }\n'
             f'\tclamp_variable = {{ name = pmr_sb_thr min = {SUB_RANGE[0]} max = {SUB_RANGE[1]} }}\n'
             '\tpmr_bl_sub_focus = yes\n'
             # perf review S-5: the traits only change with pmr_sb_thr, the parent's Pay and Hours bylaws or a new
             # executive, so they are applied only then (pmr_sb_sig, cleared by pmr_cc_init)
             '\tset_local_variable = { name = pmr_sb_s value = 0 }\n'
             '\tif = {\n\t\tlimit = { scope:pmr_cc_par ?= { has_variable = pmr_bl_1 has_variable = pmr_bl_2 } }\n'
             '\t\tset_local_variable = { name = pmr_sb_s value = scope:pmr_cc_par.var:pmr_bl_1 }\n'
             '\t\tchange_local_variable = { name = pmr_sb_s multiply = 10 }\n'
             '\t\tchange_local_variable = { name = pmr_sb_s add = scope:pmr_cc_par.var:pmr_bl_2 }\n'
             '\t\tchange_local_variable = { name = pmr_sb_s multiply = 1000 }\n\t}\n'
             '\tchange_local_variable = { name = pmr_sb_s add = var:pmr_sb_thr }\n'
             '\tif = {\n\t\tlimit = {\n\t\t\tOR = {\n\t\t\t\tNOT = { var:pmr_sb_sig ?= local_var:pmr_sb_s }\n'
             '\t\t\t\texecutive ?= { NOT = { var:pmr_cc_of ?= scope:pmr_cc_co } }\n\t\t\t}\n\t\t}\n'
             '\t\tset_variable = { name = pmr_sb_sig value = local_var:pmr_sb_s }\n'
             '\t\tpmr_cc_apply = yes\n\t}\n'
             f'\t{player_log("CC_SUB", sub_log)}\n}}\n\n')
    # Node states.
    states = ''
    for ln, t in NODES:
        k = ln.key
        st = f'pmr_cc_st_{k}_{t}'

        def s(n):
            return f'set_variable = {{ name = {st} value = {n} }}'
        states += f'\t# {k} {t}\n'
        if ln.sub and t == 1:
            n = ln.sub
            states += (f'\tif = {{\n\t\tlimit = {{ var:pmr_cc_{k} >= 1 }}\n'
                       f'\t\tif = {{ limit = {{ var:pmr_sb_pick = {n} }} {s(6)} }}\n'
                       f'\t\telse_if = {{ limit = {{ var:pmr_sb_d{n} = 1 }} {s(4)} }}\n'
                       f'\t\telse_if = {{ limit = {{ pmr_sb_again_{n} = yes }} {s(1)} }}\n'
                       f'\t\telse = {{ {s(2)} }}\n\t}}\n')
        else:
            states += f'\tif = {{ limit = {{ var:pmr_cc_{k} >= {t} }} {s(4)} }}\n'
            if k in GRANTS:
                states += f'\telse_if = {{ limit = {{ var:pmr_rg_t = {ln.node(t)} }} {s(6)} }}\n'
        if na(ln):
            states += f'\telse_if = {{ limit = {{ {na(ln)} }} {s(7)} }}\n'
        if ruled(ln):
            states += f'\telse_if = {{ limit = {{ {ruled(ln)} }} {s(5)} }}\n'
        states += (f'\telse_if = {{\n\t\tlimit = {{ {ready(ln, t)} }}\n'
                   f'\t\tif = {{ limit = {{ pmr_cc_open_{k} = yes pmr_cc_afford_{k} = yes }} {s(1)} }}\n'
                   f'\t\telse = {{ {s(2)} }}\n\t}}\n'
                   f'\telse = {{ {s(0)} }}\n')
    copies = ''.join(f'\t\tif = {{ limit = {{ scope:pmr_cc_co = {{ has_variable = {x} }} }} '
                     f'set_variable = {{ name = {x} value = scope:pmr_cc_co.var:{x} }} }}\n'
                     f'\t\telse_if = {{ limit = {{ has_variable = {x} }} remove_variable = {x} }}\n' for x in MIRRORED)
    o.append('# The window\'s numbers, mirrored onto the executive (the panel reads Company.GetExecutive.MakeScope). Node\n'
             '# states pmr_cc_st_<line>_<tier>: 0 locked (a tier before it, or its tree\'s root), 1 a click buys it (or pays\n'
             '# for a subsidiary that went again), 2 next but short of points or of a week in the investment pool, 4 bought,\n'
             '# 5 ruled out by the other branch, 6 its subsidiary being paid for or its research grant running, 7 nothing to\n'
             '# found for this company.\n'
             'pmr_cc_states = {\n' + states + '}\n\n'
             'pmr_cc_mirror = {\n\tsave_scope_as = pmr_cc_co\n\tpmr_cc_states = yes\n'
             '\tset_variable = { name = pmr_cc_pct value = var:pmr_cc_funds }\n'
             '\tchange_variable = { name = pmr_cc_pct multiply = 100 }\n'
             '\tchange_variable = { name = pmr_cc_pct divide = var:pmr_cc_cost }\n'
             '\tif = {\n\t\tlimit = { var:pmr_cc_rate > 0 }\n'
             '\t\tset_variable = { name = pmr_cc_mth value = var:pmr_cc_cost }\n'
             '\t\tchange_variable = { name = pmr_cc_mth subtract = var:pmr_cc_funds }\n'
             '\t\tchange_variable = { name = pmr_cc_mth divide = var:pmr_cc_rate }\n'
             '\t\tchange_variable = { name = pmr_cc_mth add = 0.99 }\n'
             '\t\tround_variable = { name = pmr_cc_mth nearest = 1 }\n\t}\n'
             '\telse = { set_variable = { name = pmr_cc_mth value = -1 } }\n'
             '\texecutive ?= {\n' + copies + '\t}\n}\n\n')
    o.append('# Monthly, every company in the world (from each country\'s monthly pulse). A subsidiary follows its parent and\n'
             '# earns nothing. The mirror only for the player\'s companies; an AI company\'s is brought up to date when its\n'
             '# window opens (pmr_cc_view_sgui).\n'
             'pmr_cc_tick = {\n\tsave_scope_as = pmr_cc_co\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:pmr_cc_on ?= {CAL_VERSION} }} }}\n\t\tpmr_cc_init = yes\n\t}}\n'
             '\tif = {\n\t\tlimit = { has_variable = pmr_sub }\n\t\tpmr_cc_sub_sync = yes\n\t}\n'
             '\telse = {\n\t\tpmr_cc_earn = yes\n\t\tpmr_cc_derive = yes\n\t\tpmr_bl_month = yes\n'
             '\t\tif = {\n\t\t\tlimit = { owner ?= { is_player = no } }\n\t\t\tpmr_cc_ai_buy = yes\n\t\t}\n'
             '\t\tif = {\n\t\t\tlimit = { executive ?= { NOT = { var:pmr_cc_of ?= scope:pmr_cc_co } } }\n\t\t\tpmr_cc_apply = yes\n\t\t}\n'
             '\t\tif = {\n\t\t\tlimit = { owner ?= { is_player = yes } }\n\t\t\tpmr_cc_mirror = yes\n'
             f'\t\t\t{log_line("CC")}\n\t\t}}\n\t}}\n}}\n\n')
    o.append('# The window was opened, a company was founded or the game started: bring it up to date without earning.\n'
             'pmr_cc_refresh = {\n\tsave_scope_as = pmr_cc_co\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:pmr_cc_on ?= {CAL_VERSION} }} }}\n\t\tpmr_cc_init = yes\n\t}}\n'
             '\tif = {\n\t\tlimit = { has_variable = pmr_sub }\n\t\tpmr_cc_sub_sync = yes\n\t}\n'
             '\telse = {\n\t\tpmr_cc_derive = yes\n\t\tpmr_bl_init = yes\n\t\tpmr_bl_focus = yes\n\t\tpmr_bl_count = yes\n'
             '\t\tif = {\n\t\t\tlimit = { executive ?= { NOT = { var:pmr_cc_of ?= scope:pmr_cc_co } } }\n\t\t\tpmr_cc_apply = yes\n\t\t}\n'
             '\t}\n\tpmr_cc_mirror = yes\n}\n\n')
    o.append('# Character scope (an executive, from the window): the owner\'s company this character runs, scope:line kept.\n'
             'pmr_cc_with_company = {\n\tsave_scope_as = pmr_cc_exec\n'
             '\towner ?= {\n\t\tevery_company = {\n\t\t\tlimit = { executive ?= scope:pmr_cc_exec }\n\t\t\t$EFFECT$ = yes\n\t\t}\n\t}\n}\n\n')
    return (''.join(o) + subsidiaries.effects(p) + bylaws.effects(player_log)
            + bylaws.wealth(p, subsidiaries.NUMS, subsidiaries.SLOTS))


# The order AI companies buy in after the roots and their branch (a step whose line is not open is passed over; the
# first open step is bought when affordable, otherwise the company saves for it).
AI_ORDER = [('en', 1), ('vx', 2), ('hx', 2), ('en', 2), ('vx', 3), ('hx', 3), ('en', 3)]


def triggers():
    o = ['# Company Culture (company_culture.py). Company scope.\n\n'
         '# pmr_cc_open_<line>: the line\'s next tier can be bought, points aside: its tree\'s root for the first tier, the\n'
         '# other branch not taken, and for a branch\'s first tier something to found and, unless a subsidiary already\n'
         '# exists (a save from before the trees), a week of its payment in the investment pool (pmr_sb_ok<n>).\n']
    for ln in LINES:
        k = ln.key
        c = [f'var:pmr_cc_{k} < {ln.tiers}']
        if not ln.root:
            c.append(f'var:pmr_cc_{ROOT_OF[ln.tree]} = 1')
        if ruled(ln):
            c.append(f'var:pmr_cc_{RIVAL[k]} = 0')
        if ln.sub:
            n = ln.sub
            c += [f'var:pmr_cc_k_sbp{n} > 0', f'OR = {{ var:pmr_cc_{k} > 0 var:pmr_sb_d{n} = 1 var:pmr_sb_ok{n} = 1 }}']
        if k in GRANTS:   # no grant running, and a week of the next in the pool
            c += ['var:pmr_rg_t = 0', 'var:pmr_rg_ok = 1']
        o.append(f'pmr_cc_open_{k} = {{\n' + ''.join(f'\t{x}\n' for x in c) + '}\n\n')
    o.append('# The points for each line\'s next tier.\n')
    for ln in LINES:
        alts = ''.join(f'\t\tAND = {{ var:pmr_cc_{ln.key} = {t} var:pmr_cc_pts >= {c} }}\n' for t, c in enumerate(ln.cost))
        o.append(f'pmr_cc_afford_{ln.key} = {{\n\tOR = {{\n{alts}\t}}\n}}\n\n')
    o.append('# pmr_sb_again_<n>: the branch is bought, its subsidiary went (dissolved under 5 levels) and none is paid for:\n'
             '# a click on its first node pays for it again.\n')
    for ln in LINES:
        if ln.sub:
            n = ln.sub
            o.append(f'pmr_sb_again_{n} = {{\n\tvar:pmr_cc_{ln.key} >= 1\n\tvar:pmr_sb_d{n} = 0\n\tvar:pmr_sb_ok{n} = 1\n}}\n\n')
    o.append('# An Engineering research grant runs (pmr_rg_week).\n'
             'pmr_rg_running = {\n\thas_variable = pmr_rg_t\n\tvar:pmr_rg_t > 0\n}\n\n'
             '# The weekly clock (pmr_cc.1) has work for this company: a subsidiary being paid for, a research grant.\n'
             'pmr_cc_weekly = {\n\tOR = {\n\t\tpmr_sb_paying = yes\n\t\tpmr_rg_running = yes\n\t}\n}\n\n')
    return ''.join(o) + subsidiaries.triggers()


def sguis():
    picks = ''.join(f'\t\t\tAND = {{ scope:line = {ln.node(t)} var:pmr_cc_st_{ln.key}_{t} ?= 1 }}\n' for ln, t in NODES)
    return ('# Company Culture window (company_culture.py). Character scope: the company\'s executive, as the panel reads\n'
            '# Company.GetExecutive.MakeScope. scope:line is the node clicked (Line.node in company_culture.py).\n\n'
            'pmr_cc_pick_sgui = {\n\tscope = character\n\tsaved_scopes = { line }\n'
            '\tis_valid = {\n\t\towner ?= { is_player = yes }\n\t\tOR = {\n' + picks + '\t\t}\n\t}\n'
            '\teffect = {\n\t\tpmr_cc_with_company = { EFFECT = pmr_cc_click }\n\t}\n}\n\n'
            '# The Show button while the executive has no numbers yet (a new executive this month, a save from before\n'
            '# Company Culture) brings the company up to date.\n'
            'pmr_cc_refresh_sgui = {\n\tscope = character\n'
            '\teffect = {\n\t\tpmr_cc_with_company = { EFFECT = pmr_cc_refresh }\n\t}\n}\n\n'
            '# The tab and its Open button: as the refresh, and the executive kept on the viewing player\'s country\n'
            '# (pmr_cc_exec), where the full-screen window (ingame_hud.gui, outside the company panel) finds the company.\n'
            'pmr_cc_view_sgui = {\n\tscope = character\n\tsaved_scopes = { player }\n'
            '\teffect = {\n\t\tscope:player = {\n\t\t\tset_variable = { name = pmr_cc_exec value = root }\n\t\t}\n'
            '\t\tpmr_cc_with_company = { EFFECT = pmr_cc_refresh }\n\t}\n}\n\n' + bylaws.sguis())


ON_ACTIONS = '''# Company Culture (company_culture.py). Appended to vanilla on_actions the documented way.
on_game_started_after_lobby = { on_actions = { pmr_cc_game_started } }
on_monthly_pulse_country = { on_actions = { pmr_cc_monthly_country } }
on_company_established = { on_actions = { pmr_cc_on_company_established } }
on_company_disbanded = { on_actions = { pmr_cc_on_company_disbanded } }

# No root. Every company's numbers and window from the first day, before any monthly pulse.
pmr_cc_game_started = {
	effect = {
		every_country = {
			every_company = {
				pmr_cc_refresh = yes
			}
		}
	}
}

# Root = country. Every company earns, buys (AI companies), counts its board (bylaws.py) and keeps its executive's
# traits; a company paying keeps the weekly clock going; the country's subsidiary slots are recounted (subsidiaries.py),
# and the Trade Unions' answer to harsh bylaws (bylaws.py).
pmr_cc_monthly_country = {
	trigger = { NOT = { has_global_variable = pmr_ticks_paused } }   # the test pause (perf review S-6)
	effect = {
		every_company = {
			pmr_cc_tick = yes
		}
		if = {
			limit = { any_company = { pmr_cc_weekly = yes } }
			pmr_cc_gclock = yes
		}
		pmr_sb_slots = yes
		pmr_bl_country = yes
	}
}

# Root = country, scope:company = the company founded: its numbers and window at once.
pmr_cc_on_company_established = {
	effect = {
		scope:company ?= {
			pmr_cc_refresh = yes
		}
	}
}

# Root = country, scope:company = the company disbanded: its executive loses its Culture traits (Pat 04:00Z); a
# subsidiary leaves its parent's list, a parent's subsidiaries go their own way (subsidiaries.py).
pmr_cc_on_company_disbanded = {
	effect = {
		scope:company ?= {
			executive ?= {
				pmr_cc_strip = yes
			}
		}
		pmr_sb_disbanded = yes
	}
}
'''

EVENTS = '''namespace = pmr_cc

# Country, every 7 days while one of its companies pays for a subsidiary (pmr_cc_gclock starts it): each payment's
# week (pmr_sb_week) and the week's total for the investment pool's tooltip (pmr_cc_gweek). 1.14.5 runs no weekly
# on_action for script, so the event re-arms itself.
pmr_cc.1 = {
	type = country_event
	hidden = yes
	immediate = {
		set_variable = { name = pmr_cc_gweek value = 0 }
		set_variable = { name = pmr_cc_rweek value = 0 }
		every_company = {
			limit = { pmr_cc_weekly = yes var:pmr_cc_on ?= CAL_VERSION }
			if = { limit = { pmr_sb_paying = yes } pmr_sb_week = yes }
			if = { limit = { pmr_rg_running = yes } pmr_rg_week = yes }
		}
		if = {
			limit = { any_company = { pmr_cc_weekly = yes } }
			set_variable = { name = pmr_cc_gclock days = 9 }
			trigger_event = { id = pmr_cc.1 days = 7 }
		}
		else = {
			remove_variable = pmr_cc_gclock
			set_variable = { name = pmr_cc_gweek value = 0 }
			set_variable = { name = pmr_cc_rweek value = 0 }
		}
	}
}
'''

TEST_DECISION = f'''# Company Culture test decision (test builds only). The AI never takes it. Gives each of the player's companies
# {TEST_POINTS} Culture points (not levels) and refreshes its window. Writes PMR;rec=CC_TEST lines.
pmr_cc_test_points_decision = {{
	is_shown = {{ always = yes }}
	possible = {{ always = yes }}
	when_taken = {{
		every_company = {{
			limit = {{ NOT = {{ has_variable = pmr_sub }} }}
			save_scope_as = pmr_cc_co
			if = {{
				limit = {{ NOT = {{ var:pmr_cc_on ?= {CAL_VERSION} }} }}
				pmr_cc_init = yes
			}}
			change_variable = {{ name = pmr_cc_pts add = {TEST_POINTS} }}
			pmr_cc_refresh = yes
			{{LOG}}
		}}
	}}
	ai_chance = {{ value = 0 }}
}}

# Test builds only: every research grant of the player's companies is paid up, so its tier is granted at the next
# weekly tick. Writes PMR;rec=CC_GRANT_WEEK lines from there.
pmr_rg_test_finish_decision = {{
	is_shown = {{ always = yes }}
	possible = {{ always = yes }}
	when_taken = {{
		every_company = {{
			limit = {{ pmr_rg_running = yes }}
			set_variable = {{ name = pmr_rg_w value = {GRANT_WEEKS - 1} }}
		}}
	}}
	ai_chance = {{ value = 0 }}
}}
'''


def charters(game):
    """The vanilla charter types, each possible only for a company holding the node that opens it (CHARTER_AT; SPEC.md
    section 2). A subsidiary buys no nodes, so it never takes a charter (Pat 14:43Z)."""
    text = open(os.path.join(game, CHARTER_FILE), encoding='utf-8-sig').read()
    edits = []
    for n in pdx.parse(text):
        if not (n.is_block and n.key in CHARTER_AT):
            continue
        k, t = CHARTER_AT[n.key]
        check = (f'has_variable = pmr_cc_{k}\n\t\tvar:pmr_cc_{k} >= {t}  # PMR Company Culture: the '
                 f'{BY_KEY[k].names[t - 1]} node')
        pos = pdx.get(n.value, 'possible')
        if pos:
            edits.append((pos.start + text[pos.start:].index('{') + 1, f'\n\t\t{check}'))
        else:
            edits.append((n.start + text[n.start:].index('{') + 1, f'\n\tpossible = {{\n\t\t{check}\n\t}}'))
        aip = pdx.get(n.value, 'ai_possible')
        if not aip:
            fail(CHARTER_FILE, f'{n.key} has no ai_possible')
        edits.append((aip.start + text[aip.start:].index('{') + 1, f'\n\t\t{check}'))
    if len(set(edits)) != 2 * len(CHARTER_AT):
        fail(CHARTER_FILE, f'found {len(edits) // 2} of the {len(CHARTER_AT)} charter types')
    for at, ins in sorted(edits, reverse=True):
        text = text[:at] + ins + text[at:]
    return ('# PMR Company Culture (company_culture.py): vanilla\'s charter types, each possible only for a company that\n'
            '# holds the node opening it. The engine drops a charter whose possible fails.\n' + text)


DEFINE = ('# PMR Company Culture: charters cost no authority (their nodes cost points). Game-wide. Vanilla: 100.\n'
          'NEconomy = {\n\tCOMPANY_CHARTER_AUTHORITY_COST = 0\n}\n')


def viewing_value():
    return ('# Company Culture (company_culture.py). Country scope.\n'
            '# 1 once the player has opened a Company Culture tab (pmr_cc_view_sgui): the full-screen window shows only then.\n'
            'pmr_cc_viewing = {\n\tvalue = 0\n\tif = {\n\t\tlimit = { has_variable = pmr_cc_exec }\n\t\tvalue = 1\n\t}\n}\n\n')


# ---------------------------------------------------------------------------------------------------------------
# Text

def custom_loc(p):
    """Character scope (the executive, mirrored numbers): each node's tooltip line, and the company's own goods."""
    out = ['# Company Culture (company_culture.py). Character scope: a company\'s executive, which holds the company\'s\n'
           '# numbers (pmr_cc_mirror).\n\n']

    def entry(key, cases, default='PMR_EMPTY'):
        body = ''.join(f'\ttext = {{\n\t\ttrigger = {{ {trig} }}\n\t\tlocalization_key = {lk}\n\t}}\n' for trig, lk in cases)
        return (f'{key} = {{\n\ttype = character\n\trandom_valid = no\n{body}'
                f'\ttext = {{\n\t\tlocalization_key = {default}\n\t}}\n}}\n')
    for slot in ('eg1', 'eg2'):
        out.append(entry(f'pmr_cc_good_{slot}', [(f'var:pmr_cc_k_{slot} ?= {gi(p, g)}', g) for g in p.goods]))
    for ln, t in NODES:
        out.append(entry(f'pmr_cc_why_{ln.key}_{t}', why_cases(ln, t), 'PMR_CC_WHY_LOCKED'))
    out.append(entry('pmr_cc_fx_eg2_2', [('var:pmr_cc_k_eg2 ?= 0', 'PMR_EMPTY')], 'PMR_CC_FX_EG2_2'))
    out.append(entry('pmr_cc_fx_eg2_3', [('var:pmr_cc_k_eg2 ?= 0', 'PMR_EMPTY')], 'PMR_CC_FX_EG2_3'))
    out.append(entry('pmr_cc_fx_pg', [('var:pmr_cc_k_pg ?= 0', 'PMR_EMPTY')], 'PMR_CC_FX_PG'))
    out.append(entry(f'pmr_cc_name_{SECTOR_NODE[0]}_{SECTOR_NODE[1]}',
                     [(f'var:pmr_cc_k_sec ?= {i}', f'PMR_CC_SEC_{i}') for i in range(2, len(SECTORS) + 1)], 'PMR_CC_SEC_1'))
    return '\n'.join(out) + '\n' + bylaws.custom_loc()


def why_cases(ln, t):
    """Custom loc cases naming why node (line, tier) is in its state (pmr_cc_st_<line>_<tier>, pmr_cc_states): its
    tooltip (Pat 20:37Z: the lock reason in the tooltip)."""
    k = ln.key
    st = f'var:pmr_cc_st_{k}_{t}'
    cases = [(f'{st} ?= 1', 'PMR_CC_WHY_BUY'), (f'{st} ?= 4', 'PMR_CC_WHY_DONE')]
    if ln.sub and t == 1:
        cases += [(f'{st} ?= 6', 'PMR_SB_FUNDING'),
                  (f'{st} ?= 2 var:pmr_sb_ok{ln.sub} ?= 0', f'PMR_SB_POOL_{ln.sub}')]
    if k in GRANTS:
        cases += [(f'{st} ?= 6', 'PMR_RG_FUNDING'), (f'{st} ?= 2 var:pmr_rg_ok ?= 0', 'PMR_RG_POOL')]
    cases.append((f'{st} ?= 2', 'PMR_CC_WHY_POINTS'))
    if ruled(ln):
        cases.append((f'{st} ?= 5', f'PMR_CC_WHY_RULED_{RIVAL[k]}'))
    if na(ln):
        cases.append((f'{st} ?= 7', 'PMR_CC_WHY_NA'))
    if t > 1:
        cases.append((f'{st} ?= 0', f'PMR_CC_WHY_PREV_{k}_{t}'))
    elif not ln.root:
        cases.append((f'{st} ?= 0', f'PMR_CC_WHY_ROOT_{ln.tree}'))
    return cases


def V(name):
    return f"[Character.MakeScope.Var('{name}').GetValue|0]"


def money(name):
    return f"[Character.MakeScope.Var('{name}').GetValue|D]"


def fx_lines(k, t):
    """The bullets a node shows (one per benefit, the value green; one per good, written good, value, then output).
    A branch's first node shows its subsidiary's industries instead (cc_tree.sub_body)."""
    pct = lambda x: f'{round(x * 100):+d}%'.replace('-', '−')   # noqa: E731
    G = lambda label, val: f'• {label} #P {val}#!'               # noqa: E731
    good = f"[Character.GetCustom('pmr_cc_good_eg1')]"
    out = {
        ('xr', 1): [G('Input goods', pct(-ROOT_INPUT))],
        ('er', 1): [G('Throughput', pct(ROOT_THROUGHPUT))],
        ('vx', 2): [G('Input goods', pct(-INPUT_CUT))],
        ('vx', 3): [G('Throughput', pct(THROUGHPUT))],
        ('hx', 2): [G('Economy of scale', f'+{EOS_LEVELS} levels')],
        ('hx', 3): [G('Throughput', pct(THROUGHPUT))],
        ('en', 1): [G('Throughput', pct(THROUGHPUT))],
        ('en', 2): [f'• {good} #P {pct(OUTPUT[0])}#! output', "[Character.GetCustom('pmr_cc_fx_eg2_2')]"],
        ('en', 3): [f'• {good} #P {pct(OUTPUT[1] - OUTPUT[0])}#! output', "[Character.GetCustom('pmr_cc_fx_eg2_3')]",
                    "[Character.GetCustom('pmr_cc_fx_pg')]"],
    }
    return out.get((k, t), [])


def localization(p):
    pct = lambda x: f'{round(x * 100):+d}%'.replace('-', '−')   # noqa: E731
    good2 = "[Character.GetCustom('pmr_cc_good_eg2')]"
    loc = [
        ' PMR_CC_TAB:0 "Company Culture"',
        f' PMR_CC_LEVEL:0 "Culture Level #v {V("pmr_cc_level")}#!"',
        f' PMR_CC_POINTS:0 "#v {V("pmr_cc_pts")}#! points"',
        f' PMR_CC_BAR:0 "#v {V("pmr_cc_funds")}#! / {V("pmr_cc_cost")}"',
        f' PMR_CC_BAR_TT:0 "#header Next point#!\\nProsperity #v {V("pmr_cc_prosp")}#! × size #v ×[Character.MakeScope.Var(\'pmr_cc_size\').GetValue|1]#! = #v +{V("pmr_cc_rate")}#! a month"',
        ' PMR_CC_SHOW:0 "Show Company Culture"',
        ' PMR_CC_OPEN:0 "Open Company Culture"',
        ' PMR_CC_FULL_TITLE:0 "Company Culture: [Company.GetNameNoFormatting]"',
        ' PMR_CC_BOARD:0 "Board"',
        ' PMR_CC_WHY_BUY:0 "#P Ready#!"',
        ' PMR_CC_WHY_DONE:0 "#P Bought#!"',
        ' PMR_CC_WHY_POINTS:0 "#N Not enough points#!"',
        ' PMR_CC_WHY_NA:0 "#N Nothing to found#!"',
        ' PMR_CC_WHY_LOCKED:0 "#N Locked#!"',
        ' PMR_CC_PG_REQ:0 "Hallmark Goods"',
        f" PMR_CC_FX_EG2_2:0 \"• {good2} #P {pct(OUTPUT[0])}#! output\"",
        f" PMR_CC_FX_EG2_3:0 \"• {good2} #P {pct(OUTPUT[1] - OUTPUT[0])}#! output\"",
        ' PMR_CC_FX_PG:0 "• Prestige goods"',
        f' PMR_RG_PAY:0 "@money!{money("pmr_rg_next")} × {GRANT_WEEKS}"',
        f' PMR_RG_POOL:0 "#N Investment pool needs @money!{money("pmr_rg_next")}#!"',
        f' PMR_RG_FUNDING:0 "@money!{money("pmr_rg_pay")}, {V("pmr_rg_w")} / {GRANT_WEEKS}"',
        ' PMR_CC_COST_TT:0 "Culture points"',
        ' PMR_CC_METHODS_HEADER:0 "Methods"',
        f' pmr_cc_test_points_decision:0 "PMR test: {TEST_POINTS} Culture points for each of your companies"',
        f' pmr_cc_test_points_decision_desc:0 "Each of your companies gets {TEST_POINTS} Culture points."',
        ' pmr_rg_test_finish_decision:0 "PMR test: finish your research grants"',
        ' pmr_rg_test_finish_decision_desc:0 "Each running research grant is paid up next week."',
    ]
    sec = f"[Character.GetCustom('pmr_cc_name_{SECTOR_NODE[0]}_{SECTOR_NODE[1]}')]"
    name = lambda k, t: sec if (k, t) == SECTOR_NODE else BY_KEY[k].names[t - 1]   # noqa: E731
    loc += [f' PMR_CC_SEC_{i}:0 "{n}"' for i, (n, _i, _g) in enumerate(SECTORS, 1)]
    for ln in LINES:
        for t in range(1, ln.tiers + 1):
            loc.append(f' PMR_CC_NAME_{ln.key}_{t}:0 "{name(ln.key, t)}"')
            if t > 1:
                loc.append(f' PMR_CC_WHY_PREV_{ln.key}_{t}:0 "#N Needs {name(ln.key, t - 1)}#!"')
            fx = fx_lines(ln.key, t)
            if fx:
                loc.append(f' PMR_CC_FX_{ln.key}_{t}:0 "' + '\\n'.join(fx) + '"')
            loc.append(f" PMR_CC_TT_{ln.key}_{t}:0 \"[Character.GetCustom('pmr_cc_why_{ln.key}_{t}')]\"")
    for k in RIVAL:
        loc.append(f' PMR_CC_WHY_RULED_{k}:0 "#N Ruled out by {BY_KEY[k].names[0]}#!"')
    for tr, k in ROOT_OF.items():
        loc.append(f' PMR_CC_WHY_ROOT_{tr}:0 "#N Needs {BY_KEY[k].names[0]}#!"')
    for (k, t) in TRAITS:
        loc += [f' {trait_key(k, t)}:0 "{BY_KEY[k].names[t - 1]}"', f' {trait_key(k, t)}_desc:0 "Company Culture"']
    for n in SUB_TRAITS:
        loc += [f' {sub_key(n)}:0 "Subsidiary"', f' {sub_key(n)}_desc:0 ""']
    for key, _i, mods, _w in output_traits(p):
        t = int(key.rsplit('_', 1)[1])
        g = mods[0][0][len('goods_output_'):-len('_mult')]
        nm = SECTORS[p.good_sec.get(g, 1) - 1][0] if ('en', t) == SECTOR_NODE else BY_KEY['en'].names[t - 1]
        loc += [f' {key}:0 "{nm}: ${g}$"', f' {key}_desc:0 "Company Culture"']
    return loc


# ---------------------------------------------------------------------------------------------------------------

def write_all(game, write, header_text, report, p, out_dir):
    """Writes every file of the feature (test builds for now) and returns its loc lines."""
    write('common/character_traits/pmr_cc_traits.txt', header_text + traits(p))
    write('common/modifier_type_definitions/pmr_cc_modifier_types.txt', header_text + modifier_types(p, game))
    write('common/scripted_effects/pmr_cc_effects.txt', header_text + effects(p))
    write('common/scripted_triggers/pmr_cc_triggers.txt', header_text + triggers())
    write('common/scripted_guis/pmr_cc_sguis.txt', header_text + sguis())
    write('common/on_actions/pmr_cc_on_actions.txt', header_text + ON_ACTIONS)
    write('events/pmr_cc_events.txt', header_text + EVENTS.replace('?= CAL_VERSION', f'?= {CAL_VERSION}'))
    write('common/script_values/pmr_cc_values.txt', header_text + viewing_value())
    write('common/decisions/pmr_cc_test_decisions.txt', header_text + TEST_DECISION.replace('{LOG}', log_line('CC_TEST'))
          + subsidiaries.TEST_DECISION)
    write('common/customizable_localization/pmr_cc_custom_loc.txt', header_text + custom_loc(p))
    write(CHARTER_FILE, charters(game))
    write('common/defines/zz_pmr_cc.txt', header_text + DEFINE)
    write(PANEL_GUI, cc_tree.patch_panel(company_panel.patch_company_panel(   # without the retool sites
        open(os.path.join(game, PANEL_GUI), encoding='utf-8-sig').read()), TAB), bom=False)
    write(OWN_GUI, cc_tree.tab(p), bom=False)
    # the HUD (cc_tree.patch_hud) is written by generate.py, with the retool site flags
    n_tex = cc_tree.textures(out_dir)
    sb_loc = subsidiaries.write_all(game, write, header_text, p)
    write(bylaws.TRAIT_FILE, header_text + bylaws.traits())
    write(bylaws.STATIC_FILE, header_text + bylaws.static_modifiers())
    n_traits = len(all_traits(p))
    report['company_culture'] = {
        'companies': len(p.comp), 'traits': n_traits, 'textures': n_tex,
        'key_building': {c: v['key'] for c, v in sorted(p.comp.items())},
        'main_goods': {c: v['eg'] for c, v in sorted(p.comp.items())}}
    report['subsidiaries'] = {c: {'vertical': v['sb'][0], 'horizontal': v['sb'][1]} for c, v in sorted(p.comp.items())}
    no_h = sum(1 for v in p.comp.values() if v['key'] and not v['sb'][1])
    no_v = sum(1 for v in p.comp.values() if v['key'] and not v['sb'][0])
    print(f'company culture: {len(p.comp)} companies ({sum(1 for v in p.comp.values() if not v["key"])} without a key '
          f'building), {n_traits} traits, {n_tex} textures; subsidiaries over {len(p.sb_types)} building types, '
          f'{no_v} companies with no vertical and {no_h} with no horizontal one')
    return localization(p) + goods_mult_loc(p, game) + sb_loc + bylaws.localization()


ai_value_tail = bylaws.ai_value_tail   # generate.py: private_investment.AI_TAIL, the Focus bylaw
