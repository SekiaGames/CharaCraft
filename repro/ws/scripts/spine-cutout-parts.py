import argparse
import json
import os

import cv2
import numpy as np
from PIL import Image

def key_green(rgb):
    r, g, b = [rgb[..., i].astype(np.int16) for i in range(3)]
    spill = g - np.maximum(r, b)
    alpha = np.clip((80 - spill) / 60.0, 0, 1)
    out = rgb.copy()
    g2 = np.minimum(g, np.maximum(r, b) + 4)
    out[..., 1] = np.where(spill > 4, g2, g).astype(np.uint8)
    return out, (alpha * 255).astype(np.uint8)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("out_dir")
    ap.add_argument("--min-area", type=int, default=2000)
    ap.add_argument("--pad", type=int, default=4)
    a = ap.parse_args()

    rgb = np.array(Image.open(a.sheet).convert("RGB"))
    rgb2, alpha = key_green(rgb)
    mask = (alpha > 127).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    os.makedirs(a.out_dir, exist_ok=True)
    comps = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= a.min_area]
    comps.sort(key=lambda i: (stats[i, 0] // 50, stats[i, 1]))
    H, W = mask.shape
    meta = []
    for k, i in enumerate(comps):
        x, y, w, h = stats[i, :4]
        x1, y1 = max(x - a.pad, 0), max(y - a.pad, 0)
        x2, y2 = min(x + w + a.pad, W), min(y + h + a.pad, H)
        comp = (labels[y1:y2, x1:x2] == i).astype(np.uint8)
        near = cv2.dilate(comp, np.ones((5, 5), np.uint8))
        al = alpha[y1:y2, x1:x2] * near
        rgba = np.dstack([rgb2[y1:y2, x1:x2], al]).astype(np.uint8)
        name = f"part_{k:02d}.png"
        Image.fromarray(rgba, "RGBA").save(os.path.join(a.out_dir, name))
        meta.append({"file": name, "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
                     "area": int(stats[i, cv2.CC_STAT_AREA])})
    with open(os.path.join(a.out_dir, "parts.json"), "w") as f:
        json.dump(meta, f, indent=1)
    for m in meta:
        print(m)

if __name__ == "__main__":
    main()
