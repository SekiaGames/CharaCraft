import argparse
import json
import os
import subprocess
import sys

import numpy as np

import editkit
import riggeom
import rigkit

def sample(ch, t, default=0.0):
    if not ch:
        return default
    if t <= ch[0]["time"]:
        return ch[0]["value"] if "value" in ch[0] else ch[0].get("y", 0.0)
    for p, q in zip(ch, ch[1:]):
        if p["time"] <= t <= q["time"]:
            u = 0.0 if q["time"] == p["time"] else (t - p["time"]) / (q["time"] - p["time"])
            v0 = p["value"] if "value" in p else p.get("y", 0.0)
            v1 = q["value"] if "value" in q else q.get("y", 0.0)
            return v0 + (v1 - v0) * u
    last = ch[-1]
    return last["value"] if "value" in last else last.get("y", 0.0)

def sample_key(ch, t, key, default=0.0):
    if not ch:
        return default
    if t <= ch[0]["time"]:
        return ch[0].get(key, default)
    for p, q in zip(ch, ch[1:]):
        if p["time"] <= t <= q["time"]:
            u = 0.0 if q["time"] == p["time"] else (t - p["time"]) / (q["time"] - p["time"])
            return p.get(key, default) + (q.get(key, default) - p.get(key, default)) * u
    return ch[-1].get(key, default)

def world_pose(local, t_bones, t=0.0, hip_dy=0.0, hip=None):
    rot = riggeom.rot
    par = {b["index"]: b.get("parent", -1) for b in local}
    loc = {b["index"]: np.array([b["x"], b["y"]], float) for b in local}
    lrot = {b["index"]: float(b.get("rotation", 0.0)) for b in local}
    pv, wg, sg = {}, {}, {}
    for b in (x["index"] for x in local):
        tl = t_bones.get(b) or {}
        ch = tl.get("rotate")
        sc = tl.get("scale")
        ang = sample(ch, t) if ch else 0.0
        sg[b] = sample(sc, t, 1.0) if sc else 1.0
        p = par[b]
        tr = tl.get("translate")
        if p < 0:
            pv[b] = loc[b].copy()
            if tr:
                pv[b][0] = sample_key(tr, t, "x", loc[b][0])
            wg[b] = lrot[b] + ang
        else:
            base = loc[b] if not tr else np.array([sample_key(tr, t, "x", loc[b][0]),
                                                   sample_key(tr, t, "y", loc[b][1])], float)
            pv[b] = pv[p] + rot(wg[p]) @ (base * sg[p])
            wg[b] = wg[p] + lrot[b] + ang
    if hip_dy and hip and hip in pv:
        pv[hip] = pv[hip] + np.array([0.0, hip_dy])
    return pv, wg, sg

def read_fps(video, fallback=24.0):
    if not video or not os.path.isfile(video):
        return fallback
    probe = os.environ.get("FFPROBE") or "ffprobe"
    out = subprocess.run([probe, "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", video],
                         capture_output=True, text=True, timeout=20)
    s = (out.stdout or "").strip().split("\n")[0]
    if "/" in s:
        a, b = s.split("/")
        return round(float(a) / float(b), 3)
    if s:
        return round(float(s), 3)
    return fallback

def median(v):
    v = sorted(v)
    return v[len(v) // 2]

def wrap180(v):
    return (v + 180.0) % 360.0 - 180.0


def lean_split(rig, role2i):
    by = {b["index"]: b for b in rig["bones"]}
    out = {}
    for main, other in (("body-down", "body-up"), ("head", "neck")):
        a, b = role2i[main], role2i[other]
        la = float(by[a].get("length") or 0)
        lb = float(by[b].get("length") or 0)
        if la + lb > 0:
            out[a] = (b, la / (la + lb))
    return out


def load_calib():
    rig = rigkit.read()
    role2i = rigkit.roles(rig)
    calib = rig.get("calib")
    if not calib:
        sys.exit("%s 里没有 calib —— 先跑 pose-extract + calib-rest --write" % rigkit.SKEL)
    zero = {int(k): v for k, v in calib.items() if k != "near"}
    return role2i, zero

def build_tracks(case, act):
    md = os.path.join(case, "clip-" + act)
    pf = os.path.join(md, "dwpose_bones.json")
    if not os.path.isfile(pf):
        sys.exit("缺 %s —— 先跑「DWPose 骨骼」" % pf)
    src = json.load(open(pf, encoding="utf-8"))
    frames = [{int(k): v for k, v in f["bones"].items()} for f in src["frames"]]
    hips = [f.get("hip") for f in src["frames"]]
    role2i, calib = load_calib()

    kf = editkit.bone_keys(case, act)
    keys = json.load(open(kf, encoding="utf-8")) if os.path.isfile(kf) else {}
    hand = {}
    for k, v in keys.items():
        i = int(k) - 1
        if 0 <= i < len(frames) and v:
            hand[i] = {int(b) for b in v}
            frames[i] = {int(b): {"r": r["r"], "s": r.get("s", 1.0),
                                  "x": r.get("x", 0.0), "y": r.get("y", 0.0)}
                         for b, r in v.items()}

    video = None
    for ext in (".mp4", ".mov", ".webm", ".mkv"):
        p = os.path.join(case, "input", "clip-%s%s" % (act, ext))
        if os.path.isfile(p):
            video = p
            break
    fps = read_fps(video)
    n = len(frames)

    hip_ok = [h[1] for h in hips if h]
    hip_med = median(hip_ok) if hip_ok else 0.0

    loc = {b["index"]: (float(b["x"]), float(b["y"])) for b in rigkit.read()["bones"]}

    tracks = {}

    def put(i, ch, t, v, key="value"):
        cur = tracks.setdefault(str(i), {}).setdefault(ch, [])
        row = {"time": round(t, 4)}
        row[key] = round(float(v), 4)
        cur.append(row)

    def put_xy(i, ch, t, x, y):
        cur = tracks.setdefault(str(i), {}).setdefault(ch, [])
        cur.append({"time": round(t, 4), "x": round(float(x), 4), "y": round(float(y), 4)})

    sheet = editkit.sheet(case, act)
    picked = sheet.get("frames") or []
    idx = [x - 1 for x in picked if 0 < x <= len(frames)] if picked else list(range(len(frames)))
    n_manual = sum(1 for k in keys if int(k) - 1 in set(idx))

    gaps = []
    for gi in range(1, len(idx)):
        dlt = idx[gi] - idx[gi - 1]
        gaps.append(dlt if dlt > 0 else None)
    pos = sorted(g for g in gaps if g)
    step = pos[len(pos) // 2] if pos else 1
    times = [0.0]
    for g in gaps:
        times.append(times[-1] + (g if g else step))
    dur = round((times[-1] + step) / fps, 4) if times and len(idx) > 1 else 0.0

    for ci, i in enumerate(idx):
        t = times[ci] / fps
        fr = frames[i]
        rt = fr.get(role2i["root"]) or {}
        for b, v in fr.items():
            if b in calib:
                put(b, "rotate", t, wrap180(v["r"] - calib[b]))
            put(b, "scale", t, v.get("s", 1.0))
            if b == role2i["root"] or not (v.get("x") or v.get("y")):
                continue
            put_xy(b, "translate", t, loc[b][0] + v.get("x", 0.0), loc[b][1] + v.get("y", 0.0))
        if hips[i]:
            put_xy(role2i["root"], "translate", t,
                   loc[role2i["root"]][0] + rt.get("x", 0.0),
                   hip_med - hips[i][1] + rt.get("y", 0.0))

    if picked and idx:
        for chans in tracks.values():
            for ch, arr in chans.items():
                keys = [k for k in arr[0] if k != "time"]
                first = {k: arr[0][k] for k in keys}
                if arr[-1]["time"] < dur - 1e-6:
                    tail = dict(arr[-1])
                    tail["time"] = dur
                    tail.update(first)
                    arr.append(tail)
                else:
                    arr[-1].update(first)

    if picked:
        print("关键帧模式：%d 个关键帧（共 %d 帧素材）@ %.3f fps → 0~%.3fs，中间由 Spine 插值"
              % (len(idx), n, fps, dur))
    else:
        dur = round((n - 1) / fps, 4) if n > 1 else round(1.0 / fps, 4)
        print("逐帧转换：%d 帧 @ %.3f fps → %.3fs（不回环、不平滑）" % (n, fps, dur))
    if n_manual:
        print("  BoneKeys 覆盖 %d 个关键帧" % n_manual)
    edited = set()
    for ci, i in enumerate(idx):
        for b in hand.get(i, ()):
            edited.add((b, round(times[ci] / fps, 4)))
    n_sc = sum(1 for c in tracks.values() if "scale" in c)
    print("  骨骼 %d 根 · 带缩放轨道 %d 根（长度比 s 一律写成 scale 轨道）" % (len(tracks), n_sc))
    return tracks, dur, edited

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--act", required=True, help="动作名：读 clip-<act>/dwpose_bones.json")
    ap.add_argument("--arm-max", type=float, default=24.0,
                    help="手臂摆幅上限（度）。视频里手被法杖/身体挡，常估出 ±60°，走路实际 ±20°")
    ap.add_argument("--lean-max", type=float, default=9.0,
                    help="躯干前倾上限（度）。帽子/长发会把颈点带偏，视频常估出 20~28°")
    ap.add_argument("--knee-max", type=float, default=58.0,
                    help="膝屈上限（度）。素材是整条腿一张图，弯太狠接缝会露")
    a = ap.parse_args()

    case = a.case.rstrip("/")
    md = os.path.join(case, "clip-" + a.act)
    tracks, dur, edited = build_tracks(case, a.act)

    g = riggeom.load()
    B, R, HIPS = g["B"], g["R"], g["HIPS"]
    print("骨架 %d 根（%s）" % (len(B), g["path"]))

    t_bones = {}
    skipped = []
    for src, tl in tracks.items():
        if int(src) not in B:
            skipped.append(src)
            continue
        tl = dict(tl)
        if "scale" in tl:
            tl["scale"] = [{"time": f["time"], "x": f["value"], "y": f["value"]}
                           for f in tl["scale"]]
        t_bones.setdefault(int(src), {}).update(tl)

    DOWN_LEGS = {R.get("leg-down"), R.get("leg-down-back")}
    ARMS = {R.get(k) for k in ("arm-front-up", "arm-front-down",
                               "arm-back-up", "arm-back-down")}
    n_cl = 0
    for b, tl in t_bones.items():
        if b not in DOWN_LEGS or "rotate" not in tl:
            continue
        for f in tl["rotate"]:
            if (b, f["time"]) in edited:
                continue
            if f["value"] < -a.knee_max:
                f["value"] = -a.knee_max
                n_cl += 1
    if n_cl:
        print("膝角截到 -%.0f°：改了 %d 个关键帧" % (a.knee_max, n_cl))
    n_arm = n_lean = 0
    for b, tl in t_bones.items():
        ch = tl.get("rotate")
        if not ch:
            continue
        if b in ARMS:
            for f in ch:
                if (b, f["time"]) in edited:
                    continue
                v = max(-a.arm_max, min(a.arm_max, f["value"]))
                n_arm += abs(v - f["value"]) > 1e-6
                f["value"] = v
        elif b == R.get("body-down"):
            for f in ch:
                if (b, f["time"]) in edited:
                    continue
                v = max(-a.lean_max, min(a.lean_max, f["value"]))
                n_lean += abs(v - f["value"]) > 1e-6
                f["value"] = v
    if n_arm or n_lean:
        print("截断：手臂 ±%.0f°（改 %d 帧）· 躯干 ±%.0f°（改 %d 帧）"
              % (a.arm_max, n_arm, a.lean_max, n_lean))
    print("接上的轨道：%s" % ", ".join(str(k) for k in sorted(t_bones)))
    if skipped:
        print("丢掉：%s" % ", ".join(sorted(skipped)))

    dur2 = 0.0
    for tl in t_bones.values():
        for ch in tl.values():
            for f in ch:
                dur2 = max(dur2, f["time"])
    if dur2 <= 0:
        sys.exit("轨道里没有关键帧")
    dur = dur2

    rot = riggeom.rot
    pv0, wg0, sg0 = world_pose(g["local"], {}, 0.0, 0.0, HIPS)
    ank = {}
    for role in ("leg-down", "leg-down-back"):
        n = R.get(role)
        if n:
            L = B[n]["len"] * sg0.get(n, 1.0)
            ank[n] = float((pv0[n] + rot(wg0[n]) @ np.array([L, 0.0], float))[1])
    hip_ch = (t_bones.get(HIPS) or {}).get("translate")
    lows = []
    for i in range(48):
        t = (dur * i / 48) if dur else 0.0
        hdy = sample(hip_ch, t) if hip_ch else 0.0
        pv, wg, sg = world_pose(g["local"], t_bones, t, hdy, HIPS)
        for shin, an_y in ank.items():
            L = B[shin]["len"] * sg.get(shin, 1.0)
            end = pv[shin] + rot(wg[shin]) @ np.array([L, 0.0], float)
            lows.append(end[1] - an_y)
    if lows:
        C = float(np.min(lows))
        if abs(C) > 0.5 and hip_ch:
            for f in hip_ch:
                f["y"] = f.get("y", 0.0) - C
            print("接地：最低鞋底偏了 %.1f px，hip 整体%+0.1f" % (C, -C))
        elif abs(C) <= 0.5:
            print("接地：已经贴地（偏差 %.1f px）" % C)

    split = lean_split(rigkit.read(), R)
    for main, (other, k) in split.items():
        ch = (t_bones.get(main) or {}).get("rotate")
        if not ch:
            continue
        mate = [{"time": f["time"], "value": round(f["value"] * (1.0 - k), 4)} for f in ch]
        for f in ch:
            f["value"] = round(f["value"] * k, 4)
        t_bones.setdefault(other, {})["rotate"] = mate

    for tl in t_bones.values():
        for ch in tl.values():
            if ch and ch[-1]["time"] < dur - 1e-6:
                last = dict(ch[0])
                last["time"] = round(dur, 4)
                ch.append(last)

    anims = {a.act: {"bones": {str(k): v for k, v in t_bones.items()}}}
    jout = os.path.join(md, "animations.json")
    json.dump(anims, open(jout, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写入 %s：动画 %s %.3fs · %d 根骨骼有轨道（骨骼/槽位在「皮肤片段」里）"
          % (jout, a.act, dur, len(t_bones)))

if __name__ == "__main__":
    main()
