function previewRowIssues(headers, row) {
  const labels = headers.map(value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase());
  const issues = [];
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
  if (["modelFile", "classifyFile", "txtModel"].includes(input.id)) return "Abas do modelo";
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

function initializeSidebarControls() {
  const toggle = document.querySelector("#sidebarToggle");
  const sidebar = document.querySelector("#mainSidebar");
  const main = document.querySelector("main");
  const footer = document.querySelector("footer");
  let open = false;
  function setOpen(next, moveFocus = true) {
    open = next;
    document.body.classList.toggle("sidebar-collapsed", !open);
    document.body.classList.toggle("nav-drawer-open", open);
    main.inert = open;
    if (footer) footer.inert = open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Fechar menu lateral" : "Abrir menu lateral");
    toggle.title = open ? "Fechar menu lateral" : "Abrir menu lateral";
    if (!open && moveFocus) toggle.focus();
    sidebar.inert = !open;
    sidebar.setAttribute("aria-hidden", String(!open));
    if (open && moveFocus) sidebar.querySelector(".main-nav-btn.active, .main-nav-btn")?.focus();
  }
  setOpen(false, false);
  toggle.addEventListener("click", () => setOpen(!open));
  document.querySelector("#sidebarClose").addEventListener("click", () => setOpen(false));
  document.querySelector("#sidebarBackdrop").addEventListener("click", () => setOpen(false));
  sidebar.addEventListener("click", event => {
    if (event.target.closest(".main-nav-btn")) setOpen(false);
  });
  document.addEventListener("keydown", event => {
    if (!open) return;
    if (event.key === "Escape") {
      event.preventDefault(); setOpen(false); return;
    }
    if (event.key !== "Tab") return;
    const items = [...sidebar.querySelectorAll('a[href], button:not([disabled])')];
    const first = items[0], last = items.at(-1);
    if (event.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) {
      event.preventDefault(); last?.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) {
      event.preventDefault(); first?.focus();
    }
  });
}

function initializeCompanyControls() {
  initializeSidebarControls();
  const dialog = document.querySelector("#companyDialog");
  const form = document.querySelector("#companyCreateForm");
  const message = document.querySelector("#companyCreateMessage");
  document.querySelector("#addCompany").addEventListener("click", () => {
    form.reset(); message.textContent = ""; dialog.showModal();
  });
  document.querySelector("#closeCompanyDialog").addEventListener("click", () => dialog.close());
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector('[type="submit"]'); button.disabled = true;
    message.textContent = "Criando empresa…";
    try {
      const response = await window.adminFetch(`${API()}/api/v1/companies`, {
        method:"POST", headers:{"Content-Type":"application/json"},
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
    } catch (error) { message.textContent = error.name === "AbortError" ? "Cadastro cancelado. Você pode tentar novamente." : error.message; }
    finally { button.disabled = false; }
  });
}
