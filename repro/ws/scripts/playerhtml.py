import base64
import json
import os

TEMPLATE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ preview</title>
<link rel="stylesheet" href="https://unpkg.com/@esotericsoftware/spine-player@4.2.*/dist/spine-player.css">
<script src="https://unpkg.com/@esotericsoftware/spine-player@4.2.*/dist/iife/spine-player.js"></script>
<style>
body{margin:0;background:#1c1f2b;color:#ccd;font:14px sans-serif}
#bar{padding:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
button{background:#3a4060;color:#fff;border:0;padding:6px 12px;border-radius:4px;cursor:pointer}
button.on{background:#4c7f6b}
button.act{background:#5a4a2a}
button.act.on{background:#8a6a24}
#p{width:100%;height:calc(100vh - 50px)}
</style>
</head><body><div id="bar"></div><div id="p"></div>
<script>
const NAME = __NAME__;
const RIG = __RIG__;
const ATLAS = __ATLAS__;
const PAGES = __PAGES__;
const ACTS = __ACTS__;
let cur = null, curAct = ACTS[0];

function b64(s, mime) {
  return 'data:' + mime + ';base64,' + btoa(unescape(encodeURIComponent(s)));
}

function build() {
  if (cur) { try { cur.dispose(); } catch (e) {} cur = null; }
  document.getElementById('p').innerHTML = '';
  const raw = {};
  raw[NAME + '.json'] = b64(JSON.stringify(RIG), 'application/json');
  raw[NAME + '.atlas'] = b64(ATLAS, 'text/plain');
  for (const k in PAGES) raw[k] = PAGES[k];
  const cfg = {
    skeleton: NAME + '.json',
    atlas: NAME + '.atlas',
    rawDataURIs: raw,
    animation: curAct,
    showControls: true,
    premultipliedAlpha: false,
    backgroundColor: '#282c3cff'
  };
  cfg.success = p => { cur = p; drawBar(); };
  cfg.error = (p, r) => { document.getElementById('bar').textContent = 'Error: ' + r; };
  new spine.SpinePlayer('p', cfg);
}

function drawBar() {
  const bar = document.getElementById('bar');
  bar.innerHTML = '';
  for (const a of ACTS) {
    const b = document.createElement('button');
    b.className = 'act' + (a === curAct ? ' on' : '');
    b.textContent = a;
    b.onclick = () => { curAct = a; build(); };
    bar.appendChild(b);
  }
  const tip = document.createElement('span');
  tip.style.marginLeft = 'auto';
  tip.style.opacity = 0.7;
  tip.textContent = '图集 ' + NAME + '.atlas（' + Object.keys(PAGES).length + ' 页）· 动画 ' + curAct;
  bar.appendChild(tip);
}

build();
</script></body></html>
"""


def page_names(text):
    lines = text.split("\n")
    return [ln for i, ln in enumerate(lines)
            if ln and not ln.startswith(" ") and i + 1 < len(lines)
            and lines[i + 1].startswith("size:")]


def uri(p, mime):
    with open(p, "rb") as f:
        return "data:%s;base64," % mime + base64.b64encode(f.read()).decode()


def write(rig_dir, name, rig, atlas_text):
    pages = {n: uri(os.path.join(rig_dir, n), "image/png") for n in page_names(atlas_text)}
    acts = sorted(rig.get("animations") or {})
    html = (TEMPLATE
            .replace("__TITLE__", name)
            .replace("__NAME__", json.dumps(name))
            .replace("__RIG__", json.dumps(rig))
            .replace("__ATLAS__", json.dumps(atlas_text))
            .replace("__PAGES__", json.dumps(pages))
            .replace("__ACTS__", json.dumps(acts)))
    p = os.path.join(rig_dir, "preview.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    return p, len(pages), acts
