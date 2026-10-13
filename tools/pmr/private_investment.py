"""The construction panel's Private tab: investment pool, economic policy and investment priorities.

Pat, 2026-10-13 03:52Z and 04:03Z. The construction panel gets a Private tab beside the government one, and the
funding-type filter goes. The Government tab keeps the construction sector and the government queue and loses the
investment pool. The Private tab, top to bottom:
  1. the weekly re-investment into the pool (Pat 04:13Z: not the pool amount), previous investments, next private
     construction
  2. the weekly re-investment, as monthly columns (Pat 04:13Z: the weekly inflow, not the pool amount; the game keeps
     no history of it, so PMR samples investment_pool_income monthly into country variables)
  3. what feeds the pool: the game's own breakdown text (Pat 04:12Z chose it over estimated charts; the game has
     no per-group numbers, and GUI pie charts only take engine lists)
  4. the economic system law as a card, and to its right a policy card, chosen under Interventionism only
  5. investment priority sliders, one per building group, 0..+100%
  6. the private construction queue with the vanilla location filter, then recent investments and privatizations

Sliders (Pat 04:16Z). Each building group's slider runs 0..100% of a cap: the cap is +50% weight, or +75% while the
Steer the Economy card is held. The pool weighs each building group by the `investment_scores` of the ownership
buildings funding it (Manor Houses, Financial Districts), clamped 0.25..1.0 (00_ai.txt:942-950). Those scores are
country-scope script values (vanilla reads has_law_or_variant and country modifiers in them), so a country variable
can feed them. Every score is multiplied by (100 + boost) / (100 + highest boost): a plain x1.5 would hit the 1.0
ceiling, and raising the ceiling changes vanilla (Manor Houses score farms 2.0 under Agrarianism). So AI countries and
untouched sliders are exactly vanilla, equal sliders cancel, and a boost gains nothing against groups already at the
0.25 floor. Manufacturing is split into Light, Heavy and Military Industry by adding those child groups to both
investment_scores with Manufacturing's score: vanilla already lists child groups there (bg_mining, bg_logging under
bg_extraction; bg_arts; bg_trade), so a building is inferred to take its nearest listed group. Inferred, not traced in
the exe: that lookup, and that the weight is the pool-share-weighted sum of the scores.

The GUI cannot write a number into script, so a slider is a row of notches; each notch runs the group's scripted GUI
with the step as a saved value scope (MakeScopeValue, as vanilla's ep2_japan_widgets.gui does).

Policy cards (Pat: only under Interventionism). One at a time, as a static modifier; a monthly country pulse drops it
when the law is no longer Interventionism.
  - Steer the Economy (Pat 04:16Z): the sliders' cap goes from +50% to +75%.
  - Favour Large Corporations (Pat 04:15Z): the pool weighs building types your companies list higher. There is no
    modifier or per-country define for company weighting, so each company building type in PMR's building files gets
    ai_value = pmr_ai_value_<b>: its vanilla ai_value plus CORP_BONUS while the card is held.
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
PIP_COLOR = (0.74, 0.60, 0.30)     # ochre, from TIER_COLORS: muted, never red or green
VAR = 'pmr_ipw_{}'                 # country variable per group, 0..100
ON = 'pmr_ipw_on'                  # set once the player touches any slider
TAB = 'pmr_private'                # InformationPanel tab id of the Private tab
SOURCE_FILE = 'common/buildings/11_private_infrastructure.txt'
QUEUE_GUI = 'gui/construction_queue.gui'
PANEL_GUI = 'gui/construction_panel.gui'
OWN_GUI = 'gui/pmr_private_investment.gui'
COUNTRY = 'GetPlayer'

CAP = 0.5                  # slider at 100% = +50% weight (Pat 04:16Z)
CAP_STEER = 0.75           # +75% under Steer the Economy
SPLIT = {'bg_manufacturing': ('bg_light_industry', 'bg_heavy_industry', 'bg_military_industry')}
REINVEST_PER_POINT = 0.99  # Re-invest: retool ai_value x (1 + this x slider%): x100 at 100%
CORP_BONUS = 75000         # Favour Large Corporations: ai_value added, = GBP 10/worker of vanilla's profit term
BASE_AI_VALUE = 1000       # PRODUCTION_BUILDING_BASE_VALUE, when a building has no ai_value

# key, short label, full name, icon, modifiers, effect line for the card
POLICIES = [
    ('steer', 'Steer', 'Steer the Economy', 'gfx/interface/icons/law_icons/command_economy.dds', {},
     f'Investment priority sliders reach #v +{CAP_STEER * 100:.0f}%#! weight instead of #v +{CAP * 100:.0f}%#!.'),
    ('corporations', 'Corporations', 'Favour Large Corporations', 'gfx/interface/icons/law_icons/laissez_faire.dds', {},
     'Investors weigh building types your companies own much higher, as if each earned #v @money!10#! more per worker.'),
    ('reinvest', 'Re-invest', 'Re-invest', 'gfx/interface/icons/law_icons/interventionism.dds', {},
     'Investors favour retooling a building by its group\'s investment priority: up to #v 100×#! at a full slider.'),
    ('small', 'Small Business', 'Favour Small Businesses', 'gfx/interface/icons/law_icons/cooperative_ownership.dds',
     {'state_shopkeepers_investment_pool_efficiency_mult': 0.15, 'building_self_investment_chance_add': 0.1},
     'Shopkeepers put more into the investment pool, and new building levels are likelier to be owned by the building itself.'),
]
POLICY_LAW = 'law_interventionism'
RI_MONTHS = 24             # re-investment chart: one point per month, newest on the right
RI_ROWS, RI_ROW_H, RI_COL_W = 20, 6, 19   # the line is drawn on a 20-row grid, 6 px a row, 19 px a month
LINE_COLOR = (0.9, 0.9, 0.9)              # vanilla's trend line colour (v3_plotline_gdp)
CARD_W, CARD_H = 268, 260                 # law and policy cards, the same size (Pat 04:50Z)
MOD_NAMES = {  # how each modifier reads on a policy card
    'country_private_construction_allocation_mult': ('Private construction allocation', True),
    'country_government_dividends_reinvestment_add': ('Government dividends reinvested', True),
    'country_max_companies_add': ('Company slots', False),
    'country_company_throughput_bonus_add': ('Company throughput bonus', True),
    'state_capitalists_investment_pool_efficiency_mult': ('Capitalists\' investment efficiency', True),
    'state_aristocrats_investment_pool_efficiency_mult': ('Aristocrats\' investment efficiency', True),
    'state_shopkeepers_investment_pool_efficiency_mult': ('Shopkeepers\' investment efficiency', True),
    'building_self_investment_chance_add': ('Self-investment chance', True),
}


def mod_lines(mods):
    if not mods:
        return ''
    out = []
    for m, v in mods.items():
        name, pct = MOD_NAMES[m]
        val = f'{v * 100:+.0f}%' if pct else f'{v:+g}'
        out.append(f'{name}: #v {val}#!')
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
    """Vanilla 11_private_infrastructure.txt with `multiply = pmr_ipw_<group>` as the last line of every
    investment_scores score, and Manufacturing's score copied to its SPLIT children. Returns (text, every group
    scored, the groups that get a slider)."""
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
            edits.append((score_close, f'\n{indent}\t\t# PMR: investment priorities slider\n{indent}\t\tmultiply = {VAR.format(g)}\n{indent}\t', True))
            groups.extend(c for c in SPLIT.get(g, ()) if c not in groups)
            for child in reversed(SPLIT.get(g, ())):
                entry = text[m.end() + e.start() + 1 + len(indent):entry_close + 1]
                entry = entry.replace(f'{g}_score', f'{child}_score', 1).replace(f'"{g}"', f'"{child}"', 1)
                sc_open = re.search(r'\n\s*score\s*=\s*\{', entry).end() - 1
                sc_close = block_end(entry, sc_open)
                k = sc_close
                while entry[k - 1] in ' \t\n':
                    k -= 1
                entry = (entry[:k] + f'\n{indent}\t\t# PMR: investment priorities slider\n{indent}\t\tmultiply = {VAR.format(child)}\n{indent}\t'
                         + entry[sc_close:])
                edits.append((entry_close + 1, f'\n{indent}# PMR: {child} scored as {g}, with its own slider\n{indent}{entry}', False))
    if filled != 2 or len(edits) < 20:
        fail(SOURCE_FILE, f'expected the Manor House and Financial District investment_scores, found {filled} '
                          f'filled blocks with {len(edits)} scores')
    for pos, ins, trim in sorted(edits, key=lambda t: t[0], reverse=True):
        start = pos
        if trim:
            while text[start - 1] in ' \t\n':
                start -= 1
        text = text[:start] + ins + text[pos:]
    sliders = [g for g in groups if g not in SPLIT]
    return text, groups, sliders


def script_values(groups, sliders):
    top = ''.join(f'\tif = {{\n\t\tlimit = {{ has_variable = {VAR.format(g)} }}\n\t\tmin = var:{VAR.format(g)}\n\t}}\n'
                  for g in sliders)
    out = ('# Country scope. The pool\'s weekly income right now (country value investment_pool_income).\n'
           'pmr_ri_now = {\n\tvalue = investment_pool_income\n}\n\n')
    out += ('# Country scope. What a full slider adds to a group\'s weight: +50%, or +75% under Steer the Economy.\n'
            f'pmr_ipw_cap = {{\n\tvalue = {CAP}\n\tif = {{\n\t\tlimit = {{ has_modifier = pmr_policy_steer }}\n\t\tvalue = {CAP_STEER}\n\t}}\n}}\n\n'
            '# Country scope. The highest slider position, 0..100 (min = X keeps the value at least X).\n'
            f'pmr_ipw_top = {{\n\tvalue = 0\n{top}}}\n\n'
            '# Country scope, read by the investment_scores of Manor Houses and Financial Districts:\n'
            '# (100 + slider x cap) / (100 + highest slider x cap). Exactly 1 for AI countries and for a player who\n'
            '# never touched the sliders. Groups without a slider (Manufacturing itself, now only retooling) count as 0.\n')
    for g in groups:
        v = VAR.format(g)
        out += (f'{v} = {{\n\tvalue = 1\n\tif = {{\n\t\tlimit = {{ has_variable = {ON} }}\n\t\tvalue = 0\n'
                f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = {v} }}\n\t\t\tvalue = var:{v}\n\t\t}}\n'
                '\t\tmultiply = pmr_ipw_cap\n\t\tadd = 100\n'
                '\t\tdivide = {\n\t\t\tvalue = pmr_ipw_top\n\t\t\tmultiply = pmr_ipw_cap\n\t\t\tadd = 100\n\t\t}\n\t}\n}\n\n')
    out += '# Country scope. The weight a slider adds now, in percent, for the panel.\n'
    for g in sliders:
        v = VAR.format(g)
        out += (f'{v}_pct = {{\n\tvalue = 0\n\tif = {{\n\t\tlimit = {{ has_variable = {v} }}\n\t\tvalue = var:{v}\n'
                '\t\tmultiply = pmr_ipw_cap\n\t}\n}\n\n')
    out += ('# State scope, multiplied into private retool buildings\' ai_value (pmr_retool_buildings.txt): while the\n'
            f'# owner holds Re-invest, 1 + {REINVEST_PER_POINT} x the slider of the retooled building\'s group (x100 at 100%).\n')
    for g in sliders:
        v = VAR.format(g)
        out += (f'pmr_reinvest_mult_{g} = {{\n\tvalue = 1\n\tif = {{\n\t\tlimit = {{\n\t\t\towner ?= {{\n'
                f'\t\t\t\thas_modifier = pmr_policy_reinvest\n\t\t\t\thas_variable = {v}\n\t\t\t}}\n\t\t}}\n'
                f'\t\tvalue = owner.var:{v}\n\t\tmultiply = {REINVEST_PER_POINT}\n\t\tadd = 1\n\t}}\n}}\n\n')
    return out


def sguis(sliders):
    out = ('# Investment priorities. Country scope; scope:step is the notch clicked (0, 10 .. 100), passed from\n'
           f'# {OWN_GUI} with MakeScopeValue.\n\n')
    for g in sliders:
        v = VAR.format(g)
        steps = '\t\telse_'.join(
            f'if = {{\n\t\t\tlimit = {{ scope:step = {s} }}\n\t\t\tset_variable = {{ name = {v} value = {s} }}\n\t\t}}\n'
            for s in STEPS)
        out += (f'{v}_sgui = {{\n\tscope = country\n\tsaved_scopes = {{ step }}\n'
                f'\teffect = {{\n\t\tset_variable = {ON}\n\t\t{steps}\t}}\n}}\n\n')
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
    for k, _s, _n, icon, mods, _e in POLICIES:
        out += f'pmr_policy_{k} = {{\n\ticon = "{icon}"\n' + ''.join(f'\t{m} = {v}\n' for m, v in mods.items()) + '}\n\n'
    return out


def reinvest_effect():
    """Country scope, monthly, players only. The game keeps no history of the pool's weekly income (the budget's
    Investment Pool Transfer trend is money drawn out for construction), so PMR samples investment_pool_income
    (a country value; its description string is in the 1.14.5 exe) once a month into pmr_ri_0 (newest) ..
    pmr_ri_<N-1>. For the trend line (Pat 04:50Z: like the GDP graph; GUI plot lines only take the engine's own
    trends) each month gets its row on a RI_ROWS grid between the lowest and highest month shown (pmr_ri_b_<i>,
    1 = bottom), and each pair of neighbouring months the rows the line climbs between them (pmr_ri_lo_<i>,
    pmr_ri_hi_<i>, joining month i to month i + 1)."""
    n, top_row = RI_MONTHS, RI_ROWS - 1
    shift = ''.join(f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_ri_{i - 1} }}\n'
                    f'\t\t\tset_variable = {{ name = pmr_ri_{i} value = var:pmr_ri_{i - 1} }}\n\t\t}}\n'
                    for i in range(n - 1, 0, -1))

    def fold(op):
        return ''.join(f'\t\t\t\tif = {{\n\t\t\t\t\tlimit = {{ has_variable = pmr_ri_{i} }}\n\t\t\t\t\t{op} = var:pmr_ri_{i}\n\t\t\t\t}}\n'
                       for i in range(1, n))
    rows = ''.join(
        f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_ri_{i} }}\n'
        f'\t\t\tset_variable = {{\n\t\t\t\tname = pmr_ri_b_{i}\n\t\t\t\tvalue = {{\n'
        f'\t\t\t\t\tvalue = {RI_ROWS // 2}\n'
        f'\t\t\t\t\tif = {{\n\t\t\t\t\t\tlimit = {{ var:pmr_ri_span > 0 }}\n'
        f'\t\t\t\t\t\tvalue = var:pmr_ri_{i}\n\t\t\t\t\t\tsubtract = var:pmr_ri_min\n\t\t\t\t\t\tdivide = var:pmr_ri_span\n'
        f'\t\t\t\t\t\tmultiply = {top_row}\n\t\t\t\t\t\tround = yes\n\t\t\t\t\t\tadd = 1\n\t\t\t\t\t}}\n'
        f'\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n'
        for i in range(n))
    joins = ''.join(
        f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_ri_{i + 1} }}\n'
        f'\t\t\tset_variable = {{\n\t\t\t\tname = pmr_ri_lo_{i}\n\t\t\t\tvalue = {{\n\t\t\t\t\tvalue = var:pmr_ri_b_{i}\n'
        f'\t\t\t\t\tmax = var:pmr_ri_b_{i + 1}\n\t\t\t\t}}\n\t\t\t}}\n'
        f'\t\t\tset_variable = {{\n\t\t\t\tname = pmr_ri_hi_{i}\n\t\t\t\tvalue = {{\n\t\t\t\t\tvalue = var:pmr_ri_b_{i}\n'
        f'\t\t\t\t\tmin = var:pmr_ri_b_{i + 1}\n\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n'
        for i in range(n - 1))
    return ('pmr_ri_record = {\n'
            + shift +
            '\t\tset_variable = {\n\t\t\tname = pmr_ri_0\n\t\t\tvalue = {\n\t\t\t\tvalue = investment_pool_income\n\t\t\t\tmin = 0\n\t\t\t}\n\t\t}\n'
            '\t\t# highest and lowest month shown (min = X keeps a value at least X, max = X at most X)\n'
            '\t\tset_variable = {\n\t\t\tname = pmr_ri_max\n\t\t\tvalue = {\n\t\t\t\tvalue = var:pmr_ri_0\n' + fold('min') + '\t\t\t}\n\t\t}\n'
            '\t\tset_variable = {\n\t\t\tname = pmr_ri_min\n\t\t\tvalue = {\n\t\t\t\tvalue = var:pmr_ri_0\n' + fold('max') + '\t\t\t}\n\t\t}\n'
            '\t\tset_variable = {\n\t\t\tname = pmr_ri_span\n\t\t\tvalue = {\n\t\t\t\tvalue = var:pmr_ri_max\n\t\t\t\tsubtract = var:pmr_ri_min\n\t\t\t}\n\t\t}\n'
            + rows + joins +
            '\t\tdebug_log = "PMR;rec=REINVEST;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
            'weekly=[THIS.Var(\'pmr_ri_0\').GetValue|0];min=[THIS.Var(\'pmr_ri_min\').GetValue|0];max=[THIS.Var(\'pmr_ri_max\').GetValue|0];'
            'row=[THIS.Var(\'pmr_ri_b_0\').GetValue|0]"\n'
            '}\n')


def on_actions():
    drop = ''.join(f'\t\t\tif = {{\n\t\t\t\tlimit = {{ has_modifier = pmr_policy_{k} }}\n'
                   f'\t\t\t\tremove_modifier = pmr_policy_{k}\n\t\t\t}}\n' for k, *_r in POLICIES)
    return ('# Appended to vanilla on_actions the documented way, like pmr_on_actions.txt.\n'
            'on_monthly_pulse_country = { on_actions = { pmr_pi_monthly_country } }\n\n'
            '# A policy card lasts only while the country keeps Interventionism.\n'
            'pmr_pi_monthly_country = {\n\teffect = {\n\t\tif = {\n'
            f'\t\t\tlimit = {{\n\t\t\t\thas_variable = pmr_policy\n\t\t\t\tNOT = {{ has_law_or_variant = law_type:{POLICY_LAW} }}\n\t\t\t}}\n'
            + drop +
            '\t\t\tremove_variable = pmr_policy\n'
            '\t\t\tdebug_log = "PMR;rec=POLICY;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];policy=dropped"\n'
            '\t\t}\n'
            '\t\tif = {\n\t\t\tlimit = { is_player = yes }\n\t\t\tpmr_ri_record = yes\n\t\t}\n'
            '\t}\n}\n')


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
        f'\t\t\t\tblockoverride "second_button_click" {{\n\t\t\t\t\tonclick = "[InformationPanel.SelectTab(\'{TAB}\')]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "second_button_visibility" {{\n\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'{TAB}\')]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "second_button_visibility_checked" {{\n\t\t\t\t\tvisible = "[Not( InformationPanel.IsTabSelected(\'{TAB}\') )]"\n\t\t\t\t}}\n'
        '\t\t\t\tblockoverride "second_button_selected" {\n\t\t\t\t\ttext = "PMR_TAB_PRIVATE"\n\t\t\t\t}\n\n')
    tabs = once(tabs, '\t\t\t\tblockoverride "third_button"\n', private + '\t\t\t\tblockoverride "third_button"\n', where)
    text = text[:start] + tabs + text[end + 1:]

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
    """One building group's investment priority, on the budget page's own five-coin selector (Pat 04:50Z):
    vanilla's tax_exp_frame_coin with its coins, sounds and selected frame, each coin one of STEPS."""
    v = VAR.format(g)
    cur = f"{COUNTRY}.MakeScope.Var('{v}').GetValue"

    def execute(s):
        return (f"GetScriptedGui('{v}_sgui').Execute(GuiScope.SetRoot({COUNTRY}.MakeScope)"
                f".AddScope('step', MakeScopeValue('(CFixedPoint){s}')).End)")

    def selected(k):
        # the nearest coin, so a value set on the earlier ten-notch slider still shows a coin
        lo = (STEPS[k - 1] + STEPS[k]) // 2 if k else None
        hi = (STEPS[k] + STEPS[k + 1]) // 2 if k + 1 < len(STEPS) else None
        tests = ([f"GreaterThanOrEqualTo_CFixedPoint({cur}, '(CFixedPoint){lo}')"] if lo is not None else []) + \
                ([f"LessThan_CFixedPoint({cur}, '(CFixedPoint){hi}')"] if hi is not None else [])
        return tests[0] if len(tests) == 1 else f'And({tests[0]}, {tests[1]})'

    out = (f'{ind}# {g}\n{ind}tax_exp_frame_coin = {{\n{ind}\tparentanchor = hcenter\n'
           f'{ind}\tblockoverride "tutorial_highilight_name" {{}}\n'
           f'{ind}\tblockoverride "text_upper" {{\n{ind}\t\ttext = "{g}"\n{ind}\t}}\n'
           f'{ind}\tblockoverride "second_line" {{}}\n'
           f'{ind}\tblockoverride "text_money" {{\n'
           f'{ind}\t\traw_text = "#v +[{COUNTRY}.MakeScope.ScriptValue(\'{v}_pct\')|0]%#! weight"\n'
           f'{ind}\t\ttooltip = "PMR_IPW_ROW_{g}"\n{ind}\t}}\n')
    for k, s in enumerate(STEPS):
        n = k + 1
        out += (f'{ind}\tblockoverride "button_{n}_click" {{\n{ind}\t\tonclick = "[{execute(s)}]"\n{ind}\t}}\n'
                f'{ind}\tblockoverride "tooltip_{n}" {{\n{ind}\t\ttooltip = "PMR_IPW_NOTCH_{s}"\n{ind}\t}}\n'
                f'{ind}\tblockoverride "is_selected_visibility_{n}" {{\n{ind}\t\tvisible = "[{selected(k)}]"\n{ind}\t}}\n')
    return out + f'{ind}}}\n'


def reinvest_chart(ind):
    """The weekly re-investment as a trend line in vanilla's graph frame (v3_plotline, as the GDP graph; Pat
    04:50Z). GUI plot lines only take the engine's own trends, so the line is drawn from cells: for each month
    (pmr_ri_<i>, 0 = newest, rightmost) a flat segment on its row (pmr_ri_b_<i>), and at the month's left edge
    a riser through the rows between it and the month before (pmr_ri_lo_<i> .. pmr_ri_hi_<i>)."""
    var = lambda name: f"{COUNTRY}.MakeScope.Var('{name}').GetValue"
    fp = lambda x: f"'(CFixedPoint){x}'"
    w, h = RI_MONTHS * RI_COL_W, RI_ROWS * RI_ROW_H
    mid = lambda row: h - row * RI_ROW_H + RI_ROW_H // 2   # centre of a row, 1 = bottom
    r, g, b = LINE_COLOR
    i2, i3 = ind + '\t\t', ind + '\t\t\t'

    def cell(vis, x, y, cw, ch):
        return (f'{i2}icon = {{\n{i3}visible = "[{vis}]"\n{i3}position = {{ {x} {y} }}\n{i3}size = {{ {cw} {ch} }}\n'
                f'{i3}texture = "gfx/interface/colors/white.dds"\n{i3}color = {{ {r} {g} {b} 1 }}\n{i3}alwaystransparent = yes\n{i2}}}\n')
    cells, hover = '', ''
    for c in range(RI_MONTHS):
        i = RI_MONTHS - 1 - c
        for row in range(1, RI_ROWS + 1):
            cells += cell(f"EqualTo_CFixedPoint({var(f'pmr_ri_b_{i}')}, {fp(row)})", c * RI_COL_W, mid(row) - 1, RI_COL_W, 3)
        if c:
            for row in range(1, RI_ROWS):
                cells += cell(f"And(LessThanOrEqualTo_CFixedPoint({var(f'pmr_ri_lo_{i}')}, {fp(row)}), "
                              f"GreaterThan_CFixedPoint({var(f'pmr_ri_hi_{i}')}, {fp(row)}))",
                              c * RI_COL_W - 1, mid(row + 1) - 1, 3, RI_ROW_H + 2)
        hover += (f'{i2}widget = {{\n{i3}visible = "[GreaterThan_CFixedPoint({var(f"pmr_ri_b_{i}")}, {fp(0)})]"\n'
                  f'{i3}position = {{ {c * RI_COL_W} 0 }}\n{i3}size = {{ {RI_COL_W} {h} }}\n'
                  f'{i3}tooltip = "PMR_RI_COLUMN_{i}"\n{i3}using = tooltip_above\n{i2}}}\n')
    has = f"GreaterThan_CFixedPoint({var('pmr_ri_b_0')}, {fp(0)})"
    bo = lambda name, body: f'{ind}\tblockoverride "{name}" {{\n{body}{ind}\t}}\n'
    return (f'{ind}v3_plotline = {{\n{ind}\tparentanchor = hcenter\n'
            + bo('header', f'{ind}\t\ttext = "PMR_RI_CHART_HEADER"\n')
            + bo('size', f'{ind}\t\tsize = {{ {w} {h} }}\n')
            + bo('singleitem', '') + bo('multiitem', '')
            + bo('extra_plotlines', cells + hover)
            + bo('maxvalue', f'{ind}\t\traw_text = "@money![{var("pmr_ri_max")}|K]"\n')
            + bo('minvalue', f'{ind}\t\traw_text = "@money![{var("pmr_ri_min")}|K]"\n')
            + bo('startdate', f'{ind}\t\ttext = "PMR_RI_AXIS_START"\n')
            + bo('enddate', f'{ind}\t\ttext = "PMR_RI_AXIS_END"\n')
            + bo('empty_state_visibility', f'{ind}\t\tvisible = "[Not({has})]"\n')
            + bo('everything_that_is_not_empty_state_visibility', f'{ind}\t\tvisible = "[{has}]"\n')
            + bo('empty_state_text', f'{ind}\t\ttext = "PMR_RI_EMPTY"\n')
            + f'{ind}}}\n')


def card(ind, inner, extra=''):
    """A fixed CARD_W x CARD_H card, so the law and policy cards match (Pat 04:50Z)."""
    return (f'{ind}widget = {{\n{ind}\tsize = {{ {CARD_W} {CARD_H} }}\n{extra}'
            f'{ind}\tbackground = {{\n{ind}\t\tusing = entry_bg\n{ind}\t}}\n'
            + inner + f'{ind}}}\n')


def card_column(ind, inner, visible=None):
    vis = f'{ind}\tvisible = "[{visible}]"\n' if visible else ''
    return (f'{ind}flowcontainer = {{\n{vis}{ind}\tdirection = vertical\n{ind}\tmargin = {{ 10 10 }}\n{ind}\tspacing = 6\n'
            + inner + f'{ind}}}\n')


def card_title(icon, name, ind, visible=None):
    vis = f'{ind}\tvisible = "[{visible}]"\n' if visible else ''
    return (f'{ind}flowcontainer = {{\n{vis}{ind}\tspacing = 8\n'
            f'{ind}\ticon = {{\n{ind}\t\tsize = {{ 48 48 }}\n{ind}\t\ttexture = "{icon}"\n{ind}\t}}\n'
            f'{ind}\ttextbox = {{\n{ind}\t\tparentanchor = vcenter\n{ind}\t\tautoresize = yes\n{ind}\t\tmax_width = 190\n'
            f'{ind}\t\tmultiline = yes\n{ind}\t\talign = nobaseline\n{ind}\t\tusing = fontsize_large\n'
            f'{ind}\t\ttext = "{name}"\n{ind}\t}}\n{ind}}}\n')


def card_text(key, ind, visible=None, raw=False):
    vis = f'{ind}\tvisible = "[{visible}]"\n' if visible else ''
    return (f'{ind}textbox = {{\n{vis}{ind}\tautoresize = yes\n{ind}\tmultiline = yes\n{ind}\tmax_width = 248\n'
            f'{ind}\talign = nobaseline\n{ind}\t{"raw_text" if raw else "text"} = "{key}"\n{ind}}}\n')


def policy_card(ind):
    """The policy card: a plus in the middle like vanilla's Add Principle slot (Pat 04:50Z); the plus opens the
    four choices in the card (a GUI-only flag, pmr_policy_pick); a held policy shows its name and effects and a
    Change button."""
    scope = f'GuiScope.SetRoot({COUNTRY}.MakeScope).End'
    avail = f"GetScriptedGui('pmr_policy_available_sgui').IsShown({scope})"
    pick = "GetVariableSystem.Exists('pmr_policy_pick')"
    held_any = f"GreaterThan_CFixedPoint({COUNTRY}.MakeScope.Var('pmr_policy').GetValue, '(CFixedPoint)0')"
    held = lambda i: f"EqualTo_CFixedPoint({COUNTRY}.MakeScope.Var('pmr_policy').GetValue, '(CFixedPoint){i}')"
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    inner = ''
    # A policy held: its title and effects, and Change at the bottom
    for i, (k, _s, _n, icon, _m, _e) in enumerate(POLICIES, 1):
        inner += card_column(i1, card_title(icon, f'PMR_POLICY_{k}', i2) + card_text(f'PMR_POLICY_{k}_DESC', i2),
                             f'And(Not({pick}), {held(i)})')
    inner += (f'{i1}button = {{\n{i2}visible = "[And(Not({pick}), {held_any})]"\n{i2}using = default_button\n'
              f'{i2}size = {{ 140 30 }}\n{i2}parentanchor = bottom|hcenter\n{i2}position = {{ 0 -10 }}\n'
              f'{i2}text = "PMR_POLICY_CHANGE"\n{i2}enabled = "[{avail}]"\n'
              f'{i2}onclick = "[GetVariableSystem.Set(\'pmr_policy_pick\', \'yes\')]"\n'
              f'{i2}tooltip = "PMR_POLICY_CHANGE_TT"\n{i2}using = tooltip_above\n{i1}}}\n')
    # None held: vanilla's Add Principle slot, centred, and what it requires beneath it
    inner += (f'{i1}flowcontainer = {{\n{i2}visible = "[And(Not({pick}), Not({held_any}))]"\n{i2}parentanchor = center\n'
              f'{i2}direction = vertical\n{i2}spacing = 8\n'
              f'{i2}new_principle_slot = {{\n{i3}parentanchor = hcenter\n'
              f'{i3}blockoverride "onclick" {{\n{i3}\tonclick = "[GetVariableSystem.Set(\'pmr_policy_pick\', \'yes\')]"\n'
              f'{i3}\tenabled = "[{avail}]"\n{i3}}}\n'
              f'{i3}blockoverride "slot_tooltip" {{\n{i3}\ttooltip = "PMR_POLICY_ADD_TT"\n{i3}}}\n'
              f'{i3}blockoverride "slot_text" {{\n{i3}\ttext = "PMR_POLICY_ADD"\n{i3}}}\n{i2}}}\n'
              f'{i2}textbox = {{\n{i3}visible = "[Not({avail})]"\n{i3}parentanchor = hcenter\n{i3}autoresize = yes\n'
              f'{i3}multiline = yes\n{i3}max_width = 240\n{i3}align = hcenter|nobaseline\n{i3}using = fontsize_small\n'
              f'{i3}text = "PMR_POLICY_LOCKED"\n{i2}}}\n{i1}}}\n')
    # Choosing: the four policies, each closing the choice once taken
    choices = ''
    for k, _s, _n, icon, _m, _e in POLICIES:
        sg = f"GetScriptedGui('pmr_policy_{k}_sgui')"
        choices += (f'{i2}button = {{\n{i3}using = default_button\n{i3}size = {{ 248 42 }}\n'
                    f'{i3}enabled = "[{sg}.IsValid({scope})]"\n'
                    f'{i3}onclick = "[{sg}.Execute({scope})]"\n'
                    f'{i3}onclick = "[GetVariableSystem.Clear(\'pmr_policy_pick\')]"\n'
                    f'{i3}tooltip = "PMR_POLICY_{k}_TT"\n{i3}using = tooltip_above\n{i3}using = confirm_button_sound\n'
                    f'{i3}icon = {{\n{i3}\tsize = {{ 34 34 }}\n{i3}\tparentanchor = vcenter\n{i3}\tposition = {{ 6 0 }}\n'
                    f'{i3}\ttexture = "{icon}"\n{i3}\talwaystransparent = yes\n{i3}}}\n'
                    f'{i3}textbox = {{\n{i3}\tparentanchor = vcenter\n{i3}\tposition = {{ 48 0 }}\n{i3}\tautoresize = yes\n'
                    f'{i3}\tmax_width = 190\n{i3}\telide = right\n{i3}\talign = nobaseline\n'
                    f'{i3}\ttext = "PMR_POLICY_{k}"\n{i3}\talwaystransparent = yes\n{i3}}}\n{i2}}}\n')
    inner += (f'{i1}flowcontainer = {{\n{i2}visible = "[And({avail}, {pick})]"\n{i2}direction = vertical\n'
              f'{i2}margin = {{ 10 10 }}\n{i2}spacing = 6\n'
              f'{i2}textbox = {{\n{i3}autoresize = yes\n{i3}align = nobaseline\n{i3}text = "PMR_POLICY_PICK_TITLE"\n{i2}}}\n'
              + choices + f'{i1}}}\n'
              f'{i1}button = {{\n{i2}visible = "[And({avail}, {pick})]"\n{i2}using = default_button\n'
              f'{i2}size = {{ 26 26 }}\n{i2}parentanchor = right|top\n{i2}position = {{ -8 8 }}\n'
              f'{i2}onclick = "[GetVariableSystem.Clear(\'pmr_policy_pick\')]"\n{i2}tooltip = "PMR_POLICY_CANCEL"\n'
              f'{i2}icon = {{\n{i3}size = {{ 100% 100% }}\n{i3}texture = "gfx/interface/buttons/button_icons/close.dds"\n'
              f'{i3}alwaystransparent = yes\n{i2}}}\n{i1}}}\n')
    return card(ind, inner)


def private_tab(sliders):
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
                                    + card_text('[Law.GetLawType.GetEffectDesc(GetPlayer.Self)]', i2 + '\t\t', raw=True)),
                    f'{i2}\tdatacontext = "[{law}]"\n')
    return (
        '@pmr_w = 554\n\n'
        'types pmr_private_investment {\n'
        '\ttype pmr_private_tab = flowcontainer {\n'
        '\t\tusing = default_list_position\n\t\tdirection = vertical\n\t\tminimumsize = { 540 -1 }\n\t\tmargin_bottom = 10\n\n'
        # 1. the pool
        + header('PMR_PI_POOL_HEADER', i1) +
        f'{i1}widget = {{\n{i1}\tsize = {{ @pmr_w 50 }}\n{i1}\tbackground = {{\n{i1}\t\tusing = entry_bg\n{i1}\t}}\n'
        f'{i1}\ttextbox = {{\n{i1}\t\tusing = fontsize_large\n{i1}\t\tautoresize = yes\n{i1}\t\ttext = "PMR_RI_LABEL"\n'
        f'{i1}\t\talign = left|nobaseline\n{i1}\t\tparentanchor = vcenter\n{i1}\t\tmargin_left = 20\n{i1}\t}}\n'
        f'{i1}\ttextbox = {{\n{i1}\t\tusing = fontsize_large\n{i1}\t\tautoresize = yes\n'
        f'{i1}\t\traw_text = "#v @money![{COUNTRY}.MakeScope.ScriptValue(\'pmr_ri_now\')|D]#!"\n'
        f'{i1}\t\tparentanchor = right|vcenter\n{i1}\t\talign = right|nobaseline\n{i1}\t\tmargin_right = 20\n'
        f'{i1}\t\tusing = investment_pool_tooltip_with_graph\n{i1}\t}}\n{i1}}}\n'
        f'{i1}widget = {{\n{i1}\tsize = {{ @pmr_w 34 }}\n'
        f'{i1}\ttextbox = {{\n{i1}\t\tparentanchor = vcenter\n{i1}\t\tmargin = {{ 20 0 }}\n{i1}\t\talign = nobaseline\n'
        f'{i1}\t\tautoresize = yes\n{i1}\t\tusing = elide_fontsize_min\n{i1}\t\tmax_width = 265\n'
        f'{i1}\t\ttooltip = "[{COUNTRY}.GetPreviousAutonomousInvestmentsDesc]"\n{i1}\t\ttext = "PREVIOUS_INVESTMENTS"\n{i1}\t}}\n{i1}}}\n'
        f'{i1}textbox = {{\n{i1}\tvisible = "[{COUNTRY}.ShowInvestmentPoolPredictedNextBuilding]"\n{i1}\tparentanchor = hcenter\n'
        f'{i1}\tminimumsize = {{ @pmr_w -1 }}\n{i1}\tmaximumsize = {{ @pmr_w -1 }}\n{i1}\tmargin = {{ 10 10 }}\n'
        f'{i1}\tautoresize = yes\n{i1}\tmultiline = yes\n{i1}\talign = hcenter|nobaseline\n{i1}\ttext = "NEXT_PRIVATE_CONSTRUCTION"\n'
        f'{i1}\tbackground = {{\n{i1}\t\tusing = dark_area\n{i1}\t}}\n{i1}}}\n'
        # 2. the weekly re-investment over time, titled inside its graph frame like vanilla's
        + reinvest_chart(i1) +
        # 3. contributors: the game's own breakdown (Pat 04:12Z picked this over an estimate)
        header('PMR_PI_SOURCES_HEADER', i1) +
        f'{i1}textbox = {{\n{i1}\tminimumsize = {{ @pmr_w -1 }}\n{i1}\tmaximumsize = {{ @pmr_w -1 }}\n{i1}\tmargin = {{ 14 8 }}\n'
        f'{i1}\tautoresize = yes\n{i1}\tmultiline = yes\n{i1}\talign = nobaseline\n'
        f'{i1}\traw_text = "[{COUNTRY}.GetInvestmentPoolChangeFromInvestmentBreakdown]"\n{i1}}}\n'
        +
        # 4. economic law and policy
        header('PMR_PI_POLICY_HEADER', i1) +
        f'{i1}flowcontainer = {{\n{i1}\tparentanchor = hcenter\n{i1}\tmargin_top = 8\n{i1}\tmargin_bottom = 8\n{i1}\tspacing = 8\n'
        + law_card + policy_card(i2) + f'{i1}}}\n'
        # 5. sliders
        + header('PMR_IPW_HEADER', i1) +
        f'{i1}textbox = {{\n{i1}\tminimumsize = {{ @pmr_w -1 }}\n{i1}\tmaximumsize = {{ @pmr_w -1 }}\n{i1}\tmargin = {{ 10 6 }}\n'
        f'{i1}\tautoresize = yes\n{i1}\tmultiline = yes\n{i1}\talign = nobaseline\n{i1}\ttext = "PMR_IPW_EXPLAIN"\n{i1}}}\n'
        + ''.join(priority_row(g, i1) for g in sliders) +
        # 6. private construction, then recent investments
        f'{i1}default_header_2texts = {{\n{i1}\tblockoverride "text1" {{\n{i1}\t\ttext = "PMR_PI_QUEUE_HEADER"\n{i1}\t}}\n'
        f'{i1}\tblockoverride "text2" {{\n{i1}\t\ttext = "PMR_PI_QUEUE_COUNT"\n{i1}\t}}\n{i1}}}\n'
        f'{i1}flowcontainer = {{\n{i1}\tparentanchor = hcenter\n{i1}\tmargin = {{ 0 8 }}\n{i1}\tspacing = 5\n'
        + ''.join(filt) + f'{i1}}}\n'
        f'{i1}fixedgridbox = {{\n{i1}\tvisible = "[Not(IsDataModelEmpty({queue}))]"\n{i1}\taddcolumn = 540\n{i1}\taddrow = 40\n'
        f'{i1}\tparentanchor = hcenter\n{i1}\tdatamodel = "[{queue}]"\n{i1}\titem = {{\n{i1}\t\tconstruction_queue_item = {{}}\n{i1}\t}}\n{i1}}}\n'
        f'{i1}empty_state = {{\n{i1}\tblockoverride "visible" {{\n{i1}\t\tvisible = "[IsDataModelEmpty({queue})]"\n{i1}\t}}\n'
        f'{i1}\tblockoverride "text" {{\n{i1}\t\ttext = "PMR_PI_QUEUE_EMPTY"\n{i1}\t}}\n{i1}}}\n'
        + header('PMR_PI_RECENT_HEADER', i1) +
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


def slider_of(bk, btype, parent, sliders):
    g = btype.get(bk)
    while g and g not in sliders:
        g = parent.get(g)
    return g


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


def patch_retool_ai(text, btype, parent, sliders):
    """pmr_retool_buildings.txt: each private retool building's ai_value ends with multiply = pmr_reinvest_mult_<group>."""
    edits, n = [], 0
    for k, _s, o, c in top_blocks(text):
        m = re.fullmatch(r'building_pmr_retool_(.+)_(\d+)', k)
        if not m or k.startswith('building_pmr_retool_gov_'):
            continue
        g = slider_of('building_' + m.group(1), btype, parent, sliders)
        if not g:
            fail('pmr_retool_buildings.txt', f'no slider group for {k}')
        a = text.find('\tai_value = {', o, c)
        if a < 0:
            fail('pmr_retool_buildings.txt', f'{k} has no ai_value block')
        close = block_end(text, text.index('{', a))
        edits.append((close, f'\t# PMR: Re-invest card, x the {g} slider\n\t\tmultiply = pmr_reinvest_mult_{g}\n\t'))
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

def localization(sliders):
    loc = [
        ' PMR_TAB_GOVERNMENT:0 "Government"',
        ' PMR_TAB_GOVERNMENT_TT:0 "The construction sector and the government construction queue"',
        ' PMR_TAB_PRIVATE:0 "Private"',
        ' PMR_TAB_PRIVATE_TT:0 "The investment pool, economic policy, investment priorities and private construction"',
        ' PMR_PI_POOL_HEADER:0 "Investment Pool"',
        ' PMR_RI_LABEL:0 "Weekly re-investment:"',
        ' PMR_RI_CHART_HEADER:0 "Weekly Re-investment"',
        ' PMR_RI_EMPTY:0 "Recorded on the 1st of each month"',
        f' PMR_RI_AXIS_START:0 "{RI_MONTHS - 1} months ago"',
        ' PMR_RI_AXIS_END:0 "This month"',
        ' PMR_PI_POLICY_HEADER:0 "Economic Policy"',
        ' PMR_PI_SOURCES_HEADER:0 "Buildings Adding to the Pool"',
        ' PMR_PI_QUEUE_HEADER:0 "Private Construction"',
        ' PMR_PI_QUEUE_COUNT:0 ""',
        ' PMR_PI_QUEUE_EMPTY:0 "No private construction is queued"',
        ' PMR_PI_RECENT_HEADER:0 "Recent Investments and Privatizations"',
        ' PMR_POLICY_ADD:0 "Add Policy"',
        ' PMR_POLICY_ADD_TT:0 "Choose an economic policy. One can be held at a time, and it lapses if [GetLawType(\'law_interventionism\').GetName] is repealed."',
        ' PMR_POLICY_LOCKED:0 "Requires [GetLawType(\'law_interventionism\').GetName]"',
        ' PMR_POLICY_PICK_TITLE:0 "Choose a Policy"',
        ' PMR_POLICY_CANCEL:0 "Close without choosing"',
        ' PMR_POLICY_CHANGE:0 "Change Policy"',
        ' PMR_POLICY_CHANGE_TT:0 "Swap this policy for another. Only one can be held at a time."',
        ' PMR_IPW_HEADER:0 "Investment Priorities"',
        ' PMR_IPW_EXPLAIN:0 "Raise how much your investors favour a building group over the others: a full slider adds '
        '#v +[FixedPointToInt(Multiply_CFixedPoint(GetPlayer.MakeScope.ScriptValue(\'pmr_ipw_cap\'), \'(CFixedPoint)100\'))]%#! weight '
        '(+75% under Steer the Economy). '
        'Raising every group by the same amount changes nothing. A group your investors already weigh at the 25% '
        'minimum cannot drop further, so a boost gains nothing against it."',
    ]
    for k, short, name, _i, mods, effect in POLICIES:
        loc += [f' PMR_POLICY_{k}:0 "{name}"', f' PMR_POLICY_{k}_SHORT:0 "{short}"',
                f' PMR_POLICY_{k}_DESC:0 "{effect}' + (f'\\n{mod_lines(mods)}' if mods else '') + '"',
                f' PMR_POLICY_{k}_TT:0 "#header {name}#!\\n{effect}' + (f'\\n{mod_lines(mods)}' if mods else '') + '"']
    for s in STEPS:
        loc.append(f' PMR_IPW_NOTCH_{s}:0 "' + ('No priority' if s == 0 else
                   f'{s}% of the cap: #v +[FixedPointToInt(Multiply_CFixedPoint({COUNTRY}.MakeScope.ScriptValue(\'pmr_ipw_cap\'), \'(CFixedPoint){s}\'))]%#! weight') + '"')
    for i in range(RI_MONTHS):
        when = 'This month' if i == 0 else ('1 month ago' if i == 1 else f'{i} months ago')
        loc.append(f' PMR_RI_COLUMN_{i}:0 "{when}: #v @money![{COUNTRY}.MakeScope.Var(\'pmr_ri_{i}\').GetValue|D]#! a week"')
    for g in sliders:
        v = VAR.format(g)
        loc.append(f' PMR_IPW_ROW_{g}:0 "Your investors weigh ${g}$ at #v ×[{COUNTRY}.MakeScope.ScriptValue(\'{v}\')|2]#! '
                   f'its usual weight. Only the differences between sliders matter: the highest slider\'s group stays at ×1.00."')
    return loc


def write_all(game, write, header_text, out=None):
    """Writes every file this feature owns, then patches generate.py's building outputs under out (skipped when
    out is None, as in the standalone run). Returns loc lines."""
    def vanilla(rel):
        return open(os.path.join(game, rel), encoding='utf-8-sig').read()
    buildings, groups, sliders = patch_scores(vanilla(SOURCE_FILE))
    write(SOURCE_FILE, buildings)
    values = script_values(groups, sliders)
    write('common/scripted_guis/pmr_ipw_sguis.txt', header_text + sguis(sliders))
    write('common/static_modifiers/pmr_policy_modifiers.txt', header_text + static_modifiers())
    write('common/on_actions/pmr_pi_on_actions.txt', header_text + on_actions())
    write('common/scripted_effects/pmr_pi_effects.txt', header_text + reinvest_effect())
    write(QUEUE_GUI, patch_queue(vanilla(QUEUE_GUI)), bom=False)
    write(PANEL_GUI, patch_panel(vanilla(PANEL_GUI)), bom=False)
    write(OWN_GUI, '# GENERATED by tools/pmr/private_investment.py\n' + private_tab(sliders), bom=False)
    if out:
        btype, parent = building_groups(game)
        rpath = os.path.join(out, 'common', 'buildings', 'pmr_retool_buildings.txt')
        text, n = patch_retool_ai(open(rpath, encoding='utf-8-sig').read(), btype, parent, sliders)
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
    return localization(sliders)


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
