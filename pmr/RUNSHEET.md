# PMR run sheet (PMR Test)

Newest build first. Sections for q31 to q105 are in git history (`git show ebbe73f:pmr/RUNSHEET.md`); the rows from
them still unseen are under "Still open from q104 and q106" at the end.

Every line PMR writes goes to `Documents\Paradox Interactive\Victoria 3\logs\debug.log` and starts
with `PMR;rec=`. Filter with:

```
findstr /C:"PMR;rec=" "%USERPROFILE%\Documents\Paradox Interactive\Victoria 3\logs\debug.log"
```

Also check `logs\error.log` for any line containing `pmr_` before reading anything else: a script
error there means the mechanism below never ran, and a missing log line is then not a result.

Timed runs: from switching to no country until the timed stretch ends, nothing else heavy runs on the PC. The game keeps
only six debug.log files of 512 KB, so a long run loses PMR lines between backup pulls; `logs\dedicated_server.log`
logs every tick's wall clock, and the pace is read from there.

## Latest: the Chamber of Commerce card alike in every country; the chance names its order (q122, test mod)

Your notes on q120 (2026-11-13 22:58Z and 23:00Z). "Everything should be the same between players and ai": q120
filled in the Investment Chance, the Funding cost and the state row's chips only for the player and great powers; they
now fill in for every country, every month (q121, never installed, is this half). The Investment Chance tooltip showed
the score's parts (`1.00K from Rye Farms`, `+352 from Weekly Balance`), which did not match the row's `+58`; it now
names the order up for investment and its building, with the row's own gain. Nothing else changed, so a q120 save loads
and the blanks fill in at the next monthly pass.

| # | Check | Pass | Null means |
| --- | --- | --- | --- |
| A1 | A minor's state with Chamber orders (Piedmont), observer | Investment Chance on the card, the cost in red on the Funding header, chips on the Buildings tab row | Blank: the monthly country or state pass does not reach that country |
| A2 | Hover the Investment Chance on a card with an investors' order | `<method> in <building>` and the same `£ +N` as that order's row | Another figure: the tooltip reads another order than the row |
| A3 | `dedicated_server.log` pace against q120-1 | Within about 0.2 s a game month | Slower: the card's monthly passes in every country cost more than expected; send to the perf review |

## Earlier: the Chamber of Commerce's fixes from your q119 screens (q120, test mod)

Your q119 screens and notes (2026-11-13 22:26Z to 22:28Z), with the Funding block drawn by the interface thread as
`ui/FUNDING-BAR.md`. The state row's chips showed pink icons and "0 Levels" because their variables shared names with
the Chamber's own working values; they have their own names now. A retool row had no gain because the gain only
counted when a building's full profit pass ran, about twice a year; it now counts in every monthly pass while a retool
order is open, and a negative gain shows in red. The Funding header's cost is big and red; the bar has vanilla's frame,
is as wide as the Order Book's rows and reads `0 / 500` and `0 / 18.8K`. No building type changed, so a q119 save loads.

The q119 observer game crashed on 21 Jan 1842 inside the game's own treaty naming ("Agreement Between Sintang and
..."), reading a country that no longer existed; no PMR line or error came before it.

| # | Check | Pass | Null means |
| --- | --- | --- | --- |
| K1 | A state's Buildings tab row, in a state with Chamber orders | Up to three chips with the building's icon, blue for the government, teal for investors; the tooltip names the building and reads `1 Level` or `N Levels` | Pink icons or "0 Levels": the chips still read the Chamber's working values |
| G1 | The Chamber card's retool rows, a month after the order | Each row shows a gain a level a week; a loss shows in red | No figure: the monthly pass does not reach the retool gain |
| G2 | A row whose gain rounds to 0 | No figure, not `+0` | `+0`: the visibility check is not applied |
| O1 | A card with one order | `1 Order` | `1 Orders`: the old key is still used |
| F1 | The Funding header on a card with orders | The cost in red, clearly larger than "Funding", not clipped by the band | White or small: the format or font size is not applied to the right text. Clipped: 30 is too tall for the band |
| F2 | The bar with nothing funded | A framed empty track, the same look as an Order Book bar at 0 | A dark slab: the frame is not set |
| F3 | The bar's figures on a small order and a large one | `0 / 500` and `0 / 18.8K` | `0.00K`: the old format is still used |
| F4 | The bar after a government press and an investors' unit | Blue then teal slices from the left inside the frame, a mark on a slice over 8% | Slices outside the frame or doubled rims: the slice texture is wrong |

## Earlier: the Chamber of Commerce, round 2 (q119, test mod)

q118 crashed on load (2026-11-13 22:14Z): the state row put its chips' hbox straight into a flowcontainer
(`error.log`: "can't have an hbox/vbox as a direct child"), the last line before the crash. q119 is q118 with the
hbox inside a widget; nothing else changed.

Your notes on q117 (2026-11-13 21:18Z to 21:42Z), drawn by the interface thread as `ui/CENTER-CARD.md` (round 2,
revised 22:10Z) and `ui/CONSTRUCTION-TAB.md`. The Center is now called the Chamber of Commerce everywhere it is shown
(the building and its group; the key and saves are unchanged), with its own icon, a building with gold. Its card has
no tab row and no Workforce or Modifiers. The top block adds the state's Investment Chance (its share of the country's
investor score; the tooltip gives the parts). The Funding header carries the estimated cost of everything asked
(construction asked times what a construction point's goods cost at the market's prices). The bar shows funded of
asked, with the unfunded part as an empty slice. Each Order Book row shows the vanilla icon of the method the order
buys, "<from> to <to>" for a retool or the rung for Re-equip and Rail Connection, and the gain a level a week. The
state's Buildings tab row shows up to three chips (the building's icon and levels, blue for the government, teal for
investors, `+N` past three). The construction panel's tabs are Construction and Investments, and the private queue
(header, filter, rows) sits under the government queue on Construction. The queue row's numeral click from q117's
`error.log` is fixed. No building type changed, so a q117 save loads; the gains, chips, chance and cost fill in at the
first monthly pass, and a new game reads cleanest.

A retool row's gain is the target recipe's weekly balance a level less the recipe most of the building's levels run
now (`pmr_retool_gain_<b>`), not the pay score's pick less default, which is 0 once the default is the pick.

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| P1 | Open the Chamber in a state with an investors' order | No tab row; Orders, Levels and Investment Chance in the top block | Tabs still drawn: the gate is on the content, not on `tab_buttons` |
| P2 | A Retool row's name and tooltip | "<from> to <to>", the to being the recipe the building card's switching bar names as the default; from and to differ | Blank name: the custom loc has no entry for that recipe. Same from and to: the row reads `pmr_best_now` twice |
| P3 | A row's gain against the building card | About the gap between the two recipes' weekly balance a level; green, with the money icon | No figure on any row: the gain variable is never written. Huge figures: it is the score, not pounds |
| P4 | Funding with nothing queued, then after a government press | An empty track and 0 of asked; then a blue slice the size of the order | A full bar with nothing queued: it still reads construction on order |
| P5 | Funding as investors buy a unit | The teal slice grows by that unit's size when the row enters the country queue | Grows only when the level lands: queued units are not counted |
| P6 | Investment Chance in two states, then against the run's log | The chances differ, the country's add to about 100%, and the tooltip's parts multiply out to the score; hidden in a state with only government orders. Over a run, a state's share of investors' units is near its chance | Same chance everywhere: the walk writes one value. Never shown: the monthly pass does not run for the player. The top states take far more than their chance: the game's pick is sharper than a plain share (back to the interface thread) |
| P7 | The state's Buildings tab | Up to three chips, icon and levels, blue for the government and teal for investors, `+N` when there are more | Chips with no icon: the building type variable does not resolve |
| P8 | The rows' icons | Each row shows the vanilla icon of the method it names; Rail Connection rows the rail track | A blank slot: the texture does not resolve. One icon on every row of a building: it follows the building, not the order |
| P9 | The Funding header's cost | Pounds, about asked construction times the price in its tooltip; moves with the market month by month | 0 or blank: `pmr_cc_cp` is never written for the player. Far from the construction panel's weekly goods bill a point: the wrong method's goods |
| P10 | The Chamber's icon in the state list and on the card | The building with gold, framed like its neighbours | A dark square behind the corners: the icon lost its alpha |
| C1 | Open the construction panel | Tabs read Construction, Investments, Foreign Queues, Ships | Old names: a later file overrides the tab keys |
| C2 | Construction tab with private levels queued | Government rows, then the Private Construction header, the filter and the private rows | No private block: it left Investments but was not added to the page |
| C3 | Investments tab | Pool line, charts, policies, priorities, Recent Investments; no queue rows | The queue drawn twice: the block is still in the old tab |
| C4 | The filter on the Construction tab | All, Domestic and Abroad still filter the private rows | The buttons do nothing: the filter's state lived on the old tab |
| L1 | Load a game, then open any state's Buildings tab | No crash; no `states_panel_buildings.gui` line in `error.log` | A crash again: something else in the row; send the logs |
| T3 | Click a refit row's numeral in the queue | The Chamber's card opens; no `construction_queue.gui` line in `error.log` at load | The const `GetBuilding` line again: the old file is still installed |

## Earlier: the Construction Center's row in the state's Buildings tab (q117, test mod)

You did not find the Center in the Midlands' Buildings tab on q116 (2026-11-13 20:08Z). The tab's grid lists only the
urban types a player can build, expand or downsize, and the Center is none of these, so q117 gives it a row of its own
between Urban Center and Trade Center, as `ui/CENTER-CARD.md` drew it: the icon, "Construction Center" and the go-to
arrow, then, while an order is open, a small Funding bar and levels done / ordered. q117 also stops the 140 "used but is
never set" lines q116 wrote to `error.log` at load (a New Equipment or Rail Connection job read a side abroad it never
has, and Minor Refit an abroad site that does not exist). No building type changed, so a q116 save loads. q116's rows
below still stand.

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| S1 | Any state's Buildings tab on 1 January 1836 | A "Construction Center" row under Urban Center: icon, name, arrow; no bar or figure | No row in any state, and S2 makes one appear: the Center is not created at the start. No row even after S2: the row does not find the Center |
| S2 | Press Retool Government Levels on one building, then the state's tab | The Funding bar (blue, the flag) and `0 / N` at the right of the row | A bare row: the card's totals do not see the order (N1 fails too) |
| S3 | Click the row's arrow | The Center's card opens | Nothing opens, or another building's panel |
| S4 | `error.log` after loading | No `pmr_cc_*_gova_50`, `pmr_eq_*_gova_*` or `pmr_rc_*_gova_*` "used but is never set" lines | They remain: a project still reads a side abroad |

## Earlier: the Construction Center and four refit sizes (q116, test mod)

You planned it on 2026-11-13 and gave the go at 19:03Z (`retool-tiers/PLAN.md`, the interface thread's `ui/CENTER-CARD.md`
and `ui/TIER-SITES-ROW.md`). q116 is q115 with the 192 per-building retool sites replaced by 15 shared ones: four sizes,
Heavy, Medium, Light and Minor Refit (200, 150, 100 and 50 construction a row), for each payer (home investors,
investors abroad, the government, the player's government abroad; Minor Refit has no abroad government site, as no
retool costs 50). Every building in a state draws on its state's sites. Each state that has an order gets a
Construction Center, one level owned by its government, which keeps the line: the player's government's orders fill
in the order they were pressed, and a level investors or an AI government build goes to the best open job of its size.
A major rebuild level (the 800 and 600 buildings) is two rows of its size. Switch `--center`; needs a new game, since a
q115 save has sites whose types are gone.

The Center's card shows and controls nothing: the orders in the top block, a Funding bar by payer, and an Order Book
row per order (building, job, levels done of ordered, payer). Its rows are one static row per job and payer, each built
only while its order is open. In the country queue a refit row starts with the building it is for (the Center while
several orders share the site), then the size's numeral, which opens the Center.

Known gaps in q116: the Private tab's Recent Investments bars do not count retooling, a building's private "queued"
figure reads 0, and companies list no retooling (the shared sites belong to no one building).

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| R1 | Midnight tick on ordinary days and pace, observer with no country, Feb 1837 to Feb 1839 (`dedicated_server.log`) | Below q115-1's (figures in the perf review, not here) | No gain: the retool types were cheap per type, or the Center's work costs what the types saved |
| R2 | `RETOOL_LEVEL` and `PROJECT_LEVEL` lines by July 1844 | About q115-1's counts | Far fewer: the shared sites lose the AI's roll; raise `CC_AI_MULT`. Far more: lower it. None at all: a site's `potential` never holds (`pmr_cc_gate_*` not set) |
| R3 | `CENTER_LEVEL` lines in an AI country | Each names a building and job with open levels; `rule=best` or `rule=half` | No lines: the sites are never built. A job with no open levels: the hand-out skips the room test |
| R4 | One state, several government buildings of one size, one press of Retool Government Levels | `GOV_QUEUE` and `CENTER_ORDER` lines for each; every row in the queue at once; the card lists each order | Only one building queues: a hold is still in the push |
| R5 | Two government orders of one size, watch the levels land | The first pressed fills first (`CENTER_LEVEL ... rule=line`); each row's bar moves by its own levels | The second fills first: the order's place in the line is not set. A bar jumps by two: a level was credited twice |
| R6 | Cancel rows of a refit size in the country queue | A `CENTER_CANCEL ... why=cancel` line; the last order in the line drops by that many; the card agrees with the queue | The card shows more ordered than queued: the cancel check is not running |
| R7 | A job closes with a row still building | The row lands on another order or open job of its size and payer; with none, a `CENTER_DROP` line, and the site goes once its queue is empty | A site left standing with nothing queued: a dropped row is not counted. A dead row in the queue: the site was removed under a queued row |
| R8 | A building with its retool and New Equipment both open | Both move at once | Only one moves: the jobs still share a hold |
| R9 | Move a Re-invest row on the Private tab | The refit site's score moves at once | It moves only after the building's tick: the weight is baked into a stored score |
| R10 | A government Major Rebuild level | Two rows of its size, both building at once; the level switches when the second lands | Switches at the first: units a level are not applied. Never switches: the second row went to another job |
| R11 | The Center's card and the state's Buildings tab | No demolish, privatise, nationalise or expand anywhere; the Center survives a conquest | A button shows: the type lets it change owner or size |
| T1 | Queue one building's retool, then open the construction queue | The row shows that building's icon, then the numeral, then "<size> in <state>" ("Heavy Refit in Midlands") | The Center's icon although one order stands: `pmr_for_<site>` is not set, or `Var()` does not take a built name; `error.log` names which |
| T2 | Queue a second building of the same size in that state | The first icon changes to the Center | Still the first building: `pmr_for_<site>` is not cleared when a second order joins |
| T3 | Click the first icon, then the numeral | The building's (or the Center's) panel opens; the numeral opens the Center | The hidden site opens: vanilla's button is still drawn on refit rows |
| T4 | A refit row under way in a state with a long name | The name shrinks or elides before it meets the construction figure | Overlap: the name's width needs cutting further |
| T5 | The Private tab's list with a private refit row | The same two icons, then the investor's icon on the right | |
| T6 | Rows of two sizes | The numerals differ and match the names | The same numeral: the sizes share an icon |
| N1 | Open the Center in a state with a government and a private order | One row each, blue and teal, the flag and the private badge | No rows: the rows' variables are not set (`pmr_*_ord_gov_*`, `pmr_*_cc1_*`) |
| N2 | Hover a row's bar; click its building icon | Job name, building, construction a level, payer; the building's panel opens | A blank building line: the row names a building the state lacks |
| N3 | The Funding bar with both payers | Two slices in the share of construction on order, a mark on each wide one | One slice: a payer's total is not counted (`pmr_cc_f_*`) |
| N4 | Look for anything to press on the card | Nothing but the tabs, the header's own buttons and the rows' building icons | Vanilla's top block shows: the card's swap for the Center did not apply |
| N5 | A level lands | The row's bar and figures move; the row leaves when its order is filled | The row stays: the levels-done counter is not cleared (`pmr_*_got_*`) |
| N6 | A state with no orders after its orders are done | "0 Orders", no Funding, "No Orders" under Order Book | Rows left over: a finished order keeps its variables |

## Earlier: New Equipment and Rail Connection built on the retool sites (q115, test mod)

q114 ran slower than q105 from the first day, all of it in the midnight tick, and the likeliest cost is the 184
hidden building types New Equipment and Rail Connection had of their own. You chose to fold them into the retool
sites (2026-11-12 21:20Z): each building keeps its four retool sites, which serve the retool, New Equipment or Rail
Connection, one at a time, so the mod adds 192 hidden building types instead of 376. Prices are unchanged; a retool
level is two site levels. A queued project shows the retool's name. Needs a new game: a q114 save has project sites
whose types are gone.

q115 is also the first build made from the game files as patched on 11 Nov. q114 (and most likely q105) came from an
older copy, so their copies of vanilla files put back what the patch changed there: its culling of surplus characters,
a personal-union check, port and trade-center method fixes and some interface fixes. q105 against q114 still compares
like with like; q115 against q114 moves both at once, and F1 reads them apart by the gain's shape.

The yearly TREAT line now logs for the logged country only, and a TREAT_MOVES line each month counts every Treatment
re-size in the world (buildings and states).

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| F1 | Midnight tick on ordinary days and pace, observer with no country from 1 Jan 1836 (`dedicated_server.log`; pace Feb 1837 to Feb 1839) | Midnight tick down from the first months of 1836 and level through the run: the site types were q114's cost (figures in the perf review, not here). Pace also below q105's: the patched game files gave something on top | A gain that is small in 1836 and grows by year: the patched files, not the types. No gain: the types are cleared and the cost is elsewhere. Slow daytime ticks with a flat midnight tick: the PC was busy, the stretch is unread |
| F2 | `PROJECT_LEVEL` lines by 1840 | Lines with `project=eq` and `project=rc` beside `RETOOL_LEVEL` lines, about as many as q114-1's 81 and 138 (a retool level now writes two) | `PROJECT_OPEN` lines but no `PROJECT_LEVEL`: the projects never get the sites |
| F3 | `TREAT_MOVES` lines | One a month, `building=` and `state=` counts | No line: the monthly report never ran; check `error.log` for `pmr_trm` |

## Earlier: the Investment Pool chart back to the game's own year (q114, test mod)

q113 drew the pool's years before the game's own year on the Investment Pool chart. You asked for it out again
(2026-11-12 20:15Z, "just set it to vanilla 52 week history its not worth the performance and jankiness"), so q114
is q112 again: both charts show the game's own 52 weeks, and nothing reads the pool each January. Everything in
q112's section below still applies. A q113 game carries on; the readings it stored stay in the save and are unused.

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| Y5 | The Investment Pool chart after Feb 1837 | The game's own year, left date a year back | Left date "1 Jan, 1836": the q113 files are still installed |

Ran 2026-11-12 as an observer game with no country from 1 Jan 1836 to 6 Jan 1844 (run q114-1, logs in
`runs/logs/q114-1/`): no PMR runtime error. Y5 and q112's C11, C12 and C14 need a played country and are unread.

## Earlier: the workers a retool adds, called out, and no Method Mix icon on a state (q112, test mod)

q111 with your asks of 2026-11-12 17:07Z ("we need to make sure we call out when we are adding workforce
requirements", laid out by the interface review in `ui/Q111-WORKFORCE.md`, "Still live") and 17:25Z (the "Method Mix"
icon among Yorkshire's modifiers). Everything in q111's section below still applies. A q111 game carries on in q112;
a building shows its line once its methods next update, so give it a month or two.

- A line of pop icons and figures for the skilled posts a method brings, the whole building's, added posts first: at
  the end of the New Default bar's hover, under the retool button's row, after "To retool" in method bar 1's hover
  ("At 12 of 22 levels:"), and on the card in the New Default bar's row, level with the employment bar, from the day
  the method is on its way until the posts have moved. Laborers are not listed (the Automation bar has them).
- A New Equipment row that buys Chainsaws (logging camps) or a motor industry step names the posts it moves too.
- The state's modifier icons (its Overview and the condensed state rows) leave out "Method Mix".

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| C11 | A textile mill whose New Default bar runs to Sewing Machines: the bar's hover, and the card beside the bar | Last hover line and the card line read about @machinists! +250 x levels and @engineers! +250 x levels (from Dye Workshops) | No line: its methods haven't updated since q112 went in, or the posts are read from the wrong method |
| C12 | The same mill once the bar is full, while its levels retool: method bar 1's hover, the retool button's hover, the card | "At N of M levels:" with the same figures (N = half the levels plus one); the card line until N levels are on Sewing Machines, then gone | The line stays after the posts moved (Workforce tab shows them): it compares against the wrong method |
| C13 | Yorkshire's Overview, the modifier icons at the bottom right of its picture | No "Method Mix" icon | Still there: another mod's states_panel.gui loads after PMR's |
| C14 | A logging camp's retool button when New Equipment buys Chainsaws | Under its row, @engineers! +500 x levels | No line: the step's posts aren't read |

## Earlier: thinner method bar rims, an Automation bar that fills from the left and a New Default bar that gains a month a month (q111, test mod)

q110 with your three asks from its first screenshots (2026-11-12 17:01Z, 17:03Z and 17:05Z). Everything in q110's
section below still applies; a q110 game carries on in q111 (a bar already running keeps its months).

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| C8 | A building's method bars beside employment and cash | One rim each, the same as the employment bar's | Still a double rim: the old slice texture is in use |
| C9 | The Automation bar of a mine with levels on rail | Blue from the left edge, grey at the right | Grey on the left: the old order |
| C10 | A building's New Default bar (hover: "_ of 6 months") from the month it appears | 0 the month it appears, then one more each month; the new default takes over at 6 | It jumps by 2 or more, or appears nearly full: the old gain-based points |

## Earlier: the building card from your q109 screenshots and rail steps that pay (q110, test mod, started 2026-11-12)

From the build thread, on your asks of 2026-11-12 16:07Z to 16:20Z while q109 ran. q110 is q109 with these:

- **The card** (interface review's Q110-CARD.md): the method bars at the size of the employment and cash bars, level
  with them, with no name lines (the name is in the hover); the Retool button between Privatize and Nationalize, and
  in the slot of each building row on the Buildings tab; Vacancies under Owners; a new Automation section between
  Process and Owners, one bar of hand labor (grey), machines (green) and rail (blue).
- **One Retool button**: its tooltip lists each project it queues by the step it buys.
- **Rail steps that pay**: they read the state's own transportation price, refuse only when the state is short of
  transportation, and cut 3,000 to 5,250 laborers a level (1,500 to 3,000 before), enough to pay at base price in a
  state paying 100 a week.
- **Connected from the start**: on 1 January 1836 a mine, plantation, vineyard, logging camp or oil rig in a state
  with a railway, whose owner has Railways, starts with every level on Rail Transportation.

**Start a new game.**

1. Use the PMR Test playset and launch with -debug_mode. Start a new game as **Great Britain**.
2. In the first week, open Yorkshire's coal mine and take screenshots of its card (top and Information tab), with
   the hover on a method bar, on the Automation bar and on the Retool button (C1 to C6).
3. Open the Buildings tab, expand Coal Mines and take one screenshot (C2).
4. Play as Britain at any speed to 1 February 1837, then switch to no country. From there to 1 February 1839 nothing
   else heavy runs on the PC and the game stays in front; the build thread does not read the PC in that stretch (S15).
5. Run on to 1 January 1845 or as far as you like, close the game and tell the build thread.

Read `logs\error.log` first: a line naming `pmr_rl_`, `pmr_lprice_`, `pmr_lpx_`, `pmr_eq_` or `pmr_rc_` means that part
never ran, and its nulls below are then not results.

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| C1 | A building with two method bars | Both the size of the employment and cash bars, level with them, no text beside them | A bar off by a few pixels: the column is not centred as vanilla's is |
| C2 | The action row | Retool between Privatize and Nationalize, the same size; also in the Buildings tab's building rows | On one screen only: one of the two slots was not filled |
| C3 | The method bar's hover on a building at rest | "Production Methods", divider, the method and 100% | "100% on ..." with no header: the old key is still in use |
| C4 | A coal mine's Information tab | Process, Automation, Owners, Vacancies in that order | Automation missing: the type test |
| C5 | The Automation bar on a building with levels on a step | Green or blue slice as wide as its share of the laborers the steps take off; the hover's levels match the RAILS line | All grey with levels on a step: the tallies are not read |
| C6 | The Automation hover on a building with no step | The step and one reason a track (for example "Requires Steam Donkey") | Header only: the reason is not passed to the interface |
| C7 | The Retool button's hover where a project is open | A row a project, "N levels to <step>" with its cost, under the retool row | Retool row only: the project rows are not read |
| L1 | RAILS lines of 1836 in Yorkshire, Lancashire, Midlands, Home Counties, East Anglia, Lowlands (railway states) | Mines and logging camps there have their levels on rail step 1 (`lv2=0/N` style, N = level) | All on step 0: the start placement did not fire (the railway flag was not set yet, or the setup flag was gone) |
| L2 | RAILS lines' `ltr=` from March 1836 | The state's own transportation price, different across states, 1.75 only where short | 1 everywhere: the local read never ran |
| L3 | PROJECT_OPEN lines with `rc` in British states with a railway, by 1838 | At least one, `pay>0` | None while `ltr<1.75`: the pay test still refuses; read why on the Automation hover (C6) |
| L4 | JOBS `lbm=` of a coal mine with every level on rail and none on equipment | -24 (3,000 fewer laborers a level) | -12: the old cut |
| L5 | PROJECT_OPEN lines at all for Great Britain in 1836 | At least one (q109 had none) | None: the first-sight log never fires for a player |

S15 (pace) and R9 carry over from q109: read them from the no-country stretch of step 4.

## Earlier: automation bought level by level, and the rules review (q109, test mod, played as GB to Jan 1844)

From the build thread, on your go of 14:29Z. Two things, each behind its own switch and off in every other build:

- **Automation bought level by level** (your 13:24Z "Level by level", 13:40Z "Shared laborers method" and 13:41Z
  price). On the 39 types with automation or railway steps, a step is bought as a "New Equipment" or "Rail
  Connection" project beside the retool site, one level per paid level, at a quarter of the building's construction
  cost. Laborers come from one shared method group; skilled posts stay in the recipe. A step that stops paying idles
  for free and resumes when it pays again. New levels arrive on the building's target steps; buildings on the map at
  game start begin with none.
- **The rules review, A to G**: projects and retools scored by their payoff (A), the free idle (B), one profit term in
  the investment score (C), the switching bar counted and on the clock (D), the newest recipe priced (E), Treatment
  as modifiers (F), and one method a recipe on 32 of the step types (G).

q109 is q108 with both, without the group probe. **Start a new game**: the projects and step counts set up on
1 January 1836.

1. Use the PMR Test playset and launch with -debug_mode. Start a new game as **Great Britain**.
2. In the first week, take a screenshot of a coal mine's building card (S5, F1, F3).
3. Play as Britain at any speed. On or after 1 July 1836, take a screenshot of the construction queue; if a row reads
   "New Equipment" or "Rail Connection", hover it and take one of its tooltip too (S6, S9). If a mine, farm, mill or
   plantation of yours is newly built while you play, a screenshot of its card in its first month (F3).
4. On 1 February 1837 switch to no country. From there to 1 February 1839 nothing else heavy runs on the PC and the
   game stays in front (S15).
5. Run on to 1 January 1851 (S10 reads to 1850; stop earlier if you need the PC and S10 reads to that year).
6. Close the game and tell the build thread.

Read `logs\error.log` first: a line naming `pmr_rl_`, `pmr_eq_`, `pmr_rc_`, `pmg_pmr_laborers`, `pm_pmr_lab_`,
`pmr_less_pol_`, `pmr_rg_`, `pmr_pay_`, `pmr_psc`, `pmr_bar_` or `pmr_tx` means that part never ran, and its nulls below
are then not results.

Lines: `PROJECT_OPEN` (a project opens, with `pay=` and `score=`), `PROJECT_QUEUE` (your government queues one),
`PROJECT_LEVEL` (a paid level lands), `IDLE` and `RESUME`, `RAILS` (each of your step-type buildings, about twice a
year: levels on each step, projects needed, built and queued, the laborers method), `JOBS` (monthly, your buildings:
jobs by pop type as the game reads them, and `lbm=`, the laborers method in steps of 125), `RUNGS` (yearly in the
observer stretch, every country: levels on each step), `SWITCH` and `TICK` (now with `pay=` and `score=`), `BAR`,
`TREAT`. PROJECT and IDLE lines come from your country while you play and from the largest economy after.

Automation (SPEC v4 section 7):

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| S1 | JOBS line of a building at rest on a step (`lbm` below 0) | `cap` within 62 a level of `want` (its frame plus the laborers method); `cap_<pop>` the recipe's | `cap` at the frame's laborers alone: the laborers group's jobs don't reach the building, or its method never switched |
| S2 | JOBS line in a month where a building's `frame` and `lbm` both changed | `cap` equals that month's `want` | Doubled or last month's: a group was switched twice, or a running method re-activated |
| S3 | PROJECT_LEVEL lines against the same building's next JOBS `lbm` | `lbm` moves toward the step's cut after each paid level | `lbm` stuck at its first value while levels land: the mix isn't called when a level lands |
| S4 | UNDO lines | None names a `pm_pmr_lab_` method | One does: the swap lock doesn't cover the laborers group |
| S5 | error.log, and the coal mine card (step 2) | No line; names and icons right; no laborers selector on the card | A missing key or a wrong name: the group needs per-type localisation |
| S6 | Construction queue screenshot, PROJECT_OPEN and PROJECT_QUEUE lines | A row reads "New Equipment: (type)" or "Rail Connection: (type)" once a project opens with room | PROJECT_OPEN lines all year and no project ever in a queue: the gate, room or potential is wrong (compare the retool site's) |
| S7 | PROJECT_LEVEL lines a year beside RETOOL_LEVEL, world | Both bought; RETOOL_LEVEL within q105's 30 to 76 | None bought while retools are: `PAY_TILT` too low. Retools under 15 a year: the projects starve them |
| S8 | Two RAILS lines of one building, and the PROJECT_LEVEL lines between | Levels on the target step rose by the paid levels plus any new levels | Rose by more: more than one level moves a paid level. No rise with levels paid (`built` climbs): paid levels pile up |
| S9 | The project row's tooltip (step 3) against a new level of that building | A quarter of its construction cost | Half: the retool site's figure is in use |
| S10 | RUNGS lines, 1837 to 1850 | Levels on step 1 and up appear as technologies land: grain farm tools and railway steps first | `eq` and `rc` past the first figure at 0 everywhere by 1850: the step test's wage or price read is wrong, check one building by hand from its PROFIT line. Every level on its top step at once: the test isn't applied |
| S10a | IDLE and RESUME lines | A building whose `buys` top its `saves` logs IDLE; its laborers return in that run (JOBS `lbm`); its levels stay on the step (RAILS); RESUME once it pays again | No IDLE line in a run with such a building: idling isn't wired. Levels leave the step: the counts were moved |
| S11 | PROFIT lines of a building at rest on a step against q108-1's, same recipe and step | Margin a level equal within prices | Higher by the step's goods: the goods modifiers aren't on. Lower: goods are cut twice |
| S12 | Wage read on a stepped building against a hand count from its PROFIT line | Within 5% | High: the laborers method's cut is missing from the crew count |
| S13 | RAILS `pol` of a building with levels on a polluting step (a mine's rail connection 10 a level, its steam donkey 5) | Each such step's pollution times its levels | 0 with levels on such a step: the pollution modifier isn't put |
| S14 | Vanilla automation events (those `vanilla_compat` rewrites) | Fire for a building with levels on the step | Never fire: the step check isn't reached |
| S15 | Pace, February 1837 to February 1839 with no country (the build thread times it) | Stated before the run: no slower a month than the spread between runs, against q105's same stretch | Slower: an install of q109 with the switches off follows, then the laborers group, then the projects, are turned off one at a time |
| S16 | Build thread, before install | With every switch off, the generated mod equals dev 3413b77's apart from the build stamp | Passed 2026-11-12 |

Rules review (`rules-review/HANDOFF.md`):

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| R1 | PROJECT_OPEN, SWITCH and TICK `pay=` and `score=`; purchase order over a year | Larger payoffs bought sooner | Order doesn't follow payoff: the score isn't reaching the picker |
| R2 | PROJECT_OPEN lines and the queue screenshot | No project with `pay` of 0 or less opens or shows | One does: the gate isn't in the private build check |
| R3 | Where New Equipment levels land (PROJECT_LEVEL, JOBS `occ` while you play) | Mostly where the building is under 80% staffed or the state lacks workers | Only where expansions also are: the engine's gates don't favour it |
| R4 | RETOOL_LEVEL lines a year, all countries | Within q105's 30 to 76 | Under 15 a year: payoffs score too low, raise `PAY_TILT` |
| R5 | Step purchases and IDLE/RESUME (with S10a) | A step that pays 1.0x to 1.25x is bought; a step at a loss logs IDLE with its working step | No IDLE line with a step at a loss: the fallback isn't wired |
| R6 | One autosave's candidate records against PROFIT lines | Profit per employee within 10% | More than a tenth of pairs off by over 10%: turn `--no-pterm` off |
| R7 | A year of BAR lines | Counts and red-bar ages logged | No BAR line: the count isn't wired. Restarts rare and red bars short: D saves only the watch |
| R8 | A building two recipes behind (a conquered or released state), if one occurs | The newest recipe is its target in one step (DEFAULT) | Two targets in a row: the newest isn't priced |
| R9 | S15 | As S15 | As S15; turn off G first |
| T1 | A TREAT line a year per plantation: shares and modifier sizes | Sizes follow the shares | Size 0 or absent with a share above 0: the tick doesn't set the modifier |
| T2 | A plantation's output against q108-1's at the same share | Within 2% | Unchanged by the share: the output modifier doesn't reach the building |
| T3 | Same plantation, the `read=` fields; wage, mortality and attractiveness against a Standard Labor plantation | Wage lower by the minimum-wage line; mortality and attractiveness moved | Wage unchanged: the minimum wage modifier is inert on a building, and you decide whether to drop that line |
| T4 | `slave` size and the state's slave import read, where Violent or Exploitative shares run | Present, sized by share | Absent: the state modifier isn't put |
| F1 | Coal mine card at rest with no step (step 2) | Only the recipe's goods | Zeroed step goods or -100% lines: turn `--one-frame` off (your q99 card complaint) |
| F2 | error.log, and vanilla events or journal entries that check a recipe method | No line; they fire as before | A missing key or a check that stops firing: keep the union frames |
| F3 | Inputs of the step-2 coal mine and of a newly built step-type building with no step | The recipe's goods only | Every step good at its largest amount: the method mix modifiers aren't set at creation or game start |

## Earlier: the investment window and a workforce figure per building (q108, test mod, ran 2026-11-12)

From the build thread, for the fundamentals review. Two things, each off in every other build:

- **The investment window** (you chose "Both, window first" at 03:46Z and "Today's timer, 6 to 8 months" at
  04:37Z). An AI building now looks at its recipe on news (research, a new level, electricity or a railway, a law),
  when its books turn (a loss, a subsidy, too few staff, or back in the black) and at its re-check every 6 to 8
  months. Between those it no longer watches prices, except while a switching bar fills. Your own buildings keep
  today's watch, so nothing changes on your screens.
- **The workforce probe** (your 04:21Z question, "Can't we just put every building into a building group?"). Textile
  mills sit in a building group of their own, and some British states get that group's employee multiplier, to see
  whether it moves one building type's jobs. Nothing else about textile mills changes.

q108 is q107 with both added; q107's K rows still need your q106 observer autosave and can run in q108 later.

1. Use the PMR Test playset and launch with -debug_mode. Start a **new game** as **Great Britain** (the probe sets
   up on 1 January 1836; an autosave won't do).
2. In the first week: open the construction menu's light industry list, and the Lancashire textile mill's building
   card. Take a screenshot of each (G5). If a treaty with a "build" article is easy to open, a screenshot of its
   list of building groups too (G6); skip it otherwise.
3. Play to 1 January 1837 at any speed. No timing is read, so other programs don't matter.
4. Close the game and tell the build thread.

Read `logs\error.log` first: any line naming `bg_pmr_g_`, `employee_mult` or `pmr_probe_gj` means that probe route
never ran, and any naming `pmr_bx`, `pmr_bxh`, `pmr_bxl`, `pmr_sgc_door`, `pmr_sgc_bar` or a division means the window's
watch or a door never ran. The nulls below are then not results.

Workforce probe (`PMR;rec=PROBE;p=Gsetup`, `p=G` and `p=GM` lines; Lancashire control, Midlands g1, Yorkshire g2,
Home Counties g3, West Country extra):

| # | Where | Pass | A null means |
| --- | --- | --- | --- |
| G0 | Lancashire (`role=control`) | `laborers_ratio` holds near 1 through July | If the control moves, the market moved every mill, and each route is read against it, not against 1 |
| G1 | Midlands (`role=g1`) | Every pop type's `_ratio` toward 0.5 within three months; `p=GM` `new` reads -0.50 | Held at 1 with -0.50 read: the engine applies the employee multiplier only for its own groups, so a workforce figure per building is dead and automation goes the throughput way. Held at 1 with -99 or an error.log line: the declaration was refused, same conclusion |
| G2 | Yorkshire (`role=g2`) | `ratio` near 0.75 by March, near 0.5 by June (`stage=1`), back toward 1 by October (`stage=2`) | 0.75 never left: a replaced modifier is not re-read, so the figure can't move every other month. No return after July: jobs cut this way don't come back on their own |
| G3 | Home Counties (`role=g3`) | The mill's `ratio` toward 0.5, and `other_ratio` (its furniture manufactory) too | `other_ratio` moves and the mill's doesn't: a parent's multiplier stops at a child group, so vanilla's own group modifiers would miss every re-grouped building |
| G4 | `p=Gsetup` lines; March's `p=GM` lines | `in_parent=1`, `in_top=1`, `in_own=1`, `other_in_own=0`; `thr` above 0 on a mill above level 1 wherever `thr_other` is above 0 | `in_parent=0`: a child doesn't count as its parent in triggers, and vanilla's group checks would miss the building: stop. `thr=0` with `thr_other` above 0: economy of scale was lost with the move. Both 0: the read can't see economy of scale, not a result. `thr_other=-99`: that state has no furniture manufactory |
| G5 | Your two screenshots | Textile mills listed in the light industry list as before; the card shows its usual throughput and infrastructure lines | Missing from the list: the group's lens didn't come through |
| G6 | Your treaty screenshot, if taken | The list of building groups is as in vanilla, with no second "Textile Mills" entry | A new entry: the engine lists every group there, and one group per building type would crowd it |

Investment window (`PMR;rec=SOLO`, `PROFIT`, `DEFAULT`, `SWITCH_START`, `RETOOL_LEVEL`):

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| Y1 | SOLO lines, 1836 | `door` above 0 in at least one month and `bar` above 0 in at least one month | `door=0` all year: the books never open a look, so buildings going into a loss wait for the timer. `bar=0` all year with SWITCH_START lines in the log: the watch isn't reached while a bar fills, so a pick no longer has to hold |
| Y2 | SOLO lines against q105's 1836 months | `lite` at roughly half of q105's (420 to 456 late in 1836); `held` and `end` near q105's | `lite` near q105's: the books move at almost every update, so the saving is smaller than replayed. `lite=0`: the books watch never fires and AI investment scores go stale |
| Y3 | PROFIT lines for Great Britain | Lines with `why=price` still appear | None in a year: your buildings lost their price watch |
| Y4 | DEFAULT and SWITCH_START lines; RETOOL_LEVEL for the world | Present; RETOOL_LEVEL within q105's 30 to 76 for the year | None: no building changes its default any more, the looks aren't happening. Compare `full` in the SOLO line with q105's 180 to 209 |
| Y5 | Only if the game runs on past 1837: runs.py compare with q105 | DEFAULT changes for the logged countries in q105's range | Far fewer: price-driven changes are being lost, not delayed |
| Y6 | Build thread, before install | Without `--window` the generated mod equals q107's apart from the build stamp | Passed 2026-11-12 (dev 4029e78) |

**Result (run q108-1, Great Britain to 1 Oct 1837; logs and verdicts in `/mnt/project-files/pmr/runs/logs/q108-1/README.md`):**
G0-G5 passed and G6 was not taken. A mod-made group's employee multiplier halves every pop type within a month (G1),
comes off at once (G2, rehiring stops near 89%) and is reached by a parent group's multiplier (G3). G3's shopkeeper
ratio prints 0.25 only because its January count came before PMR's first retool; it is 3,250 of 6,500 slots. Y1 and Y3
passed. Y2: `lite` was 0.61x q105's over March to December 1836, less saving than the half expected; `held` and `end`
were near. Y4: the lines were present; RETOOL_LEVEL was 23 in 1836 against q105's 30, and 32 from January to September
1837. Y5 was not run. Later test builds drop `--group-probe`.

## Earlier: administrations that wait for telephones (q107, test mod, K rows not yet run)

From the build thread, after your q106 observer game (Great Britain given every technology): PMR put the Midlands
administration straight on Switchboards with no telephones in its market. You chose "Follow supply" (22:12Z). Once a
country has Central Planning, its administrations now run a blend of Vertical Filing Cabinets and Switchboards in 10%
steps: at each state's update (every other month) a step toward Switchboards while telephones sell at least 75% of
their buy orders in the state's market, and a step back while they sell half or less; in between it holds. The earlier
methods are still taken at once. The blends are hidden from the method list unless one runs. q107 also makes the
Private Levels and By Owner legends add to 100% (q106 J7 read 97%).

1. Use the PMR Test playset and launch with -debug_mode. Load the last autosave of your q106 observer game and pick
   Great Britain.
2. Play four game months at any speed. Take a screenshot of the Midlands government administration's method list
   (K3) and of the Private tab (K4).
3. Close the game and tell the build thread.

Read `logs\error.log` first (K1).

| # | Do | Pass | A null means |
| --- | --- | --- | --- |
| K1 | error.log | No line naming `pmr_blend`, `pm_pmr_blend` or `pmr_sv_bfill` | Any of them: send back with the line |
| K2 | Nothing (logs) | `PMR;rec=BLEND` lines for Great Britain's states: an administration on Switchboards steps down (`step=-1`, `pos=29`, then `28`) while `fill_telephones` is 0.50 or less, and steps up while it is 0.75 or more. Home Counties (the capital) logs every update, holds as `step=0` | No BLEND line in four months: the blend never ran (error.log names `pmr_blend_government_administration`), send back. Lines from Home Counties only: the other states held, so their telephones sold between half and three quarters of their orders; read `fill_telephones` |
| K3 | The Midlands administration's method list | The running method reads "Switchboards 90%" (or lower), with the four vanilla methods beside it and no other blend listed | Nine or more "Switchboards N%" entries listed: the hidden flag did not hold, send back. Still "Switchboards" after four months: read K2 first |
| K4 | Private tab: Private Levels and By Owner legends | Every legend's shares add to 100% | 97 to 99%: the shares fix did not load, send back |

The q106 rows not yet seen (J1, J4, J5, J6) can run in the same game: queue a government retool in the first weeks.

## Still open from q104 and q106

These read as written for their own build. A null that names "the q105 files" now means an old install.

| # | Read | Pass | A null means |
| --- | --- | --- | --- |
| J1 | Open a government retool site from the construction queue's row | Its method reads "Retooling" with the saw icon | The pink face and "Should never be shown in UI": the q105 files are still installed, send back |
| J2 | Private tab: the two graphs, then hover each one's line | A gold line across each graph at the latest value; while the transfer is under its peak, a red "-X below peak" tag at the right end. The tooltip: the graph's name, "£X currently", and the red "below peak" line only when under the peak | No gold line or tag: the graph's parts did not load (error.log names `v3_plotline_current_value`), send back. A tag at the peak: send back with the screenshot |
| J4 | A building with a government retool queued, before its first level has moved, then after | Before: the bar's title is the method it runs, as with no retool, and its tooltip has "To retool". After: "N% on (method)" | "0% on (method)" over a full bar: the q105 files are still installed, send back |
| J5 | Hover the building's greyed Retool button once every level is queued | "@green_checkmark! 2 of 2 levels queued", not red | A red cross and "All N levels queued": the q105 files are still installed, send back |
| J6 | Company Culture: a locked node past another | The red line reads "Requires (node)" | "Needs (node)": send back |
| J7 | Private tab: Private Levels and By Owner; then Recent Investments once something is built | No text on the tree tiles; the legends name every slice. In Recent Investments each chart's shares add to 100%, and 0% rows are grey | Tile text: send back. Shares adding to 99%: the shares effect did not run (error.log names `pmr_pi_shares`), send back |
| J9 | Policies tab: hover a method's or a method pair's cell | Money in the short form ("£1.34K per level a week") | "£1349 per level a week": send back |
| G3 | In G2's tooltip, hover the underlined "Retool Government Levels" | A "Retooling" tooltip, three lines | No underline and no tooltip: the concept file did not load (error.log names `concept_pmr_retooling`); the text still reads, send back |
| G6 | Policies tab: a card's New Default bar, its Investment Chance figure and an owner's share | "New Default: (method)", the divider, "+N% profit over (method)", "N of 6 months"; Investment Chance "N% (w of total)", the divider and "from" rows; the owner "N% of new private levels" | Key names or a blank tooltip: send back |
| G7 | G1's bar and a Policies card, for colour | Tiers in bronze, ochre, steel blue, dusty rose, slate teal and parchment, no green or red; every slice tells from its neighbour | Two slices that look alike: name them, the next build steps them apart |
| P2 | Private tab: a policy card past its 60-month lock, Cancel Policy, then No | A Yes/No box headed "Cancel Policy"; No keeps the policy; Change Policy has no tooltip | The policy goes with no question: the confirmation was skipped, send back. Nothing opens: error.log names `pmr_policy_cancel`. No button while the lock runs: by design, not a result |
