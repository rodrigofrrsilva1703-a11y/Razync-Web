/* Apply before styles paint; a saved choice takes priority over the OS. */
(() => {
  const key = "razync:theme";
  const root = document.documentElement;
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference;
  try { preference = localStorage.getItem(key); } catch { /* Optional storage. */ }
  const valid = value => value === "dark" || value === "light";
  function apply(theme) {
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    const button = document.querySelector("#themeToggle");
    if (button) {
      const dark = theme === "dark";
      button.setAttribute("aria-pressed", String(dark));
      button.setAttribute("aria-label", dark ? "Ativar modo claro" : "Ativar modo escuro");
      button.title = dark ? "Ativar modo claro" : "Ativar modo escuro";
      document.querySelector("#themeToggleLabel").textContent = dark ? "Escuro" : "Claro";
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === "dark" ? "#080808" : "#f4f7fb";
  }
  const current = () => valid(preference) ? preference : system.matches ? "dark" : "light";
  let transition;
  function changeTheme(theme, button) {
    // A second click wins immediately, including while a snapshot is being prepared.
    if (transition) {
      transition.skipTransition();
      apply(theme);
      return;
    }
    if (!document.startViewTransition || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      apply(theme);
      return;
    }
    const bounds = button.getBoundingClientRect();
    const x = bounds.left + bounds.width / 2, y = bounds.top + bounds.height / 2;
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    root.dataset.themeTransition = "active";
    let active;
    try {
      active = document.startViewTransition(() => apply(current()));
      transition = active;
    } catch {
      delete root.dataset.themeTransition;
      apply(theme);
      return;
    }
    // Snapshot capture can stall in background tabs or under rendering pressure.
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      active.skipTransition();
      apply(current());
      if (transition === active) {
        transition = undefined;
        delete root.dataset.themeTransition;
      }
    }, 900);
    active.ready.then(() => {
      if (timedOut) return;
      root.animate({clipPath:[`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`]}, {
        duration:460, easing:"cubic-bezier(.22,1,.36,1)", pseudoElement:"::view-transition-new(root)"
      });
    }).catch(() => { /* Skipped transitions still apply the selected theme. */ });
    active.finished.catch(() => {}).finally(() => {
      clearTimeout(timeout);
      if (transition === active) {
        transition = undefined;
        delete root.dataset.themeTransition;
      }
    });
  }
  apply(current());
  document.addEventListener("DOMContentLoaded", () => {
    apply(current());
    document.querySelector("#themeToggle")?.addEventListener("click", () => {
      preference = root.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem(key, preference); } catch { /* Still works for this visit. */ }
      changeTheme(preference, document.querySelector("#themeToggle"));
    });
  });
  system.addEventListener("change", () => { if (!valid(preference)) apply(current()); });
  window.addEventListener("storage", event => {
    if (event.key === key || event.key === null) {
      preference = event.newValue;
      apply(current());
    }
  });
})();
