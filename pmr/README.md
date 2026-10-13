# Production Method Rework (PMR)

A script-only Victoria 3 mod. Recipes swap by technology as ordinary production methods, and a
recipe switch takes effect gradually as retooling construction completes: a building's goods and
workforce are the mix of the recipes its levels run.

- `ProductionMethodRework/` is the mod folder. Copy it into
  `Documents\Paradox Interactive\Victoria 3\mod\` and enable it in a playset.
- `RUNSHEET.md` is the test handover: what to do in game and the exact
  `debug.log` lines to look for, including what each null means.
- `tools/pmr/generate.py` writes the whole mod from the installed game's own script. Re-run it after
  every beta update: `python tools/pmr/generate.py --game "G:/SteamLibrary/steamapps/common/Victoria 3/game"`.
- `GENERATION_REPORT.json`, written into the generated mod folder, lists every building treated, every building
  skipped and why, and every recipe whose modifiers moved into share methods.

The mod output is not committed. It is generated locally from the installed game's script and copied
into the mod folder; only the generator, the design notes and the run sheet live in the repo. Target:
the 1.14.x open beta, `supported_version = 1.14.*`.

## The design, as built

| Design point | Where it lives |
| --- | --- |
| 1. The workforce blends (was: fixed) | Pat, 2026-10-13: the workforce follows the recipes like the goods. Each recipe's `level_scaled` employment moves into its share methods, scaled by its share of the levels, so a mine with 6 levels on Picks and Shovels and 5 on Condensing Engine Pump employs 6/11 of the first recipe's workforce and 5/11 of the second's. Each treated building still gets `pmg_pmr_labour_<b>` with one method, `pm_pmr_labour_<b>`, now carrying nothing: it is the slot the building browser rows and market lists draw as the gold main output good. |
| 1a. Automation from the third recipe | Pat, 2026-10-13: every recipe from the third on includes the building's automation: from each automation group (`pmg_automation_*`, `pmg_steam_automation_*`, `pmg_train_automation_*`) the most advanced method that runs without electricity, such as Rotary Valve Engine, Mechanized Looms, Automated Bakery, or for mines Steam Donkey plus Rail Transport. Its goods, pollution and job cuts are added to those recipes' share methods (`AUTOMATION_FROM_TIER = 3`), and the automation groups leave the building, so automation is never counted twice. Buildings with fewer than three recipes (plantations but coffee, vineyards, oil rigs, munition plants, automotive) keep their automation groups. No profession's workforce goes below zero (none does in 1.14.5). |
| 1b. Electricity | Pat, 2026-10-13: a recipe that needs electricity, through its own goods, its folded automation or vanilla's `required_input_goods`, becomes a building's target only while the state produces electricity (`sg:electricity` production above zero; electricity is a local good). Retooling towards such a target pauses, for the government and for investors, while the state produces none; levels already queued finish. The recipe methods lose `required_input_goods`, which would otherwise make the game switch a building off its recipe the day electricity ran out, and PMR would read that as a switch and retool backwards. In 1.14.5 the electric targets are: textile mill 4–5, furniture 4, tooling 5, explosives 4, steel 4, motor 2 and 4, shipyard 4, arms and artillery 5, logging 3 (the electric recipes of 1c, and vanilla recipes that use electricity themselves). |
| 1c. Electric automation is a recipe of its own | Pat, later on 2026-10-13, after Steel Tools showed an electricity input: automation that needs electricity (Assembly Lines, Automatic Power Looms) is not folded into the third recipe on. It becomes one more recipe on top of the newest, `pm_pmr_elec_<b>`, named "newest recipe + automation" (e.g. Machined Steel Tools + Assembly Lines). It is inserted into the vanilla recipe group, which the mod therefore shadows (`common/production_method_groups/01_industry.txt`), carries nothing itself like every recipe, and its share methods carry the newest recipe's goods and workforce plus the automation's. The tick makes it the target only when the owner has researched both the newest recipe's and the automation's technologies and the state produces electricity. In 1.14.5: textile mill, furniture, tooling, motor, arms and artillery. |
| 2. Recipes mark the target | The vanilla recipe methods keep their technology gates and anything not scaled by workforce, and lose employment and every `workforce_scaled` block (goods, pollution and the rest). They say which recipe the building runs, which is the retool target. Vanilla files are shadowed whole under their own names, so every other byte is the game's. |
| 3. Gradual switch, blended | The state keeps how many of the building's levels run each recipe (`pmr_lv_<i>_<b>`, i = the recipe's place in vanilla's group, oldest first). Per recipe, the building has a share group `pmg_pmr_share_<b>_<i>` of 101 methods, `pm_pmr_share_<b>_<i>_<n>`, each carrying that recipe's `workforce_scaled` modifiers and `level_scaled` employment × n/100. Every tick activates, in each share group, the method for that recipe's share of the levels, rounded to 1%, the target taking what is left so the shares sum to 100%. The building's goods are therefore the level-weighted mix of its recipes in its own production figures, scaled by employment and throughput like any recipe, and its profit and the investment AI's view of it follow. An iron mine with 15 of 20 levels on Atmospheric and 5 on Condensing runs Atmospheric 75% and Condensing 25%, coal included. Share method n unlocks only while lock method `pm_pmr_key_<b>_<i>_<n>` (no modifiers, in `pmg_pmr_key_<b>_<i>`) or the switching lock `pm_pmr_key_<b>_<i>_any` is active, as vanilla gates `pm_elastics`, so the AI never has a second share method to pick. Lock n in turn unlocks only while share n runs, so a lock group offers the AI two methods, not 102. To change a share the tick moves the lock to `_any`, then the share, then the lock to the new step, so the running share is never locked out. Each tick runs only when no tick of that building is already running (`pmr_busy_<b>`), because the game runs the tick a method change fires inside that change, and the re-entered tick left switched shares counted twice in 1.14.5. |
| 4. p is driven by construction | Pseudo-buildings cost 50% of the building's construction cost ÷ N per level, with N = 1 (steel: 800 × 0.5 = 400). Four private slots, `building_pmr_retool_<b>_1` … `_4`, are built only by private investors for the privately owned levels still to retool; `building_pmr_retool_gov_<b>` only by the government, for the government's own levels that don't run the target yet (Pat, 2026-10-13: splitting by ownership alone offered the government two old private levels of the Sicily sulfur mine after it had built two new levels on the new recipe). Nothing queues them: the investment pool picks the private slots (AI value from the building's earnings plus a top-up while open) and the player, or an AI government, builds the government one. Each tick gives each empty private slot one level, as a new construction, and the rest of the private room to the first slot with a finished level, and stores a cap per slot; `can_build_private` requires the slot to be open and under its cap (the canton-system pattern again), and the investing country's investors to own part of the building (`levels_owned_by_country`; for the state's own country, more than the government's levels), so an investment agreement alone does not let a foreign pool retool it. `can_build_government` caps the government building the same way. Every tick re-splits the levels nobody has queued. On 1.14.5 the investment pool never queued a second level on a retool building that had one in a year of testing, most likely `PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD` (0.8): the AI expands no building under 80% employment unless it hired last week, and a retool building employed nobody. Pat's crews (2026-10-13, 02:23Z: a fixed crew of 10 laborers per private slot so investors could expand it, removed 90 days after its last level if still short) did not make investors stack levels in game, and the finished slots cluttered the state's Buildings tab, so they are off (`RETOOL_CREW = 0`, Pat 03:37Z): every retool building, private or government, is removed once its levels are counted, and only construction sites show. A retool building is never removed while it has levels queued: that leaves a construction with no building, shown as NULL_STATE in the queue. |
| 5. Each completed retool level moves one building level | `pmr_progress_<b>`: retool levels completed since the last tick (per side, the slots' or the government building's `level`, less `pmr_seen_<side>_<b>`, ÷ N) move that many levels onto the target, oldest recipe first: a government level moves one of the government's own levels, a private one a privately owned level, and levels a side can't use move the other side's. The state tracks the government's levels per recipe (`pmr_lvg_<i>_<b>`): levels it gains go on the target first, as new levels arrive, then oldest first; levels it loses go from its oldest recipe. New building levels arrive on the target; lost levels go from the oldest recipe first. p is the target's share. When every level is on the target, the target's share method is at 100% and the others at 0%. |
| 5a. Investment randomness | Pat, 2026-10-13: the investment pool's building-type roll multiplies each candidate's score by (1 + F·u1) / (1 + F·u2), F = `PRODUCTION_BUILDING_RANDOM_FACTOR` (10) × `PRODUCTION_BUILDING_AUTONOMOUS_INVESTMENT_RANDOM_FACTOR_MULT`. The mod sets the multiplier to 1 (vanilla 2), so the roll spans 1/11 to 11 instead of 1/21 to 21 (`common/defines/zz_pmr_ai.txt`, `INVESTMENT_RANDOM_FACTOR_MULT`). It is a define, so it applies to every building, not only retooling. The 80% employment gate (`PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD`) stays vanilla. Analysis: `/mnt/project-files/pmr/investment-ai.md`. |
| 6. Second groups blend too | Pat, 2026-10-13. Two kinds of second production method group become shares like the recipes. **Trade-offs, by local prices** (`TRADE_GROUPS`: hardwood, the rye, wheat, rice, maize and millet secondary crops, the textile mill, furniture and glassworks luxury lines, canning and distilling, aeroplanes and tanks): each option's value per level is what its goods add at this state's prices (base cost × the local price ratio, read through the `state_goods_pricier` / `state_goods_cheaper` ladder in 5% steps, `pmr_px_<good>`), "none" being worth 0. Once a month points move from the worst-paying option holding a share to the best-paying one that can run, when the gap is over `TRADE_DEAD_BAND` = 5% of the first recipe's output value per level: as many points as the gap in % of that output value (`TRADE_GAIN` = 1), from 2 to 20 (`TRADE_STEP_MIN`, `TRADE_STEP_MAX`), so the move slows as prices answer. Pat, 2026-10-13: a flat 2 points took Yorkshire's rye farms 33 months to reach 66% Apple Orchards. An option that can no longer run sheds first, at the full 20. At game start each building type starts on `TRADE_PRELOAD`, the level-weighted mix that every building of the type in Pat's 1838-10-28 save was heading for (its best-paying option at its state's prices, none inside the dead band), read with `tools/pmr/save_blends.py` (Pat, 2026-10-13: start near where games take it, so shares need not travel far); a preloaded option that can't run here passes its share to the option before it, then to none, and a type with no entry (automotive) keeps vanilla's history choice. The test decision "PMR test: record trade-offs worldwide" logs every state's shares (`WORLD`) for refreshing the table from a later save. A building built later starts wholly on the best-paying option. **Plantation treatment, by acceptance** (every group with a violent or exploitative method): the workforce with acceptance under 40 is the violent share and 40–59 the harsh share, recounted monthly (`TREAT_BANDS`). The law wins: a barred violent share goes to harsh, a barred harsh share to standard. Either way each option gets `pmg_pmr_x_<b>_<j>` of 101 methods `pm_pmr_x_<b>_<j>_<n>` carrying every effect of the vanilla method × n/100 (building, state and country modifiers, output included), with lock group `pmg_pmr_xk_<b>_<j>` as for recipes. The vanilla methods stay on the building as markers with their effects and `required_input_goods` cut: they hold the history choice for game start and gate each option through `can_activate_production_method` (technology, laws, the recipe it needs). Rayon and radios stay vanilla, as their buildings are not PMR buildings. Tech ladders (automation, explosives, rail and the like) are not blended yet. |
| 7. The construction panel's Private tab | Pat, 2026-10-13 (03:52Z to 04:16Z), built in the "Investment pool sliders by building group" thread: `tools/pmr/private_investment.py`, called last from `generate.py` (its docstring and `/mnt/project-files/pmr/investment-sliders/README.md` carry the detail). The construction panel's tabs become Government, Private, Foreign and Ships, and the funding filter goes (shadowed `gui/construction_panel.gui` and `gui/construction_queue.gui`; the tab itself is `gui/pmr_private_investment.gui`). Private shows the weekly re-investment, a 24-month column chart of it (sampled monthly into `pmr_ri_<i>`, as the game keeps no history of the inflow), the game's own breakdown of what feeds the pool, the economic law as a card beside a policy card, investment priority sliders, the private queue and recent investments. **Sliders**: 0 to 100% of a cap per building group, +50% weight or +75% under Steer the Economy; every `investment_scores` entry in a shadowed `11_private_infrastructure.txt` is multiplied by `(100 + boost) / (100 + highest boost)`, so AI countries and untouched sliders stay vanilla, and Manufacturing is split into Light, Heavy and Military Industry. **Policy cards**, Interventionism only, one at a time as a static modifier, dropped monthly once the law goes: Steer the Economy (the higher cap); Favour Large Corporations (each building type a company lists, in PMR's building files, gets `ai_value = pmr_ai_value_<b>`, its vanilla value plus 75,000 while the state's owner holds the card and has such a company); Re-invest (each private retool building's `ai_value`, the retool weight 1,000 + 7,500 × earnings per worker + 150,000, ends with `multiply = pmr_reinvest_mult_<group>`, 1 + 0.99 × the group's slider, so up to ×100); Favour Small Businesses (shopkeepers' investment efficiency +15%, self-investment chance +10%). Government retool buildings are untouched. **Revised 13:05Z (Pat):** the top shows the budget panel's Investment Pool line; the trend line's cells use `gfx/interface/backgrounds/white.dds` (the `colors/white.dds` used before is not in 1.14.5, so nothing drew); the contributors are a tree chart of privately owned levels per priority group (`pmr_pc_<i>`, recounted when the tab opens and monthly; tiles find their group by their index in `DataModelRepeatedItem`), with the game's own list in money as its tooltip, since the game gives that list only as text; the sliders become five priority groups, Light Industries, Heavy Industries, Agriculture, Resources and Infrastructure (`GROUPS`, each over vanilla building groups), reading +0% or the boost in green; the law and policy cards are 268×380 with the law's effects scrolling; and Add Policy opens an Economic Policies window beside the panel (the window root's `map_modes_button` block) with every policy as a card, each with a few added modifiers. **Revised 14:28Z (Pat):** the re-investment line records weekly from a self-re-arming hidden event (`pmr_pi.1`; 1.14.5 runs no weekly on_action for script) into `pmr_rw_<i>` over 26 weeks, the monthly `pmr_ri_*` left unread; under the line each week's column is split by the tree chart's shares that week (`pmr_rs_<g>_<i>` running totals, `pmr_rc_<g>_<i>` heights in rows, drawn as vertical progressbars from the back); vanilla's investment pool graph (`GetInvestmentFundTrend`) sits beside it, both plots narrowed through `v3_plotline`'s `margins` block. Recent Investments gains two stacked bars, domestic vs foreign and by priority group, by construction points of the levels the player's investors complete: the game lists previous investments only as text, so `on_start_expanding_building` notes the player's and every government's levels in a building on its state by type (`pmr_iv_o_<b>`, `pmr_iv_g_<b>`, read by halving steps on `levels_owned_by_country` and `country_ownership_fraction`), and PMR's completion handlers count a level when the player's levels rose and no government's did (`PMR;rec=INVEST`, `kind=private`); retool buildings, canals, the construction sector and subsistence buildings are left out. Policies are clickable blue cards (vanilla's `default_button`) showing benefits only, the explanation in a tooltip. Construction and investment efficiency are left to Laissez-faire: Favour Large Corporations gives +1 free company charter, +1 maximum companies and +10% company government dividends (1.14.5 has no per-company monopoly modifier), Steer keeps only its cap, Small Businesses loses the farmers bonus. |
| 8. Retooling what the player owns abroad | Pat, 2026-10-13 14:33Z and 14:36Z (East India Company states: levels of the player's government and investors could not upgrade). In another country's state where the player owns levels (`pmr_abroad_<b>`, set on each tick from `levels_owned_by_country` against the global `pmr_player`), a recipe counts as available when the player has its technologies (`abroad()` in `generate.py`; recipes gated by anything but technology stay on the host's rules). The host's own best (`pmr_hbest_<b>`) is kept apart: when the player's best is beyond it, the marker can't be activated, so the target moves directly (`PMR;rec=ABROAD`, with `host_best=`) and the switch ignores marker changes below the target. No script can queue a construction for a foreign government, so government levels abroad are read as private and the player's investors retool every level; the upgrade button stays domestic. Research re-ticks such states (`pmr_state_research_abroad`). |
| The building panel | A shadowed `gui/building_details_panel.gui` (vanilla's, with two patches the generator asserts). On a PMR building the production method grid is hidden (the grid keeps a column for every group even when hidden, so hiding items was not enough once each recipe had share and lock groups) and nothing takes its place (Pat, 2026-10-13: no goods icon). The recipe row runs from the panel's left edge to the employment and cash-reserve bars: the recipe's name, the government upgrade button against the employment bar, and below them a recipe bar, built the way vanilla builds the Owners bar: one slice per recipe, oldest on the left, as wide as that recipe's share of the levels (`layoutstretchfactor_horizontal`), on vanilla's stacked bar chart texture in a muted colour per tier, the same on every building (`TIER_COLORS`: bronze, ochre, steel blue, plum, slate; no red or green), with the recipe's icon centred on any slice over 25%. Under that row, one more bar per blended second group (6), the details panel only (`block "pmr_option_bars"`, added to `condensed_building_information` and filled by the panel's own instance so Buildings tab rows keep their height): aligned under the recipe bar, grey for none then each option in a second muted palette (`OPTION_COLORS`: sand, dusk blue, mauve, umber), with vanilla's own name for the group in the employment bars' column beside it (Hardwood Production, Secondary, Luxury Production, Canning, Distilleries, Working Conditions, Aeroplanes, Tanks), cut with an ellipsis if it would run past the panel (Pat, 2026-10-13). Its tooltip gives each share, for trade-offs each option's earnings per level a week at local prices, a locked or barred note, and one line on how the group moves. The recipe bar's tooltip lists every recipe's share; the title reads the building custom localization `pmr_new_recipe`, with the target's share while retooling. The same row (vanilla's `condensed_building_information`) is each building's row when a building type is expanded in the Buildings tab. The wide building browser's rows show the bar beside the gold labour icon (`tools/pmr/icons.py`). The bar is 32 px tall, as tall as the cash reserves bar looks (Pat, 2026-10-13). The Owners list gets a Production Method column (Pat, 2026-10-13) with the icons of the recipes the row's levels run: a government row shows the government's levels, every private row the private owners' together, since PMR tracks the two sides, not each owner; the tooltip gives the counts. On a PMR building the vanilla header and rows are hidden and narrower copies drawn (owner 230, method 120, levels 90, dividends 100). |
| The Buildings tab type row | In `gui/production_methods.gui`, each PMR building type's row (`buildings_production_method_item`) shows, where vanilla's method grid was, the recipe bar over all of the player's buildings of that type, and the upgrade button left of nationalize, which queues every government retool level in every state (`pmr_gov_retool_c_<b>_sgui`, country scope). The totals are country variables (`pmr_c_*_<b>`), summed over the country's states after every single tick and once for all types after the monthly and research ticks, and for every country at game start, when no country is a player's yet (1.14.5 logs no player INIT lines there). A player's totals also add buildings abroad that the country or its investors own levels in (`levels_owned_by_country`), whole, since the tab lists them; that scans every state, so it runs for players only, monthly, after research and the day after game start (hidden event `pmr.1`). The upgrade button's room stays domestic. Each player sum writes `PMR;rec=CSUM`. |
| The government upgrade button | Beside the recipe name, against the employment bar, and in each building browser row left of nationalize (the browser grows 35 px to make room). It runs the scripted GUI `pmr_gov_retool_<b>_sgui` (state scope), which queues every government retool level the building still needs (`start_building_construction`, once per level of the government's room) and ticks the building. Greyed out unless the state is the player's and the government has room left, which needs government-owned levels not yet on the target. |
| Recipes switch on research | With the selector gone, each tick finds the newest recipe the building can run (the last in the vanilla group that `can_activate_production_method` allows) and, when that rises, activates it, which starts retooling like any switch. A newly constructed building starts on the newest recipe at no cost. |

p is recomputed on these hooks, all appended to vanilla on_actions the documented way:
`on_production_method_changed` (the switch is seen at once), `on_acquired_technology` (research
switches at once), `on_building_built` and `on_building_expanded` (a building's first level and each
later one; together every completed retool level moves p at once), `on_monthly_pulse_state`
(backstop), and `on_monthly_pulse_country` (the player's Buildings tab totals). A save that predates the mod
adopts each building's current recipe, every level on it, on its first tick. A save made with an
earlier build of PMR is not supported: its lag modifiers and retool buildings no longer exist.

Two log-only probes (`PROBE_TREAT`, `PROBE_PRICE` in `generate.py`) can run from `on_monthly_pulse_state`, in
player-owned states (`pmr_probe_effects.txt`, `pmr_probe_values.txt`). `TREAT` counts each plantation's workforce by
acceptance band; `PRICE` reads the local hardwood and wood prices through the `state_goods_pricier` /
`state_goods_cheaper` ladder. Both answered their questions and are off since the 2026-10-13 performance round. The blending itself (6) logs `OPT` monthly per building type in player-owned states.

A loop breaker guards every building type's tick (`TICK_TRIP`): past 25 outermost runs in one state
on one day, that building waits for the next day and PMR logs `TRIP`. It went in after a game froze
during the daily update of 16 June 1836. `TECH`, `RETOOL_LEVEL`, `RELEASE` and `RELEASED` lines mark
the rarer actions in every country and are padded past 4 KB (`flush_log`), so they reach debug.log
even when the game hangs right after them.

**Performance (Pat approved 2026-10-13 13:12Z; review in `/mnt/project-files/pmr/perf/README.md`).** Log-only
diagnostics (pool, unemployment, home investors, the second blend read) run only in the player's states. The ownership
and earnings ladders are bisected, and earnings are read only while a building needs retooling. Electricity is read
once per state per tick (`pmr_elec_read`) and each good's price once per state per day (`pmr_pxd_<good>`). Research
ticks only buildings whose best recipe changed or that have no blend yet (`pmr_state_research`), so a trade-off
research unlocks shows as unavailable until the month turns. The state flag `pmr_in_tick` makes
`on_production_method_changed` skip the tick's own activations. The Buildings tab caches the player's buildings abroad
(`pmr_cf_*`) between the monthly and research sums. The test decision "PMR test: pause or resume the monthly ticks"
sets the global `pmr_ticks_paused`, which stops the monthly state and country ticks and the research tick, so a year can
be timed with and without PMR's script in one save.

## Scope

Treated: every building in industry, agriculture, mining, plantations and the
misc-resource file (logging, fishing, whaling, oil, rubber) whose first production method group
holds two or more recipes. Skipped: synthetics plant, electrics industry and gold fields (one recipe
each), and the government, military, urban, infrastructure, monument, canal, subsistence, company
and construction-sector buildings, whose first group is not a goods recipe or whose retooling would
be paid for by itself.

## Why share methods and not modifiers

An earlier build scaled the target recipe's goods back with `goods_*_mult` static modifiers and
added goods only an old recipe has with `goods_*_add` ones. On 1.14.5 the economy reads a building
static modifier's `_mult` but ignores its goods `_add`: an iron mine retooling from Atmospheric to
Diesel lost its coal although the modifier showed. A production method's `workforce_scaled` goods
are what the economy, the building's profit and the investment AI all read, so the blend is made of
production methods.

## Where PMR keeps its numbers

Buildings cannot hold script variables on 1.14.5 (`This scope doesn't support variables. Scope:
Building`), so every number PMR keeps for a building lives on its state, named by building type:
`pmr_p_steel_mill` on a state is that state's steel mill's p. A state has at most one building of
each type. The tick runs in state scope; it reads the building's level and ownership through `b:<type>` and
switches its methods with state-scope `activate_production_method`.

## Choices made where the design was silent

- **Only the recipe group and, from the third recipe, the automation groups are folded.** Other
  secondary groups (canning, luxury goods, explosives, harvesting, refrigeration, ...) keep their
  vanilla methods and employment changes. Pat's automation rule names automation, and vanilla names
  those groups; farms' harvesting and logging equipment are not named automation and are left alone.
- **A newer recipe mid-retool keeps what is done.** Levels already moved keep their recipe; every
  level not on the new target is to retool, oldest recipe first. Retool levels already queued
  continue and count toward the new target. Switching to a recipe that every level already runs
  costs nothing and ends retooling.
- **The newest recipe is taken directly.** Research that unlocks two recipes at once (or a country
  that already has both) moves straight to the newer one; the levels never pass through the middle.
- **The blend is in 1% steps** (`SHARE_STEPS = 100`, Pat 2026-10-13; it was 5%). A building whose
  level count divides 100 is exact; otherwise each recipe's share is rounded, oldest recipes first,
  and the target takes the remainder. The cost is 26,593 hidden methods (203 per recipe) and a
  scripted-effects file of about 11 MB, almost all of it the bisected ladders that pick a step; a
  tick reads about seven comparisons per recipe.
- **Companies list the first private retool slot.** Pat dropped company listing on 2026-10-12 to keep
  Retooling icons out of company panels, and asked for it back on 2026-10-13 so companies can own
  and expand retooling: the autonomous investment AI favours expanding a building type a company
  lists in a state that has it. Only `building_pmr_retool_<b>_1` is listed (`COMPANY_RETOOL_SLOTS`),
  so a company panel shows one Retooling icon per building type it lists. A company-owned building
  retools either way: its headquarters owns levels the way a Financial District does.
- **The Owners column tracks two sides, not each owner.** PMR can't keep a variable per owner, so it
  knows which recipes the government's levels run and which the private owners' run together.
- **Newest means last in the vanilla list.** Vanilla orders recipe groups oldest first; the generator
  does not check that every group is a strict progression.
- **Only research and new construction switch recipes.** Automation and any other multi-method group
  on a PMR building are hidden too and stay on whatever they run, in the building panel, the
  Buildings tab and the market panel's building lists.
- **Pollution and every other workforce-scaled modifier blend too.** They move into the share
  methods with the goods. Modifiers a recipe applies per level or flat stay on the recipe method and
  follow the target.
- **Other `_mult`s on the same good apply to the blend as they would to a recipe**, since the share
  methods' goods are ordinary production method goods.
- **The government share is read in 5% steps** through `country_ownership_fraction`, a ladder of
  constant comparisons. Its level count (`gov_levels`, used in the investor check) is exact up to 19
  levels and can be one off above that.
- **Investors need a group they score.** `bg_pmr_retool` is a child of `bg_manufacturing`, which
  Financial Districts score; standing alone, 1.14.5 never gave it a private investor. Countries
  whose private investment comes only from Manor Houses (which score manufacturing 0) may never
  retool their private share.
- **AI value steers the investment pool** (seen in game on 1.14.5 at 1,000,000): a retool building is
  picked ahead of everything else, at home and abroad. That is why the ownership check matters.
  `ai_value` replaces the base weight of 1,000; the profit terms in `00_ai.txt` are per pound of
  predicted profit per employee and per pound of goods produced, and a retool building has neither.
  So PMR builds the weight itself (Pat, 2026-10-13, with the roll at 1/11..11): what vanilla would
  score an expansion of the building from its profit, 1,000 + 7,500 × e, with e the building's
  earnings per employee read with a ladder (`earnings`, 2 to 50, 0 below), plus a top-up of 150,000.
  Retooling is then the likelier pick, about three times a new building earning the same at e = 10,
  but the random roll and vanilla's multipliers (a shortage ×5, a company) can still beat it, as Pat
  wanted. Until then the weight was a flat 1,000,000. The same weight applies to AI governments'
  government retooling. `TICK` lines log `earn=` and `ai_w=`.
- **The retool buildings are gated.** `potential` is true only while script holds a state variable
  for that retool, so neither shows in any construction list outside a retool.

## Assumptions about game script that are not verified in game

Everything below is read from the installed game's script and the generated docs in
`Documents\Paradox Interactive\Victoria 3\docs\`. None of it
has run yet; the run sheet says how each shows up when it fails.

1. Each share method's goods count once now that only the outermost tick runs. Seen in game:
   `activate_production_method` in state scope applies a share at once (`active=` matches `blend`
   on the same line), and the tick that its `on_production_method_changed` fires runs inside the
   change (a `SWITCH` line is logged before the line of the tick that made the switch). Before the
   `pmr_busy_<b>` guard, every switched share was counted twice, through either order of lock and
   share. Why is inferred: the outer tick activated again a share the inner tick had already applied.
2. The AI leaves the lock groups alone, including the switching lock: their methods carry nothing, and vanilla's production method
   AI keeps the current method when a change gains nothing (`PRODUCTION_METHOD_STICKINESS_*`).
3. `on_production_method_changed`, `on_building_built` and `on_building_expanded` fire with the building as root.
4. `level_after_queued_constructions` and `country_ownership_fraction` behave as documented.
5. `can_activate_production_method` on a second-group marker stripped of its effects still reports
   whether its technology and laws allow it (the `can=` field of `OPT`).
6. A `type = state` custom localization reads a state variable in its trigger (`pmr_xlk_<b>_<j>`, the
   ", not unlocked here" note in the trade-off tooltip).
7. `[THIS.GetBuilding.GetState...]` and `[THIS.Var('x').GetValue]` resolve inside `debug_log` text in
   building scope.
