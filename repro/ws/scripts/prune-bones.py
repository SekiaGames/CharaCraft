#!/usr/bin/env python3
import json
import os
import sys

import editkit
import layerkit
import rigkit

HERE = os.path.dirname(os.path.abspath(__file__))


def keep_set(rig, rows):
    bones = {b["index"]: b for b in rig["bones"]}
    want = set()
    for r in rows:
        want |= {int(x) for x in r["bones"]}
    want |= {int(k) for k in (rig.get("calib") or {}) if k != "near"}
    keep = set()
    for i in want:
        while i >= 0 and i not in keep:
            keep.add(i)
            i = bones[i].get("parent", -1)
            i = -1 if i is None else int(i)
    return bones, keep


def main():
    args = sys.argv[1:]
    dry = "--dry" in args
    rest = [a for a in args if not a.startswith("--")]
    if len(rest) != 1:
        sys.exit("用法：prune-bones.py <案例目录> [--dry]")
    case = os.path.abspath(rest[0])

    rig = rigkit.read()
    path = os.path.join(rigkit.CONFIG, "attachments_template.json")
    with open(path, encoding="utf-8") as f:
        att = json.load(f)

    bones, keep = keep_set(rig, att["rows"])
    for i in sorted(set(bones) - keep):
        if bones[i].get("role"):
            sys.exit("骨骼 #%d（role=%s）没有部件也没有 calib 通道，删它会丢一条动作轨道"
                     % (i, bones[i]["role"]))

    old = [b["index"] for b in rig["bones"] if b["index"] in keep]
    new = {o: n for n, o in enumerate(old)}
    if dry:
        for o in old:
            print("#%d -> #%d" % (o, new[o]))
        print("%d -> %d，删 %d" % (len(bones), len(old), len(bones) - len(old)))
        return

    rig["bones"] = [b for b in rig["bones"] if b["index"] in keep]
    rigkit.reindex(rig)
    rigkit.write(rig)

    rows = []
    for r in att["rows"]:
        rows.append({"layer": r["layer"], "bones": [new[int(x)] for x in r["bones"]],
                     "z": r["z"], "enabled": r["enabled"]})
    att["rows"] = rows
    with open(path, "w", encoding="utf-8") as f:
        f.write(layerkit.dump_attachments(att))

    for p in editkit.bone_key_files(case):
        with open(p, encoding="utf-8") as f:
            rec = json.load(f)
        out = {}
        for fr in sorted(rec, key=int):
            row = {}
            for k in sorted(rec[fr], key=int):
                if int(k) not in new:
                    sys.exit("%s 的 %s 帧改的是 #%s，这根骨已经删了" % (os.path.basename(p), fr, k))
                row[str(new[int(k)])] = rec[fr][k]
            out[fr] = row
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)

    print("%d -> %d，删 %d" % (len(bones), len(old), len(bones) - len(old)))
    for o in old:
        print("  #%d -> #%d" % (o, new[o]))


if __name__ == "__main__":
    main()
