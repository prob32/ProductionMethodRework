"""Generate the Production Method Rework (PMR) mod from the installed game's own script.

PMR is generated, not hand-written, because it touches every recipe production method in the
game and must follow the beta as it moves. Run it against the game folder of the build you are
testing; it rewrites the mod folder in place.

    python tools/pmr/generate.py --game "G:/SteamLibrary/steamapps/common/Victoria 3/game"

With ``--release`` it writes the build players get, to pmr/release/ProductionMethodRework: no "PMR test:"
decision, no GENERATION_REPORT.json, and no PMR log lines but TRIP and AUTO_TRIP (the loop breakers) and LOADED.
The default build keeps the test tools. Both write every game language: localise.py translates the English text
from tools/pmr/translations/, and a line no table has yet stays English.

What it does, building by building (see pmr/README.md for the design):

1. The building gets one extra production method group, ``pmg_pmr_labour_<b>``, holding one
   method, ``pm_pmr_labour_<b>``, that carries nothing: it is the slot the building browser rows and
   market lists show, drawn as the gold main output good. (Until 2026-10-13 it held the default
   recipe's workforce, fixed; Pat then asked for the workforce to blend like the goods.)
2. Recipes stay vanilla production methods but carry no goods and no workforce: they mark the
   recipe the building runs (the retool target) and gate it by technology. Everything they scaled
   by workforce (goods, pollution, ...) and their employment move into share methods, and so does
   the best automation that runs without electricity from AUTOMATION_FROM_TIER (the building's
   automation groups leave it). Automation that needs electricity becomes a recipe of its own on top
   of the newest one, ``pm_pmr_elec_<b>``, inserted into the vanilla recipe group.
3. Per recipe i, a share group ``pmg_pmr_share_<b>_<i>`` holds SHARE_STEPS + 1 methods
   ``pm_pmr_share_<b>_<i>_<n>`` carrying recipe i's workforce-scaled modifiers and its employment
   x n / SHARE_STEPS.
   The state tracks how many levels run each recipe; the tick activates, in each share group, the
   method for that recipe's share of the levels. So the building's goods are the level-weighted mix
   of its recipes, in its own production figures, scaled by employment and throughput like any
   recipe. Share method n unlocks only while lock method ``pm_pmr_key_<b>_<i>_<n>`` (goods-less, in
   ``pmg_pmr_key_<b>_<i>``) or the switching lock ``pm_pmr_key_<b>_<i>_any`` is active, so the AI
   never has a second share method to pick. The tick moves the lock to ``_any``, then the share,
   then the lock to the new step, so the running share method is never left locked out. ``_any`` is
   the first method of its lock group, so a share and lock that are both unavailable settle at once
   (a new building can inherit them from two different buildings; with ``_any`` last that froze the game).
4. Hidden pseudo-buildings retool one level each per completed level, at RETOOL_SHARE of the
   building's construction cost: RETOOL_SLOTS private ones, ``building_pmr_retool_<b>_<n>``, built
   by investors who own part of the building (with ABROAD_SLOT, that one only where the player owns
   levels abroad and the others only elsewhere; without, the one site everywhere), and one government
   one, ``building_pmr_retool_gov_<b>``, queued by the government.
   Abroad the player's government retools its own levels on ``building_pmr_retool_gova_<b>``, a site the tick keeps
   standing so the upgrade button can expand it into the government construction queue.
   The government retools the levels it owns that don't run the target yet; private investors the
   rest. The building panel's Owners list shows which recipes each side's levels run.
5. Recipes switch on research: when a newer recipe becomes available the building activates it,
   which starts retooling. A recipe that needs electricity waits until the state produces it. The
   building panel hides every selector and shows the recipe's name, a bar of each recipe's share of
   the levels, and the government upgrade button; the Buildings tab shows the same per building
   and, on each building type's row, the bar and button over the whole country.

Vanilla files the mod changes are written whole under their vanilla names (file shadowing), with
only the employment lines and the extra group inserted; every other byte is the installed game's.
"""

import argparse
import collections
import glob
import json
import math
import re
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import icons  # noqa: E402
import pdx  # noqa: E402
import private_investment  # noqa: E402
import company_culture  # noqa: E402
import company_panel  # noqa: E402
import methods_row  # noqa: E402
import localise  # noqa: E402

# ---------------------------------------------------------------------------------------------
# Tunables. Change here and regenerate; nothing below hard-codes them.
N = 1                      # retool levels per real building level (Pat, 2026-10-12: one per level)
RETOOL_SHARE = 0.5         # retooling one level costs this share of the building's construction cost
GOV_FRACTION_STEP = 0.05   # resolution of the government-owned share read from the ownership trigger
# AI weight of a retool building while it has room (Pat, 2026-10-13 20:12Z): what vanilla would score an
# expansion of the building, times RETOOL_AI_MULT, so retooling a building is likelier than expanding it
# but a building that scores well above it (say a profitable plantation) still wins. Vanilla scores a
# candidate from its ai_value (base 1000, ai:831) plus 5000 x 1.5 per pound of predicted WEEKLY profit per
# employee (ai:833, ai:909). PMR stands in the building's earnings per employee, which the game gives a
# YEAR (read with RETOOL_EARNINGS_LADDER; anything under the lowest step, losses included, counts as 0), so
# a pound of earnings weighs 7500 / 52. Pat's 1838-01-01 autosave (20:06Z) bears the units out: a new
# coal mine level's predicted profit of 517 over its 5,000 workers is GBP 0.10 a week, GBP 5.4 a year,
# and PMR read its earnings as 4..8; iron mines 1,857 -> 19 a year, read as 15..30. Until then PMR
# weighed a pound at 7,500 and added 150,000, so retool sites scored 39,000..75,000 before the roll
# against 30..3,400 for new builds (a tea plantation 14,000) and took every pick. For the 48 investable
# types private_investment.py swaps RETOOL_AI_BASE for the building's own ai_value (pmr_ai_value_<b>).
RETOOL_AI_BASE = 1000
RETOOL_AI_PER_EARNING = round(7500 / 52)
RETOOL_AI_MULT = 2
RETOOL_EARNINGS_LADDER = (50, 40, 30, 25, 20, 15, 12, 10, 8, 6, 4, 2)
SHARE_STEPS = 100          # a recipe's share of the levels is blended in steps of 1 / SHARE_STEPS (1%, Pat 2026-10-13)
RETOOL_SLOTS = 2           # private retool buildings per building type: one at home, one abroad (ABROAD_SLOT)
# The last slot is the player's investors' abroad (Pat 2026-10-13 19:25Z: no level abroad ever retooled). 1.14.5's
# investment AI picks one state per building type and investor and only then tests can_build_private: Great
# Britain's 15 retool candidates abroad in the 1844 save all sat in states where the host's own slot was open and
# Britain owned no level, so none could be built, and the West Bengal coal mine (Britain's two levels, both
# slots open a year) never got one. So slots 1..ABROAD_SLOT-1 open only where investors retool at home, in
# bg_pmr_retool with foreign_investment_ai_factor = 0 (vanilla's building-group weight for investing abroad), and
# ABROAD_SLOT opens only where the player owns levels abroad (pmr_abroad_<b>), in bg_pmr_retool_abroad, so the
# player's pool finds a state its investors may build in.
# Pat, 2026-10-13 22:37Z: still only home retooling, with the West Bengal coal mine's abroad slot open since 1839.
# The state pick tests can_build_private as the host's investors would (pmr_retool_investor_abroad_<b>), so the
# abroad slot lets the host pass; and its Focus on Infrastructure weight is the investor's, not the host's
# (private_investment.py, pmr_reinvest_mult_abroad_<g>).
# Pat, 2026-10-14: one private site per building, picked by investors (ABROAD_SLOT 0: no slot of its own abroad).
# Performance review 2 measured a record per country per building type in the AI, 78% of them for the 315 retool
# types in Pat's 1837 save; slots 2..5 were four of the five private types per building. The script-queued
# test that replaced them (af82983, 672ae8e) queued levels the investment pool could not fund: the game marks
# those invalid (red cross) and the pool sat at zero. Investors queue a build only once the pool can fund it,
# and the priorities steer their picks, so they choose retooling again. The one site serves home and abroad:
# where the player owns levels abroad (pmr_abroad_<b>) the host's investors pass the investor check
# (pmr_retool_investor_abroad_<b>), and bg_pmr_retool keeps foreign pools off (foreign_investment_ai_factor 0).
# Pat, 2026-10-14 02:33Z (console, West Bengal coal mine): "I want my investors to be able to re-tool this coal mine";
# whoever owns levels and has the technology may retool. The site scored "Foreign investment factor: x0" for Britain,
# so only the East India Company's investors could build it. A foreign weight on the one site would let every pool
# pick a foreign state its investors can't build in and lose that building's retooling at home (the 1844 save
# above), so the abroad site comes back: slot 1 at home, slot 2 only where the player owns levels abroad, with
# foreign weight. 90 private retool types against 0.1.0's 225.
ABROAD_SLOT = 2
# Pat, 2026-10-14 01:09Z: the one site may be queued for several levels at once ("allowing for one level of
# re-tooling to be queued multiple levels as necessary"). So it takes all of its building's private room: investors
# may add a level to it while others are still queued or building, each level an investment of its own, scored and
# funded like any other. Its cap (pmr_cap_priv1_<b>) is what it has queued plus the room; a site under construction
# exists at level 0 (Pat's 1836 save), so level_after_queued_constructions counts every queued level against it.
# It goes once every queued level has landed and been counted (release()).
# Pat's console check 2026-10-14 (ai_evaluate_autonomous_construction) gave Jamaica's queued coffee site "Should
# construct: NO" with room for 4 more, where a fresh site and a vanilla ranch with a level queued said YES. The
# 1.14.5 code behind it (the "Should construct" test, 0x141514c50 and its inlined copies in the console commands)
# lets the AI add to a building that already exists only at PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD (0.8)
# employment or if it hired last week, and where the state lacks workforce only at full employment with spare
# infrastructure. A site with no jobs never passes, so stacking needs the crew below (RETOOL_CREW).
RETOOL_STACK = True
# Pat, 2026-10-13: private retool buildings get a crew so investors can expand them. 1.14.5's AI
# expands no building under PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD (0.8) employment unless it
# hired last week, and a building under MINIMUM_EMPLOYEES (10) employees always tries to hire, even
# one that earns nothing, as a retool building does. So the crew is fixed at 10, not per level
# ("unscaled"): it stays fully employed however many levels the building has.
# Pat, 2026-10-13 03:37Z: finished retool buildings cluttered the state's Buildings tab (four
# "Retooling: Iron Mines" at level 1 in Yorkshire) and investors did not stack levels on them. So
# RETOOL_CREW is 0: no crew, and a private retool building goes the moment its level is counted, as a
# government one does. Only construction sites still show while they build.
# Pat, 2026-10-14 01:34Z: give the site employment and income so the AI's expansion test passes. The 03:37Z crew
# earned nothing, so it could not pay to hire (1.14.5 logs "cant_afford_hires"). Now each level employs
# RETOOL_CREW and makes RETOOL_CREW_OUTPUT of RETOOL_CREW_GOOD at full staff, a little more than the crew's wages,
# so it hires, stays staffed and investors may add levels; it stays while staffed (RETOOL_CREW_GRACE_DAYS).
RETOOL_CREW = 10
RETOOL_CREW_GOOD = 'services'   # local, cost 30: 0.1 a week is about 3, against a few pounds a week for 10 laborers
RETOOL_CREW_OUTPUT = 0.1
RETOOL_CREW_POP = 'laborers'
# A private retool building with a finished level stays while its crew is hiring; one still short of
# RETOOL_CREW_STAFFED this many days after its last level landed goes, so the next level is a new
# construction again, as before the crew existed.
RETOOL_CREW_GRACE_DAYS = 90
RETOOL_CREW_STAFFED = 0.8
# Pat, 2026-10-13 (reversing 2026-10-12): companies list retooling again, so a company can own and
# expand it. Only the first private retool building of each type, which also takes the levels that
# can stack, so each company panel shows one Retooling icon per building type it lists.
COMPANY_RETOOL = True
COMPANY_RETOOL_SLOTS = 1
# Pat, 2026-10-13 20:00Z: companies also list ABROAD_SLOT, so a company owning levels abroad can own their
# retooling and its company weight counts there; the first slot opens only at home since 2d3f175. A company
# panel then shows a second Retooling icon per building type it lists.
COMPANY_RETOOL_ABROAD = bool(ABROAD_SLOT)
# Recipe bar colour per recipe tier (position in vanilla's group, oldest first), the same on every
# building. Pat, 2026-10-13: muted, in Victoria 3's own style, and no red or green, which read as bad
# and good. Drawn on vanilla's stacked bar chart texture, as the Owners bar is.
TIER_COLORS = [('Bronze', (0.60, 0.43, 0.27)), ('Ochre', (0.74, 0.60, 0.30)), ('Steel blue', (0.29, 0.43, 0.62)),
               ('Plum', (0.48, 0.34, 0.53)), ('Slate', (0.43, 0.48, 0.53))]
RECIPE_ICON_SHARE = 0.25   # a recipe's slice of the bar shows its icon above this share (Pat, 2026-10-13)
# Pat, 2026-10-13: every recipe from this tier up includes the building's automation, blended with it:
# from each automation group (vanilla names them pmg_automation_*, pmg_steam_automation_*,
# pmg_train_automation_*) the most advanced method that runs without electricity. Those groups leave
# the building, since the recipes now carry them. Buildings with fewer recipes keep their groups.
# Pat, later that day: automation that needs electricity (assembly lines, power looms) is not folded
# into those recipes. It becomes one more recipe on top of the newest, needing the newest recipe's and
# the automation's technologies and electricity in the state (ElectricRecipe).
AUTOMATION_FROM_TIER = 3
# Pat, 2026-10-18 18:36Z ("yeah i want to split it"): automation is no longer folded into the recipes. Every recipe
# with every automation option (one method of each automation group) is a retool target of its own (PairRecipe),
# so new levels and retooling follow the most profitable pair. The blend stays per axis: one share group per
# recipe and one per automation method (split_members), so a building carries as many share groups as before.
SPLIT_AUTOMATION = True
# Pat, 2026-10-19 01:07Z ("some buildings are missing their Automation PM's", "are there no railroads for these
# buildings?"): every labour saver is automation, whatever its group is called, and splits however few recipes the
# building has. Vanilla draws them all with the automation icon: the plantations' and vineyards' rail transport,
# glass bottle blowers, farm harvesting, logging equipment and transport, oil rig transport, ranch fencing and
# refrigeration, wharf and whaling refrigeration (AUTOMATION_GROUPS, read from the group files).
AUTOMATION_ICON = 'gfx/interface/icons/generic_icons/mixed_icon_automation.dds'
AUTOMATION_GROUPS = set()


def is_automation(g):
    """a labour-saver group; AUTO_BEST's (the trade centre's trade quantity) run the newest method instead"""
    return ('automation' in g or g in AUTOMATION_GROUPS) and not any(g in gs for gs in AUTO_BEST.values())


SPLIT_BARS = {}   # short name -> plain recipes of a split building: its bars read pmr_rs_<j> (recipe j's share), not pmr_sh_<i>
# Pat, 2026-10-18 14:48Z: every automation method pays for itself at 1836 wages with its goods at the +75%
# price cap (buff_automation). Vanilla's lose GBP 220 to 900 a level a week there: they save 1,000 to 3,000
# laborers, whose wage is about GBP 0.04 a week each. Each method now removes AUTOMATION_LABOUR_MULT times
# vanilla's workforce, and its goods (its inputs and the output it eats) are cut by one factor until the wage
# it saves covers them at AUTOMATION_PRICE_CAP x base price, where it runs with the fewest workers to save.
# The wage is Pat's Champagne food industry on 1836.1.1: GBP 1.41K a week for 6 levels of 36,000 wage units.
AUTOMATION_WAGE = 390          # weekly GBP per 10,000 wage units (REVIEW.md: GB 1838 median about 450)
AUTOMATION_PRICE_CAP = 1.75    # the game clamps prices to +75% (PRICE_LADDER)
AUTOMATION_LABOUR_MULT = 1.5   # workforce removed, x vanilla's, to the nearest AUTOMATION_JOBS_STEP
AUTOMATION_JOBS_STEP = 250
AUTOMATION_GOODS_STEP = 0.1    # goods rounded down to this, never below it, so a method keeps its demand
# The profit calculation (Pat, 2026-10-18 17:06Z, for Company Culture's best-methods window; SUMMARY.md §3 of
# /mnt/project-files/pmr/retool-profitability): each recipe's weekly profit per level at the state's prices,
# wages at pmr_wage (AUTOMATION_WAGE until a measured local wage replaces it), the best one in pmr_pbest_<b>.
# A recipe other than the current pick must beat it by PROFIT_STICK_UP of its margin when newer and
# PROFIT_STICK_DOWN when older (vanilla's x0.95 and x0.75 stickiness, ai:1010-1011), and a recipe needing more
# of an input whose price is at the +75% cap is vetoed (vanilla's x0.01 for shortages, ai:1001). Pat,
# 2026-10-19 01:07Z ("diesel pumps when we have little to no oil"): the pick itself is vetoed too when it needs
# more of a capped input than an older recipe, so a shortage moves the pick down.
# Pat, 17:14Z: the pick decides how new builds and retooling go (PROFIT_TARGET; False puts back the newest
# runnable recipe), computed only when something changed or on a re-check every six months (profit_effect).
# Pat, 2026-10-19 01:07Z: a new pick becomes that default (pmr_best_now_<b>) only once a bar has filled for
# SWITCH_MONTHS monthly pulses, green up to a newer recipe, red down to an older one (pmr_switch_<b>).
PROFIT_TARGET = True
PROFIT_RECHECK_DAYS = 182
PROFIT_RECHECK_SPREAD = 60     # re-checks fall 30 days either side, in 7 steps
SWITCH_MONTHS = 6
PROFIT_STICK_UP = 0.05
PROFIT_STICK_DOWN = 0.25
# Pat, 2026-10-18 21:32Z: "Whatever the true basis for ai scoring is should be reflected." What vanilla's investment
# pool adds to a building's ai_value for a new level (00_ai.txt): its predicted weekly profit divided by the employees
# a level has, x PRODUCTION_BUILDING_GOODS_PROFIT_FACTOR 5000 x the pool's PROFIT_FACTOR_MULT 1.5 (a deficit x
# GOODS_DEFICIT_FACTOR 10000), plus the goods it makes at base value x PRODUCED_VALUE_FACTOR 0.25 x the pool's 1.25.
# pmr_profit_<b> scores its pick so (pmr_pvs_<b>); private_investment.pf_effects averages it per country into the
# type's ai_value. The market terms (price bands, wanted goods, shortages) stay the game's own, per state.
VANILLA_PROFIT_W, VANILLA_DEFICIT_W, VANILLA_OUTPUT_W = 5000 * 1.5, 10000, 0.25 * 1.25
TARGET_EMPLOYEES = {}   # building type -> employees per level of each retool target (the order of econ)
# Pat, 2026-10-13: a recipe that needs electricity (its own goods, its folded automation, or vanilla's
# required_input_goods) can't become a building's target unless its state produces electricity, and
# retooling towards it pauses while the state has none. One rule for government and private retooling.
ELECTRICITY = 'electricity'
# Loop breaker (2026-10-13: Pat's game froze during the daily update of 16 June 1836, and debug.log
# held nothing after 11 June). A building type's tick that runs more than TICK_TRIP times in one
# state in one day stops there for the rest of the day and writes a TRIP line. TRIP and RELEASE (a
# private retool building with a crew removed) lines go through flush_log: debug.log reaches disk in
# 4 KB blocks, so the last lines before a hang are lost unless one line fills a block by itself.
TICK_TRIP = 25
FLUSH_PAD = 4500
# Second groups (Pat approved both 2026-10-13; built from 03:21Z). A group after the recipe group is
# either a trade-off, blended by local prices, or a plantation's working conditions, blended by the
# workforce's acceptance. Each of its options (every method but the one that does nothing) gets a share
# of the building, in 1% steps, through share methods built like the recipe ones; the do-nothing method
# is the remainder. The vanilla group stays on the building as a marker that carries nothing: it keeps
# the game's history setup readable at game start and lets can_activate_production_method gate each
# option by technology, law and recipe as vanilla would.
# Trade-offs (pmr/second-groups.md): once a month each option is valued at local prices (outputs minus
# inputs per level, goods only), and points move from the worst-paying option with a share to the
# best-paying one, when the gap beats TRADE_DEAD_BAND of the building's output value per level. Pat,
# 2026-10-13 (2 points a month took Yorkshire's rye farms 33 months to reach 66% Apple Orchards): the
# move is the gap in % of that output value times TRADE_GAIN, within TRADE_STEP_MIN..TRADE_STEP_MAX
# points, so an option paying 10% more moves 10 points a month, and the move slows as prices answer.
# "None" is worth 0. A building built during the game starts on the best-paying option.
TRADE_GROUPS = ('pmg_hardwood', 'pmg_canning', 'pmg_distillery', 'pmg_luxury_building_textile_mill',
                'pmg_luxury_building_furniture_manufactory', 'pmg_luxury_building_glassworks',
                'pmg_aeroplanes', 'pmg_tanks', 'pmg_synthetic_silk', 'pmg_radios_category',
                'pmg_secondary_building_rye_farm', 'pmg_secondary_building_wheat_farm',
                'pmg_secondary_building_rice_farm', 'pmg_secondary_building_maize_farm',
                'pmg_secondary_building_millet_farm',
                # the mines' explosives (none, nitroglycerin, dynamite) trade explosives for ore. Left vanilla,
                # they lost their selector with the rest of the hidden method grid, so the player's mines never
                # used them (#2). Pat, 2026-10-19 01:18Z: blended by price like the other trade-offs.
                'pmg_explosives_building_coal_mine', 'pmg_explosives_building_iron_mine',
                'pmg_explosives_building_lead_mine', 'pmg_explosives_building_sulfur_mine',
                'pmg_explosives_building_gold_mine')
TRADE_GAIN = 1.0
# Pat, 2026-10-13: new games start each trade-off near where games take it, not on vanilla's history
# choice. Read from his Great Britain save of 28 October 1838 by tools/pmr/save_blends.py: for each
# building type, the share of the world's levels whose best-paying option at their state's prices
# is each option (none below the dead band). At game start a building takes these shares; an option
# its state can't run yet passes its share to the option before it in vanilla's order, then to none.
# Buildings built later still start on their own best-paying option. A type left out keeps vanilla's
# start (automotive: none built by 1838).
TRADE_PRELOAD = {
    'building_rye_farm': {'pm_potatoes': 32, 'pm_apple_orchards': 68},
    'building_wheat_farm': {'pm_citrus_orchards': 100},
    'building_maize_farm': {'pm_citrus_orchards': 100},
    'building_millet_farm': {'pm_fig_orchards': 100},
    'building_rice_farm': {'pm_fig_orchards_building_rice_farm': 100},
    'building_logging_camp': {'pm_hardwood': 5, 'pm_increased_hardwood': 27},
    'building_textile_mill': {'pm_craftsman_sewing': 21},
    'building_furniture_manufactory': {'pm_luxury_furniture': 70, 'pm_precision_tools': 2},
    'building_glassworks': {'pm_ceramics': 99},
    'building_food_industry': {'pm_pot_stills': 3, 'pm_patent_stills': 10},   # canning stays none
}
TRADE_STEP_MIN, TRADE_STEP_MAX = 2, 20
TRADE_DEAD_BAND = 0.05
# Treatment (pmr/treatment-by-acceptance.md): Violent Treatment's share is the building's workforce
# with acceptance under TREAT_BANDS[0], Exploitative Practices' (Pat's "harsh") the workforce from
# there to under TREAT_BANDS[1], recounted monthly. Every effect of each method, output, penalties and
# slave imports alike, scales by its share (Pat, 02:26Z). The law wins: a share the owner's laws bar
# goes to the nearest treatment they allow (violent to harsh to standard; standard, barred under the
# slave trade, to harsh, then violent).
# Trade-off bar colours, muted and never red or green, apart from the recipe tiers; "none" is grey.
OPTION_COLORS = [('Sand', (0.74, 0.66, 0.48)), ('Dusk blue', (0.42, 0.52, 0.66)),
                 ('Mauve', (0.60, 0.46, 0.56)), ('Umber', (0.52, 0.41, 0.31))]
OPTION_NONE_COLOR = (0.36, 0.36, 0.36)
# Pat, 2026-10-18 17:15Z: an automation bar under the recipe bar, the levels by how automated their recipe is,
# in shades of green, the darkest the most automated: none (recipes below AUTOMATION_FROM_TIER), the folded
# automation, electric automation (ElectricRecipe). Only on buildings that fold automation.
AUTO_COLORS = [('Pale green', (0.66, 0.76, 0.58)), ('Green', (0.38, 0.58, 0.36)), ('Dark green', (0.17, 0.37, 0.21))]
# Log-only probes (Pat approved both 2026-10-13), both answered by 2026-10-13 (TREAT w = wv+wh+ws; PRICE
# reads fractions), so off since the performance review. They change nothing in game; each
# writes one line a month per player-owned state where it applies.
# TREAT: each plantation's workforce by acceptance band, for plantation treatment by acceptance
# (pmr/treatment-by-acceptance.md). Acceptance below TREAT_BANDS[0] (levels 1-2) is the violent band,
# below TREAT_BANDS[1] (level 3) the harsh band, the rest standard (Pat's levels).
PROBE_TREAT = False
TREAT_BANDS = (40, 60)
# PRICE: the local price of PRICE_PROBE_GOODS, read through the state_goods_pricier/cheaper ladder the
# market blend of the trade-off groups will use (pmr/second-groups.md), where PRICE_PROBE_BUILDING stands.
PROBE_PRICE = False
PRICE_PROBE_BUILDING = 'building_logging_camp'
PRICE_PROBE_GOODS = ('hardwood', 'wood')
PRICE_STEP = 5             # ladder resolution, % of base price; the game clamps prices to +-75%
# Pat, 2026-10-13: the investment pool's building-type roll multiplies each candidate's score by
# (1 + F*u1) / (1 + F*u2), F = PRODUCTION_BUILDING_RANDOM_FACTOR (10) x this (vanilla 2), so 1/21 to 21.
# At 1 it is 1/11 to 11. A defines override, so it applies to every building, not only PMR's (Pat
# accepted that). The 80% employment gate (PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD) stays vanilla.
# See /mnt/project-files/pmr/investment-ai.md.
INVESTMENT_RANDOM_FACTOR_MULT = 1.0
GOV_RETOOL_ICON = 'gfx/interface/icons/formation_order_icons/upgrade.dds'
RETOOL_CREW_ICON = 'gfx/interface/icons/production_method_icons/wooden_buildings.dds'

MOD_NAME = 'ProductionMethodRework'
MOD_VERSION = '0.2.0'
SUPPORTED_VERSION = '1.14.*'

# Building files whose buildings make goods from goods. Government, military, monuments, canals,
# subsistence, companies and the construction sector are out of scope: their first group is not a goods
# recipe, or retooling them through construction is circular. Urban Centers run their best (AUTO_BEST).
BUILDING_FILES = ['01_industry.txt', '02_agro.txt', '03_mines.txt', '04_plantations.txt', '06_urban_center.txt',
                  '09_misc_resource.txt', '11_private_infrastructure.txt']
# Pat, 2026-10-13 17:00Z: ports and railways retool like the rest. Only these buildings of a file listed
# here are candidates; the file's others (trade centres, Financial Districts, Manor Houses) stay vanilla.
# Pat, 21:39Z and 22:01Z: Arts Academies and power plants retool too (the Urban Center runs its best methods
# instead, AUTO_BEST).
BUILDING_ONLY = {'11_private_infrastructure.txt': ('building_port', 'building_railway'),
                 '06_urban_center.txt': ('building_art_academy', 'building_power_plant')}
# Buildings whose recipes carry no workforce because vanilla puts it in another group, which stays on the
# building (kept on its best method by AUTO_BEST). The share methods then blend only the recipes' goods.
WORKFORCE_ELSEWHERE = {'building_art_academy': 'pmg_ownership_building_art_academy'}
# Power bloc principle variants of a recipe, which vanilla swaps in with replacement_if_valid, leave the
# recipe group (and the replacement lines go): a building would otherwise have to retool backwards the
# day its bloc dropped the principle.
DROP_RECIPES = ('pm_steam_trains_principle_transport_3', 'pm_electric_trains_principle_transport_3',
                'pm_diesel_trains_principle_transport_3')
# Pat, 2026-10-13 20:56Z ("Restore it"): a power bloc principle that unlocked the dropped variants gives their
# bonus on top of the recipe instead, so nothing retools when the bloc gains or loses it. Each month, in each
# state of a member country, the levels on a recipe that had a variant get PRINCIPLE_THROUGHPUT more throughput
# (vanilla's variants: 20 to 29% more transport for 20 to 33% more engines and fuel) and the variant's extra
# infrastructure per level, scaled by the building's employment as the recipe's own infrastructure is.
PRINCIPLE_THROUGHPUT = 0.25
# Pat, 2026-10-13 17:00Z: these groups always run their best method, with no retooling and no selectors.
# Best is the newest method the state can activate (vanilla lists them oldest first), a principle variant
# before the method it replaces; PMR switches to it monthly, on research, when the building is built
# and whenever a method changes. Where laws allow only one (bureaucrat professionalism, and religious
# or secular staff once AUTO_SECULAR applies), that one. A method that uses electricity (Arcades, Electric
# Streetlights) counts only while the state produces it, as for retooling; without it the next one runs.
AUTO_BEST = {
    'building_government_administration': ('pmg_base_building_government_administration',
                                           'pmg_government_administration_bureaucrat_professionalism',
                                           'pmg_government_administration_religious_administration'),
    'building_university': ('pmg_base_building_university', 'pmg_university_academia'),
    'building_trade_center': ('pmg_base_building_trade_center', 'pmg_trade_quantity_trade_center'),
    'building_railway': ('pmg_passenger_trains',),   # "always produce transport": carriages always on
    # Pat, 2026-10-13 21:51Z: Urban Centers "automatically retool to max level". The game grows them with
    # urbanisation and they own themselves, so nobody would fund a retool site; clergy goes by law as vanilla's.
    'building_urban_center': ('pmg_amenities', 'pmg_street_lighting', 'pmg_public_transport', 'pmg_urban_clergy'),
    # Pat 21:39Z: Arts Academies retool their art (a PMR building); patronage, which carries their workforce
    # (WORKFORCE_ELSEWHERE), and the Freedom of Movement principle variant run their best.
    'building_art_academy': ('pmg_ownership_building_art_academy', 'pmg_principle_freedom_of_movement_3'),
}
# Clergy or bureaucrats by law (Pat 17:00Z). Vanilla bars the religious method under the laws its
# disallowing_laws list (Total Separation, State Atheism) and the secular one only under State Religion,
# so both run under the laws between. PMR lets the secular method run only under the laws that bar the
# religious one: State Religion, Millet System, People of the Book and Freedom of Conscience staff clergy.
AUTO_SECULAR = {'pm_secular_bureaucrats': 'pm_religious_bureaucrats', 'pm_secular_academia': 'pm_religious_academia'}

GENERIC_ICON = 'gfx/interface/icons/generic_icons/mixed_icon_base.dds'
RETOOL_BACKGROUND = 'gfx/interface/icons/building_icons/backgrounds/building_panel_bg_monuments.dds'

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_OUT = os.path.join(ROOT, 'pmr', MOD_NAME)
RELEASE_OUT = os.path.join(ROOT, 'pmr', 'release', MOD_NAME)
THUMBNAIL = os.path.join(ROOT, 'pmr', 'thumbnail.png')   # the preview, 1024 x 1024: the launcher reads .metadata/,
# the Workshop upload the mod's root folder (Steam showed a blank preview without the root copy, fixed 2026-10-14)
# Dev-only probes, each laid out like a mod (pmr/test_probes/<probe>/common/...), copied as they are into test
# builds only. Pat 2026-10-14 03:42Z: one live and one test mod, so probes ride in the test build rather than in
# add-on mods. works_probe (the Hudson's Bay executive trait) passed 03:51Z and was retired when Company Culture
# (company_culture.py) took over building_employment_laborers_mult. buyin_probe (Pat 13:54Z) ran at 14:22Z and was
# retired when Pat dropped foreign buy-in at 14:29Z (results: /mnt/project-files/pmr/foreign-buyin/probe-results.md).
# works_share_probe (Company Culture thread, Pat 2026-10-18 15:35Z) asks whether a building reads its company owners'
# share through an executive trait (run sheet: /mnt/project-files/pmr/mio/works-share-probe/RUN.md). A probe's
# English localisation is copied to every other language.
TEST_PROBES = os.path.join(ROOT, 'pmr', 'test_probes')
SHORT_DESCRIPTION = ('Research no longer upgrades a factory overnight: buildings retool level by level through '
                     'construction, and their output blends the recipes their levels run.')
# The game's other languages (1.14.5 game/localization), translated by localise.py, English where a line has no
# translation yet.
OTHER_LANGUAGES = ('braz_por', 'french', 'german', 'japanese', 'korean', 'polish', 'russian', 'simp_chinese',
                   'spanish', 'turkish')
# The release build keeps only these log lines: the loop breaker's, and the one saying the mod loaded.
RELEASE_LOGS = ('TRIP', 'AUTO_TRIP', 'LOADED')
RELEASE = False   # set by main(): --release, so code that only feeds the log is left out


# ---------------------------------------------------------------------------------------------
# Reading vanilla

class Source:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        with open(path, encoding='utf-8-sig') as f:
            self.text = pdx.strip_bom(f.read())
        self.nodes = pdx.parse(self.text)
        self.cuts = []      # (start, end) spans to delete
        self.inserts = []   # (offset, text)

    def objects(self):
        return {n.key: n for n in self.nodes if n.key and n.is_block}

    def render(self):
        edits = [(s, e, '') for s, e in self.cuts] + [(o, o, t) for o, t in self.inserts]
        out, pos = [], 0
        for s, e, t in sorted(edits, key=lambda x: (x[0], x[1])):
            if s < pos:
                raise ValueError(f'{self.name}: overlapping edits at {s}')
            out.append(self.text[pos:s])
            out.append(t)
            pos = e
        out.append(self.text[pos:])
        return '\ufeff' + ''.join(out)


def load_dir(game, sub, only=None):
    srcs = []
    for path in sorted(glob.glob(os.path.join(game, 'common', sub, '*.txt'))):
        if only and os.path.basename(path) not in only:
            continue
        srcs.append(Source(path))
    return srcs


def num(v, where):
    try:
        return float(v)
    except (TypeError, ValueError):
        raise SystemExit(f'non-numeric value {v!r} in {where}; extend the generator before shipping')


def line_span(text, node):
    """Extend a node's span to its whole line (leading indent and trailing newline)."""
    s = text.rfind('\n', 0, node.start) + 1
    e = text.find('\n', node.end)
    e = len(text) if e < 0 else e + 1
    if text[s:node.start].strip() or text[node.end:e].strip() and not text[node.end:e].strip().startswith('#'):
        return node.start, node.end   # shares its line with something else: cut the node only
    return s, e


BLEND_SECTIONS = ('building_modifiers', 'state_modifiers', 'country_modifiers')


class Recipe:
    def __init__(self, key, node, src):
        self.key, self.node, self.src = key, node, src
        self.inputs, self.outputs, self.employment = {}, {}, {}
        self.texture = (pdx.get(node.value, 'texture').value if pdx.get(node.value, 'texture') else GENERIC_ICON)
        # Goods vanilla requires before the method may run (only ever electricity in 1.14.5).
        self.required = [n.value for n in node.value if n.key == 'required_input_goods']
        # Everything the recipe scales by workforce (goods, pollution, ...), by section. PMR moves it
        # into the share methods, scaled by the recipe's share of the levels.
        self.blend = {}
        for sec in BLEND_SECTIONS:
            sn = pdx.get(node.value, sec)
            for block in (pdx.get_all(sn.value, 'workforce_scaled') if sn else []):
                for n in block.value:
                    if n.key:
                        d = self.blend.setdefault(sec, {})
                        d[n.key] = d.get(n.key, 0) + num(n.value, f'{key}.{sec}.{n.key}')
        bm = pdx.get(node.value, 'building_modifiers')
        if bm:
            for block in pdx.get_all(bm.value, 'workforce_scaled'):
                for n in block.value:
                    if not n.key:
                        continue
                    if n.key.startswith('goods_input_') and n.key.endswith('_add'):
                        g = n.key[len('goods_input_'):-len('_add')]
                        self.inputs[g] = self.inputs.get(g, 0) + num(n.value, f'{key}.{n.key}')
                    elif n.key.startswith('goods_output_') and n.key.endswith('_add'):
                        g = n.key[len('goods_output_'):-len('_add')]
                        self.outputs[g] = self.outputs.get(g, 0) + num(n.value, f'{key}.{n.key}')
            for block in pdx.get_all(bm.value, 'level_scaled'):
                for n in block.value:
                    if n.key and n.key.startswith('building_employment_'):
                        self.employment[n.key] = self.employment.get(n.key, 0) + num(n.value, f'{key}.{n.key}')
        # Abroad (pmr_best_<b>): the technologies the recipe needs, and whether anything else gates it
        # (laws, principles), in which case only the host's can_activate_production_method decides.
        ut = pdx.get(node.value, 'unlocking_technologies')
        self.unlock_techs = pdx.items(ut) if ut else []
        self.gated_otherwise = any(n.key and n.key != 'unlocking_technologies'
                                   and (n.key.startswith('unlocking_') or n.key.startswith('disallowing_'))
                                   for n in node.value)

    def strip_blend(self):
        """Cut the workforce-scaled blocks; the share methods carry them instead."""
        for sec in BLEND_SECTIONS:
            sn = pdx.get(self.node.value, sec)
            for block in (pdx.get_all(sn.value, 'workforce_scaled') if sn else []):
                self.src.cuts.append(line_span(self.src.text, block))

    def strip_required(self):
        """Cut required_input_goods: a recipe method carries no goods, and with the requirement the
        game would switch a building off its recipe the day the good ran out, which PMR would read
        as a switch and retool backwards. PMR enforces the electricity rule itself (pmr_best_<b>)."""
        for n in self.node.value:
            if n.key == 'required_input_goods':
                self.src.cuts.append(line_span(self.src.text, n))

    def needs(self, good):
        return good in self.inputs or good in self.required

    def strip_employment(self):
        bm = pdx.get(self.node.value, 'building_modifiers')
        for block in pdx.get_all(bm.value, 'level_scaled'):
            kids = [n for n in block.value if n.key]
            emp = [n for n in kids if n.key.startswith('building_employment_')]
            if not emp:
                continue
            if len(emp) == len(kids):
                self.src.cuts.append(line_span(self.src.text, block))
            else:
                for n in emp:
                    self.src.cuts.append(line_span(self.src.text, n))


ELECTRIC_DOC = """# Electric recipes (Pat, 2026-10-13): a building whose automation needs electricity (assembly lines,
# power looms) gets one more recipe on top of its newest, pm_pmr_elec_<b>: the newest recipe with that
# automation. Like every recipe it carries nothing itself and marks the retool target; its share methods
# carry the goods and workforce. The tick makes it the target only when the owner has researched every
# technology below and the state produces electricity (pmr_best_<b>). unlocking_technologies lists them all
# as well, in case the game reads the list as all-of.

"""


class PairRecipe:
    """Pat, 2026-10-18 18:36Z: a recipe with an automation option (SPLIT_AUTOMATION), as a retool target of its own.
    Its marker, pm_pmr_pair_<b>_<r>_<a>, carries nothing and needs the recipe's and the automation's technologies;
    the tick also asks the recipe's own marker (its other gates) and electricity where the automation needs it."""
    def __init__(self, bk, base, r, a, opt, pms):
        self.key = f'pm_pmr_pair_{short(bk)}_{r}_{a}'
        self.base, self.opt, self.r, self.a = base, opt, r, a
        self.autos = [m for m in opt if m.blend or m.employment]
        self.texture = base.texture
        self.unlock_techs = []
        for m in [base] + list(opt):
            ut = pdx.get(pms[m.key][0].value, 'unlocking_technologies')
            for t in (pdx.items(ut) if ut else []):
                if t not in self.unlock_techs:
                    self.unlock_techs.append(t)
        self.techs = list(self.unlock_techs)
        # The other gates: the recipe's own (coffee's growing regions) as vanilla writes them, and every
        # disallowing_* of the automation (law_industry_banned), so the marker runs only where both may.
        self.gates, barred = [], {}
        for m in [base] + list(opt):
            for n in m.node.value:
                if not n.key or n.key == 'unlocking_technologies':
                    continue
                if n.key.startswith('disallowing_'):
                    for x in pdx.items(n):
                        if x not in barred.setdefault(n.key, []):
                            barred[n.key].append(x)
                elif n.key.startswith('unlocking_'):
                    if m is not base:
                        raise SystemExit(f'{m.key}: {n.key} on an automation method; extend PairRecipe before shipping')
                    self.gates.append(m.src.text[n.start:n.end])
        self.gates += [f'{k} = {{ ' + ' '.join(xs) + ' }' for k, xs in barred.items()]
        self.gated_otherwise = base.gated_otherwise or bool(barred)

    def needs(self, good):
        return self.base.needs(good) or any(m.needs(good) for m in self.opt)

    def method(self):
        return (f'{self.key} = {{\n\ttexture = "{self.texture}"\n'
                + (f'\tunlocking_technologies = {{\n' + ''.join(f'\t\t{t}\n' for t in self.techs) + '\t}\n'
                   if self.techs else '')
                + ''.join(f'\t{g}\n' for g in self.gates)
                + '}\n')


def automation_options(auto_groups, groups, pms):
    """Every automation option of a building: one method of each automation group, vanilla's order (a = 1 none)."""
    options = [[]]
    for g in auto_groups:
        options = [o + [Recipe(p, *pms[p])] for o in options for p in groups[g]]
    return options


class ElectricRecipe:
    """The newest recipe with electric automation, as a recipe of its own on top of it."""
    def __init__(self, bk, base, autos, pms):
        self.key = f'pm_pmr_elec_{short(bk)}'
        self.base, self.autos = base, autos
        elec = [a for a in autos if a.needs(ELECTRICITY)]
        self.texture = elec[0].texture
        self.techs = []
        for m in [base] + elec:
            ut = pdx.get(pms[m.key][0].value, 'unlocking_technologies')
            for t in (pdx.items(ut) if ut else []):
                if t not in self.techs:
                    self.techs.append(t)

    def method(self):
        return (f'{self.key} = {{\n\ttexture = "{self.texture}"\n'
                + (f'\tunlocking_technologies = {{\n' + ''.join(f'\t\t{t}\n' for t in self.techs) + '\t}\n'
                   if self.techs else '')
                + '}\n')


def effective(r, autos):
    """What recipe r's share methods carry: its workforce-scaled modifiers (blend) and its workforce
    (level-scaled employment), plus those of the folded automation methods autos; and whether it needs
    electricity. Employment per profession is kept at zero or more (automation only removes jobs)."""
    blend = {sec: dict(mods) for sec, mods in r.blend.items()}
    emp = dict(r.employment)
    elec = r.needs(ELECTRICITY)
    for a in autos:
        for sec, mods in a.blend.items():
            d = blend.setdefault(sec, {})
            for k, v in mods.items():
                d[k] = d.get(k, 0) + v
        for k, v in a.employment.items():
            emp[k] = emp.get(k, 0) + v
        elec = elec or a.needs(ELECTRICITY)
    clamped = {k: v for k, v in emp.items() if v < 0}
    emp = {k: v for k, v in emp.items() if v > 0}
    blend = {sec: {k: v for k, v in mods.items() if v} for sec, mods in blend.items()}
    return {sec: mods for sec, mods in blend.items() if mods}, emp, elec, clamped


def wage_weights(game):
    weight = {}
    for s in load_dir(game, 'pop_types'):
        for k, n in s.objects().items():
            w = pdx.get(n.value, 'wage_weight')
            weight[k] = num(w.value, f'{k} wage_weight') if w else 1.0
    return weight


def recipe_econ(blend, emp, weight):
    """goods per level ({good: amount}, outputs positive, inputs negative) and wage units per level of
    an effective() blend, at full staffing and throughput 1."""
    goods = {}
    for mk, mv in blend.get('building_modifiers', {}).items():
        for pre, sign in (('goods_output_', 1), ('goods_input_', -1)):
            if mk.startswith(pre) and mk.endswith('_add'):
                g = mk[len(pre):-len('_add')]
                goods[g] = goods.get(g, 0) + sign * mv
    wu = sum(v * weight.get(k[len('building_employment_'):-len('_add')], 1.0) for k, v in emp.items())
    return {g: q for g, q in goods.items() if q}, wu


def pairs(recipes, auto_groups, groups, pms, weight):
    """Pat, 2026-10-18 18:17Z: the Methods view scores every recipe with every automation (PM1 + PM3). The plain
    recipes (not the electric one, which is the newest recipe with the top automation already) are i = 1.. as PMR
    numbers them; an automation option a = 1.. is one method of each automation group (their product, vanilla's
    order, so a = 1 is none). Each pair's goods and wage units are effective(recipe, option), so employment that
    automation would push below zero stops at zero as it does in the game. Automation methods don't depend on the
    recipe (PM rework, 14:06Z), so these are the figures a split of the fold would retool by."""
    plain = [(i, r) for i, r in enumerate(recipes, 1) if not isinstance(r, ElectricRecipe)]
    options = [[]]
    for g in auto_groups:
        options = [o + [Recipe(p, *pms[p])] for o in options for p in groups[g]]
    econ, elec = {}, {}
    for i, r in plain:
        for a, opt in enumerate(options, 1):
            blend, emp, needs, _ = effective(r, opt)
            econ[(i, a)] = recipe_econ(blend, emp, weight)
            elec[(i, a)] = needs
    return {'recipes': [i for i, _ in plain], 'options': options, 'econ': econ, 'elec': elec,
            'techs': [list(dict.fromkeys(t for m in opt for t in m.unlock_techs)) for opt in options]}


def buff_automation(game, p_srcs, groups, b_srcs):
    """Pat, 2026-10-18 14:48Z (AUTOMATION_WAGE): rewrite every automation method in its vanilla file, before
    anything reads it, so the folded, electric and kept automation all carry the buff. Each method's
    workforce change is x AUTOMATION_LABOUR_MULT; its goods are x k, the smallest factor over every place it
    runs (a recipe it folds into, the electric recipe, or each recipe beside a kept group) that lets the wage
    it really saves there (employment stops at zero, shared between the methods running together) pay for
    them at AUTOMATION_PRICE_CAP. Returns the report rows; the caller rebuilds pms from p_srcs."""
    pms = {k: (n, s) for s in p_srcs for k, n in s.objects().items()}
    cost = {k: num(pdx.get(n.value, 'cost').value, f'{k} cost')
            for s in load_dir(game, 'goods') for k, n in s.objects().items() if pdx.get(n.value, 'cost')}
    weight = wage_weights(game)

    def rec(p):
        return Recipe(p, *pms[p])

    # Where each method runs, as generate's own folding rules put it: (building, where, base employment, methods).
    places = []
    for s in b_srcs:
        for bk, bn in s.objects().items():
            pg = pdx.get(bn.value, 'production_method_groups')
            gl = pdx.items(pg) if pg else []
            if not gl:
                continue
            g0 = gl[0]
            ag = [g for g in gl if g != g0 and is_automation(g)]
            recipes = [rec(p) for p in groups.get(g0, []) if p not in DROP_RECIPES and p in pms]
            if not ag or not recipes:
                continue
            if SPLIT_AUTOMATION:
                # every recipe with every automation option, the option's methods running together
                for opt in automation_options(ag, groups, pms)[1:]:
                    autos = [a for a in opt if a.employment]
                    if autos:
                        places += [(bk, f'{r.key} + ' + ' + '.join(a.key for a in opt), r.employment, autos)
                                   for r in recipes]
            elif len(recipes) >= AUTOMATION_FROM_TIER:
                folded = []
                for g in ag:
                    plain = [p for p in groups[g] if not rec(p).needs(ELECTRICITY)]
                    if plain:
                        folded.append(rec(plain[-1]))
                for r in recipes[AUTOMATION_FROM_TIER - 1:]:
                    places.append((bk, r.key, r.employment, folded))
                tops = [rec(groups[g][-1]) for g in ag]
                if any(a.needs(ELECTRICITY) for a in tops):
                    places.append((bk, f'{recipes[-1].key} + electric automation', recipes[-1].employment, tops))
            else:
                for g in ag:
                    for p in groups[g]:
                        if rec(p).employment:
                            places += [(bk, f'{r.key} + {p}', r.employment, [rec(p)]) for r in recipes]

    def jobs(v):
        return round(v * AUTOMATION_LABOUR_MULT / AUTOMATION_JOBS_STEP) * AUTOMATION_JOBS_STEP

    def saved(base, autos):
        """wage units each method really removes from base, the methods' new workforce together."""
        tot = {}
        for a in autos:
            for k, v in a.employment.items():
                tot[k] = tot.get(k, 0) + jobs(v)
        out = {}
        for a in autos:
            out[a.key] = sum(jobs(v) / tot[k] * min(-tot[k], base.get(k, 0)) * weight[k[len('building_employment_'):-len('_add')]]
                             for k, v in a.employment.items() if tot[k] < 0)
        return out

    def goods_bill(a, k=1.0):
        """weekly GBP of a method's goods at the price cap: its inputs, and the output it eats."""
        return AUTOMATION_PRICE_CAP * k * (sum(q * cost[g] for g, q in a.inputs.items())
                                           - sum(q * cost[g] for g, q in a.outputs.items() if q < 0))

    worst = {}   # method -> (wage units it saves where it saves least, where)
    for bk, where, base, autos in places:
        for key, wu in saved(base, autos).items():
            if key not in worst or wu < worst[key][0]:
                worst[key] = (wu, f'{bk}: {where}')
    rows, edits = [], {}
    for key, (wu, where) in sorted(worst.items()):
        a = rec(key)
        bill = goods_bill(a)
        pay = wu * AUTOMATION_WAGE / 10000
        k = min(1.0, pay / bill) if bill else 1.0
        new_goods = {}
        for g, q in list(a.inputs.items()) + [(g, -q) for g, q in a.outputs.items() if q < 0]:
            new_goods[g] = max(AUTOMATION_GOODS_STEP, math.floor(q * k / AUTOMATION_GOODS_STEP) * AUTOMATION_GOODS_STEP)
        bill_new = AUTOMATION_PRICE_CAP * sum(q * cost[g] for g, q in new_goods.items())
        if bill_new > pay:
            raise SystemExit(f'buff_automation: {key} still loses GBP {bill_new - pay:.1f} a week at the cap ({where}); '
                             'lower AUTOMATION_GOODS_STEP')
        rows.append({'method': key, 'least_saved_at': where, 'wage_units_saved': wu, 'wage_saved': round(pay, 1),
                     'goods_before': {**a.inputs, **{g: -q for g, q in a.outputs.items() if q < 0}},
                     'goods_after': {g: round(q, 4) for g, q in new_goods.items()},
                     'goods_bill_at_cap_before': round(bill, 1), 'goods_bill_at_cap_after': round(bill_new, 1),
                     'employment_before': dict(a.employment),
                     'employment_after': {k2: jobs(v) for k2, v in a.employment.items()}})
        edits[key] = new_goods
    # Rewrite the values in place: every other byte of the file stays vanilla's.
    for s in p_srcs:
        spans = []
        for key, n in s.objects().items():
            if key not in edits:
                continue
            new_goods = edits[key]
            bm = pdx.get(n.value, 'building_modifiers')
            for block in pdx.get_all(bm.value, 'workforce_scaled'):
                for m in block.value:
                    for pre, sign in (('goods_input_', 1), ('goods_output_', -1)):
                        if m.key and m.key.startswith(pre) and m.key.endswith('_add'):
                            g = m.key[len(pre):-len('_add')]
                            if sign * num(m.value, m.key) > 0 and g in new_goods:
                                spans.append((m, fmt(sign * new_goods[g])))
            for block in pdx.get_all(bm.value, 'level_scaled'):
                for m in block.value:
                    if m.key and m.key.startswith('building_employment_'):
                        spans.append((m, fmt(jobs(num(m.value, m.key)))))
        if not spans:
            continue
        text, pos, out = s.text, 0, []
        for m, val in sorted(spans, key=lambda x: x[0].start):
            e = text.find('\n', m.end)
            e = len(text) if e < 0 else e
            tail = text[m.end:e]
            end = e if tail.strip().startswith('#') or not tail.strip() else m.end
            out += [text[pos:m.start], f'{m.key} = {val}\t# PMR: vanilla {m.value} (automation buff)']
            pos = end
        out.append(text[pos:])
        s.text = ''.join(out)
        s.nodes = pdx.parse(s.text)
    return rows


class Option:
    """One option of a second group on one building: a vanilla method whose effects PMR moves into
    share methods pm_pmr_x_<b>_<j>_<n>, scaled by n / SHARE_STEPS. The vanilla method stays in its
    group as a marker that carries nothing."""
    def __init__(self, bk, j, group, gi, mode, role, key, pms):
        self.bk, self.b, self.j, self.group, self.gi = bk, short(bk), j, group, gi
        self.mode, self.role, self.key = mode, role, key
        self.node, self.src = pms[key]
        t = pdx.get(self.node.value, 'texture')
        self.texture = t.value if t else GENERIC_ICON
        self.mods = {}   # (section, sub-block) -> {modifier: value}, in vanilla's order
        for sec in BLEND_SECTIONS:
            sn = pdx.get(self.node.value, sec)
            for sub in (sn.value if sn else []):
                if not sub.key:
                    continue
                if not sub.is_block:
                    raise SystemExit(f'{key}.{sec}.{sub.key} is not a block; extend Option before shipping')
                d = self.mods.setdefault((sec, sub.key), {})
                for n in sub.value:
                    if n.key:
                        d[n.key] = d.get(n.key, 0) + num(n.value, f'{key}.{sec}.{sub.key}.{n.key}')
        # goods per level at full employment: outputs positive, inputs negative
        self.goods = {}
        for mk, mv in self.mods.get(('building_modifiers', 'workforce_scaled'), {}).items():
            for pre, sign in (('goods_output_', 1), ('goods_input_', -1)):
                if mk.startswith(pre) and mk.endswith('_add'):
                    g = mk[len(pre):-len('_add')]
                    self.goods[g] = self.goods.get(g, 0) + sign * mv
        self.required = [n.value for n in self.node.value if n.key == 'required_input_goods']
        self.elec = ELECTRICITY in self.required or self.goods.get(ELECTRICITY, 0) < 0

    def strip(self):
        """Cut the effects and required goods: the share methods carry them."""
        for n in self.node.value:
            if n.key in BLEND_SECTIONS or n.key == 'required_input_goods':
                self.src.cuts.append(line_span(self.src.text, n))

    def share_body(self, f):
        out = []
        for sec in BLEND_SECTIONS:
            subs = [(sub, d) for (s2, sub), d in self.mods.items() if s2 == sec and d]
            if not subs:
                continue
            out.append(f'\t{sec} = {{\n' + ''.join(
                f'\t\t{sub} = {{\n' + ''.join(f'\t\t\t{mk} = {fmt(mv * f)}\n' for mk, mv in d.items()) + '\t\t}\n'
                for sub, d in subs) + '\t}\n')
        return ''.join(out)


def fmt(x):
    s = f'{x:.5f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def short(building_key):
    return building_key[len('building_'):] if building_key.startswith('building_') else building_key


# ---------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--game', required=True, help='path to the Victoria 3 "game" folder')
    ap.add_argument('--out', default=None, help=f'default {DEFAULT_OUT}, or {RELEASE_OUT} with --release')
    ap.add_argument('--release', action='store_true',
                    help='the build players get: no test decisions, no generation report, no log lines but '
                         + ' and '.join(RELEASE_LOGS))
    ap.add_argument('--version-label', default='', help='game build label written into the README header')
    ap.add_argument('--test-name', default='', metavar='LABEL',
                    help='a test build for its own mod folder: names the mod "Production Method Rework (LABEL)" '
                         'with its own id, so it never replaces the published one')
    ap.add_argument('--trace-from', default=None, metavar='Y.M.D',
                    help='diagnostic build: flushed T lines from this game date on (see TRACE_FIELDS)')
    args = ap.parse_args()
    global RELEASE
    RELEASE = args.release
    if args.test_name and args.release:
        raise SystemExit('--test-name is for test builds; a release build is the published mod')
    if args.trace_from and (args.release or not re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}', args.trace_from)):
        raise SystemExit('--trace-from takes a game date like 1838.8.15 and never goes into a release build')
    args.out = args.out or (RELEASE_OUT if args.release else DEFAULT_OUT)
    game = args.game

    b_srcs = load_dir(game, 'buildings', BUILDING_FILES)
    g_srcs = load_dir(game, 'production_method_groups')
    p_srcs = load_dir(game, 'production_methods')
    all_b_srcs = load_dir(game, 'buildings')

    groups, group_src = {}, {}
    for s in g_srcs:
        for k, n in s.objects().items():
            pm = pdx.get(n.value, 'production_methods')
            groups[k] = pdx.items(pm) if pm else []
            group_src[k] = (s, pm)
            tex = pdx.get(n.value, 'texture')
            if tex is not None and tex.value == AUTOMATION_ICON:
                AUTOMATION_GROUPS.add(k)
    report_automation_buff = buff_automation(game, p_srcs, groups, b_srcs)
    pms = {}
    for s in p_srcs:
        for k, n in s.objects().items():
            pms[k] = (n, s)
    # Principle variants out of their recipe groups, and the replacements that named them.
    dropped = set()
    for g, (gsrc, gpm) in group_src.items():
        for n in (gpm.value if gpm else []):
            if n.key is None and n.value in DROP_RECIPES:
                gsrc.cuts.append(line_span(gsrc.text, n))
                dropped.add(n.value)
        groups[g] = [p for p in groups[g] if p not in DROP_RECIPES]
    drop_base = {}    # dropped principle variant -> the recipe it replaced (vanilla checks on it read that recipe)
    for p, (n, psrc) in pms.items():
        r = pdx.get(n.value, 'replacement_if_valid')
        if r is not None and r.value in DROP_RECIPES:
            psrc.cuts.append(line_span(psrc.text, r))
            dropped.add(r.value)
            drop_base[r.value] = p
    if dropped != set(DROP_RECIPES):
        raise SystemExit(f'DROP_RECIPES not all found in a group and a replacement: {sorted(set(DROP_RECIPES) - dropped)}')

    # Which buildings use which groups, across every building file (not just the in-scope ones),
    # so a group or method shared with an out-of-scope building is never stripped.
    group_users = {}
    for s in all_b_srcs:
        for bk, bn in s.objects().items():
            pg = pdx.get(bn.value, 'production_method_groups')
            for g in (pdx.items(pg) if pg else []):
                group_users.setdefault(g, set()).add(bk)
    pm_groups = {}
    for g, lst in groups.items():
        for p in lst:
            pm_groups.setdefault(p, set()).add(g)

    report = {'treated': [], 'skipped': [], 'blended': [], 'icon_fallback': [],
              'automation_buff': report_automation_buff}
    treated = []          # (building_key, building_node, building_src, [Recipe])
    candidates = []
    for s in b_srcs:
        for bk, bn in s.objects().items():
            pg = pdx.get(bn.value, 'production_method_groups')
            if not pg or not pdx.items(pg):
                continue
            if s.name in BUILDING_ONLY and bk not in BUILDING_ONLY[s.name]:
                continue
            candidates.append((bk, bn, s, pdx.items(pg)[0], pg))
    for name, only in BUILDING_ONLY.items():
        missing = set(only) - {c[0] for c in candidates if c[2].name == name}
        if missing:
            raise SystemExit(f'{name}: BUILDING_ONLY lists {sorted(missing)}, not found with method groups')
    recipe_groups = {c[3] for c in candidates}

    for bk, bn, s, g0, pg in candidates:
        why = None
        lst = groups.get(g0, [])
        if len(lst) < 2:
            why = f'{g0} has {len(lst)} method(s); nothing to switch between'
        elif not group_users.get(g0, set()) <= {c[0] for c in candidates}:
            why = f'{g0} is also used by out-of-scope buildings'
        else:
            for p in lst:
                if p not in pms:
                    why = f'{p} not found'
                    break
                if not pm_groups[p] <= recipe_groups:
                    why = f'{p} is also used outside recipe groups ({sorted(pm_groups[p] - recipe_groups)})'
                    break
        if why:
            report['skipped'].append({'building': bk, 'reason': why})
            continue
        recipes = [Recipe(p, *pms[p]) for p in lst]
        if bk in WORKFORCE_ELSEWHERE:
            if WORKFORCE_ELSEWHERE[bk] not in pdx.items(pg) or any(r.employment for r in recipes):
                raise SystemExit(f'{bk}: WORKFORCE_ELSEWHERE no longer matches vanilla; update it')
        elif not recipes[0].employment:
            report['skipped'].append({'building': bk, 'reason': f'default recipe {lst[0]} carries no employment'})
            continue
        treated.append((bk, bn, s, recipes, g0, pg))

    # ---- edit vanilla: strip recipe employment and goods, add the labour and share groups -------
    # The vanilla recipe methods keep only what is not scaled by workforce: they mark the recipe
    # the building runs (the retool target) and gate it by technology. Their goods and other
    # workforce-scaled modifiers move into the share methods.
    stripped = set()
    automation = {}   # building -> the automation methods folded into its recipes from AUTOMATION_FROM_TIER
    auto_groups_of = {}   # building -> the automation groups that left it (their methods fold into the recipes)
    elec_pms = []     # the electric recipes' marker methods (ElectricRecipe), one per building that has one
    pair_pms = []     # the recipe + automation pairs' marker methods (PairRecipe, SPLIT_AUTOMATION)
    split_info = {}   # building -> its plain recipes, automation options, pair index and blend members
    for bk, bn, s, recipes, g0, pg in treated:
        for r in recipes:
            if r.key not in stripped:
                r.strip_employment()
                r.strip_blend()
                r.strip_required()
                stripped.add(r.key)
        auto_groups = [g for g in pdx.items(pg) if g != g0 and is_automation(g)]
        if auto_groups and (SPLIT_AUTOMATION or len(recipes) >= AUTOMATION_FROM_TIER):
            # Pat, 2026-10-13: recipes from AUTOMATION_FROM_TIER fold the best automation that runs
            # without electricity; automation that needs it (assembly lines, power looms) becomes a
            # recipe of its own on top of the newest one (ElectricRecipe).
            tops = [Recipe(groups[g][-1], *pms[groups[g][-1]]) for g in auto_groups]
            folded = []
            for g in auto_groups:
                plain = [p for p in groups[g] if not Recipe(p, *pms[p]).needs(ELECTRICITY)]
                folded.append(Recipe(plain[-1], *pms[plain[-1]]) if plain else None)
            automation[bk] = [a for a in folded if a is not None]
            auto_groups_of[bk] = auto_groups
            for n in pg.value:
                if n.key is None and n.value in auto_groups:
                    s.cuts.append(line_span(s.text, n))
            entry = {'building': bk, 'groups': auto_groups, 'folded': [a.key for a in automation[bk]],
                     'from_tier': AUTOMATION_FROM_TIER}
            if SPLIT_AUTOMATION:
                # every recipe with every automation option; (recipe, none) keeps the vanilla recipe as its marker
                if group_users.get(g0, set()) != {bk}:
                    raise SystemExit(f'{bk}: {g0} is shared with {sorted(group_users[g0] - {bk})}; '
                                     'the recipe + automation pairs would need one marker per building')
                plain_r = list(recipes)
                options = automation_options(auto_groups, groups, pms)
                pairs_l, index = [], {}
                for ri, r in enumerate(plain_r, 1):
                    for a, opt in enumerate(options, 1):
                        none = a == 1 and not any(m.blend or m.employment for m in opt)
                        pairs_l.append(r if none else PairRecipe(bk, r, ri, a, opt, pms))
                        index[(ri, a)] = len(pairs_l)
                recipes[:] = pairs_l
                members = [(j, [index[(j, a)] for a in range(1, len(options) + 1)], 'recipe', r)
                           for j, r in enumerate(plain_r, 1)]
                for g in auto_groups:
                    for pk in groups[g]:
                        m = Recipe(pk, *pms[pk])
                        if m.blend or m.employment:
                            members.append((len(members) + 1,
                                            [index[(ri, a)] for ri in range(1, len(plain_r) + 1)
                                             for a, opt in enumerate(options, 1) if any(x.key == pk for x in opt)],
                                            g, m))
                split_info[bk] = {'plain': plain_r, 'options': options, 'index': index, 'members': members,
                                  'pairs': pairs_l}
                gsrc, gpm = group_src[g0]
                markers = [r for r in pairs_l if isinstance(r, PairRecipe)]
                pair_pms.extend(markers)
                gsrc.inserts.append((gpm.end - 1, ''.join(f'\t{r.key}  # PMR: {r.base.key} + {", ".join(m.key for m in r.opt)}\n\t'
                                                          for r in markers)))
                entry['split'] = {'options': [[m.key for m in o] for o in options], 'pairs': [r.key for r in pairs_l]}
            elif any(a.needs(ELECTRICITY) for a in tops):
                if group_users.get(g0, set()) != {bk}:
                    raise SystemExit(f'{bk}: {g0} is shared with {sorted(group_users[g0] - {bk})}; '
                                     'the electric recipe would need one marker per building')
                er = ElectricRecipe(bk, recipes[-1], tops, pms)
                recipes.append(er)
                elec_pms.append(er)
                gsrc, gpm = group_src[g0]
                gsrc.inserts.append((gpm.end - 1, f'\t{er.key}  # PMR: {recipes[-2].key} with electric automation\n\t'))
                entry['electric_recipe'] = {'key': er.key, 'automation': [a.key for a in tops],
                                            'technologies': er.techs}
            report.setdefault('automation', []).append(entry)
        # First in the list, so the building panel's grid shows it in the first slot and the hidden
        # recipe and automation slots after it leave no gap.
        brace = s.text.index('{', pg.start) + 1
        rest = s.text[brace:s.text.find('\n', brace)]
        tail = '' if not rest.strip() else '\n\t\t'   # the list continues on the brace's line
        s.inserts.append((brace, f'\n\t\tpmg_pmr_labour_{short(bk)}  # PMR: blended recipes slot{tail}'))
        # Last in the list: one share group and one lock group per recipe (per blend member when split).
        blend_of = ([(j, m.key) for j, _, _, m in split_info[bk]['members']] if bk in split_info
                    else [(i, r.key) for i, r in enumerate(recipes, 1)])
        s.inserts.append((pg.end - 1, ''.join(
            f'\tpmg_pmr_share_{short(bk)}_{i}  # PMR: share of levels on {key}\n\t'
            f'\tpmg_pmr_key_{short(bk)}_{i}  # PMR: lock for that share\n\t'
            for i, key in blend_of)))

    goods_tex, goods_cost = {}, {}
    for gsrc in load_dir(game, 'goods'):
        for gk, gn in gsrc.objects().items():
            t = pdx.get(gn.value, 'texture')
            if t:
                goods_tex[gk] = t.value
            c = pdx.get(gn.value, 'cost')
            if c is not None:
                goods_cost[gk] = num(c.value, f'{gk} cost')

    # Company Culture (test builds until Pat ships it): each building type making one of a company's top two output
    # goods gets two more blend members, the works members (company_culture.works_members), whose share is the
    # company levels that hold a completed goods tier there. Listed last in the building's production method groups.
    cc_plan, works_of = None, {}
    if not args.release:
        cc_plan = company_culture.plan(game, {bk: (split_info[bk]['plain'] if bk in split_info else
                                                   [r for r in recipes if not isinstance(r, ElectricRecipe)])
                                              for bk, _bn, _s, recipes, _g0, _pg in treated}, goods_cost, goods_tex)
        for bk, _bn, s_, recipes, _g0, pg in treated:
            if bk not in cc_plan.works:
                continue
            j0 = len(split_info[bk]['members']) if bk in split_info else len(recipes)
            plain_ = split_info[bk]['plain'] if bk in split_info else recipes
            works_of[bk] = [(j0 + n, kind, wm, mods) for n, (kind, wm, mods)
                            in enumerate(company_culture.works_members(cc_plan, bk, plain_[-1].texture), 1)]
            s_.inserts.append((pg.end - 1, ''.join(
                f'\tpmg_pmr_share_{short(bk)}_{j}  # PMR: Company Culture works {kind}\n\t'
                f'\tpmg_pmr_key_{short(bk)}_{j}  # PMR: lock for that share\n\t'
                for j, kind, _wm, _m in works_of[bk])))

    # A method another method needs (unlocking_production_methods: pm_elastics needs a sewing machines recipe) is
    # also met by every pair built on it: with the split, the recipe group's marker on such a building is the pair.
    pair_of = {}
    for sp in split_info.values():
        for r in sp['pairs']:
            if isinstance(r, PairRecipe):
                pair_of.setdefault(r.base.key, []).append(r.key)
    for key, (n, psrc) in pms.items():
        upm = pdx.get(n.value, 'unlocking_production_methods')
        listed = pdx.items(upm) if upm else []
        add = [pk for x in listed for pk in pair_of.get(x, []) if pk not in listed]
        if add:
            psrc.inserts.append((upm.end - 1, ''.join(f'\t{pk}  # PMR: a recipe + automation pair\n\t' for pk in add)))

    # ---- second groups: trade-offs and working conditions become option shares -------------------
    # options[bk] = [(group, gi, mode, none method, [Option], standard methods)], gi counting the
    # building's converted groups from 1 and j (Option.j) its options across them.
    options = {}
    treated_keys = {t[0] for t in treated}
    for bk, bn, s, recipes, g0, pg in treated:
        conv, j = [], 0
        for g in pdx.items(pg):
            lst = groups.get(g, [])
            if g == g0 or g not in group_src:
                continue
            viol = [p for p in lst if p.startswith('slave_exploitation_')]
            harsh = [p for p in lst if p.startswith('worker_exploitation_')]
            std = [p for p in lst if p.startswith('default_labour')]
            if g in TRADE_GROUPS:
                mode, none, picks = 'market', lst[0], [(p, None) for p in lst[1:]]
            elif viol or harsh:
                if not std:
                    raise SystemExit(f'{bk}: {g} has no standard labour method; extend the treatment before shipping')
                mode, none, picks = 'treat', std[0], [(p, 'violent') for p in viol[:1]] + [(p, 'harsh') for p in harsh[:1]]
            else:
                continue
            if not group_users.get(g, set()) <= treated_keys:
                raise SystemExit(f'{g} is also used by {sorted(group_users[g] - treated_keys)}, which PMR does not tick')
            opts = []
            for key, role in picks:
                j += 1
                opts.append(Option(bk, j, g, len(conv) + 1, mode, role, key, pms))
            conv.append((g, len(conv) + 1, mode, none, opts, std))
        if conv:
            options[bk] = conv
    converted = {g for conv in options.values() for g, *_ in conv}
    stripped_opts = set()
    elec_of = {t[0]: t[3][-1] for t in treated if isinstance(t[3][-1], ElectricRecipe)}
    for bk, conv in options.items():
        for g, gi, mode, none, opts, std in conv:
            for o in opts:
                if not pm_groups[o.key] <= converted:
                    raise SystemExit(f'{o.key} is also in {sorted(pm_groups[o.key] - converted)}, which PMR does not convert')
                if o.key not in stripped_opts:
                    o.strip()
                    stripped_opts.add(o.key)
                # An option that needs a recipe the electric recipe builds on needs the electric
                # recipe too: on it, the recipe group's marker is the electric one.
                er = elec_of.get(bk)
                upm = pdx.get(o.node.value, 'unlocking_production_methods')
                if er and upm and er.base.key in pdx.items(upm) and er.key not in pdx.items(upm):
                    o.src.inserts.append((upm.end - 1, f'\t{er.key}  # PMR: electric recipe\n\t'))
        # The option share groups, after the recipe ones.
        bsrc, bpg = next((t[2], t[5]) for t in treated if t[0] == bk)
        bsrc.inserts.append((bpg.end - 1, ''.join(
            f'\tpmg_pmr_x_{short(bk)}_{o.j}  # PMR: share of {o.key}\n\t'
            f'\tpmg_pmr_xk_{short(bk)}_{o.j}  # PMR: lock for that share\n\t'
            for g, gi, mode, none, opts, std in conv for o in opts)))
    report['options'] = [{'building': bk, 'group': g, 'mode': mode, 'none': none,
                          'options': [{'j': o.j, 'key': o.key, 'role': o.role, 'goods': o.goods, 'electricity': o.elec}
                                      for o in opts]}
                         for bk, conv in options.items() for g, gi, mode, none, opts, std in conv]

    # ---- groups kept on their best method (AUTO_BEST) -----------------------------------------------
    # auto[bk] = [(group, its methods best first)]
    all_buildings = {bk: bn for s in all_b_srcs for bk, bn in s.objects().items()}
    auto = {}
    for bk, gl in AUTO_BEST.items():
        pg = pdx.get(all_buildings[bk].value, 'production_method_groups') if bk in all_buildings else None
        for g in gl:
            if not pg or g not in pdx.items(pg) or g not in groups or g in converted:
                raise SystemExit(f'AUTO_BEST: {bk} has no group {g} PMR leaves vanilla; update AUTO_BEST')
            order = list(reversed(groups[g]))
            for p in list(order):   # a principle variant before the method it replaces
                r = pdx.get(pms[p][0].value, 'replacement_if_valid')
                if r is not None and r.value in order and order.index(r.value) > order.index(p):
                    order.remove(r.value)
                    order.insert(order.index(p), r.value)
            # every method gated by laws: the laws allow exactly one (bureaucrat professionalism; religious or
            # secular staff with AUTO_SECULAR), so the one that can run is asked, never the one running
            by_law = all(pdx.get(pms[p][0].value, 'unlocking_laws') or pdx.get(pms[p][0].value, 'disallowing_laws')
                         for p in order)
            techs = {p: pdx.items(pdx.get(pms[p][0].value, 'unlocking_technologies'))
                     if pdx.get(pms[p][0].value, 'unlocking_technologies') else [] for p in order}
            elec = {p for p in order if Recipe(p, *pms[p]).needs(ELECTRICITY)}
            auto.setdefault(bk, []).append((g, order, by_law, techs, elec))
    report['auto_best'] = [{'building': bk, 'group': g, 'best_first': order, 'by_law': by_law}
                           for bk, gl in auto.items() for g, order, by_law, *_t in gl]
    # low_pop_method (vanilla's AI picks it in thinly peopled states) would fight the recipe the tick keeps
    # and the method AUTO_BEST keeps: pm_anchorage, the limited trade quantity.
    for p in dict.fromkeys([r.key for t in treated for r in t[3] if r.key in pms]
                           + [p for gl in auto.values() for g, order, *_r in gl for p in order]):
        n, psrc = pms[p]
        lp = pdx.get(n.value, 'low_pop_method')
        if lp is not None:
            psrc.cuts.append(line_span(psrc.text, lp))
    for sec, rel in AUTO_SECULAR.items():
        n, psrc = pms[sec]
        dl, rl = pdx.get(n.value, 'disallowing_laws'), pdx.get(pms[rel][0].value, 'disallowing_laws')
        if dl is None or rl is None or pdx.get(n.value, 'unlocking_laws') is not None:
            raise SystemExit(f'AUTO_SECULAR: {sec} or {rel} no longer gated by disallowing_laws alone; update AUTO_SECULAR')
        s0, e0 = line_span(psrc.text, dl)
        psrc.cuts.append((s0, e0))
        psrc.inserts.append((s0, f'\t# PMR: only where {rel} is barred (vanilla: disallowing_laws = {{ '
                                 + ' '.join(pdx.items(dl)) + ' })\n\tunlocking_laws = { ' + ' '.join(pdx.items(rl)) + ' }\n'))

    if os.path.isdir(args.out):
        for sub in ('common', 'events', 'localization', '.metadata', 'gfx', 'gui'):
            shutil.rmtree(os.path.join(args.out, sub), ignore_errors=True)
        if args.release:    # files only the test build carries
            for name in ('GENERATION_REPORT.json', 'RUNSHEET.md'):
                if os.path.exists(os.path.join(args.out, name)):
                    os.remove(os.path.join(args.out, name))
    os.makedirs(args.out, exist_ok=True)
    unlogged = re.compile(r'debug_log = "PMR;rec=(?!(?:' + '|'.join(RELEASE_LOGS) + r');)[^"]*"')

    def write(rel, text, bom=True):
        if args.release and rel.endswith('.txt'):
            text = drop_empty(unlogged.sub('', text))
        if args.trace_from and rel.endswith('.txt'):
            text = add_trace(rel, text, args.trace_from)
        path = os.path.join(args.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if bom and not text.startswith('\ufeff'):
            text = '\ufeff' + text
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)

    header = ('# GENERATED by tools/pmr/generate.py from the installed game. Do not edit by hand; regenerate.\n'
              f'# N = {N} retool levels per level, retool share = {RETOOL_SHARE}.\n\n')

    for s in {id(t[2]): t[2] for t in treated}.values():
        write(f'common/buildings/{s.name}', s.render())
    for s in p_srcs:
        if s.cuts or s.inserts:
            write(f'common/production_methods/{s.name}', s.render())
    # Vanilla recipe groups that gain an electric recipe or lose a principle variant (DROP_RECIPES), whole,
    # with only those lines changed.
    for s in g_srcs:
        if s.inserts or s.cuts:
            write(f'common/production_method_groups/{s.name}', s.render())
    write('common/production_methods/pmr_electric_production_methods.txt', header + ELECTRIC_DOC
          + '\n'.join(er.method() for er in elec_pms))
    if pair_pms:
        write('common/production_methods/pmr_pair_production_methods.txt', header
              + '# Recipe + automation pairs (PairRecipe, SPLIT_AUTOMATION): markers of the retool target only.\n\n'
              + '\n'.join(r.method() for r in pair_pms))

    # ---- new script ------------------------------------------------------------------------------
    labour_pms, labour_groups, retools, costs, loc = [], [], [], [], []
    site_types = []    # every retool site type, hidden from the state Buildings tab
    blend_pms, blend_groups = [], []
    triggers = []
    tick_effects, dispatch = [], []
    cost_values = {}
    for line in open(os.path.join(game, 'common', 'script_values', 'building_values.txt'), encoding='utf-8-sig'):
        parts = line.split('#')[0].split('=')
        if len(parts) == 2 and parts[0].strip().startswith('construction_cost_'):
            try:
                cost_values[parts[0].strip()] = float(parts[1])
            except ValueError:
                pass

    gfx_root = game
    custom_new = []
    recipe_keys, recipe_tex, recipe_elec = {}, {}, {}
    bar_keys = {}          # building -> the recipes its bars show (recipe_tex's keys): with the split, the plain ones
    weight = wage_weights(game)
    auto_ui = {}           # building -> (its first automation group, auto_tiers), for the automation bar
    profit_goods = set()   # every good a recipe's profit is read at (pmr_price_<good>)
    pair_ui = {}           # building -> pairs(): every plain recipe with every automation, for the Methods view

    for bk, bn, s, recipes, g0, pg in treated:
        b = short(bk)
        sp = split_info.get(bk)
        plain = sp['plain'] if sp else recipes   # what the recipe bars show: with the split, recipes without automation
        r0 = plain[0]
        # The fixed labour method's icon: the building's main output good, drawn gold (from the first recipe
        # that makes goods: a port's anchorage makes none).
        r_out = next((r for r in plain if r.outputs), r0)
        good = max(r_out.outputs.items(), key=lambda kv: kv[1])[0] if r_out.outputs else None
        icon_tex = r0.texture
        src = os.path.join(gfx_root, goods_tex[good]) if good in goods_tex else None
        if src and os.path.isfile(src):
            icon_tex = f'gfx/interface/icons/production_method_icons/pmr_labour_{b}.dds'
            path = os.path.join(args.out, icon_tex)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            icons.write_dds(icons.gold_icon(src), path)
        else:
            report['icon_fallback'].append({'building': bk, 'good': good, 'missing': src})
        recipe_keys[bk] = [r.key for r in recipes]
        recipe_tex[bk] = [r.texture for r in plain]
        bar_keys[bk] = [r.key for r in plain]
        if sp:
            SPLIT_BARS[b] = len(plain)
        if len(plain) > len(TIER_COLORS):
            raise SystemExit(f'{bk}: {len(plain)} recipes, but TIER_COLORS has {len(TIER_COLORS)}; add a colour')
        for i, r in enumerate(recipes, 1):
            custom_new.append(f'\ttext = {{\n\t\ttrigger = {{ is_building_type = {bk} state = {{ var:pmr_to_{b} = {i} }} }}\n'
                              f'\t\tlocalization_key = {r.key}\n\t}}\n')
        # Carries nothing since the workforce is blended (Pat, 2026-10-13): it is the slot the building
        # browser rows and market lists show, drawn as the gold main output good.
        labour_pms.append(
            f'# {bk}: the blended-recipes slot. Goods and workforce come from the share methods.\n'
            f'pm_pmr_labour_{b} = {{\n'
            f'\ttexture = "{icon_tex}"\n'
            f'\tis_default = yes\n}}\n')
        labour_groups.append(
            f'pmg_pmr_labour_{b} = {{\n'
            f'\ttexture = "gfx/interface/icons/generic_icons/mixed_icon_base.dds"\n'
            f'\tproduction_methods = {{\n\t\tpm_pmr_labour_{b}\n\t}}\n}}\n')

        rc = pdx.get(bn.value, 'required_construction')
        base_cost = cost_values.get(rc.value) if rc else None
        if base_cost is None and rc is not None:
            base_cost = num(rc.value, f'{bk}.required_construction')
        if base_cost is None:
            raise SystemExit(f'{bk}: no required_construction')
        retool_cost = base_cost * RETOOL_SHARE / N
        costs.append(f'pmr_retool_cost_{b} = {fmt(retool_cost)}  # {rc.value} = {fmt(base_cost)} x {RETOOL_SHARE} / {N}')
        icon = pdx.get(bn.value, 'icon').value
        retools.append(retool_buildings(b, bk, icon))
        site_types += priv_slots(b) + [f'building_pmr_retool_gov_{b}', f'building_pmr_retool_gova_{b}']
        triggers.append(retool_triggers(b, bk))
        costs.append(retool_values(b))

        for rbx in priv_slots(b):
            loc += [f' {rbx}:0 "Retooling: ${bk}$"',
                    f' {rbx}_desc:0 "Switches one level of ${bk}$ to its newest recipe."']
        for r in recipes:
            if isinstance(r, (ElectricRecipe, PairRecipe)):
                loc.append(f' {r.key}:0 "' + ' + '.join(f'${x.key}$' for x in [r.base] + r.autos) + '"')
        loc += [f' pmg_pmr_labour_{b}:0 "Recipes"',
                f' pm_pmr_labour_{b}:0 "Blended Recipes"',
                f' building_pmr_retool_gov_{b}:0 "Retooling (Government): ${bk}$"',
                f' building_pmr_retool_gov_{b}_desc:0 "Switches the government\'s levels of ${bk}$ to the new recipe."',
                f' building_pmr_retool_gova_{b}:0 "Retooling (Government): ${bk}$"',
                f' building_pmr_retool_gova_{b}_desc:0 "Switches your government\'s levels of ${bk}$ here to the new recipe."']

        # Blended recipe: per recipe i, a share group of SHARE_STEPS + 1 methods carrying recipe i's
        # workforce-scaled modifiers x n / SHARE_STEPS, so the building's goods are the level-weighted
        # mix of its recipes, scaled by workforce and throughput like any recipe. Share method n
        # unlocks only while lock method n of the same recipe is active (unlocking_production_methods,
        # which vanilla uses the same way for pm_elastics). Only one share method per group is ever
        # available, so the AI cannot move a share; the locks carry nothing, and vanilla's AI keeps
        # the current method when a change gains nothing (PRODUCTION_METHOD_STICKINESS_*).
        # Every share method also unlocks under the switching lock _any (unlocking_production_methods
        # is any-of, as vanilla's pm_sewing_machines / pm_electric_sewing_machines lists show), so the
        # tick can change the share without first locking out the one that runs. Lock n in turn
        # unlocks only while share n runs, so each lock group offers the AI two methods (lock n and
        # _any), not SHARE_STEPS + 2.
        # _any comes FIRST in each lock group (LOCK_ANY_FIRST): when the game finds a share and its lock
        # both unavailable, it replaces each with the first available method of its group, judged against
        # the other's old method. With _any last, share n and lock m swap places on every pass and never
        # settle: on 16 August 1838 a new Hanoverian rye farm, given one existing farm's share and
        # another's lock, switched methods without end and the game froze. With _any first the lock
        # becomes _any and the share the old lock's step, both available, and the next tick relocks.
        elec_tiers = []
        fold_techs = {}   # tier -> the technologies of the methods folded into it (pmr_best_<b> asks the owner)
        econ = []         # per recipe: (goods per level, wage units per level), for pmr_profit_<b>
        auto_tiers = []   # the automation bar's levels: [(name key, texture or None, [tiers])], least automated first
        if sp:
            # one level per automation option, its key the option's name (PMR_MVA_<b>_<a>, methods_view_loc)
            for a, opt in enumerate(sp['options'], 1):
                on = [m for m in opt if m.blend or m.employment]
                auto_tiers.append((f'PMR_MVA_{b}_{a}', on[-1].texture if on else None,
                                   [sp['index'][(ri, a)] for ri in range(1, len(sp['plain']) + 1)]))
            auto_ui[bk] = (auto_groups_of[bk][0], auto_tiers)
        elif automation.get(bk):
            plain_i = [i for i, r in enumerate(recipes, 1) if not isinstance(r, ElectricRecipe)]
            er = [(i, r) for i, r in enumerate(recipes, 1) if isinstance(r, ElectricRecipe)]
            auto_tiers.append((groups[auto_groups_of[bk][0]][0], None, [i for i in plain_i if i < AUTOMATION_FROM_TIER]))
            auto_tiers.append((automation[bk][0].key, automation[bk][0].texture,
                               [i for i in plain_i if i >= AUTOMATION_FROM_TIER]))
            for i, r in er:
                elec_auto = [a for a in r.autos if a.needs(ELECTRICITY)] or r.autos
                auto_tiers.append((elec_auto[0].key, r.texture, [i]))
            auto_ui[bk] = (auto_groups_of[bk][0], auto_tiers)
        # Each recipe (each recipe + automation pair with the split) as a retool target: what a level of it makes,
        # costs and needs.
        tiers_of = []     # per retool target: (recipe, the automation run with it)
        TARGET_EMPLOYEES[bk] = []
        # vanilla divides profit by the building's whole workforce, so the other groups' first methods (ownership)
        # count too; the art academy's are all there (q29: its term came out at 4 million with 1 for its workforce)
        other_emp = sum(sum(Recipe(groups[g][0], *pms[groups[g][0]]).employment.values())
                        for g in pdx.items(pg) if g != g0 and 'automation' not in g and groups.get(g) and groups[g][0] in pms)
        for i, r in enumerate(recipes, 1):
            if isinstance(r, ElectricRecipe):
                autos = r.autos
                blend, emp, elec, clamped = effective(r.base, autos)
            elif isinstance(r, PairRecipe):
                autos = r.autos
                blend, emp, elec, clamped = effective(r.base, autos)
            else:
                autos = automation.get(bk, []) if i >= AUTOMATION_FROM_TIER and not sp else []
                blend, emp, elec, clamped = effective(r, autos)
            fold_techs[i] = [] if sp else list(dict.fromkeys(t for a in autos for t in a.unlock_techs))
            econ.append(recipe_econ(blend, emp, weight))
            TARGET_EMPLOYEES[bk].append(sum(emp.values()) + other_emp)
            profit_goods.update(g for g in econ[-1][0] if goods_cost.get(g))
            if elec:
                elec_tiers.append(i)
            if clamped:
                report.setdefault('employment_clamped', []).append({'building': bk, 'recipe': r.key, 'below_zero': clamped})
            tiers_of.append((r, autos, blend, emp, elec))
        # The blend members: without the split, each recipe with its folded automation (recipe i is member i). With
        # it (Pat, 2026-10-18 18:36Z), each plain recipe and each automation method that does something, on its own:
        # an automation member carries the method's goods and its (negative) workforce, x its share of the levels.
        if sp:
            members = []
            for j, idxs, grp, m in sp['members']:
                if grp == 'recipe':
                    blend, emp, _e, _c = effective(m, [])
                else:
                    blend = {sec: {k2: v2 for k2, v2 in mods.items() if v2} for sec, mods in m.blend.items()}
                    blend = {sec: mods for sec, mods in blend.items() if mods}
                    emp = {k2: v2 for k2, v2 in m.employment.items() if v2}
                members.append((j, m, blend, emp, SHARE_STEPS if j == 1 else 0,
                                {'member': j, 'kind': grp, 'pairs': idxs}))
        else:
            members = [(i, r, blend, emp, SHARE_STEPS if i == 1 else 0,
                        {'tier': i, 'automation': [a.key for a in autos], 'needs_electricity': elec})
                       for i, (r, autos, blend, emp, elec) in enumerate(tiers_of, 1)]
        # Company Culture's works members: unscaled goods mults (a goods tier's output and its extra input over the
        # base recipe), in WORKS_STEPS steps of the full share, on the company levels that hold a tier (works_effect).
        for j, kind, wm, mods in works_of.get(bk, []):
            members.append((j, wm, {'building_modifiers': mods}, {}, 0,
                            {'member': j, 'kind': 'works', 'works': kind, 'steps': company_culture.works_steps(kind)}))
        if bk in works_of and cc_plan.works[bk]['in']:
            profit_goods.add(cc_plan.works[bk]['in'])   # works_effect reads its price (pmr_px_<good>)
        for i, r, blend, emp, default_n, rep in members:
            shares, keys = [], []
            any_key = f'pm_pmr_key_{b}_{i}_any'
            secs = list(dict.fromkeys(list(blend) + (['building_modifiers'] if emp else [])))
            steps = rep.get('steps', SHARE_STEPS)
            works = rep.get('kind') == 'works'
            for n in range(steps + 1):
                f = n / steps
                body = (''.join(
                    f'\t{sec} = {{\n\t\tunscaled = {{\n'
                    + ''.join(f'\t\t\t{mk} = {fmt(mv * f)}\n' for mk, mv in blend[sec].items())
                    + '\t\t}\n\t}\n' for sec in secs if n > 0) if works else ''.join(
                    f'\t{sec} = {{\n'
                    + (f'\t\tworkforce_scaled = {{\n'
                       + ''.join(f'\t\t\t{mk} = {fmt(mv * f)}\n' for mk, mv in blend[sec].items())
                       + '\t\t}\n' if sec in blend else '')
                    + (f'\t\tlevel_scaled = {{\n'
                       + ''.join(f'\t\t\t{mk} = {fmt(mv * f)}\n' for mk, mv in emp.items())
                       + '\t\t}\n' if sec == 'building_modifiers' and emp else '')
                    + '\t}\n'
                    for sec in secs if n > 0))
                dflt = '\tis_default = yes\n' if n == default_n else ''
                blend_pms.append(
                    f'pm_pmr_share_{b}_{i}_{n} = {{\n\ttexture = "{r.texture}"\n{dflt}'
                    f'\tunlocking_production_methods = {{ pm_pmr_key_{b}_{i}_{n} {any_key} }}\n{body}}}\n')
                # The lock unlocks only while its own share runs, so the AI has two locks to weigh, not
                # SHARE_STEPS + 2. The switch never needs another: it goes through _any.
                blend_pms.append(f'pm_pmr_key_{b}_{i}_{n} = {{\n\ttexture = "{GENERIC_ICON}"\n{dflt}'
                                 f'\tunlocking_production_methods = {{ pm_pmr_share_{b}_{i}_{n} }}\n}}\n')
                shares.append(f'pm_pmr_share_{b}_{i}_{n}')
                keys.append(f'pm_pmr_key_{b}_{i}_{n}')
                pct = round(100 * f)
                loc += ([f' pm_pmr_share_{b}_{i}_{n}:0 "${r.key}$"',   # Pat 01:07Z read "13/40" as levels
                         f' pm_pmr_key_{b}_{i}_{n}:0 "${r.key}$ share lock ({n}/{steps})"'] if works else
                        [f' pm_pmr_share_{b}_{i}_{n}:0 "${r.key}$ ({pct}% of levels)"',
                         f' pm_pmr_key_{b}_{i}_{n}:0 "${r.key}$ share lock ({pct}%)"'])
            blend_pms.append(f'{any_key} = {{\n\ttexture = "{GENERIC_ICON}"\n}}\n')
            keys.insert(0, any_key)   # first: see LOCK_ANY_FIRST above
            loc.append(f' {any_key}:0 "${r.key}$ share lock (switching)"')
            # No is_hidden_when_unavailable: with it, a share group lists only its one unlocked method,
            # and the building panel, which shows a PMR building's groups of exactly one method (the
            # fixed labour slot), drew every share group's icon in the row (seen in 1.14.5).
            for g, lst, what in ((f'pmg_pmr_share_{b}_{i}', shares, 'share of levels'),
                                 (f'pmg_pmr_key_{b}_{i}', keys, 'share lock')):
                blend_groups.append(f'{g} = {{\n\ttexture = "{GENERIC_ICON}"\n'
                                    '\tproduction_methods = {\n' + ''.join(f'\t\t{x}\n' for x in lst) + '\t}\n}\n')
                loc.append(f' {g}:0 "${r.key}$ {what}"')
            report['blended'].append({'building': bk, 'recipe': r.key, **rep, 'blend': blend, 'employment': emp})

        # Option shares: the same share / lock / switching-lock pattern as the recipes, carrying the
        # option's every effect x n / SHARE_STEPS. n = 0 is the default: a new building starts on none.
        for g, gi, mode, none, opts, std in options.get(bk, []):
            for o in opts:
                shares, keys = [], []
                any_key = f'pm_pmr_xk_{b}_{o.j}_any'
                what = 'workforce' if mode == 'treat' else 'building'
                for n in range(SHARE_STEPS + 1):
                    dflt = '\tis_default = yes\n' if n == 0 else ''
                    blend_pms.append(
                        f'pm_pmr_x_{b}_{o.j}_{n} = {{\n\ttexture = "{o.texture}"\n{dflt}'
                        f'\tunlocking_production_methods = {{ pm_pmr_xk_{b}_{o.j}_{n} {any_key} }}\n'
                        f'{o.share_body(n / SHARE_STEPS) if n else ""}}}\n')
                    blend_pms.append(f'pm_pmr_xk_{b}_{o.j}_{n} = {{\n\ttexture = "{GENERIC_ICON}"\n{dflt}'
                                     f'\tunlocking_production_methods = {{ pm_pmr_x_{b}_{o.j}_{n} }}\n}}\n')
                    shares.append(f'pm_pmr_x_{b}_{o.j}_{n}')
                    keys.append(f'pm_pmr_xk_{b}_{o.j}_{n}')
                    loc += [f' pm_pmr_x_{b}_{o.j}_{n}:0 "${o.key}$ ({n}% of the {what})"',
                            f' pm_pmr_xk_{b}_{o.j}_{n}:0 "${o.key}$ share lock ({n}%)"']
                blend_pms.append(f'{any_key} = {{\n\ttexture = "{GENERIC_ICON}"\n}}\n')
                keys.insert(0, any_key)   # first: see LOCK_ANY_FIRST
                loc.append(f' {any_key}:0 "${o.key}$ share lock (switching)"')
                for grp, lst, label in ((f'pmg_pmr_x_{b}_{o.j}', shares, 'share'),
                                        (f'pmg_pmr_xk_{b}_{o.j}', keys, 'share lock')):
                    blend_groups.append(f'{grp} = {{\n\ttexture = "{GENERIC_ICON}"\n'
                                        '\tproduction_methods = {\n' + ''.join(f'\t\t{x}\n' for x in lst) + '\t}\n}\n')
                    loc.append(f' {grp}:0 "${o.key}$ {label}"')

        if sp:
            # the Methods view's grid is the retool targets themselves: pair (r, a) is target index[(r, a)]
            pair_ui[bk] = {'recipes': list(range(1, len(plain) + 1)), 'options': sp['options'],
                           'keys': [r.key for r in plain], 'index': sp['index'], 'split': True,
                           'econ': {ra: econ[i - 1] for ra, i in sp['index'].items()},
                           'members': [(j, idxs, grp) for j, idxs, grp, _m in sp['members']]}
        elif automation.get(bk):
            pair_ui[bk] = pairs(recipes, auto_groups_of[bk], groups, pms, weight)
            profit_goods.update(g for gd, _ in pair_ui[bk]['econ'].values() for g in gd if goods_cost.get(g))
        tick_effects.append(option_effects(bk, b, options.get(bk, []), goods_cost, plain)
                            + tick_effect(bk, b, recipes, elec_tiers, options.get(bk, []), fold_techs,
                                          econ, goods_cost, [t for _, _, t in auto_tiers], pair_ui.get(bk),
                                          [(j, company_culture.works_steps(kind)) for j, kind, *_r in works_of.get(bk, [])])
                            + (company_culture.works_effect(cc_plan, bk, *[j for j, *_r in works_of[bk]], *([None] * (2 - len(works_of[bk]))))
                               if bk in works_of else ''))
        recipe_elec[bk] = elec_tiers
        dispatch.append(bk)
        report['treated'].append({'building': bk, 'recipe_group': g0, 'recipes': [r.key for r in recipes],
                                  'icon_good': good,
                                  'electric_tiers': elec_tiers,
                                  'retool_cost': retool_cost})

    # ---- companies: a company that owns a building type may own its private retooling ----------
    # When the investment pool builds a building type a company lists in building_types, the company
    # can be chosen as owner (OWNER_COMPANY_EXPANSION_CHANCE_MULTIPLIER, x OWNER_COMPANY_OWN_STATE_MULT
    # in its headquarters state). With COMPANY_RETOOL each treated type's first COMPANY_RETOOL_SLOTS
    # private retool buildings (and ABROAD_SLOT with COMPANY_RETOOL_ABROAD) are listed beside it,
    # rewriting the vanilla company files with only those lines inserted. Off 2026-10-12 to keep
    # Retooling icons out of the company panels; on again 2026-10-13 (Pat): the autonomous investment
    # AI favours expanding a building a company lists
    # (AUTONOMOUS_INVESTMENT_COMPANY_TARGET_STATE_WITH_BUILDING_CONSTRUCTION_FACTOR), which is how
    # retool levels stack. A company-owned building retools either way: its headquarters owns levels
    # the way a Financial District does, so levels_owned_by_country counts them for its country.
    # Pat, 2026-10-13 22:53Z: the retooling of a company's additional industries (extension_building_types, the
    # industry charter's choice) too. 1.14.5 gives script no way to read which one the charter picked (no trigger,
    # value or effect names it; only the company panel does), so both are listed in building_types all the time:
    # a company may own the retooling of an additional industry it has not chosen, and its panel shows those icons.
    # In extension_building_types they would be offered as additional industries of their own instead.
    report['company_types'] = []
    if COMPANY_RETOOL:
        retool_of = {t[0]: priv_slots(short(t[0]))[:COMPANY_RETOOL_SLOTS]
                     + (priv_slots(short(t[0]))[ABROAD_SLOT - 1:ABROAD_SLOT] if COMPANY_RETOOL_ABROAD else [])
                     for t in treated}
        for csrc in load_dir(game, 'company_types'):
            for ck, cn in csrc.objects().items():
                # Pat, 2026-10-19 01:21Z (Krupp making Krupp Guns with no Hallmark Goods): in the test build every
                # company's prestige goods wait for Company Culture's Hallmark Goods. The 66 vanilla lets make them
                # whenever prosperous get a trigger; the rest already wait for the variable the node sets.
                if (not args.release and pdx.get(cn.value, 'possible_prestige_goods')
                        and not pdx.get(cn.value, 'prestige_goods_trigger')):
                    csrc.inserts.append((cn.end - 1, '\tprestige_goods_trigger = { custom_tooltip = { '
                                                     'text = PMR_CC_PG_REQ has_variable = pmr_cc_hallmark } }  # PMR\n'))
                    report.setdefault('hallmark_gate', []).append(ck)
                bt = pdx.get(cn.value, 'building_types')
                if not bt or not bt.is_block:
                    continue
                listed = pdx.items(bt)
                ext = pdx.get(cn.value, 'extension_building_types')
                extra = [x for x in (pdx.items(ext) if ext and ext.is_block else []) if x not in listed]
                new = [(x, rbx) for x in listed + extra if x in retool_of for rbx in retool_of[x] if rbx not in listed]
                if not new:
                    continue
                csrc.inserts.append((bt.end - 1, ''.join(f'\t{rbx}  # PMR: retooling of {x}'
                                                          + (' (additional industry)' if x in extra else '') + '\n\t'
                                                          for x, rbx in new)))
                report['company_types'].append({'company': ck, 'file': csrc.name, 'added': [rbx for _, rbx in new]})
            if csrc.inserts:
                write(f'common/company_types/{csrc.name}', csrc.render())
    # the panels listing a company's industries hide them (Pat 2026-10-19 02:32Z, company_panel.py)
    company_panel.RETOOL_TYPES = sorted({rbx for c in report['company_types'] for rbx in c['added']})

    write('common/production_methods/pmr_labour_production_methods.txt', header + '\n'.join(labour_pms))
    write('common/production_method_groups/pmr_labour_groups.txt', header + '\n'.join(labour_groups))
    write('common/buildings/pmr_retool_buildings.txt', header + '\n'.join(retools))
    # Written even while RETOOL_CREW is 0 (nothing uses them then), so a deployed folder never keeps a stale copy.
    write('common/production_methods/pmr_retool_production_methods.txt', header + RETOOL_CREW_DOC +
          'pm_pmr_retool_crew = {\n'
          f'\ttexture = "{RETOOL_CREW_ICON}"\n'
          '\tbuilding_modifiers = {\n\t\tworkforce_scaled = {\n'
          f'\t\t\tgoods_output_{RETOOL_CREW_GOOD}_add = {RETOOL_CREW_OUTPUT}\n'
          '\t\t}\n\t\tlevel_scaled = {\n'
          f'\t\t\tbuilding_employment_{RETOOL_CREW_POP}_add = {RETOOL_CREW}\n'
          '\t\t}\n\t}\n}\n')
    write('common/production_method_groups/pmr_retool_groups.txt', header +
          'pmg_pmr_retool_crew = {\n'
          f'\ttexture = "{RETOOL_CREW_ICON}"\n'
          '\tproduction_methods = {\n\t\tpm_pmr_retool_crew\n\t}\n}\n')
    loc += [' pmg_pmr_retool_crew:0 "Crew"', ' pm_pmr_retool_crew:0 "Retooling Crew"']
    write('common/building_groups/pmr_building_groups.txt', header +
          '# No lens, not in the outliner. 1.14.5 put privately funded retool levels in the government queue\n'
          '# with this group standing alone, even marked is_government_funded = no and its buildings\n'
          '# ownership_type = self. A private construction needs an investor, and investors (Financial\n'
          '# Districts, Manor Houses) pick by the building groups their investment_scores name, which a\n'
          '# child group inherits from its parent. bg_manufacturing is the parent with no land usage or\n'
          '# resource cap to inherit; Financial Districts score it.\n'
          '# Investors retool at home in bg_pmr_retool and abroad in bg_pmr_retool_abroad (see ABROAD_SLOT in\n'
          '# tools/pmr/generate.py): a foreign pool weighs the home slots at 0, so it does not pick a state where\n'
          '# only the host\'s investors may build.\n'
          'bg_pmr_retool = {\n\tparent_group = bg_manufacturing\n\tcategory = urban\n\tis_government_funded = no\n'
          '\talways_possible = yes\n\tis_shown_in_outliner = no\n\tforeign_investment_ai_factor = 0\n}\n\n'
          'bg_pmr_retool_abroad = {\n\tparent_group = bg_manufacturing\n\tcategory = urban\n\tis_government_funded = no\n'
          '\talways_possible = yes\n\tis_shown_in_outliner = no\n\tforeign_investment_ai_factor = 1\n}\n\n'
          '# The government-owned share is retooled by the government: the player builds it from the state,\n'
          '# AI governments by ai_value. Shaped on bg_government, which is how vanilla marks government-only\n'
          '# construction; the lens puts it in the development construction list.\n'
          'bg_pmr_retool_gov = {\n\tcategory = urban\n\tis_government_funded = yes\n\talways_possible = yes\n'
          '\tlens = development\n\tis_shown_in_outliner = no\n}\n\n'
          '# The player\'s government retooling its own levels abroad (Pat 2026-10-13 21:26Z). Not government-funded,\n'
          '# like any building a government builds in another country\'s state (inferred: vanilla\'s government-funded\n'
          '# groups are administration, military and public works, which only a state\'s owner builds).\n'
          'bg_pmr_retool_gov_abroad = {\n\tparent_group = bg_manufacturing\n\tcategory = urban\n\tis_government_funded = no\n'
          '\talways_possible = yes\n\tis_shown_in_outliner = no\n\tforeign_investment_ai_factor = 0\n}\n')
    write('common/scripted_triggers/pmr_triggers.txt', header + RETOOL_TRIGGERS_DOC + '\n'.join(triggers))
    write('common/script_values/pmr_values.txt', header +
          f'pmr_retool_levels_per_level = {N}\n\n' + '\n'.join(costs) + '\n')
    write('common/production_methods/pmr_blend_production_methods.txt', header +
          '# Share methods: pm_pmr_share_<b>_<recipe>_<n> carries the recipe\'s workforce-scaled\n'
          f'# modifiers x n / {SHARE_STEPS}. Each unlocks while pm_pmr_key_<b>_<recipe>_<n>\n'
          '# or the switching lock pm_pmr_key_<b>_<recipe>_any is active.\n\n'
          + '\n'.join(blend_pms))
    write('common/production_method_groups/pmr_blend_groups.txt', header + '\n'.join(blend_groups))
    write('common/scripted_effects/pmr_effects.txt', header + shared_effects(sorted(set(option_goods(options)) | profit_goods)) + '\n'.join(tick_effects)
          + dispatch_effects(dispatch) + '\n' + auto_best_effects(auto))
    write('common/on_actions/pmr_on_actions.txt', header + ON_ACTIONS.replace('TECH_CRUMB', flush_log('TECH', '-')))
    write('events/pmr_events.txt', header + EVENTS)
    # Defines merge key by key, so this file holds only the one PMR changes; zz_ loads it after vanilla.
    write('common/defines/zz_pmr_ai.txt', header +
          '# Investment pool randomness (Pat, 2026-10-13): the building-type roll goes from 1/21..21 to\n'
          '# 1/11..11. Vanilla: common/defines/00_ai.txt, PRODUCTION_BUILDING_AUTONOMOUS_INVESTMENT_RANDOM_FACTOR_MULT = 2.0.\n'
          f'NAI = {{\n\tPRODUCTION_BUILDING_AUTONOMOUS_INVESTMENT_RANDOM_FACTOR_MULT = {INVESTMENT_RANDOM_FACTOR_MULT:.1f}\n}}\n')
    treat = treatment_buildings(all_b_srcs, groups, pms)
    report['probe_treat'] = [t[0] for t in treat]
    write('common/script_values/pmr_probe_values.txt', header + probe_values(treat))
    write('common/scripted_effects/pmr_probe_effects.txt', header + probe_effects(treat, pms, goods_cost))
    pb_eff, pb_mods, pb_loc = principle_bonus(treated, drop_base, pms)
    write('common/scripted_effects/pmr_principle_effects.txt', header + pb_eff)
    write('common/static_modifiers/pmr_principle_modifiers.txt', header + pb_mods)
    loc += pb_loc
    compat_trig, compat_files, compat_lines = vanilla_compat(game, treated, auto_groups_of, groups, pms, group_users,
                                                             drop_base, split_info)
    write(COMPAT_TRIGGERS, header + compat_trig)
    for rel, text in compat_files.items():
        write(rel, text)
    report['vanilla_compat'] = compat_lines
    write('common/scripted_guis/pmr_sguis.txt', header + SGUI_DOC + ''.join(gov_retool_sgui(bk) for bk in dispatch)
          + '# The same for every state at once, from the Buildings tab\'s building type row. Country scope.\n\n'
          + ''.join(gov_retool_country_sgui(bk) for bk in dispatch)
          + ('# The Buildings panel\'s Owners\' Methods tab, recounted from the cached picks when the tab is clicked.\n'
             'pmr_mv_refresh_sgui = {\n\tscope = country\n\teffect = {\n\t\tpmr_pf_all = yes\n\t\tpmr_mv_refresh = yes\n'
             # a company panel opening skips its own recount today (company_panel.REFRESH_SGUI)
             f'\t\tset_variable = {{ name = {company_panel.TODAY} value = yes days = 1 }}\n\t}}\n}}\n'
             if PROFIT_TARGET else ''))
    # the panel's second group bars, per building type
    def pm_tex(key):
        t = pdx.get(pms[key][0].value, 'texture')
        return t.value if t else GENERIC_ICON
    opt_ui = {bk: [(gi, mode, none, pm_tex(none), os_) for g, gi, mode, none, os_, std in conv]
              for bk, conv in options.items() if conv}
    # the pick row, on every type the profit calculation covers (PROFIT_TARGET)
    pick_ui = {bk: recipe_keys[bk] for bk in dispatch} if PROFIT_TARGET else {}
    mv_keys = pick_ui   # the Private tab's Methods view covers the same types
    ai_of = private_investment.ai_groups(game) if mv_keys else {}   # each row's AI weight (Pat 18:40Z)
    # the policy parts of each AI weight, for its tooltip's nested Policy line (Pat 2026-10-19 00:01Z); in the test
    # build a company type's Expanded Works (company_culture.ai_value_tail) is what is left of Policy
    owners_of = private_investment.company_owners(game) if mv_keys else {}
    ai_parts = {bk: private_investment.ai_parts(bk, owners_of, ai_of)
                + ([('works', None)] if not args.release and bk in owners_of else []) for bk in ai_of}
    write('common/customizable_localization/pmr_custom_loc.txt', header +
          '# Building scope. The recipe a building runs, which is the one any retooling moves it to.\n'
          'pmr_new_recipe = {\n\ttype = building\n\tlog_loc_errors = no\n' + ''.join(custom_new) + '}\n'
          + '\n# State scope. A note after an option the state can\'t run (technology, laws, electricity).\n'
          + ''.join(f'pmr_xlk_{short(bk)}_{o.j} = {{\n\ttype = state\n\trandom_valid = no\n'
                    f'\ttext = {{\n\t\ttrigger = {{ var:pmr_xav_{o.j}_{short(bk)} = 0 }}\n'
                    f'\t\tlocalization_key = {"PMR_OPT_BARRED" if mode == "treat" else "PMR_OPT_LOCKED"}\n\t}}\n'
                    '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n'
                    for bk, groups in opt_ui.items() for gi, mode, none, tex, os_ in groups for o in os_)
          + '\n# State scope. The profit pick\'s name and each recipe\'s note on the pick row (pick_row).\n'
          + pick_custom_loc(pick_ui) + (methods_view_custom_loc(mv_keys, pair_ui) if mv_keys else ''))
    if mv_keys:
        # who would buy a new private level of each type (Pat 2026-10-19 00:01Z; private_investment.buyer_odds)
        bo_vals, bo_eff = private_investment.buyer_odds(game, [bk for bk in mv_keys if bk in ai_of], owners_of)
        write('common/script_values/pmr_bo_values.txt', header + bo_vals)
        mv_extra = {bk: ([f'pmr_ash_{a}_{short(bk)}' for a in range(1, len(auto_ui[bk][1]) + 1)]
                         if bk in auto_ui and pair_ui.get(bk, {}).get('split') else [])
                    + [x for gi, _m, _n, _t, os_ in opt_ui.get(bk, [])
                       for x in [f'pmr_xn_{gi}_{short(bk)}'] + [f'pmr_x_{o.j}_{short(bk)}' for o in os_]]
                    for bk in mv_keys}
        write('common/scripted_effects/pmr_mv_effects.txt', header
              + methods_view_effects(mv_keys, pair_ui, ai_of, ai_parts, owners_of, mv_extra) + bo_eff)
        write('gui/pmr_methods_view.gui', methods_view_gui(mv_keys, recipe_tex, pair_ui, ai_of, owners_of, opt_ui, auto_ui),
              bom=False)
    # AUTO_BEST types PMR does not retool: no selectors either, and nothing in their place.
    also = [bk for bk in auto if bk not in dispatch]
    write('gui/building_details_panel.gui', gate_type_copies(patch_building_panel(
        recipe_tex, open(os.path.join(game, 'gui', 'building_details_panel.gui'), encoding='utf-8-sig').read(),
        opt_ui, also, auto_ui, pick_ui)), bom=False)
    def vanilla_gui(name):
        return open(os.path.join(game, 'gui', name), encoding='utf-8-sig').read()
    # The Buildings tab: the building type row's grid (the first of three) becomes the country recipe
    # bar, and the upgrade button goes left of nationalize. Expanded, each building's row is the
    # details panel's condensed_building_information, recipe row and button included.
    # (the second grid, buildings_production_method_item_potential, is shown nowhere: vanilla sets it visible = no)
    write('gui/production_methods.gui', gate_type_copies(patch_type_row_buttons(patch_type_grids(
        vanilla_gui('production_methods.gui'), dispatch, 'production_methods.gui', 3,
        replace={0: lambda bk, gind, vis: type_bar(bk, recipe_tex[bk])(bk, gind, vis)}, also=also, skip=(1,)),
        dispatch)), bom=False)
    # Building browser rows: the labour icon with the recipe bar beside it in the production method
    # column (220 wide), and the government upgrade button left of nationalize.
    browser_bars = ''.join(
        f'\t\t\t\t# PMR: recipe bar for {bk}\n\t\t\t\twidget = {{\n'
        f'\t\t\t\t\tvisible = "[{is_type(bk)}]"\n\t\t\t\t\tposition = {{ 56 0 }}\n'
        f'\t\t\t\t\tsize = {{ 156 24 }}\n\t\t\t\t\tparentanchor = vcenter\n'
        + stacked_bar(short(bk), recipe_tex[bk], ('100%', '100%'), 18, '\t\t\t\t\t') + '\t\t\t\t}\n'
        for bk in dispatch)
    write('gui/building_browser_panel.gui', gate_type_copies(patch_browser_tabs(patch_browser_actions(patch_grid_instance(
        patch_type_grids(vanilla_gui('building_browser_panel.gui'), dispatch, 'building_browser_panel.gui', 1, also=also),
        dispatch, '\t\t\t', 'building_browser_panel.gui', outer=(214, 50), cell=50, anchor='vcenter',
        extra=browser_bars, also=also), dispatch), list(mv_keys))), bom=False)
    # The state's Buildings tab without the retool sites (Pat 2026-10-14 01:54Z).
    write('gui/states_panel_buildings.gui', hide_retool_sites(vanilla_gui('states_panel_buildings.gui'), site_types),
          bom=False)
    # The company panels without the retool sites that companies list (Pat 2026-10-19 02:32Z, company_panel.py); in the
    # test build company_culture.write_all writes company_panel.gui, with its Company Culture tab.
    write('gui/companies_panel.gui', company_panel.patch_companies_panel(vanilla_gui('companies_panel.gui')), bom=False)
    if args.release:
        write('gui/company_panel.gui', company_panel.patch_company_panel(vanilla_gui('company_panel.gui')), bom=False)
    report['gated_type_copies'] = list(GATED)
    write('gui/goods_state_panel.gui', patch_building_grids(vanilla_gui('goods_state_panel.gui'), dispatch,
                                                            'goods_state_panel.gui', 1, also), bom=False)
    loc += panel_loc(bar_keys) + option_loc(opt_ui) + automation_loc(auto_ui) + pick_loc(pick_ui) + methods_view_loc(mv_keys, pair_ui, ai_of, ai_parts, opt_ui, auto_ui)
    loc += [' bg_pmr_retool:0 "Retooling"', ' bg_pmr_retool_abroad:0 "Retooling Abroad"',
            ' bg_pmr_retool_gov:0 "Government Retooling"', ' bg_pmr_retool_gov_abroad:0 "Government Retooling Abroad"']
    if not args.release:    # the "PMR test:" decision is for testing only: every player would see it
        write('common/decisions/pmr_test_decisions.txt', header + DECISIONS)
        loc += DECISION_LOC
        for probe in sorted(os.listdir(TEST_PROBES)) if os.path.isdir(TEST_PROBES) else []:
            src = os.path.join(TEST_PROBES, probe)
            for dirpath, _dirs, files in os.walk(src):
                for fn in files:
                    rel = os.path.relpath(os.path.join(dirpath, fn), src)
                    dst = os.path.join(args.out, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(os.path.join(dirpath, fn), dst)
                    # A probe's English text goes to every language too, or a tester playing in another language
                    # sees its keys raw.
                    if rel.startswith(os.path.join('localization', 'english', '')) and fn.endswith('_l_english.yml'):
                        with open(os.path.join(dirpath, fn), encoding='utf-8-sig') as f:
                            body = f.read().split('\n', 1)[1]
                        for lang in OTHER_LANGUAGES:
                            write(f'localization/{lang}/{fn[:-len("english.yml")]}{lang}.yml', f'l_{lang}:\n' + body)
        # Its tab's Methods table: the Policies grid of the company's own building types (Pat 2026-10-19 02:32Z)
        loc += company_panel.write_methods(write, header, mv_keys, recipe_tex, pair_ui, pair_options, mv_read,
                                           mv_cols(mv_keys, pair_ui) if mv_keys else 1, cc_plan.works)
        # Company Culture (Pat, 2026-10-14 04:01Z): a trait tree tab on every company, in the test build until Pat ships it.
        loc += company_culture.write_all(game, write, header, report, cc_plan, args.out)
        private_investment.AI_TAIL = company_culture.ai_value_tail   # Expanded Works (company_culture.py)
        private_investment.GRANT_LINE = True                         # research grants in the pool's tooltip
    # The construction panel's Private tab (Pat, 2026-10-13). Runs last: it patches the building files and
    # pmr_retool_buildings.txt written above (company ai_value; the Re-invest card's retool multiplier).
    private_investment.PROFIT_TYPES = set(pick_ui)   # their ai_value follows their average profit (Pat 21:10Z)
    loc += private_investment.write_all(game, write, header, args.out)
    if args.trace_from:
        write('common/scripted_effects/pmr_trace_effects.txt', header + trace_pm_effects(game, args.out, args.trace_from))
    write('localization/english/pmr_l_english.yml', 'l_english:\n' + '\n'.join(loc) + '\n')
    # Every other language, translated (Pat 2026-10-18 14:37Z, #3). A game set to a language shows raw keys where it
    # has no text, so a line its table lacks stays English, test builds included.
    report['untranslated'] = {}
    for lang in OTHER_LANGUAGES:
        missing = collections.Counter()
        write(f'localization/{lang}/pmr_l_{lang}.yml',
              f'l_{lang}:\n' + '\n'.join(localise.translate(loc, lang, missing)) + '\n')
        report['untranslated'][lang] = sorted(missing)
    # Vanilla text PMR rewrites, the same in every language (private_investment.replace_loc)
    replace = private_investment.replace_loc()
    for lang in ('english',) + OTHER_LANGUAGES if replace else ():
        write(f'localization/{lang}/replace/pmr_replace_l_{lang}.yml', f'l_{lang}:\n' + '\n'.join(replace) + '\n')

    # A test build for its own mod folder (--test-name) carries its own name and id, so the launcher lists it
    # beside the published mod and a playset holds one or the other.
    title = 'Production Method Rework' + (f' ({args.test_name})' if args.test_name else '')
    mod_id = 'org.prob32.pmr' + ('.' + re.sub(r'[^a-z0-9]+', '_', args.test_name.lower()) if args.test_name else '')
    write('descriptor.mod', f'version="{MOD_VERSION}"\ntags={{\n\t"Gameplay"\n\t"Economy"\n}}\n'
          f'name="{title}"\nsupported_version="{SUPPORTED_VERSION}"\n', bom=False)
    write('.metadata/metadata.json', json.dumps({
        'name': title, 'id': mod_id, 'version': MOD_VERSION,
        'game_id': 'victoria3', 'supported_game_version': SUPPORTED_VERSION,
        'short_description': SHORT_DESCRIPTION,
        'tags': ['Gameplay', 'Economy'], 'relationships': [],
        'game_custom_data': {'multiplayer_synchronized': True}}, indent=2) + '\n', bom=False)
    report['settings'] = {'N': N, 'retool_share': RETOOL_SHARE, 'gov_fraction_step': GOV_FRACTION_STEP,
                          'game': args.version_label}
    shutil.copyfile(THUMBNAIL, os.path.join(args.out, '.metadata', 'thumbnail.png'))
    shutil.copyfile(THUMBNAIL, os.path.join(args.out, 'thumbnail.png'))
    if not args.release:
        write('GENERATION_REPORT.json', json.dumps(report, indent=1) + '\n', bom=False)
    print(f"treated {len(report['treated'])} buildings, skipped {len(report['skipped'])}, "
          f"{len(report['blended'])} recipes blended by share ({len(blend_pms)} methods), "
          f"{len(report['company_types'])} company types may own retooling")
    lacking = {lang: len(v) for lang, v in report['untranslated'].items() if v}
    print('every language translated' if not lacking else
          'lines left in English: ' + ', '.join(f'{lang} {n}' for lang, n in lacking.items()))


# ---------------------------------------------------------------------------------------------
# Script templates
#
# Buildings cannot hold variables (1.14.5 error.log: "This scope doesn't support variables. Scope:
# Building"). Everything PMR remembers about a building lives on its state instead, under the
# building type's short name: a state has at most one building of each type, so pmr_p_steel_mill on
# a state is that state's steel mill's p. The tick runs in state scope and reaches the building with
# b:<building_type> only to read its level and ownership and to activate its methods.

def log(rec, bk, b, k, extra=''):
    def v(name, f):
        return f"[THIS.Var('{name}_{b}').GetValue|{f}]"
    levels = '/'.join(v(f'pmr_lv_{i}', 0) for i in range(1, k + 1))
    # Player-owned states only: debug.log rotates at about 2.5 MB and the world's lines overflow it.
    return (f'if = {{ limit = {{ OR = {{ owner = {{ is_player = yes }} has_variable = pmr_abroad_{b} }} }} '
            f'debug_log = "PMR;rec={rec};date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={bk};'
            f"to={v('pmr_to', 0)};level={v('pmr_level', 0)};levels={levels};"
            f"p={v('pmr_p', 3)};to_retool={v('pmr_need', 0)}{extra}\" }}")


# What the release build's stripped log lines leave behind: an if or else_if with nothing but its limit, an else
# with nothing at all. They do nothing but still run their checks, several in every building's monthly tick. An if
# followed by an else or else_if is kept, as removing it would change the chain.
EMPTY_IF = re.compile(r'(?:(?<![\w])|\belse_)if = \{ limit = \{ (?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})* \}[ \t]*\}'
                      r'(?![ \t\n]*else)')
EMPTY_ELSE = re.compile(r'\n[ \t]*else = \{[ \t]*\}(?=[ \t]*\n)|(?<=\}) else = \{[ \t]*\}')


def drop_empty(text):
    while True:
        new = EMPTY_ELSE.sub('', EMPTY_IF.sub('', text))
        if new == text:
            return text
        text = new


def flush_log(rec, bk, extra=''):
    """State scope, every country: a line long enough to push itself and everything before it to disk."""
    return (f'debug_log = "PMR;rec={rec};date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting];'
            f'building={bk}{extra};pad={"." * FLUSH_PAD}"')


# --trace-from DATE (a diagnostic build, never a release; 2026-10-13: Pat's game froze on 16 August 1838
# twice from the same save). From DATE on, every PMR on_action and event writes a flushed T line as it
# starts and ends, and so does every effect they call; every building type's tick, automatic method,
# building removal and government retool construction writes one as it starts. The last T line before
# a hang names what was running; an :out line last means PMR had finished and the engine hung.
TRACE_FIELDS = {
    'building': ('building=[THIS.GetBuilding.GetNameNoFormatting];state=[THIS.GetBuilding.GetState.GetNameNoFormatting];'
                 'country=[THIS.GetBuilding.GetState.GetOwner.GetNameNoFormatting]'),
    'country': 'country=[THIS.GetCountry.GetNameNoFormatting]',
    'state': 'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting]',
}
# on_action or event -> its root's scope
TRACE_ROOTS = {
    'pmr_on_production_method_changed': 'building', 'pmr_on_building_built': 'building',
    'pmr_on_building_expanded': 'building', 'pmr_pi_on_start': 'building',
    'pmr_on_acquired_technology': 'country', 'pmr_on_monthly_pulse_country': 'country',
    'pmr_pi_monthly_country': 'country', 'pmr.1': 'country', 'pmr_pi.1': 'country',
    'pmr_on_monthly_pulse_state': 'state',
}
# effects those call -> the scope they run in. A building may be gone after pmr_tick_parent_of_retool
# (it can remove its own root), so :out lines read nothing from scope.
TRACE_CALLS = {
    'pmr_tick_building': 'building', 'pmr_auto_building': 'building', 'pmr_pi_on_done': 'building',
    'pmr_built_building': 'building', 'pmr_tick_parent_of_retool': 'building', 'pmr_pi_start': 'building',
    'pmr_state_tick': 'state', 'pmr_state_research': 'state', 'pmr_auto_best': 'state',
    'pmr_probe_state': 'state', 'pmr_state_research_abroad': 'state',
    'pmr_c_sum_all': 'country', 'pmr_c_sum_every': 'country', 'pmr_policy_upkeep': 'country',
    'pmr_pi_start_clock': 'country', 'pmr_pc_record': 'country', 'pmr_rw_record': 'country',
}


def trace_line(since, at, fields=''):
    # pmr_trace_flush's long line pushes this one to disk (see FLUSH_PAD) without a pad in every line
    return (f'if = {{ limit = {{ game_date >= {since} }} debug_log = "PMR;rec=T;at={at};'
            f'date=[TimeKeeper.GetCurrentDate.GetString]{";" + fields if fields else ""}" pmr_trace_flush = yes }}')


def block_end(text, i):
    """Index of the brace closing the block that opens at text[i] == '{' (skips strings and comments)."""
    depth, j, in_str = 0, i, False
    while j < len(text):
        c = text[j]
        if in_str:
            in_str = c != '"'
        elif c == '#':
            j = text.find('\n', j)
            if j < 0:
                break
        elif c == '"':
            in_str = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise SystemExit(f'--trace-from: unbalanced block at {i}')


L0_TRIP = 20


def trace_pm_effects(game, out, since):
    """--trace-from: pmr_trace_pms (building scope) logs a building's active methods, one PM line each;
    pmr_l0_guard (building scope, below level 1) opens every share lock (key and xk groups to _any) on
    the L0_TRIP-th method change in a day and writes a flushed L0_TRIP line. 16 August 1838: the engine
    switched an unbuilt Hanoverian rye farm's methods without end while PMR's own handler did nothing."""
    groups = {}
    for d in (os.path.join(game, 'common', 'production_method_groups'),
              os.path.join(out, 'common', 'production_method_groups')):
        for path in sorted(glob.glob(os.path.join(d, '*.txt'))):
            for n in pdx.parse(pdx.strip_bom(open(path, encoding='utf-8-sig').read())):
                if n.key and n.is_block and pdx.get(n.value, 'production_methods') is not None:
                    groups[n.key] = pdx.items(pdx.get(n.value, 'production_methods'))
    types = {}
    for path in sorted(glob.glob(os.path.join(out, 'common', 'buildings', '*.txt'))):
        for n in pdx.parse(pdx.strip_bom(open(path, encoding='utf-8-sig').read())):
            g = n.key and n.is_block and pdx.get(n.value, 'production_method_groups')
            if g and any(x.startswith('pmg_pmr_') for x in pdx.items(g)):
                types[n.key] = pdx.items(g)
    logs, guards = [], []
    for i, (bk, gs) in enumerate(sorted(types.items())):
        kw = 'if' if i == 0 else 'else_if'
        logs.append(f'\t{kw} = {{\n\t\tlimit = {{ is_building_type = {bk} }}\n'
                    + ''.join(f'\t\tif = {{ limit = {{ has_active_production_method = {p} }} '
                              f'debug_log = "PMR;rec=PM;group={g};pm={p}" }}\n' for g in gs for p in groups[g])
                    + '\t}\n')
        b = short(bk)
        locks = [p for g in gs if g.startswith(('pmg_pmr_key_', 'pmg_pmr_xk_')) for p in groups[g] if p.endswith('_any')]
        guards.append(f'\t{kw} = {{\n\t\tlimit = {{ is_building_type = {bk} }}\n\t\tstate = {{\n'
                      f'\t\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_l0_day_{b} }} }} '
                      f'set_variable = {{ name = pmr_l0_day_{b} value = yes days = 1 }} set_variable = {{ name = pmr_l0_runs_{b} value = 0 }} }}\n'
                      f'\t\t\tchange_variable = {{ name = pmr_l0_runs_{b} add = 1 }}\n'
                      f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:pmr_l0_runs_{b} = {L0_TRIP} }}\n'
                      f'\t\t\t\t{flush_log("L0_TRIP", bk)}\n\t\t\t\tset_variable = pmr_l0_busy\n'
                      + ''.join(f'\t\t\t\tif = {{ limit = {{ NOT = {{ is_production_method_active = {{ building_type = {bk} production_method = {p} }} }} }} '
                                f'activate_production_method = {{ building_type = {bk} production_method = {p} }} }}\n' for p in locks)
                      + '\t\t\t\tremove_variable = pmr_l0_busy\n\t\t\t}\n\t\t}\n\t}\n')
    return ('# --trace-from only (see trace_pm_effects in tools/pmr/generate.py).\n\n'
            'pmr_trace_pms = {\n' + ''.join(logs) + '}\n\n'
            'pmr_l0_guard = {\n\tif = {\n\t\tlimit = { state = { NOT = { has_variable = pmr_l0_busy } } }\n'
            + ''.join('\t' + line + '\n' for line in ''.join(guards).rstrip('\n').split('\n')) + '\t}\n}\n')


def add_trace(rel, text, since):
    """The --trace-from lines for one generated file (see TRACE_FIELDS)."""
    if rel.startswith(('common/on_actions/', 'events/')):
        calls = re.compile(r'(?<![\w:.])(' + '|'.join(TRACE_CALLS) + r') = yes')
        text = calls.sub(lambda m: (trace_line(since, m.group(1) + ':in', TRACE_FIELDS[TRACE_CALLS[m.group(1)]])
                                    + f' {m.group(1)} = yes ' + trace_line(since, m.group(1) + ':out')), text)
        for name, scope in TRACE_ROOTS.items():
            m = re.search(r'^' + re.escape(name) + r' = \{', text, re.M)
            if not m:
                continue
            body = re.compile(r'^\t(effect|immediate) = \{', re.M).search(text, m.end(), block_end(text, m.end() - 1))
            if not body:
                raise SystemExit(f'--trace-from: {name} has no effect or immediate block')
            close = block_end(text, body.end() - 1)
            close = text.rfind('\n', 0, close) + 1
            extra = ''
            if name == 'pmr_on_production_method_changed':   # an unbuilt building: its methods, and the guard
                extra = (f'\n\t\tif = {{ limit = {{ level < 1 }} if = {{ limit = {{ game_date >= {since} }} pmr_trace_pms = yes }} '
                         'pmr_l0_guard = yes }')
            text = (text[:body.end()] + '\n\t\t' + trace_line(since, name + ':in', TRACE_FIELDS[scope]) + extra
                    + text[body.end():close] + '\t\t' + trace_line(since, name + ':out') + '\n' + text[close:])
    elif rel.startswith('common/scripted_effects/'):
        state = TRACE_FIELDS['state']
        ticks = [n for n in re.findall(r'^(pmr_(?:tick|auto)_\w+) = \{', text, re.M)
                 if n not in TRACE_CALLS and not n.startswith(('pmr_tick_body_', 'pmr_auto_best'))]
        if ticks:
            text = re.sub(r'(?<![\w:.])(' + '|'.join(ticks) + r') = yes',
                          lambda m: trace_line(since, m.group(1), state) + f' {m.group(1)} = yes', text)
        text = re.sub(r'(?<![\w:.])(remove_building|start_building_construction) = (\w+)',
                      lambda m: trace_line(since, f'{m.group(1)}:{m.group(2)}', state) + f' {m.group(0)}', text)
        if rel.endswith('/pmr_effects.txt'):    # defined before its first use
            text = (f'pmr_trace_flush = {{\n\tdebug_log = "PMR;rec=PAD;pad={"." * FLUSH_PAD}"\n}}\n\n'
                    + text.lstrip('\ufeff'))
    return text


# ---------------------------------------------------------------------------------------------
# Second groups: option shares (trade-offs by local price, plantation treatment by acceptance)

PRICE_LADDER = list(range(-75, 76, PRICE_STEP))   # % off the base price; the game clamps prices to +-75%


def price_effect(good):
    """State scope: pmr_px_<good>, the local price as a multiple of the base price, to PRICE_STEP %.
    The game only compares prices (state_goods_pricier / _cheaper, in fractions: the PRICE probe read
    hardwood at +20% through them and nothing through percent), so this bisects to the step nearest the
    price in about five comparisons."""
    half = PRICE_STEP / 200

    def above(k):   # the price is at least k % off base, give or take half a step
        if k > 0:
            return f'sg:{good} = {{ state_goods_pricier > {fmt(k / 100 - half)} }}'
        return f'NOT = {{ sg:{good} = {{ state_goods_cheaper > {fmt(-k / 100 + half)} }} }}'

    def find(lo, hi, ind):   # above(PRICE_LADDER[lo]) holds
        if lo == hi:
            return f'{ind}set_variable = {{ name = pmr_px_{good} value = {fmt(1 + PRICE_LADDER[lo] / 100)} }}\n'
        mid = (lo + hi + 1) // 2
        return (f'{ind}if = {{ limit = {{ {above(PRICE_LADDER[mid])} }}\n' + find(mid, hi, ind + '\t')
                + f'{ind}}}\n{ind}else = {{\n' + find(lo, mid - 1, ind + '\t') + f'{ind}}}\n')
    return (f'pmr_price_{good} = {{\n\tif = {{\n\t\tlimit = {{ exists = sg:{good} }}\n'
            + find(0, len(PRICE_LADDER) - 1, '\t\t')
            + f'\t}}\n\telse = {{ set_variable = {{ name = pmr_px_{good} value = 1 }} }}\n}}\n\n')


def option_goods(options):
    return sorted({g for conv in options.values() for _, _, mode, _, opts, _ in conv if mode == 'market'
                   for o in opts for g in o.goods})


def option_effects(bk, b, conv, goods_cost, recipes):
    """State scope, for one building type with converted second groups: pmr_opts_<b>, run by every
    tick after the recipe blend. Sets each option's share (pmr_x_<j>_<b>, 0..SHARE_STEPS) at first
    sight and once a month (pmr_month, set by the monthly pulse), then makes the share methods match."""
    if not conv:
        return ''
    opts = [o for _, _, _, _, os_, _ in conv for o in os_]
    bv = lambda name: f'{name}_{b}'               # noqa: E731
    xv = lambda name, j: f'{name}_{j}_{b}'        # noqa: E731
    act = lambda pm: f'activate_production_method = {{ building_type = {bk} production_method = {pm} }}'   # noqa: E731
    is_on = lambda pm: f'is_production_method_active = {{ building_type = {bk} production_method = {pm} }}'   # noqa: E731
    can = lambda pm: f'OR = {{ {is_on(pm)} can_activate_production_method = {{ building_type = {bk} production_method = {pm} }} }}'   # noqa: E731
    r0 = recipes[0]
    band = TRADE_DEAD_BAND * sum(v * goods_cost.get(g, 0) for g, v in r0.outputs.items())
    o = []

    # Each option's availability: its vanilla marker could run here (technology, laws, recipe), and
    # electricity in the state if it uses any.
    o.append(f'pmr_xavail_{b} = {{\n')
    for x in opts:
        cond = can(x.key) + (' var:pmr_elec = 1' if x.elec else '')
        o.append(f'\tset_variable = {{ name = {xv("pmr_xav", x.j)} value = 0 }}\n'
                 f'\tif = {{ limit = {{ {cond} }} set_variable = {{ name = {xv("pmr_xav", x.j)} value = 1 }} }}\n')
    for g, gi, mode, none, os_, std in conv:
        if mode == 'treat':
            o.append(f'\tset_variable = {{ name = {xv("pmr_xas", gi)} value = 0 }}\n'
                     f'\tif = {{ limit = {{ {can(none)} }} set_variable = {{ name = {xv("pmr_xas", gi)} value = 1 }} }}\n')
    o.append('}\n\n')

    # Market options: value per level at local prices; an option that can't run sheds its share first.
    market = [x for x in opts if x.mode == 'market']
    if market:
        goods = sorted({g for x in market for g in x.goods})
        # A good's price is read once a day per state (pmr_pxd_<good>), not once per building type that
        # values it: grain, sugar and fruit each feed five or six farm types.
        o.append(f'pmr_xvalue_{b} = {{\n' + ''.join(
            f'\tif = {{ limit = {{ NOT = {{ has_variable = pmr_pxd_{g} }} }} pmr_price_{g} = yes '
            f'set_variable = {{ name = pmr_pxd_{g} value = yes days = 1 }} }}\n' for g in goods))
        for x in market:
            o.append(f'\tset_variable = {{ name = {xv("pmr_xv", x.j)} value = 0 }}\n')
            for g, amt in x.goods.items():
                if amt and goods_cost.get(g):
                    o.append(f'\tset_variable = {{ name = pmr_t value = var:pmr_px_{g} }}\n'
                             f'\tchange_variable = {{ name = pmr_t multiply = {fmt(amt * goods_cost[g])} }}\n'
                             f'\tchange_variable = {{ name = {xv("pmr_xv", x.j)} add = var:pmr_t }}\n')
            # the panel shows the value whether or not the option can run (pmr_xw_<j>_<b>)
            o.append(f'\tset_variable = {{ name = {xv("pmr_xw", x.j)} value = var:{xv("pmr_xv", x.j)} }}\n'
                     f'\tif = {{ limit = {{ var:{xv("pmr_xav", x.j)} = 0 }} '
                     f'set_variable = {{ name = {xv("pmr_xv", x.j)} value = -1000000 }} }}\n')
        o.append('}\n\n')

    def none_share(gi, os_):
        return (f'\tset_variable = {{ name = {xv("pmr_xn", gi)} value = {SHARE_STEPS} }}\n'
                + ''.join(f'\tchange_variable = {{ name = {xv("pmr_xn", gi)} subtract = var:{xv("pmr_x", x.j)} }}\n'
                          for x in os_))

    def best(os_, ind='\t'):
        """pmr_bi / pmr_bv: the best-paying option that can run, 0 (none, worth 0) if none beats it."""
        return (f'{ind}set_variable = {{ name = pmr_bv value = 0 }}\n{ind}set_variable = {{ name = pmr_bi value = 0 }}\n'
                + ''.join(f'{ind}if = {{ limit = {{ var:{xv("pmr_xav", x.j)} = 1 var:{xv("pmr_xv", x.j)} > var:pmr_bv }} '
                          f'set_variable = {{ name = pmr_bv value = var:{xv("pmr_xv", x.j)} }} '
                          f'set_variable = {{ name = pmr_bi value = {x.j} }} }}\n' for x in os_))

    def start_shares(os_):
        """Game start: TRADE_PRELOAD's shares, an option the state can't run passing its share down the
        list (pmr_t carries it), or without a preload for the type the option vanilla's history set."""
        pre = TRADE_PRELOAD.get(bk)
        if pre is None:
            return ''.join(f'\t\tif = {{ limit = {{ b:{bk} = {{ has_active_production_method = {x.key} }} }} '
                           f'set_variable = {{ name = {xv("pmr_x", x.j)} value = {SHARE_STEPS} }} }}\n' for x in os_)
        unknown = set(pre) - {x.key for x in opts}
        if unknown:
            raise SystemExit(f'TRADE_PRELOAD[{bk!r}] names {sorted(unknown)}, not options of the building')
        out = '\t\tset_variable = { name = pmr_t value = 0 }\n'
        for x in reversed(os_):
            if pre.get(x.key):
                out += f'\t\tchange_variable = {{ name = pmr_t add = {pre[x.key]} }}\n'
            out += (f'\t\tif = {{ limit = {{ var:{xv("pmr_xav", x.j)} = 1 }} set_variable = {{ name = {xv("pmr_x", x.j)} value = var:pmr_t }} '
                    'set_variable = { name = pmr_t value = 0 } }\n')
        return out

    # Monthly market step, group by group.
    for g, gi, mode, none, os_, std in conv:
        if mode != 'market':
            continue
        o.append(f'pmr_xstep_{gi}_{b} = {{\n' + none_share(gi, os_) + best(os_)
                 + '\t# the worst-paying option that holds a share (none, worth 0, included)\n'
                 '\tset_variable = { name = pmr_wi value = -1 }\n\tset_variable = { name = pmr_wv value = 0 }\n'
                 f'\tif = {{ limit = {{ var:{xv("pmr_xn", gi)} > 0 }} set_variable = {{ name = pmr_wi value = 0 }} }}\n'
                 + ''.join(f'\tif = {{ limit = {{ var:{xv("pmr_x", x.j)} > 0 OR = {{ var:pmr_wi < 0 var:{xv("pmr_xv", x.j)} < var:pmr_wv }} }} '
                           f'set_variable = {{ name = pmr_wv value = var:{xv("pmr_xv", x.j)} }} '
                           f'set_variable = {{ name = pmr_wi value = {x.j} }} }}\n' for x in os_)
                 + '\tif = {\n\t\tlimit = { var:pmr_wi >= 0 NOT = { var:pmr_wi = var:pmr_bi } }\n'
                 '\t\tset_variable = { name = pmr_gap value = var:pmr_bv }\n'
                 '\t\tchange_variable = { name = pmr_gap subtract = var:pmr_wv }\n'
                 f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_gap > {fmt(band)} }}\n'
                 # the gap in % of the output value per level, times TRADE_GAIN
                 '\t\t\tset_variable = { name = pmr_m value = var:pmr_gap }\n'
                 f'\t\t\tchange_variable = {{ name = pmr_m multiply = {fmt(TRADE_GAIN * 100 * TRADE_DEAD_BAND / band)} }}\n'
                 '\t\t\tround_variable = { name = pmr_m nearest = 1 }\n'
                 f'\t\t\tif = {{ limit = {{ var:pmr_m < {TRADE_STEP_MIN} }} set_variable = {{ name = pmr_m value = {TRADE_STEP_MIN} }} }}\n'
                 f'\t\t\tif = {{ limit = {{ var:pmr_m > {TRADE_STEP_MAX} }} set_variable = {{ name = pmr_m value = {TRADE_STEP_MAX} }} }}\n'
                 f'\t\t\tif = {{ limit = {{ var:pmr_wi = 0 var:{xv("pmr_xn", gi)} < var:pmr_m }} '
                 f'set_variable = {{ name = pmr_m value = var:{xv("pmr_xn", gi)} }} }}\n'
                 + ''.join(f'\t\t\tif = {{ limit = {{ var:pmr_wi = {x.j} var:{xv("pmr_x", x.j)} < var:pmr_m }} '
                           f'set_variable = {{ name = pmr_m value = var:{xv("pmr_x", x.j)} }} }}\n' for x in os_)
                 + ''.join(f'\t\t\tif = {{ limit = {{ var:pmr_wi = {x.j} }} '
                           f'change_variable = {{ name = {xv("pmr_x", x.j)} subtract = var:pmr_m }} }}\n' for x in os_)
                 + ''.join(f'\t\t\tif = {{ limit = {{ var:pmr_bi = {x.j} }} '
                           f'change_variable = {{ name = {xv("pmr_x", x.j)} add = var:pmr_m }} }}\n' for x in os_)
                 + '\t\t}\n\t}\n}\n\n')
        # First sight: the option the vanilla marker runs (game start), or for a building built
        # during the game the best-paying one, if it beats none by the dead band.
        o.append(f'pmr_xinit_{gi}_{b} = {{\n'
                 + ''.join(f'\tset_variable = {{ name = {xv("pmr_x", x.j)} value = 0 }}\n' for x in os_)
                 + f'\tif = {{\n\t\tlimit = {{ has_variable = {bv("pmr_xnew")} }}\n'
                 + best(os_, '\t\t')
                 + f'\t\tif = {{ limit = {{ var:pmr_bv <= {fmt(band)} }} set_variable = {{ name = pmr_bi value = 0 }} }}\n'
                 + ''.join(f'\t\tif = {{ limit = {{ var:pmr_bi = {x.j} }} set_variable = {{ name = {xv("pmr_x", x.j)} value = {SHARE_STEPS} }} }}\n'
                           for x in os_)
                 + '\t}\n\telse = {\n' + start_shares(os_) + '\t}\n}\n\n')

    # Treatment, group by group: the workforce's acceptance, then the laws.
    for g, gi, mode, none, os_, std in conv:
        if mode != 'treat':
            continue
        viol = next((x for x in os_ if x.role == 'violent'), None)
        harsh = next((x for x in os_ if x.role == 'harsh'), None)
        lo, hi = TREAT_BANDS
        t = [f'pmr_xtreat_{gi}_{b} = {{\n'
             f'\t# workforce under acceptance {lo} (violent), {lo} to {hi - 1} (harsh), in % of all of it\n'
             f'\tset_variable = {{ name = pmr_tw value = pmr_tr_w_{b} }}\n'
             '\tset_variable = { name = pmr_tv value = 0 }\n\tset_variable = { name = pmr_th value = 0 }\n'
             '\tif = {\n\t\tlimit = { var:pmr_tw > 0 }\n'
             f'\t\tset_variable = {{ name = pmr_tv value = pmr_tr_wv_{b} }}\n'
             f'\t\tchange_variable = {{ name = pmr_tv multiply = {SHARE_STEPS} }}\n'
             '\t\tchange_variable = { name = pmr_tv divide = var:pmr_tw }\n'
             '\t\tround_variable = { name = pmr_tv nearest = 1 }\n'
             f'\t\tset_variable = {{ name = pmr_th value = pmr_tr_wh_{b} }}\n'
             f'\t\tchange_variable = {{ name = pmr_th multiply = {SHARE_STEPS} }}\n'
             '\t\tchange_variable = { name = pmr_th divide = var:pmr_tw }\n'
             '\t\tround_variable = { name = pmr_th nearest = 1 }\n\t}\n'
             '\tset_variable = { name = pmr_bandv value = var:pmr_tv }\n\tset_variable = { name = pmr_bandh value = var:pmr_th }\n'
             f'\tset_variable = {{ name = {xv("pmr_xbv", gi)} value = var:pmr_tv }}\n'
             f'\tset_variable = {{ name = {xv("pmr_xbh", gi)} value = var:pmr_th }}\n'
             '\t# The law wins: a barred treatment\'s share goes to the nearest one allowed.\n']
        if viol:
            t.append(f'\tif = {{ limit = {{ var:{xv("pmr_xav", viol.j)} = 0 }} '
                     'change_variable = { name = pmr_th add = var:pmr_tv } set_variable = { name = pmr_tv value = 0 } }\n')
        else:
            t.append('\t# no violent treatment here: that band is treated harshly\n'
                     '\tchange_variable = { name = pmr_th add = var:pmr_tv }\n\tset_variable = { name = pmr_tv value = 0 }\n')
        if harsh:
            t.append(f'\tif = {{\n\t\tlimit = {{ var:{xv("pmr_xav", harsh.j)} = 0 }}\n'
                     + (f'\t\tif = {{ limit = {{ var:{xv("pmr_xas", gi)} = 0 var:{xv("pmr_xav", viol.j)} = 1 }} '
                        'change_variable = { name = pmr_tv add = var:pmr_th } }\n' if viol else '')
                     + '\t\tset_variable = { name = pmr_th value = 0 }\n\t}\n')
        else:
            t.append('\tset_variable = { name = pmr_th value = 0 }\n')
        t.append(f'\tif = {{\n\t\tlimit = {{ var:{xv("pmr_xas", gi)} = 0 }}\n'
                 f'\t\tset_variable = {{ name = pmr_t value = {SHARE_STEPS} }}\n'
                 '\t\tchange_variable = { name = pmr_t subtract = var:pmr_tv }\n'
                 '\t\tchange_variable = { name = pmr_t subtract = var:pmr_th }\n'
                 + (f'\t\tif = {{ limit = {{ var:{xv("pmr_xav", harsh.j)} = 1 }} change_variable = {{ name = pmr_th add = var:pmr_t }} }}\n'
                    if harsh else '')
                 + (f'\t\t{"else_if" if harsh else "if"} = {{ limit = {{ var:{xv("pmr_xav", viol.j)} = 1 }} '
                    'change_variable = { name = pmr_tv add = var:pmr_t } }\n' if viol else '')
                 + '\t}\n'
                 f'\tif = {{ limit = {{ var:pmr_tv > {SHARE_STEPS} }} set_variable = {{ name = pmr_tv value = {SHARE_STEPS} }} }}\n'
                 f'\tset_variable = {{ name = pmr_t value = {SHARE_STEPS} }}\n'
                 '\tchange_variable = { name = pmr_t subtract = var:pmr_tv }\n'
                 '\tif = { limit = { var:pmr_th > var:pmr_t } set_variable = { name = pmr_th value = var:pmr_t } }\n'
                 + (f'\tset_variable = {{ name = {xv("pmr_x", viol.j)} value = var:pmr_tv }}\n' if viol else '')
                 + (f'\tset_variable = {{ name = {xv("pmr_x", harsh.j)} value = var:pmr_th }}\n' if harsh else '')
                 + '}\n\n')
        o.append(''.join(t))

    # Making the share methods match, as pmr_blend_<b> does for recipes: only a share that is not
    # running is activated, through the switching lock, then locked again.
    def bisect(var, leaf, ind, lo=0, hi=SHARE_STEPS):
        if lo == hi:
            return f'{ind}{leaf(lo)}\n'
        mid = (lo + hi) // 2
        return (f'{ind}if = {{ limit = {{ var:{var} <= {mid} }}\n' + bisect(var, leaf, ind, lo, mid)
                + f'{ind}}}\n{ind}else = {{\n' + bisect(var, leaf, ind, mid + 1, hi) + f'{ind}}}\n')
    for x in opts:
        o.append(f'pmr_xlock_{x.j}_{b} = {{\n'
                 + bisect(xv('pmr_x', x.j), lambda n, x=x: act(f'pm_pmr_xk_{b}_{x.j}_{n}'), '\t') + '}\n\n')
    o.append(f'pmr_xapply_{b} = {{\n')
    for x in opts:
        anyk = f'pm_pmr_xk_{b}_{x.j}_any'
        o.append(f'\tset_variable = {{ name = {xv("pmr_xa", x.j)} value = -1 }}\n'
                 + bisect(xv('pmr_x', x.j), lambda n, x=x: f'if = {{ limit = {{ {is_on(f"pm_pmr_x_{b}_{x.j}_{n}")} }} '
                          f'set_variable = {{ name = {xv("pmr_xa", x.j)} value = {n} }} }}', '\t')
                 + f'\tif = {{\n\t\tlimit = {{ var:{xv("pmr_xa", x.j)} = -1 }}\n'
                 f'\t\tif = {{ limit = {{ NOT = {{ {is_on(anyk)} }} }} {act(anyk)} }}\n'
                 + bisect(xv('pmr_x', x.j), lambda n, x=x: act(f'pm_pmr_x_{b}_{x.j}_{n}'), '\t\t')
                 + f'\t\tpmr_xlock_{x.j}_{b} = yes\n'
                 f'\t\tset_variable = {{ name = {xv("pmr_xa", x.j)} value = var:{xv("pmr_x", x.j)} }}\n\t}}\n'
                 f'\telse_if = {{ limit = {{ {is_on(anyk)} }} pmr_xlock_{x.j}_{b} = yes }}\n')
    o.append('}\n\n')

    # The entry point, and what the panel's trade-off bars read: each group's none share.
    o.append(f'pmr_opts_{b} = {{\n\tpmr_xavail_{b} = yes\n'
             + (f'\tif = {{ limit = {{ OR = {{ NOT = {{ has_variable = {bv("pmr_xinit")} }} has_variable = pmr_month }} }} pmr_xvalue_{b} = yes }}\n'
                if market else '')
             + f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {bv("pmr_xinit")} }} }}\n'
             f'\t\tset_variable = {bv("pmr_xinit")}\n'
             + ''.join(f'\t\tpmr_xinit_{gi}_{b} = yes\n' if mode == 'market' else f'\t\tpmr_xtreat_{gi}_{b} = yes\n'
                       for g, gi, mode, *_ in conv)
             + '\t}\n\telse_if = {\n\t\tlimit = { has_variable = pmr_month }\n'
             + ''.join(f'\t\tpmr_xstep_{gi}_{b} = yes\n' if mode == 'market' else f'\t\tpmr_xtreat_{gi}_{b} = yes\n'
                       for g, gi, mode, *_ in conv)
             + f'\t}}\n\tif = {{ limit = {{ has_variable = {bv("pmr_xnew")} }} remove_variable = {bv("pmr_xnew")} }}\n'
             f'\tpmr_xapply_{b} = yes\n')
    for g, gi, mode, none, os_, std in conv:
        o.append(none_share(gi, os_))
    f = lambda name, d=0: f"[THIS.Var('{name}').GetValue|{d}]"   # noqa: E731
    line = (f'PMR;rec=OPT;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={bk}'
            + ';x=' + '/'.join(f(xv('pmr_x', x.j)) for x in opts)
            + ';running=' + '/'.join(f(xv('pmr_xa', x.j)) for x in opts)
            + ';can=' + '/'.join(f(xv('pmr_xav', x.j)) for x in opts))
    if market:
        goods = sorted({g for x in market for g in x.goods})
        line += (';value=' + '/'.join(f(xv('pmr_xv', x.j)) for x in market)
                 + ';px=' + ','.join(f'{g}:{f("pmr_px_" + g, 2)}' for g in goods))
    if any(m == 'treat' for _, _, m, *_ in conv):
        # the workforce and its violent / harsh bands in % this month, before the laws
        line += (f";w={f('pmr_tw')};band_v={f('pmr_bandv')};band_h={f('pmr_bandh')};std_ok="
                 + '/'.join(f(xv('pmr_xas', gi)) for _, gi, m, *_ in conv if m == 'treat'))
    o.append(f'\tif = {{ limit = {{ has_variable = pmr_month owner = {{ is_player = yes }} }} debug_log = "{line}" }}\n}}\n\n')
    return ''.join(o)


# ---------------------------------------------------------------------------------------------
# Retooling construction. Per building type, RETOOL_SLOTS private pseudo-buildings,
# building_pmr_retool_<b>_<n>, built only by private investors for the privately owned share of the
# levels being retooled, and one government one, building_pmr_retool_gov_<b>, for its share. Nothing
# queues them: the investment pool and the government choose. 1.14.5's investment pool never queued a
# second level on a retool building that had one, inferred to be its employment rule (RETOOL_CREW),
# so a private retool building has a fixed crew that keeps it fully employed. Each empty one takes one
# level as a new construction; the rest of the private room goes to the first one with a finished
# level, which investors may then expand. One whose crew is still short after RETOOL_CREW_GRACE_DAYS
# is removed once its levels are counted, so its next level is a new construction again. Every
# retool building is capped the way vanilla caps trade centers under the canton system (in both
# can_build_government and can_build_private): the level after queued constructions, plus the levels
# being added (scope:num_levels), may not pass the cap the tick stores on the state.

RETOOL_TRIGGERS_DOC = """# State scope. pmr_retool_room_gov_<b>: true while the government may add scope:num_levels more
# retool levels in the state, against pmr_cap_gov_<b>, recomputed by pmr_split_retool_<b> every tick.
# pmr_retool_room_gova_<b>: the same for the player's government abroad (pmr_abroad_<b>), on its own site.
# pmr_retool_room_priv_<b>_<n>: the same for private retool building n, against pmr_cap_priv<n>_<b>.
# pmr_retool_investor_<b>: true when scope:investor_country's investors own part of the building, so
# an investment agreement alone does not let a foreign pool retool it.
# pmr_retool_investor_abroad_<b>: the same for the abroad slot, where the host's own investors also pass.

"""


RETOOL_CREW_DOC = f"""# The crew of a private retool building: {RETOOL_CREW} {RETOOL_CREW_POP} per level, making {RETOOL_CREW_OUTPUT} {RETOOL_CREW_GOOD}
# per level at full staff so it can pay them. 1.14.5's AI adds levels to a building that exists only at
# PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD (0.8) employment or if it hired last week, and a building that
# earns nothing cannot afford to hire.

"""


def priv_slots(b):
    """The private retool building types of one building type."""
    return [f'building_pmr_retool_{b}_{j}' for j in range(1, RETOOL_SLOTS + 1)]


def retool_buildings(b, bk, icon):
    out = []
    sides = [('priv', 'bg_pmr_retool_abroad' if j == ABROAD_SLOT else 'bg_pmr_retool', rbx, j)
             for j, rbx in enumerate(priv_slots(b), 1)]
    sides.append(('gov', 'bg_pmr_retool_gov', f'building_pmr_retool_gov_{b}', 0))
    sides.append(('gova', 'bg_pmr_retool_gov_abroad', f'building_pmr_retool_gova_{b}', 0))
    for side, group, rb, j in sides:
        if side == 'priv':
            flag = f'pmr_retool_open_priv_{b}_{j}'
            ai_limit = f'has_variable = {flag}'
            who = ('\t# Private investors only, for the privately owned share. Every building vanilla lets private\n'
                   '\t# investors build says ownership_type = self.\n'
                   '\townership_type = self\n'
                   f'\tcan_build_government = {{ always = no }}\n'
                   '\t# This one open, room left under its cap, and only investors from a country whose investors\n'
                   '\t# own part of the building'
                   + (', or the host\'s, whose check the game makes first (pmr_retool_investor_abroad_<b>)'
                      if j == ABROAD_SLOT else
                      '; where the player owns levels abroad, also the host\'s (pmr_retool_investor_abroad_<b>)'
                      if not ABROAD_SLOT else '') + '.\n'
                   f'\tcan_build_private = {{\n\t\thas_variable = {flag}\n\t\tpmr_retool_room_priv_{b}_{j} = yes\n'
                   + (f'\t\tpmr_retool_investor{"_abroad" if j == ABROAD_SLOT else ""}_{b} = yes\n\t}}\n' if ABROAD_SLOT else
                      f'\t\ttrigger_if = {{\n\t\t\tlimit = {{ has_variable = pmr_abroad_{b} }}\n\t\t\tpmr_retool_investor_abroad_{b} = yes\n\t\t}}\n'
                      f'\t\ttrigger_else = {{ pmr_retool_investor_{b} = yes }}\n\t}}\n'))
            pmgs = 'pmg_pmr_retool_crew' if RETOOL_CREW else 'pmg_dummy'
        elif side == 'gov':
            flag = f'pmr_retool_open_gov_{b}'
            who = ('\t# The government only, for the government-owned share, where the player owns no levels abroad\n'
                   '\t# (there building_pmr_retool_gova_<b>, for the player\'s government only).\n'
                   f'\tcan_build_government = {{ pmr_retool_room_gov_{b} = yes }}\n'
                   '\tcan_build_private = { always = no }\n')
            pmgs = 'pmg_dummy'
            ai_limit = f'has_variable = {flag} NOT = {{ has_variable = pmr_abroad_{b} }}'
        else:
            flag = f'pmr_retool_open_gov_{b}'
            who = ('\t# The player\'s government only, for its own levels abroad (pmr_abroad_<b>): the upgrade button\n'
                   '\t# expands the site the tick keeps standing there (Building.QueueConstruction), never an AI.\n'
                   f'\tcan_build_government = {{ pmr_retool_room_gova_{b} = yes }}\n'
                   '\tcan_build_private = { always = no }\n')
            pmgs = 'pmg_dummy'
        out.append(
            f'{rb} = {{\n'
            f'\tbuilding_group = {group}\n'
            f'\ticon = "{icon}"\n'
            f'\tcity_type = none\n'
            f'\tdownsizeable = no\n'
            '\t# Retool levels come only from the funders below, never from auto-expansion.\n'
            '\tshould_auto_expand = { always = no }\n'
            f'\t# Open only while script is retooling a {bk} in this state'
            + (', where the player owns levels abroad' if j == ABROAD_SLOT else '') + '.\n'
            f'\tpotential = {{ has_variable = pmr_retool_gate_{b} }}\n'
            + who +
            ('\t# Only ever the player\'s click: no AI scores it.\n\tai_value = 0\n' if side == 'gova' else
             '\t# While there is room: what an expansion of the building would score from its earnings\n'
             f'\t# (pmr_ai_w_<b>, set by the tick), x {RETOOL_AI_MULT}, so investors (or an AI government) are likelier\n'
             '\t# to retool it than to expand it.\n'
             f'\tai_value = {{\n\t\tvalue = 0\n\t\tif = {{\n\t\t\tlimit = {{ {ai_limit} }}\n'
             f'\t\t\tvalue = {RETOOL_AI_BASE}\n'
             f'\t\t\tif = {{ limit = {{ has_variable = pmr_ai_w_{b} }} value = var:pmr_ai_w_{b} }}\n'
             f'\t\t\tmultiply = {RETOOL_AI_MULT}\n'
             '\t\t}\n\t}\n') +
            f'\trequired_construction = pmr_retool_cost_{b}\n'
            f'\tproduction_method_groups = {{\n\t\t{pmgs}\n\t}}\n'
            f'\tbackground = "{RETOOL_BACKGROUND}"\n}}\n')
    return '\n'.join(out)


def retool_triggers(b, bk):
    rbg = f'building_pmr_retool_gov_{b}'
    rbga = f'building_pmr_retool_gova_{b}'
    cap = f'pmr_cap_gov_{b}'
    out = [
        f'pmr_retool_room_gova_{b} = {{\n'
        f'\thas_variable = pmr_abroad_{b}\n'
        f'\thas_variable = {cap}\n'
        '\ttrigger_if = {\n'
        f'\t\tlimit = {{ exists = b:{rbga} }}\n'
        f'\t\tb:{rbga} = {{ level_after_queued_constructions <= pmr_room_value_gov_{b} }}\n'
        '\t}\n'
        f'\ttrigger_else = {{ var:{cap} >= scope:num_levels }}\n'
        '}\n',
        f'pmr_retool_room_gov_{b} = {{\n'
        f'\tNOT = {{ has_variable = pmr_abroad_{b} }}\n'
        f'\thas_variable = {cap}\n'
        '\t# b: finds the retool building even while all of it is still queued (seen in 1.14.5).\n'
        '\ttrigger_if = {\n'
        f'\t\tlimit = {{ exists = b:{rbg} }}\n'
        f'\t\tb:{rbg} = {{ level_after_queued_constructions <= pmr_room_value_gov_{b} }}\n'
        '\t}\n'
        f'\ttrigger_else = {{ var:{cap} >= scope:num_levels }}\n'
        '}\n']
    # A private retool building takes levels up to the cap the tick gives it (pmr_cap_priv<j>_<b>).
    for j, rbx in enumerate(priv_slots(b), 1):
        cap = f'pmr_cap_priv{j}_{b}'
        out.append(f'pmr_retool_room_priv_{b}_{j} = {{\n'
                   f'\thas_variable = {cap}\n'
                   '\ttrigger_if = {\n'
                   f'\t\tlimit = {{ exists = b:{rbx} }}\n'
                   f'\t\tb:{rbx} = {{ level_after_queued_constructions <= pmr_room_value_priv_{b}_{j} }}\n'
                   '\t}\n'
                   f'\ttrigger_else = {{ var:{cap} >= scope:num_levels }}\n'
                   '}\n')
    # levels_owned_by_country counts "a country or investors in that country" (triggers.log), so for
    # the state's own country it includes the government's levels: its investors need more than those.
    # Vanilla compares the same trigger against c:RUS for the Manchurian railway.
    out.append(
        f'pmr_retool_investor_{b} = {{\n'
        '\texists = scope:investor_country\n'
        f'\texists = b:{bk}\n'
        '\ttrigger_if = {\n'
        '\t\tlimit = { owner = scope:investor_country }\n'
        f'\t\thas_variable = pmr_gov_levels_{b}\n'
        f'\t\tb:{bk} = {{ levels_owned_by_country = {{ target = scope:investor_country value > state.var:pmr_gov_levels_{b} }} }}\n'
        '\t}\n'
        f'\ttrigger_else = {{\n\t\tb:{bk} = {{ levels_owned_by_country = {{ target = scope:investor_country value >= 1 }} }}\n\t}}\n'
        '}\n')
    # The abroad slot (ABROAD_SLOT): any investors who own part of the building, and the host's own whatever they
    # own. The investment AI picks a building type's one candidate state by testing can_build_private with the
    # state's owner as scope:investor_country, and only then tests the investor itself (inferred from Pat's
    # autosaves of 1 July 1839 and 1 January 1841: Britain's abroad slots were picked in exactly the states where
    # the host's own investors owned levels, e.g. the Mysore coffee plantation and Quebec shipyard, and never in
    # West Bengal, whose coal and iron mines Britain owns whole). So the host must pass for the player's investors
    # to be offered the state at all; its own investors may then retool there too.
    out.append(
        f'pmr_retool_investor_abroad_{b} = {{\n'
        '\texists = scope:investor_country\n'
        f'\texists = b:{bk}\n'
        '\tOR = {\n'
        '\t\towner = scope:investor_country\n'
        f'\t\tb:{bk} = {{ levels_owned_by_country = {{ target = scope:investor_country value >= 1 }} }}\n'
        '\t}\n'
        '}\n')
    return '\n'.join(out)


SGUI_DOC = """# The government upgrade button on PMR buildings (details panel and building browser rows). State
# scope, one per building type, since a state has at most one building of each type. Valid while the
# government still has room to queue retool levels for that building (pmr_retool_open_gov_<b>, set by
# the tick). The GUI also requires the state to be the player's.

"""


def gov_retool_sgui(bk):
    b = short(bk)
    return (f'pmr_gov_retool_{b}_sgui = {{\n\tscope = state\n'
            f'\tis_shown = {{ exists = b:{bk} }}\n'
            f'\tis_valid = {{ has_variable = pmr_retool_open_gov_{b} NOT = {{ has_variable = pmr_abroad_{b} }} }}\n'
            f'\teffect = {{ pmr_queue_gov_{b} = yes }}\n}}\n\n'
            '# Abroad the button queues through the game (Building.QueueConstruction on the standing site), then this\n'
            '# ticks the building so the room, and with it the button, drops to what is left.\n'
            f'pmr_gov_retool_tick_{b}_sgui = {{\n\tscope = state\n'
            f'\tis_shown = {{ exists = b:{bk} }}\n'
            f'\tis_valid = {{ has_variable = pmr_abroad_{b} }}\n'
            f'\teffect = {{ pmr_tick_{b} = yes }}\n}}\n\n')


def gov_retool_country_sgui(bk):
    """The Buildings tab's upgrade button on a building type row: every state at once."""
    b = short(bk)
    return (f'pmr_gov_retool_c_{b}_sgui = {{\n\tscope = country\n'
            f'\tis_valid = {{ any_scope_state = {{ has_variable = pmr_retool_open_gov_{b} }} }}\n'
            f'\teffect = {{\n\t\tevery_scope_state = {{\n\t\t\tlimit = {{ has_variable = pmr_retool_open_gov_{b} }}\n'
            '\t\t\tset_variable = pmr_bulk\n'
            f'\t\t\tpmr_queue_gov_{b} = yes\n'
            '\t\t\tremove_variable = pmr_bulk\n\t\t}\n'
            f'\t\tpmr_c_sum_{b} = yes\n\t}}\n}}\n\n')


def retool_values(b):
    """Building scope: the most retool levels each retool building may have after queued
    constructions, before the scope:num_levels being added."""
    return (f'pmr_room_value_gov_{b} = {{\n\tvalue = state.var:pmr_cap_gov_{b}\n'
            '\tsubtract = scope:num_levels\n}\n'
            + ''.join(f'pmr_room_value_priv_{b}_{j} = {{\n\tvalue = state.var:pmr_cap_priv{j}_{b}\n'
                      '\tsubtract = scope:num_levels\n}\n' for j in range(1, RETOOL_SLOTS + 1)))



def highest(ns, cond, leaf, ind='\t'):
    """Bisection over a monotone ladder: leaf(x) for the largest x of ns (ascending) whose cond(x) holds,
    cond holding for every x below one that holds; leaf(None) if none does. About log2(len(ns)) checks
    where an if / else_if ladder from the top checks every rung when the answer is low (performance
    review, 2026-10-13: most buildings have no government share and low earnings)."""
    def find(lo, hi, ind):
        if lo > hi:
            return f'{ind}{leaf(ns[lo - 1] if lo > 0 else None)}\n'
        mid = (lo + hi) // 2
        return (f'{ind}if = {{ limit = {{ {cond(ns[mid])} }}\n' + find(mid + 1, hi, ind + '\t')
                + f'{ind}}}\n{ind}else = {{\n' + find(lo, mid - 1, ind + '\t') + f'{ind}}}\n')
    return find(0, len(ns) - 1, ind)


def tick_effect(bk, b, recipes, elec_tiers=(), opts=(), fold_techs=None, econ=(), goods_cost=None, auto_tiers=(),
                pair=None, works=()):
    """Every effect for one building type. All run in STATE scope.

    The state keeps how many of the building's levels run each recipe (pmr_lv_<i>_<b>, i = the
    recipe's position in vanilla's group, oldest first). The building's active recipe is the
    target (pmr_to_<b>); every level on another recipe still needs retooling. Each completed retool
    level moves one level, oldest recipe first, onto the target. A newer recipe arriving mid-retool
    only changes the target: levels already moved keep their recipe until retooled again.
    Each recipe's share of the levels picks the method active in that recipe's share group, so the
    building's goods are the level-weighted mix of its recipes in its own production figures."""
    k = len(recipes)
    fold_techs = fold_techs or {}
    slots = list(enumerate(priv_slots(b), 1))
    # The blend members, each with one share group (pmg_pmr_share_<b>_<j>): recipe i is member i, or with the split
    # (SPLIT_AUTOMATION) each plain recipe and each automation method, over the retool targets (pairs) using it.
    split = pair if pair and pair.get('split') else None
    bm = split['members'] if split else [(i, [i], 'recipe') for i in range(1, k + 1)]
    nb = len(bm)
    # Company Culture's works members (company_culture.works_members), after bm: their steps come from
    # pmr_works_<b> (pmr_wn_<j>_<b>), company_culture.works_steps of them, not from the levels' recipes.
    hi_of = {j: n for j, n in works}
    nb_all = nb + len(works)
    rec_of = {i: j for j, idxs, grp in bm if grp == 'recipe' for i in idxs}   # target -> its recipe member
    sv = 'pmr_rs' if split else 'pmr_sh'   # a member's share of the levels

    def slot_here(j):
        # the abroad slot only where the player owns levels abroad, the home slots everywhere else (ABROAD_SLOT);
        # without an abroad slot, every slot everywhere
        if not ABROAD_SLOT:
            return ''
        return (f'has_variable = pmr_abroad_{b}' if j == ABROAD_SLOT
                else f'NOT = {{ has_variable = pmr_abroad_{b} }}')
    rbg = f'building_pmr_retool_gov_{b}'
    rbga = f'building_pmr_retool_gova_{b}'   # the player's government's site abroad
    v = lambda name: f'{name}_{b}'           # noqa: E731  state variable for this building type
    lv = lambda i: v(f'pmr_lv_{i}')          # noqa: E731
    lvg = lambda i: v(f'pmr_lvg_{i}')        # noqa: E731  of those, the government's
    o = [f'# ===== {bk}: ' + ', '.join(f'{i} = {r.key}' for i, r in enumerate(recipes, 1)) + '\n'
         '# State scope throughout; the building is b:' + bk + '.\n\n']

    def active(r):
        return f'is_production_method_active = {{ building_type = {bk} production_method = {r.key} }}'

    def on_index(var, body, ind='\t'):
        """body(i) for the recipe whose index is held in var."""
        return ''.join(f'{ind}{"if" if i == 1 else "else_if"} = {{ limit = {{ var:{v(var)} = {i} }} {body(i)} }}\n'
                       for i in range(1, k + 1))

    def setv(name, value):
        return f'set_variable = {{ name = {v(name)} value = {value} }}'

    def chg(name, op, value):
        return f'change_variable = {{ name = {v(name)} {op} = {value} }}'

    # the recipe the building runs now, 0 if none of the group's is active
    o.append(f'pmr_running_{b} = {{\n\t{setv("pmr_run", 0)}\n')
    for i, r in enumerate(recipes, 1):
        o.append(f'\t{"if" if i == 1 else "else_if"} = {{ limit = {{ {active(r)} }} {setv("pmr_run", i)} }}\n')
    o.append('}\n\n')

    # all levels on one recipe (the one in pmr_to)
    o.append(f'pmr_reset_levels_{b} = {{\n'
             + ''.join(f'\tset_variable = {{ name = {lv(i)} value = 0 }}\n' for i in range(1, k + 1))
             + on_index('pmr_to', lambda i: f'set_variable = {{ name = {lv(i)} value = var:{v("pmr_level")} }}')
             + '\t# the government\'s levels are placed again by pmr_sync_gov_<b>\n'
             + ''.join(f'\tset_variable = {{ name = {lvg(i)} value = 0 }}\n' for i in range(1, k + 1))
             + '}\n\n')

    # The blend: each recipe's share of the levels, in steps of 1 / SHARE_STEPS, picks the active
    # method of that recipe's share group. Recipes other than the target are rounded to the nearest
    # step, oldest first and never past the whole; the target takes what is left, so the shares
    # always add up to exactly SHARE_STEPS steps. A share method unlocks while its own lock or the
    # switching lock _any is active. To change share, the lock moves to _any (the running share stays
    # unlocked), then the share moves (the new one is unlocked), then the lock moves to the new step:
    # no step ever locks out the running share method, so the game never has to replace it itself.
    # Only a share that is not running is activated (pmr_read_blend_<b> finds out first): activating
    # a running share again counted its goods twice (see pmr_tick_<b>). With 1% steps the step is
    # found by bisection, so a tick costs about seven comparisons per recipe, not a hundred.
    def pm(kind, i, n):
        return f'pm_pmr_{kind}_{b}_{i}_{n}'

    def pm_active(kind, i, n):
        return f'is_production_method_active = {{ building_type = {bk} production_method = {pm(kind, i, n)} }}'

    def act(kind, i, n):
        return f'activate_production_method = {{ building_type = {bk} production_method = {pm(kind, i, n)} }}'

    def bisect(var, leaf, ind, lo=0, hi=SHARE_STEPS):
        """leaf(n) for the step n held in var, found in log2(SHARE_STEPS) comparisons. Not indented by
        depth: with 1% steps these ladders are most of the file."""
        if lo == hi:
            return f'{ind}{leaf(lo)}\n'
        mid = (lo + hi) // 2
        return (f'{ind}if = {{ limit = {{ var:{var} <= {mid} }}\n' + bisect(var, leaf, ind, lo, mid)
                + f'{ind}}}\n{ind}else = {{\n' + bisect(var, leaf, ind, mid + 1, hi) + f'{ind}}}\n')

    # pmr_a_<i>: the step the tick wants (pmr_n_<i>) if that share method runs, else -1. Read before
    # the blend to see what must change, and after it for the log.
    o.append(f'pmr_read_blend_{b} = {{\n')
    for i in range(1, nb_all + 1):
        o.append(f'\t{setv(f"pmr_a_{i}", -1)}\n'
                 + bisect(v(f'pmr_n_{i}'), lambda n, i=i: f'if = {{ limit = {{ {pm_active("share", i, n)} }} {setv(f"pmr_a_{i}", n)} }}', '\t',
                          hi=hi_of.get(i, SHARE_STEPS)))
    o.append('}\n\n')

    # pmr_lock_<i>_<b>: member i's lock onto the step the tick wants.
    for i in range(1, nb_all + 1):
        o.append(f'pmr_lock_{i}_{b} = {{\n'
                 + bisect(v(f'pmr_n_{i}'), lambda n, i=i: act("key", i, n), '\t', hi=hi_of.get(i, SHARE_STEPS)) + '}\n\n')

    def step(i, cum):
        # member i's share in steps, never past what is left of the whole (SHARE_STEPS less cum)
        return (f'\t\t{setv(f"pmr_n_{i}", "var:" + v(f"{sv}_{i}"))}\n'
                f'\t\t{chg(f"pmr_n_{i}", "multiply", SHARE_STEPS)}\n'
                f'\t\tround_variable = {{ name = {v(f"pmr_n_{i}")} nearest = 1 }}\n'
                f'\t\t{setv("pmr_nrest", SHARE_STEPS)}\n'
                f'\t\t{chg("pmr_nrest", "subtract", "var:" + v(cum))}\n'
                f'\t\tif = {{ limit = {{ var:{v(f"pmr_n_{i}")} > var:{v("pmr_nrest")} }} {setv(f"pmr_n_{i}", "var:" + v("pmr_nrest"))} }}\n'
                f'\t\t{chg(cum, "add", "var:" + v(f"pmr_n_{i}"))}\n')
    o.append(f'pmr_blend_{b} = {{\n\t{setv("pmr_ncum", 0)}\n')
    for i, idxs, grp in bm:
        if grp != 'recipe':
            continue
        on_target = (f'var:{v("pmr_to")} = {idxs[0]}' if len(idxs) == 1 else
                     'OR = { ' + ' '.join(f'var:{v("pmr_to")} = {x}' for x in idxs) + ' }')
        o.append(f'\tif = {{\n\t\tlimit = {{ NOT = {{ {on_target} }} }}\n' + step(i, 'pmr_ncum') + '\t}\n')
    o.append(on_index('pmr_to', lambda i: f'{setv(f"pmr_n_{rec_of[i]}", SHARE_STEPS)} '
                                          f'{chg(f"pmr_n_{rec_of[i]}", "subtract", "var:" + v("pmr_ncum"))}'))
    # automation members (the split): each its own share, rounded, the methods of one group never past the whole
    for grp in dict.fromkeys(grp for _, _, grp in bm if grp != 'recipe'):
        o.append(f'\t# {grp}\n\t{setv("pmr_gcum", 0)}\n'
                 + ''.join(step(i, 'pmr_gcum') for i, _, g2 in bm if g2 == grp))
    for j, _n in works:
        o.append(f'\t# Company Culture works member (pmr_works_{b})\n\t{setv(f"pmr_n_{j}", "var:" + v(f"pmr_wn_{j}"))}\n')
    o.append(f'\tpmr_read_blend_{b} = yes\n')
    for i in range(1, nb_all + 1):
        o.append(f'\t# recipe {i}: if its share is not the one wanted, unlock every share, switch, lock again;\n'
                 '\t# if only the lock moved (the AI took the switching lock), lock again\n'
                 f'\tif = {{\n\t\tlimit = {{ var:{v(f"pmr_a_{i}")} = -1 }}\n'
                 f'\t\tif = {{ limit = {{ NOT = {{ {pm_active("key", i, "any")} }} }} {act("key", i, "any")} }}\n'
                 + bisect(v(f'pmr_n_{i}'), lambda n, i=i: act("share", i, n), '\t\t', hi=hi_of.get(i, SHARE_STEPS))
                 + f'\t\tpmr_lock_{i}_{b} = yes\n\t}}\n'
                 f'\telse_if = {{ limit = {{ {pm_active("key", i, "any")} }} pmr_lock_{i}_{b} = yes }}\n')
    o.append('}\n\n')

    # The levels the state tracks always add up to the building's level. New levels arrive on the
    # recipe the building runs; lost levels go from the oldest recipe first.
    o.append(f'pmr_sync_levels_{b} = {{\n\t{setv("pmr_lvsum", 0)}\n'
             + ''.join(f'\t{chg("pmr_lvsum", "add", "var:" + lv(i))}\n' for i in range(1, k + 1))
             + f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_lvsum")} < var:{v("pmr_level")} }}\n'
             f'\t\t{setv("pmr_d", "var:" + v("pmr_level"))}\n\t\t{chg("pmr_d", "subtract", "var:" + v("pmr_lvsum"))}\n'
             + on_index('pmr_to', lambda i: f'change_variable = {{ name = {lv(i)} add = var:{v("pmr_d")} }}', '\t\t')
             + f'\t}}\n\telse_if = {{\n\t\tlimit = {{ var:{v("pmr_lvsum")} > var:{v("pmr_level")} }}\n'
             f'\t\t{setv("pmr_d", "var:" + v("pmr_lvsum"))}\n\t\t{chg("pmr_d", "subtract", "var:" + v("pmr_level"))}\n'
             + ''.join(f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_d")} > 0 var:{lv(i)} > 0 }}\n'
                       f'\t\t\tif = {{ limit = {{ var:{lv(i)} >= var:{v("pmr_d")} }} '
                       f'change_variable = {{ name = {lv(i)} subtract = var:{v("pmr_d")} }} {setv("pmr_d", 0)} }}\n'
                       f'\t\t\telse = {{ {chg("pmr_d", "subtract", "var:" + lv(i))} set_variable = {{ name = {lv(i)} value = 0 }} }}\n'
                       '\t\t}\n' for i in range(1, k + 1))
             + '\t}\n}\n\n')

    # government-owned share of the building, read through the building-scope ownership trigger
    steps = round(1 / GOV_FRACTION_STEP)
    o.append(f'pmr_read_gov_{b} = {{\n'
             + highest(list(range(1, steps + 1)),
                       lambda n: f'b:{bk} = {{ country_ownership_fraction >= {fmt(n * GOV_FRACTION_STEP - GOV_FRACTION_STEP / 2)} }}',
                       lambda n: setv("pmr_gov_frac", fmt(n * GOV_FRACTION_STEP) if n else 0)))
    o.append('\t# Government-owned levels, which the state owner\'s count in levels_owned_by_country includes.\n'
             f'\tset_variable = {{ name = {v("pmr_gov_levels")} value = b:{bk}.level }}\n'
             f'\t{chg("pmr_gov_levels", "multiply", "var:" + v("pmr_gov_frac"))}\n'
             f'\tround_variable = {{ name = {v("pmr_gov_levels")} nearest = 1 }}\n'
             '\t# Abroad (pmr_abroad_<b>) too: the player\'s investors retool only privately owned levels there, never a\n'
             '\t# government\'s (Pat 2026-10-13 20:54Z). The fraction counts every government\'s levels together, so the\n'
             '\t# player\'s own government levels (pmr_gov_mine_<b>), which its government retools through its own\n'
             '\t# construction queue (Pat 21:26Z), are read as at least the levels the player and its investors own\n'
             '\t# less every privately owned level, and never more than all the governments\' levels.\n'
             f'\t{setv("pmr_gov_mine", 0)}\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_abroad_{b} has_global_variable = pmr_player var:{v("pmr_gov_levels")} > 0 }}\n'
             f'\t\t{setv("pmr_gm_n", f"b:{bk}.level")}\n'
             f'\t\t{chg("pmr_gm_n", "subtract", "var:" + v("pmr_gov_levels"))}\n'
             f'\t\twhile = {{\n\t\t\tlimit = {{\n\t\t\t\tvar:{v("pmr_gov_mine")} < var:{v("pmr_gov_levels")}\n'
             f'\t\t\t\tb:{bk} = {{ levels_owned_by_country = {{ target = global_var:pmr_player value > state.var:{v("pmr_gm_n")} }} }}\n'
             '\t\t\t}\n'
             f'\t\t\t{chg("pmr_gov_mine", "add", 1)}\n\t\t\t{chg("pmr_gm_n", "add", 1)}\n\t\t}}\n\t}}\n'
             '}\n\n')

    # Which recipes the government's own levels run (pmr_lvg_<i>), so it retools only those. Pat,
    # 2026-10-13: two new government levels of the Sicily sulfur mine arrived on the new recipe, yet
    # the upgrade button still offered the government two of the five old private levels, because the
    # split went by ownership alone. Levels the government gains (it built them, or bought them) are
    # placed on the recipe the building runs first, as new levels arrive, then oldest first; levels it
    # loses go from its oldest recipe first.
    def place(i, ind):
        return (f'{ind}if = {{\n{ind}\tlimit = {{ var:{v("pmr_gd")} > 0 }}\n'
                f'{ind}\t{setv("pmr_amt", "var:" + lv(i))}\n{ind}\t{chg("pmr_amt", "subtract", "var:" + lvg(i))}\n'
                f'{ind}\tif = {{ limit = {{ var:{v("pmr_amt")} > var:{v("pmr_gd")} }} {setv("pmr_amt", "var:" + v("pmr_gd"))} }}\n'
                f'{ind}\tchange_variable = {{ name = {lvg(i)} add = var:{v("pmr_amt")} }}\n'
                f'{ind}\t{chg("pmr_gd", "subtract", "var:" + v("pmr_amt"))}\n{ind}}}\n')
    o.append(f'pmr_sync_gov_{b} = {{\n'
             + ''.join(f'\tif = {{ limit = {{ NOT = {{ has_variable = {lvg(i)} }} }} set_variable = {{ name = {lvg(i)} value = 0 }} }}\n'
                       f'\tif = {{ limit = {{ var:{lvg(i)} > var:{lv(i)} }} set_variable = {{ name = {lvg(i)} value = var:{lv(i)} }} }}\n'
                       for i in range(1, k + 1))
             + f'\t{setv("pmr_gsum", 0)}\n'
             + ''.join(f'\t{chg("pmr_gsum", "add", "var:" + lvg(i))}\n' for i in range(1, k + 1))
             + f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_gsum")} < var:{v("pmr_gov_levels")} }}\n'
             f'\t\t{setv("pmr_gd", "var:" + v("pmr_gov_levels"))}\n\t\t{chg("pmr_gd", "subtract", "var:" + v("pmr_gsum"))}\n'
             + ''.join(f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_to")} = {i} }}\n' + place(i, '\t\t\t') + '\t\t}\n'
                       for i in range(1, k + 1))
             + ''.join(place(i, '\t\t') for i in range(1, k + 1))
             + f'\t}}\n\telse_if = {{\n\t\tlimit = {{ var:{v("pmr_gsum")} > var:{v("pmr_gov_levels")} }}\n'
             f'\t\t{setv("pmr_gd", "var:" + v("pmr_gsum"))}\n\t\t{chg("pmr_gd", "subtract", "var:" + v("pmr_gov_levels"))}\n'
             + ''.join(f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_gd")} > 0 var:{lvg(i)} > 0 }}\n'
                       f'\t\t\t{setv("pmr_amt", "var:" + lvg(i))}\n'
                       f'\t\t\tif = {{ limit = {{ var:{v("pmr_amt")} > var:{v("pmr_gd")} }} {setv("pmr_amt", "var:" + v("pmr_gd"))} }}\n'
                       f'\t\t\tchange_variable = {{ name = {lvg(i)} subtract = var:{v("pmr_amt")} }}\n'
                       f'\t\t\t{chg("pmr_gd", "subtract", "var:" + v("pmr_amt"))}\n\t\t}}\n' for i in range(1, k + 1))
             + '\t}\n}\n\n')

    def read_side(rbx, side):
        return (f'\t{setv("pmr_retool_built_" + side, 0)}\n'
                f'\t{setv("pmr_retool_q_" + side, 0)}\n'
                f'\tif = {{\n\t\tlimit = {{ OR = {{ has_building = {rbx} exists = b:{rbx} }} }}\n'
                f'\t\t{setv("pmr_retool_built_" + side, f"b:{rbx}.level")}\n'
                f'\t\t{setv("pmr_retool_q_" + side, f"b:{rbx}.level_after_queued_constructions")}\n'
                '\t}\n')

    def totals():
        """Private totals over the slots, pending per side, and both sides together."""
        return (f'\t{setv("pmr_retool_built_priv", 0)}\n\t{setv("pmr_retool_q_priv", 0)}\n'
                + ''.join(f'\t{chg("pmr_retool_built_priv", "add", "var:" + v(f"pmr_retool_built_priv{j}"))}\n'
                          f'\t{chg("pmr_retool_q_priv", "add", "var:" + v(f"pmr_retool_q_priv{j}"))}\n' for j, _ in slots)
                + ''.join(f'\t{setv("pmr_pending_" + side, "var:" + v("pmr_retool_q_" + side))}\n'
                          f'\t{chg("pmr_pending_" + side, "subtract", "var:" + v("pmr_retool_built_" + side))}\n'
                          for side in ('priv', 'gov'))
                + f'\t{setv("pmr_retool_built", "var:" + v("pmr_retool_built_priv"))}\n'
                f'\t{chg("pmr_retool_built", "add", "var:" + v("pmr_retool_built_gov"))}\n'
                f'\t{setv("pmr_pending", "var:" + v("pmr_pending_priv"))}\n'
                f'\t{chg("pmr_pending", "add", "var:" + v("pmr_pending_gov"))}\n')
    o.append(f'pmr_read_retool_{b} = {{\n'
             '\t# A retool still entirely under construction may not count for has_building.\n'
             + ''.join(read_side(rbx, f'priv{j}') for j, rbx in slots) + read_side(rbg, 'gov') + read_side(rbga, 'gova')
             + '\t# the player\'s government\'s site abroad is the government side there\n'
             f'\t{chg("pmr_retool_built_gov", "add", "var:" + v("pmr_retool_built_gova"))}\n'
             f'\t{chg("pmr_retool_q_gov", "add", "var:" + v("pmr_retool_q_gova"))}\n'
             + totals() +
             '}\n\n')

    # A government retool building whose levels are all counted and with nothing queued on it is
    # removed, so the next government level is a new construction. So is a private one, unless it has
    # a crew (RETOOL_CREW, 0 since Pat's 03:37Z call): then it stays so investors can expand it, until
    # the crew is still short RETOOL_CREW_GRACE_DAYS after its last level landed. Never removed while
    # anything is queued on it (that leaves a NULL_STATE construction).
    def release(rbx, side, keep=''):
        seen = 'pmr_seen_gov' if side.startswith('gov') else 'pmr_seen_priv'
        built = v('pmr_retool_built_' + side)
        # A crewed private one may still have staff when it goes: logged (flush_log) in case that hangs.
        crumb = '' if side.startswith('gov') else f"\t\t{flush_log('RELEASE', rbx, f';built=[THIS.Var({built!r}).GetValue|0]')}\n"
        # the abroad site's levels are also in the government side's totals
        merged = (f'\t\t{chg("pmr_retool_built_gov", "subtract", "var:" + built)}\n'
                  f'\t\t{chg("pmr_retool_q_gov", "subtract", "var:" + v("pmr_retool_q_gova"))}\n' if side == 'gova' else '')
        return (f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_retool_built_" + side)} > 0 '
                f'var:{v("pmr_retool_q_" + side)} <= var:{v("pmr_retool_built_" + side)} {keep}'
                f'OR = {{ has_building = {rbx} exists = b:{rbx} }} }}\n'
                + crumb +
                f'\t\tremove_building = {rbx}\n'
                + crumb.replace('RELEASE', 'RELEASED') +
                f'\t\t{chg(seen, "subtract", "var:" + v("pmr_retool_built_" + side))}\n'
                + merged +
                f'\t\t{setv("pmr_retool_built_" + side, 0)}\n'
                f'\t\t{setv("pmr_retool_q_" + side, 0)}\n\t}}\n')

    def keep_crew(j):
        return (f'NOT = {{ has_variable = {v(f"pmr_grace_priv{j}")} }} '
                f'var:{v(f"pmr_staff_priv{j}")} < 2 ')

    # pmr_staff_priv<j>: the crew of private retool building j, -1 without a finished level, 0 nobody
    # hired, 1 some, 2 at least RETOOL_CREW_STAFFED. A level landing starts its grace period.
    def crew(j, rbx):
        built, prev = v(f'pmr_retool_built_priv{j}'), v(f'pmr_prev_priv{j}')
        return (f'\t{setv(f"pmr_staff_priv{j}", -1)}\n'
                f'\tif = {{\n\t\tlimit = {{ var:{built} > 0 exists = b:{rbx} }}\n'
                f'\t\tif = {{ limit = {{ b:{rbx} = {{ occupancy >= {RETOOL_CREW_STAFFED} }} }} {setv(f"pmr_staff_priv{j}", 2)} }}\n'
                f'\t\telse_if = {{ limit = {{ b:{rbx} = {{ occupancy > 0 }} }} {setv(f"pmr_staff_priv{j}", 1)} }}\n'
                f'\t\telse = {{ {setv(f"pmr_staff_priv{j}", 0)} }}\n\t}}\n'
                f'\tif = {{ limit = {{ NOT = {{ has_variable = {prev} }} }} {setv(f"pmr_prev_priv{j}", 0)} }}\n'
                f'\tif = {{ limit = {{ var:{built} > var:{prev} }} '
                f'set_variable = {{ name = {v(f"pmr_grace_priv{j}")} value = yes days = {RETOOL_CREW_GRACE_DAYS} }} }}\n'
                f'\t{setv(f"pmr_prev_priv{j}", "var:" + built)}\n')

    # Move up to var conv of recipe i's government (gov) or private levels onto the target.
    def convert(conv, i, gov):
        avail = (f'\t\t{setv("pmr_amt", "var:" + lvg(i))}\n' if gov else
                 f'\t\t{setv("pmr_amt", "var:" + lv(i))}\n\t\t{chg("pmr_amt", "subtract", "var:" + lvg(i))}\n')
        return (f'\tif = {{\n\t\tlimit = {{ var:{v(conv)} > 0 NOT = {{ var:{v("pmr_to")} = {i} }} }}\n'
                + avail +
                f'\t\tif = {{ limit = {{ var:{v("pmr_amt")} > var:{v(conv)} }} {setv("pmr_amt", "var:" + v(conv))} }}\n'
                f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_amt")} > 0 }}\n'
                f'\t\t\tchange_variable = {{ name = {lv(i)} subtract = var:{v("pmr_amt")} }}\n'
                + (f'\t\t\tchange_variable = {{ name = {lvg(i)} subtract = var:{v("pmr_amt")} }}\n'
                   f'\t\t\t{chg("pmr_ggain", "add", "var:" + v("pmr_amt"))}\n' if gov else '')
                + f'\t\t\t{chg(conv, "subtract", "var:" + v("pmr_amt"))}\n'
                f'\t\t\t{chg("pmr_gain", "add", "var:" + v("pmr_amt"))}\n\t\t}}\n\t}}\n')

    def count(side):
        conv, seen, built = f'pmr_conv_{side}', f'pmr_seen_{side}', f'pmr_retool_built_{side}'
        return (f'\tif = {{ limit = {{ NOT = {{ has_variable = {v(seen)} }} }} {setv(seen, 0)} }}\n'
                f'\t{setv(conv, "var:" + v(built))}\n'
                f'\t{chg(conv, "subtract", "var:" + v(seen))}\n'
                f'\tif = {{ limit = {{ var:{v(conv)} < 0 }} {setv(conv, 0)} }}\n'
                f'\t{setv(seen, "var:" + v(built))}\n'
                f'\t{chg(conv, "divide", "pmr_retool_levels_per_level")}\n')

    # Completed retool levels not yet counted move levels onto the target, oldest recipe first: a
    # government retool level moves one of the government's own levels (pmr_lvg_*), a private one a
    # privately owned level. Levels a side can't use (it has none left to retool, after a sale) move
    # the other side's. The retool buildings keep their levels between retools, so pmr_seen_<side>
    # counts the levels already used and only the rest move anything.
    o.append(f'pmr_progress_{b} = {{\n\tpmr_read_retool_{b} = yes\n'
             + (''.join(crew(j, rbx) for j, rbx in slots) if RETOOL_CREW else '')
             + count('gov') + count('priv')
             + f'\t{setv("pmr_gain", 0)}\n\t{setv("pmr_ggain", 0)}\n'
             + ''.join(convert('pmr_conv_gov', i, True) for i in range(1, k + 1))
             + ''.join(convert('pmr_conv_priv', i, False) for i in range(1, k + 1))
             + f'\t{chg("pmr_conv_priv", "add", "var:" + v("pmr_conv_gov"))}\n'
             + ''.join(convert('pmr_conv_priv', i, False) for i in range(1, k + 1))
             + ''.join(convert('pmr_conv_priv', i, True) for i in range(1, k + 1))
             + on_index('pmr_to', lambda i: f'change_variable = {{ name = {lv(i)} add = var:{v("pmr_gain")} }} '
                                            f'change_variable = {{ name = {lvg(i)} add = var:{v("pmr_ggain")} }}')
             + ''.join(release(rbx, f'priv{j}', keep_crew(j) if RETOOL_CREW else '') for j, rbx in slots)
             + release(rbg, 'gov')
             # the abroad site stands while the player's government still has room (pmr_split_retool_<b>)
             + release(rbga, 'gova', f'NOT = {{ AND = {{ has_variable = pmr_abroad_{b} has_variable = pmr_retool_open_gov_{b} }} }} ')
             + totals() + '}\n\n')

    # Shares for the bar and the blend, the levels still to retool, and p (share on the target).
    o.append(f'pmr_mix_{b} = {{\n'
             + on_index('pmr_to', lambda i: setv("pmr_lv_to", "var:" + lv(i)))
             + f'\t{setv("pmr_need", "var:" + v("pmr_level"))}\n'
             f'\t{chg("pmr_need", "subtract", "var:" + v("pmr_lv_to"))}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_need")} < 0 }} {setv("pmr_need", 0)} }}\n'
             f'\t{chg("pmr_need", "multiply", "pmr_retool_levels_per_level")}\n'
             f'\t{setv("pmr_p", "var:" + v("pmr_lv_to"))}\n'
             f'\t{chg("pmr_p", "divide", "var:" + v("pmr_level"))}\n'
             f'\t{setv("pmr_cum", 0)}\n'
             + ''.join(f'\t{setv(f"pmr_sh_{i}", "var:" + lv(i))}\n'
                       f'\t{chg(f"pmr_sh_{i}", "divide", "var:" + v("pmr_level"))}\n'
                       f'\t{chg("pmr_cum", "add", "var:" + v(f"pmr_sh_{i}"))}\n'
                       f'\t{setv(f"pmr_cum_{i}", "var:" + v("pmr_cum"))}\n' for i in range(1, k + 1))
             + ''.join(f'\t{setv(f"pmr_ash_{a}", 0)}\n'
                       + ''.join(f'\t{chg(f"pmr_ash_{a}", "add", "var:" + v(f"pmr_sh_{i}"))}\n' for i in tiers)
                       for a, tiers in enumerate(auto_tiers, 1))
             + '\t# privately owned levels per recipe, for the Owners list\n'
             + ''.join(f'\t{setv(f"pmr_lvp_{i}", "var:" + lv(i))}\n\t{chg(f"pmr_lvp_{i}", "subtract", "var:" + lvg(i))}\n'
                       for i in range(1, k + 1))
             + ('\t# the split: each member\'s share (the blend, the bars), and each plain recipe\'s levels (the Owners list)\n'
                + ''.join(f'\t{setv(f"pmr_rs_{j}", 0)}\n'
                          + ''.join(f'\t{chg(f"pmr_rs_{j}", "add", "var:" + v(f"pmr_sh_{i}"))}\n' for i in idxs)
                          + (f'\t{setv(f"pmr_rlvg_{j}", 0)}\n\t{setv(f"pmr_rlvp_{j}", 0)}\n'
                             + ''.join(f'\t{chg(f"pmr_rlvg_{j}", "add", "var:" + lvg(i))}\n'
                                       f'\t{chg(f"pmr_rlvp_{j}", "add", "var:" + v(f"pmr_lvp_{i}"))}\n' for i in idxs)
                             if grp == 'recipe' else '')
                          for j, idxs, grp in bm) if split else '')
             + f'\tif = {{ limit = {{ var:{v("pmr_need")} > 0 }} {setv("pmr_ui_retooling", 1)} }}\n'
             f'\telse = {{ {setv("pmr_ui_retooling", 0)} }}\n'
             '}\n\n')

    # Who may add retool levels, from who owns the building now. The levels still to retool (need)
    # are split by ownership; each side's room is its share less what it already has queued, and
    # the rooms never add up to more than need less everything queued.
    def clamp_to(name, other):
        return (f'\tif = {{ limit = {{ var:{v(name)} > var:{v(other)} }} '
                f'{setv(name, "var:" + v(other))} }}\n')
    o.append(f'pmr_split_retool_{b} = {{\n'
             '\t# The government retools its own levels not yet on the target (pmr_sync_gov_<b>), the\n'
             '\t# private owners the rest.\n'
             + f'\t{setv("pmr_gov_on_to", 0)}\n'
             + on_index('pmr_to', lambda i: setv("pmr_gov_on_to", "var:" + lvg(i)))
             + f'\t{setv("pmr_retool_gov", "var:" + v("pmr_gov_levels"))}\n'
             f'\t{chg("pmr_retool_gov", "subtract", "var:" + v("pmr_gov_on_to"))}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_retool_gov")} < 0 }} {setv("pmr_retool_gov", 0)} }}\n'
             f'\t{chg("pmr_retool_gov", "multiply", "pmr_retool_levels_per_level")}\n'
             + clamp_to("pmr_retool_gov", "pmr_need") +
             f'\t{setv("pmr_retool_priv", "var:" + v("pmr_need"))}\n'
             f'\t{chg("pmr_retool_priv", "subtract", "var:" + v("pmr_retool_gov"))}\n'
             f'\t{setv("pmr_room", "var:" + v("pmr_need"))}\n'
             f'\t{chg("pmr_room", "subtract", "var:" + v("pmr_pending"))}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_room")} < 0 }} {setv("pmr_room", 0)} }}\n'
             + (f'\t# The target needs electricity and the state makes none: no new retooling until it does.\n'
                f'\t{setv("pmr_elec_wait", 0)}\n'
                + on_index('pmr_to', lambda i: f'if = {{ limit = {{ var:pmr_elec = 0 }} {setv("pmr_room", 0)} {setv("pmr_elec_wait", 1)} }}'
                           if i in elec_tiers else f'{setv("pmr_elec_wait", 0)}')
                if elec_tiers else '') +
             ('' if RELEASE else
                '\t# Diagnostic for the log: may the home investment pool fund this building\'s private retooling?\n'
                '\tif = {\n\t\tlimit = { owner = { is_player = yes } }\n'
                '\t\towner = { save_temporary_scope_as = investor_country }\n'
                f'\t\tif = {{ limit = {{ pmr_retool_investor_{b} = yes }} {setv("pmr_inv_home", 1)} }}\n'
                f'\t\telse = {{ {setv("pmr_inv_home", 0)} }}\n\t}}\n') +
             f'\t{setv("pmr_room_gov", "var:" + v("pmr_retool_gov"))}\n'
             f'\t{chg("pmr_room_gov", "subtract", "var:" + v("pmr_pending_gov"))}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_room_gov")} < 0 }} {setv("pmr_room_gov", 0)} }}\n'
             + clamp_to("pmr_room_gov", "pmr_room") +
             f'\t{setv("pmr_room_priv", "var:" + v("pmr_room"))}\n'
             f'\t{chg("pmr_room_priv", "subtract", "var:" + v("pmr_room_gov"))}\n'
             '\t# Abroad the government side is the player\'s own government levels (pmr_gov_mine_<b>) less the\n'
             '\t# governments\' levels already on the target: other governments\' levels there are never retooled\n'
             '\t# (Pat 20:54Z), and they stay out of the private room above.\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_abroad_{b} }}\n'
             f'\t\t{setv("pmr_gm_room", "var:" + v("pmr_gov_mine"))}\n'
             f'\t\t{chg("pmr_gm_room", "subtract", "var:" + v("pmr_gov_on_to"))}\n'
             f'\t\t{chg("pmr_gm_room", "multiply", "pmr_retool_levels_per_level")}\n'
             f'\t\t{chg("pmr_gm_room", "subtract", "var:" + v("pmr_pending_gov"))}\n'
             f'\t\tif = {{ limit = {{ var:{v("pmr_gm_room")} < 0 }} {setv("pmr_gm_room", 0)} }}\n'
             f'\t\tif = {{ limit = {{ var:{v("pmr_room_gov")} > var:{v("pmr_gm_room")} }} {setv("pmr_room_gov", "var:" + v("pmr_gm_room"))} }}\n'
             '\t}\n'
             f'\t{setv("pmr_cap_gov", "var:" + v("pmr_retool_q_gov"))}\n'
             f'\t{chg("pmr_cap_gov", "add", "var:" + v("pmr_room_gov"))}\n'
             f'\tset_variable = pmr_retool_gate_{b}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_room_gov")} > 0 }} set_variable = pmr_retool_open_gov_{b} }}\n'
             f'\telse_if = {{ limit = {{ has_variable = pmr_retool_open_gov_{b} }} remove_variable = pmr_retool_open_gov_{b} }}\n'
             '\t# Abroad no script effect queues a construction for the player\'s government: the upgrade button\n'
             '\t# expands a site that stands (Building.QueueConstruction). So while its government has room the\n'
             '\t# tick keeps one, a level owned by the player\'s government that counts as used (pmr_seen_gov).\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_abroad_{b} has_variable = pmr_retool_open_gov_{b} has_global_variable = pmr_player '
             f'NOT = {{ has_building = {rbga} }} NOT = {{ exists = b:{rbga} }} }}\n'
             f'\t\tcreate_building = {{\n\t\t\tbuilding = {rbga}\n'
             '\t\t\tadd_ownership = { country = { country = global_var:pmr_player levels = 1 } }\n\t\t}\n'
             f'\t\tif = {{ limit = {{ NOT = {{ has_variable = {v("pmr_seen_gov")} }} }} {setv("pmr_seen_gov", 0)} }}\n'
             f'\t\t{chg("pmr_seen_gov", "add", 1)}\n'
             f'\t\t{chg("pmr_cap_gov", "add", 1)}\n\t}}\n'
             + ('\t# Private: the retool building takes the whole room (RETOOL_STACK), so investors may queue\n'
                '\t# several levels on it at once. Its cap (pmr_cap_priv<j>_<b>) is what it has plus the room.\n'
                if RETOOL_STACK else
                '\t# Private: each empty retool building may take one level, as a new construction; the rest\n'
                '\t# of the room goes to the first one with a finished level, whose crew lets investors\n'
                '\t# expand it. Each gets a cap (pmr_cap_priv<j>_<b>) of what it has plus its share.\n') +
             '\t# The home slots where investors retool at home, the abroad slot where the player owns levels\n'
             '\t# abroad (ABROAD_SLOT).\n'
             f'\t{setv("pmr_slots_left", "var:" + v("pmr_room_priv"))}\n'
             + ''.join(f'\t{setv(f"pmr_alloc{j}", 0)}\n' for j, _ in slots)
             + (''.join(f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_slots_left")} > 0 {slot_here(j)} }}\n'
                        f'\t\t{setv(f"pmr_alloc{j}", "var:" + v("pmr_slots_left"))}\n\t\t{setv("pmr_slots_left", 0)}\n\t}}\n'
                        for j, _ in slots) if RETOOL_STACK else
                ''.join(f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_slots_left")} > 0 var:{v(f"pmr_retool_q_priv{j}")} <= 0 {slot_here(j)} }}\n'
                        f'\t\t{setv(f"pmr_alloc{j}", 1)}\n\t\t{chg("pmr_slots_left", "subtract", 1)}\n\t}}\n'
                        for j, _ in slots)
                + ''.join(f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_slots_left")} > 0 var:{v(f"pmr_retool_built_priv{j}")} > 0 {slot_here(j)} }}\n'
                          f'\t\t{chg(f"pmr_alloc{j}", "add", "var:" + v("pmr_slots_left"))}\n\t\t{setv("pmr_slots_left", 0)}\n\t}}\n'
                          for j, _ in slots))
             + ''.join(f'\tset_variable = {{ name = pmr_cap_priv{j}_{b} value = var:{v(f"pmr_retool_q_priv{j}")} }}\n'
                       f'\tchange_variable = {{ name = pmr_cap_priv{j}_{b} add = var:{v(f"pmr_alloc{j}")} }}\n'
                       # with levels stacked on it the site stays open while any is still queued, in case the game
                       # re-checks can_build_private for waiting constructions; its cap still stops new ones
                       + (f'\tif = {{ limit = {{ OR = {{ var:{v(f"pmr_alloc{j}")} > 0 '
                          f'var:{v(f"pmr_retool_q_priv{j}")} > var:{v(f"pmr_retool_built_priv{j}")} }} }} '
                          f'set_variable = pmr_retool_open_priv_{b}_{j} }}\n' if RETOOL_STACK else
                          f'\tif = {{ limit = {{ var:{v(f"pmr_alloc{j}")} > 0 }} set_variable = pmr_retool_open_priv_{b}_{j} }}\n')
                       + f'\telse_if = {{ limit = {{ has_variable = pmr_retool_open_priv_{b}_{j} }} remove_variable = pmr_retool_open_priv_{b}_{j} }}\n'
                       for j, _ in slots) +
             '}\n\n')

    # Nothing left to retool. A retool building with levels still queued is never removed: that
    # leaves a construction with no building (seen as NULL_STATE in the queue). It is closed
    # instead, and removed by a later tick once its queue has emptied.
    flags = [f'pmr_retool_open_priv_{b}_{j}' for j, _ in slots] + [f'pmr_retool_open_gov_{b}']
    o.append(f'pmr_close_retool_{b} = {{\n'
             + ''.join(f'\tif = {{ limit = {{ has_variable = {fl} }} remove_variable = {fl} }}\n' for fl in flags)
             + f'\t{setv("pmr_room_priv", 0)}\n\t{setv("pmr_room_gov", 0)}\n'
             f'\t{setv("pmr_cap_gov", "var:" + v("pmr_retool_q_gov"))}\n'
             + ''.join(f'\tif = {{ limit = {{ var:{v("pmr_retool_q_" + side)} <= var:{v("pmr_retool_built_" + side)} '
                       f'OR = {{ has_building = {rbx} exists = b:{rbx} }} }} remove_building = {rbx} }}\n'
                       for rbx, side in [(rbx, f'priv{j}') for j, rbx in slots] + [(rbg, 'gov'), (rbga, 'gova')])
             + f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_pending")} <= 0 }}\n'
             f'\t\t{setv("pmr_seen_gov", 0)}\n\t\t{setv("pmr_seen_priv", 0)}\n'
             + ''.join(f'\t\tif = {{ limit = {{ has_variable = {n} }} remove_variable = {n} }}\n'
                       for n in (f'pmr_retool_gate_{b}', v('pmr_cap_gov'), v('pmr_gov_levels'))) +
             '\t}\n}\n\n')

    # The building's earnings per employee (ladder lower bound, 0 below the lowest step) and the
    # retool buildings' AI weight from it, before RETOOL_AI_MULT: RETOOL_AI_BASE + RETOOL_AI_PER_EARNING x earnings.
    o.append(f'pmr_read_earnings_{b} = {{\n'
             + highest(sorted(RETOOL_EARNINGS_LADDER), lambda x: f'b:{bk} = {{ earnings >= {x} }}',
                       lambda x: setv("pmr_earn", x or 0))
             + f'\t{setv("pmr_ai_w", "var:" + v("pmr_earn"))}\n'
             f'\t{chg("pmr_ai_w", "multiply", RETOOL_AI_PER_EARNING)}\n'
             f'\t{chg("pmr_ai_w", "add", RETOOL_AI_BASE)}\n'
             '}\n\n')

    # newest recipe the building runs or can activate; vanilla lists recipes oldest first. A recipe
    # that needs electricity counts only while the state produces it (pmr_elec, read by the tick).
    # Abroad (Pat, 2026-10-13 14:33Z): where the player's government or investors own levels in a
    # state another country owns (pmr_abroad_<b>, set by the tick), a recipe also counts once the
    # player has its technologies, as the levels the player owns there run on the player's know-how.
    # The host's own reach (pmr_hbest_now, the same without that) says whether the recipe's marker can
    # be activated there; a recipe gated by anything besides technology stays the host's call.
    # A recipe from AUTOMATION_FROM_TIER also needs its folded automation's technologies (fold_techs): its
    # marker only knows its own, so without them an era 2 Baking Powder brought the era 5 Automated
    # Bakery with it (PM balance review, 2026-10-18).
    def techs_of(r, i):
        return list(dict.fromkeys(list(getattr(r, 'techs', None) or getattr(r, 'unlock_techs', []))
                                  + fold_techs.get(i, [])))

    def abroad(r, i):
        techs = techs_of(r, i)
        if not techs or getattr(r, 'gated_otherwise', False):
            return None
        return (f'AND = {{ has_variable = pmr_abroad_{b} global_var:pmr_player ?= {{ '
                + ' '.join(f'has_technology_researched = {t}' for t in techs) + ' } }')

    def reach(i, with_abroad):
        """recipe i can become the target here: its marker can activate, the owner has its folded automation's
        technologies, abroad the player's know-how counts (with_abroad), and an electric recipe has electricity."""
        r = recipes[i - 1]
        can = f'can_activate_production_method = {{ building_type = {bk} production_method = {r.key} }}'
        # the electric recipe: its newest recipe's and its automation's technologies, all of them; any
        # recipe: its folded automation's
        owner_techs = list(dict.fromkeys(list(getattr(r, 'techs', None) or []) + fold_techs.get(i, [])))
        if owner_techs:   # the technologies first: they rule out most of a split type's pairs before the engine's check
            can = (f'AND = {{ owner = {{ '
                   + ' '.join(f'has_technology_researched = {t}' for t in owner_techs) + f' }} {can} }}')
        if with_abroad and abroad(r, i):
            can = f'OR = {{ {can} {abroad(r, i)} }}'
        if i in elec_tiers:
            can = f'AND = {{ {can} var:pmr_elec = 1 }}'
        return can

    def best_effect(name, var, with_abroad):
        out = [f'{name} = {{\n\t{setv(var, 0)}\n']
        for i in range(k, 0, -1):
            r = recipes[i - 1]
            kw = 'if' if i == k else 'else_if'
            out.append(f'\t{kw} = {{\n\t\tlimit = {{ OR = {{\n\t\t\t{active(r)}\n'
                       f'\t\t\t{reach(i, with_abroad)}\n'
                       f'\t\t}} }}\n\t\t{setv(var, i)}\n\t}}\n')
        out.append('}\n\n')
        return ''.join(out)
    o.append(best_effect(f"pmr_newest_{b}", "pmr_new_now", True))
    o.append(best_effect(f"pmr_hbest_{b}", "pmr_hbest_now", False))
    o.append(profit_effect(bk, b, recipes, econ, goods_cost or {}, active, reach, setv, v, pair))

    o.append(f'pmr_activate_{b} = {{\n')
    for i, r in enumerate(recipes, 1):
        kw = 'if' if i == 1 else 'else_if'
        o.append(f'\t{kw} = {{ limit = {{ var:{v("pmr_best_now")} = {i} }} '
                 f'activate_production_method = {{ building_type = {bk} production_method = {r.key} }} }}\n')
    o.append('}\n\n')

    def f(name, d=0):
        return f"[THIS.Var('{v(name)}').GetValue|{d}]"
    # blend: each recipe's share of the levels in steps of 1/SHARE_STEPS, as the tick set it;
    # active: the step each recipe's share group runs as the game reports it, -1 if none
    mix = (';blend=' + '/'.join(f(f'pmr_n_{i}') for i in range(1, nb_all + 1))
           + ';active=' + '/'.join(f(f'pmr_a_{i}') for i in range(1, nb_all + 1)))
    best = f";best={f('pmr_best_now')}" + mix
    split = mix + (f";gov_frac={f('pmr_gov_frac', 2)};gov_levels={f('pmr_gov_levels')}"
             f";share_gov={f('pmr_retool_gov')};share_priv={f('pmr_retool_priv')}"
             f";queued_gov={f('pmr_pending_gov')};queued_priv={f('pmr_pending_priv')}"
             f";room_gov={f('pmr_room_gov')};room_priv={f('pmr_room_priv')}"
             + ';gov_lv=' + '/'.join(f(f'pmr_lvg_{i}') for i in range(1, k + 1))
             + ';slots=' + '/'.join(f(f'pmr_retool_q_priv{j}') for j in range(1, RETOOL_SLOTS + 1))
             + (';crew=' + '/'.join(f(f'pmr_staff_priv{j}') for j in range(1, RETOOL_SLOTS + 1)) if RETOOL_CREW else '')
             + f";elec=[THIS.Var('pmr_elec').GetValue|0]" + (f";elec_wait={f('pmr_elec_wait')}" if elec_tiers else '')
             + f";home_investors={f('pmr_inv_home')};pool=[THIS.Var('pmr_pool').GetValue|0]"
             + f";earn={f('pmr_earn')};ai_w={f('pmr_ai_w')}"
             + ";unemp=[THIS.Var('pmr_unemp').GetValue|0]")
    done = mix + f";queued_gov={f('pmr_pending_gov')};queued_priv={f('pmr_pending_priv')}"


    # Every method change, including the tick's own, fires on_production_method_changed, and its tick
    # runs inside the change (seen in 1.14.5: a SWITCH line logged before the line of the tick that
    # made the switch, and about ten identical lines per change). Re-entered that way, the outer tick
    # re-activated a share the inner tick had already applied, and the game then counted that share's
    # goods twice (Pat's Sicily sulfur mine, two identical "(… of levels)" lines per switched recipe;
    # cause inferred from the log order).
    # So only the outermost tick runs (pmr_tick_<b>, below); the flag expires after a day in case a
    # tick never finishes.
    o.append(f'pmr_tick_body_{b} = {{\n'
             + (f'\t# a building just built takes the best-paying trade-offs (pmr_opts_{b})\n'
                f'\tif = {{ limit = {{ has_variable = pmr_new_build_{b} NOT = {{ has_variable = pmr_xinit_{b} }} }} '
                f'set_variable = pmr_xnew_{b} }}\n' if opts else '')
             + f'\t{setv("pmr_level", f"b:{bk}.level")}\n'
             '\tif = { limit = { NOT = { has_variable = pmr_elec_read } } pmr_read_elec = yes }\n'
             '\t# Abroad: the player (global_var:pmr_player) owns levels here, in a state another country owns.\n'
             f'\tif = {{\n\t\tlimit = {{ has_global_variable = pmr_player NOT = {{ owner = global_var:pmr_player }} '
             f'b:{bk} = {{ levels_owned_by_country = {{ target = global_var:pmr_player value >= 1 }} }} }}\n'
             f'\t\tset_variable = {{ name = pmr_abroad_{b} value = 1 }}  # a value, so the Owners list can read it\n'
             '\t\tset_variable = { name = pmr_abroad_any days = 62 }\n\t}\n'
             f'\telse_if = {{ limit = {{ has_variable = pmr_abroad_{b} }} remove_variable = pmr_abroad_{b} }}\n'
             f'\tpmr_best_{b} = yes\n'
             f'\tif = {{ limit = {{ has_variable = pmr_abroad_{b} }} pmr_hbest_{b} = yes }}\n'
             f'\telse = {{ {setv("pmr_hbest_now", "var:" + v("pmr_best_now"))} }}\n'
             '\t# First sight (game start, a new building, or a save from before the level mix): every\n'
             '\t# level runs the recipe the building runs now. Retool levels already built\n'
             '\t# count for nothing.\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = pmr_mix_{b} }} }}\n'
             f'\t\tset_variable = pmr_mix_{b}\n'
             f'\t\tif = {{ limit = {{ has_variable = {v("pmr_retooling")} }} remove_variable = {v("pmr_retooling")} }}\n'
             f'\t\t{setv("pmr_best", "var:" + v("pmr_best_now"))}\n'
             f'\t\tpmr_running_{b} = yes\n'
             f'\t\t{setv("pmr_to", "var:" + v("pmr_run"))}\n'
             f'\t\tpmr_reset_levels_{b} = yes\n'
             f'\t\tpmr_read_retool_{b} = yes\n'
             f'\t\t{setv("pmr_seen_gov", "var:" + v("pmr_retool_built_gov"))}\n'
             f'\t\t{setv("pmr_seen_priv", "var:" + v("pmr_retool_built_priv"))}\n'
             '\t\t# Newly constructed: built with the newest recipe the owner has, at no retooling cost.\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = {v("pmr_new_build")} var:{v("pmr_best_now")} > 0 '
             f'NOT = {{ var:{v("pmr_to")} = var:{v("pmr_best_now")} }} }}\n'
             f'\t\t\t{setv("pmr_to", "var:" + v("pmr_best_now"))}\n'
             f'\t\t\tpmr_reset_levels_{b} = yes\n'
             '\t\t\t# abroad on the player\'s technology the host cannot run the marker: nothing to wait for\n'
             f'\t\t\tif = {{\n\t\t\t\tlimit = {{ NOT = {{ var:{v("pmr_best_now")} > var:{v("pmr_hbest_now")} }} }}\n'
             f'\t\t\t\t{setv("pmr_adopting", 0)}\n'
             f'\t\t\t\tpmr_activate_{b} = yes\n\t\t\t}}\n'
             f'\t\t\tpmr_mix_{b} = yes\n'
             f'\t\t\t{log("ADOPT", bk, b, k)}\n\t\t}}\n'
             f'\t\tpmr_mix_{b} = yes\n'
             f'\t\t{log("INIT", bk, b, k, extra=best)}\n\t}}\n'
             f'\tif = {{ limit = {{ has_variable = {v("pmr_new_build")} }} remove_variable = {v("pmr_new_build")} }}\n')

    o.append('\t# Research: a newer recipe became available since the last tick, or the target is below the newest\n'
             '\t# recipe the owner can run (Pat, 2026-10-13 22:09Z: levels are built with the most advanced technology;\n'
             '\t# a building used to keep its game-start recipe as the target until the next recipe was researched, so\n'
             '\t# new levels arrived on it and the government had nothing to retool). Switch to it; the switch below\n'
             '\t# then opens retooling like any other.\n'
             + (f'\t# The profit pick (PROFIT_TARGET) can also step down: any pick other than the target moves it.\n'
                f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_best_now")} > 0 OR = {{ NOT = {{ var:{v("pmr_best_now")} = var:{v("pmr_best")} }} '
                f'NOT = {{ var:{v("pmr_best_now")} = var:{v("pmr_to")} }} }} }}\n' if PROFIT_TARGET else
                f'\tif = {{\n\t\tlimit = {{ OR = {{ var:{v("pmr_best_now")} > var:{v("pmr_best")} var:{v("pmr_best_now")} > var:{v("pmr_to")} }} }}\n') +
             f'\t\t{setv("pmr_best", "var:" + v("pmr_best_now"))}\n'
             f'\t\t{log("RESEARCH", bk, b, k, extra=best)}\n'
             '\t\t# Abroad, beyond what the host can run: the marker cannot follow, so the target moves\n'
             '\t\t# here and retooling opens as after a switch.\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_best_now")} > var:{v("pmr_hbest_now")} }}\n'
             f'\t\t\t{setv("pmr_to", "var:" + v("pmr_best_now"))}\n'
             f'\t\t\tset_variable = {v("pmr_switched")}\n'
             f'\t\t\t{log("ABROAD", bk, b, k, extra=best + ";host_best=" + f("pmr_hbest_now"))}\n\t\t}}\n'
             f'\t\telse = {{ pmr_activate_{b} = yes }}\n\t}}\n'
             f'\t{setv("pmr_best", "var:" + v("pmr_best_now"))}\n'
             f'\tpmr_running_{b} = yes\n')

    o.append('\t# A free adoption waits for the game to apply the activation: until it shows, the running\n'
             '\t# recipe is not a switch. Give up after one more tick and keep what runs.\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = {v("pmr_adopting")} }}\n'
             f'\t\tif = {{ limit = {{ var:{v("pmr_run")} = var:{v("pmr_to")} }} remove_variable = {v("pmr_adopting")} }}\n'
             f'\t\telse = {{\n\t\t\t{chg("pmr_adopting", "add", 1)}\n'
             f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:{v("pmr_adopting")} > 1 }}\n'
             f'\t\t\t\tremove_variable = {v("pmr_adopting")}\n'
             f'\t\t\t\t{setv("pmr_to", "var:" + v("pmr_run"))}\n'
             f'\t\t\t\tpmr_reset_levels_{b} = yes\n'
             f'\t\t\t\t{log("ADOPT_FAILED", bk, b, k)}\n\t\t\t}}\n\t\t}}\n\t}}\n')

    o.append('\t# A switch: the building now runs a recipe other than the target. The levels keep the\n'
             '\t# recipes they run; every level not on the new target is now to retool.\n'
             '\t# Abroad, the host\'s marker below the player\'s target is no switch (it cannot follow).\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {v("pmr_adopting")} }} var:{v("pmr_run")} > 0 '
             f'NOT = {{ var:{v("pmr_run")} = var:{v("pmr_to")} }} '
             f'NOT = {{ AND = {{ has_variable = pmr_abroad_{b} var:{v("pmr_run")} < var:{v("pmr_to")} }} }} }}\n'
             f'\t\t{setv("pmr_to", "var:" + v("pmr_run"))}\n'
             f'\t\tset_variable = {v("pmr_switched")}\n\t}}\n')

    o.append(f'\tpmr_sync_levels_{b} = yes\n'
             f'\tpmr_read_gov_{b} = yes\n'
             f'\tpmr_sync_gov_{b} = yes\n'
             f'\tpmr_progress_{b} = yes\n'
             f'\tpmr_mix_{b} = yes\n'
             + (f'\tpmr_works_{b} = yes\n' if works else '') +
             f'\tpmr_blend_{b} = yes\n'
             + ('' if RELEASE else
                '\t# read again after the blend only for the log line (active=), so only in the player\'s states\n'
                f'\tif = {{ limit = {{ owner = {{ is_player = yes }} }} pmr_read_blend_{b} = yes }}\n')
             + (f'\tpmr_opts_{b} = yes\n' if opts else '') +
             f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_need")} > 0 }}\n'
             f'\t\tset_variable = {v("pmr_retooling")}\n'
             f'\t\tpmr_read_earnings_{b} = yes\n'
             f'\t\tpmr_split_retool_{b} = yes\n'
             f'\t\tif = {{ limit = {{ has_variable = {v("pmr_switched")} }} {log("SWITCH", bk, b, k, extra=split)} }}\n'
             f'\t\telse = {{ {log("TICK", bk, b, k, extra=split)} }}\n'
             '\t}\n'
             '\telse = {\n'
             '\t\t# Without the gate nothing is open, queued or standing: the close that removed it removed the last\n'
             '\t\t# site, and no site can be built without it (potential). So a quiet building skips the close.\n'
             f'\t\tif = {{ limit = {{ has_variable = pmr_retool_gate_{b} }} pmr_close_retool_{b} = yes }}\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = {v("pmr_retooling")} }}\n'
             f'\t\t\tremove_variable = {v("pmr_retooling")}\n'
             f'\t\t\t{log("DONE", bk, b, k, extra=done)}\n'
             '\t\t}\n'
             f'\t\telse_if = {{ limit = {{ has_variable = {v("pmr_switched")} }} {log("CANCEL", bk, b, k, extra=mix)} }}\n'
             '\t}\n'
             f'\tif = {{ limit = {{ has_variable = {v("pmr_switched")} }} remove_variable = {v("pmr_switched")} }}\n'
             '}\n\n')
    # Country scope: the country's totals for the Buildings tab row (its recipe bar and upgrade
    # button). Recomputed after each single tick, and once for all building types after the ticks that
    # run state by state (pmr_bulk; see pmr_c_sum_all). The tab also lists buildings abroad that the
    # country or its investors own levels in (Pat's cotton plantations in the East India Company's
    # states, 2026-10-13), so a player's bar counts those buildings too, whole, as their own bars do.
    # Only a player's: it scans every state in the world. The upgrade button's room stays domestic.
    live = f'has_variable = pmr_mix_{b} has_building = {bk} b:{bk} = {{ level >= 1 }}'
    cnames = ['level', 'need'] + [f'lv_{i}' for i in range(1, k + 1)]
    adds = ''.join(f'\t\t\tchange_variable = {{ name = pmr_c_{n}_{b} add = scope:pmr_st.var:pmr_{n}_{b} }}\n'
                   for n in cnames)
    o.append(f'pmr_c_sum_{b} = {{\n'
             '\tsave_temporary_scope_as = pmr_ctry\n'
             + ''.join(f'\tset_variable = {{ name = pmr_c_{n}_{b} value = 0 }}\n'
                       for n in ['level', 'need', 'room_gov'] + [f'lv_{i}' for i in range(1, k + 1)])
             + ''.join(f'\tset_variable = {{ name = pmr_c_{n}_{b} value = 0 }}\n' for n in ('swm', 'sw', 'swd', 'swto', 'now'))
             + f'\tevery_scope_state = {{\n\t\tlimit = {{ {live} }}\n'
             '\t\tsave_temporary_scope_as = pmr_st\n\t\towner = {\n'
             + adds
             + '\t\t}\n'
             # the switching bar (pmr_switch_<b>) of the state with the most levels (Pat, 2026-10-19 01:07Z)
             + f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_swd_{b} var:pmr_level_{b} > scope:pmr_ctry.var:pmr_c_swm_{b} }}\n'
             '\t\t\towner = {\n'
             + ''.join(f'\t\t\t\tset_variable = {{ name = pmr_c_{n}_{b} value = scope:pmr_st.var:{x}_{b} }}\n'
                       for n, x in (('swm', 'pmr_level'), ('sw', 'pmr_sw'), ('swd', 'pmr_swd'), ('swto', 'pmr_swto'),
                                    ('now', 'pmr_best_now')))
             + '\t\t\t}\n\t\t}\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_retool_open_gov_{b} has_variable = pmr_room_gov_{b} }}\n'
             f'\t\t\towner = {{ change_variable = {{ name = pmr_c_room_gov_{b} add = scope:pmr_st.var:pmr_room_gov_{b} }} }}\n'
             '\t\t}\n\t}\n'
             # Buildings abroad: a scan of every state in the world, so it runs with the country-wide sums
             # (pmr_c_abroad, set by pmr_c_sum_every: monthly, on research) and is cached in pmr_cf_*;
             # the sum after a single building's tick adds the cache (performance review, 2026-10-13).
             '\tif = {\n\t\tlimit = { is_player = yes }\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ OR = {{ has_variable = pmr_c_abroad NOT = {{ has_variable = pmr_cf_level_{b} }} }} }}\n'
             + ''.join(f'\t\t\tset_variable = {{ name = pmr_cf_{n}_{b} value = 0 }}\n' for n in cnames)
             + f'\t\t\tevery_state = {{\n\t\t\t\tlimit = {{\n\t\t\t\t\tNOT = {{ owner = scope:pmr_ctry }}\n\t\t\t\t\t{live}\n'
             f'\t\t\t\t\tb:{bk} = {{ levels_owned_by_country = {{ target = scope:pmr_ctry value >= 1 }} }}\n\t\t\t\t}}\n'
             '\t\t\t\tsave_temporary_scope_as = pmr_st\n\t\t\t\tscope:pmr_ctry = {\n'
             + adds.replace('\t\t\t', '\t\t\t\t\t').replace('name = pmr_c_', 'name = pmr_cf_')
             + '\t\t\t\t}\n\t\t\t}\n\t\t}\n'
             + ''.join(f'\t\tchange_variable = {{ name = pmr_c_{n}_{b} add = var:pmr_cf_{n}_{b} }}\n' for n in cnames)
             + '\t}\n'
             + ''.join(f'\tset_variable = {{ name = pmr_c_sh_{i}_{b} value = 0 }}\n' for i in range(1, k + 1))
             + f'\tif = {{\n\t\tlimit = {{ var:pmr_c_level_{b} > 0 }}\n'
             + ''.join(f'\t\tset_variable = {{ name = pmr_c_sh_{i}_{b} value = var:pmr_c_lv_{i}_{b} }}\n'
                       f'\t\tchange_variable = {{ name = pmr_c_sh_{i}_{b} divide = var:pmr_c_level_{b} }}\n'
                       for i in range(1, k + 1))
             + '\t}\n'
             # the split: each plain recipe's share across the country, for the Buildings tab's bar
             + ''.join(f'\tset_variable = {{ name = pmr_c_rs_{j}_{b} value = 0 }}\n'
                       + ''.join(f'\tchange_variable = {{ name = pmr_c_rs_{j}_{b} add = var:pmr_c_sh_{i}_{b} }}\n' for i in idxs)
                       for j, idxs, grp in (bm if split else []) if grp == 'recipe')
             + f'\tif = {{ limit = {{ var:pmr_c_need_{b} > 0 }} set_variable = {{ name = pmr_c_retooling_{b} value = 1 }} }}\n'
             f'\telse = {{ set_variable = {{ name = pmr_c_retooling_{b} value = 0 }} }}\n'
             '}\n\n')

    # The guarded entry point, after the body it calls (every scripted effect here is defined before use).
    # pmr_runs_<b> counts the day's outermost ticks (pmr_rday_<b> marks the day); past TICK_TRIP the
    # building waits for the next day (pmr_trip_<b>), so a loop through the game's own hooks ends.
    o.append(f'pmr_tick_{b} = {{\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = pmr_busy_{b} }} NOT = {{ has_variable = pmr_trip_{b} }} }}\n'
             f'\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_rday_{b} }} }} '
             f'set_variable = {{ name = pmr_rday_{b} value = yes days = 1 }} set_variable = {{ name = pmr_runs_{b} value = 0 }} }}\n'
             f'\t\tchange_variable = {{ name = pmr_runs_{b} add = 1 }}\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_runs_{b} > {TICK_TRIP} }}\n'
             f'\t\t\tset_variable = {{ name = pmr_trip_{b} value = yes days = 1 }}\n'
             f'\t\t\t{flush_log("TRIP", bk, f";runs={TICK_TRIP + 1}")}\n\t\t}}\n'
             f'\t\telse = {{\n'
             f'\t\t\tset_variable = {{ name = pmr_busy_{b} value = yes days = 1 }}\n'
             '\t\t\tset_variable = { name = pmr_in_tick value = yes days = 1 }\n'
             f'\t\t\tpmr_tick_body_{b} = yes\n'
             '\t\t\tremove_variable = pmr_in_tick\n'
             f'\t\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_bulk }} owner = {{ is_player = yes }} }} owner = {{ pmr_c_sum_{b} = yes }} }}\n'
             f'\t\t\tremove_variable = pmr_busy_{b}\n\t\t}}\n\t}}\n}}\n\n')

    # The government upgrade button (pmr_gov_retool_<b>_sgui): queue every government retool level
    # the building still needs, as if the player had built them one by one, then tick so the room,
    # and with it the button, drops to nothing.
    o.append(f'pmr_queue_gov_{b} = {{\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_retool_open_gov_{b} NOT = {{ has_variable = pmr_abroad_{b} }} }}\n'
             f'\t\t{setv("pmr_q", "var:" + v("pmr_room_gov"))}\n'
             f'\t\t{log("GOV_QUEUE", bk, b, k, extra=";queueing=" + f("pmr_q"))}\n'
             f'\t\twhile = {{\n\t\t\tlimit = {{ var:{v("pmr_q")} > 0 }}\n'
             f'\t\t\tstart_building_construction = {rbg}\n'
             f'\t\t\t{chg("pmr_q", "subtract", 1)}\n\t\t}}\n'
             f'\t\tremove_variable = {v("pmr_q")}\n'
             f'\t\tpmr_tick_{b} = yes\n\t}}\n}}\n\n')
    return ''.join(o)


def profit_effect(bk, b, recipes, econ, goods_cost, active, reach, setv, v, pair=None):
    """State scope: pmr_profit_<b>, the profit calculation, and pmr_best_<b>, which makes its pick the target.
    The interface Company Culture reads (fixed 2026-10-18; the best-methods windows), recipe index i as everywhere:
      pmr_rg_<i>_<b>     goods margin per level per week at the state's prices (outputs minus inputs, GBP)
      pmr_rw_<i>_<b>     wages per level per week: wage units x pmr_wage / 10,000
      pmr_rm_<i>_<b>     pmr_rg - pmr_rw, the profit per level per week
      pmr_rav_<i>_<b>    1 while recipe i can become the target here (pmr_newest_<b>'s rule)
      pmr_rveto_<i>_<b>  1 while recipe i needs more of an input than the current pick and its price is at the cap
      pmr_pbest_<b>      the pick: best pmr_rm of the runnable, unvetoed recipes, sticky (PROFIT_STICK_*); 0 if none
      pmr_prm_<b>        the pick's pmr_rm (the panel's pick row)
    Throughput and the building's modifiers are left out: they scale every recipe alike.
    Pat, 2026-10-18 17:14Z: the pick decides new builds and retooling, and must not cost the game speed. So the
    calculation runs only when pmr_best_<b> finds a reason: no pick yet, the newest runnable recipe changed
    (research, electricity, the player's know-how abroad), a new building, its first monthly pulse (the setup pass
    runs before the market has prices), or its re-check timer ran out
    (pmr_pchk_<b>, PROFIT_RECHECK_DAYS, spread over PROFIT_RECHECK_SPREAD so states don't all check on one day).
    Every other tick reads the cached pick."""
    k = len(recipes)
    newest = (f'\tpmr_newest_{b} = yes\n')
    if not econ or not PROFIT_TARGET:
        return f'pmr_best_{b} = {{\n{newest}\t{setv("pmr_best_now", "var:" + v("pmr_new_now"))}\n}}\n\n'
    xv = lambda name, i: f'{name}_{i}_{b}'   # noqa: E731
    top = fmt(1 + PRICE_LADDER[-1] / 100)
    goods = sorted({g for gd, _ in list(econ) + list((pair or {}).get('econ', {}).values())
                    for g in gd if goods_cost.get(g)})
    o = [f'pmr_profit_{b} = {{\n'
         '\t# a good\'s price is read once a day per state (pmr_pxd_<good>), as for the trade-offs. During game setup\n'
         '\t# (pmr_setup) the market has no prices yet, so the base price stands in until the first monthly pulse.\n'
         + ''.join(f'\tif = {{ limit = {{ has_global_variable = pmr_setup }} set_variable = {{ name = pmr_px_{g} value = 1 }} }}\n'
                   f'\telse_if = {{ limit = {{ NOT = {{ has_variable = pmr_pxd_{g} }} }} pmr_price_{g} = yes '
                   f'set_variable = {{ name = pmr_pxd_{g} value = yes days = 1 }} }}\n' for g in goods)
         + f'\tset_variable = {{ name = pmr_wage value = {AUTOMATION_WAGE} }}\n']
    for i, (gd, wu) in enumerate(econ, 1):
        o.append(f'\tset_variable = {{ name = {xv("pmr_rg", i)} value = 0 }}\n')
        for g, q in sorted(gd.items()):
            if goods_cost.get(g):
                o.append(f'\tset_variable = {{ name = pmr_t value = var:pmr_px_{g} }}\n'
                         f'\tchange_variable = {{ name = pmr_t multiply = {fmt(q * goods_cost[g])} }}\n'
                         f'\tchange_variable = {{ name = {xv("pmr_rg", i)} add = var:pmr_t }}\n')
        o.append(f'\tset_variable = {{ name = {xv("pmr_rw", i)} value = var:pmr_wage }}\n'
                 f'\tchange_variable = {{ name = {xv("pmr_rw", i)} multiply = {fmt(wu / 10000)} }}\n'
                 f'\tset_variable = {{ name = {xv("pmr_rm", i)} value = var:{xv("pmr_rg", i)} }}\n'
                 f'\tchange_variable = {{ name = {xv("pmr_rm", i)} subtract = var:{xv("pmr_rw", i)} }}\n'
                 f'\tset_variable = {{ name = {xv("pmr_rav", i)} value = 0 }}\n'
                 f'\tif = {{ limit = {{ OR = {{ {active(recipes[i - 1])} {reach(i, True)} }} }} '
                 f'set_variable = {{ name = {xv("pmr_rav", i)} value = 1 }} }}\n')
    # the current pick: the last one, else PMR's target, else the recipe the building runs, else the oldest
    o.append(f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {v("pmr_pbest")} }} }}\n\t\t{setv("pmr_pbest", 1)}\n'
             f'\t\tif = {{ limit = {{ has_variable = {v("pmr_to")} var:{v("pmr_to")} > 0 }} '
             f'{setv("pmr_pbest", "var:" + v("pmr_to"))} }}\n'
             + ''.join(f'\t\telse_if = {{ limit = {{ {active(r)} }} {setv("pmr_pbest", i)} }}\n'
                       for i, r in enumerate(recipes, 1) if i > 1)
             + '\t}\n')
    # the veto: an input recipe i needs more of than the pick c, at the price cap. One branch per pick c, so a run
    # tests about k/2 picks and then k recipes, not k x (k-1) (perf review 3, S1)
    inputs = [{g: -q for g, q in gd.items() if q < 0 and goods_cost.get(g)} for gd, _ in econ]
    o += [f'\tset_variable = {{ name = {xv("pmr_rveto", i)} value = 0 }}\n' for i in range(1, k + 1)]

    def capped(gs, i):
        return (f'\t\tif = {{ limit = {{ OR = {{ ' + ' '.join(f'var:pmr_px_{g} >= {top}' for g in gs)
                + f' }} }} set_variable = {{ name = {xv("pmr_rveto", i)} value = 1 }} }}\n')
    first = True
    for c in range(1, k + 1):
        body = ''
        for i in range(1, k + 1):
            more = [g for g, q in sorted(inputs[i - 1].items()) if q > inputs[c - 1].get(g, 0) + 1e-9]
            if c != i and more:
                body += capped(more, i)
        # the pick itself, when it needs more of a capped input than an older recipe
        own = [g for g, q in sorted(inputs[c - 1].items())
               if any(q > inputs[j - 1].get(g, 0) + 1e-9 for j in range(1, c))]
        if own:
            body += capped(own, c)
        if body:
            o.append(f'\t{"if" if first else "else_if"} = {{\n\t\tlimit = {{ var:{v("pmr_pbest")} = {c} }}\n{body}\t}}\n')
            first = False
    # the pick, against the current one's hurdles (pmr_hu newer, pmr_hd older); a pick that can't run sets none
    o.append('\tset_variable = { name = pmr_hu value = 0 }\n\tset_variable = { name = pmr_hd value = 0 }\n'
             '\tset_variable = { name = pmr_pk value = 0 }\n\tset_variable = { name = pmr_pv value = -1000000 }\n')
    for c in range(1, k + 1):
        o.append(f'\t{"if" if c == 1 else "else_if"} = {{ limit = {{ var:{v("pmr_pbest")} = {c} var:{xv("pmr_rav", c)} = 1 }} '
                 f'set_variable = {{ name = pmr_hu value = var:{xv("pmr_rm", c)} }} }}\n')
    o.append('\tif = { limit = { var:pmr_hu < 0 } change_variable = { name = pmr_hu multiply = -1 } }\n'
             '\tset_variable = { name = pmr_hd value = var:pmr_hu }\n'
             f'\tchange_variable = {{ name = pmr_hu multiply = {fmt(PROFIT_STICK_UP)} }}\n'
             f'\tchange_variable = {{ name = pmr_hd multiply = {fmt(PROFIT_STICK_DOWN)} }}\n')
    for i in range(1, k + 1):
        o.append(f'\tif = {{\n\t\tlimit = {{ var:{xv("pmr_rav", i)} = 1 var:{xv("pmr_rveto", i)} = 0 }}\n'
                 f'\t\tset_variable = {{ name = pmr_t value = var:{xv("pmr_rm", i)} }}\n'
                 f'\t\tif = {{ limit = {{ var:{v("pmr_pbest")} < {i} }} change_variable = {{ name = pmr_t subtract = var:pmr_hu }} }}\n'
                 f'\t\telse_if = {{ limit = {{ var:{v("pmr_pbest")} > {i} }} change_variable = {{ name = pmr_t subtract = var:pmr_hd }} }}\n'
                 f'\t\tif = {{ limit = {{ var:pmr_t > var:pmr_pv }} set_variable = {{ name = pmr_pv value = var:pmr_t }} '
                 f'set_variable = {{ name = pmr_pk value = {i} }} }}\n\t}}\n')
    o.append(f'\t{setv("pmr_pbest", "var:pmr_pk")}\n\t{setv("pmr_prm", 0)}\n'
             + ''.join(f'\tif = {{ limit = {{ var:pmr_pk = {i} }} {setv("pmr_prm", "var:" + xv("pmr_rm", i))} }}\n'
                       for i in range(1, k + 1))
             + vanilla_score(bk, b, econ, goods_cost, setv, v)
             + pair_effect(bk, b, recipes, pair, goods_cost, active, setv, v) + '}\n\n')

    # pmr_best_<b>: the target candidate every tick reads (pmr_best_now), the cached pick
    def var(name, d=0):
        return f"[THIS.Var('{name}').GetValue|{d}]"
    per = lambda name, d=0: '/'.join(var(xv(name, i), d) for i in range(1, k + 1))   # noqa: E731
    line = (f'PMR;rec=PROFIT;date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting];'
            f"building={bk};to={var(v('pmr_to'))};newest={var(v('pmr_new_now'))};pick={var(v('pmr_pbest'))};"
            f"wage={var('pmr_wage')};rm={per('pmr_rm', 1)};rg={per('pmr_rg', 1)};rw={per('pmr_rw', 1)};"
            f"can={per('pmr_rav')};veto={per('pmr_rveto')};"
            + (f"pair={var(v('pmr_cbi'))}x{var(v('pmr_cba'))};"
               + ('' if pair.get('split') else
                  'cp=' + '/'.join(var(f'pmr_cp_{i}_{a}_{b}', 1) for i, a in sorted(pair['econ'])) + ';') if pair else '')
            + 'px='
            + ','.join(f"{g}:{var('pmr_px_' + g, 2)}" for g in goods))
    spread = ' '.join(f'1 = {{ set_variable = {{ name = pmr_pchk_{b} value = yes days = {d} }} }}'
                      for d in range(PROFIT_RECHECK_DAYS - PROFIT_RECHECK_SPREAD // 2,
                                     PROFIT_RECHECK_DAYS + PROFIT_RECHECK_SPREAD // 2 + 1, PROFIT_RECHECK_SPREAD // 6))
    # The first calculation runs during game setup, before the market has real prices (q23: steel read 0.25-0.35
    # of base in every French state, so Blister Steel showed -£2,990 a level while the mill made +£1.57K; q31: the
    # Investments tab showed those figures on 1 January, Pat 23:22Z). It uses base prices (pmr_setup) and is
    # not trusted: every building's pick is computed once more on its first monthly pulse (pmr_pmkt_<b>), which
    # also gives the log every player building's pick on its own (Pat, 17:59Z), then the yearly re-check runs.
    first = f'has_variable = pmr_month NOT = {{ has_variable = pmr_pmkt_{b} }}'
    o.append(f'pmr_best_{b} = {{\n{newest}'
             f'\tif = {{\n\t\tlimit = {{ OR = {{ NOT = {{ has_variable = pmr_pchk_{b} }} '
             f'NOT = {{ has_variable = {v("pmr_new")} }} NOT = {{ var:{v("pmr_new")} = var:{v("pmr_new_now")} }} '
             f'has_variable = {v("pmr_new_build")} AND = {{ {first} }} }} }}\n'
             f'\t\tpmr_profit_{b} = yes\n\t\t{setv("pmr_new", "var:" + v("pmr_new_now"))}\n'
             f'\t\tif = {{ limit = {{ has_variable = pmr_pchk_{b} }} remove_variable = pmr_pchk_{b} }}\n'
             f'\t\trandom_list = {{ {spread} }}\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ {first} }}\n\t\t\tset_variable = pmr_pmkt_{b}\n'
             '\t\t\tset_variable = pmr_sw_inst  # the first pick at market prices stands at once (pmr_switch)\n'
             f'\t\t\tif = {{ limit = {{ owner = {{ is_player = yes }} }} debug_log = "{line};why=first_month" }}\n\t\t}}\n'
             f'\t\telse_if = {{ limit = {{ owner = {{ is_player = yes }} }} debug_log = "{line};why=recompute" }}\n\t}}\n'
             + f'\tpmr_switch_{b} = yes\n}}\n\n')
    return switch_effect(b, bk, k, setv, v, var) + ''.join(o)


def switch_effect(b, bk, k, setv, v, var):
    """State scope, after each pick: pmr_switch_<b> (Pat, 2026-10-19 01:07Z: "a progress bar ... towards setting a new
    PM default ... if it wants to downgrade because goods are too expensive it has to also fill up the same bar in
    red; it should take 6 months"). The pick (pmr_pbest_<b>) becomes the default new levels and retooling follow
    (pmr_best_now_<b>) once it has stood for SWITCH_MONTHS monthly pulses:
      pmr_swto_<b>  the pick the bar fills toward (0: none)     pmr_sw_<b>   monthly pulses so far
      pmr_swd_<b>   1 toward a newer recipe (green), -1 an older one (red), 0 none
    A pick that changes starts the bar again; one back on the default empties it. The default takes the pick at once
    the first time, at the building's first pick at market prices (pmr_sw_inst), and when the default can no longer
    run here."""
    now, pick = v('pmr_best_now'), v('pmr_pbest')
    clear = f'\t\t{setv("pmr_sw", 0)}\n\t\t{setv("pmr_swd", 0)}\n\t\t{setv("pmr_swto", 0)}\n'
    take = (f'\t\tif = {{ limit = {{ var:{pick} > 0 }} {setv("pmr_best_now", "var:" + pick)} }}\n'
            f'\t\telse_if = {{ limit = {{ NOT = {{ has_variable = {now} }} }} {setv("pmr_best_now", "var:" + v("pmr_new_now"))} }}\n'
            + clear)
    dead = ' '.join(f'AND = {{ var:{now} = {i} var:pmr_rav_{i}_{b} = 0 }}' for i in range(1, k + 1))
    where = ('date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
             f'state=[THIS.GetState.GetNameNoFormatting];building={bk}')
    return (f'pmr_switch_{b} = {{\n'
            f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {now} }} }}\n' + take + '\t}\n'
            f'\telse_if = {{\n\t\tlimit = {{ OR = {{ has_variable = pmr_sw_inst {dead} }} }}\n' + take + '\t}\n'
            f'\telse_if = {{\n\t\tlimit = {{ OR = {{ var:{pick} = 0 var:{pick} = var:{now} }} }}\n' + clear + '\t}\n'
            '\telse = {\n'
            f'\t\tif = {{\n\t\t\tlimit = {{ NOT = {{ var:{v("pmr_swto")} = var:{pick} }} }}\n'
            f'\t\t\t{setv("pmr_swto", "var:" + pick)}\n\t\t\t{setv("pmr_sw", 0)}\n'
            f'\t\t\tif = {{ limit = {{ var:{pick} > var:{now} }} {setv("pmr_swd", 1)} }}\n'
            f'\t\t\telse = {{ {setv("pmr_swd", -1)} }}\n'
            f'\t\t\tif = {{ limit = {{ owner = {{ is_player = yes }} }} debug_log = "PMR;rec=SWITCH_START;{where};'
            f"default={var(now)};to={var(pick)};dir={var(v('pmr_swd'))}\" }}\n\t\t}}\n"
            f'\t\tif = {{ limit = {{ has_variable = pmr_month }} change_variable = {{ name = {v("pmr_sw")} add = 1 }} }}\n'
            f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_sw")} >= {SWITCH_MONTHS} }}\n'
            f'\t\t\tif = {{ limit = {{ owner = {{ is_player = yes }} }} debug_log = "PMR;rec=DEFAULT;{where};'
            f"from={var(now)};to={var(pick)};dir={var(v('pmr_swd'))};months={var(v('pmr_sw'))}\" }}\n"
            f'\t\t\t{setv("pmr_best_now", "var:" + pick)}\n'
            + clear.replace('\t\t', '\t\t\t') + '\t\t}\n\t}\n'
            '\tif = { limit = { has_variable = pmr_sw_inst } remove_variable = pmr_sw_inst }\n}\n\n')


def vanilla_score(bk, b, econ, goods_cost, setv, v):
    """Inside pmr_profit_<b>, after the pick: pmr_pvs_<b>, what vanilla's investment pool would add to the type's
    ai_value for a new level of the pick at this state's prices (VANILLA_*_W): its profit per level a week
    (pmr_prm_<b>) / the target's employees per level x 7500 (x 10000 for a loss), plus its outputs at base value
    x 0.3125. 0 without a pick."""
    emps = TARGET_EMPLOYEES.get(bk, [])
    o = [f'\t# vanilla\'s profit and output terms for the pick (vanilla_score)\n\t{setv("pmr_pvs", 0)}\n']
    for i, (gd, _wu) in enumerate(econ, 1):
        e = max(emps[i - 1] if i <= len(emps) else 0, 1)
        out = sum(q * goods_cost[g] for g, q in gd.items() if q > 0 and goods_cost.get(g))
        o.append(f'\tif = {{\n\t\tlimit = {{ var:pmr_pk = {i} }}\n\t\t{setv("pmr_pvs", "var:" + v("pmr_prm"))}\n'
                 f'\t\tif = {{ limit = {{ var:{v("pmr_pvs")} > 0 }} '
                 f'change_variable = {{ name = {v("pmr_pvs")} multiply = {fmt(VANILLA_PROFIT_W / e)} }} }}\n'
                 f'\t\telse = {{ change_variable = {{ name = {v("pmr_pvs")} multiply = {fmt(VANILLA_DEFICIT_W / e)} }} }}\n'
                 f'\t\tchange_variable = {{ name = {v("pmr_pvs")} add = {fmt(out * VANILLA_OUTPUT_W)} }}\n\t}}\n')
    return ''.join(o)


def pair_effect(bk, b, recipes, pair, goods_cost, active, setv, v):
    """Inside pmr_profit_<b>: every plain recipe with every automation option (pairs()), at the same prices and wage.
    The pairs' interface (the Methods view; a = 1 is no automation, options in vanilla's order):
      pmr_cp_<i>_<a>_<b>   the pair's profit per level a week, as pmr_rm
      pmr_cav_<i>_<a>_<b>  1 while the pair could run here: recipe i's marker can activate (or runs), the owner has
                           the automation's technologies, and a pair that needs electricity has it
      pmr_cbi_<b>, pmr_cba_<b>  the most profitable runnable pair (0, 0 if none); no stickiness, no veto: it is read,
                           not retooled to (the fold still decides what levels run)"""
    if not pair:
        return ''
    if pair.get('split'):
        # The pairs are the retool targets (SPLIT_AUTOMATION): the grid shows the pick's own figures, and its gold
        # cell is the pick. A pair that can't run or is skipped at the price cap reads as unavailable.
        o = [f'\t# recipe + automation pairs: the retool targets\' figures (pair_effect)\n'
             f'\t{setv("pmr_cbi", 0)}\n\t{setv("pmr_cba", 0)}\n']
        for (i, a), x in sorted(pair['index'].items()):
            cp, cav = f'pmr_cp_{i}_{a}_{b}', f'pmr_cav_{i}_{a}_{b}'
            o.append(f'\tset_variable = {{ name = {cp} value = var:pmr_rm_{x}_{b} }}\n'
                     f'\tset_variable = {{ name = {cav} value = 0 }}\n'
                     f'\tif = {{ limit = {{ var:pmr_rav_{x}_{b} = 1 var:pmr_rveto_{x}_{b} = 0 }} '
                     f'set_variable = {{ name = {cav} value = 1 }} }}\n'
                     f'\tif = {{ limit = {{ var:{v("pmr_pbest")} = {x} }} {setv("pmr_cbi", i)} {setv("pmr_cba", a)} }}\n')
        return ''.join(o)
    o = [f'\t# recipe + automation pairs (pair_effect)\n\t{setv("pmr_cbi", 0)}\n\t{setv("pmr_cba", 0)}\n'
         '\tset_variable = { name = pmr_pv value = -1000000 }\n']
    for (i, a), (gd, wu) in sorted(pair['econ'].items()):
        r, cp, cav = recipes[i - 1], f'pmr_cp_{i}_{a}_{b}', f'pmr_cav_{i}_{a}_{b}'
        o.append(f'\tset_variable = {{ name = {cp} value = var:pmr_wage }}\n'
                 f'\tchange_variable = {{ name = {cp} multiply = {fmt(-wu / 10000)} }}\n')
        for g, q in sorted(gd.items()):
            if goods_cost.get(g):
                o.append(f'\tset_variable = {{ name = pmr_t value = var:pmr_px_{g} }}\n'
                         f'\tchange_variable = {{ name = pmr_t multiply = {fmt(q * goods_cost[g])} }}\n'
                         f'\tchange_variable = {{ name = {cp} add = var:pmr_t }}\n')
        techs = pair['techs'][a - 1]
        cond = (f'OR = {{ {active(r)} can_activate_production_method = {{ building_type = {bk} production_method = {r.key} }} }}'
                + (' owner = { ' + ' '.join(f'has_technology_researched = {t}' for t in techs) + ' }' if techs else '')
                + (' var:pmr_elec = 1' if pair['elec'][(i, a)] else ''))
        o.append(f'\tset_variable = {{ name = {cav} value = 0 }}\n'
                 f'\tif = {{\n\t\tlimit = {{ {cond} }}\n\t\tset_variable = {{ name = {cav} value = 1 }}\n'
                 f'\t\tif = {{ limit = {{ var:{cp} > var:pmr_pv }} set_variable = {{ name = pmr_pv value = var:{cp} }} '
                 f'{setv("pmr_cbi", i)} {setv("pmr_cba", a)} }}\n\t}}\n')
    return ''.join(o)


def moved(b):
    """the research changed the building's target candidate (pmr_best_<b> has just run)"""
    if PROFIT_TARGET:
        return f'NOT = {{ var:pmr_best_now_{b} = var:pmr_best_{b} }}'
    return f'var:pmr_best_now_{b} > var:pmr_best_{b}'


def shared_effects(price_goods=()):
    return ''.join(price_effect(g) for g in price_goods) + '''# State scope. pmr_elec: 1 while the state produces electricity (a local good, so only the state's
# own power plants count). pmr_pool: the owner's investment pool by order of magnitude, and pmr_unemp:
# the state's unemployment rate in % (lower bound of 1/2/5/10/20), for the log. The investment pool
# scores a building x0.25 in a state short of workers, which can cost a retool site with a crew a pick.
pmr_read_elec = {
	if = {
		limit = { exists = sg:electricity sg:electricity = { state_goods_production > 0 } }
		set_variable = { name = pmr_elec value = 1 }
	}
	else = { set_variable = { name = pmr_elec value = 0 } }
''' + ('}\n\n' if RELEASE else '''	# pool and unemployment are read only for the log, so only in the player's states (not in a release build)
	if = {
		limit = { owner = { is_player = yes } }
		set_variable = { name = pmr_pool value = 0 }
''' + ''.join(f'\t\t{"if" if j == 0 else "else_if"} = {{ limit = {{ owner = {{ investment_pool >= {x} }} }} set_variable = {{ name = pmr_pool value = {x} }} }}\n'
              for j, x in enumerate((100000, 10000, 1000, 100))) +
        '\t\tset_variable = { name = pmr_unemp value = 0 }\n' +
        ''.join(f'\t\t{"if" if j == 0 else "else_if"} = {{ limit = {{ state_unemployment_rate > {fmt(x / 100)} }} set_variable = {{ name = pmr_unemp value = {x} }} }}\n'
                for j, x in enumerate((20, 10, 5, 2, 1))) + '\t}\n}\n\n')


def dispatch_effects(buildings):
    def live(bk):
        return f'has_building = {bk} b:{bk} = {{ level >= 1 }}'
    o = ['# ===== dispatch\n\n'
         '# Building scope (on_production_method_changed): tick this building through its state.\n'
         'pmr_tick_building = {\n']
    for i, bk in enumerate(buildings):
        kw = 'if' if i == 0 else 'else_if'
        o.append(f'\t{kw} = {{ limit = {{ is_building_type = {bk} level >= 1 }} state = {{ pmr_tick_{short(bk)} = yes }} }}\n')
    o.append('}\n\n'
             '# Building scope (on_building_built). A PMR building not seen before was just constructed, so\n'
             '# it starts on the newest recipe at no cost.\n'
             'pmr_built_building = {\n')
    for i, bk in enumerate(buildings):
        b = short(bk)
        kw = 'if' if i == 0 else 'else_if'
        o.append(f'\t{kw} = {{\n\t\tlimit = {{ is_building_type = {bk} level >= 1 }}\n\t\tstate = {{\n'
                 f'\t\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_mix_{b} }} }} set_variable = pmr_new_build_{b} }}\n'
                 f'\t\t\tpmr_tick_{b} = yes\n'
                 f'\t\t\tif = {{ limit = {{ has_variable = pmr_new_build_{b} }} remove_variable = pmr_new_build_{b} }}\n'
                 '\t\t}\n\t}\n')
    o.append('}\n\n'
             '# Building scope, for a retool pseudo-building that just completed a level: tick its parent.\n'
             'pmr_tick_parent_of_retool = {\n')
    for i, bk in enumerate(buildings):
        b = short(bk)
        kw = 'if' if i == 0 else 'else_if'
        types = priv_slots(b) + [f'building_pmr_retool_gov_{b}', f'building_pmr_retool_gova_{b}']
        o.append(f'\t{kw} = {{\n\t\tlimit = {{ OR = {{ ' + ' '.join(f'is_building_type = {t}' for t in types) + ' } }\n'
                 f'\t\tstate = {{\n\t\t\t{flush_log("RETOOL_LEVEL", bk)}\n'
                 f'\t\t\tif = {{ limit = {{ {live(bk)} }} pmr_tick_{b} = yes }}\n\t\t}}\n\t}}\n')
    o.append('}\n\n'
             '# State scope: tick every PMR building in the state. Run state by state over a country (monthly, on\n'
             '# research, at game start), so the country totals wait for pmr_c_sum_all once the states are done.\n'
             'pmr_state_tick = {\n\tset_variable = pmr_bulk\n'
             '\t# electricity once for every building of the state (pmr_tick_body_<b> skips its own read)\n'
             '\tpmr_read_elec = yes\n\tset_variable = pmr_elec_read\n')
    for bk in buildings:
        o.append(f'\tif = {{ limit = {{ {live(bk)} }} pmr_tick_{short(bk)} = yes }}\n')
    o.append('\tremove_variable = pmr_elec_read\n\tremove_variable = pmr_bulk\n}\n\n'
             '# State scope (on_acquired_technology): tick only the buildings whose best recipe the research\n'
             '# changed, and any not seen yet. The rest wait for the month; until then a newly unlocked\n'
             '# trade-off shows as unavailable on the panel, whose shares move only monthly anyway.\n'
             'pmr_state_research = {\n\tset_variable = pmr_bulk\n\tpmr_read_elec = yes\n\tset_variable = pmr_elec_read\n')
    for bk in buildings:
        b = short(bk)
        o.append(f'\tif = {{\n\t\tlimit = {{ {live(bk)} }}\n'
                 f'\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_mix_{b} }} }} pmr_tick_{b} = yes }}\n'
                 f'\t\telse = {{\n\t\t\tpmr_best_{b} = yes\n'
                 f'\t\t\tif = {{ limit = {{ {moved(b)} }} pmr_tick_{b} = yes }}\n'
                 '\t\t}\n\t}\n')
    o.append('\tremove_variable = pmr_elec_read\n\tremove_variable = pmr_bulk\n}\n\n'
             '# State scope, another country\'s state where the player owns levels (pmr_abroad_any), when the\n'
             '# player researches: the same, for the buildings the player owns levels in.\n'
             'pmr_state_research_abroad = {\n\tset_variable = pmr_bulk\n\tpmr_read_elec = yes\n\tset_variable = pmr_elec_read\n')
    for bk in buildings:
        b = short(bk)
        o.append(f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_abroad_{b} has_variable = pmr_mix_{b} {live(bk)} }}\n'
                 f'\t\tpmr_best_{b} = yes\n'
                 f'\t\tif = {{ limit = {{ {moved(b)} }} pmr_tick_{b} = yes }}\n'
                 '\t}\n')
    o.append('\tremove_variable = pmr_elec_read\n\tremove_variable = pmr_bulk\n}\n\n'
             '# Country scope: the country\'s totals for every PMR building type (Buildings tab rows).\n'
             'pmr_c_sum_every = {\n\tset_variable = pmr_c_abroad\n')
    for bk in buildings:
        o.append(f'\tpmr_c_sum_{short(bk)} = yes\n')
    o.append('\tremove_variable = pmr_c_abroad\n}\n\n'
             '# The same for a player\'s country only (monthly, on research).\n'
             'pmr_c_sum_all = {\n\tif = {\n\t\tlimit = { is_player = yes }\n'
             '\t\tpmr_c_sum_every = yes\n'
             '\t\tdebug_log = "PMR;rec=CSUM;date=[TimeKeeper.GetCurrentDate.GetString]"\n'
             '\t}\n}\n')
    return ''.join(o)


# State scope: the state produces electricity (as pmr_read_elec reads it, without the variable).
ELEC_MADE = 'exists = sg:electricity sg:electricity = { state_goods_production > 0 }'
AUTO_TRIP = 3   # AUTO_BEST switches one building may make from method changes in a day before it waits for the next


def auto_best_effects(auto):
    """AUTO_BEST: per building type, pmr_auto_<b> (state scope) activates each listed group's best method
    the state can activate, unless it already runs. activate_production_method runs on_production_method_changed
    inside itself, so pmr_auto_busy on the state keeps that from running these again. A method change from
    anything else (the AI, the game replacing a method it no longer allows) runs it at most AUTO_TRIP times a
    day per building (pmr_auto_runs_<b>): should the game and PMR disagree on a method, each would otherwise
    switch it back the moment the other did, with no end (written after Pat's freeze of 2026-10-13, cause
    unproven). Past that it logs AUTO_TRIP, flushed. A technology the method needs is asked of the owner as
    well as through can_activate_production_method, which on 21 February 1836 allowed Great Britain
    Switchboards (central_planning, era 4) in every administration."""
    o = ['# ===== best methods (AUTO_BEST; Pat, 2026-10-13 17:00Z: no retooling, always the best method)\n\n']
    for bk, gl in auto.items():
        o.append(f'# State scope: {bk} on its best methods, newest first.\npmr_auto_{short(bk)} = {{\n')
        for g, order, by_law, techs, elec in gl:
            o.append(f'\t# {g}' + (', set by laws' if by_law else '') + '\n')
            for j, p in enumerate(order):
                spec = f'building_type = {bk} production_method = {p}'
                # A technology ladder asks "running or can run", as pmr_best_<b> does, so a running method is
                # never stepped down from; a group the laws decide asks only which one the laws allow.
                can = f'can_activate_production_method = {{ {spec} }}'
                if techs[p]:
                    can = (f'AND = {{ {can} owner = {{ '
                           + ' '.join(f'has_technology_researched = {x}' for x in techs[p]) + ' } }')
                # electricity only while the state makes it, running or not: else the next method takes over
                pre = f'{ELEC_MADE} ' if p in elec else ''
                o.append(f'\t{"if" if j == 0 else "else_if"} = {{\n'
                         + (f'\t\tlimit = {{ {pre}{can} }}\n' if by_law else
                            f'\t\tlimit = {{ {pre}OR = {{ is_production_method_active = {{ {spec} }} {can} }} }}\n')
                         + f'\t\tif = {{\n\t\t\tlimit = {{ NOT = {{ is_production_method_active = {{ {spec} }} }} }}\n'
                         f'\t\t\tactivate_production_method = {{ {spec} }}\n'
                         f'\t\t\tif = {{ limit = {{ owner = {{ is_player = yes }} }} {flush_log("AUTO", bk, ";method=" + p)} }}\n'
                         '\t\t}\n\t}\n')
        o.append('}\n\n')
    o.append('# State scope (monthly, on research, at game start): every such building of the state.\n'
             'pmr_auto_best = {\n\tset_variable = pmr_auto_busy\n')
    for bk in auto:
        o.append(f'\tif = {{ limit = {{ has_building = {bk} b:{bk} = {{ level >= 1 }} }} pmr_auto_{short(bk)} = yes }}\n')
    o.append('\tremove_variable = pmr_auto_busy\n}\n\n'
             '# Building scope (on_production_method_changed, on_building_built): the building, if it is such a type,\n'
             f'# at most {AUTO_TRIP} times a day.\n'
             'pmr_auto_building = {\n')
    for j, bk in enumerate(auto):
        b = short(bk)
        o.append(f'\t{"if" if j == 0 else "else_if"} = {{\n\t\tlimit = {{ is_building_type = {bk} level >= 1 }}\n'
                 '\t\tstate = {\n'
                 f'\t\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_auto_day_{b} }} }} '
                 f'set_variable = {{ name = pmr_auto_day_{b} value = yes days = 1 }} set_variable = {{ name = pmr_auto_runs_{b} value = 0 }} }}\n'
                 f'\t\t\tchange_variable = {{ name = pmr_auto_runs_{b} add = 1 }}\n'
                 f'\t\t\tif = {{ limit = {{ var:pmr_auto_runs_{b} <= {AUTO_TRIP} }} '
                 f'set_variable = pmr_auto_busy pmr_auto_{b} = yes remove_variable = pmr_auto_busy }}\n'
                 f'\t\t\telse_if = {{ limit = {{ var:pmr_auto_runs_{b} = {AUTO_TRIP + 1} }} {flush_log("AUTO_TRIP", bk)} }}\n'
                 '\t\t}\n\t}\n')
    o.append('}\n')
    return ''.join(o)


# ---------------------------------------------------------------------------------------------
# Log-only probes (PROBE_TREAT, PROBE_PRICE). State scope, from the monthly state pulse.

def treatment_buildings(all_b_srcs, groups, pms):
    """Buildings with a working-conditions group: [(building, group, violent pm, harsh pm, [standard pms])]."""
    out = []
    for s in all_b_srcs:
        for bk, bn in s.objects().items():
            pg = pdx.get(bn.value, 'production_method_groups')
            for g in (pdx.items(pg) if pg else []):
                lst = groups.get(g, [])
                viol = [p for p in lst if p.startswith('slave_exploitation_') and p in pms]
                harsh = [p for p in lst if p.startswith('worker_exploitation_') and p in pms]
                std = [p for p in lst if p.startswith('default_labour')]
                if viol or harsh:
                    out.append((bk, g, viol[0] if viol else None, harsh[0] if harsh else None, std))
    return out


def barring_laws(pms, pm):
    if not pm:
        return []
    dl = pdx.get(pms[pm][0].value, 'disallowing_laws')
    return pdx.items(dl) if dl else []


def probe_values(treat):
    """State scope: workforce (and pop size, the fallback) employed in each treated building type,
    in total and per acceptance band. A state has at most one building of a type, so the pops of the
    state employed in that type are that building's workforce."""
    lo, hi = TREAT_BANDS
    bands = [('', ''), ('v', f' pop_acceptance < {lo}'),
             ('h', f' pop_acceptance >= {lo} pop_acceptance < {hi}'), ('s', f' pop_acceptance >= {hi}')]
    o = ['# State scope. pmr_tr_<measure><band>_<b>: the pops of the state employed in building type <b>,\n'
         f'# summed by workforce (w) and, as the fallback if workforce reads 0, by total_size (n); all of\n'
         f'# them, then acceptance below {lo} (v), {lo} to {hi - 1} (h), {hi} and over (s).\n\n']
    for bk, *_ in treat:
        b = short(bk)
        for measure, field in (('w', 'workforce'), ('n', 'total_size')):
            for band, cond in bands:
                # Each value is a pass over every pop of the state: without the probe, only the three
                # pmr_xtreat_<j>_<b> reads (w, wv, wh).
                if not PROBE_TREAT and (measure == 'n' or band == 's'):
                    continue
                o.append(f'pmr_tr_{measure}{band}_{b} = {{\n\tvalue = 0\n\tevery_scope_pop = {{\n'
                         f'\t\tlimit = {{ pop_employment_building = {bk}{cond} }}\n'
                         f'\t\tadd = {field}\n\t}}\n}}\n')
    return ''.join(o)


def probe_effects(treat, pms, goods_cost):
    def var(name, d=0):
        return f"[THIS.Var('{name}').GetValue|{d}]"
    where = ('date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
             'state=[THIS.GetState.GetNameNoFormatting]')
    o = ['# Log-only probes for the next batch: nothing here changes the game.\n\n']
    if not PROBE_TREAT:
        treat = []      # pmr_probe_treat would read script values not written without the probe
    tvars = ['pmr_tr_level', 'pmr_tr_cur', 'pmr_tr_vb', 'pmr_tr_hb'] + [
        f'pmr_tr_{m}{band}' for m in 'wn' for band in ('', 'v', 'h', 's')]
    o.append('# TREAT: one line per treated plantation. cur = the treatment it runs (2 violent, 1 exploitative,\n'
             '# 0 standard, 3 another method of the group); vb / hb = 1 while the owner\'s laws bar violent /\n'
             '# exploitative treatment; w, v, h, s = workforce in all, violent band, harsh band, standard band;\n'
             '# n, nv, nh, ns = the same by pop size.\n'
             'pmr_probe_treat = {\n')
    for bk, g, viol, harsh, std in treat:
        b = short(bk)
        o.append(f'\tif = {{\n\t\tlimit = {{ has_building = {bk} b:{bk} = {{ level >= 1 }} }}\n'
                 f'\t\tset_variable = {{ name = pmr_tr_level value = b:{bk}.level }}\n'
                 '\t\tset_variable = { name = pmr_tr_cur value = 3 }\n')
        cur = [(viol, 2), (harsh, 1)]
        for p, code in cur:
            if p:
                o.append(f'\t\tif = {{ limit = {{ b:{bk} = {{ has_active_production_method = {p} }} }} '
                         f'set_variable = {{ name = pmr_tr_cur value = {code} }} }}\n')
        for p in std:
            o.append(f'\t\tif = {{ limit = {{ b:{bk} = {{ has_active_production_method = {p} }} }} '
                     'set_variable = { name = pmr_tr_cur value = 0 } }\n')
        for p, name in ((viol, 'pmr_tr_vb'), (harsh, 'pmr_tr_hb')):
            o.append(f'\t\tset_variable = {{ name = {name} value = 0 }}\n')
            laws = barring_laws(pms, p)
            if laws:
                o.append(f'\t\tif = {{ limit = {{ owner = {{ OR = {{ '
                         + ' '.join(f'has_law = law_type:{law}' for law in laws)
                         + f' }} }} }} set_variable = {{ name = {name} value = 1 }} }}\n')
        for m in 'wn':
            for band in ('', 'v', 'h', 's'):
                o.append(f'\t\tset_variable = {{ name = pmr_tr_{m}{band} value = pmr_tr_{m}{band}_{b} }}\n')
        o.append(f'\t\tdebug_log = "PMR;rec=TREAT;{where};building={bk};level={var("pmr_tr_level")};'
                 f'cur={var("pmr_tr_cur")};vb={var("pmr_tr_vb")};hb={var("pmr_tr_hb")};'
                 + ';'.join(f'{m}{band}={var(f"pmr_tr_{m}{band}")}'
                            for m in 'wn' for band in ('', 'v', 'h', 's')) + '"\n\t}\n')
    # Without the probe nothing sets these: the clean-up would only log "used but never set" at startup.
    o.append(''.join(f'\tif = {{ limit = {{ has_variable = {n} }} remove_variable = {n} }}\n'
                     for n in (tvars if PROBE_TREAT else []))
             + '}\n\n')

    steps = list(range(75, 0, -PRICE_STEP)) if PROBE_PRICE else []
    o.append(f'# PRICE: where {PRICE_PROBE_BUILDING} stands, the local price of each probed good against its base,\n'
             f'# in steps of {PRICE_STEP}%: f reads the ladder with thresholds written as fractions (0.05 = 5%),\n'
             '# p with the same thresholds written as percent (5 = 5%), because the docs don\'t say which\n'
             '# state_goods_pricier means. Vanilla writes "state_goods_pricier > 0.5" (railways), which\n'
             '# suggests fractions; then p reads 0 for every good.\n'
             'pmr_probe_price = {\n'
             f'\tif = {{\n\t\tlimit = {{ has_building = {PRICE_PROBE_BUILDING} b:{PRICE_PROBE_BUILDING} = {{ level >= 1 }} }}\n')
    for good in (PRICE_PROBE_GOODS if PROBE_PRICE else ()):
        o.append(f'\t\tif = {{\n\t\t\tlimit = {{ exists = sg:{good} }}\n')
        for name, scale in (('pmr_pr_f', 100), ('pmr_pr_p', 1)):
            ladder = [(f'state_goods_pricier > {fmt(x / scale)}', x) for x in steps] + \
                     [(f'state_goods_cheaper > {fmt(x / scale)}', -x) for x in steps]
            for j, (cond, x) in enumerate(ladder):
                o.append(f'\t\t\t{"if" if j == 0 else "else_if"} = {{ limit = {{ sg:{good} = {{ {cond} }} }} '
                         f'set_variable = {{ name = {name} value = {x} }} }}\n')
            o.append(f'\t\t\telse = {{ set_variable = {{ name = {name} value = 0 }} }}\n')
        o.append(f'\t\t\tdebug_log = "PMR;rec=PRICE;{where};good={good};base={fmt(goods_cost.get(good, 0))};'
                 f'f={var("pmr_pr_f")};p={var("pmr_pr_p")}"\n'
                 '\t\t\tremove_variable = pmr_pr_f\n\t\t\tremove_variable = pmr_pr_p\n\t\t}\n'
                 f'\t\telse = {{ debug_log = "PMR;rec=PRICE;{where};good={good};sg=none" }}\n')
    o.append('\t}\n}\n\n')
    # Last: a scripted effect must be defined above its first use.
    o.append('# State scope, monthly. Player-owned states only, as for the tick logs.\n'
             'pmr_probe_state = {\n\tif = {\n\t\tlimit = { owner = { is_player = yes } }\n')
    if PROBE_TREAT and treat:
        o.append('\t\tpmr_probe_treat = yes\n')
    if PROBE_PRICE:
        o.append('\t\tpmr_probe_price = yes\n')
    o.append('\t}\n}\n')
    return ''.join(o)



def principle_bonus(treated, drop_base, pms):
    """(effects, static modifiers, loc) for the bonus of the dropped principle variants (PRINCIPLE_THROUGHPUT)."""
    def infra(p):
        sm = pdx.get(pms[p][0].value, 'state_modifiers')
        ws = sm and pdx.get(sm.value, 'workforce_scaled')
        n = ws and pdx.get(ws.value, 'state_infrastructure_add')
        return num(n.value, p) if n else 0.0

    by_principle = {}   # principle -> {building: {recipe index: extra infrastructure per level}}
    for variant, base in drop_base.items():
        up = pdx.get(pms[variant][0].value, 'unlocking_principles')
        principle = pdx.items(up)[0] if up else None
        if principle is None:
            raise SystemExit(f'{variant}: no unlocking_principles; PRINCIPLE_THROUGHPUT cannot place its bonus')
        for bk, _, _, recipes, _, _ in treated:
            for i, r in enumerate(recipes, 1):
                if r.key == base:
                    by_principle.setdefault(principle, {}).setdefault(bk, {})[i] = infra(variant) - infra(base)
    eff, mods, loc = [], [], []
    for principle, per in sorted(by_principle.items()):
        icon = 'gfx/interface/icons/principles_icons/transport.dds' if 'transport' in principle else GENERIC_ICON
        for bk, extra in sorted(per.items()):
            b = short(bk)
            thr, inf = f'pmr_pb_{principle}_{b}_thr', f'pmr_pb_{principle}_{b}_inf'
            mods.append(f'{thr} = {{\n\ticon = "{icon}"\n\tbuilding_{b}_throughput_add = 0.01\n}}\n\n'
                        f'{inf} = {{\n\ticon = "{icon}"\n\tstate_infrastructure_add = 1\n}}\n\n')
            group = 'principle_group_' + re.sub(r'_\d+$', '', principle[len('principle_'):])   # its name in vanilla loc
            loc += [f' {thr}:0 "${group}$"', f' {inf}:0 "${group}$"']
            lvs = ' '.join(f'add = var:pmr_lv_{i}_{b}' for i in sorted(extra))
            eff.append(
                '\tset_variable = { name = pmr_pb_thr value = 0 }\n\tset_variable = { name = pmr_pb_inf value = 0 }\n'
                '\tif = {\n\t\tlimit = {\n'
                f'\t\t\towner = {{ power_bloc ?= {{ has_principle = principle:{principle} }} }}\n'
                f'\t\t\thas_building = {bk}\n\t\t\tb:{bk} = {{ level >= 1 }}\n'
                + ''.join(f'\t\t\thas_variable = pmr_lv_{i}_{b}\n' for i in sorted(extra)) +
                '\t\t}\n'
                f'\t\t# the levels on recipes {sorted(extra)}, as a share of the building, times {fmt(PRINCIPLE_THROUGHPUT * 100)}%\n'
                f'\t\tset_variable = {{ name = pmr_pb_thr value = {{ value = 0 {lvs} multiply = {fmt(PRINCIPLE_THROUGHPUT * 100)} divide = b:{bk}.level }} }}\n'
                '\t\t# the extra infrastructure, by recipe, scaled by employment\n'
                '\t\tset_variable = { name = pmr_pb_inf value = { value = 0 '
                + ' '.join(f'add = {{ value = var:pmr_lv_{i}_{b} multiply = {fmt(x)} }}' for i, x in sorted(extra.items()) if x) + ' } }\n'
                f'\t\tset_variable = {{ name = pmr_pb_occ value = 0 }}\n'
                f'\t\tif = {{ limit = {{ b:{bk} = {{ occupancy >= 0.9 }} }} set_variable = {{ name = pmr_pb_occ value = 1 }} }}\n'
                f'\t\telse_if = {{ limit = {{ b:{bk} = {{ occupancy >= 0.7 }} }} set_variable = {{ name = pmr_pb_occ value = 0.8 }} }}\n'
                f'\t\telse_if = {{ limit = {{ b:{bk} = {{ occupancy >= 0.5 }} }} set_variable = {{ name = pmr_pb_occ value = 0.6 }} }}\n'
                f'\t\telse_if = {{ limit = {{ b:{bk} = {{ occupancy >= 0.3 }} }} set_variable = {{ name = pmr_pb_occ value = 0.4 }} }}\n'
                f'\t\telse_if = {{ limit = {{ b:{bk} = {{ occupancy > 0 }} }} set_variable = {{ name = pmr_pb_occ value = 0.2 }} }}\n'
                '\t\tchange_variable = { name = pmr_pb_inf multiply = var:pmr_pb_occ }\n'
                '\t\tremove_variable = pmr_pb_occ\n'
                '\t}\n'
                # Performance review 2 (2026-10-14): a state modifier removed and added again dirties every
                # building and pop of the state for the modifier update, so each is replaced only when its
                # value moved (pmr_pb_<...>_v keeps the value applied).
                + ''.join(
                    f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {m}_v }} }}\n\t\tset_variable = {{ name = {m}_v value = -1 }}\n\t}}\n'
                    f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:{m}_v = var:{var} }} }}\n'
                    f'\t\tif = {{ limit = {{ has_modifier = {m} }} remove_modifier = {m} }}\n'
                    f'\t\tif = {{ limit = {{ var:{var} > 0 }} add_modifier = {{ name = {m} multiplier = var:{var} }} }}\n'
                    f'\t\tset_variable = {{ name = {m}_v value = var:{var} }}\n\t}}\n'
                    for m, var in ((thr, 'pmr_pb_thr'), (inf, 'pmr_pb_inf')))
                + '\tremove_variable = pmr_pb_thr\n\tremove_variable = pmr_pb_inf\n')
    return ('# State scope, monthly: the bonus of a power bloc principle whose recipe variants PMR drops (PRINCIPLE_THROUGHPUT).\n'
            'pmr_principle_bonus = {\n' + ''.join(eff) + '}\n'), ''.join(mods), loc


# ---------------------------------------------------------------------------------------------
# Vanilla checks on methods PMR takes out (Pat, 2026-10-13, before the first upload)
#
# Vanilla events, journal entries and scripted triggers ask for automation methods by name (Mechanized
# Looms, Watertube Boiler, Steam Donkey...) and for the Transport principle's train variants. PMR folds a
# building's automation into its recipes and drops the variants, so those checks named methods the
# building no longer has: they never matched (Dangerous Equipment, Untrained Hands, the steam donkey
# objective) or matched the wrong buildings (NOT Traditional Looms). PMR shadows each vanilla file
# holding such a check, unchanged but for the checks, which ask PMR's equivalent instead:
#   - an automation method counts as running while any level of the building runs a recipe whose folded
#     automation is of its kind: the group's first method (no automation) on the recipes below
#     AUTOMATION_FROM_TIER, any other method that runs without electricity on the recipes from it (the
#     recipe folds the group's best such method, so an older one like the Watertube Boiler counts too),
#     and one that needs electricity on the electric recipe. A recipe runs while its share is above 0.
#   - a dropped principle variant reads as the recipe it replaced (the principle's bonus is applied on
#     top of that recipe, so it runs wherever the variant would have).
# The building files under common/history are left alone: their starting buildings name the methods in
# create_building, which only logs an error and builds them anyway.
COMPAT_DIRS = ('common', 'events')
COMPAT_SKIP = ('common/history/', 'common/buildings/', 'common/production_methods/', 'common/production_method_groups/')
COMPAT_TRIGGERS = 'common/scripted_triggers/00_00_pmr_vanilla_compat_triggers.txt'   # sorts before 00_scripted_triggers


def vanilla_compat(game, treated, auto_groups_of, groups, pms, group_users, drop_base, split_info=None):
    """Returns (scripted triggers, {published path: shadowed vanilla file}, [report lines])."""
    split_info = split_info or {}

    def kind(p, g):
        if p == groups[g][0]:
            return 'none'
        return 'elec' if Recipe(p, *pms[p]).needs(ELECTRICITY) else 'auto'

    recipes_of = {t[0]: t[3] for t in treated}
    runs = {}   # method -> [(building, [recipe indices on which a method of its kind runs])]
    for bk, ags in auto_groups_of.items():
        sp = split_info.get(bk)
        for gpos, g in enumerate(ags):
            plain = [p for p in groups[g] if not Recipe(p, *pms[p]).needs(ELECTRICITY)]
            on = []   # the method of group g each recipe runs, by recipe index
            if sp:    # the split: each pair runs its option's method of group g
                on = [(x, sp['options'][a - 1][gpos].key) for (ri, a), x in sorted(sp['index'].items())]
            for i, r in enumerate([] if sp else recipes_of[bk], 1):
                if isinstance(r, ElectricRecipe):
                    on.append((i, groups[g][-1]))
                else:
                    on.append((i, plain[-1] if i >= AUTOMATION_FROM_TIER and plain else groups[g][0]))
            for p in groups[g]:
                k = kind(p, g)
                runs.setdefault(p, []).append((bk, [i for i, q in on if kind(q, g) == k]))
    # With the split a recipe of such a building is the marker of (recipe, no automation) only: a check on it means
    # any pair built on it.
    alias = {}
    for bk, sp in split_info.items():
        for r in sp['pairs']:
            if isinstance(r, PairRecipe):
                alias.setdefault(r.base.key, [r.base.key]).append(r.key)
    folded_bks = set(auto_groups_of)
    pm_users = {}
    for g, lst in groups.items():
        for p in lst:
            pm_users.setdefault(p, set()).update(group_users.get(g, set()))
    still = {p for p in runs if pm_users.get(p, set()) - folded_bks}   # still a method of some other building

    used, files, lines = set(), {}, []

    def walk(src, nodes, rel):
        for n in nodes:
            if not n.is_block:
                if n.key == 'has_active_production_method' and (n.value in runs or n.value in drop_base or n.value in alias):
                    rep = (f'has_active_production_method = {drop_base[n.value]}' if n.value in drop_base
                           else f'pmr_has_{n.value} = yes')
                    used.add(n.value)
                    src.cuts.append((n.start, n.end))
                    src.inserts.append((n.start, rep))
                continue
            if n.key == 'is_production_method_active':
                kv = {c.key: c.value for c in n.value if c.key}
                p, b = kv.get('production_method'), kv.get('building_type')
                if p in drop_base:
                    rep = f'is_production_method_active = {{ building_type = {b} production_method = {drop_base[p]} }}'
                elif p in runs or p in alias:
                    rep = f'AND = {{ has_building = {b} b:{b} = {{ pmr_has_{p} = yes }} }}'
                else:
                    continue
                used.add(p)
                src.cuts.append((n.start, n.end))
                src.inserts.append((n.start, rep))
                continue
            walk(src, n.value, rel)

    names = set(runs) | set(drop_base) | set(alias)
    for top in COMPAT_DIRS:
        for root, _, fs in os.walk(os.path.join(game, top)):
            for fn in sorted(fs):
                path = os.path.join(root, fn)
                rel = os.path.relpath(path, game).replace(os.sep, '/')
                if not fn.endswith('.txt') or rel.startswith(COMPAT_SKIP):
                    continue
                with open(path, encoding='utf-8-sig', errors='replace') as f:
                    raw = f.read()
                if not any(nm in raw for nm in names):
                    continue
                src = Source(path)
                walk(src, src.nodes, rel)
                if not src.cuts:
                    continue
                out = src.render()
                code = '\n'.join(line.split('#')[0] for line in out.splitlines())
                left = sorted(nm for nm in names if re.search(rf'\b{nm}\b', code))
                if left:
                    raise SystemExit(f'{rel}: {left} still named in a form PMR does not rewrite; extend vanilla_compat')
                files[rel] = ('\ufeff# PMR: vanilla file, shadowed only to point its checks on methods PMR folds into '
                              'recipes at PMR\'s equivalents (pmr_has_*, ' + COMPAT_TRIGGERS.split('/')[-1] + ').\n'
                              + out.lstrip('\ufeff'))
                lines.append(f'{rel}: {len(src.cuts)} checks')

    trig = ['# Each vanilla check on a method PMR folds into recipes, building scope: true while a level of the\n'
            '# building runs a recipe with automation of the same kind (see vanilla_compat in generate.py).\n\n']
    for p in sorted(used & set(runs)):
        alts = [f'\t\thas_active_production_method = {p}\n'] if p in still else []
        for bk, idx in runs[p]:
            if idx and bk in split_info:
                # the split: a level on a pair whose option runs a method of p's kind (pmr_lv_<i>_<b>, the state's)
                lvs = [f'pmr_lv_{i}_{short(bk)}' for i in idx]
                alts.append(f'\t\tAND = {{\n\t\t\tis_building_type = {bk}\n\t\t\tstate = {{ OR = {{ '
                            + ' '.join(f'AND = {{ has_variable = {x} var:{x} > 0 }}' for x in lvs) + ' } }\n\t\t}\n')
            elif idx:
                alts.append(f'\t\tAND = {{\n\t\t\tis_building_type = {bk}\n\t\t\tOR = {{ '
                            + ' '.join(f'NOT = {{ has_active_production_method = pm_pmr_share_{short(bk)}_{i}_0 }}'
                                       for i in idx) + ' }\n\t\t}\n')
        trig.append(f'pmr_has_{p} = {{\n' + (f'\tOR = {{\n{"".join(alts)}\t}}\n' if alts else '\talways = no\n') + '}\n\n')
    for p in sorted(used & set(alias)):
        trig.append(f'pmr_has_{p} = {{\n\tOR = {{\n'
                    + ''.join(f'\t\thas_active_production_method = {x}\n' for x in alias[p]) + '\t}\n}\n\n')
    return ''.join(trig), files, lines


# ---------------------------------------------------------------------------------------------
# Building panel

def is_type(bk):
    return f"ObjectsEqual(Building.GetBuildingType, GetBuildingType('{bk}').Self)"


def any_type(buildings):
    """Or() over every PMR building type, nested two at a time."""
    expr = is_type(buildings[-1])
    for bk in reversed(buildings[:-1]):
        expr = f'Or({is_type(bk)}, {expr})'
    return expr


TYPE_TEST = re.compile(r"ObjectsEqual\((?:Building\.GetBuildingType|BuildingType\.Self), GetBuildingType\('building_\w+'\)\.Self\)")
TYPE_COPY = re.compile(r'^(\t*)([A-Za-z_]\w*) = \{\n\1\tvisible = "\[(.*)\]"[^\n]*\n', re.M)
MOVED = ('position =', 'parentanchor =', 'widgetanchor =')
GATED = []   # copies gated per file, for the report


def gate_type_copies(text):
    """Perf review 3 (G1, Pat 2026-10-19 01:23Z: "its gotten a bit bad on opening the building screen"): PMR writes a
    copy of a widget per building type and hides the others with visible, but the game builds a hidden widget all the
    same. Each copy whose visible starts with its type test becomes the one item of a list that has an item only for
    that type (DataModelRepeatedItem, as pmr_methods_cards), so a panel builds one gate per other type, not its
    whole copy. The gate takes the copy's visible, position and anchors, so it sits and hides where the copy did;
    a copy sized in % of its parent, or reading its parents, stays as it is."""
    n = 0
    for m in reversed(list(TYPE_COPY.finditer(text))):
        ind, cond = m.group(1), m.group(3)
        test = TYPE_TEST.match(cond, 4 if cond.startswith('And(') else 0)
        if not test or not (cond == test.group(0) or cond.startswith(f'And({test.group(0)}, ')):
            continue
        start, end = m.start() + len(ind), block_end(text, m.start())
        lines = text[start:end].split('\n')
        head, body = lines[0], lines[2:]
        direct = [l for l in body if l.startswith(ind + '\t') and not l.startswith(ind + '\t\t')]
        if 'AccessParent' in text[start:end] or any(l.strip().startswith('size =') and '%' in l for l in direct):
            continue
        moved = [l for l in direct if l.strip().startswith(MOVED)]
        item = '\n'.join('\t\t' + l if l.strip() else l for l in [ind + head] + [l for l in body if l not in moved])
        gate = (f"{ind}flowcontainer = {{  # PMR: built for its own type only\n{ind}\tvisible = \"[{cond}]\"\n"
                + ''.join(f'{ind}\t{l.strip()}\n' for l in moved)
                + f"{ind}\tdatamodel = \"[DataModelRepeatedItem(Select_int32({test.group(0)}, '(int32)1', '(int32)0'))]\"\n"
                f'{ind}\titem = {{\n{item}\n{ind}\t}}\n{ind}}}')
        text = text[:m.start()] + gate + text[end:]
        n += 1
    GATED.append(n)
    return text


def any_of(exprs):
    """Or() over exprs, nested as a balanced tree so a long list stays shallow."""
    if len(exprs) == 1:
        return exprs[0]
    mid = len(exprs) // 2
    return f'Or({any_of(exprs[:mid])}, {any_of(exprs[mid:])})'


def hide_retool_sites(text, site_types):
    """states_panel_buildings.gui: the state's Buildings tab without the retool sites (Pat 2026-10-14 01:54Z).

    A site has to stay a real building: investors pick it and the crew works there. The engine fills the
    tab's urban grid and list (State.AccessUrbanBuildings) with every building whose group's category is
    urban (1.14.5 exe, 0x141a8c560), and a site's group needs bg_manufacturing as its parent for investors
    to score it, so its category stays urban. The tab hides it instead: the item is invisible and the grid
    ignores invisible items, as the lens toolbar's grid does. The list view's grid is shared with the rural
    and development lists, which never hold a site."""
    hidden = 'Not(' + any_of([is_type(t) for t in site_types]) + ')'
    for old, new, what in [
            ('\t\t\t\t\tdatamodel = "[State.AccessUrbanBuildings]"\n\t\t\t\t\tdatamodel_wrap = 4\n'
             '\t\t\t\t\tflipdirection = yes\n\n\t\t\t\t\titem = {\n\t\t\t\t\t\tbuilding_item = {}\n',
             '\t\t\t\t\tdatamodel = "[State.AccessUrbanBuildings]"\n\t\t\t\t\tdatamodel_wrap = 4\n'
             '\t\t\t\t\tflipdirection = yes\n\t\t\t\t\t# PMR: no retool sites\n'
             '\t\t\t\t\tignoreinvisible = yes\n\n\t\t\t\t\titem = {\n'
             f'\t\t\t\t\t\tbuilding_item = {{\n\t\t\t\t\t\t\tvisible = "[{hidden}]"\n\t\t\t\t\t\t}}\n',
             'the urban grid'),
            ('\t\tdynamicgridbox = {\n\t\t\tblock "datamodel" {}\n\n\t\t\titem = {\n'
             '\t\t\t\tbuildings_list_item = {}\n',
             '\t\tdynamicgridbox = {\n\t\t\tblock "datamodel" {}\n\t\t\t# PMR: no retool sites\n'
             '\t\t\tignoreinvisible = yes\n\n\t\t\titem = {\n'
             f'\t\t\t\tbuildings_list_item = {{\n\t\t\t\t\tvisible = "[{hidden}]"\n\t\t\t\t}}\n',
             'the list view')]:
        if text.count(old) != 1:
            raise SystemExit(f'states_panel_buildings.gui: expected one {what} item, found {text.count(old)}; '
                             'update hide_retool_sites')
        text = text.replace(old, new)
    return text


def state_var(b, name):
    return f"Building.GetState.MakeScope.Var('{name}_{b}').GetValue"


def country_var(b, name):
    return f"GetPlayer.MakeScope.Var('{name}_{b}').GetValue"


def stacked_bar(b, textures, size, icon, ind, var=None, tips=None):
    """A recipe bar in the style of vanilla's Owners bar (building_ownership_stacked_barchart): one
    slice per recipe, oldest on the left, as wide as that recipe's share of the levels
    (layoutstretchfactor_horizontal, as vanilla sizes owners), coloured by its tier (TIER_COLORS),
    with the recipe's icon centred on it once the slice is over RECIPE_ICON_SHARE. var(name) reads a
    PMR variable (one building's state by default); tips are (visible, tooltip key) hover areas."""
    var = var or (lambda name: state_var(b, name))
    retooling = f'NotZero_CFixedPoint({var("pmr_ui_retooling")})'
    if tips is None:
        tips = [(retooling, f'PMR_BAR_TOOLTIP_{b}'), (f'Not({retooling})', 'PMR_BAR_FULL_TOOLTIP')]
    slices = []
    for i, tex in enumerate(textures, 1):
        name, rgb = TIER_COLORS[i - 1]
        sh = var(f'{"pmr_rs" if b in SPLIT_BARS else "pmr_sh"}_{i}')
        slices.append((f'tier {i}, {name.lower()}', f"GreaterThan_CFixedPoint({sh}, '(CFixedPoint)0')",
                       f"FixedPointToInt(Multiply_CFixedPoint({sh}, '(CFixedPoint)100'))",
                       f"GreaterThan_CFixedPoint({sh}, '(CFixedPoint){RECIPE_ICON_SHARE}')", rgb, tex))
    return slice_bar(slices, size, icon, ind, tips)


def slice_bar(slices, size, icon, ind, tips):
    """The Owners-style bar itself. slices are (comment, visible, stretch factor, icon visible,
    colour, icon texture or None), left to right."""
    items = []
    for comment, vis, stretch, icon_vis, (r, g, bl), tex in slices:
        items.append(
            f'{ind}\t\t# {comment}\n'
            f'{ind}\t\thbox = {{\n'
            f'{ind}\t\t\tvisible = "[{vis}]"\n'
            f'{ind}\t\t\tlayoutpolicy_horizontal = expanding\n{ind}\t\t\tlayoutpolicy_vertical = expanding\n'
            f'{ind}\t\t\tlayoutstretchfactor_horizontal = "[{stretch}]"\n'
            f'{ind}\t\t\talwaystransparent = yes\n'
            f'{ind}\t\t\tbackground = {{\n'
            f'{ind}\t\t\t\ttexture = "gfx/interface/tooltip/stacked_barchart_small_item.dds"\n'
            f'{ind}\t\t\t\tcolor = {{ {r} {g} {bl} 1 }}\n'
            f'{ind}\t\t\t\tspriteborder = {{ 3 3 }}\n'
            f'{ind}\t\t\t\tusing = simple_frame_mask\n{ind}\t\t\t\tusing = progressbar_texture_properties\n'
            f'{ind}\t\t\t}}\n'
            + (f'{ind}\t\t\ticon = {{\n'
               f'{ind}\t\t\t\tvisible = "[{icon_vis}]"\n'
               f'{ind}\t\t\t\tsize = {{ {icon} {icon} }}\n'
               f'{ind}\t\t\t\talwaystransparent = yes\n'
               f'{ind}\t\t\t\ttexture = "{tex}"\n'
               f'{ind}\t\t\t}}\n' if tex else '')
            + f'{ind}\t\t}}\n')
    return (f'{ind}widget = {{\n'
            f'{ind}\tsize = {{ {size[0]} {size[1]} }}\n'
            f'{ind}\tbackground = {{\n'
            f'{ind}\t\ttexture = "gfx/interface/progressbar/progressbar_empty.dds"\n'
            f'{ind}\t\tspriteType = Corneredtiled\n{ind}\t\tspriteborder = {{ 4 4 }}\n{ind}\t\ttexture_density = 2\n'
            f'{ind}\t\tusing = progressbar_texture_properties\n{ind}\t}}\n'
            f'{ind}\thbox = {{\n'
            f'{ind}\t\tlayoutpolicy_horizontal = expanding\n{ind}\t\tlayoutpolicy_vertical = expanding\n'
            f'{ind}\t\tmargin = {{ 1 1 }}\n'
            + ''.join(items) +
            f'{ind}\t}}\n'
            f'{ind}\t# hover areas\n'
            + ''.join(f'{ind}\twidget = {{\n' + (f'{ind}\t\tvisible = "[{vis}]"\n' if vis else '')
                      + f'{ind}\t\tsize = {{ 100% 100% }}\n{ind}\t\ttooltip = "{key}"\n{ind}\t\tusing = tooltip_above\n{ind}\t}}\n'
                      for vis, key in tips)
            + f'{ind}}}\n')


def switch_bar(sw, swd, size, ind, tip, idle_tip=None, place=''):
    """Pat, 2026-10-19 01:07Z: the bar a new pick fills for SWITCH_MONTHS months before it becomes the default new
    levels and retooling follow (pmr_switch_<b>): green with vanilla's moving arrows toward a newer recipe, red toward an
    older one (the cash reserve bar's changed_value_increased_progressbar_horizontal and its _bad twin). sw and swd are
    the months filled and the direction (1, -1, 0); with idle_tip an empty bar stands in while nothing is pending."""
    i1, i2 = ind + '\t', ind + '\t\t'
    val = f"FixedPointToFloat(Add_CFixedPoint({sw}, '(CFixedPoint)0.25'))"

    def bar(kind, vis, key):
        return (f'{ind}{kind} = {{\n{place}{i1}visible = "[{vis}]"\n{i1}size = {{ {size[0]} {size[1]} }}\n'
                f'{i1}blockoverride "second_progressbar" {{}}\n'
                f'{i1}blockoverride "values" {{\n{i2}min = 0\n{i2}max = {SWITCH_MONTHS}\n{i2}value = "[{val}]"\n{i1}}}\n'
                f'{i1}blockoverride "arrow_texture_density" {{\n{i2}texture_density = {max(2, size[1] // 4)}\n{i1}}}\n'
                f'{i1}tooltip = "{key}"\n{i1}using = tooltip_above\n{ind}}}\n')
    out = (bar('changed_value_increased_progressbar_horizontal', f"GreaterThan_CFixedPoint({swd}, '(CFixedPoint)0')", tip)
           + bar('changed_value_increased_progressbar_horizontal_bad', f"LessThan_CFixedPoint({swd}, '(CFixedPoint)0')", tip))
    if idle_tip:
        out += (f'{ind}default_progressbar_horizontal = {{\n{place}{i1}visible = "[EqualTo_CFixedPoint({swd}, '
                f"'(CFixedPoint)0')]\"\n{i1}size = {{ {size[0]} {size[1]} }}\n"
                f'{i1}blockoverride "values" {{\n{i2}min = 0\n{i2}max = 1\n{i2}value = 0\n{i1}}}\n'
                f'{i1}tooltip = "{idle_tip}"\n{i1}using = tooltip_above\n{ind}}}\n')
    return out


GOV_ABROAD_CLICKS = 8   # most government retool levels one click queues abroad; more take another click


def gov_button(b, size, ind, place=''):
    """The government upgrade button: queues every government retool level the building still
    needs (pmr_gov_retool_<b>_sgui). Greyed out unless the government has room left, which needs
    government-owned levels still to retool. At home the scripted GUI queues them; abroad (pmr_abroad_<b>,
    Pat 21:26Z) no script can queue a construction for the player's government, so the button expands the
    site the tick keeps standing there (Building.QueueConstruction, the game's own expand, into the
    government construction queue) once per level of room, then ticks. A GUI can't loop, so there is one
    button per room of 1 .. GOV_ABROAD_CLICKS levels, each with that many clicks."""
    sgui = f"GetScriptedGui('pmr_gov_retool_{b}_sgui')"
    tick = f"GetScriptedGui('pmr_gov_retool_tick_{b}_sgui')"
    scope = 'GuiScope.SetRoot(Building.GetState.MakeScope).End'
    abroad = f"GreaterThan_CFixedPoint({state_var(b, 'pmr_abroad')}, '(CFixedPoint)0')"
    site = f"Building.GetState.GetBuilding('building_pmr_retool_gova_{b}')"
    room = state_var(b, 'pmr_room_gov')

    def button(visible, enabled, clicks, tooltip):
        return (f'{ind}button_icon_round = {{\n{place}'
                f'{ind}\tvisible = "[{visible}]"\n'
                f'{ind}\tsize = {{ {size} {size} }}\n'
                f'{ind}\tenabled = {enabled}\n'
                + ''.join(f'{ind}\tonclick = "[{c}]"\n' for c in clicks) +
                f'{ind}\ttooltip = "{tooltip}"\n'
                f'{ind}\tusing = tooltip_ne\n'
                f'{ind}\tusing = confirm_button_sound\n'
                f'{ind}\tblockoverride "icon" {{\n{ind}\t\ttexture = "{GOV_RETOOL_ICON}"\n{ind}\t}}\n'
                f'{ind}\tblockoverride "icon_size" {{\n{ind}\t\tsize = {{ 80% 80% }}\n{ind}\t}}\n'
                f'{ind}}}\n')

    def room_is(n):
        at_least = f"GreaterThanOrEqualTo_CFixedPoint({room}, '(CFixedPoint){n}')"
        if n == GOV_ABROAD_CLICKS:
            return at_least
        return f"And({at_least}, LessThan_CFixedPoint({room}, '(CFixedPoint){n + 1}'))"

    out = button(f'Not({abroad})',
                 f'"[And(ObjectsEqual(Building.GetState.GetOwner.Self, GetPlayer.Self), {sgui}.IsValid({scope}))]"',
                 [f'{sgui}.Execute({scope})'], f'PMR_GOV_RETOOL_TOOLTIP_{b}')
    out += button(f"And({abroad}, Or(Not({site}.IsValid), LessThan_CFixedPoint({room}, '(CFixedPoint)1')))",
                  'no', [], f'PMR_GOV_RETOOL_ABROAD_TOOLTIP_{b}')
    for n in range(1, GOV_ABROAD_CLICKS + 1):
        out += button(f'And({abroad}, And({site}.IsValid, {room_is(n)}))',
                      f'"[IsValid({site}.QueueConstruction)]"',
                      [f'Execute({site}.QueueConstruction)'] * n + [f'{tick}.Execute({scope})'],
                      f'PMR_GOV_RETOOL_ABROAD_TOOLTIP_{b}')
    return out


ROW_X, ROW_W = 6, 287   # the recipe row: from the panel's left edge to 12 px short of the employment bar
# Pat, 2026-10-13: as tall as the cash reserves bar looks. That bar is 26 px in a frame that shows
# about 3 px either side, so the recipe bar is 32 px, centred on it (y 34..60 in the 60 px row).
RECIPE_BAR_Y, RECIPE_BAR_H, RECIPE_BAR_ICON = 31, 32, 26


def recipe_bar(bk, b, textures):
    """The recipe bar for one building type, in the details panel's row left of the employment and
    cash-reserve bars (230 wide, 5 from the right edge of the 540 px panel). Pat, 2026-10-13: no goods
    icon in front, so the row runs from the left edge: x 6..293. The top row holds the recipe's name
    and, against the employment bar, the government upgrade button; below it the stacked recipe bar,
    as tall as the cash reserves bar looks (RECIPE_BAR_H). The same row shows in the Buildings tab
    when a building type is expanded (vanilla's condensed_building_information is both)."""
    retooling = f'NotZero_CFixedPoint({state_var(b, "pmr_ui_retooling")})'
    ind = '\t\t\t\t\t'
    return f"""
				# PMR: recipe bar and government upgrade button for {bk}
				widget = {{
					visible = "[{is_type(bk)}]"
					position = {{ {ROW_X} 0 }}
					size = {{ {ROW_W} 60 }}
					parentanchor = vcenter

					textbox = {{
						visible = "[Not({retooling})]"
						size = {{ {ROW_W - 34} 26 }}
						align = left|nobaseline
						elide = right
						text = "PMR_RECIPE_BAR_TITLE"
						tooltip = "PMR_RECIPE_BAR_TOOLTIP"
						using = tooltip_above
					}}
					textbox = {{
						visible = "[{retooling}]"
						size = {{ {ROW_W - 34} 26 }}
						align = left|nobaseline
						elide = right
						text = "PMR_RECIPE_BAR_TITLE_RETOOLING_{b}"
						tooltip = "PMR_BAR_TOOLTIP_{b}"
						using = tooltip_above
					}}
{gov_button(b, 30, ind, f'{ind}\tposition = {{ {ROW_W - 30} -2 }}\n')}
					widget = {{
						position = {{ 0 {RECIPE_BAR_Y} }}
						size = {{ {ROW_W} {RECIPE_BAR_H} }}
{stacked_bar(b, textures, ('100%', '100%'), RECIPE_BAR_ICON, ind + chr(9))}					}}
				}}
"""


# Pat, 2026-10-13: a second stacked bar under the recipe bar for each second group PMR blends,
# one row per group: the trade-offs mixed by local prices, and plantation treatment set by the
# workforce's acceptance. The bar lines up under the recipe bar; the leading option and its share
# sit in the employment bars' column beside it.
OPTION_ROW_H, OPTION_BAR_H, OPTION_BAR_ICON = 26, 22, 18
OPTION_ICON_SHARE = 25      # an option's slice shows its icon above this share, as on the recipe bar


def option_bars(bk, groups, ind):
    """The details panel's option rows for one building type, at indent ind. groups are (gi, mode,
    none key, none texture, [Option]) per converted group."""
    b = short(bk)
    x = lambda name: state_var(b, name)    # noqa: E731
    gt = lambda e, n: f"GreaterThan_CFixedPoint({e}, '(CFixedPoint){n}')"    # noqa: E731
    i2, i3 = ind + '\t\t', ind + '\t\t\t'
    rows = []
    for gi, mode, none, none_tex, os_ in groups:
        def piece(name, comment, rgb, tex):
            e = x(name)
            return (comment, gt(e, 0), f'FixedPointToInt({e})', gt(e, OPTION_ICON_SHARE), rgb, tex)
        slices = [piece(f'pmr_xn_{gi}', f'{none}, grey', OPTION_NONE_COLOR, none_tex)]
        for k, o in enumerate(os_):
            name, rgb = OPTION_COLORS[k % len(OPTION_COLORS)]
            slices.append(piece(f'pmr_x_{o.j}', f'{o.key}, {name.lower()}', rgb, o.texture))
        tip = f'PMR_OPT_TOOLTIP_{b}_{gi}'
        rows.append(
            f'{ind}\twidget = {{\n{i2}size = {{ @panel_width {OPTION_ROW_H} }}\n'
            f'{i2}widget = {{\n{i3}position = {{ {ROW_X} {(OPTION_ROW_H - OPTION_BAR_H) // 2} }}\n'
            f'{i3}size = {{ {ROW_W} {OPTION_BAR_H} }}\n'
            + slice_bar(slices, ('100%', '100%'), OPTION_BAR_ICON, i3, [(None, tip)])
            + f'{i2}}}\n'
            # Pat, 2026-10-13: a fixed name, vanilla's own for the group (Hardwood Production,
            # Secondary, Luxury Production, Working Conditions), not the leading option's
            + f'{i2}textbox = {{\n'
            f'{i3}position = {{ {ROW_X + ROW_W + 12} 0 }}\n'
            f'{i3}size = {{ 223 {OPTION_ROW_H} }}\n'
            f'{i3}align = left|nobaseline\n{i3}elide = right\n'
            f'{i3}text = "{os_[0].group}"\n{i3}tooltip = "{tip}"\n'
            f'{i3}using = tooltip_above\n{i2}}}\n'
            + f'{ind}\t}}\n')
    return (f'{ind}# PMR: second groups of {bk}\n'
            f'{ind}flowcontainer = {{\n{ind}\tvisible = "[{is_type(bk)}]"\n{ind}\tdirection = vertical\n'
            + ''.join(rows) + f'{ind}}}\n')


def automation_bar(bk, group, levels, ind):
    """The details panel's automation row for one building type (AUTO_COLORS), laid out as an option row."""
    b = short(bk)
    x = lambda name: state_var(b, name)    # noqa: E731
    i2, i3 = ind + '\t\t', ind + '\t\t\t'
    slices = []
    for a, (key, tex, _) in enumerate(levels, 1):
        # the least automated level is always the palest and the most automated the darkest
        name, rgb = AUTO_COLORS[round((a - 1) * (len(AUTO_COLORS) - 1) / max(1, len(levels) - 1))]
        sh = x(f'pmr_ash_{a}')
        slices.append((f'{key}, {name.lower()}', f"GreaterThan_CFixedPoint({sh}, '(CFixedPoint)0')",
                       f"FixedPointToInt(Multiply_CFixedPoint({sh}, '(CFixedPoint)100'))",
                       f"GreaterThan_CFixedPoint({sh}, '(CFixedPoint){RECIPE_ICON_SHARE}')", rgb, tex))
    tip = f'PMR_AUTO_TOOLTIP_{b}'
    return (f'{ind}# PMR: automation bar of {bk}\n'
            f'{ind}widget = {{\n{ind}\tvisible = "[{is_type(bk)}]"\n{ind}\tsize = {{ @panel_width {OPTION_ROW_H} }}\n'
            f'{ind}\twidget = {{\n{i2}position = {{ {ROW_X} {(OPTION_ROW_H - OPTION_BAR_H) // 2} }}\n'
            f'{i2}size = {{ {ROW_W} {OPTION_BAR_H} }}\n'
            + slice_bar(slices, ('100%', '100%'), OPTION_BAR_ICON, i2, [(None, tip)])
            + f'{ind}\t}}\n'
            f'{ind}\ttextbox = {{\n{i2}position = {{ {ROW_X + ROW_W + 12} 0 }}\n{i2}size = {{ 223 {OPTION_ROW_H} }}\n'
            f'{i2}align = left|nobaseline\n{i2}elide = right\n{i2}text = "{group}"\n{i2}tooltip = "{tip}"\n'
            f'{i2}using = tooltip_above\n{ind}\t}}\n{ind}}}\n')


SW_ROW_H, SW_BAR_H = 16, 12   # the details panel's switching bar row


def pick_row(bk, ind):
    """The details panel's pick row (Pat, 2026-10-18 17:49Z: where a building shows its preferred recipe): the
    most profitable recipe, the target its new levels and retooling follow, and its profit per level a week. No
    tooltip: the Policies cards show every recipe's (Pat, 2026-10-19 01:07Z)."""
    b = short(bk)
    i2 = ind + '\t\t'
    return (f'{ind}# PMR: most profitable recipe of {bk}\n'
            f'{ind}widget = {{\n{ind}\tvisible = "[And({is_type(bk)}, '
            f"GreaterThan_CFixedPoint({state_var(b, 'pmr_pbest')}, '(CFixedPoint)0'))]\"\n"
            f'{ind}\tsize = {{ @panel_width {OPTION_ROW_H} }}\n'
            f'{ind}\ttextbox = {{\n{i2}position = {{ {ROW_X} 0 }}\n{i2}size = {{ {ROW_W + 235} {OPTION_ROW_H} }}\n'
            f'{i2}align = left|nobaseline\n{i2}elide = right\n{i2}text = "PMR_PICK_ROW_{b}"\n{ind}\t}}\n{ind}}}\n'
            # Pat, 2026-10-19 01:07Z: the switching bar under it while a new pick fills it
            f'{ind}widget = {{\n{ind}\tvisible = "[And({is_type(bk)}, Not(EqualTo_CFixedPoint({state_var(b, "pmr_swd")}, '
            f"'(CFixedPoint)0')))]\"\n{ind}\tsize = {{ @panel_width {SW_ROW_H} }}\n"
            + switch_bar(state_var(b, 'pmr_sw'), state_var(b, 'pmr_swd'), (ROW_W, SW_BAR_H), ind + '\t', f'PMR_SW_TT_{b}',
                         place=f'{ind}\t\tposition = {{ {ROW_X} {(SW_ROW_H - SW_BAR_H) // 2} }}\n')
            + f'{ind}}}\n')


# The Private tab's Methods view (Pat, 2026-10-18 18:00Z): what financial districts and manor houses build and
# retool to. They follow each state's profit pick (pmr_pbest_<b>); script can't tell the two apart within a
# building, so the view is the country's private side. Each row is one building type the country has, at the prices
# of its state with the most levels of the type (the interface variables copied onto the country under the same
# names), and each recipe's tooltip adds how much of the country picks it (pmr_mv_ps_<i>_<b>, a share of the
# levels) and runs it (pmr_c_sh_<i>_<b>). Recounted only when the tab opens (pmr_pc_refresh_sgui runs
# pmr_mv_refresh), from the cached picks: opening it never recalculates or moves a target.
MV_COUNTRY = 'GetPlayer'


def mv_read(name):
    return f"{MV_COUNTRY}.MakeScope.Var('{name}').GetValue"


def company_mark(bk, ctypes):
    """Pat 2026-10-19 00:01Z: "a company icon and outliner for buildings companies own": the country's company with
    building type bk (the last of them, so it stays the same between refreshes), by its executive."""
    if not ctypes:
        return ''
    b = short(bk)
    has = ' '.join(f'is_company_type = company_type:{c}' for c in ctypes)
    return (f'\tset_variable = {{ name = pmr_mv_cf_{b} value = 0 }}\n'
            f'\tevery_company = {{\n\t\tlimit = {{ OR = {{ {has} }} }}\n'
            f'\t\texecutive ?= {{ save_scope_as = pmr_mv_cx_{b} }}\n\t}}\n'
            f'\tif = {{\n\t\tlimit = {{ exists = scope:pmr_mv_cx_{b} }}\n'
            f'\t\tset_variable = {{ name = pmr_mv_co_{b} value = scope:pmr_mv_cx_{b} }}\n'
            f'\t\tset_variable = {{ name = pmr_mv_cf_{b} value = 1 }}\n\t}}\n')


def methods_view_effects(recipe_keys, pair_ui=None, ai=None, parts=None, companies=None, extra=None):
    """Country scope: pmr_mv_<b> per building type and pmr_mv_refresh for all of them. ai: the types with an AI value
    (private_investment.ai_groups), copied from the same state as pmr_mv_aiv_<b> and its vanilla base as pmr_mv_aib_<b>;
    parts: each type's policy parts (private_investment.ai_parts), copied as pmr_mv_p<key>_<b>; companies: building
    type -> the company types listing it (private_investment.company_owners): the country's company with the type,
    if any, as its executive in pmr_mv_co_<b> (the GUI reaches a company through a character, cc_wheel.VIEWED) and
    pmr_mv_cf_<b> = 1."""
    pair_ui, ai, parts, companies, extra = pair_ui or {}, ai or {}, parts or {}, companies or {}, extra or {}
    o = ['# Country scope. The Buildings panel\'s Policies tab (methods_view_effects in generate.py).\n\n']
    for bk, keys in recipe_keys.items():
        b, k = short(bk), len(keys)
        split = pair_ui.get(bk, {}).get('split')
        per = ([] if split else   # with the split the grid shows the targets' own figures (pair_effect)
               [f'pmr_rm_{i}_{b}' for i in range(1, k + 1)] + [f'pmr_rav_{i}_{b}' for i in range(1, k + 1)]
               + [f'pmr_rveto_{i}_{b}' for i in range(1, k + 1)]) + [f'pmr_pbest_{b}']
        if bk in pair_ui:
            per += [f'pmr_{x}_{i}_{a}_{b}' for i, a in sorted(pair_ui[bk]['econ']) for x in ('cp', 'cav')] \
                + [f'pmr_cbi_{b}', f'pmr_cba_{b}']
        pk = [key for key, name in parts.get(bk, []) if name] if bk in ai else []
        o.append(f'pmr_mv_{b} = {{\n\tsave_temporary_scope_as = pmr_ctry\n'
                 f'\tset_variable = {{ name = pmr_mv_lv_{b} value = 0 }}\n\tset_variable = {{ name = pmr_mv_max_{b} value = 0 }}\n'
                 f'\tset_variable = {{ name = pmr_pbest_{b} value = 0 }}\n'
                 + ''.join(f'\tset_variable = {{ name = pmr_mv_ps_{i}_{b} value = 0 }}\n' for i in range(1, k + 1))
                 + f'\tevery_scope_state = {{\n\t\tlimit = {{ has_variable = pmr_level_{b} var:pmr_level_{b} > 0 '
                 f'has_variable = pmr_pbest_{b} has_variable = pmr_rm_1_{b} }}\n'
                 '\t\tsave_temporary_scope_as = pmr_st\n'
                 f'\t\towner = {{ change_variable = {{ name = pmr_mv_lv_{b} add = scope:pmr_st.var:pmr_level_{b} }} }}\n'
                 + ''.join(f'\t\tif = {{ limit = {{ var:pmr_pbest_{b} = {i} }} '
                           f'owner = {{ change_variable = {{ name = pmr_mv_ps_{i}_{b} add = scope:pmr_st.var:pmr_level_{b} }} }} }}\n'
                           for i in range(1, k + 1))
                 + f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_level_{b} > scope:pmr_ctry.var:pmr_mv_max_{b} }}\n'
                 + (f'\t\t\tset_variable = {{ name = pmr_mv_aiv_{b} value = pmr_ai_value_{b} }}\n'
                    f'\t\t\tset_variable = {{ name = pmr_mv_aib_{b} value = pmr_ai_base_{b} }}\n' if bk in ai else '')
                 + ''.join(f'\t\t\tset_variable = {{ name = pmr_mv_p{key}_{b} value = pmr_ai_{key}_{b} }}\n' for key in pk)
                 + f'\t\t\towner = {{\n'
                 f'\t\t\t\tset_variable = {{ name = pmr_mv_max_{b} value = scope:pmr_st.var:pmr_level_{b} }}\n'
                 + ''.join(f'\t\t\t\tset_variable = {{ name = {n} value = scope:pmr_st.var:{n} }}\n'
                           for n in per + ([f'pmr_mv_aiv_{b}', f'pmr_mv_aib_{b}'] if bk in ai else [])
                           + [f'pmr_mv_p{key}_{b}' for key in pk])
                 # the bars under the card's grid (card_bars): copied where the state has them
                 + ''.join(f'\t\t\t\tif = {{ limit = {{ scope:pmr_st = {{ has_variable = {n} }} }} '
                           f'set_variable = {{ name = {n} value = scope:pmr_st.var:{n} }} }}\n' for n in extra.get(bk, []))
                 + '\t\t\t}\n\t\t}\n\t}\n'
                 f'\tif = {{\n\t\tlimit = {{ var:pmr_mv_lv_{b} > 0 }}\n'
                 + ''.join(f'\t\tchange_variable = {{ name = pmr_mv_ps_{i}_{b} divide = var:pmr_mv_lv_{b} }}\n'
                           for i in range(1, k + 1))
                 + '\t}\n' + company_mark(bk, companies.get(bk)) + '}\n\n')
    # Pat 23:22Z: each type's AI weight as its share of the sum over every type on the tab, as the investors pick by
    # weight: the AI value times its priority group's multiplier (pmr_mv_w_<b>), over pmr_mv_wsum, as pmr_mv_sh_<b>
    shown = [(short(bk), private_investment.VAR.format(ai[bk])) for bk in recipe_keys if bk in ai]
    share = ('\tset_variable = { name = pmr_mv_wsum value = 0 }\n\tset_variable = { name = pmr_mv_m value = 1 }\n'
             + ''.join(f'\tset_variable = {{ name = pmr_mv_w_{b} value = 0 }}\n'
                       f'\tif = {{\n\t\tlimit = {{ var:pmr_mv_lv_{b} > 0 has_variable = pmr_mv_aiv_{b} }}\n'
                       f'\t\tset_variable = {{ name = pmr_mv_m value = {m} }}\n'
                       f'\t\tset_variable = {{ name = pmr_mv_w_{b} value = var:pmr_mv_aiv_{b} }}\n'
                       f'\t\tchange_variable = {{ name = pmr_mv_w_{b} multiply = var:pmr_mv_m }}\n'
                       f'\t\tchange_variable = {{ name = pmr_mv_wsum add = var:pmr_mv_w_{b} }}\n\t}}\n'
                       for b, m in shown)
             + ''.join(f'\tset_variable = {{ name = pmr_mv_sh_{b} value = 0 }}\n'
                       f'\tif = {{\n\t\tlimit = {{ var:pmr_mv_wsum > 0 }}\n'
                       f'\t\tset_variable = {{ name = pmr_mv_sh_{b} value = var:pmr_mv_w_{b} }}\n'
                       f'\t\tchange_variable = {{ name = pmr_mv_sh_{b} divide = var:pmr_mv_wsum }}\n\t}}\n'
                       for b, _m in shown)
             + '\tremove_variable = pmr_mv_m\n\tpmr_mv_sort = yes\n'
             + '\tif = {\n\t\tlimit = { is_player = yes }\n'
             '\t\tdebug_log = "PMR;rec=MV_SHARE;date=[TimeKeeper.GetCurrentDate.GetString];'
             "sum=[THIS.Var('pmr_mv_wsum').GetValue|0];"
             + ';'.join(f"{b}=[THIS.Var('pmr_mv_w_{b}').GetValue|0]/[THIS.Var('pmr_mv_sh_{b}').GetValue|3]"
                        f"/[THIS.Var('pmr_mv_rk_{b}').GetValue|0]" for b, _m in shown)
             + '"\n\t}\n' if shown else '')
    o.append('pmr_mv_refresh = {\n' + ''.join(f'\tpmr_mv_{short(bk)} = yes\n' for bk in recipe_keys)
             + ('\tpmr_bo_refresh = yes\n' if shown else '')
             + (share or '\tpmr_mv_sort = yes\n') + '}\n\n')
    # Pat 23:53Z: the Investments cards sorted by AI weight. Each type with a card gets its place in that order,
    # pmr_mv_rk_<b> (0 first, -1 without a card), over pmr_mv_n places; methods_view_gui's AI sort shows place k's card
    # in its k-th slot. A selection sort: each pass takes the heaviest type still waiting (-2); types without an AI
    # weight come last, in the list's order. Runs with the refresh, on the tab's or the sort button's click.
    types = [(j, short(bk), f'var:pmr_mv_w_{short(bk)}' if bk in ai else None) for j, bk in enumerate(recipe_keys, 1)]
    o.append('pmr_mv_sort = {\n\tset_variable = { name = pmr_mv_n value = 0 }\n\tset_variable = { name = pmr_mv_left value = 0 }\n'
             + ''.join(f'\tset_variable = {{ name = pmr_mv_rk_{b} value = -1 }}\n'
                       f'\tif = {{ limit = {{ var:pmr_mv_lv_{b} > 0 }} set_variable = {{ name = pmr_mv_rk_{b} value = -2 }} '
                       'change_variable = { name = pmr_mv_left add = 1 } }\n' for _j, b, _w in types)
             + '\twhile = {\n\t\tlimit = { var:pmr_mv_left > 0 }\n'
             '\t\tset_variable = { name = pmr_mv_best value = -1 }\n\t\tset_variable = { name = pmr_mv_bi value = 0 }\n'
             + ''.join(f'\t\tif = {{ limit = {{ var:pmr_mv_rk_{b} = -2 {w} > var:pmr_mv_best }} '
                       f'set_variable = {{ name = pmr_mv_best value = {w} }} set_variable = {{ name = pmr_mv_bi value = {j} }} }}\n'
                       for j, b, w in types if w)
             + ''.join(f'\t\tif = {{ limit = {{ var:pmr_mv_rk_{b} = -2 var:pmr_mv_best < 0 }} '
                       f'set_variable = {{ name = pmr_mv_best value = 0 }} set_variable = {{ name = pmr_mv_bi value = {j} }} }}\n'
                       for j, b, w in types if not w)
             + ''.join(f'\t\t{"if" if n == 0 else "else_if"} = {{ limit = {{ var:pmr_mv_bi = {j} }} '
                       f'set_variable = {{ name = pmr_mv_rk_{b} value = var:pmr_mv_n }} }}\n' for n, (j, b, _w) in enumerate(types))
             + '\t\telse = {   # nothing left waiting: stop\n\t\t\tset_variable = { name = pmr_mv_left value = 1 }\n'
             '\t\t\tchange_variable = { name = pmr_mv_n add = -1 }\n\t\t}\n'
             '\t\tchange_variable = { name = pmr_mv_n add = 1 }\n\t\tchange_variable = { name = pmr_mv_left add = -1 }\n\t}\n'
             '\tremove_variable = pmr_mv_best\n\tremove_variable = pmr_mv_bi\n\tremove_variable = pmr_mv_left\n}\n')
    return ''.join(o)


def pair_options(bk, pair):
    """[(tooltip key, icon)] per automation option of pairs(): the icon of its first method beyond none."""
    out = []
    for a, opt in enumerate(pair['options'], 1):
        on = [m for m in opt if m.blend or m.employment] or opt
        out.append((f'PMR_MVA_{short(bk)}_{a}', on[-1].texture))
    return out


# Pat 21:53Z: the Investments tab is a column of cards, one per building type, in the order and under the filters of
# the side Buildings panel's own list: the building's icon and its grid on the left, the AI weight on the right.
# 23:22Z: every card in the same columns: one icon column, then a grid box of the same width on every card (the widest
# type's recipe count, MV_COLS), recipe columns at the same x, the AI weight at the same x.
CARD_W, CARD_PAD, ICON_W, ICON_GAP = 540, 8, 60, 8
AI_W = 100   # the AI weight column's text
BUY_ICON = 20  # an owner's icon in the AI column's who-buys cells
CO_SIZE = 30   # the company's round icon on a card's building icon
AI_H = 82      # the AI column's height: label, weight and two rows of who-buys cells
LEFT_H = 78    # the icon column: the icon with the country's levels on it, its productivity under it (Pat 01:07Z)
MINI_H, MINI_GAP = 10, 4   # the automation and trade-off bars under the grid (Pat 01:07Z: "smaller bars")
CSW_H = 10     # the switching bar across the card's foot


def mv_cols(recipe_keys, pair_ui):
    return max(len(pair_ui[bk]['recipes']) if bk in pair_ui else len(keys) for bk, keys in recipe_keys.items())


def ai_column(bk, h, x, ind):
    """Pat, 2026-10-18 18:40Z, 21:53Z, 23:22Z: what the AI weighs a building type by, in the card's right column at x:
    its share of the country's AI weights over every building type on the tab (pmr_mv_sh_<b>, methods_view_effects),
    as the investors pick by weight. The weight is the type's AI value (pmr_ai_value_<b>: vanilla's with the policy and
    foreign-or-domestic additions, plus vanilla's profit and output terms at the country's average for the type, Pat
    21:10Z/21:32Z) at the state the grid's prices come from, times its priority group's slider (pmr_ipw_<group>). The
    breakdown is in the tooltip. Under it (Pat 2026-10-19 00:01Z), who would buy a new private level, two by two:
    each owner's icon and share (private_investment.buyer_odds), its name the tooltip."""
    b = short(bk)
    i1, i2, i3, i4 = ind + '\t', ind + '\t\t', ind + '\t\t\t', ind + '\t\t\t\t'
    cells = ''
    for r in range(2):
        cells += f'{i2}flowcontainer = {{\n'
        for key, icon, name in private_investment.BUYERS[2 * r:2 * r + 2]:
            cells += (f'{i3}flowcontainer = {{\n{i4}minimumsize = {{ {AI_W // 2} -1 }}\n{i4}spacing = 3\n'
                      f'{i4}tooltip = "{name}"\n{i4}using = tooltip_above\n'
                      f'{i4}icon = {{\n{i4}\tsize = {{ {BUY_ICON} {BUY_ICON} }}\n{i4}\ttexture = "{icon}"\n{i4}}}\n'
                      f'{i4}textbox = {{\n{i4}\tautoresize = yes\n{i4}\tparentanchor = vcenter\n{i4}\talign = left|nobaseline\n'
                      f'{i4}\tusing = fontsize_small\n{i4}\ttext = "PMR_MV_BUY_{key}_{b}"\n{i4}}}\n{i3}}}\n')
        cells += f'{i2}}}\n'
    return (f'{ind}icon = {{\n{i1}position = {{ {x - 8} {CARD_PAD} }}\n{i1}size = {{ 1 {h - 2 * CARD_PAD} }}\n'
            f'{i1}texture = "{methods_row.WHITE}"\n{i1}color = {{ 1 1 1 0.15 }}\n{i1}alwaystransparent = yes\n{ind}}}\n'
            f'{ind}flowcontainer = {{\n{i1}position = {{ {x} 0 }}\n{i1}parentanchor = vcenter\n{i1}direction = vertical\n'
            f'{i1}flowcontainer = {{\n{i2}direction = vertical\n'
            f'{i2}tooltip = "PMR_MV_AI_TT_{b}"\n{i2}using = tooltip_above\n'
            f'{i2}textbox = {{\n{i3}autoresize = yes\n{i3}align = left|nobaseline\n{i3}using = fontsize_small\n'
            f'{i3}text = "PMR_MV_AI_LABEL"\n{i2}}}\n'
            f'{i2}textbox = {{\n{i3}autoresize = yes\n{i3}align = left|nobaseline\n{i3}using = fontsize_large\n'
            f'{i3}text = "PMR_MV_AI_{b}"\n{i2}}}\n{i1}}}\n'
            + cells + f'{ind}}}\n')


def card_left(bk, ind):
    """Pat, 2026-10-19 01:07Z ("add level amount and productivity to the building cards"): the building's icon with
    the country's levels on it, as the company panel shows them, and the type's productivity span under it, as the
    Buildings list's header shows it."""
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    return (f'{ind}widget = {{\n{i1}size = {{ {ICON_W} {LEFT_H} }}\n{i1}datacontext = "[GetBuildingType(\'{bk}\')]"\n'
            f'{i1}icon = {{\n{i2}position = {{ 3 0 }}\n{i2}size = {{ 54 54 }}\n{i2}texture = "[BuildingType.GetIcon]"\n'
            f'{i2}tooltipwidget = {{\n{i3}FancyTooltip_BuildingType = {{}}\n{i2}}}\n'
            f'{i2}textbox = {{\n{i3}text = "[BuildingType.GetNumLevelsInCountryFormatted(GetPlayer.Self)]"\n'
            f'{i3}autoresize = yes\n{i3}position = {{ 2 -1 }}\n{i3}parentanchor = bottom\n{i3}align = left|nobaseline\n'
            f'{i3}alwaystransparent = yes\n{i2}}}\n{i1}}}\n'
            f'{i1}textbox = {{\n{i2}position = {{ -{CARD_PAD} 57 }}\n{i2}size = {{ {ICON_W + CARD_PAD + ICON_GAP} 20 }}\n'
            f'{i2}align = hcenter|nobaseline\n{i2}using = fontsize_small\n'
            f'{i2}text = "[BuildingType.GetProductivitySpanDesc(GetPlayer.Self)]"\n'
            f'{i2}tooltip = "PRODUCTIVITY_SPAN_TOOLTIP"\n{i2}using = tooltip_above\n{i1}}}\n{ind}}}\n')


def card_bars(bk, opt_groups, auto, width, ind):
    """Pat, 2026-10-19 01:07Z ("add the automation and pm2 trade offs below the pm cards as smaller bars"): under the
    grid, the country's automation bar (split types: each automation option's share of the levels) and one bar per
    second group (trade-offs, treatment), as the details panel draws them, at the state the grid's figures come from
    (methods_view_effects copies pmr_ash_* and pmr_x*_*). Returns (gui, height)."""
    b = short(bk)
    gt = lambda e, n: f"GreaterThan_CFixedPoint({e}, '(CFixedPoint){n}')"    # noqa: E731
    bars = []
    if auto:
        _group, levels = auto
        sl = []
        for a, (key, _tex, _) in enumerate(levels, 1):
            name, rgb = AUTO_COLORS[round((a - 1) * (len(AUTO_COLORS) - 1) / max(1, len(levels) - 1))]
            e = mv_read(f'pmr_ash_{a}_{b}')
            sl.append((f'{key}, {name.lower()}', gt(e, 0), f"FixedPointToInt(Multiply_CFixedPoint({e}, '(CFixedPoint)100'))",
                       'no', rgb, None))
        bars.append((sl, f'PMR_MV_AUTO_TT_{b}'))
    for gi, _mode, none, _none_tex, os_ in opt_groups:
        e = mv_read(f'pmr_xn_{gi}_{b}')
        sl = [(f'{none}, grey', gt(e, 0), f'FixedPointToInt({e})', 'no', OPTION_NONE_COLOR, None)]
        for k, o in enumerate(os_):
            name, rgb = OPTION_COLORS[k % len(OPTION_COLORS)]
            e = mv_read(f'pmr_x_{o.j}_{b}')
            sl.append((f'{o.key}, {name.lower()}', gt(e, 0), f'FixedPointToInt({e})', 'no', rgb, None))
        bars.append((sl, f'PMR_MV_OPT_TT_{b}_{gi}'))
    out = ''.join(slice_bar(sl, (width, MINI_H), 0, ind, [(None, tip)]) for sl, tip in bars)
    return out, len(bars) * (MINI_H + MINI_GAP)


def company_badge(bk, h, ind):
    """The card's company mark (company_mark): vanilla's static selection outline round the card, and its company's
    icon, a round button that opens the company (as production_methods.gui's company_owned_button), on the building
    icon's corner."""
    b = short(bk)
    on = methods_row.gt(mv_read(f'pmr_mv_cf_{b}'), 0)
    i1, i2 = ind + '\t', ind + '\t\t'
    return (f'{ind}icon = {{\n{i1}visible = "[{on}]"\n{i1}size = {{ 100% 100% }}\n'
            f'{i1}texture = "gfx/interface/selections/selected_square_selection.dds"\n{i1}spriteType = Corneredtiled\n'
            f'{i1}spriteborder = {{ 22 22 }}\n{i1}texture_density = 2\n{i1}alwaystransparent = yes\n{ind}}}\n'
            f'{ind}button_icon_round = {{\n{i1}visible = "[{on}]"\n'
            f'{i1}position = {{ {CARD_PAD + 3 + 54 - CO_SIZE + 6} {CARD_PAD + 54 - CO_SIZE + 6} }}\n'
            f'{i1}size = {{ {CO_SIZE} {CO_SIZE} }}\n'
            f'{i1}datacontext = "[{MV_COUNTRY}.MakeScope.Var(\'pmr_mv_co_{b}\').GetCharacter]"\n'
            f'{i1}datacontext = "[Character.GetCompany]"\n'
            f'{i1}onclick = "[InformationPanelBar.OpenCompanyPanel(Company.Self)]"\n'
            f'{i1}tooltip = "GO_TO_BUTTON_COMPANY"\n{i1}using = tooltip_above\n'
            f'{i1}blockoverride "icon" {{\n{i2}texture = "[Company.GetCompanyType.GetIcon]"\n{i1}}}\n'
            f'{i1}blockoverride "icon_size" {{\n{i2}size = {{ 75% 75% }}\n{i1}}}\n{ind}}}\n')


def methods_view_gui(recipe_keys, recipe_tex, pair_ui=None, ai=None, companies=None, opt_ui=None, auto_ui=None):
    """One card per building type the player has (pmr_mv_card_<b>): the building's icon, then its grid, the recipe x
    automation pairs where the type has them (Pat, 2026-10-18 18:17Z) or one row of recipes, every grid box MV_COLS
    columns wide so all cards line up (Pat 23:22Z), with the AI weight beside it (ai_column). pmr_methods_cards stands in
    each item of the side Buildings panel's list (patch_browser_tabs), under the item's building type, and makes only
    that type's card: a card per item per type would be thousands of widgets."""
    pair_ui, ai, companies, opt_ui, auto_ui = pair_ui or {}, ai or {}, companies or {}, opt_ui or {}, auto_ui or {}
    cols = mv_cols(recipe_keys, pair_ui)
    box_w = methods_row.pairs_size(cols, 1)[0]
    ai_x = CARD_PAD + ICON_W + ICON_GAP + box_w + 14
    if ai_x + AI_W > CARD_W:
        raise SystemExit(f'methods_view_gui: {cols} recipe columns leave no room for the AI weight')
    cards, picks, slots = '', '', ''
    for bk, keys in recipe_keys.items():
        b = short(bk)
        pr = pair_ui.get(bk)
        grid, gh = '', 0
        if not (pr and pr.get('split')):   # the recipes are the targets: one row of them
            grid = methods_row.recipes_grid(bk, list(enumerate(recipe_tex[bk], 1)), mv_read,
                                            lambda i, b=b: f'PMR_MV_TIP_{b}_{i}', '\t\t\t\t', cols=cols)
            gh = methods_row.pairs_size(cols, 1)[1]
        if pr:
            names = pr.get('keys') or recipe_keys[bk]
            grid += methods_row.pairs_grid(
                bk, [(i, recipe_tex[bk][i - 1]) for i in pr['recipes']], pair_options(bk, pr), mv_read,
                lambda i, a, b=b, names=names: f'PMR_MVP_TIP_{b}_{i}_{a}' if a else f'{names[i - 1]}', '\t\t\t\t',
                cols=cols)
            gh += (6 if gh else 0) + methods_row.pairs_size(cols, len(pr['options']))[1]
        mini, mh = card_bars(bk, opt_ui.get(bk, []), auto_ui.get(bk) if pr and pr.get('split') else None,
                             box_w, '\t\t\t\t')
        grid = f'\t\t\tflowcontainer = {{\n\t\t\t\tdirection = vertical\n\t\t\t\tspacing = {MINI_GAP}\n{grid}{mini}\t\t\t}}\n'
        inner = max(LEFT_H, gh + mh, AI_H if bk in ai else 0)
        h = inner + 2 * CARD_PAD + CSW_H + MINI_GAP
        # Pat, 2026-10-19 01:07Z: the switching bar across the card's foot (switch_bar), at the country's biggest state
        foot = switch_bar(mv_read(f'pmr_c_sw_{b}'), mv_read(f'pmr_c_swd_{b}'), (CARD_W - 2 * CARD_PAD, CSW_H), '\t\t',
                          f'PMR_CSW_TT_{b}', f'PMR_CSW_IDLE_{b}',
                          place=f'\t\t\tposition = {{ {CARD_PAD} {h - CARD_PAD - CSW_H} }}\n') if bk in recipe_keys else ''
        cards += (f'\ttype pmr_mv_card_{b} = widget {{\n\t\tvisible = "[{methods_row.gt(mv_read(f"pmr_mv_lv_{b}"), 0)}]"\n'
                  f'\t\tsize = {{ {CARD_W} {h} }}\n'
                  '\t\tbackground = {\n\t\t\tusing = entry_bg_simple\n\t\t}\n'
                  f'\t\tflowcontainer = {{\n\t\t\tposition = {{ {CARD_PAD} {CARD_PAD} }}\n\t\t\tspacing = {ICON_GAP}\n'
                  + card_left(bk, '\t\t\t') + grid + '\t\t}\n'
                  + (ai_column(bk, inner + 2 * CARD_PAD, ai_x, '\t\t') if bk in ai else '')
                  + (company_badge(bk, h, '\t\t') if bk in companies else '') + foot + '\t}\n\n')
        same = f"ObjectsEqual(BuildingType.Self, GetBuildingType('{bk}').Self)"
        picks += (f'\t\tflowcontainer = {{\n\t\t\tdatamodel = "[DataModelRepeatedItem(Select_int32({same}, '
                  "'(int32)1', '(int32)0'))]\"\n"
                  f'\t\t\titem = {{\n\t\t\t\tpmr_mv_card_{b} = {{}}\n\t\t\t}}\n\t\t}}\n')
        here = (f"EqualTo_int32(FixedPointToInt({mv_read(f'pmr_mv_rk_{b}')}), "
                'PdxGuiWidget.AccessParent.GetIndexInDataModel)')
        slots += (f'\t\tflowcontainer = {{\n\t\t\tposition = {{ 7 0 }}\n'
                  f'\t\t\tdatamodel = "[DataModelRepeatedItem(Select_int32({here}, '
                  "'(int32)1', '(int32)0'))]\"\n"
                  f'\t\t\titem = {{\n\t\t\t\tpmr_mv_card_{b} = {{}}\n\t\t\t}}\n\t\t}}\n')
    return ('# GENERATED by tools/pmr/generate.py (methods_view_gui). The side Buildings panel\'s Investments tab: a card\n'
            '# per building type; grids by tools/pmr/methods_row.py.\n'
            'types pmr_methods_view {\n' + cards
            + '\t# in an item of the Buildings list (BuildingType = the item\'s): makes its own type\'s card only\n'
            '\ttype pmr_methods_cards = container {\n\t\tposition = { 7 0 }\n' + picks + '\t}\n\n'
            '\t# Pat 23:53Z, sorted by AI weight: slot k of MV_SLOTS\'s list makes the card of the type in place k\n'
            '\t# (pmr_mv_rk_<b>, pmr_mv_sort); its children read the slot\'s index from it\n'
            '\ttype pmr_methods_slot = container {\n' + slots + '\t}\n}\n')


def methods_view_custom_loc(recipe_keys, pair_ui=None):
    out = ['\n# Country scope. A note after each recipe\'s or pair\'s profit in the Owners\' Methods tab.\n']
    for bk, pr in (pair_ui or {}).items():
        b = short(bk)
        for i, a in sorted(pr['econ']):
            out.append(f'pmr_mvcn_{b}_{i}_{a} = {{\n\ttype = country\n\trandom_valid = no\n'
                       f'\ttext = {{\n\t\ttrigger = {{ var:pmr_cbi_{b} = {i} var:pmr_cba_{b} = {a} }}\n'
                       '\t\tlocalization_key = PMR_PAIR_NOTE_BEST\n\t}\n'
                       f'\ttext = {{\n\t\ttrigger = {{ var:pmr_cav_{i}_{a}_{b} = 0 }}\n\t\tlocalization_key = PMR_PICK_NOTE_LOCKED\n\t}}\n'
                       '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n')
    for bk, keys in recipe_keys.items():
        b = short(bk)
        if (pair_ui or {}).get(bk, {}).get('split'):
            continue   # no recipe row (methods_view_gui)
        for i in range(1, len(keys) + 1):
            out.append(f'pmr_mvnote_{b}_{i} = {{\n\ttype = country\n\trandom_valid = no\n'
                       f'\ttext = {{\n\t\ttrigger = {{ var:pmr_pbest_{b} = {i} }}\n\t\tlocalization_key = PMR_PICK_NOTE_BEST\n\t}}\n'
                       f'\ttext = {{\n\t\ttrigger = {{ var:pmr_rav_{i}_{b} = 0 }}\n\t\tlocalization_key = PMR_PICK_NOTE_LOCKED\n\t}}\n'
                       f'\ttext = {{\n\t\ttrigger = {{ var:pmr_rveto_{i}_{b} = 1 }}\n\t\tlocalization_key = PMR_PICK_NOTE_VETO\n\t}}\n'
                       '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n')
    return ''.join(out)


def methods_view_loc(recipe_keys, pair_ui=None, ai=None, parts=None, opt_ui=None, auto_ui=None):
    loc = [' PMR_MV_HEADER:0 "Production Methods"',   # Pat 21:53Z, with no explainer text under it
           ' PMR_BB_TAB_INVEST:0 "Policies"',   # Pat 2026-10-19 01:07Z
           ' PMR_BB_TAB_BUILDINGS:0 "Buildings"',
           ' PMR_PAIR_NOTE_BEST:0 " (best combination)"',
           ' PMR_MV_AI_LABEL:0 "Investment chance"', ' PMR_MV_POLICY:0 "Policy"', ' PMR_MV_POL_WORKS:0 "Expanded Works"']
    for bk, keys in recipe_keys.items():
        b = short(bk)
        if (pair_ui or {}).get(bk, {}).get('split'):
            continue   # no recipe row (methods_view_gui)
        for i, key in enumerate(keys, 1):
            lines = methods_row.recipe_tip_lines(bk, i, key, mv_read, f"[{MV_COUNTRY}.GetCustom('pmr_mvnote_{b}_{i}')]")
            lines += [f"Picked: #bold [{mv_read(f'pmr_mv_ps_{i}_{b}')}|%0]#!",
                      f"Running: #bold [{mv_read(f'pmr_c_sh_{i}_{b}')}|%0]#!"]
            loc.append(f' PMR_MV_TIP_{b}_{i}:0 "' + '\\n'.join(lines) + '"')
    for bk, group in (ai or {}).items():
        if bk not in recipe_keys:
            continue
        b = short(bk)
        mult = f"{MV_COUNTRY}.MakeScope.ScriptValue('{private_investment.VAR.format(group)}')"
        aiv, aib = mv_read(f'pmr_mv_aiv_{b}'), mv_read(f'pmr_mv_aib_{b}')
        term = mv_read(f'pmr_pterm_{b}')
        policy = f'Subtract_CFixedPoint(Subtract_CFixedPoint({aiv}, {aib}), {term})'
        # Pat 21:53Z: less text, on the card and in the tooltip; 23:22Z: the card shows the share of all weights
        loc.append(f' PMR_MV_AI_{b}:0 "#bold [{mv_read(f"pmr_mv_sh_{b}")}|%1]#!"')
        loc += [f' PMR_MV_BUY_{key}_{b}:0 "[{mv_read(f"pmr_mv_b{key}_{b}")}|%0]"' for key, *_r in private_investment.BUYERS]
        # Pat 2026-10-19 00:01Z: Policy opens a nested tooltip with each policy's part, the ones not 0; Expanded Works
        # (test build) is what is left of Policy once the parts are taken off
        rest = policy
        pol = [f'#bold $PMR_MV_POLICY$ [{policy}|=+0]#!']
        for key, name in (parts or {}).get(bk, []):
            if name:
                val = mv_read(f'pmr_mv_p{key}_{b}')
                rest = f'Subtract_CFixedPoint({rest}, {val})'
            else:
                val, name = rest, 'PMR_MV_POL_WORKS'
            loc.append(f' PMR_MV_POL_{key}_{b}:0 "\\n${name}$: [{val}|=+0]"')
            nonzero = f"Or(GreaterThan_CFixedPoint({val}, '(CFixedPoint)0.5'), LessThan_CFixedPoint({val}, '(CFixedPoint)-0.5'))"
            pol.append(f"[SelectLocalization({nonzero}, 'PMR_MV_POL_{key}_{b}', 'PMR_EMPTY')]")
        loc.append(f' PMR_MV_POL_TT_{b}:0 "' + ''.join(pol) + '"')
        loc.append(f' PMR_MV_AI_TT_{b}:0 "#bold $PMR_MV_AI_LABEL$ [{mv_read(f"pmr_mv_w_{b}")}|0] of [{mv_read("pmr_mv_wsum")}|0]#!\\n'
                   f'Base: [{aib}|0]\\n'
                   f'#tooltippable;tooltip:[{MV_COUNTRY}.GetTooltipTag],PMR_MV_POL_TT_{b} $PMR_MV_POLICY$#!: [{policy}|=+0]\\n'
                   f'Profit and output: [{term}|=+0]\\n'
                   f'Priority: ×[{mult}|2] from $PMR_IPW_GROUP_{group}$"')
    for bk, pr in (pair_ui or {}).items():
        b = short(bk)
        for a, opt in enumerate(pr['options'], 1):
            on = [m for m in opt if m.blend or m.employment] or opt
            loc.append(f' PMR_MVA_{b}_{a}:0 "' + ' + '.join(f'${m.key}$' for m in on) + '"')
        names = pr.get('keys') or recipe_keys[bk]
        for i, a in sorted(pr['econ']):
            # with the split each cell is a retool target: how much of the country picks it, and runs it
            more = (f"\\nPicked: #bold [{mv_read(f'pmr_mv_ps_{pr['index'][(i, a)]}_{b}')}|%0]#!"
                    f"\\nRunning: #bold [{mv_read(f'pmr_c_sh_{pr['index'][(i, a)]}_{b}')}|%0]#!"
                    if pr.get('split') else '')
            loc.append(f' PMR_MVP_TIP_{b}_{i}_{a}:0 "#bold ${names[i - 1]}$#! + #bold $PMR_MVA_{b}_{a}$#!\\n'
                       f"@money![{mv_read(f'pmr_cp_{i}_{a}_{b}')}|0] per level a week"
                       f"[{MV_COUNTRY}.GetCustom('pmr_mvcn_{b}_{i}_{a}')]{more}\"")
    # the bars under the grid (card_bars): the group's name, then each option that holds a share
    def shares(tip, head, rows):
        body = []
        for n, (key, e, f) in enumerate(rows):
            loc.append(f' {tip}_{n}:0 "\\n${key}$: #bold [{e}|{f}#!"')
            body.append(f"[SelectLocalization({methods_row.gt(e, 0)}, '{tip}_{n}', 'PMR_EMPTY')]")
        loc.append(f' {tip}:0 "#bold ${head}$#!' + ''.join(body) + '"')
    for bk, (group, levels) in (auto_ui or {}).items():
        b = short(bk)
        if bk in recipe_keys and (pair_ui or {}).get(bk, {}).get('split'):
            shares(f'PMR_MV_AUTO_TT_{b}', group,
                   [(key, mv_read(f'pmr_ash_{a}_{b}'), '%0]') for a, (key, _t, _) in enumerate(levels, 1)])
    for bk, groups in (opt_ui or {}).items():
        b = short(bk)
        if bk not in recipe_keys:
            continue
        for gi, _mode, none, _tex, os_ in groups:
            shares(f'PMR_MV_OPT_TT_{b}_{gi}', os_[0].group,
                   [(none, mv_read(f'pmr_xn_{gi}_{b}'), '0]%')] + [(o.key, mv_read(f'pmr_x_{o.j}_{b}'), '0]%') for o in os_])
    return loc


def pick_custom_loc(pick_ui):
    """State scope: pmr_pick_<b>, the pick's name; pmr_sw_now_<b> and pmr_sw_to_<b>, the default and the pick the
    switching bar fills toward (switch_effect); country scope pmr_csw_now_<b> and pmr_csw_to_<b>, the same at the
    country's biggest state (pmr_c_now_<b>, pmr_c_swto_<b>)."""
    out = []
    for bk, keys in pick_ui.items():
        b = short(bk)
        for name, typ, var in (('sw_now', 'state', f'pmr_best_now_{b}'), ('sw_to', 'state', f'pmr_swto_{b}'),
                               ('csw_now', 'country', f'pmr_c_now_{b}'), ('csw_to', 'country', f'pmr_c_swto_{b}')):
            out.append(f'pmr_{name}_{b} = {{\n\ttype = {typ}\n\trandom_valid = no\n'
                       + ''.join(f'\ttext = {{\n\t\ttrigger = {{ var:{var} = {i} }}\n\t\tlocalization_key = {key}\n\t}}\n'
                                 for i, key in enumerate(keys, 1))
                       + '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n')
        out.append(f'pmr_pick_{b} = {{\n\ttype = state\n\trandom_valid = no\n'
                   + ''.join(f'\ttext = {{\n\t\ttrigger = {{ var:pmr_pbest_{b} = {i} }}\n\t\tlocalization_key = {key}\n\t}}\n'
                             for i, key in enumerate(keys, 1))
                   + '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n')
    return ''.join(out)


def pick_loc(pick_ui):
    """The pick row, and the notes the Policies cards' tooltips put after a recipe's profit."""
    loc = [' PMR_PICK_NOTE_BEST:0 " (most profitable)"', ' PMR_PICK_NOTE_LOCKED:0 " (not available)"',
           ' PMR_PICK_NOTE_VETO:0 " (input at price cap)"']
    for bk, keys in pick_ui.items():
        b = short(bk)

        def var(name, f='0'):
            return f"[Building.GetState.MakeScope.Var('{name}').GetValue|{f}]"
        loc.append(f' PMR_PICK_ROW_{b}:0 "Most profitable: #bold [Building.GetState.GetCustom(\'pmr_pick_{b}\')]#!, '
                   f'@money!{var(f"pmr_prm_{b}")} per level a week"')
        # the switching bar (switch_bar): from, to, months
        loc.append(f' PMR_SW_TT_{b}:0 "#bold [Building.GetState.GetCustom(\'pmr_sw_now_{b}\')]#! → '
                   f'#bold [Building.GetState.GetCustom(\'pmr_sw_to_{b}\')]#!\\n{var(f"pmr_sw_{b}")} of {SWITCH_MONTHS} months"')
        loc.append(f' PMR_CSW_TT_{b}:0 "#bold [GetPlayer.GetCustom(\'pmr_csw_now_{b}\')]#! → '
                   f'#bold [GetPlayer.GetCustom(\'pmr_csw_to_{b}\')]#!\\n'
                   f"[GetPlayer.MakeScope.Var('pmr_c_sw_{b}').GetValue|0] of {SWITCH_MONTHS} months\"")
        loc.append(f' PMR_CSW_IDLE_{b}:0 "#bold [GetPlayer.GetCustom(\'pmr_csw_now_{b}\')]#!"')
    return loc


def automation_loc(auto_ui):
    """The automation bar's tooltips, from vanilla's own names, so every language has them."""
    loc = []
    for bk, (group, levels) in auto_ui.items():
        b = short(bk)
        lines = [f"${key}$: #bold [Building.GetState.MakeScope.Var('pmr_ash_{a}_{b}').GetValue|%0]#!"
                 for a, (key, _, _) in enumerate(levels, 1)]
        loc.append(f' PMR_AUTO_TOOLTIP_{b}:0 "#bold ${group}$#!\\n' + '\\n'.join(lines) + '"')
    return loc


def patch_option_bars(text, opt_ui, auto_ui=None, pick_ui=None):
    """building_details_panel.gui: an empty block at the end of condensed_building_information,
    filled only by the details panel's own instance, so the Buildings tab rows stay as they are.
    The automation bars come first, right under the recipe bar."""
    auto_ui, pick_ui = auto_ui or {}, pick_ui or {}
    if not opt_ui and not auto_ui and not pick_ui:
        return text
    end = '\t\t\t}\n\t\t}\n\t}\n\n\ttype building_type_nationalize_button = '
    if text.count(end) != 1:
        raise SystemExit('building_details_panel.gui: condensed_building_information no longer ends before '
                         'building_type_nationalize_button; update patch_option_bars')
    at = text.index(end) + len('\t\t\t}\n\t\t}\n')
    text = text[:at] + '\n\t\t# PMR: second group bars (details panel only)\n\t\tblock "pmr_option_bars" {}\n' + text[at:]
    inst = '\t\tcondensed_building_information = {\n\t\t\tmargin = { 7 0 }\n'
    if text.count(inst) != 1:
        raise SystemExit('building_details_panel.gui: expected one condensed_building_information with margin 7; '
                         'update patch_option_bars')
    at = text.index(inst) + len(inst)
    return (text[:at] + '\n\t\t\tblockoverride "pmr_option_bars" {\n'
            '\t\t\t\tflowcontainer = {\n\t\t\t\t\tdirection = vertical\n\t\t\t\t\tignoreinvisible = yes\n'
            '\t\t\t\t\tmargin_bottom = 4\n'
            + ''.join(pick_row(bk, '\t\t\t\t\t') for bk in pick_ui)
            + ''.join(automation_bar(bk, group, levels, '\t\t\t\t\t') for bk, (group, levels) in auto_ui.items())
            + ''.join(option_bars(bk, groups, '\t\t\t\t\t') for bk, groups in opt_ui.items())
            + '\t\t\t\t}\n\t\t\t}\n' + text[at:])


def patch_grid_instance(text, buildings, ind, name, outer, cell, anchor='', extra='', labour_icon=True, also=()):
    """The one use of vanilla's condensed_building_information_pms in a GUI file, at indent ind: on a
    PMR building type it is hidden and the fixed labour icon stands in its place. The grid inside is
    a fixedgridbox, which keeps a column for every production method group even when the item is
    hidden: with a share and a lock group per recipe, an iron mine's 13 groups made the details
    panel's row 936 px wide and pushed the panel's contents off its left edge (seen in 1.14.5).
    Hiding the grid's items is therefore not enough; the whole grid goes. The building types in also
    (AUTO_BEST) lose the grid too, with nothing in its place."""
    inst = f'{ind}condensed_building_information_pms = {{\n'
    if text.count(inst) != 1:
        raise SystemExit(f'{name}: expected one condensed_building_information_pms at this indent, found '
                         f'{text.count(inst)}; update patch_grid_instance')
    at = text.index(inst) + len(inst)
    end = block_end(text, text.index(inst))
    icons = ''.join(f'{ind}\t\ticon = {{\n{ind}\t\t\tvisible = "[{is_type(bk)}]"\n'
                    f'{ind}\t\t\tsize = {{ 80% 80% }}\n{ind}\t\t\tparentanchor = center\n'
                    f'{ind}\t\t\ttexture = "gfx/interface/icons/production_method_icons/pmr_labour_{short(bk)}.dds"\n'
                    f'{ind}\t\t}}\n' for bk in buildings)
    labour = (f'\n{ind}# PMR: the fixed labour icon in the grid\'s place\n'
              f'{ind}widget = {{\n{ind}\tvisible = "[{any_type(buildings)}]"\n{ind}\tsize = {{ {outer[0]} {outer[1]} }}\n'
              + (f'{ind}\tparentanchor = {anchor}\n' if anchor else '') +
              f'{ind}\twidget = {{\n{ind}\t\tsize = {{ {cell} {cell} }}\n{ind}\t\tparentanchor = vcenter\n'
              f'{ind}\t\ttooltip = "PMR_LABOUR_ICON_TOOLTIP"\n'
              f'{ind}\t\tusing = tooltip_ne\n{icons}{ind}\t}}\n{extra}{ind}}}')
    hide = (text[:at] + f'{ind}\t# PMR: no grid on PMR building types\n'
            f'{ind}\tvisible = "[Not({any_type(list(buildings) + list(also))})]"\n')
    if not labour_icon:
        return hide + text[at:]
    return hide + text[at:end] + labour + text[end:]


def patch_building_panel(recipe_tex, text, opt_ui=None, also=(), auto_ui=None, pick_ui=None):
    buildings = list(recipe_tex)
    """Vanilla building_details_panel.gui with two changes, asserted so a game update that moves
    either anchor fails generation instead of shipping a panel that silently lost them."""
    # 1. The production method row: no grid on a PMR building type, and nothing in its place (Pat,
    # 2026-10-13: no goods icon; the recipe row below takes the room).
    text = patch_grid_instance(text, buildings, '\t\t\t\t\t', 'building_details_panel.gui', outer=(208, 70), cell=70,
                               labour_icon=False, also=also)
    inst = '\t\t\t\t\tcondensed_building_information_pms = {\n'
    ind = '\t\t\t\t\t'
    # A flowcontainer still makes room for hidden children unless told not to (vanilla sets this
    # wherever it hides some).
    fc = text.rfind('flowcontainer = {\n', 0, text.index(inst))
    fc_at = fc + len('flowcontainer = {\n')
    if text[fc_at:text.index(inst)].count('{') != 0:
        raise SystemExit('building_details_panel.gui: the method grid is no longer a direct child of a '
                         'flowcontainer; update patch_building_panel')
    text = text[:fc_at] + f'{ind}# PMR: hidden children take no room\n{ind}ignoreinvisible = yes\n' + text[fc_at:]

    # 2. The recipe bar beside it, in the details panel's PMs / employment / cash reserves row.
    anchor = '\t\t\t\tblock "extra_items_in_production_methods_list" {}\n'
    if text.count(anchor) != 1:
        raise SystemExit(f'building_details_panel.gui: expected one {anchor.strip()!r}, found '
                         f'{text.count(anchor)}; the panel changed in this build, update patch_building_panel')
    text = text.replace(anchor, anchor + ''.join(recipe_bar(bk, short(bk), recipe_tex[bk]) for bk in buildings))
    text = patch_input_mults(text)
    return patch_option_bars(patch_owners(text, recipe_tex), opt_ui or {}, auto_ui or {}, pick_ui or {})


def patch_input_mults(text):
    """Pat, 2026-10-19 01:07Z: the Process view lists an input's modifier (Fabric input +5%) with the outputs' on the
    right. Beside each input's amount on the left, that good's goods_input_<good>_mult from the same list
    (Building.GetProducedModifiers), shown while it isn't 0."""
    dm = 'datamodel = "[Building.AccessConsumedGoods]"\n'
    at = text.find(dm)
    amount = 'raw_text = "#bold #n [FixedPointToInt(Building.GetConsumption(Goods.Self))|D]#!#!"\n'
    if at < 0 or text.find(amount, at) < 0:
        raise SystemExit('building_details_panel.gui: the Process inputs list changed; update patch_input_mults')
    box = text.rindex('textbox = {', 0, text.index(amount, at))
    ind = text[text.rindex('\n', 0, box) + 1:box]
    end = block_end(text, box)
    key = "Concatenate3('goods_input_', Goods.GetKey, '_mult')"
    i1 = ind + '\t'
    mult = (f'\n{ind}# PMR: this input\'s modifier\n{ind}textbox = {{\n'
            f'{i1}visible = "[NotZero_CFixedPoint(Building.GetProducedModifiers.GetValueFor({key}))]"\n'
            f'{i1}raw_text = "[Building.GetProducedModifiers.GetFormattedValueFor({key})]"\n'
            f'{i1}autoresize = yes\n{i1}parentanchor = left|vcenter\n{i1}widgetanchor = left|vcenter\n'
            f'{i1}align = left|nobaseline\n{i1}using = fontsize_small\n{ind}}}')
    return text[:end] + mult + text[end:]


# Pat, 2026-10-13: a Production Method column in the Owners list, with the icons of the recipes each
# owner's levels run. PMR knows the government's levels per recipe (pmr_lvg_*) and the private ones
# only together (pmr_lvp_*), so a government row shows the government's recipes and every private
# row the private owners' together. On a PMR building type the vanilla header and rows are hidden
# and these drawn instead, with the columns narrowed to make room: owner 230 (icon 30 + name 200),
# production method 120, levels owned 90, dividends 100, the panel's 540.
OWN_NAME_W, OWN_PM_W, OWN_LEVELS_W = 200, 120, 90


def owners_cell(bk, textures):
    """Government rows show the governments' levels (pmr_lvg_*), at home and abroad, where every government's
    levels are counted together, the player's investors leave them alone (Pat 20:54Z) and the player's
    government retools its own with the upgrade button (Pat 21:26Z); private rows show pmr_lvp_*."""
    b = short(bk)
    lvg, lvp = ('pmr_rlvg', 'pmr_rlvp') if b in SPLIT_BARS else ('pmr_lvg', 'pmr_lvp')   # by plain recipe with the split
    rows = []
    for side, gov in (('gov', True), ('priv', False)):
        who = 'BuildingOwnership.IsCountryOwned' if gov else 'Not(BuildingOwnership.IsCountryOwned)'

        def shown(i):
            if not gov:
                return f"GreaterThan_CFixedPoint({state_var(b, f'{lvp}_{i}')}, '(CFixedPoint)0')"
            return f"GreaterThan_CFixedPoint({state_var(b, f'{lvg}_{i}')}, '(CFixedPoint)0')"
        icons = ''.join(
            '\t\t\t\t\t\t\t\t\ticon = {\n'
            f'\t\t\t\t\t\t\t\t\t\tvisible = "[{shown(i)}]"\n'
            f'\t\t\t\t\t\t\t\t\t\tsize = {{ 26 26 }}\n\t\t\t\t\t\t\t\t\t\ttexture = "{tex}"\n'
            '\t\t\t\t\t\t\t\t\t}\n' for i, tex in enumerate(textures, 1))
        tooltip = f'PMR_OWNERS_GOV_TOOLTIP_{b}' if gov else f'PMR_OWNERS_PRIV_TOOLTIP_{b}'
        rows.append('\t\t\t\t\t\t\t\tflowcontainer = {\n'
                    f'\t\t\t\t\t\t\t\t\tvisible = "[And({is_type(bk)}, {who})]"\n'
                    '\t\t\t\t\t\t\t\t\tparentanchor = center\n\t\t\t\t\t\t\t\t\tspacing = 2\n'
                    f'\t\t\t\t\t\t\t\t\ttooltip = "{tooltip}"\n'
                    '\t\t\t\t\t\t\t\t\tusing = tooltip_above\n'
                    + icons + '\t\t\t\t\t\t\t\t}\n')
    return ''.join(rows)


def patch_owners(text, recipe_tex):
    buildings = list(recipe_tex)
    pmr = any_type(buildings)

    def once(old):
        if text.count(old) != 1:
            raise SystemExit(f'building_details_panel.gui: expected one {old.strip()[:60]!r}, found {text.count(old)}; '
                             'the Owners list changed in this build, update patch_owners')
        return text.index(old)

    # the section stacks its children: hidden ones must take no room
    sec = '\t\t### DETAILED BUILDING OWNERSHIP\n\t\tflowcontainer = {\n'
    at = once(sec) + len(sec)
    text = text[:at] + '\t\t\tignoreinvisible = yes  # PMR\n' + text[at:]

    # header
    head = '\t\t\tflowcontainer = {\n\t\t\t\tparentanchor = hcenter\n\t\t\t\tsort_button = {\n\t\t\t\t\tsize = { 320 30 }\n'
    at = once(head)
    end = block_end(text, at)
    vanilla = text[at:end]
    ours = (vanilla.replace('size = { 320 30 }', f'size = {{ {30 + OWN_NAME_W} 30 }}')
            .replace('\t\t\t\tsort_button = {\n\t\t\t\t\tsize = { 120 30 }',
                     f'\t\t\t\tsort_button = {{\n\t\t\t\t\tsize = {{ {OWN_PM_W} 30 }}\n\t\t\t\t\ttext = "PMR_OWNERS_PM_HEADER"\n'
                     '\t\t\t\t\talign = hcenter|nobaseline\n\t\t\t\t}\n\n'
                     f'\t\t\t\tsort_button = {{\n\t\t\t\t\tsize = {{ {OWN_LEVELS_W} 30 }}'))
    if ours.count('PMR_OWNERS_PM_HEADER') != 1 or str(30 + OWN_NAME_W) not in ours:
        raise SystemExit('building_details_panel.gui: the Owners header columns changed; update patch_owners')
    ours = ours.replace('\t\t\tflowcontainer = {\n', f'\t\t\t# PMR: Owners header with a Production Method column\n'
                        f'\t\t\tflowcontainer = {{\n\t\t\t\tvisible = "[{pmr}]"\n', 1)
    text = (text[:at] + vanilla.replace('\t\t\tflowcontainer = {\n', f'\t\t\tflowcontainer = {{\n\t\t\t\tvisible = "[Not({pmr})]"\n', 1)
            + '\n\n' + ours + text[end:])

    # rows
    row = '\t\t\t\t\t\tusing = building_ownership_share_tooltip\n\t\t\t\t\t\tflowcontainer = {\n\t\t\t\t\t\t\tmargin_bottom = 4\n'
    at = once(row) + len('\t\t\t\t\t\tusing = building_ownership_share_tooltip\n')
    end = block_end(text, at)
    vanilla = text[at:end]
    lvl = '\t\t\t\t\t\t\ttextbox = {\n\t\t\t\t\t\t\t\tsize = { 120 30 }\n\t\t\t\t\t\t\t\ttext = "[BuildingOwnership.GetLevel|v]"\n'
    if vanilla.count(lvl) != 1 or vanilla.count('ownership_list_name = {\n') != 3 or vanilla.count('blockoverride "oln_label"') != 3:
        raise SystemExit('building_details_panel.gui: the Owners row changed; update patch_owners')
    ours = vanilla.replace('ownership_list_name = {\n', f'ownership_list_name = {{\n\t\t\t\t\t\t\t\tminimumsize = {{ {OWN_NAME_W} 30 }}\n')
    ours = re.sub(r'blockoverride "oln_label"\s*\{\n', lambda m: m.group(0) + f'\t\t\t\t\t\t\t\t\tmaximumsize = {{ {OWN_NAME_W - 35} 30 }}\n', ours)
    ours = ours.replace(lvl, '\t\t\t\t\t\t\t# PMR: the recipes this owner\'s levels run\n'
                        f'\t\t\t\t\t\t\twidget = {{\n\t\t\t\t\t\t\t\tsize = {{ {OWN_PM_W} 30 }}\n'
                        + ''.join(owners_cell(bk, recipe_tex[bk]) for bk in buildings)
                        + '\t\t\t\t\t\t\t}\n\n' + lvl.replace('size = { 120 30 }', f'size = {{ {OWN_LEVELS_W} 30 }}'))
    ours = ours.replace('flowcontainer = {\n', f'flowcontainer = {{\n\t\t\t\t\t\t\tvisible = "[{pmr}]"\n', 1)
    text = (text[:at] + vanilla.replace('flowcontainer = {\n', f'flowcontainer = {{\n\t\t\t\t\t\t\tvisible = "[Not({pmr})]"\n', 1)
            + '\n\t\t\t\t\t\t# PMR: the owner row with a Production Method column\n' + ours + text[end:])
    return text


BROWSER_EXTRA = 35  # px the building browser grows by, for the government upgrade button


def patch_browser_actions(text, buildings):
    """building_browser_panel.gui: the government upgrade button left of nationalize in each building
    row, at the same 35 px, on PMR building types. The rows have no room to spare (their columns
    already fill @spreadsheet_width), so the spreadsheet, the row's action column and the
    Interactions header above it grow by BROWSER_EXTRA. Asserted per anchor."""
    def once(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise SystemExit(f'building_browser_panel.gui: expected one {old.strip()!r}, found {text.count(old)}; '
                             'update patch_browser_actions')
        text = text.replace(old, new)
    once('@spreadsheet_width = 1381\n', f'@spreadsheet_width = {1381 + BROWSER_EXTRA}  # PMR: +{BROWSER_EXTRA}\n')
    once('@spreadsheet_width_minus_10 = 1371\n', f'@spreadsheet_width_minus_10 = {1371 + BROWSER_EXTRA}  # PMR\n')
    once('\t\t\t\t\t\t\t\t\tsize = { 191 30 }\n', f'\t\t\t\t\t\t\t\t\tsize = {{ {191 + BROWSER_EXTRA} 30 }}  # PMR\n')
    once('\t\t\tsize = { 180 @spreadsheet_height }\n', f'\t\t\tsize = {{ {180 + BROWSER_EXTRA} @spreadsheet_height }}  # PMR\n')
    ind = '\t\t\t\t\t'
    buttons = ''.join(f'{ind}\twidget = {{\n{ind}\t\tvisible = "[{is_type(bk)}]"\n{ind}\t\tsize = {{ 35 35 }}\n'
                      + gov_button(short(bk), 35, ind + '\t\t', f'{ind}\t\t\tparentanchor = center\n')
                      + f'{ind}\t}}\n' for bk in buildings)
    once('\t\t\t\tflowcontainer = {\n\t\t\t\t\t### NATIONALIZE\n',
         '\t\t\t\tflowcontainer = {\n'
         f'{ind}ignoreinvisible = yes  # PMR\n'
         f'{ind}# PMR: government upgrade button\n{ind}widget = {{\n{ind}\tvisible = "[{any_type(buildings)}]"\n'
         f'{ind}\tsize = {{ 35 35 }}\n' + buttons + f'{ind}}}\n\n{ind}### NATIONALIZE\n')
    return text


MV_TAB = 'pmr_bb_mv'   # GetVariableSystem flag: the side Buildings panel shows its Investments tab
MV_AI = 'pmr_bb_mv_ai'   # GetVariableSystem flag: the Investments cards are sorted by AI weight (Pat 23:53Z)


def patch_browser_tabs(text, types):
    """building_browser_panel.gui (Pat, 2026-10-18 21:08Z, 21:21Z: "a sub panel called Investments in the buildings
    panel", "just like how private and government are separate panels with construction"): the side Buildings panel
    (compact_building_browser_panel) gets the construction panel's tab row, Buildings (vanilla's list) and Investments:
    the economic law, policy and investment priorities (private_investment.policy_block, Pat 18:40Z), then Production
    Methods, a card per building type (Pat 21:53Z), recounted by pmr_mv_refresh_sgui as the tab is clicked. The cards
    are the list's own items (types: the building types with a card), so the search, filters and sort buttons order
    and filter them as they do the vanilla rows; on Investments they sit under the Production Methods header (Pat
    22:28Z), on Buildings in the panel's fixed top as in vanilla. The tabs are vanilla's tab_buttons switched by a
    GetVariableSystem flag (MV_TAB), which the panel's closing clears, so it reopens on Buildings as the construction
    panel does. The full-screen Building Registry stays vanilla."""
    if not types:
        return text
    def once(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise SystemExit(f'building_browser_panel.gui: expected one {old.strip()!r}, found {text.count(old)}; '
                             'update patch_browser_tabs')
        text = text.replace(old, new)
    shown, hidden = f"GetVariableSystem.Exists('{MV_TAB}')", f"Not(GetVariableSystem.Exists('{MV_TAB}'))"
    refresh = "GetScriptedGui('pmr_mv_refresh_sgui').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).End)"
    pick_off = f"GetVariableSystem.Clear('{private_investment.PICK}')"   # the policy window starts closed
    t = '\t\t\t\t'

    def tab(n, key, click, sel):
        return (f'{t}blockoverride "{n}_button" {{\n{t}\ttext = "{key}"\n{t}}}\n'
                f'{t}blockoverride "{n}_button_tooltip" {{}}\n'   # no tooltip: it only repeated the tab name
                f'{t}blockoverride "{n}_button_click" {{\n' + ''.join(f'{t}\tonclick = "[{c}]"\n' for c in click) + f'{t}}}\n'
                f'{t}blockoverride "{n}_button_visibility" {{\n{t}\tvisible = "[{sel}]"\n{t}}}\n'
                f'{t}blockoverride "{n}_button_visibility_checked" {{\n{t}\tvisible = "[Not({sel})]"\n{t}}}\n'
                f'{t}blockoverride "{n}_button_selected" {{\n{t}\ttext = "{key}"\n{t}}}\n')
    # the tab row over the search and filters
    top = '\t\tblockoverride "fixed_top" {\n\n\t\t\tflowcontainer = {\n\t\t\t\tdirection = vertical\n'
    once(top, '\t\tblockoverride "fixed_top" {\n'
         '\t\t\t# PMR: Buildings / Investments tabs (patch_browser_tabs)\n\t\t\ttab_buttons = {\n'
         + tab('first', 'PMR_BB_TAB_BUILDINGS', [f"GetVariableSystem.Clear('{MV_TAB}')", pick_off], hidden)
         + tab('second', 'PMR_BB_TAB_INVEST', [f"GetVariableSystem.Set('{MV_TAB}', 'yes')", refresh, pick_off], shown)
         + '\t\t\t}\n\t\t\twidget = { size = { 1 10 } }\n\n'
         '\t\t\tflowcontainer = {\n\t\t\t\tdirection = vertical\n')
    # Pat 22:28Z: on Investments the search, filters and sort buttons sit under the Production Methods header; the
    # fixed top keeps them for Buildings only and the Investments head below gets its own copy
    gap = '\t\t\twidget = { size = { 1 10 } }\n\n'
    f0 = text.index(gap) + len(gap)
    f1 = block_end(text, f0)
    s0 = text.index('\t\t\t# SORT BUTTONS\n', f1)
    s1 = block_end(text, s0)
    if s1 > text.index('blockoverride "scrollarea_content"', f0):
        raise SystemExit('building_browser_panel.gui: sort buttons not in fixed_top; update patch_browser_tabs')
    filters, sorts = text[f0:f1], text[s0:s1]

    def on_buildings(block, when=hidden):
        i = block.index('{\n') + 2
        return block[:i] + f'\t\t\t\tvisible = "[{when}]"  # PMR\n' + block[i:]
    text = text[:s0] + on_buildings(sorts) + text[s1:]
    text = text[:f0] + on_buildings(filters) + text[f1:]
    # Pat 23:53Z: on Investments a fifth sort button, AI weight, which the game's list can't sort by: it shows PMR's own
    # list in that order instead (MV_AI, pmr_methods_slot), where the game's filters and search don't apply, so they
    # step aside until another sort button is clicked
    ai_on = f"GetVariableSystem.Exists('{MV_AI}')"
    ai_off = f"GetVariableSystem.Clear('{MV_AI}')"
    if sorts.count('size = { 135 30 }') != 4 or sorts.count('onclick = "[BuildingBrowserPanel.Sort(') != 4:
        raise SystemExit('building_browser_panel.gui: expected four sort buttons; update patch_browser_tabs')
    # Pat 2026-10-19 01:07Z: no Building Type sort on Policies
    d1 = sorts.find("BuildingBrowserPanel.Sort('database_order')")
    if d1 < 0:
        raise SystemExit('building_browser_panel.gui: no database_order sort button; update patch_browser_tabs')
    d0 = sorts.rindex('\n', 0, sorts.rindex('sort_button = {', 0, d1))
    inv_sorts = re.sub(r'(\n(\t+)onclick = "\[BuildingBrowserPanel\.Sort\([^\n]*\n)',
                       lambda m: f'{m.group(1)}{m.group(2)}onclick = "[{ai_off}]"  # PMR\n',
                       sorts[:d0] + sorts[block_end(sorts, d0):])
    b4 = '\t\t\t\t'
    inv_sorts = (inv_sorts[:inv_sorts.rindex('}')].rstrip('\t')
                 + f'\n{b4}# PMR: sorted by AI weight\n{b4}sort_button = {{\n{b4}\tsize = {{ 135 30 }}\n'
                 f'{b4}\ttext = "PMR_MV_AI_LABEL"\n{b4}\talign = nobaseline\n'
                 f'{b4}\tonclick = "[GetVariableSystem.Set(\'{MV_AI}\', \'yes\')]"\n{b4}\tonclick = "[{refresh}]"\n'
                 f'{b4}\tblockoverride "selected_visibility" {{\n{b4}\t\tvisible = "[{ai_on}]"\n{b4}\t}}\n{b4}}}\n'
                 + '\t\t\t' + inv_sorts[inv_sorts.rindex('}'):])
    inv_filters = on_buildings(filters, f'Not({ai_on})')
    # the list's items: vanilla's row on Buildings, PMR's card on Investments (pmr_methods_cards, gui/pmr_methods_view.gui)
    has_rows = 'Not(IsDataModelEmpty(BuildingBrowserBuildingTypeItem.GetBuildings))'
    # q30's ObjectsEqual(BuildingBrowserBuildingTypeItem.GetBuildingType, ...) matched nothing (Pat 22:28Z: blank);
    # vanilla's own form reads the item's BuildingType context (production_methods.gui)
    carded = any_of([f"ObjectsEqual(BuildingType.Self, GetBuildingType('{bk}').Self)" for bk in types])
    items = ('\t\t\t\tflowcontainer = {\n\t\t\t\t\tdirection = vertical\n\t\t\t\t\tspacing = 5\n\n'
             '\t\t\t\t\tdatamodel = "[BuildingBrowserPanel.GetBuildingBrowserBuildingTypeItems]"\n\n'
             '\t\t\t\t\titem = {\n\t\t\t\t\t\tcontainer = {\n\t\t\t\t\t\t\tbuildings_production_method_item = {\n')
    once(items, '\t\t\t\tflowcontainer = {\n\t\t\t\t\tdirection = vertical\n\t\t\t\t\tspacing = 5\n'
         '\t\t\t\t\tignoreinvisible = yes  # PMR\n\n'
         '\t\t\t\t\tdatamodel = "[BuildingBrowserPanel.GetBuildingBrowserBuildingTypeItems]"\n\n'
         '\t\t\t\t\titem = {\n\t\t\t\t\t\tcontainer = {\n'
         '\t\t\t\t\t\t\tdatacontext = "[BuildingBrowserBuildingTypeItem.GetBuildingType]"  # PMR\n'
         f'\t\t\t\t\t\t\tvisible = "[Or({hidden}, And(And({has_rows}, {carded}), Not({ai_on})))]"  # PMR\n'
         '\t\t\t\t\t\t\t# PMR: a card per building type on Investments\n'
         # perf review 3 (G2): the cards are built only while Policies is open
         f'\t\t\t\t\t\t\tflowcontainer = {{\n\t\t\t\t\t\t\t\tvisible = "[{shown}]"\n\t\t\t\t\t\t\t\tposition = {{ 7 0 }}\n'
         f"\t\t\t\t\t\t\t\tdatamodel = \"[DataModelRepeatedItem(Select_int32({shown}, '(int32)1', '(int32)0'))]\"\n"
         '\t\t\t\t\t\t\t\titem = {\n\t\t\t\t\t\t\t\t\tpmr_methods_cards = {\n\t\t\t\t\t\t\t\t\t\tposition = { 0 0 }\n'
         '\t\t\t\t\t\t\t\t\t}\n\t\t\t\t\t\t\t\t}\n\t\t\t\t\t\t\t}\n'
         '\t\t\t\t\t\t\tbuildings_production_method_item = {\n'
         f'\t\t\t\t\t\t\t\tblockoverride "visible" {{\n\t\t\t\t\t\t\t\t\tvisible = "[And({has_rows}, {hidden})]"  # PMR\n'
         '\t\t\t\t\t\t\t\t}\n')
    # perf review 3 (G2): vanilla's row is built only while Buildings is open
    row = '\t\t\t\t\t\t\tbuildings_production_method_item = {\n\t\t\t\t\t\t\t\tblockoverride "visible" {\n'
    if text.count(row) != 1:
        raise SystemExit('building_browser_panel.gui: expected one patched type row; update patch_browser_tabs')
    r0 = text.index(row)
    r1 = block_end(text, r0)
    i7 = '\t' * 7
    text = (text[:r0] + f'{i7}flowcontainer = {{  # PMR\n{i7}\tvisible = "[{hidden}]"\n'
            f"{i7}\tdatamodel = \"[DataModelRepeatedItem(Select_int32({hidden}, '(int32)1', '(int32)0'))]\"\n"
            f'{i7}\titem = {{\n'
            + '\n'.join('\t\t' + l if l.strip() else l for l in text[r0:r1].split('\n'))
            + f'\n{i7}\t}}\n{i7}}}' + text[r1:])
    # the policy window pops out to the right of the panel, under the map mode button (Pat 2026-10-19 00:06Z); the
    # panel's root allows children outside it (default_block_window allow_outside)
    modes = ('\t\tblockoverride "map_modes_button" {\n\t\t\tmap_modes_single_button_minimized = {\n'
             '\t\t\t\tdatacontext = "[BuildingBrowserPanel.GetMapModeList]"\n'
             '\t\t\t\tusing = map_modes_button_position\n\t\t\t}\n')
    once(modes, modes + f'\t\t\tpmr_policy_popout = {{  # PMR\n\t\t\t\tvisible = "[{shown}]"\n'
         '\t\t\t\tposition = { 622 150 }\n\t\t\t}\n')
    # vanilla's lists of buildings that could be built stay on Buildings
    for f in ('is_development', 'is_rural', 'is_urban'):
        once(f'\t\t\t\tbuilding_panel_potential_buildings = {{\n\t\t\t\t\tvisible = "[BuildingBrowserPanel.IsFilterYes(\'{f}\')]"\n',
             f'\t\t\t\tbuilding_panel_potential_buildings = {{\n'
             f'\t\t\t\t\tvisible = "[And(BuildingBrowserPanel.IsFilterYes(\'{f}\'), {hidden})]"  # PMR\n')
    # Investments' own head (law, policy, priorities, the Production Methods header) above the list
    body = '\t\tblockoverride "scrollarea_content"\n\t\t{\n'
    lst = '\t\t\tflowcontainer = {\n\t\t\t\tdirection = vertical\n'
    once(body + lst, body + '\t\t\t# PMR: the Investments tab\'s head, then the list both tabs share\n'
         '\t\t\tflowcontainer = {\n\t\t\t\tdirection = vertical\n\t\t\t\tignoreinvisible = yes\n\n'
         f'\t\t\tflowcontainer = {{\n\t\t\t\tvisible = "[{shown}]"\n\t\t\t\tusing = default_list_position\n'
         '\t\t\t\tdirection = vertical\n\t\t\t\tignoreinvisible = yes\n\t\t\t\tspacing = 8\n\t\t\t\tmargin_bottom = 8\n'
         '\t\t\t\tpmr_policy_block = {}\n'
         '\t\t\t\tdefault_header = {\n\t\t\t\t\tblockoverride "text" {\n\t\t\t\t\t\ttext = "PMR_MV_HEADER"\n'
         '\t\t\t\t\t}\n\t\t\t\t}\n' + inv_filters + '\n' + inv_sorts + '\n\t\t\t}\n'
         # the cards in AI weight order: one slot per card (pmr_mv_n), each making the card of its place
         f'\t\t\tflowcontainer = {{\n\t\t\t\tvisible = "[And({shown}, {ai_on})]"\n\t\t\t\tdirection = vertical\n'
         '\t\t\t\tspacing = 5\n'
         f'\t\t\t\tdatamodel = "[DataModelRepeatedItem(FixedPointToInt({mv_read("pmr_mv_n")}))]"\n'
         '\t\t\t\titem = {\n\t\t\t\t\tpmr_methods_slot = {}\n\t\t\t\t}\n\t\t\t}\n'
         + '@@PMR_LIST@@' + lst)
    at = text.index('@@PMR_LIST@@')
    end = block_end(text, at + len('@@PMR_LIST@@'))
    text = text[:at] + text[at + len('@@PMR_LIST@@'):end] + '\n\t\t\t}  # PMR' + text[end:]
    # closing the panel puts it back on Buildings, with the policy window shut
    hide = ('\t\t\t\tname = _hide\n\t\t\t\tstart_sound = {\n\t\t\t\t\tsoundeffect = "event:/SFX/UI/SideBar/buildings_stop"\n'
            '\t\t\t\t}\n\n\t\t\t\ton_start = "[BuildingBrowserPanel.Sort(\'database_order\')]"\n')
    once(hide, hide + f'\t\t\t\ton_start = "[GetVariableSystem.Clear(\'{MV_TAB}\')]"  # PMR\n'
         f'\t\t\t\ton_start = "[{pick_off}]"  # PMR\n'
         f'\t\t\t\ton_start = "[{ai_off}]"  # PMR\n')
    return text


def block_end(text, start):
    """Index just past the '}' that closes the first '{' at or after start."""
    i = text.index('{', start)
    depth = 0
    while True:
        c = text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        elif c == '#':
            i = text.index('\n', i)
            continue
        elif c == '"':
            i = text.index('"', i + 1)
        i += 1


TYPE_BAR_W = 160   # Buildings tab type row: x 110 (the grid's place) to the action buttons, six of them since the upgrade


def c_name(name):
    """The country total behind a per-state variable name (pmr_c_sum_<b>)."""
    return {'pmr_ui_retooling': 'pmr_c_retooling'}.get(name, name.replace('pmr_', 'pmr_c_', 1))


def type_bar(bk, textures):
    """The Buildings tab's building type row (vanilla buildings_production_method_item): in place of
    the method grid, the recipe bar over all of the player's buildings of the type (country totals),
    centred on the action buttons (they sit 5 from the row's bottom, 40 tall; this widget's container
    is anchored to the bottom, so 12 px below the 26 px bar line them up)."""
    b = short(bk)

    def make(_bk, gind, visible):
        return (f'\n{gind}# PMR: recipe bar across the country for {bk}\n{gind}widget = {{\n'
                f'{gind}\tvisible = "[{visible}]"\n{gind}\tsize = {{ {TYPE_BAR_W} 38 }}\n'
                + stacked_bar(b, textures, (TYPE_BAR_W, 26), 18, gind + '\t',
                              var=lambda name: country_var(b, c_name(name)),
                              tips=[(None, f'PMR_CBAR_TOOLTIP_{b}')])
                # Pat, 2026-10-19 01:07Z ("can we have this bar be green with progress arrows?"): the switching bar of
                # the country's biggest state of the type under it, while a new pick fills it
                + switch_bar(country_var(b, 'pmr_c_sw'), country_var(b, 'pmr_c_swd'), (TYPE_BAR_W, 10), gind + '\t',
                             f'PMR_CSW_TT_{b}', place=f'{gind}\t\tposition = {{ 0 28 }}\n')
                + f'{gind}}}\n')
    return make


def patch_type_row_buttons(text, buildings):
    """production_methods.gui, the Buildings tab's building type row: the government upgrade button
    left of nationalize, at the row's 40 px, queueing every government retool level the player's
    buildings of the type still need, in every state (pmr_gov_retool_c_<b>_sgui, country scope)."""
    anchor = '\t\t\t\tspacing = 5\n\t\t\t\t\n\t\t\t\t### nationalize\n\t\t\t\tbuilding_type_nationalize_button = {\n'
    if text.count(anchor) != 1:
        raise SystemExit(f'production_methods.gui: expected one type-row nationalize button, found {text.count(anchor)}; '
                         'update patch_type_row_buttons')
    ind = '\t\t\t\t'
    scope = 'GuiScope.SetRoot(GetPlayer.MakeScope).End'

    def is_bt(bk):
        return f"ObjectsEqual(BuildingType.Self, GetBuildingType('{bk}').Self)"
    any_bt = is_bt(buildings[-1])
    for bk in reversed(buildings[:-1]):
        any_bt = f'Or({is_bt(bk)}, {any_bt})'
    buttons = ''.join(
        f'{ind}\tbutton_icon_round = {{\n{ind}\t\tvisible = "[{is_bt(bk)}]"\n{ind}\t\tsize = {{ 40 40 }}\n'
        f"{ind}\t\tenabled = \"[GetScriptedGui('pmr_gov_retool_c_{short(bk)}_sgui').IsValid({scope})]\"\n"
        f"{ind}\t\tonclick = \"[GetScriptedGui('pmr_gov_retool_c_{short(bk)}_sgui').Execute({scope})]\"\n"
        f'{ind}\t\ttooltip = "PMR_GOV_RETOOL_C_TOOLTIP_{short(bk)}"\n{ind}\t\tusing = tooltip_se\n'
        f'{ind}\t\tusing = confirm_button_sound\n'
        f'{ind}\t\tblockoverride "icon" {{\n{ind}\t\t\ttexture = "{GOV_RETOOL_ICON}"\n{ind}\t\t}}\n'
        f'{ind}\t\tblockoverride "icon_size" {{\n{ind}\t\t\tsize = {{ 80% 80% }}\n{ind}\t\t}}\n{ind}\t}}\n'
        for bk in buildings)
    return text.replace(anchor,
                        f'{ind}spacing = 5\n{ind}ignoreinvisible = yes  # PMR\n{ind}\n'
                        f'{ind}# PMR: government upgrade button, every state at once\n{ind}widget = {{\n'
                        f'{ind}\tvisible = "[{any_bt}]"\n{ind}\tsize = {{ 40 40 }}\n{buttons}{ind}}}\n\n'
                        f'{ind}### nationalize\n{ind}building_type_nationalize_button = {{\n')


def patch_type_grids(text, buildings, name, expected, replace=None, also=(), skip=()):
    """A vanilla GUI file's per-building-type production method grids (the building browser's,
    which switch every building of a type at once): for PMR building types the whole grid is
    hidden and one static fixed-labour icon takes its place. Asserted per file.

    1.14.5 ignored a visible on the grid's items here (the browser still showed every selector), so
    the grid itself is hidden. The type test uses the BuildingType datacontext each of these grids
    sits in, in the form vanilla's own company panels use."""
    out, pos, n = [], 0, 0
    pattern = re.compile(r'datamodel = "\[(\w+)\.GetBuildingType\.AccessProductionMethodGroups\]"')

    def is_bt(bk):
        return f"ObjectsEqual(BuildingType.Self, GetBuildingType('{bk}').Self)"

    hidden = list(buildings) + list(also)   # also: AUTO_BEST types, no selectors and nothing in their place
    any_expr = is_bt(hidden[-1])
    for bk in reversed(hidden[:-1]):
        any_expr = f'Or({is_bt(bk)}, {any_expr})'
    for m in pattern.finditer(text):
        grid = text.rfind('fixedgridbox = {', 0, m.start())
        inner = text.index('\n', grid) + 1
        end = block_end(text, grid)
        if n in skip:   # a grid no screen shows: left as vanilla's
            out.append(text[pos:end])
            pos = end
            n += 1
            continue
        gind = text[text.rfind('\n', 0, grid) + 1:grid]
        # place the icon where the grid's first cell is: copy the grid's own position and anchor
        head = text[grid:m.start()] + text[m.end():text.index('item = {', m.end())]
        place = ''.join(f'{gind}\t{l.strip()}\n' for l in head.splitlines()
                        if l.strip().startswith(('position =', 'parentanchor =')))
        if replace and n in replace:
            icons = ''.join(replace[n](bk, gind, is_bt(bk)) for bk in buildings)
        else:
            icons = ''.join(
                f'\n{gind}# PMR: fixed labour icon for {bk}\n{gind}widget = {{\n'
                f'{gind}\tvisible = "[{is_bt(bk)}]"\n'
                f'{place}{gind}\tsize = {{ 50 50 }}\n'
                f'{gind}\ticon = {{\n{gind}\t\tsize = {{ 40 40 }}\n{gind}\t\tparentanchor = center\n'
                f'{gind}\t\ttexture = "gfx/interface/icons/production_method_icons/pmr_labour_{short(bk)}.dds"\n'
                f'{gind}\t}}\n{gind}}}\n'
                for bk in buildings)
        out += [text[pos:inner], f'{gind}\t# PMR: no selectors for PMR building types\n{gind}\tvisible = "[Not({any_expr})]"\n',
                text[inner:end], icons]
        pos = end
        n += 1
    if n != expected:
        raise SystemExit(f'{name}: expected {expected} per-type production method grids, found {n}; '
                         'update patch_type_grids')
    return ''.join(out) + text[pos:]


def patch_building_grids(text, buildings, name, expected, also=()):
    """A vanilla GUI file's per-building production method lists (Building context): on PMR building
    types only single-method groups (the fixed labour slot) show, and so on the AUTO_BEST types in also,
    which have none. Asserted per file."""
    buildings = list(buildings) + list(also)
    anchor = 'datamodel = "[Building.AccessProductionMethodGroups]"'
    n = text.count(anchor)
    if n != expected:
        raise SystemExit(f'{name}: expected {expected} building production method lists, found {n}; '
                         'update patch_building_grids')
    pos = 0
    for _ in range(n):
        at = text.index(anchor, pos)
        w = text.index('widget = {\n', at) + len('widget = {\n')
        ind = text[text.rfind('\n', 0, w - len('widget = {\n')) + 1:w - len('widget = {\n')] + '\t'
        line = (f'{ind}# PMR: fixed labour only on PMR building types\n{ind}visible = "[Or(Not({any_type(buildings)}), '
                "EqualTo_int32(GetDataModelSize(ProductionMethodGroup.AccessBuildingProductionMethods(Building.Self)), "
                "'(int32)1'))]\"\n")
        text = text[:w] + line + text[w:]
        pos = w + len(line)
        # The hidden share and lock groups must take no room in the list (vanilla's default keeps it).
        dl = text.index('\n', at) + 1
        dind = text[text.rfind('\n', 0, at) + 1:at]
        text = text[:dl] + f'{dind}ignoreinvisible = yes  # PMR\n' + text[dl:]
        pos += len(f'{dind}ignoreinvisible = yes  # PMR\n')
    return text


def panel_loc(recipe_keys):
    loc = [
        ' PMR_RECIPE_BAR_TITLE:0 "#bold [Building.GetCustom(\'pmr_new_recipe\')]#!"',
        ' PMR_OWNERS_PM_HEADER:0 "Production Method"',
        ' PMR_LABOUR_ICON_TOOLTIP:0 "#bold Blended recipes#!\\nThe mix of recipes its levels run"',
        ' PMR_BAR_FULL_TOOLTIP:0 "Every level runs #bold [Building.GetCustom(\'pmr_new_recipe\')]#!."',
        ' PMR_RECIPE_BAR_TOOLTIP:0 "Switches to newer recipes by retooling"',
    ]
    for bk, keys in recipe_keys.items():
        b = short(bk)

        def var(name, f):
            return f"[Building.GetState.MakeScope.Var('{name}_{b}').GetValue|{f}]"
        # Pat, 2026-10-13: no colour names, and short. With the split, by plain recipe (SPLIT_BARS).
        sh, lvg, lvp = ('pmr_rs', 'pmr_rlvg', 'pmr_rlvp') if b in SPLIT_BARS else ('pmr_sh', 'pmr_lvg', 'pmr_lvp')
        tiers = ''.join(f'\\n${key}$: #bold {var(f"{sh}_{i}", "%0")}#!' for i, key in enumerate(keys, 1))
        gov = f'Government: #bold {var("pmr_pending_gov", "0")}#! queued, #bold {var("pmr_room_gov", "0")}#! room'
        loc += [
            f' PMR_RECIPE_BAR_TITLE_RETOOLING_{b}:0 "#bold {var("pmr_p", "%0")}#! on #bold [Building.GetCustom(\'pmr_new_recipe\')]#!"',
            f' PMR_BAR_TOOLTIP_{b}:0 "#bold Levels by recipe#!{tiers}'
            f'\\n\\nTo retool: #bold {var("pmr_need", "0")}#!'
            f'\\nPrivate: #bold {var("pmr_pending_priv", "0")}#! queued, #bold {var("pmr_room_priv", "0")}#! room'
            f'\\n{gov}"',
            f' PMR_GOV_RETOOL_TOOLTIP_{b}:0 "#bold Retool the government\'s levels#!'
            f'\\nQueues #bold {var("pmr_room_gov", "0")}#! levels"',
            f' PMR_GOV_RETOOL_ABROAD_TOOLTIP_{b}:0 "#bold Retool your government\'s levels#!'
            f'\\nQueues #bold {var("pmr_room_gov", "0")}#! levels, up to {GOV_ABROAD_CLICKS} a click"',
            f' PMR_OWNERS_GOV_TOOLTIP_{b}:0 "#bold Government-owned levels by recipe#!'
            + ''.join(f'\\n${key}$: #bold {var(f"{lvg}_{i}", "0")}#!' for i, key in enumerate(keys, 1)) + '"',
            f' PMR_OWNERS_PRIV_TOOLTIP_{b}:0 "#bold Privately owned levels by recipe#!'
            + ''.join(f'\\n${key}$: #bold {var(f"{lvp}_{i}", "0")}#!' for i, key in enumerate(keys, 1)) + '"',
        ]

        def cvar(name, f):
            return f"[GetPlayer.MakeScope.Var('{name}_{b}').GetValue|{f}]"
        ctiers = ''.join(f'\\n${key}$: #bold {cvar(c_name(f"{sh}_{i}"), "%0")}#!' for i, key in enumerate(keys, 1))
        loc += [
            f' PMR_CBAR_TOOLTIP_{b}:0 "#bold Levels by recipe#!{ctiers}'
            f'\\n\\nLevels: #bold {cvar("pmr_c_level", "0")}#!, to retool: #bold {cvar("pmr_c_need", "0")}#!"',
            f' PMR_GOV_RETOOL_C_TOOLTIP_{b}:0 "#bold Retool the government\'s levels everywhere#!'
            f'\\nQueues #bold {cvar("pmr_c_room_gov", "0")}#! levels"',
        ]
    return loc


def option_loc(opt_ui):
    """Tooltips of the second group bars. Pat, 2026-10-13: short."""
    loc = [' PMR_EMPTY:0 ""', ' PMR_OPT_LOCKED:0 " (locked)"', ' PMR_OPT_BARRED:0 " (barred)"']
    for bk, groups in opt_ui.items():
        b = short(bk)

        def var(name, f='0'):
            return f"[Building.GetState.MakeScope.Var('{name}_{b}').GetValue|{f}]"
        for gi, mode, none, tex, os_ in groups:
            lines = [f'${none}$: #bold {var(f"pmr_xn_{gi}")}%#!']
            for o in os_:
                note = f"[Building.GetState.GetCustom('pmr_xlk_{b}_{o.j}')]"
                worth = f', @money!{var(f"pmr_xw_{o.j}")}' if mode == 'market' else ''
                lines.append(f'${o.key}$: #bold {var(f"pmr_x_{o.j}")}%#!{worth}{note}')
            foot = ''
            if mode != 'market':
                lo, hi = TREAT_BANDS
                foot = (f'\\n\\nAcceptance under {lo}: #bold {var(f"pmr_xbv_{gi}")}%#!, {lo} to {hi - 1}: '
                        f'#bold {var(f"pmr_xbh_{gi}")}%#!')
            loc.append(f' PMR_OPT_TOOLTIP_{b}_{gi}:0 "#bold ${os_[0].group}$#!\\n' + '\\n'.join(lines) + f'{foot}"')
    return loc


ON_ACTIONS = '''# Appended to vanilla on_actions the documented way (_on_actions.md, MODDING INFO):
# the vanilla on_action calls ours, nothing vanilla is overwritten.

on_game_started = { on_actions = { pmr_on_game_started } }
on_production_method_changed = { on_actions = { pmr_on_production_method_changed } }
on_building_built = { on_actions = { pmr_on_building_built } }
on_building_expanded = { on_actions = { pmr_on_building_expanded } }
on_monthly_pulse_state = { on_actions = { pmr_on_monthly_pulse_state } }
on_monthly_pulse_country = { on_actions = { pmr_on_monthly_pulse_country } }
on_acquired_technology = { on_actions = { pmr_on_acquired_technology } }

# No root. Adopt every building's starting recipe, all levels on it.
pmr_on_game_started = {
	effect = {
		debug_log = "PMR;rec=LOADED;date=[TimeKeeper.GetCurrentDate.GetString];hook=on_game_started"
		# No country is a player's yet here (no player state logs INIT), so every country gets its
		# Buildings tab totals now; after this only players' are kept up to date.
		# The market has no prices yet: the profit calculation uses base prices meanwhile (profit_effect).
		set_global_variable = pmr_setup
		every_country = {
			every_scope_state = {
				pmr_state_tick = yes
				pmr_auto_best = yes   # AUTO_BEST: government administration, universities, trade centres, carriages
			}
			pmr_c_sum_every = yes
			# A day later the players exist: their totals then add buildings abroad (pmr.1).
			trigger_event = { id = pmr.1 days = 1 }
		}
		remove_global_variable = pmr_setup
	}
}

# Root = building whose production method changed. The switch is seen the moment it happens.
# A change a PMR tick makes itself (pmr_in_tick on the state) would only meet that tick's own guard,
# so it skips the dispatch over every PMR building type.
pmr_on_production_method_changed = {
	effect = {
		if = {
			limit = { state = { NOT = { has_variable = pmr_in_tick } } }
			pmr_tick_building = yes
		}
		# AUTO_BEST: a change away from the best method is undone at once (not the ones it makes itself, nor
		# a PMR tick's share switches on a railway)
		if = {
			limit = { state = { NOT = { has_variable = pmr_auto_busy } NOT = { has_variable = pmr_in_tick } } }
			pmr_auto_building = yes
		}
	}
}

# Root = building whose first level just completed. A new retool building moves p at once, and a
# new PMR building is seen without waiting for the month.
pmr_on_building_built = {
	effect = {
		# First, while the building is sure to exist: the Private tab's record of what the player's
		# investors built (pmr_pi_effects.txt; retool buildings are not counted).
		pmr_pi_on_done = yes
		pmr_built_building = yes
		pmr_auto_building = yes   # AUTO_BEST: a new building starts on the best methods
		# Last: the parent's tick can remove this retool building once its level is counted.
		pmr_tick_parent_of_retool = yes
	}
}

# Root = building that just completed a further level. on_building_built fires only for a
# building's first level, so without this every later retool level waited for the month to turn.
pmr_on_building_expanded = {
	effect = {
		# First, while the building is sure to exist: the Private tab's record of what the player's
		# investors built (pmr_pi_effects.txt; retool buildings are not counted).
		pmr_pi_on_done = yes
		pmr_built_building = yes
		# Last: the parent's tick can remove this retool building once its level is counted.
		pmr_tick_parent_of_retool = yes
	}
}

# Root = country that just acquired a technology. A newly unlocked recipe switches its buildings
# at once instead of at the next month turn.
pmr_on_acquired_technology = {
	effect = {
		if = { limit = { exists = capital } capital = { TECH_CRUMB } }
		# The player, for buildings abroad the player owns levels in (pmr_abroad_<b>).
		if = {
			limit = { is_player = yes }
			set_global_variable = { name = pmr_player value = ROOT }
		}
		if = {
			limit = { NOT = { has_global_variable = pmr_ticks_paused } }
			every_scope_state = {
				pmr_state_research = yes
				pmr_auto_best = yes
			}
			# the player's levels abroad run on the player's technology
			if = {
				limit = { is_player = yes }
				every_state = {
					limit = { has_variable = pmr_abroad_any NOT = { owner = ROOT } }
					pmr_state_research_abroad = yes
				}
			}
			pmr_c_sum_all = yes
		}
	}
}

# Root = state. Backstop: recompute the shares and re-apply the blend once a month even if no event fired.
# pmr_month marks the monthly tick: the trade-off shares step and the treatment shares are recounted.
pmr_on_monthly_pulse_state = {
	trigger = { NOT = { has_global_variable = pmr_ticks_paused } }
	effect = {
		set_variable = pmr_month
		pmr_state_tick = yes
		remove_variable = pmr_month
		pmr_auto_best = yes
		pmr_principle_bonus = yes
		pmr_probe_state = yes
	}
}

# Root = country. The player's totals for the Buildings tab rows, once the month's state ticks are in
# (whichever pulse runs first, a change made only by the monthly tick shows within a month).
pmr_on_monthly_pulse_country = {
	trigger = { NOT = { has_global_variable = pmr_ticks_paused } }
	effect = {
		pmr_c_sum_all = yes
	}
}
'''

EVENTS = '''namespace = pmr

# Country, the day after game start (from pmr_on_game_started): no country is a player's at game start,
# so the players' Buildings tab totals are summed again here, now including buildings abroad.
pmr.1 = {
	type = country_event
	hidden = yes
	immediate = {
		if = {
			limit = { is_player = yes }
			set_global_variable = { name = pmr_player value = ROOT }
		}
		pmr_c_sum_all = yes
	}
}
'''

DECISIONS = '''# Test decision. The AI never takes it (ai_chance 0). It writes PMR;rec=TEST lines to debug.log.
# Pat, 2026-10-13 20:00Z: the other test decisions (grant Bessemer and a steel mill, grant Open Hearth,
# recompute retooling now, record trade-offs worldwide) are gone; this one stays for the performance
# review's timing run.

# Performance test (2026-10-13): stops the monthly and research ticks worldwide, or starts them again,
# so a year can be timed in the same save with and without them. Methods, buildings and the per-building
# hooks (construction, method changes) stay, so what remains is the cost of the data itself. Shares
# freeze while paused and move again from the next month after resuming.
pmr_test_pause_ticks_decision = {
	is_shown = { always = yes }
	possible = { always = yes }
	when_taken = {
		if = {
			limit = { has_global_variable = pmr_ticks_paused }
			remove_global_variable = pmr_ticks_paused
			capital = { debug_log = "PMR;rec=TEST;arm=TICKS_RESUMED;date=[TimeKeeper.GetCurrentDate.GetString]" }
		}
		else = {
			set_global_variable = pmr_ticks_paused
			capital = { debug_log = "PMR;rec=TEST;arm=TICKS_PAUSED;date=[TimeKeeper.GetCurrentDate.GetString]" }
		}
	}
	ai_chance = { value = 0 }
}
'''

DECISION_LOC = [
    ' pmr_test_pause_ticks_decision:0 "PMR test: pause or resume the monthly ticks"',
    ' pmr_test_pause_ticks_decision_desc:0 "Pauses or resumes PMR\'s ticks."',
]


if __name__ == '__main__':
    main()
