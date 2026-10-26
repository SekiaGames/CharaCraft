#!/usr/bin/env python3
import argparse
import json
import math
import os

import editkit


def wrap(v):
    return (v + 180.0) % 360.0 - 180.0


def load_rig():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "config", "skeleton.json")
    rig = json.load(open(p, encoding="utf-8"))
    role2i = {b["role"]: b["index"] for b in rig["bones"] if b.get("role")}
    length = {}
    for b in rig["bones"]:
        length[b["index"]] = float(b.get("length") or 0) or math.hypot(
            float(b.get("x") or 0), float(b.get("y") or 0))
    return role2i, length


def feat(frame, role2i):
    bones = frame.get("bones") or {}
    out = []
    for up, dn in (("leg-up-back", "leg-down-back"), ("leg-up", "leg-down"),
                   ("arm-back-up", "arm-back-down"), ("arm-front-up", "arm-front-down")):
        u = (bones.get(role2i[up]) or {}).get("r")
        d = (bones.get(role2i[dn]) or {}).get("r")
        out.append(u)
        out.append(d if u is not None and d is not None else None)
    bd = (bones.get(role2i["body-down"]) or {}).get("r")
    out.append(bd)
    hip = frame.get("hip")
    out.append(-hip[1] * 0.25 if hip else None)
    return out


def foot_lift(frame, role2i, length):
    hip = frame.get("hip")
    if not hip:
        return None
    ys = []
    for up, dn in (("leg-up", "leg-down"), ("leg-up-back", "leg-down-back")):
        u = (frame["bones"].get(role2i[up]) or {}).get("r")
        d = (frame["bones"].get(role2i[dn]) or {}).get("r")
        if u is None or d is None:
            continue
        ys.append(hip[1] + length[role2i[up]] * math.sin(math.radians(u))
                  + length[role2i[dn]] * math.sin(math.radians(u + d)))
    if len(ys) < 2:
        return None
    return hip[1] - min(ys)


def phase_curve(M, T, K):
    C = len(M[0])
    acc = [[0.0] * C for _ in range(K)]
    cnt = [[0.0] * C for _ in range(K)]
    for i, row in enumerate(M):
        p = (i % T) / T * K
        a = int(math.floor(p)) % K
        b = (a + 1) % K
        u = p - math.floor(p)
        for c in range(C):
            if row[c] is None:
                continue
            acc[a][c] += row[c] * (1 - u)
            cnt[a][c] += 1 - u
            acc[b][c] += row[c] * u
            cnt[b][c] += u
    return [[acc[i][c] / cnt[i][c] if cnt[i][c] > 1e-9 else None for c in range(C)]
            for i in range(K)]


def phase_error(M, U, T, K):
    dev = []
    for i, row in enumerate(M):
        g = int(round((i % T) / T * K)) % K
        for c in range(len(row)):
            if row[c] is None or U[g][c] is None:
                continue
            dev.append(abs(wrap(row[c] - U[g][c])))
    dev.sort()
    return dev[len(dev) // 2] if dev else 0.0


def phase_span(U):
    span = []
    for c in range(len(U[0])):
        col = [r[c] for r in U if r[c] is not None]
        if col:
            span.append(max(col) - min(col))
    span.sort()
    return span[len(span) // 2] if span else 0.0


def best_period(M, lo, hi):
    rows = []
    T = lo
    while T <= hi:
        K = int(round(T))
        U = phase_curve(M, T, K)
        rows.append((T, phase_error(M, U, T, K), K, phase_span(U), U))
        T = round(T + 0.05, 4)
    lo_r = min(r[1] for r in rows)
    amp = max(r[3] for r in rows)
    for row in rows:
        if row[3] >= amp * 0.6 and row[1] <= lo_r * 1.5:
            return row
    return rows[0]


def phase_lift(frames, T, K, role2i, length):
    acc = [0.0] * K
    cnt = [0] * K
    for i, p in enumerate(frames):
        v = foot_lift(p, role2i, length)
        if v is None:
            continue
        g = int(round((i % T) / T * K)) % K
        acc[g] += v
        cnt[g] += 1
    return [acc[g] / cnt[g] if cnt[g] else None for g in range(K)]


def phase_dev(M, U, T, K):
    out = []
    for i, row in enumerate(M):
        g = int(round((i % T) / T * K)) % K
        d = [abs(wrap(row[c] - U[g][c])) for c in range(len(row))
             if row[c] is not None and U[g][c] is not None]
        out.append(sum(d) / len(d) if d else None)
    return out


def pick_first(frames, M, U, T, K, role2i, length):
    pm = phase_lift(frames, T, K, role2i, length)
    sm = []
    for g in range(K):
        nb = [pm[(g + d) % K] for d in (-1, 0, 1)]
        nb = [v for v in nb if v is not None]
        sm.append(sum(nb) / len(nb) if nb else None)
    best = max(v for v in sm if v is not None)
    g = min(i for i in range(K) if sm[i] is not None and sm[i] >= best - 8.0)

    dev = phase_dev(M, U, T, K)
    pick = None
    for i in range(len(frames) - K):
        if int(round((i % T) / T * K)) % K != g:
            continue
        seg = dev[i:i + K + 1]
        if any(v is None for v in seg):
            continue
        cost = sum(seg) / len(seg)
        if pick is None or cost < pick[0]:
            pick = (cost, i)
    if pick is None:
        return 0, 0.0, 0.0
    return pick[1], pm[g], pick[0]


def jump_stats(M):
    out = []
    for c in (1, 3):
        seq = [r[c] for r in M]
        for i in range(1, len(seq)):
            if seq[i] is None or seq[i - 1] is None:
                continue
            out.append(abs(wrap(seq[i] - seq[i - 1])))
    out.sort()
    if not out:
        return (0.0, 0.0)
    return (out[len(out) // 2], out[int(len(out) * 0.9)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--act", required=True)
    ap.add_argument("--step", type=int, default=0)
    ap.add_argument("--min-span", type=float, default=10.0)
    ap.add_argument("--only-if-auto", action="store_true",
                    help="已经有手动挑帧记录就跳过（链上用）")
    a = ap.parse_args()

    md = os.path.join(a.case, "clip-" + a.act)
    edit = editkit.frame_sheet(a.case, a.act)
    if a.only_if_auto and os.path.isfile(edit):
        have = json.load(open(edit, encoding="utf-8"))
        print("%s 有手动挑帧记录（%d 帧），跳过自动挑帧"
              % (a.act, len(have.get("frames") or [])))
        return
    kf = editkit.picked(a.case, a.act)
    role2i, length = load_rig()
    frames_src = json.load(open(os.path.join(md, "dwpose_bones.json"), encoding="utf-8"))["frames"]
    for f in frames_src:
        f["bones"] = {int(k): v for k, v in f["bones"].items()}
    n = len(frames_src)
    M = [feat(p, role2i) for p in frames_src]
    jm, j90 = jump_stats(M)

    T, err, K, span, U = best_period(M, max(6.0, n * 0.06), n * 0.28)
    looped = span >= a.min_span and K >= 6
    if not looped:
        K = 8
        T = float(K)
        U = phase_curve(M, T, K)
        span = phase_span(U)

    i0, lift_v, fit = pick_first(frames_src, M, U, T, K, role2i, length)
    step = a.step if a.step > 0 else max(1, int(round(K / 12.0)))
    frames = []
    for p in range(0, K, step):
        f = i0 + int(round(p * T / K))
        if not frames or f > frames[-1]:
            frames.append(f)

    json.dump({"frames": [f + 1 for f in frames]},
              open(kf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("素材 %d 帧" % n)
    if looped:
        print("周期 %.2f 帧（%d 个相位格）· 折叠残差 %.1f° · 相位幅度中位 %.0f°"
              "（还要求折叠后幅度不低于全段最大的 60%% —— 半周期会把左右步折叠在一起、幅度塌一半）"
              % (T, K, err, span))
    else:
        print("相位幅度只有 %.0f°（< %.0f°）→ 按静止处理：%d 帧循环"
              % (span, a.min_span, K))
    print("首帧 = 第 %d 帧（该相位平均抬脚 %.0f px；这一周期与相位模板的平均偏差 %.1f°，全段里最小的，"
          "所以跳过片头站姿/片尾收势）" % (i0 + 1, lift_v, fit))
    print("关键帧 %d 个，步长 %d：" % (len(frames), step))
    print("  " + " ".join(str(f + 1) for f in frames))
    print("逐帧膝角跳变 中位 %.1f° / 90%% %.1f° —— 单帧不可信，所以按相位等分挑，不按残差挑"
          % (jm, j90))


if __name__ == "__main__":
    main()
