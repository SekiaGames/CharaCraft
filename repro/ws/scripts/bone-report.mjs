import fs from 'fs';
import path from 'path';
import vm from 'vm';
import { createCanvas, loadImage } from '@napi-rs/canvas';

const STUDIO = path.resolve(import.meta.dirname, '../../studio');
const WS = path.resolve(import.meta.dirname, '..');

const argv = process.argv.slice(2);
const opt = (name, dflt) => {
  const i = argv.indexOf('--' + name);
  return i >= 0 ? argv[i + 1] : dflt;
};
const CASE = argv[0] || '/Volumes/Data/CharaCraft/Roxy';
const ACT = opt('act', 'idle');
const FRAME = +opt('frame', 81);
const BONE = opt('bone', null);
const PNG = opt('png', null);

function stub() {
  return {
    innerHTML: '', textContent: '', value: '', style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    appendChild(c) { return c; }, setAttribute() {}, getAttribute() { return null; },
    addEventListener() {}, querySelector: () => stub(), querySelectorAll: () => [],
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 640, height: 640 })
  };
}

const nodes = {};
const sandbox = {
  console, Math, JSON, Object, Array, String, Number, Boolean, Map, Set, Date,
  Float32Array, Int32Array, Uint8Array, Uint16Array, Uint8ClampedArray, Promise,
  setTimeout, clearTimeout, performance, URLSearchParams, isNaN, parseInt, parseFloat,
  document: {
    querySelector: s => (nodes[s] = nodes[s] || stub()),
    querySelectorAll: () => [],
    createElement: t => (t === 'canvas' ? createCanvas(4, 4) : stub()),
    documentElement: { style: { setProperty() {} } }, body: stub()
  },
  location: { search: '' },
  Image: class { constructor() {} },
  ResizeObserver: class { observe() {} unobserve() {} disconnect() {} },
  requestAnimationFrame: () => 0,
  navigator: { userAgent: 'node' },
  fetch: async () => { throw new Error('bone-report 不联网'); }
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
const ctx = vm.createContext(sandbox);
const run = code => vm.runInContext(code, ctx);

const spineFile = path.join(WS, 'node_modules/@esotericsoftware/spine-core/dist/iife/spine-core.min.js');
vm.runInContext(fs.readFileSync(spineFile, 'utf8'), ctx, { filename: 'spine-core.js' });
for (const f of ['core.js', 'bones.js', 'motion.js', 'rt.js']) {
  vm.runInContext(fs.readFileSync(path.join(STUDIO, 'js', f), 'utf8'), ctx, { filename: f });
}

function atlasName() {
  const dir = path.join(CASE, 'output');
  const f = fs.readdirSync(dir).find(n => n.endsWith('.atlas'));
  if (!f) throw new Error('output 里没有 .atlas');
  return f;
}

async function build() {
  const spine = ctx.spine;
  const rigFile = path.join(CASE, 'base/rig', ACT + '.json');
  const rig = JSON.parse(fs.readFileSync(rigFile, 'utf8'));
  const atlasFile = atlasName();
  const atlasText = fs.readFileSync(path.join(CASE, 'output', atlasFile), 'utf8');
  const data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(atlasText))).readSkeletonData(rig);
  const skeleton = new spine.Skeleton(data);
  const cfg = JSON.parse(fs.readFileSync(path.join(STUDIO, '../config/skeleton.json'), 'utf8'));
  for (const b of cfg.bones) {
    const d = data.bones[b.index];
    if (!d) continue;
    d.x = +b.x; d.y = +b.y; d.rotation = +b.rotation; d.length = +(b.length || 0);
  }
  const pages = {};
  const lines = atlasText.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i] || lines[i][0] === ' ' || !(lines[i + 1] || '').startsWith('size:')) continue;
    const p = path.join(CASE, 'output', lines[i]);
    if (!fs.existsSync(p)) continue;
    const img = await loadImage(p);
    pages[lines[i]] = { img, w: img.width, h: img.height };
  }
  return { data, skeleton, pages };
}

const { data, skeleton, pages } = await build();

const clipDir = path.join(CASE, 'clip-' + ACT);
const dw = JSON.parse(fs.readFileSync(path.join(clipDir, 'dwpose_bones.json'), 'utf8'));
const shots = fs.readdirSync(path.join(clipDir, 'frames')).filter(n => /^f_\d+\.png$/.test(n)).sort();
const cfg = JSON.parse(fs.readFileSync(path.join(STUDIO, '../config/skeleton.json'), 'utf8'));

const roles = {};
const meta = {};
for (const b of cfg.bones) {
  if (b.role) roles[b.role] = b.index;
  meta[String(b.index)] = {
    p: b.parent === undefined ? -1 : b.parent, l: +(b.length || 0),
    x: +(b.x || 0), y: +(b.y || 0), r: b.role, s: b.side || 'front',
    a: b.aim === undefined ? null : b.aim
  };
}

const payload = {
  frames_list: shots.map((name, i) => {
    const src = dw.frames[i] || {};
    return {
      n: i + 1, name, path: path.join(clipDir, 'frames', name),
      w: (src.size || [0, 0])[0], h: (src.size || [0, 0])[1],
      hip: src.hip, bones: src.bones || {}
    };
  }),
  scale: dw.scale, roles, meta, calib: cfg.calib,
  limits: { knee: 45, arm: 24, lean: 9 }
};

const keysFile = path.join(CASE, 'edit', 'Edit-BoneKeys-' + ACT + '.json');
const keys = fs.existsSync(keysFile) ? JSON.parse(fs.readFileSync(keysFile, 'utf8')) : {};

Object.assign(sandbox, {
  __frames: payload.frames_list, __keys: keys, __roles: payload.roles, __meta: payload.meta,
  __calib: payload.calib, __scale: payload.scale, __limits: payload.limits,
  __data: data, __skel: skeleton, __pages: pages, __load: p => loadImage(p)
});
run(`
  MO.list = __frames; MO.keys = __keys; MO.roles = __roles; MO.meta = __meta;
  MO.calib = __calib; MO.scale = __scale; MO.limits = __limits;
  MO.act = '${ACT}'; MO.sel = ${FRAME};
  RT.data = __data; RT.skel = __skel; RT.pages = __pages; RT.alpha = 1;
  RT.adj = { kx: 1, ky: 1, dx: 0, dy: 0, lock: true };
  RT.anchor = null;
`);

const frameInfo = payload.frames_list.find(x => x.n === FRAME);
if (!frameInfo) throw new Error('帧 ' + FRAME + ' 不在帧表里');

const video = await loadImage(frameInfo.path);
const vcv = createCanvas(frameInfo.w, frameInfo.h);
vcv.getContext('2d').drawImage(video, 0, 0);
const vd = vcv.getContext('2d').getImageData(0, 0, frameInfo.w, frameInfo.h).data;
const V = new Uint8Array(frameInfo.w * frameInfo.h);
for (let i = 0; i < V.length; i++) V[i] = (vd[i * 4 + 1] - Math.max(vd[i * 4], vd[i * 4 + 2])) < 60 ? 1 : 0;
const W = frameInfo.w, H = frameInfo.h;

function axisHit(a, b) {
  let hit = 0, n = 0;
  for (let t = 0; t <= 20; t++) {
    const u = t / 20;
    const x = Math.round(a[0] + (b[0] - a[0]) * u), y = Math.round(a[1] + (b[1] - a[1]) * u);
    n++;
    if (x < 0 || y < 0 || x >= W || y >= H) continue;
    hit += V[y * W + x];
  }
  return hit / n;
}

const inverted = new Uint8Array(V.length);
for (let i = 0; i < V.length; i++) inverted[i] = V[i] ? 0 : 1;
const field = run('iouField')(inverted, W, H);

function depthAt(x, y) {
  if (x < 0 || y < 0 || x >= W || y >= H) return 0;
  return field[y * W + x] / 3;
}

function axisDepth(a, b) {
  const out = [];
  for (let t = 0; t <= 20; t++) {
    const u = t / 20;
    out.push(depthAt(Math.round(a[0] + (b[0] - a[0]) * u), Math.round(a[1] + (b[1] - a[1]) * u)));
  }
  out.sort((p, q) => p - q);
  return out[out.length >> 1];
}

function exitAt(tip, ang) {
  const nx = Math.cos(ang * Math.PI / 180), ny = -Math.sin(ang * Math.PI / 180);
  for (let r = 0; r < 120; r++) {
    const x = Math.round(tip[0] + nx * r), y = Math.round(tip[1] + ny * r);
    if (x < 0 || y < 0 || x >= W || y >= H) return -1;
    if (!V[y * W + x]) return r;
  }
  return 120;
}

const row = keys[String(FRAME)] || payload.frames_list[FRAME - 1].bones;
if (opt('deg', null) !== null) {
  const k = opt('deg');
  const d = +opt('by', 15);
  const cur = row[k] || (row[k] = { s: 1 });
  cur.r = Math.round(((+cur.r || 0) + d) * 100) / 100;
}
sandbox.__row = row;
run('MO.keys[MO.sel] = __row;');
const joints = JSON.parse(run('JSON.stringify(boneJoints({ bones: MO.keys[MO.sel], hip: null }))'));
console.log('第 ' + FRAME + ' 帧 · ' + CASE.split('/').pop() + ' · ' + ACT);
console.log('骨  role             r       s      世界角   实际长  轴命中  末端出界  轴心距  源Δr');
const report = [];
for (const k of Object.keys(joints).map(Number).sort((a, b) => a - b)) {
  const gj = joints[k];
  const meta = payload.meta[String(k)] || {};
  const kk = row[String(k)] || {};
  const sc = +kk.s || 1;
  const L = (+meta.l || 0) * sc;
  const ang = Math.atan2(gj.p[1] - gj.q[1], gj.q[0] - gj.p[0]) * 180 / Math.PI;
  const hit = axisHit(gj.p, gj.q);
  const out = exitAt(gj.q, ang);
  const src = (payload.frames_list[FRAME - 1].bones || {})[String(k)] || {};
  const dr = (+kk.r || 0) - (+src.r || 0);
  report.push({ k, meta, kk, sc, L, ang, hit, out, dr, gj });
  console.log(String(k).padStart(2) + '  ' + (meta.r || '?').padEnd(15)
    + String((+kk.r || 0).toFixed(2)).padStart(7)
    + String(sc.toFixed(3)).padStart(8)
    + String(ang.toFixed(1)).padStart(9)
    + String(L.toFixed(1)).padStart(9)
    + String((hit * 100).toFixed(0) + '%').padStart(8)
    + String(out < 0 ? '出画' : out + 'px').padStart(10)
    + String(axisDepth(gj.p, gj.q).toFixed(1) + 'px').padStart(9)
    + String((dr >= 0 ? '+' : '') + dr.toFixed(1)).padStart(8));
}

if (opt('scan', null) !== null) {
  const k = +opt('scan');
  const base = JSON.parse(JSON.stringify(row[String(k)] || {}));
  const cur = +base.r || 0;
  const rows = [];
  for (let d = -45; d <= 45; d += 2.5) {
    base.r = Math.round((cur + d) * 100) / 100;
    row[String(k)] = base;
    sandbox.__row = row;
    run('MO.keys[MO.sel] = __row;');
    const jj = JSON.parse(run('JSON.stringify(boneJoints({ bones: MO.keys[MO.sel], hip: null }))'))[k];
    const aa = Math.atan2(jj.p[1] - jj.q[1], jj.q[0] - jj.p[0]) * 180 / Math.PI;
    rows.push({ d, hit: axisHit(jj.p, jj.q), out: exitAt(jj.q, aa) });
  }
  row[String(k)] = JSON.parse(JSON.stringify(Object.assign({}, base, { r: cur })));
  sandbox.__row = row;
  run('MO.keys[MO.sel] = __row;');
  const full = rows.filter(x => x.hit >= 0.999).map(x => x.d);
  console.log('\n骨 ' + k + ' 旋转扫描（当前 r=' + cur.toFixed(2) + '°，命中率 vs 偏移）：');
  console.log('  偏移   命中率  末端余量');
  for (const x of rows) {
    console.log('  ' + String((x.d > 0 ? '+' : '') + x.d + '°').padStart(6)
      + String((x.hit * 100).toFixed(0) + '%').padStart(8)
      + String(x.out < 0 ? '出画' : x.out + 'px').padStart(10));
  }
  console.log(full.length
    ? '  100% 命中区间：' + full[0] + '° ~ ' + full[full.length - 1] + '°（相对当前）'
    : '  ±45° 内没有能完全收进轮廓的方向');
}

if (opt('pos', null) !== null) {
  const k = +opt('pos');
  const base = JSON.parse(JSON.stringify(row[String(k)] || {}));
  const ax = +(base.x || 0), ay = +(base.y || 0);
  console.log('\n骨 ' + k + ' 起点偏移扫描（r 已转到最佳角，命中率 / 末端余量）：');
  for (let dy = -16; dy <= 16; dy += 8) {
    const line = [];
    for (let dx = -16; dx <= 16; dx += 8) {
      row[String(k)] = Object.assign({}, base, { x: ax + dx, y: ay + dy });
      sandbox.__row = row;
      run('MO.keys[MO.sel] = __row;');
      const jj = JSON.parse(run('JSON.stringify(boneJoints({ bones: MO.keys[MO.sel], hip: null }))'))[k];
      const aa = Math.atan2(jj.p[1] - jj.q[1], jj.q[0] - jj.p[0]) * 180 / Math.PI;
      const h = axisHit(jj.p, jj.q);
      const o = exitAt(jj.q, aa);
      line.push('(' + (dx > 0 ? '+' : '') + dx + ',' + (dy > 0 ? '+' : '') + dy + ') '
        + (h * 100).toFixed(0) + '%/' + (o < 0 ? '出画' : o + 'px'));
    }
    console.log('  ' + line.join('   '));
  }
  row[String(k)] = base;
  sandbox.__row = row;
  run('MO.keys[MO.sel] = __row;');
}

const bad = report.filter(r => r.hit < 0.95 && r.L > 8);
console.log(bad.length
  ? '\n有骨段落在人物轮廓外：' + bad.map(r => r.k + '(' + (r.hit * 100).toFixed(0) + '%)').join(' ')
  : '\n所有骨的轴线都落在人物轮廓内');

if (PNG || BONE !== null) {
  const target = BONE !== null ? report.find(r => r.k === +BONE) : null;
  const outFile = PNG || path.join('/tmp', 'bones-f' + FRAME + '.png');
  const canvas = createCanvas(W, H);
  const c = canvas.getContext('2d');
  c.drawImage(vcv, 0, 0);
  for (const r of report) {
    c.strokeStyle = target && r.k === target.k ? '#ff2d55' : 'rgba(0,140,255,0.8)';
    c.lineWidth = target && r.k === target.k ? 3.5 : 1.6;
    c.beginPath();
    c.moveTo(r.gj.p[0], r.gj.p[1]);
    c.lineTo(r.gj.q[0], r.gj.q[1]);
    c.stroke();
  }
  if (target) {
    c.fillStyle = '#ffcc00';
    c.beginPath(); c.arc(target.gj.p[0], target.gj.p[1], 4, 0, 6.3); c.fill();
    c.fillStyle = '#00a3ff';
    c.beginPath(); c.arc(target.gj.q[0], target.gj.q[1], 4, 0, 6.3); c.fill();
  }
  fs.writeFileSync(outFile, canvas.toBuffer('image/png'));
  console.log('图 ' + outFile);
}
