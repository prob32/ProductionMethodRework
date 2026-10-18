# PMR run sheet: automation pays at 1836 wages, PMR translated into every game language, the automation tech gate, Company Culture tab on every company (test mod), one retool site per building with a paid crew so investors can add levels, hidden from the Buildings tab (test mod), your investors retool abroad, companies list their additional industries' retooling, the target follows your best recipe, the Foreign or Domestic bar as a multiplier with a 3-month lock, Arts Academies, power plants and Urban Centers, your government retooling abroad, retooling abroad, priorities on a timer and locked by law, policy costs and Agrarianism policies, ports and railways retool, administration, universities and trade centres always on their best method, Laissez-faire policies and Recent Investments as tree maps, the Private tab (fifth round) and your recipes abroad in the Owners list, retooling what you own abroad, the Private tab (fourth round), faster monthly ticks and a timing test, the Private construction tab (third round), trade-offs pre-loaded from your 1838 save, vanilla group names on the second bar, faster trade-offs, plantation treatment by acceptance, trade-offs by local prices

Every line PMR writes goes to `Documents\Paradox Interactive\Victoria 3\logs\debug.log` and starts
with `PMR;rec=`. Filter with:

```
findstr /C:"PMR;rec=" "%USERPROFILE%\Documents\Paradox Interactive\Victoria 3\logs\debug.log"
```

Also check `logs\error.log` for any line containing `pmr_` before reading anything else: a script
error there means the mechanism below never ran, and a missing log line is then not a result.

## Latest: automation pays for itself (q18, test mod; a new game shows it from the start)

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

## Also new since q16: PMR's text in every game language (q17)

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
