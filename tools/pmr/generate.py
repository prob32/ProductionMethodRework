"""Generate the Production Method Rework (PMR) mod from the installed game's own script.

PMR is generated, not hand-written, because it touches every recipe production method in the
game and must follow the beta as it moves. Run it against the game folder of the build you are
testing; it rewrites the mod folder in place.

    python tools/pmr/generate.py --game "G:/SteamLibrary/steamapps/common/Victoria 3/game"

With ``--release`` it writes the build players get, to pmr/release/ProductionMethodRework: no "PMR test:"
decision, no GENERATION_REPORT.json, and no PMR log lines but TRIP and AUTO_TRIP (the loop breakers) and LOADED.
The default build keeps the test logs; the "PMR test:" decisions and test probes need ``--test-decisions``. Both write every game language: localise.py translates the English text
from tools/pmr/translations/, and a line no table has yet stays English.

What it does, building by building (see pmr/README.md for the design):

1. Frames (method-count rework, Pat 2026-11-10; frames.py): the vanilla recipe group holds every
   recipe and pair recipe as a pure frame with its full body (its own goods, workforce and automation),
   plus one union frame per recipe, ``pm_pmr_union_<b>_<p>``, carrying each good at the most any mix
   uses. Each market trade-off group gets an option union, ``pm_pmr_union_<b>_x<g>``. Unions unlock
   only while they run, so no one else can pick them. No modifier moves a building's jobs (q100), so
   each union comes in job versions, ``<union>_j<n>``, and the tick runs the one nearest the mix:
   laborers a level in steps of 250 (500 where a group would pass 250 methods), the other pop types
   those of the target with the larger share; a trade-off's union each pop type in a few steps.
2. A building that runs one recipe on every level runs that recipe's pure frame and nothing else. A
   mixed building runs the union of its target and takes the difference off with "less" static
   modifiers, ``pmr_less_in/out_<good>`` and ``pmr_less_job_<pop>``, each -100% of its key, applied at
   1 - mix/union. So the building's goods are the level-weighted mix of its recipes, in its own
   production figures, at one active method per group where the old share ladders ran up to a dozen.
   The tick resets the frame only when the mix or a trade-off changes, and undoes any swap by the AI.
3. Treatment shares keep their ladders, ``pm_pmr_x_<b>_<g>_<n>`` in ``pmg_pmr_x_<b>_<g>``, and count
   in the frame's mix; their 0% method is always open and the others unlock only while they run.
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
only the frame bodies and groups changed; every other byte is the installed game's.
"""

import argparse
import collections
import glob
import json
import math
import re
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import icons  # noqa: E402
import pdx  # noqa: E402
import private_investment  # noqa: E402
import company_culture  # noqa: E402
import cc_tree  # noqa: E402
import subsidiaries  # noqa: E402
import company_panel  # noqa: E402
import methods_row  # noqa: E402
import localise  # noqa: E402
import frames  # noqa: E402
import frame_probe  # noqa: E402
import group_probe  # noqa: E402

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
# A share of n% runs one method the engine adds, pm_pmr_share_<b>_<i>_<n> (n = 0..SHARE_STEPS; options pm_pmr_x_),
# alone in its group. It unlocks only while it runs itself: 1.14.5 checks unlocking_production_methods against the
# building's active methods (the player's command, the AI switcher, can_activate and the repair pass alike), and
# activate_production_method checks nothing, so only script moves a share and no lock group is needed. Measured
# fastest (q54, 2026-10-20 observer run): ~20% under the tens + units digits of q52/q53 and ~5% under q51's
# 101 + 102 key groups, though it has more methods than the digits (each one a weekly national-standard cost,
# vanilla-standard-pms): a building carries half the groups and active methods, and a share's modifiers once.
# A building that runs no method yet has none of them available, so the game leaves every share group empty when it
# builds one, history's included, and start-of-game hiring found no jobs (q52-q61: every building began the game
# empty; q61's START_STAFF line read no share at all on Great Britain's and Austria's ranches). So each building also
# has pmg_pmr_start_<b>: pm_pmr_start_<b> (its default, always available) also unlocks every share group's default, so
# a new building starts on recipe 1 at 100% and the rest at 0%, and the first tick moves it to pm_pmr_run_<b> (listed
# first), which unlocks nothing (pmr_blend_<b>).
# --digit-shares keeps q53's digits: tens (pm_pmr_share_<b>_<i>_<10t>, t = 0..10) and units (pm_pmr_shu_<b>_<i>_<u>,
# u = 0..9), each self-locking, options pm_pmr_x_ / pm_pmr_xu_.
TENS = list(range(0, SHARE_STEPS + 1, 10))
UNITS = list(range(10))
SHARE_DIGITS = False   # set by main()


def share_digits(stem, default_n, step=1):
    """the methods one share runs: [(method stem, values, default value, group suffix)]; step: the share's grain in
    points (a trade-off's OPT_STEP, opt_values)"""
    if not SHARE_DIGITS:
        return [(stem, list(range(0, SHARE_STEPS + 1, step)), default_n, '')]
    return [(stem, TENS, default_n, ' (tens)'), (stem.replace('pm_pmr_share_', 'pm_pmr_shu_').replace('pm_pmr_x_', 'pm_pmr_xu_'),
                                                 UNITS, 0, ' (units)')]
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
# Interface review 2026-11-11 (gui-review/SPEC.md A7): re-stepped so neighbours stay apart under colour blindness; the
# moss tier went, which also keeps the tiers clear of green.
TIER_COLORS = [('Bronze', (0.59, 0.40, 0.25)), ('Ochre', (0.79, 0.65, 0.33)), ('Steel blue', (0.29, 0.46, 0.66)),
               ('Dusty rose', (0.73, 0.56, 0.66)), ('Slate teal', (0.34, 0.47, 0.51)),
               ('Parchment', (0.84, 0.80, 0.69))]   # 1.15: artillery foundries have six (the bronze cannons and smoothbores)
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
# Pat, 2026-10-19 21:18Z ("Retool, next batch"): the plantations' processing groups leave vanilla's hidden selectors for
# the automation axis, changed through retooling like the labour savers. Vanilla draws them with the base icon. They
# keep vanilla's numbers (no AUTOMATION_WAGE buff): most add jobs and output rather than save wages.
PROCESSING_GROUPS = {'pmg_drying_coffee_plantation', 'pmg_manufacture_tobacco', 'pmg_refinement_building_sugar_plantation'}
AUTOMATION_GROUPS |= PROCESSING_GROUPS


def is_automation(g):
    """a labour-saver group; AUTO_BEST's (the trade centre's trade quantity) run the newest method instead"""
    return ('automation' in g or g in AUTOMATION_GROUPS) and not any(g in gs for gs in AUTO_BEST.values())


SPLIT_BARS = {}   # short name -> plain recipes of a split building: its bars read pmr_rs_<j> (recipe j's share), not pmr_sh_<i>
RETOOL_COST = {}  # short name -> construction one retool level costs (pmr_retool_cost_<b>), for tooltips
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
# Pat, 2026-10-19 12:59Z ("a threshold; new combination is at least 25% more productive; then progress points speed
# up for how much more productive it really is"): a recipe other than the default (pmr_best_now_<b>, else the last
# pick) becomes the pick only when its profit beats the default's by SWITCH_GAIN of the default's, newer or older,
# and the switching bar then gains gain / SWITCH_GAIN points a month (at least 1, at most SWITCH_MONTHS). A recipe
# needing more than the default of an input whose price is at the +75% cap is vetoed (vanilla's x0.01 for
# shortages, ai:1001); the default itself no longer is (Pat 12:58Z, "why is this happening if rail is a better
# deal?": the 01:07Z rule moved iron mines off Rail Transportation while engines sat at the cap).
# Pat, 17:14Z: the pick decides how new builds and retooling go (PROFIT_TARGET; False puts back the newest
# runnable recipe), computed only when something changed or on a re-check every six months (profit_effect).
# Pat, 2026-10-19 01:07Z: a new pick becomes that default (pmr_best_now_<b>) only once a bar has filled for
# SWITCH_MONTHS monthly pulses, green up to a newer recipe, red down to an older one (pmr_switch_<b>).
PROFIT_TARGET = True
# Pat 2026-10-21 12:37Z (decision card "Try it"; performance review 9, B1): a state's buildings update on every
# TICK_EVERY-th monthly pulse of the state, half the states each month (pmr_ph, state_turn), so a month runs about half
# of the state tick. Each rate that was "a month" grows by TICK_EVERY an update to keep its pace: a trade-off's step and
# the switching bar's points. The wage watch reads the wage at each update, so every other month as before (review 8, T-1).
TICK_EVERY = 2
# Run A (Pat's observer game 2026-10-21 14:08-14:37Z): the trade-off step (pmr_opts_<b> of a building with trade-offs)
# cost 0.85 s of a game month at every update, the largest part of PMR's monthly script. Pat 2026-10-21 19:35Z: four
# times a year instead of six. A state runs it at all but the last of every OPTS_CYCLE updates (pmr_xc, state_turn), so
# 2 and 4 months apart in turn, the states taking turns, and a step grows to the months since the last (opts_pace).
# Builds, expansions, method changes and research still run it at once; treatment (no prices, ~0 s) runs at every update.
OPTS_CYCLE = 3
PROFIT_RECHECK_DAYS = 182
# Performance review 11 (2026-11-11; Pat 16:33-16:35Z: "good heuristics ... make the existing engine do the work ...
# review everything and come up with the best fit"). The q102 log: 688 of Britain's 705 profit runs after the first
# priced no option but the default, because the default already was the newest recipe the owner could run, and a pick
# with no rival cannot change with prices or wages. The solo gate (pmr_solo_<b>, set at the end of pmr_profit_<b>):
# an AI building whose default is the newest runnable recipe (pmr_new_now_<b>), whose books are read and at 0 or more
# (pmr_ok, pmr_bpl_<b>) and whose run priced no rival (pmr_nrv 0). While it stands, pmr_moved_<b> asks the engine's own
# books instead of deriving the wage (is_subsidized, occupancy, weekly_profit, earnings: the conditions that open the
# options below the default, or stop the books being read), and any of them ends it with a full run at once. A newer
# recipe (research, electricity) ends it through pmr_new_now_<b>, as before. A player's building and one the player
# owns levels in abroad never take it: their cards show every figure.
#   0  off (the q102 code)
#   1  no wage read for a solo building; a price PRICE_MOVE off still runs pmr_profit_<b>
#   2  a price PRICE_MOVE off runs pmr_lite_<b> instead: the books' profit per level, the pick's row and the
#      investment score (pmr_pvs_<b>), which for a building held to its books is all the full run would change
#   3  the re-check timer does the same after scanning for a newer recipe (pmr_newest_<b>); pmr_profit_<b> runs
#      only when the gate ends
#   4  no price check either: the score waits for the re-check (measured, not recommended: review 11)
SOLO_GATE = 0
# Performance review 11: pmr_switch_<b> asks whether the pick is the default before it asks whether the default can
# still run (one test per recipe); with the pick on the default both branches only empty the bar. The same result.
SOLO_COUNTS = ('held', 'end', 'lite', 'full', 'watch')   # test builds: the SOLO log line (pmr_skip_report)
SWITCH_QUICK = False
# Performance review 11: pmr_moved_<b> compares the market's own price (scope:pmr_xmo.var:pmr_mpx_<good>, the value
# pmr_price_<good> copies) with the bounds, without the state's copy and its day guard; pmr_profit_<b> and the
# trade-offs read their own copies as before. The same prices.
WATCH_DIRECT = False
# Performance review 12 (2026-11-11; Pat 17:29Z: "a full review of where else we can save on performance ... through
# restructuring and otherwise clever scripting and better engine leverage for outcomes"). Each switch is off by default
# (= the q102 output) and stands alone.
# RESEARCH_MAP: a research pass scans only the building types whose newest-recipe rules (pmr_newest_<b>, pmr_hbest_<b>)
# name a technology the country holds since its last look (pmr_tk_<technology> on the country; 123 of 1.15's 178
# technologies are named by none, and one that is touches 3.2 types of 48 on average). The scan has no other input a
# technology can change, so the types left out would have read the same newest recipe. Its other inputs keep their own
# wake: electricity and rail (pmr_lsup), a law the rules name (pmr_lw_<law>, asked at the country's monthly pulse, where
# q102 waited for the next technology), and a state that changed hands, whose next update scans every type (pmr_own).
# AUTO_BEST's pass runs only for a technology its ladders name; its monthly run stays.
RESEARCH_MAP = False
RESEARCH_TECHS = {}   # building short name -> the technologies its newest-recipe scans ask about (tick_effect fills it)
RESEARCH_LAWS = {}    # building short name -> the laws they ask about
RESEARCH_OTHER = {}   # building short name -> unlock keys of its recipes that are neither (scanned at every technology)
# PF_SUMS: the AI countries' investment term (pmr_pterm_<b>, the pick's vanilla score averaged over the country's
# levels) from running sums: a state adds the difference to its owner's sums when its score or level moves
# (pmr_pf_sync_<b>, from pmr_best_<b>), where pmr_pf_all swept every state of every AI country for every type each
# month. The same sums, so the same term (private_investment.pf_sums_effects). A state that changed hands moves its
# parts (pmr_own_check, from on_state_owner_change and the state's monthly pulse); a country takes its sums afresh once
# a year and in a month its number of states moved. A building that is gone leaves the sums, which the sweep never
# saw (the state kept its last pmr_level_<b>). Test builds log PMR;rec=PFSUM monthly.
PF_SUMS = False
PF_SYNC = set()   # short names of the types whose pmr_best_<b> calls pmr_pf_sync_<b> (tick_effect fills it)
# QUIET_TICK: an AI building's monthly update with nothing open, queued or moved since its last accounting ends after
# the ownership read and the trade-off step: every later step of pmr_tick_body_<b> tests one of the same facts and
# would skip its part. Test builds count them (PMR;rec=QUIET monthly).
QUIET_TICK = False
# VALUE_READS: the building's books as plain numbers. 1.15's own script reads weekly_profit as a value in building
# scope (common/treaty_articles/18_acquire_monopoly_for_company.txt) and numeric triggers through a scope chain
# everywhere (scope:target_state.gdp), so earnings, weekly_profit, occupancy and country_ownership_fraction need no
# bisection: about 175 operations a books read and 43 an ownership read become a handful.
#   0  off: the ladders (pmr_read_books, pmr_read_gov_<b>)
#   1  test builds only: the ladders decide, and the monthly BOOKS line counts how often a plain read of the same
#      figure lands outside the ladder's step (pmr_dv_n, pmr_dv_bad), so one game says whether 2 is safe
#   2  the plain reads decide
VALUE_READS = 0
# LEAN_CHECKS: the monthly state checks that find nothing leave on one test: the transport principle's bonus where
# the state can earn none and has none standing; the Buildings tab's list where the state has no list walks the
# state's buildings for a retool site twice a year, not monthly (a site's build events refresh the list at once).
LEAN_CHECKS = False
# LEAN_CHARTS: the Private tab's contributors charts are counted weekly only while the tab was shown in the last
# 30 days, else every fourth week, and recount as the tab shows (private_investment.LEAN_CHARTS).
LEAN_CHARTS = False
URB_WALK_DAYS = 180   # LEAN_CHECKS: a state with no urban list walks its buildings for a retool site this often
PROFIT_RECHECK_SPREAD = 60     # re-checks fall 30 days either side, in 7 steps
SWITCH_MONTHS = 6
SWITCH_GAIN = 0.25
# Pat, 2026-10-19 22:47Z (decision card "Both", observer run q51: USA ports went Industrial -> Basic -> Industrial ->
# Basic in four months on figures of -£45 to +£4, which the relative test reads as +171%): a switch also needs
# SWITCH_MIN £ a week per level over the default, and a building whose books can't be read (pmr_bsx_<b>: government
# paid, subsidised, nearly empty) keeps its default. Pat 2026-10-20 12:56Z: a subsidised one with staff may still step up (profit_effect).
SWITCH_MIN = 20
PROFIT_RULE = 107    # added to pmr_pmb_<b> (pmr_moved_<b>): a new pick rule makes older saves recompute once (q40;
                     # 101: q46, the transportation rule; 102: q47, figures held to the books; 103: q48, a railway;
                     # 104: q50, no step down while the building makes money; 105: q52, SWITCH_MIN and unread books;
                     # 106: q61, a subsidised building with staff steps up; 107: q79, SWITCH_GAIN_OF)
# Pat, 2026-10-18 21:32Z: "Whatever the true basis for ai scoring is should be reflected." What vanilla's investment
# pool adds to a building's ai_value for a new level (00_ai.txt): its predicted weekly profit divided by the employees
# a level has, x PRODUCTION_BUILDING_GOODS_PROFIT_FACTOR 5000 x the pool's PROFIT_FACTOR_MULT 1.5 (a deficit x
# GOODS_DEFICIT_FACTOR 10000), plus the goods it makes at base value x PRODUCED_VALUE_FACTOR 0.25 x the pool's 1.25.
# pmr_profit_<b> scores its pick so (pmr_pvs_<b>); private_investment.pf_effects averages it per country into the
# type's ai_value. The market terms (price bands, wanted goods, shortages) stay the game's own, per state.
VANILLA_PROFIT_W, VANILLA_DEFICIT_W, VANILLA_OUTPUT_W = 5000 * 1.5, 10000, 0.25 * 1.25
TARGET_EMPLOYEES = {}   # building type -> employees per level of each retool target (the order of econ)
TARGET_OUTPUTS = {}     # building type -> the goods each retool target makes (the order of econ), for Output's tooltip
# Pat, 2026-10-13: a recipe that needs electricity (its own goods, its folded automation, or vanilla's
# required_input_goods) can't become a building's target unless its state produces electricity, and
# retooling towards it pauses while the state has none. One rule for government and private retooling.
ELECTRICITY = 'electricity'
# Pat, 2026-10-19 16:49Z ("prevent our pm automation default from setting a rail transport if there is no rail transport
# in a state"): transportation is local too, and the engine cuts a building's whole output by 75% when an input is
# missing from local supply (GOODS_SHORTAGE_PENALTY_MISSING_INPUTS; Michigan's sulfur mine, q45: a quarter of its levels
# on Rail Transport left all four making a quarter). A recipe using it can be the default only where the state has a
# railway (pmr_rail), even one the building already runs. Pat 17:49Z: a port's transportation doesn't count (West
# Bengal's opium, q47: rail=1 from its port, no railway, retooling onto Rail Transport).
TRANSPORTATION = 'transportation'
# Pat, 2026-11-10 12:44Z: "eliminate the state checks for electricity and rail and still have the system work!" Until q95
# every tick read the state's electricity (sg:electricity state_goods_production) and railway (has_building) itself.
# Since q96 the state's turn sets both flags from the very has_building test it already makes to tick each building
# type: SUPPLY's types tick first, each setting its flag to 1 (pmr_tick_body_<b>) or, gone, to 0, so every later type
# that turn sees them, and so does any tick between turns (a new building, research, a method change) and AUTO_BEST.
# Only power plants make electricity in vanilla (pm_*_power_plant), and only a railway counts for transportation.
SUPPLY = (('building_power_plant', 'pmr_elec'), ('building_railway', 'pmr_rail'))


def rails(goods):
    """a recipe's goods per level ({good: amount}, inputs negative) take transportation"""
    return goods.get(TRANSPORTATION, 0) < 0
# Loop breaker (2026-10-13: Pat's game froze during the daily update of 16 June 1836, and debug.log
# held nothing after 11 June). A building type's tick that runs more than TICK_TRIP times in one
# state in one day stops there for the rest of the day and writes a TRIP line. TRIP and RELEASE (a
# private retool building with a crew removed) lines go through flush_log: debug.log reaches disk in
# 4 KB blocks, so the last lines before a hang are lost unless one line fills a block by itself.
TICK_TRIP = 25
FLUSH_PAD = 4500
# S3 (performance review 3; Pat, 2026-10-19 02:35Z): a tick skips the level accounting when nothing it reads has
# changed (pmr_recount_<b>). In test builds a player's building that skipped this many ticks in a row runs it
# anyway and logs SKIP_MISS for any value the skipped ticks had left different, and the player's country logs a
# SKIP line a month: the ticks that skipped, ran it, and ran it as that check.
SKIP_CHECK = 12
# Second groups (Pat approved both 2026-10-13; built from 03:21Z). A group after the recipe group is
# either a trade-off, blended by market prices, or a plantation's working conditions, blended by the
# workforce's acceptance. Each of its options (every method but the one that does nothing) gets a share
# of the building, in 1% steps, through share methods built like the recipe ones; the do-nothing method
# is the remainder. The vanilla group stays on the building as a marker that carries nothing: it keeps
# the game's history setup readable at game start and lets can_activate_production_method gate each
# option by technology, law and recipe as vanilla would.
# Trade-offs (pmr/second-groups.md): each option is valued at its market's prices (outputs minus inputs per level,
# goods only), and points move from the worst-paying option with a share to the best-paying one, when the gap beats
# TRADE_DEAD_BAND of the building's output value per level. "None" is worth 0. A building built during the game starts
# on the best-paying option.
# Pat 2026-11-10 (q94): "One of the slowest parts of the mod is the pricier checks; could we instead of doing these set
# the PM2's to be gated based on Supply/Demand orders of the market and be market based and drop the locality? Also
# have them operate in larger chunks of 5%?" A good's price is no longer read per state through a state_goods_pricier
# ladder (about five comparisons a good, a state and a day) but once a month per market from its order book
# (market_values): vanilla's price from buy and sell orders, base x (1 + PRICE_RANGE x (buy - sell) / the smaller of
# the two, within -1..1; BUY_SELL_DIFF_AT_MAX_FACTOR 2). A local good (LOCAL_GOODS) counts at its market's (q96). Shares move
# OPT_STEP points a month and hold multiples of it, with share methods only at those (21 an option, not 101).
# Before q94 (Pat 2026-10-13) the move was the gap in % of the output value, 2 to 20 points a month.
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
                'pmg_explosives_building_gold_mine', 'pmg_explosives_building_copper_mine',   # copper: new in 1.15
                # Pat 2026-10-19 21:12Z: the ranches' wool (simple, sheep farms, intensive grazing) blended like
                # hardwood. Its none, Simple Ranch, makes wool of its own: the options carry their difference from it
                # (Option.less) and the marker stays on it (option_effects).
                'pmg_sheep_ranch')
OPT_STEP = 5
PRICE_RANGE = 0.75   # vanilla's (00_defines.txt): a price runs from 0.25 to 1.75 of base
kept_none = set()     # (building, none method) of a trade-off whose none has effects: its marker stays on it
# (file, text, replacement): vanilla script errors PMR corrects, each text found once. Each ships a whole copy of the
# vanilla file, so a mod with its own copy clashes. q77 and 2026-10-29 (#12) dropped the Hawaii fix for that; Pat put it
# back both times (2026-10-21 22:34Z, and 2026-10-30 13:31Z after the q91 observer run, whose error log filled with it
# from the 1850s at about 45 a second). 1.15 fixed it in vanilla (00_default_strategy.txt:3009 names
# s:STATE_HAWAIIAN_ISLANDS), so PMR no longer ships the file.
VANILLA_FIXES = []
# Pat 2026-10-25 22:08Z: "Unlock Aerial Recon from requiring supply in the market". A mobilization option here loses
# the has_potential_supply check of the goods listed, through a REPLACE: of that one option in a file loaded after
# vanilla's (as Market Liberal, private_investment.IDEOLOGY_FILE), so an army can ask for a good before anyone makes it.
MOBILIZATION_SOURCE = 'common/mobilization_options/00_mobilization_option.txt'
MOBILIZATION_FILE = 'common/mobilization_options/zz_pmr_mobilization_options.txt'
MOBILIZATION_UNGATE = {'mobilization_option_aerial_recon': ('aeroplanes',)}
PRESTIGE_JE_FILE = '05_prestige_goods.txt'   # vanilla's prestige goods journal entries (off: Hallmark Goods gives prestige goods)
# Pat, 2026-10-13: new games start each trade-off near where games take it, not on vanilla's history
# choice. Read from his Great Britain save of 28 October 1838 by tools/pmr/save_blends.py: for each
# building type, the share of the world's levels whose best-paying option at their state's prices
# is each option (none below the dead band). At game start a building takes these shares; an option
# its state can't run yet passes its share to the option before it in vanilla's order, then to none.
# Buildings built later still start on their own best-paying option. A type left out keeps vanilla's
# start (automotive: none built by 1838). Since q94 each share rounds to OPT_STEP (start_shares).
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
# Pat 2026-10-30 (#12): more paper mills at game start, so paper starts near vanilla's price, erring low. AUTO_BEST runs
# administrations and universities on their newest methods from day one, about 1,690 more paper a week than vanilla's
# history methods; these 33 levels make about 1,800-1,920 (/mnt/project-files/pmr/paper-start/PLAN.md). Only states
# that import paper, each on vanilla's own block and start method. (state, region_state tag, building): ((owner entry,
# its building type, its region), levels added); the owner entry is a building of add_ownership, or its country (None).
START_LEVELS = {
    ('STATE_WEST_BENGAL', 'BIC', 'building_paper_mill'): (('building', 'building_paper_mill', 'STATE_WEST_BENGAL'), 8),
    ('STATE_GUJARAT', 'BIC', 'building_paper_mill'): (('building', 'building_paper_mill', 'STATE_GUJARAT'), 3),
    ('STATE_HYDERABAD', 'HYD', 'building_paper_mill'): (('building', 'building_paper_mill', 'STATE_HYDERABAD'), 1),
    ('STATE_NEW_YORK', 'USA', 'building_paper_mill'): (('building', 'building_financial_district', 'STATE_NEW_YORK'), 5),
    ('STATE_AUSTRIA', 'AUS', 'building_paper_mill'): (('building', 'building_financial_district', 'STATE_AUSTRIA'), 5),
    ('STATE_VENETIA', 'AUS', 'building_paper_mill'): (('building', 'building_financial_district', 'STATE_VENETIA'), 2),
    ('STATE_HOME_COUNTIES', 'GBR', 'building_paper_mill'): (('building', 'building_financial_district', 'STATE_HOME_COUNTIES'), 2),
    ('STATE_WALES', 'GBR', 'building_paper_mill'): (('building', 'building_financial_district', 'STATE_HOME_COUNTIES'), 1),
    ('STATE_BRANDENBURG', 'PRU', 'building_paper_mill'): (('building', 'building_financial_district', 'STATE_BRANDENBURG'), 2),
    ('STATE_FLANDERS', 'BEL', 'building_paper_mill'): (('country', None, None), 1),
    ('STATE_PIEDMONT', 'SAR', 'building_paper_mill'): (('country', None, None), 1),
    ('STATE_ESTREMADURA', 'POR', 'building_paper_mill'): (('building', 'building_paper_mill', 'STATE_ESTREMADURA'), 1),
    ('STATE_CAMPANIA', 'SIC', 'building_paper_mill'): (('country', None, None), 1),
}
TRADE_DEAD_BAND = 0.05
# Pat, 2026-10-25 (a player on Discord: "no aeroplanes", tanks and radios came a couple of years late): nobody asks for
# aeroplanes until some exist. Pops' leisure need weighs a good by its share of the market's sell orders, and Aerial
# Reconnaissance needs a supply in the market, so with none made the price sits at base, where 10 aeroplanes (£80)
# for 10 cars (£100) never pays. Pat: "churn out when needed", with chunky thresholds to keep it cheap. A demand-led
# group follows its market's price instead of its options' worth: DEMAND_STEP points a month toward its one option
# while the market pays DEMAND_BAND over base, away while it pays that much under, never under DEMAND_SEED while the
# option can run. Since q94 the price is the one the market's order book gives (market_values), no valuation.
# Pat 22:07Z: "10% aero planes is way way to many". 22:08Z: Aerial Reconnaissance no longer needs aeroplanes on sale
# (MOBILIZATION_UNGATE), "that way it would cause a shortage and then pmr automatically would pick it up", so no seed.
# 22:09Z: "unlock tanks as well please": tanks too (armies already ask for them, without a supply).
DEMAND_GROUPS = ('pmg_aeroplanes', 'pmg_tanks')
DEMAND_SEED = 0
DEMAND_STEP = OPT_STEP
DEMAND_BAND = 0.25
# Treatment (pmr/treatment-by-acceptance.md): Violent Treatment's share is the building's workforce
# with acceptance under TREAT_BANDS[0], Exploitative Practices' (Pat's "harsh") the workforce from
# there to under TREAT_BANDS[1], recounted monthly. Every effect of each method, output, penalties and
# slave imports alike, scales by its share (Pat, 02:26Z). The law wins: a share the owner's laws bar
# goes to the nearest treatment they allow (violent to harsh to standard; standard, barred under the
# slave trade, to harsh, then violent).
# Trade-off bar colours, muted and never red or green, apart from the recipe tiers; "none" is grey.
OPTION_COLORS = [('Sand', (0.80, 0.71, 0.50)), ('Dusk blue', (0.31, 0.45, 0.66)),
                 ('Rose', (0.77, 0.58, 0.66)), ('Umber', (0.54, 0.40, 0.27))]   # SPEC.md A7
OPTION_NONE_COLOR = (0.40, 0.40, 0.40)
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
MOD_VERSION = '0.5.0'
SUPPORTED_VERSION = '1.15.*'

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
# Issue #13 (Crimea River, 2026-10-23: Arts Academies never retool; Pat: they should retool like other buildings). Their
# recipes carry no wages (WORKFORCE_ELSEWHERE), so a recipe's profit is its goods margin alone, and Realist Art (6 art for
# 15 paper) can never beat Traditional Art (5 for 10) by SWITCH_GAIN at any prices: 6A - 15P >= 1.25 (5A - 10P) needs
# -0.25A >= 2.5P. As options are priced one step from the default, Photographic and Film Art never came up either. Such a
# building switches on SWITCH_MIN alone (Realist Art at base prices: GBP 50 a week a level more).
SWITCH_GAIN_OF = {bk: 0 for bk in WORKFORCE_ELSEWHERE}
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
# Pat 2026-11-11 22:12Z ("Follow supply"): in a game granted every technology in 1836, PMR's newest-method rule put the
# Midlands administration on Switchboards with no telephones anywhere in its market, and its bureaucracy fell with the
# shortage. SUPPLY_BLEND names, per AUTO_BEST group, the ladder methods reached through a blend: when one is the newest the
# owner has, the group runs a blend of it and the method before it, in BLEND_STEPS steps. On the state's building update
# (every other month) the blend moves a step toward the newest while every good that method adds sells at least
# BLEND_UP of its buy orders in the state's market (price at most +25% over base), and a step back while one sells at
# most BLEND_DOWN of them (price at vanilla's +75% cap); in between it holds. Every other ladder method is still taken
# at once, as before. The blends are methods of their own (pm_pmr_blend_<b>_<i>_<k>: k tenths of ladder method i over
# method i-1), self-locked and hidden so only PMR sets them; so is a blended method no history file starts, so the AI
# can't jump to it past the blend. No construction: vanilla switches these for free.
SUPPLY_BLEND = {'building_government_administration': ('pmg_base_building_government_administration', ['pm_switch_boards'])}
BLEND_STEPS = 10
BLEND_UP = 0.75
BLEND_DOWN = 0.5
BLEND_INFO = {}   # {(building key, group): {'ladder', 'techs', 'adds', 'keys'}}; filled by supply_blends before any effect


def blend_fill_values():
    """SUPPLY_BLEND's script values: pmr_blend_fill (market goods scope), sell orders over buy orders, any sell order
    plenty with no buy orders; pmr_sv_bfill_<good> (state scope), the same for the good in the state's market (the
    BLEND line's)."""
    goods = sorted({gd for i in BLEND_INFO.values() for gl in i['adds'].values() for gd in gl})
    return ('pmr_blend_fill = {\n\tvalue = market_goods_sell_orders\n\tdivide = {\n\t\tvalue = market_goods_buy_orders\n'
            '\t\tmin = 0.001\n\t}\n}\n\n'
            + ''.join(f'pmr_sv_bfill_{gd} = {{\n\tvalue = 0\n\tmarket ?= {{ mg:{gd} ?= {{ add = pmr_blend_fill }} }}\n}}\n\n'
                      for gd in goods))
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
    # q57: the Freedom of Movement principle variant too, as the Arts Academy's; with the panel's grid hidden nothing
    # else could switch it on
    'building_university': ('pmg_base_building_university', 'pmg_university_academia', 'pmg_principle_freedom_of_movement_3'),
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
# share through an executive trait (run sheet: /mnt/project-files/pmr/mio/works-share-probe/RUN.md). sub_company
# (Pat 2026-10-19 04:13Z) asks whether script can found a company mid-game and give it levels, at 2 and at 5 levels
# (/mnt/project-files/pmr/sub-companies/FINDINGS.md). A probe's English localisation is copied to every other language.
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
# Pat 2026-10-30 12:35Z: "track every single save log we do by build version". A test build made with --build qN
# stamps itself: a BUILD line at game start and once a game year (the largest economy's monthly pulse), and the global
# variables pmr_build (the build that ran last) and pmr_build_first (the one that started the game) in every save.
# tools/pmr/runs.py files each log line and autosave under the build it names.
BUILD = None      # set by main(): (tag, number, commit) from --build, test builds only


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
        # What the share methods don't carry, by (section, block): unscaled effects (sugar's slave mortality and
        # standard of living, patio drying's mortality) and level-scaled ones that aren't jobs. A recipe keeps
        # them on its own method; a pair marker repeats its recipe's, and an automation member carries its own
        # x its share of the levels (the automation methods themselves never run).
        self.rest = {}
        for sec in BLEND_SECTIONS:
            sn = pdx.get(node.value, sec)
            for sub in (sn.value if sn else []):
                if not sub.key or sub.key == 'workforce_scaled':
                    continue
                if not sub.is_block:
                    raise SystemExit(f'{key}.{sec}.{sub.key} is not a block; extend Recipe before shipping')
                for n in sub.value:
                    if n.key and not (sub.key == 'level_scaled' and n.key.startswith('building_employment_')):
                        d = self.rest.setdefault((sec, sub.key), {})
                        d[n.key] = d.get(n.key, 0) + num(n.value, f'{key}.{sec}.{sub.key}.{n.key}')
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

    def frame_body(self, body):
        """Method-count rework (Pat 2026-11-10): the recipe is a pure frame, its retool target's full goods, jobs and
        other modifiers (frames.pure_mods: its own, and its first automation option's with the split). Its modifier
        blocks are replaced by body; required_input_goods goes, as a frame the game switched off for a missing good
        would come straight back through the tick. PMR keeps the electricity rule itself (pmr_best_<b>)."""
        for n in self.node.value:
            if n.key in BLEND_SECTIONS or n.key == 'required_input_goods':
                self.src.cuts.append(line_span(self.src.text, n))
        self.src.inserts.append((self.node.end - 1, body))

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
        self.locked = False   # frame_lock: unlocks only while it runs

    def needs(self, good):
        return self.base.needs(good) or any(m.needs(good) for m in self.opt)

    def method(self, body):
        """the pair's pure frame: its gates, then body (frames.sections of its full modifiers)"""
        return (f'{self.key} = {{\n\ttexture = "{self.texture}"\n'
                + (f'\tunlocking_technologies = {{\n' + ''.join(f'\t\t{t}\n' for t in self.techs) + '\t}\n'
                   if self.techs else '')
                + ''.join(f'\t{g}\n' for g in self.gates)
                + (f'\tunlocking_production_methods = {{ {self.key} }}\n' if self.locked else '')
                + body + '}\n')


LOCK_NOTE = '# PMR: unlocks only while it runs (the AI\'s lock); PMR asks the rest itself'


def frame_gate(bk, nodes, frames_of_bk, adds):
    """frames.Gate: what vanilla's unlock keys ask of a method made of nodes (a recipe's or an option's own method; a
    pair's recipe and its automation methods, each of which must be allowed), or None where a key asks something the
    gate does not state, and the method keeps the game's own check.
    - unlocking_technologies: every one (vanilla lists one a method; a pair lists its recipe's and its automation's,
      and the tick has always asked the owner for each);
    - disallowing_laws: none of them, in any variant;
    - unlocking_geographic_regions, unlocking_principles: a single entry only, so no any-or-all is assumed (and an
      empty region list asks nothing: vanilla's one is on dry process coffee, which every coffee plantation starts on);
    - unlocking_production_methods: any one of them running, or a frame of bk built on one (adds, as the list itself
      gained them before the lock)."""
    techs, owner, state, run = [], [], [], []
    for node in nodes:
        for n in node.value:
            if not n.key or not n.key.startswith(('unlocking_', 'disallowing_')):
                continue
            xs = pdx.items(n) if n.is_block else None
            if n.key == 'unlocking_technologies' and xs is not None:
                techs += [t for t in xs if t not in techs]
            elif n.key == 'disallowing_laws' and xs:
                owner += [t for t in (f'NOT = {{ has_law_or_variant = law_type:{x} }}' for x in xs) if t not in owner]
            elif n.key == 'unlocking_geographic_regions' and xs is not None and len(xs) <= 1:
                state += [f'is_in_geographic_region = {x}' for x in xs]
            elif n.key == 'unlocking_principles' and xs and len(xs) == 1:
                owner.append(f'power_bloc ?= {{ has_principle = principle:{xs[0]} }}')
            elif n.key == 'unlocking_production_methods' and xs:
                on = [x for x in dict.fromkeys(xs + adds) if x in frames_of_bk]
                if not on:
                    return None
                run.append((bk, on, []))   # kept as a list: the unions' job versions join it (frames.widen_gates)
            else:
                return None
    return frames.Gate(techs, owner, state, run)


def frame_lock(treated, options, groups, pm_groups, pms, frame_adds):
    """The AI's lock (frames.LOCK_PURE, Pat 2026-11-10 21:31Z): every pure frame but the first of its group unlocks
    only while it runs, and frames.GATES holds what PMR asks in the game's place. A frame stays open (vanilla's keys,
    the game's check) where it is the first method of a group, where a group PMR does not frame lists it too, or where
    one of its keys is not one frame_gate states.
    Returns {'locked': {method key}, 'open': {method key: why}}."""
    frames.GATES.clear()
    out = {'locked': set(), 'open': {}}
    if not frames.LOCK_PURE:
        return out
    frame_groups = {t[4] for t in treated} | {g for conv in options.values() for g, _gi, mode, *_r in conv if mode == 'market'}
    firsts = {groups[g][0] for g in frame_groups if groups.get(g)}
    gates, pairs = {}, {}
    for bk, _bn, _s, recipes, g0, _pg in treated:
        of_bk = set(groups.get(g0, [])) | {r.key for r in recipes} | {f'pm_pmr_union_{short(bk)}_{p}'
                                                                       for p in range(1, len(recipes) + 1)}
        cands = [(r.key, [r.base.node] + [m.node for m in r.opt] if isinstance(r, PairRecipe) else [r.node], r)
                 for r in recipes]
        cands += [(o.key, [o.node], None) for _g, _gi, mode, _none, opts, _std in options.get(bk, []) if mode == 'market'
                  for o in opts]
        for key, nodes, r in cands:
            why = None
            if key in firsts:
                why = 'the first method of a group'
            elif not pm_groups.get(key, set()) <= frame_groups:
                why = 'also in ' + ', '.join(sorted(pm_groups[key] - frame_groups))
            else:
                gate = frame_gate(bk, nodes, of_bk, frame_adds.get(key, []))
                if gate is None:
                    why = 'an unlock key the gate does not state'
                else:
                    gates[(bk, key)] = gate
                    if isinstance(r, PairRecipe):
                        pairs[key] = r
            if why:
                out['open'][key] = why
    # replacement_if_valid (vacuum canning and its power bloc variant): the game takes the method away where its
    # replacement may run, so the gate does too; a replacement with no gate of its own leaves the method open
    for (bk, key), gate in gates.items():
        rep = pdx.get(pms[key][0].value, 'replacement_if_valid') if key in pms else None
        if rep is not None and rep.value in DROP_RECIPES:   # a principle variant PMR drops, the line with it
            continue
        if rep is not None and (bk, rep.value) in gates:
            if gates[(bk, rep.value)].run:   # written out here, before the unions' job versions join it (widen_gates)
                raise SystemExit(f'{key}: its replacement {rep.value} asks for a recipe; state that gate once the frames are built')
            gate.state.append('NOT = { ' + gates[(bk, rep.value)].trigger() + ' }')
        elif rep is not None:
            out['open'][key] = f'replaced by {rep.value}, which has no gate'
    # a method two buildings share is locked for both or for neither
    for (bk, key), gate in gates.items():
        if key not in out['open']:
            frames.GATES[(bk, key)] = gate
            out['locked'].add(key)
    for key in sorted(out['locked']):
        if key in pairs:
            pairs[key].locked = True
            continue
        n, psrc = pms[key]
        upm = pdx.get(n.value, 'unlocking_production_methods')
        if upm is not None:
            psrc.cuts.append(line_span(psrc.text, upm))
        psrc.inserts.append((n.end - 1, f'\tunlocking_production_methods = {{ {key} }}  {LOCK_NOTE}\n'))
    return out


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

    processing = {p for g in PROCESSING_GROUPS for p in groups.get(g, [])}   # vanilla's numbers, unbuffed
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
                    autos = [a for a in opt if a.employment and a.key not in processing]
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
        # goods per level at full employment: outputs positive, inputs negative; self.used the inputs alone (q97: a
        # smaller output, hardwood's wood, is not bought from the market)
        self.goods, self.used = {}, {}
        for mk, mv in self.mods.get(('building_modifiers', 'workforce_scaled'), {}).items():
            for pre, sign in (('goods_output_', 1), ('goods_input_', -1)):
                if mk.startswith(pre) and mk.endswith('_add'):
                    g = mk[len(pre):-len('_add')]
                    self.goods[g] = self.goods.get(g, 0) + sign * mv
                    if sign < 0:
                        self.used[g] = self.used.get(g, 0) + mv
        self.required = [n.value for n in self.node.value if n.key == 'required_input_goods']
        self.elec = ELECTRICITY in self.required or self.goods.get(ELECTRICITY, 0) < 0

    def less(self, base):
        """Carry only the difference from `base` (an Option read from the group's none method): a none that has
        effects of its own keeps them, so an option's share adds what it changes."""
        for k, d in base.mods.items():
            mine = self.mods.setdefault(k, {})
            for mk, mv in d.items():
                mine[mk] = mine.get(mk, 0) - mv
                if abs(mine[mk]) < 1e-9:
                    del mine[mk]
        for mine, theirs in ((self.goods, base.goods), (self.used, base.used)):
            for g, amt in theirs.items():
                mine[g] = mine.get(g, 0) - amt
                if abs(mine[g]) < 1e-9:
                    del mine[g]

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
# Localisation keys sharing a hash. The game files its text by a 32-bit hash of the key and keeps one text for two
# keys with the same hash, so the other key shows raw (1.15 error.log: "Localization key hash collision. Key
# 'intelligentsia.1.b' and 'pm_pmr_share_steel_mill_2_27' have the same hash: 4271602869", then "Unrecognized loc
# key intelligentsia.1.b": a 1.15 event option lost its text). The hash is MurmurHash3 (32-bit, seed 0) of the key.

def murmur3_32(s):
    data, h = s.encode('utf-8'), 0
    n = len(data)
    for i in range(0, n - n % 4, 4):
        k = int.from_bytes(data[i:i + 4], 'little') * 0xcc9e2d51 & 0xffffffff
        k = ((k << 15) | (k >> 17)) & 0xffffffff
        h ^= k * 0x1b873593 & 0xffffffff
        h = ((h << 13) | (h >> 19)) & 0xffffffff
        h = (h * 5 + 0xe6546b64) & 0xffffffff
    if n % 4:
        k = int.from_bytes(data[n - n % 4:], 'little') * 0xcc9e2d51 & 0xffffffff
        k = ((k << 15) | (k >> 17)) & 0xffffffff
        h ^= k * 0x1b873593 & 0xffffffff
    h ^= n
    h ^= h >> 16
    h = h * 0x85ebca6b & 0xffffffff
    h ^= h >> 13
    h = h * 0xc2b2ae35 & 0xffffffff
    return h ^ (h >> 16)


LOC_KEY = re.compile(r'^[ \t]+([\w.\-\']+):\d*[ \t]*"', re.M)


def loc_keys(folder):
    keys = set()
    for dirpath, _dirs, files in os.walk(folder):
        for fn in files:
            if fn.endswith('.yml'):
                with open(os.path.join(dirpath, fn), encoding='utf-8-sig', errors='replace') as f:
                    keys.update(LOC_KEY.findall(f.read()))
    return keys


def rename_hash_clashes(game, out, release):
    """Rename, everywhere in the build, each PMR key whose hash a vanilla key (or another PMR key) already has.
    Returns {old: new}."""
    vanilla = loc_keys(os.path.join(game, 'localization', 'english'))
    if len(vanilla) < 50000:
        msg = f'{len(vanilla)} vanilla localisation keys under --game: the key hash check needs the full install'
        if release:
            raise SystemExit(msg)
        print('warning: ' + msg)
    mod = loc_keys(os.path.join(out, 'localization', 'english'))
    owner = {}
    for k in sorted(vanilla) + sorted(mod - vanilla):
        owner.setdefault(murmur3_32(k), k)
    clash = sorted(k for k in mod - vanilla if owner[murmur3_32(k)] != k)
    if not clash:
        return {}
    texts = {}
    for dirpath, _dirs, files in os.walk(out):
        for fn in files:
            if fn.endswith(('.txt', '.yml', '.gui')):
                path = os.path.join(dirpath, fn)
                with open(path, encoding='utf-8', newline='') as f:
                    texts[path] = f.read()
    renames = {}
    for k in clash:
        n = 1
        while f'{k}_h{n}' in vanilla or f'{k}_h{n}' in mod or murmur3_32(f'{k}_h{n}') in owner:
            n += 1
        renames[k] = f'{k}_h{n}'
        owner[murmur3_32(renames[k])] = renames[k]
    alt = '|'.join(map(re.escape, renames))
    tok = re.compile(r'(?<![\w.])(' + alt + r')(?![\w.])')
    derived = re.compile(r'(?<![\w.])(?:' + alt + r')_\w')   # its _desc and the like would keep the old name
    for path, text in texts.items():
        if not any(k in text for k in renames):
            continue
        m = derived.search(text)
        if m:
            raise SystemExit(f'{path}: {text[m.start():m.end() + 20]!r} extends a key whose hash a vanilla key '
                             'has; rename that key by hand')
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(tok.sub(lambda m: renames[m.group(1)], text))
    return renames


# ---------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--game', required=True, help='path to the Victoria 3 "game" folder')
    ap.add_argument('--out', default=None, help=f'default {DEFAULT_OUT}, or {RELEASE_OUT} with --release')
    ap.add_argument('--release', action='store_true',
                    help='the build players get: no test decisions, no generation report, no log lines but '
                         + ' and '.join(RELEASE_LOGS))
    ap.add_argument('--beta', action='store_true',
                    help='with --release: the open beta, a Workshop item of its own beside the published mod (Pat '
                         '2026-11-12 02:55Z): named "Production Method Rework BETA", id org.prob32.pmr.beta, version '
                         'MOD_VERSION-beta')
    ap.add_argument('--version-label', default='', help='game build label written into the README header')
    ap.add_argument('--test-name', default='', metavar='LABEL',
                    help='a test build for its own mod folder: names the mod "Production Method Rework (LABEL)" '
                         'with its own id, so it never replaces the published one')
    ap.add_argument('--test-decisions', action='store_true',
                    help='test build: the "PMR test:" decisions and the test probes (pmr/test_probes). Off by default '
                         'since Pat 2026-10-20 13:26Z: the test build stays close to the release')
    ap.add_argument('--digit-shares', action='store_true',
                    help='each share as tens and units methods (q53) instead of one method per share (SHARE_DIGITS)')
    ap.add_argument('--obs-script-off', action='store_true',
                    help='test build: observer games pause PMR\'s script in OBS_AB_YEARS, to time months without it')
    ap.add_argument('--obs-parts-off', action='store_true',
                    help='test build: observer games switch one part of PMR\'s monthly script off a year (OBS_PARTS)')
    ap.add_argument('--obs-pad', action='store_true',
                    help='test build: observer games give every state OBS_PAD_N dummy variables in OBS_PAD_YEARS and update '
                         'every state monthly in OBS_MONTHLY_YEARS, to time what the count of a state\'s variables costs '
                         '(review 9) and what TICK_EVERY saves')
    ap.add_argument('--script-profile', action='store_true',
                    help='test build: the HUD writes the script profiler\'s totals every minute (patch_hud_profile); '
                         'the game needs the -script_profiling launch option')
    ap.add_argument('--engine-timing', action='store_true',
                    help='test build: the HUD logs the engine\'s tick task timings and writes them out every '
                         'TIMING_DUMP_S seconds (timing_widget); the game needs -debug_mode')
    ap.add_argument('--frame-probe', action='store_true',
                    help='test build: six British fishing wharves log which of five modifier routes moves a '
                         'building\'s jobs (frame_probe.py, method-count PLAN section 6)')
    ap.add_argument('--group-probe', action='store_true',
                    help='test build: British textile mills in a building group of their own log whether that group\'s '
                         'employee multiplier moves their jobs (group_probe.py, fundamentals-review/group-jobs-probe)')
    ap.add_argument('--timing-only', action='store_true',
                    help='write only a small mod with vanilla\'s HUD and the same timing widget to --out, to time a '
                         'vanilla game (write_timing_mod)')
    ap.add_argument('--solo', type=int, default=None, choices=(0, 1, 2, 3, 4),
                    help='the solo gate (SOLO_GATE): 0 off, 1 no wage watch for a building with nothing to choose, '
                         '2 a light refresh on a price move, 3 a light re-check too')
    ap.add_argument('--quick-switch', action='store_true', help='SWITCH_QUICK (performance review 11)')
    ap.add_argument('--direct-watch', action='store_true', help='WATCH_DIRECT (performance review 11)')
    ap.add_argument('--research-map', action='store_true', help='RESEARCH_MAP (performance review 12)')
    ap.add_argument('--pf-sums', action='store_true', help='PF_SUMS (performance review 12)')
    ap.add_argument('--quiet-tick', action='store_true', help='QUIET_TICK (performance review 12)')
    ap.add_argument('--value-reads', type=int, default=None, choices=(0, 1, 2),
                    help='VALUE_READS (performance review 12): 1 checks plain reads of the books against the ladders '
                         'in a test build, 2 uses them')
    ap.add_argument('--lean-checks', action='store_true', help='LEAN_CHECKS (performance review 12)')
    ap.add_argument('--lean-charts', action='store_true', help='LEAN_CHARTS (performance review 13)')
    ap.add_argument('--build', default='', metavar='qN',
                    help='test build: its tag (q91), stamped into a BUILD log line and the saves (pmr_build)')
    ap.add_argument('--trace-from', default=None, metavar='Y.M.D',
                    help='diagnostic build: flushed T lines from this game date on (see TRACE_FIELDS)')
    args = ap.parse_args()
    global RELEASE, SHARE_DIGITS, OBS_AB, OBS_PARTS_ON, OBS_PAD, SOLO_GATE, SWITCH_QUICK, WATCH_DIRECT
    global RESEARCH_MAP, PF_SUMS, QUIET_TICK, VALUE_READS, LEAN_CHECKS, LEAN_CHARTS
    RELEASE = args.release
    if args.solo is not None:
        SOLO_GATE = args.solo
    SWITCH_QUICK = SWITCH_QUICK or args.quick_switch
    WATCH_DIRECT = WATCH_DIRECT or args.direct_watch
    RESEARCH_MAP = RESEARCH_MAP or args.research_map
    PF_SUMS = PF_SUMS or args.pf_sums
    QUIET_TICK = QUIET_TICK or args.quiet_tick
    if args.value_reads is not None:
        VALUE_READS = args.value_reads
    LEAN_CHECKS = LEAN_CHECKS or args.lean_checks
    LEAN_CHARTS = LEAN_CHARTS or args.lean_charts
    if VALUE_READS == 1 and RELEASE:
        raise SystemExit('--value-reads 1 is a test-build check; a release takes 0 or 2')
    SHARE_DIGITS = args.digit_shares
    OBS_AB = args.obs_script_off
    OBS_PARTS_ON = args.obs_parts_off
    OBS_PAD = args.obs_pad
    if OBS_PAD and (args.release or OBS_AB or OBS_PARTS_ON or args.script_profile):
        raise SystemExit('--obs-pad is a test build of its own: not with --release, --obs-script-off, --obs-parts-off '
                         'or --script-profile')
    if OBS_PARTS_ON and (args.release or OBS_AB or args.script_profile):
        raise SystemExit('--obs-parts-off is a test build of its own: not with --release, --obs-script-off or --script-profile')
    if args.test_name and args.release:
        raise SystemExit('--test-name is for test builds; a release build is the published mod')
    if args.beta and not args.release:
        raise SystemExit('--beta is a release build (--release) published as its own Workshop item')
    if args.script_profile and args.release:
        raise SystemExit('--script-profile is for test builds')
    if args.engine_timing and args.release:
        raise SystemExit('--engine-timing is for test builds')
    if args.frame_probe and args.release:
        raise SystemExit('--frame-probe is for test builds')
    if args.group_probe and args.release:
        raise SystemExit('--group-probe is for test builds')
    if args.timing_only:
        if not args.out or args.release or args.test_name:
            raise SystemExit('--timing-only takes only --game and --out')
        write_timing_mod(args.game, args.out)
        return
    if args.test_decisions and args.release:
        raise SystemExit('--test-decisions is for test builds; players never see a "PMR test:" decision')
    if args.trace_from and (args.release or not re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}', args.trace_from)):
        raise SystemExit('--trace-from takes a game date like 1838.8.15 and never goes into a release build')
    if args.build:
        if args.release or not re.fullmatch(r'q\d+[a-z]?', args.build):
            raise SystemExit('--build takes a test build tag like q91 and never goes into a release build')
        global BUILD
        sha = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(['git', '-C', ROOT, 'status', '--porcelain', '--', 'tools'], capture_output=True, text=True).stdout.strip()
        BUILD = (args.build, int(re.sub(r'\D', '', args.build)), (sha or 'unknown') + ('+' if dirty else ''))
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
        # q57: one recipe is enough where a trade-off follows it (rayon, radios: second-groups.md), as nothing retools
        if len(lst) < 2 and not (lst and any(g in TRADE_GROUPS for g in pdx.items(pg))):
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

    # ---- edit vanilla: the recipe group becomes the frame group ------------------------------------
    # Method-count rework (Pat 2026-11-10, frames.py): the vanilla recipe methods are pure frames again, each its retool
    # target's full goods, jobs and other modifiers (their bodies are written in the per-building loop below, once the
    # members are known); the recipe group also holds the pair frames and one union frame per target.
    automation = {}   # building -> the automation methods folded into its recipes from AUTOMATION_FROM_TIER
    auto_groups_of = {}   # building -> the automation groups that left it (their methods fold into the recipes)
    elec_pms = []     # the electric recipes' marker methods (ElectricRecipe), one per building that has one
    pair_pms = []     # the recipe + automation pairs' marker methods (PairRecipe, SPLIT_AUTOMATION)
    split_info = {}   # building -> its plain recipes, automation options, pair index and blend members
    for bk, bn, s, recipes, g0, pg in treated:
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
                # every recipe with every automation option; (recipe, first option) keeps the vanilla recipe as its marker
                if group_users.get(g0, set()) != {bk}:
                    raise SystemExit(f'{bk}: {g0} is shared with {sorted(group_users[g0] - {bk})}; '
                                     'the recipe + automation pairs would need one marker per building')
                plain_r = list(recipes)
                options = automation_options(auto_groups, groups, pms)
                pairs_l, index = [], {}
                for ri, r in enumerate(plain_r, 1):
                    for a, opt in enumerate(options, 1):
                        # (recipe, first option) marks on the recipe itself unless the option is gated: a first
                        # option that does something (patio drying, hand rolling) is carried by its member's share,
                        # and the game's history and new buildings start on the recipe
                        none = a == 1 and not any(m.unlock_techs or m.gated_otherwise for m in opt)
                        pairs_l.append(r if none else PairRecipe(bk, r, ri, a, opt, pms))
                        index[(ri, a)] = len(pairs_l)
                recipes[:] = pairs_l
                members = [(j, [index[(j, a)] for a in range(1, len(options) + 1)], 'recipe', r)
                           for j, r in enumerate(plain_r, 1)]
                for g in auto_groups:
                    for pk in groups[g]:
                        m = Recipe(pk, *pms[pk])
                        if m.blend or m.employment or m.rest:
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
        # The union frames, last in the recipe group: one per retool target (frames.union_key), in pmr_to order.
        gsrc, gpm = group_src[g0]
        gsrc.inserts.append((gpm.end - 1, ''.join(f'\tpm_pmr_union_{short(bk)}_{p}  # PMR: union frame of {r.key}\n\t'
                                                  for p, r in enumerate(recipes, 1))))

    goods_tex, goods_cost = {}, {}
    for gsrc in load_dir(game, 'goods'):
        for gk, gn in gsrc.objects().items():
            t = pdx.get(gn.value, 'texture')
            if t:
                goods_tex[gk] = t.value
            c = pdx.get(gn.value, 'cost')
            if c is not None:
                goods_cost[gk] = num(c.value, f'{gk} cost')

    # Company Culture: the company types' trees and subsidiaries (company_culture.plan, Pat 2026-10-19 14:43Z; no special
    # production methods any more). In both builds since Pat 2026-10-20 12:59Z ("Ship it"); its "PMR test:" decisions
    # only with --test-decisions.
    company_culture.TEST = args.test_decisions
    cc_plan = company_culture.plan(game, {bk: (split_info[bk]['plain'] if bk in split_info else
                                               [r for r in recipes if not isinstance(r, ElectricRecipe)])
                                          for bk, _bn, _s, recipes, _g0, _pg in treated}, goods_cost, goods_tex)
    THROUGHPUT_KEYS.update(throughput_keys(game, [t[0] for t in treated]))   # pmr_thr (profit_effect)

    # A method another method needs (unlocking_production_methods: pm_elastics needs a sewing machines recipe) is
    # also met by every pair built on it: with the split, the recipe group's marker on such a building is the pair.
    # Method-count rework: and by the union frame of every target built on it, which stands for that target while the
    # building is blended.
    pair_of = {}
    for bk, _bn, _s, recipes, _g0, _pg in treated:
        for p, r in enumerate(recipes, 1):
            base = r.base.key if isinstance(r, PairRecipe) else r.key
            if isinstance(r, PairRecipe):
                pair_of.setdefault(base, []).append(r.key)
            pair_of.setdefault(base, []).append(f'pm_pmr_union_{short(bk)}_{p}')
    # Written once the AI's lock is known (frame_lock below): a locked method's list becomes the method itself, and
    # PMR's gate asks for the frames named here.
    frame_adds = {}
    unlock_users = {}   # recipe -> [methods whose list names it]: the unions' job versions join them (the frames loop)
    for key, (n, psrc) in pms.items():
        upm = pdx.get(n.value, 'unlocking_production_methods')
        listed = pdx.items(upm) if upm else []
        add = [pk for x in listed for pk in pair_of.get(x, []) if pk not in listed]
        if add:
            frame_adds[key] = add
        for x in listed:
            if x in pair_of:
                unlock_users.setdefault(x, []).append(key)

    # ---- second groups: trade-offs and working conditions become option shares -------------------
    # options[bk] = [(group, gi, mode, none method, [Option], standard methods)], gi counting the
    # building's converted groups from 1 and j (Option.j) its options across them.
    options = {}
    kept_none.clear()
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
            if mode == 'market':
                base = Option(bk, 0, g, len(conv) + 1, mode, None, none, pms)
                if base.goods or base.required:
                    for x in opts:
                        x.less(base)
                    kept_none.add((bk, none))
            conv.append((g, len(conv) + 1, mode, none, opts, std))
        if conv:
            options[bk] = conv
    converted = {g for conv in options.values() for g, *_ in conv}
    stripped_opts = set()
    elec_of = {t[0]: t[3][-1] for t in treated if isinstance(t[3][-1], ElectricRecipe)}
    for bk, conv in options.items():
        for g, gi, mode, none, opts, std in conv:
            # Method-count rework: a trade-off group is an option frame group. Its none and options keep vanilla's
            # bodies (frames), less required_input_goods (Recipe.frame_body); the union frame joins them. Treatment
            # keeps its share methods for now: its vanilla methods carry nothing.
            if mode == 'market' and none not in stripped_opts:
                nn, nsrc = pms[none]
                nsrc.cuts += [line_span(nsrc.text, n) for n in nn.value if n.key == 'required_input_goods']
                stripped_opts.add(none)
            if mode == 'market':
                gsrc, gpm = group_src[g]
                gsrc.inserts.append((gpm.end - 1, f'\tpm_pmr_union_{short(bk)}_x{gi}  # PMR: union frame\n\t'))
            for o in opts:
                if not pm_groups[o.key] <= converted:
                    raise SystemExit(f'{o.key} is also in {sorted(pm_groups[o.key] - converted)}, which PMR does not convert')
                if o.key not in stripped_opts:
                    if mode == 'treat':
                        o.strip()
                    else:
                        o.src.cuts += [line_span(o.src.text, n) for n in o.node.value if n.key == 'required_input_goods']
                    stripped_opts.add(o.key)
                # An option that needs a recipe the electric recipe builds on needs the electric
                # recipe too: on it, the recipe group's marker is the electric one.
                er = elec_of.get(bk)
                upm = pdx.get(o.node.value, 'unlocking_production_methods')
                if er and upm and er.base.key in pdx.items(upm) and er.key not in pdx.items(upm):
                    o.src.inserts.append((upm.end - 1, f'\t{er.key}  # PMR: electric recipe\n\t'))
        # The treatment share groups, last in the building's list.
        bsrc, bpg = next((t[2], t[5]) for t in treated if t[0] == bk)
        bsrc.inserts.append((bpg.end - 1, ''.join(
            f'\t{xg}  # PMR: share of {o.key}{part}\n\t'
            for g, gi, mode, none, opts, std in conv if mode == 'treat' for o in opts
            for xg, part in ((f'pmg_pmr_x_{short(bk)}_{o.j}', ' (tens)' if SHARE_DIGITS else ''), (f'pmg_pmr_xu_{short(bk)}_{o.j}', ' (units)'))
            if SHARE_DIGITS or 'xu' not in xg)))
    report['options'] = [{'building': bk, 'group': g, 'mode': mode, 'none': none,
                          'options': [{'j': o.j, 'key': o.key, 'role': o.role, 'goods': o.goods, 'electricity': o.elec}
                                      for o in opts]}
                         for bk, conv in options.items() for g, gi, mode, none, opts, std in conv]

    # ---- the AI's lock (frames.LOCK_PURE): before any effect is built, as the effects ask the gates ----
    lock_report = frame_lock(treated, options, groups, pm_groups, pms, frame_adds)
    for key, add in frame_adds.items():
        if key not in lock_report['locked']:
            upm = pdx.get(pms[key][0].value, 'unlocking_production_methods')
            pms[key][1].inserts.append((upm.end - 1, ''.join(f'\t{pk}  # PMR: a frame of a recipe it names\n\t' for pk in add)))
    report['frame_lock'] = {'on': frames.LOCK_PURE, 'locked': len(lock_report['locked']),
                            'open': lock_report['open']}

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
    # SUPPLY_BLEND (Pat 2026-11-11 22:12Z "Follow supply"): those ladders step through blends of their two newest methods
    supply_pms, supply_loc = supply_blends(game, auto, pms, group_src)
    report['supply_blend'] = [{'building': bk, 'group': g, 'ladder': i['ladder'], 'adds': {str(k): v for k, v in i['adds'].items()}}
                              for (bk, g), i in BLEND_INFO.items()]
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
        for old, new in OBS_PART_HOOKS.get(rel, []) if OBS_PARTS_ON else []:
            if text.count(old) != 1:
                raise SystemExit(f'{rel}: a part of the monthly script moved; update OBS_PART_HOOKS')
            text = text.replace(old, new)
        for n, part in enumerate(split_file(text, rel), 1):
            path = os.path.join(args.out, rel if n == 1 else rel[:-len('.txt')] + f'_{n}.txt')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if bom and not part.startswith('\ufeff'):
                part = '\ufeff' + part
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(part)

    header = ('# GENERATED by tools/pmr/generate.py from the installed game. Do not edit by hand; regenerate.\n'
              f'# N = {N} retool levels per level, retool share = {RETOOL_SHARE}.\n\n')

    # ---- new script ------------------------------------------------------------------------------
    retools, costs, loc = [], [], list(supply_loc)
    frames_of, frame_body_of, frame_pms = {}, {}, []   # the method-count rework (frames.py)
    frame_extras = {}   # building -> {target p: the job versions of its union frame beyond the plain key}
    less_all = (set(), set(), set())                     # goods in, goods out, pop types the "less" modifiers scale
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
    start_shares = {}      # history_start_shares: none since the method-count rework (history names the pure frames)

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
            custom_new.append(f'\ttext = {{\n\t\ttrigger = {{ is_building_type = {bk} state = {{ has_variable = pmr_to_{b} var:pmr_to_{b} = {i} }} }}\n'
                              f'\t\tlocalization_key = {r.key}\n\t}}\n')
        # Method-count rework: no labour or start group any more. The gold icon (pmr_labour_<b>.dds) stays: the building
        # browser draws it in the method grid's place (patch_grid_instance).

        rc = pdx.get(bn.value, 'required_construction')
        base_cost = cost_values.get(rc.value) if rc else None
        if base_cost is None and rc is not None:
            base_cost = num(rc.value, f'{bk}.required_construction')
        if base_cost is None:
            raise SystemExit(f'{bk}: no required_construction')
        retool_cost = base_cost * RETOOL_SHARE / N
        RETOOL_COST[b] = retool_cost
        costs.append(f'pmr_retool_cost_{b} = {fmt(retool_cost)}  # {rc.value} = {fmt(base_cost)} x {RETOOL_SHARE} / {N}')
        icon = pdx.get(bn.value, 'icon').value
        retools.append(retool_buildings(b, bk, icon))
        site_types += priv_slots(b) + [f'building_pmr_retool_gov_{b}', f'building_pmr_retool_gova_{b}']
        triggers.append(retool_triggers(b, bk))
        costs.append(retool_values(b))

        for rbx in priv_slots(b):
            loc += [f' {rbx}:0 "Retool: ${bk}$"',
                    f' {rbx}_desc:0 "Switches one level of ${bk}$ to its newest [concept_production_method]."']
        for r in recipes:
            if isinstance(r, (ElectricRecipe, PairRecipe)):
                loc.append(f' {r.key}:0 "' + ' + '.join(f'${x.key}$' for x in [r.base] + r.autos) + '"')
        loc += [f' building_pmr_retool_gov_{b}:0 "Retool: ${bk}$"',
                f' building_pmr_retool_gov_{b}_desc:0 "Switches the government\'s levels of ${bk}$ to the new [concept_production_method]."',
                f' building_pmr_retool_gova_{b}:0 "Retool: ${bk}$"',
                f' building_pmr_retool_gova_{b}_desc:0 "Switches your government\'s levels of ${bk}$ here to the new [concept_production_method]."']

        # Blended recipe: per recipe i, a tens and a units group whose two running digits carry recipe i's
        # workforce-scaled modifiers x n / SHARE_STEPS, so the building's goods are the level-weighted
        # mix of its recipes, scaled by workforce and throughput like any recipe. A digit unlocks only while
        # it runs itself, so only the running digit of each group is ever available and the AI cannot move a
        # share. When the game finds a method unavailable (its repair pass, repeated until nothing changes)
        # it keeps the current one if available, else the default, else the first available. 16 August
        # 1838: mutual share/lock pairs with _any last swapped without end and froze the game. A digit
        # depends on nothing but itself, so nothing loops.
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
        TARGET_OUTPUTS[bk] = []
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
                if sp:   # the recipe as the marker of (recipe, first option): that option's methods run with it
                    autos = [m for m in sp['options'][0] if m.blend or m.employment]
                else:
                    autos = automation.get(bk, []) if i >= AUTOMATION_FROM_TIER else []
                blend, emp, elec, clamped = effective(r, autos)
            fold_techs[i] = [] if sp else list(dict.fromkeys(t for a in autos for t in a.unlock_techs))
            econ.append(recipe_econ(blend, emp, weight))
            TARGET_EMPLOYEES[bk].append(sum(emp.values()) + other_emp)
            TARGET_OUTPUTS[bk].append([g for g, q in econ[-1][0].items() if q > 0 and goods_cost.get(g)])
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
                rest = {} if grp == 'recipe' else {k2: d for k2, d in m.rest.items() if d}   # a recipe keeps its own
                members.append((j, m, blend, emp, rest, SHARE_STEPS if j == 1 else 0,
                                {'member': j, 'kind': grp, 'pairs': idxs}))
        else:
            members = [(i, r, blend, emp, {}, SHARE_STEPS if i == 1 else 0,
                        {'tier': i, 'automation': [a.key for a in autos], 'needs_electricity': elec})
                       for i, (r, autos, blend, emp, elec) in enumerate(tiers_of, 1)]
        def ladder(sh, values, default_v, body_of, tex, loc_share, gname):
            """share methods <sh>_<v> carrying v% (body_of(v / SHARE_STEPS)); each unlocks only while it runs, the
            default at all times, so a new building's group is never empty (the start group went with the method-count
            rework: it unlocked the defaults)"""
            shares = []
            for val in values:
                dflt = '\tis_default = yes\n' if val == default_v else ''
                lock = '' if val == default_v else f'\tunlocking_production_methods = {{ {sh}_{val} }}\n'
                blend_pms.append(f'{sh}_{val} = {{\n\ttexture = "{tex}"\n{dflt}{lock}'
                                 f'{body_of(val / SHARE_STEPS) if val else ""}}}\n')
                shares.append(f'{sh}_{val}')
                loc.append(f' {sh}_{val}:0 "{loc_share(val)}"')
            g, gl = gname
            blend_groups.append(f'{g} = {{\n\ttexture = "{GENERIC_ICON}"\n'
                                '\tproduction_methods = {\n' + ''.join(f'\t\t{x}\n' for x in shares) + '\t}\n}\n')
            loc.append(f' {g}:0 "{gl}"')

        # Method-count rework (Pat 2026-11-10, frames.py): the blend members as frames.Member, each its modifiers at
        # 100%. A target's pure frame carries its members' and its base recipe's own (Recipe.rest); its union frame the
        # most any combination uses. The blend itself is "less" modifiers sized by pmr_frame_<b>.
        fm, own = [], {}
        for i, r, blend, emp, rest, default_n, rep in members:
            mods = {(sec, 'workforce_scaled'): dict(d) for sec, d in blend.items()}
            if emp:
                mods[('building_modifiers', 'level_scaled')] = dict(emp)
            fm.append(frames.Member(i, r.key, rep.get('kind', 'recipe'), rep.get('pairs', [rep.get('tier')]),
                                    frames.add_mods(mods, rest)))
            report['blended'].append({'building': bk, 'recipe': r.key, **rep, 'blend': blend, 'employment': emp,
                                      **({'other': {f'{sec}.{sub}': mods for (sec, sub), mods in rest.items()}} if rest else {})})
        for r in recipes:
            base = r.base if isinstance(r, PairRecipe) else r
            own[r.key] = {k2: dict(d) for k2, d in base.rest.items() if d}
        # Trade-offs: an option frame group each (vanilla's bodies); treatment: share methods as before, "live" amounts
        # for the frames (frames.Live).
        ogs, live, tex_of = [], [], {r.key: r.texture for r in recipes}
        for g, gi, mode, none, opts, std in options.get(bk, []):
            if mode == 'market':
                nopt = Option(bk, 0, g, gi, mode, None, none, pms)
                tex_of[none] = nopt.texture
                ogs.append(frames.OptionGroup(g, gi, none, nopt.mods, [
                    frames.Option(o.j, o.key, frames.sub_mods(Option(bk, o.j, g, gi, mode, o.role, o.key, pms).mods, nopt.mods))
                    for o in opts]))
                continue
            for o in opts:
                live.append(frames.Live(o.j, o.mods))
                for sh, values, dv, _part in share_digits(f'pm_pmr_x_{b}_{o.j}', 0, opt_step(o)):
                    gs = sh.replace('pm_', 'pmg_', 1)
                    ladder(sh, values, dv, o.share_body, o.texture,
                           lambda val, o=o: f'${o.key}$ ({val}% of the workforce)', (gs, f'${o.key}$ share'))
        fb = frames.Building(bk, g0, [r.key for r in recipes], fm, ogs, own, live, first=groups[g0][0])
        frames_of[bk] = fb
        FRAMES[bk] = fb
        for p, r in enumerate(recipes, 1):
            body = frames.sections(frames.pure_mods(fb, p))
            if r.key in frame_body_of:
                if frame_body_of[r.key] != body:
                    raise SystemExit(f'{r.key}: a recipe two buildings share, with different frames; extend the rework')
                continue
            frame_body_of[r.key] = body
            if not isinstance(r, PairRecipe):
                r.frame_body(body)
        frame_pms.extend(frames.union_methods(fb, lambda key: tex_of[key]).values())
        loc += frames.frame_loc(fb)
        # The unions' job versions (frames.union_versions, option_versions; no modifier moves a building's jobs, so the
        # frames carry them): listed wherever the plain union is, after it: the recipe group, the lists of the methods
        # that name the target's recipe (a method the AI's lock locked asks through its gate instead: widen_gates),
        # each trade-off group, and vanilla_compat's aliases (frame_extras).
        xr, xo = frames.extra_union_keys(fb)
        frame_extras[bk] = xr
        frames.widen_gates(fb)
        gsrc, gpm = group_src[g0]
        if any(xr.values()):
            gsrc.inserts.append((gpm.end - 1, ''.join(f'\t{k}  # PMR: union frame of {r.key}, a job version\n\t'
                                                      for p, r in enumerate(recipes, 1) for k in xr[p])))
        for p, r in enumerate(recipes, 1):
            base = r.base.key if isinstance(r, PairRecipe) else r.key
            for key in unlock_users.get(base, []) if xr[p] else []:
                if key not in lock_report['locked']:
                    upm = pdx.get(pms[key][0].value, 'unlocking_production_methods')
                    pms[key][1].inserts.append((upm.end - 1, ''.join(f'\t{k}  # PMR: a frame of a recipe it names\n\t'
                                                                     for k in xr[p])))
        for g, ks in xo.items():
            if ks:
                gsrc, gpm = group_src[g]
                gsrc.inserts.append((gpm.end - 1, ''.join(f'\t{k}  # PMR: union frame, a job version\n\t' for k in ks)))
        for side, names in zip(less_all, frames.frame_goods(fb)):
            side.update(names)

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
                            + frames.frame_effect(fb, log=not RELEASE, count=not RELEASE)
                            + tick_effect(bk, b, recipes, elec_tiers, options.get(bk, []), fold_techs,
                                          econ, goods_cost, [t for _, _, t in auto_tiers], pair_ui.get(bk),
                                          '' if RELEASE else frames.short_check(fb)))
        recipe_elec[bk] = elec_tiers
        dispatch.append(bk)
        report['treated'].append({'building': bk, 'recipe_group': g0, 'recipes': [r.key for r in recipes],
                                  'icon_good': good,
                                  'electric_tiers': elec_tiers,
                                  'retool_cost': retool_cost})

    # ---- the vanilla files PMR changes, now that the frames have their bodies ----------------------
    regrouped = 0
    for s in {id(t[2]): t[2] for t in treated}.values():
        text = s.render()
        if args.group_probe:
            text, hits = group_probe.regroup(s.name, text)
            regrouped += hits
        write(f'common/buildings/{s.name}', text)
    if args.group_probe and regrouped != 1:
        raise SystemExit(f'group probe: {group_probe.BUILDING} regrouped {regrouped} times, not once')
    for s in p_srcs:
        if s.cuts or s.inserts:
            write(f'common/production_methods/{s.name}', s.render())
    # Vanilla groups that gain frames or lose a principle variant (DROP_RECIPES), whole, with only those lines changed.
    for s in g_srcs:
        if s.inserts or s.cuts:
            write(f'common/production_method_groups/{s.name}', s.render())
    if elec_pms:
        raise SystemExit('electric recipes (no SPLIT_AUTOMATION) have no frames yet; extend the method-count rework')
    if pair_pms:
        write('common/production_methods/pmr_pair_production_methods.txt', header
              + '# Recipe + automation pairs (PairRecipe, SPLIT_AUTOMATION): pure frames of their retool targets.\n\n'
              + '\n'.join(r.method(frame_body_of[r.key]) for r in pair_pms))
    write('common/production_methods/pmr_frame_production_methods.txt', header + frames.FRAME_DOC + '\n'.join(frame_pms))
    if supply_pms:
        write('common/production_methods/pmr_supply_blend_production_methods.txt', header
              + '# SUPPLY_BLEND (tools/pmr/generate.py): pm_pmr_blend_<b>_<i>_<k> is k tenths of ladder method i over method\n'
              + '# i-1, every modifier weighted so. Each unlocks only while it runs itself; pmr_blend_<b> sets them.\n\n'
              + supply_pms)
    if not RELEASE:
        # the JOBS line: a blended building's jobs as the game reads them back, against its frame's
        for path, text in frames.jobs_check_files(frames_of.values()):
            write(path, header + text)
    write('common/static_modifiers/pmr_less_modifiers.txt', header + frames.LESS_DOC + frames.static_modifiers(*less_all))
    # the goods and job multipliers the engine knows only by pattern: vanilla declares some, Company Culture its own
    declared = company_culture.vanilla_modifier_types(game) | set(company_culture.goods_mults(cc_plan))
    less_types = frames.type_keys(*less_all, declared)
    if args.frame_probe:
        # the jobs probe's own types, which the frames declare only with frames.JOB_LESS
        less_types += [t for t in sorted({t for t, _ in frame_probe.MODS.values()})
                       if t not in declared and t not in less_types]
    write('common/modifier_type_definitions/pmr_less_modifier_types.txt', header + frames.TYPES_DOC
          + frames.modifier_types(less_types))
    add_names, named = set(), set()
    for path in glob.glob(os.path.join(game, 'localization', 'english', '*.yml')):
        text = open(path, encoding='utf-8-sig').read()
        add_names |= set(re.findall(r'^ (goods_\w+_add):', text, re.M))
        # vanilla names every building_employment_<pop>_mult although it declares none
        named |= set(re.findall(r'^ ((?:goods|building_employment)_\w+_mult):', text, re.M))
    loc += frames.static_modifier_loc(*less_all) + frames.modifier_type_loc(less_types, add_names, named)
    if args.frame_probe:
        probe_files, probe_loc = frame_probe.files(declared | set(less_types))
        for path, text in probe_files:
            write(path, header + text)
        loc += probe_loc
    if args.group_probe:
        probe_files, probe_loc = group_probe.files()
        for path, text in probe_files:
            write(path, header + text)
        loc += probe_loc
    report['frames'] = {'less_in': sorted(less_all[0]), 'less_out': sorted(less_all[1]), 'less_jobs': sorted(less_all[2]),
                        'types_added': less_types, 'unions': len(frame_pms),
                        'job_versions': sum(len(ks) for xr in frame_extras.values() for ks in xr.values())}

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
                # Pat, 2026-10-19 01:21Z (Krupp making Krupp Guns with no Hallmark Goods): every company's prestige
                # goods wait for Company Culture's Hallmark Goods. The 66 vanilla lets make them whenever prosperous
                # get a trigger; the rest already wait for the variable the node sets.
                if (cc_plan and pdx.get(cn.value, 'possible_prestige_goods')
                        and not pdx.get(cn.value, 'prestige_goods_trigger')):
                    csrc.inserts.append((cn.end - 1, '\tprestige_goods_trigger = { custom_tooltip = { '
                                                     'text = PMR_CC_PG_REQ has_variable = pmr_cc_hallmark } }  # PMR\n'))
                    report.setdefault('hallmark_gate', []).append(ck)
                bt = pdx.get(cn.value, 'building_types')
                if not bt or not bt.is_block:
                    continue
                listed = pdx.items(bt)
                ext = pdx.get(cn.value, 'extension_building_types')
                # Pat 2026-10-19 15:40Z: with subsidiaries the retooling of an industry the company doesn't
                # list belongs to the subsidiary that lists it (subsidiaries.RETOOL_OF), not to the parent
                extra = [] if cc_plan else [x for x in (pdx.items(ext) if ext and ext.is_block else []) if x not in listed]
                new = [(x, rbx) for x in listed + extra if x in retool_of for rbx in retool_of[x] if rbx not in listed]
                if not new:
                    continue
                csrc.inserts.append((bt.end - 1, ''.join(f'\t{rbx}  # PMR: retooling of {x}'
                                                          + (' (additional industry)' if x in extra else '') + '\n\t'
                                                          for x, rbx in new)))
                report['company_types'].append({'company': ck, 'file': csrc.name, 'added': [rbx for _, rbx in new]})
            if csrc.inserts:
                write(f'common/company_types/{csrc.name}', csrc.render())
        # Pat 2026-10-19 18:45Z ("why is this still active as a je?", the Hudson's Bay Company's Select Fish): Hallmark
        # Goods gives a company its prestige goods, so vanilla's prestige goods journal entries never start, and one
        # already running is dropped (invalid).
        if cc_plan:
            je = load_dir(game, 'journal_entries', only={PRESTIGE_JE_FILE})
            if not je:
                raise SystemExit(f'common/journal_entries/{PRESTIGE_JE_FILE} is missing from the game copy')
            for jsrc in je:
                for jk, jn in jsrc.objects().items():
                    if not jk.startswith('je_prestige_goods_'):
                        continue
                    for key in ('is_shown_when_inactive', 'possible'):
                        kn = pdx.get(jn.value, key)
                        if kn:
                            jsrc.cuts.append(line_span(jsrc.text, kn))
                    # 1.15 folds complete/fail/invalid into outcome blocks, at most one of them invalid_outcome
                    # (hidden, silent): it takes the place of any vanilla one.
                    for on in pdx.get_all(jn.value, 'outcome'):
                        fl = pdx.get(on.value, 'flags')
                        if fl and any(c.key is None and c.value == 'invalid_outcome' for c in fl.value):
                            jsrc.cuts.append(line_span(jsrc.text, on))
                    jsrc.inserts.append((jn.end - 1, '\tis_shown_when_inactive = { always = no }  # PMR\n'
                                                     '\tpossible = { always = no }  # PMR\n'
                                                     '\toutcome = {  # PMR: Hallmark Goods gives prestige goods\n'
                                                     '\t\tflags = { hidden invalid_outcome }\n'
                                                     '\t\tconclusion_desc = je_standard_failure_conclusion_desc\n'
                                                     '\t\ttrigger = { always = yes }\n\t}\n'))
                    report.setdefault('prestige_je_off', []).append(jk)
                write(f'common/journal_entries/{jsrc.name}', jsrc.render())
    # Pat 2026-10-20 03:35Z ("can we patch that so it doesn't hurt our performance"): vanilla's default AI strategy
    # compares a state to s:STATE_HAWAII, a region that doesn't exist (STATE_HAWAIIAN_ISLANDS, as vanilla's own
    # 00_scripted_triggers.txt has it), so every evaluation in a game with the Hawaiian Interest journal entry writes a
    # script error (q51: about 86 a second by 1868). The file is copied with the name corrected.
    for rel, old_s, new_s in VANILLA_FIXES:
        path = os.path.join(game, rel)
        if not os.path.exists(path):
            raise SystemExit(f'{rel} is missing from the game copy')
        text = open(path, encoding='utf-8-sig').read()
        if text.count(old_s) != 1:
            raise SystemExit(f'{rel}: {old_s.strip()!r} found {text.count(old_s)} times; check the vanilla fix')
        write(rel, text.replace(old_s, new_s))
        report.setdefault('vanilla_fixes', []).append(rel)
    write(MOBILIZATION_FILE, header + ungate_mobilization(open(os.path.join(game, MOBILIZATION_SOURCE), encoding='utf-8-sig').read()))
    # the panels listing a company's industries hide them (Pat 2026-10-19 02:32Z, company_panel.py)
    company_panel.RETOOL_TYPES = sorted({rbx for c in report['company_types'] for rbx in c['added']})
    if COMPANY_RETOOL and cc_plan:   # each subsidiary type lists the retooling of its industries (subsidiaries.py)
        subsidiaries.RETOOL_OF = {b: retool_of[b] for b in cc_plan.sb_types if b in retool_of}
        company_panel.RETOOL_TYPES = sorted(set(company_panel.RETOOL_TYPES)
                                            | {r for rs in subsidiaries.RETOOL_OF.values() for r in rs})

    write('common/buildings/pmr_retool_buildings.txt', header + '\n'.join(retools))
    # Written even while RETOOL_CREW is 0 (nothing uses them then), so a deployed folder never keeps a stale copy.
    write('common/production_methods/pmr_retool_production_methods.txt', header + RETOOL_CREW_DOC +
          'pm_pmr_retool_crew = {\n'
          f'\ttexture = "{RETOOL_CREW_ICON}"\n'
          '\tbuilding_modifiers = {\n\t\tworkforce_scaled = {\n'
          f'\t\t\tgoods_output_{RETOOL_CREW_GOOD}_add = {RETOOL_CREW_OUTPUT}\n'
          '\t\t}\n\t\tlevel_scaled = {\n'
          f'\t\t\tbuilding_employment_{RETOOL_CREW_POP}_add = {RETOOL_CREW}\n'
          '\t\t}\n\t}\n}\n\n'
          'pm_pmr_retool = {\n'
          f'\ttexture = "{RETOOL_CREW_ICON}"\n'
          '\tis_default = yes\n}\n')
    write('common/production_method_groups/pmr_retool_groups.txt', header +
          'pmg_pmr_retool_crew = {\n'
          f'\ttexture = "{RETOOL_CREW_ICON}"\n'
          '\tproduction_methods = {\n\t\tpm_pmr_retool_crew\n\t}\n}\n\n'
          '# A retool site with no crew (the government\'s): one method with no effects, named, where vanilla\'s\n'
          '# pmg_dummy showed "Should never be shown in UI" and a placeholder icon in the building panel (q105).\n'
          'pmg_pmr_retool = {\n'
          f'\ttexture = "{RETOOL_CREW_ICON}"\n'
          '\tproduction_methods = {\n\t\tpm_pmr_retool\n\t}\n}\n')
    loc += [' pmg_pmr_retool_crew:0 "Crew"', ' pm_pmr_retool_crew:0 "Retooling Crew"',
            ' pmg_pmr_retool:0 "Retooling"', ' pm_pmr_retool:0 "Retooling"']
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
    write('common/scripted_triggers/pmr_triggers.txt', header + RETOOL_TRIGGERS_DOC + '\n'.join(triggers)
          + '\n' + LOGGED_TRIGGER + '\n' + VIEWER_TRIGGER)
    write('common/script_values/pmr_values.txt', header +
          f'pmr_retool_levels_per_level = {N}\n\n' + '\n'.join(costs) + '\n')
    write('common/production_methods/pmr_blend_production_methods.txt', header +
          '# Treatment share methods: pm_pmr_x_<b>_<option>_<n> carries the treatment\'s modifiers\n'
          + (f'# x n / {SHARE_STEPS}, n = 0, 10 .. 100; pm_pmr_xu_<b>_<option>_<u> its units, u = 0..9. Each\n'
             if SHARE_DIGITS else f'# x n / {SHARE_STEPS}, n = 0 .. {SHARE_STEPS}. Each but 0\n')
          + '# unlocks only while it runs itself; the tick sets them with activate_production_method.\n\n'
          + '\n'.join(blend_pms))
    write('common/production_method_groups/pmr_blend_groups.txt', header + '\n'.join(blend_groups))
    # q95: every good the profit pick or a trade-off prices, a traded one from its market's order book (market_read)
    price_goods = sorted(profit_goods | set(option_goods(options)))
    traded = sorted(set(price_goods) | set(demand_goods(options)))   # q96: local goods from their market's orders too
    spare = set(budget_goods(options))
    check_price_defines(game)
    write('common/script_values/pmr_market_values.txt', header + market_values(traded, sorted(spare))
          + (blend_fill_values() if BLEND_INFO else ''))
    write('common/scripted_effects/pmr_effects.txt', header + shared_effects(price_goods)
          + ''.join(market_read(g, g in spare) for g in traded) + '\n'.join(tick_effects)
          + dispatch_effects(dispatch) + '\n' + auto_best_effects(auto)
          + (research_map_effects(dispatch, auto) if RESEARCH_MAP else '') + own_effects()
          + (QUIET_COUNT if QUIET_TICK and not RELEASE else ''))
    hist_text, hist_n = history_frames(game)
    if hist_n:
        write('common/scripted_effects/pmr_history_effects.txt', header + hist_text)
    report['frame_lock']['history'] = hist_n
    on_actions = ON_ACTIONS.replace('STATE_TURN', state_turn())
    if RESEARCH_MAP or PF_SUMS:
        old = 'OBS_ON_ACTION\n'
        if on_actions.count(old) != 1:
            raise SystemExit('on_actions: OBS_ON_ACTION not found once')
        on_actions = on_actions.replace(old, 'on_state_owner_change = { on_actions = { pmr_on_state_owner_change } }\n' + old)
        on_actions += ('\n# Root = state, under its new owner (vanilla\'s own effects there read owner so). RESEARCH_MAP, PF_SUMS.\n'
                       'pmr_on_state_owner_change = {\n\teffect = {\n\t\tpmr_own_check = yes\n\t}\n}\n')
    if RESEARCH_MAP:
        for old, new in RESEARCH_MAP_HOOKS:
            if on_actions.count(old) != 1:
                raise SystemExit(f'RESEARCH_MAP: on_actions hook not found once: {old!r}')
            on_actions = on_actions.replace(old, new)
    if args.script_profile:
        if on_actions.count(PULSE_STATE_HOOK) != 1 or on_actions.count(pulse_state_effect()) != 1:
            raise SystemExit('pmr_on_monthly_pulse_state changed; update pulse_state_effect and profile_pulse_state')
        on_actions = on_actions.replace(PULSE_STATE_HOOK, profile_pulse_state(dispatch))
    write('common/on_actions/pmr_on_actions.txt', header + on_actions.replace('TECH_CRUMB', flush_log('TECH', '-'))
          .replace('SKIP_REPORT\n', '' if RELEASE else '\t\tpmr_skip_report = yes   # S3: the month\'s SKIP line (test builds)\n'
                   + ('\t\tpmr_dv_report = yes   # VALUE_READS 1: the month\'s DV line\n' if VALUE_READS == 1 else '')
                   + ('\t\tpmr_qt_report = yes   # QUIET_TICK: the month\'s QUIET line\n' if QUIET_TICK else '')
                   + ('\t\tpmr_rm_report = yes   # RESEARCH_MAP: the month\'s RMAP line\n' if RESEARCH_MAP else ''))
          .replace('OBS_ON_ACTION\n', '' if RELEASE else 'on_monthly_pulse_country = { on_actions = { pmr_obs_monthly_country } }\n'
                   + ('on_monthly_pulse_state = { on_actions = { pmr_obs_monthly_state } }\n' if OBS_PAD else ''))
          .replace('BUILD_ON_ACTION\n', 'on_monthly_pulse_country = { on_actions = { pmr_build_monthly_country } }\n' if BUILD else '')
          .replace('BUILD_STAMP', '\t\tpmr_build_stamp = yes\n' if BUILD else '')
          .replace('PMC_ON', '' if RELEASE else '\t\t\tstate = { set_variable = { name = pmr_pmc days = 1 } }   # pmr_count_undo\n')
          .replace('PMC_OFF', '' if RELEASE else '\t\t\tstate = { remove_variable = pmr_pmc }\n')
          .replace('START_STAFF', '' if RELEASE else START_STAFF)
          .replace('HISTORY_FRAMES', "\t\tpmr_history_frames = yes   # the AI's lock: history's locked frames, before the first tick adopts what runs\n"
                   if hist_n else '')
          .replace('START_LEFT', '' if RELEASE else START_LEFT)
          + ('' if RELEASE else OBS_ON_ACTIONS.replace(OBS_PAD_HOOK[0], OBS_PAD_HOOK[1]) + OBS_PAD_ON_ACTIONS if OBS_PAD else
             OBS_ON_ACTIONS) + (BUILD_ON_ACTIONS if BUILD else ''))
    if not RELEASE:
        write('common/scripted_effects/pmr_obs_effects.txt', header + obs_report(dispatch) + obs_methods(options, dispatch, split_info) + obs_ab()
              + obs_pad() + OBS_ARMY + obs_budget()[0] + build_stamp())
        write('common/script_values/pmr_obs_values.txt', header + OBS_ARMY_VALUES + obs_budget()[1])
    for rel, text in history_start_shares(args.game, start_shares).items():
        # vanilla's own text with names added: no header, so the game's line numbers still match vanilla's
        path = os.path.join(args.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\ufeff' + text)
    write('events/pmr_events.txt', header + EVENTS)
    write('events/pmr_error_suppression_events.txt', header + ERROR_SUPPRESSION_EVENTS)
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
                                                             drop_base, split_info, frame_extras)
    write(COMPAT_TRIGGERS, header + compat_trig)
    for rel, text in compat_files.items():
        write(rel, text)
    report['vanilla_compat'] = compat_lines
    write('common/scripted_guis/pmr_sguis.txt', header + SGUI_DOC + ''.join(gov_retool_sgui(bk) for bk in dispatch)
          + '# The same for every state at once, from the Buildings tab\'s building type row. Country scope.\n\n'
          + ''.join(gov_retool_country_sgui(bk) for bk in dispatch)
          + '# Every building type at once, from the Buildings panel. Country scope.\n\n' + gov_retool_all_sgui(list(dispatch))
          + ('# The Buildings panel, as it opens (patch_browser_tabs): its country\'s Buildings tab totals, buildings abroad\n'
             '# included, the first time, and monthly after (pmr_c_viewer). Pat 2026-10-20 03:43Z: an observer game taken\n'
             '# over as Great Britain showed no bar for its plantations in the East India Company\'s states, and logged no\n'
             '# CSUM or TECH line, both is_player in country scope, on its research.\n'
             'pmr_c_view_sgui = {\n\tscope = country\n\teffect = {\n'
             '\t\tif = {\n\t\t\tlimit = { NOT = { has_variable = pmr_c_view } }\n\t\t\tset_variable = pmr_c_view\n'
             '\t\t\tpmr_c_sum_every = yes\n'
             '\t\t\tdebug_log = "PMR;rec=CVIEW;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting]"\n'
             '\t\t}\n\t}\n}\n\n')
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
    # the details panel's switching bars show what they fill toward (switch_targets, Pat 2026-10-19 02:32Z)
    SWITCH_ICONS.update((bk, switch_targets(bk, recipe_tex[bk], pair_ui.get(bk), len(keys))) for bk, keys in pick_ui.items())
    mv_keys = pick_ui   # the Private tab's Methods view covers the same types
    ai_of = private_investment.ai_groups(game) if mv_keys else {}   # each row's AI weight (Pat 18:40Z)
    # the policy parts of each AI weight, for its tooltip's nested Policy line (Pat 2026-10-19 00:01Z)
    if args.test_decisions:    # the test probes' companies buy levels like any other (Pat 2026-10-19 14:10Z)
        private_investment.EXTRA_COMPANY_DIRS[:] = [
            d for d in (os.path.join(TEST_PROBES, p, 'common', 'company_types') for p in sorted(os.listdir(TEST_PROBES)))
            if os.path.isdir(d)] if os.path.isdir(TEST_PROBES) else []
    owners_of = private_investment.company_owners(game) if mv_keys else {}
    if owners_of and cc_plan:   # and the subsidiaries their bundles found (subsidiaries.py)
        for bk, types in subsidiaries.owners(cc_plan).items():
            owners_of.setdefault(bk, []).extend(types)
    # a company's Focus bylaw ends the weight (company_culture.ai_value_tail), shown as Companies
    ai_parts = {bk: private_investment.ai_parts(bk, owners_of, ai_of)
                + ([('works', None)] if cc_plan and bk in owners_of else []) for bk in ai_of}
    write('common/customizable_localization/pmr_custom_loc.txt', header +
          '# Building scope. The recipe a building runs, which is the one any retooling moves it to.\n'
          'pmr_new_recipe = {\n\ttype = building\n\tlog_loc_errors = no\n' + ''.join(custom_new) + '}\n'
          + '\n# State scope. A note after an option the state can\'t run (technology, laws, electricity), or is short of an\n'
          + '# input for (pmr_xsh).\n'
          + ''.join(f'pmr_xlk_{short(bk)}_{o.j} = {{\n\ttype = state\n\trandom_valid = no\n'
                    f'\ttext = {{\n\t\ttrigger = {{ var:pmr_xav_{o.j}_{short(bk)} ?= 0 }}\n'   # unset below level 1 (bug review q48, P3-1)
                    f'\t\tlocalization_key = {"PMR_OPT_BARRED" if mode == "treat" else "PMR_OPT_LOCKED"}\n\t}}\n'
                    + (f'\ttext = {{\n\t\ttrigger = {{ var:pmr_xsh_{o.j}_{short(bk)} ?= 1 }}\n'
                       '\t\tlocalization_key = PMR_OPT_SHORT\n\t}\n' if mode == 'market' and o.group not in DEMAND_GROUPS else '')
                    + '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n'
                    for bk, groups in opt_ui.items() for gi, mode, none, tex, os_ in groups for o in os_)
          + '\n# State and country scope. The names on the switching bars\' tooltips (pick_custom_loc).\n'
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
    TYPE_FLAGS[:] = [('pmr_t_', set(dispatch) | set(recipe_tex)), ('pmr_a_', set(also))]
    def vanilla_gui(name):
        return open(os.path.join(game, 'gui', name), encoding='utf-8-sig').read()
    write('gui/building_details_panel.gui', gate_type_copies(patch_building_panel(
        recipe_tex, vanilla_gui('building_details_panel.gui'), opt_ui, also, auto_ui, pick_ui,
        vanilla_gui('modifiers_panel.gui'), less_all[:2])), bom=False)
    # The same icon row in the building tooltip and the map list (hide_less_icons): two more vanilla files carried
    # whole, each with one line added.
    for name in LESS_ICON_FILES:
        write(f'gui/{name}', hide_less_icons(vanilla_gui(name), name), bom=False)
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
    menu_gui, browser_gui = hide_sites_elsewhere(vanilla_gui('build_urban_buildings_menu.gui'),
                                                 vanilla_gui('building_browser_panel.gui'), site_types)
    write('gui/build_urban_buildings_menu.gui', menu_gui, bom=False)
    write('gui/building_browser_panel.gui', gate_type_copies(patch_browser_tabs(patch_browser_retool_all(patch_browser_actions(patch_grid_instance(
        patch_type_grids(browser_gui, dispatch, 'building_browser_panel.gui', 1, also=also),
        dispatch, '\t\t\t', 'building_browser_panel.gui', outer=(214, 50), cell=50, anchor='vcenter',
        extra=browser_bars, also=also), dispatch)), list(mv_keys))), bom=False)
    # No reset to the national standard: right-click items and the map action (Pat 2026-10-20 21:40Z).
    rcm_gui, lens_gui = hide_pm_reset(vanilla_gui('right_click_menu.gui'), vanilla_gui('lens_toolbar.gui'))
    write('gui/right_click_menu.gui', rcm_gui, bom=False)
    write('gui/lens_toolbar.gui', lens_gui, bom=False)
    # The state's Buildings tab without the retool sites (Pat 2026-10-14 01:54Z).
    write('gui/states_panel_buildings.gui',
          urban_list_gui(hide_retool_sites(vanilla_gui('states_panel_buildings.gui'), site_types)), bom=False)
    urb_trig, urb_value, urb_eff = urban_list_script(urban_types(game, report))
    write('common/scripted_triggers/pmr_urb_triggers.txt', header + urb_trig)
    write('common/script_values/pmr_urb_values.txt', header + urb_value)
    write('common/scripted_effects/pmr_urb_effects.txt', header + urb_eff)
    # The company panels without the retool sites that companies list (Pat 2026-10-19 02:32Z, company_panel.py);
    # company_culture.write_all writes company_panel.gui, with its Company Culture tab.
    company_panel.SUB_LINKS = args.test_decisions   # the Regional HQs subsidiary probe (pmr/test_probes/sub_hq)
    write('gui/companies_panel.gui', company_panel.patch_companies_panel(vanilla_gui('companies_panel.gui')), bom=False)
    report['gated_type_copies'] = list(GATED)
    write('gui/goods_state_panel.gui', patch_building_grids(vanilla_gui('goods_state_panel.gui'), dispatch,
                                                            'goods_state_panel.gui', 1, also), bom=False)
    loc += panel_loc(bar_keys) + option_loc(opt_ui) + automation_loc(auto_ui) + pick_loc(pick_ui) + methods_view_loc(mv_keys, pair_ui, ai_of, ai_parts, opt_ui, auto_ui)
    loc += [' PMR_GOV_RETOOL_ALL:0 "Retool Government Levels"'] + GOV_ALL_LOC
    # Interface review 2026-11-11 (gui-review/SPEC.md P2, Pat's "All three" at 19:30Z): one game concept, the one place
    # the mechanic is explained, linked from the bar tooltips' "To retool" and the retool buttons' header only.
    write('common/game_concepts/pmr_concepts.txt', f'concept_pmr_retooling = {{\n\ttexture = "{GOV_RETOOL_ICON}"\n}}\n')
    share = 'half' if RETOOL_SHARE == 0.5 else f'{RETOOL_SHARE:.0%} of'
    loc += [' concept_pmr_retooling:0 "Retooling"',
            ' concept_pmr_retooling_desc:0 "Moves a [concept_building]\'s levels to a newer [concept_production_method].'
            f'\\nEach level costs {share} the building\'s [concept_construction] and is built through the [concept_construction_queue].'
            '\\n[concept_government_construction] retools the government\'s levels, [concept_private_construction] the rest."']
    loc += [' bg_pmr_retool:0 "Retooling"', ' bg_pmr_retool_abroad:0 "Retooling Abroad"',
            ' bg_pmr_retool_gov:0 "Government Retooling"', ' bg_pmr_retool_gov_abroad:0 "Government Retooling Abroad"']
    # the "PMR test:" decision is for testing only: every player would see it. Pat 2026-10-20 13:26Z: out of the test
    # build too ("closer to release I want these to be more similar"), unless asked for
    if args.test_decisions:
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
                                       mv_cols(mv_keys, pair_ui) if mv_keys else 1)
    # Company Culture (Pat, 2026-10-14 04:01Z): a trait tree tab on every company, shipped 2026-10-20 12:59Z.
    loc += company_culture.write_all(game, write, header, report, cc_plan, args.out)
    private_investment.GRANT_LINE = True   # subsidiary payments in the pool's tooltip (subsidiaries.py)
    private_investment.AI_TAIL = company_culture.ai_value_tail   # the Focus bylaw (company_culture.py)
    # The HUD: the retool site flags and Company Culture's full-screen window
    hud = vanilla_gui('ingame_hud.gui')
    if cc_plan:
        hud = cc_tree.patch_hud(hud)
    if args.script_profile:
        hud = patch_hud_profile(hud)
    if args.engine_timing:
        hud = patch_hud_timing(hud)
    write('gui/ingame_hud.gui', patch_hud_flags(patch_hud_gov_all(hud), site_types), bom=False)
    # The construction panel's Private tab (Pat, 2026-10-13). Runs last: it patches the building files and
    # pmr_retool_buildings.txt written above (company ai_value; the Re-invest card's retool multiplier).
    private_investment.PROFIT_TYPES = set(pick_ui)   # their ai_value follows their average profit (Pat 21:10Z)
    private_investment.PF_SUMS, private_investment.PF_SYNC = PF_SUMS, set(PF_SYNC)
    private_investment.PF_CHECK = PF_SUMS and not RELEASE
    private_investment.LEAN_CHARTS = LEAN_CHARTS
    loc += private_investment.write_all(game, write, header, args.out)
    if args.trace_from:
        write('common/scripted_effects/pmr_trace_effects.txt', header + trace_pm_effects(game, args.out, args.trace_from))
    write('localization/english/pmr_l_english.yml', 'l_english:\n' + '\n'.join(loc) + '\n')
    # Every other language, translated (Pat 2026-10-18 14:37Z, #3). A game set to a language shows raw keys where it
    # has no text, so a line its table lacks stays English, test builds included.
    report['untranslated'] = {}
    # The "less" modifiers keep their English name in every language: the GUI leaves them out by it (LESS_SHOWN).
    fixed = {line for line in loc if line.startswith(tuple(' ' + pre for pre in LESS_PREFIXES))
             and line.endswith(f':0 "{frames.LESS_NAME}"')}
    for lang in OTHER_LANGUAGES:
        missing = collections.Counter()
        write(f'localization/{lang}/pmr_l_{lang}.yml',
              f'l_{lang}:\n' + '\n'.join(line if line in fixed else out for line, out in
                                         zip(loc, localise.translate(loc, lang, missing))) + '\n')
        report['untranslated'][lang] = sorted(missing)
    # Vanilla text PMR rewrites, the same in every language (private_investment.replace_loc)
    replace = private_investment.replace_loc()
    for lang in ('english',) + OTHER_LANGUAGES if replace else ():
        write(f'localization/{lang}/replace/pmr_replace_l_{lang}.yml', f'l_{lang}:\n' + '\n'.join(replace) + '\n')

    # A test build for its own mod folder (--test-name) carries its own name and id, so the launcher lists it
    # beside the published mod and a playset holds one or the other.
    title = 'Production Method Rework' + (f' ({args.test_name})' if args.test_name else ' BETA' if args.beta else '')
    mod_id = 'org.prob32.pmr' + ('.' + re.sub(r'[^a-z0-9]+', '_', args.test_name.lower()) if args.test_name
                                 else '.beta' if args.beta else '')
    version = MOD_VERSION + ('-beta' if args.beta else '')
    # The Modding Co-op's Mod Template (Pat 2026-11-05 14:23Z, "Template layout only"): its metadata fields, and tags
    # from its list (the Workshop page's "Economy And Buildings"). The id stays org.prob32.pmr: launchers and playsets
    # already know the mod by it.
    write('descriptor.mod', f'version="{version}"\ntags={{\n\t"Gameplay"\n\t"Economy And Buildings"\n}}\n'
          f'name="{title}"\nsupported_version="{SUPPORTED_VERSION}"\n', bom=False)
    write('.metadata/metadata.json', json.dumps({
        'name': title, 'id': mod_id, 'version': version,
        'game_id': 'victoria3', 'picture': 'thumbnail.png', 'supported_game_version': SUPPORTED_VERSION,
        'short_description': SHORT_DESCRIPTION,
        'tags': ['Gameplay', 'Economy And Buildings'], 'relationships': [],
        'game_custom_data': {'multiplayer_synchronized': True}}, indent=2) + '\n', bom=False)
    report['loc_hash_renames'] = rename_hash_clashes(game, args.out, args.release)
    for old, new in report['loc_hash_renames'].items():
        print(f'renamed {old} to {new}: another localisation key has its hash')
    report['settings'] = {'N': N, 'retool_share': RETOOL_SHARE, 'gov_fraction_step': GOV_FRACTION_STEP,
                          'game': args.version_label}
    shutil.copyfile(THUMBNAIL, os.path.join(args.out, '.metadata', 'thumbnail.png'))
    shutil.copyfile(THUMBNAIL, os.path.join(args.out, 'thumbnail.png'))
    if not args.release:
        write('GENERATION_REPORT.json', json.dumps(report, indent=1) + '\n', bom=False)
    print(f"treated {len(report['treated'])} buildings, skipped {len(report['skipped'])}, "
          f"{len(report['blended'])} blend members, {len(frame_body_of) + len(frame_pms)} frames, "
          f"{len(blend_pms)} treatment share methods, "
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


def flush_log(rec, bk, extra='', mine=None):
    """State scope, every country: a line long enough to push itself and everything before it to disk.
    With mine (a trigger: the player's), only the player's lines are padded and the others are written plain:
    padded lines from every country rotated Pat's debug.log about once a minute of play (2026-10-19)."""
    line = (f'PMR;rec={rec};date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting];'
            f'building={bk}{extra}')
    if mine:
        return (f'if = {{ limit = {{ {mine} }} debug_log = "{line};pad={"." * FLUSH_PAD}" }} '
                f'else = {{ debug_log = "{line}" }}')
    return f'debug_log = "{line};pad={"." * FLUSH_PAD}"'


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
    'pmr_pi_start_clock': 'country', 'pmr_pc_record': 'country',
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
    pmr_l0_guard (building scope, below level 1) writes a flushed L0_TRIP line on the L0_TRIP-th method
    change in a day (it opened the share locks while there were any). 16 August 1838: the engine
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
            # a PMR type: a group of it holds a union frame (the method-count rework)
            if g and any(p.startswith('pm_pmr_union_') for x in pdx.items(g) for p in groups.get(x, [])):
                types[n.key] = pdx.items(g)
    logs, guards = [], []
    for i, (bk, gs) in enumerate(sorted(types.items())):
        kw = 'if' if i == 0 else 'else_if'
        logs.append(f'\t{kw} = {{\n\t\tlimit = {{ is_building_type = {bk} }}\n'
                    + ''.join(f'\t\tif = {{ limit = {{ has_active_production_method = {p} }} '
                              f'debug_log = "PMR;rec=PM;group={g};pm={p}" }}\n' for g in gs for p in groups[g])
                    + '\t}\n')
        b = short(bk)
        guards.append(f'\t{kw} = {{\n\t\tlimit = {{ is_building_type = {bk} }}\n\t\tstate = {{\n'
                      f'\t\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_l0_day_{b} }} }} '
                      f'set_variable = {{ name = pmr_l0_day_{b} value = yes days = 1 }} set_variable = {{ name = pmr_l0_runs_{b} value = 0 }} }}\n'
                      f'\t\t\tchange_variable = {{ name = pmr_l0_runs_{b} add = 1 }}\n'
                      f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:pmr_l0_runs_{b} = {L0_TRIP} }}\n'
                      f'\t\t\t\t{flush_log("L0_TRIP", bk)}\n'
                      '\t\t\t}\n\t\t}\n\t}\n')
    return ('# --trace-from only (see trace_pm_effects in tools/pmr/generate.py).\n\n'
            'pmr_trace_pms = {\n' + ''.join(logs) + '}\n\n'
            'pmr_l0_guard = {\n' + ''.join(guards) + '}\n')


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


SPLIT_MB = 24   # a script file over this many MB is written in parts (pmr_effects.txt, pmr_effects_2.txt, ...)


def split_file(text, rel):
    """A scripted effects file over SPLIT_MB in parts of at most SPLIT_MB each, cut before a top-level definition, in
    order: the game reads every file of the folder (a name defined in a later file is found, as pmr_urb_check). The
    device copy tool takes files up to 30 MB (2026-10-20: q58's pmr_effects.txt was 35 MB)."""
    cap = SPLIT_MB * 1024 * 1024
    if not rel.startswith('common/scripted_effects/') or len(text.encode('utf-8')) <= cap:
        return [text]
    cuts = [m.start() for m in re.finditer(r'^[a-z0-9_]+ = \{', text, re.M)]
    parts, start, size, last = [], 0, 0, 0
    for c in cuts[1:] + [len(text)]:
        piece = len(text[last:c].encode('utf-8'))
        if size + piece > cap and last > start:
            parts.append(text[start:last])
            start, size = last, 0
        size += piece
        last = c
    parts.append(text[start:])
    for x in parts:
        depth = x.count('{') - x.count('}')
        if depth or len(x.encode('utf-8')) > cap:
            raise SystemExit(f'{rel}: a part is {len(x.encode("utf-8")) >> 20} MB or cuts a block ({depth:+d} braces)')
    return parts


# ---------------------------------------------------------------------------------------------
# Second groups: option shares (trade-offs by local price, plantation treatment by acceptance)

PRICE_LADDER = list(range(-75, 76, PRICE_STEP))   # % off the base price; the game clamps prices to +-75%


def price_effect(good):
    """State scope: pmr_px_<good>, the price as a multiple of the base price: its market's, from the order book read
    once a month per market (market_read); scope:pmr_xmo is left on the market's owner. Since q95 (Pat 2026-11-10
    05:40Z: "we should read those by market and be as cheap as possible there as well") for a traded good, and since
    q96 (Pat 12:44Z, SUPPLY) for a local good too (LOCAL_GOODS): a local good's market orders are its states' summed,
    as vanilla's Five Year Plan reads electricity and transportation (ip5_je_values.txt), so a state's own surplus or
    shortage no longer moves its price; whether the state has any at all is SUPPLY's flag."""
    return (f'pmr_price_{good} = {{\n'
            '\tmarket ?= { owner ?= { save_temporary_scope_as = pmr_xmo } }\n'
            f'\tset_variable = {{ name = pmr_px_{good} value = 1 }}\n'
            f'\tif = {{\n\t\tlimit = {{ exists = scope:pmr_xmo }}\n\t\tpmr_xmkt_{good} = yes\n'
            f'\t\tset_variable = {{ name = pmr_px_{good} value = scope:pmr_xmo.var:pmr_mpx_{good} }}\n\t}}\n}}\n\n')


# Pat, 2026-10-19 02:32Z: "why are the pm options negative but the buildings profitable?" The profit calculation paid
# every recipe AUTOMATION_WAGE, about 2.5 times what Westfalen's steel mill pays. Each building type now pays its own
# state's wage, read off the building's books (books_effect, pmr_wage_<b>). 1.14.5 has no wage trigger: `earnings` is
# the panel's productivity (Building.GetAverageAnnualEarningsPerEmployee, shown under the productivity graph: revenue
# less inputs per employee a year; vanilla's tutorial counts a "productive" building as earnings >= 8), not the wage.
# So the wage bill is that margin less the week's profit, over the wage units at work:
#   wages a week = earnings x employees / 52 - weekly_profit,   employees = occupancy x the levels' full workforce
# Westfalen (q34 screenshot): productivity 5.2 x 8.5K / 52 = 850, balance 671, wages 179 (the panel: GBP 0.18K).
# The wage is a difference of two reads, so each is read to half a BOOKS_RATIO step: Westfalen's comes out within
# about 5%, under the PRICE_MOVE that triggers a recompute.
BOOKS_RATIO = 1.01
BOOKS_EARN = (0.05, 2000)      # earnings per employee a year, either sign; below the first, 0
BOOKS_PROFIT = (1, 3000000)    # weekly profit, either sign
BOOKS_OCC = 0.05               # below this occupancy the books are too thin to read: the last wage stands
WAGE_FLOOR = 10                # GBP a week per 10,000 wage units: what a reading lost to the reads' rounding falls to
PRICE_MOVE = 0.1               # a monthly pulse recomputes when a good's price or the wage moved this much (Pat 02:43Z)
THROUGHPUT_KEYS = {}           # building -> the throughput modifiers read on it (throughput_keys)


def geo_ladder(lo, hi):
    """lo, lo x BOOKS_RATIO, ... up to hi, to four significant figures"""
    out, x = [], lo
    while x <= hi * (1 + 1e-9):
        v = float(f'{x:.4g}')
        if not out or v > out[-1]:
            out.append(v)
        x *= BOOKS_RATIO
    return out


def books_effect():
    """State scope, the building saved as scope:pmr_bk (pmr_wage_<b>): pmr_bk_e, its earnings per employee a year (the
    panel's productivity), pmr_bk_p, its weekly profit, and pmr_bk_o, its occupancy (0 below BOOKS_OCC), each by
    bisection to the geometric middle of its BOOKS_RATIO step: about 11, 12 and 9 comparisons."""
    mid = BOOKS_RATIO ** 0.5

    def read(name, trig, rng):
        ns = geo_ladder(*rng)

        def leaf(sign):
            return lambda x: f'set_variable = {{ name = {name} value = {fmt(sign * float(f"{x * mid:.4g}")) if x else 0} }}'
        pos = highest(ns, lambda x: f'scope:pmr_bk = {{ {trig} >= {fmt(x)} }}', leaf(1), '\t\t')
        neg = highest(ns, lambda x: f'scope:pmr_bk = {{ {trig} <= {fmt(-x)} }}', leaf(-1), '\t\t')
        return (f'\tif = {{\n\t\tlimit = {{ scope:pmr_bk = {{ {trig} >= {fmt(ns[0])} }} }}\n{pos}\t}}\n'
                f'\telse = {{\n{neg}\t}}\n')
    occ = highest(geo_ladder(BOOKS_OCC, 1), lambda x: f'scope:pmr_bk = {{ occupancy >= {fmt(x)} }}',
                  lambda x: f'set_variable = {{ name = pmr_bk_o value = {fmt(min(1.0, float(f"{x * mid:.4g}"))) if x else 0} }}')
    if VALUE_READS:
        # VALUE_READS: the same three figures as plain numbers. Under a ladder's first step it read 0 (no earnings yet,
        # too thinly staffed), which the wage calculation tests, so the plain read keeps that.
        def plain(name, trig, lo, both=True):
            return (f'\tset_variable = {{ name = {name} value = scope:pmr_bk.{trig} }}\n'
                    f'\tif = {{ limit = {{ var:{name} < {fmt(lo)}' + (f' var:{name} > {fmt(-lo)}' if both else '')
                    + f' }} set_variable = {{ name = {name} value = 0 }} }}\n')

        def check(name, trig, lo, hi, both=True):
            # VALUE_READS 1: the ladder's figure stands; the plain read of the same figure is compared with it
            return (f'\tset_variable = {{ name = pmr_dv value = scope:pmr_bk.{trig} }}\n'
                    f'\tset_variable = {{ name = pmr_dl value = var:{name} }}\n'
                    f'\tset_variable = {{ name = pmr_dlo value = {fmt(lo)} }}\n\tset_variable = {{ name = pmr_dhi value = {fmt(hi)} }}\n'
                    f'\tpmr_dv_cmp = yes\n')
        e, pr, oc = (('pmr_bk_e', 'earnings', BOOKS_EARN[0], BOOKS_EARN[1]), ('pmr_bk_p', 'weekly_profit', BOOKS_PROFIT[0], BOOKS_PROFIT[1]),
                     ('pmr_bk_o', 'occupancy', BOOKS_OCC, 1))
        if VALUE_READS == 2:
            body = lambda rows: ''.join(plain(n, t, lo, n != 'pmr_bk_o') for n, t, lo, _hi in rows)   # noqa: E731
            return ('# State scope, the building saved as scope:pmr_bk: its books as the game holds them (VALUE_READS 2,\n'
                    '# books_effect in generate.py). pmr_bk_e, earnings per employee a year; pmr_bk_p, the week\'s profit;\n'
                    f'# pmr_bk_o, occupancy (0 below {fmt(BOOKS_OCC)}).\n'
                    'pmr_read_books = {\n' + body((e, pr, oc)) + '}\n\n'
                    + ('pmr_read_books_po = {\n' + body((pr, oc)) + '}\n\n' if SOLO_GATE >= 2 else ''))
        # the comparison runs in its window only (pmr_dv_on, value_check_effects), so the build's timing stays usable
        chk = lambda rows: ('\tif = {\n\t\tlimit = { has_global_variable = pmr_dv_on }\n'   # noqa: E731
                            + ''.join('\t' + ln for r in rows for ln in check(*r).splitlines(True)) + '\t}\n')
        return ('# State scope, the building saved as scope:pmr_bk: its books (books_effect in generate.py), each figure by\n'
                '# bisection, then compared with a plain read of it (VALUE_READS 1, pmr_dv_cmp).\n'
                'pmr_read_books = {\n' + read('pmr_bk_e', 'earnings', BOOKS_EARN) + read('pmr_bk_p', 'weekly_profit', BOOKS_PROFIT)
                + occ + chk((e, pr, oc)) + '}\n\n'
                + ('pmr_read_books_po = {\n' + read('pmr_bk_p', 'weekly_profit', BOOKS_PROFIT) + occ + chk((pr, oc)) + '}\n\n'
                   if SOLO_GATE >= 2 else '') + value_check_effects())
    return ('# State scope, the building saved as scope:pmr_bk: its books (books_effect in generate.py). pmr_bk_e, earnings\n'
            '# per employee a year (the productivity figure); pmr_bk_p, the week\'s profit; pmr_bk_o, occupancy (0 below '
            f'{fmt(BOOKS_OCC)}).\n'
            'pmr_read_books = {\n' + read('pmr_bk_e', 'earnings', BOOKS_EARN) + read('pmr_bk_p', 'weekly_profit', BOOKS_PROFIT)
            + occ + '}\n\n'
            + ('# The week\'s profit and the occupancy alone, for pmr_lite_<b> (SOLO_GATE).\n'
               'pmr_read_books_po = {\n' + read('pmr_bk_p', 'weekly_profit', BOOKS_PROFIT) + occ + '}\n\n'
               if SOLO_GATE >= 2 else ''))


DV_LOG = 40   # VALUE_READS 1: the first plain reads off their ladder's step are logged one by one (PMR;rec=DVOFF)
DV_WINDOW = (62, 365)   # VALUE_READS 1: the comparison runs for the first of these days in every second


def value_check_effects():
    """VALUE_READS 1 (test builds). State scope: pmr_dv_cmp compares a plain read (pmr_dv) with the ladder's figure for
    it (pmr_dl), whose steps are BOOKS_RATIO apart from pmr_dlo up to pmr_dhi (0 under the first, either sign): the
    read is off when it lies further from the ladder's figure than a step allows. Counts in pmr_dv_n and pmr_dv_bad
    (global); pmr_dv_report (country scope, monthly) logs them once a month. The ownership share is compared the same
    way against its step (pmr_dv_cmp_gov)."""
    tol = BOOKS_RATIO ** 0.5 - 1 + 0.001   # half a step, and the bounds' rounding to four figures
    where = ('date=[TimeKeeper.GetCurrentDate.GetString];state=[THIS.GetState.GetNameNoFormatting];'
             "plain=[THIS.Var('pmr_dv').GetValue|4];ladder=[THIS.Var('pmr_dl').GetValue|4]")
    count = ('\tif = {\n\t\tlimit = { NOT = { has_global_variable = pmr_dv_n } }\n'
             '\t\tset_global_variable = { name = pmr_dv_n value = 0 }\n\t\tset_global_variable = { name = pmr_dv_bad value = 0 }\n\t}\n'
             '\tchange_global_variable = { name = pmr_dv_n add = 1 }\n')
    bad = ('\t\tchange_global_variable = { name = pmr_dv_bad add = 1 }\n'
           f'\t\tif = {{ limit = {{ global_var:pmr_dv_bad <= {DV_LOG} }} debug_log = "PMR;rec=DVOFF;{where};what=WHAT" }}\n')
    drop = ''.join(f'\tremove_variable = {n}\n' for n in ('pmr_dv', 'pmr_dl', 'pmr_dlo', 'pmr_dhi', 'pmr_dd', 'pmr_dt'))
    return ('# State scope (VALUE_READS 1): is the plain read pmr_dv within a ladder step of the ladder\'s figure pmr_dl\n'
            'pmr_dv_cmp = {\n' + count
            + '\tset_variable = { name = pmr_dd value = var:pmr_dv }\n\tchange_variable = { name = pmr_dd subtract = var:pmr_dl }\n'
            '\tif = { limit = { var:pmr_dd < 0 } change_variable = { name = pmr_dd multiply = -1 } }\n'
            '\tset_variable = { name = pmr_dt value = var:pmr_dl }\n'
            '\tif = { limit = { var:pmr_dt < 0 } change_variable = { name = pmr_dt multiply = -1 } }\n'
            '\tset_variable = { name = pmr_dhi_at value = 0 }\n'
            '\tif = { limit = { var:pmr_dt >= var:pmr_dhi } set_variable = { name = pmr_dhi_at value = 1 } }   # the ladder\'s top: no upper bound\n'
            f'\tchange_variable = {{ name = pmr_dt multiply = {fmt(round(tol, 5))} }}\n'
            '\tif = { limit = { var:pmr_dl = 0 } set_variable = { name = pmr_dt value = var:pmr_dlo } }   # under the first step\n'
            '\tif = {\n\t\tlimit = { var:pmr_dd > var:pmr_dt var:pmr_dhi_at = 0 }\n' + bad.replace('WHAT', 'books')
            + '\t}\n\tremove_variable = pmr_dhi_at\n' + drop + '}\n\n'
            '# State scope (VALUE_READS 1): the same for the government\'s share, read in steps of '
            f'{fmt(GOV_FRACTION_STEP)}\n'
            'pmr_dv_cmp_gov = {\n' + count
            + '\tset_variable = { name = pmr_dd value = var:pmr_dv }\n\tchange_variable = { name = pmr_dd subtract = var:pmr_dl }\n'
            '\tif = { limit = { var:pmr_dd < 0 } change_variable = { name = pmr_dd multiply = -1 } }\n'
            f'\tif = {{\n\t\tlimit = {{ var:pmr_dd > {fmt(GOV_FRACTION_STEP / 2 + 0.0001)} }}\n' + bad.replace('WHAT', 'share')
            + '\t}\n\tremove_variable = pmr_dv\n\tremove_variable = pmr_dl\n\tremove_variable = pmr_dd\n}\n\n'
            '# Country scope, monthly (VALUE_READS 1): reads = plain reads compared so far, off = of those, outside their\n'
            f'# ladder step. The comparison runs for {DV_WINDOW[0]} days in every {DV_WINDOW[1]} (pmr_dv_on): every building\'s update falls\n'
            '# in a window, and the months between carry no check, so the build\'s timing stays usable.\n'
            'pmr_dv_report = {\n\tif = {\n\t\tlimit = { NOT = { has_global_variable = pmr_dv_m } }\n'
            '\t\tset_global_variable = { name = pmr_dv_m value = yes days = 28 }\n'
            '\t\tif = {\n\t\t\tlimit = { NOT = { has_global_variable = pmr_dv_w } }\n'
            f'\t\t\tset_global_variable = {{ name = pmr_dv_w value = yes days = {DV_WINDOW[1]} }}\n'
            f'\t\t\tset_global_variable = {{ name = pmr_dv_on value = yes days = {DV_WINDOW[0]} }}\n\t\t}}\n'
            '\t\tif = {\n\t\t\tlimit = { has_global_variable = pmr_dv_n }\n'
            '\t\t\tset_variable = { name = pmr_dv_n_v value = global_var:pmr_dv_n }\n'
            '\t\t\tset_variable = { name = pmr_dv_bad_v value = global_var:pmr_dv_bad }\n'
            '\t\t\tdebug_log = "PMR;rec=DV;date=[TimeKeeper.GetCurrentDate.GetString];'
            "reads=[THIS.Var('pmr_dv_n_v').GetValue|0];off=[THIS.Var('pmr_dv_bad_v').GetValue|0]\"\n"
            '\t\t\tremove_variable = pmr_dv_n_v\n\t\t\tremove_variable = pmr_dv_bad_v\n\t\t}\n\t}\n}\n\n')


def wage_effect(bk, b, econ):
    """State scope: pmr_wage_<b>, the wage the state's building of the type pays, as pmr_wg_<b> in GBP a week per 10,000
    wage units, read at most once a day (pmr_wgd_<b>). From its books (pmr_read_books) and the full workforce and wage
    units of the levels on each recipe (pmr_lv_<i>_<b>, TARGET_EMPLOYEES, econ):
      wage = (earnings x employees per level / 52 - weekly profit / occupancy / level) x 10,000 / wage units per level
    A building that can't be read (none yet, game setup, subsidised, under BOOKS_OCC staffed, or no earnings yet) keeps
    its last wage, or AUTOMATION_WAGE before the first. Test builds keep the reads for the PROFIT line (pmr_bke/bkp/bko_<b>)."""
    emps = TARGET_EMPLOYEES.get(bk, [])
    k = len(econ)
    sums = ''.join(f'\t\t\tif = {{ limit = {{ var:pmr_lv_{i}_{b} > 0 }} '
                   f'set_variable = {{ name = pmr_t value = var:pmr_lv_{i}_{b} }} '
                   f'change_variable = {{ name = pmr_bk_l add = var:pmr_t }} '
                   f'change_variable = {{ name = pmr_t multiply = {fmt(emps[i - 1] if i <= len(emps) else 0)} }} '
                   f'change_variable = {{ name = pmr_bk_n add = var:pmr_t }} '
                   f'set_variable = {{ name = pmr_t value = var:pmr_lv_{i}_{b} }} '
                   f'change_variable = {{ name = pmr_t multiply = {fmt(wu)} }} '
                   f'change_variable = {{ name = pmr_bk_u add = var:pmr_t }} }}\n'
                   for i, (_gd, wu) in enumerate(econ, 1))
    drop = f'if = {{ limit = {{ has_variable = pmr_bpl_{b} }} remove_variable = pmr_bpl_{b} }}'
    # bug review q51, P2-1: books unreadable because the building is subsidised or under BOOKS_OCC staffed say nothing
    # good about it (pmr_bsx_<b>), unlike a building with no reading yet; profit_effect's pmr_ok tells them apart
    unsx = f'if = {{ limit = {{ has_variable = pmr_bsx_{b} }} remove_variable = pmr_bsx_{b} }}'
    sx = (f'if = {{ limit = {{ NOT = {{ has_global_variable = pmr_setup }} exists = b:{bk} b:{bk} = {{ OR = {{ is_subsidized = yes '
          f'occupancy < {fmt(BOOKS_OCC)} }} }} }} set_variable = pmr_bsx_{b} }} else = {{ {unsx} }}')
    keep = ('' if RELEASE else
            ''.join(f'\t\t\tset_variable = {{ name = pmr_bk{x}_{b} value = var:pmr_bk_{x} }}\n' for x in 'epo'))
    return (f'pmr_wage_{b} = {{\n\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = pmr_wgd_{b} }} }}\n'
            f'\t\tset_variable = {{ name = pmr_wgd_{b} value = yes days = 1 }}\n'
            f'\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_wg_{b} }} }} '
            f'set_variable = {{ name = pmr_wg_{b} value = {AUTOMATION_WAGE} }} }}\n'
            f'\t\tif = {{\n\t\t\tlimit = {{ NOT = {{ has_global_variable = pmr_setup }} exists = b:{bk} has_variable = pmr_lv_{k}_{b} '
            f'has_variable = pmr_level_{b} var:pmr_level_{b} > 0 b:{bk} = {{ is_subsidized = no occupancy >= {fmt(BOOKS_OCC)} }} }}\n'
            f'\t\t\tb:{bk} = {{ save_temporary_scope_as = pmr_bk }}\n\t\t\tpmr_read_books = yes\n' + keep
            + '\t\t\t# the levels\' full workforce (pmr_bk_n) and wage units (pmr_bk_u) per level, from the recipes they run\n'
            '\t\t\tset_variable = { name = pmr_bk_l value = 0 }\n\t\t\tset_variable = { name = pmr_bk_n value = 0 }\n'
            '\t\t\tset_variable = { name = pmr_bk_u value = 0 }\n' + sums
            # q35 (Pat's Prussia, 2026-10-19 03:51Z): in a building's first days its books hold no sales, earnings read 0
            # and the formula took the week's whole loss as wages (739 against 360 a month later), so every recipe looked
            # like a loss and the cheapest became the default at once. No earnings: no reading.
            + '\t\t\tif = {\n\t\t\t\tlimit = { var:pmr_bk_l > 0 var:pmr_bk_u > 0 var:pmr_bk_o > 0 var:pmr_bk_e > 0 }\n'
            '\t\t\t\tchange_variable = { name = pmr_bk_n divide = var:pmr_bk_l }\n'
            '\t\t\t\tchange_variable = { name = pmr_bk_u divide = var:pmr_bk_l }\n'
            '\t\t\t\t# the margin a level makes at full staffing, less its profit at full staffing: its wages\n'
            '\t\t\t\tset_variable = { name = pmr_t value = var:pmr_bk_n }\n'
            '\t\t\t\tchange_variable = { name = pmr_t divide = 52 }\n'
            '\t\t\t\tchange_variable = { name = pmr_t multiply = var:pmr_bk_e }\n'
            f'\t\t\t\tset_variable = {{ name = pmr_wg_{b} value = var:pmr_bk_p }}\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_wg_{b} divide = var:pmr_bk_o }}\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_wg_{b} divide = var:pmr_level_{b} }}\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_wg_{b} multiply = -1 }}\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_wg_{b} add = var:pmr_t }}\n'
            '\t\t\t\t# per 10,000 wage units\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_wg_{b} multiply = 100 }}\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_wg_{b} divide = var:pmr_bk_u }}\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_wg_{b} multiply = 100 }}\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_wg_{b} max = {WAGE_FLOOR} }}\n'
            '\t\t\t\t# the books\' weekly profit per level at full staffing, which the profit calculation is held to\n'
            f'\t\t\t\tset_variable = {{ name = pmr_bpl_{b} value = var:pmr_bk_p }}\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_bpl_{b} divide = var:pmr_bk_o }}\n'
            f'\t\t\t\tchange_variable = {{ name = pmr_bpl_{b} divide = var:pmr_level_{b} }}\n\t\t\t\t{unsx}\n'
            # bug review q48, P2-3: a building whose books can't be read (subsidised, emptied, no earnings) drops its
            # last reading and is priced from its recipes, not frozen at an old profit
            f'\t\t\t}}\n\t\t\telse = {{ {drop} {unsx} }}\n\t\t}}\n\t\telse = {{ {drop} {sx} }}\n\t}}\n}}\n\n')


# 1.14.5's building_group_bg_<g>_throughput_add types and the fishing wharf's own (most in
# 99_todo_sort_into_other_files.txt, which a partial copy of the game can lack)
THROUGHPUT_1145 = {f'building_group_bg_{g}_throughput_add' for g in (
    'agriculture', 'arts', 'extraction', 'fishing', 'government', 'heavy_industry', 'infrastructure', 'light_industry',
    'logging', 'manufacturing', 'military', 'military_industry', 'mining', 'oil_extraction', 'plantations', 'ranching',
    'rubber', 'service', 'whaling')} | {'building_throughput_add', 'building_fishing_wharf_throughput_add'}


def throughput_keys(game, buildings):
    """Pat 02:43Z: each recipe's goods x (1 + the building's throughput). What 1.14.5 lets script read of it, per building
    type: building_throughput_add (economy of scale is the static modifier economy_of_scale, building_throughput_add
    0.01 a level beyond the first), building_group_<g>_throughput_add for its group and the groups above it, and the
    type's own building_<type>_throughput_add (companies' prosperity bonuses; vanilla names some in the singular,
    building_tooling_workshop_throughput_add), each where the modifier type exists. Left out: the company throughput
    bonus (country_company_throughput_bonus_add, on the share a company owns, which script can't read on a building)
    and the unincorporated-state variants."""
    defs = ''.join(open(os.path.join(game, 'common', 'modifier_type_definitions', n), encoding='utf-8-sig').read()
                   for n in sorted(os.listdir(os.path.join(game, 'common', 'modifier_type_definitions')))
                   if n.endswith('.txt'))
    known = set(re.findall(r'^(building_(?:\w+_)?throughput_add)\s*=', defs, re.M)) | THROUGHPUT_1145
    btype, parent = private_investment.building_groups(game)
    out = {}
    for bk in buildings:
        chain, g = [], btype.get(bk)
        while g and g not in chain:
            chain.append(g)
            g = parent.get(g)
        name = short(bk)
        own = [f'building_{f}_throughput_add' for f in (name, name[:-3] + 'y' if name.endswith('ies') else None,
                                                         name[:-1] if name.endswith('s') else None) if f]
        keys = (['building_throughput_add'] + [f'building_group_{g}_throughput_add' for g in chain]
                + [next((x for x in own if x in known), own[0])])
        out[bk] = [x for x in keys if x in known]
    return out


def opt_step(o):
    """an option's share grain in points: a trade-off's OPT_STEP (Pat 2026-11-10), treatment's 1"""
    return OPT_STEP if o.mode == 'market' else 1


LOCAL_GOODS = ('services', 'transportation', 'electricity')   # local = yes: no market order book to share out


def option_goods(options):
    """The goods the trade-offs value (pmr_price_<good>): every good of an option outside DEMAND_GROUPS."""
    return sorted({g for conv in options.values() for _, _, mode, _, opts, _ in conv if mode == 'market'
                   for o in opts if o.group not in DEMAND_GROUPS for g in o.goods})


def demand_goods(options):
    """The one good each demand-led option makes, whose market price its step reads (pmr_xmkt_<good>)."""
    return sorted({g for conv in options.values() for _, _, mode, _, opts, _ in conv if mode == 'market'
                   for o in opts if o.group in DEMAND_GROUPS for g, amt in o.goods.items() if amt > 0})


def budget_goods(options):
    """The market goods a trade-off option takes as an input (pmr_xb_<good>, market_read)."""
    return sorted({g for conv in options.values() for _, _, mode, _, opts, _ in conv if mode == 'market'
                   for o in opts if o.group not in DEMAND_GROUPS for g, amt in o.used.items()
                   if amt > 0 and g not in LOCAL_GOODS})


def market_values(goods, spare_goods):
    """Script values, in a country's scope (the market owner's, market_read). pmr_sv_mpx_<good>: the market's price of
    the good over its base, from its buy and sell orders as vanilla prices them, at the cap once one side is twice the
    other (BUY_SELL_DIFF_AT_MAX_FACTOR 2); base with neither. pmr_sv_spare_<good>: the market's spare supply of an input
    (sell less buy orders, at least 0), which the steps draw down (option_effects)."""
    out = []
    for g in goods:
        out.append(f'pmr_sv_mpx_{g} = {{\n\tvalue = 0\n\tmarket ?= {{\n\t\tmg:{g} ?= {{\n'
                   '\t\t\tadd = market_goods_buy_orders\n\t\t\tsubtract = market_goods_sell_orders\n'
                   '\t\t\tdivide = {\n\t\t\t\tvalue = market_goods_buy_orders\n\t\t\t\tmax = market_goods_sell_orders\n'
                   '\t\t\t\tmin = 1\n\t\t\t}\n\t\t}\n\t}\n'
                   f'\tmin = -1\n\tmax = 1\n\tmultiply = {fmt(PRICE_RANGE)}\n\tadd = 1\n}}\n\n')
    for g in spare_goods:
        out.append(f'pmr_sv_spare_{g} = {{\n\tvalue = 0\n\tmarket ?= {{ mg:{g} ?= {{ add = market_goods_delta }} }}\n'
                   '\tmin = 0\n}\n\n')
    return ''.join(out)


def check_price_defines(game):
    """market_values copies vanilla's pricing: refuse to build if the game's PRICE_RANGE or BUY_SELL_DIFF_AT_MAX_FACTOR
    moved"""
    text = open(os.path.join(game, 'common', 'defines', '00_defines.txt'), encoding='utf-8-sig').read()
    for key, want in (('PRICE_RANGE', PRICE_RANGE), ('BUY_SELL_DIFF_AT_MAX_FACTOR', 2)):
        m = re.search(r'^\s*' + key + r'\s*=\s*([0-9.]+)', text, re.M)
        if not m or float(m.group(1)) != want:
            raise SystemExit(f'00_defines.txt: {key} is {m.group(1) if m else "missing"}, market_values assumes {want}')


def market_read(good, spare):
    """State scope, scope:pmr_xmo its market's owner: the owner's pmr_mpx_<good> (market_values), and for an input its
    pmr_xb_<good>, read once a month (pmr_xmm_<good>): two reads a good a market a month, where q93 read the price
    through about five comparisons a good a state a day and the spare supply through a ladder."""
    return (f'pmr_xmkt_{good} = {{\n\tif = {{\n'
            f'\t\tlimit = {{ exists = scope:pmr_xmo NOT = {{ scope:pmr_xmo = {{ has_variable = pmr_xmm_{good} }} }} }}\n'
            '\t\tscope:pmr_xmo = {\n'
            # during game setup (pmr_setup) the market has no orders yet: read again at the first monthly pulse
            f'\t\t\tif = {{ limit = {{ NOT = {{ has_global_variable = pmr_setup }} }} '
            f'set_variable = {{ name = pmr_xmm_{good} value = yes days = 28 }} }}\n'
            f'\t\t\tset_variable = {{ name = pmr_mpx_{good} value = pmr_sv_mpx_{good} }}\n'
            + (f'\t\t\tset_variable = {{ name = pmr_xb_{good} value = pmr_sv_spare_{good} }}\n' if spare else '')
            + '\t\t}\n\t}\n}\n\n')


FRAMES = {}            # building type -> its frames.Building (the method-count rework), set by main()
OPTION_TYPES = set()   # building types with trade-off options (option_effects), the only ones with pmr_xok_<b>


def ungate_mobilization(text):
    """MOBILIZATION_UNGATE's options from vanilla's MOBILIZATION_SOURCE, each as a REPLACE: without the supply check of
    its listed goods."""
    out = []
    for key, goods in MOBILIZATION_UNGATE.items():
        start = text.find(f'\n{key} = {{')
        if start < 0:
            raise SystemExit(f'{MOBILIZATION_SOURCE}: {key} not found')
        block = text[start + 1:private_investment.block_end(text, text.index('{', start)) + 1]
        for g in goods:
            m = re.search(r'\n\t*mg:' + g + r' \?= \{\s*has_potential_supply = yes\s*\}', block)
            if not m:
                raise SystemExit(f'{MOBILIZATION_SOURCE}: {key} has no supply check for {g}; check MOBILIZATION_UNGATE')
            block = block[:m.start()] + block[m.end():]
        out.append(f'# vanilla\'s {key} without the supply check for {", ".join(goods)}\nREPLACE:{block}\n')
    return '\n'.join(out)


def demand_effects(b, gi, os_):
    """State scope: the step and first sight of a demand-led group (DEMAND_GROUPS) of building b, its one option's share
    (pmr_x_<j>_<b>) moved by the market's price of what it makes (its order book, market_read), against base:
    pmr_xd_<j>_<b> 1 over DEMAND_BAND, -1 under, 0 between."""
    if len(os_) != 1:
        raise SystemExit(f'{os_[0].bk}: {os_[0].group} is demand-led with {len(os_)} options; extend demand_effects')
    x = os_[0]
    made = [g for g, amt in x.goods.items() if amt > 0]
    if len(made) != 1:
        raise SystemExit(f'{x.key} makes {made}; a demand-led option follows the price of one good')
    xs, xd, xa = f'pmr_x_{x.j}_{b}', f'pmr_xd_{x.j}_{b}', f'pmr_xav_{x.j}_{b}'

    px = f'scope:pmr_xmo.var:pmr_mpx_{made[0]}'
    return (f'pmr_xstep_{gi}_{b} = {{\n'
            f'\tset_variable = {{ name = {xd} value = 0 }}\n'
            f'\tif = {{ limit = {{ var:{xa} = 0 }} set_variable = {{ name = {xs} value = 0 }} }}\n'
            '\telse = {\n'
            '\t\tmarket ?= { owner ?= { save_temporary_scope_as = pmr_xmo } }\n'
            f'\t\tpmr_xmkt_{made[0]} = yes\n'
            f'\t\tif = {{ limit = {{ exists = scope:pmr_xmo {px} > {fmt(1 + DEMAND_BAND)} }} set_variable = {{ name = {xd} value = 1 }} }}\n'
            f'\t\telse_if = {{ limit = {{ exists = scope:pmr_xmo {px} < {fmt(1 - DEMAND_BAND)} }} set_variable = {{ name = {xd} value = -1 }} }}\n'
            f'\t\tset_variable = {{ name = pmr_m value = {DEMAND_STEP} }}\n'
            + opts_pace('\t\t') +
            f'\t\tchange_variable = {{ name = pmr_m multiply = var:{xd} }}\n'
            f'\t\tchange_variable = {{ name = {xs} add = var:pmr_m }}\n'
            f'\t\tif = {{ limit = {{ var:{xs} > {SHARE_STEPS} }} set_variable = {{ name = {xs} value = {SHARE_STEPS} }} }}\n'
            f'\t\tif = {{ limit = {{ var:{xs} < {DEMAND_SEED} }} set_variable = {{ name = {xs} value = {DEMAND_SEED} }} }}\n'
            '\t}\n}\n\n'
            # first sight: the seed if it can run
            f'pmr_xinit_{gi}_{b} = {{\n'
            f'\tset_variable = {{ name = {xs} value = 0 }}\n'
            + (f'\tif = {{ limit = {{ var:{xa} = 1 }} set_variable = {{ name = {xs} value = {DEMAND_SEED} }} }}\n'
               if DEMAND_SEED else '')
            + '}\n\n')


def option_effects(bk, b, conv, goods_cost, recipes):
    """State scope, for one building type with converted second groups: pmr_opts_<b>, run by every
    tick after the recipe blend. Sets each option's share (pmr_x_<j>_<b>, 0..SHARE_STEPS) at first
    sight and once a month (pmr_month, set by the monthly pulse), then makes the share methods match."""
    if not conv:
        return ''
    OPTION_TYPES.add(bk)   # R8-1: only these set pmr_xok_<b>
    opts = [o for _, _, _, _, os_, _ in conv for o in os_]
    bv = lambda name: f'{name}_{b}'               # noqa: E731
    xv = lambda name, j: f'{name}_{j}_{b}'        # noqa: E731
    act = lambda pm: f'activate_production_method = {{ building_type = {bk} production_method = {pm} }}'   # noqa: E731
    is_on = lambda pm: f'is_production_method_active = {{ building_type = {bk} production_method = {pm} }}'   # noqa: E731
    can = lambda pm: frames.may_run(bk, pm)       # noqa: E731  a locked option: PMR's gate (frames.LOCK_PURE)
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

    def inputs(x):
        """The goods x buys from its market (q97: not an output it makes less of, as hardwood's wood: Pat 2026-11-10
        17:44Z, the step follows the market's prices, and wood short too had held logging camps off hardwood)"""
        return sorted(g for g, amt in x.used.items() if amt > 0 and goods_cost.get(g) and g not in LOCAL_GOODS)

    # Market options: value per level at the market's prices; an option that can't run sheds its share first. A
    # demand-led option (DEMAND_GROUPS) has no value: its step reads the market's price alone.
    market = [x for x in opts if x.mode == 'market' and x.group not in DEMAND_GROUPS]
    if market:
        goods = sorted({g for x in market for g in x.goods})
        # q95: a good's price is pmr_price_<good>'s (the market's, from its order book once a month; a local good's
        # too since q96), copied once a day per state (pmr_pxd_<good>): grain, sugar and fruit each feed several farm types
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
            # an option using an input its market is short of (at the price cap: buy orders twice the sell orders, as
            # vanilla's GOODS_SHORTAGE_PENALTY_THRESHOLD) says so in the panel (pmr_xsh_<j>_<b>). Pat 18:24Z: no
            # shedding for it ("not that it needs to reduce its pm target"); the step holds its gains to the market's
            # spare supply instead (pmr_xb_<good>)
            short_of = inputs(x)
            if short_of:
                cap = fmt(1 + PRICE_RANGE - 0.001)
                o.append(f'\tset_variable = {{ name = {xv("pmr_xsh", x.j)} value = 0 }}\n'
                         '\tif = { limit = { OR = { '
                         + ' '.join(f'var:pmr_px_{g} >= {cap}' for g in short_of)
                         + f' }} }} set_variable = {{ name = {xv("pmr_xsh", x.j)} value = 1 }} }}\n')
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
        pre = {k: OPT_STEP * round(v / OPT_STEP) for k, v in pre.items()}   # whole OPT_STEP chunks (q94)
        if sum(pre[x.key] for x in os_ if x.key in pre) > SHARE_STEPS:
            raise SystemExit(f'TRADE_PRELOAD[{bk!r}] rounds to more than {SHARE_STEPS} in one group')
        out = '\t\tset_variable = { name = pmr_t value = 0 }\n'
        for x in reversed(os_):
            if pre.get(x.key):
                out += f'\t\tchange_variable = {{ name = pmr_t add = {pre[x.key]} }}\n'
            out += (f'\t\tif = {{ limit = {{ var:{xv("pmr_xav", x.j)} = 1 }} set_variable = {{ name = {xv("pmr_x", x.j)} value = var:pmr_t }} '
                    'set_variable = { name = pmr_t value = 0 } }\n')
        return out

    # Pat 2026-10-19 18:24Z (mines across a market moved onto explosives together and ran it short): "explosives should
    # be like hardwood". A step onto an option using an input good gains no more points than the market's spare supply
    # of it covers: the surplus (sell less buy orders) read once a month into the market owner's pmr_xb_<good>
    # (pmr_xmkt_<good>, market_read), and each gain takes its demand (points x level x input per level) off it, so
    # the market's buildings move onto it a surplus at a time, OPT_STEP points at a time. Prices do the rest.
    def budget_cap(x):
        out = f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:pmr_bi = {x.j} }}\n'
        for g in inputs(x):
            per = x.used[g] / SHARE_STEPS
            out += ('\t\t\t\tset_variable = { name = pmr_t value = 0 }\n'
                    f'\t\t\t\tif = {{ limit = {{ exists = scope:pmr_xmo }} set_variable = {{ name = pmr_t value = scope:pmr_xmo.var:pmr_xb_{g} }} }}\n'
                    f'\t\t\t\tset_variable = {{ name = pmr_u value = var:pmr_level_{b} }}\n'
                    f'\t\t\t\tchange_variable = {{ name = pmr_u multiply = {fmt(per)} }}\n'
                    '\t\t\t\tif = { limit = { var:pmr_u > 0 } change_variable = { name = pmr_t divide = var:pmr_u } }\n'
                    # down to whole OPT_STEP chunks
                    f'\t\t\t\tchange_variable = {{ name = pmr_t divide = {OPT_STEP} }}\n'
                    '\t\t\t\tchange_variable = { name = pmr_t subtract = 0.5 }\n'
                    '\t\t\t\tround_variable = { name = pmr_t nearest = 1 }\n'
                    f'\t\t\t\tchange_variable = {{ name = pmr_t multiply = {OPT_STEP} }}\n'
                    '\t\t\t\tif = { limit = { var:pmr_t < var:pmr_m } set_variable = { name = pmr_m value = var:pmr_t } }\n')
        return out + '\t\t\t\tif = { limit = { var:pmr_m < 0 } set_variable = { name = pmr_m value = 0 } }\n\t\t\t}\n'

    def budget_use(x):
        out = f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:pmr_bi = {x.j} var:pmr_m > 0 exists = scope:pmr_xmo }}\n'
        for g in inputs(x):
            out += (f'\t\t\t\tset_variable = {{ name = pmr_u value = var:pmr_level_{b} }}\n'
                    f'\t\t\t\tchange_variable = {{ name = pmr_u multiply = {fmt(x.used[g] / SHARE_STEPS)} }}\n'
                    '\t\t\t\tchange_variable = { name = pmr_u multiply = var:pmr_m }\n'
                    f'\t\t\t\tset_variable = {{ name = pmr_t value = scope:pmr_xmo.var:pmr_xb_{g} }}\n'
                    '\t\t\t\tchange_variable = { name = pmr_t subtract = var:pmr_u }\n'
                    f'\t\t\t\tscope:pmr_xmo = {{ set_variable = {{ name = pmr_xb_{g} value = scope:pmr_xst.var:pmr_t }} }}\n')
        return out + '\t\t\t}\n'

    # Monthly market step, group by group.
    for g, gi, mode, none, os_, std in conv:
        if mode != 'market':
            continue
        if g in DEMAND_GROUPS:
            o.append(demand_effects(b, gi, os_))
            continue
        capped = any(inputs(x) for x in os_)
        scopes = ('\tsave_temporary_scope_as = pmr_xst\n'
                  '\tmarket ?= { owner ?= { save_temporary_scope_as = pmr_xmo } }\n'
                  if capped else '')
        o.append(f'pmr_xstep_{gi}_{b} = {{\n' + scopes + none_share(gi, os_) + best(os_)
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
                 # OPT_STEP points a month (Pat 2026-11-10, q94)
                 f'\t\t\tset_variable = {{ name = pmr_m value = {OPT_STEP} }}\n'
                 # TICK_EVERY (Pat 2026-10-21 12:37Z) and OPTS_CYCLE (19:35Z): the step of the months since the last,
                 # capped below by what the options hold
                 + opts_pace('\t\t\t') +
                 f'\t\t\tif = {{ limit = {{ var:pmr_wi = 0 var:{xv("pmr_xn", gi)} < var:pmr_m }} '
                 f'set_variable = {{ name = pmr_m value = var:{xv("pmr_xn", gi)} }} }}\n'
                 + ''.join(f'\t\t\tif = {{ limit = {{ var:pmr_wi = {x.j} var:{xv("pmr_x", x.j)} < var:pmr_m }} '
                           f'set_variable = {{ name = pmr_m value = var:{xv("pmr_x", x.j)} }} }}\n' for x in os_)
                 # q97: what the best option's spare-supply cap turns away from an option that can't run goes to none
                 + ('\t\t\tset_variable = { name = pmr_m0 value = var:pmr_m }\n' if capped else '')
                 + ''.join(budget_cap(x) for x in os_ if inputs(x))
                 + ''.join(f'\t\t\tif = {{ limit = {{ var:pmr_wi = {x.j} }} '
                           + (f'if = {{ limit = {{ var:{xv("pmr_xav", x.j)} = 0 }} '
                              f'change_variable = {{ name = {xv("pmr_x", x.j)} subtract = var:pmr_m0 }} }} else = {{ '
                              if capped else '')
                           + f'change_variable = {{ name = {xv("pmr_x", x.j)} subtract = var:pmr_m }}'
                           + (' }' if capped else '') + ' }\n' for x in os_)
                 + ''.join(f'\t\t\tif = {{ limit = {{ var:pmr_bi = {x.j} }} '
                           f'change_variable = {{ name = {xv("pmr_x", x.j)} add = var:pmr_m }} }}\n' for x in os_)
                 + ''.join(budget_use(x) for x in os_ if inputs(x))
                 + '\t\t}\n\t}\n}\n\n')
        # First sight: the option the vanilla marker runs (game start), or for a building built
        # during the game the best-paying one, if it beats none by the dead band.
        o.append(f'pmr_xinit_{gi}_{b} = {{\n'
                 + ''.join(f'\tset_variable = {{ name = {xv("pmr_x", x.j)} value = 0 }}\n' for x in os_)
                 + f'\tif = {{\n\t\tlimit = {{ has_variable = {bv("pmr_xnew")} }}\n'
                 + best([x for x in os_ if not inputs(x)], '\t\t')
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

    # Making the share methods match, as pmr_blend_<b> does for recipes: only a digit that is not
    # running is activated, with the building's lock open, then shut again.
    def bisect(var, leaf, ind, lo=0, hi=SHARE_STEPS):
        if lo == hi:
            return f'{ind}{leaf(lo)}\n'
        mid = (lo + hi) // 2
        return (f'{ind}if = {{ limit = {{ var:{var} <= {mid} }}\n' + bisect(var, leaf, ind, lo, mid)
                + f'{ind}}}\n{ind}else = {{\n' + bisect(var, leaf, ind, mid + 1, hi) + f'{ind}}}\n')

    def bisect_x(x, leaf, ind):
        """bisect over an option's share methods (opt_values): a trade-off's run every OPT_STEP points, a share
        between two of them running the nearer"""
        step = opt_step(x)
        if step == 1:
            return bisect(xv('pmr_x', x.j), leaf, ind)

        def by(vals):
            if len(vals) == 1:
                return f'{ind}{leaf(vals[0])}\n'
            mid = (len(vals) - 1) // 2
            return (f'{ind}if = {{ limit = {{ var:{xv("pmr_x", x.j)} <= {fmt((vals[mid] + vals[mid + 1]) / 2)} }}\n'
                    + by(vals[:mid + 1]) + f'{ind}}}\n{ind}else = {{\n' + by(vals[mid + 1:]) + f'{ind}}}\n')
        return by(list(range(0, SHARE_STEPS + 1, step)))
    # each option's tens (pmr_xqt, 0..10) and units (pmr_xqu, 0..9) of its share in % (pmr_x)
    halves = (('pmr_xqt', 'pmr_xat', 'x', 10, lambda d: 10 * d), ('pmr_xqu', 'pmr_xau', 'xu', 9, lambda d: d))
    # Method-count rework: only treatment runs share methods; a trade-off's shares are its frames (pmr_frame_<b>)
    topts = [x for x in opts if x.mode == 'treat']
    o.append(f'pmr_xapply_{b} = {{\n')
    if not SHARE_DIGITS:   # one method per share
        # Review 8, R8-1: after a full read (pmr_xok_<b>) pmr_xa_<j> holds the share that runs, and only this effect
        # changes it (the methods self-lock), so a monthly tick reads and activates only an option whose share moved.
        # pmr_mix_<b> and a building still on its start method (pmr_blend_<b>) remove pmr_xok_<b>.
        for x in topts:
            sm = lambda n, x=x: f'pm_pmr_x_{b}_{x.j}_{n}'   # noqa: E731
            o.append(f'\tif = {{\n\t\tlimit = {{ NOT = {{ AND = {{ has_variable = pmr_month has_variable = pmr_xok_{b} '
                     f'var:{xv("pmr_xa", x.j)} = var:{xv("pmr_x", x.j)} }} }} }}\n'
                     f'\tset_variable = {{ name = {xv("pmr_xa", x.j)} value = -1 }}\n'
                     + bisect_x(x, lambda n, sm=sm, x=x: f'if = {{ limit = {{ {is_on(sm(n))} }} '
                                f'set_variable = {{ name = {xv("pmr_xa", x.j)} value = {n} }} }}', '\t')
                     + f'\tif = {{\n\t\tlimit = {{ var:{xv("pmr_xa", x.j)} = -1 }}\n'
                     + bisect_x(x, lambda n, sm=sm: act(sm(n)), '\t\t')
                     + f'\t\tset_variable = {{ name = {xv("pmr_xa", x.j)} value = var:{xv("pmr_x", x.j)} }}\n\t}}\n\t}}\n')
        o.append(f'\tset_variable = pmr_xok_{b}\n')
    for x in (topts if SHARE_DIGITS else ()):
        o.append(f'\tset_variable = {{ name = {xv("pmr_xqt", x.j)} value = var:{xv("pmr_x", x.j)} }}\n'
                 f'\tchange_variable = {{ name = {xv("pmr_xqt", x.j)} subtract = 4.5 }}\n'
                 f'\tchange_variable = {{ name = {xv("pmr_xqt", x.j)} multiply = 0.1 }}\n'
                 f'\tround_variable = {{ name = {xv("pmr_xqt", x.j)} nearest = 1 }}\n'
                 f'\tset_variable = {{ name = {xv("pmr_xqu", x.j)} value = var:{xv("pmr_xqt", x.j)} }}\n'
                 f'\tchange_variable = {{ name = {xv("pmr_xqu", x.j)} multiply = -10 }}\n'
                 f'\tchange_variable = {{ name = {xv("pmr_xqu", x.j)} add = var:{xv("pmr_x", x.j)} }}\n')
        for qv, av, sh, hi, val in halves:
            o.append(f'\tset_variable = {{ name = {xv(av, x.j)} value = -1 }}\n'
                     + bisect(xv(qv, x.j), lambda d, x=x, sh=sh, av=av, val=val: f'if = {{ limit = {{ {is_on(f"pm_pmr_{sh}_{b}_{x.j}_{val(d)}")} }} '
                              f'set_variable = {{ name = {xv(av, x.j)} value = {d} }} }}', '\t', hi=hi))
    if SHARE_DIGITS:
        o.append('\t# each digit not the one wanted moves (activate_production_method checks no unlock)\n')
    for x in (topts if SHARE_DIGITS else ()):
        for qv, av, sh, hi, val in halves:
            o.append(f'\tif = {{\n\t\tlimit = {{ var:{xv(av, x.j)} = -1 }}\n'
                     + bisect(xv(qv, x.j), lambda d, x=x, sh=sh, val=val: act(f'pm_pmr_{sh}_{b}_{x.j}_{val(d)}'), '\t\t', hi=hi)
                     + f'\t\tset_variable = {{ name = {xv(av, x.j)} value = var:{xv(qv, x.j)} }}\n\t}}\n')
    for x in (topts if SHARE_DIGITS else ()):
        # the share in % both digits run (the OPT log line's running=), -1 while either is off
        o.append(f'\tset_variable = {{ name = {xv("pmr_xa", x.j)} value = -1 }}\n'
                 f'\tif = {{ limit = {{ var:{xv("pmr_xat", x.j)} >= 0 var:{xv("pmr_xau", x.j)} >= 0 }} '
                 f'set_variable = {{ name = {xv("pmr_xa", x.j)} value = var:{xv("pmr_x", x.j)} }} }}\n')
    o.append('}\n\n')

    # The entry point, and what the panel's trade-off bars read: each group's none share.
    # method-count rework: the frame pick runs again only if a share moved (pmr_fok_<b>, pmr_frame_<b>)
    keep = ''.join(f'\tset_variable = {{ name = {xv("pmr_xo", x.j)} value = -1 }}\n'
                   f'\tif = {{ limit = {{ has_variable = {xv("pmr_x", x.j)} }} '
                   f'set_variable = {{ name = {xv("pmr_xo", x.j)} value = var:{xv("pmr_x", x.j)} }} }}\n' for x in opts)
    moved_x = (f'\tif = {{ limit = {{ has_variable = pmr_fok_{b} OR = {{ '
               + ' '.join(f'NOT = {{ var:{xv("pmr_xo", x.j)} = var:{xv("pmr_x", x.j)} }}' for x in opts)
               + f' }} }} remove_variable = pmr_fok_{b} }}\n'
               + ''.join(f'\tremove_variable = {xv("pmr_xo", x.j)}\n' for x in opts))
    o.append(f'pmr_opts_{b} = {{\n{keep}\tpmr_xavail_{b} = yes\n'
             + (f'\tif = {{ limit = {{ OR = {{ NOT = {{ has_variable = {bv("pmr_xinit")} }} has_variable = pmr_month }} }} pmr_xvalue_{b} = yes }}\n'
                if market else '')
             + f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {bv("pmr_xinit")} }} }}\n'
             f'\t\tset_variable = {bv("pmr_xinit")}\n'
             + ''.join(f'\t\tpmr_xinit_{gi}_{b} = yes\n' if mode == 'market' else f'\t\tpmr_xtreat_{gi}_{b} = yes\n'
                       for g, gi, mode, *_ in conv)
             + '\t}\n\telse_if = {\n\t\tlimit = { has_variable = pmr_month }\n'
             + ''.join(f'\t\tpmr_xstep_{gi}_{b} = yes\n' if mode == 'market' else
                       (f'\t\tif = {{ limit = {{ NOT = {{ has_global_variable = pmr_off_treat }} }} pmr_xtreat_{gi}_{b} = yes }}\n'
                        if OBS_PARTS_ON else f'\t\tpmr_xtreat_{gi}_{b} = yes\n')
                       for g, gi, mode, *_ in conv)
             + f'\t}}\n\tif = {{ limit = {{ has_variable = {bv("pmr_xnew")} }} remove_variable = {bv("pmr_xnew")} }}\n'
             f'\tpmr_xapply_{b} = yes\n')
    for g, gi, mode, none, os_, std in conv:
        o.append(none_share(gi, os_))
    o.append(moved_x)
    f = lambda name, d=0: f"[THIS.Var('{name}').GetValue|{d}]"   # noqa: E731
    line = (f'PMR;rec=OPT;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={bk}'
            + ';x=' + '/'.join(f(xv('pmr_x', x.j)) for x in opts)
            + ';running=' + '/'.join(f(xv('pmr_xa', x.j)) if x.mode == 'treat' else '-' for x in opts)
            + ';can=' + '/'.join(f(xv('pmr_xav', x.j)) for x in opts))
    demand = [x for x in opts if x.group in DEMAND_GROUPS]
    if demand:   # the market's price signal at the last demand-led step: 1 over DEMAND_BAND, -1 under, 0 between
        line += ';demand=' + '/'.join(f(xv('pmr_xd', x.j)) for x in demand)
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
        pot = f'has_variable = pmr_retool_gate_{b}'
        if side == 'priv':
            flag = f'pmr_retool_open_priv_{b}_{j}'
            open_ = f'has_variable = {flag}'
            ai_limit = open_
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
                   f'\tcan_build_private = {{\n\t\t{open_}\n\t\tpmr_retool_room_priv_{b}_{j} = yes\n'
                   + (f'\t\tpmr_retool_investor{"_abroad" if j == ABROAD_SLOT else ""}_{b} = yes\n\t}}\n' if ABROAD_SLOT else
                      f'\t\ttrigger_if = {{\n\t\t\tlimit = {{ has_variable = pmr_abroad_{b} }}\n\t\t\tpmr_retool_investor_abroad_{b} = yes\n\t\t}}\n'
                      f'\t\ttrigger_else = {{ pmr_retool_investor_{b} = yes }}\n\t}}\n'))
            pmgs = 'pmg_pmr_retool_crew' if RETOOL_CREW else 'pmg_pmr_retool'
        elif side == 'gov':
            flag = f'pmr_retool_open_gov_{b}'
            who = ('\t# The government only, for the government-owned share, where the player owns no levels abroad\n'
                   '\t# (there building_pmr_retool_gova_<b>, for the player\'s government only).\n'
                   f'\tcan_build_government = {{ pmr_retool_room_gov_{b} = yes }}\n'
                   '\tcan_build_private = { always = no }\n')
            pmgs = 'pmg_pmr_retool'   # vanilla's pmg_dummy showed its placeholder name and icon (q105 screenshot)
            ai_limit = f'has_variable = {flag} NOT = {{ has_variable = pmr_abroad_{b} }}'
        else:
            flag = f'pmr_retool_open_gov_{b}'
            who = ('\t# The player\'s government only, for its own levels abroad (pmr_abroad_<b>): the upgrade button\n'
                   '\t# expands the site the tick keeps standing there (Building.QueueConstruction), never an AI.\n'
                   f'\tcan_build_government = {{ pmr_retool_room_gova_{b} = yes }}\n'
                   '\tcan_build_private = { always = no }\n')
            pmgs = 'pmg_pmr_retool'   # vanilla's pmg_dummy showed its placeholder name and icon (q105 screenshot)
        out.append(
            f'{rb} = {{\n'
            f'\tbuilding_group = {group}\n'
            f'\ticon = "{icon}"\n'
            f'\tcity_type = none\n'
            f'\tdownsizeable = no\n'
            '\t# Retool levels come only from the funders below, never from auto-expansion.\n'
            '\tshould_auto_expand = { always = no }\n'
            f'\t# Open only while script is retooling a {bk} in this state'
            + (', where the player owns levels abroad' if j == ABROAD_SLOT else '')
            + '.\n'
            f'\tpotential = {{ {pot} }}\n'
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
        plain = (f'\thas_variable = {cap}\n'
                 '\ttrigger_if = {\n'
                 f'\t\tlimit = {{ exists = b:{rbx} }}\n'
                 f'\t\tb:{rbx} = {{ level_after_queued_constructions <= pmr_room_value_priv_{b}_{j} }}\n'
                 '\t}\n'
                 f'\ttrigger_else = {{ var:{cap} >= scope:num_levels }}\n')
        out.append(f'pmr_retool_room_priv_{b}_{j} = {{\n' + plain + '}\n')
    # levels_owned_by_country counts "a country or investors in that country" (triggers.log), so for
    # the state's own country it includes the government's levels: its investors need more than those.
    # Vanilla compares the same trigger against c:RUS for the Manchurian railway.
    out.append(
        f'pmr_retool_investor_{b} = {{\n'
        '\texists = scope:investor_country\n'
        f'\texists = b:{bk}\n'
        '\ttrigger_if = {\n'
        '\t\tlimit = { owner = scope:investor_country }\n'
        + f'\t\thas_variable = pmr_gov_levels_{b}\n'
        f'\t\tb:{bk} = {{ levels_owned_by_country = {{ target = scope:investor_country value > state.var:pmr_gov_levels_{b} }} }}\n'
        + '\t}\n'
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
            f'\tis_valid = {{ has_variable = pmr_abroad_{b} b:{bk} ?= {{ level >= 1 }} }}\n'
            f'\teffect = {{ pmr_tick_{b} = yes }}\n}}\n\n')


def gov_retool_all_sgui(buildings):
    """The Buildings panel's Retool Government Levels button (Pat 2026-10-20 21:54Z): every building type row's
    upgrade button at once, the player's own states only (abroad goes through the game's queue, building by building)."""
    def open_(bk):
        return f'has_variable = pmr_retool_open_gov_{short(bk)} b:{bk} ?= {{ level >= 1 }}'
    any_open = ''.join(f'\t\t\t\tAND = {{ {open_(bk)} }}\n' for bk in buildings)
    queue = ''.join(f'\t\t\tif = {{ limit = {{ {open_(bk)} }} pmr_queue_gov_{short(bk)} = yes }}\n' for bk in buildings)
    # Pat 2026-10-21 21:18Z: the button asks first, with how much it will queue: the levels (pmr_gall_l, one
    # construction each, pmr_queue_gov_<b>) and the buildings (pmr_gall_b), counted as it is clicked
    count = ''.join(f'\t\t\tif = {{\n\t\t\t\tlimit = {{ {open_(bk)} NOT = {{ has_variable = pmr_abroad_{short(bk)} }} '
                    f'has_variable = pmr_room_gov_{short(bk)} }}\n'
                    f'\t\t\t\troot = {{ change_variable = {{ name = pmr_gall_l add = scope:pmr_st.var:pmr_room_gov_{short(bk)} }} '
                    'change_variable = { name = pmr_gall_b add = 1 } '
                    f'change_variable = {{ name = pmr_gall_c add = {{ value = scope:pmr_st.var:pmr_room_gov_{short(bk)} '
                    f'multiply = pmr_retool_cost_{short(bk)} }} }} }}\n\t\t\t}}\n' for bk in buildings)
    return ('pmr_gov_retool_all_sgui = {\n\tscope = country\n'
            f'\tis_valid = {{\n\t\tany_scope_state = {{\n\t\t\tOR = {{\n{any_open}'
            '\t\t\t}\n\t\t}\n\t}\n'
            f'\teffect = {{\n\t\tevery_scope_state = {{\n\t\t\tset_variable = pmr_bulk\n{queue}'
            '\t\t\tremove_variable = pmr_bulk\n\t\t}\n'
            '\t\tif = { limit = { has_variable = pmr_gall_l var:pmr_gall_l >= 0 var:pmr_gall_b >= 0 } '
            'remove_variable = pmr_gall_l remove_variable = pmr_gall_b }\n'
            '\t\tif = { limit = { has_variable = pmr_gall_c var:pmr_gall_c >= 0 } remove_variable = pmr_gall_c }\n'
            + '\t\tpmr_c_sum_all = yes\n\t\tdebug_log = "PMR;rec=GOV_ALL;date=[TimeKeeper.GetCurrentDate.GetString]"\n\t}\n}\n\n'
            'pmr_gov_retool_count_sgui = {\n\tscope = country\n'
            '\teffect = {\n\t\tset_variable = { name = pmr_gall_l value = 0 }\n\t\tset_variable = { name = pmr_gall_b value = 0 }\n'
            '\t\tset_variable = { name = pmr_gall_c value = 0 }\n'
            f'\t\tevery_scope_state = {{\n\t\t\tsave_temporary_scope_as = pmr_st\n{count}\t\t}}\n\t}}\n}}\n\n')


GOV_ALL_ASK = 'pmr_gall_ask'   # GUI variable: the Retool Government Levels popup is open (patch_hud_gov_all)
GOV_ALL_SCOPE = 'GuiScope.SetRoot(GetPlayer.MakeScope).End'
GOV_ALL_CLICK = (f"onclick = \"[GetScriptedGui('pmr_gov_retool_count_sgui').Execute({GOV_ALL_SCOPE})]\"\n"
                 f"{{i}}onclick = \"[GetVariableSystem.Set('{GOV_ALL_ASK}', 'yes')]\"\n")


def patch_browser_retool_all(text):
    """building_browser_panel.gui: the Retool Government Levels button above the Building Registry's Nationalize Filtered
    Buildings, in its style, and (Pat 2026-10-21 21:18Z, "right below the gear cog in the same format") a 45 x 45 one
    under the Buildings panel's map mode button (map_modes_button_position, 607 102). Both open the popup that asks
    first (patch_hud_gov_all); its Yes runs pmr_gov_retool_all_sgui."""
    anchor = '\t\t\t\t\t\t# NATIONALIZE FILTERED BUILDINGS BUTTON\n'
    if text.count(anchor) != 1:
        raise SystemExit(f'building_browser_panel.gui: expected one Nationalize Filtered Buildings button, found '
                         f'{text.count(anchor)}; update patch_browser_retool_all')
    modes = ('\t\tblockoverride "map_modes_button" {\n\t\t\tmap_modes_single_button_minimized = {\n'
             '\t\t\t\tdatacontext = "[BuildingBrowserPanel.GetMapModeList]"\n'
             '\t\t\t\tusing = map_modes_button_position\n\t\t\t}\n')
    if text.count(modes) != 1:
        raise SystemExit('building_browser_panel.gui: expected one map mode button; update patch_browser_retool_all')
    ind = '\t\t\t\t\t\t'
    scope = GOV_ALL_SCOPE
    i3 = '\t\t\t'
    # interface review (SPEC.md B3, P1): both buttons take the same tooltip, and say why while greyed
    tip = (f"tooltip = \"[SelectLocalization(GetScriptedGui('pmr_gov_retool_all_sgui').IsValid({scope}), "
           "'PMR_GOV_RETOOL_ALL_TT', 'PMR_GOV_RETOOL_ALL_NONE')]\"\n")
    gear = (f'{i3}# PMR: Retool Government Levels, under the map mode button\n{i3}button = {{\n{i3}\tposition = {{ 607 152 }}\n'
            f'{i3}\tsize = {{ 45 45 }}\n{i3}\tusing = default_button\n{i3}\t{tip}'
            f'{i3}\tusing = tooltip_ne\n'
            f"{i3}\tenabled = \"[GetScriptedGui('pmr_gov_retool_all_sgui').IsValid({scope})]\"\n"
            f'{i3}\t' + GOV_ALL_CLICK.format(i=i3 + '\t')
            + f'\n{i3}\ticon = {{\n{i3}\t\tparentanchor = center\n{i3}\t\tsize = {{ 30 30 }}\n'
            f'{i3}\t\ttexture = "{GOV_RETOOL_ICON}"\n{i3}\t\talwaystransparent = yes\n{i3}\t}}\n{i3}}}\n')
    text = text.replace(modes, modes + gear)
    button = (f'{ind}# PMR: government retooling for every building at once\n{ind}button = {{\n'
              f'{ind}\tsize = {{ 404 50 }}\n{ind}\tusing = default_button_primary\n{ind}\tusing = confirm_button_sound\n'
              f'{ind}\t{tip}{ind}\tusing = tooltip_ne\n'
              f"{ind}\tenabled = \"[GetScriptedGui('pmr_gov_retool_all_sgui').IsValid({scope})]\"\n"
              f'{ind}\t' + GOV_ALL_CLICK.format(i=ind + '\t') + '\n'

              f'{ind}\tflowcontainer = {{\n{ind}\t\tparentanchor = center\n{ind}\t\tspacing = 5\n\n'
              f'{ind}\t\ticon = {{\n{ind}\t\t\tparentanchor = vcenter\n{ind}\t\t\tsize = {{ 40 40 }}\n'
              f'{ind}\t\t\ttexture = "{GOV_RETOOL_ICON}"\n{ind}\t\t}}\n\n'
              f'{ind}\t\ttextbox = {{\n{ind}\t\t\tparentanchor = vcenter\n{ind}\t\t\tusing = fontsize_large\n'
              f'{ind}\t\t\talign = hcenter|nobaseline\n{ind}\t\t\tautoresize = yes\n{ind}\t\t\tmax_width = 350\n'
              f'{ind}\t\t\tfontsize_min = 14\n{ind}\t\t\telide = right\n{ind}\t\t\ttext = "PMR_GOV_RETOOL_ALL"\n'
              f'{ind}\t\t}}\n{ind}\t}}\n{ind}}}\n\n')
    return text.replace(anchor, button + anchor)


def gov_retool_country_sgui(bk):
    """The Buildings tab's upgrade button on a building type row: every state at once."""
    b = short(bk)
    return (f'pmr_gov_retool_c_{b}_sgui = {{\n\tscope = country\n'
            f'\tis_valid = {{ any_scope_state = {{ has_variable = pmr_retool_open_gov_{b} b:{bk} ?= {{ level >= 1 }} }} }}\n'
            f'\teffect = {{\n\t\tevery_scope_state = {{\n\t\t\tlimit = {{ has_variable = pmr_retool_open_gov_{b} b:{bk} ?= {{ level >= 1 }} }}\n'
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


LOOKUP_FROM = 7   # an index ladder this long or longer becomes a binary search (lookup); shorter ones cost no more as ladders


def lookup(var, ns, body, ind='\t'):
    """body(x) for the x of ns (ascending integers) that var holds, nothing if it holds none of them: the
    `if var = 1 ... else_if var = 2 ...` ladder done as a binary search on var > m, each leaf still testing
    var = x (performance review 3, S2; Pat, 2026-10-19 02:35Z). The same leaf runs for every value, about
    log2(len(ns)) + 1 checks where the ladder took len(ns) / 2 (a ranch's 36 targets: 7, not 18). Ladders
    shorter than LOOKUP_FROM stay ladders."""
    if len(ns) < LOOKUP_FROM:
        return ''.join(f'{ind}{"if" if j == 0 else "else_if"} = {{ limit = {{ {var} = {x} }} {body(x)} }}\n'
                       for j, x in enumerate(ns))

    def find(lo, hi, ind):
        if lo == hi:
            return f'{ind}if = {{ limit = {{ {var} = {ns[lo]} }} {body(ns[lo])} }}\n'
        mid = (lo + hi) // 2
        return (f'{ind}if = {{\n{ind}\tlimit = {{ {var} > {ns[mid]} }}\n' + find(mid + 1, hi, ind + '\t')
                + f'{ind}}}\n{ind}else = {{\n' + find(lo, mid, ind + '\t') + f'{ind}}}\n')
    return find(0, len(ns) - 1, ind)


def tick_effect(bk, b, recipes, elec_tiers=(), opts=(), fold_techs=None, econ=(), goods_cost=None, auto_tiers=(),
                pair=None, short_check=''):
    """Every effect for one building type. All run in STATE scope.

    The state keeps how many of the building's levels run each recipe (pmr_lv_<i>_<b>, i = the
    recipe's position in vanilla's group, oldest first). The building's active recipe is the
    target (pmr_to_<b>); every level on another recipe still needs retooling. Each completed retool
    level moves one level, oldest recipe first, onto the target. A newer recipe arriving mid-retool
    only changes the target: levels already moved keep their recipe until retooled again.
    Each recipe's share of the levels picks the method active in that recipe's share group, so the
    building's goods are the level-weighted mix of its recipes in its own production figures.

    Method-count rework (Pat 2026-11-10): the shares no longer pick share methods; pmr_frame_<b> (frames.py) turns them
    into a frame and "less" modifiers. The target lives in pmr_to_<b> alone: the recipe group's method is the frame."""
    k = len(recipes)
    fold_techs = fold_techs or {}
    slots = list(enumerate(priv_slots(b), 1))
    # The blend members, each with one share group (pmg_pmr_share_<b>_<j>): recipe i is member i, or with the split
    # (SPLIT_AUTOMATION) each plain recipe and each automation method, over the retool targets (pairs) using it.
    split = pair if pair and pair.get('split') else None
    bm = split['members'] if split else [(i, [i], 'recipe') for i in range(1, k + 1)]
    nb = len(bm)
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
        # the building runs r: its pure frame, or r is the target (a blended building runs a union frame)
        return (f'OR = {{ is_production_method_active = {{ building_type = {bk} production_method = {r.key} }} '
                f'var:{v("pmr_to")} ?= {recipes.index(r) + 1} }}')

    def on_index(var, body, ind='\t'):
        """body(i) for the recipe whose index is held in var (a binary search from LOOKUP_FROM recipes on)."""
        return lookup(f'var:{v(var)}', list(range(1, k + 1)), body, ind)

    def setv(name, value):
        return f'set_variable = {{ name = {v(name)} value = {value} }}'

    def chg(name, op, value):
        return f'change_variable = {{ name = {v(name)} {op} = {value} }}'

    # the target whose pure frame the building runs now (history's, a new building's), 0 if none
    o.append(f'pmr_running_{b} = {{\n\t{setv("pmr_run", 0)}\n')
    for i, r in enumerate(recipes, 1):
        o.append(f'\t{"if" if i == 1 else "else_if"} = {{ limit = {{ is_production_method_active = {{ building_type = {bk} '
                 f'production_method = {r.key} }} }} {setv("pmr_run", i)} }}\n')
    o.append('}\n\n')

    # all levels on one recipe (the one in pmr_to)
    o.append(f'pmr_reset_levels_{b} = {{\n'
             + ''.join(f'\tset_variable = {{ name = {lv(i)} value = 0 }}\n' for i in range(1, k + 1))
             + on_index('pmr_to', lambda i: f'set_variable = {{ name = {lv(i)} value = var:{v("pmr_level")} }}')
             + '\t# the government\'s levels are placed again by pmr_sync_gov_<b>\n'
             + ''.join(f'\tset_variable = {{ name = {lvg(i)} value = 0 }}\n' for i in range(1, k + 1))
             + '\t# the level accounting runs in full again (S3)\n'
             f'\tif = {{ limit = {{ has_variable = pmr_fp_{b} }} remove_variable = pmr_fp_{b} }}\n'
             + '}\n\n')

    # The blend: each member's share of the levels, in steps of 1 / SHARE_STEPS. Members other than the target's are
    # rounded to the nearest step, oldest first and never past the whole; the target's takes what is left, so the
    # shares always add up to exactly SHARE_STEPS steps. pmr_frame_<b> turns them into a frame and "less" modifiers.
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
    if split:
        # S2: the target's recipe member (pmr_tom_<b>, 0 for no target) found once, so each member tests it
        # rather than every pair it is in (a ranch's 36 tests, now 7 and one per member)
        if len(rec_of) != sum(len(idxs) for _, idxs, grp in bm if grp == 'recipe'):
            raise SystemExit(f'{bk}: a retool target in two recipe members')
        o.append(f'\t{setv("pmr_tom", 0)}\n' + on_index('pmr_to', lambda i: setv("pmr_tom", rec_of[i])))
    for i, idxs, grp in bm:
        if grp != 'recipe':
            continue
        on_target = (f'var:{v("pmr_tom")} = {i}' if split else
                     f'var:{v("pmr_to")} = {idxs[0]}' if len(idxs) == 1 else
                     'OR = { ' + ' '.join(f'var:{v("pmr_to")} = {x}' for x in idxs) + ' }')
        o.append(f'\tif = {{\n\t\tlimit = {{ NOT = {{ {on_target} }} }}\n' + step(i, 'pmr_ncum') + '\t}\n')
    if split:
        o.append(lookup(f'var:{v("pmr_tom")}', sorted(set(rec_of.values())),
                        lambda j: f'{setv(f"pmr_n_{j}", SHARE_STEPS)} {chg(f"pmr_n_{j}", "subtract", "var:" + v("pmr_ncum"))}'))
    else:
        o.append(on_index('pmr_to', lambda i: f'{setv(f"pmr_n_{rec_of[i]}", SHARE_STEPS)} '
                                              f'{chg(f"pmr_n_{rec_of[i]}", "subtract", "var:" + v("pmr_ncum"))}'))
    # automation members (the split): each its own share, rounded, the methods of one group never past the whole
    for grp in dict.fromkeys(grp for _, _, grp in bm if grp != 'recipe'):
        o.append(f'\t# {grp}\n\t{setv("pmr_gcum", 0)}\n'
                 + ''.join(step(i, 'pmr_gcum') for i, _, g2 in bm if g2 == grp))
    # R8-1: the shares now match the levels. Until pmr_mix_<b> changes them a quiet monthly tick can skip the blend.
    o.append(f'\tset_variable = pmr_bok_{b}\n')
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
    gov_ladder = highest(list(range(1, steps + 1)),
                         lambda n: f'b:{bk} = {{ country_ownership_fraction >= {fmt(n * GOV_FRACTION_STEP - GOV_FRACTION_STEP / 2)} }}',
                         lambda n: setv("pmr_gov_frac", fmt(n * GOV_FRACTION_STEP) if n else 0))
    if VALUE_READS == 2:   # the share as a plain number, to the same step
        gov_ladder = (f'\tset_variable = {{ name = {v("pmr_gov_frac")} value = b:{bk}.country_ownership_fraction }}\n'
                      f'\t{chg("pmr_gov_frac", "multiply", steps)}\n'
                      f'\tround_variable = {{ name = {v("pmr_gov_frac")} nearest = 1 }}\n'
                      f'\t{chg("pmr_gov_frac", "divide", steps)}\n')
    elif VALUE_READS == 1:
        gov_ladder += ('\tif = {\n\t\tlimit = { has_global_variable = pmr_dv_on }\n'
                       f'\t\tset_variable = {{ name = pmr_dv value = b:{bk}.country_ownership_fraction }}\n'
                       f'\t\tset_variable = {{ name = pmr_dl value = var:{v("pmr_gov_frac")} }}\n\t\tpmr_dv_cmp_gov = yes\n\t}}\n')
    o.append(f'pmr_read_gov_{b} = {{\n' + gov_ladder)
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
             + (''.join(f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_to")} = {i} }}\n' + place(i, '\t\t\t') + '\t\t}\n'
                        for i in range(1, k + 1)) if k < LOOKUP_FROM else
                on_index('pmr_to', lambda i: ' '.join(x.strip() for x in place(i, '').splitlines()), '\t\t'))
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
    mine = f'OR = {{ owner = {{ is_player = yes }} has_variable = pmr_abroad_{b} }}'   # the player's, as log() reads it

    def release(rbx, side, keep=''):
        seen = 'pmr_seen_gov' if side.startswith('gov') else 'pmr_seen_priv'
        built = v('pmr_retool_built_' + side)
        # A crewed private one may still have staff when it goes: logged (flush_log) in case that hangs; padded
        # only for the player's, at home or abroad.
        crumb = '' if side.startswith('gov') else f"\t\t{flush_log('RELEASE', rbx, f';built=[THIS.Var({built!r}).GetValue|0]', mine)}\n"
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
    # In three parts since S3 (performance review 3; Pat, 2026-10-19 02:35Z): pmr_count_retool_<b> reads the sites
    # and counts their new levels (pmr_conv_<side>_<b>) every tick; pmr_progress_<b> moves the levels, inside the
    # level accounting a quiet tick skips (pmr_recount_<b>); pmr_release_retool_<b> removes finished sites every tick.
    # The three share nothing with the level accounting but those counts, so the order between them is free.
    def each_pass(conv, gov):
        # S2: one test of the count per pass; every convert in it tests the count first, and none runs at 0
        return (f'\tif = {{\n\t\tlimit = {{ var:{v(conv)} > 0 }}\n'
                + ''.join('\t' + x for x in ''.join(convert(conv, i, gov) for i in range(1, k + 1)).splitlines(True))
                + '\t}\n')
    o.append(f'pmr_count_retool_{b} = {{\n\tpmr_read_retool_{b} = yes\n'
             + (''.join(crew(j, rbx) for j, rbx in slots) if RETOOL_CREW else '')
             + count('gov') + count('priv') + '}\n\n')
    o.append(f'pmr_progress_{b} = {{\n'
             + f'\t{setv("pmr_gain", 0)}\n\t{setv("pmr_ggain", 0)}\n'
             + each_pass('pmr_conv_gov', True)
             + each_pass('pmr_conv_priv', False)
             + f'\t{chg("pmr_conv_priv", "add", "var:" + v("pmr_conv_gov"))}\n'
             + each_pass('pmr_conv_priv', False)
             + each_pass('pmr_conv_priv', True)
             + on_index('pmr_to', lambda i: f'change_variable = {{ name = {lv(i)} add = var:{v("pmr_gain")} }} '
                                            f'change_variable = {{ name = {lvg(i)} add = var:{v("pmr_ggain")} }}')
             + '}\n\n')
    o.append(f'pmr_release_retool_{b} = {{\n'
             + ''.join(release(rbx, f'priv{j}', keep_crew(j) if RETOOL_CREW else '') for j, rbx in slots)
             + release(rbg, 'gov')
             # the abroad site stands while the player's government still has room (pmr_split_retool_<b>)
             + release(rbga, 'gova', f'NOT = {{ AND = {{ has_variable = pmr_abroad_{b} has_variable = pmr_retool_open_gov_{b} }} }} ')
             + totals() + '}\n\n')

    # Shares for the bar and the blend, the levels still to retool, and p (share on the target).
    o.append(f'pmr_mix_{b} = {{\n'
             # review 8, R8-1: the shares may change, so the next blend, trade-off read and frame pick run in full
             f'\tif = {{ limit = {{ has_variable = pmr_bok_{b} }} remove_variable = pmr_bok_{b} }}\n'
             f'\tif = {{ limit = {{ has_variable = pmr_fok_{b} }} remove_variable = pmr_fok_{b} }}\n'
             + (f'\tif = {{ limit = {{ has_variable = pmr_xok_{b} }} remove_variable = pmr_xok_{b} }}\n' if opts else '')
             + on_index('pmr_to', lambda i: setv("pmr_lv_to", "var:" + lv(i)))
             + f'\t{setv("pmr_need", "var:" + v("pmr_level"))}\n'
             f'\t{chg("pmr_need", "subtract", "var:" + v("pmr_lv_to"))}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_need")} < 0 }} {setv("pmr_need", 0)} }}\n'
             f'\t{chg("pmr_need", "multiply", "pmr_retool_levels_per_level")}\n'
             f'\t{setv("pmr_p", "var:" + v("pmr_lv_to"))}\n'
             f'\t{chg("pmr_p", "divide", "var:" + v("pmr_level"))}\n'
             + ''.join(f'\t{setv(f"pmr_sh_{i}", "var:" + lv(i))}\n'
                       f'\t{chg(f"pmr_sh_{i}", "divide", "var:" + v("pmr_level"))}\n' for i in range(1, k + 1))
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
             f'\tif = {{ limit = {{ has_variable = pmr_rq_{b} }} remove_variable = pmr_rq_{b} }}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_room_gov")} > 0 }} set_variable = pmr_retool_open_gov_{b} }}\n'
             f'\telse_if = {{ limit = {{ has_variable = pmr_retool_open_gov_{b} }} remove_variable = pmr_retool_open_gov_{b} }}\n'
             '\t# Abroad no script effect queues a construction for the player\'s government: the upgrade button\n'
             '\t# expands a site that stands (Building.QueueConstruction). So while its government has room the\n'
             '\t# tick keeps one, a level owned by the player\'s government that counts as used (pmr_seen_gov).\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_abroad_{b} has_variable = pmr_retool_open_gov_{b} has_global_variable = pmr_player '
             f'NOT = {{ has_building = {rbga} }} NOT = {{ exists = b:{rbga} }} }}\n'
             f'\t\tcreate_building = {{\n\t\t\tbuilding = {rbga}\n'
             '\t\t\tadd_ownership = { country = { country = global_var:pmr_player levels = 1 } }\n\t\t}\n'
             '\t\tpmr_urb_check = yes   # the state Buildings tab\'s own list\n'
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
    # that needs electricity counts only while the state has a power plant (pmr_elec, SUPPLY's flag).
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
        if (bk, r.key) in frames.GATES:
            # a locked frame (frames.LOCK_PURE) fails the engine's check unless it runs: PMR's gate, those technologies in it
            can = frames.can_activate(bk, r.key, owner_techs)
        elif owner_techs:   # the technologies first: they rule out most of a split type's pairs before the engine's check
            can = (f'AND = {{ owner = {{ '
                   + ' '.join(f'has_technology_researched = {t}' for t in owner_techs) + f' }} {can} }}')
        if with_abroad and abroad(r, i):
            can = f'OR = {{ {can} {abroad(r, i)} }}'
        if i in elec_tiers:
            can = f'AND = {{ {can} var:pmr_elec = 1 }}'
        if econ and rails(econ[i - 1][0]):
            can = f'AND = {{ {can} var:pmr_rail = 1 }}'
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
    scans = best_effect(f"pmr_newest_{b}", "pmr_new_now", True) + best_effect(f"pmr_hbest_{b}", "pmr_hbest_now", False)
    o.append(scans)
    # RESEARCH_MAP: every technology and law the scans can ask about: the ones their text names, and the ones the game's
    # own check asks for a method that stays unlocked (its unlocking_technologies)
    def own_gates(r):
        """the unlock keys of a recipe's own methods (its marker's, a pair's recipe and automation methods')"""
        for m in [r, getattr(r, 'base', None)] + list(getattr(r, 'opt', [])) + list(getattr(r, 'autos', [])):
            node = getattr(m, 'node', None)
            for n in (node.value if node is not None else []):
                if n.key and n.key.startswith(('unlocking_', 'disallowing_')):
                    yield n
    RESEARCH_TECHS[b] = sorted(set(re.findall(r'has_technology_researched = (\w+)', scans))
                               | {t for i, r in enumerate(recipes, 1) for t in techs_of(r, i)})
    RESEARCH_LAWS[b] = sorted(set(re.findall(r'has_law_or_variant = law_type:(\w+)', scans))
                              | {x for r in recipes for n in own_gates(r) if n.key.endswith('_laws') and n.is_block
                                 for x in pdx.items(n)})
    # a gate neither a technology nor a law nor fixed for the state (a power bloc's principle): such a type is scanned
    # at every technology, as before the map
    RESEARCH_OTHER[b] = sorted({n.key for r in recipes for n in own_gates(r)
                                if n.key not in ('unlocking_technologies', 'unlocking_laws', 'disallowing_laws',
                                                 'unlocking_geographic_regions', 'unlocking_production_methods')}
                               | ({'has_principle'} if 'has_principle' in scans else set()))
    o.append(profit_effect(bk, b, recipes, econ, goods_cost or {}, active, reach, setv, v, pair))


    def f(name, d=0):
        return f"[THIS.Var('{v(name)}').GetValue|{d}]"
    # blend: each member's share of the levels in steps of 1/SHARE_STEPS, as the tick set it (the frame and its sizes:
    # the FRAME line)
    mix = ';blend=' + '/'.join(f(f'pmr_n_{i}') for i in range(1, nb + 1))
    best = f";best={f('pmr_best_now')}" + mix
    split = mix + (f";gov_frac={f('pmr_gov_frac', 2)};gov_levels={f('pmr_gov_levels')}"
             f";share_gov={f('pmr_retool_gov')};share_priv={f('pmr_retool_priv')}"
             f";queued_gov={f('pmr_pending_gov')};queued_priv={f('pmr_pending_priv')}"
             f";room_gov={f('pmr_room_gov')};room_priv={f('pmr_room_priv')}"
             + ';gov_lv=' + '/'.join(f(f'pmr_lvg_{i}') for i in range(1, k + 1))
             + ';slots=' + '/'.join(f(f'pmr_retool_q_priv{j}') for j in range(1, RETOOL_SLOTS + 1))
             + (';crew=' + '/'.join(f(f'pmr_staff_priv{j}') for j in range(1, RETOOL_SLOTS + 1)) if RETOOL_CREW else '')
             + f";elec=[THIS.Var('pmr_elec').GetValue|0];rail=[THIS.Var('pmr_rail').GetValue|0]" + (f";elec_wait={f('pmr_elec_wait')}" if elec_tiers else '')
             + f";home_investors={f('pmr_inv_home')};pool=[THIS.Var('pmr_pool').GetValue|0]"
             + f";earn={f('pmr_earn')};ai_w={f('pmr_ai_w')}"
             + ";unemp=[THIS.Var('pmr_unemp').GetValue|0]")
    done = mix + f";queued_gov={f('pmr_pending_gov')};queued_priv={f('pmr_pending_priv')}"

    # S3, skip unchanged months (performance review 3; Pat, 2026-10-19 02:35Z). The level accounting
    # (pmr_recount_<b>: sync_levels, sync_gov, progress, mix) reads the building's level, the target, the
    # government's levels (pmr_read_gov_<b>), the new retool levels (pmr_count_retool_<b>) and the levels on each
    # recipe, all and the government's; it writes those levels and mix's shares, which nothing else writes but
    # pmr_reset_levels_<b> (it drops the fingerprint). Run again on what it left with no new retool level and a
    # target, it changes nothing: the levels already add up to the building's, the government's to its own. So as
    # it finishes it keeps what it read (pmr_fp_*_<b>), and a tick that finds every value the same and no new retool
    # level skips it. A retool level finished on any path is a new level here (pmr_conv_*). Mix is in it: it reads
    # nothing else.
    # Review 8, R8-3: the levels on each recipe (pmr_lv_<i>, pmr_lvg_<i>) are no longer in the fingerprint. Only the
    # accounting itself writes them (sync_levels, sync_gov, progress), and pmr_reset_levels_<b>, which drops the
    # fingerprint, so a copy taken as it finished always matched (2 x recipes comparisons a tick, and as many state
    # variables a building). Anything that writes them outside pmr_recount_<b> must drop pmr_fp_<b> too. Test builds
    # still check them (SKIP_MISS, pmr_skip_check_<b>).
    fp = [('pmr_level', 'pmr_fp_level'), ('pmr_to', 'pmr_fp_to'), ('pmr_gov_levels', 'pmr_fp_gl')]
    same = (f'has_variable = pmr_fp_{b} var:{v("pmr_conv_gov")} <= 0 var:{v("pmr_conv_priv")} <= 0 var:{v("pmr_to")} > 0 '
            + ' '.join(f'var:{v(a)} = var:{v(s)}' for a, s in fp))
    # (an older save keeps its pmr_fp_lv/lvg copies, unread: removing them names variables a new game never sets,
    # which error.log lists at every load)
    o.append(f'pmr_recount_{b} = {{\n\tpmr_sync_levels_{b} = yes\n\tpmr_sync_gov_{b} = yes\n\tpmr_progress_{b} = yes\n'
             f'\tpmr_mix_{b} = yes\n\tset_variable = pmr_fp_{b}\n'
             + ''.join(f'\t{setv(s, "var:" + v(a))}\n' for a, s in fp) + '}\n\n')
    if not RELEASE:
        # The check (test builds): a player's building that skipped SKIP_CHECK ticks in a row runs the accounting
        # anyway and logs SKIP_MISS for each value it left different from what the skipped ticks had left.
        splitting = bool(pair and pair.get('split'))
        outs = ([f'pmr_lv_{i}' for i in range(1, k + 1)] + [f'pmr_lvg_{i}' for i in range(1, k + 1)]
                + ['pmr_lv_to', 'pmr_need', 'pmr_p', 'pmr_ui_retooling']
                + [f'pmr_sh_{i}' for i in range(1, k + 1)] + [f'pmr_lvp_{i}' for i in range(1, k + 1)]
                + [f'pmr_ash_{a}' for a in range(1, len(auto_tiers) + 1)]
                + ([f'pmr_rs_{j}' for j, _, _ in bm]
                   + [f'pmr_rl{s}_{j}' for j, _, grp in bm if grp == 'recipe' for s in ('vg', 'vp')] if splitting else []))
        o.append(f'pmr_skip_check_{b} = {{\n'
                 + ''.join(f'\t{setv("pmr_sm" + n[3:], "var:" + v(n))}\n' for n in outs)
                 + f'\tpmr_recount_{b} = yes\n'
                 + ''.join(f'\tif = {{ limit = {{ NOT = {{ var:{v(n)} = var:{v("pmr_sm" + n[3:])} }} }} '
                           'debug_log = "PMR;rec=SKIP_MISS;date=[TimeKeeper.GetCurrentDate.GetString];'
                           'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting];'
                           f'building={bk};var={n};skipped={f("pmr_sm" + n[3:], 3)};full={f(n, 3)}" }}\n' for n in outs)
                 + ''.join(f'\tremove_variable = {v("pmr_sm" + n[3:])}\n' for n in outs) + '}\n\n')

    def sk_add(name):
        # the player's monthly SKIP line counts (pmr_skip_report)
        return (f'owner = {{ if = {{ limit = {{ NOT = {{ has_variable = {name} }} }} set_variable = {{ name = {name} value = 0 }} }} '
                f'change_variable = {{ name = {name} add = 1 }} }}')
    # perf review 5, S-7: the sites are read and released only where one can stand (the gate), or until a gate-less
    # state has read none built and none pending (pmr_rq_<b>, cleared where the gate is set)
    sites_may = f'OR = {{ has_variable = pmr_retool_gate_{b} NOT = {{ has_variable = pmr_rq_{b} }} }}'
    recount = (f'\tpmr_read_gov_{b} = yes\n\tif = {{ limit = {{ {sites_may} }} pmr_count_retool_{b} = yes }}\n'
               '\t# S3: the level accounting only when something it reads has changed (pmr_recount_<b>)\n'
               f'\tif = {{\n\t\tlimit = {{ NOT = {{ AND = {{ {same} }} }} }}\n\t\tpmr_recount_{b} = yes\n'
               + ('' if RELEASE else
                  f'\t\tif = {{ limit = {{ owner = {{ is_player = yes }} }} {sk_add("pmr_sk_ran")} {setv("pmr_skn", 0)} }}\n')
               + '\t}\n'
               + ('' if RELEASE else
                  f'\telse_if = {{\n\t\tlimit = {{ owner = {{ is_player = yes }} }}\n'
                  f'\t\tif = {{ limit = {{ NOT = {{ has_variable = {v("pmr_skn")} }} }} {setv("pmr_skn", 0)} }}\n'
                  f'\t\t{chg("pmr_skn", "add", 1)}\n'
                  f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_skn")} >= {SKIP_CHECK} }}\n\t\t\t{setv("pmr_skn", 0)}\n'
                  f'\t\t\tpmr_skip_check_{b} = yes\n\t\t\t{sk_add("pmr_sk_checked")}\n\t\t}}\n'
                  f'\t\telse = {{ {sk_add("pmr_sk_skip")} }}\n\t}}\n')
               + f'\tif = {{\n\t\tlimit = {{ {sites_may} }}\n\t\tpmr_release_retool_{b} = yes\n'
               f'\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_retool_gate_{b} }} var:{v("pmr_retool_built")} = 0 '
               f'var:{v("pmr_pending")} = 0 }} set_variable = pmr_rq_{b} }}\n\t}}\n')

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
             '\tpmr_supply_once = yes\n'
             + ''.join(f'\tif = {{ limit = {{ var:{v("pmr_level")} >= 1 }} set_variable = {{ name = {flag} value = 1 }} pmr_lsup_now = yes }}'
                       '  # SUPPLY: this building is the state\'s\n' for sbk, flag in SUPPLY if sbk == bk)
             + '\t# Abroad: the player (global_var:pmr_player) owns levels here, in a state another country owns.\n'
             f'\tif = {{\n\t\tlimit = {{ has_global_variable = pmr_player NOT = {{ owner = global_var:pmr_player }} '
             f'b:{bk} = {{ levels_owned_by_country = {{ target = global_var:pmr_player value >= 1 }} }} }}\n'
             + (f'\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_abroad_{b} }} has_variable = pmr_nel_{b} }} '
                f'remove_variable = pmr_nel_{b} }}  # RESEARCH_MAP: the player\'s technologies count from here, so the scan runs\n'
                if RESEARCH_MAP else '')
             + f'\t\tset_variable = {{ name = pmr_abroad_{b} value = 1 }}  # a value, so the Owners list can read it\n'
             '\t\tset_variable = { name = pmr_abroad_any days = 62 }\n\t}\n'
             f'\telse_if = {{ limit = {{ has_variable = pmr_abroad_{b} }} remove_variable = pmr_abroad_{b}'
             + (f' if = {{ limit = {{ has_variable = pmr_nel_{b} }} remove_variable = pmr_nel_{b} }}' if RESEARCH_MAP else '')
             + ' }\n'
             f'\tpmr_best_{b} = yes\n'
             f'\tif = {{ limit = {{ has_variable = pmr_abroad_{b} }} pmr_hbest_{b} = yes }}\n'
             f'\telse = {{ {setv("pmr_hbest_now", "var:" + v("pmr_best_now"))} }}\n'
             '\t# First sight (game start, a new building, or a save from before the level mix): every\n'
             '\t# level runs the recipe the building runs now. Retool levels already built\n'
             '\t# count for nothing.\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = pmr_mix_{b} }} }}\n'
             f'\t\tset_variable = pmr_mix_{b}\n'
             f'\t\tif = {{ limit = {{ has_variable = {v("pmr_retooling")} }} remove_variable = {v("pmr_retooling")} }}\n'
             # the frame's sizes start again: a building seen for the first time carries no "less" modifier
             + (frames.clear_vars(FRAMES[bk], '\t\t') if bk in FRAMES else '') +
             f'\t\t{setv("pmr_best", "var:" + v("pmr_best_now"))}\n'
             # the pure frame history (or the game, for a new building) started it on; none: the best it can run
             f'\t\tpmr_running_{b} = yes\n'
             f'\t\t{setv("pmr_to", "var:" + v("pmr_run"))}\n'
             f'\t\tif = {{ limit = {{ var:{v("pmr_to")} = 0 }} {setv("pmr_to", "var:" + v("pmr_best_now"))} }}\n'
             f'\t\tif = {{ limit = {{ var:{v("pmr_to")} = 0 }} {setv("pmr_to", 1)} }}\n'
             f'\t\tpmr_reset_levels_{b} = yes\n'
             f'\t\tpmr_read_retool_{b} = yes\n'
             f'\t\t{setv("pmr_seen_gov", "var:" + v("pmr_retool_built_gov"))}\n'
             f'\t\t{setv("pmr_seen_priv", "var:" + v("pmr_retool_built_priv"))}\n'
             '\t\t# Newly constructed: built with the newest recipe the owner has, at no retooling cost (the frame follows).\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = {v("pmr_new_build")} var:{v("pmr_best_now")} > 0 '
             f'NOT = {{ var:{v("pmr_to")} = var:{v("pmr_best_now")} }} }}\n'
             f'\t\t\t{setv("pmr_to", "var:" + v("pmr_best_now"))}\n'
             f'\t\t\tpmr_reset_levels_{b} = yes\n'
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
             '\t\t# Abroad, beyond what the host can run (logged): the target moves all the same.\n'
             f'\t\tif = {{ limit = {{ var:{v("pmr_best_now")} > var:{v("pmr_hbest_now")} }} '
             f'{log("ABROAD", bk, b, k, extra=best + ";host_best=" + f("pmr_hbest_now"))} }}\n'
             '\t\t# The switch (method-count rework: the target is pmr_to alone, the recipe group runs the frame). The\n'
             '\t\t# levels keep the recipes they run; every level not on the new target is now to retool.\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ NOT = {{ var:{v("pmr_to")} = var:{v("pmr_best_now")} }} }}\n'
             f'\t\t\t{setv("pmr_to", "var:" + v("pmr_best_now"))}\n'
             f'\t\t\tset_variable = {v("pmr_switched")}\n\t\t}}\n\t}}\n'
             f'\t{setv("pmr_best", "var:" + v("pmr_best_now"))}\n')

    tail = (recount
             # review 8, R8-1: a monthly tick whose shares are those of the last blend (pmr_bok_<b>: no pmr_mix_<b>
             # since) skips it; every event tick (built, expanded, method changed, research) and a new building still
             # on its start method run it in full
             + f'\tif = {{\n\t\tlimit = {{ OR = {{ NOT = {{ has_variable = pmr_month }} NOT = {{ has_variable = pmr_bok_{b} }} }} }}\n'
             f'\t\tpmr_blend_{b} = yes\n\t}}\n'
             + (opts_call(b, any(mode == 'market' for _, _, mode, *_ in opts)) if opts else '')
             # the frames and their "less" sizes (frames.py): every event tick (an AI's or the game's switch is put back
             # at once), and a monthly one whose shares moved since (pmr_mix_<b>, pmr_opts_<b> drop pmr_fok_<b>)
             + f'\tif = {{ limit = {{ NOT = {{ AND = {{ has_variable = pmr_month has_variable = pmr_fok_{b} }} }} }} pmr_frame_{b} = yes }}\n'
             + short_check +
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
             '')
    if QUIET_TICK:
        # QUIET_TICK: an AI building's monthly update with nothing open, queued or moved since its last accounting.
        # Every step after the ownership read tests one of these and would skip its part; the trade-off step keeps
        # its own turn. The player's buildings always take the steps one by one (their counts and logs sit there).
        rg = f'\tpmr_read_gov_{b} = yes\n'
        if not tail.startswith(rg):
            raise SystemExit('QUIET_TICK: pmr_tick_body tail does not start with the ownership read')
        quiet = (f'has_variable = pmr_month NOT = {{ has_variable = pmr_retool_gate_{b} }} has_variable = pmr_rq_{b} '
                 f'has_variable = pmr_bok_{b} has_variable = pmr_fok_{b} {same} NOT = {{ var:{v("pmr_need")} > 0 }} '
                 f'NOT = {{ has_variable = {v("pmr_retooling")} }} NOT = {{ has_variable = {v("pmr_switched")} }} '
                 'NOT = { owner = { is_player = yes } }')
        oc = opts_call(b, any(mode == 'market' for _, _, mode, *_ in opts)) if opts else ''
        # the trade-off step drops pmr_fok_<b> when a share moved: the frame then follows at once, as in the full tail
        if oc:
            oc += f'\tif = {{ limit = {{ NOT = {{ has_variable = pmr_fok_{b} }} }} pmr_frame_{b} = yes }}\n'
        tail = (rg + f'\tif = {{\n\t\tlimit = {{ {quiet} }}\n' + ''.join('\t' + ln for ln in oc.splitlines(True))
                + ('' if RELEASE else '\t\tpmr_qt_count = yes\n')
                + '\t}\n\telse = {\n' + ''.join('\t' + ln if ln.strip() else ln for ln in tail[len(rg):].splitlines(True)) + '\t}\n')
    o.append(tail + '}\n\n')
    # Country scope: the country's totals for the Buildings tab row (its recipe bar and upgrade
    # button). Recomputed after each single tick, and once for all building types after the ticks that
    # run state by state (pmr_bulk; see pmr_c_sum_all). The tab also lists buildings abroad that the
    # country or its investors own levels in (Pat's cotton plantations in the East India Company's
    # states, 2026-10-13), so a player's bar counts those buildings too, whole, as their own bars do.
    # Only a player's (pmr_c_viewer): it scans every state in the world. The upgrade button's room stays domestic.
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
             '\tif = {\n\t\tlimit = { pmr_c_viewer = yes }\n'
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
    # Country scope: drop the totals above from a country no player views (pmr_c_sum_all). Saves from before review 9
    # carry a copy for every country from game start, about 380,000 variables by 1855 (q69), none ever read: every
    # reader is the player's (GUI GetPlayer, pmr_switch_<b> is_player). Each name is checked, as an older version may
    # have set fewer.
    c_all = (['level', 'need', 'room_gov'] + [f'lv_{i}' for i in range(1, k + 1)] + ['swm', 'sw', 'swd', 'swto', 'now', 'swg']
             + [f'sh_{i}' for i in range(1, k + 1)] + [f'rs_{j}' for j, idxs, grp in (bm if split else []) if grp == 'recipe']
             + ['retooling'])
    gone = [f'pmr_c_{n}_{b}' for n in c_all] + [f'pmr_cf_{n}_{b}' for n in cnames]
    o.append(f'pmr_c_clear_{b} = {{\n'
             + ''.join(f'\tif = {{ limit = {{ has_variable = {g} }} remove_variable = {g} }}\n' for g in gone)
             + '}\n\n')

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
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_retool_open_gov_{b} NOT = {{ has_variable = pmr_abroad_{b} }} b:{bk} ?= {{ level >= 1 }} }}\n'
             f'\t\t{setv("pmr_q", "var:" + v("pmr_room_gov"))}\n'
             f'\t\t{log("GOV_QUEUE", bk, b, k, extra=";queueing=" + f("pmr_q"))}\n'
             f'\t\twhile = {{\n\t\t\tlimit = {{ var:{v("pmr_q")} > 0 }}\n'
             f'\t\t\tstart_building_construction = {rbg}\n'
             f'\t\t\t{chg("pmr_q", "subtract", 1)}\n\t\t}}\n'
             f'\t\tremove_variable = {v("pmr_q")}\n'
             f'\t\tpmr_tick_{b} = yes\n\t\tpmr_urb_check = yes   # the state Buildings tab\'s own list\n\t}}\n}}\n\n')
    return ''.join(o)


def profit_axes(k, pair=None):
    """Option index i (1..k) -> its place on each axis, the recipe first: (i,) for a type without automation pairs; with
    the split (recipe ri, automation option a) -> (ri, its method's place in each automation group), groups in vanilla's
    order, as automation_options builds them (a - 1 in mixed radix, the last group fastest)."""
    if not (pair and pair.get('split')):
        return {i: (i,) for i in range(1, k + 1)}
    opts = pair['options']
    radix = [len(dict.fromkeys(o[g].key for o in opts)) for g in range(len(opts[0]))] if opts and opts[0] else []
    out = {}
    for (ri, a), x in pair['index'].items():
        rest, place = a - 1, []
        for n in reversed(radix):
            place.append(rest % n)
            rest //= n
        out[x] = (ri, *reversed(place))
    assert sorted(out) == list(range(1, k + 1)), 'profit_axes: the pairs are not the options 1..k'
    return out


def axis_weights(k, pair, axes):
    """The option at given places, back from profit_axes: index = (recipe - 1) x na + 1 + the sum of each automation
    place x its weight (pairs are numbered recipe first, then automation option a, a - 1 in mixed radix). Returns
    (na, weights); checked against every option."""
    nd = len(axes[1])
    if nd == 1:
        na, wts = 1, []
    else:
        opts = pair['options']
        radix = [len(dict.fromkeys(o[g].key for o in opts)) for g in range(len(opts[0]))]
        na = len(opts)
        wts = [math.prod(radix[j + 1:]) for j in range(len(radix))]
    for x, ax in axes.items():
        if x != (ax[0] - 1) * na + 1 + sum(p * w for p, w in zip(ax[1:], wts)):
            raise SystemExit(f'axis_weights: option {x} sits at {ax}, which the weights {na}, {wts} do not give back')
    return na, wts


def profit_effect(bk, b, recipes, econ, goods_cost, active, reach, setv, v, pair=None):
    """State scope: pmr_profit_<b>, the profit calculation, and pmr_best_<b>, which makes its pick the target.
    The interface Company Culture reads (fixed 2026-10-18; the best-methods windows), recipe index i as everywhere:
      pmr_rg_<i>_<b>     goods margin per level per week at the state's prices (outputs minus inputs, GBP) x pmr_thr
      pmr_rw_<i>_<b>     wages per level per week: wage units x pmr_wage / 10,000
      pmr_rm_<i>_<b>     pmr_rg - pmr_rw, the profit per level per week
      pmr_rav_<i>_<b>    1 while recipe i can become the target here (pmr_newest_<b>'s rule) and this run priced it:
                         the reference, or one runnable step from it (Pat 13:09Z); 0 otherwise, its figures an earlier run's
      pmr_rveto_<i>_<b>  1 while recipe i needs more of an input than the default and its price is at the cap
      pmr_pbest_<b>      the pick: the best pmr_rm of the runnable, unvetoed recipes, the default unless another beats
                         it by SWITCH_GAIN; 0 if none
      pmr_swg_<b>        the pick's gain over the default (0.3 = 30% more profit), pmr_swr_<b> the bar's points a month
      pmr_prm_<b>        the pick's pmr_rm (the panel's pick row)
    Pat, 2026-10-19 02:32Z ("why are the pm options negative but the buildings profitable?", agreed 02:43Z): the wage is
    the one the state's own building of the type pays (pmr_wage, from pmr_wage_<b>), and the goods margins are x the
    building's throughput (pmr_thr, 1 + the modifiers throughput_keys reads; the company throughput bonus is left out),
    so the figures follow the building's books.
    Pat, 2026-10-18 17:14Z: the pick decides new builds and retooling, and must not cost the game speed. So the
    calculation runs only when pmr_best_<b> finds a reason: no pick yet, the newest runnable recipe changed
    (research, electricity, the player's know-how abroad), a new building, its first monthly pulse (the setup pass
    runs before the market has prices), its re-check timer ran out
    (pmr_pchk_<b>, PROFIT_RECHECK_DAYS, spread over PROFIT_RECHECK_SPREAD so states don't all check on one day), or
    (Pat 02:43Z) a monthly pulse finds a good's price or the wage PRICE_MOVE off what the last run used (pmr_moved_<b>).
    Every other tick reads the cached pick."""
    k = len(recipes)
    newest = (f'\tpmr_newest_{b} = yes\n')
    if not econ or not PROFIT_TARGET:
        return f'pmr_best_{b} = {{\n{newest}\t{setv("pmr_best_now", "var:" + v("pmr_new_now"))}\n}}\n\n'
    # Pat 2026-10-19 13:09Z: the newest runnable recipe (pmr_newest_<b>) tests every recipe from the newest down, locked
    # ones first, so it runs only where it can have changed: the first time, in a research pass (pmr_research), and
    # when the state's electricity changed since (pmr_nel_<b>). The re-check timer catches anything else.
    # The state's local goods changed (pmr_lsup: electricity, transportation) also re-prices the options (pmr_pmv).
    scan = f'pmr_newest_{b} = yes set_variable = {{ name = pmr_nel_{b} value = var:pmr_lsup }}'
    newest = (f'\tif = {{ limit = {{ OR = {{ NOT = {{ has_variable = pmr_nel_{b} }} NOT = {{ has_variable = {v("pmr_new_now")} }} }} }} '
              f'{scan} }}\n'
              f'\telse_if = {{ limit = {{ NOT = {{ var:pmr_nel_{b} = var:pmr_lsup }} }} {scan} set_variable = pmr_pmv }}\n'
              f'\telse_if = {{ limit = {{ has_variable = pmr_research }} {scan} }}\n')
    xv = lambda name, i: f'{name}_{i}_{b}'   # noqa: E731
    cv = lambda name, op, x: f'change_variable = {{ name = {v(name)} {op} = {x} }}'   # noqa: E731
    top = fmt(1 + PRICE_LADDER[-1] / 100)
    goods = sorted({g for gd, _ in list(econ) + list((pair or {}).get('econ', {}).values())
                    for g in gd if goods_cost.get(g)})
    read_px = ''.join(f'\tif = {{ limit = {{ NOT = {{ has_variable = pmr_pxd_{g} }} }} pmr_price_{g} = yes '
                      f'set_variable = {{ name = pmr_pxd_{g} value = yes days = 1 }} }}\n' for g in goods)
    thr = ''.join(f'\t\tchange_variable = {{ name = pmr_thr add = scope:pmr_bk.modifier:{m} }}\n'
                  for m in THROUGHPUT_KEYS.get(bk, []))
    o = [f'pmr_profit_{b} = {{\n'
         '\t# a good\'s price is read once a day per state (pmr_pxd_<good>), as for the trade-offs. During game setup\n'
         '\t# (pmr_setup) the market has no prices yet, so the base price stands in until the first monthly pulse.\n'
         + ''.join(f'\tif = {{ limit = {{ has_global_variable = pmr_setup }} set_variable = {{ name = pmr_px_{g} value = 1 }} }}\n'
                   f'\telse_if = {{ limit = {{ NOT = {{ has_variable = pmr_pxd_{g} }} }} pmr_price_{g} = yes '
                   f'set_variable = {{ name = pmr_pxd_{g} value = yes days = 1 }} }}\n' for g in goods)
         + '\t# the state\'s own wage for the type (pmr_wage_<b>) and the building\'s throughput\n'
         f'\tpmr_wage_{b} = yes\n\tset_variable = {{ name = pmr_wage value = var:pmr_wg_{b} }}\n'
         '\tset_variable = { name = pmr_thr value = 1 }\n\tset_variable = { name = pmr_off value = 0 }\n'
         + (f'\tif = {{\n\t\tlimit = {{ exists = b:{bk} }}\n\t\tb:{bk} = {{ save_temporary_scope_as = pmr_bk }}\n{thr}'
            '\t\tchange_variable = { name = pmr_thr max = 0.1 }\n\t}\n' if thr else '')]
    # Pat 2026-10-19 13:09Z: "we should only evaluate unlocked items that are +/- from our current to save on calcs. If
    # our current is profitable we should never evaluate going back down." Each option's figures are a scripted effect of
    # their own (pmr_rmx_<i>_<b>), run for the reference (the default where it can run, else the last pick) and then only
    # for options one runnable step from it on every axis (recipe, each automation group: profit_axes), none below it while it
    # makes a profit, and only those the owner can run. Without a reference every option that can run is priced.
    axes = profit_axes(k, pair)
    nd = len(axes[1])
    pre = []
    for i, (gd, wu) in enumerate(econ, 1):
        body = [f'\tset_variable = {{ name = {xv("pmr_rg", i)} value = 0 }}\n']
        for g, q in sorted(gd.items()):
            if goods_cost.get(g):
                body.append(f'\tset_variable = {{ name = pmr_t value = var:pmr_px_{g} }}\n'
                            f'\tchange_variable = {{ name = pmr_t multiply = {fmt(q * goods_cost[g])} }}\n'
                            f'\tchange_variable = {{ name = {xv("pmr_rg", i)} add = var:pmr_t }}\n')
        body.append(f'\tchange_variable = {{ name = {xv("pmr_rg", i)} multiply = var:pmr_thr }}\n'
                    f'\tset_variable = {{ name = {xv("pmr_rw", i)} value = var:pmr_wage }}\n'
                    f'\tchange_variable = {{ name = {xv("pmr_rw", i)} multiply = {fmt(wu / 10000)} }}\n'
                    f'\tset_variable = {{ name = {xv("pmr_rm", i)} value = var:{xv("pmr_rg", i)} }}\n'
                    f'\tchange_variable = {{ name = {xv("pmr_rm", i)} subtract = var:{xv("pmr_rw", i)} }}\n'
                    f'\tchange_variable = {{ name = {xv("pmr_rm", i)} add = var:pmr_off }}\n')
        pre.append(f'pmr_rmx_{i}_{b} = {{\n' + ''.join(body) + '}\n\n')
    rmx = lambda i: f'pmr_rmx_{i}_{b} = yes'   # noqa: E731
    can = lambda i: (f'OR = {{ {active(recipes[i - 1])} {reach(i, True)} }}'   # noqa: E731
                     + (' var:pmr_rail = 1' if rails(econ[i - 1][0]) else ''))
    # a building's first run gives every option figures (0) for the cards to read
    o.append(f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {xv("pmr_rm", 1)} }} }}\n'
             + ''.join(f'\t\tset_variable = {{ name = {xv(n, i)} value = 0 }}\n'
                       for i in range(1, k + 1) for n in ('pmr_rg', 'pmr_rw', 'pmr_rm'))
             + '\t}\n')
    # the current pick: the last one, else PMR's target, else the recipe the building runs, else the oldest
    o.append(f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {v("pmr_pbest")} }} }}\n\t\t{setv("pmr_pbest", 1)}\n'
             f'\t\tif = {{ limit = {{ has_variable = {v("pmr_to")} var:{v("pmr_to")} > 0 }} '
             f'{setv("pmr_pbest", "var:" + v("pmr_to"))} }}\n'
             + ''.join(f'\t\telse_if = {{ limit = {{ {active(r)} }} {setv("pmr_pbest", i)} }}\n'
                       for i, r in enumerate(recipes, 1) if i > 1)
             + '\t}\n')
    now = v('pmr_best_now')
    # Pat 2026-10-19 19:30Z (New Jersey's shipyards made a profit on the newer recipe and were retooled down to a default
    # the game-start pick had set): "We should ONLY look to even go down a level of PM if we are unprofitable." The floor
    # (pmr_fl) is the highest option the building's levels run (pmr_lv_<i>_<b>). While the building isn't losing money
    # (its books, pmr_bpl_<b>, at 0 or more, or no reading yet), a default below the floor on any axis is raised to it at
    # once, and the box below prices nothing under the reference. A default a loss lowered (pmr_dn_<b>, switch_effect)
    # is left to finish its retooling.
    na, wts = axis_weights(k, pair, axes)
    # the solo gate (SOLO_GATE): nothing to choose between. The default is the newest recipe that can run here, so no
    # option at or above it on every axis can (the options' order follows the axes, axis_weights); the books are read
    # and at 0 or more, so nothing below it is priced; and this run priced no rival (pmr_nrv), which covers a newest
    # recipe not scanned since the owner changed
    solo = f'pmr_solo_{b}'
    solo_flag = '' if not SOLO_GATE else (
        '\t# the solo gate (SOLO_GATE): the default is the newest recipe that can run, the books are in the black, no rival priced\n'
        f'\tif = {{ limit = {{ has_variable = {solo} }} remove_variable = {solo} }}\n'
        f'\tif = {{\n\t\tlimit = {{ var:pmr_ref > 0 var:pmr_pk = var:pmr_ref var:pmr_nrv = 0 var:pmr_ok = 1 '
        f'has_variable = {now} var:{now} = var:pmr_ref has_variable = {v("pmr_new_now")} var:{v("pmr_new_now")} = var:pmr_ref '
        f'has_variable = pmr_bpl_{b} var:pmr_bpl_{b} >= 0 '
        f'NOR = {{ has_global_variable = pmr_setup has_variable = pmr_abroad_{b} owner = {{ is_player = yes }} }} }}\n'
        f'\t\tset_variable = {solo}\n\t}}\n')
    put = lambda name: lambda i: ' '.join(f'set_variable = {{ name = {name}_{d} value = {axes[i][d - 1]} }}'   # noqa: E731
                                          for d in range(1, nd + 1))
    o.append('\t# the floor and the raise (Pat 19:30Z)\n'
             '\tset_variable = { name = pmr_fl value = 0 }\n\tset_variable = { name = pmr_ok value = 0 }\n'
             f'\tif = {{\n\t\tlimit = {{ exists = b:{bk} has_variable = {v("pmr_level")} var:{v("pmr_level")} > 0 }}\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_lv_{k}_{b} }}\n'
             + ''.join(f'\t\t\t{"if" if i == k else "else_if"} = {{ limit = {{ var:pmr_lv_{i}_{b} > 0 }} '
                       f'set_variable = {{ name = pmr_fl value = {i} }} }}\n' for i in range(k, 0, -1))
             # game setup runs the first pick before the levels are counted: the method the building runs
             + '\t\t}\n\t\telse = {\n'
             + ''.join(f'\t\t\t{"if" if i == k else "else_if"} = {{ limit = {{ {active(recipes[i - 1])} }} '
                       f'set_variable = {{ name = pmr_fl value = {i} }} }}\n' for i in range(k, 0, -1))
             + '\t\t}\n\t}\n'
             f'\tif = {{ limit = {{ var:pmr_fl > 0 OR = {{ AND = {{ has_variable = pmr_bpl_{b} var:pmr_bpl_{b} >= 0 }} '
             f'NOR = {{ has_variable = pmr_bpl_{b} has_variable = pmr_bsx_{b} }} }} }} '
             'set_variable = { name = pmr_ok value = 1 } }\n'
             f'\tif = {{\n\t\tlimit = {{ var:pmr_fl > 0 has_variable = {now} var:{now} > 0 }}\n'
             + lookup('var:pmr_fl', list(range(1, k + 1)), put('pmr_fa'), '\t\t')
             + lookup(f'var:{now}', list(range(1, k + 1)), put('pmr_da'), '\t\t')
             + '\t\tif = {\n\t\t\tlimit = { OR = { '
             + ' '.join(f'var:pmr_da_{d} < var:pmr_fa_{d}' for d in range(1, nd + 1)) + ' } }\n'
             f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:pmr_ok = 1 NOT = {{ has_variable = pmr_dn_{b} }} }}\n'
             + ''.join(f'\t\t\t\tif = {{ limit = {{ var:pmr_da_{d} < var:pmr_fa_{d} }} '
                       f'set_variable = {{ name = pmr_da_{d} value = var:pmr_fa_{d} }} }}\n' for d in range(1, nd + 1))
             # the option at those places: (recipe - 1) x na + 1 + each automation place x its weight
             + '\t\t\t\tset_variable = { name = pmr_fu value = var:pmr_da_1 }\n'
             f'\t\t\t\tchange_variable = {{ name = pmr_fu subtract = 1 }}\n\t\t\t\tchange_variable = {{ name = pmr_fu multiply = {na} }}\n'
             '\t\t\t\tchange_variable = { name = pmr_fu add = 1 }\n'
             + ''.join(f'\t\t\t\tset_variable = {{ name = pmr_t value = var:pmr_da_{d} }}\n'
                       f'\t\t\t\tchange_variable = {{ name = pmr_t multiply = {wts[d - 2]} }}\n'
                       '\t\t\t\tchange_variable = { name = pmr_fu add = var:pmr_t }\n' for d in range(2, nd + 1))
             + lookup('var:pmr_fu', list(range(1, k + 1)),
                      lambda i: (f'if = {{ limit = {{ {can(i)} }} '
                                 f'if = {{ limit = {{ owner = {{ pmr_logged = yes }} }} debug_log = "PMR;rec=FLOOR;'
                                 'date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
                                 f'state=[THIS.GetState.GetNameNoFormatting];building={bk};from=[THIS.Var(\'{now}\').GetValue|0];'
                                 f'to={i};floor=[THIS.Var(\'pmr_fl\').GetValue|0];books=[THIS.Var(\'pmr_bpl_{b}\').GetValue|1]" }} '
                                 f'{setv("pmr_best_now", i)} {setv("pmr_sw", 0)} {setv("pmr_swd", 0)} {setv("pmr_swto", 0)} }}'),
                      '\t\t\t\t')
             + '\t\t\t}\n\t\t}\n'
             f'\t\telse_if = {{ limit = {{ has_variable = pmr_dn_{b} }} remove_variable = pmr_dn_{b} }}\n\t}}\n')
    # the reference (pmr_ref): the default where it can run here, else the last pick where it can, else none (0)
    ref_at = lambda c: (f'set_variable = {{ name = {xv("pmr_rav", c)} value = 0 }} '   # noqa: E731
                        f'if = {{ limit = {{ {can(c)} }} set_variable = {{ name = {xv("pmr_rav", c)} value = 1 }} '
                        f'set_variable = {{ name = pmr_ref value = {c} }} }}')
    o.append('\tset_variable = { name = pmr_ref value = 0 }\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = {now} }}\n'
             + lookup(f'var:{now}', list(range(1, k + 1)), ref_at, '\t\t') + '\t}\n'
             + '\tif = {\n\t\tlimit = { var:pmr_ref = 0 }\n'
             + lookup(f'var:{v("pmr_pbest")}', list(range(1, k + 1)), ref_at, '\t\t') + '\t}\n')
    # Pat 2026-10-19 17:23Z (Pommern's rye farm made +GBP 55 a week while PMR priced its method at -49 and moved it down):
    # the recipe figures leave out what the building's other groups add (its secondary group's liquor, ownership jobs),
    # so the reference is held to the books' profit per level (pmr_bpl_<b>, wage_effect) and every other option moves by
    # the same amount (pmr_off), keeping the recipes' differences.
    def calib(c):
        rm = xv('pmr_rm', c)
        return (f'if = {{ limit = {{ has_variable = pmr_bpl_{b} }} set_variable = {{ name = pmr_off value = var:pmr_bpl_{b} }} '
                f'change_variable = {{ name = pmr_off subtract = var:{rm} }} set_variable = {{ name = {rm} value = var:pmr_bpl_{b} }} }}')
    # its figures (pmr_rr) and the box around it: pmr_lo_<d>, pmr_hi_<d> on axis d, none below it while it makes a profit
    # (the books at 0 or more, pmr_ok)
    # q58 (the q57 observer run: Britain's sugar mills stayed on ox-driven rollers to 1849 where q51's vanilla AI had them
    # on steam evaporation by 1842): a step is to the nearest place on the axis whose option can run here, past locked
    # ones, as sugar's steam evaporation (fractional distillation) sits beyond the vacuum pan (watertube boiler)
    at = {ax: i for i, ax in axes.items()}

    def edge(c, d, way):
        p, name = axes[c][d - 1], ('pmr_hi' if way > 0 else 'pmr_lo')
        js, q = [], p + way
        while (*axes[c][:d - 1], q, *axes[c][d:]) in at:
            js.append((q, at[(*axes[c][:d - 1], q, *axes[c][d:])]))
            q += way
        out = f'set_variable = {{ name = {name}_{d} value = {p + way} }}'
        if len(js) > 1:
            out += ' ' + ' '.join(f'{"if" if n == 0 else "else_if"} = {{ limit = {{ {can(j)} }} '
                                  f'set_variable = {{ name = {name}_{d} value = {q} }} }}' for n, (q, j) in enumerate(js))
        return out

    def box(c):
        dims = range(1, nd + 1)
        return (f'{rmx(c)} {calib(c)} set_variable = {{ name = pmr_rr value = var:{xv("pmr_rm", c)} }} '
                + ' '.join(f'{edge(c, d, 1)} set_variable = {{ name = pmr_lo_{d} value = {axes[c][d - 1]} }}' for d in dims)
                + ' if = { limit = { var:pmr_rr < 0 NOT = { var:pmr_ok = 1 } } '
                + ' '.join(edge(c, d, -1) for d in dims) + ' }')
    o.append('\tset_variable = { name = pmr_rr value = 0 }\n'
             + ('\tset_variable = { name = pmr_nrv value = 0 }\n' if SOLO_GATE else '')
             + ''.join(f'\tset_variable = {{ name = pmr_lo_{d} value = -1 }}\n'
                       f'\tset_variable = {{ name = pmr_hi_{d} value = 999 }}\n' for d in range(1, nd + 1))
             + lookup('var:pmr_ref', list(range(1, k + 1)), box))
    # every other option: priced only inside the box and where it can run (pmr_rav_<i>_<b> 1), else pmr_rav 0; the
    # recipe axis first, so a recipe outside the box skips all its automation options at one check
    def inside(i, dims):
        return ' '.join(f'var:pmr_lo_{d} <= {axes[i][d - 1]} var:pmr_hi_{d} >= {axes[i][d - 1]}' for d in dims)

    def price(i, ind):
        body = (f'{ind}if = {{\n{ind}\tlimit = {{ NOT = {{ var:pmr_ref = {i} }} }}\n'
                f'{ind}\tset_variable = {{ name = {xv("pmr_rav", i)} value = 0 }}\n'
                f'{ind}\tif = {{ limit = {{ {can(i)} }} set_variable = {{ name = {xv("pmr_rav", i)} value = 1 }} {rmx(i)}'
                + (' change_variable = { name = pmr_nrv add = 1 }' if SOLO_GATE else '') + ' }\n'
                f'{ind}}}\n')
        rest = inside(i, range(2, nd + 1))
        if not rest:
            return body
        return (f'{ind}if = {{\n{ind}\tlimit = {{ {rest} }}\n' + body.replace(ind, ind + '\t')
                + f'{ind}}}\n{ind}else = {{ set_variable = {{ name = {xv("pmr_rav", i)} value = 0 }} }}\n')
    by_first = {}
    for i in range(1, k + 1):
        by_first.setdefault(axes[i][0], []).append(i)
    for c0, xs in sorted(by_first.items()):
        o.append(f'\tif = {{\n\t\tlimit = {{ var:pmr_lo_1 <= {c0} var:pmr_hi_1 >= {c0} }}\n'
                 + ''.join(price(i, '\t\t') for i in xs)
                 + '\t}\n\telse = {\n'
                 + ''.join(f'\t\tset_variable = {{ name = {xv("pmr_rav", i)} value = 0 }}\n' for i in xs)
                 + '\t}\n')
    # the veto: an input recipe i needs more of than the reference c, at the price cap. One branch per reference c,
    # so a run tests about k/2 references and then k recipes, not k x (k-1) (perf review 3, S1)
    inputs = [{g: -q for g, q in gd.items() if q < 0 and goods_cost.get(g)} for gd, _ in econ]
    o += [f'\tset_variable = {{ name = {xv("pmr_rveto", i)} value = 0 }}\n' for i in range(1, k + 1)]

    def capped(gs, i):
        return (f'\t\tif = {{ limit = {{ OR = {{ ' + ' '.join(f'var:pmr_px_{g} >= {top}' for g in gs)
                + f' }} }} set_variable = {{ name = {xv("pmr_rveto", i)} value = 1 }} }}\n')
    # q98 (Pat 2026-11-10 18:29Z, the check map's savings): the references as a binary search (lookup), not a ladder
    vetoes = {}
    for c in range(1, k + 1):
        body = ''
        for i in range(1, k + 1):
            more = [g for g, q in sorted(inputs[i - 1].items()) if q > inputs[c - 1].get(g, 0) + 1e-9]
            if c != i and more:
                body += capped(more, i)
        if body:
            vetoes[c] = body
    if vetoes:
        o.append(lookup('var:pmr_ref', sorted(vetoes), lambda c: '\n' + vetoes[c] + '\t', '\t'))
    # the pick: the reference unless another recipe beats its profit (pmr_rr) by SWITCH_GAIN of it (SWITCH_GAIN_OF) and
    # SWITCH_MIN (pmr_hu); a pick that can't run sets none
    o.append('\tset_variable = { name = pmr_pk value = 0 }\n\tset_variable = { name = pmr_pv value = -1000000 }\n'
             '\tset_variable = { name = pmr_pkm value = 0 }\n')
    o.append('\tset_variable = { name = pmr_hu value = var:pmr_rr }\n'
             '\tif = { limit = { var:pmr_hu < 0 } change_variable = { name = pmr_hu multiply = -1 } }\n'
             f'\tchange_variable = {{ name = pmr_hu multiply = {fmt(SWITCH_GAIN_OF.get(bk, SWITCH_GAIN))} }}\n'
             f'\tchange_variable = {{ name = pmr_hu max = {fmt(SWITCH_MIN)} }}\n'
             # the first run at market prices replaces the setup pick (base prices) freely, as it stands at once
             f'\tif = {{ limit = {{ OR = {{ has_global_variable = pmr_setup AND = {{ has_variable = pmr_month '
             f'NOT = {{ has_variable = pmr_pmkt_{b} }} }} }} }} set_variable = {{ name = pmr_hu value = 0 }} }}\n'
             # books that can't be read keep the default (SWITCH_MIN above); a hold under pmr_pv's start, so a default
             # that can no longer run still gives way. Not a building just built (Pat 2026-10-20 00:08Z, Burgundy's and West
             # Bengal's new mines): it has no default yet and no staff to read, so the hold kept the recipe the game built
             # it on, and its first month's pick sent every level to retooling. Pat 2026-10-20 12:56Z ("subsidizing should
             # move up; and they should stay frozen if they can't staff"): a subsidised building that has staff may still
             # step up, onto an option at or above the default on every axis (pmr_da_<d>), at the usual hurdle; one under
             # BOOKS_OCC staffed holds everything (pmr_da_<d> left above every option)
             '\tset_variable = { name = pmr_frz value = 0 }\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_bsx_{b} has_variable = {now} NOT = {{ has_variable = {v("pmr_new_build")} }} }}\n'
             '\t\tset_variable = { name = pmr_frz value = 1 }\n'
             + ''.join(f'\t\tset_variable = {{ name = pmr_da_{d} value = 1000 }}\n' for d in range(1, nd + 1))
             + f'\t\tif = {{\n\t\t\tlimit = {{ var:{now} > 0 exists = b:{bk} b:{bk} = {{ occupancy >= {fmt(BOOKS_OCC)} }} }}\n'
             + lookup(f'var:{now}', list(range(1, k + 1)), put('pmr_da'), '\t\t\t')
             + '\t\t}\n\t}\n')
    for i in range(1, k + 1):
        o.append(f'\tif = {{\n\t\tlimit = {{ var:{xv("pmr_rav", i)} = 1 var:{xv("pmr_rveto", i)} = 0 }}\n'
                 f'\t\tset_variable = {{ name = pmr_t value = var:{xv("pmr_rm", i)} }}\n'
                 f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_ref > 0 NOT = {{ var:pmr_ref = {i} }} }}\n'
                 f'\t\t\tchange_variable = {{ name = pmr_t subtract = var:pmr_hu }}\n'
                 # the hold: below the default on some axis while the books can't be read
                 f'\t\t\tif = {{ limit = {{ var:pmr_frz = 1 OR = {{ '
                 + ' '.join(f'var:pmr_da_{d} > {axes[i][d - 1]}' for d in range(1, nd + 1))
                 + ' } } change_variable = { name = pmr_t subtract = 100000 } }\n\t\t}\n'
                 f'\t\tif = {{ limit = {{ var:pmr_t > var:pmr_pv }} set_variable = {{ name = pmr_pv value = var:pmr_t }} '
                 f'set_variable = {{ name = pmr_pk value = {i} }} set_variable = {{ name = pmr_pkm value = var:{xv("pmr_rm", i)} }} }}\n\t}}\n')
    # bug review q51, P2-2: the pick sits below the default on some axis (pmr_pdn_<b>): a step down, whatever the index
    # order says (food industry 2 -> 3 drops automation), for the red bar and the floor's pmr_dn_<b> (switch_effect)
    o.append(f'\t{setv("pmr_pdn", 0)}\n'
             f'\tif = {{\n\t\tlimit = {{ var:pmr_pk > 0 has_variable = {now} var:{now} > 0 NOT = {{ var:pmr_pk = var:{now} }} }}\n'
             + lookup('var:pmr_pk', list(range(1, k + 1)), put('pmr_pa'), '\t\t')
             + lookup(f'var:{now}', list(range(1, k + 1)), put('pmr_da'), '\t\t')
             + '\t\tif = { limit = { OR = { ' + ' '.join(f'var:pmr_pa_{d} < var:pmr_da_{d}' for d in range(1, nd + 1))
             + f' }} }} {setv("pmr_pdn", 1)} }}\n\t}}\n')
    o.append(f'\t{setv("pmr_pbest", "var:pmr_pk")}\n\t{setv("pmr_prm", "var:pmr_pkm")}\n'
             # the gain over the reference (pmr_swg_<b>) and the bar's points a month (pmr_swr_<b>)
             + f'\t{setv("pmr_swg", 0)}\n\t{setv("pmr_swr", 1)}\n'
             f'\tif = {{\n\t\tlimit = {{ var:pmr_ref > 0 var:pmr_pk > 0 NOT = {{ var:pmr_pk = var:pmr_ref }} }}\n'
             f'\t\t{setv("pmr_swg", "var:" + v("pmr_prm"))}\n\t\t{cv("pmr_swg", "subtract", "var:pmr_rr")}\n'
             '\t\tset_variable = { name = pmr_t value = var:pmr_rr }\n'
             '\t\tif = { limit = { var:pmr_t < 0 } change_variable = { name = pmr_t multiply = -1 } }\n'
             '\t\tchange_variable = { name = pmr_t max = 1 }\n'
             f'\t\t{cv("pmr_swg", "divide", "var:pmr_t")}\n'
             f'\t\t{setv("pmr_swr", "var:" + v("pmr_swg"))}\n\t\t{cv("pmr_swr", "divide", fmt(SWITCH_GAIN))}\n'
             f'\t\t{cv("pmr_swr", "max", 1)}\n\t\t{cv("pmr_swr", "min", SWITCH_MONTHS)}\n\t}}\n'
             + vanilla_score(bk, b, econ, goods_cost, setv, v)
             + pair_effect(bk, b, recipes, pair, goods_cost, active, setv, v)
             + solo_flag
             + '\t# what this run used, for the monthly check (pmr_moved_<b>): each price and the wage, PRICE_MOVE either side\n'
             + ''.join(f'\tset_variable = {{ name = pmr_px{e}_{g}_{b} value = var:pmr_px_{g} }}\n'
                       f'\tchange_variable = {{ name = pmr_px{e}_{g}_{b} multiply = {fmt(1 + s * PRICE_MOVE)} }}\n'
                       for g in goods for e, s in (('h', 1), ('l', -1)))
             + ''.join(f'\tset_variable = {{ name = pmr_wg{e}_{b} value = var:pmr_wage }}\n'
                       f'\tchange_variable = {{ name = pmr_wg{e}_{b} multiply = {fmt(1 + s * PRICE_MOVE)} }}\n'
                       for e, s in (('h', 1), ('l', -1)))
             + f'\tset_variable = {{ name = pmr_pmb_{b} value = {len(goods) + PROFIT_RULE} }}\n}}\n\n')
    # pmr_moved_<b>: on a monthly update (TICK_EVERY), pmr_pmv when a good's price or the wage moved PRICE_MOVE off what
    # the last run used; prices first (read once a day per state anyway), the wage only when they stand. Updates come
    # every other month, so the wage is read every other month as review 8's T-1 had it (Pat 2026-10-21 02:37Z).
    # Bounds from an older build (no pmr_pmb_<b>, or another goods count) recompute at once.
    spread = ' '.join(f'1 = {{ set_variable = {{ name = pmr_pchk_{b} value = yes days = {d} }} }}'
                      for d in range(PROFIT_RECHECK_DAYS - PROFIT_RECHECK_SPREAD // 2,
                                     PROFIT_RECHECK_DAYS + PROFIT_RECHECK_SPREAD // 2 + 1, PROFIT_RECHECK_SPREAD // 6))
    px_moved = ('OR = { ' + ' '.join(f'var:pmr_px_{g} >= var:pmr_pxh_{g}_{b} var:pmr_px_{g} <= var:pmr_pxl_{g}_{b}'
                                     for g in goods) + ' }')
    xm = 'scope:pmr_xmo'
    xm_moved = ('OR = { ' + ' '.join(f'{xm}.var:pmr_mpx_{g} >= var:pmr_pxh_{g}_{b} {xm}.var:pmr_mpx_{g} <= var:pmr_pxl_{g}_{b}'
                                     for g in goods) + ' }')
    # WATCH_DIRECT: the market's prices, refreshed where their 28 days ran out (pmr_xmkt_<good>, one test for them all)
    xm_fresh = (f'if = {{ limit = {{ {xm} = {{ NOT = {{ AND = {{ ' + ' '.join(f'has_variable = pmr_xmm_{g}' for g in goods)
                + ' } } } } ' + ' '.join(f'pmr_xmkt_{g} = yes' for g in goods) + ' }')

    def at(lines, ind):
        """lines written at one tab, moved to ind"""
        return ''.join(ind + ln[1:] + '\n' for ln in lines.split('\n') if ln)

    def ready(ind):
        """the prices at hand, for pmr_lite_<b>: the market's (WATCH_DIRECT), else the state's copies"""
        if not goods:
            return ''
        if not WATCH_DIRECT:
            return at(read_px, ind)
        return (f'{ind}market ?= {{ owner ?= {{ save_temporary_scope_as = pmr_xmo }} }}\n'
                f'{ind}if = {{ limit = {{ exists = {xm} }} {xm_fresh} }}\n'
                f'{ind}else = {{\n' + at(read_px, ind + '\t') + f'{ind}}}\n')

    def watch(ind, then, other=None):
        """the price check at ind: `then` where a price is PRICE_MOVE off the last run's, else other(ind)'s lines"""
        def old(i):
            return (at(read_px, i) + f'{i}if = {{ limit = {{ {px_moved} }} {then} }}\n'
                    + (f'{i}else = {{\n' + other(i + '\t') + f'{i}}}\n' if other else ''))
        if not WATCH_DIRECT:
            return old(ind)
        return (f'{ind}market ?= {{ owner ?= {{ save_temporary_scope_as = pmr_xmo }} }}\n'
                f'{ind}if = {{\n{ind}\tlimit = {{ exists = {xm} }}\n{ind}\t{xm_fresh}\n'
                f'{ind}\tif = {{ limit = {{ {xm_moved} }} {then} }}\n'
                + (f'{ind}\telse = {{\n' + other(ind + '\t\t') + f'{ind}\t}}\n' if other else '')
                + f'{ind}}}\n{ind}else = {{\n' + old(ind + '\t') + f'{ind}}}\n')
    solo_watch = ''
    sgc = (lambda n: f'pmr_sgc_{n} = yes') if SOLO_GATE and not RELEASE else (lambda n: '')   # the SOLO line's counts
    if SOLO_GATE:
        # the engine's books say when the gate ends: the building's owner, staff, subsidy, profit and earnings, the
        # conditions pmr_wage_<b> and pmr_ok read off them. Then prices alone: a full run (1) or the light one (2, 3)
        on_move = 'set_variable = pmr_pmv' if SOLO_GATE == 1 else f'pmr_lite_{b} = yes'
        prices = watch('\t\t\t', on_move) if goods and SOLO_GATE < 4 else ''
        recheck = '' if SOLO_GATE < 3 else (
            f'\t\telse_if = {{\n\t\t\tlimit = {{ NOT = {{ has_variable = pmr_pchk_{b} }} }}\n'
            f'\t\t\tpmr_newest_{b} = yes\n\t\t\tset_variable = {{ name = pmr_nel_{b} value = var:pmr_lsup }}\n'
            f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:{v("pmr_new_now")} = var:{now} }}\n'
            + (f'\t\t\t\t{sgc("held")}\n' if sgc('held') else '')
            + ready('\t\t\t\t')
            + f'\t\t\t\tpmr_lite_{b} = yes\n\t\t\t\t{setv("pmr_new", "var:" + v("pmr_new_now"))}\n'
            f'\t\t\t\trandom_list = {{ {spread} }}\n\t\t\t}}\n'
            f'\t\t\telse = {{ remove_variable = {solo} }}\n\t\t}}\n')
        solo_watch = (f'\telse_if = {{\n\t\tlimit = {{ has_variable = {solo} }}\n'
                      f'\t\tif = {{\n\t\t\tlimit = {{ OR = {{ owner = {{ is_player = yes }} has_variable = pmr_abroad_{b} '
                      f'NOT = {{ exists = b:{bk} }} var:{v("pmr_level")} <= 0 b:{bk} = {{ OR = {{ is_subsidized = yes '
                      f'occupancy < {fmt(BOOKS_OCC)} weekly_profit <= {fmt(-BOOKS_PROFIT[0])} NOT = {{ earnings >= {fmt(BOOKS_EARN[0])} }} }} }} }} }}\n'
                      f'\t\t\tremove_variable = {solo}\n\t\t\tset_variable = pmr_pmv\n'
                      + (f'\t\t\t{sgc("end")}\n' if sgc('end') else '') + '\t\t}\n'
                      + recheck
                      + '\t\telse = {\n' + (f'\t\t\t{sgc("held")}\n' if sgc('held') else '') + prices + '\t\t}\n\t}\n')

    def wage_watch(ind):
        return (f'{ind}pmr_wage_{b} = yes\n'
                f'{ind}if = {{ limit = {{ OR = {{ var:pmr_wg_{b} >= var:pmr_wgh_{b} var:pmr_wg_{b} <= var:pmr_wgl_{b} }} }} '
                'set_variable = pmr_pmv }\n')
    o.append(f'pmr_moved_{b} = {{\n'
             f'\tif = {{\n\t\tlimit = {{ OR = {{ NOT = {{ has_variable = pmr_pmb_{b} }} NOT = {{ var:pmr_pmb_{b} = {len(goods) + PROFIT_RULE} }} }} }}\n'
             '\t\tset_variable = pmr_pmv\n\t}\n' + solo_watch + '\telse = {\n'
             + (f'\t\t{sgc("watch")}\n' if sgc('watch') else '')
             + (watch('\t\t', 'set_variable = pmr_pmv', wage_watch) if goods else
                '\t\tif = { limit = { always = yes }\n' + wage_watch('\t\t\t') + '\t\t}\n')
             + '\t}\n}\n\n')

    # pmr_best_<b>: the target candidate every tick reads (pmr_best_now), the cached pick
    def var(name, d=0):
        return f"[THIS.Var('{name}').GetValue|{d}]"
    per = lambda name, d=0: '/'.join(var(xv(name, i), d) for i in range(1, k + 1))   # noqa: E731
    line = (f'PMR;rec=PROFIT;date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting];'
            f"building={bk};to={var(v('pmr_to'))};newest={var(v('pmr_new_now'))};pick={var(v('pmr_pbest'))};"
            f"ref={var('pmr_ref')};floor={var('pmr_fl')};ok={var('pmr_ok')};frz={var('pmr_frz')};gain={var(v('pmr_swg'), 2)};wage={var('pmr_wage')};thr={var('pmr_thr', 2)};off={var('pmr_off', 1)};"
            f"earn={var(v('pmr_bke'), 2)};bal={var(v('pmr_bkp'))};occ={var(v('pmr_bko'), 3)};"
            f"rm={per('pmr_rm', 1)};rg={per('pmr_rg', 1)};rw={per('pmr_rw', 1)};"
            f"can={per('pmr_rav')};veto={per('pmr_rveto')};"
            + (f"pair={var(v('pmr_cbi'))}x{var(v('pmr_cba'))};"
               + ('' if pair.get('split') else
                  'cp=' + '/'.join(var(f'pmr_cp_{i}_{a}_{b}', 1) for i, a in sorted(pair['econ'])) + ';') if pair else '')
            + 'px='
            + ','.join(f"{g}:{var('pmr_px_' + g, 2)}" for g in goods))
    # The first calculation runs during game setup, before the market has real prices (q23: steel read 0.25-0.35
    # of base in every French state, so Blister Steel showed -£2,990 a level while the mill made +£1.57K; q31: the
    # Investments tab showed those figures on 1 January, Pat 23:22Z). It uses base prices (pmr_setup) and is
    # not trusted: every building's pick is computed once more on its first monthly pulse (pmr_pmkt_<b>), which
    # also gives the log every player building's pick on its own (Pat, 17:59Z), then the yearly re-check runs.
    first = f'has_variable = pmr_month NOT = {{ has_variable = pmr_pmkt_{b} }}'
    o.append(f'pmr_best_{b} = {{\n{newest}'
             '\t# Pat 02:43Z: each monthly pulse after the first pick at market prices looks for moved prices or wage\n'
             f'\tif = {{ limit = {{ has_variable = pmr_month has_variable = pmr_pmkt_{b}'
             + (' NOT = { has_global_variable = pmr_off_watch }' if OBS_PARTS_ON else '') + f' }} pmr_moved_{b} = yes }}\n'
             # SOLO_GATE 3: a solo building's re-check is pmr_moved_<b>'s, at its next monthly update
             f'\tif = {{\n\t\tlimit = {{ OR = {{ '
             + (f'NOT = {{ has_variable = pmr_pchk_{b} }} ' if SOLO_GATE < 3 else
                f'AND = {{ NOT = {{ has_variable = pmr_pchk_{b} }} OR = {{ has_variable = pmr_month NOT = {{ has_variable = {solo} }} }} }} ')
             + f'NOT = {{ has_variable = {v("pmr_new")} }} NOT = {{ var:{v("pmr_new")} = var:{v("pmr_new_now")} }} '
             f'has_variable = {v("pmr_new_build")} AND = {{ {first} }} has_variable = pmr_pmv }} }}\n'
             f'\t\tpmr_profit_{b} = yes\n' + (f'\t\t{sgc("full")}\n' if sgc('full') else '')
             + f'\t\t{setv("pmr_new", "var:" + v("pmr_new_now"))}\n'
             f'\t\tif = {{ limit = {{ has_variable = pmr_pchk_{b} }} remove_variable = pmr_pchk_{b} }}\n'
             f'\t\trandom_list = {{ {spread} }}\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ {first} }}\n\t\t\tset_variable = pmr_pmkt_{b}\n'
             '\t\t\tset_variable = pmr_sw_inst  # the first pick at market prices stands at once (pmr_switch)\n'
             f'\t\t\tif = {{ limit = {{ owner = {{ is_player = yes }} }} debug_log = "{line};why=first_month" }}\n\t\t}}\n'
             f'\t\telse_if = {{ limit = {{ has_variable = pmr_pmv owner = {{ is_player = yes }} }} debug_log = "{line};why=price" }}\n'
             f'\t\telse_if = {{ limit = {{ owner = {{ is_player = yes }} }} debug_log = "{line};why=recompute" }}\n\t}}\n'
             '\tif = { limit = { has_variable = pmr_pmv } remove_variable = pmr_pmv }\n'
             + f'\tpmr_switch_{b} = yes\n'
             + (f'\tif = {{ limit = {{ NOT = {{ AND = {{ has_variable = pmr_pfx_l_{b} var:pmr_pfx_l_{b} = var:{v("pmr_level")} '
                f'var:pmr_pfx_v_{b} = var:{v("pmr_pvs")} }} }} }} pmr_pf_sync_{b} = yes }}'
                '   # PF_SUMS: the score or the level moved\n' if PF_SUMS else '') + '}\n\n')
    if PF_SUMS:
        PF_SYNC.add(b)
    if SOLO_GATE >= 2:
        o.append(lite_effect(bk, b, econ, goods, goods_cost, setv, v))
    return switch_effect(b, bk, k, setv, v, var) + wage_effect(bk, b, econ) + ''.join(pre) + ''.join(o)


def lite_effect(bk, b, econ, goods, goods_cost, setv, v):
    """State scope, SOLO_GATE 2 and 3: pmr_lite_<b>, what pmr_profit_<b> would change for a building the solo gate
    holds (pmr_moved_<b> has just read the engine's books: not subsidised, BOOKS_OCC staffed, earning, no loss). Its
    pick is the default, and the default's figure is held to the books (profit_effect's calib), so the run comes to
    the books' profit per level (pmr_bpl_<b>, as pmr_wage_<b> reads it), the pick's row (pmr_prm_<b>), the investment
    score (vanilla_score, the same weights) and the prices the next check compares with."""
    emps = TARGET_EMPLOYEES.get(bk, [])
    pvs = v('pmr_pvs')

    def score(i):
        gd = econ[i - 1][0]
        e = max(emps[i - 1] if i <= len(emps) else 0, 1)
        out = sum(q * goods_cost[g] for g, q in gd.items() if q > 0 and goods_cost.get(g))
        return (f'{setv("pmr_pve", e)} '
                f'if = {{ limit = {{ var:{pvs} > 0 }} change_variable = {{ name = {pvs} multiply = {fmt(VANILLA_PROFIT_W / e)} }} }} '
                f'else = {{ change_variable = {{ name = {pvs} multiply = {fmt(VANILLA_DEFICIT_W / e)} }} }} '
                f'{setv("pmr_pvp", "var:" + pvs)} '
                f'change_variable = {{ name = {pvs} add = {fmt(out * VANILLA_OUTPUT_W)} }}')
    keep = ('' if RELEASE else
            ''.join(f'\tset_variable = {{ name = pmr_bk{x}_{b} value = var:pmr_bk_{x} }}\n' for x in 'po'))

    def bound(src, ind):
        return ''.join(f'{ind}set_variable = {{ name = pmr_px{e}_{g}_{b} value = {src(g)} }}\n'
                       f'{ind}change_variable = {{ name = pmr_px{e}_{g}_{b} multiply = {fmt(1 + sg * PRICE_MOVE)} }}\n'
                       for g in goods for e, sg in (('h', 1), ('l', -1)))
    bounds = bound(lambda g: f'var:pmr_px_{g}', '\t')
    if WATCH_DIRECT and goods:   # the prices pmr_moved_<b> compared: the market's where it has one
        bounds = ('\tif = {\n\t\tlimit = { exists = scope:pmr_xmo }\n'
                  + bound(lambda g: f'scope:pmr_xmo.var:pmr_mpx_{g}', '\t\t')
                  + '\t}\n\telse = {\n' + bounds.replace('\n\t', '\n\t\t').replace('\t', '\t\t', 1) + '\t}\n')
    return (f'pmr_lite_{b} = {{\n' + ('' if RELEASE else '\tpmr_sgc_lite = yes\n')
            + f'\tb:{bk} = {{ save_temporary_scope_as = pmr_bk }}\n\tpmr_read_books_po = yes\n' + keep
            + f'\tset_variable = {{ name = pmr_bpl_{b} value = var:pmr_bk_p }}\n'
            f'\tchange_variable = {{ name = pmr_bpl_{b} divide = var:pmr_bk_o }}\n'
            f'\tchange_variable = {{ name = pmr_bpl_{b} divide = var:{v("pmr_level")} }}\n'
            f'\t{setv("pmr_prm", "var:pmr_bpl_" + b)}\n\t{setv("pmr_pvs", "var:pmr_bpl_" + b)}\n'
            + lookup(f'var:{v("pmr_pbest")}', list(range(1, len(econ) + 1)), score)
            + bounds
            + '}\n\n')


def switch_effect(b, bk, k, setv, v, var):
    """State scope, after each pick: pmr_switch_<b> (Pat, 2026-10-19 01:07Z: "a progress bar ... towards setting a new
    PM default ... if it wants to downgrade because goods are too expensive it has to also fill up the same bar in
    red; it should take 6 months"). The pick (pmr_pbest_<b>) becomes the default new levels and retooling follow
    (pmr_best_now_<b>) once its bar has SWITCH_MONTHS points, pmr_swr_<b> a monthly pulse (Pat 12:59Z):
      pmr_swto_<b>  the pick the bar fills toward (0: none)     pmr_sw_<b>   points so far
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
    same = f'\telse_if = {{\n\t\tlimit = {{ OR = {{ var:{pick} = 0 var:{pick} = var:{now} }} }}\n' + clear + '\t}\n'
    return (f'pmr_switch_{b} = {{\n'
            f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {now} }} }}\n' + take + '\t}\n'
            + (same if SWITCH_QUICK else '')
            # bug review q51, P2-2: a default the first pick at market prices lowers is marked like one a red bar lowered
            + f'\telse_if = {{\n\t\tlimit = {{ OR = {{ has_variable = pmr_sw_inst {dead} }} }}\n'
            f'\t\tif = {{\n\t\t\tlimit = {{ var:{pick} > 0 NOT = {{ var:{pick} = var:{now} }} }}\n'
            f'\t\t\tif = {{ limit = {{ owner = {{ pmr_logged = yes }} }} debug_log = "PMR;rec=DEFAULT;{where};'
            f"from={var(now)};to={var(pick)};dir={var(v('pmr_pdn'))};months=0\" }}\n"
            f'\t\t\tif = {{ limit = {{ var:{v("pmr_pdn")} ?= 1 }} set_variable = pmr_dn_{b} }}\n'
            f'\t\t\telse_if = {{ limit = {{ has_variable = pmr_dn_{b} }} remove_variable = pmr_dn_{b} }}\n\t\t}}\n'
            + take + '\t}\n'
            + ('' if SWITCH_QUICK else same)
            + '\telse = {\n'
            f'\t\tif = {{\n\t\t\tlimit = {{ NOT = {{ var:{v("pmr_swto")} = var:{pick} }} }}\n'
            f'\t\t\t{setv("pmr_swto", "var:" + pick)}\n\t\t\t{setv("pmr_sw", 0)}\n'
            f'\t\t\tif = {{ limit = {{ var:{v("pmr_pdn")} ?= 1 }} {setv("pmr_swd", -1)} }}\n'
            f'\t\t\telse = {{ {setv("pmr_swd", 1)} }}\n'
            f'\t\t\tif = {{ limit = {{ owner = {{ pmr_logged = yes }} }} debug_log = "PMR;rec=SWITCH_START;{where};'
            f"default={var(now)};to={var(pick)};dir={var(v('pmr_swd'))};gain={var(v('pmr_swg'), 2)};pts={var(v('pmr_swr'), 2)}\" }}\n\t\t}}\n"
            # bug review q51, P2-3: a red bar stops once the books show no loss (Pat 19:30Z), and the next tick prices again
            f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_swd")} = -1 has_variable = pmr_bpl_{b} var:pmr_bpl_{b} >= 0 }}\n'
            + clear.replace('\t\t', '\t\t\t')
            + f'\t\t\tif = {{ limit = {{ has_variable = pmr_pchk_{b} }} remove_variable = pmr_pchk_{b} }}\n\t\t}}\n'
            # Pat 12:59Z: the bigger the gain over the default, the more points a month (pmr_swr_<b>, profit_effect)
            # TICK_EVERY (Pat 2026-10-21 12:37Z): an update every other month adds two months' points
            f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_month NOT = {{ var:{v("pmr_swd")} = 0 }} }}\n'
            '\t\t\tset_variable = { name = pmr_t value = 1 }\n'
            f'\t\t\tif = {{ limit = {{ has_variable = {v("pmr_swr")} }} set_variable = {{ name = pmr_t value = var:{v("pmr_swr")} }} }}\n'
            + every_other(f'change_variable = {{ name = pmr_t multiply = {TICK_EVERY} }}', '\t\t\t')
            + f'\t\t\tchange_variable = {{ name = {v("pmr_sw")} add = var:pmr_t }}\n\t\t}}\n'
            f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_sw")} >= {SWITCH_MONTHS} }}\n'
            f'\t\t\tif = {{ limit = {{ owner = {{ pmr_logged = yes }} }} debug_log = "PMR;rec=DEFAULT;{where};'
            f"from={var(now)};to={var(pick)};dir={var(v('pmr_swd'))};months={var(v('pmr_sw'))}\" }}\n"
            f'\t\t\t{setv("pmr_best_now", "var:" + pick)}\n'
            # a default a loss lowered keeps the floor from raising it while its levels retool (profit_effect)
            f'\t\t\tif = {{ limit = {{ var:{v("pmr_swd")} = -1 }} set_variable = pmr_dn_{b} }}\n'
            f'\t\t\telse_if = {{ limit = {{ has_variable = pmr_dn_{b} }} remove_variable = pmr_dn_{b} }}\n'
            # the next tick prices the options around the new default (profit_effect's box)
            f'\t\t\tif = {{ limit = {{ has_variable = pmr_pchk_{b} }} remove_variable = pmr_pchk_{b} }}\n'
            + clear.replace('\t\t', '\t\t\t') + '\t\t}\n\t}\n'
            '\tif = { limit = { has_variable = pmr_sw_inst } remove_variable = pmr_sw_inst }\n'
            # Pat 2026-10-19 03:51Z: the card showed a finished bar for a month, as the country's copy (pmr_c_sum_<b>, the
            # state with the most levels) waited for the country's monthly pulse. That state's bar now reaches it at once.
            f'\tif = {{\n\t\tlimit = {{ has_variable = {v("pmr_level")} owner = {{ is_player = yes has_variable = pmr_c_swm_{b} }} }}\n'
            '\t\tsave_temporary_scope_as = pmr_sws\n'
            f'\t\towner = {{\n\t\t\tif = {{\n\t\t\t\tlimit = {{ scope:pmr_sws.var:{v("pmr_level")} >= var:pmr_c_swm_{b} }}\n'
            + ''.join(f'\t\t\t\tset_variable = {{ name = pmr_c_{n}_{b} value = scope:pmr_sws.var:{v(x)} }}\n'
                      for n, x in (('sw', 'pmr_sw'), ('swd', 'pmr_swd'), ('swto', 'pmr_swto'), ('now', 'pmr_best_now'),
                                   ('swg', 'pmr_swg')))
            + '\t\t\t}\n\t\t}\n\t}\n}\n\n')


def vanilla_score(bk, b, econ, goods_cost, setv, v):
    """Inside pmr_profit_<b>, after the pick: pmr_pvs_<b>, what vanilla's investment pool would add to the type's
    ai_value for a new level of the pick at this state's prices (VANILLA_*_W): its profit per level a week
    (pmr_prm_<b>) / the target's employees per level x 7500 (x 10000 for a loss), plus its outputs at base value
    x 0.3125. 0 without a pick. pmr_pvp_<b>: the profit (or loss) term alone, for the Policies tooltip's lines;
    pmr_pve_<b>: the pick's employees per level, for Productivity's nested tooltip."""
    emps = TARGET_EMPLOYEES.get(bk, [])
    o = [f'\t# vanilla\'s profit and output terms for the pick (vanilla_score); pmr_pvp_<b> the profit term alone\n'
         f'\t{setv("pmr_pvs", 0)}\n\t{setv("pmr_pvp", 0)}\n\t{setv("pmr_pve", 0)}\n']
    for i, (gd, _wu) in enumerate(econ, 1):
        e = max(emps[i - 1] if i <= len(emps) else 0, 1)
        out = sum(q * goods_cost[g] for g, q in gd.items() if q > 0 and goods_cost.get(g))
        o.append(f'\tif = {{\n\t\tlimit = {{ var:pmr_pk = {i} }}\n\t\t{setv("pmr_pvs", "var:" + v("pmr_prm"))}\n'
                 f'\t\t{setv("pmr_pve", e)}\n'
                 f'\t\tif = {{ limit = {{ var:{v("pmr_pvs")} > 0 }} '
                 f'change_variable = {{ name = {v("pmr_pvs")} multiply = {fmt(VANILLA_PROFIT_W / e)} }} }}\n'
                 f'\t\telse = {{ change_variable = {{ name = {v("pmr_pvs")} multiply = {fmt(VANILLA_DEFICIT_W / e)} }} }}\n'
                 f'\t\t{setv("pmr_pvp", "var:" + v("pmr_pvs"))}\n'
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
        # cell is the pick. pmr_cav_<i>_<a>_<b>: 1 priced and runnable, -1 priced but skipped at the price cap, 0 not
        # priced this run (out of reach or one step too far, profit_effect), so the card leaves its figure out.
        o = [f'\t# recipe + automation pairs: the retool targets\' figures (pair_effect)\n'
             f'\t{setv("pmr_cbi", 0)}\n\t{setv("pmr_cba", 0)}\n']
        for (i, a), x in sorted(pair['index'].items()):
            cp, cav = f'pmr_cp_{i}_{a}_{b}', f'pmr_cav_{i}_{a}_{b}'
            o.append(f'\tset_variable = {{ name = {cp} value = var:pmr_rm_{x}_{b} }}\n'
                     f'\tset_variable = {{ name = {cav} value = 0 }}\n'
                     f'\tif = {{ limit = {{ var:pmr_rav_{x}_{b} = 1 }} set_variable = {{ name = {cav} value = 1 }} '
                     f'if = {{ limit = {{ var:pmr_rveto_{x}_{b} = 1 }} set_variable = {{ name = {cav} value = -1 }} }} }}\n')
        at = {x: ia for ia, x in pair['index'].items()}
        o.append(lookup(f'var:{v("pmr_pbest")}', sorted(at), lambda x: f'{setv("pmr_cbi", at[x][0])} {setv("pmr_cba", at[x][1])}'))
        return ''.join(o)
    o = [f'\t# recipe + automation pairs (pair_effect)\n\t{setv("pmr_cbi", 0)}\n\t{setv("pmr_cba", 0)}\n'
         '\tset_variable = { name = pmr_pv value = -1000000 }\n']
    for (i, a), (gd, wu) in sorted(pair['econ'].items()):
        r, cp, cav = recipes[i - 1], f'pmr_cp_{i}_{a}_{b}', f'pmr_cav_{i}_{a}_{b}'
        o.append(f'\tset_variable = {{ name = {cp} value = 0 }}\n')
        for g, q in sorted(gd.items()):
            if goods_cost.get(g):
                o.append(f'\tset_variable = {{ name = pmr_t value = var:pmr_px_{g} }}\n'
                         f'\tchange_variable = {{ name = pmr_t multiply = {fmt(q * goods_cost[g])} }}\n'
                         f'\tchange_variable = {{ name = {cp} add = var:pmr_t }}\n')
        # the goods x the building's throughput, less the wage (as pmr_rm)
        o.append(f'\tchange_variable = {{ name = {cp} multiply = var:pmr_thr }}\n'
                 '\tset_variable = { name = pmr_t value = var:pmr_wage }\n'
                 f'\tchange_variable = {{ name = pmr_t multiply = {fmt(wu / 10000)} }}\n'
                 f'\tchange_variable = {{ name = {cp} subtract = var:pmr_t }}\n'
                 f'\tchange_variable = {{ name = {cp} add = var:pmr_off }}\n')
        techs = pair['techs'][a - 1]
        cond = (f'OR = {{ {active(r)} {frames.can_activate(bk, r.key)} }}'
                + (' owner = { ' + ' '.join(f'has_technology_researched = {t}' for t in techs) + ' }' if techs else '')
                + (' var:pmr_elec = 1' if pair['elec'][(i, a)] else '')
                + (' var:pmr_rail = 1' if rails(gd) else ''))
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


def supply_test(bk):
    """State scope: the state has a level of bk, as pmr_state_tick asks it before ticking the type."""
    return f'has_building = {bk} b:{bk} = {{ level >= 1 }}'


def shared_effects(price_goods=()):
    once = ''.join(f'\t\tif = {{ limit = {{ {supply_test(bk)} }} set_variable = {{ name = {var} value = 1 }} }}\n'
                   f'\t\telse = {{ set_variable = {{ name = {var} value = 0 }} }}\n' for bk, var in SUPPLY)
    out = (''.join(price_effect(g) for g in price_goods) + (books_effect() if PROFIT_TARGET else '')
           + '# State scope. pmr_elec: 1 while the state has a power plant, pmr_rail: 1 while it has a railway (SUPPLY;\n'
           '# electricity and transportation are local goods, so only the state\'s own count). The state\'s turn sets\n'
           '# them from the test it makes anyway to tick each building type (pmr_state_tick, power plants and railways\n'
           '# first); pmr_lsup holds both, for pmr_newest\'s re-scan.\n'
           'pmr_lsup_now = {\n'
           '\tset_variable = { name = pmr_lsup value = var:pmr_rail }\n'
           '\tchange_variable = { name = pmr_lsup multiply = 2 }\n'
           '\tchange_variable = { name = pmr_lsup add = var:pmr_elec }\n'
           '}\n\n'
           '# State scope: the flags of a state no turn has set yet (a state created since its country\'s last turn).\n'
           'pmr_supply_once = {\n'
           '\tif = {\n\t\tlimit = { OR = { NOT = { has_variable = pmr_elec } NOT = { has_variable = pmr_rail } } }\n'
           + once + '\t\tpmr_lsup_now = yes\n\t}\n}\n\n')
    if RELEASE:
        return out
    # Method-count rework, test builds: a frame pmr_frame_<b> puts back after a change from outside PMR's tick (the AI's,
    # the game's: pmr_pmc, pmr_on_production_method_changed), counted for the month's UNDO line (pmr_skip_report).
    if SOLO_GATE:
        # the solo gate's month, for the SOLO line (pmr_skip_report): building updates the gate held, updates it ended on
        # (the books), light runs, full profit runs and updates that took the full price and wage watch
        out += '# Any scope (test builds): the solo gate\'s counts for the month\'s SOLO line.\n'
        for n in SOLO_COUNTS:
            out += (f'pmr_sgc_{n} = {{\n\tif = {{ limit = {{ NOT = {{ has_global_variable = pmr_sg_{n} }} }} '
                    f'set_global_variable = {{ name = pmr_sg_{n} value = 0 }} }}\n'
                    f'\tchange_global_variable = {{ name = pmr_sg_{n} add = 1 }}\n}}\n\n')
    out += ('# State scope (test builds): count a frame put back after a change from outside PMR\'s tick.\n'
            'pmr_count_undo = {\n\tif = {\n\t\tlimit = { has_variable = pmr_pmc }\n'
            '\t\tif = { limit = { NOT = { has_global_variable = pmr_undo } } set_global_variable = { name = pmr_undo value = 0 } }\n'
            '\t\tchange_global_variable = { name = pmr_undo add = 1 }\n\t}\n}\n\n'
            '# State scope (test builds): of those, the building was found on the first method of the frame\'s group, the\n'
            '# one switch the AI\'s lock (frames.LOCK_PURE) leaves open.\n'
            'pmr_count_undo_first = {\n\tif = {\n\t\tlimit = { has_variable = pmr_pmc }\n'
            '\t\tif = { limit = { NOT = { has_global_variable = pmr_undo_f } } set_global_variable = { name = pmr_undo_f value = 0 } }\n'
            '\t\tchange_global_variable = { name = pmr_undo_f add = 1 }\n\t}\n}\n\n')
    # pmr_pool: the owner's investment pool by order of magnitude, and pmr_unemp: the state's unemployment rate in %
    # (lower bound of 1/2/5/10/20), for the log, read once a turn. The investment pool scores a building x0.25 in a
    # state short of workers, which can cost a retool site with a crew a pick.
    return (out + '# State scope, the state\'s turn: pool and unemployment for the log, only in the player\'s states\n'
            '# (not in a release build).\n'
            'pmr_read_log = {\n\tif = {\n\t\tlimit = { owner = { is_player = yes } }\n'
            '\t\tset_variable = { name = pmr_pool value = 0 }\n'
            + ''.join(f'\t\t{"if" if j == 0 else "else_if"} = {{ limit = {{ owner = {{ investment_pool >= {x} }} }} set_variable = {{ name = pmr_pool value = {x} }} }}\n'
                      for j, x in enumerate((100000, 10000, 1000, 100)))
            + '\t\tset_variable = { name = pmr_unemp value = 0 }\n'
            + ''.join(f'\t\t{"if" if j == 0 else "else_if"} = {{ limit = {{ state_unemployment_rate > {fmt(x / 100)} }} set_variable = {{ name = pmr_unemp value = {x} }} }}\n'
                      for j, x in enumerate((20, 10, 5, 2, 1))) + '\t}\n}\n\n')


def tick_order(buildings):
    """The order a state's turn ticks its building types: SUPPLY's first, so every later type sees their flags."""
    missing = [bk for bk, _ in SUPPLY if bk not in buildings]
    if missing:
        raise SystemExit(f'SUPPLY types {missing} are not PMR buildings: their flags would never be set')
    first = [bk for bk, _ in SUPPLY]
    return first + [bk for bk in buildings if bk not in first]


def state_tick_type(bk, t='\t'):
    """pmr_state_tick's step for one building type, indented by t: its tick, or the clean-up once it is gone. A SUPPLY
    type also sets its flag, 1 or 0, and the last of them pmr_lsup."""
    b = short(bk)
    flag = dict(SUPPLY).get(bk)
    clean = (f'{t}\tif = {{ limit = {{ has_variable = pmr_pending_{b} }} set_variable = {{ name = pmr_pending_{b} value = 0 }} }}\n'
             f'{t}\tpmr_close_retool_{b} = yes\n'
             + ''.join(f'{t}\tif = {{ limit = {{ has_variable = {n} }} remove_variable = {n} }}\n'
                       for n in (f'pmr_mix_{b}', f'pmr_abroad_{b}', f'pmr_bpl_{b}', f'pmr_bsx_{b}', f'pmr_dn_{b}',
                                 f'pmr_bok_{b}') + ((f'pmr_xok_{b}',) if bk in OPTION_TYPES else ())
                       + ((f'pmr_solo_{b}',) if SOLO_GATE else ()))
             + (frames.clear_vars(FRAMES[bk], t + '\t') if bk in FRAMES else '')
             + (f'{t}\tpmr_pf_gone_{b} = yes   # PF_SUMS: its part leaves the owner\'s sums\n' if PF_SUMS and b in PF_SYNC else ''))
    # performance review 6, S-14: pmr_mix_<b> is set whenever the other two can be, so it alone says to clean up;
    # nothing is pending for a building that is gone, so the gate closes now (performance review 6)
    gone = f'has_variable = pmr_mix_{b} NOT = {{ exists = b:{bk} }}'
    if not flag:
        return (f'{t}if = {{ limit = {{ {supply_test(bk)} }} pmr_tick_{b} = yes }}\n'
                f'{t}else_if = {{\n{t}\tlimit = {{ {gone} }}\n' + clean + f'{t}}}\n')
    return (f'{t}if = {{ limit = {{ {supply_test(bk)} }} set_variable = {{ name = {flag} value = 1 }} pmr_tick_{b} = yes }}\n'
            f'{t}else = {{\n{t}\tset_variable = {{ name = {flag} value = 0 }}\n'
            f'{t}\tif = {{\n{t}\t\tlimit = {{ {gone} }}\n' + clean.replace(f'{t}\t', f'{t}\t\t') + f'{t}\t}}\n{t}}}\n'
            + (f'{t}pmr_lsup_now = yes\n' if bk == SUPPLY[-1][0] else ''))


# --script-profile: the text profiler keys its totals by top-level block, so the monthly state pulse runs as one
# on_action per step, each its own effect block: the opening (pmr_month, the state's electricity), each building
# type's tick, the closing, then the four state checks. The same effects in the same order as
# pmr_on_monthly_pulse_state (pulse_state_effect, checked), which the other builds run.
XTURN_DONE = '\t\t\tif = { limit = { has_variable = pmr_xturn } remove_variable = pmr_xturn }\n'


# Test builds (RESEARCH_MAP). pmr_rm_count counts into a global; pmr_rm_report (country scope, monthly) logs the RMAP
# line: passes = country passes that had a type marked since the last line, runs = one type's research pass in one state.
RMAP_COUNT = ('# Test builds (RESEARCH_MAP): the month\'s count of marked passes (pmr_rm_p) and of state passes (pmr_rm_r).\n'
              'pmr_rm_count = {\n\tif = { limit = { NOT = { has_global_variable = $N$ } } set_global_variable = { name = $N$ value = 0 } }\n'
              '\tchange_global_variable = { name = $N$ add = 1 }\n}\n'
              'pmr_rm_report = {\n\tif = {\n\t\tlimit = { NOT = { has_global_variable = pmr_rm_m } }\n'
              '\t\tset_global_variable = { name = pmr_rm_m value = yes days = 28 }\n'
              '\t\tset_variable = { name = pmr_rm_pv value = 0 }\n\t\tset_variable = { name = pmr_rm_rv value = 0 }\n'
              '\t\tif = { limit = { has_global_variable = pmr_rm_p } set_variable = { name = pmr_rm_pv value = global_var:pmr_rm_p } }\n'
              '\t\tif = { limit = { has_global_variable = pmr_rm_r } set_variable = { name = pmr_rm_rv value = global_var:pmr_rm_r } }\n'
              '\t\tdebug_log = "PMR;rec=RMAP;date=[TimeKeeper.GetCurrentDate.GetString];'
              "passes=[THIS.Var('pmr_rm_pv').GetValue|0];runs=[THIS.Var('pmr_rm_rv').GetValue|0]\"\n"
              '\t\tremove_variable = pmr_rm_pv\n\t\tremove_variable = pmr_rm_rv\n'
              '\t\tset_global_variable = { name = pmr_rm_p value = 0 }\n\t\tset_global_variable = { name = pmr_rm_r value = 0 }\n\t}\n}\n\n')

QUIET_COUNT = ('\n# Test builds (QUIET_TICK). State scope: one more quiet update. Country scope, monthly: the QUIET line, the\n'
               '# quiet updates since the last one.\n'
               'pmr_qt_count = {\n\tif = { limit = { NOT = { has_global_variable = pmr_qt_n } } set_global_variable = { name = pmr_qt_n value = 0 } }\n'
               '\tchange_global_variable = { name = pmr_qt_n add = 1 }\n}\n'
               'pmr_qt_report = {\n\tif = {\n\t\tlimit = { has_global_variable = pmr_qt_n NOT = { has_global_variable = pmr_qt_m } }\n'
               '\t\tset_global_variable = { name = pmr_qt_m value = yes days = 28 }\n'
               '\t\tset_variable = { name = pmr_qt_v value = global_var:pmr_qt_n }\n'
               '\t\tdebug_log = "PMR;rec=QUIET;date=[TimeKeeper.GetCurrentDate.GetString];'
               "updates=[THIS.Var('pmr_qt_v').GetValue|0]\"\n"
               '\t\tremove_variable = pmr_qt_v\n\t\tset_global_variable = { name = pmr_qt_n value = 0 }\n\t}\n}\n')


def own_effects():
    """State scope: pmr_own_check, a state that changed hands since its last accounting (pmr_own, the owner then). From
    on_state_owner_change (vanilla runs its own effects there, root the state under its new owner), from the state's
    monthly pulse in case a transfer did not fire it, and before a state's part of the investment sums moves.
    RESEARCH_MAP: the state's next update scans every type's newest recipe (pmr_ownchg), as the new owner's
    technologies and laws are other ones. PF_SUMS: its parts of the investment sums move to the new owner."""
    if not (RESEARCH_MAP or PF_SUMS):
        return ''
    return ('\n# State scope: has the state changed hands since its last accounting (RESEARCH_MAP, PF_SUMS)\n'
            'pmr_own_check = {\n'
            '\tif = { limit = { NOT = { has_variable = pmr_own } } set_variable = { name = pmr_own value = owner }'
            + (' pmr_pf_own_g = yes' if PF_SUMS else '') + ' }\n'
            '\telse_if = {\n\t\tlimit = { NOT = { owner = var:pmr_own } }\n'
            + ("\t\tpmr_pf_moved = yes   # PF_SUMS: its parts off the last owner's sums and onto the new owner's\n" if PF_SUMS else '')
            + '\t\tset_variable = { name = pmr_own value = owner }\n'
            + ('\t\tpmr_pf_own_g = yes\n' if PF_SUMS else '')
            + ('\t\tset_variable = pmr_ownchg   # RESEARCH_MAP: its next update scans every type\n' if RESEARCH_MAP else '')
            + '\t}\n}\n')


def state_turn():
    """pmr_on_monthly_pulse_state's building update, every TICK_EVERY-th pulse of the state (Pat 2026-10-21 12:37Z):
    pmr_ph 1 runs it, then 2 waits a pulse. A state seen the first time (a new game, or a save from before) takes the
    phase after the last state's (pmr_ph_g), so half the states update each month. --obs-pad: in OBS_MONTHLY_YEARS
    (pmr_b1_off) every pulse runs it, as before. Each update counts pmr_xc round OPTS_CYCLE (a state seen the first
    time takes the count after the last state's, pmr_xc_g); all but the last count are the trade-off step's turn
    (pmr_xturn, Pat 19:35Z)."""
    turn = ('\t\t\tif = {\n\t\t\t\tlimit = { NOT = { has_variable = pmr_xc } }\n'
            '\t\t\t\tif = { limit = { NOT = { has_global_variable = pmr_xc_g } } set_global_variable = { name = pmr_xc_g value = 0 } }\n'
            '\t\t\t\tset_variable = { name = pmr_xc value = global_var:pmr_xc_g }\n'
            '\t\t\t\tchange_global_variable = { name = pmr_xc_g add = 1 }\n'
            f'\t\t\t\tif = {{ limit = {{ global_var:pmr_xc_g >= {OPTS_CYCLE} }} set_global_variable = {{ name = pmr_xc_g value = 0 }} }}\n'
            '\t\t\t}\n\t\t\telse = {\n\t\t\t\tchange_variable = { name = pmr_xc add = 1 }\n'
            f'\t\t\t\tif = {{ limit = {{ var:pmr_xc >= {OPTS_CYCLE} }} set_variable = {{ name = pmr_xc value = 0 }} }}\n\t\t\t}}\n'
            f'\t\t\tif = {{ limit = {{ var:pmr_xc < {OPTS_CYCLE - 1} }} set_variable = pmr_xturn }}\n')
    tick = ('\t\t\tset_variable = pmr_month\n' + turn
            + ('\t\t\tif = { limit = { has_variable = pmr_ownchg } remove_variable = pmr_ownchg set_variable = pmr_research }'
               '   # RESEARCH_MAP: a new owner\n' if RESEARCH_MAP else '')
            + "\t\t\tpmr_state_tick = yes   # this state's turn\n"
            + ('\t\t\tif = { limit = { has_variable = pmr_research } remove_variable = pmr_research }\n' if RESEARCH_MAP else '')
            + '\t\t\tremove_variable = pmr_month\n' + XTURN_DONE)
    out = (('\t\tpmr_own_check = yes   # RESEARCH_MAP, PF_SUMS: a state that changed hands\n' if RESEARCH_MAP or PF_SUMS else '')
           + '\t\tif = {\n\t\t\tlimit = { NOT = { has_variable = pmr_ph } }\n'
           '\t\t\tif = { limit = { has_global_variable = pmr_ph_g } remove_global_variable = pmr_ph_g '
           'set_variable = { name = pmr_ph value = 2 } }\n'
           '\t\t\telse = { set_global_variable = pmr_ph_g set_variable = { name = pmr_ph value = 1 } }\n\t\t}\n')
    if OBS_PAD:
        out += '\t\tif = {\n\t\t\tlimit = { has_global_variable = pmr_b1_off }\n' + tick + '\t\t}\n\t\telse_if = {\n'
    else:
        out += '\t\tif = {\n'
    return (out + '\t\t\tlimit = { var:pmr_ph = 1 }\n\t\t\tset_variable = { name = pmr_ph value = 2 }\n' + tick
            + '\t\t}\n\t\telse = { set_variable = { name = pmr_ph value = 1 } }\n')


def opts_call(b, market):
    """The tick's trade-off step (pmr_opts_<b>): for a building with trade-offs (market), on a monthly update only at
    the state's turn (pmr_xturn, OPTS_CYCLE), at every event tick, and for a building not yet set up (pmr_xinit_<b>);
    treatment only, at every update"""
    conds = []
    if market:
        conds.append(f'OR = {{ NOT = {{ has_variable = pmr_month }} has_variable = pmr_xturn NOT = {{ has_variable = pmr_xinit_{b} }} }}')
    if OBS_PARTS_ON:
        conds.append(f'OR = {{ NOT = {{ has_global_variable = pmr_off_opts }} NOT = {{ has_variable = pmr_xinit_{b} }} }}')
    if not conds:
        return f'\tpmr_opts_{b} = yes\n'
    return f'\tif = {{ limit = {{ {" ".join(conds)} }} pmr_opts_{b} = yes }}\n'


def opts_pace(t):
    """The trade-off step's multiplier, lines indented by t: the months since the state's last turn (OPTS_CYCLE), two
    updates at the cycle's first count (pmr_xc 0, after the skipped one), one at the others"""
    def by(updates):
        return every_other(f'change_variable = {{ name = pmr_m multiply = {TICK_EVERY * updates} }}', '',
                           f'change_variable = {{ name = pmr_m multiply = {updates} }}' if updates > 1 else '').strip()
    return f'{t}if = {{ limit = {{ var:pmr_xc = 0 }} {by(2)} }}\n{t}else = {{ {by(1)} }}\n'


def every_other(effect, t, monthly=''):
    """effect, one line indented by t, that makes a step TICK_EVERY months long; --obs-pad runs monthly instead (a
    step of a month, or nothing) in OBS_MONTHLY_YEARS (pmr_b1_off), when every monthly pulse updates"""
    if OBS_PAD:
        return (f'{t}if = {{ limit = {{ NOT = {{ has_global_variable = pmr_b1_off }} }} {effect} }}'
                + (f' else = {{ {monthly} }}' if monthly else '') + '\n')
    return f'{t}{effect}\n'


def pulse_state_effect():
    """pmr_on_monthly_pulse_state's effect, as written (checked by --script-profile)"""
    return (state_turn() + '\t\tpmr_auto_best = yes\n\t\tpmr_principle_bonus = yes\n\t\tpmr_probe_state = yes\n'
            '\t\tpmr_urb_check = yes   # the state Buildings tab\'s own list\n')
PULSE_STATE_HOOK = 'on_monthly_pulse_state = { on_actions = { pmr_on_monthly_pulse_state } }\n'


def profile_pulse_state(buildings):
    """on_actions text: the monthly state pulse split into steps (--script-profile), replacing PULSE_STATE_HOOK."""
    paused = 'trigger = { NOT = { has_global_variable = pmr_ticks_paused } }'
    # this state's turn (state_turn) sets pmr_month for the steps between open and close
    turn = (state_turn().replace("\t\t\tpmr_state_tick = yes   # this state's turn\n", '').replace('\t\t\tremove_variable = pmr_month\n', '')
            .replace(XTURN_DONE, ''))
    steps = [('open', turn + '\t\tset_variable = pmr_bulk\n' + ('' if RELEASE else '\t\tpmr_read_log = yes\n'))]
    steps += [(f't_{short(bk)}', '\t\tif = {\n\t\t\tlimit = { has_variable = pmr_month }\n' + state_tick_type(bk, '\t\t\t') + '\t\t}\n')
              for bk in tick_order(buildings)]
    steps += [('close', '\t\tremove_variable = pmr_bulk\n'
                        '\t\tif = { limit = { has_variable = pmr_month } remove_variable = pmr_month }\n'
                        + XTURN_DONE.replace('\t\t\t', '\t\t', 1))]
    steps += [(k, f'\t\t{e} = yes\n') for k, e in (('auto_best', 'pmr_auto_best'), ('principle', 'pmr_principle_bonus'),
                                                     ('probe', 'pmr_probe_state'), ('urb', 'pmr_urb_check'))]
    return ('# --script-profile: the monthly state pulse one step per on_action, for the script profiler\n'
            'on_monthly_pulse_state = { on_actions = { ' + ' '.join(f'pmr_prof_{k}' for k, _ in steps) + ' } }\n\n'
            + ''.join(f'pmr_prof_{k} = {{\n\t{paused}\n\teffect = {{\n{e}\t}}\n}}\n' for k, e in steps) + '\n')


HISTORY_FRAMES_DOC = """# The AI's lock (frames.LOCK_PURE): the frames vanilla's history names that unlock only while they run. Whether the
# game sets such a frame as history makes the building is not known (no build before this one locked a method history
# names; the share methods history named until q98 were unlocked by a start method on purpose). So at game start,
# before the first tick adopts what each building runs, every locked frame history names is set here where it is not
# running and its gate holds. activate_production_method asks nothing, and a running locked frame unlocks itself.
# Test builds log a HIST line for each frame set: none at all means the game set history's frames itself.

"""


def history_frames(game):
    """(text, entries): pmr_history_frames, no scope, for pmr_on_game_started. One block per state and owner of
    vanilla's history building files, a line per locked frame (frames.GATES) a create_building there names."""
    src = os.path.join(game, 'common', 'history', 'buildings')
    names = sorted(f for f in os.listdir(src) if f.endswith('.txt')) if os.path.isdir(src) and frames.GATES else []

    def creates(nodes):
        for n in nodes:
            if n.key == 'create_building' and n.is_block:
                yield n
            elif n.is_block:
                yield from creates(n.value)

    blocks, count = collections.OrderedDict(), 0
    for fn in names:
        with open(os.path.join(src, fn), encoding='utf-8-sig') as f:
            nodes = pdx.parse(pdx.strip_bom(f.read()))
        for top in nodes:
            for st in (top.value if top.is_block else []):
                if not (st.key or '').startswith('s:') or not st.is_block:
                    continue
                for rs in st.value:
                    if not (rs.key or '').startswith('region_state:') or not rs.is_block:
                        continue
                    made = [pdx.get(cb.value, 'building') for cb in creates(rs.value)]
                    twice = {bn.value for bn in made if bn is not None and sum(1 for x in made if x is not None and x.value == bn.value) > 1}
                    for cb in creates(rs.value):
                        bn, apm = pdx.get(cb.value, 'building'), pdx.get(cb.value, 'activate_production_methods')
                        # a building history makes twice in one state (four in 1.15): which entry's methods the game
                        # keeps is not known, so it is left as the game made it
                        if bn is None or apm is None or not apm.is_block or bn.value in twice:
                            continue
                        for key in pdx.items(apm):
                            gate = frames.GATES.get((bn.value, key))
                            if gate is None:
                                continue
                            spec = f'building_type = {bn.value} production_method = {key}'
                            asks = gate.trigger()
                            line = (f'\t\tif = {{ limit = {{ has_building = {bn.value} NOT = {{ is_production_method_active = {{ {spec} }} }}'
                                    + ('' if asks == 'always = yes' else f' {asks}')
                                    + f' }} activate_production_method = {{ {spec} }} '
                                    'debug_log = "PMR;rec=HIST;date=[TimeKeeper.GetCurrentDate.GetString];'
                                    'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting];'
                                    f'building={bn.value};method={key}" }}\n')
                            lines = blocks.setdefault((st.key, rs.key), [])
                            if line not in lines:
                                lines.append(line)
                                count += 1
    if not count:
        return '', 0
    # pmr_in_tick: the switch is PMR's own, so pmr_on_production_method_changed leaves it alone
    out = [HISTORY_FRAMES_DOC, 'pmr_history_frames = {\n']
    for (st, rs), lines in blocks.items():
        out.append(f'\t{st}.{rs} ?= {{\n\t\tset_variable = {{ name = pmr_in_tick value = yes days = 1 }}\n'
                   + ''.join(lines) + '\t\tremove_variable = pmr_in_tick\n\t}\n')
    out.append('}\n')
    return ''.join(out), count


def history_start_shares(game, start_shares=None):
    """{published path: text}: vanilla's history building files with START_LEVELS raised (a number replaced, so line
    numbers stay vanilla's). Only the files with a level raised are published; the rest is vanilla's, byte for byte.
    Until the method-count rework (Pat 2026-11-10) each create_building also named its start method and shares, so the
    game staffed a building on its own recipe (Pat 2026-10-21 19:31Z, France's ports); history now names the pure frames
    themselves, the vanilla recipes with their own goods and jobs, so nothing is added."""
    src = os.path.join(game, 'common', 'history', 'buildings')
    names = sorted(f for f in os.listdir(src) if f.endswith('.txt')) if os.path.isdir(src) else []
    out = {}
    hits = {key: 0 for key in START_LEVELS}
    for fn in names:
        with open(os.path.join(src, fn), encoding='utf-8-sig', newline='') as f:
            text = f.read()
        raised = False
        for key in START_LEVELS:
            text, n = start_levels(text, key)
            hits[key] += n
            raised = raised or n > 0
        if raised:
            out[f'common/history/buildings/{fn}'] = text
    missed = [k for k, n in hits.items() if n != 1]
    if missed and names:
        raise SystemExit('START_LEVELS: no single owner entry matched for ' + ', '.join('/'.join(k) for k in missed))
    return out


def _block_end(text, k):
    """The position just past the } closing the block whose { ends at k."""
    depth = 1
    while depth:
        depth += {'{': 1, '}': -1}.get(text[k], 0)
        k += 1
    return k


def start_levels(text, key):
    """(text, matches): START_LEVELS[key] added to the levels of its owner entry in one history file's text, inside
    s:<state> > region_state:<tag> > the create_building of the building > add_ownership."""
    (st, tag, bk), ((kind, otype, oreg), add) = key, START_LEVELS[key]
    found = []   # (start, end) of each matching levels number
    for sm in re.finditer(rf'\bs:{st}\s*=\s*\{{', text):
        se = _block_end(text, sm.end())
        for rm in re.finditer(rf'\bregion_state:{tag}\s*=\s*\{{', text[sm.end():se]):
            r0 = sm.end() + rm.end()
            re_ = _block_end(text, r0)
            for cm in re.finditer(r'\bcreate_building\s*=\s*\{', text[r0:re_]):
                c0 = r0 + cm.end()
                ce = _block_end(text, c0)
                if not re.search(rf'\bbuilding\s*=\s*"?{bk}"?\s', text[c0:ce]):
                    continue
                om = re.search(r'\badd_ownership\s*=\s*\{', text[c0:ce])
                if not om:
                    continue
                o0 = c0 + om.end()
                oe = _block_end(text, o0)
                k = o0
                while True:
                    em = re.compile(r'\b(building|country)\s*=\s*\{').search(text, k, oe)
                    if not em:
                        break
                    e0, ee = em.end(), _block_end(text, em.end())
                    body = text[e0:ee]
                    if em.group(1) == kind and (kind == 'country' or (
                            re.search(rf'\btype\s*=\s*"?{otype}"?\s', body) and re.search(rf'\bregion\s*=\s*"?{oreg}"?\s', body))):
                        lm = re.search(r'\blevels\s*=\s*(\d+)', body)
                        if lm:
                            found.append((e0 + lm.start(1), e0 + lm.end(1)))
                    k = ee
    if len(found) == 1:
        a, b = found[0]
        text = text[:a] + str(int(text[a:b]) + add) + text[b:]
    return text, len(found)


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
             '# Building scope (on_building_built: a new building, its first level). It carries no "less" modifier yet,\n'
             '# whatever its state still keeps of one gone before (the method-count rework, frames.py).\n'
             'pmr_frame_new_building = {\n'
             + ''.join(f'\t{"if" if i == 0 else "else_if"} = {{\n\t\tlimit = {{ is_building_type = {bk} }}\n\t\tstate = {{\n'
                       + frames.clear_vars(FRAMES[bk], '\t\t\t') + '\t\t}\n\t}\n'
                       for i, bk in enumerate([x for x in buildings if x in FRAMES]))
             + '}\n\n'
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
    o.append('}\n\n')
    # perf review S-2: a site searches only its own group's 45 types, any other building leaves after the group checks
    for bk in buildings:
        b = short(bk)
        o.append(f'# Building scope: a retool site of {bk} completed a level; tick it.\npmr_tick_parent_{b} = {{\n'
                 f'\tstate = {{\n\t\t{flush_log("RETOOL_LEVEL", bk, mine=f"OR = {{ owner = {{ is_player = yes }} has_variable = pmr_abroad_{b} }}")}\n'
                 f'\t\tif = {{ limit = {{ {live(bk)} }} pmr_tick_{b} = yes }}\n\t}}\n}}\n\n')
    sites = {'bg_pmr_retool': lambda b: [t for j, t in enumerate(priv_slots(b), 1) if j != ABROAD_SLOT],
             'bg_pmr_retool_abroad': lambda b: [priv_slots(b)[ABROAD_SLOT - 1]],
             'bg_pmr_retool_gov': lambda b: [f'building_pmr_retool_gov_{b}'],
             'bg_pmr_retool_gov_abroad': lambda b: [f'building_pmr_retool_gova_{b}']}
    o.append('# Building scope, for a retool pseudo-building that just completed a level: tick its parent.\n'
             'pmr_tick_parent_of_retool = {\n')
    for g, (grp, types) in enumerate(sites.items()):
        o.append(f'\t{"if" if g == 0 else "else_if"} = {{\n\t\tlimit = {{ is_building_group = {grp} }}\n')
        for i, bk in enumerate(buildings):
            b = short(bk)
            ts = types(b)
            cond = f'is_building_type = {ts[0]}' if len(ts) == 1 else 'OR = { ' + ' '.join(f'is_building_type = {t}' for t in ts) + ' }'
            o.append(f'\t\t{"if" if i == 0 else "else_if"} = {{ limit = {{ {cond} }} pmr_tick_parent_{b} = yes }}\n')
        o.append('\t}\n')
    o.append('}\n\n'
             '# State scope: tick every PMR building in the state. Run state by state over a country (monthly, on\n'
             '# research, at game start), so the country totals wait for pmr_c_sum_all once the states are done.\n'
             'pmr_state_tick = {\n\tset_variable = pmr_bulk\n'
             + ('' if RELEASE else '\tpmr_read_log = yes\n')
             + '\t# power plants and railways first: they set pmr_elec and pmr_rail (SUPPLY) for the rest\n')
    # bug review q48, P2-2: a building gone mid-retool (downsized to nothing) leaves no open retool, no stale recipe mix
    # (a rebuild starts on the newest recipe, as a new one), no abroad flag, no books and no step-down mark. It runs once,
    # as it removes pmr_mix_<b>.
    for bk in tick_order(buildings):
        o.append(state_tick_type(bk))
    o.append('\tremove_variable = pmr_bulk\n}\n\n'
             '# State scope (on_acquired_technology): tick only the buildings whose best recipe the research\n'
             '# changed, and any not seen yet. The rest wait for the month; until then a newly unlocked\n'
             '# trade-off shows as unavailable on the panel, whose shares move only monthly anyway.\n'
             'pmr_state_research = {\n\tset_variable = pmr_bulk\n\tset_variable = pmr_research\n')
    for bk in buildings:
        b = short(bk)
        o.append(f'\tif = {{\n\t\tlimit = {{ {live(bk)} }}\n'
                 f'\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_mix_{b} }} }} pmr_tick_{b} = yes }}\n'
                 f'\t\telse = {{\n\t\t\tpmr_best_{b} = yes\n'
                 f'\t\t\tif = {{ limit = {{ {moved(b)} }} pmr_tick_{b} = yes }}\n'
                 '\t\t}\n\t}\n')
    o.append('\tremove_variable = pmr_bulk\n\tremove_variable = pmr_research\n}\n\n'
             '# State scope, another country\'s state where the player owns levels (pmr_abroad_any), when the\n'
             '# player researches: the same, for the buildings the player owns levels in.\n'
             'pmr_state_research_abroad = {\n\tset_variable = pmr_bulk\n\tset_variable = pmr_research\n')
    for bk in buildings:
        b = short(bk)
        o.append(f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_abroad_{b} has_variable = pmr_mix_{b} {live(bk)} }}\n'
                 f'\t\tpmr_best_{b} = yes\n'
                 f'\t\tif = {{ limit = {{ {moved(b)} }} pmr_tick_{b} = yes }}\n'
                 '\t}\n')
    o.append('\tremove_variable = pmr_bulk\n\tremove_variable = pmr_research\n}\n\n'
             '# Country scope: the country\'s totals for every PMR building type (Buildings tab rows).\n'
             'pmr_c_sum_every = {\n\tset_variable = pmr_c_abroad\n')
    for bk in buildings:
        o.append(f'\tpmr_c_sum_{short(bk)} = yes\n')
    o.append('\tremove_variable = pmr_c_abroad\n}\n\n'
             '# Country scope: no Buildings tab totals (a country no player views; pmr_c_sum_all).\n'
             'pmr_c_clear = {\n')
    for bk in buildings:
        o.append(f'\tpmr_c_clear_{short(bk)} = yes\n')
    o.append('}\n\n'
             '# The same for a player\'s country only (monthly, on research). Another country\'s totals, left from a save\n'
             '# made before review 9 (every country\'s, from game start) or by a player gone, are dropped at its next pulse.\n'
             'pmr_c_sum_all = {\n\tif = {\n\t\tlimit = { pmr_c_viewer = yes }\n'
             '\t\tpmr_c_sum_every = yes\n'
             '\t\tdebug_log = "PMR;rec=CSUM;date=[TimeKeeper.GetCurrentDate.GetString]"\n'
             f'\t}}\n\telse_if = {{\n\t\tlimit = {{ has_variable = pmr_c_level_{short(buildings[0])} }}\n'
             '\t\tpmr_c_clear = yes\n'
             '\t\tdebug_log = "PMR;rec=CCLEAR;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting]"\n'
             '\t}\n}\n')
    if not RELEASE:
        counts = ('pmr_sk_skip', 'pmr_sk_ran', 'pmr_sk_checked')
        o.append('\n# Country scope, monthly (test builds): the player\'s PMR building ticks since the last SKIP line that\n'
                 '# skipped the level accounting (S3, pmr_recount_<b>), ran it, and ran it as a check (SKIP_MISS).\n'
                 'pmr_skip_report = {\n\tif = {\n\t\tlimit = { is_player = yes }\n'
                 # the month's frames put back after the AI or the game changed one, all countries (pmr_count_undo)
                 '\t\tif = { limit = { has_global_variable = pmr_undo } set_variable = { name = pmr_undo_v value = global_var:pmr_undo } '
                 'set_global_variable = { name = pmr_undo value = 0 } }\n'
                 '\t\telse = { set_variable = { name = pmr_undo_v value = 0 } }\n'
                 # of those, the ones found on their group's first method (pmr_count_undo_first)
                 '\t\tif = { limit = { has_global_variable = pmr_undo_f } set_variable = { name = pmr_undo_fv value = global_var:pmr_undo_f } '
                 'set_global_variable = { name = pmr_undo_f value = 0 } }\n'
                 '\t\telse = { set_variable = { name = pmr_undo_fv value = 0 } }\n'
                 '\t\tdebug_log = "PMR;rec=UNDO;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
                 "n=[THIS.Var('pmr_undo_v').GetValue|0];first=[THIS.Var('pmr_undo_fv').GetValue|0]\"\n"
                 '\t\tremove_variable = pmr_undo_v\n'
                 '\t\tremove_variable = pmr_undo_fv\n'
                 + ('' if not SOLO_GATE else
                    ''.join(f'\t\tif = {{ limit = {{ has_global_variable = pmr_sg_{n} }} set_variable = {{ name = pmr_sg_{n}_v value = global_var:pmr_sg_{n} }} '
                            f'set_global_variable = {{ name = pmr_sg_{n} value = 0 }} }}\n'
                            f'\t\telse = {{ set_variable = {{ name = pmr_sg_{n}_v value = 0 }} }}\n' for n in SOLO_COUNTS)
                    + '\t\tdebug_log = "PMR;rec=SOLO;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
                    + ';'.join(f"{n}=[THIS.Var('pmr_sg_{n}_v').GetValue|0]" for n in SOLO_COUNTS) + '"\n'
                    + ''.join(f'\t\tremove_variable = pmr_sg_{n}_v\n' for n in SOLO_COUNTS))
                 + '\t\tdebug_log = "PMR;rec=SKIP;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
                 + ';'.join(f"{n[7:]}=[THIS.Var('{n}').GetValue|0]" for n in counts) + '"\n'
                 + ''.join(f'\t\tset_variable = {{ name = {n} value = 0 }}\n' for n in counts) + '\t}\n}\n')
    return ''.join(o)


# State scope: the state has electricity (SUPPLY's flag, set by its turn; pmr_auto_best makes sure it is set).
ELEC_MADE = 'var:pmr_elec = 1'
AUTO_TRIP = 3   # AUTO_BEST switches one building may make from method changes in a day before it waits for the next


def supply_blends(game, auto, pms, group_src):
    """SUPPLY_BLEND: the blend methods (text), their names (loc lines), and BLEND_INFO for auto_best_effects. Each blend
    is the two ladder methods' modifiers weighted k/BLEND_STEPS, so its goods, jobs and bureaucracy sit between them."""
    hist = ''
    src = os.path.join(game, 'common', 'history', 'buildings')
    if os.path.isdir(src):
        hist = ''.join(open(os.path.join(src, f), encoding='utf-8-sig').read() for f in sorted(os.listdir(src)) if f.endswith('.txt'))

    def mods(node):
        """{(section, scaling, key): value} of a method's numeric modifiers"""
        out = {}
        for sec in node.value:
            if not sec.is_block or not sec.key.endswith('_modifiers'):
                continue
            for sc in sec.value:
                if not sc.is_block:
                    continue
                for m in sc.value:
                    if not m.is_block and m.key:
                        try:
                            out[(sec.key, sc.key, m.key)] = float(m.value)
                        except ValueError:
                            pass
        return out

    def num(x):
        return f'{x:.3f}'.rstrip('0').rstrip('.') if x != int(x) else str(int(x))

    text, loc = [], []
    for bk, (g, targets) in SUPPLY_BLEND.items():
        entry = [e for e in auto.get(bk, []) if e[0] == g]
        if len(entry) != 1 or entry[0][2]:
            raise SystemExit(f'SUPPLY_BLEND: {bk} {g} is not a technology ladder of AUTO_BEST; update SUPPLY_BLEND')
        _g, order, _by_law, techs, elec = entry[0]
        ladder = list(reversed(order))   # oldest first
        if elec:
            raise SystemExit(f'SUPPLY_BLEND: {g} has an electric method; the blend asks no electricity')
        if not set(targets) <= set(ladder[1:]):
            raise SystemExit(f'SUPPLY_BLEND: {sorted(set(targets) - set(ladder[1:]))} not past the first method of {g}')
        m = [mods(pms[p][0]) for p in ladder]
        adds, keys = {}, {}
        for i in [ladder.index(t) for t in targets]:
            a, b = m[i - 1], m[i]
            adds[i] = sorted({k[2][len('goods_input_'):-len('_add')] for k in b
                              if k[2].startswith('goods_input_') and k[2].endswith('_add') and b[k] > a.get(k, 0)})
            tex = pdx.get(pms[ladder[i]][0].value, 'texture')
            for k in range(1, BLEND_STEPS):
                key = f'pm_pmr_blend_{short(bk)}_{i}_{k}'
                keys[(i, k)] = key
                t = k / BLEND_STEPS
                body = {}
                for mk in sorted(set(a) | set(b), key=lambda x: (x[0], x[1], x[2])):
                    v = a.get(mk, 0) * (1 - t) + b.get(mk, 0) * t
                    if abs(v) > 1e-9:
                        body.setdefault(mk[0], {}).setdefault(mk[1], []).append(f'\t\t\t{mk[2]} = {num(v)}\n')
                text.append(f'{key} = {{\n'
                            + (f'\ttexture = "{tex.value}"\n' if tex is not None else '')
                            + (f'\tunlocking_technologies = {{ {" ".join(techs[ladder[i]])} }}\n' if techs[ladder[i]] else '')
                            + f'\tunlocking_production_methods = {{ {key} }}  # PMR: only PMR sets it (SUPPLY_BLEND)\n'
                            + '\tis_hidden_when_unavailable = yes\n'
                            + ''.join(f'\t{sec} = {{\n' + ''.join(f'\t\t{sc} = {{\n' + ''.join(lines) + '\t\t}\n'
                                                                   for sc, lines in scs.items()) + '\t}\n'
                                      for sec, scs in body.items())
                            + '}\n')
                loc.append(f' {key}:0 "${ladder[i]}$ {k * 100 // BLEND_STEPS}%"')
        gsrc, gpm = group_src[g]
        gsrc.inserts.append((gpm.end - 1, ''.join(f'\t{keys[(i, k)]}  # PMR: blend toward {ladder[i]} (SUPPLY_BLEND)\n\t'
                                                  for i in sorted(adds) for k in range(1, BLEND_STEPS))))
        # a blended method no history file starts: self-locked too, so the AI can't skip the blend to it
        for p in targets:
            if not re.search(r'["\s{]' + re.escape(p) + r'["\s}]', hist):
                n, psrc = pms[p]
                psrc.inserts.append((n.end - 1, f'\tunlocking_production_methods = {{ {p} }}  # PMR: only PMR sets it (SUPPLY_BLEND)\n'))
        BLEND_INFO[(bk, g)] = {'ladder': ladder, 'techs': techs, 'adds': adds, 'keys': keys}
    return '\n'.join(text), loc


def blend_effect(bk, g):
    """State scope: SUPPLY_BLEND's group g of bk on its place (pmr_bp_<b>: BLEND_STEPS x a ladder index, or a blend
    between). The newest ladder method the owner has is its place, or, for a blended one, the range from the method
    before it, where the place steps once in the state's update month (pmr_ph 2, guarded by pmr_bs_<b>)."""
    info, b, n = BLEND_INFO[(bk, g)], short(bk), BLEND_STEPS
    ladder, techs, adds, keys = info['ladder'], info['techs'], info['adds'], info['keys']
    top = len(ladder) - 1
    pos = f'var:pmr_bp_{b}'
    spec = lambda key: f'building_type = {bk} production_method = {key}'   # noqa: E731
    method = {i * n: ladder[i] for i in range(len(ladder))}
    method.update({(i - 1) * n + k: keys[(i, k)] for (i, k) in keys})

    def has(i):
        return ' '.join(f'has_technology_researched = {t}' for t in techs[ladder[i]]) or 'always = yes'

    def supplied(i):
        return ' '.join(f'market ?= {{ mg:{gd} ?= {{ market_goods_sell_orders > 0 pmr_blend_fill >= {BLEND_UP} }} }}'
                        for gd in adds[i]) or 'always = yes'

    def short_of(i):
        return ('OR = { ' + ' '.join(f'market ?= {{ mg:{gd} ?= {{ pmr_blend_fill <= {BLEND_DOWN} }} }}' for gd in adds[i])
                + ' }') if adds[i] else 'always = no'
    o = [f'# State scope: {g} of {bk} on its blend (SUPPLY_BLEND).\npmr_blend_{b} = {{\n'
         '\t# the newest ladder method the owner has the technologies for\n'
         '\tset_variable = { name = pmr_bn value = 0 }\n']
    for j, i in enumerate(range(top, 0, -1)):
        o.append(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ owner = {{ {has(i)} }} }} set_variable = {{ name = pmr_bn value = {i} }} }}\n')
    o.append('\t# where it stands, read from what runs the first time\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = pmr_bp_{b} }} }}\n\t\tset_variable = {{ name = pmr_bp_{b} value = 0 }}\n')
    for v, key in sorted(method.items()):
        if v:
            o.append(f'\t\tif = {{ limit = {{ is_production_method_active = {{ {spec(key)} }} }} '
                     f'set_variable = {{ name = pmr_bp_{b} value = {v} }} }}\n')
    o.append('\t}\n'
             '\t# its range: the newest method, or for a blended one from the method before it; outside it, to its nearer end\n')
    for j, i in enumerate(range(top, -1, -1)):
        lo = (i - 1) * n if i in adds else i * n
        o.append(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ var:pmr_bn = {i} }} '
                 f'set_variable = {{ name = pmr_bp_lo value = {lo} }} set_variable = {{ name = pmr_bp_hi value = {i * n} }} }}\n')
    o.append(f'\tif = {{ limit = {{ {pos} < var:pmr_bp_lo }} set_variable = {{ name = pmr_bp_{b} value = var:pmr_bp_lo }} }}\n'
             f'\tif = {{ limit = {{ {pos} > var:pmr_bp_hi }} set_variable = {{ name = pmr_bp_{b} value = var:pmr_bp_hi }} }}\n'
             '\t# the state\'s update (pmr_ph 2 after state_turn), once: a step toward the newest while the goods it adds are\n'
             '\t# in supply, back while one is short\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_ph var:pmr_ph = 2 NOT = {{ has_variable = pmr_bs_{b} }} }}\n'
             f'\t\tset_variable = {{ name = pmr_bs_{b} days = {30 * TICK_EVERY - 15} }}\n'
             '\t\tset_variable = { name = pmr_bd value = 0 }\n')
    for j, i in enumerate(sorted(adds, reverse=True)):
        o.append(f'\t\t{"if" if j == 0 else "else_if"} = {{\n\t\t\tlimit = {{ var:pmr_bn = {i} }}\n'
                 f'\t\t\tif = {{ limit = {{ {pos} < var:pmr_bp_hi {supplied(i)} }} set_variable = {{ name = pmr_bd value = 1 }} }}\n'
                 f'\t\t\telse_if = {{ limit = {{ {pos} > var:pmr_bp_lo {short_of(i)} }} set_variable = {{ name = pmr_bd value = -1 }} }}\n'
                 '\t\t}\n')
    fills = sorted({gd for gl in adds.values() for gd in gl})
    o.append(f'\t\tchange_variable = {{ name = pmr_bp_{b} add = var:pmr_bd }}\n'
             + ('' if RELEASE else
                '\t\t# the BLEND line: every move, and each update of the capital in a blended range (a hold: step=0)\n'
                '\t\tif = {\n\t\t\tlimit = { var:pmr_bp_hi > var:pmr_bp_lo OR = { NOT = { var:pmr_bd = 0 } is_capital = yes } }\n'
                + ''.join(f'\t\t\tset_variable = {{ name = pmr_bf_{gd} value = pmr_sv_bfill_{gd} }}\n' for gd in fills)
                + f'\t\t\tdebug_log = "PMR;rec=BLEND;date=[TimeKeeper.GetCurrentDate.GetString];'
                f'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting];building={bk};'
                f"pos=[THIS.Var('pmr_bp_{b}').GetValue|0];step=[THIS.Var('pmr_bd').GetValue|0];newest=[THIS.Var('pmr_bn').GetValue|0]"
                + ''.join(f";fill_{gd}=[THIS.Var('pmr_bf_{gd}').GetValue|2]" for gd in fills) + '"\n'
                + ''.join(f'\t\t\tremove_variable = pmr_bf_{gd}\n' for gd in fills) + '\t\t}\n')
             + '\t\tremove_variable = pmr_bd\n\t}\n'
             '\t# the method of that place, unless it runs\n')
    for j, (v, key) in enumerate(sorted(method.items())):
        o.append(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ {pos} = {v} }} '
                 f'if = {{ limit = {{ NOT = {{ is_production_method_active = {{ {spec(key)} }} }} }} '
                 f'activate_production_method = {{ {spec(key)} }} '
                 f'if = {{ limit = {{ owner = {{ is_player = yes }} }} {flush_log("AUTO", bk, ";method=" + key)} }} }} }}\n')
    o.append('\tremove_variable = pmr_bn\n\tremove_variable = pmr_bp_lo\n\tremove_variable = pmr_bp_hi\n}\n\n')
    return ''.join(o)


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
            if (bk, g) in BLEND_INFO:
                o.append(f'\t# {g}, following supply (SUPPLY_BLEND)\n\tpmr_blend_{short(bk)} = yes\n')
                continue
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
    o += [blend_effect(bk, g) for bk, g in BLEND_INFO]
    o.append('# State scope (monthly, on research, at game start): every such building of the state.\n'
             'pmr_auto_best = {\n\tpmr_supply_once = yes\n\tset_variable = pmr_auto_busy\n')
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


RESEARCH_LOOK_DAYS = 365   # RESEARCH_MAP: a country's own yearly look at its technologies (the hook's safety net)

# RESEARCH_MAP's hooks in ON_ACTIONS: (text, its replacement), each found once.
RESEARCH_MAP_HOOKS = [
    # a technology: only the types it touches
    ('\t\t\tevery_scope_state = {\n\t\t\t\tpmr_state_research = yes\n\t\t\t\tpmr_auto_best = yes\n\t\t\t}\n',
     '\t\t\tpmr_research_look = yes   # RESEARCH_MAP: the building types this technology can move\n'
     '\t\t\tpmr_research_marked = yes\n'),
    # the laws the rules name, monthly; once a year the technologies too, in case one arrived without the hook above
    # (a save from before the map takes its one full pass here)
    ('\teffect = {\n\t\tpmr_c_sum_all = yes\nSKIP_REPORT',
     '\teffect = {\n\t\t# RESEARCH_MAP: a law the newest-recipe rules name, passed or dropped; yearly, the technologies as well\n'
     f'\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_rml }} }} set_variable = {{ name = pmr_rml days = {RESEARCH_LOOK_DAYS} }} pmr_research_look = yes }}\n'
     '\t\telse = { pmr_research_laws = yes }\n'
     '\t\tpmr_research_marked = yes\n\t\tpmr_c_sum_all = yes\nSKIP_REPORT'),
    # game start: what each country holds is seen (every state is ticked there anyway)
    ('\t\t\t# A day later the players exist: their totals, buildings abroad included (pmr.1).\n',
     '\t\t\tpmr_research_seen = yes   # RESEARCH_MAP\n'
     '\t\t\t# A day later the players exist: their totals, buildings abroad included (pmr.1).\n')]


def research_map_effects(buildings, auto):
    """RESEARCH_MAP. Country scope:
      pmr_research_look    marks the building types (pmr_rmk_<b>) a technology the country holds, or a law it has or
                           has dropped, since the last look can move the newest recipe of; pmr_rmk_auto where an
                           AUTO_BEST ladder names the technology; pmr_rmk_any with any of them. pmr_tk_<technology>
                           and pmr_lw_<law> on the country keep what was seen.
      pmr_research_laws    the laws alone (the country's monthly pulse)
      pmr_research_marked  the research pass of the marked types, state by state where one stands, then the marks go
      pmr_research_seen    game start: what the country holds is seen and nothing marked (every state is ticked there)
    State scope: pmr_research_<b>, one type's part of pmr_state_research."""
    by_tech, by_law = collections.defaultdict(list), collections.defaultdict(list)
    always = [short(bk) for bk in buildings if RESEARCH_OTHER.get(short(bk))]
    for bk in buildings:
        b = short(bk)
        for t in RESEARCH_TECHS.get(b, []):
            by_tech[t].append(b)
        for x in RESEARCH_LAWS.get(b, []):
            by_law[x].append(b)
    auto_techs = {x for gl in auto.values() for _g, order, _by_law, techs, _elec in gl for p in order for x in techs[p]}
    # Only a type that a technology, a law or RESEARCH_OTHER marks can carry pmr_rmk_<b>; the others are not tested
    # (q103 X1: two load-time "used but never set" notes, and a test a month for nothing).
    marked = set(always) | {b for bs in by_tech.values() for b in bs} | {b for bs in by_law.values() for b in bs}

    def mark(bs, also=''):
        return ' '.join(['set_variable = pmr_rmk_any'] + [f'set_variable = pmr_rmk_{b}' for b in bs]) + also
    o = ['\n# ===== research by technology (RESEARCH_MAP, performance review 12)\n\n'
         '# Country scope: mark the building types a newly held technology or a changed law can move the newest recipe of.\n'
         'pmr_research_look = {\n']
    if always:   # a gate the map does not follow: these are scanned at every look, as before
        o.append(f'\t{mark(always)}\n')
    for t in sorted(set(by_tech) | auto_techs):
        o.append(f'\tif = {{ limit = {{ has_technology_researched = {t} NOT = {{ has_variable = pmr_tk_{t} }} }} '
                 f'set_variable = pmr_tk_{t} {mark(by_tech.get(t, []), " set_variable = pmr_rmk_auto" if t in auto_techs else "")} }}\n')
    o.append('\tpmr_research_laws = yes\n}\n\n'
             '# Country scope: the same for the laws the rules name, either way.\n'
             'pmr_research_laws = {\n')
    for x in sorted(by_law):
        o.append(f'\tif = {{ limit = {{ has_law_or_variant = law_type:{x} NOT = {{ has_variable = pmr_lw_{x} }} }} '
                 f'set_variable = pmr_lw_{x} {mark(by_law[x])} }}\n'
                 f'\telse_if = {{ limit = {{ has_variable = pmr_lw_{x} NOT = {{ has_law_or_variant = law_type:{x} }} }} '
                 f'remove_variable = pmr_lw_{x} {mark(by_law[x])} }}\n')
    o.append('}\n\n'
             '# Country scope: the marked types\' research pass, in the states that have one.\n'
             'pmr_research_marked = {\n\tif = {\n\t\tlimit = { has_variable = pmr_rmk_any }\n\t\tremove_variable = pmr_rmk_any\n'
             + ('' if RELEASE else '\t\tpmr_rm_count = { N = pmr_rm_p }\n'))
    for bk in buildings:
        b = short(bk)
        if b not in marked:
            continue
        o.append(f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_rmk_{b} }}\n\t\t\tremove_variable = pmr_rmk_{b}\n'
                 f'\t\t\tevery_scope_state = {{ limit = {{ has_building = {bk} b:{bk} = {{ level >= 1 }} }} pmr_research_{b} = yes }}\n\t\t}}\n')
    o.append('\t\tif = {\n\t\t\tlimit = { has_variable = pmr_rmk_auto }\n\t\t\tremove_variable = pmr_rmk_auto\n'
             '\t\t\tevery_scope_state = { pmr_auto_best = yes }\n\t\t}\n\t}\n}\n\n'
             '# Country scope, game start: every technology and law it holds is seen, nothing is marked.\n'
             'pmr_research_seen = {\n\tpmr_research_look = yes\n'
             + ''.join(f'\tif = {{ limit = {{ has_variable = pmr_rmk_{x} }} remove_variable = pmr_rmk_{x} }}\n'
                       for x in ['any', 'auto'] + [short(bk) for bk in buildings if short(bk) in marked]) + '}\n\n')
    for bk in buildings:
        b = short(bk)
        o.append(f'# State scope: the research pass of {bk} (pmr_state_research\'s part for it).\n'
                 f'pmr_research_{b} = {{\n\tset_variable = pmr_bulk\n\tset_variable = pmr_research\n'
                 + ('' if RELEASE else '\tpmr_rm_count = { N = pmr_rm_r }\n') +
                 f'\tif = {{ limit = {{ NOT = {{ has_variable = pmr_mix_{b} }} }} pmr_tick_{b} = yes }}\n'
                 f'\telse = {{\n\t\tpmr_best_{b} = yes\n'
                 f'\t\tif = {{ limit = {{ {moved(b)} }} pmr_tick_{b} = yes }}\n\t}}\n'
                 '\tremove_variable = pmr_bulk\n\tremove_variable = pmr_research\n}\n\n')
    if not RELEASE:
        o.append(RMAP_COUNT)
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
            if LEAN_CHECKS:
                # LEAN_CHECKS: a state that can earn no bonus (no such building, or its owner's bloc without the
                # principle) and has none standing leaves on this test; the steps above would have changed nothing
                eff[-1] = ('\tif = {\n\t\tlimit = { OR = {\n'
                           f'\t\t\tAND = {{ has_building = {bk} owner = {{ power_bloc ?= {{ has_principle = principle:{principle} }} }} }}\n'
                           + ''.join(f'\t\t\tAND = {{ has_variable = {m}_v var:{m}_v > 0 }}\n' for m in (thr, inf))
                           + '\t\t} }\n' + ''.join('\t' + ln for ln in eff[-1].splitlines(True)) + '\t}\n')
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


def vanilla_compat(game, treated, auto_groups_of, groups, pms, group_users, drop_base, split_info=None,
                   frame_extras=None):
    """Returns (scripted triggers, {published path: shadowed vanilla file}, [report lines]). frame_extras: building ->
    {target p: the job versions of its union frame} (frames.extra_union_keys)."""
    split_info = split_info or {}
    frame_extras = frame_extras or {}

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
    # With the split a recipe of such a building is the pure frame of (recipe, no automation) only: a check on it means
    # any pair built on it. Method-count rework: and any union frame standing for one of those (a blended building), in
    # any of its job versions.
    alias = {}
    for bk, _bn, _s, recipes, _g0, _pg in treated:
        for p, r in enumerate(recipes, 1):
            base = r.base.key if isinstance(r, PairRecipe) else r.key
            alias.setdefault(base, [base])
            alias[base] += (([r.key] if isinstance(r, PairRecipe) else []) + [f'pm_pmr_union_{short(bk)}_{p}']
                            + frame_extras.get(bk, {}).get(p, []))
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
                    p = drop_base.get(n.value, n.value)   # a dropped principle variant: the recipe it replaced
                    rep = (f'pmr_has_{p} = yes' if p in runs or p in alias else f'has_active_production_method = {p}')
                    used.add(p)
                    src.cuts.append((n.start, n.end))
                    src.inserts.append((n.start, rep))
                continue
            if n.key == 'is_production_method_active':
                kv = {c.key: c.value for c in n.value if c.key}
                p, b = kv.get('production_method'), kv.get('building_type')
                p = drop_base.get(p, p)
                if p in runs or p in alias:
                    rep = f'AND = {{ has_building = {b} b:{b} = {{ pmr_has_{p} = yes }} }}'
                elif p != kv.get('production_method'):
                    rep = f'is_production_method_active = {{ building_type = {b} production_method = {p} }}'
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
            if idx:
                # a level on a target (a pair with the split) that runs a method of p's kind (pmr_lv_<i>_<b>, the state's)
                lvs = [f'pmr_lv_{i}_{short(bk)}' for i in idx]
                alts.append(f'\t\tAND = {{\n\t\t\tis_building_type = {bk}\n\t\t\tstate = {{ OR = {{ '
                            + ' '.join(f'AND = {{ has_variable = {x} var:{x} > 0 }}' for x in lvs) + ' } }\n\t\t}\n')
        trig.append(f'pmr_has_{p} = {{\n' + (f'\tOR = {{\n{"".join(alts)}\t}}\n' if alts else '\talways = no\n') + '}\n\n')
    for p in sorted(used & set(alias)):
        trig.append(f'pmr_has_{p} = {{\n\tOR = {{\n'
                    + ''.join(f'\t\thas_active_production_method = {x}\n' for x in alias[p]) + '\t}\n}\n\n')
    return ''.join(trig), files, lines


# ---------------------------------------------------------------------------------------------
# Building panel

def is_type(bk):
    return f"ObjectsEqual(Building.GetBuildingType, GetBuildingType('{bk}').Self)"


# Perf review 5, G-2: the HUD marks each PMR type (pmr_t_<key>) and each AUTO_BEST type PMR doesn't retool (pmr_a_<key>)
# in the GUI variable system, as it marks the retool sites (patch_hud_flags), so "is this a PMR type" is one lookup, not
# 45 type tests. Vanilla 1.14.5 tests flags the same way (building_browser_panel.gui, Concatenate + Exists).
TYPE_FLAGS = []   # (prefix, types), set before the GUI is patched


def any_type(buildings):
    """Building context: whether its type is one of `buildings`. The type flags where they cover the set exactly, else
    Or() over the types, nested two at a time."""
    want = set(buildings)
    fams = [(pre, ts) for pre, ts in TYPE_FLAGS if ts and ts <= want]
    if fams and set().union(*(ts for _p, ts in fams)) == want:
        return any_of([f"GetVariableSystem.Exists(Concatenate('{pre}', Building.GetBuildingType.GetKey))" for pre, _t in fams])
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


# A retool site is a GUI variable of its own key, set once as the game's HUD is made (patch_hud_flags): one lookup an
# item, where a test against all 180 site types cost about 1,000 calls (perf review 4, G-1; Pat 2026-10-19 16:32Z)
SITE_HIDDEN = {'Building': 'Not(GetVariableSystem.Exists(Building.GetBuildingType.GetKey))',
               'BuildingType': 'Not(GetVariableSystem.Exists(BuildingType.GetKey))'}
HUD_ANCHOR = '\t# topbar / alerts / timemanip\n\tvbox = {\n'


def patch_hud_flags(text, site_types):
    """ingame_hud.gui: a widget that, as the HUD is made, marks every retool site type in the GUI variable system
    (SITE_HIDDEN), before any list that hides them can open."""
    if text.count(HUD_ANCHOR) != 1:
        raise SystemExit('ingame_hud.gui: the topbar vbox moved; update patch_hud_flags')
    keys = sorted(site_types) + [pre + t for pre, ts in TYPE_FLAGS for t in sorted(ts)]
    flags = ''.join(f"\t\t\ton_start = \"[GetVariableSystem.Set('{t}', 'yes')]\"\n" for t in keys)
    return text.replace(HUD_ANCHOR, '\t# PMR: every retool site type marked once, for the lists that hide them\n'
                        '\twidget = {\n\t\tsize = { 0 0 }\n\t\talwaystransparent = yes\n'
                        '\t\tstate = {\n\t\t\tname = pmr_site_flags\n\t\t\ttrigger_on_create = yes\n'
                        + flags + '\t\t}\n\t}\n\n' + HUD_ANCHOR)


def patch_hud_gov_all(text):
    """ingame_hud.gui: Retool Government Levels asks first (Pat 2026-10-21 21:18Z: "do you want to re-tool all government
    OWNED buildings and the amount of buildings it will queue up"), in vanilla's confirmation window style
    (popups.gui default_confirmation_window), over the side panels; GOV_ALL_ASK opens it (patch_browser_retool_all)."""
    if text.count(HUD_ANCHOR) != 1:
        raise SystemExit('ingame_hud.gui: the topbar vbox moved; update patch_hud_gov_all')
    i = '\t'
    close = f"onclick = \"[GetVariableSystem.Clear('{GOV_ALL_ASK}')]\""
    return text.replace(HUD_ANCHOR, f'{i}# PMR: Retool Government Levels, confirm (patch_hud_gov_all)\n'
                        f'{i}container = {{\n{i}\tvisible = "[GetVariableSystem.Exists(\'{GOV_ALL_ASK}\')]"\n'
                        f'{i}\tparentanchor = center\n{i}\tusing = clickthrough_blocker\n'
                        f'{i}\tbackground = {{\n{i}\t\tusing = default_background\n{i}\t}}\n'
                        f'{i}\tbackground = {{\n{i}\t\tusing = frame_small\n{i}\t}}\n'
                        f'{i}\tflowcontainer = {{\n{i}\t\tdirection = vertical\n{i}\t\tmargin = {{ 30 20 }}\n{i}\t\tspacing = 20\n'
                        f'{i}\t\ttextbox = {{\n{i}\t\t\tminimumsize = {{ 300 -1 }}\n{i}\t\t\tmaximumsize = {{ 300 800 }}\n'
                        f'{i}\t\t\tmultiline = yes\n{i}\t\t\tautoresize = yes\n{i}\t\t\talign = hcenter|nobaseline\n'
                        f'{i}\t\t\ttext = "PMR_GALL_ASK"\n{i}\t\t}}\n'
                        f'{i}\t\tflowcontainer = {{\n{i}\t\t\tdirection = horizontal\n{i}\t\t\tusing = default_list_position\n'
                        f'{i}\t\t\tspacing = 20\n'
                        f'{i}\t\t\tbutton = {{\n{i}\t\t\t\tusing = default_button\n{i}\t\t\t\tusing = close_button_sound\n'
                        f'{i}\t\t\t\tsize = {{ 140 40 }}\n{i}\t\t\t\ttext = "CONFIRM_NO"\n{i}\t\t\t\t{close}\n{i}\t\t\t}}\n'
                        f'{i}\t\t\tbutton = {{\n{i}\t\t\t\tusing = default_button_primary_action\n{i}\t\t\t\tusing = confirm_button_sound\n'
                        f'{i}\t\t\t\tsize = {{ 140 40 }}\n{i}\t\t\t\ttext = "CONFIRM_YES"\n'
                        f"{i}\t\t\t\tenabled = \"[GetScriptedGui('pmr_gov_retool_all_sgui').IsValid({GOV_ALL_SCOPE})]\"\n"
                        f"{i}\t\t\t\tonclick = \"[GetScriptedGui('pmr_gov_retool_all_sgui').Execute({GOV_ALL_SCOPE})]\"\n"
                        f'{i}\t\t\t\t{close}\n{i}\t\t\t}}\n{i}\t\t}}\n{i}\t}}\n{i}}}\n\n' + HUD_ANCHOR)


GALL_N = "#v [GetPlayer.MakeScope.Var('{v}').GetValue|0]#!"
# interface review (SPEC.md B3, P1): the confirmation names the action and its cost; the buttons' tooltip, and the reason
GOV_ALL_LOC = [f' PMR_GALL_ASK:0 "#header $PMR_GOV_RETOOL_ALL$#!\\n{GALL_N.format(v="pmr_gall_l")} levels in '
               f'{GALL_N.format(v="pmr_gall_b")} buildings\\n@construction! {GALL_N.format(v="pmr_gall_c")}"',
               ' PMR_GOV_RETOOL_ALL_TT:0 "#header [Concept(\'concept_pmr_retooling\',\'$PMR_GOV_RETOOL_ALL|q$\')]#!'
               '\\n$TOOLTIP_DELIMITER$\\n#instruction Click to queue every level#!"',
               ' PMR_GOV_RETOOL_ALL_NONE:0 "#header [Concept(\'concept_pmr_retooling\',\'$PMR_GOV_RETOOL_ALL|q$\')]#!'
               '\\n$TOOLTIP_DELIMITER$\\n@red_cross! #N Nothing to retool#!"']


# --script-profile (Pat 2026-10-20: checks log on their own, no console steps). 1.14.5's text script profiler collects
# from launch with -script_profiling, but only the console command ScriptProfiling.Dump writes it, to
# logs/script_profiling.txt: totals since launch, a row per top-level effect / trigger / script value block (type,
# file:line, seconds, calls), the file replaced each time. A HUD widget runs that command every PROFILE_DUMP_S real
# seconds through ExecuteConsoleCommand, as vanilla console.gui's buttons do, on a two-state loop like error_deer.gui's.
PROFILE_DUMP_S = 60


def patch_hud_profile(text):
    """ingame_hud.gui: a widget that dumps the script profiler's totals every PROFILE_DUMP_S seconds."""
    if text.count(HUD_ANCHOR) != 1:
        raise SystemExit('ingame_hud.gui: the topbar vbox moved; update patch_hud_profile')
    return text.replace(HUD_ANCHOR, '\t# PMR: the script profiler written out every minute (--script-profile)\n'
                        '\twidget = {\n\t\tsize = { 0 0 }\n\t\talwaystransparent = yes\n'
                        '\t\tstate = {\n\t\t\tname = pmr_prof_wait\n\t\t\ttrigger_on_create = yes\n'
                        f'\t\t\tnext = pmr_prof_dump\n\t\t\tduration = {PROFILE_DUMP_S}\n\t\t\talpha = 0\n\t\t}}\n'
                        '\t\tstate = {\n\t\t\tname = pmr_prof_dump\n\t\t\tnext = pmr_prof_wait\n\t\t\tduration = 1\n'
                        '\t\t\talpha = 1\n\t\t\ton_start = "[ExecuteConsoleCommand(\'ScriptProfiling.Dump\')]"\n\t\t}\n'
                        '\t}\n\n' + HUD_ANCHOR)



# --engine-timing / --timing-only (Pat 2026-11-10 18:43Z: "the most granular performance tracking data possible"). No
# PDB ships with the game (the exe names only Paradox's own build path), but 1.15's engine times its own tick tasks: 263
# named ones (CTickTask_* in the exe's RTTI), among them UpdateBuildingThroughput, RecomputeStandardProductionMethods,
# ValidateProductionMethods, RecalculateModifierNodes and UpdateEmployment, which is where the engine's work on PMR's
# methods shows. Console log_ticktask_performance (a toggle) streams them to logs/profiling.log; dump_ticktask_timings
# <file> writes the frames recorded so far as frame,task,milliseconds,calls,longest_lock and clear_ticktask_timings
# drops them. The HUD switches the log on once a session (a GUI variable guards the toggle) and writes a CSV every
# TIMING_DUMP_S real seconds into a ring of TIMING_FILES names, clearing after each, so the files hold the last
# TIMING_DUMP_S x TIMING_FILES seconds in TIMING_DUMP_S slices. The same widget in a mod of its own times vanilla.
#
# q99's run gave nothing, for three reasons its logs show (2026-11-10):
# - the first CSV was due after 300 s and the HUD lived 254 s, so no file was written: one a minute now;
# - the console takes one command at a time ("You can't add new commands while the console is still running
#   commands", error.log, the moment the HUD was made): the clear sent with the log toggle was refused, and the clear
#   sent with each dump would have been. Every command now has a state of its own, a second apart;
# - "Animation triggered has no valid state properties" beside it: a state with only a duration. Whether such a state
#   still runs its next is unknown, so each state carries alpha like the script profiler's two (patch_hud_profile),
#   which are known to loop.
TIMING_DUMP_S = 60
TIMING_FILES = 20
TIMING_ON = 'pmr_tt_on'


def timing_widget():
    """The HUD widget for --engine-timing and --timing-only."""
    def state(name, nxt, duration, alpha, command=None, first=False):
        return (f'\t\tstate = {{\n\t\t\tname = {name}\n' + ('\t\t\ttrigger_on_create = yes\n' if first else '')
                + f'\t\t\tnext = {nxt}\n\t\t\tduration = {duration}\n\t\t\talpha = {alpha}\n'
                + (f"\t\t\ton_start = \"[ExecuteConsoleCommand('{command}')]\"\n" if command else '') + '\t\t}\n')
    start = ('\t\tstate = {\n\t\t\tname = pmr_tt_start\n'
             f"\t\t\ttrigger_when = \"[Not(GetVariableSystem.Exists('{TIMING_ON}'))]\"\n\t\t\talpha = 1\n"
             f"\t\t\ton_start = \"[GetVariableSystem.Set('{TIMING_ON}', 'yes')]\"\n"
             "\t\t\ton_start = \"[ExecuteConsoleCommand('log_ticktask_performance')]\"\n\t\t}\n")
    # the ring: two seconds after the toggle, drop what loading recorded; then wait, dump, clear, and on to the next file
    states = [state('pmr_tt_first', 'pmr_tt_clear_0', 2, 0, first=True),
              state('pmr_tt_clear_0', 'pmr_tt_wait_1', 1, 1, 'clear_ticktask_timings')]
    for n in range(1, TIMING_FILES + 1):
        states += [state(f'pmr_tt_wait_{n}', f'pmr_tt_dump_{n}', TIMING_DUMP_S, 0),
                   state(f'pmr_tt_dump_{n}', f'pmr_tt_clear_{n}', 1, 1, f'dump_ticktask_timings pmr_tt_{n:02d}.csv'),
                   state(f'pmr_tt_clear_{n}', f'pmr_tt_wait_{n % TIMING_FILES + 1}', 1, 0, 'clear_ticktask_timings')]
    # Two widgets: a widget holds one state at a time, so the once-a-session switch would stop the ring
    blank = '\twidget = {\n\t\tsize = { 0 0 }\n\t\talwaystransparent = yes\n'
    return ('\t# PMR: the engine\'s tick task timings logged and written out (--engine-timing / --timing-only)\n'
            + blank + start + '\t}\n' + blank + ''.join(states) + '\t}\n\n')


def patch_hud_timing(text):
    """ingame_hud.gui: the engine timing widget (timing_widget) before the topbar."""
    if text.count(HUD_ANCHOR) != 1:
        raise SystemExit('ingame_hud.gui: the topbar vbox moved; update patch_hud_timing')
    return text.replace(HUD_ANCHOR, timing_widget() + HUD_ANCHOR)


def write_timing_mod(game, out):
    """--timing-only: a mod holding only vanilla's HUD with the timing widget, to time a vanilla game the same way."""
    if os.path.isdir(out):
        shutil.rmtree(out)
    hud = patch_hud_timing(open(os.path.join(game, 'gui', 'ingame_hud.gui'), encoding='utf-8-sig').read())
    files = {'gui/ingame_hud.gui': hud,
             'descriptor.mod': f'version="1"\nname="PMR Engine Timing"\nsupported_version="{SUPPORTED_VERSION}"\n',
             '.metadata/metadata.json': json.dumps({
                 'name': 'PMR Engine Timing', 'id': 'org.prob32.pmr.engine_timing', 'version': '1',
                 'game_id': 'victoria3', 'supported_game_version': SUPPORTED_VERSION, 'short_description': '',
                 'tags': [], 'relationships': [], 'game_custom_data': {'multiplayer_synchronized': True}}, indent=2) + '\n'}
    for rel, text in files.items():
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    print(f'timing-only mod written to {out}')

# The state Buildings tab's own urban list (Pat 2026-10-19 18:27Z, "push this in as well"). A hidden site keeps its cell:
# 1.14.5's dynamicgridbox places item i at (i % wrap, i / wrap) whether or not it is visible, and the "+" tile after
# the count of every item (StatesPanel.CalcBuildUrbanBuildingsButtonPosition, exe 0x1422dbde0). So a state with a
# site shows a list script keeps instead (pmr_urb on the state, pmr_urb_refresh): its urban buildings in the tab's
# order, then the state itself, which the grid draws as the "+" tile. A state without one keeps vanilla's grid.
SITE_GROUPS = ('bg_pmr_retool', 'bg_pmr_retool_abroad', 'bg_pmr_retool_gov', 'bg_pmr_retool_gov_abroad')
URBAN_HQ_GROUPS = ('bg_company_headquarter', 'bg_company_regional_headquarter')
URB_ON = ("And(GreaterThan_CFixedPoint(State.MakeScope.Var('pmr_urb_on').GetValue, '(CFixedPoint)0'), "
          "Not(IsDataModelEmpty(State.MakeScope.GetList('pmr_urb'))))")
URB_END = "GreaterThan_CFixedPoint(Scope.Var('pmr_urb_on').GetValue, '(CFixedPoint)0')"


def urban_types(game, report):
    """The building types the tab lists as urban (State.AccessUrbanBuildings, exe filter 0x141a8c560): category urban up
    the group chain, no land_usage = urban and no is_subsistence on it, and buildable, expandable or downsizeable unless
    a company or regional headquarters. In the tab's order among equal levels (comparator 0x141a53120): the group's
    name, then the type's, in English (the other languages fall back to it until finalization). As (type, group)."""
    groups, types, loc = {}, [], {}
    for path in sorted(glob.glob(os.path.join(game, 'common', 'building_groups', '*.txt'))):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and n.key and n.key.startswith('bg_'):
                groups[n.key] = {k: (pdx.get(n.value, k).value if pdx.get(n.value, k) else None)
                                 for k in ('parent_group', 'category', 'land_usage', 'is_subsistence')}
    for path in sorted(glob.glob(os.path.join(game, 'common', 'buildings', '*.txt'))):
        for n in pdx.parse(open(path, encoding='utf-8-sig').read()):
            if n.is_block and n.key and n.key.startswith('building_'):
                g = pdx.get(n.value, 'building_group')
                flags = [pdx.get(n.value, k) for k in ('buildable', 'expandable', 'downsizeable')]
                types.append((n.key, g.value if g else None, all(f and f.value == 'no' for f in flags)))
    yml = os.path.join(game, 'localization', 'english', 'buildings_l_english.yml')
    if os.path.exists(yml):
        for line in open(yml, encoding='utf-8-sig'):
            m = re.match(r'\s*([\w.]+):\d*\s*"(.*)"', line)
            if m:
                loc[m.group(1)] = m.group(2)
    else:
        report['urban_order'] = 'no buildings_l_english.yml: types ordered by key among equal levels'

    def chain(g):
        while g:
            yield groups.get(g, {})
            g = groups.get(g, {}).get('parent_group')
    out = []
    for bk, g, fixed in types:
        cat = next((x['category'] for x in chain(g) if x.get('category')), None)
        if cat != 'urban' or g in SITE_GROUPS or any(x.get('land_usage') == 'urban' or x.get('is_subsistence') == 'yes'
                                                     for x in chain(g)):
            continue
        if fixed and g not in URBAN_HQ_GROUPS:
            continue
        out.append((loc.get(g, g).lower(), loc.get(bk, bk).lower(), bk, g))
    if not out:
        raise SystemExit('urban_types: no urban building types found; the building groups moved')
    return [(bk, g) for _g, _n, bk, g in sorted(out)]


def urban_list_script(order):
    """(triggers, values, effects) for the state's own urban list (see URB_ON), from urban_types' (type, group) pairs."""
    n = len(order)
    # A headquarters is matched by its group: each company's HQ is a type of its own that the game makes from
    # building_company_headquarter (building_company_krupp and the like, seen in Pat's save 2026-10-20 19:51Z), so no
    # script file names it.
    match = [f'is_building_group = {g}' if g in URBAN_HQ_GROUPS else f'is_building_type = {bk}' for bk, g in order]
    trig = ('# PMR: the state Buildings tab\'s own urban list (generate.py, SITE_GROUPS). Building scope: a retool site.\n'
            'pmr_urb_site = { OR = { ' + ' '.join(f'is_building_group = {g}' for g in SITE_GROUPS) + ' } }\n\n'
            '# Building scope: a type the tab lists as urban.\n'
            'pmr_urb_type = {\n\tOR = {\n' + ''.join(f'\t\t{m}\n' for m in match) + '\t}\n}\n')
    value = ('# Building scope: its place in the tab, highest first: its level, then its group\'s name and its own.\n'
             'pmr_urb_key = {\n\tvalue = 0\n\tadd = this.level\n\tmultiply = 100\n'
             + ''.join(f'\t{"if" if i == 0 else "else_if"} = {{ limit = {{ {m} }} add = {n - i} }}\n'
                       for i, m in enumerate(match)) + '}\n')
    eff = ('# State scope: pmr_urb, the urban buildings in the tab\'s order and then the state (the "+" tile), while the state\n'
           '# has a retool site (pmr_urb_on); none without one, and the tab shows vanilla\'s grid.\n'
           'pmr_urb_refresh = {\n\tif = { limit = { has_variable_list = pmr_urb } clear_variable_list = pmr_urb }\n'
           '\tif = {\n\t\tlimit = { any_scope_building = { pmr_urb_site = yes } }\n'
           '\t\tset_variable = { name = pmr_urb_on value = 1 }\n\t\tsave_temporary_scope_as = pmr_urb_st\n'
           '\t\tordered_scope_building = {\n\t\t\tlimit = { pmr_urb_type = yes }\n\t\t\torder_by = pmr_urb_key\n'
           '\t\t\tmax = 99\n\t\t\tcheck_range_bounds = no\n\t\t\tsave_temporary_scope_as = pmr_urb_b\n'
           + ''.join(f'\t\t\tif = {{ limit = {{ is_building_group = {g} scope:pmr_urb_st = {{ owner = {{ is_player = yes }} }} }} debug_log = "PMR;rec=URB_HQ;'
                     'date=[TimeKeeper.GetCurrentDate.GetString];state=[THIS.GetBuilding.GetState.GetNameNoFormatting];'
                     'hq=[THIS.GetBuilding.GetNameNoFormatting]" }\n' for g in URBAN_HQ_GROUPS) +
           '\t\t\tscope:pmr_urb_st = { add_to_variable_list = { name = pmr_urb target = scope:pmr_urb_b } }\n\t\t}\n'
           '\t\tadd_to_variable_list = { name = pmr_urb target = this }\n\t}\n'
           '\telse_if = { limit = { has_variable = pmr_urb_on } remove_variable = pmr_urb_on }\n}\n\n'
           '# State scope: refresh it where a site stands or stood (monthly, and after PMR places one).\n'
           + ('pmr_urb_check = {\n\tif = {\n\t\tlimit = { OR = { has_variable = pmr_urb_on any_scope_building = { pmr_urb_site = yes } } }\n'
              '\t\tpmr_urb_refresh = yes\n\t}\n}\n\n' if not LEAN_CHECKS else
              # LEAN_CHECKS: a state with no list asks every building of the state whether it is a site only twice a
              # year. A site's first level and every level started already refresh the list at once (pmr_urb_built), so
              # the monthly walk only ever found a site no build event had announced.
              'pmr_urb_check = {\n\tif = { limit = { has_variable = pmr_urb_on } pmr_urb_refresh = yes }\n'
              '\telse_if = {\n\t\tlimit = { NOT = { has_variable = pmr_urb_chk } }\n'
              f'\t\tset_variable = {{ name = pmr_urb_chk value = yes days = {URB_WALK_DAYS} }}\n'
              '\t\tif = { limit = { any_scope_building = { pmr_urb_site = yes } } pmr_urb_refresh = yes }\n\t}\n}\n\n')
           +
           '# Building scope (a level built or started): refresh its state\'s list if it is a site or the list is in use.\n'
           'pmr_urb_built = {\n\tif = {\n\t\tlimit = { OR = { pmr_urb_site = yes state ?= { has_variable = pmr_urb_on } } }\n'
           '\t\tstate ?= { pmr_urb_refresh = yes }\n\t}\n}\n')
    return trig, value, eff


def urban_list_gui(text):
    """states_panel_buildings.gui after hide_retool_sites: vanilla's urban grid and "+" tile only while the state keeps
    no list of its own (URB_ON), and the list's grid beside them."""
    grid = '\t\t\t\tdynamicgridbox = {\n\t\t\t\t\tname = "urban_building_list"\n'
    plus_vis = '\t\t\t\t\tvisible = "[GetPlayer.HasForeignInvestmentRights(State.GetOwner)]"\n'
    pos = '\t\t\t\t\tposition = "[StatesPanel.CalcBuildUrbanBuildingsButtonPosition]"\n'
    for what, old in (('the urban grid', grid), ('the "+" tile\'s visibility', plus_vis), ('the "+" tile\'s position', pos)):
        if text.count(old) != 1:
            raise SystemExit(f'states_panel_buildings.gui: expected one {what}, found {text.count(old)}; update urban_list_gui')
    a = text.index(plus_vis)
    w0 = text.rindex('\t\t\t\twidget = {\n', 0, a)
    w1 = block_end(text, w0)   # just past its closing brace
    plus = text[w0:w1]
    if not plus.endswith('}') or pos not in plus:
        raise SystemExit('states_panel_buildings.gui: the "+" tile moved; update urban_list_gui')
    # the tile as a grid item: no position of its own, one level deeper
    item = '\n'.join(('\t\t\t\t' + ln if ln.strip() else ln) for ln in plus.replace(pos, '').split('\n'))
    ours = ('\t\t\t\t# PMR: the state\'s own list while it has a retool site, the "+" tile its last item\n'
            '\t\t\t\tdynamicgridbox = {\n'
            f'\t\t\t\t\tvisible = "[{URB_ON}]"\n'
            '\t\t\t\t\tdatamodel = "[State.MakeScope.GetList(\'pmr_urb\')]"\n'
            '\t\t\t\t\tdatamodel_wrap = 4\n\t\t\t\t\tflipdirection = yes\n\n'
            '\t\t\t\t\titem = {\n\t\t\t\t\t\twidget = {\n\t\t\t\t\t\t\tsize = { 135 210 }\n\n'
            '\t\t\t\t\t\t\twidget = {\n'
            f'\t\t\t\t\t\t\t\tvisible = "[Not({URB_END})]"\n'
            '\t\t\t\t\t\t\t\tsize = { 135 210 }\n'
            '\t\t\t\t\t\t\t\tbuilding_item = {\n\t\t\t\t\t\t\t\t\tdatacontext = "[Scope.GetBuilding]"\n'
            '\t\t\t\t\t\t\t\t}\n\t\t\t\t\t\t\t}\n\n'
            '\t\t\t\t\t\t\twidget = {\n'
            f'\t\t\t\t\t\t\t\tvisible = "[{URB_END}]"\n'
            '\t\t\t\t\t\t\t\tsize = { 135 210 }\n'
            + item + '\n\t\t\t\t\t\t\t}\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t}\n')
    mark = '\0PMR_URB\0'
    text = text[:w1] + mark + text[w1:]
    text = text.replace(plus_vis, f'\t\t\t\t\tvisible = "[And(GetPlayer.HasForeignInvestmentRights(State.GetOwner), Not({URB_ON}))]"\n')
    text = text.replace(grid, grid + f'\t\t\t\t\tvisible = "[Not({URB_ON})]"   # PMR: the state\'s own list instead\n')
    return text.replace(mark, '\n\n' + ours)


def hide_retool_sites(text, site_types):
    """states_panel_buildings.gui: the state's Buildings tab without the retool sites (Pat 2026-10-14 01:54Z).

    A site has to stay a real building: investors pick it and the crew works there. The engine fills the
    tab's urban grid and list (State.AccessUrbanBuildings) with every building whose group's category is
    urban (1.14.5 exe, 0x141a8c560), and a site's group needs bg_manufacturing as its parent for investors
    to score it, so its category stays urban. The tab hides it instead: the item is invisible and the grid
    ignores invisible items, as the lens toolbar's grid does. The list view's grid is shared with the rural
    and development lists, which never hold a site."""
    hidden = SITE_HIDDEN['Building']
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
             '\t\tflowcontainer = {   # PMR: a flow, which closes the row a hidden site leaves (a grid keeps it)\n'
             '\t\t\tdirection = vertical\n\t\t\tblock "datamodel" {}\n\t\t\t# PMR: no retool sites\n'
             '\t\t\tignoreinvisible = yes\n\n\t\t\titem = {\n'
             f'\t\t\t\tbuildings_list_item = {{\n\t\t\t\t\tvisible = "[{hidden}]"\n\t\t\t\t}}\n',
             'the list view')]:
        if text.count(old) != 1:
            raise SystemExit(f'states_panel_buildings.gui: expected one {what} item, found {text.count(old)}; '
                             'update hide_retool_sites')
        text = text.replace(old, new)
    return text


def hide_pm_reset(menu, lens):
    """Pat 2026-10-20 21:40Z: no "Reset Production Methods" to the national standard. Vanilla offers it in the right-click
    menus of a building and a building type (right_click_menu.gui, five items) and as the Reset Production Methods map
    action (lens_toolbar.gui; map interaction reset_production_methods). Each item is made invisible; the lens grid skips
    invisible items. The lens option's key is the interaction's plus _lens_option (exe strings, like
    move_capital_lens_option): q67 matched the bare interaction key and the button stayed (Pat 2026-10-21 21:04Z, State
    Actions). Returns (menu, lens)."""
    item = re.compile(r'(\t*)right_click_menu_item = \{\n')
    out, pos, hidden = [], 0, 0
    for m in item.finditer(menu):
        depth, i = 1, m.end()
        while depth:
            depth += {'{': 1, '}': -1}.get(menu[i], 0)
            i += 1
        block = menu[m.start():i]
        if 'ResetProductionMethodsToStandard' not in block:
            continue
        inner = m.group(1) + '\t'
        body = re.sub('^' + inner + r'visible = "[^"\n]*"\n', '', block[m.end() - m.start():], count=1)
        out += [menu[pos:m.end()], f'{inner}visible = no  # PMR: no reset to the national standard\n', body]
        pos, hidden = i, hidden + 1
    if hidden != 5:
        raise SystemExit(f'right_click_menu.gui: expected 5 Reset Production Methods items, found {hidden}; update hide_pm_reset')
    menu = ''.join(out) + menu[pos:]
    old = ('\t\t\t\t\t\t\t\t\titem = {\n\t\t\t\t\t\t\t\t\t\tflowcontainer = {\n'
           '\t\t\t\t\t\t\t\t\t\t\tlens_option_button = {\n')
    new = ('\t\t\t\t\t\t\t\t\titem = {\n\t\t\t\t\t\t\t\t\t\tflowcontainer = {\n'
           '\t\t\t\t\t\t\t\t\t\t\tvisible = "[Not(EqualTo_string(LensOption.GetKey, \'reset_production_methods_lens_option\'))]"  # PMR\n'
           '\t\t\t\t\t\t\t\t\t\t\tlens_option_button = {\n')
    if lens.count(old) != 1:
        raise SystemExit(f'lens_toolbar.gui: expected one lens option item, found {lens.count(old)}; update hide_pm_reset')
    return menu, lens.replace(old, new)


def hide_sites_elsewhere(menu, browser, site_types):
    """Pat 2026-10-19 04:10Z ("all re tooling buildings should be hidden"): the retool sites off the state's Build Urban
    Buildings menu (build_urban_buildings_menu.gui, Building context) and the Buildings panel's Available Rural / Urban
    Buildings grids (building_browser_panel.gui's building_panel_potential_buildings, BuildingType context), as
    hide_retool_sites does for the state's Buildings tab: the item is invisible and its list skips invisible items.
    Returns (menu, browser)."""
    in_building, in_type = SITE_HIDDEN['Building'], SITE_HIDDEN['BuildingType']
    for old, new, what in [
            ('\t\tdatamodel = "[StatesPanel.AccessState.GetPotentialUrbanBuildings]"\n',
             '\t\tdatamodel = "[StatesPanel.AccessState.GetPotentialUrbanBuildings]"\n'
             '\t\tignoreinvisible = yes  # PMR: no retool sites\n', 'the menu\'s list'),
            ('\t\t\t\tblockoverride "properties" {\n\t\t\t\t\ttooltip = "[Building.GetQueueConstructionTooltip]"\n',
             '\t\t\t\tblockoverride "properties" {\n'
             f'\t\t\t\t\tvisible = "[{in_building}]"  # PMR: no retool sites\n'
             '\t\t\t\t\ttooltip = "[Building.GetQueueConstructionTooltip]"\n', 'the menu\'s item')]:
        if menu.count(old) != 1:
            raise SystemExit(f'build_urban_buildings_menu.gui: expected one {what}, found {menu.count(old)}; '
                             'update hide_sites_elsewhere')
        menu = menu.replace(old, new)
    old = ('\t\t\tdynamicgridbox = {\n\t\t\t\tblock "potential_building_types" {\n\n\t\t\t\t}\n'
           '\t\t\t\tflipdirection = yes\n\t\t\t\tdatamodel_wrap = 5\n\n\t\t\t\titem = {\n\t\t\t\t\tcontainer = {\n')
    if browser.count(old) != 1:
        raise SystemExit(f'building_browser_panel.gui: expected one potential buildings grid, found {browser.count(old)}; '
                         'update hide_sites_elsewhere')
    browser = browser.replace(old, old.replace('\t\t\t\tdatamodel_wrap = 5\n',
                                               '\t\t\t\tdatamodel_wrap = 5\n\t\t\t\tignoreinvisible = yes  # PMR: no retool sites\n')
                              + f'\t\t\t\t\t\tvisible = "[{in_type}]"  # PMR: no retool sites\n')
    return menu, browser


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


def switch_bar(sw, swd, size, ind, tip, place=''):
    """Pat, 2026-10-19 01:07Z: the bar a new pick fills for SWITCH_MONTHS months before it becomes the default new
    levels and retooling follow (pmr_switch_<b>): green with vanilla's moving arrows toward a newer recipe, red toward an
    older one (the cash reserve bar's changed_value_increased_progressbar_horizontal and its _bad twin). sw and swd are
    the months filled and the direction (1, -1, 0). 02:32Z ("it should only pop up when there's momentum for a
    change"): nothing stands in while no switch is under way."""
    i1, i2 = ind + '\t', ind + '\t\t'
    val = f"FixedPointToFloat(Add_CFixedPoint({sw}, '(CFixedPoint)0.25'))"

    def bar(kind, vis, key):
        return (f'{ind}{kind} = {{\n{place}{i1}visible = "[{vis}]"\n{i1}size = {{ {size[0]} {size[1]} }}\n'
                f'{i1}blockoverride "second_progressbar" {{}}\n'
                f'{i1}blockoverride "values" {{\n{i2}min = 0\n{i2}max = {SWITCH_MONTHS}\n{i2}value = "[{val}]"\n{i1}}}\n'
                f'{i1}blockoverride "arrow_texture_density" {{\n{i2}texture_density = {max(2, size[1] // 4)}\n{i1}}}\n'
                f'{i1}tooltip = "{key}"\n{i1}using = tooltip_above\n{ind}}}\n')
    return (bar('changed_value_increased_progressbar_horizontal', f"GreaterThan_CFixedPoint({swd}, '(CFixedPoint)0')", tip)
            + bar('changed_value_increased_progressbar_horizontal_bad', f"LessThan_CFixedPoint({swd}, '(CFixedPoint)0')", tip))


SW_ICON, SW_ICON_GAP = 24, 2   # the switching bar's target icons, at its right end (Pat 02:32Z)


def switch_targets(bk, textures, pair, n):
    """What a switching bar fills toward, as icons (Pat, 2026-10-19 02:32Z: "more clearly an upgrade bar"): a list of
    icon slots, each [(texture, target indices)], one alternative of which shows, the one whose indices hold the
    target (pmr_swto_<b>, pmr_c_swto_<b>: an index into the type's n recipes, as pmr_pbest_<b>). Without the split,
    one slot: recipe i's icon. With it (pair_ui's split) target i is a recipe with an automation option, so two slots:
    the recipe's icon and the option's (pair_options)."""
    if pair and pair.get('split'):
        index = pair['index']
        slots = [[(textures[r - 1], sorted(i for (ri, _a), i in index.items() if ri == r)) for r in pair['recipes']],
                 [(tex, sorted(i for (_ri, aa), i in index.items() if aa == a))
                  for a, (_key, tex) in enumerate(pair_options(bk, pair), 1)]]
    else:
        slots = [[(tex, [i]) for i, tex in enumerate(textures, 1)]]
    for slot in slots:   # every target shows exactly one icon per slot
        if sorted(i for _tex, idxs in slot for i in idxs) != list(range(1, n + 1)):
            raise SystemExit(f'switch_targets: {bk}\'s icons do not cover its {n} recipes once each')
    return slots


def switch_row(slots, sw, swd, swto, x, w, h, size, y, ind, tip, room=1):
    """A switching row (Pat, 2026-10-19 02:32Z): a widget of size, built only while a switch is under way (swd not 0:
    an item of a list that has one only then, as gate_type_copies, so an idle row costs one empty flowcontainer, which
    a flowcontainer with ignoreinvisible skips), holding at y a line SW_ICON tall and w wide from x: the bar
    (switch_bar, h tall), then the target's icons (switch_targets, read from swto) after its right end, with room for
    at least room icon slots, so the line spans what the bars above it span and, given the most slots any card has,
    every card's bar ends at the same x."""
    i1, i2, i3, i4 = ind + '\t', ind + '\t\t', ind + '\t\t\t', ind + '\t\t\t\t'
    i5 = i4 + '\t'
    on = f"Not(EqualTo_CFixedPoint({swd}, '(CFixedPoint)0'))"
    n = max(len(slots), room)
    icons_w = n * SW_ICON + (n - 1) * SW_ICON_GAP
    bar_w = w - icons_w - 6
    out = (f'{ind}flowcontainer = {{  # PMR: built only while a switch is under way\n{i1}visible = "[{on}]"\n'
           f"{i1}datamodel = \"[DataModelRepeatedItem(Select_int32({on}, '(int32)1', '(int32)0'))]\"\n"
           f'{i1}item = {{\n{i2}widget = {{\n{i3}size = {{ {size[0]} {size[1]} }}\n'
           f'{i3}widget = {{\n{i4}position = {{ 0 {y} }}\n{i4}size = {{ {size[0]} {SW_ICON} }}\n'
           + switch_bar(sw, swd, (bar_w, h), i4, tip, place=f'{i5}position = {{ {x} 0 }}\n{i5}parentanchor = vcenter\n'))
    for s, alts in enumerate(slots):
        ix = x + bar_w + 6 + s * (SW_ICON + SW_ICON_GAP)
        for tex, idxs in alts:
            out += (f'{i4}icon = {{\n{i5}visible = "[{any_of([methods_row.eq(swto, i) for i in idxs])}]"\n'
                    f'{i5}position = {{ {ix} 0 }}\n{i5}parentanchor = vcenter\n{i5}size = {{ {SW_ICON} {SW_ICON} }}\n'
                    f'{i5}texture = "{tex}"\n{i5}tooltip = "{tip}"\n{i5}using = tooltip_above\n{i4}}}\n')
    return out + f'{i3}}}\n{i2}}}\n{i1}}}\n{ind}}}\n'


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

    pending = state_var(b, 'pmr_pending_gov')

    def why(tooltip, on):
        """The tooltip, or with the button greyed the reason (SPEC.md P1): all levels queued, or none to retool."""
        return (f"[SelectLocalization({on}, '{tooltip}', SelectLocalization(GreaterThan_CFixedPoint({pending}, '(CFixedPoint)0.5'), "
                f"'PMR_GOV_RETOOL_QUEUED_{b}', 'PMR_GOV_RETOOL_NONE'))]")

    def button(visible, enabled, clicks, tooltip):
        # the action style, as vanilla's subsidise and pause buttons on the same rows (SPEC.md B1)
        return (f'{ind}button_icon_round_action = {{\n{place}'
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

    home = f'And(ObjectsEqual(Building.GetState.GetOwner.Self, GetPlayer.Self), {sgui}.IsValid({scope}))'
    out = button(f'Not({abroad})', f'"[{home}]"',
                 [f'{sgui}.Execute({scope})'], why(f'PMR_GOV_RETOOL_TOOLTIP_{b}', home))
    out += button(f"And({abroad}, Or(Not({site}.IsValid), LessThan_CFixedPoint({room}, '(CFixedPoint)1')))",
                  'no', [], why(f'PMR_GOV_RETOOL_ABROAD_TOOLTIP_{b}', f"GreaterThanOrEqualTo_CFixedPoint({room}, '(CFixedPoint)1')"))
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
    # Q105-FEEDBACK N5: "0% on Bronze Cannons" sat over a bar all of the method the building runs; the plain title
    # stays until a level has moved, and the retooling tooltip shows from the start
    moved = f"GreaterThan_CFixedPoint({state_var(b, 'pmr_p')}, '(CFixedPoint)0.005')"
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
						tooltip = "PMR_BAR_FULL_TOOLTIP"
						using = tooltip_above
					}}
					textbox = {{
						visible = "[And({retooling}, Not({moved}))]"
						size = {{ {ROW_W - 34} 26 }}
						align = left|nobaseline
						elide = right
						text = "PMR_RECIPE_BAR_TITLE"
						tooltip = "PMR_BAR_TOOLTIP_{b}"
						using = tooltip_above
					}}
					textbox = {{
						visible = "[And({retooling}, {moved})]"
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


SW_ROW_H, SW_BAR_H = OPTION_ROW_H, OPTION_BAR_H   # the details panel's switching row, as tall as an option row
SWITCH_ICONS = {}   # building type -> its switching bar's target icons (switch_targets), filled by main()


def pick_row(bk, ind):
    """The details panel's switching row (Pat, 2026-10-19 01:07Z: the bar a new pick fills, under the recipe bar).
    02:32Z: no "Most profitable" line above it (the Policies cards show every recipe's profit), and the row only while
    a switch is under way (pmr_swd_<b> not 0), thicker, with the target's icons at its right end (switch_row): the
    flowcontainer it sits in ignores it otherwise, so it leaves no gap."""
    b = short(bk)
    swd = state_var(b, 'pmr_swd')
    return (f'{ind}# PMR: switching bar of {bk}\n'
            f'{ind}widget = {{\n{ind}\tvisible = "[And({is_type(bk)}, Not(EqualTo_CFixedPoint({swd}, '
            f"'(CFixedPoint)0')))]\"\n{ind}\tsize = {{ @panel_width {SW_ROW_H} }}\n"
            + switch_row(SWITCH_ICONS[bk], state_var(b, 'pmr_sw'), swd, state_var(b, 'pmr_swto'), ROW_X, ROW_W, SW_BAR_H,
                         ('@panel_width', SW_ROW_H), (SW_ROW_H - SW_ICON) // 2, ind + '\t', f'PMR_SW_TT_{b}')
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
    if any, as its executive in pmr_mv_co_<b> (the GUI reaches a company through a character, cc_tree.VIEWED) and
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
        # Pat 2026-10-19 02:32Z: the AI weight's tooltip read the profit term live against a total from the last refresh,
        # and the gap showed as Expanded Works. Every part is now taken here, at one refresh: Expanded Works as what the
        # tail adds (pmr_ai_pre_<b>, private_investment.patch_ai_value), the profit and output term as the value before
        # the tail less base and policy parts (so after the AI_FLOOR), and Policy as the rest (pmr_mv_pt/pworks/pol_<b>)
        tail = bk in ai and any(key == 'works' and not name for key, name in parts.get(bk, []))
        # Pat 2026-10-19 03:52-03:54Z: the tooltip in sections. Policy = the policy cards' parts (pmr_mv_pol_<b>) and
        # the priority (methods_view's share block); Companies = Expanded Works (pmr_mv_pworks_<b>); the vanilla terms
        # as Productivity, Losses and Output (pmr_mv_pprod/ploss/pout_<b>, private_investment.pf_effects). The
        # foreign-or-domestic part leaves the card's weight (pmr_mv_wb_<b>): it lifts every type in the owner's states
        # alike, so it moves investment home, not towards one type ("it doesn't increase the building does it?").
        fd = 'fd' in pk
        snap = ''
        if bk in ai:
            sv = lambda n: f'pmr_mv_{n}_{b}'   # noqa: E731
            snap = (f'\t\t\tset_variable = {{ name = {sv("pt")} value = {"pmr_ai_pre_" if tail else "pmr_ai_value_"}{b} }}\n'
                    f'\t\t\tset_variable = {{ name = {sv("wb")} value = var:{sv("pt")} }}\n'
                    + (f'\t\t\tchange_variable = {{ name = {sv("wb")} subtract = var:{sv("pfd")} }}\n' if fd else '')
                    + f'\t\t\tset_variable = {{ name = {sv("pworks")} value = 0 }}\n'
                    # what Expanded Works multiplies onto the card's weight: (total / before - 1) x the card's part
                    + (f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:{sv("pt")} > 0 }}\n'
                       f'\t\t\t\tset_variable = {{ name = {sv("pworks")} value = var:pmr_mv_aiv_{b} }}\n'
                       f'\t\t\t\tchange_variable = {{ name = {sv("pworks")} subtract = var:{sv("pt")} }}\n'
                       f'\t\t\t\tchange_variable = {{ name = {sv("pworks")} multiply = var:{sv("wb")} }}\n'
                       f'\t\t\t\tchange_variable = {{ name = {sv("pworks")} divide = var:{sv("pt")} }}\n\t\t\t}}\n' if tail else '')
                    + f'\t\t\tchange_variable = {{ name = {sv("wb")} add = var:{sv("pworks")} }}\n'
                    f'\t\t\tchange_variable = {{ name = {sv("pt")} subtract = var:pmr_mv_aib_{b} }}\n'
                    + ''.join(f'\t\t\tchange_variable = {{ name = {sv("pt")} subtract = var:pmr_mv_p{key}_{b} }}\n'
                              for key in pk)
                    + f'\t\t\tset_variable = {{ name = {sv("pol")} value = 0 }}\n'
                    + ''.join(f'\t\t\tchange_variable = {{ name = {sv("pol")} add = var:pmr_mv_p{key}_{b} }}\n'
                              for key in pk if key != 'fd')
                    # the vanilla terms (pmr_ai_pt_<b>, after the AI_FLOOR): the country's productivity and output parts,
                    # losses the rest
                    + ''.join(f'\t\t\tset_variable = {{ name = {sv(n)} value = 0 }}\n'
                              f'\t\t\tif = {{ limit = {{ owner = {{ has_variable = {cv}_{b} }} }} '
                              f'set_variable = {{ name = {sv(n)} value = owner.var:{cv}_{b} }} }}\n'
                              for n, cv in (('pprod', 'pmr_ptp'), ('pout', 'pmr_pto')))
                    + f'\t\t\tset_variable = {{ name = {sv("ploss")} value = var:{sv("pt")} }}\n'
                    f'\t\t\tchange_variable = {{ name = {sv("ploss")} subtract = var:{sv("pprod")} }}\n'
                    f'\t\t\tchange_variable = {{ name = {sv("ploss")} subtract = var:{sv("pout")} }}\n'
                    # Pat 2026-10-20 03:57Z (gold mines, "Losses: +2027"): a type the country has only abroad has no split
                    # of its own (pmr_pto_<b>), and the term read in the state abroad is its owner's whole profit term:
                    # Profit, not Losses
                    f'\t\t\tset_variable = {{ name = {sv("pprf")} value = 0 }}\n'
                    f'\t\t\tif = {{ limit = {{ owner = {{ NOT = {{ has_variable = pmr_pto_{b} }} }} }} '
                    f'set_variable = {{ name = {sv("pprf")} value = var:{sv("ploss")} }} '
                    f'set_variable = {{ name = {sv("ploss")} value = 0 }} }}\n'
                    # Pat 2026-10-19 12:56Z: what Productivity and Output value (their nested tooltips): the pick's
                    # employees per level (pmr_pte_<b>, pf_effects), the profit per level that gives Productivity with
                    # them, and the goods per level at base prices that give Output
                    f'\t\t\tset_variable = {{ name = {sv("pe")} value = 0 }}\n'
                    f'\t\t\tif = {{ limit = {{ owner = {{ has_variable = pmr_pte_{b} }} }} '
                    f'set_variable = {{ name = {sv("pe")} value = owner.var:pmr_pte_{b} }} }}\n'
                    f'\t\t\tset_variable = {{ name = {sv("pp")} value = var:{sv("pprod")} }}\n'
                    f'\t\t\tchange_variable = {{ name = {sv("pp")} multiply = var:{sv("pe")} }}\n'
                    f'\t\t\tchange_variable = {{ name = {sv("pp")} divide = {fmt(VANILLA_PROFIT_W)} }}\n'
                    f'\t\t\tset_variable = {{ name = {sv("pv")} value = var:{sv("pout")} }}\n'
                    f'\t\t\tchange_variable = {{ name = {sv("pv")} divide = {fmt(VANILLA_OUTPUT_W)} }}\n')
        snapped = ([f'pmr_mv_{n}_{b}' for n in ('pt', 'pol', 'pworks', 'pprod', 'pout', 'ploss', 'pprf', 'wb', 'pe', 'pp', 'pv')]
                   if bk in ai else [])
        # the state's levels and picks, and the figures of the country's biggest state of the type, onto the country
        # (scope:pmr_ctry)
        body = ('\t\tsave_temporary_scope_as = pmr_st\n'
                f'\t\tscope:pmr_ctry = {{ change_variable = {{ name = pmr_mv_lv_{b} add = scope:pmr_st.var:pmr_level_{b} }} }}\n'
                + ''.join(f'\t\tif = {{ limit = {{ var:pmr_pbest_{b} = {i} }} '
                          f'scope:pmr_ctry = {{ change_variable = {{ name = pmr_mv_ps_{i}_{b} add = scope:pmr_st.var:pmr_level_{b} }} }} }}\n'
                          for i in range(1, k + 1))
                + f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_level_{b} > scope:pmr_ctry.var:pmr_mv_max_{b} }}\n'
                + (f'\t\t\tset_variable = {{ name = pmr_mv_aiv_{b} value = pmr_ai_value_{b} }}\n'
                   f'\t\t\tset_variable = {{ name = pmr_mv_aib_{b} value = pmr_ai_base_{b} }}\n' if bk in ai else '')
                + ''.join(f'\t\t\tset_variable = {{ name = pmr_mv_p{key}_{b} value = pmr_ai_{key}_{b} }}\n' for key in pk)
                + snap.replace('owner = {', 'scope:pmr_ctry = {').replace('owner.var:', 'scope:pmr_ctry.var:')
                + f'\t\t\tscope:pmr_ctry = {{\n'
                f'\t\t\t\tset_variable = {{ name = pmr_mv_max_{b} value = scope:pmr_st.var:pmr_level_{b} }}\n'
                + ''.join(f'\t\t\t\tset_variable = {{ name = {n} value = scope:pmr_st.var:{n} }}\n'
                          for n in per + ([f'pmr_mv_aiv_{b}', f'pmr_mv_aib_{b}'] if bk in ai else [])
                          + [f'pmr_mv_p{key}_{b}' for key in pk] + snapped)
                # the bars under the card's grid (card_bars): copied where the state has them
                + ''.join(f'\t\t\t\tif = {{ limit = {{ scope:pmr_st = {{ has_variable = {n} }} }} '
                          f'set_variable = {{ name = {n} value = scope:pmr_st.var:{n} }} }}\n' for n in extra.get(bk, []))
                + '\t\t\t}\n\t\t}\n')
        found = f'has_variable = pmr_level_{b} var:pmr_level_{b} > 0 has_variable = pmr_pbest_{b} has_variable = pmr_rm_1_{b}'
        o.append(f'pmr_mv_{b} = {{\n\tsave_temporary_scope_as = pmr_ctry\n'
                 f'\tset_variable = {{ name = pmr_mv_lv_{b} value = 0 }}\n\tset_variable = {{ name = pmr_mv_max_{b} value = 0 }}\n'
                 f'\tset_variable = {{ name = pmr_pbest_{b} value = 0 }}\n'
                 + ''.join(f'\tset_variable = {{ name = pmr_mv_ps_{i}_{b} value = 0 }}\n' for i in range(1, k + 1))
                 + f'\tevery_scope_state = {{\n\t\tlimit = {{ {found} }}\n{body}\t}}\n'
                 # Pat 17:47Z ("i can't see my opium plantations"): a type the country has only abroad, where its
                 # investors own levels (pmr_abroad_<b>), from those states
                 + f'\tif = {{\n\t\tlimit = {{ var:pmr_mv_lv_{b} = 0 }}\n'
                 f'\t\tevery_state = {{\n\t\t\tlimit = {{ has_variable = pmr_abroad_{b} {found} }}\n'
                 + body.replace('\n\t', '\n\t\t').replace('\t\tsave_temporary', '\t\t\tsave_temporary', 1)
                 + '\t\t}\n\t}\n'
                 f'\tif = {{\n\t\tlimit = {{ var:pmr_mv_lv_{b} > 0 }}\n'
                 + ''.join(f'\t\tchange_variable = {{ name = pmr_mv_ps_{i}_{b} divide = var:pmr_mv_lv_{b} }}\n'
                           for i in range(1, k + 1))
                 + '\t}\n' + company_mark(bk, companies.get(bk)) + '}\n\n')
    # Pat 23:22Z: each type's AI weight as its share of the sum over every type on the tab, as the investors pick by
    # weight: the AI value times its priority group's multiplier (pmr_mv_w_<b>), over pmr_mv_wsum, as pmr_mv_sh_<b>
    # weight: the card's weight (pmr_mv_wb_<b>) plus its priority group's share of it (pmr_mv_prio_<b>, Policy's last
    # line: the slider's +%, private_investment.VAR_pct), over pmr_mv_wsum. The game multiplies each group's score by
    # its slider over the highest slider (private_investment's pmr_ipw_<g>); the shares are the same either way.
    groups = {k for k, *_r in private_investment.GROUPS}
    shown = [(short(bk), ai[bk]) for bk in recipe_keys if bk in ai]
    share = ('\tset_variable = { name = pmr_mv_wsum value = 0 }\n'
             + ''.join(f'\tset_variable = {{ name = pmr_mv_w_{b} value = 0 }}\n'
                       f'\tset_variable = {{ name = pmr_mv_prio_{b} value = 0 }}\n'
                       f'\tset_variable = {{ name = pmr_mv_pola_{b} value = 0 }}\n'
                       f'\tif = {{\n\t\tlimit = {{ var:pmr_mv_lv_{b} > 0 has_variable = pmr_mv_wb_{b} }}\n'
                       + (f'\t\tset_variable = {{ name = pmr_mv_prio_{b} value = var:pmr_mv_wb_{b} }}\n'
                          f'\t\tchange_variable = {{ name = pmr_mv_prio_{b} multiply = {private_investment.VAR.format(g)}_pct }}\n'
                          if g in groups else '')
                       + f'\t\tset_variable = {{ name = pmr_mv_w_{b} value = var:pmr_mv_wb_{b} }}\n'
                       f'\t\tchange_variable = {{ name = pmr_mv_w_{b} add = var:pmr_mv_prio_{b} }}\n'
                       f'\t\tset_variable = {{ name = pmr_mv_pola_{b} value = var:pmr_mv_pol_{b} }}\n'
                       f'\t\tchange_variable = {{ name = pmr_mv_pola_{b} add = var:pmr_mv_prio_{b} }}\n'
                       f'\t\tchange_variable = {{ name = pmr_mv_wsum add = var:pmr_mv_w_{b} }}\n\t}}\n'
                       for b, g in shown)
             + ''.join(f'\tset_variable = {{ name = pmr_mv_sh_{b} value = 0 }}\n'
                       f'\tif = {{\n\t\tlimit = {{ var:pmr_mv_wsum > 0 }}\n'
                       f'\t\tset_variable = {{ name = pmr_mv_sh_{b} value = var:pmr_mv_w_{b} }}\n'
                       f'\t\tchange_variable = {{ name = pmr_mv_sh_{b} divide = var:pmr_mv_wsum }}\n\t}}\n'
                       for b, _m in shown)
             + '\tpmr_mv_sort = yes\n'
             + '\tif = {\n\t\tlimit = { is_player = yes }\n'
             '\t\tdebug_log = "PMR;rec=MV_SHARE;date=[TimeKeeper.GetCurrentDate.GetString];'
             "sum=[THIS.Var('pmr_mv_wsum').GetValue|0];"
             + ';'.join(f"{b}=[THIS.Var('pmr_mv_w_{b}').GetValue|0]/[THIS.Var('pmr_mv_sh_{b}').GetValue|3]"
                        f"/[THIS.Var('pmr_mv_rk_{b}').GetValue|0]" for b, _m in shown)
             + '"\n'
             # the tooltip's sections (methods_view_loc), which add up to the weight: base/policy/companies/
             # productivity/losses/output/profit (abroad only)/weight
             '\t\tdebug_log = "PMR;rec=MV_PARTS;date=[TimeKeeper.GetCurrentDate.GetString];'
             + ';'.join(f'{b}=' + '/'.join(f"[THIS.Var('pmr_mv_{n}_{b}').GetValue|0]"
                                           for n in ('aib', 'pola', 'pworks', 'pprod', 'ploss', 'pout', 'pprf', 'w'))
                        for b, _m in shown)
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
AI_W = 116   # the AI weight column: two owner cells of AI_W // 2, each an icon and "100%" (Q104-FEEDBACK F3)
BUY_ICON = 20  # an owner's icon in the AI column's who-buys cells
CO_SIZE = 26   # the company's round icon, a badge on the top-right corner of a card's building icon (Pat 02:32Z)
AI_H = 82      # the AI column's height: label, weight and two rows of who-buys cells
LEFT_H = 78    # the icon column: the icon with the country's levels on it, its productivity under it (Pat 01:07Z)
MINI_H, MINI_GAP = 14, 4   # the automation and trade-off bars under the grid (Pat 01:07Z: "smaller bars"; 14 px, SPEC.md C6)
CSW_H = 18     # the switching bar under the grid, only while a switch is under way (Pat 02:32Z: "thicker")


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
                      f'{i4}tooltip = "PMR_MV_BUY_TT_{key}_{b}"\n{i4}using = tooltip_above\n'
                      f'{i4}icon = {{\n{i4}\tsize = {{ {BUY_ICON} {BUY_ICON} }}\n{i4}\ttexture = "{icon}"\n{i4}}}\n'
                      f'{i4}textbox = {{\n{i4}\tautoresize = yes\n{i4}\tparentanchor = vcenter\n{i4}\talign = left|nobaseline\n'
                      f'{i4}\tusing = fontsize_small\n{i4}\ttext = "PMR_MV_BUY_{key}_{b}"\n{i4}}}\n{i3}}}\n')
        cells += f'{i2}}}\n'
    return (f'{ind}icon = {{\n{i1}position = {{ {x - 8} 0 }}\n{i1}parentanchor = vcenter\n{i1}size = {{ 1 85% }}\n'
            f'{i1}texture = "{methods_row.WHITE}"\n{i1}color = {{ 1 1 1 0.15 }}\n{i1}alwaystransparent = yes\n{ind}}}\n'
            f'{ind}flowcontainer = {{\n{i1}position = {{ {x} 0 }}\n{i1}parentanchor = vcenter\n{i1}direction = vertical\n'
            f'{i1}flowcontainer = {{\n{i2}direction = vertical\n'
            f'{i2}tooltip = "PMR_MV_AI_TT_{b}"\n{i2}using = tooltip_above\n'
            f'{i2}textbox = {{\n{i3}autoresize = yes\n{i3}align = left|nobaseline\n{i3}using = fontsize_large\n'
            f'{i3}text = "PMR_MV_AI_{b}"\n{i2}}}\n{i1}}}\n'
            + cells + f'{ind}}}\n')


def card_left(bk, ind, min_h=0):
    """Pat, 2026-10-19 01:07Z ("add level amount and productivity to the building cards"): the building's icon with
    the country's levels on it, as the company panel shows them, and the type's productivity span under it, as the
    Buildings list's header shows it. Pat 2026-10-19 13:00Z ("doesn't jump outside its card margins"): the span stays
    inside the card, 2 px from its edge, and shrinks its font to fit (elide as the last resort)."""
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    return (f'{ind}widget = {{\n{i1}size = {{ {ICON_W} {max(LEFT_H, min_h)} }}\n{i1}datacontext = "[GetBuildingType(\'{bk}\')]"\n'
            f'{i1}icon = {{\n{i2}position = {{ 3 0 }}\n{i2}size = {{ 54 54 }}\n{i2}texture = "[BuildingType.GetIcon]"\n'
            f'{i2}tooltipwidget = {{\n{i3}FancyTooltip_BuildingType = {{}}\n{i2}}}\n'
            f'{i2}textbox = {{\n{i3}text = "[BuildingType.GetNumLevelsInCountryFormatted(GetPlayer.Self)]"\n'
            f'{i3}autoresize = yes\n{i3}position = {{ 2 -1 }}\n{i3}parentanchor = bottom\n{i3}align = left|nobaseline\n'
            f'{i3}alwaystransparent = yes\n{i2}}}\n{i1}}}\n'
            f'{i1}textbox = {{\n{i2}position = {{ -{CARD_PAD - 2} 57 }}\n{i2}size = {{ {ICON_W + CARD_PAD + ICON_GAP - 4} 20 }}\n'
            f'{i2}align = hcenter|nobaseline\n{i2}using = fontsize_small\n{i2}fontsize_min = 10\n{i2}elide = right\n'
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


def company_badge(bk, ind, outer):
    """The card's company mark (company_mark), as (outline, badge): vanilla's static selection outline round the card
    (at indent outer), and its company's icon, a round button that opens the company (as production_methods.gui's
    company_owned_button), at indent ind in the card's body.
    Pat, 2026-10-19 02:32Z ("the company icon is misaligned"): the badge sits on the building icon's top-right corner,
    clear of the levels at its foot and the productivity under it."""
    b = short(bk)
    on = methods_row.gt(mv_read(f'pmr_mv_cf_{b}'), 0)
    i1, i2, o1 = ind + '\t', ind + '\t\t', outer + '\t'
    outline = (f'{outer}icon = {{\n{o1}visible = "[{on}]"\n{o1}size = {{ 100% 100% }}\n'
               f'{o1}texture = "gfx/interface/selections/selected_square_selection.dds"\n{o1}spriteType = Corneredtiled\n'
               f'{o1}spriteborder = {{ 22 22 }}\n{o1}texture_density = 2\n{o1}alwaystransparent = yes\n{outer}}}\n')
    return outline, (
            f'{ind}button_icon_round = {{\n{i1}visible = "[{on}]"\n'
            f'{i1}position = {{ {CARD_PAD + 3 + 54 - CO_SIZE + 4} {CARD_PAD - 4} }}\n'
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
    # 1.15's artillery foundries have six recipes: the columns narrow (on every card, so they line up) until the AI
    # weight fits beside the box
    fit = CARD_W - AI_W - (CARD_PAD + ICON_W + ICON_GAP + 14) - methods_row.PAIR_LEFT - 10
    methods_row.PAIR_COL = min(methods_row.PAIR_COL, fit // cols)
    box_w = methods_row.pairs_size(cols, 1)[0]
    ai_x = CARD_PAD + ICON_W + ICON_GAP + box_w + 14
    if ai_x + AI_W > CARD_W:
        raise SystemExit(f'methods_view_gui: {cols} recipe columns leave no room for the AI weight')
    targets = {bk: switch_targets(bk, recipe_tex[bk], pair_ui.get(bk), len(keys)) for bk, keys in recipe_keys.items()}
    room = max(len(t) for t in targets.values())   # the switching bars end at the same x on every card
    cards, picks, slots = '', '', ''
    for bk, keys in recipe_keys.items():
        b = short(bk)
        pr = pair_ui.get(bk)
        grid, gh = '', 0
        t4, t5, t6 = '\t' * 4, '\t' * 5, '\t' * 6
        if not (pr and pr.get('split')):   # the recipes are the targets: one row of them
            grid = methods_row.recipes_grid(bk, list(enumerate(recipe_tex[bk], 1)), mv_read,
                                            lambda i, b=b: f'PMR_MV_TIP_{b}_{i}', t6, cols=cols)
            gh = methods_row.pairs_size(cols, 1)[1]
        if pr:
            names = pr.get('keys') or recipe_keys[bk]
            grid += methods_row.pairs_grid(
                bk, [(i, recipe_tex[bk][i - 1]) for i in pr['recipes']], pair_options(bk, pr), mv_read,
                lambda i, a, b=b, names=names: f'PMR_MVP_TIP_{b}_{i}_{a}' if a else f'{names[i - 1]}', t6,
                cols=cols)
            gh += (6 if gh else 0) + methods_row.pairs_size(cols, len(pr['options']))[1]
        # Pat 02:32Z ("the pm bars are all misaligned"): the bars under the grid, and the switching row below, start at
        # the grid box's left edge and are box_w wide, as the box
        mini, mh = card_bars(bk, opt_ui.get(bk, []), auto_ui.get(bk) if pr and pr.get('split') else None, box_w, t6)
        grid = f'{t5}flowcontainer = {{\n{t6}direction = vertical\n{t6}spacing = {MINI_GAP}\n{grid}{mini}{t5}}}\n'
        inner = max(LEFT_H, gh + mh, AI_H if bk in ai else 0)
        h = inner + 2 * CARD_PAD
        outline, badge = company_badge(bk, t4, '\t\t') if bk in companies else ('', '')
        # Pat, 2026-10-19 01:07Z: the switching bar (switch_bar), at the country's biggest state. 02:32Z ("it should only
        # pop up when there's momentum for a change and the card should autosize around it"): a row under the card's
        # body only while a switch is under way, its bar and target icons (switch_row) spanning the grid box, MINI_GAP
        # under the body's content and CARD_PAD above the card's foot. The card's flowcontainer ignores the row
        # otherwise and resizes the card to what it shows (resizeparent, as diplomatic_play_panel.gui's items).
        foot = '\t\t\t# the switching row\n' + switch_row(
            targets[bk], mv_read(f'pmr_c_sw_{b}'), mv_read(f'pmr_c_swd_{b}'), mv_read(f'pmr_c_swto_{b}'),
            CARD_PAD + ICON_W + ICON_GAP, box_w, CSW_H, (CARD_W, SW_ICON + MINI_GAP), MINI_GAP - CARD_PAD, '\t\t\t',
            f'PMR_CSW_TT_{b}', room)
        cards += (f'\ttype pmr_mv_card_{b} = widget {{\n\t\tvisible = "[{methods_row.gt(mv_read(f"pmr_mv_lv_{b}"), 0)}]"\n'
                  f'\t\tsize = {{ {CARD_W} {h} }}\n'
                  '\t\tbackground = {\n\t\t\tusing = entry_bg_simple\n\t\t}\n'
                  '\t\tflowcontainer = {\n\t\t\tresizeparent = yes\n\t\t\tdirection = vertical\n\t\t\tignoreinvisible = yes\n'
                  f'\t\t\t# the body\n\t\t\twidget = {{\n{t4}size = {{ {CARD_W} {h} }}\n'
                  # Pat 13:27Z: the body takes the height of what it shows (the grid hides empty rows), CARD_PAD round it
                  f'{t4}flowcontainer = {{\n{t5}resizeparent = yes\n{t5}direction = vertical\n'
                  f'{t5}widget = {{ size = {{ {CARD_W} {CARD_PAD} }} }}\n'
                  f'{t5}flowcontainer = {{\n{t6}spacing = {ICON_GAP}\n{t6}widget = {{ size = {{ {CARD_PAD - ICON_GAP} 0 }} }}\n'
                  + card_left(bk, t6, AI_H if bk in ai else 0) + grid.replace('\n\t', '\n\t\t').replace(t5, t6, 1)
                  + f'{t5}}}\n{t5}widget = {{ size = {{ {CARD_W} {CARD_PAD} }} }}\n{t4}}}\n'
                  + (ai_column(bk, h, ai_x, t4) if bk in ai else '')
                  + badge + '\t\t\t}\n' + foot + '\t\t}\n' + outline + '\t}\n\n')
        same = f"ObjectsEqual(BuildingType.Self, GetBuildingType('{bk}').Self)"
        picks += (f'\t\tflowcontainer = {{\n\t\t\tdatamodel = "[DataModelRepeatedItem(Select_int32({same}, '
                  "'(int32)1', '(int32)0'))]\"\n"
                  f'\t\t\titem = {{\n\t\t\t\tpmr_mv_card_{b} = {{}}\n\t\t\t}}\n\t\t}}\n')
        here = (f"EqualTo_int32(FixedPointToInt({mv_read(f'pmr_mv_rk_{b}')}), "
                'PdxGuiWidget.AccessParent.GetIndexInDataModel)')
        # Pat 17:46Z ("they disappear when i click investment chance"): the filters and search stay, so place k makes
        # its card only while the Buildings list, as filtered, has the type (its item, with buildings)
        listed = (f"And(ObjectsEqual(BuildingType.Self, GetBuildingType('{bk}').Self), "
                  'Not(IsDataModelEmpty(BuildingBrowserBuildingTypeItem.GetBuildings)))')
        slots += (f'\t\tflowcontainer = {{\n\t\t\tposition = {{ 7 0 }}\n'
                  f'\t\t\tdatamodel = "[DataModelRepeatedItem(Select_int32({here}, '
                  "'(int32)1', '(int32)0'))]\"\n"
                  '\t\t\titem = {\n\t\t\t\tflowcontainer = {\n\t\t\t\t\tdirection = vertical\n'
                  '\t\t\t\t\tdatamodel = "[BuildingBrowserPanel.GetBuildingBrowserBuildingTypeItems]"\n'
                  '\t\t\t\t\titem = {\n\t\t\t\t\t\tflowcontainer = {\n'
                  '\t\t\t\t\t\t\tdatacontext = "[BuildingBrowserBuildingTypeItem.GetBuildingType]"\n'
                  '\t\t\t\t\t\t\tdirection = vertical\n'
                  f"\t\t\t\t\t\t\tdatamodel = \"[DataModelRepeatedItem(Select_int32({listed}, '(int32)1', '(int32)0'))]\"\n"
                  f'\t\t\t\t\t\t\titem = {{\n\t\t\t\t\t\t\t\tflowcontainer = {{\n\t\t\t\t\t\t\t\t\tdirection = vertical\n'
                  f'\t\t\t\t\t\t\t\t\tpmr_mv_card_{b} = {{}}\n'
                  '\t\t\t\t\t\t\t\t\twidget = { size = { 0 5 } }\n'
                  '\t\t\t\t\t\t\t\t}\n\t\t\t\t\t\t\t}\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t}\n'
                  '\t\t\t}\n\t\t}\n')
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
                       f'\ttext = {{\n\t\ttrigger = {{ var:pmr_cav_{i}_{a}_{b} = -1 }}\n\t\tlocalization_key = PMR_PICK_NOTE_VETO\n\t}}\n'
                       '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n')
    for bk, keys in recipe_keys.items():
        b = short(bk)
        if (pair_ui or {}).get(bk, {}).get('split'):
            continue   # no recipe row (methods_view_gui)
        for i in range(1, len(keys) + 1):
            out.append(f'pmr_mvnote_{b}_{i} = {{\n\ttype = country\n\trandom_valid = no\n'
                       f'\ttext = {{\n\t\ttrigger = {{ var:pmr_pbest_{b} = {i} }}\n\t\tlocalization_key = PMR_PICK_NOTE_BEST\n\t}}\n'
                       f'\ttext = {{\n\t\ttrigger = {{ var:pmr_rveto_{i}_{b} = 1 }}\n\t\tlocalization_key = PMR_PICK_NOTE_VETO\n\t}}\n'
                       '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n')
    return ''.join(out)


def producing(loc, bk, b, k):
    """The goods Output's tooltip names after "Producing" (Q105-FEEDBACK A3, vanilla's PRODUCING_GOODS), each with its
    icon, comma separated, the first three and "and N more". Output is the level-weighted average of every state's
    pick, so where the retool targets make different goods, a good shows while a target making it holds a share of
    the levels (pmr_mv_ps_<i>_<b>, methods_view_effects); where they all make the same goods the list is fixed."""
    outs = TARGET_OUTPUTS.get(bk, [])[:k]
    goods = list(dict.fromkeys(g for o in outs for g in o))
    name = lambda g: f'@{g}! ${g}$'   # noqa: E731
    if not goods:
        return ''
    if all(set(o) == set(goods) for o in outs) or len(goods) == 1:
        return ', '.join(name(g) for g in goods[:3]) + (f' and {len(goods) - 3} more' if len(goods) > 3 else '')

    def any_of(conds):
        return conds[0] if len(conds) == 1 else f'Or({conds[0]}, {any_of(conds[1:])})'
    held = [any_of([f"GreaterThan_CFixedPoint({mv_read(f'pmr_mv_ps_{i}_{b}')}, '(CFixedPoint)0')"
                    for i, o in enumerate(outs, 1) if g in o]) for g in goods]
    out = ''
    for j, g in enumerate(goods):
        loc.append(f' PMR_MVG_{b}_{j}:0 "{name(g)}"')
        if j == 0:
            out += f"[SelectLocalization({held[0]}, 'PMR_MVG_{b}_0', 'PMR_EMPTY')]"
            continue
        loc.append(f' PMR_MVG_C_{b}_{j}:0 ", {name(g)}"')
        out += (f"[SelectLocalization({held[j]}, SelectLocalization({any_of(held[:j])}, 'PMR_MVG_C_{b}_{j}', "
                f"'PMR_MVG_{b}_{j}'), 'PMR_EMPTY')]")
    return out


def methods_view_loc(recipe_keys, pair_ui=None, ai=None, parts=None, opt_ui=None, auto_ui=None):
    loc = [' PMR_MV_HEADER:0 "Production Methods"',   # Pat 21:53Z, with no explainer text under it
           ' PMR_BB_TAB_INVEST:0 "Policies"',   # Pat 2026-10-19 01:07Z
           ' PMR_BB_TAB_BUILDINGS:0 "Buildings"',
           ' PMR_PAIR_NOTE_BEST:0 "  #P Most profitable#!"',
           ' PMR_MV_AI_LABEL:0 "Investment Chance"', ' PMR_MV_POLICY:0 "Policy"', ' PMR_MV_BASE:0 "Base"',
           ' PMR_MV_BUY_ZERO:0 "#grey 0%#!"',
           ' PMR_MV_COMPANIES:0 "Companies"', ' PMR_MV_PROD:0 "Productivity"', ' PMR_MV_LOSS:0 "Losses"', ' PMR_MV_PRF:0 "Profit"',
           ' PMR_MV_OUT:0 "Output"', ' PMR_MV_PROFIT_LV:0 "Profit per level a week"',
           ' PMR_MV_EMP_LV:0 "Employees per level"',
           ' PMR_MV_PER_EMPLOYEE:0 "#title Weekly profit per employee of a new level:#!"']
    for bk, keys in recipe_keys.items():
        b = short(bk)
        if (pair_ui or {}).get(bk, {}).get('split'):
            continue   # no recipe row (methods_view_gui)
        for i, key in enumerate(keys, 1):
            name, profit = methods_row.recipe_tip_lines(bk, i, key, mv_read, f"[{MV_COUNTRY}.GetCustom('pmr_mvnote_{b}_{i}')]")
            # the profit line only where the last run priced the recipe (profit_effect's box, Pat 13:09Z)
            loc.append(f' PMR_MV_PL_{b}_{i}:0 "\\n{profit}"')
            loc.append(f' PMR_MV_TIP_{b}_{i}:0 "{name}'
                       f"[SelectLocalization({methods_row.eq(mv_read(f'pmr_rav_{i}_{b}'), 1)}, 'PMR_MV_PL_{b}_{i}', 'PMR_EMPTY')]"
                       f"{TT_DELIM}\\nTarget of #v [{mv_read(f'pmr_mv_ps_{i}_{b}')}|%0]#! of levels"
                       f"\\nRunning on #v [{mv_read(f'pmr_c_sh_{i}_{b}')}|%0]#! of levels\"")
    for bk, group in (ai or {}).items():
        if bk not in recipe_keys:
            continue
        b = short(bk)
        # Pat 2026-10-19 03:52-03:54Z: every figure from the same refresh (methods_view_effects), in sections that add
        # up to the weight: Base, Policy (the policy cards and the priority, nested), Companies, Productivity, Losses,
        # Output. A section that reads 0 is left out, Base and Policy aside.
        aib = mv_read(f'pmr_mv_aib_{b}')
        pola = mv_read(f'pmr_mv_pola_{b}')
        # Pat 21:53Z: less text, on the card and in the tooltip; 23:22Z: the card shows the share of all weights
        loc.append(f' PMR_MV_AI_{b}:0 "#bold [{mv_read(f"pmr_mv_sh_{b}")}|%1]#!"')
        # Q104-FEEDBACK F3: a 0% share in vanilla's grey (#grey, as COASTAL_BUILDING_MARKER_THROUGHPUT_UNAFFECTED)
        loc += [f' PMR_MV_BUY_{key}_{b}:0 "[SelectLocalization(GreaterThan_CFixedPoint({mv_read(f"pmr_mv_b{key}_{b}")}, '
                f'\'(CFixedPoint)0.005\'), \'PMR_MV_BUY_ON_{key}_{b}\', \'PMR_MV_BUY_ZERO\')]"'
                for key, *_r in private_investment.BUYERS]
        loc += [f' PMR_MV_BUY_ON_{key}_{b}:0 "[{mv_read(f"pmr_mv_b{key}_{b}")}|%0]"' for key, *_r in private_investment.BUYERS]
        # interface review (SPEC.md A3, T10): the owner's name, and what the figure is a share of
        loc += [f' PMR_MV_BUY_TT_{key}_{b}:0 "#header ${name}$#!\\n#v [{mv_read(f"pmr_mv_b{key}_{b}")}|%0]#! of new private levels"'
                for key, _icon, name in private_investment.BUYERS]

        def nonzero(val):
            return f"Or(GreaterThan_CFixedPoint({val}, '(CFixedPoint)0.5'), LessThan_CFixedPoint({val}, '(CFixedPoint)-0.5'))"

        def line(key, label, val):
            loc.append(f' {key}:0 "\\n[{val}|=+0] from {label}"')
            return f"[SelectLocalization({nonzero(val)}, '{key}', 'PMR_EMPTY')]"
        # Pat 2026-10-19 00:01Z: Policy opens a nested tooltip with each policy's part, the ones not 0, then the
        # priority group's (Pat 03:52Z: "everything I change to augment the ai weightings should show up in policies")
        pol = [f'#header $PMR_MV_POLICY$#!\\n[{pola}|=+0]{TT_DELIM}']
        pol += [line(f'PMR_MV_POL_{key}_{b}', f'${name}$', mv_read(f'pmr_mv_p{key}_{b}'))
                for key, name in (parts or {}).get(bk, []) if name and key != 'fd']
        pol.append(line(f'PMR_MV_POL_PRIO_{b}', f'$PMR_IPW_GROUP_{group}$', mv_read(f'pmr_mv_prio_{b}')))
        loc.append(f' PMR_MV_POL_TT_{b}:0 "' + ''.join(pol) + '"')
        tail = any(key == 'works' and not name for key, name in (parts or {}).get(bk, []))
        # Pat 2026-10-19 12:56Z: Productivity and Output open a nested tooltip with what they value: the profit and
        # employees per level and vanilla's weight; the goods per level at base prices and its weight
        pprod, pout = mv_read(f'pmr_mv_pprod_{b}'), mv_read(f'pmr_mv_pout_{b}')
        # interface review (SPEC.md A3): the formula's weights are constants, not something to act on, so not shown.
        # Pat 2026-11-11 21:00Z: Productivity says what it is and Output names the goods (Q105-FEEDBACK A2, A3). Not
        # the game's concept_productivity, which is yearly and before wages: the figure is the weekly profit after
        # wages per employee of a new level (vanilla_score), said as the grey sub-heading over the two figures (the
        # quotient itself reads as nothing: £214 over 5,000 employees is £0.04)
        loc.append(f' PMR_MV_PROD_TT_{b}:0 "#header $PMR_MV_PROD$#!\\n[{pprod}|=+0]{TT_DELIM}\\n$PMR_MV_PER_EMPLOYEE$\\n'
                   f'$PMR_MV_PROFIT_LV$ @money!#v [{mv_read(f"pmr_mv_pp_{b}")}|D]#!\\n'
                   f'$PMR_MV_EMP_LV$ #v [{mv_read(f"pmr_mv_pe_{b}")}|D]#!"')
        made = producing(loc, bk, b, len(recipe_keys[bk]))
        loc.append(f' PMR_MV_OUT_TT_{b}:0 "#header $PMR_MV_OUT$#!\\n[{pout}|=+0]{TT_DELIM}\\n'
                   + (f'#title Producing {made}:#!\\n' if made else '') +
                   f'@money!#v [{mv_read(f"pmr_mv_pv_{b}")}|D]#! per level a week at base prices"')
        nest = {'PROD': f'PMR_MV_PROD_TT_{b}', 'OUT': f'PMR_MV_OUT_TT_{b}'}
        rest = ([line(f'PMR_MV_CO_{b}', '$PMR_MV_COMPANIES$', mv_read(f'pmr_mv_pworks_{b}'))] if tail else []) + [
            line(f'PMR_MV_{x.upper()}_{b}',
                 (f'#tooltippable;tooltip:[{MV_COUNTRY}.GetTooltipTag],{nest[lab]} $PMR_MV_{lab}$#!' if lab in nest
                  else f'$PMR_MV_{lab}$'), mv_read(f'pmr_mv_{x}_{b}'))
            for x, lab in (('pprod', 'PROD'), ('pprf', 'PRF'), ('ploss', 'LOSS'), ('pout', 'OUT'))]
        loc.append(f' PMR_MV_AI_TT_{b}:0 "#header $PMR_MV_AI_LABEL$#!\\n#v [{mv_read(f"pmr_mv_sh_{b}")}|%1]#!  '
                   f'(#v [{mv_read(f"pmr_mv_w_{b}")}|0]#! of #v [{mv_read("pmr_mv_wsum")}|0]#!){TT_DELIM}\\n'
                   f'#v [{aib}|0]#! base\\n'
                   f'[{pola}|=+0] from #tooltippable;tooltip:[{MV_COUNTRY}.GetTooltipTag],PMR_MV_POL_TT_{b} $PMR_MV_POLICY$#!'
                   + ''.join(rest) + '"')
    for bk, pr in (pair_ui or {}).items():
        b = short(bk)
        for a, opt in enumerate(pr['options'], 1):
            on = [m for m in opt if m.blend or m.employment] or opt
            loc.append(f' PMR_MVA_{b}_{a}:0 "' + ' + '.join(f'${m.key}$' for m in on) + '"')
        names = pr.get('keys') or recipe_keys[bk]
        for i, a in sorted(pr['econ']):
            # with the split each cell is a retool target: how much of the country picks it, and runs it
            more = (f"{TT_DELIM}\\nTarget of #v [{mv_read(f'pmr_mv_ps_{pr['index'][(i, a)]}_{b}')}|%0]#! of levels"
                    f"\\nRunning on #v [{mv_read(f'pmr_c_sh_{pr['index'][(i, a)]}_{b}')}|%0]#! of levels"
                    if pr.get('split') else '')
            loc.append(f' PMR_MVP_PL_{b}_{i}_{a}:0 "\\n@money!#v [{mv_read(f"pmr_cp_{i}_{a}_{b}")}|D]#! per level a week'
                       f"[{MV_COUNTRY}.GetCustom('pmr_mvcn_{b}_{i}_{a}')]\"")
            loc.append(f' PMR_MVP_TIP_{b}_{i}_{a}:0 "#header ${names[i - 1]}$ + $PMR_MVA_{b}_{a}$#!'
                       f"[SelectLocalization(Not({methods_row.eq(mv_read(f'pmr_cav_{i}_{a}_{b}'), 0)}), "
                       f"'PMR_MVP_PL_{b}_{i}_{a}', 'PMR_EMPTY')]{more}\"")
    # the bars under the grid (card_bars): the group's name, then each option that holds a share
    def shares(tip, head, rows):
        body = []
        for n, (key, e, f) in enumerate(rows):
            loc.append(f' {tip}_{n}:0 "\\n${key}$ #v [{e}|{f}#!"')
            body.append(f"[SelectLocalization({methods_row.gt(e, 0)}, '{tip}_{n}', 'PMR_EMPTY')]")
        loc.append(f' {tip}:0 "#header ${head}$#!{TT_DELIM}' + ''.join(body) + '"')
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
    """State scope: pmr_sw_now_<b> and pmr_sw_to_<b>, the default and the pick the switching bar fills toward
    (switch_effect); country scope pmr_csw_now_<b> and pmr_csw_to_<b>, the same at the country's biggest state
    (pmr_c_now_<b>, pmr_c_swto_<b>). The pick's name for the pick row (pmr_pick_<b>) went with the row (Pat 02:32Z)."""
    out = []
    for bk, keys in pick_ui.items():
        b = short(bk)
        for name, typ, var in (('sw_now', 'state', f'pmr_best_now_{b}'), ('sw_to', 'state', f'pmr_swto_{b}'),
                               ('csw_now', 'country', f'pmr_c_now_{b}'), ('csw_to', 'country', f'pmr_c_swto_{b}')):
            out.append(f'pmr_{name}_{b} = {{\n\ttype = {typ}\n\trandom_valid = no\n'
                       + ''.join(f'\ttext = {{\n\t\ttrigger = {{ var:{var} = {i} }}\n\t\tlocalization_key = {key}\n\t}}\n'
                                 for i, key in enumerate(keys, 1))
                       + '\ttext = {\n\t\tlocalization_key = PMR_EMPTY\n\t}\n}\n')
    return ''.join(out)


def pick_loc(pick_ui):
    """The switching bars' tooltips, and the notes the Policies cards' tooltips put after a recipe's profit. Pat,
    2026-10-19 02:32Z: no "Most profitable" line (PMR_PICK_ROW_<b>) and no idle bar (PMR_CSW_IDLE_<b>) any more."""
    loc = [' PMR_PICK_NOTE_BEST:0 "  #P Most profitable#!"', ' PMR_PICK_NOTE_VETO:0 "  @warning! #N Input at price cap#!"']
    for bk, keys in pick_ui.items():
        b = short(bk)

        def var(name, f='0'):
            return f"[Building.GetState.MakeScope.Var('{name}').GetValue|{f}]"
        # the switching bar (switch_bar): the pick it fills toward, the gain over the default, months (Pat 12:59Z;
        # interface review SPEC.md A2)
        cvar = lambda name, f='0': f"[GetPlayer.MakeScope.Var('{name}').GetValue|{f}]"   # noqa: E731
        loc.append(f' PMR_SW_TT_{b}:0 "#header New Default: [Building.GetState.GetCustom(\'pmr_sw_to_{b}\')]#!{TT_DELIM}'
                   f'\\n{var(f"pmr_swg_{b}", "=+%0")} profit over [Building.GetState.GetCustom(\'pmr_sw_now_{b}\')]'
                   f'\\n#v {var(f"pmr_sw_{b}", "0")}#! of #v {SWITCH_MONTHS}#! months"')
        loc.append(f' PMR_CSW_TT_{b}:0 "#header New Default: [GetPlayer.GetCustom(\'pmr_csw_to_{b}\')]#!{TT_DELIM}'
                   f'\\n{cvar(f"pmr_c_swg_{b}", "=+%0")} profit over [GetPlayer.GetCustom(\'pmr_csw_now_{b}\')]'
                   f'\\n#v {cvar(f"pmr_c_sw_{b}", "0")}#! of #v {SWITCH_MONTHS}#! months"')
    return loc


def automation_loc(auto_ui):
    """The automation bar's tooltips, from vanilla's own names, so every language has them. Interface review
    (SPEC.md A2): a #header and divider, rows at 0 left out."""
    loc = []
    for bk, (group, levels) in auto_ui.items():
        b = short(bk)
        rows = ''.join(zrow(loc, f'PMR_AUTO_R_{b}_{a}', f"${key}$ #v [Building.GetState.MakeScope.Var('pmr_ash_{a}_{b}').GetValue|%0]#!",
                            methods_row.gt(f"Building.GetState.MakeScope.Var('pmr_ash_{a}_{b}').GetValue", 0.005))
                       for a, (key, _, _) in enumerate(levels, 1))
        loc.append(f' PMR_AUTO_TOOLTIP_{b}:0 "#header ${group}$#!{TT_DELIM}{rows}"')
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
              f'{icons}{ind}\t}}\n{extra}{ind}}}')
    hide = (text[:at] + f'{ind}\t# PMR: no grid on PMR building types\n'
            f'{ind}\tvisible = "[Not({any_type(list(buildings) + list(also))})]"\n')
    if not labour_icon:
        return hide + text[at:]
    return hide + text[at:end] + labour + text[end:]


def patch_building_panel(recipe_tex, text, opt_ui=None, also=(), auto_ui=None, pick_ui=None, modifiers_gui=None,
                         cut_goods=(set(), set())):
    """Vanilla building_details_panel.gui with two changes, asserted so a game update that moves
    either anchor fails generation instead of shipping a panel that silently lost them."""
    buildings = list(recipe_tex)
    # 0. The "less" modifiers out of the icon row and the Modifiers tab, and goods at 0 out of the Process lists
    # (method-count rework, Pat's q99 screenshots).
    text = patch_zero_rows(hide_less_icons(text, 'building_details_panel.gui'))
    if modifiers_gui is not None:
        text = patch_modifier_list(text, modifiers_gui, cut_goods)
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


# The "less" modifiers (frames.py) are timed modifiers on the building, and the game lists every timed modifier a
# building has: an icon each in condensed_building_information's row (the details panel and every row of the Buildings
# lists), in the building tooltip and in the map list, and a "Retooling / Indefinite" row each on the Modifiers tab.
# Pat's q99 screenshots (2026-11-10 20:41Z): six to eight icons on every blended building, pushing the state's name off
# its row, and six identical rows on the textile mill's Modifiers tab. They are the frame's arithmetic, not something
# to read (the Modifier Entries below keep their numbers), so each list leaves them out by name: EqualTo_string
# against a literal, as hide_pm_reset's lens option test. The name stays English in every language for that (main,
# LESS_PREFIXES).
LESS_SHOWN = f"Not(EqualTo_string(TimedModifier.GetName, '{frames.LESS_NAME}'))"
LESS_PREFIXES = ('pmr_less_', 'pmr_probe_')   # static modifiers named frames.LESS_NAME: no translation
LESS_ICON_FILES = ('custom_tooltip.gui', 'map_list_panel.gui')   # beside building_details_panel.gui
LESS_STRIP = re.compile(r'datamodel = "\[Building\.GetTimedModifiers\]"\n(?:[ \t]*(?:spacing = \d+)?\n)*'
                        r'[ \t]*item = \{\n([ \t]*)icon = \{\n')


def hide_less_icons(text, name, count=1):
    """A GUI file's icon rows of a building's timed modifiers (count of them, asserted so a game update that moves one
    fails generation): no icon for a "less" modifier. Each row is an hbox, which leaves a hidden child out."""
    if len(LESS_STRIP.findall(text)) != count or text.count('datamodel = "[Building.GetTimedModifiers]"') != count:
        raise SystemExit(f'{name}: expected {count} icon row(s) of Building.GetTimedModifiers; update hide_less_icons')
    return LESS_STRIP.sub(lambda m: m.group(0) + f'{m.group(1)}\t# PMR: no icon for a "less" modifier (frames.py)\n'
                          f'{m.group(1)}\tvisible = "[{LESS_SHOWN}]"\n', text)


def entry_unused(cut_goods):
    """ModifierEntry context inside a building: the entry is a union frame's goods_input/output_<good>_add for a good
    a "less" modifier took to nothing (q102, Pat's 15:47Z screenshot: "Rubber input +275" on a textile mill using no
    rubber). Matched by its name against the modifier's own localisation, so in every language; a staffed building
    only, as the Process rows (ZERO_ROWS)."""
    gin, gout = cut_goods
    terms = ([f"And(EqualTo_string(ModifierEntry.GetName, Localize('goods_input_{g}_add')), "
              f"Not(GreaterThan_CFixedPoint(Building.GetConsumption(GetGoods('{g}')), '(CFixedPoint)0')))" for g in sorted(gin)]
             + [f"And(EqualTo_string(ModifierEntry.GetName, Localize('goods_output_{g}_add')), "
                f"Not(GreaterThan_CFixedPoint(Building.GetProduction(GetGoods('{g}')), '(CFixedPoint)0')))" for g in sorted(gout)])
    return f'And({STAFFED}, {any_of(terms)})' if terms else ''


def patch_modifier_list(text, modifiers_gui, cut_goods=(set(), set())):
    """building_details_panel.gui: the Modifiers tab without a row per "less" modifier. The tab is vanilla's
    modifier_list (modifiers_panel.gui), which the country, character, interest group and formation panels share, so
    the building panel gets a copy of its own, pmr_modifier_list, with those rows hidden, and vanilla's stays as it
    is. When every timed modifier is one of them the header stands alone: the list is not empty, so vanilla's "none"
    line stays hidden, and nothing can count the rows left. Its Modifier Entries (modifier_list_content) get a copy
    too, pmr_modifier_list_content, without the rows of goods a cut took to nothing (entry_unused)."""
    head = '\ttype modifier_list = flowcontainer {\n'
    if modifiers_gui.count(head) != 1:
        raise SystemExit('modifiers_panel.gui: type modifier_list moved; update patch_modifier_list')
    start = modifiers_gui.index(head)
    body = modifiers_gui[start:block_end(modifiers_gui, start)]
    for at in set(re.findall(r'@\w+', body)):   # the copy reads its sizes from the building panel's own constants
        want, have = (re.search(rf'^{at} = (\S+)', t, re.M) for t in (modifiers_gui, text))
        if not want or not have or want.group(1) != have.group(1):
            raise SystemExit(f'building_details_panel.gui: {at} differs from modifiers_panel.gui; update patch_modifier_list')
    rows = ('datamodel = "[ModifiersPanel.GetTimedModifiers]"\n', 'ignoreinvisible = yes   # PMR\n')
    item = ('item = {\n\t\t\t\t\tcontainer = {\n',
            f'\t# PMR: no row for a "less" modifier (frames.py)\n\t\t\t\t\t\tvisible = "[{LESS_SHOWN}]"\n')
    if body.count(rows[0]) != 1 or body.count(item[0]) != 1 or body.index(item[0]) < body.index(rows[0]):
        raise SystemExit('modifiers_panel.gui: the timed modifier rows changed; update patch_modifier_list')
    body = body.replace(rows[0], rows[0] + '\t\t\t\t' + rows[1]).replace(item[0], item[0] + '\t\t\t\t\t' + item[1])
    body = body.replace(head, '\t# PMR: vanilla\'s modifier_list (modifiers_panel.gui) without the "less" modifiers\' rows\n'
                        '\ttype pmr_modifier_list = flowcontainer {\n')
    unused = entry_unused(cut_goods)
    if unused:
        chead = '\ttype modifier_list_content = flowcontainer {\n'
        cuse = '\t\tmodifier_list_content = {\n\t\t\tdatacontext = "[ModifiersPanel.GetModifier]"\n'
        if modifiers_gui.count(chead) != 1 or body.count(cuse) != 1:
            raise SystemExit('modifiers_panel.gui: type modifier_list_content moved; update patch_modifier_list')
        cstart = modifiers_gui.index(chead)
        cbody = modifiers_gui[cstart:block_end(modifiers_gui, cstart)]
        for at in set(re.findall(r'@\w+', cbody)):   # its sizes too come from the building panel's constants
            want, have = (re.search(rf'^{at} = (\S+)', t, re.M) for t in (modifiers_gui, text))
            if not want or not have or want.group(1) != have.group(1):
                raise SystemExit(f'building_details_panel.gui: {at} differs from modifiers_panel.gui; update patch_modifier_list')
        erows = 'datamodel = "[Modifier.GetEntries]"\n'
        eitem = 'item = {\n\t\t\t\twidget = {\n'
        if cbody.count(erows) != 1 or cbody.count(eitem) != 1 or cbody.index(eitem) < cbody.index(erows):
            raise SystemExit('modifiers_panel.gui: the modifier entry rows changed; update patch_modifier_list')
        cbody = (cbody.replace(erows, erows + '\t\t\tignoreinvisible = yes   # PMR\n')
                 .replace(eitem, eitem + '\t\t\t\t\t# PMR: no row for a good a "less" modifier took to nothing (frames.py)\n'
                          f'\t\t\t\t\tvisible = "[Not({unused})]"\n')
                 .replace(chead, '\t# PMR: vanilla\'s modifier_list_content (modifiers_panel.gui) without unused goods\' rows\n'
                          '\ttype pmr_modifier_list_content = flowcontainer {\n'))
        body = cbody + '\n\n' + body.replace(cuse, cuse.replace('modifier_list_content = {', 'pmr_modifier_list_content = {'))
    types = 'types building_panels\n{\n'
    use = '\t\t\t\tmodifier_list = {\n\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'modifiers\')]"\n'
    if text.count(types) != 1 or text.count(use) != 1:
        raise SystemExit('building_details_panel.gui: the Modifiers tab moved; update patch_modifier_list')
    return (text.replace(types, types + body + '\n\n')
            .replace(use, use.replace('modifier_list = {', 'pmr_modifier_list = {')))


# A union frame names every good any mix of its recipes uses, and a "less" modifier at 1.00 takes one to nothing: the
# Process lists then showed it at 0 (q99: rubber on the textile mills, coal, electricity, engines and oil on a logging
# camp mid-retool). A row is left out while its amount is 0 and the building has staff; a building with none shows
# every row at 0, as vanilla does.
STAFFED = "GreaterThan_CFixedPoint(Building.GetEmploymentPercentage, '(CFixedPoint)0')"
ZERO_ROWS = (('Building.AccessConsumedGoods', 'Building.GetConsumption(Goods.Self)'),
             ('Building.AccessProducedGoods', 'Building.GetProduction(Goods.Self)'))


def patch_zero_rows(text):
    """building_details_panel.gui: the Process view's inputs and outputs (the panel's own lists and
    building_process_breakdown's) without a row for a good at 0 in a staffed building."""
    for model, amount in ZERO_ROWS:
        rows = re.compile(r'([ \t]*)datamodel = "\[' + re.escape(model) + r'\]"\n\n[ \t]*item = \{\n([ \t]*)widget = \{\n')
        if len(rows.findall(text)) != 2 or text.count(f'datamodel = "[{model}]"') != 2:
            raise SystemExit(f'building_details_panel.gui: expected two lists of {model}; update patch_zero_rows')
        text = rows.sub(lambda m, amount=amount: (
            m.group(0).replace('\n\n', f'\n{m.group(1)}ignoreinvisible = yes   # PMR\n\n', 1)
            + f'{m.group(2)}\t# PMR: no row for a good a "less" modifier took to nothing (frames.py)\n'
            f"{m.group(2)}\tvisible = \"[Or(GreaterThan_CFixedPoint({amount}, '(CFixedPoint)0'), Not({STAFFED}))]\"\n"), text)
    return text


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
    # list in that order instead (MV_AI, pmr_methods_slot), each place showing its card only while the game's filtered
    # list has the type (Pat 17:46Z: the filters and search stay)
    ai_on = f"GetVariableSystem.Exists('{MV_AI}')"
    ai_off = f"GetVariableSystem.Clear('{MV_AI}')"
    if sorts.count('size = { 135 30 }') != 4 or sorts.count('onclick = "[BuildingBrowserPanel.Sort(') != 4:
        raise SystemExit('building_browser_panel.gui: expected four sort buttons; update patch_browser_tabs')
    # Pat 2026-10-19 01:07Z: no Building Type sort on Policies; 02:32Z: "remove the productivity column header"
    inv_sorts = sorts
    for sort in ('database_order', 'profitability'):
        d1 = inv_sorts.find(f"BuildingBrowserPanel.Sort('{sort}')")
        if d1 < 0:
            raise SystemExit(f'building_browser_panel.gui: no {sort} sort button; update patch_browser_tabs')
        d0 = inv_sorts.rindex('\n', 0, inv_sorts.rindex('sort_button = {', 0, d1))
        inv_sorts = inv_sorts[:d0] + inv_sorts[block_end(inv_sorts, d0):]
    inv_sorts = re.sub(r'(\n(\t+)onclick = "\[BuildingBrowserPanel\.Sort\([^\n]*\n)',
                       lambda m: f'{m.group(1)}{m.group(2)}onclick = "[{ai_off}]"  # PMR\n', inv_sorts)
    # the three left (Name, Size, the AI weight) fill the row the four vanilla buttons did
    sort_w = 4 * 135 // (inv_sorts.count('sort_button = {') + 1)
    inv_sorts = inv_sorts.replace('size = { 135 30 }', f'size = {{ {sort_w} 30 }}  # PMR')
    b4 = '\t\t\t\t'
    inv_sorts = (inv_sorts[:inv_sorts.rindex('}')].rstrip('\t')
                 + f'\n{b4}# PMR: sorted by AI weight\n{b4}sort_button = {{\n{b4}\tsize = {{ {sort_w} 30 }}\n'
                 f'{b4}\ttext = "PMR_MV_AI_LABEL"\n{b4}\talign = nobaseline\n'
                 f'{b4}\tonclick = "[GetVariableSystem.Set(\'{MV_AI}\', \'yes\')]"\n{b4}\tonclick = "[{refresh}]"\n'
                 f'{b4}\tblockoverride "selected_visibility" {{\n{b4}\t\tvisible = "[{ai_on}]"\n{b4}\t}}\n{b4}}}\n'
                 + '\t\t\t' + inv_sorts[inv_sorts.rindex('}'):])
    inv_filters = filters   # Pat 17:46Z: with every sort, the AI weight's too (methods_view_gui's slots follow them)
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
         '\t\t\t\tposition = { 622 204 }\n\t\t\t}\n')   # under Retool Government Levels (patch_browser_retool_all)
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
         f'\t\t\t\tdatamodel = "[DataModelRepeatedItem(FixedPointToInt({mv_read("pmr_mv_n")}))]"\n'
         '\t\t\t\titem = {\n\t\t\t\t\tpmr_methods_slot = {}\n\t\t\t\t}\n\t\t\t}\n'
         + '@@PMR_LIST@@' + lst)
    at = text.index('@@PMR_LIST@@')
    end = block_end(text, at + len('@@PMR_LIST@@'))
    text = text[:at] + text[at + len('@@PMR_LIST@@'):end] + '\n\t\t\t}  # PMR' + text[end:]
    # opening the panel counts its country's buildings abroad (pmr_c_view_sgui)
    show = ('\t\t\t\tname = _show\n\t\t\t\tstart_sound = {\n\t\t\t\t\tsoundeffect = "event:/SFX/UI/SideBar/buildings"\n'
            '\t\t\t\t}\n\n\t\t\t\ton_start = "[BuildingBrowserPanel.Sort(\'database_order\')]"\n')
    once(show, show + '\t\t\t\ton_start = "[GetScriptedGui(\'pmr_c_view_sgui\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).End)]"'
         '  # PMR\n')
    # closing the panel puts it back on Buildings, with the policy window shut
    hide = ('\t\t\t\tname = _hide\n\t\t\t\tstart_sound = {\n\t\t\t\t\tsoundeffect = "event:/SFX/UI/SideBar/buildings_stop"\n'
            '\t\t\t\t}\n\n\t\t\t\ton_start = "[BuildingBrowserPanel.Sort(\'database_order\')]"\n')
    once(hide, hide + f'\t\t\t\ton_start = "[GetVariableSystem.Clear(\'{MV_TAB}\')]"  # PMR\n'
         f'\t\t\t\ton_start = "[GetVariableSystem.Clear(\'{GOV_ALL_ASK}\')]"  # PMR\n'
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
    """production_methods.gui, the Buildings tab's building type row: the government upgrade button, at the row's
    40 px, queueing every government retool level the player's buildings of the type still need, in every state
    (pmr_gov_retool_c_<b>_sgui, country scope). Interface review 2026-11-11 (SPEC.md B1, B4, P1): vanilla's action
    style, directly left of expand (the plus) after the toggles, and the reason in its tooltip while greyed."""
    anchor = '\t\t\t\tspacing = 5\n\t\t\t\t\n\t\t\t\t### nationalize\n\t\t\t\tbuilding_type_nationalize_button = {\n'
    if text.count(anchor) != 1:
        raise SystemExit(f'production_methods.gui: expected one type-row nationalize button, found {text.count(anchor)}; '
                         'update patch_type_row_buttons')
    expand = '\t\t\t\t### expand\n\t\t\t\tbutton_icon_round_map_interaction = {\n\t\t\t\t\tsize = { 40 40 }\n'
    at = text.find(expand, text.index(anchor))
    span = text.find('### PRODUCTIVITY SPAN ###', text.index(anchor))
    if at < 0 or not at < span:
        raise SystemExit('production_methods.gui: the type row\'s expand button no longer follows its toggles; '
                         'update patch_type_row_buttons')
    ind = '\t\t\t\t'
    scope = 'GuiScope.SetRoot(GetPlayer.MakeScope).End'

    def is_bt(bk):
        return f"ObjectsEqual(BuildingType.Self, GetBuildingType('{bk}').Self)"
    any_bt = is_bt(buildings[-1])
    for bk in reversed(buildings[:-1]):
        any_bt = f'Or({is_bt(bk)}, {any_bt})'

    def button(bk):
        on = f"GetScriptedGui('pmr_gov_retool_c_{short(bk)}_sgui').IsValid({scope})"
        return (f'{ind}\tbutton_icon_round_action = {{\n{ind}\t\tvisible = "[{is_bt(bk)}]"\n{ind}\t\tsize = {{ 40 40 }}\n'
                f'{ind}\t\tenabled = "[{on}]"\n'
                f"{ind}\t\tonclick = \"[GetScriptedGui('pmr_gov_retool_c_{short(bk)}_sgui').Execute({scope})]\"\n"
                f"{ind}\t\ttooltip = \"[SelectLocalization({on}, 'PMR_GOV_RETOOL_C_TOOLTIP_{short(bk)}', 'PMR_GOV_RETOOL_NONE')]\"\n"
                f'{ind}\t\tusing = tooltip_se\n'
                f'{ind}\t\tusing = confirm_button_sound\n'
                f'{ind}\t\tblockoverride "icon" {{\n{ind}\t\t\ttexture = "{GOV_RETOOL_ICON}"\n{ind}\t\t}}\n'
                f'{ind}\t\tblockoverride "icon_size" {{\n{ind}\t\t\tsize = {{ 80% 80% }}\n{ind}\t\t}}\n{ind}\t}}\n')
    block = (f'{ind}# PMR: government upgrade button, every state at once\n{ind}widget = {{\n'
             f'{ind}\tvisible = "[{any_bt}]"\n{ind}\tsize = {{ 40 40 }}\n' + ''.join(button(bk) for bk in buildings)
             + f'{ind}}}\n\n')
    text = text[:at] + block + text[at:]
    return text.replace(anchor, f'{ind}spacing = 5\n{ind}ignoreinvisible = yes  # PMR\n{ind}\n'
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


TT_DELIM = '\\n$TOOLTIP_DELIMITER$'   # vanilla's divider under a tooltip's header (SPEC.md A1)
RETOOL_LINK = "[Concept('concept_pmr_retooling','$PMR_GOV_RETOOL_ALL|q$')]"   # the retool buttons' header (SPEC.md P2)


def add_fp(a, b):
    """a + b in a GUI expression, from Subtract_CFixedPoint alone (in game since q60; Add_CFixedPoint has no vanilla use)."""
    return f"Subtract_CFixedPoint({a}, Subtract_CFixedPoint('(CFixedPoint)0', {b}))"


def zrow(loc, key, text, cond):
    """A tooltip row in a key of its own, shown only while cond holds (PMR_EMPTY otherwise), so rows at 0 drop out
    (SPEC.md A2). The picked key reads the same data context, as vanilla's COASTAL_BUILDING_MARKER_* sub-keys do."""
    loc.append(f' {key}:0 "\\n{text}"')
    return f"[SelectLocalization({cond}, '{key}', 'PMR_EMPTY')]"


def panel_loc(recipe_keys):
    """The recipe bar's, owners' and government retool buttons' tooltips. Interface review 2026-11-11
    (gui-review/SPEC.md A2, A6, P1-P3): a #header, vanilla's divider, #v figures, rows at 0 left out, the Retooling
    concept linked from "To retool" and the buttons' header, and a greyed button says why."""
    new = "[Building.GetCustom('pmr_new_recipe')]"
    loc = [
        f' PMR_RECIPE_BAR_TITLE:0 "#bold {new}#!"',
        ' PMR_OWNERS_PM_HEADER:0 "Production Method"',
        f' PMR_BAR_FULL_TOOLTIP:0 "#v 100%#! on {new}"',
        ' PMR_TO_RETOOL:0 "To retool"',
        ' PMR_BAR_HEADER:0 "#header [Concept(\'concept_production_method\',\'$concept_production_methods|q$\')]#!"',
        f' PMR_GOV_RETOOL_NONE:0 "#header {RETOOL_LINK}#!{TT_DELIM}\\n@red_cross! #N No government levels to retool#!"',
    ]
    gtz = methods_row.gt
    for bk, keys in recipe_keys.items():
        b = short(bk)

        def ex(name):
            return f"Building.GetState.MakeScope.Var('{name}_{b}').GetValue"

        def var(name, f):
            return f"[{ex(name)}|{f}]"
        # Pat, 2026-10-13: no colour names, and short. With the split, by plain recipe (SPLIT_BARS).
        sh, lvg, lvp = ('pmr_rs', 'pmr_rlvg', 'pmr_rlvp') if b in SPLIT_BARS else ('pmr_sh', 'pmr_lvg', 'pmr_lvp')
        tiers = ''.join(zrow(loc, f'PMR_BAR_R_{b}_{i}', f'${key}$ #v {var(f"{sh}_{i}", "%0")}#!', gtz(ex(f'{sh}_{i}'), 0.005))
                        for i, key in enumerate(keys, 1))
        owners = ''.join(
            zrow(loc, f'PMR_BAR_{w}_{b}', f'{label} #v {var(pend, "0")}#! of #v [{add_fp(ex(pend), ex(room))}|0]#! queued',
                 gtz(add_fp(ex(pend), ex(room)), 0.5))
            for w, label, pend, room in (('G', 'Government', 'pmr_pending_gov', 'pmr_room_gov'),
                                         ('P', 'Private', 'pmr_pending_priv', 'pmr_room_priv')))
        loc.append(f' PMR_BAR_RT_{b}:0 "\\n#title [Concept(\'concept_pmr_retooling\',\'$PMR_TO_RETOOL|q$\')]:#! '
                   f'#v {var("pmr_need", "0")}#! levels{owners}"')
        cost = RETOOL_COST.get(b)
        price = f"  @construction! #v [Multiply_CFixedPoint({ex('pmr_room_gov')}, '(CFixedPoint){fmt(cost)}')|0]#!" if cost else ''
        head = f'#header {RETOOL_LINK}#!{TT_DELIM}\\n#v {var("pmr_room_gov", "0")}#! levels to {new}{price}'
        loc += [
            f' PMR_RECIPE_BAR_TITLE_RETOOLING_{b}:0 "#v {var("pmr_p", "%0")}#! on {new}"',
            f' PMR_BAR_TOOLTIP_{b}:0 "$PMR_BAR_HEADER${TT_DELIM}{tiers}'
            f"[SelectLocalization({gtz(ex('pmr_need'), 0.5)}, 'PMR_BAR_RT_{b}', 'PMR_EMPTY')]\"",
            f' PMR_GOV_RETOOL_TOOLTIP_{b}:0 "{head}\\n#instruction Click to queue#!"',
            f' PMR_GOV_RETOOL_ABROAD_TOOLTIP_{b}:0 "{head}\\n#instruction Click to queue up to {GOV_ABROAD_CLICKS}#!"',
            f' PMR_GOV_RETOOL_QUEUED_{b}:0 "#header {RETOOL_LINK}#!{TT_DELIM}'
            # Pat 2026-11-11 21:05Z (card, Q105-FEEDBACK N8): every level queued is good news, so a green check, not red
            f'\\n@green_checkmark! #v {var("pmr_pending_gov", "0")}#! of #v {var("pmr_pending_gov", "0")}#! levels queued"',
            f' PMR_OWNERS_GOV_TOOLTIP_{b}:0 "#header Government Levels#!{TT_DELIM}'
            + ''.join(zrow(loc, f'PMR_OWN_G_{b}_{i}', f'${key}$ #v {var(f"{lvg}_{i}", "0")}#!', gtz(ex(f'{lvg}_{i}'), 0.5))
                      for i, key in enumerate(keys, 1)) + '"',
            f' PMR_OWNERS_PRIV_TOOLTIP_{b}:0 "#header Private Levels#!{TT_DELIM}'
            + ''.join(zrow(loc, f'PMR_OWN_P_{b}_{i}', f'${key}$ #v {var(f"{lvp}_{i}", "0")}#!', gtz(ex(f'{lvp}_{i}'), 0.5))
                      for i, key in enumerate(keys, 1)) + '"',
        ]

        def cex(name):
            return f"GetPlayer.MakeScope.Var('{name}_{b}').GetValue"

        def cvar(name, f):
            return f"[{cex(name)}|{f}]"
        ctiers = ''.join(zrow(loc, f'PMR_CBAR_R_{b}_{i}', f'${key}$ #v {cvar(c_name(f"{sh}_{i}"), "%0")}#!',
                              gtz(cex(c_name(f'{sh}_{i}')), 0.005)) for i, key in enumerate(keys, 1))
        loc.append(f' PMR_CBAR_RT_{b}:0 "\\n#title [Concept(\'concept_pmr_retooling\',\'$PMR_TO_RETOOL|q$\')]:#! '
                   f'#v {cvar("pmr_c_need", "0")}#! of #v {cvar("pmr_c_level", "0")}#! levels"')
        cprice = (f"  @construction! #v [Multiply_CFixedPoint({cex('pmr_c_room_gov')}, '(CFixedPoint){fmt(cost)}')|0]#!"
                  if cost else '')
        loc += [
            f' PMR_CBAR_TOOLTIP_{b}:0 "$PMR_BAR_HEADER${TT_DELIM}{ctiers}'
            f"[SelectLocalization({gtz(cex('pmr_c_need'), 0.5)}, 'PMR_CBAR_RT_{b}', 'PMR_EMPTY')]\"",
            f' PMR_GOV_RETOOL_C_TOOLTIP_{b}:0 "#header {RETOOL_LINK}#!{TT_DELIM}'
            f'\\n#v {cvar("pmr_c_room_gov", "0")}#! levels{cprice}\\n#instruction Click to queue#!"',
        ]
    return loc


def option_loc(opt_ui):
    """Tooltips of the second group bars. Pat, 2026-10-13: short. Interface review 2026-11-11 (SPEC.md A2): a #header
    and divider, #v shares, a status as icon and colour; a row at 0 stays only while it carries a status."""
    loc = [' PMR_EMPTY:0 ""', ' PMR_OPT_LOCKED:0 "  @lock! #N Locked#!"', ' PMR_OPT_SHORT:0 "  @warning! #N Shortage#!"',
           ' PMR_OPT_BARRED:0 "  @red_cross! #N Banned by law#!"']
    gtz, eqz = methods_row.gt, methods_row.eq
    for bk, groups in opt_ui.items():
        b = short(bk)

        def ex(name):
            return f"Building.GetState.MakeScope.Var('{name}_{b}').GetValue"

        def var(name, f='0'):
            return f"[{ex(name)}|{f}]"
        for gi, mode, none, tex, os_ in groups:
            rows = zrow(loc, f'PMR_OPT_N_{b}_{gi}', f'${none}$ #v {var(f"pmr_xn_{gi}")}%#!', gtz(ex(f'pmr_xn_{gi}'), 0.5))
            for o in os_:
                note = f"[Building.GetState.GetCustom('pmr_xlk_{b}_{o.j}')]"
                market = mode == 'market' and o.group not in DEMAND_GROUPS
                worth = f'  @money!#v {var(f"pmr_xw_{o.j}", "D")}#! / week' if market else ''   # vanilla's money format (Q104-FEEDBACK L2)
                shown = f"Or({gtz(ex(f'pmr_x_{o.j}'), 0.5)}, {eqz(ex(f'pmr_xav_{o.j}'), 0)})"
                if market:
                    shown = f"Or({shown}, {eqz(ex(f'pmr_xsh_{o.j}'), 1)})"
                rows += zrow(loc, f'PMR_OPT_X_{b}_{o.j}', f'${o.key}$ #v {var(f"pmr_x_{o.j}")}%#!{worth}{note}', shown)
            foot = ''
            if mode != 'market':
                lo, hi = TREAT_BANDS
                foot = (f'\\n\\nAcceptance under {lo} #v {var(f"pmr_xbv_{gi}")}%#!, {lo} to {hi - 1} '
                        f'#v {var(f"pmr_xbh_{gi}")}%#!')
            loc.append(f' PMR_OPT_TOOLTIP_{b}_{gi}:0 "#header ${os_[0].group}$#!{TT_DELIM}{rows}{foot}"')
    return loc


OBS_TOP = 8           # an observer game's OBS lines: the largest economies by GDP
OBS_LOGGED = 1        # ... and its SWITCH_START, DEFAULT and FLOOR lines: the largest
VIEWER_TRIGGER = """# Country scope: its Buildings tab totals count its buildings abroad (pmr_c_sum_<b>, pmr_c_sum_all): a player's,
# or one whose Buildings panel has been opened (pmr_c_view_sgui).
pmr_c_viewer = {
\tOR = {
\t\tis_player = yes
\t\thas_variable = pmr_c_view
\t}
}
"""
LOGGED_TRIGGER = f"""# Country scope: its buildings' SWITCH_START, DEFAULT and FLOOR lines are logged: the player's, or in an
# observer game (pmr_obs, pmr.1) the largest economy's.
pmr_logged = {{
\tOR = {{
\t\tis_player = yes
\t\tAND = {{ has_global_variable = pmr_obs gdp_ranking <= {OBS_LOGGED} }}
\t}}
}}
"""


def obs_report(dispatch):
    """Country scope, monthly in an observer game (test builds): one OBS line for each of the OBS_TOP largest
    economies. types = building types it has in a state (pmr_mix_<b>), loss = those whose books show a loss (pmr_bpl_<b>
    < 0) or can't be read as it is subsidised or nearly empty (pmr_bsx_<b>),
    up / down = switching bars filling toward a newer / older default, lowered = defaults a loss lowered (pmr_dn_<b>)."""
    keys = ('types', 'loss', 'up', 'down', 'lowered')
    per = ''.join(f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_mix_{b} }}\n'
                  '\t\t\tscope:pmr_obs_c = { change_variable = { name = pmr_obs_types add = 1 } }\n'
                  f'\t\t\tif = {{ limit = {{ OR = {{ has_variable = pmr_bsx_{b} AND = {{ has_variable = pmr_bpl_{b} var:pmr_bpl_{b} < 0 }} }} }} '
                  'scope:pmr_obs_c = { change_variable = { name = pmr_obs_loss add = 1 } } }\n'
                  f'\t\t\tif = {{ limit = {{ var:pmr_swd_{b} ?= 1 }} scope:pmr_obs_c = {{ change_variable = {{ name = pmr_obs_up add = 1 }} }} }}\n'
                  f'\t\t\telse_if = {{ limit = {{ var:pmr_swd_{b} ?= -1 }} scope:pmr_obs_c = {{ change_variable = {{ name = pmr_obs_down add = 1 }} }} }}\n'
                  f'\t\t\tif = {{ limit = {{ has_variable = pmr_dn_{b} }} scope:pmr_obs_c = {{ change_variable = {{ name = pmr_obs_lowered add = 1 }} }} }}\n'
                  '\t\t}\n' for b in (short(bk) for bk in dispatch))
    fields = ';'.join(f"{k}=[THIS.Var('pmr_obs_{k}').GetValue|0]" for k in keys)
    return (''.join(f'# {ln.strip()}\n' for ln in obs_report.__doc__.splitlines()) +
            'pmr_obs_report = {\n\tsave_scope_as = pmr_obs_c\n'
            + ''.join(f'\tset_variable = {{ name = pmr_obs_{k} value = 0 }}\n' for k in keys)
            + '\tevery_scope_state = {\n' + per + '\t}\n'
            '\tdebug_log = "PMR;rec=OBS;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
            'gdp=[THIS.GetCountry.GetGDP|0];sol=[THIS.GetCountry.GetAverageSoLByPopulation|1];' + fields + '"\n'
            + ''.join(f'\tremove_variable = pmr_obs_{k}\n' for k in keys) + '\tpmr_obs_methods = yes\n}\n\n')


# Issue #12 (2026-10-29, Pat's "Run it" card at 22:35Z): players say the AI deletes its army, two of them with PMR as
# their only mod. An observer game logs one ARMY line a year for every country that can hold an army: its barracks and
# conscription centre levels, battalions in armies, vanilla's barracks target (wanted_army_size_script_value, what the
# AI builds and cuts toward), military spending, fixed income, gold reserves, and whether it is at war or borrowing.
OBS_ARMY = """# Country scope, from pmr_obs_monthly_country (test builds): the ARMY line, once a year (pmr_obs_army_chk).
pmr_obs_army = {
	if = {
		limit = { NOT = { has_variable = pmr_obs_army_chk } NOT = { is_country_type = decentralized } }
		set_variable = { name = pmr_obs_army_chk value = yes days = 350 }
		set_variable = { name = pmr_obs_bar value = pmr_obs_barracks }
		set_variable = { name = pmr_obs_con value = pmr_obs_conscription }
		set_variable = { name = pmr_obs_bat value = pmr_obs_battalions }
		set_variable = { name = pmr_obs_want value = wanted_army_size_script_value }
		set_variable = { name = pmr_obs_mil value = pmr_obs_military_expenses }
		set_variable = { name = pmr_obs_inc value = pmr_obs_fixed_income }
		set_variable = { name = pmr_obs_gold value = pmr_obs_gold_reserves }
		set_variable = { name = pmr_obs_war value = 0 }
		if = { limit = { is_at_war = yes } set_variable = { name = pmr_obs_war value = 1 } }
		set_variable = { name = pmr_obs_loan value = 0 }
		if = { limit = { taking_loans = yes } set_variable = { name = pmr_obs_loan value = 1 } }
		debug_log = "PMR;rec=ARMY;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];gdp=[THIS.GetCountry.GetGDP|0];barracks=[THIS.Var('pmr_obs_bar').GetValue|0];conscription=[THIS.Var('pmr_obs_con').GetValue|0];battalions=[THIS.Var('pmr_obs_bat').GetValue|0];wanted=[THIS.Var('pmr_obs_want').GetValue|1];military=[THIS.Var('pmr_obs_mil').GetValue|0];income=[THIS.Var('pmr_obs_inc').GetValue|0];gold=[THIS.Var('pmr_obs_gold').GetValue|0];war=[THIS.Var('pmr_obs_war').GetValue|0];loans=[THIS.Var('pmr_obs_loan').GetValue|0]"
		remove_variable = pmr_obs_bar
		remove_variable = pmr_obs_con
		remove_variable = pmr_obs_bat
		remove_variable = pmr_obs_want
		remove_variable = pmr_obs_mil
		remove_variable = pmr_obs_inc
		remove_variable = pmr_obs_gold
		remove_variable = pmr_obs_war
		remove_variable = pmr_obs_loan
		pmr_obs_budget = yes
	}
}

"""
# Pat 2026-10-30 03:05Z: the yearly checks during an observer run go to a database and 20 years of it are analysed for
# why the AI doesn't build barracks. The BUDGET line beside ARMY carries what vanilla's money-spending AI weighs
# (00_ai.txt MONEY_SPENDING_*): fixed and total income and expenses, gold and debt against their limits, the investment
# pool and its weekly income (the construction target), construction sectors, both queues, tax and military wage
# levels, wasted construction, the economic system law and PMR's investment policy and subsidiaries.
OBS_LAWS = ('law_traditionalism', 'law_interventionism', 'law_agrarianism', 'law_laissez_faire',
            'law_cooperative_ownership', 'law_command_economy', 'law_extraction_economy', 'law_industry_banned')
OBS_POLICIES = ('steer', 'corporations', 'reinvest', 'small', 'bulls', 'titans', 'landed', 'concessions')
OBS_BUDGET_VALUES = (('fexp', 'fixed_expenses', 0), ('tinc', 'total_income', 0), ('texp', 'total_expenses', 0),
                     ('sgold', 'scaled_gold_reserves', 2), ('glim', 'gold_reserves_limit', 0),
                     ('sdebt', 'scaled_debt', 2), ('pool', 'investment_pool', 0),
                     ('pinc', 'investment_pool_income', 0), ('gq', 'num_queued_government_constructions', 0),
                     ('pq', 'num_queued_private_constructions', 0), ('tax', 'tax_level_value', 0),
                     ('mwage', 'military_wage_level_value', 0))


def obs_budget():
    """pmr_obs_budget (effect) and its script values: the BUDGET line, called from pmr_obs_army."""
    sets = ''.join(f'\tset_variable = {{ name = pmr_obs_{k} value = pmr_obs_v_{k} }}\n' for k, _v, _d in OBS_BUDGET_VALUES)
    sets += '\tset_variable = { name = pmr_obs_csec value = pmr_obs_v_csec }\n'
    sets += '\tset_variable = { name = pmr_obs_subs value = pmr_obs_v_subs }\n'
    sets += ('\tset_variable = { name = pmr_obs_waste value = 0 }\n'
             '\tif = { limit = { has_wasted_construction = yes } set_variable = { name = pmr_obs_waste value = 1 } }\n')
    sets += '\tset_variable = { name = pmr_obs_law value = 0 }\n' + ''.join(
        f'\t{"if" if i == 0 else "else_if"} = {{ limit = {{ has_law = law_type:{l} }} '
        f'set_variable = {{ name = pmr_obs_law value = {i + 1} }} }}\n' for i, l in enumerate(OBS_LAWS))
    sets += '\tset_variable = { name = pmr_obs_pol value = 0 }\n' + ''.join(
        f'\t{"if" if i == 0 else "else_if"} = {{ limit = {{ has_modifier = pmr_policy_{k} }} '
        f'set_variable = {{ name = pmr_obs_pol value = {i + 1} }} }}\n' for i, k in enumerate(OBS_POLICIES))
    fields = [(k, d) for k, _v, d in OBS_BUDGET_VALUES] + [('csec', 0), ('subs', 0), ('waste', 0), ('law', 0), ('pol', 0)]
    log = ('\tdebug_log = "PMR;rec=BUDGET;date=[TimeKeeper.GetCurrentDate.GetString];'
           'country=[THIS.GetCountry.GetNameNoFormatting];'
           + ';'.join(f"{k}=[THIS.Var('pmr_obs_{k}').GetValue|{d}]" for k, d in fields) + '"\n')
    effect = ('# Country scope, from pmr_obs_army (test builds): the BUDGET line, once a year.\npmr_obs_budget = {\n' + sets + log
              + ''.join(f'\tremove_variable = pmr_obs_{k}\n' for k, _d in fields) + '}\n\n')
    values = ('# Country scope, for the BUDGET line (pmr_obs_budget, test builds).\n'
              + ''.join(f'pmr_obs_v_{k} = {{ value = {v} }}\n' for k, v, _d in OBS_BUDGET_VALUES)
              + 'pmr_obs_v_csec = {\n\tvalue = { every_scope_building = { limit = { is_building_type = '
                'building_construction_sector } add = this.level } }\n}\n'
              + 'pmr_obs_v_subs = {\n\tvalue = { every_company = { limit = { has_variable = pmr_sub } add = 1 } }\n}\n')
    return effect, values


OBS_ARMY_VALUES = """# Country scope, for the ARMY line (pmr_obs_army, test builds).
pmr_obs_barracks = {
	value = { every_scope_building = { limit = { is_building_type = building_barrack } add = this.level } }
}
pmr_obs_conscription = {
	value = { every_scope_building = { limit = { is_building_type = building_conscription_center } add = this.level } }
}
pmr_obs_battalions = {
	value = { every_military_formation = { limit = { is_army = yes } every_combat_unit = { add = 1 } } }
}
pmr_obs_military_expenses = { value = military_expenses }
pmr_obs_fixed_income = { value = fixed_income }
pmr_obs_gold_reserves = { value = gold_reserves }
"""


OBS_AB_YEARS = range(1839, 1936, 2)   # an observer game's years with PMR's script off (--obs-script-off)
OBS_AB = False   # set by main()
# --obs-parts-off (Pat 2026-10-20 01:33Z card): the q56 profiler can't see on_actions, so an observer game times PMR's
# monthly script part by part, each part off for one year (pmr_off_<part>; 'all' = the test pause) and every part on
# in the years between: the state tick, the state's other checks, the company tick, the investment and Buildings-tab
# sums. Pairs (part, year).
OBS_PARTS = (('tick', 1839), ('checks', 1841), ('companies', 1843), ('invest', 1845), ('all', 1847))
# Review 9: three parts inside the state tick, each expected under a year's noise (about 0.4 s a month in q69), so
# each is off in alternate months for two years from its year instead, switched at the largest economy's pulse: the
# monthly price and wage watch (pmr_moved_<b>, and with it most profit re-checks), the trade-off and treatment step
# (pmr_opts_<b>, a building already set up), and of that only the treatment recount over the state's pops
# (pmr_xtreat_<j>_<b>).
OBS_ALT_PARTS = (('watch', 1849), ('opts', 1851), ('treat', 1853))
OBS_PARTS_ON = False   # set by main()
OBS_PART_HOOKS = {   # file: (text, the same with the part's switch), each found once
    'common/on_actions/pmr_on_actions.txt': [
        ("\t\t\tpmr_state_tick = yes   # this state's turn\n",
         "\t\t\tif = { limit = { NOT = { has_global_variable = pmr_off_tick } } pmr_state_tick = yes }   # this state's turn\n"),
        ('\t\tpmr_auto_best = yes\n\t\tpmr_principle_bonus = yes\n\t\tpmr_probe_state = yes\n'
         '\t\tpmr_urb_check = yes   # the state Buildings tab\'s own list\n',
         '\t\tif = {\n\t\t\tlimit = { NOT = { has_global_variable = pmr_off_checks } }\n\t\t\tpmr_auto_best = yes\n'
         '\t\t\tpmr_principle_bonus = yes\n\t\t\tpmr_probe_state = yes\n\t\t\tpmr_urb_check = yes\n\t\t}\n'),
        ('pmr_on_monthly_pulse_country = {\n\ttrigger = { NOT = { has_global_variable = pmr_ticks_paused } }',
         'pmr_on_monthly_pulse_country = {\n\ttrigger = { NOT = { has_global_variable = pmr_ticks_paused } '
         'NOT = { has_global_variable = pmr_off_invest } }')],
    'common/on_actions/pmr_cc_on_actions.txt': [
        ('pmr_cc_monthly_country = {\n\ttrigger = { NOT = { has_global_variable = pmr_ticks_paused } }',
         'pmr_cc_monthly_country = {\n\ttrigger = { NOT = { has_global_variable = pmr_ticks_paused } '
         'NOT = { has_global_variable = pmr_off_companies } }')],
    'common/on_actions/pmr_pi_on_actions.txt': [
        ('pmr_pi_monthly_country = {\n\ttrigger = { NOT = { has_global_variable = pmr_ticks_paused } }',
         'pmr_pi_monthly_country = {\n\ttrigger = { NOT = { has_global_variable = pmr_ticks_paused } '
         'NOT = { has_global_variable = pmr_off_invest } }')]}


def obs_ab():
    """Country scope, from pmr_obs_monthly_country (test builds). Pat 2026-10-20 00:01Z, after q52 removed the weekly
    method recompute and the months got no faster: PMR's monthly pulses run in the daily event tick, outside the Tick
    Task List, so their cost shows only as a slower month. An observer game turns them off (pmr_ticks_paused, the test
    decision's pause) in OBS_AB_YEARS, so one run times months with and without PMR's script; the methods, buildings
    and their hooks stay. Once a month, at the first country's pulse; a pause it didn't set (pmr_obs_abp) it leaves.
    Opt-in since 2026-10-20 (Pat 01:06Z, the comparison done): other test builds only lift a pause one left in a save."""
    line = 'PMR;rec=TEST;arm=TICKS_{};date=[TimeKeeper.GetCurrentDate.GetString];by=observer'
    flags = ['pmr_ticks_paused'] + [f'pmr_off_{k}' for k, _ in OBS_PARTS if k != 'all']
    lift = ''.join(f'\t\tif = {{ limit = {{ has_global_variable = {g} }} remove_global_variable = {g} }}\n' for g in flags)
    if OBS_PARTS_ON:   # --obs-parts-off: one part off a year
        def year(y):
            return f'game_date >= {y}.1.1 game_date < {y + 1}.1.1'
        out = ('pmr_obs_ab = {\n\tif = {\n\t\tlimit = { NOT = { has_global_variable = pmr_obs_abc } }\n'
               '\t\tset_global_variable = { name = pmr_obs_abc value = yes days = 20 }\n')
        for k, y in OBS_PARTS:
            g = 'pmr_ticks_paused' if k == 'all' else f'pmr_off_{k}'
            out += (f'\t\tif = {{\n\t\t\tlimit = {{ {year(y)} NOT = {{ has_global_variable = {g} }} }}\n'
                    f'\t\t\tset_global_variable = {g}\n\t\t\tset_global_variable = pmr_obs_abp\n'
                    f'\t\t\tdebug_log = "{line.format("PAUSED")};part={k}"\n\t\t}}\n')
        out += ('\t\tif = {\n\t\t\tlimit = { has_global_variable = pmr_obs_abp NOT = { OR = { '
                + ' '.join(f'AND = {{ {year(y)} }}' for _, y in OBS_PARTS) + ' } } }\n'
                + lift.replace('\t\tif', '\t\t\tif') + '\t\t\tremove_global_variable = pmr_obs_abp\n'
                f'\t\t\tdebug_log = "{line.format("RESUMED")}"\n\t\t}}\n\t}}\n')
        # OBS_ALT_PARTS: each interval between two of these lines is a month with the part off (PART_OFF) or on
        alt = 'PMR;rec=TEST;arm=PART_{};date=[TimeKeeper.GetCurrentDate.GetString];part={}'
        out += '\tif = {\n\t\tlimit = { gdp_ranking <= 1 }\n'
        for k, y in OBS_ALT_PARTS:
            g = f'pmr_off_{k}'
            out += (f'\t\tif = {{\n\t\t\tlimit = {{ game_date >= {y}.1.1 game_date < {y + 2}.1.1 }}\n'
                    f'\t\t\tif = {{ limit = {{ has_global_variable = {g} }} remove_global_variable = {g} '
                    f'debug_log = "{alt.format("ON", k)}" }}\n'
                    f'\t\t\telse = {{ set_global_variable = {g} debug_log = "{alt.format("OFF", k)}" }}\n\t\t}}\n'
                    f'\t\telse_if = {{ limit = {{ has_global_variable = {g} }} remove_global_variable = {g} '
                    f'debug_log = "{alt.format("ON", k)}" }}\n')
        return out + '\t}\n}\n\n'
    if not OBS_AB:
        return ('pmr_obs_ab = {\n\tif = {\n\t\tlimit = { has_global_variable = pmr_obs_abp }\n'
                + lift + '\t\tremove_global_variable = pmr_obs_abp\n'
                f'\t\tdebug_log = "{line.format("RESUMED")}"\n\t}}\n}}\n\n')
    years = ' '.join(f'AND = {{ game_date >= {y}.1.1 game_date < {y + 1}.1.1 }}' for y in OBS_AB_YEARS)
    return ('pmr_obs_ab = {\n\tif = {\n\t\tlimit = { NOT = { has_global_variable = pmr_obs_abc } }\n'
            '\t\tset_global_variable = { name = pmr_obs_abc value = yes days = 20 }\n'
            f'\t\tif = {{\n\t\t\tlimit = {{ OR = {{ {years} }} NOT = {{ has_global_variable = pmr_ticks_paused }} }}\n'
            '\t\t\tset_global_variable = pmr_ticks_paused\n\t\t\tset_global_variable = pmr_obs_abp\n'
            f'\t\t\tdebug_log = "{line.format("PAUSED")}"\n\t\t}}\n'
            f'\t\telse_if = {{\n\t\t\tlimit = {{ NOT = {{ OR = {{ {years} }} }} has_global_variable = pmr_obs_abp }}\n'
            '\t\t\tremove_global_variable = pmr_ticks_paused\n\t\t\tremove_global_variable = pmr_obs_abp\n'
            f'\t\t\tdebug_log = "{line.format("RESUMED")}"\n\t\t}}\n\t}}\n}}\n\n')


OBS_PAD_N = 2000                        # --obs-pad: dummy variables per state ...
OBS_PAD_YEARS = (1839, 1843, 1847, 1851)        # ... in these years; none in the others
OBS_MONTHLY_YEARS = (1841, 1845, 1849, 1853)    # every monthly pulse updates every state's buildings (TICK_EVERY off)
OBS_PAD = False   # set by main()
OBS_PAD_HOOK = ('\t\tpmr_obs_ab = yes\n', '\t\tpmr_obs_ab = yes\n\t\tif = { limit = { gdp_ranking <= 1 } pmr_obs_pad_month = yes }\n')
OBS_PAD_ON_ACTIONS = '''
# Root = state, an observer game's monthly pulse (--obs-pad): the dummy variables of OBS_PAD_YEARS (pmr_obs_pad).
pmr_obs_monthly_state = {
	trigger = { has_global_variable = pmr_obs }
	effect = { pmr_obs_pad = yes }
}
'''


def obs_pad():
    """--obs-pad (review 9): is a variable's cost tied to how many its holder has? The q69 save holds 1.46 million PMR
    variables, a median of 1,149 per state, 75% of them 0. An observer game gives every state OBS_PAD_N more (value 0,
    never read but here) at its first monthly pulse of each year in OBS_PAD_YEARS and takes them away at its first in
    the year after, so one run times months with and without them. A dummy created in January sits after the state's
    older variables and before any it creates later. Pat 2026-10-21 12:38Z ("q70/71 in one test"): the same run
    updates every state's buildings at every monthly pulse in OBS_MONTHLY_YEARS (pmr_b1_off: TICK_EVERY's single
    steps), every other one in the rest, so it times TICK_EVERY too. Monthly, at the largest economy's pulse: one PAD
    line with the count of states holding the dummies (padded=) and monthly=1 in OBS_MONTHLY_YEARS."""
    if not OBS_PAD:
        return ''
    on = 'OR = { ' + ' '.join(f'AND = {{ game_date >= {y}.1.1 game_date < {y + 1}.1.1 }}' for y in OBS_PAD_YEARS) + ' }'
    monthly = 'OR = { ' + ' '.join(f'AND = {{ game_date >= {y}.1.1 game_date < {y + 1}.1.1 }}' for y in OBS_MONTHLY_YEARS) + ' }'
    names = [f'pmr_obs_pad_{n}' for n in range(1, OBS_PAD_N + 1)]
    line = ('PMR;rec=TEST;arm=PAD;date=[TimeKeeper.GetCurrentDate.GetString];'
            'monthly=[THIS.Var(\'pmr_obs_padm\').GetValue|0];padded=')
    return (''.join(f'# {ln.strip()}\n' for ln in obs_pad.__doc__.splitlines())
            + '# State scope.\npmr_obs_pad = {\n\tif = {\n'
            f'\t\tlimit = {{ {on} NOT = {{ has_variable = {names[0]} }} }}\n'
            + ''.join(f'\t\tset_variable = {{ name = {v} value = 0 }}\n' for v in names)
            + f'\t}}\n\telse_if = {{\n\t\tlimit = {{ NOT = {{ {on} }} has_variable = {names[0]} }}\n'
            + ''.join(f'\t\tif = {{ limit = {{ has_variable = {v} }} remove_variable = {v} }}\n' for v in names)
            + '\t}\n}\n\n'
            '# Country scope, the largest economy\'s monthly pulse.\npmr_obs_pad_month = {\n'
            f'\tif = {{\n\t\tlimit = {{ {monthly} }}\n'
            '\t\tif = { limit = { NOT = { has_global_variable = pmr_b1_off } } set_global_variable = pmr_b1_off }\n\t}\n'
            '\telse_if = { limit = { has_global_variable = pmr_b1_off } remove_global_variable = pmr_b1_off }\n'
            '\tset_variable = { name = pmr_obs_padm value = 0 }\n'
            '\tif = { limit = { has_global_variable = pmr_b1_off } set_variable = { name = pmr_obs_padm value = 1 } }\n'
            '\tset_variable = { name = pmr_obs_padn value = 0 }\n'
            f'\tevery_state = {{\n\t\tlimit = {{ has_variable = {names[-1]} }}\n'
            '\t\troot = { change_variable = { name = pmr_obs_padn add = 1 } }\n\t}\n'
            f'\tif = {{ limit = {{ var:pmr_obs_padn > 0 }} debug_log = "{line}[THIS.Var(\'pmr_obs_padn\').GetValue|0]" }}\n'
            f'\telse = {{ debug_log = "{line}0" }}\n'
            '\tremove_variable = pmr_obs_padn\n\tremove_variable = pmr_obs_padm\n}\n\n')


# Pat 2026-10-19 21:20Z: the observer run tracks the ranches' wool, the mines' explosives and the plantations' processing
# methods. Each row: a label, its building types, and per option a label and how a state's building reads it: a trade-off
# option's share (pmr_x_<j>_<b>, 0..SHARE_STEPS) or a vanilla method's marker (all its levels while active).
OBS_METHODS = [
    ('ranch', ['building_livestock_ranch'], [('sheep', 'pm_sheep_farms'), ('grazing', 'pm_intensive_grazing_ranch')]),
    ('mines', ['building_coal_mine', 'building_iron_mine', 'building_lead_mine', 'building_sulfur_mine',
               'building_gold_mine'], [('nitro', 'nitroglycerin'), ('dynamite', 'dynamite')]),
    ('coffee', ['building_coffee_plantation'], [('mech', 'coffee_plantation_mechanical_drying')]),
    ('tobacco', ['building_tobacco_plantation'], [('molds', 'molds'), ('electric', 'electric_rollers')]),
    ('sugar', ['building_sugar_plantation'], [('vacuum', 'vacuum_pan_sugar'), ('steam', 'steam_powered_evaporation_sugar'),
                                              ('centrifugal', 'centrifugal_machine_sugar')]),
]


def obs_methods(options, dispatch, split_info):
    """Country scope, after pmr_obs_report: one OBSPM line, each row's levels in the country (ranch=) and each option's
    share of them in percent (ranch_sheep=). A trade-off option counts its share of a building's levels, an automation
    method its blend member's (pmr_rs_<j>), a vanilla method all of them while active; then whether the country knows
    each automation method's technologies (coffee_mech_t=1)."""
    vars_, body, fields, techs = [], [], [], {}
    for row, bks, opts in OBS_METHODS:
        lv = f'pmr_obs_{row}_l'
        vars_.append(lv)
        for bk in bks:
            if bk not in dispatch:
                raise SystemExit(f'OBS_METHODS: {bk} is not a PMR building')
            b = short(bk)
            conv = {o.key: o for *_g, os_, _std in options.get(bk, []) for o in os_}
            member = {m.key: j for j, _, _, m in split_info[bk]['members']} if bk in split_info else {}
            add = []
            for lab, key in opts:
                for _j, _i, _g, m in (split_info[bk]['members'] if bk in split_info else []):
                    if m.key == key and m.unlock_techs:
                        techs[f'pmr_obs_{row}_{lab}_t'] = list(m.unlock_techs)
                x = next((o for k2, o in conv.items() if key in k2), None)
                ov = f'pmr_obs_{row}_{lab}'
                if key in member:      # an automation method: its blend member's share of the levels
                    j = member[key]
                    add.append(f'\t\t\tif = {{ limit = {{ has_variable = pmr_rs_{j}_{b} }} '
                               f'set_variable = {{ name = pmr_t value = var:pmr_level_{b} }} '
                               f'change_variable = {{ name = pmr_t multiply = var:pmr_rs_{j}_{b} }} '
                               f'scope:pmr_obs_c = {{ change_variable = {{ name = {ov} add = scope:pmr_obs_s.var:pmr_t }} }} }}\n')
                elif x is not None:      # a trade-off option: its share of the levels
                    add.append(f'\t\t\tif = {{ limit = {{ has_variable = pmr_x_{x.j}_{b} }} '
                               f'set_variable = {{ name = pmr_t value = var:pmr_level_{b} }} '
                               f'change_variable = {{ name = pmr_t multiply = var:pmr_x_{x.j}_{b} }} '
                               f'change_variable = {{ name = pmr_t divide = {SHARE_STEPS} }} '
                               f'scope:pmr_obs_c = {{ change_variable = {{ name = {ov} add = scope:pmr_obs_s.var:pmr_t }} }} }}\n')
                else:                  # a vanilla method: all the levels while its marker runs
                    add.append(f'\t\t\tif = {{ limit = {{ is_production_method_active = {{ building_type = {bk} production_method = {key} }} }} '
                               f'scope:pmr_obs_c = {{ change_variable = {{ name = {ov} add = scope:pmr_obs_s.var:pmr_level_{b} }} }} }}\n')
            body.append(f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_mix_{b} has_variable = pmr_level_{b} }}\n'
                        f'\t\t\tscope:pmr_obs_c = {{ change_variable = {{ name = {lv} add = scope:pmr_obs_s.var:pmr_level_{b} }} }}\n'
                        + ''.join(add) + '\t\t}\n')
        vars_ += [f'pmr_obs_{row}_{lab}' for lab, _k in opts]
        fields.append(f"{row}=[THIS.Var('{lv}').GetValue|0];"
                      + ';'.join(f"{row}_{lab}=[THIS.Var('pmr_obs_{row}_{lab}').GetValue|0]" for lab, _k in opts))
    # q58: whether the country knows each automation method's technologies (_t=1), so a 0 share reads as locked or unpicked
    fields.append(';'.join(f"{n[8:]}=[THIS.Var('{n}').GetValue|0]" for n in techs))
    vars_ += list(techs)
    pct = ''.join(f'\tif = {{ limit = {{ var:pmr_obs_{row}_l > 0 }}\n'
                  + ''.join(f'\t\tchange_variable = {{ name = pmr_obs_{row}_{lab} multiply = 100 }}\n'
                            f'\t\tchange_variable = {{ name = pmr_obs_{row}_{lab} divide = var:pmr_obs_{row}_l }}\n'
                            for lab, _k in opts) + '\t}\n' for row, _b, opts in OBS_METHODS)
    return (''.join(f'# {ln.strip()}\n' for ln in obs_methods.__doc__.splitlines()) +
            'pmr_obs_methods = {\n\tsave_scope_as = pmr_obs_c\n'
            + ''.join(f'\tset_variable = {{ name = {n} value = 0 }}\n' for n in vars_)
            + '\tevery_scope_state = {\n\t\tsave_scope_as = pmr_obs_s\n' + ''.join(body) + '\t}\n'
            + pct
            + ''.join(f'\tif = {{ limit = {{ ' + ' '.join(f'has_technology_researched = {t}' for t in ts)
                      + f' }} set_variable = {{ name = {n} value = 1 }} }}\n' for n, ts in techs.items())
            + '\tdebug_log = "PMR;rec=OBSPM;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetCountry.GetNameNoFormatting];'
            + ';'.join(fields) + '"\n'
            + ''.join(f'\tremove_variable = {n}\n' for n in vars_) + '}\n')


ON_ACTIONS = '''# Appended to vanilla on_actions the documented way (_on_actions.md, MODDING INFO):
# the vanilla on_action calls ours, nothing vanilla is overwritten.

on_game_started = { on_actions = { pmr_on_game_started } }
on_production_method_changed = { on_actions = { pmr_on_production_method_changed } }
on_building_built = { on_actions = { pmr_on_building_built } }
on_building_expanded = { on_actions = { pmr_on_building_expanded } }
on_monthly_pulse_state = { on_actions = { pmr_on_monthly_pulse_state } }
on_monthly_pulse_country = { on_actions = { pmr_on_monthly_pulse_country } }
on_acquired_technology = { on_actions = { pmr_on_acquired_technology } }
OBS_ON_ACTION
BUILD_ON_ACTION

# No root. Adopt every building's starting recipe, all levels on it.
pmr_on_game_started = {
	effect = {
		debug_log = "PMR;rec=LOADED;date=[TimeKeeper.GetCurrentDate.GetString];hook=on_game_started"
BUILD_STAMPSTART_STAFF		# No country is a player's yet here (no player state logs INIT), so no Buildings tab totals: pmr.1
		# sums the players' a day later, and the Buildings panel its own country's as it opens (pmr_c_view_sgui).
		# Review 9: every country's copy was about 380,000 variables by 1855 (q69), none ever read.
		# The market has no prices yet: the profit calculation uses base prices meanwhile (profit_effect).
		set_global_variable = pmr_setup
		# the Mod Template's "is loaded" flag, so other mods can tell PMR is running (exists = global_var:pmr_is_loaded)
		set_global_variable = { name = pmr_is_loaded value = yes }
HISTORY_FRAMES		every_country = {
			every_scope_state = {
				pmr_state_tick = yes
				pmr_auto_best = yes   # AUTO_BEST: government administration, universities, trade centres, carriages
			}
			# A day later the players exist: their totals, buildings abroad included (pmr.1).
			trigger_event = { id = pmr.1 days = 1 }
		}
		remove_global_variable = pmr_setup
START_LEFT	}
}

# Root = building whose production method changed. The switch is seen the moment it happens.
# A change a PMR tick makes itself (pmr_in_tick on the state) would only meet that tick's own guard,
# so it skips the dispatch over every PMR building type.
pmr_on_production_method_changed = {
	effect = {
		if = {
			limit = { state = { NOT = { has_variable = pmr_in_tick } } }
PMC_ON			pmr_tick_building = yes
PMC_OFF		}
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
		pmr_frame_new_building = yes   # no "less" modifier on it yet (frames.py)
		pmr_built_building = yes
		pmr_auto_building = yes   # AUTO_BEST: a new building starts on the best methods
		pmr_urb_built = yes   # the state Buildings tab's own list
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
		pmr_urb_built = yes   # the state Buildings tab's own list (its order is by level)
		# Last: the parent's tick can remove this retool building once its level is counted.
		pmr_tick_parent_of_retool = yes
	}
}

# Root = country that just acquired a technology. A newly unlocked recipe switches its buildings
# at once instead of at the next month turn.
pmr_on_acquired_technology = {
	effect = {
		# the player's only: a padded line per country per technology rotated debug.log (2026-10-19)
		if = { limit = { is_player = yes exists = capital } capital = { TECH_CRUMB } }
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

# Root = state. Backstop: recompute the shares and re-apply the blend every other month (TICK_EVERY) even if no event
# fired. pmr_month marks that tick: the trade-off shares step and the treatment shares are recounted.
pmr_on_monthly_pulse_state = {
	trigger = { NOT = { has_global_variable = pmr_ticks_paused } }
	effect = {
STATE_TURN		pmr_auto_best = yes
		pmr_principle_bonus = yes
		pmr_probe_state = yes
		pmr_urb_check = yes   # the state Buildings tab's own list
	}
}

# Root = country. The player's totals for the Buildings tab rows, once the month's state ticks are in
# (whichever pulse runs first, a change made only by the monthly tick shows within a month).
pmr_on_monthly_pulse_country = {
	trigger = { NOT = { has_global_variable = pmr_ticks_paused } }
	effect = {
		pmr_c_sum_all = yes
SKIP_REPORT
	}
}
'''

# Test builds: how Great Britain's and Austria's buildings start a new game, before PMR's first tick (q61). half = levels
# at 50% staffing or more; ranches; ports, of them port_basic on a basic port, and of those port_half at 50% staffing or
# more (q74). Since the method-count rework history names the pure frames, so a basic port is staffed as one.
START_PORTS = ('\t\t\t\t\tif = {\n\t\t\t\t\t\tlimit = { is_building_type = building_port }\n'
               '\t\t\t\t\t\tscope:pmr_ss_c = { change_variable = { name = pmr_ss_p add = 1 } }\n'
               '\t\t\t\t\t\tif = {\n\t\t\t\t\t\t\tlimit = { has_active_production_method = pm_basic_port }\n'
               '\t\t\t\t\t\t\tscope:pmr_ss_c = { change_variable = { name = pmr_ss_pb add = 1 } }\n'
               '\t\t\t\t\t\t\tif = { limit = { occupancy >= 0.5 } scope:pmr_ss_c = { change_variable = { name = pmr_ss_ph add = 1 } } }\n'
               '\t\t\t\t\t\t}\n\t\t\t\t\t}\n')
START_STAFF = ''.join(
    f'\t\tif = {{\n\t\t\tlimit = {{ exists = c:{tag} }}\n\t\t\tc:{tag} = {{\n\t\t\t\tsave_temporary_scope_as = pmr_ss_c\n'
    + ''.join(f'\t\t\t\tset_variable = {{ name = pmr_ss_{x} value = 0 }}\n' for x in ('n', 'h', 'r', 'p', 'pb', 'ph'))
    + '\t\t\t\tevery_scope_building = {\n\t\t\t\t\tlimit = { level > 0 }\n'
    '\t\t\t\t\tscope:pmr_ss_c = { change_variable = { name = pmr_ss_n add = 1 } }\n'
    '\t\t\t\t\tif = { limit = { occupancy >= 0.5 } scope:pmr_ss_c = { change_variable = { name = pmr_ss_h add = 1 } } }\n'
    '\t\t\t\t\tif = { limit = { is_building_type = building_livestock_ranch } '
    'scope:pmr_ss_c = { change_variable = { name = pmr_ss_r add = 1 } } }\n'
    + START_PORTS + '\t\t\t\t}\n'
    '\t\t\t\tdebug_log = "PMR;rec=START_STAFF;date=[TimeKeeper.GetCurrentDate.GetString];'
    'country=[THIS.GetCountry.GetNameNoFormatting];'
    + ';'.join(f"{lab}=[THIS.Var('pmr_ss_{x}').GetValue|0]" for lab, x in
               (('buildings', 'n'), ('half', 'h'), ('ranches', 'r'), ('ports', 'p'), ('port_basic', 'pb'), ('port_half', 'ph')))
    + '"\n'
    + ''.join(f'\t\t\t\tremove_variable = pmr_ss_{x}\n' for x in ('n', 'h', 'r', 'p', 'pb', 'ph'))
    + '\t\t\t}\n\t\t}\n' for tag in ('GBR', 'AUS'))

# Test builds: after the setup, the basic ports at 50% staffing or more (q73).
START_LEFT = ''.join(
    f'\t\tif = {{\n\t\t\tlimit = {{ exists = c:{tag} }}\n\t\t\tc:{tag} = {{\n\t\t\t\tsave_temporary_scope_as = pmr_ss_c\n'
    + ''.join(f'\t\t\t\tset_variable = {{ name = pmr_ss_{x} value = 0 }}\n' for x in ('pb', 'ph'))
    + '\t\t\t\tevery_scope_building = {\n\t\t\t\t\tlimit = { level > 0 is_building_type = building_port '
    'has_active_production_method = pm_basic_port }\n'
    '\t\t\t\t\tscope:pmr_ss_c = { change_variable = { name = pmr_ss_pb add = 1 } }\n'
    '\t\t\t\t\tif = { limit = { occupancy >= 0.5 } scope:pmr_ss_c = { change_variable = { name = pmr_ss_ph add = 1 } } }\n'
    '\t\t\t\t}\n'
    '\t\t\t\tdebug_log = "PMR;rec=START_LEFT;date=[TimeKeeper.GetCurrentDate.GetString];'
    'country=[THIS.GetCountry.GetNameNoFormatting];'
    "port_basic=[THIS.Var('pmr_ss_pb').GetValue|0];port_half=[THIS.Var('pmr_ss_ph').GetValue|0]\"\n"
    + ''.join(f'\t\t\t\tremove_variable = pmr_ss_{x}\n' for x in ('pb', 'ph'))
    + '\t\t\t}\n\t\t}\n' for tag in ('GBR', 'AUS'))

# Test builds. The observer game's monthly lines run outside the test pause, so its script-off years (obs_ab) are timed too.
OBS_ON_ACTIONS = f'''
# Root = country, an observer game's monthly pulse (test builds): PMR's script off in alternate years with
# --obs-script-off (pmr_obs_ab), and
# the OBS lines of the largest economies.
pmr_obs_monthly_country = {{
	trigger = {{ has_global_variable = pmr_obs }}
	effect = {{
		pmr_obs_ab = yes
		if = {{ limit = {{ gdp_ranking <= {OBS_TOP} }} pmr_obs_report = yes }}
		pmr_obs_army = yes
	}}
}}
'''

BUILD_ON_ACTIONS = '''
# Root = country (test builds made with --build): the BUILD line once a game year, from the largest economy, so a
# loaded save says which build carries it on.
pmr_build_monthly_country = {
	trigger = { gdp_ranking <= 1 NOT = { has_variable = pmr_build_chk } }
	effect = {
		set_variable = { name = pmr_build_chk value = yes days = 350 }
		pmr_build_stamp = yes
	}
}
'''


def build_stamp():
    """Any scope (test builds made with --build): the BUILD line and the build in the save (BUILD)."""
    if not BUILD:
        return ''
    tag, n, sha = BUILD
    return ('\n# Any scope (test builds made with --build): the BUILD line, and the build in the save: pmr_build the build\n'
            '# that ran last, pmr_build_first the one that started the game.\n'
            'pmr_build_stamp = {\n'
            f'\tset_global_variable = {{ name = pmr_build value = {n} }}\n'
            f'\tif = {{ limit = {{ NOT = {{ has_global_variable = pmr_build_first }} }} '
            f'set_global_variable = {{ name = pmr_build_first value = {n} }} }}\n'
            f'\tdebug_log = "PMR;rec=BUILD;date=[TimeKeeper.GetCurrentDate.GetString];build={tag};commit={sha};'
            f'version={MOD_VERSION}"\n'
            '}\n')


# The Mod Template's error suppression: pmr_is_loaded is set for other mods to read, never read by PMR itself, so the
# game would report it unused.
ERROR_SUPPRESSION_EVENTS = '''namespace = pmr_error_suppression

pmr_error_suppression.0001 = {
	hidden = yes
	orphan = yes
	trigger = {
		exists = global_var:pmr_is_loaded
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
		# an observer game (no player): pmr_obs, so the largest economies log (pmr_logged, OBS_REPORT)
		if = {
			limit = { NOT = { has_global_variable = pmr_obs_chk } }
			set_global_variable = pmr_obs_chk
			if = { limit = { NOT = { any_country = { is_player = yes } } } set_global_variable = pmr_obs }
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
	is_shown = { has_global_variable = pmr_ticks_paused }   # resume only (Pat paused a game with it by accident, 2026-10-19)
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
    ' pmr_test_pause_ticks_decision:0 "PMR test: resume the monthly ticks"',
    ' pmr_test_pause_ticks_decision_desc:0 "Resumes PMR\'s monthly ticks."',
]


if __name__ == '__main__':
    main()
