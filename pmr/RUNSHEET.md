# PMR run sheet: the script profiler, no script-off years, one method per share, new buildings on the best recipe, script-off years in observer games, far fewer hidden methods, ports that hold still, ranch wool blended like hardwood, an observer game logged, the board counted the day after start with votes that trend, no step down while a building makes money, board votes by profit and the private owners' share, a state Buildings tab without gaps, explosives within spare supply, board votes by wealth, bylaws as laws, a railway for Rail Transport, explosives off while short, seat votes by clout and popularity, Engineering named by trade, profit figures held to the books, bylaws that open from the law in force, no Rail Transport without a railway, ideologies on the board, law-style bylaws and three speedups, bylaws on the board, grants on Engineering, two trees and a board, one click, three industries, a subsidiary on its parent's Assets tab, test companies as buyers, cards that shrink to what they show, a subsidiary under its parent's Regional HQs, a 25% bar to switch, only nearby unlocked options priced, Productivity and Output explained, the Industry Charter node by decision, two test companies founded by script, a second Industry Rights, every input in the charter list, a grant decision, the investment chance in sections, retool sites out of the build menus, profit figures from the buildings' own books, built special methods, a cleaner Policies tab, faster months, the Policies tab, a 6-month bar before a new default, automation on 38 types, explosives by price, Hallmark Goods for every company, the policy window pops out, research grants paid every week, who buys each type, company marks and a nested Policy tooltip on the cards, Production Methods cards sorted by AI weight, Production Methods cards in one set of columns, AI weight as a share of all weights, base prices at game start, research grants paid from the investment pool, Production Methods cards fixed, less text on the wheel, Production Methods cards sorted and filtered like the Buildings list, a quieter Company Culture wheel, the Investments tab in the side Buildings panel, AI weight by vanilla's own scoring at your average, the Company Culture full-screen fixed, Company Culture full-screen with lock reasons and charter buttons on its nodes, the Company Culture wheel with research grants and company special methods, recipe and automation chosen as pairs, the investment cards and AI weights on Private Owners' Methods, profit figures at market prices, Private Owners' Methods as a Buildings panel tab with recipe + automation pairs, the profit pick logs itself, private owners' methods on the Private tab, each building shows its most profitable recipe, new builds and retooling follow it, a green automation bar, who owns each level of a building, Company Works share probe, automation pays at 1836 wages, PMR translated into every game language, the automation tech gate, Company Culture tab on every company (test mod), one retool site per building with a paid crew so investors can add levels, hidden from the Buildings tab (test mod), your investors retool abroad, companies list their additional industries' retooling, the target follows your best recipe, the Foreign or Domestic bar as a multiplier with a 3-month lock, Arts Academies, power plants and Urban Centers, your government retooling abroad, retooling abroad, priorities on a timer and locked by law, policy costs and Agrarianism policies, ports and railways retool, administration, universities and trade centres always on their best method, Laissez-faire policies and Recent Investments as tree maps, the Private tab (fifth round) and your recipes abroad in the Owners list, retooling what you own abroad, the Private tab (fourth round), faster monthly ticks and a timing test, the Private construction tab (third round), trade-offs pre-loaded from your 1838 save, vanilla group names on the second bar, faster trade-offs, plantation treatment by acceptance, trade-offs by local prices

Every line PMR writes goes to `Documents\Paradox Interactive\Victoria 3\logs\debug.log` and starts
with `PMR;rec=`. Filter with:

```
findstr /C:"PMR;rec=" "%USERPROFILE%\Documents\Paradox Interactive\Victoria 3\logs\debug.log"
```

Also check `logs\error.log` for any line containing `pmr_` before reading anything else: a script
error there means the mechanism below never ran, and a missing log line is then not a result.

## Latest: the script profiler (q56, test mod; start a new game)

From the build thread, after your 01:12Z question. The game's own script profiler adds up the time of every
script block. It collects from launch when the game starts with `-script_profiling`, and q56 writes its totals
to `logs\script_profiling.txt` every minute by itself.

- The test build runs the profiler's write command once a minute from the HUD. Nothing is typed.
- The monthly state pulse runs in steps, one per building type, so each gets its own line in the file.
- The profiler slows the game, so this run's months can't be compared with q54's or q55's.

1. In Steam, Victoria 3, Properties, Launch Options: add `-script_profiling` to what is there
   (for example `-debug_mode -script_profiling`).
2. Start a new observer game in PMR Test at speed 5. Let it run to about January 1840 without opening anything.
3. Close the game and tell the build thread. Take `-script_profiling` out of the launch options afterwards.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| R1 | Step 2 | `logs\script_profiling.txt` appears within two minutes and is rewritten every minute | No file: the HUD's write command never ran, so the next build gets a button instead. A file with only its `# type, location ...` header: the game didn't see `-script_profiling` |
| R2 | Step 2 | Lines naming `common/on_actions/pmr_on_actions.txt`, one for each `pmr_prof_` step | Rows but none of PMR's: this profiler doesn't time on_actions, so the next step is the in-game profiler window or script-off years by part. It does not mean PMR's script is cheap |
| R3 | Step 3 | No new `pmr_` line in error.log, and no "hash collision" naming a `pm_pmr_` key | A new line: read it before anything else |

## Earlier: no script-off years (q55, test mod; a q54 game carries on)

From the build thread, after your 01:06Z message. q54 measured 1838 7.8, 1840 8.1 s per game month with PMR's
script and 1839 6.2 without it: about 20% under q53 and 5% under q51.

- Observer games no longer switch PMR's script off in odd years. A pause an older build left in a save is lifted
  at the next month.
- One method per share is now what every build makes. Nothing else changed.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| R1 | Any observer game | No `PMR;rec=TEST;arm=TICKS_PAUSED` line in any year | No `OBS` line at all: the game wasn't an observer game, so the check says nothing. A `TICKS_PAUSED` line: the q54 files loaded |
| R2 | Close the game | No new `pmr_` line in error.log, and no "hash collision" naming a `pm_pmr_` key | A new line: read it before anything else |

## Earlier: one method per share (q54, test mod; start a new game)

From the build thread, after the q53 run (00:29Z-00:37Z): 1838 9.8 s per game month with PMR's script, 1839 7.9
without it, 1840 10.0 with it. q53 with its script off ran about as fast as q51 with it on.

- Each building's share of a recipe or option is one method again, 0-100% in 1% steps, as in q51, but it locks
  itself like q52's digits, so there is no lock group. 28,675 methods (q51 56,830, q53 6,598), and half the share
  groups and running share methods per building of q51 or q53.
- Built with `--single-shares`. Everything else is q53, including the script-off odd years in observer games.

1. Start a new observer game in PMR Test at speed 5. Let it run to January 1842 without opening anything.
2. Close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| R1 | Step 1 | Seconds per game month below q53's in the same years: 1837 9.5, 1838 9.8, 1840 10.0 (script on); 1839 7.9 (script off) | The same as q53: two methods per share weren't what cost the time; the methods side is then the buildings and modifiers themselves |
| R2 | Step 1 | `PMR;rec=TEST;arm=TICKS_PAUSED` early in January 1839 and 1841, `TICKS_RESUMED` in January 1840 | No TEST line: the game wasn't an observer game, and the years can't be told apart |
| R3 | Step 1 | `OBS` GDP for the 8 largest economies close to q53's in 1838 | GDP well off q53's: a share isn't adding up to what it stands for |
| R4 | Step 2 | No new `pmr_` line in error.log, and no "hash collision" naming a `pm_pmr_` key | A new line: read it before anything else |

## Earlier: new buildings on the best recipe, script-off years in observer games (q53, test mod; start a new game)

From the build thread, after your 00:08Z-00:20Z messages.

- A building's first level in a state is built on the state's best recipe again. q52's "unreadable books keep the
  default" held a brand-new building, which has no staff yet, on the recipe the game built it with, and a month later
  every level went to retooling (the West Bengal and Burgundy mines).
- PMR's monthly script doesn't show in the Tick Task List: it runs in the daily pulse, outside the tick tasks.
  MonthlyPulseJournalEntries is vanilla's journal entries only. So an observer game now turns PMR's script off in
  1839, 1841, 1843 and 1845 (and every odd year after), and the seconds per month say what the script costs.
- The digit check q52 logged each month (SELFLOCK) is gone, with the work it added to every building.

1. Start a new observer game in PMR Test at speed 5. Let it run to January 1847 without opening anything: no panels,
   no Tick Task List. Panels and that list slow the game and spoil the timing.
2. After 1847, open a few buildings built since 1840 ("No historical data") in different countries.
3. Close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| R1 | Step 1 | `PMR;rec=TEST;arm=TICKS_PAUSED;...;by=observer` in early January 1839, 1841, 1843 and 1845, and `TICKS_RESUMED` in early January 1840, 1842, 1844 and 1846. The OBS lines keep coming every month in both | No TEST line: the game wasn't an observer game or the hook never ran, and the years can't be told apart. No OBS lines in the odd years: the monthly lines are still behind the pause |
| R2 | Step 1 | A figure, not a pass: seconds per game month in the odd years against the even years around them. The gap is what PMR's monthly script costs | Odd and even years the same: the script costs little, and the gap to vanilla is the methods, modifiers and buildings themselves |
| R3 | Step 1 | Even years at or below q51's 8.3 (1838), 8.4 (1840), 9.1 (1842), 8.9 (1844) | Slower than q51 in even years too: q52's tens and units digits cost more per building than they saved; the next build looks at the extra methods each building runs |
| R4 | Step 2 | Each building shows just its recipe's name, not "0% on ..." with all its levels to retool | "0% on ..." on a new building with nothing retooled: new buildings still miss their state's best recipe |
| R5 | Step 3 | No new `pmr_` line in error.log, and no "hash collision" naming a `pm_pmr_` key | A new line: read it before anything else |

## Earlier: far fewer hidden methods, ports that hold still (q52, test mod; start a new game)

From the build thread, after your 22:47Z, 22:50Z and 22:56Z messages.

- The game's weekly RecomputeStandardProductionMethods task works out, for every country, which method most of its
  buildings run. It does this over every production method in the game, for all of about 730 country slots. PMR had
  56,830 methods against vanilla's 436.
- Each building's hidden share of a recipe now runs as two methods, tens and units: 21 methods instead of 203 for
  each recipe. Each digit locks itself, so the 102-method lock groups are gone. The game now has 6,598 methods
  (−88%). Shares still move in 1% steps.
- Ports and other buildings whose books can't be read keep their default method. Any other switch needs a gain of
  £20 a week per level as well as 25%.
- A hidden name that clashed with vanilla's `liberal_trailblazer` text is gone.

1. Start a new observer game in PMR Test at speed 5, as for q51. Let it run to January 1841.
2. Around January 1838 and again near January 1841, pause, open Slow Ticks and screenshot the Tick Task List.
3. Close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| R1 | Step 1 | `PMR;rec=SELFLOCK` lines each month for the largest economy's buildings, every one with `moved=0` and `other_can=0`; no `TRIP`, `L0_TRIP` or `AUTO_TRIP` line; the game never freezes | No SELFLOCK line at all: the old build loaded or the game wasn't an observer game, so the run says nothing. `moved` above 0, `other_can=1`, a TRIP line or a freeze: the game doesn't hold a running share on its own; the next build gives each digit its own lock (12,946 methods) |
| R2 | Step 2 | RecomputeStandardProductionMethods far below the 37 it showed in 1868 on q51, no longer near the top of the list | The same size with R1 passing: the method count is not what this task costs, so the groups per building are next |
| R3 | Step 1 | Real seconds per game month from 1836 to 1840 below q51's 8.0 (1836) and 8.4 (1840), read from the OBS lines' times | The same speed with R2 passing: at this game size the task wasn't what limited the month; the later years will tell |
| R4 | Step 1 | `OBS` GDP for the 8 largest economies close to q51's in the same years (Qing 96.8, Britain 32.4, France 25.2 in 1840) | GDP well below q51's: the tens and units no longer add up to the share they stand for |
| R5 | Step 1 | No port goes down and back up within a year in the largest economy's `SWITCH_START` lines | Ports still flip: their books read as known; the freeze rule doesn't reach them |
| R6 | Step 3 | No new `pmr_` line in error.log, and no "hash collision" naming a `pm_pmr_` key | A new line: read it before anything else |

## Earlier: ranch wool blended like hardwood, an observer game logged, the board counted the day after start, votes that trend, share bar tooltips (q51, test mod; start a new game)

From the build thread, after your 20:34Z, 20:35Z, 20:39Z and 21:12Z messages.

- An observer game (no player) now logs: each month an `OBS` line for each of the 8 largest economies (GDP, average
  standard of living, how many of its building types are in a state, how many show a loss on their books, how many
  switching bars fill up or down, how many defaults a loss lowered), an `OBSPM` line with the share of levels on Sheep
  Farms and Intensive Grazing, on nitroglycerin and dynamite (the five mines together), and on the coffee, tobacco and
  sugar processing methods, and the largest economy's `SWITCH_START`, `DEFAULT` and `FLOOR` lines. Nothing changes in
  a game with a player.
- From the bug review: a building whose books can't be read because it is subsidised or nearly empty no longer counts
  as making money; a red bar stops once the books show no loss; a default lowered at once by the first pick at market
  prices is marked so the floor leaves it to finish.
- Livestock ranches' wool (Simple Ranch, Sheep Farms, Intensive Grazing) is blended by local prices like hardwood,
  with its own bar under the ranch card: Sheep Farms and Intensive Grazing take grain for more wool and fertilizer, on
  top of Simple Ranch's own wool. The mines' explosives (nitroglycerin, dynamite) already blend this way since q49.
- Board: every company is counted again the day after game start from a fresh read of its country's ownership, so the
  shareholders hold their votes from day 2. Votes then move a quarter of the way to their target at each monthly count
  instead of jumping (a player's companies count monthly; an AI company's yearly, or monthly while a bylaw change is
  under way). Hovering a seat's bar shows its votes, all the board's votes and its target.

1. Start a new observer game in PMR Test. Run it at speed for ten years or more. In the first days, Ctrl+click a
   country with companies, open one company's Company Culture window and hover its bars.
2. Close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| V1 | Step 1 | From the first month, `PMR;rec=OBS` lines for 8 countries each month | No OBS line: the game wasn't seen as an observer game (`pmr_obs` is set the day after start only when no country is a player); the other rows then say nothing about this game |
| V2 | Step 1 | Over ten years most of the 8 countries' `gdp` rises, `loss` stays well under `types`, and `down` stays near 0 | `gdp` falling in most of them while `down` or `lowered` climbs: the economies still retool themselves into losses (the Steam observer report); `loss` near `types` with `down` 0: buildings lose money for another reason (prices) |
| V3 | Step 1 | The largest economy's `SWITCH_START` lines are mostly `dir=1`; any `FLOOR` line ends a step down (to= above from=) | Many `dir=-1` starts: lower methods are still priced for buildings that make money |
| V4 | Step 1 | A `PMR;rec=BL_PRIVATE` line for the largest economy the day after start (date 2 January) with `levels` above 0 and `share` above 0 | `levels=0`: the country's buildings weren't found on that day either; `share=0` with levels: the owners read as government or company only |
| V5 | Step 1 | The window opened in the first days shows the shareholders with votes and a share above 0% | Shareholders 0: the day-after count didn't run (no `pmr_cc.2`) or read 0 (see V4) |
| V6 | Step 1 | Hovering any seat's bar shows "n of m votes" and "Target t" | No tooltip: the bar's wrapper doesn't take the hover |
| V7 | Step 1 | A ranch card shows a wool bar; where grain is cheap and fabric dear, Sheep Farms' share grows a few points a month once Intensive Agriculture is researched | No bar: the ranch's trade-off groups weren't added; the bar stuck at Simple Ranch with the tech known: the options read as unavailable (`pmr_xav`) |
| V8 | Step 1 | `PMR;rec=OBSPM` lines: `ranch_sheep` above 0 in countries with Intensive Agriculture, `mines_nitro` / `mines_dynamite` above 0 once their technologies are in, and the plantations' `coffee_mech`, `tobacco_*`, `sugar_*` above 0 somewhere by the 1850s | `ranch_sheep` and `ranch_grazing` 0 everywhere for ten years: the wool blend never moves (check `pmr_xav`); `mines_*` 0 with the techs known: explosives never pay or the spare-supply cap holds them at 0; the plantation figures 0: the AI doesn't switch those vanilla methods either (they move to retooling next batch) |
| V9 | Step 2 | No new `pmr_` line in error.log | A new line: read it before anything else |

In a game you play (any later save), `PMR;rec=BL_COUNT` lines each month show each seat as `votes>target`, the votes
closing a quarter of the gap each month.

## Earlier: no step down while a building makes money, board votes by profit and the private owners' share (q50, test mod)

From the build thread, after your 19:23Z and 19:30Z messages.

- A building that isn't losing money (its books at £0 or more a level, or no reading yet) is never moved to a lower
  method. If its default sits below what its levels run (New Jersey's shipyards: default Basic, running Complex, from a
  pick at game start), the default goes up to what runs at once, so the retooling down stops. Lower methods are only
  looked at while the books show a loss; a default a loss lowered is left to finish its retooling.
- Board: the chairman has 3 votes and one more for each step its company's week's profit reaches (£1K, 2K, 5K, 10K,
  20K, 50K, 100K); a subsidiary's chairman 1 and the same steps. The shareholders have 10 × the share of the economy
  the Private tab shows for Manor Houses and Financial Districts. The council keeps 20 × the Trade Unions' clout.
  Popularity multiplies each. Every seat shows a bar and a percentage: its share of all the board's votes.

1. Load your latest PMR Test save. Play two months.
2. Open New Jersey's shipyards, the Policies tab's shipyard card, and an American company's Company Culture window.
3. Close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| U1 | Step 1 | Within the first month a `PMR;rec=FLOOR` line for New Jersey's shipyards (from=1;to=2), then its `PMR;rec=PROFIT` lines read `to=2;...;floor=2;ok=1` and the retooling to Basic Shipbuilding ends | No FLOOR line and PROFIT still `to=1` with `floor=2;ok=1`: the raise was skipped (a `pmr_dn` flag, or Complex can't run there). No PROFIT line with `floor=` at all: the recompute after loading never ran |
| U2 | Steps 1-2 | Every `PMR;rec=SWITCH_START` with `dir=-1` belongs to a building whose PROFIT line reads `ok=0` (books below £0) | A `dir=-1` with `ok=1`: lower methods are still priced for a profitable building |
| U3 | Step 2 | Hovering the shareholders' votes shows Manor Houses and Financial Districts at the Private tab's By owner figure (64% now) and Popularity; votes = 10 × that × popularity, rounded | 0%: the country's share never ran (`pmr_bl_private`); a figure far from the Private tab's: the two count different buildings |
| U4 | Step 2 | Hovering the chairman's votes shows Chairman 3, Profit £…K +n and Popularity; votes = (3 + n) × popularity, rounded | Profit £0 +0 on a company with levels: its industries weren't found (`pmr_cc_k_id`) |
| U5 | Step 2 | Each seat has a bar and a percentage under its name, and the percentages add up to 100% | Empty bars and 0% everywhere: the board hasn't been counted since loading (it counts monthly); still empty after a month: `pmr_bl_tot` is 0 |
| U6 | Step 3 | No new `pmr_` line in error.log | A new line: read it before anything else |

## Earlier: a state Buildings tab without gaps, explosives within spare supply, board votes by wealth, bylaws as laws (q49, test mod)

From the build thread, after your 18:24Z to 18:45Z messages.

- A state with a retool site draws its urban buildings from a list PMR keeps, in the tab's own order (level, then
  group and name), with the "+" tile right after the last one. A state without one keeps vanilla's grid. The list
  view closes the row a hidden site left.
- Explosives work like hardwood: each month a mine moves toward its best option, but a move onto an explosives method
  is held to the market's spare explosives (production and imports less use and exports), shared out mine by mine.
  Nothing is shed when explosives run short; the mines simply stop gaining.
- Board: each seat's votes come from the wealth it makes, as a share of 10. The chairman's is the company's own levels,
  the shareholders' the other private levels of the company's industries, each subsidiary's its own levels, all
  priced at their industries' profit per level. Popularity multiplies it (×0.0 at −100 to ×2.0 at +100). Each
  chairman gets +2. The Workers Council gets 20 × the Trade Unions' clout, times its leader's popularity.
- The Expansion root costs 1 culture point.
- Bylaws are law rows like the Power Structure: icon, group, the bylaw in force; a click opens the others below with
  their effects and support. A change under way gets its own row with its bar and a cancel button.
- Vanilla's prestige-goods journal entries no longer start, and one already open closes: Hallmark Goods is the only way
  to a prestige good.
- Fixes: a subsidiary founding re-checks the technology and the state before it builds (GBR's oil rig without
  Pumpjacks); a building gone mid-retool no longer leaves its retooling open; a building whose books can't be read
  is priced from its recipes instead of a frozen reading; an option tooltip below level 1 no longer logs an error.

1. Load your latest PMR Test save. Play two months.
2. Open a state with a retool site (West Bengal) in grid and list view, an iron mine's Explosives bar, the Hudson's Bay
   Company's Company Culture window, and the Journal.
3. Close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| T1 | Step 2 | The state with a retool site shows no empty cell in grid or list view, its buildings in the usual order, and the "+" tile right after the last one | An empty cell after the first month: the state has no list of its own (`pmr_urb_on` unset, the refresh never ran). Blank tiles: the list's entries didn't turn back into buildings. Only a "+" tile: the type filter matched none of the state's buildings |
| T2 | Steps 1-2 | Iron mine `PMR;rec=OPT` lines: where explosives are short (red), no mine's explosives share rises; where they are in surplus, shares rise a little each month | No share rises anywhere in two months with explosives in surplus: the spare supply reads 0 (the market read fails). Shares still jump by 20 at once across a market: the cap isn't applied |
| T3 | Step 2 | Hovering a seat's votes shows Wealth £…K (…%) and Popularity ×…, plus Chairman +2 on the chairman; the council shows the Trade Unions' clout | Wealth £0 and 50% on both chairman and shareholders: the company's industries weren't found (`pmr_cc_k_id` unset) |
| T4 | Step 2 | The Expansion root shows a cost of 1 and buying it spends a point | Bought with no point spent: the old free root loaded |
| T5 | Step 2 | Each bylaw group is a law row; a click opens the others under it with effects and support | Full-width boxes: the old layout loaded |
| T6 | Steps 1-2 | Hudson's Bay's "Select Fish" journal entry is gone, and no prestige-goods entry appears | Still open after a month: a running entry ignores `invalid`, and it needs removing by script |
| T7 | Step 3 | No `create_building` error from `pmr_cc_effects.txt` and no `pmr_xav` fetch error in error.log; no other new `pmr_` line | A new line: read it before anything else. "Trying to reshape data model with negative offset -1" is vanilla's workforce panel on a building with no workers yet, not PMR's |

## Earlier: a railway for Rail Transport, explosives off while short, seat votes by clout and popularity, Engineering named by trade (q48, test mod)

From the build thread, after your 17:40Z to 18:10Z messages.

- Rail Transport counts only a real railway in the state; a port's transportation no longer does (West Bengal's opium).
- A mine's explosives share falls 20 points a month while its market or your states are short of explosives.
- The Policies tab keeps its filters under the Investment chance sort, and a type you hold only in another country's
  state (opium in the East India Company's) gets its card.
- Engineering costs 1 point and runs a research grant (£250 a level a week for 52 weeks) like its three tiers.
- Engineering's second tier is named and drawn by the company's trade: Crop Science (plantations, farms), Deep
  Prospecting (mines, oil), Scientific Forestry, Fleet Outfitting, Systems Engineering (railways, power, trade), Fine
  Craftsmanship (arts), Precision Manufacturing (industry).
- Vertical Integration of a mining, logging, oil, plantation or rubber company lists railways.
- Board: the Workers Council seat is the Trade Unions' leader. Each seat's votes come from its base or its interest
  group's clout (shareholders 1 to 4 by the Industrialists' clout, as the council by the Trade Unions'), plus its
  character's popularity (+1 at 25, +2 at 75, as much off below −25 and −75), at least 1. Hover a seat's votes for
  where they come from, its ideology for its views of the bylaws, a bylaw for each seat's vote on it.
- Bylaw boxes fill the board's width. The middle bylaws (Market Wages, Standard Shifts, Balanced) have no effects;
  click the box to see the others with theirs.
- Cheaper months and Buildings panels: subsidiaries re-apply their traits only on a change, retool bookkeeping runs
  only where a site can stand, the Trade Unions modifier is touched only on a change, construction hooks look in the
  site's own group, and "is this a PMR building" is one lookup in the panels.

1. Load your latest PMR Test save. Play two months.
2. Open West Bengal's opium plantation, an iron mine, the side Buildings panel's Policies tab sorted by Investment
   chance, and the East India Company's Company Culture window (and a manufacturing company's).
3. Close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| T1 | Step 1 | West Bengal's opium `PMR;rec=TICK` lines read `rail=0`, and its retooling target is not a Rail Transport recipe | `rail=1` with no railway: the railway test isn't read. `rail=0` and still retooling onto Rail Transport: the pick ignores `pmr_rail` |
| T2 | Step 2 | An iron mine whose market is short of explosives shows "(shortage)" after Nitroglycerin in its Explosives tooltip, and the share is 20 points lower a month later | No "(shortage)" while explosives show red: the shortage test reads false here, and the rule needs another trigger. "(shortage)" but the share holds: the step ignores the flag |
| T3 | Step 2 | The Policies tab under Investment chance shows Search and Filters, and has an Opium Plantations card | No filters: the AI sort still hides them. No opium card: the abroad count didn't run (`pmr_mv_lv_opium_plantation` 0) |
| T4 | Step 2 | Engineering shows a cost of 1 and a grant row; once bought, `PMR;rec=CC_GRANT_WEEK` lines with `tier=41` run weekly | Engineering bought at once: the grant isn't wired for it. No CC_GRANT_WEEK lines: the weekly clock didn't start |
| T5 | Step 2 | The East India Company's second Engineering tier reads Crop Science with a fertiliser icon; a manufacturing company's reads Precision Manufacturing | A blank name: the window can't read the custom text. Precision Manufacturing for both: `pmr_cc_k_sec` wasn't set (a save from before q48 needs one month) |
| T6 | Step 2 | A mining or plantation company's Vertical Integration lists railways | No railways: railways aren't ownable by that company in this build's plan |
| T7 | Step 2 | The Workers Council seat shows the Trade Unions' leader's portrait and name; hovering a seat's ideology lists its views; hovering its votes shows the base and popularity; hovering a bylaw lists each seat's vote | A silhouette or IG picture with a leader present: the leader wasn't stored (`pmr_bl_wcl`). Empty views: the views text isn't read |
| T8 | Step 2 | Each bylaw group is one full-width box; a click opens the others across the row; a change under way sits beside the box in force | Narrow boxes at the left: the old layout loaded |
| T9 | Step 3 | No new `pmr_` line in error.log | A new line: read it before anything else |

## Earlier: profit figures held to the books, bylaws that open from the law in force (q47, test mod; your latest PMR Test save carries on)

From the build thread, after your 17:23Z and 17:24Z messages.

- Each building's figure for the method it runs now equals its own books (weekly balance per level at full staffing),
  and its other options move by the same amount. Pommern's rye farm had read −£62 against a +£55 balance: PMR's sum
  left out its potatoes (liquor) and the jobs they bring. A building in profit no longer prices methods below its own.
- The Shareholders portrait is drawn as vanilla draws a stored character.
- Each bylaw group shows only the bylaw in force, and a change under way beside it. A click on the bylaw in force
  opens the others, each with its support (approve or disapprove icon and the net votes); a click on one starts the
  change and closes the group.
- Bylaw effects read green when they help the company and red when they cost it, as vanilla colours the same
  modifiers: more throughput or job attractiveness green, higher working conditions, wages or dividends red.

1. Load your latest PMR Test save. Play to the next month.
2. Open a company's Company Culture window and use the bylaws.
3. Open the side Buildings panel's Policies tab. Close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| S1 | Step 1 | Every `PMR;rec=PROFIT` line has `off=`; for Pommern's rye farm the `rm` figure at the `ref` position is about its weekly balance per level (+£55 at the time of your screenshot) and its `pick` is its own method | No `off=` field: the new version didn't load. `off=0` on every line: the books weren't read (`pmr_bpl_` never set), and the figures are the old ones |
| S2 | Step 3 | Pommern's rye farm card shows its own method in profit and no red bar; cards of other buildings in profit show no red bar | A red bar on a building in profit: its figures still come from the recipe sum, not the books |
| S3 | Step 2 | The Shareholders seat shows the Industrialists' leader's portrait (not a silhouette) | A silhouette: the window can't draw the stored character, and the seat needs another way to read it |
| S4 | Step 2 | Each group shows one box (two while a change runs); a click opens the others in a row under it, each with an icon and a signed number; a click on one starts the change and the group closes; the X still cancels | All boxes shown at once: the open/closed switch isn't read. A click that does nothing: the group's switch doesn't toggle |
| S5 | Step 2 | Effects read green or red: more throughput, job attractiveness or Focus (above ×1) green; higher working conditions, wages or dividends red, lower ones green | All effects one colour: the colour codes weren't read |

## Earlier: no Rail Transport without a railway, ideologies on the board, law-style bylaws and three speedups (q46, test mod; your latest PMR Test save carries on)

From the build thread, after your 16:32Z to 16:53Z messages.

- The Shareholders seat is your country's Industrialists' leader. Every seat with a character shows its ideology, and
  votes by that ideology's view of each bylaw (`/mnt/project-files/pmr/company-rework/IDEOLOGY-VIEWS.md`, guesses
  until you confirm them); the Workers Council keeps the Trade Unions' view.
- Bylaws are boxes like vanilla's laws: icon and name, effects under them, the bar of a change at the box's foot. The
  bylaw in force is lit. The board panel scrolls when it is taller than the window.
- A change's bar gains 20 a month plus 2 for each net vote of support (2 votes against: +16). Its tooltip shows
  the bar, the support and the monthly gain; each other box's tooltip shows its support.
- Retool sites are marked once when the game's screen is made, and the state Buildings tab, the Build Urban menu and the
  Buildings panel's Available grids hide them by that mark instead of a 180-way test per item.
- The subsidiary company-slot modifier is only touched when your number of subsidiaries changes.
- AI countries' monthly profit pass keeps only the number their investment weights read, and every country skips the
  building types it has no levels of. Your own country's figures are unchanged.
- A method using transportation (Rail Transport and the like) can't be a building's default in a state that makes no
  transportation, even if the building already runs it; such a default gives way at once. Every building re-prices its
  options on the first month after loading.

1. Load your latest PMR Test save. Open a company's Company Culture window.
2. Open a state's Buildings tab (urban grid and list view), its Build Urban menu, and the side Buildings panel's
   Available grids.
3. Open the side Buildings panel's Policies tab. Play to the next month, close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| S1 | Step 1 | Pay, Hours and Safety and Focus as rows of boxes (three a row), each with its law icon, name and effects; a change under way has its green bar inside its box and its tooltip's Support is the sum of each seat's votes × its vote icon, and its monthly gain 20 + 2 × that | Boxes without effects: the effect text didn't load. No scrolling with several subsidiaries: the scroll area didn't take (the panel is cut off at the bottom) |
| S2 | Step 1 | The Shareholders seat shows your Industrialists' leader's portrait and name; the executive, each subsidiary's executive and the leader each show an ideology icon with its name on hover; a change's vote icons match the table for those ideologies | The Industrialists icon in place of a portrait: no leader was found (`error.log` near `pmr_bl_count`). No ideology icons: the window can't read a character's ideology |
| S3 | Step 2 | No "Retooling …" building anywhere in those lists, from the first opening on | Retool sites listed: the screen's marks weren't set (`error.log` near `pmr_site_flags`); the lists are then showing every site |
| S4 | Step 3 | `PMR;rec=PF` lines for your country's building types as before; the Policies cards' Productivity and Output figures unchanged | No `PF` lines: the building-levels check failed, and every country's profit term is zero (AI weights lose it) |
| S5 | A month | Your Companies panel's company limit unchanged; no `pmr_sb` lines in `error.log` | The limit dropped by your subsidiaries: the slot modifier was removed and not re-added |
| S6 | A month | In a state of yours with no railway, every mine, plantation, ranch, logging camp, fishing wharf, whaling station and oil rig has a `PROFIT` line whose pick is a method without Rail Transport, and its `TICK` lines read `rail=0`; states with a railway read `rail=1` | `rail=1` in a state with no railway, or `rail=0` everywhere: the state's transportation output was misread, and the rule then bites nowhere or everywhere. A rail pick where `rail=0`: the gate didn't reach the pick |

## Earlier: bylaws on the board, grants on Engineering (q45, test mod; your latest PMR Test save carries on)

From the build thread, after your 15:37Z to 15:54Z messages. Phase 2 of the company rework
(`/mnt/project-files/pmr/company-rework/SPEC.md` sections 5 to 7).

- The board is a fixed panel right of the trees: the executive (3 votes), each subsidiary's executive (1), the
  Shareholders (2, the Industrialists' view) and, while Trade Unions have 5% clout or more, the Workers Council (2 to
  4). Under it the Bylaws: Pay (Tight Payroll, Market Wages, Living Wage, Profit Sharing), Hours and Safety (Long
  Shifts, Standard Shifts, Safety Code), Focus (Original Company, Balanced, Subsidiaries). The bylaw in force is lit.
- A click on another bylaw starts a change: its green bar gains 20 + 10 x support a month (5 to 50) and it passes at
  100; support 6 against or worse can't start. One change at a time; the X cancels it. Pay and Hours bylaws are traits
  on the executive and on each subsidiary's executive. A company of 20 levels or more with Tight Payroll or Long
  Shifts gives your country "Harsh Company Bylaws": Trade Unions approval −1 and strength +5% each, up to 5.
- Engineering's three tiers are research grants: the click (points as before) starts 52 weekly payments from the
  investment pool, £500 / £1,000 / £1,500 per employed level; the tier's bonus comes when its green bar is full, and
  the next tier stays locked until then.
- A subsidiary's payment is one level's construction cost over 52 weeks (a fifth of q44's), on the budget line
  "Expansion"; grants have their own line, "Research grants".
- Subsidiaries carry no parent traits any more, only "Subsidiary": half the parent's tree throughput less half your
  country's Company Throughput Bonus. Construction stays full.
- Culture costs x1.25 (level 0: 1,000), about 10 years for a tree. Diversification always lists industries (power
  plants: the industries using electricity; art academies: other luxuries). The Companies panel no longer tests retool
  sites one by one.

1. Load your latest PMR Test save. Open a company of yours with a subsidiary (Krupp if Prussia) and its Company Culture
   window.
2. Click "Living Wage". Play two months.
3. Click "Long Shifts" in Hours and Safety: it can't start while Pay changes. Click the X on Pay, then "Long Shifts".
   Play until it passes (the bar's tooltip shows its monthly gain).
4. Open a company that hasn't bought Process Engineering. Click Engineering if needed, then Process Engineering (take
   "PMR test: 12 Culture points…" and "PMR test: £1,000,000…" if short). Play two weeks, then take "PMR test: finish
   your research grants" and play a week.
5. Open the Companies panel and its company type list. Open Hudson's Bay Company (or any logging company) and its
   window. Play to the next month, close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| Q1 | Step 1 | The trees sit at the top, nothing cut off; the board panel lists the executive (3), the subsidiary's executive (1), Shareholders (2), the Workers Council where Trade Unions have 5% clout; then Pay, Hours and Safety and Focus, Market Wages, Standard Shifts and Balanced lit | No Bylaws: the window failed (`error.log` names the GUI line). Every button greyed: the company isn't yours or the click check failed (`pmr_bl_pick_sgui` in `error.log`) |
| Q2 | Step 2 | `BL_START` with `group=1;bylaw=3`; a green bar under Living Wage; Shareholders against, the council for, the executive by its interest group (Industrialists or Landowners against); the bar's tooltip shows the monthly gain | No `BL_START`: the click didn't run. A bar that doesn't move: the monthly count didn't run (no `pmr_bl` work in `pmr_cc_tick`) |
| Q3 | Step 3 | `BL_CANCEL`, then `BL_START` with `group=2;bylaw=1`, then `BL_PASS` with `g2=1`; the executive and the subsidiary's executive carry "Long Shifts" (throughput +5%, dangerous conditions +30%); the next month your country has "Harsh Company Bylaws" (if the company employs 20 levels) | `BL_PASS` with no trait: the traits weren't re-applied. No country modifier with 20+ levels: the monthly country count didn't run |
| Q4 | Step 4 | Before: "£… × 52" at the card's foot; after the click a green bar and `CC_GRANT_WEEK` lines; Precision Manufacturing stays locked; the budget's investment pool shows "Research grants"; after the decision `CC_GRANT_DONE` with `en=1` and the throughput trait on the executive | "Investment pool needs …" in red: the pool can't cover a week (take the £1,000,000 decision). No `CC_GRANT_WEEK`: the weekly event didn't pick the company up |
| Q5 | Step 1, a month on | `CC_SUB` with `thr=` and `country=` (your Company Throughput Bonus in %); the subsidiary's executive carries only "Subsidiary" (and Long Shifts after Q3), throughput `thr`%, no input goods cut | `country=0` with a bonus in the Companies panel: the bonus wasn't read, and the trait only adds half the tree. No "Subsidiary" trait with `thr` not 0: the trait didn't apply |
| Q6 | Step 5 | The Companies panel's type list shows no "Retooling …" types and opens without the stall | Retool types listed: the panel's flags weren't set (its opening state) |
| Q7 | Step 5 | Hudson's Bay Company's Diversification card shows industry icons (Oil Rig, Sulfur Mine, Gold Mine, Iron Mine) | An empty card: the build is older than q45 |
| Q8 | Steps 1 to 5 | The Culture bar fills slower: `CC_POINT` lines with `cost` 1.25 times q44's for the same level (`level=1`: 1310, was 1048); a subsidiary's payment on the "Expansion" line is about a fifth of q44's | `cost=1048` at `level=1`: the costs weren't reset (CAL 8) |

## Earlier: two trees and a board (q44, test mod; your Prussia PMR Test save carries on)

From the build thread, after your 14:43Z, 14:44Z, 14:50Z and 14:58Z messages. Phase 1 of the company rework
(`/mnt/project-files/pmr/company-rework/SPEC.md`); the bylaws come in q45.

- The Company Culture window splits 70 / 30. Left: Expansion (free: input goods −2%) over Vertical Integration and
  Diversification, of which a company takes one; Engineering (free: throughput +3%) over Process Engineering,
  Precision Manufacturing and Hallmark Goods. Right: the board, the company's executive with its subsidiaries'
  executives underneath.
- Vertical Integration founds the supply subsidiary (Krupp: Iron Mine, Coal Mine, Power Plant), Diversification the
  sister one (Krupp: Explosives Factory, Motor Industry, Chemical Plant, Automotive Industry), paid from the pool as in
  q43. Charters: Trade on Supply Contracts, Monopoly on Captive Supply, Industry on Diversification, Investment on
  Regional Headquarters, Colonization on Market Reach.
- A subsidiary has no Company Culture tab and no charters, carries half its parent's throughput and input cuts, and
  adds one company slot to your country.
- No special methods or research grants any more. Old nodes come back as points; Krupp's q43 subsidiary becomes its
  supply subsidiary ("Friedrich Krupp Supply").

1. Load your latest PMR Test save. Open Krupp's panel and its Company Culture window.
2. Click Expansion and Engineering. If short of points, take "PMR test: 12 Culture points for each of your companies".
3. Click Vertical Integration, Supply Contracts and Captive Supply, then the three Engineering nodes. Grant the Trade
   charter from the Supply Contracts card.
4. Open another of your companies (found one if needed), click Expansion, then Vertical Integration or
   Diversification. Take "PMR test: £1,000,000 to your investment pool" first if its card shows the pool short.
5. Take "PMR test: finish your subsidiary payments", play a week, then open the new subsidiary's panel and the
   Companies panel. Play to the next month, close the game and tell the build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| R1 | Step 1 | Left: two trees of 11 nodes, Expansion's root over two columns, Engineering's over one; right: "Board" with Krupp's executive (portrait, name), and under a line the Friedrich Krupp Supply executive | No nodes or no board: the window failed (`error.log` names the GUI line). A board without the subsidiary: the list wasn't read (its Regional HQs entry still shows it) |
| R2 | Step 2 | `CC_BUY` lines with `line=xr` and `line=er`, points unchanged; both roots get a check | No `CC_BUY`: the click didn't run (the node's tooltip says why) |
| R3 | Step 3 | `CC_BUY` with `line=vx` and no `SB_PICK` (Krupp already has its subsidiary); Diversification shows a warning, its tooltip "Ruled out by Vertical Integration"; Hallmark Goods shows Krupp's prestige good | An `SB_PICK` line: the q43 subsidiary wasn't counted, and a second one is being paid for |
| R4 | Step 3, then a month | The executive carries Expansion, Engineering, Captive Supply, Process Engineering and "Hallmark Goods: Steel" and "Hallmark Goods: Artillery" traits; the subsidiary's executive a half "Captive Supply" (throughput +5%, input goods −5%); `CC_SUB` lines with `pvx=3` | `CC_SUB` with `pvx=0`: the parent hadn't re-read its numbers yet (one more month). No half trait with `pvx=3`: the trait didn't apply |
| R5 | Step 3 | Before buying, the charter shows faint (icon and name) at the card's foot; after, the vanilla charter button, and the Trade charter can be granted | No button once bought: the charter row didn't find the type (`error.log`). A greyed button: vanilla's own conditions |
| R6 | Steps 4 and 5 | The card lists its industries' icons and "£… × 52"; the click gives `SB_PICK`, a gold bar fills; after the decision `SB_FOUND` with `levels=5`, and the board lists the new subsidiary | `SB_NO_STATE`: no state can take any of its industries; it retries weekly. `levels` below 5: it dissolves within a day (`SB_GONE`) |
| R7 | Step 5 | The subsidiary's panel has no Company Culture tab; the Companies panel's company limit is one higher per subsidiary | The tab shows: the panel didn't read `pmr_sub`. The limit unchanged: the "Subsidiaries" country modifier didn't apply (it should be listed among the country's modifiers) |

## Earlier: one click, three industries (q43, test mod; your PMR Test save carries on)

From the build thread, after your 14:18Z pick ("Paid from pool").

- A company holding the Industry Charter node shows up to three bundles on that card, above the Industry Rights
  button: three building icons each (the industries making its inputs, most valuable first) and the weekly cost.
  Krupp: Iron Mine, Coal Mine, Tooling Workshop, then Power Plant and Oil Rig.
- A click starts paying: 5 levels' construction cost of the bundle's first industry, spread over 52 paid weeks from
  your investment pool (Krupp's first bundle: £38,462 a week with wooden buildings, £27,692 with iron frames). A week
  the pool can't cover is skipped and waits. One bundle at a time per company.
- After the last week the subsidiary is founded with 5 levels of the first industry a state can take, listed under
  the parent's Regional HQs and Assets tab, and left off the Companies panel. It can own and buy all three industries.
- Industry Rights II is gone (q38 settled it: one industry charter per company).
- Every company re-reads its numbers once (the tab's numbers may show 0 until the month ends or you open the tab).

1. Load your latest PMR Test save. Open Krupp's panel (or any of your companies') and its Company Culture wheel.
2. If the Industry Charter node isn't bought, take "PMR test: open the Industry Charter node". If the bundle's
   tooltip says the pool needs more, take "PMR test: £1,000,000 to your investment pool".
3. Hover the first bundle, then click it. Play a week.
4. Take "PMR test: finish your subsidiary payments". Play a week, then a few more days.
5. Open the parent's panel (Regional HQs column and Assets tab), then the Companies panel. Close the game and tell the
   build thread.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| N1 | Step 2 | The Industry Charter card shows bundle buttons with three building icons each and a cost under them; only vanilla's Industry Rights button below | No buttons with the node bought: the company hasn't re-read its numbers (open the tab again, or wait for the month) or the buttons failed (`error.log` names the GUI call). Buttons with no icons: the bundle numbers didn't reach the executive |
| N2 | Step 3 | The tooltip lists the three industries and the weekly cost × 52 weeks; after the click a gold bar fills under the icons, and debug.log has `SB_PICK` with `pick=1` and then `SB_WEEK` with `paid=1`, `w=1` and `pool_after` below `pool_before` | No `SB_PICK`: the click didn't run (button greyed: the tooltip's red line says why). `SB_WEEK` with `paid=0`: the pool was short that week, which is the rule working |
| N3 | Step 4 | `SB_FOUND` with `sub=` naming the subsidiary (Krupp: "Friedrich Krupp Iron, Coal & Tools") and `levels=5`; the bundle shows a green check | `SB_NO_STATE`: no incorporated state can take a level of any of the three (technology or resources); the pick waits and retries weekly. `SB_FOUND` with `levels` below 5: the levels didn't land, and the subsidiary will be gone in a day (`SB_GONE`) |
| N4 | Step 5 | The parent's Regional HQs column lists the subsidiary with your flag; its Assets tab has a section with the subsidiary's 5 levels; the Companies panel doesn't list it | Listed but no Assets section: as L1. Listed on the Companies panel: it lost `pmr_sub` (tell the build thread) |
| N5 | A few days after N3 | The subsidiary still exists, with its 5 levels, and no `SB_GONE` line | `SB_GONE` within a day: it fell under 5 levels (the state's resources or the ownership didn't take) |

## Earlier: a subsidiary on its parent's Assets tab, test companies as buyers (q42, test mod; your Prussia PMR Test save carries on)

From the build thread, after your 14:10Z message. q41's subsidiary works: it is listed under its parent's Regional
HQs and has grown from 5 to 10 Tooling Workshop levels.

- The parent's Assets tab lists the subsidiary's HQ and its buildings right after the company's own HQ, headed with
  the subsidiary's name.
- The Policies cards now count the test companies as buyers, so the Tooling Workshop card gives companies a share
  while Subsidiary B exists. Before, PMR's estimate only knew the game's own companies.

1. Load your latest PMR Test save.
2. Open the parent company's panel (the one listing B under Regional HQs) and its Assets tab.
3. Play a month. Open the Policies tab and look at the Tooling Workshop card's buyer shares.
4. Close the game and tell the build thread. q41's rows below still apply.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| L1 | Step 2 | After "Company HQ in ...", a section "PMR Test Subsidiary B in ..." lists B's Tooling Workshops with their levels | No section: B's HQ building can't be read through the list (`error.log` names the failing call); its Regional HQs entry still opens B |
| L2 | Step 3 | The Tooling Workshop card's company share is above 0%, and in `MV_BUYERS` lines the last of the four `tooling_workshop=` figures (companies) is above 0 | Still 0%: the card hasn't refreshed yet (open the tab again a day later). Still 0 in `MV_BUYERS` after a month: tell the build thread |

## Earlier: cards that shrink to what they show, a subsidiary under its parent's Regional HQs (q41, test mod; your France PMR Test save carries on)

From the build thread, after your 13:11Z and 13:27Z messages.

- A Production Methods card shows a recipe-and-automation row only while one of its cells has a figure, and the card
  takes the height of the rows it shows, on the Policies tab and in the company panel's Methods table.
- A decision, "PMR test: Subsidiary B under a parent company", links PMR Test Subsidiary B to one of your companies
  (founding B first, with 5 Tooling Workshop levels, if the save has none). That company's panel should list B under
  Regional HQs, and the Companies panel should no longer list B. This is the test of whether a
  subsidiary can live under its parent the way you asked; the bundle of three industries comes after it passes.
- It writes a `SUBHQ_TEST` line (and a `SUB_TEST` line with B's levels) at once and the next day.

1. Load your latest PMR Test save.
2. Open the Policies tab: look at the lumber camp, iron mine and tooling workshop cards.
3. Take "PMR test: Subsidiary B under a parent company". Open the Companies panel, then each of your companies'
   panels in turn, and look at the Regional HQs column (under Regional HQs & Colonies). Click B's entry there.
4. Play a few days, close the game and tell the build thread; it reads debug.log and error.log. q40's rows below still
   apply.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| K1 | Step 2 | The lumber camp card shows only its rows with figures and is no taller than it needs; cards with every row filled look as before | The card keeps its full height with empty rows: the rows' visibility didn't take (the row test reads the wrong cells). Rows gone but the card as tall as before: the card didn't resize to its body |
| K2 | Step 3, debug.log | `SUBHQ_TEST` with `has_b=1;sub=1;linked=1;in_list=1;exec_list=1` and `parent=` naming one of your companies | `has_b=0`: founding B failed (`SUB_TEST` shows its levels). `in_list=0` or `exec_list=0`: a company (or its executive) can't hold a list of companies; the next build stores B in a plain variable instead |
| K3 | Step 3 | One company's Regional HQs column lists PMR Test Subsidiary B with your flag, and "No Regional HQs" is gone there | B listed without a flag: the panel can't read the company's own variables, but reads its executive's (the next build uses that). Nothing listed while K2 passed: the panel can't read a company out of a variable list (`error.log` names the failing call) |
| K4 | Step 3 | Clicking B's entry opens B's company panel | Nothing opens: the panel can't open a company it reads out of a list; the next build opens it another way |
| K5 | Step 3 | The Companies panel lists your companies and every company without B; the others still show | B still listed: the hide test can't read B's `pmr_sub`. Every company gone: the test hides all of them (tell the build thread at once) |

## Earlier: a 25% bar to switch, only nearby unlocked options priced, Productivity and Output explained (q40, test mod; your 1836 PMR Test save carries on)

From the build thread, after your 12:56Z to 13:09Z messages.

- A building moves its default only for an option at least 25% more profitable than the default. The bar then gains
  1 point a month at 25% more, up to 6 points (one month) at 150% more. The default is no longer dropped for its own
  inputs at the price cap; only an option needing more of a capped input than the default is passed over.
- Only the default and the unlocked options one step from it on each row and column are priced; none below it while it
  makes a profit. Other cells on the cards stay empty. The newest-recipe scan runs only after research or when a
  state's electricity changes.
- Productivity and Output in the investment chance tooltip have their own tooltips: profit and employees per level,
  goods per level at base prices, and the weight each is multiplied by.
- The productivity span under the building icon stays inside the card.
- The pause decision shows only while the ticks are paused, as "PMR test: resume the monthly ticks" (you paused them on
  22 May 1836 and resumed them on 2 February 1838, so your save runs them).

1. Load your latest PMR Test save.
2. Play three months. Open the Policies tab: look at the iron mine, lumber camp and tooling workshop cards.
3. Hover a card's investment chance, then Productivity and Output in it.
4. Close the game and tell the build thread; it reads debug.log and error.log. q39's rows below still apply.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| S1 | Step 2 | No "PMR test: resume the monthly ticks" decision, and the cards' bars move each month | The decision shows: the save's ticks are paused again (take it). Bars stuck with no decision: something else stops them (tell the build thread) |
| S2 | Step 2, debug.log | `PROFIT` lines carry `ref=` and `gain=`; every `SWITCH_START` line has `gain=` at 0.25 or more and `pts=` from 1 to 6 | A `SWITCH_START` with `gain=` under 0.25: the threshold isn't applied. No `SWITCH_START` lines: nothing beat its default by 25% in three months, which is not a fault (`rm=` in `PROFIT` shows the figures) |
| S3 | Step 2 | Each card shows figures only in the gold cell and the unlocked options one step from it in recipe or in an automation row (none older while the gold cell is positive); `PROFIT` lines' `can=` holds 1 only for those | Every cell still filled after a month: the save's old figures weren't recomputed (no `PROFIT` line with `why=price` or `why=recompute` for that type). An empty gold cell: the default can't run, so nothing is priced around it |
| S4 | Step 3 | Productivity and Output each open a tooltip with three lines and numbers that aren't all 0 | No inner tooltip: the nested tooltip didn't take. Lines with 0: the pick's employees weren't saved (`pmr_pte`) |
| S5 | Step 2 | The span "£x - £y" under each building icon stays inside its card | It still crosses the card's edge: the text box needs a smaller font or a narrower span |

## Earlier: more industries for one company, by a monopoly or by a replacing company (q39, test mod; your 1836 PMR Test save carries on)

From the build thread, after your 12:14Z to 12:28Z messages. Both tests look for a way to give one company more
industries than its one Industry Rights allows, so that one pick can open a bundle of three.

- A decision, "PMR test: Textile Mills monopoly": your first company that isn't a test company (Krupp) gets a
  monopoly on Textile Mills, which is on none of its lists. The test is whether a monopoly lets a company own and
  build a type it has no rights to. Clothes may get dearer in this save.
- PMR Test Subsidiary C, a company type that says it replaces Subsidiary B and carries B's Tooling Workshops plus Coal
  Mines, Iron Mines and Steel Mills. A decision, "PMR test: Subsidiary C replaces B", founds C with no levels of its
  own. The test is whether B's levels pass to C, which would let a company be swapped for a copy with a longer list.
- Both write `RIGHTS_TEST` lines at once, the next day and every 30 days. q38's `SUB_TEST` lines carry on.

1. Load your latest PMR Test save.
2. If Subsidiary B isn't in this save, take "PMR test: found two test companies" first. Open the Companies panel
   and find PMR Test Subsidiary C. Note whether Subsidiary B still shows and whether C's
   Establish button is active (hover it). If it is active, establish C there.
3. If C wasn't established in step 2, take the decision "PMR test: Subsidiary C replaces B". Open the Companies
   panel again and hover C.
4. Take the decision "PMR test: Textile Mills monopoly". Hover Krupp in the Companies panel.
5. Play three months. Watch the construction queue for Textile Mills and Krupp's industries.
6. Close the game and tell the build thread; it reads debug.log and error.log.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| R1 | Step 2 | C listed, its Establish button active although you're over the company limit | C missing: its file didn't load (tell the build thread). Establish greyed for the company limit: replacing doesn't lift the limit; go on to step 3. B gone from the list once C shows, with nothing else changing: `replaces_company` only swaps the list entry |
| R2 | Step 3, debug.log | A `src=2` line with `has_b=0;has_c=1;levels_c=5`, and C's card shows 5 Tooling Workshop levels and four industries | `has_b=1;has_c=1`: founding C doesn't replace B. `has_b=0;has_c=1;levels_c=0`: B is removed but its levels don't move (C then goes within days, under 5 levels). `has_c=0` at `src=2`: the game refuses to found a replacing company (check error.log). No `RIGHTS_TEST` line: the decision didn't run |
| R3 | Steps 4-5, debug.log | `mono=1` at `src=1`, and within three months Krupp's card lists Textile Mills with levels (`co_levels` rises with them) | `mono=0` at `src=1`: a company can't hold a monopoly on a type outside its lists (check error.log). `mono=1` with new Textile Mills owned by others: a monopoly gives no rights to the type. `mono=1` and no Textile Mills built or bought by anyone: a monopoly only shuts others out. `co_levels` can also rise from Krupp's own industries, so its card decides |

## Earlier: a second Industry Rights, every input in the charter list, a grant decision, the investment chance in sections, retool sites out of the build menus, two test companies founded by script, the Industry Charter node by decision (q38, test mod; played 2026-10-19, H1 and C1 seen 12:03Z to 12:14Z)

From the build thread, after your 03:48Z to 04:13Z and 12:02Z messages.

- Each company's Industry Rights list adds the building making each input of its industries (Krupp: Iron Mines, Coal
  Mines, Tooling Workshops, Power Plants, Oil Rigs). This replaces q35's E5, which could not show anything: vanilla's
  list for Krupp was Iron Mines alone.
- Industry Rights II, a copy of vanilla's industry charter under its own name, behind the same node. The test is
  whether a company may hold both.
- A decision, "PMR test: open the Industry Charter node": each of your companies takes the node free, and its card
  shows both charter buttons.
- A decision, "PMR test: start a research grant on both goods lines".
- A building's first days no longer set its wage from empty books; the card's switching bar follows the state's bar
  the day it moves.
- The investment chance tooltip in sections that add up: Base, Policy (the policy cards and your priority group, such
  as Light Industries), Companies, Productivity, Losses, Output. Foreign or Domestic is out of the card's figure: it
  moves investment home, not towards one type.
- Retooling sites are gone from a state's Build Urban Buildings menu and the Buildings panel's Available lists.
- A decision, "PMR test: found two test companies": PMR Test Subsidiary A with 2 Tooling Workshop levels and B with
  5, each in a state without one. The companies stay in the save, so take it last.

1. Load your latest PMR Test save.
2. Take the decision "PMR test: open the Industry Charter node". On Krupp's Company Culture wheel, click Industry
   Rights on the Industry Charter card and look at its list. With Industry Rights held, grant Industry Rights II with
   another building.
3. Take the decision "PMR test: start a research grant on both goods lines". Hover the Private tab's Investment Pool.
   Play a few weeks.
4. Open the Policies tab with Light Industries raised. Hover a textile mill card's investment chance, then Policy.
   Right-click a state's Build Urban Buildings, and open the Buildings panel's Available lists.
5. Take the decision "PMR test: found two test companies". Open the Companies panel. Play two months.
6. Close the game and tell the build thread; it reads debug.log and error.log. q35's rows below still apply.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| H1 | Step 2 (seen 12:14Z: greyed, "already has other Industry Rights") | Industry Rights II grants a second building while Industry Rights keeps the first; Krupp's Available Industries shows both | Industry Rights II greyed out with "already has other Industry Rights": the game allows one per kind, so a company can't hold two industry charters. Only one button on the card: the game lists one charter per kind (tell the build thread). No buttons: the node didn't open (check `CC_BUY` with `line=ch`) |
| H2 | Step 2 | Industry Rights lists Iron Mines, Coal Mines, Tooling Workshops, Power Plants and Oil Rigs | Iron Mines alone: the company file override didn't load |
| E3 | Step 3, debug.log | A `CC_TEST_GRANTS` line per company with `grant_g1` and `grant_g2` not 0; then `CC_GRANT_WEEK` lines with `line=g1` and `line=g2` every week; the pool tooltip's Research grants is their sum | `grant_g2=0/0` in `CC_TEST_GRANTS`: that line couldn't take a grant (its next tier already known or gated); no `CC_TEST_GRANTS` line: the decision didn't run |
| T1 | Step 4, debug.log | Policy shows a Light Industries line; no Foreign or Domestic line; an `MV_PARTS` line where, per type, the six numbers before the last add up to the last | No `MV_PARTS` line: the Policies tab never refreshed (open it once). Numbers that don't add up: the snapshot is wrong (tell the build thread) |
| T2 | Step 4 | No "Retooling (…)" entry in Build Urban Buildings or the Available lists, and no empty gap where one was | They still show: another mod in the playset overrides those two screens, or ours didn't load. A gap: the hidden entry still takes its slot |
| C1 | Step 5, debug.log (seen 12:03Z: founding works, over the company limit, with levels; A gone within days) | `SUB_TEST` lines with `has_a=1;levels_a=2;has_b=1;levels_b=5` at `month=0` and in each later line; both companies listed in the Companies panel | `has_a=0;has_b=0` at `month=0`: the game refuses to found a company mid-game, or the country is at its limit (`companies` = `max`). `has=1` with `levels=0`: script can't give a company levels mid-game. A gone and B kept in later lines: a company under 5 levels is dissolved. Both gone later: script-founded companies aren't kept. No `SUB_TEST` line: the decision didn't run |

## Earlier: profit figures from the buildings' own books, built special methods, a cleaner Policies tab, faster months (q35, test mod; being played 2026-10-19 as Prussia)

From the build thread, after your 02:32Z to 02:47Z messages on q34.

- The profit figures now use what each building really pays. The wage comes from its own books (productivity ×
  employees ÷ 52 − weekly balance) instead of a fixed £390 per 10,000 wage units, and goods count with the building's
  throughput. A state's figures are redone at the next monthly pulse when a price or the wage moves 10% or more.
- The investment chance tooltip adds up: Base + Policy + Profit and output = the total. Expanded Works shows only
  when one of the type's companies holds it.
- Policies cards: the company icon sits on the building icon's top-right corner. The bars under the grid line up
  with it. The switching bar shows only while a switch is under way, thicker, with the target's icon, and the card
  grows and shrinks with it. The sort row reads Name | Size | Investment chance.
- The details panel has no "Most profitable" line. Its switching bar shows only while a switch is under way.
- The company panel lists each industry once (retooling sites are hidden, still owned). Company Culture's Methods
  shows the Policies grid for the types the company owns, and a row per goods line with each special method's
  profit. "Research grants" moved into the Investment Pool tooltip.
- Engineering special methods are built: a company's levels move onto its special method one at a time, as private
  retooling levels finish there. The building's modifiers name the method ("Steam Winding"), not "Company works
  output". A goods tier whose technology your country has unlocks free at once. Grants now research tiers ahead of
  your technology, one per goods line at a time, on a green arrow bar.
- The Industry Charter tries to offer only the building that makes the company's main input (Krupp: iron mines).
- Months are cheaper: a building finds its target with fewer checks, and skips its level accounting in months when
  nothing changed (a ranch costs about half). Other countries' log lines no longer carry padding, so debug.log keeps
  more of your game.

1. Start a new game on the PMR Test playset as Prussia. Open the Buildings panel and click Policies. Look at the
   sort row, a card with a company icon, and the bars under the grids.
2. Open Westfalen's steel mill. Note its productivity (the £ under the graph), Weekly Balance, Wages and Throughput,
   and hover its Steel output modifier.
3. Open a company with a goods line (Companies). Look at Available Industries and the Company Culture tab's Methods.
   Found Engineering if the company hasn't. Take the decision "PMR test: 6 Culture points for each of your companies" if you need points, and
   start a research grant on each goods line. Hover the Private tab's Investment Pool.
4. Play to 1 January 1837. Open a card or a details panel whose type shows a switching bar, and hover it.
5. Whenever a company holds the Industry Charter node, open its charter window and look at the building list.
6. Close the game and tell the build thread; it reads debug.log and error.log.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| W1 | Step 2, debug.log | The steel mill's `PROFIT` line: `earn=` matches the productivity, `bal=` the weekly balance, and the running recipe's `rw` × levels × `occ` is close to the panel's Wages | `wage=390` everywhere, or `earn`, `bal` or `occ` 0: the books weren't read, and the figures still use the old fixed wage |
| W2 | Step 2, debug.log | `thr=` is close to 1 + the panel's Throughput | `thr=1.00` on a building with several levels: the throughput read sees nothing |
| W3 | debug.log, a year | At least one `PROFIT` line with `why=price` | None in a year: the price check never fires, so figures can still go stale |
| W4 | Steps 1, 4 | Each card's gold figure has the same sign as that type's buildings' weekly balance (steel, ranch) | A negative card while the buildings make money: tell the build thread which type and state |
| W5 | Step 1 | The investment chance tooltip's Base + Policy + Profit and output equals its total; no Expanded Works line when no company holds it | An Expanded Works line without the node: the parts were still read at different times |
| C1 | Step 1 | The company icon on the building icon's top-right corner; the level number and productivity fully visible; clicking it opens the company | The icon over the level number: the old files are installed |
| C2 | Step 4 | A card with a switch under way: a thick green (newer) or red (older) arrow bar under the grid, the target's icon at its end, "Default → Pick" and "N of 6 months" on hover. A card without one: no bar and no gap at its foot | No bar anywhere by 1837: check debug.log for `SWITCH_START`; none means no switch started (fine). A strip or gap at a card's foot: the card didn't shrink |
| C3 | Step 1 | The sort row reads Name, Size, Investment chance, three equal buttons; the Buildings tab still has Productivity | Four buttons on Policies: the old files |
| C4 | Steps 2, 4 | No "Most profitable" line on the details panel; its switching bar only while that state switches | — |
| P1 | Step 3 | Each industry once in Available Industries, the companies list and the company tooltip | Each still doubled: the filter didn't match the retooling sites |
| P2 | debug.log | `RETOOL_LEVEL` lines for company-owned buildings still appear | None: hiding the sites stopped retooling (tell the build thread) |
| P3 | Step 3 | Methods lists only the types the company owns, with the same figures and gold square as the Policies card; a row per goods line with each special method and its £ a week | An empty Methods: the copies weren't refreshed (debug.log `CM_REFRESH` at most once a day) |
| P4 | Step 3 | The Investment Pool tooltip has a "Research grants" line while a grant runs; nothing under the pool itself | No line while a grant runs: the tooltip override didn't load |
| E1 | Step 3, debug.log | Founding Engineering gives the goods tiers whose technology Prussia has at once: `CC_FRONTIER;line=g1;tier=N`, points unchanged | A `CC` line with `g1tk` at or above N but no `CC_FRONTIER`: the free unlock never fires |
| E2 | Step 3, then play | `WORKS` lines show held and built per tier; investors queue the building's retooling site; each `RETOOL_LEVEL` there is followed by `WORKS_LEVEL tier=N` and built + 1. Step 2's Steel output reads "from" the method's name once built | Built stays 0 for a year while `RETOOL_LEVEL` lines appear: the hook doesn't run. `queued=0` with `cap>0` for months: investors are never offered the site |
| E3 | Step 3, debug.log | `CC_GRANT_WEEK` lines with `line=g1` and `line=g2` every week; the pool tooltip's Research grants is their sum | Only one line paid: the second grant didn't start |
| E4 | Step 3 | A green bar with moving arrows under each node with a grant, filling by paid weeks | A blue bar: the old files |
| E5 | Step 5 | Only the company's input building in the charter's list (Krupp: Iron Mine) | Every building listed: the charter's check can't see the building being picked, so no restriction is possible. No building listed, or the charter missing: tell the build thread |
| S1 | debug.log, monthly | A `SKIP` line each month with `skip`, `ran`, `checked`; after the first month `skip` is the larger | No `SKIP` line: the count never ran (error.log `pmr_`). `skip=0` every month: the skip never fires |
| S2 | debug.log, 13+ months | `checked` above 0; no `SKIP_MISS` line ever | Any `SKIP_MISS` line is a bug: it names the building and the value. `checked=0` throughout proves nothing |
| S3 | logs folder | debug.log lasts much longer than a minute of play; `TECH` lines only for Prussia | Files still rotating every minute: tell the build thread |
| E8 | error.log | No line naming `pmr_wage_`, `pmr_read_books`, `pmr_moved_`, `pmr_recount_`, `pmr_skip_`, `pmr_cw_`, `pmr_works_`, `pmr_cm_` or `PMR_CM_` | Any such line: that part never ran, and the rows above it are not results |

## Earlier: Policies tab, the 6-month switching bar, automation on 38 types, explosives, Hallmark Goods (q34, test mod; played 2026-10-19 as France and Prussia, feedback 02:32Z)

From the build thread, after your 01:07Z to 01:23Z messages on q33.

- The Investments tab is now Policies. The Building type sort button is gone. AI weight reads "Investment chance".
- Each card shows the country's levels on the building icon and the type's productivity under it. Under the grid
  sit the automation bar (types with automation) and one small bar per trade-off group, as on the details panel.
- A new pick no longer becomes the default at once. A bar fills over 6 monthly pulses, green toward a newer recipe
  and red toward an older one, and the default changes when it is full. A pick that changes starts the bar again.
  The default changes at once the first time a building is seen, on its first pick at market prices, and when the
  default can no longer run. The bar shows under "Most profitable" on the details panel, under each type row on the
  Buildings list (biggest state), and at the foot of each card.
- The pick is re-checked every 5 to 7 months instead of 10 to 14. A recipe whose own extra input sits at the +75%
  price cap is skipped, even when it is the current pick.
- Every vanilla labour saver is now its own automation axis: farms' harvesting, plantation railroads, ranches,
  logging camps, fishing and whaling, oil rigs, glassworks, munitions and motor industry join the 15 types from q25.
- Mine explosives (nitroglycerin, dynamite) are a trade-off again, blended by price.
- The 59 companies that vanilla let make their prestige good whenever prosperous (Krupp, Schneider-Creusot,
  Saint-Étienne, Maison Worth...) now wait for Hallmark Goods like the rest.
- A company's goods tier unlocks at once, with no points or grant, when your country already has the technology for
  the recipe after its base one.
- "Wage floor" is now "Wage cut cap"; a works input reads +5.0% instead of +4.8%.
- On the details panel's Process view, an input with a modifier (Fabric input +5%) shows that value beside its
  amount on the left.
- The building screens are lighter (your 01:23Z message): every per-type piece PMR adds (recipe bars, pick and
  automation rows, owners' recipe icons, type-row bars, upgrade buttons) is now built only for the building on screen,
  not hidden 44 times over. The details panel builds about 870 widgets instead of 3,100 (vanilla: 290), the Buildings
  list about 160 a row instead of 750, and the cards are built only while Policies is open. The pick's price-cap
  veto checks about 36 cases instead of 1,260 on a ranch.

1. Start a new game on the PMR Test playset as France. Open the Buildings panel and click Policies. Look at a coal
   mine, a wheat farm and a cotton plantation card, and hover the small bars under their grids and the bar at the
   foot of a card.
2. Hover a card's building icon and its productivity line.
3. Unpause and play to 1 August 1836. Open a building that shows a bar under "Most profitable" on its details panel
   and hover the bar.
4. Open Schneider-Creusot or Saint-Étienne (Companies) and look at its prestige good.
5. Whenever a building's Process view lists an input modifier on the right, look at that input on the left.
6. Then do q33's steps below.
7. Close the game and tell the build thread; it reads debug.log and error.log.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| T1 | Step 1 | The tab reads Policies; no Building type sort button; the last sort button reads Investment chance | "Investments": the old files are still installed |
| K1 | Step 1 | Every card: the level count on the building icon's bottom-left, the productivity under the icon, the bars under the grid, a thin grey bar at the foot | A card with no level count: the building type couldn't be read from the card (error.log naming `GetBuildingType` or `GetNumLevelsInCountryFormatted`) |
| K2 | Step 1 | The coal mine has a bar for explosives (grey for none), the wheat farm and cotton plantation an automation bar; hovering a bar names the group and lists each option above 0 | The bars all grey or empty on 1 January is expected on types France doesn't run; empty on a type it runs means the card's copies never ran (error.log naming `pmr_mv_refresh`) |
| X1 | Step 1, debug.log | `PROFIT` lines for coal, iron, lead and sulfur mines include `explosives:` in `px=`, and the farms' and plantations' lines show `pair=` with two numbers | No `pair=` on farms: the wider split didn't reach them; tell the build thread |
| D1 | Step 3 | A green or red bar under "Most profitable" while the pick differs from the default; its tooltip reads "Default → Pick" and "N of 6 months". debug.log has `SWITCH_START` lines, then `DEFAULT` lines with `months=6` | No `SWITCH_START` line by August: every pick matched its default (fine if the cards' gold squares match the defaults); a `SWITCH_START` but no `DEFAULT` after 6 months: the month count never advanced (tell the build thread) |
| H1 | Step 4 | The company's prestige good is locked, its tooltip naming "Hallmark Goods" | Producible: the gate isn't installed (the old files) |
| F1 | debug.log | `CC_FRONTIER` lines for companies whose line's next recipe France already knows, with `tier=` the tier they reached | No `CC_FRONTIER` line in the first month: no French company is behind the frontier on 1 January, which can be right; tell the build thread if a company's wheel shows a goods tier locked whose recipe France already runs |
| I1 | Step 5 | "+5%" beside the input on the left, matching the right-hand modifier | Nothing on the left: the game doesn't take the modifier's name from the good (error.log naming `GetValueFor` or `Concatenate3`) |
| PF1 | Steps 1-3 | The details panel, the Buildings list (expanded type rows too) and the Policies cards show the same bars, rows, owner icons and upgrade buttons as in q33, and open faster than in q33, most of all for a building with many owners | A bar or row missing that q33 showed: a piece built for its own type can't read its building from inside the list it now sits in (error.log naming `DataModelRepeatedItem` or the missing piece's variable); tell the build thread. Opening no faster: the cost is elsewhere (a monthly tick at the same moment); tell the build thread which screen |
| E7 | error.log | No line naming `pmr_switch_`, `pmr_cc_frontier`, `pmr_cc_free_`, `pmr_c_sw`, `PMR_MV_AUTO_TT` or `PMR_MV_OPT_TT` | Any such line: that part never ran, and the rows above it are not results |

## Earlier: the policy window, weekly research grants, who buys, company marks, nested Policy, AI weight sort (q33, test mod; not yet seen)

From the build thread, after your 23:53Z to 00:06Z messages on q32.

- Add Policy now opens the policy window to the right of the Buildings panel instead of down the list, and its
  "One policy at a time" tooltip is gone.
- A research grant costs £500 a level each week for tier I (£1,000 tier II, £1,500 tier III), paid from the
  investment pool for 52 paid weeks (12 months). A week the pool can't cover isn't paid and the grant waits. The
  bar is the game's own progress bar; its tooltip gives the weekly cost. The Private tab shows "Research grants" under
  the pool while one runs.
- Under each card's AI weight: who would buy a new private level, as Manor Houses, Local Shop Owners, Financial
  Districts and Company HQs. This is PMR's estimate from the game's own rules (00_ai.txt and the owners'
  investment_scores); the game's pool shares by owner can't be read, so levels stand in for them.
- A card whose type one of your companies works gets an outline and that company's icon on the building icon.
- The AI weight tooltip's Policy word opens a nested tooltip with each policy's part.
- On Investments a fifth sort button, AI weight, shows the cards from the heaviest AI weight down. The search and
  filters step aside while it is on; any other sort button brings them back.

1. Start a new game on the PMR Test playset as France. Open the Buildings panel from the left sidebar and click
   Investments.
2. Click Add Policy. Close the window with its X.
3. Hover a card's AI weight, then hover the word Policy in that tooltip. Look at the four owner icons under the AI
   weights and hover one. Find a card with a company icon on its building icon and click the icon.
4. Click the AI weight sort button and scroll; click Name, then AI weight again.
5. Take the "PMR test: … Culture points for each of your companies" decision, open a company with a goods line (Company Culture), and buy the first
   goods tier. Hover its bar. Unpause and play three weeks, then open the construction panel's Private tab.
6. Then do q32's steps below.
7. Close the game and tell the build thread; it reads debug.log and error.log.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| P4 | Step 2 | A window with France's economic system's policies opens to the right of the panel, under the map mode button; the X closes it | Nothing opens: the click never set the window's flag or the panel won't draw outside itself; tell the build thread, error.log naming `pmr_policy_popout` or `pmr_policy_window` says which |
| N1 | Step 3 | Policy is underlined; hovering it shows "Policy" with its total and one line per policy part that isn't 0 (none on 1 January without a policy) | No underline: the nested tooltip markup isn't read in this tooltip; tell the build thread |
| B1 | Step 3 | Four icons with percentages under each AI weight; on light industry (no collectivization) Local Shop Owners reads 0%, Manor Houses 0%, Financial Districts and Company HQs share the rest. debug.log has an `MV_BUYERS` line per refresh with `type=mh/self/fd/ch` shares | All four 0% everywhere: `MV_BUYERS` missing (the refresh never ran, error.log naming `pmr_bo_refresh`) or `mhl=0;fdl=0` with every share 0 (the owners' scores read 0); tell the build thread |
| C1 | Step 3 | Cards for types your companies work (textiles, food, iron, ...) have an outline and a round company icon; clicking it opens that company | Outline without an icon: the company couldn't be reached through its executive; no outline anywhere: France has no company working those types yet, which is fine on 1 January |
| S2 | Step 4 | The AI weight button is highlighted, the search and filters are gone, and the cards run from the highest AI weight percentage down; every card is there | No cards at all: each slot couldn't read its own place in the list (error.log naming `GetIndexInDataModel` or `pmr_methods_slot`). Cards in the old order: the sort never ran (the `MV_SHARE` line's `type=weight/share/place` should have places 0, 1, 2... by falling weight) |
| S3 | Step 4 | Name brings back the filters and the game's alphabetical order; AI weight sorts again | The filters stay hidden after Name: the button didn't clear the AI order |
| G3 | Step 5 | The grant's bar is the game's default progress bar, as on the construction queue, with "Grant 0 / 12 months"; its tooltip reads "£X a week", "N levels × £500" and "From the investment pool" | The old green bar: the old files are still installed |
| G4 | Step 5 | A `CC_GRANT_WEEK` line each week with `paid=1`, `gweek=` the weekly cost and `pool_before` minus `pool_after` close to `gweek`; the Private tab shows "Research grants -£X weekly" under the pool | No `CC_GRANT_WEEK` line after a week: the weekly clock never started (error.log naming `pmr_cc.1` or `pmr_cc_gclock`). `paid=0`: the pool held less than a week's cost |
| E6 | error.log | No line naming `pmr_mv_sort`, `pmr_mv_rk`, `pmr_bo_`, `pmr_mv_co_`, `pmr_cc_grant_week`, `pmr_cc_pool_read` or `pmr_policy_popout` | Any such line: that part never ran, and the rows above it are not results |

## Earlier: Production Methods cards in one set of columns, AI weight as a share, base prices at game start (q32, test mod; seen 2026-10-18 23:53Z on 1 January)

From the build thread, after your 23:22Z message and screenshots on q31. Your q31 logs are saved in
`pmr_dev_files\logs_q31`: no PMR errors; the game stayed on 1 January 1836.

- Every card now has the same shape: the building's icon, then one framed grid of the same width on every card, with
  recipe columns at the same place. Types without automation pairs (glassworks, farms, plantations, ports...) get a
  one-row grid. The AI weight sits at the same place on the right of every card.
- The AI weight on a card is now that type's share of the sum of all AI weights on the tab (its AI value times its
  priority multiplier, divided by the total). The tooltip gives the weight, the total and the breakdown.
- Why the profits read negative: on 1 January the cards showed the game-start pass, which read prices before the
  market had any (tooling showed -£292 for its pick; in your q30 game the same workshops made +£246 to +£1,438 a level
  once prices existed, Burgundy 2 January and Lorraine 29 January). That pass now uses base prices; each building
  recomputes at market prices on its first monthly pulse in January. Some stay negative at real prices: in q30 French
  clothes sold at 0.6-0.7 of base with dye at the +75% cap, and glass sold at 0.65.

1. Start a new game on the PMR Test playset as France. Before unpausing, open the Buildings panel from the left
   sidebar and click Investments. Scroll through the cards and hover a few AI weights.
2. Unpause and play to 1 February 1836, then pause. Click Buildings, then Investments again.
3. Then do q31's steps 2 to 8 below (they were not reached in q31).
4. Close the game and tell the build thread; it reads debug.log and error.log.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| A1 | Step 1 | Every card: the building icon on the left, then a framed grid the same width as every other card's, recipe icons in the same columns from card to card, the AI weight at the same place on the right | The glassworks card still framed around its icon: the old q31 files are still installed |
| W1 | Step 1 | Each AI weight reads as a percentage (all cards together come to about 100%); its tooltip reads "AI weight X of Y" then Base, Policy, Profit and output, Priority. debug.log has a `MV_SHARE` line whose `sum=` is the total and whose `type=weight/share` pairs add up to `sum=` and to 1 | "0.0%" on every card: the total read as 0 (`MV_SHARE` with `sum=0`); tell the build thread. No `MV_SHARE` line: the tab's refresh never ran (error.log naming `pmr_mv_refresh`) |
| P1 | Step 1, debug.log | The `PF` lines dated 1 January show positive `avg=` for tooling workshops and steel mills (q31: -322.7 and -2,910.6) | Still those negatives: the game-start pass still read the empty market; tell the build thread |
| P2 | Step 2, debug.log | `PROFIT` lines with `why=first_month` for France's buildings through January, and the cards show those figures after step 2 | No `first_month` lines by 1 February: the monthly pulse never reached the profit calculation; the cards then still show base-price figures |
| E5 | error.log | No line naming `pmr_setup`, `pmr_mv_w`, `pmr_mv_sh`, `pmr_mv_wsum` or `pmr_methods_view` | Any such line: that part never ran, and its rows above are not results |

## Earlier: grants paid from the investment pool, the Production Methods cards fixed, less text (q31, test mod; opened 2026-10-18 on 1 January only, logs in logs_q31)

From the build thread, after your 22:28Z message and screenshots on q30. Your q30 logs are saved in
`pmr_dev_files\logs_q30`.

- Investments: the cards were blank because the list asked for each row's building type in a form the game doesn't
  match; they now use the form vanilla's own rows use. On Investments the search, filters and sort buttons sit under the
  "Production Methods" header; on Buildings they stay at the top.
- Research grants cost money from your investment pool, no longer extra input goods: £500 per level the company
  employs for a tier I grant, £1,000 for tier II, £1,500 for tier III, taken when the grant starts. A goods node stays
  locked while the pool holds less ("Investment pool needs £…").
- Stewardship opens with Safety Rules and a running grant: a tier whose grant is running now counts as bought toward the
  2 nodes the second founding culture needs.
- Less text: no bullets on the charter nodes, no "Choose a founding culture", no line under the points bar, and the
  grant shows only its bar. Providence's nodes have a green outline, Stewardship's stay purple.
- Each goods, Supply and Up-skilling node shows a picture of the company's own method.
- Shorter text everywhere (your "be ruthless" ask): a node's tooltip is now only why it is locked (and, for a goods
  node, the grant's months and cost); lock reasons drop "Locked:"; the Methods intro, several button tooltips and the
  executive traits' descriptions are gone; the Private tab, policy cards and building panel tooltips lose their
  closing explanations. New wording shows in English in the other languages until the final translation round.

1. Start a new game on the PMR Test playset as France, unpause and play to 1 February 1836, then pause.
2. Open the budget panel and note the investment pool.
3. Take "PMR test: 6 Culture points for each of your companies" twice.
4. Open Dollfus-Mieg's company panel and click its Company Culture tab. Look at the wheel.
5. Click Engineering, then Safety Rules, then the textile mill's first goods node. Hover Stewardship.
6. Open the budget panel again and look at the investment pool.
7. Open the Buildings panel from the left sidebar and click Investments. Scroll down past the header, click each sort
   button and turn the Rural filter on and off.
8. Click Buildings.
9. Close the game and tell the build thread; it reads debug.log and error.log.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| C1 | Step 7 | One card per building type under "Production Methods": method row or grid on the left, AI weight on the right | Still blank: the cards' lookup still fails (error.log naming `pmr_methods_cards`, `BuildingType` or `ObjectsEqual`); tell the build thread |
| C2 | Steps 7 and 8 | On Investments the search, Filters and the four sort buttons sit under the header and sort and filter the cards; on Buildings they are at the top as before | Filters at the top on Investments: the old q30 files are still installed |
| U1 | Step 4 | Charter nodes show only their name; nothing written under the seal or under the points bar | A bullet or caption still there: the old files are still installed |
| U2 | Step 4 | Stewardship's founding node is purple, Providence's green | Both purple: the old files are still installed |
| U3 | Step 4 | The goods nodes show pictures of sewing and cutting, not a rifle barrel or a kiln; Supply and Up-skilling nodes show their own pictures | The rifle barrel or kiln still there: the old files are still installed. A node with an empty frame: its picture file is missing; tell the build thread which node |
| G1 | Step 5, debug.log | A `CC_GRANT_COST` line with `gcost=` (thousands of pounds) and `pool=`, then a `CC_BUY` line whose `pool=` is lower by `gcost`; step 6 shows the pool down by about that much | `pool=` the same in both lines: the game ignored a negative amount; tell the build thread. `gcost=0`: the company's employed levels read as 0 |
| G2 | Step 5 | The grant shows a green bar "Grant 0 / 12 months" and nothing under it | Text lines under the bar: the old files are still installed |
| S1 | Step 5's hover | Stewardship reads "Ready to buy" (2 points) | "Needs 2 nodes in the first arm": the running grant isn't counted (debug.log `CC` line shows `grant=`); tell the build thread |
| E4 | error.log | No line naming `add_investment_pool`, `investment_pool`, `pmr_cc_gco`, `pmr_cc_gc`, `building_browser_panel`, `pmr_methods_cards` or `pmr_company_culture` | Any such line: that part never ran, and its rows above are not results |

## Earlier: Production Methods cards, a quieter wheel, 12-month grants (q30, test mod; played 2026-10-18, logs in logs_q30)

From the build thread, after your 21:53Z message and screenshots on q29. Your q29 logs are saved in
`pmr_dev_files\logs_q29`: no errors from the new window or the Investments tab, 29 `PF` lines as France, and two
faults fixed here. The art academy's AI weight term came out at about 4 million, because its workers sit in its
ownership method and PMR divided its profit by 1 worker; it now divides by the building's whole workforce, as the game
does. Six text keys were missing or doubled in error.log; they are fixed.

- The wheel: no gold glow behind a node you can buy, no gold orbit dots, and no "Drag to move, scroll to zoom" line.
  A goods node shows its method's name, then the output gain (green) and the extra input (red) on lines of their own,
  without "over the base … method".
- Hallmark Goods shows the company's own prestige good, its name and picture (Dollfus-Mieg: Designer Clothes), and
  the STEWARDSHIP title moved out so it no longer runs behind the node.
- Node tooltips are shorter: the name, the lock reason, the bullets, and for a goods tier "Unlocks after a 12-month
  research grant." The closing line on cost, arm and what rules it out is gone. Research grants run 12 months.
- Investments: the header reads "Production Methods" with nothing under it. Each building type is a card: the recipe
  row or recipe and automation grid on the left, the AI weight on the right ("AI weight", then the weight and the
  priority multiplier). The cards are the Buildings list's own rows, so the search, filters and the four sort buttons
  stay on both tabs and sort and filter the cards too. The AI weight tooltip is five short lines.

1. Start a new game on the PMR Test playset as France, unpause and play to 1 February 1836, then pause.
2. Take "PMR test: 6 Culture points for each of your companies" twice.
3. Open Dollfus-Mieg's company panel and click its Company Culture tab. Look at the wheel, then hover a goods node.
4. Click Engineering, then the textile mill's first goods node, and look under it.
5. Open the Buildings panel from the left sidebar and click Investments. Click each of the four sort buttons, then turn
   on the Rural filter and off again. Hover an AI weight.
6. Click Buildings.
7. Close the game and tell the build thread; it reads debug.log and error.log.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| W1 | Step 3 | No gold bars glowing behind any node, no rings of gold dots, nothing written in the top left corner under the title | A glow or dots still there: the old q29 files are still installed (the test mod folder wasn't replaced) |
| W2 | Step 3's goods node | The method's name in yellow, then "+15% Clothes" in green, then "+5% Fabric" in red on the next line; no grey line under them. Its tooltip ends "Unlocks after a 12-month research grant." with no "Costs … Ruled out by …" line | One combined line or a "for": the q29 text is still loaded |
| W3 | Step 3, the Stewardship arm's outermost node | It reads "Designer Clothes" with the designer clothes picture, and the STEWARDSHIP title sits clear of it | "Hallmark Goods" with a glass picture: the company's prestige goods list was empty in that window (error.log naming `GetPrestigeGoods` or `DataModelFirst`). The title still behind the node: tell the build thread, with a screenshot |
| W4 | Step 4 | A green bar "Research grant 0 / 12 months" under the node | "/ 24 months": the q29 files are still installed. No bar at all with `CC_BUY` in debug.log: the grant didn't start |
| I1 | Step 5 | "Production Methods" under the priorities, with no text under it, then one card per building type: icon and method row or grid on the left, "AI weight" and a number with ×1.00 on the right; nothing wider than the panel | The header but no cards: a card is made only for its own list row, and that lookup failed (error.log naming `pmr_methods_cards`, `DataModelRepeatedItem` or `Select_int32`); tell the build thread |
| I2 | Step 5's sort buttons and filter | Each sort button reorders the cards as it reorders the Buildings rows; Rural leaves only rural building types | The buttons show but the cards don't move: the cards aren't following the list's order; tell the build thread which button |
| I3 | Step 5's hover | Five lines: "AI weight for (building)", Base, Policy and Foreign/Domestic bar, Profit and output (with £ a week), Priority | Blank numbers on every line: the monthly count (`PMR;rec=PF`) never ran |
| I4 | Step 6 | The normal Buildings rows, with no cards | Cards on Buildings: the tab flag isn't read by the list |
| P3 | debug.log `PMR;rec=PF` | The art academy's `term=` is in the thousands or less, not millions | Still millions: the workforce fix didn't load |
| E3 | error.log | No line naming `pmr_cc_why`, `PMR_CC_FX_pg`, `PMR_EMPTY`, `pmr_methods_cards`, `building_browser_panel` or `pmr_company_culture` | Any such line: that part never ran, and its rows above are not results |

## Earlier: the Investments tab, AI weight by vanilla's own scoring, the full-screen wheel fixed (q29, test mod; played 2026-10-18, logs in logs_q29)

From the build thread, after your 21:08Z to 21:32Z messages on q27. q29 replaces q28, which was installed for a few
minutes with an earlier AI weight scale and never played.

- The full-screen Company Culture window now finds its company: q27 asked the company panel for it from outside the
  panel, so every node showed every state at once and the game logged errors without end (941,475 on your screen; they
  also pushed q27's early debug.log lines out of the log). Clicking a company's Company Culture tab, or its "Open
  Company Culture" button, now stores that company's executive on your country, and the window reads the company from
  there. Its X moved left of the topbar's construction box, which covered it.
- The side Buildings panel has two tabs at the top, like the construction panel's: **Buildings** (the normal list) and
  **Investments**: the economic law and policy cards, the investment priorities, then Private Owners' Methods, each
  building type's recipe row with its AI weight in a strip under it. The policy window opens under the cards, one policy
  to a row. Closing the panel puts it back on Buildings. The Building Registry is vanilla again, and the q27 button under
  it is gone.
- AI weight by vanilla's own scoring (your 21:10Z and 21:32Z asks). Vanilla's investment pool scores a new level as
  its AI value (1000 for most buildings) plus its predicted weekly profit divided by its workers x 7,500 (a loss
  x 10,000), plus the goods it makes at base prices x 0.31, plus market terms, then multipliers. PMR now scores each
  state's most profitable recipe the same way (profit and output terms, at the state's prices) and, every month for
  every country, adds the level-weighted average of that score for the building type to its AI value, never below 100.
  The game still adds its own terms for the state it looks at, so profit counts twice: locally and as your country's
  average. A type the country has nowhere gets nothing added.

1. Start a new game on the PMR Test playset as Prussia, unpause and play to 1 February 1836, then pause.
2. Take "PMR test: 6 Culture points for each of your companies" twice.
3. Open Krupp's company panel and click its Company Culture tab. Hover Expansion and the steel mill's Works Method II;
   click Engineering and hover them again.
4. Click the back arrow, then the X. Open another company's panel and click its Company Culture tab.
5. Open the Buildings panel from the left sidebar and click Investments. Hover an AI weight strip. Click the policy
   card's button to open the policy window, then close it.
6. Close and reopen the Buildings panel.
7. Close the game and tell the build thread; it reads debug.log and error.log.

Rows L2, K1, K2 and M1 of the q27 section below still apply on this run (step 5 of q27 for L2); F1, F2 and B1 here
replace q27's.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| F1 | Step 3 | A full-screen window like the tech tree: "Company Culture: Friedrich Krupp" at the top, the back arrow top left, the X left of the construction box, Krupp's level, points and bar under the title. Bought, buyable and locked nodes look different; the goods nodes show their methods; no charter buttons on unbought charter nodes; the error counter in the corner doesn't climb | The q27 picture again (every node the same, empty goods nodes, errors climbing): the window still can't read the company. error.log names `pmr_cc_exec` or `Character.GetCompany`; tell the build thread which |
| F2 | Step 4 | The back arrow returns to Krupp's company panel, the X closes both, and the second company's tab opens the full-screen window with its own name and seal | Krupp's wheel over the second company: the stored executive isn't replaced on the click (`pmr_cc_view_sgui` in error.log) |
| L1 | Step 3's hovers | Before Engineering, Works Method II reads "Locked: needs the Engineering founding culture." After, Expansion reads "Ruled out: this company holds Engineering." | A blank first line under the name: the reason's custom localisation didn't resolve (error.log names `pmr_cc_why`) |
| B1 | Step 5 | Two tabs, Buildings and Investments, at the top of the panel. Investments shows the law and policy cards, the priority rows, then "Private Owners' Methods" with a recipe row per building type you have and an AI weight strip under each; nothing wider than the panel | No tabs: another enabled mod replaces `building_browser_panel.gui`. Tabs but an empty Investments tab: the tab's contents didn't load (error.log `pmr_methods_view` or `pmr_policy_block`) |
| B2 | Step 6 | The panel reopens on Buildings, with the normal search, filters and list | It reopens on Investments: the panel's closing didn't clear the tab, a nuisance only |
| P1 | Step 5's strips | Each reads "AI weight N x(priority)" and "Base 1000 +T from your average level's profit (£A a week) and output". T differs by type: large where A is high (paper mills, logging camps in q26), negative where A is negative (textile mills, shipyards), and N is 1000 + T but never below 100 | Every strip "+0" and "£0": the averages weren't counted (no `PMR;rec=PF` lines, row P2). N stays 1000 while T isn't 0: the term isn't added to the AI value (error.log `pmr_ai_pt`) |
| P2 | debug.log `PMR;rec=PF` | From 1 February, once a month, one line per building type you have: `levels=`, `avg=` (£ a level a week) and `term=`; term has avg's sign whenever avg is clearly positive or negative | No lines: the monthly count never ran (error.log `pmr_pf`); then the AI weights haven't changed either |
| E2 | error.log | No line naming `pmr_cc`, `pmr_pf`, `pmr_mv`, `pmr_company_culture`, `ingame_hud` or `building_browser_panel` | Any such line: that part never ran, and its rows above are not results |

## Earlier: Company Culture full-screen, lock reasons, charter buttons on the nodes (q27, test mod; a new game is needed)

From the build thread, after your 20:37Z feedback on q26:

- Clicking a company's Company Culture tab opens the wheel full-screen, like the tech tree: title, back arrow, close
  button, the Culture level and points under the title, and the wheel filling the screen (a tenth tighter than q26).
  The back arrow returns to the company panel, whose Company Culture tab now holds the level, an "Open Company
  Culture" button and the Methods list.
- The dashed gold ring and the "Node outline" legend are gone.
- Every node's tooltip opens with a red or green line saying why it is in its state: the technology it waits for, the
  tier before it, the charter node that opens it, its founding culture, Culture points, another research grant
  running, or ruled out by the opposed arm.
- The charter row at the foot of the company panel is gone. A bought charter node (Trade, Investment, Industry,
  Monopoly, Colonization) carries vanilla's charter button instead.
- The side Buildings list has a "Private Owners' Methods" button under Building Registry.
- Fixed: the months-to-next-point number was written into the Monopoly Charter's variable (`mo=-1` in your q26 log).
  q26 saves keep the wrong value, hence the new game.

1. Start a new game on the PMR Test playset as Prussia and unpause.
2. Take "PMR test: 6 Culture points for each of your companies" twice.
3. Open Krupp's company panel and click its Company Culture tab.
4. Hover Expansion and the steel mill's Works Method II. Click Engineering, then hover them again.
5. Buy the steel mill's Works Method I, take "PMR test: finish your companies' research grants", play two months, then
   hover the steel mill's Works Method II once more.
6. Click the back arrow, then the X. Open any other company.
7. Open the Buildings list from the left sidebar and click "Private Owners' Methods" under Building Registry.
8. Optional, for the charter buttons: establish a second company, take the points decision twice more, and on its
   wheel buy Expansion, Supply I and II, Stewardship, Company Housing, Model Dwellings and the Industry Charter.
9. Close the game and tell the build thread; it reads debug.log and error.log.

Rows C3 to C7, W1, W2 and H0 to H2 of the q26 section below still apply on this run; F1 and L1 replace C1 and G1.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| F1 | Click Krupp's Company Culture tab | A full-screen window over the map like the tech tree: "Company Culture: Friedrich Krupp" at the top, a back arrow top left, the X top right, the Culture level, points and bar under the title, and the wheel filling the rest with Krupp's seal in the middle. No gold ring, no legend. Drag pans, the mouse wheel zooms | Only the company panel's tab with the "Open Company Culture" button, and clicking it does nothing: the window isn't drawn. Either another enabled mod replaces `ingame_hud.gui`, or the game doesn't know the panel id `company_panel` (error.log "invalid panel type"). Tell the build thread which |
| F2 | Back arrow, then the X, then open another company | The back arrow shows Krupp's company panel on its Company Culture tab (level, "Open Company Culture", Methods). The X closes the window and the company panel together. The next company opens on its normal tab without the wheel | The wheel opens over every company panel afterwards: closing doesn't clear the window's switch (its `_hide`), a nuisance but not a blocker |
| L1 | Step 4: hover Expansion and Works Method II, before and after Engineering | Before: Works Method II reads "Locked: needs the Engineering founding culture." After: Expansion reads "Ruled out: this company holds Engineering." and Works Method II "Locked: needs (its tier I name) first." | A blank first line under the name: the reason's custom localisation didn't resolve (error.log names `pmr_cc_why`). "Locked." alone: no specific reason matched (tell the build thread which node) |
| L2 | Step 5: hover the steel mill's Works Method II after the grant | "Locked: waits for the technology Bessemer Process." | "needs (tier I) first" still: the grant hasn't completed (see C6). A blank technology name: the technology lookup didn't resolve |
| K1 | Look at the foot of Krupp's company panel | No charter row | The row still shows: the company panel patch didn't load (then F1 fails too) |
| K2 | Optional: the second company's bought Industry Charter node | A vanilla "Industry Rights" button inside the node card; clicking it opens vanilla's menu of buildings to target | No button on the bought node: the charter list or its Industry filter doesn't work inside the wheel. Charters then can't be taken anywhere in this build; tell the build thread |
| B1 | Step 7 | The Buildings panel opens on "Private Owners' Methods". Building Registry still opens on the normal Buildings tab | No second button: the side list patch didn't load. It opens the normal tab: the tab switch isn't read on opening |
| M1 | debug.log `PMR;rec=CC` lines | `mo=0` on every line until a Monopoly Charter is bought | `mo=-1` or any other number: the old months variable is still being written there |
| E2 | error.log | No line naming `pmr_cc`, `pmr_cw`, `pmr_company_culture` or `ingame_hud` | Any such line: that part never ran, and its rows above are not results |

## Earlier: the Company Culture wheel, research grants and the companies' special methods (q26, test mod; a new game is needed)

From the build thread (your 18:18Z "ok submit this to the build agent to construct", BUILD-SPEC.md). Each company's
Company Culture tab is now a wheel on the tech tree's backdrop: drag to pan, mouse wheel to zoom. Four arms sit on the
diagonals. Engineering and Expansion are opposed, as are Stewardship and Providence, and a company holds one of each
pair. Each pair of neighbouring arms shares a charter node halfway out (Trade = Engineering + Stewardship, Investment =
Engineering + Providence, Industry = Expansion + Stewardship, Monopoly = Expansion + Providence) with a synergy node
behind it. The dashed gold ring is the gate: nodes past it stay locked until the company holds a shared charter of that
arm. A vanilla charter can now be taken only by a company holding its node, and charters cost no authority.

Engineering's Works Method nodes are the company's special production methods, one line per goods-line building (Krupp:
steel mill and artillery foundry). Buying a tier starts a 24-month research grant, shown as a green bar; while it runs,
the company's buildings use 5% more input goods. When it ends, the company's levels of that building blend in the new
method: more of the main good (+15% / +25% / +40% by tier) for more of one input (+5% / +10% / +15%). Only the
company's share of the building's levels changes, and those levels fall back to the base method while that extra input
sits at the +75% price cap. Tier II and III appear once your technology has the building's second and third recipe.

Two test decisions save waiting: "PMR test: 6 Culture points for each of your companies" (repeatable) and "PMR test:
finish your companies' research grants", which completes every running grant at the next monthly tick.

1. Start a new game on the PMR Test playset as Prussia (Krupp owns steel mill levels in Westfalen) and unpause.
2. Take "PMR test: 6 Culture points for each of your companies" twice.
3. Open Krupp's company panel and its Company Culture tab. Click Engineering, then the steel mill's Works Method I.
   Hover the Westfalen steel mill's modifiers.
4. Take "PMR test: finish your companies' research grants" and play two months.
5. Back on Krupp's wheel, buy Safety Rules, Stewardship, Fair Wages and Living Wage.
6. Optional, for the charters: establish a second company, take the points decision twice more, and on that company
   buy Expansion, Supply I and II, Stewardship, Company Housing, Model Dwellings and the Industry Charter. Then open
   its charters.
7. Close the game and tell the build thread; it reads debug.log (`PMR;rec=CC`, `CC_BUY`, `CC_TEST`, `CC_TEST_GRANT`,
   `CC_GRANT_DONE`, `WORKS`) and error.log.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| C1 | Open Krupp's Company Culture tab | The tech tree's backdrop with Krupp's icon in a centre seal ("Choose a founding culture"), four arm titles on the diagonals, faint orbits, dotted links between nodes, a dashed gold ring, and a "Node outline" legend with five colours at the bottom left. Dragging pans, the mouse wheel zooms | The old list or a blank tab: the wheel didn't load, and error.log names `pmr_company_culture.gui`. Every node piled in one corner: the node positions didn't apply. No company icon: `AccessCompanyType.GetIcon` doesn't exist (cosmetic) |
| C2 | Hover and read a Works Method node | A yellow method name, a small yellow glyph of the building, a net line such as "+15% Steel for +5% Coal" and a grey "over the base … method" line | A solid yellow square instead of the glyph: the icon mask doesn't work on that widget (cosmetic). Blank good or method names: the nested custom localisation doesn't resolve |
| C3 | Take the points decision | A `CC_TEST` line per company of yours, each with `pts=` 6 higher; the tab's points go up by 6 | No `CC_TEST` line: the decision didn't run, so nothing below can be bought |
| C4 | Click Engineering | It turns gold at no cost. Expansion, every Expansion node and the Industry and Monopoly charters turn grey with a red warning. A `CC_BUY` line with `line=fe` | No change on click: the click never reached the script (no `CC_BUY`). Expansion still buyable: the opposed-pair rule failed |
| C5 | Buy the steel mill's Works Method I, then hover the Westfalen steel mill's modifiers | The node shows a green bar "Research grant 0 / 24 months" and `CC_BUY` has `grant=5/1/0`. The steel mill's input goods are up by Krupp's share of 5% (about +2% with Krupp at 2 of 5 levels) | No bar while `grant=5/1/0`: the grant state isn't drawn. No input increase: the grant trait isn't on Krupp's executive |
| C6 | Take the finish-grants decision, play into the next month | A `CC_TEST_GRANT` line with `grant=5/1/23`, then `CC_GRANT_DONE` with `g1=1` and `grant=5/1/24`. The node turns gold, the input increase goes, and the steel mill's methods gain "Company works output (n/40)" and "Company works input (n/40)" | No `CC_GRANT_DONE` after a full month: the monthly grant tick didn't run. Gold node but both shares stay at 0/40: see W1 |
| W1 | Play one more month | A `WORKS` line for each of your states where Krupp holds steel mill levels: `t1=` Krupp's levels there, `out=` t1 x 15 / level and `in=` t1 x 13.3 / level, rounded (Westfalen at 2 of 5: `out=6;in=5`), and `px_coal=` under 1.75 | No `WORKS` line: either the global switch wasn't set when the grant completed or the modifier read failed, and `CC_GRANT_DONE` decides which. `t1=0` everywhere: Krupp's tier trait isn't scaling onto the building. `out=0` with `px_coal=` 1.75 or more: the price-cap fallback, a pass |
| W2 | Open the Westfalen steel mill | Steel output up by about `out=`% (+6%) and coal input up by about `in=` x 0.375% (+1.9%) over the plain recipe | The two shares are listed but steel output doesn't change: unscaled goods modifiers don't work inside a production method |
| C7 | Buy Safety Rules, then Stewardship | Stewardship is buyable only once two Engineering nodes are done (Works Method I and Safety Rules) and costs 2 points; Providence then turns grey with the warning | Stewardship buyable before that: the reach rule failed |
| G1 | Buy Fair Wages and Living Wage, then look past the gold ring | `CC_BUY` lines with `fw=1` and `fw=2`. Profit Sharing and Works Method III stay locked past the ring. The Trade Charter stays locked: it needs Works Method II on the artillery foundry, which waits for Shell Gun | A node past the ring is buyable without a shared charter: the gate failed |
| H0 | Optional: after the second company's Supply I, hover one of its buildings that uses the good the node names | The building's modifiers show that good's input at about −5% times the company's share of the building, and the building's input of that good drops by the same amount | No such line: the per-good modifier type didn't load (error.log "Unknown modifier type"). The line shows but the input amount doesn't change: per-good multipliers on an executive only display, like the per-good `_add` ones |
| H1 | Optional: the second company's Industry Charter | Expansion is free, Stewardship costs 2 after Supply I and II, and the Industry Charter costs 3 after Supply II and Model Dwellings. Once it's bought, Supply III past the ring turns buyable | Industry Charter still locked with both nodes done: its needs failed. Supply III still locked after the charter: the charter doesn't open the gate |
| H2 | Optional: open the second company's charters | Industry Rights (vanilla's name for the Industry Charter) can be taken and costs no authority. Before the node it can't be taken | Industry Rights available before the node: the charter file patch didn't load. It costs 100 authority: the define didn't load |
| E1 | error.log | No line naming `pmr_cc`, `pmr_cw` or `pmr_company_culture` | Any such line: that part never ran, and its rows above are not results |

## Earlier: recipe and automation chosen as pairs, and the investment cards move to Private Owners' Methods (q25, test mod; a new game is needed)

From the build thread (your 18:36Z "yeah i want to split it"): the 15 building types that folded automation into their
recipes no longer do. Every recipe with every automation option is a retool target of its own, so new levels and
retooling follow the most profitable pair (a steel mill has 4 recipes x 3 options = 12 pairs, a coal mine 16). The
recipe bar shows the plain recipes again and the green bar under it shows the automation methods. Buildings start a
new game on their history recipe with no automation, so the green bar stays empty until a building retools onto a
pair with automation. Watertube boilers now get the same buff as the other automation methods.

Also from the build thread (your 18:40Z ask): the economic law and policy cards and the investment priorities have left
the Private tab and now sit at the top of the Buildings panel's "Private Owners' Methods" heading, and the policy window
opens under the cards. Each building row ends with an "AI weight" cell: what investors weigh that building by, and the
multiplier its investment priority slider gives it.

1. Start a new game on the PMR Test playset (a q24 save has no pairs) and play past 1 February 1836.
2. Open a steel mill and a textile mill and hover each one's "Most profitable" row.
3. Open the Buildings panel from the top bar, click "Private Owners' Methods", then click the policy card.
4. Open the Private tab.
5. Tell the build thread; it reads debug.log (`PMR;rec=PROFIT`) and error.log.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| S1 | Play past 1 February 1836 | Steel, textile and the other split types write PROFIT lines with `pick=` between 1 and the pair count, `pair=<recipe>x<automation>` (automation 1 = none) and one `rm=` figure per pair (12 on a steel mill) | `pair=0x0` with `pick=` above 0: the pair copy didn't run. Four `rm=` figures on a steel mill: an old build. No PROFIT lines at all: nothing logs |
| S2 | Look at a steel or textile mill's recipe bar | The bar names plain recipes only (no "+" in a slice's name); the green bar under it is empty or shows automation methods | A slice named "Recipe + Automation": the bar reads per-pair shares instead of per-recipe ones. Recipe slices that don't add up to the building's levels: the recipe sums (`pmr_rs`) are wrong |
| S3 | Hover the "Most profitable" row | A pair such as "Blister Steel + Watertube Boiler" or a plain recipe, with its £ per level a week matching the building's PROFIT line for the same `pair=` | A different pair from the PROFIT line: the row reads a stale pick |
| M3 | "Private Owners' Methods" heading | The law card and policy card on the left and the investment priorities on the right, above the building rows; clicking the policy card opens its window under the cards | No cards: the block didn't load. The window never opens, or opens over the map: the card's click and the window's visibility test disagree |
| M4 | Same heading, each building row | An "AI weight" cell: a number, `x` and the priority multiplier (x1.00 with every slider at its default), and the priority group's name; hovering explains it | 0 on every row: the AI values weren't copied when the tab opened. x0.00 on every row: the priority multiplier didn't evaluate |
| M5 | Same heading, a steel or textile mill row | A grid with a column per recipe and a row per automation option, gold behind one cell that matches that building's `pair=` in the state with the most levels | Gold on a different cell: the grid and the retool pick disagree |
| P1 | Private tab | No law card, policy card or priorities; the construction queue follows the sections above it | The cards are still there: an old build |
| S4 | Play a year or more (optional) | A mill's PROFIT line picks a pair with automation (`pair=<r>x2` or higher) once its `rm=` is the highest runnable figure, and its green bar starts to fill | An automation pair with the highest `rm=` and `can=1` that is never picked: the pick ignores pairs. Every pick stays on automation 1 while those pairs earn less: expected at 1836 wages |

## Earlier: profit figures at market prices, and Private Owners' Methods moves to the Buildings panel (q24, test mod; a new game is needed)

From the PM rework thread (dev dce666b, your 18:15Z screenshot): in q23 the profit pick was worked out during game
setup, before the market had prices (steel read 0.25-0.35 of base), so the Alsace-Lorraine steel mill showed Blister
Steel at £-2990 a level a week while it earned +1.57K. Each building's pick is now worked out again on its first
monthly pulse, at market prices, and that pass writes the `why=first_month` line.

Also from the PM rework thread (dev 3944076, your 18:17Z ask): "Private Owners' Methods" has left the Private tab. The
top-bar Buildings panel (not a state's Buildings tab) now has two tab headings, "Buildings" and "Private Owners'
Methods". The second shows each building type's recipe row and, for the 15 types that fold automation, a grid: a
column per recipe, a row per automation option, £ per level a week in each cell, gold behind the best pair and faded
cells for pairs that can't run. Retooling still follows the folded recipes.

1. Start a new game on the PMR Test playset (a q23 save keeps its setup-time picks) and play past 1 February 1836.
2. Open the Alsace-Lorraine steel mill (or any steel mill) and hover the "Most profitable" row.
3. Open the Buildings panel from the top bar and click the "Private Owners' Methods" heading.
4. Tell the build thread; it reads debug.log (`PMR;rec=PROFIT`).

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| A2 | Play past 1 February 1836 | `why=first_month` PROFIT lines whose `px=` shows market prices: tools about 1.2-1.6, iron about 1.6, steel well above 0.35 | Steel still 0.25-0.35 in every state: the first-month pass didn't recompute (`pmr_pmkt_<b>`) and the setup pick stands. No PROFIT lines at all: nothing logs |
| A3 | Hover the steel mill's "Most profitable" row after 1 February | Blister Steel positive, roughly +£850 a level a week at May 1836 prices, with the same figure as the building's PROFIT line | Still £-2990: the panel reads the setup-time numbers |
| M2 | Buildings panel (top bar), "Private Owners' Methods" heading, after 1 February | Each building type's recipe row; a steel or textile mill also shows the recipe x automation grid with gold behind one cell and some cells faded | No second heading: the panel patch didn't load. Every £ reads 0: the picks haven't been recomputed yet (before 1 February) or the heading wasn't clicked. The Private tab still shows the section: an old build |
| A4 | Play past 1 February 1836 | PROFIT lines for steel mills, textile mills and the other types that fold automation carry `pair=<recipe>x<automation>` and `cp=` | No `pair=` on those lines: the pair profit effect didn't load |

## Earlier: the profit pick logs itself, and private owners' methods on the Private tab (q23, test mod; a new game is best)

From the PM rework thread (dev 0bda5cf and f031724, your 17:59Z and 18:00Z messages).

- **The profit log needs no console step.** Each of your buildings writes a `PMR;rec=PROFIT` line on its first
  monthly pulse (`why=first_month`) and again whenever its pick is recomputed (`why=recompute`): after research, a
  new building, or the yearly re-check.
- **"Private Owners' Methods" on the Private tab**, under the priorities: one row per building type you have, the
  £ per level a week under each recipe, and a gold square on the recipe the manor houses and financial districts
  pick.

1. Start a new game on the PMR Test playset and play past 1 February 1836.
2. Open the Private tab and scroll below the priorities.
3. Tell the build thread; it reads debug.log (`PMR;rec=PROFIT`).

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| A1 | Play past 1 February 1836 | `PMR;rec=PROFIT` lines with `why=first_month`, one per building of yours, each with `to=`, `newest=`, `pick=` and an `rm=` per recipe | No PROFIT lines by 1 February 1836: the pick isn't computed or logged |
| M1 | Private tab, below the priorities (replaced in q24 by M2: the section moved to the Buildings panel) | "Private Owners' Methods": a row per building type you have, £ under each recipe, a gold square on the pick | Section empty: the view isn't refreshed when the tab opens (`pmr_mv_refresh`). Every £ reads 0: the per-state values (`pmr_level_<b>`, `pmr_rm`) weren't found |

## Earlier: each building shows its most profitable recipe (q22, test mod; your current save works)

From the PM rework thread (dev 8cea159, your 17:49Z question): a row under the recipe bar on every PMR building's
details panel reads "Most profitable: <recipe>, £ per level a week", with a tooltip listing every recipe's profit.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| P1 | Open any PMR building (a textile mill, a steel mill, a farm) | The row shows a recipe name and a £ figure; its tooltip lists each recipe's profit | No row: the panel patch didn't apply. "Most profitable: , £0": the pick (`pmr_pbest_<b>`) is not set for that building |

## Earlier: new builds and retooling follow the most profitable recipe, and a green automation bar (q21, test mod; a new game is best)

From the PM rework thread (dev 0167f30, your 17:14Z message): a building's target is no longer simply the newest
recipe it can run. Each recipe is valued per level per week at the state's prices, with wages at the 1836 reference
rate, and the target is the most profitable one that can run. A recipe that would need more of an input already at
the +75% price cap is ruled out. Like vanilla, a newer recipe has to beat the current pick by 5% of its margin and an
older one by 25%, so the target can step back down. It is worked out only at game start, when research or a new
building changes what can run, and on a staggered yearly re-check; every other tick reads the stored pick.

From q23 the `PMR;rec=PROFIT` lines log on their own (see Latest above); the console step is gone.

| Result | Meaning (decided before the run) |
| --- | --- |
| `PMR;rec=PROFIT` lines for your buildings, each with `to=`, `newest=`, `pick=` and an `rm=` margin per recipe; `pick` is the recipe with the best `rm` among those with `can=1` and `veto=0`, allowing for the stickiness | **Works.** The profit pick is computed and stored |
| No `PMR;rec=PROFIT` line by 1 February 1836 (q23 on) | A real bug: the pick isn't computed or logged |
| `pick=0` on buildings that clearly run | No recipe counted as runnable or every one was vetoed; send the line |

**Also in q21: a green automation bar** (dev f860857, your 17:15Z ask). On the 15 building types whose recipes fold in
automation, a second bar sits under the recipe bar in the building's details panel: pale green for levels on recipes
below tier 3, darker the more automated, darkest for the most. Its tooltip names vanilla's automation methods with
the share of levels on each.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| G1 | Open a Steel Mill or Textile Mills building | A second bar sits under the recipe bar, pale green on an 1836 building (no automation yet), and its tooltip lists the automation methods with percentages adding to 100% | No bar: the panel patch didn't apply. A bar that is always empty or a tooltip at 0% everywhere: the shares (`pmr_ash`) are never set, so `pmr_mix_<b>` didn't run |

## Earlier: who owns each level of a building (q20; answered 2026-10-18 16:52Z: Krupp 2, government 3, others 0)

What q19 answered (2026-10-18): a company's executive trait lands on each building scaled by the company's share,
and script reads it (Krupp's 2 of 5 Westfalen steel levels read `marker=0.400`, `company_levels=2.00`). A trait's
engines input shows in the Modifiers tab only and is not a real input or demand.

q20 adds the rest of the split you asked for (16:14Z), from the Company Culture thread. Each `PMR;rec=WSP` line
now names its state and building and adds `gov`, `private` and `self`: the building's government, private and
self-owned fractions, to the nearest 0.05 at or below (-1 = that trigger never held). The probe is still on in your
save; in a new game take the decision again.

1. Load and let one month pass.
2. Filter debug.log for `PMR;rec=WSP` and find the Westfalen Steel Mills line.

| Result | Meaning (decided before the run) |
| --- | --- |
| Westfalen steel: `marker=0.400`, `gov=0.6`, `private=0.4`, `self=0` | **Works.** Krupp 2, government 3, financial districts and manor houses 2 - 2 = 0: the split is definitive |
| `private` minus `marker` is not 0 on a building whose ownership tooltip shows no financial district or manor | Companies don't count as private; see whether `self` or foreign owners make up the gap |
| `gov` + `private` + `self` isn't 1 where there are no foreign owners | One of the fractions means something else; compare with the ownership tooltip |
| Any field -1 | That trigger doesn't read on this building |
| `state=` or `building=` empty or ERROR | The names are still broken; the numbers still count |

## Earlier: Company Works share probe (q19; answered 2026-10-18 16:10Z, above)

One addition since q18, asked for in the Company Culture thread (2026-10-18 15:35Z and 15:42Z). It is a test-only
probe with two questions. First, can a building read how much of it your companies own, through an executive trait?
If it can, Company Works can blend a company's special method in proportion to that company's own levels. Second,
can an executive trait add an input the building's methods don't use? If it can, the special method could sit on
the trait itself. While it is on, your companies' buildings may take 5 engines a week as an extra input.

- A new building modifier, `building_pmr_works_probe_marker`, that nothing else uses, set to 1 by a hidden
  executive trait ("Share Marker (probe)").
- A second hidden executive trait, "Engine Input (probe)", carries `goods_input_engines_add = 5`.
- A decision, **PMR probe: company share marker (on/off)**, gives both traits to every company of yours (English
  text in every language). Taking it again removes both.
- Each monthly pulse, every building of yours reads the marker: a `PMR;rec=WSP` line for each building that reads
  non-zero, and one `PMR;rec=WSP_SUM` line that always prints, counting `executives` (share trait),
  `input_executives` (engine trait), `buildings` and `nonzero`.

Steps (PMR Test playset, new game or any save):

1. Load the game. Check error.log for `pmr_wsp` or `building_pmr_works_probe_marker` before anything else.
2. Take the decision. debug.log shows `PMR;rec=WSP_ARM;arm=ON`.
3. Let one month pass.
4. Pick a building one of your companies part-owns, ideally with only one company among its owners. Note the
   company's levels and the building's total level from its ownership tooltip.
5. Hover the building's modifiers. The probe marker should appear with a value.
6. Find that building's `PMR;rec=WSP` line in debug.log (filter `PMR;rec=WSP`).
7. Take the decision again to switch the probe off.

| Result | Meaning (decided before the run) |
| --- | --- |
| `marker` equals the companies' share (5 of 20 levels gives 0.25) and `company_levels` equals their levels | **Works.** A building can read its company share; Company Works can size its share from the executive trait |
| `marker` = 1 on part-owned buildings | The engine applies executive modifiers unscaled; the share can't be measured this way |
| `WSP_SUM` shows `executives` > 0 and `nonzero=0`, no error, but the tooltip in step 5 shows the right share | The marker is applied, but script can't read it on a building |
| Same as the row above, but the tooltip shows nothing either | The trait never reached the buildings; check the executive has "Share Marker (probe)" |
| An error.log line naming `modifier` in pmr_wsp_effects.txt | Building scope has no `modifier:` link |
| No `WSP_SUM` line a month after taking the decision | The monthly hook didn't run: a probe bug, not an answer |
| `executives=0` | No company of yours has an executive, or the trait wasn't added: a probe bug, not an answer |

If two companies of yours share one building, its marker is their combined share; use a building with a single
company owner for the clean check.

**Second question: can an executive trait add a new input?** Do these after step 3, in the same month:

1. Pick a company-owned building whose production methods use no engines, such as a farm, a logging camp, or a mine
   on its first method.
2. Open its goods breakdown (inputs) and its modifier tooltip.
3. Open the engines market and look at where its demand comes from.

| Result | Meaning (decided before the run) |
| --- | --- |
| Engines appear as a real input of the building, sized to the company's share (or levels), and show in engines demand | **Works.** A trait can add an input, so the special method can be a trait. Note the number to see how it scales: 5 × share, 5 per level, or a flat 5 |
| The modifier tooltip shows "+5 engines input", but the building's inputs and engines demand don't change | The modifier lands but the economy ignores it (the expected null: a building static modifier behaved the same in earlier tests). The special method then has to be a real production method, a blend share |
| Nothing anywhere, while `input_executives` > 0 in `WSP_SUM` | executive_modifier doesn't carry `goods_input_<g>_add`; same consequence as the row above |
| `input_executives=0` | The trait wasn't added: a probe bug, not an answer |

On a building that already uses engines the input rises by the same amount; read the clean case on a building with
none. If both fail, the fallback is to count the levels the company's retool site converted.

## Still to check from q18: automation pays for itself (a new game shows it from the start)

New since q17, from `dev` in prob32/ProductionMethodRework (q18 also carries q17's translations, below):

- **Every automation method is cheaper (your 14:48Z ask).** At 1836 wages vanilla's automation lost money: it saves
  1,000 to 3,000 laborers at about GBP 0.04 a week each, against goods that cost far more. Each automation method
  now needs fewer goods (6 to 24% of vanilla's) and removes half as many workers again, so it pays even with its
  inputs at +75% of base price. This applies wherever the automation sits: folded into a recipe from tier 3,
  the electric recipe, or kept as its own group. Company Culture's tier sizes shift a little, as they are worked
  out from the blends.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| B1 | Open a Steel Mill whose levels all run Open Hearth Process (tier 3), and hover its coal and tools inputs and its employment | Each fully staffed level takes coal 30.8 and tools 0.4 (the totals scale with levels), and the jobs are machinists and engineers, no laborers | Coal 40 and tools 5 a level, or laborers listed: the automation buff is not in this build; check that the Queue Test folder's `RUNSHEET.md` starts with "automation pays at 1836 wages" |
| B2 | The earliest place to see it: a Textile Mill whose levels all run Sewing Machines (tier 3; needs Mechanized Workshops). Hover its tools input and employment. Not testable in 1836: no country starts with the tech, and the tech tooltip lists Sewing Machines, not Mechanized Looms, because PMR folds the looms into that recipe, whose own method carries no numbers | Each fully staffed level takes tools 6.2 and 1,250 laborers | Tools 10 and 2,000 laborers a level: the buff is not in this build |

## Earlier: PMR's text in every game language (q17; you checked it in Chinese on 2026-10-18 15:39Z)

From `dev` in prob32/ProductionMethodRework:

- **PMR is translated (#3).** All of PMR's text now reads in the game's language: Brazilian Portuguese, French,
  German, Japanese, Korean, Polish, Russian, Simplified Chinese, Spanish and Turkish. Each uses the game's own
  words for its terms (investment pool, retooling, building level, throughput...). PMR's own word for a building's
  main production method is a short "recipe" word in each language (Chinese 配方, German Rezept, French procédé).
  The translations are drafted, not proofread by native speakers. Policy cards are sized for each language's text,
  so the policy windows are a little taller.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| L1 | Set the game to Chinese, load, open a mine's building panel, hover its recipe bar, then open the Private construction tab | PMR's text in Chinese: the recipe bar tooltip, the tab's headers, priorities and charts. No English sentences, no `PMR_` keys | An English line: that line has no translation yet (send a screenshot). Raw `PMR_` keys: the language files didn't install; check `localization\simp_chinese\pmr_l_simp_chinese.yml` in the Queue Test folder starts with Chinese text |
| L2 | Still in Chinese, on the Private tab click Add Policy | Every card's name, benefits and authority cost sit inside the card | Text under a card: the height estimate is short for that language; send a screenshot |
| L3 | Optional: the same panels in German or French (their text runs longest) | Text inside its boxes; a narrow chart legend may end in "…" | Text running out of a box or over another: send a screenshot |
| A1 | Whenever you research Baking Powder before Dough Rollers | No `PMR;rec=RESEARCH` line for `building=building_food_industry` with `best=3` until you also have Dough Rollers; then one appears | A `RESEARCH` line with `best=3` before Dough Rollers: the gate didn't take. Check `error.log` for `pmr_best_food_industry` |

## Earlier: every game language, and automation waits for its technology (test mod; your current save works)

Four changes since the Company Culture build (q14), from `dev` in prob32/ProductionMethodRework:

- **Every game language (#3).** The test build now carries PMR's text in all 11 game languages, the English text in
  each, as the release always has. Your Chinese screenshots of 2026-10-18 showed raw `PMR_` keys because q14 shipped
  English only.
- **Automation waits for its technology (#10).** From the third recipe on, a recipe carries its building's
  automation. It now becomes a building's target only once the country has also researched that automation's
  technology: Baking Powder waits for Dough Rollers (the Automated Bakery), the mines' Condensing Engine Pump for
  Steam Donkey and Railways, steel's Open Hearth for the Rotary Valve Engine, and so on (25 recipes on 15 building
  types). Buildings already running such a recipe keep it.
- **The foreign buy-in probe is gone** (you dropped the idea on 2026-10-14), with its log lines and decision.
- **Policy cards fit every language (q16, #3).** In Chinese, Focus on Infrastructure's authority cost spilled under
  its card: a Chinese, Japanese or Korean game draws PMR's English text about a third wider. The cards are now sized
  for that font, so in English they keep a little room at the bottom.

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| L1 | Set the game to Chinese (or any language but English), load, open a mine's building panel and the Private construction tab | PMR's text in English, no `PMR_` keys | Raw `PMR_` keys: the language files didn't install. Check that the Queue Test folder has `localization\simp_chinese\pmr_l_simp_chinese.yml` |
| L2 | Still in Chinese, open the Private tab and click Add Policy | Every card's authority cost sits inside its card | A cost under its card: the card height estimate is still short for that font; send a screenshot |
| A1 | Whenever you research Baking Powder before Dough Rollers | No `PMR;rec=RESEARCH` line for `building=building_food_industry` with `best=3` until you also have Dough Rollers; then one appears | A `RESEARCH` line with `best=3` before Dough Rollers: the gate didn't take. Check `error.log` for `pmr_best_food_industry` |

## Earlier: Company Culture, a trait tree on every company (test mod; a new game is best)

Built from your answers of 2026-10-14 04:00Z, changed at 12:37Z: **no queue** (a click spends points already
earned), **no In Force list** (bought tiers carry a gold frame instead), and every company's tab is filled from the
first day. Every company's panel has a fourth tab, **Company Culture**:

- **Points.** Each month a company earns its prosperity times its size (x1, plus a tenth per 5 employed levels, at
  most x2). A full bar is one point and one Culture level; each level costs more (800 for the first, then
  100 x (level+1)^1.8 + 700). Expect roughly a point a year early on, so a test decision hands out points (item 3).
- **Three columns, tiers costing 1, 2 and 3 points.** Equipment (Refined Process I-III): fewer input goods on every
  level the company owns. People (Skilled Workforce I-III): fewer laborer jobs, one engineer job for every four
  laborer jobs cut, so 3 / 6 / 10% fewer jobs in all. Scale (Expanded Works I, II, Mass Production): +5 / +10 / +20%
  throughput. The first Equipment or People tier bought locks the other column. No charter bonus.
- **Clicking.** Only a column's next tier can be clicked, and only when the company has the points ("Buy: 1 point").
  Without them it reads "Needs 2 points" and does nothing. A bought tier gets a gold frame and reads "Bought".
- **Matched per company on productivity.** Each Equipment tier raises a level's productivity as much as the People
  tier beside it (+3.1 / +6.4 / +11.1%) at base prices, so the input cut is company by company (-1.3% at Refined
  Process I for a steel firm, -5.6% for a plantation). Where inputs are so cheap that the cut would pass 20%
  (58 of 221 companies, mostly plantations), Equipment gains less. Table: `/mnt/project-files/pmr/mio/calibration.md`.
- **AI companies** earn and buy on their own, their column chosen from their inputs (People where inputs are small
  against value added), a quarter of the time the other one.
- **Methods**: every recipe of the company's building types, greyed until researched, the newest you can run framed
  in gold, and under each the share of your levels running it.
- Bonuses are hidden traits on the company's executive; the game applies them to the levels the company owns, in
  proportion on part-owned buildings (the Hudson's Bay test, 03:51Z). A disbanded company loses them; a new
  executive gets them within a month.

**Setup.** Same playset, only **Production Method Rework (Queue Test)**, updated in place. Start a **new game as
Great Britain** (your save from this morning loads too; see item 1). Log lines: `PMR;rec=CC` in debug.log, your
companies only.

1. **The tab is filled from day one.** Open the Hudson's Bay Company, then the East India Company, switching between
   them with the tab left open: each shows "Culture Level 0", a bar at 0 / 800 and its tree, with no month passed.
   In this morning's save a company not yet read shows one button, **Show Company Culture**; clicking it brings up
   the tree. **"0 / 0" anywhere:** can't happen any more, so send a screenshot. **The tree is missing in a new game
   (only the button shows):** the game-start hook didn't run; send error.log lines with `pmr_cc`. **The button does
   nothing:** its script failed; same lines.
2. **Points come in.** After the first 1st of a month: "+N a month, next point in about M months" under the bar.
   debug.log has one `PMR;rec=CC;` line a month per company of yours (`rate=`, `funds=`). **No CC lines at all:**
   the monthly hook never ran; send me error.log lines with `pmr_cc`. **Lines with rate=0 while the company's
   prosperity (Overview tab) is above 5:** the prosperity read is wrong. A company at prosperity 0 earning nothing is
   expected.
3. **Buying.** Before the decision, every tier I reads "Needs 1 point" and clicking it does nothing. Take the
   decision **PMR test: 6 Culture points for each of your companies**: each tab shows 6 points to spend and the tier
   I nodes read "Buy: 1 point". Click **Skilled Workforce I**: it gets a gold frame and reads **Bought**, the points
   drop to 5, a `PMR;rec=CC_BUY;...line=pp` line appears, and the whole Equipment column reads "Ruled out by People"
   and can't be clicked. **Nothing happens on click:** the button's script refused; tell me what the node said
   before you clicked. **Bought but no frame:** the frame failed to draw; send a screenshot.
4. **The bonus reaches the buildings.** Open a building the company owns and hover over its employment and its
   inputs: an "Executive Trait" line for the tier, as in the Hudson's Bay test (laborer jobs down, engineer jobs up
   for People; input goods down for Equipment; throughput up for Scale). A building the company doesn't own is
   unchanged. **No line but the CC_BUY line is there:** the trait didn't reach the executive; open the executive's
   character window and tell me whether the trait shows.
5. **Not enough points.** Buy Skilled Workforce II and Expanded Works I (5 points down to 2). Skilled Workforce III
   now reads "Needs 3 points" and clicking it does nothing; Expanded Works II reads "Buy: 2 points". **Skilled
   Workforce III can be bought with 2 points:** the price check is wrong; send the CC_BUY lines.
6. **AI companies.** Play on a few years (or run as observer), then open some foreign companies' tabs: levels above
   0 and some tiers framed, People mostly for farms, mines and plantations and Equipment mostly for factories and
   shipyards. **All still at level 0 with full bars:** AI buying is broken; **bars empty after years:** AI companies
   don't earn.
7. **Methods.** In the tab's Methods list, each of the company's building types shows its recipes oldest to newest:
   unresearched ones greyed, the newest you can run in a gold frame, your share of levels under each. **A building
   type with no row:** PMR doesn't retool it (3 types, said in the row).
8. **No errors.** error.log has no line with `pmr_cc` or `pmr_company_culture`.

## Latest: one retool site per building with a paid crew, so investors can add levels (test mod, new game)

Third round of the queue test, after your call on 2026-10-14 that retooling must stay with investors. Investors
pick retooling exactly as in 0.1.0: the building's own score x2, your priorities, Focus on Infrastructure, and
funding like any other investment. PMR queues nothing itself any more. Two things differ from 0.1.0:

- **Two sites per building, not five:** one at home and one abroad (your 02:33Z call, item 5). That is the speed
  gain: the AI keeps a record per country for every building type, and the extra sites were most of them.
- **A paid crew on that site.** The game adds a level to a building that already stands only if it employs 80% of its
  jobs or hired last week (read in the 1.14.5 code behind `ai_evaluate_autonomous_construction`). A site had no jobs,
  so Jamaica's said NO. Now each site level employs 10 laborers and makes 0.1 services a week to pay them, and the
  site stays while it is staffed, so investors can queue more levels on it.

Also fixed: round 2's Market Liberal file was missing its last brace.

Also changed (your 01:53Z call): Focus on Infrastructure multiplies retooling by up to **3** at a full priority, not
100, so a far more profitable new build can still beat retooling.

Also new (your 01:54Z ask): the retool sites no longer show in a state's **Buildings** tab, in the grid or the list
view. They are still real buildings: their **Retooling: X** entries stay in the construction queue and their
laborers still count as employed. PMR now also replaces the game's state Buildings tab file.

**Setup.** Same playset, only **Production Method Rework (Queue Test)**; its folder was updated in place. Start
a **new game as Great Britain** (the site types changed). Play to 1 January 1837, save, quit and tell me; I read
the log and the save myself.

**Observer run (your 02:46Z call).** With no player country, PMR writes no `PMR;rec=` lines (they cover the
player's states only), so an empty filter is expected, not a failure. Item 5 can't happen either: the abroad site
opens only for levels the player owns abroad. Items 1, 3, 4 and 6 are read from the save, item 7 from error.log.

1. **Investors pick retooling.** By mid-1836 your **Private** queue holds **Retooling: X** entries among
   investors' new buildings, as in 0.1.0. **None by July:** investors never pick the one site. Send me a
   screenshot of the Private tab.
2. **The crew, then more levels.** PASSED 01:48-01:54Z: East Anglia's staffed site said YES and stood at 1+1. From
   this build the site is hidden from the Buildings tab, so check it from the queue and the console. Once a site's
   first level lands, it hires 10 laborers within a few weeks. Then run
   `ai_evaluate_autonomous_construction building_pmr_retool_<building>_1 STATE_<STATE>` on it: **Should construct:
   YES**, and later two or more levels on it, or `queued_priv=2`+ on its `PMR;rec=` line. **Crew stays at 0:** it
   can't afford to hire or finds no laborers; hover over its employment and send me the tooltip. **Staffed but NO:**
   the employment rule isn't the only gate.
3. **No red crosses.** A cross on a waiting **Retooling** entry: the game re-checks it and counts the entry
   against its own cap (vanilla's trade centres use the same check). Hover over it and send me the tooltip.
4. **Levels land.** Bars move a level at a time. The site stays while its crew is staffed and goes once its
   building has nothing left to retool (or its crew is still short 90 days after its last level). **Null:** a
   Retooling building standing after its building is fully retooled.
5. **Abroad.** Your 02:33Z call: your own investors retool levels you own abroad. Where you own levels abroad the
   site is now its own type, `building_pmr_retool_<building>_2` (home stays `_1`), and your investors weigh it
   like any foreign investment. Check: `ai_evaluate_autonomous_construction building_pmr_retool_coal_mine_2
   STATE_WEST_BENGAL` should show **Foreign investment factor: x1**, not x0, and a score above 0. Within a few
   months, expect a **Retooling: Coal Mines** entry in West Bengal in your Private queue. **x0 again:** the abroad
   group's foreign weight didn't apply. **x1 but never queued by 1838:** the AI's one-state-per-type pick still
   lands somewhere your investors can't build. Send me the console output.
6. **The save.** I count the AI's retool records: about 55% of 0.1.0's at the same date (180 retool types, not 315). **The same count as
   0.1.0** means the published mod was loaded, not the test one.
7. **Market Liberal.** I read error.log for lines naming `ideology_market_liberal` or `zz_pmr_market_liberal`.
   **A line there** means the game doesn't accept the replace for ideologies.
8. **Timing (optional).** Time 1 Jan 1836 to 1 Jan 1837 at speed 5 with a stopwatch, once with only the
   published mod and once with only the test mod, each from a new game. **No speed-up while item 6 passes**
   means the retool sites weren't the drag; the share blend itself is (performance review 2, section 3).
9. **Hidden from the Buildings tab.** PASSED 02:46Z (no tile, no gap). Open a state with a **Retooling: X** entry in the queue that has landed a
   level (the Private tab or the queue's location filter finds one) and look at its Buildings tab in both the grid
   and the list view (the toggle top right). Expect no **Retooling: X** tile or row, and every other building as
   before. **The site still shows:** the filter didn't apply; send me error.log lines naming
   `states_panel_buildings`. **The tab is empty or broken:** the game rejected PMR's copy of the file; same
   lines, and tell me at once. **An empty cell before the + tile:** the game places that tile by counting
   hidden sites too. That's cosmetic, but tell me.

What changes for play: nothing in how investors choose retooling. A building's private retooling in a state
runs on one site that can hold several levels, where 0.1.0 had up to four sites of one level each. Government
retooling and the upgrade button are unchanged. The Workshop update will need a "start a new game" note.

## Latest: your investors retool abroad, and companies own their additional industries' retooling (your current save works)

The release build writes no `PMR;rec=` lines, so these are read in the game's own panels. Load
`autosave_exit` (January 1841, Great Britain) and keep Strongly Foreign, Resources at the top and Focus on
Infrastructure as they were.

1. **Retool sites abroad appear.** Run 3 months at any speed. The AI looks at each building type again
   about once a month, so give it that long. Then open West Bengal's buildings (or the construction queue
   with the location filter on India): expect **Retooling: Coal Mines** or **Retooling: Iron Mines** there,
   or in Madras, Agra, Central Provinces or Gujarat (iron, textile, fishing). Your Private queue should show
   some of them beside the home coal mines.
   - A site there that **isn't** in your Private queue was built by the East India Company's own
     investors. The game checks the host's investors before yours, so they may now retool there too. Your
     levels get retooled either way; tell me if you want them kept out at the cost of slower retooling.
   - **What a null means:** after 3 months, no retool site anywhere in India, and your queue still holds
     only home coal mines. Then the fix did not take. Send me the newest autosave; it records each building
     type's chosen state.
2. **The West Bengal coal mine** (2 levels yours, 2 your investors'): the investors' 2 levels should reach
   your newest recipe once its site completes. Its bar then shows them on the newest recipe. A null here is
   the same as in item 1.
3. **The East India Company panel**: Available Industries gains four icons, Silk and Sugar Plantations twice
   each (home and abroad retooling), whether or not you chartered them. 1.14.5 gives script no way to read
   the charter's choice, so a company lists its additional industries' retooling all the time. **Null:** the
   same ten icons as before means the company files did not load; check `error.log` for `company_types`.
4. **Speed**: nothing to see. Four small savings, none changing what happens in game: a building with nothing
   to retool skips the retooling cleanup, and the release build drops checks that only fed log lines.

## Latest: a building targets the newest recipe you have, and the Foreign or Domestic bar counts (your current save works)

From your 22:07 and 22:09 messages. A building used to keep the recipe it ran when PMR first saw it (game start, or
the coal mine your government built in West Bengal) as its target until the next recipe was researched, so new levels
arrived on Picks and Shovels and the upgrade button had nothing to queue. Now, at every 1st of the month, a building
whose target is behind the newest recipe its owner can run moves its target there. Expect a wave of retooling in the
first months of any game, yours and the AI's: every building behind its owner's technology now has levels to retool.
This build also carries the power plant change (item 4 of the next section). The release build writes no PMR log
lines, so every check here is something you see. Wait for the next 1st of the month after loading.

1. Open the West Bengal coal mine. **Expect** the line above the bar to read "0% on Atmospheric Engine Pump" (or
   your newest mine recipe), the bar still all Picks and Shovels, and the upgrade button lit with a tooltip of 2.
   **Null:** the line still reads Picks and Shovels: the monthly tick never moved the target; check error.log for `pmr_` and tell
   me. Name moved but the tooltip says 0: PMR doesn't read those two levels as your government's; send the Owners list.
2. Click it. **Expect** 2 levels of "Retooling (Government): Coal Mines" in West Bengal in your government queue.
   **Null:** the tooltip says 2 but nothing is queued or the button is grey: the game won't let your government
   expand there (the open question from the section below).
3. At home, open any building of yours on an older recipe than you have researched (a mine on Picks and Shovels in
   Britain). **Expect** "0% on" the newest recipe above the bar, the upgrade button lit for government levels, and in time
   "Retooling" sites from investors for the private ones. **Null:** the name doesn't move: same as 1.
4. Expand a building that is behind (any of the above). **Expect** the new level to arrive on the newest recipe: a
   new slice on the right of the bar. **Null:** the bar's old recipe grows by a level: new levels still take the old
   target; tell me which building.
5. Foreign or Domestic bar (your 22:14 message). It was working but far too weak: each notch added what £1 a worker
   a year of profit adds to a score, so Strongly Domestic moved a typical building by a few percent and the random
   roll hid it. Now a notch multiplies the weight of every building in your states: ⅓, ½, ⅔ toward Foreign, 1.5, 2,
   3 toward Domestic. Your save is on Strongly Domestic already. **Expect** within a few months the private queue's
   new entries almost all in your own states (Malabar and Hindustan tea and opium were 3 of 7 in your screenshot).
   **Null:** still around a third abroad after three months: the weight doesn't reach the game's score; tell me.
   Recent Investments counts from the start of the game, so its Domestic share moves slowly; judge by the queue.
6. Click a different notch. **Expect** you can still change it for 7 days, then the notches turn transparent and
   their tooltip says "Changed recently" with about 14 weeks left, as the priority rows do. **Null:** still
   clickable after 7 days: the lock didn't take.

## Latest: Arts Academies and power plants retool, Urban Centers run their best methods (your current save should work)

From your 21:39, 21:51 and 22:01 messages. Arts Academies and power plants are PMR buildings now: an academy's art
(Traditional, Realist, Photographic, Film) and a power plant's recipe (Early, Coal-Fired, Oil-Fired) retool level by
level like a mine, your upgrade button for government levels and investors for the rest. An academy's patronage
runs its best (Independent Artists once Realism is researched). Urban Centers retool nothing: every group runs its best method automatically, at no cost, and their method icons are hidden like the
administration's. Gas Streetlights need no technology, so every Urban Center lights with gas, buying coal; Arcades and
Electric Streetlights run only in states that produce electricity. The release build writes no PMR log lines, so
every check here is something you see. Wait for the next 1st of the month.

1. Open London's Urban Center. **Expect** coal in its inputs (Gas Streetlights), engines if you have Railways
   (Trams), and glass with wood or steel (Market Squares or Covered Markets, by your technology). **Null:** no coal:
   PMR's monthly switch didn't reach Urban Centers. Check error.log for `pmr_auto_urban_center` and tell me.
2. Open an Arts Academy (Britain has one with 3 levels). **Expect** the recipe bar beside the employment bar on
   Traditional Art, and the patronage method's workforce: academics 2,000 a level once you have Realism.
   **Null:** the vanilla method icons still show and no recipe bar: the panel didn't take the new building type.
3. With Realism researched, the Arts Academy's target is Realist Art: **expect** a "Retooling: Arts Academies"
   site from investors in time, or the upgrade button lit where your government owns levels. **Null:** the bar
   stays on Traditional Art and the button's tooltip says 0 after a few months: tell me who owns the levels.
4. Once you research Steam Turbine, open a power plant: **expect** the recipe bar on Early Power Plant with Coal-Fired as
   the target, and the upgrade button lit where your government owns levels. **Null:** no recipe bar, or a vanilla
   method icon still showing: the panel didn't take the new building type.

## Latest: your government retools its levels abroad from the upgrade button (your current save works)

From your 21:26 message. Government levels abroad now go through your government construction queue, the same
button as at home. The release build writes no PMR log lines, so every check here is something you see.

No script effect can queue a construction for your government in another country's state; only the game's own
expand can. So while your government has levels to retool in a state abroad, PMR keeps a "Retooling (Government):
<building>" site standing there with one level owned by your government (it retools nothing itself). The upgrade
button expands that site once per level of room (up to 8 a click). Only your own government's levels count: PMR
reads them as the levels you and your investors own less every privately owned level, so another government's
levels are never retooled. The Buildings tab button on a building type row still covers only your own states.

1. Open a building abroad where your government owns levels on an older recipe (the West Bengal coal mine,
   "Great Britain 1 level"), after the next 1st of the month. **Expect** a "Retooling (Government): Coal Mines"
   site in that state and the upgrade button beside the recipe name lit; its tooltip says how many levels it queues.
   **Null:** no site and the tooltip says 0: PMR read none of the government levels as yours (other countries'
   investors owning levels there make it read fewer). Tell me the Owners list.
2. Click it. **Expect** that many levels of "Retooling (Government): Coal Mines" in West Bengal in your government
   construction queue, and the button greys. **Null:** the site stands, the tooltip shows room, but the button is
   grey or nothing is queued: the game won't let your government expand there, so this route doesn't work in that
   country. More queued than the tooltip said: the game doesn't recheck the room between clicks; tell me both numbers.
3. As each level completes, the recipe bar moves a level and the Owners list's Great Britain row shows the new
   recipe. Once every level is on it, the site goes.

## Latest: retooling weighed against the building, a 5-year policy lock, a year of weekly re-investment, retooling abroad, priorities on a timer (your current save works)

From your 19:25 to 20:28 messages. Your current save works; wait for the game to reach the 1st before checking.

- **Retooling weight** (20:12). A retool site now weighs twice what an expansion of its building would score: the
  building's own AI value plus its earnings, the way the game scores profit. Before, PMR counted a year's earnings
  as if they were a week's and added 150,000, so in your 1838 autosave retool sites scored 39,000 to 75,000 against
  30 to 3,400 for new builds and took every pick. A building scoring well above a retool site, like the tea
  plantation at 14,000, now wins. The foreign-or-domestic bar (£1 a worker a year per notch), Favour Large
  Corporations, Bulls & Bears and Market Titans had the same 52-fold error and were scaled down with it.
- **Policies** (20:06, 20:08). The text at the top of the policy window is gone; how policies work is in the Add
  Policy and Change Policy tooltips. A policy adopted from now on is kept for 5 years: the other cards read "Locked,
  N months" until then. After that an X at the top right of the policy card on the Private tab cancels it. A
  policy you already hold has no lock, so its X shows at once. Cancelling writes `PMR;rec=POLICY;...;policy=cancelled`.
- **Retooling abroad.** No level you own abroad had ever retooled. The game's investors pick one state for each
  retool site before checking who may build there, and in your 1844 save all 15 of Britain's picks abroad were in
  states where only the host could build (your West Bengal coal mine waited a year with both sites open). Each
  building now has a fifth retool site, opened only where you own levels in another country's state; the other
  four open only at home, and foreign investors now give those a weight of 0.
- **Companies abroad** (your 20:00 card). Companies now list the abroad site as well as the first home site, so a
  company owning levels abroad can own their retooling and its company weight counts there. A company panel shows
  two Retooling icons for each building type it lists.
- **Test decisions.** Only "PMR test: pause or resume the monthly ticks" is left, for the timing run the
  performance review still needs. Grant Bessemer, grant Open Hearth, recompute retooling now and record trade-offs
  worldwide are gone.
- **Publish review fixes** (20:53 to 20:56). Vanilla events and objectives that look for an automation method
  (Dangerous Equipment, Untrained Hands, the watertube boiler and textile mill accidents, the steam donkey objective)
  now read PMR's recipes. Your investors no longer retool government-owned levels abroad (your government does, above). In a power bloc with
  the Transport principle, railways on Steam, Electric or Diesel get +25% throughput and the principle's extra
  infrastructure (state modifiers named Transportation Infrastructure), with no retooling.
- **Weekly Re-investment** (20:28) now holds 52 weeks, like the Investment Pool graph beside it, and its axis
  shows the same two dates. The weeks your save already recorded stay; the older half fills in as weeks pass.
- **Policy cards** are as tall as their text. The last line holds the authority cost on the left and "Requires
  Investment Banks" or "Current Policy" on the right, so nothing sits on the effects. Each law has its own window.
- **Priority timer.** After you change a priority row you have 7 days to change it again, then it stays for 3
  months, as tariffs do. Each row has its own timer; a locked coin's tooltip says about how many weeks are left.
  Each change writes `PMR;rec=PRIORITY;...;group=...;value=...`.
- **Law locks.** Under Laissez-faire every row is locked at +0%; each coin's tooltip says why (no line under the header, your 20:25 ask). Under
  Agrarianism only Agriculture and Resources can be set. The coin you set before is kept and counts again under
  another law.
- **Policy cost.** A policy now uses authority while held, set when you adopt it from your legitimacy: 200 at 25 or
  less, 100 at 50, 50 at 75 or more, in straight lines between. The card shows the price; the held card shows what
  it uses. A policy you already hold stays free until you change it. `PMR;rec=POLICY` lines now end in
  `authority=<cost>`.
- **Agrarianism policies.** Landed Credit: +25% Aristocrats' investment efficiency, +10% Agriculture throughput,
  +2 Landowners, -2 Industrialists. Crown Concessions: +10% Mining and Logging throughput, +10% government
  dividends efficiency, -2 Rural Folk.
- **AI policies.** On the 1st, an AI country under one of the three laws with no policy picks one it can afford,
  at random (never Steer the Economy, which only widens your priority cap).

What to do: play on from your save for six months. Open the Private tab and change one priority, then try it again
after a week. Open the policy window. After a few months check your private queue and the West Bengal coal mine.

| What you see | What it means |
| --- | --- |
| Six months on, nothing queued at the West Bengal coal mine and it is still 0% on Condensing Engine Pump | The investors still don't pick the abroad site. Send your latest autosave; I'll read Britain's picks for `building_pmr_retool_coal_mine_5`. |
| No `RETOOL_LEVEL` line for any of your home states in three months, where there were before | The weight of 0 for foreign investors also stopped your own. Send error.log lines containing `bg_pmr_retool`. |
| Clicking a coin writes no `PRIORITY` line, or the coins are still clickable 8 days after a change | The timer didn't load. Send error.log lines containing `pmr_ipw`. |
| Under Laissez-faire a row shows anything but +0%, or its coins are clickable | The law lock didn't load. Send a screenshot and error.log lines containing `pmr_ipw_law_lock`. |
| You adopt a policy and the topbar authority tooltip shows no Economic Policy line | The authority cost didn't apply. Send the `POLICY` line and error.log lines containing `pmr_policy`. |
| No `POLICY` line for any AI country two months after you load | The AI pick never ran, or no AI country could afford one. Send error.log lines containing `pmr_policy`. |
| The policy window's cards overflow again | My height estimate is off for that text. Send a screenshot. |
| A company panel shows only one Retooling icon per building type | The abroad site didn't make it into the company files. Send error.log lines containing `company_types`. |
| Your private queue is still all retooling a few months on | Retool sites still outscore new builds. Send your latest autosave. |
| No retooling queued at all for three months where some was before | The new weight came out too low or failed to read. Send error.log lines containing `pmr_ai_value`. |
| After adopting a policy, the other cards stay clickable | The lock didn't load. Send error.log lines containing `pmr_policy_lock`. |
| No X on your current policy's card | The cancel button didn't load. Send a screenshot and error.log lines containing `pmr_policy_cancel`. |

## Earlier: ports and railways retool; administration, universities and trade centres pick their best method (start a new game)

From your 17:00 message. Start a **new game**: ports and railways gain PMR's recipe slots, and buildings in an older
save would lack them.

- **Ports and railways retool** like factories: a recipe bar on the building panel and the Buildings tab row, the
  upgrade button, and investors' retool sites. Ports go Anchorage, Basic, Industrial, Modern Port; railways Early,
  Steam, Electric, Diesel Trains, Electric waiting for the state's own electricity as other electric recipes do.
  The Transport principle's better railway recipes (power blocs) are gone: with them a railway would have had to
  retool backwards whenever its bloc dropped the principle.
- **Always the best method, no retooling, no selectors**: government administrations, universities, trade centres,
  and railways' passenger carriages (always the best carriages, so railways always carry passengers too). They
  switch on the 1st, when you research something, when built, and at once if anything else changes them. Each
  switch in your states writes `PMR;rec=AUTO;...;building=...;method=...`, flushed to disk at once. A method the
  owner lacks the technology for is never picked (21 February 1836 put your administrations on Switchboards).
- **Clergy or bureaucrats by law**: administrations and universities staff clergy under State Religion, Millet
  System, People of the Book and Freedom of Conscience, and bureaucrats or academics under Total Separation and
  State Atheism. Hereditary or professional bureaucrats already followed the bureaucracy law.

What to do: start a new game, unpause for a month, then look at a railway, a port, a government administration and
a university. With the selectors gone, an administration's inputs show its method: none on Simple Organization,
paper from Horizontal Drawer Cabinets on. Research Centralization and check an administration after the next 1st.

| What you see | What it means |
| --- | --- |
| A port or railway shows vanilla's method icons instead of the recipe bar | The building file didn't load. Check error.log for `11_private_infrastructure` and send the lines. |
| An administration, university or trade centre still shows its method selectors | The panel patch missed. Send a screenshot. |
| After researching Centralization, an administration of yours still uses no paper after the next 1st, and no `AUTO` line names it | The switch never ran. Check error.log for `pmr_auto` and send what you find. |
| `AUTO` lines for the same building every month, alternating methods | The game and PMR disagree on what can run. Send the lines. |
| Under State Religion or Freedom of Conscience your administrations employ no clergy | The law gate didn't load. Check error.log for `07_government` and send the lines. |
| A railway whose inputs show neither wood nor steel | No carriages are running: the switch failed. Send a screenshot of the railway and any `AUTO` lines. |
| An `AUTO_TRIP` line | The game and PMR switched one building's method back and forth more than 3 times in a day; PMR stopped for the day. Send the line and the `AUTO` lines before it. (Added after the 16 August 1838 freeze, which left no log line; a loop like this is one candidate.) |

## Earlier: two Laissez-faire policies, and Recent Investments as tree maps (your current save works)

From your 16:06 and 16:12 messages.

- **Recent Investments.** The three bars are now tree maps in the style of the market panel's Exports and
  Imports: Domestic and Foreign beside Built By, Priority Groups under them. Tan is domestic and your own
  investors, plum is foreign. Hover a tile for the chart's numbers, or a legend row for its own (a group's row
  lists its building types). They stay hidden until a level completes, as before.
- **Policies under Laissez-faire.** With Laissez-faire, Add Policy opens a window holding only **Bulls & Bears**
  and **Market Titans**; under Interventionism it shows the four from before. Switching law drops the policy on
  the 1st, as before.
  - Bulls & Bears needs Investment Banks; until then its card is greyed and reads "Requires Investment Banks".
    It gives +25% Capitalists' investment efficiency, +15% private construction allocation (90% with
    Laissez-faire), +2.5% market access price impact, -2 Trade Unions approval and +10% Trade Unions attraction.
    Investors weigh each building in your states by half again of its earnings per worker, and Market Liberal
    leaders are 25% more likely to appear (the ideology's own leader weights, × 1.25).
  - Market Titans gives +1 company, +4 free charters, +20% Company Throughput Bonus and +20% Company Construction
    Bonus. Investors weigh building types your companies own by half again. Industrialists lose 2 approval for
    each of Health System and Education you have (shown as "Market Titans: Health System" and "Market Titans:
    Education"; they appear on the 1st or when you adopt it). Executives' bonuses are not doubled: 1.14.5 has no
    modifier or script link for them.
- Adopting a policy writes `PMR;rec=POLICY;...;policy=bulls` or `policy=titans`.
- **Favour Large Corporations** (your 16:42 message) now gives only +1 free charter and the investment weight; the
  Company Throughput Bonus and Company Government Dividends are gone.

| What you see | What it means |
| --- | --- |
| The charts never appear, though `INVEST` lines with `kind=gov` or `kind=investors` show | The tree map isn't reading PMR's numbers. Send a screenshot. |
| Every tile is the same colour or grey | The tiles aren't finding their place in the list. Send a screenshot. |
| Under Laissez-faire the policy window is empty | The law check on the rows failed. Send a screenshot and any `pmr_policy` lines in error.log. |
| Bulls & Bears can be clicked without Investment Banks | The technology check isn't read. Send the `POLICY` line. |
| Market Titans held, Health System or Education in place, and no Market Titans line in Industrialists' approval after the 1st | The monthly upkeep didn't run. Check error.log for `pmr_titans`. |
| error.log mentions `01_character_ideologies` or `ideology_market_liberal` | The Market Liberal patch broke. Send the lines. |

## Earlier: the Private tab, fifth round, and your government's row abroad (your current save works)

From your 15:33 and 15:34 messages. Open the Private tab once after loading, as before.

- **Owners list abroad.** In the West Bengal coal mine, Great Britain's row now shows recipe icons. Abroad, PMR
  tracks every owner's levels together, so your row shows the same recipes as the Financial Districts row, and
  its hover says so. The flag that marks a building abroad is set on the 1st of the month (or when you research
  something), so the icons appear from then.
- **Weekly chart.** No white line; each week is a column from zero, split by group. Until the first week is
  recorded the frame reads "No historical data".
- **Two tree maps.** The existing one (privately owned levels by priority group), and under it building levels
  by owner: Government, Local Shop Owners, Companies, and Manor Houses with Financial Districts together.
  `PMR;rec=CONTRIB` now ends with `owner_gov=`, `owner_self=`, `owner_company=`, `owner_invest=`.
- **Three bars at the top of Recent Investments**, drawn like the game's own ownership bar: Domestic or
  Foreign, by priority group, and who built it (Government, Your Investors, Local Owners, Foreign Investors).
  Each segment and each legend entry has a tooltip; a group's tooltip lists each building type with its
  points and levels. They now count **every level completed in your states, and every level you build
  abroad**, government building and retooling included. Retooling counts under the building it retools. The
  record from the previous version starts again from zero, so the bars stay hidden until the next level
  completes.
- **Foreign or Domestic Investment.** Replaces the priorities text: its own framed row with seven notches, the
  tariff bar's icons, Foreign on the left and Domestic on the right. Each notch from the middle makes every
  building in your states weigh as if it earned £1 more (Domestic) or less (Foreign) a worker. Foreign
  investors see your states the same way. Clicking a notch writes `PMR;rec=FOCUS;...;notch=<1-7>;bias=<-3..3>`.
- **Policies.** Favour Large Corporations: +1 free charter, +10% Company Throughput Bonus, +10% company
  government dividends (no more extra company). 1.14.5 has no company price or wage modifier. Favour Small
  Businesses: shopkeepers' investment efficiency +25%. Re-invest is now **Focus on Infrastructure** with a gold
  rail icon: +10% railway and +10% port throughput, and it keeps the retooling weight.

Each completed level now writes
`PMR;rec=INVEST;...;building=<type>;kind=gov|investors|local|foreign|not_counted;levels=<levels added>;player_levels=;government_levels=;local_levels=;points=`.

| What you see | What it means |
| --- | --- |
| Great Britain's row in the West Bengal mine still has no icons after the 1st | The abroad flag isn't read by the panel. Send a screenshot and the mine's `ABROAD` line. |
| Bars never appear although `INVEST` lines with `kind=gov` or `kind=investors` show | The record isn't reaching the panel. Send the lines and a screenshot. |
| `INVEST` lines say `kind=not_counted` for levels in your own states | The owner check failed. Send the lines. |
| A government retool level completes but no `INVEST` line appears | Retool buildings aren't reaching the hook. Check error.log for `pmr_pi_`. |
| Bar segments are missing or all the same width | The game's stretch layout isn't taking PMR's shares. Send a screenshot. |
| The owner tree map shows only Manor Houses and Financial Districts | The ownership reads returned nothing. Send the `CONTRIB` line. |
| Clicking a notch writes no `FOCUS` line | The slider's script didn't run. Check error.log for `pmr_fd`. |
| `INVEST_MISS` lines | Expected once for constructions that started before this version. |

## Earlier: retooling what you own abroad, and the Private tab, fourth round (your current save works)

After loading, **open the construction panel's Private tab once.** That names you as the player for the
new hooks and starts the weekly clock (`PMR;rec=CLOCK`, once). Without it both wait for the 1st of the month.

### Retooling what you own abroad (your 14:33 and 14:36 messages)

Levels your government or your investors own in another country's state, such as the West Bengal coal mine
(Financial Districts 2 levels, Great Britain 1 level), now retool to the best recipe **your** technology
allows, even where the host's technology is behind. Script can't queue a construction for your government
in a foreign state, so your investors retool every level you own there, your government's included. The
upgrade button stays greyed out abroad, as before.

1. Open the Private tab, then run to the 1st of the month (or research anything).
2. Look for `PMR;rec=RESEARCH` and then `PMR;rec=ABROAD` for `state=West Bengal;building=building_coal_mine`.
   The ABROAD line's `best=` is your best recipe and `host_best=` the host's; `to=` should now equal `best=`.
3. Over the following months, "Retooling: Coal Mines" should appear in West Bengal's construction, queued by
   your investors. The investment pool picks it among everything else it could build, so it can take a while.

| What you see | What it means |
| --- | --- |
| No `ABROAD` line for West Bengal by the 2nd | PMR doesn't see you owning levels there. Send the West Bengal `TICK` or `INIT` lines and any `pmr_` line in error.log. |
| `ABROAD` with `best=` equal to `host_best=` | Not abroad-limited: the host can already run your best recipe, so retooling follows the normal path. |
| `ABROAD` appears, but no retool construction for a year | The pool never picks it. Tell me; the retool weight abroad can be raised. |
| Retool levels finish, but the mine keeps the old recipe | The switch is being blocked abroad. Send the `TICK` lines for the mine after the retool completes. |

### The Private tab, fourth round (your 14:28 message)

- **Weekly re-investment.** The line records every 7 days (`PMR;rec=REINVEST` and `PMR;rec=CONTRIB` once a
  week, starting the day after you open the tab). It starts empty and fills in from the right; the old
  monthly points are not carried over. The x-axis reads "25 weeks ago" to "This week".
- **Columns under the line.** Each week's column reaches up to the line and is split by that week's tree chart
  shares, in the tree chart's colours, darkened so the white line stays readable.
- **The pool graph** from the budget's Investment Pool tooltip sits to the right of the line.
- **Two bars at the top of Recent Investments.** Domestic vs foreign, and by priority group, both by
  construction points of the levels your investors complete from now on. Retooling and government construction
  are not counted. Until the first level completes, a line of text stands in their place.
- **Policies.** The window is smaller and fits the screen. Each policy is a blue card showing its benefits;
  click one to adopt it. The card you hold is highlighted and marked "Current Policy". Hover any card for
  the explanation.
- **New policy benefits.** Construction and investment efficiency now belong to Laissez-faire. Favour Large
  Corporations: +1 free company charter, +1 maximum companies, +10% company government dividends, plus its
  higher investment weight for company industries. 1.14.5 has no modifier for how many monopolies one company
  may hold, so the free charter stands in. Steer the Economy keeps only the +75% priority cap. Re-invest keeps
  +10% government dividends reinvestment. Favour Small Businesses loses the farmers bonus.

Each completed level in a building where you own levels writes one line:
`PMR;rec=INVEST;...;building=<type>;kind=private|government|other;levels=<your levels added>;government_levels=<government levels added>;points=<construction points>`.
Only `kind=private` adds to the bars.

| What you see | What it means |
| --- | --- |
| No `CLOCK` line after opening the Private tab | The tab's script didn't run. Check error.log for `pmr_pc_refresh_sgui`. |
| `CLOCK` but no `REINVEST` line a day later | The weekly event didn't fire. Check error.log for `pmr_pi`. |
| The line draws but there are no columns under it | The coloured bars aren't drawing. Send a screenshot. |
| Columns hang down from the top of the frame | Vertical bars fill top-down in 1.14.5. Tell me; it's a one-line fix. |
| Private constructions complete in your states but no `INVEST` lines appear | The completion hook isn't running. Check error.log for `pmr_pi_`. |
| `INVEST` says `kind=other` for a level your investors built | The new level's owner isn't set yet when the hook runs, so the bars can't count it. Send the line. |
| `INVEST_MISS` lines | Expected for constructions that started before this version: there was no "before" count to compare with. They should stop as old constructions finish. |
| The policy window still runs off the screen | Tell me your resolution and UI scale. |
| Clicking a card does nothing | Check for a `PMR;rec=POLICY` line. If there is none, check error.log for `pmr_policy_`. |

## Earlier: faster monthly ticks, and a timing test (your current save works)

The performance changes you approved at 13:12. None of them changes what the mod does; they cut
checks that ran for every building in the world but fed only the log, or that ran more often than
needed:

- The investment-pool, unemployment and home-investor checks, and the second blend read, now run only
  in your own states (they only ever fed your log lines).
- The ownership and earnings ladders are bisected (about 5 checks instead of 20, and about 4 instead
  of 12); earnings are read only while a building has something to retool.
- Electricity is read once per state instead of once per building, and each good's price once per
  state per day instead of once per farm type.
- Research no longer re-runs the full tick on every building the country owns: it ticks only the
  buildings whose best recipe changed, and any it hasn't seen yet. **Side effect:** a trade-off that
  research just unlocked shows as unavailable on the building panel until the 1st of the month. The
  shares only move monthly anyway.
- Method changes the tick makes itself no longer walk the 41-type dispatch before being ignored.
- The Buildings tab's count of your buildings abroad is cached between the monthly sums.
- The TREAT and PRICE probes are off (they answered their questions), so those log lines stop.
- New decision **PMR test: pause or resume the monthly ticks**, for timing.

**Timing test (one save, about ten minutes):**

1. Load a save from the 1840s or later and unpause at speed 5.
2. Time one in-game year with a stopwatch.
3. Take **PMR test: pause or resume the monthly ticks** (it logs `PMR;rec=TEST;arm=TICKS_PAUSED`),
   then time the next year at the same speed.
4. Take the decision again to resume (`PMR;rec=TEST;arm=TICKS_RESUMED`). Shares hold still while
   paused and move again from the next 1st of the month.

Tell me both times. A much faster paused year means PMR's script is the cost, and the next round of
script savings is worth doing. Little change means the cost is the data the engine carries (the
35,728 hidden methods and the retool building types), and the levers that shrink that are the ones
to weigh.

| What you see | What it means |
| --- | --- |
| `TICK`, `OPT` or `CSUM` lines keep appearing after `TICKS_PAUSED` | The pause didn't take, so the paused time is not a measurement. Tell me. |
| No `TICKS_PAUSED` line after taking the decision | The decision didn't run; check error.log for `pmr_test`. |
| `REINVEST` and `CONTRIB` lines carry on while paused | Expected: the Private tab's weekly records are not part of the tick. |
| A trade-off reads unavailable right after its technology | Expected until the 1st of the month (side effect above). |
| Shares or bars move differently from before | Not expected; these changes should move nothing. Send the building and the `OPT` line. |

## Earlier: the Private tab, third round (still to check; your current save works)

What changed after your 13:05 look:

- **The trend line draws now.** Its cells used a white texture that 1.14.5 doesn't ship, so they drew
  nothing. Your save already holds four months (your log rows were 10, 1, 10 and 20), so the line
  should show on load.
- **Top of the tab:** the budget panel's own Investment Pool line. The Weekly re-investment line and
  the Previous Investments line are gone; recent investments stay at the bottom.
- **Buildings Adding to the Pool is a tree chart.** The game gives its per-building amounts only as
  text, so the tiles are the privately owned building levels in each of the five priority groups,
  with a legend of shares. Hovering the chart shows the game's list in money. It is counted when you
  open the Private tab and on the 1st of each month.
- **Five priority groups.** Light Industries (light industry, shipyards, arts), Heavy Industries
  (heavy and military industry), Agriculture (farms, ranches, plantations, rubber, fishing, whaling),
  Resources (mines, logging, oil) and Infrastructure (railways, ports, trade centers, power). Each
  row reads +0%, or the boost in green (+25%, +50%). Earlier coin settings don't carry over: every
  group starts at +0%.
- **Larger cards.** The law and policy cards are 268 by 380; a law with more effects than fit
  scrolls inside its card.
- **Economic Policies window.** Add Policy and Change Policy open a window beside the panel with all
  four policies as cards: benefits, a short description, and Adopt Policy. Added benefits: Steer the
  Economy +10% private construction allocation and +10% infrastructure construction efficiency;
  Favour Large Corporations +10% capitalists' investment efficiency and +10% company construction
  bonus; Re-invest +10% government dividends reinvestment and +10% light and heavy industry
  construction efficiency; Favour Small Businesses +10% farmers' investment efficiency.

1. **Trend line.** On load the graph shows a pale line through the four recorded months on the
   right. Hovering a month shows its weekly figure.
2. **Pool line.** "Investment Pool: £… (+…)" matches the budget panel, and hovering it shows
   vanilla's pool graph.
3. **Chart.** Opening the Private tab logs
   `PMR;rec=CONTRIB;...;light=...;heavy=...;agriculture=...;resources=...;infrastructure=...`. Five
   coloured tiles, each labelled with its group and sized by those numbers, and a legend whose
   percentages add to 100%.
4. **Cards.** All of Interventionism's effects are readable (scroll inside the card if needed), and
   the policy card is the same size.
5. **Policy window.** Add Policy opens "Economic Policies" to the right of the panel. Adopt Steer the
   Economy: a `PMR;rec=POLICY;...;policy=steer` line, the window closes, and the policy card shows
   Steer with its benefits and Change Policy. Change Policy reopens the window with Steer marked
   Current Policy. The close button shuts it; it hides on other tabs, and clicking the Private tab
   closes it.
6. **Priority rows.** Five rows, all reading +0% in white. Fifth coin on Light Industries: it reads
   +50% in green; hovering shows what it covers and x1.00, and Heavy Industries shows x0.67. Under
   Steer the Economy the same coin reads +75%.
7. **error.log** has no line naming `pmr_pc`, `pmr_ipw`, `pmr_policy` or `pmr_ri`.

| What you see | What it means |
| --- | --- |
| No line, but hovering a month shows its figure | The cells still don't draw; send a screenshot. |
| "Counted when you open this tab…" stays after opening the tab, and no `CONTRIB` line | The tab button's recount didn't run. |
| A `CONTRIB` line with numbers, a correct legend, but no tiles, equal tiles, one colour or one label | The tiles can't find their group by their place in the list; the legend is still right. Tell me which. |
| Add Policy does nothing | The window isn't placed beside the panel; send error.log lines naming `construction_panel` or `pmr_policy_window`. |
| The window opens but clicks go through it to the map | It doesn't block clicks; tell me. |
| A row stays at +0% after a coin click | The row's value isn't read; the coin frame tells you whether the click itself landed. |

## Earlier: the Private construction tab, first two rounds (superseded above where they differ)

**Revised 2026-10-13 after your first look:** the weekly re-investment is a trend line in vanilla's
graph frame (the GDP graph's), the policy card is the law card's size with an Add Policy plus in the
middle, and each investment priority is the budget page's five-coin selector (0, 25, 50, 75 or 100%
of the cap). The contributors stay as the game's own list for now: the game gives them only as text.

Built in the investment sliders thread to your design. The construction panel's tabs are now
Government, Private, Foreign and Ships; the Government/Private funding filter is gone, and so is the
investment pool from the Government tab. The policy cards need Interventionism: play a country that
has it, or enact it. Besides `PMR;rec=` in debug.log, look in error.log for `pmr_ipw`, `pmr_policy`,
`pmr_ri`, `pmr_ai_value` and `pmr_pi`.

1. **Tabs.** Four tabs: Government, Private, Foreign, Ships. Government shows the construction
   sector and the government queue, with no investment pool and no funding filter.
2. **Private tab**, top to bottom: weekly re-investment, its chart, buildings adding to the pool,
   economic policy (the law card, and the policy card to its right), investment priorities (one row
   per building group), private construction with the All/Domestic/Abroad filter, then recent
   investments and privatizations.
3. **Weekly re-investment** at the top matches the weekly income in vanilla's investment pool tooltip
   (hover the number for that tooltip).
4. **Trend line.** Reads "Recorded on the 1st of each month" until the next 1st. Then each 1st logs
   `PMR;rec=REINVEST;...;weekly=...;min=...;max=...;row=...` and the line gains a point on the right;
   the axis shows the lowest and highest month, hovering a month shows its figure.
5. **Coins.** Click the fifth coin of Light Industries: its frame moves there and the row reads +50%
   weight. Hover the figure: x1.00, and every other group's x0.67. Fifth coin on Heavy Industries
   too: both read x1.00.
6. **Policy card.** It matches the law card's size, with Add Policy in the middle. Click it: the four
   policies appear in the card. Pick Steer the Economy: a `PMR;rec=POLICY;...;policy=steer` line, the
   card shows Steer with a Change Policy button, the fifth coin reads +75%, and with Light Industries
   alone at the fifth coin the other rows read x0.57.
7. **Card lock.** Under another economic law Add Policy is greyed with "Requires Interventionism"
   under it. Repeal Interventionism while holding a card: the next 1st of the month logs
   `policy=dropped` and the card clears.
8. **Priorities in play.** Light Industries at full, nothing else: over a year, new private
   construction leans to light industry. The 1/11 to 11 roll swamps a x1.5 on any one pick, so judge
   over many builds.
9. **Re-invest.** Hold it with Light Industries at full, with a light industry building on an old
   recipe and a newer one researched: private retooling of it is picked almost every time it is offered.
10. **Favour Large Corporations.** Hold it with a company founded: private builds of that company's
    building types rise.
11. **error.log** has no line naming the five filters above. A "set but never used" warning on
    `pmr_ipw_on` is harmless.

| What you see | What it means |
| --- | --- |
| Three tabs, or the funding filter still there | The panel files didn't load; send me error.log lines naming `construction_panel` or `construction_queue`. |
| An empty Private tab | The tab's layout (`pmr_private_tab`) didn't load; send error.log lines naming `pmr_private_investment`. |
| Weekly re-investment reads 0 while the pool grows | `investment_pool_income` reads differently from the tooltip. |
| No `REINVEST` line on the 1st | The monthly country pulse never ran. A line with `row=` above 0 but no line drawn means the chart cells don't read the variables. |
| The graph frame is missing or empty with no message | `v3_plotline` didn't take the overrides; send error.log lines naming `pmr_private_investment`. |
| A coin click does nothing | The priority's scripted GUI didn't run. |
| The frame moves but every row reads x1.00 | The priority values aren't evaluated. |
| Add Policy does nothing | The GUI flag `pmr_policy_pick` isn't kept; tell me. |
| No `POLICY` line when you pick a card | The card's scripted GUI didn't run. |
| A card stays after Interventionism goes | The monthly law check failed. |
| Re-invest or Favour Large Corporations change nothing | The weight isn't read where I put it (`pmr_reinvest_mult`, `pmr_ai_value`); look for those in error.log. |

## Earlier: trade-offs start where your 1838 save was heading, and the second bar's label is vanilla's group name (you confirmed both)

- **The label beside each second bar is now vanilla's name for the group**: Hardwood Production,
  Secondary (farms), Luxury Production, Canning, Distilleries, Working Conditions (plantations),
  Aeroplanes, Tanks. It no longer changes with the leading option, and an ellipsis cuts it if it
  would run past the panel. The tooltip is shorter: the group, each option's share and, for
  trade-offs, what it earns per level a week, then one line on how the group moves. Your current
  save shows this at once.
- **New games start each trade-off near where games take it.** I read your 1838-10-28 save
  (7,609 buildings in 1,141 states) and took, per building type, where every building was heading
  at its state's prices. New games now start there: rye farms 32% Potatoes and 68% Apple Orchards,
  wheat and maize farms all Citrus Orchards, millet and rice farms all Fig Orchards, logging camps
  5% Hardwood and 27% Focused Hardwood, textile mills 21% luxury, furniture 70% luxury and 2%
  Precision Tools, glassworks 99% Ceramics, food industry 3% Pot Stills and 10% Patent Stills
  (canning stays off). An option a state can't run yet passes its share to the option before it,
  then to none. Your current save keeps its shares; this needs a new game.

Check, in a new game: the first `OPT` line of a Yorkshire rye farm reads `x=32/68/0`, or one
month's move past it; a logging camp reads `x=5/27`. In your current save, the logging camp's
second bar reads Hardwood Production.

| What you see | What it means |
| --- | --- |
| A new game's rye farm starts at `x=0/0/0` or on vanilla's single choice | The start shares didn't load; check error.log for `pmr_t` or `pmr_xinit`. |
| A rye farm starts with Potatoes at 100 | Apple Orchards can't run in that state, so its share passed down. Normal where the technology is missing. |
| The label still shows an option's name and share | The panel file didn't load; tell me. |
| The label is blank | The group's name didn't resolve; tell me which building. |

## Earlier: faster trade-offs, and a record of trade-offs worldwide (your current save carries on)

- **Trade-offs move by how much better the option pays.** Each month the best-paying option takes
  as many points as its lead over the worst-paying share, in % of the building's output, from 2 to
  20. Your rye farms' Apple Orchards lead by about 48% of a rye farm's output, so they now take 20
  points a month and finish in two months; an option ahead by 10% moves 10 points; the move slows
  as prices answer. An option that can no longer run sheds 20 points a month.
- **New test decision, "PMR test: record trade-offs worldwide".** Load your current save, take it
  once, then save and quit so the log reaches disk. It writes one `WORLD` line per state and
  building type for every country, with the levels, shares, which options can run and their values.
  From those I'll set where new games start each building type.

Check: the month after loading, the rye farm in Yorkshire goes 66% to 86% Apple Orchards (`x` in its
`OPT` line), and Ireland's potatoes drop 20 points a month.

| What you see | What it means |
| --- | --- |
| Shares still move 2 points a month | The new step didn't load; check error.log for `pmr_m`. |
| The decision writes no `WORLD` lines | Its loop over the world's states found no state with a trade-off building. Tell me. |
| `WORLD` lines stop partway, with no `WORLD_DONE` after them | The log hadn't reached disk; save and quit before sending. |

## Earlier: plantation treatment and trade-offs blend (start a new game)

**Start a new game.** Buildings gain new production method groups, which a running save can't take.

- **Plantation treatment follows the workforce.** Each plantation's Working Conditions is now a mix:
  the share of its workforce with acceptance under 40 is treated violently, 40 to 59 exploitatively,
  the rest under Standard Labor. Every effect of a treatment scales by its share, output, mortality,
  wages, job attractiveness and slave imports alike. The law wins: where Violent Treatment is barred
  (Britain bans slavery), that share is treated exploitatively, and where Exploitative Practices are
  barred too, it goes to Standard Labor. Recounted monthly.
- **Trade-offs follow local prices.** Hardwood, the farms' secondary crops, the luxury lines (textile
  mills, furniture, glassworks), canning and distilling, aeroplanes and tanks. Once a month points
  move from the worst-paying option to the best-paying one, if it adds over 5% of the building's
  output value more at this state's prices (2 points a month in that build; see Latest). At game start every building keeps vanilla's choice; one
  built later starts on the best-paying option.
- **A second bar under the recipe bar** on the building panel, one per group (food industry has two):
  grey for none (Standard Labor, Prioritize Softwood Production, Jars), then each option. Beside it,
  the leading option and its share. Hover for each share, this month's change and, for trade-offs,
  what each option adds per level a week at local prices.

Play to at least 1 March 1836. Each month a player-owned state logs one `OPT` line per building type
with a blended group, for example
`PMR;rec=OPT;...;building=building_logging_camp;x=0/0;running=0/0;can=1/0;value=-100/-1000000;px=hardwood:1.00,wood:1.00`.
The fields list the options in order (for food industry: the four canning options, then the two
distilling ones):

| Field | Meaning |
| --- | --- |
| `x` | each option's share, 0 to 100; none is the rest |
| `running` | the share the building actually runs; should equal `x` |
| `can` | 1 if the option can run here (technology, laws) |
| `value` | what the option adds per level a week at local prices; -1000000 when it can't run |
| `px` | each good's local price as a share of its base price, 0.25 to 1.75 |
| `w`, `band_v`, `band_h` | plantations: workforce, and % of it under acceptance 40 and from 40 to 59 |

Checks:

1. **Treatment.** On a Jamaican sugar plantation (or any of your plantations), the exploitative share
   in `x` equals `band_v + band_h`, since Britain bars violent treatment (`can=0/1`). Its panel's
   second bar shows the same split.
2. **Prices.** On a logging camp, a hardwood option gains points each month whenever its `value` beats
   the worst-paying share by more than 5% of the camp's output; otherwise `x` stays put. At base
   prices hardwood loses money (`value=-100`), so expect movement only where hardwood is dear.
3. **The bar.** Open a food industry: two bars under the recipe bar, Canning and Distillery.

| What you see | What it means |
| --- | --- |
| No `OPT` line after 1 February | The blending never ran; it is not that every share is zero. Check error.log for `pmr_x`. |
| `can=0` for an option you know is unlocked | Asking whether the stripped vanilla method could run reads false; every share drains to none. |
| `running` differs from `x`, or reads -1 | The share method did not activate, so the building's figures don't show that share. |
| `w=0` on a staffed plantation | The workforce read nothing, so treatment stays all Standard Labor. |
| `px` all 1.00 every month, `value` never moving | The price reads fail; trade-offs then only follow base prices. |
| A bar all grey while `x` shows a share | The bar fails to read the state's variables; the blend itself works. |

The `TREAT` and `PRICE` probe lines from the last build still run; `OPT` supersedes them.

## Earlier: retool clutter and the bar tooltip

- **Finished retool buildings go at once.** A private retool building is removed the moment its level
  is counted, as a government one already was, so the state's Buildings tab shows only the
  construction sites still building. The crews are gone: investors never stacked levels on them, and
  they kept the finished sites around. Ones already finished in your save go at their state's next
  monthly tick.
- **Shorter recipe bar tooltip**, without the colour names, on the building panel and the Buildings
  tab row.

Null: a "Retooling: …" card still showing at level 1 after its state's monthly tick means the removal
did not run; tell me the state and building.

## First: the 16 June 1836 freeze

Your last game froze during the daily update of 16 June 1836, with nothing clicked. debug.log held
no PMR line after 11 June, because the game writes that log to disk in 4 KB blocks and loses the
last block when it hangs. This build adds:

- **A loop breaker.** If one building type's PMR tick runs more than 25 times in one state on one
  day, PMR stops ticking it there until the next day and logs `PMR;rec=TRIP`. Normal play runs it
  once or twice a day at most.
- **Lines that reach disk even if the game hangs right after**, for the rare PMR actions that could
  set one off, in every country (not only yours): `TECH` (a country acquired a technology; its states
  tick next), `RETOOL_LEVEL` (a retool level finished; its building ticks next), `RELEASE` /
  `RELEASED` (a private retool building with a crew is about to be removed / was removed, 90 days
  after its last level when its crew stayed short). Each ends in a long run of dots, which is what
  pushes it to disk.

Run a new game at full speed to at least September 1836.

| What you see | What it means |
| --- | --- |
| No freeze, no `TRIP` | The freeze did not repeat. It needs something this run lacked; play on and tell me. |
| No freeze, `TRIP` lines | PMR's own hooks were looping and the breaker ended it. The `TRIP` line names the building and state. |
| Freeze, last PMR line `RELEASE` with no `RELEASED` after it | Removing a crewed retool building hangs the game. |
| Freeze, last PMR line `TECH` or `RETOOL_LEVEL` | The tick that follows that event hangs. |
| Freeze, no PMR line from that day | Not PMR's hooks: the loop is in the game's own daily update. The investment AI choosing among retool buildings is the next suspect. |

If it freezes, close it and tell me; I read the logs from here.

**Start a new game for this build**, including if you started one on d920da5. Recipes from the third
on change what they consume, and six building types gain a recipe. Leave `fastresearch` off for the
full run.

## What changed in this build

- **Electric automation is a recipe of its own.** Your Yorkshire tooling workshop on Steel Tools was
  using oil and electricity, because every recipe from the third on included Assembly Lines. Recipes
  from the third on now include the best automation that runs without electricity (Rotary Valve Engine
  for tools, so Steel Tools uses wood, steel and coal). Assembly Lines and Automatic Power Looms
  become one more recipe on top of the newest, e.g. "Machined Steel Tools + Assembly Lines". A
  building moves to it only when its owner has both technologies (Vulcanization and Conveyors for
  tools) and its state produces electricity. Textile mills, furniture, tooling, motor, arms and
  artillery each get one.
- **Buildings tab type rows count buildings abroad.** The tab lists buildings in other countries'
  states that you or your investors own levels in (your cotton plantations in the East India
  Company's states). The type row's bar summed only your own states, so a type with every building
  abroad stayed black. A player's bar now adds those buildings, whole, as their own bars show them,
  recounted monthly and the day after game start. The upgrade button still queues at home only.
- **Retooling priority follows profit.** Investors now weigh a retooling site as vanilla would weigh
  expanding the building from its profit (1,000 + 7,500 per pound the building earns per worker) plus
  a top-up of 150,000, in place of a flat 1,000,000. Retooling is the likelier pick, about three times
  a new building earning the same, but not a certain one. `TICK` lines add `earn=` (the building's
  earnings per worker: 0, or at least 2, 4, 6, 8, 10, 12, 15, 20, 25, 30, 40 or 50) and `ai_w=` (the
  weight).
- **Investment randomness** (your call in the investment thread): the investment pool's random roll
  on each building type now spans 1/11 to 11 instead of 1/21 to 21, for every building, through
  `common/defines/zz_pmr_ai.txt`. The 80% employment gate is unchanged.
- **Government upgrade button:** the government retools only its own levels that don't run the new
  recipe yet. Levels it builds new arrive on the new recipe and never count. (Your Sicily sulfur mine:
  2 new government levels on Atmospheric Engine Pump, 5 private levels on Picks and Shovels. The
  button offered 2; it now offers 0 and stays grey, and the private side gets all 5.)
- **Owners list:** a Production Method column between Owner and Levels Owned, with the icons of the
  recipes that owner's levels run. The government's row shows the government's levels; every private
  row shows the private owners' together (PMR tracks the two sides, not each owner). Hover for counts.
- **Recipe bar** in the building panel is 32 px tall, as tall as the cash reserves bar looks.
- **Buildings tab type row:** the bar was black until the first month passed, because at game start
  no country is a player's yet and the country totals were skipped. They are now computed for every
  country at game start. Each monthly recount writes `PMR;rec=CSUM`.
- **Retool crews:** each private retooling building has a fixed crew of 10 laborers, whatever its
  level, so it counts as fully employed and investors may add levels to it. Each empty one still
  takes one level as a new construction; the rest of the private room goes to the first one with a
  finished level. One whose crew hasn't reached 80% 90 days after its last level landed is removed
  once counted, as before.
- **Companies** list Retooling again (the first private retooling building of each type they list),
  so company panels show one Retooling icon per building type.
- `TICK` lines add `gov_lv=` (the government's levels per recipe), `slots=` (each private retooling
  building's levels including queued), `crew=` (-1 no finished level, 0 nobody hired, 1 some,
  2 at least 80%) and `unemp=` (the state's unemployment, at least 1, 2, 5, 10 or 20%; 0 below 1%).
- **Two log-only probes** for the next batch, plantation treatment and the market blend. They change
  nothing in game. See "Probes for the next batch" below.

## Checks

0. **Defines on load.** Before anything else, search `logs\error.log` for `zz_pmr_ai` and
   `RANDOM_FACTOR_MULT`. There should be no lines. A define that fails to merge is silent in game,
   and script can't read it back, so this is the only check that the 1/11 roll took effect.
1. **Government button.** In a new game, research a newer recipe for a building the government
   partly owns and let the government build a new level of it. The new level runs the new recipe;
   its `TICK` line shows `gov_lv=` with that level on the new recipe and `room_gov=` without it. If the
   government owns no old levels, the arrow is grey.
2. **Owners column.** Open a building with government and private owners. The Production Method
   column shows the government row's recipe icons and the private rows' icons; hover each for counts.
   Send a screenshot of the Owners list.
3. **Buildings tab bar.** From the second day, each PMR type row shows its recipe bar in the tier
   colours, not black, including Cotton Plantations, whose buildings are all abroad. Hover it: the
   level count includes the buildings abroad.
4. **Recipe bar height.** The bar lines up with the cash reserves bar. Screenshot.
5. **Stacking.** Let two years pass. On `TICK` lines with `room_priv` above 1, `slots=` should show
   2 or more on one building once its `crew=` reads 2.
5a. **Retool priority.** On `TICK` lines, `earn=` varies between buildings and is 0 on loss-makers.
   Over two years, investors should queue retooling more often than new buildings, but not every
   time, and sooner on buildings with a higher `earn=`.
6. **Electric recipes.** On day one, open the Yorkshire tooling workshop. Its Process box shows wood,
   steel and coal going in, and no oil or electricity. No PMR building whose recipe isn't one of the
   electric ones (or a vanilla recipe that uses electricity itself, such as Electric Arc Process)
   lists electricity. Screenshot the tooling workshop.

| You see | It means |
| --- | --- |
| The government arrow is lit on a building whose government levels all run the new recipe | The government's levels per recipe went wrong. Send me the `TICK` line (its `gov_lv=` and `gov_levels=`). |
| The Owners list overlaps or runs past the panel | The narrower copy of the row didn't take its new widths. Screenshot. |
| The type row bar is still black on day one and `PMR;rec=CSUM` lines appear from the first month | The totals exist but the bar can't read the country's variables. Screenshot plus any `error.log` line with `pmr_c_`. |
| Only types whose buildings are all abroad stay black after the second day, and a `CSUM` line was logged | The scan of states abroad finds nothing, so the ownership check doesn't match. Send the `error.log` lines with `levels_owned_by_country` or `pmr_c_sum`. |
| The type row bar is black and there is no `CSUM` line after a month | The monthly recount never runs. Send me the `error.log` lines with `pmr_`. |
| `crew=0` on a building with a finished level for 90 days | Nobody was hired: the game ignores a crew that doesn't scale with level, or no laborers would take the job. That building drops back to one level at a time. Open it from the state's building list and send its Workforce tab. |
| `crew=2`, `room_priv` above 1 and `slots=` never above 1 for two years | Employment was not what stopped investors stacking levels. Send me the lines. |
| `crew=2` and `slots=` 2 or more on one building | Stacking works. |
| An `error.log` line naming `zz_pmr_ai` or the define | The randomness change did not load, and the roll is still vanilla's 1/21 to 21. Send the line. |
| `earn=0` on every `TICK` line, profitable buildings included | The earnings ladder never reads true, so every retooling site weighs 151,000 whatever the building earns. Send the `error.log` lines with `earnings`. |
| Investors build almost nothing but new buildings while yours show `room_priv` above 0 and `home_investors=1` | The top-up is too small against vanilla's weights. Tell me and I'll raise `RETOOL_AI_TOPUP`. |
| Investors retool and never build anything new while any room is left | The top-up is too large. Tell me and I'll lower it. |
| Steel Tools still lists oil or electricity | The game loaded the old build. Check the date of `common/production_methods/pmr_electric_production_methods.txt` in the mod folder, then send the Modifiers tab. |
| A building runs a "+ Assembly Lines" or "+ Automatic Power Looms" recipe whose owner lacks either technology, or in a state with no power plant | The gate failed. Send that building's `TICK` line. |
| `crew=2`, `room_priv` above 1, `slots=` stuck at 1 and `unemp=0` | The state is short of workers. The investment pool scores buildings x0.25 there once they employ anyone, so a strong rival may be winning the picks. Send the lines; compare with a state where `unemp` is 5 or more. |

## Probes for the next batch (log only)

Both run once a month in your own states and change nothing in game.

**TREAT**, one line per plantation:
`PMR;rec=TREAT;...;building=building_coffee_plantation;level=…;cur=…;vb=…;hb=…;w=…;wv=…;wh=…;ws=…;n=…;nv=…;nh=…;ns=…`

- `w` is the plantation's workforce. `wv`, `wh` and `ws` split it by acceptance: under 40 (Violent
  Hostility, Cultural Erasure: the violent share), 40 to 59 (Open Prejudice: the harsh share), 60 and
  over (standard). `n`, `nv`, `nh` and `ns` are the same counted by pop size, dependents included,
  as a fallback in case `w` reads 0.
- `cur` is the treatment it runs now: 2 Violent Treatment, 1 Exploitative Practices, 0 Standard
  Labor, 3 another method (tobacco's lectors or radio stations).
- `vb=1` means the owner's laws bar Violent Treatment; `hb=1` means they bar Exploitative Practices.

**PRICE**, two lines (hardwood and wood) per state with a logging camp:
`PMR;rec=PRICE;...;good=hardwood;base=40;f=…;p=…`

- `f` is the local price against the base price in steps of 5%: `f=35` means 35 to 40% above base,
  `f=-10` means 10 to 15% below. `p` reads the same with the threshold written in percent instead of
  as a fraction, because the game's docs don't say which it takes. One of the two will stay at 0.

7. **TREAT.** Pick a plantation with a `TREAT` line. Its `w` matches the employee total on its
   Workforce tab, and `wv + wh + ws = w`. Send a screenshot of the Workforce tab and the line. If one
   of your states has discriminated plantation workers, check their band against that state's Pops tab.
8. **PRICE.** Pick a state with a logging camp and open its market panel. The local price of hardwood
   and of wood should be base x (1 + f/100), within 5%. Send a screenshot and the two lines.

| You see | It means |
| --- | --- |
| No `TREAT` or `PRICE` lines at all after a month | The probe never ran. This is not a result about plantations or prices. Send the `error.log` lines with `pmr_probe` or `pmr_tr_`. |
| `w=0` on a staffed plantation and `n` above 0 | Workforce can't be summed this way. The build will count by pop size (`n`) instead. |
| `w=0` and `n=0` on a staffed plantation | No pop matched, so either the employment check or both counts read nothing. Send the `error.log` lines naming `workforce`, `total_size` or `pop_employment_building`. |
| `ws` equals `w` in a state whose Pops tab shows plantation workers under 60 acceptance | Acceptance read wrong. Send the Pops tab. |
| `wv + wh + ws` differs from `w` | The bands miss some pops. Send the line. |
| `f=0` and `p=0` for both goods in every state for a year | The price ladder never reads true. This does not mean prices sit at base. Send the `error.log` lines with `state_goods`. |
| `p` varies and `f` reads 75 or -75 almost everywhere | The threshold is in percent. The build will use the `p` ladder. |
| `f` varies and `p` stays 0 | The threshold is a fraction, as vanilla's railway rule suggests. The build will use the `f` ladder. |
| `sg=none` | The state has no market entry for that good. Harmless. |

## Checks from the previous build (b9c7304), still to confirm

1. **Panel row.** Open any PMR building. There is no goods icon; the recipe name starts at the left
   edge and the bar is about 290 px wide, ending where the employment bar starts.
2. **Workforce.** Open a building that is retooling (queue its government levels with the upgrade
   button and let one land). In the Workforce tab its jobs move towards the new recipe's as each level
   lands. Its Modifiers tab lists one `(… % of levels)` line per recipe, each with jobs and goods.
3. **Automation.** A mine whose newest recipe is Condensing Engine Pump: that recipe's share line in
   the Modifiers tab includes engines, coal and transportation inputs and fewer laborers. No mine,
   steel mill or factory shows an automation selector.
4. **Buildings tab.** Now check 3 of this build.
5. **Private retooling.** Let a year pass. For each building with `room_priv` above 0, read
   `home_investors` and `pool` on its `TICK` lines.

| You see | It means |
| --- | --- |
| A building's jobs never change as levels land, but its goods do | The share methods' employment is not read by the game. Send me the Workforce and Modifiers tabs. |
| A mine still shows an automation selector, or `error.log` names a production method group | The building file edit did not take. Send me the `error.log` lines. |
| The arrow on the type row never lights although a state's building panel arrow is lit | The country scripted GUI cannot see the state flags. Send me a screenshot of both. |
| A `TICK` line with `elec=0` shows `to=` an electric recipe that was not running before | The electricity lock failed. Send me the line. |
| `room_priv` above 0 for a year, `queued_priv=0`, `home_investors=0` | Your country's investors do not own enough of the building (at home they need more levels than the government) to fund its retooling. Ownership, not the pool. |
| The same, with `home_investors=1` and `pool=1000` or more | The pool is allowed and has money but never picks the retool buildings. Send me the lines: that points at how the pool scores them. |
| The same, with `pool=0` or `100` | The pool is too small to fund anything yet. Not a result. |

## Earlier checks, still to confirm

- **Goods counted once.** A building whose shares the tick had changed listed each switched recipe
  twice: Sicily's sulfur mine showed **Condensing Engine Pump (15% of levels)** and **Diesel Pump
  (10% of levels)** twice each in its Modifiers tab, and its inputs at about twice its blend.
  Buildings still on their starting share were right. A method change runs the tick it triggers
  inside the change, so one level landing ran about ten ticks nested in each other, and the log shows
  it (`SWITCH` written before the line of the tick that made the switch). Now only the outermost tick
  runs, and no share is activated while it already runs. Why the nesting doubled the goods is
  inferred: the outer tick activated again a share the inner one had already applied. The first try
  at this, the switching lock, stays: it does no harm and keeps the running share unlocked mid-change.

### The doubling check

1. Load your save (or start a new game) and open the Sicily sulfur mine, or any building with two
   recipes in its bar.
2. Open its **Modifiers** tab and hover each input. Each recipe appears **once**, as **Recipe (…
   of levels)**, and the figure is that line times the throughput. Sicily's tools, coal and oil
   should be about half what they were at the same employment.
3. Let a retool level land on that building, then hover again. Still once, and the log has one
   `rec=TICK` line for that building on that day, not ten.

| You see | It means |
| --- | --- |
| Right after loading, each recipe once and the figures halved, and still once after a level lands | Fixed. |
| Right after loading, each recipe once, but a recipe is listed twice again after a level lands | The guard did not stop it. Send me that building's `PMR;rec=` lines for that day and the Modifiers tab. |
| A landing day still writes many identical `rec=TICK` lines for one building | The guard flag is not holding, so ticks still nest. Send me a few of the lines. |
| Right after loading, a recipe is still listed twice | The doubling is saved with the building, not made at runtime, so loading does not clear it. A new game is the test of this build; send me the tooltip either way. |
| A tier's `active` reads `-1`, or `active` and `blend` differ on two lines in a row for one building | The switching lock left a share group without a method. Send me the lines. |

### Earlier in this build

- **Old recipes' goods are now in the building's own production figures.** Each recipe has a hidden
  share method carrying its goods (and pollution) times its share of the building's levels, in 1%
  steps (5% before this build). An iron mine with 15 levels on Atmospheric and 5 on Condensing lists **Atmospheric Engine
  Pump (75% of levels)** and **Condensing Engine Pump (25% of levels)** in its input and output
  tooltips, coal included, scaled by employment and throughput exactly like a vanilla recipe. Its
  profit, and the investment AI's view of it, use those figures. The **Not yet retooled** and lag
  modifiers are gone.
- **Up to four private retool levels per building at a time.** Each building type has four private
  retool slots, each holding one level, so a state can show up to four **Retooling: Iron Mines**
  entries in the Private queue at once, plus the government's.
- **Companies no longer list Retooling.** Company panels show only their own building types again.
  A building a company owns still retools through investors from the company's country.
- Unchanged: research switches the recipe, the level mix, the bar colours, who may fund retooling,
  and the government cap.

## Reading the log lines

`to` is the target recipe's tier. `levels` is the level count on each tier, oldest first, so
`5/3/0/0` means 5 levels on Blister and 3 on Bessemer. `p` is the target's share and `to_retool` is
the number of levels not on it.

`blend` is each tier's share in percent as the tick set it (`75/25/0/0`), and `active` is the same
figure for each tier whose share method the game reports running, `-1` where it does not. They match
when the blend has been applied, which with the guard should be on every line.

`gov_frac` and `gov_levels` give the government-owned share and the levels it comes to.
`share_gov` / `share_priv` split `to_retool` between government and investors. `queued_gov` /
`queued_priv` are retool levels queued but not yet built, and `room_gov` / `room_priv` are how many
more each side may queue.

While a building retools, every method change on it writes another `rec=TICK` line, so a level
landing usually brings two or three lines for that building on the same day.

## What each null means, decided before the run

| You see | It means | Not |
| --- | --- | --- |
| No `rec=LOADED` line | The mod is not in the playset, or `on_game_started` is not reaching appended on_actions. Check the playset first. | Anything about the design. |
| `rec=LOADED` but no `rec=INIT` lines | `pmr_state_tick` is not reaching buildings. Take **PMR test: recompute retooling now** and look again. | — |
| `error.log` names any `pmr_` script, method or group | Part of the script did not load. Send me the lines. | A failure of the design. |
| A mill's input and output tooltips show no **(… of levels)** line at all, and its figures are zero | The share methods are not applying: the defaults did not take on load. Send me a screenshot of the tooltip and the mill's `rec=INIT` line. | A failure of retooling. |
| `active` stays behind `blend` across two lines for the same building, and the tooltip shows the old percentages | The share method was refused although the switching lock was active, and the lock's own method change did not bring a second tick. Take **PMR test: recompute retooling now**; if `active` then catches up, the blend works one tick late. | A failure of the level mix. |
| `active` shows `-1` for a tier | None of that tier's share methods is running. The game dropped the method when its lock changed. Send me the line. | — |
| An input tooltip lists the same **Recipe (… of levels)** line twice, or a building's inputs are about twice its blend | A share's goods are counted twice. See the doubling check above. | A failure of the level mix. |
| The same building writes dozens of `rec=TICK` lines on one day | The method changes are retriggering each other. Send me a few of the lines. | — |
| The figures move but the tooltip's percentages and `blend` disagree | The rounding or the tier order is off. Send me the line and the tooltip. | — |
| The bar is grey, white or one colour although the tooltip shows two recipes above 0% | The bar failed, not the model. Send a screenshot with the tooltip open. | A failure of retooling. |
| A Retooling entry shows **NULL_STATE** in a queue | A retool slot was removed while a level was queued on it. Send me that state's `PMR;rec=` lines around that date. | — |
| Months pass with money in the pool and a building with `room_priv` of 2 or more never has more than one **Retooling:** entry queued at a time | The pool picks one slot per building at a time anyway. Still better than before: each lands and the next opens. Send me the tooltip of an open slot that is not being built. | A failure of the cap. |
| More than four **Retooling: Steel Mills** in Yorkshire in the Private queue at once, or more than `to_retool` | The slot check (`level_after_queued_constructions < 1` in `can_build_private`) is not holding. | — |
| Months pass with money in the pool, Yorkshire keeps `queued_priv=0` with `room_priv` above 0, and no **Retooling: Steel Mills** appears | The ownership check refuses your own investors. Hover **Retooling: Steel Mills** in Yorkshire's construction list and send me the tooltip. | A failure of the cap. |
| A **Retooling:** entry appears in your Private queue for a building your investors own none of | The ownership check is not applied. Send me the state and building. | — |
| A retool level lands but the next line's `levels` and `to_retool` do not move | Completed levels are not being counted (`pmr_seen_`). | A failure of the investors. |
| After **PMR test: grant Open Hearth**, Yorkshire's SWITCH line shows `levels=8/0/0/0` or `levels=0/0/8/0` | The level mix was reset instead of kept. | — |
| **Retooling (Government): Steel Mills** is not in the capital's construction list, or is listed but greyed out while the capital's line says `room_gov=5` | Its `potential` or the government cap failed. Send me the tooltip. | — |
| You can queue a sixth government level in the capital | The government cap is not enforced. | — |
| `rec=RESEARCH;...;best=2` but no `rec=SWITCH` follows, even after the month turns | `activate_production_method` in state scope did not switch the mill. | A failure of retooling. |
| A company panel still shows **Retooling** icons | The old company files are still in the mod folder. Check `mod\ProductionMethodRework\common` has no `company_types` folder. | — |
| A field prints as text in brackets rather than a number | A log datafunction did not resolve on this build. The instrument failed, not the mod. | — |

## The run

**1. Install** (already copied to your mod folder). Start a **new** game with only this mod in the
playset.

**2. Start as Great Britain.** Before unpausing, expect `PMR;rec=LOADED` and one `rec=INIT` per
treated building. Yorkshire's steel mill line reads:

```
PMR;rec=INIT;...;state=Yorkshire;building=building_steel_mill;to=1;level=8;levels=8/0/0/0;p=1.000;to_retool=0;best=1;blend=...
```

The `blend` and `active` fields on INIT are written before the first blend, so ignore them there.
Every mill's bar is solid red with **100%** in the middle.

**3. Check the starting figures.** Open Yorkshire's Steel Mills and hover its iron input and steel
output. Each lists **Blister Steel Process (100% of levels)** and no other recipe line, and the
figures match vanilla Blister (Yorkshire held 345 iron and 561 steel last time). Also note the
investment pool on the **Construction** panel; if it reads £0, unpause for a few weeks.

**4. Take `PMR test: grant Bessemer and a steel mill`.** It creates five government-owned levels in
the capital, then researches Bessemer. Without unpausing:

```
PMR;rec=SWITCH;...;state=Yorkshire;...;to=2;level=8;levels=8/0/0/0;p=0.000;to_retool=8;blend=100/0/0/0;active=100/0/0/0;...;room_gov=0;room_priv=8
PMR;rec=SWITCH;...;state=Home Counties;...;to=2;level=5;levels=5/0/0/0;p=0.000;to_retool=5;blend=100/0/0/0;active=100/0/0/0;...;room_gov=5;room_priv=0
```

The mills read **Retooling to Bessemer Process** over an all-red bar showing **0%**, and the
tooltips still show Blister at 100%: nothing has been retooled yet.

**5. Queue the government's share.** In Home Counties, build **Retooling (Government): Steel Mills**
until it refuses. It should take exactly 5, in the Government queue, at 400 construction each.

**6. Unpause and watch the Private queue.** Expect up to four **Retooling: Steel Mills in
Yorkshire** entries under Private at once, owned by a Financial District, never more than 8 in all.

**7. Let some levels land.** Each one writes a `rec=TICK` the day it lands, with one more level
moved from the first figure to the second, and the blend following:

```
PMR;rec=TICK;...;state=Yorkshire;...;levels=6/2/0/0;...;blend=75/25/0/0;active=75/25/0/0;...
PMR;rec=TICK;...;state=Yorkshire;...;levels=4/4/0/0;...;blend=50/50/0/0;active=50/50/0/0;...
```

Shares round to the nearest 1% (7 of 8 levels shows as 88%).
`active` may trail `blend` on the first line of a day and match on the next. The mill's tooltips now
list **Blister Steel Process (75% of levels)** and **Bessemer Process (25% of levels)**, and its iron,
coal and steel figures sit between the two recipes'. On the bar, red shrinks and yellow grows from
the right. When a slot's level lands and nothing else is queued on it, that **Retooling:** building
leaves Yorkshire's building list and the slot opens for the next level.

**8. Your edge case: grant Open Hearth mid-retool.** While Yorkshire still has levels on Blister
(say `levels=4/4/0/0`) and some retooling is queued, take **PMR test: grant Open Hearth**. Expect:

```
PMR;rec=SWITCH;...;state=Yorkshire;...;to=3;level=8;levels=4/4/0/0;p=0.000;to_retool=8;blend=50/50/0/0;...
```

The bar shows red and yellow at half each, with no blue yet, under **Retooling to Open Hearth Process**,
and the tooltips list Blister and Bessemer and no Open Hearth. Queued Retooling entries stay as they
were: none turns into NULL_STATE. As levels land, red goes first (`3/4/1/0`, `2/4/2/0`, and so
on), then yellow, while blue grows from the right.

**9. When the last level moves:** `rec=DONE;...;levels=0/0/8/0;p=1.000;to_retool=0;blend=0/0/100/0`,
the bar is solid blue at 100%, and the tooltips list only **Open Hearth Process (100% of levels)**.
If the DONE line shows `queued_priv` or `queued_gov` above 0, those levels still build. The retool
buildings stay until they land, then disappear.

## Optional checks

- **Your iron mine case.** After Diesel Pump on a mine with Atmospheric levels left, the coal input
  lists **Atmospheric Engine Pump (… of levels)** for as long as any level runs it.
- **Privatise mid-retool.** The next line should show `gov_frac` falling, `room_gov` dropping, and
  `room_priv` taking the rest.
- **Build a level mid-retool.** When it lands, `level=` rises and the new level arrives on the target,
  so the target's figure in `levels` goes up by one.
- **Build a new Steel Mills elsewhere after Bessemer.** Expect `rec=ADOPT`, then `rec=INIT` with
  every level on the newest recipe and `p=1.000`.

Send me the filtered `PMR;rec=` lines and the `error.log` lines containing `pmr_`, and say which row
of the null table matched if any did.
