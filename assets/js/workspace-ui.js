function previewRowIssues(headers, row) {
  const labels = headers.map(value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase());
  const issues = [];
  if (["DEBITO", "CREDITO"].some(label => {
    const index = labels.indexOf(label);
    return index >= 0 && (!String(row[index] ?? "").trim() || Number(row[index]) === 0);
  })) issues.push("Conta pendente");
  const dateIndex = labels.indexOf("DATA");
  if (dateIndex >= 0) {
    let date = String(row[dateIndex] ?? "").trim();
    if (/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(date)) date = date.slice(0,10).split("-").reverse().join("/");
    if (!date || typedDateToISO(date) === null) issues.push("Data inválida");
  }
  return issues;
}

function selectedFileBankLabel(input) {
  const banks = selected?.capabilities?.banks || {};
  const bank = input.dataset.bank || input.dataset.reconcileBank
    || (banks[input.dataset.role] ? input.dataset.role : "")
    || (input.id === "fileInput" ? bankSelect.value : "")
    || (input.closest?.("#processForm") && Object.keys(banks).length === 1 ? Object.keys(banks)[0] : "");
  if (bank) return bankLabel(bank, banks[bank]);
  if (["modelFile", "classifyFile", "reviewFile", "txtModel"].includes(input.id)) return "Abas do modelo";
  return "Identificado no processamento";
}

function initializeWorkspaceUI() {
  initializeCompanyControls();
  const targets = "#workflowPreview, #classificationPreview, #reconcileResult, #ledgerResult";
  const main = document.querySelector("main");
  const bar = document.createElement("div");
  bar.className = "mobile-preview-actions"; bar.hidden = true;
  bar.setAttribute("aria-label", "Ações da prévia");
  const info = document.createElement("span"); info.textContent = "Prévia pronta";
  const review = document.createElement("button"); review.type = "button"; review.textContent = "Conferir";
  const download = document.createElement("button"); download.type = "button"; download.textContent = "Baixar Excel";
  bar.append(info, review, download); document.body.append(bar);
  let activeTarget, activeDownload, expanded, frame;

  function expandPreview(target, trigger) {
    if (expanded) return;
    const dialog = document.createElement("dialog"); dialog.className = "preview-dialog";
    dialog.setAttribute("aria-label", "Prévia expandida");
    const anchor = document.createComment("preview-position"); target.before(anchor);
    const header = document.createElement("div"); header.className = "preview-dialog-header";
    const title = document.createElement("strong"); title.textContent = "Conferir prévia";
    const close = document.createElement("button"); close.type = "button"; close.textContent = "Fechar prévia";
    close.addEventListener("click", () => dialog.close()); header.append(title, close);
    anchor.parentNode.append(dialog); dialog.append(header, target);
    expanded = {dialog, target}; document.body.classList.add("preview-modal-open");
    dialog.addEventListener("close", () => {
      anchor.replaceWith(target); dialog.remove(); expanded = null;
      document.body.classList.remove("preview-modal-open");
      if (trigger.isConnected) trigger.focus(); schedule();
    }, {once:true});
    dialog.showModal(); schedule();
  }

  function update() {
    frame = null;
    if (expanded && !expanded.target.querySelector("table")) expanded.dialog.close();
    main.querySelectorAll(targets).forEach(target => {
      if (!target.querySelector("table") || target.querySelector(".preview-expand")) return;
      const button = document.createElement("button"); button.type = "button";
      button.className = "preview-expand"; button.textContent = "Expandir prévia";
      button.addEventListener("click", () => expandPreview(target, button));
      const toolbar = target.querySelector(".preview-primary-actions, .daily-toolbar");
      if (toolbar) toolbar.append(button); else target.prepend(button);
    });
    activeTarget = [...main.querySelectorAll(targets)].find(target =>
      target.getClientRects().length && target.querySelector("table") && target.querySelector(".preview-download, .daily-download"));
    activeDownload = activeTarget?.querySelector(".preview-download, .daily-download");
    const show = window.matchMedia("(max-width: 760px)").matches && Boolean(activeDownload) && !expanded;
    bar.hidden = !show; document.body.classList.toggle("has-mobile-preview", show);
    download.disabled = Boolean(activeDownload?.disabled);
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(update); }
  review.addEventListener("click", () => activeTarget?.scrollIntoView({behavior:"smooth", block:"start"}));
  download.addEventListener("click", () => {
    if (activeDownload?.isConnected && !activeDownload.disabled && activeTarget.getClientRects().length) activeDownload.click();
  });
  new MutationObserver(schedule).observe(main, {
    childList:true, subtree:true, attributes:true,
    attributeFilter:["hidden", "class", "disabled", "data-active-tool"]
  });
  window.addEventListener("resize", schedule); schedule();
}

function initializeCompanyControls() {
  const toggle = document.querySelector("#sidebarToggle");
  let collapsed = false;
  try { collapsed = localStorage.getItem("razync.sidebar-collapsed") === "true"; } catch (_) {}
  const applySidebar = () => {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", collapsed ? "Abrir menu lateral" : "Recolher menu lateral");
    toggle.title = collapsed ? "Abrir menu lateral" : "Recolher menu lateral";
  };
  applySidebar();
  toggle.addEventListener("click", () => {
    collapsed = !collapsed; applySidebar();
    try { localStorage.setItem("razync.sidebar-collapsed", String(collapsed)); } catch (_) {}
    window.dispatchEvent(new Event("resize"));
  });
  const dialog = document.querySelector("#companyDialog");
  const form = document.querySelector("#companyCreateForm");
  const message = document.querySelector("#companyCreateMessage");
  document.querySelector("#addCompany").addEventListener("click", () => {
    form.reset(); message.textContent = ""; dialog.showModal();
  });
  document.querySelector("#closeCompanyDialog").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => document.querySelector("#companyCreateKey").value = "");
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector('[type="submit"]'); button.disabled = true;
    message.textContent = "Criando empresa…";
    try {
      const response = await fetch(`${API()}/api/v1/companies`, {
        method:"POST", headers:{"Content-Type":"application/json", Authorization:`Bearer ${document.querySelector("#companyCreateKey").value}`},
        body:JSON.stringify({codigo:document.querySelector("#newCompanyCode").value, nome:document.querySelector("#newCompanyName").value, regime:document.querySelector("#newCompanyRegime").value})
      });
      if (!response.ok) throw new Error(await responseError(response));
      const company = await response.json();
      companies = [...companies.filter(item => Number(item.codigo) !== Number(company.codigo)), company];
      if (dialog.open) {
        search.value = ""; document.querySelector("#regimeFilter").value = ""; companyFilter = "all";
        document.querySelectorAll(".company-filter").forEach(item => { item.classList.toggle("active", item.dataset.filter === "all"); item.setAttribute("aria-pressed", String(item.dataset.filter === "all")); });
        filterCompanies(); dialog.close(); openCompany(company);
      } else filterCompanies();
    } catch (error) { message.textContent = error.message; }
    finally { button.disabled = false; }
  });
}
