import argparse
import json
import math
import os
import shutil

VIEW = (560, 940)
ORIGIN = (260, 900)
BG = (40, 44, 60)
POSES = [("idle", 0.5), ("walk", 0.25), ("walk", 0.6), ("run", 0.1), ("run", 0.35),
         ("jump", 0.2), ("jump", 0.55), ("wave", 0.5), ("run_video", 0.2), ("run_video", 0.5),
         ("katana_attack", 0.2), ("katana_attack", 0.45), ("katana_attack", 0.66), ("katana_attack", 0.9),
         ("katana_attack", 1.26), ("katana_attack", 1.65), ("katana_attack", 2.3)]
HOLD = 3

def poses_for(anim_names):
    return [p for p in POSES if p[0] in anim_names]

def v2(x, y):
    return f"Vector2({x:.4g}, {y:.4g})"

def draw_order(slot_names, key):
    if not key.get("offsets"):
        return list(slot_names)
    out, moved = [None] * len(slot_names), set()
    for o in key["offsets"]:
        i = slot_names.index(o["slot"])
        out[i + o["offset"]] = i
        moved.add(i)
    rest = iter(i for i in range(len(slot_names)) if i not in moved)
    return [slot_names[i if i is not None else next(rest)] for i in out]

def flt(x):
    return f"{x:.6f}"

def mesh_node(name, att, z, tex, bw, bone_names, path):
    v, i = att["vertices"], 0
    pts, weights = [], {}
    nverts = len(att["uvs"]) // 2
    for n in range(nverts):
        cnt = v[i]
        i += 1
        X = Y = 0.0
        for _ in range(cnt):
            bi, bx, by, w = v[i:i + 4]
            i += 4
            wx, wy = bw[bone_names[bi]]
            X += w * (wx + bx)
            Y += w * (wy + by)
            weights.setdefault(bone_names[bi], [0.0] * nverts)[n] = w
        pts.append((X, -Y))
    uv = [(att["uvs"][2 * n] * att["width"], att["uvs"][2 * n + 1] * att["height"]) for n in range(nverts)]
    tri = att["triangles"]
    polys = ", ".join(f"PackedInt32Array({tri[q]}, {tri[q + 1]}, {tri[q + 2]})" for q in range(0, len(tri), 3))
    vec = lambda arr: "PackedVector2Array(" + ", ".join(f"{x:.4f}, {y:.4f}" for x, y in arr) + ")"
    bones = ", ".join(f'NodePath("{path[b][len("Skeleton2D/"):]}"), PackedFloat32Array({", ".join(flt(w) for w in ws)})'
                      for b, ws in weights.items())
    return "\n".join([f'[node name="{name}" type="Polygon2D" parent="Skeleton2D"]',
                      f"z_index = {z}",
                      f'texture = ExtResource("{tex}")',
                      'skeleton = NodePath("..")',
                      f"polygon = {vec(pts)}",
                      f"uv = {vec(uv)}",
                      f"polygons = [{polys}]",
                      f"internal_vertex_count = {nverts - att['hull']}",
                      f"bones = [{bones}]"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rig_dir")
    ap.add_argument("godot_dir")
    ap.add_argument("--name", default="kurumi")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    with open(os.path.join(a.rig_dir, f"{a.name}.json"), encoding="utf-8") as f:
        sk = json.load(f)
    os.makedirs(os.path.join(a.godot_dir, "images"), exist_ok=True)
    for p in os.listdir(os.path.join(a.rig_dir, "images")):
        shutil.copy(os.path.join(a.rig_dir, "images", p), os.path.join(a.godot_dir, "images", p))

    bones = {b["name"]: b for b in sk["bones"]}
    path = {}
    for b in sk["bones"]:
        path[b["name"]] = (path[b["parent"]] + "/" if "parent" in b else "Skeleton2D/") + b["name"]

    ext, subs, nodes = [], [], []
    images = sorted({att for s in sk["skins"][0]["attachments"].values() for att in s})
    for i, im in enumerate(images, 1):
        ext.append(f'[ext_resource type="Texture2D" path="res://images/{im}.png" id="{i}"]')
    tex_id = {im: i for i, im in enumerate(images, 1)}

    anim_ids = []
    for n, an in sk["animations"].items():
        dur = max(k["time"] for tl in an["bones"].values() for ch in tl.values() for k in ch)
        lines = [f'[sub_resource type="Animation" id="Anim_{n}"]', f'resource_name = "{n}"',
                 f"length = {dur:.4g}", "loop_mode = 1"]
        t = 0
        for bn, tl in an["bones"].items():
            b = bones[bn]
            for ch, keys in tl.items():
                if ch == "rotate":
                    prop, vals = "rotation", [flt(-math.radians(k['value'])) for k in keys]
                elif ch == "translate":
                    prop, vals = "position", [v2(b["x"] + k["x"], -(b["y"] + k["y"])) for k in keys]
                elif ch == "scale":
                    prop, vals = "scale", [v2(k.get("x", 1), k.get("y", 1)) for k in keys]
                else:
                    raise SystemExit(f"unsupported timeline {ch} on {bn}")
                times = ", ".join(f"{k['time']:.4g}" for k in keys)
                lines += [f'tracks/{t}/type = "value"', f"tracks/{t}/imported = false",
                          f"tracks/{t}/enabled = true",
                          f'tracks/{t}/path = NodePath("{path[bn]}:{prop}")',
                          f"tracks/{t}/interp = 1", f"tracks/{t}/loop_wrap = true",
                          f"tracks/{t}/keys = {{",
                          f'"times": PackedFloat32Array({times}),',
                          f'"transitions": PackedFloat32Array({", ".join(["1"] * len(keys))}),',
                          '"update": 0,', f'"values": [{", ".join(vals)}]', "}"]
                t += 1
        if any("drawOrder" in x for x in sk["animations"].values()):
            names = [s["name"] for s in sk["slots"]]
            keys = an.get("drawOrder") or [{"time": 0}]
            orders = [draw_order(names, k) for k in keys]
            for s in sk["slots"]:
                att = next(iter(sk["skins"][0]["attachments"][s["name"]].values()))
                node = ("Skeleton2D/" if att.get("type") == "mesh" else path[s["bone"]] + "/") + s["name"]
                times = ", ".join(f"{k['time']:.4g}" for k in keys)
                zs = ", ".join(str(o.index(s["name"])) for o in orders)
                lines += [f'tracks/{t}/type = "value"', f"tracks/{t}/imported = false",
                          f"tracks/{t}/enabled = true", f'tracks/{t}/path = NodePath("{node}:z_index")',
                          f"tracks/{t}/interp = 0", f"tracks/{t}/loop_wrap = true", f"tracks/{t}/keys = {{",
                          f'"times": PackedFloat32Array({times}),',
                          f'"transitions": PackedFloat32Array({", ".join(["1"] * len(keys))}),',
                          '"update": 1,', f'"values": [{zs}]', "}"]
                t += 1
        subs.append("\n".join(lines))
        anim_ids.append(n)
    subs.append('[sub_resource type="AnimationLibrary" id="AnimLib"]\n_data = {\n'
                + ",\n".join(f'&"{n}": SubResource("Anim_{n}")' for n in anim_ids) + "\n}")

    nodes.append(f'[node name="{a.name}" type="Node2D"]')
    nodes.append('[node name="Skeleton2D" type="Skeleton2D" parent="."]')
    for b in sk["bones"]:
        parent = path[b["name"]].rsplit("/", 1)[0]
        pos = v2(b["x"], -b["y"])
        nodes.append(f'[node name="{b["name"]}" type="Bone2D" parent="{parent}"]\n'
                     f"position = {pos}\nrest = Transform2D(1, 0, 0, 1, {b['x']:.4g}, {-b['y']:.4g})\n"
                     "auto_calculate_length_and_angle = false\nlength = 16.0")
    bw = {}
    for b in sk["bones"]:
        px, py = bw[b["parent"]] if "parent" in b else (0.0, 0.0)
        bw[b["name"]] = (px + b["x"], py + b["y"])
    bone_names = [b["name"] for b in sk["bones"]]
    for z, s in enumerate(sk["slots"]):
        (att_name, att), = sk["skins"][0]["attachments"][s["name"]].items()
        if att.get("type") == "mesh":
            nodes.append(mesh_node(s["name"], att, z, tex_id[att_name], bw, bone_names, path))
            continue
        mod = ""
        if "color" in s:
            c = s["color"]
            r, g, bl, al = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4, 6))
            mod = f"\nself_modulate = Color({r:.4g}, {g:.4g}, {bl:.4g}, {al:.4g})"
        nodes.append(f'[node name="{s["name"]}" type="Sprite2D" parent="{path[s["bone"]]}"]\n'
                     f"z_index = {z}\nposition = {v2(att['x'], -att['y'])}\n"
                     f'texture = ExtResource("{tex_id[att_name]}"){mod}')
    first = "run" if "run" in anim_ids else anim_ids[0]
    nodes.append('[node name="AnimationPlayer" type="AnimationPlayer" parent="."]\n'
                 'libraries = {\n&"": SubResource("AnimLib")\n}\n' f'autoplay = &"{first}"')

    with open(os.path.join(a.godot_dir, f"{a.name}.tscn"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f'[gd_scene load_steps={len(ext) + len(subs) + 1} format=3]\n\n'
                + "\n".join(ext) + "\n\n" + "\n\n".join(subs) + "\n\n" + "\n\n".join(nodes) + "\n")

    main_scene = "res://check.tscn" if a.check else f"res://{a.name}.tscn"
    with open(os.path.join(a.godot_dir, "project.godot"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"""config_version=5

[application]
config/name="{a.name} cutout rig"
run/main_scene="{main_scene}"
config/features=PackedStringArray("4.7")

[display]
window/size/viewport_width={VIEW[0]}
window/size/viewport_height={VIEW[1]}

[rendering]
environment/defaults/default_clear_color=Color({BG[0] / 255:.4g}, {BG[1] / 255:.4g}, {BG[2] / 255:.4g}, 1)
""")
    if a.check:
        with open(os.path.join(a.godot_dir, "check.tscn"), "w", encoding="utf-8", newline="\n") as f:
            f.write(f"""[gd_scene load_steps=3 format=3]

[ext_resource type="PackedScene" path="res://{a.name}.tscn" id="1"]
[ext_resource type="Script" path="res://check.gd" id="2"]

[node name="Check" type="Node2D"]
script = ExtResource("2")

[node name="Rig" parent="." instance=ExtResource("1")]
position = Vector2({ORIGIN[0]}, {ORIGIN[1]})
""")
        poses = ", ".join(f'["{n}", {t}]' for n, t in poses_for(anim_ids))
        with open(os.path.join(a.godot_dir, "check.gd"), "w", encoding="utf-8", newline="\n") as f:
            f.write(f"""extends Node2D
# Frame plan (one movie frame per _process at --fixed-fps 30):
#   poses: each POSES entry held {HOLD} frames via seek() -> frames 0..{len(POSES) * HOLD - 1}
#   switch test: play run 0.5 s, then play wave and let it run 0.5 s; last frame = wave@0.5 after run
const POSES = [{poses}]
const HOLD = {HOLD}
var frame := 0
var ap: AnimationPlayer

func _ready() -> void:
	ap = $Rig/AnimationPlayer
	ap.stop()
	print("anims ", ap.get_animation_list())

func _process(_dt: float) -> void:
	var n := POSES.size() * HOLD
	if frame < n:
		var p = POSES[frame / HOLD]
		ap.play(p[0])
		ap.seek(p[1], true)
		ap.pause()
	elif frame == n:
		ap.play("run")
	elif frame == n + 15:
		ap.play("wave")
	elif frame == n + 30:
		ap.pause()
		print("switch test frame ", frame, " wave pos ", ap.current_animation_position)
	elif frame >= n + 32:
		get_tree().quit()
	frame += 1
""")
    print(f"wrote {a.godot_dir}: {len(sk['bones'])} bones, {len(sk['slots'])} sprites, anims {anim_ids}")

if __name__ == "__main__":
    main()
