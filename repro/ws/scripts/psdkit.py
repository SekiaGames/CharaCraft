import glob
import json
import os
import re

import numpy as np

import editkit
import layerkit

WORKING_RE = re.compile(r"^(\d+)\.psd$", re.I)

def batch_key(bid):
    s = str(bid)
    return (len(s), s)

def batches(case):
    out = []
    for p in glob.glob(os.path.join(case, "input", "*.psd")):
        m = WORKING_RE.match(os.path.basename(p))
        if m:
            out.append((m.group(1), p))
    out.sort(key=lambda x: batch_key(x[0]))
    return out

def backup_path(case, bid):
    return os.path.join(case, "input", "%s_backup.psd" % bid)

def batch_index_path(case, bid):
    return os.path.join(case, "base", "batches", bid + ".json")

def iter_layers(node):
    for layer in node:
        if not layer.visible:
            continue
        if layer.is_group():
            for sub in iter_layers(layer):
                yield sub
        else:
            yield layer

def read_layers(psd_path):
    from psd_tools import PSDImage

    psd = PSDImage.open(psd_path)
    W, H = int(psd.width), int(psd.height)
    items = []
    used = {}
    for layer in iter_layers(psd):
        im = layer.topil()
        if im is None:
            continue
        im = im.convert("RGBA")
        if not np.any(np.array(im)[..., 3] > 8):
            continue
        name = (layer.name or "layer").strip() or "layer"
        if name in used:
            used[name] += 1
            name = "%s-%d" % (name, used[name])
        else:
            used[name] = 1
        items.append({"name": name, "img": im,
                      "left": int(layer.left), "top": int(layer.top)})
    return W, H, items

def scan_batch(psd_path, keep_image=False):
    W, H, items = read_layers(psd_path)
    out = []
    for i, it in enumerate(items):
        im = it["img"]
        a = np.array(im)
        px = int((a[..., 3] > layerkit.A).sum())
        box = layerkit.robust_box(a) if px else None
        rec = {"name": it["name"], "index": i, "px": px,
               "left": it["left"], "top": it["top"],
               "right": it["left"] + im.width, "bottom": it["top"] + im.height,
               "empty": True, "why": "全透明"}
        if box:
            x, y, x1, y1 = box
            why = layerkit.classify(px, it["left"] + x, it["top"] + y,
                                    x1 - x, y1 - y, W, H, amax=int(a[..., 3].max()))
            rec.update(left=it["left"] + x, top=it["top"] + y,
                       right=it["left"] + x1, bottom=it["top"] + y1,
                       empty=bool(why), why=why)
            if keep_image:
                rec["img"] = im.crop(box)
        out.append(rec)
    return W, H, out

def read_selection(case, act):
    p = editkit.parts_selection(case, act)
    if not os.path.isfile(p):
        return {}
    return {k: v for k, v in json.load(open(p, encoding="utf-8")).items()
            if isinstance(k, str) and isinstance(v, str) and v}

def read_disabled(case):
    p = editkit.parts_disabled(case)
    if not os.path.isfile(p):
        return set()
    return set(json.load(open(p, encoding="utf-8")))

def effective(case, act):
    bs = batches(case)
    if not bs:
        raise SystemExit("input/ 下没有 <批次>.psd（先用「同步 PSD」）")
    first_id = bs[0][0]
    sel = read_selection(case, act)
    need = {first_id} | {v for v in sel.values() if v}

    scans = {}
    for bid, path in bs:
        if bid not in need:
            continue
        W, H, layers = scan_batch(path, keep_image=True)
        scans[bid] = {"W": W, "H": H, "layers": layers,
                      "by_name": {L["name"]: L for L in layers}}

    dis = read_disabled(case)
    layers, skipped, subs = [], [], []
    for L in scans[first_id]["layers"]:
        name = L["name"]
        if name in dis:
            skipped.append((name, "禁用（edit/Edit-PartsDisable.json）"))
            continue
        src, rec = first_id, L
        want = sel.get(name)
        if want and want != first_id:
            cand = scans.get(want, {}).get("by_name", {}).get(name)
            if cand and not cand["empty"]:
                src, rec = want, cand
                subs.append((name, want))
        if rec["empty"]:
            skipped.append((name, rec.get("why") or "空层"))
            continue
        layers.append({"name": name, "img": rec["img"],
                       "left": rec["left"], "top": rec["top"],
                       "right": rec["right"], "bottom": rec["bottom"],
                       "index": L["index"], "from": src})

    return {"width": scans[first_id]["W"], "height": scans[first_id]["H"],
            "first": first_id, "layers": layers, "skipped": skipped, "subs": subs}
