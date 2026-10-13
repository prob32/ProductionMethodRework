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
| 1a. Full automation from the third recipe | Pat, 2026-10-13: every recipe from the third on includes full automation. Full automation is the last method of each of the building's automation groups (`pmg_automation_*`, `pmg_steam_automation_*`, `pmg_train_automation_*`): Assembly Lines, Automatic Power Looms, Automated Bakery, Rotary Valve Engine, or for mines Steam Donkey plus Rail Transport. Its goods, pollution and job cuts are added to those recipes' share methods (`AUTOMATION_FROM_TIER = 3`), and the automation groups leave the building, so automation is never counted twice. Buildings with fewer than three recipes (plantations but coffee, vineyards, oil rigs, munition plants, automotive) keep their automation groups. No profession's workforce goes below zero (none does in 1.14.5). |
| 1b. Electricity | Pat, 2026-10-13: a recipe that needs electricity, through its own goods, its folded automation or vanilla's `required_input_goods`, becomes a building's target only while the state produces electricity (`sg:electricity` production above zero; electricity is a local good). Retooling towards such a target pauses, for the government and for investors, while the state produces none; levels already queued finish. The recipe methods lose `required_input_goods`, which would otherwise make the game switch a building off its recipe the day electricity ran out, and PMR would read that as a switch and retool backwards. In 1.14.5 the electric targets are: textile mill 3–4, furniture 3, tooling 3–4, explosives 4, steel 4, motor 2–3, shipyard 4, arms and artillery 3–4, logging 3. |
| 2. Recipes mark the target | The vanilla recipe methods keep their technology gates and anything not scaled by workforce, and lose employment and every `workforce_scaled` block (goods, pollution and the rest). They say which recipe the building runs, which is the retool target. Vanilla files are shadowed whole under their own names, so every other byte is the game's. |
| 3. Gradual switch, blended | The state keeps how many of the building's levels run each recipe (`pmr_lv_<i>_<b>`, i = the recipe's place in vanilla's group, oldest first). Per recipe, the building has a share group `pmg_pmr_share_<b>_<i>` of 101 methods, `pm_pmr_share_<b>_<i>_<n>`, each carrying that recipe's `workforce_scaled` modifiers and `level_scaled` employment × n/100. Every tick activates, in each share group, the method for that recipe's share of the levels, rounded to 1%, the target taking what is left so the shares sum to 100%. The building's goods are therefore the level-weighted mix of its recipes in its own production figures, scaled by employment and throughput like any recipe, and its profit and the investment AI's view of it follow. An iron mine with 15 of 20 levels on Atmospheric and 5 on Condensing runs Atmospheric 75% and Condensing 25%, coal included. Share method n unlocks only while lock method `pm_pmr_key_<b>_<i>_<n>` (no modifiers, in `pmg_pmr_key_<b>_<i>`) or the switching lock `pm_pmr_key_<b>_<i>_any` is active, as vanilla gates `pm_elastics`, so the AI never has a second share method to pick. Lock n in turn unlocks only while share n runs, so a lock group offers the AI two methods, not 102. To change a share the tick moves the lock to `_any`, then the share, then the lock to the new step, so the running share is never locked out. Each tick runs only when no tick of that building is already running (`pmr_busy_<b>`), because the game runs the tick a method change fires inside that change, and the re-entered tick left switched shares counted twice in 1.14.5. |
| 4. p is driven by construction | Pseudo-buildings cost 50% of the building's construction cost ÷ N per level, with N = 1 (steel: 800 × 0.5 = 400). Four private slots, `building_pmr_retool_<b>_1` … `_4`, are built only by private investors for the privately owned share of the levels still to retool, one level each at a time; `building_pmr_retool_gov_<b>` only by the government, for its share. Nothing queues them: the investment pool picks the private slots (AI value 1,000,000 while open) and the player, or an AI government, builds the government one. Each tick opens as many empty private slots as the private share has room for; `can_build_private` requires the slot to be open and empty, and the investing country's investors to own part of the building (`levels_owned_by_country`; for the state's own country, more than the government's levels), so an investment agreement alone does not let a foreign pool retool it. `can_build_government` caps the government building at its share, the way vanilla caps trade centers under the canton system. Every tick re-splits the levels nobody has queued by current ownership. On 1.14.5 the investment pool never queued a second level on a retool building that had one in a year of testing (most likely `PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD`: a retool building employs nobody), so a slot is removed once its level is counted and nothing is queued on it, and the next level is a new construction. A retool building is never removed while it has levels queued: that leaves a construction with no building, shown as NULL_STATE in the queue. |
| 5. Each completed retool level moves one building level | `pmr_progress_<b>`: retool levels completed since the last tick (every slot's and the government building's `level`, less `pmr_seen_<b>`, ÷ N) move that many levels onto the target, oldest recipe first, and the shares follow. New building levels arrive on the target; lost levels go from the oldest recipe first. p is the target's share. When every level is on the target, the target's share method is at 100% and the others at 0%. |

| The building panel | A shadowed `gui/building_details_panel.gui` (vanilla's, with two patches the generator asserts). On a PMR building the production method grid is hidden (the grid keeps a column for every group even when hidden, so hiding items was not enough once each recipe had share and lock groups) and nothing takes its place (Pat, 2026-10-13: no goods icon). The recipe row runs from the panel's left edge to the employment and cash-reserve bars: the recipe's name, the government upgrade button against the employment bar, and below them a recipe bar, built the way vanilla builds the Owners bar: one slice per recipe, oldest on the left, as wide as that recipe's share of the levels (`layoutstretchfactor_horizontal`), on vanilla's stacked bar chart texture in a muted colour per tier, the same on every building (`TIER_COLORS`: bronze, ochre, steel blue, plum, slate; no red or green), with the recipe's icon centred on any slice over 25%. Its tooltip lists every recipe's share; the title reads the building custom localization `pmr_new_recipe`, with the target's share while retooling. The same row (vanilla's `condensed_building_information`) is each building's row when a building type is expanded in the Buildings tab. The wide building browser's rows show the bar beside the gold labour icon (`tools/pmr/icons.py`). |
| The Buildings tab type row | In `gui/production_methods.gui`, each PMR building type's row (`buildings_production_method_item`) shows, where vanilla's method grid was, the recipe bar over all of the player's buildings of that type, and the upgrade button left of nationalize, which queues every government retool level in every state (`pmr_gov_retool_c_<b>_sgui`, country scope). The totals are country variables (`pmr_c_*_<b>`), summed over the player's states after every single tick and once for all types after the monthly, research and game-start ticks. |
| The government upgrade button | Beside the recipe name, against the employment bar, and in each building browser row left of nationalize (the browser grows 35 px to make room). It runs the scripted GUI `pmr_gov_retool_<b>_sgui` (state scope), which queues every government retool level the building still needs (`start_building_construction`, once per level of the government's room) and ticks the building. Greyed out unless the state is the player's and the government has room left, which needs government-owned levels still to retool. |
| Recipes switch on research | With the selector gone, each tick finds the newest recipe the building can run (the last in the vanilla group that `can_activate_production_method` allows) and, when that rises, activates it, which starts retooling like any switch. A newly constructed building starts on the newest recipe at no cost. |

p is recomputed on these hooks, all appended to vanilla on_actions the documented way:
`on_production_method_changed` (the switch is seen at once), `on_acquired_technology` (research
switches at once), `on_building_built` and `on_building_expanded` (a building's first level and each
later one; together every completed retool level moves p at once), `on_monthly_pulse_state`
(backstop), and `on_monthly_pulse_country` (the player's Buildings tab totals). A save that predates the mod
adopts each building's current recipe, every level on it, on its first tick. A save made with an
earlier build of PMR is not supported: its lag modifiers and retool buildings no longer exist.

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
- **Companies do not list the retool buildings.** Listing them let the pool make a company the owner
  of retooling, but every company panel then showed the Retooling icons, and Pat chose to drop it
  (2026-10-12; `COMPANY_RETOOL` in the generator). A company-owned building still retools: its
  headquarters owns levels the way a Financial District does, so its country's investors pass the
  ownership check.
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
- **AI value steers the investment pool** (seen in game on 1.14.5): a 1,000,000 retool building is
  picked ahead of everything else, at home and abroad. That is why the ownership check matters.
  `ai_value` replaces the base weight of 1,000; the profit terms in `00_ai.txt` are per pound of
  predicted profit per employee and per pound of goods produced, and a retool building has neither,
  so a loss-making building is retooled as eagerly as a profitable one.
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
5. `[THIS.GetBuilding.GetState...]` and `[THIS.Var('x').GetValue]` resolve inside `debug_log` text in
   building scope.
