"""Frames (method-count rework, Pat 2026-11-10): a building runs one frame method per frame group, and "less" modifiers
scale its goods and jobs down to the blend of its levels.

From the design thread's draft (pmr/method-count/draft/frames.py, PLAN.md sections 3 and 8). generate.py builds the
member tables and calls this module for the union frames, the frame bodies, the modifiers and pmr_frame_<b>.

Per building:
- the recipe frame group (the vanilla recipe group): a pure frame per retool target (the vanilla recipe method, or
  pm_pmr_pair_<b>_<r>_<a>) at its full goods, jobs and other modifiers, then one union frame per target,
  pm_pmr_union_<b>_<p>: each good and pop type at the most any combination of the axes uses, and the other modifiers
  of target p;
- one option frame group per trade-off group (the vanilla group): the none, the options (vanilla's own bodies), and
  pm_pmr_union_<b>_x<gi>;
- pmr_frame_<b> (state scope): picks the frames from the shares and sizes the "less" modifiers.

Shared: pmr_less_in_<g>, pmr_less_out_<g>, pmr_less_job_<pop>, each its key at -1, applied with a multiplier 0..1, and
the modifier type definitions they need. The job modifiers are off (JOB_LESS): they moved no jobs in q99's run, so a
blended building holds its union frame's jobs.

Treatment (the working-conditions shares, pm_pmr_x_<b>_<j>_<n>) stays share methods for now: its goods and jobs are
"live" amounts here, counted in both the blend (A) and the frames (B), so a "less" modifier on the same good leaves them
whole.
"""

import collections

SHARE_STEPS = 100
GENERIC_ICON = 'gfx/interface/icons/generic_icons/mixed_icon_base.dds'
LESS_ICON = GENERIC_ICON
SECTIONS = ('building_modifiers', 'state_modifiers', 'country_modifiers')
LOOKUP_FROM = 7      # as generate.py: a ladder this long becomes a binary search
EPS = 1e-9
LESS_NAME = 'Retooling'
# q99's run (Pat, 2026-11-10): building_employment_<pop>_mult on a building's own modifier reads back and shows on the
# Modifiers tab ("Shopkeepers Per Level -60%") but moves no jobs: the Midlands furniture manufactory kept the union's
# 30.0K capacity with its shopkeepers cut 43%, and the probe wharf every laborer at -50%. A blend holds its union's jobs
# either way, so until a route that moves jobs is found (frame_probe.py, q100) the job modifiers are neither made nor
# applied: each was an icon, a Modifiers tab row and a line that did nothing, sized every time the frame ran.
JOB_LESS = False
OPTION_UNION_NAME = 'Trade-off'


FRAME_DOC = """# Union frames (method-count rework, frames.py): pm_pmr_union_<b>_<p> stands for retool target p while the building's
# levels are blended, each good and job at the most any combination of its recipes and automation uses, the rest as
# target p's; pm_pmr_union_<b>_x<group> for a trade-off group in a blend. Each unlocks only while it runs, so only the
# tick (pmr_frame_<b>) sets one; the "less" modifiers scale its goods down to the blend (and its jobs, were
# frames.JOB_LESS on: without it a blended building holds the frame's jobs).

"""
LESS_DOC = """# "Less" modifiers (method-count rework, frames.py): each its multiplier at -1, applied to a blended building by
# pmr_frame_<b> with a multiplier of 1 - (blended amount / frame amount), 0 to 1 in steps of 0.01.

"""
TYPES_DOC = """# The goods and job multipliers the "less" modifiers use: the engine knows them by pattern, but an undeclared one
# loads empty ("Unknown modifier type"). Vanilla and Company Culture declare some; these are the rest, styled as
# vanilla's.

"""


def fmt(x):
    s = f'{x:.5f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def short(bk):
    return bk[len('building_'):] if bk.startswith('building_') else bk


def lookup(var, ns, body, ind='\t'):
    """body(x) for the x of ns (ascending integers) that var holds (generate.py's lookup)."""
    if len(ns) < LOOKUP_FROM:
        return ''.join(f'{ind}{"if" if j == 0 else "else_if"} = {{ limit = {{ {var} = {x} }} {body(x)} }}\n'
                       for j, x in enumerate(ns))

    def find(lo, hi, ind):
        if lo == hi:
            return f'{ind}if = {{ limit = {{ {var} = {ns[lo]} }} {body(ns[lo])} }}\n'
        mid = (lo + hi) // 2
        return (f'{ind}if = {{\n{ind}\tlimit = {{ {var} > {ns[mid]} }}\n' + find(mid + 1, hi, ind + '\t')
                + f'{ind}}}\n{ind}else = {{\n' + find(lo, mid, ind + '\t') + f'{ind}}}\n')
    return find(0, len(ns) - 1, ind)


# ---------------------------------------------------------------------------------------------------------------------
# Member tables. mods everywhere: {(section, sub-block): {modifier: amount at 100%}}, sub-block as in vanilla
# (workforce_scaled, level_scaled, unscaled).

class Member:
    """One blend member: a plain recipe (axis 'recipe') or an automation method (axis = its vanilla group). Its share
    is pmr_n_<j>_<b>."""
    def __init__(self, j, key, axis, pairs, mods):
        self.j, self.key, self.axis, self.pairs, self.mods = j, key, axis, list(pairs), mods


class Option:
    """One trade-off option: mods is its difference from the group's none. Its share is pmr_x_<j>_<b>."""
    def __init__(self, j, key, mods):
        self.j, self.key, self.mods = j, key, mods


class OptionGroup:
    def __init__(self, key, gi, none, none_mods, options):
        self.key, self.gi, self.none, self.none_mods, self.options = key, gi, none, none_mods, list(options)


class Live:
    """A treatment option's share methods (pm_pmr_x_<b>_<j>_<n>): mods x pmr_x_<j>_<b> / SHARE_STEPS run as they are."""
    def __init__(self, j, mods):
        self.j, self.mods = j, mods


class Building:
    """pair_keys[p - 1]: retool target p (the vanilla recipe key or pm_pmr_pair_<b>_<r>_<a>), in pmr_to order.
    own_mods[key]: modifiers target p's frame carries besides its members' (a recipe's unscaled ones)."""
    def __init__(self, bk, recipe_group, pair_keys, members, option_groups=(), own_mods=None, live=()):
        self.bk, self.b, self.recipe_group, self.pair_keys = bk, short(bk), recipe_group, list(pair_keys)
        self.members, self.option_groups = list(members), list(option_groups)
        self.own_mods, self.live = own_mods or {}, list(live)
        self.recipes = [m for m in self.members if m.axis == 'recipe']
        self.auto_axes = list(dict.fromkeys(m.axis for m in self.members if m.axis != 'recipe'))
        for p in range(1, len(self.pair_keys) + 1):
            if sum(1 for m in self.recipes if p in m.pairs) != 1:
                raise SystemExit(f'{bk}: target {p} is in {sum(1 for m in self.recipes if p in m.pairs)} recipe members')
            for ax in self.auto_axes:
                if sum(1 for m in self.members if m.axis == ax and p in m.pairs) > 1:
                    raise SystemExit(f'{bk}: target {p} has two members of {ax}')

    def pair_members(self, p):
        return [m for m in self.members if p in m.pairs]

    def pair_recipe(self, p):
        return next(m.j for m in self.recipes if p in m.pairs)

    def pair_auto(self, p):
        """{axis: member j, 0 for the axis's none}"""
        return {ax: next((m.j for m in self.members if m.axis == ax and p in m.pairs), 0) for ax in self.auto_axes}


def add_mods(*ms):
    out = {}
    for m in ms:
        for k, d in (m or {}).items():
            o = out.setdefault(k, {})
            for mk, mv in d.items():
                o[mk] = o.get(mk, 0) + mv
    return out


def sub_mods(a, b):
    """a less b, zeros dropped"""
    out = add_mods(a)
    for k, d in (b or {}).items():
        o = out.setdefault(k, {})
        for mk, mv in d.items():
            o[mk] = o.get(mk, 0) - mv
            if abs(o[mk]) < EPS:
                del o[mk]
    return {k: d for k, d in out.items() if d}


def split(mods):
    """(goods in, goods out, jobs, rest): goods are workforce_scaled goods_*_add, jobs level_scaled
    building_employment_*_add; rest is every other modifier, {(section, sub): {modifier: amount}}."""
    gin, gout, jobs, rest = {}, {}, {}, {}
    for (sec, sub), d in mods.items():
        for k, val in d.items():
            if sec == 'building_modifiers' and sub == 'workforce_scaled' and k.startswith('goods_input_') and k.endswith('_add'):
                gin[k[12:-4]] = gin.get(k[12:-4], 0) + val
            elif sec == 'building_modifiers' and sub == 'workforce_scaled' and k.startswith('goods_output_') and k.endswith('_add'):
                gout[k[13:-4]] = gout.get(k[13:-4], 0) + val
            elif sec == 'building_modifiers' and sub == 'level_scaled' and k.startswith('building_employment_') and k.endswith('_add'):
                jobs[k[20:-4]] = jobs.get(k[20:-4], 0) + val
            else:
                rest.setdefault((sec, sub), {})[k] = rest.get((sec, sub), {}).get(k, 0) + val
    return gin, gout, jobs, rest


def join(gin, gout, jobs, rest):
    out = {}
    if gin or gout:
        ws = out.setdefault(('building_modifiers', 'workforce_scaled'), {})
        ws.update({f'goods_input_{g}_add': x for g, x in gin.items()})
        ws.update({f'goods_output_{g}_add': x for g, x in gout.items()})
    if jobs:
        out[('building_modifiers', 'level_scaled')] = {f'building_employment_{p}_add': x for p, x in jobs.items()}
    return add_mods(out, rest)


def nonneg(d):
    return {k: x for k, x in d.items() if x > EPS}


def nonzero(d):
    return {k: x for k, x in d.items() if abs(x) > EPS}


# ---------------------------------------------------------------------------------------------------------------------
# What each frame carries

def pair_amounts(bld, p):
    """target p at full amounts: its members plus what its own frame keeps"""
    return split(add_mods(*[m.mods for m in bld.pair_members(p)], bld.own_mods.get(bld.pair_keys[p - 1])))


def pure_mods(bld, p):
    """target p's pure frame: never below 0 a good or a pop (63 pairs automate away more laborers than they have)"""
    gi, go, gj, rest = pair_amounts(bld, p)
    return join(nonneg(gi), nonneg(go), nonneg(gj), rest)


def recipe_union(bld):
    """each good and pop type at the most any combination of the axes uses: the largest recipe's amount plus, per
    automation group, the largest of its members' (or 0, its none), never below 0. A blend mixes the axes
    independently, so A <= B always, even where some combinations are no target."""
    rec = [split(add_mods(m.mods)) for m in bld.recipes]
    own = [split(bld.own_mods.get(k, {})) for k in bld.pair_keys]
    mem = {m.j: split(m.mods) for m in bld.members}
    out = []
    for side in range(3):
        keys = {k for s in rec + own for k in s[side]} | {k for s in mem.values() for k in s[side]}
        tot = {}
        for k in sorted(keys):   # sorted: a set's order moves between runs and churns the generated file
            x = max(s[side].get(k, 0) for s in rec) + max([0] + [s[side].get(k, 0) for s in own])
            for ax in bld.auto_axes:
                x += max([0] + [mem[m.j][side].get(k, 0) for m in bld.members if m.axis == ax])
            tot[k] = x
        out.append(nonneg(tot))
    return tuple(out)


def option_full(og, o):
    """an option's (or the none's, o None) amounts as its vanilla method has them: none + difference"""
    return split(add_mods(og.none_mods, o.mods if o else None))


def option_union(og):
    """each amount at the most the none or any option has; an option's amount can be below the none's (canning
    takes grain off the recipe), so an amount every option lowers stays at the none's"""
    full = [option_full(og, o) for o in [None] + og.options]
    out = []
    for side in range(3):
        keys = {k for f in full for k in f[side]}
        out.append(nonzero({k: max(f[side].get(k, 0) for f in full) for k in sorted(keys)}))
    return tuple(out)


def frame_goods(bld):
    """(goods in, goods out, pops) the building's frames name: what the less modifiers may scale"""
    gin, gout, pops = set(), set(), set()
    for p in range(1, len(bld.pair_keys) + 1):
        pi, po, pj, _ = pair_amounts(bld, p)
        gin |= set(nonzero(pi)); gout |= set(nonzero(po)); pops |= set(nonzero(pj))
    for og in bld.option_groups:
        for o in [None] + og.options:
            oi, oo, oj, _ = option_full(og, o)
            gin |= set(nonzero(oi)); gout |= set(nonzero(oo)); pops |= set(nonzero(oj))
    return sorted(gin), sorted(gout), sorted(pops) if JOB_LESS else []


def union_key(bld, p):
    return f'pm_pmr_union_{bld.b}_{p}'


def option_union_key(bld, og):
    return f'pm_pmr_union_{bld.b}_x{og.gi}'


def unions_of(bld):
    """{frame key: the union frame standing in for it}"""
    out = {k: union_key(bld, p) for p, k in enumerate(bld.pair_keys, 1)}
    for og in bld.option_groups:
        out.update({k: option_union_key(bld, og) for k in [og.none] + [o.key for o in og.options]})
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Methods

def sections(mods, ind='\t'):
    """mods as a method's modifier blocks, in vanilla's section order"""
    body = []
    for sec in SECTIONS:
        subs = [(sub, d) for (s2, sub), d in mods.items() if s2 == sec and nonzero(d)]
        if not subs:
            continue
        body.append(f'{ind}{sec} = {{\n')
        for sub, d in subs:
            body.append(f'{ind}\t{sub} = {{\n' + ''.join(f'{ind}\t\t{k} = {fmt(x)}\n' for k, x in nonzero(d).items())
                        + f'{ind}\t}}\n')
        body.append(f'{ind}}}\n')
    return ''.join(body)


def union_methods(bld, texture):
    """{union key: definition}: the recipe unions, then each option group's. texture(key): a frame's icon. Each union
    unlocks only while it runs, so neither the AI nor the player can pick one; the tick sets it."""
    out = collections.OrderedDict()
    ui, uo, uj = recipe_union(bld)
    for p, key in enumerate(bld.pair_keys, 1):
        _, _, _, rest = pair_amounts(bld, p)
        uk = union_key(bld, p)
        out[uk] = (f'{uk} = {{\n\ttexture = "{texture(key)}"\n\tunlocking_production_methods = {{ {uk} }}\n'
                   + sections(join(ui, uo, uj, rest)) + '}\n')
    for og in bld.option_groups:
        ui2, uo2, uj2 = option_union(og)
        _, _, _, nrest = option_full(og, None)
        uk = option_union_key(bld, og)
        out[uk] = (f'{uk} = {{\n\ttexture = "{texture(og.none)}"\n\tunlocking_production_methods = {{ {uk} }}\n'
                   + sections(join(ui2, uo2, nonneg(uj2), nrest)) + '}\n')
    return out


def frame_loc(bld):
    """English names of the new methods: a union frame reads as the target it stands for"""
    return ([f' {union_key(bld, p)}:0 "${k}$"' for p, k in enumerate(bld.pair_keys, 1)]
            + [f' {option_union_key(bld, og)}:0 "{OPTION_UNION_NAME}"' for og in bld.option_groups])


# ---------------------------------------------------------------------------------------------------------------------
# "Less" modifiers and their types

def less_name(kind, x):
    return f'pmr_less_{kind}_{x}'


def less_keys(gin, gout, pops):
    """[(static modifier, modifier type)]"""
    return ([(less_name('in', g), f'goods_input_{g}_mult') for g in sorted(gin)]
            + [(less_name('out', g), f'goods_output_{g}_mult') for g in sorted(gout)]
            + [(less_name('job', p), f'building_employment_{p}_mult') for p in sorted(pops)])


def static_modifiers(gin, gout, pops):
    return ''.join(f'{name} = {{\n\ticon = "{LESS_ICON}"\n\t{key} = -1\n}}\n\n' for name, key in less_keys(gin, gout, pops))


def static_modifier_loc(gin, gout, pops):
    return [f' {name}:0 "{LESS_NAME}"' for name, _ in less_keys(gin, gout, pops)]


def type_keys(gin, gout, pops, declared=frozenset()):
    return [key for _, key in less_keys(gin, gout, pops) if key not in declared]


def modifier_types(keys):
    """Definitions styled as vanilla's 01_building_modifier_types.txt: inputs and jobs bad, outputs good."""
    out = []
    for key in keys:
        color = 'good' if key.startswith('goods_output_') else 'bad'
        out.append(f'{key} = {{\n\tdecimals = 1\n\tcolor = {color}\n\tpercent = yes\n\tgame_data = {{ ai_value = 0 }}\n}}\n')
    return '\n'.join(out)


def modifier_type_loc(keys, vanilla_loc=frozenset(), named=frozenset()):
    """Names for the types modifier_types() adds: vanilla's own name of the matching _add type where it has one. A type
    vanilla already names (named) gets none: q99 named every building_employment_<pop>_mult a second time, and the game
    logged a duplicate key for each and kept vanilla's."""
    out = []
    for key in keys:
        if key in named:
            continue
        add = key[:-len('_mult')] + '_add'
        if add in vanilla_loc and key.startswith('goods_'):   # a job type's _add reads "per level"
            out.append(f' {key}:0 "${add}$"')
        elif key.startswith('goods_'):
            g = key.split('_', 2)[2][:-len('_mult')]
            side = 'input' if key.startswith('goods_input_') else 'output'
            out.append(f' {key}:0 "@{g}! ${g}$ ($concept_{side}_goods$)"')
        else:
            pop = key[len('building_employment_'):-len('_mult')]
            out.append(f' {key}:0 "@{pop}! ${pop}$"')
        out.append(f' {key}_desc:0 ""')
    return out


# ---------------------------------------------------------------------------------------------------------------------
# The effect

def state_vars(bld):
    """the per-building state variables pmr_frame_<b> keeps: the sizes applied, which must go with the building (a new
    one has no modifiers), and its flags"""
    gin, gout, pops = frame_goods(bld)
    return ([f'pmr_lxi_{g}_{bld.b}' for g in gin] + [f'pmr_lxo_{g}_{bld.b}' for g in gout]
            + [f'pmr_lj_{p}_{bld.b}' for p in pops] + [f'pmr_fz_{bld.b}', f'pmr_fok_{bld.b}'])


def clear_vars(bld, ind='\t'):
    return ''.join(f'{ind}if = {{ limit = {{ has_variable = {n} }} remove_variable = {n} }}\n' for n in state_vars(bld))


def frame_effect(bld, log=True, count=False):
    """pmr_frame_<b>, state scope, after pmr_blend_<b> and pmr_opts_<b> (the shares pmr_n_<j>_<b>, pmr_x_<j>_<b> and
    pmr_xn_<gi>_<b> are set). Call only where b:<bk> exists. count (test builds): each frame put back after a change
    from outside PMR's tick (the AI's, the game's) adds 1 to the UNDO line's count (pmr_count_undo)."""
    bk, b = bld.bk, bld.b
    v = lambda name: f'{name}_{b}'                     # noqa: E731
    n = lambda j: f'var:{v(f"pmr_n_{j}")}'             # noqa: E731
    xs = lambda j: f'var:{v(f"pmr_x_{j}")}'            # noqa: E731
    setv = lambda name, val: f'set_variable = {{ name = {name} value = {val} }}'   # noqa: E731
    spec = lambda key: f'building_type = {bk} production_method = {key}'           # noqa: E731
    on = lambda key: f'is_production_method_active = {{ {spec(key)} }}'           # noqa: E731
    may = lambda key: f'OR = {{ {on(key)} can_activate_production_method = {{ {spec(key)} }} }}'   # noqa: E731
    act = lambda key: (f'if = {{ limit = {{ NOT = {{ {on(key)} }} }} '                                     # noqa: E731
                       f'activate_production_method = {{ {spec(key)} }} {setv("pmr_fm_ch", 1)}'
                       + (' pmr_count_undo = yes' if count else '') + ' }')
    P = len(bld.pair_keys)
    axes = list(enumerate(bld.auto_axes, 1))
    o = [f'# ===== {bk}: targets ' + ', '.join(f'{p} = {k}' for p, k in enumerate(bld.pair_keys, 1)) + '\n',
         f'pmr_frame_{b} = {{\n\t{setv("pmr_fm_ch", 0)}\n']

    # 1. the recipe axis: the recipe member with the largest share, and per automation group its largest (0: none)
    o.append('\t# largest share on each axis (first wins a tie)\n'
             f'\t{setv("pmr_fm_r", bld.recipes[0].j)}\n\t{setv("pmr_fm_rs", n(bld.recipes[0].j))}\n')
    for m in bld.recipes[1:]:
        o.append(f'\tif = {{ limit = {{ {n(m.j)} > var:pmr_fm_rs }} {setv("pmr_fm_r", m.j)} {setv("pmr_fm_rs", n(m.j))} }}\n')
    for k, ax in axes:
        ms = [m for m in bld.members if m.axis == ax]
        o.append(f'\t# {ax}\n\t{setv(f"pmr_fm_g{k}", 0)}\n'
                 f'\tset_variable = {{ name = pmr_fm_gs{k} value = {{ value = {SHARE_STEPS} '
                 + ' '.join(f'subtract = {n(m.j)}' for m in ms) + ' } }\n'
                 + ''.join(f'\tif = {{ limit = {{ {n(m.j)} > var:pmr_fm_gs{k} }} {setv(f"pmr_fm_g{k}", m.j)} '
                           f'{setv(f"pmr_fm_gs{k}", n(m.j))} }}\n' for m in ms))
    o.append(f'\t{setv("pmr_fm_pr", 0)}\n'
             f'\tif = {{ limit = {{ var:pmr_fm_rs = {SHARE_STEPS} '
             + ''.join(f'var:pmr_fm_gs{k} = {SHARE_STEPS} ' for k, _ in axes) + f'}} {setv("pmr_fm_pr", 1)} }}\n')

    # 2. the target those make; a combination that is no target falls back to the recipe's first one
    def pair_of(rj):
        ps = [p for p in range(1, P + 1) if bld.pair_recipe(p) == rj]
        body = setv('pmr_fm_pair', ps[0])
        if axes:
            for i, p in enumerate(ps):
                cond = ' '.join(f'var:pmr_fm_g{k} = {bld.pair_auto(p)[ax]}' for k, ax in axes)
                body += f' {"if" if i == 0 else "else_if"} = {{ limit = {{ {cond} }} {setv("pmr_fm_pair", p)} }}'
        return body
    o.append('\t# the target the largest shares make\n'
             + lookup('var:pmr_fm_r', sorted(m.j for m in bld.recipes), pair_of))

    # 3. the recipe frame: pure only where the game lets the building run it (technology, laws), else its union; each
    # frame activated only if it isn't running (activate_production_method checks no unlock, and a frame the game
    # can't run would be switched away again, through on_production_method_changed back into this tick)
    pairs = list(range(1, P + 1))
    o.append('\tif = {\n\t\tlimit = { var:pmr_fm_pr = 1 }\n'
             + lookup('var:pmr_fm_pair', pairs,
                      lambda p: f'if = {{ limit = {{ NOT = {{ {may(bld.pair_keys[p - 1])} }} }} {setv("pmr_fm_pr", 0)} }}', '\t\t')
             + '\t}\n'
             '\tif = {\n\t\tlimit = { var:pmr_fm_pr = 1 }\n'
             + lookup('var:pmr_fm_pair', pairs, lambda p: act(bld.pair_keys[p - 1]), '\t\t')
             + '\t}\n\telse = {\n'
             + lookup('var:pmr_fm_pair', pairs, lambda p: act(union_key(bld, p)), '\t\t') + '\t}\n')

    # 4. each trade-off group: the none or option with the largest share; pure where it is at 100% and may run
    for og in bld.option_groups:
        gi = og.gi
        keys = {0: og.none, **{x.j: x.key for x in og.options}}
        o.append(f'\t# {og.key}\n\t{setv(f"pmr_fm_o{gi}", 0)}\n\t{setv(f"pmr_fm_os{gi}", "var:" + v(f"pmr_xn_{gi}"))}\n'
                 + ''.join(f'\tif = {{ limit = {{ {xs(x.j)} > var:pmr_fm_os{gi} }} {setv(f"pmr_fm_o{gi}", x.j)} '
                           f'{setv(f"pmr_fm_os{gi}", xs(x.j))} }}\n' for x in og.options)
                 + f'\t{setv(f"pmr_fm_po{gi}", 0)}\n'
                 f'\tif = {{\n\t\tlimit = {{ var:pmr_fm_os{gi} = {SHARE_STEPS} }}\n'
                 + lookup(f'var:pmr_fm_o{gi}', sorted(keys),
                          lambda j, keys=keys, gi=gi: f'if = {{ limit = {{ {may(keys[j])} }} {setv(f"pmr_fm_po{gi}", 1)} }}', '\t\t')
                 + '\t}\n'
                 f'\tif = {{\n\t\tlimit = {{ var:pmr_fm_po{gi} = 1 }}\n'
                 + lookup(f'var:pmr_fm_o{gi}', sorted(keys), lambda j, keys=keys: act(keys[j]), '\t\t')
                 + f'\t}}\n\telse = {{ {act(option_union_key(bld, og))} }}\n')
    o.append(f'\t{setv("pmr_fm_pure", 0)}\n'
             '\tif = { limit = { var:pmr_fm_pr = 1 ' + ''.join(f'var:pmr_fm_po{og.gi} = 1 ' for og in bld.option_groups)
             + f'}} {setv("pmr_fm_pure", 1)} }}\n')

    # 5. sizes: x = 1 - A / B, A the blended amount, B what the running frames carry, in steps of 0.01. A and B are
    # both kept x SHARE_STEPS (share points x amount), so no multiplier is smaller than an amount.
    gin, gout, pops = frame_goods(bld)
    ui, uo, uj = recipe_union(bld)
    unions = {og.gi: option_union(og) for og in bld.option_groups}
    mem = {m.j: split(m.mods) for m in bld.members}
    opt = {og.gi: (option_full(og, None), {x.j: split(x.mods) for x in og.options}) for og in bld.option_groups}
    live = [(lv.j, split(lv.mods)) for lv in bld.live]

    def size(side, name):
        # side: 0 goods in, 1 goods out, 2 jobs
        terms = [(j, d[side].get(name, 0)) for j, d in mem.items() if abs(d[side].get(name, 0)) > EPS]
        u = (ui, uo, uj)[side].get(name, 0)
        s = ('\t\t# the recipe axis: B is A itself on a pure frame (never below 0), else the union\'s\n'
             '\t\tset_variable = { name = pmr_fm_a value = { value = 0'
             + ''.join(f' add = {{ value = {n(j)} multiply = {fmt(a)} }}' for j, a in terms) + ' } }\n'
             f'\t\t{setv("pmr_fm_b", fmt(u * SHARE_STEPS))}\n'
             f'\t\tif = {{ limit = {{ var:pmr_fm_pr = 1 }} {setv("pmr_fm_b", "var:pmr_fm_a")} '
             f'if = {{ limit = {{ var:pmr_fm_b < 0 }} {setv("pmr_fm_b", 0)} }} }}\n')
        lterms = [(j, d[side].get(name, 0)) for j, d in live if abs(d[side].get(name, 0)) > EPS]
        if lterms:
            s += ('\t\t# treatment\'s share methods run as they are: in A and B alike\n'
                  '\t\tset_variable = { name = pmr_fm_ao value = { value = 0'
                  + ''.join(f' add = {{ value = {xs(j)} multiply = {fmt(a)} }}' for j, a in lterms) + ' } }\n'
                  '\t\tchange_variable = { name = pmr_fm_a add = var:pmr_fm_ao }\n'
                  '\t\tchange_variable = { name = pmr_fm_b add = var:pmr_fm_ao }\n')
        for og in bld.option_groups:
            none = opt[og.gi][0][side].get(name, 0)
            oterms = [(j, d[side].get(name, 0)) for j, d in opt[og.gi][1].items() if abs(d[side].get(name, 0)) > EPS]
            ou = unions[og.gi][side].get(name, 0)
            if not oterms and abs(none) < EPS and abs(ou) < EPS:
                continue
            s += (f'\t\t# {og.key}\n'
                  f'\t\tset_variable = {{ name = pmr_fm_ao value = {{ value = {fmt(none * SHARE_STEPS)}'
                  + ''.join(f' add = {{ value = {xs(j)} multiply = {fmt(a)} }}' for j, a in oterms) + ' } }\n'
                  '\t\tchange_variable = { name = pmr_fm_a add = var:pmr_fm_ao }\n'
                  f'\t\tif = {{ limit = {{ var:pmr_fm_po{og.gi} = 1 }} change_variable = {{ name = pmr_fm_b add = var:pmr_fm_ao }} }}\n'
                  f'\t\telse = {{ change_variable = {{ name = pmr_fm_b add = {fmt(ou * SHARE_STEPS)} }} }}\n')
        return s

    def apply(var, mod):
        # remove, then add, only when the size moved (Performance review 2: every change dirties the building). The
        # removal is asked of the building itself, so a size the state lost (a building gone and back) can't stack two.
        return (f'\tif = {{ limit = {{ NOT = {{ has_variable = {var} }} }} {setv(var, 0)} }}\n'
                f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:{var} = var:pmr_fm_x }} }}\n'
                f'\t\tb:{bk} = {{ if = {{ limit = {{ has_modifier = {mod} }} remove_modifier = {mod} }} }}\n'
                '\t\tif = {\n\t\t\tlimit = { var:pmr_fm_x > 0 }\n'
                '\t\t\tset_local_variable = { name = pmr_fm_lx value = var:pmr_fm_x }\n'
                f'\t\t\tb:{bk} = {{ add_modifier = {{ name = {mod} multiplier = local_var:pmr_fm_lx }} }}\n\t\t}}\n'
                f'\t\t{setv(var, "var:pmr_fm_x")}\n\t\t{setv("pmr_fm_ch", 1)}\n\t}}\n')

    o.append('\t# sizes, applied only when they move (remove, then add)\n')
    for side, names, kind, pre in ((0, gin, 'in', 'pmr_lxi'), (1, gout, 'out', 'pmr_lxo'), (2, pops, 'job', 'pmr_lj')):
        for name in names:
            o.append(f'\t# {kind} {name}\n\t{setv("pmr_fm_x", 0)}\n'
                     '\tif = {\n\t\tlimit = { var:pmr_fm_pure = 0 }\n' + size(side, name)
                     + '\t\tif = {\n\t\t\tlimit = { var:pmr_fm_b > 0 }\n'
                     '\t\t\tset_variable = { name = pmr_fm_x value = { value = var:pmr_fm_a divide = var:pmr_fm_b '
                     f'multiply = -{SHARE_STEPS} add = {SHARE_STEPS} min = 0 max = {SHARE_STEPS} }} }}\n'
                     '\t\t\tround_variable = { name = pmr_fm_x nearest = 1 }\n'
                     f'\t\t\tchange_variable = {{ name = pmr_fm_x multiply = {fmt(1 / SHARE_STEPS)} }}\n'
                     '\t\t}\n\t}\n' + apply(f'{pre}_{name}_{b}', less_name(kind, name)))

    # SHORT (PLAN.md 8.6): a union frame with an input it carries at nothing; the tick asks the building for a shortage
    o.append(f'\tif = {{ limit = {{ has_variable = {v("pmr_fz")} }} remove_variable = {v("pmr_fz")} }}\n')
    if gin:
        o.append(f'\tif = {{\n\t\tlimit = {{ var:pmr_fm_pure = 0 OR = {{ '
                 + ' '.join(f'var:{v(f"pmr_lxi_{g}")} = 1' for g in gin) + ' } }\n'
                 f'\t\tset_variable = {v("pmr_fz")}\n\t}}\n')
    if log:
        f = lambda name, d=0: f"[THIS.Var('{name}').GetValue|{d}]"   # noqa: E731
        sizes = ','.join([f'in_{g}:{f(f"pmr_lxi_{g}_{b}", 2)}' for g in gin] + [f'out_{g}:{f(f"pmr_lxo_{g}_{b}", 2)}' for g in gout]
                         + [f'job_{p}:{f(f"pmr_lj_{p}_{b}", 2)}' for p in pops])
        line = (f'PMR;rec=FRAME;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
                f'state=[THIS.GetState.GetNameNoFormatting];building={bk};pair={f("pmr_fm_pair")};pure={f("pmr_fm_pr")}'
                + (';opt=' + '/'.join(f'{f(f"pmr_fm_o{og.gi}")}:{f(f"pmr_fm_po{og.gi}")}' for og in bld.option_groups)
                   if bld.option_groups else '')
                + f';x={sizes}')
        o.append(f'\tif = {{ limit = {{ var:pmr_fm_ch = 1 owner = {{ is_player = yes }} }} debug_log = "{line}" }}\n')
    o.append(f'\tset_variable = {v("pmr_fok")}\n}}\n')
    return ''.join(o)


def short_check(bld):
    """State scope, the tick, monthly in a player's state: a union frame with an input at nothing (pmr_fz_<b>) and the
    building's goods shortage. short=1 means an input the frame carries at 0 still counts as missing."""
    bk, b = bld.bk, bld.b
    head = (f'PMR;rec=SHORT;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={bk};zeroed='
            + ','.join(f"{g}:[THIS.Var('pmr_lxi_{g}_{b}').GetValue|2]" for g in frame_goods(bld)[0]))
    return (f'\tif = {{\n\t\tlimit = {{ has_variable = pmr_month has_variable = pmr_fz_{b} owner = {{ is_player = yes }} }}\n'
            f'\t\tif = {{ limit = {{ b:{bk} = {{ building_has_goods_shortage = yes }} }} debug_log = "{head};short=1" }}\n'
            f'\t\telse = {{ debug_log = "{head};short=0" }}\n\t}}\n')
