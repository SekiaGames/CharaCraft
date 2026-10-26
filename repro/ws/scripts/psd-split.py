import argparse
import glob
import json
import os
import sys

import psdkit

def write_batch_index(case, bid, W, H, layers):
    p = psdkit.batch_index_path(case, bid)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    clean = [{k: v for k, v in L.items() if k != "img"} for L in layers]
    json.dump({"batch": bid, "width": int(W), "height": int(H), "layers": clean},
              open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

def prune_batch_index(case, alive):
    gone = []
    for p in sorted(glob.glob(os.path.join(case, "base", "batches", "*.json"))):
        bid = os.path.splitext(os.path.basename(p))[0]
        if bid not in alive:
            os.remove(p)
            gone.append(bid)
    return gone

def scan(case, verbose=True):
    bs = psdkit.batches(case)
    if not bs:
        sys.exit("input/ 下没有 <批次>.psd（先用「同步 PSD」）")

    first_id = bs[0][0]
    total = {}
    for bid, path in bs:
        W, H, layers = psdkit.scan_batch(path)
        total[bid] = (W, H, layers)
        write_batch_index(case, bid, W, H, layers)
        if verbose:
            n_empty = sum(1 for L in layers if L["empty"])
            print("  扫描 %-20s %2d 层（空 %d）" % (bid, len(layers), n_empty))

    stale = prune_batch_index(case, set(total))
    if stale and verbose:
        print("  清掉已消失的批次清单：%s" % "、".join(stale))
    if verbose:
        W, H, layers = total[first_id]
        print("\n首批 %s（层名 / 层序以它为准，%d 层）· %d 批已扫 · 画布 %dx%d"
              % (first_id, len(layers), len(total), W, H))
        print("只写批次清单（矩阵和预览读它），不落图层图 —— 图由「打包图集」按选择直接从 PSD 取")
    return {"first": first_id, "canvas": total[first_id][:2], "batches": len(total)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case", help="素材目录（含 input/）")
    a = ap.parse_args()
    case = os.path.abspath(a.case)
    if not os.path.isdir(case):
        sys.exit("目录不存在：%s" % case)
    print("素材 %s" % case)
    res = scan(case)
    print("\n完成：首批 %s，%d 批，画布 %dx%d"
          % (res["first"], res["batches"], res["canvas"][0], res["canvas"][1]))

if __name__ == "__main__":
    main()
