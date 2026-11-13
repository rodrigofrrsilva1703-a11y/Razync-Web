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
  function render(sheets) {
    showWorkflowPreview({sheets}, result, {
      title: "Prévia do Modelo Domínio",
      primarySheet: "Consolidado",
      sheetLabel: "Abas",
      description: "Revise os lançamentos por aba. A prévia é limitada a 500 linhas por aba; o Excel inclui todos os lançamentos, com as contas em branco para preenchimento."
    });
    result.querySelector(".preview-primary-actions").append(downloadButton);
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
    const ticket = generation;
    downloadButton.disabled = true;
    message.textContent = "Gerando Modelo Domínio…";
    try {
      const response = await fetch(url(), { method: "POST", body: snapshot });
      if (!response.ok) throw new Error(await errorText(response));
      const blob = await response.blob();
      if (ticket !== generation) return;
      const link = document.createElement("a");
      const objectUrl = URL.createObjectURL(blob);
      link.href = objectUrl;
      link.download = "RAZYNC_CONVERSOR_EXTRATOS_MODELO_DOMINIO.xlsx";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 2000);
      message.textContent = "Arquivo gerado.";
    } catch (err) { if (ticket === generation) message.textContent = err.message || "Não foi possível exportar."; }
    finally { downloadButton.disabled = false; }
  });
})();
