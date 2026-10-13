"""Generate the Production Method Rework (PMR) mod from the installed game's own script.

PMR is generated, not hand-written, because it touches every recipe production method in the
game and must follow the beta as it moves. Run it against the game folder of the build you are
testing; it rewrites the mod folder in place.

    python tools/pmr/generate.py --game "G:/SteamLibrary/steamapps/common/Victoria 3/game"

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
   then the lock to the new step, so the running share method is never left locked out.
4. Hidden pseudo-buildings retool one level each per completed level, at RETOOL_SHARE of the
   building's construction cost: RETOOL_SLOTS private ones, ``building_pmr_retool_<b>_<n>``, built
   by investors who own part of the building, each with a fixed crew (RETOOL_CREW) so investors can
   expand it, and one government one, ``building_pmr_retool_gov_<b>``, queued by the government.
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
import glob
import json
import re
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import icons  # noqa: E402
import pdx  # noqa: E402

# ---------------------------------------------------------------------------------------------
# Tunables. Change here and regenerate; nothing below hard-codes them.
N = 1                      # retool levels per real building level (Pat, 2026-10-12: one per level)
RETOOL_SHARE = 0.5         # retooling one level costs this share of the building's construction cost
GOV_FRACTION_STEP = 0.05   # resolution of the government-owned share read from the ownership trigger
RETOOL_AI_VALUE = 1000000  # AI weight of a retool building while it has room; vanilla's default is 1000
SHARE_STEPS = 100          # a recipe's share of the levels is blended in steps of 1 / SHARE_STEPS (1%, Pat 2026-10-13)
RETOOL_SLOTS = 4           # private retool buildings per building type; each starts as one new construction
# Pat, 2026-10-13: private retool buildings get a crew so investors can expand them. 1.14.5's AI
# expands no building under PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD (0.8) employment unless it
# hired last week, and a building under MINIMUM_EMPLOYEES (10) employees always tries to hire, even
# one that earns nothing, as a retool building does. So the crew is fixed at 10, not per level
# ("unscaled"): it stays fully employed however many levels the building has.
RETOOL_CREW = 10
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
# Pat, 2026-10-13: a recipe that needs electricity (its own goods, its folded automation, or vanilla's
# required_input_goods) can't become a building's target unless its state produces electricity, and
# retooling towards it pauses while the state has none. One rule for government and private retooling.
ELECTRICITY = 'electricity'
# Log-only probes for the next batch (Pat approved both 2026-10-13). They change nothing in game; each
# writes one line a month per player-owned state where it applies.
# TREAT: each plantation's workforce by acceptance band, for plantation treatment by acceptance
# (pmr/treatment-by-acceptance.md). Acceptance below TREAT_BANDS[0] (levels 1-2) is the violent band,
# below TREAT_BANDS[1] (level 3) the harsh band, the rest standard (Pat's levels).
PROBE_TREAT = True
TREAT_BANDS = (40, 60)
# PRICE: the local price of PRICE_PROBE_GOODS, read through the state_goods_pricier/cheaper ladder the
# market blend of the trade-off groups will use (pmr/second-groups.md), where PRICE_PROBE_BUILDING stands.
PROBE_PRICE = True
PRICE_PROBE_BUILDING = 'building_logging_camp'
PRICE_PROBE_GOODS = ('hardwood', 'wood')
PRICE_STEP = 5             # ladder resolution, % of base price; the game clamps prices to +-75%
GOV_RETOOL_ICON = 'gfx/interface/icons/formation_order_icons/upgrade.dds'
RETOOL_CREW_ICON = 'gfx/interface/icons/production_method_icons/wooden_buildings.dds'

MOD_NAME = 'ProductionMethodRework'
MOD_VERSION = '0.1.0'
SUPPORTED_VERSION = '1.14.*'

# Building files whose buildings make goods from goods. Government, military, urban, monuments,
# canals, infrastructure, subsistence, companies and the construction sector are out of scope:
# their first group is not a goods recipe, or retooling them through construction is circular.
BUILDING_FILES = ['01_industry.txt', '02_agro.txt', '03_mines.txt', '04_plantations.txt',
                  '09_misc_resource.txt']

GENERIC_ICON = 'gfx/interface/icons/generic_icons/mixed_icon_base.dds'
RETOOL_BACKGROUND = 'gfx/interface/icons/building_icons/backgrounds/building_panel_bg_monuments.dds'

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_OUT = os.path.join(ROOT, 'pmr', MOD_NAME)


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


def fmt(x):
    s = f'{x:.5f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def short(building_key):
    return building_key[len('building_'):] if building_key.startswith('building_') else building_key


# ---------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--game', required=True, help='path to the Victoria 3 "game" folder')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--version-label', default='', help='game build label written into the README header')
    args = ap.parse_args()
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
    pms = {}
    for s in p_srcs:
        for k, n in s.objects().items():
            pms[k] = (n, s)

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

    report = {'treated': [], 'skipped': [], 'blended': [], 'icon_fallback': []}
    treated = []          # (building_key, building_node, building_src, [Recipe])
    candidates = []
    for s in b_srcs:
        for bk, bn in s.objects().items():
            pg = pdx.get(bn.value, 'production_method_groups')
            if not pg or not pdx.items(pg):
                continue
            candidates.append((bk, bn, s, pdx.items(pg)[0], pg))
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
        if not recipes[0].employment:
            report['skipped'].append({'building': bk, 'reason': f'default recipe {lst[0]} carries no employment'})
            continue
        treated.append((bk, bn, s, recipes, g0, pg))

    # ---- edit vanilla: strip recipe employment and goods, add the labour and share groups -------
    # The vanilla recipe methods keep only what is not scaled by workforce: they mark the recipe
    # the building runs (the retool target) and gate it by technology. Their goods and other
    # workforce-scaled modifiers move into the share methods.
    stripped = set()
    automation = {}   # building -> the automation methods folded into its recipes from AUTOMATION_FROM_TIER
    elec_pms = []     # the electric recipes' marker methods (ElectricRecipe), one per building that has one
    for bk, bn, s, recipes, g0, pg in treated:
        for r in recipes:
            if r.key not in stripped:
                r.strip_employment()
                r.strip_blend()
                r.strip_required()
                stripped.add(r.key)
        auto_groups = [g for g in pdx.items(pg) if g != g0 and 'automation' in g]
        if len(recipes) >= AUTOMATION_FROM_TIER and auto_groups:
            # Pat, 2026-10-13: recipes from AUTOMATION_FROM_TIER fold the best automation that runs
            # without electricity; automation that needs it (assembly lines, power looms) becomes a
            # recipe of its own on top of the newest one (ElectricRecipe).
            tops = [Recipe(groups[g][-1], *pms[groups[g][-1]]) for g in auto_groups]
            folded = []
            for g in auto_groups:
                plain = [p for p in groups[g] if not Recipe(p, *pms[p]).needs(ELECTRICITY)]
                folded.append(Recipe(plain[-1], *pms[plain[-1]]) if plain else None)
            automation[bk] = [a for a in folded if a is not None]
            for n in pg.value:
                if n.key is None and n.value in auto_groups:
                    s.cuts.append(line_span(s.text, n))
            entry = {'building': bk, 'groups': auto_groups, 'folded': [a.key for a in automation[bk]],
                     'from_tier': AUTOMATION_FROM_TIER}
            if any(a.needs(ELECTRICITY) for a in tops):
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
        # Last in the list: one share group and one lock group per recipe.
        s.inserts.append((pg.end - 1, ''.join(
            f'\tpmg_pmr_share_{short(bk)}_{i}  # PMR: share of levels on {r.key}\n\t'
            f'\tpmg_pmr_key_{short(bk)}_{i}  # PMR: lock for that share\n\t'
            for i, r in enumerate(recipes, 1))))

    if os.path.isdir(args.out):
        for sub in ('common', 'localization', '.metadata', 'gfx', 'gui'):
            shutil.rmtree(os.path.join(args.out, sub), ignore_errors=True)
    os.makedirs(args.out, exist_ok=True)

    def write(rel, text, bom=True):
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
        if s.cuts:
            write(f'common/production_methods/{s.name}', s.render())
    # Vanilla recipe groups that gain an electric recipe, whole, with only its line inserted.
    for s in g_srcs:
        if s.inserts:
            write(f'common/production_method_groups/{s.name}', s.render())
    write('common/production_methods/pmr_electric_production_methods.txt', header + ELECTRIC_DOC
          + '\n'.join(er.method() for er in elec_pms))

    # ---- new script ------------------------------------------------------------------------------
    labour_pms, labour_groups, retools, costs, loc = [], [], [], [], []
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

    goods_tex = {}
    for gsrc in load_dir(game, 'goods'):
        for gk, gn in gsrc.objects().items():
            t = pdx.get(gn.value, 'texture')
            if t:
                goods_tex[gk] = t.value
    gfx_root = game
    custom_new = []
    recipe_keys, recipe_tex, recipe_elec = {}, {}, {}

    for bk, bn, s, recipes, g0, pg in treated:
        b = short(bk)
        r0 = recipes[0]
        # The fixed labour method's icon: the building's main output good, drawn gold.
        good = max(r0.outputs.items(), key=lambda kv: kv[1])[0] if r0.outputs else None
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
        recipe_tex[bk] = [r.texture for r in recipes]
        if len(recipes) > len(TIER_COLORS):
            raise SystemExit(f'{bk}: {len(recipes)} recipes, but TIER_COLORS has {len(TIER_COLORS)}; add a colour')
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
        triggers.append(retool_triggers(b, bk))
        costs.append(retool_values(b))

        for rbx in priv_slots(b):
            loc += [f' {rbx}:0 "Retooling: ${bk}$"',
                    f' {rbx}_desc:0 "Privately funded construction that switches one level of ${bk}$ to its newest recipe. Investors from countries that own part of the building fund the privately owned share. A crew of {RETOOL_CREW} keeps it staffed so investors can add more levels to it."']
        for r in recipes:
            if isinstance(r, ElectricRecipe):
                loc.append(f' {r.key}:0 "' + ' + '.join(f'${x.key}$' for x in [r.base] + r.autos) + '"')
        loc += [f' pmg_pmr_labour_{b}:0 "Recipes"',
                f' pm_pmr_labour_{b}:0 "Blended Recipes"',
                f' building_pmr_retool_gov_{b}:0 "Retooling (Government): ${bk}$"',
                f' building_pmr_retool_gov_{b}_desc:0 "Government construction that switches the government-owned share of ${bk}$ to a new recipe. Each completed level moves the old recipe\'s output closer to the new one."']

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
        elec_tiers = []
        for i, r in enumerate(recipes, 1):
            if isinstance(r, ElectricRecipe):
                autos = r.autos
                blend, emp, elec, clamped = effective(r.base, autos)
            else:
                autos = automation.get(bk, []) if i >= AUTOMATION_FROM_TIER else []
                blend, emp, elec, clamped = effective(r, autos)
            if elec:
                elec_tiers.append(i)
            if clamped:
                report.setdefault('employment_clamped', []).append({'building': bk, 'recipe': r.key, 'below_zero': clamped})
            default_n = SHARE_STEPS if i == 1 else 0
            shares, keys = [], []
            any_key = f'pm_pmr_key_{b}_{i}_any'
            secs = list(dict.fromkeys(list(blend) + (['building_modifiers'] if emp else [])))
            for n in range(SHARE_STEPS + 1):
                f = n / SHARE_STEPS
                body = ''.join(
                    f'\t{sec} = {{\n'
                    + (f'\t\tworkforce_scaled = {{\n'
                       + ''.join(f'\t\t\t{mk} = {fmt(mv * f)}\n' for mk, mv in blend[sec].items())
                       + '\t\t}\n' if sec in blend else '')
                    + (f'\t\tlevel_scaled = {{\n'
                       + ''.join(f'\t\t\t{mk} = {fmt(mv * f)}\n' for mk, mv in emp.items())
                       + '\t\t}\n' if sec == 'building_modifiers' and emp else '')
                    + '\t}\n'
                    for sec in secs if n > 0)
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
                loc += [f' pm_pmr_share_{b}_{i}_{n}:0 "${r.key}$ ({pct}% of levels)"',
                        f' pm_pmr_key_{b}_{i}_{n}:0 "${r.key}$ share lock ({pct}%)"']
            blend_pms.append(f'{any_key} = {{\n\ttexture = "{GENERIC_ICON}"\n}}\n')
            keys.append(any_key)
            loc.append(f' {any_key}:0 "${r.key}$ share lock (switching)"')
            # No is_hidden_when_unavailable: with it, a share group lists only its one unlocked method,
            # and the building panel, which shows a PMR building's groups of exactly one method (the
            # fixed labour slot), drew every share group's icon in the row (seen in 1.14.5).
            for g, lst, what in ((f'pmg_pmr_share_{b}_{i}', shares, 'share of levels'),
                                 (f'pmg_pmr_key_{b}_{i}', keys, 'share lock')):
                blend_groups.append(f'{g} = {{\n\ttexture = "{GENERIC_ICON}"\n'
                                    '\tproduction_methods = {\n' + ''.join(f'\t\t{x}\n' for x in lst) + '\t}\n}\n')
                loc.append(f' {g}:0 "${r.key}$ {what}"')
            report['blended'].append({'building': bk, 'recipe': r.key, 'tier': i, 'blend': blend,
                                      'employment': emp, 'automation': [a.key for a in autos],
                                      'needs_electricity': elec})

        tick_effects.append(tick_effect(bk, b, recipes, elec_tiers))
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
    # private retool buildings are listed beside it, rewriting the vanilla company files with only
    # those lines inserted. Off 2026-10-12 to keep Retooling icons out of the company panels; on again
    # 2026-10-13 (Pat): the autonomous investment AI favours expanding a building a company lists
    # (AUTONOMOUS_INVESTMENT_COMPANY_TARGET_STATE_WITH_BUILDING_CONSTRUCTION_FACTOR), which is how
    # retool levels stack. A company-owned building retools either way: its headquarters owns levels
    # the way a Financial District does, so levels_owned_by_country counts them for its country.
    report['company_types'] = []
    if COMPANY_RETOOL:
        retool_of = {t[0]: priv_slots(short(t[0]))[:COMPANY_RETOOL_SLOTS] for t in treated}
        for csrc in load_dir(game, 'company_types'):
            for ck, cn in csrc.objects().items():
                bt = pdx.get(cn.value, 'building_types')
                if not bt or not bt.is_block:
                    continue
                listed = pdx.items(bt)
                new = [(x, rbx) for x in listed if x in retool_of for rbx in retool_of[x] if rbx not in listed]
                if not new:
                    continue
                csrc.inserts.append((bt.end - 1, ''.join(f'\t{rbx}  # PMR: retooling of {x}\n\t' for x, rbx in new)))
                report['company_types'].append({'company': ck, 'file': csrc.name, 'added': [rbx for _, rbx in new]})
            if csrc.inserts:
                write(f'common/company_types/{csrc.name}', csrc.render())

    write('common/production_methods/pmr_labour_production_methods.txt', header + '\n'.join(labour_pms))
    write('common/production_method_groups/pmr_labour_groups.txt', header + '\n'.join(labour_groups))
    write('common/buildings/pmr_retool_buildings.txt', header + '\n'.join(retools))
    write('common/production_methods/pmr_retool_production_methods.txt', header + RETOOL_CREW_DOC +
          'pm_pmr_retool_crew = {\n'
          f'\ttexture = "{RETOOL_CREW_ICON}"\n'
          '\tbuilding_modifiers = {\n\t\tunscaled = {\n'
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
          'bg_pmr_retool = {\n\tparent_group = bg_manufacturing\n\tcategory = urban\n\tis_government_funded = no\n'
          '\talways_possible = yes\n\tis_shown_in_outliner = no\n}\n\n'
          '# The government-owned share is retooled by the government: the player builds it from the state,\n'
          '# AI governments by ai_value. Shaped on bg_government, which is how vanilla marks government-only\n'
          '# construction; the lens puts it in the development construction list.\n'
          'bg_pmr_retool_gov = {\n\tcategory = urban\n\tis_government_funded = yes\n\talways_possible = yes\n'
          '\tlens = development\n\tis_shown_in_outliner = no\n}\n')
    write('common/scripted_triggers/pmr_triggers.txt', header + RETOOL_TRIGGERS_DOC + '\n'.join(triggers))
    write('common/script_values/pmr_values.txt', header +
          f'pmr_retool_levels_per_level = {N}\n\n' + '\n'.join(costs) + '\n')
    write('common/production_methods/pmr_blend_production_methods.txt', header +
          '# Share methods: pm_pmr_share_<b>_<recipe>_<n> carries the recipe\'s workforce-scaled\n'
          f'# modifiers x n / {SHARE_STEPS}. Each unlocks while pm_pmr_key_<b>_<recipe>_<n>\n'
          '# or the switching lock pm_pmr_key_<b>_<recipe>_any is active.\n\n'
          + '\n'.join(blend_pms))
    write('common/production_method_groups/pmr_blend_groups.txt', header + '\n'.join(blend_groups))
    write('common/scripted_effects/pmr_effects.txt', header + shared_effects() + '\n'.join(tick_effects)
          + dispatch_effects(dispatch) + '\n' + COUNT_QUEUES)
    write('common/on_actions/pmr_on_actions.txt', header + ON_ACTIONS)
    treat = treatment_buildings(all_b_srcs, groups, pms)
    goods_cost = {}
    for gs in load_dir(game, 'goods'):
        for gk, gn in gs.objects().items():
            c = pdx.get(gn.value, 'cost')
            if c is not None:
                goods_cost[gk] = num(c.value, f'{gk} cost')
    report['probe_treat'] = [t[0] for t in treat]
    write('common/script_values/pmr_probe_values.txt', header + probe_values(treat))
    write('common/scripted_effects/pmr_probe_effects.txt', header + probe_effects(treat, pms, goods_cost))
    write('common/scripted_guis/pmr_sguis.txt', header + SGUI_DOC + ''.join(gov_retool_sgui(bk) for bk in dispatch)
          + '# The same for every state at once, from the Buildings tab\'s building type row. Country scope.\n\n'
          + ''.join(gov_retool_country_sgui(bk) for bk in dispatch))
    write('common/customizable_localization/pmr_custom_loc.txt', header +
          '# Building scope. The recipe a building runs, which is the one any retooling moves it to.\n'
          'pmr_new_recipe = {\n\ttype = building\n\tlog_loc_errors = no\n' + ''.join(custom_new) + '}\n')
    write('gui/building_details_panel.gui', patch_building_panel(
        recipe_tex, open(os.path.join(game, 'gui', 'building_details_panel.gui'), encoding='utf-8-sig').read()),
        bom=False)
    def vanilla_gui(name):
        return open(os.path.join(game, 'gui', name), encoding='utf-8-sig').read()
    # The Buildings tab: the building type row's grid (the first of three) becomes the country recipe
    # bar, and the upgrade button goes left of nationalize. Expanded, each building's row is the
    # details panel's condensed_building_information, recipe row and button included.
    write('gui/production_methods.gui', patch_type_row_buttons(patch_type_grids(
        vanilla_gui('production_methods.gui'), dispatch, 'production_methods.gui', 3,
        replace={0: lambda bk, gind, vis: type_bar(bk, recipe_tex[bk])(bk, gind, vis)}), dispatch), bom=False)
    # Building browser rows: the labour icon with the recipe bar beside it in the production method
    # column (220 wide), and the government upgrade button left of nationalize.
    browser_bars = ''.join(
        f'\t\t\t\t# PMR: recipe bar for {bk}\n\t\t\t\twidget = {{\n'
        f'\t\t\t\t\tvisible = "[{is_type(bk)}]"\n\t\t\t\t\tposition = {{ 56 0 }}\n'
        f'\t\t\t\t\tsize = {{ 156 24 }}\n\t\t\t\t\tparentanchor = vcenter\n'
        + stacked_bar(short(bk), recipe_tex[bk], ('100%', '100%'), 18, '\t\t\t\t\t') + '\t\t\t\t}\n'
        for bk in dispatch)
    write('gui/building_browser_panel.gui', patch_browser_actions(patch_grid_instance(
        patch_type_grids(vanilla_gui('building_browser_panel.gui'), dispatch, 'building_browser_panel.gui', 1),
        dispatch, '\t\t\t', 'building_browser_panel.gui', outer=(214, 50), cell=50, anchor='vcenter',
        extra=browser_bars), dispatch), bom=False)
    write('gui/goods_state_panel.gui', patch_building_grids(vanilla_gui('goods_state_panel.gui'), dispatch,
                                                            'goods_state_panel.gui', 1), bom=False)
    loc += panel_loc(recipe_keys)
    write('common/decisions/pmr_test_decisions.txt', header + DECISIONS)
    loc += [' bg_pmr_retool:0 "Retooling"', ' bg_pmr_retool_gov:0 "Government Retooling"'] + DECISION_LOC
    write('localization/english/pmr_l_english.yml', 'l_english:\n' + '\n'.join(loc) + '\n')

    write('descriptor.mod', f'version="{MOD_VERSION}"\ntags={{\n\t"Gameplay"\n\t"Economy"\n}}\n'
          f'name="Production Method Rework"\nsupported_version="{SUPPORTED_VERSION}"\n', bom=False)
    write('.metadata/metadata.json', json.dumps({
        'name': 'Production Method Rework', 'id': 'org.prob32.pmr', 'version': MOD_VERSION,
        'game_id': 'victoria3', 'supported_game_version': SUPPORTED_VERSION,
        'short_description': 'Fixed labour, tech-swapped recipes, and recipe switches that take effect '
                             'gradually as retooling construction completes.',
        'tags': ['Gameplay', 'Economy'], 'relationships': [],
        'game_custom_data': {'multiplayer_synchronized': True}}, indent=2) + '\n', bom=False)
    report['settings'] = {'N': N, 'retool_share': RETOOL_SHARE, 'gov_fraction_step': GOV_FRACTION_STEP,
                          'game': args.version_label}
    write('GENERATION_REPORT.json', json.dumps(report, indent=1) + '\n', bom=False)
    print(f"treated {len(report['treated'])} buildings, skipped {len(report['skipped'])}, "
          f"{len(report['blended'])} recipes blended by share ({len(blend_pms)} methods), "
          f"{len(report['company_types'])} company types may own retooling")


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
    return (f'if = {{ limit = {{ owner = {{ is_player = yes }} }} '
            f'debug_log = "PMR;rec={rec};date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={bk};'
            f"to={v('pmr_to', 0)};level={v('pmr_level', 0)};levels={levels};"
            f"p={v('pmr_p', 3)};to_retool={v('pmr_need', 0)}{extra}\" }}")


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
# pmr_retool_room_priv_<b>_<n>: the same for private retool building n, against pmr_cap_priv<n>_<b>.
# pmr_retool_investor_<b>: true when scope:investor_country's investors own part of the building, so
# an investment agreement alone does not let a foreign pool retool it.

"""


RETOOL_CREW_DOC = f"""# The crew of a private retool building: {RETOOL_CREW} {RETOOL_CREW_POP} whatever its level ("unscaled"; vanilla
# documents unscaled building_modifiers but uses them only for other modifiers). 1.14.5 always lets a
# building with fewer than MINIMUM_EMPLOYEES (10) employees hire, though a retool building earns
# nothing, and its AI expands only buildings at PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD (0.8)
# employment or that hired last week.

"""


def priv_slots(b):
    """The private retool building types of one building type."""
    return [f'building_pmr_retool_{b}_{j}' for j in range(1, RETOOL_SLOTS + 1)]


def retool_buildings(b, bk, icon):
    out = []
    sides = [('priv', 'bg_pmr_retool', rbx, j) for j, rbx in enumerate(priv_slots(b), 1)]
    sides.append(('gov', 'bg_pmr_retool_gov', f'building_pmr_retool_gov_{b}', 0))
    for side, group, rb, j in sides:
        if side == 'priv':
            flag = f'pmr_retool_open_priv_{b}_{j}'
            who = ('\t# Private investors only, for the privately owned share. Every building vanilla lets private\n'
                   '\t# investors build says ownership_type = self.\n'
                   '\townership_type = self\n'
                   f'\tcan_build_government = {{ always = no }}\n'
                   '\t# This one open, room left under its cap, and only investors from a country whose investors\n'
                   '\t# own part of the building.\n'
                   f'\tcan_build_private = {{\n\t\thas_variable = {flag}\n\t\tpmr_retool_room_priv_{b}_{j} = yes\n'
                   f'\t\tpmr_retool_investor_{b} = yes\n\t}}\n')
            pmgs = 'pmg_pmr_retool_crew'
        else:
            flag = f'pmr_retool_open_gov_{b}'
            who = ('\t# The government only, for the government-owned share.\n'
                   f'\tcan_build_government = {{ pmr_retool_room_gov_{b} = yes }}\n'
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
            f'\t# Open only while script is retooling a {bk} in this state.\n'
            f'\tpotential = {{ has_variable = pmr_retool_gate_{b} }}\n'
            + who +
            '\t# Very attractive while there is room, so investors (or an AI government) pick it first.\n'
            f'\tai_value = {{\n\t\tvalue = 0\n\t\tif = {{\n\t\t\tlimit = {{ has_variable = {flag} }}\n'
            f'\t\t\tvalue = {RETOOL_AI_VALUE}\n\t\t}}\n\t}}\n'
            f'\trequired_construction = pmr_retool_cost_{b}\n'
            f'\tproduction_method_groups = {{\n\t\t{pmgs}\n\t}}\n'
            f'\tbackground = "{RETOOL_BACKGROUND}"\n}}\n')
    return '\n'.join(out)


def retool_triggers(b, bk):
    rbg = f'building_pmr_retool_gov_{b}'
    cap = f'pmr_cap_gov_{b}'
    out = [
        f'pmr_retool_room_gov_{b} = {{\n'
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
            f'\tis_valid = {{ has_variable = pmr_retool_open_gov_{b} }}\n'
            f'\teffect = {{ pmr_queue_gov_{b} = yes }}\n}}\n\n')


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



def tick_effect(bk, b, recipes, elec_tiers=()):
    """Every effect for one building type. All run in STATE scope.

    The state keeps how many of the building's levels run each recipe (pmr_lv_<i>_<b>, i = the
    recipe's position in vanilla's group, oldest first). The building's active recipe is the
    target (pmr_to_<b>); every level on another recipe still needs retooling. Each completed retool
    level moves one level, oldest recipe first, onto the target. A newer recipe arriving mid-retool
    only changes the target: levels already moved keep their recipe until retooled again.
    Each recipe's share of the levels picks the method active in that recipe's share group, so the
    building's goods are the level-weighted mix of its recipes in its own production figures."""
    k = len(recipes)
    slots = list(enumerate(priv_slots(b), 1))
    rbg = f'building_pmr_retool_gov_{b}'
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
    for i in range(1, k + 1):
        o.append(f'\t{setv(f"pmr_a_{i}", -1)}\n'
                 + bisect(v(f'pmr_n_{i}'), lambda n, i=i: f'if = {{ limit = {{ {pm_active("share", i, n)} }} {setv(f"pmr_a_{i}", n)} }}', '\t'))
    o.append('}\n\n')

    # pmr_lock_<i>_<b>: recipe i's lock onto the step the tick wants.
    for i in range(1, k + 1):
        o.append(f'pmr_lock_{i}_{b} = {{\n'
                 + bisect(v(f'pmr_n_{i}'), lambda n, i=i: act("key", i, n), '\t') + '}\n\n')

    o.append(f'pmr_blend_{b} = {{\n\t{setv("pmr_ncum", 0)}\n')
    for i in range(1, k + 1):
        o.append(f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:{v("pmr_to")} = {i} }} }}\n'
                 f'\t\t{setv(f"pmr_n_{i}", "var:" + v(f"pmr_sh_{i}"))}\n'
                 f'\t\t{chg(f"pmr_n_{i}", "multiply", SHARE_STEPS)}\n'
                 f'\t\tround_variable = {{ name = {v(f"pmr_n_{i}")} nearest = 1 }}\n'
                 f'\t\t{setv("pmr_nrest", SHARE_STEPS)}\n'
                 f'\t\t{chg("pmr_nrest", "subtract", "var:" + v("pmr_ncum"))}\n'
                 f'\t\tif = {{ limit = {{ var:{v(f"pmr_n_{i}")} > var:{v("pmr_nrest")} }} {setv(f"pmr_n_{i}", "var:" + v("pmr_nrest"))} }}\n'
                 f'\t\t{chg("pmr_ncum", "add", "var:" + v(f"pmr_n_{i}"))}\n\t}}\n')
    o.append(on_index('pmr_to', lambda i: f'{setv(f"pmr_n_{i}", SHARE_STEPS)} {chg(f"pmr_n_{i}", "subtract", "var:" + v("pmr_ncum"))}'))
    o.append(f'\tpmr_read_blend_{b} = yes\n')
    for i in range(1, k + 1):
        o.append(f'\t# recipe {i}: if its share is not the one wanted, unlock every share, switch, lock again;\n'
                 '\t# if only the lock moved (the AI took the switching lock), lock again\n'
                 f'\tif = {{\n\t\tlimit = {{ var:{v(f"pmr_a_{i}")} = -1 }}\n'
                 f'\t\tif = {{ limit = {{ NOT = {{ {pm_active("key", i, "any")} }} }} {act("key", i, "any")} }}\n'
                 + bisect(v(f'pmr_n_{i}'), lambda n, i=i: act("share", i, n), '\t\t')
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
    o.append(f'pmr_read_gov_{b} = {{\n\t{setv("pmr_gov_frac", 0)}\n')
    for n in range(steps, 0, -1):
        frac = n * GOV_FRACTION_STEP
        kw = 'if' if n == steps else 'else_if'
        o.append(f'\t{kw} = {{ limit = {{ b:{bk} = {{ country_ownership_fraction >= {fmt(frac - GOV_FRACTION_STEP / 2)} }} }} '
                 f'{setv("pmr_gov_frac", fmt(frac))} }}\n')
    o.append('\t# Government-owned levels, which the state owner\'s count in levels_owned_by_country includes.\n'
             f'\tset_variable = {{ name = {v("pmr_gov_levels")} value = b:{bk}.level }}\n'
             f'\t{chg("pmr_gov_levels", "multiply", "var:" + v("pmr_gov_frac"))}\n'
             f'\tround_variable = {{ name = {v("pmr_gov_levels")} nearest = 1 }}\n'
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
             + ''.join(read_side(rbx, f'priv{j}') for j, rbx in slots) + read_side(rbg, 'gov') + totals() +
             '}\n\n')

    # A government retool building whose levels are all counted and with nothing queued on it is
    # removed, so the next government level is a new construction. A private one stays, so its crew
    # (RETOOL_CREW) lets investors expand it, unless the crew is still short RETOOL_CREW_GRACE_DAYS
    # after its last level landed: then it goes too, and its next level is a new construction, as
    # before the crew existed (1.14.5's pool never expanded a crewless retool building). Never removed
    # while anything is queued on it (that leaves a NULL_STATE construction).
    def release(rbx, side, keep=''):
        seen = 'pmr_seen_gov' if side == 'gov' else 'pmr_seen_priv'
        return (f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_retool_built_" + side)} > 0 '
                f'var:{v("pmr_retool_q_" + side)} <= var:{v("pmr_retool_built_" + side)} {keep}'
                f'OR = {{ has_building = {rbx} exists = b:{rbx} }} }}\n'
                f'\t\tremove_building = {rbx}\n'
                f'\t\t{chg(seen, "subtract", "var:" + v("pmr_retool_built_" + side))}\n'
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
             + ''.join(crew(j, rbx) for j, rbx in slots)
             + count('gov') + count('priv')
             + f'\t{setv("pmr_gain", 0)}\n\t{setv("pmr_ggain", 0)}\n'
             + ''.join(convert('pmr_conv_gov', i, True) for i in range(1, k + 1))
             + ''.join(convert('pmr_conv_priv', i, False) for i in range(1, k + 1))
             + f'\t{chg("pmr_conv_priv", "add", "var:" + v("pmr_conv_gov"))}\n'
             + ''.join(convert('pmr_conv_priv', i, False) for i in range(1, k + 1))
             + ''.join(convert('pmr_conv_priv', i, True) for i in range(1, k + 1))
             + on_index('pmr_to', lambda i: f'change_variable = {{ name = {lv(i)} add = var:{v("pmr_gain")} }} '
                                            f'change_variable = {{ name = {lvg(i)} add = var:{v("pmr_ggain")} }}')
             + ''.join(release(rbx, f'priv{j}', keep_crew(j)) for j, rbx in slots) + release(rbg, 'gov')
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
             + '\t# privately owned levels per recipe, for the Owners list\n'
             + ''.join(f'\t{setv(f"pmr_lvp_{i}", "var:" + lv(i))}\n\t{chg(f"pmr_lvp_{i}", "subtract", "var:" + lvg(i))}\n'
                       for i in range(1, k + 1))
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
             '\t# Diagnostic: may the home investment pool fund this building\'s private retooling?\n'
             '\towner = { save_temporary_scope_as = investor_country }\n'
             f'\tif = {{ limit = {{ pmr_retool_investor_{b} = yes }} {setv("pmr_inv_home", 1)} }}\n'
             f'\telse = {{ {setv("pmr_inv_home", 0)} }}\n'
             f'\t{setv("pmr_room_gov", "var:" + v("pmr_retool_gov"))}\n'
             f'\t{chg("pmr_room_gov", "subtract", "var:" + v("pmr_pending_gov"))}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_room_gov")} < 0 }} {setv("pmr_room_gov", 0)} }}\n'
             + clamp_to("pmr_room_gov", "pmr_room") +
             f'\t{setv("pmr_room_priv", "var:" + v("pmr_room"))}\n'
             f'\t{chg("pmr_room_priv", "subtract", "var:" + v("pmr_room_gov"))}\n'
             f'\t{setv("pmr_cap_gov", "var:" + v("pmr_retool_q_gov"))}\n'
             f'\t{chg("pmr_cap_gov", "add", "var:" + v("pmr_room_gov"))}\n'
             f'\tset_variable = pmr_retool_gate_{b}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_room_gov")} > 0 }} set_variable = pmr_retool_open_gov_{b} }}\n'
             f'\telse_if = {{ limit = {{ has_variable = pmr_retool_open_gov_{b} }} remove_variable = pmr_retool_open_gov_{b} }}\n'
             '\t# Private: each empty retool building may take one level, as a new construction; the rest\n'
             '\t# of the room goes to the first one with a finished level, whose crew lets investors\n'
             '\t# expand it. Each gets a cap (pmr_cap_priv<j>_<b>) of what it has plus its share.\n'
             f'\t{setv("pmr_slots_left", "var:" + v("pmr_room_priv"))}\n'
             + ''.join(f'\t{setv(f"pmr_alloc{j}", 0)}\n' for j, _ in slots)
             + ''.join(f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_slots_left")} > 0 var:{v(f"pmr_retool_q_priv{j}")} <= 0 }}\n'
                       f'\t\t{setv(f"pmr_alloc{j}", 1)}\n\t\t{chg("pmr_slots_left", "subtract", 1)}\n\t}}\n'
                       for j, _ in slots)
             + ''.join(f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_slots_left")} > 0 var:{v(f"pmr_retool_built_priv{j}")} > 0 }}\n'
                       f'\t\t{chg(f"pmr_alloc{j}", "add", "var:" + v("pmr_slots_left"))}\n\t\t{setv("pmr_slots_left", 0)}\n\t}}\n'
                       for j, _ in slots)
             + ''.join(f'\tset_variable = {{ name = pmr_cap_priv{j}_{b} value = var:{v(f"pmr_retool_q_priv{j}")} }}\n'
                       f'\tchange_variable = {{ name = pmr_cap_priv{j}_{b} add = var:{v(f"pmr_alloc{j}")} }}\n'
                       f'\tif = {{ limit = {{ var:{v(f"pmr_alloc{j}")} > 0 }} set_variable = pmr_retool_open_priv_{b}_{j} }}\n'
                       f'\telse_if = {{ limit = {{ has_variable = pmr_retool_open_priv_{b}_{j} }} remove_variable = pmr_retool_open_priv_{b}_{j} }}\n'
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
                       for rbx, side in [(rbx, f'priv{j}') for j, rbx in slots] + [(rbg, 'gov')])
             + f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_pending")} <= 0 }}\n'
             f'\t\t{setv("pmr_seen_gov", 0)}\n\t\t{setv("pmr_seen_priv", 0)}\n'
             + ''.join(f'\t\tif = {{ limit = {{ has_variable = {n} }} remove_variable = {n} }}\n'
                       for n in (f'pmr_retool_gate_{b}', v('pmr_cap_gov'), v('pmr_gov_levels'))) +
             '\t}\n}\n\n')

    # newest recipe the building runs or can activate; vanilla lists recipes oldest first. A recipe
    # that needs electricity counts only while the state produces it (pmr_elec, read by the tick).
    o.append(f'pmr_best_{b} = {{\n\t{setv("pmr_best_now", 0)}\n')
    for i in range(k, 0, -1):
        r = recipes[i - 1]
        kw = 'if' if i == k else 'else_if'
        can = f'can_activate_production_method = {{ building_type = {bk} production_method = {r.key} }}'
        if getattr(r, 'techs', None):
            # the electric recipe: its newest recipe's and its automation's technologies, all of them
            can = (f'AND = {{ {can} owner = {{ '
                   + ' '.join(f'has_technology_researched = {t}' for t in r.techs) + ' } }')
        if i in elec_tiers:
            can = f'AND = {{ {can} var:pmr_elec = 1 }}'
        o.append(f'\t{kw} = {{\n\t\tlimit = {{ OR = {{\n\t\t\t{active(r)}\n'
                 f'\t\t\t{can}\n'
                 f'\t\t}} }}\n\t\t{setv("pmr_best_now", i)}\n\t}}\n')
    o.append('}\n\n')

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
    mix = (';blend=' + '/'.join(f(f'pmr_n_{i}') for i in range(1, k + 1))
           + ';active=' + '/'.join(f(f'pmr_a_{i}') for i in range(1, k + 1)))
    best = f";best={f('pmr_best_now')}" + mix
    split = mix + (f";gov_frac={f('pmr_gov_frac', 2)};gov_levels={f('pmr_gov_levels')}"
             f";share_gov={f('pmr_retool_gov')};share_priv={f('pmr_retool_priv')}"
             f";queued_gov={f('pmr_pending_gov')};queued_priv={f('pmr_pending_priv')}"
             f";room_gov={f('pmr_room_gov')};room_priv={f('pmr_room_priv')}"
             + ';gov_lv=' + '/'.join(f(f'pmr_lvg_{i}') for i in range(1, k + 1))
             + ';slots=' + '/'.join(f(f'pmr_retool_q_priv{j}') for j in range(1, RETOOL_SLOTS + 1))
             + ';crew=' + '/'.join(f(f'pmr_staff_priv{j}') for j in range(1, RETOOL_SLOTS + 1))
             + f";elec=[THIS.Var('pmr_elec').GetValue|0]" + (f";elec_wait={f('pmr_elec_wait')}" if elec_tiers else '')
             + f";home_investors={f('pmr_inv_home')};pool=[THIS.Var('pmr_pool').GetValue|0]"
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
             f'\t{setv("pmr_level", f"b:{bk}.level")}\n'
             '\tpmr_read_elec = yes\n'
             f'\tpmr_best_{b} = yes\n'
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
             f'\t\t\t{setv("pmr_adopting", 0)}\n'
             f'\t\t\tpmr_activate_{b} = yes\n'
             f'\t\t\tpmr_mix_{b} = yes\n'
             f'\t\t\t{log("ADOPT", bk, b, k)}\n\t\t}}\n'
             f'\t\tpmr_mix_{b} = yes\n'
             f'\t\t{log("INIT", bk, b, k, extra=best)}\n\t}}\n'
             f'\tif = {{ limit = {{ has_variable = {v("pmr_new_build")} }} remove_variable = {v("pmr_new_build")} }}\n')

    o.append('\t# Research: a newer recipe became available since the last tick. Switch to it; the switch\n'
             '\t# below then opens retooling like any other.\n'
             f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_best_now")} > var:{v("pmr_best")} }}\n'
             f'\t\t{setv("pmr_best", "var:" + v("pmr_best_now"))}\n'
             f'\t\t{log("RESEARCH", bk, b, k, extra=best)}\n'
             f'\t\tpmr_activate_{b} = yes\n\t}}\n'
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
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {v("pmr_adopting")} }} var:{v("pmr_run")} > 0 '
             f'NOT = {{ var:{v("pmr_run")} = var:{v("pmr_to")} }} }}\n'
             f'\t\t{setv("pmr_to", "var:" + v("pmr_run"))}\n'
             f'\t\tset_variable = {v("pmr_switched")}\n\t}}\n')

    o.append(f'\tpmr_sync_levels_{b} = yes\n'
             f'\tpmr_read_gov_{b} = yes\n'
             f'\tpmr_sync_gov_{b} = yes\n'
             f'\tpmr_progress_{b} = yes\n'
             f'\tpmr_mix_{b} = yes\n'
             f'\tpmr_blend_{b} = yes\n'
             f'\tpmr_read_blend_{b} = yes\n'
             f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_need")} > 0 }}\n'
             f'\t\tset_variable = {v("pmr_retooling")}\n'
             f'\t\tpmr_split_retool_{b} = yes\n'
             f'\t\tif = {{ limit = {{ has_variable = {v("pmr_switched")} }} {log("SWITCH", bk, b, k, extra=split)} }}\n'
             f'\t\telse = {{ {log("TICK", bk, b, k, extra=split)} }}\n'
             '\t}\n'
             '\telse = {\n'
             f'\t\tpmr_close_retool_{b} = yes\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = {v("pmr_retooling")} }}\n'
             f'\t\t\tremove_variable = {v("pmr_retooling")}\n'
             f'\t\t\t{log("DONE", bk, b, k, extra=done)}\n'
             '\t\t}\n'
             f'\t\telse_if = {{ limit = {{ has_variable = {v("pmr_switched")} }} {log("CANCEL", bk, b, k, extra=mix)} }}\n'
             '\t}\n'
             f'\tif = {{ limit = {{ has_variable = {v("pmr_switched")} }} remove_variable = {v("pmr_switched")} }}\n'
             '}\n\n')
    # Country scope: the player's totals over every state with this building, for the Buildings tab
    # row (its recipe bar and upgrade button). Recomputed after each single tick, and once for all
    # building types after the ticks that run state by state (pmr_bulk; see pmr_c_sum_all).
    o.append(f'pmr_c_sum_{b} = {{\n'
             + ''.join(f'\tset_variable = {{ name = pmr_c_{n}_{b} value = 0 }}\n'
                       for n in ['level', 'need', 'room_gov'] + [f'lv_{i}' for i in range(1, k + 1)])
             + f'\tevery_scope_state = {{\n\t\tlimit = {{ has_variable = pmr_mix_{b} has_building = {bk} b:{bk} = {{ level >= 1 }} }}\n'
             '\t\tsave_temporary_scope_as = pmr_st\n\t\towner = {\n'
             + ''.join(f'\t\t\tchange_variable = {{ name = pmr_c_{n}_{b} add = scope:pmr_st.var:pmr_{n}_{b} }}\n'
                       for n in ['level', 'need'] + [f'lv_{i}' for i in range(1, k + 1)])
             + '\t\t}\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_retool_open_gov_{b} has_variable = pmr_room_gov_{b} }}\n'
             f'\t\t\towner = {{ change_variable = {{ name = pmr_c_room_gov_{b} add = scope:pmr_st.var:pmr_room_gov_{b} }} }}\n'
             '\t\t}\n\t}\n'
             + ''.join(f'\tset_variable = {{ name = pmr_c_sh_{i}_{b} value = 0 }}\n' for i in range(1, k + 1))
             + f'\tif = {{\n\t\tlimit = {{ var:pmr_c_level_{b} > 0 }}\n'
             + ''.join(f'\t\tset_variable = {{ name = pmr_c_sh_{i}_{b} value = var:pmr_c_lv_{i}_{b} }}\n'
                       f'\t\tchange_variable = {{ name = pmr_c_sh_{i}_{b} divide = var:pmr_c_level_{b} }}\n'
                       for i in range(1, k + 1))
             + '\t}\n'
             f'\tif = {{ limit = {{ var:pmr_c_need_{b} > 0 }} set_variable = {{ name = pmr_c_retooling_{b} value = 1 }} }}\n'
             f'\telse = {{ set_variable = {{ name = pmr_c_retooling_{b} value = 0 }} }}\n'
             '}\n\n')

    # The guarded entry point, after the body it calls (every scripted effect here is defined before use).
    o.append(f'pmr_tick_{b} = {{\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = pmr_busy_{b} }} }}\n'
             f'\t\tset_variable = {{ name = pmr_busy_{b} value = yes days = 1 }}\n'
             f'\t\tpmr_tick_body_{b} = yes\n'
             f'\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_bulk }} owner = {{ is_player = yes }} }} owner = {{ pmr_c_sum_{b} = yes }} }}\n'
             f'\t\tremove_variable = pmr_busy_{b}\n\t}}\n}}\n\n')

    # The government upgrade button (pmr_gov_retool_<b>_sgui): queue every government retool level
    # the building still needs, as if the player had built them one by one, then tick so the room,
    # and with it the button, drops to nothing.
    o.append(f'pmr_queue_gov_{b} = {{\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_retool_open_gov_{b} }}\n'
             f'\t\t{setv("pmr_q", "var:" + v("pmr_room_gov"))}\n'
             f'\t\t{log("GOV_QUEUE", bk, b, k, extra=";queueing=" + f("pmr_q"))}\n'
             f'\t\twhile = {{\n\t\t\tlimit = {{ var:{v("pmr_q")} > 0 }}\n'
             f'\t\t\tstart_building_construction = {rbg}\n'
             f'\t\t\t{chg("pmr_q", "subtract", 1)}\n\t\t}}\n'
             f'\t\tremove_variable = {v("pmr_q")}\n'
             f'\t\tpmr_tick_{b} = yes\n\t}}\n}}\n\n')
    return ''.join(o)


def shared_effects():
    return '''# State scope. pmr_elec: 1 while the state produces electricity (a local good, so only the state's
# own power plants count). pmr_pool: the owner's investment pool by order of magnitude, and pmr_unemp:
# the state's unemployment rate in % (lower bound of 1/2/5/10/20), for the log. The investment pool
# scores a building x0.25 in a state short of workers, which can cost a retool site with a crew a pick.
pmr_read_elec = {
	if = {
		limit = { exists = sg:electricity sg:electricity = { state_goods_production > 0 } }
		set_variable = { name = pmr_elec value = 1 }
	}
	else = { set_variable = { name = pmr_elec value = 0 } }
	set_variable = { name = pmr_pool value = 0 }
''' + ''.join(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ owner = {{ investment_pool >= {x} }} }} set_variable = {{ name = pmr_pool value = {x} }} }}\n'
              for j, x in enumerate((100000, 10000, 1000, 100))) + \
        '\tset_variable = { name = pmr_unemp value = 0 }\n' + \
        ''.join(f'\t{"if" if j == 0 else "else_if"} = {{ limit = {{ state_unemployment_rate > {fmt(x / 100)} }} set_variable = {{ name = pmr_unemp value = {x} }} }}\n'
                for j, x in enumerate((20, 10, 5, 2, 1))) + '}\n\n'


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
        types = priv_slots(b) + [f'building_pmr_retool_gov_{b}']
        o.append(f'\t{kw} = {{\n\t\tlimit = {{ OR = {{ ' + ' '.join(f'is_building_type = {t}' for t in types) + ' } }\n'
                 f'\t\tstate = {{ if = {{ limit = {{ {live(bk)} }} pmr_tick_{b} = yes }} }}\n\t}}\n')
    o.append('}\n\n'
             '# State scope: tick every PMR building in the state. Run state by state over a country (monthly, on\n'
             '# research, at game start), so the country totals wait for pmr_c_sum_all once the states are done.\n'
             'pmr_state_tick = {\n\tset_variable = pmr_bulk\n')
    for bk in buildings:
        o.append(f'\tif = {{ limit = {{ {live(bk)} }} pmr_tick_{short(bk)} = yes }}\n')
    o.append('\tremove_variable = pmr_bulk\n}\n\n'
             '# Country scope: the country\'s totals for every PMR building type (Buildings tab rows).\n'
             'pmr_c_sum_every = {\n')
    for bk in buildings:
        o.append(f'\tpmr_c_sum_{short(bk)} = yes\n')
    o.append('}\n\n'
             '# The same for a player\'s country only (monthly, on research).\n'
             'pmr_c_sum_all = {\n\tif = {\n\t\tlimit = { is_player = yes }\n'
             '\t\tpmr_c_sum_every = yes\n'
             '\t\tdebug_log = "PMR;rec=CSUM;date=[TimeKeeper.GetCurrentDate.GetString]"\n'
             '\t}\n}\n')
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
    o.append(''.join(f'\tif = {{ limit = {{ has_variable = {n} }} remove_variable = {n} }}\n' for n in tvars)
             + '}\n\n')

    steps = list(range(75, 0, -PRICE_STEP))
    o.append(f'# PRICE: where {PRICE_PROBE_BUILDING} stands, the local price of each probed good against its base,\n'
             f'# in steps of {PRICE_STEP}%: f reads the ladder with thresholds written as fractions (0.05 = 5%),\n'
             '# p with the same thresholds written as percent (5 = 5%), because the docs don\'t say which\n'
             '# state_goods_pricier means. Vanilla writes "state_goods_pricier > 0.5" (railways), which\n'
             '# suggests fractions; then p reads 0 for every good.\n'
             'pmr_probe_price = {\n'
             f'\tif = {{\n\t\tlimit = {{ has_building = {PRICE_PROBE_BUILDING} b:{PRICE_PROBE_BUILDING} = {{ level >= 1 }} }}\n')
    for good in PRICE_PROBE_GOODS:
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
    items = []
    for i, tex in enumerate(textures, 1):
        name, (r, g, bl) = TIER_COLORS[i - 1]
        sh = var(f'pmr_sh_{i}')
        items.append(
            f'{ind}\t\t# tier {i}, {name.lower()}\n'
            f'{ind}\t\thbox = {{\n'
            f'{ind}\t\t\tvisible = "[GreaterThan_CFixedPoint({sh}, \'(CFixedPoint)0\')]"\n'
            f'{ind}\t\t\tlayoutpolicy_horizontal = expanding\n{ind}\t\t\tlayoutpolicy_vertical = expanding\n'
            f'{ind}\t\t\tlayoutstretchfactor_horizontal = "[FixedPointToInt(Multiply_CFixedPoint({sh}, \'(CFixedPoint)100\'))]"\n'
            f'{ind}\t\t\talwaystransparent = yes\n'
            f'{ind}\t\t\tbackground = {{\n'
            f'{ind}\t\t\t\ttexture = "gfx/interface/tooltip/stacked_barchart_small_item.dds"\n'
            f'{ind}\t\t\t\tcolor = {{ {r} {g} {bl} 1 }}\n'
            f'{ind}\t\t\t\tspriteborder = {{ 3 3 }}\n'
            f'{ind}\t\t\t\tusing = simple_frame_mask\n{ind}\t\t\t\tusing = progressbar_texture_properties\n'
            f'{ind}\t\t\t}}\n'
            f'{ind}\t\t\ticon = {{\n'
            f'{ind}\t\t\t\tvisible = "[GreaterThan_CFixedPoint({sh}, \'(CFixedPoint){RECIPE_ICON_SHARE}\')]"\n'
            f'{ind}\t\t\t\tsize = {{ {icon} {icon} }}\n'
            f'{ind}\t\t\t\talwaystransparent = yes\n'
            f'{ind}\t\t\t\ttexture = "{tex}"\n'
            f'{ind}\t\t\t}}\n'
            f'{ind}\t\t}}\n')
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


def gov_button(b, size, ind, place=''):
    """The government upgrade button: queues every government retool level the building still
    needs (pmr_gov_retool_<b>_sgui). Greyed out unless the state is the player's and the government
    has room left, which needs government-owned levels still to retool."""
    sgui = f"GetScriptedGui('pmr_gov_retool_{b}_sgui')"
    scope = 'GuiScope.SetRoot(Building.GetState.MakeScope).End'
    return (f'{ind}button_icon_round = {{\n{place}'
            f'{ind}\tsize = {{ {size} {size} }}\n'
            f'{ind}\tenabled = "[And(ObjectsEqual(Building.GetState.GetOwner.Self, GetPlayer.Self), {sgui}.IsValid({scope}))]"\n'
            f'{ind}\tonclick = "[{sgui}.Execute({scope})]"\n'
            f'{ind}\ttooltip = "PMR_GOV_RETOOL_TOOLTIP_{b}"\n'
            f'{ind}\tusing = tooltip_ne\n'
            f'{ind}\tusing = confirm_button_sound\n'
            f'{ind}\tblockoverride "icon" {{\n{ind}\t\ttexture = "{GOV_RETOOL_ICON}"\n{ind}\t}}\n'
            f'{ind}\tblockoverride "icon_size" {{\n{ind}\t\tsize = {{ 80% 80% }}\n{ind}\t}}\n'
            f'{ind}}}\n')


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


def patch_grid_instance(text, buildings, ind, name, outer, cell, anchor='', extra='', labour_icon=True):
    """The one use of vanilla's condensed_building_information_pms in a GUI file, at indent ind: on a
    PMR building type it is hidden and the fixed labour icon stands in its place. The grid inside is
    a fixedgridbox, which keeps a column for every production method group even when the item is
    hidden: with a share and a lock group per recipe, an iron mine's 13 groups made the details
    panel's row 936 px wide and pushed the panel's contents off its left edge (seen in 1.14.5).
    Hiding the grid's items is therefore not enough; the whole grid goes."""
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
    hide = text[:at] + f'{ind}\t# PMR: no grid on PMR building types\n{ind}\tvisible = "[Not({any_type(buildings)})]"\n'
    if not labour_icon:
        return hide + text[at:]
    return hide + text[at:end] + labour + text[end:]


def patch_building_panel(recipe_tex, text):
    buildings = list(recipe_tex)
    """Vanilla building_details_panel.gui with two changes, asserted so a game update that moves
    either anchor fails generation instead of shipping a panel that silently lost them."""
    # 1. The production method row: no grid on a PMR building type, and nothing in its place (Pat,
    # 2026-10-13: no goods icon; the recipe row below takes the room).
    text = patch_grid_instance(text, buildings, '\t\t\t\t\t', 'building_details_panel.gui', outer=(208, 70), cell=70,
                               labour_icon=False)
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
    return patch_owners(text, recipe_tex)


# Pat, 2026-10-13: a Production Method column in the Owners list, with the icons of the recipes each
# owner's levels run. PMR knows the government's levels per recipe (pmr_lvg_*) and the private ones
# only together (pmr_lvp_*), so a government row shows the government's recipes and every private
# row the private owners' together. On a PMR building type the vanilla header and rows are hidden
# and these drawn instead, with the columns narrowed to make room: owner 230 (icon 30 + name 200),
# production method 120, levels owned 90, dividends 100, the panel's 540.
OWN_NAME_W, OWN_PM_W, OWN_LEVELS_W = 200, 120, 90


def owners_cell(bk, textures):
    b = short(bk)
    rows = []
    for side, gov in (('gov', True), ('priv', False)):
        who = 'BuildingOwnership.IsCountryOwned' if gov else 'Not(BuildingOwnership.IsCountryOwned)'
        name = 'pmr_lvg' if gov else 'pmr_lvp'
        icons = ''.join(
            '\t\t\t\t\t\t\t\t\ticon = {\n'
            f"\t\t\t\t\t\t\t\t\t\tvisible = \"[GreaterThan_CFixedPoint({state_var(b, f'{name}_{i}')}, '(CFixedPoint)0')]\"\n"
            f'\t\t\t\t\t\t\t\t\t\tsize = {{ 26 26 }}\n\t\t\t\t\t\t\t\t\t\ttexture = "{tex}"\n'
            '\t\t\t\t\t\t\t\t\t}\n' for i, tex in enumerate(textures, 1))
        rows.append('\t\t\t\t\t\t\t\tflowcontainer = {\n'
                    f'\t\t\t\t\t\t\t\t\tvisible = "[And({is_type(bk)}, {who})]"\n'
                    '\t\t\t\t\t\t\t\t\tparentanchor = center\n\t\t\t\t\t\t\t\t\tspacing = 2\n'
                    f'\t\t\t\t\t\t\t\t\ttooltip = "PMR_OWNERS_{side.upper()}_TOOLTIP_{b}"\n'
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
    buttons = ''.join(f'{ind}\twidget = {{\n{ind}\t\tvisible = "[{is_type(bk)}]"\n{ind}\t\tsize = {{ 100% 100% }}\n'
                      + gov_button(short(bk), 35, ind + '\t\t', f'{ind}\t\t\tparentanchor = center\n')
                      + f'{ind}\t}}\n' for bk in buildings)
    once('\t\t\t\tflowcontainer = {\n\t\t\t\t\t### NATIONALIZE\n',
         '\t\t\t\tflowcontainer = {\n'
         f'{ind}ignoreinvisible = yes  # PMR\n'
         f'{ind}# PMR: government upgrade button\n{ind}widget = {{\n{ind}\tvisible = "[{any_type(buildings)}]"\n'
         f'{ind}\tsize = {{ 35 35 }}\n' + buttons + f'{ind}}}\n\n{ind}### NATIONALIZE\n')
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


def patch_type_grids(text, buildings, name, expected, replace=None):
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

    any_expr = is_bt(buildings[-1])
    for bk in reversed(buildings[:-1]):
        any_expr = f'Or({is_bt(bk)}, {any_expr})'
    for m in pattern.finditer(text):
        grid = text.rfind('fixedgridbox = {', 0, m.start())
        inner = text.index('\n', grid) + 1
        end = block_end(text, grid)
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


def patch_building_grids(text, buildings, name, expected):
    """A vanilla GUI file's per-building production method lists (Building context): on PMR building
    types only single-method groups (the fixed labour slot) show. Asserted per file."""
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
        ' PMR_LABOUR_ICON_TOOLTIP:0 "#bold Blended recipes#!\\nGoods and workforce here are the mix of the recipes the levels run, as the recipe bar shows. Recipes from the third on include full automation."',
        ' PMR_BAR_FULL_TOOLTIP:0 "Every level runs #bold [Building.GetCustom(\'pmr_new_recipe\')]#!."',
        ' PMR_RECIPE_BAR_TOOLTIP:0 "This building runs #bold [Building.GetCustom(\'pmr_new_recipe\')]#!. When your country researches a newer recipe it switches automatically, and the change takes effect as retooling construction completes. A recipe that needs electricity waits until this state produces it."',
    ]
    for bk, keys in recipe_keys.items():
        b = short(bk)

        def var(name, f):
            return f"[Building.GetState.MakeScope.Var('{name}_{b}').GetValue|{f}]"
        tiers = ''.join(f'\\n{TIER_COLORS[i - 1][0]}, ${key}$: #bold {var(f"pmr_sh_{i}", "%0")}#!'
                        for i, key in enumerate(keys, 1))
        gov = (f'Government: #bold {var("pmr_pending_gov", "0")}#! queued, room for #bold {var("pmr_room_gov", "0")}#! more.')
        loc += [
            f' PMR_RECIPE_BAR_TITLE_RETOOLING_{b}:0 "#bold {var("pmr_p", "%0")}#! on #bold [Building.GetCustom(\'pmr_new_recipe\')]#!"',
            f' PMR_BAR_TOOLTIP_{b}:0 "#bold Levels by recipe#!{tiers}'
            f'\\n\\nLevels still to retool to [Building.GetCustom(\'pmr_new_recipe\')]: #bold {var("pmr_need", "0")}#!'
            f'\\n\\nPrivate investors: #bold {var("pmr_pending_priv", "0")}#! queued, room for #bold {var("pmr_room_priv", "0")}#! more. Only investors who own part of this building fund these, from the investment pool. A crew of {RETOOL_CREW} keeps each private retooling site staffed, so investors can add levels to it.'
            f'\\n{gov} Queue them all with the upgrade button beside the recipe name, or build #bold $building_pmr_retool_gov_{b}$#! in this state yourself."',
            f' PMR_GOV_RETOOL_TOOLTIP_{b}:0 "#bold Retool the government\'s levels#!'
            f'\\nQueues every government retooling level this building still needs in your government construction queue: #bold {var("pmr_room_gov", "0")}#! now.'
            f'\\n\\n{gov} Privately owned levels are retooled by their investors.'
            f'\\n\\nUnavailable when the government\'s own levels already run the new recipe, it has already queued them all, the new recipe needs electricity and this state produces none, or the state is not yours."',
            f' PMR_OWNERS_GOV_TOOLTIP_{b}:0 "#bold Government-owned levels by recipe#!'
            + ''.join(f'\\n${key}$: #bold {var(f"pmr_lvg_{i}", "0")}#!' for i, key in enumerate(keys, 1)) + '"',
            f' PMR_OWNERS_PRIV_TOOLTIP_{b}:0 "#bold Privately owned levels by recipe#!'
            + ''.join(f'\\n${key}$: #bold {var(f"pmr_lvp_{i}", "0")}#!' for i, key in enumerate(keys, 1))
            + '\\n\\nAll private owners together: retooling is tracked for the government and for private owners, not owner by owner."',
        ]

        def cvar(name, f):
            return f"[GetPlayer.MakeScope.Var('{name}_{b}').GetValue|{f}]"
        ctiers = ''.join(f'\\n{TIER_COLORS[i - 1][0]}, ${key}$: #bold {cvar(f"pmr_c_sh_{i}", "%0")}#!'
                         for i, key in enumerate(keys, 1))
        loc += [
            f' PMR_CBAR_TOOLTIP_{b}:0 "#bold Levels by recipe in your country#!{ctiers}'
            f'\\n\\n#bold {cvar("pmr_c_level", "0")}#! levels in your states, #bold {cvar("pmr_c_need", "0")}#! still to retool.'
            f'\\nGovernment retooling the upgrade button would queue now: #bold {cvar("pmr_c_room_gov", "0")}#! levels."',
            f' PMR_GOV_RETOOL_C_TOOLTIP_{b}:0 "#bold Retool the government\'s levels everywhere#!'
            f'\\nQueues every government retooling level your ${bk}$ still need, in every state, in your government construction queue: #bold {cvar("pmr_c_room_gov", "0")}#! now.'
            f'\\n\\nUnavailable when no state has government-owned levels left to queue (or its new recipe is waiting for electricity)."',
        ]
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
		every_country = {
			every_scope_state = { pmr_state_tick = yes }
			pmr_c_sum_every = yes
		}
	}
}

# Root = building whose production method changed. The switch is seen the moment it happens.
pmr_on_production_method_changed = {
	effect = {
		pmr_tick_building = yes
	}
}

# Root = building whose first level just completed. A new retool building moves p at once, and a
# new PMR building is seen without waiting for the month.
pmr_on_building_built = {
	effect = {
		pmr_built_building = yes
		# Last: the parent's tick can remove this retool building once its level is counted.
		pmr_tick_parent_of_retool = yes
	}
}

# Root = building that just completed a further level. on_building_built fires only for a
# building's first level, so without this every later retool level waited for the month to turn.
pmr_on_building_expanded = {
	effect = {
		pmr_built_building = yes
		# Last: the parent's tick can remove this retool building once its level is counted.
		pmr_tick_parent_of_retool = yes
	}
}

# Root = country that just acquired a technology. A newly unlocked recipe switches its buildings
# at once instead of at the next month turn.
pmr_on_acquired_technology = {
	effect = {
		every_scope_state = { pmr_state_tick = yes }
		pmr_c_sum_all = yes
	}
}

# Root = state. Backstop: recompute the shares and re-apply the blend once a month even if no event fired.
pmr_on_monthly_pulse_state = {
	effect = {
		pmr_state_tick = yes
		pmr_probe_state = yes
	}
}

# Root = country. The player's totals for the Buildings tab rows, once the month's state ticks are in
# (whichever pulse runs first, a change made only by the monthly tick shows within a month).
pmr_on_monthly_pulse_country = {
	effect = {
		pmr_c_sum_all = yes
	}
}
'''

DECISIONS = '''# Test decisions. The AI never takes them (ai_chance 0). Each writes PMR;rec=TEST lines to debug.log.

pmr_test_setup_decision = {
	is_shown = { always = yes }
	possible = { always = yes }
	when_taken = {
		# The mill first, seen on Blister; then Bessemer, so the next tick sees the research.
		capital = {
			if = {
				limit = { NOT = { has_building = building_steel_mill } }
				# Government-owned, so retooling it is the government's to queue.
				create_building = {
					building = building_steel_mill
					add_ownership = { country = { country = root levels = 5 } }
				}
			}
			pmr_state_tick = yes
			debug_log = "PMR;rec=TEST;arm=SETUP;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting]"
		}
		add_technology_researched = bessemer_process
		capital = { pmr_state_tick = yes }
	}
	ai_chance = { value = 0 }
}

# A newer recipe arriving mid-retool: the levels already on Bessemer stay on it, and every level
# not on Open Hearth is now to retool.
pmr_test_open_hearth_decision = {
	is_shown = { has_technology_researched = bessemer_process }
	possible = { always = yes }
	when_taken = {
		add_technology_researched = open_hearth_process
		capital = {
			debug_log = "PMR;rec=TEST;arm=OPEN_HEARTH;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting]"
		}
		every_scope_state = { pmr_state_tick = yes }
	}
	ai_chance = { value = 0 }
}

pmr_test_tick_decision = {
	is_shown = { always = yes }
	possible = { always = yes }
	when_taken = {
		every_scope_state = { pmr_state_tick = yes }
		capital = {
			pmr_count_queues = yes
			debug_log = "PMR;rec=TEST;arm=TICK_NOW;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];queued_gov=[THIS.Var('pmr_q_gov').GetValue|0];queued_priv=[THIS.Var('pmr_q_priv').GetValue|0]"
		}
	}
	ai_chance = { value = 0 }
}
'''

# State scope: the owner's queued building levels, government and private, into pmr_q_gov / pmr_q_priv.
# The triggers only compare, so count up to them.
COUNT_QUEUES = '''pmr_count_queues = {
	set_variable = { name = pmr_q_gov value = 0 }
	while = {
		limit = { owner = { construction_queue_num_queued_government_levels > prev.var:pmr_q_gov } }
		change_variable = { name = pmr_q_gov add = 1 }
	}
	set_variable = { name = pmr_q_priv value = 0 }
	while = {
		limit = { owner = { construction_queue_num_queued_private_levels > prev.var:pmr_q_priv } }
		change_variable = { name = pmr_q_priv add = 1 }
	}
}
'''

DECISION_LOC = [
    ' pmr_test_setup_decision:0 "PMR test: grant Bessemer and a steel mill"',
    ' pmr_test_setup_decision_desc:0 "If the capital has no Steel Mills, creates five government-owned levels there; then researches the Bessemer Process, which switches every Steel Mills to it and opens retooling."',
    ' pmr_test_open_hearth_decision:0 "PMR test: grant Open Hearth"',
    ' pmr_test_open_hearth_decision_desc:0 "Researches the Open Hearth Process, which switches every Steel Mills to it, including mills still part way through retooling to Bessemer."',
    ' pmr_test_tick_decision:0 "PMR test: recompute retooling now"',
    ' pmr_test_tick_decision_desc:0 "Runs the monthly PMR tick on every state you own immediately, instead of waiting for the month to turn, and logs how many building levels sit in each construction queue."',
]


if __name__ == '__main__':
    main()
