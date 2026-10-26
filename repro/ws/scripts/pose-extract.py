import glob
import hashlib
import json
import math
import os
import sys

import numpy as np
from PIL import Image

COMFY = os.environ.get("COMFYUI_DIR", "ComfyUI")
AUX = os.path.join(COMFY, "custom_nodes/comfyui_controlnet_aux/src")
sys.path.insert(0, AUX)

NOSE, NECK, RSH, REL, RWR, LSH, LEL, LWR = 0, 1, 2, 3, 4, 5, 6, 7
RHIP, RKNE, RANK, LHIP, LKNE, LANK = 8, 9, 10, 11, 12, 13
LHAND, RHAND, LTOE, RTOE = 14, 15, 16, 17

NEAR_L = (LSH, LEL, LWR, LHIP, LKNE, LANK, LHAND, LTOE)
FAR_L = (RSH, REL, RWR, RHIP, RKNE, RANK, RHAND, RTOE)
LEG_ROLES = ("leg-up", "leg-down")


def ws_path(name):
    ws = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(os.path.dirname(ws), "config", name)


def rig_info():
    rig = json.load(open(ws_path("skeleton.json"), encoding="utf-8"))
    role2i = {b["role"]: b["index"] for b in rig["bones"] if b.get("role")}
    length = {}
    for b in rig["bones"]:
        length[b["index"]] = float(b.get("length") or 0) or math.hypot(
            float(b.get("x") or 0), float(b.get("y") or 0))
    parent = {b["index"]: (-1 if b.get("parent") is None else int(b["parent"]))
              for b in rig["bones"]}
    return role2i, rig["calib"], length, parent, [b["index"] for b in rig["bones"]]


def vec(kp, i):
    k = kp[i]
    return None if k is None else (k[0], k[1])


def down_angle(a, b):
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))


def wrap180(v):
    return (v + 180.0) % 360.0 - 180.0


def seg(kp, a, b):
    p, q = vec(kp, a), vec(kp, b)
    if p is None or q is None:
        return None
    return down_angle(p, q) - 90.0, math.hypot(q[0] - p[0], q[1] - p[1])


def chain(kp, root, mid, end, bend):
    r, m = vec(kp, root), vec(kp, mid)
    if r is None or m is None:
        return None
    e = vec(kp, end)
    if e is None:
        e = (m[0] + (m[0] - r[0]), m[1] + (m[1] - r[1]))
    up = down_angle(r, m)
    rel = wrap180(down_angle(m, e) - up)
    if bend * rel < -10:
        return None
    return up, rel, math.hypot(m[0] - r[0], m[1] - r[1]), math.hypot(e[0] - m[0], e[1] - m[1])


def frame_bones(kp, near_is_l, role2i, parent):
    near = NEAR_L if near_is_l else FAR_L
    far = FAR_L if near_is_l else NEAR_L
    out = {}
    for side, ch in (("front", near), ("back", far)):
        lg = chain(kp, ch[3], ch[4], ch[5], -1)
        if lg:
            up = lg[0] - 90.0
            out[role2i["leg-up" if side == "front" else "leg-up-back"]] = (up, lg[2])
            out[role2i["leg-down" if side == "front" else "leg-down-back"]] = (up + lg[1], lg[3])
        ac = chain(kp, ch[0], ch[1], ch[2], +1)
        if ac:
            up = ac[0] - 90.0
            out[role2i["arm-%s-up" % side]] = (up, ac[2])
            out[role2i["arm-%s-down" % side]] = (up + ac[1], ac[3])
        for role, pair in (("hand-%s" % side, (ch[2], ch[6])), ("foot-%s" % side, (ch[5], ch[7]))):
            sv = seg(kp, pair[0], pair[1])
            if sv:
                out[role2i[role]] = sv
    hd = seg(kp, NECK, NOSE)
    if hd:
        out[role2i["head"]] = hd
    hp, lh = vec(kp, RHIP), vec(kp, LHIP)
    nk = vec(kp, NECK)
    if hp and lh and nk:
        mx, my = (hp[0] + lh[0]) / 2.0, (hp[1] + lh[1]) / 2.0
        out[role2i["body-down"]] = (-math.degrees(math.atan2(nk[0] - mx, -(nk[1] - my))),
                                    math.hypot(nk[0] - mx, nk[1] - my))
    loc = {}
    for i, (w, ln) in out.items():
        p = parent[i]
        pw = out[p][0] if p in out else 0.0
        loc[i] = (wrap180(w - pw), ln)
    return loc


def read_body(best):
    return [None if k is None else [k.x, k.y, k.score] for k in best.body.keypoints]


def fill_ext(kp, best):
    for hand, i in ((best.left_hand, LHAND), (best.right_hand, RHAND)):
        if hand and hand[12] is not None:
            kp[i] = [hand[12].x, hand[12].y, hand[12].score]
    legs = []
    for hip, knee, ankle in ((RHIP, RKNE, RANK), (LHIP, LKNE, LANK)):
        if kp[hip] and kp[knee] and kp[ankle]:
            legs.append(math.hypot(kp[knee][0] - kp[hip][0], kp[knee][1] - kp[hip][1])
                        + math.hypot(kp[ankle][0] - kp[knee][0], kp[ankle][1] - kp[knee][1]))
    if not legs:
        return
    L = sum(legs) / len(legs)
    for ankle, i in ((LANK, LTOE), (RANK, RTOE)):
        if kp[ankle]:
            kp[i] = [kp[ankle][0] + 0.16 * L, kp[ankle][1], kp[ankle][2]]


def hip_mid(kp):
    hp, lh = vec(kp, RHIP), vec(kp, LHIP)
    return None if hp is None or lh is None else ((hp[0] + lh[0]) / 2.0, (hp[1] + lh[1]) / 2.0)


def leg_px(kp):
    hp, kn, an = vec(kp, RHIP), vec(kp, RKNE), vec(kp, RANK)
    if None in (hp, kn, an):
        hp, kn, an = vec(kp, LHIP), vec(kp, LKNE), vec(kp, LANK)
    if None in (hp, kn, an):
        return None
    return math.hypot(kn[0] - hp[0], kn[1] - hp[1]) + math.hypot(an[0] - kn[0], an[1] - kn[1])


def median(v):
    v = sorted(v)
    return v[len(v) // 2]


def frames_sha1(paths):
    h = hashlib.sha1()
    for p in paths:
        h.update(os.path.basename(p).encode())
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def rig_sha1(role2i, calib, length):
    bits = {"near": calib.get("near"),
            "roles": role2i,
            "leg": [length[role2i[r]] for r in LEG_ROLES]}
    return hashlib.sha1(json.dumps(bits, sort_keys=True).encode()).hexdigest()


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(args) < 2:
        sys.exit("用法：pose-extract.py <图片 glob> <输出 .json>")
    pattern, out = args[0], args[1]
    force = "--force" in sys.argv
    paths = sorted(glob.glob(pattern))
    if not paths:
        sys.exit("没有帧：%s —— 先跑「抽帧」" % pattern)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    role2i, calib, length, parent, order = rig_info()

    mark = os.path.join(os.path.dirname(os.path.abspath(out)), "dwpose_sha1_mark.json")
    cur = {"frames": len(paths), "sha1": frames_sha1(paths),
           "rig": rig_sha1(role2i, calib, length)}
    prev = json.load(open(mark, encoding="utf-8")) if os.path.isfile(mark) else None
    if not force and os.path.isfile(out) and prev and all(prev.get(k) == cur[k] for k in cur):
        print("%d 帧和骨架都没变（sha1 %s），%s 还能用，跳过检测"
              % (len(paths), cur["sha1"][:8], os.path.basename(out)))
        return

    from custom_controlnet_aux.dwpose import DwposeDetector

    near_is_l = calib["near"] == "L"

    det = DwposeDetector.from_pretrained("yzd-v/DWPose", "yzd-v/DWPose", det_filename="yolox_l.onnx",
                                         pose_filename="dw-ll_ucoco_384.onnx", torchscript_device="cuda")
    raw = []
    for f in paths:
        src = Image.open(f)
        if src.mode == "RGBA" and (np.array(src)[..., 3] < 128).mean() > 0.05:
            bg = Image.new("RGBA", src.size, (255, 255, 255, 255))
            bg.alpha_composite(src)
            im = bg.convert("RGB")
        else:
            im = src.convert("RGB")
        w, h = im.size
        kp, n_people = [None] * 18, 0
        poses = det.detect_poses(np.array(im))
        if poses:
            n_people = len(poses)
            best = max(poses, key=lambda p: p.body.total_score)
            kp = read_body(best)
            fill_ext(kp, best)
        raw.append({"file": os.path.basename(f), "size": [w, h], "n_people": n_people,
                    "kp": kp, "hip": hip_mid(kp),
                    "bones": frame_bones(kp, near_is_l, role2i, parent)})
        print("%s people=%d bones=%d/%d" % (os.path.basename(f), n_people,
                                           len(raw[-1]["bones"]), len(order)))

    legs = [leg_px(x["kp"]) for x in raw]
    leg_med = median([x for x in legs if x])
    rig_leg = sum(length[role2i[r]] for r in LEG_ROLES)
    scale = rig_leg / leg_med

    per_bone = {}
    for x in raw:
        for i, (ang, ln) in x["bones"].items():
            per_bone.setdefault(i, []).append(ln)
    base_len = {i: median(v) for i, v in per_bone.items()}

    frames = []
    for x in raw:
        bones = {}
        for i in order:
            if i in x["bones"]:
                ang, ln = x["bones"][i]
                bones[i] = {"r": round(ang, 3), "s": round(ln / base_len[i], 4)}
            elif str(i) not in calib:
                bones[i] = {"r": 0.0, "s": 1.0}
        hip = x["hip"]
        frames.append({"file": x["file"], "size": x["size"],
                       "hip": None if hip is None else [round(hip[0] * scale, 2),
                                                        round(hip[1] * scale, 2)],
                       "bones": bones})

    with open(out, "w") as fp:
        json.dump({"size": frames[0]["size"], "scale": round(scale, 4), "frames": frames}, fp)
    json.dump(cur, open(mark, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n%d 帧 · 视频腿长 %.1f px · scale %.4f · 输出 %s" % (len(frames), leg_med, scale, out))


if __name__ == "__main__":
    main()
