(() => {
  const key = "razync:workspace-position:v1";
  const views = new Set(["companies", "converter", "ledger", "fiscal"]);
  const dateIds = ["globalConverterStart", "globalConverterEnd", "ledgerStart", "ledgerEnd",
    "processStart", "processEnd", "reconcileStart", "reconcileEnd", "francesinhasStart", "francesinhasEnd"];
  const fields = new Set([...dateIds, "fiscalFilialCodigo"]);
  let restoring = false;
  let pending = false;

  const root = document.documentElement;
  function savedPosition() {
    try { return JSON.parse(sessionStorage.getItem(key) || "null"); }
    catch { return null; }
  }
  const hasDestination = saved => views.has(saved?.view) && (saved.view !== "companies" || Boolean(saved.wallet));
  function beginTransition() {
    if (hasDestination(savedPosition())) root.dataset.workspaceRestoring = "";
  }
  function endTransition() {
    delete root.dataset.workspaceRestoring;
  }
  beginTransition();

  const element = id => document.getElementById(id);
  const owner = () => window.RazyncSiteAccess?.identity();
  const fileDrafts = () => window.RazyncWorkspaceFiles;
  const filePosition = ({owner, view, company, tool}) => JSON.stringify([owner, view, company, tool || ""]);
  function fileScope({view, company, tool}) {
    return company ? panel.querySelector(`.tool-pane[data-pane="${CSS.escape(tool || "")}"]`) : element(view + "View");
  }

  function leave(view, company = "", tool = "") {
    if (restoring || !fileDrafts()) return;
    const saved = savedPosition();
    if (!saved || saved.owner !== owner()) return;
    if (filePosition(saved) === filePosition({owner:owner(), view, company, tool})) return;
    const scope = fileScope(saved);
    for (const input of scope?.querySelectorAll('input[type="file"]') || []) {
      if (input.files.length) replaceInputFiles(input, []);
    }
    fileDrafts().clear().catch(() => {});
  }
  function save() {
    if (restoring || !owner()) return;
    const view = document.querySelector(".global-view.active")?.id.replace(/View$/, "") || "companies";
    const company = view === "companies" && selected && !panel.hidden ? String(selected.codigo) : "";
    const scope = company ? panel : element(view + "View");
    const tool = company ? panel.dataset.activeTool : "";
    const bankControls = fileDrafts() && fileScope({view, company, tool})?.querySelectorAll('[data-bank-choice]');
    const banks = bankControls?.length ? [...bankControls].filter(input => input.checked).map(input => input.value) : undefined;
    const values = {};
    for (const id of fields) {
      const input = element(id);
      if (!input || !scope?.contains(input) || !input.value || !input.validity.valid) continue;
      values[id] = input.dataset.manualDate ? dateApiValue(input) : input.value;
    }
    try {
      sessionStorage.setItem(key, JSON.stringify({owner:owner(), view,
        wallet:activePortfolio?.id || "", company, tool, values, banks}));
      pending = false;
    } catch {}
  }

  async function restore() {
    if (restoring) return;
    restoring = true;
    try {
      await window.RazyncSiteAccess?.ready;
      const saved = savedPosition();
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
      if (fileDrafts() && (!saved.company || panel.dataset.activeTool === saved.tool)) {
        const draftScope = fileScope(saved);
        if (draftScope) {
          if (Array.isArray(saved.banks)) {
            for (const input of draftScope.querySelectorAll('[data-bank-choice]')) {
              const checked = saved.banks.includes(input.value);
              if (input.checked === checked || (input.type === "radio" && !checked)) continue;
              input.checked = checked;
              input.dispatchEvent(new Event("change", {bubbles:true}));
            }
          }
          await fileDrafts().restore(filePosition(saved), draftScope);
        }
      }
    } catch { /* An unavailable catalog or storage must not block navigation. */ }
    finally { restoring = false; endTransition(); }
  }

  window.RazyncWorkspaceResume = {
    save,
    leave,
    beginTransition,
    endTransition,
    retry() { if (pending) return restore(); },
    async clear() {
      pending = false;
      try { sessionStorage.removeItem(key); await fileDrafts()?.clear(); } catch {}
    }
  };
  document.addEventListener("change", event => {
    if (fields.has(event.target.id)) save();
    if (restoring || !fileDrafts() || (event.target.type !== "file" && !event.target.dataset?.bankChoice)) return;
    const saved = savedPosition();
    if (!saved || saved.owner !== owner()) return;
    const scope = fileScope(saved);
    if (scope?.contains(event.target)) {
      save();
      fileDrafts().save(filePosition(saved), scope).catch(() => {});
    }
  });
  document.addEventListener("input", event => {
    if (fields.has(event.target.id)) save();
  });
  window.addEventListener("pagehide", () => { if (!pending) save(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", restore, {once:true});
  else restore();
})();
