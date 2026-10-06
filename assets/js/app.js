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
let companyFilter = 'all';

const API = () => String(window.RAZYNC_CONFIG?.apiBase || "").replace(/\/$/, "");

function setProcessStage(stage, title="", text="") {
  const flow = document.querySelector(".tool-flow");
  if (flow) {
    const order = ["upload","processing","review"];
    const current = order.indexOf(stage);
    flow.querySelectorAll("[data-step]").forEach(item => {
      const index = order.indexOf(item.dataset.step);
      item.classList.toggle("active", index === current);
      item.classList.toggle("completed", current >= 0 && index < current);
    });
  }

  const box = $("#processVisualStatus");
  if (!box) return;
  if (!title && !text) {
    box.hidden = true;
    box.classList.remove("is-processing","is-success","is-error");
    return;
  }
  box.hidden = false;
  box.classList.toggle("is-processing", stage === "processing");
  box.classList.toggle("is-success", stage === "review");
  box.classList.toggle("is-error", stage === "error");
  $("#processStatusTitle").textContent = title;
  $("#processStatusText").textContent = text;
}

function renderProcessingSkeleton() {
  const target = $("#workflowPreview");
  if (!target) return;
  target.innerHTML = `
    <div class="processing-preview" aria-hidden="true">
      <div class="processing-preview-head">
        <span class="skeleton skeleton-icon"></span>
        <div><span class="skeleton skeleton-line wide"></span><span class="skeleton skeleton-line short"></span></div>
      </div>
      <div class="processing-preview-table">
        <span class="skeleton skeleton-row"></span>
        <span class="skeleton skeleton-row"></span>
        <span class="skeleton skeleton-row"></span>
        <span class="skeleton skeleton-row"></span>
      </div>
    </div>`;
}

function enhanceFileInput(input) {
  if (!input || input.dataset.dropEnhanced === "1") return;
  input.dataset.dropEnhanced = "1";

  const shell = document.createElement("div");
  shell.className = "file-drop-shell";
  input.parentNode.insertBefore(shell, input);
  shell.appendChild(input);

  const hint = document.createElement("span");
  hint.className = "file-drop-hint";
  hint.innerHTML = '<i aria-hidden="true"></i><span>Arraste o arquivo aqui ou clique para selecionar</span>';
  shell.appendChild(hint);

  const activate = event => {
    event.preventDefault();
    event.stopPropagation();
    shell.classList.add("is-dragging");
  };
  const deactivate = event => {
    event.preventDefault();
    event.stopPropagation();
    shell.classList.remove("is-dragging");
  };

  ["dragenter","dragover"].forEach(name => shell.addEventListener(name, activate));
  ["dragleave","drop"].forEach(name => shell.addEventListener(name, deactivate));
  shell.addEventListener("drop", event => {
    const dropped = [...(event.dataTransfer?.files || [])];
    if (!dropped.length) return;
    const transfer = new DataTransfer();
    const limit = input.multiple ? dropped.length : Math.min(1, dropped.length);
    dropped.slice(0, limit).forEach(file => transfer.items.add(file));
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", {bubbles:true}));
  });
}

function enhanceFileInputs(root=document) {
  root.querySelectorAll('input[type="file"]').forEach(enhanceFileInput);
}


function unlockProtectedInput(input) {
  if (!input) return;
  const unlock = () => input.removeAttribute("readonly");
  input.addEventListener("pointerdown", unlock, {once:true});
  input.addEventListener("focus", unlock, {once:true});
}

function clearAutofilledSearch() {
  if (!search) return;
  const value = String(search.value || "").trim();
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
    search.value = "";
    filterCompanies();
  }
}

unlockProtectedInput(search);
unlockProtectedInput($("#adminAccess"));
requestAnimationFrame(clearAutofilledSearch);
setTimeout(clearAutofilledSearch, 200);
setTimeout(clearAutofilledSearch, 900);
window.addEventListener("pageshow", () => setTimeout(clearAutofilledSearch, 50));


function normalize(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function statusFor(company) {
  const status = company?.capabilities?.status;
  if (status === "api_ready") return "Disponível · em validação";
  if (status === "fiscal_only") return "Fiscal disponível";
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
  $('#totalCompanies').textContent = companies.length || '—';
  $('#organizerCompanies').textContent = companies.filter(c=>c.capabilities?.status==='api_ready').length;
  $('#fiscalCompanies').textContent = companies.filter(c=>(c.capabilities?.tools || []).includes('conferencia_fiscal')).length;
  if (!items.length) {
    grid.innerHTML = '<div class="empty-state">Nenhuma empresa encontrada.</div>';
    return;
  }

  items.forEach((company, index) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "company-card company-card-button company-row";
    row.dataset.availability = company.capabilities?.status || 'unknown';
    row.style.setProperty("--row-index", String(Math.min(index, 12)));

    const code = document.createElement("span");
    code.className = "company-row-code";
    code.textContent = company.codigo;

    const main = document.createElement("span");
    main.className = "company-row-main";
    const name = document.createElement("strong");
    name.className = "company-row-name";
    name.textContent = company.nome;
    const meta = document.createElement("span");
    meta.className = "company-row-meta";
    const regime = document.createElement("span");
    regime.className = "company-row-regime";
    regime.textContent = company.regime;
    const status = document.createElement("span");
    status.className = "mini-status";
    status.textContent = statusFor(company);
    meta.append(regime, status);
    main.append(name, meta);

    const action = document.createElement("span");
    action.className = "company-row-action";
    action.innerHTML = '<span>Abrir</span><b aria-hidden="true">→</b>';

    row.append(code, main, action);
    row.addEventListener("click", () => openCompany(company));
    grid.appendChild(row);
  });
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
  $('#currentSection').textContent = `Empresa ${company.codigo}`;
  document.querySelectorAll(".global-view").forEach(view => view.classList.remove("active"));
  document.querySelectorAll(".main-nav-btn").forEach(btn => btn.classList.toggle("active",btn.dataset.view==='companies'));
  $("#panelCode").textContent = `Empresa ${company.codigo}`;
  $("#panelName").textContent = company.nome;
  $("#panelRegime").textContent = company.regime;
  $("#panelStatus").textContent = statusFor(company);

  const quickInfo = $("#panelQuickInfo");
  quickInfo.replaceChildren();
  Object.entries(company.capabilities?.banks || {}).forEach(([bank, account]) => {
    const badge = document.createElement("span");
    badge.textContent = bankLabel(bank, account);
    quickInfo.appendChild(badge);
  });

  const available = ["api_ready", "fiscal_only"].includes(company.capabilities?.status);
  $("#toolUnavailable").hidden = available;
  $$(".tool-tabs, .tool-pane").forEach(el => {
    if (el.classList.contains("tool-tabs")) el.hidden = !available;
    else if (!available) el.classList.remove("active");
  });

  if (available) {
    renderWorkflow(company);
    enhanceFileInputs(panel);
    setProcessStage("upload");
    activateTool(company.capabilities?.status === "fiscal_only" ? "fiscal" : "organizar");
    refreshBaseStats();
  }

  processMessage.textContent = "";
  $("#learnMessage").textContent = "";
  $("#classifyMessage").textContent = "";
  $("#reconcileMessage").textContent = "";
  $("#fiscalMessage").textContent = "";
  clearToolResult("#reconcileResult");
  clearToolResult("#fiscalResult");
  clearToolResult("#taxResult");
  workspace.hidden = true;
  $(".hero").hidden = true;
  panel.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function closeCompany() {
  cancelAutomaticPreview();
  cancelClassificationPreview();
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

function renderReportResult(target, {title, text, tone="success", metrics=[], blob=null, filename=""}) {
  if (!target) return;
  target.replaceChildren();
  target.hidden = false;
  target.className = `tool-result compact-result is-${tone}`;

  const head = document.createElement("div");
  head.className = "tool-result-head";
  const icon = document.createElement("span");
  icon.className = "tool-result-icon";
  icon.setAttribute("aria-hidden","true");
  const copy = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = title;
  const paragraph = document.createElement("span");
  paragraph.textContent = text;
  copy.append(heading, paragraph);
  head.append(icon, copy);
  target.appendChild(head);

  if (metrics.length) {
    const grid = document.createElement("div");
    grid.className = "tool-result-metrics";
    metrics.forEach(([label,value]) => {
      const item = document.createElement("span");
      const small = document.createElement("small");
      small.textContent = label;
      const strong = document.createElement("strong");
      strong.textContent = String(value ?? "—");
      item.append(small,strong);
      grid.appendChild(item);
    });
    target.appendChild(grid);
  }

  if (blob && filename) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-download";
    button.textContent = "Baixar relatório";
    button.addEventListener("click", () => downloadBlob(
      new Response(blob, {headers:{"Content-Disposition":`attachment; filename="${filename}"`}}),
      filename
    ));
    target.appendChild(button);
  }
}

function clearToolResult(id) {
  const target = $(id);
  if (!target) return;
  target.hidden = true;
  target.replaceChildren();
}

let autoPreviewTimer;
let previewController;
let previewVersion = 0;
function cancelAutomaticPreview() {
  clearTimeout(autoPreviewTimer);
  previewController?.abort();
  previewVersion++;
  form.querySelectorAll("button.is-loading").forEach(button => {
    button.disabled = false;
    button.classList.remove("is-loading");
  });
}
function updateUploadProgress() {
  let progress = form.querySelector(".upload-progress");
  if (!progress) { progress=document.createElement("div");progress.className="upload-progress";progress.setAttribute("role","status");form.querySelector(".form-card-header").after(progress); }
  const workflow=selected?.capabilities?.workflow;
  const inputs=workflow==="advanced" ? [...form.querySelectorAll("[data-role]")] : workflow==="standard_multi_bank" ? [...form.querySelectorAll("[data-bank]")] : [fileInput];
  const required=inputs.filter(input=>input.required);
  const filled=inputs.filter(input=>input.files.length);
  const missing=required.filter(input=>!input.files.length);
  const names=missing.map(input=>form.querySelector(`label[for="${input.id}"]`)?.textContent.trim() || "arquivo");
  progress.textContent=required.length ? `${required.length-missing.length} de ${required.length} campos obrigatórios preenchidos${missing.length ? " · Falta: "+names.join(", ") : " · Pronto para prévia"}` : `${filled.length} campo(s) com arquivos · Selecione pelo menos um para conferir`;
}
function scheduleAutomaticPreview() {
  cancelAutomaticPreview();
  updateUploadProgress();
  $("#workflowPreview").replaceChildren();
  processMessage.textContent = "";
  const workflow = selected?.capabilities?.workflow;
  const inputs = workflow === "advanced" ? [...form.querySelectorAll("[data-role]")]
    : workflow === "standard_multi_bank" ? [...form.querySelectorAll("[data-bank]")] : [fileInput];
  const missing = inputs.filter(input => input.required && !input.files.length);
  const hasFiles = inputs.some(input => input.files.length);
  if (!hasFiles || missing.length || !form.checkValidity()) {
    setProcessStage("upload", "Aguardando arquivos", missing.length
      ? "Complete os arquivos obrigatórios para mostrar a prévia automaticamente."
      : "A prévia aparece automaticamente após selecionar os arquivos.");
    return;
  }
  const start = form.querySelector('[data-option="data_inicial"]') || $("#processStart");
  const end = form.querySelector('[data-option="data_final"]') || $("#processEnd");
  if (start.value && end.value && start.value > end.value) {
    setProcessStage("error", "Confira o período", "A data inicial deve ser anterior ou igual à data final.");
    return;
  }
  setProcessStage("upload", "Preparando prévia automática", "Os arquivos estão prontos. A prévia será atualizada em instantes.");
  autoPreviewTimer = setTimeout(() => form.requestSubmit(processButton), 800);
}
form.addEventListener("change", scheduleAutomaticPreview);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selected) return;
  clearTimeout(autoPreviewTimer);
  previewController?.abort();
  const controller = new AbortController();
  previewController = controller;
  const currentVersion = ++previewVersion;
  const companyCode=selected.codigo;
  const cap = selected.capabilities || {};
  const workflow = cap.workflow || "standard";
  const submitButton = event.submitter || processButton;
  $("#workflowPreview").replaceChildren();
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
      const bankOptions=$$("[data-selected-bank]");
      if(bankOptions.length) {
        options.bancos=bankOptions.filter(input=>input.checked).map(input=>input.dataset.selectedBank);
        if(!options.bancos.length)throw new Error("Selecione pelo menos um banco para organizar.");
      }
      data.append("roles_json", JSON.stringify(roles));
      data.append("options_json", JSON.stringify(options));
      endpoint = `${API()}/api/v1/workflow/${selected.codigo}`;
      if (event.submitter?.dataset.output) endpoint += `/${event.submitter.dataset.output}`;
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
      data.append("options_json",JSON.stringify({data_inicial:$("#processStart").value,data_final:$("#processEnd").value}));
      endpoint = `${API()}/api/v1/modelo-dominio/${selected.codigo}/multi`;
    } else {
      const files = [...fileInput.files];
      if (!files.length) throw new Error("Selecione pelo menos um arquivo.");
      data.append("bank", bankSelect.value);
      data.append("options_json",JSON.stringify({data_inicial:$("#processStart").value,data_final:$("#processEnd").value}));
      files.forEach(file => data.append("files", file));
    }

    processMessage.textContent = "";
    submitButton.disabled = true;
    submitButton.classList.add("is-loading");
    setProcessStage("processing", "Processando arquivos", "O Razync está lendo, organizando e montando os lançamentos.");
    renderProcessingSkeleton();
    const response = await fetch(endpoint, { method: "POST", body: data, signal:controller.signal });
    if (currentVersion !== previewVersion) return;
    if (!response.ok) throw new Error(await responseError(response));
    if (event.submitter?.dataset.output === "preview") {
      if(selected?.codigo!==companyCode)return;
      showWorkflowPreview(await response.json());
      processMessage.textContent = "";
      setProcessStage("review", "Prévia concluída", "Confira os lançamentos e os totais antes de baixar.");
      return;
    }
    if (event.submitter?.dataset.output === "reports") {
      await downloadBlob(response, `RAZYNC_${companyCode}_RELATORIOS.zip`);
      $("#workflowPreview").replaceChildren();
      processMessage.textContent = "";
      setProcessStage("review", "Relatórios gerados", "Os arquivos foram preparados e baixados com sucesso.");
      return;
    }
    const workbook = await response.blob();
    const previewData = new FormData();
    previewData.append("file", workbook, "modelo.xlsx");
    const previewResponse = await fetch(`${API()}/api/v1/modelo-preview`, {method:"POST", body:previewData, signal:controller.signal});
    if (!previewResponse.ok) throw new Error(await responseError(previewResponse));
    if (selected?.codigo !== companyCode || currentVersion !== previewVersion) return;
    const previewResult = await previewResponse.json();
    if (selected?.codigo !== companyCode || currentVersion !== previewVersion) return;
    showWorkflowPreview(previewResult);
    const download = document.createElement("button");
    download.type = "button";
    download.textContent = "Baixar Modelo Domínio";
    const disposition = response.headers.get("content-disposition");
    download.addEventListener("click", () => downloadBlob(new Response(workbook, {headers:disposition ? {"Content-Disposition":disposition} : {}}), `RAZYNC_${companyCode}_MODELO_DOMINIO.xlsx`));
    download.className = "preview-download";
    ($("#workflowPreview .preview-primary-actions") || $("#workflowPreview")).append(download);
    processMessage.textContent = "";
    setProcessStage("review", "Modelo pronto para conferência", "Revise a prévia e baixe o Modelo Domínio quando estiver tudo certo.");
  } catch (error) {
    if (error.name === "AbortError" || currentVersion !== previewVersion) return;
    $("#workflowPreview").replaceChildren();
    processMessage.textContent = error.message;
    setProcessStage("error", "Não foi possível processar", error.message);
  } finally {
    if (currentVersion === previewVersion) {
      submitButton.disabled = false;
      submitButton.classList.remove("is-loading");
    }
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

let classificationController;
function cancelClassificationPreview() {
  classificationController?.abort();
  $("#classificationPreview").replaceChildren();
  classifyForm.querySelector('button[type="submit"]').disabled = false;
}
classifyForm.addEventListener("change", () => {
  cancelClassificationPreview();
  $("#classifyMessage").textContent = "";
});

classifyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#classifyFile").files[0];
  if (!file) return $("#classifyMessage").textContent = "Selecione o Modelo Domínio.";
  cancelClassificationPreview();
  const controller = new AbortController();
  classificationController = controller;
  const companyCode = selected.codigo;
  const target = $("#classificationPreview");
  const button = event.submitter;
  button.disabled = true;
  const data = new FormData();
  data.append("file", file);
  if ([242, 1408].includes(Number(selected.codigo))) {
    const column = $("#classificationColumn").value;
    data.append("options_json", JSON.stringify({
      modo_consolidado: !column && $("#eletroConsolidated").checked,
      coluna_substituir: column,
      valores_substituiveis: $("#classificationValues").value.split(",").map(v => v.trim())
    }));
  }
  $("#classifyMessage").textContent = "Classificando…";
  try {
    const response = await fetch(`${API()}/api/v1/base-inteligente/${companyCode}/classificar`, {method:"POST", body:data, signal:controller.signal});
    if (!response.ok) throw new Error(await responseError(response));
    const raw = response.headers.get("x-razync-summary");
    const summary = raw ? JSON.parse(raw) : {};
    const workbook = await response.blob();
    const previewData = new FormData(); previewData.append("file",workbook,"classificado.xlsx");
    const preview = await fetch(`${API()}/api/v1/modelo-preview`,{method:"POST",body:previewData,signal:controller.signal});
    if (!preview.ok) throw new Error(await responseError(preview));
    const result = await preview.json();
    if (controller.signal.aborted || selected?.codigo !== companyCode) return;
    showWorkflowPreview(result,target);
    const download = document.createElement("button");download.type="button";download.className="preview-download";
    download.textContent="Baixar Excel classificado";
    const disposition=response.headers.get("content-disposition");
    download.addEventListener("click",()=>downloadBlob(new Response(workbook,{headers:disposition ? {"Content-Disposition":disposition} : {}}),`RAZYNC_${companyCode}_CLASSIFICADO.xlsx`));
    target.querySelector(".preview-primary-actions").append(download);
    $("#classifyMessage").textContent = `Classificação concluída: ${summary.automaticos || 0} automáticos. Confira a prévia antes de baixar.`;
  } catch (error) {
    if (controller.signal.aborted || selected?.codigo !== companyCode) return;
    $("#classifyMessage").textContent = error.message;
  } finally {
    if (classificationController === controller) button.disabled = false;
  }
});

reconcileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearToolResult("#reconcileResult");
  const model = $("#modelFile").files[0];
  const statements = [...$("#statementFiles").files];
  if (!model || !statements.length) return $("#reconcileMessage").textContent = "Envie o Modelo Domínio e pelo menos um extrato.";
  const data = new FormData();
  data.append("bank", $("#reconcileBank").value);
  data.append("model_file", model);
  data.append("options_json", JSON.stringify({data_inicial: $("#reconcileStart").value, data_final: $("#reconcileEnd").value}));
  statements.forEach(file => data.append("statement_files", file));
  $("#reconcileMessage").textContent = "Conferindo lançamentos…";
  try {
    const response = await fetch(`${API()}/api/v1/conferencia-extrato/${selected.codigo}`, {method:"POST", body:data});
    if (!response.ok) throw new Error(await responseError(response));
    const raw = response.headers.get("x-razync-summary");
    const summary = raw ? JSON.parse(raw) : {};
    const report = await response.blob();
    const ok = Boolean(summary.ok);
    renderReportResult($("#reconcileResult"), {
      title: ok ? "Conferência concluída sem divergências" : "Conferência concluída com diferenças",
      text: ok ? "Modelo Domínio e extrato estão batendo dentro dos critérios da conferência." : "Revise os lançamentos apontados no relatório antes de finalizar.",
      tone: ok ? "success" : "warning",
      metrics: [
        ["Faltando no Modelo", summary.faltando_planilha || 0],
        ["A mais no Modelo", summary.a_mais_planilha || 0],
        ["Extratos enviados", statements.length],
      ],
      blob: report,
      filename: `RAZYNC_${selected.codigo}_CONFERENCIA_EXTRATO.xlsx`
    });
    $("#reconcileMessage").textContent = "";
  } catch (error) {
    $("#reconcileMessage").textContent = error.message;
    renderReportResult($("#reconcileResult"), {title:"Não foi possível concluir", text:error.message, tone:"error"});
  }
});

fiscalForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearToolResult("#fiscalResult");
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
    const raw = response.headers.get("x-razync-summary");
    const summary = raw ? JSON.parse(raw) : {};
    const report = await response.blob();
    renderReportResult($("#fiscalResult"), {
      title:"Conferência fiscal pronta",
      text:"O relatório foi processado. Confira o resumo e baixe o arquivo detalhado.",
      metrics:[
        ["Linhas no resumo", summary.linhas_resumo || 0],
        ["Filial", summary.filial_aplicada || "Todas"],
        ["Período fiscal", summary.periodo_fiscal || "—"],
        ["Período razão", summary.periodo_razao || "—"],
      ],
      blob:report,
      filename:`RAZYNC_${selected.codigo}_CONFERENCIA_FISCAL.xlsx`
    });
    $("#fiscalMessage").textContent = "";
  } catch (error) {
    $("#fiscalMessage").textContent = error.message;
    renderReportResult($("#fiscalResult"), {title:"Falha na conferência fiscal", text:error.message, tone:"error"});
  }
});

function filterCompanies() {
  const query = normalize(search.value.trim());
  const regime = $('#regimeFilter').value;
  render(companies.filter(company =>
    (!regime || company.regime === regime) &&
    (companyFilter==='all' || company.capabilities?.status === (companyFilter==='organizer'?'api_ready':'fiscal_only')) &&
    (normalize(company.codigo).includes(query) ||
    normalize(company.nome).includes(query) ||
    normalize(company.regime).includes(query))
  ));
}
search.addEventListener("input", filterCompanies);
$('#regimeFilter').addEventListener('change',filterCompanies);
$$('.company-filter').forEach(button=>button.addEventListener('click',()=>{
  companyFilter=button.dataset.filter;
  $$('.company-filter').forEach(item=>{item.classList.toggle('active',item===button);item.setAttribute('aria-pressed',String(item===button));});
  filterCompanies();
}));
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
  filterCompanies();
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
enhanceFileInputs(panel);


function showGlobalView(name) {
  $('#currentSection').textContent = {companies:'Empresas',converter:'Conversor de Extratos',ledger:'Conciliação com Razão'}[name];
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
  window.scrollTo({top:0, behavior:"smooth"});
}

document.querySelectorAll(".main-nav-btn").forEach(btn => {
  btn.addEventListener("click", () => showGlobalView(btn.dataset.view));
});

function humanFileSize(bytes) {
  const size = Number(bytes || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function updateFileSelection(input) {
  input.classList.toggle("has-files", input.files.length > 0);
  input.title = input.files.length
    ? [...input.files].map(file => file.name).join("\n")
    : "";

  const shell = input.closest(".file-drop-shell");
  let selection = shell?.querySelector(":scope > .file-selection");
  if (!selection) {
    selection = document.createElement("div");
    selection.className = "file-selection";
    if (shell) shell.appendChild(selection);
    else input.insertAdjacentElement("afterend", selection);
  }
  selection.replaceChildren();

  if (!input.files.length) {
    selection.hidden = true;
    return;
  }

  selection.hidden = false;
  [...input.files].slice(0, 4).forEach(file => {
    const item = document.createElement("span");
    item.className = "file-selection-item";
    const icon = document.createElement("i");
    icon.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = file.name;
    const meta = document.createElement("small");
    meta.textContent = humanFileSize(file.size);
    text.append(name, meta);
    item.append(icon, text);
    selection.appendChild(item);
  });

  if (input.files.length > 4) {
    const more = document.createElement("span");
    more.className = "file-selection-more";
    more.textContent = `+${input.files.length - 4} arquivo(s)`;
    selection.appendChild(more);
  }

  if (input.closest("#processForm")) {
    setProcessStage("upload", "Arquivos prontos", input.files.length === 1
      ? "1 arquivo selecionado para processamento."
      : `${input.files.length} arquivos selecionados para processamento.`);
  }
}

panel.addEventListener("change", event => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
  updateFileSelection(input);
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
  clearToolResult("#taxResult");
  const balance = $("#taxBalance").files[0];
  const revenue = $("#taxRevenue").files[0];
  const msg = $("#taxMessage");
  if (!balance || !revenue) return msg.textContent = "Envie o balancete e o relatório DCTFWeb/Receita.";
  try {
    const result = await runTaxComparison(balance, revenue, msg);
    renderReportResult($("#taxResult"), {
      title: result.summary.revisar ? "Conferência com pontos para revisar" : "Impostos conferindo",
      text: result.summary.revisar ? "Existem impostos com diferença. Use o relatório detalhado para revisar os valores." : "Os impostos localizados estão conferindo com o relatório informado.",
      tone: result.summary.revisar ? "warning" : "success",
      metrics:[
        ["Impostos", result.summary.impostos || 0],
        ["Conferem", result.summary.conferem || 0],
        ["Revisar", result.summary.revisar || 0],
      ],
      blob:result.report,
      filename:`RAZYNC_${selected.codigo}_CONFERENCIA_IMPOSTOS.xlsx`
    });
    msg.textContent = "";
  } catch (error) {
    msg.textContent = error.message;
    renderReportResult($("#taxResult"), {title:"Falha na conferência de impostos", text:error.message, tone:"error"});
  }
});

async function runTaxComparison(balance, revenue, msgElement) {
  const companyCode=selected.codigo;
  const data = new FormData();
  data.append("receita", revenue);
  data.append("balancete", balance);
  data.append("competencia", $("#taxCompetence").value);
  msgElement.textContent = "Conferindo impostos…";
  const response = await fetch(`${API()}/api/v1/conferencia-impostos/${companyCode}`, {method:"POST", body:data});
  if (!response.ok) throw new Error(await responseError(response));
  const raw = response.headers.get("x-razync-summary");
  const summary = raw ? JSON.parse(raw) : {};
  const report = await response.blob();
  return {summary, report};
}

const originalLoadCompanies = loadCompanies;
loadCompanies = async function() {
  await originalLoadCompanies();
  const select=$("#taskCompany");
  if(select) {
    select.innerHTML='<option value="">Sem empresa específica</option>'+companies.map(c=>`<option value="${c.codigo}">${c.codigo} · ${c.nome}</option>`).join("");
  }
};

loadCompanies();
