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

function createPreviewCommand(title, meta) {
  const command = document.createElement("div");
  command.className = "preview-commandbar";
  const info = document.createElement("div");
  info.className = "preview-command-info";
  const ready = document.createElement("span");
  ready.className = "preview-ready-dot";
  ready.setAttribute("aria-hidden", "true");
  const text = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = title;
  const detail = document.createElement("small");
  detail.textContent = meta;
  text.append(heading, detail);
  info.append(ready, text);
  const actions = document.createElement("div");
  actions.className = "preview-primary-actions";
  command.append(info, actions);
  return {command, actions};
}

function initializeWorkspaceUI() {
  initializeCompanyControls();
  const targets = ".standard-preview";
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
    const title = document.createElement("strong");
    title.textContent = target.querySelector(".preview-command-info strong")?.textContent || "Conferir prévia";
    dialog.setAttribute("aria-label", title.textContent);
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
      if (!target.getClientRects().length || !target.querySelector("table") || target.querySelector(".preview-expand") || expanded?.target === target) return;
      const button = document.createElement("button"); button.type = "button";
      button.className = "preview-expand"; button.textContent = "Expandir prévia";
      button.addEventListener("click", () => expandPreview(target, button));
      const toolbar = target.querySelector(".preview-primary-actions");
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
    if (!open && moveFocus) toggle.focus({preventScroll:true});
    sidebar.inert = !open;
    sidebar.setAttribute("aria-hidden", String(!open));
    if (open && moveFocus) sidebar.querySelector(".main-nav-btn.active, .main-nav-btn")?.focus({preventScroll:true});
  }
  setOpen(false, false);
  toggle.addEventListener("click", () => setOpen(!open));
  document.querySelector("#sidebarClose").addEventListener("click", () => setOpen(false));
  document.querySelector("#sidebarBackdrop").addEventListener("click", () => setOpen(false));
  sidebar.addEventListener("click", event => {
    if (event.target.closest(".main-nav-btn, [data-home-link]")) setOpen(false);
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
  initializeCompanyOwners();
  const dialog = document.querySelector("#companyDialog");
  const form = document.querySelector("#companyCreateForm");
  const message = document.querySelector("#companyCreateMessage");
  document.querySelector("#addCompany").addEventListener("click", () => {
    if (!globalThis.jaguarCompanyAccess?.admin) return;
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
      try { if (!window.RazyncSiteAccess?.isPrivate()) localStorage.setItem(`razync:companies:v1:${API()}`, JSON.stringify(companies)); } catch { /* Cache opcional. */ }
      if (dialog.open) {
        search.value = ""; document.querySelector("#regimeFilter").value = ""; companyFilter = "all";
        document.querySelectorAll(".company-filter").forEach(item => { item.classList.toggle("active", item.dataset.filter === "all"); item.setAttribute("aria-pressed", String(item.dataset.filter === "all")); });
        filterCompanies(); dialog.close(); openCompany(company);
      } else filterCompanies();
    } catch (error) { message.textContent = error.name === "AbortError" ? "Cadastro cancelado. Você pode tentar novamente." : error.message; }
    finally { button.disabled = false; }
  });
}

let loadCompanyOwners;
function initializeCompanyOwners() {
  const query = document.querySelector("#ownerCompanySearch");
  if (!query) return;
  const rows = document.querySelector("#ownerCompanyRows");
  const count = document.querySelector("#ownerCompanyCount");
  const message = document.querySelector("#companyOwnerMessage");
  const endpoint = () => `${API()}/api/v1/company-access/assignments`;
  const removalDialog = document.querySelector("#removeCompanyDialog");
  const removalForm = document.querySelector("#removeCompanyForm");
  const removalMessage = document.querySelector("#removeCompanyStatus");
  const removeConfirm = removalForm.querySelector('button[type="submit"]');
  const cancelRemove = document.querySelector("#cancelRemoveCompany");
  let companies = [], users = [], loading = false, removing;
  cancelRemove.onclick = () => removalDialog.close();
  removalDialog.addEventListener("cancel", event => {
    if (removeConfirm.disabled) event.preventDefault();
  });
  removalForm.onsubmit = async event => {
    event.preventDefault();
    if (!removing || removeConfirm.disabled) return;
    const {codigo} = removing;
    removeConfirm.disabled = cancelRemove.disabled = true;
    removalMessage.textContent = "Removendo…";
    try {
      const response = await fetch(`${API()}/api/v1/company-access/companies/${codigo}`, {method:"DELETE"});
      if (!response.ok) throw new Error(await responseError(response));
      companies = companies.filter(row => row.codigo !== codigo);
      drafts.delete(codigo);
      removalDialog.close();
      render();
      query.focus();
      message.textContent = `Empresa ${codigo} removida do catálogo.`;
      await loadCompanies();
    } catch (error) { removalMessage.textContent = error.message; }
    finally { removeConfirm.disabled = cancelRemove.disabled = false; }
  };
  const pending = new Set();
  const drafts = new Map();

  function render() {
    const term = query.value.trim().toLocaleLowerCase("pt-BR");
    const matching = companies.filter(row => `${row.codigo} ${row.nome} ${row.email}`.toLocaleLowerCase("pt-BR").includes(term));
    count.textContent = `${matching.length} de ${companies.length} empresas`;
    rows.replaceChildren();
    for (const company of matching) {
      const row = rows.insertRow();
      row.insertCell().textContent = company.codigo;
      row.insertCell().textContent = company.nome;
      const select = document.createElement("select");
      select.setAttribute("aria-label", `Responsável pela empresa ${company.codigo}`);
      select.append(new Option("Selecione um responsável", ""));
      if (company.email && !users.includes(company.email)) {
        select.append(new Option(company.email + " (sem acesso)", company.email));
      }
      for (const email of users) select.append(new Option(email, email));
      select.value = drafts.get(company.codigo) ?? company.email ?? "";
      select.disabled = pending.has(company.codigo);
      row.insertCell().append(select);
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Salvar";
      button.setAttribute("aria-label", `Salvar responsável da empresa ${company.codigo}`);
      button.disabled = true;
      const actions = row.insertCell();
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remover";
      remove.disabled = pending.has(company.codigo);
      remove.setAttribute("aria-label", `Remover empresa ${company.codigo}`);
      remove.onclick = () => {
        removing = company;
        document.querySelector("#removeCompanyName").textContent = `${company.codigo} · ${company.nome}`;
        removalMessage.textContent = "";
        removalDialog.showModal();
      };
      actions.append(button, " ", remove);
      const updateButton = () => { button.disabled = !users.includes(select.value) || select.value === company.email; };
      select.addEventListener("change", () => {
        if (select.value === company.email) drafts.delete(company.codigo);
        else drafts.set(company.codigo, select.value);
        updateButton();
      });
      if (!pending.has(company.codigo)) updateButton();
      button.addEventListener("click", async () => {
        const email = select.value;
        pending.add(company.codigo);
        select.disabled = button.disabled = remove.disabled = true;
        message.textContent = `Salvando empresa ${company.codigo}…`;
        try {
          const response = await fetch(`${endpoint()}/${company.codigo}`, {
            method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({email})
          });
          if (!response.ok) throw new Error(await responseError(response));
          const saved = await response.json();
          company.email = saved.email;
          drafts.delete(company.codigo);
          message.textContent = saved.changed === false
            ? `O responsável pela empresa ${company.codigo} já estava atualizado.`
            : `Responsável da empresa ${company.codigo} atualizado${saved.changed ? " e notificado" : ""}.`;
        } catch (error) { message.textContent = error.message; }
        finally {
          pending.delete(company.codigo);
          if (row.isConnected) {
            select.disabled = remove.disabled = false;
            updateButton();
          } else render();
        }
      });
    }
    if (!matching.length) {
      const cell = rows.insertRow().insertCell();
      cell.colSpan = 4;
      cell.textContent = "Nenhuma empresa encontrada.";
    }
  }

  query?.addEventListener("input", render);
  loadCompanyOwners = async () => {
    if (loading || pending.size) return;
    loading = true;
    query.disabled = true;
    rows.replaceChildren();
    count.textContent = "";
    message.textContent = "Carregando empresas…";
    try {
      const response = await fetch(endpoint());
      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json();
      companies = data.companies;
      drafts.clear();
      users = data.users;
      render();
      message.textContent = "";
    } catch (error) { message.textContent = error.message; }
    finally { loading = false; query.disabled = false; }
  };
}

let loadCompanyNotifications;
function initializeCompanyNotifications() {
  const nav = document.querySelector("#companyNotificationsNav");
  if (!nav) return;
  const badge = document.querySelector("#companyNotificationsBadge");
  const toast = document.querySelector("#companyNotificationToast");
  if (typeof toast.showPopover !== "function") toast.removeAttribute("popover");
  const toastText = document.querySelector("#companyNotificationToastText");
  const announcement = document.querySelector("#companyNotificationAnnouncement");
  const list = document.querySelector("#companyNotificationsList");
  const status = document.querySelector("#companyNotificationsStatus");
  const markRead = document.querySelector("#companyNotificationsRead");
  const endpoint = () => `${API()}/api/v1/company-access/notifications`;
  const date = new Intl.DateTimeFormat("pt-BR", {dateStyle:"short", timeStyle:"short"});
  let latest = null;
  let seen = 0;
  let seenKey;
  let pending;
  let toastTimer;
  let toastOpen = false;
  let saving = false;

  function dismissToast() {
    clearTimeout(toastTimer);
    if (toast.hasAttribute("popover") && toast.matches(":popover-open")) toast.hidePopover();
    toast.hidden = true;
    toastOpen = false;
    announcement.textContent = "";
  }

  function scheduleToastDismissal() {
    clearTimeout(toastTimer);
    if (toastOpen && !document.hidden) toastTimer = setTimeout(dismissToast, 5000);
  }

  function showToast(items) {
    const [item] = items;
    const company = `${item.company} · ${item.name}`;
    const message = items.length > 1
      ? `${company} e mais ${items.length - 1} ${items.length === 2 ? "empresa atribuída" : "empresas atribuídas"}.`
      : company;
    toastText.textContent = message;
    toast.hidden = false;
    toastOpen = true;
    if (toast.hasAttribute("popover") && !toast.matches(":popover-open")) {
      try { toast.showPopover(); }
      catch { toast.removeAttribute("popover"); }
    }
    announcement.textContent = `Nova atribuição de empresa. ${message}`;
    scheduleToastDismissal();
  }

  document.querySelector("#companyNotificationToastClose").addEventListener("click", dismissToast);
  nav.addEventListener("click", () => {
    dismissToast();
    void showGlobalView("companyNotifications");
  });

  function render(data) {
    badge.textContent = data.unread > 99 ? "99+" : data.unread;
    badge.hidden = !data.unread;
    nav.setAttribute("aria-label", data.unread ? `Notificações, ${data.unread} não lidas` : "Notificações");
    markRead.hidden = !data.unread;
    status.textContent = data.items.length ? "" : "Nenhuma notificação por enquanto.";
    list.replaceChildren();
    for (const item of data.items) {
      const row = document.createElement("li");
      const summary = document.createElement("div");
      const title = document.createElement("strong");
      const detail = document.createElement("p");
      const time = document.createElement("time");
      title.textContent = `${item.company} · ${item.name}`;
      detail.textContent = "Você agora é responsável por esta empresa.";
      time.dateTime = item.created_at;
      time.textContent = date.format(new Date(item.created_at));
      summary.append(title, detail);
      row.append(summary, time);
      if (!item.read_at) {
        const label = document.createElement("span");
        label.className = "company-notification-unread";
        label.textContent = "Nova";
        title.after(label);
      }
      list.append(row);
    }
  }

  loadCompanyNotifications = (interactive = false) => {
    if (pending) return pending;
    if (saving || !globalThis.RazyncSiteAccess?.identity()) return;
    if (interactive && latest === null) status.textContent = "Carregando notificações…";
    pending = (async () => {
      try {
        const response = await fetch(endpoint(), {signal:AbortSignal.timeout(10000)});
        if (!response.ok) throw new Error();
        const data = await response.json();
        const newest = data.items[0]?.id ?? 0;
        if (latest !== null && latest !== newest) void loadCompanies();
        latest = newest;
        if (!document.hidden && newest > seen) {
          const fresh = data.items.filter(item => item.id > seen && !item.read_at);
          if (fresh.length) showToast(fresh);
          seen = newest;
          try { sessionStorage.setItem(seenKey, String(seen)); } catch {}
        }
        render(data);
      } catch {
        if (interactive || latest === null) status.textContent = "Não foi possível carregar as notificações. Abra esta tela novamente para tentar.";
      }
    })().finally(() => { pending = null; });
    return pending;
  };

  markRead.addEventListener("click", async () => {
    if (pending) await pending;
    if (saving || !latest || markRead.hidden) return;
    saving = markRead.disabled = true;
    try {
      const response = await fetch(`${endpoint()}/read`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({through:latest}), signal:AbortSignal.timeout(10000)
      });
      if (!response.ok) throw new Error();
    } catch {
      status.textContent = "Não foi possível marcar as notificações como lidas. Tente novamente.";
      return;
    } finally {
      saving = markRead.disabled = false;
    }
    await loadCompanyNotifications(true);
  });

  globalThis.RazyncSiteAccess?.ready.then(() => {
    const identity = globalThis.RazyncSiteAccess.identity();
    if (!identity) return;
    seenKey = `jaguar:notification-displayed:${identity}`;
    try { seen = Number(sessionStorage.getItem(seenKey)) || 0; } catch {}
    nav.hidden = false;
    const refresh = () => { if (!document.hidden) void loadCompanyNotifications(); };
    refresh();
    setInterval(refresh, 5000);
    document.addEventListener("visibilitychange", () => {
      scheduleToastDismissal();
      refresh();
    });
  });
}

globalThis.document?.addEventListener?.("DOMContentLoaded", initializeCompanyNotifications, {once:true});
