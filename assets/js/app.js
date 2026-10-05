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
