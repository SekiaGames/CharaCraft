const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s)
  .replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const LOG = $('#log');
let state = null, running = false, current = null;
let DIR = new URLSearchParams(location.search).get('dir') || '';
let TAB = new URLSearchParams(location.search).get('tab') || 'motion';
if (TAB === 'split') TAB = 'motion';
let ACT = new URLSearchParams(location.search).get('action') || 'walk';

function log(text, cls) {
  const span = document.createElement('span');
  if (cls) span.className = cls;
  span.textContent = text + '\n';
  LOG.appendChild(span);
  LOG.scrollTop = LOG.scrollHeight;
}

const qs = () => {
  const p = new URLSearchParams();
  if (DIR) p.set('dir', DIR);
  if (TAB) p.set('tab', TAB);
  if (TAB === 'motion' && ACT) p.set('action', ACT);
  const s = p.toString();
  return s ? '?' + s : '';
};

function showLast() {
  if (!DIR && state && state.dir_input) DIR = state.dir_input;
  if (DIR) $('#dir').value = DIR;
}

function applyCopy(cp) {
  if (!cp) return;
  document.title = cp.page.title;
  $('#apptitle').textContent = cp.page.title;
  document.querySelectorAll('.tab').forEach(b => {
    if (cp.page.tabs[b.dataset.tab]) b.textContent = cp.page.tabs[b.dataset.tab];
  });
  $('#stepstitle').textContent = cp.panel.title;
  $('#acttitle').textContent = cp.panel.actTitle;
  $('#acthint').textContent = cp.panel.actHint || '';
  $('#runAll').textContent = cp.panel.runAll;
  $('#runAll').title = cp.panel.runAllHint;
  $('#openPreview').textContent = cp.panel.preview;
  $('#refresh').textContent = cp.panel.refresh;
}

async function load() {
  if (DIR) {
    const u = new URL(location.href);
    u.searchParams.set('dir', DIR);
    history.replaceState(null, '', u);
  }
  const r = await fetch('/api/state' + qs());
  state = await r.json();
  const c = state.case;
  BLK.cfg = state.blocks.steps;
  applyCopy(state.copy);

  $('#dirhint').textContent = c ? '' : (state.dir_input ? '目录不存在' : '');
  showLast();
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('on', b.dataset.tab === TAB));
  const isMo = TAB === 'motion', isSk = TAB === 'skel', isAt = TAB === 'attach';
  $('#panelSteps').hidden = isSk || isAt;
  $('#panelSkelInfo').hidden = !isSk;
  $('#panelSkelProps').hidden = !isSk;
  $('#panelSkelView').hidden = !isSk;
  $('#panelAttach').hidden = !isAt;
  $('#panelAct').hidden = !isMo || !c;
  $('#panelMx').hidden = !isMo;
  $('#panelPv').hidden = !isMo;
  $('#panelMotion').hidden = !isMo;
  if (!isMo) {
    lpPlay(false);
    gbPlay(false);
    $('#panelSel').hidden = true;
    $('#panelGif').hidden = true;
    $('#panelLoop').hidden = true;
    $('#panelFrame').hidden = true;
  }
  renderActions();
  renderSteps();
  applyBlocks();
  document.querySelector('main').classList.toggle('wide', isAt);
  if (isAt) loadAttach();
  else if (isSk) loadSkeleton();
  else { loadMotion(); loadMatrix(); loadPreview(); }
}
async function postJSON(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                               body: JSON.stringify(body) });
  return r.json().catch(() => ({}));
}

function watchHeader() {
  const h = document.querySelector('header');
  const sync = () => document.documentElement.style.setProperty('--hdr', h.offsetHeight + 'px');
  sync();
  new ResizeObserver(sync).observe(h);
}

watchHeader();
