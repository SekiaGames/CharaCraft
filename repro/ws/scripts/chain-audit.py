import argparse
import os
import re
import sys

import editkit

E = editkit.DIR + "/"

SPEC = [
    {"id": "同步 PSD",
     "ins": [],
     "outs": ["input/*.psd"],
     "writes_input": True, "optional": True},

    {"id": "拆图",
     "ins": ["input/*.psd"],
     "outs": ["base/batches/{batch}.json"],
     "ui": ["base/batches/{batch}.json"]},

    {"id": "打包图集",
     "ins": ["input/*.psd", E + "Edit-Parts-{act}.json", E + "Edit-PartsDisable.json"],
     "outs": ["output/{name}-{act}.png", "output/{name}.atlas"]},

    {"id": "皮肤片段",
     "ins": ["input/*.psd", E + "Edit-Parts-{act}.json", E + "Edit-PartsDisable.json"],
     "outs": ["base/rig/{act}.json"]},

    {"id": "合并 + 预览",
     "ins": ["base/rig/{act}.json", "clip-{act}/animations.json", "output/{name}.atlas"],
     "outs": ["output/{name}.json", "output/preview.html"]},

    {"id": "抽帧",
     "ins": ["input/clip-{act}.mp4"],
     "outs": ["clip-{act}/frames/f_*.png", "clip-{act}/source_sha1_mark.json"],
     "own": ["clip-{act}/source_sha1_mark.json"]},

    {"id": "DWPose 骨骼",
     "ins": ["clip-{act}/frames/f_*.png"],
     "outs": ["clip-{act}/dwpose_bones.json", "clip-{act}/dwpose_sha1_mark.json"],
     "own": ["clip-{act}/dwpose_sha1_mark.json"]},

    {"id": "自动挑帧",
     "ins": ["clip-{act}/dwpose_bones.json", E + "Edit-FrameSheet-{act}.json"],
     "outs": ["clip-{act}/keyframes.json"]},

    {"id": "关键帧转动画",
     "ins": ["clip-{act}/dwpose_bones.json", "config/skeleton.json",
             "clip-{act}/keyframes.json",
             E + "Edit-BoneKeys-{act}.json",
             E + "Edit-FrameSheet-{act}.json"],
     "outs": ["clip-{act}/animations.json"]},

    {"id": "页面 · 拖点",
     "ins": ["clip-{act}/frames/f_*.png", "clip-{act}/dwpose_bones.json"],
     "outs": [E + "Edit-BoneKeys-{act}.json"],
     "optional": True},
]


def rig_name(case):
    base = os.path.basename(case.rstrip("/")).lower()
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "rig"


def acts_of(case):
    return sorted(n[5:] for n in os.listdir(case)
                  if n.startswith("clip-") and os.path.isdir(os.path.join(case, n)))


def batch_ids(case):
    inp = os.path.join(case, "input")
    if not os.path.isdir(inp):
        return []
    return sorted({m.group(1) for m in
                   (re.fullmatch(r"(\d+)\.psd", n) for n in os.listdir(inp)) if m})


def expand(pat, acts, batches, name):
    if "{act}" in pat:
        return [x for a in acts for x in expand(pat.replace("{act}", a), acts, batches, name)]
    if "{batch}" in pat:
        return [x for b in batches for x in expand(pat.replace("{batch}", b), acts, batches, name)]
    return [pat.replace("{name}", name)]


def rgx(pat):
    out, i = [], 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


class Rule:
    def __init__(self, spec, acts, batches, name):
        self.id = spec["id"]
        self.writes_input = bool(spec.get("writes_input"))
        self.optional = bool(spec.get("optional"))
        self.ins = [(p, rgx(p)) for p in
                    [q for pat in spec["ins"] for q in expand(pat, acts, batches, name)]]
        self.outs = [(p, rgx(p)) for p in
                     [q for pat in spec["outs"] for q in expand(pat, acts, batches, name)]]
        self.ui = [rgx(q) for pat in spec.get("ui") or []
                   for q in expand(pat, acts, batches, name)]
        self.own = [rgx(q) for pat in spec.get("own") or []
                    for q in expand(pat, acts, batches, name)]

    def hits_in(self, rel):
        return any(r.match(rel) for _, r in self.ins)

    def hits_out(self, rel):
        return any(r.match(rel) for _, r in self.outs)

    def hits_ui(self, rel):
        return any(r.match(rel) for r in self.ui)

    def hits_own(self, rel):
        return any(r.match(rel) for r in self.own)


def walk(case):
    for root, dirs, files in os.walk(case):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            yield os.path.relpath(os.path.join(root, f), case)


def audit(case):
    acts, batches, name = acts_of(case), batch_ids(case), rig_name(case)
    rules = [Rule(s, acts, batches, name) for s in SPEC]
    files = sorted(walk(case))

    produced, external, records, off = {}, [], [], []
    for rel in files:
        owner = next((r for r in rules if r.hits_out(rel)), None)
        if owner:
            produced.setdefault(owner.id, []).append(rel)
        elif rel.startswith(E):
            records.append(rel)
        elif rel.startswith("input/"):
            external.append(rel)
        else:
            off.append(rel)

    orphan, selfonly = [], []
    for r in rules:
        for rel in produced.get(r.id, []):
            if rel.startswith(("output/", "input/", E)):
                continue
            others = [o.id for o in rules if o is not r and o.hits_in(rel)]
            if others:
                continue
            if r.hits_ui(rel) or r.hits_own(rel):
                continue
            if r.hits_in(rel):
                selfonly.append((r.id, rel))
            else:
                orphan.append((r.id, rel))

    bad_input = [(r.id, rel) for r in rules if not r.writes_input
                 for rel in produced.get(r.id, []) if rel.startswith("input/")]

    missing = [r.id for r in rules if not r.optional and not produced.get(r.id)]

    idle_input = [rel for rel in external
                  if not any(r.hits_in(rel) for r in rules)]

    idle_edit = [rel for rel in records
                 if not any(r.hits_in(rel) for r in rules)]

    return {"rules": rules, "produced": produced, "external": external, "off": off,
            "orphan": orphan, "selfonly": selfonly, "bad_input": bad_input,
            "missing": missing, "idle_input": idle_input, "idle_edit": idle_edit,
            "total": len(files)}


def consumers(res, rel, skip=None):
    return [r.id for r in res["rules"]
            if r.id != skip and r.hits_in(rel)]


def report(res):
    print("（每步的产出 → 消费方）\n")
    for r in res["rules"]:
        got = res["produced"].get(r.id) or []
        print("%s  产出 %d 个" % (r.id, len(got)))
        for pat, rx in r.outs:
            hit = [x for x in got if rx.match(x)]
            who = sorted({c for x in hit for c in consumers(res, x, r.id)})
            if pat.startswith("output/"):
                note = "交付物（免检）"
            elif who:
                note = "消费：" + "、".join(who)
            elif any(r.hits_ui(x) for x in hit):
                note = "只给页面看，不往下流"
            elif any(r.hits_own(x) for x in hit):
                note = "本步内部消费，不往下流"
            elif not hit:
                note = "还没产出"
            else:
                note = "!! 没有消费方"
            print("    %-42s %s" % (pat, note))
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--delete", action="store_true", help="删掉链外文件（只删文件，不删目录）")
    ap.add_argument("--graph", action="store_true", help="打印每步产出的消费方")
    a = ap.parse_args()
    case = os.path.abspath(a.case)
    if not os.path.isdir(case):
        sys.exit("目录不存在：%s" % case)
    res = audit(case)
    print("链上 %d 个文件 · 链外 %d 个 · 没有消费方 %d 个"
          % (res["total"], len(res["off"]), len(res["orphan"])))
    if a.graph:
        report(res)

    if res["off"]:
        print("链外文件（不在任何步骤的 outs，也不在 input/）：")
        for rel in res["off"]:
            print("  " + rel)
    if res["bad_input"]:
        print("\ninput/ 只能被消费，但这些步骤往里写：")
        for sid, rel in res["bad_input"]:
            print("  %s → %s" % (sid, rel))
    if res["orphan"]:
        print("\n没有消费方的产物：")
        for sid, rel in res["orphan"]:
            print("  %s → %s" % (sid, rel))
    if res["missing"]:
        print("\n还没产出（这步没跑过或没跑完）：" + "、".join(res["missing"]))
    if res["selfonly"]:
        print("\n只被本步消费（不往下流）：")
        for sid, rel in res["selfonly"]:
            print("  %s → %s" % (sid, rel))
    if res["idle_input"]:
        print("\ninput/ 里没被任何步骤读到（备份之类通常正常）：")
        for rel in res["idle_input"]:
            print("  " + rel)
    if res["idle_edit"]:
        print("\nedit/ 里没被任何步骤读到（对应的动作可能已经删了）：")
        for rel in res["idle_edit"]:
            print("  " + rel)

    hard = res["off"] + [rel for _, rel in res["orphan"]] + \
        [rel for _, rel in res["bad_input"]]
    if not hard:
        print("\n通过：没有链外文件，每步产出都有消费方")
        return
    if not a.delete:
        if res["off"]:
            print("\n加 --delete 删掉链外文件（只删链外，不动没有消费方的产物）")
        else:
            print("\n这些是步骤定义的问题，--delete 不管；改 SPEC 或改那一步的输出")
        sys.exit(1)
    for rel in res["off"]:
        os.remove(os.path.join(case, rel))
    print("\n已删链外文件 %d 个" % len(res["off"]))
    for root, dirs, files in os.walk(case, topdown=False):
        if root != case and not os.listdir(root):
            os.rmdir(root)
            print("  空目录已清：" + os.path.relpath(root, case))
    sys.exit(1 if res["orphan"] or res["bad_input"] else 0)


if __name__ == "__main__":
    main()
