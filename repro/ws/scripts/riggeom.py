import os
import sys

import numpy as np

import rigkit

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
CONFIG = rigkit.CONFIG

if HERE not in sys.path:
    sys.path.insert(0, HERE)

def rot(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]], float)

def load():
    rig = rigkit.read()
    if not rig.get("bones"):
        raise SystemExit("骨架是空的：%s" % rigkit.SKEL)
    if not rig.get("ground"):
        raise SystemExit("骨架缺 ground（脚底基准）：%s" % rigkit.SKEL)
    if not rig.get("calib"):
        raise SystemExit("骨架缺 calib（动补零点）：%s" % rigkit.SKEL)

    ground = float(rig["ground"])

    def spine(p):
        return np.array([p[0], ground - p[1]], float)

    W = rigkit.world(rig)
    B = {}
    for b in W:
        B[b["index"]] = {"pos": spine((b["x"], b["y"])),
                         "parent": b["parent"],
                         "abs": float(b["rotation"]),
                         "len": float(b["length"]),
                         "role": b["role"],
                         "side": b["side"]}

    R = rigkit.roles(rig)
    missing = [k for k in ("root", "body-down", "body-up", "head",
                           "arm-front-up", "arm-front-down", "leg-up", "leg-down")
               if k not in R]
    if missing:
        raise SystemExit("骨架缺关键骨骼（role）：%s —— 去「骨架」页补上 role" % ", ".join(missing))

    local, bones = [], []
    for b in W:
        i, par = b["index"], b["parent"]
        if par >= 0:
            d = rot(-B[par]["abs"]) @ (B[i]["pos"] - B[par]["pos"])
            row = {"index": i, "parent": par,
                   "x": round(float(d[0]), 2), "y": round(float(d[1]), 2),
                   "rotation": round(B[i]["abs"] - B[par]["abs"], 2)}
        else:
            row = {"index": i, "parent": -1,
                   "x": round(float(B[i]["pos"][0]), 2), "y": round(float(B[i]["pos"][1]), 2),
                   "rotation": round(float(B[i]["abs"]), 2)}
        if b["length"]:
            row["length"] = round(float(b["length"]), 2)
        local.append(row)

        sk = {"name": str(i)}
        if par >= 0:
            sk["parent"] = str(par)
        sk["x"] = row["x"]
        sk["y"] = row["y"]
        sk["rotation"] = row["rotation"]
        if row.get("length"):
            sk["length"] = row["length"]
        bones.append(sk)

    return {"rig": rig, "path": rigkit.SKEL, "ground": ground, "spine": spine,
            "B": B, "R": R, "HIPS": R["root"], "bones": bones, "local": local,
            "order": [b["index"] for b in W]}
