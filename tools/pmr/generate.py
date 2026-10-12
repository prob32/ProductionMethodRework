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

    report = {'treated': [], 'skipped': [], 'unrepresentable': [], 'icon_fallback': []}
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
    custom_old, custom_new = [], []

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
        for i, r in enumerate(recipes, 1):
            for var, lst in (('pmr_from', custom_old), ('pmr_to', custom_new)):
                lst.append(f'\ttext = {{\n\t\ttrigger = {{ is_building_type = {bk} state = {{ var:{var}_{b} = {i} }} }}\n'
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
                                  'icon_good': good,
                                  'labour_from': r0.key, 'employment': r0.employment,
                                  'retool_cost': retool_cost, 'lag_modifiers': len(pair_names)})

    write('common/production_methods/pmr_labour_production_methods.txt', header + '\n'.join(labour_pms))
    write('common/production_method_groups/pmr_labour_groups.txt', header + '\n'.join(labour_groups))
    write('common/buildings/pmr_retool_buildings.txt', header + '\n'.join(retools))
    write('common/building_groups/pmr_building_groups.txt', header +
          '# Shaped on vanilla bg_monuments_hidden: no lens, not in the outliner. With neither a category nor\n'
          '# is_government_funded, 1.14.5 showed privately funded retool levels in the government queue;\n'
          '# both are set here on the guess that the group decides which queue a construction joins.\n'
          'bg_pmr_retool = {\n\tcategory = urban\n\tis_government_funded = no\n\talways_possible = yes\n'
          '\tis_shown_in_outliner = no\n}\n')
    write('common/script_values/pmr_values.txt', header +
          f'pmr_retool_levels_per_level = {N}\n\n' + '\n'.join(costs) + '\n')
    write('common/static_modifiers/pmr_lag_modifiers.txt', header + '\n'.join(lags))
    write('common/scripted_effects/pmr_effects.txt', header + shared_effects() + '\n'.join(tick_effects)
          + dispatch_effects(dispatch))
    write('common/on_actions/pmr_on_actions.txt', header + ON_ACTIONS)
    write('common/customizable_localization/pmr_custom_loc.txt', header +
          '# Building scope. The recipe a building is retooling from, and the one it runs or retools to.\n'
          'pmr_old_recipe = {\n\ttype = building\n\tlog_loc_errors = no\n' + ''.join(custom_old) + '}\n\n'
          'pmr_new_recipe = {\n\ttype = building\n\tlog_loc_errors = no\n' + ''.join(custom_new) + '}\n')
    write('gui/building_details_panel.gui', patch_building_panel(
        open(os.path.join(game, 'gui', 'building_details_panel.gui'), encoding='utf-8-sig').read(), dispatch),
        bom=False)
    write('gui/production_methods.gui', patch_pm_browser(
        open(os.path.join(game, 'gui', 'production_methods.gui'), encoding='utf-8-sig').read(), dispatch),
        bom=False)
    loc += panel_loc(dispatch)
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
#
# Buildings cannot hold variables (1.14.5 error.log: "This scope doesn't support variables. Scope:
# Building"). Everything PMR remembers about a building lives on its state instead, under the
# building type's short name: a state has at most one building of each type, so pmr_p_steel_mill on
# a state is that state's steel mill's p. The tick runs in state scope and reaches the building with
# b:<building_type> only to add or remove its lag modifier and to read its ownership.

def log(rec, bk, b, extra=''):
    def v(name, f):
        return f"[THIS.Var('{name}_{b}').GetValue|{f}]"
    # Player-owned states only: debug.log rotates at about 2.5 MB and the world's lines overflow it.
    return (f'if = {{ limit = {{ owner = {{ is_player = yes }} }} '
            f'debug_log = "PMR;rec={rec};date=[TimeKeeper.GetCurrentDate.GetString];'
            f'country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={bk};'
            f"from={v('pmr_from', 0)};to={v('pmr_to', 0)};level={v('pmr_level', 0)};l_start={v('pmr_l_start', 0)};"
            f"retool_built={v('pmr_retool_built', 0)};retool_total={v('pmr_retool_total', 0)};"
            f"p={v('pmr_p', 3)}{extra}\" }}")


def tick_effect(bk, b, recipes, pairs):
    """Every effect for one building type. All run in STATE scope."""
    k = len(recipes)
    rb = f'building_pmr_retool_{b}'
    v = lambda name: f'{name}_{b}'           # noqa: E731  state variable for this building type
    o = [f'# ===== {bk}: ' + ', '.join(f'{i} = {r.key}' for i, r in enumerate(recipes, 1)) + '\n'
         '# State scope throughout; the building is b:' + bk + '.\n\n']

    def active(r):
        return f'is_production_method_active = {{ building_type = {bk} production_method = {r.key} }}'

    def adopt_running(ind):
        out = []
        for i, r in enumerate(recipes, 1):
            kw = 'if' if i == 1 else 'else_if'
            out.append(f'{ind}{kw} = {{ limit = {{ {active(r)} }} set_variable = {{ name = {v("pmr_from")} value = {i} }} '
                       f'set_variable = {{ name = {v("pmr_to")} value = {i} }} }}\n')
        return ''.join(out)

    # lag modifiers live on the building
    o.append(f'pmr_clear_lag_{b} = {{\n\tb:{bk} = {{\n')
    for name in pairs.values():
        o.append(f'\t\tif = {{ limit = {{ has_modifier = {name} }} remove_modifier = {name} }}\n')
    o.append('\t}\n}\n\n')

    o.append(f'pmr_apply_lag_{b} = {{\n\tpmr_clear_lag_{b} = yes\n'
             f'\tset_variable = {{ name = {v("pmr_lagmul")} value = 1 }}\n'
             f'\tchange_variable = {{ name = {v("pmr_lagmul")} subtract = var:{v("pmr_p")} }}\n')
    for (i, j), name in pairs.items():
        o.append(f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_from")} = {i} var:{v("pmr_to")} = {j} }}\n'
                 f'\t\tb:{bk} = {{ add_modifier = {{ name = {name} multiplier = prev.var:{v("pmr_lagmul")} }} }}\n\t}}\n')
    o.append('}\n\n')

    o.append(f'pmr_clear_retool_{b} = {{\n'
             f'\tif = {{ limit = {{ OR = {{ has_building = {rb} exists = b:{rb} }} }} remove_building = {rb} }}\n'
             f'\tif = {{ limit = {{ has_variable = pmr_retool_gate_{b} }} remove_variable = pmr_retool_gate_{b} }}\n'
             '}\n\n')

    # government-owned share of the building, read through the building-scope ownership trigger
    steps = round(1 / GOV_FRACTION_STEP)
    o.append(f'pmr_read_gov_{b} = {{\n\tset_variable = {{ name = {v("pmr_gov_frac")} value = 0 }}\n')
    for n in range(steps, 0, -1):
        frac = n * GOV_FRACTION_STEP
        kw = 'if' if n == steps else 'else_if'
        o.append(f'\t{kw} = {{ limit = {{ b:{bk} = {{ country_ownership_fraction >= {fmt(frac - GOV_FRACTION_STEP / 2)} }} }} '
                 f'set_variable = {{ name = {v("pmr_gov_frac")} value = {fmt(frac)} }} }}\n')
    o.append('}\n\n')

    o.append(f'pmr_queue_retool_{b} = {{\n'
             f'\tpmr_read_gov_{b} = yes\n'
             f'\tset_variable = {{ name = {v("pmr_retool_total")} value = var:{v("pmr_level")} }}\n'
             f'\tchange_variable = {{ name = {v("pmr_retool_total")} multiply = pmr_retool_levels_per_level }}\n'
             f'\tset_variable = {{ name = {v("pmr_retool_gov")} value = var:{v("pmr_retool_total")} }}\n'
             f'\tchange_variable = {{ name = {v("pmr_retool_gov")} multiply = var:{v("pmr_gov_frac")} }}\n'
             f'\tround_variable = {{ name = {v("pmr_retool_gov")} nearest = 1 }}\n'
             f'\tset_variable = {{ name = {v("pmr_retool_priv")} value = var:{v("pmr_retool_total")} }}\n'
             f'\tchange_variable = {{ name = {v("pmr_retool_priv")} subtract = var:{v("pmr_retool_gov")} }}\n'
             f'\tset_local_variable = {{ name = pmr_n_gov value = var:{v("pmr_retool_gov")} }}\n'
             f'\tset_local_variable = {{ name = pmr_n_priv value = var:{v("pmr_retool_priv")} }}\n'
             f'\tset_variable = pmr_retool_gate_{b}\n'
             '\twhile = {\n\t\tlimit = { local_var:pmr_n_gov > 0 }\n'
             f'\t\tstart_building_construction = {rb}\n'
             '\t\tchange_local_variable = { name = pmr_n_gov subtract = 1 }\n\t}\n'
             '\twhile = {\n\t\tlimit = { local_var:pmr_n_priv > 0 }\n'
             f'\t\tstart_privately_funded_building_construction = {rb}\n'
             '\t\tchange_local_variable = { name = pmr_n_priv subtract = 1 }\n\t}\n'
             f'\tpmr_read_retool_{b} = yes\n'
             '}\n\n')

    o.append(f'pmr_read_retool_{b} = {{\n'
             f'\tset_variable = {{ name = {v("pmr_retool_built")} value = 0 }}\n'
             f'\tset_variable = {{ name = {v("pmr_retool_queued")} value = 0 }}\n'
             '\t# A retool still entirely under construction may not count for has_building.\n'
             f'\tif = {{\n\t\tlimit = {{ OR = {{ has_building = {rb} exists = b:{rb} }} }}\n'
             f'\t\tset_variable = {{ name = {v("pmr_retool_built")} value = b:{rb}.level }}\n'
             f'\t\tset_variable = {{ name = {v("pmr_retool_queued")} value = b:{rb}.level_after_queued_constructions }}\n'
             '\t}\n}\n\n')

    # newest recipe the building runs or can activate; vanilla lists recipes oldest first
    o.append(f'pmr_best_{b} = {{\n\tset_variable = {{ name = {v("pmr_best_now")} value = 0 }}\n')
    for i in range(k, 0, -1):
        r = recipes[i - 1]
        kw = 'if' if i == k else 'else_if'
        o.append(f'\t{kw} = {{\n\t\tlimit = {{ OR = {{\n\t\t\t{active(r)}\n'
                 f'\t\t\tcan_activate_production_method = {{ building_type = {bk} production_method = {r.key} }}\n'
                 f'\t\t}} }}\n\t\tset_variable = {{ name = {v("pmr_best_now")} value = {i} }}\n\t}}\n')
    o.append('}\n\n')

    o.append(f'pmr_activate_{b} = {{\n')
    for i, r in enumerate(recipes, 1):
        kw = 'if' if i == 1 else 'else_if'
        o.append(f'\t{kw} = {{ limit = {{ var:{v("pmr_best_now")} = {i} }} '
                 f'activate_production_method = {{ building_type = {bk} production_method = {r.key} }} }}\n')
    o.append('}\n\n')

    o.append(f'pmr_set_bar_{b} = {{\n'
             f'\tset_variable = {{ name = {v("pmr_bar_old")} value = 1 }}\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = {v("pmr_retooling")} }}\n'
             f'\t\tchange_variable = {{ name = {v("pmr_bar_old")} subtract = var:{v("pmr_p")} }}\n'
             f'\t\tset_variable = {{ name = {v("pmr_ui_retooling")} value = 1 }}\n\t}}\n'
             f'\telse = {{ set_variable = {{ name = {v("pmr_ui_retooling")} value = 0 }} }}\n}}\n\n')

    best = f";best=[THIS.Var('{v('pmr_best_now')}').GetValue|0]"
    o.append(f'pmr_tick_{b} = {{\n'
             f'\tset_variable = {{ name = {v("pmr_level")} value = b:{bk}.level }}\n'
             f'\tpmr_best_{b} = yes\n'
             '\t# First sight: adopt whatever recipe runs now, with no lag.\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {v("pmr_to")} }} }}\n'
             f'\t\tset_variable = {{ name = {v("pmr_best")} value = var:{v("pmr_best_now")} }}\n'
             + adopt_running('\t\t') +
             f'\t\tset_variable = {{ name = {v("pmr_p")} value = 1 }}\n'
             f'\t\tset_variable = {{ name = {v("pmr_l_start")} value = var:{v("pmr_level")} }}\n'
             '\t\t# Newly constructed (not seen at game start or on first load): built with the newest\n'
             '\t\t# recipe the owner has, at no retooling cost.\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ has_variable = {v("pmr_new_build")} var:{v("pmr_best_now")} > 0 '
             f'NOT = {{ var:{v("pmr_to")} = var:{v("pmr_best_now")} }} }}\n'
             f'\t\t\tset_variable = {{ name = {v("pmr_from")} value = var:{v("pmr_best_now")} }}\n'
             f'\t\t\tset_variable = {{ name = {v("pmr_to")} value = var:{v("pmr_best_now")} }}\n'
             f'\t\t\tset_variable = {{ name = {v("pmr_adopting")} value = 0 }}\n'
             f'\t\t\tpmr_activate_{b} = yes\n'
             f'\t\t\t{log("ADOPT", bk, b)}\n\t\t}}\n'
             f'\t\t{log("INIT", bk, b, extra=best)}\n\t}}\n'
             f'\tif = {{ limit = {{ has_variable = {v("pmr_new_build")} }} remove_variable = {v("pmr_new_build")} }}\n')

    o.append('\t# Research: a newer recipe became available since the last tick. Switch to it; the switch\n'
             '\t# below then queues the retooling like any other.\n'
             f'\tif = {{\n\t\tlimit = {{ var:{v("pmr_best_now")} > var:{v("pmr_best")} }}\n'
             f'\t\tset_variable = {{ name = {v("pmr_best")} value = var:{v("pmr_best_now")} }}\n'
             f'\t\t{log("RESEARCH", bk, b, extra=best)}\n'
             f'\t\tpmr_activate_{b} = yes\n\t}}\n'
             f'\tset_variable = {{ name = {v("pmr_best")} value = var:{v("pmr_best_now")} }}\n')

    o.append('\t# A free adoption waits for the game to apply the activation: until it shows, the running\n'
             '\t# recipe is not a switch. Give up after one more tick and keep what runs.\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = {v("pmr_adopting")} }}\n')
    for i, r in enumerate(recipes, 1):
        kw = 'if' if i == 1 else 'else_if'
        o.append(f'\t\t{kw} = {{ limit = {{ var:{v("pmr_to")} = {i} {active(r)} }} remove_variable = {v("pmr_adopting")} }}\n')
    o.append(f'\t\telse = {{\n\t\t\tchange_variable = {{ name = {v("pmr_adopting")} add = 1 }}\n'
             f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:{v("pmr_adopting")} > 1 }}\n'
             f'\t\t\t\tremove_variable = {v("pmr_adopting")}\n' + adopt_running('\t\t\t\t') +
             f'\t\t\t\t{log("ADOPT_FAILED", bk, b)}\n\t\t\t}}\n\t\t}}\n\t}}\n')

    queued = f";queued=[THIS.Var('{v('pmr_retool_queued')}').GetValue|0]"
    sw = (f";gov_frac=[THIS.Var('{v('pmr_gov_frac')}').GetValue|2];gov=[THIS.Var('{v('pmr_retool_gov')}').GetValue|0];"
          f"priv=[THIS.Var('{v('pmr_retool_priv')}').GetValue|0]" + queued)
    o.append('\t# A switch: the running recipe is not the one we are retooling towards.\n'
             f'\tif = {{\n\t\tlimit = {{ NOT = {{ has_variable = {v("pmr_adopting")} }} }}\n')
    for i, r in enumerate(recipes, 1):
        o.append(f'\t\tif = {{\n\t\t\tlimit = {{ {active(r)} NOT = {{ var:{v("pmr_to")} = {i} }} }}\n'
                 f'\t\t\tset_variable = {{ name = {v("pmr_to")} value = {i} }}\n'
                 f'\t\t\tpmr_clear_lag_{b} = yes\n'
                 f'\t\t\tpmr_clear_retool_{b} = yes\n'
                 f'\t\t\tif = {{\n\t\t\t\tlimit = {{ var:{v("pmr_from")} = {i} }}\n'
                 '\t\t\t\t# Back to the recipe it fully runs: nothing to retool.\n'
                 f'\t\t\t\tset_variable = {{ name = {v("pmr_p")} value = 1 }}\n'
                 f'\t\t\t\tif = {{ limit = {{ has_variable = {v("pmr_retooling")} }} remove_variable = {v("pmr_retooling")} }}\n'
                 f'\t\t\t\t{log("CANCEL", bk, b)}\n\t\t\t}}\n'
                 '\t\t\telse = {\n'
                 f'\t\t\t\tset_variable = {{ name = {v("pmr_l_start")} value = var:{v("pmr_level")} }}\n'
                 f'\t\t\t\tset_variable = {{ name = {v("pmr_p")} value = 0 }}\n'
                 f'\t\t\t\tset_variable = {v("pmr_retooling")}\n'
                 f'\t\t\t\tpmr_queue_retool_{b} = yes\n'
                 f'\t\t\t\t{log("SWITCH", bk, b, extra=sw)}\n'
                 '\t\t\t}\n\t\t}\n')
    o.append('\t}\n')

    o.append('\t# Progress: p = (retool.level / N + level - L_start) / level, clamped to 0..1.\n'
             f'\tif = {{\n\t\tlimit = {{ has_variable = {v("pmr_retooling")} }}\n'
             f'\t\tpmr_read_retool_{b} = yes\n'
             f'\t\tset_variable = {{ name = {v("pmr_p")} value = var:{v("pmr_retool_built")} }}\n'
             f'\t\tchange_variable = {{ name = {v("pmr_p")} divide = pmr_retool_levels_per_level }}\n'
             f'\t\tchange_variable = {{ name = {v("pmr_p")} add = var:{v("pmr_level")} }}\n'
             f'\t\tchange_variable = {{ name = {v("pmr_p")} subtract = var:{v("pmr_l_start")} }}\n'
             f'\t\tchange_variable = {{ name = {v("pmr_p")} divide = var:{v("pmr_level")} }}\n'
             f'\t\tclamp_variable = {{ name = {v("pmr_p")} min = 0 max = 1 }}\n'
             f'\t\tif = {{\n\t\t\tlimit = {{ var:{v("pmr_p")} >= 1 }}\n'
             f'\t\t\tset_variable = {{ name = {v("pmr_from")} value = var:{v("pmr_to")} }}\n'
             f'\t\t\tremove_variable = {v("pmr_retooling")}\n'
             f'\t\t\tpmr_clear_lag_{b} = yes\n'
             f'\t\t\tpmr_clear_retool_{b} = yes\n'
             f'\t\t\t{log("DONE", bk, b)}\n\t\t}}\n'
             '\t\telse = {\n'
             f'\t\t\tpmr_apply_lag_{b} = yes\n'
             f'\t\t\t{log("TICK", bk, b, extra=queued)}\n'
             '\t\t}\n\t}\n'
             f'\tpmr_set_bar_{b} = yes\n}}\n\n')
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
                 f'\t\t\tif = {{ limit = {{ NOT = {{ has_variable = pmr_to_{b} }} }} set_variable = pmr_new_build_{b} }}\n'
                 f'\t\t\tpmr_tick_{b} = yes\n'
                 f'\t\t\tif = {{ limit = {{ has_variable = pmr_new_build_{b} }} remove_variable = pmr_new_build_{b} }}\n'
                 '\t\t}\n\t}\n')
    o.append('}\n\n'
             '# Building scope, for a retool pseudo-building that just completed a level: tick its parent.\n'
             'pmr_tick_parent_of_retool = {\n')
    for i, bk in enumerate(buildings):
        b = short(bk)
        kw = 'if' if i == 0 else 'else_if'
        o.append(f'\t{kw} = {{\n\t\tlimit = {{ is_building_type = building_pmr_retool_{b} }}\n'
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


def recipe_bar(bk, b):
    """The recipe bar for one building type. Two rows sized and centred to match the employment
    and cash-reserve bars to its right (26 px each, 8 apart), between the production method slot
    (x 2..72) and those bars (230 wide, 5 from the right edge of the 540 px panel): x 84..293."""
    def var(name):
        return f"Building.GetState.MakeScope.Var('{name}_{b}').GetValue"
    retooling = f'NotZero_CFixedPoint({var("pmr_ui_retooling")})'
    return f"""
				# PMR: recipe bar for {bk}. Gold is the recipe the building fully runs; while retooling,
				# blue is the share already moved to the new recipe.
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

						gold_progressbar_horizontal = {{
							size = {{ 100% 100% }}
							blockoverride "background" {{
								background = {{
									texture = "gfx/interface/progressbar/progressbar_default.dds"
									spriteType = Corneredtiled
									spriteborder = {{ 4 4 }}
									texture_density = 2
									using = progressbar_texture_properties
								}}
							}}
							blockoverride "values" {{
								min = 0
								max = 1
								value = "[FixedPointToFloat({var("pmr_bar_old")})]"
							}}
						}}
						textbox = {{
							visible = "[{retooling}]"
							position = {{ 6 0 }}
							size = {{ 98 26 }}
							align = left|nobaseline
							text = "PMR_BAR_OLD_{b}"
						}}
						textbox = {{
							visible = "[{retooling}]"
							position = {{ -6 0 }}
							parentanchor = right
							size = {{ 98 26 }}
							align = right|nobaseline
							text = "PMR_BAR_NEW_{b}"
						}}
						textbox = {{
							visible = "[Not({retooling})]"
							size = {{ 100% 100% }}
							align = center|nobaseline
							text = "PMR_BAR_FULL"
							tooltip = "PMR_BAR_FULL_TOOLTIP"
							using = tooltip_above
						}}
						# hover area for the retooling breakdown, only while retooling
						widget = {{
							visible = "[{retooling}]"
							size = {{ 100% 100% }}
							tooltip = "PMR_BAR_TOOLTIP_{b}"
							using = tooltip_above
						}}
					}}
				}}
"""


def patch_building_panel(text, buildings):
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
    text = text.replace(anchor, anchor + ''.join(recipe_bar(bk, short(bk)) for bk in buildings))
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


def patch_pm_browser(text, buildings):
    """Vanilla production_methods.gui: the building browser's per-type production method grids
    (which switch every building of a type at once) show no selectors for PMR building types, only
    the fixed labour icon. Asserted: three grids, or generation fails."""
    out, pos, n = [], 0, 0
    pattern = re.compile(r'datamodel = "\[(\w+)\.GetBuildingType\.AccessProductionMethodGroups\]"')
    for m in pattern.finditer(text):
        ctx = m.group(1)
        types = [f"ObjectsEqual({ctx}.GetBuildingType, GetBuildingType('{bk}').Self)" for bk in buildings]
        any_expr = types[-1]
        for t in reversed(types[:-1]):
            any_expr = f'Or({t}, {any_expr})'
        grid = text.rfind('fixedgridbox = {', 0, m.start())
        w = text.index('widget = {\n', m.end()) + len('widget = {\n')
        ind = text[text.rfind('\n', 0, w - len('widget = {\n')) + 1:w - len('widget = {\n')] + '\t'
        end = block_end(text, grid)
        gind = text[text.rfind('\n', 0, grid) + 1:grid]
        icons = ''.join(
            f'\n{gind}# PMR: fixed labour icon for {bk}\n{gind}icon = {{\n'
            f'{gind}\tvisible = "[ObjectsEqual({ctx}.GetBuildingType, GetBuildingType(\'{bk}\').Self)]"\n'
            f'{gind}\tposition = {{ 5 5 }}\n{gind}\tsize = {{ 40 40 }}\n'
            f'{gind}\ttexture = "gfx/interface/icons/production_method_icons/pmr_labour_{short(bk)}.dds"\n{gind}}}\n'
            for bk in buildings)
        out += [text[pos:w], f'{ind}# PMR: no selectors for PMR building types\n{ind}visible = "[Not({any_expr})]"\n',
                text[w:end], icons]
        pos = end
        n += 1
    if n != 3:
        raise SystemExit(f'production_methods.gui: expected 3 per-type production method grids, found {n}; '
                         'update patch_pm_browser')
    return ''.join(out) + text[pos:]


def panel_loc(buildings):
    loc = [
        ' PMR_RECIPE_BAR_TITLE:0 "#bold [Building.GetCustom(\'pmr_new_recipe\')]#!"',
        ' PMR_RECIPE_BAR_TITLE_RETOOLING:0 "Retooling to #bold [Building.GetCustom(\'pmr_new_recipe\')]#!"',
        ' PMR_BAR_FULL:0 "#bold 100%#!"',
        ' PMR_BAR_FULL_TOOLTIP:0 "[Building.GetCustom(\'pmr_new_recipe\')]: #bold 100%#!"',
        ' PMR_RECIPE_BAR_TOOLTIP:0 "This building runs #bold [Building.GetCustom(\'pmr_new_recipe\')]#!. When your country researches a newer recipe it switches automatically, and the change takes effect as retooling construction completes."',
    ]
    for bk in buildings:
        b = short(bk)

        def var(name, f):
            return f"[Building.GetState.MakeScope.Var('{name}_{b}').GetValue|{f}]"
        loc += [
            f' PMR_BAR_OLD_{b}:0 "#bold {var("pmr_bar_old", "%0")}#!"',
            f' PMR_BAR_NEW_{b}:0 "#bold {var("pmr_p", "%0")}#!"',
            f' PMR_BAR_TOOLTIP_{b}:0 "#bold Retooling#!\\n[Building.GetCustom(\'pmr_old_recipe\')] (gold): #bold {var("pmr_bar_old", "%0")}#!'
            f'\\n[Building.GetCustom(\'pmr_new_recipe\')] (blue): #bold {var("pmr_p", "%0")}#!'
            f'\\nRetooling levels built: {var("pmr_retool_built", "0")} of {var("pmr_retool_total", "0")}"',
        ]
    return loc


ON_ACTIONS = '''# Appended to vanilla on_actions the documented way (_on_actions.md, MODDING INFO):
# the vanilla on_action calls ours, nothing vanilla is overwritten.

on_game_started = { on_actions = { pmr_on_game_started } }
on_production_method_changed = { on_actions = { pmr_on_production_method_changed } }
on_building_built = { on_actions = { pmr_on_building_built } }
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

# Root = building that completed construction. A finished retool level moves p at once, and a
# new or expanded PMR building is seen (and its new level counted) without waiting for the month.
pmr_on_building_built = {
	effect = {
		pmr_tick_parent_of_retool = yes
		pmr_built_building = yes
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
				create_building = { building = building_steel_mill level = 5 }
			}
			pmr_state_tick = yes
			debug_log = "PMR;rec=TEST;arm=SETUP;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting]"
		}
		add_technology_researched = bessemer_process
		capital = { pmr_state_tick = yes }
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
    ' pmr_test_setup_decision_desc:0 "If the capital has no Steel Mills, creates five levels there; then researches the Bessemer Process, which switches the mill to it and starts retooling."',
    ' pmr_test_tick_decision:0 "PMR test: recompute retooling now"',
    ' pmr_test_tick_decision_desc:0 "Runs the monthly PMR tick on every state you own immediately, instead of waiting for the month to turn."',
]


if __name__ == '__main__':
    main()
