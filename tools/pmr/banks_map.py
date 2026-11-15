"""BANKS (q121, UI.md section 7; Pat's card 2026-11-15 19:47Z "Build it into q121"): Banks on the map.

Vanilla places a city model for a building type through the city type files
(gfx/map/city_data/city_types/*.txt): `building_financial_district = {"european_city_financialdistrict_01_mesh"}`.
A mod cannot add a line to an object in those files, so each file that names a Financial District model is written
again whole into the mod, with one line added that gives Banks the same model.

For the build thread: call `banks_city_types(args.game, args.out)` under the switch (suggested `--banks-map`, needs
`--banks`), and give the Banks building `city_type = city` and `levels_per_mesh = 50` in `cc_buildings` in place of
`city_type = none` (vanilla's Company Headquarters is the working example: one level, not buildable, not
expandable, `city_type = city`, `levels_per_mesh = 50`, one model). The size sites keep `city_type = none`.
"""
import glob
import os
import re

BANKS = 'building_pmr_construction_center'
SOURCE = 'building_financial_district'
LINE = re.compile(r'^([ \t]*)' + SOURCE + r'[ \t]*=[ \t]*(\{[^}\n]*\})[^\n]*$', re.M)


def banks_city_types(game, out, banks=BANKS):
    """Write every city type file that gives the Financial District a model, with Banks added on the same model.
    Returns the file names written. Stops the build if the game folder has none, so a build never ships the building
    change without its models."""
    src = os.path.join(game, 'gfx', 'map', 'city_data', 'city_types')
    written = []
    for path in sorted(glob.glob(os.path.join(src, '*.txt'))):
        with open(path, encoding='utf-8-sig') as f:
            text = f.read()
        if banks in text:
            raise SystemExit(f'--banks-map: {path} already names {banks}')
        new, n = LINE.subn(lambda m: f'{m.group(0)}\n{m.group(1)}{banks} = {m.group(2)}   # PMR: Banks (q121)', text)
        if not n:
            continue   # a commented example, or a type with no city buildings (farm, mine, port, wood)
        dst = os.path.join(out, 'gfx', 'map', 'city_data', 'city_types', os.path.basename(path))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'w', encoding='utf-8-sig', newline='') as f:   # the game's files carry a BOM
            f.write(new)
        written.append(os.path.basename(path))
    if not written:
        raise SystemExit(f'--banks-map: no city type file under {src} names {SOURCE}')
    return written


if __name__ == '__main__':
    import sys
    print('\n'.join(banks_city_types(sys.argv[1], sys.argv[2])))
