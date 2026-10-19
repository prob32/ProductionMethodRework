"""Subsidiaries (Pat 2026-10-19 14:43Z): Vertical Integration founds the company's supply subsidiary, Diversification
its sister subsidiary. Test builds, with Company Culture (company_culture.py), whose trees hold both nodes.

Each company type has up to two subsidiary types, n = 1 vertical and n = 2 horizontal (company_culture.plan, 'sb'):
the building types making an input of the company's key building, and the other building types of the key building's
class, up to SB_SIZE each, the company's own aside. Buying the node charges SB_LEVELS levels' construction cost of
the list's first industry to the owner's investment pool, a part every week for SB_WEEKS paid weeks (q43's payment,
Pat 14:18Z "Paid from pool"); then the subsidiary is founded: a company type of its own (company_pmr_sb_<parent>_<n>)
founded by add_company with SB_LEVELS levels (COMPANY_MINIMUM_LEVELS_PER_HQ: a company with fewer is dissolved within
a day, q37) of the first of its industries a state can take. It is listed under the parent's Regional HQs and Assets
tab and left off the Companies panel (company_panel.py, SUB_LINKS: the parent's variable list pmr_subs, the
subsidiary's pmr_sub), buys levels like any company (q41), and has no Company Culture tab and no charters. Each one
adds a company slot to its country (Pat 14:44Z: SLOT_MODIFIER, recounted by pmr_sb_slots), so it never takes one of
the player's. Its profit is its own: no 1.14.5 effect moves money between companies (Pat asked 14:56Z).

Company variables (company_culture mirrors them onto the executive): pmr_sb_pick the subsidiary being paid for (0
none), pmr_sb_w its paid weeks, pmr_sb_pay its weekly cost, pmr_sb_pay<n> subsidiary n's weekly cost now, pmr_sb_ok<n>
1 when its payment can start (a list, none of it founded or paid for, a week in the pool), pmr_sb_d<n> 1 while it
exists. On the subsidiary: pmr_sub, pmr_parent, pmr_sb_n.
"""
import glob
import os
import re

import pdx

SB_SIZE = 8             # industries a subsidiary lists, at most
SB_LEVELS = 5           # COMPANY_MINIMUM_LEVELS_PER_HQ (00_defines.txt)
SB_WEEKS = 52           # paid weeks
TEST_POOL = 1000000     # pmr_sb_test_pool_decision
CONSTRUCTION_PMS = 'common/production_methods/13_construction.txt'
TYPES_FILE = 'common/company_types/pmr_subsidiaries.txt'
STATIC_FILE = 'common/static_modifiers/pmr_sb_static_modifiers.txt'
SLOT_MODIFIER = 'pmr_sb_company_slots'
NUMS = (1, 2)           # 1 the supply subsidiary (Vertical Integration), 2 the sister subsidiary (Diversification)
SLOTS = range(1, SB_SIZE + 1)
NAME = {1: 'Supply', 2: 'Industries'}


def short(c):
    return c[len('company_'):] if c.startswith('company_') else c


def type_key(c, n):
    return f'company_pmr_sb_{short(c)}_{n}'


# ---------------------------------------------------------------------------------------------------------------
# Reading the game

def point_prices(game):
    """[(technologies, £ per construction point at base prices)], cheapest first, the default method's last (no
    technologies): each construction method's inputs over its points (13_construction.txt; wooden 1,000)."""
    cost = {}
    for path in glob.glob(os.path.join(game, 'common', 'goods', '*.txt')):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            c = pdx.get(n.value, 'cost') if n.is_block else None
            if c:
                cost[n.key] = float(c.value)
    text = open(os.path.join(game, CONSTRUCTION_PMS), encoding='utf-8-sig').read()
    out = []
    for n in pdx.parse(text):
        if not n.is_block:
            continue
        body = text[n.start:n.end]
        pts = re.search(r'country_construction_add\s*=\s*([\d.]+)', body)
        if not pts:
            continue
        price = sum(cost[g] * float(q) for g, q in re.findall(r'goods_input_(\w+)_add\s*=\s*([\d.]+)', body))
        techs = pdx.get(n.value, 'unlocking_technologies')
        out.append((pdx.items(techs) if techs else [], round(price / float(pts.group(1)))))
    if not out or out[-1][0] and not any(not t for t, _p in out):
        raise SystemExit(f'subsidiaries: {CONSTRUCTION_PMS} has no default construction method')
    return sorted(out, key=lambda tp: tp[1])


def buildings(game):
    """building key -> (icon, construction points)."""
    values = {}
    for path in glob.glob(os.path.join(game, 'common', 'script_values', '*.txt')):
        for k, v in re.findall(r'^\s*(construction_cost_\w+)\s*=\s*(\d+)', open(path, encoding='utf-8-sig').read(), re.M):
            values[k] = int(v)
    out = {}
    for path in glob.glob(os.path.join(game, 'common', 'buildings', '*.txt')):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if not (n.is_block and n.key):
                continue
            icon, rc = pdx.get(n.value, 'icon'), pdx.get(n.value, 'required_construction')
            pts = rc.value if rc else '0'
            out[n.key] = (icon.value.strip('"') if icon else '', values.get(pts, int(pts) if pts.isdigit() else 0))
    return out


def company_art(game):
    """company key -> (icon, background) of its type."""
    out = {}
    for path in sorted(glob.glob(os.path.join(game, 'common', 'company_types', '*.txt'))):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and n.key and n.key.startswith('company_'):
                i, b = pdx.get(n.value, 'icon'), pdx.get(n.value, 'background')
                out[n.key] = (i.value.strip('"') if i else '', b.value.strip('"') if b else '')
    return out


# ---------------------------------------------------------------------------------------------------------------
# The plan

def plan_types(p, game):
    """Every building type a subsidiary lists (p.sb_types, 1-based in the variables), their icons and points; the
    lists themselves are company_culture.plan's (p.comp[c]['sb'])."""
    info = buildings(game)
    p.sb_prices = point_prices(game)
    p.sb_types = sorted({b for v in p.comp.values() for s in v['sb'] for b in s})
    p.sb_icon = {b: info[b][0] for b in p.sb_types}
    p.sb_points = {b: info[b][1] for b in p.sb_types}
    for b in p.sb_types:
        if not p.sb_icon[b] or not p.sb_points[b]:
            raise SystemExit(f'subsidiaries: {b} has no icon or construction cost')


def owners(p):
    """building type -> the subsidiary types listing it (private_investment.company_owners' shape)."""
    out = {}
    for c, v in sorted(p.comp.items()):
        for n, s in zip(NUMS, v['sb']):
            for b in s:
                out.setdefault(b, []).append(type_key(c, n))
    return out


KVARS = [f'pmr_cc_k_sb{n}_{j}' for n in NUMS for j in SLOTS] + [f'pmr_cc_k_sbp{n}' for n in NUMS]
ZERO = ['pmr_sb_pick', 'pmr_sb_w', 'pmr_sb_pay'] + [f'pmr_sb_d{n}' for n in NUMS]
MIRRORED = ZERO + ['pmr_sb_paid'] + [f'pmr_sb_{x}{n}' for x in ('pay', 'ok') for n in NUMS]


def kvals(p, v):
    """company_culture's init chain: the company type's subsidiaries."""
    out = {k: 0 for k in KVARS}
    for n, s in zip(NUMS, v['sb']):
        for j, b in enumerate(s, 1):
            out[f'pmr_cc_k_sb{n}_{j}'] = p.sb_types.index(b) + 1
        if s:
            out[f'pmr_cc_k_sbp{n}'] = SB_LEVELS * p.sb_points[s[0]]
    return out


# ---------------------------------------------------------------------------------------------------------------
# Script

def company_types(p, game):
    art = company_art(game)
    out = ['# PMR subsidiaries (subsidiaries.py), test builds. Founded only by their parent\'s Vertical Integration or\n'
           '# Diversification node (pmr_sb_found): potential needs the country variable the founding sets, and possible is\n'
           '# never met, so neither the Companies panel nor the AI founds one.\n\n']
    for c, v in sorted(p.comp.items()):
        icon, bg = art.get(c, ('', ''))
        for n, s in zip(NUMS, v['sb']):
            if not s:
                continue
            t = type_key(c, n)
            out.append(f'{t} = {{\n'
                       + (f'\ticon = "{icon}"\n' if icon else '')
                       + (f'\tbackground = "{bg}"\n' if bg else '')
                       + '\n\tflavored_company = yes\n\n\tbuilding_types = {\n'
                       + ''.join(f'\t\t{b}\n' for b in s)
                       + f'\t}}\n\n\tpotential = {{\n\t\thas_variable = pmr_sb_ok_{t}\n\t}}\n\n'
                       '\tpossible = {\n\t\talways = no\n\t}\n\n\tai_will_do = {\n\t\talways = no\n\t}\n}\n\n')
    return ''.join(out)


def static_modifiers():
    return ('# PMR subsidiaries (subsidiaries.py): one company slot per subsidiary the country has (Pat 2026-10-19 14:44Z),\n'
            '# added with that count as its multiplier (pmr_sb_slots).\n'
            f'{SLOT_MODIFIER} = {{\n\ticon = gfx/interface/icons/timed_modifier_icons/modifier_statue_positive.dds\n'
            '\tcountry_max_companies_add = 1\n}\n')


def derive(prices):
    """Appended to company_culture's pmr_cc_derive (company scope, scope:pmr_cc_gco = the company): each subsidiary's
    weekly cost by the owner's construction technology, and whether its payment can start."""
    d = ('\t# subsidiaries (subsidiaries.py): each one\'s weekly cost, its founding levels\' construction points x the\n'
         '\t# owner\'s price per point / weeks, and whether its payment can start (a list, nothing founded or paid for, a\n'
         '\t# week in the pool)\n'
         f'\tset_local_variable = {{ name = pmr_sb_ppt value = {prices[-1][1]} }}\n')
    first = True
    for techs, price in prices:
        if not techs:
            break
        lim = ' '.join(f'has_technology_researched = {t}' for t in techs)
        d += (f'\t{"if" if first else "else_if"} = {{ limit = {{ owner ?= {{ {lim} }} }} '
              f'set_local_variable = {{ name = pmr_sb_ppt value = {price} }} }}\n')
        first = False
    for n in NUMS:
        d += (f'\tset_variable = {{ name = pmr_sb_pay{n} value = var:pmr_cc_k_sbp{n} }}\n'
              f'\tchange_variable = {{ name = pmr_sb_pay{n} multiply = local_var:pmr_sb_ppt }}\n'
              f'\tchange_variable = {{ name = pmr_sb_pay{n} divide = {SB_WEEKS} }}\n'
              f'\tround_variable = {{ name = pmr_sb_pay{n} nearest = 1 }}\n'
              f'\tset_variable = {{ name = pmr_sb_ok{n} value = 0 }}\n'
              f'\tif = {{ limit = {{ var:pmr_cc_k_sbp{n} > 0 var:pmr_sb_d{n} = 0 var:pmr_sb_pick = 0 '
              f'owner ?= {{ investment_pool >= scope:pmr_cc_gco.var:pmr_sb_pay{n} }} }} '
              f'set_variable = {{ name = pmr_sb_ok{n} value = 1 }} }}\n')
    return d


def log(rec, extra=''):
    return ('debug_log = "PMR;rec=' + rec + ';date=[TimeKeeper.GetCurrentDate.GetString];'
            'company=[THIS.GetCompany.GetNameNoFormatting];' + extra +
            "pick=[THIS.Var('pmr_sb_pick').GetValue|0];w=[THIS.Var('pmr_sb_w').GetValue|0];"
            "pay=[THIS.Var('pmr_sb_pay').GetValue|0];"
            + ';'.join(f"s{n}=[THIS.Var('pmr_cc_k_sb{n}_1').GetValue|0]/[THIS.Var('pmr_sb_pay{n}').GetValue|0]/"
                       f"[THIS.Var('pmr_sb_ok{n}').GetValue|0]/[THIS.Var('pmr_sb_d{n}').GetValue|0]" for n in NUMS) + '"')


def player_log(rec, extra=''):
    return f'if = {{ limit = {{ owner ?= {{ is_player = yes }} }} {log(rec, extra)} }}'


def effects(p):
    o = ['# PMR subsidiaries (subsidiaries.py), test builds. Company scope unless said otherwise.\n\n']
    o.append('# Subsidiary $N$\'s weekly payments start (its node bought, or bought again after the subsidiary went).\n'
             'pmr_sb_start = {\n\tset_variable = { name = pmr_sb_pick value = $N$ }\n'
             '\tset_variable = { name = pmr_sb_w value = 0 }\n'
             '\tset_variable = { name = pmr_sb_pay value = var:pmr_sb_pay$N$ }\n'
             '\towner ?= { pmr_cc_gclock = yes }\n'
             f'\t{player_log("SB_PICK")}\n}}\n\n')
    # The weekly payment.
    wlog = ("paid=[THIS.Var('pmr_sb_paid').GetValue|0];pool_before=[THIS.Var('pmr_cc_pool0').GetValue|0];"
            "pool_after=[THIS.Var('pmr_cc_pool1').GetValue|0];")
    o.append(f'# Weekly (pmr_cc.1) while a subsidiary is paid for: the owner\'s investment pool pays pmr_sb_pay, or the week\n'
             f'# waits; after {SB_WEEKS} paid weeks the subsidiary is founded (pmr_sb_found), or, with no state for its levels,\n'
             '# tried again each week without paying.\n'
             'pmr_sb_week = {\n\tsave_scope_as = pmr_cc_gco\n'
             f'\tif = {{\n\t\tlimit = {{ var:pmr_sb_w < {SB_WEEKS} }}\n'
             '\t\tif = { limit = { owner ?= { is_player = yes } } pmr_cc_pool_read = { V = pmr_cc_pool0 } }\n'
             '\t\tif = {\n\t\t\tlimit = { owner ?= { investment_pool >= scope:pmr_cc_gco.var:pmr_sb_pay } }\n'
             '\t\t\tchange_variable = { name = pmr_sb_pay multiply = -1 }\n'
             '\t\t\towner = { add_investment_pool = scope:pmr_cc_gco.var:pmr_sb_pay }\n'
             '\t\t\tchange_variable = { name = pmr_sb_pay multiply = -1 }\n'
             '\t\t\tchange_variable = { name = pmr_sb_w add = 1 }\n'
             '\t\t\towner = { change_variable = { name = pmr_cc_gweek add = scope:pmr_cc_gco.var:pmr_sb_pay } }\n'
             '\t\t\tset_variable = { name = pmr_sb_paid value = 1 }\n\t\t}\n'
             '\t\telse = { set_variable = { name = pmr_sb_paid value = 0 } }\n'
             '\t\tif = { limit = { owner ?= { is_player = yes } } pmr_cc_pool_read = { V = pmr_cc_pool1 } }\n'
             f'\t\t{player_log("SB_WEEK", wlog)}\n\t}}\n'
             f'\tif = {{\n\t\tlimit = {{ var:pmr_sb_w >= {SB_WEEKS} }}\n\t\tpmr_sb_found = yes\n\t}}\n'
             '\tif = { limit = { owner ?= { is_player = yes } } pmr_cc_mirror = yes }\n}\n\n')
    # Founding.
    chain = ''
    i = 0
    for c, v in sorted(p.comp.items()):
        if not any(v['sb']):
            continue
        inner = ''
        for n, s in zip(NUMS, v['sb']):
            if not s:
                continue
            bs = (s + [s[0]] * SB_SIZE)[:SB_SIZE]
            args = ' '.join(f'B{j} = {b}' for j, b in enumerate(bs, 1))
            inner += (f'\t\t{"if" if not inner else "else_if"} = {{ limit = {{ var:pmr_sb_pick = {n} }} '
                      f'owner = {{ pmr_sb_found_one = {{ T = {type_key(c, n)} N = {n} {args} }} }} }}\n')
        chain += (f'\t{"if" if i == 0 else "else_if"} = {{\n\t\tlimit = {{ is_company_type = company_type:{c} }}\n'
                  f'{inner}\t}}\n')
        i += 1
    found_log = ("sub=[THIS.Var('pmr_sb_last').GetCompany.GetNameNoFormatting];"
                 "levels=[THIS.Var('pmr_sb_lastlv').GetValue|0];")
    o.append('# The subsidiary being paid for is paid: it is founded (pmr_sb_found_one), listed under this company (pmr_subs,\n'
             '# company_panel.SUB_LINKS), and its country gets its company slot. The saved scopes are cleared first: one weekly\n'
             '# event can found several.\n'
             'pmr_sb_found = {\n\tsave_scope_as = pmr_sb_par\n'
             + ''.join(f'\tclear_saved_scope = {x}\n' for x in ['pmr_sb_new'] + [f'pmr_sb_st{j}' for j in SLOTS])
             + chain
             + '\tif = {\n\t\tlimit = { exists = scope:pmr_sb_new }\n'
             + ''.join(f'\t\tif = {{ limit = {{ var:pmr_sb_pick = {n} }} set_variable = {{ name = pmr_sb_d{n} value = 1 }} }}\n'
                       for n in NUMS)
             + '\t\tadd_to_variable_list = { name = pmr_subs target = scope:pmr_sb_new }\n'
             '\t\tset_variable = { name = pmr_sb_last value = scope:pmr_sb_new }\n'
             '\t\tset_variable = { name = pmr_sb_lastlv value = scope:pmr_sb_new.var:pmr_sb_lv }\n'
             f'\t\t{player_log("SB_FOUND", found_log)}\n'
             '\t\tset_variable = { name = pmr_sb_pick value = 0 }\n'
             '\t\tset_variable = { name = pmr_sb_w value = 0 }\n'
             '\t\tset_variable = { name = pmr_sb_pay value = 0 }\n'
             '\t\towner ?= { pmr_sb_slots = yes }\n'
             '\t\tpmr_cc_derive = yes\n\t}\n'
             f'\telse = {{\n\t\t{player_log("SB_NO_STATE")}\n\t}}\n}}\n\n')
    lv = ''.join(f'\t\t\t{"if" if m == 3 * SB_LEVELS else "else_if"} = {{ limit = {{ company_owned_levels >= {m} }} '
                 f'set_variable = {{ name = pmr_sb_lv value = {m} }} }}\n' for m in range(3 * SB_LEVELS, 0, -1))
    bs = ' '.join(f'$B{j}$' for j in SLOTS)
    o.append('# Country scope (the owner, ROOT), scope:pmr_sb_par the parent: founds subsidiary type $T$ (the parent\'s\n'
             f'# subsidiary $N$) with {SB_LEVELS} levels of the first of {bs} a state can take (pmr_sb_seed); the next one\n'
             f'# too if the company still owns fewer than {SB_LEVELS} (a mine past its resources). scope:pmr_sb_new: the company.\n'
             'pmr_sb_found_one = {\n'
             + ''.join(f'\tpmr_sb_seed = {{ B = $B{j}$ I = {j} }}\n' for j in SLOTS)
             + '\tif = {\n\t\tlimit = { OR = { ' + ' '.join(f'exists = scope:pmr_sb_st{j}' for j in SLOTS) + ' } }\n'
             '\t\tset_variable = pmr_sb_ok_$T$\n'
             '\t\tif = { limit = { NOT = { has_company = company_type:$T$ } } add_company = company_type:$T$ }\n'
             '\t\tcompany:$T$ ?= {\n\t\t\tsave_scope_as = pmr_sb_new\n'
             '\t\t\tset_variable = { name = pmr_sub value = 1 }\n'
             '\t\t\tset_variable = { name = pmr_parent value = scope:pmr_sb_par }\n'
             '\t\t\tset_variable = { name = pmr_sb_n value = $N$ }\n\t\t}\n'
             + ''.join(f'\t\tpmr_sb_levels = {{ T = $T$ B = $B{j}$ I = {j} }}\n' for j in SLOTS)
             + '\t\tscope:pmr_sb_new ?= {\n\t\t\tset_variable = { name = pmr_sb_lv value = 0 }\n' + lv
             + '\t\t}\n\t}\n}\n\n')
    o.append('# Country scope: scope:pmr_sb_st$I$, an incorporated state that can take a level of $B$ (can_construct_building:\n'
             '# technology, resources), one without the building first.\n'
             'pmr_sb_seed = {\n'
             '\trandom_scope_state = {\n'
             '\t\tlimit = { is_incorporated = yes can_construct_building = $B$ NOT = { any_scope_building = { is_building_type = $B$ } } }\n'
             '\t\tsave_scope_as = pmr_sb_st$I$\n\t}\n'
             '\tif = {\n\t\tlimit = { NOT = { exists = scope:pmr_sb_st$I$ } }\n'
             '\t\trandom_scope_state = {\n\t\t\tlimit = { is_incorporated = yes can_construct_building = $B$ }\n'
             '\t\t\tsave_scope_as = pmr_sb_st$I$\n\t\t}\n\t}\n}\n\n')
    o.append(f'# Country scope: {SB_LEVELS} levels of $B$ owned by the new company in scope:pmr_sb_st$I$, while it owns fewer;\n'
             '# its headquarters there, at the first.\n'
             'pmr_sb_levels = {\n\tif = {\n'
             f'\t\tlimit = {{ exists = scope:pmr_sb_st$I$ scope:pmr_sb_new ?= {{ company_owned_levels < {SB_LEVELS} }} }}\n'
             '\t\tscope:pmr_sb_new = {\n\t\t\tif = {\n\t\t\t\tlimit = { NOT = { has_variable = pmr_sb_hq } }\n'
             '\t\t\t\tset_company_state_region = scope:pmr_sb_st$I$.state_region\n'
             '\t\t\t\tset_variable = pmr_sb_hq\n\t\t\t}\n\t\t}\n'
             '\t\tscope:pmr_sb_st$I$ = {\n\t\t\tcreate_building = {\n\t\t\t\tbuilding = $B$\n'
             '\t\t\t\tadd_ownership = {\n\t\t\t\t\tcompany = {\n\t\t\t\t\t\ttype = $T$\n\t\t\t\t\t\tcountry = ROOT\n'
             f'\t\t\t\t\t\tlevels = {SB_LEVELS}\n\t\t\t\t\t}}\n\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n\t}}\n}}\n\n')
    o.append('# Country scope: one company slot per subsidiary the country has (Pat 2026-10-19 14:44Z), the static modifier\n'
             f'# {SLOT_MODIFIER} with the count as its multiplier. On a founding, a disbanding (the company going has lost\n'
             '# pmr_sub by then) and monthly.\n'
             'pmr_sb_slots = {\n\tsave_scope_as = pmr_sb_cty\n\tset_variable = { name = pmr_sb_cnt value = 0 }\n'
             '\tevery_company = {\n\t\tlimit = { has_variable = pmr_sub }\n'
             '\t\tscope:pmr_sb_cty = { change_variable = { name = pmr_sb_cnt add = 1 } }\n\t}\n'
             f'\tif = {{ limit = {{ has_modifier = {SLOT_MODIFIER} }} remove_modifier = {SLOT_MODIFIER} }}\n'
             f'\tif = {{ limit = {{ var:pmr_sb_cnt > 0 }} add_modifier = {{ name = {SLOT_MODIFIER} multiplier = var:pmr_sb_cnt }} }}\n'
             '}\n\n')
    # Disbanding.
    clear = ''.join(f'\t\t\t\tif = {{ limit = {{ scope:pmr_sb_gone.var:pmr_sb_n ?= {n} }} set_variable = {{ name = pmr_sb_d{n} value = 0 }} }}\n'
                    for n in NUMS)
    o.append('# Root = country, scope:company disbanded (company_culture\'s pmr_cc_on_company_disbanded). A subsidiary leaves its\n'
             '# parent\'s list, and the parent can pay for it again; a parent\'s subsidiaries become companies of their own.\n'
             'pmr_sb_disbanded = {\n\tscope:company ?= {\n\t\tsave_scope_as = pmr_sb_gone\n'
             '\t\tif = {\n\t\t\tlimit = { has_variable = pmr_parent }\n'
             '\t\t\tvar:pmr_parent ?= {\n\t\t\t\tremove_list_variable = { name = pmr_subs target = scope:pmr_sb_gone }\n'
             + clear + '\t\t\t\tpmr_cc_derive = yes\n'
             f'\t\t\t\t{player_log("SB_GONE")}\n\t\t\t}}\n\t\t}}\n\t}}\n'
             '\tevery_company = {\n\t\tlimit = { var:pmr_parent ?= scope:pmr_sb_gone }\n'
             '\t\tremove_variable = pmr_sub\n\t\tremove_variable = pmr_parent\n\t}\n'
             '\tscope:company ?= {\n\t\tif = { limit = { has_variable = pmr_sub } remove_variable = pmr_sub }\n\t}\n'
             '\tpmr_sb_slots = yes\n}\n\n')
    return ''.join(o)


def triggers():
    return ('# PMR subsidiaries (subsidiaries.py). Company scope: a subsidiary is being paid for (the weekly clock pmr_cc.1).\n'
            'pmr_sb_paying = {\n\thas_variable = pmr_sb_pick\n\tvar:pmr_sb_pick > 0\n}\n\n')


TEST_DECISION = f'''
# Test builds only: every subsidiary the player's companies pay for is paid up, so it is founded at the next weekly
# tick without waiting {SB_WEEKS} weeks. Writes PMR;rec=SB_TEST lines.
pmr_sb_test_finish_decision = {{
	is_shown = {{ always = yes }}
	possible = {{ always = yes }}
	when_taken = {{
		every_company = {{
			limit = {{ pmr_sb_paying = yes }}
			set_variable = {{ name = pmr_sb_w value = {SB_WEEKS} }}
			{log('SB_TEST')}
		}}
	}}
	ai_chance = {{ value = 0 }}
}}

# Test builds only: £{TEST_POOL:,} to the player's investment pool, so a subsidiary can be bought and paid for at once.
pmr_sb_test_pool_decision = {{
	is_shown = {{ always = yes }}
	possible = {{ always = yes }}
	when_taken = {{
		add_investment_pool = {TEST_POOL}
	}}
	ai_chance = {{ value = 0 }}
}}
'''


def localization(p):
    import company_culture as cc   # noqa: PLC0415 (circular: company_culture imports this module)
    money = cc.money
    loc = []
    for c, v in sorted(p.comp.items()):
        for n, s in zip(NUMS, v['sb']):
            if s:
                loc.append(f' {type_key(c, n)}:0 "${c}$ {NAME[n]}"')
    for n in NUMS:
        loc += [f' PMR_SB_PAY_{n}:0 "@money!{money(f"pmr_sb_pay{n}")} × {SB_WEEKS}"',
                f' PMR_SB_POOL_{n}:0 "#N Investment pool needs @money!{money(f"pmr_sb_pay{n}")}#!"']
    loc += [f' PMR_SB_FUNDING:0 "@money!{money("pmr_sb_pay")}, {cc.V("pmr_sb_w")} / {SB_WEEKS}"',
            f' {SLOT_MODIFIER}:0 "Subsidiaries"',
            f' {SLOT_MODIFIER}_desc:0 ""',
            ' pmr_sb_test_finish_decision:0 "PMR test: finish your subsidiary payments"',
            ' pmr_sb_test_finish_decision_desc:0 "Subsidiaries being paid for are founded next week."',
            f' pmr_sb_test_pool_decision:0 "PMR test: £{TEST_POOL:,} to your investment pool"',
            f' pmr_sb_test_pool_decision_desc:0 "Adds £{TEST_POOL:,} to your investment pool."']
    return loc


def write_all(game, write, header_text, p):
    write(TYPES_FILE, header_text + company_types(p, game))
    write(STATIC_FILE, header_text + static_modifiers())
    return localization(p)
