(() => {
  const key = "razync:workspace-position:v1";
  const views = new Set(["companies", "converter", "ledger", "fiscal"]);
  const dateIds = ["globalConverterStart", "globalConverterEnd", "ledgerStart", "ledgerEnd",
    "processStart", "processEnd", "reconcileStart", "reconcileEnd", "francesinhasStart", "francesinhasEnd"];
  const fields = new Set([...dateIds, "fiscalFilialCodigo"]);
  let restoring = false;
  let pending = false;

  const element = id => document.getElementById(id);
  const owner = () => window.RazyncSiteAccess?.identity();
  function save() {
    if (restoring || !owner()) return;
    const view = document.querySelector(".global-view.active")?.id.replace(/View$/, "") || "companies";
    const company = view === "companies" && selected && !panel.hidden ? String(selected.codigo) : "";
    const scope = company ? panel : element(view + "View");
    const values = {};
    for (const id of fields) {
      const input = element(id);
      if (!input || !scope?.contains(input) || !input.value || !input.validity.valid) continue;
      values[id] = input.dataset.manualDate ? dateApiValue(input) : input.value;
    }
    try {
      sessionStorage.setItem(key, JSON.stringify({owner:owner(), view,
        wallet:activePortfolio?.id || "", company, tool:company ? panel.dataset.activeTool : "", values}));
      pending = false;
    } catch {}
  }

  async function restore() {
    if (restoring) return;
    restoring = true;
    try {
      await window.RazyncSiteAccess?.ready;
      const saved = JSON.parse(sessionStorage.getItem(key) || "null");
      if (!owner() || saved?.owner !== owner() || !views.has(saved.view)) return;
      pending = true;
      if (saved.view !== "companies") {
        await showGlobalView(saved.view);
        if (!element(saved.view + "View")?.classList.contains("active")) return;
      } else if (saved.wallet) {
        await initialCatalog;
        if (!companies.length) return;
        if (!element("companiesView").classList.contains("active") || activePortfolio || selected) return;
        pending = false;
        if (!portfolios.some(item => item.id === saved.wallet)) return;
        selectPortfolio(saved.wallet);
        const company = companies.find(item => String(item.codigo) === saved.company && companyBelongsToPortfolio(item));
        if (company) {
          openCompany(company);
          const tool = [...panel.querySelectorAll(".tool-tab")].find(button =>
            button.dataset.tool === saved.tool && !button.hidden);
          if (hasCompanyTools(company) && tool) activateTool(saved.tool);
        } else if (saved.company) return;
      }
      pending = false;
      const scope = saved.company ? panel : element(saved.view + "View");
      for (const [id,value] of Object.entries(saved.values || {})) {
        if (!fields.has(id) || typeof value !== "string") continue;
        if (id === "fiscalFilialCodigo" ? !/^\d{1,12}$/.test(value) : !/^\d{4}-\d{2}-\d{2}$/.test(value)) continue;
        const input = element(id);
        if (!scope?.contains(input)) continue;
        input.value = input.dataset.manualDate ? value.split("-").reverse().join("/") : value;
        const options = input.closest("details.company-period-options");
        if (options) options.open = true;
      }
    } catch { /* An unavailable catalog or storage must not block navigation. */ }
    finally { restoring = false; }
  }

  window.RazyncWorkspaceResume = {
    save,
    retry() { if (pending) return restore(); },
    clear() { pending = false; try { sessionStorage.removeItem(key); } catch {} }
  };
  document.addEventListener("change", event => {
    if (fields.has(event.target.id)) save();
  });
  document.addEventListener("input", event => {
    if (fields.has(event.target.id)) save();
  });
  window.addEventListener("pagehide", () => { if (!pending) save(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", restore, {once:true});
  else restore();
})();
