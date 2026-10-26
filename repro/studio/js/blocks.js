function initBlocks() {
  for (const el of blockEls()) {
    const k = el.dataset.blk;
    const h2 = el.querySelector('h2');
    if (!h2) continue;
    const head = [...h2.childNodes].find(n => (n.nodeType === 3 && n.textContent.trim()) ||
      (n.nodeType === 1 && !n.classList.contains('hint')));
    BLK_NAME[k] = ((head && head.textContent) || k).trim();
    const box = document.createElement('span');
    box.className = 'blk-tools';
    const add = document.createElement('button');
    add.textContent = '+';
    add.title = '把收起的区块加回来';
    add.onclick = e => { e.stopPropagation(); openBlkMenu(add); };
    box.append(add);
    if (!BLK_FIXED.has(k)) {
      const del = document.createElement('button');
      del.textContent = '×';
      del.title = '收起这个区块';
      del.onclick = e => {
        e.stopPropagation();
        closeBlkMenu();
        const cur = (BLK.step && BLK.cfg) ? (BLK.cfg[BLK.step] || []) : null;
        if (cur && cur.includes(k)) saveStepBlocks(BLK.step, cur.filter(x => x !== k));
        else { BLK.manual[k] = 'closed'; applyBlocks(); }
      };
      box.append(del);
    }
    h2.appendChild(box);
  }
  applyBlocks();
}

function firstStep() {
  const list = (state && state.steps) || [];
  return list.length ? list[0].id : null;
}

function renderSteps() {
  if (state) {
    const list = state.steps || [];
    if (!list.some(s => s.id === BLK.step)) BLK.step = firstStep();
  }
  const ul = $('#steps');
  ul.innerHTML = '';
  if (!state.steps.length) {
    ul.innerHTML = `<li class="empty">${state.copy.panel.empty}</li>`;
    return;
  }
  let dep = null;
  for (const s of state.steps) {
    if (s.depth !== dep) {
      dep = s.depth;
      const hd = document.createElement('li');
      hd.className = 'depth-hd';
      hd.textContent = '深度 ' + dep;
      ul.appendChild(hd);
    }
    const li = document.createElement('li');
    li.className = 'step' + (s.id === current ? ' running' : '');
    const reasons = s.blocked.join(' · ');
    const mtag = s.manual ? '<span class="tag">手动 · 不进跑一遍</span>' : '';
    const chips = x => (x || []).length
      ? x.map(v => `<code>${esc(v)}</code>`).join('')
      : '<code class="none">—</code>';
    li.dataset.step = s.id;
    li.classList.toggle('sel', BLK.step === s.id);
    li.innerHTML = `<div class="t">${s.name}${mtag}${reasons ? `<span class="tag need">${reasons}</span>` : ''}</div>
      <div class="d">${s.desc}</div>
      <div class="meta">
        <div class="io"><b>脚本</b><span>${chips(s.scripts)}</span></div>
        <div class="io"><b>输入</b><span>${chips(s.ins)}</span></div>
        <div class="io"><b>输出</b><span>${chips(s.outs)}</span></div>
      </div>`;
    const b = document.createElement('button');
    b.textContent = s.id === current ? '运行中' : '运行';
    b.disabled = running || s.blocked.length > 0;
    b.onclick = () => runStep(s.id);
    li.appendChild(b);
    li.onclick = ev => {
      if (ev.target.closest('button')) return;
      BLK.step = s.id;
      clearManual();
      renderSteps();
      applyBlocks();
    };
    ul.appendChild(li);
  }
}
