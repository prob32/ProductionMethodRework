# Production Method Rework (PMR)

A script-only Victoria 3 mod. Labour is fixed per building, recipes swap by technology as ordinary
production methods, and a recipe switch takes effect gradually as retooling construction completes.

- `ProductionMethodRework/` is the mod folder. Copy it into
  `Documents\Paradox Interactive\Victoria 3\mod\` and enable it in a playset.
- `RUNSHEET.md` is the test handover: what to do in game and the exact
  `debug.log` lines to look for, including what each null means.
- `tools/pmr/generate.py` writes the whole mod from the installed game's own script. Re-run it after
  every beta update: `python tools/pmr/generate.py --game "G:/SteamLibrary/steamapps/common/Victoria 3/game"`.
- `GENERATION_REPORT.json`, written into the generated mod folder, lists every building treated, every building
  skipped and why, and every lag entry the design cannot express.

The mod output is not committed. It is generated locally from the installed game's script and copied
into the mod folder; only the generator, the design notes and the run sheet live in the repo. Target:
the 1.14.x open beta, `supported_version = 1.14.*`.

## The design, as built

| Design point | Where it lives |
| --- | --- |
| 1. Labour is fixed | Each treated building gets `pmg_pmr_labour_<b>` with one method, `pm_pmr_labour_<b>`, holding the default recipe's `level_scaled` employment. The recipe methods lose their `building_employment_*` lines. Steel: shopkeepers 500, laborers 3500, machinists 750, engineers 250, from Blister. |
| 2. Recipes are ordinary methods | The vanilla recipe methods, unchanged apart from employment: `goods_input_<g>_add` / `goods_output_<g>_add` in `workforce_scaled`. Vanilla files are shadowed whole under their own names, so every other byte is the game's. |
| 3. Gradual switch | `common/static_modifiers/pmr_lag_modifiers.txt`: one modifier per ordered recipe pair, values old/new − 1. Applied to the building with `multiplier = 1 − p` and re-applied whenever p moves. Steel Blister → Bessemer is `goods_input_iron_mult = -0.33333`, `goods_output_steel_mult = -0.27778`, no coal entry. |
| 4. p is driven by construction | `building_pmr_retool_<b>` costs 50% of the building's construction cost ÷ N per level (steel: 800 × 0.5 ÷ 4 = 100). A switch queues N × level of it: the government-owned share through `start_building_construction`, the rest through `start_privately_funded_building_construction`. |
| 5. p is read, not accumulated | `p = (retool.level ÷ N + level − L_start) ÷ level`, clamped to 0..1, in `pmr_tick_<b>`. When p reaches 1 the lag and the retool building are removed. |

| The building panel | A shadowed `gui/building_details_panel.gui` (vanilla's, with two patches the generator asserts). On a PMR building the production method row shows only the fixed labour slot, drawn as the building's main output good in gold (`tools/pmr/icons.py`, written to `gfx/.../production_method_icons/pmr_labour_<b>.dds`). Beside it a recipe bar, sized to sit between that slot and the employment and cash-reserve bars: gold is the recipe the building fully runs, blue the share already retooled to the new one. It reads `pmr_bar_old`, `pmr_p` and two building custom localizations, `pmr_old_recipe` and `pmr_new_recipe`. |
| Recipes switch on research | With the selector gone, each tick finds the newest recipe the building can run (the last in the vanilla group that `can_activate_production_method` allows) and, when that rises, activates it, which starts retooling like any switch. A newly constructed building starts on the newest recipe at no cost. |

p is recomputed on three hooks, all appended to vanilla on_actions the documented way:
`on_production_method_changed` (the switch is seen at once), `on_building_built` (each completed
retool level moves p at once), and `on_monthly_pulse_state` (backstop). A save that predates the mod
adopts each building's current recipe with no lag on its first tick.

## Scope

Treated: every building in industry, agriculture, mining, plantations and the
misc-resource file (logging, fishing, whaling, oil, rubber) whose first production method group
holds two or more recipes. Skipped: synthetics plant, electrics industry and gold fields (one recipe
each), and the government, military, urban, infrastructure, monument, canal, subsistence, company
and construction-sector buildings, whose first group is not a goods recipe or whose retooling would
be paid for by itself.

## Choices made where the design was silent

- **Only the recipe group is stripped of labour.** Automation and other secondary groups keep their
  vanilla employment changes (a watertube boiler still removes 1,500 laborers). The design says recipe
  methods carry goods only and says nothing about the others.
- **Switching back cancels.** Switching to the recipe the building last fully ran removes the lag and
  the retool building with no cost. Switching to a third recipe mid-retool restarts retooling from the
  last fully-run recipe, against the new pair.
- **Lags the design cannot express are left out and listed.** When the new recipe has none of a good
  the old one used (glassworks wood when moving to crystal glass, shipyard clippers when moving to
  metal shipbuilding), `old/new − 1` divides by zero and no `_mult` can restore it, so that good
  switches at once.
  `GENERATION_REPORT.json` lists every one.
- **Newest means last in the vanilla list.** Vanilla orders recipe groups oldest first; the generator
  does not check that every group is a strict progression.
- **Only research and new construction switch recipes.** Automation and any other multi-method group
  on a PMR building are hidden too and stay on whatever they run. The building browser's
  per-building-type production method menus still exist and still switch recipes; such a switch
  retools like any other.
- **Pollution has no lag.** It is a state modifier, not a building one.
- **Other `_mult`s on the same good combine with the lag additively**, exactly as the design notes
  for recipes: a +25% steel bonus during Blister → Bessemer gives 90 × (1 + 0.25 − 0.278 × (1 − p)).
- **The government share is read in 5% steps** through `country_ownership_fraction`, a ladder of
  constant comparisons, so no trigger needs a variable on its right-hand side.
- **The retool building is gated, not unbuildable.** `potential` is true only while script holds a
  state variable for that retool, and `ai_value = 0`, because no vanilla script ever queues a
  `buildable = no` building and a queued construction may need its building to stay possible.

## Assumptions about game script that are not verified in game

Everything below is read from the installed game's script and the generated docs in
`Documents\Paradox Interactive\Victoria 3\docs\`. None of it
has run yet; the run sheet says how each shows up when it fails.

1. `add_modifier` in building scope with per-good `goods_input_<g>_mult` / `goods_output_<g>_mult`
   moves that building's numbers. Documented for building scope; Ironroad's research found the engine
   reads building-scope goods modifiers, but never this exact pair.
2. `start_building_construction` and `start_privately_funded_building_construction` accept a modded
   building gated by a `potential` trigger, and calling one N × L times queues N × L levels.
3. `on_production_method_changed` and `on_building_built` fire with the building as root.
4. `level_after_queued_constructions` and `country_ownership_fraction` behave as documented.
5. `[THIS.GetBuilding.GetState...]` and `[THIS.Var('x').GetValue]` resolve inside `debug_log` text in
   building scope.
