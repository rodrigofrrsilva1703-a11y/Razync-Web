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
    if (meta) meta.content = theme === "dark" ? "#0e1724" : "#f4f7fb";
  }
  const current = () => valid(preference) ? preference : system.matches ? "dark" : "light";
  apply(current());
  document.addEventListener("DOMContentLoaded", () => {
    apply(current());
    document.querySelector("#themeToggle")?.addEventListener("click", () => {
      preference = root.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem(key, preference); } catch { /* Still works for this visit. */ }
      apply(preference);
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
