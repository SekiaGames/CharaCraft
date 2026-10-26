const $ = (sel) => document.querySelector(sel);

const ui = {
  stage: $('#stage'),
  view: $('#view'),
  drop: $('#dropHint'),
  hud: $('#hud'),
  err: $('#err'),
  fileName: $('#fileName'),
  jsonPick: $('#jsonPick'),
  openFiles: $('#openFiles'),
  openDir: $('#openDir'),
  fileInput: $('#fileInput'),
  dirInput: $('#dirInput'),
  animPick: $('#animPick'),
  animHint: $('#animHint'),
  playBtn: $('#playBtn'),
  stepBack: $('#stepBack'),
  stepFwd: $('#stepFwd'),
  seek: $('#seek'),
  timeLabel: $('#timeLabel'),
  loopChk: $('#loopChk'),
  speed: $('#speed'),
  speedLabel: $('#speedLabel'),
  mix: $('#mix'),
  skins: $('#skins'),
  skinHint: $('#skinHint'),
  skinDefault: $('#skinDefault'),
  skinNone: $('#skinNone'),
  skinAll: $('#skinAll'),
  fitBtn: $('#fitBtn'),
  resetBtn: $('#resetBtn'),
  bgPick: $('#bgPick'),
  boneChk: $('#boneChk'),
  dragChk: $('#dragChk'),
  pmaChk: $('#pmaChk'),
  info: $('#info'),
};

const app = {
  viewer: null,
  bundle: null,
  asset: null,
  skeleton: null,
  state: null,
  stateData: null,
  animName: null,
  skinNames: [],
  playing: false,
  speed: 1,
  loop: true,
  showBones: false,
  pmaMode: 'auto',
  time: 0,
  fps: 60,
  lastFrame: 0,
  drag: null,
  dragging: false,
  pointer: { x: 0, y: 0 },
};

function showError(message) {
  if (!message) {
    ui.err.hidden = true;
    ui.err.textContent = '';
    return;
  }
  ui.err.hidden = false;
  ui.err.textContent = message;
}

function duration() {
  if (!app.asset || !app.animName) return 0;
  const anim = app.asset.data.findAnimation(app.animName);
  return anim ? anim.duration : 0;
}

function syncTransport() {
  const dur = duration();
  ui.seek.max = String(Math.max(dur, 0.0001));
  if (document.activeElement !== ui.seek) ui.seek.value = String(Math.min(app.time, dur));
  ui.timeLabel.textContent = app.time.toFixed(2) + ' / ' + dur.toFixed(2);
  ui.playBtn.textContent = app.playing ? '暂停' : '播放';
  ui.playBtn.classList.toggle('paused', !app.playing);
  ui.animHint.textContent = dur ? dur.toFixed(3) + ' 秒' : '—';
}

function updateHud() {
  const zoom = app.viewer ? app.viewer.renderer.camera.zoom : 1;
  const perUnit = 1 / (zoom * app.viewer.dpr);
  ui.hud.textContent = '1 单位 = ' + perUnit.toFixed(2) + ' px · '
    + Math.round(app.fps) + ' fps · ' + ui.view.clientWidth + '×' + ui.view.clientHeight;
}

function renderInfo() {
  const rows = [];
  const add = (k, v) => {
    rows.push('<dt>' + k + '</dt><dd title="' + String(v) + '">' + String(v) + '</dd>');
  };
  if (!app.asset) {
    add('状态', '未载入');
  } else {
    const d = app.asset.data;
    add('文件', app.asset.jsonFile.name);
    add('图集', app.asset.atlasFile.name);
    add('版本', d.version || '—');
    add('骨骼', d.bones.length);
    add('插槽', d.slots.length);
    add('皮肤', d.skins.filter((s) => s.name !== 'default').length);
    add('动画', d.animations.length);
    add('约束', d.constraints.length);
    add('物理', app.skeleton ? app.skeleton.physics.length : 0);
    add('贴图', app.asset.pages.map((p) => p.width + '×' + p.height).join(' + '));
    add('alpha', app.asset.premultiplied ? '预乘' : '直通');
  }
  ui.info.innerHTML = rows.join('');
}

function renderSkinList() {
  if (!app.asset) {
    ui.skins.innerHTML = '<div class="empty">没有皮肤</div>';
    ui.skinHint.textContent = '—';
    return;
  }
  const names = app.asset.data.skins.map((s) => s.name).filter((n) => n !== 'default');
  if (!names.length) {
    ui.skins.innerHTML = '<div class="empty">只有默认皮肤，没有可切换的</div>';
    ui.skinHint.textContent = '0';
    return;
  }
  ui.skins.innerHTML = names.map((n) => {
    const on = app.skinNames.includes(n) ? ' checked' : '';
    return '<label><input type="checkbox" value="' + n + '"' + on + '>' + n + '</label>';
  }).join('');
  for (const box of ui.skins.querySelectorAll('input')) {
    box.addEventListener('change', () => {
      app.skinNames = Array.from(ui.skins.querySelectorAll('input:checked')).map((i) => i.value);
      applySkin();
    });
  }
  ui.skinHint.textContent = app.skinNames.length + ' / ' + names.length;
  const first = ui.skins.querySelector('input:checked');
  if (first) ui.skins.scrollTop = first.closest('label').offsetTop;
}

function renderAnimList() {
  if (!app.asset) {
    ui.animPick.innerHTML = '';
    return;
  }
  const names = app.asset.data.animations.map((a) => a.name);
  ui.animPick.innerHTML = names.map((n) => '<option value="' + n + '">' + n + '</option>').join('');
  if (!names.length) {
    ui.animPick.innerHTML = '<option value="">（没有动画）</option>';
    ui.animPick.disabled = true;
    return;
  }
  ui.animPick.disabled = false;
  ui.animPick.value = app.animName || names[0];
}

function applySkin() {
  if (!app.skeleton) return;
  const at = app.time;
  const skin = combinedSkin(app.asset.data, app.skinNames);
  app.skeleton.setSkin(skin);
  app.skeleton.setupPoseSlots();
  restartAnimation();
  if (at > 0) seekTo(at);
  ui.skinHint.textContent = app.skinNames.length
    ? app.skinNames.length + ' 套组合'
    : '默认';
}

function restartAnimation() {
  if (!app.state) return;
  app.state.clearTracks();
  app.skeleton.setupPose();
  app.time = 0;
  if (app.animName) {
    const entry = app.state.setAnimation(0, app.animName, app.loop);
    if (entry) entry.trackTime = 0;
  }
  app.state.apply(app.skeleton);
  app.skeleton.updateWorldTransform(spine.Physics.update);
  syncTransport();
}

function switchAnimation(name) {
  if (!app.state || name === app.animName) {
    app.animName = name;
    return;
  }
  app.animName = name;
  if (app.playing && app.state.tracks[0]) {
    app.state.setAnimation(0, name, app.loop);
  } else {
    restartAnimation();
    return;
  }
  app.time = 0;
  syncTransport();
}

function setPlaying(on) {
  if (on && !app.animName) return;
  app.playing = on;
  if (on) app.lastFrame = performance.now();
  syncTransport();
}

function releaseBone() {
  if (app.drag && app.skeleton) {
    const bone = app.skeleton.findBone(app.drag.name);
    if (bone) {
      bone.pose.x = app.drag.baseX;
      bone.pose.y = app.drag.baseY;
    }
  }
  app.drag = null;
}

function applyBoneDrag() {
  if (!app.drag || !app.skeleton) return;
  const bone = app.skeleton.findBone(app.drag.name);
  if (!bone) {
    app.drag = null;
    return;
  }
  const local = app.viewer.toLocalDelta(bone.parent, app.drag.world.x, app.drag.world.y);
  bone.pose.x = app.drag.baseX + local.x;
  bone.pose.y = app.drag.baseY + local.y;
}

function seekTo(seconds) {
  if (!app.state || !app.state.tracks[0]) return;
  const dur = duration();
  const t = Math.max(0, Math.min(dur, seconds));
  app.state.tracks[0].trackTime = t;
  app.state.apply(app.skeleton);
  app.skeleton.updateWorldTransform(spine.Physics.update);
  app.time = t;
  syncTransport();
}

async function openFiles(fileList) {
  const bundle = sortFiles(fileList);
  const candidates = bundle.json.concat(bundle.skel);
  if (!candidates.length) {
    showError('没有找到 .json 或 .skel 文件');
    return;
  }
  if (!bundle.atlas.length) {
    showError('没有找到 .atlas，请把图集和贴图一起选上');
    return;
  }
  app.bundle = bundle;
  ui.jsonPick.hidden = candidates.length < 2;
  ui.jsonPick.innerHTML = candidates.map((f) => '<option value="' + f.name + '">' + f.name + '</option>').join('');
  ui.jsonPick.value = candidates[0].name;
  await loadModel(candidates[0].name);
}

async function loadModel(jsonName) {
  showError('');
  try {
    if (app.asset) {
      for (const page of app.asset.atlas.pages) {
        if (page.texture) page.texture.dispose();
      }
    }
    const asset = await buildSpineAsset(app.bundle, app.viewer.gl, {
      jsonName,
      pma: app.pmaMode,
    });
    app.asset = asset;
    ui.pmaChk.checked = asset.premultiplied;
    app.skeleton = new spine.Skeleton(asset.data);
    app.skinNames = defaultSkinNames(asset.data);
    app.stateData = new spine.AnimationStateData(asset.data);
    app.stateData.defaultMix = Number(ui.mix.value) || 0;
    app.state = new spine.AnimationState(app.stateData);
    const anims = asset.data.animations;
    const idle = anims.find((a) => a.name === 'idle');
    app.animName = anims.length ? (idle || anims[0]).name : null;
    app.playing = false;
    app.time = 0;
    ui.fileName.textContent = asset.jsonFile.name;
    ui.stage.classList.add('loaded');
    renderSkinList();
    renderAnimList();
    renderInfo();
    applySkin();
    app.state.apply(app.skeleton);
    app.skeleton.updateWorldTransform(spine.Physics.update);
    app.viewer.fit(app.skeleton);
    syncTransport();
  } catch (e) {
    showError(e && e.message ? e.message : String(e));
    app.skeleton = null;
    app.asset = null;
    ui.stage.classList.remove('loaded');
    renderInfo();
  }
}

function tick(now) {
  requestAnimationFrame(tick);
  const delta = app.lastFrame ? Math.min(0.1, (now - app.lastFrame) / 1000) : 0;
  app.lastFrame = now;
  if (delta > 0) app.fps = app.fps * 0.9 + (1 / delta) * 0.1;

  if (app.skeleton) {
    const entry = app.state.tracks[0];
    if (app.playing && entry) {
      const step = delta * app.speed;
      app.state.update(step);
      app.skeleton.update(step);
    }
    app.state.apply(app.skeleton);
    applyBoneDrag();
    app.skeleton.updateWorldTransform(spine.Physics.update);
    const active = app.state.tracks[0];
    if (active) {
      app.time = active.getAnimationTime();
      syncTransport();
      if (app.playing && !app.loop && app.time >= duration() - 1e-4) setPlaying(false);
    }
    app.viewer.render(app.skeleton, app.showBones);
  } else {
    app.viewer.render(null, false);
  }
  updateHud();
}

function bindTransport() {
  ui.playBtn.addEventListener('click', () => setPlaying(!app.playing));
  ui.seek.addEventListener('input', () => {
    seekTo(Number(ui.seek.value));
  });
  ui.stepBack.addEventListener('click', () => {
    setPlaying(false);
    seekTo(app.time - 1 / 30);
  });
  ui.stepFwd.addEventListener('click', () => {
    setPlaying(false);
    seekTo(app.time + 1 / 30);
  });
  ui.loopChk.addEventListener('change', () => {
    app.loop = ui.loopChk.checked;
    restartAnimation();
  });
  ui.speed.addEventListener('input', () => {
    app.speed = Number(ui.speed.value);
    ui.speedLabel.textContent = app.speed.toFixed(2) + '×';
  });
  ui.mix.addEventListener('change', () => {
    const value = Math.max(0, Number(ui.mix.value) || 0);
    ui.mix.value = String(value);
    app.stateData.defaultMix = value;
  });
  ui.animPick.addEventListener('change', () => {
    switchAnimation(ui.animPick.value);
  });
}

function bindPickers() {
  ui.openFiles.addEventListener('click', () => ui.fileInput.click());
  ui.openDir.addEventListener('click', () => ui.dirInput.click());
  ui.fileInput.addEventListener('change', () => {
    if (ui.fileInput.files.length) openFiles(ui.fileInput.files);
    ui.fileInput.value = '';
  });
  ui.dirInput.addEventListener('change', () => {
    if (ui.dirInput.files.length) openFiles(ui.dirInput.files);
    ui.dirInput.value = '';
  });
  ui.jsonPick.addEventListener('change', () => loadModel(ui.jsonPick.value));

  const takeDrop = (files) => {
    if (files && files.length) openFiles(files);
  };
  window.addEventListener('dragover', (e) => {
    e.preventDefault();
    ui.stage.classList.add('over');
  });
  window.addEventListener('dragleave', (e) => {
    if (e.target === document.documentElement) ui.stage.classList.remove('over');
  });
  window.addEventListener('drop', (e) => {
    e.preventDefault();
    ui.stage.classList.remove('over');
    takeDrop(e.dataTransfer.files);
  });
}

function bindView() {
  ui.fitBtn.addEventListener('click', () => {
    if (app.skeleton) app.viewer.fit(app.skeleton);
  });
  ui.resetBtn.addEventListener('click', () => {
    const cam = app.viewer.renderer.camera;
    cam.zoom = 1 / app.viewer.dpr;
    if (app.skeleton) {
      const offset = new spine.Vector2();
      const size = new spine.Vector2();
      app.skeleton.getBounds(offset, size, new Array(2), app.viewer.clipper);
      if (Number.isFinite(size.x) && Number.isFinite(size.y) && size.x > 0 && size.y > 0) {
        cam.position.set(offset.x + size.x / 2, offset.y + size.y / 2, 0);
      } else {
        cam.position.set(0, 0, 0);
      }
    }
    cam.update();
  });
  ui.bgPick.addEventListener('change', () => {
    ui.stage.className = 'stage ' + ui.bgPick.value + (ui.stage.classList.contains('loaded') ? ' loaded' : '');
  });
  ui.boneChk.addEventListener('change', () => {
    app.showBones = ui.boneChk.checked;
  });
  ui.pmaChk.addEventListener('change', () => {
    app.pmaMode = ui.pmaChk.checked ? 'premultiplied' : 'straight';
    if (app.bundle && app.asset) loadModel(ui.jsonPick.value || app.asset.jsonFile.name);
  });

  const canvas = ui.view;
  const localPoint = (e) => {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  canvas.addEventListener('pointerdown', (e) => {
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.add('dragging');
    const p = localPoint(e);
    if (ui.dragChk.checked && app.skeleton) {
      const bone = app.viewer.pickBone(app.skeleton, p.x, p.y, 22);
      if (bone) {
        app.drag = {
          name: bone.data.name,
          baseX: bone.pose.x,
          baseY: bone.pose.y,
          from: p,
          world: { x: 0, y: 0 },
        };
        if (!app.playing && app.animName) setPlaying(true);
        return;
      }
    }
    app.dragging = true;
    app.pointer = { x: e.clientX, y: e.clientY };
  });

  canvas.addEventListener('pointermove', (e) => {
    const p = localPoint(e);
    if (app.drag) {
      app.drag.world = app.viewer.worldDelta(app.drag.from.x, app.drag.from.y, p.x, p.y);
      return;
    }
    if (!app.dragging) {
      const hit = ui.dragChk.checked && app.skeleton
        ? app.viewer.pickBone(app.skeleton, p.x, p.y, 22)
        : null;
      canvas.style.cursor = hit ? 'move' : '';
      return;
    }
    const dx = e.clientX - app.pointer.x;
    const dy = e.clientY - app.pointer.y;
    app.pointer = { x: e.clientX, y: e.clientY };
    app.viewer.pan(dx * app.viewer.dpr, dy * app.viewer.dpr);
  });

  const stopDrag = (e) => {
    app.dragging = false;
    canvas.classList.remove('dragging');
    if (e.pointerId !== undefined && canvas.hasPointerCapture(e.pointerId)) {
      canvas.releasePointerCapture(e.pointerId);
    }
  };
  canvas.addEventListener('pointerup', stopDrag);
  canvas.addEventListener('pointercancel', stopDrag);
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const px = (e.clientX - rect.left) * app.viewer.dpr;
    const py = (e.clientY - rect.top) * app.viewer.dpr;
    app.viewer.zoomAt(px, py, Math.exp(-e.deltaY * 0.0015));
  }, { passive: false });
  canvas.addEventListener('dblclick', () => {
    if (app.skeleton) app.viewer.fit(app.skeleton);
  });

  window.addEventListener('resize', () => app.viewer.resize());
  window.addEventListener('keydown', (e) => {
    if (/input|select|textarea/i.test(e.target.tagName)) return;
    if (e.code === 'Escape') releaseBone();
    if (e.code === 'Space') {
      e.preventDefault();
      setPlaying(!app.playing);
    }
    if (e.code === 'ArrowLeft') seekTo(app.time - 1 / 30);
    if (e.code === 'ArrowRight') seekTo(app.time + 1 / 30);
  });
}

function bindSkins() {
  ui.skinDefault.addEventListener('click', () => {
    if (!app.asset) return;
    app.skinNames = defaultSkinNames(app.asset.data);
    renderSkinList();
    applySkin();
  });
  ui.skinNone.addEventListener('click', () => {
    if (!app.asset) return;
    app.skinNames = [];
    renderSkinList();
    applySkin();
  });
  ui.skinAll.addEventListener('click', () => {
    if (!app.asset) return;
    app.skinNames = app.asset.data.skins.map((s) => s.name).filter((n) => n !== 'default');
    renderSkinList();
    applySkin();
  });
}

function start() {
  app.viewer = new SpineViewer(ui.view);
  ui.pmaChk.checked = false;
  bindPickers();
  bindTransport();
  bindView();
  bindSkins();
  renderInfo();
  renderSkinList();
  syncTransport();
  updateHud();
  requestAnimationFrame(tick);
}

window.spinePreview = app;
start();
