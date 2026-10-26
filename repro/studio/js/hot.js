let hotBoot = null, hotUi = null, hotTimer = null, hotFails = 0;
async function pollHot() {
  let h;
  try {
    const r = await fetch('/api/hot', { cache: 'no-store' });
    if (!r.ok) throw new Error(r.status);
    h = await r.json();
    hotFails = 0;
  } catch (e) {
    hotFails++;
    if (hotFails > 40) clearInterval(hotPoll);
    return;
  }
  if (hotBoot === null) { hotBoot = h.boot; hotUi = h.ui; }
  else if (h.boot !== hotBoot) { location.reload(); return; }
  else if (h.ui !== hotUi) { location.reload(); return; }

  const el = $('#hot');
  const stale = h.disk !== h.boot;
  el.hidden = !stale;
  if (!stale) { clearTimeout(hotTimer); return; }
  el.textContent = h.watching
    ? (h.runs ? '代码已更新，等这一步跑完…' : '代码已更新，正在重启…')
    : '代码已更新（未开热更，需重启）';
  el.onclick = () => location.reload();
  const typing = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if (h.watching && !h.runs && !running && !typing) {
    clearTimeout(hotTimer);
    hotTimer = setTimeout(() => location.reload(), 900);
  }
}
const hotPoll = setInterval(pollHot, 1500);
pollHot();
