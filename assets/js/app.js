const $ = (q) => document.querySelector(q);
const $$ = (q) => [...document.querySelectorAll(q)];

const grid = $("#companyGrid");
const search = $("#companySearch");
const count = $("#companyCount");
const workspace = $(".workspace");
const panel = $("#companyPanel");
const backButton = $("#backButton");
const apiStatus = $("#apiStatus");

const form = $("#processForm");
const bankSelect = $("#bankSelect");
const fileInput = $("#fileInput");
const standardFields = $("#standardFields");
const advancedFields = $("#advancedFields");
const processButton = $("#processButton");
const processMessage = $("#processMessage");

const baseStats = $("#baseStats");
const learnForm = $("#learnForm");
const classifyForm = $("#classifyForm");
const reconcileForm = $("#reconcileForm");
const fiscalForm = $("#fiscalForm");

let companies = [];
let selected = null;

const API = () => String(window.RAZYNC_CONFIG?.apiBase || "").replace(/\/$/, "");

function normalize(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function statusFor(company) {
  const status = company?.capabilities?.status;
  if (status === "api_ready") return "Ferramentas migradas";
  if (status === "catalog_only") return "Sem ferramenta específica";
  return "Em migração";
}

function bankLabel(bank, account) {
  const names = {
    itau: "Itaú", itau_508: "Itaú", itau_509: "Itaú",
    bradesco: "Bradesco", sicredi: "Sicredi", banco_brasil: "Banco do Brasil",
    caixa: "Caixa", inter: "Banco Inter", safra: "Safra", btg: "BTG",
    santander: "Santander", daycoval: "Daycoval", fibra: "Banco Fibra"
  };
  const name = names[bank] || bank;
  return account ? `${name} · conta ${account}` : name;
}

function render(items) {
  grid.innerHTML = "";
  count.textContent = `${items.length} empresa(s)`;
  if (!items.length) {
    grid.innerHTML = '<div class="empty-state">Nenhuma empresa encontrada.</div>';
    return;
  }
  for (const company of items) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "company-card company-card-button";
    card.innerHTML = `
      <div>
        <div class="card-topline">
          <span class="company-code">${company.codigo}</span>
          <span class="mini-status">${statusFor(company)}</span>
        </div>
        <h2>${company.nome}</h2>
        <p>${company.regime}</p>
      </div>
      <span class="arrow">→</span>
    `;
    card.addEventListener("click", () => openCompany(company));
    grid.appendChild(card);
  }
}

function fillBankSelect(select, banks) {
  select.innerHTML = "";
  for (const [bank, account] of Object.entries(banks || {})) {
    const option = document.createElement("option");
    option.value = bank;
    option.textContent = bankLabel(bank, account);
    select.appendChild(option);
  }
  if (!select.options.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Banco não configurado";
    select.appendChild(option);
  }
}

function activateTool(name) {
  $$(".tool-tab").forEach(btn => btn.classList.toggle("active", btn.dataset.tool === name));
  $$(".tool-pane").forEach(pane => pane.classList.toggle("active", pane.dataset.pane === name));
}

$$(".tool-tab").forEach(btn => btn.addEventListener("click", () => activateTool(btn.dataset.tool)));

function renderWorkflow(company) {
  const cap = company.capabilities || {};
  const workflow = cap.workflow || "standard";
  const banks = cap.banks || {};
  fillBankSelect(bankSelect, banks);
  fillBankSelect($("#reconcileBank"), banks);

  advancedFields.innerHTML = "";
  advancedFields.hidden = true;
  standardFields.hidden = false;

  if (workflow === "advanced") {
    standardFields.hidden = true;
    advancedFields.hidden = false;
    for (const role of cap.roles || []) {
      const wrap = document.createElement("div");
      wrap.className = "field-group";
      const id = `role_${role.name}`;
      wrap.innerHTML = `
        <label for="${id}">${role.label}${role.optional ? " <span class='optional'>(opcional)</span>" : ""}</label>
        <input id="${id}" data-role="${role.name}" type="file"
          ${role.multiple ? "multiple" : ""}
          accept="${role.accept || ".pdf,.xls,.xlsx,.zip"}"
          ${role.optional ? "" : "required"}>
      `;
      advancedFields.appendChild(wrap);
    }
    for (const option of cap.options || []) {
      const wrap = document.createElement("div");
      wrap.className = "field-group";
      const year = new Date().getFullYear();
      wrap.innerHTML = `
        <label for="opt_${option.name}">${option.label}</label>
        <input id="opt_${option.name}" data-option="${option.name}" type="${option.type || "text"}"
          ${option.type === "number" ? `value="${year}" min="2000" max="2100"` : ""}>
      `;
      advancedFields.appendChild(wrap);
    }
    $("#toolDescription").textContent = "Este fluxo usa arquivos complementares. Envie cada documento no campo correspondente.";
  } else if (workflow === "standard_multi_bank") {
    standardFields.hidden = true;
    advancedFields.hidden = false;
    for (const [bank, account] of Object.entries(banks)) {
      const wrap = document.createElement("div");
      wrap.className = "field-group";
      wrap.innerHTML = `
        <label for="bankfiles_${bank}">${bankLabel(bank, account)} <span class="optional">(opcional)</span></label>
        <input id="bankfiles_${bank}" data-bank="${bank}" type="file" multiple
          accept=".pdf,.xls,.xlsx,.csv,.ofx">
      `;
      advancedFields.appendChild(wrap);
    }
    $("#toolDescription").textContent = "Envie os arquivos por banco. O Razync gera um único Modelo Domínio com uma aba para cada banco informado.";
  } else {
    $("#toolDescription").textContent = "Selecione o banco, envie um ou vários arquivos e gere o Modelo Domínio.";
  }
}

async function refreshBaseStats() {
  if (!selected || selected.capabilities?.status !== "api_ready") {
    baseStats.innerHTML = "";
    return;
  }
  try {
    const r = await fetch(`${API()}/api/v1/base-inteligente/${selected.codigo}/status`);
    const data = await r.json();
    baseStats.innerHTML = `
      <span><strong>${data.patterns || 0}</strong> padrões</span>
      <span><strong>${data.banks || 0}</strong> bancos</span>
      <span><strong>${data.periods || 0}</strong> períodos</span>
    `;
  } catch {
    baseStats.innerHTML = "<span>Base temporariamente indisponível</span>";
  }
}

function openCompany(company) {
  selected = company;
  document.querySelectorAll(".global-view").forEach(view => view.classList.remove("active"));
  document.querySelectorAll(".main-nav-btn").forEach(btn => btn.classList.remove("active"));
  $("#panelCode").textContent = `Empresa ${company.codigo}`;
  $("#panelName").textContent = company.nome;
  $("#panelRegime").textContent = company.regime;
  $("#panelStatus").textContent = statusFor(company);

  const available = company.capabilities?.status === "api_ready";
  $("#toolUnavailable").hidden = available;
  $$(".tool-tabs, .tool-pane").forEach(el => {
    if (el.classList.contains("tool-tabs")) el.hidden = !available;
    else if (!available) el.classList.remove("active");
  });

  if (available) {
    renderWorkflow(company);
    activateTool("organizar");
    refreshBaseStats();
  }

  processMessage.textContent = "";
  $("#learnMessage").textContent = "";
  $("#classifyMessage").textContent = "";
  $("#reconcileMessage").textContent = "";
  $("#fiscalMessage").textContent = "";
  workspace.hidden = true;
  $(".hero").hidden = true;
  panel.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function closeCompany() {
  panel.hidden = true;
  workspace.hidden = false;
  $(".hero").hidden = false;
  selected = null;
  showGlobalView("companies");
}

function downloadBlob(response, fallback) {
  return response.blob().then(blob => {
    const disp = response.headers.get("content-disposition") || "";
    const match = disp.match(/filename="?([^";]+)"?/i);
    const filename = match?.[1] || fallback;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 3000);
  });
}

async function responseError(response) {
  const body = await response.json().catch(() => ({}));
  return body.detail || `Erro ${response.status}`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selected) return;
  const cap = selected.capabilities || {};
  const workflow = cap.workflow || "standard";
  const data = new FormData();
  let endpoint = `${API()}/api/v1/modelo-dominio/${selected.codigo}`;

  try {
    if (workflow === "advanced") {
      const roles = [];
      for (const input of $$("[data-role]")) {
        for (const file of [...input.files]) {
          data.append("files", file);
          roles.push(input.dataset.role);
        }
      }
      if (!roles.length) throw new Error("Envie os arquivos necessários para esta empresa.");
      const options = {};
      for (const input of $$("[data-option]")) options[input.dataset.option] = input.value;
      data.append("roles_json", JSON.stringify(roles));
      data.append("options_json", JSON.stringify(options));
      endpoint = `${API()}/api/v1/workflow/${selected.codigo}`;
    } else if (workflow === "standard_multi_bank") {
      const banks = [];
      for (const input of $$("[data-bank]")) {
        for (const file of [...input.files]) {
          data.append("files", file);
          banks.push(input.dataset.bank);
        }
      }
      if (!banks.length) throw new Error("Envie pelo menos um arquivo bancário.");
      data.append("banks_json", JSON.stringify(banks));
      endpoint = `${API()}/api/v1/modelo-dominio/${selected.codigo}/multi`;
    } else {
      const files = [...fileInput.files];
      if (!files.length) throw new Error("Selecione pelo menos um arquivo.");
      data.append("bank", bankSelect.value);
      files.forEach(file => data.append("files", file));
    }

    processMessage.textContent = "Processando…";
    processButton.disabled = true;
    const response = await fetch(endpoint, { method: "POST", body: data });
    if (!response.ok) throw new Error(await responseError(response));
    await downloadBlob(response, `RAZYNC_${selected.codigo}_MODELO_DOMINIO.xlsx`);
    processMessage.textContent = "Modelo Domínio gerado com sucesso.";
  } catch (error) {
    processMessage.textContent = error.message;
  } finally {
    processButton.disabled = false;
  }
});

learnForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = [...$("#learnFiles").files];
  if (!files.length) return $("#learnMessage").textContent = "Selecione pelo menos um arquivo revisado.";
  const data = new FormData();
  files.forEach(file => data.append("files", file));
  $("#learnMessage").textContent = "Aprendendo padrões…";
  try {
    const response = await fetch(`${API()}/api/v1/base-inteligente/${selected.codigo}/aprender`, {method:"POST", body:data});
    if (!response.ok) throw new Error(await responseError(response));
    const result = await response.json();
    $("#learnMessage").textContent = `${result.learned} padrão(ões) processado(s).`;
    refreshBaseStats();
  } catch (error) {
    $("#learnMessage").textContent = error.message;
  }
});

classifyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#classifyFile").files[0];
  if (!file) return $("#classifyMessage").textContent = "Selecione o Modelo Domínio.";
  const data = new FormData();
  data.append("file", file);
  $("#classifyMessage").textContent = "Classificando…";
  try {
    const response = await fetch(`${API()}/api/v1/base-inteligente/${selected.codigo}/classificar`, {method:"POST", body:data});
    if (!response.ok) throw new Error(await responseError(response));
    const raw = response.headers.get("x-razync-summary");
    const summary = raw ? JSON.parse(raw) : {};
    await downloadBlob(response, `RAZYNC_${selected.codigo}_CLASSIFICADO.xlsx`);
    $("#classifyMessage").textContent = `Classificação concluída: ${summary.automaticos || 0} automáticos.`;
  } catch (error) {
    $("#classifyMessage").textContent = error.message;
  }
});

reconcileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const model = $("#modelFile").files[0];
  const statements = [...$("#statementFiles").files];
  if (!model || !statements.length) return $("#reconcileMessage").textContent = "Envie o Modelo Domínio e pelo menos um extrato.";
  const data = new FormData();
  data.append("bank", $("#reconcileBank").value);
  data.append("model_file", model);
  statements.forEach(file => data.append("statement_files", file));
  $("#reconcileMessage").textContent = "Conferindo…";
  try {
    const response = await fetch(`${API()}/api/v1/conferencia-extrato/${selected.codigo}`, {method:"POST", body:data});
    if (!response.ok) throw new Error(await responseError(response));
    const raw = response.headers.get("x-razync-summary");
    const summary = raw ? JSON.parse(raw) : {};
    await downloadBlob(response, `RAZYNC_${selected.codigo}_CONFERENCIA_EXTRATO.xlsx`);
    $("#reconcileMessage").textContent = summary.ok
      ? "Conferência concluída: planilha e extrato estão batendo."
      : `Conferência concluída com ${summary.faltando_planilha || 0} faltando e ${summary.a_mais_planilha || 0} a mais.`;
  } catch (error) {
    $("#reconcileMessage").textContent = error.message;
  }
});

fiscalForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const acumuladores = $("#acumuladoresFile").files[0];
  const razao = $("#razaoFile").files[0];
  if (!acumuladores || !razao) return $("#fiscalMessage").textContent = "Envie Acumuladores e Razão.";
  const data = new FormData();
  data.append("acumuladores", acumuladores);
  data.append("razao", razao);
  data.append("filial", $("#filialInput").value);
  $("#fiscalMessage").textContent = "Processando conferência fiscal…";
  try {
    const response = await fetch(`${API()}/api/v1/conferencia-fiscal/${selected.codigo}`, {method:"POST", body:data});
    if (!response.ok) throw new Error(await responseError(response));
    await downloadBlob(response, `RAZYNC_${selected.codigo}_CONFERENCIA_FISCAL.xlsx`);
    $("#fiscalMessage").textContent = "Relatório fiscal gerado com sucesso.";
  } catch (error) {
    $("#fiscalMessage").textContent = error.message;
  }
});

search.addEventListener("input", () => {
  const query = normalize(search.value.trim());
  render(companies.filter(company =>
    normalize(company.codigo).includes(query) ||
    normalize(company.nome).includes(query) ||
    normalize(company.regime).includes(query)
  ));
});
backButton.addEventListener("click", closeCompany);

async function loadCompanies() {
  try {
    const response = await fetch(`${API()}/api/v1/companies`);
    if (!response.ok) throw new Error();
    companies = await response.json();
  } catch {
    const response = await fetch("./assets/data/companies.json");
    companies = await response.json();
  }
  render(companies);
}

async function checkApi() {
  if (!API()) return apiStatus.textContent = "API não configurada";
  try {
    const response = await fetch(`${API()}/health`);
    if (!response.ok) throw new Error();
    apiStatus.textContent = "Sistema online";
    apiStatus.classList.add("online");
  } catch {
    apiStatus.textContent = "API temporariamente indisponível";
  }
}

loadCompanies();
checkApi();


function showGlobalView(name) {
  panel.hidden = true;
  selected = null;
  if (name === "companies") {
    workspace.hidden = false;
    $(".hero").hidden = false;
  }
  document.querySelectorAll(".global-view").forEach(view => {
    view.classList.toggle("active", view.id === `${name}View`);
  });
  document.querySelectorAll(".main-nav-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
  if (name === "tasks") loadTasks();
  window.scrollTo({top:0, behavior:"smooth"});
}

document.querySelectorAll(".main-nav-btn").forEach(btn => {
  btn.addEventListener("click", () => showGlobalView(btn.dataset.view));
});

$("#converterForm")?.addEventListener("submit", async event => {
  event.preventDefault();
  const files = [...$("#converterFiles").files];
  const msg = $("#converterMessage");
  if (!files.length) return msg.textContent = "Selecione pelo menos um extrato.";
  const data = new FormData();
  files.forEach(file => data.append("files", file));
  msg.textContent = "Convertendo extratos…";
  try {
    const response = await fetch(`${API()}/api/v1/conversor-extratos`, {method:"POST", body:data});
    if (!response.ok) throw new Error(await responseError(response));
    await downloadBlob(response, "RAZYNC_CONVERSOR_EXTRATOS_MODELO_DOMINIO.xlsx");
    msg.textContent = "Modelo Domínio gerado com sucesso.";
  } catch (error) {
    msg.textContent = error.message;
  }
});

$("#ledgerForm")?.addEventListener("submit", async event => {
  event.preventDefault();
  const statement = $("#ledgerStatement").files[0];
  const ledger = $("#ledgerFile").files[0];
  const msg = $("#ledgerMessage");
  if (!statement || !ledger) return msg.textContent = "Envie o extrato e o Razão.";
  const data = new FormData();
  data.append("extrato", statement);
  data.append("razao", ledger);
  msg.textContent = "Conciliando…";
  try {
    const response = await fetch(`${API()}/api/v1/conciliacao-razao`, {method:"POST", body:data});
    if (!response.ok) throw new Error(await responseError(response));
    const raw = response.headers.get("x-razync-summary");
    const summary = raw ? JSON.parse(raw) : {};
    await downloadBlob(response, "RAZYNC_CONCILIACAO_RAZAO.xlsx");
    msg.textContent = summary.dias_revisar
      ? `Concluído: ${summary.dias_revisar} dia(s) precisam de revisão.`
      : "Concluído: os totais diários estão conferindo.";
  } catch (error) {
    msg.textContent = error.message;
  }
});

function brl(value) {
  return new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(Number(value||0));
}

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
    ].map(([a,b])=>`<div class="task-metric"><span>${a}</span><strong>${b??0}</strong></div>`).join("");
    $("#taskCompetencia").textContent = `Competência ${String(data.competencia||"").slice(5,7)}/${String(data.competencia||"").slice(0,4)}`;

    companiesBox.innerHTML = (data.empresas||[]).map(item => `
      <div class="task-row ${item.classe||""}">
        <div>
          <strong>${item.codigo} · ${item.nome}</strong>
          <small>${item.regime} · vence ${new Date(item.vencimento+"T12:00:00").toLocaleDateString("pt-BR")} · ${item.status}</small>
        </div>
        <button type="button" data-company-task="${item.codigo}" data-done="${item.concluida ? "1":"0"}" data-competencia="${data.competencia}">
          ${item.concluida ? "Reabrir" : "Concluir"}
        </button>
      </div>
    `).join("");

    manualBox.innerHTML = (data.manuais||[]).length ? (data.manuais||[]).map(item => `
      <div class="task-row">
        <div>
          <strong>${item.titulo}</strong>
          <small>${item.prioridade||"Normal"} · ${item.classificacao?.faixa||item.status}</small>
        </div>
        <div class="task-actions">
          <button type="button" data-manual-done="${item.id}">${item.status==="Concluída" ? "Reabrir":"Concluir"}</button>
          <button type="button" data-manual-delete="${item.id}" class="danger-lite">Excluir</button>
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
    metrics.innerHTML = `<div class="empty-state">${error.message}</div>`;
  }
}

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

$("#taxForm")?.addEventListener("submit", async event => {
  event.preventDefault();
  const balance = $("#taxBalance").files[0];
  const revenue = $("#taxRevenue").files[0];
  const msg = $("#taxMessage");
  if (!balance || !revenue) return msg.textContent = "Envie o balancete e o relatório da Receita, ou use o Conector Windows.";
  try {
    await runTaxComparison(balance, revenue, msg);
  } catch (error) {
    msg.textContent = error.message;
  }
});

async function runTaxComparison(balance, revenue, msgElement) {
  const data = new FormData();
  data.append("receita", revenue);
  data.append("balancete", balance);
  data.append("competencia", $("#taxCompetence").value);
  msgElement.textContent = "Conferindo impostos…";
  const response = await fetch(`${API()}/api/v1/conferencia-impostos/${selected.codigo}`, {method:"POST", body:data});
  if (!response.ok) throw new Error(await responseError(response));
  const raw = response.headers.get("x-razync-summary");
  const summary = raw ? JSON.parse(raw) : {};
  await downloadBlob(response, `RAZYNC_${selected.codigo}_CONFERENCIA_IMPOSTOS.xlsx`);
  msgElement.textContent = summary.revisar
    ? `Relatório gerado: ${summary.revisar} imposto(s) precisam de revisão.`
    : "Relatório gerado: impostos conferindo.";
}

const CONNECTOR = "http://127.0.0.1:17891";
const connectorTokenKey = "razync_connector_token_v1";

async function connectorHealth() {
  try {
    const r = await fetch(`${CONNECTOR}/v1/health`);
    if (!r.ok) throw new Error();
    const data = await r.json();
    $("#connectorStatus").textContent = `Conectado · v${data.version||""}`;
    return true;
  } catch {
    $("#connectorStatus").textContent = "Conector não encontrado";
    return false;
  }
}

async function connectorRequest(path, options={}) {
  const token = localStorage.getItem(connectorTokenKey) || "";
  const headers = {...(options.headers||{})};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && typeof options.body === "string") headers["Content-Type"]="application/json";
  const r = await fetch(`${CONNECTOR}${path}`, {...options, headers});
  const body = await r.json().catch(()=>({}));
  if (!r.ok) throw new Error(body.error || `Erro do conector (${r.status})`);
  return body;
}

async function loadCertificates() {
  const data = await connectorRequest("/v1/certificates");
  const select = $("#certificateSelect");
  select.innerHTML = "";
  for (const cert of data.certificates || []) {
    const o=document.createElement("option");
    o.value=cert.thumbprint;
    o.textContent=`${cert.subject || "Certificado"}${cert.valid_to ? " · "+String(cert.valid_to).slice(0,10):""}`;
    select.appendChild(o);
  }
  if (!select.options.length) throw new Error("Nenhum certificado A1 disponível no Windows.");
}

$("#pairConnector")?.addEventListener("click", async () => {
  const msg=$("#taxMessage");
  try {
    if (!await connectorHealth()) throw new Error("Abra ou instale o Conector Razync no Windows.");
    const code=$("#pairingCode").value.trim();
    if (!/^\d{6}$/.test(code)) throw new Error("Informe o código de pareamento de 6 dígitos.");
    const data=await connectorRequest("/v1/pair",{method:"POST",body:JSON.stringify({code})});
    localStorage.setItem(connectorTokenKey,data.token);
    await loadCertificates();
    $("#connectorStatus").textContent="Pareado";
    msg.textContent="Conector pareado com sucesso.";
  } catch(error) {
    msg.textContent=error.message;
  }
});

async function identifyCompanyCnpj(balance) {
  const data=new FormData(); data.append("balancete",balance);
  const r=await fetch(`${API()}/api/v1/impostos/${selected.codigo}/identificar-cnpj`,{method:"POST",body:data});
  if(!r.ok) throw new Error(await responseError(r));
  const body=await r.json();
  if(!body.cnpjs?.length) throw new Error("Não encontrei um CNPJ válido no balancete.");
  return body.cnpjs[0];
}

$("#openDctf")?.addEventListener("click", async () => {
  const msg=$("#taxMessage");
  try {
    const balance=$("#taxBalance").files[0];
    const comp=$("#taxCompetence").value;
    if(!balance || !comp) throw new Error("Envie o balancete e informe a competência.");
    if(!localStorage.getItem(connectorTokenKey)) throw new Error("Pareie o Conector Windows primeiro.");
    if(!$("#certificateSelect").options.length) await loadCertificates();
    const cnpj=await identifyCompanyCnpj(balance);
    const [year,month]=comp.split("-");
    await connectorRequest("/v1/dctf/open",{
      method:"POST",
      body:JSON.stringify({cnpj,competencia:`${month}-${year}`,thumbprint:$("#certificateSelect").value})
    });
    msg.textContent="e-CAC aberto. Após o relatório ser baixado, clique em “Buscar relatório baixado e conferir”.";
  } catch(error) {
    msg.textContent=error.message;
  }
});

$("#fetchDctf")?.addEventListener("click", async () => {
  const msg=$("#taxMessage");
  try {
    const balance=$("#taxBalance").files[0];
    if(!balance) throw new Error("Envie o balancete primeiro.");
    const report=await connectorRequest("/v1/dctf/latest");
    const binary=atob(report.content);
    const bytes=new Uint8Array(binary.length);
    for(let i=0;i<binary.length;i++) bytes[i]=binary.charCodeAt(i);
    const revenue=new File([bytes],report.name||"DCTFWeb.pdf");
    await runTaxComparison(balance,revenue,msg);
  } catch(error) {
    msg.textContent=error.message;
  }
});

const originalLoadCompanies = loadCompanies;
loadCompanies = async function() {
  await originalLoadCompanies();
  const select=$("#taskCompany");
  if(select) {
    select.innerHTML='<option value="">Sem empresa específica</option>'+companies.map(c=>`<option value="${c.codigo}">${c.codigo} · ${c.nome}</option>`).join("");
  }
};

connectorHealth();
loadCompanies();
