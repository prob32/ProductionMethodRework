"""The jobs probe (method-count PLAN section 6; q99's run, Pat 2026-11-10 20:41Z).

q99 settled two of its three questions: goods_output_<good>_mult on a building's own modifier lands (furniture and
textile cards), and building.modifier:<key> reads back. It left the third null: building_employment_laborers_mult
-0.50 on a fishing wharf read back all year yet the wharf kept every laborer. Vanilla has commented out its own
building_employment_* lines on building modifiers (agitators_4_modifiers.txt) and moves jobs only with a state's
building_group_bg_<group>_employee_mult (state_oil_rush). Five routes, each on a British fishing wharf of its own,
against an untouched one:
  control  Lancashire (level 3)
  a        Home Counties (2): the same laborers mult -50%, then the wharf's method switched away and back each month
  b        Highlands (4): building_employment_laborers_add, negative, sized to half the level's trawler laborers
  c        East Anglia (3): building_group_bg_fishing_employee_mult -50% on the state (the oil rush route)
  d        West Country (2): building_employment_laborers_mult +50% on the building
  e        Lowlands (2): building_group_bg_fishing_employee_mult -50% on the building
Applied on 1 January 1836. Monthly per wharf: PMR;rec=PROBE;p=J (level, laborers employed, ratio to January,
occupancy band, the frame's own cut, the switch in a) and p=M (the four modifier totals as read back; -99 is a read
the engine refused).

Test builds with --frame-probe only. files() raises if a modifier type is declared nowhere in the build or vanilla.
"""

BUILDING = 'building_fishing_wharf'
SHORT = BUILDING[len('building_'):]
POP = 'laborers'
GROUP = 'bg_fishing'
CUT = 0.5               # every route moves laborer jobs by half
JOBS_PER_LEVEL = 4000   # pm_fishing_trawlers' laborers per level, the method every probe wharf runs on day one
METHOD, OTHER = 'pm_fishing_trawlers', 'pm_simple_fishing'   # route a switches between these
ICON = 'gfx/interface/icons/generic_icons/mixed_icon_base.dds'

MULT = f'building_employment_{POP}_mult'
ADD = f'building_employment_{POP}_add'
GRP = f'building_group_{GROUP}_employee_mult'

# (role, state, what it gets)
ROLES = [('control', 'STATE_LANCASHIRE', None),
         ('a', 'STATE_HOME_COUNTIES', 'mult_minus'),
         ('b', 'STATE_HIGHLANDS', 'add_minus'),
         ('c', 'STATE_EAST_ANGLIA', 'group_state'),
         ('d', 'STATE_WEST_COUNTRY', 'mult_plus'),
         ('e', 'STATE_LOWLANDS', 'group_building')]

# static modifier name -> (type, sign of its key)
MODS = {'pmr_probe_job_mult_minus': (MULT, -1), 'pmr_probe_job_add_minus': (ADD, -1),
        'pmr_probe_job_group_minus': (GRP, -1), 'pmr_probe_job_mult_plus': (MULT, 1)}

OCC_BANDS = (1.5, 1.2, 1.05, 1.0, 0.98, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5, 0.4, 0.3, 0.2, 0.1)

HEAD = ('# Jobs probe (frame_probe.py, --frame-probe): five routes to move a building\'s jobs, one British fishing\n'
        '# wharf each, against a control. Great Britain only, logs on its own.\n\n')

READS = [('mult', 'pmr_pf_rm', f'b:{BUILDING}.modifier:{MULT}'),
         ('add', 'pmr_pf_ra', f'b:{BUILDING}.modifier:{ADD}'),
         ('group', 'pmr_pf_rg', f'b:{BUILDING}.modifier:{GRP}'),
         ('state_group', 'pmr_pf_rs', f'modifier:{GRP}')]


def _glob(role):
    return f'pmr_probe_{role}'


def _line(p, role, fields, extra=''):
    return ('debug_log = "PMR;rec=PROBE;p=' + p + ';date=[TimeKeeper.GetCurrentDate.GetString];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={BUILDING};role={role};' + extra
            + ';'.join(f'{k}=[THIS.Var(\'{v}\').GetValue|{d}]' for k, v, d in fields) + '"')


J_FIELDS = [('level', 'pmr_pf_lvl', 0), (POP, 'pmr_pf_lab', 0), (f'{POP}_n', 'pmr_pf_labn', 0),
            ('jan', 'pmr_pf_lab0', 0), ('ratio', 'pmr_pf_ratio', 2), ('occ', 'pmr_pf_occ', 2),
            ('frame_cut', 'pmr_pf_fx', 2), ('switched', 'pmr_pf_tg', 0)]
M_FIELDS = [(k, v, 2) for k, v, _ in READS]


def _apply(kind):
    """State scope, the wharf exists: put this route's modifier on."""
    b = f'b:{BUILDING}'
    if kind == 'mult_minus':
        return f'\t\t\t{b} = {{ add_modifier = {{ name = pmr_probe_job_mult_minus multiplier = {CUT} }} }}\n'
    if kind == 'mult_plus':
        return f'\t\t\t{b} = {{ add_modifier = {{ name = pmr_probe_job_mult_plus multiplier = {CUT} }} }}\n'
    if kind == 'group_building':
        return f'\t\t\t{b} = {{ add_modifier = {{ name = pmr_probe_job_group_minus multiplier = {CUT} }} }}\n'
    if kind == 'group_state':
        return f'\t\t\tadd_modifier = {{ name = pmr_probe_job_group_minus multiplier = {CUT} }}\n'
    if kind == 'add_minus':
        return '\t\t\tpmr_probe_job_size_add = yes\n'
    return ''


def files(declared_types):
    """[(path, text)] and the English loc lines, for a test build. declared_types: every modifier type the build
    declares or vanilla has."""
    missing = sorted({t for t, _ in MODS.values()} - set(declared_types))
    if missing:
        raise SystemExit(f'jobs probe: {missing} declared nowhere in this build or vanilla')

    mods = HEAD + ''.join(f'{name} = {{\n\ticon = "{ICON}"\n\t{t} = {sign}\n}}\n\n' for name, (t, sign) in MODS.items())

    values = HEAD + ''.join(
        f'# State scope: the state\'s {POP} employed in its {BUILDING} (a state has one of each type), by {what}.\n'
        f'{name} = {{\n\tvalue = 0\n\tevery_scope_pop = {{\n'
        f'\t\tlimit = {{ pop_employment_building = {BUILDING} is_pop_type = {POP} }}\n\t\tadd = {field}\n\t}}\n}}\n\n'
        for name, what, field in (('pmr_probe_frame_workers', 'workforce', 'workforce'),
                                  ('pmr_probe_frame_workers_n', 'pop size', 'total_size')))

    occ = ''.join(f'\t{"if" if i == 0 else "else_if"} = {{ limit = {{ b:{BUILDING} = {{ occupancy >= {x} }} }} '
                  f'set_variable = {{ name = pmr_pf_occ value = {x} }} }}\n' for i, x in enumerate(OCC_BANDS))
    reads = ''.join(
        f'# The wharf\'s {what} read back, on its own so a read the engine refuses cannot take the others (the caller\'s -99 stays).\n'
        f'pmr_probe_job_read_{k} = {{\n\tset_variable = {{ name = {v} value = {link} }}\n}}\n\n'
        for (k, v, link), what in zip(READS, (MULT, ADD, GRP, f'state\'s {GRP}')))
    switch = (f'# Route a: switch the wharf\'s method away and back (pmr_pf_tg 1 when the first switch is seen at once,\n'
              f'# 0 when not, -1 when it runs neither {METHOD} nor {OTHER}).\n'
              'pmr_probe_job_switch = {\n\tset_variable = { name = pmr_pf_tg value = -1 }\n')
    for i, (on, to) in enumerate(((METHOD, OTHER), (OTHER, METHOD))):
        switch += (f'\t{"if" if i == 0 else "else_if"} = {{\n'
                   f'\t\tlimit = {{ is_production_method_active = {{ building_type = {BUILDING} production_method = {on} }} }}\n'
                   '\t\tset_variable = { name = pmr_pf_tg value = 0 }\n'
                   f'\t\tactivate_production_method = {{ building_type = {BUILDING} production_method = {to} }}\n'
                   f'\t\tif = {{ limit = {{ is_production_method_active = {{ building_type = {BUILDING} production_method = {to} }} }} '
                   'set_variable = { name = pmr_pf_tg value = 1 } }\n'
                   f'\t\tactivate_production_method = {{ building_type = {BUILDING} production_method = {on} }}\n\t}}\n')
    switch += '}\n\n'
    size_add = (f'# Route b: {ADD} at -1 x (level x {JOBS_PER_LEVEL} x {CUT}), resized when the level moves\n'
                '# (pmr_pf_szl the level it was sized for). pmr_pf_lvl must be fresh.\n'
                'pmr_probe_job_size_add = {\n'
                '\tif = { limit = { NOT = { has_variable = pmr_pf_szl } } set_variable = { name = pmr_pf_szl value = 0 } }\n'
                '\tif = {\n\t\tlimit = { NOT = { var:pmr_pf_szl = var:pmr_pf_lvl } }\n'
                f'\t\tb:{BUILDING} = {{ if = {{ limit = {{ has_modifier = pmr_probe_job_add_minus }} remove_modifier = pmr_probe_job_add_minus }} }}\n'
                f'\t\tset_local_variable = {{ name = pmr_pf_lm value = {{ value = var:pmr_pf_lvl multiply = {int(JOBS_PER_LEVEL * CUT)} }} }}\n'
                f'\t\tb:{BUILDING} = {{ add_modifier = {{ name = pmr_probe_job_add_minus multiplier = local_var:pmr_pf_lm }} }}\n'
                '\t\tset_variable = { name = pmr_pf_szl value = var:pmr_pf_lvl }\n\t}\n}\n\n')

    setup = ('# Game start, no root. Each route\'s state, if Great Britain holds it with a fishing wharf, is kept in\n'
             '# global pmr_probe_<role> and gets its modifier; a missing one logs camp=none.\n'
             'pmr_probe_frame_setup = {\n')
    monthly = '# Root = Great Britain, monthly: one J and one M line per wharf.\npmr_probe_frame_monthly = {\n'
    for role, state, kind in ROLES:
        g = _glob(role)
        setup += (f'\ts:{state}.region_state:GBR ?= {{\n\t\tif = {{\n\t\t\tlimit = {{ has_building = {BUILDING} }}\n'
                  f'\t\t\tset_global_variable = {{ name = {g} value = this }}\n'
                  '\t\t\tset_variable = { name = pmr_pf_lab0 value = 0 }\n'
                  '\t\t\tpmr_probe_frame_read = yes\n'
                  + _apply(kind)
                  + ('\t\t\tpmr_probe_job_switch = yes\n' if kind == 'mult_minus' else '\t\t\tset_variable = { name = pmr_pf_tg value = 0 }\n')
                  + '\t\t\tif = { limit = { var:pmr_pf_lab > 0 } set_variable = { name = pmr_pf_lab0 value = var:pmr_pf_lab } }\n'
                  f'\t\t\t{_line("setup", role, [("level", "pmr_pf_lvl", 0), (POP, "pmr_pf_lab", 0), ("switched", "pmr_pf_tg", 0)], f"state_key={state};")}\n'
                  '\t\t}\n\t}\n'
                  f'\tif = {{ limit = {{ NOT = {{ has_global_variable = {g} }} }} '
                  f'debug_log = "PMR;rec=PROBE;p=setup;date=[TimeKeeper.GetCurrentDate.GetString];role={role};state_key={state};camp=none" }}\n')
        gone = ('debug_log = "PMR;rec=PROBE;p=J;date=[TimeKeeper.GetCurrentDate.GetString];'
                f'state=[THIS.GetState.GetNameNoFormatting];building={BUILDING};role={role};gone=1"')
        monthly += (f'\tif = {{\n\t\tlimit = {{ has_global_variable = {g} }}\n\t\tglobal_var:{g} = {{\n'
                    f'\t\t\tif = {{\n\t\t\t\tlimit = {{ has_building = {BUILDING} }}\n'
                    '\t\t\t\tpmr_probe_frame_read = yes\n'
                    + ''.join(f'\t\t\t\tset_variable = {{ name = {v} value = -99 }}\n\t\t\t\tpmr_probe_job_read_{k} = yes\n'
                              for k, v, _ in READS)
                    + '\t\t\t\t# the first reading with workers in it is the January figure\n'
                    '\t\t\t\tif = { limit = { var:pmr_pf_lab0 <= 0 } set_variable = { name = pmr_pf_lab0 value = var:pmr_pf_lab } }\n'
                    '\t\t\t\tset_variable = { name = pmr_pf_ratio value = 0 }\n'
                    '\t\t\t\tif = { limit = { var:pmr_pf_lab0 > 0 } set_variable = { name = pmr_pf_ratio value = { value = var:pmr_pf_lab divide = var:pmr_pf_lab0 } } }\n'
                    + ('\t\t\t\tpmr_probe_job_switch = yes\n' if kind == 'mult_minus' else '')
                    + ('\t\t\t\tpmr_probe_job_size_add = yes\n' if kind == 'add_minus' else '')
                    + f'\t\t\t\t{_line("J", role, J_FIELDS)}\n'
                    f'\t\t\t\t{_line("M", role, M_FIELDS)}\n'
                    f'\t\t\t}}\n\t\t\telse = {{ {gone} }}\n\t\t}}\n\t}}\n')
    setup += '}\n\n'
    monthly += '}\n'

    effects = (
        HEAD
        + f'# State scope, a state with a {BUILDING}: pmr_pf_lvl level, pmr_pf_lab {POP} employed by workforce, pmr_pf_labn\n'
        f'# by pop size, pmr_pf_fx the frame\'s own {POP} cut on it (0 on a pure frame), pmr_pf_occ its occupancy band\n'
        '# (the highest band it reaches; 0 under the lowest).\n'
        'pmr_probe_frame_read = {\n'
        f'\tset_variable = {{ name = pmr_pf_lvl value = b:{BUILDING}.level }}\n'
        '\tset_variable = { name = pmr_pf_lab value = pmr_probe_frame_workers }\n'
        '\tset_variable = { name = pmr_pf_labn value = pmr_probe_frame_workers_n }\n'
        '\tset_variable = { name = pmr_pf_fx value = 0 }\n'
        f'\tif = {{ limit = {{ has_variable = pmr_lj_{POP}_{SHORT} }} set_variable = {{ name = pmr_pf_fx value = var:pmr_lj_{POP}_{SHORT} }} }}\n'
        '\tset_variable = { name = pmr_pf_occ value = 0 }\n'
        + occ + '}\n\n' + reads + switch + size_add + setup + monthly)

    on_actions = (HEAD + 'on_game_started = { on_actions = { pmr_probe_on_game_started } }\n'
                  'on_monthly_pulse_country = { on_actions = { pmr_probe_on_monthly_country } }\n\n'
                  '# No root.\npmr_probe_on_game_started = {\n\teffect = { pmr_probe_frame_setup = yes }\n}\n\n'
                  '# Root = country; Great Britain only.\npmr_probe_on_monthly_country = {\n'
                  '\ttrigger = { exists = c:GBR this = c:GBR }\n\teffect = { pmr_probe_frame_monthly = yes }\n}\n')
    import frames   # the GUI hides timed modifiers by this name (generate.py LESS_SHOWN)
    loc = [f' {name}:0 "{frames.LESS_NAME}"' for name in MODS]
    return [('common/static_modifiers/pmr_probe_modifiers.txt', mods),
            ('common/script_values/pmr_probe_frame_values.txt', values),
            ('common/scripted_effects/pmr_probe_frame_effects.txt', effects),
            ('common/on_actions/pmr_probe_on_actions.txt', on_actions)], loc
