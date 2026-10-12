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

Vanilla files the mod changes are written whole under their vanilla names (file shadowing), with
only the employment lines and the extra group inserted; every other byte is the installed game's.
"""

import argparse
import glob
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdx  # noqa: E402

# ---------------------------------------------------------------------------------------------
# Tunables. Change here and regenerate; nothing below hard-codes them.
N = 4                      # retool levels per real building level
RETOOL_SHARE = 0.5         # retooling one level costs this share of the building's construction cost
GOV_FRACTION_STEP = 0.05   # resolution of the government-owned share read from the ownership trigger

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

    report = {'treated': [], 'skipped': [], 'unrepresentable': []}
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
        close = pg.end - 1   # the '}' of production_method_groups
        indent = s.text[s.text.rfind('\n', 0, close) + 1:close]
        line_start = s.text.rfind('\n', 0, close) + 1
        item_indent = indent + '\t' if not indent.strip() else '\t\t'
        s.inserts.append((line_start, f'{item_indent}pmg_pmr_labour_{short(bk)}  # PMR: fixed labour\n'))

    if os.path.isdir(args.out):
        for sub in ('common', 'localization', '.metadata'):
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
    tick_effects, dispatch = [], []
    cost_values = {}
    for line in open(os.path.join(game, 'common', 'script_values', 'building_values.txt'), encoding='utf-8-sig'):
        parts = line.split('#')[0].split('=')
        if len(parts) == 2 and parts[0].strip().startswith('construction_cost_'):
            try:
                cost_values[parts[0].strip()] = float(parts[1])
            except ValueError:
                pass

    for bk, bn, s, recipes, g0, pg in treated:
        b = short(bk)
        r0 = recipes[0]
        emp = '\n'.join(f'\t\t\t{k} = {fmt(v)}' for k, v in r0.employment.items())
        labour_pms.append(
            f'# {bk}: employment of {r0.key}, the default recipe, held fixed whatever recipe runs.\n'
            f'pm_pmr_labour_{b} = {{\n'
            f'\ttexture = "{r0.texture}"\n'
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
        retools.append(
            f'building_pmr_retool_{b} = {{\n'
            f'\tbuilding_group = bg_pmr_retool\n'
            f'\ticon = "{icon}"\n'
            f'\tcity_type = none\n'
            f'\tgenerates_residences = no\n'
            f'\teconomic_contribution = 0\n'
            f'\tdownsizeable = no\n'
            f'\t# Open only while script is retooling a {bk} in this state.\n'
            f'\tpotential = {{ has_variable = pmr_retool_gate_{b} }}\n'
            f'\tai_value = 0\n'
            f'\trequired_construction = pmr_retool_cost_{b}\n'
            f'\tproduction_method_groups = {{\n\t\tpmg_dummy\n\t}}\n'
            f'\tbackground = "{RETOOL_BACKGROUND}"\n}}\n')

        loc += [f' pmg_pmr_labour_{b}:0 "Workforce"',
                f' pm_pmr_labour_{b}:0 "Fixed Workforce"',
                f' building_pmr_retool_{b}:0 "Retooling: ${bk}$"',
                f' building_pmr_retool_{b}_desc:0 "Construction that switches existing ${bk}$ to a new recipe. Each completed level moves the old recipe\'s output closer to the new one."']

        # lag modifiers for every ordered pair
        pair_names = {}
        for i, old in enumerate(recipes, 1):
            for j, new in enumerate(recipes, 1):
                if i == j:
                    continue
                lines = []
                for kind, o, n in (('input', old.inputs, new.inputs), ('output', old.outputs, new.outputs)):
                    for g in sorted(set(o) | set(n)):
                        ov, nv = o.get(g, 0), n.get(g, 0)
                        if nv == 0:
                            if ov != 0:
                                report['unrepresentable'].append(
                                    {'building': bk, 'old': old.key, 'new': new.key, 'good': g, 'kind': kind,
                                     'old_value': ov, 'note': 'new recipe has none; a _mult cannot restore it'})
                            continue
                        v = ov / nv - 1
                        if abs(v) > 1e-9:
                            lines.append(f'\tgoods_{kind}_{g}_mult = {fmt(v)}  # {fmt(ov)}/{fmt(nv)} - 1')
                if not lines:
                    continue
                name = f'pmr_lag_{b}_{i}_{j}'
                pair_names[(i, j)] = name
                lags.append(f'# {bk}: {old.key} -> {new.key}\n{name} = {{\n\ticon = "{LAG_ICON}"\n' + '\n'.join(lines) + '\n}\n')
                loc.append(f' {name}:0 "Retooling: ${old.key}$ to ${new.key}$"')
                loc.append(f' {name}_desc:0 "This building still runs partly on its old recipe. The effect fades as retooling construction completes."')

        tick_effects.append(tick_effect(bk, b, recipes, pair_names))
        dispatch.append(bk)
        report['treated'].append({'building': bk, 'recipe_group': g0, 'recipes': [r.key for r in recipes],
                                  'labour_from': r0.key, 'employment': r0.employment,
                                  'retool_cost': retool_cost, 'lag_modifiers': len(pair_names)})

    write('common/production_methods/pmr_labour_production_methods.txt', header + '\n'.join(labour_pms))
    write('common/production_method_groups/pmr_labour_groups.txt', header + '\n'.join(labour_groups))
    write('common/buildings/pmr_retool_buildings.txt', header + '\n'.join(retools))
    write('common/building_groups/pmr_building_groups.txt', header +
          '# Shaped on vanilla bg_monuments_hidden: no lens, not in the outliner.\n'
          'bg_pmr_retool = {\n\talways_possible = yes\n\tis_shown_in_outliner = no\n}\n')
    write('common/script_values/pmr_values.txt', header +
          f'pmr_retool_levels_per_level = {N}\n\n' + '\n'.join(costs) + '\n')
    write('common/static_modifiers/pmr_lag_modifiers.txt', header + '\n'.join(lags))
    write('common/scripted_effects/pmr_effects.txt', header + shared_effects() + '\n'.join(tick_effects)
          + dispatch_effects(dispatch))
    write('common/on_actions/pmr_on_actions.txt', header + ON_ACTIONS)
    write('common/decisions/pmr_test_decisions.txt', header + DECISIONS)
    loc += [' bg_pmr_retool:0 "Retooling"'] + DECISION_LOC
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
          f"{len(report['unrepresentable'])} unrepresentable goods in lag pairs")


# ---------------------------------------------------------------------------------------------
# Script templates

def log(rec, b, extra=''):
    return (f'debug_log = "PMR;rec={rec};date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetBuilding.GetState.GetOwner.GetNameNoFormatting];'
            f'state=[THIS.GetBuilding.GetState.GetNameNoFormatting];building=building_{b};'
            f"from=[THIS.Var('pmr_from').GetValue|0];to=[THIS.Var('pmr_to').GetValue|0];"
            f"level=[THIS.Var('pmr_level').GetValue|0];l_start=[THIS.Var('pmr_l_start').GetValue|0];"
            f"retool_built=[THIS.Var('pmr_retool_built').GetValue|0];retool_total=[THIS.Var('pmr_retool_total').GetValue|0];"
            f"p=[THIS.Var('pmr_p').GetValue|3]{extra}\"")


def tick_effect(bk, b, recipes, pairs):
    k = len(recipes)
    o = []
    o.append(f'# ===== {bk}: ' + ', '.join(f'{i} = {r.key}' for i, r in enumerate(recipes, 1)) + '\n')

    # clear lag
    o.append(f'pmr_clear_lag_{b} = {{\n')
    for name in pairs.values():
        o.append(f'\tif = {{ limit = {{ has_modifier = {name} }} remove_modifier = {name} }}\n')
    o.append('}\n\n')

    # apply lag for the current (from, to) pair at multiplier 1 - p
    o.append(f'pmr_apply_lag_{b} = {{\n\tpmr_clear_lag_{b} = yes\n')
    for (i, j), name in pairs.items():
        o.append(f'\tif = {{\n\t\tlimit = {{ var:pmr_from = {i} var:pmr_to = {j} }}\n'
                 f'\t\tadd_modifier = {{\n\t\t\tname = {name}\n\t\t\tmultiplier = {{ value = 1 subtract = var:pmr_p }}\n\t\t}}\n\t}}\n')
    o.append('}\n\n')

    # remove retool pseudo-building and close its gate (state scope)
    o.append(f'pmr_clear_retool_{b} = {{\n'
             f'\tif = {{ limit = {{ OR = {{ has_building = building_pmr_retool_{b} exists = b:building_pmr_retool_{b} }} }} remove_building = building_pmr_retool_{b} }}\n'
             f'\tif = {{ limit = {{ has_variable = pmr_retool_gate_{b} }} remove_variable = pmr_retool_gate_{b} }}\n'
             '}\n\n')

    # queue N x level retool levels, government share first (building scope)
    o.append(f'pmr_queue_retool_{b} = {{\n'
             '\tpmr_read_gov_fraction = yes\n'
             '\tset_variable = { name = pmr_retool_total value = level }\n'
             '\tchange_variable = { name = pmr_retool_total multiply = pmr_retool_levels_per_level }\n'
             '\tset_variable = { name = pmr_retool_gov value = var:pmr_retool_total }\n'
             '\tchange_variable = { name = pmr_retool_gov multiply = var:pmr_gov_frac }\n'
             '\tround_variable = { name = pmr_retool_gov nearest = 1 }\n'
             '\tset_variable = { name = pmr_retool_priv value = var:pmr_retool_total }\n'
             '\tchange_variable = { name = pmr_retool_priv subtract = var:pmr_retool_gov }\n'
             '\tset_local_variable = { name = pmr_n_gov value = var:pmr_retool_gov }\n'
             '\tset_local_variable = { name = pmr_n_priv value = var:pmr_retool_priv }\n'
             '\tstate = {\n'
             f'\t\tset_variable = pmr_retool_gate_{b}\n'
             '\t\twhile = {\n\t\t\tlimit = { local_var:pmr_n_gov > 0 }\n'
             f'\t\t\tstart_building_construction = building_pmr_retool_{b}\n'
             '\t\t\tchange_local_variable = { name = pmr_n_gov subtract = 1 }\n\t\t}\n'
             '\t\twhile = {\n\t\t\tlimit = { local_var:pmr_n_priv > 0 }\n'
             f'\t\t\tstart_privately_funded_building_construction = building_pmr_retool_{b}\n'
             '\t\t\tchange_local_variable = { name = pmr_n_priv subtract = 1 }\n\t\t}\n'
             '\t}\n'
             f'\tpmr_read_retool_{b} = yes\n'
             '}\n\n')

    # read built and queued retool levels into variables
    o.append(f'pmr_read_retool_{b} = {{\n'
             '\tset_variable = { name = pmr_retool_built value = 0 }\n'
             '\tset_variable = { name = pmr_retool_queued value = 0 }\n'
             '\t# A retool still entirely under construction may not count for has_building, so also accept\n'
             '\t# the building object existing at all.\n'
             f'\tif = {{\n\t\tlimit = {{ state = {{ OR = {{ has_building = building_pmr_retool_{b} exists = b:building_pmr_retool_{b} }} }} }}\n'
             f'\t\tset_variable = {{ name = pmr_retool_built value = state.b:building_pmr_retool_{b}.level }}\n'
             f'\t\tset_variable = {{ name = pmr_retool_queued value = state.b:building_pmr_retool_{b}.level_after_queued_constructions }}\n'
             '\t}\n}\n\n')

    # the tick
    o.append(f'pmr_tick_{b} = {{\n'
             '\tset_variable = { name = pmr_level value = level }\n'
             '\t# First sight: adopt whatever recipe runs now, with no lag.\n'
             '\tif = {\n\t\tlimit = { NOT = { has_variable = pmr_to } }\n')
    for i, r in enumerate(recipes, 1):
        kw = 'if' if i == 1 else 'else_if'
        o.append(f'\t\t{kw} = {{ limit = {{ has_active_production_method = {r.key} }} '
                 f'set_variable = {{ name = pmr_from value = {i} }} set_variable = {{ name = pmr_to value = {i} }} }}\n')
    o.append('\t\tset_variable = { name = pmr_p value = 1 }\n'
             '\t\tset_variable = { name = pmr_l_start value = level }\n'
             f'\t\t{log("INIT", b)}\n\t}}\n')
    o.append('\t# A switch: the active recipe is not the one we are retooling towards.\n')
    for i, r in enumerate(recipes, 1):
        o.append(f'\tif = {{\n\t\tlimit = {{ has_active_production_method = {r.key} NOT = {{ var:pmr_to = {i} }} }}\n'
                 f'\t\tset_variable = {{ name = pmr_to value = {i} }}\n'
                 f'\t\tpmr_clear_lag_{b} = yes\n'
                 f'\t\tstate = {{ pmr_clear_retool_{b} = yes }}\n'
                 f'\t\tif = {{\n\t\t\tlimit = {{ var:pmr_from = {i} }}\n'
                 '\t\t\t# Back to the recipe it fully runs: nothing to retool.\n'
                 '\t\t\tset_variable = { name = pmr_p value = 1 }\n'
                 '\t\t\tif = { limit = { has_variable = pmr_retooling } remove_variable = pmr_retooling }\n'
                 f'\t\t\t{log("CANCEL", b)}\n\t\t}}\n'
                 '\t\telse = {\n'
                 '\t\t\tset_variable = { name = pmr_l_start value = level }\n'
                 '\t\t\tset_variable = { name = pmr_p value = 0 }\n'
                 '\t\t\tset_variable = pmr_retooling\n'
                 f'\t\t\tpmr_queue_retool_{b} = yes\n'
                 f'\t\t\t{log("SWITCH", b, extra=";gov_frac=[THIS.Var(\'pmr_gov_frac\').GetValue|2];gov=[THIS.Var(\'pmr_retool_gov\').GetValue|0];priv=[THIS.Var(\'pmr_retool_priv\').GetValue|0];queued=[THIS.Var(\'pmr_retool_queued\').GetValue|0]")}\n'
                 '\t\t}\n\t}\n')
    o.append('\t# Progress: p = (retool.level / N + level - L_start) / level, clamped to 0..1.\n'
             '\tif = {\n\t\tlimit = { has_variable = pmr_retooling }\n'
             f'\t\tpmr_read_retool_{b} = yes\n'
             '\t\tset_variable = { name = pmr_p value = var:pmr_retool_built }\n'
             '\t\tchange_variable = { name = pmr_p divide = pmr_retool_levels_per_level }\n'
             '\t\tchange_variable = { name = pmr_p add = level }\n'
             '\t\tchange_variable = { name = pmr_p subtract = var:pmr_l_start }\n'
             '\t\tchange_variable = { name = pmr_p divide = level }\n'
             '\t\tclamp_variable = { name = pmr_p min = 0 max = 1 }\n'
             '\t\tif = {\n\t\t\tlimit = { var:pmr_p >= 1 }\n'
             '\t\t\tset_variable = { name = pmr_from value = var:pmr_to }\n'
             '\t\t\tremove_variable = pmr_retooling\n'
             f'\t\t\tpmr_clear_lag_{b} = yes\n'
             f'\t\t\tstate = {{ pmr_clear_retool_{b} = yes }}\n'
             f'\t\t\t{log("DONE", b)}\n\t\t}}\n'
             '\t\telse = {\n'
             f'\t\t\tpmr_apply_lag_{b} = yes\n'
             f'\t\t\t{log("TICK", b, extra=";queued=[THIS.Var(\'pmr_retool_queued\').GetValue|0]")}\n'
             '\t\t}\n\t}\n}\n\n')
    return ''.join(o)


def shared_effects():
    # Government-owned share of the building, read through the documented ownership trigger as a
    # ladder of constant comparisons, so no trigger has to accept a variable on its right side.
    steps = round(1 / GOV_FRACTION_STEP)
    o = ['# Building scope. Sets var:pmr_gov_frac to the government-owned share of levels, to the\n'
         f'# nearest {GOV_FRACTION_STEP}. country_ownership_fraction is documented for building scope.\n'
         'pmr_read_gov_fraction = {\n\tset_variable = { name = pmr_gov_frac value = 0 }\n']
    first = True
    for k in range(steps, 0, -1):
        v = k * GOV_FRACTION_STEP
        threshold = v - GOV_FRACTION_STEP / 2
        kw = 'if' if first else 'else_if'
        first = False
        o.append(f'\t{kw} = {{ limit = {{ country_ownership_fraction >= {fmt(threshold)} }} '
                 f'set_variable = {{ name = pmr_gov_frac value = {fmt(v)} }} }}\n')
    o.append('}\n\n')
    return ''.join(o)


def dispatch_effects(buildings):
    o = ['# ===== dispatch\n\n'
         '# Building scope: run the tick for whichever PMR building this is.\n'
         'pmr_tick_building = {\n']
    for i, bk in enumerate(buildings):
        kw = 'if' if i == 0 else 'else_if'
        o.append(f'\t{kw} = {{ limit = {{ is_building_type = {bk} level >= 1 }} pmr_tick_{short(bk)} = yes }}\n')
    o.append('}\n\n'
             '# Building scope, for a retool pseudo-building that just completed a level: tick its parent.\n'
             'pmr_tick_parent_of_retool = {\n')
    for i, bk in enumerate(buildings):
        b = short(bk)
        kw = 'if' if i == 0 else 'else_if'
        o.append(f'\t{kw} = {{\n\t\tlimit = {{ is_building_type = building_pmr_retool_{b} state = {{ has_building = {bk} }} }}\n'
                 f'\t\tstate.b:{bk} = {{ pmr_tick_building = yes }}\n\t}}\n')
    o.append('}\n\n'
             '# State scope: tick every PMR building in the state.\n'
             'pmr_state_tick = {\n')
    for bk in buildings:
        o.append(f'\tif = {{ limit = {{ has_building = {bk} }} b:{bk} = {{ pmr_tick_building = yes }} }}\n')
    o.append('}\n')
    return ''.join(o)


ON_ACTIONS = '''# Appended to vanilla on_actions the documented way (_on_actions.md, MODDING INFO):
# the vanilla on_action calls ours, nothing vanilla is overwritten.

on_game_started = { on_actions = { pmr_on_game_started } }
on_production_method_changed = { on_actions = { pmr_on_production_method_changed } }
on_building_built = { on_actions = { pmr_on_building_built } }
on_monthly_pulse_state = { on_actions = { pmr_on_monthly_pulse_state } }

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

# Root = building that completed construction. A finished retool level moves p at once, and a
# new or expanded PMR building is seen (and its new level counted) without waiting for the month.
pmr_on_building_built = {
	effect = {
		pmr_tick_parent_of_retool = yes
		pmr_tick_building = yes
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
		add_technology_researched = bessemer_process
		capital = {
			if = {
				limit = { NOT = { has_building = building_steel_mill } }
				create_building = { building = building_steel_mill level = 5 }
			}
			pmr_state_tick = yes
			debug_log = "PMR;rec=TEST;arm=SETUP;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting]"
		}
	}
	ai_chance = { value = 0 }
}

pmr_test_tick_decision = {
	is_shown = { always = yes }
	possible = { always = yes }
	when_taken = {
		capital = {
			debug_log = "PMR;rec=TEST;arm=TICK_NOW;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting]"
		}
		every_scope_state = { pmr_state_tick = yes }
	}
	ai_chance = { value = 0 }
}
'''

DECISION_LOC = [
    ' pmr_test_setup_decision:0 "PMR test: grant Bessemer and a steel mill"',
    ' pmr_test_setup_decision_desc:0 "Researches the Bessemer Process and, if the capital has no Steel Mills, creates five levels there."',
    ' pmr_test_tick_decision:0 "PMR test: recompute retooling now"',
    ' pmr_test_tick_decision_desc:0 "Runs the monthly PMR tick on every state you own immediately, instead of waiting for the month to turn."',
]


if __name__ == '__main__':
    main()
