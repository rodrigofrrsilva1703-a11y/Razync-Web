/* Conversor global: reutiliza a API de leitura e a geração do Modelo Domínio. */
(() => {
  const form = document.querySelector("#globalConverterForm");
  if (!form) return;
  const $ = id => document.getElementById(id);
  const files = $("globalConverterFiles");
  const start = $("globalConverterStart");
  const end = $("globalConverterEnd");
  const result = $("globalConverterResult");
  const message = $("globalConverterMessage");
  const previewButton = $("globalConverterPreviewButton");
  const downloadButton = $("globalConverterDownload");
  const url = () => (window.RAZYNC_CONFIG?.apiBase || "").replace(/\/$/, "") + "/api/v1/conversor-extratos";
  let snapshot = null;
  let generation = 0;

  function payload() {
    const data = new FormData();
    [...files.files].forEach(file => data.append("files", file));
    data.append("data_inicial", start.value);
    data.append("data_final", end.value);
    return data;
  }
  function invalidate() {
    generation++;
    snapshot = null;
    downloadButton.hidden = true;
    result.replaceChildren();
    result.hidden = true;
    message.textContent = "";
  }
  [files, start, end].forEach(el => el.addEventListener("change", invalidate));
  function money(n) {
    return Number(n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  function render(sheets) {
    result.replaceChildren();
    const title = document.createElement("h3");
    title.textContent = "Prévia do Modelo Domínio";
    result.append(title);
    const note = document.createElement("p");
    note.textContent = "A prévia exibe até 500 linhas por aba; o Excel contém todos os lançamentos. Contas de débito e crédito permanecem em branco para revisão.";
    result.append(note);
    for (const sheet of sheets) {
      const details = document.createElement("details");
      details.open = sheet.name === "Consolidado";
      const summary = document.createElement("summary");
      summary.textContent = sheet.name + " · " + sheet.count + " lançamentos · Entradas " + money(sheet.entradas) + " · Saídas " + money(sheet.saidas);
      details.append(summary);
      const wrap = document.createElement("div");
      wrap.className = "preview-table-scroll";
      const table = document.createElement("table");
      table.className = "razync-table";
      const head = document.createElement("thead");
      const tr = document.createElement("tr");
      sheet.columns.forEach(col => {
        const th = document.createElement("th");
        th.textContent = col;
        tr.append(th);
      });
      head.append(tr);
      const body = document.createElement("tbody");
      (sheet.rows || []).forEach(row => {
        const line = document.createElement("tr");
        row.forEach(value => {
          const td = document.createElement("td");
          td.textContent = value == null ? "" : String(value);
          line.append(td);
        });
        body.append(line);
      });
      table.append(head, body);
      wrap.append(table);
      details.append(wrap);
      result.append(details);
    }
    result.hidden = false;
  }
  async function errorText(response) {
    try {
      const data = await response.json();
      return typeof data.detail === "string" ? data.detail : "O arquivo não pôde ser processado.";
    } catch { return "Falha na comunicação com o servidor."; }
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    invalidate();
    if (!files.files.length) { message.textContent = "Selecione pelo menos um extrato."; return; }
    if (start.value && end.value && start.value > end.value) { message.textContent = "A data inicial não pode ser maior que a final."; return; }
    const ticket = generation;
    snapshot = payload();
    previewButton.disabled = true;
    message.textContent = "Lendo extratos e montando a prévia…";
    try {
      const response = await fetch(url() + "/preview", { method: "POST", body: snapshot });
      if (!response.ok) throw new Error(await errorText(response));
      const data = await response.json();
      if (ticket !== generation) return;
      render(data.sheets || []);
      downloadButton.hidden = false;
      message.textContent = "Prévia pronta. Confira os lançamentos antes de exportar.";
    } catch (err) {
      if (ticket === generation) { snapshot = null; message.textContent = err.message || "Não foi possível ler o extrato."; }
    } finally { previewButton.disabled = false; }
  });
  downloadButton.addEventListener("click", async () => {
    if (!snapshot) return;
    downloadButton.disabled = true;
    message.textContent = "Gerando Modelo Domínio…";
    try {
      const response = await fetch(url(), { method: "POST", body: snapshot });
      if (!response.ok) throw new Error(await errorText(response));
      const blob = await response.blob();
      const link = document.createElement("a");
      const objectUrl = URL.createObjectURL(blob);
      link.href = objectUrl;
      link.download = "RAZYNC_CONVERSOR_EXTRATOS_MODELO_DOMINIO.xlsx";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 2000);
      message.textContent = "Arquivo gerado.";
    } catch (err) { message.textContent = err.message || "Não foi possível exportar."; }
    finally { downloadButton.disabled = false; }
  });
})();
