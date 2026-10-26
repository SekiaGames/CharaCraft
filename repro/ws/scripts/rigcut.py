import numpy as np
from PIL import Image

MESH_COLS, MESH_ROWS = 5, 11
MAX_BONES = 4

def split(lay, table, W, H, suffix):
    info = {x["name"]: x for x in lay["layers"]}
    out = []
    n_skip = 0
    for r in sorted([x for x in table.get("rows") or [] if x.get("enabled")],
                    key=lambda x: x.get("z", 0)):
        layer = r.get("layer")
        if not layer:
            n_skip += 1
            continue
        box = info.get(layer)
        if not box:
            print("  跳过 %s：「部件 × 批次」在本动作里没选中它（禁用 / 空层）" % layer)
            n_skip += 1
            continue
        im = box["img"]
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        canvas.paste(im, (int(box["left"]), int(box["top"])), im)
        bb = canvas.getbbox()
        if bb is None:
            n_skip += 1
            continue
        out.append({"slot": layer, "key": (layer + suffix).replace(" ", "_"),
                    "img": canvas.crop(bb), "bbox": bb, "row": r})
    print("附件表：%d 行 → %d 块切件（跳过 %d）" % (len(table.get("rows") or []), len(out), n_skip))
    return out


def chain_weights(P, bs):
    n = len(bs)
    if n == 1:
        return [1.0]
    starts, acc = [], 0.0
    for b in bs:
        starts.append(acc)
        acc += b["len"]
    best, s = None, 0.0
    for k, b in enumerate(bs):
        q = b["pos"]
        a = np.radians(b["abs"])
        d = np.array([np.cos(a), np.sin(a)])
        ln = max(b["len"], 1e-6)
        t = min(max(float(np.dot(P - q, d)), 0.0), ln)
        dist = float(np.linalg.norm(P - (q + d * t)))
        if best is None or dist < best:
            best, s = dist, starts[k] + t
    ts = []
    for k in range(n - 1):
        joint = starts[k] + bs[k]["len"]
        band = max(4.0, 0.35 * min(bs[k]["len"] or 1e9, bs[k + 1]["len"] or 1e9))
        t = min(1.0, max(0.0, (s - joint) / (2.0 * band) + 0.5))
        ts.append(t * t * (3.0 - 2.0 * t))
    w = [1.0 - ts[0]] + [ts[k - 1] - ts[k] for k in range(1, n - 1)] + [ts[-1]]
    w = [max(0.0, x) for x in w]
    tot = sum(w)
    return [x / tot for x in w]


def place(items, B, spine):
    out = []
    n_skip = 0

    def local_rot(deg):
        a = np.radians(deg)
        return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]], float)

    for it in items:
        r, key, im = it["row"], it["key"], it["img"]
        cover = [int(i) for i in (r.get("bones") or []) if int(i) in B]
        if not cover:
            print("  跳过 %s：附件表里没给它挂骨骼" % it["slot"])
            n_skip += 1
            continue
        main = cover[0]
        bb = it["bbox"]
        fx, fy = bb[0], bb[1]
        w, h = im.width, im.height
        c = spine((fx + w / 2.0, fy + h / 2.0))
        off = local_rot(-B[main]["abs"]) @ (c - B[main]["pos"])
        base = {"x": round(float(off[0]), 2), "y": round(float(off[1]), 2),
                "rotation": round(-float(B[main]["abs"]), 2),
                "width": w, "height": h}
        if len(cover) == 1:
            out.append(({"name": it["slot"], "bone": str(main), "attachment": key}, {key: base}))
            continue

        bs = [B[n] for n in cover]
        uvs, verts, tris = [], [], []
        for j in range(MESH_ROWS):
            v = j / (MESH_ROWS - 1)
            for i in range(MESH_COLS):
                u = i / (MESH_COLS - 1)
                P = spine((fx + u * w, fy + v * h))
                uvs += [round(u, 5), round(v, 5)]
                ws = chain_weights(P, bs)
                top = [k for k in sorted(range(len(cover)), key=lambda k: -ws[k])[:MAX_BONES]
                       if ws[k] > 1e-4] or [0]
                tot = sum(ws[k] for k in top)
                verts.append(len(top))
                for k in top:
                    b = bs[k]
                    lp = local_rot(-b["abs"]) @ (P - b["pos"])
                    verts += [cover[k], round(float(lp[0]), 2), round(float(lp[1]), 2),
                              round(ws[k] / tot, 4)]
        for j in range(MESH_ROWS - 1):
            for i in range(MESH_COLS - 1):
                a = j * MESH_COLS + i
                tris += [a, a + 1, a + MESH_COLS + 1, a, a + MESH_COLS + 1, a + MESH_COLS]
        att = {"type": "mesh", **base, "uvs": uvs, "triangles": tris, "vertices": verts}
        out.append(({"name": it["slot"], "bone": str(main), "attachment": key}, {key: att}))
    print("  挂上 %d 个槽位（跳过 %d）" % (len(out), n_skip))
    return out
