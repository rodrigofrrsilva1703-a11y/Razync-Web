/* The illustration is decorative; it never represents server processing. */
(() => {
  const home = document.querySelector('#portfolioPicker');
  const button = document.querySelector('#homeMotionToggle');
  if (!home || !button) return;
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  let paused = false;
  try { paused = localStorage.getItem('razync:home-motion') === 'paused'; } catch { /* Optional. */ }
  function apply() {
    home.dataset.motion = paused || media.matches || document.hidden ? 'paused' : 'playing';
    button.disabled = media.matches;
    button.setAttribute('aria-pressed', String(paused));
    const label = media.matches ? 'Animações reduzidas pelo sistema' : paused ? 'Retomar animações do início' : 'Pausar animações do início';
    button.setAttribute('aria-label', label);
    button.title = label;
  }
  button.addEventListener('click', () => {
    paused = !paused;
    try { localStorage.setItem('razync:home-motion', paused ? 'paused' : 'playing'); } catch { /* Optional. */ }
    apply();
  });
  document.addEventListener('visibilitychange', apply);
  media.addEventListener('change', apply);
  apply();
})();
