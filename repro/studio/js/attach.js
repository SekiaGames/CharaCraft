let AT = null, ATDIRTY = false;


async function loadAttach() {
  if (!DIR || !state || !state.case) { AT = null; renderAttach(); return; }
  try {
    const r = await fetch('/api/attachments' + qs());
    AT = await r.json();
  } catch (e) { AT = null; }
  ATDIRTY = false;
  renderAttach();
}

function atBoneList() {
  return (AT && AT.bones) || [];
}

function atBones(r) {
  return (r.bones || []).map(Number);
}

function atBoneName(idx) {
  const b = atBoneList().find(x => x.index === idx);
  if (!b) return '#' + idx + '（骨架里没有）';
  return '#' + b.index + (b.role ? ' <i class="ro">' + b.role + '</i>' : '');
}

function atChips(r, i) {
  const cur = atBones(r);
  let h = '<span class="bchips">';
  for (const idx of cur) {
    h += '<span class="bchip' + (cur.length === 1 ? ' solo' : '') +
         '" data-i="' + i + '" data-b="' + idx + '" title="' +
         (cur.length === 1 ? '只挂这一根 = 全权重（region）' : '多根 = 按骨骼链生成 mesh 权重') +
         '">' + atBoneName(idx) + '<b class="bx" title="去掉这根">×</b></span>';
  }
  if (!cur.length) h += '<span class="dim">没挂骨骼（这一层会被跳过）</span>';
  h += '</span>';
  h += '<select class="badd" data-i="' + i + '"><option value="">＋</option>' +
    atBoneList().slice().sort((a, b) => a.index - b.index)
      .filter(b => !cur.includes(b.index))
      .map(b => '<option value="' + b.index + '">#' + b.index +
        (b.role ? ' ' + b.role : '') + '</option>').join('') +
    '</select>';
  return h;
}

function renderAttach() {
  const hint = $('#athint'), box = $('#atTable'), foot = $('#atFoot'), d = $('#atDirty');
  if (!AT || !AT.rows || !AT.rows.length) {
    hint.textContent = '没有图层（先跑「拆图」）';
    box.innerHTML = '';
    foot.textContent = '';
    return;
  }
  const sizeOf = {};
  for (const L of (AT.layers || [])) sizeOf[L.name] = L.size;
  let h = '<thead><tr><th>z</th><th>图层</th><th>骨骼列表</th>' +
          '<th>启用</th><th></th></tr></thead><tbody>';
  AT.rows.forEach((r, i) => {
    const sz = sizeOf[r.layer];
    h += '<tr class="' + (r.enabled ? '' : 'off') + '">' +
      '<td class="z">' + r.z + '</td>' +
      '<td><input class="layer" data-i="' + i + '" data-k="layer" value="' +
        (r.layer || '').replace(/"/g, '&quot;') + '" list="atLayers">' +
        (sz ? '<br><span class="sz">' + sz[0] + '×' + sz[1] + '</span>' : '') + '</td>' +
      '<td class="bones">' + atChips(r, i) + '</td>' +
      '<td><input type="checkbox" data-i="' + i + '" data-k="enabled"' +
        (r.enabled ? ' checked' : '') + '></td>' +
      '<td><button class="del" data-i="' + i + '" title="删掉这一行">×</button></td>' +
      '</tr>';
  });
  box.innerHTML = h + '</tbody>' +
    '<datalist id="atLayers"></datalist>';
  const dl = $('#atLayers');
  if (dl) dl.innerHTML = (AT.layers || []).map(L =>
    '<option value="' + L.name + '">').join('');

  hint.textContent = AT.generated
    ? '这是「拆图」按层名猜的初值 —— 骨骼还没人确认'
    : (AT.saved ? '已保存' : '改过还没保存');
  d.textContent = ATDIRTY ? '未保存' : '';
  const first = AT.first || AT.batch;
  foot.innerHTML = '首批 <code>' + (first || '?') + '</code> · 一行 = 一个 PSD 图层 = 一个部件；'
    + '改动后点「保存」（直接写 <code>' + (AT.path || 'repro/config/attachments_template.json')
    + '</code>），再跑 <b>打包图集</b> / <b>皮肤片段</b> 才生效。<br>'
    + '<b>骨骼列表</b>：只挂 1 根 = 全权重（普通 region，整块贴图跟这根骨走）；'
    + '挂 2 根以上 = 按列表顺序当骨骼链，烘成 mesh 权重（关节处平滑过渡）。'
    + '顺序有意义，先近端后远端；点 <b>×</b> 去掉一根，右边 <b>＋</b> 追加。<br>'
    + '要新部件（比如把帽子拆成帽子前/帽子后）：先在首批的 PSD 里拆好 → 重跑 <b>拆图</b> → '
    + '这里点「+ 添加图层」填图层名。名对不上会跳过并在日志里说明。'
    + (AT.added && AT.added.length
        ? `<br><b>新出现 ${AT.added.length} 个图层还没保存：</b><code>${AT.added.slice(0, 8).join('</code> <code>')}</code>` : '')
    + (AT.gone && AT.gone.length
        ? `<br>表里有 ${AT.gone.length} 行已不在生效图层里（保存后会被丢掉）` : '');
}

function markDirty() {
  ATDIRTY = true;
  $('#atDirty').textContent = '未保存';
}

async function saveAttach() {
  if (!AT) return;
  const r = await fetch('/api/attachments', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dir: DIR, batch: AT.batch, canvas: AT.canvas, rows: AT.rows }),
  });
  const j = await r.json().catch(() => ({}));
  if (j.saved) { log('附件表已保存：' + j.saved + '（' + j.rows + ' 行）', 'cmd');
                 AT.saved = true; ATDIRTY = false; renderAttach(); }
  else log('保存失败：' + (j.error || '未知'), 'err');
}

function initAttach() {
  const box = $('#atTable');
  box.addEventListener('change', e => {
    const t = e.target, i = +t.dataset.i;
    if (!AT || isNaN(i)) return;
    if (t.classList.contains('badd')) {
      if (t.value === '') return;
      AT.rows[i].bones = atBones(AT.rows[i]).concat(+t.value);
      markDirty(); renderAttach();
      return;
    }
    const k = t.dataset.k;
    if (!k) return;
    if (t.type === 'checkbox') AT.rows[i][k] = t.checked;
    else AT.rows[i][k] = t.value;
    markDirty();
    if (k === 'enabled') t.closest('tr').classList.toggle('off', !t.checked);
  });
  box.addEventListener('input', e => {
    const t = e.target, i = +t.dataset.i, k = t.dataset.k;
    if (!AT || isNaN(i) || k !== 'layer') return;
    AT.rows[i].layer = t.value;
    markDirty();
  });
  box.addEventListener('click', e => {
    if (!AT) return;
    const x = e.target.closest('.bx');
    if (x) {
      const chip = x.closest('.bchip'), i = +chip.dataset.i, b = +chip.dataset.b;
      AT.rows[i].bones = atBones(AT.rows[i]).filter(v => v !== b);
      markDirty(); renderAttach();
      return;
    }
    const b = e.target.closest('button.del');
    if (!b) return;
    AT.rows.splice(+b.dataset.i, 1);
    markDirty(); renderAttach();
  });
  $('#atSave').onclick = saveAttach;
  $('#atAdd').onclick = () => {
    if (!AT) return;
    const z = AT.rows.reduce((m, r) => Math.max(m, r.z || 0), 0) + 1;
    AT.rows.push({ layer: '', bones: [], z: z, enabled: true });
    markDirty(); renderAttach();
    const inputs = document.querySelectorAll('#atTable input.layer');
    if (inputs.length) inputs[inputs.length - 1].focus();
  };
}
