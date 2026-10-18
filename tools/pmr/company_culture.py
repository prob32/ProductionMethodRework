"""Company Culture: a wheel of company traits on every company's panel (Pat, 2026-10-14; reworked 2026-10-18).

Pat 02:03Z (10-14) asked for a company sub-panel like Hearts of Iron IV's military-industrial organisations: prosperity
earns points, points buy bonuses. On 2026-10-18 Pat redesigned it as a wheel and sent it to build at 18:18Z ("ok submit
this to the build agent to construct"). The single source is /mnt/project-files/pmr/mio/tree-ui/BUILD-SPEC.md; this
module builds it, cc_wheel.py draws it. Test builds only until Pat ships it.

The wheel (BUILD-SPEC section 1): four arms round the company's seal, Engineering top right, Stewardship top left,
Expansion bottom left, Providence bottom right. Engineering and Expansion are opposed, as are Stewardship and
Providence: a company holds one arm of each pair at most. The first founding culture is free; a second, from the other
pair, costs SECOND_COST points once REACH nodes are bought in the first. Each pair of neighbouring arms has a shared
charter halfway out (it needs tier II of a line on each side and opens the outer half of both arms) and a synergy
behind it.

How a bonus reaches the company's own levels and nobody else's (confirmed in game 2026-10-14 03:51Z): each bonus is a
character trait on the company's executive with an `executive_modifier`, which the engine applies to the building
levels the company owns, in proportion on part-owned buildings. Lines whose numbers depend on the company (Supply's
goods, Up-skilling's engineers, Master Craftsmen's goods, the works markers) use one trait per good or value, picked
by variables the company type sets at init, so the traits never need a chain over company types.

Engineering's goods lines (section 4): each tier is a new production method for the building making one of the
company's top two output goods. A trait cannot add a real input (works share probe, q19), so the method is a share in
PMR's blend: generate.py gives each goods-line building two more blend members, `works out` (goods_output_<good>_mult)
and `works in` (goods_input_<good>_mult), whose steps carry WORKS_OUT[-1] and WORKS_IN[-1] x n / WORKS_STEPS as
unscaled building modifiers. Each completed tier's trait sets the script-only marker building_pmr_cw_<b>_t<tier> to
1; the engine scales it by the company's share of the building (q19/q20: Krupp's 2 of 5 Westfalen steel levels read
0.400), so the building reads the levels at each tier with no loop over companies, and PMR's tick (pmr_works_<b>,
works_effect) sizes the two members from them. A company carries only its highest completed tier's trait for a
building, so a level is never counted twice. While the variant's extra input is at the price cap those levels fall
back to the base recipe (the members go to 0).

Research grants (section 5): buying a goods tier starts a grant that runs GRANT_MONTHS on the monthly company tick,
one at a time per company, paid as it starts from the owner's investment pool: GRANT_COST per level the company
employs (it can't start while the pool holds less). The tier then unlocks: its marker trait goes on, and the building's next tick blends it in.

Points (unchanged since 10-14): each month a company earns prosperity x (1 + employed levels / 50, capped at 2)
funds; a full bar (100 x (level + 1)^1.8 + 700, HoI4's curve) is one point.

State lives on the company; every value the tab shows is mirrored onto the executive (the panel reads
Company.GetExecutive.MakeScope), and the clicks are character-scope scripted GUIs that find the company back as the
owner's company whose executive is that character.

Wiring into generate.py main(), test builds only:

    import company_culture
    cc_plan = company_culture.plan(game, {bk: plain recipes}, goods_cost)   # before the blend members are made
    ... company_culture.works_members(cc_plan, bk) as extra blend members, works_effect() in the tick ...
    loc += company_culture.write_all(game, write, header, report, cc_plan, args.out)
"""
import glob
import os
import re

import pdx
import cc_icons
import cc_wheel

TAB = 'pmr_culture'                 # InformationPanel tab id
OWN_GUI = 'gui/pmr_company_culture.gui'
PANEL_GUI = 'gui/company_panel.gui'
CHARTER_FILE = 'common/company_charter_types/00_company_charter_types.txt'
CAL_VERSION = 4                     # bump to make every company re-read its numbers (pmr_cc_on); 4: the wheel

# ---------------------------------------------------------------------------------------------------------------
# Numbers Pat hasn't confirmed (BUILD-SPEC section 5 and 7): named so they are easy to change.
GRANT_MONTHS = 12                       # Pat 21:53Z: 12 months, not 24
GRANT_COST = (500, 1000, 1500)      # £ per level the company employs, paid from its country's investment pool as a
                                    # grant starts (Pat 22:28Z: money from the investment pool, not input goods)
WORKS_OUT = (0.15, 0.25, 0.40)      # a goods tier's main output over the base method it replaces
WORKS_IN = (0.05, 0.10, 0.15)       # and its one extra input
WORKS_STEPS = 40                    # blend steps of the two works members (2.5% of WORKS_*[-1] each)
PRICE_CAP = 1.75                    # pmr_px_<good> at the price cap: the variant falls back (PM rework's veto rule)
INPUT_CUT_CAP = 20                  # an input good never more than 20% cheaper in amount from all lines
WAGE_CUT_CAP = 25                   # wage target never below -25% from all lines
REACH = 2                           # nodes bought in the first arm before a second founding culture
SECOND_COST = 2                     # points for the second founding culture
UPSKILL_CUT = (0.06, 0.12, 0.20)    # Up-skilling: laborer jobs cut
LABORERS_PER_ENGINEER = 4           # one engineer job per four laborer jobs cut
SC_AI_MULT = (1.25, 1.5, 2)         # Expanded Works: ai_value of the company's building types

# Points
PROSPERITY_LADDER = list(range(100, 0, -5))          # 100, 95 .. 5
SIZE_LADDER = [(n, 1 + n / 50) for n in range(50, 0, -5)]
LV_LADDER = list(range(100, 20, -5)) + list(range(20, 0, -1))   # employed levels, for a grant's cost
MAX_LEVEL = 60
TEST_POINTS = 6

TRAIT_ICON = 'gfx/interface/icons/character_trait_icons/{}.dds'
INVENTION = 'gfx/interface/icons/invention_icons/{}.dds'
WORKERS = ('laborers', 'farmers', 'machinists', 'clerks', 'engineers', 'shopkeepers')


def point_cost(level):
    return round(100 * (level + 1) ** 1.8 + 700)


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
# Names by good and building group (GOODS-BRANCHES.md tables)

# Engineering: (goods, tier names, extra inputs)
ENG_ROWS = [
    (('steel',), ('Hot Blast Stoves', 'Steam Blowing Engines', 'Regenerative Furnaces'), ('coal', 'engines', 'tools')),
    (('iron',), ('Ore Roasting', 'Steam Hoists', 'Rock Drills'), ('coal', 'engines', 'explosives')),
    (('coal',), ('Steam Winding', 'Mechanical Cutters', 'Electric Haulage'), ('engines', 'tools', 'electricity')),
    (('lead',), ('Ore Dressing', 'Steam Hoists', 'Flotation Cells'), ('engines', 'explosives', 'tools')),
    (('gold',), ('Stamp Mills', 'Hydraulic Sluicing', 'Cyanide Process'), ('explosives', 'engines', 'tools')),
    (('sulfur',), ('Steam Pumps', 'Ore Furnaces', 'Frasch Wells'), ('coal', 'engines', 'oil')),
    (('oil',), ('Cable-Tool Rigs', 'Rotary Drilling', 'Gas Lift'), ('engines', 'steel', 'tools')),
    (('wood', 'hardwood'), ('Steam Sawmills', 'Logging Railways', 'Band Saws'), ('engines', 'tools', 'transportation')),
    (('rubber',), ('Tapping Panels', 'Smoke Houses', 'Budded Clones'), ('tools', 'sulfur', 'fertilizer')),
    (('engines',), ('Precision Lathes', 'Machine Shops', 'Assembly Lines'), ('steel', 'tools', 'electricity')),
    (('tools',), ('Machine Tools', 'Milling Machines', 'Interchangeable Parts'), ('steel', 'coal', 'electricity')),
    (('clippers', 'manowars'), ('Composite Hulls', 'Steam Saws', 'Patent Rigging'), ('hardwood', 'fabric', 'tools')),
    (('steamers', 'ironclads'), ('Iron Hulls', 'Compound Engines', 'Triple Expansion'), ('steel', 'engines', 'coal')),
    (('clothes',), ('Sewing Machines', 'Cutting Tables', 'Electric Sewing'), ('fabric', 'tools', 'electricity')),
    (('luxury_clothes',), ('Pattern Cutting', 'Jacquard Trims', 'Couture Ateliers'), ('silk', 'dye', 'tools')),
    (('fabric',), ('Power Looms', 'Ring Spinning', 'Automatic Looms'), ('engines', 'dye', 'coal')),
    (('silk',), ('Rearing Houses', 'Reeling Machines', 'Steam Filatures'), ('coal', 'tools', 'fertilizer')),
    (('liquor',), ('Column Stills', 'Steam Distilling', 'Bottling Lines'), ('glass', 'coal', 'sugar')),
    (('wine',), ('Press Machines', 'Cellar Cooling', 'Bottling Lines'), ('glass', 'tools', 'electricity')),
    (('groceries',), ('Canning', 'Refrigeration', 'Mechanised Bakeries'), ('iron', 'glass', 'electricity')),
    (('sugar',), ('Vacuum Pans', 'Centrifuges', 'Diffusion Batteries'), ('coal', 'engines', 'tools')),
    (('grain',), ('Seed Drills', 'Reapers', 'Steam Threshers'), ('tools', 'engines', 'fertilizer')),
    (('fruit',), ('Grafted Orchards', 'Irrigation', 'Cold Storage'), ('fertilizer', 'tools', 'electricity')),
    (('meat',), ('Feedlots', 'Refrigerated Cars', 'Packing Lines'), ('grain', 'transportation', 'electricity')),
    (('fish',), ('Steam Trawlers', 'Ice Holds', 'Cold Storage'), ('engines', 'coal', 'electricity')),
    (('tobacco', 'tea', 'coffee', 'opium', 'dye'), ('Curing Barns', 'Rolling Machines', 'Fertilised Estates'),
     ('coal', 'tools', 'fertilizer')),
    (('artillery',), ('Rifled Barrels', 'Breech Blocks', 'Recoil Mechanisms'), ('steel', 'tools', 'explosives')),
    (('small_arms',), ('Machine Rifling', 'Interchangeable Parts', 'Automatic Lathes'), ('steel', 'tools', 'hardwood')),
    (('ammunition',), ('Brass Drawing', 'Smokeless Powder', 'Belt Loading'), ('lead', 'explosives', 'electricity')),
    (('explosives',), ('Nitration Sheds', 'Contact Process', 'Continuous Nitration'), ('sulfur', 'coal', 'electricity')),
    (('fertilizer',), ('Superphosphate Works', 'Lead Chambers', 'Nitrogen Fixation'), ('sulfur', 'coal', 'electricity')),
    (('glass',), ('Tank Furnaces', 'Pressing Machines', 'Bottle Machines'), ('coal', 'tools', 'electricity')),
    (('porcelain',), ('Tunnel Kilns', 'Jiggering', 'Transfer Printing'), ('coal', 'dye', 'tools')),
    (('paper',), ('Fourdrinier Machines', 'Wood Pulping', 'Sulphite Process'), ('wood', 'sulfur', 'coal')),
    (('furniture', 'luxury_furniture'), ('Steam Saws', 'Bentwood', 'Veneering'), ('hardwood', 'tools', 'fabric')),
    (('transportation',), ('Steel Rails', 'Air Brakes', 'Block Signalling'), ('steel', 'engines', 'electricity')),
    (('merchant_marine',), ('Steam Cranes', 'Dry Docks', 'Coaling Stations'), ('engines', 'coal', 'steel')),
    (('electricity',), ('Compound Dynamos', 'Steam Turbines', 'AC Transmission'), ('coal', 'steel', 'engines')),
    (('telephones', 'radios'), ('Switchboards', 'Loading Coils', 'Vacuum Tubes'), ('rubber', 'lead', 'electricity')),
    (('automobiles',), ('Assembly Lines', 'Pressed Steel Bodies', 'Electric Starters'), ('steel', 'rubber', 'electricity')),
    (('aeroplanes',), ('Metal Airframes', 'Wind Tunnels', 'Radial Engines'), ('engines', 'steel', 'electricity')),
    (('tanks',), ('Welded Hulls', 'Diesel Engines', 'Torsion Bars'), ('steel', 'engines', 'oil')),
]
# Expansion's Supply: (goods, tier names); the last row is every other good's.
EXP_ROWS = [
    (('coal',), ('Coal Contracts', 'Fuel Economisers', 'Captive Collieries')),
    (('tools',), ('Bulk Tool Orders', 'Tool Rooms', 'In-House Smithies')),
    (('engines',), ('Maintenance Shops', 'Standard Patterns', 'Engine Pools')),
    (('oil',), ('Lubricant Contracts', 'Oil Recovery', 'Pipeline Supply')),
    (('electricity',), ('Load Scheduling', 'Own Dynamos', 'Grid Contracts')),
    (('transportation',), ('Rail Sidings', 'Freight Contracts', 'Private Wagons')),
    (('iron',), ('Ore Contracts', 'Scrap Recycling', 'Captive Mines')),
    (('steel',), ('Steel Contracts', 'Scrap Reuse', 'Captive Mills')),
    (('wood', 'hardwood'), ('Timber Concessions', 'Kiln Drying', 'Own Forests')),
    (('fabric',), ('Bolt Contracts', 'Cutting Patterns', 'Remnant Reuse')),
    (('explosives',), ('Bulk Powder', 'Blasting Schedules', 'Controlled Charges')),
    (('rubber',), ('Latex Contracts', 'Reclaimed Rubber', 'Own Estates')),
    (('dye',), ('Dye Contracts', 'Fast Mordants', 'Own Dyeworks')),
    (('lead',), ('Lead Contracts', 'Scrap Lead', 'Captive Mines')),
    (('fertilizer',), ('Guano Contracts', 'Manure Recycling', 'Own Works')),
    (('silk',), ('Bale Contracts', 'Waste Silk Spinning', 'Own Filatures')),
    (('grain', 'sugar', 'meat', 'fish', 'fruit', 'tobacco', 'tea', 'coffee', 'opium'),
     ('Harvest Contracts', 'Waste Reduction', 'Own Estates')),
    (('glass',), ('Glass Contracts', 'Cullet Recycling', 'Own Glassworks')),
    (('sulfur',), ('Sulfur Contracts', 'Acid Recovery', 'Captive Mines')),
    (('clippers', 'steamers', 'manowars', 'ironclads'), ('Charter Contracts', 'Fleet Pooling', 'Own Fleet')),
    ((), ('Supply Contracts', 'Waste Reduction', 'Vertical Integration')),
]
# Stewardship's Up-skilling, by the company's main building group.
UPSKILL_ROWS = [
    ('mines', ('Mine Captains', 'Mining School', 'School of Mines')),
    ('heavy', ('Apprenticeships', 'Technical Institute', 'Works Laboratory')),
    ('light', ('Foremen Training', 'Trade School', 'Works Engineers')),
    ('farms', ('Agronomists', 'Farm School', 'Agricultural College')),
    ('logging', ('Forest Wardens', 'Forestry School', 'Silviculture')),
    ('oil', ('Drillers\' Training', 'Petroleum Geologists', 'Research Station')),
    ('shipyards', ('Shipwrights\' Guild', 'Naval Architects', 'Model Basin')),
    ('rail', ('Railway Engineers', 'Signal School', 'Electrical Institute')),
]
GROUP_ROW = {'bg_mining': 'mines', 'bg_gold_fields': 'mines', 'bg_heavy_industry': 'heavy',
             'bg_military_industry': 'heavy', 'bg_ship_construction': 'shipyards', 'bg_light_industry': 'light',
             'bg_agriculture': 'farms', 'bg_ranching': 'farms', 'bg_plantations': 'farms', 'bg_fishing': 'farms',
             'bg_whaling': 'farms', 'bg_logging': 'logging', 'bg_rubber': 'logging', 'bg_oil_extraction': 'oil',
             'bg_infrastructure': 'rail', 'bg_power': 'rail', 'bg_trade': 'rail'}


def eng_row(good):
    for i, (goods, _n, _x) in enumerate(ENG_ROWS, 1):
        if good in goods:
            return i
    return 0


def exp_row(good):
    for i, (goods, _n) in enumerate(EXP_ROWS, 1):
        if good in goods:
            return i
    return len(EXP_ROWS)


# A company-named line's node picture follows its name row (Pat 22:28Z: "we can't have a rifle barrel representing
# steam winding"): line -> (the company variable holding its row, the pictures per row and tier, cc_icons.py).
ROW_ICONS = {'g1': ('pmr_cc_k_g1r', cc_icons.ENG_ICONS), 'g2': ('pmr_cc_k_g2r', cc_icons.ENG_ICONS),
             'xs': ('pmr_cc_k_xr', cc_icons.EXP_ICONS), 'au': ('pmr_cc_k_ar', cc_icons.UPS_ICONS)}


def rows_used(p, k):
    """The name rows of line k some company has (plus the default rows of a company type PMR doesn't know)."""
    row = {'g1': lambda v: v['grow'][0] if v['g'] else 0, 'g2': lambda v: v['grow'][1] if len(v['g']) > 1 else 0,
           'xs': lambda v: v['xr'], 'au': lambda v: v['ar']}[k]
    dflt = {'xs': {len(EXP_ROWS)}, 'au': {3}}.get(k, set())
    return sorted(({row(v) for v in p.comp.values()} | dflt) - {0})


# ---------------------------------------------------------------------------------------------------------------
# The lines

ARMS = ('eng', 'stw', 'exp', 'prv')
OPP = {'eng': 'exp', 'exp': 'eng', 'stw': 'prv', 'prv': 'stw'}
FOUND = {'eng': 'fe', 'exp': 'fx', 'stw': 'fs', 'prv': 'ft'}


class Line:
    """A line of tiers bought in order; its tier is the company variable pmr_cc_<key>. code is the scope:line value a
    click passes. arms: its arm, or the two arms of a shared node. needs: script conditions for tier 1 (and the links
    drawn to it, `links`). outer: tiers past the gate orbit, waiting for a shared charter of the arm. goods: an
    Engineering goods line (1 or 2), whose tiers are research grants."""
    def __init__(self, code, key, arms, kind, names, icons, cost, needs=(), links=(), outer=(), goods=0,
                 founding=False):
        self.code, self.key, self.arms, self.kind = code, key, arms, kind
        self.names, self.icons, self.cost = names, icons, cost
        self.needs, self.links, self.outer, self.goods, self.founding = needs, links, set(outer), goods, founding
        self.tiers = len(cost)
        self.shared = len(arms) == 2

    @property
    def arm(self):
        return self.arms[0]


def _inv(*names):
    return tuple(INVENTION.format(n) for n in names)


T3 = (1, 2, 3)
NEED_G1_II = ('OR = { AND = { var:pmr_cc_k_g1b > 0 var:pmr_cc_g1 >= 2 } '
              'AND = { var:pmr_cc_k_g1b = 0 var:pmr_cc_sf >= 1 } }')
NEED_G2_II = ('OR = { AND = { var:pmr_cc_k_g2b > 0 var:pmr_cc_g2 >= 2 } '
              'AND = { var:pmr_cc_k_g2b = 0 var:pmr_cc_k_g1b > 0 var:pmr_cc_g1 >= 2 } '
              'AND = { var:pmr_cc_k_g1b = 0 var:pmr_cc_sf >= 1 } }')
LINES = [
    Line(1, 'fe', ('eng',), 'prod', ('Engineering',), _inv('mechanical_tools'), (0,), founding=True),
    Line(2, 'fs', ('stw',), 'work', ('Stewardship',), _inv('labor_movement'), (0,), founding=True),
    Line(3, 'fx', ('exp',), 'input', ('Expansion',), _inv('manufacturies'), (0,), founding=True),
    Line(4, 'ft', ('prv',), 'labour', ('Providence',), _inv('currency_standards'), (0,), founding=True),
    # Engineering
    Line(5, 'g1', ('eng',), 'pm', ('Works Method I', 'Works Method II', 'Works Method III'),
         _inv('steelworking', 'bessemer_process', 'open_hearth_process'), T3, outer=(3,), goods=1),
    Line(6, 'g2', ('eng',), 'pm', ('Works Method I', 'Works Method II', 'Works Method III'),
         _inv('rifling', 'breech_loading_artillery', 'lathe'), T3, outer=(3,), goods=2),
    Line(7, 'sf', ('eng',), 'work', ('Safety Rules',), _inv('triage'), (2,)),
    # Expansion
    Line(8, 'xs', ('exp',), 'input', ('Supply I', 'Supply II', 'Supply III'),
         _inv('shaft_mining', 'watertube_boiler', 'steam_donkey'), T3, outer=(3,)),
    Line(9, 'sc', ('exp',), 'prod', ('Expanded Works I', 'Expanded Works II', 'Mass Production'),
         _inv('mechanized_workshops', 'gantry_crane', 'conveyers'), T3, outer=(3,)),
    Line(10, 'cz', ('exp',), 'charter', ('Colonization Charter',), _inv('colonization'), (3,),
         needs=('var:pmr_cc_sc >= 3',), links=(('sc', 3),), outer=(1,)),
    # Stewardship
    Line(11, 'fw', ('stw',), 'work', ('Fair Wages', 'Living Wage', 'Profit Sharing'),
         _inv('postal_savings', 'mutual_funds', 'joint_stock_companies'), T3, outer=(3,)),
    Line(12, 'ho', ('stw',), 'work', ('Company Housing', 'Model Dwellings'), _inv('urbanization', 'urban_planning'),
         (1, 2)),
    Line(13, 'ct', ('stw',), 'work', ('Company Town',), _inv('modern_sewerage'), (3,),
         needs=('var:pmr_cc_ho >= 2', 'var:pmr_cc_fw >= 2'), links=(('ho', 2), ('fw', 2)), outer=(1,)),
    Line(14, 'au', ('stw',), 'work', ('Up-skilling I', 'Up-skilling II', 'Up-skilling III'),
         _inv('academia', 'empiricism', 'rationalism'), T3, outer=(2, 3)),
    Line(15, 'pg', ('stw',), 'charter', ('Hallmark Goods',), _inv('crystal_glass'), (3,),
         needs=('var:pmr_cc_ct >= 1',), links=(('ct', 1),), outer=(1,)),
    # Providence
    Line(16, 'cl', ('prv',), 'labour', ('Casual Labour I', 'Casual Labour II', 'Casual Labour III'),
         _inv('shift_work', 'enclosure', 'identification_documents'), T3, outer=(3,)),
    Line(17, 'tp', ('prv',), 'labour', ('Tight Payroll I', 'Tight Payroll II'), _inv('bureaucracy', 'law_enforcement'),
         (1, 2)),
    # Shared charters, halfway out (Pat 17:17-17:21Z, 17:42Z)
    Line(18, 'tr', ('eng', 'stw'), 'charter', ('Trade Charter',), _inv('international_trade'), (3,),
         needs=(NEED_G2_II, 'var:pmr_cc_fw >= 2'), links=(('g2', 2), ('fw', 2))),
    Line(19, 'iv', ('eng', 'prv'), 'charter', ('Investment Charter',), _inv('investment_banks'), (3,),
         needs=(NEED_G1_II, 'var:pmr_cc_tp >= 2'), links=(('g1', 2), ('tp', 2))),
    Line(20, 'ch', ('exp', 'stw'), 'charter', ('Industry Charter',), _inv('corporate_charters'), (3,),
         needs=('var:pmr_cc_xs >= 2', 'var:pmr_cc_ho >= 2'), links=(('xs', 2), ('ho', 2))),
    Line(21, 'mo', ('exp', 'prv'), 'charter', ('Monopoly Charter',), _inv('power_of_the_purse'), (3,),
         needs=('var:pmr_cc_sc >= 2', 'var:pmr_cc_cl >= 2'), links=(('sc', 2), ('cl', 2))),
    # Synergies, further out on the same boundaries
    Line(22, 'ys', ('eng', 'stw'), 'prod', ('Master Craftsmen',), _inv('pneumatic_tools'), (3,),
         needs=('var:pmr_cc_tr >= 1',), links=(('tr', 1),)),
    Line(23, 'yi', ('eng', 'prv'), 'labour', ('Labour-Saving Machinery',), _inv('steam_turbines'), (3,),
         needs=('var:pmr_cc_iv >= 1',), links=(('iv', 1),)),
    Line(24, 'yt', ('exp', 'stw'), 'input', ('Fair Supply Contracts',), _inv('international_exchange_standards'), (3,),
         needs=('var:pmr_cc_ch >= 1',), links=(('ch', 1),)),
    Line(25, 'ym', ('exp', 'prv'), 'input', ('Vertical Trust',), _inv('stock_exchanges'), (3,),
         needs=('var:pmr_cc_mo >= 1',), links=(('mo', 1),)),
]
BY_KEY = {ln.key: ln for ln in LINES}
for _k, _icons in cc_icons.LINE_ICONS.items():   # Pat 22:28Z: pictures that show the node (cc_icons.py)
    BY_KEY[_k].icons = _icons
KEYS = [ln.key for ln in LINES]
CHARTERS = {'tr': 'trade_charter', 'iv': 'investment_charter', 'ch': 'industry_charter', 'mo': 'monopoly_charter',
            'cz': 'colonization_charter'}
SHARED_OF = {a: [ln.key for ln in LINES if ln.shared and a in ln.arms and ln.key in CHARTERS] for a in ARMS}
# The lines in each arm, for the count that opens a second founding culture.
ARM_LINES = {a: [ln.key for ln in LINES if not ln.shared and not ln.founding and ln.arm == a] for a in ARMS}
# Company-specific names: these lines' node names come from custom localization (custom_loc()).
NAMED_BY_COMPANY = {'g1', 'g2', 'xs', 'au'}

# The order AI companies buy in (a step whose arm the company doesn't hold is passed over; the first open step is
# bought when affordable, otherwise the company saves for it).
AI_ORDER = [('g1', 1), ('xs', 1), ('fw', 1), ('cl', 1), ('sc', 1), ('au', 1), ('tp', 1), ('ho', 1), ('g2', 1),
            ('sf', 1), ('g1', 2), ('xs', 2), ('sc', 2), ('fw', 2), ('cl', 2), ('ho', 2), ('tp', 2), ('g2', 2),
            ('tr', 1), ('iv', 1), ('ch', 1), ('mo', 1), ('g1', 3), ('g2', 3), ('xs', 3), ('sc', 3), ('fw', 3),
            ('cl', 3), ('au', 2), ('ct', 1), ('au', 3), ('cz', 1), ('pg', 1), ('ys', 1), ('yi', 1), ('yt', 1),
            ('ym', 1)]

# Traits of the lines whose numbers are the same for every company: (line, tier) -> executive modifiers. A tier's
# trait replaces the one before (Profit Sharing keeps Living Wage's wage target and attractiveness).
SOL = [(f'building_{p}_standard_of_living_add', 1) for p in WORKERS]
GENERIC = {
    ('fe', 1): [('building_throughput_add', 0.03)],
    ('fx', 1): [('building_goods_input_mult', -0.02)],
    ('fs', 1): [('building_job_attractiveness_mult', 0.10)],
    ('ft', 1): [('building_minimum_wage_mult', -0.05)],
    ('sf', 1): [('building_working_conditions_mult', -0.20)],
    ('xs', 1): [('building_throughput_add', 0.05)],
    ('xs', 2): [('building_throughput_add', 0.10)],
    ('xs', 3): [('building_throughput_add', 0.15)],
    ('sc', 1): [('building_throughput_add', 0.10)],
    ('sc', 2): [('building_throughput_add', 0.15)],
    ('sc', 3): [('building_throughput_add', 0.25)],
    ('fw', 1): [('building_minimum_wage_mult', 0.10)],
    ('fw', 2): [('building_minimum_wage_mult', 0.20), ('building_job_attractiveness_mult', 0.20)],
    ('fw', 3): [('building_minimum_wage_mult', 0.20), ('building_job_attractiveness_mult', 0.20),
                ('building_company_worker_dividends_add', 0.15)],
    ('ho', 1): SOL,
    ('ho', 2): [(k, 2) for k, _v in SOL],
    ('ct', 1): SOL + [('building_job_attractiveness_mult', 0.15)],
    ('au', 1): [('building_employment_laborers_mult', -UPSKILL_CUT[0])],
    ('au', 2): [('building_employment_laborers_mult', -UPSKILL_CUT[1])],
    ('au', 3): [('building_employment_laborers_mult', -UPSKILL_CUT[2])],
    ('cl', 1): [('building_employment_laborers_mult', 0.05), ('building_minimum_wage_mult', -0.05)],
    ('cl', 2): [('building_employment_laborers_mult', 0.10), ('building_minimum_wage_mult', -0.10)],
    ('cl', 3): [('building_employment_laborers_mult', 0.15), ('building_minimum_wage_mult', -0.15)],
    ('tp', 1): [('building_minimum_wage_mult', -0.10)],
    ('tp', 2): [('building_minimum_wage_mult', -0.20)],
    ('ys', 1): [('building_employment_engineers_mult', 0.05)],
    ('yi', 1): [('building_employment_laborers_mult', -0.15), ('goods_input_tools_mult', 0.05)],
    ('yt', 1): [('building_goods_input_mult', -0.05), ('building_job_attractiveness_mult', 0.10)],
    ('ym', 1): [('building_goods_input_mult', -0.10), ('building_minimum_wage_mult', -0.05)],
}
# Supply's per-good cut, capped so an input good stays within INPUT_CUT_CAP from all lines: the general cuts beside
# it are Expansion's founding 2 and Fair Supply Contracts 5 or Vertical Trust 10 (never both: opposed arms).
SUPPLY_VALUES = sorted({min(5 * t, INPUT_CUT_CAP - g) for t in T3 for g in (2, 7, 12)})


def trait_icon(k, t):
    return BY_KEY[k].icons[t - 1]


# ---------------------------------------------------------------------------------------------------------------
# Reading the game

def companies(game):
    """company key -> (building_types, prestige variables its prestige_goods_trigger reads), in file order."""
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
                out[n.key] = (pdx.items(bt) if bt else [], sorted(set(pvars)))
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


class Plan:
    """What the generator decides per building and per company type (plan())."""
    def __init__(self):
        self.works = {}        # building -> {'out', 'in', 'row', 'techs': [per tier], 'icons': [per tier], 'idx'}
        self.comp = {}         # company -> dict of its numbers (see plan())
        self.goods = []        # every good a company variable names, 1-based
        self.ae_values = []    # every Up-skilling engineer count
        self.goods_tex = {}     # good -> its icon (vanilla's goods texture)


def plan(game, plain, goods_cost, goods_tex=None):
    """plain: building -> its plain PMR recipes (generate.Recipe). Picks each company's goods lines (the building types
    making its top two output goods by value), Supply goods (its top two input goods), Up-skilling names and engineer
    counts, and the works spec of every goods-line building."""
    comps = companies(game)
    groups = building_groups(game)
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
    lab = {bk: sum(r.employment.get('building_employment_laborers_add', 0) for r in rs) / len(rs)
           for bk, rs in plain.items() if rs}

    def works_spec(bk):
        good = main[bk][0]
        row = eng_row(good)
        extra = ENG_ROWS[row - 1][2]
        rs = plain[bk]
        newest = rs[-1]
        cand = ([g for g in extra if g in newest.inputs] + [g for g in extra if any(g in r.inputs for r in rs)])
        if not cand:   # no extra input the recipes use: the building's own most valuable input
            iv = in_val.get(bk, {})
            cand = [max(iv, key=iv.get)] if iv else []
        tier = [rs[min(t, len(rs)) - 1] for t in T3]
        return {'out': good, 'in': cand[0] if cand else None, 'row': row,
                'techs': [list(r.unlock_techs) for r in tier], 'icons': [r.texture for r in tier]}

    for c, (bts, pvars) in comps.items():
        own = [b for b in bts if b in main]
        ranked = sorted((b for b in own if eng_row(main[b][0])), key=lambda b: -main[b][1])
        g = ranked[:2]
        for b in g:
            if b not in p.works:
                p.works[b] = works_spec(b)
        ins = {}
        for b in own:
            for good, v in in_val.get(b, {}).items():
                ins[good] = ins.get(good, 0) + v
        xg = sorted(ins, key=lambda k: -ins[k])[:2]
        top = (g[0] if g else (own[0] if own else (bts[0] if bts else None)))
        row = 'light'
        for grp in groups.get(top, []):
            if grp in GROUP_ROW:
                row = GROUP_ROW[grp]
                break
        if top and 'shipyard' in top:
            row = 'shipyards'
        labs = [lab[b] for b in own if lab.get(b)]
        lb = sum(labs) / len(labs) if labs else 0
        ae = [max(5, 5 * round(lb * cut / LABORERS_PER_ENGINEER / 5)) if lb else 0 for cut in UPSKILL_CUT]
        p.comp[c] = {'g': g, 'gout': [main[b][0] for b in g], 'gin': [None] * len(g), 'xg': xg, 'xr': exp_row(xg[0]) if xg else len(EXP_ROWS),
                     'ar': [r for r, _n in UPSKILL_ROWS].index(row) + 1, 'ae': ae, 'pvars': pvars,
                     'grow': [eng_row(main[b][0]) for b in g]}
    for i, b in enumerate(sorted(p.works), 1):
        p.works[b]['idx'] = i
    for c, v in p.comp.items():
        v['gin'] = [p.works[b]['in'] for b in v['g']]
    goods = set()
    for v in p.comp.values():
        goods.update(v['gout'] + [x for x in v['gin'] if x] + v['xg'])
    p.goods = sorted(goods)
    p.ae_values = sorted({a for v in p.comp.values() for a in v['ae'] if a})
    return p


def gi(p, good):
    return p.goods.index(good) + 1 if good else 0


# ---------------------------------------------------------------------------------------------------------------
# The works members (generate.py) and their tick

def works_marker(b, t):
    return f'building_pmr_cw_{short(b)}_t{t}'


class WorksMember:
    """A blend member for generate.py's members list: a loc key and an icon, carrying unscaled modifiers."""
    def __init__(self, key, texture):
        self.key, self.texture = key, texture


def works_members(p, bk, texture):
    """[(kind, WorksMember, {modifier: value at the full share})] for a goods-line building, or []."""
    w = p.works.get(bk)
    if not w:
        return []
    b = short(bk)
    out = [('out', WorksMember(f'pmr_cw_out_{b}', texture), {f'goods_output_{w["out"]}_mult': WORKS_OUT[-1]})]
    if w['in']:
        out.append(('in', WorksMember(f'pmr_cw_in_{b}', texture), {f'goods_input_{w["in"]}_mult': WORKS_IN[-1]}))
    return out


def works_effect(p, bk, jout, jin):
    """State scope: pmr_wn_<j>_<b>, the steps of the two works members, from the company levels at each tier (the
    markers), 0 while the variant's extra input is at the price cap (BUILD-SPEC section 4)."""
    b = short(bk)
    w = p.works[bk]

    def v(name):
        return f'{name}_{b}'
    o = f'pmr_works_{b} = {{\n'
    o += f'\tset_variable = {{ name = {v(f"pmr_wn_{jout}")} value = 0 }}\n'
    if jin:
        o += f'\tset_variable = {{ name = {v(f"pmr_wn_{jin}")} value = 0 }}\n'
    # read as the works share probe did (q19/q20): the building as a saved scope, its modifier through it
    body = f'\t\tb:{bk} = {{ save_temporary_scope_as = pmr_cw_b }}\n'
    for t in T3:
        body += (f'\t\tset_variable = {{ name = {v(f"pmr_cwl{t}")} value = scope:pmr_cw_b.modifier:{works_marker(bk, t)} }}\n'
                 f'\t\tchange_variable = {{ name = {v(f"pmr_cwl{t}")} multiply = var:{v("pmr_level")} }}\n'
                 f'\t\tround_variable = {{ name = {v(f"pmr_cwl{t}")} nearest = 1 }}\n')
    # steps = sum(levels_t x share_t) / level / max x STEPS, with share_t / max per tier folded into one factor
    for j, table in ((jout, WORKS_OUT), (jin, WORKS_IN)):
        if not j:
            continue
        body += f'\t\tset_variable = {{ name = {v(f"pmr_wn_{j}")} value = 0 }}\n'
        for t in T3:
            body += (f'\t\tset_variable = {{ name = {v("pmr_cwt")} value = var:{v(f"pmr_cwl{t}")} }}\n'
                     f'\t\tchange_variable = {{ name = {v("pmr_cwt")} multiply = {fmt(table[t - 1] / table[-1] * WORKS_STEPS)} }}\n'
                     f'\t\tchange_variable = {{ name = {v(f"pmr_wn_{j}")} add = var:{v("pmr_cwt")} }}\n')
        body += (f'\t\tchange_variable = {{ name = {v(f"pmr_wn_{j}")} divide = var:{v("pmr_level")} }}\n'
                 f'\t\tround_variable = {{ name = {v(f"pmr_wn_{j}")} nearest = 1 }}\n'
                 f'\t\tif = {{ limit = {{ var:{v(f"pmr_wn_{j}")} > {WORKS_STEPS} }} '
                 f'set_variable = {{ name = {v(f"pmr_wn_{j}")} value = {WORKS_STEPS} }} }}\n')
    cap = ''
    if w['in']:
        cap = (f'\t\tpmr_price_{w["in"]} = yes\n'
               f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_px_{w["in"]} >= {fmt(PRICE_CAP)} }}\n'
               f'\t\t\t# the variant\'s extra input is at the price cap: those levels run the base recipe\n'
               f'\t\t\tset_variable = {{ name = {v(f"pmr_wn_{jout}")} value = 0 }}\n'
               + (f'\t\t\tset_variable = {{ name = {v(f"pmr_wn_{jin}")} value = 0 }}\n' if jin else '')
               + '\t\t}\n')

    # a quiet building never logs a blend, so the share logs itself each month while a company holds a tier here
    def g(name, f=0):
        return f"[THIS.Var('{v(name)}').GetValue|{f}]"
    held = ' '.join(f'var:{v(f"pmr_cwl{t}")} > 0' for t in T3)
    log = (f'\t\tif = {{ limit = {{ owner = {{ is_player = yes }} OR = {{ {held} }} }} '
           f'debug_log = "PMR;rec=WORKS;date=[TimeKeeper.GetCurrentDate.GetString];'
           f'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting];'
           f'building={bk};level={g("pmr_level")};'
           + ';'.join(f't{t}={g(f"pmr_cwl{t}")}' for t in T3)
           + f';out={g(f"pmr_wn_{jout}")}'
           + (f';in={g(f"pmr_wn_{jin}")};px_{w["in"]}=[THIS.Var(\'pmr_px_{w["in"]}\').GetValue|2]' if jin else '')
           + '" }\n')
    o += (f'\t# only once some company has completed a tier for this building type (pmr_cc_grant_done)\n'
          f'\tif = {{\n\t\tlimit = {{ has_global_variable = pmr_cw_on_{b} exists = b:{bk} var:{v("pmr_level")} > 0 }}\n'
          + body + cap + log + '\t}\n}\n\n')
    return o


# ---------------------------------------------------------------------------------------------------------------
# Traits

def trait(key, icon, mods):
    body = ''.join(f'\t\t{k} = {fmt(v)}\n' for k, v in mods)
    return (f'{key} = {{\n\ttype = condition\n\ttexture = "{icon}"\n\n'
            f'\texecutive_modifier = {{\n{body}\t}}\n\n'
            '\tpossible = { always = no }\n\tweight = { value = 0 }\n\tvalue = 0\n}\n')


def generic_trait(k, t):
    return f'pmr_cc_{k}_{t}'


def keyed_traits(p):
    """(trait key, icon, modifiers, condition on the company) for the traits picked by company variables."""
    out = []
    for g in p.goods:
        n = gi(p, g)
        for val in SUPPLY_VALUES:
            out.append((f'pmr_cc_xs_{g}_{val}', trait_icon('xs', 1), [(f'goods_input_{g}_mult', -val / 100)],
                        f'var:pmr_cc_xsv = {val} OR = {{ var:pmr_cc_k_xg1 = {n} var:pmr_cc_k_xg2 = {n} }}'))
        out.append((f'pmr_cc_ys_{g}', trait_icon('ys', 1), [(f'goods_output_{g}_mult', 0.05)],
                    f'var:pmr_cc_ys = 1 OR = {{ var:pmr_cc_k_g1g = {n} var:pmr_cc_k_g2g = {n} }}'))
    for a in p.ae_values:
        out.append((f'pmr_cc_ae_{a}', trait_icon('au', 1), [('building_employment_engineers_add', a)],
                    f'var:pmr_cc_aev = {a}'))
    for bk, w in sorted(p.works.items()):
        for t in T3:
            out.append((f'pmr_cc_cw_{short(bk)}_{t}', BY_KEY['g1'].icons[t - 1], [(works_marker(bk, t), 1)],
                        f'OR = {{ AND = {{ var:pmr_cc_k_g1b = {w["idx"]} var:pmr_cc_g1 = {t} }} '
                        f'AND = {{ var:pmr_cc_k_g2b = {w["idx"]} var:pmr_cc_g2 = {t} }} }}'))
    for n in range(1, 5):
        out.append((f'pmr_cc_wcap_{n}', trait_icon('ft', 1), [('building_minimum_wage_mult', 0.05 * n)],
                    f'var:pmr_cc_wc = {n}'))
    return out


def traits(p):
    out = ['# Company Culture traits (company_culture.py). Each sits on a company\'s executive; its executive_modifier\n'
           '# applies to the building levels that company owns. Never random (possible no, weight 0, value 0).\n\n']
    for (k, t), mods in GENERIC.items():
        out.append(trait(generic_trait(k, t), trait_icon(k, t), mods))
    for key, icon, mods, _w in keyed_traits(p):
        out.append(trait(key, icon, mods))
    return '\n'.join(out)


GOODS_MULT = re.compile(r'goods_(input|output)_\w+_mult')


def goods_mults(p):
    """Every goods_input/output_<good>_mult the traits and the works members use."""
    used = {k for (_k, _t), mods in GENERIC.items() for k, _v in mods}
    used |= {k for _key, _i, mods, _w in keyed_traits(p) for k, _v in mods}
    for bk in p.works:
        used |= {k for _kind, _m, mods in works_members(p, bk, None) for k in mods}
    return sorted(k for k in used if GOODS_MULT.fullmatch(k))


def vanilla_modifier_types(game):
    keys = set()
    for path in glob.glob(os.path.join(game, 'common', 'modifier_type_definitions', '*.txt')):
        keys |= set(re.findall(r'^(\w+)\s*=\s*\{', open(path, encoding='utf-8-sig').read(), re.M))
    return keys


def goods_mult_loc(p, game):
    """Names for the goods modifier types modifier_types() adds: vanilla's own name of the matching _add type, as
    vanilla names building_employment_laborers_mult, so every language reads its own (else the good's name)."""
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
        else:   # vanilla names no _add for this good either: the good and vanilla's Input / Output Goods
            m = GOODS_MULT.fullmatch(k)
            g = k[len(f'goods_{m.group(1)}_'):-len('_mult')]
            out.append(f' {k}:0 "@{g}! ${g}$ ($concept_{m.group(1)}_goods$)"')
    return out


def modifier_types(p, game):
    out = ['# Dynamic modifier types vanilla 1.14.5 does not define (the exe has the pattern building_employment_{}_mult;\n'
           '# the Hudson\'s Bay probe confirmed laborers in game, 2026-10-14).\n']
    for pop in ('laborers', 'engineers'):
        out.append(f'building_employment_{pop}_mult = {{\n\tdecimals = 0\n\tcolor = neutral\n\tpercent = yes\n'
                   '\tgame_data = { ai_value = 0 }\n}\n')
    have = vanilla_modifier_types(game)
    if not {'goods_output_hardwood_mult', 'goods_input_tanks_mult'} <= have:
        fail('common/modifier_type_definitions', 'vanilla\'s goods modifier types not found')
    out.append('# The per-good input and output multipliers the traits and the works members use: the engine looks them up\n'
               '# by the pattern goods_input_{}_mult / goods_output_{}_mult, but an undefined one loads empty ("Unknown\n'
               '# modifier type"). Vanilla defines some; these are the rest, styled as vanilla\'s.\n')
    for k in goods_mults(p):
        if k not in have:
            col = 'good' if k.startswith('goods_output_') else 'bad'
            out.append(f'{k} = {{\n\tdecimals = 1\n\tcolor = {col}\n\tpercent = yes\n\tgame_data = {{ ai_value = 0 }}\n}}\n')
    out.append('# Works markers (BUILD-SPEC section 4): a company\'s goods-tier trait sets one to 1, and a building reads it\n'
               '# as that company\'s share of its levels (the engine scales executive modifiers by share; q19/q20).\n')
    for bk in sorted(p.works):
        for t in T3:
            out.append(f'{works_marker(bk, t)} = {{\n\tscript_only = yes\n\tdecimals = 2\n\tcolor = neutral\n'
                       '\tgame_data = { ai_value = 0 }\n}\n')
    return '\n'.join(out)


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
            "grant=[THIS.Var('pmr_cc_gr').GetValue|0]/[THIS.Var('pmr_cc_grt').GetValue|0]/[THIS.Var('pmr_cc_grm').GetValue|0];"
            "g1b=[THIS.Var('pmr_cc_k_g1b').GetValue|0];g2b=[THIS.Var('pmr_cc_k_g2b').GetValue|0];"
            + ';'.join(f"{k}=[THIS.Var('pmr_cc_{k}').GetValue|0]" for k in KEYS) + '"')


def player_log(rec, extra=''):
    return f'if = {{ limit = {{ owner ?= {{ is_player = yes }} }} {log_line(rec, extra)} }}'


KVARS = ['pmr_cc_k_g1b', 'pmr_cc_k_g2b', 'pmr_cc_k_g1g', 'pmr_cc_k_g2g', 'pmr_cc_k_g1i', 'pmr_cc_k_g2i',
         'pmr_cc_k_g1r', 'pmr_cc_k_g2r', 'pmr_cc_k_xg1', 'pmr_cc_k_xg2', 'pmr_cc_k_xr', 'pmr_cc_k_ar',
         'pmr_cc_k_ae1', 'pmr_cc_k_ae2', 'pmr_cc_k_ae3', 'pmr_cc_k_pg']
STATE_VARS = [f'pmr_cc_st_{ln.key}_{t}' for ln in LINES for t in range(1, ln.tiers + 1)]
MIRRORED = (['pmr_cc_level', 'pmr_cc_pts', 'pmr_cc_funds', 'pmr_cc_cost', 'pmr_cc_rate', 'pmr_cc_pct', 'pmr_cc_mth',
             'pmr_cc_prosp', 'pmr_cc_size', 'pmr_cc_gr', 'pmr_cc_grt', 'pmr_cc_grm', 'pmr_cc_fcost', 'pmr_cc_nf',
             'pmr_cc_xsv', 'pmr_cc_aev', 'pmr_cc_gc1', 'pmr_cc_gc2', 'pmr_cc_gok1', 'pmr_cc_gok2']
            + [f'pmr_cc_{k}' for k in KEYS] + [f'pmr_cc_pick_{k}' for k in KEYS] + STATE_VARS + KVARS)


def reached(arm):
    return f'var:pmr_cc_{FOUND[arm]} = 1'


def ruled(arm):
    return f'var:pmr_cc_{FOUND[OPP[arm]]} = 1'


def outer_ok(arm):
    return 'OR = { ' + ' '.join(f'var:pmr_cc_{s} = 1' for s in SHARED_OF[arm]) + ' }'


def tier_conds(ln, t):
    """What tier t of line ln needs beyond its arms and points: the tier before, its needs, the gate, technology."""
    c = [f'var:pmr_cc_{ln.key} = {t - 1}']
    if t == 1:
        c += list(ln.needs)
    if t in ln.outer:
        c.append(outer_ok(ln.arm))
    if ln.goods:
        c.append(f'var:pmr_cc_g{ln.goods}tk >= {t}')
    return c


def arm_ok(ln):
    return [reached(a) for a in ln.arms]


def not_available(ln):
    if ln.goods:
        return f'var:pmr_cc_k_g{ln.goods}b = 0'
    if ln.key == 'pg':
        return 'var:pmr_cc_k_pg = 0'
    return None


def effects(p, comps):
    o = []
    o.append('# Company Culture (company_culture.py). Company scope unless said otherwise. Variables on the company:\n'
             '# pmr_cc_on (calibration version), pmr_cc_funds, pmr_cc_level, pmr_cc_pts (unspent), pmr_cc_cost (funds for\n'
             '# the next point), pmr_cc_rate (funds last month), pmr_cc_<line> (tier completed), pmr_cc_k_* (the company\n'
             '# type\'s numbers: goods-line buildings, goods, name rows, engineers), pmr_cc_gr / grt / grm (the research grant\n'
             '# running: line code, tier, months), pmr_cc_n_<arm>, pmr_cc_nf, pmr_cc_nfirst (founding cultures and nodes),\n'
             '# pmr_cc_g1tk / g2tk (the highest goods tier the owner\'s technology allows), pmr_cc_xsv (Supply\'s cut per good,\n'
             '# capped), pmr_cc_wc (the wage target correction, in 5% steps), pmr_cc_aev (Up-skilling\'s engineer jobs).\n'
             '# Everything the tab shows is mirrored onto the executive (pmr_cc_mirror), which also holds pmr_cc_of, the\n'
             '# company its traits were set for.\n\n')
    # Init: the company type's numbers.
    chain = ''
    for i, (c, v) in enumerate(sorted(p.comp.items())):
        g = v['g']
        vals = {'pmr_cc_k_g1b': p.works[g[0]]['idx'] if g else 0, 'pmr_cc_k_g2b': p.works[g[1]]['idx'] if len(g) > 1 else 0,
                'pmr_cc_k_g1g': gi(p, v['gout'][0]) if g else 0, 'pmr_cc_k_g2g': gi(p, v['gout'][1]) if len(g) > 1 else 0,
                'pmr_cc_k_g1i': gi(p, v['gin'][0]) if g else 0, 'pmr_cc_k_g2i': gi(p, v['gin'][1]) if len(g) > 1 else 0,
                'pmr_cc_k_g1r': v['grow'][0] if g else 0, 'pmr_cc_k_g2r': v['grow'][1] if len(g) > 1 else 0,
                'pmr_cc_k_xg1': gi(p, v['xg'][0]) if v['xg'] else 0,
                'pmr_cc_k_xg2': gi(p, v['xg'][1]) if len(v['xg']) > 1 else 0,
                'pmr_cc_k_xr': v['xr'], 'pmr_cc_k_ar': v['ar'], 'pmr_cc_k_ae1': v['ae'][0], 'pmr_cc_k_ae2': v['ae'][1],
                'pmr_cc_k_ae3': v['ae'][2], 'pmr_cc_k_pg': 1 if v['pvars'] else 0}
        sets = ' '.join(f'set_variable = {{ name = {k} value = {x} }}' for k, x in vals.items())
        chain += f'\t{"if" if i == 0 else "else_if"} = {{\n\t\tlimit = {{ is_company_type = company_type:{c} }}\n\t\t{sets}\n\t}}\n'
    dflt = ' '.join(f'set_variable = {{ name = {k} value = 0 }}' for k in KVARS if k != 'pmr_cc_k_xr')
    dflt += f' set_variable = {{ name = pmr_cc_k_xr value = {len(EXP_ROWS)} }} set_variable = {{ name = pmr_cc_k_ar value = 3 }}'
    zero = (['pmr_cc_funds', 'pmr_cc_level', 'pmr_cc_pts', 'pmr_cc_rate', 'pmr_cc_gr', 'pmr_cc_grt', 'pmr_cc_grm']
            + [f'pmr_cc_{k}' for k in KEYS])
    o.append('# A company seen for the first time, or after CAL_VERSION changed: zero state where missing, the company\n'
             '# type\'s numbers, its first cost. A company type PMR does not know (another mod) has no goods lines.\n'
             'pmr_cc_init = {\n'
             + ''.join(f'\tif = {{ limit = {{ NOT = {{ has_variable = {x} }} }} set_variable = {{ name = {x} value = 0 }} }}\n'
                       for x in zero)
             + chain + f'\telse = {{\n\t\t{dflt}\n\t}}\n'
             f'\tset_variable = {{ name = pmr_cc_on value = {CAL_VERSION} }}\n'
             '\tpmr_cc_set_cost = yes\n\tpmr_cc_derive = yes\n}\n\n')
    # Cost of the next point.
    costs = ''.join(f'\t{"if" if L == 0 else "else_if"} = {{ limit = {{ var:pmr_cc_level <= {L} }} '
                    f'set_variable = {{ name = pmr_cc_cost value = {point_cost(L)} }} }}\n' for L in range(MAX_LEVEL))
    o.append('# Funds for the next point: 100 x (level + 1)^1.8 + 700, HoI4\'s curve.\n'
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
    # Derived numbers.
    d = ''
    for a in ARMS:
        ks = ARM_LINES[a]
        d += f'\tset_variable = {{ name = pmr_cc_n_{a} value = var:pmr_cc_{ks[0]} }}\n'
        d += ''.join(f'\tchange_variable = {{ name = pmr_cc_n_{a} add = var:pmr_cc_{k} }}\n' for k in ks[1:])
    # a tier whose research grant is running is bought (Pat 22:28Z: Stewardship stayed locked with Safety Rules
    # bought and the Sewing Machines grant running)
    d += ''.join(f'\tif = {{ limit = {{ var:pmr_cc_gr = {ln.code} }} change_variable = {{ name = pmr_cc_n_{ln.arm} add = 1 }} }}\n'
                 for ln in LINES if ln.goods)
    d += '\tset_variable = { name = pmr_cc_nf value = 0 }\n\tset_variable = { name = pmr_cc_nfirst value = 0 }\n'
    for a in ARMS:
        d += (f'\tif = {{ limit = {{ {reached(a)} }} change_variable = {{ name = pmr_cc_nf add = 1 }} '
              f'change_variable = {{ name = pmr_cc_nfirst add = var:pmr_cc_n_{a} }} }}\n')
    d += ('\t# the founding culture\'s cost on the tab: free for the first, then the second\'s\n'
          '\tif = { limit = { var:pmr_cc_nf = 0 } set_variable = { name = pmr_cc_fcost value = 0 } }\n'
          f'\telse = {{ set_variable = {{ name = pmr_cc_fcost value = {SECOND_COST} }} }}\n')
    d += ('\t# Supply\'s cut per good: 5% a tier, never past ' + str(INPUT_CUT_CAP) + '% with the general cuts beside it\n'
          '\tset_variable = { name = pmr_cc_xsv value = var:pmr_cc_xs }\n'
          '\tchange_variable = { name = pmr_cc_xsv multiply = 5 }\n'
          f'\tset_local_variable = {{ name = pmr_cc_cap value = {INPUT_CUT_CAP} }}\n'
          '\tif = { limit = { var:pmr_cc_fx = 1 } change_local_variable = { name = pmr_cc_cap subtract = 2 } }\n'
          '\tif = { limit = { var:pmr_cc_yt = 1 } change_local_variable = { name = pmr_cc_cap subtract = 5 } }\n'
          '\tif = { limit = { var:pmr_cc_ym = 1 } change_local_variable = { name = pmr_cc_cap subtract = 10 } }\n'
          '\tif = { limit = { var:pmr_cc_xsv > local_var:pmr_cc_cap } set_variable = { name = pmr_cc_xsv value = local_var:pmr_cc_cap } }\n'
          f'\t# the wage target correction: never below -{WAGE_CUT_CAP}% from all lines (5% steps)\n'
          '\tset_variable = { name = pmr_cc_wc value = var:pmr_cc_cl }\n'
          '\tchange_variable = { name = pmr_cc_wc add = var:pmr_cc_ft }\n'
          '\tchange_variable = { name = pmr_cc_wc add = var:pmr_cc_ym }\n'
          '\tchange_variable = { name = pmr_cc_wc add = var:pmr_cc_tp }\n'
          '\tchange_variable = { name = pmr_cc_wc add = var:pmr_cc_tp }\n'
          f'\tchange_variable = {{ name = pmr_cc_wc subtract = {WAGE_CUT_CAP // 5} }}\n'
          '\tif = { limit = { var:pmr_cc_wc < 0 } set_variable = { name = pmr_cc_wc value = 0 } }\n'
          '\t# Up-skilling\'s engineer jobs at its tier\n'
          '\tset_variable = { name = pmr_cc_aev value = 0 }\n'
          + ''.join(f'\tif = {{ limit = {{ var:pmr_cc_au = {t} }} set_variable = {{ name = pmr_cc_aev value = var:pmr_cc_k_ae{t} }} }}\n'
                    for t in T3))
    # the highest goods tier the owner's technology allows
    for gl in (1, 2):
        d += f'\tset_variable = {{ name = pmr_cc_g{gl}tk value = 0 }}\n'
        first = True
        for bk, w in sorted(p.works.items(), key=lambda kv: kv[1]['idx']):
            inner = ''
            for n, t in enumerate((3, 2, 1)):
                techs = w['techs'][t - 1]
                kw = 'if' if n == 0 else 'else_if'
                if not techs:
                    inner += (f' {"else" if n else ""}' + (' = {' if n else '') + f' set_variable = {{ name = pmr_cc_g{gl}tk value = {t} }}'
                              + (' }' if n else ''))
                    break
                lim = ' '.join(f'has_technology_researched = {x}' for x in techs)
                inner += f' {kw} = {{ limit = {{ owner ?= {{ {lim} }} }} set_variable = {{ name = pmr_cc_g{gl}tk value = {t} }} }}'
            d += f'\t{"if" if first else "else_if"} = {{ limit = {{ var:pmr_cc_k_g{gl}b = {w["idx"]} }}{inner} }}\n'
            first = False
    # a research grant's cost (Pat 22:28Z): GRANT_COST per employed level for each goods line's next tier
    # (pmr_cc_gc<gl>), and whether the owner's investment pool holds it (pmr_cc_gok<gl>)
    d += ('\tset_local_variable = { name = pmr_cc_lv value = 0 }\n'
          + ladder('company_employed_levels', [(n, n) for n in LV_LADDER], 'pmr_cc_lv', '\t')
          + '\tsave_scope_as = pmr_cc_gco\n')
    for gl in (1, 2):
        d += (f'\tset_variable = {{ name = pmr_cc_gc{gl} value = 0 }}\n'
              + ''.join(f'\t{"if" if t == 1 else "else_if"} = {{ limit = {{ var:pmr_cc_g{gl} = {t - 1} }} '
                        f'set_variable = {{ name = pmr_cc_gc{gl} value = local_var:pmr_cc_lv }} '
                        f'change_variable = {{ name = pmr_cc_gc{gl} multiply = {GRANT_COST[t - 1]} }} }}\n' for t in T3)
              + f'\tset_variable = {{ name = pmr_cc_gok{gl} value = 0 }}\n'
              f'\tif = {{ limit = {{ owner ?= {{ investment_pool >= scope:pmr_cc_gco.var:pmr_cc_gc{gl} }} }} '
              f'set_variable = {{ name = pmr_cc_gok{gl} value = 1 }} }}\n')
    o.append('# Numbers derived from the tiers, and the goods tiers the owner\'s technology allows (each tier shows once the\n'
             '# owner has the technology of the base recipe it modifies: tier t, recipe t or the newest).\n'
             'pmr_cc_derive = {\n' + d + '}\n\n')
    # Pay and buy, per line.
    for ln in LINES:
        k = ln.key
        if ln.founding:
            pay = f'\tif = {{ limit = {{ var:pmr_cc_nf > 0 }} change_variable = {{ name = pmr_cc_pts subtract = {SECOND_COST} }} }}\n'
        else:
            pay = ''.join(f'\t{"if" if t == 0 else "else_if"} = {{ limit = {{ var:pmr_cc_{k} = {t} }} '
                          f'change_variable = {{ name = pmr_cc_pts subtract = {c} }} }}\n' for t, c in enumerate(ln.cost))
        if ln.goods:
            gc = f'pmr_cc_gc{ln.goods}'
            take = (f'\t# a research grant, paid from the owner\'s investment pool; the tier unlocks after {GRANT_MONTHS}\n'
                    '\t# months (pmr_cc_grant_tick)\n'
                    f'\t{player_log("CC_GRANT_COST", f"gcost=[THIS.Var({chr(39)}{gc}{chr(39)}).GetValue|0];pool=[GetPlayer.GetInvestmentPool|0];")}\n'
                    f'\tset_variable = {{ name = pmr_cc_gpay value = var:{gc} }}\n'
                    '\tchange_variable = { name = pmr_cc_gpay multiply = -1 }\n'
                    '\tsave_scope_as = pmr_cc_gco\n'
                    '\towner ?= { add_investment_pool = scope:pmr_cc_gco.var:pmr_cc_gpay }\n'
                    f'\tset_variable = {{ name = pmr_cc_gr value = {ln.code} }}\n'
                    f'\tset_variable = {{ name = pmr_cc_grt value = var:pmr_cc_{k} }}\n'
                    '\tchange_variable = { name = pmr_cc_grt add = 1 }\n'
                    '\tset_variable = { name = pmr_cc_grm value = 0 }\n')
        else:
            take = f'\tchange_variable = {{ name = pmr_cc_{k} add = 1 }}\n'
        if k == 'pg':
            pchain = ''
            n = 0
            for c, v in sorted(p.comp.items()):
                if v['pvars']:
                    pchain += (f'\t{"if" if n == 0 else "else_if"} = {{ limit = {{ is_company_type = company_type:{c} }} '
                               + ' '.join(f'set_variable = {x}' for x in v['pvars']) + ' }\n')
                    n += 1
            take += '\t# Hallmark Goods: the variable its prestige goods wait for (05_prestige_goods)\n' + pchain
        pool = 'pool=[GetPlayer.GetInvestmentPool|0];' if ln.goods else ''
        o.append(f'pmr_cc_buy_{k} = {{\n{pay}{take}\tpmr_cc_after_buy = yes\n'
                 f'\t{player_log("CC_BUY", f"line={k};{pool}")}\n}}\n\n')
    o.append('pmr_cc_after_buy = {\n\tpmr_cc_derive = yes\n\tsave_scope_as = pmr_cc_co\n\tpmr_cc_apply = yes\n}\n\n')
    # Grants.
    flag = ''.join(f'\t\t{"if" if n == 0 else "else_if"} = {{ limit = {{ var:pmr_cc_k_g$G$b = {w["idx"]} }} '
                   f'set_global_variable = pmr_cw_on_{short(bk)} }}\n'
                   for n, (bk, w) in enumerate(sorted(p.works.items(), key=lambda kv: kv[1]['idx'])))
    o.append('# Goods line $G$: its building\'s ticks blend the works members in from now on (works_effect).\n'
             f'pmr_cc_works_on = {{\n{flag}}}\n\n'
             f'# Monthly: a running grant fills its bar; after {GRANT_MONTHS} months the tier is the company\'s.\n'
             'pmr_cc_grant_tick = {\n\tif = {\n\t\tlimit = { var:pmr_cc_gr > 0 }\n'
             '\t\tchange_variable = { name = pmr_cc_grm add = 1 }\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_cc_grm >= {GRANT_MONTHS} }}\n'
             '\t\t\tif = { limit = { var:pmr_cc_gr = 5 } set_variable = { name = pmr_cc_g1 value = var:pmr_cc_grt } pmr_cc_works_on = { G = 1 } }\n'
             '\t\t\telse = { set_variable = { name = pmr_cc_g2 value = var:pmr_cc_grt } pmr_cc_works_on = { G = 2 } }\n'
             f'\t\t\t{player_log("CC_GRANT_DONE")}\n'
             '\t\t\tset_variable = { name = pmr_cc_gr value = 0 }\n'
             '\t\t\tset_variable = { name = pmr_cc_grt value = 0 }\n'
             '\t\t\tset_variable = { name = pmr_cc_grm value = 0 }\n'
             '\t\t\tpmr_cc_after_buy = yes\n\t\t}\n\t}\n}\n\n')
    # A click.
    click = ''
    for i, ln in enumerate(LINES):
        click += (f'\t{"if" if i == 0 else "else_if"} = {{\n\t\tlimit = {{ scope:line = {ln.code} pmr_cc_open_{ln.key} = yes '
                  f'pmr_cc_afford_{ln.key} = yes }}\n\t\tpmr_cc_buy_{ln.key} = yes\n\t}}\n')
    o.append('# The player clicked the next node of line scope:line (Line.code in company_culture.py): it is bought with\n'
             '# points already earned, or nothing happens (Pat 12:37Z: no queue).\n'
             'pmr_cc_click = {\n\tsave_scope_as = pmr_cc_co\n\tpmr_cc_derive = yes\n' + click + '\tpmr_cc_mirror = yes\n}\n\n')
    # AI.
    steps = ('\tif = {\n\t\tlimit = { var:pmr_cc_nf = 0 }\n\t\trandom_list = {\n'
             '\t\t\t3 = { pmr_cc_buy_fe = yes }\n\t\t\t3 = { pmr_cc_buy_fx = yes }\n'
             '\t\t\t2 = { pmr_cc_buy_fs = yes }\n\t\t\t2 = { pmr_cc_buy_ft = yes }\n\t\t}\n\t}\n'
             '\telse_if = {\n\t\tlimit = { var:pmr_cc_nf = 1 var:pmr_cc_nfirst >= ' + str(REACH) + ' }\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_cc_pts >= {SECOND_COST} pmr_cc_open_fs = yes pmr_cc_open_ft = yes }}\n'
             '\t\t\trandom_list = {\n\t\t\t\t1 = { pmr_cc_buy_fs = yes }\n\t\t\t\t1 = { pmr_cc_buy_ft = yes }\n\t\t\t}\n\t\t}\n'
             f'\t\telse_if = {{\n\t\t\tlimit = {{ var:pmr_cc_pts >= {SECOND_COST} pmr_cc_open_fe = yes pmr_cc_open_fx = yes }}\n'
             '\t\t\trandom_list = {\n\t\t\t\t1 = { pmr_cc_buy_fe = yes }\n\t\t\t\t1 = { pmr_cc_buy_fx = yes }\n\t\t\t}\n\t\t}\n\t}\n')
    for k, t in AI_ORDER:
        pool = f' var:pmr_cc_gok{BY_KEY[k].goods} = 1' if BY_KEY[k].goods else ''
        steps += (f'\telse_if = {{\n\t\tlimit = {{ var:pmr_cc_{k} < {t} pmr_cc_open_{k} = yes{pool} }}\n'
                  f'\t\tif = {{ limit = {{ pmr_cc_afford_{k} = yes }} pmr_cc_buy_{k} = yes }}\n\t}}\n')
    o.append('# AI companies (Pat 04:00Z: yes): a founding culture at random, a second once allowed, then the first open\n'
             '# step of AI_ORDER, bought when affordable, otherwise saved for.\n'
             'pmr_cc_ai_step = {\n' + steps + '}\n\n'
             'pmr_cc_ai_buy = {\n\tif = {\n\t\tlimit = { var:pmr_cc_pts >= 1 }\n\t\tpmr_cc_ai_step = yes\n'
             '\t\tif = { limit = { var:pmr_cc_pts >= 1 } pmr_cc_ai_step = yes }\n\t}\n}\n\n')
    # Traits on the executive.
    def line_fx(k, n):
        keys = [generic_trait(k, t) for t in range(1, n + 1)]
        out = ''
        for t in range(n, 0, -1):
            kw = 'if' if t == n else 'else_if'
            cond = f'var:pmr_cc_{k} >= {t}' if t == n else f'var:pmr_cc_{k} = {t}'
            out += f'\t\t{kw} = {{\n\t\t\tlimit = {{ scope:pmr_cc_co = {{ {cond} }} }}\n'
            out += ''.join(f'\t\t\tif = {{ limit = {{ has_trait = {x} }} remove_trait = {x} }}\n'
                           for m, x in enumerate(keys, 1) if m != t)
            out += f'\t\t\tif = {{ limit = {{ NOT = {{ has_trait = {keys[t - 1]} }} }} add_trait = {keys[t - 1]} }}\n\t\t}}\n'
        out += '\t\telse = {\n' + ''.join(f'\t\t\tif = {{ limit = {{ has_trait = {x} }} remove_trait = {x} }}\n'
                                          for x in keys) + '\t\t}\n'
        return out
    lines_fx = ''
    for k in dict.fromkeys(k for k, _t in GENERIC):
        lines_fx += f'\t\t# {k}\n' + line_fx(k, max(t for kk, t in GENERIC if kk == k))
    keyed = ''.join(f'\t\tif = {{ limit = {{ has_trait = {key} NOT = {{ scope:pmr_cc_co = {{ {w} }} }} }} remove_trait = {key} }}\n'
                    f'\t\tif = {{ limit = {{ NOT = {{ has_trait = {key} }} scope:pmr_cc_co = {{ {w} }} }} add_trait = {key} }}\n'
                    for key, _i, _m, w in keyed_traits(p))
    o.append('# The executive\'s traits for the company\'s tiers. An executive who came from another company with Culture\n'
             '# traits loses them first (pmr_cc_strip). Company scope.\n'
             'pmr_cc_apply = {\n\tsave_scope_as = pmr_cc_co\n\texecutive ?= {\n'
             '\t\tif = {\n\t\t\tlimit = {\n\t\t\t\thas_variable = pmr_cc_of\n\t\t\t\tNOT = { var:pmr_cc_of ?= scope:pmr_cc_co }\n\t\t\t}\n'
             '\t\t\tpmr_cc_strip = yes\n\t\t}\n'
             '\t\tset_variable = { name = pmr_cc_of value = scope:pmr_cc_co }\n'
             + lines_fx + keyed + '\t}\n}\n\n')
    every = [generic_trait(k, t) for k, t in GENERIC] + [key for key, *_r in keyed_traits(p)]
    o.append('# Character scope: every Company Culture trait off. When an executive changes company and on disbanding.\n'
             'pmr_cc_strip = {\n' + ''.join(f'\tif = {{ limit = {{ has_trait = {x} }} remove_trait = {x} }}\n' for x in every)
             + '\tremove_variable = pmr_cc_of\n}\n\n')
    # Node states.
    states = ''
    for ln in LINES:
        k = ln.key
        states += f'\t# {k}\n\tset_variable = {{ name = pmr_cc_pick_{k} value = 0 }}\n'
        for t in range(1, ln.tiers + 1):
            st = f'pmr_cc_st_{k}_{t}'

            def s(n):
                return f'set_variable = {{ name = {st} value = {n} }}'
            states += f'\tif = {{ limit = {{ var:pmr_cc_{k} >= {t} }} {s(4)} }}\n'
            if ln.founding:
                states += (f'\telse_if = {{ limit = {{ {ruled(ln.arm)} }} {s(5)} }}\n'
                           f'\telse_if = {{ limit = {{ var:pmr_cc_nf = 0 }} {s(1)} set_variable = {{ name = pmr_cc_pick_{k} value = 1 }} }}\n'
                           f'\telse_if = {{\n\t\tlimit = {{ var:pmr_cc_nfirst >= {REACH} }}\n'
                           f'\t\tif = {{ limit = {{ var:pmr_cc_pts >= {SECOND_COST} }} {s(1)} '
                           f'set_variable = {{ name = pmr_cc_pick_{k} value = 1 }} }}\n\t\telse = {{ {s(2)} }}\n\t}}\n'
                           f'\telse = {{ {s(0)} }}\n')
                continue
            if ln.goods:
                states += f'\telse_if = {{ limit = {{ var:pmr_cc_gr = {ln.code} var:pmr_cc_grt = {t} }} {s(6)} }}\n'
            na = not_available(ln)
            if na:
                states += f'\telse_if = {{ limit = {{ {na} }} {s(7)} }}\n'
            states += (f'\telse_if = {{ limit = {{ OR = {{ {" ".join(ruled(a) for a in ln.arms)} }} }} {s(5)} }}\n'
                       f'\telse_if = {{ limit = {{ NOT = {{ AND = {{ {" ".join(arm_ok(ln))} }} }} }} {s(3)} }}\n')
            conds = tier_conds(ln, t)
            busy = f'var:pmr_cc_gr = 0 var:pmr_cc_gok{ln.goods} = 1 ' if ln.goods else ''
            states += (f'\telse_if = {{\n\t\tlimit = {{ {" ".join(conds)} }}\n'
                       f'\t\tif = {{ limit = {{ {busy}var:pmr_cc_pts >= {ln.cost[t - 1]} }} {s(1)} '
                       f'set_variable = {{ name = pmr_cc_pick_{k} value = 1 }} }}\n\t\telse = {{ {s(2)} }}\n\t}}\n')
            if ln.goods:
                states += (f'\telse_if = {{ limit = {{ {" ".join(c for c in conds if "tk >=" not in c)} }} {s(8)} }}\n')
            states += f'\telse = {{ {s(0)} }}\n'
    copies = ''.join(f'\t\tif = {{ limit = {{ scope:pmr_cc_co = {{ has_variable = {x} }} }} '
                     f'set_variable = {{ name = {x} value = scope:pmr_cc_co.var:{x} }} }}\n'
                     f'\t\telse_if = {{ limit = {{ has_variable = {x} }} remove_variable = {x} }}\n' for x in MIRRORED)
    o.append('# The tab\'s numbers, mirrored onto the executive (the panel reads Company.GetExecutive.MakeScope). Node states\n'
             '# pmr_cc_st_<line>_<tier>: 0 locked (a tier before it, its needs or the gate), 1 next and affordable (a click\n'
             '# buys it), 2 next but not enough points (or another grant running), 3 its arm not chosen, 4 completed,\n'
             '# 5 ruled out by the opposed arm, 6 its research grant running, 7 not for this company, 8 waiting for the\n'
             '# technology of its base recipe. pmr_cc_pick_<line>: the line\'s next node can be bought.\n'
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
    o.append('# Monthly, every company in the world (from each country\'s monthly pulse). The tab\'s mirror only for the\n'
             '# player\'s companies; an AI company\'s is brought up to date when its tab opens (pmr_cc_refresh_sgui).\n'
             'pmr_cc_tick = {\n\tsave_scope_as = pmr_cc_co\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:pmr_cc_on ?= {CAL_VERSION} }} }}\n\t\tpmr_cc_init = yes\n\t}}\n'
             '\tpmr_cc_earn = yes\n\tpmr_cc_grant_tick = yes\n\tpmr_cc_derive = yes\n'
             '\tif = {\n\t\tlimit = { owner ?= { is_player = no } }\n\t\tpmr_cc_ai_buy = yes\n\t}\n'
             '\tif = {\n\t\tlimit = { executive ?= { NOT = { var:pmr_cc_of ?= scope:pmr_cc_co } } }\n\t\tpmr_cc_apply = yes\n\t}\n'
             '\tif = {\n\t\tlimit = { owner ?= { is_player = yes } }\n\t\tpmr_cc_mirror = yes\n'
             f'\t\t{log_line("CC")}\n\t}}\n}}\n\n')
    o.append('# The tab was opened, a company was founded or the game started: bring it up to date without earning.\n'
             'pmr_cc_refresh = {\n\tsave_scope_as = pmr_cc_co\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:pmr_cc_on ?= {CAL_VERSION} }} }}\n\t\tpmr_cc_init = yes\n\t}}\n'
             '\tpmr_cc_derive = yes\n'
             '\tif = {\n\t\tlimit = { executive ?= { NOT = { var:pmr_cc_of ?= scope:pmr_cc_co } } }\n\t\tpmr_cc_apply = yes\n\t}\n'
             '\tpmr_cc_mirror = yes\n}\n\n')
    o.append('# Character scope (an executive, from the tab): the owner\'s company this character runs, scope:line kept.\n'
             'pmr_cc_with_company = {\n\tsave_scope_as = pmr_cc_exec\n'
             '\towner ?= {\n\t\tevery_company = {\n\t\t\tlimit = { executive ?= scope:pmr_cc_exec }\n\t\t\t$EFFECT$ = yes\n\t\t}\n\t}\n}\n\n')
    return ''.join(o)


def triggers():
    o = ['# Company Culture (company_culture.py). Company scope.\n\n'
         '# pmr_cc_open_<line>: the line\'s next tier can be bought, points aside: its arms chosen (both, for a shared\n'
         '# node), the tier before it, its needs, the gate (a shared charter of its arm, for the outer half), and for a\n'
         '# goods line its technology and no grant running.\n']
    for ln in LINES:
        k = ln.key
        if ln.founding:
            body = (f'\tvar:pmr_cc_{k} = 0\n\tNOT = {{ {ruled(ln.arm)} }}\n'
                    f'\tOR = {{ var:pmr_cc_nf = 0 var:pmr_cc_nfirst >= {REACH} }}\n')
        else:
            alts = ''.join(f'\t\tAND = {{ {" ".join(tier_conds(ln, t))} }}\n' for t in range(1, ln.tiers + 1))
            na = not_available(ln)
            body = (''.join(f'\t{c}\n' for c in arm_ok(ln))
                    + (f'\tNOT = {{ {na} }}\n' if na else '')
                    + ('\tvar:pmr_cc_gr = 0\n' if ln.goods else '')
                    + f'\tOR = {{\n{alts}\t}}\n')
        o.append(f'pmr_cc_open_{k} = {{\n{body}}}\n\n')
    o.append('# The points for each line\'s next tier.\n')
    for ln in LINES:
        if ln.founding:
            alts = f'\t\tvar:pmr_cc_nf = 0\n\t\tvar:pmr_cc_pts >= {SECOND_COST}\n'
        else:
            alts = ''.join(f'\t\tAND = {{ var:pmr_cc_{ln.key} = {t} var:pmr_cc_pts >= {c} }}\n' for t, c in enumerate(ln.cost))
        pool = f'\tvar:pmr_cc_gok{ln.goods} = 1\n' if ln.goods else ''
        o.append(f'pmr_cc_afford_{ln.key} = {{\n{pool}\tOR = {{\n{alts}\t}}\n}}\n\n')
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
            '\teffect = {\n\t\tpmr_cc_with_company = { EFFECT = pmr_cc_refresh }\n\t}\n}\n\n'
            '# The tab and its Open button: as the refresh, and the executive kept on the viewing player\'s country\n'
            '# (pmr_cc_exec), where the full-screen wheel (ingame_hud.gui, outside the company panel) finds the company.\n'
            'pmr_cc_view_sgui = {\n\tscope = character\n\tsaved_scopes = { player }\n'
            '\teffect = {\n\t\tscope:player = {\n\t\t\tset_variable = { name = pmr_cc_exec value = root }\n\t\t}\n'
            '\t\tpmr_cc_with_company = { EFFECT = pmr_cc_refresh }\n\t}\n}\n')


ON_ACTIONS = '''# Company Culture (company_culture.py). Appended to vanilla on_actions the documented way.
on_game_started_after_lobby = { on_actions = { pmr_cc_game_started } }
on_monthly_pulse_country = { on_actions = { pmr_cc_monthly_country } }
on_company_established = { on_actions = { pmr_cc_on_company_established } }
on_company_disbanded = { on_actions = { pmr_cc_on_company_disbanded } }

# No root. Every company's numbers and tab from the first day, before any monthly pulse.
pmr_cc_game_started = {
	effect = {
		every_country = {
			every_company = {
				pmr_cc_refresh = yes
			}
		}
	}
}

# Root = country. Every company earns, runs its grant, buys (AI companies) and keeps its executive's traits.
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
			pmr_cc_refresh = yes
			{{LOG}}
		}}
	}}
	ai_chance = {{ value = 0 }}
}}

# Test builds only: every running research grant of the player's companies completes at the next monthly tick, so the
# special method can be checked without waiting {GRANT_MONTHS} months. Writes PMR;rec=CC_TEST_GRANT lines.
pmr_cc_test_grant_decision = {{
	is_shown = {{ always = yes }}
	possible = {{ always = yes }}
	when_taken = {{
		every_company = {{
			limit = {{ has_variable = pmr_cc_gr var:pmr_cc_gr > 0 }}
			set_variable = {{ name = pmr_cc_grm value = {GRANT_MONTHS - 1} }}
			{{LOG_GRANT}}
		}}
	}}
	ai_chance = {{ value = 0 }}
}}
'''


def charters(game):
    """The vanilla charter types, each possible only for a company holding its node (BUILD-SPEC section 3)."""
    text = open(os.path.join(game, CHARTER_FILE), encoding='utf-8-sig').read()
    var = {v: k for k, v in CHARTERS.items()}
    edits = []
    for n in pdx.parse(text):
        if not (n.is_block and n.key in var):
            continue
        k = var[n.key]
        check = f'var:pmr_cc_{k} ?= 1  # PMR Company Culture: the {BY_KEY[k].names[0]} node'
        pos = pdx.get(n.value, 'possible')
        if pos:
            edits.append((pos.start + text[pos.start:].index('{') + 1, f'\n\t\t{check}'))
        else:
            edits.append((n.start + text[n.start:].index('{') + 1, f'\n\tpossible = {{\n\t\t{check}\n\t}}'))
        aip = pdx.get(n.value, 'ai_possible')
        if not aip:
            fail(CHARTER_FILE, f'{n.key} has no ai_possible')
        edits.append((aip.start + text[aip.start:].index('{') + 1, f'\n\t\t{check}'))
    if len({e for e in edits}) != 2 * len(CHARTERS):
        fail(CHARTER_FILE, f'found {len(edits) // 2} of the {len(CHARTERS)} charter types')
    for at, ins in sorted(edits, reverse=True):
        text = text[:at] + ins + text[at:]
    return ('# PMR Company Culture (company_culture.py): vanilla\'s charter types, each possible only for a company that\n'
            '# holds its node on the Company Culture wheel. The engine drops a charter whose possible fails.\n' + text)


DEFINE = ('# PMR Company Culture: charters cost no authority (BUILD-SPEC section 3). Game-wide. Vanilla: 100.\n'
          'NEconomy = {\n\tCOMPANY_CHARTER_AUTHORITY_COST = 0\n}\n')


def ai_value_tail(company_types):
    """Expanded Works for private_investment.py's pmr_ai_value_<b> (read in the state's scope): the building's ai_value
    x SC_AI_MULT while the state's owner has a company that lists the type and holds that tier. Ends the value: it
    multiplies everything added before it."""
    types = ' '.join(f'is_company_type = company_type:{c}' for c in company_types)
    out = ''
    for t in range(3, 0, -1):
        out += (f'\t{"if" if t == 3 else "else_if"} = {{\n\t\tlimit = {{ owner ?= {{ any_company = {{ var:pmr_cc_sc ?= {t} '
                f'OR = {{ {types} }} }} }} }}\n\t\tmultiply = {fmt(SC_AI_MULT[t - 1])}\n\t}}\n')
    return '\t# PMR Company Culture: Expanded Works (company_culture.py)\n' + out


# ---------------------------------------------------------------------------------------------------------------
# Methods sub-heading (kept from the 10-14 tab: every recipe of the company's buildings)

def method_rows(report, pms, comps):
    listed = {b for bts, _pv in comps.values() for b in bts}
    elec = {a['building']: a['electric_recipe'] for a in report['automation'] if a.get('electric_recipe')}
    split = {a['building'] for a in report['automation'] if a.get('split')}
    rows = {}
    for t in report['treated']:
        b = t['building']
        if b not in listed:
            continue
        out, last = [], []
        for key in t['recipes']:
            if b in split and key not in pms:
                continue
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
    return rows, sorted(listed - set(rows)), split


def pm_info(game):
    out = {}
    for path in glob.glob(os.path.join(game, 'common', 'production_methods', '*.txt')):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and n.key:
                tex = pdx.get(n.value, 'texture')
                ut = pdx.get(n.value, 'unlocking_technologies')
                out[n.key] = (tex.value if tex else None, pdx.items(ut) if ut else [])
    return out


def unlock_values(rows):
    out = ['# Company Culture Methods list (company_culture.py). Country scope.\n'
           '# pmr_cc_unl_<recipe>: 1 once the country has researched every technology the recipe needs.\n'
           '# pmr_cc_new_<b>: the newest recipe of the building type the country can run (its index, from 1).\n\n'
           '# 1 once the player has opened a Company Culture tab (pmr_cc_view_sgui): the full-screen wheel shows only then.\n'
           'pmr_cc_viewing = {\n\tvalue = 0\n\tif = {\n\t\tlimit = { has_variable = pmr_cc_exec }\n\t\tvalue = 1\n\t}\n}\n\n']
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
# Text

def custom_loc(p):
    """Character scope (the executive, mirrored numbers): the company-specific names and goods on the wheel."""
    out = ['# Company Culture (company_culture.py). Character scope: a company\'s executive, which holds the company\'s\n'
           '# numbers (pmr_cc_mirror).\n\n']

    def entry(key, cases, default='PMR_EMPTY'):
        body = ''.join(f'\ttext = {{\n\t\ttrigger = {{ {trig} }}\n\t\tlocalization_key = {lk}\n\t}}\n' for trig, lk in cases)
        return (f'{key} = {{\n\ttype = character\n\trandom_valid = no\n{body}'
                f'\ttext = {{\n\t\tlocalization_key = {default}\n\t}}\n}}\n')
    for gl in (1, 2):
        for t in T3:
            out.append(entry(f'pmr_cc_n_g{gl}_{t}', [(f'var:pmr_cc_k_g{gl}r ?= {r}', f'PMR_CC_ENG_{r}_{t}')
                                                     for r in range(1, len(ENG_ROWS) + 1)], f'PMR_CC_NAME_g1_{t}'))
    for t in T3:
        out.append(entry(f'pmr_cc_n_xs_{t}', [(f'var:pmr_cc_k_xr ?= {r}', f'PMR_CC_EXP_{r}_{t}')
                                              for r in range(1, len(EXP_ROWS) + 1)], f'PMR_CC_NAME_xs_{t}'))
        out.append(entry(f'pmr_cc_n_au_{t}', [(f'var:pmr_cc_k_ar ?= {r}', f'PMR_CC_UPS_{r}_{t}')
                                              for r in range(1, len(UPSKILL_ROWS) + 1)], f'PMR_CC_NAME_au_{t}'))
    for slot in ('g1g', 'g2g', 'g1i', 'g2i', 'xg1', 'xg2'):
        out.append(entry(f'pmr_cc_good_{slot}', [(f'var:pmr_cc_k_{slot} ?= {gi(p, g)}', g) for g in p.goods]))
    for gl in (1, 2):
        for t in T3:
            out.append(entry(f'pmr_cc_tech_g{gl}_{t}', [(f'var:pmr_cc_k_g{gl}b ?= {w["idx"]}', f'PMR_CC_TECHS_{w["idx"]}_{t}')
                                                        for _bk, w in sorted(p.works.items()) if w['techs'][t - 1]]))
    for ln in LINES:
        for t in range(1, ln.tiers + 1):
            out.append(entry(f'pmr_cc_why_{ln.key}_{t}', why_cases(ln, t), 'PMR_CC_WHY_LOCKED'))
    out.append(entry('pmr_cc_fx_xs_2', [('var:pmr_cc_k_xg2 ?= 0', 'PMR_EMPTY')], 'PMR_CC_XS_GOOD2'))
    out.append(entry('pmr_cc_fx_pg', [('var:pmr_cc_k_pg ?= 0', 'PMR_EMPTY')], 'PMR_CC_FX_pg_YES'))
    return '\n'.join(out)


def why_cases(ln, t):
    """Custom loc cases naming why node (line, tier) is in its state (pmr_cc_st_<line>_<tier>, pmr_cc_states), for the
    first line of its tooltip (Pat 20:37Z: "This needs to show in the tool tip ... when its technology locked")."""
    k = ln.key
    st = f'var:pmr_cc_st_{k}_{t}'
    cases = [(f'{st} ?= 1', 'PMR_CC_WHY_BUY'), (f'{st} ?= 4', 'PMR_CC_WHY_DONE'), (f'{st} ?= 6', 'PMR_CC_WHY_GRANT')]
    if ln.goods:
        cases += [(f'{st} ?= 2 var:pmr_cc_gr > 0', 'PMR_CC_WHY_BUSY'),
                  (f'{st} ?= 2 var:pmr_cc_gok{ln.goods} ?= 0', f'PMR_CC_WHY_POOL_g{ln.goods}'),
                  (f'{st} ?= 8', f'PMR_CC_WHY_TECH_g{ln.goods}_{t}')]
    cases.append((f'{st} ?= 2', 'PMR_CC_WHY_POINTS'))
    if not ln.founding:   # a founding node is never waiting for its arm (q29 error.log: no PMR_CC_WHY_ARM_fe)
        cases.append((f'{st} ?= 3', f'PMR_CC_WHY_ARM_{k}'))
    cases += [(f'{st} ?= 5 var:pmr_cc_{FOUND[OPP[a]]} ?= 1', f'PMR_CC_WHY_RULED_{OPP[a]}') for a in ln.arms]
    cases.append((f'{st} ?= 7', 'PMR_CC_WHY_NA_pg' if k == 'pg' else 'PMR_CC_WHY_NA'))
    if ln.founding:
        cases.append((f'{st} ?= 0', 'PMR_CC_WHY_REACH'))
        return cases
    if t > 1:
        cases.append((f'{st} ?= 0 NOT = {{ var:pmr_cc_{k} ?= {t - 1} }}', f'PMR_CC_WHY_PREV_{k}_{t}'))
    if t in ln.outer:
        cases.append((f'{st} ?= 0 NOT = {{ {outer_ok(ln.arm).replace(" = 1", " ?= 1")} }}', f'PMR_CC_WHY_GATE_{ln.arm}'))
    if t == 1 and ln.links:
        cases.append((f'{st} ?= 0', f'PMR_CC_WHY_NEEDS_{k}'))
    return cases


def node_name(k, t):
    """The loc key or text a node's title shows."""
    if k in ('g1', 'g2', 'xs', 'au'):
        return f"[Character.GetCustom('pmr_cc_n_{k}_{t}')]"
    return f'$PMR_CC_NAME_{k}_{t}$'


def V(name):
    return f"[Character.MakeScope.Var('{name}').GetValue|0]"


def money(name):
    return f"[Character.MakeScope.Var('{name}').GetValue|D]"


def fx_lines(k, t):
    """The bullets a node shows (one per benefit, the value green for a gain and red for a cost; one per good, written
    good, value, then input or output). Goods-line nodes are drawn by cc_wheel (name, logo, net line, note)."""
    pct = lambda x: f'{x:+d}%'.replace('-', '−')   # noqa: E731
    G = lambda label, val: f'• {label} #P {val}#!'     # noqa: E731
    R = lambda label, val: f'• {label} #N {val}#!'     # noqa: E731
    good = lambda slot: f"[Character.GetCustom('pmr_cc_good_{slot}')]"   # noqa: E731
    sc = {1: 10, 2: 15, 3: 25}
    out = {
        ('fe', 1): [G('Output', '+3%'), R('Input goods', '+3%')],
        ('fx', 1): [G('Input goods', '−2%')],
        ('fs', 1): [G('Job attractiveness', '+10%')],
        ('ft', 1): [G('Wage target', '−5%')],
        ('sf', 1): [G('Dangerous conditions', '−20%')],
        ('fw', 1): [R('Wage target', '+10%')],
        ('fw', 2): [R('Wage target', '+20%'), G('Job attractiveness', '+20%')],
        ('fw', 3): [G('Worker dividends', '+15%')],
        ('ho', 1): [G('Standard of living', '+1')],
        ('ho', 2): [G('Standard of living', '+2')],
        ('ct', 1): [G('Standard of living', '+1'), G('Job attractiveness', '+15%')],
        ('pg', 1): ["[Character.GetCustom('pmr_cc_fx_pg')]"],
        ('tp', 1): [G('Wage target', '−10%')],
        ('tp', 2): [G('Wage target', '−20%')],
        ('ys', 1): [G('Output', '+5%'), G('Engineers', '+5%')],
        ('yi', 1): [G('Laborers', '−15%'), f'• $tools$ #N +5%#! input'],
        ('yt', 1): [G('Input goods', '−5%'), G('Job attractiveness', '+10%')],
        ('ym', 1): [G('Input goods', '−10%'), G('Wage target', '−5%')],
    }
    for tt in T3:
        out[('xs', tt)] = [f'• {good("xg1")} #P {pct(-5 * tt)}#! input', f"[Character.GetCustom('pmr_cc_fx_xs_2')]",
                           G('Throughput', pct(5 * tt))]
        out[('sc', tt)] = [G('Throughput', pct(sc[tt])), G('AI build weight', f'×{fmt(SC_AI_MULT[tt - 1])}')]
        out[('au', tt)] = [G('Laborers', pct(-round(UPSKILL_CUT[tt - 1] * 100))),
                           f'• Engineers #P +{V(f"pmr_cc_k_ae{tt}")}#! per level']
        out[('cl', tt)] = [G('Laborers', pct(5 * tt)), G('Wage target', pct(-5 * tt))]
    return out.get((k, t), [])


def localization(p, rows, kept_split):
    co = '[Company.GetNameNoFormatting]'
    loc = [
        ' PMR_CC_TAB:0 "Company Culture"',
        ' PMR_CC_TAB_TT:0 "Prosperity earns points; points buy bonuses."',
        f' PMR_CC_LEVEL:0 "Culture Level #v {V("pmr_cc_level")}#!"',
        f' PMR_CC_POINTS:0 "#v {V("pmr_cc_pts")}#! points"',
        ' PMR_CC_LEVEL_TT:0 "#header Culture points#!\\nEarned from prosperity, spent on nodes."',
        f' PMR_CC_BAR:0 "#v {V("pmr_cc_funds")}#! / {V("pmr_cc_cost")}"',
        f' PMR_CC_BAR_TT:0 "#header Next point#!\\nProsperity #v {V("pmr_cc_prosp")}#! × size #v ×[Character.MakeScope.Var(\'pmr_cc_size\').GetValue|1]#! = #v +{V("pmr_cc_rate")}#! a month"',
        ' PMR_CC_SHOW:0 "Show Company Culture"',
        ' PMR_CC_SHOW_TT:0 "Not read in yet; updates monthly."',
        f' PMR_CC_HUB_TT:0 "#header Founding cultures#!\\nFirst is free; a second costs {SECOND_COST} points after {REACH} nodes.\\nEngineering excludes Expansion; Stewardship excludes Providence."',
        ' PMR_CC_OPEN:0 "Open Company Culture"',
        ' PMR_CC_FULL_TITLE:0 "Company Culture: [Company.GetNameNoFormatting]"',
        ' PMR_CC_BACK_TT:0 "Back to the company panel"',
        ' PMR_CC_WHY_BUY:0 "#P Ready to buy#!"',
        ' PMR_CC_WHY_DONE:0 "#P Bought.#!"',
        ' PMR_CC_WHY_GRANT:0 "#v Grant running#!"',
        ' PMR_CC_WHY_BUSY:0 "#N Another grant running#!"',
        *[f' PMR_CC_WHY_POOL_g{gl}:0 "#N Investment pool needs @money!{money(f"pmr_cc_gc{gl}")}#!"'
          for gl in (1, 2)],
        ' PMR_CC_WHY_POINTS:0 "#N Not enough points#!"',
        ' PMR_CC_WHY_NA:0 "#N Not open to this company.#!"',
        ' PMR_CC_WHY_NA_pg:0 "#N No prestige goods#!"',
        f' PMR_CC_WHY_REACH:0 "#N Needs {REACH} nodes in the first arm#!"',
        ' PMR_CC_WHY_LOCKED:0 "#N Locked.#!"',
        ' PMR_CC_ARM_eng:0 "E N G I N E E R I N G"',
        ' PMR_CC_ARM_stw:0 "S T E W A R D S H I P"',
        ' PMR_CC_ARM_exp:0 "E X P A N S I O N"',
        ' PMR_CC_ARM_prv:0 "P R O V I D E N C E"',
        ' PMR_CC_FX_pg_YES:0 "• Produces its prestige goods"',
        f" PMR_CC_XS_GOOD2:0 \"• [Character.GetCustom('pmr_cc_good_xg2')] #P −5%#! input\"",
        f' PMR_CC_GRANT_BAR:0 "Grant #v {V("pmr_cc_grm")}#! / {GRANT_MONTHS} months"',
        ' PMR_CC_COST_TT:0 "Culture points"',
        ' PMR_CC_METHODS_HEADER:0 "Methods"',
        ' PMR_CC_METHODS_NONE:0 "No recipes to retool"',
        f' pmr_cc_test_points_decision:0 "PMR test: {TEST_POINTS} Culture points for each of your companies"',
        f' pmr_cc_test_points_decision_desc:0 "Each of your companies gets {TEST_POINTS} Culture points."',
        ' pmr_cc_test_grant_decision:0 "PMR test: finish your companies\' research grants"',
        ' pmr_cc_test_grant_decision_desc:0 "Running grants finish next month."',
    ]
    for bk in sorted(p.works):
        for t in T3:
            loc.append(f' {works_marker(bk, t)}:0 "Company works, tier {t} share"')
        b = short(bk)
        loc += [f' pmr_cw_out_{b}:0 "Company works output"', f' pmr_cw_in_{b}:0 "Company works input"']
    # Names.
    for ln in LINES:
        for t in range(1, ln.tiers + 1):
            loc.append(f' PMR_CC_NAME_{ln.key}_{t}:0 "{ln.names[t - 1]}"')
    for r, (_g, names, _x) in enumerate(ENG_ROWS, 1):
        loc += [f' PMR_CC_ENG_{r}_{t}:0 "{names[t - 1]}"' for t in T3]
    for r, (_g, names) in enumerate(EXP_ROWS, 1):
        loc += [f' PMR_CC_EXP_{r}_{t}:0 "{names[t - 1]}"' for t in T3]
    for r, (_g, names) in enumerate(UPSKILL_ROWS, 1):
        loc += [f' PMR_CC_UPS_{r}_{t}:0 "{names[t - 1]}"' for t in T3]
    # Goods-line node text.
    pct = lambda x: f'+{round(x * 100)}%'   # noqa: E731
    for gl in (1, 2):
        for t in T3:
            out_g = f"[Character.GetCustom('pmr_cc_good_g{gl}g')]"
            in_g = f"[Character.GetCustom('pmr_cc_good_g{gl}i')]"
            # Pat 21:53Z: the output gain and the input cost on lines of their own
            loc += [f' PMR_CC_GAIN_g{gl}_{t}:0 "• #P {pct(WORKS_OUT[t - 1])} {out_g}#!"',
                    f' PMR_CC_COST_g{gl}_{t}:0 "• #N {pct(WORKS_IN[t - 1])} {in_g}#!"']
        loc += [f' PMR_CC_PMNAME_g{gl}_{t}:0 "• #yellow [Character.GetCustom(\'pmr_cc_n_g{gl}_{t}\')]#!"' for t in T3]
    # Bullets and tooltips.
    arm_title = {'eng': 'Engineering', 'stw': 'Stewardship', 'exp': 'Expansion', 'prv': 'Providence'}
    opens = {a: ' or '.join(BY_KEY[c].names[0] for c in SHARED_OF[a]) for a in ARMS}
    for a in ARMS:
        loc += [f' PMR_CC_WHY_RULED_{a}:0 "#N Ruled out by {arm_title[a]}#!"',
                f' PMR_CC_WHY_GATE_{a}:0 "#N Needs {opens[a]}#!"']
    for gl in (1, 2):
        for t in T3:
            loc.append(f" PMR_CC_WHY_TECH_g{gl}_{t}:0 \"#N Needs [Character.GetCustom('pmr_cc_tech_g{gl}_{t}')]#!\"")
    for bk, w in sorted(p.works.items()):
        for t in T3:
            if w['techs'][t - 1]:
                loc.append(f' PMR_CC_TECHS_{w["idx"]}_{t}:0 "' + ' and '.join(f'${x}$' for x in w['techs'][t - 1]) + '"')
    for ln in LINES:
        k = ln.key
        if ln.shared:
            loc.append(f' PMR_CC_WHY_ARM_{k}:0 "#N Needs {arm_title[ln.arms[0]]} and {arm_title[ln.arms[1]]}#!"')
        elif not ln.founding:
            loc.append(f' PMR_CC_WHY_ARM_{k}:0 "#N Needs {arm_title[ln.arm]}#!"')
        for t in range(2, ln.tiers + 1):
            loc.append(f' PMR_CC_WHY_PREV_{k}_{t}:0 "#N Needs {node_name(k, t - 1)}#!"')
        if ln.links:
            loc.append(f' PMR_CC_WHY_NEEDS_{k}:0 "#N Needs '
                       + ' and '.join(node_name(nk, nt) for nk, nt in ln.links) + '#!"')
    for ln in LINES:
        k = ln.key
        for t in range(1, ln.tiers + 1):
            fx = fx_lines(k, t)
            if fx and not ln.goods:   # charters have no bullets, so no key and no textbox (cc_wheel.node)
                loc.append(f' PMR_CC_FX_{k}_{t}:0 "' + '\\n'.join(fx) + '"')
            # The tooltip is the lock reason only: the card already shows the name and the bullets
            grant = (f"\\nGrant: {GRANT_MONTHS} months, @money!#v {money(f'pmr_cc_gc{ln.goods}')}#!"
                     if ln.goods else '')
            loc.append(f' PMR_CC_TT_{k}_{t}:0 "[Character.GetCustom(\'pmr_cc_why_{k}_{t}\')]{grant}"')
    # Traits.
    for (k, t), _mods in GENERIC.items():
        loc += [f' {generic_trait(k, t)}:0 "{BY_KEY[k].names[t - 1]}"',
                f' {generic_trait(k, t)}_desc:0 "Company Culture"']
    for key, _i, mods, _w in keyed_traits(p):
        if key.startswith('pmr_cc_xs_'):
            g = mods[0][0][len('goods_input_'):-len('_mult')]
            nm = f'Supply: ${g}$'
        elif key.startswith('pmr_cc_ys_'):
            nm = f'Master Craftsmen: ${mods[0][0][len("goods_output_"):-len("_mult")]}$'
        elif key.startswith('pmr_cc_ae_'):
            nm = 'Up-skilling: engineers'
        elif key.startswith('pmr_cc_cw_'):
            b = key[len('pmr_cc_cw_'):].rsplit('_', 1)
            nm = f'Works method {b[1]}: $building_{b[0]}$'
        else:
            nm = 'Wage floor'
        loc += [f' {key}:0 "{nm}"',
                f' {key}_desc:0 "Company Culture"']
    # Methods list.
    done = set()
    for b, recipes in rows.items():
        for key, _tex, techs in recipes:
            if key in done:
                continue
            done.add(key)
            need = ['Needs ' + ', '.join(f'${tk}$' for tk in techs) + '.'] if techs else []
            if key.startswith('pm_pmr_elec_'):
                need.append('Runs only where the state produces electricity.')
            need = ('\\n' + ' '.join(need)) if need else ''
            loc.append(f' PMR_CC_PM_{key}:0 "#header ${key}$#!{need}"')
    return loc


# ---------------------------------------------------------------------------------------------------------------

def write_all(game, write, header_text, report, p, out_dir):
    """Writes every file of the feature (test builds for now) and returns its loc lines."""
    comps = companies(game)
    pms = pm_info(game)
    rows, untreated, split = method_rows(report, pms, comps)
    write('common/character_traits/pmr_cc_traits.txt', header_text + traits(p))
    write('common/modifier_type_definitions/pmr_cc_modifier_types.txt', header_text + modifier_types(p, game))
    write('common/scripted_effects/pmr_cc_effects.txt', header_text + effects(p, comps))
    write('common/scripted_triggers/pmr_cc_triggers.txt', header_text + triggers())
    write('common/scripted_guis/pmr_cc_sguis.txt', header_text + sguis())
    write('common/on_actions/pmr_cc_on_actions.txt', header_text + ON_ACTIONS)
    write('common/script_values/pmr_cc_values.txt', header_text + unlock_values(rows))
    write('common/decisions/pmr_cc_test_decisions.txt', header_text + TEST_DECISION.replace('{LOG}', log_line('CC_TEST'))
          .replace('{LOG_GRANT}', log_line('CC_TEST_GRANT')))
    write('common/customizable_localization/pmr_cc_custom_loc.txt', header_text + custom_loc(p))
    write(CHARTER_FILE, charters(game))
    write('common/defines/zz_pmr_cc.txt', header_text + DEFINE)
    write(PANEL_GUI, cc_wheel.patch_panel(open(os.path.join(game, PANEL_GUI), encoding='utf-8-sig').read(), TAB), bom=False)
    write(OWN_GUI, cc_wheel.tab(p, rows, untreated, split), bom=False)
    write(cc_wheel.HUD_GUI, cc_wheel.patch_hud(open(os.path.join(game, cc_wheel.HUD_GUI), encoding='utf-8-sig').read()),
          bom=False)
    n_tex = cc_wheel.textures(out_dir)
    n_traits = len(GENERIC) + len(keyed_traits(p))
    report['company_culture'] = {
        'companies': len(p.comp), 'traits': n_traits, 'textures': n_tex, 'works_buildings': sorted(p.works),
        'goods_lines': {c: v['g'] for c, v in sorted(p.comp.items())},
        'supply': {c: v['xg'] for c, v in sorted(p.comp.items())},
        'no_goods_line': sorted(c for c, v in p.comp.items() if not v['g']),
        'works': {bk: {k: w[k] for k in ('out', 'in', 'row', 'techs')} for bk, w in sorted(p.works.items())},
        'method_rows': len(rows), 'untreated': untreated}
    print(f'company culture: {len(p.comp)} companies, {n_traits} traits, {len(p.works)} goods-line buildings '
          f'({sum(1 for v in p.comp.values() if not v["g"])} companies without a goods line), {n_tex} textures')
    return localization(p, rows, split) + goods_mult_loc(p, game)
