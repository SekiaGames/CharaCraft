import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONFIG = os.path.join(ROOT, "config")
SKEL = os.path.join(CONFIG, "skeleton.json")

KEY_ORDER = ("side", "role", "aim")

def path():
    return SKEL

def read():
    return json.load(open(SKEL, encoding="utf-8"))

def rel(dx, dy, a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return (dx * c - dy * s, -dx * s - dy * c)

def world(rig):
    bones = rig.get("bones") or []
    by = {b["index"]: b for b in bones}
    done = {}

    def one(i):
        if i in done:
            return done[i]
        b = by[i]
        par = b.get("parent", -1)
        if par is None:
            par = -1
        par = int(par)
        if par >= 0 and par in by:
            p = one(par)
            dx, dy = rel(float(b["x"]), float(b["y"]), p["rotation"])
            x, y, rot = p["x"] + dx, p["y"] + dy, p["rotation"] + float(b["rotation"])
        else:
            par = -1
            x, y, rot = float(b["x"]), float(b["y"]), float(b["rotation"])
        length = float(b.get("length") or 0.0)
        row = {"index": i, "parent": par,
               "x": round(x, 2), "y": round(y, 2), "rotation": round(rot, 2),
               "ox": float(b["x"]), "oy": float(b["y"]), "lrot": float(b["rotation"]),
               "length": length, "zero": not (length >= 0.5),
               "side": b.get("side") or "front", "role": b.get("role"),
               "aim": None if b.get("aim") is None else int(b["aim"])}
        done[i] = row
        return row

    for b in bones:
        one(b["index"])
    return [done[b["index"]] for b in bones]

def roles(rig):
    return {b["role"]: b["index"] for b in (rig.get("bones") or []) if b.get("role")}

def validate(rig):
    errs = []
    bones = rig.get("bones") or []
    if [b.get("index") for b in bones] != list(range(len(bones))):
        errs.append("骨骼 index 不是 0..%d 连续" % (len(bones) - 1))
    n = len(bones)
    par = {}
    for b in bones:
        i = b.get("index")
        p = b.get("parent", -1)
        p = -1 if p is None else int(p)
        if p >= n or p == i:
            errs.append("#%s 的 parent=%s 非法" % (i, p))
        par[i] = p
    for i in par:
        seen, j = set(), i
        while j >= 0:
            if j in seen:
                errs.append("父级成环：从 #%s 起" % i)
                break
            seen.add(j)
            j = par.get(j, -1)
    for b in bones:
        i = b.get("index")
        a = b.get("aim")
        if a is None:
            continue
        a = int(a)
        if a == i or not 0 <= a < n:
            errs.append("#%s 的 aim=%s 不是别的骨骼" % (i, a))
        elif float(b.get("length") or 0) < 0.5:
            errs.append("#%s 是零长骨骼，不能设置指向" % i)
    return errs

def dump(rig):
    lines = ["{", ' "version": 2,',
             ' "canvas": [%s],' % ", ".join(str(x) for x in rig["canvas"]),
             ' "ground": %s,' % json.dumps(rig["ground"]),
             ' "calib": {']
    cal = rig.get("calib") or {}
    items = list(cal.items())
    for k, (key, v) in enumerate(items):
        lines.append('  %s: %s%s' % (json.dumps(key), json.dumps(v),
                                     "," if k < len(items) - 1 else ""))
    lines.append(" },")
    lines.append(' "bones": [')
    bones = rig["bones"]
    for k, b in enumerate(bones):
        par = b.get("parent", -1)
        parts = ['"index": %d' % b["index"],
                 '"parent": %d' % (-1 if par is None else int(par)),
                 '"x": %s' % json.dumps(b["x"]), '"y": %s' % json.dumps(b["y"]),
                 '"rotation": %s' % json.dumps(b["rotation"]),
                 '"length": %s' % json.dumps(b["length"])]
        for key in KEY_ORDER:
            if key in b:
                v = b[key]
                parts.append('"%s": %s' % (key, "true" if v is True
                                           else ("false" if v is False else json.dumps(v))))
        lines.append("  {" + ", ".join(parts) + "}" + ("," if k < len(bones) - 1 else ""))
    lines += [" ]", "}"]
    return "\n".join(lines) + "\n"

def write(rig):
    errs = validate(rig)
    if errs:
        raise ValueError("；".join(errs))
    os.makedirs(CONFIG, exist_ok=True)
    with open(SKEL, "w", encoding="utf-8") as f:
        f.write(dump(rig))
    return SKEL

def reindex(rig):
    bones = rig["bones"]
    bones.sort(key=lambda b: b["index"])
    old = [b["index"] for b in bones]
    remap = {o: n for n, o in enumerate(old)}
    for n, b in enumerate(bones):
        b["index"] = n
        p = b.get("parent", -1)
        p = -1 if p is None else int(p)
        b["parent"] = remap.get(p, -1) if p >= 0 else -1
        a = b.get("aim")
        if a is not None:
            if int(a) in remap:
                b["aim"] = remap[int(a)]
            else:
                del b["aim"]
    cal = rig.get("calib") or {}
    if cal:
        nc = {}
        for k, v in cal.items():
            nc[str(remap[int(k)]) if k != "near" and int(k) in remap else k] = v
        rig["calib"] = nc
    return rig
