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
the modifier type definitions they need. The job modifiers are off (JOB_LESS): they moved no jobs in q99's run.

Jobs (q100's probe; Pat 2026-11-10 22:01Z, "Switch at halfway"): a method's own job lines are all that moves a
building's jobs, so a union frame comes in versions (union_versions, option_versions) and pmr_frame_<b> runs the one
nearest the blend: a recipe union's laborers a level in steps of JOB_STEP from its target's own, its other pop types
those of its target (they move in one go when the larger share changes hands); an option union's pop types each in a
few steps between the least and the most its options give. Test builds log a JOBS line a month for each of a player's
blended buildings (jobs_check_files).

Treatment (the working-conditions shares, pm_pmr_x_<b>_<j>_<n>) stays share methods for now: its goods and jobs are
"live" amounts here, counted in both the blend (A) and the frames (B), so a "less" modifier on the same good leaves them
whole. With TREAT_MOD (rules review item F) they are modifiers instead (treat_sizes).

The AI's lock (LOCK_PURE): a pure frame other than its group's first unlocks only while it runs, as the union frames do,
so the AI finds nothing to switch a building to, and PMR asks what the frame needs itself (GATES).
"""

import collections
import math

SHARE_STEPS = 100
GENERIC_ICON = 'gfx/interface/icons/generic_icons/mixed_icon_base.dds'
LESS_ICON = GENERIC_ICON
SECTIONS = ('building_modifiers', 'state_modifiers', 'country_modifiers')
LOOKUP_FROM = 7      # as generate.py: a ladder this long becomes a binary search
EPS = 1e-9
# The cut lines' name, which the GUI also hides them by (generate.py LESS_SHOWN). q102: a pure mill's trade-off cuts
# read "Retooling" in the Modifier Entries tooltips (Pat's screenshot 2026-11-11 15:50Z); "Method mix" from q103, Title
# Case from q104 (interface review K2). One name for every good: the GUI can only hide by an exact name, so the review's
# per-good "Method Mix: <good>" (T12) would put the timed modifiers back on the tab.
LESS_NAME = 'Method Mix'
# q99's run (Pat, 2026-11-10): building_employment_<pop>_mult on a building's own modifier reads back and shows on the
# Modifiers tab ("Shopkeepers Per Level -60%") but moves no jobs: the Midlands furniture manufactory kept the union's
# 30.0K capacity with its shopkeepers cut 43%, and the probe wharf every laborer at -50%. A blend holds its union's jobs
# either way, so until a route that moves jobs is found (frame_probe.py, q100) the job modifiers are neither made nor
# applied: each was an icon, a Modifiers tab row and a line that did nothing, sized every time the frame ran.
# q100 (frame_probe.py, Pat's year 2026-11-10): the same on a second wharf with its method switched away and back, a
# negative building_employment_<pop>_add sized by level, +50%, and building_group_<g>_employee_mult on the building all
# read back and moved no jobs. Only that group multiplier on the STATE did (12,000 laborers to 6,000 in a month), one
# figure for every pop type of every building of the group there, so it cannot trade laborers for machinists. The
# frames carry their jobs themselves instead (JOB_STEP below); JOB_LESS stays off, its sizes would be measured against
# jobs the union frames no longer hold.
JOB_LESS = False
OPTION_UNION_NAME = 'Trade-off'
# Job versions of the union frames (Pat 2026-11-10 22:01Z, "Switch at halfway": laborers in steps, the other pop types
# in one go at the halfway point, over those in three stages too or a jobs group of their own). A recipe union of
# target p: JOB_POP a level in steps of JOB_STEP (JOB_STEP_SMALL on a type whose targets all hold under JOB_SMALL_BELOW
# of them: port, railway, power plant) from the target's own figure, down to halfway to the target with the fewest and
# up to halfway to the one with the most; past halfway the blend's larger share is another target's and its union
# runs. An option union: each of its job axes (option_job_axes) in steps of about OPT_JOB_STEP, OPT_JOB_POINTS points
# at most and OPT_JOB_FEW on a short one, OPT_JOB_MAX versions a group at most.
JOB_POP = 'laborers'
JOB_STEP = 250
JOB_STEP_SMALL = 50
JOB_SMALL_BELOW = 2000
# The longest production method group any build has run holds 101 methods: the plantations' Treatment ladders
# (pmg_pmr_x_<b>_<n>, a share method a percent), in the release too. Nothing says how many the game takes, so a recipe
# group stays at that: where the versions at JOB_STEP would take it over JOB_GROUP_MAX, the building takes the first
# wider step of JOB_STEP_UP that fits (job_step). One and a half is there because farms, ranches and logging camps
# space their automation levels 750 apart, so 375 lands on them. The JOBS line names the place of the frame a
# building runs.
JOB_GROUP_MAX = 101
JOB_STEP_UP = (1, 1.5, 2, 3, 4, 6, 8, 12, 16)
# Pat 2026-11-10 22:56Z ("no way to more intelligently blend these into our existing frames and automation PMs,
# combining and condensing"): the targets of one recipe that differ in JOB_POP alone, its automation levels, share the
# versions of their unions (job_sets). In all 48 types such targets differ in nothing else but pollution. A version
# belongs to the target whose own figure is nearest (version_owner), so the versions of two automation levels never
# overlap: 2,137 recipe unions where each target's own versions made 4,744, and with JOB_GROUP_MAX at 101 no recipe
# group longer than 100 methods where the longest held 232. Off, every target keeps versions of its own, as q102
# built them.
JOB_SHARE = True
OPT_JOB_STEP = 250
OPT_JOB_POINTS = 5
OPT_JOB_FEW = 3
OPT_JOB_MAX = 27
OCC_BANDS = (1.5, 1.2, 1.05, 1.0, 0.98, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5, 0.4, 0.3, 0.2, 0.1)
# Pat 2026-11-10 21:31Z ("implement this", on the q99 review's "locking the AI out of method swaps"): in q99 and q100 the
# AI switched a building to another pure frame 194 to 276 times a month all year (the UNDO line), and each switch was
# two method changes and a whole pmr_tick_<b> to put it back. With LOCK_PURE every pure frame but the first of its
# group carries unlocking_production_methods = { itself }, like the union frames and the share methods before them
# (1.14.5 and 1.15 ask it of the player's command, the AI's switch and can_activate_production_method alike;
# activate_production_method asks nothing, so the tick still sets any frame). The first method of a group stays as
# vanilla has it: a building that runs nothing yet has no self-locked method available, and the game left such a group
# empty in every new and every history building (q52-q61). So the AI can still step a building down to that first
# method, and nothing else.
# A locked frame fails can_activate_production_method whenever it is not running, so what vanilla's unlock keys ask is
# asked by PMR (Gate), from the keys themselves. A frame with a key Gate does not know stays unlocked and keeps the
# game's own check. False gives q100's methods and checks back unchanged.
LOCK_PURE = True
GATES = {}   # {(building key, method key): Gate} of the locked frames; generate.py fills it before any effect is built
# Rules review item F, Treatment ladders as modifiers (Pat 2026-11-12 14:29Z, rules-review/HANDOFF.md F): with
# TREAT_MOD (generate.py --treat-mod) a Treatment option's lines leave its share methods for modifiers pmr_frame_<b>
# sizes by the share: its unscaled building lines at 100% in pmr_treat_<b>_<j> (size = share), its output as
# goods_output_<good>_mult in pmr_treat_out_<b>_<good> (an _add is ignored on a building modifier: size = the options'
# output a level at their shares / B, what the running frames carry a level, the B of the "less" sizes), its state
# lines in pmr_treat_slave_<b> on the state (size = share). Its goods leave A and B, as no method adds them any more.
# Job lines stay share methods (generate.py treat_jobs): no modifier moves jobs (q99, q100).
TREAT_MOD = False
TREAT_COUNT = False   # test builds with TREAT_MOD (generate.py): the month's TREAT_MOVES line counts the re-sizes

# Automation on rails (fundamentals review, automation/SPEC.md v4, sections 3.3 and 3.4; Pat 2026-11-12 13:40Z "Shared
# laborers method", 14:29Z go; generate.py RAILS). A step type's automation is no axis of its targets: each rung is a
# step member with no target (Member.pairs empty), its share the levels working on it (pmr_n_<j>_<b>). Its goods ride
# the union frames at the most any rung of the track asks, cut by the "less" modifiers; its laborers are one method of
# the shared group pmg_pmr_laborers, which pmr_frame_<b> switches to the one nearest the blend's laborers a level less
# the frame's own, in steps of LAB_GRAIN from LAB_DOWN fewer to LAB_UP more. The union frames of a step type come in
# no job versions; a type whose steps move a skilled post (Building.skilled) has one more union a target,
# pm_pmr_union_<b>_<p>_s, run while more than half the levels work on such a rung.
LAB_GROUP = 'pmg_pmr_laborers'
LAB_GRAIN = 125
LAB_DOWN = 48     # 6,000 fewer
LAB_UP = 12       # 1,500 more
# Rules review item G, one frame a recipe (Pat 2026-11-12 14:29Z, rules-review/HANDOFF.md G; generate.py --one-frame):
# on a step type with no processing axis the vanilla recipe method carries its union frame's lines and is the frame
# in every blend (Building.one_frame), so pm_pmr_union_<b>_<p> goes; the skilled-post unions (_s) stay, and so do the
# processing types' pairs and unions. Its "less" modifiers then apply from a building's first tick, at rest too.
ONE_FRAME = False


def lab_key(n):
    """the shared laborers method n x LAB_GRAIN a level (n < 0 fewer)"""
    return 'pm_pmr_lab_0' if n == 0 else f'pm_pmr_lab_{"m" if n < 0 else "p"}{abs(n) * LAB_GRAIN}'


def lab_methods(texture):
    """(group text, methods text, loc lines) of pmg_pmr_laborers: none first (the game's default, open to all, as a
    group's first method must be), then each amount, which unlocks only while it runs"""
    ns = [0] + list(range(-1, -LAB_DOWN - 1, -1)) + list(range(1, LAB_UP + 1))
    group = (f'{LAB_GROUP} = {{\n\ttexture = "{texture}"\n\tproduction_methods = {{\n'
             + ''.join(f'\t\t{lab_key(n)}\n' for n in ns) + '\t}\n}\n')
    methods = ''.join(f'{lab_key(n)} = {{\n\ttexture = "{texture}"\n'
                      + ('' if n == 0 else f'\tunlocking_production_methods = {{ {lab_key(n)} }}\n'
                         '\tbuilding_modifiers = {\n\t\tlevel_scaled = {\n'
                         f'\t\t\tbuilding_employment_{JOB_POP}_add = {n * LAB_GRAIN}\n\t\t}}\n\t}}\n')
                      + '}\n\n' for n in ns)
    loc = [f' {lab_key(n)}:0 "{n * LAB_GRAIN:+,}"' if n else f' {lab_key(n)}:0 "0"' for n in ns]
    return group, methods, loc


def skilled_key(bld, p):
    return f'pm_pmr_union_{bld.b}_{p}_s'


class Gate:
    """What vanilla's unlock keys ask of one locked frame, as a trigger of PMR's own (state scope).
    techs: every technology the owner needs; owner: other triggers on the owner (laws, its power bloc); state: triggers
    on the state (its region); run: [(building key, [methods], [job versions])], of each entry one method must be
    running (a recipe an option needs, in any frame built on it). Kept as lists until the trigger is asked for, because
    a union frame's job versions (union_versions) are known only once the building's frames are (widen); those are
    asked only of a building on a union frame (pmr_fu_<b>, which pmr_frame_<b> sets with the frame), so a building on
    a pure frame is asked no more than before there were versions."""
    def __init__(self, techs=(), owner=(), state=(), run=()):
        self.techs, self.owner, self.state, self.run = list(techs), list(owner), list(state), list(run)

    def trigger(self, also=()):
        """one trigger; also: more technologies to ask of the owner in the same block"""
        techs = list(dict.fromkeys(list(also) + self.techs))
        own = [f'has_technology_researched = {t}' for t in techs] + self.owner
        parts = ([f'owner = {{ {" ".join(own)} }}'] if own else []) + self.state
        for bk, keys, more in self.run:
            on = [f'is_production_method_active = {{ building_type = {bk} production_method = {x} }}' for x in keys]
            if more:
                vs = [f'is_production_method_active = {{ building_type = {bk} production_method = {x} }}' for x in more]
                on.append(f'AND = {{ has_variable = pmr_fu_{short(bk)} '
                          + (vs[0] if len(vs) == 1 else 'OR = { ' + ' '.join(vs) + ' }') + ' }')
            parts.append(on[0] if len(on) == 1 else 'OR = { ' + ' '.join(on) + ' }')
        if not parts:
            return 'always = yes'
        return parts[0] if len(parts) == 1 else 'AND = { ' + ' '.join(parts) + ' }'

    def widen(self, versions):
        """versions: {a union frame's plain key: its other job versions}. An entry that names the plain key is met by
        any of its versions too."""
        self.run = [(bk, keys, [k for x in keys for k in versions.get(x, [])]) for bk, keys, _ in self.run]


def can_activate(bk, key, also=()):
    """State scope: the game would let the building switch to key. A locked frame: its gate, with the technologies
    also; any other method: the game's own check (also is then the caller's to ask)."""
    gate = GATES.get((bk, key))
    if gate is not None:
        return gate.trigger(also)
    return f'can_activate_production_method = {{ building_type = {bk} production_method = {key} }}'


def may_run(bk, key):
    """State scope: the building may run key. A locked frame: its gate alone, running or not (PMR's gate is then the
    only one that can take a running frame away; the game sees a running locked frame as unlocked by itself). Any
    other method: it runs, or the game would let the building switch to it."""
    if (bk, key) in GATES:
        return GATES[(bk, key)].trigger()
    spec = f'building_type = {bk} production_method = {key}'
    return f'OR = {{ is_production_method_active = {{ {spec} }} can_activate_production_method = {{ {spec} }} }}'


FRAME_DOC = """# Union frames (method-count rework, frames.py): pm_pmr_union_<b>_<p> stands for retool target p while the building's
# levels are blended, each good at the most any combination of its recipes and automation uses, the rest as target p's;
# pm_pmr_union_<b>_x<group> for a trade-off group in a blend. Each unlocks only while it runs, so only the tick
# (pmr_frame_<b>) sets one; the "less" modifiers scale its goods down to the blend.
# Jobs: no modifier moves a building's jobs (q100), so each union comes in versions, <key>_j<n>, that differ in jobs
# alone, and the tick runs the one nearest the blend. A recipe union: laborers a level in steps from target p's own
# (<key>_j<laborers a level>), its other pop types those of target p. An option union: each pop type its options
# move, in a few steps (<key>_j<index>).

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


def lookup_lines(var, ns, body, ind='\t'):
    """lookup for a body of whole lines: body(x, ind) are the lines, at ind, for the x of ns that var holds"""
    def one(x, ind, kw='if'):
        return f'{ind}{kw} = {{\n{ind}\tlimit = {{ {var} = {x} }}\n' + body(x, ind + '\t') + f'{ind}}}\n'
    if len(ns) < LOOKUP_FROM:
        return ''.join(one(x, ind, 'if' if j == 0 else 'else_if') for j, x in enumerate(ns))

    def find(lo, hi, ind):
        if lo == hi:
            return one(ns[lo], ind)
        mid = (lo + hi) // 2
        return (f'{ind}if = {{\n{ind}\tlimit = {{ {var} > {ns[mid]} }}\n' + find(mid + 1, hi, ind + '\t')
                + f'{ind}}}\n{ind}else = {{\n' + find(lo, mid, ind + '\t') + f'{ind}}}\n')
    return find(0, len(ns) - 1, ind)


def half_up(x):
    return int(math.floor(x + 0.5 + EPS))


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
    """A treatment option's share methods (pm_pmr_x_<b>_<j>_<n>): mods x pmr_x_<j>_<b> / SHARE_STEPS run as they are.
    key, tex: its vanilla method and icon (TREAT_MOD names and draws its modifiers by them)."""
    def __init__(self, j, mods, key=None, tex=None):
        self.j, self.mods, self.key, self.tex = j, mods, key, tex


class Building:
    """pair_keys[p - 1]: retool target p (the vanilla recipe key or pm_pmr_pair_<b>_<r>_<a>), in pmr_to order.
    own_mods[key]: modifiers target p's frame carries besides its members' (a recipe's unscaled ones).
    first: the method the game lists first in the recipe group, the one LOCK_PURE leaves open (an option group's is its
    none); test builds count the frames put back from it apart."""
    def __init__(self, bk, recipe_group, pair_keys, members, option_groups=(), own_mods=None, live=(), first=None):
        self.first = first
        self.bk, self.b, self.recipe_group, self.pair_keys = bk, short(bk), recipe_group, list(pair_keys)
        self.members, self.option_groups = list(members), list(option_groups)
        self.own_mods, self.live = own_mods or {}, list(live)
        self.recipes = [m for m in self.members if m.axis == 'recipe']
        self.auto_axes = list(dict.fromkeys(m.axis for m in self.members if m.axis != 'recipe' and m.pairs))
        # rails: the step members (no target), their tracks, and the skilled posts their steps move ({pop: a level},
        # the members that move them); generate.py sets skilled
        self.steps = [m for m in self.members if m.axis != 'recipe' and not m.pairs]
        self.step_axes = list(dict.fromkeys(m.axis for m in self.steps))
        self.skilled, self.skilled_js = {}, []
        self.one_frame = ONE_FRAME and bool(self.steps) and not self.auto_axes
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
            for ax in bld.auto_axes + bld.step_axes:
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
    for m in bld.steps:
        si, so, _sj, _ = split(m.mods)
        gin |= set(nonzero(si)); gout |= set(nonzero(so))
    return sorted(gin), sorted(gout), sorted(pops) if JOB_LESS else []


def union_key(bld, p):
    # ONE_FRAME: the recipe method is its own union frame
    return bld.pair_keys[p - 1] if bld.one_frame else f'pm_pmr_union_{bld.b}_{p}'


def option_union_key(bld, og):
    return f'pm_pmr_union_{bld.b}_x{og.gi}'


def unions_of(bld):
    """{frame key: the union frame standing in for it}"""
    out = {k: union_key(bld, p) for p, k in enumerate(bld.pair_keys, 1)}
    for og in bld.option_groups:
        out.update({k: option_union_key(bld, og) for k in [og.none] + [o.key for o in og.options]})
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Job versions of the union frames

def pair_jobs(bld, p):
    """JOB_POP a level on target p, as its members add up (below 0 where automation takes more than the recipe has)"""
    return pair_amounts(bld, p)[2].get(JOB_POP, 0)


def _job_steps(bld, p, step):
    """(steps down, steps up) from target p's own JOB_POP a level that its union's versions run to: halfway to the
    target with the fewest, and to the one with the most"""
    labs = [pair_jobs(bld, q) for q in range(1, len(bld.pair_keys) + 1)]
    own = max(0, labs[p - 1])
    lo, hi = (max(0, (labs[p - 1] + x) / 2) for x in (min(labs), max(labs)))
    return half_up((own - lo) / step), half_up((hi - own) / step)


def job_sets(bld):
    """{target p: the targets that share their unions' versions with p, p among them}: the targets of p's recipe whose
    jobs differ from p's in JOB_POP alone, so a recipe's automation levels as a rule. In all 48 types such targets
    differ in nothing else but state_pollution_generation_add. With JOB_SHARE off every target stands alone."""
    if getattr(bld, '_job_sets', None) is None:
        sets = {}
        for p in range(1, len(bld.pair_keys) + 1):
            other = tuple(sorted((k, x) for k, x in nonneg(pair_amounts(bld, p)[2]).items() if k != JOB_POP))
            sets.setdefault((bld.pair_recipe(p), other) if JOB_SHARE else p, []).append(p)
        bld._job_sets = {p: ps for ps in sets.values() for p in ps}
    return bld._job_sets


def version_owner(bld, p, lab):
    """The target a version at lab JOB_POP a level belongs to, asked for target p: of the targets p shares versions
    with (job_sets), the one whose own figure is nearest (the first, on a tie). The version is that target's union in
    all but JOB_POP: its name, its icon, its pollution."""
    return min(job_sets(bld)[p], key=lambda q: (abs(max(0, pair_jobs(bld, q)) - lab), q))


def _versions(bld, p, step):
    down, up = _job_steps(bld, p, step)
    own, out = max(0, pair_jobs(bld, p)), []
    for n in range(-down, up + 1):
        lab = max(0, own + n * step)
        o = p if n == 0 else version_owner(bld, p, lab)
        uk = union_key(bld, o)
        out.append((n, uk if abs(lab - max(0, pair_jobs(bld, o))) < EPS else f'{uk}_j{fmt(lab)}', lab))
    return out


def _frames_at(bld, step):
    """{key: (owner target, JOB_POP a level)} at this step: a plain union a target, then the versions, by owner and
    size, each once however many targets use it"""
    pairs = range(1, len(bld.pair_keys) + 1)
    out = collections.OrderedDict((union_key(bld, p), (p, max(0, pair_jobs(bld, p)))) for p in pairs)
    extra = {}
    for p in pairs:
        for n, k, lab in _versions(bld, p, step):
            if k not in out:
                extra[k] = (version_owner(bld, p, lab), lab)
    for k in sorted(extra, key=lambda k: extra[k]):
        out[k] = extra[k]
    return out


def job_step(bld):
    """JOB_POP a level between two versions of the building's recipe unions: JOB_STEP (JOB_STEP_SMALL on a small
    type), or the first of its JOB_STEP_UP multiples at which the recipe group holds JOB_GROUP_MAX methods at most
    (its pure frames and its union frames)."""
    if getattr(bld, '_job_step', None) is None:
        pairs = range(1, len(bld.pair_keys) + 1)
        base = JOB_STEP if max(pair_jobs(bld, p) for p in pairs) >= JOB_SMALL_BELOW else JOB_STEP_SMALL
        fits = [base * k for k in JOB_STEP_UP
                if len(bld.pair_keys) + len(_frames_at(bld, base * k)) <= JOB_GROUP_MAX]
        if not fits:
            raise SystemExit(f'{bld.bk}: no step in JOB_STEP_UP keeps its recipe group at {JOB_GROUP_MAX} methods')
        bld._job_step = fits[0]
    return bld._job_step


def union_frames(bld):
    """{key: (owner target, JOB_POP a level)} every recipe union frame of the building: a plain union a target, then
    the job versions by owner and size"""
    if getattr(bld, '_union_frames', None) is None:
        if bld.steps:   # rails: no job versions; a skilled-post type's _s union a target besides
            pairs = range(1, len(bld.pair_keys) + 1)
            out = collections.OrderedDict((union_key(bld, p), (p, max(0, pair_jobs(bld, p)))) for p in pairs)
            if bld.skilled:
                out.update((skilled_key(bld, p), (p, max(0, pair_jobs(bld, p)))) for p in pairs)
            bld._union_frames = out
        else:
            bld._union_frames = _frames_at(bld, job_step(bld))
    return bld._union_frames


def union_versions(bld, p):
    """[(n, key, JOB_POP a level)] the frames target p's union runs as, fewest first: the target's own figure plus
    n x job_step(bld) (never below 0), n from halfway to the target with the fewest to halfway to the one with the
    most. The target's own (n = 0) is its plain union (union_key). The others are versions, <a plain key>_j<JOB_POP a
    level>, shared between the targets of one recipe that differ in JOB_POP alone (job_sets): each belongs to the
    target of the set whose own figure is nearest (version_owner) and is that target's plain union where it is the
    figure itself. So a recipe's automation levels overlap in no frame, and a blend reads as the automation level its
    laborers are nearest."""
    if bld.steps:
        return [(0, union_key(bld, p), max(0, pair_jobs(bld, p)))]
    return _versions(bld, p, job_step(bld))


def union_places(bld):
    """{union key: about its place in the recipe group's list}: the pure frames, then a plain union a target, then the
    versions by owner and size, as generate.py lists them (about: the group can list a method or two that is no
    target). For the JOBS line."""
    P = len(bld.pair_keys)
    return {k: P + i for i, k in enumerate(union_frames(bld), 1)}


def option_job_axes(og):
    """The option group's jobs as axes: [{'lead': pop, 'tied': {pop: ratio to the lead}, 'none': the lead's amount on
    the none, 'vec': its change per option (og.options order), 'lo', 'hi': its least and most over the none and the
    options, 'n': points}]. Pop types whose changes are in one proportion over every option share an axis (rayon's
    laborers go as its machinists come; a distillery's shopkeepers with its machinists), so no version is made that no
    blend reaches."""
    full = [option_full(og, o)[2] for o in [None] + og.options]
    pops = sorted({k for f in full for k in f})
    vec = {k: [f.get(k, 0) - full[0].get(k, 0) for f in full[1:]] for k in pops}
    span = {k: max([0] + vec[k]) - min([0] + vec[k]) for k in pops}
    axes = []
    # the widest first, one that rises before one that falls: it leads its axis, and point 0 is its least
    for k in sorted((k for k in pops if span[k] > EPS), key=lambda k: (-span[k], max(vec[k]) <= EPS, k)):
        for ax in axes:
            lead = vec[ax['lead']]
            i = next(i for i, x in enumerate(lead) if abs(x) > EPS)
            c = vec[k][i] / lead[i]
            if all(abs(x - c * y) < EPS for x, y in zip(vec[k], lead)):
                ax['tied'][k] = c
                break
        else:
            none = full[0].get(k, 0)
            lo, hi = none + min([0] + vec[k]), none + max([0] + vec[k])
            n = OPT_JOB_FEW if hi - lo < 2 * OPT_JOB_STEP else min(OPT_JOB_POINTS, 1 + half_up((hi - lo) / OPT_JOB_STEP))
            axes.append({'lead': k, 'tied': {k: 1}, 'none': none, 'vec': vec[k], 'lo': lo, 'hi': hi, 'n': n})
    while axes and math.prod(ax['n'] for ax in axes) > OPT_JOB_MAX:
        ax = max(axes, key=lambda ax: ax['n'])
        if ax['n'] <= 2:
            raise SystemExit(f'{og.key}: {len(axes)} job axes, over {OPT_JOB_MAX} versions at two points each')
        ax['n'] -= 1
    return axes


def option_versions(bld, og):
    """[(index, key, {pop: jobs a level})] the versions of the group's union frame: every combination of its axes'
    points, the first axis counting fastest. Index 0 (each axis at its least) keeps the plain key (option_union_key),
    the others are <key>_j<index>. A pop type the options leave alone keeps the none's."""
    axes = option_job_axes(og)
    none = option_full(og, None)[2]
    uk = option_union_key(bld, og)
    out = []
    for idx in range(math.prod(ax['n'] for ax in axes)):
        jobs, rest = dict(none), idx
        for ax in axes:
            i, rest = rest % ax['n'], rest // ax['n']
            lead = ax['lo'] + i * (ax['hi'] - ax['lo']) / (ax['n'] - 1)
            for pop, c in ax['tied'].items():
                jobs[pop] = none.get(pop, 0) + c * (lead - ax['none'])
        out.append((idx, uk if idx == 0 else f'{uk}_j{idx}', jobs))
    return out


def widen_gates(bld):
    """The AI's lock: a gate that asks for a recipe in any frame built on it names the plain union keys (generate.py
    builds the gates before the frames); the job versions of those unions meet it too. Call once bld is built and
    before any of its effects are."""
    versions = {union_key(bld, p): ks for p, ks in extra_union_keys(bld)[0].items()}
    for (bk, _key), gate in GATES.items():
        if bk == bld.bk:
            gate.widen(versions)


def extra_union_keys(bld):
    """({target p: [keys]}, {option group key: [keys]}): the versions beyond the plain union keys, which generate.py
    lists wherever it lists a plain one (the groups, the methods a recipe unlocks, vanilla's checks on a recipe). A
    version is listed once, under the target it belongs to (version_owner)."""
    plain = {union_key(bld, p) for p in range(1, len(bld.pair_keys) + 1)}
    return ({p: [k for k, (o, _) in union_frames(bld).items() if o == p and k not in plain]
             for p in range(1, len(bld.pair_keys) + 1)},
            {og.key: [k for _, k, _ in option_versions(bld, og) if k != option_union_key(bld, og)]
             for og in bld.option_groups})


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
    """{union key: definition}: the recipe unions, then each option group's, every job version of each. texture(key):
    a frame's icon. Each union unlocks only while it runs, so neither the AI nor the player can pick one; the tick sets
    it. Goods are the union's in every version (the "less" modifiers take them down to the blend); jobs are the
    version's own, an option union's below 0 where an option's are (rayon's laborers), as vanilla writes them. A recipe
    union is the target's it belongs to (union_frames) in everything else."""
    out = collections.OrderedDict()
    for uk, (p, lab) in union_frames(bld).items():
        if uk == bld.pair_keys[p - 1]:   # ONE_FRAME: the recipe method itself carries it (one_frame_body)
            continue
        out[uk] = (f'{uk} = {{\n\ttexture = "{texture(bld.pair_keys[p - 1])}"\n\tunlocking_production_methods = {{ {uk} }}\n'
                   + union_body(bld, uk, p, lab) + '}\n')
    for og in bld.option_groups:
        ui2, uo2, _ = option_union(og)
        _, _, _, nrest = option_full(og, None)
        for _, uk, jobs in option_versions(bld, og):
            out[uk] = (f'{uk} = {{\n\ttexture = "{texture(og.none)}"\n\tunlocking_production_methods = {{ {uk} }}\n'
                       + sections(join(ui2, uo2, nonzero(jobs), nrest)) + '}\n')
    return out


def union_body(bld, uk, p, lab):
    """the modifier blocks of recipe union uk (target p, JOB_POP a level lab)"""
    ui, uo, _ = recipe_union(bld)
    _, _, pj, rest = pair_amounts(bld, p)
    jobs = {**pj, JOB_POP: lab}
    if bld.steps and uk == skilled_key(bld, p):
        jobs = {k: jobs.get(k, 0) + bld.skilled.get(k, 0) for k in [*jobs, *(k for k in bld.skilled if k not in jobs)]}
    return sections(join(ui, uo, nonneg(jobs), rest))


def one_frame_body(bld, p):
    """ONE_FRAME: the body of target p's recipe method, its union frame's"""
    return union_body(bld, union_key(bld, p), p, union_frames(bld)[union_key(bld, p)][1])


def frame_loc(bld):
    """English names of the new methods: a union frame reads as the target it belongs to, in every job version"""
    return ([f' {uk}:0 "${bld.pair_keys[p - 1]}$"' for uk, (p, _) in union_frames(bld).items() if uk != bld.pair_keys[p - 1]]
            + [f' {uk}:0 "{OPTION_UNION_NAME}"' for og in bld.option_groups for _, uk, _ in option_versions(bld, og)])


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
# Treatment as modifiers (TREAT_MOD)

TREAT_DOC = """# Treatment as modifiers (rules review item F, frames.py TREAT_MOD): pmr_frame_<b> puts each on a plantation with a
# multiplier, removing and re-adding it only when its size moves. pmr_treat_<b>_<j>: option j's unscaled lines at 100%,
# sized by its share. pmr_treat_out_<b>_<good>: the options' output of the good a level at their shares over what the
# running frames carry a level, in steps of 0.01. pmr_treat_slave_<b>, on the state: the option's state lines at 100%,
# sized by its share.

"""


def treat_split(lv):
    """a Treatment option's lines at 100%: (unscaled building lines, output a level by good, state lines, job lines)"""
    unscaled, out, state, jobs = {}, {}, {}, {}
    for (sec, sub), d in lv.mods.items():
        for k, x in d.items():
            if abs(x) < EPS:
                continue
            if (sec, sub) == ('building_modifiers', 'unscaled'):
                unscaled[k] = x
            elif (sec, sub) == ('building_modifiers', 'workforce_scaled') and k.startswith('goods_output_') and k.endswith('_add'):
                out[k[13:-4]] = x
            elif (sec, sub) == ('state_modifiers', 'unscaled'):
                state[k] = x
            elif (sec, sub) == ('building_modifiers', 'level_scaled') and k.startswith('building_employment_') and k.endswith('_add'):
                jobs[k] = x
            else:
                raise SystemExit(f'TREAT_MOD: {lv.key} has {sec}.{sub}.{k}, which no Treatment modifier carries; extend it')
    return unscaled, out, state, jobs


def treat_plan(bld):
    """([(j, vanilla key, unscaled lines)], {good: [(j, output a level at 100%)]}, (j, key, icon, state lines) or None)"""
    opts, goods, state = [], {}, None
    for lv in bld.live:
        un, out, st, _ = treat_split(lv)
        if un:
            opts.append((lv.j, lv.key, un))
        for g, x in out.items():
            goods.setdefault(g, []).append((lv.j, x))
        if st:
            if state:
                raise SystemExit(f'TREAT_MOD: {bld.bk} has state lines on two options; pmr_treat_slave_<b> is one a type')
            state = (lv.j, lv.key, lv.tex, st)
    return opts, dict(sorted(goods.items())), state


def treat_name(bld, j):
    return f'pmr_treat_{bld.b}_{j}'


def treat_out_name(bld, g):
    return f'pmr_treat_out_{bld.b}_{g}'


def treat_slave_name(bld):
    return f'pmr_treat_slave_{bld.b}'


def treat_vars(bld):
    """the sizes applied: pmr_tx_<j>_<b>, pmr_txo_<good>_<b>, pmr_txs_<b>"""
    opts, goods, state = treat_plan(bld)
    return ([f'pmr_tx_{j}_{bld.b}' for j, _, _ in opts] + [f'pmr_txo_{g}_{bld.b}' for g in goods]
            + ([f'pmr_txs_{bld.b}'] if state else []))


def treat_static_modifiers(blds):
    out = []
    for bld in blds:
        opts, goods, state = treat_plan(bld)
        for j, _, un in opts:
            out.append(f'{treat_name(bld, j)} = {{\n\ticon = "{LESS_ICON}"\n'
                       + ''.join(f'\t{k} = {fmt(x)}\n' for k, x in un.items()) + '}\n\n')
        for g in goods:
            out.append(f'{treat_out_name(bld, g)} = {{\n\ticon = "{LESS_ICON}"\n\tgoods_output_{g}_mult = 1\n}}\n\n')
        if state:
            _, _, tex, st = state
            out.append(f'{treat_slave_name(bld)} = {{\n\ticon = "{tex}"\n'
                       + ''.join(f'\t{k} = {fmt(x)}\n' for k, x in st.items()) + '}\n\n')
    return ''.join(out)


def treat_loc(blds):
    """The building's ones are LESS_NAME, so the lists that leave the "less" modifiers out leave them out too; the
    state's is its option's vanilla name"""
    out = []
    for bld in blds:
        opts, goods, state = treat_plan(bld)
        out += [f' {treat_name(bld, j)}:0 "{LESS_NAME}"' for j, _, _ in opts]
        out += [f' {treat_out_name(bld, g)}:0 "{LESS_NAME}"' for g in goods]
        if state:
            out.append(f' {treat_slave_name(bld)}:0 "${state[1]}$"')
    return out


def treat_log(bld, ind='\t'):
    """State scope, test builds: the TREAT line, the logged country's (pmr_logged), once a year a building (pmr_trl_<b>, 350 days, so a building updated
    every other month logs every sixth update): each option's share and each modifier's size in force (both set at the
    building's last update, pmr_opts_<b> then pmr_frame_<b>), and the lines as the game reads them back, the building's
    and the state's totals from every source (-99: a read the engine refused)."""
    bk, b = bld.bk, bld.b
    opts, goods, state = treat_plan(bld)
    keys = list(dict.fromkeys([k for _, _, un in opts for k in un] + [f'goods_output_{g}_mult' for g in goods]))
    skeys = list(state[3]) if state else []
    f = lambda name, d=0: f"[THIS.Var('{name}').GetValue|{d}]"   # noqa: E731
    reads = (''.join(f'{ind}\tset_variable = {{ name = pmr_trd_{i} value = -99 }}\n'
                     f'{ind}\tset_variable = {{ name = pmr_trd_{i} value = b:{bk}.modifier:{k} }}\n' for i, k in enumerate(keys))
             + ''.join(f'{ind}\tset_variable = {{ name = pmr_trs_{i} value = -99 }}\n'
                       f'{ind}\tset_variable = {{ name = pmr_trs_{i} value = modifier:{k} }}\n' for i, k in enumerate(skeys)))
    line = ('PMR;rec=TREAT;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={bk};level=[THIS.Var(\'pmr_level_{b}\').GetValue|0]'
            + ';x=' + '/'.join(f(f'pmr_x_{lv.j}_{b}') for lv in bld.live)
            + ';size=' + ','.join([f'{j}:{f(f"pmr_tx_{j}_{b}", 2)}' for j, _, _ in opts]
                                  + [f'out_{g}:{f(f"pmr_txo_{g}_{b}", 2)}' for g in goods]
                                  + ([f'slave:{f(f"pmr_txs_{b}", 2)}'] if state else []))
            + ';read=' + ','.join([f'{k}:{f(f"pmr_trd_{i}", 3)}' for i, k in enumerate(keys)]
                                  + [f'{k}:{f(f"pmr_trs_{i}", 3)}' for i, k in enumerate(skeys)]))
    # q115 (perf review 16): the logged country's only; TREAT_MOVES counts the world's re-sizes
    return (f'{ind}if = {{\n{ind}\tlimit = {{ has_variable = pmr_xinit_{b} NOT = {{ has_variable = pmr_trl_{b} }} owner = {{ pmr_logged = yes }} }}\n'
            f'{ind}\tset_variable = {{ name = pmr_trl_{b} value = yes days = 350 }}\n' + reads
            + f'{ind}\tdebug_log = "{line}"\n'
            + ''.join(f'{ind}\tremove_variable = pmr_trd_{i}\n' for i in range(len(keys)))
            + ''.join(f'{ind}\tremove_variable = pmr_trs_{i}\n' for i in range(len(skeys))) + f'{ind}}}\n')


# ---------------------------------------------------------------------------------------------------------------------
# The effect

def state_vars(bld):
    """the per-building state variables pmr_frame_<b> keeps: the sizes applied, which must go with the building (a new
    one has no modifiers), its flags, the flag of a building on a union frame (pmr_fu_<b>; the AI's lock asks it too,
    Gate), and for the JOBS line the JOB_POP a level its recipe frame holds and its place (pmr_fq_<b>, pmr_fpl_<b>)"""
    gin, gout, pops = frame_goods(bld)
    return ([f'pmr_lxi_{g}_{bld.b}' for g in gin] + [f'pmr_lxo_{g}_{bld.b}' for g in gout]
            + [f'pmr_lj_{p}_{bld.b}' for p in pops]
            + [f'pmr_fz_{bld.b}', f'pmr_fok_{bld.b}', f'pmr_fu_{bld.b}', f'pmr_fq_{bld.b}', f'pmr_fpl_{bld.b}']
            + (treat_vars(bld) if TREAT_MOD else [])
            + ([f'pmr_lbm_{bld.b}'] if bld.steps else []) + ([f'pmr_fsk_{bld.b}'] if bld.skilled else []))


def clear_vars(bld, ind='\t'):
    """TREAT_MOD: the state's own Treatment modifier goes with its size (a building gone, seen again or new)"""
    slave = treat_slave_name(bld) if TREAT_MOD and treat_plan(bld)[2] else None
    return (''.join(f'{ind}if = {{ limit = {{ has_variable = {n} }} remove_variable = {n} }}\n' for n in state_vars(bld))
            + (f'{ind}if = {{ limit = {{ has_modifier = {slave} }} remove_modifier = {slave} }}\n' if slave else ''))


def treat_sizes(bld, size, xs, setv):
    """TREAT_MOD, inside pmr_frame_<b> after the "less" sizes (the frames and pmr_fm_pr / pmr_fm_po<gi> are set):
    each Treatment modifier sized from the shares pmr_x_<j>_<b>, removed and re-added only when its size moved. The
    output's B is size()'s, the "less" sizes' own: the running pure frame's amount a level, or the union's, plus each
    trade-off group's running frame (x SHARE_STEPS)."""
    bk, b = bld.bk, bld.b
    opts, goods, state = treat_plan(bld)

    def put(var, mod, on):
        # on: the building (b:<bk>) or None, the state itself. A size not set (a building gone and back, or seen again)
        # takes a modifier still there off first.
        at = lambda x: f'{on} = {{ {x} }}' if on else x   # noqa: E731
        rm = at(f'if = {{ limit = {{ has_modifier = {mod} }} remove_modifier = {mod} }}')
        # TREAT_COUNT: each re-size, the building's (pmr_trm_b) or the state's (pmr_trm_s), for the TREAT_MOVES line
        g = f'pmr_trm_{"b" if on else "s"}'
        cnt = (f'\t\tif = {{ limit = {{ NOT = {{ has_global_variable = {g} }} }} set_global_variable = {{ name = {g} value = 0 }} }}\n'
               f'\t\tchange_global_variable = {{ name = {g} add = 1 }}\n' if TREAT_COUNT else '')
        return (f'\tif = {{ limit = {{ NOT = {{ has_variable = {var} }} }} {setv(var, 0)} {rm} }}\n'
                f'\tif = {{\n\t\tlimit = {{ NOT = {{ var:{var} = var:pmr_fm_x }} }}\n\t\t{rm}\n' + cnt +
                '\t\tif = {\n\t\t\tlimit = { var:pmr_fm_x > 0 }\n'
                '\t\t\tset_local_variable = { name = pmr_fm_lx value = var:pmr_fm_x }\n'
                f'\t\t\t{at(f"add_modifier = {{ name = {mod} multiplier = local_var:pmr_fm_lx }}")}\n\t\t}}\n'
                f'\t\t{setv(var, "var:pmr_fm_x")}\n\t}}\n')

    share = lambda j: f'set_variable = {{ name = pmr_fm_x value = {{ value = {xs(j)} multiply = {fmt(1 / SHARE_STEPS)} }} }}'   # noqa: E731
    o = ['\t# Treatment as modifiers (TREAT_MOD): each option\'s lines at its share\n']
    for j, key, _ in opts:
        o.append(f'\t# {key}\n\t{share(j)}\n' + put(f'pmr_tx_{j}_{b}', treat_name(bld, j), f'b:{bk}'))
    for g, terms in goods.items():
        held = [j for j, _ in terms]
        o.append(f'\t# output {g}: the options\' a level at their shares over B, in steps of 0.01\n\t{setv("pmr_fm_x", 0)}\n'
                 '\tif = {\n\t\tlimit = { ' + (f'{xs(held[0])} > 0' if len(held) == 1 else
                                               'OR = { ' + ' '.join(f'{xs(j)} > 0' for j in held) + ' }') + ' }\n'
                 + size(1, g)
                 + '\t\tif = {\n\t\t\tlimit = { var:pmr_fm_b > 0 }\n'
                 '\t\t\tset_variable = { name = pmr_fm_x value = { value = 0'
                 + ''.join(f' add = {{ value = {xs(j)} multiply = {fmt(x)} }}' for j, x in terms)
                 + f' divide = var:pmr_fm_b multiply = {SHARE_STEPS} }} }}\n'
                 '\t\t\tround_variable = { name = pmr_fm_x nearest = 1 }\n'
                 f'\t\t\tchange_variable = {{ name = pmr_fm_x multiply = {fmt(1 / SHARE_STEPS)} }}\n'
                 '\t\t}\n\t}\n' + put(f'pmr_txo_{g}_{b}', treat_out_name(bld, g), f'b:{bk}'))
    if state:
        j, key, _, _ = state
        o.append(f'\t# {key}: its state lines, on the state\n\t{share(j)}\n' + put(f'pmr_txs_{b}', treat_slave_name(bld), None))
    return ''.join(o)


def frame_effect(bld, log=True, count=False):
    """pmr_frame_<b>, state scope, after pmr_blend_<b> and pmr_opts_<b> (the shares pmr_n_<j>_<b>, pmr_x_<j>_<b> and
    pmr_xn_<gi>_<b> are set). Call only where b:<bk> exists. count (test builds): each frame put back after a change
    from outside PMR's tick (the AI's, the game's) adds 1 to the UNDO line's count (pmr_count_undo), and 1 to its
    "first" where the building was found on its group's first method (pmr_count_undo_first): the one switch LOCK_PURE
    leaves the AI."""
    bk, b = bld.bk, bld.b
    v = lambda name: f'{name}_{b}'                     # noqa: E731
    n = lambda j: f'var:{v(f"pmr_n_{j}")}'             # noqa: E731
    xs = lambda j: f'var:{v(f"pmr_x_{j}")}'            # noqa: E731
    setv = lambda name, val: f'set_variable = {{ name = {name} value = {val} }}'   # noqa: E731
    spec = lambda key: f'building_type = {bk} production_method = {key}'           # noqa: E731
    on = lambda key: f'is_production_method_active = {{ {spec(key)} }}'           # noqa: E731
    may = lambda key: may_run(bk, key)                # noqa: E731
    def act(key, first=None):
        was = (f'if = {{ limit = {{ {on(first)} }} pmr_count_undo_first = yes }} ' if count and first and first != key else '')
        return (f'if = {{ limit = {{ NOT = {{ {on(key)} }} }} {was}'
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
    if bld.steps:
        # rails: the levels working on a step (pmr_fm_st), and on a step that moves a skilled post (pmr_fm_sk); a
        # building with any step runs its union frame, whose step goods the "less" modifiers cut
        o.append('\t# rails: shares of the levels working on a step\n'
                 '\tset_variable = { name = pmr_fm_st value = { value = 0 '
                 + ' '.join(f'add = {n(m.j)}' for m in bld.steps) + ' } }\n'
                 + ('\tset_variable = { name = pmr_fm_sk value = { value = 0 '
                    + ' '.join(f'add = {n(j)}' for j in bld.skilled_js) + ' } }\n' if bld.skilled else ''))
    o.append(f'\t{setv("pmr_fm_pr", 0)}\n' + ('\t# ONE_FRAME: the recipe method is the union, so the "less" sizes always apply\n'
                                                if bld.one_frame else
             f'\tif = {{ limit = {{ var:pmr_fm_rs = {SHARE_STEPS} '
             + ''.join(f'var:pmr_fm_gs{k} = {SHARE_STEPS} ' for k, _ in axes)
             + ('var:pmr_fm_st = 0 ' if bld.steps else '') + f'}} {setv("pmr_fm_pr", 1)} }}\n'))

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
             + lookup('var:pmr_fm_r', sorted(m.j for m in bld.recipes), pair_of)
             # kept, for the posts a retool brings (generate.py wf_effect, Pat 2026-11-12 17:07Z)
             + f'\t{setv(v("pmr_wfp"), "var:pmr_fm_pair")}\n')

    # 3. the recipe frame: pure only where the building may run it (technology, laws: may_run), else its union; each
    # frame activated only if it isn't running (activate_production_method checks no unlock, and a frame the game
    # can't run would be switched away again, through on_production_method_changed back into this tick)
    # The union comes in job versions (union_versions): the one whose JOB_POP a level is nearest the blend's, among
    # those of the target with the larger share. Test builds, for the JOBS line: pmr_fq_<b>, the JOB_POP a level of
    # the frame set, pure or union, and pmr_fpl_<b>, about its place in the group's list (union_places).
    pairs = list(range(1, P + 1))
    step = JOB_STEP if bld.steps else job_step(bld)
    vers = {p: union_versions(bld, p) for p in pairs}
    fq, place = v('pmr_fq'), union_places(bld)
    fqset = lambda lab, at: f' {setv(fq, fmt(lab))} {setv(v("pmr_fpl"), at)}' if log else ''   # noqa: E731
    jm = [(m.j, split(m.mods)[2].get(JOB_POP, 0)) for m in bld.members]

    def union_pick(p, ind):
        leaf = {q: act(uk, bld.first) + fqset(lab, place[uk]) for q, uk, lab in vers[p]}
        if bld.skilled:   # rails: the _s union while more than half the levels work on a skilled-post step
            sk, uk = skilled_key(bld, p), union_key(bld, p)
            lab = max(0, pair_jobs(bld, p))
            return (f'{ind}if = {{ limit = {{ var:pmr_fm_sk > {SHARE_STEPS // 2} }} {act(sk, bld.first)}{fqset(lab, place[sk])} }}\n'
                    f'{ind}else = {{ {act(uk, bld.first)}{fqset(lab, place[uk])} }}\n')
        if len(leaf) == 1:
            return f'{ind}{next(iter(leaf.values()))}\n'
        # steps from the target's own figure, within its versions
        return (f'{ind}set_variable = {{ name = pmr_fm_qp value = {{ value = var:pmr_fm_q '
                f'subtract = {fmt(max(0, pair_jobs(bld, p)) / step)} min = {min(leaf)} max = {max(leaf)} }} }}\n'
                f'{ind}round_variable = {{ name = pmr_fm_qp nearest = 1 }}\n'
                + lookup('var:pmr_fm_qp', sorted(leaf), lambda q: leaf[q], ind))

    o.append('\tif = {\n\t\tlimit = { var:pmr_fm_pr = 1 }\n'
             + lookup('var:pmr_fm_pair', pairs,
                      lambda p: f'if = {{ limit = {{ NOT = {{ {may(bld.pair_keys[p - 1])} }} }} {setv("pmr_fm_pr", 0)} }}', '\t\t')
             + '\t}\n'
             '\tif = {\n\t\tlimit = { var:pmr_fm_pr = 1 }\n'
             + lookup('var:pmr_fm_pair', pairs,
                      lambda p: act(bld.pair_keys[p - 1], bld.first) + fqset(max(0, pair_jobs(bld, p)), p), '\t\t')
             + '\t}\n\telse = {\n'
             + (f'\t\t# the blend\'s {JOB_POP} a level, counted in steps of {fmt(step)}\n'
                '\t\tset_variable = { name = pmr_fm_q value = { value = 0'
                + ''.join(f' add = {{ value = {n(j)} multiply = {fmt(a / (SHARE_STEPS * step))} }}' for j, a in jm if abs(a) > EPS)
                + ' } }\n'
                if any(len(x) > 1 for x in vers.values()) else '')
             + lookup_lines('var:pmr_fm_pair', pairs, union_pick, '\t\t') + '\t}\n')

    # 4. each trade-off group: the none or option with the largest share; pure where it is at 100% and may run, else
    # its union, in the job version nearest the blend (option_versions): a point on each job axis, pmr_fm_oj<gi> their
    # index (-1 on a pure frame, and where the group's options move no jobs)
    def option_union_pick(og):
        gi, overs = og.gi, option_versions(bld, og)
        if len(overs) == 1:
            return f'\telse = {{ {act(overs[0][1], og.none)} }}\n'
        s, radix = f'\telse = {{\n\t\t{setv(f"pmr_fm_oj{gi}", 0)}\n', 1
        for ax in option_job_axes(og):
            k = (ax['n'] - 1) / (ax['hi'] - ax['lo'])
            s += (f'\t\t# {", ".join(ax["tied"])}: {ax["n"]} points, {fmt(ax["lo"])} to {fmt(ax["hi"])} {ax["lead"]}\n'
                  f'\t\tset_variable = {{ name = pmr_fm_ot value = {{ value = {fmt((ax["none"] - ax["lo"]) * k)}'
                  + ''.join(f' add = {{ value = {xs(x.j)} multiply = {fmt(d * k / SHARE_STEPS)} }}'
                            for x, d in zip(og.options, ax['vec']) if abs(d) > EPS)
                  + f' min = 0 max = {ax["n"] - 1} }} }}\n'
                  '\t\tround_variable = { name = pmr_fm_ot nearest = 1 }\n'
                  f'\t\tset_variable = {{ name = pmr_fm_oj{gi} value = {{ value = var:pmr_fm_oj{gi} '
                  f'add = {{ value = var:pmr_fm_ot multiply = {radix} }} }} }}\n')
            radix *= ax['n']
        return (s + lookup(f'var:pmr_fm_oj{gi}', [i for i, _, _ in overs], lambda i: act(overs[i][1], og.none), '\t\t')
                + '\t}\n')

    for og in bld.option_groups:
        gi = og.gi
        keys = {0: og.none, **{x.j: x.key for x in og.options}}
        o.append(f'\t# {og.key}\n\t{setv(f"pmr_fm_o{gi}", 0)}\n\t{setv(f"pmr_fm_os{gi}", "var:" + v(f"pmr_xn_{gi}"))}\n'
                 f'\t{setv(f"pmr_fm_oj{gi}", -1)}\n'
                 + ''.join(f'\tif = {{ limit = {{ {xs(x.j)} > var:pmr_fm_os{gi} }} {setv(f"pmr_fm_o{gi}", x.j)} '
                           f'{setv(f"pmr_fm_os{gi}", xs(x.j))} }}\n' for x in og.options)
                 + f'\t{setv(f"pmr_fm_po{gi}", 0)}\n'
                 f'\tif = {{\n\t\tlimit = {{ var:pmr_fm_os{gi} = {SHARE_STEPS} }}\n'
                 + lookup(f'var:pmr_fm_o{gi}', sorted(keys),
                          lambda j, keys=keys, gi=gi: f'if = {{ limit = {{ {may(keys[j])} }} {setv(f"pmr_fm_po{gi}", 1)} }}', '\t\t')
                 + '\t}\n'
                 f'\tif = {{\n\t\tlimit = {{ var:pmr_fm_po{gi} = 1 }}\n'
                 + lookup(f'var:pmr_fm_o{gi}', sorted(keys), lambda j, keys=keys, og=og: act(keys[j], og.none), '\t\t')
                 + '\t}\n' + option_union_pick(og))
    o.append(f'\t{setv("pmr_fm_pure", 0)}\n'
             '\tif = { limit = { var:pmr_fm_pr = 1 ' + ''.join(f'var:pmr_fm_po{og.gi} = 1 ' for og in bld.option_groups)
             + f'}} {setv("pmr_fm_pure", 1)} }}\n'
             f'\tif = {{ limit = {{ var:pmr_fm_pure = 0 }} set_variable = {v("pmr_fu")} }}\n'
             f'\telse_if = {{ limit = {{ has_variable = {v("pmr_fu")} }} remove_variable = {v("pmr_fu")} }}\n')

    # 5. sizes: x = 1 - A / B, A the blended amount, B what the running frames carry, in steps of 0.01. A and B are
    # both kept x SHARE_STEPS (share points x amount), so no multiplier is smaller than an amount.
    gin, gout, pops = frame_goods(bld)
    ui, uo, uj = recipe_union(bld)
    unions = {og.gi: option_union(og) for og in bld.option_groups}
    mem = {m.j: split(m.mods) for m in bld.members}
    opt = {og.gi: (option_full(og, None), {x.j: split(x.mods) for x in og.options}) for og in bld.option_groups}
    live = [] if TREAT_MOD else [(lv.j, split(lv.mods)) for lv in bld.live]   # TREAT_MOD: no method adds its goods

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

    if TREAT_MOD and bld.live:
        o.append(treat_sizes(bld, size, xs, setv))
    if bld.steps:
        # rails (SPEC 3.3): the shared laborers method nearest the blend's laborers a level less the frame's own.
        # Wanted = each recipe's share x its laborers less the steps' cut (never below 0), plus the processing members';
        # the cut = each step's share x the laborers it removes. Switched only when it moves (act).
        lab = lambda m: split(m.mods)[2].get(JOB_POP, 0)   # noqa: E731
        cuts = [(m.j, -lab(m)) for m in bld.steps if lab(m) < -EPS]
        procs = [(m.j, lab(m)) for m in bld.members if m.axis in bld.auto_axes and abs(lab(m)) > EPS]
        o.append('\t# rails: the shared laborers method (pmg_pmr_laborers)\n'
                 '\tset_variable = { name = pmr_fm_cut value = { value = 0'
                 + ''.join(f' add = {{ value = {n(j)} multiply = {fmt(c / SHARE_STEPS)} }}' for j, c in cuts) + ' } }\n'
                 '\tset_variable = { name = pmr_fm_lw value = 0 }\n'
                 + ''.join(f'\tset_variable = {{ name = pmr_fm_lt value = {{ value = {fmt(lab(m))} subtract = var:pmr_fm_cut '
                           f'min = 0 multiply = {n(m.j)} }} }}\n'
                           '\tchange_variable = { name = pmr_fm_lw add = var:pmr_fm_lt }\n'
                           for m in bld.recipes if lab(m) > EPS)
                 + ''.join(f'\tset_variable = {{ name = pmr_fm_lt value = {{ value = {n(j)} multiply = {fmt(a)} }} }}\n'
                           '\tchange_variable = { name = pmr_fm_lw add = var:pmr_fm_lt }\n' for j, a in procs)
                 + '\t# the frame\'s own laborers a level (its target\'s, pure or union)\n'
                 '\tset_variable = { name = pmr_fm_fl value = 0 }\n'
                 + lookup('var:pmr_fm_pair', [p for p in pairs if pair_jobs(bld, p) > EPS],
                          lambda p: setv('pmr_fm_fl', fmt(max(0, pair_jobs(bld, p)))))
                 + '\tset_variable = { name = pmr_fm_lb value = { value = var:pmr_fm_lw divide = '
                 f'{SHARE_STEPS} subtract = var:pmr_fm_fl divide = {LAB_GRAIN} min = -{LAB_DOWN} max = {LAB_UP} }} }}\n'
                 '\tround_variable = { name = pmr_fm_lb nearest = 1 }\n'
                 + lookup('var:pmr_fm_lb', list(range(-LAB_DOWN, LAB_UP + 1)), lambda x: act(lab_key(x), lab_key(0)))
                 + f'\t{setv(v("pmr_lbm"), "var:pmr_fm_lb")}\n'
                 # the wage read's nominal crew (generate.py wage_effect): the skilled post the _s union moves, 1 while it runs
                 + (f'\tif = {{ limit = {{ var:pmr_fm_pr = 0 var:pmr_fm_sk > {SHARE_STEPS // 2} }} {setv(v("pmr_fsk"), 1)} }}\n'
                    f'\telse = {{ {setv(v("pmr_fsk"), 0)} }}\n' if bld.skilled else ''))

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
                + f';x={sizes};lab={f(fq)}' + (f';lbm={f(v("pmr_lbm"))}' if bld.steps else '')
                + (';oj=' + '/'.join(f(f'pmr_fm_oj{og.gi}') for og in bld.option_groups) if bld.option_groups else ''))
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


# ---------------------------------------------------------------------------------------------------------------------
# The JOBS line (test builds)

JOBS_DOC = ('# Jobs check (frames.py, test builds): once a month, each of a player\'s buildings on a union frame logs\n'
            '# PMR;rec=JOBS: its level, about the place of its recipe frame in the group\'s list (place), the ' + JOB_POP + '\n'
            '# a level that frame holds (frame) and that x level (want),\n'
            '# the building\'s ' + JOB_POP + ' jobs as the game reads them back (cap; every group\'s, so above want where a\n'
            '# trade-off or Treatment adds its own, and twice want if a method were ever counted twice), those employed,\n'
            '# its occupancy band, and each other pop type\'s jobs (cap_<pop>). -99 is a read the engine refused.\n'
            '# On its own on_action and in files of its own, so nothing here can take the tick with it.\n\n')


def jobs_pops(bld):
    """the pop types the building's frames name, JOB_POP first"""
    pops = set()
    for p in range(1, len(bld.pair_keys) + 1):
        pops |= set(nonzero(pair_amounts(bld, p)[2]))
    for og in bld.option_groups:
        for x in [None] + og.options:
            pops |= set(nonzero(option_full(og, x)[2]))
    return [JOB_POP] + sorted(pops - {JOB_POP})


def jobs_check_files(blds):
    """[(path, text)] of the JOBS line for the buildings blds (frames.Building): a script value, the effects and the
    on_action, the caller's header to go before each."""
    values, effects, monthly = [], [], []
    for bld in blds:
        bk, b = bld.bk, bld.b
        pops = jobs_pops(bld)
        values.append(f'# State scope: the state\'s {JOB_POP} employed in its {bk}, by workforce.\n'
                      f'pmr_jobs_{b} = {{\n\tvalue = 0\n\tevery_scope_pop = {{\n'
                      f'\t\tlimit = {{ pop_employment_building = {bk} is_pop_type = {JOB_POP} }}\n\t\tadd = workforce\n\t}}\n}}\n\n')
        occ = ''.join(f'\t{"if" if i == 0 else "else_if"} = {{ limit = {{ b:{bk} = {{ occupancy >= {x} }} }} '
                      f'set_variable = {{ name = pmr_fj_occ value = {x} }} }}\n' for i, x in enumerate(OCC_BANDS))
        reads = ''.join(f'\tset_variable = {{ name = pmr_fj_c{i} value = -99 }}\n'
                        f'\tset_variable = {{ name = pmr_fj_c{i} value = b:{bk}.modifier:building_employment_{pop}_add }}\n'
                        for i, pop in enumerate(pops))
        f = lambda name, d=0: f"[THIS.Var('{name}').GetValue|{d}]"   # noqa: E731
        line = ('PMR;rec=JOBS;date=[TimeKeeper.GetCurrentDate.GetString];country=[THIS.GetState.GetOwner.GetNameNoFormatting];'
                f'state=[THIS.GetState.GetNameNoFormatting];building={bk};level={f("pmr_fj_lvl")};'
                f'place={f(f"pmr_fpl_{b}")};frame={f(f"pmr_fq_{b}")};'
                f'want={f("pmr_fj_want")};cap={f("pmr_fj_c0")};{JOB_POP}={f("pmr_fj_emp")};occ={f("pmr_fj_occ", 2)}'
                + ''.join(f';cap_{pop}={f(f"pmr_fj_c{i}")}' for i, pop in enumerate(pops) if i))
        # rails: the frame's JOB_POP plus the shared laborers method's (lbm=, in LAB_GRAIN steps)
        lbm = f' add = {{ value = var:pmr_lbm_{b} multiply = {LAB_GRAIN} }}' if bld.steps else ''
        if bld.steps:
            line += f';lbm={f(f"pmr_lbm_{b}")}'
        effects.append(f'# State scope, a state with a {bk} on a union frame.\n'
                       f'pmr_jobs_log_{b} = {{\n'
                       f'\tset_variable = {{ name = pmr_fj_lvl value = b:{bk}.level }}\n'
                       f'\tset_variable = {{ name = pmr_fj_want value = {{ value = var:pmr_fq_{b}{lbm} multiply = var:pmr_fj_lvl }} }}\n'
                       f'\tset_variable = {{ name = pmr_fj_emp value = pmr_jobs_{b} }}\n'
                       '\tset_variable = { name = pmr_fj_occ value = 0 }\n' + occ + reads
                       + f'\tdebug_log = "{line}"\n}}\n\n')
        monthly.append(f'\t\tif = {{ limit = {{ has_variable = pmr_fu_{b} has_variable = pmr_fq_{b} '
                       + (f'has_variable = pmr_lbm_{b} ' if bld.steps else '') + f'has_building = {bk} }} '
                       f'pmr_jobs_log_{b} = yes }}\n')
    return [('common/script_values/pmr_jobs_values.txt', JOBS_DOC + ''.join(values)),
            ('common/scripted_effects/pmr_jobs_effects.txt', JOBS_DOC + ''.join(effects)
             + '# Country scope, a player, monthly.\npmr_jobs_monthly = {\n\tevery_scope_state = {\n' + ''.join(monthly)
             + '\t}\n}\n'),
            ('common/on_actions/pmr_jobs_on_actions.txt', JOBS_DOC
             + 'on_monthly_pulse_country = { on_actions = { pmr_jobs_on_monthly_country } }\n\n'
             '# Root = country.\npmr_jobs_on_monthly_country = {\n\ttrigger = { is_player = yes }\n'
             '\teffect = { pmr_jobs_monthly = yes }\n}\n')]
