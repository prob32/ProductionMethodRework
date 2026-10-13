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
  4. the economic system law as a card, and to its right a policy card, chosen under Interventionism or (Pat 16:06Z)
     Laissez-faire
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

Policies (Pat: under Interventionism; 16:06Z: two more under Laissez-faire). One at a time, as a static modifier; a
monthly country pulse drops it when the country no longer has its law (POLICY_LAWS). The policy card's plus opens a window beside the panel with every policy as a
blue card that is clicked to adopt it, showing its benefits only, the explanation on hover (Pat 13:05Z and 14:28Z;
Pat also asked for a few fitting benefits to round them out: the modifiers in POLICIES).
  - Steer the Economy (Pat 04:16Z): the sliders' cap goes from +50% to +75%.
  - Favour Large Corporations (Pat 04:15Z): the pool weighs building types your companies list higher. There is no
    modifier or per-country define for company weighting, so each company building type in PMR's building files gets
    ai_value = pmr_ai_value_<b>: its vanilla ai_value plus CORP_BONUS while the card is held. Its other benefits
    work the interventionist way: since Pat 16:42Z only a free charter.
  - Re-invest (Pat 04:15Z): private retooling of a building is weighted by its group's slider, x(1 + 0.99 x slider%),
    so x100 at a full slider. Retool weight is mostly ai_value (no profit terms), so this multiplies
    pmr_retool_buildings.txt's private ai_value.
  - Favour Small Businesses (Pat confirmed 04:25Z): shopkeepers' investment efficiency +15%, self-investment chance +10%.
  - Bulls & Bears (Laissez-faire, needs Investment Banks; Pat 16:06Z): the modifiers in POLICIES, profitability
    weight in pmr_ai_value_<b>, Market Liberal leader weights x LIBERAL_WEIGHT (patch_ideologies).
  - Market Titans (Laissez-faire; Pat 16:06Z): the modifiers in POLICIES, company industries' weight in
    pmr_ai_value_<b>, Industrialists approval per institution (pmr_policy_upkeep). No executive bonus modifier exists.

Wiring into generate.py main(), after the other writes and before the localization file is written:

    import private_investment
    loc += private_investment.write_all(game, write, header, args.out)

It must run after the building files and pmr_retool_buildings.txt are written: it patches those two outputs in place
(company ai_value; Re-invest's retool multiplier) and asserts what it expects to find.
"""
import colorsys
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
# Pat 15:33Z: the Victoria 3 palette instead of the bright one. The colours are the pop types' own
# (common/pop_types/*.txt, hsv), which the GUI can read as GetPopType('<pop>').GetColor, so the tree charts (whose
# tiles take a bound colour) and the bars and legends (literal colours, the same values converted here) match.
POP_HSV = {
    'academics': (0.94, 0.51, 0.37), 'aristocrats': (0.60, 0.58, 0.46), 'bureaucrats': (0.25, 0.4, 0.5),
    'capitalists': (0.52, 0.32, 0.49), 'engineers': (0.07, 0.57, 0.77), 'officers': (0.12, 0.51, 0.36),
    'peasants': (0.58, 0.338, 0.812), 'slaves': (0.11, 0.21, 0.68), 'soldiers': (0.8, 0.20, 0.56),
}


def pop_rgb(pop):
    return tuple(round(x, 2) for x in colorsys.hsv_to_rgb(*POP_HSV[pop]))


# Pat 13:05Z: five priority groups over the vanilla building groups (a building group's children come with it).
# Pat named farms, plantations and fishing for Agriculture; ranches, whaling and rubber plantations join them, and
# military industry joins Heavy Industries (defaults, said in the reply). Each entry: key, name, the pop type whose
# colour it takes, that colour, and the building groups.
GROUPS = [
    ('light', 'Light Industries', 'capitalists', pop_rgb('capitalists'), ('bg_light_industry', 'bg_arts')),
    ('heavy', 'Heavy Industries', 'soldiers', pop_rgb('soldiers'), ('bg_heavy_industry', 'bg_military_industry')),
    ('agriculture', 'Agriculture', 'bureaucrats', pop_rgb('bureaucrats'),
     ('bg_agriculture', 'bg_ranching', 'bg_plantations', 'bg_fishing', 'bg_whaling', 'bg_rubber')),
    ('resources', 'Resources', 'engineers', pop_rgb('engineers'), ('bg_mining', 'bg_logging', 'bg_oil_extraction')),
    ('infrastructure', 'Infrastructure', 'slaves', pop_rgb('slaves'), ('bg_infrastructure', 'bg_power', 'bg_trade')),
]
# Pat 15:33Z: who owns what feeds the pool, a second tree chart. Key, name, pop type for the colour.
OWNERS = [
    ('gov', 'Government', 'aristocrats'),
    ('self', 'Local Shop Owners', 'academics'),
    ('company', 'Companies', 'peasants'),
    ('invest', 'Manor Houses and Financial Districts', 'officers'),
]
# Pat 15:33Z: a third chart, who built. Key, name, pop type for the colour (a tree map slice takes its colour from
# the GUI, so pop types' colours: tan for your own investors and domestic, plum for foreign).
WHO = [
    ('gov', 'Government', 'aristocrats'),
    ('investors', 'Your Investors', 'engineers'),
    ('local', 'Local Owners', 'academics'),
    ('foreign', 'Foreign Investors', 'soldiers'),
]
HOME_POP, ABROAD_POP = 'engineers', 'soldiers'
GROUP_OF = {bg: k for k, _n, _d, _c, bgs in GROUPS for bg in bgs}
NO_GROUP = 'none'          # a scored building group outside the five (Manufacturing itself): an untouched slider
# The chart counts private levels of these building groups; subsistence farms and ranches are no investors' business.
CHART_EXCLUDE = ('bg_subsistence_agriculture', 'bg_subsistence_ranching')
REINVEST_PER_POINT = 0.99  # Re-invest: retool ai_value x (1 + this x slider%): x100 at 100%
# Vanilla's profit term is 5000 x 1.5 a pound of predicted WEEKLY profit per employee (00_ai.txt); the
# earnings PMR reads (pmr_ai_earn_<b>) are a YEAR's, so a pound of them weighs 7500 / 52. Until 20:12Z PMR
# weighed it at 7,500, which made every weight below about 50 times too strong (Pat's 1838 autosave: new
# builds scored 30..3,400 before the roll, retool sites 39,000..75,000; see generate.py RETOOL_AI_MULT).
PROFIT_WEIGHT = round(7500 / 52)
CORP_BONUS = 10 * PROFIT_WEIGHT   # Favour Large Corporations: ai_value added, = GBP 10/worker a year of profit
LIBERAL_WEIGHT = 1.25      # Bulls & Bears: Market Liberal leader weights x this (Pat 16:06Z: +25%)
TITANS_APPROVAL = -2       # Market Titans: Industrialists approval per institution (Pat 16:06Z)
TITANS_INSTITUTIONS = ('institution_health_system', 'institution_schools')
EARNINGS_LADDER = (50, 40, 30, 25, 20, 15, 12, 10, 8, 6, 4, 2)   # as generate.py's RETOOL_EARNINGS_LADDER
BASE_AI_VALUE = 1000       # PRODUCTION_BUILDING_BASE_VALUE, when a building has no ai_value

# key, name, icon, modifiers, the card's first benefit (what PMR's script does, short), how that works (hover),
# details (hover). Pat 14:28Z: the cards show benefits only, the explanation goes in the hover; construction and
# investment efficiency belong to Laissez-faire. Pat 15:33Z: Favour Large Corporations drops the extra company and
# takes benefits for the companies themselves (he named output prices and lower wages; 1.14.5 has no company price or
# wage modifier, so it took the Company Throughput Bonus and kept the free charter and the state's cut; Pat 16:42Z
# removed the throughput bonus and the state's cut, leaving the free charter and the investment weight); Small
# Businesses gives shopkeepers +25%; Re-invest becomes Focus on Infrastructure (railway and port throughput instead of
# dividends reinvestment, a gold rail icon; the key stays so saves keep it).
POLICIES = [
    ('steer', 'Steer the Economy', 'gfx/interface/icons/law_icons/command_economy.dds',
     {},
     f'#P +{CAP_STEER * 100:.0f}%#! Investment Priority Cap',
     f'Each investment priority can add up to #P +{CAP_STEER * 100:.0f}%#! to its group instead of '
     f'#v +{CAP * 100:.0f}%#!.',
     'The state sets investment targets and leans on banks and boards to meet them. Investors still choose what to '
     'build, but within the priorities you set.'),
    ('corporations', 'Favour Large Corporations', 'gfx/interface/icons/law_icons/corporate_state.dds',
     {'country_free_charters_add': 1},     # Pat 16:42Z: throughput bonus and government dividends removed
     '#P Higher#! Investment Weight for Company Industries',
     'Investors weigh building types your companies own as if each earned #P @money!10#! more per worker. A monopoly '
     'is a company charter, so the free charter lets one more of your companies hold one without spending authority.',
     'National champions get licences, contracts and charters ahead of their smaller rivals.'),
    ('reinvest', 'Focus on Infrastructure', 'gfx/interface/icons/ai_strategy_icons/unused/infrastructure_expansion.dds',
     {'building_railway_throughput_add': 0.1, 'building_port_throughput_add': 0.1},
     '#P Up to 100×#! Investment Weight for Retooling',
     'Investors favour retooling a building by its group\'s investment priority: up to #P 100×#! at a full '
     'priority.',
     'Rails, docks and new machinery come before new sites: the state guarantees the loans and the works are '
     'brought up to date.'),
    ('small', 'Favour Small Businesses', 'gfx/interface/icons/law_icons/cooperative_ownership.dds',
     {'state_shopkeepers_investment_pool_efficiency_mult': 0.25, 'building_self_investment_chance_add': 0.1},
     None, None,
     'Shopkeepers get easier credit and lighter paperwork, so more of their savings reach the pool and more new '
     'levels stay with the people who work them.'),
    # Pat 16:06Z: two Laissez-faire cards. Bulls & Bears needs Investment Banks. Its profitability weight and Market
    # Titans' company weight are added to ai_value (pmr_ai_value_<b>), from the building's earnings per employee
    # in the state (pmr_ai_earn_<b>); Market Liberals appear more often through the ideology's own leader weights
    # (patch_ideologies); Market Titans' Industrialists penalty is a modifier per institution, kept monthly. 1.14.5
    # has no scope or modifier for an executive's bonuses, so those are not doubled.
    ('bulls', 'Bulls & Bears', 'gfx/interface/icons/law_icons/laissez_faire.dds',
     {'state_capitalists_investment_pool_efficiency_mult': 0.25, 'country_private_construction_allocation_mult': 0.15,
      'state_market_access_price_impact': 0.025, 'interest_group_ig_trade_unions_approval_add': -2,
      'interest_group_ig_trade_unions_pop_attraction_mult': 0.1},
     f'#P +50%#! Investment Weight from Profitability\\n#P +{(LIBERAL_WEIGHT - 1) * 100:.0f}%#! Market Liberal Leaders',
     f'Investors weigh each building in your states by half as much again of its earnings per employee as the game '
     f'does. Leaders with the Market Liberal ideology are #P {(LIBERAL_WEIGHT - 1) * 100:.0f}%#! more likely to come '
     f'forward. Requires $investment_banks$.',
     'The exchange never sleeps: capital goes wherever the returns are highest, and the state keeps out of its way.'),
    ('titans', 'Market Titans', 'gfx/interface/icons/law_icons/corporate_state.dds',
     {'country_max_companies_add': 1, 'country_free_charters_add': 4, 'country_company_throughput_bonus_add': 0.2,
      'country_company_construction_efficiency_bonus_add': 0.2},
     f'#P +50%#! Investment Weight for Company Industries\\n#N {TITANS_APPROVAL}#! Industrialists Approval for each of '
     f'$institution_health_system$ and $institution_schools$',
     'Investors weigh building types your companies own by half as much again of their usual weight. The '
     'Industrialists resent paying for public health and schooling while the giants run the economy.',
     'A handful of great houses own the railways, the mills and the banks, and the state lets them.'),
    # Pat 19:34Z: Agrarianism's cards, one for the land and one for the mines and forests, the two priority groups
    # Agrarianism leaves open (LAW_ROWS).
    ('landed', 'Landed Credit', 'gfx/interface/icons/law_icons/agrarianism.dds',
     {'state_aristocrats_investment_pool_efficiency_mult': 0.25, 'building_group_bg_agriculture_throughput_add': 0.1,
      'interest_group_ig_landowners_approval_add': 2, 'interest_group_ig_industrialists_approval_add': -2},
     None, None,
     'Land banks lend against estates and the coming harvest. The landowners drain, fence and manure their fields '
     'with the credit, and the rents go back into the land.'),
    ('concessions', 'Crown Concessions', 'gfx/interface/icons/law_icons/extraction_economy.dds',
     {'building_group_bg_mining_throughput_add': 0.1, 'building_group_bg_logging_throughput_add': 0.1,
      'country_government_dividends_efficiency_add': 0.1, 'interest_group_ig_rural_folk_approval_add': -2},
     None, None,
     'The crown leases its mines and forests to whoever will work them, for a share of the yield, and the villages '
     'lose their commons to the lessees.'),
]
# Pat 16:06Z: each policy belongs to one economic system law, and some need a technology.
POLICY_LAWS = {'steer': 'law_interventionism', 'corporations': 'law_interventionism', 'reinvest': 'law_interventionism',
               'small': 'law_interventionism', 'bulls': 'law_laissez_faire', 'titans': 'law_laissez_faire',
               'landed': 'law_agrarianism', 'concessions': 'law_agrarianism'}
POLICY_TECH = {'bulls': 'investment_banks'}
# Pat 19:34Z: a priority changes as a tariff does: once changed, 7 days to think again, then locked for 3 months
# (TARIFF_LEVEL_COOLDOWN_GRACE_PERIOD_DAYS, TARIFF_LEVEL_COOLDOWN_MONTHS, 00_defines.txt). Each row on its own clock.
GRACE_DAYS = 7
COOLDOWN_DAYS = GRACE_DAYS + 91
COOLDOWN_WEEKS = COOLDOWN_DAYS // 7
# Pat 19:34Z: the priority rows a law leaves open. Every other row counts as +0% and is locked while the law holds;
# the coin set before is kept and counts again under another law. Laissez-faire leaves none.
LAW_ROWS = {'law_laissez_faire': (), 'law_agrarianism': ('agriculture', 'resources')}
# Pat 19:34Z: adopting a policy costs authority by legitimacy: 200 at 25 or less, 100 at 50, 50 at 75 or more,
# straight lines between. It is fixed when the policy is adopted and used while the policy is held, as vanilla
# charges authority for patronage (an add_modifier of country_authority_cost_add x the cost, 00_ep2_04_modifiers.txt).
POLICY_COST_LOW, POLICY_COST_MID, POLICY_COST_HIGH = 200, 100, 50
# How the policy window works, now in the Add Policy and Change Policy tooltips (Pat 20:06Z: no text in the window).
POLICY_HOW = ('One can be held at a time, and it lapses if your economic system law changes. It uses @aut! authority '
              f'while held, set by your legitimacy when you adopt it: {POLICY_COST_LOW} at 25 or less, {POLICY_COST_MID} '
              f'at 50, {POLICY_COST_HIGH} at 75 or more.')
# Pat 20:06Z: a policy is kept for 5 years once adopted; then it can be swapped, or cancelled with the card's X (20:08Z).
# pmr_policy_lock_m counts the months left, down on each monthly pulse.
POLICY_LOCK_MONTHS = 60
AI_SKIP = ('steer',)       # the AI never picks Steer the Economy: it only raises the cap of the player's priorities
RI_WEEKS = 26              # re-investment chart: one column per week (Pat 14:28Z), newest on the right
RI_ROWS, RI_ROW_H, RI_COL_W = 20, 6, 7    # columns are measured in rows of 6 px, from zero to the highest week
PLOT_MARGINS = (52, 14)    # v3_plotline's left and right margins, narrowed so two graphs share the row
POOL_GRAPH_W = 200         # the vanilla investment pool graph beside it (Pat 14:28Z)
# Recent investments as the market panel's Exports and Imports charts (Pat 16:12Z): vanilla compact_chart
# (politics_panel_types.gui), a 120 px tree map in its frame with legend rows of 28 px, four to a column.
TREE = 120
LEGEND_ROW_H, LEGEND_ROWS = 28, 4
PANEL_W = 540
# Building groups whose types are no investors' business, left out of the bars.
INVEST_EXCLUDE = ('bg_canals', 'bg_construction', 'bg_subsistence_agriculture', 'bg_subsistence_ranching')
# A plain white texture that 1.14.5 ships (gfx/interface/colors/white.dds, used before, does not exist: the line
# drew nothing, Pat 13:05Z).
WHITE = 'gfx/interface/backgrounds/white.dds'
TRANSPARENT = 'gfx/interface/icons/generic_icons/transparent.dds'
# Foreign or domestic investment (Pat 15:34Z), on the tariff bar's seven notches: 1 = strongly foreign, 4 = no
# preference, 7 = strongly domestic. Each notch from the middle adds or takes FD_STEP of ai_value from every
# investable building type in the player's states (GBP 1 a worker a year of vanilla's profit term, as CORP_BONUS).
FD_NOTCHES = 7
SINCE = 'Counted since this version of the mod was loaded.'
FD_STEP = PROFIT_WEIGHT
FD_ICONS = ('max_subvention', 'high_subvention', 'low_subvention', 'no_tariffs_no_subvention', 'low_tariffs',
            'high_tariffs', 'max_tariffs')
CARD_W, CARD_H = 268, 380                 # law and policy cards, the same size (Pat 04:50Z), taller (Pat 13:05Z)
PCARD_W = 300                             # a policy in the policy window: benefits only (Pat 14:28Z)
# Each row of policy cards is as tall as its longest card's text (Pat 19:25Z: the Laissez-faire cards ran out of
# their fixed 176 px and the status line sat on the effects). A GUI box cannot size itself to wrapped text and
# keep two cards level, so the height is worked out here from the text: 1.14.5's body font averages 6.9 px a
# character and 22 px a line (measured on Pat's 19:25Z screenshot), lines wrap at the card's text width.
PCARD_CHAR_W, PCARD_LINE_H = 6.9, 22
PCARD_TOP, PCARD_FOOT = 10 + 48 + 6, 6 + 20 + 10    # margin, icon row, spacing / spacing, status line, margin
PCARD_LOC = {'institution_health_system': 'Health System', 'institution_schools': 'Education',
             'investment_banks': 'Investment Banks'}    # vanilla names, for the estimate only
MOD_NAMES = {  # how each modifier reads on a policy card (vanilla's names, modifiers.log)
    'country_free_charters_add': 'Free Company Charters',
    'country_company_throughput_bonus_add': 'Company Throughput Bonus',
    'building_company_government_dividends_add': 'Company Government Dividends',
    'building_railway_throughput_add': 'Railway Throughput',
    'building_port_throughput_add': 'Port Throughput',
    'state_shopkeepers_investment_pool_efficiency_mult': 'Shopkeepers\' Investment Efficiency',
    'building_self_investment_chance_add': 'Self-investment Chance',
    'state_capitalists_investment_pool_efficiency_mult': 'Capitalists\' Investment Efficiency',
    'country_private_construction_allocation_mult': 'Private Construction Allocation',
    'state_market_access_price_impact': 'Market Access Price Impact',
    'interest_group_ig_trade_unions_approval_add': 'Trade Unions Approval',
    'interest_group_ig_trade_unions_pop_attraction_mult': 'Trade Unions Attraction',
    'country_max_companies_add': 'Max Number of Companies',
    'country_company_construction_efficiency_bonus_add': 'Company Construction Bonus',
    'state_aristocrats_investment_pool_efficiency_mult': 'Aristocrats\' Investment Efficiency',
    'building_group_bg_agriculture_throughput_add': 'Agriculture Throughput',
    'building_group_bg_mining_throughput_add': 'Mining Throughput',
    'building_group_bg_logging_throughput_add': 'Logging Throughput',
    'country_government_dividends_efficiency_add': 'Government Dividends Efficiency',
    'interest_group_ig_landowners_approval_add': 'Landowners Approval',
    'interest_group_ig_industrialists_approval_add': 'Industrialists Approval',
    'interest_group_ig_rural_folk_approval_add': 'Rural Folk Approval',
}
BAD = ('interest_group_ig_trade_unions_approval_add', 'interest_group_ig_trade_unions_pop_attraction_mult',
       'interest_group_ig_industrialists_approval_add', 'interest_group_ig_rural_folk_approval_add')
NEUTRAL = ('state_market_access_price_impact',)
WHOLE = ('country_free_charters_add', 'country_max_companies_add', 'interest_group_ig_trade_unions_approval_add',
         'interest_group_ig_landowners_approval_add', 'interest_group_ig_industrialists_approval_add',
         'interest_group_ig_rural_folk_approval_add')   # counts, not percentages


def benefit_lines(core, mods):
    """A policy's benefits, one per line: what PMR's script does, then each modifier."""
    out = [core] if core else []
    for m, v in mods.items():
        c = 'N' if m in BAD else 'v' if m in NEUTRAL else 'P'
        num = f'{v:+d}' if m in WHOLE else f'{v * 100:+.1f}%'.replace('.0%', '%')
        out.append(f'#{c} {num}#! {MOD_NAMES[m]}')
    return '\\n'.join(out)


def text_lines(text, width):
    """How many lines a policy card's text takes at width px: each \\n starts a line, words wrap."""
    text = re.sub(r'#[A-Za-z]+ |#!', '', text)
    text = re.sub(r'\$(\w+)\$', lambda m: PCARD_LOC.get(m.group(1), m.group(1)), text)
    n = 0
    for para in text.split('\\n'):
        line, n = '', n + 1
        for word in para.split():
            if line and len(line) + 1 + len(word) > width / PCARD_CHAR_W:
                line, n = word, n + 1
            else:
                line = f'{line} {word}' if line else word
    return n


def policy_card_h(keys):
    """The height of a row of policy cards: room for the longest card's benefits and its status line."""
    by_key = {k: (core, mods) for k, _n, _i, mods, core, *_x in POLICIES}
    lines = max(text_lines(benefit_lines(*by_key[k]), PCARD_W - 24) for k in keys)
    return PCARD_TOP + lines * PCARD_LINE_H + PCARD_FOOT


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
    top = ''.join(f'\tmin = pmr_ipw_now_{g}\n' for g in keys)
    out = ('# Country scope. Each priority as it counts now, 0..100: the coin set, or 0 while the economic system law\n'
           '# locks the row (pmr_ipw_law_lock_<g>, Pat 19:34Z).\n')
    for g in keys:
        v = VAR.format(g)
        out += (f'pmr_ipw_now_{g} = {{\n\tvalue = 0\n\tif = {{\n\t\tlimit = {{\n\t\t\thas_variable = {v}\n'
                f'\t\t\tNOT = {{ pmr_ipw_law_lock_{g} = yes }}\n\t\t}}\n\t\tvalue = var:{v}\n\t}}\n}}\n\n')
    out += '# Country scope, for the panel: 1 while the law locks the row; 1 while the row is cooling down (Pat 19:34Z).\n'
    for g in keys:
        out += (f'pmr_ipw_locked_{g} = {{\n\tvalue = 0\n\tif = {{\n\t\tlimit = {{ pmr_ipw_law_lock_{g} = yes }}\n'
                '\t\tvalue = 1\n\t}\n}\n\n'
                f'pmr_ipw_cooling_{g} = {{\n\tvalue = 0\n\tif = {{\n\t\tlimit = {{\n\t\t\thas_variable = pmr_ipw_cd_{g}\n'
                f'\t\t\tNOT = {{ has_variable = pmr_ipw_grace_{g} }}\n\t\t}}\n\t\tvalue = 1\n\t}}\n}}\n\n')
    out += ('pmr_ipw_lf = {\n\tvalue = 0\n\tif = {\n\t\tlimit = { has_law_or_variant = law_type:law_laissez_faire }\n'
            '\t\tvalue = 1\n\t}\n}\n\n')
    # straight lines through (25, LOW), (50, MID) and (75, HIGH), clamped
    s1, s2 = (POLICY_COST_MID - POLICY_COST_LOW) / 25, (POLICY_COST_HIGH - POLICY_COST_MID) / 25
    out += (f'# Country scope. A policy\'s authority cost by legitimacy (Pat 19:34Z): {POLICY_COST_LOW} at 25 or less, '
            f'{POLICY_COST_MID} at 50,\n# {POLICY_COST_HIGH} at 75 or more.\n'
            f'pmr_policy_cost = {{\n\tvalue = legitimacy\n\tif = {{\n\t\tlimit = {{ legitimacy < 50 }}\n'
            f'\t\tmultiply = {s1:g}\n\t\tadd = {POLICY_COST_LOW - s1 * 25:g}\n\t}}\n'
            f'\telse = {{\n\t\tmultiply = {s2:g}\n\t\tadd = {POLICY_COST_MID - s2 * 50:g}\n\t}}\n'
            f'\tmin = {POLICY_COST_HIGH}\n\tmax = {POLICY_COST_LOW}\n\tround = yes\n}}\n\n'
            '# Country scope, for the panel: 1 while the held policy is in its first 5 years (POLICY_LOCK_MONTHS); 1 once\n'
            '# a held policy may be cancelled.\n'
            'pmr_policy_locked = {\n\tvalue = 0\n\tif = {\n\t\tlimit = { has_variable = pmr_policy_lock_m }\n\t\tvalue = 1\n\t}\n}\n\n'
            'pmr_policy_cancellable = {\n\tvalue = 0\n\tif = {\n\t\tlimit = {\n\t\t\thas_variable = pmr_policy\n'
            '\t\t\tNOT = { has_variable = pmr_policy_lock_m }\n\t\t}\n\t\tvalue = 1\n\t}\n}\n\n'
            + ''.join(f'pmr_policy_no_tech_{k} = {{\n\tvalue = 1\n\tif = {{\n\t\tlimit = {{ has_technology_researched = {tech} }}\n'
                      '\t\tvalue = 0\n\t}\n}\n\n' for k, tech in POLICY_TECH.items()) +
            '# Country scope. The authority a new policy needs free: its cost less what the policy held now uses.\n'
            'pmr_policy_cost_net = {\n\tvalue = pmr_policy_cost\n\tif = {\n\t\tlimit = { has_variable = pmr_policy_paid }\n'
            '\t\tsubtract = var:pmr_policy_paid\n\t}\n\tmin = 0\n}\n\n')
    out += ('# Country scope. What a full slider adds to a group\'s weight: +50%, or +75% under Steer the Economy.\n'
           f'pmr_ipw_cap = {{\n\tvalue = {CAP}\n\tif = {{\n\t\tlimit = {{ has_modifier = pmr_policy_steer }}\n\t\tvalue = {CAP_STEER}\n\t}}\n}}\n\n'
           '# Country scope. The highest slider position, 0..100 (min = X keeps the value at least X).\n'
           f'pmr_ipw_top = {{\n\tvalue = 0\n{top}}}\n\n'
           '# Country scope, read by the investment_scores of Manor Houses and Financial Districts, one per priority\n'
           '# group: (100 + slider x cap) / (100 + highest slider x cap). Exactly 1 for AI countries and for a player who\n'
           '# never touched the sliders.\n')
    for g in keys:
        v = VAR.format(g)
        out += (f'{v} = {{\n\tvalue = 1\n\tif = {{\n\t\tlimit = {{ has_variable = {ON} }}\n\t\tvalue = pmr_ipw_now_{g}\n'
                '\t\tmultiply = pmr_ipw_cap\n\t\tadd = 100\n'
                '\t\tdivide = {\n\t\t\tvalue = pmr_ipw_top\n\t\t\tmultiply = pmr_ipw_cap\n\t\t\tadd = 100\n\t\t}\n\t}\n}\n\n')
    out += ('# A scored building group in no priority group (Manufacturing itself, now only retooling): an untouched slider.\n'
            f'{VAR.format(NO_GROUP)} = {{\n\tvalue = 1\n\tif = {{\n\t\tlimit = {{ has_variable = {ON} }}\n\t\tvalue = 100\n'
            '\t\tdivide = {\n\t\t\tvalue = pmr_ipw_top\n\t\t\tmultiply = pmr_ipw_cap\n\t\t\tadd = 100\n\t\t}\n\t}\n}\n\n')
    out += '# Country scope. The weight a slider adds now, as a fraction (0.25 = +25%), for the panel.\n'
    for g in keys:
        v = VAR.format(g)
        out += (f'{v}_pct = {{\n\tvalue = pmr_ipw_now_{g}\n\tmultiply = pmr_ipw_cap\n\tdivide = 100\n}}\n\n')
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
        out += (f'pmr_pc_{g} = {{\n\tvalue = 0\n\tevery_scope_building = {{\n\t\tlimit = {{\n\t\t\tlevel > 0\n'
                f'\t\t\tOR = {{\n{ors}\t\t\t}}\n\t\t\tNOR = {{\n{excl}\t\t\t}}\n'
                '\t\t\tprivate_ownership_fraction >= 0.125\n\t\t}\n\t\tadd = pmr_pc_levels\n\t}\n}\n\n')
    # The owners chart (Pat 15:33Z): levels by who owns them, in the same building groups. The ownership triggers
    # are comparisons, so each building's shares are read to the nearest eighth of its levels. Both charts skip
    # buildings still at level 0: the ownership triggers need a built building (1.14.5 error.log, "ownership_fraction
    # requires the building to be built", a building under its first construction).
    def eighths(trigger):
        cuts = [(k + 0.5) / 8 for k in range(8)]
        out = ''
        for k, c in enumerate(cuts):
            out += (f'\t{"else_if" if k else "if"} = {{\n\t\tlimit = {{ {trigger} < {c:g} }}\n'
                    f'\t\tmultiply = {k / 8:g}\n\t}}\n')
        return out
    out += ('# Building scope. Its levels owned by any government, and by the building itself (local owners), to the\n'
            '# nearest eighth of its levels; the rest belong to ownership buildings (Manor Houses, Financial Districts,\n'
            '# company headquarters).\n'
            'pmr_po_gov_levels = {\n\tvalue = this.level\n' + eighths('country_ownership_fraction') + '}\n\n'
            'pmr_po_self_levels = {\n\tvalue = this.level\n' + eighths('self_ownership_fraction') + '}\n\n'
            'pmr_po_rest_levels = {\n\tvalue = this.level\n\tsubtract = pmr_po_gov_levels\n'
            '\tsubtract = pmr_po_self_levels\n\tmin = 0\n}\n\n'
            '# Country scope. Those levels summed over the buildings of the five priority groups.\n')
    ors = ''.join(f'\t\t\t\tis_building_group = {bg}\n' for *_r, bgs in GROUPS for bg in bgs)
    for k in ('gov', 'self', 'rest'):
        out += (f'pmr_po_{k} = {{\n\tvalue = 0\n\tevery_scope_building = {{\n\t\tlimit = {{\n\t\t\tlevel > 0\n'
                f'\t\t\tOR = {{\n{ors}\t\t\t}}\n\t\t\tNOR = {{\n{excl}\t\t\t}}\n\t\t}}\n'
                f'\t\tadd = pmr_po_{k}_levels\n\t}}\n}}\n\n')
    return out


def sguis():
    out = ('# Investment priorities. Country scope; scope:step is the coin clicked (0, 25 .. 100), passed from\n'
           f'# {OWN_GUI} with MakeScopeValue.\n\n')
    out += (f'# A row may change while its law leaves it open (LAW_ROWS) and it is not cooling down: like a tariff, a\n'
            f'# change starts {GRACE_DAYS} days to think again, then the row is locked until {COOLDOWN_DAYS} days after the '
            f'change\n# (Pat 19:34Z). pmr_ipw_wk_<g> counts the weeks left for the panel (pmr_ipw_weekly).\n')
    for g, *_r in GROUPS:
        v = VAR.format(g)
        steps = '\t\t\telse_'.join(
            f'if = {{\n\t\t\t\tlimit = {{ scope:step = {s} }}\n\t\t\t\tset_variable = {{ name = {v} value = {s} }}\n\t\t\t}}\n'
            for s in STEPS)
        changed = (f'OR = {{\n\t\t\t\tAND = {{ has_variable = {v} NOT = {{ var:{v} = scope:step }} }}\n'
                   f'\t\t\t\tAND = {{ NOT = {{ has_variable = {v} }} NOT = {{ scope:step = 0 }} }}\n\t\t\t}}')
        out += (f'{v}_sgui = {{\n\tscope = country\n\tsaved_scopes = {{ step }}\n'
                f'\tis_valid = {{\n\t\tNOT = {{ pmr_ipw_law_lock_{g} = yes }}\n'
                f'\t\tOR = {{\n\t\t\tNOT = {{ has_variable = pmr_ipw_cd_{g} }}\n\t\t\thas_variable = pmr_ipw_grace_{g}\n\t\t}}\n\t}}\n'
                f'\teffect = {{\n\t\tif = {{\n\t\t\tlimit = {{\n\t\t\t{changed}\n\t\t\t}}\n'
                f'\t\t\tset_variable = {ON}\n\t\t\t{steps}'
                f'\t\t\tif = {{\n\t\t\t\tlimit = {{ NOT = {{ has_variable = pmr_ipw_cd_{g} }} }}\n'
                f'\t\t\t\tset_variable = {{ name = pmr_ipw_cd_{g} value = 1 days = {COOLDOWN_DAYS} }}\n'
                f'\t\t\t\tset_variable = {{ name = pmr_ipw_grace_{g} value = 1 days = {GRACE_DAYS} }}\n'
                f'\t\t\t\tset_variable = {{ name = pmr_ipw_wk_{g} value = {COOLDOWN_WEEKS} }}\n\t\t\t}}\n'
                '\t\t\tdebug_log = "PMR;rec=PRIORITY;date=[TimeKeeper.GetCurrentDate.GetString];'
                f'country=[THIS.GetCountry.GetNameNoFormatting];group={g};value=[THIS.Var(\'{v}\').GetValue|0]"\n'
                '\t\t}\n\t}\n}\n\n')
    notches = '\t\telse_'.join(
        f'if = {{\n\t\t\tlimit = {{ scope:step = {n} }}\n\t\t\tset_variable = {{ name = pmr_fd_i value = {n} }}\n'
        f'\t\t\tset_variable = {{ name = pmr_fd value = {n - (FD_NOTCHES + 1) // 2} }}\n\t\t}}\n'
        for n in range(1, FD_NOTCHES + 1))
    out += ('# Foreign or domestic investment (Pat 15:34Z). Country scope; scope:step is the notch clicked, 1 (strongly\n'
            f'# foreign) .. {FD_NOTCHES} (strongly domestic). pmr_fd is the notch less the middle one, read by the ai_value of\n'
            '# every investable building type in the country\'s states (pmr_ai_value_<b>).\n'
            f'pmr_fd_sgui = {{\n\tscope = country\n\tsaved_scopes = {{ step }}\n\teffect = {{\n\t\t{notches}'
            '\t\tdebug_log = "PMR;rec=FOCUS;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
            'notch=[THIS.Var(\'pmr_fd_i\').GetValue|0];bias=[THIS.Var(\'pmr_fd\').GetValue|0]"\n\t}\n}\n\n')
    out += ('# The contributors chart, recounted whenever the Private tab is opened (and weekly); opening the tab also\n'
            '# starts the weekly clock if it is not running.\n'
            'pmr_pc_refresh_sgui = {\n\tscope = country\n\teffect = {\n\t\tpmr_pc_record = yes\n\t\tpmr_pi_v2 = yes\n'
            '\t\tif = {\n\t\t\tlimit = { is_player = yes }\n\t\t\tset_global_variable = { name = pmr_player value = ROOT }\n\t\t}\n'
            '\t\tpmr_pi_start_clock = yes\n\t}\n}\n\n')
    laws = sorted(set(POLICY_LAWS.values()))
    any_law = 'OR = { ' + ' '.join(f'has_law_or_variant = law_type:{law}' for law in laws) + ' }'
    out += ('# Policy cards. is_shown: the country may hold a policy at all (Interventionism or Laissez-faire, Pat\n'
            '# 16:06Z), or this one under its law; is_valid: its law, its technology, and not already held.\n\n'
            f'pmr_policy_available_sgui = {{\n\tscope = country\n\tis_shown = {{ {any_law} }}\n'
            '\teffect = { }\n}\n\n')
    for i, (k, *_rest) in enumerate(POLICIES, 1):
        law = f'has_law_or_variant = law_type:{POLICY_LAWS[k]}'
        tech = f'\t\thas_technology_researched = {POLICY_TECH[k]}\n' if k in POLICY_TECH else ''
        out += (f'pmr_policy_{k}_sgui = {{\n\tscope = country\n'
                f'\tis_shown = {{ {law} }}\n'
                f'\tis_valid = {{\n\t\t{law}\n{tech}\t\tNOT = {{ has_modifier = pmr_policy_{k} }}\n'
                '\t\tNOT = { has_variable = pmr_policy_lock_m }\n'
                '\t\tauthority >= pmr_policy_cost_net\n\t}\n'
                f'\teffect = {{\n\t\tpmr_policy_adopt_{k} = yes\n\t}}\n}}\n\n')
    drop_all = ''.join(f'\t\tif = {{\n\t\t\tlimit = {{ has_modifier = pmr_policy_{k} }}\n\t\t\tremove_modifier = pmr_policy_{k}\n\t\t}}\n'
                       for k, *_r in POLICIES)
    out += ('# The X on the held policy\'s card (Pat 20:08Z), once its 5 years are up: ends the policy and its authority cost.\n'
            'pmr_policy_cancel_sgui = {\n\tscope = country\n\tis_shown = { has_variable = pmr_policy }\n'
            '\tis_valid = { NOT = { has_variable = pmr_policy_lock_m } }\n\teffect = {\n' + drop_all +
            '\t\tpmr_policy_drop = yes\n\t\tpmr_policy_upkeep = yes\n'
            '\t\tdebug_log = "PMR;rec=POLICY;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
            'policy=cancelled"\n\t}\n}\n\n')
    return out


def static_modifiers():
    out = ('# Policy cards on the construction panel\'s Private tab, one at a time, each under its economic system law\n'
           '# (Interventionism or Laissez-faire).\n\n')
    for k, _n, icon, mods, *_r in POLICIES:
        out += f'pmr_policy_{k} = {{\n\ticon = "{icon}"\n' + ''.join(f'\t{m} = {v}\n' for m, v in mods.items()) + '}\n\n'
    out += ('# The authority a held policy uses (Pat 19:34Z), added with multiplier = its cost when adopted, as vanilla\n'
            '# charges patronage (modifier_granted_character_patronage, 00_ep2_04_modifiers.txt).\n'
            'pmr_policy_authority = {\n\ticon = "gfx/interface/icons/topbar/authority_icon.dds"\n'
            '\tcountry_authority_cost_add = 1\n}\n\n')
    out += '# Market Titans: Industrialists approval for each institution the country has (pmr_policy_upkeep).\n\n'
    for inst in TITANS_INSTITUTIONS:
        out += (f'pmr_titans_{inst} = {{\n\ticon = "gfx/interface/icons/law_icons/corporate_state.dds"\n'
                f'\tinterest_group_ig_industrialists_approval_add = {TITANS_APPROVAL}\n}}\n\n')
    return out


def reinvest_effect():
    """Country scope, weekly (pmr_pi.1, Pat 14:28Z), players only. The game keeps no history of the pool's weekly
    income (the budget's Investment Pool Transfer trend is money drawn out for construction), so PMR samples
    investment_pool_income (a country value; its description string is in the 1.14.5 exe) once a week into
    pmr_rw_0 (newest) .. pmr_rw_<N-1>. Each week is a column from zero (Pat 15:33Z: no line over it): pmr_rw_h_<i>
    is its height in rows against the highest week shown, and pmr_rw_b_<i> is 1 once the week is recorded. The
    column is split by the tree chart's shares that week (Pat 14:28Z): pmr_rs_<g>_<i> is the running total of the
    shares of groups 0..g (1 for the last group, 0 when nothing was counted), and pmr_rc_<g>_<i> the height of that
    running total, in rows; the GUI draws the five as bars from the back (the whole column) to the front (the first
    group alone). The monthly series (pmr_ri_*) and the line rows (pmr_rw_lo_*, pmr_rw_hi_*) of earlier versions are
    left alone and no longer drawn."""
    n, ng = RI_WEEKS, len(GROUPS)
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
    fold = ''.join(f'\t\t\tif = {{\n\t\t\t\tlimit = {{ has_variable = pmr_rw_{i} }}\n\t\t\t\tmin = var:pmr_rw_{i}\n\t\t\t}}\n'
                   for i in range(1, n))
    rows = ''.join(
        f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_rw_{i} }}\n'
        f'\t\tset_variable = {{ name = pmr_rw_b_{i} value = 1 }}\n'
        f'\t\tset_variable = {{\n\t\t\tname = pmr_rw_h_{i}\n\t\t\tvalue = {{\n\t\t\t\tvalue = 0\n'
        f'\t\t\t\tif = {{\n\t\t\t\t\tlimit = {{ var:pmr_rw_max > 0 }}\n'
        f'\t\t\t\t\tvalue = var:pmr_rw_{i}\n\t\t\t\t\tdivide = var:pmr_rw_max\n\t\t\t\t\tmultiply = {RI_ROWS}\n\t\t\t\t}}\n'
        f'\t\t\t}}\n\t\t}}\n'
        + ''.join(f'\t\tset_variable = {{\n\t\t\tname = pmr_rc_{g}_{i}\n\t\t\tvalue = {{\n\t\t\t\tvalue = var:pmr_rw_h_{i}\n'
                  f'\t\t\t\tmultiply = var:pmr_rs_{g}_{i}\n\t\t\t}}\n\t\t}}\n' for g in range(ng))
        + '\t}\n'
        for i in range(n))
    return ('pmr_rw_record = {\n'
            + shift +
            '\tset_variable = {\n\t\tname = pmr_rw_0\n\t\tvalue = {\n\t\t\tvalue = investment_pool_income\n\t\t\tmin = 0\n\t\t}\n\t}\n'
            + shares +
            '\t# the highest week shown (min = X keeps a value at least X)\n'
            '\tset_variable = {\n\t\tname = pmr_rw_max\n\t\tvalue = {\n\t\t\tvalue = var:pmr_rw_0\n' + fold + '\t\t}\n\t}\n'
            + rows +
            '\tdebug_log = "PMR;rec=REINVEST;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
            'weekly=[THIS.Var(\'pmr_rw_0\').GetValue|0];max=[THIS.Var(\'pmr_rw_max\').GetValue|0];'
            'height=[THIS.Var(\'pmr_rw_h_0\').GetValue|1];column_first_group=[THIS.Var(\'pmr_rc_0_0\').GetValue|2]"\n'
            '}\n')


def chart_effect():
    """Country scope. Counts privately owned levels per priority group into pmr_pc_<i> (GROUPS order, read by the
    tree chart by index) and each group's share of them into pmr_pc_share_<i>; and the levels of those groups by
    owner into pmr_po_<i> (OWNERS order) with shares pmr_po_share_<i> (Pat 15:33Z). Companies are told apart by
    company_owned_levels (company scope, a comparison, read by halving steps over the country's companies; it counts
    a company's levels wherever they are); Manor Houses and Financial Districts are what is left, as script cannot
    tell those two apart. Run weekly for players (pmr_pi.1) and whenever the Private tab is opened
    (pmr_pc_refresh_sgui)."""
    sets = ''.join(f'\tset_variable = {{ name = pmr_pc_{i} value = pmr_pc_{g} }}\n' for i, (g, *_r) in enumerate(GROUPS))

    def total_and_shares(prefix, n):
        tot = ''.join(f'\t\t\tadd = var:{prefix}_{i}\n' for i in range(n))
        return (f'\tset_variable = {{\n\t\tname = {prefix}_total\n\t\tvalue = {{\n\t\t\tvalue = 0\n{tot}\t\t}}\n\t}}\n'
                + ''.join(f'\tset_variable = {{\n\t\tname = {prefix}_share_{i}\n\t\tvalue = {{\n\t\t\tvalue = 0\n'
                          f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:{prefix}_total > 0 }}\n\t\t\t\tvalue = var:{prefix}_{i}\n'
                          f'\t\t\t\tdivide = var:{prefix}_total\n\t\t\t}}\n\t\t}}\n\t}}\n' for i in range(n)))
    steps = (512, 256, 128, 64, 32, 16, 8, 4, 2, 1)
    company = ('\tset_variable = { name = pmr_po_2 value = 0 }\n\tevery_company = {\n'
               '\t\troot = { set_variable = { name = pmr_po_x value = 0 } }\n'
               + ''.join(f'\t\troot = {{ set_variable = {{ name = pmr_po_t value = {{ value = var:pmr_po_x add = {st} }} }} }}\n'
                         '\t\tif = {\n\t\t\tlimit = { company_owned_levels >= root.var:pmr_po_t }\n'
                         '\t\t\troot = { set_variable = { name = pmr_po_x value = var:pmr_po_t } }\n\t\t}\n' for st in steps)
               + '\t\troot = { change_variable = { name = pmr_po_2 add = var:pmr_po_x } }\n\t}\n')
    owners = ('\tset_variable = { name = pmr_po_0 value = pmr_po_gov }\n'
              '\tset_variable = { name = pmr_po_1 value = pmr_po_self }\n'
              + company +
              '\tset_variable = {\n\t\tname = pmr_po_3\n\t\tvalue = {\n\t\t\tvalue = pmr_po_rest\n'
              '\t\t\tsubtract = var:pmr_po_2\n\t\t\tmin = 0\n\t\t}\n\t}\n')
    log = ';'.join(f"{g}=[THIS.Var('pmr_pc_{i}').GetValue|1]" for i, (g, *_r) in enumerate(GROUPS))
    log += ';' + ';'.join(f"owner_{k}=[THIS.Var('pmr_po_{i}').GetValue|1]" for i, (k, *_r) in enumerate(OWNERS))
    return ('pmr_pc_record = {\n' + sets + total_and_shares('pmr_pc', len(GROUPS))
            + owners + total_and_shares('pmr_po', len(OWNERS)) +
            '\tdebug_log = "PMR;rec=CONTRIB;date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetCountry.GetNameNoFormatting];{log}"\n'
            '}\n')


def on_actions():
    drop = ''.join(f'\t\tif = {{\n\t\t\tlimit = {{\n\t\t\t\thas_modifier = pmr_policy_{k}\n'
                   f'\t\t\t\tNOT = {{ has_law_or_variant = law_type:{POLICY_LAWS[k]} }}\n\t\t\t}}\n'
                   f'\t\t\tremove_modifier = pmr_policy_{k}\n\t\t\tpmr_policy_drop = yes\n'
                   '\t\t\tdebug_log = "PMR;rec=POLICY;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];policy=dropped"\n'
                   '\t\t}\n' for k, *_r in POLICIES)
    return ('# Appended to vanilla on_actions the documented way, like pmr_on_actions.txt.\n'
            'on_monthly_pulse_country = { on_actions = { pmr_pi_monthly_country } }\n'
            'on_start_expanding_building = { on_actions = { pmr_pi_on_start } }\n\n'
            '# A policy card lasts only while the country keeps its law; an AI country without one picks one it can\n'
            '# afford (Pat 19:34Z). The player\'s weekly clock is restarted here if its chain broke (pmr_pi_start_clock).\n'
            'pmr_pi_monthly_country = {\n\teffect = {\n'
            + drop +
            '\t\tif = {\n\t\t\tlimit = { has_variable = pmr_policy_lock_m }\n'
            '\t\t\tchange_variable = { name = pmr_policy_lock_m add = -1 }\n'
            '\t\t\tif = {\n\t\t\t\tlimit = { var:pmr_policy_lock_m <= 0 }\n\t\t\t\tremove_variable = pmr_policy_lock_m\n\t\t\t}\n\t\t}\n'
            '\t\tpmr_policy_upkeep = yes\n'
            '\t\tpmr_policy_ai_pick = yes\n'
            '\t\tif = {\n\t\t\tlimit = { is_player = yes }\n'
            '\t\t\tset_global_variable = { name = pmr_player value = ROOT }\n'
            '\t\t\tpmr_pi_start_clock = yes\n\t\t}\n'
            '\t}\n}\n\n'
            '# Root = building, a level of it starting construction (the Recent Investments bars).\n'
            'pmr_pi_on_start = {\n\teffect = {\n\t\tpmr_pi_start = yes\n\t}\n}\n')


def upkeep_effect():
    """Country scope, monthly and when a policy is adopted: Market Titans' Industrialists penalty, one modifier
    for each of the institutions Pat named that the country has (Pat 16:06Z)."""
    out = ('# Country scope. Market Titans: one Industrialists approval modifier per institution the country has.\n'
           'pmr_policy_upkeep = {\n')
    for inst in TITANS_INSTITUTIONS:
        m = f'pmr_titans_{inst}'
        out += (f'\tif = {{\n\t\tlimit = {{\n\t\t\thas_modifier = pmr_policy_titans\n\t\t\thas_institution = {inst}\n'
                f'\t\t\tNOT = {{ has_modifier = {m} }}\n\t\t}}\n\t\tadd_modifier = {{ name = {m} }}\n\t}}\n'
                f'\telse_if = {{\n\t\tlimit = {{\n\t\t\thas_modifier = {m}\n\t\t\tNOR = {{\n'
                f'\t\t\t\tAND = {{\n\t\t\t\t\thas_modifier = pmr_policy_titans\n\t\t\t\t\thas_institution = {inst}\n\t\t\t\t}}\n'
                f'\t\t\t}}\n\t\t}}\n\t\tremove_modifier = {m}\n\t}}\n')
    return out + '}\n'


def policy_effects():
    """Country scope. Adopting a policy (the policy window and the AI, Pat 19:34Z): its modifier replaces any other,
    and its authority cost (pmr_policy_cost, by legitimacy now) is fixed in pmr_policy_paid and used while it is held;
    it is then kept POLICY_LOCK_MONTHS months (pmr_policy_lock_m, counted down monthly in on_actions).
    Dropping one when its law goes. An AI country with no policy picks one of those it can afford, at random, each
    month (AI_SKIP aside). The weekly countdown of each priority row's cooldown, for the panel."""
    out = ''
    for i, (k, *_r) in enumerate(POLICIES, 1):
        others = ''.join(f'\tif = {{\n\t\tlimit = {{ has_modifier = pmr_policy_{o} }}\n'
                         f'\t\tremove_modifier = pmr_policy_{o}\n\t}}\n' for o, *_x in POLICIES if o != k)
        out += (f'pmr_policy_adopt_{k} = {{\n{others}'
                '\tif = {\n\t\tlimit = { has_modifier = pmr_policy_authority }\n\t\tremove_modifier = pmr_policy_authority\n\t}\n'
                '\tset_variable = { name = pmr_policy_paid value = pmr_policy_cost }\n'
                '\tadd_modifier = {\n\t\tname = pmr_policy_authority\n\t\tmultiplier = var:pmr_policy_paid\n\t}\n'
                f'\tadd_modifier = {{ name = pmr_policy_{k} }}\n'
                f'\tset_variable = {{ name = pmr_policy value = {i} }}\n'
                f'\tset_variable = {{ name = pmr_policy_lock_m value = {POLICY_LOCK_MONTHS} }}\n'
                '\tpmr_policy_upkeep = yes\n'
                f'\tdebug_log = "PMR;rec=POLICY;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
                f'policy={k};authority=[THIS.Var(\'pmr_policy_paid\').GetValue|0]"\n}}\n\n')
    # A law change that drops the policy also ends its lock (the drop is not the player's choice).
    out += ('pmr_policy_drop = {\n\tremove_variable = pmr_policy\n'
            '\tif = {\n\t\tlimit = { has_variable = pmr_policy_lock_m }\n\t\tremove_variable = pmr_policy_lock_m\n\t}\n'
            '\tif = {\n\t\tlimit = { has_modifier = pmr_policy_authority }\n\t\tremove_modifier = pmr_policy_authority\n\t}\n'
            '\tif = {\n\t\tlimit = { has_variable = pmr_policy_paid }\n\t\tremove_variable = pmr_policy_paid\n\t}\n}\n\n')

    def can(k):
        tech = f' has_technology_researched = {POLICY_TECH[k]}' if k in POLICY_TECH else ''
        return f'has_law_or_variant = law_type:{POLICY_LAWS[k]}{tech} authority >= pmr_policy_cost'
    picks = [k for k, *_r in POLICIES if k not in AI_SKIP]
    out += ('pmr_policy_ai_pick = {\n\tif = {\n\t\tlimit = {\n\t\t\tis_player = no\n'
            '\t\t\tNOT = { has_variable = pmr_policy }\n\t\t\tOR = {\n'
            + ''.join(f'\t\t\t\tAND = {{ {can(k)} }}\n' for k in picks)
            + '\t\t\t}\n\t\t}\n\t\trandom_list = {\n'
            + ''.join(f'\t\t\t1 = {{\n\t\t\t\ttrigger = {{ {can(k)} }}\n\t\t\t\tpmr_policy_adopt_{k} = yes\n\t\t\t}}\n'
                      for k in picks)
            + '\t\t}\n\t}\n}\n\n')
    out += 'pmr_ipw_weekly = {\n'
    for g, *_r in GROUPS:
        wk = f'pmr_ipw_wk_{g}'
        out += (f'\tif = {{\n\t\tlimit = {{ has_variable = {wk} }}\n\t\tchange_variable = {{ name = {wk} add = -1 }}\n'
                f'\t\tif = {{\n\t\t\tlimit = {{\n\t\t\t\tOR = {{\n\t\t\t\t\tvar:{wk} <= 0\n'
                f'\t\t\t\t\tNOT = {{ has_variable = pmr_ipw_cd_{g} }}\n\t\t\t\t}}\n\t\t\t}}\n'
                f'\t\t\tremove_variable = {wk}\n\t\t}}\n\t}}\n')
    return out + '}\n'


def law_triggers():
    """Country scope. pmr_ipw_law_lock_<g>: the economic system law locks this priority row (LAW_ROWS, Pat 19:34Z)."""
    out = ('# Country scope. True while the economic system law locks the priority row: Laissez-faire locks every row,\n'
           '# Agrarianism every row but Agriculture and Resources (Pat 19:34Z).\n')
    for g, *_r in GROUPS:
        laws = [law for law, rows in LAW_ROWS.items() if g not in rows]
        body = (' '.join(f'has_law_or_variant = law_type:{law}' for law in laws)) if laws else 'always = no'
        out += f'pmr_ipw_law_lock_{g} = {{\n\tOR = {{ {body} }}\n}}\n\n'
    return out


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
            '\t\t\tpmr_pc_record = yes\n\t\t\tpmr_rw_record = yes\n\t\t\tpmr_ipw_weekly = yes\n'
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


def retool_types(game, out):
    """(retool type without building_, priority group index, construction points a level, parent without building_)
    for every retool building generate.py wrote (Pat 15:33Z: retooling counts in the bars, under the parent's
    group, at the retool building's cost). Empty in the standalone run."""
    if not out:
        return []
    common = os.path.join(out, 'common')
    text = open(os.path.join(common, 'buildings', 'pmr_retool_buildings.txt'), encoding='utf-8-sig').read()
    costs = dict(re.findall(r'^pmr_retool_cost_([a-z_0-9]+) = ([0-9.]+)',
                            open(os.path.join(common, 'script_values', 'pmr_values.txt'), encoding='utf-8-sig').read(),
                            re.M))
    btype, parent = building_groups(game)
    index = {k: i for i, (k, *_r) in enumerate(GROUPS)}
    res = []
    for k, _s, _o, _c in top_blocks(text):
        m = re.fullmatch(r'building_pmr_retool_gov_(.+)', k) or re.fullmatch(r'building_pmr_retool_(.+)_\d+', k)
        if not m:
            continue
        b = m.group(1)
        g = group_of('building_' + b, btype, parent)
        if not g or b not in costs:
            fail('pmr_retool_buildings.txt', f'{k}: no priority group or no pmr_retool_cost_{b}')
        res.append((k[len('building_'):], index[g], costs[b], b))
    if not res:
        fail('pmr_retool_buildings.txt', 'found no retool buildings')
    return res


def invest_effects(types, retools):
    """The Recent Investments bars (Pat 14:28Z, reworked 15:33Z). The game lists previous investments only as text,
    so PMR keeps its own record: when a level starts (on_start_expanding_building) the building's levels are put on
    the state by building type: its level (pmr_iv_l_<b>), the player's levels (pmr_iv_o_<b>), every government's
    (pmr_iv_g_<b>) and the building's own, its local owners' (pmr_iv_s_<b>). When a level completes (PMR's
    on_building_built and on_building_expanded, before anything else) the changes say who built it. Counted: every
    level completed in the player's states, and every level abroad that raised the player's levels (Pat 15:33Z: so
    government retooling and building count too), retool levels under the group of the building they retool, at
    their own cost. Who built it: the building's own levels went up, local owners; a government's and the player's,
    the player's government; the player's alone, the player's investors; otherwise foreign investors (or a foreign
    government). levels_owned_by_country counts a country's government and its investors; the fractions are any
    government's and the building's own; all are comparisons only, so pmr_pi_read finds them by halving steps."""
    steps = (128, 64, 32, 16, 8, 4, 2, 1)
    own = ''.join(
        f'\tstate = {{ set_variable = {{ name = pmr_iv_t value = {{ value = var:pmr_iv_x add = {s} }} }} }}\n'
        f'\tif = {{\n\t\tlimit = {{ levels_owned_by_country = {{ target = global_var:pmr_player value >= state.var:pmr_iv_t }} }}\n'
        f'\t\tstate = {{ set_variable = {{ name = pmr_iv_x value = var:pmr_iv_t }} }}\n\t}}\n' for s in steps)

    def by_fraction(trigger, var):
        return ''.join(
            f'\t\tstate = {{\n\t\t\tset_variable = {{\n\t\t\t\tname = pmr_iv_t\n\t\t\t\tvalue = {{\n\t\t\t\t\tvalue = var:{var}\n'
            f'\t\t\t\t\tadd = {s - 0.5:g}\n\t\t\t\t\tdivide = scope:pmr_iv_b.level\n\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n'
            f'\t\tif = {{\n\t\t\tlimit = {{ {trigger} >= state.var:pmr_iv_t }}\n'
            f'\t\t\tstate = {{ change_variable = {{ name = {var} add = {s} }} }}\n\t\t}}\n' for s in steps)
    read = ('# Building scope. On its state: pmr_iv_x = the player\'s levels in it (government and investors),\n'
            '# pmr_iv_y = levels owned by any government, pmr_iv_z = levels the building owns itself, all to 255.\n'
            'pmr_pi_read = {\n\tsave_scope_as = pmr_iv_b\n'
            '\tstate = {\n\t\tset_variable = { name = pmr_iv_x value = 0 }\n\t\tset_variable = { name = pmr_iv_y value = 0 }\n'
            '\t\tset_variable = { name = pmr_iv_z value = 0 }\n\t}\n'
            + own +
            '\tif = {\n\t\tlimit = {\n\t\t\tlevel > 0\n\t\t\tcountry_ownership_fraction > 0\n\t\t}\n'
            + by_fraction('country_ownership_fraction', 'pmr_iv_y') + '\t}\n'
            '\tif = {\n\t\tlimit = {\n\t\t\tlevel > 0\n\t\t\tself_ownership_fraction > 0\n\t\t}\n'
            + by_fraction('self_ownership_fraction', 'pmr_iv_z') + '\t}\n}\n\n')

    def dispatch(effect, with_gc):
        def call(k, s, g, c, t):
            args = f'S = {s} G = {g} C = {c} T = {t}' if with_gc else f'S = {s}'
            return (f'\t\t{"else_if" if k else "if"} = {{\n\t\t\tlimit = {{ is_building_type = building_{s} }}\n'
                    f'\t\t\t{effect} = {{ {args} }}\n\t\t}}\n')
        out = ''.join(call(k, s, g, c, s) for k, (s, g, c) in enumerate(types))
        if retools:
            inner = ''.join('\t' + line + '\n' for line in
                            ''.join(call(k, s, g, c, t) for k, (s, g, c, t) in enumerate(retools)).rstrip('\n').split('\n'))
            out += ('\t\telse_if = {\n\t\t\tlimit = {\n\t\t\t\tOR = {\n\t\t\t\t\tis_building_group = bg_pmr_retool\n'
                    '\t\t\t\t\tis_building_group = bg_pmr_retool_abroad\n'
                    '\t\t\t\t\tis_building_group = bg_pmr_retool_gov\n\t\t\t\t}\n\t\t\t}\n' + inner + '\t\t}\n')
        return out
    where = ('date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
             'state=[THIS.GetState.GetNameNoFormatting];building=$S$')
    nums = ("levels=[THIS.Var('pmr_iv_dl').GetValue|0];player_levels=[THIS.Var('pmr_iv_d').GetValue|0];"
            "government_levels=[THIS.Var('pmr_iv_dg').GetValue|0];local_levels=[THIS.Var('pmr_iv_ds').GetValue|0];"
            "points=[THIS.Var('pmr_iv_p').GetValue|0]")
    kinds = [k for k, *_r in WHO]

    def log(kind):
        return f'\t\t\tstate = {{ debug_log = "PMR;rec=INVEST;{where};kind={kind};{nums}" }}\n'
    ng = len(GROUPS)
    snap = ('# Building scope, $S$ = its type without building_. Its levels now, until one completes.\n'
            'pmr_pi_snap = {\n\tpmr_pi_read = yes\n\tstate = {\n'
            '\t\tset_variable = { name = pmr_iv_l_$S$ value = scope:pmr_iv_b.level }\n'
            '\t\tset_variable = { name = pmr_iv_o_$S$ value = var:pmr_iv_x }\n'
            '\t\tset_variable = { name = pmr_iv_g_$S$ value = var:pmr_iv_y }\n'
            '\t\tset_variable = { name = pmr_iv_s_$S$ value = var:pmr_iv_z }\n\t}\n}\n\n')
    add = ('# Country scope (the player). Adds the state variable $A$ of the level just counted (scope:pmr_iv_s) to $V$.\n'
           'pmr_pi_add = {\n\tif = {\n\t\tlimit = { NOT = { has_variable = $V$ } }\n\t\tset_variable = { name = $V$ value = 0 }\n\t}\n'
           '\tchange_variable = { name = $V$ add = scope:pmr_iv_s.var:$A$ }\n}\n\n')
    reset = ('# Country scope (the player). The record before this version counted only private construction: start\n'
             '# again once (from the first count, or when the Private tab is opened).\n'
             'pmr_pi_v2 = {\n\tif = {\n\t\tlimit = { NOT = { has_variable = pmr_iv_v2 } }\n'
             + ''.join(f'\t\tset_variable = {{ name = {v} value = 0 }}\n' for v in
                       [f'pmr_iv_pts_{g}' for g in range(ng)] + [f'pmr_iv_w_{w}' for w in range(len(WHO))]
                       + ['pmr_iv_dom', 'pmr_iv_for', 'pmr_iv_tot'])
             + '\t\tset_variable = pmr_iv_v2\n\t}\n}\n\n')
    who = ''.join(f'\t\t\t{"else_if" if w else "if"} = {{\n\t\t\t\tlimit = {{ state = {{ var:pmr_iv_w = {w} }} }}\n'
                  f'\t\t\t\tglobal_var:pmr_player = {{ pmr_pi_add = {{ V = pmr_iv_w_{w} A = pmr_iv_p }} }}\n'
                  + log(kinds[w]).replace('\t\t\t', '\t\t\t\t', 1) + '\t\t\t}\n' for w in range(len(WHO)))
    done = ('# Building scope, a level of it just completed; $S$ as above, $G$ its priority group (GROUPS order), $C$ the\n'
            '# construction points of a level, $T$ the building type it counts under (a retool building\'s parent).\n'
            'pmr_pi_done = {\n\tpmr_pi_read = yes\n'
            '\t# a building\'s first level: nothing was there before it\n'
            '\tif = {\n\t\tlimit = { level <= 1 }\n\t\tstate = {\n'
            '\t\t\tset_variable = { name = pmr_iv_l_$S$ value = 0 }\n'
            '\t\t\tset_variable = { name = pmr_iv_o_$S$ value = 0 }\n\t\t\tset_variable = { name = pmr_iv_g_$S$ value = 0 }\n'
            '\t\t\tset_variable = { name = pmr_iv_s_$S$ value = 0 }\n\t\t}\n\t}\n'
            '\tif = {\n\t\tlimit = { state = { NOT = { has_variable = pmr_iv_l_$S$ } } }\n'
            f'\t\tstate = {{ debug_log = "PMR;rec=INVEST_MISS;{where}" }}\n\t}}\n'
            '\telse = {\n\t\tstate = {\n'
            + ''.join(f'\t\t\tset_variable = {{\n\t\t\t\tname = {n}\n\t\t\t\tvalue = {{\n\t\t\t\t\tvalue = {now}\n'
                      f'\t\t\t\t\tsubtract = var:{was}_$S$\n\t\t\t\t}}\n\t\t\t}}\n'
                      for n, now, was in (('pmr_iv_dl', 'scope:pmr_iv_b.level', 'pmr_iv_l'), ('pmr_iv_d', 'var:pmr_iv_x', 'pmr_iv_o'),
                                          ('pmr_iv_dg', 'var:pmr_iv_y', 'pmr_iv_g'), ('pmr_iv_ds', 'var:pmr_iv_z', 'pmr_iv_s')))
            + '\t\t\tset_variable = {\n\t\t\t\tname = pmr_iv_p\n\t\t\t\tvalue = {\n\t\t\t\t\tvalue = var:pmr_iv_dl\n\t\t\t\t\tmultiply = $C$\n\t\t\t\t}\n\t\t\t}\n'
            '\t\t\t# who built it (WHO order)\n'
            f'\t\t\tset_variable = {{ name = pmr_iv_w value = {kinds.index("foreign")} }}\n'
            f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:pmr_iv_ds >= 1 }}\n\t\t\t\tset_variable = {{ name = pmr_iv_w value = {kinds.index("local")} }}\n\t\t\t}}\n'
            f'\t\t\telse_if = {{\n\t\t\t\tlimit = {{\n\t\t\t\t\tvar:pmr_iv_dg >= 1\n\t\t\t\t\tvar:pmr_iv_d >= 1\n\t\t\t\t}}\n'
            f'\t\t\t\tset_variable = {{ name = pmr_iv_w value = {kinds.index("gov")} }}\n\t\t\t}}\n'
            f'\t\t\telse_if = {{\n\t\t\t\tlimit = {{\n\t\t\t\t\tvar:pmr_iv_dg < 1\n\t\t\t\t\tvar:pmr_iv_d >= 1\n\t\t\t\t}}\n'
            f'\t\t\t\tset_variable = {{ name = pmr_iv_w value = {kinds.index("investors")} }}\n\t\t\t}}\n'
            '\t\t\tsave_scope_as = pmr_iv_s\n\t\t}\n'
            '\t\t# counted: a level in the player\'s states, or one abroad that raised the player\'s levels\n'
            '\t\tif = {\n\t\t\tlimit = {\n\t\t\t\tstate = { var:pmr_iv_dl >= 1 }\n'
            '\t\t\t\tOR = {\n\t\t\t\t\towner = global_var:pmr_player\n\t\t\t\t\tstate = { var:pmr_iv_d >= 1 }\n\t\t\t\t}\n\t\t\t}\n'
            '\t\t\tglobal_var:pmr_player = {\n\t\t\t\tpmr_pi_v2 = yes\n'
            '\t\t\t\tpmr_pi_add = { V = pmr_iv_pts_$G$ A = pmr_iv_p }\n'
            '\t\t\t\tpmr_pi_add = { V = pmr_iv_bt_$T$ A = pmr_iv_p }\n'
            '\t\t\t\tpmr_pi_add = { V = pmr_iv_bl_$T$ A = pmr_iv_dl }\n\t\t\t}\n'
            '\t\t\tif = {\n\t\t\t\tlimit = { owner = global_var:pmr_player }\n'
            '\t\t\t\tglobal_var:pmr_player = { pmr_pi_add = { V = pmr_iv_dom A = pmr_iv_p } }\n\t\t\t}\n'
            '\t\t\telse = {\n\t\t\t\tglobal_var:pmr_player = { pmr_pi_add = { V = pmr_iv_for A = pmr_iv_p } }\n\t\t\t}\n'
            + who +
            '\t\t\tglobal_var:pmr_player = { pmr_pi_shares = yes }\n'
            '\t\t}\n'
            '\t\telse = {\n' + log('not_counted') + '\t\t}\n'
            '\t}\n'
            '\t# the next level of the same construction starts from here\n'
            '\tstate = {\n\t\tset_variable = { name = pmr_iv_l_$S$ value = scope:pmr_iv_b.level }\n'
            '\t\tset_variable = { name = pmr_iv_o_$S$ value = var:pmr_iv_x }\n'
            '\t\tset_variable = { name = pmr_iv_g_$S$ value = var:pmr_iv_y }\n'
            '\t\tset_variable = { name = pmr_iv_s_$S$ value = var:pmr_iv_z }\n\t}\n}\n\n')
    tot = ''.join(f'\t\t\tadd = var:pmr_iv_pts_{g}\n' for g in range(ng))

    def share(name, var):
        return (f'\t\tset_variable = {{\n\t\t\tname = {name}\n\t\t\tvalue = {{\n\t\t\t\tvalue = var:{var}\n'
                '\t\t\t\tdivide = var:pmr_iv_tot\n\t\t\t}\n\t\t}\n')
    shares_fx = ('# Country scope (the player). Each group\'s share of the construction points counted (pmr_iv_gs_<g>), the\n'
                 '# domestic and foreign shares, and each builder\'s (pmr_iv_ws_<w>, WHO order).\n'
                 'pmr_pi_shares = {\n'
                 f'\tset_variable = {{\n\t\tname = pmr_iv_tot\n\t\tvalue = {{\n\t\t\tvalue = 0\n{tot}\t\t}}\n\t}}\n'
                 '\tif = {\n\t\tlimit = { var:pmr_iv_tot > 0 }\n'
                 + ''.join(share(f'pmr_iv_gs_{g}', f'pmr_iv_pts_{g}') for g in range(ng))
                 + share('pmr_iv_dsh', 'pmr_iv_dom') + share('pmr_iv_fsh', 'pmr_iv_for')
                 + ''.join(share(f'pmr_iv_ws_{w}', f'pmr_iv_w_{w}') for w in range(len(WHO)))
                 + '\t}\n}\n\n')
    hooks = ('# Building scope (on_start_expanding_building, every country\'s): note the levels of a counted type that\n'
             '# has levels already (a new building\'s first level needs no note).\n'
             'pmr_pi_start = {\n\tif = {\n\t\tlimit = {\n\t\t\thas_global_variable = pmr_player\n\t\t\tlevel > 0\n\t\t}\n'
             + dispatch('pmr_pi_snap', False) +
             '\t}\n}\n\n'
             '# Building scope (PMR\'s on_building_built and on_building_expanded, every country\'s): a level completed\n'
             '# in the player\'s states, or in a building the player owns levels in.\n'
             'pmr_pi_on_done = {\n\tif = {\n\t\tlimit = {\n\t\t\thas_global_variable = pmr_player\n'
             '\t\t\tOR = {\n\t\t\t\towner = global_var:pmr_player\n'
             '\t\t\t\tlevels_owned_by_country = { target = global_var:pmr_player value >= 1 }\n\t\t\t}\n\t\t}\n'
             + dispatch('pmr_pi_done', True) +
             '\t}\n}\n')
    return read + snap + add + reset + shares_fx + done + hooks   # an effect is defined before its first use


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
                '\t\t# PMR: the economic policy windows, one per law\n\t\tblockoverride "map_modes_button" {\n'
                + ''.join(f'\t\t\tpmr_policy_window_{law} = {{}}\n' for law in policy_laws()) +
                '\t\t}\n\n\t\t#TOP\n\t\tblockoverride "fixed_top"\n', where)

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
    on (Pat 13:05Z): two textboxes in the selector's divider block, its own money text hidden. The coins show the
    priority as it counts now and are disabled while the law locks the row or it is cooling down (Pat 19:34Z); each
    coin's tooltip then says why."""
    v = VAR.format(g)
    cur = f"{COUNTRY}.MakeScope.ScriptValue('pmr_ipw_now_{g}')"
    valid = f"GetScriptedGui('{v}_sgui').IsValid(GuiScope.SetRoot({COUNTRY}.MakeScope).End)"
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
        out += (f'{ind}\tblockoverride "button_{n}_click" {{\n{ind}\t\tonclick = "[{execute(s)}]"\n'
                f'{ind}\t\tenabled = "[{valid}]"\n{ind}\t}}\n'
                f'{ind}\tblockoverride "is_clickable_alpha_{n}" {{\n{ind}\t\talpha = "[TransparentIfFalse({valid})]"\n{ind}\t}}\n'
                f'{ind}\tblockoverride "tooltip_{n}" {{\n{ind}\t\ttooltip = "PMR_IPW_COIN_{g}_{s}"\n{ind}\t}}\n'
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
    """The weekly re-investment in vanilla's graph frame (v3_plotline, as the GDP graph; Pat 04:50Z, weekly since
    14:28Z). GUI plot lines only take the engine's own trends, so each week (pmr_rw_<i>, 0 = newest, rightmost) is a
    column from zero, split by the tree chart's shares (pmr_rc_<g>_<i>, reinvest_effect) in the groups' colours.
    Pat 15:33Z: no line over the columns, and "No historical data" until the first week is recorded."""
    var = lambda name: f"{COUNTRY}.MakeScope.Var('{name}').GetValue"
    fp = lambda x: f"'(CFixedPoint){x}'"
    w, h = RI_WEEKS * RI_COL_W, RI_ROWS * RI_ROW_H
    i2, i3 = ind + '\t\t', ind + '\t\t\t'
    columns, hover = '', ''
    for c in range(RI_WEEKS):
        i = RI_WEEKS - 1 - c
        for gi in range(len(GROUPS) - 1, -1, -1):
            columns += bar(i2, c * RI_COL_W, 0, RI_COL_W - 1, h, f"FixedPointToFloat({var(f'pmr_rc_{gi}_{i}')})",
                           RI_ROWS, GROUPS[gi][3], 'vertical', f"GreaterThan_CFixedPoint({var(f'pmr_rc_{gi}_{i}')}, {fp(0)})")
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
            + bo('extra_plotlines', columns + hover)
            + bo('maxvalue', f'{ind}\t\traw_text = "@money![{var("pmr_rw_max")}|K]"\n')
            + bo('minvalue', f'{ind}\t\traw_text = "@money!0"\n')
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


def tree_chart(ind, items, prefix, tooltip, caption, empty):
    """A tree chart as vanilla's v3_treemapchart draws it, with a legend beside it. The game has no list of the
    pool's sources the GUI could chart (1.14.5 exe: only the GetInvestmentPoolChangeFromInvestmentBreakdown text),
    so the tiles are building levels (<prefix>_<i>, chart_effect) and the game's list in money is the tooltip.
    The tiles come from vanilla's repeated-item datamodel; each tile finds its item by its index in it, and takes
    its pop type's colour (Pat 15:33Z: the game's palette). items: (name loc key, pop type, colour, row tooltip)."""
    n = len(items)
    idx = 'PdxGuiWidget.GetIndexInDataModel'
    pidx = 'PdxGuiWidget.AccessParent.GetIndexInDataModel'

    def chain(fn, at, vals):
        out = vals[-1]
        for i in range(len(vals) - 2, -1, -1):
            out = f"{fn}(EqualTo_int32({at}, '(int32){i}'), {vals[i]}, {out})"
        return out
    color = chain('Select_CVector4f', idx, [f"GetPopType('{pop}').GetColor" for _k, pop, _c, _t in items])
    label = chain('Select_CString', pidx, [f"Localize('{k}')" for k, *_r in items])
    value = f"FixedPointToFloat({COUNTRY}.MakeScope.Var(Concatenate('{prefix}_', ToString_int32({idx}))).GetValue)"
    has = f"GreaterThan_CFixedPoint({COUNTRY}.MakeScope.Var('{prefix}_total').GetValue, '(CFixedPoint)0')"
    i1, i2, i3, i4, i5 = (ind + '\t' * k for k in range(1, 6))
    rows = ''
    for i, (k, _pop, (r, gg, b), tt) in enumerate(items):
        rows += (f'{i2}widget = {{\n{i3}size = {{ 260 26 }}\n{i3}tooltip = "{tt}"\n{i3}using = tooltip_above\n'
                 f'{i3}icon = {{\n{i4}parentanchor = vcenter\n{i4}size = {{ 18 18 }}\n'
                 f'{i4}texture = "gfx/interface/piechart/piechart_legend.dds"\n{i4}color = {{ {r} {gg} {b} 1 }}\n{i3}}}\n'
                 f'{i3}textbox = {{\n{i4}parentanchor = vcenter\n{i4}position = {{ 26 0 }}\n{i4}size = {{ 180 24 }}\n'
                 f'{i4}align = left|nobaseline\n{i4}elide = right\n{i4}text = "{k}"\n{i3}}}\n'
                 f'{i3}textbox = {{\n{i4}parentanchor = right|vcenter\n{i4}autoresize = yes\n{i4}align = right|nobaseline\n'
                 f'{i4}raw_text = "#v [{COUNTRY}.MakeScope.Var(\'{prefix}_share_{i}\').GetValue|0%]#!"\n{i3}}}\n{i2}}}\n')
    return (f'{ind}widget = {{\n{i1}parentanchor = hcenter\n{i1}size = {{ 540 204 }}\n'
            f'{i1}tooltip = "{tooltip}"\n{i1}using = tooltip_above\n'
            f'{i1}textbox = {{\n{i2}visible = "[Not({has})]"\n{i2}parentanchor = center\n{i2}autoresize = yes\n'
            f'{i2}align = hcenter|nobaseline\n{i2}text = "{empty}"\n{i1}}}\n'
            f'{i1}container = {{\n{i2}visible = "[{has}]"\n{i2}position = {{ 40 18 }}\n'
            f'{i2}treemapchart = {{\n{i3}parentanchor = center\n{i3}size = {{ 200 170 }}\n'
            f'{i3}datamodel = "[DataModelRepeatedItem(\'(int32){n}\')]"\n'
            f'{i3}item = {{\n{i4}treemapslice = {{\n'
            f'{i5}texture = "gfx/interface/treemapchart/treemapchart.dds"\n'
            f'{i5}value = "[{value}]"\n{i5}color = "[{color}]"\n'
            f'{i5}tooltip = "{tooltip}"\n'
            f'{i5}textbox = {{\n{i5}\tsize = {{ 100% 100% }}\n{i5}\talign = center|nobaseline\n{i5}\tmargin = {{ 4 4 }}\n'
            f'{i5}\tusing = fontsize_small\n{i5}\tmultiline = yes\n{i5}\telide = right\n{i5}\talwaystransparent = yes\n'
            f'{i5}\traw_text = "#bold [{label}]#!"\n{i5}}}\n'
            f'{i4}}}\n{i3}}}\n{i2}}}\n'
            f'{i2}icon = {{\n{i3}texture = "gfx/interface/treemapchart/treemapchart_frame.dds"\n{i3}parentanchor = center\n'
            f'{i3}size = {{ 124% 110% }}\n{i2}}}\n{i1}}}\n'
            f'{i1}flowcontainer = {{\n{i2}visible = "[{has}]"\n{i2}position = {{ 270 18 }}\n{i2}direction = vertical\n{i2}spacing = 4\n'
            f'{i2}textbox = {{\n{i3}autoresize = yes\n{i3}align = left|nobaseline\n{i3}using = fontsize_small\n'
            f'{i3}text = "{caption}"\n{i2}}}\n'
            + rows + f'{i1}}}\n{ind}}}\n')


def contributors_charts(ind):
    """What feeds the pool: privately owned levels by priority group (Pat 13:05Z), then levels by owner (Pat
    15:33Z: Government, Local Shop Owners, Manor Houses, Financial Districts, company headquarters)."""
    groups = [(f'PMR_IPW_GROUP_{g}', pop, rgb, f'PMR_PC_ROW_{i}') for i, (g, _n, pop, rgb, _b) in enumerate(GROUPS)]
    owners = [(f'PMR_PO_NAME_{k}', pop, pop_rgb(pop), f'PMR_PO_ROW_{i}') for i, (k, _n, pop) in enumerate(OWNERS)]
    return (tree_chart(ind, groups, 'pmr_pc', 'PMR_PC_TT', 'PMR_PC_CAPTION', 'PMR_PC_EMPTY')
            + tree_chart(ind, owners, 'pmr_po', 'PMR_PO_TT', 'PMR_PO_CAPTION', 'PMR_PC_EMPTY'))


def compact_tree(ind, title, items, tooltip, legend_w):
    """A chart in the style of the market panel's Exports and Imports (vanilla compact_chart, Pat 16:12Z): an
    entry_bg frame, a #title heading, the tree map in vanilla's frame, and a legend beside it of swatch, name and
    share, four rows to a column. items: (name key, pop type for the colour, points variable, share variable, row
    tooltip). The slices take the chart's tooltip; each legend row has its own."""
    idx = 'PdxGuiWidget.GetIndexInDataModel'

    def chain(fn, vals):
        out = vals[-1]
        for i in range(len(vals) - 2, -1, -1):
            out = f"{fn}(EqualTo_int32({idx}, '(int32){i}'), {vals[i]}, {out})"
        return out
    color = chain('Select_CVector4f', [f"GetPopType('{pop}').GetColor" for _k, pop, *_r in items])
    name = chain('Select_CString', [f"'{pts}'" for _k, _p, pts, *_r in items])
    value = f"FixedPointToFloat({COUNTRY}.MakeScope.Var({name}).GetValue)"
    cols = (len(items) + LEGEND_ROWS - 1) // LEGEND_ROWS
    w = 10 + TREE + 10 + cols * legend_w + 5
    i1, i2, i3, i4, i5, i6 = (ind + '\t' * k for k in range(1, 7))
    legend = ''
    for c in range(cols):
        legend += f'{i3}flowcontainer = {{\n{i4}direction = vertical\n'
        for k, pop, _pts, share, tt in items[c * LEGEND_ROWS:(c + 1) * LEGEND_ROWS]:
            r, g, b = pop_rgb(pop)
            legend += (f'{i4}widget = {{\n{i5}size = {{ {legend_w} {LEGEND_ROW_H} }}\n{i5}tooltip = "{tt}"\n'
                       f'{i5}using = tooltip_above\n'
                       f'{i5}icon = {{\n{i6}parentanchor = vcenter\n{i6}position = {{ 4 0 }}\n{i6}size = {{ 18 18 }}\n'
                       f'{i6}texture = "gfx/interface/piechart/piechart_legend.dds"\n{i6}color = {{ {r} {g} {b} 1 }}\n{i5}}}\n'
                       f'{i5}textbox = {{\n{i6}parentanchor = vcenter\n{i6}position = {{ 26 0 }}\n'
                       f'{i6}size = {{ {legend_w - 26 - 30} {LEGEND_ROW_H} }}\n{i6}align = left|nobaseline\n{i6}elide = right\n'
                       f'{i6}using = fontsize_small\n{i6}text = "{k}"\n{i5}}}\n'
                       f'{i5}textbox = {{\n{i6}parentanchor = right|vcenter\n{i6}position = {{ -3 0 }}\n{i6}autoresize = yes\n'
                       f'{i6}align = right|nobaseline\n{i6}using = fontsize_small\n'
                       f'{i6}raw_text = "#v [{COUNTRY}.MakeScope.Var(\'{share}\').GetValue|0%]#!"\n{i5}}}\n{i4}}}\n')
        legend += f'{i3}}}\n'
    return (f'{ind}flowcontainer = {{\n{i1}direction = vertical\n{i1}spacing = 5\n'
            f'{i1}margin_left = 10\n{i1}margin_right = 5\n{i1}margin_top = 5\n{i1}margin_bottom = 10\n'
            f'{i1}background = {{\n{i2}using = entry_bg\n{i1}}}\n'
            f'{i1}textbox = {{\n{i2}size = {{ {w - 15} 23 }}\n{i2}align = hcenter|nobaseline\n{i2}default_format = "#title"\n'
            f'{i2}elide = right\n{i2}text = "{title}"\n{i2}tooltip = "{tooltip}"\n{i2}using = tooltip_above\n{i1}}}\n'
            f'{i1}flowcontainer = {{\n{i2}spacing = 10\n'
            f'{i2}container = {{\n'
            f'{i3}treemapchart = {{\n{i4}parentanchor = center\n{i4}size = {{ {TREE} {TREE} }}\n'
            f'{i4}datamodel = "[DataModelRepeatedItem(\'(int32){len(items)}\')]"\n'
            f'{i4}item = {{\n{i5}treemapslice = {{\n'
            f'{i6}texture = "gfx/interface/treemapchart/treemapchart.dds"\n'
            f'{i6}value = "[{value}]"\n{i6}color = "[{color}]"\n{i6}tooltip = "{tooltip}"\n{i6}using = tooltip_above\n'
            f'{i5}}}\n{i4}}}\n{i3}}}\n'
            f'{i3}icon = {{\n{i4}texture = "gfx/interface/treemapchart/treemapchart_frame.dds"\n{i4}parentanchor = center\n'
            f'{i4}size = {{ 124% 110% }}\n{i3}}}\n{i2}}}\n'
            f'{i2}flowcontainer = {{\n{i3}parentanchor = vcenter\n'
            + legend + f'{i2}}}\n{i1}}}\n{ind}}}\n')


def invest_charts(ind):
    """Top of Recent Investments: what was built since this version, by construction points (invest_effects), as
    the market panel's Exports and Imports charts (Pat 16:12Z, replacing the three bars of 15:33Z): domestic or
    foreign and who built it side by side, the priority groups under them."""
    var = lambda name: f"{COUNTRY}.MakeScope.Var('{name}').GetValue"
    has = f"GreaterThan_CFixedPoint({var('pmr_iv_tot')}, '(CFixedPoint)0')"
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    place = [('PMR_IV_HOME', HOME_POP, 'pmr_iv_dom', 'pmr_iv_dsh', 'PMR_IV_HOME_TT'),
             ('PMR_IV_ABROAD', ABROAD_POP, 'pmr_iv_for', 'pmr_iv_fsh', 'PMR_IV_ABROAD_TT')]
    who = [(f'PMR_IV_WHO_SHORT_{k}', pop, f'pmr_iv_w_{i}', f'pmr_iv_ws_{i}', f'PMR_IV_WHO_{k}_TT')
           for i, (k, _n, pop) in enumerate(WHO)]
    groups = [(f'PMR_IPW_GROUP_{g}', pop, f'pmr_iv_pts_{i}', f'pmr_iv_gs_{i}', f'PMR_IV_GROUP_{g}_TT')
              for i, (g, _n, pop, _c, _b) in enumerate(GROUPS)]
    # the first row shares the panel's width: the domestic chart's legend is narrow, who built takes the rest
    place_legend = 112
    who_legend = PANEL_W - 10 - 2 * (10 + TREE + 10 + 5) - place_legend
    row = (compact_tree(i3, 'PMR_IV_PLACE_TITLE', place, 'PMR_IV_PLACE_TT', place_legend)
           + compact_tree(i3, 'PMR_IV_WHO_TITLE', who, 'PMR_IV_WHOS_TT', who_legend))
    return (f'{ind}flowcontainer = {{\n{i1}parentanchor = hcenter\n{i1}direction = vertical\n{i1}spacing = 10\n'
            f'{i1}margin = {{ 0 8 }}\n'
            f'{i1}textbox = {{\n{i2}visible = "[Not({has})]"\n{i2}autoresize = yes\n{i2}multiline = yes\n'
            f'{i2}max_width = {PANEL_W - 20}\n{i2}align = nobaseline\n{i2}text = "PMR_IV_EMPTY"\n{i1}}}\n'
            f'{i1}flowcontainer = {{\n{i2}visible = "[{has}]"\n{i2}parentanchor = hcenter\n{i2}direction = vertical\n'
            f'{i2}spacing = 10\n'
            f'{i2}flowcontainer = {{\n{i3[:-1]}\tparentanchor = hcenter\n{i3}spacing = 10\n' + row + f'{i2}}}\n'
            + compact_tree(i2, 'PMR_IV_GROUPS_TITLE', groups, 'PMR_IV_GROUPS_TT', 140).replace(
                f'{i2}flowcontainer = {{\n', f'{i2}flowcontainer = {{\n{i3}parentanchor = hcenter\n', 1)
            + f'{i1}}}\n{ind}}}\n')


def fd_row(ind):
    """Foreign or domestic investment (Pat 15:34Z: a slider set apart from the priorities, laid out as the tariff
    bar): vanilla's set_level_bar with seven notches and the tariff bar's icons, Foreign on the left and Domestic on
    the right, on its own framed row. Each notch runs pmr_fd_sgui with its number (1..7, 4 = no preference)."""
    cur = f"{COUNTRY}.MakeScope.Var('pmr_fd_i').GetValue"
    i1, i2, i3, i4 = (ind + '\t' * k for k in range(1, 5))
    mid = (FD_NOTCHES + 1) // 2
    items = ''
    for n in range(1, FD_NOTCHES + 1):
        sel = f"EqualTo_CFixedPoint({cur}, '(CFixedPoint){n}')"
        if n == mid:   # never set reads 0: no preference
            sel = f"Or({sel}, EqualTo_CFixedPoint({cur}, '(CFixedPoint)0'))"
        run = (f"GetScriptedGui('pmr_fd_sgui').Execute(GuiScope.SetRoot({COUNTRY}.MakeScope)"
               f".AddScope('step', MakeScopeValue('(CFixedPoint){n}')).End)")
        items += (f'{i3}set_level_bar_item = {{\n{i4}tooltip = "PMR_FD_NOTCH_{n}"\n'
                  f'{i4}blockoverride "button_texture" {{\n{i4}\ttexture = "gfx/interface/icons/trade_icons/{FD_ICONS[n - 1]}.dds"\n{i4}}}\n'
                  f'{i4}blockoverride "click" {{\n{i4}\tonclick = "[{run}]"\n{i4}}}\n'
                  f'{i4}blockoverride "is_selected_visibility" {{\n{i4}\tvisible = "[{sel}]"\n{i4}}}\n{i3}}}\n')
    side = lambda key: (f'{i2}textbox = {{\n{i3}parentanchor = vcenter\n{i3}autoresize = yes\n{i3}align = nobaseline\n'
                        f'{i3}text = "{key}"\n{i2}}}\n')
    return (f'{ind}widget = {{\n{i1}size = {{ 540 76 }}\n{i1}parentanchor = hcenter\n'
            f'{i1}background = {{\n{i2}using = entry_bg\n{i1}}}\n'
            f'{i1}textbox = {{\n{i2}position = {{ 0 6 }}\n{i2}parentanchor = hcenter\n{i2}autoresize = yes\n'
            f'{i2}align = hcenter|nobaseline\n{i2}using = fontsize_large\n{i2}text = "PMR_FD_TITLE"\n'
            f'{i2}tooltip = "PMR_FD_TT"\n{i2}using = tooltip_above\n{i1}}}\n'
            f'{i1}flowcontainer = {{\n{i2}parentanchor = bottom|hcenter\n{i2}position = {{ 0 -8 }}\n{i2}spacing = 10\n'
            + side('PMR_FD_FOREIGN')
            + f'{i2}flowcontainer = {{\n{i3}using = set_level_bar_background\n{i3}parentanchor = vcenter\n'
            + items + f'{i2}}}\n'
            + side('PMR_FD_DOMESTIC')
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
    the same window, and once its 5 years are up an X that cancels it (Pat 20:08Z)."""
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
              f'{i2}tooltip = "PMR_POLICY_CHANGE_SEL_TT"\n{i2}using = tooltip_above\n{i1}}}\n')
    # Pat 20:08Z: once its 5 years are up, an X at the card's top right cancels the policy (vanilla's close button)
    cancel = f"GetScriptedGui('pmr_policy_cancel_sgui')"
    inner += (f'{i1}close_button = {{\n{i2}visible = "[{sv_on("pmr_policy_cancellable")}]"\n{i2}size = {{ 30 30 }}\n'
              f'{i2}parentanchor = top|right\n{i2}position = {{ -6 6 }}\n'
              f'{i2}enabled = "[{cancel}.IsValid(GuiScope.SetRoot({COUNTRY}.MakeScope).End)]"\n'
              f'{i2}onclick = "[{cancel}.Execute(GuiScope.SetRoot({COUNTRY}.MakeScope).End)]"\n'
              f'{i2}blockoverride "tooltip" {{\n{i3}tooltip = "PMR_POLICY_CANCEL_TT"\n{i2}}}\n{i1}}}\n')
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


def policy_content(k, icon, ind, w, cost, foots):
    """A policy's face: its icon, name and benefits only (Pat 14:28Z), then a last line with its authority cost on
    the left (cost: a loc key, Pat 19:34Z) and its status on the right (foots: (visible condition, text) per status,
    at most one shown at a time); click-through so its card takes the click. That line is the last of the card's own
    flow, so it can never sit on the benefits (Pat 19:25Z)."""
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    status = (f'{i1}widget = {{\n{i2}size = {{ {w - 24} 20 }}\n{i2}alwaystransparent = yes\n'
              f'{i2}textbox = {{\n{i3}size = {{ 100% 20 }}\n{i3}align = left|nobaseline\n{i3}using = fontsize_small\n'
              f'{i3}alwaystransparent = yes\n{i3}text = "{cost}"\n{i2}}}\n')
    for shown, text in foots:
        status += (f'{i2}textbox = {{\n' + (f'{i3}visible = "[{shown}]"\n' if shown else '') +
                   f'{i3}size = {{ 100% 20 }}\n{i3}align = right|nobaseline\n{i3}using = fontsize_small\n'
                   f'{i3}alwaystransparent = yes\n{i3}text = "{text}"\n{i2}}}\n')
    status += f'{i1}}}\n'
    return (f'{ind}flowcontainer = {{\n{i1}direction = vertical\n{i1}margin = {{ 12 10 }}\n{i1}spacing = 6\n'
            f'{i1}alwaystransparent = yes\n'
            f'{i1}flowcontainer = {{\n{i2}spacing = 8\n{i2}alwaystransparent = yes\n'
            f'{i2}icon = {{\n{i2}\tsize = {{ 48 48 }}\n{i2}\ttexture = "{icon}"\n{i2}\talwaystransparent = yes\n{i2}}}\n'
            f'{i2}textbox = {{\n{i2}\tparentanchor = vcenter\n{i2}\tautoresize = yes\n{i2}\tmax_width = {w - 84}\n'
            f'{i2}\tmultiline = yes\n{i2}\talign = nobaseline\n{i2}\tusing = fontsize_large\n{i2}\talwaystransparent = yes\n'
            f'{i2}\ttext = "PMR_POLICY_{k}"\n{i2}}}\n{i1}}}\n'
            f'{i1}textbox = {{\n{i2}autoresize = yes\n{i2}multiline = yes\n{i2}max_width = {w - 24}\n{i2}align = nobaseline\n'
            f'{i2}alwaystransparent = yes\n{i2}text = "PMR_POLICY_{k}_BENEFITS"\n{i1}}}\n' + status + f'{ind}}}\n')


def policy_choice(k, i, icon, ind, h):
    """One policy in the policy window (Pat 14:28Z): a blue card, as vanilla's law options, that adopts the
    policy when clicked; the explanation is its tooltip. The policy held shows as a selected card. h is its row's
    height (policy_card_h), so both cards of a row stay level."""
    scope = f'GuiScope.SetRoot({COUNTRY}.MakeScope).End'
    sg = f"GetScriptedGui('pmr_policy_{k}_sgui')"
    held = f"EqualTo_CFixedPoint({COUNTRY}.MakeScope.Var('pmr_policy').GetValue, '(CFixedPoint){i}')"
    i1, i2 = ind + '\t', ind + '\t\t'
    # In the 5 years after an adoption every other card says how long is left (Pat 20:06Z); otherwise a card that
    # needs a technology says so while the country lacks it (its law is held, or the row is hidden).
    foots = [(sv_on('pmr_policy_locked'), 'PMR_POLICY_LOCKED_FOR')]
    if k in POLICY_TECH:
        foots.append((f"And(Not({sv_on('pmr_policy_locked')}), {sv_on(f'pmr_policy_no_tech_{k}')})", f'PMR_POLICY_{k}_REQ'))
    return (f'{ind}widget = {{\n{i1}size = {{ {PCARD_W} {h} }}\n'
            f'{i1}button = {{\n{i2}visible = "[Not({held})]"\n{i2}using = default_button\n'
            f'{i2}size = {{ {PCARD_W} {h} }}\n'
            f'{i2}enabled = "[{sg}.IsValid({scope})]"\n'
            f'{i2}onclick = "[{sg}.Execute({scope})]"\n'
            f'{i2}onclick = "[GetVariableSystem.Clear(\'{PICK}\')]"\n'
            f'{i2}tooltip = "PMR_POLICY_{k}_TT"\n'
            + policy_content(k, icon, i2, PCARD_W, 'PMR_POLICY_COST', foots) + f'{i1}}}\n'
            f'{i1}widget = {{\n{i2}visible = "[{held}]"\n{i2}size = {{ 100% 100% }}\n{i2}tooltip = "PMR_POLICY_{k}_TT"\n'
            f'{i2}background = {{\n{i2}\tusing = entry_bg\n{i2}}}\n'
            f'{i2}background = {{\n{i2}\tusing = highlighted_selected_square_selection\n{i2}}}\n'
            + policy_content(k, icon, i2, PCARD_W, 'PMR_POLICY_PAID', [(None, 'PMR_POLICY_CURRENT')]) +
            f'{i1}}}\n{ind}}}\n')


def policy_laws():
    """Each law's policies in POLICIES order, as (key, index, icon)."""
    by_law = {}
    for i, (k, _n, icon, *_x) in enumerate(POLICIES, 1):
        by_law.setdefault(POLICY_LAWS[k], []).append((k, i, icon))
    return by_law


def policy_window(law, items):
    """The economic policy window (Pat 13:05Z, slimmed 14:28Z so it fits the screen): one per economic system law,
    showing that law's policies as cards, two to a row, beside the construction panel while its Private tab is
    open (only the held law's window shows, Pat 16:06Z). Each window is as tall as its own rows (Pat 19:25Z: the
    Laissez-faire window had an empty half). Vanilla's popup background, header and frame (block_windows.gui
    default_popup)."""
    i1, i2, i3 = '\t\t', '\t\t\t', '\t\t\t\t'
    shown = f"GetScriptedGui('pmr_policy_{items[0][0]}_sgui').IsShown(GuiScope.SetRoot({COUNTRY}.MakeScope).End)"
    rows, body = '', 0
    for r in range(0, len(items), 2):
        row = items[r:r + 2]
        h = policy_card_h([k for k, _i, _c in row])
        body += h + 10
        rows += f'{i2}flowcontainer = {{\n{i3}spacing = 10\n'
        for k, i, icon in row:
            rows += policy_choice(k, i, icon, i3, h)
        rows += f'{i2}}}\n'
    w = 2 * PCARD_W + 10 + 40
    h = 84 + body + 10    # the rows and their spacing, then a margin; no intro text (Pat 20:06Z)
    return (f'\ttype pmr_policy_window_{law} = widget {{\n'
            f'{i1}visible = "[And(And(InformationPanel.IsTabSelected(\'{TAB}\'), GetVariableSystem.Exists(\'{PICK}\')), '
            f'{shown})]"\n'
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
            + rows + f'{i1}}}\n\t}}\n')


def sv_on(name):
    """GUI: the player's country script value name is above 0."""
    return f"GreaterThan_CFixedPoint({COUNTRY}.MakeScope.ScriptValue('{name}'), '(CFixedPoint)0')"


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
        + ''.join(policy_window(lw, items) + '\n' for lw, items in policy_laws().items()) +
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
        # 3. contributors, as tree charts by group (Pat 13:05Z) and by owner (Pat 15:33Z)
        header('PMR_PI_SOURCES_HEADER', i1) + contributors_charts(i1) +
        # 4. economic law and policy
        header('PMR_PI_POLICY_HEADER', i1) +
        f'{i1}flowcontainer = {{\n{i1}\tparentanchor = hcenter\n{i1}\tmargin_top = 8\n{i1}\tmargin_bottom = 8\n{i1}\tspacing = 8\n'
        + law_card + policy_card(i2) + f'{i1}}}\n'
        # 5. priorities: foreign or domestic on its own row (Pat 15:34Z, instead of the explanation), then the groups
        + header('PMR_IPW_HEADER', i1) +
        f'{i1}widget = {{\n{i1}\tsize = {{ 540 6 }}\n{i1}}}\n'
        + fd_row(i1) +
        # the law's lock on the rows, in one line (Pat 19:34Z)
        ''.join(f'{i1}textbox = {{\n{i1}\tvisible = "[{shown}]"\n{i1}\tparentanchor = hcenter\n{i1}\tmargin_top = 6\n'
                f'{i1}\tautoresize = yes\n{i1}\tmultiline = yes\n{i1}\tmax_width = 520\n{i1}\talign = hcenter|nobaseline\n'
                f'{i1}\tusing = fontsize_small\n{i1}\ttext = "{key}"\n{i1}}}\n'
                for shown, key in ((sv_on('pmr_ipw_lf'), 'PMR_IPW_LF_NOTE'),
                                   (f"And(Not({sv_on('pmr_ipw_lf')}), {sv_on('pmr_ipw_locked_light')})",
                                    'PMR_IPW_AGR_NOTE'))) +
        f'{i1}widget = {{\n{i1}\tsize = {{ 540 6 }}\n{i1}}}\n'
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
        + header('PMR_PI_RECENT_HEADER', i1) + invest_charts(i1) +
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


def patch_retool_ai(text, btype, parent, invest):
    """pmr_retool_buildings.txt: each private retool building's ai_value ends with multiply = pmr_reinvest_mult_<group>,
    and for an investable type (invest) its base is the building's own ai_value, pmr_ai_value_<b> (vanilla's, with the
    foreign-or-domestic notch and the company policies), plus PROFIT_WEIGHT x its earnings: the score of an expansion
    of the building, which generate.py's ai_value then multiplies by RETOOL_AI_MULT (Pat 20:12Z)."""
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
        b = m.group(1)
        if 'building_' + b in invest:
            fallback = re.compile(r'\t\t\tvalue = \d+\n\t\t\tif = \{ limit = \{ has_variable = pmr_ai_w_' + b
                                  + r' \} value = var:pmr_ai_w_' + b + r' \}\n')
            f = fallback.search(text, a, close)
            if not f:
                fail('pmr_retool_buildings.txt', f'{k}: ai_value base not found')
            edits.append((f.start(), f'\t\t\t# PMR: the building\'s own ai_value and earnings\n\t\t\tvalue = pmr_ai_value_{b}\n'
                                     f'\t\t\tif = {{ limit = {{ has_variable = pmr_earn_{b} }} add = {{ value = var:pmr_earn_{b} '
                                     f'multiply = {PROFIT_WEIGHT} }} }}\n', f.end()))
        edits.append((close, f'\t# PMR: Re-invest card, x the {g} priority\n\t\tmultiply = pmr_reinvest_mult_{g}\n\t', close))
        n += 1
    if not n:
        fail('pmr_retool_buildings.txt', 'found no private retool buildings')
    for pos, ins, end in sorted(edits, reverse=True):
        text = text[:pos] + ins + text[end:]
    return text, n


def patch_ai_value(text, owners, invest):
    """A building file: each building type a company lists (owners) or the investment bars count (invest) gets
    ai_value = pmr_ai_value_<b>, whose body is the vanilla ai_value (number, block, or the 1000 default), plus
    CORP_BONUS while the state's owner holds Favour Large Corporations and has one of those companies, plus the
    owner's foreign-or-domestic notch (pmr_fd, -3..3) x FD_STEP on an investable type (Pat 15:34Z; ai_value is read
    in the state's scope, so foreign investors see the same weight in the player's states). Returns (text, script
    values)."""
    values, edits = [], []
    for k, _s, o, c in top_blocks(text):
        if k not in owners and k not in invest:
            continue
        body = text[o + 1:c]
        name = f'pmr_ai_value_{k[len("building_"):]}'
        m = re.search(r'\n(\s*)ai_value\s*=\s*', body)
        if m and body[m.end()] == '{':
            vo = o + 1 + m.end()
            vc = block_end(text, vo)
            inner = text[vo + 1:vc].rstrip() + '\n'
            edits.append((o + 1 + m.start(), vc + 1, f'\n{m.group(1)}ai_value = {name}  # PMR: vanilla value + policy and focus'))
        elif m:
            num = re.match(r'[-0-9.]+', body[m.end():]).group(0)
            inner = f'\tvalue = {num}\n'
            end = o + 1 + m.end() + len(num)
            edits.append((o + 1 + m.start(), end, f'\n{m.group(1)}ai_value = {name}  # PMR: vanilla {num} + policy and focus'))
        else:
            inner = f'\tvalue = {BASE_AI_VALUE}\n'
            edits.append((c, c, f'\t# PMR: vanilla default {BASE_AI_VALUE} + policy and focus\n\tai_value = {name}\n'))
        b = k[len('building_'):]
        extra = ''
        if k in owners:
            has = ''.join(f'\t\t\t\t\thas_company = company_type:{ct}\n' for ct in owners[k])
            for card, add in (('corporations', f'{CORP_BONUS}'),
                              ('titans', f'{{\n\t\t\tvalue = pmr_ai_earn_{b}\n\t\t\tmultiply = {PROFIT_WEIGHT}\n'
                                         f'\t\t\tadd = pmr_ai_base_{b}\n\t\t\tmultiply = 0.5\n\t\t}}')):
                extra += (f'\tif = {{\n\t\tlimit = {{\n\t\t\towner ?= {{\n'
                          f'\t\t\t\thas_modifier = pmr_policy_{card}\n\t\t\t\tOR = {{\n{has}\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n'
                          f'\t\tadd = {add}\n\t}}\n')
        if k in invest:
            extra += ('\tif = {\n\t\tlimit = {\n\t\t\towner ?= { has_variable = pmr_fd }\n\t\t}\n'
                      f'\t\tadd = {{\n\t\t\tvalue = owner.var:pmr_fd\n\t\t\tmultiply = {FD_STEP}\n\t\t}}\n\t}}\n'
                      '\tif = {\n\t\tlimit = {\n\t\t\towner ?= { has_modifier = pmr_policy_bulls }\n\t\t}\n'
                      f'\t\tadd = {{\n\t\t\tvalue = pmr_ai_earn_{b}\n\t\t\tmultiply = {PROFIT_WEIGHT // 2}\n\t\t}}\n\t}}\n')
        ladder = ''.join(f'\t\t{"else_if" if j else "if"} = {{\n\t\t\tlimit = {{ b:{k} = {{ earnings >= {e} }} }}\n'
                         f'\t\t\tvalue = {e}\n\t\t}}\n' for j, e in enumerate(EARNINGS_LADDER))
        values.append(f'pmr_ai_base_{b} = {{\n{inner}}}\n'
                      f'pmr_ai_earn_{b} = {{\n\tvalue = 0\n\tif = {{\n\t\tlimit = {{ exists = b:{k} }}\n{ladder}\t}}\n}}\n'
                      f'{name} = {{\n\tvalue = pmr_ai_base_{b}\n{extra}}}\n')
    for a, b, ins in sorted(edits, reverse=True):
        text = text[:a] + ins + text[b:]
    return text, values


# ---------------------------------------------------------------------------------------------------------------

def localization(types):
    law = "[GetLawType('law_interventionism').GetName]"
    lf = "[GetLawType('law_laissez_faire').GetName]"
    var = lambda name: f"{COUNTRY}.MakeScope.Var('{name}').GetValue"
    loc = [
        ' PMR_TAB_GOVERNMENT:0 "Government"',
        ' PMR_TAB_GOVERNMENT_TT:0 "The construction sector and the government construction queue"',
        ' PMR_TAB_PRIVATE:0 "Private"',
        ' PMR_TAB_PRIVATE_TT:0 "The investment pool, economic policy, investment priorities and private construction"',
        ' PMR_PI_POOL_HEADER:0 "Investment Pool"',
        ' PMR_RW_CHART_HEADER:0 "Weekly Re-investment"',
        ' PMR_RW_EMPTY:0 "No historical data"',
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
        ' PMR_IV_EMPTY:0 "Construction completed in your states, and what you build abroad, is counted here from now on '
        'by construction points."',
        ' PMR_IV_HOME:0 "Domestic"',
        ' PMR_IV_ABROAD:0 "Foreign"',
        f' PMR_IV_HOME_TT:0 "#header Domestic#!\\nConstruction points completed in your states, by anyone, retooling '
        f'included: #v [{var("pmr_iv_dom")}|0]#! (#v [{var("pmr_iv_dsh")}|0%]#!).\\n{SINCE}"',
        f' PMR_IV_ABROAD_TT:0 "#header Foreign#!\\nConstruction points your government and investors completed abroad, '
        f'retooling included: #v [{var("pmr_iv_for")}|0]#! (#v [{var("pmr_iv_fsh")}|0%]#!).\\n{SINCE}"',
        ' PMR_IV_NONE:0 ""',
        ' PMR_POLICY_ADD:0 "Add Policy"',
        f' PMR_POLICY_ADD_TT:0 "Choose an economic policy. {POLICY_HOW} Once adopted it is kept for 5 years."',
        f' PMR_POLICY_LOCKED:0 "Requires {law}, {lf} or [GetLawType(\'law_agrarianism\').GetName]"',
        ' PMR_POLICY_CHANGE:0 "Change Policy"',
        f' PMR_POLICY_CHANGE_SEL_TT:0 "[SelectLocalization({sv_on("pmr_policy_locked")}, \'PMR_POLICY_CHANGE_LOCK_TT\', '
        '\'PMR_POLICY_CHANGE_TT\')]"',
        f' PMR_POLICY_CHANGE_TT:0 "See every policy and swap this one for another. {POLICY_HOW} A new policy is kept for '
        '5 years. The X on this card cancels the policy."',
        ' PMR_POLICY_CHANGE_LOCK_TT:0 "See every policy. A policy is kept for 5 years once adopted: this one can be '
        f'swapped or cancelled in #v [{var("pmr_policy_lock_m")}|0]#! months."',
        f' PMR_POLICY_LOCKED_FOR:0 "#N Locked, [{var("pmr_policy_lock_m")}|0] months#!"',
        ' PMR_POLICY_CANCEL_TT:0 "#header Cancel Policy#!\\nEnds this policy and the authority it uses. You can adopt '
        'another at once."',
        ' PMR_POLICY_WINDOW_TITLE:0 "Economic Policies"',
        f' PMR_POLICY_COST:0 "@aut! #v [{COUNTRY}.MakeScope.ScriptValue(\'pmr_policy_cost\')|0]#! Authority"',
        f' PMR_POLICY_PAID:0 "@aut! #v [{var("pmr_policy_paid")}|0]#! Authority"',
        ' pmr_policy_authority:0 "Economic Policy"',
        ' PMR_POLICY_CURRENT:0 "#v Current Policy#!"',
        ' PMR_IPW_HEADER:0 "Investment Priorities"',
        ' PMR_PO_CAPTION:0 "Building levels by owner"',
        ' PMR_PO_TT:0 "#header Building Levels by Owner#!\\nWho owns the building levels of the five investment priority '
        'groups in your states, each building counted to the nearest eighth. Companies are the levels your companies own '
        'wherever they are; Manor Houses and Financial Districts are the rest, as script cannot tell those two apart. The '
        'game reports what each owner adds to the pool only as this list:\\n$TOOLTIP_DELIMITER$\\n'
        '[GetPlayer.GetInvestmentPoolChangeFromInvestmentBreakdown]"',
        ' PMR_FD_TITLE:0 "Foreign or Domestic Investment"',
        ' PMR_FD_FOREIGN:0 "Foreign"',
        ' PMR_FD_DOMESTIC:0 "Domestic"',
        f' PMR_FD_TT:0 "#header Foreign or Domestic Investment#!\\nTilts where investors build. Each notch from the '
        f'middle makes every building in your states weigh as if it earned #v @money!{FD_STEP / CORP_BONUS * 10:g}#! more '
        '(toward Domestic) or less (toward Foreign) a worker a year. Foreign investors weigh your states the same way. Toward '
        'Foreign, your investors need investment rights abroad, or the pool waits for something at home worth it."',
    ]
    mid = (FD_NOTCHES + 1) // 2
    names = {1: 'Strongly Foreign', 2: 'Foreign', 3: 'Leaning Foreign', 4: 'No Preference', 5: 'Leaning Domestic',
             6: 'Domestic', 7: 'Strongly Domestic'}
    for n in range(1, FD_NOTCHES + 1):
        d = (n - mid) * FD_STEP / CORP_BONUS * 10
        what = ('the game\'s own weighting' if d == 0 else
                f'buildings in your states weigh as if they earned {"#P" if d > 0 else "#N"} @money!{abs(d):g}#! '
                f'{"more" if d > 0 else "less"} a worker a year')
        loc.append(f' PMR_FD_NOTCH_{n}:0 "#bold {names[n]}#!: {what}"')
    for i, (k, name, _p) in enumerate(OWNERS):
        loc.append(f' PMR_PO_NAME_{k}:0 "{name}"')
        loc.append(f' PMR_PO_ROW_{i}:0 "#header {name}#!\\n#v [{var(f"pmr_po_{i}")}|0]#! building levels, '
                   f'#v [{var(f"pmr_po_share_{i}")}|0%]#! of them."')
    who_tt = {
        'gov': 'Construction points your government completed, at home and abroad, retooling included',
        'investors': 'Construction points your investors completed, at home and abroad, retooling included',
        'local': 'Construction points of levels in your states that went to the building\'s own local owners',
        'foreign': 'Construction points foreign investors or governments completed in your states',
    }
    for i, (k, name, _c) in enumerate(WHO):
        loc.append(f' PMR_IV_WHO_{k}:0 "{name}"')
        loc.append(f' PMR_IV_WHO_{k}_TT:0 "#header {name}#!\\n{who_tt[k]}: #v [{var(f"pmr_iv_w_{i}")}|0]#! '
                   f'(#v [{var(f"pmr_iv_ws_{i}")}|0%]#!).\\n{SINCE}"')
    short = {'gov': 'Government', 'investors': 'Investors', 'local': 'Local Owners', 'foreign': 'Foreign'}
    loc += [f' PMR_IV_WHO_SHORT_{k}:0 "{short[k]}"' for k, *_r in WHO]
    pts = lambda name, share: f'#v [{var(name)}|0]#! (#v [{var(share)}|0%]#!)'
    loc += [' PMR_IV_PLACE_TITLE:0 "Domestic and Foreign"',
            ' PMR_IV_WHO_TITLE:0 "Built By"',
            ' PMR_IV_GROUPS_TITLE:0 "Priority Groups"',
            ' PMR_IV_PLACE_TT:0 "#header Domestic and Foreign#!\\nConstruction points completed, retooling included:\\n'
            f'Domestic, in your states: {pts("pmr_iv_dom", "pmr_iv_dsh")}\\n'
            f'Foreign, your government and investors abroad: {pts("pmr_iv_for", "pmr_iv_fsh")}\\n{SINCE}"',
            ' PMR_IV_WHOS_TT:0 "#header Built By#!\\nConstruction points completed, retooling included:'
            + ''.join(f'\\n{name}: {pts(f"pmr_iv_w_{i}", f"pmr_iv_ws_{i}")}' for i, (k, name, _p) in enumerate(WHO))
            + f'\\n{SINCE}"',
            ' PMR_IV_GROUPS_TT:0 "#header Priority Groups#!\\nConstruction points completed, retooling counted under the '
            'building it retools:'
            + ''.join(f'\\n{name}: {pts(f"pmr_iv_pts_{i}", f"pmr_iv_gs_{i}")}' for i, (g, name, *_r) in enumerate(GROUPS))
            + f'\\nHover a group below the chart for its buildings. {SINCE}"']
    for gi, (g, name, *_r) in enumerate(GROUPS):
        lines = ''.join(f"[SelectLocalization(GreaterThan_CFixedPoint({var(f'pmr_iv_bt_{t}')}, '(CFixedPoint)0'), "
                        f"'PMR_IV_BT_{t}', 'PMR_IV_NONE')]" for t, tg, _c in types if tg == gi)
        loc.append(f' PMR_IV_GROUP_{g}_TT:0 "#header {name}#!\\nConstruction points completed: '
                   f'#v [{var(f"pmr_iv_pts_{gi}")}|0]#! (#v [{var(f"pmr_iv_gs_{gi}")}|0%]#!), by building:{lines}\\n'
                   f'Retooling counts under the building it retools. {SINCE}"')
    for t, _g, _c in types:
        loc.append(f' PMR_IV_BT_{t}:0 "\\n$building_{t}$: #v [{var(f"pmr_iv_bt_{t}")}|0]#! points, '
                   f'#v [{var(f"pmr_iv_bl_{t}")}|0]#! levels"')
    for k, name, _i, mods, core, core_tt, details in POLICIES:
        how = f'{core_tt}\\n' if core_tt else ''
        loc += [f' pmr_policy_{k}:0 "{name}"', f' PMR_POLICY_{k}:0 "{name}"',
                f' PMR_POLICY_{k}_BENEFITS:0 "{benefit_lines(core, mods)}"',
                f' PMR_POLICY_{k}_TT:0 "#header {name}#!\\n{how}$TOOLTIP_DELIMITER$\\n#italic {details}#!"']
        if k in POLICY_TECH:
            loc.append(f' PMR_POLICY_{k}_REQ:0 "#N Requires ${POLICY_TECH[k]}$#!"')
    for inst in TITANS_INSTITUTIONS:
        loc.append(f' pmr_titans_{inst}:0 "Market Titans: ${inst}$"')
    sv = lambda name: f"GreaterThan_CFixedPoint({COUNTRY}.MakeScope.ScriptValue('{name}'), '(CFixedPoint)0')"  # noqa: E731
    loc += [f' PMR_IPW_LOCK_LF:0 "#N Locked#! under {lf}: investors choose for themselves, so every priority counts '
            'as +0%. The coin you set is kept and counts again under another law."',
            ' PMR_IPW_LOCK_AGR:0 "#N Locked#! under [GetLawType(\'law_agrarianism\').GetName]: only Agriculture and '
            'Resources can be given priority. The coin you set here is kept and counts again under another law."',
            f' PMR_IPW_LF_NOTE:0 "Under {lf} investors choose for themselves: no priorities."',
            ' PMR_IPW_AGR_NOTE:0 "Under [GetLawType(\'law_agrarianism\').GetName] only Agriculture and Resources can '
            'be given priority."']
    for g, *_r in GROUPS:
        loc += [f' PMR_IPW_LOCK_{g}:0 "[SelectLocalization({sv("pmr_ipw_lf")}, \'PMR_IPW_LOCK_LF\', \'PMR_IPW_LOCK_AGR\')]"',
                f' PMR_IPW_COOLDOWN_{g}:0 "#N Changed recently#!\\nLike a tariff, a priority can be changed for '
                f'{GRACE_DAYS} days after a change, then not until 3 months have passed. About '
                f'#v [{var(f"pmr_ipw_wk_{g}")}|0]#! weeks left."']
        for st in STEPS:
            loc += [f' PMR_IPW_COIN_{g}_{st}:0 "[SelectLocalization({sv(f"pmr_ipw_locked_{g}")}, '
                    f'\'PMR_IPW_LOCK_{g}\', \'PMR_IPW_OPEN_{g}_{st}\')]"',
                    f' PMR_IPW_OPEN_{g}_{st}:0 "[SelectLocalization({sv(f"pmr_ipw_cooling_{g}")}, '
                    f'\'PMR_IPW_COOLDOWN_{g}\', \'PMR_IPW_NOTCH_{st}\')]"']
    for s in STEPS:
        loc.append(f' PMR_IPW_NOTCH_{s}:0 "' + ('No priority' if s == 0 else
                   f'{s}% of the cap: #P +[FixedPointToInt(Multiply_CFixedPoint({COUNTRY}.MakeScope.ScriptValue(\'pmr_ipw_cap\'), \'(CFixedPoint){s}\'))]%#!')
                   + f'\\nAfter a change you have {GRACE_DAYS} days to change it again, then it stays for 3 months, as a '
                   'tariff does."')
    for i in range(RI_WEEKS):
        when = 'This week' if i == 0 else ('1 week ago' if i == 1 else f'{i} weeks ago')
        loc.append(f' PMR_RW_COLUMN_{i}:0 "{when}: #v @money![{var(f"pmr_rw_{i}")}|D]#! re-invested\\n'
                   'The column splits it by the privately owned levels of each priority group that week, as the tree '
                   'chart below."')
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


IDEOLOGY_FILE = 'common/ideologies/01_character_ideologies.txt'


def patch_ideologies(text):
    """Bulls & Bears (Pat 16:06Z): Market Liberal leaders appear more often. 1.14.5 has no modifier for an
    ideology's chance, so both of the ideology's leader weights (interest group leaders and others) are multiplied
    by LIBERAL_WEIGHT when the country holds the policy. Shadows the whole vanilla file."""
    start = text.find('\nideology_market_liberal = {')
    if start < 0:
        fail(IDEOLOGY_FILE, 'ideology_market_liberal not found')
    end = block_end(text, text.index('{', start))
    block = text[start:end]
    for key, desc in (('interest_group_leader_weight', '\n\t\t\tdesc = "PMR_POLICY_bulls"'),
                      ('non_interest_group_leader_weight', '')):
        m = re.search(r'^\t' + key + r' = \{', block, re.M)
        if not m:
            fail(IDEOLOGY_FILE, f'ideology_market_liberal has no {key}')
        close = block_end(block, block.index('{', m.start()))
        block = (block[:close] + '\t# PMR: Bulls & Bears\n\t\tif = {\n\t\t\tlimit = {\n\t\t\t\towner ?= { has_modifier = '
                 f'pmr_policy_bulls }}\n\t\t\t}}\n\t\t\tmultiply = {{\n\t\t\t\tvalue = {LIBERAL_WEIGHT}'
                 + desc.replace('\n\t\t\t', '\n\t\t\t\t') + '\n\t\t\t}\n\t\t}\n\t' + block[close:])
    return text[:start] + block + text[end:]


def write_all(game, write, header_text, out=None):
    """Writes every file this feature owns, then patches generate.py's building outputs under out (skipped when
    out is None, as in the standalone run). Returns loc lines."""
    def vanilla(rel):
        return open(os.path.join(game, rel), encoding='utf-8-sig').read()
    types = invest_types(game)
    # generate.py's copy of SOURCE_FILE when it wrote one (ports and railways retool), else vanilla's
    mine = os.path.join(out, SOURCE_FILE) if out else None
    buildings, _groups = patch_scores(open(mine, encoding='utf-8-sig').read() if mine and os.path.exists(mine)
                                      else vanilla(SOURCE_FILE))
    values = script_values()
    write('common/scripted_guis/pmr_ipw_sguis.txt', header_text + sguis())
    write('common/static_modifiers/pmr_policy_modifiers.txt', header_text + static_modifiers())
    write('common/on_actions/pmr_pi_on_actions.txt', header_text + on_actions())
    write('common/scripted_effects/pmr_pi_effects.txt', header_text + reinvest_effect() + '\n' + chart_effect() + '\n'
          + clock_effect() + '\n' + upkeep_effect() + '\n' + policy_effects() + '\n'
          + invest_effects(types, retool_types(game, out)))
    write('common/scripted_triggers/pmr_ipw_triggers.txt', header_text + law_triggers())
    write('events/pmr_pi_events.txt', header_text + events())
    write(IDEOLOGY_FILE, patch_ideologies(vanilla(IDEOLOGY_FILE)))
    write(QUEUE_GUI, patch_queue(vanilla(QUEUE_GUI)), bom=False)
    write(PANEL_GUI, patch_panel(vanilla(PANEL_GUI)), bom=False)
    write(OWN_GUI, '# GENERATED by tools/pmr/private_investment.py\n' + private_tab(), bom=False)
    if out:
        btype, parent = building_groups(game)
        rpath = os.path.join(out, 'common', 'buildings', 'pmr_retool_buildings.txt')
        invest = {f'building_{s}' for s, _g, _c in types}
        text, n = patch_retool_ai(open(rpath, encoding='utf-8-sig').read(), btype, parent, invest)
        write('common/buildings/pmr_retool_buildings.txt', text)
        owners = company_owners(game)
        wrapped, patched, done = [], [], set()
        # generate.py's building files, this feature's copy of SOURCE_FILE, and the vanilla files holding other
        # investable types (06_urban_center.txt: the art academy and the power plant), shadowed
        files = [(name, open(os.path.join(out, 'common', 'buildings', name), encoding='utf-8-sig').read())
                 for name in sorted(os.listdir(os.path.join(out, 'common', 'buildings')))
                 if not name.startswith('pmr_') and name != os.path.basename(SOURCE_FILE)]
        files.append((os.path.basename(SOURCE_FILE), buildings))
        for k, _s, _o, _c in [b for _n, t in files for b in top_blocks(t)]:
            done.add(k)
        for name in sorted(os.listdir(os.path.join(game, 'common', 'buildings'))):
            t = vanilla(f'common/buildings/{name}')
            if name.endswith('.txt') and any(k in invest and k not in done for k, *_r in top_blocks(t)):
                files.append((name, t))
        for name, t in files:
            text, vals = patch_ai_value(t, owners, invest)
            if name == os.path.basename(SOURCE_FILE):
                buildings = text
            elif vals:
                write(f'common/buildings/{name}', text)
            if vals:
                wrapped += vals
                patched.append(name)
        names = set(re.findall(r'^pmr_ai_value_([a-z_0-9]+) = ', '\n'.join(wrapped), re.M))
        missing = sorted(invest - {f'building_{n}' for n in names})
        if missing:
            fail('common/buildings', f'investable types without a wrapped ai_value: {missing}')
        values += ('# State scope. For each company or investable building type in ' + ', '.join(patched) + ':\n'
                   '# pmr_ai_base_<b>, its vanilla ai_value; pmr_ai_earn_<b>, the earnings per employee of the state\'s\n'
                   '# building of that type (0 without one); and pmr_ai_value_<b>, the ai_value: the base, plus\n'
                   f'# {CORP_BONUS} under Favour Large Corporations and half of (base + {PROFIT_WEIGHT} x earnings) under Market\n'
                   '# Titans when the owner has a company listing the type, the owner\'s foreign-or-domestic notch x\n'
                   f'# {FD_STEP}, and {PROFIT_WEIGHT // 2} x earnings under Bulls & Bears.\n'
                   + '\n'.join(wrapped))
        print(f'private investment: {n} private retool buildings take Re-invest; {len(names)} building types take '
              f'the company card or the investment focus, in {", ".join(patched)}')
    write(SOURCE_FILE, buildings)
    write('common/script_values/pmr_ipw_values.txt', header_text + values)
    return localization(types)


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
