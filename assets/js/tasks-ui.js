// Painel de tarefas e cadastro manual. Não altera regras ou prazos.
async function loadTasks() {
  const metrics = $("#taskMetrics");
  const companiesBox = $("#companyTasks");
  const manualBox = $("#manualTasks");
  try {
    const response = await fetch(`${API()}/api/v1/tasks`);
    if (!response.ok) throw new Error(await responseError(response));
    const data = await response.json();
    const r = data.resumo || {};
    metrics.innerHTML = [
      ["Pendentes",r.pendentes],["Atrasadas",r.atrasadas],
      ["Urgentes / hoje",r.urgentes_hoje],["Concluídas",r.concluidas],
      ["Progresso",`${r.progresso||0}%`]
    ].map(([a,b])=>`<div class="task-metric"><span>${a}</span><strong>${RazyncDOM.escapeHTML(b??0)}</strong></div>`).join("");
    $("#taskCompetencia").textContent = `Competência ${String(data.competencia||"").slice(5,7)}/${String(data.competencia||"").slice(0,4)}`;

    companiesBox.innerHTML = (data.empresas||[]).map(item => `
      <div class="task-row ${RazyncDOM.escapeHTML(item.classe||"")}">
        <div>
          <strong>${RazyncDOM.escapeHTML(item.codigo)} · ${RazyncDOM.escapeHTML(item.nome)}</strong>
          <small>${RazyncDOM.escapeHTML(item.regime)} · vence ${new Date(item.vencimento+"T12:00:00").toLocaleDateString("pt-BR")} · ${RazyncDOM.escapeHTML(item.status)}</small>
        </div>
        <button type="button" data-company-task="${RazyncDOM.escapeHTML(item.codigo)}" data-done="${item.concluida ? "1":"0"}" data-competencia="${RazyncDOM.escapeHTML(data.competencia)}">
          ${item.concluida ? "Reabrir" : "Concluir"}
        </button>
      </div>
    `).join("");

    manualBox.innerHTML = (data.manuais||[]).length ? (data.manuais||[]).map(item => `
      <div class="task-row">
        <div>
          <strong>${RazyncDOM.escapeHTML(item.titulo)}</strong>
          <small>${RazyncDOM.escapeHTML(item.prioridade||"Normal")} · ${RazyncDOM.escapeHTML(item.classificacao?.faixa||item.status)}</small>
        </div>
        <div class="task-actions">
          <button type="button" data-manual-done="${RazyncDOM.escapeHTML(item.id)}">${item.status==="Concluída" ? "Reabrir":"Concluir"}</button>
          <button type="button" data-manual-delete="${RazyncDOM.escapeHTML(item.id)}" class="danger-lite">Excluir</button>
        </div>
      </div>
    `).join("") : '<div class="empty-state compact">Nenhuma tarefa manual.</div>';

    companiesBox.querySelectorAll("[data-company-task]").forEach(btn => btn.addEventListener("click", async () => {
      await fetch(`${API()}/api/v1/tasks/company/${btn.dataset.companyTask}`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({competencia:btn.dataset.competencia, concluida:btn.dataset.done!=="1"})
      });
      loadTasks();
    }));
    manualBox.querySelectorAll("[data-manual-done]").forEach(btn => btn.addEventListener("click", async () => {
      const row = (data.manuais||[]).find(x=>x.id===btn.dataset.manualDone);
      await fetch(`${API()}/api/v1/tasks/manual/${btn.dataset.manualDone}`, {
        method:"PATCH", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({status:row?.status==="Concluída" ? "Pendente":"Concluída"})
      });
      loadTasks();
    }));
    manualBox.querySelectorAll("[data-manual-delete]").forEach(btn => btn.addEventListener("click", async () => {
      await fetch(`${API()}/api/v1/tasks/manual/${btn.dataset.manualDelete}`, {method:"DELETE"});
      loadTasks();
    }));
  } catch (error) {
    const message = document.createElement("div");
    message.className = "empty-state";
    message.textContent = error.message;
    metrics.replaceChildren(message);
  }
}

function initializeTaskUI() {
  $("#manualTaskForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const payload = {
      titulo: $("#taskTitle").value,
      codigo_empresa: $("#taskCompany").value,
      categoria: $("#taskCategory").value,
      prioridade: $("#taskPriority").value,
      prazo: $("#taskDue").value,
      descricao: $("#taskDescription").value
    };
    const msg = $("#taskMessage");
    msg.textContent = "Salvando…";
    try {
      const response = await fetch(`${API()}/api/v1/tasks/manual`, {
        method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(await responseError(response));
      event.target.reset();
      $("#taskCategory").value = "Geral";
      $("#taskPriority").value = "Normal";
      msg.textContent = "Tarefa criada.";
      loadTasks();
    } catch (error) {
      msg.textContent = error.message;
    }
  });

}

function populateTaskCompanies(items) {
  const select = document.querySelector("#taskCompany");
  if (!select) return;
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "Sem empresa específica";
  select.replaceChildren(empty);
  for (const company of items) {
    const option = document.createElement("option");
    option.value = company.codigo;
    option.textContent = `${company.codigo} · ${company.nome}`;
    select.appendChild(option);
  }
}
