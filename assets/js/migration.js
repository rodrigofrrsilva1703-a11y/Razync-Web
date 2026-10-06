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
  const dates = [...advancedFields.querySelectorAll('input[type="date"]')];
  if (dates.length) {
    const period = document.createElement("fieldset"); period.className = "period-card";
    const legend = document.createElement("legend"); legend.textContent = "Período dos lançamentos (opcional)";
    const fields = document.createElement("div"); fields.className = "period-fields";
    dates.forEach(input => fields.append(input.closest(".field-group")));
    period.append(legend, fields); advancedFields.append(period);
  }
  $("#toolDescription").textContent += " A prévia aparece automaticamente quando os arquivos obrigatórios estiverem preenchidos.";
  $("#standardPeriod").hidden = company.capabilities?.workflow === "advanced";
  const eletro = [242,1408].includes(Number(company.codigo));
  const fiscalOnly = company.capabilities?.status === "fiscal_only";
  $$(".tool-tab").forEach(button => {button.hidden = fiscalOnly && button.dataset.tool !== "fiscal";});
  $("#reportPackage").hidden = company.capabilities?.workflow !== "advanced";
  $("#reportPackage").textContent = eletro ? "Baixar relatórios individuais e consolidado" : "Baixar modelo e conferências";
  $("#previewWorkflow").hidden = true;
  $("#eletroClassification").hidden = !eletro;
  $("#reviewForm").hidden = eletro;
  if ([3,178,343,266,1396].includes(Number(company.codigo))) {
    const label=document.createElement("label");label.textContent="Bancos para organizar";
    const wrapper=document.createElement("div");wrapper.className="bank-options";
    const names={itau:"Itaú",daycoval:"Daycoval",bradesco:"Bradesco",fibra:"Fibra"};
    Object.keys(company.capabilities.banks).forEach(bank=>{
      const item=document.createElement("label"),input=document.createElement("input");input.type="checkbox";input.checked=true;input.dataset.selectedBank=names[bank];item.append(input,document.createTextNode(names[bank]));wrapper.appendChild(item);
    });
    advancedFields.append(label,wrapper);
  }
  francesinhasTab.hidden = !eletro;
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
  table.className = "dataframe-preview";
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

function metricChip(label, value) {
  const item = document.createElement("span");
  item.className = "preview-metric";
  const small = document.createElement("small");
  small.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
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
      [["all","Todos"],["in","Entradas"],["out","Saídas"],["pending","Contas a revisar"]].forEach(([value,label])=>{
        const option=document.createElement("option");option.value=value;option.textContent=label;kind.append(option);
      });
      const visible = document.createElement("span");
      const columns = (sheet.columns || []).map(previewLabel);
      const amountIndex = columns.indexOf("VALOR");
      const debitIndex = columns.indexOf("DEBITO"), creditIndex = columns.indexOf("CREDITO");
      const needsReview = row => [debitIndex,creditIndex].some(index=>index>=0 && (!String(row[index] ?? "").trim() || Number(row[index]) === 0));
      [...table.tBodies[0].rows].forEach((row,index)=>{
        if(needsReview(rows[index])) {row.classList.add("accounts-pending");row.title="Há conta em branco ou zero. Confira antes de importar.";}
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

$("#reviewForm").addEventListener("submit", async event=>{
  event.preventDefault(); const code=selected.codigo; const msg=$("#reviewMessage");
  reviewSourceFile=$("#reviewFile").files[0];if(!reviewSourceFile)return;
  const sourceFile=reviewSourceFile;
  const data=new FormData();data.append("file",reviewSourceFile);msg.textContent="Listando pendências…";
  try {
    const r=await fetch(`${API()}/api/v1/base-inteligente/${code}/pendencias`,{method:"POST",body:data});
    if(!r.ok)throw new Error(await responseError(r));
    const result=await r.json();
    if(selected?.codigo!==code || reviewSourceFile!==sourceFile)return;
    reviewPendingRows=result.pendencias;
    const table=tableFor(["Banco","Data","Valor","Histórico","Classificar em","Conta da contrapartida"],reviewPendingRows.map(row=>[row.Banco,row.Data,row.Valor,row["Histórico"],row["Classificar em"],""]));
    [...table.querySelectorAll("tbody tr")].forEach((tr,i)=>{
      const input=document.createElement("input");input.type="text";input.inputMode="numeric";input.setAttribute("aria-label",`Conta da contrapartida do lançamento ${i+1}`);
      input.addEventListener("input",()=>reviewPendingRows[i]["Conta da contrapartida"]=input.value);
      tr.lastElementChild.appendChild(input);
    });
    $("#reviewRows").replaceChildren(table);$("#applyReview").hidden=!reviewPendingRows.length;
    msg.textContent=`${reviewPendingRows.length} lançamento(s) pendente(s).`;
  }catch(e){msg.textContent=e.message;}
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
  try {const r=await fetch(`${API()}/api/v1/modelo-dominio-txt`,{method:"POST",body:data});if(!r.ok)throw new Error(await responseError(r));await downloadBlob(r,"RAZYNC_MODELO_DOMINIO.txt");msg.textContent="TXT gerado com as regras de histórico do original.";}catch(e){msg.textContent=e.message;}
});
fetch(`${API()}/api/v1/migration-status`).then(response=>response.ok?response.json():null).then(status=>{
  $("#importOriginalBase").hidden=!status?.original_base_import_configured;
}).catch(()=>{});
