/* Conferência Fiscal x Contábil: projeto piloto exclusivo da empresa 242. */
(() => {
  const tab = document.querySelector('#companyPanel .tool-tab[data-tool="fiscal"]');
  const pane = document.querySelector('#companyPanel .tool-pane[data-pane="fiscal"]');
  const form = document.querySelector("#fiscal242Form");
  const message = document.querySelector("#fiscal242Message");
  const results = document.querySelector("#fiscal242Results");
  const filter = document.querySelector("#fiscal242Filter");
  const tableBody = document.querySelector("#fiscal242Rows");
  const details = document.querySelector("#fiscal242Detail");
  const download = document.querySelector("#fiscal242Download");
  const submit = document.querySelector("#fiscal242Submit");
  if (!tab || !pane || !form || !results) return;

  const money = new Intl.NumberFormat("pt-BR", {style:"currency", currency:"BRL"});
  const statusLabels = {
    "CONFERE": "Bate",
    "CONFERE COM ALERTAS": "Com alertas",
    "REVISAR": "Divergência",
    "AUSENTE NO CONTÁBIL": "Sem razão"
  };
  let data = null;
  let previewBody = null;
  let aiController = null;
  let aiConfigured = false;

  let selectedKey = "";
  let pendingRequest = null;

  const byId = id => document.getElementById(id);
  const aiButton = byId("fiscal242AI");
  const aiMessage = byId("fiscal242AIMessage");
  const aiResult = byId("fiscal242AIResult");
  let statusController = null;
  async function refreshAIStatus() {
    statusController?.abort();
    const controller = new AbortController(); statusController = controller;
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/242/ia/status?t=" + Date.now(), {cache:"no-store", signal:controller.signal});
      if (!response.ok) throw new Error("Status indisponível");
      const result = await response.json();
      if (statusController !== controller) return;
      aiConfigured = result.configurado === true;
      aiButton.disabled = !aiConfigured || !previewBody || Boolean(aiController);
      if (!aiController && !aiResult.children.length) aiMessage.textContent = aiConfigured
        ? (previewBody ? "Gemini conectado. Clique em Analisar diferenças com IA." : "Gemini conectado. Faça a conferência para analisar as diferenças.")
        : "Gemini ainda não configurado. Após adicionar a chave no Railway, clique em Atualizar conexão.";
    } catch (error) {
      if (statusController !== controller) return;
      if (!aiController) aiMessage.textContent = "Não foi possível verificar a conexão. Clique em Atualizar conexão para tentar novamente.";
    } finally {
      clearTimeout(timeout);
      if (statusController === controller) statusController = null;
    }
  }
  const refreshConnection = node("button", "secondary-action", "Atualizar conexão");
  refreshConnection.type = "button";
  refreshConnection.addEventListener("click", refreshAIStatus);
  aiButton.after(refreshConnection);
  tab.addEventListener("click", refreshAIStatus);
  window.addEventListener("focus", () => { if (Number(selected?.codigo) === 242 && !pane.hidden) refreshAIStatus(); });
  refreshAIStatus();
  aiButton.addEventListener("click", async () => {
    if (!previewBody || !aiConfigured || Number(selected?.codigo) !== 242) return;
    aiController?.abort(); const controller = new AbortController(); aiController = controller;
    const snapshot = previewBody; aiButton.disabled = true; aiResult.replaceChildren();
    aiResult.setAttribute("aria-busy", "true");
    aiMessage.textContent = "Analisando lançamentos e diferenças com Gemini…";
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/242/ia", {method:"POST",body:snapshot,signal:controller.signal});
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      if (controller.signal.aborted || previewBody !== snapshot || Number(selected?.codigo) !== 242) return;
      for (const item of result.analises || []) {
        const card = node("article", "fiscal-ai-card");
        const heading = node("div", "fiscal-ai-card-heading");
        heading.append(node("h4", "", `Conta ${item.conta}`), node("span", "fiscal-ai-type", item.tipo));
        const analysis = node("div", "fiscal-ai-analysis");
        analysis.append(node("h5", "", "Análise dos lançamentos"), node("p", "", item.explicacao));
        const review = node("div", "fiscal-ai-review");
        review.append(node("h5", "", "O que conferir"), node("p", "", item.verificar));
        card.appendChild(heading);
        if (item.valores) {
          const metrics = node("div", "fiscal-ai-values");
          [["Fiscal", "fiscal"], ["Total do Razão", "total_conta"],
           ["Contábil considerado", "contabil"], ["Diferença", "diferenca"]].forEach(([label, key]) => {
            const metric = node("div", "fiscal-ai-value");
            metric.append(node("small", "", label), node("strong", "", money.format(Number(item.valores[key] || 0))));
            metrics.appendChild(metric);
          });
          card.appendChild(metrics);
        }
        card.append(analysis, review);
        if (item.evidencias?.length) {
          const details = node("details", "fiscal-ai-evidence");
          details.append(node("summary", "", `Lançamentos citados (${item.evidencias.length})`));
          for (const row of item.evidencias) {
            const value = n => Number(n || 0).toLocaleString("pt-BR", {style:"currency", currency:"BRL"});
            const record = node("div", "fiscal-ai-record");
            const title = node("div", "fiscal-ai-record-title");
            title.append(node("strong", "", row.referencia), node("span", "", row.data));
            const metrics = node("dl", "fiscal-ai-record-metrics");
            for (const [label, content] of [["Conta", row.conta], ["Contrapartida", row.contrapartida], ["Débito", value(row.debito)], ["Crédito", value(row.credito)]]) {
              const metric = node("div", ""); metric.append(node("dt", "", label), node("dd", "", content)); metrics.append(metric);
            }
            record.append(title, node("p", "", row.historico), metrics); details.append(record);
          }
          card.append(details);
        }
        aiResult.append(card);
      }
      aiMessage.textContent = result.aviso + (result.limite ? " " + result.limite : "");
    } catch (error) {
      if (!controller.signal.aborted && previewBody === snapshot) aiMessage.textContent = error.message;
    } finally {
      if (aiController === controller) { aiResult.setAttribute("aria-busy", "false"); aiController = null; aiButton.disabled = !aiConfigured || !previewBody; }
    }
  });
  const keyOf = row => String(row.conta) + ":" + String(row.tipo);
  const selectedFiles = () => {
    const acumuladores = byId("fiscal242Acumuladores").files[0];
    const razao = byId("fiscal242Razao").files[0];
    if (!acumuladores || !razao) throw new Error("Selecione o Resumo por Acumulador e o Razão.");
    return {acumuladores, razao};
  };
  function buildFormData() {
    const files = selectedFiles();
    const body = new FormData();
    body.append("acumuladores", files.acumuladores);
    body.append("razao", files.razao);
    body.append("filial", "242");
    return body;
  }
  function node(tag, className, content) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (content !== undefined) el.textContent = String(content);
    return el;
  }
  function cell(tr, value, className) {
    const td = node("td", className, value);
    tr.appendChild(td);
    return td;
  }
  function setMessage(value, kind) {
    message.textContent = value || "";
    message.dataset.state = kind || "";
  }
  function clearState() {
    aiController?.abort(); aiController = null;
    aiButton.disabled = true; aiResult.replaceChildren(); aiResult.setAttribute("aria-busy", "false");
    aiMessage.textContent = aiConfigured ? "Faça a conferência antes de analisar com IA." : "Gemini ainda não configurado no servidor.";
    if (pendingRequest) {
      pendingRequest.abort();
      pendingRequest = null;
    }
    data = null;
    previewBody = null;
    byId("fiscal242Unmapped").hidden = true;
    byId("fiscal242UnmappedRows").replaceChildren();
    selectedKey = "";
    filter.value = "todas";
    results.hidden = true;
    details.hidden = true;
    details.replaceChildren();
    tableBody.replaceChildren();
    setMessage("");
    submit.disabled = false;
    download.disabled = false;
  }

  // O app original mostra todas as guias disponíveis. A 242 é a única
  // empresa que recebe esta guia durante a homologação.
  const previousOpenCompany = openCompany;
  openCompany = function(company) {
    clearState();
    previousOpenCompany(company);
    const is242 = Number(company && company.codigo) === 242;
    if (is242) refreshAIStatus();
    tab.hidden = !is242;
    if (!is242 && panel.dataset.activeTool === "fiscal") activateTool("organizar");
  };
  tab.hidden = true;

  function filteredRows() {
    const contas = data?.contas || [];
    if (filter.value === "revisar") return contas.filter(row => ["REVISAR", "AUSENTE NO CONTÁBIL"].includes(row.situacao));
    if (filter.value === "alertas") return contas.filter(row => row.situacao === "CONFERE COM ALERTAS");
    if (filter.value === "bate") return contas.filter(row => row.situacao === "CONFERE");
    return contas;
  }
  function renderDetails(row) {
    details.replaceChildren();
    if (!row) { details.hidden = true; return; }
    details.hidden = false;
    const heading = node("div", "fiscal-detail-heading");
    const summary = node("div");
    summary.appendChild(node("h3", "", "Conta " + row.conta + " · " + (row.descricao || "Sem descrição")));
    summary.appendChild(node("p", "", "Acumulador(es): " + row.acumuladores + " · " + row.tipo));
    heading.appendChild(summary);
    heading.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(row.situacao), statusLabels[row.situacao] || row.situacao));
    details.appendChild(heading);

    const metrics = node("div", "fiscal-detail-metrics");
    [
      ["Fiscal", money.format(row.fiscal)],
      ["Total movimentado no Razão (lado analisado)", money.format(row.total_conta)],
      ["Contábil considerado (preliminar)", money.format(row.contabil)],
      ["Diferença", money.format(row.diferenca)]
    ].forEach(pair => {
      const card = node("div");
      card.appendChild(node("small", "", pair[0]));
      card.appendChild(node("strong", "", pair[1]));
      metrics.appendChild(card);
    });
    details.appendChild(metrics);
    if (row.extras) {
      details.appendChild(node("p", "fiscal-detail-alert", row.extras + " lançamento(s) com indício de movimento não fiscal. Valide os históricos e as contrapartidas."));
    }
    if (row.sem_evidencia) {
      details.appendChild(node("p", "fiscal-detail-alert", row.sem_evidencia + " lançamento(s) fecham apenas pelo valor, mas o histórico não comprova origem fiscal. Situação: com alertas."));
    }

    const wantedCredit = row.tipo === "SAÍDAS";
    const movimentos = (data.lancamentos || []).filter(item =>
      item.conta === row.conta &&
      String(item.natureza).includes(wantedCredit ? "CRÉDITO" : "DÉBITO")
    );
    details.appendChild(node("h4", "", "Lançamentos do Razão (" + movimentos.length + ")"));
    if (!movimentos.length) {
      details.appendChild(node("p", "fiscal-empty", "Não há movimentos dessa natureza no Razão enviado."));
      return;
    }
    const wrap = node("div", "fiscal-table-scroll");
    const table = node("table", "fiscal-table fiscal-detail-table");
    const head = node("thead");
    const headerRow = node("tr");
    ["Data", "Histórico", "Contrapartida", "Débito", "Crédito", "Classificação"].forEach(label => {
      headerRow.appendChild(node("th", "", label));
    });
    head.appendChild(headerRow);
    table.appendChild(head);
    const body = node("tbody");
    movimentos.slice(0, 200).forEach(mov => {
      const tr = node("tr");
      cell(tr, mov.data);
      cell(tr, mov.historico);
      cell(tr, mov.contrapartida);
      cell(tr, money.format(mov.debito), "fiscal-money");
      cell(tr, money.format(mov.credito), "fiscal-money");
      const classificacao = mov.classificacao === "ALERTA - NÃO FISCAL" ? "Possível movimento não fiscal"
        : mov.classificacao === "FECHAMENTO POR VALOR - VALIDAR" ? "Fecha por valor · validar" : "Fiscal provável";
      cell(tr, classificacao);
      body.appendChild(tr);
    });
    table.appendChild(body);
    wrap.appendChild(table);
    details.appendChild(wrap);
    if (movimentos.length > 200) {
      details.appendChild(node("p", "fiscal-empty", "Exibindo 200 de " + movimentos.length + " lançamentos; consulte os arquivos originais para a análise completa."));
    }
    details.appendChild(node("p", "fiscal-disclaimer", "Conferência preliminar: lançamentos classificados pelo histórico precisam de validação contábil."));
  }

  function statusClass(status) {
    if (status === "CONFERE") return "ok";
    if (status === "CONFERE COM ALERTAS") return "alert";
    return "review";
  }

  function renderTable() {
    const rows = filteredRows();
    tableBody.replaceChildren();
    byId("fiscal242Empty").hidden = rows.length > 0;
    if (!rows.length) { renderDetails(null); return; }
    if (!rows.some(row => keyOf(row) === selectedKey)) selectedKey = keyOf(rows[0]);
    rows.forEach(row => {
      const tr = node("tr");
      const id = keyOf(row);
      if (id === selectedKey) tr.classList.add("selected");
      const account = cell(tr, "", "fiscal-account");
      const button = node("button", "fiscal-account-link", row.conta);
      button.type = "button";
      button.setAttribute("aria-label", "Ver detalhes da conta " + row.conta);
      button.addEventListener("click", () => {
        selectedKey = id;
        renderTable();
      });
      account.appendChild(button);
      cell(tr, row.descricao || "—", "fiscal-description");
      cell(tr, row.tipo);
      cell(tr, money.format(row.fiscal), "fiscal-money");
      cell(tr, money.format(row.total_conta), "fiscal-money");
      cell(tr, money.format(row.contabil), "fiscal-money");
      cell(tr, money.format(row.diferenca), "fiscal-money");
      const td = cell(tr, "");
      td.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(row.situacao), statusLabels[row.situacao] || row.situacao));
      tableBody.appendChild(tr);
    });
    renderDetails(rows.find(row => keyOf(row) === selectedKey));
  }

  function renderResponse(report) {
    data = report;
    byId("fiscal242Total").textContent = report.resumo.total;
    byId("fiscal242Matches").textContent = report.resumo.conferem;
    byId("fiscal242Alerts").textContent = report.resumo.com_alertas;
    byId("fiscal242Pending").textContent = report.resumo.revisar;
    const fiscal = report.periodo_fiscal || {};
    const parts = [];
    if (fiscal.inicio && fiscal.fim) parts.push("Fiscal: " + fiscal.inicio + " a " + fiscal.fim);
    if (report.filial_aplicada) parts.push("Filial do Razão: " + report.filial_aplicada);
    byId("fiscal242Period").textContent = parts.join(" · ");
    const warningBox = byId("fiscal242Warnings");
    warningBox.replaceChildren();
    (report.avisos || []).forEach(aviso => warningBox.appendChild(node("p", "", aviso)));
    const semConta = report.sem_conta || [];
    const pendentes = byId("fiscal242Unmapped");
    const pendentesCorpo = byId("fiscal242UnmappedRows");
    pendentes.hidden = !semConta.length;
    byId("fiscal242UnmappedCount").textContent = semConta.length ? "(" + semConta.length + ")" : "";
    pendentesCorpo.replaceChildren();
    semConta.forEach(item => {
      const tr = node("tr");
      cell(tr, item.acumulador || "—");
      cell(tr, item.descricao || "—");
      cell(tr, item.tipo || "—");
      cell(tr, money.format(item.valor || 0), "fiscal-money");
      pendentesCorpo.appendChild(tr);
    });
    results.hidden = false;
    selectedKey = "";
    filter.value = "todas";
    renderTable();
  }
  filter.addEventListener("change", renderTable);
  form.querySelectorAll("input[type=file]").forEach(input => input.addEventListener("change", clearState));
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (Number(selected?.codigo) !== 242) return;
    let body;
    try { body = buildFormData(); } catch (error) { setMessage(error.message, "error"); return; }
    aiController?.abort(); aiController = null; aiButton.disabled = true; aiResult.replaceChildren();
    if (pendingRequest) pendingRequest.abort();
    const controller = new AbortController();
    pendingRequest = controller;
    submit.disabled = true;
    results.hidden = true;
    setMessage("Analisando acumuladores e lançamentos do Razão…", "loading");
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/242/preview", {
        method:"POST", body, signal: controller.signal
      });
      if (!response.ok) throw new Error(await responseError(response));
      const report = await response.json();
      if (controller.signal.aborted || Number(selected?.codigo) !== 242) return;
      renderResponse(report);
      previewBody = body;
      aiButton.disabled = !aiConfigured;
      refreshAIStatus();
      setMessage("Conferência concluída. Os resultados estão abaixo.", "success");
    } catch (error) {
      if (error.name === "AbortError") return;
      setMessage(error.message || "Não foi possível conferir esses relatórios.", "error");
    } finally {
      if (pendingRequest === controller) {
        pendingRequest = null;
        submit.disabled = false;
      }
    }
  });

  download.addEventListener("click", async () => {
    if (!data || !previewBody || Number(selected?.codigo) !== 242) return;
    const body = previewBody;
    download.disabled = true;
    setMessage("Preparando relatório Excel…", "loading");
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/242", {
        method:"POST", body
      });
      if (!response.ok) throw new Error(await responseError(response));
      if (previewBody !== body || Number(selected?.codigo) !== 242) return;
      await downloadBlob(response, "RAZYNC_242_CONFERENCIA_FISCAL.xlsx");
      setMessage("Relatório Excel gerado.", "success");
    } catch (error) {
      setMessage(error.message || "Não foi possível gerar o Excel.", "error");
    } finally {
      download.disabled = false;
    }
  });
})();
