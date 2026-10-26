function skToWorld(ox, oy, a) {
  const r = a * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  return [ox * c - oy * s, -ox * s - oy * c];
}
function skToLocal(dx, dy, a) {
  const r = a * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  return [dx * c - dy * s, -dx * s - dy * c];
}

function skWorld(rig) {
  const bones = (rig && rig.bones) || [];
  const map = {};
  bones.forEach(b => { map[b.index] = b; });
  const out = {}, busy = {};
  function one(i) {
    if (out[i]) return out[i];
    if (busy[i]) return null;
    busy[i] = 1;
    const d = map[i];
    if (!d) return null;
    const par = (d.parent == null ? -1 : +d.parent);
    const ox = +(d.x || 0), oy = +(d.y || 0), lrot = +(d.rotation || 0), len = +(d.length || 0);
    let v = null;
    if (par >= 0 && map[par]) {
      const pv = one(par);
      if (pv) {
        const dd = skToWorld(ox, oy, pv.rotation);
        v = { x: pv.x + dd[0], y: pv.y + dd[1], rotation: pv.rotation + lrot };
      }
    }
    if (!v) v = { x: ox, y: oy, rotation: lrot };
    out[i] = { index: i,
               parent_index: (par >= 0 && map[par]) ? par : -1,
               ox: ox, oy: oy, lrot: lrot, length: len, zero: !(len >= 0.5),
               side: d.side || 'front', role: d.role,
               aim: d.aim == null ? null : +d.aim,
               x: v.x, y: v.y, rotation: v.rotation };
    return out[i];
  }
  bones.forEach(b => { one(b.index); });
  return bones.map(b => out[b.index]).filter(Boolean);
}

const BONE_COLOR = '#d8315b';

let BONE_SEL = null, SK_SAVE_T = null, SK_REV = 0;

const skR2 = v => Math.round((+v || 0) * 100) / 100;
const skWrap = v => ((v + 180) % 360 + 360) % 360 - 180;
const skNm = b => '#' + b.index;

function boxClamp(v, a, b) {
  return v < a ? a : (v > b ? b : v);
}

function boneEnd(x, y, rot, len) {
  const r = rot * Math.PI / 180;
  return [x + Math.cos(r) * len, y - Math.sin(r) * len];
}

function boneFits(x, y, rot, len, W, H) {
  const e = boneEnd(x, y, rot, len);
  return e[0] >= -0.01 && e[0] <= W + 0.01 && e[1] >= -0.01 && e[1] <= H + 0.01;
}

function boneShift(x, y, rot, len, W, H) {
  const e = boneEnd(x, y, rot, len);
  const ox = e[0] - x, oy = e[1] - y;
  const x0 = Math.max(0, -ox), x1 = Math.min(W, W - ox);
  const y0 = Math.max(0, -oy), y1 = Math.min(H, H - oy);
  return [x0 > x1 ? x : x0, x0 > x1 ? x : x1,
          y0 > y1 ? y : y0, y0 > y1 ? y : y1];
}

function boneReach(x, y, rot, W, H) {
  const r = rot * Math.PI / 180;
  const ux = Math.cos(r), uy = -Math.sin(r);
  let t = Infinity;
  if (ux > 1e-9) t = Math.min(t, (W - x) / ux);
  else if (ux < -1e-9) t = Math.min(t, -x / ux);
  if (uy > 1e-9) t = Math.min(t, (H - y) / uy);
  else if (uy < -1e-9) t = Math.min(t, -y / uy);
  return Math.max(0, t);
}

function boneFitRot(x, y, from, to, len, W, H) {
  if (!boneFits(x, y, from, len, W, H)) return from;
  if (boneFits(x, y, to, len, W, H)) return to;
  const d = skWrap(to - from);
  let lo = 0, hi = 1;
  for (let k = 0; k < 16; k++) {
    const mid = (lo + hi) / 2;
    if (boneFits(x, y, skWrap(from + d * mid), len, W, H)) lo = mid;
    else hi = mid;
  }
  return skWrap(from + d * lo);
}

function withSel(list) {
  return list.map(b => (b.index === BONE_SEL ? Object.assign({}, b, { sel: true }) : b));
}

function boneShapeSvg(list, opt) {
  const o = opt || {};
  const R = o.r || 14, k = R / 14;
  const grab = Math.max(9, o.hitR || 12);
  const size = (b) => (b.length || 0) < 0.5 ? 8 * k : R;
  let seg = '', tips = '', rings = '', aims = '';

  for (const b of list) {
    const len = b.length || 0;
    if (len < 0.5) continue;
    const rad = (b.rotation || 0) * Math.PI / 180;
    const ux = Math.cos(rad), uy = -Math.sin(rad);
    const nx = -uy, ny = ux;
    const ex = b.x + ux * len, ey = b.y + uy * len;
    const ws = Math.min(9.5 * k, Math.max(4 * k, len * 0.14));
    const we = Math.max(1 * k, Math.min(2 * k, len * 0.045));
    const pts = [[b.x + nx * ws, b.y + ny * ws], [b.x - nx * ws, b.y - ny * ws],
                 [ex - nx * we, ey - ny * we], [ex + nx * we, ey + ny * we]]
      .map(q => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' ');
    const cls = 'sk-seg' + (b.sel ? ' sel' : '') + (b.aim != null ? ' aimed' : '');
    seg += '<polygon class="' + cls + '" data-seg="' + b.index + '" points="' + pts +
           '" fill="' + BONE_COLOR + '" stroke="' + BONE_COLOR + '"/>';
  }

  for (const b of list) {
    const len = b.length || 0;
    if (len < 0.5) continue;
    const rad = (b.rotation || 0) * Math.PI / 180;
    const ex = +(b.x + Math.cos(rad) * len).toFixed(1);
    const ey = +(b.y - Math.sin(rad) * len).toFixed(1);
    if (b.aim != null) {
      const s = 5 * k;
      aims += '<rect class="sk-aim-mark" x="' + (ex - s).toFixed(1) + '" y="' + (ey - s).toFixed(1) +
              '" width="' + (2 * s).toFixed(1) + '" height="' + (2 * s).toFixed(1) +
              '" transform="rotate(45 ' + ex + ' ' + ey + ')" fill="#fff" stroke="' + BONE_COLOR +
              '" stroke-width="1.6" stroke-dasharray="3 2">' +
              '<title>末端对准 #' + b.aim + ' 的原点</title></rect>';
      continue;
    }
    tips += '<circle class="sk-tip-hit' + (b.sel ? ' sel' : '') + '" data-tip="' + b.index +
            '" cx="' + ex + '" cy="' + ey + '" r="' + grab + '" fill="none"/>' +
            '<circle class="sk-tip" cx="' + ex + '" cy="' + ey + '" r="' + (5.5 * k).toFixed(1) +
            '" fill="#fff" stroke="' + BONE_COLOR + '" stroke-width="2"/>';
  }

  for (const b of list) {
    rings += '<circle class="sk-ring' + ((b.length || 0) < 0.5 ? ' zero' : '') +
             (b.sel ? ' sel' : '') + '" data-ring="' + b.index + '" cx="' + b.x + '" cy="' + b.y +
             '" r="' + size(b) + '" fill="#fff" stroke="' + BONE_COLOR + '">' +
             (o.title ? '<title>#' + b.index + (b.role ? ' ' + b.role : '') +
               ((b.length || 0) < 0.5 ? '（零长 · 控制骨）' : '（长 ' + Math.round(b.length) + 'px）') +
               (b.aim != null ? ' → #' + b.aim : '') + '</title>' : '') + '</circle>';
  }

  const s = list.find(b => b.sel);
  const core = s
    ? '<circle class="sk-core" cx="' + s.x + '" cy="' + s.y + '" r="' +
      ((s.length || 0) < 0.5 ? 3 * k : 4.5 * k) + '" fill="' + BONE_COLOR + '"/>'
    : '';
  return seg + tips + rings + aims + core;
}

function skSvgHtml(bones) {
  return boneShapeSvg(withSel(bones), { r: 14, hitR: 14, title: true });
}

function boneRowHtml(b) {
  const i = b.index, sel = BONE_SEL === i;
  return '<div class="sk-row' + (sel ? ' sel' : '') + '" data-i="' + i + '">' +
    '<div class="sk-hd" data-i="' + i + '">' +
      '<span class="sk-idx">#' + i + '</span>' +
      '<span class="sk-role">' + (b.role || '') + '</span>' +
    '</div>' +
  '</div>';
}

const BONE_SECS = [[0, 4, '躯干'], [5, 7, '左手'], [8, 10, '右手'], [11, 13, '左腿'], [14, 16, '右腿']];

function boneListHtml(list) {
  if (!list.length) return '<div class="empty">没有骨骼</div>';
  const rest = list.slice();
  let out = '';
  const secs = BONE_SECS.slice();
  secs.push([null, null, '其它']);
  for (const [a, b, name] of secs) {
    const rows = a == null ? rest : rest.filter(x => x.index >= a && x.index <= b);
    if (!rows.length) continue;
    for (const r of rows) rest.splice(rest.indexOf(r), 1);
    out += '<div class="sk-gap"></div><div class="sk-sec">' + name + '</div>' +
      rows.map(boneRowHtml).join('');
  }
  return out;
}

function boneWire(box, onPick) {
  const keep = box.scrollTop;
  box.querySelectorAll('.sk-hd').forEach(el => {
    el.onclick = () => {
      BONE_SEL = +el.dataset.i;
      onPick();
    };
  });
  box.scrollTop = keep;
}

function boneViewAt(list, i) {
  return (list || []).find(b => b.index === +i) || null;
}

function boneHit(e) {
  const ring = e.target.closest('[data-ring]');
  if (ring) return { i: +ring.dataset.ring, mode: 'move' };
  const tip = e.target.closest('[data-tip]');
  if (tip) return { i: +tip.dataset.tip, mode: 'tip' };
  const seg = e.target.closest('[data-seg]');
  if (seg) return { i: +seg.dataset.seg, mode: 'seg' };
  return null;
}

function boneStep(s, pt) {
  const b = s.b, W = s.W, H = s.H;
  if (s.mode === 'move') {
    const lim = boneShift(b.x, b.y, b.rotation, b.length || 0, W, H);
    const tx = boxClamp(b.x + (pt[0] - s.prev[0]), lim[0], lim[1]);
    const ty = boxClamp(b.y + (pt[1] - s.prev[1]), lim[2], lim[3]);
    return { i: b.index, mode: 'move', b: b, tx: tx, ty: ty, dx: tx - b.x, dy: ty - b.y };
  }
  const dx = pt[0] - b.x, dy = pt[1] - b.y, dist = Math.hypot(dx, dy);
  if (dist < 1) return null;
  const wa = Math.atan2(-dy, dx) * 180 / Math.PI;
  const rot = s.mode === 'seg'
    ? boneFitRot(b.x, b.y, b.rotation, wa, b.length || 0, W, H) : wa;
  return { i: b.index, mode: s.mode, b: b, wa: wa, rot: rot, dist: dist,
           len: Math.max(0, Math.min(dist, boneReach(b.x, b.y, rot, W, H))) };
}

function boneDrag(svg, h) {
  let st = null;
  const at = i => boneViewAt(h.bones(), i);
  const map = e => {
    const [W, H] = h.extent();
    const r = svg.getBoundingClientRect();
    return [boxClamp((e.clientX - r.left) / r.width * W, 0, W),
            boxClamp((e.clientY - r.top) / r.height * H, 0, H)];
  };
  svg.onpointerdown = e => {
    st = null;
    if (h.busy()) return;
    const hit = boneHit(e);
    if (!hit) return;
    if (BONE_SEL !== hit.i) { h.hint(hit.i); return; }
    const b = at(hit.i);
    if (!b) return;
    if (b.aim != null && hit.mode !== 'move') {
      h.warn('#' + hit.i + ' 指向 #' + b.aim + '：长度和角度由指向决定，拖 #' + b.aim + ' 改它');
      return;
    }
    const [W, H] = h.extent();
    st = { i: hit.i, b: b, mode: hit.mode, prev: map(e), W: W, H: H, moved: false,
           ctx: h.begin(b, hit.mode) };
    svg.setPointerCapture(e.pointerId);
    e.preventDefault();
  };
  svg.onpointermove = e => {
    if (!st) return;
    const pt = map(e), g = boneStep(st, pt);
    if (!g) return;
    st.prev = pt;
    h.drag(g, st.ctx);
    st.b = at(st.i) || st.b;
    st.moved = true;
  };
  const drop = () => {
    if (!st) return;
    const s = st;
    st = null;
    h.drop(s.moved);
  };
  svg.onpointerup = drop;
  svg.onpointercancel = drop;
}

function skSubtree(rig, i) {
  const kids = {};
  (rig.bones || []).forEach(b => {
    const p = (b.parent == null ? -1 : +b.parent);
    (kids[p] = kids[p] || []).push(b.index);
  });
  const out = new Set([i]), stack = [i];
  while (stack.length) {
    const k = stack.pop();
    (kids[k] || []).forEach(j => { if (!out.has(j)) { out.add(j); stack.push(j); } });
  }
  return out;
}

function skReindex(rig) {
  const bones = rig.bones.slice().sort((a, b) => a.index - b.index);
  const old = bones.map(b => b.index);
  const map = {};
  old.forEach((o, n) => { map[o] = n; });
  bones.forEach((b, n) => {
    b.index = n;
    const par = (b.parent == null ? -1 : +b.parent);
    b.parent = (par >= 0 && map[par] != null) ? map[par] : -1;
    if (b.aim != null) {
      if (map[+b.aim] != null) b.aim = map[+b.aim];
      else delete b.aim;
    }
  });
  rig.bones = bones;
  const cal = rig.calib || {};
  const nc = {};
  for (const k in cal) {
    if (k === 'near') { nc[k] = cal[k]; continue; }
    const v = map[+k];
    if (v != null) nc[String(v)] = cal[k];
  }
  rig.calib = nc;
  return rig;
}

function skBone(i) {
  return (SK && SK.rig && (SK.rig.bones || []).find(x => x.index === +i)) || null;
}

function skSnap(w) {
  const m = {};
  for (const b of w) m[b.index] = { x: b.x, y: b.y, rotation: b.rotation };
  return m;
}

function skPin(rig, i, snap) {
  const w = skWorld(rig);
  const me = w.find(x => x.index === +i);
  if (!me) return;
  for (const c of (rig.bones || [])) {
    if ((c.parent == null ? -1 : +c.parent) !== +i) continue;
    const s = snap[c.index];
    if (!s) continue;
    const d = skToLocal(s.x - me.x, s.y - me.y, me.rotation);
    c.x = skR2(d[0]); c.y = skR2(d[1]);
    c.rotation = skR2(skWrap(s.rotation - me.rotation));
  }
}

function skAimOne(rig, i) {
  const b = (rig.bones || []).find(x => x.index === +i);
  if (!b || b.aim == null) return;
  const w = skWorld(rig);
  const me = w.find(x => x.index === b.index), t = w.find(x => x.index === +b.aim);
  if (!me || !t) return;
  const dx = t.x - me.x, dy = t.y - me.y;
  const len = Math.hypot(dx, dy);
  if (len < 0.5) return;
  const snap = skSnap(w);
  const pv = me.parent_index >= 0 ? w.find(x => x.index === me.parent_index) : null;
  b.length = skR2(len);
  b.rotation = skR2(skWrap(Math.atan2(-dy, dx) * 180 / Math.PI - (pv ? pv.rotation : 0)));
  skPin(rig, b.index, snap);
}

function skSyncAims(rig) {
  for (const b of (rig.bones || [])) {
    if (b.aim == null) continue;
    if (+b.aim === b.index || (b.length || 0) < 0.5) {
      delete b.aim;
      continue;
    }
    skAimOne(rig, b.index);
  }
}
