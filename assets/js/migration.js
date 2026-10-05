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
  $("#workflowPreview").replaceChildren();
  $("#reviewRows").replaceChildren();
  $("#applyReview").hidden = true;
  reviewPendingRows = [];
  reviewSourceFile = null;
};

openCompany = function(company) {
  // File inputs must not carry documents across company navigation.
  document.querySelectorAll("#companyPanel form").forEach(f => f.reset());
  $("#adminAccess").value = "";
  $("#targetCnpj").value = "";
  $("#baseManagementMessage").textContent = "";
  $("#reviewMessage").textContent = "";
  $("#a1Message").textContent = "";
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

function showWorkflowPreview(data) {
  const target = $("#workflowPreview");
  target.replaceChildren();

  const intro = document.createElement("div");
  intro.className = "preview-intro";
  const introText = document.createElement("div");
  const eyebrow = document.createElement("span");
  eyebrow.className = "preview-eyebrow";
  eyebrow.textContent = "PRÉVIA DOS LANÇAMENTOS";
  const heading = document.createElement("h3");
  heading.textContent = "Confira como os lançamentos ficarão no Modelo Domínio";
  const description = document.createElement("p");
  description.textContent = "A tabela abaixo representa o arquivo processado. Confira datas, valores, débito, crédito e histórico antes de baixar.";
  introText.append(eyebrow, heading, description);
  intro.appendChild(introText);
  target.appendChild(intro);

  (data.sheets || []).forEach(sheet => {
    const block = document.createElement("section");
    block.className = "preview-sheet";

    const header = document.createElement("div");
    header.className = "preview-sheet-head";
    const titleBox = document.createElement("div");
    const title = document.createElement("h4");
    title.textContent = sheet.name;
    const subtitle = document.createElement("span");
    subtitle.textContent = `${sheet.count} lançamento(s)`;
    titleBox.append(title, subtitle);

    const metrics = document.createElement("div");
    metrics.className = "preview-metrics";
    metrics.append(
      metricChip("Entradas", new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(Number(sheet.entradas || 0))),
      metricChip("Saídas", new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(Number(sheet.saidas || 0)))
    );

    header.append(titleBox, metrics);
    block.appendChild(header);

    const rows = sheet.rows || [];
    const table = tableFor(sheet.columns || [], rows);

    if (rows.length > 6) {
      const tools = document.createElement("div");
      tools.className = "preview-table-tools";
      const search = document.createElement("input");
      search.type = "search";
      search.placeholder = "Filtrar lançamentos desta tabela";
      search.setAttribute("aria-label", `Filtrar lançamentos de ${sheet.name}`);
      const visible = document.createElement("span");
      visible.textContent = `${rows.length} exibidos`;

      search.addEventListener("input", () => {
        const query = previewLabel(search.value);
        let shown = 0;
        [...table.tBodies[0].rows].forEach(row => {
          const match = !query || previewLabel(row.textContent).includes(query);
          row.hidden = !match;
          if (match) shown += 1;
        });
        visible.textContent = query
          ? `${shown} de ${rows.length}`
          : `${rows.length} exibidos`;
      });

      tools.append(search, visible);
      block.appendChild(tools);
    }

    const scroll = document.createElement("div");
    scroll.className = "preview-table-scroll";
    scroll.appendChild(table);
    block.appendChild(scroll);
    target.appendChild(block);
  });

  if ((data.diagnostics || []).length) {
    const details = document.createElement("details");
    details.className = "preview-diagnostics";
    const summary = document.createElement("summary");
    summary.textContent = "Ver conferências e diagnósticos";
    details.appendChild(summary);

    data.diagnostics.forEach(sheet => {
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

$("#downloadConnector").addEventListener("click",async()=>{
  try {const r=await fetch(`${API()}/api/v1/connector/download`);if(!r.ok)throw new Error(await responseError(r));await downloadBlob(r,"RAZYNC_WEB_CONECTOR_WINDOWS.zip");}catch(e){$("#taxMessage").textContent=e.message;}
});
$("#a1Form").addEventListener("submit",async event=>{
  event.preventDefault();const code=selected.codigo;const msg=$("#a1Message");const data=new FormData();data.append("file",$("#a1File").files[0]);data.append("password",$("#a1Password").value);data.append("cnpj",$("#a1Cnpj").value);
  try {const r=await fetch(`${API()}/api/v1/certificates/${code}`,{method:"POST",headers:adminHeaders(),body:data});if(!r.ok)throw new Error(await responseError(r));const result=await r.json();msg.textContent=`A1 cadastrado: ${result.certificate.titular} · validade ${result.certificate.validade_fim}`;event.target.reset();}catch(e){msg.textContent=e.message;}
});
$("#a1Status").addEventListener("click",async()=>{
  try {const r=await fetch(`${API()}/api/v1/certificates/${selected.codigo}`,{headers:adminHeaders()});if(!r.ok)throw new Error(await responseError(r));const certificate=(await r.json()).certificate;$("#a1Message").textContent=certificate?`${certificate.titular} · CNPJ ${certificate.cnpj} · validade ${certificate.validade_fim}`:"Nenhum A1 cadastrado.";}catch(e){$("#a1Message").textContent=e.message;}
});

$("#a1Delete").addEventListener("click",async()=>{
  if(!confirm("Remover o certificado A1 cadastrado desta empresa?"))return;
  try {const r=await fetch(`${API()}/api/v1/certificates/${selected.codigo}`,{method:"DELETE",headers:adminHeaders()});if(!r.ok)throw new Error(await responseError(r));$("#a1Message").textContent="Cadastro removido.";}catch(e){$("#a1Message").textContent=e.message;}
});
$("#txtForm").addEventListener("submit",async event=>{
  event.preventDefault();const data=new FormData();data.append("file",$("#txtModel").files[0]);const msg=$("#txtMessage");
  try {const r=await fetch(`${API()}/api/v1/modelo-dominio-txt`,{method:"POST",body:data});if(!r.ok)throw new Error(await responseError(r));await downloadBlob(r,"RAZYNC_MODELO_DOMINIO.txt");msg.textContent="TXT gerado com as regras de histórico do original.";}catch(e){msg.textContent=e.message;}
});
fetch(`${API()}/api/v1/migration-status`).then(response=>response.ok?response.json():null).then(status=>{
  $("#importOriginalBase").hidden=!status?.original_base_import_configured;
}).catch(()=>{});
