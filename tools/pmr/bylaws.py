"""Company bylaws (Pat 2026-10-19 14:43Z, 14:50Z; SPEC.md sections 5 to 7): three groups of laws on how a company
treats and pays its workers and where its investment goes, passed by its board. Test builds, with Company Culture
(company_culture.py), whose window (cc_tree.board) shows the board and the bylaws.

Groups (Pat 14:43Z: "come up with your best guess on 3 law groupings"; 14:50Z: Focus in place of Welfare):
    Pay               Tight Payroll (harsh), Market Wages (default), Living Wage, Profit Sharing
    Hours and Safety  Long Shifts (harsh), Standard Shifts (default), Safety Code
    Focus             Original Company, Balanced (default), Subsidiaries
A Pay or Hours bylaw is a trait on the executive (its executive_modifier applies to the levels the company owns), on
the company's and on each of its subsidiaries' (one policy for the group, as the board votes for the group). Focus
multiplies the AI weight of the company's industries and its subsidiaries' (ai_value_tail).

Passing (Pat 14:43Z: "an law passing system; come up with some generalized mapping of opinions"): the board's seats
back (+1), oppose (-1) or don't care (0) about a change, by their view of the bylaw it brings against the one it
replaces. Seats: the executive (3), each subsidiary's executive (1), the shareholders (by the Industrialists' clout: 1, 2 at
5%, 3 at 15%, 4 at 25%; Pat 18:03Z), and the Workers Council where the Trade Unions have 5% clout or more (2, 3 at 15%, 4
at 25%; Pat 14:43Z). A seat's character adds its popularity (POP: +1 at 25, +2 at 75, as much off below -25 and -75;
Pat 18:03Z), and a seat keeps at least 1 vote. Pat 16:53Z: the shareholders' seat is the
country's Industrialists' leader, and a character's view is its ideology's (IDEOLOGY_VIEWS; an ideology not listed
falls back to its interest group's, VIEWS, as does a country without an Industrialists' leader). Pat 17:44Z: the
council's seat is the Trade Unions' leader, by its ideology, else the Trade Unions' view. Support = the sum of weight x view; a change at BLOCK or below can't start;
otherwise its bar gains 20 + 2 x support a month (Pat 16:39Z: shareholders' 2 votes against give +16; 5 to 50) and it
passes at 100. One change at a time; it can be
cancelled. An AI company proposes, once a year, the Pay or Hours bylaw its board backs most (support 2 or more).

Trade Unions (Pat 14:43Z: "If a company is powerful in a nation and it has harsh worker laws that should add minus
interest group approval to trade unions and increase their support"): each month, every company of the country
employing TU_LEVELS levels or more counts its harsh bylaws; the country's total (at most TU_CAP) is the multiplier of
a country modifier: Trade Unions approval -1 and political strength +5% for each.

Company variables: pmr_bl_<g> the group's bylaw (1-based), pmr_bl_pg / pmr_bl_pv the change under way (group, bylaw;
0 none), pmr_bl_pp its bar, pmr_bl_sup its support, pmr_bl_rt its monthly gain, pmr_bl_s_<code> each bylaw's support,
pmr_bl_v_ex / _sh / _wc the executive's, shareholders' and council's vote on the change (a subsidiary's own vote is
its pmr_bl_v, its weight pmr_bl_w, its popularity's votes pmr_bl_pa), pmr_bl_w_x / _h / _w the executive's,
shareholders' and council's weights (pmr_bl_pa_x / _h / _w their popularity's votes, pmr_bl_wb_h the shareholders' by
clout), pmr_bl_wc the council's weight by clout (0: no council), pmr_bl_shl the Industrialists' leader (pmr_bl_shx 1 while there is
one), pmr_bl_wcl the Trade Unions' leader (pmr_bl_wcx), pmr_bl_<seat>_<code> each seat's weighted vote on each bylaw
(SEATS), pmr_bl_ns the subsidiaries' seats, pmr_bl_harsh, pmr_bl_ai (Focus's AI factor). Mirrored onto the executive for the window with company_culture's
numbers.
"""

THR, WAGE, ATTR = 'building_throughput_add', 'building_minimum_wage_mult', 'building_job_attractiveness_mult'
DIV, COND = 'building_company_worker_dividends_add', 'building_working_conditions_mult'
LAW_ICON = 'gfx/interface/icons/law_icons/{}.dds'
IG_ICON = 'gfx/interface/icons/ig_icons/{}.dds'

GROUPS = [
    (1, 'Pay', ('Tight Payroll', 'Market Wages', 'Living Wage', 'Profit Sharing')),
    (2, 'Hours and Safety', ('Long Shifts', 'Standard Shifts', 'Safety Code')),
    (3, 'Focus', ('Original Company', 'Balanced', 'Subsidiaries')),
]
DEFAULT = 2                          # each group's middle bylaw
FOCUS = 3


def code(g, i):
    return 10 * g + i


OPTIONS = [(g, i, name) for g, _n, names in GROUPS for i, name in enumerate(names, 1)]
CODES = [code(g, i) for g, i, _n in OPTIONS]
NAME = {code(g, i): name for g, i, name in OPTIONS}
HARSH = (11, 21)
# Effects (SPEC.md section 5; Pat hasn't confirmed the numbers): code -> executive modifiers.
TRAITS = {
    11: [(WAGE, -0.15)],
    13: [(WAGE, 0.15), (ATTR, 0.20)],
    14: [(WAGE, 0.10), (DIV, 0.15)],
    21: [(THR, 0.05), (COND, 0.30)],
    23: [(COND, -0.30), (THR, -0.02)],
}
ICON = {11: 'laissez_faire', 12: 'free_trade', 13: 'wage_controls', 14: 'cooperative_ownership',
        21: 'no_workers_rights', 22: 'regulatory_bodies', 23: 'worker_protections',
        31: 'protectionism', 32: 'mercantilism', 33: 'corporate_state'}
FOCUS_AI = {1: (1.5, 0.75), 3: (0.75, 1.5)}   # Focus bylaw -> (the company's factor, its subsidiaries')

# Views by interest group (SPEC.md section 6): code -> +1 backs, -1 opposes.
VIEWS = {
    'ig_industrialists': {11: 1, 13: -1, 14: -1, 21: 1, 23: -1},
    'ig_landowners': {11: 1, 13: -1, 14: -1, 21: 1},
    'ig_petty_bourgeoisie': {14: -1},
    'ig_trade_unions': {11: -1, 13: 1, 14: 1, 21: -1, 23: 1},
    'ig_intelligentsia': {13: 1, 21: -1, 23: 1},
    'ig_devout': {13: 1, 21: -1, 23: 1},
    'ig_rural_folk': {13: 1},
    'ig_armed_forces': {},
}
# Views by character ideology (Pat 2026-10-19 16:53Z: "all characters should have their primary ideologies displayed and
# those ideologies should have an opinion on the company bylaws"): code -> -2..2, and a seat votes the sign of its view
# of the new bylaw less its view of the current one. Where vanilla's ideology (1.14.5 common/ideologies) has a view on
# the law a bylaw stands for, the row follows it: Hours and Safety = labour rights (no workers' rights, regulatory
# bodies, worker protections); Pay = welfare (no social security, poor laws, wage subsidies) and economic system
# (laissez-faire for Tight Payroll and Market Wages, cooperative ownership for Profit Sharing). The other rows are
# guesses from the ideology's leaning; moderates back the defaults. Pat hasn't confirmed them.
IDEOLOGY_ROWS = {
    'defaults': {12: 1, 22: 1},
    'tradition': {12: 1, 14: -1, 22: 1},
    'market': {11: 1, 12: 1, 13: -1, 14: -2, 21: 0, 22: -1, 23: -2},     # market liberal (vanilla)
    'national': {11: -1, 12: 1, 14: -2, 22: 1},                           # protectionist, modernizer, Mitogaku, Bonapartist
    'corporate': {11: -1, 12: 0, 13: 1, 14: -1, 22: 1},                   # corporatist (vanilla), fascist, integralist
    'reform': {11: -1, 13: 1, 21: -1, 23: 1},
    'labour': {11: -2, 12: -1, 13: 1, 14: 2, 21: -1, 22: 1, 23: 2},       # social democrat (vanilla)
    'left': {11: -2, 12: -1, 13: 1, 14: 2, 21: -2, 22: 0, 23: 2},         # communist, utopian (vanilla), anarchist
    'luddite': {11: -2, 12: -1, 13: 1, 21: -1, 23: 1},
    'slaver': {11: 2, 13: -2, 14: -2, 21: 2, 23: -2},
}
IDEOLOGIES = {
    'defaults': ['moderate', 'pacifist', 'ethno_nationalist', 'nihilist', 'shojoi', 'sovereignist_leader',
                 'jingoist_leader', 'jacksonian_democrat'],
    'tradition': ['traditionalist', 'traditionalist_minoritarian', 'royalist', 'legitimist', 'carlist', 'carlist_2',
                  'miguelist', 'miguelist_2', 'authoritarian'],
    'market': ['market_liberal', 'orleanist', 'liberal_leader'],
    'national': ['protectionist', 'modernizer_leader', 'mitogaku', 'bonapartist'],
    'corporate': ['corporatist_leader', 'fascist', 'integralist', 'despotic_utopian'],
    'reform': ['reformer', 'radical', 'republican_leader', 'humanitarian', 'humanitarian_royalist', 'positivist',
               'utilitarian_leader', 'feminist', 'abolitionist', 'ilustrado_leader', 'land_reformer', 'theocrat'],
    'labour': ['social_democrat'],
    'left': ['communist', 'vanguardist', 'anarchist', 'utopian'],
    'luddite': ['luddite'],
    'slaver': ['slaver'],
}
IG_TEX = {'ig_industrialists': 'industrialists', 'ig_landowners': 'landowners',
          'ig_petty_bourgeoisie': 'petty_bourgeoisie', 'ig_trade_unions': 'trade_unions',
          'ig_intelligentsia': 'intelligensia', 'ig_devout': 'devout', 'ig_rural_folk': 'rural_folk',
          'ig_armed_forces': 'armed_forces'}
EXEC_W, SUB_W = 3, 1
COUNCIL = [(0.25, 4), (0.15, 3), (0.05, 2)]   # Trade Unions clout -> the council's weight
# Pat 18:03Z ("clout of the share holders, board member extc influenced by their popularity and relative power"): the
# shareholders weigh by the Industrialists' clout as the council by the Trade Unions' (1 below 5%), and a seat's
# character adds its popularity's step (vanilla's 25 and 75 marks); a seat keeps at least 1 vote
SHARE = [(0.25, 4), (0.15, 3), (0.05, 2)]
SHARE_LOW = 1
POP = [(75, 2), (25, 1), (-75, -2), (-25, -1)]   # popularity at least (or, negative, at most) -> votes
BLOCK = -6
VOTED = [c for c in CODES if c // 10 != FOCUS]   # the bylaws interest groups have views on
RATE = (20, 2, 5, 50)                # base, per net vote of support, least, most (Pat 16:39-16:40Z)
AI_MIN = 2
TU_LEVELS = 20
TU_CAP = 5
TU_MODIFIER = 'pmr_bl_harsh_companies'
STATIC_FILE = 'common/static_modifiers/pmr_bl_static_modifiers.txt'
TRAIT_FILE = 'common/character_traits/pmr_bl_traits.txt'
# Pat 17:43Z ("i need to be able to see who supports and opposes a change"): each seat's weighted vote on each bylaw,
# pmr_bl_<seat>_<code>: x the executive, b the subsidiaries' executives together, h the shareholders, w the council
SEATS = ('x', 'b', 'h', 'w')
VARS = ([f'pmr_bl_{g}' for g, _n, _o in GROUPS] + ['pmr_bl_pg', 'pmr_bl_pv', 'pmr_bl_pp', 'pmr_bl_sup', 'pmr_bl_rt',
        'pmr_bl_v_ex', 'pmr_bl_v_sh', 'pmr_bl_v_wc', 'pmr_bl_wc', 'pmr_bl_ai', 'pmr_bl_shx', 'pmr_bl_wcx', 'pmr_bl_ns',
        'pmr_bl_pa', 'pmr_bl_w_b', 'pmr_bl_wb_h'] + [f'pmr_bl_{x}_{k}' for x in ('w', 'pa') for k in ('x', 'h', 'w')]
        + [f'pmr_bl_s_{c}' for c in CODES] + [f'pmr_bl_{k}_{c}' for k in SEATS for c in VOTED])
MIRRORED = VARS + ['pmr_bl_shl', 'pmr_bl_wcl']


def trait_key(c):
    return f'pmr_bl_{c}'


def trait_keys():
    return [trait_key(c) for c in TRAITS]


def view(ig, c):
    return VIEWS[ig].get(c, 0)


def sign(x):
    return (x > 0) - (x < 0)


def fmt(x):
    s = f'{x:.4f}'.rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'


def short(ig):
    return ig[len('ig_'):]


# ---------------------------------------------------------------------------------------------------------------
# Script

def traits():
    out = ['# PMR company bylaws (bylaws.py): a Pay or Hours bylaw on the executive of the company and of each of its\n'
           '# subsidiaries; its executive_modifier applies to the levels that company owns. Never random.\n\n']
    for c, mods in TRAITS.items():
        body = ''.join(f'\t\t{k} = {fmt(v)}\n' for k, v in mods)
        out.append(f'{trait_key(c)} = {{\n\ttype = condition\n\ttexture = "{LAW_ICON.format(ICON[c])}"\n\n'
                   f'\texecutive_modifier = {{\n{body}\t}}\n\n'
                   '\tpossible = { always = no }\n\tweight = { value = 0 }\n\tvalue = 0\n}\n')
    return '\n'.join(out)


def apply_traits(ind):
    """Character scope (an executive), scope:pmr_bl_src = the company whose bylaws it carries: its bylaw traits."""
    out = f'{ind}# bylaws (bylaws.py): the company\'s, or a subsidiary\'s parent\'s\n'
    for c in TRAITS:
        g, i, t = c // 10, c % 10, trait_key(c)
        on = f'scope:pmr_bl_src = {{ var:pmr_bl_{g} ?= {i} }}'
        out += (f'{ind}if = {{ limit = {{ has_trait = {t} NOT = {{ {on} }} }} remove_trait = {t} }}\n'
                f'{ind}if = {{ limit = {{ NOT = {{ has_trait = {t} }} {on} }} add_trait = {t} }}\n')
    return out


def src_scope(ind):
    """Company scope: scope:pmr_bl_src = this company, or a subsidiary's parent."""
    return (f'{ind}save_scope_as = pmr_bl_src\n'
            f'{ind}if = {{ limit = {{ has_variable = pmr_sub }} var:pmr_parent ?= {{ save_scope_as = pmr_bl_src }} }}\n')


def _row(views):
    """pmr_bl_d_<code>: the seat's vote on each bylaw against the group's current one, by views (code -> view)."""
    out = ''
    for g, _n, names in GROUPS:
        if g == FOCUS:
            continue
        n = len(names)
        for cur in range(1, n + 1):
            sets = ' '.join(f'set_variable = {{ name = pmr_bl_d_{code(g, i)} value = '
                            f'{sign(views.get(code(g, i), 0) - views.get(code(g, cur), 0))} }}'
                            for i in range(1, n + 1))
            out += f'\t{"if" if cur == 1 else "else_if"} = {{ limit = {{ var:pmr_bl_{g} = {cur} }} {sets} }}\n'
    return out


def effects(log_line):
    """log_line(rec, extra) -> the debug_log effect (company_culture.player_log)."""
    o = ['# PMR company bylaws (bylaws.py). Company scope (the parent company) unless said otherwise.\n\n']
    o.append('# Each group on its default where unset; no change under way.\n'
             'pmr_bl_init = {\n'
             + ''.join(f'\tif = {{ limit = {{ NOT = {{ has_variable = pmr_bl_{g} }} }} set_variable = {{ name = pmr_bl_{g} value = {DEFAULT} }} }}\n'
                       for g, _n, _o in GROUPS)
             + ''.join(f'\tif = {{ limit = {{ NOT = {{ has_variable = {x} }} }} set_variable = {{ name = {x} value = 0 }} }}\n'
                       for x in VARS if x not in [f'pmr_bl_{g}' for g, _n, _o in GROUPS])
             + '}\n\n')
    for ig in VIEWS:
        o.append(f'# A seat of {ig}: its vote on each bylaw.\npmr_bl_row_{short(ig)} = {{\n{_row(VIEWS[ig])}}}\n\n')
    for row, views in IDEOLOGY_ROWS.items():
        o.append(f'# A seat whose character is of an ideology in IDEOLOGIES[{row!r}].\npmr_bl_row_i_{row} = {{\n{_row(views)}}}\n\n')
    o.append(f'# A seat with no view: no votes.\npmr_bl_row_none = {{\n{_row({})}}}\n\n')
    disp = ''.join(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ scope:pmr_bl_ch = {{ OR = {{ '
                   + ' '.join(f'has_ideology = ideology:ideology_{x}' for x in IDEOLOGIES[row])
                   + f' }} }} }} pmr_bl_row_i_{row} = yes }}\n' for j, row in enumerate(IDEOLOGY_ROWS))
    disp += ''.join(f'\telse_if = {{ limit = {{ scope:pmr_bl_ch = {{ is_interest_group_type = {ig} }} }} '
                    f'pmr_bl_row_{short(ig)} = yes }}\n' for ig in VIEWS)
    pop = ''.join(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ scope:pmr_bl_ch = {{ popularity {">=" if p > 0 else "<="} {p} }} }} '
                  f'set_variable = {{ name = pmr_bl_pa value = {v} }} }}\n' for j, (p, v) in enumerate(POP))
    o.append('# The votes of character scope:pmr_bl_ch: its ideology\'s, else its interest group\'s; its popularity\'s votes\n'
             '# (pmr_bl_pa, POP).\n'
             'pmr_bl_row_ch = {\n' + disp + '\telse = { pmr_bl_row_none = yes }\n'
             '\tset_variable = { name = pmr_bl_pa value = 0 }\n' + pop + '}\n\n')
    o.append('# A seat\'s weight pmr_bl_$V$: $B$ and its character\'s popularity (pmr_bl_pa, 0 for a seat with none), at least 1.\n'
             'pmr_bl_weigh = {\n\tset_variable = { name = pmr_bl_$V$ value = $B$ }\n'
             '\tchange_variable = { name = pmr_bl_$V$ add = var:pmr_bl_pa }\n'
             '\tif = { limit = { var:pmr_bl_$V$ < 1 } set_variable = { name = pmr_bl_$V$ value = 1 } }\n}\n\n')
    o.append('# The votes of company $WHO$\'s executive.\npmr_bl_row_of = {\n'
             '\tif = {\n\t\tlimit = { $WHO$ = { exists = executive } }\n'
             '\t\t$WHO$ = { executive = { save_scope_as = pmr_bl_ch } }\n\t\tpmr_bl_row_ch = yes\n\t}\n'
             '\telse = { pmr_bl_row_none = yes }\n}\n\n')
    acc = ''.join(f'\tset_variable = {{ name = pmr_bl_t value = var:pmr_bl_d_{c} }}\n'
                  '\tchange_variable = { name = pmr_bl_t multiply = $W$ }\n'
                  f'\tchange_variable = {{ name = pmr_bl_s_{c} add = var:pmr_bl_t }}\n'
                  f'\tchange_variable = {{ name = pmr_bl_$K$_{c} add = var:pmr_bl_t }}\n' for c in VOTED)
    vote = ''.join(f'\tif = {{ limit = {{ var:pmr_bl_pg = {c // 10} var:pmr_bl_pv = {c % 10} }} '
                   f'set_variable = {{ name = pmr_bl_vt value = var:pmr_bl_d_{c} }} }}\n' for c in VOTED)
    o.append('# A seat of weight $W$ (its votes in pmr_bl_d_*): its weight on each bylaw\'s support and on its own line $K$\n'
             '# (SEATS), and its vote on the change under way (pmr_bl_vt).\npmr_bl_seat = {\n' + acc
             + '\tset_variable = { name = pmr_bl_vt value = 0 }\n' + vote + '}\n\n')
    council = ''.join(f'\t\t\t{"if" if j == 0 else "else_if"} = {{ limit = {{ ig_clout >= {fmt(cl)} }} '
                      f'scope:pmr_bl_co = {{ set_variable = {{ name = pmr_bl_wc value = {w} }} }} }}\n'
                      for j, (cl, w) in enumerate(COUNCIL))
    share = ''.join(f'\t\t\t{"if" if j == 0 else "else_if"} = {{ limit = {{ ig_clout >= {fmt(cl)} }} '
                    f'scope:pmr_bl_co = {{ set_variable = {{ name = pmr_bl_wb_h value = {w} }} }} }}\n'
                    for j, (cl, w) in enumerate(SHARE))
    pend = ''.join(f'\tif = {{ limit = {{ var:pmr_bl_pg = {c // 10} var:pmr_bl_pv = {c % 10} }} '
                   f'set_variable = {{ name = pmr_bl_sup value = var:pmr_bl_s_{c} }} }}\n' for c in VOTED)
    o.append('# The board counts: each bylaw\'s support (pmr_bl_s_*), each seat\'s vote on the change under way, its support.\n'
             'pmr_bl_count = {\n\tsave_scope_as = pmr_bl_co\n'
             + ''.join(f'\tset_variable = {{ name = pmr_bl_s_{c} value = 0 }}\n' for c in CODES)
             + ''.join(f'\tset_variable = {{ name = pmr_bl_{k}_{c} value = 0 }}\n' for k in SEATS for c in VOTED)
             + '\tset_variable = { name = pmr_bl_ns value = 0 }\n'
             '\tset_variable = { name = pmr_bl_wc value = 0 }\n'
             '\towner ?= {\n\t\tig:ig_trade_unions ?= {\n' + council + '\t\t}\n\t}\n'
             f'\tset_variable = {{ name = pmr_bl_wb_h value = {SHARE_LOW} }}\n'
             '\towner ?= {\n\t\tig:ig_industrialists ?= {\n' + share + '\t\t}\n\t}\n'
             f'\t# the executive ({EXEC_W} and its popularity)\n'
             '\tset_variable = { name = pmr_bl_pa value = 0 }\n'
             '\tpmr_bl_row_of = { WHO = scope:pmr_bl_co }\n'
             f'\tpmr_bl_weigh = {{ V = w_x B = {EXEC_W} }}\n'
             '\tset_variable = { name = pmr_bl_pa_x value = var:pmr_bl_pa }\n'
             '\tpmr_bl_seat = { W = var:pmr_bl_w_x K = x }\n'
             '\tset_variable = { name = pmr_bl_v_ex value = var:pmr_bl_vt }\n'
             f'\t# each subsidiary\'s executive ({SUB_W} and its popularity), its vote and weight on the subsidiary\n'
             '\tevery_in_list = {\n\t\tvariable = pmr_subs\n\t\tsave_scope_as = pmr_bl_sub\n'
             '\t\tscope:pmr_bl_co = {\n\t\t\tset_variable = { name = pmr_bl_pa value = 0 }\n'
             '\t\t\tpmr_bl_row_of = { WHO = scope:pmr_bl_sub }\n'
             f'\t\t\tpmr_bl_weigh = {{ V = w_b B = {SUB_W} }}\n'
             '\t\t\tpmr_bl_seat = { W = var:pmr_bl_w_b K = b }\n\t\t\tchange_variable = { name = pmr_bl_ns add = 1 }\n\t\t}\n'
             '\t\tset_variable = { name = pmr_bl_v value = scope:pmr_bl_co.var:pmr_bl_vt }\n'
             '\t\tset_variable = { name = pmr_bl_w value = scope:pmr_bl_co.var:pmr_bl_w_b }\n'
             '\t\tset_variable = { name = pmr_bl_pa value = scope:pmr_bl_co.var:pmr_bl_pa }\n\t}\n'
             '\t# the shareholders (the Industrialists\' clout, SHARE): the Industrialists\' leader, else their view\n'
             '\tset_variable = { name = pmr_bl_pa value = 0 }\n'
             '\tif = {\n\t\tlimit = { owner ?= { ig:ig_industrialists ?= { exists = leader } } }\n'
             '\t\towner = { ig:ig_industrialists = { leader = { save_scope_as = pmr_bl_ch } } }\n'
             '\t\tset_variable = { name = pmr_bl_shl value = scope:pmr_bl_ch }\n'
             '\t\tset_variable = { name = pmr_bl_shx value = 1 }\n\t\tpmr_bl_row_ch = yes\n\t}\n'
             '\telse = {\n\t\tif = { limit = { has_variable = pmr_bl_shl } remove_variable = pmr_bl_shl }\n'
             '\t\tset_variable = { name = pmr_bl_shx value = 0 }\n\t\tpmr_bl_row_industrialists = yes\n\t}\n'
             '\tpmr_bl_weigh = { V = w_h B = var:pmr_bl_wb_h }\n'
             '\tset_variable = { name = pmr_bl_pa_h value = var:pmr_bl_pa }\n'
             '\tpmr_bl_seat = { W = var:pmr_bl_w_h K = h }\n'
             '\tset_variable = { name = pmr_bl_v_sh value = var:pmr_bl_vt }\n'
             '\t# the Workers Council: the Trade Unions\' leader (Pat 17:44Z), else the Trade Unions\' view\n'
             '\tset_variable = { name = pmr_bl_v_wc value = 0 }\n'
             '\tset_variable = { name = pmr_bl_wcx value = 0 }\n'
             '\tset_variable = { name = pmr_bl_pa value = 0 }\n'
             '\tset_variable = { name = pmr_bl_w_w value = 0 }\n'
             '\tif = {\n\t\tlimit = { var:pmr_bl_wc > 0 owner ?= { ig:ig_trade_unions ?= { exists = leader } } }\n'
             '\t\towner = { ig:ig_trade_unions = { leader = { save_scope_as = pmr_bl_ch } } }\n'
             '\t\tset_variable = { name = pmr_bl_wcl value = scope:pmr_bl_ch }\n'
             '\t\tset_variable = { name = pmr_bl_wcx value = 1 }\n\t\tpmr_bl_row_ch = yes\n\t}\n'
             '\telse_if = {\n\t\tlimit = { var:pmr_bl_wc > 0 }\n\t\tpmr_bl_row_trade_unions = yes\n\t}\n'
             '\tif = { limit = { var:pmr_bl_wcx = 0 has_variable = pmr_bl_wcl } remove_variable = pmr_bl_wcl }\n'
             '\tif = {\n\t\tlimit = { var:pmr_bl_wc > 0 }\n'
             '\t\tpmr_bl_weigh = { V = w_w B = var:pmr_bl_wc }\n'
             '\t\tpmr_bl_seat = { W = var:pmr_bl_w_w K = w }\n'
             '\t\tset_variable = { name = pmr_bl_v_wc value = var:pmr_bl_vt }\n\t}\n'
             '\tset_variable = { name = pmr_bl_pa_w value = var:pmr_bl_pa }\n'
             '\tset_variable = { name = pmr_bl_sup value = 0 }\n' + pend
             + '\tset_variable = { name = pmr_bl_rt value = var:pmr_bl_sup }\n'
             f'\tchange_variable = {{ name = pmr_bl_rt multiply = {RATE[1]} }}\n'
             f'\tchange_variable = {{ name = pmr_bl_rt add = {RATE[0]} }}\n'
             f'\tclamp_variable = {{ name = pmr_bl_rt min = {RATE[2]} max = {RATE[3]} }}\n'
             '\tif = { limit = { var:pmr_bl_pg = 0 } set_variable = { name = pmr_bl_rt value = 0 } }\n}\n\n')
    # Focus factor.
    focus = ''.join(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ var:pmr_bl_{FOCUS} = {i} }} '
                    f'set_variable = {{ name = pmr_bl_ai value = {fmt(f[0])} }} }}\n' for j, (i, f) in enumerate(FOCUS_AI.items()))
    sub_focus = ''.join(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ scope:pmr_cc_par ?= {{ var:pmr_bl_{FOCUS} ?= {i} }} }} '
                        f'set_variable = {{ name = pmr_bl_ai value = {fmt(f[1])} }} }}\n' for j, (i, f) in enumerate(FOCUS_AI.items()))
    o.append('# Focus: the AI weight factor of the company\'s industries (ai_value_tail).\n'
             'pmr_bl_focus = {\n' + focus + '\telse = { set_variable = { name = pmr_bl_ai value = 1 } }\n}\n\n'
             '# A subsidiary (scope:pmr_cc_par its parent, pmr_cc_sub_sync): its factor under its parent\'s Focus.\n'
             'pmr_bl_sub_focus = {\n' + sub_focus + '\telse = { set_variable = { name = pmr_bl_ai value = 1 } }\n}\n\n')
    # Start, cancel, pass.
    start = ''.join(f'\t\t{"if" if j == 0 else "else_if"} = {{ limit = {{ var:pmr_bl_new = {c} }} '
                    f'set_variable = {{ name = pmr_bl_pg value = {c // 10} }} set_variable = {{ name = pmr_bl_pv value = {c % 10} }} }}\n'
                    for j, c in enumerate(CODES))
    blog = ("group=[THIS.Var('pmr_bl_pg').GetValue|0];bylaw=[THIS.Var('pmr_bl_pv').GetValue|0];"
            "bar=[THIS.Var('pmr_bl_pp').GetValue|0];support=[THIS.Var('pmr_bl_sup').GetValue|0];"
            "rate=[THIS.Var('pmr_bl_rt').GetValue|0];ex=[THIS.Var('pmr_bl_v_ex').GetValue|0];"
            "sh=[THIS.Var('pmr_bl_v_sh').GetValue|0];wc=[THIS.Var('pmr_bl_wc').GetValue|0]x[THIS.Var('pmr_bl_v_wc').GetValue|0];"
            + ''.join(f"g{g}=[THIS.Var('pmr_bl_{g}').GetValue|0];" for g, _n, _o in GROUPS))
    o.append('# A change to bylaw pmr_bl_new (its code, 10 x group + bylaw) starts, unless one is under way.\n'
             'pmr_bl_start = {\n\tif = {\n\t\tlimit = { var:pmr_bl_pg = 0 }\n'
             + start
             + '\t\tset_variable = { name = pmr_bl_pp value = 0 }\n\t\tpmr_bl_count = yes\n'
             f'\t\t{log_line("BL_START", blog)}\n\t}}\n}}\n\n'
             '# The change under way is dropped.\n'
             'pmr_bl_cancel = {\n'
             f'\t{log_line("BL_CANCEL", blog)}\n'
             '\tset_variable = { name = pmr_bl_pg value = 0 }\n\tset_variable = { name = pmr_bl_pv value = 0 }\n'
             '\tset_variable = { name = pmr_bl_pp value = 0 }\n\tpmr_bl_count = yes\n}\n\n')
    passing = ''.join(f'\tif = {{ limit = {{ var:pmr_bl_pg = {g} }} set_variable = {{ name = pmr_bl_{g} value = var:pmr_bl_pv }} }}\n'
                      for g, _n, _o in GROUPS)
    o.append('# The change passes: the group\'s new bylaw, its traits on the executives (pmr_cc_after_buy).\n'
             'pmr_bl_pass = {\n' + passing
             + f'\t{log_line("BL_PASS", blog)}\n'
             '\tset_variable = { name = pmr_bl_pg value = 0 }\n\tset_variable = { name = pmr_bl_pv value = 0 }\n'
             '\tset_variable = { name = pmr_bl_pp value = 0 }\n'
             '\tpmr_bl_focus = yes\n\tpmr_bl_count = yes\n\tpmr_cc_after_buy = yes\n}\n\n')
    # AI pick.
    best = ''.join(f'\tif = {{ limit = {{ var:pmr_bl_s_{c} > var:pmr_bl_bs }} '
                   f'set_variable = {{ name = pmr_bl_bs value = var:pmr_bl_s_{c} }} set_variable = {{ name = pmr_bl_new value = {c} }} }}\n'
                   for c in VOTED)
    o.append(f'# An AI company, once a year: the Pay or Hours bylaw its board backs most, at support {AI_MIN} or more.\n'
             'pmr_bl_ai_pick = {\n'
             f'\tset_variable = {{ name = pmr_bl_bs value = {AI_MIN - 1} }}\n\tset_variable = {{ name = pmr_bl_new value = 0 }}\n'
             + best + '\tif = { limit = { var:pmr_bl_new > 0 } pmr_bl_start = yes }\n}\n\n')
    harsh = ''.join(f'\tif = {{ limit = {{ var:pmr_bl_{c // 10} = {c % 10} }} change_variable = {{ name = pmr_bl_harsh add = 1 }} }}\n'
                    for c in HARSH)
    o.append('# Monthly, a parent company (company_culture.pmr_cc_tick): the board counts (a player\'s company, or one with a\n'
             '# change under way), the change gains, an AI company proposes one once a year, the harsh bylaws are counted.\n'
             'pmr_bl_month = {\n\tpmr_bl_init = yes\n\tpmr_bl_focus = yes\n'
             '\tif = {\n\t\tlimit = { var:pmr_bl_pg > 0 }\n\t\tpmr_bl_count = yes\n'
             '\t\tchange_variable = { name = pmr_bl_pp add = var:pmr_bl_rt }\n'
             '\t\tif = { limit = { var:pmr_bl_pp >= 100 } pmr_bl_pass = yes }\n\t}\n'
             '\telse_if = {\n\t\tlimit = { owner ?= { is_player = yes } }\n\t\tpmr_bl_count = yes\n\t}\n'
             '\telse_if = {\n\t\tlimit = { NOT = { has_variable = pmr_bl_ai_t } }\n'
             '\t\tset_variable = { name = pmr_bl_ai_t days = 365 }\n\t\tpmr_bl_count = yes\n\t\tpmr_bl_ai_pick = yes\n\t}\n'
             '\tset_variable = { name = pmr_bl_harsh value = 0 }\n' + harsh + '}\n\n')
    o.append(f'# Country scope, monthly: the harsh bylaws of its companies employing {TU_LEVELS} levels or more, at most {TU_CAP},\n'
             f'# as the multiplier of {TU_MODIFIER} (Trade Unions approval and political strength); pmr_bl_focused while\n'
             '# one of its companies has a Focus other than Balanced (ai_value_tail reads its companies only then).\n'
             'pmr_bl_country = {\n'
             '\tif = {\n\t\tlimit = { any_company = { has_variable = pmr_bl_ai NOT = { var:pmr_bl_ai = 1 } } }\n'
             '\t\tset_variable = pmr_bl_focused\n\t}\n'
             '\telse_if = {\n\t\tlimit = { has_variable = pmr_bl_focused }\n\t\tremove_variable = pmr_bl_focused\n\t}\n'
             '\tset_variable = { name = pmr_bl_tu value = 0 }\n'
             '\tsave_scope_as = pmr_bl_country\n'
             '\tevery_company = {\n'
             f'\t\tlimit = {{\n\t\t\tNOT = {{ has_variable = pmr_sub }}\n\t\t\tcompany_employed_levels >= {TU_LEVELS}\n'
             '\t\t\thas_variable = pmr_bl_harsh\n\t\t\tvar:pmr_bl_harsh > 0\n\t\t}\n'
             '\t\tsave_scope_as = pmr_bl_c\n'
             '\t\tscope:pmr_bl_country = { change_variable = { name = pmr_bl_tu add = scope:pmr_bl_c.var:pmr_bl_harsh } }\n\t}\n'
             + f'\tclamp_variable = {{ name = pmr_bl_tu min = 0 max = {TU_CAP} }}\n'
             # touched only when the count differs from the one it carries (pmr_bl_tu_on; perf review 5, S-8)
             '\tif = {\n\t\tlimit = {\n\t\t\tOR = {\n'
             '\t\t\t\tNOT = { has_variable = pmr_bl_tu_on }\n\t\t\t\tNOT = { var:pmr_bl_tu_on = var:pmr_bl_tu }\n'
             f'\t\t\t\tAND = {{ var:pmr_bl_tu > 0 NOT = {{ has_modifier = {TU_MODIFIER} }} }}\n'
             '\t\t\t}\n\t\t}\n'
             f'\t\tif = {{ limit = {{ has_modifier = {TU_MODIFIER} }} remove_modifier = {TU_MODIFIER} }}\n'
             f'\t\tif = {{ limit = {{ var:pmr_bl_tu > 0 }} add_modifier = {{ name = {TU_MODIFIER} multiplier = var:pmr_bl_tu }} }}\n'
             '\t\tset_variable = { name = pmr_bl_tu_on value = var:pmr_bl_tu }\n\t}\n}\n\n')
    o.append('# The player clicked bylaw scope:opt (pmr_bl_pick_sgui), or the change\'s cancel (pmr_bl_cancel_sgui).\n'
             'pmr_bl_pick = {\n\tset_variable = { name = pmr_bl_new value = scope:opt }\n\tpmr_bl_start = yes\n\tpmr_cc_mirror = yes\n}\n\n'
             'pmr_bl_cancel_click = {\n\tpmr_bl_cancel = yes\n\tpmr_cc_mirror = yes\n}\n\n')
    return ''.join(o)


def ai_value_tail(types):
    """The end of pmr_ai_value_<b> (private_investment.AI_TAIL; state scope) for a building type that company types
    `types` list: the Focus bylaw of a company listing it (Pat 14:50Z), x1.5 where one favours it, else x0.75 where one
    turns away from it."""
    if not types:
        return ''
    of = ' '.join(f'is_company_type = company_type:{t}' for t in sorted(set(types)))
    lists = f'OR = {{ {of} }}' if len(set(types)) > 1 else of
    hi, lo = max(f for pair in FOCUS_AI.values() for f in pair), min(f for pair in FOCUS_AI.values() for f in pair)
    return ('\t# PMR: the Focus bylaw of a company listing this industry (bylaws.py)\n'
            f'\tif = {{\n\t\tlimit = {{ owner ?= {{ has_variable = pmr_bl_focused any_company = {{ {lists} var:pmr_bl_ai ?= {fmt(hi)} }} }} }}\n'
            f'\t\tmultiply = {fmt(hi)}\n\t}}\n'
            f'\telse_if = {{\n\t\tlimit = {{ owner ?= {{ has_variable = pmr_bl_focused any_company = {{ {lists} var:pmr_bl_ai ?= {fmt(lo)} }} }} }}\n'
            f'\t\tmultiply = {fmt(lo)}\n\t}}\n')


def static_modifiers():
    return ('# PMR company bylaws (bylaws.py): Trade Unions\' answer to harsh companies, added to a country with its\n'
            '# companies\' harsh bylaws as the multiplier (pmr_bl_country).\n'
            f'{TU_MODIFIER} = {{\n\ticon = gfx/interface/icons/timed_modifier_icons/modifier_fist_negative.dds\n'
            '\tinterest_group_ig_trade_unions_approval_add = -1\n'
            '\tinterest_group_ig_trade_unions_pol_str_mult = 0.05\n}\n')


LABEL = {WAGE: 'Wage target', ATTR: 'Job attractiveness', DIV: 'Workforce dividends', THR: 'Throughput',
         COND: 'Dangerous conditions'}
# Pat 17:24Z ("bonuses to these laws should either format green or red"): +1 where a rise is good for the company,
# -1 where it is bad (vanilla's colour where it has one: throughput and job attractiveness good, dangerous conditions
# bad; wages and workforce dividends, neutral in vanilla, cost the company).
GOOD = {THR: 1, ATTR: 1, COND: -1, WAGE: -1, DIV: -1}


def fx(c):
    """A bylaw's effect bullets, values only."""
    pct = lambda x: f'{round(x * 100):+d}%'.replace('-', '−')   # noqa: E731
    col = lambda good: 'P' if good else 'N'   # noqa: E731
    if c in TRAITS:
        return [f'• {LABEL[m]} #{col(v * GOOD[m] > 0)} {pct(v)}#!' for m, v in TRAITS[c]]
    i = c % 10
    if c // 10 == FOCUS and i in FOCUS_AI:
        own, sub = FOCUS_AI[i]
        return [f'• Own industries #{col(own > 1)} ×{fmt(own)}#!', f'• Subsidiary industries #{col(sub > 1)} ×{fmt(sub)}#!']
    return []


# The characters on the board, as the window reaches them (cc_tree.seats): the seat key -> the character
WHO = {'EX': 'Company.GetExecutive', 'SH': "Character.MakeScope.Var('pmr_bl_shl').GetCharacter",
       'WC': "Character.MakeScope.Var('pmr_bl_wcl').GetCharacter"}


def _gv(n):
    return f"Character.MakeScope.Var('{n}').GetValue"


def _views(views):
    """A view row's bullets (Pat 17:44Z: "i need to see the opinions ... on the company bylaws"), values only."""
    return '\\n'.join(f'• {NAME[c]} #{"P" if views[c] > 0 else "N"} {views[c]:+d}#!'.replace('-', '−')
                       for c in VOTED if views.get(c))


def custom_loc():
    """Character scope, a board seat's character: its views of the bylaws, by the row its votes come from
    (pmr_bl_row_ch's order)."""
    cases = [(f'OR = {{ ' + ' '.join(f'has_ideology = ideology:ideology_{x}' for x in IDEOLOGIES[row]) + ' }',
              f'PMR_BL_VIEWS_I_{row}' if _views(IDEOLOGY_ROWS[row]) else 'PMR_EMPTY') for row in IDEOLOGY_ROWS]
    cases += [(f'is_interest_group_type = {ig}', f'PMR_BL_VIEWS_G_{short(ig)}' if _views(VIEWS[ig]) else 'PMR_EMPTY')
              for ig in VIEWS]
    body = ''.join(f'\ttext = {{\n\t\ttrigger = {{ {t} }}\n\t\tlocalization_key = {k}\n\t}}\n' for t, k in cases)
    return ('# Company bylaws (bylaws.py). Character scope: a board seat\'s views of the bylaws.\n'
            'pmr_bl_views = {\n\ttype = character\n\trandom_valid = no\n' + body
            + '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n')


def localization():
    loc = [' PMR_BL_HEADER:0 "Bylaws"', ' PMR_BL_SHAREHOLDERS:0 "Shareholders"', ' PMR_BL_COUNCIL:0 "Workers Council"',
           f' {TU_MODIFIER}:0 "Harsh Company Bylaws"', f' {TU_MODIFIER}_desc:0 ""', 
           ' PMR_BL_BAR_TT:0 "#v [Character.MakeScope.Var(\'pmr_bl_pp\').GetValue|0]#! / 100\\n'
           'Support [Character.MakeScope.Var(\'pmr_bl_sup\').GetValue|+=0]\\n'
           '[Character.MakeScope.Var(\'pmr_bl_rt\').GetValue|+=0] a month"']
    for g, name, _o in GROUPS:
        loc.append(f' PMR_BL_GROUP_{g}:0 "{name}"')
    # a seat's votes, what they come from (Pat 18:03Z)
    pa = lambda v: f"\\nPopularity [{v}.GetValue|+=0]"   # noqa: E731
    cv = lambda n: f"Character.MakeScope.Var('{n}')"   # noqa: E731
    sub_pa = "Company.MakeScope.Var('pmr_bl_pa')"
    loc += [f' PMR_BL_VOTES_X:0 "Executive {EXEC_W}{pa(cv("pmr_bl_pa_x"))}"',
            f' PMR_BL_VOTES_B:0 "Subsidiary {SUB_W}{pa(sub_pa)}"',
            f' PMR_BL_VOTES_H:0 "Industrialists\' clout [{_gv("pmr_bl_wb_h")}|0]{pa(cv("pmr_bl_pa_h"))}"',
            f' PMR_BL_VOTES_W:0 "Trade Unions\' clout [{_gv("pmr_bl_wc")}|0]{pa(cv("pmr_bl_pa_w"))}"']
    # a seat's ideology: its name and its views (custom_loc)
    for k, who in WHO.items():
        loc.append(f' PMR_BL_IDEO_{k}:0 "[Ideology.GetName]\\n[{who}.GetCustom(\'pmr_bl_views\')]"')
    for row, views in IDEOLOGY_ROWS.items():
        if _views(views):
            loc.append(f' PMR_BL_VIEWS_I_{row}:0 "{_views(views)}"')
    for ig, views in VIEWS.items():
        if _views(views):
            loc.append(f' PMR_BL_VIEWS_G_{short(ig)}:0 "{_views(views)}"')
    gt = lambda n: f"GreaterThan_CFixedPoint({_gv(n)}, '(CFixedPoint)0')"   # noqa: E731
    eq1 = lambda n: f"EqualTo_CFixedPoint({_gv(n)}, '(CFixedPoint)1')"   # noqa: E731
    for c in CODES:
        sup = f"Support [Character.MakeScope.Var('pmr_bl_s_{c}').GetValue|+=0]"
        if c in VOTED:
            # Pat 17:43Z: who supports and opposes it, seat by seat
            vote = lambda k: f'[{_gv(f"pmr_bl_{k}_{c}")}|+=0]'   # noqa: E731
            sup += (f'\\n[{WHO["EX"]}.GetFullNameNoFormatting] {vote("x")}'
                    f"[SelectLocalization({gt('pmr_bl_ns')}, 'PMR_BL_TT_B_{c}', 'PMR_EMPTY')]"
                    f"[SelectLocalization({eq1('pmr_bl_shx')}, 'PMR_BL_TT_HL_{c}', 'PMR_BL_TT_H_{c}')]"
                    f"[SelectLocalization(And({gt('pmr_bl_wc')}, {eq1('pmr_bl_wcx')}), 'PMR_BL_TT_WL_{c}', 'PMR_EMPTY')]"
                    f"[SelectLocalization(And({gt('pmr_bl_wc')}, Not({eq1('pmr_bl_wcx')})), 'PMR_BL_TT_W_{c}', 'PMR_EMPTY')]")
            loc += [f' PMR_BL_TT_B_{c}:0 "\\nSubsidiaries {vote("b")}"',
                    f' PMR_BL_TT_HL_{c}:0 "\\n[{WHO["SH"]}.GetFullNameNoFormatting] {vote("h")}"',
                    f' PMR_BL_TT_H_{c}:0 "\\nShareholders {vote("h")}"',
                    f' PMR_BL_TT_WL_{c}:0 "\\n[{WHO["WC"]}.GetFullNameNoFormatting] {vote("w")}"',
                    f' PMR_BL_TT_W_{c}:0 "\\nWorkers Council {vote("w")}"']
        loc += [f' PMR_BL_NAME_{c}:0 "{NAME[c]}"', f' PMR_BL_TT_{c}:0 "{sup}"',
                f' PMR_BL_SUP_{c}:0 "[Character.MakeScope.Var(\'pmr_bl_s_{c}\').GetValue|+=0]"']
        if fx(c):
            loc.append(f' PMR_BL_FX_{c}:0 "' + '\\n'.join(fx(c)) + '"')
    for c in TRAITS:
        loc += [f' {trait_key(c)}:0 "{NAME[c]}"', f' {trait_key(c)}_desc:0 ""']
    return loc


def sguis():
    picks = ''.join(f'\t\t\tAND = {{ scope:opt = {c} NOT = {{ var:pmr_bl_{c // 10} ?= {c % 10} }} '
                    f'has_variable = pmr_bl_s_{c} var:pmr_bl_s_{c} > {BLOCK} }}\n' for c in CODES)
    return ('# Company bylaws (bylaws.py). Character scope: the company\'s executive, as the window reads it. scope:opt is the\n'
            '# bylaw clicked (10 x group + bylaw).\n\n'
            'pmr_bl_pick_sgui = {\n\tscope = character\n\tsaved_scopes = { opt }\n'
            '\tis_valid = {\n\t\towner ?= { is_player = yes }\n\t\tvar:pmr_bl_pg ?= 0\n\t\tOR = {\n' + picks + '\t\t}\n\t}\n'
            '\teffect = {\n\t\tpmr_cc_with_company = { EFFECT = pmr_bl_pick }\n\t}\n}\n\n'
            'pmr_bl_cancel_sgui = {\n\tscope = character\n'
            '\tis_valid = {\n\t\towner ?= { is_player = yes }\n\t\tNOT = { var:pmr_bl_pg ?= 0 }\n\t}\n'
            '\teffect = {\n\t\tpmr_cc_with_company = { EFFECT = pmr_bl_cancel_click }\n\t}\n}\n')
