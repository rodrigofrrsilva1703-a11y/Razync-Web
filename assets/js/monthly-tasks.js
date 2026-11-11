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

  function displayOwner(email) {
    return email ? email.split("@")[0].split(/[._-]/).map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(" ") : "Sem responsável";
  }

  function renderTeam() {
    team.hidden = importPanel.hidden = !state.admin;
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
        renderRows();
        stages.children[index]?.focus();
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
      issueCell.append(issueEditor(item, saving.has(key)), historyView(key, item.code));
    }
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
    metrics.replaceChildren();
    rows.replaceChildren();
    team.hidden = importPanel.hidden = true;
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
    const form = document.createElement("form");
    form.id = `monthly-issue-${item.code}`;
    form.hidden = !issueDrafts.has(key);
    summary.setAttribute("aria-controls", form.id);
    summary.setAttribute("aria-expanded", String(!form.hidden));
    summary.onclick = () => {
      form.hidden = !form.hidden;
      summary.setAttribute("aria-expanded", String(!form.hidden));
    };
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
    form.append(button);
    form.oninput = () => issueDrafts.set(key, {issue:issue.value, action:action.value, issue_status:status.value});
    form.onsubmit = event => {
      event.preventDefault();
      void saveTask(item, {issue:issue.value, action:action.value, issue_status:status.value}, button);
    };
    details.append(summary, form);
    return details;
  }

  function historyView(key, code) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Histórico";
    summary.setAttribute("aria-label", `Histórico da empresa ${code}`);
    const list = document.createElement("ul");
    details.append(summary, list);
    const states = {pending:"Pendente", done:"OK", na:"N/A", open:"Aberta", resolved:"Resolvida", none:"Sem pendência"};
    details.ontoggle = async () => {
      if (!details.open || list.childElementCount) return;
      list.textContent = "Carregando…";
      try {
        const response = await fetch(`${endpoint()}/${key}/history`);
        if (!response.ok) throw new Error(await responseError(response));
        const events = await response.json();
        list.textContent = events.length ? "" : "Sem alterações registradas.";
        for (const event of events) {
          const entry = document.createElement("li");
          const when = new Date(event.at).toLocaleString("pt-BR");
          const changes = event.changes.map(change => change.before === undefined ? change.field
            : `${change.field}: ${states[change.before]} → ${states[change.after]}`);
          entry.textContent = `${displayOwner(event.actor)} · ${when} · ${changes.join("; ")}`;
          list.append(entry);
        }
      } catch (error) { list.textContent = error.message; }
    };
    return details;
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
    feedback.textContent = `Salvando empresa ${item.code}…`;
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
      if ("issue" in changes) issueDrafts.delete(key);
      saved = true;
      feedback.textContent = `Empresa ${item.code} atualizada.`;
    } catch (error) {
      feedback.textContent = `Empresa ${item.code}: ${error.message}`;
      if (changes.steps) {
        renderProgress(progress, item);
        trigger.value = item.steps[Number(trigger.dataset.step)];
        trigger.dataset.value = trigger.value;
      }
    } finally {
      saving.delete(key);
      row.removeAttribute("aria-busy");
      if (state === snapshot) {
        if (saved || !row.isConnected) {
          renderTeam();
          renderRows();
          const replacement = rows.querySelector(`[data-task-key="${key}"]`);
          replacement?.querySelector("step" in trigger.dataset ? `[data-step="${trigger.dataset.step}"]` : ".monthly-issue-editor > button")?.focus();
        } else {
          row.querySelectorAll("select, button, textarea").forEach(field => { field.disabled = false; });
          trigger.focus();
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
