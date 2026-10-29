/* Pointer effects are decorative, frame-limited, and disabled on touch/reduced motion. */
(() => {
  const home = document.querySelector('#portfolioPicker');
  if (!home) return;
  const allowed = window.matchMedia('(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)');
  let active, bounds, frame = null, point;
  const properties = ['--pointer-x','--pointer-y','--tilt-x','--tilt-y'];
  function reset() {
    if (frame !== null) window.cancelAnimationFrame(frame);
    frame = null;
    if (active) properties.forEach(name => active.style.removeProperty(name));
    active = bounds = point = null;
  }
  function update() {
    frame = null;
    if (!active?.isConnected || !allowed.matches || document.hidden || home.hidden) { reset(); return; }
    const x = Math.max(0,Math.min(1,(point.x-bounds.left)/bounds.width));
    const y = Math.max(0,Math.min(1,(point.y-bounds.top)/bounds.height));
    active.style.setProperty('--pointer-x',`${(x*100).toFixed(1)}%`);
    active.style.setProperty('--pointer-y',`${(y*100).toFixed(1)}%`);
    active.style.setProperty('--tilt-x',`${((.5-y)*3).toFixed(2)}deg`);
    active.style.setProperty('--tilt-y',`${((x-.5)*3).toFixed(2)}deg`);
  }
  home.addEventListener('pointermove', event => {
    if (!allowed.matches || event.pointerType !== 'mouse') return;
    const target = event.target.closest('.portfolio-entry,.portfolio-heading');
    if (!target || !home.contains(target)) { reset(); return; }
    if (target !== active) {
      reset(); active = target; bounds = target.getBoundingClientRect();
      if (!bounds.width || !bounds.height) { reset(); return; }
    }
    point = {x:event.clientX,y:event.clientY};
    if (frame === null) frame = window.requestAnimationFrame(update);
  });
  home.addEventListener('pointerleave', reset);
  home.addEventListener('click', reset);
  window.addEventListener('resize', reset);
  window.addEventListener('blur', reset);
  window.addEventListener('scroll', reset, {passive:true});
  document.addEventListener('visibilitychange', () => { if (document.hidden) reset(); });
  allowed.addEventListener('change', reset);
})();
