const KP_LIMB = [[1, 2], [2, 3], [3, 4], [1, 5], [5, 6], [6, 7], [1, 8], [8, 9], [9, 10],
                 [1, 11], [11, 12], [12, 13], [1, 0], [7, 14], [4, 15], [13, 16], [10, 17]];
const KPC = { R: '#e0475c', L: '#3d7dd6', C: '#d9a520', E: '#2f9d6a' };
const KPR = [2, 3, 4, 8, 9, 10, 15, 17], KPL = [5, 6, 7, 11, 12, 13, 14, 16];

function kpCol(a, b) {
  if (KPR.includes(a) || KPR.includes(b)) return KPC.R;
  if (KPL.includes(a) || KPL.includes(b)) return KPC.L;
  return KPC.C;
}

let MO = { list: [], sel: 0, keys: {}, act: 'walk', selFrames: [], roles: {}, auto: false,
           allFrames: false };
let moSaveT = null, kfSaveT = null;

function bonesAt(n) {
  if (MO.keys[n]) return { bones: MO.keys[n], hip: null };
  const f = MO.list.find(x => x.n === n);
  return f ? { bones: f.bones, hip: f.hip } : null;
}

function boneBones(n) {
  const f = bonesAt(n);
  return f ? f.bones : null;
}

function calibRel() {
  if (RT.crel) return RT.crel;
  const c = MO.calib || {}, out = {};
  for (const k in c) {
    if (k === 'near') continue;
    out[k] = c[k];
  }
  RT.crel = out;
  return out;
}

function bonePose(fr) {
  const rot = {}, scl = {}, off = {};
  if (!fr || !fr.bones) return { rot, scl, off, hipY: 0 };
  const cr = calibRel(), bones = fr.bones;
  for (const k in bones) {
    rot[k] = bones[k].r - (cr[k] || 0);
    const sc = +bones[k].s;
    if (sc > 0 && Math.abs(sc - 1) > 1e-4) scl[k] = sc;
    if (bones[k].x || bones[k].y) off[k] = [+bones[k].x || 0, +bones[k].y || 0];
  }
  const hipY = (fr.hip && MO.hipMed !== undefined) ? MO.hipMed - fr.hip[1] : 0;
  return { rot, scl, off, hipY };
}

async function loadMotion() {
  const box = $('#mobody'), shots = $('#moshots'), hint = $('#mohint');
  if (!DIR || !state || !state.case) {
    box.innerHTML = '<div class="empty">先选案例目录。</div>';
    shots.innerHTML = '';
    hint.textContent = '—';
    return;
  }
  hint.textContent = '读取中…';
  let m;
  try { m = await (await fetch('/api/motion' + qs())).json(); }
  catch (e) { box.innerHTML = `<div class="empty">读取失败：${e}</div>`; hint.textContent = '—'; return; }

  MO.list = m.frames_list || [];
  MO.keys = m.keys || {};
  MO.auto = !!((m.framesheet || {}).auto);
  MO.calib = m.calib || {};
  MO.meta = m.meta || {};
  MO.scale = m.scale || 1;
  const hs = MO.list.map(f => (f.hip ? f.hip[1] : null)).filter(v => v !== null);
  hs.sort((a, b) => a - b);
  MO.hipMed = hs.length ? hs[Math.floor(hs.length / 2)] : undefined;
  RT.crel = null;
  RT.anchor = null;
  MO.act = m.act || 'walk';
  MO.selFrames = (m.keyframes || []).slice();
  MO.allFrames = false;
  if (!MO.auto && !MO.selFrames.length && MO.list.length) {
    MO.selFrames = MO.list.map(f => f.n);
    MO.allFrames = true;
  }
  MO.fps = m.fps || 24;
  MO.roles = m.roles || {};
  MO.near = m.near || 'L';
  MO.limits = m.limits || { knee: 45, arm: 24, lean: 9 };
  MO.calib = m.calib || null;
  if (!MO.selFrames.includes(MO.sel)) MO.sel = MO.selFrames.length ? MO.selFrames[0] : 0;
  RT.anchor = null;
  RT.stats = null;

  const k = (label, val, unit) =>
    `<div class="mo-k"><b>${label}</b><span>${val}</span>${unit ? `<em>${unit}</em>` : ''}</div>`;
  box.innerHTML = [
    k('源视频', m.clip ? m.clip.split('/').pop() : '—'),
    k('抽帧', m.frames || '—', '帧'),
    k('已手改', Object.keys(MO.keys).length, '帧'),
    k('动画', m.rig ? '已生成' : '未生成'),
  ].join('');
  hint.textContent = `${MO.list.length} 帧 · 点一下加入关键帧（红框），再点移出`;
  renderShots();
  renderSelFrames();
  renderKeyEditor();
  renderFramePreview();
}


const LP = { frames: [], poses: [], times: [], fps: 24, dur: 0, t: 0, playing: false, raf: 0, last: 0 };

function loopGaps(seq) {
  const pos = [];
  for (let i = 1; i < seq.length; i++) {
    const d = seq[i] - seq[i - 1];
    if (d > 0) pos.push(d);
  }
  pos.sort((a, b) => a - b);
  const step = pos.length ? pos[pos.length >> 1] : 1;
  const out = [];
  for (let i = 1; i < seq.length; i++) {
    const d = seq[i] - seq[i - 1];
    out.push(d > 0 ? d : step);
  }
  return out;
}

function loopStep(gaps) {
  if (!gaps.length) return 1;
  const s = gaps.slice().sort((a, b) => a - b);
  return s[s.length >> 1];
}

function lpBuild() {
  const fr = (MO.selFrames || []).slice();
  LP.frames = fr;
  LP.fps = MO.fps || 24;
  LP.poses = fr.map(n => poseBones(bonesAt(n)));
  const gaps = loopGaps(fr);
  const step = loopStep(gaps);
  LP.times = [0];
  gaps.forEach(g => LP.times.push(LP.times[LP.times.length - 1] + g / LP.fps));
  if (LP.poses.length > 1) {
    const a = LP.poses[0];
    LP.poses.push({ rot: Object.assign({}, a.rot), hipY: a.hipY });
    LP.times.push(LP.times[LP.times.length - 1] + step / LP.fps);
  }
  LP.dur = LP.times[LP.times.length - 1] || 0;
  LP.t = LP.dur > 0 ? ((LP.t % LP.dur) + LP.dur) % LP.dur : 0;
  const cv = $('#lpcanvas');
  const f = MO.list.find(x => x.n === fr[0]);
  const W = f ? (f.w || 640) : 640, H = f ? (f.h || 640) : 640;
  if (cv.width !== W || cv.height !== H) {
    cv.width = W;
    cv.height = H;
  }
}

function lpPoseAt(t) {
  const P = LP.poses, T = LP.times;
  if (!P.length) return null;
  if (P.length === 1 || LP.dur <= 0) return P[0];
  const tt = ((t % LP.dur) + LP.dur) % LP.dur;
  let i = 0;
  while (i < T.length - 2 && T[i + 1] <= tt) i++;
  const t0 = T[i], t1 = T[i + 1];
  const u = t1 > t0 ? Math.min(1, Math.max(0, (tt - t0) / (t1 - t0))) : 0;
  const a = P[i], b = P[i + 1];
  const rot = {};
  for (const k in a.rot) {
    const v0 = a.rot[k];
    const v1 = (k in b.rot) ? b.rot[k] : v0;
    rot[k] = v0 + wrap180(v1 - v0) * u;
  }
  return { rot, hipY: a.hipY + (b.hipY - a.hipY) * u };
}

function lpShow() {
  const st = lpPoseAt(LP.t);
  const n = rtPaint($('#lpcanvas'), st, 1);
  let k = 0;
  while (k < LP.times.length - 2 && LP.times[k + 1] <= LP.t) k++;
  const cur = LP.frames[k] || 0;
  $('#lphint').textContent = LP.frames.length
    ? LP.frames.length + ' 个关键帧 · ' + LP.fps.toFixed(2) + ' fps · 时长 ' + LP.dur.toFixed(3)
      + 's · 第 ' + (k + 1) + '/' + LP.frames.length + ' 张（素材 ' + cur + '）'
    : '还没选关键帧';
  $('#lpNote').textContent = LP.frames.length ? n + ' 个部件' : '';
  return n;
}

function lpSync() {
  const panel = $('#panelLoop');
  if (!MO.selFrames || !MO.selFrames.length) {
    panel.hidden = true;
    lpPlay(false);
    return;
  }
  panel.hidden = false;
  if (RT.skel && rtAnchor()) {
    lpBuild();
    lpShow();
    return;
  }
  rtLoad().then(err => {
    if (err || !rtAnchor()) {
      $('#lphint').textContent = err || '骨架摆不出来';
      return;
    }
    lpBuild();
    lpShow();
  });
}

function lpPlay(on) {
  LP.playing = on;
  $('#lpPlay').textContent = on ? '暂停' : '播放';
  $('#lpPlay').classList.toggle('on', on);
  if (LP.raf) {
    cancelAnimationFrame(LP.raf);
    LP.raf = 0;
  }
  if (on) {
    gbPlay(false);
    LP.last = 0;
    LP.raf = requestAnimationFrame(lpTick);
  }
}

function lpTick(ts) {
  if (!LP.playing) return;
  if (!LP.last) LP.last = ts;
  const dt = Math.min(0.2, (ts - LP.last) / 1000);
  LP.last = ts;
  if (LP.dur > 0) LP.t = (LP.t + dt) % LP.dur;
  lpShow();
  LP.raf = requestAnimationFrame(lpTick);
}

function lpStep(d) {
  lpPlay(false);
  if (!LP.frames.length) return;
  if (LP.dur <= 0) {
    LP.t = 0;
  } else {
    const fps = LP.fps || 24;
    LP.t = (((LP.t + d / fps) % LP.dur) + LP.dur) % LP.dur;
  }
  lpShow();
}

function initLoop() {
  $('#lpPlay').onclick = () => lpPlay(!LP.playing);
  $('#lpPrev').onclick = () => lpStep(-1);
  $('#lpNext').onclick = () => lpStep(1);
}


const GB = { seq: [], urls: [], holds: [], idx: 0, playing: false, raf: 0, last: 0, until: 0 };

function gbFlash(text) {
  $('#gbMsg').textContent = text || '';
}

function gbAutoSync() {
  $('#gbAutoToggle').classList.toggle('on', !!MO.auto);
}

function gbSync() {
  const panel = $('#panelGif');
  const sel = (MO.selFrames || []).slice();
  if (!sel.length) {
    panel.hidden = !MO.list.length;
    gbPlay(false);
    GB.seq = [];
    GB.urls = [];
    GB.holds = [];
    GB.idx = 0;
    const im = $('#gbimg');
    im.removeAttribute('src');
    im.dataset.n = '';
    $('#gbstage').hidden = true;
    $('#gbPlay').disabled = true;
    $('#gbPrev').disabled = true;
    $('#gbNext').disabled = true;
    $('#gbhint').textContent = MO.list.length
      ? '还没选关键帧 —— 在动补里点缩略图，或直接「自动挑帧」'
      : '还没抽帧';
    return;
  }
  panel.hidden = false;
  $('#gbstage').hidden = false;
  $('#gbPlay').disabled = false;
  $('#gbPrev').disabled = false;
  $('#gbNext').disabled = false;
  GB.seq = sel;
  GB.holds = loopGaps(sel);
  GB.urls = sel.map(n => {
    const f = MO.list.find(x => x.n === n);
    return f ? '/api/file?p=' + encodeURIComponent(f.path) + '&dir=' + encodeURIComponent(DIR) : '';
  });
  const at = GB.seq.indexOf(MO.sel);
  GB.idx = at >= 0 ? at : Math.min(GB.idx, GB.seq.length - 1);
  gbShow();
}

function gbHold(i) {
  const g = GB.holds;
  const fps = MO.fps || 24;
  if (!g.length) return 1 / fps;
  return Math.max(1 / 120, (i < g.length ? g[i] : loopStep(g)) / fps);
}

function gbShow() {
  const n = GB.seq.length;
  if (!n) return;
  GB.idx = ((GB.idx % n) + n) % n;
  const im = $('#gbimg'), tag = String(GB.seq[GB.idx]);
  if (im.dataset.n !== tag) {
    im.src = GB.urls[GB.idx];
    im.dataset.n = tag;
  }
  let total = 0;
  for (let i = 0; i < n; i++) total += gbHold(i);
  $('#gbhint').textContent = n + ' 张 · 第 ' + (GB.idx + 1) + '/' + n
    + ' 张（素材 ' + GB.seq[GB.idx] + '）· 这张 ' + gbHold(GB.idx).toFixed(3)
    + 's · 合计 ' + total.toFixed(3) + 's';
  gbBones();
}

function gbPlay(on) {
  GB.playing = on;
  $('#gbPlay').textContent = on ? '暂停' : '播放';
  $('#gbPlay').classList.toggle('on', on);
  if (GB.raf) {
    cancelAnimationFrame(GB.raf);
    GB.raf = 0;
  }
  if (on && GB.seq.length) {
    lpPlay(false);
    GB.last = 0;
    GB.until = gbHold(GB.idx);
    GB.raf = requestAnimationFrame(gbTick);
    return;
  }
  const at = GB.seq.indexOf(MO.sel);
  if (at >= 0) {
    GB.idx = at;
    gbShow();
  }
}

function gbTick(ts) {
  if (!GB.playing) return;
  if (!GB.last) GB.last = ts;
  const dt = Math.min(0.5, (ts - GB.last) / 1000);
  GB.last = ts;
  GB.until -= dt;
  if (GB.until <= 0) {
    GB.idx = (GB.idx + 1) % GB.seq.length;
    gbShow();
    GB.until = gbHold(GB.idx);
  }
  GB.raf = requestAnimationFrame(gbTick);
}

function gbStep(d) {
  gbPlay(false);
  if (!GB.seq.length) return;
  GB.idx = (GB.idx + d + GB.seq.length) % GB.seq.length;
  gbShow();
  editFrame(GB.seq[GB.idx]);
}

function initGif() {
  initGbDrag();
  $('#gbPlay').onclick = () => gbPlay(!GB.playing);
  $('#gbPrev').onclick = () => gbStep(-1);
  $('#gbNext').onclick = () => gbStep(1);
}

function shotsBox() {
  return $('#moshots');
}

function renderSelFrames() {
  const panel = $('#panelSel'), box = $('#selframes'), hint = $('#selhint');
  panel.hidden = !MO.list.length;
  const sel = (MO.selFrames || []).map(n => MO.list.find(f => f.n === n)).filter(Boolean);
  if (sel.length && !sel.some(f => f.n === MO.sel)) MO.sel = sel[0].n;
  gbAutoSync();
  $('#selAutoHint').textContent = MO.auto
    ? '脚本按周期挑的 · 手点缩略图不生效'
    : '手动模式 · 点上面的缩略图增删';
  shotsBox().classList.toggle('lock', MO.auto);
  hint.textContent = MO.allFrames
    ? `全部 ${sel.length} 帧（没挑帧 = 逐帧全量）· 点缩略图可以去掉某帧`
    : (sel.length
      ? `${sel.length} 个关键帧 · 按播放顺序 · 绿圈 = 正在编辑（蓝框 = 手改过）· 换帧用下面的「关键帧动画预览」`
      : (MO.auto ? '自动挑帧没挑出帧（看日志）' : '还没选关键帧 —— 在上面点缩略图挑'));
  box.innerHTML = sel.length ? sel.map(f => {
    const cls = [MO.keys[f.n] ? 'edited' : '', f.n === MO.sel ? 'cur' : ''].filter(Boolean).join(' ');
    return `<figure data-n="${f.n}" class="${cls}">`
      + `<img src="/api/file?p=${encodeURIComponent(f.path)}&dir=${encodeURIComponent(DIR)}"`
      + ` loading="lazy" alt=""><figcaption>${f.n}</figcaption></figure>`;
  }).join('') : '<div class="empty" style="grid-column:1/-1">还没选关键帧。</div>';
  gbSync();
  lpSync();
}

function useAsFirst() {
  const seq = (MO.selFrames || []).slice();
  const n0 = GB.seq[GB.idx];
  if (!n0 || seq.length < 3 || seq.indexOf(n0) < 0) {
    gbFlash('先用「自动挑帧」挑出关键帧，再用「上一张 / 下一张」走到想当首帧的那张');
    return;
  }
  const k = seq.indexOf(n0);
  const rot = seq.slice(k).concat(seq.slice(0, k));
  MO.selFrames = rot;
  MO.sel = n0;
  GB.idx = 0;
  saveKeyframes();
  renderShots();
  renderSelFrames();
  renderKeyEditor();
  renderFramePreview();
  gbFlash('首帧换成第 ' + n0 + ' 帧，只重排顺序：' + rot.join(' → ') + ' → 回到 ' + n0);
}

function initSel() {
  $('#selFirst').onclick = useAsFirst;
  $('#gbAutoToggle').onclick = async () => {
    const btn = $('#gbAutoToggle'), on = !MO.auto;
    btn.disabled = true;
    gbFlash(on ? '自动挑帧中…' : '切到手动模式…');
    try {
      await setAutoFrames(on);
    } catch (err) {
      log('自动挑帧失败：' + (err && err.message ? err.message : err), 'err');
      gbFlash('自动挑帧失败，看日志');
    } finally {
      btn.disabled = false;
    }
  };
  $('#gbAuto').onclick = async () => {
    gbFlash('重挑中…');
    $('#gbAuto').disabled = true;
    try {
      await setAutoFrames(true);
    } catch (e) {
      log('自动挑帧失败：' + (e && e.message ? e.message : e), 'err');
      gbFlash('自动挑帧失败，看日志');
    } finally {
      $('#gbAuto').disabled = false;
    }
  };
}

async function setAutoFrames(on) {
  const r = await postJSON('/api/autokeys',
    { dir: DIR, action: MO.act, auto: on, frames: on ? null : (MO.selFrames || []) });
  if (r.log) log(r.log, r.ok ? 'cmd' : 'err');
  MO.auto = !!r.auto;
  if (r.frames) MO.selFrames = r.frames.slice();
  MO.allFrames = false;
  if (!MO.auto && !MO.selFrames.length && MO.list.length) {
    MO.selFrames = MO.list.map(f => f.n);
    MO.allFrames = true;
  }
  renderShots();
  renderSelFrames();
  renderKeyEditor();
  renderFramePreview();
  gbFlash(on ? '自动挑帧已开：脚本每跑一次就重挑' : '自动挑帧已关：可以手动增删关键帧');
}

function saveKeyframes() {
  clearTimeout(kfSaveT);
  kfSaveT = setTimeout(() => {
    postJSON('/api/keyframes', { dir: DIR, action: MO.act, frames: MO.selFrames });
  }, 300);
}

function renderShots() {
  const box = $('#moshots');
  if (!MO.list.length) {
    box.innerHTML = '<div class="empty" style="grid-column:1/-1">还没有抽帧（跑「抽帧」）。</div>';
    return;
  }
  box.innerHTML = MO.list.map(f => {
    const cls = MO.selFrames.includes(f.n) ? 'on' : '';
    return `<figure data-n="${f.n}" class="${cls}">`
      + `<img src="/api/file?p=${encodeURIComponent(f.path)}&dir=${encodeURIComponent(DIR)}"`
      + ` loading="lazy" alt=""><figcaption>${f.n}</figcaption></figure>`;
  }).join('');
  box.querySelectorAll('figure').forEach(el => {
    el.onclick = () => toggleKeyframe(+el.dataset.n);
  });
}

function toggleKeyframe(n) {
  if (MO.auto) {
    gbFlash('自动挑帧开着 —— 先关掉开关才能手动增删');
    return;
  }
  const seq = MO.selFrames;
  MO.allFrames = false;
  if (seq.indexOf(n) >= 0) {
    MO.selFrames = seq.filter(v => v !== n);
  } else {
    MO.selFrames = seq.concat([n]);
  }
  saveKeyframes();
  renderShots();
  renderSelFrames();
  renderKeyEditor();
  renderFramePreview();
}

function editFrame(n) {
  MO.sel = n;
  renderSelFrames();
  renderKeyEditor();
  renderFramePreview();
}

function boneJoints(fr) {
  const a = rtAnchor();
  if (!a || !RT.skel || !fr || !fr.bones) return null;
  rtApplySt(poseBones(fr));
  const meta = MO.meta || {};
  const out = {};
  for (const k in fr.bones) {
    const b = RT.skel.bones[+k];
    if (!b) continue;
    const L = +((meta[k] || {}).l || 0) * a.s * (+((fr.bones[k] || {}).s || 1));
    const x = a.s * b.worldX + a.tx, y = -a.s * b.worldY + a.ty;
    const rad = b.getWorldRotationX() * Math.PI / 180;
    out[k] = { p: [x, y], q: [x + L * Math.cos(rad), y - L * Math.sin(rad)] };
  }
  return out;
}

function keBoneList(fr) {
  const j = boneJoints(fr);
  if (!j) return null;
  const meta = MO.meta || {};
  const out = [];
  for (const k in j) {
    const m = meta[k] || {};
    const dx = j[k].q[0] - j[k].p[0], dy = j[k].q[1] - j[k].p[1];
    const len = Math.hypot(dx, dy);
    out.push({ index: +k, x: j[k].p[0], y: j[k].p[1],
               rotation: len < 0.5 ? 0 : Math.atan2(-dy, dx) * 180 / Math.PI,
               length: len, parent_index: (m.p == null ? -1 : +m.p),
               side: m.s || 'front', role: m.r,
               aim: m.a == null ? null : +m.a, zero: len < 0.5 });
  }
  return out.sort((a, b) => a.index - b.index);
}

function metaBoneList() {
  const meta = MO.meta || {};
  const out = [];
  for (const k in meta) {
    const m = meta[k];
    const len = +(m.l || 0);
    out.push({ index: +k, x: 0, y: 0, rotation: 0, length: len,
               parent_index: (m.p == null ? -1 : +m.p), side: m.s || 'front',
               role: m.r, aim: m.a == null ? null : +m.a, zero: !(len >= 0.5) });
  }
  return out.sort((a, b) => a.index - b.index);
}

function keSvg(fr, W) {
  const list = keBoneList(fr);
  if (!list) return '';
  const k = Math.max(0.55, (W || 640) / 1024);
  return boneShapeSvg(withSel(list), { r: 14 * k, hitR: 16 * k });
}

function keName(idx) {
  const m = MO.roles || {};
  for (const k in m) if (m[k] === +idx) return k;
  return '#' + idx;
}

function keHint(i) {
  const b = metaBoneList().find(x => x.index === i);
  gbFlash('先在右边列表里点 #' + i + (b && b.role ? ' ' + b.role : '') + ' 选中，再在图上拖');
}

function renderKeList() {
  const box = $('#gbones');
  if (!box) return;
  const list = metaBoneList();
  if (BONE_SEL != null && !list.some(b => b.index === BONE_SEL)) BONE_SEL = null;
  box.innerHTML = boneListHtml(list);
  boneWire(box, renderKeyEditor);
}

function keFrame() {
  const n = GB.seq.length ? GB.seq[Math.max(0, Math.min(GB.idx, GB.seq.length - 1))] : MO.sel;
  return MO.list.find(x => x.n === n) || null;
}

function gbBones() {
  const svg = $('#gbsvg');
  const f = keFrame();
  if (!f) { svg.innerHTML = ''; return; }
  const W = f.w || 640, H = f.h || 640;
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.innerHTML = keSvg(bonesAt(f.n), W);
}

function renderKeyEditor() {
  renderKeList();
  gbBones();
  gbShow();
}

function keAimTo(row, i, tx, ty, pin) {
  const meta = MO.meta || {};
  const mp = meta[i] || {};
  const p = mp.p;
  if (p == null || p < 0) return;
  if (+((meta[p] || {}).a) !== +i) return;
  const f = MO.list.find(x => x.n === MO.sel);
  const fr = { bones: row, hip: f && f.hip };
  const before = boneJoints(fr);
  if (!before || !before[p] || !before[i]) return;
  const as = (rtAnchor() || { s: 1 }).s;
  const ox = before[p].p[0], oy = before[p].p[1];
  const dx = tx - ox, dy = ty - oy;
  const L = Math.hypot(dx, dy) / as;
  if (L < 1) return;
  const wNow = Math.atan2(-(before[p].q[1] - oy), before[p].q[0] - ox) * 180 / Math.PI;
  const wWant = Math.atan2(-dy, dx) * 180 / Math.PI;
  const cp = Object.assign({}, row[p]);
  cp.r = Math.round(wrap180((+cp.r || 0) + wrap180(wWant - wNow)) * 100) / 100;
  cp.s = Math.round(Math.max(0.2, Math.min(5, L / (+((meta[p] || {}).l) || 1))) * 1000) / 1000;
  row[p] = cp;
  const ci = Object.assign({}, row[i]);
  ci.x = Math.round((((+((meta[p] || {}).l) || 0) - (+mp.x || 0))) * 100) / 100;
  ci.y = Math.round(-(+(mp.y) || 0) * 100) / 100;
  row[i] = ci;
  if (pin === false) return;
  const kids = Object.keys(meta).filter(k => +(meta[k].p) === +i).map(Number);
  if (!kids.length) return;
  const after = boneJoints(fr);
  if (!after || !after[i]) return;
  const wI = Math.atan2(-(after[i].q[1] - after[i].p[1]), after[i].q[0] - after[i].p[0]) * 180 / Math.PI;
  for (const c of kids) {
    const s0 = before[c] && before[c].p, s1 = after[c] && after[c].p;
    if (!s0 || !s1) continue;
    const cc = Object.assign({}, row[c]);
    const dl = skToLocal((s0[0] - s1[0]) / as, (s0[1] - s1[1]) / as, wI);
    cc.x = Math.round(((+cc.x || 0) + dl[0] / (+cc.s || 1)) * 100) / 100;
    cc.y = Math.round(((+cc.y || 0) + dl[1] / (+cc.s || 1)) * 100) / 100;
    row[c] = cc;
  }
}

function keBegin(b) {
  const meta = MO.meta || {};
  const fr = bonesAt(MO.sel) || { bones: {} };
  const a = rtAnchor();
  const as = a ? a.s : 1;
  const sOf = k => +(((MO.keys[MO.sel] || {})[k] || fr.bones[k] || {}).s) || 1;
  const bone = RT.skel && RT.skel.bones[b.index];
  const par = bone && bone.parent;
  const pIdx = (meta[b.index] || {}).p;
  return { as: as,
           unit: as * (+((meta[b.index] || {}).l) || 0),
           pw: par ? par.getWorldRotationX() : 0,
           wi: bone ? bone.getWorldRotationX() : 0,
           ps: (pIdx != null && pIdx >= 0) ? sOf(pIdx) : 1,
           si: sOf(b.index),
           aim: (pIdx != null && pIdx >= 0) && +((meta[pIdx] || {}).a) === +b.index,
           kids: Object.keys(meta).filter(k => +(meta[k].p) === b.index).map(Number) };
}

function keCommit(row) {
  MO.keys[MO.sel] = row;
  gbBones();
  renderSelFrames();
  renderFramePreview();
  clearTimeout(moSaveT);
  moSaveT = setTimeout(() => {
    postJSON('/api/keys', { dir: DIR, action: MO.act, frame: MO.sel, bones: row });
  }, 400);
}

function keDrag(g, c) {
  const base = bonesAt(MO.sel) || { bones: {} };
  const row = Object.assign({}, MO.keys[MO.sel] || base.bones);
  if (g.mode === 'move') {
    if (c.aim) {
      keAimTo(row, g.i, g.tx, g.ty);
      return keCommit(row);
    }
    const dx = g.dx / c.as, dy = g.dy / c.as;
    const pb = RT.skel.bones[g.i] && RT.skel.bones[g.i].parent;
    const cur = Object.assign({}, row[g.i] || base.bones[g.i] || {});
    const dl = skToLocal(dx, dy, pb ? pb.getWorldRotationX() : c.pw);
    cur.x = Math.round(((+(cur.x) || 0) + dl[0] / c.ps) * 100) / 100;
    cur.y = Math.round(((+(cur.y) || 0) + dl[1] / c.ps) * 100) / 100;
    if (cur.s === undefined) cur.s = 1;
    row[g.i] = cur;
    for (const k of c.kids) {
      const cc = Object.assign({}, row[k] || base.bones[k] || {});
      const dcl = skToLocal(dx, dy, c.wi);
      cc.x = Math.round(((+(cc.x) || 0) - dcl[0] / c.si) * 100) / 100;
      cc.y = Math.round(((+(cc.y) || 0) - dcl[1] / c.si) * 100) / 100;
      if (cc.s === undefined) cc.s = 1;
      row[k] = cc;
    }
  } else {
    const cur = Object.assign({}, row[g.i] || {});
    if (cur.s === undefined) cur.s = 1;
    cur.r = Math.round(skWrap(g.rot - c.pw) * 100) / 100;
    if (g.mode === 'tip' && c.unit > 0.5) {
      cur.s = Math.round(Math.max(0.25, Math.min(4, g.len / c.unit)) * 1000) / 1000;
    }
    row[g.i] = cur;
  }
  keCommit(row);
}

function initGbDrag() {
  boneDrag($('#gbsvg'), {
    busy: () => GB.playing,
    extent: () => {
      const f = keFrame();
      return [f ? (f.w || 640) : 640, f ? (f.h || 640) : 640];
    },
    bones: () => {
      const f = keFrame();
      return f ? (keBoneList(bonesAt(f.n)) || []) : [];
    },
    hint: keHint,
    warn: gbFlash,
    begin: keBegin,
    drag: keDrag,
    drop: () => {}
  });
}
