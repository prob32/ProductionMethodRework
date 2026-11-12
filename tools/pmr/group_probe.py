"""The group jobs probe (pmr/fundamentals-review/group-jobs-probe/PROBE.md; Pat 2026-11-12 04:21Z, "Can't we just put
every building into a building group?").

q100 (frame_probe.py) found one route that moves a building's jobs: building_group_bg_<g>_employee_mult on the STATE,
which reaches every building of the group. If each PMR type had a group of its own, that would be a workforce figure
per building. Two things only a game can answer: does the engine honour an employee multiplier declared for a group
the mod made, and does a building moved into a child group keep what its old group gave it?

The probe moves building_textile_mill into bg_pmr_g_textile_mill (parent bg_light_industry, restating its parent's
own lines), declares that group's employee multiplier, and on 1 January 1836 puts state modifiers on British states:
  control  Lancashire     nothing
  g1       Midlands       the new group's multiplier at -50%
  g2       Yorkshire      the new group's multiplier at -25%, -50% from 1 April, removed from 1 July
  g3       Home Counties  vanilla's bg_manufacturing multiplier at -50% (the mill's grandparent); also logs the
                          state's furniture manufactory, which the same modifier must move
West Country logs too (setup and monthly, role=extra) for the trigger and throughput reads.

Lines: PMR;rec=PROBE;p=Gsetup on day one per state (the group triggers), p=G monthly per state (laborers, machinists
and shopkeepers employed, each against January, occupancy band, the g2 stage, g3's other factory) and p=GM monthly
(the state's read of both multiplier types and the mill's and the furniture manufactory's throughput reads; -99 is a
read the engine refused, or thr_other in a state with no furniture manufactory). Great Britain only. Test builds with --group-probe only; no PMR mechanic changes.
"""

import frame_probe

BUILDING = 'building_textile_mill'
PARENT = 'bg_light_industry'
TOP = 'bg_manufacturing'
GROUP = 'bg_pmr_g_textile_mill'
OTHER = 'building_furniture_manufactory'   # in PARENT; g3's parent route must move it too, and its throughput is the
                                           # reference for the mill's (economy of scale through the child group)
POPS = ('laborers', 'machinists', 'shopkeepers')
NEW_TYPE = f'building_group_{GROUP}_employee_mult'
TOP_TYPE = f'building_group_{TOP}_employee_mult'   # vanilla declares it
THR = 'building_throughput_add'
CUT = 0.5

# vanilla's bg_light_industry lines, restated so nothing depends on which lines a child inherits
GROUP_TEXT = (f'{GROUP} = {{\n\tparent_group = {PARENT}\n\tlens = light_industry\n\turbanization = 20\n'
              '\teconomy_of_scale_ai_factor = 3.0\n\tinfrastructure_usage_per_level = 1.5\n'
              '\tconstruction_efficiency_modifier = yes\n}\n')

# static modifier -> type (each at -1, sized by the add_modifier multiplier)
MODS = {'pmr_probe_gj_new': NEW_TYPE, 'pmr_probe_gj_parent': TOP_TYPE}

# (role, state, modifier, size)
ROLES = [('control', 'STATE_LANCASHIRE', None, 0),
         ('g1', 'STATE_MIDLANDS', 'pmr_probe_gj_new', CUT),
         ('g2', 'STATE_YORKSHIRE', 'pmr_probe_gj_new', 0.25),
         ('g3', 'STATE_HOME_COUNTIES', 'pmr_probe_gj_parent', CUT),
         ('extra', 'STATE_WEST_COUNTRY', None, 0)]
G2_STEPS = (('1836.4.1', 1, CUT), ('1836.7.1', 2, 0))   # (from, stage, size; 0 = removed)

HEAD = ('# Group jobs probe (group_probe.py, --group-probe): the textile mill in a building group of its own, with that\n'
        '# group\'s employee multiplier on British states. Great Britain only, logs on its own.\n\n')

READS = [('new', 'pmr_pg_rn', f'modifier:{NEW_TYPE}'),
         ('parent', 'pmr_pg_rp', f'modifier:{TOP_TYPE}'),
         ('thr', 'pmr_pg_thr', f'b:{BUILDING}.modifier:{THR}'),
         ('thr_other', 'pmr_pg_tho', f'b:{OTHER}.modifier:{THR}')]


def regroup(name, text):
    """(text, hits): a common/buildings file with the mill's building_group line pointed at GROUP."""
    start = text.find(f'\n{BUILDING} = {{')
    if start < 0:
        return text, 0
    end = text.find('\n}', start)
    old, new = f'\n\tbuilding_group = {PARENT}\n', f'\n\tbuilding_group = {GROUP}\n'
    block = text[start:end]
    if block.count(old) != 1:
        raise SystemExit(f'group probe: {name} has no single "building_group = {PARENT}" line in {BUILDING}')
    return text[:start] + block.replace(old, new) + text[end:], 1


def _line(p, role, fields, extra=''):
    return ('debug_log = "PMR;rec=PROBE;p=' + p + ';date=[TimeKeeper.GetCurrentDate.GetString];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={BUILDING};role={role};' + extra
            + ';'.join(f'{k}=[THIS.Var(\'{v}\').GetValue|{d}]' for k, v, d in fields) + '"')


def _short(pop):
    return pop[:3]


G_FIELDS = ([('level', 'pmr_pg_lvl', 0)]
            + [f for pop in POPS for f in ((pop, f'pmr_pg_{_short(pop)}', 0),
                                           (f'{pop}_jan', f'pmr_pg_{_short(pop)}0', 0),
                                           (f'{pop}_ratio', f'pmr_pg_{_short(pop)}r', 2))]
            + [('occ', 'pmr_pg_occ', 2), ('stage', 'pmr_pg_stage', 0)])
OTHER_FIELDS = [('other_level', 'pmr_pg_olvl', 0), ('other_laborers', 'pmr_pg_olab', 0),
                ('other_jan', 'pmr_pg_olab0', 0), ('other_ratio', 'pmr_pg_olabr', 2)]
GM_FIELDS = [(k, v, 2) for k, v, _ in READS]
SETUP_FIELDS = [('level', 'pmr_pg_lvl', 0), ('laborers', 'pmr_pg_lab', 0), ('in_parent', 'pmr_pg_inp', 0),
                ('in_top', 'pmr_pg_intop', 0), ('in_own', 'pmr_pg_inown', 0), ('other_in_own', 'pmr_pg_oown', 0)]


def files():
    """[(path, text)] and the English loc lines, for a test build."""
    groups = HEAD + GROUP_TEXT
    types = HEAD + f'{NEW_TYPE} = {{\n\tdecimals = 1\n\tcolor = bad\n\tpercent = yes\n\tgame_data = {{ ai_value = 0 }}\n}}\n'
    mods = HEAD + ''.join(f'{name} = {{\n\ticon = "{frame_probe.ICON}"\n\t{t} = -1\n}}\n\n' for name, t in MODS.items())

    values = HEAD
    for b, tag in ((BUILDING, ''), (OTHER, 'other_')):
        for pop in (POPS if b == BUILDING else ('laborers',)):
            values += (f'# State scope: the state\'s {pop} employed in its {b} (a state has one of each type).\n'
                       f'pmr_probe_gj_{tag}{pop} = {{\n\tvalue = 0\n\tevery_scope_pop = {{\n'
                       f'\t\tlimit = {{ pop_employment_building = {b} is_pop_type = {pop} }}\n\t\tadd = workforce\n\t}}\n}}\n\n')

    occ = ''.join(f'\t{"if" if i == 0 else "else_if"} = {{ limit = {{ b:{BUILDING} = {{ occupancy >= {x} }} }} '
                  f'set_variable = {{ name = pmr_pg_occ value = {x} }} }}\n' for i, x in enumerate(frame_probe.OCC_BANDS))

    def ratio(var, jan, out):
        return (f'\tif = {{ limit = {{ var:{jan} <= 0 }} set_variable = {{ name = {jan} value = var:{var} }} }}\n'
                f'\tset_variable = {{ name = {out} value = 0 }}\n'
                f'\tif = {{ limit = {{ var:{jan} > 0 }} set_variable = {{ name = {out} value = {{ value = var:{var} divide = var:{jan} }} }} }}\n')

    read = (f'# State scope, a state with a {BUILDING}: its level, each pop type employed and that type\'s ratio to the first\n'
            f'# reading with workers in it, its occupancy band, and the same for the state\'s {OTHER} (-1 when it has none).\n'
            'pmr_probe_gj_read = {\n'
            f'\tset_variable = {{ name = pmr_pg_lvl value = b:{BUILDING}.level }}\n'
            + ''.join(f'\tset_variable = {{ name = pmr_pg_{_short(p)} value = pmr_probe_gj_{p} }}\n'
                      f'\tif = {{ limit = {{ NOT = {{ has_variable = pmr_pg_{_short(p)}0 }} }} set_variable = {{ name = pmr_pg_{_short(p)}0 value = 0 }} }}\n'
                      for p in POPS)
            + ''.join(ratio(f'pmr_pg_{_short(p)}', f'pmr_pg_{_short(p)}0', f'pmr_pg_{_short(p)}r') for p in POPS)
            + '\tset_variable = { name = pmr_pg_occ value = 0 }\n' + occ
            + f'\tif = {{\n\t\tlimit = {{ has_building = {OTHER} }}\n'
            f'\t\tset_variable = {{ name = pmr_pg_olvl value = b:{OTHER}.level }}\n'
            '\t\tset_variable = { name = pmr_pg_olab value = pmr_probe_gj_other_laborers }\n'
            '\t\tif = { limit = { NOT = { has_variable = pmr_pg_olab0 } } set_variable = { name = pmr_pg_olab0 value = 0 } }\n'
            + ratio('pmr_pg_olab', 'pmr_pg_olab0', 'pmr_pg_olabr')
            + '\t}\n\telse = {\n'
            + ''.join(f'\t\tset_variable = {{ name = {v} value = -1 }}\n' for _, v, _ in OTHER_FIELDS)
            + '\t}\n}\n\n')
    reads = ''.join(
        f'# The {k} read, on its own so a read the engine refuses cannot take the others (the caller\'s -99 stays).\n'
        f'pmr_probe_gj_read_{k} = {{\n\tset_variable = {{ name = {v} value = {link} }}\n}}\n\n'
        for k, v, link in READS)
    triggers = ('# State scope, on day one: which groups the mill (and the state\'s furniture manufactory) counts as.\n'
                'pmr_probe_gj_groups = {\n'
                + ''.join(f'\tset_variable = {{ name = {v} value = 0 }}\n'
                          f'\tif = {{ limit = {{ b:{b} ?= {{ is_building_group = {g} }} }} set_variable = {{ name = {v} value = 1 }} }}\n'
                          for v, b, g in (('pmr_pg_inp', BUILDING, PARENT), ('pmr_pg_intop', BUILDING, TOP),
                                          ('pmr_pg_inown', BUILDING, GROUP), ('pmr_pg_oown', OTHER, GROUP)))
                + '}\n\n')

    setup = ('# Game start, no root. Each role\'s state, if Great Britain holds it with a textile mill, is kept in global\n'
             '# pmr_probe_g_<role> and gets its modifier; a missing one logs mill=none.\n'
             'pmr_probe_gj_setup = {\n')
    monthly = '# Root = Great Britain, monthly: one G and one GM line per state.\npmr_probe_gj_monthly = {\n'
    for role, state, mod, size in ROLES:
        g = f'pmr_probe_g_{role}'
        setup += (f'\ts:{state}.region_state:GBR ?= {{\n\t\tif = {{\n\t\t\tlimit = {{ has_building = {BUILDING} }}\n'
                  f'\t\t\tset_global_variable = {{ name = {g} value = this }}\n'
                  '\t\t\tset_variable = { name = pmr_pg_stage value = 0 }\n'
                  + (f'\t\t\tadd_modifier = {{ name = {mod} multiplier = {size} }}\n' if mod else '')
                  + '\t\t\tpmr_probe_gj_read = yes\n\t\t\tpmr_probe_gj_groups = yes\n'
                  f'\t\t\t{_line("Gsetup", role, SETUP_FIELDS, f"state_key={state};modifier={mod or 'none'};size={size};")}\n'
                  '\t\t}\n\t}\n'
                  f'\tif = {{ limit = {{ NOT = {{ has_global_variable = {g} }} }} '
                  f'debug_log = "PMR;rec=PROBE;p=Gsetup;date=[TimeKeeper.GetCurrentDate.GetString];role={role};state_key={state};mill=none" }}\n')
        steps = ''
        if role == 'g2':
            for when, stage, sz in G2_STEPS:
                steps += (f'\t\t\t\tif = {{\n\t\t\t\t\tlimit = {{ game_date >= {when} var:pmr_pg_stage < {stage} }}\n'
                          f'\t\t\t\t\tremove_modifier = {mod}\n'
                          + (f'\t\t\t\t\tadd_modifier = {{ name = {mod} multiplier = {sz} }}\n' if sz else '')
                          + f'\t\t\t\t\tset_variable = {{ name = pmr_pg_stage value = {stage} }}\n\t\t\t\t}}\n')
        gone = ('debug_log = "PMR;rec=PROBE;p=G;date=[TimeKeeper.GetCurrentDate.GetString];'
                f'state=[THIS.GetState.GetNameNoFormatting];building={BUILDING};role={role};gone=1"')
        monthly += (f'\tif = {{\n\t\tlimit = {{ has_global_variable = {g} }}\n\t\tglobal_var:{g} = {{\n'
                    f'\t\t\tif = {{\n\t\t\t\tlimit = {{ has_building = {BUILDING} }}\n'
                    + steps
                    + '\t\t\t\tpmr_probe_gj_read = yes\n'
                    + ''.join(f'\t\t\t\tset_variable = {{ name = {v} value = -99 }}\n'
                              + (f'\t\t\t\tif = {{ limit = {{ has_building = {OTHER} }} pmr_probe_gj_read_{k} = yes }}\n'
                                 if k == 'thr_other' else f'\t\t\t\tpmr_probe_gj_read_{k} = yes\n')
                              for k, v, _ in READS)
                    + f'\t\t\t\t{_line("G", role, G_FIELDS + OTHER_FIELDS)}\n'
                    f'\t\t\t\t{_line("GM", role, GM_FIELDS)}\n'
                    f'\t\t\t}}\n\t\t\telse = {{ {gone} }}\n\t\t}}\n\t}}\n')
    setup += '}\n\n'
    monthly += '}\n'

    effects = HEAD + read + reads + triggers + setup + monthly
    on_actions = (HEAD + 'on_game_started = { on_actions = { pmr_probe_gj_on_game_started } }\n'
                  'on_monthly_pulse_country = { on_actions = { pmr_probe_gj_on_monthly_country } }\n\n'
                  '# No root.\npmr_probe_gj_on_game_started = {\n\teffect = { pmr_probe_gj_setup = yes }\n}\n\n'
                  '# Root = country; Great Britain only.\npmr_probe_gj_on_monthly_country = {\n'
                  '\ttrigger = { exists = c:GBR this = c:GBR }\n\teffect = { pmr_probe_gj_monthly = yes }\n}\n')
    loc = [f' {GROUP}:0 "Textile Mills"',
           f' {NEW_TYPE}:0 "Textile Mill Employees"',
           f' {NEW_TYPE}_desc:0 "A bonus or penalty to the number of employees in Textile Mills"']
    loc += [f' {name}:0 "Workforce Probe"' for name in MODS]
    return [('common/building_groups/pmr_probe_gj_groups.txt', groups),
            ('common/modifier_type_definitions/pmr_probe_gj_types.txt', types),
            ('common/static_modifiers/pmr_probe_gj_modifiers.txt', mods),
            ('common/script_values/pmr_probe_gj_values.txt', values),
            ('common/scripted_effects/pmr_probe_gj_effects.txt', effects),
            ('common/on_actions/pmr_probe_gj_on_actions.txt', on_actions)], loc
