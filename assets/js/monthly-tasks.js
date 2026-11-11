(() => {
  const get = id => document.getElementById(id);
  const period = get("monthlyTasksPeriod");
  if (!period) return;
  const search = get("monthlyTasksSearch");
  const sort = get("monthlyTasksSort");
  const filter = get("monthlyTasksFilter");
  const status = get("monthlyTasksStatus");
  const metrics = get("monthlyTasksMetrics");
  const rows = get("monthlyTasksRows");
  const queue = get("monthlyTasksQueue");
  const views = get("monthlyTasksViews");
  const clear = get("monthlyTasksClear");
  const activeFilters = get("monthlyTasksActiveFilters");
  const rowMessages = new Map();
  let currentView = "queue";
  const team = get("monthlyTasksTeam");
  const people = get("monthlyTasksPeople");
  const importPanel = get("monthlyTasksImportPanel");
  const importer = get("monthlyTasksImport");
  const importMessage = get("monthlyTasksImportMessage");
  const feedback = get("monthlyTaskFeedback");
  const endpoint = () => `${API()}/api/v1/monthly-tasks`;
  const labels = {pending:"Não iniciado", progress:"Em andamento", done:"Concluído", na:"Não se aplica"};
  const names = {none:"Registrar", open:"Aberta", resolved:"Resolvida"};
  let state, ownerFilter, request, stageFilter;
  const saving = new Set();
  const issueDrafts = new Map();
  let refreshAfterIssue = false;

  function displayOwner(email) {
    return email ? email.split("@")[0].split(/[._-]/).map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(" ") : "Sem responsável";
  }

  function setView(view) {
    currentView = state?.admin && view === "team" ? "team" : "queue";
    views.hidden = !state?.admin;
    team.hidden = currentView !== "team";
    queue.hidden = currentView === "team";
    for (const button of views.querySelectorAll("button")) {
      button.setAttribute("aria-pressed", String(button.dataset.taskView === currentView));
    }
  }

  for (const button of views.querySelectorAll("button")) {
    button.onclick = () => setView(button.dataset.taskView);
  }
  clear.onclick = () => {
    search.value = filter.value = "";
    ownerFilter = stageFilter = undefined;
    renderTeam();
    renderRows();
    search.focus();
  };

  function renderTeam() {
    importPanel.hidden = !state.admin;
    setView(currentView);
    people.replaceChildren();
    if (!state.admin) return;
    const all = document.createElement("button");
    all.type = "button";
    all.textContent = "Toda a equipe";
    all.setAttribute("aria-pressed", String(ownerFilter === undefined));
    all.onclick = () => { ownerFilter = undefined; setView("queue"); renderTeam(); renderRows(); search.focus(); };
    people.append(all);
    for (const group of state.progress) {
      const button = document.createElement("button");
      const name = document.createElement("strong");
      const detail = document.createElement("span");
      const percent = group.applicable ? Math.round(100 * group.done / group.applicable) : 0;
      name.textContent = `${displayOwner(group.owner)} · ${percent}% das etapas`;
      detail.textContent = `${group.completed}/${group.companies} empresas concluídas · ${group.issues} pendências`;
      button.type = "button";
      button.setAttribute("aria-pressed", String(ownerFilter === group.owner));
      button.append(name, detail, progressBar(percent));
      button.onclick = () => { ownerFilter = group.owner; setView("queue"); renderTeam(); renderRows(); search.focus(); };
      people.append(button);
    }
  }

  const closed = row => row.status === "done" && row.issue_status !== "open";
  const nextStep = row => row.steps.indexOf("pending");
  const myEmail = () => globalThis.RazyncSiteAccess?.identity();

  function renderStages() {
    const stages = get("monthlyTasksStages");
    stages.replaceChildren();
    if (!state.admin) return;
    const scoped = state.companies.filter(row => ownerFilter === undefined || row.owner === ownerFilter);
    state.steps.forEach((label, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${label} · ${scoped.filter(row => nextStep(row) === index).length}`;
      button.setAttribute("aria-pressed", String(stageFilter === index));
      button.onclick = () => {
        stageFilter = stageFilter === index ? undefined : index;
        setView("queue");
        renderRows();
        search.focus();
      };
      stages.append(button);
    });
  }

  function progressBar(percent) {
    const bar = document.createElement("progress");
    bar.max = 100;
    bar.value = percent;
    bar.setAttribute("aria-label", `${percent}% das etapas concluídas`);
    return bar;
  }

  function renderRows() {
    if (!state) return;
    const viewport = rows.closest(".monthly-tasks-table");
    const top = viewport.scrollTop;
    const left = viewport.scrollLeft;
    rows.replaceChildren();
    renderStages();
    const term = search.value.trim().toLocaleLowerCase("pt-BR");
    const matching = state.companies.filter(row =>
      (ownerFilter === undefined || row.owner === ownerFilter) &&
      (stageFilter === undefined || nextStep(row) === stageFilter) &&
      `${row.code} ${row.name}`.toLocaleLowerCase("pt-BR").includes(term)
    );
    const ready = row => row.reconciliation_ready && row.steps[1] === "pending";
    const matches = (row, key) => {
      if (key === "done") return closed(row);
      if (key === "ready") return ready(row);
      if (key === "mine") return row.owner === myEmail() && row.issue_status === "open";
      if (key === "issue") return row.issue_status === "open";
      return row.status === key;
    };
    const selected = [
      term ? `Busca: ${search.value.trim()}` : "",
      filter.value ? filter.selectedOptions[0].textContent : "",
      ownerFilter !== undefined ? displayOwner(ownerFilter) : "",
      stageFilter !== undefined ? state.steps[stageFilter] : ""
    ].filter(Boolean);
    clear.hidden = activeFilters.hidden = !selected.length;
    activeFilters.textContent = selected.join(" · ");
    const cards = [["", "Empresas"], ["issue", "Com pendência"], ["ready", "Conciliação para confirmar"], ["pending", "Não iniciadas"], ["progress", "Em andamento"], ["done", "Concluídas"]];
    metrics.replaceChildren();
    for (const [key, label] of cards) {
      const button = document.createElement("button");
      const total = document.createElement("strong");
      button.type = "button";
      total.textContent = key ? matching.filter(row => matches(row, key)).length : matching.length;
      button.dataset.metric = key;
      button.append(total, label);
      button.setAttribute("aria-pressed", String(filter.value === key));
      button.onclick = () => {
        filter.value = filter.value === key ? "" : key;
        renderRows();
        metrics.querySelector(`[data-metric="${filter.value}"]`)?.focus({preventScroll:true});
      };
      metrics.append(button);
    }
    const visible = matching.filter(row => !filter.value || matches(row, filter.value));
    visible.sort((a, b) => {
      if (sort.value === "queue") {
        const rank = row => row.issue_status === "open" ? 0 : ready(row) ? 1 : closed(row) || row.status === "na" ? 3 : 2;
        return rank(a) - rank(b) || b.percent - a.percent || a.code - b.code;
      }
      if (sort.value === "progress") return a.percent - b.percent || a.code - b.code;
      return a.code - b.code;
    });
    status.textContent = visible.length ? `${visible.length} empresas` : "Nenhuma empresa encontrada.";
    for (const item of visible) {
      const row = rows.insertRow();
      const company = row.insertCell();
      const title = document.createElement("strong");
      title.textContent = `${item.code} · ${item.name}`;
      company.append(title);
      if (state.admin) {
        const owner = document.createElement("small");
        owner.textContent = displayOwner(item.owner);
        company.append(owner);
      }
      const key = `${state.period}/${item.code}`;
      row.dataset.taskKey = key;
      const saveStatus = document.createElement("small");
      saveStatus.className = "monthly-row-save";
      saveStatus.setAttribute("role", "status");
      company.append(saveStatus);
      updateRowMessage(row, key);
      const next = nextStep(item);
      if (next >= 0) {
        const hint = document.createElement("small");
        hint.textContent = `Próxima etapa: ${state.steps[next]}`;
        company.append(hint);
      }
      item.steps.forEach((value, index) => {
        const field = document.createElement("select");
        field.append(new Option("Pendente", "pending"), new Option("OK", "done"), new Option("N/A", "na"));
        field.value = value;
        field.dataset.step = index;
        field.dataset.value = value;
        field.disabled = saving.has(key);
        field.setAttribute("aria-label", `${state.steps[index]} · empresa ${item.code}`);
        field.onchange = () => {
          const steps = [...item.steps];
          steps[index] = field.value;
          field.dataset.value = field.value;
          void saveTask(item, {steps}, field);
        };
        const stepCell = row.insertCell();
        stepCell.append(field);
        if (index === 1 && ready(item)) {
          const hint = document.createElement("small");
          hint.textContent = "Pronta para confirmar";
          hint.title = "A conferência do mês bateu para os bancos analisados. Confira a cobertura antes de marcar OK.";
          stepCell.append(hint);
        }
      });
      const progress = row.insertCell();
      progress.className = "monthly-task-progress";
      renderProgress(progress, item);
      const issueCell = row.insertCell();
      issueCell.dataset.issue = item.issue_status;
      issueCell.append(issueEditor(item, saving.has(key)), historyView(key, item));
    }
    viewport.scrollTop = top;
    viewport.scrollLeft = left;
  }

  function updateRowMessage(row, key) {
    const target = row.querySelector(".monthly-row-save");
    const message = rowMessages.get(key);
    target.textContent = message?.text ?? "";
    target.dataset.state = message?.state ?? "";
    target.title = message?.detail ?? "";
  }

  function renderProgress(cell, item) {
    cell.textContent = item.applicable ? `${item.percent}% · ${item.done}/${item.applicable}` : "—";
    if (item.applicable) cell.append(progressBar(item.percent));
    const tag = document.createElement("small");
    tag.textContent = item.status === "done" && !closed(item) ? "Pendência aberta" : labels[item.status];
    cell.append(tag);
  }

  async function load() {
    request?.abort();
    const controller = new AbortController();
    request = controller;
    state = null;
    refreshAfterIssue = false;
    metrics.replaceChildren();
    rows.replaceChildren();
    importPanel.hidden = true;
    const previousView = currentView;
    setView("queue");
    status.textContent = "Carregando tarefas…";
    try {
      const query = period.value ? `?period=${encodeURIComponent(period.value)}` : "";
      const response = await fetch(endpoint() + query, {signal:controller.signal});
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      if (controller.signal.aborted) return;
      state = result;
      setView(previousView);
      period.value = state.period;
      if (!state.progress.some(item => item.owner === ownerFilter)) ownerFilter = undefined;
      renderTeam();
      renderRows();
    } catch (error) {
      if (!controller.signal.aborted) status.textContent = `Não foi possível carregar as tarefas. ${error.message}`;
    }
  }

  function issueEditor(item, busy) {
    const details = document.createElement("div");
    details.className = "monthly-issue-editor";
    const key = `${state.period}/${item.code}`;
    const draft = issueDrafts.get(key) ?? item;
    const summary = document.createElement("button");
    summary.type = "button";
    summary.className = "secondary-action";
    summary.textContent = names[item.issue_status];
    summary.setAttribute("aria-label", `Pendência da empresa ${item.code}: ${summary.textContent}`);
    const dialog = document.createElement("dialog");
    dialog.className = "monthly-issue-dialog";
    dialog.id = `monthly-issue-${item.code}`;
    const header = document.createElement("header");
    const title = document.createElement("h2");
    title.id = `${dialog.id}-title`;
    title.textContent = "Pendência da empresa";
    const context = document.createElement("p");
    context.textContent = `${item.code} · ${item.name} · ${state.period.split("-").reverse().join("/")}`;
    header.append(title, context);
    dialog.setAttribute("aria-labelledby", title.id);
    summary.setAttribute("aria-controls", dialog.id);
    summary.setAttribute("aria-haspopup", "dialog");
    summary.disabled = busy;
    summary.onclick = () => dialog.showModal();
    dialog.addEventListener("close", () => {
      if (!refreshAfterIssue || !dialog.isConnected) return;
      refreshAfterIssue = false;
      renderRows();
      rows.querySelector(`[data-task-key="${key}"] .monthly-issue-editor > button`)?.focus();
    });
    dialog.addEventListener("cancel", event => { if (saving.has(key)) event.preventDefault(); });
    const form = document.createElement("form");
    const status = document.createElement("select");
    for (const [value, label] of [["none", "Sem pendência"], ["open", "Aberta"], ["resolved", "Resolvida"]]) {
      status.append(new Option(label, value));
    }
    status.value = draft.issue_status;
    const issue = document.createElement("textarea");
    issue.value = draft.issue;
    const action = document.createElement("textarea");
    action.value = draft.action;
    issue.maxLength = action.maxLength = 3000;
    for (const [title, field] of [["Situação", status], ["Pendência", issue], ["Última ação", action]]) {
      const label = document.createElement("label");
      label.append(title, field);
      form.append(label);
    }
    const button = document.createElement("button");
    button.className = "secondary-action";
    button.textContent = "Salvar pendência";
    button.disabled = busy;
    const footer = document.createElement("footer");
    const close = document.createElement("button");
    close.type = "button";
    close.className = "secondary-action";
    close.textContent = "Fechar";
    close.onclick = () => dialog.close();
    const message = document.createElement("p");
    message.className = "monthly-issue-feedback";
    message.setAttribute("role", "status");
    footer.append(close, button);
    form.append(message, footer);
    form.oninput = () => issueDrafts.set(key, {issue:issue.value, action:action.value, issue_status:status.value});
    form.onsubmit = event => {
      event.preventDefault();
      void saveTask(item, {issue:issue.value, action:action.value, issue_status:status.value}, button);
    };
    dialog.append(header, form);
    details.append(summary, dialog);
    return details;
  }

  function historyView(key, item) {
    const code = item.code;
    const wrapper = document.createElement("div");
    wrapper.className = "monthly-history";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-action";
    button.textContent = "Histórico";
    button.setAttribute("aria-label", `Histórico da empresa ${code}`);
    const dialog = document.createElement("dialog");
    dialog.className = "monthly-issue-dialog monthly-history-dialog";
    dialog.id = `monthly-history-${code}`;
    const title = document.createElement("h2");
    title.id = `${dialog.id}-title`;
    title.textContent = "Histórico da empresa";
    const context = document.createElement("p");
    context.textContent = `${code} · ${item.name} · ${state.period.split("-").reverse().join("/")}`;
    const header = document.createElement("header");
    header.append(title, context);
    dialog.setAttribute("aria-labelledby", title.id);
    button.setAttribute("aria-controls", dialog.id);
    button.setAttribute("aria-haspopup", "dialog");
    const list = document.createElement("ul");
    const message = document.createElement("p");
    message.setAttribute("role", "status");
    const close = document.createElement("button");
    close.type = "button";
    close.className = "secondary-action";
    close.textContent = "Fechar";
    close.onclick = () => dialog.close();
    const footer = document.createElement("footer");
    footer.append(close);
    dialog.append(header, message, list, footer);
    wrapper.append(button, dialog);
    const states = {pending:"Pendente", done:"OK", na:"N/A", open:"Aberta", resolved:"Resolvida", none:"Sem pendência"};
    let loading = false;
    button.onclick = async () => {
      dialog.showModal();
      if (loading || list.childElementCount) return;
      loading = true;
      message.textContent = "Carregando histórico…";
      try {
        const response = await fetch(`${endpoint()}/${key}/history`);
        if (!response.ok) throw new Error(await responseError(response));
        const events = await response.json();
        message.textContent = events.length ? "" : "Sem alterações registradas.";
        for (const event of events) {
          const entry = document.createElement("li");
          const when = new Date(event.at).toLocaleString("pt-BR");
          const changes = event.changes.map(change => change.before === undefined ? change.field
            : `${change.field}: ${states[change.before]} → ${states[change.after]}`);
          const actor = document.createElement("strong");
          actor.textContent = displayOwner(event.actor);
          const time = document.createElement("time");
          time.dateTime = event.at;
          time.textContent = when;
          const detail = document.createElement("p");
          detail.textContent = changes.join(" · ");
          entry.append(actor, time, detail);
          list.append(entry);
        }
      } catch (error) { message.textContent = error.message; }
      finally { loading = false; }
    };
    dialog.addEventListener("close", () => {
      if (!refreshAfterIssue || !dialog.isConnected) return;
      refreshAfterIssue = false;
      renderRows();
      rows.querySelector(`[data-task-key="${key}"] .monthly-history > button`)?.focus();
    });
    return wrapper;
  }

  async function saveTask(item, changes, trigger) {
    const snapshot = state;
    const key = `${snapshot.period}/${item.code}`;
    if (saving.has(key)) return;
    saving.add(key);
    const row = trigger.closest("tr");
    const progress = row.querySelector(".monthly-task-progress");
    if (changes.steps) {
      const done = changes.steps.filter(value => value === "done").length;
      const applicable = changes.steps.filter(value => value !== "na").length;
      const status = !applicable ? "na" : done === applicable ? "done" : done ? "progress" : "pending";
      renderProgress(progress, {...item, done, applicable, status, percent:applicable ? Math.round(done / applicable * 100) : 0});
    }
    row.querySelectorAll("select, button, textarea").forEach(field => { field.disabled = true; });
    row.setAttribute("aria-busy", "true");
    rowMessages.set(key, {state:"saving", text:"Salvando…"});
    updateRowMessage(row, key);
    const dialog = trigger.closest("dialog");
    const message = dialog?.querySelector(".monthly-issue-feedback") ?? feedback;
    if (dialog) message.textContent = "Salvando…";
    let saved = false;
    try {
      const {steps, issue, action, issue_status, revision} = item;
      const response = await fetch(`${endpoint()}/${key}`, {
        method:"PUT", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({steps, issue, action, issue_status, revision, ...changes})
      });
      if (!response.ok) throw new Error(await responseError(response));
      const updated = await response.json();
      const group = snapshot.progress.find(entry => entry.owner === item.owner);
      if (group) {
        group.done += updated.done - item.done;
        group.applicable += updated.applicable - item.applicable;
        group.completed += Number(closed(updated)) - Number(closed(item));
        group.issues += Number(updated.issue_status === "open") - Number(item.issue_status === "open");
      }
      Object.assign(item, updated);
      if ("issue" in changes) {
        issueDrafts.delete(key);
        dialog?.close();
      }
      saved = true;
      rowMessages.set(key, {state:"saved", text:"Salvo"});
      feedback.textContent = "";
    } catch (error) {
      rowMessages.set(key, {state:"error", text:"Falha ao salvar", detail:error.message});
      message.textContent = `Empresa ${item.code}: ${error.message}`;
      if (changes.steps) {
        renderProgress(progress, item);
        trigger.value = item.steps[Number(trigger.dataset.step)];
        trigger.dataset.value = trigger.value;
      }
    } finally {
      saving.delete(key);
      row.removeAttribute("aria-busy");
      updateRowMessage(row, key);
      if (state === snapshot) {
        if (saved || !row.isConnected) {
          renderTeam();
          if (rows.querySelector(".monthly-issue-dialog[open]")) {
            refreshAfterIssue = true;
            row.querySelectorAll("select, button, textarea").forEach(field => { field.disabled = false; });
            renderProgress(progress, item);
            return;
          }
          refreshAfterIssue = false;
          renderRows();
          const replacement = rows.querySelector(`[data-task-key="${key}"]`);
          replacement?.querySelector("step" in trigger.dataset ? `[data-step="${trigger.dataset.step}"]` : ".monthly-issue-editor > button")?.focus({preventScroll:true});
        } else {
          row.querySelectorAll("select, button, textarea").forEach(field => { field.disabled = false; });
          trigger.focus({preventScroll:true});
        }
      }
    }
  }

  sort.addEventListener("change", renderRows);
  importer.addEventListener("submit", async event => {
    event.preventDefault();
    const button = importer.querySelector("button");
    button.disabled = true;
    importMessage.hidden = false;
    importMessage.textContent = "Importando…";
    try {
      const response = await fetch(endpoint() + "/import", {method:"POST", body:new FormData(importer)});
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      importMessage.textContent = `${result.imported} registros importados. ${result.preserved} já salvos foram preservados.`;
      if (result.missing.length) importMessage.textContent += ` Códigos sem cadastro no site: ${result.missing.join(", ")}.`;
      importer.reset();
      await load();
    } catch (error) { importMessage.textContent = error.message; }
    finally { button.disabled = false; }
  });
  period.addEventListener("change", load);
  search.addEventListener("input", renderRows);
  filter.addEventListener("change", renderRows);
  globalThis.JaguarMonthlyTasks = {open:load};
})();
