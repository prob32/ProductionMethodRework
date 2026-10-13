"""The construction panel's Private tab: investment pool, economic policy and investment priorities.

Pat, 2026-10-13 03:52Z and 04:03Z, revised 04:50Z, 13:05Z and 14:28Z. The construction panel gets a Private tab beside the
government one, and the funding-type filter goes. The Government tab keeps the construction sector and the government
queue and loses the investment pool. The Private tab, top to bottom:
  1. the budget panel's Investment Pool line (Pat 13:05Z), and the next private construction
  2. the weekly re-investment as a trend line in vanilla's graph frame (Pat 04:13Z: the weekly inflow, not the pool
     amount; the game keeps no history of it, so PMR samples investment_pool_income weekly into country variables),
     with a column under the line split by the tree chart's shares; beside it the budget's own pool graph (14:28Z)
  3. what feeds the pool, as a tree chart by priority group (Pat 13:05Z). The game gives its per-building amounts
     only as text (1.14.5 exe: no datamodel, no script value), so the chart shows the privately owned building levels
     of each group, and the game's own list in money is its tooltip
  4. the economic system law as a card, and to its right a policy card, chosen under Interventionism only
  5. investment priorities, one row per priority group (Pat 13:05Z: five groups over the vanilla building groups)
  6. the private construction queue with the vanilla location filter, then recent investments and privatizations,
     topped by two bars of what the player's investors built: domestic vs foreign, and by priority group, both in
     construction points (14:28Z; PMR records them from now on, invest_effects)

Priorities (Pat 04:16Z). Each priority group's slider runs 0..100% of a cap: the cap is +50% weight, or +75% while
Steer the Economy is held. The pool weighs each building group by the `investment_scores` of the ownership buildings
funding it (Manor Houses, Financial Districts), clamped 0.25..1.0 (00_ai.txt:942-950). Those scores are country-scope
script values (vanilla reads has_law_or_variant and country modifiers in them), so a country variable can feed them.
Every score is multiplied by (100 + boost) / (100 + highest boost): a plain x1.5 would hit the 1.0 ceiling, and raising
the ceiling changes vanilla (Manor Houses score farms 2.0 under Agrarianism). So AI countries and untouched sliders are
exactly vanilla, equal sliders cancel, and a boost gains nothing against groups already at the 0.25 floor.
Manufacturing is split into Light, Heavy and Military Industry by adding those child groups to both investment_scores
with Manufacturing's score: vanilla already lists child groups there (bg_mining, bg_logging under bg_extraction;
bg_arts; bg_trade), so a building is inferred to take its nearest listed group. Inferred, not traced in the exe: that
lookup, and that the weight is the pool-share-weighted sum of the scores. Each scored building group then takes the
slider of its priority group (GROUPS).

The GUI cannot write a number into script, so a slider is the budget page's five-coin selector; each coin runs the
group's scripted GUI with the step as a saved value scope (MakeScopeValue, as vanilla's ep2_japan_widgets.gui does).

Policies (Pat: only under Interventionism). One at a time, as a static modifier; a monthly country pulse drops it when
the law is no longer Interventionism. The policy card's plus opens a window beside the panel with every policy as a
blue card that is clicked to adopt it, showing its benefits only, the explanation on hover (Pat 13:05Z and 14:28Z;
Pat also asked for a few fitting benefits to round them out: the modifiers in POLICIES).
  - Steer the Economy (Pat 04:16Z): the sliders' cap goes from +50% to +75%.
  - Favour Large Corporations (Pat 04:15Z): the pool weighs building types your companies list higher. There is no
    modifier or per-country define for company weighting, so each company building type in PMR's building files gets
    ai_value = pmr_ai_value_<b>: its vanilla ai_value plus CORP_BONUS while the card is held. Its other benefits
    work the interventionist way (Pat 14:28Z): a free charter, one more company, the state's cut of company profits.
  - Re-invest (Pat 04:15Z): private retooling of a building is weighted by its group's slider, x(1 + 0.99 x slider%),
    so x100 at a full slider. Retool weight is mostly ai_value (no profit terms), so this multiplies
    pmr_retool_buildings.txt's private ai_value.
  - Favour Small Businesses (Pat confirmed 04:25Z): shopkeepers' investment efficiency +15%, self-investment chance +10%.

Wiring into generate.py main(), after the other writes and before the localization file is written:

    import private_investment
    loc += private_investment.write_all(game, write, header, args.out)

It must run after the building files and pmr_retool_buildings.txt are written: it patches those two outputs in place
(company ai_value; Re-invest's retool multiplier) and asserts what it expects to find.
"""
import os
import re

STEPS = (0, 25, 50, 75, 100)       # priority levels, percent of the cap (Pat 04:50Z: the budget page's five coins)
VAR = 'pmr_ipw_{}'                 # country variable per priority group, 0..100; also the score multiplier's name
ON = 'pmr_ipw_on'                  # set once the player touches any slider
TAB = 'pmr_private'                # InformationPanel tab id of the Private tab
PICK = 'pmr_policy_pick'           # GUI-only flag: the policy window is open
SOURCE_FILE = 'common/buildings/11_private_infrastructure.txt'
QUEUE_GUI = 'gui/construction_queue.gui'
PANEL_GUI = 'gui/construction_panel.gui'
OWN_GUI = 'gui/pmr_private_investment.gui'
COUNTRY = 'GetPlayer'
REFRESH = f"GetScriptedGui('pmr_pc_refresh_sgui').Execute(GuiScope.SetRoot({COUNTRY}.MakeScope).End)"

CAP = 0.5                  # slider at 100% = +50% weight (Pat 04:16Z)
CAP_STEER = 0.75           # +75% under Steer the Economy
SPLIT = {'bg_manufacturing': ('bg_light_industry', 'bg_heavy_industry', 'bg_military_industry')}
# Pat 13:05Z: five priority groups over the vanilla building groups (a building group's children come with it).
# Pat named farms, plantations and fishing for Agriculture; ranches, whaling and rubber plantations join them, and
# military industry joins Heavy Industries (defaults, said in the reply). Each entry: key, name, its NGUI chart colour
# (a vanilla define, so the chart can colour its tiles from the GUI), and the building groups.
GROUPS = [
    ('light', 'Light Industries', 'BUILDING_OWNERSHIP_COLOR_PLAYER_POPS', (0.41, 0.67, 0.74),
     ('bg_light_industry', 'bg_arts')),
    ('heavy', 'Heavy Industries', 'BUILDING_OWNERSHIP_COLOR_PLAYER_GOVERNMENT', (0.20, 0.40, 0.90),
     ('bg_heavy_industry', 'bg_military_industry')),
    ('agriculture', 'Agriculture', 'ALERT_COLOR_GREEN', (0.54, 0.78, 0.33),
     ('bg_agriculture', 'bg_ranching', 'bg_plantations', 'bg_fishing', 'bg_whaling', 'bg_rubber')),
    ('resources', 'Resources', 'BUILDING_OWNERSHIP_COLOR_LOCAL_NON_PLAYER_GOVERNMENT', (0.9, 0.50, 0.2),
     ('bg_mining', 'bg_logging', 'bg_oil_extraction')),
    ('infrastructure', 'Infrastructure', 'ALERT_COLOR_YELLOW', (0.97, 0.77, 0.33),
     ('bg_infrastructure', 'bg_power', 'bg_trade')),
]
GROUP_OF = {bg: k for k, _n, _d, _c, bgs in GROUPS for bg in bgs}
NO_GROUP = 'none'          # a scored building group outside the five (Manufacturing itself): an untouched slider
# The chart counts private levels of these building groups; subsistence farms and ranches are no investors' business.
CHART_EXCLUDE = ('bg_subsistence_agriculture', 'bg_subsistence_ranching')
REINVEST_PER_POINT = 0.99  # Re-invest: retool ai_value x (1 + this x slider%): x100 at 100%
CORP_BONUS = 75000         # Favour Large Corporations: ai_value added, = GBP 10/worker of vanilla's profit term
BASE_AI_VALUE = 1000       # PRODUCTION_BUILDING_BASE_VALUE, when a building has no ai_value

# key, name, icon, modifiers, the card's first benefit (what PMR's script does, short), how that works (hover),
# details (hover). Pat 14:28Z: the cards show benefits only, the explanation goes in the hover; construction and
# investment efficiency belong to Laissez-faire, so the rounding-out benefits added at 13:05Z (construction
# efficiency and allocation, investment efficiency, farmers) are gone, and Favour Large Corporations works the
# interventionist way: charters, companies and the state's cut of their profits. 1.14.5 has no modifier for how
# many monopolies one company may hold (monopolies are company charters; COUNTRY_MONOPOLY_MAX_COUNT is a global
# define), so the card grants a free charter instead.
POLICIES = [
    ('steer', 'Steer the Economy', 'gfx/interface/icons/law_icons/command_economy.dds',
     {},
     f'#P +{CAP_STEER * 100:.0f}%#! Investment Priority Cap',
     f'Each investment priority can add up to #P +{CAP_STEER * 100:.0f}%#! to its group instead of '
     f'#v +{CAP * 100:.0f}%#!.',
     'The state sets investment targets and leans on banks and boards to meet them. Investors still choose what to '
     'build, but within the priorities you set.'),
    ('corporations', 'Favour Large Corporations', 'gfx/interface/icons/law_icons/corporate_state.dds',
     {'country_free_charters_add': 1, 'country_max_companies_add': 1,
      'building_company_government_dividends_add': 0.1},
     '#P Higher#! Investment Weight for Company Industries',
     'Investors weigh building types your companies own as if each earned #P @money!10#! more per worker. A monopoly '
     'is a company charter, so the free charter lets one more of your companies hold one without spending authority.',
     'National champions get licences, contracts and charters, and the state takes its cut of their profits.'),
    ('reinvest', 'Re-invest', 'gfx/interface/icons/law_icons/interventionism.dds',
     {'country_government_dividends_reinvestment_add': 0.1},
     '#P Up to 100×#! Investment Weight for Retooling',
     'Investors favour retooling a building by its group\'s investment priority: up to #P 100×#! at a full '
     'priority.',
     'Profits are ploughed back into the works: new machinery and better methods come before new sites, and the '
     'state\'s own dividends follow them into the pool.'),
    ('small', 'Favour Small Businesses', 'gfx/interface/icons/law_icons/cooperative_ownership.dds',
     {'state_shopkeepers_investment_pool_efficiency_mult': 0.15, 'building_self_investment_chance_add': 0.1},
     None, None,
     'Shopkeepers get easier credit and lighter paperwork, so more of their savings reach the pool and more new '
     'levels stay with the people who work them.'),
]
POLICY_LAW = 'law_interventionism'
RI_WEEKS = 26              # re-investment chart: one point per week (Pat 14:28Z), newest on the right
RI_ROWS, RI_ROW_H, RI_COL_W = 20, 6, 7    # the line is drawn on a 20-row grid, 6 px a row, 7 px a week
PLOT_MARGINS = (52, 14)    # v3_plotline's left and right margins, narrowed so two graphs share the row
POOL_GRAPH_W = 200         # the vanilla investment pool graph beside it (Pat 14:28Z)
COLUMN_DIM = 0.7           # the group columns under the line: the tree chart's colours, darker so the line reads
INVEST_BAR_W, INVEST_BAR_H = 498, 18   # the recent investment bars (Pat 14:28Z)
HOME_COLOR, ABROAD_COLOR = (0.80, 0.66, 0.38), (0.60, 0.44, 0.72)
# Building groups whose types are no investors' business, left out of the bars.
INVEST_EXCLUDE = ('bg_canals', 'bg_construction', 'bg_subsistence_agriculture', 'bg_subsistence_ranching')
LINE_COLOR = (0.9, 0.9, 0.9)              # vanilla's trend line colour (v3_plotline_gdp)
# A plain white texture that 1.14.5 ships (gfx/interface/colors/white.dds, used before, does not exist: the line
# drew nothing, Pat 13:05Z).
WHITE = 'gfx/interface/backgrounds/white.dds'
TRANSPARENT = 'gfx/interface/icons/generic_icons/transparent.dds'
CARD_W, CARD_H = 268, 380                 # law and policy cards, the same size (Pat 04:50Z), taller (Pat 13:05Z)
PCARD_W, PCARD_H = 300, 176               # a policy in the policy window: benefits only (Pat 14:28Z)
MOD_NAMES = {  # how each modifier reads on a policy card (vanilla's names, modifiers.log)
    'country_government_dividends_reinvestment_add': 'Government Dividends Reinvestment',
    'country_free_charters_add': 'Free Company Charters',
    'country_max_companies_add': 'Max Number of Companies',
    'building_company_government_dividends_add': 'Company Government Dividends',
    'state_shopkeepers_investment_pool_efficiency_mult': 'Shopkeepers\' Investment Efficiency',
    'building_self_investment_chance_add': 'Self-investment Chance',
}
WHOLE = ('country_free_charters_add', 'country_max_companies_add')   # counts, not percentages


def benefit_lines(core, mods):
    """A policy's benefits, one per line: what PMR's script does, then each modifier."""
    out = [core] if core else []
    out += [f'#P {v:+d}#! {MOD_NAMES[m]}' if m in WHOLE else f'#P {v * 100:+.0f}%#! {MOD_NAMES[m]}'
            for m, v in mods.items()]
    return '\\n'.join(out)


def fail(where, msg):
    raise SystemExit(f'{where}: {msg}; update tools/pmr/private_investment.py')


def block_end(text, open_brace):
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    fail('block_end', f'unbalanced braces after offset {open_brace}')


def once(text, old, new, where):
    if text.count(old) != 1:
        fail(where, f'expected one {old.strip()[:70]!r}, found {text.count(old)}')
    return text.replace(old, new)


# ---------------------------------------------------------------------------------------------------------------
# Sliders: script side
#

def patch_scores(text):
    """Vanilla 11_private_infrastructure.txt with `multiply = pmr_ipw_<priority group>` as the last line of every
    investment_scores score, and Manufacturing's score copied to its SPLIT children. Returns (text, every group
    scored)."""
    def mult(g):
        if g not in GROUP_OF and g not in SPLIT:
            fail(SOURCE_FILE, f'{g} is scored but in no priority group; add it to GROUPS')
        return VAR.format(GROUP_OF.get(g, NO_GROUP))
    groups, edits, filled = [], [], 0
    for m in re.finditer(r'\binvestment_scores\s*=\s*\{', text):
        end = block_end(text, m.end() - 1)
        body = text[m.end():end]
        if not body.strip():
            continue
        filled += 1
        for e in re.finditer(r'\n(\s*)(bg_[a-z_]+_score)\s*=\s*\{\s*group\s*=\s*"?(bg_[a-z_]+)"?\s*score\s*=\s*\{', body):
            indent, g = e.group(1), e.group(3)
            if g not in groups:
                groups.append(g)
            entry_open = m.end() + e.start() + body[e.start():].index('{')
            entry_close = block_end(text, entry_open)
            score_close = block_end(text, m.end() + e.end() - 1)
            edits.append((score_close, f'\n{indent}\t\t# PMR: investment priorities slider\n{indent}\t\tmultiply = {mult(g)}\n{indent}\t', True))
            groups.extend(c for c in SPLIT.get(g, ()) if c not in groups)
            for child in reversed(SPLIT.get(g, ())):
                entry = text[m.end() + e.start() + 1 + len(indent):entry_close + 1]
                entry = entry.replace(f'{g}_score', f'{child}_score', 1).replace(f'"{g}"', f'"{child}"', 1)
                sc_open = re.search(r'\n\s*score\s*=\s*\{', entry).end() - 1
                sc_close = block_end(entry, sc_open)
                k = sc_close
                while entry[k - 1] in ' \t\n':
                    k -= 1
                entry = (entry[:k] + f'\n{indent}\t\t# PMR: investment priorities slider\n{indent}\t\tmultiply = {mult(child)}\n{indent}\t'
                         + entry[sc_close:])
                edits.append((entry_close + 1, f'\n{indent}# PMR: {child} scored as {g}, with its own priority\n{indent}{entry}', False))
    if filled != 2 or len(edits) < 20:
        fail(SOURCE_FILE, f'expected the Manor House and Financial District investment_scores, found {filled} '
                          f'filled blocks with {len(edits)} scores')
    for pos, ins, trim in sorted(edits, key=lambda t: t[0], reverse=True):
        start = pos
        if trim:
            while text[start - 1] in ' \t\n':
                start -= 1
        text = text[:start] + ins + text[pos:]
    return text, groups


def script_values():
    keys = [k for k, *_r in GROUPS]
    top = ''.join(f'\tif = {{\n\t\tlimit = {{ has_variable = {VAR.format(g)} }}\n\t\tmin = var:{VAR.format(g)}\n\t}}\n'
                  for g in keys)
    out = ('# Country scope. What a full slider adds to a group\'s weight: +50%, or +75% under Steer the Economy.\n'
           f'pmr_ipw_cap = {{\n\tvalue = {CAP}\n\tif = {{\n\t\tlimit = {{ has_modifier = pmr_policy_steer }}\n\t\tvalue = {CAP_STEER}\n\t}}\n}}\n\n'
           '# Country scope. The highest slider position, 0..100 (min = X keeps the value at least X).\n'
           f'pmr_ipw_top = {{\n\tvalue = 0\n{top}}}\n\n'
           '# Country scope, read by the investment_scores of Manor Houses and Financial Districts, one per priority\n'
           '# group: (100 + slider x cap) / (100 + highest slider x cap). Exactly 1 for AI countries and for a player who\n'
           '# never touched the sliders.\n')
    for g in keys:
        v = VAR.format(g)
        out += (f'{v} = {{\n\tvalue = 1\n\tif = {{\n\t\tlimit = {{ has_variable = {ON} }}\n\t\tvalue = 0\n'
                f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = {v} }}\n\t\t\tvalue = var:{v}\n\t\t}}\n'
                '\t\tmultiply = pmr_ipw_cap\n\t\tadd = 100\n'
                '\t\tdivide = {\n\t\t\tvalue = pmr_ipw_top\n\t\t\tmultiply = pmr_ipw_cap\n\t\t\tadd = 100\n\t\t}\n\t}\n}\n\n')
    out += ('# A scored building group in no priority group (Manufacturing itself, now only retooling): an untouched slider.\n'
            f'{VAR.format(NO_GROUP)} = {{\n\tvalue = 1\n\tif = {{\n\t\tlimit = {{ has_variable = {ON} }}\n\t\tvalue = 100\n'
            '\t\tdivide = {\n\t\t\tvalue = pmr_ipw_top\n\t\t\tmultiply = pmr_ipw_cap\n\t\t\tadd = 100\n\t\t}\n\t}\n}\n\n')
    out += '# Country scope. The weight a slider adds now, as a fraction (0.25 = +25%), for the panel.\n'
    for g in keys:
        v = VAR.format(g)
        out += (f'{v}_pct = {{\n\tvalue = 0\n\tif = {{\n\t\tlimit = {{ has_variable = {v} }}\n\t\tvalue = var:{v}\n'
                '\t\tmultiply = pmr_ipw_cap\n\t\tdivide = 100\n\t}\n}\n\n')
    out += ('# State scope, multiplied into private retool buildings\' ai_value (pmr_retool_buildings.txt): while the\n'
            f'# owner holds Re-invest, 1 + {REINVEST_PER_POINT} x the slider of the retooled building\'s group (x100 at 100%).\n')
    for g in keys:
        v = VAR.format(g)
        out += (f'pmr_reinvest_mult_{g} = {{\n\tvalue = 1\n\tif = {{\n\t\tlimit = {{\n\t\t\towner ?= {{\n'
                f'\t\t\t\thas_modifier = pmr_policy_reinvest\n\t\t\t\thas_variable = {v}\n\t\t\t}}\n\t\t}}\n'
                f'\t\tvalue = owner.var:{v}\n\t\tmultiply = {REINVEST_PER_POINT}\n\t\tadd = 1\n\t}}\n}}\n\n')
    # The contributors chart: privately owned levels per priority group (the game's per-building amounts exist only
    # as text). private_ownership_fraction is a comparison, so a building's private share is read to the nearest
    # quarter.
    out += ('# Building scope. Its privately owned levels, to the nearest quarter of its levels.\n'
            'pmr_pc_levels = {\n\tvalue = this.level\n'
            '\tif = {\n\t\tlimit = { private_ownership_fraction < 0.375 }\n\t\tmultiply = 0.25\n\t}\n'
            '\telse_if = {\n\t\tlimit = { private_ownership_fraction < 0.625 }\n\t\tmultiply = 0.5\n\t}\n'
            '\telse_if = {\n\t\tlimit = { private_ownership_fraction < 0.875 }\n\t\tmultiply = 0.75\n\t}\n}\n\n'
            '# Country scope. Privately owned levels in each priority group (is_building_group takes child groups too,\n'
            '# as vanilla\'s bg_military test for barracks shows).\n')
    excl = ''.join(f'\t\t\tis_building_group = {bg}\n' for bg in CHART_EXCLUDE)
    for g, _n, _d, _c, bgs in GROUPS:
        ors = ''.join(f'\t\t\t\tis_building_group = {bg}\n' for bg in bgs)
        out += (f'pmr_pc_{g} = {{\n\tvalue = 0\n\tevery_scope_building = {{\n\t\tlimit = {{\n'
                f'\t\t\tOR = {{\n{ors}\t\t\t}}\n\t\t\tNOR = {{\n{excl}\t\t\t}}\n'
                '\t\t\tprivate_ownership_fraction >= 0.125\n\t\t}\n\t\tadd = pmr_pc_levels\n\t}\n}\n\n')
    return out


def sguis():
    out = ('# Investment priorities. Country scope; scope:step is the coin clicked (0, 25 .. 100), passed from\n'
           f'# {OWN_GUI} with MakeScopeValue.\n\n')
    for g, *_r in GROUPS:
        v = VAR.format(g)
        steps = '\t\telse_'.join(
            f'if = {{\n\t\t\tlimit = {{ scope:step = {s} }}\n\t\t\tset_variable = {{ name = {v} value = {s} }}\n\t\t}}\n'
            for s in STEPS)
        out += (f'{v}_sgui = {{\n\tscope = country\n\tsaved_scopes = {{ step }}\n'
                f'\teffect = {{\n\t\tset_variable = {ON}\n\t\t{steps}\t}}\n}}\n\n')
    out += ('# The contributors chart, recounted whenever the Private tab is opened (and weekly); opening the tab also\n'
            '# starts the weekly clock if it is not running.\n'
            'pmr_pc_refresh_sgui = {\n\tscope = country\n\teffect = {\n\t\tpmr_pc_record = yes\n'
            '\t\tif = {\n\t\t\tlimit = { is_player = yes }\n\t\t\tset_global_variable = { name = pmr_player value = ROOT }\n\t\t}\n'
            '\t\tpmr_pi_start_clock = yes\n\t}\n}\n\n')
    out += ('# Policy cards. is_shown: the country may hold a policy at all (Interventionism); is_valid: this one\n'
            '# is not already held.\n\n'
            f'pmr_policy_available_sgui = {{\n\tscope = country\n\tis_shown = {{ has_law_or_variant = law_type:{POLICY_LAW} }}\n'
            '\teffect = { }\n}\n\n')
    for i, (k, *_rest) in enumerate(POLICIES, 1):
        others = ''.join(f'\t\tif = {{\n\t\t\tlimit = {{ has_modifier = pmr_policy_{o} }}\n'
                         f'\t\t\tremove_modifier = pmr_policy_{o}\n\t\t}}\n' for o, *_r in POLICIES if o != k)
        out += (f'pmr_policy_{k}_sgui = {{\n\tscope = country\n'
                f'\tis_shown = {{ has_law_or_variant = law_type:{POLICY_LAW} }}\n'
                f'\tis_valid = {{\n\t\thas_law_or_variant = law_type:{POLICY_LAW}\n\t\tNOT = {{ has_modifier = pmr_policy_{k} }}\n\t}}\n'
                f'\teffect = {{\n{others}\t\tadd_modifier = {{ name = pmr_policy_{k} }}\n'
                f'\t\tset_variable = {{ name = pmr_policy value = {i} }}\n'
                f'\t\tdebug_log = "PMR;rec=POLICY;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];policy={k}"\n'
                '\t}\n}\n\n')
    return out


def static_modifiers():
    out = '# Policy cards on the construction panel\'s Private tab, one at a time, Interventionism only.\n\n'
    for k, _n, icon, mods, *_r in POLICIES:
        out += f'pmr_policy_{k} = {{\n\ticon = "{icon}"\n' + ''.join(f'\t{m} = {v}\n' for m, v in mods.items()) + '}\n\n'
    return out


def reinvest_effect():
    """Country scope, weekly (pmr_pi.1, Pat 14:28Z), players only. The game keeps no history of the pool's weekly
    income (the budget's Investment Pool Transfer trend is money drawn out for construction), so PMR samples
    investment_pool_income (a country value; its description string is in the 1.14.5 exe) once a week into
    pmr_rw_0 (newest) .. pmr_rw_<N-1>. For the trend line (Pat 04:50Z: like the GDP graph; GUI plot lines only take
    the engine's own trends) each week gets its row on a RI_ROWS grid between the lowest and highest week shown
    (pmr_rw_b_<i>, 1 = bottom), and each pair of neighbouring weeks the rows the line climbs between them
    (pmr_rw_lo_<i>, pmr_rw_hi_<i>, joining week i to week i + 1).
    Under the line, a column per week split by the tree chart's shares that week (Pat 14:28Z): pmr_rs_<g>_<i> is
    the running total of the shares of groups 0..g (1 for the last group, 0 when nothing was counted), and
    pmr_rc_<g>_<i> the height of that running total under the line, in rows; the GUI draws the five as bars from
    the back (the whole column) to the front (the first group alone). The monthly series (pmr_ri_*) of earlier
    versions is left alone and no longer drawn."""
    n, top_row, ng = RI_WEEKS, RI_ROWS - 1, len(GROUPS)
    shift = ''.join(f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_rw_{i - 1} }}\n'
                    f'\t\tset_variable = {{ name = pmr_rw_{i} value = var:pmr_rw_{i - 1} }}\n'
                    + ''.join(f'\t\tset_variable = {{ name = pmr_rs_{g}_{i} value = var:pmr_rs_{g}_{i - 1} }}\n'
                              for g in range(ng))
                    + '\t}\n'
                    for i in range(n - 1, 0, -1))
    shares = '\tset_variable = { name = pmr_rs_0_0 value = var:pmr_pc_share_0 }\n'
    shares += ''.join(f'\tset_variable = {{\n\t\tname = pmr_rs_{g}_0\n\t\tvalue = {{\n\t\t\tvalue = var:pmr_rs_{g - 1}_0\n'
                      f'\t\t\tadd = var:pmr_pc_share_{g}\n\t\t}}\n\t}}\n' for g in range(1, ng - 1))
    shares += (f'\tset_variable = {{ name = pmr_rs_{ng - 1}_0 value = 0 }}\n'
               f'\tif = {{\n\t\tlimit = {{ var:pmr_pc_total > 0 }}\n\t\tset_variable = {{ name = pmr_rs_{ng - 1}_0 value = 1 }}\n\t}}\n')

    def fold(op):
        return ''.join(f'\t\t\tif = {{\n\t\t\t\tlimit = {{ has_variable = pmr_rw_{i} }}\n\t\t\t\t{op} = var:pmr_rw_{i}\n\t\t\t}}\n'
                       for i in range(1, n))
    rows = ''.join(
        f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_rw_{i} }}\n'
        f'\t\tset_variable = {{\n\t\t\tname = pmr_rw_b_{i}\n\t\t\tvalue = {{\n'
        f'\t\t\t\tvalue = {RI_ROWS // 2}\n'
        f'\t\t\t\tif = {{\n\t\t\t\t\tlimit = {{ var:pmr_rw_span > 0 }}\n'
        f'\t\t\t\t\tvalue = var:pmr_rw_{i}\n\t\t\t\t\tsubtract = var:pmr_rw_min\n\t\t\t\t\tdivide = var:pmr_rw_span\n'
        f'\t\t\t\t\tmultiply = {top_row}\n\t\t\t\t\tround = yes\n\t\t\t\t\tadd = 1\n\t\t\t\t}}\n'
        f'\t\t\t}}\n\t\t}}\n'
        + ''.join(f'\t\tset_variable = {{\n\t\t\tname = pmr_rc_{g}_{i}\n\t\t\tvalue = {{\n\t\t\t\tvalue = var:pmr_rw_b_{i}\n'
                  f'\t\t\t\tsubtract = 0.5\n\t\t\t\tmultiply = var:pmr_rs_{g}_{i}\n\t\t\t}}\n\t\t}}\n' for g in range(ng))
        + '\t}\n'
        for i in range(n))
    joins = ''.join(
        f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_rw_{i + 1} }}\n'
        f'\t\tset_variable = {{\n\t\t\tname = pmr_rw_lo_{i}\n\t\t\tvalue = {{\n\t\t\t\tvalue = var:pmr_rw_b_{i}\n'
        f'\t\t\t\tmax = var:pmr_rw_b_{i + 1}\n\t\t\t}}\n\t\t}}\n'
        f'\t\tset_variable = {{\n\t\t\tname = pmr_rw_hi_{i}\n\t\t\tvalue = {{\n\t\t\t\tvalue = var:pmr_rw_b_{i}\n'
        f'\t\t\t\tmin = var:pmr_rw_b_{i + 1}\n\t\t\t}}\n\t\t}}\n\t}}\n'
        for i in range(n - 1))
    return ('pmr_rw_record = {\n'
            + shift +
            '\tset_variable = {\n\t\tname = pmr_rw_0\n\t\tvalue = {\n\t\t\tvalue = investment_pool_income\n\t\t\tmin = 0\n\t\t}\n\t}\n'
            + shares +
            '\t# highest and lowest week shown (min = X keeps a value at least X, max = X at most X)\n'
            '\tset_variable = {\n\t\tname = pmr_rw_max\n\t\tvalue = {\n\t\t\tvalue = var:pmr_rw_0\n' + fold('min') + '\t\t}\n\t}\n'
            '\tset_variable = {\n\t\tname = pmr_rw_min\n\t\tvalue = {\n\t\t\tvalue = var:pmr_rw_0\n' + fold('max') + '\t\t}\n\t}\n'
            '\tset_variable = {\n\t\tname = pmr_rw_span\n\t\tvalue = {\n\t\t\tvalue = var:pmr_rw_max\n\t\t\tsubtract = var:pmr_rw_min\n\t\t}\n\t}\n'
            + rows + joins +
            '\tdebug_log = "PMR;rec=REINVEST;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
            'weekly=[THIS.Var(\'pmr_rw_0\').GetValue|0];min=[THIS.Var(\'pmr_rw_min\').GetValue|0];max=[THIS.Var(\'pmr_rw_max\').GetValue|0];'
            'row=[THIS.Var(\'pmr_rw_b_0\').GetValue|0];column_first_group=[THIS.Var(\'pmr_rc_0_0\').GetValue|2]"\n'
            '}\n')


def chart_effect():
    """Country scope. Counts privately owned levels per priority group into pmr_pc_<i> (GROUPS order, read by the
    tree chart by index) and each group's share of them into pmr_pc_share_<i>; run weekly for players (pmr_pi.1) and
    whenever the Private tab is opened (pmr_pc_refresh_sgui)."""
    sets = ''.join(f'\tset_variable = {{ name = pmr_pc_{i} value = pmr_pc_{g} }}\n' for i, (g, *_r) in enumerate(GROUPS))
    total = ''.join(f'\t\t\tadd = var:pmr_pc_{i}\n' for i in range(len(GROUPS)))
    shares = ''.join(
        f'\tset_variable = {{\n\t\tname = pmr_pc_share_{i}\n\t\tvalue = {{\n\t\t\tvalue = 0\n'
        f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:pmr_pc_total > 0 }}\n\t\t\t\tvalue = var:pmr_pc_{i}\n'
        '\t\t\t\tdivide = var:pmr_pc_total\n\t\t\t}\n\t\t}\n\t}\n'
        for i in range(len(GROUPS)))
    log = ';'.join(f"{g}=[THIS.Var('pmr_pc_{i}').GetValue|1]" for i, (g, *_r) in enumerate(GROUPS))
    return ('pmr_pc_record = {\n' + sets +
            f'\tset_variable = {{\n\t\tname = pmr_pc_total\n\t\tvalue = {{\n\t\t\tvalue = 0\n{total}\t\t}}\n\t}}\n'
            + shares +
            '\tdebug_log = "PMR;rec=CONTRIB;date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetCountry.GetNameNoFormatting];{log}"\n'
            '}\n')


def on_actions():
    drop = ''.join(f'\t\t\tif = {{\n\t\t\t\tlimit = {{ has_modifier = pmr_policy_{k} }}\n'
                   f'\t\t\t\tremove_modifier = pmr_policy_{k}\n\t\t\t}}\n' for k, *_r in POLICIES)
    return ('# Appended to vanilla on_actions the documented way, like pmr_on_actions.txt.\n'
            'on_monthly_pulse_country = { on_actions = { pmr_pi_monthly_country } }\n'
            'on_start_expanding_building = { on_actions = { pmr_pi_on_start } }\n\n'
            '# A policy card lasts only while the country keeps Interventionism. The player\'s weekly clock is restarted\n'
            '# here if its chain broke (pmr_pi_start_clock).\n'
            'pmr_pi_monthly_country = {\n\teffect = {\n\t\tif = {\n'
            f'\t\t\tlimit = {{\n\t\t\t\thas_variable = pmr_policy\n\t\t\t\tNOT = {{ has_law_or_variant = law_type:{POLICY_LAW} }}\n\t\t\t}}\n'
            + drop +
            '\t\t\tremove_variable = pmr_policy\n'
            '\t\t\tdebug_log = "PMR;rec=POLICY;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];policy=dropped"\n'
            '\t\t}\n'
            '\t\tif = {\n\t\t\tlimit = { is_player = yes }\n'
            '\t\t\tset_global_variable = { name = pmr_player value = ROOT }\n'
            '\t\t\tpmr_pi_start_clock = yes\n\t\t}\n'
            '\t}\n}\n\n'
            '# Root = building, a level of it starting construction (the Recent Investments bars).\n'
            'pmr_pi_on_start = {\n\teffect = {\n\t\tpmr_pi_start = yes\n\t}\n}\n')


def clock_effect():
    return ('# Country scope. Starts the weekly clock (pmr_pi.1) unless it is running: from the monthly pulse and\n'
            '# whenever the Private tab is opened. pmr_pi_clock outlives a week by two days, so a live clock is never\n'
            '# started twice.\n'
            'pmr_pi_start_clock = {\n\tif = {\n\t\tlimit = {\n\t\t\tis_player = yes\n\t\t\tNOT = { has_variable = pmr_pi_clock }\n\t\t}\n'
            '\t\tset_variable = { name = pmr_pi_clock days = 9 }\n'
            '\t\ttrigger_event = { id = pmr_pi.1 days = 1 }\n'
            '\t\tdebug_log = "PMR;rec=CLOCK;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting]"\n'
            '\t}\n}\n')


def events():
    return ('namespace = pmr_pi\n\n'
            '# Country, every 7 days while it is a player\'s: the Private tab\'s weekly chart (Pat 14:28Z). 1.14.5 runs\n'
            '# no weekly on_action for script, so the event re-arms itself; pmr_pi_start_clock restarts a broken chain.\n'
            'pmr_pi.1 = {\n\ttype = country_event\n\thidden = yes\n\timmediate = {\n\t\tif = {\n\t\t\tlimit = { is_player = yes }\n'
            '\t\t\tset_variable = { name = pmr_pi_clock days = 9 }\n'
            '\t\t\tset_global_variable = { name = pmr_player value = ROOT }\n'
            '\t\t\tpmr_pc_record = yes\n\t\t\tpmr_rw_record = yes\n'
            '\t\t\ttrigger_event = { id = pmr_pi.1 days = 7 }\n\t\t}\n\t}\n}\n')


def invest_types(game):
    """(type without building_, priority group index, construction points a level) for every building type the
    investment bars count: the five groups' buildable types with a construction cost; canals, the construction
    sector and subsistence buildings are no investors' business."""
    btype, parent = building_groups(game)
    costs = dict((k, float(v)) for k, v in re.findall(
        r'^\s*(construction_cost_[a-z_]+)\s*=\s*([0-9.]+)',
        open(os.path.join(game, 'common', 'script_values', 'building_values.txt'), encoding='utf-8-sig').read(), re.M))
    index = {k: i for i, (k, *_r) in enumerate(GROUPS)}
    out = []
    bdir = os.path.join(game, 'common', 'buildings')
    for name in sorted(os.listdir(bdir)):
        if not name.endswith('.txt'):
            continue
        t = open(os.path.join(bdir, name), encoding='utf-8-sig').read()
        for k, _s, o, c in top_blocks(t):
            g = group_of(k, btype, parent)
            if not g or btype.get(k) in INVEST_EXCLUDE:
                continue
            body = t[o:c]
            if re.search(r'\n\s*(buildable\s*=\s*no|unique\s*=\s*yes)', body):
                continue
            rc = re.search(r'\n\s*required_construction\s*=\s*([a-z_0-9.]+)', body)
            if not rc:
                continue
            cost = costs.get(rc.group(1))
            if cost is None:
                try:
                    cost = float(rc.group(1))
                except ValueError:
                    fail(f'common/buildings/{name}', f'{k} costs {rc.group(1)}, not a number or a building_values value')
            out.append((k[len('building_'):], index[g], f'{cost:g}'))
    if len(out) < 40:
        fail('common/buildings', f'expected about 50 investable building types, found {len(out)}')
    return out


def invest_effects(types):
    """The Recent Investments bars (Pat 14:28Z: foreign vs domestic, and by priority group in construction points).
    The game lists previous investments only as text, so PMR keeps its own record from now on: when a level starts
    (on_start_expanding_building) the player's levels in the building and every government's are put on the
    state by building type (pmr_iv_o_<b>, pmr_iv_g_<b>); when a level completes (PMR's on_building_built and
    on_building_expanded, before anything else) the change says who built it. The player's levels went up and no
    government's did: the player's investors built it, and its construction points count. Retool buildings are
    not counted. levels_owned_by_country counts a country's government and its investors; country_ownership_fraction
    is every government's share; both are comparisons only, so pmr_pi_read finds them by halving steps."""
    steps = (128, 64, 32, 16, 8, 4, 2, 1)
    own = ''.join(
        f'\tstate = {{ set_variable = {{ name = pmr_iv_t value = {{ value = var:pmr_iv_x add = {s} }} }} }}\n'
        f'\tif = {{\n\t\tlimit = {{ levels_owned_by_country = {{ target = global_var:pmr_player value >= state.var:pmr_iv_t }} }}\n'
        f'\t\tstate = {{ set_variable = {{ name = pmr_iv_x value = var:pmr_iv_t }} }}\n\t}}\n' for s in steps)
    gov = ''.join(
        f'\t\tstate = {{\n\t\t\tset_variable = {{\n\t\t\t\tname = pmr_iv_t\n\t\t\t\tvalue = {{\n\t\t\t\t\tvalue = var:pmr_iv_y\n'
        f'\t\t\t\t\tadd = {s - 0.5:g}\n\t\t\t\t\tdivide = scope:pmr_iv_b.level\n\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n'
        f'\t\tif = {{\n\t\t\tlimit = {{ country_ownership_fraction >= state.var:pmr_iv_t }}\n'
        f'\t\t\tstate = {{ change_variable = {{ name = pmr_iv_y add = {s} }} }}\n\t\t}}\n' for s in steps)
    read = ('# Building scope. On its state: pmr_iv_x = the player\'s levels in it (government and investors),\n'
            '# pmr_iv_y = levels owned by any government, both to 255.\n'
            'pmr_pi_read = {\n\tsave_scope_as = pmr_iv_b\n'
            '\tstate = {\n\t\tset_variable = { name = pmr_iv_x value = 0 }\n\t\tset_variable = { name = pmr_iv_y value = 0 }\n\t}\n'
            + own +
            '\tif = {\n\t\tlimit = {\n\t\t\tlevel > 0\n\t\t\tcountry_ownership_fraction > 0\n\t\t}\n' + gov + '\t}\n}\n\n')

    def dispatch(effect, with_gc):
        out = ''
        for k, (s, g, c) in enumerate(types):
            args = f'S = {s} G = {g} C = {c}' if with_gc else f'S = {s}'
            out += (f'\t\t{"else_if" if k else "if"} = {{\n\t\t\tlimit = {{ is_building_type = building_{s} }}\n'
                    f'\t\t\t{effect} = {{ {args} }}\n\t\t}}\n')
        return out
    where = ('date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
             'state=[THIS.GetState.GetNameNoFormatting];building=$S$')
    nums = ("levels=[THIS.Var('pmr_iv_d').GetValue|0];government_levels=[THIS.Var('pmr_iv_dg').GetValue|0];"
            "points=[THIS.Var('pmr_iv_p').GetValue|0]")

    def log(kind):
        return f'\t\t\tstate = {{ debug_log = "PMR;rec=INVEST;{where};kind={kind};{nums}" }}\n'
    ng = len(GROUPS)
    init = ''.join(f'\t\t\t\t\tset_variable = {{ name = pmr_iv_pts_{g} value = 0 }}\n' for g in range(ng))
    snap = ('# Building scope, $S$ = its type without building_. Its levels now, until one completes.\n'
            'pmr_pi_snap = {\n\tpmr_pi_read = yes\n\tstate = {\n'
            '\t\tset_variable = { name = pmr_iv_o_$S$ value = var:pmr_iv_x }\n'
            '\t\tset_variable = { name = pmr_iv_g_$S$ value = var:pmr_iv_y }\n\t}\n}\n\n')
    done = ('# Building scope, a level of it just completed; $S$ as above, $G$ its priority group (GROUPS order), $C$ the\n'
            '# construction points of a level.\n'
            'pmr_pi_done = {\n\tpmr_pi_read = yes\n'
            '\t# a building\'s first level: nothing was there before it\n'
            '\tif = {\n\t\tlimit = { level <= 1 }\n\t\tstate = {\n'
            '\t\t\tset_variable = { name = pmr_iv_o_$S$ value = 0 }\n\t\t\tset_variable = { name = pmr_iv_g_$S$ value = 0 }\n\t\t}\n\t}\n'
            '\tif = {\n\t\tlimit = { state = { NOT = { has_variable = pmr_iv_o_$S$ } } }\n'
            f'\t\tstate = {{ debug_log = "PMR;rec=INVEST_MISS;{where}" }}\n\t}}\n'
            '\telse = {\n\t\tstate = {\n'
            '\t\t\tset_variable = {\n\t\t\t\tname = pmr_iv_d\n\t\t\t\tvalue = {\n\t\t\t\t\tvalue = var:pmr_iv_x\n\t\t\t\t\tsubtract = var:pmr_iv_o_$S$\n\t\t\t\t}\n\t\t\t}\n'
            '\t\t\tset_variable = {\n\t\t\t\tname = pmr_iv_dg\n\t\t\t\tvalue = {\n\t\t\t\t\tvalue = var:pmr_iv_y\n\t\t\t\t\tsubtract = var:pmr_iv_g_$S$\n\t\t\t\t}\n\t\t\t}\n'
            '\t\t\tset_variable = {\n\t\t\t\tname = pmr_iv_p\n\t\t\t\tvalue = {\n\t\t\t\t\tvalue = var:pmr_iv_d\n\t\t\t\t\tmultiply = $C$\n\t\t\t\t}\n\t\t\t}\n'
            '\t\t\tsave_scope_as = pmr_iv_s\n\t\t}\n'
            '\t\tif = {\n\t\t\tlimit = {\n\t\t\t\tstate = {\n\t\t\t\t\tvar:pmr_iv_d >= 1\n\t\t\t\t\tvar:pmr_iv_dg <= 0\n\t\t\t\t}\n\t\t\t}\n'
            '\t\t\tglobal_var:pmr_player = {\n'
            '\t\t\t\tif = {\n\t\t\t\t\tlimit = { NOT = { has_variable = pmr_iv_tot } }\n' + init +
            '\t\t\t\t\tset_variable = { name = pmr_iv_dom value = 0 }\n\t\t\t\t\tset_variable = { name = pmr_iv_for value = 0 }\n\t\t\t\t}\n'
            '\t\t\t\tchange_variable = { name = pmr_iv_pts_$G$ add = scope:pmr_iv_s.var:pmr_iv_p }\n\t\t\t}\n'
            '\t\t\tif = {\n\t\t\t\tlimit = { owner = global_var:pmr_player }\n'
            '\t\t\t\tglobal_var:pmr_player = { change_variable = { name = pmr_iv_dom add = scope:pmr_iv_s.var:pmr_iv_p } }\n\t\t\t}\n'
            '\t\t\telse = {\n'
            '\t\t\t\tglobal_var:pmr_player = { change_variable = { name = pmr_iv_for add = scope:pmr_iv_s.var:pmr_iv_p } }\n\t\t\t}\n'
            '\t\t\tglobal_var:pmr_player = { pmr_pi_shares = yes }\n'
            + log('private') +
            '\t\t}\n'
            '\t\telse_if = {\n\t\t\tlimit = { state = { var:pmr_iv_d >= 1 } }\n' + log('government') + '\t\t}\n'
            '\t\telse = {\n' + log('other') + '\t\t}\n'
            '\t}\n'
            '\t# the next level of the same construction starts from here\n'
            '\tstate = {\n\t\tset_variable = { name = pmr_iv_o_$S$ value = var:pmr_iv_x }\n'
            '\t\tset_variable = { name = pmr_iv_g_$S$ value = var:pmr_iv_y }\n\t}\n}\n\n')
    tot = ''.join(f'\t\t\tadd = var:pmr_iv_pts_{g}\n' for g in range(ng))
    gs = ''.join(f'\tset_variable = {{\n\t\tname = pmr_iv_gs_{g}\n\t\tvalue = {{\n\t\t\tvalue = var:pmr_iv_pts_{g}\n'
                 '\t\t\tdivide = var:pmr_iv_tot\n\t\t}\n\t}\n' for g in range(ng))
    gc = '\tset_variable = { name = pmr_iv_gc_0 value = var:pmr_iv_gs_0 }\n'
    gc += ''.join(f'\tset_variable = {{\n\t\tname = pmr_iv_gc_{g}\n\t\tvalue = {{\n\t\t\tvalue = var:pmr_iv_gc_{g - 1}\n'
                  f'\t\t\tadd = var:pmr_iv_gs_{g}\n\t\t}}\n\t}}\n' for g in range(1, ng - 1))
    gc += f'\tset_variable = {{ name = pmr_iv_gc_{ng - 1} value = 1 }}\n'
    shares_fx = ('# Country scope (the player). Each group\'s share of the construction points counted (pmr_iv_gs_<g>), the\n'
                 '# running totals the bar draws from the back (pmr_iv_gc_<g>), and the domestic and foreign shares.\n'
                 'pmr_pi_shares = {\n'
                 f'\tset_variable = {{\n\t\tname = pmr_iv_tot\n\t\tvalue = {{\n\t\t\tvalue = 0\n{tot}\t\t}}\n\t}}\n'
                 '\tif = {\n\t\tlimit = { var:pmr_iv_tot > 0 }\n'
                 + ''.join('\t' + line + '\n' for line in (gs + gc).rstrip('\n').split('\n')) +
                 '\t\tset_variable = {\n\t\t\tname = pmr_iv_dsh\n\t\t\tvalue = {\n\t\t\t\tvalue = var:pmr_iv_dom\n'
                 '\t\t\t\tdivide = var:pmr_iv_tot\n\t\t\t}\n\t\t}\n'
                 '\t\tset_variable = {\n\t\t\tname = pmr_iv_fsh\n\t\t\tvalue = {\n\t\t\t\tvalue = var:pmr_iv_for\n'
                 '\t\t\t\tdivide = var:pmr_iv_tot\n\t\t\t}\n\t\t}\n\t}\n}\n\n')
    hooks = ('# Building scope (on_start_expanding_building, every country\'s): note the levels of a counted type.\n'
             'pmr_pi_start = {\n\tif = {\n\t\tlimit = { has_global_variable = pmr_player }\n'
             + dispatch('pmr_pi_snap', False).replace('\n\t\t', '\n\t\t') +
             '\t}\n}\n\n'
             '# Building scope (PMR\'s on_building_built and on_building_expanded, every country\'s): a level completed\n'
             '# in a building the player owns levels in.\n'
             'pmr_pi_on_done = {\n\tif = {\n\t\tlimit = {\n\t\t\thas_global_variable = pmr_player\n'
             '\t\t\tlevels_owned_by_country = { target = global_var:pmr_player value >= 1 }\n\t\t}\n'
             + dispatch('pmr_pi_done', True) +
             '\t}\n}\n')
    return read + snap + shares_fx + done + hooks   # an effect is defined before its first use


# ---------------------------------------------------------------------------------------------------------------
# GUI: vanilla construction_panel.gui and construction_queue.gui, patched
#

VANILLA_TABS_2_3 = (
    '\t\t\t\tblockoverride "second_button"\n\t\t\t\t{\n\t\t\t\t\ttext = "CONSTRUCTION_TAB_FOREIGN"\n\t\t\t\t}\n')


def patch_panel(text):
    """construction_panel.gui: tabs become Government | Private | Foreign | Ships; the Private tab's contents go
    beside the domestic queue; the domestic pager follows the tab instead of the funding filter."""
    where = PANEL_GUI
    start = text.find('\t\t\ttab_buttons = {')
    if start < 0 or text.count('\t\t\ttab_buttons = {') != 1:
        fail(where, 'expected one tab_buttons in the construction panel')
    end = block_end(text, text.index('{', start))
    tabs = text[start:end + 1]
    for n in ('third', 'second'):
        nxt = {'second': 'third', 'third': 'fourth'}[n]
        tabs = re.sub(rf'"{n}_button', f'"{nxt}_button', tabs)
    if tabs.count('"fourth_button') != 6 or tabs.count('"third_button') != 6 or '"second_button' in tabs:
        fail(where, 'the tab_buttons block no longer has three tabs of six blocks each')
    if tabs.count('"CONSTRUCTION_TAB_DOMESTIC"') != 3:
        fail(where, 'expected the first tab to name CONSTRUCTION_TAB_DOMESTIC three times')
    tabs = tabs.replace('tooltip = "CONSTRUCTION_TAB_DOMESTIC"', 'tooltip = "PMR_TAB_GOVERNMENT_TT"')
    tabs = tabs.replace('"CONSTRUCTION_TAB_DOMESTIC"', '"PMR_TAB_GOVERNMENT"')
    private = (
        '\t\t\t\t# PMR: Private tab\n'
        '\t\t\t\tblockoverride "second_button" {\n\t\t\t\t\ttext = "PMR_TAB_PRIVATE"\n\t\t\t\t}\n'
        '\t\t\t\tblockoverride "second_button_tooltip" {\n\t\t\t\t\ttooltip = "PMR_TAB_PRIVATE_TT"\n\t\t\t\t}\n'
        f'\t\t\t\tblockoverride "second_button_click" {{\n\t\t\t\t\tonclick = "[InformationPanel.SelectTab(\'{TAB}\')]"\n'
        f'\t\t\t\t\tonclick = "[{REFRESH}]"\n'
        f'\t\t\t\t\tonclick = "[GetVariableSystem.Clear(\'{PICK}\')]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "second_button_visibility" {{\n\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'{TAB}\')]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "second_button_visibility_checked" {{\n\t\t\t\t\tvisible = "[Not( InformationPanel.IsTabSelected(\'{TAB}\') )]"\n\t\t\t\t}}\n'
        '\t\t\t\tblockoverride "second_button_selected" {\n\t\t\t\t\ttext = "PMR_TAB_PRIVATE"\n\t\t\t\t}\n\n')
    tabs = once(tabs, '\t\t\t\tblockoverride "third_button"\n', private + '\t\t\t\tblockoverride "third_button"\n', where)
    text = text[:start] + tabs + text[end + 1:]

    # The policy window, beside the panel where other panels put their map-mode button (block_windows.gui: the
    # window root allows children outside it; map_modes_button_position is { 607 102 }).
    text = once(text, '\t\t#TOP\n\t\tblockoverride "fixed_top"\n',
                '\t\t# PMR: the economic policy window\n\t\tblockoverride "map_modes_button" {\n'
                '\t\t\tpmr_policy_window = {}\n\t\t}\n\n'
                '\t\t#TOP\n\t\tblockoverride "fixed_top"\n', where)

    # The Private tab's contents, after the domestic tab's flowcontainer.
    text = once(text, '\t\t\t# FOREIGN QUEUE TAB CONTENTS\n',
                '\t\t\t# PMR: PRIVATE TAB CONTENTS\n'
                '\t\t\tflowcontainer = {\n'
                f'\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'{TAB}\')]"\n'
                '\t\t\t\tdirection = vertical\n'
                '\t\t\t\tdatacontext = "[AccessPlayer]"\n'
                '\t\t\t\tpmr_private_tab = {}\n'
                '\t\t\t}\n\n'
                '\t\t\t# FOREIGN QUEUE TAB CONTENTS\n', where)

    # The domestic pager: government pages on the Government tab, private pages on the Private tab.
    a = text.find('\t\t\t\tname = "construction_queue_pages"')
    b = text.find('\t\t\t# SHIP QUEUE PAGE BUTTONS')
    if a < 0 or b < a:
        fail(where, 'the domestic pager (construction_queue_pages) moved')
    pager = text[a:b]
    pager = once(pager, 'visible = "[InformationPanel.IsTabSelected(\'default\')]"',
                 f'visible = "[Or(InformationPanel.IsTabSelected(\'default\'), InformationPanel.IsTabSelected(\'{TAB}\'))]"',
                 where)
    n_gov = pager.count('ConstructionPanel.IsShowingGovernmentConstructions')
    n_priv = pager.count('ConstructionPanel.IsShowingPrivateConstructions')
    if (n_gov, n_priv) != (2, 2):
        fail(where, f'expected the pager to test the funding filter twice each, found {n_gov} and {n_priv}')
    pager = pager.replace('ConstructionPanel.IsShowingGovernmentConstructions', "InformationPanel.IsTabSelected('default')")
    pager = pager.replace('ConstructionPanel.IsShowingPrivateConstructions', f"InformationPanel.IsTabSelected('{TAB}')")
    return text[:a] + pager + text[b:]


def patch_queue(text):
    """construction_queue.gui: the Government tab's queue. The investment pool section, the funding filter and the
    private list go (they live on the Private tab); the government list no longer waits for the funding filter."""
    where = QUEUE_GUI
    # 1. the investment pool block: the first child flowcontainer of construction_queue, ending before the header
    a = text.find('\t\tflowcontainer = {\n\t\t\tparentanchor = hcenter\n\t\t\tdirection = vertical\n\n\t\t\tbackground = {\n\t\t\t\tusing = dark_area')
    if a < 0 or 'CURRENT_INVESTMENT_POOL' not in text[a:block_end(text, text.index('{', a))]:
        fail(where, 'the investment pool block moved')
    e = block_end(text, text.index('{', a))
    text = text[:a] + '\t\t# PMR: the investment pool moved to the Private tab (pmr_private_investment.gui)\n' + text[e + 2:]
    # 2. the funding filter: its label and its button row
    label = list(re.finditer(r'textbox = \{(\s*)size = \{ 95 60 \}\s*text = "CONSTRUCTION_QUEUE_FILTER_FUNDING"', text))
    if len(label) != 1:
        fail(where, f'expected one funding filter label, found {len(label)}')
    m = label[0]
    text = text[:m.start()] + 'textbox = {' + m.group(1) + 'visible = no  # PMR: funding is a tab now' + text[m.start() + len('textbox = {'):]
    m = text.find('text = "CONSTRUCTION_QUEUE_FILTER_FUNDING_NATIONAL"')
    rows = [r for r in re.finditer(r'flowcontainer = \{(\s*)', text[:m])]
    if m < 0 or not rows:
        fail(where, 'the funding filter buttons moved')
    r = rows[-1]
    text = text[:r.start()] + 'flowcontainer = {' + r.group(1) + 'visible = no  # PMR: funding is a tab now' + r.group(1) + text[r.end():]
    # 3. the private list goes; the government list shows without the funding filter
    a = text.find('\t\t# PRIVATE CONSTRUCTION QUEUE\n')
    b = text.find('\t\t# GOVERNMENT CONSTRUCTION QUEUE\n')
    if a < 0 or b < a:
        fail(where, 'the private and government lists moved')
    text = text[:a] + '\t\t# PMR: the private list moved to the Private tab\n\n' + text[b:]
    text = once(text, 'visible = "[And(ConstructionPanel.IsShowingGovernmentConstructions, Not(IsDataModelEmpty(',
                'visible = "[And(\'(bool)yes\', Not(IsDataModelEmpty(', where)
    text = once(text, 'visible = "[Not(Country.HasConstructionQueued)]"',
                'visible = "[IsDataModelEmpty(Country.AccessPagedGovernmentConstructionQueue(ConstructionPanel.'
                'AccessCurrentGovernmentConstructionQueuePage(GetMetaPlayer.GetPlayedOrObservedCountry), ConstructionPanel.GetFilter))]"',
                where)
    return text


# ---------------------------------------------------------------------------------------------------------------
# GUI: the Private tab (own file)
#

def header(key, ind):
    return f'{ind}default_header = {{\n{ind}\tblockoverride "text" {{\n{ind}\t\ttext = "{key}"\n{ind}\t}}\n{ind}}}\n'


def priority_row(g, ind):
    """One priority group, on the budget page's own five-coin selector (Pat 04:50Z): vanilla's tax_exp_frame_coin
    with its coins, sounds and selected frame, each coin one of STEPS. The value reads +0%, or +25% in green and so
    on (Pat 13:05Z): two textboxes in the selector's divider block, its own money text hidden."""
    v = VAR.format(g)
    cur = f"{COUNTRY}.MakeScope.Var('{v}').GetValue"
    pct = f"{COUNTRY}.MakeScope.ScriptValue('{v}_pct')"
    up = f"GreaterThan_CFixedPoint({pct}, '(CFixedPoint)0')"

    def execute(s):
        return (f"GetScriptedGui('{v}_sgui').Execute(GuiScope.SetRoot({COUNTRY}.MakeScope)"
                f".AddScope('step', MakeScopeValue('(CFixedPoint){s}')).End)")

    def selected(k):
        # the nearest coin, so a value between coins still shows one
        lo = (STEPS[k - 1] + STEPS[k]) // 2 if k else None
        hi = (STEPS[k] + STEPS[k + 1]) // 2 if k + 1 < len(STEPS) else None
        tests = ([f"GreaterThanOrEqualTo_CFixedPoint({cur}, '(CFixedPoint){lo}')"] if lo is not None else []) + \
                ([f"LessThan_CFixedPoint({cur}, '(CFixedPoint){hi}')"] if hi is not None else [])
        return tests[0] if len(tests) == 1 else f'And({tests[0]}, {tests[1]})'

    def value(vis, text):
        return (f'{ind}\t\ttextbox = {{\n{ind}\t\t\tvisible = "[{vis}]"\n{ind}\t\t\tautoresize = yes\n'
                f'{ind}\t\t\tparentanchor = right|vcenter\n{ind}\t\t\tmargin_bottom = 6\n{ind}\t\t\tusing = fontsize_large\n'
                f'{ind}\t\t\traw_text = "{text}"\n{ind}\t\t\ttooltip = "PMR_IPW_ROW_{g}"\n{ind}\t\t}}\n')
    out = (f'{ind}# {g}\n{ind}tax_exp_frame_coin = {{\n{ind}\tparentanchor = hcenter\n'
           f'{ind}\tblockoverride "tutorial_highilight_name" {{}}\n'
           f'{ind}\tblockoverride "text_upper" {{\n{ind}\t\ttext = "PMR_IPW_GROUP_{g}"\n{ind}\t\ttooltip = "PMR_IPW_ROW_{g}"\n{ind}\t}}\n'
           f'{ind}\tblockoverride "second_line" {{}}\n'
           f'{ind}\tblockoverride "text_money" {{\n{ind}\t\tvisible = no\n{ind}\t\traw_text = ""\n{ind}\t}}\n'
           f'{ind}\tblockoverride "divider" {{\n{ind}\t\tdivider_clean = {{}}\n'
           + value(f'Not({up})', '#v +0%#!')
           + value(up, f"#P +[{pct}|0%]#!")
           + f'{ind}\t}}\n')
    for k, s in enumerate(STEPS):
        n = k + 1
        out += (f'{ind}\tblockoverride "button_{n}_click" {{\n{ind}\t\tonclick = "[{execute(s)}]"\n{ind}\t}}\n'
                f'{ind}\tblockoverride "tooltip_{n}" {{\n{ind}\t\ttooltip = "PMR_IPW_NOTCH_{s}"\n{ind}\t}}\n'
                f'{ind}\tblockoverride "is_selected_visibility_{n}" {{\n{ind}\t\tvisible = "[{selected(k)}]"\n{ind}\t}}\n')
    return out + f'{ind}}}\n'


def bar(ind, x, y, w, h, value, maximum, color, direction='horizontal', visible=None):
    """A flat progressbar in one colour (vanilla's white_progressbar_vertical colours its bar the same way)."""
    r, g, b = color
    vis = f'{ind}\tvisible = "[{visible}]"\n' if visible else ''
    return (f'{ind}progressbar = {{\n{vis}{ind}\tposition = {{ {x} {y} }}\n{ind}\tsize = {{ {w} {h} }}\n'
            f'{ind}\tdirection = {direction}\n{ind}\tmin = 0\n{ind}\tmax = {maximum}\n{ind}\tvalue = "[{value}]"\n'
            f'{ind}\tprogresstexture = "{WHITE}"\n{ind}\tnoprogresstexture = "{TRANSPARENT}"\n'
            f'{ind}\tcolor = {{ {r:.2f} {g:.2f} {b:.2f} 1 }}\n{ind}\talwaystransparent = yes\n{ind}}}\n')


def reinvest_chart(ind):
    """The weekly re-investment as a trend line in vanilla's graph frame (v3_plotline, as the GDP graph; Pat
    04:50Z, weekly since 14:28Z). GUI plot lines only take the engine's own trends, so the line is drawn from
    cells: for each week (pmr_rw_<i>, 0 = newest, rightmost) a flat segment on its row (pmr_rw_b_<i>), and at the
    week's left edge a riser through the rows between it and the week before (pmr_rw_lo_<i> .. pmr_rw_hi_<i>).
    Under the line each week is a column split by the tree chart's shares (pmr_rc_<g>_<i>, reinvest_effect),
    drawn first so the line stays on top, in the groups' colours darkened so the white line reads over them."""
    var = lambda name: f"{COUNTRY}.MakeScope.Var('{name}').GetValue"
    fp = lambda x: f"'(CFixedPoint){x}'"
    w, h = RI_WEEKS * RI_COL_W, RI_ROWS * RI_ROW_H
    mid = lambda row: h - row * RI_ROW_H + RI_ROW_H // 2   # centre of a row, 1 = bottom
    r, g, b = LINE_COLOR
    i2, i3 = ind + '\t\t', ind + '\t\t\t'

    def cell(vis, x, y, cw, ch):
        return (f'{i2}icon = {{\n{i3}visible = "[{vis}]"\n{i3}position = {{ {x} {y} }}\n{i3}size = {{ {cw} {ch} }}\n'
                f'{i3}texture = "{WHITE}"\n{i3}color = {{ {r} {g} {b} 1 }}\n{i3}alwaystransparent = yes\n{i2}}}\n')
    columns, cells, hover = '', '', ''
    for c in range(RI_WEEKS):
        i = RI_WEEKS - 1 - c
        for gi in range(len(GROUPS) - 1, -1, -1):
            dim = tuple(x * COLUMN_DIM for x in GROUPS[gi][3])
            columns += bar(i2, c * RI_COL_W, 0, RI_COL_W - 1, h, f"FixedPointToFloat({var(f'pmr_rc_{gi}_{i}')})",
                           RI_ROWS, dim, 'vertical', f"GreaterThan_CFixedPoint({var(f'pmr_rc_{gi}_{i}')}, {fp(0)})")
        for row in range(1, RI_ROWS + 1):
            cells += cell(f"EqualTo_CFixedPoint({var(f'pmr_rw_b_{i}')}, {fp(row)})", c * RI_COL_W, mid(row) - 1, RI_COL_W, 3)
        if c:
            for row in range(1, RI_ROWS):
                cells += cell(f"And(LessThanOrEqualTo_CFixedPoint({var(f'pmr_rw_lo_{i}')}, {fp(row)}), "
                              f"GreaterThan_CFixedPoint({var(f'pmr_rw_hi_{i}')}, {fp(row)}))",
                              c * RI_COL_W - 1, mid(row + 1) - 1, 3, RI_ROW_H + 2)
        hover += (f'{i2}widget = {{\n{i3}visible = "[GreaterThan_CFixedPoint({var(f"pmr_rw_b_{i}")}, {fp(0)})]"\n'
                  f'{i3}position = {{ {c * RI_COL_W} 0 }}\n{i3}size = {{ {RI_COL_W} {h} }}\n'
                  f'{i3}tooltip = "PMR_RW_COLUMN_{i}"\n{i3}using = tooltip_above\n{i2}}}\n')
    has = f"GreaterThan_CFixedPoint({var('pmr_rw_b_0')}, {fp(0)})"
    bo = lambda name, body: f'{ind}\tblockoverride "{name}" {{\n{body}{ind}\t}}\n'
    left, right = PLOT_MARGINS
    return (f'{ind}v3_plotline = {{\n'
            + bo('margins', f'{ind}\t\tmargin_bottom = 40\n{ind}\t\tmargin_left = {left}\n{ind}\t\tmargin_right = {right}\n')
            + bo('text_max_width', f'{ind}\t\tmax_width = {w + left + right - 10}\n')
            + bo('header', f'{ind}\t\ttext = "PMR_RW_CHART_HEADER"\n')
            + bo('size', f'{ind}\t\tsize = {{ {w} {h} }}\n')
            + bo('singleitem', '') + bo('multiitem', '')
            + bo('extra_plotlines', columns + cells + hover)
            + bo('maxvalue', f'{ind}\t\traw_text = "@money![{var("pmr_rw_max")}|K]"\n')
            + bo('minvalue', f'{ind}\t\traw_text = "@money![{var("pmr_rw_min")}|K]"\n')
            + bo('startdate', f'{ind}\t\ttext = "PMR_RW_AXIS_START"\n')
            + bo('enddate', f'{ind}\t\ttext = "PMR_RW_AXIS_END"\n')
            + bo('empty_state_visibility', f'{ind}\t\tvisible = "[Not({has})]"\n')
            + bo('everything_that_is_not_empty_state_visibility', f'{ind}\t\tvisible = "[{has}]"\n')
            + bo('empty_state_text', f'{ind}\t\ttext = "PMR_RW_EMPTY"\n')
            + f'{ind}}}\n')


def pool_chart(ind):
    """The budget's own investment pool graph (Pat 14:28Z, beside the re-investment line): vanilla's
    GraphTooltip_InvestmentPool plot, the engine's weekly trend of the pool, narrowed to share the row."""
    t = f'{COUNTRY}.GetInvestmentFundTrend'
    left, right = PLOT_MARGINS
    bo = lambda name, body: f'{ind}\tblockoverride "{name}" {{\n{body}{ind}\t}}\n'
    return (f'{ind}v3_plotline = {{\n'
            + bo('margins', f'{ind}\t\tmargin_bottom = 40\n{ind}\t\tmargin_left = {left}\n{ind}\t\tmargin_right = {right}\n')
            + bo('text_max_width', f'{ind}\t\tmax_width = {POOL_GRAPH_W + left + right - 10}\n')
            + bo('header', f'{ind}\t\ttext = "[concept_investment_pool]"\n')
            + bo('line_color', f'{ind}\t\tcolor = {{ .9 .9 .9 1.0 }}\n')
            + bo('size', f'{ind}\t\tsize = {{ {POOL_GRAPH_W} {RI_ROWS * RI_ROW_H} }}\n')
            + bo('line_plotpoints', f'{ind}\t\tvisible = "[Not(IsEmpty({t}))]"\n'
                 f'{ind}\t\tplotpoints = "[GetTrendPlotPointsNormalized({t}, GetMinPadded({t}), GetMaxPadded({t}))]"\n')
            + bo('maxvalue', f'{ind}\t\ttext = "[GetMax({t})|D]"\n')
            + bo('minvalue', f'{ind}\t\ttext = "[GetMin({t})|D]"\n')
            + bo('startdate', f'{ind}\t\ttext = "[GetOldestDate({t})]"\n')
            + bo('enddate', f'{ind}\t\ttext = "[GetLatestDate({t})]"\n')
            + bo('multiitem', '')
            + bo('empty_state_visibility', f'{ind}\t\tvisible = "[IsEmpty({t})]"\n')
            + bo('everything_that_is_not_empty_state_visibility', f'{ind}\t\tvisible = "[Not(IsEmpty({t}))]"\n')
            + bo('empty_state_text', f'{ind}\t\ttext = "GRAPH_NOT_INITIALIZED"\n')
            + f'{ind}}}\n')


def charts_row(ind):
    """Pat 14:28Z: the space split down the middle, the re-investment line on the left and the pool on the right."""
    return (f'{ind}flowcontainer = {{\n{ind}\tparentanchor = hcenter\n{ind}\tspacing = 8\n'
            + reinvest_chart(ind + '\t') + pool_chart(ind + '\t') + f'{ind}}}\n')


def contributors_chart(ind):
    """What feeds the pool, as a tree chart (Pat 13:05Z). The game has no list of the pool's sources the GUI could
    chart (1.14.5 exe: only the GetInvestmentPoolChangeFromInvestmentBreakdown text), so the tiles are the privately
    owned levels of each priority group (pmr_pc_<i>, chart_effect) and the game's list in money is the tooltip.
    The tiles come from vanilla's repeated-item datamodel; each tile finds its group by its index in it."""
    n = len(GROUPS)
    idx = 'PdxGuiWidget.GetIndexInDataModel'
    pidx = 'PdxGuiWidget.AccessParent.GetIndexInDataModel'

    def chain(fn, at, vals):
        out = vals[-1]
        for i in range(len(vals) - 2, -1, -1):
            out = f"{fn}(EqualTo_int32({at}, '(int32){i}'), {vals[i]}, {out})"
        return out
    color = chain('Select_CVector4f', idx, [f"GetDefine('NGUI','{d}')" for _g, _n, d, _c, _b in GROUPS])
    label = chain('Select_CString', pidx, [f"Localize('PMR_IPW_GROUP_{g}')" for g, *_r in GROUPS])
    value = (f"FixedPointToFloat({COUNTRY}.MakeScope.Var(Concatenate('pmr_pc_', ToString_int32({idx}))).GetValue)")
    has = f"GreaterThan_CFixedPoint({COUNTRY}.MakeScope.Var('pmr_pc_total').GetValue, '(CFixedPoint)0')"
    i1, i2, i3, i4, i5 = (ind + '\t' * k for k in range(1, 6))
    rows = ''
    for i, (g, _n, _d, (r, gg, b), _bgs) in enumerate(GROUPS):
        rows += (f'{i2}widget = {{\n{i3}size = {{ 260 28 }}\n{i3}tooltip = "PMR_PC_ROW_{i}"\n{i3}using = tooltip_above\n'
                 f'{i3}icon = {{\n{i4}parentanchor = vcenter\n{i4}size = {{ 18 18 }}\n'
                 f'{i4}texture = "gfx/interface/piechart/piechart_legend.dds"\n{i4}color = {{ {r} {gg} {b} 1 }}\n{i3}}}\n'
                 f'{i3}textbox = {{\n{i4}parentanchor = vcenter\n{i4}position = {{ 26 0 }}\n{i4}size = {{ 150 24 }}\n'
                 f'{i4}align = left|nobaseline\n{i4}elide = right\n{i4}text = "PMR_IPW_GROUP_{g}"\n{i3}}}\n'
                 f'{i3}textbox = {{\n{i4}parentanchor = right|vcenter\n{i4}autoresize = yes\n{i4}align = right|nobaseline\n'
                 f'{i4}raw_text = "#v [{COUNTRY}.MakeScope.Var(\'pmr_pc_share_{i}\').GetValue|0%]#!"\n{i3}}}\n{i2}}}\n')
    return (f'{ind}widget = {{\n{i1}parentanchor = hcenter\n{i1}size = {{ 540 214 }}\n'
            f'{i1}tooltip = "PMR_PC_TT"\n{i1}using = tooltip_above\n'
            f'{i1}textbox = {{\n{i2}visible = "[Not({has})]"\n{i2}parentanchor = center\n{i2}autoresize = yes\n'
            f'{i2}align = hcenter|nobaseline\n{i2}text = "PMR_PC_EMPTY"\n{i1}}}\n'
            # the tree chart, as vanilla's v3_treemapchart draws it
            f'{i1}container = {{\n{i2}visible = "[{has}]"\n{i2}position = {{ 40 22 }}\n'
            f'{i2}treemapchart = {{\n{i3}parentanchor = center\n{i3}size = {{ 200 170 }}\n'
            f'{i3}datamodel = "[DataModelRepeatedItem(\'(int32){n}\')]"\n'
            f'{i3}item = {{\n{i4}treemapslice = {{\n'
            f'{i5}texture = "gfx/interface/treemapchart/treemapchart.dds"\n'
            f'{i5}value = "[{value}]"\n{i5}color = "[{color}]"\n'
            f'{i5}tooltip = "PMR_PC_TT"\n'
            f'{i5}textbox = {{\n{i5}\tsize = {{ 100% 100% }}\n{i5}\talign = center|nobaseline\n{i5}\tmargin = {{ 4 4 }}\n'
            f'{i5}\tusing = fontsize_small\n{i5}\tmultiline = yes\n{i5}\telide = right\n{i5}\talwaystransparent = yes\n'
            f'{i5}\traw_text = "#bold [{label}]#!"\n{i5}}}\n'
            f'{i4}}}\n{i3}}}\n{i2}}}\n'
            f'{i2}icon = {{\n{i3}texture = "gfx/interface/treemapchart/treemapchart_frame.dds"\n{i3}parentanchor = center\n'
            f'{i3}size = {{ 124% 110% }}\n{i2}}}\n{i1}}}\n'
            # the legend
            f'{i1}flowcontainer = {{\n{i2}visible = "[{has}]"\n{i2}position = {{ 270 22 }}\n{i2}direction = vertical\n{i2}spacing = 4\n'
            f'{i2}textbox = {{\n{i3}autoresize = yes\n{i3}align = left|nobaseline\n{i3}using = fontsize_small\n'
            f'{i3}text = "PMR_PC_CAPTION"\n{i2}}}\n'
            + rows + f'{i1}}}\n{ind}}}\n')


def legend_item(ind, color, label, value, tooltip, width):
    r, g, b = color
    i1, i2 = ind + '\t', ind + '\t\t'
    return (f'{ind}widget = {{\n{i1}size = {{ {width} 22 }}\n{i1}tooltip = "{tooltip}"\n{i1}using = tooltip_above\n'
            f'{i1}icon = {{\n{i2}parentanchor = vcenter\n{i2}size = {{ 14 14 }}\n'
            f'{i2}texture = "gfx/interface/piechart/piechart_legend.dds"\n{i2}color = {{ {r} {g} {b} 1 }}\n{i1}}}\n'
            f'{i1}textbox = {{\n{i2}parentanchor = vcenter\n{i2}position = {{ 20 0 }}\n{i2}size = {{ {width - 20} 22 }}\n'
            f'{i2}align = left|nobaseline\n{i2}elide = right\n{i2}using = fontsize_small\n'
            f'{i2}raw_text = "[Localize(\'{label}\')] #v [{value}|0%]#!"\n{i1}}}\n{ind}}}\n')


def invest_bars(ind):
    """Top of Recent Investments (Pat 14:28Z): what the player's investors built since this version, as two
    stacked bars, foreign vs domestic and by priority group, each by construction points (invest_effects)."""
    var = lambda name: f"{COUNTRY}.MakeScope.Var('{name}').GetValue"
    has = f"GreaterThan_CFixedPoint({var('pmr_iv_tot')}, '(CFixedPoint)0')"
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    W, H = INVEST_BAR_W, INVEST_BAR_H

    def frame(inner, tooltip):
        return (f'{i1}widget = {{\n{i2}size = {{ {W} {H} }}\n{i2}parentanchor = hcenter\n'
                f'{i2}tooltip = "{tooltip}"\n{i2}using = tooltip_above\n'
                f'{i2}background = {{\n{i3}using = dark_area\n{i2}}}\n' + inner + f'{i1}}}\n')

    def caption(key):
        return (f'{i1}textbox = {{\n{i2}autoresize = yes\n{i2}align = left|nobaseline\n{i2}using = fontsize_small\n'
                f'{i2}text = "{key}"\n{i1}}}\n')
    home = (bar(i2, 0, 0, W, H, "FixedPointToFloat('(CFixedPoint)1')", 1, ABROAD_COLOR)
            + bar(i2, 0, 0, W, H, f"FixedPointToFloat({var('pmr_iv_dsh')})", 1, HOME_COLOR))
    groups = ''.join(bar(i2, 0, 0, W, H, f"FixedPointToFloat({var(f'pmr_iv_gc_{g}')})", 1, GROUPS[g][3])
                     for g in range(len(GROUPS) - 1, -1, -1))
    lw = W // 3
    home_legend = (f'{i1}flowcontainer = {{\n{i2}spacing = 0\n'
                   + legend_item(i2, HOME_COLOR, 'PMR_IV_HOME', var('pmr_iv_dsh'), 'PMR_IV_PLACE_TT', lw)
                   + legend_item(i2, ABROAD_COLOR, 'PMR_IV_ABROAD', var('pmr_iv_fsh'), 'PMR_IV_PLACE_TT', lw)
                   + f'{i1}}}\n')
    group_legend = ''
    for row in (GROUPS[:3], GROUPS[3:]):
        group_legend += f'{i1}flowcontainer = {{\n{i2}spacing = 0\n'
        for g, name, _d, color, _b in row:
            gi = [k for k, *_r in GROUPS].index(g)
            group_legend += legend_item(i2, color, f'PMR_IPW_GROUP_{g}', var(f'pmr_iv_gs_{gi}'), 'PMR_IV_GROUP_TT', lw)
        group_legend += f'{i1}}}\n'
    return (f'{ind}flowcontainer = {{\n{i1}parentanchor = hcenter\n{i1}direction = vertical\n{i1}spacing = 4\n'
            f'{i1}margin = {{ 0 8 }}\n'
            f'{i1}textbox = {{\n{i2}visible = "[Not({has})]"\n{i2}autoresize = yes\n{i2}multiline = yes\n'
            f'{i2}max_width = {W}\n{i2}align = nobaseline\n{i2}text = "PMR_IV_EMPTY"\n{i1}}}\n'
            f'{i1}flowcontainer = {{\n{i2}visible = "[{has}]"\n{i2}direction = vertical\n{i2}spacing = 4\n'
            + ''.join('\t' + line + '\n' for line in (caption('PMR_IV_PLACE_CAPTION') + frame(home, 'PMR_IV_PLACE_TT')
                                                     + home_legend + caption('PMR_IV_GROUP_CAPTION')
                                                     + frame(groups, 'PMR_IV_GROUP_TT') + group_legend).rstrip('\n').split('\n'))
            + f'{i1}}}\n{ind}}}\n')


def card(ind, inner, extra='', w=CARD_W, h=CARD_H):
    """A fixed card, so the law and policy cards match (Pat 04:50Z), now tall enough for the law's effects
    (Pat 13:05Z); a longer law scrolls inside it."""
    return (f'{ind}widget = {{\n{ind}\tsize = {{ {w} {h} }}\n{extra}'
            f'{ind}\tbackground = {{\n{ind}\t\tusing = entry_bg\n{ind}\t}}\n'
            + inner + f'{ind}}}\n')


def card_column(ind, inner, visible=None):
    vis = f'{ind}\tvisible = "[{visible}]"\n' if visible else ''
    return (f'{ind}flowcontainer = {{\n{vis}{ind}\tdirection = vertical\n{ind}\tmargin = {{ 10 10 }}\n{ind}\tspacing = 6\n'
            + inner + f'{ind}}}\n')


def card_title(icon, name, ind, visible=None, max_width=190):
    vis = f'{ind}\tvisible = "[{visible}]"\n' if visible else ''
    return (f'{ind}flowcontainer = {{\n{vis}{ind}\tspacing = 8\n'
            f'{ind}\ticon = {{\n{ind}\t\tsize = {{ 48 48 }}\n{ind}\t\ttexture = "{icon}"\n{ind}\t}}\n'
            f'{ind}\ttextbox = {{\n{ind}\t\tparentanchor = vcenter\n{ind}\t\tautoresize = yes\n{ind}\t\tmax_width = {max_width}\n'
            f'{ind}\t\tmultiline = yes\n{ind}\t\talign = nobaseline\n{ind}\t\tusing = fontsize_large\n'
            f'{ind}\t\ttext = "{name}"\n{ind}\t}}\n{ind}}}\n')


def card_text(key, ind, visible=None, raw=False, max_width=CARD_W - 20, small=False):
    vis = f'{ind}\tvisible = "[{visible}]"\n' if visible else ''
    font = f'{ind}\tusing = fontsize_small\n' if small else ''
    return (f'{ind}textbox = {{\n{vis}{ind}\tautoresize = yes\n{ind}\tmultiline = yes\n{ind}\tmax_width = {max_width}\n'
            f'{font}{ind}\talign = nobaseline\n{ind}\t{"raw_text" if raw else "text"} = "{key}"\n{ind}}}\n')


def scrolled_text(key, ind, w, h, raw=False):
    """Text in a fixed box that scrolls when it is longer (a law with many effects)."""
    i1, i2 = ind + '\t', ind + '\t\t'
    return (f'{ind}scrollarea = {{\n{i1}size = {{ {w} {h} }}\n{i1}scrollbarpolicy_horizontal = always_off\n'
            f'{i1}scrollbarpolicy_vertical = as_needed\n{i1}scrollbar_vertical = {{\n{i2}using = vertical_scrollbar\n{i1}}}\n'
            f'{i1}scrollwidget = {{\n' + card_text(key, i2, raw=raw, max_width=w - 18) + f'{i1}}}\n{ind}}}\n')


def open_window(ind):
    return f'{ind}onclick = "[GetVariableSystem.Set(\'{PICK}\', \'yes\')]"\n'


def policy_card(ind):
    """The policy card on the tab: a plus in the middle like vanilla's Add Principle slot (Pat 04:50Z) that opens
    the policy window (Pat 13:05Z); a held policy shows its name and benefits and a Change Policy button that opens
    the same window."""
    avail = f"GetScriptedGui('pmr_policy_available_sgui').IsShown(GuiScope.SetRoot({COUNTRY}.MakeScope).End)"
    held_any = f"GreaterThan_CFixedPoint({COUNTRY}.MakeScope.Var('pmr_policy').GetValue, '(CFixedPoint)0')"
    held = lambda i: f"EqualTo_CFixedPoint({COUNTRY}.MakeScope.Var('pmr_policy').GetValue, '(CFixedPoint){i}')"
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    inner = ''
    for i, (k, _n, icon, *_r) in enumerate(POLICIES, 1):
        inner += card_column(i1, f'{i2}tooltip = "PMR_POLICY_{k}_TT"\n' + card_title(icon, f'PMR_POLICY_{k}', i2)
                             + card_text(f'PMR_POLICY_{k}_BENEFITS', i2), held(i))
    inner += (f'{i1}button = {{\n{i2}visible = "[{held_any}]"\n{i2}using = default_button\n'
              f'{i2}size = {{ 160 32 }}\n{i2}parentanchor = bottom|hcenter\n{i2}position = {{ 0 -12 }}\n'
              f'{i2}text = "PMR_POLICY_CHANGE"\n{i2}enabled = "[{avail}]"\n' + open_window(i2) +
              f'{i2}tooltip = "PMR_POLICY_CHANGE_TT"\n{i2}using = tooltip_above\n{i1}}}\n')
    inner += (f'{i1}flowcontainer = {{\n{i2}visible = "[Not({held_any})]"\n{i2}parentanchor = center\n'
              f'{i2}direction = vertical\n{i2}spacing = 8\n'
              f'{i2}new_principle_slot = {{\n{i3}parentanchor = hcenter\n'
              f'{i3}blockoverride "onclick" {{\n{i3}\tonclick = "[GetVariableSystem.Set(\'{PICK}\', \'yes\')]"\n'
              f'{i3}\tenabled = "[{avail}]"\n{i3}}}\n'
              f'{i3}blockoverride "slot_tooltip" {{\n{i3}\ttooltip = "PMR_POLICY_ADD_TT"\n{i3}}}\n'
              f'{i3}blockoverride "slot_text" {{\n{i3}\ttext = "PMR_POLICY_ADD"\n{i3}}}\n{i2}}}\n'
              f'{i2}textbox = {{\n{i3}visible = "[Not({avail})]"\n{i3}parentanchor = hcenter\n{i3}autoresize = yes\n'
              f'{i3}multiline = yes\n{i3}max_width = 240\n{i3}align = hcenter|nobaseline\n{i3}using = fontsize_small\n'
              f'{i3}text = "PMR_POLICY_LOCKED"\n{i2}}}\n{i1}}}\n')
    return card(ind, inner)


def policy_content(k, icon, ind, w):
    """A policy's face: its icon, name and benefits only (Pat 14:28Z); click-through so its card takes the click."""
    i1, i2 = ind + '\t', ind + '\t\t'
    return (f'{ind}flowcontainer = {{\n{i1}direction = vertical\n{i1}margin = {{ 12 10 }}\n{i1}spacing = 6\n'
            f'{i1}alwaystransparent = yes\n'
            f'{i1}flowcontainer = {{\n{i2}spacing = 8\n{i2}alwaystransparent = yes\n'
            f'{i2}icon = {{\n{i2}\tsize = {{ 48 48 }}\n{i2}\ttexture = "{icon}"\n{i2}\talwaystransparent = yes\n{i2}}}\n'
            f'{i2}textbox = {{\n{i2}\tparentanchor = vcenter\n{i2}\tautoresize = yes\n{i2}\tmax_width = {w - 84}\n'
            f'{i2}\tmultiline = yes\n{i2}\talign = nobaseline\n{i2}\tusing = fontsize_large\n{i2}\talwaystransparent = yes\n'
            f'{i2}\ttext = "PMR_POLICY_{k}"\n{i2}}}\n{i1}}}\n'
            f'{i1}textbox = {{\n{i2}autoresize = yes\n{i2}multiline = yes\n{i2}max_width = {w - 24}\n{i2}align = nobaseline\n'
            f'{i2}alwaystransparent = yes\n{i2}text = "PMR_POLICY_{k}_BENEFITS"\n{i1}}}\n{ind}}}\n')


def policy_choice(k, i, icon, ind):
    """One policy in the policy window (Pat 14:28Z): a blue card, as vanilla's law options, that adopts the
    policy when clicked; the explanation is its tooltip. The policy held shows as a selected card."""
    scope = f'GuiScope.SetRoot({COUNTRY}.MakeScope).End'
    sg = f"GetScriptedGui('pmr_policy_{k}_sgui')"
    held = f"EqualTo_CFixedPoint({COUNTRY}.MakeScope.Var('pmr_policy').GetValue, '(CFixedPoint){i}')"
    i1, i2 = ind + '\t', ind + '\t\t'
    return (f'{ind}widget = {{\n{i1}size = {{ {PCARD_W} {PCARD_H} }}\n'
            f'{i1}button = {{\n{i2}visible = "[Not({held})]"\n{i2}using = default_button\n'
            f'{i2}size = {{ {PCARD_W} {PCARD_H} }}\n'
            f'{i2}enabled = "[{sg}.IsValid({scope})]"\n'
            f'{i2}onclick = "[{sg}.Execute({scope})]"\n'
            f'{i2}onclick = "[GetVariableSystem.Clear(\'{PICK}\')]"\n'
            f'{i2}tooltip = "PMR_POLICY_{k}_TT"\n'
            + policy_content(k, icon, i2, PCARD_W) + f'{i1}}}\n'
            f'{i1}widget = {{\n{i2}visible = "[{held}]"\n{i2}size = {{ 100% 100% }}\n{i2}tooltip = "PMR_POLICY_{k}_TT"\n'
            f'{i2}background = {{\n{i2}\tusing = entry_bg\n{i2}}}\n'
            f'{i2}background = {{\n{i2}\tusing = highlighted_selected_square_selection\n{i2}}}\n'
            + policy_content(k, icon, i2, PCARD_W) +
            f'{i2}textbox = {{\n{i2}\tparentanchor = bottom|right\n{i2}\tposition = {{ -12 -8 }}\n{i2}\tautoresize = yes\n'
            f'{i2}\talign = right|nobaseline\n{i2}\tusing = fontsize_small\n{i2}\ttext = "PMR_POLICY_CURRENT"\n{i2}}}\n'
            f'{i1}}}\n{ind}}}\n')


def policy_window():
    """The economic policy window (Pat 13:05Z, slimmed 14:28Z so it fits the screen): every policy as a card, two
    by two, beside the construction panel while its Private tab is open. Vanilla's popup background, header and
    frame (block_windows.gui default_popup)."""
    i1, i2, i3 = '\t\t', '\t\t\t', '\t\t\t\t'
    w, h = 2 * PCARD_W + 10 + 40, 84 + 34 + 2 * PCARD_H + 10 + 24
    rows = ''
    for r in range(0, len(POLICIES), 2):
        rows += f'{i2}flowcontainer = {{\n{i3}spacing = 10\n'
        for i, (k, _n, icon, *_x) in enumerate(POLICIES[r:r + 2], r + 1):
            rows += policy_choice(k, i, icon, i3)
        rows += f'{i2}}}\n'
    return (f'\ttype pmr_policy_window = widget {{\n'
            f'{i1}visible = "[And(InformationPanel.IsTabSelected(\'{TAB}\'), GetVariableSystem.Exists(\'{PICK}\'))]"\n'
            f'{i1}position = {{ 607 102 }}\n{i1}size = {{ {w} {h} }}\n{i1}using = clickthrough_blocker\n'
            f'{i1}background = {{\n{i2}texture = "gfx/interface/backgrounds/popup_bg.dds"\n{i2}spriteType = Corneredstretched\n'
            f'{i2}spriteborder = {{ 90 90 }}\n{i2}texture_density = 2\n'
            f'{i2}modify_texture = {{\n{i3}texture = "gfx/interface/backgrounds/default_bg_shading.dds"\n'
            f'{i3}spriteType = Corneredstretched\n{i3}spriteborder = {{ 0 0 }}\n{i3}blend_mode = overlay\n{i2}}}\n'
            f'{i2}modify_texture = {{\n{i3}using = texture_velvet\n{i2}}}\n{i1}}}\n'
            f'{i1}widget = {{\n{i2}size = {{ 100% 82 }}\n{i2}popup_top_header = {{}}\n'
            f'{i2}textbox = {{\n{i3}position = {{ 0 24 }}\n{i3}size = {{ 70% 40 }}\n{i3}parentanchor = hcenter\n'
            f'{i3}align = hcenter|nobaseline\n{i3}elide = right\n{i3}using = header_font\n{i3}using = header_font_size\n'
            f'{i3}default_format = "#header"\n{i3}text = "PMR_POLICY_WINDOW_TITLE"\n{i2}}}\n{i1}}}\n'
            f'{i1}popup_bg_frame = {{}}\n'
            f'{i1}close_button_large = {{\n{i2}parentanchor = right\n{i2}position = {{ -14 18 }}\n'
            f'{i2}onclick = "[GetVariableSystem.Clear(\'{PICK}\')]"\n{i1}}}\n'
            f'{i1}flowcontainer = {{\n{i2}position = {{ 20 84 }}\n{i2}direction = vertical\n{i2}spacing = 10\n'
            f'{i2}textbox = {{\n{i3}autoresize = yes\n{i3}multiline = yes\n{i3}max_width = {w - 40}\n'
            f'{i3}align = nobaseline\n{i3}text = "PMR_POLICY_WINDOW_INTRO"\n{i2}}}\n'
            + rows + f'{i1}}}\n\t}}\n')


def private_tab():
    i1, i2, i3 = '\t\t', '\t\t\t', '\t\t\t\t'
    filt = []
    for mode, key, tt in (('off', 'ALL', 'LOCATION_FILTER_ALL'), ('yes', 'DOMESTIC', 'LOCATION_FILTER_DOMESTIC'),
                          ('no', 'ABROAD', 'LOCATION_FILTER_ABROAD')):
        on = {'off': "Not(ConstructionPanel.IsFiltered('is_domestic'))", 'yes': "ConstructionPanel.IsFilterYes('is_domestic')",
              'no': "ConstructionPanel.IsFilterNo('is_domestic')"}[mode]
        filt.append(f'{i3}filter_button = {{\n{i3}\tvisible = "[Not({on})]"\n{i3}\tsize = {{ 132 40 }}\n'
                    f'{i3}\ttooltip = "{tt}"\n{i3}\tusing = tooltip_above\n'
                    f'{i3}\tblockoverride "text" {{\n{i3}\t\ttext = "{key}"\n{i3}\t}}\n'
                    f'{i3}\tblockoverride "onclick" {{\n{i3}\t\tonclick = "[ConstructionPanel.SetFilterMode(\'is_domestic\', \'{mode}\')]"\n{i3}\t}}\n{i3}}}\n'
                    f'{i3}filter_background_selected = {{\n{i3}\tvisible = "[{on}]"\n{i3}\tsize = {{ 132 40 }}\n'
                    f'{i3}\tblockoverride "text" {{\n{i3}\t\ttext = "{key}"\n{i3}\t}}\n{i3}}}\n')
    queue = ('Country.AccessPagedPrivateConstructionQueue(ConstructionPanel.AccessCurrentPrivateConstructionQueuePage('
             'GetMetaPlayer.GetPlayedOrObservedCountry), ConstructionPanel.GetFilter)')
    law = f"{COUNTRY}.GetActiveLawFromGroup('lawgroup_economic_system')"
    law_card = card(i2, card_column(i2 + '\t', card_title('[Law.GetTexture]', '[Law.GetNameNoFormatting]', i2 + '\t\t')
                                    + scrolled_text('[Law.GetLawType.GetEffectDesc(GetPlayer.Self)]', i2 + '\t\t',
                                                    CARD_W - 14, CARD_H - 84, raw=True)),
                    f'{i2}\tdatacontext = "[{law}]"\n')
    return (
        '@pmr_w = 554\n\n'
        'types pmr_private_investment {\n'
        + policy_window() + '\n'
        '\ttype pmr_private_tab = flowcontainer {\n'
        '\t\tusing = default_list_position\n\t\tdirection = vertical\n\t\tminimumsize = { 540 -1 }\n\t\tmargin_bottom = 10\n\n'
        # 1. the pool: the budget panel's own Investment Pool line (Pat 13:05Z), then the next private construction
        + header('PMR_PI_POOL_HEADER', i1) +
        f'{i1}widget = {{\n{i1}\tsize = {{ 540 60 }}\n{i1}\tparentanchor = hcenter\n{i1}\tbackground = {{\n{i1}\t\tusing = entry_bg\n{i1}\t}}\n'
        f'{i1}\ttextbox = {{\n{i1}\t\tusing = fontsize_large\n{i1}\t\tautoresize = yes\n{i1}\t\traw_text = "[concept_investment_pool]:"\n'
        f'{i1}\t\talign = left|nobaseline\n{i1}\t\tparentanchor = vcenter\n{i1}\t\tmargin_left = 20\n{i1}\t}}\n'
        f'{i1}\ttextbox = {{\n{i1}\t\tusing = fontsize_large\n{i1}\t\tautoresize = yes\n'
        f'{i1}\t\traw_text = "#v @money![{COUNTRY}.GetInvestmentPool|D+]#! ([{COUNTRY}.GetInvestmentPoolChange|=+D])"\n'
        f'{i1}\t\tparentanchor = right|vcenter\n{i1}\t\talign = right|nobaseline\n{i1}\t\tmargin_right = 20\n'
        f'{i1}\t\tusing = investment_pool_tooltip_with_graph\n{i1}\t}}\n{i1}}}\n'
        f'{i1}textbox = {{\n{i1}\tvisible = "[{COUNTRY}.ShowInvestmentPoolPredictedNextBuilding]"\n{i1}\tparentanchor = hcenter\n'
        f'{i1}\tminimumsize = {{ @pmr_w -1 }}\n{i1}\tmaximumsize = {{ @pmr_w -1 }}\n{i1}\tmargin = {{ 10 10 }}\n'
        f'{i1}\tautoresize = yes\n{i1}\tmultiline = yes\n{i1}\talign = hcenter|nobaseline\n{i1}\ttext = "NEXT_PRIVATE_CONSTRUCTION"\n'
        f'{i1}\tbackground = {{\n{i1}\t\tusing = dark_area\n{i1}\t}}\n{i1}}}\n'
        # 2. the weekly re-investment over time beside the pool (Pat 14:28Z), titled inside their frames like vanilla's
        + charts_row(i1) +
        # 3. contributors, as a tree chart (Pat 13:05Z)
        header('PMR_PI_SOURCES_HEADER', i1) + contributors_chart(i1) +
        # 4. economic law and policy
        header('PMR_PI_POLICY_HEADER', i1) +
        f'{i1}flowcontainer = {{\n{i1}\tparentanchor = hcenter\n{i1}\tmargin_top = 8\n{i1}\tmargin_bottom = 8\n{i1}\tspacing = 8\n'
        + law_card + policy_card(i2) + f'{i1}}}\n'
        # 5. priorities
        + header('PMR_IPW_HEADER', i1) +
        f'{i1}textbox = {{\n{i1}\tminimumsize = {{ @pmr_w -1 }}\n{i1}\tmaximumsize = {{ @pmr_w -1 }}\n{i1}\tmargin = {{ 10 6 }}\n'
        f'{i1}\tautoresize = yes\n{i1}\tmultiline = yes\n{i1}\talign = nobaseline\n{i1}\ttext = "PMR_IPW_EXPLAIN"\n{i1}}}\n'
        + ''.join(priority_row(g, i1) for g, *_r in GROUPS) +
        # 6. private construction, then recent investments
        f'{i1}default_header_2texts = {{\n{i1}\tblockoverride "text1" {{\n{i1}\t\ttext = "PMR_PI_QUEUE_HEADER"\n{i1}\t}}\n'
        f'{i1}\tblockoverride "text2" {{\n{i1}\t\ttext = "PMR_PI_QUEUE_COUNT"\n{i1}\t}}\n{i1}}}\n'
        f'{i1}flowcontainer = {{\n{i1}\tparentanchor = hcenter\n{i1}\tmargin = {{ 0 8 }}\n{i1}\tspacing = 5\n'
        + ''.join(filt) + f'{i1}}}\n'
        f'{i1}fixedgridbox = {{\n{i1}\tvisible = "[Not(IsDataModelEmpty({queue}))]"\n{i1}\taddcolumn = 540\n{i1}\taddrow = 40\n'
        f'{i1}\tparentanchor = hcenter\n{i1}\tdatamodel = "[{queue}]"\n{i1}\titem = {{\n{i1}\t\tconstruction_queue_item = {{}}\n{i1}\t}}\n{i1}}}\n'
        f'{i1}empty_state = {{\n{i1}\tblockoverride "visible" {{\n{i1}\t\tvisible = "[IsDataModelEmpty({queue})]"\n{i1}\t}}\n'
        f'{i1}\tblockoverride "text" {{\n{i1}\t\ttext = "PMR_PI_QUEUE_EMPTY"\n{i1}\t}}\n{i1}}}\n'
        + header('PMR_PI_RECENT_HEADER', i1) + invest_bars(i1) +
        f'{i1}textbox = {{\n{i1}\tminimumsize = {{ @pmr_w -1 }}\n{i1}\tmaximumsize = {{ @pmr_w -1 }}\n{i1}\tmargin = {{ 14 8 }}\n'
        f'{i1}\tautoresize = yes\n{i1}\tmultiline = yes\n{i1}\talign = nobaseline\n'
        f'{i1}\traw_text = "[{COUNTRY}.GetPreviousAutonomousInvestmentsDesc]"\n{i1}}}\n'
        '\t}\n}\n')


# ---------------------------------------------------------------------------------------------------------------
# Post-processing generate.py's own outputs
#

def top_blocks(text):
    """(key, start, open brace, close brace) of each top-level `key = {` block."""
    out = []
    for m in re.finditer(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{', text, re.M):
        if out and m.start() < out[-1][3]:  # nested key at column 0 inside a block
            continue
        o = text.index('{', m.start())
        out.append((m.group(1), m.start(), o, block_end(text, o)))
    return out


def building_groups(game):
    """building type -> building_group, and group -> parent group, from the vanilla files."""
    btype, parent = {}, {}
    bdir = os.path.join(game, 'common', 'buildings')
    for name in sorted(os.listdir(bdir)):
        t = open(os.path.join(bdir, name), encoding='utf-8-sig').read()
        for k, _s, o, c in top_blocks(t):
            g = re.search(r'\n\s*building_group\s*=\s*([a-z_]+)', t[o:c])
            if g:
                btype[k] = g.group(1)
    t = open(os.path.join(game, 'common', 'building_groups', '00_building_groups.txt'), encoding='utf-8-sig').read()
    for k, _s, o, c in top_blocks(t):
        pg = re.search(r'\n\s*parent_group\s*=\s*([a-z_]+)', t[o:c])
        if pg:
            parent[k] = pg.group(1)
    return btype, parent


def group_of(bk, btype, parent):
    """The priority group of a building type: its building group, or the nearest parent group, in GROUPS."""
    g = btype.get(bk)
    while g and g not in GROUP_OF:
        g = parent.get(g)
    return GROUP_OF.get(g)


def company_owners(game):
    """building type -> company types that list it in building_types (vanilla files)."""
    owners = {}
    cdir = os.path.join(game, 'common', 'company_types')
    for name in sorted(os.listdir(cdir)):
        t = open(os.path.join(cdir, name), encoding='utf-8-sig').read()
        for k, _s, o, c in top_blocks(t):
            bt = re.search(r'\n\s*building_types\s*=\s*\{([^}]*)\}', t[o:c])
            for bk in (bt.group(1).split() if bt else []):
                owners.setdefault(bk, []).append(k)
    return owners


def patch_retool_ai(text, btype, parent):
    """pmr_retool_buildings.txt: each private retool building's ai_value ends with multiply = pmr_reinvest_mult_<group>."""
    edits, n = [], 0
    for k, _s, o, c in top_blocks(text):
        m = re.fullmatch(r'building_pmr_retool_(.+)_(\d+)', k)
        if not m or k.startswith('building_pmr_retool_gov_'):
            continue
        g = group_of('building_' + m.group(1), btype, parent)
        if not g:
            fail('pmr_retool_buildings.txt', f'no priority group for {k}')
        a = text.find('\tai_value = {', o, c)
        if a < 0:
            fail('pmr_retool_buildings.txt', f'{k} has no ai_value block')
        close = block_end(text, text.index('{', a))
        edits.append((close, f'\t# PMR: Re-invest card, x the {g} priority\n\t\tmultiply = pmr_reinvest_mult_{g}\n\t'))
        n += 1
    if not n:
        fail('pmr_retool_buildings.txt', 'found no private retool buildings')
    for pos, ins in sorted(edits, reverse=True):
        text = text[:pos] + ins + text[pos:]
    return text, n


def patch_company_ai(text, owners):
    """A building file generate.py wrote: each building type a company lists gets ai_value = pmr_ai_value_<b>,
    whose body is the vanilla ai_value (number, block, or the 1000 default) plus CORP_BONUS while the state's
    owner holds Favour Large Corporations and has one of those companies. Returns (text, script values)."""
    values, edits = [], []
    for k, _s, o, c in top_blocks(text):
        if k not in owners:
            continue
        body = text[o + 1:c]
        name = f'pmr_ai_value_{k[len("building_"):]}'
        m = re.search(r'\n(\s*)ai_value\s*=\s*', body)
        if m and body[m.end()] == '{':
            vo = o + 1 + m.end()
            vc = block_end(text, vo)
            inner = text[vo + 1:vc].rstrip() + '\n'
            edits.append((o + 1 + m.start(), vc + 1, f'\n{m.group(1)}ai_value = {name}  # PMR: vanilla value + company card'))
        elif m:
            num = re.match(r'[-0-9.]+', body[m.end():]).group(0)
            inner = f'\tvalue = {num}\n'
            end = o + 1 + m.end() + len(num)
            edits.append((o + 1 + m.start(), end, f'\n{m.group(1)}ai_value = {name}  # PMR: vanilla {num} + company card'))
        else:
            inner = f'\tvalue = {BASE_AI_VALUE}\n'
            edits.append((c, c, f'\t# PMR: vanilla default {BASE_AI_VALUE} + company card\n\tai_value = {name}\n'))
        has = ''.join(f'\t\t\t\t\thas_company = company_type:{ct}\n' for ct in owners[k])
        values.append(f'{name} = {{\n{inner}\tif = {{\n\t\tlimit = {{\n\t\t\towner ?= {{\n'
                      f'\t\t\t\thas_modifier = pmr_policy_corporations\n\t\t\t\tOR = {{\n{has}\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n'
                      f'\t\tadd = {CORP_BONUS}\n\t}}\n}}\n')
    for a, b, ins in sorted(edits, reverse=True):
        text = text[:a] + ins + text[b:]
    return text, values


# ---------------------------------------------------------------------------------------------------------------

def localization():
    law = "[GetLawType('law_interventionism').GetName]"
    var = lambda name: f"{COUNTRY}.MakeScope.Var('{name}').GetValue"
    loc = [
        ' PMR_TAB_GOVERNMENT:0 "Government"',
        ' PMR_TAB_GOVERNMENT_TT:0 "The construction sector and the government construction queue"',
        ' PMR_TAB_PRIVATE:0 "Private"',
        ' PMR_TAB_PRIVATE_TT:0 "The investment pool, economic policy, investment priorities and private construction"',
        ' PMR_PI_POOL_HEADER:0 "Investment Pool"',
        ' PMR_RW_CHART_HEADER:0 "Weekly Re-investment"',
        ' PMR_RW_EMPTY:0 "Recorded every week from the day you open this tab"',
        f' PMR_RW_AXIS_START:0 "{RI_WEEKS - 1} weeks ago"',
        ' PMR_RW_AXIS_END:0 "This week"',
        ' PMR_PI_POLICY_HEADER:0 "Economic Policy"',
        ' PMR_PI_SOURCES_HEADER:0 "Buildings Adding to the Pool"',
        ' PMR_PC_CAPTION:0 "Privately owned building levels"',
        ' PMR_PC_EMPTY:0 "Counted when you open this tab and every week"',
        ' PMR_PC_TT:0 "#header Buildings Adding to the Pool#!\\nThe chart shows the privately owned building levels in each '
        'investment priority group, the capital whose profits feed the pool. The game reports what each building type adds '
        'only as this list:\\n$TOOLTIP_DELIMITER$\\n[GetPlayer.GetInvestmentPoolChangeFromInvestmentBreakdown]"',
        ' PMR_PI_QUEUE_HEADER:0 "Private Construction"',
        ' PMR_PI_QUEUE_COUNT:0 ""',
        ' PMR_PI_QUEUE_EMPTY:0 "No private construction is queued"',
        ' PMR_PI_RECENT_HEADER:0 "Recent Investments and Privatizations"',
        ' PMR_IV_EMPTY:0 "What your investors build is counted here from now on, at home and abroad, by construction '
        'points."',
        ' PMR_IV_PLACE_CAPTION:0 "Where your investors built"',
        ' PMR_IV_GROUP_CAPTION:0 "What they built, by construction points"',
        ' PMR_IV_HOME:0 "Domestic"',
        ' PMR_IV_ABROAD:0 "Foreign"',
        f' PMR_IV_PLACE_TT:0 "#header Where Your Investors Built#!\\nConstruction points of the building levels your '
        f'investors completed since this version of the mod was loaded: #v [{var("pmr_iv_dom")}|0]#! at home, '
        f'#v [{var("pmr_iv_for")}|0]#! abroad. Retooling and government construction are not counted."',
        ' PMR_IV_GROUP_TT:0 "#header What Your Investors Built#!\\nConstruction points of the building levels your '
        'investors completed since this version of the mod was loaded, by investment priority group:\\n'
        + '\\n'.join(f'{name}: #v [{var(f"pmr_iv_pts_{i}")}|0]#! (#v [{var(f"pmr_iv_gs_{i}")}|0%]#!)'
                     for i, (_g, name, *_r) in enumerate(GROUPS))
        + '\\nRetooling and government construction are not counted."',
        ' PMR_POLICY_ADD:0 "Add Policy"',
        f' PMR_POLICY_ADD_TT:0 "Choose an economic policy. One can be held at a time, and it lapses if {law} is repealed."',
        f' PMR_POLICY_LOCKED:0 "Requires {law}"',
        ' PMR_POLICY_CHANGE:0 "Change Policy"',
        ' PMR_POLICY_CHANGE_TT:0 "See every policy and swap this one for another. Only one can be held at a time."',
        ' PMR_POLICY_WINDOW_TITLE:0 "Economic Policies"',
        f' PMR_POLICY_WINDOW_INTRO:0 "Click a policy to adopt it. One at a time, while {law} lasts."',
        ' PMR_POLICY_CURRENT:0 "#v Current Policy#!"',
        ' PMR_IPW_HEADER:0 "Investment Priorities"',
        ' PMR_IPW_EXPLAIN:0 "Raise how much your investors favour a group over the others: a full priority adds '
        '#v +[FixedPointToInt(Multiply_CFixedPoint(GetPlayer.MakeScope.ScriptValue(\'pmr_ipw_cap\'), \'(CFixedPoint)100\'))]%#! '
        '(+75% under Steer the Economy). '
        'Raising every group by the same amount changes nothing. A group your investors already weigh at the 25% '
        'minimum cannot drop further, so a boost gains nothing against it."',
    ]
    for k, name, _i, mods, core, core_tt, details in POLICIES:
        how = f'{core_tt}\\n' if core_tt else ''
        loc += [f' pmr_policy_{k}:0 "{name}"', f' PMR_POLICY_{k}:0 "{name}"',
                f' PMR_POLICY_{k}_BENEFITS:0 "{benefit_lines(core, mods)}"',
                f' PMR_POLICY_{k}_TT:0 "#header {name}#!\\n{how}$TOOLTIP_DELIMITER$\\n#italic {details}#!"']
    for s in STEPS:
        loc.append(f' PMR_IPW_NOTCH_{s}:0 "' + ('No priority' if s == 0 else
                   f'{s}% of the cap: #P +[FixedPointToInt(Multiply_CFixedPoint({COUNTRY}.MakeScope.ScriptValue(\'pmr_ipw_cap\'), \'(CFixedPoint){s}\'))]%#!') + '"')
    for i in range(RI_WEEKS):
        when = 'This week' if i == 0 else ('1 week ago' if i == 1 else f'{i} weeks ago')
        loc.append(f' PMR_RW_COLUMN_{i}:0 "{when}: #v @money![{var(f"pmr_rw_{i}")}|D]#! re-invested\\n'
                   'The column under the line splits it by the privately owned levels of each priority group that week, '
                   'as the tree chart below."')
    for i, (g, name, _d, _c, bgs) in enumerate(GROUPS):
        v = VAR.format(g)
        covers = ', '.join(f'${bg}$' for bg in bgs)
        loc.append(f' PMR_IPW_GROUP_{g}:0 "{name}"')
        loc.append(f' PMR_IPW_ROW_{g}:0 "#header {name}#!\\nCovers {covers}.\\nYour investors weigh these at '
                   f'#v ×[{COUNTRY}.MakeScope.ScriptValue(\'{v}\')|2]#! their usual weight. Only the differences between '
                   'priorities matter: the highest priority\'s group stays at ×1.00."')
        loc.append(f' PMR_PC_ROW_{i}:0 "#header {name}#!\\n#v [{var(f"pmr_pc_{i}")}|0]#! privately '
                   f'owned building levels, #v [{var(f"pmr_pc_share_{i}")}|0%]#! of the five groups. '
                   f'Covers {covers}."')
    return loc


def write_all(game, write, header_text, out=None):
    """Writes every file this feature owns, then patches generate.py's building outputs under out (skipped when
    out is None, as in the standalone run). Returns loc lines."""
    def vanilla(rel):
        return open(os.path.join(game, rel), encoding='utf-8-sig').read()
    buildings, _groups = patch_scores(vanilla(SOURCE_FILE))
    write(SOURCE_FILE, buildings)
    values = script_values()
    write('common/scripted_guis/pmr_ipw_sguis.txt', header_text + sguis())
    write('common/static_modifiers/pmr_policy_modifiers.txt', header_text + static_modifiers())
    write('common/on_actions/pmr_pi_on_actions.txt', header_text + on_actions())
    write('common/scripted_effects/pmr_pi_effects.txt', header_text + reinvest_effect() + '\n' + chart_effect() + '\n'
          + clock_effect() + '\n' + invest_effects(invest_types(game)))
    write('events/pmr_pi_events.txt', header_text + events())
    write(QUEUE_GUI, patch_queue(vanilla(QUEUE_GUI)), bom=False)
    write(PANEL_GUI, patch_panel(vanilla(PANEL_GUI)), bom=False)
    write(OWN_GUI, '# GENERATED by tools/pmr/private_investment.py\n' + private_tab(), bom=False)
    if out:
        btype, parent = building_groups(game)
        rpath = os.path.join(out, 'common', 'buildings', 'pmr_retool_buildings.txt')
        text, n = patch_retool_ai(open(rpath, encoding='utf-8-sig').read(), btype, parent)
        write('common/buildings/pmr_retool_buildings.txt', text)
        owners = company_owners(game)
        corp, patched = [], []
        bdir = os.path.join(out, 'common', 'buildings')
        for name in sorted(os.listdir(bdir)):
            if name.startswith('pmr_') or name == os.path.basename(SOURCE_FILE):
                continue
            text, vals = patch_company_ai(open(os.path.join(bdir, name), encoding='utf-8-sig').read(), owners)
            if vals:
                write(f'common/buildings/{name}', text)
                corp += vals
                patched.append(name)
        if not corp:
            fail('common/buildings', 'no company building types found in the generated building files')
        values += ('# State scope. Favour Large Corporations: the vanilla ai_value of each company building type in\n'
                   f'# {", ".join(patched)}, plus {CORP_BONUS} while the owner holds the card and has a company listing it.\n'
                   + '\n'.join(corp))
        print(f'private investment: {n} private retool buildings take Re-invest; {len(corp)} company building types '
              f'take Favour Large Corporations')
    write('common/script_values/pmr_ipw_values.txt', header_text + values)
    return localization()


if __name__ == '__main__':
    import sys
    game, out = sys.argv[1], sys.argv[2]

    def _write(rel, text, bom=True):
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if bom and not text.startswith('﻿'):
            text = '﻿' + text
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    lines = write_all(game, _write, '# GENERATED by tools/pmr/private_investment.py. Do not edit by hand.\n\n')
    _write('localization/english/pmr_pi_l_english.yml', 'l_english:\n' + '\n'.join(lines) + '\n')
