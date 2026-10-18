"""The profit Methods grid, one box per building type in the Investments tab's cards (generate.py methods_view_gui).

Pat, 2026-10-18 18:00Z: what a building type's owners would run, each recipe's icon over its profit per level a week, a
gold square behind the most profitable one (the pick). 18:17Z: types that fold automation show every recipe with every
automation option (pairs_grid). 23:22Z: every card in the same columns, so a type without pairs gets the same box with
one row (recipes_grid): recipe column c sits at PAIR_LEFT + c x PAIR_COL in both, and the caller gives every box the
same width (cols).

The grids read the profit calculation's interface variables (generate.py profit_effect and pair_effect) from whatever
scope the caller names, so the caller decides where the prices come from:
    pmr_rm_<i>_<b>     profit per level a week          pmr_rav_<i>_<b>    1 while recipe i can run
    pmr_rveto_<i>_<b>  1 while recipe i is skipped      pmr_pbest_<b>      the pick (recipe index, 0 if none)
read(name) returns the GUI expression for one of them, e.g. lambda n: f"GetPlayer.MakeScope.Var('{n}').GetValue" for
country copies.
"""

WHITE = 'gfx/interface/backgrounds/white.dds'
GOLD = '0.74 0.60 0.30 0.55'   # the Methods list's highlight (company_culture.py), here on the pick
ROW_H = 70


def gt(expr, n):
    return f"GreaterThan_CFixedPoint({expr}, '(CFixedPoint){n}')"


def eq(expr, n):
    return f"EqualTo_CFixedPoint({expr}, '(CFixedPoint){n}')"


def type_icon(bk, ind):
    """The building type's icon, left of its grid on every card."""
    i1, i2 = ind + '\t', ind + '\t\t'
    return (f'{ind}widget = {{\n{i1}size = {{ 60 {ROW_H} }}\n{i1}icon = {{\n{i2}position = {{ 3 0 }}\n'
            f'{i2}parentanchor = vcenter\n{i2}size = {{ 54 54 }}\n'
            f'{i2}datacontext = "[GetBuildingType(\'{bk}\')]"\n{i2}texture = "[BuildingType.GetIcon]"\n'
            f'{i2}tooltipwidget = {{\n{i2}\tFancyTooltip_BuildingType = {{}}\n{i2}}}\n{i1}}}\n{ind}}}\n')


def recipe_tip_lines(bk, i, key, read, note):
    """The first lines of recipe i's tooltip: its name, and its profit with the caller's note (a [GetCustom(...)]
    fragment naming the pick, a recipe that can't run, or one skipped at the price cap)."""
    b = bk[len('building_'):]
    return [f'#bold ${key}$#!', f"@money![{read(f'pmr_rm_{i}_{b}')}|0] per level a week{note}"]


PAIR_COL, PAIR_ROW, PAIR_HEAD, PAIR_LEFT = 58, 24, 50, 40


def pairs_size(n_cols, n_rows):
    return PAIR_LEFT + n_cols * PAIR_COL + 10, PAIR_HEAD + n_rows * PAIR_ROW + 6


def _box(w, h, ind, visible=None):
    i1 = ind + '\t'
    vis = f'{i1}visible = "[{visible}]"\n' if visible else ''
    return f'{ind}widget = {{\n{vis}{i1}size = {{ {w} {h} }}\n{i1}background = {{\n{i1}\tusing = entry_bg\n{i1}}}\n'


def _head(col, tex, tip, ind):
    """Recipe column col's icon, over its column."""
    i1 = ind + '\t'
    return (f'{ind}icon = {{\n{i1}position = {{ {PAIR_LEFT + col * PAIR_COL + 9} 5 }}\n{i1}size = {{ 40 40 }}\n'
            f'{i1}texture = "{tex}"\n{i1}tooltip = "{tip}"\n{ind}}}\n')


def _cell(col, y, tip, best, alive, value, ind):
    """One figure in column col at row y: the gold square while best holds, faded while alive doesn't."""
    i1, i2 = ind + '\t', ind + '\t\t'
    return (f'{ind}widget = {{\n{i1}position = {{ {PAIR_LEFT + col * PAIR_COL} {y} }}\n'
            f'{i1}size = {{ {PAIR_COL} {PAIR_ROW} }}\n{i1}tooltip = "{tip}"\n'
            f'{i1}icon = {{\n{i2}visible = "[{best}]"\n{i2}position = {{ 2 1 }}\n'
            f'{i2}size = {{ {PAIR_COL - 4} {PAIR_ROW - 2} }}\n{i2}texture = "{WHITE}"\n'
            f'{i2}color = {{ {GOLD} }}\n{i2}alwaystransparent = yes\n{i1}}}\n'
            f'{i1}textbox = {{\n{i2}size = {{ {PAIR_COL} {PAIR_ROW} }}\n{i2}align = hcenter|vcenter|nobaseline\n'
            f'{i2}using = fontsize_small\n{i2}alpha = "[TransparentIfFalse({alive})]"\n'
            f'{i2}raw_text = "@money![{value}|0]"\n{i2}alwaystransparent = yes\n{i1}}}\n{ind}}}\n')


def recipes_grid(bk, recipes, read, tip, ind, cols=None, visible=None):
    """pairs_grid's box with one row, for a building type without automation pairs: recipes: [(index i, icon texture)];
    tip(i) the tooltip key of recipe i. The figure fades while the recipe can't run here or is skipped for an input at
    the +75% price cap. cols: the box's width in columns (the widest card's), else its own."""
    b = bk[len('building_'):]
    i1 = ind + '\t'
    w, h = pairs_size(cols or len(recipes), 1)
    out = _box(w, h, ind, visible)
    for col, (i, tex) in enumerate(recipes):
        out += _head(col, tex, tip(i), i1)
    for col, (i, _) in enumerate(recipes):
        alive = f"And({eq(read(f'pmr_rav_{i}_{b}'), 1)}, Not({eq(read(f'pmr_rveto_{i}_{b}'), 1)}))"
        out += _cell(col, PAIR_HEAD, tip(i), eq(read(f'pmr_pbest_{b}'), i), alive, read(f'pmr_rm_{i}_{b}'), i1)
    return out + f'{ind}}}\n'


def pairs_grid(bk, recipes, options, read, tip, ind, cols=None, visible=None):
    """Pat, 2026-10-18 18:17Z: every recipe with every automation (PM1 + PM3), the same gold highlight on the most
    profitable pair. Columns are the plain recipes (recipes: [(index i, icon texture)]), rows the automation options
    (options: [(option tooltip key, icon texture)], a = 1 none). Reads generate.py pair_effect's interface:
        pmr_cp_<i>_<a>_<b>   profit per level a week     pmr_cav_<i>_<a>_<b>  1 while the pair could run
        pmr_cbi_<b>, pmr_cba_<b>  the most profitable runnable pair
    tip(i, a): the tooltip key of a cell (a = 0 the column's icon). cols as recipes_grid."""
    b = bk[len('building_'):]
    i1, i2 = ind + '\t', ind + '\t\t'
    w, h = pairs_size(cols or len(recipes), len(options))
    out = _box(w, h, ind, visible)
    for col, (i, tex) in enumerate(recipes):
        out += _head(col, tex, tip(i, 0), i1)
    for a, (key, tex) in enumerate(options, 1):
        y = PAIR_HEAD + (a - 1) * PAIR_ROW
        out += (f'{i1}icon = {{\n{i2}position = {{ 10 {y + 1} }}\n{i2}size = {{ 22 22 }}\n'
                f'{i2}texture = "{tex}"\n{i2}tooltip = "{key}"\n{i1}}}\n')
        for col, (i, _) in enumerate(recipes):
            best = f"And({eq(read(f'pmr_cbi_{b}'), i)}, {eq(read(f'pmr_cba_{b}'), a)})"
            out += _cell(col, y, tip(i, a), best, eq(read(f'pmr_cav_{i}_{a}_{b}'), 1), read(f'pmr_cp_{i}_{a}_{b}'), i1)
    return out + f'{ind}}}\n'
