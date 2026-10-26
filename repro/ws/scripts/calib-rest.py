import argparse
import importlib.util
import json
import os
import sys

NOSE, NECK, RSH, REL, RWR, LSH, LEL, LWR = 0, 1, 2, 3, 4, 5, 6, 7
RHIP, RKNE, RANK, LHIP, LKNE, LANK = 8, 9, 10, 11, 12, 13
LHAND, RHAND, LTOE, RTOE = 14, 15, 16, 17


def _load(name):
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"),
                                                  os.path.join(here, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def calib_from(kp, p2f):
    ls = (kp[LSH] or [0])[0] + (kp[LHIP] or [0])[0]
    rs = (kp[RSH] or [0])[0] + (kp[RHIP] or [0])[0]
    near_l = ls >= rs
    near = ((LSH, LEL, LWR, LHIP, LKNE, LANK, LHAND, LTOE) if near_l
            else (RSH, REL, RWR, RHIP, RKNE, RANK, RHAND, RTOE))
    far = ((RSH, REL, RWR, RHIP, RKNE, RANK, RHAND, RTOE) if near_l
           else (LSH, LEL, LWR, LHIP, LKNE, LANK, LHAND, LTOE))
    out = {"near": "L" if near_l else "R"}
    for tag, ch in (("near", near), ("far", far)):
        lc = p2f.chain(kp, ch[3], ch[4], ch[5], -1)
        ac = p2f.chain(kp, ch[0], ch[1], ch[2], +1, p2f.wrist_from_elbow)
        out["%s-upper-leg" % tag] = round(lc[0], 4)
        out["%s-lower-leg" % tag] = round(lc[1], 4)
        out["%s-upper-arm" % tag] = round(ac[0], 4)
        out["%s-lower-arm" % tag] = round(ac[1], 4)
        out["%s-hand" % tag] = round(p2f.seg_angle(kp, ch[2], ch[6]), 4)
        out["%s-foot" % tag] = round(p2f.seg_angle(kp, ch[5], ch[7]), 4)
    out["head"] = round(p2f.seg_angle(kp, NECK, NOSE), 4)
    out["torso"] = round(p2f.torso_lean(kp), 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pose", help="pose-extract.py 对站姿图的输出")
    ap.add_argument("--write", action="store_true",
                    help="写进 config/skeleton.json 的 calib")
    a = ap.parse_args()

    p2f = _load("pose-to-frames")
    kp = json.load(open(a.pose, encoding="utf-8"))[0]["kp"]
    calib = calib_from(kp, p2f)
    print(json.dumps(calib, ensure_ascii=False, indent=1))
    if not a.write:
        print("\n（没写盘；加 --write 覆盖骨架的 calib）")
        return

    import rigkit
    rig = rigkit.read()
    rig["calib"] = calib
    print("\n写入 %s" % rigkit.write(rig))


if __name__ == "__main__":
    main()
