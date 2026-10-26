#!/usr/bin/env python3
import glob
import json
import os
import sys

import editkit
import layerkit
import rigkit


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dump(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def rows_with(m, keys):
    out = {}
    for k in keys:
        out[str(m[int(k)])] = keys[k]
    return {k: out[k] for k in sorted(out, key=int)}


def main():
    args = sys.argv[1:]
    if len(args) != 2:
        sys.exit("用法：reorder-bones.py <案例目录> 0,1,2,...,16")
    case = os.path.abspath(args[0])
    order = [int(x) for x in args[1].split(",") if x.strip()]
    rig = rigkit.read()
    old = [b["index"] for b in rig["bones"]]
    if sorted(order) != sorted(old):
        sys.exit("顺序必须是现有 index 的一个排列，现在是 %s" % old)
    m = {o: n for n, o in enumerate(order)}

    for b in rig["bones"]:
        b["index"] = m[b["index"]]
        p = b.get("parent", -1)
        b["parent"] = -1 if p is None or int(p) < 0 else m[int(p)]
        if b.get("aim") is not None:
            b["aim"] = m[int(b["aim"])]
    rig["bones"].sort(key=lambda b: b["index"])
    cal = rig.get("calib") or {}
    near = {"near": cal["near"]} if "near" in cal else {}
    rig["calib"] = dict(near, **rows_with(m, {k: v for k, v in cal.items() if k != "near"}))
    rigkit.write(rig)

    att_path = os.path.join(rigkit.CONFIG, "attachments_template.json")
    att = load(att_path)
    for r in att.get("rows") or []:
        r["bones"] = [m[int(x)] for x in r["bones"]]
    with open(att_path, "w", encoding="utf-8") as f:
        f.write(layerkit.dump_attachments(att))

    for p in editkit.bone_key_files(case):
        rec = load(p)
        dump(p, {fr: rows_with(m, rec[fr]) for fr in rec})

    for p in sorted(glob.glob(os.path.join(case, "clip-*", "dwpose_bones.json"))):
        d = load(p)
        for fr in d.get("frames") or []:
            fr["bones"] = rows_with(m, fr.get("bones") or {})
        dump(p, d)

    for o in old:
        print("#%d -> #%d" % (o, m[o]))


if __name__ == "__main__":
    main()
