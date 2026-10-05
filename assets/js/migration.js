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
  $("#previewWorkflow").hidden = company.capabilities?.workflow !== "advanced";
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

function tableFor(headers, rows) {
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const line = document.createElement("tr");
  headers.forEach(label => {const th = document.createElement("th"); th.textContent = label; line.appendChild(th);});
  head.appendChild(line); table.appendChild(head);
  const body = document.createElement("tbody");
  rows.forEach(row => {
    const tr = document.createElement("tr");
    row.forEach(value => {const td=document.createElement("td"); td.textContent=String(value ?? ""); tr.appendChild(td);});
    body.appendChild(tr);
  });
  table.appendChild(body);
  return table;
}

function showWorkflowPreview(data) {
  const target = $("#workflowPreview"); target.replaceChildren();
  data.sheets.forEach(sheet => {
    const title = document.createElement("h4");
    title.textContent = `${sheet.name} · ${sheet.count} lançamentos · entradas ${sheet.entradas.toFixed(2)} · saídas ${sheet.saidas.toFixed(2)}`;
    target.appendChild(title);
    target.appendChild(tableFor(sheet.columns, sheet.rows));
  });
  (data.diagnostics || []).forEach(sheet => {
    const title=document.createElement("h4");title.textContent=`${sheet.name} · ${sheet.count} registro(s)`;target.appendChild(title);
    target.appendChild(tableFor(sheet.columns,sheet.rows));
  });
  const note = document.createElement("p"); note.textContent="A prévia mostra até 500 linhas por aba. O Excel contém todos os lançamentos."; target.appendChild(note);
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
