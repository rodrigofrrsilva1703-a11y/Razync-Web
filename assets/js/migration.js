/* Additional controls use the same company state and original API routes. */
const migratedRenderWorkflow = renderWorkflow;
const migratedOpenCompany = openCompany;
let reviewPendingRows = [];
let reviewSourceFile = null;

const francesinhasTab = document.createElement("button");
francesinhasTab.type = "button";
francesinhasTab.className = "tool-tab";
francesinhasTab.dataset.tool = "francesinhas";
francesinhasTab.textContent = "Francesinhas";
francesinhasTab.addEventListener("click", () => activateTool("francesinhas"));
$(".tool-tabs").appendChild(francesinhasTab);

renderWorkflow = function(company) {
  migratedRenderWorkflow(company);
  enableMobileDateFields(advancedFields);
  $("#toolDescription").textContent += " A prévia aparece automaticamente quando os arquivos obrigatórios estiverem preenchidos.";
  const companyCode = Number(company.codigo);
  const eletro = [242,1408].includes(companyCode);
  $("#standardPeriod").hidden = companyCode === 1408;
  $("#reportPackage").hidden = company.capabilities?.workflow !== "advanced" || companyCode === 1408;
  $("#reportPackage").textContent = companyCode === 242 ? "Baixar relatórios individuais e consolidado" : "Baixar modelo e conferências";
  $("#previewWorkflow").hidden = true;
  $("#eletro242Classification").hidden = companyCode !== 242;
  $("#eletro1408Classification").hidden = companyCode !== 1408;
  $("#reviewForm").hidden = false;

  const learnLabel = document.querySelector('label[for="learnFiles"]');
  const classifyLabel = document.querySelector('label[for="classifyFile"]');
  if (companyCode === 242) {
    setEletro242ClassificationMode("consolidada");
    $("#learnFiles").accept = ".xls,.xlsx,.zip";
    if (learnLabel) learnLabel.textContent = "Planilhas já classificadas da 242";
    if (classifyLabel) classifyLabel.textContent = "Planilha Consolidada para classificar";
  } else if (companyCode === 1408) {
    $("#learnFiles").accept = ".xls,.xlsx,.zip";
    if (learnLabel) learnLabel.textContent = "Planilhas já classificadas da 1408";
    if (classifyLabel) classifyLabel.textContent = "Modelo Domínio consolidado para classificar";
  } else {
    $("#learnFiles").accept = ".xls,.xlsx,.zip,.csv,.json";
    if (learnLabel) learnLabel.textContent = "Arquivos revisados";
    if (classifyLabel) classifyLabel.textContent = "Modelo Domínio para classificar";
  }

  francesinhasTab.hidden = companyCode !== 242;
  updateUploadProgress();
  $("#workflowPreview").replaceChildren();
  $("#reviewRows").replaceChildren();
  $("#applyReview").hidden = true;
  reviewPendingRows = [];
  reviewSourceFile = null;
};

openCompany = function(company) {
  cancelAutomaticPreview();
  cancelClassificationPreview();
  // File inputs and their visual state must not carry documents across companies.
  document.querySelectorAll("#companyPanel form").forEach(f => f.reset());
  document.querySelectorAll("#companyPanel .file-selection").forEach(el => el.remove());
  document.querySelectorAll("#companyPanel input[type='file']").forEach(input => {
    input.classList.remove("has-files");
    input.title = "";
  });
  document.querySelectorAll("#companyPanel .file-drop-shell").forEach(shell => {
    shell.classList.remove("is-dragging");
  });
  $("#workflowPreview").replaceChildren();
  $("#adminAccess").value = "";
  $("#baseManagementMessage").textContent = "";
  $("#reviewMessage").textContent = "";
  migratedOpenCompany(company);
};

function adminHeaders() {
  const token = $("#adminAccess").value;
  if (!token) throw new Error("Informe a chave em Acesso administrativo, acima das ferramentas.");
  return {Authorization: `Bearer ${token}`};
}

function previewLabel(value) {
  return String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
}

function previewValue(label, value) {
  if (value === null || value === undefined || value === "") return "";
  const normalized = previewLabel(label);
  if (normalized === "VALOR" && typeof value === "number") {
    return new Intl.NumberFormat("pt-BR", {minimumFractionDigits:2, maximumFractionDigits:2}).format(value);
  }
  return String(value);
}

function tableFor(headers, rows) {
  const table = document.createElement("table");
  table.className = "dataframe-preview razync-table";
  const head = document.createElement("thead");
  const line = document.createElement("tr");
  headers.forEach(label => {
    const th = document.createElement("th");
    th.textContent = label;
    const normalized = previewLabel(label);
    if (["VALOR","DEBITO","CREDITO"].includes(normalized)) th.classList.add("numeric");
    line.appendChild(th);
  });
  head.appendChild(line);
  table.appendChild(head);

  const body = document.createElement("tbody");
  rows.forEach(row => {
    const tr = document.createElement("tr");
    row.forEach((value, index) => {
      const td = document.createElement("td");
      const label = headers[index] || "";
      td.textContent = previewValue(label, value);
      const normalized = previewLabel(label);
      if (["VALOR","DEBITO","CREDITO"].includes(normalized)) td.classList.add("numeric");
      if (normalized === "HISTORICO") td.classList.add("history-cell");
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  table.appendChild(body);
  return table;
}

function fitMetricValue(element, value) {
  const text = String(value ?? "");
  element.classList.remove("value-compact","value-xcompact");
  if (text.length >= 22) element.classList.add("value-xcompact");
  else if (text.length >= 16) element.classList.add("value-compact");
  element.title = text;
}

function metricChip(label, value) {
  const item = document.createElement("span");
  item.className = "preview-metric";
  const small = document.createElement("small");
  small.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  fitMetricValue(strong,value);
  item.append(small, strong);
  return item;
}

function showWorkflowPreview(data, target = $("#workflowPreview")) {
  target.replaceChildren();

  const sheets = data.sheets || [];
  const diagnostics = data.diagnostics || [];
  const money = value => new Intl.NumberFormat("pt-BR",{
    style:"currency",currency:"BRL"
  }).format(Number(value || 0));

  const totalCount = sheets.reduce((sum, sheet) => sum + Number(sheet.count || 0), 0);
  const totalEntradas = sheets.reduce((sum, sheet) => sum + Number(sheet.entradas || 0), 0);
  const totalSaidas = sheets.reduce((sum, sheet) => sum + Number(sheet.saidas || 0), 0);

  const command = document.createElement("div");
  command.className = "preview-commandbar";
  const commandInfo = document.createElement("div");
  commandInfo.className = "preview-command-info";
  const ready = document.createElement("span");
  ready.className = "preview-ready-dot";
  ready.setAttribute("aria-hidden","true");
  const commandText = document.createElement("div");
  const commandTitle = document.createElement("strong");
  commandTitle.textContent = "Prévia pronta para conferência";
  const commandMeta = document.createElement("small");
  commandMeta.textContent = `${totalCount} lançamento(s) em ${sheets.length} aba(s)`;
  commandText.append(commandTitle, commandMeta);
  commandInfo.append(ready, commandText);
  const primaryActions = document.createElement("div");
  primaryActions.className = "preview-primary-actions";
  command.append(commandInfo, primaryActions);
  target.appendChild(command);

  const summaryGrid = document.createElement("div");
  summaryGrid.className = "preview-summary-grid";
  [
    ["Lançamentos", totalCount.toLocaleString("pt-BR"), "summary-icon summary-icon-rows"],
    ["Entradas", money(totalEntradas), "summary-icon summary-icon-in"],
    ["Saídas", money(totalSaidas), "summary-icon summary-icon-out"],
    ["Abas / bancos", String(sheets.length), "summary-icon summary-icon-sheets"],
  ].forEach(([label,value,iconClass]) => {
    const card = document.createElement("div");
    card.className = "preview-summary-item";
    const icon = document.createElement("span");
    icon.className = iconClass;
    icon.setAttribute("aria-hidden","true");
    const content = document.createElement("div");
    const small = document.createElement("small");
    small.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    fitMetricValue(strong,value);
    content.append(small,strong);
    card.append(icon,content);
    summaryGrid.appendChild(card);
  });
  target.appendChild(summaryGrid);

  const intro = document.createElement("div");
  intro.className = "preview-intro";
  const introText = document.createElement("div");
  const eyebrow = document.createElement("span");
  eyebrow.className = "preview-eyebrow";
  eyebrow.textContent = "LANÇAMENTOS PROCESSADOS";
  const heading = document.createElement("h3");
  heading.textContent = "Confira o Modelo Domínio antes de baixar";
  const description = document.createElement("p");
  description.textContent = "Revise datas, valores, contas e históricos. Você pode filtrar os lançamentos dentro de cada tabela.";
  introText.append(eyebrow, heading, description);
  intro.appendChild(introText);
  target.appendChild(intro);

  const sheetBlocks = [];
  const pendingCount = sheets.reduce((sum, sheet) => sum + (sheet.rows || []).filter(row => previewRowIssues(sheet.columns || [], row).length).length, 0);
  if (pendingCount) {
    const notice = document.createElement("div"); notice.className = "preview-pending-summary";
    const text = document.createElement("span"); text.textContent = `${pendingCount} linha(s) da prévia precisam de revisão: confira as datas.`;
    const onlyPending = document.createElement("button"); onlyPending.type = "button"; onlyPending.textContent = "Ver apenas pendências";
    onlyPending.addEventListener("click", () => {
      target.querySelectorAll(".preview-sheet").forEach(block => block.hidden = false);
      target.querySelectorAll(".preview-sheet-switcher button").forEach(button => button.classList.toggle("active", button.dataset.sheetIndex === "-1"));
      target.querySelectorAll(".preview-table-tools input").forEach(input => input.value = "");
      target.querySelectorAll(".preview-table-tools select").forEach(select => { select.value = "pending"; select.dispatchEvent(new Event("change")); });
      target.querySelector(".preview-table-tools")?.scrollIntoView({behavior:"smooth", block:"center"});
    });
    notice.append(text, onlyPending); target.append(notice);
  }

  if (sheets.length > 1) {
    const switcher = document.createElement("div");
    switcher.className = "preview-sheet-switcher";
    const switcherLabel = document.createElement("span");
    switcherLabel.textContent = "Visualizar";
    switcher.appendChild(switcherLabel);

    const makeButton = (label, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.dataset.sheetIndex = String(index);
      if (index === -1) button.classList.add("active");
      button.addEventListener("click", () => {
        switcher.querySelectorAll("button").forEach(item => item.classList.toggle("active", item === button));
        sheetBlocks.forEach((block, blockIndex) => {
          block.hidden = index !== -1 && blockIndex !== index;
        });
      });
      return button;
    };

    switcher.appendChild(makeButton("Todas", -1));
    sheets.forEach((sheet,index) => switcher.appendChild(makeButton(sheet.name,index)));
    target.appendChild(switcher);
  }

  sheets.forEach((sheet, sheetIndex) => {
    const block = document.createElement("section");
    block.className = "preview-sheet";
    block.dataset.previewSheetIndex = String(sheetIndex);
    sheetBlocks.push(block);

    const header = document.createElement("div");
    header.className = "preview-sheet-head";
    const titleBox = document.createElement("div");
    const badge = document.createElement("span");
    badge.className = "preview-sheet-badge";
    badge.textContent = String(sheetIndex + 1).padStart(2,"0");
    const titleText = document.createElement("div");
    const title = document.createElement("h4");
    title.textContent = sheet.name;
    const subtitle = document.createElement("span");
    subtitle.textContent = `${sheet.count} lançamento(s)`;
    titleText.append(title, subtitle);
    titleBox.className = "preview-sheet-title";
    titleBox.append(badge,titleText);

    const metrics = document.createElement("div");
    metrics.className = "preview-metrics";
    metrics.append(
      metricChip("Entradas", money(sheet.entradas)),
      metricChip("Saídas", money(sheet.saidas))
    );

    header.append(titleBox, metrics);
    block.appendChild(header);

    const rows = sheet.rows || [];
    const table = tableFor(sheet.columns || [], rows);

    if (rows.length) {
      const tools = document.createElement("div"); tools.className = "preview-table-tools";
      const search = document.createElement("input"); search.type = "search";
      search.placeholder = "Buscar data, histórico ou conta";
      search.setAttribute("aria-label", `Filtrar lançamentos de ${sheet.name}`);
      const kind = document.createElement("select"); kind.setAttribute("aria-label", `Tipo de lançamento de ${sheet.name}`);
      [["all","Todos"],["in","Entradas"],["out","Saídas"],["pending","Datas inválidas"]].forEach(([value,label])=>{
        const option=document.createElement("option");option.value=value;option.textContent=label;kind.append(option);
      });
      const visible = document.createElement("span");
      const columns = (sheet.columns || []).map(previewLabel);
      const amountIndex = columns.indexOf("VALOR");
      const issues = rows.map(row => previewRowIssues(sheet.columns || [], row));
      const needsReview = row => previewRowIssues(sheet.columns || [], row).length > 0;
      [...table.tBodies[0].rows].forEach((row,index)=>{
        if (issues[index].length) {
          row.classList.add("accounts-pending"); row.title = issues[index].join(" · ");
          const badge = document.createElement("small"); badge.className = "preview-row-warning";
          badge.textContent = issues[index].join(" · "); row.cells[0]?.append(badge);
        }
      });
      const applyFilter = () => {
        const query=previewLabel(search.value); let shown=0;
        [...table.tBodies[0].rows].forEach((row,index)=>{
          const amount=Number(rows[index][amountIndex]);
          const matchType=kind.value==="all" || (kind.value==="in" && amount>0) || (kind.value==="out" && amount<0) || (kind.value==="pending" && needsReview(rows[index]));
          row.hidden = !matchType || (query && !previewLabel(row.textContent).includes(query));
          if(!row.hidden)shown++;
        });
        visible.textContent=`${shown} de ${rows.length} linhas da prévia`;
      };
      search.addEventListener("input",applyFilter);kind.addEventListener("change",applyFilter);
      applyFilter(); tools.append(search,kind,visible);block.append(tools);
    }

    const scroll = document.createElement("div");
    scroll.className = "preview-table-scroll";
    scroll.appendChild(table);
    block.appendChild(scroll);
    target.appendChild(block);
  });

  if (diagnostics.length) {
    const details = document.createElement("details");
    details.className = "preview-diagnostics";
    const summary = document.createElement("summary");
    const summaryText = document.createElement("span");
    summaryText.textContent = "Conferências e diagnósticos";
    const counter = document.createElement("b");
    counter.textContent = diagnostics.reduce((sum,item)=>sum + Number(item.count || 0),0);
    summary.append(summaryText,counter);
    details.appendChild(summary);

    diagnostics.forEach(sheet => {
      const block = document.createElement("div");
      block.className = "diagnostic-block";
      const title = document.createElement("h4");
      title.textContent = `${sheet.name} · ${sheet.count} registro(s)`;
      const scroll = document.createElement("div");
      scroll.className = "preview-table-scroll";
      scroll.appendChild(tableFor(sheet.columns || [], sheet.rows || []));
      block.append(title, scroll);
      details.appendChild(block);
    });
    target.appendChild(details);
  }

  const note = document.createElement("p");
  note.className = "preview-note";
  note.textContent = "A prévia mostra até 500 linhas por aba. O Excel baixado contém todos os lançamentos.";
  target.appendChild(note);
}

$("#francesinhasForm").addEventListener("submit", async event => {
  event.preventDefault(); const code=selected.codigo; const msg=$("#francesinhasMessage");
  const data=new FormData(); [...$("#francesinhasFiles").files].forEach(f=>data.append("files",f));
  try { appendPeriod(data,"#francesinhasStart","#francesinhasEnd"); }
  catch(error) { return msg.textContent=error.message; }
  msg.textContent="Processando francesinhas…";
  try {
    const response=await fetch(`${API()}/api/v1/francesinhas/${code}`,{method:"POST",body:data});
    if(!response.ok) throw new Error(await responseError(response));
    const summary=JSON.parse(response.headers.get("x-razync-summary") || "{}");
    await downloadBlob(response,`ELETRO_FORTE_${code}_FRANCESINHAS.xlsx`);
    msg.textContent=`${summary.lancamentos} liquidações. ${(summary.avisos || []).join(" ")}`;
  } catch(error) {msg.textContent=error.message;}
});

$("#exportBase").addEventListener("click",async()=>{
  const code=selected.codigo; const msg=$("#baseManagementMessage");
  try {const r=await fetch(`${API()}/api/v1/base-inteligente/${code}/exportar`,{headers:adminHeaders()}); if(!r.ok)throw new Error(await responseError(r));await downloadBlob(r,`RAZYNC_${code}_BASE.json`);msg.textContent="Base exportada. Reimporte o JSON no campo Arquivos revisados.";}catch(e){msg.textContent=e.message;}
});
$("#importOriginalBase").addEventListener("click",async()=>{
  const code=selected.codigo; const msg=$("#baseManagementMessage");msg.textContent="Copiando padrões da base original…";
  try {const r=await fetch(`${API()}/api/v1/base-inteligente/${code}/importar-original`,{method:"POST",headers:adminHeaders()});if(!r.ok)throw new Error(await responseError(r));const result=await r.json();msg.textContent=`${result.learned} padrão(ões) copiado(s).`;refreshBaseStats();}catch(e){msg.textContent=e.message;}
});

window.prepareIntelligentReview = async function(file, code = selected?.codigo) {
  const msg=$("#reviewMessage");
  if (!file || !code) return;
  reviewSourceFile=file;
  const sourceFile=reviewSourceFile;
  const data=new FormData();data.append("file",reviewSourceFile);
  msg.textContent="Listando pendências…";
  try {
    const r=await fetch(`${API()}/api/v1/base-inteligente/${code}/pendencias`,{method:"POST",body:data});
    if(!r.ok)throw new Error(await responseError(r));
    const result=await r.json();
    if(Number(selected?.codigo)!==Number(code) || reviewSourceFile!==sourceFile)return;
    reviewPendingRows=result.pendencias;
    const table=tableFor(["Banco","Data","Valor","Histórico","Classificar em","Conta da contrapartida"],reviewPendingRows.map(row=>[row.Banco,row.Data,row.Valor,row["Histórico"],row["Classificar em"],""]));
    [...table.querySelectorAll("tbody tr")].forEach((tr,i)=>{
      const input=document.createElement("input");input.type="text";input.inputMode="numeric";input.setAttribute("aria-label",`Conta da contrapartida do lançamento ${i+1}`);
      input.addEventListener("input",()=>reviewPendingRows[i]["Conta da contrapartida"]=input.value);
      tr.lastElementChild.appendChild(input);
    });
    const scroll = document.createElement("div"); scroll.className = "preview-table-scroll";
    scroll.appendChild(table);
    $("#reviewRows").replaceChildren(scroll);$("#applyReview").hidden=!reviewPendingRows.length;
    msg.textContent=reviewPendingRows.length
      ? `${reviewPendingRows.length} lançamento(s) pendente(s). Confirme as contas abaixo.`
      : "Nenhuma pendência de contrapartida encontrada.";
    $("#reviewForm").scrollIntoView({behavior:"smooth",block:"nearest"});
  }catch(e){msg.textContent=e.message;}
};

$("#reviewForm").addEventListener("submit", async event=>{
  event.preventDefault();
  const file=$("#reviewFile").files[0];
  if(!file)return;
  await window.prepareIntelligentReview(file, selected.codigo);
});
$("#reviewFile").addEventListener("change",()=>{$("#applyReview").hidden=true;reviewSourceFile=null;$("#reviewRows").replaceChildren();});
$("#applyReview").addEventListener("click",async()=>{
  const code=selected.codigo;const msg=$("#reviewMessage");if(!reviewSourceFile)return;
  const revisions=reviewPendingRows.filter(row=>row["Conta da contrapartida"]?.trim());
  if(!revisions.length)return msg.textContent="Informe ao menos uma conta.";
  const data=new FormData();data.append("file",reviewSourceFile);data.append("revisoes_json",JSON.stringify(revisions));data.append("aprender",$("#rememberReview").checked);
  try {const r=await fetch(`${API()}/api/v1/base-inteligente/${code}/revisar`,{method:"POST",body:data});if(!r.ok)throw new Error(await responseError(r));await downloadBlob(r,`RAZYNC_${code}_REVISADO.xlsx`);msg.textContent="Revisão aplicada. Baixe e confira o arquivo.";refreshBaseStats();}catch(e){msg.textContent=e.message;}
});

$("#txtForm").addEventListener("submit",async event=>{
  event.preventDefault();const data=new FormData();data.append("file",$("#txtModel").files[0]);const msg=$("#txtMessage");
  try {appendPeriod(data,"#txtStart","#txtEnd");const r=await fetch(`${API()}/api/v1/modelo-dominio-txt`,{method:"POST",body:data});if(!r.ok)throw new Error(await responseError(r));await downloadBlob(r,"RAZYNC_MODELO_DOMINIO.txt");msg.textContent="TXT gerado com as regras de histórico do original.";}catch(e){msg.textContent=e.message;}
});
fetch(`${API()}/api/v1/migration-status`).then(response=>response.ok?response.json():null).then(status=>{
  $("#importOriginalBase").hidden=!status?.original_base_import_configured;
}).catch(()=>{});

initializeWorkspaceUI();
