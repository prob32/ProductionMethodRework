"""Generate the Production Method Rework (PMR) mod from the installed game's own script.

PMR is generated, not hand-written, because it touches every recipe production method in the
game and must follow the beta as it moves. Run it against the game folder of the build you are
testing; it rewrites the mod folder in place.

    python tools/pmr/generate.py --game "G:/SteamLibrary/steamapps/common/Victoria 3/game"

What it does, building by building (see pmr/ProductionMethodRework/README.md for the design):

1. Labour is fixed. The building gets one extra production method group,
   ``pmg_pmr_labour_<b>``, holding one method, ``pm_pmr_labour_<b>``, whose ``level_scaled``
   employment is copied from the default (first) recipe. The recipe methods lose their
   ``building_employment_*`` lines and carry goods only.
2. Recipes stay ordinary vanilla production methods, ``_add`` values in ``workforce_scaled``,
   untouched apart from the employment lines.
3. For every ordered pair of recipes (old, new) a static modifier ``pmr_lag_<b>_<i>_<j>`` holds
   ``goods_input_<g>_mult`` / ``goods_output_<g>_mult`` = old/new - 1. Script applies it with
   ``multiplier = 1 - p``.
4. A hidden pseudo-building ``building_pmr_retool_<b>`` costs RETOOL_SHARE / N of the building's
   construction cost per level. A switch queues N x level of it, split between the government
   and private construction queues by the building's government-owned fraction.
5. p = (retool.level / N + level - L_start) / level, clamped to 0..1, recomputed whenever the
   recipe changes, whenever a retool level completes, and on the monthly state pulse.
6. Recipes switch on research: when a newer recipe becomes available the building activates it,
   which starts retooling. The building panel hides the recipe and automation selectors, shows the
   fixed labour method as a gold drawing of the main output good, and adds a bar showing the old
   and new recipe's shares.

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
OCCUPANCY_STEP = 0.05      # resolution of the occupancy that scales goods only old recipes have
# Recipe bar colour per recipe tier (position in vanilla's group, oldest first), the same on every
# building (Pat, 2026-10-12): tier 1 red, 2 yellow, 3 blue, 4 purple; 5 green for the two farms with five.
TIER_COLORS = [('Red', (0.80, 0.22, 0.20)), ('Yellow', (0.93, 0.78, 0.22)), ('Blue', (0.25, 0.50, 0.88)),
               ('Purple', (0.62, 0.36, 0.78)), ('Green', (0.32, 0.70, 0.36))]

MOD_NAME = 'ProductionMethodRework'
MOD_VERSION = '0.1.0'
SUPPORTED_VERSION = '1.14.*'

# Building files whose buildings make goods from goods. Government, military, urban, monuments,
# canals, infrastructure, subsistence, companies and the construction sector are out of scope:
# their first group is not a goods recipe, or retooling them through construction is circular.
BUILDING_FILES = ['01_industry.txt', '02_agro.txt', '03_mines.txt', '04_plantations.txt',
                  '09_misc_resource.txt']

LAG_ICON = 'gfx/interface/icons/timed_modifier_icons/modifier_gear_negative.dds'
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


class Recipe:
    def __init__(self, key, node, src):
        self.key, self.node, self.src = key, node, src
        self.inputs, self.outputs, self.employment = {}, {}, {}
        self.texture = (pdx.get(node.value, 'texture').value if pdx.get(node.value, 'texture') else None)
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

    groups = {}
    for s in g_srcs:
        for k, n in s.objects().items():
            pm = pdx.get(n.value, 'production_methods')
            groups[k] = pdx.items(pm) if pm else []
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

    report = {'treated': [], 'skipped': [], 'carried_by_add': [], 'icon_fallback': []}
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

    # ---- edit vanilla: strip recipe employment, add the labour group ----------------------------
    stripped = set()
    for bk, bn, s, recipes, g0, pg in treated:
        for r in recipes:
            if r.key not in stripped:
                r.strip_employment()
                stripped.add(r.key)
        # First in the list, so the building panel's grid shows it in the first slot and the hidden
        # recipe and automation slots after it leave no gap.
        brace = s.text.index('{', pg.start) + 1
        rest = s.text[brace:s.text.find('\n', brace)]
        tail = '' if not rest.strip() else '\n\t\t'   # the list continues on the brace's line
        s.inserts.append((brace, f'\n\t\tpmg_pmr_labour_{short(bk)}  # PMR: fixed labour{tail}'))

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

    # ---- new script ------------------------------------------------------------------------------
    labour_pms, labour_groups, retools, costs, lags, loc = [], [], [], [], [], []
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
    recipe_keys = {}

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
        if len(recipes) > len(TIER_COLORS):
            raise SystemExit(f'{bk}: {len(recipes)} recipes, but TIER_COLORS has {len(TIER_COLORS)}; add a colour')
        for i, r in enumerate(recipes, 1):
            custom_new.append(f'\ttext = {{\n\t\ttrigger = {{ is_building_type = {bk} state = {{ var:pmr_to_{b} = {i} }} }}\n'
                              f'\t\tlocalization_key = {r.key}\n\t}}\n')
        emp = '\n'.join(f'\t\t\t{k} = {fmt(v)}' for k, v in r0.employment.items())
        labour_pms.append(
            f'# {bk}: employment of {r0.key}, the default recipe, held fixed whatever recipe runs.\n'
            f'pm_pmr_labour_{b} = {{\n'
            f'\ttexture = "{icon_tex}"\n'
            f'\tis_default = yes\n'
            f'\tbuilding_modifiers = {{\n\t\tlevel_scaled = {{\n{emp}\n\t\t}}\n\t}}\n}}\n')
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

        loc += [f' pmg_pmr_labour_{b}:0 "Workforce"',
                f' pm_pmr_labour_{b}:0 "Fixed Workforce"',
                f' building_pmr_retool_{b}:0 "Retooling: ${bk}$"',
                f' building_pmr_retool_{b}_desc:0 "Privately funded construction that switches existing ${bk}$ to a new recipe. Investors from countries that own part of it fund the privately owned share; each completed level moves the old recipe\'s output closer to the new one."',
                f' building_pmr_retool_gov_{b}:0 "Retooling (Government): ${bk}$"',
                f' building_pmr_retool_gov_{b}_desc:0 "Government construction that switches the government-owned share of ${bk}$ to a new recipe. Each completed level moves the old recipe\'s output closer to the new one."']

        # lag modifiers for every ordered pair
        pair_names, add_names = {}, {}
        for i, old in enumerate(recipes, 1):
            for j, new in enumerate(recipes, 1):
                if i == j:
                    continue
                lines, adds = [], []
                for kind, o, n in (('input', old.inputs, new.inputs), ('output', old.outputs, new.outputs)):
                    for g in sorted(set(o) | set(n)):
                        ov, nv = o.get(g, 0), n.get(g, 0)
                        if nv == 0:
                            # A _mult on the new recipe's figure cannot bring back a good it does not
                            # have (coal on Atmospheric levels of an iron mine retooling to Diesel).
                            # Those goods come back as a flat _add per level still on the old recipe.
                            if ov != 0:
                                adds.append(f'\tgoods_{kind}_{g}_add = {fmt(ov)}  # per level on {old.key}')
                                report['carried_by_add'].append(
                                    {'building': bk, 'old': old.key, 'new': new.key, 'good': g, 'kind': kind,
                                     'per_level': ov})
                            continue
                        v = ov / nv - 1
                        if abs(v) > 1e-9:
                            lines.append(f'\tgoods_{kind}_{g}_mult = {fmt(v)}  # {fmt(ov)}/{fmt(nv)} - 1')
                if lines:
                    name = f'pmr_lag_{b}_{i}_{j}'
                    pair_names[(i, j)] = name
                    lags.append(f'# {bk}: {old.key} -> {new.key}\n{name} = {{\n\ticon = "{LAG_ICON}"\n' + '\n'.join(lines) + '\n}\n')
                    loc.append(f' {name}:0 "Retooling: ${old.key}$ to ${new.key}$"')
                    loc.append(f' {name}_desc:0 "This building still runs partly on its old recipe. The effect fades as retooling construction completes."')
                if adds:
                    name = f'pmr_old_{b}_{i}_{j}'
                    add_names[(i, j)] = name
                    lags.append(f'# {bk}: goods {old.key} has and {new.key} does not, per level still on {old.key}.\n'
                                f'# Applied with multiplier = those levels x the building\'s occupancy.\n'
                                f'{name} = {{\n\ticon = "{LAG_ICON}"\n' + '\n'.join(adds) + '\n}\n')
                    loc.append(f' {name}:0 "Not yet retooled: ${old.key}$"')
                    loc.append(f' {name}_desc:0 "Goods that levels still on ${old.key}$ use or make and ${new.key}$ does not. The effect fades as retooling construction completes."')

        tick_effects.append(tick_effect(bk, b, recipes, pair_names, add_names))
        dispatch.append(bk)
        report['treated'].append({'building': bk, 'recipe_group': g0, 'recipes': [r.key for r in recipes],
                                  'icon_good': good,
                                  'labour_from': r0.key, 'employment': r0.employment,
                                  'retool_cost': retool_cost, 'lag_modifiers': len(pair_names),
                                  'old_goods_modifiers': len(add_names)})

    # ---- companies: a company that owns a building type may own its private retooling ----------
    # When the investment pool builds a building type a company lists in building_types, the company
    # can be chosen as owner (OWNER_COMPANY_EXPANSION_CHANCE_MULTIPLIER, x OWNER_COMPANY_OWN_STATE_MULT
    # in its headquarters state). Listing each treated type's private retool building beside it lets a
    # company retool the building types it owns. Not added to extension_building_types: that list is
    # what industry charters offer, and a retool building is no charter. Vanilla files are rewritten
    # with only these lines inserted, like the building files above.
    retool_of = {t[0]: f'building_pmr_retool_{short(t[0])}' for t in treated}
    report['company_types'] = []
    for csrc in load_dir(game, 'company_types'):
        for ck, cn in csrc.objects().items():
            bt = pdx.get(cn.value, 'building_types')
            if not bt or not bt.is_block:
                continue
            listed = pdx.items(bt)
            new = [(x, retool_of[x]) for x in listed if x in retool_of and retool_of[x] not in listed]
            if not new:
                continue
            csrc.inserts.append((bt.end - 1, ''.join(f'\t{rbx}  # PMR: retooling of {x}\n\t' for x, rbx in new)))
            report['company_types'].append({'company': ck, 'file': csrc.name, 'added': [rbx for _, rbx in new]})
        if csrc.inserts:
            write(f'common/company_types/{csrc.name}', csrc.render())

    write('common/production_methods/pmr_labour_production_methods.txt', header + '\n'.join(labour_pms))
    write('common/production_method_groups/pmr_labour_groups.txt', header + '\n'.join(labour_groups))
    write('common/buildings/pmr_retool_buildings.txt', header + '\n'.join(retools))
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
    write('common/static_modifiers/pmr_lag_modifiers.txt', header + '\n'.join(lags))
    # 1.14.5 only knows a goods_<input|output>_<good>_mult once modifier_type_definitions defines it
    # ("Unknown modifier type ... potential dynamic modifier type definition missing"); vanilla
    # defines a handful. Define the rest the lags use, in vanilla's own format.
    defined = set()
    for msrc in load_dir(game, 'modifier_type_definitions'):
        defined |= set(msrc.objects())
    used = sorted(set(re.findall(r'\b(goods_(?:input|output)_[a-z_]+_(?:mult|add))\b', '\n'.join(lags))))
    missing = [k for k in used if k not in defined]
    goods_names = set(goods_tex)
    mtypes, mloc = [], []
    for k in missing:
        kind = 'input' if k.startswith('goods_input_') else 'output'
        suffix = k.rsplit('_', 1)[1]
        g = k[len(f'goods_{kind}_'):-len('_' + suffix)]
        if g not in goods_names:
            raise SystemExit(f'{k}: {g} is not a good')
        mtypes.append(f'{k} = {{\n\tdecimals = 1\n\tcolor = {"bad" if kind == "input" else "good"}\n'
                      + ('\tpercent = yes\n' if suffix == 'mult' else '')
                      + '\tgame_data = {\n\t\tai_value = 0\n\t}\n}\n')
        mloc += [f' {k}:0 "Building @{g}! ${g}$ {kind}"',
                 f' {k}_desc:0 "A bonus or penalty to the amount of @{g}! {"consumed" if kind == "input" else "produced"} by buildings"']
    write('common/modifier_type_definitions/pmr_modifier_types.txt', header + '\n'.join(mtypes))
    report['modifier_types_defined'] = missing
    loc += mloc
    write('common/scripted_effects/pmr_effects.txt', header + shared_effects() + '\n'.join(tick_effects)
          + dispatch_effects(dispatch) + '\n' + COUNT_QUEUES)
    write('common/on_actions/pmr_on_actions.txt', header + ON_ACTIONS)
    write('common/customizable_localization/pmr_custom_loc.txt', header +
          '# Building scope. The recipe a building runs, which is the one any retooling moves it to.\n'
          'pmr_new_recipe = {\n\ttype = building\n\tlog_loc_errors = no\n' + ''.join(custom_new) + '}\n')
    write('gui/building_details_panel.gui', patch_building_panel(
        recipe_keys, open(os.path.join(game, 'gui', 'building_details_panel.gui'), encoding='utf-8-sig').read()),
        bom=False)
    def vanilla_gui(name):
        return open(os.path.join(game, 'gui', name), encoding='utf-8-sig').read()
    write('gui/production_methods.gui', patch_type_grids(vanilla_gui('production_methods.gui'), dispatch,
                                                         'production_methods.gui', 3), bom=False)
    write('gui/building_browser_panel.gui', patch_type_grids(vanilla_gui('building_browser_panel.gui'), dispatch,
                                                             'building_browser_panel.gui', 1), bom=False)
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
          f"{len(report['carried_by_add'])} goods carried by old-recipe _add modifiers, "
          f"{len(report['company_types'])} company types may own retooling")


# ---------------------------------------------------------------------------------------------
# Script templates
#
# Buildings cannot hold variables (1.14.5 error.log: "This scope doesn't support variables. Scope:
# Building"). Everything PMR remembers about a building lives on its state instead, under the
# building type's short name: a state has at most one building of each type, so pmr_p_steel_mill on
# a state is that state's steel mill's p. The tick runs in state scope and reaches the building with
# b:<building_type> only to add or remove its lag modifier and to read its ownership.

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
# Retooling construction. Two pseudo-buildings per building type: building_pmr_retool_<b> is
# built only by private investors, for the privately owned share of the levels being retooled;
# building_pmr_retool_gov_<b> only by the government, for its share. Nothing queues either: the
# investment pool and the government choose. Each one's room is capped through can_build_private
# and can_build_government, the way vanilla caps trade centers under the canton system: the level
# after queued constructions, plus the levels being added (scope:num_levels), may not pass the cap
# the tick stores on the state.

RETOOL_TRIGGERS_DOC = """# State scope. True while this funder may add scope:num_levels more retool levels in the state.
# The caps are pmr_cap_priv_<b> / pmr_cap_gov_<b>, recomputed by pmr_split_retool_<b> every tick.
# pmr_retool_investor_<b> (state scope): true when scope:investor_country's investors own part of the
# building, so an investment agreement alone does not let a foreign pool retool it.

"""


def retool_buildings(b, bk, icon):
    out = []
    for side, group, rb in (('priv', 'bg_pmr_retool', f'building_pmr_retool_{b}'),
                            ('gov', 'bg_pmr_retool_gov', f'building_pmr_retool_gov_{b}')):
        if side == 'priv':
            who = ('\t# Private investors only, for the privately owned share. Every building vanilla lets private\n'
                   '\t# investors build says ownership_type = self.\n'
                   '\townership_type = self\n'
                   f'\tcan_build_government = {{ always = no }}\n'
                   '\t# Room left, and only investors from a country whose investors own part of the building.\n'
                   f'\tcan_build_private = {{\n\t\tpmr_retool_room_priv_{b} = yes\n\t\tpmr_retool_investor_{b} = yes\n\t}}\n')
        else:
            who = ('\t# The government only, for the government-owned share.\n'
                   f'\tcan_build_government = {{ pmr_retool_room_gov_{b} = yes }}\n'
                   '\tcan_build_private = { always = no }\n')
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
            f'\tai_value = {{\n\t\tvalue = 0\n\t\tif = {{\n\t\t\tlimit = {{ has_variable = pmr_retool_open_{side}_{b} }}\n'
            f'\t\t\tvalue = {RETOOL_AI_VALUE}\n\t\t}}\n\t}}\n'
            f'\trequired_construction = pmr_retool_cost_{b}\n'
            f'\tproduction_method_groups = {{\n\t\tpmg_dummy\n\t}}\n'
            f'\tbackground = "{RETOOL_BACKGROUND}"\n}}\n')
    return '\n'.join(out)


def retool_triggers(b, bk):
    out = []
    for side, rb in (('priv', f'building_pmr_retool_{b}'), ('gov', f'building_pmr_retool_gov_{b}')):
        cap = f'pmr_cap_{side}_{b}'
        out.append(
            f'pmr_retool_room_{side}_{b} = {{\n'
            f'\thas_variable = {cap}\n'
            '\t# b: finds the retool building even while all of it is still queued (seen in 1.14.5).\n'
            '\ttrigger_if = {\n'
            f'\t\tlimit = {{ exists = b:{rb} }}\n'
            f'\t\tb:{rb} = {{ level_after_queued_constructions <= pmr_room_value_{side}_{b} }}\n'
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


def retool_values(b):
    """Building scope: the most retool levels this funder's building may have after queued constructions,
    before the scope:num_levels being added."""
    return ''.join(f'pmr_room_value_{side}_{b} = {{\n\tvalue = state.var:pmr_cap_{side}_{b}\n'
                   '\tsubtract = scope:num_levels\n}\n' for side in ('priv', 'gov'))



def tick_effect(bk, b, recipes, pairs, adds):
    """Every effect for one building type. All run in STATE scope.

    The state keeps how many of the building's levels run each recipe (pmr_lv_<i>_<b>, i = the
    recipe's position in vanilla's group, oldest first). The building's active recipe is the
    target (pmr_to_<b>); every level on another recipe still needs retooling. Each completed retool
    level moves one level, oldest recipe first, onto the target. A newer recipe arriving mid-retool
    only changes the target: levels already moved keep their recipe until retooled again.
    The lag is one modifier per recipe still running, scaled by that recipe's share of the levels,
    so the building's goods are the level-weighted mix of its recipes. Goods the target recipe has
    none of cannot be scaled back from it; they come from a second modifier per old recipe (adds),
    a flat amount per level still on it, times the building's occupancy."""
    k = len(recipes)
    rb = f'building_pmr_retool_{b}'
    rbg = f'building_pmr_retool_gov_{b}'
    v = lambda name: f'{name}_{b}'           # noqa: E731  state variable for this building type
    lv = lambda i: v(f'pmr_lv_{i}')          # noqa: E731
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
             + '}\n\n')

    # lag modifiers live on the building
    o.append(f'pmr_clear_lag_{b} = {{\n\tb:{bk} = {{\n')
    for name in list(pairs.values()) + list(adds.values()):
        o.append(f'\t\tif = {{ limit = {{ has_modifier = {name} }} remove_modifier = {name} }}\n')
    o.append('\t}\n}\n\n')

    o.append(f'pmr_apply_lag_{b} = {{\n\tpmr_clear_lag_{b} = yes\n')
    for (i, j), name in pairs.items():
        o.append(f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_to")} = {j} var:{v(f"pmr_sh_{i}")} > 0 }}\n'
                 f'\t\tb:{bk} = {{ add_modifier = {{ name = {name} multiplier = prev.var:{v(f"pmr_sh_{i}")} }} }}\n\t}}\n')
    if adds:
        # A static modifier is not scaled by the workforce the way a recipe's goods are, so the
        # flat per-level amounts are scaled here: levels on the old recipe x occupancy, read from
        # the building-scope occupancy trigger in steps of OCCUPANCY_STEP.
        steps = round(1 / OCCUPANCY_STEP)
        o.append(f'\t{setv("pmr_occ", 0)}\n')
        for n in range(steps, 0, -1):
            frac = n * OCCUPANCY_STEP
            kw = 'if' if n == steps else 'else_if'
            o.append(f'\t{kw} = {{ limit = {{ b:{bk} = {{ occupancy >= {fmt(frac - OCCUPANCY_STEP / 2)} }} }} '
                     f'{setv("pmr_occ", fmt(frac))} }}\n')
        for (i, j), name in adds.items():
            o.append(f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_to")} = {j} var:{lv(i)} > 0 var:{v("pmr_occ")} > 0 }}\n'
                     f'\t\t{setv("pmr_oldm", "var:" + lv(i))}\n'
                     f'\t\t{chg("pmr_oldm", "multiply", "var:" + v("pmr_occ"))}\n'
                     f'\t\tb:{bk} = {{ add_modifier = {{ name = {name} multiplier = prev.var:{v("pmr_oldm")} }} }}\n\t}}\n')
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

    def read_side(rbx, side):
        return (f'\t{setv("pmr_retool_built_" + side, 0)}\n'
                f'\t{setv("pmr_retool_q_" + side, 0)}\n'
                f'\tif = {{\n\t\tlimit = {{ OR = {{ has_building = {rbx} exists = b:{rbx} }} }}\n'
                f'\t\t{setv("pmr_retool_built_" + side, f"b:{rbx}.level")}\n'
                f'\t\t{setv("pmr_retool_q_" + side, f"b:{rbx}.level_after_queued_constructions")}\n'
                '\t}\n'
                f'\t{setv("pmr_pending_" + side, "var:" + v("pmr_retool_q_" + side))}\n'
                f'\t{chg("pmr_pending_" + side, "subtract", "var:" + v("pmr_retool_built_" + side))}\n')
    o.append(f'pmr_read_retool_{b} = {{\n'
             '\t# A retool still entirely under construction may not count for has_building.\n'
             + read_side(rb, 'priv') + read_side(rbg, 'gov') +
             f'\t{setv("pmr_retool_built", "var:" + v("pmr_retool_built_priv"))}\n'
             f'\t{chg("pmr_retool_built", "add", "var:" + v("pmr_retool_built_gov"))}\n'
             f'\t{setv("pmr_pending", "var:" + v("pmr_pending_priv"))}\n'
             f'\t{chg("pmr_pending", "add", "var:" + v("pmr_pending_gov"))}\n'
             '}\n\n')

    # A retool building whose levels are all counted and with nothing queued on it is removed, so
    # the next retool level is a new construction. 1.14.5's investment pool never queued a second
    # level on a retool building that already had one: in a year of Pat's test log, every private
    # retool level queued was the first of its building. The pool does not expand a building with
    # employment under PRODUCTION_BUILDING_LOW_EMPLOYMENT_THRESHOLD, and a retool building employs
    # nobody. Never removed while anything is queued on it (that leaves a NULL_STATE construction).
    def release(rbx, side):
        return (f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_retool_built_" + side)} > 0 var:{v("pmr_pending_" + side)} <= 0 '
                f'OR = {{ has_building = {rbx} exists = b:{rbx} }} }}\n'
                f'\t\tremove_building = {rbx}\n'
                f'\t\t{chg("pmr_seen", "subtract", "var:" + v("pmr_retool_built_" + side))}\n'
                f'\t\t{setv("pmr_retool_built_" + side, 0)}\n'
                f'\t\t{setv("pmr_retool_q_" + side, 0)}\n'
                f'\t\t{setv("pmr_pending_" + side, 0)}\n\t}}\n')

    # Completed retool levels not yet counted move levels onto the target, oldest recipe first.
    # The retool buildings keep their levels between retools while anything is queued on them,
    # so pmr_seen counts the levels already used and only the rest move anything.
    o.append(f'pmr_progress_{b} = {{\n\tpmr_read_retool_{b} = yes\n'
             f'\t{setv("pmr_conv", "var:" + v("pmr_retool_built"))}\n'
             f'\t{chg("pmr_conv", "subtract", "var:" + v("pmr_seen"))}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_conv")} < 0 }} {setv("pmr_conv", 0)} }}\n'
             f'\t{setv("pmr_seen", "var:" + v("pmr_retool_built"))}\n'
             f'\t{chg("pmr_conv", "divide", "pmr_retool_levels_per_level")}\n'
             f'\t{setv("pmr_gain", 0)}\n'
             + ''.join(f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_conv")} > 0 var:{lv(i)} > 0 NOT = {{ var:{v("pmr_to")} = {i} }} }}\n'
                       f'\t\tif = {{ limit = {{ var:{lv(i)} >= var:{v("pmr_conv")} }} {setv("pmr_amt", "var:" + v("pmr_conv"))} }}\n'
                       f'\t\telse = {{ {setv("pmr_amt", "var:" + lv(i))} }}\n'
                       f'\t\tchange_variable = {{ name = {lv(i)} subtract = var:{v("pmr_amt")} }}\n'
                       f'\t\t{chg("pmr_conv", "subtract", "var:" + v("pmr_amt"))}\n'
                       f'\t\t{chg("pmr_gain", "add", "var:" + v("pmr_amt"))}\n\t}}\n' for i in range(1, k + 1))
             + on_index('pmr_to', lambda i: f'change_variable = {{ name = {lv(i)} add = var:{v("pmr_gain")} }}')
             + ''.join(release(rbx, side) for rbx, side in ((rb, 'priv'), (rbg, 'gov')))
             + f'\t{setv("pmr_retool_built", "var:" + v("pmr_retool_built_priv"))}\n'
             f'\t{chg("pmr_retool_built", "add", "var:" + v("pmr_retool_built_gov"))}\n'
             + '}\n\n')

    # Shares for the bar and the lag, the levels still to retool, and p (share on the target).
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
             f'\tpmr_read_gov_{b} = yes\n'
             f'\t{setv("pmr_retool_gov", "var:" + v("pmr_need"))}\n'
             f'\t{chg("pmr_retool_gov", "multiply", "var:" + v("pmr_gov_frac"))}\n'
             f'\tround_variable = {{ name = {v("pmr_retool_gov")} nearest = 1 }}\n'
             f'\t{setv("pmr_retool_priv", "var:" + v("pmr_need"))}\n'
             f'\t{chg("pmr_retool_priv", "subtract", "var:" + v("pmr_retool_gov"))}\n'
             f'\t{setv("pmr_room", "var:" + v("pmr_need"))}\n'
             f'\t{chg("pmr_room", "subtract", "var:" + v("pmr_pending"))}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_room")} < 0 }} {setv("pmr_room", 0)} }}\n'
             f'\t{setv("pmr_room_gov", "var:" + v("pmr_retool_gov"))}\n'
             f'\t{chg("pmr_room_gov", "subtract", "var:" + v("pmr_pending_gov"))}\n'
             f'\tif = {{ limit = {{ var:{v("pmr_room_gov")} < 0 }} {setv("pmr_room_gov", 0)} }}\n'
             + clamp_to("pmr_room_gov", "pmr_room") +
             f'\t{setv("pmr_room_priv", "var:" + v("pmr_room"))}\n'
             f'\t{chg("pmr_room_priv", "subtract", "var:" + v("pmr_room_gov"))}\n'
             f'\t{setv("pmr_cap_gov", "var:" + v("pmr_retool_q_gov"))}\n'
             f'\t{chg("pmr_cap_gov", "add", "var:" + v("pmr_room_gov"))}\n'
             f'\t{setv("pmr_cap_priv", "var:" + v("pmr_retool_q_priv"))}\n'
             f'\t{chg("pmr_cap_priv", "add", "var:" + v("pmr_room_priv"))}\n'
             f'\tset_variable = pmr_retool_gate_{b}\n'
             + ''.join(f'\tif = {{ limit = {{ var:{v("pmr_room_" + side)} > 0 }} set_variable = pmr_retool_open_{side}_{b} }}\n'
                       f'\telse_if = {{ limit = {{ has_variable = pmr_retool_open_{side}_{b} }} remove_variable = pmr_retool_open_{side}_{b} }}\n'
                       for side in ('priv', 'gov')) +
             '}\n\n')

    # Nothing left to retool. A retool building with levels still queued is never removed: that
    # leaves a construction with no building (seen as NULL_STATE in the queue). It is closed
    # instead, and removed by a later tick once its queue has emptied.
    o.append(f'pmr_close_retool_{b} = {{\n'
             + ''.join(f'\tif = {{ limit = {{ has_variable = pmr_retool_open_{side}_{b} }} remove_variable = pmr_retool_open_{side}_{b} }}\n'
                       for side in ('priv', 'gov')) +
             f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_pending")} > 0 }}\n'
             f'\t\t{setv("pmr_cap_priv", "var:" + v("pmr_retool_q_priv"))}\n'
             f'\t\t{setv("pmr_cap_gov", "var:" + v("pmr_retool_q_gov"))}\n'
             f'\t\t{setv("pmr_room_priv", 0)}\n\t\t{setv("pmr_room_gov", 0)}\n\t}}\n'
             '\telse = {\n'
             f'\t\tif = {{ limit = {{ OR = {{ has_building = {rb} exists = b:{rb} }} }} remove_building = {rb} }}\n'
             f'\t\tif = {{ limit = {{ OR = {{ has_building = {rbg} exists = b:{rbg} }} }} remove_building = {rbg} }}\n'
             f'\t\t{setv("pmr_seen", 0)}\n'
             + ''.join(f'\t\tif = {{ limit = {{ has_variable = {n} }} remove_variable = {n} }}\n'
                       for n in (f'pmr_retool_gate_{b}', v('pmr_cap_priv'), v('pmr_cap_gov'), v('pmr_gov_levels'))) +
             '\t}\n}\n\n')

    # newest recipe the building runs or can activate; vanilla lists recipes oldest first
    o.append(f'pmr_best_{b} = {{\n\t{setv("pmr_best_now", 0)}\n')
    for i in range(k, 0, -1):
        r = recipes[i - 1]
        kw = 'if' if i == k else 'else_if'
        o.append(f'\t{kw} = {{\n\t\tlimit = {{ OR = {{\n\t\t\t{active(r)}\n'
                 f'\t\t\tcan_activate_production_method = {{ building_type = {bk} production_method = {r.key} }}\n'
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
    best = f";best={f('pmr_best_now')}"
    split = (f";gov_frac={f('pmr_gov_frac', 2)};gov_levels={f('pmr_gov_levels')}"
             f";share_gov={f('pmr_retool_gov')};share_priv={f('pmr_retool_priv')}"
             f";queued_gov={f('pmr_pending_gov')};queued_priv={f('pmr_pending_priv')}"
             f";room_gov={f('pmr_room_gov')};room_priv={f('pmr_room_priv')}")
    done = f";queued_gov={f('pmr_pending_gov')};queued_priv={f('pmr_pending_priv')}"

    o.append(f'pmr_tick_{b} = {{\n'
             f'\t{setv("pmr_level", f"b:{bk}.level")}\n'
             f'\tpmr_best_{b} = yes\n'
             '\t# First sight (game start, a new building, or a save from before the level mix): every\n'
             '\t# level runs the recipe the building runs now, with no lag. Retool levels already built\n'
             '\t# count for nothing.\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = pmr_mix_{b} }} }}\n'
             f'\t\tset_variable = pmr_mix_{b}\n'
             f'\t\tpmr_clear_lag_{b} = yes\n'
             f'\t\tif = {{ limit = {{ has_variable = {v("pmr_retooling")} }} remove_variable = {v("pmr_retooling")} }}\n'
             f'\t\t{setv("pmr_best", "var:" + v("pmr_best_now"))}\n'
             f'\t\tpmr_running_{b} = yes\n'
             f'\t\t{setv("pmr_to", "var:" + v("pmr_run"))}\n'
             f'\t\tpmr_reset_levels_{b} = yes\n'
             f'\t\tpmr_read_retool_{b} = yes\n'
             f'\t\t{setv("pmr_seen", "var:" + v("pmr_retool_built"))}\n'
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
             f'\tpmr_progress_{b} = yes\n'
             f'\tpmr_mix_{b} = yes\n'
             f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_need")} > 0 }}\n'
             f'\t\tset_variable = {v("pmr_retooling")}\n'
             f'\t\tpmr_split_retool_{b} = yes\n'
             f'\t\tpmr_apply_lag_{b} = yes\n'
             f'\t\tif = {{ limit = {{ has_variable = {v("pmr_switched")} }} {log("SWITCH", bk, b, k, extra=split)} }}\n'
             f'\t\telse = {{ {log("TICK", bk, b, k, extra=split)} }}\n'
             '\t}\n'
             '\telse = {\n'
             f'\t\tpmr_clear_lag_{b} = yes\n'
             f'\t\tpmr_close_retool_{b} = yes\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = {v("pmr_retooling")} }}\n'
             f'\t\t\tremove_variable = {v("pmr_retooling")}\n'
             f'\t\t\t{log("DONE", bk, b, k, extra=done)}\n'
             '\t\t}\n'
             f'\t\telse_if = {{ limit = {{ has_variable = {v("pmr_switched")} }} {log("CANCEL", bk, b, k)} }}\n'
             '\t}\n'
             f'\tif = {{ limit = {{ has_variable = {v("pmr_switched")} }} remove_variable = {v("pmr_switched")} }}\n'
             '}\n\n')
    return ''.join(o)


def shared_effects():
    return ''


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
        o.append(f'\t{kw} = {{\n\t\tlimit = {{ OR = {{ is_building_type = building_pmr_retool_{b} '
                 f'is_building_type = building_pmr_retool_gov_{b} }} }}\n'
                 f'\t\tstate = {{ if = {{ limit = {{ {live(bk)} }} pmr_tick_{b} = yes }} }}\n\t}}\n')
    o.append('}\n\n'
             '# State scope: tick every PMR building in the state.\n'
             'pmr_state_tick = {\n')
    for bk in buildings:
        o.append(f'\tif = {{ limit = {{ {live(bk)} }} pmr_tick_{short(bk)} = yes }}\n')
    o.append('}\n')
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


def recipe_bar(bk, b, k):
    """The recipe bar for one building type. Two rows sized and centred to match the employment
    and cash-reserve bars to its right (26 px each, 8 apart), between the production method slot
    (x 2..72) and those bars (230 wide, 5 from the right edge of the 540 px panel): x 84..293.
    The bar is one segment per recipe, oldest on the left, each as wide as that recipe's share of
    the building's levels and coloured by its tier (TIER_COLORS). Drawn as white progress bars
    tinted per tier, filled to the running total of the shares and stacked newest first, so each
    tier shows from where the older ones end."""
    def var(name):
        return f"Building.GetState.MakeScope.Var('{name}_{b}').GetValue"
    retooling = f'NotZero_CFixedPoint({var("pmr_ui_retooling")})'
    layers = []
    frame = '\n\t\t\t\t\t\t\tblockoverride "frame" {}  # the frame is drawn once, by the top layer'
    for i in range(k, 0, -1):
        name, (r, g, bl) = TIER_COLORS[i - 1]
        layers.append(f"""
						# tier {i}, {name.lower()}
						white_progressbar_horizontal = {{
							size = {{ 100% 100% }}
							blockoverride "background" {{}}{'' if i == 1 else frame}
							blockoverride "values" {{
								min = 0
								max = 1
								value = "[FixedPointToFloat({var(f"pmr_cum_{i}")})]"
							}}
							blockoverride "color" {{
								color = {{ {r} {g} {bl} 1 }}
							}}
						}}""")
    return f"""
				# PMR: recipe bar for {bk}: each recipe's share of the levels, in its tier's colour.
				widget = {{
					visible = "[{is_type(bk)}]"
					position = {{ 84 0 }}
					size = {{ 209 60 }}
					parentanchor = vcenter

					textbox = {{
						visible = "[Not({retooling})]"
						size = {{ 209 26 }}
						align = left|nobaseline
						elide = right
						text = "PMR_RECIPE_BAR_TITLE"
						tooltip = "PMR_RECIPE_BAR_TOOLTIP"
						using = tooltip_above
					}}
					textbox = {{
						visible = "[{retooling}]"
						size = {{ 209 26 }}
						align = left|nobaseline
						elide = right
						text = "PMR_RECIPE_BAR_TITLE_RETOOLING"
						tooltip = "PMR_BAR_TOOLTIP_{b}"
						using = tooltip_above
					}}

					widget = {{
						position = {{ 0 34 }}
						size = {{ 209 26 }}
						background = {{
							texture = "gfx/interface/progressbar/progressbar_empty.dds"
							spriteType = Corneredtiled
							spriteborder = {{ 4 4 }}
							texture_density = 2
							using = progressbar_texture_properties
						}}
{''.join(layers)}
						textbox = {{
							visible = "[{retooling}]"
							size = {{ 100% 100% }}
							align = center|nobaseline
							text = "PMR_BAR_PCT_{b}"
						}}
						textbox = {{
							visible = "[Not({retooling})]"
							size = {{ 100% 100% }}
							align = center|nobaseline
							text = "PMR_BAR_FULL"
						}}
						# hover areas: the breakdown by recipe while retooling, else the one recipe
						widget = {{
							visible = "[{retooling}]"
							size = {{ 100% 100% }}
							tooltip = "PMR_BAR_TOOLTIP_{b}"
							using = tooltip_above
						}}
						widget = {{
							visible = "[Not({retooling})]"
							size = {{ 100% 100% }}
							tooltip = "PMR_BAR_FULL_TOOLTIP"
							using = tooltip_above
						}}
					}}
				}}
"""


def patch_building_panel(recipe_keys, text):
    buildings = list(recipe_keys)
    """Vanilla building_details_panel.gui with two changes, asserted so a game update that moves
    either anchor fails generation instead of shipping a panel that silently lost them."""
    # 1. In the condensed production method grid, a PMR building type shows only its single-method
    #    groups (the fixed labour slot); recipe and automation selectors are hidden. Decided by
    #    building type, so it needs no script state.
    type_at = text.index('type condensed_building_information_pms')
    item = 'datacontext = "[ProductionMethodGroup]"\n'
    at = text.index(item, type_at) + len(item)
    indent = text[text.rfind('\n', 0, at - len(item)) + 1:at - len(item)]
    text = (text[:at] + indent + '# PMR: fixed labour only on PMR building types\n' + indent +
            f'visible = "[Or(Not({any_type(buildings)}), EqualTo_int32(GetDataModelSize(ProductionMethodGroup.'
            "AccessBuildingProductionMethods(Building.Self)), '(int32)1'))]\"\n" + text[at:])

    # 2. The recipe bar beside it, in the details panel's PMs / employment / cash reserves row.
    anchor = '\t\t\t\tblock "extra_items_in_production_methods_list" {}\n'
    if text.count(anchor) != 1:
        raise SystemExit(f'building_details_panel.gui: expected one {anchor.strip()!r}, found '
                         f'{text.count(anchor)}; the panel changed in this build, update patch_building_panel')
    text = text.replace(anchor, anchor + ''.join(recipe_bar(bk, short(bk), len(recipe_keys[bk])) for bk in buildings))
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


def patch_type_grids(text, buildings, name, expected):
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
    return text


def panel_loc(recipe_keys):
    loc = [
        ' PMR_RECIPE_BAR_TITLE:0 "#bold [Building.GetCustom(\'pmr_new_recipe\')]#!"',
        ' PMR_RECIPE_BAR_TITLE_RETOOLING:0 "Retooling to #bold [Building.GetCustom(\'pmr_new_recipe\')]#!"',
        ' PMR_BAR_FULL:0 "#bold 100%#!"',
        ' PMR_BAR_FULL_TOOLTIP:0 "Every level runs #bold [Building.GetCustom(\'pmr_new_recipe\')]#!."',
        ' PMR_RECIPE_BAR_TOOLTIP:0 "This building runs #bold [Building.GetCustom(\'pmr_new_recipe\')]#!. When your country researches a newer recipe it switches automatically, and the change takes effect as retooling construction completes."',
    ]
    for bk, keys in recipe_keys.items():
        b = short(bk)

        def var(name, f):
            return f"[Building.GetState.MakeScope.Var('{name}_{b}').GetValue|{f}]"
        tiers = ''.join(f'\\n{TIER_COLORS[i - 1][0]}, ${key}$: #bold {var(f"pmr_sh_{i}", "%0")}#!'
                        for i, key in enumerate(keys, 1))
        loc += [
            f' PMR_BAR_PCT_{b}:0 "#bold {var("pmr_p", "%0")}#!"',
            f' PMR_BAR_TOOLTIP_{b}:0 "#bold Levels by recipe#!{tiers}'
            f'\\n\\nLevels still to retool to [Building.GetCustom(\'pmr_new_recipe\')]: #bold {var("pmr_need", "0")}#!'
            f'\\n\\nPrivate investors: #bold {var("pmr_pending_priv", "0")}#! queued, room for #bold {var("pmr_room_priv", "0")}#! more. Only investors who own part of this building fund these, from the investment pool.'
            f'\\nGovernment: #bold {var("pmr_pending_gov", "0")}#! queued, room for #bold {var("pmr_room_gov", "0")}#! more. Queue these yourself: build #bold $building_pmr_retool_gov_{b}$#! in this state."',
        ]
    return loc


ON_ACTIONS = '''# Appended to vanilla on_actions the documented way (_on_actions.md, MODDING INFO):
# the vanilla on_action calls ours, nothing vanilla is overwritten.

on_game_started = { on_actions = { pmr_on_game_started } }
on_production_method_changed = { on_actions = { pmr_on_production_method_changed } }
on_building_built = { on_actions = { pmr_on_building_built } }
on_building_expanded = { on_actions = { pmr_on_building_expanded } }
on_monthly_pulse_state = { on_actions = { pmr_on_monthly_pulse_state } }
on_acquired_technology = { on_actions = { pmr_on_acquired_technology } }

# No root. Adopt every building's starting recipe so day-one recipes carry no lag.
pmr_on_game_started = {
	effect = {
		debug_log = "PMR;rec=LOADED;date=[TimeKeeper.GetCurrentDate.GetString];hook=on_game_started"
		every_country = {
			every_scope_state = { pmr_state_tick = yes }
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
	}
}

# Root = state. Backstop: recompute p and re-apply the lag once a month even if no event fired.
pmr_on_monthly_pulse_state = {
	effect = {
		pmr_state_tick = yes
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
