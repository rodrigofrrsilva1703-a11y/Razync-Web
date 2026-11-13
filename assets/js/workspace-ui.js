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
  initializeUserAccess();
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
      if (document.querySelector("#companyOwnersView").classList.contains("active")) {
        dialog.close();
        await Promise.all([loadCompanies(), loadCompanyOwners?.()]);
      } else if (dialog.open) {
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
      removalDialog.close();
      render();
      query.focus();
      message.textContent = `Empresa ${codigo} removida do catálogo.`;
      await loadCompanies();
    } catch (error) { removalMessage.textContent = error.message; }
    finally { removeConfirm.disabled = cancelRemove.disabled = false; }
  };
  const pending = new Set();

  function render() {
    const term = query.value.trim().toLocaleLowerCase("pt-BR");
    const matching = companies.filter(row => `${row.codigo} ${row.nome} ${row.email}`.toLocaleLowerCase("pt-BR").includes(term));
    count.textContent = `${matching.length} de ${companies.length} empresas`;
    rows.replaceChildren();
    for (const company of matching) {
      const row = rows.insertRow();
      const companyCell = row.insertCell();
      const name = document.createElement("strong");
      const code = document.createElement("small");
      name.textContent = company.nome;
      code.textContent = "#" + company.codigo;
      companyCell.append(name, code);
      const ownerCell = row.insertCell();
      ownerCell.textContent = company.email || "Sem responsável";
      const regimeCell = row.insertCell();
      regimeCell.textContent = company.regime || "Não informado";
      const actions = row.insertCell();
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "admin-action admin-edit";
      edit.textContent = "Alterar";
      edit.disabled = pending.has(company.codigo);
      edit.setAttribute("aria-label", "Alterar empresa " + company.codigo);
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Salvar";
      button.disabled = true;
      button.hidden = true;
      const select = document.createElement("select");
      select.setAttribute("aria-label", "Responsável pela empresa " + company.codigo);
      select.append(new Option("Sem responsável", ""));
      if (company.email && !users.includes(company.email)) select.add(new Option(company.email, company.email));
      for (const email of users) select.add(new Option(email, email));
      select.value = company.email || "";
      const regime = document.createElement("select");
      regime.setAttribute("aria-label", "Regime tributário da empresa " + company.codigo);
      const regimes = ["Não informado", "LUCRO REAL", "LUCRO PRESUMIDO", "SIMPLES NACIONAL"];
      const currentRegime = company.regime || regimes[0];
      for (const value of new Set([currentRegime, ...regimes])) regime.add(new Option(value, value));
      regime.value = currentRegime;
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = "Cancelar";
      cancel.hidden = true;
      cancel.onclick = () => {
        ownerCell.textContent = company.email || "Sem responsável";
        regimeCell.textContent = currentRegime;
        select.value = company.email || "";
        regime.value = currentRegime;
        button.disabled = button.hidden = cancel.hidden = true;
        edit.hidden = false;
        edit.focus();
      };
      edit.onclick = () => {
        ownerCell.replaceChildren(select);
        regimeCell.replaceChildren(regime);
        edit.hidden = true;
        button.hidden = cancel.hidden = false;
        select.focus();
      };
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
      remove.className = "admin-action admin-remove";
      actions.append(edit, button, cancel, remove);
      const updateButton = () => {
        button.disabled = (!users.includes(select.value) && select.value !== (company.email || "")) ||
          (select.value === (company.email || "") && regime.value === currentRegime);
      };
      select.onchange = regime.onchange = updateButton;
      button.addEventListener("click", async () => {
        const update = {};
        if (select.value !== (company.email || "")) update.email = select.value;
        if (regime.value !== currentRegime) update.regime = regime.value;
        pending.add(company.codigo);
        let updated = false;
        select.disabled = regime.disabled = button.disabled = cancel.disabled = remove.disabled = true;
        message.textContent = `Salvando empresa ${company.codigo}…`;
        try {
          const response = await fetch(`${endpoint()}/${company.codigo}`, {
            method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(update)
          });
          if (!response.ok) throw new Error(await responseError(response));
          const saved = await response.json();
          Object.assign(company, saved);
          updated = true;
          message.textContent = saved.changed ? "Empresa atualizada e responsável notificado." : "Regime tributário atualizado.";
          await loadCompanies();
        } catch (error) {
          message.textContent = error.message;
        } finally {
          pending.delete(company.codigo);
          if (updated || !row.isConnected) {
            render();
            rows.querySelector(`button[aria-label="Alterar empresa ${company.codigo}"]`)?.focus({preventScroll:true});
          } else {
            select.disabled = regime.disabled = cancel.disabled = remove.disabled = false;
            updateButton();
          }
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
  const composer = document.querySelector("#companyNotificationCompose");
  const sendForm = document.querySelector("#companyNotificationForm");
  const recipientField = document.querySelector("#companyNotificationRecipient");
  const bodyField = document.querySelector("#companyNotificationBody");
  const sendStatus = document.querySelector("#companyNotificationSendStatus");
  const sendButton = sendForm.querySelector("button");
  const endpoint = () => `${API()}/api/v1/company-access/notifications`;
  const date = new Intl.DateTimeFormat("pt-BR", {dateStyle:"short", timeStyle:"short"});
  const noticeLabels = {help:"Pedido de ajuda", review:"Pedido de revisão", reply:"Resposta na tarefa", resolved:"Pendência resolvida"};
  let latest = null;
  let seen = 0;
  let seenKey;
  let pending;
  let toastTimer;
  let toastOpen = false;
  let saving = false;
  let availableRecipients;

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
      ? `${items.length} novos avisos na caixa de notificações.`
      : item.kind === "direct" ? `Mensagem de ${item.sender}`
        : `${noticeLabels[item.kind] ?? "Nova atribuição de empresa"} · ${company}`;
    toastText.textContent = message;
    toast.hidden = false;
    toastOpen = true;
    if (toast.hasAttribute("popover") && !toast.matches(":popover-open")) {
      try { toast.showPopover(); }
      catch { toast.removeAttribute("popover"); }
    }
    announcement.textContent = message;
    scheduleToastDismissal();
  }

  document.querySelector("#companyNotificationToastClose").addEventListener("click", dismissToast);
  nav.addEventListener("click", () => {
    dismissToast();
    void showGlobalView("companyNotifications");
  });

  function render(data) {
    composer.hidden = !Array.isArray(data.recipients);
    if (!composer.hidden && JSON.stringify(data.recipients) !== availableRecipients) {
      availableRecipients = JSON.stringify(data.recipients);
      const selected = recipientField.value;
      recipientField.replaceChildren(new Option("Selecione o colaborador", ""));
      for (const email of data.recipients) recipientField.add(new Option(email, email));
      recipientField.value = data.recipients.includes(selected) ? selected : "";
    }
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
      const direct = item.kind === "direct";
      title.textContent = direct ? "Mensagem da administração" : `${item.company} · ${item.name}`;
      detail.textContent = direct ? item.sender : item.kind
        ? `${noticeLabels[item.kind]} · ${item.period.split("-").reverse().join("/")}`
        : "Você agora é responsável por esta empresa.";
      time.dateTime = item.created_at;
      time.textContent = date.format(new Date(item.created_at));
      summary.append(title, detail);
      if (item.body) {
        const preview = document.createElement("p");
        preview.className = "company-notice-preview";
        preview.textContent = item.body;
        summary.append(preview);
      }
      const open = document.createElement("button");
      open.type = "button";
      open.className = "secondary-action";
      open.textContent = direct ? "Marcar como lida" : "Abrir tarefa";
      open.onclick = async () => {
        if (!direct && !await showGlobalView("tasks", {company:item.company, period:item.period})) return;
        if (item.read_at) return;
        try {
          const response = await fetch(`${endpoint()}/read`, {
            method:"POST", headers:{"Content-Type":"application/json"},
            body:JSON.stringify({through:item.id, single:true}), signal:AbortSignal.timeout(10000)
          });
          if (response.ok) await loadCompanyNotifications();
        } catch {
          // The task is open. Keep the notice unread if the update fails.
        }
      };
      if (!direct || !item.read_at) summary.append(open);
      row.append(summary, time);
      if (!item.read_at) {
        const label = document.createElement("span");
        label.className = "company-notification-unread";
        label.textContent = item.kind === "help" || item.kind === "review" ? "Precisa de ação" : "Nova";
        title.after(label);
      }
      list.append(row);
    }
  }

  sendForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (sendButton.disabled) return;
    sendButton.disabled = true;
    sendStatus.textContent = "Enviando…";
    try {
      const response = await fetch(`${endpoint()}/send`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({recipient:recipientField.value, body:bodyField.value}),
        signal:AbortSignal.timeout(10000)
      });
      if (!response.ok) throw new Error(await responseError(response));
      sendForm.reset();
      sendStatus.textContent = "Mensagem enviada.";
    } catch (error) {
      sendStatus.textContent = error.message || "Não foi possível confirmar o envio.";
    } finally {
      sendButton.disabled = false;
    }
  });

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

let loadUserAccess;
function initializeUserAccess() {
  const search = document.querySelector("#userAccessSearch");
  if (!search) return;
  const rows = document.querySelector("#userAccessRows");
  const count = document.querySelector("#userAccessCount");
  const message = document.querySelector("#userAccessMessage");
  const filters = document.querySelector("#userAccessFilters");
  const endpoint = () => `${API()}/api/v1/company-access/users`;
  const pending = new Set();
  let users = [], loading = false, selectedFilter = "all";
  const clock = new Intl.DateTimeFormat("pt-BR", {timeZone:"America/Sao_Paulo", dateStyle:"short", timeStyle:"short"});
  const formatTime = seconds => seconds == null ? "—" : clock.format(new Date(seconds * 1000));

  function render(animate = false) {
    const term = search.value.trim().toLowerCase();
    const online = user => !user.suspended && user.connected;
    const subsets = {all:users, online:users.filter(online), suspended:users.filter(user => user.suspended)};
    for (const button of filters.querySelectorAll("button")) {
      button.firstElementChild.textContent = subsets[button.dataset.accessFilter].length;
      button.setAttribute("aria-pressed", String(button.dataset.accessFilter === selectedFilter));
    }
    const matches = subsets[selectedFilter].filter(user => user.email.includes(term));
    count.textContent = `${matches.length} de ${users.length} contas`;
    rows.replaceChildren();
    for (const user of matches) {
      const row = document.createElement("li");
      row.className = "access-account";
      if (animate && rows.childElementCount < 8) {
        row.classList.add("access-account-enter");
        row.style.setProperty("--access-delay", `${rows.childElementCount * 35}ms`);
      }
      const account = document.createElement("div");
      account.className = "access-account-identity";
      const avatar = document.createElement("span");
      avatar.className = "access-account-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = user.email.split("@")[0].split(/[._-]+/).filter(Boolean).slice(0, 2).map(part => part[0]).join("").toUpperCase();
      const identity = document.createElement("div");
      const email = document.createElement("strong");
      const role = document.createElement("small");
      email.textContent = user.email;
      role.textContent = (user.admin ? "Administrador" : "Colaborador") + (user.self ? " · Sua conta" : "");
      identity.append(email, role);
      account.append(avatar, identity);
      const state = document.createElement("div");
      state.className = "access-account-status";
      const badge = document.createElement("span");
      badge.className = "user-access-state";
      badge.dataset.suspended = String(user.suspended);
      badge.textContent = user.suspended ? "Suspenso" : "Ativo";
      const presence = document.createElement("span");
      presence.className = "access-presence";
      presence.dataset.connected = String(Boolean(online(user)));
      presence.textContent = !online(user) ? "Desconectado" : user.active ? "Conectado · ativo" : "Conectado · inativo";
      state.append(badge, presence);
      const activity = document.createElement("dl");
      activity.className = "access-account-activity";
      for (const [label, seconds] of [["Última atividade", user.last_active], ["Inativo desde", user.inactive_since]]) {
        const entry = document.createElement("div");
        const term = document.createElement("dt");
        const value = document.createElement("dd");
        term.textContent = label;
        value.textContent = seconds == null ? "Sem registro" : formatTime(seconds);
        entry.append(term, value);
        activity.append(entry);
      }
      const actions = document.createElement("div");
      actions.className = "access-account-actions";
      row.append(account, state, activity, actions);
      rows.append(row);
      if (user.self) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.userEmail = user.email;
      button.className = "admin-action " + (user.suspended ? "admin-restore" : "admin-remove");
      button.textContent = user.suspended ? "Reativar" : "Suspender";
      button.setAttribute("aria-label", `${button.textContent} acesso de ${user.email}`);
      button.disabled = pending.has(user.email);
      button.onclick = async () => {
        const suspended = !user.suspended;
        if (suspended && !window.confirm(`Suspender o acesso de ${user.email}? As sessões ativas desta conta serão encerradas.`)) return;
        pending.add(user.email);
        button.disabled = true;
        message.textContent = "Atualizando acesso…";
        try {
          const response = await fetch(endpoint(), {
            method:"PUT", headers:{"Content-Type":"application/json"},
            body:JSON.stringify({email:user.email, suspended})
          });
          if (!response.ok) throw new Error(await responseError(response));
          const result = await response.json();
          user.suspended = result.suspended;
          if (result.suspended) user.connected = user.active = false;
          message.textContent = `Acesso ${result.suspended ? "suspenso" : "reativado"} para ${user.email}.`;
        } catch (error) { message.textContent = error.message; }
        finally {
          pending.delete(user.email);
          render();
          void loadUserAccess(true);
          if (document.querySelector("#userAccessView").classList.contains("active") && document.activeElement === document.body) {
            rows.querySelector(`[data-user-email="${CSS.escape(user.email)}"]`)?.focus({preventScroll:true});
          }
        }
      };
      actions.append(button);
    }
    if (!matches.length) {
      const empty = document.createElement("li");
      empty.className = "access-empty";
      empty.textContent = "Nenhuma conta encontrada.";
      rows.append(empty);
    }
  }

  search.addEventListener("input", render);
  for (const button of filters.querySelectorAll("button")) {
    button.onclick = () => {
      selectedFilter = button.dataset.accessFilter;
      render(true);
    };
  }
  loadUserAccess = async (silent = false) => {
    if (loading || pending.size) return;
    loading = true;
    if (!silent) message.textContent = "Carregando contas…";
    try {
      const response = await fetch(endpoint());
      if (!response.ok) throw new Error(await responseError(response));
      const data = (await response.json()).users;
      filters.hidden = false;
      if (!silent) message.textContent = "";
      if (JSON.stringify(users) === JSON.stringify(data) && rows.childElementCount) return;
      const focused = document.activeElement?.dataset.userEmail;
      users = data;
      render(!silent);
      if (focused) rows.querySelector(`[data-user-email="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
    } catch (error) { if (!silent) message.textContent = error.message; }
    finally { loading = false; }
  };
  setInterval(() => {
    if (!document.hidden && document.querySelector("#userAccessView").classList.contains("active")) {
      void loadUserAccess(true);
    }
  }, 30000);
}
