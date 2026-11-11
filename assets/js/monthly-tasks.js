(() => {
  const get = id => document.getElementById(id);
  const period = get("monthlyTasksPeriod");
  if (!period) return;
  const search = get("monthlyTasksSearch");
  const filter = get("monthlyTasksFilter");
  const status = get("monthlyTasksStatus");
  const metrics = get("monthlyTasksMetrics");
  const rows = get("monthlyTasksRows");
  const team = get("monthlyTasksTeam");
  const people = get("monthlyTasksPeople");
  const importer = get("monthlyTasksImport");
  const importMessage = get("monthlyTasksImportMessage");
  const dialog = get("monthlyTaskEditor");
  const form = get("monthlyTaskForm");
  const stepFields = get("monthlyTaskSteps");
  const saveMessage = get("monthlyTaskSaveMessage");
  const issue = get("monthlyTaskIssue");
  const action = get("monthlyTaskAction");
  const issueStatus = get("monthlyTaskIssueStatus");
  const endpoint = () => `${API()}/api/v1/monthly-tasks`;
  const labels = {pending:"Não iniciado", progress:"Em andamento", done:"Concluído", na:"Não se aplica"};
  const names = {none:"—", open:"Aberta", resolved:"Resolvida"};
  let state, ownerFilter, editor, request;
  let saving = false;

  function displayOwner(email) {
    return email ? email.split("@")[0].split(/[._-]/).map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(" ") : "Sem responsável";
  }

  function formatDate(value) {
    return value ? value.split("-").reverse().join("/") : "—";
  }

  function renderTeam() {
    team.hidden = importer.hidden = !state.admin;
    people.replaceChildren();
    if (!state.admin) return;
    const all = document.createElement("button");
    all.type = "button";
    all.textContent = "Toda a equipe";
    all.setAttribute("aria-pressed", String(ownerFilter === undefined));
    all.onclick = () => { ownerFilter = undefined; renderTeam(); renderRows(); };
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
      button.onclick = () => { ownerFilter = group.owner; renderTeam(); renderRows(); };
      people.append(button);
    }
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
    rows.replaceChildren();
    const term = search.value.trim().toLocaleLowerCase("pt-BR");
    const matching = state.companies.filter(row =>
      (ownerFilter === undefined || row.owner === ownerFilter) &&
      `${row.code} ${row.name}`.toLocaleLowerCase("pt-BR").includes(term)
    );
    const matches = (row, key) => key === "issue" ? row.issue_status === "open" : row.status === key;
    metrics.replaceChildren();
    for (const [key, label] of [["", "Empresas"], ["pending", "Não iniciadas"], ["progress", "Em andamento"], ["done", "Concluídas"], ["issue", "Com pendência"]]) {
      const button = document.createElement("button");
      const total = document.createElement("strong");
      button.type = "button";
      total.textContent = key ? matching.filter(row => matches(row, key)).length : matching.length;
      button.append(total, label);
      button.setAttribute("aria-pressed", String(filter.value === key));
      button.onclick = () => {
        filter.value = filter.value === key ? "" : key;
        renderRows();
        metrics.querySelectorAll("button")[[ "", "pending", "progress", "done", "issue" ].indexOf(filter.value)].focus();
      };
      metrics.append(button);
    }
    const visible = matching.filter(row => !filter.value || matches(row, filter.value));
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
      row.insertCell().textContent = formatDate(item.due);
      const cell = row.insertCell();
      const tag = document.createElement("span");
      tag.className = "monthly-task-status";
      tag.dataset.status = item.status;
      tag.textContent = labels[item.status];
      cell.append(tag);
      const progress = row.insertCell();
      progress.textContent = item.applicable ? `${item.done}/${item.applicable} · ${item.percent}%` : "—";
      if (item.applicable) progress.append(progressBar(item.percent));
      row.insertCell().textContent = names[item.issue_status];
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary-action";
      button.textContent = "Abrir";
      button.setAttribute("aria-label", `Abrir tarefa da empresa ${item.code}`);
      button.onclick = () => edit(item);
      row.insertCell().append(button);
    }
  }

  async function load() {
    request?.abort();
    const controller = new AbortController();
    request = controller;
    state = null;
    metrics.replaceChildren();
    rows.replaceChildren();
    team.hidden = importer.hidden = true;
    status.textContent = "Carregando tarefas…";
    try {
      const query = period.value ? `?period=${encodeURIComponent(period.value)}` : "";
      const response = await fetch(endpoint() + query, {signal:controller.signal});
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      if (controller.signal.aborted) return;
      state = result;
      period.value = state.period;
      if (!state.progress.some(item => item.owner === ownerFilter)) ownerFilter = undefined;
      renderTeam();
      renderRows();
    } catch (error) {
      if (!controller.signal.aborted) status.textContent = `Não foi possível carregar as tarefas. ${error.message}`;
    }
  }

  function edit(row) {
    editor = {row, period:state.period};
    get("monthlyTaskEditorTitle").textContent = `${row.code} · ${row.name}`;
    get("monthlyTaskEditorPeriod").textContent = `Competência ${state.period.split("-").reverse().join("/")}`;
    issue.value = row.issue;
    action.value = row.action;
    issueStatus.value = row.issue_status;
    saveMessage.textContent = "";
    stepFields.replaceChildren();
    state.steps.forEach((name, index) => {
      const label = document.createElement("label");
      const select = document.createElement("select");
      select.append(new Option("Pendente", "pending"), new Option("Concluída", "done"), new Option("Não se aplica", "na"));
      select.value = row.steps[index];
      label.append(name, select);
      stepFields.append(label);
    });
    dialog.showModal();
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (saving || !editor) return;
    const {row, period: month} = editor;
    const button = form.querySelector('[type="submit"]');
    saving = button.disabled = true;
    saveMessage.textContent = "Salvando…";
    try {
      const response = await fetch(`${endpoint()}/${month}/${row.code}`, {
        method:"PUT", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({steps:[...stepFields.querySelectorAll("select")].map(field => field.value),
          issue:issue.value, action:action.value, issue_status:issueStatus.value, revision:row.revision})
      });
      if (!response.ok) throw new Error(await responseError(response));
      dialog.close();
      await load();
    } catch (error) { saveMessage.textContent = error.message; }
    finally { saving = button.disabled = false; }
  });

  get("monthlyTaskClose").onclick = () => { if (!saving) dialog.close(); };
  dialog.addEventListener("cancel", event => { if (saving) event.preventDefault(); });
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
