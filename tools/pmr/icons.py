"""Gold production-method icons drawn from goods icons, for PMR's fixed labour methods.

Vanilla production method icons are 104 x 104 uncompressed RGBA DDS with a full mip chain: a flat
bronze-gold silhouette, light at the top and dark brown at the foot, with a dark contour and a faint
shadow. This draws a goods icon's outline in that treatment, keeping the good's own shading so
interior shapes still read.

Needs Pillow (reads DDS) and numpy.
"""
import struct

import numpy as np
from PIL import Image, ImageFilter

SIZE = 104        # vanilla production method icon size
FIT = 82          # the good's silhouette fits this box, centred
# Vertical gradient sampled from vanilla production_method_icons/blister_steel_process.dds.
GRAD = [(0.0, (198, 186, 156)), (0.45, (160, 136, 98)), (1.0, (98, 72, 40))]
CONTOUR = (28, 23, 17)


def _gradient(t):
    t = np.clip(t, 0, 1)
    out = np.zeros(t.shape + (3,))
    for (t0, c0), (t1, c1) in zip(GRAD, GRAD[1:]):
        m = (t >= t0) & (t <= t1)
        f = ((t - t0) / (t1 - t0))[m][:, None]
        out[m] = np.array(c0) * (1 - f) + np.array(c1) * f
    return out


def _fit(src):
    im = Image.open(src).convert('RGBA')
    bbox = im.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox() or (0, 0) + im.size
    im = im.crop(bbox)
    scale = FIT / max(im.size)
    im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    canvas = Image.new('RGBA', (SIZE, SIZE))
    canvas.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2))
    return canvas


def gold_icon(src):
    """Return a 104 x 104 RGBA image: the good at path src, drawn as a gold PM icon."""
    good = _fit(src)
    rgba = np.asarray(good).astype(float) / 255
    # crisp silhouette: drop the soft baked-in shadows many goods icons carry
    a = np.clip((rgba[..., 3] - 0.55) / 0.25, 0, 1)
    lum = rgba[..., :3] @ np.array([0.299, 0.587, 0.114])
    # flatten the photo texture: vanilla PM icons are flat planes, not rendered surfaces
    lum = np.asarray(Image.fromarray((lum * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))) / 255
    inside = a > 0.5
    lo, hi = (np.percentile(lum[inside], 5), np.percentile(lum[inside], 95)) if inside.any() else (0, 1)
    shade = np.clip((lum - lo) / max(hi - lo, 1e-3), 0, 1)

    ys = np.nonzero(inside.any(axis=1))[0]
    top, bottom = (ys[0], ys[-1]) if len(ys) else (0, SIZE - 1)
    t = (np.arange(SIZE)[:, None] - top) / max(bottom - top, 1)
    base = _gradient(np.broadcast_to(t, (SIZE, SIZE)))
    col = base * (0.66 + 0.5 * shade[..., None])

    # interior detail: darken where the good's own shading has edges
    edges = np.asarray(Image.fromarray((shade * 255).astype(np.uint8)).filter(ImageFilter.FIND_EDGES)) / 255
    col = col * (1 - 0.3 * np.clip(edges * 2, 0, 1)[..., None])

    # dark contour just inside the edge
    mask = Image.fromarray((a * 255).astype(np.uint8))
    eroded = np.asarray(mask.filter(ImageFilter.MinFilter(3))) / 255
    rim = np.clip(a - eroded, 0, 1)[..., None]
    col = col * (1 - rim) + np.array(CONTOUR) * rim

    # outer contour and a soft shadow down and right
    outer = np.asarray(mask.filter(ImageFilter.MaxFilter(3))) / 255
    shadow = np.asarray(mask.transform(mask.size, Image.AFFINE, (1, 0, -1, 0, 1, -2))
                        .filter(ImageFilter.GaussianBlur(1.5))) / 255 * 0.45

    out = np.zeros((SIZE, SIZE, 4))
    sh_a = np.maximum(shadow, outer * 0.9)
    out[..., :3] = np.array(CONTOUR)
    out[..., 3] = sh_a
    # composite the gold body over contour and shadow
    out[..., :3] = col * a[..., None] + out[..., :3] * (1 - a[..., None])
    out[..., 3] = a + sh_a * (1 - a)
    return Image.fromarray(np.clip(np.round(np.dstack([out[..., :3], out[..., 3:] * 255])), 0, 255)
                           .astype(np.uint8), 'RGBA')


def write_dds(im, path):
    """Write im as uncompressed A8R8G8B8 DDS with a full mip chain, the layout vanilla PM icons use."""
    levels = [im]
    while max(levels[-1].size) > 1:
        w, h = levels[-1].size
        levels.append(levels[-1].resize((max(1, w // 2), max(1, h // 2)), Image.LANCZOS))
    w, h = im.size
    header = struct.pack('<4sIIIIIII44x', b'DDS ', 124, 0x2100F, h, w, w * 4, 0, len(levels))
    pf = struct.pack('<IIIIIIII', 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    caps = struct.pack('<IIIII', 0x401008, 0, 0, 0, 0)
    with open(path, 'wb') as f:
        f.write(header + pf + caps)
        for lv in levels:
            r, g, b, a = lv.split()
            f.write(Image.merge('RGBA', (b, g, r, a)).tobytes())
