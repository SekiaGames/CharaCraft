import argparse
import glob
import json
import os
import re
import sys

import playerhtml


def rig_name(d):
    return re.sub(r"[^a-z0-9]+", "_", os.path.basename(d.rstrip("/")).lower()).strip("_") or "rig"


def action_order(acts):
    order = ["idle", "walk", "run"]
    return sorted(acts, key=lambda a: (order.index(a) if a in order else 99, a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--name", default=None, help="骨架名（默认 = 案例目录名归一化）")
    a = ap.parse_args()

    d = a.case.rstrip("/")
    name = a.name or rig_name(d)

    frags = {}
    for p in sorted(glob.glob(os.path.join(d, "base", "rig", "*.json"))):
        act = os.path.splitext(os.path.basename(p))[0]
        if not os.path.isdir(os.path.join(d, "clip-" + act)):
            continue
        with open(p, encoding="utf-8") as f:
            frags[act] = json.load(f)
    if not frags:
        sys.exit("缺 base/rig/<动作>.json —— 先跑「打包图集」")
    acts = action_order(frags)

    base = frags[acts[0]]
    skin = {"name": "default", "attachments": {}}
    for act in acts:
        for slotname, atts in ((frags[act].get("skins") or [{}])[0].get("attachments") or {}).items():
            skin["attachments"].setdefault(slotname, {}).update(atts)

    anims, skipped = {}, []
    for p in sorted(glob.glob(os.path.join(d, "clip-*", "animations.json"))):
        act = os.path.basename(os.path.dirname(p))[len("clip-"):]
        if act not in frags:
            skipped.append(act)
            continue
        with open(p, encoding="utf-8") as f:
            for an, tl in json.load(f).items():
                anims[act] = tl
    if not anims:
        anims = {"idle": {"bones": {}}}
        print("没有 clip-*/animations.json → 造一个空的 idle（只有 setup 姿态）")

    for act in acts:
        tl = anims.get(act)
        if tl is None:
            continue
        sl = {}
        for s in frags[act].get("slots") or []:
            if s.get("attachment"):
                sl[s["name"]] = {"attachment": [{"time": 0, "name": s["attachment"]}]}
        tl["slots"] = sl

    out = {k: v for k, v in base.items() if k not in ("animations", "skins")}
    out["skins"] = [skin]
    out["animations"] = anims
    out.setdefault("skeleton", {})["images"] = "./images/"

    od = os.path.join(d, "output")
    os.makedirs(od, exist_ok=True)
    jp = os.path.join(od, name + ".json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    ap = os.path.join(od, name + ".atlas")
    if not os.path.isfile(ap):
        sys.exit("缺 %s —— 多页 atlas 是「打包图集」出的，先跑它" % ap)
    with open(ap, encoding="utf-8") as f:
        atlas_text = f.read()

    n_att = sum(len(v) for v in skin["attachments"].values())
    print("骨架 %d 骨骼 / %d 槽位 · 一套皮肤里 %d 个附件（%d 个动作各一份）"
          % (len(out.get("bones", [])), len(out.get("slots", [])), n_att, len(acts)))
    print("合并 %d 个动作：%s" % (len(anims), ", ".join(sorted(anims))))
    if skipped:
        print("跳过（没有 base/rig 片段）：%s" % ", ".join(sorted(set(skipped))))
    for k in sorted(anims):
        tl = anims[k].get("bones") or {}
        chans = [ch for c in tl.values() for ch in c.values() if isinstance(ch, list)]
        dur = max((max((f.get("time", 0) for f in ch), default=0) for ch in chans), default=0)
        print("  %-6s %5.2fs  %d 根骨骼有轨道 · %d 个槽位切到 @%s"
              % (k, dur, len(tl), len(anims[k].get("slots") or {}), k))
    print("写入 %s" % jp)
    hp, n_page, hp_acts = playerhtml.write(od, name, out, atlas_text)
    print("写入 %s：atlas %d 页 / 动画 %s" % (hp, n_page, ", ".join(hp_acts)))


if __name__ == "__main__":
    main()
