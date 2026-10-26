import glob
import json
import os

import numpy as np
from PIL import Image

A = 8
MIN_PX = 20
SPARSE = 0.001
CORNER = 4096
SPECKS = 12
FAINT = 96

def classify(px, x, y, w, h, W, H, amax=None):
    if amax is not None and amax < FAINT:
        return "空层（过淡，最大 alpha %d）" % int(amax)
    if px < MIN_PX:
        return "噪点（%dpx）" % px
    area = max(1, w * h)
    if (x + w >= W - 8 and y + h >= H - 8) and area < CORNER:
        return "包围盒退化到右下角 %d,%d" % (x, y)
    if px / area < SPARSE:
        return "内容散碎（%dpx 撑出 %dx%d）" % (px, w, h)
    return None

BRIGHT = 96

def components_keep(mask, frac=0.02, alpha=None, bright=BRIGHT):
    try:
        from scipy import ndimage
        lab, n = ndimage.label(mask)
        if n <= 1:
            return mask
        idx = np.arange(1, n + 1)
        sizes = ndimage.sum(mask, lab, idx)
        keep = sizes >= max(SPECKS, frac * sizes.max())
        if alpha is not None and keep.any():
            main = np.isin(lab, idx[keep])
            ys, xs = np.where(main)
            y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
            mean_a = ndimage.mean(alpha, lab, idx)
            inside = np.zeros(n, bool)
            for i, sl in enumerate(ndimage.find_objects(lab)):
                if sl is None:
                    continue
                sy, sx = sl
                if sy.start >= y0 and sy.stop - 1 <= y1 and sx.start >= x0 and sx.stop - 1 <= x1:
                    inside[i] = True
            keep |= (mean_a >= bright) & (sizes >= SPECKS) & inside
        keep = idx[keep]
        return np.isin(lab, keep) if len(keep) else mask
    except Exception:
        return mask

def robust_box(a, frac=0.02):
    m = a[..., 3] > A
    if not m.any():
        return None
    m = components_keep(m, frac, a[..., 3])
    ys, xs = np.where(m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1

def denoise(im, frac=0.02):
    a = np.array(im)
    m = a[..., 3] > A
    if not m.any():
        return im
    keep = components_keep(m, frac, a[..., 3])
    if keep is not m:
        a[..., 3] = np.where(keep, a[..., 3], 0)
    return Image.fromarray(a, "RGBA")

def stats(path):
    a = np.array(Image.open(path).convert("RGBA"))
    return int((a[..., 3] > A).sum()), robust_box(a), int(a[..., 3].max())

SRC_ORDER = (os.path.join("base", "small"),)

def batch_sources(case):
    out = {}
    for label in SRC_ORDER:
        for js in sorted(glob.glob(os.path.join(case, label, "*", "*layers.json"))):
            bid = os.path.basename(os.path.dirname(js))
            out.setdefault(bid, (label, os.path.dirname(js)))
    return out

def psd_batches(case):
    import re
    out = {}
    pat = re.compile(r"^(\d+)\.psd$", re.I)
    for p in sorted(glob.glob(os.path.join(case, "input", "*.psd"))):
        m = pat.match(os.path.basename(p))
        if m:
            out[m.group(1)] = p
    return out

HEAD_LAYERS = {"back hair", "face", "front hair", "headwear", "earwear", "eyewear",
               "ears", "eyebrow", "eyelash", "eyewhite", "irides", "nose", "mouth"}
TORSO_LAYERS = {"topwear", "bottomwear", "neckwear", "tail", "wings"}

def guess_rows(W, layers, role_index=None):
    ri = role_index or {}

    def idx(roles):
        return [ri[r] for r in roles if r in ri]

    cx = {x["name"]: (x.get("left", 0) + x.get("right", 0)) / 2 for x in layers}

    def mid_of(prefix):
        xs = sorted(v for k, v in cx.items() if k.startswith(prefix))
        if not xs:
            return (W or 1024) / 2
        return sum(xs) / len(xs)

    mid = mid_of("footwear") if any(k.startswith("footwear") for k in cx) else mid_of("legwear")
    rows = []
    for x in layers:
        n = x["name"]
        low = n.lower()
        r = {"layer": n, "bones": [],
             "z": int(x.get("index", len(rows))), "enabled": True}
        w = x.get("right", 0) - x.get("left", 0)
        h = x.get("bottom", 0) - x.get("top", 0)
        if w <= 24 and h <= 24:
            r["enabled"] = False
            rows.append(r)
            continue
        if low in HEAD_LAYERS:
            r["bones"] = idx(["head"])
        elif low == "neck":
            r["bones"] = idx(["neck"])
        elif low in TORSO_LAYERS:
            r["bones"] = idx(["body-down"])
        elif low.startswith("handwear"):
            front = cx[n] >= mid
            r["bones"] = idx(["arm-front-up", "arm-front-down"] if front
                             else ["arm-back-up", "arm-back-down"])
        elif low.startswith("legwear"):
            near = cx[n] >= mid
            r["bones"] = idx(["leg-up", "leg-down"] if near else ["leg-up-back", "leg-down-back"])
        elif low.startswith("footwear"):
            r["bones"] = idx(["leg-down"] if cx[n] >= mid else ["leg-down-back"])
        elif low == "objects":
            r["bones"] = idx(["root"])
        else:
            r["enabled"] = False
        rows.append(r)

    rows.sort(key=lambda r: r["z"])
    return rows

def sync_rows(saved, guessed):
    have = {r.get("layer") for r in (saved or [])}
    gmap = {r["layer"]: r for r in guessed}
    names = [r["layer"] for r in guessed]
    rows = []
    for r in (saved or []):
        g = gmap.get(r.get("layer"))
        if not g:
            continue
        row = dict(r)
        row["z"] = g.get("z", row.get("z", 0))
        rows.append(row)
    added = [n for n in names if n not in have]
    rows += [dict(gmap[n]) for n in added]
    gone = [n for n in have if n and n not in gmap]
    rows.sort(key=lambda r: r.get("z", 0))
    return rows, added, gone

def dump_attachments(data):
    out = ['{', ' "version": %d,' % data["version"],
           ' "batch": %s,' % json.dumps(data["batch"], ensure_ascii=False),
           ' "canvas": [%s],' % ", ".join(str(x) for x in data["canvas"]),
           ' "rows": [']
    rows = data["rows"]
    for i, r in enumerate(rows):
        out.append('  {"layer": %s, "bones": [%s], "z": %d, "enabled": %s}%s' % (
            json.dumps(r["layer"], ensure_ascii=False),
            ", ".join(str(x) for x in r["bones"]), r["z"],
            "true" if r["enabled"] else "false",
            "," if i < len(rows) - 1 else ""))
    out += [" ]", "}"]
    return "\n".join(out) + "\n"
