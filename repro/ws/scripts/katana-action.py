import math

import numpy as np
from scipy.interpolate import PchipInterpolator

FPS = 30
DUR = 2.4
TURN = (0.62, 0.74)
SWEEP = 0.16

K = {
    "hip_x":   [(0, 0), (0.35, 15), (0.5, 35), (0.6, 15), (0.68, 0), (1.05, 0), (1.26, 40), (1.46, 70), (1.65, 75), (2.4, 75)],
    "air":     [(0, 0), (1.08, 0), (1.17, 90), (1.26, 135), (1.36, 95), (1.46, 0), (2.4, 0)],
    "torso":   [(0, -18), (0.35, -22), (0.5, -28), (0.62, -8), (0.8, 6), (0.95, -12), (1.1, -4), (1.26, -12),
                (1.38, -18), (1.48, -25), (1.65, -32), (1.85, -30), (2.3, -2), (2.4, 0)],
    "head":    [(0, 12), (0.5, 20), (0.62, 5), (0.8, -4), (0.95, 8), (1.26, 8), (1.48, 15), (1.65, 22),
                (1.85, 20), (2.3, 0), (2.4, 0)],
    "n_thigh": [(0, 28), (0.35, 45), (0.5, 55), (0.62, 20), (0.8, 5), (0.95, 40), (1.1, 5), (1.26, 75),
                (1.38, 55), (1.48, 45), (1.65, 70), (1.85, 68), (2.3, 30), (2.4, 30)],
    "n_shin":  [(0, -50), (0.35, -55), (0.5, -60), (0.62, -25), (0.8, -5), (0.95, -75), (1.1, -5), (1.26, -110),
                (1.38, -60), (1.48, -45), (1.65, -100), (1.85, -98), (2.3, -40), (2.4, -40)],
    "f_thigh": [(0, -8), (0.35, -20), (0.5, -30), (0.62, -10), (0.8, -5), (0.95, 25), (1.1, -10), (1.26, 45),
                (1.38, 10), (1.48, -15), (1.65, -35), (1.85, -35), (2.3, -15), (2.4, -15)],
    "f_shin":  [(0, -30), (0.35, -15), (0.5, -10), (0.62, -20), (0.8, -10), (0.95, -65), (1.1, -10), (1.26, -100),
                (1.38, -60), (1.48, -40), (1.65, -80), (1.85, -80), (2.3, -25), (2.4, -25)],
    "n_upper": [(0, 100), (0.5, 100), (0.62, 150), (0.8, 160), (0.95, 155), (1.1, 158), (1.26, 165),
                (1.38, 120), (1.48, 65), (1.65, 40), (1.85, 42), (2.3, 172), (2.4, 172)],
    "n_lower": [(0, 5), (0.5, 5), (0.62, 40), (0.8, 75), (0.95, 75), (1.1, 75), (1.26, 85), (1.38, 25),
                (1.48, 5), (1.65, 8), (1.85, 8), (2.3, 15), (2.4, 15)],
    "wrist":   [(0, 12), (0.5, 12), (0.62, 57), (0.8, 73), (0.95, 73), (1.1, 75), (1.26, 101), (1.38, 22),
                (1.48, 34), (1.65, 28), (1.85, 28), (2.3, -1), (2.4, -1)],
    "f_upper": [(0, 10), (0.45, -20), (0.55, -40), (0.68, 60), (2.4, 60)],
    "f_lower": [(0, 20), (0.55, 25), (0.68, 60), (2.4, 60)],
    "saya":    [(0, 1), (0.42, 1), (0.56, 0), (2.4, 0)],
    "two_hand": [(0, 0), (0.6, 0), (0.76, 1), (2.4, 1)],
    "slide":   [(0, 0), (0.1, 0), (0.3, 160), (0.45, 330), (2.4, 330)],
    "pull":    [(0, 0), (0.1, 0), (0.3, 80), (0.45, 140), (0.6, 100), (0.85, 0), (2.4, 0)],
    "sc_rot":  [(0, 0), (0.3, -4), (0.45, -8), (0.6, -4), (0.85, 0), (2.4, 0)],
}

def curve(keys):
    t, v = np.array(keys, float).T
    return PchipInterpolator(t, v) if len(t) > 2 else (lambda x: np.interp(x, t, v))

def rot(v, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (c * v[0] - s * v[1], s * v[0] + c * v[1])

def add(a, b):
    return (a[0] + b[0], a[1] + b[1])

def ik2(S, T, e, f, parent_deg):
    L1, L2 = math.hypot(*e), math.hypot(*f)
    ae, af = math.degrees(math.atan2(e[1], e[0])), math.degrees(math.atan2(f[1], f[0]))
    d = (T[0] - S[0], T[1] - S[1])
    D = min(max(math.hypot(*d), abs(L1 - L2) + 1e-3), L1 + L2 - 1e-3)
    beta = math.pi - math.acos((L1 * L1 + L2 * L2 - D * D) / (2 * L1 * L2))
    psi1 = math.atan2(d[1], d[0]) - math.atan2(L2 * math.sin(beta), L1 + L2 * math.cos(beta))
    up_w = math.degrees(psi1) - ae
    lo_rel = math.degrees(psi1 + beta) - af - up_w
    el = add(S, rot(e, up_w))
    hand = add(el, rot(f, up_w + lo_rel))
    return up_w - parent_deg, lo_rel, math.hypot(hand[0] - T[0], hand[1] - T[1])

def build(ctx):
    bones = {b["name"]: b for b in ctx["bones"]}
    order = [b["name"] for b in ctx["bones"]]
    W = ctx["weapon"]
    SHEATH = ctx["sheath"]
    FIST = ctx["fist"]
    E_N = (bones["near-lower-arm"]["x"], bones["near-lower-arm"]["y"])
    E_F = (bones["far-lower-arm"]["x"], bones["far-lower-arm"]["y"])
    contacts = ctx["foot_points"]

    C = {k: curve(v) for k, v in K.items()}
    n = int(round(DUR * FPS))
    ts = np.arange(n + 1) / FPS

    def fk(vals):
        Wd = {}
        for name in order:
            b = bones[name]
            v = vals.get(name, {})
            lx, ly = b["x"] + v.get("x", 0.0), b["y"] + v.get("y", 0.0)
            r = v.get("rotate", 0.0)
            if "parent" in b:
                px, py, pr = Wd[b["parent"]]
                ox, oy = rot((lx, ly), pr)
                Wd[name] = (px + ox, py + oy, pr + r)
            else:
                Wd[name] = (lx, ly, r)
        return Wd

    rows, diag = [], {"ik_near_max_px": 0.0, "ik_far_max_px": 0.0}
    t_exit, phi_gap = None, 0.0
    near_ik_last = None
    for t in ts:
        c = {k: float(f(t)) for k, f in C.items()}
        vals = {
            "hip": {"x": c["hip_x"], "y": 0.0},
            "torso": {"rotate": c["torso"]}, "head": {"rotate": c["head"]},
            "near-upper-leg": {"rotate": c["n_thigh"]}, "near-lower-leg": {"rotate": c["n_shin"]},
            "far-upper-leg": {"rotate": c["f_thigh"]}, "far-lower-leg": {"rotate": c["f_shin"]},
            "near-upper-arm": {"rotate": c["n_upper"]}, "near-lower-arm": {"rotate": c["n_lower"]},
            "far-upper-arm": {"rotate": c["f_upper"]}, "far-lower-arm": {"rotate": c["f_lower"]},
        }
        Wd = fk(vals)
        low = min(add(Wd[f"{s}-lower-leg"][:2], rot(p, Wd[f"{s}-lower-leg"][2]))[1]
                  for s in ("near", "far") for p in contacts)
        vals["hip"]["y"] = -low + c["air"]
        Wd = fk(vals)
        hip = Wd["hip"]
        u_rest = rot((1.0, 0.0), SHEATH)
        sc_ang = SHEATH + c["sc_rot"]
        sc_tr = (u_rest[0] * c["pull"], u_rest[1] * c["pull"])
        M = add(add(hip[:2], (bones["scabbard"]["x"], bones["scabbard"]["y"])), sc_tr)
        drawn = c["slide"] >= W["blade_len"]
        if not drawn:
            ml = (W["mouth"][0] + c["slide"], W["mouth"][1])
            off = rot(ml, sc_ang)
            G = (M[0] - off[0], M[1] - off[1])
            S = Wd["near-upper-arm"][:2]
            u, l, res = ik2(S, G, E_N, FIST, Wd["torso"][2])
            diag["ik_near_max_px"] = max(diag["ik_near_max_px"], res)
            vals["near-upper-arm"]["rotate"], vals["near-lower-arm"]["rotate"] = u, l
            near_ik_last = (u, l)
            phi = sc_ang
        else:
            if t_exit is None:
                t_exit = t
            bl = min(1.0, (t - t_exit) / 0.1)
            bl = bl * bl * (3 - 2 * bl)
            vals["near-upper-arm"]["rotate"] = near_ik_last[0] + (c["n_upper"] - near_ik_last[0]) * bl
            vals["near-lower-arm"]["rotate"] = near_ik_last[1] + (c["n_lower"] - near_ik_last[1]) * bl
        Wd = fk(vals)
        fore = Wd["near-lower-arm"]
        hand = add(fore[:2], rot(FIST, fore[2]))
        af = math.degrees(math.atan2(FIST[1], FIST[0]))
        phi_hand = fore[2] + af + c["wrist"]
        sw_sx = 1.0
        if drawn:
            if abs(t - t_exit) < 1e-9:
                phi_gap = rows[-1]["phi"] - phi_hand if rows else 0.0
            us = (t - t_exit) / SWEEP
            phi = phi_hand + (phi_gap if us < 0.5 else 0.0)
            if us < 1:
                sw_sx = max(0.1, abs(1 - 2 * us))
            G = hand
        Sf = Wd["far-upper-arm"][:2]
        fu, fl = c["f_upper"], c["f_lower"]
        if c["saya"] > 1e-3:
            Tm = add(M, rot((14.0, 0.0), sc_ang))
            u, l, res = ik2(Sf, Tm, E_F, FIST, Wd["torso"][2])
            fu, fl = fu + (u - fu) * c["saya"], fl + (l - fl) * c["saya"]
            if c["saya"] > 0.99:
                diag["ik_far_max_px"] = max(diag["ik_far_max_px"], res)
        if c["two_hand"] > 1e-3:
            Tg = add(G, rot(W["far_grip"], phi))
            u, l, res = ik2(Sf, Tg, E_F, FIST, Wd["torso"][2])
            u = fu + ((u - fu + 180) % 360 - 180)
            fu, fl = fu + (u - fu) * c["two_hand"], fl + (l - fl) * c["two_hand"]
            if c["two_hand"] > 0.99:
                diag["ik_far_max_px"] = max(diag["ik_far_max_px"], res)
                if res > 3:
                    diag.setdefault("far_unreached", []).append((round(float(t), 2), round(res, 1)))
        vals["far-upper-arm"]["rotate"], vals["far-lower-arm"]["rotate"] = fu, fl
        tip_y = add(G, rot(W["tip"], phi))[1]
        if tip_y < -2:
            diag.setdefault("tip_below_ground", []).append((round(float(t), 2), round(tip_y, 1)))
        sw_local = (G[0] - hip[0] - bones["sword"]["x"], G[1] - hip[1] - bones["sword"]["y"])
        rs = float(np.interp(t, [0, TURN[0], TURN[1], DUR], [1, 1, -1, -1]))
        rows.append({"t": t, "vals": vals, "phi": phi, "sw": sw_local, "sc_rot": sc_ang, "sc_tr": sc_tr, "rs": rs,
                     "sw_sx": sw_sx})

    phis = np.degrees(np.unwrap(np.radians([r["phi"] for r in rows])))
    tl = {}

    def key(bone, ch, t, **v):
        tl.setdefault(bone, {}).setdefault(ch, []).append({"time": round(float(t), 4), **{k: round(float(x), 3) for k, x in v.items()}})

    for r, ph in zip(rows, phis):
        t = r["t"]
        for b, v in r["vals"].items():
            if "rotate" in v:
                key(b, "rotate", t, value=v["rotate"])
            if b == "hip":
                key(b, "translate", t, x=v["x"], y=v["y"])
        key("sword", "rotate", t, value=ph)
        key("sword", "translate", t, x=r["sw"][0], y=r["sw"][1])
        key("sword", "scale", t, x=r["sw_sx"], y=1.0)
        key("scabbard", "rotate", t, value=r["sc_rot"])
        key("scabbard", "translate", t, x=r["sc_tr"][0], y=r["sc_tr"][1])
        key("root", "scale", t, x=r["rs"], y=1.0)
    names = [s["name"] for s in ctx["slots"]]
    s_idx = names.index("sword")
    b_idx = names.index("bodice" if "bodice" in names else "body")
    dro, prev = [], None
    for r, ph in zip(rows, phis):
        front = r["t"] >= (t_exit if t_exit is not None else 1e9) and math.cos(math.radians(ph)) >= -0.25
        if front != prev:
            dro.append({"time": round(float(r["t"]), 4),
                        **({"offsets": [{"slot": "sword", "offset": b_idx - s_idx}]} if front else {})})
            prev = front
    diag.update({"sword_front": [d["time"] for d in dro if "offsets" in d]})
    diag.update({"t_exit": None if t_exit is None else round(float(t_exit), 3), "frames": len(rows),
                 "ik_near_max_px": round(diag["ik_near_max_px"], 1), "ik_far_max_px": round(diag["ik_far_max_px"], 1)})
    return {"katana_attack": {"bones": tl, "drawOrder": dro}}, diag
