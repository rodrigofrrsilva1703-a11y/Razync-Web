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

let companies = [];
let selected = null;
let companyFilter = 'all';

const API = () => String(window.RAZYNC_CONFIG?.apiBase || "").replace(/\/$/, "");

function dateApiValue(input) {
  return String(input?.value || "").trim();
}

function readPeriod(startSelector, endSelector) {
  const start = dateApiValue($(startSelector));
  const end = dateApiValue($(endSelector));
  if (Boolean(start) !== Boolean(end)) throw new Error("Informe as duas datas do período.");
  if (start && end && end < start) throw new Error("A data final não pode ser anterior à data inicial.");
  return {data_inicial:start, data_final:end};
}

function appendPeriod(formData, startSelector, endSelector) {
  const period = readPeriod(startSelector,endSelector);
  formData.append("data_inicial",period.data_inicial);
  formData.append("data_final",period.data_final);
  return period;
}

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
  box.setAttribute("aria-busy", String(stage === "processing"));
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
  hint.querySelector("span").textContent = input.multiple
    ? "Adicione arquivos ou arraste aqui. Novas seleções mantêm os anexos anteriores."
    : "Arraste o arquivo aqui ou clique para selecionar";
  let retained = [...input.files];
  input.addEventListener("change", () => {
    if (input.multiple && !input.dataset.replacingFiles) {
      const files = [...retained, ...input.files];
      const unique = files.filter((file, index) => files.findIndex(other =>
        other.name === file.name && other.size === file.size && other.lastModified === file.lastModified) === index);
      const transfer = new DataTransfer();
      unique.forEach(file => transfer.items.add(file));
      input.files = transfer.files;
    }
    retained = [...input.files];
    updateFileSelection(input);
  });
  input.form?.addEventListener("reset", () => {
    retained = [];
    queueMicrotask(() => updateFileSelection(input));
  });

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

function hasCompanyTools(company) {
  return Array.isArray(company?.capabilities?.tools) && company.capabilities.tools.length > 0;
}

function statusFor(company) {
  if (!hasCompanyTools(company)) return "";
  const status = company?.capabilities?.status;
  if (status === "api_ready") return "Disponível · em validação";
  if (status === "catalog_only") return "";
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
  const current = companies.filter(companyBelongsToPortfolio);
  count.textContent = `${items.length} de ${current.length} empresas`;
  $('#totalCompanies').textContent = current.length;
  $('#organizerCompanies').textContent = current.filter(hasCompanyTools).length;
  $('#multiBankCompanies').textContent = current.filter(c=>Object.keys(c.capabilities?.banks || {}).length > 1).length;
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state directory-empty';
    const title = document.createElement('strong');title.textContent=current.length ? 'Nenhuma empresa encontrada' : 'Esta carteira ainda não tem empresas';
    const help = document.createElement('p');help.textContent=current.length ? 'Tente outro código ou nome, ou remova os filtros para ver sua carteira.' : 'Adicione uma empresa para começar.';
    const reset = document.createElement('button');reset.type='button';reset.textContent='Limpar filtros';
    reset.addEventListener('click',resetCompanyFilters);
    empty.append(title,help);if(current.length)empty.appendChild(reset);grid.appendChild(empty);
    return;
  }

  items.forEach((company, index) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "company-card company-card-button company-row";
    row.dataset.availability = company.capabilities?.status || 'unknown';
    row.setAttribute('aria-label', `${company.codigo} · ${company.nome}. ${hasCompanyTools(company) ? 'Abrir ferramentas' : 'Ver empresa'}`);
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
    status.textContent = hasCompanyTools(company) ? statusFor(company) : 'Sem ferramenta';
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

function bankName(bank) {
  const names = {
    itau:"Itaú", itau_508:"Itaú", itau_509:"Itaú",
    bradesco:"Bradesco", sicredi:"Sicredi", banco_brasil:"Banco do Brasil",
    caixa:"Caixa", inter:"Banco Inter", safra:"Safra", btg:"BTG",
    santander:"Santander", daycoval:"Daycoval", fibra:"Banco Fibra"
  };
  return names[bank] || bank;
}

function workflowBankName(bank) {
  const names = {
    itau:"Itaú",
    bradesco:"Bradesco",
    fibra:"Fibra",
    daycoval:"Daycoval",
    banco_brasil:"Banco do Brasil",
    sicredi:"Sicredi",
    caixa:"Caixa",
    inter:"Banco Inter",
    safra:"Safra",
    btg:"BTG",
    santander:"Santander"
  };
  return names[bank] || bankName(bank);
}

function renderBankSelector(container, banks, options={}) {
  if (!container) return;
  const entries = Object.entries(banks || {});
  container.replaceChildren();
  container.hidden = !entries.length;
  if (!entries.length) return;

  const {
    mode="single",
    selectElement=null,
    controlBankFields=false,
    controlRoleFields=false,
    sendSelectedBanks=false,
    onSelectionChange=null,
    selectAllByDefault=true
  } = options;

  const head = document.createElement("div");
  head.className = "bank-selector-head";
  const copy = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = mode === "multi" ? "Selecionar bancos" : "Selecionar banco";
  const hint = document.createElement("span");
  hint.textContent = mode === "multi"
    ? `${entries.length} banco(s) disponível(is) · escolha quais entram neste processamento.`
    : "Escolha o banco usado nesta ferramenta.";
  copy.append(title,hint);
  head.appendChild(copy);

  const list = document.createElement("div");
  list.className = "bank-selector-options";

  const applyBankState = (bank, checked) => {
    if (controlBankFields) {
      const field = advancedFields.querySelector(`[data-bank-group="${bank}"]`);
      const input = field?.querySelector("[data-bank]");
      if (field) field.hidden = !checked;
      if (input) {
        input.disabled = !checked;
        if (!checked) {
          input.value = "";
          updateFileSelection(input);
        }
      }
    }
    if (controlRoleFields) {
      const field = advancedFields.querySelector(`[data-role-group="${bank}"]`);
      const input = field?.querySelector("[data-role]");
      if (field) field.hidden = !checked;
      if (input) {
        input.disabled = !checked;
        if (!checked) {
          input.value = "";
          updateFileSelection(input);
        }
      }
    }
  };

  let selectAllButton = null;
  const choices = [];

  entries.forEach(([bank, account], index) => {
    const label = document.createElement("label");
    label.className = "bank-choice";

    const input = document.createElement("input");
    input.type = mode === "multi" ? "checkbox" : "radio";
    input.name = mode === "multi" ? `bank_choice_${container.id}` : `bank_single_${container.id}`;
    input.value = bank;
    input.dataset.bankChoice = bank;
    input.checked = mode === "multi" ? (selectAllByDefault || index === 0) : index === 0;
    if (sendSelectedBanks) input.dataset.selectedBank = workflowBankName(bank);

    const textBox = document.createElement("span");
    const strong = document.createElement("strong");
    strong.textContent = bankName(bank);
    const small = document.createElement("small");
    small.textContent = account ? `Conta ${account}` : "Conta não informada";
    textBox.append(strong,small);

    label.append(input,textBox);
    list.appendChild(label);

    const choice = {bank,input,label};
    choices.push(choice);

    if (input.checked) applyBankState(bank,true);
    if (mode === "single" && input.checked && selectElement) selectElement.value = bank;

    input.addEventListener("change", () => {
      if (mode === "single") {
        if (selectElement) selectElement.value = bank;
        choices.forEach(item => item.label.classList.toggle("selected", item.input.checked));
      } else {
        applyBankState(bank,input.checked);
        label.classList.toggle("selected",input.checked);
        updateSelectAllButton();
      }
      if (typeof onSelectionChange === "function") {
        onSelectionChange(choices.filter(item => item.input.checked).map(item => item.bank));
      }
    });

    label.classList.toggle("selected",input.checked);
  });

  const updateSelectAllButton = () => {
    if (!selectAllButton) return;
    const selectedCount = choices.filter(choice => choice.input.checked).length;
    const allSelected = selectedCount === choices.length;
    selectAllButton.textContent = allSelected ? "Todos os bancos selecionados" : "Selecionar todos os bancos";
    selectAllButton.dataset.allSelected = String(allSelected);
    selectAllButton.setAttribute("aria-pressed",String(allSelected));
  };

  if (mode === "multi" && entries.length > 1) {
    selectAllButton = document.createElement("button");
    selectAllButton.type = "button";
    selectAllButton.className = "bank-select-all";
    selectAllButton.addEventListener("click", () => {
      const shouldSelect = !choices.every(choice => choice.input.checked);
      choices.forEach(choice => {
        choice.input.checked = shouldSelect;
        choice.label.classList.toggle("selected",shouldSelect);
        applyBankState(choice.bank,shouldSelect);
      });
      updateSelectAllButton();
      if (typeof onSelectionChange === "function") {
        onSelectionChange(choices.filter(item => item.input.checked).map(item => item.bank));
      }
      container.closest("form")?.dispatchEvent(new Event("change",{bubbles:true}));
    });
    head.appendChild(selectAllButton);
    updateSelectAllButton();
  }

  container.append(head,list);
}
const COMPANY_TOOL_GUIDES = {
  266: {
    organizar: {
      caption: "Empresa 266 · Nova Geração",
      intro: "A 266 usa uma planilha consolidada com os movimentos de Itaú, Bradesco, Fibra e Banco do Brasil. O Razync identifica os lançamentos pela conta bancária na coluna Conta.",
      steps: [
        ["1", "Selecione os bancos", "Marque Itaú 508, Bradesco 9, Fibra 506 e/ou Banco do Brasil 8. Para o Banco do Brasil, o relatório precisa trazer a conta bancária 200076-8 na coluna Conta."],
        ["2", "Envie a planilha consolidada", "Anexe a planilha mensal recebida da empresa. Não precisa separar um arquivo para cada banco."],
        ["3", "Informe o período se necessário", "Deixe De/Até em branco para considerar todo o arquivo ou use as datas para limitar os lançamentos."],
        ["4", "Confira antes de baixar", "Revise a prévia gerada. O Modelo Domínio final fica separado por banco em abas próprias."]
      ],
      note: "Contas contábeis: Itaú 508 · Bradesco 9 · Fibra 506 · Banco do Brasil 8. Identificação bancária do BB: 200076-8."
    },
    base: {
      caption: "Empresa 266 · Nova Geração",
      intro: "Use a Base Inteligente depois da revisão do Modelo Domínio. Ela aprende os padrões da própria 266 e pode aplicar as contas em arquivos futuros.",
      steps: [
        ["1", "Ensine com arquivo revisado", "Em “Ensinar à base”, envie um Modelo Domínio da 266 que já esteja conferido e com as contas corretas."],
        ["2", "Classifique o arquivo novo", "Em “Classificar arquivo”, envie o Modelo Domínio que ainda precisa receber as classificações aprendidas."],
        ["3", "Revise a prévia", "Confira os lançamentos classificados antes de baixar. Os padrões ficam separados por empresa e banco."]
      ],
      note: "Use arquivos da própria empresa 266 para não misturar padrões com outras empresas."
    },
    extrato: {
      caption: "Empresa 266 · Nova Geração",
      intro: "A conferência compara o Modelo Domínio final com os extratos dos bancos selecionados e mostra as diferenças de entradas e saídas por dia.",
      steps: [
        ["1", "Selecione os bancos", "Escolha somente os bancos que serão conferidos: Itaú 508, Bradesco 9, Fibra 506 e/ou Banco do Brasil 8."],
        ["2", "Envie o Modelo Domínio final", "Use o arquivo já organizado e, se necessário, classificado pela Base Inteligente."],
        ["3", "Anexe os extratos correspondentes", "Envie o extrato de cada banco selecionado no campo que aparece para ele."],
        ["4", "Analise o status diário", "Saldo Entrada = Entrada Modelo − Entrada Extrato e Saldo Saída = Saída Modelo − Saída Extrato. Só fica “Batendo” quando os dois saldos forem zero."]
      ],
      note: "Se apenas entradas ou apenas saídas estiverem corretas, o dia continua como Divergente."
    }
  },
  242: {
    francesinhas: {
      caption: "Empresa 242 · Francesinhas",
      intro: "Use esta ferramenta quando receber o ZIP das francesinhas do Itaú. O Razync lê as liquidações L e gera o Modelo Domínio separado pelas contas 508 e 509.",
      steps: [
        ["1", "Envie o ZIP das francesinhas", "Anexe o arquivo ZIP com os PDFs das francesinhas do período. O sistema ignora arquivos que não sejam PDFs válidos."],
        ["2", "Informe o período se necessário", "Use De e Até apenas se quiser limitar as liquidações; em branco, todas as francesinhas válidas do ZIP são consideradas."],
        ["3", "Confira as contas", "As liquidações da conta Itaú 10531-8 vão para a conta Domínio 508 e as da 18153-7 vão para a 509."],
        ["4", "Revise antes de baixar", "Confira data, valor e histórico dos recebimentos gerados e depois baixe o Excel com as abas das contas encontradas."]
      ],
      note: "A data utilizada é a data “Emitido em” da francesinha e somente liquidações com Hist. L entram no arquivo."
    }
  }
};

function closeCompanyToolHelp(restoreFocus = false) {
  const guide = $("#companyToolGuide");
  const trigger = $("#companyToolHelpButton");
  if (!guide || !trigger) return;
  const wasOpen = !guide.hidden;
  guide.hidden = true;
  trigger.setAttribute("aria-expanded", "false");
  if (wasOpen && restoreFocus) trigger.focus();
}

const FISCAL_TOOL_GUIDE = {
  caption: "Conferência Fiscal × Contábil",
  intro: "Compare o Resumo por Acumulador com o Razão do mesmo período para identificar diferenças por conta contábil, filial e acumulador. Os arquivos originais não são alterados.",
  steps: [
    ["1", "Prepare os relatórios", "No Domínio, exporte o Resumo por Acumulador e o Razão contábil da mesma empresa e do mesmo período."],
    ["2", "Informe a filial, se necessário", "Se o Razão possuir várias filiais, informe a que deseja conferir. Com uma só filial, a identificação é automática."],
    ["3", "Envie e confira", "Anexe as duas planilhas e clique em Conferir contas. Compare os valores fiscais com os débitos de entradas ou os créditos de saídas no Razão."],
    ["4", "Investigue as diferenças", "Pesquise por conta ou acumulador e abra os lançamentos correspondentes. Para aprofundar, envie também os relatórios de Entradas e Saídas, quando disponíveis."],
    ["5", "Revise a análise com IA", "As sugestões da IA são auxiliares: confirme notas, históricos e contrapartidas antes de realizar ajustes."]
  ],
  note: "Confira se os relatórios possuem períodos compatíveis. Diferença encontrada não comprova lançamento incorreto sem verificar os documentos."
};

function renderCompanyToolGuide(toolName) {
  const guide = $("#companyToolGuide");
  const wrapper = $("#companyToolHelp");
  if (!guide || !wrapper) return;
  closeCompanyToolHelp();
  const content = toolName === "fiscal-global"
    ? FISCAL_TOOL_GUIDE
    : (COMPANY_TOOL_GUIDES[Number(selected?.codigo)]?.[toolName]
       || window.RAZYNC_COMPANY_HELP?.resolve(selected, toolName));
  wrapper.hidden = !content;
  if (!content) return;

  $("#companyToolGuideCaption").textContent = content.caption || "";
  $("#companyToolGuideIntro").textContent = content.intro || "";
  $("#companyToolGuideNote").textContent = content.note || "";

  const steps = $("#companyToolGuideSteps");
  steps.replaceChildren();
  (content.steps || []).forEach(([number,title,text]) => {
    const item = document.createElement("div");
    item.className = "company-tool-guide-step";

    const index = document.createElement("span");
    index.className = "company-tool-guide-index";
    index.textContent = number;

    const copy = document.createElement("div");
    const heading = document.createElement("strong");
    heading.textContent = title;
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    copy.append(heading,paragraph);

    item.append(index,copy);
    steps.appendChild(item);
  });
}

const companyToolHelp = $("#companyToolHelp");
const companyToolHelpButton = $("#companyToolHelpButton");
const helpPositionKey = "razync-company-help-position-v2";
const helpClamp = (n,min,max) => Math.max(min,Math.min(n,max));
let helpDrag = null, suppressHelpClick = false, helpHasCustomPosition = false;

function setCompanyHelpPosition(left,top) {
  if (!companyToolHelp || !companyToolHelpButton) return;
  const width = companyToolHelpButton.offsetWidth || 46;
  const height = companyToolHelpButton.offsetHeight || 46;
  const x = helpClamp(left,12,Math.max(12,window.innerWidth-width-12));
  const y = helpClamp(top,12,Math.max(12,window.innerHeight-height-12));
  companyToolHelp.style.left = x + "px";
  companyToolHelp.style.top = y + "px";
  companyToolHelp.style.right = "auto";
  companyToolHelp.style.bottom = "auto";
  helpHasCustomPosition = true;
}

function positionCompanyHelpGuide() {
  const guide = $("#companyToolGuide");
  if (!guide || guide.hidden || !companyToolHelpButton) return;
  const anchor = companyToolHelpButton.getBoundingClientRect();
  const panelWidth = guide.getBoundingClientRect().width;
  const allowedHeight = Math.min(window.innerHeight * .7,620);
  const above = Math.max(0,anchor.top - 22);
  const below = Math.max(0,window.innerHeight-anchor.bottom-22);
  const placeAbove = above >= Math.min(guide.scrollHeight,allowedHeight) || above >= below;
  const availableHeight = placeAbove ? above : below;
  guide.style.maxHeight = Math.max(70,Math.min(allowedHeight,availableHeight)) + "px";
  const panelHeight = guide.getBoundingClientRect().height;
  const x = helpClamp(anchor.right-panelWidth,12,Math.max(12,window.innerWidth-panelWidth-12));
  const y = placeAbove ? anchor.top-panelHeight-10 : anchor.bottom+10;
  guide.style.left = x + "px";
  guide.style.top = helpClamp(y,10,Math.max(10,window.innerHeight-panelHeight-10)) + "px";
}

function rememberCompanyHelpPosition() {
  const pos = companyToolHelpButton?.getBoundingClientRect();
  if (!pos) return;
  try {
    localStorage.setItem(helpPositionKey,JSON.stringify({x:pos.left,y:pos.top}));
  } catch (_) { /* Navegadores com armazenamento bloqueado continuam funcionando. */ }
}

function restoreCompanyHelpPosition() {
  try {
    const saved = JSON.parse(localStorage.getItem(helpPositionKey) || "null");
    if (Number.isFinite(saved?.x) && Number.isFinite(saved?.y)) {
      setCompanyHelpPosition(saved.x,saved.y);
    }
  } catch (_) { /* Posição padrão no canto. */ }
}

companyToolHelpButton?.addEventListener("pointerdown",event => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  const rect = companyToolHelpButton.getBoundingClientRect();
  helpDrag = {
    id:event.pointerId,
    startX:event.clientX, startY:event.clientY,
    left:rect.left, top:rect.top, moved:false
  };
  companyToolHelpButton.setPointerCapture?.(event.pointerId);
});
function moveCompanyHelpDrag(event) {
  if (!helpDrag || event.pointerId !== helpDrag.id) return;
  const dx = event.clientX-helpDrag.startX, dy = event.clientY-helpDrag.startY;
  if (!helpDrag.moved && Math.hypot(dx,dy) < 6) return;
  if (!helpDrag.moved) {
    helpDrag.moved = true;
    closeCompanyToolHelp();
    companyToolHelp.classList.add("is-dragging");
  }
  if (event.cancelable) event.preventDefault();
  setCompanyHelpPosition(helpDrag.left+dx,helpDrag.top+dy);
}
companyToolHelpButton?.addEventListener("pointermove",moveCompanyHelpDrag);
window.addEventListener("pointermove",moveCompanyHelpDrag);
function finishCompanyHelpDrag(event) {
  if (!helpDrag || event.pointerId !== helpDrag.id) return;
  if (helpDrag.moved) {
    suppressHelpClick = true;
    rememberCompanyHelpPosition();
    // Um arrasto não pode abrir as instruções por acidente.
    setTimeout(() => { suppressHelpClick = false; },250);
  }
  companyToolHelp.classList.remove("is-dragging");
  helpDrag = null;
  if (companyToolHelpButton.hasPointerCapture?.(event.pointerId)) {
    companyToolHelpButton.releasePointerCapture(event.pointerId);
  }
}
companyToolHelpButton?.addEventListener("pointerup",finishCompanyHelpDrag);
companyToolHelpButton?.addEventListener("pointercancel",finishCompanyHelpDrag);
window.addEventListener("pointerup",finishCompanyHelpDrag);
window.addEventListener("pointercancel",finishCompanyHelpDrag);
window.addEventListener("resize",() => {
  if (helpHasCustomPosition) {
    const rect = companyToolHelpButton.getBoundingClientRect();
    setCompanyHelpPosition(rect.left,rect.top);
  }
  positionCompanyHelpGuide();
});
restoreCompanyHelpPosition();

companyToolHelpButton?.addEventListener("click", () => {
  if (suppressHelpClick) { suppressHelpClick = false; return; }
  const guide = $("#companyToolGuide");
  if (!guide || companyToolHelp.hidden) return;
  const opening = guide.hidden;
  guide.hidden = !opening;
  companyToolHelpButton.setAttribute("aria-expanded", String(opening));
  if (opening) {
    positionCompanyHelpGuide();
    $("#companyToolGuideClose")?.focus({preventScroll:true});
  }
});
$("#companyToolGuideClose")?.addEventListener("click", () => closeCompanyToolHelp(true));
document.addEventListener("pointerdown", event => {
  if (companyToolHelp && !companyToolHelp.hidden && !companyToolHelp.contains(event.target)) {
    closeCompanyToolHelp();
  }
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && !$("#companyToolGuide")?.hidden) closeCompanyToolHelp(true);
});

function activateTool(name) {
  if (!name) return;
  panel.dataset.activeTool = name;
  renderCompanyToolGuide(name);
  $$("[data-tool].tool-tab").forEach(btn => {
    const active = btn.dataset.tool === name;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", String(active));
    btn.tabIndex = active ? 0 : -1;
  });
  $$("[data-pane].tool-pane").forEach(pane => {
    const active = pane.dataset.pane === name;
    pane.classList.toggle("active", active);
    pane.hidden = !active;
    pane.style.display = active ? "block" : "none";
    pane.setAttribute("aria-hidden", String(!active));
    pane.style.display = active ? "block" : "none";
  });
  if (name === "base" && selected?.capabilities?.status === "api_ready") {
    refreshBaseStats();
  }
}

$$(".tool-tab").forEach(btn => btn.addEventListener("click", () => activateTool(btn.dataset.tool)));

function selectedReconcileBanks() {
  return $$("#reconcileBankSelector [data-bank-choice]:checked").map(input => input.value);
}

function syncReconcileBankFields(selectedBanks = selectedReconcileBanks()) {
  const selectedSet = new Set(selectedBanks);
  $$("#reconcileStatementFields [data-reconcile-bank-group]").forEach(group => {
    const active = selectedSet.has(group.dataset.reconcileBankGroup);
    group.hidden = !active;
    const input = group.querySelector("[data-reconcile-bank]");
    if (input) input.disabled = !active;
  });
}

function renderReconcileBankFields(banks) {
  const host = $("#reconcileStatementFields");
  if (!host) return;
  host.replaceChildren();
  Object.entries(banks || {}).forEach(([bank, account]) => {
    const group = document.createElement("div");
    group.className = "reconcile-bank-file field-group";
    group.dataset.reconcileBankGroup = bank;

    const id = `reconcile_files_${bank}`;
    const label = document.createElement("label");
    label.htmlFor = id;
    label.innerHTML = `${RazyncDOM.escapeHTML(bankName(bank))} <span class="optional">Conta ${RazyncDOM.escapeHTML(account || "—")}</span>`;

    const input = document.createElement("input");
    input.id = id;
    input.type = "file";
    input.multiple = true;
    input.accept = ".pdf,.xls,.xlsx,.csv,.ofx";
    input.dataset.reconcileBank = bank;

    group.append(label,input);
    host.appendChild(group);
  });
}

function renderWorkflow(company) {
  const cap = company.capabilities || {};
  const workflow = cap.workflow || "standard";
  const banks = cap.banks || {};
  const organizerPicker = $("#organizerBankSelector");
  const reconcilePicker = $("#reconcileBankSelector");

  fillBankSelect(bankSelect, banks);
  fillBankSelect($("#reconcileBank"), banks);
  renderReconcileBankFields(banks);
  const reconcileMode = Object.keys(banks).length > 1 ? "multi" : "single";
  renderBankSelector(reconcilePicker, banks, {
    mode:reconcileMode,
    selectElement:$("#reconcileBank"),
    onSelectionChange:syncReconcileBankFields,
    selectAllByDefault:false
  });
  syncReconcileBankFields();

  organizerPicker.replaceChildren();
  organizerPicker.hidden = true;
  advancedFields.innerHTML = "";
  advancedFields.hidden = true;
  standardFields.hidden = false;

  if (workflow === "advanced") {
    standardFields.hidden = true;
    advancedFields.hidden = false;
    for (const role of cap.roles || []) {
      const wrap = document.createElement("div");
      wrap.className = "field-group";
      wrap.dataset.roleGroup = role.name;
      const id = `role_${role.name}`;
      wrap.innerHTML = `
        <label for="${RazyncDOM.escapeHTML(id)}">${RazyncDOM.escapeHTML(role.label)}${role.optional ? " <span class='optional'>(opcional)</span>" : ""}</label>
        <input id="${RazyncDOM.escapeHTML(id)}" data-role="${RazyncDOM.escapeHTML(role.name)}" type="file"
          ${role.multiple || [3,178,242,343,266,1396].includes(Number(company.codigo)) ? "multiple" : ""}
          accept="${RazyncDOM.escapeHTML(role.accept || ".pdf,.xls,.xlsx,.zip")}"
          ${role.optional ? "" : "required"}>
      `;
      advancedFields.appendChild(wrap);
    }
    for (const option of (cap.options || []).filter(option => option.type !== "date")) {
      const wrap = document.createElement("div");
      wrap.className = "field-group";
      const year = new Date().getFullYear();
      wrap.innerHTML = `
        <label for="opt_${RazyncDOM.escapeHTML(option.name)}">${RazyncDOM.escapeHTML(option.label)}</label>
        <input id="opt_${RazyncDOM.escapeHTML(option.name)}" data-option="${RazyncDOM.escapeHTML(option.name)}" type="${RazyncDOM.escapeHTML(option.type || "text")}"
          ${option.type === "number" ? `value="${year}" min="2000" max="2100"` : ""}>
      `;
      advancedFields.appendChild(wrap);
    }

    const filterByBanks = [3,178,343,266,1396].includes(Number(company.codigo));
    const roleBanks = Object.keys(banks).filter(bank => (cap.roles || []).some(role => role.name === bank));
    if (filterByBanks) {
      renderBankSelector(organizerPicker,banks,{mode:"multi",sendSelectedBanks:true});
    } else if (roleBanks.length) {
      const roleBankMap = Object.fromEntries(roleBanks.map(bank=>[bank,banks[bank]]));
      renderBankSelector(organizerPicker,roleBankMap,{mode:"multi",controlRoleFields:true});
    }

    $("#toolDescription").textContent = "Este fluxo usa arquivos complementares. Envie cada documento no campo correspondente.";
  } else if (workflow === "standard_multi_bank") {
    standardFields.hidden = true;
    advancedFields.hidden = false;
    for (const [bank, account] of Object.entries(banks)) {
      const wrap = document.createElement("div");
      wrap.className = "field-group";
      wrap.dataset.bankGroup = bank;
      wrap.innerHTML = `
        <label for="bankfiles_${RazyncDOM.escapeHTML(bank)}">${RazyncDOM.escapeHTML(bankLabel(bank, account))} <span class="optional">(opcional)</span></label>
        <input id="bankfiles_${RazyncDOM.escapeHTML(bank)}" data-bank="${RazyncDOM.escapeHTML(bank)}" type="file" multiple
          accept=".pdf,.xls,.xlsx,.csv,.ofx">
      `;
      advancedFields.appendChild(wrap);
    }
    renderBankSelector(organizerPicker,banks,{mode:"multi",controlBankFields:true});
    $("#toolDescription").textContent = "Selecione os bancos e envie os arquivos correspondentes. O Razync gera uma aba para cada banco processado.";
  } else {
    renderBankSelector(organizerPicker,banks,{mode:"single",selectElement:bankSelect});
    $("#toolDescription").textContent = "Selecione o banco, envie um ou vários arquivos e gere o Modelo Domínio.";
  }
}

async function refreshBaseStats(learnedStatus=null) {
  if (!baseStats) return;
  if (!selected || selected.capabilities?.status !== "api_ready") {
    baseStats.innerHTML = '<span><strong>—</strong> padrões</span><span><strong>—</strong> bancos</span><span><strong>—</strong> períodos</span>';
    return;
  }

  baseStats.classList.add("is-loading");
  baseStats.innerHTML = '<span><strong>…</strong> padrões</span><span><strong>…</strong> bancos</span><span><strong>…</strong> períodos</span>';

  try {
    let data = learnedStatus;
    if (!data) {
      const r = await fetch(`${API()}/api/v1/base-inteligente/${selected.codigo}/status`);
      if (!r.ok) throw new Error(await responseError(r));
      data = await r.json();
    }
    baseStats.innerHTML = `
      <span><strong>${Number(data.patterns || 0).toLocaleString("pt-BR")}</strong> padrões salvos</span>
      <span><strong>${Number(data.banks || 0).toLocaleString("pt-BR")}</strong> bancos aprendidos</span>
      <span><strong>${Number(data.periods || 0).toLocaleString("pt-BR")}</strong> períodos</span>
    `;
    baseStats.title = `Base Inteligente da empresa ${selected.codigo}`;
  } catch (error) {
    baseStats.innerHTML = '<span class="base-stat-error"><strong>!</strong> Base indisponível</span>';
    baseStats.title = error.message || "Não foi possível consultar a Base Inteligente.";
  } finally {
    baseStats.classList.remove("is-loading");
  }
}
function openCompany(company) {
  cancelReconcilePreview();
  selected = company;
  renderCompanyToolGuide("");
  const available = hasCompanyTools(company);
  const defaultTool = "organizar";
  panel.dataset.hasTools = String(available);

  // Mostra a empresa e a ferramenta padrão primeiro. Assim um erro secundário
  // de inicialização nunca deixa todas as ferramentas invisíveis.
  workspace.hidden = true;
  $(".hero").hidden = true;
  panel.hidden = false;

  $('#currentSection').textContent = `Empresa ${company.codigo}`;
  document.querySelectorAll(".global-view").forEach(view => view.classList.remove("active"));
  document.querySelectorAll(".main-nav-btn").forEach(btn => btn.classList.toggle("active",btn.dataset.view==='companies'));
  $("#panelCode").textContent = `Empresa ${company.codigo}`;
  $("#panelName").textContent = company.nome;
  $("#panelRegime").textContent = company.regime;
  const panelStatusText = statusFor(company);
  $("#panelStatus").textContent = panelStatusText;
  $("#panelStatus").hidden = !panelStatusText;

  const quickInfo = $("#panelQuickInfo");
  quickInfo.replaceChildren();
  quickInfo.hidden = !available;
  Object.entries(company.capabilities?.banks || {}).forEach(([bank, account]) => {
    const badge = document.createElement("span");
    badge.textContent = bankLabel(bank, account);
    quickInfo.appendChild(badge);
  });

  $("#toolUnavailable").hidden = available;
  $(".tool-tabs").hidden = !available;
  const adminAccess = $(".admin-access");
  if (adminAccess) adminAccess.hidden = !available;
  $$(".tool-tab").forEach(button => {
    if (button.dataset.tool === "francesinhas") return;
    button.hidden = false;
  });

  // Estado visual determinístico: uma única ferramenta ativa.
  panel.dataset.activeTool = available ? defaultTool : "";
  $$(".tool-pane").forEach(pane => {
    const active = available && pane.dataset.pane === defaultTool;
    pane.classList.toggle("active", active);
    pane.hidden = !active;
    pane.style.display = active ? "block" : "none";
    pane.setAttribute("aria-hidden", String(!active));
  });

  if (available) {
    activateTool(defaultTool);
    try {
      renderWorkflow(company);
      enhanceFileInputs(panel);
      setProcessStage("upload");
      refreshBaseStats();
    } catch (error) {
      console.error("Falha ao inicializar ferramenta da empresa:", error);
      // Mantém a ferramenta visível mesmo se algum complemento falhar.
      activateTool(defaultTool);
      if (defaultTool === "organizar") {
        processMessage.textContent = "A ferramenta foi aberta, mas um complemento da tela não carregou. Atualize a página se necessário.";
      }
    }
  }

  processMessage.textContent = processMessage.textContent || "";
  $("#learnMessage").textContent = "";
  $("#classifyMessage").textContent = "";
  $("#reconcileMessage").textContent = "";
  clearToolResult("#reconcileResult");
  clearToolResult("#taxResult");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function closeCompany() {
  closeCompanyToolHelp();
  $("#companyToolHelp").hidden = true;
  cancelReconcilePreview();
  cancelAutomaticPreview();
  cancelClassificationPreview();
  panel.hidden = true;
  workspace.hidden = !activePortfolio;
  $(".hero").hidden = !activePortfolio;
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
let organizerRunning = false;
function cancelAutomaticPreview() {
  organizerRunning = false;
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
  const required=inputs.filter(input=>input.required && !input.disabled);
  const filled=inputs.filter(input=>!input.disabled && input.files.length);
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
  const missing = inputs.filter(input => input.required && !input.disabled && !input.files.length);
  const hasFiles = inputs.some(input => !input.disabled && input.files.length);
  if (!hasFiles || missing.length || !form.checkValidity()) {
    setProcessStage("upload", "Aguardando arquivos", missing.length
      ? "Complete os arquivos obrigatórios para mostrar a prévia automaticamente."
      : "A prévia aparece automaticamente após selecionar os arquivos.");
    return;
  }
  try { readPeriod("#processStart","#processEnd"); }
  catch (error) {
    setProcessStage("error", "Confira o período", error.message);
    return;
  }
  const fileCount = inputs.reduce((count,input) => count + (input.disabled ? 0 : input.files.length),0);
  if (fileCount > 1 || workflow === "advanced") {
    setProcessStage("upload", `${fileCount} arquivo(s) prontos`, "Termine de anexar os documentos e clique em Gerar prévia para processar o lote uma única vez.");
    return;
  }
  setProcessStage("upload", "Preparando prévia automática", "Os arquivos estão prontos. A prévia será atualizada em instantes.");
  autoPreviewTimer = setTimeout(() => form.requestSubmit(processButton), 800);
}
form.addEventListener("change", scheduleAutomaticPreview);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selected || organizerRunning) return;
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
      for (const input of $$("[data-option]")) options[input.dataset.option] = input.dataset.manualDate ? dateApiValue(input) : input.value;
      const standardPeriod = readPeriod("#processStart","#processEnd");
      options.data_inicial = standardPeriod.data_inicial;
      options.data_final = standardPeriod.data_final;
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
      data.append("options_json",JSON.stringify({data_inicial:dateApiValue($("#processStart")),data_final:dateApiValue($("#processEnd"))}));
      endpoint = `${API()}/api/v1/modelo-dominio/${selected.codigo}/multi`;
    } else {
      const files = [...fileInput.files];
      if (!files.length) throw new Error("Selecione pelo menos um arquivo.");
      data.append("bank", bankSelect.value);
      data.append("options_json",JSON.stringify({data_inicial:dateApiValue($("#processStart")),data_final:dateApiValue($("#processEnd"))}));
      files.forEach(file => data.append("files", file));
    }

    processMessage.textContent = "";
    organizerRunning = true;
    submitButton.disabled = true;
    submitButton.classList.add("is-loading");
    setProcessStage("processing", "Gerando prévia…");
    $("#workflowPreview").replaceChildren();
    let response = await fetch(endpoint, { method: "POST", body: data, signal:controller.signal, headers:{
      "X-Razync-Preview":["reports","preview"].includes(event.submitter?.dataset.output) ? "0" : "1",
      "X-Razync-Background":workflow === "advanced" && !event.submitter?.dataset.output ? "1" : "0"
    } });
    if (currentVersion !== previewVersion) return;
    response = await RazyncOrganizer.wait(response, {signal:controller.signal, onProgress:status => {
      if (currentVersion !== previewVersion) return;
      const detail = status.current ? `Lendo arquivo ${status.current} de ${status.total}.` : "Seu lote será processado sem reenviar os documentos.";
      setProcessStage("processing", status.state === "queued" ? "Lote na fila…" : status.state === "reconnecting" ? "Reconectando…" : "Organizando arquivos…", detail);
    }});
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
    const prepared = await RazyncResults.workbookPreview(response, {endpoint, snapshot:data,
      signal:controller.signal, filename:`RAZYNC_${companyCode}_MODELO_DOMINIO.xlsx`});
    if (selected?.codigo !== companyCode || currentVersion !== previewVersion) return;
    showWorkflowPreview(prepared.preview);
    const download = document.createElement("button");
    download.type = "button";
    download.textContent = "Baixar Modelo Domínio";
    download.addEventListener("click", async () => {
      download.disabled=true;
      try { await prepared.download(); }
      catch (error) { if (error.name !== "AbortError" && selected?.codigo === companyCode) processMessage.textContent=error.message; }
      finally { download.disabled=false; }
    });
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
      organizerRunning = false;
      submitButton.disabled = false;
      submitButton.classList.remove("is-loading");
    }
  }
});

learnForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = learnForm.querySelector('[type="submit"]');
  if (button.disabled) return;
  const files = [...$("#learnFiles").files];
  if (!files.length) return $("#learnMessage").textContent = "Selecione pelo menos um arquivo revisado.";
  const company = selected.codigo;
  const current = () => selected?.codigo === company;
  const data = new FormData();
  files.forEach(file => data.append("files", file));
  button.disabled = true;
  $("#learnMessage").textContent = "Aprendendo padrões…";
  try {
    const response = await fetch(`${API()}/api/v1/base-inteligente/${company}/aprender`, {method:"POST", body:data});
    if (!response.ok) throw new Error(await responseError(response));
    const result = await response.json();
    if (current()) {
      const errors = (result.errors || []).join("; ");
      $("#learnMessage").textContent = `${result.learned} padrão(ões) processado(s).${errors ? ` Alguns arquivos não foram importados: ${errors}` : ""}`;
      refreshBaseStats(result);
      window.refreshSavedBasePeriods?.();
    }
  } catch (error) {
    if (current()) $("#learnMessage").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

let eletro242ClassificationMode = "consolidada";
const ELETRO_242_MODE_HELP = {
  consolidada: "Classifica todas as abas bancárias. Pagamentos usam DÉBITO e recebimentos usam CRÉDITO; contas já classificadas são preservadas.",
  despesa: "Somente as abas bancárias são classificadas. Na Despesa, apenas DÉBITO 0 ou vazio pode ser substituído; a aba Principal é preservada.",
  fornecedor: "Somente as abas bancárias são classificadas. No Fornecedor, apenas DÉBITO 166, 0 ou vazio pode ser substituído; a aba Principal é preservada.",
  recebido: "Somente as abas bancárias são classificadas. No Recebido, apenas CRÉDITO 166, 0, 14, 16 ou vazio pode ser substituído; a aba Principal é preservada.",
  francesinhas: "Classifica a planilha gerada por Francesinhas, preenchendo somente CRÉDITO vazio e mantendo 508 e 509 separados."
};

function setEletro242ClassificationMode(mode) {
  if (!ELETRO_242_MODE_HELP[mode]) mode = "consolidada";
  eletro242ClassificationMode = mode;
  document.querySelectorAll("#eletro242Modes [data-eletro242-mode]").forEach(button => {
    const active = button.dataset.eletro242Mode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const help = $("#eletro242ModeHelp");
  if (help) help.textContent = ELETRO_242_MODE_HELP[mode];
}

document.querySelectorAll("#eletro242Modes [data-eletro242-mode]").forEach(button => {
  button.addEventListener("click", () => {
    if (eletro242ClassificationMode !== button.dataset.eletro242Mode) {
      cancelClassificationPreview();
      $("#classifyMessage").textContent = "";
    }
    setEletro242ClassificationMode(button.dataset.eletro242Mode);
  });
});

let classificationController;

function renderClassificationCoverage(coverage) {
  const panel = $("#classificationCoverage");
  if (!panel) return;
  const total = Number(coverage?.total);
  if (!coverage || !Number.isInteger(total) || total < 0) {
    panel.hidden = true;
    return;
  }
  const count = name => {
    const value = Number(coverage[name]);
    return Number.isInteger(value) ? Math.max(0, Math.min(total, value)) : 0;
  };
  const done = count("classificadas");
  const pending = total - done;
  const percent = total ? Math.round(done / total * 1000) / 10 : 0;
  const formatNumber = value => value.toLocaleString("pt-BR");
  const formatPercent = value => value.toLocaleString("pt-BR", {
    minimumFractionDigits: 1, maximumFractionDigits: 1
  });
  $("#classificationCoveragePercent").textContent = total ? `${formatPercent(percent)}%` : "—";
  $("#classificationCoverageFraction").textContent = `${formatNumber(done)} de ${formatNumber(total)} linhas`;
  $("#classificationCoverageNew").textContent = formatNumber(count("novas_classificadas"));
  $("#classificationCoveragePrevious").textContent = formatNumber(count("ja_classificadas"));
  $("#classificationCoveragePending").textContent = formatNumber(pending);
  $("#classificationCoverageFill").style.width = `${percent}%`;
  const bar = $("#classificationCoverageProgress");
  if (total) {
    bar.setAttribute("aria-valuenow", String(percent));
  } else {
    bar.removeAttribute("aria-valuenow");
  }
  panel.hidden = false;
}

function cancelClassificationPreview() {
  classificationController?.abort();
  $("#classificationPreview").replaceChildren();
  $("#classificationCoverage").hidden = true;
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
  [...$("#classifyFile").files].forEach(file => data.append("file", file));
  const classifyOptions = {};
  if (Number(selected.codigo) === 242) {
    classifyOptions.origem_242 = eletro242ClassificationMode;
  } else if (Number(selected.codigo) === 1408) {
    classifyOptions.modo_consolidado = true;
  }
  data.append("options_json", JSON.stringify(classifyOptions));
  $("#classifyMessage").textContent = "Classificando…";
  try {
    const response = await fetch(`${API()}/api/v1/base-inteligente/${companyCode}/classificar`, {method:"POST", body:data, signal:controller.signal, headers:{"X-Razync-Preview":"1"}});
    if (!response.ok) throw new Error(await responseError(response));
    const raw = response.headers.get("x-razync-summary");
    const summary = raw ? JSON.parse(raw) : {};
    const prepared = await RazyncResults.workbookPreview(response, {
      endpoint:`${API()}/api/v1/base-inteligente/${companyCode}/classificar`, snapshot:data,
      signal:controller.signal, filename:`RAZYNC_${companyCode}_CLASSIFICADO.xlsx`});
    const result = prepared.preview;
    if (controller.signal.aborted || selected?.codigo !== companyCode) return;
    showWorkflowPreview(result,target);
    renderClassificationCoverage(summary.cobertura);
    const download = document.createElement("button");download.type="button";download.className="preview-download";
    download.textContent="Baixar Excel classificado";
    download.addEventListener("click", async () => {
      download.disabled=true;
      try { await prepared.download(); }
      catch (error) { if (error.name !== "AbortError" && selected?.codigo === companyCode) $("#classifyMessage").textContent=error.message; }
      finally { download.disabled=false; }
    });
    target.querySelector(".preview-primary-actions").append(download);
    $("#classifyMessage").textContent = "Classificação concluída. Confira as linhas classificadas, as pendências e a prévia antes de baixar.";
  } catch (error) {
    if (controller.signal.aborted || selected?.codigo !== companyCode) return;
    $("#classifyMessage").textContent = error.message;
  } finally {
    if (classificationController === controller) button.disabled = false;
  }
});

function reconcileSelectionState() {
  const banks = selectedReconcileBanks();
  const missing = [];
  const files = [];
  const fileBanks = [];

  banks.forEach(bank => {
    const input = document.querySelector(`#reconcileStatementFields [data-reconcile-bank="${bank}"]`);
    const bankFiles = input ? [...input.files] : [];
    if (!bankFiles.length) {
      missing.push(bank);
      return;
    }
    bankFiles.forEach(file => {
      files.push(file);
      fileBanks.push(bank);
    });
  });

  return {banks,files,fileBanks,missing};
}

function buildSingleReconcileData(bank) {
  const data = new FormData();
  data.append("bank",bank);
  [...$("#modelFile").files].forEach(file => data.append("model_file",file));
  data.append("options_json",JSON.stringify({
    data_inicial:dateApiValue($("#reconcileStart")),
    data_final:dateApiValue($("#reconcileEnd"))
  }));
  const input = document.querySelector(`#reconcileStatementFields [data-reconcile-bank="${bank}"]`);
  [...(input?.files || [])].forEach(file => data.append("statement_files",file));
  return data;
}

function buildReconcileData() {
  const state = reconcileSelectionState();
  const data = new FormData();
  data.append("banks_json",JSON.stringify(state.banks));
  data.append("file_banks_json",JSON.stringify(state.fileBanks));
  [...$("#modelFile").files].forEach(file => data.append("model_file",file));
  data.append("options_json",JSON.stringify({
    data_inicial:dateApiValue($("#reconcileStart")),
    data_final:dateApiValue($("#reconcileEnd"))
  }));
  state.files.forEach(file => data.append("files",file));
  return data;
}

let reconcilePreviewTimer;
let reconcilePreviewController;

function cancelReconcilePreview() {
  clearTimeout(reconcilePreviewTimer);
  reconcilePreviewController?.abort();
  clearToolResult("#reconcileResult");
  $("#reconcileMessage").textContent = "";
}

function scheduleReconcilePreview() {
  cancelReconcilePreview();

  const model = $("#modelFile").files[0];
  const state = reconcileSelectionState();

  if (!model || !state.banks.length) {
    $("#reconcileResult").hidden = true;
    $("#reconcileResult").replaceChildren();
    $("#reconcileMessage").textContent = "";
    return;
  }

  if (!reconcileForm.checkValidity()) {
    $("#reconcileMessage").textContent = "Confira as datas: use DD/MM/AAAA.";
    return;
  }
  if (state.missing.length) {
    $("#reconcileResult").hidden = true;
    $("#reconcileResult").replaceChildren();
    $("#reconcileMessage").textContent = "Envie o extrato de: " + state.missing.map(bankName).join(", ") + ".";
    return;
  }

  $("#reconcileMessage").textContent = state.banks.length > 1
    ? `Arquivos prontos. Conferindo ${state.banks.length} bancos…`
    : "Arquivos prontos. Montando conferência diária…";
  const companyCode = selected?.codigo;
  reconcilePreviewTimer = setTimeout(() => {
    if (companyCode !== undefined && selected?.codigo === companyCode) reconcileForm.requestSubmit();
  },550);
}

reconcileForm.addEventListener("change",scheduleReconcilePreview);

reconcileForm.addEventListener("submit",async event => {
  event.preventDefault();
  clearTimeout(reconcilePreviewTimer);
  cancelReconcilePreview();

  const controller = new AbortController();
  reconcilePreviewController = controller;
  const companyCode = selected?.codigo;
  if (companyCode === undefined) return;
  const isCurrent = () => !controller.signal.aborted && selected?.codigo === companyCode;
  const model = $("#modelFile").files[0];
  const state = reconcileSelectionState();

  if (!model) return $("#reconcileMessage").textContent = "Envie o Modelo Domínio.";
  if (!state.banks.length) return $("#reconcileMessage").textContent = "Selecione pelo menos um banco.";
  if (state.missing.length) {
    return $("#reconcileMessage").textContent = "Envie o extrato de: " + state.missing.map(bankName).join(", ") + ".";
  }

  $("#reconcileMessage").textContent = state.banks.length > 1
    ? `Conferindo saldos de ${state.banks.length} bancos por dia…`
    : "Conferindo saldos por dia…";

  // Keep exactly the same documents, banks and period for preview and download.
  const snapshot = state.banks.length === 1 ? buildSingleReconcileData(state.banks[0]) : buildReconcileData();
  try {
    const previewEndpoint = state.banks.length === 1
      ? `${API()}/api/v1/conferencia-extrato/${companyCode}/preview`
      : `${API()}/api/v1/conferencia-extrato/${companyCode}/multi/preview`;
    const previewBody = snapshot;
    const response = await fetch(previewEndpoint,{
      method:"POST",body:previewBody,signal:controller.signal,headers:{"X-Razync-Reuse":"1"}
    });
    if (!response.ok) throw new Error(await responseError(response));
    const result = await response.json();
    if (!isCurrent()) return;

    renderDailyReconciliation($("#reconcileResult"),{
      rows:result.rows || [],
      movements:result.statement_movements || [],
      kind:"modelo",
      download:async () => {
        if (!isCurrent()) return;
        const reportEndpoint = state.banks.length === 1
          ? `${API()}/api/v1/conferencia-extrato/${companyCode}`
          : `${API()}/api/v1/conferencia-extrato/${companyCode}/multi`;
        const report = globalThis.RazyncResults
          ? await RazyncResults.downloadResponse(result.report_token, reportEndpoint, {method:"POST",body:snapshot,signal:controller.signal})
          : await fetch(reportEndpoint,{method:"POST",body:snapshot,signal:controller.signal});
        if (!report.ok) throw new Error(await responseError(report));
        if (!isCurrent()) return;
        await downloadBlob(report,`RAZYNC_${companyCode}_CONFERENCIA_EXTRATO.xlsx`);
      }
    });

    if (globalThis.RazyncAssets) {
      try { await RazyncAssets.load("investments"); }
      catch (error) { $("#reconcileMessage").textContent=error.message; return; }
    }
    if (!isCurrent()) return;
    globalThis.RazyncInvestments?.mount({
      target:$("#reconcileResult"),company:companyCode,
      banks:state.banks.map(bank=>({code:bank,label:bankName(bank),account:selected?.capabilities?.banks?.[bank] || ""})),
      snapshot:buildReconcileData(),summary:result.summary,rows:result.rows || [],
      balances:row=>reconciliationBalances(row,"modelo"),isCurrent,signal:controller.signal,
      api:API(),download:downloadBlob,responseError
    });

    const errors = result.summary?.errors || [];
    const divergent = (result.rows || []).filter(row => !reconciliationBalances(row,"modelo").ok).length;
    if (errors.length) {
      $("#reconcileMessage").textContent = `Conferência parcial: ${errors.length} banco(s) precisam de atenção e ${divergent} linha(s) diária(s) estão divergentes.`;
    } else if (divergent) {
      $("#reconcileMessage").textContent = `${divergent} banco/dia com divergência. Use os filtros para revisar.`;
    } else {
      $("#reconcileMessage").textContent = state.banks.length > 1
        ? "Todos os bancos selecionados estão batendo."
        : "Todos os dias analisados estão batendo.";
    }
  } catch (error) {
    if (error.name === "AbortError" || !isCurrent()) return;
    $("#reconcileResult").hidden = true;
    $("#reconcileResult").replaceChildren();
    $("#reconcileMessage").textContent = error.message;
  }
});

function filterCompanies() {
  const query = search.value.trim();
  const regime = $('#regimeFilter').value;
  const current = companies.filter(companyBelongsToPortfolio);
  const clear = $('#companySearchClear');if(clear)clear.hidden=!query;
  const reset = $('#companyReset');if(reset)reset.hidden=!(query || regime || companyFilter!=='all');
  render(RazyncDirectory.select(current,{query,regime,filter:companyFilter,sort:$('#companySort')?.value || 'code'}));
}
function resetCompanyFilters() {
  search.value='';$('#regimeFilter').value='';companyFilter='all';
  $$('.company-filter').forEach(button=>{
    const active=button.dataset.filter==='all';button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));
  });
  filterCompanies();
}
search.addEventListener("input", filterCompanies);
$('#regimeFilter').addEventListener('change',filterCompanies);
$('#companySort')?.addEventListener('change',filterCompanies);
$('#companySearchClear')?.addEventListener('click',()=>{search.value='';filterCompanies();search.focus();});
$('#companyReset')?.addEventListener('click',resetCompanyFilters);
search.addEventListener('keydown',event=>{
  if(event.key==='Escape' && !event.isComposing && search.value){event.preventDefault();search.value='';filterCompanies();}
});
function setCompanyView(view) {
  const value=view==='list'?'list':'cards';grid.dataset.view=value;
  $$('[data-company-view]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.companyView===value)));
  try {localStorage.setItem('razync:directory-view',value);} catch { /* Optional preference. */ }
}
let initialCompanyView='cards';
try {initialCompanyView=localStorage.getItem('razync:directory-view') || 'cards';} catch { /* Optional preference. */ }
setCompanyView(initialCompanyView);
$$('[data-company-view]').forEach(button=>button.addEventListener('click',()=>setCompanyView(button.dataset.companyView)));
$$('.company-filter').forEach(button=>button.addEventListener('click',()=>{
  companyFilter=button.dataset.filter;
  $$('.company-filter').forEach(item=>{item.classList.toggle('active',item===button);item.setAttribute('aria-pressed',String(item===button));});
  filterCompanies();
}));
backButton.addEventListener("click", closeCompany);

async function fetchAfterWake(url, {onRetry} = {}) {
  // Railway em repouso pode demorar a responder. Limite cada tentativa
  // para nunca deixar a interface indefinidamente em "carregando".
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const signal = typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
        ? AbortSignal.timeout(14000) : undefined;
      const response = await fetch(url, {signal});
      if (response.ok || ![502, 503, 504].includes(response.status) || attempt === 3) {
        return response;
      }
    } catch (error) {
      if (attempt === 3) throw error;
    }
    if (onRetry) onRetry(attempt + 1);
    await new Promise(resolve => setTimeout(resolve, [1500, 3000, 5000][attempt]));
  }
}

async function loadCompanies() {
  // O catálogo já consultado permite abrir a carteira enquanto a API acorda.
  // A resposta do servidor continua sendo a fonte das atualizações.
  const cacheKey = `razync:companies:v1:${API()}`;
  const validCatalog = items => Array.isArray(items) && items.length > 0 &&
    items.every(item => item && Number.isFinite(Number(item.codigo)) && typeof item.nome === "string");
  function applyCatalog(items) {
    if (!validCatalog(items)) throw new Error("Catálogo inválido");
    if (JSON.stringify(companies) === JSON.stringify(items)) return;
    companies = items;
    renderPortfolios();
    populateTaskCompanies(companies);
    if (activePortfolio) filterCompanies();
  }
  try {
    const cached = JSON.parse(localStorage.getItem(cacheKey) || "null");
    if (validCatalog(cached)) applyCatalog(cached);
  } catch { /* Armazenamento indisponível ou cache antigo: consultar normalmente. */ }
  try {
    const response = await fetchAfterWake(`${API()}/api/v1/companies`);
    if (!response.ok) throw new Error();
    const items = await response.json();
    applyCatalog(items);
    try { localStorage.setItem(cacheKey, JSON.stringify(items)); } catch { /* Cache opcional. */ }
  } catch {
    if (companies.length) return;
    try {
      const response = await fetch("./assets/data/companies.json");
      if (!response.ok) throw new Error();
      applyCatalog(await response.json());
    } catch {
      const message = document.querySelector("#portfolioList [role=status]");
      if (message) message.textContent = "Não foi possível carregar as carteiras. Recarregue a página para tentar novamente.";
    }
  }
}

function setApiConnectionState(state, detail = "") {
  const messages = {
    checking: ["Conectando…", "Verificando a conexão com o servidor."],
    waking: ["Iniciando servidor…", "O servidor estava em repouso. A conexão está sendo restabelecida. Você pode consultar as empresas enquanto isso."],
    online: ["Sistema online", "Servidor conectado. Clique para verificar novamente."],
    offline: ["Sem conexão · tentar", "Não foi possível conectar ao servidor. Clique aqui para tentar novamente."],
    unconfigured: ["API não configurada", "É necessário configurar o endereço do servidor."],
  };
  const [label, hint] = messages[state] || messages.offline;
  const text = apiStatus.querySelector(".connection-label");
  if (text) text.textContent = detail || label;
  apiStatus.dataset.connection = state;
  apiStatus.classList.toggle("online", state === "online");
  apiStatus.title = hint;
  apiStatus.setAttribute("aria-label", (detail || label) + ". " + hint);
  apiStatus.setAttribute("aria-busy", String(state === "checking" || state === "waking"));
}

let apiCheckPending = null;
async function checkApi() {
  if (apiCheckPending) return apiCheckPending;
  if (!API()) { setApiConnectionState("unconfigured"); return Promise.resolve(); }
  setApiConnectionState("checking");
  apiCheckPending = (async () => {
    const wakeNotice = setTimeout(() => setApiConnectionState("waking"), 1800);
    try {
      const response = await fetchAfterWake(`${API()}/health`, {
        onRetry: () => setApiConnectionState("waking"),
      });
      if (!response.ok) throw new Error("Healthcheck indisponível");
      clearTimeout(wakeNotice);
      setApiConnectionState("online");
    } catch {
      clearTimeout(wakeNotice);
      setApiConnectionState("offline");
    }
  })().finally(() => { apiCheckPending = null; });
  return apiCheckPending;
}
apiStatus.addEventListener("click", () => {
  checkApi();
  if (!companies.length) loadCompanies();
});

initializeTaskUI();
loadCompanies();
checkApi();
enhanceFileInputs(document);


let navigationVersion = 0;
async function showGlobalView(name) {
  const version = ++navigationVersion;
  if (name === "fiscal" && globalThis.RazyncAssets && !RazyncAssets.isLoaded("fiscal")) {
    const trigger = document.querySelector('.main-nav-btn[data-view="fiscal"]');
    trigger?.setAttribute("aria-busy","true");
    try { await RazyncAssets.load("fiscal"); }
    catch (error) { setApiConnectionState("offline", "Erro ao abrir ferramenta"); console.error(error); return; }
    finally { trigger?.removeAttribute("aria-busy"); }
    if (version !== navigationVersion) return;
  }
  closeCompanyToolHelp();
  $("#companyToolHelp").hidden = true;
  cancelReconcilePreview();
  $('#currentSection').textContent = {companies:'Empresas',ledger:'Conciliação com Razão',fiscal:'Conferência Fiscal × Contábil'}[name];
  panel.hidden = true;
  selected = null;
  if (name === "companies") {
    portfolioPicker.hidden = Boolean(activePortfolio);
    workspace.hidden = !activePortfolio;
    $(".hero").hidden = !activePortfolio;
    if (!activePortfolio) renderPortfolios();
  }
  document.querySelectorAll(".global-view").forEach(view => {
    view.classList.toggle("active", view.id === `${name}View`);
  });
  document.querySelectorAll(".main-nav-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
  if (name === "fiscal") {
    renderCompanyToolGuide("fiscal-global");
  }
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

function replaceInputFiles(input, files) {
  const transfer = new DataTransfer();
  files.forEach(file => transfer.items.add(file));
  input.dataset.replacingFiles = "1";
  input.files = transfer.files;
  input.dispatchEvent(new Event("change",{bubbles:true}));
  delete input.dataset.replacingFiles;
}

function removeSelectedFile(input,index) {
  const files = [...input.files];
  if (index < 0 || index >= files.length) return;
  files.splice(index,1);
  replaceInputFiles(input,files);
}

function updateFileSelection(input) {
  const files = [...input.files];
  input.classList.toggle("has-files", files.length > 0);
  input.title = files.length ? files.map(file => file.name).join("\n") : "";

  const shell = input.closest(".file-drop-shell");
  shell?.classList.toggle("has-selection", files.length > 0);
  let selection = shell?.querySelector(":scope > .file-selection");
  if (!selection) {
    selection = document.createElement("div");
    selection.className = "file-selection";
    if (shell) shell.appendChild(selection);
    else input.insertAdjacentElement("afterend", selection);
  }
  selection.replaceChildren();

  if (!files.length) {
    selection.hidden = true;
    return;
  }

  selection.hidden = false;
  const summary = document.createElement("div"); summary.className = "file-selection-summary";
  const quantity = document.createElement("span"); quantity.textContent = `${files.length} arquivo(s)`;
  const total = document.createElement("span"); total.textContent = humanFileSize(files.reduce((sum, file) => sum + file.size, 0));
  summary.append(quantity, total); selection.append(summary);
  files.forEach((file,index) => {
    const item = document.createElement("span");
    item.className = "file-selection-item";

    const icon = document.createElement("i");
    icon.setAttribute("aria-hidden","true");

    const text = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = file.name;
    name.title = file.name;

    const meta = document.createElement("small");
    meta.textContent = `${humanFileSize(file.size)} · ${selectedFileBankLabel(input)}`;
    text.append(name,meta);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "file-selection-remove";
    remove.setAttribute("aria-label",`Remover ${file.name}`);
    remove.title = "Remover arquivo";
    remove.innerHTML = '<span aria-hidden="true">×</span>';
    remove.addEventListener("click",event => {
      event.preventDefault();
      event.stopPropagation();
      removeSelectedFile(input,index);
    });

    item.append(icon,text,remove);
    selection.appendChild(item);
  });

  if (input.closest("#processForm")) {
    setProcessStage("upload","Arquivos prontos",files.length === 1
      ? "1 arquivo selecionado para processamento."
      : `${files.length} arquivos selecionados para processamento.`);
  }
}

document.addEventListener("change", event => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
  updateFileSelection(input);
});

let ledgerPreviewTimer;
let ledgerPreviewController;

function buildLedgerData() {
  const data = new FormData();
  [...$("#ledgerStatement").files].forEach(file => data.append("extrato", file));
  [...$("#ledgerFile").files].forEach(file => data.append("razao", file));
  const period = ledgerPeriod();
  data.append("data_inicial",period.data_inicial);
  data.append("data_final",period.data_final);
  return data;
}

function ledgerPeriod() {
  const start = String($("#ledgerStart")?.value || "").trim();
  const end = String($("#ledgerEnd")?.value || "").trim();
  if (Boolean(start) !== Boolean(end)) throw new Error("Informe as duas datas do período.");
  if (start && end && end < start) throw new Error("A data final não pode ser anterior à data inicial.");
  return {data_inicial:start,data_final:end};
}

function scheduleLedgerPreview() {
  clearTimeout(ledgerPreviewTimer);
  ledgerPreviewController?.abort();
  const statement = $("#ledgerStatement").files[0];
  const ledger = $("#ledgerFile").files[0];
  const target = $("#ledgerResult");
  clearToolResult("#ledgerResult");
  if (!statement || !ledger) {
    if (target) {
      target.hidden = true;
      target.replaceChildren();
    }
    $("#ledgerMessage").textContent = "";
    return;
  }
  try { ledgerPeriod(); }
  catch (error) { $("#ledgerMessage").textContent = error.message; return; }
  $("#ledgerMessage").textContent = "Arquivos prontos. Montando conciliação diária…";
  ledgerPreviewTimer = setTimeout(() => $("#ledgerForm").requestSubmit(), 550);
}

$("#ledgerForm")?.addEventListener("change", scheduleLedgerPreview);

$("#ledgerForm")?.addEventListener("submit", async event => {
  event.preventDefault();
  clearTimeout(ledgerPreviewTimer);
  ledgerPreviewController?.abort();
  clearToolResult("#ledgerResult");
  const controller = new AbortController();
  ledgerPreviewController = controller;

  const statement = $("#ledgerStatement").files[0];
  const ledger = $("#ledgerFile").files[0];
  const msg = $("#ledgerMessage");
  if (!statement || !ledger) return msg.textContent = "Envie o extrato e o Razão.";

  const snapshot = buildLedgerData();
  msg.textContent = "Conferindo movimentos por dia…";
  try {
    const response = await fetch(`${API()}/api/v1/conciliacao-razao/preview`, {
      method:"POST", body:snapshot, signal:controller.signal,headers:{"X-Razync-Reuse":"1"}
    });
    if (!response.ok) throw new Error(await responseError(response));
    const result = await response.json();
    if (controller.signal.aborted) return;

    renderDailyReconciliation($("#ledgerResult"), {
      rows:result.rows || [],
      kind:"razao",
      download:async () => {
        if (controller.signal.aborted) return;
        const report = globalThis.RazyncResults
          ? await RazyncResults.downloadResponse(result.report_token, `${API()}/api/v1/conciliacao-razao`, {method:"POST",body:snapshot,signal:controller.signal})
          : await fetch(`${API()}/api/v1/conciliacao-razao`, {method:"POST",body:snapshot,signal:controller.signal});
        if (!report.ok) throw new Error(await responseError(report));
        if (controller.signal.aborted) return;
        await downloadBlob(report,"RAZYNC_CONCILIACAO_RAZAO.xlsx");
      }
    });

    const divergent = (result.rows || []).filter(row => !reconciliationBalances(row,"razao").ok).length;
    msg.textContent = divergent
      ? `${divergent} dia(s) com divergência entre Extrato e Razão.`
      : "Todos os dias analisados estão conciliados.";
  } catch (error) {
    if (error.name === "AbortError" || controller.signal.aborted) return;
    $("#ledgerResult").hidden = true;
    $("#ledgerResult").replaceChildren();
    msg.textContent = error.message;
  }
});

function brl(value) {
  return new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(Number(value||0));
}

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
  const period = readPeriod("#taxStart","#taxEnd");
  if (period.data_inicial && period.data_inicial.slice(0,7) !== period.data_final.slice(0,7)) {
    throw new Error("Na Conferência de Impostos, as duas datas precisam estar na mesma competência.");
  }
  data.append("competencia", period.data_inicial ? period.data_inicial.slice(0,7) : "");
  data.append("data_inicial", period.data_inicial);
  data.append("data_final", period.data_final);
  msgElement.textContent = "Conferindo impostos…";
  const response = await fetch(`${API()}/api/v1/conferencia-impostos/${companyCode}`, {method:"POST", body:data});
  if (!response.ok) throw new Error(await responseError(response));
  const raw = response.headers.get("x-razync-summary");
  const summary = raw ? JSON.parse(raw) : {};
  const report = await response.blob();
  return {summary, report};
}
