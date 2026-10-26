import argparse
import json
import os
import sys

import psdkit
import rigcut
import riggeom
import rigkit

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--act", required=True, help="动作名：按 edit/Edit-Parts-<act>.json 选图")
    a = ap.parse_args()

    d = a.case.rstrip("/")
    lay = psdkit.effective(d, a.act)
    print("生效图层 %d 个（首批 %s，平替 %d，跳过 %d）"
          % (len(lay["layers"]), lay["first"], len(lay["subs"]), len(lay["skipped"])))
    for name, why in lay["skipped"]:
        print("    跳过 %-14s %s" % (name, why))

    g = riggeom.load()
    print("骨架 %d 根（%s）" % (len(g["B"]), g["path"]))

    tpath = os.path.join(rigkit.CONFIG, "attachments_template.json")
    table = json.load(open(tpath, encoding="utf-8"))
    if not (table.get("rows") or []):
        sys.exit("附件表是空的：%s —— 去「附件」页挂骨骼" % tpath)
    print("按附件表挂载：%s" % tpath)

    items = rigcut.split(lay, table, lay["width"], lay["height"], "@" + a.act)
    slots, atts = [], {}
    for slot, att in rigcut.place(items, g["B"], g["spine"]):
        slots.append(slot)
        atts[slot["name"]] = att

    W, H = lay["width"], lay["height"]
    sk = {
        "skeleton": {"spine": "4.2.0", "x": -W / 2.0, "y": 0, "width": W, "height": H,
                     "images": "./images/", "audio": ""},
        "bones": g["bones"],
        "slots": slots,
        "skins": [{"name": "default", "attachments": atts}],
    }
    out = os.path.join(d, "base", "rig")
    os.makedirs(out, exist_ok=True)
    jout = os.path.join(out, a.act + ".json")
    json.dump(sk, open(jout, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写入 %s：%d 骨骼 / %d 槽位（皮肤片段）" % (jout, len(g["bones"]), len(slots)))

if __name__ == "__main__":
    main()
