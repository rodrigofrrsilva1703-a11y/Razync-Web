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
  const aiExport = byId("fiscal242AIExport");
  const aiInlineStatus = byId("fiscal242AIStatus");
  let aiReport = null;
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
        ? (previewBody ? "Gemini conectado. Clique em Gerar análise." : "Gemini conectado. Faça a conferência para analisar as diferenças.")
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

  aiExport.addEventListener("click", async () => {
    if (!aiReport?.analises?.length || !data) return;
    const current = aiReport;
    const company = String(data.empresa_nome || "GERAL");
    aiExport.disabled = true;
    aiMessage.textContent = "Preparando a planilha Excel com o parecer e os lançamentos citados…";
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/ia/exportar", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
          empresa_nome: company,
          filial: data.filial_aplicada || "",
          analises: current.analises
        })
      });
      if (!response.ok) throw new Error(await responseError(response));
      if (aiReport !== current) return;
      const safeName = company.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0,48) || "GERAL";
      await downloadBlob(response, "RAZYNC_" + safeName + "_ANALISE_GEMINI.xlsx");
      aiMessage.textContent = "Excel gerado com sucesso. O arquivo inclui análises, acumuladores e lançamentos citados.";
    } catch (error) {
      if (aiReport === current) aiMessage.textContent = error.message || "Não foi possível exportar a análise.";
    } finally {
      aiExport.disabled = aiReport !== current || !aiReport?.analises?.length;
    }
  });

  function renderNarrative(textValue) {
    const wrap = node("div", "fiscal-ai-narrative");
    const segments = String(textValue || "").trim().split(/\n\s*\n/).map(x => x.trim()).filter(Boolean);
    const sectionTitles = ["O que foi encontrado", "Análise da diferença", "Possíveis causas", "Limitações e cuidados"];
    if (segments.length < 3) {
      wrap.appendChild(node("p", "fiscal-ai-paragraph", String(textValue || "")));
      return wrap;
    }
    segments.forEach((paragraph, index) => {
      const section = node("section", "fiscal-ai-narrative-section");
      const heading = node("h6", "", sectionTitles[index] || "Observação adicional");
      section.append(heading, node("p", "", paragraph));
      wrap.appendChild(section);
    });
    return wrap;
  }
  function renderChecklist(textValue) {
    const wrap = node("div", "fiscal-ai-steps");
    const steps = String(textValue || "").trim().split(/\n(?=\s*\d+[.)]\s+)/)
      .map(x => x.trim()).filter(Boolean);
    if (steps.length < 2 || !steps.every(x => /^\d+[.)]\s+/.test(x))) {
      wrap.appendChild(node("p", "fiscal-ai-paragraph", String(textValue || "")));
      return wrap;
    }
    const list = node("ol", "fiscal-ai-checklist");
    steps.forEach(step => {
      const item = node("li", "", step.replace(/^\d+[.)]\s+/, ""));
      list.appendChild(item);
    });
    wrap.appendChild(list);
    return wrap;
  }
  aiButton.addEventListener("click", async () => {
    if (!previewBody || !aiConfigured) return;
    aiReport = null;
    aiExport.disabled = true;
    aiController?.abort(); const controller = new AbortController(); aiController = controller;
    const snapshot = previewBody; aiButton.disabled = true; aiResult.replaceChildren();
    aiResult.setAttribute("aria-busy", "true");
    aiMessage.textContent = "Analisando lançamentos e diferenças com Gemini…";
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/ia", {method:"POST",body:snapshot,signal:controller.signal});
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      if (controller.signal.aborted || previewBody !== snapshot) return;
      aiReport = result;
      aiExport.disabled = !(Array.isArray(result.analises) && result.analises.length);
      aiInlineStatus.textContent = result.analises?.length
        ? "Análise pronta. Abra o painel para ler ou exportar para Excel."
        : "Gemini concluiu a análise. Não foram identificadas contas a explicar.";
      for (const item of result.analises || []) {
        const card = node("article", "fiscal-ai-card");
        const heading = node("div", "fiscal-ai-card-heading");
        const title = node("div", "fiscal-ai-card-title");
        title.append(node("span", "fiscal-ai-card-eyebrow", "PARECER POR CONTA"), node("h4", "", `Conta ${item.conta}`));
        if (item.descricao) title.appendChild(node("p", "fiscal-ai-card-description", item.descricao));
        const metadata = node("div", "fiscal-ai-card-meta");
        metadata.appendChild(node("span", "fiscal-ai-type", item.tipo));
        if (item.situacao) metadata.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(item.situacao), statusLabels[item.situacao] || item.situacao));
        heading.append(title, metadata);
        const officialRow = (data?.contas || []).find(row => keyOf(row) === keyOf(item)) || item;
        const accumulatorInfo = accumulatorBreakdown(officialRow);
        const analysis = node("section", "fiscal-ai-analysis");
        analysis.append(node("h5", "", "Análise da conta"), renderNarrative(item.explicacao));
        const review = node("section", "fiscal-ai-review");
        review.append(node("h5", "", "Verificações recomendadas"), renderChecklist(item.verificar));
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
        card.appendChild(accumulatorInfo);
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
      if (!controller.signal.aborted && previewBody === snapshot) {
        aiMessage.textContent = error.message || "Não foi possível gerar a análise.";
        aiInlineStatus.textContent = "A análise não foi concluída. Confira o painel e tente novamente.";
      }
    } finally {
      if (aiController === controller) {
        aiResult.setAttribute("aria-busy", "false");
        aiController = null;
        aiButton.disabled = !aiConfigured || !previewBody;
      }
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
    if (filial && !/^\d+$/.test(filial)) throw new Error("A filial deve conter apenas números.");
    body.append("filial", filial);
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
    aiReport = null;
    aiExport.disabled = true;
    aiInlineStatus.textContent = "Faça uma conferência para iniciar a análise.";
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
    const summary = node("div", "fiscal-detail-title");
    summary.appendChild(node("span", "fiscal-section-eyebrow", "DETALHAMENTO CONTÁBIL"));
    summary.appendChild(node("h3", "", "Conta " + row.conta));
    summary.appendChild(node("p", "", (row.descricao || "Sem descrição") + " · " + row.tipo));
    const headingActions = node("div", "fiscal-detail-heading-actions");
    headingActions.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(row.situacao),
      statusLabels[row.situacao] || row.situacao));
    const close = node("button", "fiscal-detail-close", "Fechar painel");
    close.type = "button";
    close.addEventListener("click", () => { selectedKey = ""; renderTable(); });
    headingActions.appendChild(close);
    heading.append(summary, headingActions);
    details.appendChild(heading);

    const metrics = node("div", "fiscal-detail-metrics");
    [
      ["Valor fiscal", row.fiscal, "fiscal"],
      ["Contábil considerado", row.contabil, "accounting"],
      ["Total do Razão", row.total_conta, "ledger"],
      ["Diferença", row.diferenca, "difference"]
    ].forEach(([label, amount, style]) => {
      const card = node("div", "fiscal-detail-metric fiscal-detail-metric-" + style);
      card.appendChild(node("small", "", label));
      card.appendChild(node("strong", "", money.format(Number(amount || 0))));
      if (style === "difference") {
        card.appendChild(node("span", "fiscal-detail-metric-hint",
          Math.abs(Number(amount || 0)) <= 0.01 ? "Sem diferença aritmética" : "Contábil considerado − fiscal"));
      }
      metrics.appendChild(card);
    });
    details.appendChild(metrics);

    const explanation = node("p", "fiscal-disclaimer fiscal-detail-explanation",
      "Valor contábil considerado: lançamentos classificados pelo sistema como compatíveis com o fiscal. " +
      "O total do Razão pode incluir outros movimentos. O fechamento dos valores não comprova sozinho a origem fiscal.");
    details.appendChild(explanation);
    details.appendChild(accumulatorBreakdown(row));

    if (row.extras || row.sem_evidencia) {
      const notices = node("div", "fiscal-detail-notices");
      if (row.extras) notices.appendChild(node("p", "", row.extras + " lançamento(s) com indício de movimento não fiscal. Confira o histórico e a contrapartida."));
      if (row.sem_evidencia) notices.appendChild(node("p", "", row.sem_evidencia + " lançamento(s) fecham somente pelo valor, sem evidência fiscal suficiente no histórico."));
      details.appendChild(notices);
    }

    const wantedCredit = row.tipo === "SAÍDAS";
    const movimentos = (data.lancamentos || []).filter(item =>
      item.conta === row.conta && String(item.natureza).includes(wantedCredit ? "CRÉDITO" : "DÉBITO")
    );
    const ledger = node("details", "fiscal-ledger-disclosure");
    const trigger = node("summary", "fiscal-ledger-toggle");
    const intro = node("span", "fiscal-ledger-toggle-copy");
    intro.appendChild(node("strong", "", "Movimentos do Razão"));
    intro.appendChild(node("small", "", movimentos.length + " lançamento(s) · " + (wantedCredit ? "créditos" : "débitos") + " examinados"));
    trigger.appendChild(intro);
    trigger.appendChild(node("span", "fiscal-ledger-toggle-icon", "⌄"));
    ledger.appendChild(trigger);
    if (!movimentos.length) {
      ledger.appendChild(node("p", "fiscal-empty", "Não há movimentos dessa natureza no Razão enviado."));
    } else {
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
        const classification = mov.classificacao === "ALERTA - NÃO FISCAL" ? "Possível movimento não fiscal"
          : mov.classificacao === "FECHAMENTO POR VALOR - VALIDAR" ? "Fecha por valor · validar" : "Fiscal provável";
        cell(tr, classification);
        body.appendChild(tr);
      });
      table.appendChild(body);
      wrap.appendChild(table);
      ledger.appendChild(wrap);
      if (movimentos.length > 200) {
        ledger.appendChild(node("p", "fiscal-empty",
          "Exibindo 200 de " + movimentos.length + " lançamentos. Consulte o Razão original para verificar os demais."));
      }
    }
    details.appendChild(ledger);
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
      const tr = node("tr", "fiscal-result-row fiscal-result-row-" + statusClass(row.situacao));
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
      button.appendChild(node("span", "fiscal-account-chevron", "›"));
      accountGroup.appendChild(button);
      accountGroup.appendChild(node("span", "fiscal-account-type", row.tipo || ""));
      account.appendChild(accountGroup);
      account.appendChild(node("div", "fiscal-account-description", row.descricao || "Descrição não informada"));
      const accumulatorCell = cell(tr, "", "fiscal-accum-cell");
      accumulatorCell.dataset.label = "Acumuladores";
      accumulatorCell.appendChild(accumulatorTags(row));
      const fiscalValue = cell(tr, money.format(row.fiscal), "fiscal-money fiscal-money-fiscal");
      fiscalValue.dataset.label = "Fiscal";
      const accountingValue = cell(tr, money.format(row.contabil), "fiscal-money fiscal-money-accounting");
      accountingValue.dataset.label = "Contábil";
      const diferenca = cell(tr, money.format(row.diferenca), "fiscal-money fiscal-difference");
      diferenca.dataset.label = "Diferença";
      if (Math.abs(Number(row.diferenca || 0)) <= 0.01) diferenca.classList.add("fiscal-difference-zero");
      const td = cell(tr, "", "fiscal-situation-cell");
      td.dataset.label = "Situação";
      td.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(row.situacao), statusLabels[row.situacao] || row.situacao));
      tableBody.appendChild(tr);
    });
    renderDetails(rows.find(row => keyOf(row) === selectedKey) || null);
  }

  function renderResponse(report) {
    data = report;
    const detected = report.empresa_nome || "";
    byId("fiscal242CompanyName").textContent = detected || "Nome não encontrado nos cabeçalhos";
    const fiscais = Boolean(report.empresa_fiscal);
    const contabil = Boolean(report.empresa_razao);
    byId("fiscal242CompanySource").textContent =
      fiscais && contabil ? "Nome confirmado no Resumo por Acumulador e no Razão." :
      (fiscais || contabil) ? "Nome encontrado em apenas um dos relatórios. Confira o outro arquivo." :
      "Não foi possível confirmar a empresa automaticamente. Verifique os arquivos enviados.";
    byId("fiscal242Total").textContent = report.resumo.total;
    byId("fiscal242Matches").textContent = report.resumo.conferem;
    byId("fiscal242Alerts").textContent = report.resumo.com_alertas;
    byId("fiscal242Pending").textContent = report.resumo.revisar;
    const totalContas = Math.max(1, Number(report.resumo.total || 0));
    [
      ["fiscal242ProgressMatches", report.resumo.conferem, "Batendo"],
      ["fiscal242ProgressAlerts", report.resumo.com_alertas, "Com alertas"],
      ["fiscal242ProgressPending", report.resumo.revisar, "Para revisar"]
    ].forEach(([id, count, label]) => {
      const bar = byId(id);
      const percentage = Math.max(0, Math.min(100, 100 * Number(count || 0) / totalContas));
      bar.style.width = percentage + "%";
      bar.setAttribute("aria-label", label + ": " + Number(count || 0) + " conta(s)");
    });
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
    aiInlineStatus.textContent = "Conferência pronta. Use a análise inteligente para revisar diferenças e alertas.";
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
  form.querySelectorAll("input[type=file], #fiscalFilialCodigo").forEach(input =>
    input.addEventListener("change", () => { clearState(); syncFileNames(); })
  );
  syncFileNames();
  form.addEventListener("submit", async event => {
    event.preventDefault();
    let body;
    try { body = buildFormData(); } catch (error) { setMessage(error.message, "error"); return; }
    aiController?.abort(); aiController = null; aiButton.disabled = true; aiResult.replaceChildren();
    aiReport = null; aiExport.disabled = true;
    aiInlineStatus.textContent = "Preparando uma nova conferência.";
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
      const nome = String(data.empresa_nome || "GERAL")
        .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
        .replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0,60) || "GERAL";
      await downloadBlob(response, `RAZYNC_${nome}_CONFERENCIA_FISCAL.xlsx`);
      setMessage("Relatório Excel gerado.", "success");
    } catch (error) {
      setMessage(error.message || "Não foi possível gerar o Excel.", "error");
    } finally {
      download.disabled = false;
    }
  });
})();
