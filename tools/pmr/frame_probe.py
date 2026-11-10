"""The frame probe (method-count PLAN section 6, folded into the first frames build, Pat 2026-11-10 19:50Z).

Three questions the frames rest on, answered in the real game by two British fishing wharves:
  P1  does add_modifier with building_employment_<pop>_mult move a building's jobs?
  P2  does goods_output_<good>_mult land on a building's output?
  P3  can script read a building's modifier totals back (building.modifier:<key>)?
On 1 January 1836 Great Britain's first state (in its own state order) with a fishing wharf of 2 levels or more
gets laborer jobs x 0.5 and fish output x 0.7 from two static modifiers of its own; the second such state is the
control and gets nothing. Both log monthly: PMR;rec=PROBE;p=setup|P1|P2|P3. The frame's own laborer cut on the same
wharf (pmr_lj_laborers_fishing_wharf, 0 while it runs a pure frame) is logged beside it, so a retool that blends
either wharf shows as frame_cut and is not read as the probe.

Test builds with --frame-probe only. The modifier types come from the frames' own type file (or Company Culture's,
for goods_output_fish_mult): files() raises if either is missing there, as a second copy would clash.
"""

BUILDING = 'building_fishing_wharf'
POP = 'laborers'
GOOD = 'fish'
JOB_CUT = 0.5   # the probe wharf's laborer jobs x (1 - JOB_CUT)
OUT_CUT = 0.3   # its fish output x (1 - OUT_CUT)
ICON = 'gfx/interface/icons/generic_icons/mixed_icon_base.dds'

HEAD = '# Frame probe (frame_probe.py, --frame-probe): P1 jobs, P2 goods, P3 reads. Great Britain only, logs on its own.\n\n'


def _line(p, role, fields):
    return ('debug_log = "PMR;rec=PROBE;p=' + p + ';date=[TimeKeeper.GetCurrentDate.GetString];'
            'country=[THIS.GetState.GetOwner.GetNameNoFormatting];state=[THIS.GetState.GetNameNoFormatting];'
            f'building={BUILDING};role={role};' + ';'.join(f'{k}=[THIS.Var(\'{v}\').GetValue|{d}]' for k, v, d in fields) + '"')


def _monthly(glob, role):
    p1 = _line('P1', role, [('level', 'pmr_pf_lvl', 0), (POP, 'pmr_pf_lab', 0), (f'{POP}_n', 'pmr_pf_labn', 0),
                            ('jan', 'pmr_pf_lab0', 0), ('ratio', 'pmr_pf_ratio', 2), ('frame_cut', 'pmr_pf_fx', 2)])
    p2 = _line('P2', role, [(f'{GOOD}_mult', 'pmr_pf_out', 2)])
    p3 = _line('P3', role, [(f'{GOOD}_mult', 'pmr_pf_out', 2), (f'{POP}_mult', 'pmr_pf_labm', 2)])
    gone = ('debug_log = "PMR;rec=PROBE;p=P1;date=[TimeKeeper.GetCurrentDate.GetString];'
            f'state=[THIS.GetState.GetNameNoFormatting];building={BUILDING};role={role};gone=1"')
    return (f'\tif = {{\n\t\tlimit = {{ has_global_variable = {glob} }}\n\t\tglobal_var:{glob} = {{\n'
            f'\t\t\tif = {{\n\t\t\t\tlimit = {{ has_building = {BUILDING} }}\n'
            '\t\t\t\tpmr_probe_frame_read = yes\n'
            '\t\t\t\tpmr_probe_frame_read_mods = yes\n'
            '\t\t\t\t# the first reading with workers in it is the January figure\n'
            '\t\t\t\tif = { limit = { var:pmr_pf_lab0 <= 0 } set_variable = { name = pmr_pf_lab0 value = var:pmr_pf_lab } }\n'
            '\t\t\t\tset_variable = { name = pmr_pf_ratio value = 0 }\n'
            '\t\t\t\tif = { limit = { var:pmr_pf_lab0 > 0 } set_variable = { name = pmr_pf_ratio value = { value = var:pmr_pf_lab divide = var:pmr_pf_lab0 } } }\n'
            f'\t\t\t\t{p1}\n\t\t\t\t{p2}\n\t\t\t\t{p3}\n'
            f'\t\t\t}}\n\t\t\telse = {{ {gone} }}\n\t\t}}\n\t}}\n')


def files(declared_types):
    """[(path, text)] and the English loc lines, for a test build. declared_types: every modifier type the build
    declares or vanilla has."""
    job_key, out_key = f'building_employment_{POP}_mult', f'goods_output_{GOOD}_mult'
    missing = [k for k in (job_key, out_key) if k not in declared_types]
    if missing:
        raise SystemExit(f'frame probe: {missing} declared nowhere in this build; the frames type file must carry them')
    short = BUILDING[len('building_'):]
    mods = (HEAD + f'pmr_probe_less_job_{POP} = {{\n\ticon = "{ICON}"\n\t{job_key} = -1\n}}\n\n'
            f'pmr_probe_less_out_{GOOD} = {{\n\ticon = "{ICON}"\n\t{out_key} = -1\n}}\n')
    values = HEAD + ''.join(
        f'# State scope: the state\'s {POP} employed in its {BUILDING} (a state has one of each type), by {what}.\n'
        f'{name} = {{\n\tvalue = 0\n\tevery_scope_pop = {{\n'
        f'\t\tlimit = {{ pop_employment_building = {BUILDING} is_pop_type = {POP} }}\n\t\tadd = {field}\n\t}}\n}}\n\n'
        for name, what, field in (('pmr_probe_frame_workers', 'workforce', 'workforce'),
                                  ('pmr_probe_frame_workers_n', 'pop size', 'total_size')))
    setup_probe = _line('setup', 'probe', [('level', 'pmr_pf_lvl', 0), (POP, 'pmr_pf_lab', 0),
                                           (f'{GOOD}_mult_before', 'pmr_pf_out_was', 2), (f'{GOOD}_mult_after', 'pmr_pf_out', 2),
                                           (f'{POP}_mult_before', 'pmr_pf_labm_was', 2), (f'{POP}_mult_after', 'pmr_pf_labm', 2)])
    setup_ctrl = _line('setup', 'control', [('level', 'pmr_pf_lvl', 0), (POP, 'pmr_pf_lab', 0),
                                            (f'{GOOD}_mult', 'pmr_pf_out', 2), (f'{POP}_mult', 'pmr_pf_labm', 2)])
    none = 'debug_log = "PMR;rec=PROBE;p=setup;date=[TimeKeeper.GetCurrentDate.GetString];role={};camp=none"'
    effects = (
        HEAD
        + f'# State scope, a state with a {BUILDING}: the readings the log lines print.\n'
        f'#   pmr_pf_lvl level, pmr_pf_lab {POP} employed by workforce, pmr_pf_labn by pop size, pmr_pf_fx the frame\'s own\n'
        f'#   {POP} cut on it (0 on a pure frame)\n'
        'pmr_probe_frame_read = {\n'
        f'\tset_variable = {{ name = pmr_pf_lvl value = b:{BUILDING}.level }}\n'
        '\tset_variable = { name = pmr_pf_lab value = pmr_probe_frame_workers }\n'
        '\tset_variable = { name = pmr_pf_labn value = pmr_probe_frame_workers_n }\n'
        '\tset_variable = { name = pmr_pf_fx value = 0 }\n'
        f'\tif = {{ limit = {{ has_variable = pmr_lj_{POP}_{short} }} set_variable = {{ name = pmr_pf_fx value = var:pmr_lj_{POP}_{short} }} }}\n'
        '}\n\n'
        f'# P3 on its own, so a read the engine refuses cannot take P1 with it: pmr_pf_out the {BUILDING}\'s {out_key},\n'
        f'# pmr_pf_labm its {job_key}\n'
        'pmr_probe_frame_read_mods = {\n'
        f'\tset_variable = {{ name = pmr_pf_out value = b:{BUILDING}.modifier:{out_key} }}\n'
        f'\tset_variable = {{ name = pmr_pf_labm value = b:{BUILDING}.modifier:{job_key} }}\n'
        '}\n\n'
        f'# Game start, no root. Great Britain\'s first and second states, in every_scope_state order, with a {BUILDING} of\n'
        '# 2 levels or more (global pmr_probe_camp, pmr_probe_ctrl): the first gets both probe modifiers, the second nothing.\n'
        'pmr_probe_frame_setup = {\n'
        '\tif = {\n\t\tlimit = { exists = c:GBR }\n\t\tc:GBR = {\n\t\t\tevery_scope_state = {\n'
        f'\t\t\t\tlimit = {{ has_building = {BUILDING} b:{BUILDING} = {{ level >= 2 }} }}\n'
        '\t\t\t\tif = { limit = { NOT = { has_global_variable = pmr_probe_camp } } set_global_variable = { name = pmr_probe_camp value = this } }\n'
        '\t\t\t\telse_if = { limit = { NOT = { has_global_variable = pmr_probe_ctrl } } set_global_variable = { name = pmr_probe_ctrl value = this } }\n'
        '\t\t\t}\n\t\t}\n\t}\n'
        '\tif = {\n\t\tlimit = { has_global_variable = pmr_probe_camp }\n\t\tglobal_var:pmr_probe_camp = {\n'
        '\t\t\tset_variable = { name = pmr_pf_lab0 value = 0 }\n'
        '\t\t\tpmr_probe_frame_read = yes\n\t\t\tpmr_probe_frame_read_mods = yes\n'
        '\t\t\tset_variable = { name = pmr_pf_out_was value = var:pmr_pf_out }\n'
        '\t\t\tset_variable = { name = pmr_pf_labm_was value = var:pmr_pf_labm }\n'
        f'\t\t\tb:{BUILDING} = {{\n'
        f'\t\t\t\tadd_modifier = {{ name = pmr_probe_less_job_{POP} multiplier = {JOB_CUT} }}\n'
        f'\t\t\t\tadd_modifier = {{ name = pmr_probe_less_out_{GOOD} multiplier = {OUT_CUT} }}\n'
        '\t\t\t}\n'
        '\t\t\tpmr_probe_frame_read = yes\n\t\t\tpmr_probe_frame_read_mods = yes\n'
        '\t\t\tif = { limit = { var:pmr_pf_lab > 0 } set_variable = { name = pmr_pf_lab0 value = var:pmr_pf_lab } }\n'
        f'\t\t\t{setup_probe}\n'
        f'\t\t}}\n\t}}\n\telse = {{ {none.format("probe")} }}\n'
        '\tif = {\n\t\tlimit = { has_global_variable = pmr_probe_ctrl }\n\t\tglobal_var:pmr_probe_ctrl = {\n'
        '\t\t\tset_variable = { name = pmr_pf_lab0 value = 0 }\n'
        '\t\t\tpmr_probe_frame_read = yes\n\t\t\tpmr_probe_frame_read_mods = yes\n'
        '\t\t\tif = { limit = { var:pmr_pf_lab > 0 } set_variable = { name = pmr_pf_lab0 value = var:pmr_pf_lab } }\n'
        f'\t\t\t{setup_ctrl}\n'
        f'\t\t}}\n\t}}\n\telse = {{ {none.format("control")} }}\n'
        '}\n\n'
        '# Root = Great Britain, monthly: one P1, P2 and P3 line per wharf.\n'
        'pmr_probe_frame_monthly = {\n' + _monthly('pmr_probe_camp', 'probe') + _monthly('pmr_probe_ctrl', 'control') + '}\n')
    on_actions = (HEAD + 'on_game_started = { on_actions = { pmr_probe_on_game_started } }\n'
                  'on_monthly_pulse_country = { on_actions = { pmr_probe_on_monthly_country } }\n\n'
                  '# No root.\npmr_probe_on_game_started = {\n\teffect = { pmr_probe_frame_setup = yes }\n}\n\n'
                  '# Root = country; Great Britain only.\npmr_probe_on_monthly_country = {\n'
                  '\ttrigger = { exists = c:GBR this = c:GBR }\n\teffect = { pmr_probe_frame_monthly = yes }\n}\n')
    loc = [f' pmr_probe_less_job_{POP}:0 "Retooling"', f' pmr_probe_less_out_{GOOD}:0 "Retooling"']
    return [('common/static_modifiers/pmr_probe_modifiers.txt', mods),
            ('common/script_values/pmr_probe_frame_values.txt', values),
            ('common/scripted_effects/pmr_probe_frame_effects.txt', effects),
            ('common/on_actions/pmr_probe_on_actions.txt', on_actions)], loc
