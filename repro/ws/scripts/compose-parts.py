import argparse
import glob
import json
import os
import re
import sys

import numpy as np
from PIL import Image

import editkit
import layerkit
from layerkit import A, classify, denoise, robust_box

CONFIG_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parts.config.json")

def ts_of(p):
    m = re.search(r"(\d{8}_\d{6})", os.path.basename(p))
    return m.group(1) if m else ""

def collect(case):
    inp = os.path.join(case, "input")
    if not os.path.isdir(inp):
        sys.exit("找不到 %s" % inp)

    canvas = None
    layers, problems = [], []

    srcs = layerkit.batch_sources(case)
    if not srcs and not glob.glob(os.path.join(inp, "**", "*.png"), recursive=True):
        if layerkit.psd_batches(case):
            sys.exit("input/ 里有 PSD 但还没拆小图 —— 先跑「拆图」")
        sys.exit("input/ 里没有 PSD，base/small 里也没有拆好的小图")

    for run, (_label, base) in sorted(srcs.items()):
        js = sorted(glob.glob(os.path.join(base, "*layers.json")))[0]
        try:
            d = json.load(open(js, encoding="utf-8"))
        except Exception as e:
            problems.append("%s 读不了：%s" % (os.path.basename(js), e))
            continue
        W, H = int(d["width"]), int(d["height"])
        canvas = canvas or (W, H)
        rank = ts_of(run) or ts_of(js) or "%d" % os.path.getmtime(base)
        for z, L in enumerate(d["layers"]):
            p = os.path.join(base, L["filename"])
            if not os.path.isfile(p):
                problems.append("%s: 缺文件 %s" % (run, L["filename"]))
                continue
            layers.append({"name": L["name"], "path": p, "run": run, "rank": rank,
                           "x": int(L["left"]), "y": int(L["top"]), "z": z, "canvas": (W, H),
                           "index": L.get("index")})

    ref_name = os.path.basename(os.path.abspath(case).rstrip("/"))
    known = {os.path.abspath(L["path"]) for L in layers}
    for p in glob.glob(os.path.join(inp, "**", "*.png"), recursive=True):
        if os.path.abspath(p) in known or p.endswith("_depth.png"):
            continue
        stem = os.path.splitext(os.path.basename(p))[0]
        if stem == ref_name:
            continue
        if re.match(r"^seethrough_.*_[a-z\- ]+$", stem):
            stem = re.sub(r"^seethrough_[0-9_a-z]+_", "", stem)
        im = Image.open(p)
        if canvas and im.size != canvas:
            problems.append("%s 尺寸 %s ≠ 画布 %s，且没有 layers.json 记位置，跳过"
                            % (os.path.basename(p), im.size, canvas))
            continue
        canvas = canvas or im.size
        layers.append({"name": stem, "path": p, "run": ".", "rank": "0",
                       "x": 0, "y": 0, "z": 0, "canvas": im.size, "index": None})

    if not canvas:
        sys.exit("base/small 里既没有 layers.json 也没有 png —— 先跑「拆图」")
    layers.sort(key=lambda L: (L["rank"], L["z"]), reverse=True)
    return canvas, layers, problems

def short_run(run):
    r = run.replace("run-", "")
    m = re.search(r"\d{8}_(\d{6})", r)
    return m.group(1) if m else r[:12]

def load_selection(case):
    p = os.path.join(case, "input", "selection.json")
    if not os.path.isfile(p):
        return {}
    try:
        sel = json.load(open(p, encoding="utf-8"))
        return {k: v for k, v in sel.items() if isinstance(v, str) and v}
    except Exception as e:
        print("selection.json 读不了（%s），按自动规则走" % e)
        return {}

def resolve(layers, W, H, sel=None, disabled=None):
    sel = sel or {}
    ordered = sorted(layers, key=lambda L: (L["rank"] == "0", L["rank"], L["z"]))
    best, dropped = {}, []
    dis = disabled or set()
    for L in ordered:
        if L["name"] in dis:
            dropped.append((L["name"], L["run"], "已禁用"))
            continue
        want = sel.get(L["name"])
        if want and L["run"] != want:
            continue
        if L["name"] in best:
            continue
        im = Image.open(L["path"]).convert("RGBA")
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        canvas.alpha_composite(im, (L["x"], L["y"]))
        arr = np.array(canvas)
        px = int((arr[..., 3] > A).sum())
        box = robust_box(arr)
        if not box:
            dropped.append((L["name"], L["run"], "全透明"))
            continue
        why = classify(px, box[0], box[1], box[2] - box[0], box[3] - box[1], W, H,
                       amax=int(arr[..., 3].max()))
        if why:
            dropped.append((L["name"], L["run"], why))
            continue
        best[L["name"]] = {"im": canvas, "x": L["x"], "y": L["y"], "z": L["z"],
                          "run": L["run"], "index": L.get("index")}
    return best, dropped

def load_config(case):
    for p in (os.path.join(case, "input", "parts.json"), CONFIG_DEFAULT):
        if not os.path.isfile(p):
            continue
        try:
            cfg = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            sys.exit("部件规则 %s 读不了：%s" % (p, e))
        if not isinstance(cfg.get("parts"), list) or not cfg["parts"]:
            sys.exit("%s 里没有 parts 列表" % p)
        for spec in cfg["parts"]:
            if not spec.get("name") or not spec.get("layers"):
                sys.exit("%s 里有部件缺 name / layers：%r" % (p, spec))
            if spec.get("side") not in (None, "l", "r"):
                sys.exit("%s 里 %s 的 side 只能是 l / r" % (p, spec["name"]))
        cfg["_path"] = p
        return cfg
    sys.exit("找不到部件规则文件：%s" % CONFIG_DEFAULT)

def family(name, have):
    sides = [n for n in (name + "-l", name + "-r") if n in have]
    if sides:
        return sides
    return [name] if name in have else []

def _content_x(im):
    box = robust_box(np.array(im))
    return (box[0], box[2] - 1) if box else None

def _side_cover(im, mid, side):
    m = np.array(im)[..., 3] > A
    cols = m.sum(0)
    k = int(mid)
    left, right = int(cols[:k].sum()), int(cols[k:].sum())
    tot = left + right
    if not tot:
        return 0.0
    return (left if side == "l" else right) / tot

def clip_side(im, side, mid):
    a = np.array(im).copy()
    x = np.arange(a.shape[1])[None, :]
    keep = (x < mid) if side == "l" else (x >= mid)
    a[..., 3] = np.where(keep, a[..., 3], 0)
    return Image.fromarray(a, "RGBA")

def pick_layers(spec, best, mid):
    out = []
    side = spec.get("side")
    family_mode = spec.get("match", "family") == "family"
    clip = side if spec.get("clip", True) else None
    for base in spec["layers"]:
        cands = family(base, best) if family_mode else ([base] if base in best else [])
        if not cands:
            continue
        if side is None or mid is None:
            out.extend((n, None) for n in cands)
            continue
        inside, scored = [], []
        for n in cands:
            box = _content_x(best[n]["im"])
            if not box:
                continue
            if (box[1] < mid) if side == "l" else (box[0] >= mid):
                inside.append(n)
            else:
                scored.append((_side_cover(best[n]["im"], mid, side), n))
        if inside:
            out.extend((n, None) for n in inside)
        else:
            scored = [x for x in scored if x[0] >= 0.3]
            if scored:
                out.append((max(scored)[1], clip))
    return out

def build(specs, best, W, H, mid):
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    used = []

    def _order(s):
        b = best[s[0]]
        i = b["index"] if b["index"] is not None else 0
        return (i, b["z"])

    for name, cut in sorted(specs, key=_order):
        im = best[name]["im"]
        if cut and mid is not None:
            im = clip_side(im, cut, mid)
        out.alpha_composite(im)
        used.append(name)
    return out, used

def load_disabled(case):
    p = editkit.parts_disabled(case)
    if not os.path.isfile(p):
        return set()
    try:
        d = json.load(open(p, encoding="utf-8"))
        return {x for x in d if isinstance(x, str) and x} if isinstance(d, list) else set()
    except Exception as e:
        print("%s 读不了（%s），按「全都不禁用」走" % (p, e))
        return set()

def side_split_x(best, cfg, W):
    xs = []
    for base in (cfg.get("split") or {}).get("from") or []:
        for n in family(base, best):
            box = _content_x(best[n]["im"])
            if box:
                xs.extend(box)
    return (min(xs) + max(xs) + 1) / 2 if xs else W / 2

def part_index(best, used):
    wsum = dsum = 0.0
    for n in used:
        b = best[n]
        d = b["index"] if b["index"] is not None else 0
        px = b.get("px")
        if px is None:
            px = int((np.array(b["im"])[..., 3] > A).sum())
            b["px"] = px
        wsum += px * d
        dsum += px
    return round(wsum / dsum, 2) if dsum else None

def compose(case):
    canvas, layers, problems = collect(case)
    W, H = canvas
    cfg = load_config(case)
    sel = load_selection(case)
    disabled = load_disabled(case)
    best, dropped = resolve(layers, W, H, sel, disabled)

    mid = side_split_x(best, cfg, W)

    parts = {}
    for spec in cfg["parts"]:
        specs = pick_layers(spec, best, mid)
        if not specs:
            continue
        im, used = build(specs, best, W, H, mid)
        if not used:
            continue
        im = denoise(im)
        box = robust_box(np.array(im))
        if not box:
            continue
        x, y, x1, y1 = box
        parts[spec["name"]] = {"im": im.crop(box), "x": x, "y": y,
                               "w": x1 - x, "h": y1 - y, "layers": used,
                               "from": {n: best[n]["run"] for n in used},
                               "index": part_index(best, used)}
    return {"canvas": (W, H), "parts": parts, "best": best, "dropped": dropped,
            "problems": problems, "sel": sel,
            "disabled": sorted(disabled), "config": cfg["_path"], "split_x": mid}

def layer_views(res):
    out = {}
    for name, b in res["best"].items():
        canvas = b["im"]
        a = np.array(canvas)
        ys, xs = np.where(a[..., 3] > A)
        if len(xs) == 0:
            continue
        crop = canvas.crop((int(xs.min()), int(ys.min()),
                            int(xs.max()) + 1, int(ys.max()) + 1))
        crop = denoise(crop, frac=0.05)
        box = robust_box(np.array(crop), frac=0.05)
        if not box:
            continue
        out[name] = {"im": crop.crop(box),
                     "x": int(xs.min()) + box[0], "y": int(ys.min()) + box[1],
                     "w": box[2] - box[0], "h": box[3] - box[1],
                     "z": b["z"], "run": b["run"], "index": b.get("index")}
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case", help="素材目录（含 input/）")
    ap.add_argument("--out", default=None, help="输出目录（默认 <case>/base/parts）")
    a = ap.parse_args()

    case = os.path.abspath(a.case)
    res = compose(case)
    W, H = res["canvas"]
    best, dropped, sel = res["best"], res["dropped"], res["sel"]
    problems = res["problems"]
    cfg = load_config(case)
    print("部件规则 %s（%d 个部件）" % (cfg["_path"], len(cfg["parts"])))
    print("画布 %dx%d，可用图层 %d 个%s%s" % (
        W, H, len(best), "，手动指定 %d 个部位" % len(sel) if sel else "",
        "，左右分界 x=%.0f" % res["split_x"] if res["split_x"] is not None else ""))

    out = a.out or os.path.join(case, "base", "parts")
    os.makedirs(out, exist_ok=True)

    info = {}
    for spec in cfg["parts"]:
        part = spec["name"]
        p = res["parts"].get(part)
        if not p:
            print("  %-7s —— 没有可用图层，跳过" % part)
            continue
        p["im"].save(os.path.join(out, part + ".png"))
        info[part] = {"file": part + ".png", "x": p["x"], "y": p["y"],
                      "w": p["w"], "h": p["h"], "layers": p["layers"], "from": p["from"],
                      "index": p.get("index")}
        srcs = sorted({short_run(b) for b in p["from"].values()})
        print("  %-7s %-24s bbox=(%d,%d) %dx%d  层序=%.2f  批次 %s" % (
            part, ",".join(p["layers"])[:24], p["x"], p["y"], p["w"], p["h"],
            p.get("index") or 0, ",".join(srcs)))

    json.dump({"canvas": [W, H], "parts": info, "selection": sel, "config": cfg["_path"]},
              open(os.path.join(out, "parts.json"), "w"), indent=1, ensure_ascii=False)

    for name, batch in sel.items():
        if name not in best:
            print("⚠ %s 指定的批次 %s 里这一层不可用（空层或缺失），这次没用上" % (name, batch))

    if dropped:
        print("\n被丢掉 %d 层（空层/杂点，不影响合成）：" % len(dropped))
        seen = set()
        for n, run, why in dropped:
            if n in best or n in seen:
                continue
            seen.add(n)
            print("  %-14s %s" % (n, why))
    if problems:
        print("\n注意：")
        for p in problems[:10]:
            print("  " + p)
    print("\n产物 %s" % out)

if __name__ == "__main__":
    main()
