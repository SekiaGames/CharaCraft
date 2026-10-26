import argparse
import glob
import hashlib
import os
import re
import shutil
import sys

OUT_GUESSES = [
    "~/ComfyUI-Shared/output",
    "~/ComfyUI-Installs/ComfyUI/ComfyUI/output",
    "~/ComfyUI/output",
]

BATCH_RE = re.compile(r"^(?P<pre>.+?)_(?P<stamp>\d{8})_(?P<clock>\d{6})\.psd$", re.I)

def find_out_dir(explicit=None):
    if explicit:
        d = os.path.abspath(os.path.expanduser(explicit))
        return d if os.path.isdir(d) else None
    for c in OUT_GUESSES:
        d = os.path.expanduser(c)
        if os.path.isdir(d):
            return d
    if os.environ.get("COMFY_OUT"):
        d = os.path.expanduser(os.environ["COMFY_OUT"])
        return d if os.path.isdir(d) else None
    return None

def norm_prefix(s):
    return re.sub(r"[\W_]+", "_", (s or "").strip().lower()).strip("_")

def batches(src, prefix):
    want = norm_prefix(prefix)
    out = []
    for p in glob.glob(os.path.join(src, "*.psd")):
        m = BATCH_RE.match(os.path.basename(p))
        if not m or norm_prefix(m.group("pre")) != want:
            continue
        out.append((m.group("clock"), p))
    out.sort(key=lambda x: (len(x[0]), x[0]))
    return out

def find_ref(case, src, prefix):
    dirs = [case, os.path.join(case, "input"),
            os.path.join(os.path.dirname(os.path.abspath(src).rstrip("/")), "input")]
    if os.environ.get("COMFY_IN"):
        dirs.append(os.path.expanduser(os.environ["COMFY_IN"]))
    for d in dirs:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = os.path.join(d, prefix + ext)
            if os.path.isfile(p):
                return p
    want = norm_prefix(prefix)
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "*"))):
            stem, ext = os.path.splitext(os.path.basename(p))
            if ext.lower() in (".png", ".jpg", ".jpeg", ".webp") and norm_prefix(stem) == want:
                return p
    return None

def same_file(a, b):
    if not (os.path.isfile(a) and os.path.isfile(b)):
        return False
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    h = hashlib.blake2b(digest_size=16)
    g = hashlib.blake2b(digest_size=16)
    for path, d in ((a, h), (b, g)):
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                d.update(chunk)
    return h.digest() == g.digest()

def import_batch(src_path, work, backup, force=False):
    has_work = os.path.isfile(work)
    has_backup = os.path.isfile(backup)

    if force:
        if has_work:
            os.remove(work)
        shutil.move(src_path, work)
        if has_backup:
            os.remove(backup)
        shutil.copy2(work, backup)
        return "forced", "按 --force 用源端覆盖"

    if not has_work and not has_backup:
        shutil.move(src_path, work)
        shutil.copy2(work, backup)
        return "moved", "迁入 + 备份"

    if not has_backup:
        shutil.copy2(src_path, backup)
        os.remove(src_path)
        return "backup", "补备份，源端已清"

    if same_file(src_path, backup) or same_file(src_path, work):
        os.remove(src_path)
        return "dedupe", "源端重复，已清掉"
    return "kept", "同批次已有不同内容，源端未动（--force 才覆盖）"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case", help="素材目录（含 input/）")
    ap.add_argument("--from", dest="src", default=None, help="ComfyUI 输出目录")
    ap.add_argument("--prefix", default=None, help="PSD 文件名前缀（默认 = 目录名）")
    ap.add_argument("--force", action="store_true",
                    help="覆盖已有的工作副本/备份（默认只在缺失时写，保住手工修改）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    case = os.path.abspath(a.case)
    if not os.path.isdir(case):
        sys.exit("目录不存在：%s" % case)
    prefix = a.prefix or os.path.basename(case.rstrip("/"))
    src = find_out_dir(a.src)
    if not src:
        sys.exit("找不到 ComfyUI 输出目录（试过：%s）" % "、".join(OUT_GUESSES))

    found = batches(src, prefix)
    print("源目录 %s" % src)
    print("前缀   %s_*_*.psd  →  %d 个批次" % (prefix, len(found)))
    if not found:
        others = sorted({BATCH_RE.match(os.path.basename(p)).group("pre")
                         for p in glob.glob(os.path.join(src, "*.psd"))
                         if BATCH_RE.match(os.path.basename(p))})
        if others:
            print("这个输出目录里现有的前缀：%s" % "、".join(others[:8]))
        print("\n没有匹配的批次。确认 ComfyUI 里 Save-PSD 节点的 filename_prefix 是 %r。" % prefix)
        return

    inp = os.path.join(case, "input")
    if not a.dry_run:
        os.makedirs(inp, exist_ok=True)

    ref = find_ref(case, src, prefix)
    print("站姿图 %s" % (os.path.basename(ref) if ref else "没找到 %s.png（不影响流程）" % prefix))
    if ref and not a.dry_run:
        dst = os.path.join(inp, os.path.basename(ref))
        if not os.path.isfile(dst):
            shutil.copy2(ref, dst)
            print("       已复制到 input/%s（它还是 ComfyUI 的 LoadImage 输入，源端保留）"
                  % os.path.basename(ref))

    n_new = n_kept = 0
    for bid, p in found:
        work = os.path.join(inp, bid + ".psd")
        backup = os.path.join(inp, bid + "_backup.psd")
        if a.dry_run:
            print("  %-20s 将迁入 %s" % (bid, os.path.basename(p)))
            n_new += 1
            continue
        action, state = import_batch(p, work, backup, a.force)
        if action in ("kept",):
            n_kept += 1
        else:
            n_new += 1
        print("  %-20s %-28s %s" % (bid, os.path.basename(p), state))

    print("\n同步完成：%d 批有动作，%d 批原样保留" % (n_new, n_kept))
    print("ComfyUI 输出目录里不再保留这些 PSD（迁移）。")
    print("改图就改 input/<批次>.psd；改完跑「拆图」→ 打包图集 → 合并。")
    if a.dry_run:
        print("（--dry-run，没有真的动文件）")

if __name__ == "__main__":
    main()
