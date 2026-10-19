"""The company panels (Pat, 2026-10-19 02:32Z): the retool sites off their industry lists, and the Company Culture tab's
Methods table.

Retool sites (Pat 02:32Z: "Can you hid[e] the re-tooling buildings from here while still making them available"):
generate.py lists each treated type's private retool sites in the building_types of every company listing the type
(COMPANY_RETOOL), so a company can own its buildings' retooling, and every list of a company's industries showed each
industry twice. The sites stay in building_types; the lists hide them. No 1.14.5 GUI file reads a building group off a
building type, so the test is vanilla's own type test, ObjectsEqual against each site type a company lists
(RETOOL_TYPES), and the lists skip invisible items (ignoreinvisible, as generate.hide_retool_sites's urban grid):
    company_panel.gui    Available Industries
    companies_panel.gui  the companies list's industry icons, each company type's Available Industries, and
                         company_building_item, the company tooltip's industry icons (custom_tooltip.gui)

Methods table (Pat 02:32Z: "can you make the methods including the company special ones show the same table only for
buildings the companies own from the policies tab?"): in place of the tab's Methods list, the Policies card's grid
(methods_row.recipes_grid and pairs_grid on the player's country copies, generate.mv_read) for each building type the
company owns levels of (BuildingType.GetNumLevelsOwnedByCompanyRaw, as companies_panel.gui reads it), each followed,
for a goods line of the company's Engineering arm, by its three works methods with their profit per level a week
(pmr_cwp_<t>_<b> on the player's country), the tier the company runs in gold. A row is built only for a type shown
(the DataModelRepeatedItem gate of generate.gate_type_copies). The figures are the Policies tab's: opening a company
panel recounts them as the tab's click does, unless the tab or a company panel did so today (TODAY, perf review G4).
"""
import re

import cc_icons
import methods_row

RETOOL_TYPES = []   # set by generate.py: every retool site type a company lists (report['company_types'])
REFRESH = False     # set by write_methods: the company panel's opening recounts the Policies copies (test build)
REFRESH_SGUI = 'pmr_cm_refresh_sgui'
TODAY = 'pmr_mv_today'   # country, a day long: the Policies copies were recounted today
OWN_GUI = 'gui/pmr_company_methods.gui'
CARD_W, CARD_PAD, ICON_GAP, GRID_GAP = 540, 8, 8, 6   # as the Policies cards (generate.methods_view_gui)
OPTION = 22          # the company's icon in the works row's option column, as pairs_grid's option icons


def fail(where, msg):
    raise SystemExit(f'company_panel: {where}: {msg}')


def short(bk):
    return bk[len('building_'):]


def any_of(exprs):
    """Or() over exprs, nested as a balanced tree so a long list stays shallow."""
    if len(exprs) == 1:
        return exprs[0]
    mid = len(exprs) // 2
    return f'Or({any_of(exprs[:mid])}, {any_of(exprs[mid:])})'


def not_site():
    """BuildingType context: not one of the retool sites a company lists."""
    return 'Not(' + any_of([f"ObjectsEqual(BuildingType.Self, GetBuildingType('{t}').Self)" for t in RETOOL_TYPES]) + ')'


MODEL = 'datamodel = "[Company.GetBuildingTypes]"\n'


def hide_sites(text, where, lists):
    """Each list of Company.GetBuildingTypes in text (lists of them) skips invisible items, and its item's widget is
    invisible for a retool site."""
    found = list(re.finditer(r'^(\t*)' + re.escape(MODEL), text, re.M))
    if len(found) != lists:
        fail(where, f'expected {lists} lists of Company.GetBuildingTypes, found {len(found)}; update hide_sites')
    if not RETOOL_TYPES:
        return text
    vis = f'visible = "[{not_site()}]"  # PMR: no retool sites (company_panel.py)\n'
    for m in reversed(found):
        ind = m.group(1)
        opener = f'\n{ind}item = {{\n'
        head = text.find(opener, m.end())
        if head < 0:
            fail(where, 'a list of Company.GetBuildingTypes without its item; update hide_sites')
        widget = head + len(opener)   # the item's widget: its first line
        if not re.match(rf'{ind}\t\w+ = {{\n', text[widget:]):
            fail(where, 'an industry item that does not open with its widget; update hide_sites')
        at = text.index('\n', widget) + 1
        text = text[:at] + f'{ind}\t\t{vis}' + text[at:]
        text = text[:m.end()] + f'{ind}ignoreinvisible = yes  # PMR\n' + text[m.end():]
    return text


def patch_company_panel(text):
    """company_panel.gui: Available Industries without the retool sites; with the Methods table, the panel's opening
    recounts its figures (REFRESH_SGUI)."""
    where = 'company_panel.gui'
    text = hide_sites(text, where, 1)
    if not REFRESH:
        return text
    show = '\t\tblockoverride "animation_state_block" {\n\t\t\tstate = {\n\t\t\t\tname = _show\n'
    if text.count(show) != 1:
        fail(where, 'the panel\'s _show state moved; update patch_company_panel')
    run = f"GetScriptedGui('{REFRESH_SGUI}').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).End)"
    return text.replace(show, show + f'\t\t\t\ton_start = "[{run}]"  # PMR: the Methods table\'s figures\n')


def patch_companies_panel(text):
    """companies_panel.gui: the companies list's and the company types' industries, and the company tooltip's
    (company_building_item), without the retool sites."""
    where = 'companies_panel.gui'
    text = hide_sites(text, where, 2)
    item = '\ttype company_building_item = button {\n'
    if text.count(item) != 1:
        fail(where, 'company_building_item moved; update patch_companies_panel')
    if RETOOL_TYPES:
        text = text.replace(item, item + f'\t\tvisible = "[{not_site()}]"  # PMR: no retool sites (company_panel.py)\n')
    return text


# ---------------------------------------------------------------------------------------------------------------
# The Methods table

def V(name):
    """The executive's mirror of a company variable (company_culture.MIRRORED); the tab's context is the executive."""
    return f"Character.MakeScope.Var('{name}').GetValue"


def owned(bk, read):
    """The company owns levels of bk and the player's country has its Policies card (pmr_mv_lv_<b>)."""
    return (f"And(GreaterThan_int32(GetBuildingType('{bk}').GetNumLevelsOwnedByCompanyRaw(Company.Self), '(int32)0'), "
            f"{methods_row.gt(read(f'pmr_mv_lv_{short(bk)}'), 0)})")


def on_line(idx):
    """The company's goods line 1 or 2 is the works building with index idx, as (line, test) pairs."""
    return [(n, methods_row.eq(V(f'pmr_cc_k_g{n}b'), idx)) for n in (1, 2)]


def gate(cond, row, ind):
    """A list with one item, row, while cond holds, else none: the row is built only while shown."""
    return (f'{ind}flowcontainer = {{\n{ind}\tvisible = "[{cond}]"\n'
            f"{ind}\tdatamodel = \"[DataModelRepeatedItem(Select_int32({cond}, '(int32)1', '(int32)0'))]\"\n"
            f'{ind}\titem = {{\n{ind}\t\t{row} = {{}}\n{ind}\t}}\n{ind}}}\n')


def card(name, grid_h, body):
    """A row as the Policies card: the building's icon and its grid box (body), on entry_bg_simple."""
    h = max(methods_row.ROW_H, grid_h) + 2 * CARD_PAD
    return (f'\ttype {name} = widget {{\n\t\tsize = {{ {CARD_W} {h} }}\n'
            '\t\tbackground = {\n\t\t\tusing = entry_bg_simple\n\t\t}\n'
            f'\t\tflowcontainer = {{\n\t\t\tposition = {{ {CARD_PAD} {CARD_PAD} }}\n\t\t\tspacing = {ICON_GAP}\n'
            + body + '\t\t}\n\t}\n\n')


def type_card(bk, keys, tex, pair, pair_options, read, cols):
    """The Policies card's grid of bk (generate.methods_view_gui): one row of recipes, or the recipe x automation pairs
    where the type has them, both where it has pairs but no split, with the same tooltips."""
    b = short(bk)
    ind = '\t\t\t\t'
    grid, gh = '', 0
    if not (pair and pair.get('split')):
        grid = methods_row.recipes_grid(bk, list(enumerate(tex, 1)), read, lambda i: f'PMR_MV_TIP_{b}_{i}', ind, cols=cols)
        gh = methods_row.pairs_size(cols, 1)[1]
    if pair:
        names = pair.get('keys') or keys
        grid += methods_row.pairs_grid(
            bk, [(i, tex[i - 1]) for i in pair['recipes']], pair_options(bk, pair), read,
            lambda i, a: f'PMR_MVP_TIP_{b}_{i}_{a}' if a else f'{names[i - 1]}', ind, cols=cols)
        gh += (GRID_GAP if gh else 0) + methods_row.pairs_size(cols, len(pair['options']))[1]
    return card(f'pmr_cm_{b}', gh, methods_row.type_icon(bk, '\t\t\t')
                + f'\t\t\tflowcontainer = {{\n\t\t\t\tdirection = vertical\n\t\t\t\tspacing = {GRID_GAP}\n{grid}\t\t\t}}\n')


def works_card(bk, w, read, cols):
    """The company's works methods of bk (company_culture.py's goods lines): pairs_grid's box with one row, a column per
    tier: the method's picture over its profit per level a week (pmr_cwp_<t>_<b>), the tier the company runs in gold,
    faded until it has it. The option column holds the company's icon."""
    b = short(bk)
    lines = on_line(w['idx'])
    ind, i1, i2, i3 = '\t\t\t', '\t\t\t\t', '\t\t\t\t\t', '\t\t\t\t\t\t'
    bw, bh = methods_row.pairs_size(cols, 1)
    y = methods_row.PAIR_HEAD
    box = (f'{ind}widget = {{\n{i1}size = {{ {bw} {bh} }}\n{i1}background = {{\n{i2}using = entry_bg\n{i1}}}\n'
           f'{i1}icon = {{\n{i2}position = {{ 9 {y + 1} }}\n{i2}size = {{ {OPTION} {OPTION} }}\n'
           f'{i2}texture = "[Company.GetCompanyType.GetIcon]"\n{i1}}}\n')
    for t in (1, 2, 3):
        x = methods_row.PAIR_LEFT + (t - 1) * methods_row.PAIR_COL
        tip = f'PMR_CM_W_{b}_{t}'
        runs = 'Or(' + ', '.join(f"And({on}, {methods_row.eq(V(f'pmr_cc_g{n}'), t)})" for n, on in lines) + ')'
        has = 'Or(' + ', '.join(f"And({on}, {methods_row.gt(V(f'pmr_cc_g{n}'), t - 1)})" for n, on in lines) + ')'
        box += (f'{i1}icon = {{\n{i2}position = {{ {x + 9} 5 }}\n{i2}size = {{ 40 40 }}\n'
                f'{i2}texture = "{cc_icons.ENG_ICONS[w["row"] - 1][t - 1]}"\n{i2}tooltip = "{tip}"\n{i1}}}\n'
                f'{i1}widget = {{\n{i2}position = {{ {x} {y} }}\n'
                f'{i2}size = {{ {methods_row.PAIR_COL} {methods_row.PAIR_ROW} }}\n{i2}tooltip = "{tip}"\n'
                f'{i2}icon = {{\n{i3}visible = "[{runs}]"\n{i3}position = {{ 2 1 }}\n'
                f'{i3}size = {{ {methods_row.PAIR_COL - 4} {methods_row.PAIR_ROW - 2} }}\n'
                f'{i3}texture = "{methods_row.WHITE}"\n{i3}color = {{ {methods_row.GOLD} }}\n{i3}alwaystransparent = yes\n{i2}}}\n'
                f'{i2}textbox = {{\n{i3}size = {{ {methods_row.PAIR_COL} {methods_row.PAIR_ROW} }}\n'
                f'{i3}align = hcenter|vcenter|nobaseline\n{i3}using = fontsize_small\n'
                f'{i3}alpha = "[TransparentIfFalse({has})]"\n'
                f"{i3}raw_text = \"@money![{read(f'pmr_cwp_{t}_{b}')}|0]\"\n{i3}alwaystransparent = yes\n{i2}}}\n{i1}}}\n")
    return card(f'pmr_cm_works_{b}', bh, methods_row.type_icon(bk, ind) + box + f'{ind}}}\n')


def methods_gui(recipe_keys, recipe_tex, pair_ui, pair_options, read, cols, works):
    """The tab's Methods table, pmr_cc_methods. recipe_keys, recipe_tex and pair_ui as generate.methods_view_gui (the
    Policies tab's types), pair_options and read (mv_read) its helpers, cols its boxes' width in columns (mv_cols);
    works: company_culture.Plan.works. Shown for the player's own companies only: the figures are its country's."""
    ind = '\t\t'
    rows, gates = '', ''
    for bk, keys in recipe_keys.items():
        rows += type_card(bk, keys, recipe_tex[bk], pair_ui.get(bk), pair_options, read, cols)
        gates += gate(owned(bk, read), f'pmr_cm_{short(bk)}', ind)
        if bk in works:
            gates += gate(any_of([on for _n, on in on_line(works[bk]['idx'])]), f'pmr_cm_works_{short(bk)}', ind)
    for bk in [bk for bk in sorted(works) if bk not in recipe_keys]:
        gates += gate(any_of([on for _n, on in on_line(works[bk]['idx'])]), f'pmr_cm_works_{short(bk)}', ind)
    rows += ''.join(works_card(bk, w, read, cols) for bk, w in sorted(works.items()))
    return ('# GENERATED by tools/pmr/company_panel.py. The company panel\'s Company Culture tab: the Methods table, the\n'
            '# Policies tab\'s grid for each building type the company owns levels of and its works methods; grids by\n'
            '# tools/pmr/methods_row.py.\n'
            'types pmr_company_methods {\n'
            '\ttype pmr_cc_methods = flowcontainer {\n\t\tvisible = "[Company.GetCountry.IsLocalPlayer]"\n'
            '\t\tparentanchor = hcenter\n\t\tdirection = vertical\n\t\tspacing = 4\n'
            '\t\tdefault_header = {\n\t\t\tblockoverride "text" {\n\t\t\t\ttext = "PMR_CC_METHODS_HEADER"\n\t\t\t}\n\t\t}\n'
            + gates + '\t}\n\n' + rows + '}\n')


def sguis():
    return ('# The company panel\'s Methods table (company_panel.py) reads the Policies tab\'s country copies. Opening a\n'
            '# company panel recounts them as the tab\'s click does (pmr_mv_refresh_sgui), at most once a day: not while\n'
            f'# {TODAY} is set, which both set for a day (perf review G4). Country scope (the player).\n'
            f'{REFRESH_SGUI} = {{\n\tscope = country\n\teffect = {{\n\t\tif = {{\n'
            f'\t\t\tlimit = {{ NOT = {{ has_variable = {TODAY} }} }}\n'
            '\t\t\tpmr_pf_all = yes\n\t\t\tpmr_mv_refresh = yes\n'
            f'\t\t\tset_variable = {{ name = {TODAY} value = yes days = 1 }}\n'
            '\t\t\tdebug_log = "PMR;rec=CM_REFRESH;date=[TimeKeeper.GetCurrentDate.GetString]"\n'
            '\t\t}\n\t}\n}\n')


def localization(works, read):
    loc = []
    for bk, w in sorted(works.items()):
        b = short(bk)
        loc += [f' PMR_CM_W_{b}_{t}:0 "#bold $PMR_CC_ENG_{w["row"]}_{t}$#!\\n'
                f"@money![{read(f'pmr_cwp_{t}_{b}')}|0] per level a week\"" for t in (1, 2, 3)]
    return loc


def write_methods(write, header_text, recipe_keys, recipe_tex, pair_ui, pair_options, read, cols, works):
    """Test builds (Company Culture's tab): writes the table and, with Policies types to show, the refresh the panel's
    opening runs (REFRESH, patch_company_panel). Returns its loc lines."""
    global REFRESH
    REFRESH = bool(recipe_keys)
    write(OWN_GUI, methods_gui(recipe_keys, recipe_tex, pair_ui, pair_options, read, cols, works), bom=False)
    if REFRESH:
        write('common/scripted_guis/pmr_cm_sguis.txt', header_text + sguis())
    return localization(works, read)
