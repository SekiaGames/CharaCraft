import glob
import json
import math
import sys

import cv2
import numpy as np
from PIL import Image

DEBUG = []

def measure(img_path, kp, belt_offset=None):
    a = np.array(Image.open(img_path).convert("RGB")).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = (r > 60) & (r - g > 40) & (r - b > 25) & (g < 80)
    white = (np.minimum(np.minimum(r, g), b) > 175) & (np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b) < 30) & (b - r > -10)
    neck_y = kp[1][1]
    hips = [k for k in (kp[8], kp[11]) if k]
    hip_y = np.mean([k[1] for k in hips])
    y0, y1 = int(neck_y + 0.3 * (hip_y - neck_y)), int(hip_y + 20)
    if belt_offset is not None:
        y0, y1 = int(hip_y + belt_offset - 25), int(hip_y + belt_offset + 25)
    def longest_run(row):
        xs = np.where(row)[0]
        if len(xs) == 0:
            return 0
        return max(len(r_) for r_ in np.split(xs, np.where(np.diff(xs) > 3)[0] + 1))
    belt_y = y0 + int(np.argmax([longest_run(red[y]) for y in range(y0, y1)]))
    bx = np.where(red[belt_y - 2:belt_y + 3].any(0))[0]
    if len(bx) < 10:
        return None
    belt_back, belt_front = bx.min(), bx.max()
    sk = white.copy()
    sk[:belt_y + 3] = False
    sk = cv2.morphologyEx(sk.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab = cv2.connectedComponents(sk, connectivity=8)
    band = lab[belt_y + 3:belt_y + 120, max(belt_back - 60, 0):belt_front + 61].ravel()
    ids, cnt = np.unique(band[band > 0], return_counts=True)
    area = np.bincount(lab.ravel())
    seed = [i for i, c in zip(ids, cnt) if c > 30 and area[i] > 1500]
    if not seed:
        raise SystemExit(f"{img_path}: no skirt under the belt at y={belt_y}")
    ys, xs = np.nonzero(np.isin(lab, seed))
    top, bottom = belt_y, ys.max()
    low = ys > top + 0.65 * (bottom - top)
    fi, bi = np.argmax(np.where(low, xs, -1)), np.argmin(np.where(low, xs, 10 ** 6))
    front = (xs[fi], ys[fi])
    back = (xs[bi], ys[bi])
    ang = lambda p, q: math.degrees(math.atan2(q[0] - p[0], q[1] - p[1]))
    DEBUG.append((img_path, belt_y, (belt_back, belt_front), front, back, int(bottom)))
    return {"belt_y": int(belt_y), "belt_minus_hip": float(belt_y - hip_y), "front_deg": ang((belt_front, belt_y), front),
            "back_deg": ang((belt_back, belt_y), back), "skirt_len": int(bottom - top)}

def main():
    pattern, loop_poses, rest_img, rest_poses, out = sys.argv[1:6]
    lp = {p["file"]: p["kp"] for p in json.load(open(loop_poses))}
    rest = measure(rest_img, json.load(open(rest_poses))[0]["kp"])
    files = sorted(glob.glob(pattern))
    first = [measure(f, lp[f.replace("\\", "/").split("/")[-1]]) for f in files]
    offset = float(np.median([m["belt_minus_hip"] for m in first if m]))
    DEBUG.clear()
    DEBUG.append(None)
    res = []
    for f in files:
        name = f.replace("\\", "/").split("/")[-1]
        m = measure(f, lp[name], offset)
        if m is None:
            res.append({"file": name, "front_delta": None, "back_delta": None})
            print(name, "belt hidden, skipped")
            continue
        m["front_delta"] = round(m["front_deg"] - rest["front_deg"], 1)
        m["back_delta"] = round(m["back_deg"] - rest["back_deg"], 1)
        m["file"] = name
        res.append(m)
        print(name, "front", m["front_delta"], "back", m["back_delta"], "len", m["skirt_len"])
    fd, bd = [m["front_delta"] for m in res], [m["back_delta"] for m in res]
    fv, bv = [x for x in fd if x is not None], [x for x in bd if x is not None]
    summary = {"rest": rest, "front_delta_range": [min(fv), max(fv)], "back_delta_range": [min(bv), max(bv)],
               "front_delta": fd, "back_delta": bd}
    json.dump({"summary": summary, "frames": res}, open(out, "w"), indent=1, default=float)
    from PIL import ImageDraw
    tiles = []
    for path, by, (bb, bf), fr, bk, bot in [x for x in DEBUG if x][::3]:
        im = Image.open(path).convert("RGB")
        d = ImageDraw.Draw(im)
        d.line([(bb, by), (bf, by)], fill=(255, 0, 0), width=6)
        d.line([(bf, by), fr], fill=(0, 0, 255), width=4)
        d.line([(bb, by), bk], fill=(0, 0, 255), width=4)
        d.line([(0, bot), (im.width, bot)], fill=(255, 255, 0), width=2)
        cx = (bb + bf) // 2
        tiles.append(im.crop((cx - 300, by - 300, cx + 300, by + 600)).resize((200, 300)))
    sheet = Image.new("RGB", (200 * len(tiles), 300))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 200, 0))
    sheet.save(out.replace(".json", "_debug.png"))
    print(json.dumps({k: v for k, v in summary.items() if "range" in k or k == "rest"}, default=float))

if __name__ == "__main__":
    main()
