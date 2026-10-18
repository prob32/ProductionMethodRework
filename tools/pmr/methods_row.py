"""The profit Methods row, shared by every window that shows what a building type's owners would run.

Pat, 2026-10-18 18:00Z: the financial district / manor house view in the Private tab first, the company window in the
Company Culture tab reusing the same row (one layout, one set of variables). A row is one building type: its icon, then
each recipe's icon with the profit per level a week under it, a gold square behind the most profitable recipe (the
pick), and a faded icon for a recipe that can't run here or is skipped for an input at the +75% price cap.

The row reads the profit calculation's interface variables (generate.py profit_effect) from whatever scope the caller
names, so the caller decides where the prices come from:
    pmr_rm_<i>_<b>     profit per level a week          pmr_rav_<i>_<b>    1 while recipe i can run
    pmr_rveto_<i>_<b>  1 while recipe i is skipped      pmr_pbest_<b>      the pick (recipe index, 0 if none)
read(name) returns the GUI expression for one of them, e.g. lambda n: f"GetPlayer.MakeScope.Var('{n}').GetValue" for
country copies, or f"<a state>.MakeScope.Var('{n}').GetValue" for a state's own.

    methods_row(bk, recipes, read, tip, ind, visible=None, width=ROW_W) -> GUI text
        recipes: [(recipe key, icon texture)], oldest first, as PMR numbers them
        tip(i):  the tooltip key of recipe i's icon (the caller writes the loc; recipe_tip_lines helps)

pairs_grid (below) is the recipe x automation grid beside it, for building types that fold automation.
"""

WHITE = 'gfx/interface/backgrounds/white.dds'
GOLD = '0.74 0.60 0.30 0.55'   # the Methods list's highlight (company_culture.py), here on the pick
ROW_W, ROW_H, CELL_W = 540, 70, 58


def gt(expr, n):
    return f"GreaterThan_CFixedPoint({expr}, '(CFixedPoint){n}')"


def eq(expr, n):
    return f"EqualTo_CFixedPoint({expr}, '(CFixedPoint){n}')"


def methods_row(bk, recipes, read, tip, ind, visible=None, width=ROW_W):
    b = bk[len('building_'):]
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    vis = f'{i1}visible = "[{visible}]"\n' if visible else ''
    out = (f'{ind}widget = {{\n{vis}{i1}size = {{ {width} {ROW_H} }}\n{i1}parentanchor = hcenter\n'
           f'{i1}background = {{\n{i1}\tusing = entry_bg\n{i1}}}\n'
           f'{i1}icon = {{\n{i2}position = {{ 6 0 }}\n{i2}parentanchor = vcenter\n{i2}size = {{ 54 54 }}\n'
           f'{i2}datacontext = "[GetBuildingType(\'{bk}\')]"\n{i2}texture = "[BuildingType.GetIcon]"\n'
           f'{i2}tooltipwidget = {{\n{i2}\tFancyTooltip_BuildingType = {{}}\n{i2}}}\n{i1}}}\n'
           f'{i1}flowcontainer = {{\n{i2}position = {{ 66 4 }}\n{i2}spacing = 2\n')
    for i, (key, tex) in enumerate(recipes, 1):
        pick = eq(read(f'pmr_pbest_{b}'), i)
        usable = f"And({eq(read(f'pmr_rav_{i}_{b}'), 1)}, Not({eq(read(f'pmr_rveto_{i}_{b}'), 1)}))"
        out += (f'{i2}widget = {{\n{i3}size = {{ {CELL_W} 62 }}\n{i3}tooltip = "{tip(i)}"\n'
                f'{i3}icon = {{\n{i3}\tvisible = "[{pick}]"\n{i3}\tposition = {{ 5 0 }}\n{i3}\tsize = {{ 48 48 }}\n'
                f'{i3}\ttexture = "{WHITE}"\n{i3}\tcolor = {{ {GOLD} }}\n{i3}\talwaystransparent = yes\n{i3}}}\n'
                f'{i3}icon = {{\n{i3}\tposition = {{ 9 4 }}\n{i3}\tsize = {{ 40 40 }}\n{i3}\ttexture = "{tex}"\n'
                f'{i3}\talpha = "[TransparentIfFalse({usable})]"\n{i3}\talwaystransparent = yes\n{i3}}}\n'
                f'{i3}textbox = {{\n{i3}\tposition = {{ 0 47 }}\n{i3}\tsize = {{ {CELL_W} 15 }}\n'
                f'{i3}\talign = hcenter|nobaseline\n{i3}\tusing = fontsize_small\n'
                f'{i3}\traw_text = "@money![{read(f"pmr_rm_{i}_{b}")}|0]"\n{i3}\talwaystransparent = yes\n{i3}}}\n'
                f'{i2}}}\n')
    return out + f'{i1}}}\n{ind}}}\n'


def type_icon(bk, ind):
    """The building type's icon alone, where a pairs_grid stands in for the row (the split: the pairs are the targets)."""
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


def pairs_size(n_recipes, n_options):
    return PAIR_LEFT + n_recipes * PAIR_COL + 10, PAIR_HEAD + n_options * PAIR_ROW + 6


def pairs_grid(bk, recipes, options, read, tip, ind, visible=None):
    """Pat, 2026-10-18 18:17Z: every recipe with every automation (PM1 + PM3), the same gold highlight on the most
    profitable pair. Columns are the plain recipes (recipes: [(index i, icon texture)]), rows the automation options
    (options: [(option tooltip key, icon texture)], a = 1 none). Reads generate.py pair_effect's interface:
        pmr_cp_<i>_<a>_<b>   profit per level a week     pmr_cav_<i>_<a>_<b>  1 while the pair could run
        pmr_cbi_<b>, pmr_cba_<b>  the most profitable runnable pair
    tip(i, a): the tooltip key of a cell."""
    b = bk[len('building_'):]
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    w, h = pairs_size(len(recipes), len(options))
    vis = f'{i1}visible = "[{visible}]"\n' if visible else ''
    out = f'{ind}widget = {{\n{vis}{i1}size = {{ {w} {h} }}\n{i1}background = {{\n{i1}\tusing = entry_bg\n{i1}}}\n'
    for col, (i, tex) in enumerate(recipes):
        out += (f'{i1}icon = {{\n{i2}position = {{ {PAIR_LEFT + col * PAIR_COL + 9} 5 }}\n{i2}size = {{ 40 40 }}\n'
                f'{i2}texture = "{tex}"\n{i2}tooltip = "{tip(i, 0)}"\n{i1}}}\n')
    for a, (key, tex) in enumerate(options, 1):
        y = PAIR_HEAD + (a - 1) * PAIR_ROW
        out += (f'{i1}icon = {{\n{i2}position = {{ 10 {y + 1} }}\n{i2}size = {{ 22 22 }}\n'
                f'{i2}texture = "{tex}"\n{i2}tooltip = "{key}"\n{i1}}}\n')
        for col, (i, _) in enumerate(recipes):
            best = f"And({eq(read(f'pmr_cbi_{b}'), i)}, {eq(read(f'pmr_cba_{b}'), a)})"
            out += (f'{i1}widget = {{\n{i2}position = {{ {PAIR_LEFT + col * PAIR_COL} {y} }}\n'
                    f'{i2}size = {{ {PAIR_COL} {PAIR_ROW} }}\n{i2}tooltip = "{tip(i, a)}"\n'
                    f'{i2}icon = {{\n{i3}visible = "[{best}]"\n{i3}position = {{ 2 1 }}\n'
                    f'{i3}size = {{ {PAIR_COL - 4} {PAIR_ROW - 2} }}\n{i3}texture = "{WHITE}"\n'
                    f'{i3}color = {{ {GOLD} }}\n{i3}alwaystransparent = yes\n{i2}}}\n'
                    f'{i2}textbox = {{\n{i3}size = {{ {PAIR_COL} {PAIR_ROW} }}\n{i3}align = hcenter|vcenter|nobaseline\n'
                    f'{i3}using = fontsize_small\n'
                    f'{i3}alpha = "[TransparentIfFalse({eq(read(f"pmr_cav_{i}_{a}_{b}"), 1)})]"\n'
                    f'{i3}raw_text = "@money![{read(f"pmr_cp_{i}_{a}_{b}")}|0]"\n{i3}alwaystransparent = yes\n{i2}}}\n'
                    f'{i1}}}\n')
    return out + f'{ind}}}\n'
