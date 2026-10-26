import glob
import os
import re

import numpy as np
from PIL import Image
from scipy import ndimage

BLEED_PAD = 3
MAX_PAGE = 4096
FILTER = "MipMapLinearLinear,Linear"
NL = chr(10)


def bleed(im):
    a = np.array(im)
    rgb, al = a[..., :3], a[..., 3]
    solid = al > 0
    if solid.any() and not solid.all():
        _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
        rgb = rgb[iy, ix]
    p = BLEED_PAD
    rgb = np.pad(rgb, ((p, p), (p, p), (0, 0)), mode="edge")
    al = np.pad(al, ((p, p), (p, p)))
    return Image.fromarray(np.dstack([rgb, al]).astype(np.uint8), "RGBA")


def bleed_page(page):
    a = np.array(page)
    solid = a[..., 3] > 0
    if solid.any() and not solid.all():
        _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
        a[..., :3] = a[..., :3][iy, ix]
    return Image.fromarray(a, "RGBA")


def pack_page(order, side, pad):
    x = y = shelf_h = 0
    pos, rest = {}, []
    for name, im in order:
        w, h = im.width + pad, im.height + pad
        if x + w > side:
            x, y, shelf_h = 0, y + shelf_h, 0
        if y + h > side or w > side:
            rest.append((name, im))
            continue
        pos[name] = (x + pad // 2, y + pad // 2)
        x += w
        shelf_h = max(shelf_h, h)
    return pos, rest


def pack(images, pad=2 * BLEED_PAD + 2):
    order = sorted(images.items(), key=lambda kv: (-kv[1].height, kv[0]))
    pages = []
    while order:
        side = 64
        while side < MAX_PAGE:
            pos, rest = pack_page(order, side, pad)
            if not rest:
                break
            side *= 2
        pos, rest = pack_page(order, side, pad)
        if not pos:
            raise SystemExit("有切件超过 %dpx，装不进图集" % MAX_PAGE)
        pages.append((side, pos))
        order = rest
    return pages


def rig_name(case):
    return re.sub(r"[^a-z0-9]+", "_", os.path.basename(case.rstrip("/")).lower()).strip("_") or "rig"


def read_blocks(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return [(b.split(NL)[0], b.strip(NL)) for b in text.strip(NL).split(NL + NL) if b.strip(NL)]


def mine(page, name, act):
    return page == "%s-%s.png" % (name, act) or page.startswith("%s-%s_" % (name, act))


def write(case, act, images, name=None, filt=FILTER):
    name = name or rig_name(case)
    out = os.path.join(case, "output")
    os.makedirs(out, exist_ok=True)
    for p in glob.glob(os.path.join(out, "%s-%s*.png" % (name, act))):
        os.remove(p)

    pages, blocks = [], []
    for k, (side, pos) in enumerate(pack(images)):
        fname = "%s-%s.png" % (name, act) if k == 0 else "%s-%s_%d.png" % (name, act, k + 1)
        page = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        lines = [fname, "size:%d,%d" % (side, side), "filter:%s" % filt, "format:RGBA8888"]
        for key in sorted(pos):
            x, y = pos[key]
            im = images[key]
            page.paste(bleed(im), (x - BLEED_PAD, y - BLEED_PAD))
            lines += [key, "bounds:%d,%d,%d,%d" % (x, y, im.width, im.height)]
        bleed_page(page).save(os.path.join(out, fname))
        pages.append(fname)
        blocks.append(NL.join(lines))

    path = os.path.join(out, name + ".atlas")
    keep = [b for b in read_blocks(path) if not mine(b[0], name, act)]
    keep += [(b.split(NL)[0], b) for b in blocks]
    keep.sort(key=lambda b: b[0])
    with open(path, "w", newline=NL) as f:
        f.write((NL + NL).join(b for _, b in keep) + NL)
    return pages, [b[0] for b in keep]
