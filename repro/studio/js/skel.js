let SK = null;

async function loadSkeleton() {
  if (!DIR || !state || !state.case) { SK = null; renderSkel(); return; }
  try { SK = await (await fetch('/api/skeleton' + qs())).json(); }
  catch (e) { SK = null; }
  let stale = false;
  if (SK && SK.rig) {
    const before = JSON.stringify(SK.rig.bones || []);
    skSyncAims(SK.rig);
    stale = JSON.stringify(SK.rig.bones || []) !== before;
  }
  renderSkel();
  if (stale) saveSkel();
}

function skHint(i) {
  const el = $('#sklive');
  if (!el) return;
  const b = skBone(i);
  el.innerHTML = '先在列表里点 <b>#' + i + '</b>' +
    (b && b.role ? ' ' + b.role : '') + ' 选中它，再在画布上拖';
}

function skLive(id) {
  const el = $('#sklive');
  if (!el) return;
  const b = skBone(id == null ? BONE_SEL : id);
  if (!b) { el.textContent = '点一根骨骼'; return; }
  const w = (skWorld(SK.rig) || []).find(x => x.index === b.index) || {};
  el.innerHTML = '<b>' + skNm(b) + '</b>' + (b.role ? ' ' + b.role : '') +
    ' · 长 ' + skR2(b.length) + 'px · 绝对角 ' +
    (w.rotation == null ? '—' : skR2(w.rotation)) + '°' +
    (b.aim != null ? ' · 指向 #' + b.aim : '');
}

function skDetailHtml(b) {
  const i = b.index;
  const w = skWorld(SK.rig);
  const ban = skSubtree(SK.rig, i);
  const zero = (b.length || 0) < 0.5;
  const aimed = b.aim != null;
  const opts = (cur, none, skip) =>
    '<option value=""' + (cur == null ? ' selected' : '') + '>' + none + '</option>' +
    w.filter(x => x.index !== i && !skip.has(x.index))
      .map(x => '<option value="' + x.index + '"' + (x.index === cur ? ' selected' : '') + '>' +
           skNm(x) + (x.role ? ' ' + x.role : '') + '</option>').join('');
  return '<div class="sk-ed">' +
    '<label>父级<select data-i="' + i + '" data-k="parent">' +
      opts(b.parent_index >= 0 ? b.parent_index : null, '（无 · 世界坐标）', ban) + '</select></label>' +
    (zero ? '' : '<label>指向<select data-i="' + i + '" data-k="aim">' +
      opts(aimed ? +b.aim : null, '（无）', new Set([i])) + '</select></label>') +
    '<label>偏移<input type="number" step="0.1" data-i="' + i + '" data-k="ox" value="' +
      skR2(b.ox) + '"><input type="number" step="0.1" data-i="' + i + '" data-k="oy" value="' +
      skR2(b.oy) + '"></label>' +
    '<label>旋转<input type="number" step="0.1" data-i="' + i + '" data-k="lrot" value="' +
      skR2(b.lrot) + '"' + (aimed ? ' disabled' : '') +
      '><span class="sk-unit">° 相对父级</span></label>' +
    '<label>长度<input type="number" step="0.1" data-i="' + i + '" data-k="length" value="' +
      skR2(b.length) + '"' + (aimed ? ' disabled' : '') +
      '><span class="sk-unit">px</span></label>' +
    '<div class="sk-world">世界 <b>' + Math.round(b.x * 10) / 10 + ', ' +
      Math.round(b.y * 10) / 10 + '</b> · 绝对角 <b>' +
      Math.round(b.rotation * 10) / 10 + '°</b> <em>（父级累加出来的，改上面几个就行）</em></div>' +
    '<div class="sk-act"><button class="sk-del" data-del="' + i + '">删除这根骨骼</button>' +
      '<span class="sk-note">' + (zero ? '零长（控制骨）'
        : '长 ' + (Math.round(b.length * 10) / 10) + ' · 相对角 ' +
          (Math.round(b.lrot * 10) / 10) + '°' +
          (aimed ? ' · 指向 #' + b.aim : '')) +
      '</span></div>' +
    '</div>';
}

function skListHtml(bones) {
  const head = '<div class="sk-new"><select id="skNewParent">' +
    '<option value="">（无父级 · 世界坐标）</option>' +
    bones.map(x => '<option value="' + x.index + '">' + skNm(x) + '</option>').join('') +
    '</select><button id="skNewAdd">新建骨骼</button></div>';
  return head + boneListHtml(bones);
}

function renderSkelList(bones) {
  const box = $('#sklist');
  if (!box) return;
  box.innerHTML = skListHtml(bones);
  const add = $('#skNewAdd');
  if (add) add.onclick = () => skAddBone();
  boneWire(box, renderSkel);
}

function renderSkelProps(bones) {
  const box = $('#skprops'), hint = $('#skphint');
  if (!box) return;
  const b = BONE_SEL == null ? null : bones.find(x => x.index === BONE_SEL);
  const was = document.activeElement;
  const keep = was && was.dataset && was.dataset.k ? was.dataset.k : '';
  if (!b) {
    hint.textContent = '没选中';
    box.innerHTML = '<div class="empty">在左边列表里点一根骨骼，这里改它的父级 / 偏移 / 旋转 / ' +
      '长度 / 指向。</div>';
    return;
  }
  hint.textContent = '#' + b.index + (b.role ? ' ' + b.role : '') +
    ' · 长 ' + skR2(b.length) + 'px';
  box.innerHTML = skDetailHtml(b);
  box.querySelectorAll('.sk-ed input, .sk-ed select').forEach(el => {
    el.onchange = () => skApply(+el.dataset.i, el.dataset.k,
      el.type === 'checkbox' ? el.checked : el.value);
  });
  box.querySelectorAll('button.sk-del').forEach(el => {
    el.onclick = () => skDelBone(+el.dataset.del);
  });
  const again = keep ? box.querySelector('[data-k="' + keep + '"]') : null;
  if (again && again.type !== 'checkbox') again.focus();
}

function queueSkelSave() {
  clearTimeout(SK_SAVE_T);
  SK_SAVE_T = setTimeout(() => saveSkel(), 600);
}

async function skApply(i, key, val) {
  const rig = SK && SK.rig;
  if (!rig) return;
  const b = skBone(i);
  if (!b) return;
  const snap = skSnap(skWorld(rig));
  if (key === 'parent') {
    const par = (val === '' || val == null) ? -1 : parseInt(val, 10);
    if (par === i || (par >= 0 && skSubtree(rig, i).has(par))) {
      log('不能挂到自己或自己的子骨上', 'err'); renderSkel(); return;
    }
    const w = skWorld(rig);
    const me = w.find(x => x.index === i);
    const pv = par >= 0 ? w.find(x => x.index === par) : null;
    b.parent = par;
    if (pv && me) {
      const dd = skToLocal(me.x - pv.x, me.y - pv.y, pv.rotation);
      b.x = skR2(dd[0]); b.y = skR2(dd[1]);
      b.rotation = skR2(me.rotation - pv.rotation);
    } else if (me) {
      b.x = skR2(me.x); b.y = skR2(me.y); b.rotation = skR2(me.rotation);
    }
    log('换父级：#' + i + ' → ' + (par >= 0 ? '#' + par : '根（世界坐标）'), 'cmd');
  } else if (key === 'aim') {
    const t = (val === '' || val == null) ? null : parseInt(val, 10);
    if (t == null) {
      delete b.aim;
      log('#' + i + ' 取消指向', 'cmd');
    } else {
      if (t === i) {
        log('不能指向自己', 'err'); renderSkel(); return;
      }
      b.aim = t;
      skAimOne(rig, i);
      log('#' + i + ' 指向 #' + t + '：拖 #' + t + ' 时 #' + i + ' 的长度和角度跟着变', 'cmd');
    }
  } else if (key === 'ox' || key === 'oy') {
    b[key === 'ox' ? 'x' : 'y'] = skR2(val);
  } else if (key === 'lrot') {
    if (b.aim != null) return;
    b.rotation = skR2(val);
  } else if (key === 'length') {
    b.length = Math.max(0, skR2(val));
    if (b.length < 0.5 && b.aim != null) {
      delete b.aim;
      log('#' + i + ' 变成零长，指向已取消', 'cmd');
    }
  }
  skPin(rig, i, snap);
  skSyncAims(rig);
  renderSkel();
  queueSkelSave();
}

async function skDelBone(i) {
  const rig = SK && SK.rig;
  if (!rig) return;
  const b = skBone(i);
  if (!b) return;
  if (!confirm('删掉骨骼 #' + i + '？它的子骨会接到它的父级上，index 会重排。')) return;
  const par = (b.parent == null ? -1 : +b.parent);
  const w = skWorld(rig);
  const pv = par >= 0 ? w.find(x => x.index === par) : null;
  rig.bones = rig.bones.filter(x => x.index !== i);
  rig.bones.forEach(x => {
    if (x.aim != null && +x.aim === i) delete x.aim;
    if (+x.parent !== i) return;
    const s = w.find(y => y.index === x.index);
    x.parent = par;
    if (!s) return;
    if (pv) {
      const d = skToLocal(s.x - pv.x, s.y - pv.y, pv.rotation);
      x.x = skR2(d[0]); x.y = skR2(d[1]);
      x.rotation = skR2(skWrap(s.rotation - pv.rotation));
    } else {
      x.x = skR2(s.x); x.y = skR2(s.y); x.rotation = skR2(s.rotation);
    }
  });
  skReindex(rig);
  BONE_SEL = null;
  log('已删除 #' + i + '（还剩 ' + rig.bones.length + ' 根）', 'cmd');
  renderSkel();
  queueSkelSave();
}

async function skAddBone() {
  const rig = SK && SK.rig;
  if (!rig) return;
  const sel = $('#skNewParent').value;
  const par = (sel === '' || sel == null) ? -1 : parseInt(sel, 10);
  const i = rig.bones.length;
  rig.bones.push({ index: i, parent: par, x: 0, y: 0, rotation: 0, length: 40 });
  BONE_SEL = i;
  log('新建骨骼 #' + i + (par >= 0 ? '（父级 #' + par + '）' : ''), 'cmd');
  renderSkel();
  queueSkelSave();
}

function skDrag(g) {
  const rig = SK.rig, b = skBone(g.i);
  if (!b) return;
  const w = skWorld(rig), me = w.find(x => x.index === g.i);
  if (!me) return;
  const snap = skSnap(w);
  const pv = me.parent_index >= 0 ? w.find(x => x.index === me.parent_index) : null;
  if (g.mode === 'move') {
    if (pv) {
      const dd = skToLocal(g.tx - pv.x, g.ty - pv.y, pv.rotation);
      b.x = skR2(dd[0]); b.y = skR2(dd[1]);
    } else {
      b.x = skR2(g.tx); b.y = skR2(g.ty);
    }
  } else {
    b.rotation = skR2(skWrap(g.rot - (pv ? pv.rotation : 0)));
    if (g.mode === 'tip') b.length = skR2(g.len);
  }
  skPin(rig, g.i, snap);
  skSyncAims(rig);
  $('#sksvg').innerHTML = skSvgHtml(skWorld(rig));
  skLive(g.i);
}

function skDrop(moved) {
  if (moved) saveSkel(); else renderSkel();
}

function initSkel() {
  boneDrag($('#sksvg'), {
    busy: () => false,
    extent: () => (SK && SK.rig && SK.rig.canvas) || [1024, 1024],
    bones: () => (SK && SK.rig ? skWorld(SK.rig) : []),
    hint: skHint,
    warn: m => log(m, 'err'),
    begin: () => null,
    drag: skDrag,
    drop: skDrop
  });
}

function renderSkel() {
  const hint = $('#skhint'), bar = $('#skbar'), foot = $('#skfoot'),
        info = $('#ski'), ih = $('#skihint'), stage = $('#skstage'), svg = $('#sksvg');
  const base = SK && SK.rig;
  if (!base) {
    hint.textContent = '没有骨架';
    bar.innerHTML = '';
    foot.textContent = '';
    ih.textContent = '—';
    info.innerHTML = '<div class="empty">缺骨架 <code>repro/config/skeleton.json</code>。</div>';
    $('#skprops').innerHTML = '<div class="empty">缺骨架。</div>';
    svg.innerHTML = '';
    $('#skimg').removeAttribute('src');
    return;
  }

  const bones = skWorld(base);
  const dims = base.canvas || [1024, 1024];
  const W = dims[0], H = dims[1];

  const img = $('#skimg');
  if (SK.ref) {
    const src = '/api/file?p=' + encodeURIComponent(SK.ref) + '&dir=' + encodeURIComponent(DIR);
    if (img.getAttribute('src') !== src) img.src = src;
    img.hidden = false;
    stage.style.aspectRatio = '';
  } else {
    img.removeAttribute('src');
    img.hidden = true;
    stage.style.aspectRatio = W + ' / ' + H;
  }
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.innerHTML = skSvgHtml(bones);

  bar.innerHTML =
    '<span class="sk-live" id="sklive">—</span>' +
    '<span class="sp">列表里点行选中 —— 画布只动选中的那根：拖圆环移、拖骨身转、拖末端改长度</span>';

  hint.textContent = bones.length + ' 根骨骼 · ' + W + '×' + H;
  ih.textContent = '骨架';
  const g = base.ground;
  info.innerHTML = '<div class="sk-foot2">脚底 y = ' +
    (g == null ? '—' : g) + ' px · 骨骼按 index 引用（名字就是 index）</div>' +
    '<div class="sk-list" id="sklist"></div>';
  renderSkelList(bones);
  renderSkelProps(bones);
  skLive();
  foot.textContent = '选中只在这里点。属性在预览下方的「骨骼属性设置」里改，画布上只动拖的那一根 —— ' +
    '拖圆环移动、拖骨身转、拖末端同时改长度和角度，子骨和其它骨都留在原地。' +
    '改动自动存回 repro/config/skeleton.json。' +
    '「指向」= 末端钉在目标骨的原点上，长度和角度都按它的位置算；拖那根骨，这根跟着摆。';
}

async function saveSkel() {
  if (!SK || !SK.rig) return;
  const j = await postJSON('/api/skeleton', { rig: SK.rig });
  if (j.saved) log('骨架已保存：' + j.saved.split('/').pop(), 'cmd');
  else if (j.error) log('骨架保存失败：' + j.error, 'err');
  SK_REV++;
  renderSkel();
}
