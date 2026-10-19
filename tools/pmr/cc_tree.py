"""Company Culture: the full-screen window (Pat, 2026-10-19 14:43Z), opened from the company panel's Company Culture tab.

company_culture.py builds the lines, their script and their text; this module draws them. The window's body splits
70 / 30: on the left the two trees on a fixed canvas, Expansion (its root over the Vertical and Horizontal columns) and
Engineering (its root over its one column), each a root and three levels (Pat 14:58Z); on the right the board, the
company's executive with its subsidiaries' executives underneath. The window keeps the wheel's header (Culture level,
points, the bar to the next point) and its opening and closing (fullscreen()).

A node is the tech node, smaller: the round frame and the invention picture, a rounded card whose outline colour is its
tree's, the name, and its bullets; a branch's first node shows its subsidiary's industries and payment instead, and a
node opening a charter carries the vanilla charter button once bought (the charter row is off the panel's foot). Links
are straight lines in three colourings (done, open, locked), of which one shows.

A node reads its state from the executive's mirror, pmr_cc_st_<line>_<tier> (company_culture.effects, pmr_cc_states):
0 locked, 1 a click buys it, 2 next but short of points or of a week in the investment pool, 4 bought, 5 ruled out by
the other branch, 6 its subsidiary being paid for or its research grant running (an Engineering tier: grant_row), 7
nothing to found for this company.
"""
import os

import numpy as np
from PIL import Image, ImageDraw

import company_culture as cc   # circular: company_culture imports this module; used inside functions only
import bylaws
import company_panel
import icons
import subsidiaries

TEX = 'gfx/interface/pmr_company_culture'
WHITE = 'gfx/interface/backgrounds/white.dds'
FRAME_TEX = 'gfx/interface/backgrounds/round_frame_dec.dds'
ROUND_BG = 'gfx/interface/backgrounds/round_button_bg.dds'
WARNING = 'gfx/interface/icons/generic_icons/warning.dds'
CHECK = 'gfx/interface/icons/generic_icons/checkmark.dds'
GREEN_CHECK = 'gfx/interface/icons/generic_icons/green_checkmark.dds'
SG_SCOPE = 'GuiScope.SetRoot(Character.MakeScope)'
LOCAL = 'Company.GetCountry.IsLocalPlayer'

# The node card
NODE_W, NODE_H = 360, 156
FRAME, ICON = 104, 80                   # round frame and invention picture, as the tech node
CX = FRAME // 2                         # the card, from the frame's middle to the node's right
CW = NODE_W - CX
TX0 = FRAME + 10                        # the text column
TXW = NODE_W - TX0 - 12
BODY_Y = 50
CHARTER_Y = NODE_H - 50
GRANT_Y = NODE_H - 30                   # an Engineering tier's grant row (grant_row)
SB_ICON = 30

# The canvas: 1146 x 744, top-centred left of the board; with the board it fits the window at 1920 x 1080 and interface
# scale 1 (1825 x 810 below its header)
COL_X = {'vx': 0, 'hx': 376, 'en': 786}
ROOT_X = {'xr': (COL_X['vx'] + COL_X['hx']) // 2, 'er': COL_X['en']}
GAP = 40
ROW_Y = [r * (NODE_H + GAP) for r in range(4)]
CANVAS_W, CANVAS_H = COL_X['en'] + NODE_W, ROW_Y[-1] + NODE_H
DIVIDER_X = (COL_X['hx'] + NODE_W + COL_X['en']) // 2
LINK_W = 4

TREE_COL = {'exp': (206, 124, 80), 'eng': (98, 156, 214)}
CARD_COL = {'active': (30, 63, 77), 'pending': (20, 40, 48), 'bought': (55, 50, 44), 'locked': (12, 24, 30)}
LINK_COL = {'done': (214, 178, 120), 'active': (130, 190, 215), 'locked': (66, 80, 84)}
CLASSES = {'active': (1,), 'pending': (2, 6), 'bought': (4,), 'locked': (0, 5, 7)}

# The board: a fixed panel right of the trees, its seats and its bylaws
BOARD_W = 540                           # its contents; the panel is BOARD_W + 2 x BOARD_M
BOARD_M = 10
EXEC_H, SEAT_H = 104, 84                # character_portrait_medium (80 x 88), character_portrait_small2 (60 x 66), a share bar
IDEO = 36                               # a seat's ideology icon
SEAT_TX = 100
BADGE = 36
VOTE = 32
CARD_H = 136               # an open group's other bylaws, as vanilla's law item (country_panel_law_item, 170 x 65)
ROW_H = 97                 # the bylaw in force and a change under way: vanilla's active_law row (Pat 18:31Z)
ROW_ICON = 81              # its law icon (law_icon: 90% of 90)
SUP_H = 22                  # an open group's support line
LAW_ICON = 40
BAR_H = 8
SCROLL_W = 14                           # the board panel's scrollbar
APPROVE = 'gfx/interface/icons/generic_icons/approval_icon.dds'
DISAPPROVE = 'gfx/interface/icons/generic_icons/disapproval_icon.dds'

FULL = 'pmr_cc_full'                    # the GUI variable that opens the full-screen window
# The full-screen window lives in ingame_hud.gui, outside the company panel, so it reads the company from the
# executive the tab or its Open button stored on the player's country (pmr_cc_view_sgui).
VIEWED = "GetPlayer.MakeScope.Var('pmr_cc_exec').GetCharacter"
VIEW = ("GetScriptedGui('pmr_cc_view_sgui').Execute(GuiScope.SetRoot(Company.GetExecutive.MakeScope)"
        ".AddScope('player', GetPlayer.MakeScope).End)")


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


# ---------------------------------------------------------------------------------------------------------------
# Layout

def corner(k, t):
    """A node's top left on the canvas."""
    if cc.BY_KEY[k].root:
        return ROOT_X[k], ROW_Y[0]
    return COL_X[k], ROW_Y[t]


def links():
    """[(parent node, child node, segments)]; a segment is a rectangle (x, y, w, h). A root's link to a first tier
    drops to the middle of the gap, runs across and drops again; the drop under the root is drawn once, with the
    root (trunks())."""
    out = []
    for ln in cc.LINES:
        if ln.root:
            continue
        k = ln.key
        rk = cc.ROOT_OF[ln.tree]
        rx, ry = corner(rk, 1)
        cx = COL_X[k] + NODE_W // 2
        rcx = rx + NODE_W // 2
        y0, y1 = ry + NODE_H, ROW_Y[1]
        ym = (y0 + y1) // 2
        if cx == rcx:
            segs = [(cx - LINK_W // 2, y0, LINK_W, y1 - y0)]
        else:
            lo, hi = min(cx, rcx), max(cx, rcx)
            segs = [(lo - LINK_W // 2, ym - LINK_W // 2, hi - lo + LINK_W, LINK_W),
                    (cx - LINK_W // 2, ym, LINK_W, y1 - ym)]
        out.append(((rk, 1), (k, 1), segs))
        for t in range(2, ln.tiers + 1):
            out.append(((k, t - 1), (k, t), [(cx - LINK_W // 2, ROW_Y[t - 1] + NODE_H, LINK_W, GAP)]))
    return out


def trunks():
    """The drop under a root whose first tiers sit beside it: (root, segment)."""
    out = []
    for tree, rk in cc.ROOT_OF.items():
        rx, ry = corner(rk, 1)
        rcx = rx + NODE_W // 2
        if any(COL_X[ln.key] + NODE_W // 2 != rcx for ln in cc.LINES if ln.tree == tree and not ln.root):
            y0 = ry + NODE_H
            out.append((rk, (rcx - LINK_W // 2, y0, LINK_W, GAP // 2)))
    return out


def check_layout():
    boxes = {(ln.key, t): corner(ln.key, t) for ln, t in cc.NODES}
    keys = list(boxes)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            (ax, ay), (bx, by) = boxes[a], boxes[b]
            if abs(ax - bx) < NODE_W + 10 and abs(ay - by) < NODE_H + 10:
                cc.fail('cc_tree layout', f'{a} and {b} overlap')
    for x, y in boxes.values():
        if x < 0 or y < 0 or x + NODE_W > CANVAS_W or y + NODE_H > CANVAS_H:
            cc.fail('cc_tree layout', f'a node at {x}, {y} leaves the canvas')


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
        cc.fail('cc_tree', f'unbalanced braces ({depth})')
    return '\n'.join(out) + '\n'


def _vis(expr):
    return f'visible = "[{expr}]"\n' if expr else ''


def _rgb(c, a=1):
    return f'color = {{ {c[0] / 255:.3f} {c[1] / 255:.3f} {c[2] / 255:.3f} {a} }}\n'


def _rect(seg, col, vis=None):
    x, y, w, h = seg
    return (f'icon = {{\n{_vis(vis)}position = {{ {x} {y} }}\nsize = {{ {w} {h} }}\ntexture = "{WHITE}"\n{_rgb(col)}'
            'alwaystransparent = yes\n}\n')


def _textbox(x, y, w, h, text, size, extra=''):
    return (f'textbox = {{\nposition = {{ {x} {y} }}\nsize = {{ {w} {h} }}\nalign = left|nobaseline\n'
            f'fontsize = {size}\nfontsize_min = {max(12, size - 8)}\nelide = right\n{extra}text = "{text}"\n'
            'alwaystransparent = yes\n}\n')


def link_gui(a, b, segs):
    """One link in its three colourings: done once both ends are bought, open while its child is next, locked
    otherwise."""
    done = AND(ST(*b, 4), ST(*a, 4))
    active = ST(*b, 1, 2, 6)
    modes = {'locked': f'Not({OR(done, active)})', 'active': active, 'done': done}
    return ''.join(f'container = {{\n{_vis(vis)}' + ''.join(_rect(s, LINK_COL[m]) for s in segs) + '}\n'
                   for m, vis in modes.items())


def trunk_gui(rk, seg):
    return ''.join(_rect(seg, LINK_COL[m], vis) for m, vis in
                   (('done', ST(rk, 1, 4)), ('active', ST(rk, 1, 1, 2)), ('locked', f'Not({ST(rk, 1, 1, 2, 4)})')))


def sub_body(p, ln):
    """A branch's first node: its subsidiary's industries (the company type's own list, pmr_cc_k_sb<n>_<j>), what it
    costs a week, and while it is paid for the weeks paid."""
    n = ln.sub
    out = ''
    for j in subsidiaries.SLOTS:
        cands = sorted({v['sb'][n - 1][j - 1] for v in p.comp.values() if len(v['sb'][n - 1]) >= j})
        x = TX0 + (j - 1) * (SB_ICON + 3)
        out += ''.join(f'icon = {{\n{_vis(EQ(f"pmr_cc_k_sb{n}_{j}", p.sb_types.index(b) + 1))}'
                       f'position = {{ {x} {BODY_Y} }}\nsize = {{ {SB_ICON} {SB_ICON} }}\ntexture = "{p.sb_icon[b]}"\n'
                       f'tooltip = "{b}"\n}}\n' for b in cands)
    py = BODY_Y + SB_ICON + 4
    paying, done = ST(ln.key, 1, 6), ST(ln.key, 1, 4)
    return (out
            + f'textbox = {{\n{_vis(f"Not({OR(paying, done)})")}position = {{ {TX0} {py} }}\nsize = {{ {TXW} 22 }}\n'
            f'align = left|nobaseline\nfontsize = 18\nelide = right\ntext = "PMR_SB_PAY_{n}"\nalwaystransparent = yes\n}}\n'
            f'widget = {{\n{_vis(paying)}position = {{ {TX0} {py + 4} }}\nsize = {{ {TXW - 8} 14 }}\n'
            'alwaystransparent = yes\ngold_progressbar_horizontal = {\nsize = { 100% 100% }\nblockoverride "values" {\n'
            f'min = 0\nmax = {subsidiaries.SB_WEEKS}\nvalue = "[FixedPointToFloat({V("pmr_sb_w")})]"\n}}\n}}\n}}\n')


def grant_row(k, t):
    """An Engineering tier (Pat 15:54Z): its research grant at the card's foot, the weekly cost while it is next, the
    green bar of paid weeks while it runs."""
    nxt, running = ST(k, t, 1, 2), ST(k, t, 6)
    return (f'textbox = {{\n{_vis(nxt)}position = {{ {TX0} {GRANT_Y} }}\nsize = {{ {TXW} 24 }}\n'
            'align = left|nobaseline\nfontsize = 18\nelide = right\ntext = "PMR_RG_PAY"\nalwaystransparent = yes\n}\n'
            f'widget = {{\n{_vis(running)}position = {{ {TX0} {GRANT_Y + 6} }}\nsize = {{ {TXW - 8} 14 }}\n'
            'alwaystransparent = yes\ngreen_progressbar_horizontal = {\nsize = { 100% 100% }\nblockoverride "values" {\n'
            f'min = 0\nmax = {cc.GRANT_WEEKS}\nvalue = "[FixedPointToFloat({V("pmr_rg_w")})]"\n}}\n}}\n}}\n')


PG_NONE = 'IsDataModelEmpty(Company.GetPrestigeGoods)'


def prestige_badge():
    """Hallmark Goods: the company's first prestige good (vanilla company_panel.gui lists them), top right."""
    return (f'flowcontainer = {{\n{_vis(f"Not({PG_NONE})")}position = {{ {NODE_W - 52} 6 }}\n'
            "datamodel = \"[DataModelFirst(Company.GetPrestigeGoods, '(int32)1')]\"\nitem = {\n"
            f'widget = {{\nsize = {{ 44 44 }}\n'
            f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{ROUND_BG}"\nalwaystransparent = yes\n}}\n'
            'icon = {\nparentanchor = center\nsize = { 34 34 }\ntexture = "[Goods.GetTexture]"\ntooltip = "[Goods.GetName]"\n}\n'
            '}\n}\n}\n')


CHARTER_TEST = {'trade_charter': 'IsTradeCharter', 'investment_charter': 'IsInvestmentCharter',
                'industry_charter': 'IsIndustryCharter', 'monopoly_charter': 'IsMonopolyCharter',
                'colonization_charter': 'IsColonizationCharter'}
TARGETS = 'Or(CompanyCharterType.IsTargettingRegions, CompanyCharterType.IsTargettingBuildings)'
ACTIVE = ('Or(And(CompanyCharterType.IsTradeCharter, Company.HasAnyTradeCharterActive), '
          'And(CompanyCharterType.IsInvestmentCharter, Company.HasAnyInvestmentCharterActive))')
TOGGLE = 'Company.ToggleCharter(CompanyCharterType.Self)'


def charter_gui(k, t, charter):
    """The charter a node opens, at the card's foot. Bought: the vanilla charter button, as the company panel's charter
    row drew it (company_panel.gui, "COMPANY CHARTER BUTTONS - DO NOT OWN DLC"; a charter aimed at regions or buildings
    opens vanilla's target menu, the others ask to confirm). Otherwise its icon and name, faint."""
    test = CHARTER_TEST[charter]
    size = f'size = {{ {NODE_W - TX0 + 2} 44 }}\n'
    pick = ('datamodel = "[GetCompanyCharterTypes]"\nitem = {\n'
            f'container = {{\n{_vis(f"CompanyCharterType.{test}")}')
    bought = AND(LOCAL, ST(k, t, 4))
    plate = (f'flowcontainer = {{\n{_vis(bought)}position = {{ {TX0 - 4} {CHARTER_Y} }}\n'
             'direction = vertical\nignoreinvisible = yes\n' + pick
             + f'company_charter_button_horizontal = {{\n{_vis(TARGETS)}{size}'
             'blockoverride "onclick" {\nonclick = "[RightClickMenuManager.ToggleCompanyCharterType(CompanyCharterType.AccessSelf, '
             'Company.AccessSelf, PdxGuiWidget.AccessSelf)]"\n}\n'
             'blockoverride "button_style" {\nusing = default_button\n}\n}\n'
             f'container = {{\n{_vis(f"Not({TARGETS})")}'
             f'company_charter_active_widget_horizontal = {{\n{_vis(ACTIVE)}{size}'
             # vanilla puts this block's onclick on an icon, which logs an error per widget (gui.log)
             'blockoverride "onclick" {}\n}\n'
             f'company_charter_button_horizontal = {{\n{_vis(f"Not({ACTIVE})")}{size}enabled = "[IsValid({TOGGLE})]"\n'
             f'blockoverride "onclick" {{\nonclick = "[PopupManager.AskConfirmationWithSound({TOGGLE}, '
             "'event:/SFX/UI/CompanyCharters/company_charter_grant')]\"\nusing = icon_toggle_single_on_sound\n}\n"
             'blockoverride "charter_tooltip" {\ntooltipwidget = {\nFancyTooltip_CompanyCharterType = {\n'
             'blockoverride "tooltip_content_before" {\n'
             f'custom_tooltip_textbox = {{\nvisible = "[StringIsEmpty(GetDesc({TOGGLE}))]"\ntext = "GRANT_COMPANY_CHARTER_GENERIC_TOOLTIP"\n}}\n'
             f'custom_tooltip_textbox_with_empty_line = {{\nvisible = "[Not(StringIsEmpty(GetDesc({TOGGLE})))]"\ntext = "[GetDesc({TOGGLE})]"\n}}\n'
             'custom_tooltip_textbox_with_empty_line = {\ndatacontext = "[Company.GetCountry]"\ntext = "USING_X_FREE_CHARTERS"\n}\n'
             '}\n}\n}\n}\n}\n}\n}\n}\n}\n')
    preview = (f'flowcontainer = {{\n{_vis(f"Not({bought})")}position = {{ {TX0} {CHARTER_Y + 2} }}\n'
               'direction = vertical\nignoreinvisible = yes\nalpha = 0.6\n' + pick
               + f'widget = {{\nsize = {{ {NODE_W - TX0 - 12} 40 }}\n'
               f'icon = {{\nsize = {{ 40 40 }}\ntexture = "{FRAME_TEX}"\nalwaystransparent = yes\n}}\n'
               'icon = {\nposition = { 6 6 }\nsize = { 28 28 }\ntexture = "[CompanyCharterType.GetIcon]"\nalwaystransparent = yes\n}\n'
               f'textbox = {{\nposition = {{ 48 0 }}\nsize = {{ {NODE_W - TX0 - 60} 40 }}\nalign = left|nobaseline\n'
               'fontsize = 18\nfontsize_min = 12\nelide = right\ntext = "[CompanyCharterType.GetNameNoFormatting]"\n'
               'alwaystransparent = yes\n}\n}\n}\n}\n}\n')
    return plate + preview


def node(p, ln, t, x, y):
    """The node for one tier, top left at (x, y) on the canvas."""
    k = ln.key
    st = f'pmr_cc_st_{k}_{t}'
    cls = {c: ST(k, t, *v) for c, v in CLASSES.items()}
    locked = cls['locked']
    tt = f'tooltip = "PMR_CC_TT_{k}_{t}"\n'
    sg = "GetScriptedGui('pmr_cc_pick_sgui')"
    scope = f"{SG_SCOPE}.AddScope('line', MakeScopeValue('(CFixedPoint){ln.node(t)}')).End"
    can = AND(LOCAL, EQ(st, 1), f'{sg}.IsValid({scope})')
    click = f'enabled = "[{can}]"\nonclick = "[{sg}.Execute({scope})]"\n'
    tc = TREE_COL[ln.tree]
    out = f'widget = {{\nposition = {{ {x} {y} }}\nsize = {{ {NODE_W} {NODE_H} }}\n{tt}'
    # the card by state, its outline by tree (fainter while locked, faintest when ruled out)
    card = f'position = {{ {CX} 0 }}\nsize = {{ {CW} {NODE_H} }}\nalwaystransparent = yes\n'
    for c, col in CARD_COL.items():
        if c == 'locked':
            out += f'icon = {{\n{_vis(ST(k, t, 0, 7))}{card}texture = "{TEX}/cc_card.dds"\n{_rgb(col)}}}\n'
            out += f'icon = {{\n{_vis(ST(k, t, 5))}{card}texture = "{TEX}/cc_card.dds"\n{_rgb(col, 0.6)}}}\n'
        else:
            out += f'icon = {{\n{_vis(cls[c])}{card}texture = "{TEX}/cc_card.dds"\n{_rgb(col)}}}\n'
    out += f'icon = {{\n{_vis(f"Not({locked})")}{card}texture = "{TEX}/cc_outline.dds"\n{_rgb(tc)}}}\n'
    out += f'icon = {{\n{_vis(ST(k, t, 0, 7))}{card}texture = "{TEX}/cc_outline.dds"\n{_rgb(tc, 0.65)}}}\n'
    out += f'icon = {{\n{_vis(ST(k, t, 5))}{card}texture = "{TEX}/cc_outline.dds"\n{_rgb(tc, 0.45)}}}\n'
    # a click on the card buys it
    out += (f'button = {{\n{_vis(cls["active"])}{card.replace("alwaystransparent = yes", "")}'
            f'using = technology_confirm_button_sound\n{click}{tt}}}\n')
    # name, divider and what it does; dimmed while locked
    text = (_textbox(TX0, 8, TXW - (44 if (k, t) == ('en', 3) else 0), 34, f'PMR_CC_NAME_{k}_{t}', 24)
            + f'icon = {{\nposition = {{ {TX0} 44 }}\nsize = {{ {TXW} 2 }}\ntexture = "{WHITE}"\n'
            f'{_rgb((200, 185, 150), 0.35)}alwaystransparent = yes\n}}\n')
    if ln.sub and t == 1:
        text += sub_body(p, ln)
    elif cc.fx_lines(k, t):
        text += (f'textbox = {{\nposition = {{ {TX0} {BODY_Y} }}\nautoresize = yes\n'
                 f'maximumsize = {{ {TXW} {(CHARTER_Y if t in ln.charters else GRANT_Y if k in cc.GRANTS else NODE_H) - BODY_Y - 4} }}\nmultiline = yes\n'
                 f'align = left|nobaseline\nfontsize = 19\nfontsize_min = 14\nelide = right\ntext = "PMR_CC_FX_{k}_{t}"\n'
                 'alwaystransparent = yes\n}\n')
    out += (f'widget = {{\n{_vis(f"Not({locked})")}size = {{ 100% 100% }}\n{text}}}\n'
            f'widget = {{\n{_vis(locked)}size = {{ 100% 100% }}\nalpha = 0.55\n{text}}}\n')
    # the round frame and the picture, greyed while locked
    fy, iy = (NODE_H - FRAME) // 2, (NODE_H - ICON) // 2
    frame = f'position = {{ 0 {fy} }}\nsize = {{ {FRAME} {FRAME} }}\ntexture = "{FRAME_TEX}"\nalwaystransparent = yes\n'
    out += (f'icon = {{\n{_vis(f"Not({locked})")}{frame}}}\n'
            f'icon = {{\n{_vis(locked)}{frame}color = {{ 0.5 0.5 0.5 1 }}\n}}\n')
    # Pat 17:55Z: Engineering's second tier shows the company's trade (company_culture.SECTORS, pmr_cc_k_sec)
    pics = ([(f'Not({GT("pmr_cc_k_sec", 1)})' if i == 1 else EQ('pmr_cc_k_sec', i), icon)
             for i, (_n, icon, _g) in enumerate(cc.SECTORS, 1)] if (k, t) == cc.SECTOR_NODE
            else [(None, ln.icons[t - 1])])
    for sec, icon in pics:
        pic = f'position = {{ {(FRAME - ICON) // 2} {iy} }}\nsize = {{ {ICON} {ICON} }}\ntexture = "{icon}"\n'
        both = lambda c: AND(sec, c) if sec else c   # noqa: E731
        out += (f'button = {{\n{_vis(both(cls["active"]))}{pic}using = technology_confirm_button_sound\n{click}{tt}}}\n'
                f'icon = {{\n{_vis(both(OR(cls["pending"], cls["bought"])))}{pic}{tt}}}\n'
                f'icon = {{\n{_vis(both(locked))}{pic}color = {{ 0.4 0.4 0.4 1 }}\n{tt}}}\n')
    # the cost in points, where the tech node shows its era
    if ln.cost[t - 1]:
        out += (f'widget = {{\n{_vis(f"Not({cls["bought"]})")}position = {{ {FRAME // 2 - 18} {fy + FRAME - 26} }}\n'
                f'size = {{ 36 36 }}\ntooltip = "PMR_CC_COST_TT"\n'
                f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{ROUND_BG}"\n}}\n'
                f'textbox = {{\nraw_text = "{ln.cost[t - 1]}"\nparentanchor = center\nautoresize = yes\n'
                'align = center|nobaseline\nfontsize = 20\nalwaystransparent = yes\n}\n}\n')
    # bought: the tech node's ticks
    out += (f'widget = {{\n{_vis(cls["bought"])}size = {{ 40 40 }}\nparentanchor = bottom|right\nposition = {{ -6 -6 }}\n'
            f'icon = {{\nsize = {{ 40 40 }}\ntexture = "{ROUND_BG}"\nparentanchor = center\n}}\n'
            f'icon = {{\ntexture = "{CHECK}"\nsize = {{ 48 48 }}\nparentanchor = center\n}}\n}}\n'
            f'icon = {{\n{_vis(cls["bought"])}size = {{ 36 36 }}\nposition = {{ 2 {fy + 2} }}\ntexture = "{ROUND_BG}"\n'
            f'icon = {{\nsize = {{ 80% 80% }}\nparentanchor = center\ntexture = "{GREEN_CHECK}"\n}}\n}}\n')
    # can be bought: the add button; ruled out: the warning
    out += (f'button_icon_plus_action = {{\n{_vis(cls["active"])}position = {{ 0 {fy} }}\nsize = {{ 38 38 }}\n'
            f'using = tooltip_ne\n{click}{tt}}}\n'
            f'icon = {{\n{_vis(ST(k, t, 5))}position = {{ 4 {fy + 4} }}\nsize = {{ 30 30 }}\ntexture = "{WARNING}"\n'
            'alwaystransparent = yes\n}\n')
    if (k, t) == ('en', 3):
        out += prestige_badge()
    if t in ln.charters:
        out += charter_gui(k, t, ln.charters[t])
    if k in cc.GRANTS:
        out += grant_row(k, t)
    return out + '}\n'


def trees(p):
    """The canvas: the divider between the trees, the links, the nodes."""
    check_layout()
    out = (f'icon = {{\nposition = {{ {DIVIDER_X - 1} 0 }}\nsize = {{ 2 {CANVAS_H} }}\ntexture = "{WHITE}"\n'
           f'{_rgb((200, 185, 150), 0.18)}alwaystransparent = yes\n}}\n')
    for rk, seg in trunks():
        out += trunk_gui(rk, seg)
    for a, b, segs in links():
        out += link_gui(a, b, segs)
    for ln, t in cc.NODES:
        out += node(p, ln, t, *corner(ln.key, t))
    return (f'widget = {{\nparentanchor = hcenter\nposition = {{ 0 8 }}\nsize = {{ {CANVAS_W} {CANVAS_H} }}\n{out}}}\n')


def _badge(x, y, n, tt):
    """A seat's votes: its weight on the round plate, what it comes from on hover (Pat 18:03Z)."""
    return (f'widget = {{\nposition = {{ {x} {y} }}\nsize = {{ {BADGE} {BADGE} }}\ntooltip = "{tt}"\n'
            f'icon = {{\nsize = {{ 100% 100% }}\ntexture = "{ROUND_BG}"\n}}\n'
            f'textbox = {{\n{n}\nparentanchor = center\nautoresize = yes\nalign = center|nobaseline\nfontsize = 20\n'
            'alwaystransparent = yes\n}\n}\n')


def _vote(x, y, value):
    """A seat's vote on the change under way: for, against, or nothing while it doesn't care."""
    under_way = GT('pmr_bl_pg', 0)
    return ''.join(f'icon = {{\n{_vis(AND(under_way, f"EqualTo_CFixedPoint({value}, \'(CFixedPoint){v}\')"))}'
                   f'position = {{ {x} {y} }}\nsize = {{ {VOTE} {VOTE} }}\ntexture = "{tex}"\nalwaystransparent = yes\n}}\n'
                   for v, tex in ((1, APPROVE), (-1, DISAPPROVE)))


def _ideology(x, y, who):
    """Character `who`'s ideology (Pat 16:53Z), its name and its views of the bylaws on hover (Pat 17:44Z;
    bylaws.custom_loc). who: a bylaws.WHO key."""
    return (f'icon = {{\ndatacontext = "[{bylaws.WHO[who]}.GetIdeology]"\nposition = {{ {x} {y} }}\n'
            f'size = {{ {IDEO} {IDEO} }}\ntexture = "[Ideology.GetTexture]"\ntooltip = "PMR_BL_IDEO_{who}"\n}}\n')


def _share(h, share, tt):
    """A seat's share of all the board's votes (Pat 19:23Z: "bars representing their share of power from the whole"),
    along the card's foot, and the share; its votes, all votes and its target on hover (Pat 20:34Z)."""
    return (f'widget = {{\nposition = {{ {SEAT_TX} {h - 26} }}\nsize = {{ {BOARD_W - SEAT_TX - 10} 24 }}\ntooltip = "{tt}"\n'
            f'widget = {{\nposition = {{ 0 10 }}\nsize = {{ {BOARD_W - SEAT_TX - 74} {BAR_H} }}\n'
            'alwaystransparent = yes\ngold_progressbar_horizontal = {\nsize = { 100% 100% }\nblockoverride "values" {\n'
            f'min = 0\nmax = 1\nvalue = "[FixedPointToFloat({share})]"\n}}\n}}\n}}\n'
            f'textbox = {{\nposition = {{ {BOARD_W - 66 - SEAT_TX} 2 }}\nsize = {{ 56 22 }}\nalign = right|nobaseline\n'
            f'fontsize = 16\ntext = "[{share}|%0]"\nalwaystransparent = yes\n}}\n}}\n')


def _seat(h, picture, name, sub, weight, vote, share, vis=None, ctx='', who=None, tt='', share_tt=''):
    """One seat of the board: its picture, its name (and its company), its character's ideology, its votes, its vote
    and its share of all the votes."""
    yc = h // 2
    w = BOARD_W - SEAT_TX - BADGE - VOTE - 30 - (IDEO + 8 if who else 0)
    lines = (_textbox(SEAT_TX, yc - (34 if sub else 19), w, 30, name, 22)
             + (_textbox(SEAT_TX, yc - 2, w, 26, sub, 17) if sub else ''))
    ideo = _ideology(BOARD_W - BADGE - VOTE - 26 - IDEO, yc - IDEO // 2, who) if who else ''
    return (f'widget = {{\n{_vis(vis)}{ctx}size = {{ {BOARD_W} {h} }}\nbackground = {{\nusing = entry_bg\n}}\n'
            + picture + lines + ideo + _badge(BOARD_W - BADGE - VOTE - 18, yc - BADGE // 2, weight, tt)
            + _vote(BOARD_W - VOTE - 8, yc - VOTE // 2, vote) + _share(h, share, share_tt) + '}\n')


def _ig_picture(h, ig):
    size = SEAT_H - 18
    return (f'icon = {{\nposition = {{ {(SEAT_TX - size) // 2} {(h - size) // 2} }}\nsize = {{ {size} {size} }}\n'
            f'texture = "{bylaws.IG_ICON.format(bylaws.IG_TEX[ig])}"\nalwaystransparent = yes\n}}\n')


def seats():
    """The executive, each subsidiary's executive, the shareholders and the Workers Council (while there is one), each
    with its votes: bylaws.pmr_bl_count."""
    exe = _seat(EXEC_H, f'character_portrait_medium = {{\nposition = {{ {(SEAT_TX - 80) // 2} 4 }}\n'
                         'datacontext = "[Company.GetExecutive]"\n}\n',
                '[Company.GetExecutive.GetFullNameNoFormatting]', '[Company.GetNameNoFormatting]',
                f'text = "[{V("pmr_bl_w_x")}|0]"', V('pmr_bl_v_ex'), V('pmr_bl_sh_x'), who='EX', tt='PMR_BL_VOTES_X',
                share_tt='PMR_BL_SHARE_X')
    sub = _seat(SEAT_H, f'character_portrait_small2 = {{\nposition = {{ {(SEAT_TX - 60) // 2} 4 }}\n'
                         'datacontext = "[Company.GetExecutive]"\n}\n',
                '[Company.GetExecutive.GetFullNameNoFormatting]', '[Company.GetNameNoFormatting]',
                "text = \"[Company.MakeScope.Var('pmr_bl_w').GetValue|0]\"", "Company.MakeScope.Var('pmr_bl_v').GetValue",
                "Company.MakeScope.Var('pmr_bl_sh').GetValue",
                ctx='datacontext = "[Scope.GetCompany]"\n', who='EX', tt='PMR_BL_VOTES_B', share_tt='PMR_BL_SHARE_B')
    subs = (f'flowcontainer = {{\ndirection = vertical\nspacing = 6\nignoreinvisible = yes\n'
            f'datamodel = "[{company_panel.SUBS}]"\nitem = {{\n{sub}}}\n}}\n')
    # Pat 16:53Z: the shareholders' seat is the country's Industrialists' leader (pmr_bl_shl), while there is one;
    # Pat 17:44Z: the Workers Council's is the Trade Unions' leader (pmr_bl_wcl)
    share_w = f'text = "[{V("pmr_bl_w_h")}|0]"'
    share = (_seat(SEAT_H, _var_portrait('pmr_bl_shl'), f'[{bylaws.WHO["SH"]}.GetFullNameNoFormatting]',
                   'PMR_BL_SHAREHOLDERS', share_w, V('pmr_bl_v_sh'), V('pmr_bl_sh_h'), vis=EQ('pmr_bl_shx', 1), who='SH',
                   tt='PMR_BL_VOTES_H', share_tt='PMR_BL_SHARE_H')
             + _seat(SEAT_H, _ig_picture(SEAT_H, 'ig_industrialists'), 'PMR_BL_SHAREHOLDERS', None,
                     share_w, V('pmr_bl_v_sh'), V('pmr_bl_sh_h'), vis=f'Not({EQ("pmr_bl_shx", 1)})', tt='PMR_BL_VOTES_H',
                     share_tt='PMR_BL_SHARE_H'))
    council_w = f'text = "[{V("pmr_bl_w_w")}|0]"'
    council = (_seat(SEAT_H, _var_portrait('pmr_bl_wcl'), f'[{bylaws.WHO["WC"]}.GetFullNameNoFormatting]',
                     'PMR_BL_COUNCIL', council_w, V('pmr_bl_v_wc'), V('pmr_bl_sh_w'), vis=AND(GT('pmr_bl_wc', 0), EQ('pmr_bl_wcx', 1)),
                     who='WC', tt='PMR_BL_VOTES_W', share_tt='PMR_BL_SHARE_W')
               + _seat(SEAT_H, _ig_picture(SEAT_H, 'ig_trade_unions'), 'PMR_BL_COUNCIL', None, council_w,
                       V('pmr_bl_v_wc'), V('pmr_bl_sh_w'), vis=AND(GT('pmr_bl_wc', 0), f'Not({EQ("pmr_bl_wcx", 1)})'),
                       tt='PMR_BL_VOTES_W', share_tt='PMR_BL_SHARE_W'))
    return exe + subs + share + council


def _var_portrait(var):
    """The portrait of the character held in the executive's variable `var`. Pat 17:23Z: a Character read off a
    variable drew the empty silhouette; vanilla draws a variable's character from the Scope (ep2_japan_widgets.gui,
    emperor_var), so this does too, with no button, icons or frame that would read the window's Character (the
    executive)."""
    return (f'character_portrait_small2 = {{\nposition = {{ {(SEAT_TX - 60) // 2} 4 }}\n'
            f"datacontext = \"[Character.MakeScope.Var('{var}')]\"\n"
            'blockoverride "portrait_texture" {\nportrait_texture = "[Scope.GetCharacter.GetPortrait('
            "'environment_standard', 'camera_head', 'idle', GetPortraitRenderSize(PdxGuiWidget.Self))]\"\n}\n"
            'blockoverride "portrait_frame" {\nicon = {\nsize = { 100% 100% }\n'
            'texture = "gfx/interface/portraits/portrait_frame_head.dds"\n}\n}\n'
            'blockoverride "portrait_button" {}\nblockoverride "portrait_icons" {}\n'
            'blockoverride "tooltip" {\ntooltipwidget = {\nFancyTooltip_Character = {\n'
            'datacontext = "[Scope.AccessCharacter]"\n}\n}\n}\n}\n')


def _law_text(x, w, g, c, extra=''):
    """A law row's group name over its law's name, as vanilla's active_law (politics_panel_types.gui): #title over
    #variable, extra-large, bold."""
    return (f'textbox = {{\nposition = {{ {x} 16 }}\nsize = {{ {w} 22 }}\nalign = left|nobaseline\nelide = right\n'
            f'default_format = "#title"\ntext = "PMR_BL_GROUP_{g}"\nalwaystransparent = yes\n}}\n'
            f'textbox = {{\nposition = {{ {x} 38 }}\nsize = {{ {w} 32 }}\nalign = left|nobaseline\nelide = right\n'
            f'default_format = "#variable"\nusing = fontsize_xl\ntext = "PMR_BL_ROW_{c}"\nalwaystransparent = yes\n}}\n'
            + extra)


def bylaw_card(g, i, kind, n=3):
    """One bylaw. Pat 18:31Z ("bylaws need to be formatted and look like regular laws"): the bylaw in force ('law') is
    a row of vanilla's Power Structure laws (active_law: its icon, the group's name over the bylaw's, the toggle on the
    right; its effects on hover), and a click opens the others; a change under way ('pending') is a row like it, its
    bar under the name and its cancel on the right, who backs it and who opposes it on hover (Pat 17:43Z). Pat 18:32Z
    ("I like the drop down layout and support + color coded tool tips"): open, the others ('alt', n in the group) show
    their effects and support, and a click on one starts the change (bylaws.pmr_bl_pick_sgui)."""
    c = bylaws.code(g, i)
    sg = "GetScriptedGui('pmr_bl_pick_sgui')"
    scope = f"{SG_SCOPE}.AddScope('opt', MakeScopeValue('(CFixedPoint){c}')).End"
    under_way = EQ('pmr_bl_pg', g)
    now = EQ(f'pmr_bl_{g}', i)
    toggle = f'onclick = "[GetVariableSystem.Toggle(\'pmr_bl_open_{g}\')]"\n'
    if kind in ('law', 'pending'):
        icon = (f'icon = {{\nposition = {{ 9 {(ROW_H - ROW_ICON) // 2} }}\nsize = {{ {ROW_ICON} {ROW_ICON} }}\n'
                f'texture = "{bylaws.LAW_ICON.format(bylaws.ICON[c])}"\nalwaystransparent = yes\n}}\n')
        tx = ROW_ICON + 20
        tw = BOARD_W - tx - 60
        if kind == 'law':
            tt = f'tooltip = "PMR_BL_FX_{c}"\n' if bylaws.fx(c) else ''
            right = (f'icon = {{\nposition = {{ {BOARD_W - 46} {(ROW_H - 30) // 2} }}\nsize = {{ 30 30 }}\n'
                     'texture = "gfx/interface/icons/generic_icons/toggle.dds"\nalwaystransparent = yes\n}\n')
            return (f'button = {{\n{_vis(now)}size = {{ {BOARD_W} {ROW_H} }}\nusing = default_button\n{toggle}{tt}'
                    + icon + _law_text(tx, tw, g, c) + right + '}\n')
        cancel = "GetScriptedGui('pmr_bl_cancel_sgui')"
        end = f'{SG_SCOPE}.End'
        bar = (f'widget = {{\nposition = {{ {tx} 74 }}\nsize = {{ {tw} {BAR_H} }}\ntooltip = "PMR_BL_BAR_TT"\n'
               'green_progressbar_horizontal = {\nsize = { 100% 100% }\nblockoverride "values" {\n'
               f'min = 0\nmax = 100\nvalue = "[FixedPointToFloat({V("pmr_bl_pp")})]"\n}}\n}}\n}}\n')
        right = (f'button_icon_cancel = {{\n{_vis(LOCAL)}position = {{ {BOARD_W - 46} {(ROW_H - 30) // 2} }}\n'
                 f'size = {{ 30 30 }}\nenabled = "[{cancel}.IsValid({end})]"\nonclick = "[{cancel}.Execute({end})]"\n}}\n')
        return (f'button = {{\n{_vis(AND(under_way, EQ("pmr_bl_pv", i)))}size = {{ {BOARD_W} {ROW_H} }}\n'
                f'using = default_button_primary\n{toggle}tooltip = "PMR_BL_TT_{c}"\n'
                + icon + _law_text(tx, tw, g, c, bar) + right + '}\n')
    w, h = (BOARD_W - 6 * (n - 2)) // (n - 1), CARD_H
    fx_h = h - LAW_ICON - 14 - 8 - BAR_H - SUP_H
    sup = V(f'pmr_bl_s_{c}')
    support = (''.join(f'icon = {{\n{_vis(f"{cmp}({sup}, \'(CFixedPoint)0\')")}position = {{ 10 {h - BAR_H - 8 - SUP_H} }}\n'
                       f'size = {{ {SUP_H} {SUP_H} }}\ntexture = "{tex}"\nalwaystransparent = yes\n}}\n'
                       for cmp, tex in (('GreaterThan_CFixedPoint', APPROVE), ('LessThan_CFixedPoint', DISAPPROVE)))
               + f'textbox = {{\nposition = {{ {SUP_H + 16} {h - BAR_H - 8 - SUP_H} }}\nsize = {{ 80 {SUP_H} }}\n'
               f'align = left|vcenter|nobaseline\nfontsize = 16\ntext = "PMR_BL_SUP_{c}"\nalwaystransparent = yes\n}}\n')
    inner = (f'icon = {{\nposition = {{ 8 8 }}\nsize = {{ {LAW_ICON} {LAW_ICON} }}\n'
             f'texture = "{bylaws.LAW_ICON.format(bylaws.ICON[c])}"\nalwaystransparent = yes\n}}\n'
             f'textbox = {{\nposition = {{ {LAW_ICON + 14} 6 }}\nsize = {{ {w - LAW_ICON - 20} 44 }}\n'
             'align = left|vcenter|nobaseline\nmultiline = yes\nfontsize = 17\nfontsize_min = 12\nelide = right\n'
             f'text = "PMR_BL_NAME_{c}"\nalwaystransparent = yes\n}}\n'
             + (f'textbox = {{\nposition = {{ 10 {LAW_ICON + 14} }}\nsize = {{ {w - 16} {fx_h} }}\n'
                'align = left|nobaseline\nmultiline = yes\nfontsize = 14\nfontsize_min = 12\nelide = right\n'
                f'text = "PMR_BL_FX_{c}"\nalwaystransparent = yes\n}}\n' if bylaws.fx(c) else '')
             + support)
    return (f'button = {{\n{_vis(f"Not({now})")}size = {{ {w} {h} }}\nusing = default_button\n'
            f'enabled = "[And({LOCAL}, {sg}.IsValid({scope}))]"\nonclick = "[{sg}.Execute({scope})]"\n'
            f'onclick = "[GetVariableSystem.Clear(\'pmr_bl_open_{g}\')]"\n'
            f'tooltip = "PMR_BL_TT_{c}"\n{inner}}}\n')


def bylaw_group(g, names):
    """One group of bylaws: the bylaw in force, the change under way under it, and open, the others."""
    n = range(1, len(names) + 1)
    return (f'flowcontainer = {{\ndirection = vertical\nspacing = 6\nignoreinvisible = yes\n'
            + ''.join(bylaw_card(g, i, 'law') for i in n) + ''.join(bylaw_card(g, i, 'pending') for i in n)
            + f'flowcontainer = {{\n{_vis(f"GetVariableSystem.Exists(\'pmr_bl_open_{g}\')")}direction = horizontal\n'
            'spacing = 6\nignoreinvisible = yes\n'
            + ''.join(bylaw_card(g, i, 'alt', len(names)) for i in n) + '}\n}\n')


def board():
    """The board (Pat 14:43Z, 15:37Z): its seats, then the bylaws it passes (bylaws.py)."""
    def header(key):
        return (f'default_header = {{\nblockoverride "text" {{\ntext = "{key}"\n}}\n'
                f'blockoverride "size" {{\nsize = {{ {BOARD_W} 38 }}\n}}\n}}\n')
    return (f'flowcontainer = {{\nmargin = {{ {BOARD_M} 10 }}\ndirection = vertical\nspacing = 6\nignoreinvisible = yes\n'
            + header('PMR_CC_BOARD') + seats()
            + 'widget = {\nsize = { 10 8 }\n}\n'
            + header('PMR_BL_HEADER')
            + ''.join(bylaw_group(g, names) for g, _n, names in bylaws.GROUPS)
            + '}\n')


def body(p, ready):
    """The window's body: the trees, top-centred in what the board leaves, and the board."""
    return (f'hbox = {{\n{_vis(ready)}layoutpolicy_horizontal = expanding\nlayoutpolicy_vertical = expanding\n'
            'margin = { 10 6 }\nspacing = 12\n'
            'widget = {\nlayoutpolicy_horizontal = expanding\nlayoutpolicy_vertical = expanding\nscissor = yes\n'
            # the tech tree's backdrop painting
            'background = {\nusing = illu_alpha\nfittype = center\n'
            'texture = "gfx/interface/illustrations/tech_tree/illustration_tech_production.dds"\n}\n'
            + trees(p) + '}\n'
            f'widget = {{\nsize = {{ {BOARD_W + 2 * BOARD_M + SCROLL_W} 0 }}\nlayoutpolicy_horizontal = fixed\n'
            'layoutpolicy_vertical = expanding\nscissor = yes\nbackground = {\nusing = dark_area\n}\n'
            # taller than the window at small resolutions or with several subsidiaries: it scrolls
            'scrollarea = {\nsize = { 100% 100% }\nscrollbarpolicy_horizontal = always_off\n'
            'scrollbar_vertical = {\nusing = vertical_scrollbar\n}\nscrollwidget = {\n'
            + board() + '}\n}\n}\n}\n')


# ---------------------------------------------------------------------------------------------------------------
# The tab

def header_gui(ready):
    """Culture level, points and the bar to the next point (the tab and the full-screen window)."""
    bar_value = f"FixedPointToFloat({V('pmr_cc_pct')})"
    return (
        f'widget = {{\n{_vis(ready)}parentanchor = hcenter\nsize = {{ 540 82 }}\nbackground = {{\nusing = entry_bg\n}}\n'
        'textbox = {\nposition = { 16 10 }\nautoresize = yes\nalign = left|nobaseline\nusing = fontsize_xxl\n'
        'text = "PMR_CC_LEVEL"\n}\n'
        'textbox = {\nposition = { 16 48 }\nautoresize = yes\nalign = left|nobaseline\ntext = "PMR_CC_POINTS"\n}\n'
        'widget = {\nposition = { 220 12 }\nsize = { 300 30 }\ntooltip = "PMR_CC_BAR_TT"\n'
        'gold_progressbar_horizontal = {\nsize = { 100% 100% }\nblockoverride "values" {\n'
        f'min = 0\nmax = 100\nvalue = "[{bar_value}]"\n}}\n}}\n'
        'textbox = {\nparentanchor = center\nautoresize = yes\nalign = hcenter|nobaseline\ntext = "PMR_CC_BAR"\n'
        'alwaystransparent = yes\n}\n}\n}\n')


def show_button(ready):
    """Every mirrored executive holds a cost (800 and up). Without one (a new executive this month, a save from before
    Company Culture) a button reads the company in, instead of an empty window."""
    return (f'button = {{\n{_vis(f"Not({ready})")}parentanchor = hcenter\nusing = default_button\nsize = {{ 300 40 }}\n'
            'text = "PMR_CC_SHOW"\n'
            f'onclick = "[GetScriptedGui(\'pmr_cc_refresh_sgui\').Execute({SG_SCOPE}.End)]"\n}}\n')


def tab(p):
    """The company panel's Company Culture tab: the summary, the button to the full-screen window, and the Methods
    table (company_panel.py). Returns the gui file with both types (the tab and pmr_cc_fullscreen)."""
    i1 = '\t\t'
    ready = GT('pmr_cc_cost', 0)
    open_button = (f'button = {{\n{_vis(ready)}parentanchor = hcenter\nusing = default_button_primary_big\n'
                   'size = { 400 50 }\ntext = "PMR_CC_OPEN"\n'
                   f'onclick = "[{VIEW}]"\nonclick = "[GetVariableSystem.Set(\'{FULL}\', \'yes\')]"\n}}\n')
    methods = f'{i1}pmr_cc_methods = {{}}\n'   # gui/pmr_company_methods.gui
    return ('# GENERATED by tools/pmr/company_culture.py and cc_tree.py\n'
            'types pmr_company_culture {\n'
            '\ttype company_panel_culture_tab = flowcontainer {\n'
            '\t\tdirection = vertical\n\t\tusing = default_list_position\n\t\tusing = default_content_fade\n'
            '\t\tspacing = 6\n\t\tmargin_bottom = 10\n\t\tminimumsize = { 540 -1 }\n'
            '\t\tdatacontext = "[Company.GetExecutive]"\n\n'
            + _reindent(show_button(ready) + header_gui(ready) + 'widget = {\nsize = { 10 6 }\n}\n' + open_button
                        + 'widget = {\nsize = { 10 10 }\n}\n', i1)
            + methods + '\t}\n\n'
            + _reindent(fullscreen(body(p, ready), ready), '\t') + '}\n')


def fullscreen(gui, ready):
    """The full-screen window: vanilla's fullscreen_block_window, as the tech tree, over the side panels
    (ingame_hud.gui, patch_hud). It shows while the company panel is open and the 'pmr_cc_full' GUI variable is set (the
    tab sets it); the back arrow clears it, back to the panel. Closing it, or the company panel closing under it,
    clears it too (its _hide), so the next company panel opens on its own tabs. Its company is the one whose executive
    the tab stored on the player's country (VIEWED)."""
    return (f'type pmr_cc_fullscreen = fullscreen_block_window {{\nname = "pmr_cc_fullscreen"\n'
            f'visible = "[And(And(GetVariableSystem.Exists(\'{FULL}\'), InformationPanelBar.IsPanelOpen(\'company_panel\')), '
            "GreaterThan_CFixedPoint(GetPlayer.MakeScope.ScriptValue('pmr_cc_viewing'), '(CFixedPoint)0'))]\"\n"
            f'datacontext = "[{VIEWED}]"\ndatacontext = "[Character.GetCompany]"\n'
            'blockoverride "animation_state_block" {\n'
            'state = {\nname = _show\nstart_sound = {\nsoundeffect = "event:/SFX/UI/SideBar/technology"\n}\n}\n'
            f'state = {{\nname = _hide\non_start = "[GetVariableSystem.Clear(\'{FULL}\')]"\n'
            'start_sound = {\nsoundeffect = "event:/SFX/UI/SideBar/technology_stop"\n}\n}\n}\n'
            'blockoverride "window_header_name" {\ntext = "PMR_CC_FULL_TITLE"\n}\n'
            # the topbar's construction box (410 x 75 at y 76, right) stays over this window, unlike over vanilla's
            # full-screens (block_windows.gui fullscreen_hide), so the X sits left of it
            'blockoverride "close_button_position" {\nposition = { -425 15 }\n}\n'
            'blockoverride "back_button_fullscreen" {\nback_button_large = {\nposition = { 11 15 }\nparentanchor = top|left\n'
            f'onclick = "[GetVariableSystem.Clear(\'{FULL}\')]"\ninput_action = "back"\n}}\n}}\n'
            'blockoverride "fixed_top" {\nwidget = {\nlayoutpolicy_horizontal = expanding\nsize = { 0 98 }\n'
            + header_gui(ready).replace('parentanchor = hcenter\n', 'parentanchor = hcenter\nposition = { 0 4 }\n', 1)
            + show_button(ready).replace('parentanchor = hcenter\n', 'parentanchor = center\n', 1)
            + '}\n}\n'
            'blockoverride "entire_content_area" {\n' + gui + '}\n}\n')


def patch_panel(text, tab_id):
    """company_panel.gui: a fourth tab, Company Culture, after Statistics, which opens the full-screen window, left off
    a subsidiary's panel (Pat 14:43Z: no Company Culture on subsidiaries); the charter row off the panel's foot (its
    buttons are on the charter nodes); and the panel's closing clears the full-screen window's variable."""
    where = cc.PANEL_GUI
    not_sub = company_panel.NOT_SUB
    anchor = '\t\t\t\tblockoverride "third_button_selected"\n\t\t\t\t{\n\t\t\t\t\ttext = "COMPANY_TAB_STATISTICS"\n\t\t\t\t}\n'
    if text.count(anchor) != 1:
        cc.fail(where, 'the Statistics tab button block moved')
    four = (
        '\n\t\t\t\t# PMR: Company Culture tab\n'
        '\t\t\t\tblockoverride "fourth_button"\n\t\t\t\t{\n\t\t\t\t\ttext = "PMR_CC_TAB"\n\t\t\t\t}\n'
        '\t\t\t\tblockoverride "fourth_button_tooltip"\n\t\t\t\t{\n\t\t\t\t}\n'
        f'\t\t\t\tblockoverride "fourth_button_click"\n\t\t\t\t{{\n\t\t\t\t\tonclick = "[InformationPanel.SelectTab(\'{tab_id}\')]"\n'
        f'\t\t\t\t\tonclick = "[{VIEW}]"\n'
        f'\t\t\t\t\tonclick = "[GetVariableSystem.Set(\'{FULL}\', \'yes\')]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "fourth_button_visibility"\n\t\t\t\t{{\n\t\t\t\t\tvisible = "[And(InformationPanel.IsTabSelected(\'{tab_id}\'), {not_sub})]"\n\t\t\t\t}}\n'
        f'\t\t\t\tblockoverride "fourth_button_visibility_checked"\n\t\t\t\t{{\n\t\t\t\t\tvisible = "[And(Not( InformationPanel.IsTabSelected(\'{tab_id}\') ), {not_sub})]"\n\t\t\t\t}}\n'
        '\t\t\t\tblockoverride "fourth_button_selected"\n\t\t\t\t{\n\t\t\t\t\ttext = "PMR_CC_TAB"\n\t\t\t\t}\n')
    text = text.replace(anchor, anchor + four)
    anchor2 = ('\t\t\t\tcompany_panel_statistics_tab = {\n'
               '\t\t\t\t\tvisible = "[InformationPanel.IsTabSelected(\'statistics\')]"\n\t\t\t\t}\n')
    if text.count(anchor2) != 1:
        cc.fail(where, 'the Statistics tab contents moved')
    text = text.replace(anchor2, anchor2 + '\n\t\t\t\t# PMR: Company Culture tab\n\t\t\t\tcompany_panel_culture_tab = {\n'
                        f'\t\t\t\t\tvisible = "[And(InformationPanel.IsTabSelected(\'{tab_id}\'), {not_sub})]"\n\t\t\t\t}}\n')
    bar = '\t\tblockoverride "fixed_bottom" {\n\t\t\tflowcontainer = {\n\t\t\t\tvisible = "[Company.GetCountry.IsLocalPlayer]"\n'
    if text.count(bar) != 1:
        cc.fail(where, 'the charter row at the panel\'s foot moved')
    text = text.replace(bar, '\t\tblockoverride "fixed_bottom" {\n\t\t\tflowcontainer = {\n'
                        '\t\t\t\tvisible = no  # PMR: the charter buttons are on the Company Culture charter nodes\n')
    hide = ('\t\t\tstate = {\n\t\t\t\tname = _hide\n\t\t\t\tstart_sound = {\n'
            '\t\t\t\t\tsoundeffect = "event:/SFX/UI/CompanyCharters/company_panel_stop"\n')
    if text.count(hide) != 1:
        cc.fail(where, 'the panel\'s _hide state moved')
    return text.replace(hide, hide.replace('name = _hide\n', f'name = _hide\n\t\t\t\ton_start = "[GetVariableSystem.Clear(\'{FULL}\')]"  # PMR\n'))


HUD_GUI = 'gui/ingame_hud.gui'


def patch_hud(text):
    """ingame_hud.gui: the full-screen window after the side panels and before the topbar, so the topbar and the left
    sidebar buttons stay over it as over the tech tree."""
    anchor = '\t# topbar / alerts / timemanip\n\tvbox = {\n'
    if text.count(anchor) != 1:
        cc.fail(HUD_GUI, 'the topbar vbox moved')
    return text.replace(anchor, '\t# PMR: Company Culture, full-screen (cc_tree.fullscreen)\n\tpmr_cc_fullscreen = {}\n\n' + anchor)


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


def textures(out_dir):
    """Writes the window's textures under out_dir; returns how many."""
    ims = {
        'cc_card': _rounded(CW, NODE_H, 16, grad=0.66),
        'cc_outline': _rounded(CW, NODE_H, 16, ring=3),
    }
    for name, im in ims.items():
        path = os.path.join(out_dir, TEX, f'{name}.dds')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        icons.write_dds(im, path)
    return len(ims)
