function streamStep(id) {
  return new Promise(resolve => {
    const es = new EventSource('/api/run?step=' + encodeURIComponent(id) + '&' + qs().slice(1));
    es.onmessage = e => {
      const m = JSON.parse(e.data);
      if (m.type === 'line') log(m.text, m.text.startsWith('$ ') ? 'cmd' : '');
      if (m.type === 'done') { es.close(); resolve(m.ok); }
    };
    es.onerror = () => { es.close(); resolve(false); };
  });
}

async function runStep(id) {
  if (running) return;
  BLK.step = id;
  clearManual();
  applyBlocks();
  running = true; current = id; renderSteps();
  $('#loghint').textContent = '运行中';
  LOG.textContent = '';
  const ok = await streamStep(id);
  log(ok ? '\n完成。' : '\n失败，看上面的输出。', ok ? 'cmd' : 'err');
  running = false; current = null;
  $('#loghint').textContent = ok ? '完成' : '失败';
  load();
}

$('#browse').onclick = async () => {
  const btn = $('#browse');
  if (btn.disabled) return;
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = '选择中…';
  try {
    const r = await fetch('/api/pick');
    const d = await r.json();
    if (d.path) {
      DIR = d.path;
      $('#dir').value = DIR;
      await load();
    } else if (d.error) {
      log('打开选择框失败：' + d.error + '（可以直接把路径粘进输入框）', 'err');
    }
  } catch (e) {
    log('打开选择框失败：' + e, 'err');
  }
  btn.disabled = false;
  btn.textContent = old;
};
$('#load').onclick = () => { DIR = $('#dir').value.trim(); load(); };
$('#dir').onkeydown = e => { if (e.key === 'Enter') $('#load').click(); };
$('#refresh').onclick = load;
$('#openPreview').onclick = () => {
  if (!state || !state.case) { log('先填目录。', 'err'); return; }
  const sub = '/output/preview.html';
  window.open('/api/file?p=' + encodeURIComponent(state.case.path + sub)
    + '&dir=' + encodeURIComponent(state.case.path), '_blank');
};
async function refreshState() {
  const r = await fetch('/api/state' + qs());
  state = await r.json();
  BLK.cfg = state.blocks.steps;
  applyCopy(state.copy);
  renderSteps();
}

$('#runAll').onclick = async () => {
  if (running) return;
  BLK.step = firstStep();
  clearManual();
  applyBlocks();
  running = true; renderSteps();
  LOG.textContent = '';
  const done = new Set();
  for (;;) {
    await refreshState();
    const ready = state.steps.filter(s => !done.has(s.id) && !s.manual && !s.blocked.length);
    if (!ready.length) break;
    const dep = Math.min(...ready.map(s => s.depth));
    const group = ready.filter(s => s.depth === dep);
    log('\n=== 深度 ' + dep + '（' + group.length + ' 步）===', 'cmd');
    for (const s of group) {
      log('· ' + s.name, 'cmd');
      current = s.id; renderSteps();
      await streamStep(s.id);
      done.add(s.id);
    }
  }
  running = false; current = null;
  $('#loghint').textContent = '完成';
  load();
};

$('#pvzoom').onclick = () => { PVFIT = !PVFIT; applyZoom(); };

$('#mxclear').onclick = async () => {
  if (!Object.keys(SEL).length) return;
  SEL = {};
  renderMatrix();
  try {
    await fetch('/api/select', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dir: DIR, action: (MX && MX.act) || ACT, selection: {} }),
    });
    $('#mxstate').textContent = '全部按自动（已保存）';
    loadPreview();
  } catch (e) { log('清空失败：' + e, 'err'); }
};

if (DIR) $('#dir').value = DIR;
