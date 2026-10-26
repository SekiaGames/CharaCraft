import glob
import json
import math
import mimetypes
import os
import py_compile
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WS = os.path.join(ROOT, "ws")
SCRIPTS = os.path.join(WS, "scripts")
CACHE = os.path.join(HERE, ".cache")
RECENT = os.path.join(CACHE, "dirs.json")
PORT = int(os.environ.get("PORT", 8765))
DEFAULT_DIR = os.environ.get("DIR", "")
PY = sys.executable
IMG = (".png", ".jpg", ".jpeg", ".webp")

WATCH = os.environ.get("STUDIO_WATCH", "1") != "0"
SELF = os.path.abspath(__file__)
RUNS = 0
HOT_BAD = ""

def code_stamp(path=SELF):
    try:
        st = os.stat(path)
    except OSError:
        return "0-0"
    return "%d-%d" % (st.st_mtime_ns, st.st_size)

def py_ok(path=SELF):
    try:
        py_compile.compile(path, cfile=os.path.join(CACHE, "hot.pyc"), doraise=True)
        return True, ""
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)

BOOT_STAMP = code_stamp()
UI = os.path.join(HERE, "index.html")

def dir_stamp(d):
    t = 0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                st = os.stat(os.path.join(root, f))
            except OSError:
                continue
            t = max(t, st.st_mtime_ns)
    return str(t)

def ui_stamp():
    return "|".join((code_stamp(UI), dir_stamp(os.path.join(HERE, "js")),
                     dir_stamp(os.path.join(HERE, "css")),
                     code_stamp(COPY_PATH), code_stamp(BLOCKS_PATH)))

def hot_watch(interval=0.5, settle=0.35):
    global HOT_BAD
    base = code_stamp()
    while True:
        time.sleep(interval)
        s = code_stamp()
        if s == base:
            continue
        time.sleep(settle)
        s2 = code_stamp()
        if s2 != s:
            base = s2
            continue
        ok, err = py_ok()
        if not ok:
            if err != HOT_BAD:
                HOT_BAD = err
                print("[hot] server.py 有语法错误，先不重启：%s" % err)
                sys.stdout.flush()
            base = s2
            continue
        HOT_BAD = ""
        while RUNS:
            time.sleep(0.4)
        print("[hot] server.py 变了 → 重启（网页刷新即生效）")
        sys.stdout.flush()
        os.execv(sys.executable, [sys.executable, SELF] + sys.argv[1:])

def find_node():
    p = shutil.which("node")
    if p:
        return p
    for c in glob.glob(os.path.expanduser("~/.workbuddy/binaries/node/versions/*/bin/node")):
        if os.access(c, os.X_OK):
            return c
    return "node"

NODE = find_node()

def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    for c in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg",
              "/opt/local/bin/ffmpeg", os.path.expanduser("~/bin/ffmpeg")):
        if os.access(c, os.X_OK):
            d = os.path.dirname(c)
            if d not in os.environ.get("PATH", "").split(os.pathsep):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            return c
    return ""

FFMPEG = find_ffmpeg()
CONFIG = os.path.join(os.path.dirname(HERE), "config")
SKEL = os.path.join(CONFIG, "skeleton.json")
LIMITS = {"knee": 45.0, "arm": 24.0, "lean": 9.0}

COMFY_HOME = os.environ.get("COMFYUI_DIR") or os.path.expanduser(
    "~/ComfyUI-Installs/ComfyUI/ComfyUI")

COPY_PATH = os.path.join(CONFIG, "copy.json")
BLOCKS_PATH = os.path.join(CONFIG, "blocks.json")

_copy_cache = {"mtime": None, "val": None}
_blocks_cache = {"mtime": None, "val": None}

def _json_cached(path, box):
    m = os.stat(path).st_mtime
    if box["mtime"] != m:
        box["val"] = json.load(open(path, encoding="utf-8"))
        box["mtime"] = m
    return box["val"]

def copy_text():
    return _json_cached(COPY_PATH, _copy_cache)

def blocks_text():
    return _json_cached(BLOCKS_PATH, _blocks_cache)

def dump_blocks(cfg):
    out = ["{"]
    keys = list(cfg)
    for i, k in enumerate(keys):
        tail = "," if i < len(keys) - 1 else ""
        if k != "steps":
            one = json.dumps(cfg[k], ensure_ascii=False, indent=1).replace("\n", "\n ")
            out.append(' "%s": %s%s' % (k, one, tail))
            continue
        out.append(' "steps": {')
        steps = list(cfg[k].items())
        for j, (sid, arr) in enumerate(steps):
            body = ", ".join(json.dumps(x, ensure_ascii=False) for x in arr)
            out.append('  %s: [%s]%s' % (json.dumps(sid, ensure_ascii=False), body,
                                         "," if j < len(steps) - 1 else ""))
        out.append(" }" + tail)
    out.append("}")
    return "\n".join(out) + "\n"

def write_step_blocks(step, blocks):
    cfg = json.load(open(BLOCKS_PATH, encoding="utf-8"))
    cfg.setdefault("steps", {})[step] = list(blocks)
    with open(BLOCKS_PATH, "w", encoding="utf-8") as f:
        f.write(dump_blocks(cfg))
    _blocks_cache["mtime"] = None
    return cfg

def _venv_pys():
    out = []
    for root in (COMFY_HOME, os.path.dirname(COMFY_HOME.rstrip("/"))):
        for d in (".venv", "venv", "standalone-env"):
            p = os.path.join(root, d, "bin", "python")
            if os.path.isfile(p):
                out.append(p)
    out += glob.glob(os.path.expanduser(
        "~/.workbuddy/binaries/python/envs/*/bin/python"))
    return out

_can_cache = {}

def _can(py, mods):
    if not (py and os.path.isfile(py) and os.access(py, os.X_OK)):
        return False
    key = (py, tuple(mods))
    if key in _can_cache:
        return _can_cache[key]
    try:
        r = subprocess.run([py, "-c", "import " + ", ".join(mods)],
                           capture_output=True, timeout=40)
        _can_cache[key] = r.returncode == 0
    except Exception:
        _can_cache[key] = False
    return _can_cache[key]

_cache_py = {}

def find_py(mods, env_var=None):
    key = tuple(mods) + (env_var or "",)
    if key in _cache_py:
        return _cache_py[key]
    cands = []
    if env_var:
        cands.append(os.environ.get(env_var, ""))
    cands += [PY] + _venv_pys()
    for p in cands:
        if _can(p, mods):
            _cache_py[key] = p
            return p
    _cache_py[key] = PY
    return PY

def comfy_py():
    return find_py(("torch", "cv2", "numpy"), env_var="DWPOSE_PY")

def work_py():
    return find_py(("numpy", "PIL"))

def recent():
    try:
        rows = json.load(open(RECENT, encoding="utf-8"))
        return rows[:1] if isinstance(rows, list) else []
    except Exception:
        return []

def remember(d):
    try:
        os.makedirs(CACHE, exist_ok=True)
        json.dump([d], open(RECENT, "w", encoding="utf-8"), indent=1)
    except Exception:
        pass

def case_dir(raw):
    if not raw:
        return None
    d = os.path.abspath(os.path.expanduser(raw))
    return d if os.path.isdir(d) else None

OUT_GUESSES = ("~/ComfyUI-Shared/output",
               "~/ComfyUI-Installs/ComfyUI/ComfyUI/output",
               "~/ComfyUI/output")
_out_cache = {"t": 0, "v": None}

def out_dir(ttl=30):
    if time.time() - _out_cache["t"] < ttl:
        return _out_cache["v"]
    v = None
    for c in filter(None, (os.environ.get("COMFY_OUT"),) + OUT_GUESSES):
        p = os.path.abspath(os.path.expanduser(c))
        if os.path.isdir(p):
            v = p
            break
    _out_cache.update(t=time.time(), v=v)
    return v

def batch_scans(d):
    if not d:
        return {}
    out = {}
    for p in sorted(glob.glob(os.path.join(d, "base", "batches", "*.json"))):
        data = _read_json(p)
        if data and isinstance(data.get("layers"), list):
            out[data.get("batch") or os.path.splitext(os.path.basename(p))[0]] = data
    return out

def psd_batches(d):
    if not d:
        return {}
    out = {}
    pat = re.compile(r"^(\d+)\.psd$", re.I)
    for p in glob.glob(os.path.join(d, "input", "*.psd")):
        m = pat.match(os.path.basename(p))
        if m:
            out[m.group(1)] = p
    return out

def batch_key(bid):
    s = str(bid)
    return (len(s), s)

def first_batch(d):
    bs = sorted(psd_batches(d), key=batch_key)
    return bs[0] if bs else None

def batches(d):
    return sorted(batch_scans(d) or psd_batches(d), key=batch_key)

def pick_folder(prompt="选择素材目录（目录名 = 站姿图名 = ComfyUI 前缀）"):
    if sys.platform != "darwin":
        return None, "只有 macOS 能弹系统选择框，请直接填路径"
    script = ("try\n"
              '  POSIX path of (choose folder with prompt "%s")\n'
              "on error number -128\n"
              '  return ""\n'
              "end try\n") % prompt.replace('"', '\\"')
    try:
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=900)
    except Exception as e:
        return None, str(e)[:80]
    out = (p.stdout or "").strip()
    if not out:
        return None, "cancelled"
    return out.rstrip("/"), None

IN_GUESSES = ("~/ComfyUI-Shared/input",
              "~/ComfyUI-Installs/ComfyUI/ComfyUI/input",
              "~/ComfyUI/input")

def comfy_in():
    for c in filter(None, (os.environ.get("COMFY_IN"),) + IN_GUESSES):
        p = os.path.abspath(os.path.expanduser(c))
        if os.path.isdir(p):
            return p
    return None

def ref_image(d):
    name = os.path.basename(d.rstrip("/"))
    for base, where in ((d, "本地"), (os.path.join(d, "input"), "本地 input"),
                        (comfy_in(), "ComfyUI input")):
        if not base:
            continue
        for ext in IMG:
            if os.path.isfile(os.path.join(base, name + ext)):
                return name + ext, True, where
    for base, where in ((d, "本地"), (os.path.join(d, "input"), "本地 input")):
        for p in sorted(glob.glob(os.path.join(base, "*"))):
            if p.lower().endswith(IMG) and os.path.isfile(p):
                return os.path.basename(p), False, where
    return None, False, None

VID = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
ACTIONS = ("idle", "walk", "run")


def motion_dir(d, act):
    return os.path.join(d, "clip-" + act)

def motion_clip(d, act):
    inp = os.path.join(d, "input")
    for ext in VID:
        p = os.path.join(inp, "clip-%s%s" % (act, ext))
        if os.path.isfile(p):
            return p
    old = os.path.join(d, "motion", "clip.mp4")
    if act == "walk" and os.path.isfile(old):
        return old
    return None

def available_actions(d):
    seen = {}
    if not d:
        return [{"id": a, "video": False, "dir": False} for a in ACTIONS]
    for ext in VID:
        for p in glob.glob(os.path.join(d, "input", "clip-*" + ext)):
            a = os.path.basename(p)[5:-len(ext)]
            if a:
                seen.setdefault(a, {})["video"] = True
    for sub in glob.glob(os.path.join(d, "clip-*")):
        if os.path.isdir(sub):
            a = os.path.basename(sub)[5:]
            if a:
                seen.setdefault(a, {})["dir"] = True
    for a in ACTIONS:
        seen.setdefault(a, {"video": False, "dir": False})
    order = {a: i for i, a in enumerate(ACTIONS)}
    return [{"id": a, "video": bool(seen[a].get("video")), "dir": bool(seen[a].get("dir"))}
            for a in sorted(seen, key=lambda x: (order.get(x, 99), x))]

def case_info(d, act="walk"):
    if not d:
        return None
    inp = os.path.join(d, "input")
    psds = psd_batches(d)
    first = first_batch(d)
    name = os.path.basename(d.rstrip("/"))
    loose = [f for f in glob.glob(os.path.join(inp, "**", "*.png"), recursive=True)
             if not f.endswith("_depth.png")
             and os.path.splitext(os.path.basename(f))[0] != name]
    base = os.path.join(d, "base")
    parts = sorted(os.path.basename(f) for f in glob.glob(os.path.join(base, "parts", "*.png")))
    rig = sorted(glob.glob(os.path.join(base, "rig", "*.json")))
    ref, ref_ok, ref_where = ref_image(d)
    ref_path = None
    if ref:
        ref_path = os.path.join(d, "input", ref) if ref_where == "本地 input" \
            else os.path.join(d, ref)
    md = motion_dir(d, act)
    rig_stem = rig_name(d)
    acts_all = available_actions(d)
    ac = [a["id"] for a in acts_all if a.get("dir") or a.get("video")]
    macts = [a["id"] for a in acts_all if a.get("video")]
    atlas = os.path.join(d, "output", rig_stem + ".atlas")
    m = {
        "act": act,
        "clip": motion_clip(d, act),
        "frames": len(glob.glob(os.path.join(md, "frames", "*.png"))),
        "bones": os.path.isfile(os.path.join(md, "dwpose_bones.json")),
        "calib": bool(rig_calib()),
        "loop": os.path.isfile(os.path.join(md, "loop.json")),
        "rig": os.path.isfile(os.path.join(md, "animations.json")),
        "atlas": os.path.isfile(atlas),
        "rigged": sorted(os.path.basename(os.path.dirname(p))[len("clip-"):]
                         for p in glob.glob(os.path.join(d, "clip-*", "animations.json"))),
    }
    return {"path": d, "name": name, "prefix": name, "ref": ref, "ref_ok": ref_ok,
            "ref_where": ref_where, "ref_path": ref_path,
            "comfy_in": comfy_in(), "motion": m, "actions": acts_all,
            "has_input": os.path.isdir(inp), "psd": len(psds),
            "acts": ac,
            "macts": macts,
            "frames_all": bool(macts) and all(
                glob.glob(os.path.join(d, "clip-" + x, "frames", "*.png")) for x in macts),
            "bones_all": bool(macts) and all(
                os.path.isfile(os.path.join(d, "clip-" + x, "dwpose_bones.json")) for x in macts),
            "rig_all": bool(ac) and all(os.path.isfile(os.path.join(d, "base", "rig", x + ".json"))
                                        for x in ac),
            "out_json": os.path.isfile(os.path.join(d, "output", rig_stem + ".json")),
            "rig_stem": rig_stem, "stem": rig_stem,
            "first": first, "batches_all": batches(d),
            "runs": len(psds), "loose": len(loose),
            "batches": sorted(psds), "comfy_out": out_dir(),
            "parts": [p for p in parts if p != "parts.json"], "rig": [os.path.basename(r) for r in rig],
            "atlas": os.path.isfile(atlas)}

def matrix(d, act):
    scans = batch_scans(d)
    first = first_batch(d)
    if not scans and not psd_batches(d):
        return {"batches": [], "layers": [], "selection": {}, "first": first, "extra": [],
                "act": act}

    ids = sorted(set(scans) | set(psd_batches(d)))
    cols = []
    for bid in ids:
        sc = scans.get(bid)
        cols.append({"id": bid, "split": bool(sc),
                     "layers": len((sc or {}).get("layers") or []),
                     "first": bid == first,
                     "time": bid.split("_")[1] if "_" in bid else bid})

    flayers = (scans.get(first) or {}).get("layers") or []
    disabled = read_disabled(d)
    sel = read_selection(d, act)

    rows = []
    for L in flayers:
        name = L["name"]
        cells = {}
        for bid in ids:
            for x in (scans.get(bid) or {}).get("layers") or []:
                if x["name"] == name:
                    cells[bid] = {"px": x.get("px", 0),
                                  "empty": bool(x.get("empty", True)),
                                  "why": x.get("why")}
                    break
        own = cells.get(first) or {}
        rows.append({"name": name, "index": L.get("index"),
                     "auto": None if (name in disabled or own.get("empty")) else first,
                     "sel": sel.get(name), "disabled": name in disabled,
                     "cells": cells})

    have = {L["name"] for L in flayers}
    extra = sorted({x["name"] for bid in ids if bid != first
                    for x in (scans.get(bid) or {}).get("layers") or []} - have)
    return {"batches": cols, "layers": rows, "selection": sel, "act": act,
            "disabled": sorted(disabled), "first": first, "extra": extra}

def disabled_path(d):
    return editkit_mod().parts_disabled(d)

def read_disabled(d):
    p = disabled_path(d)
    if not os.path.isfile(p):
        return set()
    try:
        v = json.load(open(p, encoding="utf-8"))
        return {x for x in v if isinstance(x, str) and x} if isinstance(v, list) else set()
    except Exception:
        return set()

def write_disabled(d, name, off):
    p = disabled_path(d)
    cur = read_disabled(d)
    if off:
        cur.add(name)
    else:
        cur.discard(name)
    if not cur:
        if os.path.isfile(p):
            os.remove(p)
        return 0
    _write_json(p, sorted(cur), indent=1)
    return len(cur)

def write_selection(d, act, mapping):
    p = parts_selection_path(d, act)
    clean = {k: v for k, v in (mapping or {}).items()
             if isinstance(k, str) and isinstance(v, str) and v in batches(d)}
    if not clean:
        if os.path.isfile(p):
            os.remove(p)
        return 0
    _write_json(p, clean, indent=1)
    return len(clean)

def rig_name(d):
    return re.sub(r"[^a-z0-9]+", "_", os.path.basename(d.rstrip("/")).lower()).strip("_") or "rig"

_pv = {"key": None, "val": None}

def short_run(run):
    r = (run or "").replace("run-", "")
    m = re.search(r"\d{8}_(\d{6})", r)
    return m.group(1) if m else r[:12]

def preview_key(d, act):
    inp = os.path.join(d, "input")
    marks = []
    for p in (parts_selection_path(d, act), disabled_path(d)):
        marks.append(os.path.getmtime(p) if os.path.isfile(p) else 0)
    for p in sorted(glob.glob(os.path.join(inp, "*.psd"))):
        marks.append(os.path.getmtime(p))
    return (d, act, tuple(marks))

def preview(d, act):
    k = preview_key(d, act)
    if _pv["key"] == k:
        return _pv["val"]
    lay = psdkit_mod().effective(d, act)
    layers = [{"name": L["name"], "im": L["img"],
               "x": L["left"], "y": L["top"],
               "w": L["img"].width, "h": L["img"].height,
               "index": L["index"], "from": L["from"]} for L in lay["layers"]]
    res = {"canvas": (lay["width"], lay["height"]), "layers": layers, "first": lay["first"],
           "v": int(time.time() * 1000)}
    _pv.update(key=k, val=res)
    return res

def composite(res):
    if res.get("_comp") is not None:
        return res["_comp"]
    from PIL import Image
    import numpy as np
    W, H = res["canvas"]
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for L in sorted(res["layers"], key=lambda L: (L.get("index") or 0, L["name"])):
        im.alpha_composite(L["im"], (L["x"], L["y"]))
    try:
        sys.path.insert(0, SCRIPTS)
        import layerkit
        im = layerkit.denoise(im)
    except Exception:
        pass
    a = np.array(im)
    ys, xs = np.where(a[..., 3] > 8)
    if len(xs):
        pad = 12
        box = (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
               min(W, int(xs.max()) + 1 + pad), min(H, int(ys.max()) + 1 + pad))
        im = im.crop(box)
    bg = Image.new("RGBA", im.size, (247, 246, 242, 255))
    bg.alpha_composite(im)
    out = bg.convert("RGB")
    res["_comp"] = out
    return out

def preview_payload(d, act):
    res = preview(d, act)
    W, H = res["canvas"]
    cw, ch = composite(res).size
    first = res.get("first")

    def url(kind, name=None):
        q = "?dir=%s&act=%s&v=%d" % (quote(d, safe=""), quote(act, safe=""), res["v"])
        if name:
            q += "&name=" + quote(name, safe="")
        return "/api/%s%s" % (kind, q)

    parts = [{"name": L["name"], "w": L["w"], "h": L["h"], "url": url("part", L["name"]),
              "from": [short_run(L["from"])], "batch": L["from"], "src": "psd",
              "sub": bool(first and L["from"] != first),
              "z": L.get("index") or 0, "index": L.get("index")}
             for L in sorted(res["layers"], key=lambda L: (L.get("index") or 0, L["name"]))]
    return {"canvas": [W, H], "parts": parts, "composite": url("composite"),
            "first": first, "first_short": short_run(first),
            "composite_size": [cw, ch], "v": res["v"], "act": act,
            "selection": read_selection(d, act), "dropped": 0}

def read_selection(d, act):
    return (_read_json(parts_selection_path(d, act)) or {}) if d else {}

def _read_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None

def rigkit_mod():
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import rigkit
    return rigkit

def psdkit_mod():
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import psdkit
    return psdkit

def editkit_mod():
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import editkit
    return editkit

def skeleton_payload(d):
    return {"rig": rigkit_mod().read(), "path": SKEL, "ref": None}

def rig_bones(d):
    r = rigkit_mod().read()
    if not r:
        return []
    return [{"index": b["index"], "role": b.get("role")} for b in (r.get("bones") or [])]

def attachments_path(d):
    return os.path.join(CONFIG, "attachments_template.json")

def _layers(d):
    sc = batch_scans(d)
    first = first_batch(d)
    b = sc.get(first) or {}
    return first, (b.get("layers") or [])

def _canvas(d):
    b = batch_scans(d).get(first_batch(d)) or {}
    return int(b.get("width") or 1024), int(b.get("height") or 1024)

def guess_rows(d):
    batch, L = _layers(d)
    if not L:
        return batch, []
    W, _H = _canvas(d)
    sys.path.insert(0, SCRIPTS)
    import layerkit
    ri = rigkit_mod().roles(rigkit_mod().read())
    return batch, layerkit.guess_rows(W, L, ri)

def attachments_payload(d):
    batch, L = _layers(d)
    saved = _read_json(attachments_path(d))
    bones = [{"index": b["index"], "role": b.get("role")}
             for b in ((rigkit_mod().read() or {}).get("bones") or [])]
    _, guessed = guess_rows(d)
    sys.path.insert(0, SCRIPTS)
    import layerkit
    rows, added, gone = layerkit.sync_rows((saved or {}).get("rows") or [], guessed)
    sizes = {x["name"]: [x["right"] - x["left"], x["bottom"] - x["top"]] for x in L}
    W, H = _canvas(d)
    return {"batch": (saved or {}).get("batch") or batch,
            "first": batch,
            "canvas": (saved or {}).get("canvas") or [W, H],
            "layers": [{"name": x["name"], "z": int(x.get("index", 0)),
                        "size": sizes.get(x["name"], [0, 0]),
                        "from": x.get("from")} for x in L],
            "rows": rows, "bones": bones, "saved": bool(saved),
            "generated": bool((saved or {}).get("generated")) or not saved,
            "added": added, "gone": gone,
            "path": attachments_path(d)}

def save_attachments(d, body):
    sys.path.insert(0, SCRIPTS)
    import layerkit
    rows = body.get("rows") or []
    keep = []
    for r in rows:
        if not (r.get("layer") or "").strip():
            continue
        row = {"layer": r["layer"].strip(),
               "bones": [int(x) for x in (r.get("bones") or []) if x not in (None, "")],
               "z": int(r.get("z") or 0),
               "enabled": bool(r.get("enabled", True))}
        keep.append(row)
    keep.sort(key=lambda r: r["z"])
    data = {"version": 2, "batch": body.get("batch"), "canvas": body.get("canvas"),
            "rows": keep}
    text = layerkit.dump_attachments(data)
    p = attachments_path(d)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p, len(keep)

def parts_selection_path(d, act):
    return editkit_mod().parts_selection(d, act)


def keys_path(d, act):
    return editkit_mod().bone_keys(d, act)


def keyframes_path(d, act):
    return editkit_mod().frame_sheet(d, act)


def picked_path(d, act):
    return editkit_mod().picked(d, act)


def sheet_of(d, act):
    p = keyframes_path(d, act)
    if os.path.isfile(p):
        s = _read_json(p) or {}
        s["auto"] = False
        return s
    s = _read_json(picked_path(d, act)) or {}
    s["auto"] = True
    return s


def rig_calib():
    return (rigkit_mod().read() or {}).get("calib") or None


def bone_meta():
    r = rigkit_mod().read()
    if not r:
        return {}
    out = {}
    for b in r["bones"]:
        L = float(b.get("length") or 0)
        out[str(b["index"])] = {"p": b.get("parent", -1), "l": round(L, 3),
                                "x": round(float(b.get("x") or 0), 3),
                                "y": round(float(b.get("y") or 0), 3),
                                "r": b.get("role"), "s": b.get("side") or "front",
                                "a": None if b.get("aim") is None else int(b["aim"])}
    return out


def rig_roles(d):
    return rigkit_mod().roles(rigkit_mod().read() or {})


FPS_CACHE = {}


def clip_fps(d, act):
    key = (d, act)
    if key in FPS_CACHE:
        return FPS_CACHE[key]
    p = os.path.join(d, "input", "clip-%s.mp4" % act)
    v = 24.0
    if os.path.isfile(p):
        probe = os.environ.get("FFPROBE") or "ffprobe"
        out = subprocess.run([probe, "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", p],
                             capture_output=True, text=True, timeout=20)
        t = (out.stdout or "").strip().split("\n")[0]
        if "/" in t:
            a, b = t.split("/")
            v = round(float(a) / float(b), 3)
        elif t:
            v = round(float(t), 3)
    FPS_CACHE[key] = v
    return v


def motion_payload(d, act="walk"):
    md = motion_dir(d, act)
    fr = sorted(glob.glob(os.path.join(md, "frames", "f_*.png")))
    src = _read_json(os.path.join(md, "dwpose_bones.json")) or {}
    frames = src.get("frames") or []
    calib = rig_calib() or {}
    if len(frames) != len(fr):
        frames = [{"size": [0, 0], "hip": None, "bones": {}} for _ in fr]
    stem = "%s-%s" % (rig_name(d), act)
    sheet = sheet_of(d, act)
    out = {"act": act, "clip": motion_clip(d, act), "stem": stem,
           "rig_stem": rig_name(d),
           "rig": os.path.isfile(os.path.join(d, "output", rig_name(d) + ".json")),
           "atlas": os.path.isfile(os.path.join(d, "output", stem + ".atlas")),
           "frames": len(fr),
           "frames_list": [{"n": i + 1, "name": os.path.basename(p), "path": p,
                            "w": (po.get("size") or [0, 0])[0],
                            "h": (po.get("size") or [0, 0])[1],
                            "hip": po.get("hip"), "bones": po.get("bones") or {}}
                           for i, (p, po) in enumerate(zip(fr, frames))],
           "scale": src.get("scale"),
           "keys": _read_json(keys_path(d, act)) or {},
           "framesheet": sheet,
           "keyframes": sheet.get("frames") or [],
           "roles": rig_roles(d),
           "meta": bone_meta(),
           "limits": LIMITS,
           "calib": calib,
           "near": calib.get("near"),
           "fps": clip_fps(d, act)}
    return out

def rel(d, p):
    if not p:
        return ""
    try:
        r = os.path.relpath(p, d)
    except ValueError:
        return p
    return p if r.startswith("..") else r.replace(os.sep, "/")

def home_short(p):
    if not p:
        return ""
    h = os.path.expanduser("~")
    return "~" + p[len(h):] if p.startswith(h) else p

def _script(name):
    return os.path.join(SCRIPTS, name)

def _write_json(path, data, indent=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)

def _step(sid, deps, needs, cmd, scripts=(), ins=(), outs=(), out=(), cwd=None, env=None):
    s = {"id": sid, "deps": list(deps), "needs": tuple(needs), "cwd": cwd or ROOT,
         "scripts": list(scripts), "ins": list(ins), "outs": list(outs),
         "cmd": cmd, "out": list(out)}
    if env:
        s["env"] = env
    return s

def split_steps(d, info):
    if not d:
        return []
    case_name = os.path.basename(d.rstrip("/"))
    ref_rel = rel(d, info.get("ref_path")) if info.get("ref_path") else case_name + ".png"
    comfy_out = out_dir()
    src_rel = (home_short(os.path.join(comfy_out, case_name + "_<YYYYMMDD_HHMMSS>.psd"))
               if comfy_out else "ComfyUI 输出目录/%s_<YYYYMMDD_HHMMSS>.psd" % case_name)
    psd_in = ["input/<批次>.psd"]
    ed = editkit_mod().DIR
    acts = [a["id"] for a in available_actions(d) if a.get("dir") or a.get("video")]
    name = rig_name(d)
    outd = os.path.join(d, "output")
    cut_cmd, skin_cmd = [], []
    for act in acts:
        cut_cmd.append([work_py(), _script("spine-pack.py"), d, "--act", act])
        skin_cmd.append([work_py(), _script("spine-skin.py"), d, "--act", act])
    return [
        _step("sync", [], ("comfy_out",),
              [[work_py(), _script("sync-psd.py"), d]],
              scripts=("sync-psd.py",), ins=(src_rel,),
              outs=("input/<批次>.psd", "input/<批次>_backup.psd"),
              out=(os.path.join(d, "input", "*.psd"),)),
        _step("split", ["sync"], ("psd",),
              [[work_py(), _script("psd-split.py"), d]],
              scripts=("psd-split.py",), ins=psd_in,
              outs=("base/batches/<批次>.json",),
              out=(os.path.join(d, "base", "batches", "*.json"),)),
        _step("pack", ["split"], ("psd", "acts"), cut_cmd,
              scripts=("spine-pack.py",),
              ins=("input/<批次>.psd", ed + "/Edit-Parts-<动作>.json",
                   ed + "/Edit-PartsDisable.json", "config/attachments_template.json"),
              outs=("output/%s-<动作>.png" % name, "output/%s.atlas" % name),
              out=(os.path.join(outd, name + "-*.png"), os.path.join(outd, name + ".atlas"))),
        _step("skin", ["split"], ("psd", "acts"), skin_cmd,
              scripts=("spine-skin.py",),
              ins=("input/<批次>.psd", ed + "/Edit-Parts-<动作>.json",
                   ed + "/Edit-PartsDisable.json", "config/attachments_template.json",
                   "config/skeleton.json"),
              outs=("base/rig/<动作>.json",),
              out=(os.path.join(d, "base", "rig", "*.json"),)),
        _step("cutpack", ["pack", "skin", "anim"], ("rig_all", "atlas"),
              [[work_py(), _script("spine-merge.py"), d, "--name", name]],
              scripts=("spine-merge.py",), cwd=WS,
              ins=("base/rig/<动作>.json", "clip-*/animations.json", "output/%s.atlas" % name),
              outs=("output/%s.json" % name, "output/preview.html"),
              out=(os.path.join(outd, name + ".json"), os.path.join(outd, "preview.html"))),
    ]

def motion_steps(d, info):
    if not d:
        return []
    ed = editkit_mod().DIR
    acts = [a["id"] for a in available_actions(d) if a.get("video")]

    def cdir(a):
        return os.path.join(d, "clip-" + a)

    frames_cmd, probe_cmd, key_cmd, anim_cmd = [], [], [], []
    for a in acts:
        fdir = os.path.join(cdir(a), "frames")
        frames_cmd += [
            ["mkdir", "-p", fdir],
            ["/usr/bin/find", fdir, "-name", "f_*.png", "-delete"],
            [FFMPEG or "ffmpeg", "-v", "error", "-y", "-i", motion_clip(d, a) or "",
             "-start_number", "1", os.path.join(fdir, "f_%04d.png")],
            [work_py(), _script("frame-check.py"), cdir(a)]]
        probe_cmd.append([comfy_py(), _script("pose-extract.py"),
                          os.path.join(fdir, "f_*.png"),
                          os.path.join(cdir(a), "dwpose_bones.json")])
        key_cmd.append([work_py(), _script("motion-keyframes.py"), d,
                        "--act", a, "--only-if-auto"])
        anim_cmd.append([work_py(), _script("spine-anim.py"), d,
                         "--act", a,
                         "--knee-max", "%g" % LIMITS["knee"], "--arm-max", "%g" % LIMITS["arm"],
                         "--lean-max", "%g" % LIMITS["lean"]])
    return [
        _step("frames", [], ("macts",), frames_cmd,
              scripts=("ffmpeg", "frame-check.py"),
              ins=("input/clip-<动作>.mp4",),
              outs=("clip-<动作>/frames/f_0001.png…", "clip-<动作>/source_sha1_mark.json"),
              out=(os.path.join(d, "clip-*", "frames", "*.png"),)),
        _step("probe", ["frames"], ("frames_all",), probe_cmd,
              scripts=("pose-extract.py",),
              ins=("clip-<动作>/frames/*.png",),
              outs=("clip-<动作>/dwpose_bones.json", "clip-<动作>/dwpose_sha1_mark.json"),
              out=(os.path.join(d, "clip-*", "dwpose_bones.json"),
                   os.path.join(d, "clip-*", "dwpose_sha1_mark.json")),
              env={"COMFYUI_DIR": COMFY_HOME}),
        _step("autokeys", ["probe"], ("bones_all",), key_cmd,
              scripts=("motion-keyframes.py",),
              ins=("clip-<动作>/dwpose_bones.json", ed + "/Edit-FrameSheet-<动作>.json"),
              outs=("clip-<动作>/keyframes.json",),
              out=(os.path.join(d, "clip-*", "keyframes.json"),)),
        _step("anim", ["autokeys"], ("bones_all",), anim_cmd,
              scripts=("spine-anim.py",),
              ins=("clip-<动作>/dwpose_bones.json",
                   "clip-<动作>/keyframes.json",
                   ed + "/Edit-FrameSheet-<动作>.json",
                   ed + "/Edit-BoneKeys-<动作>.json",
                   "config/skeleton.json"),
              outs=("clip-<动作>/animations.json",),
              out=(os.path.join(d, "clip-*", "animations.json"),)),
    ]

def depth_of(steps_list):
    by_id = {s["id"]: s for s in steps_list}
    seen = {}

    def walk(i):
        if i not in seen:
            seen[i] = 0
            for p in by_id[i]["deps"]:
                seen[i] = max(seen[i], walk(p) + 1)
        return seen[i]

    for s in steps_list:
        walk(s["id"])
    return seen

MOTION_ONLY = ("frames", "probe", "autokeys", "anim")

def steps(d, info):
    ss = split_steps(d, info) + motion_steps(d, info)
    if not ss:
        return []
    acts = info.get("acts") or []
    macts = info.get("macts") or []
    ctx = {"case": os.path.basename(d.rstrip("/")), "name": rig_name(d),
           "acts": "、".join(acts) or "—", "n_acts": len(acts)}
    ctx_m = dict(ctx, acts="、".join(macts) or "—", n_acts=len(macts))
    cp = copy_text()["steps"]
    for s in ss:
        c = cp[s["id"]]
        s["label"] = c["label"]
        s["desc"] = c["desc"].format(**(ctx_m if s["id"] in MOTION_ONLY else ctx))
    order = {s["id"]: n for n, s in enumerate(ss)}
    dep = depth_of(ss)
    ss.sort(key=lambda s: (dep[s["id"]], order[s["id"]]))
    for s in ss:
        s["depth"] = dep[s["id"]]
    return ss

def deps():
    wp, cp = work_py(), comfy_py()
    ok = {}
    for mod in ("PIL", "numpy", "scipy", "psd_tools"):
        ok[mod] = _can(wp, (mod,))
    ok["dwpose"] = _can(cp, ("torch", "cv2")) and os.path.isdir(
        os.path.join(COMFY_HOME, "custom_nodes", "comfyui_controlnet_aux"))
    ok["work_py"] = wp
    ok["comfy_py"] = cp
    return ok

def step_view(s, info, dp):
    miss = []
    if "comfy_out" in s["needs"] and not out_dir():
        miss.append("找不到 ComfyUI 输出目录")
    if "psd" in s["needs"] and info and not info["psd"]:
        miss.append("input/ 里没有 PSD（先跑「同步 PSD」）")
    if "acts" in s["needs"] and info and not info.get("acts"):
        miss.append("input/ 里没有 clip-<动作>.mp4（先放视频）")
    if "macts" in s["needs"] and info and not info.get("macts"):
        miss.append("input/ 里没有 clip-<动作>.mp4（把视频放进 input/）")
    if "frames_all" in s["needs"] and info and not info.get("frames_all"):
        miss.append("还有动作没抽帧（先跑「抽帧」）")
    if "bones_all" in s["needs"] and info and not info.get("bones_all"):
        miss.append("还有动作没有 dwpose_bones.json（先跑「DWPose 骨骼」）")
    if "atlas" in s["needs"] and info and not info["atlas"]:
        miss.append("还没出多页 atlas（先跑「打包图集」）")
    if "rig_all" in s["needs"] and info and not info.get("rig_all"):
        miss.append("还有动作没有皮肤片段（先跑「打包图集」）")
    if s["id"] == "frames" and not FFMPEG:
        miss.append("缺 ffmpeg（brew install ffmpeg）")
    if s["id"] == "probe" and not dp.get("dwpose"):
        miss.append("找不到能跑 DWPose 的解释器（要 torch + cv2，用 DWPOSE_PY 指定）")
    items = []
    for pat in s["out"]:
        for p in sorted(glob.glob(pat)):
            if os.path.isfile(p):
                items.append({"path": p, "name": os.path.basename(p),
                              "size": os.path.getsize(p), "mtime": int(os.path.getmtime(p))})
    return {"id": s["id"], "name": s["label"], "desc": s["desc"], "depth": s["depth"],
            "blocked": miss, "has_cmd": bool(s["cmd"]), "artifacts": items,
            "scripts": s.get("scripts") or [],
            "ins": s.get("ins") or [], "outs": s.get("outs") or [],
            "manual": bool(s.get("manual"))}

def allow(path, d):
    p = os.path.realpath(path)
    bases = [ROOT] + ([d] if d else []) + recent()
    for base in bases:
        if not base:
            continue
        b = os.path.realpath(base)
        if os.path.commonpath([p, b]) == b:
            return p if os.path.isfile(p) else None
    return None

def _one(q, key, dflt=""):
    return (q.get(key) or [dflt])[0] or dflt

def _body_dir(body):
    return case_dir((body.get("dir") or "").strip())

def api_state(h, q, raw, d, info, act):
    dp = deps()
    if d:
        remember(d)
    tab = (_one(q, "tab", "motion")).strip()
    return h._send(200, json.dumps({
        "dir_input": raw, "case": info, "tab": tab,
        "action": ((info or {}).get("motion") or {}).get("act", "walk"),
        "last": (recent() or [None])[0], "deps": dp,
        "copy": copy_text(), "blocks": blocks_text(),
        "steps": [step_view(s, info, dp) for s in steps(d, info)]},
        ensure_ascii=False))

def api_file(h, q, raw, d, info, act):
    p = allow(unquote(_one(q, "p")), d)
    if not p:
        return h._send(404, "not found", "text/plain; charset=utf-8")
    ctype = mimetypes.guess_type(p)[0] or "application/octet-stream"
    if p.endswith((".json", ".atlas")):
        ctype = "application/json; charset=utf-8"
    if p.endswith(".html"):
        ctype = "text/html; charset=utf-8"
    with open(p, "rb") as f:
        return h._send(200, f.read(), ctype)

def api_hot(h, q, raw, d, info, act):
    return h._send(200, json.dumps({
        "boot": BOOT_STAMP, "disk": code_stamp(), "ui": ui_stamp(),
        "watching": WATCH, "runs": RUNS}))

def api_pick(h, q, raw, d, info, act):
    path, err = pick_folder()
    if err == "cancelled":
        return h._send(200, json.dumps({"cancelled": True}))
    if err:
        return h._send(500, {"error": err})
    return h._send(200, json.dumps({"path": path}, ensure_ascii=False))

def api_attachments(h, q, raw, d, info, act):
    if not d:
        return h._send(400, {"error": "目录不存在"})
    return h._send(200, json.dumps(attachments_payload(d), ensure_ascii=False))

def api_skeleton(h, q, raw, d, info, act):
    if not d:
        return h._send(400, {"error": "目录不存在"})
    p = skeleton_payload(d)
    p["ref"] = (info or {}).get("ref_path")
    p["canvas"] = ((p["rig"] or {}).get("canvas")) or [1024, 1024]
    return h._send(200, json.dumps(p, ensure_ascii=False))

def api_motion(h, q, raw, d, info, act):
    if not d:
        return h._send(400, {"error": "目录不存在"})
    a = ((info or {}).get("motion") or {}).get("act", "walk")
    return h._send(200, json.dumps(motion_payload(d, a), ensure_ascii=False))

def api_preview(h, q, raw, d, info, act):
    if not d:
        return h._send(400, {"error": "目录不存在"})
    try:
        return h._send(200, json.dumps(preview_payload(d, act), ensure_ascii=False))
    except SystemExit as e:
        return h._send(409, {"error": str(e)})
    except Exception as e:
        return h._send(500, {"error": str(e)[:200]})

def _preview_png(h, d, act, q, whole):
    if not d:
        return h._send(404, "no dir", "text/plain")
    from io import BytesIO
    try:
        res = preview(d, act)
        buf = BytesIO()
        if whole:
            composite(res).save(buf, "PNG")
        else:
            name = _one(q, "name")
            p = next((L for L in res.get("layers", []) if L["name"] == name), None)
            if not p:
                return h._send(404, "no such part", "text/plain")
            p["im"].save(buf, "PNG")
        return h._send(200, buf.getvalue(), "image/png")
    except Exception as e:
        return h._send(500, str(e)[:200], "text/plain; charset=utf-8")

def api_part(h, q, raw, d, info, act):
    return _preview_png(h, d, act, q, False)

def api_composite(h, q, raw, d, info, act):
    return _preview_png(h, d, act, q, True)

def api_layers(h, q, raw, d, info, act):
    if not d:
        return h._send(400, {"error": "目录不存在"})
    return h._send(200, json.dumps(matrix(d, act), ensure_ascii=False))

def api_run(h, q, raw, d, info, act):
    return h.stream(_one(q, "step"), d, info)

GET_ROUTES = {
    "/api/state": api_state,
    "/api/file": api_file,
    "/api/hot": api_hot,
    "/api/pick": api_pick,
    "/api/attachments": api_attachments,
    "/api/skeleton": api_skeleton,
    "/api/motion": api_motion,
    "/api/preview": api_preview,
    "/api/part": api_part,
    "/api/composite": api_composite,
    "/api/layers": api_layers,
    "/api/run": api_run,
}

def post_disable(h, body):
    d = _body_dir(body)
    if not d:
        return h._send(400, {"error": "目录不存在"})
    name = (body.get("name") or "").strip()
    if not name:
        return h._send(400, {"error": "缺 name"})
    n = write_disabled(d, name, bool(body.get("off")))
    return h._send(200, json.dumps({"disabled": n, "name": name}, ensure_ascii=False))

def post_blocks(h, body):
    step = (body.get("step") or "").strip()
    if not step:
        return h._send(400, {"error": "缺 step"})
    cfg = write_step_blocks(step, body.get("blocks") or [])
    return h._send(200, json.dumps({"blocks": cfg, "ui": ui_stamp()}, ensure_ascii=False))

def post_attachments(h, body):
    d = _body_dir(body)
    if not d:
        return h._send(400, {"error": "目录不存在"})
    path, cnt = save_attachments(d, body)
    return h._send(200, json.dumps({"saved": path, "rows": cnt}, ensure_ascii=False))

def post_autokeys(h, body):
    d = _body_dir(body)
    if not d:
        return h._send(400, {"error": "目录不存在"})
    act = (body.get("action") or "walk").strip()
    p = keyframes_path(d, act)
    if not bool(body.get("auto", True)):
        sel = body.get("frames")
        if not sel:
            sel = (sheet_of(d, act).get("frames") or [])
        sel = [int(x) for x in sel]
        _write_json(p, {"frames": sel}, indent=1)
        return h._send(200, json.dumps({"ok": True, "auto": False, "frames": sel},
                                       ensure_ascii=False))
    if os.path.isfile(p):
        os.remove(p)
    r = subprocess.run([work_py(), _script("motion-keyframes.py"),
                        d, "--act", act, "--step", str(body.get("step") or 0)],
                       capture_output=True, text=True)
    sheet = sheet_of(d, act)
    return h._send(200, json.dumps({"ok": r.returncode == 0, "auto": True,
                                    "frames": sheet.get("frames") or [],
                                    "log": (r.stdout + r.stderr).strip()},
                                   ensure_ascii=False))

def post_keyframes(h, body):
    d = _body_dir(body)
    if not d:
        return h._send(400, {"error": "目录不存在"})
    act = (body.get("action") or "walk").strip()
    sel = []
    for x in (body.get("frames") or []):
        v = int(x)
        if v not in sel:
            sel.append(v)
    p = keyframes_path(d, act)
    _write_json(p, {"frames": sel}, indent=1)
    return h._send(200, json.dumps({"frames": sel, "n": len(sel), "auto": False},
                                   ensure_ascii=False))

def post_keys(h, body):
    d = _body_dir(body)
    if not d:
        return h._send(400, {"error": "目录不存在"})
    act = (body.get("action") or "walk").strip()
    n = int(body.get("frame") or 0)
    p = keys_path(d, act)
    data = _read_json(p) or {}
    if body.get("bones"):
        data[str(n)] = body["bones"]
    else:
        data.pop(str(n), None)
    _write_json(p, data)
    return h._send(200, {"frames": len(data), "file": p})

def post_skeleton(h, body):
    rig = body.get("rig") or {}
    if not rig.get("bones"):
        return h._send(400, {"error": "缺 rig.bones"})
    rk = rigkit_mod()
    base = rk.read() or {}
    rig = dict(rig)
    rig["version"] = 2
    rig["canvas"] = rig.get("canvas") or base.get("canvas") or [1024, 1024]
    if rig.get("ground") is None:
        rig["ground"] = base.get("ground")
    if rig.get("calib") is None:
        rig["calib"] = base.get("calib") or {}
    for b in rig["bones"]:
        par = b.get("parent", -1)
        b["parent"] = -1 if par is None else int(par)
        for k in ("side", "role"):
            if b.get(k) in (None, False, ""):
                b.pop(k, None)
        if b.get("aim") is None:
            b.pop("aim", None)
        else:
            b["aim"] = int(b["aim"])
    errs = rk.validate(rig)
    if errs:
        return h._send(400, {"error": "；".join(errs)})
    return h._send(200, json.dumps({"saved": rk.write(rig)}, ensure_ascii=False))

def post_select(h, body):
    d = _body_dir(body)
    if not d:
        return h._send(400, {"error": "目录不存在"})
    act = (body.get("action") or "walk").strip()
    got = write_selection(d, act, body.get("selection") or {})
    return h._send(200, json.dumps({"saved": got, "act": act}, ensure_ascii=False))

POST_ROUTES = {
    "/api/disable": post_disable,
    "/api/blocks": post_blocks,
    "/api/attachments": post_attachments,
    "/api/autokeys": post_autokeys,
    "/api/keyframes": post_keyframes,
    "/api/keys": post_keys,
    "/api/skeleton": post_skeleton,
    "/api/select": post_select,
}

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype=None, headers=None):
        with open(path, "rb") as f:
            return self._send(200, f.read(),
                              ctype or mimetypes.guess_type(path)[0]
                              or "application/octet-stream", headers)

    def _static(self, path):
        p = os.path.normpath(os.path.join(HERE, path.lstrip("/")))
        if not p.startswith(HERE) or not os.path.isfile(p):
            return self._send(404, "not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(p)[0] or "application/octet-stream"
        return self._file(p, ctype + "; charset=utf-8", {"Cache-Control": "no-store"})

    def _ctx(self, q):
        raw = (_one(q, "dir") or DEFAULT_DIR or (recent() or [""])[0]).strip()
        d = case_dir(raw)
        act = ((q.get("act") or q.get("action") or ["walk"])[0] or "walk").strip() or "walk"
        return raw, d, case_info(d, act)

    def _guard(self, fn):
        try:
            return fn()
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as e:
            traceback.print_exc()
            try:
                self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})
            except Exception:
                pass
            return None

    def do_GET(self):
        return self._guard(self._get)

    def do_POST(self):
        return self._guard(self._post)

    def _get(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        raw, d, info = self._ctx(q)
        act = _one(q, "act") or _one(q, "action") or "walk"
        if u.path in GET_ROUTES:
            return GET_ROUTES[u.path](self, q, raw, d, info, act)
        if u.path.startswith("/js/") or u.path.startswith("/css/"):
            return self._static(u.path)
        if u.path == "/":
            return self._file(UI, "text/html; charset=utf-8",
                              {"Cache-Control": "no-store, must-revalidate",
                               "Pragma": "no-cache"})
        if u.path == "/vendor/spine-core.js":
            return self._file(os.path.join(WS, "node_modules", "@esotericsoftware", "spine-core",
                                           "dist", "iife", "spine-core.min.js"),
                              "application/javascript; charset=utf-8")
        return self._send(404, "not found", "text/plain")

    def _post(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = {}
        if n:
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, {"error": "bad json"})
        fn = POST_ROUTES.get(urlparse(self.path).path)
        if not fn:
            return self._send(404, "not found", "text/plain")
        return fn(self, body)

    def stream(self, sid, d, info):
        global RUNS
        s = next((x for x in steps(d, info) if x["id"] == sid), None)
        if not s:
            return self._send(400, "unknown step", "text/plain")
        if not s["cmd"]:
            return self._send(409, "该步骤还没接命令行实现", "text/plain")

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        RUNS += 1
        try:
            self._stream_steps(s)
        finally:
            RUNS -= 1

    def _stream_steps(self, s):
        def emit(obj):
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode())
            self.wfile.flush()

        env = dict(os.environ, PYTHONUNBUFFERED="1")
        env.update({k: str(v) for k, v in (s.get("env") or {}).items() if v})
        ok = True
        try:
            for argv in s["cmd"]:
                emit({"type": "line", "text": "$ " + " ".join(
                    os.path.basename(a) if i == 0 else a for i, a in enumerate(argv))})
                p = subprocess.Popen(argv, cwd=s.get("cwd", ROOT), env=env, text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
                for line in p.stdout:
                    emit({"type": "line", "text": line.rstrip("\n")})
                if p.wait() != 0:
                    ok = False
                    emit({"type": "line", "text": "退出码 %d" % p.returncode})
                    break
            emit({"type": "done", "ok": ok})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                emit({"type": "line", "text": "执行失败：%s: %s" % (type(e).__name__, e)})
                emit({"type": "done", "ok": False})
            except Exception:
                pass
        finally:
            self.close_connection = True

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    if not _can(PY, ("numpy", "PIL")):
        _wp = work_py()
        if _wp and os.path.abspath(_wp) != os.path.abspath(PY):
            print("当前 python 缺 numpy/PIL，改用 %s" % _wp)
            os.execv(_wp, [_wp, os.path.abspath(__file__)] + sys.argv[1:])
    os.makedirs(CACHE, exist_ok=True)
    dp = deps()
    print("workbench  http://127.0.0.1:%d" % PORT)
    print("python     %s" % PY)
    print("dwpose py   %s" % comfy_py())
    print("node       %s" % NODE)
    print("deps       " + "  ".join("%s=%s" % (k, "ok" if v else "缺") for k, v in dp.items()))
    print("workdir    %s" % (DEFAULT_DIR or "（页面里填）"))
    print("hot        %s（改 server.py 自动重启，刷新网页即生效）"
          % ("开" if WATCH else "关（STUDIO_WATCH=0）"))
    if WATCH:
        threading.Thread(target=hot_watch, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

