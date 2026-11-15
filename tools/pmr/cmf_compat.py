"""Community Mod Framework (CMF, Workshop 3385002128) alongside PMR (issue #14, Pat 2026-11-15 15:03Z).

The game keeps the FIRST definition of a GUI type it loads, and it loads gui/ files in name order across vanilla and
every mod. CMF overrides ten vanilla types from files named 00_MPM_*.gui and 00_com_gui_state_buildings.gui, so they
load before vanilla's file names, which are the names PMR writes its whole-file copies under. With CMF on, CMF's
near-vanilla copies of those types win and PMR's building browser, methods, building card and state Buildings tab
changes are silently dropped.

apply() moves the PMR copies of those types, unchanged, into files named 00_00_pmr_<source>.gui, which sort before
CMF's (and before vanilla's). Each new file carries its source file's @constants, because GUI constants are local to a
file. A type is defined once either way, so without CMF nothing changes: the same text, in another file.

CMF's two state-panel hooks (com_owner_building_header_list, com_owner_building_list) go into PMR's copy of
state_panel_buildings_content, where CMF's copy has them, so mods that list buildings through CMF still show in the
Buildings tab. Without CMF those types are taken from pmr_cmf_fallback_types.gui, an exact copy of CMF's, which sorts
after CMF's file: with CMF on, CMF's own definition is the one used. Their global list is empty without CMF, so they
stay hidden.

Call apply(out_dir) once every gui file has been written. It raises SystemExit if a type or an anchor moved.
"""
import os
import re

# (type, the vanilla-named file PMR writes it in). Types PMR changes, plus condensed_building_information_pms, which
# PMR keeps as vanilla but CMF cuts to the first four method groups (DataModelFirst(..., 4)) for its own second row.
FIRST_TYPES = (
    ('building_browser_building_item', 'building_browser_panel.gui'),
    ('building_browser_building_type_item', 'building_browser_panel.gui'),
    ('buildings_production_method_item', 'production_methods.gui'),
    ('old_buildings_production_method_item', 'production_methods.gui'),
    ('condensed_building_information', 'building_details_panel.gui'),
    ('condensed_building_information_pms', 'building_details_panel.gui'),
    ('construction_interaction_item_full', 'map_list_panel.gui'),
    ('goods_state_panel_input_output_item', 'goods_state_panel.gui'),
    ('state_panel_buildings_content', 'states_panel_buildings.gui'),
)
# CMF also overrides state_panel_buildings_fixed_bottom (its local goods grid). PMR keeps that type as vanilla, so
# CMF's copy is left to win.

PREFIX = '00_00_pmr_'
FALLBACK = 'pmr_cmf_fallback_types.gui'

# CMF 1.67.6, gui/00_com_gui_state_buildings.gui, verbatim (indentation only)
FALLBACK_TEXT = '''# PMR: Community Mod Framework's state Buildings tab hooks, copied from its gui/00_com_gui_state_buildings.gui
# (1.67.6) for when CMF is not loaded. This file sorts after CMF's, so with CMF on its own definitions are used.
# The list they read is CMF's and is empty without it, so they stay hidden.

types pmr_cmf_fallback_types {
	type com_owner_building_header_list = container {
		visible = "[DataModelHasItems(GetGlobalList('com_custom_owner_buildings'))]"
		datamodel = "[GetGlobalList('com_custom_owner_buildings')]"

		item = {
			container = {
				datacontext = "[StatesPanel.AccessBuilding(Scope.GetBuildingType.GetKey)]"
				divider_clean = {
					visible = "[GreaterThan_int32(Building.GetExpansionLevel, '(int32)0')]"
				}

				header_building_item = {
					visible = "[GreaterThan_int32(Building.GetExpansionLevel, '(int32)0')]"

					tooltipwidget = {
						FancyTooltip_Building = {}
					}

					blockoverride "text" {
						text = com_gui_total_building
					}
				}
			}
		}
	}

	type com_owner_building_list = container {
		visible = "[DataModelHasItems(GetGlobalList('com_custom_owner_buildings'))]"
		datamodel = "[GetGlobalList('com_custom_owner_buildings')]"

		item = {
			container = {
				datacontext = "[StatesPanel.AccessBuilding(Scope.GetBuildingType.GetKey)]"
				buildings_list_item = {
					visible = "[GreaterThan_int32(Building.GetExpansionLevel, '(int32)0')]"
				}
			}
		}
	}
}
'''

# Where CMF's copy of state_panel_buildings_content has its hooks, as anchors in PMR's copy (each must occur once)
HOOKS = (
    ('\t\t\t\tdivider_clean = {}\n\t\t\t}\n\n\t\t\t### URBAN BUILDINGS',
     '\t\t\t\tcom_owner_building_header_list = {}  # PMR: CMF hook (cmf_compat.py)\n\n'),
    ("\t\t\t\tdatacontext = \"[StatesPanel.AccessBuilding('building_financial_district')]\"\n\t\t\t}\n\n"
     "\t\t\tbuildings_list = {\n\t\t\t\tblockoverride \"datamodel\" {\n"
     "\t\t\t\t\tdatamodel = \"[State.AccessUrbanBuildings]\"",
     None),   # inserted after the item, before buildings_list
)
HOOK2 = '\t\t\tcom_owner_building_list = {}  # PMR: CMF hook (cmf_compat.py)\n\n'

CONST = re.compile(r'^@[A-Za-z0-9_]+\s*=.*$', re.M)


def _type_span(text, name):
    """(start, end) of 'type <name> = ... { ... }' with its line's leading indent and the newline after it."""
    m = list(re.finditer(r'^[ \t]*type[ \t]+' + re.escape(name) + r'[ \t]*=', text, re.M))
    if len(m) != 1:
        raise SystemExit(f'cmf_compat: type {name} found {len(m)} times')
    start = m[0].start()
    i, depth, quote = text.index('{', m[0].end()), 0, False
    while True:
        c = text[i]
        if c == '"':
            quote = not quote
        elif c == '#' and not quote:
            i = text.index('\n', i) - 1
        elif not quote and c == '{':
            depth += 1
        elif not quote and c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                if text.startswith('\n', end):
                    end += 1
                return start, end
        i += 1


def _hooks(body):
    a, b = HOOKS[0][0], HOOKS[1][0]
    for anchor in (a, b):
        if body.count(anchor) != 1:
            raise SystemExit('cmf_compat: a state_panel_buildings_content anchor moved; update HOOKS')
    body = body.replace(a, HOOKS[0][1] + a)
    cut = body.index(b) + b.index('\t\t\tbuildings_list = {')
    return body[:cut] + HOOK2 + body[cut:]


def apply(out_dir):
    gui = os.path.join(out_dir, 'gui')
    moved = {}
    for name, src in FIRST_TYPES:
        moved.setdefault(src, []).append(name)
    report = []
    for src, names in moved.items():
        path = os.path.join(gui, src)
        with open(path, encoding='utf-8-sig') as f:
            text = f.read()
        consts = CONST.findall(text)
        blocks = []
        for name in names:
            s, e = _type_span(text, name)
            body = text[s:e]
            if name == 'state_panel_buildings_content':
                body = _hooks(body)
            blocks.append(body)
            text = text[:s] + text[e:]
        stem = src[:-len('.gui')]
        new = (f'# GENERATED by tools/pmr/generate.py (cmf_compat.py). PMR\'s copies of {", ".join(names)},\n'
               f'# moved from {src} so they load before Community Mod Framework\'s 00_MPM_/00_com_ copies:\n'
               '# the game keeps the first definition of a GUI type. The constants are those of ' + src + '.\n\n'
               + ''.join(c + '\n' for c in consts)
               + f'\ntypes pmr_first_{stem} {{\n' + '\n'.join(blocks) + '}\n')
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        with open(os.path.join(gui, PREFIX + src), 'w', encoding='utf-8', newline='\n') as f:
            f.write(new)
        report.append((PREFIX + src, names))
    with open(os.path.join(gui, FALLBACK), 'w', encoding='utf-8', newline='\n') as f:
        f.write(FALLBACK_TEXT)
    return report


if __name__ == '__main__':
    import sys
    for f, names in apply(sys.argv[1]):
        print(f, '<-', ', '.join(names))
