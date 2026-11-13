/* Decorative motion follows accessibility and visibility automatically. */
(() => {
  const home = document.querySelector('#portfolioPicker');
  if (!home) return;
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const apply = () => { home.dataset.motion = media.matches || document.hidden ? 'paused' : 'playing'; };
  document.addEventListener('visibilitychange', apply);
  media.addEventListener('change', apply);
  apply();
})();
