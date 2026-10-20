"""The company panels (Pat, 2026-10-19 02:32Z): the retool sites off their industry lists, and the Company Culture tab's
Methods table.

Retool sites (Pat 02:32Z: "Can you hid[e] the re-tooling buildings from here while still making them available"):
generate.py lists each treated type's private retool sites in the building_types of every company listing the type
(COMPANY_RETOOL), so a company can own its buildings' retooling, and every list of a company's industries showed each
industry twice. The sites stay in building_types; the lists hide them. No 1.14.5 GUI file reads a building group off a
building type. Until q45 the test was ObjectsEqual against each of the ~90 site types, per icon and per frame, which
slowed the Companies panel (Pat 15:52Z); now each panel's opening marks every site type a company lists (RETOOL_TYPES)
as a GUI variable of its own key (site_flags), and an icon tests one: GetVariableSystem.Exists(BuildingType.GetKey)
(vanilla reads BuildingType.GetKey as a string, map_markers.gui). The lists skip invisible items (ignoreinvisible, as
generate.hide_retool_sites's urban grid):
    company_panel.gui    Available Industries
    companies_panel.gui  the companies list's industry icons; each company type's industries, its charter
                         industries and the industry filter (Pat 15:52Z); company_building_item and
                         company_type_building_item, the tooltips' industry icons

Methods table (Pat 02:32Z: "can you make the methods including the company special ones show the same table only for
buildings the companies own from the policies tab?"): in place of the tab's Methods list, the Policies card's grid
(methods_row.recipes_grid and pairs_grid on the player's country copies, generate.mv_read) for each building type the
company owns levels of (BuildingType.GetNumLevelsOwnedByCompanyRaw, as companies_panel.gui reads it). The works
methods' rows went with the special methods (Pat 2026-10-19 14:43Z). A row is built only for a type shown (the
DataModelRepeatedItem gate of generate.gate_type_copies). The figures are the Policies tab's: opening a company
panel recounts them as the tab's click does, unless the tab or a company panel did so today (TODAY, perf review G4).
"""
import re

import methods_row

RETOOL_TYPES = []   # set by generate.py: every retool site type a company lists (report['company_types'])
SUB_LINKS = False   # set by generate.py in test builds: the Regional HQs subsidiary probe (pmr/test_probes/sub_hq)
REFRESH = False     # set by write_methods: the company panel's opening recounts the Policies copies
REFRESH_SGUI = 'pmr_cm_refresh_sgui'
TODAY = 'pmr_mv_today'   # country, a day long: the Policies copies were recounted today
OWN_GUI = 'gui/pmr_company_methods.gui'
CARD_W, CARD_PAD, ICON_GAP, GRID_GAP = 540, 8, 8, 6   # as the Policies cards (generate.methods_view_gui)


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
    """BuildingType context: not one of the retool sites a company lists (site_flags marked them)."""
    return 'Not(GetVariableSystem.Exists(BuildingType.GetKey))'


def site_flags(ind):
    """A panel's _show on_start lines: every retool site type a company lists, a GUI variable of its own key."""
    return ''.join(f"{ind}on_start = \"[GetVariableSystem.Set('{t}', 'yes')]\"  # PMR: a retool site\n" for t in RETOOL_TYPES)


MODEL = 'datamodel = "[Company.GetBuildingTypes]"\n'
TYPE_MODELS = ['datamodel = "[CompanyType.AccessBuildingTypes(GetPlayer.Self)]"\n',
               'datamodel = "[CompanyType.GetPotentialBuildingTypes(GetPlayer.Self)]"\n',
               'datamodel = "[CompaniesPanel.GetAllBuildingTypes]"\n']


def hide_sites(text, where, lists, models=(MODEL,)):
    """Each list of one of models in text (lists of them in all) skips invisible items, and its item's widget is
    invisible for a retool site."""
    found = sorted((m for model in models for m in re.finditer(r'^(\t*)' + re.escape(model), text, re.M)),
                   key=lambda m: m.start())
    if len(found) != lists:
        fail(where, f'expected {lists} lists of building types, found {len(found)}; update hide_sites')
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


# Subsidiaries (Pat, 2026-10-19 12:54Z: "I only would want a subsidiary IF it was listed under regional HQ of a parent
# COMPANY"). Script keeps them as a variable list pmr_subs on the parent company and a copy on its executive, and
# pmr_sub = 1 on the subsidiary (pmr/test_probes/sub_hq). The parent's Regional HQs column lists them, from the company's
# own list, else (no flag) from its executive's, the route the Company Culture tab reads; the Companies panel's lists
# skip them.
SUBS = "Company.MakeScope.GetList('pmr_subs')"
EXEC_SUBS = "Company.GetExecutive.MakeScope.GetList('pmr_subs')"
NOT_SUB = "Not(GreaterThan_CFixedPoint(Company.MakeScope.Var('pmr_sub').GetValue, '(CFixedPoint)0'))"


def sub_list(model, visible, flag, ind):
    """A Regional HQs column list of model's companies, as vanilla's regional HQ rows (company_panel.gui)."""
    i = [ind + '\t' * n for n in range(9)]
    flag_w = (f'{i[4]}tiny_flag_no_interact = {{\n{i[5]}parentanchor = vcenter\n{i[5]}position = {{ 10 0 }}\n'
              f'{i[5]}datacontext = "[Company.GetCountry]"\n{i[4]}}}\n') if flag else ''
    return (f'{i[0]}flowcontainer = {{  # PMR: subsidiaries (company_panel.py, test build)\n'
            + (f'{i[1]}visible = "[{visible}]"\n' if visible else '')
            + f'{i[1]}direction = vertical\n{i[1]}spacing = 5\n{i[1]}datamodel = "[{model}]"\n'
            f'{i[1]}item = {{\n{i[2]}widget = {{\n{i[3]}size = {{ 250 40 }}\n{i[3]}datacontext = "[Scope.GetCompany]"\n'
            f'{i[3]}button = {{\n{i[4]}size = {{ 250 40 }}\n{i[4]}using = default_button\n'
            f'{i[4]}onclick = "[InformationPanelBar.OpenCompanyPanel(Company.Self)]"\n{i[4]}tooltip = "GO_TO_BUTTON_COMPANY"\n'
            + flag_w +
            f'{i[4]}textbox = {{\n{i[5]}parentanchor = vcenter\n{i[5]}margin_left = {50 if flag else 10}\n'
            f'{i[5]}autoresize = yes\n{i[5]}align = nobaseline\n{i[5]}elide = right\n{i[5]}fontsize_min = 14\n'
            f'{i[5]}max_width = {190 if flag else 230}\n{i[5]}text = "[Company.GetName]"\n{i[4]}}}\n'
            f'{i[3]}}}\n{i[2]}}}\n{i[1]}}}\n{i[0]}}}\n')


def sub_regional_hqs(text, where):
    """The parent's Regional HQs column lists its subsidiaries before its regional HQs; its empty state counts them."""
    empty = '\t\t\t\t\tvisible = "[IsDataModelEmpty(Company.GetRegionalHQs)]"\n'
    hqs = '\t\t\t\t### REGIONAL HQS\n'
    if text.count(empty) != 1 or text.count(hqs) != 1:
        fail(where, 'the Regional HQs column moved; update sub_regional_hqs')
    text = text.replace(empty, '\t\t\t\t\tvisible = "[And(IsDataModelEmpty(Company.GetRegionalHQs), '
                        f'And(IsDataModelEmpty({SUBS}), IsDataModelEmpty({EXEC_SUBS})))]"  # PMR: subsidiaries\n')
    return text.replace(hqs, sub_list(SUBS, '', True, '\t\t\t\t')
                        + sub_list(EXEC_SUBS, f'IsDataModelEmpty({SUBS})', False, '\t\t\t\t') + hqs)


def sub_assets(text, where):
    """Pat 2026-10-19 14:10Z ("It doesn't look like the regional subsidiary is listed as under the company hq"): the
    Assets tab lists each subsidiary's HQ with its buildings, as vanilla's company_hq_assets_item, after the company's
    own HQ."""
    hqs = '\t\t### REGIONAL HQs\n\t\tflowcontainer = {\n'
    if text.count(hqs) != 1:
        fail(where, 'the Assets tab\'s Regional HQs moved; update sub_assets')
    block = ('\t\t### PMR: subsidiaries under the company HQ (company_panel.py, test build)\n\t\tflowcontainer = {\n'
             '\t\t\tusing = default_list_position\n\t\t\tdirection = vertical\n'
             f'\t\t\tdatamodel = "[{SUBS}]"\n\t\t\titem = {{\n\t\t\t\tflowcontainer = {{\n'
             '\t\t\t\t\tdirection = vertical\n\t\t\t\t\tdatacontext = "[Scope.GetCompany]"\n'
             '\t\t\t\t\tcompany_hq_assets_item = {\n\t\t\t\t\t\tdatacontext = "[Company.GetBuilding]"\n'
             '\t\t\t\t\t\tblockoverride "header_text" {\n\t\t\t\t\t\t\ttext = "PMR_SUB_HQ_HEADER"\n'
             '\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\n')
    return text.replace(hqs, block + hqs)


def patch_company_panel(text):
    """company_panel.gui: Available Industries without the retool sites; with the Methods table, the panel's opening
    recounts its figures (REFRESH_SGUI); in test builds, the parent's subsidiaries under its Regional HQs."""
    where = 'company_panel.gui'
    text = hide_sites(text, where, 1)
    show = '\t\tblockoverride "animation_state_block" {\n\t\t\tstate = {\n\t\t\t\tname = _show\n'
    if text.count(show) != 1:
        fail(where, 'the panel\'s _show state moved; update patch_company_panel')
    text = text.replace(show, show + site_flags('\t\t\t\t'))
    if SUB_LINKS:
        text = sub_assets(sub_regional_hqs(text, where), where)
    if not REFRESH:
        return text
    run = f"GetScriptedGui('{REFRESH_SGUI}').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).End)"
    return text.replace(show, show + f'\t\t\t\ton_start = "[{run}]"  # PMR: the Methods table\'s figures\n')


def patch_companies_panel(text):
    """companies_panel.gui: the companies list's and the company types' industries, and the company tooltip's
    (company_building_item), without the retool sites."""
    where = 'companies_panel.gui'
    text = hide_sites(text, where, 5, [MODEL] + TYPE_MODELS)
    show = '\t\t\t\tname = _show\n\t\t\t\ton_start = "[GetVariableSystem.Clear(\'hide_current_companies\')]"\n'
    if text.count(show) != 1:
        fail(where, 'the panel\'s _show state moved; update patch_companies_panel')
    text = text.replace(show, show + site_flags('\t\t\t\t'))
    for item in ('\ttype company_building_item = button {\n', '\ttype company_type_building_item = button {\n'):
        if text.count(item) != 1:
            fail(where, f'{item.strip()} moved; update patch_companies_panel')
        if RETOOL_TYPES:
            text = text.replace(item, item + f'\t\tvisible = "[{not_site()}]"  # PMR: no retool sites (company_panel.py)\n')
    if SUB_LINKS:   # the player's companies and every company, without subsidiaries
        mine = ('\t\t\t\t\t\tdatamodel = "[AccessPlayer.GetCompanies]"\n',
                '\t\t\t\t\t\titem = {\n\t\t\t\t\t\t\tcompany_item = {}\n')
        every = ('\t\t\t\t\tdatamodel = "[CompaniesPanel.GetCompanies]"\n',
                 '\t\t\t\t\titem = {\n\t\t\t\t\t\tflowcontainer = {\n')
        for model, head in (mine, every):
            if text.count(model) != 1 or text.count(head) != 1:
                fail(where, 'a companies list moved; update patch_companies_panel')
            text = text.replace(model, model + model[:model.index('d')] + 'ignoreinvisible = yes  # PMR: subsidiaries\n')
        text = text.replace(mine[1], mine[1].replace('company_item = {}', f'company_item = {{ visible = "[{NOT_SUB}]" }}'))
        text = text.replace(every[1], every[1] + f'\t\t\t\t\t\t\tvisible = "[{NOT_SUB}]"  # PMR: subsidiaries\n')
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


def gate(cond, row, ind):
    """A list with one item, row, while cond holds, else none: the row is built only while shown."""
    return (f'{ind}flowcontainer = {{\n{ind}\tvisible = "[{cond}]"\n'
            f"{ind}\tdatamodel = \"[DataModelRepeatedItem(Select_int32({cond}, '(int32)1', '(int32)0'))]\"\n"
            f'{ind}\titem = {{\n{ind}\t\t{row} = {{}}\n{ind}\t}}\n{ind}}}\n')


def card(name, grid_h, body):
    """A row as the Policies card: the building's icon and its grid box (body), on entry_bg_simple."""
    # Pat 2026-10-19 13:27Z: the card takes the height of what its grid shows (pairs_grid hides empty rows), CARD_PAD
    # round it, at least the icon's
    h = max(methods_row.ROW_H, grid_h) + 2 * CARD_PAD
    return (f'\ttype {name} = widget {{\n\t\tsize = {{ {CARD_W} {h} }}\n'
            '\t\tbackground = {\n\t\t\tusing = entry_bg_simple\n\t\t}\n'
            '\t\tflowcontainer = {\n\t\t\tresizeparent = yes\n\t\t\tdirection = vertical\n'
            f'\t\t\twidget = {{ size = {{ {CARD_W} {CARD_PAD} }} }}\n'
            f'\t\t\tflowcontainer = {{\n\t\t\t\tspacing = {ICON_GAP}\n'
            f'\t\t\t\twidget = {{ size = {{ {CARD_PAD - ICON_GAP} 0 }} }}\n'
            + body + f'\t\t\t}}\n\t\t\twidget = {{ size = {{ {CARD_W} {CARD_PAD} }} }}\n\t\t}}\n\t}}\n\n')


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


def methods_gui(recipe_keys, recipe_tex, pair_ui, pair_options, read, cols):
    """The tab's Methods table, pmr_cc_methods. recipe_keys, recipe_tex and pair_ui as generate.methods_view_gui (the
    Policies tab's types), pair_options and read (mv_read) its helpers, cols its boxes' width in columns (mv_cols).
    Shown for the player's own companies only: the figures are its country's."""
    ind = '\t\t'
    rows, gates = '', ''
    for bk, keys in recipe_keys.items():
        rows += type_card(bk, keys, recipe_tex[bk], pair_ui.get(bk), pair_options, read, cols)
        gates += gate(owned(bk, read), f'pmr_cm_{short(bk)}', ind)
    return ('# GENERATED by tools/pmr/company_panel.py. The company panel\'s Company Culture tab: the Methods table, the\n'
            '# Policies tab\'s grid for each building type the company owns levels of; grids by tools/pmr/methods_row.py.\n'
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


def write_methods(write, header_text, recipe_keys, recipe_tex, pair_ui, pair_options, read, cols):
    """Test builds (Company Culture's tab): writes the table and, with Policies types to show, the refresh the panel's
    opening runs (REFRESH, patch_company_panel). Returns its loc lines."""
    global REFRESH
    REFRESH = bool(recipe_keys)
    write(OWN_GUI, methods_gui(recipe_keys, recipe_tex, pair_ui, pair_options, read, cols), bom=False)
    if REFRESH:
        write('common/scripted_guis/pmr_cm_sguis.txt', header_text + sguis())
    return []
