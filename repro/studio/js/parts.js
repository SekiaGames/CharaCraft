let MX = null, SEL = {}, mxBusy = false;

async function loadMatrix() {
  if (!DIR || !state || !state.case) { MX = null; $('#mx').innerHTML = '<div class="empty">先填目录。</div>'; return; }
  $('#mxhint').textContent = '统计中…';
  try {
    const r = await fetch('/api/layers' + qs());
    MX = await r.json();
  } catch (e) { MX = null; }
  SEL = (MX && MX.selection) || {};
  $('#mxhint').textContent = '动作 ' + (MX && MX.act || ACT)
    + ' · 左→右 = 批次 id 小→大 · 绿框 = 首批，点别的格子 = 这个部件改用那一批，'
    + '改完重跑「打包图集」';
  renderMatrix();
}

const shortId = id => (id || '').split('_')[1] || id || '';

async function toggleOff(name, off) {
  try {
    const r = await fetch('/api/disable', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dir: DIR, name, off }),
    });
    const j = await r.json();
    if (j.error) { log('禁用失败：' + j.error, 'err'); return; }
  } catch (e) { log('禁用失败：' + e, 'err'); return; }
  await loadMatrix();
  loadPreview();
}

function renderMatrix() {
  const box = $('#mx'), note = $('#mxnote');
  if (note) note.hidden = true;
  if (!MX || !MX.layers || !MX.layers.length) {
    const bs = (MX && MX.batches) || [];
    box.innerHTML = bs.length
      ? `<div class="empty">input/ 里有 ${bs.length} 批 PSD（${bs.map(b => shortId(b.id)).join(' / ')}），`
        + '但还没扫图层清单。先跑 <code>拆图</code>。</div>'
      : '<div class="empty">input/ 里还没有 PSD。先跑「同步 PSD」（把 ComfyUI 输出目录里的 PSD 迁进来）。</div>';
    return;
  }
  const cols = MX.batches;
  const first = MX.first;
  let h = '<table class="mx"><thead><tr><th class="nm">部件（首批的图层）</th>'
    + '<th class="off" title="勾掉的部件整层不要（哪一批都不取）">禁用</th>';
  for (const b of cols) {
    const src = b.split ? '已扫（层清单在 base/batches）' : '只有 PSD，还没跑「拆图」';
    h += `<th class="${b.id === first ? 'first' : ''}" title="${b.id}\n${src}">${shortId(b.id)}`
      + (b.id === first ? '<i class="sm">首批</i>' : '')
      + (b.split ? '' : '<i class="sm">待扫</i>') + '</th>';
  }
  h += '</tr></thead><tbody>';
  for (const row of MX.layers) {
    const idx = (row.index === null || row.index === undefined) ? '' : `<span class="idx">${row.index}</span>`;
    h += `<tr class="${row.disabled ? 'off' : ''}"><td class="nm">${row.name}${idx}</td>`
      + `<td class="off"><button class="tog ${row.disabled ? 'on' : ''}" data-d="${row.name}"`
      + ` title="${row.disabled ? '已禁用：哪一批都不取' : '点一下禁用这个部件'}">`
      + `${row.disabled ? '禁' : '·'}</button></td>`;
    for (const b of cols) {
      const c = row.cells[b.id];
      if (!c) { h += '<td></td>'; continue; }
      const cls = SEL[row.name] === b.id ? 'sel'
        : c.empty ? 'empty'
        : (row.auto === b.id ? 'has auto' : 'has');
      const tip = c.empty ? `${row.name} · ${shortId(b.id)}\n空层：${c.why || ''}`
        : `${row.name} · ${shortId(b.id)}\n${c.px} 像素`
          + (row.auto === b.id ? '\n（首批：不点的话就用这一份）' : '\n（点一下 = 用这一批的图平替）');
      h += `<td><button class="cell ${cls}" data-l="${row.name}" data-b="${b.id}"
             title="${tip}" ${c.empty ? 'disabled' : ''}></button></td>`;
    }
    h += '</tr>';
  }
  h += '</tbody></table>';
  box.innerHTML = h;
  box.querySelectorAll('.cell').forEach(el => {
    el.onclick = () => pick(el.dataset.l, el.dataset.b);
  });
  box.querySelectorAll('.tog').forEach(el => {
    el.onclick = () => toggleOff(el.dataset.d, !el.classList.contains('on'));
  });
  const n = Object.keys(SEL).length;
  $('#mxstate').textContent = n ? `平替 ${n} 个部件` : '全部用首批';
  if (MX.extra && MX.extra.length) {
    note.hidden = false;
    note.innerHTML = `另有 <b>${MX.extra.length}</b> 个图层只出现在别的批次里，首批没有 → `
      + `不参与：<code>${MX.extra.slice(0, 12).join('</code> <code>')}</code>`
      + `${MX.extra.length > 12 ? ' …' : ''}。想让它们生效，把那一批改成更早的日期（改名即可）让它当首批。`;
  }
}

async function pick(layer, batch) {
  if (mxBusy) return;
  if (SEL[layer] === batch) delete SEL[layer];
  else SEL[layer] = batch;
  renderMatrix();
  mxBusy = true;
  try {
    await fetch('/api/select', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dir: DIR, action: (MX && MX.act) || ACT, selection: SEL }),
    });
    $('#mxstate').textContent = Object.keys(SEL).length
      ? `平替 ${Object.keys(SEL).length} 个部件（已保存 · 重跑「打包图集」生效）`
      : '全部用首批（已保存 · 重跑「打包图集」生效）';
    loadPreview();
  } catch (e) { log('保存选择失败：' + e, 'err'); }
  mxBusy = false;
}

function renderActions() {
  const box = $('#acts');
  const acts = ((state && state.case) || {}).actions || [];
  const rigged = ((state.case || {}).motion || {}).rigged || [];
  const btns = acts.map(a => {
    const cls = a.id === ACT ? 'on' : (a.video ? '' : 'no');
    let tip = a.video ? 'input/clip-' + a.id + '.* 已就位'
      : (a.dir ? '只有 clip-' + a.id + '/ 目录，没有视频'
               : '没有 input/clip-' + a.id + '.*');
    if (rigged.includes(a.id)) tip += '\n已绑骨（会进 output 的 json）';
    const dot = rigged.includes(a.id) ? '<i class="ok"></i>' : '';
    return `<button class="${cls}" data-a="${a.id}" title="${tip}">${a.id}${dot}</button>`;
  }).join('');
  box.innerHTML = btns
    + `<span class="tip">${state.copy.panel.actsTip.replace('{act}', ACT)}</span>`;
  box.querySelectorAll('button').forEach(b => {
    b.onclick = () => {
      if (b.dataset.a === ACT) return;
      ACT = b.dataset.a;
      const u = new URL(location.href);
      u.searchParams.set('action', ACT);
      history.replaceState(null, '', u);
      load();
    };
  });
}

const BLK = { cfg: null, step: null, manual: {} };
const BLK_NAME = {};
const BLK_FIXED = new Set(['log', 'skview']);

function blockEls() {
  return [...document.querySelectorAll('section.panel[data-blk]')];
}

function blockOn(el, show) {
  if (BLK_FIXED.has(el.dataset.blk)) return true;
  const m = BLK.manual[el.dataset.blk];
  if (m === 'open') return true;
  if (m === 'closed') return false;
  return !(show && el.dataset.blk !== 'log' && !show.has(el.dataset.blk));
}

function applyBlocks() {
  const list = BLK.cfg && BLK.step ? BLK.cfg[BLK.step] : null;
  const show = (TAB === 'motion' && list) ? new Set(list) : null;
  for (const el of blockEls()) el.classList.toggle('blk-off', !blockOn(el, show));
  const off = blockEls().filter(el => el.classList.contains('blk-off')).length;
  const hint = $('#blkstate');
  if (hint) hint.textContent = (!show && off) ? '已收起 ' + off + ' 个区块 · 点 ＋ 加回来' : '';
}

function clearManual() {
  BLK.manual = {};
}

async function saveStepBlocks(step, list) {
  const order = blockEls().map(el => el.dataset.blk);
  const r = await fetch('/api/blocks', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ step: step, blocks: order.filter(k => list.includes(k)) }),
  });
  const d = await r.json();
  BLK.cfg = d.blocks.steps;
  BLK.manual = {};
  hotUi = d.ui;
  applyBlocks();
}

function closeBlkMenu() {
  const m = $('#blkmenu');
  if (m) m.remove();
}

function openBlkMenu(btn) {
  closeBlkMenu();
  const m = document.createElement('div');
  m.className = 'blk-menu';
  m.id = 'blkmenu';
  const step = BLK.step;
  const cur = (step && BLK.cfg) ? (BLK.cfg[step] || []) : null;
  const items = cur
    ? blockEls().filter(el => !BLK_FIXED.has(el.dataset.blk) && !cur.includes(el.dataset.blk))
    : blockEls().filter(el => el.classList.contains('blk-off'));
  const t = document.createElement('b');
  t.textContent = cur ? '这一步没有的区块（点一下加进配置）' : '未显示的区块';
  m.appendChild(t);
  if (!items.length) {
    const sp = document.createElement('span');
    sp.textContent = cur ? '都已经加进来了' : '全部区块都在';
    m.appendChild(sp);
  }
  for (const el of items) {
    const b = document.createElement('button');
    b.textContent = BLK_NAME[el.dataset.blk] || el.dataset.blk;
    b.onclick = () => {
      closeBlkMenu();
      if (cur) saveStepBlocks(step, cur.concat(el.dataset.blk));
      else { BLK.manual[el.dataset.blk] = 'open'; applyBlocks(); }
    };
    m.appendChild(b);
  }
  document.body.appendChild(m);
  const r = btn.getBoundingClientRect();
  m.style.left = Math.max(8, Math.min(window.innerWidth - m.offsetWidth - 10,
                                      r.right - m.offsetWidth)) + 'px';
  m.style.top = (r.bottom + 6) + 'px';
  setTimeout(() => document.addEventListener('click', closeBlkMenu, { once: true }), 0);
}

let PVFIT = false;

function applyZoom() {
  $('#pvshot').classList.toggle('fit', PVFIT);
  const b = $('#pvzoom');
  if (b) b.textContent = PVFIT ? '适应' : '1:1';
}

async function loadPreview() {
  const box = $('#pvparts'), img = $('#pvimg'), hint = $('#pvhint');
  if (!DIR || !state || !state.case) {
    box.innerHTML = '<div class="empty">先填目录。</div>';
    img.removeAttribute('src');
    hint.textContent = '按当前选择实时合成';
    return;
  }
  hint.textContent = '合成中…';
  try {
    const r = await fetch('/api/preview' + qs());
    const p = await r.json();
    if (p.error) {
      box.innerHTML = `<div class="empty">${p.error}</div>`;
      img.removeAttribute('src');
      hint.textContent = p.error.length > 26 ? p.error.slice(0, 26) + '…' : p.error;
      return;
    }
    img.src = p.composite;
    const head = `<div class="pv-row pv-head"><span>部件</span>`
      + `<span style="text-align:center">取图</span>`
      + `<span style="text-align:right">层序</span><span>预览</span></div>`;
    const rows = p.parts.map(x => {
      const idx = (x.index === null || x.index === undefined) ? '' : x.index;
      const whence = 'input/' + (x.batch || '?') + '.psd 的「' + x.name + '」层';
      const note = x.sub ? '（平替：改用别的批次的同名图层）' : '（首批）';
      return `<div class="pv-row" data-name="${x.name}"`
        + ` title="${x.name} · ${x.w}×${x.h} · 读的是 ${whence}${note}">`
        + `<span class="nm">${x.name}</span>`
        + `<span class="bt" title="${whence}">${x.from[0] || '-'}</span>`
        + `<span class="idx" title="层序来自首批（0 = 最下层）。要调顺序就在首批的 PSD 里拖动图层，再跑「拆图」">${idx}</span>`
        + `<img src="${x.url}" loading="lazy" alt="${x.name}"></div>`;
    }).join('');
    box.innerHTML = p.parts.length ? head + rows : '<div class="empty">还没有可用图层。</div>';
    const cs = p.composite_size || [];
    hint.textContent = `${p.act || ACT} · ${p.parts.length} 个部件 · 首批 ${p.first_short || '?'}`
      + ` · ${cs[0] || '?'}×${cs[1] || '?'} px`;
    renderRigLinks();
  } catch (e) {
    hint.textContent = '预览失败：' + e;
  }
}

function renderRigLinks() {
  const box = $('#pvlinks');
  const c = state && state.case;
  if (!c) { box.innerHTML = ''; return; }
  const link = (p, label) => `<a href="/api/file?p=${encodeURIComponent(p)}&dir=${encodeURIComponent(DIR)}" target="_blank">${label}</a>`;
  const items = [];
  if (c.atlas) items.push(link(c.path + '/output/preview.html', 'spine 预览（页内切动作）'));
  box.innerHTML = items.length ? items.join('')
    : '<span>跑完「合并 + 预览」这里会出现 spine 预览</span>';
}
