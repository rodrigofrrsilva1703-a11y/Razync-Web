/* Conferência Fiscal x Contábil: ferramenta universal do menu lateral. */
(() => {
  const pane = document.querySelector("#fiscalView");
  const navigation = document.querySelector('.main-nav-btn[data-view="fiscal"]');
  const form = document.querySelector("#fiscal242Form");
  const message = document.querySelector("#fiscal242Message");
  const results = document.querySelector("#fiscal242Results");
  const filter = document.querySelector("#fiscal242Filter");
  const search = document.querySelector("#fiscal242Search");
  const resultsCount = document.querySelector("#fiscal242Count");
  const tableBody = document.querySelector("#fiscal242Rows");
  const details = document.querySelector("#fiscal242Detail");
  const download = document.querySelector("#fiscal242Download");
  const submit = document.querySelector("#fiscal242Submit");
  if (!pane || !navigation || !form || !results) return;

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
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/ia/status?t=" + Date.now(), {cache:"no-store", signal:controller.signal});
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
  navigation.addEventListener("click", refreshAIStatus);
  window.addEventListener("focus", () => { if (pane.classList.contains("active")) refreshAIStatus(); });
  refreshAIStatus();
  aiButton.addEventListener("click", async () => {
    if (!previewBody || !aiConfigured) return;
    aiController?.abort(); const controller = new AbortController(); aiController = controller;
    const snapshot = previewBody; aiButton.disabled = true; aiResult.replaceChildren();
    aiResult.setAttribute("aria-busy", "true");
    aiMessage.textContent = "Analisando lançamentos e diferenças com Gemini…";
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/ia", {method:"POST",body:snapshot,signal:controller.signal});
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      if (controller.signal.aborted || previewBody !== snapshot) return;
      for (const item of result.analises || []) {
        const card = node("article", "fiscal-ai-card");
        const heading = node("div", "fiscal-ai-card-heading");
        heading.append(node("h4", "", `Conta contábil ${item.conta}`), node("span", "fiscal-ai-type", item.tipo));
        const officialRow = (data?.contas || []).find(row => keyOf(row) === keyOf(item)) || item;
        const accumulatorInfo = accumulatorBreakdown(officialRow);
        const analysis = node("div", "fiscal-ai-analysis");
        analysis.append(node("h5", "", "O que os relatórios mostram e o que pode explicar a diferença"), node("p", "", item.explicacao));
        const review = node("div", "fiscal-ai-review");
        review.append(node("h5", "", "O que conferir, passo a passo"), node("p", "", item.verificar));
        card.appendChild(heading);
        card.appendChild(accumulatorInfo);
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
  function accumulatorRows(row) {
    const details = Array.isArray(row?.detalhes_fiscais) ? row.detalhes_fiscais : [];
    if (details.length) return details.map(item => ({
      codigo: String(item.codigo ?? "").trim(),
      descricao: String(item.descricao ?? "").trim(),
      valor: Number(item.valor || 0)
    })).filter(item => item.codigo);
    return String(row?.acumuladores || "").split(",").map(code => ({
      codigo: code.trim(), descricao: "", valor: null
    })).filter(item => item.codigo);
  }
  function accumulatorTags(row) {
    const group = node("div", "fiscal-accum-tags");
    for (const item of accumulatorRows(row)) {
      const tag = node("span", "fiscal-accum-tag", item.codigo);
      if (item.descricao) tag.title = item.descricao;
      group.appendChild(tag);
    }
    if (!group.childElementCount) group.appendChild(node("span", "", "—"));
    return group;
  }
  function accumulatorBreakdown(row) {
    const items = accumulatorRows(row);
    const area = node("section", "fiscal-accum-breakdown");
    area.appendChild(node("h4", "", "Acumuladores fiscais vinculados à conta " + row.conta));
    if (!items.length) {
      area.appendChild(node("p", "fiscal-disclaimer", "Nenhum acumulador informado."));
      return area;
    }
    const wrap = node("div", "fiscal-accum-list");
    for (const item of items) {
      const line = node("div", "fiscal-accum-line");
      line.appendChild(node("strong", "fiscal-accum-code", item.codigo));
      line.appendChild(node("span", "fiscal-accum-desc", item.descricao || "Descrição não informada"));
      if (item.valor !== null) line.appendChild(node("span", "fiscal-money fiscal-accum-amount", money.format(item.valor)));
      wrap.appendChild(line);
    }
    area.appendChild(wrap);
    return area;
  }
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
    const filial = byId("fiscalFilialCodigo").value.trim();
    const empresaCodigo = byId("fiscalEmpresaCodigo").value.trim();
    if (filial && !/^\d+$/.test(filial)) throw new Error("A filial deve conter apenas números.");
    if (empresaCodigo && !/^\d+$/.test(empresaCodigo)) throw new Error("O código da empresa deve conter apenas números.");
    body.append("filial", filial);
    body.append("empresa_codigo", empresaCodigo);
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
    search.value = "";
    resultsCount.textContent = "";
    results.hidden = true;
    details.hidden = true;
    details.replaceChildren();
    tableBody.replaceChildren();
    setMessage("");
    submit.disabled = false;
    download.disabled = false;
  }

  function normalizeSearch(value) {
    return String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  }
  function filteredRows() {
    const contas = data?.contas || [];
    const term = normalizeSearch(search.value);
    return contas.filter(row => {
      const matchesStatus = filter.value === "revisar" ? ["REVISAR", "AUSENTE NO CONTÁBIL"].includes(row.situacao)
        : filter.value === "alertas" ? row.situacao === "CONFERE COM ALERTAS"
        : filter.value === "bate" ? row.situacao === "CONFERE" : true;
      if (!matchesStatus || !term) return matchesStatus;
      const key = [row.conta, row.descricao, row.tipo, row.acumuladores,
        ...accumulatorRows(row).flatMap(acc => [acc.codigo, acc.descricao])].join(" ");
      return normalizeSearch(key).includes(term);
    });
  }
  function renderDetails(row) {
    details.replaceChildren();
    if (!row) { details.hidden = true; return; }
    details.hidden = false;
    details.setAttribute("role", "region");
    details.setAttribute("aria-label", "Detalhes da conta " + row.conta);
    const heading = node("div", "fiscal-detail-heading");
    const summary = node("div");
    summary.appendChild(node("h3", "", "Conta " + row.conta + " · " + (row.descricao || "Sem descrição")));
    summary.appendChild(node("p", "", "Tipo de movimento: " + row.tipo));
    heading.appendChild(summary);
    const headingActions = node("div", "fiscal-detail-heading-actions");
    headingActions.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(row.situacao), statusLabels[row.situacao] || row.situacao));
    const close = node("button", "fiscal-detail-close", "Fechar detalhes");
    close.type = "button";
    close.addEventListener("click", () => {
      selectedKey = "";
      renderTable();
    });
    headingActions.appendChild(close);
    heading.appendChild(headingActions);
    details.appendChild(heading);
    details.appendChild(accumulatorBreakdown(row));

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
    details.appendChild(node("p", "fiscal-disclaimer", "Diferença = contábil considerado menos fiscal. O contábil considerado é uma classificação preliminar por históricos e coincidência de valores, não uma conciliação documental definitiva."));
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
    const total = (data?.contas || []).length;
    resultsCount.textContent = `Exibindo ${rows.length} de ${total} contas. Abra uma conta para consultar os valores detalhados e os lançamentos.`;
    byId("fiscal242Empty").hidden = rows.length > 0;
    if (!rows.some(row => keyOf(row) === selectedKey)) selectedKey = "";
    rows.forEach(row => {
      const tr = node("tr");
      const id = keyOf(row);
      if (id === selectedKey) tr.classList.add("selected");
      const account = cell(tr, "", "fiscal-account");
      const accountGroup = node("div", "fiscal-account-group");
      const button = node("button", "fiscal-account-link", row.conta);
      button.type = "button";
      button.setAttribute("aria-label", (id === selectedKey ? "Fechar detalhes da conta " : "Ver detalhes da conta ") + row.conta);
      button.setAttribute("aria-expanded", String(id === selectedKey));
      button.setAttribute("aria-controls", "fiscal242Detail");
      button.addEventListener("click", () => {
        selectedKey = selectedKey === id ? "" : id;
        renderTable();
        if (selectedKey) details.scrollIntoView?.({behavior:"smooth", block:"nearest"});
      });
      accountGroup.appendChild(button);
      accountGroup.appendChild(node("span", "fiscal-account-type", row.tipo || ""));
      account.appendChild(accountGroup);
      account.appendChild(node("div", "fiscal-account-description", row.descricao || "Descrição não informada"));
      const accumulatorCell = cell(tr, "", "fiscal-accum-cell");
      accumulatorCell.appendChild(accumulatorTags(row));
      cell(tr, money.format(row.fiscal), "fiscal-money");
      cell(tr, money.format(row.diferenca), "fiscal-money fiscal-difference");
      const td = cell(tr, "");
      td.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(row.situacao), statusLabels[row.situacao] || row.situacao));
      tableBody.appendChild(tr);
    });
    renderDetails(rows.find(row => keyOf(row) === selectedKey) || null);
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
    search.value = "";
    renderTable();
  }
  filter.addEventListener("change", renderTable);
  search.addEventListener("input", renderTable);
  function showSelectedFile(inputId, labelId) {
    const input = byId(inputId);
    const label = byId(labelId);
    if (!input || !label) return;
    const file = input.files?.[0];
    label.textContent = file ? file.name : "Nenhum arquivo selecionado";
    label.dataset.ready = file ? "true" : "false";
  }
  function syncFileNames() {
    showSelectedFile("fiscal242Acumuladores", "fiscal242AcumuladoresName");
    showSelectedFile("fiscal242Razao", "fiscal242RazaoName");
  }
  form.querySelectorAll("input[type=file], #fiscalEmpresaCodigo, #fiscalFilialCodigo").forEach(input =>
    input.addEventListener("change", () => { clearState(); syncFileNames(); })
  );
  syncFileNames();
  form.addEventListener("submit", async event => {
    event.preventDefault();
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
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/preview", {
        method:"POST", body, signal: controller.signal
      });
      if (!response.ok) throw new Error(await responseError(response));
      const report = await response.json();
      if (controller.signal.aborted) return;
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
    if (!data || !previewBody) return;
    const body = previewBody;
    download.disabled = true;
    setMessage("Preparando relatório Excel…", "loading");
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/exportar", {
        method:"POST", body
      });
      if (!response.ok) throw new Error(await responseError(response));
      if (previewBody !== body) return;
      const code = byId("fiscalEmpresaCodigo").value.trim() || "GERAL";
      await downloadBlob(response, `RAZYNC_${code}_CONFERENCIA_FISCAL.xlsx`);
      setMessage("Relatório Excel gerado.", "success");
    } catch (error) {
      setMessage(error.message || "Não foi possível gerar o Excel.", "error");
    } finally {
      download.disabled = false;
    }
  });
})();
