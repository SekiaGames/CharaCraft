import argparse
import json
import os
import sys

import atlaspack
import psdkit
import rigcut
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

    tpath = os.path.join(rigkit.CONFIG, "attachments_template.json")
    table = json.load(open(tpath, encoding="utf-8"))
    if not (table.get("rows") or []):
        sys.exit("附件表是空的：%s —— 去「附件」页挂骨骼" % tpath)
    print("按附件表切件：%s" % tpath)

    items = rigcut.split(lay, table, lay["width"], lay["height"], "@" + a.act)
    tex = {it["key"]: it["img"] for it in items}
    pages, all_pages = atlaspack.write(d, a.act, tex)
    print("图集页 %s：%d 页 / %d 块贴图 → output/" % ("、".join(pages), len(pages), len(tex)))
    print("atlas：%d 页（%s）→ output/%s.atlas"
          % (len(all_pages), "、".join(all_pages), atlaspack.rig_name(d)))

if __name__ == "__main__":
    main()
