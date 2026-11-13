/* An illustrative carousel. No server calls or financial data. */
(() => {
  const home = document.querySelector('#portfolioPicker');
  const scene = home?.querySelector('.home-showcase');
  if (!scene) return;
  const buttons = [...scene.querySelectorAll('.showcase-step')];
  const panels = [...scene.querySelectorAll('.showcase-panel')];
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  let current = -1, timer = null;
  const duration = 5600;
  let remaining = duration, started = 0;
  const available = () => !media.matches && !document.hidden && !home.hidden &&
    home.dataset.motion !== 'paused' &&
    !document.body.classList.contains('nav-drawer-open');
  function stop() {
    if (timer !== null) {
      remaining = Math.max(0, remaining - (Date.now() - started));
      window.clearTimeout(timer);
    }
    timer = null;
    scene.dataset.playing = 'false';
  }
  function schedule() {
    stop();
    scene.dataset.artMotion = media.matches || document.hidden || home.hidden || home.dataset.motion === 'paused' ? 'paused' : 'playing';
    if (!available()) return;
    scene.dataset.playing = 'true';
    started = Date.now();
    timer = window.setTimeout(() => { timer = null; show((current + 1) % buttons.length); }, remaining);
  }
  function show(index) {
    if (!Number.isInteger(index) || index < 0 || index >= panels.length) return;
    if (index === current) { schedule(); return; }
    stop();
    remaining = duration;
    current = index;
    scene.dataset.stage = String(index);
    buttons.forEach((button, i) => button.setAttribute('aria-pressed', String(i === index)));
    panels.forEach((panel, i) => { panel.hidden = i !== index; });
    schedule();
  }
  buttons.forEach((button, index) => button.addEventListener('click', () => show(index)));
  document.addEventListener('visibilitychange', schedule);
  media.addEventListener('change', schedule);
  const observer = new MutationObserver(schedule);
  observer.observe(home, {attributes:true,attributeFilter:['hidden','data-motion']});
  observer.observe(document.body, {attributes:true,attributeFilter:['class']});
  show(0);
})();