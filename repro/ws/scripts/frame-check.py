import glob
import hashlib
import json
import os
import sys

def sha1(path, limit=8 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            limit -= 1 << 20
            if limit <= 0:
                break
    return h.hexdigest()

def find_video(md):
    case = os.path.dirname(os.path.abspath(md).rstrip("/"))
    act = os.path.basename(md.rstrip("/"))
    if act.startswith("clip-"):
        act = act[len("clip-"):]
    hits = sorted(glob.glob(os.path.join(case, "input", "clip-%s.*" % act)))
    return hits[0] if hits else None

def main():
    if len(sys.argv) < 2:
        sys.exit("用法：frame-check.py <clip-<act> 目录>")
    md = sys.argv[1].rstrip("/")
    n = len(glob.glob(os.path.join(md, "frames", "f_*.png")))
    print("抽出 %d 帧" % n)
    if not n:
        sys.exit("没有抽出任何帧：视频解码失败，或者文件不是视频")

    video = find_video(md)
    cur = None
    if video:
        cur = {"video": os.path.basename(video),
               "size": os.path.getsize(video), "sha1": sha1(video)}
    fp_path = os.path.join(md, "source_sha1_mark.json")
    prev = json.load(open(fp_path, encoding="utf-8")) if os.path.isfile(fp_path) else None
    if cur:
        os.makedirs(os.path.dirname(fp_path), exist_ok=True)
        json.dump(cur, open(fp_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    stale = [p for p in ("dwpose_bones.json", "animations.json")
             if os.path.exists(os.path.join(md, p))]
    if not stale:
        return
    if cur and prev and prev.get("sha1") == cur["sha1"] and prev.get("size") == cur["size"]:
        print("视频没变（%s），%s 还能用；要重做就接着跑 DWPose 骨骼 → 关键帧转动画，再跑「合并 + 预览」"
              % (cur["video"], "、".join(stale)))
    else:
        print("注意：视频变了（或第一次记录指纹），%s 还是上一轮的，要重跑 DWPose 骨骼 → 关键帧转动画"
              " 再跑「合并 + 预览」" % "、".join(stale))

if __name__ == "__main__":
    main()
