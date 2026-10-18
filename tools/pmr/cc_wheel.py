"""Company Culture: the wheel on the company panel's Company Culture tab (BUILD-SPEC.md section 1).

company_culture.py builds the lines, their script and their text; this module draws them. The layout is the one in
/mnt/project-files/pmr/mio/tree-ui/wheel-preview.png (render_wheel_preview.py there): four arms on the diagonals,
Engineering top right, Stewardship top left, Expansion bottom left and Providence bottom right, each tier one orbit
further out, each orbit turned SWIRL degrees further round so the arms curl. The shared charters sit halfway out on the
boundary between two arms, on the dashed gold gate orbit, and their synergies further out behind them.

Every piece is a vanilla GUI part or a small texture this module writes (textures()): the node card is the tech
node's (round_frame_dec behind an invention picture, cost badge, ticks, the add button and the event glow), on a
rounded card whose outline colour says the kind of benefit (KIND_COL, the legend "Node outline"). The wheel sits on a
canvas in a zoomarea, the tech tree's pan-and-zoom widget, over the tech tree's backdrop painting.

Links are dotted. A drawn curve would be one uncompressed texture per link (megabytes each), so each link is a row of
small dot icons along its curve, in three colourings (done, open, locked) of which one shows. The orbits are faint
dots; the gate orbit gold dashes.

A node reads its state from the executive's mirror, pmr_cc_st_<line>_<tier> (company_culture.effects, pmr_cc_states):
0 locked, 1 can be bought now, 2 next but short of points (or another grant running), 3 its arm not chosen,
4 bought, 5 ruled out by the opposed arm, 6 its research grant running, 7 not for this company, 8 waiting for the
technology of its base recipe.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import company_culture as cc   # circular: company_culture imports this module; used inside functions only
import icons

TEX = 'gfx/interface/pmr_company_culture'
WHITE = 'gfx/interface/backgrounds/white.dds'
FRAME_TEX = 'gfx/interface/backgrounds/round_frame_dec.dds'
ROUND_BG = 'gfx/interface/backgrounds/round_button_bg.dds'
WARNING = 'gfx/interface/icons/generic_icons/warning.dds'
SG_SCOPE = 'GuiScope.SetRoot(Character.MakeScope)'
LOCAL = 'Company.GetCountry.IsLocalPlayer'

# The node card (Pat 17:08Z: bigger nodes than the tech tree's 465 x 150)
NODE_W, NODE_H = 600, 240
FRAME, ICON = 180, 138                  # round frame and invention picture, as the tech node
CW = round(NODE_W * 0.82)               # the card, right of the frame
TX0 = FRAME + 14                        # the text column
TXW = NODE_W - TX0 - 22
HUB_R = 170                             # the company's seal

# The orbits (render_wheel_preview.py)
RINGS = (620, 1220, 1820, 2420, 3020, 3620)
SWIRL = 6                               # degrees each orbit turns further round
LANE_ARC = 700                          # lanes of an arm sit this far apart along an orbit
OUTER = 3                               # the orbit from which nodes wait for a shared charter
GATE_R = (RINGS[OUTER - 1] + RINGS[OUTER]) / 2
ANGLE = {'eng': 45, 'stw': 135, 'exp': 225, 'prv': 315}     # arm centres, degrees counter-clockwise from east
# (line, lane, orbit of tier 1). A negative lane turns clockwise.
LANES = {
    'eng': [('g1', -0.6, 1), ('g2', 0.6, 1), ('sf', -1.8, 2)],
    'exp': [('xs', -0.6, 1), ('sc', 0.6, 1), ('cz', 0.6, 4)],
    'stw': [('fw', -1, 1), ('ho', 1, 1), ('ct', 0, 3), ('au', -2, 2), ('pg', 0, 4)],
    'prv': [('cl', -0.6, 1), ('tp', 0.6, 1)],
}
SHARED_AT = {'tr': 90, 'iv': 0, 'ch': 180, 'mo': 270}      # the boundary each shared charter sits on
SYNERGY_OF = {'ys': 'tr', 'yi': 'iv', 'yt': 'ch', 'ym': 'mo'}
# The outer nodes each charter's links lead to (drawn only: any shared charter of an arm opens its whole outer half)
OPENS = {'tr': [('g2', 3), ('fw', 3)], 'iv': [('g1', 3), ('cl', 3)], 'ch': [('xs', 3), ('ct', 1)],
         'mo': [('sc', 3), ('cl', 3)]}
MARGIN = 260
LABEL_OUT = 520                         # arm titles, this far beyond the arm's outermost node
LABEL_W, LABEL_H = 1500, 150

# Pat 17:08Z: the outline colour by the kind of benefit, with a legend (BUILD-SPEC section 1)
KIND_COL = {'pm': (150, 44, 56), 'prod': (206, 124, 80), 'input': (98, 156, 214), 'work': (170, 136, 216),
            'charter': (238, 202, 106)}
CARD_COL = {'active': (30, 63, 77), 'pending': (20, 40, 48), 'bought': (55, 50, 44), 'locked': (12, 24, 30)}
DOT_COL = {    # border, core: the colours of vanilla's tech_line_border_<x>.dds and tech_line_<x>.dds
    'done': ((239, 203, 154), (128, 104, 71)),
    'active': ((156, 203, 231), (112, 174, 194)),
    'locked': ((40, 44, 46), (110, 132, 137)),
}
DOT, DOT_STEP = 18, 30                  # link dots: size and spacing along the curve
ORBIT_DOT, ORBIT_STEP = 10, 64
GATE_DOT, GATE_EVERY, GATE_DASH = 18, 4, 3   # gold dashes: one every 4 degrees, 3 dots long
PM_C = (246, 204, 52)                   # Pat 17:45Z: new methods in yellow
LOGO_W, LOGO_H = 64, 40

VIEW_W, VIEW_H = 540, 660               # the zoomarea in the tab
ZOOM, ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.22, 0.06, 1, 0.04


# ---------------------------------------------------------------------------------------------------------------
# Expressions

def V(name):
    return f"Character.MakeScope.Var('{name}').GetValue"


def EQ(name, n):
    return f"EqualTo_CFixedPoint({V(name)}, '(CFixedPoint){n}')"


def GT(name, n):
    return f"GreaterThan_CFixedPoint({V(name)}, '(CFixedPoint){n}')"


def OR(*xs):
    return xs[0] if len(xs) == 1 else f'Or({xs[0]}, {OR(*xs[1:])})'


def AND(*xs):
    return xs[0] if len(xs) == 1 else f'And({xs[0]}, {AND(*xs[1:])})'


def ST(k, t, *vals):
    return OR(*(EQ(f'pmr_cc_st_{k}_{t}', v) for v in vals))


CLASSES = {'active': (1,), 'pending': (2, 6, 8), 'bought': (4,), 'locked': (0, 3, 5, 7)}


def hidden(k, t):
    """A goods line the company doesn't have is left off the wheel (state 7); other nodes always show."""
    return ST(k, t, 7) if cc.BY_KEY[k].goods else None


# ---------------------------------------------------------------------------------------------------------------
# Layout

def _ring_of(r):
    return (r - RINGS[0]) / (RINGS[1] - RINGS[0])


def _place(ang, r, lane=0):
    a = math.radians(ang + SWIRL * _ring_of(r)) + lane * LANE_ARC / r
    return np.array([r * math.cos(a), -r * math.sin(a)])


def layout():
    """Node centres {(line, tier): (x, y)} round the seal at (0, 0), y down; links [(from or None for the seal,
    to)]; arm title centres {arm: (x, y)}."""
    pos, links = {}, []

    def clear(p):
        return not any(abs(p[0] - q[0]) < NODE_W + 50 and abs(p[1] - q[1]) < NODE_H + 50 for q in pos.values())
    for a in cc.ARMS:
        f = cc.FOUND[a]
        pos[(f, 1)] = _place(ANGLE[a], RINGS[0])
        links.append((None, (f, 1)))
    for a in ('eng', 'exp', 'stw', 'prv'):
        for k, lane, o in LANES[a]:
            ln = cc.BY_KEY[k]
            r = 0
            for t in range(1, ln.tiers + 1):
                r = max(RINGS[o + t - 1], r)
                while not clear(_place(ANGLE[a], r, lane)):
                    r += 10
                pos[(k, t)] = _place(ANGLE[a], r, lane)
                parents = (list(ln.links) or [(cc.FOUND[a], 1)]) if t == 1 else [(k, t - 1)]
                links += [(q, (k, t)) for q in parents]
    for k in list(SHARED_AT) + list(SYNERGY_OF):
        ang = SHARED_AT[SYNERGY_OF.get(k, k)]
        r = RINGS[OUTER] + 300 if k in SYNERGY_OF else GATE_R
        while not clear(_place(ang, r)):
            r += 10
        pos[(k, 1)] = _place(ang, r)
        links += [(q, (k, 1)) for q in cc.BY_KEY[k].links] + [((k, 1), q) for q in OPENS.get(k, [])]
    # the gate orbit must part the inner half from the outer one as the script does (Line.outer)
    for (k, t), p in pos.items():
        ln = cc.BY_KEY[k]
        if ln.founding or ln.shared:
            continue
        r = float(np.hypot(*p))
        if (t in ln.outer) != (r > GATE_R):
            cc.fail('cc_wheel layout', f'{k} tier {t} sits at radius {r:.0f}, on the wrong side of the gate ({GATE_R:.0f})')
    keys = list(pos)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if abs(pos[a][0] - pos[b][0]) < NODE_W + 40 and abs(pos[a][1] - pos[b][1]) < NODE_H + 40:
                cc.fail('cc_wheel layout', f'{a} and {b} overlap')
    labels = {}
    for a in cc.ARMS:
        rmax = max(float(np.hypot(*p)) for (k, _t), p in pos.items()
                   if not cc.BY_KEY[k].shared and cc.BY_KEY[k].arm == a)
        labels[a] = _place(ANGLE[a], rmax + LABEL_OUT)
    return pos, links, labels


def canvas(pos, labels):
    """The canvas size and the seal's place on it."""
    ext_x = max(max(abs(p[0]) + NODE_W / 2 for p in pos.values()), max(abs(p[0]) + LABEL_W / 2 for p in labels.values()),
                RINGS[-1])
    ext_y = max(max(abs(p[1]) + NODE_H / 2 + 160 for p in pos.values()), max(abs(p[1]) + LABEL_H for p in labels.values()),
                RINGS[-1])
    w, h = int(2 * (ext_x + MARGIN)), int(2 * (ext_y + MARGIN))
    return w, h, w // 2, h // 2


def _edge_point(c, toward):
    """Where the ray from card centre c toward a point leaves the card."""
    v = toward - c
    sx = (NODE_W / 2) / abs(v[0]) if v[0] else 1e9
    sy = (NODE_H / 2) / abs(v[1]) if v[1] else 1e9
    return c + v * min(sx, sy)


def link_points(pos, a, b):
    """Dot centres along the link from a to b (a None: from the seal)."""
    pb = pos[b]
    if a is None:
        u = pb / np.linalg.norm(pb)
        p0, p3 = u * (HUB_R + 10), _edge_point(pb, np.zeros(2))
        curve = p0 + (p3 - p0) * np.linspace(0, 1, 200)[:, None]
    else:
        pa = pos[a]
        u = (pb - pa) / np.linalg.norm(pb - pa)
        t0 = pa / np.linalg.norm(pa) + u
        t0 /= np.linalg.norm(t0)
        t1 = pb / np.linalg.norm(pb) + u
        t1 /= np.linalg.norm(t1)
        p0 = _edge_point(pa, pa + t0 * 400 + (pb - pa) * 0.5)
        p3 = _edge_point(pb, pb - t1 * 400 + (pa - pb) * 0.5)
        span = np.linalg.norm(p3 - p0)
        p1, p2 = p0 + t0 * span * 0.4, p3 - t1 * span * 0.4
        ts = np.linspace(0, 1, 400)[:, None]
        curve = (1 - ts) ** 3 * p0 + 3 * (1 - ts) ** 2 * ts * p1 + 3 * (1 - ts) * ts ** 2 * p2 + ts ** 3 * p3
    seg = np.hypot(*np.diff(curve, axis=0).T)
    run = np.concatenate([[0], np.cumsum(seg)])
    n = max(1, int(run[-1] // DOT_STEP))
    at = (np.arange(n) + 0.5) * run[-1] / n
    return [curve[min(np.searchsorted(run, s), len(curve) - 1)] for s in at]


# ---------------------------------------------------------------------------------------------------------------
# GUI pieces (written unindented; _reindent indents by brace depth)

def _reindent(text, base):
    out, depth = [], 0
    for raw in text.split('\n'):
        line = raw.strip()
        if not line:
            continue
        if line.startswith('}'):
            depth -= 1
        out.append(base + '\t' * depth + line)
        depth += line.count('{') - line.count('}') + (1 if line.startswith('}') else 0)
    if depth:
        cc.fail('cc_wheel', f'unbalanced braces ({depth})')
    return '\n'.join(out) + '\n'


def _vis(expr):
    return f'visible = "[{expr}]"\n' if expr else ''


def _rgb(c, a=1):
    return f'color = {{ {c[0] / 255:.3f} {c[1] / 255:.3f} {c[2] / 255:.3f} {a} }}\n'


def dots(points, ox, oy, size, tex):
    return ''.join(f'icon = {{ position = {{ {round(ox + x - size / 2)} {round(oy + y - size / 2)} }} size = {{ {size} {size} }} '
                   f'texture = "{tex}" alwaystransparent = yes }}\n' for x, y in points)


def link_gui(pos, a, b, ox, oy):
    """One link in its three colourings: done once both ends are bought, open while its far end is next, locked
    otherwise. A link to a goods line the company doesn't have is left off."""
    pts = link_points(pos, a, b)
    bk, bt = b
    done = ST(bk, bt, 4) if a is None else AND(ST(bk, bt, 4), ST(a[0], a[1], 4))
    active = ST(bk, bt, 1, 2, 6, 8)
    modes = {'locked': f'Not({OR(done, active)})', 'active': active, 'done': done}
    hide = [h for h in (hidden(bk, bt), hidden(*a) if a else None) if h]
    out = ''
    for mode, vis in modes.items():
        if hide:
            vis = AND(vis, f'Not({OR(*hide)})')
        out += f'container = {{\n{_vis(vis)}' + dots(pts, ox, oy, DOT, f'{TEX}/cc_dot_{mode}.dds') + '}\n'
    return out, len(pts)


def orbits_gui(ox, oy, rmax):
    """The faint orbits, one per tier out to the last used, and the dashed gold gate orbit."""
    out = 'container = {\n'
    for r in RINGS:
        if r > rmax + NODE_H:
            break
        n = int(2 * math.pi * r // ORBIT_STEP)
        pts = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
        out += dots(pts, ox, oy, ORBIT_DOT + (4 if r == RINGS[0] else 0), f'{TEX}/cc_dot_orbit.dds')
    step = math.degrees(GATE_DOT * 1.4 / GATE_R)
    pts = [(GATE_R * math.cos(math.radians(a0 + j * step)), GATE_R * math.sin(math.radians(a0 + j * step)))
           for a0 in range(0, 360, GATE_EVERY) for j in range(GATE_DASH)]
    out += dots(pts, ox, oy, GATE_DOT, f'{TEX}/cc_dot_gate.dds')
    return out + '}\n'


def _textbox(x, y, w, h, text, size, extra='', raw=False):
    key = 'raw_text' if raw else 'text'
    return (f'textbox = {{\nposition = {{ {x} {y} }}\nsize = {{ {w} {h} }}\nalign = left|nobaseline\n'
            f'fontsize = {size}\nfontsize_min = {max(12, size - 12)}\nelide = right\n{extra}{key} = "{text}"\n'
            'alwaystransparent = yes\n}\n')


def goods_body(p, ln, t, cands_b, cands_g):
    """A goods tier's bullets (BUILD-SPEC section 4): the method's name in yellow with its logo, the net line, and the
    grey note naming the base method."""
    gl = ln.goods
    logos = ''
    for b in cands_b:
        w = p.works[b]
        logos += (f'icon = {{\n{_vis(EQ(f"pmr_cc_k_g{gl}b", w["idx"]))}position = {{ 14 2 }}\nsize = {{ 36 36 }}\n'
                  f'texture = "{WHITE}"\n{_rgb(PM_C)}'
                  f'modify_texture = {{\ntexture = "{w["icons"][t - 1]}"\nspriteType = Corneredstretched\n'
                  'spriteborder = { 0 0 }\nblend_mode = alphamultiply\n}\nalwaystransparent = yes\n}\n')
    return (f'flowcontainer = {{\nposition = {{ {TX0} 82 }}\ndirection = vertical\nspacing = 4\n'
            f'flowcontainer = {{\ndirection = horizontal\nspacing = 10\n'
            f'textbox = {{\nautoresize = yes\nmaximumsize = {{ {TXW - LOGO_W - 10} -1 }}\nalign = left|nobaseline\n'
            f'fontsize = 26\nelide = right\ntext = "PMR_CC_PMNAME_g{gl}_{t}"\nalwaystransparent = yes\n}}\n'
            f'widget = {{\nsize = {{ {LOGO_W} {LOGO_H} }}\n'
            f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{TEX}/cc_pm_plate.dds"\nalwaystransparent = yes\n}}\n'
            + logos + '}\n}\n'
            f'textbox = {{\nautoresize = yes\nmaximumsize = {{ {TXW} -1 }}\nalign = left|nobaseline\nfontsize = 24\n'
            f"elide = right\nraw_text = \"[Character.GetCustom('pmr_cc_net_g{gl}_{t}')]\"\nalwaystransparent = yes\n}}\n"
            f'textbox = {{\nautoresize = yes\nmaximumsize = {{ {TXW - 22} -1 }}\nposition = {{ 22 0 }}\n'
            f'align = left|nobaseline\nfontsize = 20\nelide = right\ntext = "PMR_CC_OVER_g{gl}"\nalwaystransparent = yes\n}}\n'
            '}\n')


def node(p, ln, t, x, y, cands):
    """The tech node for one tier, top left at (x, y) on the canvas."""
    k = ln.key
    st = f'pmr_cc_st_{k}_{t}'
    cls = {c: ST(k, t, *v) for c, v in CLASSES.items()}
    locked = cls['locked']
    tt = f'tooltip = "PMR_CC_TT_{k}_{t}"\n'
    sg = "GetScriptedGui('pmr_cc_pick_sgui')"
    scope = f"{SG_SCOPE}.AddScope('line', MakeScopeValue('(CFixedPoint){ln.code}')).End"
    can = AND(LOCAL, EQ(st, 1), f'{sg}.IsValid({scope})')
    click = f'enabled = "[{can}]"\nonclick = "[{sg}.Execute({scope})]"\n'
    kc = KIND_COL[ln.kind]
    out = f'widget = {{\n{_vis(f"Not({hidden(k, t)})" if hidden(k, t) else None)}position = {{ {x} {y} }}\nsize = {{ {NODE_W} {NODE_H} }}\n{tt}'
    # the tech node's glow while it can be bought
    out += (f'widget = {{\n{_vis(cls["active"])}size = {{ 130% 70 }}\nparentanchor = bottom|hcenter\nposition = {{ 0 -15 }}\n'
            'using = ui_event_glow_animation_looping\nalwaystransparent = yes\n}\n')
    # the card by state, its outline by kind (fainter while locked, faintest when ruled out)
    card = f'position = {{ {NODE_W - CW} 0 }}\nsize = {{ {CW} {NODE_H} }}\nalwaystransparent = yes\n'
    for c, col in CARD_COL.items():
        if c == 'locked':
            out += f'icon = {{\n{_vis(ST(k, t, 0, 3, 7))}{card}texture = "{TEX}/cc_card.dds"\n{_rgb(col)}}}\n'
            out += f'icon = {{\n{_vis(ST(k, t, 5))}{card}texture = "{TEX}/cc_card.dds"\n{_rgb(col, 0.6)}}}\n'
        else:
            out += f'icon = {{\n{_vis(cls[c])}{card}texture = "{TEX}/cc_card.dds"\n{_rgb(col)}}}\n'
    out += f'icon = {{\n{_vis(f"Not({locked})")}{card}texture = "{TEX}/cc_outline.dds"\n{_rgb(kc)}}}\n'
    out += f'icon = {{\n{_vis(ST(k, t, 0, 3, 7))}{card}texture = "{TEX}/cc_outline.dds"\n{_rgb(kc, 0.65)}}}\n'
    out += f'icon = {{\n{_vis(ST(k, t, 5))}{card}texture = "{TEX}/cc_outline.dds"\n{_rgb(kc, 0.45)}}}\n'
    # a click on the card buys it
    out += (f'button = {{\n{_vis(cls["active"])}position = {{ {NODE_W - CW} 0 }}\nsize = {{ {CW} {NODE_H} }}\n'
            f'using = technology_confirm_button_sound\n{click}{tt}}}\n')
    # name, divider and what it does; dimmed while locked
    name = cc.node_name(k, t)
    title = (_textbox(TX0, 18, TXW, 50, name, 36, raw=True) if name.startswith('[')
             else _textbox(TX0, 18, TXW, 50, f'PMR_CC_NAME_{k}_{t}', 36))
    body = (goods_body(p, ln, t, *cands[ln.goods]) if ln.goods else
            f'textbox = {{\nposition = {{ {TX0} 82 }}\nautoresize = yes\nmaximumsize = {{ {TXW} 150 }}\nmultiline = yes\n'
            f'align = left|nobaseline\nfontsize = 26\nelide = right\ntext = "PMR_CC_FX_{k}_{t}"\nalwaystransparent = yes\n}}\n')
    text = (title + f'icon = {{\nposition = {{ {TX0} 72 }}\nsize = {{ {TXW} 2 }}\ntexture = "{WHITE}"\n'
            f'{_rgb((200, 185, 150), 0.35)}alwaystransparent = yes\n}}\n' + body)
    out += (f'widget = {{\n{_vis(f"Not({locked})")}size = {{ 100% 100% }}\nalwaystransparent = yes\n{text}}}\n'
            f'widget = {{\n{_vis(locked)}size = {{ 100% 100% }}\nalpha = 0.55\nalwaystransparent = yes\n{text}}}\n')
    # the round frame and the picture, greyed while locked
    fy, iy = (NODE_H - FRAME) // 2, (NODE_H - ICON) // 2
    frame = f'position = {{ 0 {fy} }}\nsize = {{ {FRAME} {FRAME} }}\ntexture = "{FRAME_TEX}"\nalwaystransparent = yes\n'
    pic = f'position = {{ 20 {iy} }}\nsize = {{ {ICON} {ICON} }}\ntexture = "{ln.icons[t - 1]}"\n'
    out += (f'icon = {{\n{_vis(f"Not({locked})")}{frame}}}\n'
            f'icon = {{\n{_vis(locked)}{frame}color = {{ 0.5 0.5 0.5 1 }}\n}}\n'
            f'button = {{\n{_vis(cls["active"])}{pic}using = technology_confirm_button_sound\n{click}{tt}}}\n'
            f'icon = {{\n{_vis(OR(cls["pending"], cls["bought"]))}{pic}{tt}}}\n'
            f'icon = {{\n{_vis(locked)}{pic}color = {{ 0.4 0.4 0.4 1 }}\n{tt}}}\n')
    # the cost in points, where the tech node shows its era
    badge = f'widget = {{\n{{VIS}}position = {{ 70 {fy + FRAME - 30} }}\nsize = {{ 40 40 }}\ntooltip = "PMR_CC_COST_TT"\n' \
            f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{ROUND_BG}"\n}}\n' \
            'textbox = {\n{TEXT}\nparentanchor = center\nautoresize = yes\nalign = center|nobaseline\nfontsize = 24\n' \
            'alwaystransparent = yes\n}\n}\n'
    if ln.founding:
        out += (badge.replace('{VIS}', _vis(AND(f'Not({cls["bought"]})', GT('pmr_cc_fcost', 0))))
                .replace('{TEXT}', f'raw_text = "[{V("pmr_cc_fcost")}|0]"'))
    elif ln.cost[t - 1]:
        out += badge.replace('{VIS}', '').replace('{TEXT}', f'raw_text = "{ln.cost[t - 1]}"')
    # bought: the tech node's ticks
    out += (f'widget = {{\n{_vis(cls["bought"])}size = {{ 50 50 }}\nparentanchor = bottom|right\nposition = {{ 20 20 }}\n'
            f'icon = {{\nsize = {{ 50 50 }}\ntexture = "{ROUND_BG}"\nparentanchor = center\n}}\n'
            'icon = {\ntexture = "gfx/interface/icons/generic_icons/checkmark.dds"\nsize = { 60 60 }\nparentanchor = center\n}\n}\n'
            f'icon = {{\n{_vis(cls["bought"])}size = {{ 50 50 }}\nposition = {{ 5 {fy + 5} }}\ntexture = "{ROUND_BG}"\n'
            'icon = {\nsize = { 80% 80% }\nparentanchor = center\ntexture = "gfx/interface/icons/generic_icons/green_checkmark.dds"\n}\n}\n')
    # can be bought: the add button; ruled out: the warning (BUILD-SPEC section 3)
    out += (f'button_icon_plus_action = {{\n{_vis(cls["active"])}position = {{ 0 {fy} }}\nsize = {{ 50 50 }}\n'
            f'using = tooltip_ne\n{click}{tt}}}\n'
            f'icon = {{\n{_vis(ST(k, t, 5))}position = {{ 5 {fy + 5} }}\nsize = {{ 40 40 }}\ntexture = "{WARNING}"\n'
            'tooltip = "PMR_CC_EXCLUSIVE_TT"\n}\n')
    # a goods line's good, in a round badge on the card's top right corner
    if ln.goods:
        goods = ''.join(f'icon = {{\n{_vis(EQ(f"pmr_cc_k_g{ln.goods}g", cc.gi(p, g)))}position = {{ 4 4 }}\nsize = {{ 44 44 }}\n'
                        f'texture = "{p.goods_tex.get(g, f"gfx/interface/icons/goods_icons/{g}.dds")}"\nalwaystransparent = yes\n}}\n'
                        for g in cands[ln.goods][1])
        out += (f'widget = {{\nposition = {{ {NODE_W - 64} -26 }}\nsize = {{ 52 52 }}\n'
                f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{ROUND_BG}"\nalwaystransparent = yes\n}}\n{goods}}}\n')
    return out + '}\n'


def grant_gui(ln, t, x, y):
    """A goods tier's research grant while it runs (state 6): the vanilla green bar under the card, filling month by
    month, and what it costs and gives (BUILD-SPEC section 5). Drawn over everything, on a dark plate."""
    bw = CW - 20
    bar_value = f'FixedPointToFloat({V("pmr_cc_grm")})'
    return (f'widget = {{\n{_vis(ST(ln.key, t, 6))}position = {{ {x + NODE_W - CW - 2} {y + NODE_H + 8} }}\n'
            f'size = {{ {bw + 24} 158 }}\ntooltip = "PMR_CC_GRANT_TT"\n'
            f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{TEX}/cc_card.dds"\n{_rgb((20, 24, 26), 0.92)}alwaystransparent = yes\n}}\n'
            f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{TEX}/cc_outline.dds"\n{_rgb((120, 108, 84), 0.8)}alwaystransparent = yes\n}}\n'
            f'green_progressbar_horizontal = {{\nposition = {{ 12 12 }}\nsize = {{ {bw} 46 }}\n'
            f'blockoverride "values" {{\nmin = 0\nmax = {cc.GRANT_MONTHS}\nvalue = "[{bar_value}]"\n}}\n}}\n'
            f'textbox = {{\nposition = {{ 12 12 }}\nsize = {{ {bw} 46 }}\nalign = center|nobaseline\nfontsize = 23\n'
            'text = "PMR_CC_GRANT_BAR"\nalwaystransparent = yes\n}\n'
            + _textbox(14, 70, bw, 34, 'PMR_CC_GRANT_RUN', 22)
            + _textbox(14, 108, bw, 34, 'PMR_CC_GRANT_THEN', 22)
            + '}\n')


def hub_gui(ox, oy):
    unfounded = EQ('pmr_cc_nf', 0)
    return (f'widget = {{\nposition = {{ {ox - HUB_R} {oy - HUB_R} }}\nsize = {{ {2 * HUB_R} {2 * HUB_R} }}\n'
            'tooltip = "PMR_CC_HUB_TT"\n'
            f'icon = {{\n{_vis(unfounded)}using = rotate_glow_blue\nparentanchor = center\nsize = {{ 600 600 }}\n'
            'alwaystransparent = yes\n}\n'
            f'icon = {{\ntexture = "{FRAME_TEX}"\nsize = {{ 100% 100% }}\nalwaystransparent = yes\n}}\n'
            'icon = {\ntexture = "[Company.AccessCompanyType.GetIcon]"\nparentanchor = center\nsize = { 240 240 }\n'
            'alwaystransparent = yes\n}\n}\n'
            f'textbox = {{\n{_vis(unfounded)}position = {{ {ox - 300} {oy + HUB_R + 14} }}\nsize = {{ 600 56 }}\n'
            'align = center|nobaseline\nfontsize = 34\nusing = header_font\ntext = "PMR_CC_HUB_CHOOSE"\nalwaystransparent = yes\n}\n')


def arm_title(a, c, ox, oy):
    """Letter-spaced small caps in the game's header serif, faint, beyond the arm (Pat 17:13-17:59Z)."""
    ruled = ST(cc.FOUND[a], 1, 5)
    box = (f'position = {{ {round(ox + c[0] - LABEL_W / 2)} {round(oy + c[1] - LABEL_H / 2)} }}\n'
           f'size = {{ {LABEL_W} {LABEL_H} }}\nalign = center|nobaseline\nusing = header_font\nfontsize = 110\n'
           f'text = "PMR_CC_ARM_{a}"\nalwaystransparent = yes\n')
    return (f'textbox = {{\n{_vis(f"Not({ruled})")}alpha = 0.7\n{box}}}\n'
            f'textbox = {{\n{_vis(ruled)}alpha = 0.3\n{box}}}\n')


def legend_gui():
    """Bottom left of the view, over the wheel: "Node outline" and the five kinds (BUILD-SPEC section 1)."""
    rows = ''
    for n, kind in enumerate(cc.KINDS):
        y = 30 + 21 * n
        rows += (f'icon = {{\nposition = {{ 10 {y + 2} }}\nsize = {{ 30 15 }}\ntexture = "{WHITE}"\n'
                 f'{_rgb((30, 40, 44))}alwaystransparent = yes\n}}\n'
                 f'icon = {{\nposition = {{ 10 {y + 2} }}\nsize = {{ 30 15 }}\ntexture = "{TEX}/cc_swatch.dds"\n'
                 f'{_rgb(KIND_COL[kind])}alwaystransparent = yes\n}}\n'
                 f'textbox = {{\nposition = {{ 48 {y} }}\nsize = {{ 180 20 }}\nalign = left|nobaseline\n'
                 f'using = fontsize_small\nelide = right\ntext = "PMR_CC_KIND_{kind}"\nalwaystransparent = yes\n}}\n')
    return (f'widget = {{\nparentanchor = bottom|left\nposition = {{ 6 -6 }}\nsize = {{ 236 {38 + 21 * len(cc.KINDS)} }}\n'
            f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{WHITE}"\n{_rgb((20, 24, 26), 0.85)}alwaystransparent = yes\n}}\n'
            f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{TEX}/cc_swatch.dds"\n{_rgb((200, 185, 150), 0.6)}alwaystransparent = yes\n}}\n'
            'textbox = {\nposition = { 10 6 }\nsize = { 216 22 }\nalign = left|nobaseline\nusing = header_font\nfontsize = 15\n'
            'text = "PMR_CC_LEGEND"\nalwaystransparent = yes\n}\n' + rows + '}\n')


def wheel(p, ready):
    """The zoomarea: orbits, links, the seal, arm titles, nodes, grant bars; the legend over it."""
    pos, links, labels = layout()
    w, h, ox, oy = canvas(pos, labels)
    rmax = max(float(np.hypot(*q)) for q in pos.values())
    cands = {}
    for gl in (1, 2):
        bs = sorted({v['g'][gl - 1] for v in p.comp.values() if len(v['g']) >= gl}, key=lambda b: p.works[b]['idx'])
        gs = sorted({v['gout'][gl - 1] for v in p.comp.values() if len(v['g']) >= gl})
        cands[gl] = (bs, gs)
    out = orbits_gui(ox, oy, rmax)
    n_dots = 0
    for a, b in links:
        g, n = link_gui(pos, a, b, ox, oy)
        out += g
        n_dots += 3 * n
    out += hub_gui(ox, oy)
    for a, c in labels.items():
        out += arm_title(a, c, ox, oy)
    corner = {kt: (round(ox + c[0] - NODE_W / 2), round(oy + c[1] - NODE_H / 2)) for kt, c in pos.items()}
    for (k, t), (x, y) in corner.items():
        out += node(p, cc.BY_KEY[k], t, x, y, cands)
    for (k, t), (x, y) in corner.items():
        if cc.BY_KEY[k].goods:
            out += grant_gui(cc.BY_KEY[k], t, x, y)
    pan_x, pan_y = round(VIEW_W / 2 - ox * ZOOM), round(VIEW_H / 2 - oy * ZOOM)
    gui = (f'widget = {{\n{_vis(ready)}parentanchor = hcenter\nsize = {{ {VIEW_W} {VIEW_H} }}\nscissor = yes\n'
           # the tech tree's backdrop painting, under its zoomarea's header background
           'background = {\nusing = illu_alpha\nfittype = center\n'
           'texture = "gfx/interface/illustrations/tech_tree/illustration_tech_production.dds"\n}\n'
           'zoomarea = {\nname = "pmr_cc_wheel"\nsize = { 100% 100% }\n'
           'background = {\nusing = entry_header\nmodify_texture = {\ntexture = "gfx/interface/masks/fade_vertical_top.dds"\n'
           'spriteType = Corneredstretched\nspriteborder = { 0 0 }\nblend_mode = alphamultiply\n}\n}\n'
           'state = {\nname = "_zoom_changed"\nduration = 0.15\n}\n'
           f'zoom = {ZOOM}\nzoom_step = {ZOOM_STEP}\nzoom_min = {ZOOM_MIN}\nzoom_max = {ZOOM_MAX}\ndraggable_by = left\n'
           f'pan_position = {{ {pan_x} {pan_y} }}\n'
           f'zoomwidget = {{\ncontainer = {{\nwidget = {{\nsize = {{ {w} {h} }}\n}}\n{out}}}\n}}\n}}\n'
           'textbox = {\nposition = { 8 4 }\nautoresize = yes\nalign = left|nobaseline\nusing = fontsize_small\n'
           'text = "PMR_CC_WHEEL_HINT"\nalwaystransparent = yes\n}\n'
           + legend_gui() + '}\n')
    return gui, {'canvas': (w, h), 'nodes': len(pos), 'links': len(links), 'link_dots': n_dots}


# ---------------------------------------------------------------------------------------------------------------
# The tab

def text_row(key, ind, visible=None, w=520, small=False):
    vis = f'{ind}\tvisible = "[{visible}]"\n' if visible else ''
    font = f'{ind}\tusing = fontsize_small\n' if small else ''
    return (f'{ind}textbox = {{\n{vis}{ind}\tparentanchor = hcenter\n{ind}\tminimumsize = {{ {w} -1 }}\n'
            f'{ind}\tmaximumsize = {{ {w} -1 }}\n{ind}\tautoresize = yes\n{ind}\tmultiline = yes\n'
            f'{ind}\talign = left|nobaseline\n{font}{ind}\ttext = "{key}"\n{ind}}}\n')


def methods_block(b, recipes, ind, split):
    """One building type's recipes, oldest to newest, with the share of the player's levels on each (a split
    building's share per plain recipe sums its pairs: pmr_c_rs_<j>_<b>)."""
    i1, i2, i3 = ind + '\t', ind + '\t\t', ind + '\t\t\t'
    sb = b[len('building_'):]
    country = 'Company.GetCountry.MakeScope'
    share_var = 'pmr_c_rs' if b in split else 'pmr_c_sh'
    out = (f'{ind}flowcontainer = {{\n{i1}visible = "[ObjectsEqual(BuildingType.Self, GetBuildingType(\'{b}\').Self)]"\n'
           f'{i1}position = {{ 66 4 }}\n{i1}spacing = 6\n')
    for i, (key, tex, techs) in enumerate(recipes, 1):
        unl = (f"GreaterThan_CFixedPoint({country}.ScriptValue('pmr_cc_unl_{key}'), '(CFixedPoint)0')" if techs else None)
        newest = f"EqualTo_CFixedPoint({country}.ScriptValue('pmr_cc_new_{sb}'), '(CFixedPoint){i}')"
        share = f"GetPlayer.MakeScope.Var('{share_var}_{i}_{sb}').GetValue"
        alpha = f'{i3}alpha = "[TransparentIfFalse({unl})]"\n' if unl else ''
        out += (f'{i1}widget = {{\n{i2}size = {{ 48 58 }}\n{i2}tooltip = "PMR_CC_PM_{key}"\n'
                f'{i2}icon = {{\n{i3}visible = "[{newest}]"\n{i3}size = {{ 48 48 }}\n{i3}texture = "{WHITE}"\n'
                f'{i3}color = {{ 0.74 0.60 0.30 0.55 }}\n{i3}alwaystransparent = yes\n{i2}}}\n'
                f'{i2}icon = {{\n{i3}position = {{ 4 4 }}\n{i3}size = {{ 40 40 }}\n{i3}texture = "{tex}"\n'
                + alpha + f'{i3}alwaystransparent = yes\n{i2}}}\n'
                f'{i2}textbox = {{\n{i3}visible = "[And({LOCAL}, GreaterThan_CFixedPoint({share}, \'(CFixedPoint)0\'))]"\n'
                f'{i3}position = {{ 0 46 }}\n{i3}size = {{ 48 14 }}\n{i3}align = hcenter|nobaseline\n{i3}using = fontsize_small\n'
                f'{i3}raw_text = "[{share}|%0]"\n{i3}alwaystransparent = yes\n{i2}}}\n{i1}}}\n')
    return out + f'{ind}}}\n'


STATS = {}


def tab(p, rows, untreated, split):
    i1, i2, i3, i4 = '\t\t', '\t\t\t', '\t\t\t\t', '\t\t\t\t\t'
    bar_value = f"FixedPointToFloat({V('pmr_cc_pct')})"
    # Every mirrored executive holds a cost (800 and up). Without one (a new executive this month, a save from
    # before Company Culture) the tab offers a button that reads the company in, instead of an empty wheel.
    ready = GT('pmr_cc_cost', 0)
    refresh = "GetScriptedGui('pmr_cc_refresh_sgui')"
    show = (f'{i1}button = {{\n{i2}visible = "[Not({ready})]"\n{i2}parentanchor = hcenter\n{i2}using = default_button\n'
            f'{i2}size = {{ 300 40 }}\n{i2}text = "PMR_CC_SHOW"\n{i2}tooltip = "PMR_CC_SHOW_TT"\n'
            f'{i2}onclick = "[{refresh}.Execute({SG_SCOPE}.End)]"\n{i1}}}\n')
    header = (
        f'{i1}widget = {{\n{i2}visible = "[{ready}]"\n{i2}parentanchor = hcenter\n{i2}size = {{ 540 82 }}\n'
        f'{i2}background = {{\n{i3}using = entry_bg\n{i2}}}\n'
        f'{i2}textbox = {{\n{i3}position = {{ 16 10 }}\n{i3}autoresize = yes\n{i3}align = left|nobaseline\n'
        f'{i3}using = fontsize_xxl\n{i3}text = "PMR_CC_LEVEL"\n{i3}tooltip = "PMR_CC_LEVEL_TT"\n{i2}}}\n'
        f'{i2}textbox = {{\n{i3}position = {{ 16 48 }}\n{i3}autoresize = yes\n{i3}align = left|nobaseline\n'
        f'{i3}text = "PMR_CC_POINTS"\n{i3}tooltip = "PMR_CC_LEVEL_TT"\n{i2}}}\n'
        f'{i2}widget = {{\n{i3}position = {{ 220 12 }}\n{i3}size = {{ 300 30 }}\n{i3}tooltip = "PMR_CC_BAR_TT"\n'
        f'{i3}gold_progressbar_horizontal = {{\n{i4}size = {{ 100% 100% }}\n{i4}blockoverride "values" {{\n'
        f'{i4}\tmin = 0\n{i4}\tmax = 100\n{i4}\tvalue = "[{bar_value}]"\n{i4}}}\n{i3}}}\n'
        f'{i3}textbox = {{\n{i4}parentanchor = center\n{i4}autoresize = yes\n{i4}align = hcenter|nobaseline\n'
        f'{i4}text = "PMR_CC_BAR"\n{i4}alwaystransparent = yes\n{i3}}}\n{i2}}}\n'
        f'{i2}textbox = {{\n{i3}visible = "[{GT("pmr_cc_mo", 0)}]"\n{i3}position = {{ 220 50 }}\n{i3}size = {{ 300 22 }}\n'
        f'{i3}align = hcenter|nobaseline\n{i3}using = fontsize_small\n{i3}text = "PMR_CC_RATE"\n{i3}tooltip = "PMR_CC_BAR_TT"\n{i2}}}\n'
        f'{i2}textbox = {{\n{i3}visible = "[Not({GT("pmr_cc_mo", 0)})]"\n{i3}position = {{ 220 50 }}\n{i3}size = {{ 300 22 }}\n'
        f'{i3}align = hcenter|nobaseline\n{i3}using = fontsize_small\n{i3}text = "PMR_CC_RATE_NONE"\n{i3}tooltip = "PMR_CC_BAR_TT"\n{i2}}}\n'
        f'{i1}}}\n')
    gui, stats = wheel(p, ready)
    STATS.clear()
    STATS.update(stats)
    methods = (f'{i1}default_header = {{\n{i2}blockoverride "text" {{\n{i3}text = "PMR_CC_METHODS_HEADER"\n{i2}}}\n{i1}}}\n'
               + text_row('PMR_CC_METHODS_INTRO', i1, small=True) +
               f'{i1}flowcontainer = {{\n{i2}parentanchor = hcenter\n{i2}direction = vertical\n{i2}spacing = 4\n'
               f'{i2}datamodel = "[Company.GetBuildingTypes]"\n{i2}item = {{\n'
               f'{i3}widget = {{\n{i4}size = {{ 540 66 }}\n{i4}background = {{\n{i4}\tusing = entry_bg\n{i4}}}\n'
               f'{i4}icon = {{\n{i4}\tposition = {{ 6 0 }}\n{i4}\tparentanchor = vcenter\n{i4}\tsize = {{ 54 54 }}\n'
               f'{i4}\ttexture = "[BuildingType.GetIcon]"\n{i4}\ttooltipwidget = {{\n{i4}\t\tFancyTooltip_BuildingType = {{}}\n{i4}\t}}\n{i4}}}\n'
               + ''.join(methods_block(b, rec, i4, split) for b, rec in sorted(rows.items()))
               + ''.join(f'{i4}textbox = {{\n{i4}\tvisible = "[ObjectsEqual(BuildingType.Self, GetBuildingType(\'{b}\').Self)]"\n'
                         f'{i4}\tposition = {{ 70 0 }}\n{i4}\tparentanchor = vcenter\n{i4}\tautoresize = yes\n'
                         f'{i4}\talign = left|nobaseline\n{i4}\ttext = "PMR_CC_METHODS_NONE"\n{i4}}}\n' for b in untreated)
               + f'{i3}}}\n{i2}}}\n{i1}}}\n')
    return ('# GENERATED by tools/pmr/company_culture.py and cc_wheel.py\n'
            'types pmr_company_culture {\n'
            '\ttype company_panel_culture_tab = flowcontainer {\n'
            '\t\tdirection = vertical\n\t\tusing = default_list_position\n\t\tusing = default_content_fade\n'
            '\t\tspacing = 6\n\t\tmargin_bottom = 10\n\t\tminimumsize = { 540 -1 }\n'
            '\t\tdatacontext = "[Company.GetExecutive]"\n\n'
            + show + header + _reindent(gui, i1) + methods +
            '\t}\n}\n')


def patch_panel(text, tab_id):
    """company_panel.gui: a fourth tab, Company Culture, after Statistics."""
    where = cc.PANEL_GUI
    anchor = '\t\t\t\tblockoverride "third_button_selected"\n\t\t\t\t{\n\t\t\t\t\ttext = "COMPANY_TAB_STATISTICS"\n\t\t\t\t}\n'
    if text.count(anchor) != 1:
        cc.fail(where, 'the Statistics tab button block moved')
    refresh = "GetScriptedGui('pmr_cc_refresh_sgui').Execute(GuiScope.SetRoot(Company.GetExecutive.MakeScope).End)"
    four = (
        '\n\t\t\t\t# PMR: Company Culture tab\n'
        '\t\t\t\tblockoverride "fourth_button"\n\t\t\t\t{\n\t\t\t\t\ttext = "PMR_CC_TAB"\n\t\t\t\t}\n'
        '\t\t\t\tblockoverride "fourth_button_tooltip"\n\t\t\t\t{\n\t\t\t\t\ttooltip = "PMR_CC_TAB_TT"\n\t\t\t\t}\n'
        f'\t\t\t\tblockoverride "fourth_button_click"\n\t\t\t\t{{\n\t\t\t\t\tonclick = "[InformationPanel.SelectTab(\'{tab_id}\')]"\n'
        f'\t\t\t\t\tonclick = "[{refresh}]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "fourth_button_visibility"\n\t\t\t\t{{\n\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'{tab_id}\')]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "fourth_button_visibility_checked"\n\t\t\t\t{{\n\t\t\t\t\tvisible = "[Not( InformationPanel.IsTabSelected(\'{tab_id}\') )]"\n\t\t\t\t}}\n'
        '\t\t\t\tblockoverride "fourth_button_selected"\n\t\t\t\t{\n\t\t\t\t\ttext = "PMR_CC_TAB"\n\t\t\t\t}\n')
    text = text.replace(anchor, anchor + four)
    anchor2 = ('\t\t\t\tcompany_panel_statistics_tab = {\n'
               '\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'statistics\')]"\n\t\t\t\t}\n')
    if text.count(anchor2) != 1:
        cc.fail(where, 'the Statistics tab contents moved')
    return text.replace(anchor2, anchor2 + '\n\t\t\t\t# PMR: Company Culture tab\n\t\t\t\tcompany_panel_culture_tab = {\n'
                        f'\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'{tab_id}\')]"\n\t\t\t\t}}\n')


# ---------------------------------------------------------------------------------------------------------------
# Textures

def _rounded(w, h, radius, ring=None, grad=None, aa=4):
    """A white rounded rectangle (or its outline, ring px wide) at w x h, drawn at aa times and scaled down. grad:
    brightness from left to right (1 to grad)."""
    W, H, R = w * aa, h * aa, radius * aa
    m = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=255)
    if ring:
        q = ring * aa
        d.rounded_rectangle([q, q, W - 1 - q, H - 1 - q], radius=max(1, R - q), fill=0)
    m = m.resize((w, h), Image.LANCZOS)
    rgb = np.full((h, w, 3), 255.0)
    if grad:
        f = np.minimum(1, np.arange(w) / w * 1.4)
        rgb *= (1 - f * (1 - grad))[None, :, None]
    return Image.fromarray(np.dstack([rgb, np.asarray(m)]).round().astype('uint8'), 'RGBA')


def _dot(size, border, core):
    """A link dot: the core colour inside a border ring, as vanilla's tech lines (border at 0.6, core at 0.9)."""
    n = size * 4
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    dist = np.hypot(xx - n / 2, yy - n / 2) / 4
    a_b = 0.75 * np.clip(size / 2 - dist, 0, 1)
    a_c = 0.95 * np.clip(size / 2 - 3 - dist, 0, 1)
    a = a_c + a_b * (1 - a_c)
    rgb = np.zeros((n, n, 3))
    nz = a > 0
    for i in range(3):
        rgb[..., i][nz] = (core[i] * a_c[nz] + border[i] * a_b[nz] * (1 - a_c[nz])) / a[nz]
    im = Image.fromarray(np.dstack([rgb, a * 255]).round().astype('uint8'), 'RGBA')
    return im.resize((size, size), Image.LANCZOS)


def _soft(size, col, alpha):
    n = size * 4
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    dist = np.hypot(xx - n / 2, yy - n / 2) / (n / 2)
    a = alpha * np.clip((1 - dist) * 2, 0, 1)
    im = Image.fromarray(np.dstack([np.full((n, n, 3), col), a * 255]).round().astype('uint8'), 'RGBA')
    return im.resize((size, size), Image.LANCZOS)


def _plate():
    """The dark button the new method's logo sits on, with a gold frame (Pat 17:45-17:52Z)."""
    s = 4
    im = Image.new('RGBA', (LOGO_W * s, LOGO_H * s))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([2, 2, LOGO_W * s - 3, LOGO_H * s - 3], radius=6 * s, fill=(52, 50, 64, 255),
                        outline=(196, 160, 96, 255), width=3 * s)
    d.line([(8 * s, 4 * s), (LOGO_W * s - 8 * s, 4 * s)], fill=(92, 88, 108, 255), width=2 * s)
    return im.resize((LOGO_W * 2, LOGO_H * 2), Image.LANCZOS)


def textures(out_dir):
    """Writes the wheel's textures under out_dir; returns how many."""
    ims = {
        'cc_card': _rounded(CW // 2, NODE_H // 2, 20, grad=0.66),
        'cc_outline': _rounded(CW // 2, NODE_H // 2, 20, ring=3),
        'cc_swatch': _rounded(60, 30, 4, ring=4),
        'cc_pm_plate': _plate(),
        'cc_dot_orbit': _soft(16, (225, 205, 160), 0.35),
        'cc_dot_gate': _dot(24, (240, 205, 120), (196, 160, 80)),
    }
    for mode, (border, core) in DOT_COL.items():
        ims[f'cc_dot_{mode}'] = _dot(24, border, core)
    for name, im in ims.items():
        path = os.path.join(out_dir, TEX, f'{name}.dds')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        icons.write_dds(im, path)
    return len(ims)
