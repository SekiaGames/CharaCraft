function ang(a, b) {
  return Math.atan2(b[0] - a[0], b[1] - a[1]) * 180 / Math.PI;
}

const RT_EDGE = 1.2;
const RT = { key: '', skel: null, data: null, pages: {}, byRole: {},
             anchor: null, crel: null, alpha: 1, last: 1, slots: 0,
             status: null, adj: { kx: 1, ky: 1, dx: 0, dy: 0, lock: true } };

function wrap180(v) {
  return ((v + 180) % 360 + 360) % 360 - 180;
}

function roleIndex(role) {
  return (MO.roles || {})[role];
}

function poseBones(fr) {
  const p = bonePose(fr);
  const lim = MO.limits || { knee: 45, arm: 24, lean: 9 };
  const ed = (MO.keys || {})[MO.sel] || {};
  const cut = (i, a, b) => {
    if (i === undefined || p.rot[i] === undefined || ed[i]) return;
    p.rot[i] = Math.max(a, Math.min(b, p.rot[i]));
  };
  cut(roleIndex('leg-down'), -lim.knee, 180);
  cut(roleIndex('leg-down-back'), -lim.knee, 180);
  for (const r of ['arm-front-up', 'arm-front-down', 'arm-back-up', 'arm-back-down']) {
    cut(roleIndex(r), -lim.arm, lim.arm);
  }
  cut(roleIndex('body-down'), -lim.lean, lim.lean);
  for (const k2 of ['body-down', 'head']) {
    const mate = k2 === 'head' ? 'neck' : 'body-up';
    const a = String(roleIndex(k2)), b = String(roleIndex(mate));
    const meta = MO.meta || {};
    const la = (meta[a] || {}).l || 0, lb = (meta[b] || {}).l || 0;
    if (!(la + lb) || p.rot[a] === undefined) continue;
    const k = la / (la + lb), v = p.rot[a];
    p.rot[a] = v * k;
    p.rot[b] = (p.rot[b] || 0) + v * (1 - k);
  }
  return p;
}

async function rtLoad() {
  const c = state && state.case;
  if (!c) return '先选案例';
  const stem = c.rig_stem || c.name;
  const key = [c.path, stem, SK_REV].join('|');
  if (RT.key === key) return '';
  const url = (rel) => '/api/file?p=' + encodeURIComponent(c.path + '/' + rel)
    + '&dir=' + encodeURIComponent(DIR);
  const grab = async (rel) => {
    const r = await fetch(url(rel));
    if (!r.ok) throw new Error(rel + ' 读不到（' + r.status + '）');
    return r;
  };
  const rig = await (await grab('output/' + stem + '.json')).json();
  const atlasText = await (await grab('output/' + stem + '.atlas')).text();
  RT.data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(
    new spine.TextureAtlas(atlasText))).readSkeletonData(rig);
  RT.skel = new spine.Skeleton(RT.data);
  const sk = await (await fetch('/api/skeleton' + qs())).json();
  for (const b of ((sk.rig || {}).bones || [])) {
    const d = RT.data.bones[b.index];
    if (!d) continue;
    d.x = +b.x; d.y = +b.y; d.rotation = +b.rotation; d.length = +(b.length || 0);
  }
  RT.anchor = null;
  if (MO.sel) renderKeyEditor();
  RT.pages = {};
  for (const name of rtPageNames(atlasText)) {
    RT.pages[name] = await new Promise((ok, no) => {
      const im = new Image();
      im.onload = () => ok({ img: im, w: im.naturalWidth, h: im.naturalHeight });
      im.onerror = no;
      im.src = url('output/' + name);
    });
  }
  RT.byRole = {};
  for (const role in (MO.roles || {})) RT.byRole[role] = RT.skel.bones[MO.roles[role]];
  RT.refLean = MO.calib ? MO.calib.torso : null;
  RT.stats = null;
  RT.anchor = null;
  RT.key = key;
  return '';
}

function rtPageNames(text) {
  const out = [], lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (lines[i] && lines[i][0] !== ' ' && (lines[i + 1] || '').startsWith('size:')) out.push(lines[i]);
  }
  return out;
}

function rtSetAct() {
  const skin = RT.skel.skin, act = MO.act;
  if (!skin) return;
  for (const slot of RT.skel.slots) {
    const at = skin.getAttachment(slot.data.index, slot.data.name + '@' + act);
    slot.setAttachment(at || null);
  }
}

function rtApplySt(st) {
  RT.skel.setToSetupPose();
  rtSetAct();
  for (const src in st.rot) {
    const b = RT.skel.bones[+src];
    if (b) b.rotation = b.data.rotation + st.rot[src];
  }
  for (const src in (st.scl || {})) {
    const b = RT.skel.bones[+src];
    if (!b) continue;
    b.scaleX = st.scl[src];
    b.scaleY = st.scl[src];
  }
  for (const src in (st.off || {})) {
    const b = RT.skel.bones[+src];
    if (!b) continue;
    b.x = b.data.x + st.off[src][0];
    b.y = b.data.y + st.off[src][1];
  }
  const h = RT.skel.bones[roleIndex('root')];
  if (h) {
    const o = (st.off || {})[roleIndex('root')];
    h.y = h.data.y + st.hipY + (o ? o[1] : 0);
  }
  RT.skel.updateWorldTransform(spine.Physics.update);
}

function rtPose(fr) {
  const st = poseBones(fr);
  rtApplySt(st);
  return st;
}

function rtAnchor() {
  if (RT.anchor) return RT.anchor;
  const f1 = MO.list[0];
  const hips = RT.skel && RT.skel.bones[roleIndex('body-down')];
  const dn = RT.skel && RT.skel.bones[roleIndex('leg-down')];
  if (!f1 || !f1.hip || !hips || !dn) return null;
  rtPose(f1);
  const s = 1 / (MO.scale || 1);
  const px = f1.hip[0] / (MO.scale || 1);
  const py = f1.hip[1] / (MO.scale || 1);
  const L = ((MO.meta || {})[roleIndex('leg-down')] || {}).l || 0;
  const rad = dn.getWorldRotationX() * Math.PI / 180;
  const ay = py - s * hips.worldY;
  const ankle = [px + s * (dn.worldX - hips.worldX) + L * s * Math.cos(rad),
                 py - s * (dn.worldY - hips.worldY) - L * s * Math.sin(rad)];
  RT.anchor = { s, px, py: Math.max(ay, ankle[1]), tx: px - s * hips.worldX,
                ty: py + s * hips.worldY };
  return RT.anchor;
}

function rtPose(fr) {
  const st = poseBones(fr);
  rtApplySt(st);
  return st;
}

function rtTri(ctx, p1, p2, p3) {
  const den = (p2[2] - p1[2]) * (p3[3] - p1[3]) - (p3[2] - p1[2]) * (p2[3] - p1[3]);
  if (!den) return;
  const a = ((p2[0] - p1[0]) * (p3[3] - p1[3]) - (p3[0] - p1[0]) * (p2[3] - p1[3])) / den;
  const c = ((p3[0] - p1[0]) * (p2[2] - p1[2]) - (p2[0] - p1[0]) * (p3[2] - p1[2])) / den;
  const b = ((p2[1] - p1[1]) * (p3[3] - p1[3]) - (p3[1] - p1[1]) * (p2[3] - p1[3])) / den;
  const d = ((p3[1] - p1[1]) * (p2[2] - p1[2]) - (p2[1] - p1[1]) * (p3[2] - p1[2])) / den;
  const e = p1[0] - a * p1[2] - c * p1[3];
  const f = p1[1] - b * p1[2] - d * p1[3];
  const cx = (p1[0] + p2[0] + p3[0]) / 3, cy = (p1[1] + p2[1] + p3[1]) / 3;
  const grow = (p) => {
    const dx = p[0] - cx, dy = p[1] - cy, L = Math.hypot(dx, dy) || 1;
    return [p[0] + dx / L * RT_EDGE, p[1] + dy / L * RT_EDGE];
  };
  const sx = Math.max(0, Math.floor(Math.min(p1[2], p2[2], p3[2])) - 1);
  const sy = Math.max(0, Math.floor(Math.min(p1[3], p2[3], p3[3])) - 1);
  const sw = Math.min(RT.cw, Math.ceil(Math.max(p1[2], p2[2], p3[2])) + 1) - sx;
  const sh = Math.min(RT.ch, Math.ceil(Math.max(p1[3], p2[3], p3[3])) + 1) - sy;
  if (sw <= 0 || sh <= 0) return;
  const q1 = grow(p1), q2 = grow(p2), q3 = grow(p3);
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(q1[0], q1[1]);
  ctx.lineTo(q2[0], q2[1]);
  ctx.lineTo(q3[0], q3[1]);
  ctx.closePath();
  ctx.clip();
  ctx.transform(a, b, c, d, e, f);
  ctx.drawImage(RT.cimg, sx, sy, sw, sh, sx, sy, sw, sh);
  ctx.restore();
}

function rtPageOf(at) {
  const pg = at.region && at.region.page;
  return (pg && RT.pages[pg.name]) || RT.pages[Object.keys(RT.pages)[0]] || null;
}

function rtPaint(cv, st, alpha) {
  const ctx = cv.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, cv.width, cv.height);
  const a = rtAnchor();
  if (!a || !st || alpha <= 0) return 0;
  rtApplySt(st);
  const kx = RT.adj.kx, ky = RT.adj.ky;
  ctx.globalAlpha = alpha;
  ctx.setTransform(a.s * kx, 0, 0, -a.s * ky,
                   (a.tx - a.px) * kx + a.px + RT.adj.dx,
                   (a.ty - a.py) * ky + a.py + RT.adj.dy);
  let n = 0;
  for (const slot of RT.skel.drawOrder) {
    const at = slot.getAttachment();
    if (!at) continue;
    const pg = rtPageOf(at);
    if (!pg) continue;
    n++;
    RT.cimg = pg.img;
    RT.cw = pg.w;
    RT.ch = pg.h;
    if (at instanceof spine.RegionAttachment) {
      const v = new Float32Array(8);
      at.computeWorldVertices(slot, v, 0, 2);
      const uv = at.uvs;
      const p = (i) => [v[i * 2], v[i * 2 + 1], uv[i * 2] * RT.cw, uv[i * 2 + 1] * RT.ch];
      rtTri(ctx, p(0), p(1), p(2));
      rtTri(ctx, p(0), p(2), p(3));
    } else {
      const v = new Float32Array(at.worldVerticesLength);
      at.computeWorldVertices(slot, 0, at.worldVerticesLength, v, 0, 2);
      const uv = at.uvs, tr = at.triangles;
      for (let i = 0; i < tr.length; i += 3) {
        const p = (k) => {
          const j = tr[i + k];
          return [v[j * 2], v[j * 2 + 1], uv[j * 2] * RT.cw, uv[j * 2 + 1] * RT.ch];
        };
        rtTri(ctx, p(0), p(1), p(2));
      }
    }
  }
  ctx.globalAlpha = 1;
  return n;
}

function rtDraw(fr) {
  const cv = $('#frcanvas'), ctx = cv.getContext('2d');
  RT.slots = 0;
  const a = rtAnchor();
  if (!a || RT.alpha <= 0) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, cv.width, cv.height);
    return RT;
  }
  RT.status = poseBones(fr);
  RT.slots = rtPaint(cv, RT.status, RT.alpha);
  return RT;
}


const IOU = { res: 320, cv: null, ctx: null, frame: null, fkey: '', vid: null, vkey: '',
              vdim: '', base: null, W: 0, H: 0, iou: null, fit: null, run: 0 };

function iouPrep(w, h) {
  const k = IOU.res / Math.max(w, h);
  const W = Math.max(16, Math.round(w * k));
  const H = Math.max(16, Math.round(h * k));
  if (!IOU.cv) {
    IOU.cv = document.createElement('canvas');
    IOU.ctx = IOU.cv.getContext('2d', { willReadFrequently: true });
  }
  if (IOU.cv.width !== W || IOU.cv.height !== H) {
    IOU.cv.width = W;
    IOU.cv.height = H;
    IOU.vid = null;
    IOU.vkey = '';
  }
  IOU.W = W;
  IOU.H = H;
  return { W, H };
}

function iouRenderMask(cv, W, H) {
  const c = IOU.ctx;
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.clearRect(0, 0, W, H);
  c.drawImage(cv, 0, 0, W, H);
  const d = c.getImageData(0, 0, W, H).data;
  const thr = 60 * Math.max(RT.alpha, 0.25);
  const m = new Uint8Array(W * H);
  for (let i = 0; i < W * H; i++) m[i] = d[i * 4 + 3] > thr ? 1 : 0;
  return m;
}

function iouVideoMask(img, W, H) {
  const c = IOU.ctx;
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.clearRect(0, 0, W, H);
  c.drawImage(img, 0, 0, W, H);
  const d = c.getImageData(0, 0, W, H).data;
  const m = new Uint8Array(W * H);
  for (let i = 0; i < W * H; i++) {
    m[i] = (d[i * 4 + 1] - Math.max(d[i * 4], d[i * 4 + 2])) < 60 ? 1 : 0;
  }
  return m;
}

function iouScore(a, b) {
  let inter = 0, uni = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    const x = a[i], y = b[i];
    if (x) { na++; if (y) inter++; }
    if (y) nb++;
    if (x || y) uni++;
  }
  return { iou: uni ? inter / uni : 0, miss: nb ? 1 - inter / nb : 0, extra: na ? 1 - inter / na : 0 };
}

const FIELD_INF = 1 << 13;

function iouField(mask, W, H, out) {
  const n = W * H, d = (out && out.length === n) ? out : new Uint16Array(n);
  for (let i = 0; i < n; i++) d[i] = mask[i] ? 0 : FIELD_INF;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = y * W + x;
      let v = d[i];
      if (!v) continue;
      if (x) v = Math.min(v, d[i - 1] + 3);
      if (y) {
        v = Math.min(v, d[i - W] + 3);
        if (x) v = Math.min(v, d[i - W - 1] + 4);
        if (x < W - 1) v = Math.min(v, d[i - W + 1] + 4);
      }
      d[i] = v;
    }
  }
  for (let y = H - 1; y >= 0; y--) {
    for (let x = W - 1; x >= 0; x--) {
      const i = y * W + x;
      let v = d[i];
      if (!v) continue;
      if (x < W - 1) v = Math.min(v, d[i + 1] + 3);
      if (y < H - 1) {
        v = Math.min(v, d[i + W] + 3);
        if (x < W - 1) v = Math.min(v, d[i + W + 1] + 4);
        if (x) v = Math.min(v, d[i + W - 1] + 4);
      }
      d[i] = v;
    }
  }
  return d;
}

function iouWarpScore(base, vid, W, H, s, dx, dy, st) {
  const cx = W / 2, cy = H / 2, inv = 1 / s, gap = st || 1;
  const xs = new Int32Array(W), ys = new Int32Array(H);
  for (let x = 0; x < W; x++) xs[x] = Math.round(cx + (x - dx - cx) * inv);
  for (let y = 0; y < H; y++) ys[y] = Math.round(cy + (y - dy - cy) * inv);
  let inter = 0, uni = 0;
  for (let y = 0; y < H; y += gap) {
    const sy = ys[y], ok = sy >= 0 && sy < H;
    const r0 = ok ? sy * W : 0, r1 = y * W;
    for (let x = 0; x < W; x += gap) {
      const sx = xs[x];
      const a = (ok && sx >= 0 && sx < W) ? base[r0 + sx] : 0;
      const b = vid[r1 + x];
      if (a) { if (b) inter++; uni++; }
      else if (b) uni++;
    }
  }
  return uni ? inter / uni : 0;
}

function iouFit(base, vid, W, H) {
  let best = { s: 1, dx: 0, dy: 0, iou: iouScore(base, vid).iou };
  const R = Math.round(W * 0.15), st = Math.max(3, Math.round(W / 32));
  const fast = Math.max(2, Math.round(W / 160));
  let coarse = { s: 1, dx: 0, dy: 0, iou: iouWarpScore(base, vid, W, H, 1, 0, 0, fast) };
  for (let sc = 0.8; sc < 1.2501; sc += 0.05) {
    for (let dx = -R; dx <= R; dx += st) {
      for (let dy = -R; dy <= R; dy += st) {
        if (sc === 1 && dx === 0 && dy === 0) continue;
        const v = iouWarpScore(base, vid, W, H, sc, dx, dy, fast);
        if (v > coarse.iou) coarse = { s: sc, dx: dx, dy: dy, iou: v };
      }
    }
  }
  best = { s: coarse.s, dx: coarse.dx, dy: coarse.dy,
           iou: iouWarpScore(base, vid, W, H, coarse.s, coarse.dx, coarse.dy) };
  if (best.iou < iouWarpScore(base, vid, W, H, 1, 0, 0)) {
    best = { s: 1, dx: 0, dy: 0, iou: iouWarpScore(base, vid, W, H, 1, 0, 0) };
  }
  for (const step of [st, Math.round(st / 2) || 1, 1]) {
    for (let k = 0; k < 4; k++) {
      let moved = false;
      for (const c of [[0.01, 0, 0], [-0.01, 0, 0], [0, step, 0], [0, -step, 0],
                       [0, 0, step], [0, 0, -step]]) {
        const sc = best.s + c[0], dx = best.dx + c[1], dy = best.dy + c[2];
        if (sc < 0.7 || sc > 1.4) continue;
        const v = iouWarpScore(base, vid, W, H, sc, dx, dy);
        if (v > best.iou) { best = { s: sc, dx: dx, dy: dy, iou: v }; moved = true; }
      }
      if (!moved) break;
    }
  }
  return best;
}

function iouFrameImg(f) {
  const key = MO.act + '|' + f.n;
  if (IOU.frame && IOU.fkey === key) return Promise.resolve(IOU.frame);
  return new Promise((ok, no) => {
    const im = new Image();
    im.onload = () => {
      IOU.frame = im;
      IOU.fkey = key;
      IOU.fit = null;
      ok(im);
    };
    im.onerror = no;
    im.src = '/api/file?p=' + encodeURIComponent(f.path) + '&dir=' + encodeURIComponent(DIR);
  });
}

function iouPaint() {
  const el = $('#frIou'), sp = $('#frIouSplit');
  const r = IOU.iou;
  if (!r) {
    el.textContent = 'IoU —';
    el.className = 'iou';
    sp.textContent = '漏 — · 多 —';
    return;
  }
  el.textContent = 'IoU ' + r.iou.toFixed(3);
  el.className = 'iou ' + (r.iou >= 0.7 ? 'good' : r.iou >= 0.5 ? 'mid' : 'bad');
  sp.textContent = '漏 ' + Math.round(r.miss * 100) + '% · 多 ' + Math.round(r.extra * 100) + '%';
}

async function iouUpdate() {
  const f = MO.list.find(x => x.n === MO.sel);
  if (!f || !RT.skel || RT.alpha <= 0) return;
  const key = MO.act + '|' + f.n;
  const { W, H } = iouPrep(f.w || 640, f.h || 640);
  const base = iouRenderMask($('#frcanvas'), W, H);
  IOU.base = base;
  IOU.run = f.n;
  let im;
  try { im = await iouFrameImg(f); } catch (e) { return; }
  if (IOU.W !== W || IOU.H !== H || IOU.run !== f.n) return;
  const vk = key + '@' + W + 'x' + H;
  if (IOU.vkey !== vk || !IOU.vid) {
    IOU.vid = iouVideoMask(im, W, H);
    IOU.vkey = vk;
    IOU.fit = null;
    $('#frFitNote').textContent = '';
  }
  IOU.iou = iouScore(base, IOU.vid);
  iouPaint();
}

function renderRuntime() {
  const f = MO.list.find(x => x.n === MO.sel);
  if (!f) return;
  const cv = $('#frcanvas');
  const W = f.w || 640, H = f.h || 640;
  if (cv.width !== W || cv.height !== H) {
    cv.width = W;
    cv.height = H;
  }
  rtRedraw();
}

let rtRaf = 0;

function rtRedraw() {
  if (rtRaf) return;
  rtRaf = requestAnimationFrame(() => {
    rtRaf = 0;
    const note = $('#frNote');
    rtLoad().then(err => {
      if (err) { note.textContent = err; return; }
      rtDraw(bonesAt(MO.sel));
      iouUpdate();
      const a = RT.anchor, st = RT.status || {};
      note.textContent = a
        ? '骨骼直出 · ' + RT.slots + ' 个部件 · 缩放 ' + a.s.toFixed(2)
          + ' · 腿 ' + st.okLeg + '/2 · 臂 ' + st.okArm + '/2'
        : '骨骼不全，摆不出来';
    }).catch(e => { note.textContent = '载入失败：' + e.message; });
  });
}

function frAdj(src) {
  if (RT.adj.lock) {
    if (src === 'frSx') $('#frSy').value = $('#frSx').value;
    if (src === 'frSy') $('#frSx').value = $('#frSy').value;
  }
  RT.adj.kx = +$('#frSx').value / 100;
  RT.adj.ky = +$('#frSy').value / 100;
  RT.adj.dx = +$('#frDx').value;
  RT.adj.dy = +$('#frDy').value;
  $('#frSxv').textContent = RT.adj.kx.toFixed(2);
  $('#frSyv').textContent = RT.adj.ky.toFixed(2);
  $('#frDxv').textContent = RT.adj.dx;
  $('#frDyv').textContent = RT.adj.dy;
  rtRedraw();
  if (LP.frames.length) lpShow();
}

function iouApplyFit(b) {
  const a = RT.anchor;
  const f = MO.list.find(x => x.n === MO.sel);
  if (!a || !f) return null;
  const k = (f.w || 640) / IOU.W;
  const cv = $('#frcanvas');
  const sc = b.s;
  const want = {
    kx: RT.adj.kx * sc,
    ky: RT.adj.ky * sc,
    dx: (sc - 1) * (a.px - cv.width / 2) + sc * RT.adj.dx + b.dx * k,
    dy: (sc - 1) * (a.py - cv.height / 2) + sc * RT.adj.dy + b.dy * k,
  };
  const put = (id, v) => {
    const el = $('#' + id);
    const lo = +el.min, hi = +el.max;
    const vv = Math.min(hi, Math.max(lo, Math.round(v)));
    el.value = vv;
    return { v: vv, cut: Math.abs(vv - v) > 0.5 };
  };
  const sx = put('frSx', want.kx * 100);
  const sy = put('frSy', want.ky * 100);
  const dx = put('frDx', want.dx);
  const dy = put('frDy', want.dy);
  frAdj('frSx');
  return { kx: sx, ky: sy, dx, dy, cut: sx.cut || sy.cut || dx.cut || dy.cut, want };
}

function initFrame() {
  const adj = frAdj;
  for (const id of ['frSx', 'frSy', 'frDx', 'frDy']) $('#' + id).oninput = () => adj(id);
  $('#frLock').onclick = () => {
    RT.adj.lock = !RT.adj.lock;
    $('#frLock').classList.toggle('on', RT.adj.lock);
    $('#frLock').textContent = RT.adj.lock ? '等比' : '独立';
    if (RT.adj.lock) $('#frSy').value = $('#frSx').value;
    adj();
  };
  $('#frReset').onclick = () => {
    $('#frSx').value = 100;
    $('#frSy').value = 100;
    $('#frDx').value = 0;
    $('#frDy').value = 0;
    adj();
  };
  $('#frAlpha').oninput = (e) => {
    RT.alpha = +e.target.value / 100;
    if (RT.alpha > 0) RT.last = RT.alpha;
    $('#frToggle').textContent = RT.alpha > 0 ? '隐藏运行时' : '显示运行时';
    frLines();
    rtRedraw();
  };
  $('#frToggle').onclick = () => {
    RT.alpha = RT.alpha > 0 ? 0 : (RT.last || 1);
    $('#frAlpha').value = Math.round(RT.alpha * 100);
    $('#frToggle').textContent = RT.alpha > 0 ? '隐藏运行时' : '显示运行时';
    frLines();
    if (RT.alpha > 0) rtRedraw(); else { IOU.iou = null; iouPaint(); }
  };
  $('#frFit').onclick = () => {
    const f = MO.list.find(x => x.n === MO.sel);
    if (!f || !IOU.base || !IOU.vid) {
      $('#frFitNote').textContent = '还没有可比的掩码';
      return;
    }
    const t0 = performance.now();
    const b = iouFit(IOU.base, IOU.vid, IOU.W, IOU.H);
    const k = (f.w || 640) / IOU.W;
    IOU.fit = b;
    const got = iouApplyFit(b);
    $('#frFitNote').textContent = '已套到滑块：×' + b.s.toFixed(2)
      + ' 平移 ' + (b.dx * k >= 0 ? '+' : '') + Math.round(b.dx * k)
      + ',' + (b.dy * k >= 0 ? '+' : '') + Math.round(b.dy * k)
      + '（上限 ' + b.iou.toFixed(3) + '）'
      + (got && got.cut ? '（有滑块到顶，未完全生效）' : '')
      + ' · ' + Math.round(performance.now() - t0) + 'ms';
  };
}

function renderFramePreview() {
  const panel = $('#panelFrame'), img = $('#frimg'), svg = $('#frsvg'), hint = $('#frhint');
  if (!MO.sel) { panel.hidden = true; return; }
  const f = MO.list.find(x => x.n === MO.sel);
  const fr = bonesAt(MO.sel);
  if (!f || !fr) { panel.hidden = true; return; }
  panel.hidden = false;
  const url = '/api/file?p=' + encodeURIComponent(f.path) + '&dir=' + encodeURIComponent(DIR);
  if (img.dataset.src !== url) { img.src = url; img.dataset.src = url; }
  const W = f.w || 640, H = f.h || 640;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const J = boneJoints(fr);
  const g = [];
  const col = (k) => {
    const r = ((MO.meta || {})[k] || {}).r || '';
    if (r.indexOf('arm-') === 0) return '#2f6fd0';
    if (r === 'body-down' || r === 'head') return '#c9a227';
    return '#2f9d6a';
  };
  if (J) {
    for (const k in J) {
      g.push(`<line x1="${J[k].p[0].toFixed(1)}" y1="${J[k].p[1].toFixed(1)}"`
        + ` x2="${J[k].q[0].toFixed(1)}" y2="${J[k].q[1].toFixed(1)}"`
        + ` stroke="${col(k)}" stroke-width="7" stroke-linecap="round"/>`);
    }
  }
  svg.innerHTML = g.join('');
  const st = poseBones(fr).rot;
  const deg = (role) => {
    const v = st[roleIndex(role)];
    return v === undefined ? '—' : v.toFixed(0) + '°';
  };
  hint.textContent = [
    '膝 ' + deg('leg-down') + ' / ' + deg('leg-down-back'),
    '肘 ' + deg('arm-front-down') + ' / ' + deg('arm-back-down'),
    '躯干 ' + deg('body-down'),
  ].join('  ·  ');
  frLines();
  renderRuntime();
}

function frLines() {
  $('#frsvg').style.display = RT.alpha >= 0.99 ? 'none' : '';
}


document.querySelectorAll('.tab').forEach(b => {
  b.onclick = () => {
    if (TAB === b.dataset.tab) return;
    TAB = b.dataset.tab;
    const u = new URL(location.href);
    u.searchParams.set('tab', TAB);
    history.replaceState(null, '', u);
    load();
  };
});
