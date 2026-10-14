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
  let tableSort = {key:"", descending:true};
  let pendingRequest = null;

  const byId = id => document.getElementById(id);
  const aiButton = byId("fiscal242AI");
  const aiMessage = byId("fiscal242AIMessage");
  const aiResult = byId("fiscal242AIResult");
  const aiExport = byId("fiscal242AIExport");
  const aiInlineStatus = byId("fiscal242AIStatus");
  const aiProvider = byId("fiscal242AIProvider");
  const aiToolbar = byId("fiscal242AIToolbar");
  const aiTotal = byId("fiscal242AITotal");
  const aiSearch = byId("fiscal242AISearch");
  const aiFilter = byId("fiscal242AIFilter");
  const aiCount = byId("fiscal242AICount");
  const aiEmpty = byId("fiscal242AIEmpty");
  const aiReader = byId("fiscal242AIReader");
  const aiAccounts = byId("fiscal242AIAccounts");
  let activeAIKey = "";
  const usageButton = byId("fiscal242UsageButton");
  const usageDialog = byId("fiscal242UsageDialog");
  const usageContent = byId("fiscal242UsageContent");
  const usageMessage = byId("fiscal242UsageMessage");
  const usageRefresh = byId("fiscal242UsageRefresh");
  const usageNumber = new Intl.NumberFormat("pt-BR");
  let usageController = null;
  const loadingPanel = byId("fiscal242AILoading");
  const loadingMeter = byId("fiscal242LoadingMeter");
  let loadingCounts = {done:0, total:0};
  function showAIProgress(phase, done = loadingCounts.done, total = loadingCounts.total, waiting = "") {
    loadingCounts = {done, total};
    loadingPanel.hidden = false;
    loadingPanel.dataset.phase = phase;
    const titles = {preparing:"Preparando a análise", analyzing:"Analisando contas e evidências", waiting:"Aguardando disponibilidade da IA", complete:"Pareceres prontos", partial:"Análise parcialmente concluída", cancelled:"Análise cancelada", error:"Não foi possível concluir a análise"};
    byId("fiscal242LoadingTitle").textContent = titles[phase];
    byId("fiscal242LoadingCaption").textContent = waiting || ({preparing:"Organizando o contexto das contas com pendências.", analyzing:"Os resultados concluídos já podem ser consultados abaixo.", complete:"Abra uma conta para ler o parecer e as verificações recomendadas.", partial:"Os pareceres recebidos foram mantidos. Você pode repetir os lotes pendentes.", cancelled:"Os valores da conferência foram preservados.", error:"Consulte os detalhes do processamento e tente novamente."}[phase] || "Os resultados já recebidos continuam disponíveis.");
    const active = ["preparing", "analyzing", "waiting"].includes(phase);
    loadingPanel.querySelector(".fiscal-ai-loading-orbit span").textContent = active ? "✦" : phase === "complete" ? "✓" : phase === "cancelled" ? "−" : "!";
    byId("fiscal242LoadingTime").hidden = !active;
    loadingPanel.setAttribute("aria-busy", String(active));
    byId("fiscal242LoadingCount").textContent = total > 0 ? done + " de " + total + " grupos concluídos" : active ? "Preparando os grupos de contas…" : "Processamento encerrado";
    byId("fiscal242LoadingFill").style.width = total > 0 ? Math.min(100, 100 * done / total) + "%" : "";
    if (total > 0) {
      loadingMeter.setAttribute("aria-valuemin", "0"); loadingMeter.setAttribute("aria-valuemax", String(total)); loadingMeter.setAttribute("aria-valuenow", String(done));
    } else {
      loadingMeter.removeAttribute("aria-valuemin"); loadingMeter.removeAttribute("aria-valuemax"); loadingMeter.removeAttribute("aria-valuenow");
    }
    const stage = phase === "preparing" ? 0 : active ? 1 : 2;
    [...loadingPanel.querySelectorAll("[data-loading-stage]")].forEach((el, index) => {
      el.classList.toggle("is-done", index < stage || phase === "complete");
      el.classList.toggle("is-current", active && index === stage);
      if (active && index === stage) el.setAttribute("aria-current", "step"); else el.removeAttribute("aria-current");
    });
  }

  function usageTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" :
      date.toLocaleString("pt-BR", {day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"});
  }
  function renderUsage(data) {
    usageContent.replaceChildren();
    const top = node("p", "fiscal-usage-period",
      "Data de referência (UTC): " + (data.data_utc || "—") +
      " · Registro desde: " + usageTime(data.desde_utc));
    usageContent.appendChild(top);
    (data.provedores || []).forEach(provider => {
      const card = node("section", "fiscal-usage-provider");
      const head = node("div", "fiscal-usage-provider-head");
      head.appendChild(node("strong", "", provider.nome || provider.id));
      head.appendChild(node("span",
        "fiscal-usage-config " + (provider.configurado ? "is-configured" : ""),
        provider.configurado ? "Configurado" : "Não configurado"));
      card.appendChild(head);
      const metrics = node("div", "fiscal-usage-metrics");
      [
        ["Chamadas", provider.chamadas ?? 0],
        ["Respostas da API", provider.respostas ?? 0],
        ["Falhas", provider.falhas ?? 0],
        ["Tokens informados", provider.tokens_informados ?? 0]
      ].forEach(([label, count]) => {
        const metric = node("div", "fiscal-usage-metric");
        metric.appendChild(node("small", "", label));
        metric.appendChild(node("strong", "", usageNumber.format(Number(count) || 0)));
        metrics.appendChild(metric);
      });
      card.appendChild(metrics);
      const limits = provider.controle_local || {};
      card.appendChild(node("p", "fiscal-usage-limit",
        "Cota diária e saldo real: não disponíveis nesta consulta. Controle cautelar do Razync: " +
        (limits.requisicoes_minuto ?? "—") + " chamadas/min" +
        (limits.tokens_minuto ? " e " + usageNumber.format(limits.tokens_minuto) + " tokens/min." : ".")
      ));
      if (provider.respostas_sem_tokens) card.appendChild(
        node("p", "fiscal-usage-note",
          provider.respostas_sem_tokens + " resposta(s) sem contagem de tokens enviada pelo provedor.")
      );
      const models = Array.isArray(provider.modelos) ? provider.modelos : [];
      if (models.length) {
        const details = node("details", "fiscal-usage-models");
        details.appendChild(node("summary", "", "Detalhar uso por modelo (" + models.length + ")"));
        models.forEach(model => {
          const line = node("div", "fiscal-usage-model");
          line.appendChild(node("strong", "", model.modelo || "Modelo não identificado"));
          line.appendChild(node("span", "",
            "Chamadas " + (model.chamadas || 0) + " · Respostas " + (model.respostas || 0) +
            " · Falhas " + (model.falhas || 0)));
          line.appendChild(node("small", "", "Última chamada: " + usageTime(model.ultima_chamada)));
          details.appendChild(line);
        });
        card.appendChild(details);
      }
      usageContent.appendChild(card);
    });
    usageContent.appendChild(node("p", "fiscal-usage-disclaimer",
      data.observacao || "Os saldos reais devem ser conferidos diretamente nos provedores."));
  }
  async function loadUsage() {
    usageController?.abort();
    const controller = new AbortController();
    usageController = controller;
    const timeout = setTimeout(() => controller.abort(), 12000);
    usageRefresh.disabled = true;
    usageMessage.textContent = "Consultando consumo registrado pelo Razync…";
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/ia/uso", {
        cache:"no-store", signal:controller.signal
      });
      if (!response.ok) throw new Error("O relatório não pôde ser consultado agora.");
      const report = await response.json();
      if (usageController !== controller || !usageDialog.open) return;
      renderUsage(report);
      usageMessage.textContent = "Consumo local atualizado. Não representa saldo confirmado das cotas.";
    } catch (error) {
      if (usageController === controller && usageDialog.open) {
        usageMessage.textContent = "Não foi possível consultar o relatório. Tente atualizar novamente.";
      }
    } finally {
      clearTimeout(timeout);
      if (usageController === controller) {
        usageController = null;
        usageRefresh.disabled = false;
      }
    }
  }
  usageButton.addEventListener("click", () => {
    if (!usageDialog.open) {
      usageDialog.showModal();
      usageButton.setAttribute("aria-expanded", "true");
      loadUsage();
    }
  });
  usageDialog.addEventListener("close", () => {
    usageController?.abort();
    usageButton.setAttribute("aria-expanded", "false");
    usageButton.focus();
  });
  usageRefresh.addEventListener("click", loadUsage);

  let aiCards = [];
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
      const providerName = result.provedores?.length > 1 ? result.provedores.map(p => p === "groq" ? "Groq" : p === "gemini" ? "Gemini" : "OpenRouter").join(" + ") : result.cooperacao === true ? "Gemini + Groq" : result.provedor === "groq" ? "GroqCloud" : result.provedor === "openrouter" ? "OpenRouter" : "Gemini";
      aiProvider.textContent = aiConfigured
        ? (result.cooperacao === true ? providerName + " · gratuito" : result.gratuito === true && result.provedor === "openrouter" ? "OpenRouter · gratuito" : result.gratuito === true && result.provedor === "groq" ? "GroqCloud · gratuito" : providerName)
        : "IA";
      aiButton.disabled = !aiConfigured || !previewBody || Boolean(aiController);
      if (!aiController && !aiResult.children.length) aiMessage.textContent = aiConfigured
        ? (previewBody ? providerName + " configurado. Clique em Analisar diferenças com IA." : providerName + " configurado no servidor. Faça a conferência para solicitar a análise.")
        : "IA ainda não configurada. Confira a chave e as configurações do provedor escolhido no Railway e clique em Atualizar conexão.";
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
  byId("fiscal242UsageActions").appendChild(refreshConnection);
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
      await downloadBlob(response, "RAZYNC_" + safeName + "_ANALISE_IA.xlsx");
      aiMessage.textContent = "Excel gerado com sucesso. O arquivo inclui análises, acumuladores e lançamentos citados.";
    } catch (error) {
      if (aiReport === current) aiMessage.textContent = error.message || "Não foi possível exportar a análise.";
    } finally {
      aiExport.disabled = aiReport !== current || !aiReport?.analises?.length;
    }
  });

  function renderNarrative(textValue) {
    const wrap = node("div", "fiscal-ai-narrative");
    // A apresentação é a mesma para todos os provedores. Não atribuir títulos
    // a parágrafos apenas pela posição: a IA pode enviar outra estrutura.
    const segments = String(textValue || "").trim().replace(/\\n/g, "\n")
      .replace(/\s+(?=(?:\*\*)?(?:Fatos|Diferença|Hipóteses|Limitações)(?:\*\*)?\s*:)/gi, "\n").split(/\r?\n+/)
      .map(x => x.trim()).filter(Boolean);
    segments.forEach(paragraph => {
      const labelled = paragraph.match(/^(?:\*\*)?(Fatos|Diferença|Hipóteses|Limitações)(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.*)$/i);
      if (!labelled) { wrap.appendChild(node("p", "fiscal-ai-paragraph", paragraph)); return; }
      const section = node("section", "fiscal-ai-finding");
      section.append(node("h6", "", labelled[1]), node("p", "fiscal-ai-paragraph", labelled[2]));
      wrap.appendChild(section);
    });
    return wrap;
  }
  function renderChecklist(textValue) {
    const wrap = node("div", "fiscal-ai-steps");
    const text = String(textValue || "").trim().replace(/\\n/g, "\n")
      .replace(/^(?:#{1,6}\s*)?[*_]{0,2}(?:O que conferir|Verificaç[õo]es(?: recomendadas)?|Próximos passos)[*_]{0,2}\s*:[*_]{0,2}\s*/i, "")
      .replace(/(^|\n)\s*[*_]{1,2}(?=\d+[.)])/g, "$1")
      .replace(/(\d+[.)])[*_]{1,2}\s*/g, "$1 ")
      .replace(/([^\n])\s+(?=[2-9][.)]\s+[A-ZÀ-Ý])/g, "$1\n");
    const marker = /^(?:\d+[.)]|[-*•])\s+/;
    const steps = [];
    if (marker.test(text)) {
      text.split(/\r?\n/).forEach(line => {
        const trimmed = line.trim();
        if (!trimmed) return;
        if (marker.test(trimmed)) steps.push(trimmed.replace(marker, ""));
        else if (steps.length) steps[steps.length - 1] += "\n" + trimmed;
      });
    } else if (text) steps.push(text);
    const list = node("ol", "fiscal-ai-checklist");
    steps.forEach(step => {
      const item = node("li", "", step);
      list.appendChild(item);
    });
    wrap.appendChild(list);
    return wrap;
  }
  function differenceMeaning(amount) {
    const value = Number(amount || 0);
    if (Math.abs(value) <= 0.01) return "Os valores fiscal e contábil considerado são iguais. Confira os alertas e a origem dos lançamentos.";
    return "Contábil considerado " + money.format(Math.abs(value)) +
      (value < 0 ? " abaixo do fiscal." : " acima do fiscal.");
  }
  function aiSourceLabel(item) {
    const names = {groq:"Groq",gemini:"Gemini",openrouter:"OpenRouter"};
    const name = names[item.provedor] || "IA não identificada";
    return name + (item.modelo_usado ? " · " + item.modelo_usado : "");
  }
  function responsePoints(textValue) {
    // Quebras de linha e frases completas; números monetários ficam intactos.
    return String(textValue || "").trim().replace(/\\n/g, "\n")
      .split(/\r?\n+|(?<=[.!?])\s+(?=[A-ZÀ-Ý])/u)
      .map(text => text.trim().replace(/^(?:[-*•]|\d+[.)])\s+/, ""))
      .filter(Boolean);
  }
  function renderAIFindings(item) {
    const analysis = node("section", "fiscal-ai-analysis");
    const reading = item.parecer?.leitura_comparacao;
    if (reading?.resultado) {
      analysis.classList.add("fiscal-ai-organized-analysis");
      analysis.append(node("h5", "", "Resultado da conta"), node("p", "fiscal-ai-conclusion", reading.resultado));
      analysis.appendChild(node("h5", "", "O que os lançamentos mostram"));
      const facts = node("ul", "fiscal-ai-finding-list");
      for (const observation of reading.observacoes || []) facts.appendChild(node("li", "", observation));
      analysis.appendChild(facts);
      const interpretation = item.parecer?.analise_exibicao;
      if (interpretation) {
        analysis.append(node("h5", "", "O que permanece em aberto"), node("p", "fiscal-ai-open-question", interpretation));
      }
      analysis.appendChild(node("p", "fiscal-ai-comparison-rule", reading.criterio));
      return analysis;
    }
    analysis.appendChild(node("h5", "", "Resumo"));
    if (item.valores?.diferenca !== undefined && item.valores?.diferenca !== null) {
      analysis.appendChild(node("p", "fiscal-difference-reading", differenceMeaning(item.valores.diferenca)));
    }
    if (reading?.explicacoes?.length) {
      const context = node("div", "fiscal-ai-comparison-reading");
      for (const explanation of reading.explicacoes) context.appendChild(node("p", "", explanation));
      analysis.append(context, node("h5", "fiscal-ai-interpretation-title", "Análise da IA"));
    }
    const text = item.parecer?.analise_exibicao ?? (item.parecer?.interpretacao || item.parecer?.hipoteses || item.explicacao);
    const points = node("ul", "fiscal-ai-response-points");
    const observations = reading?.explicacoes?.length ? "" : item.parecer?.observacoes;
    for (const point of [...responsePoints(observations), ...responsePoints(text)]) points.appendChild(node("li", "", point));
    if (!points.children.length) points.appendChild(node("li", "", "Nenhuma interpretação disponível para esta conta."));
    analysis.appendChild(points);
    return analysis;
  }
  function renderAIConsidered(item) {
    const rows = item.parecer?.leitura_comparacao?.considerados || [];
    if (!rows.length) return null;
    return renderAIDataTable(`Entraram na comparação (${rows.length})`,
      ["Referência", "Data", "Histórico", "Contrapartida", "Valor", "Critério"],
      rows.map(row => [row.referencia, row.data || "—", row.historico, row.contrapartida, row.valor_brl, row.motivo]), "fiscal-ai-considered");
  }
  function renderAIReviewSteps(item) {
    const instructions = item.parecer?.leitura_comparacao?.orientacoes;
    if (!instructions?.length) return renderChecklist(item.parecer?.verificacoes || item.verificar);
    const list = node("ol", "fiscal-ai-checklist fiscal-ai-explained-checklist");
    for (const instruction of instructions) {
      const step = node("li", "");
      const body = node("div", "");
      body.append(node("strong", "", instruction.acao), node("p", "fiscal-ai-step-purpose", instruction.objetivo));
      step.appendChild(body); list.appendChild(step);
    }
    return list;
  }
  function renderAIExcluded(item) {
    const rows = item.parecer?.leitura_comparacao?.excluidos || [];
    if (!rows.length) return null;
    return renderAIDataTable(`Movimentos fora da comparação (${rows.length})`,
      ["Referência", "Data", "Histórico", "Por que ficou fora", "Valor"],
      rows.map(row => [row.referencia, row.data || "—", row.historico, row.motivo, row.valor_brl]), "fiscal-ai-excluded");
  }
  function renderAILimits(item) {
    const limits = node("section", "fiscal-ai-limits");
    limits.appendChild(node("h5", "", item.parecer?.leitura_comparacao?.resultado ? "Para concluir a análise" : "Limitações"));
    const body = node("div", "fiscal-ai-limits-content");
    const missing = node("ul", "fiscal-ai-limit-points");
    const limitations = item.parecer?.informacoes_faltantes || [];
    for (const text of limitations) {
      if (item.parecer?.leitura_comparacao?.resultado && text === "A causa do alerta ou da diferença exige conferir os documentos e a natureza dos lançamentos.") continue;
      missing.appendChild(node("li", "", text));
    }
    if (missing.children.length) body.appendChild(missing);
    const coverage = item.parecer?.cobertura;
    if (coverage) body.appendChild(node("p", "fiscal-ai-source", `Contexto da IA: ${coverage.enviados} de ${coverage.disponiveis} lançamentos disponíveis nesta conta${coverage.parcial ? " · amostra parcial" : ""}${coverage.historicos_abreviados ? " · históricos abreviados" : ""}.`));
    const revised = item.parecer?.sugestoes_retiradas?.length || item.auditoria?.alertas?.length;
    if (revised && item.parecer?.analise_exibicao !== undefined) {
      body.appendChild(node("p", "fiscal-ai-quality-note", "Resposta revisada: sugestões sem apoio suficiente nas fontes foram desconsideradas na interpretação exibida. Os valores da conferência foram preservados."));
    }
    limits.appendChild(body);
    return limits;
  }
  function renderAIDataTable(title, headers, rows, className) {
    const section = node("section", "fiscal-ai-data " + className);
    section.appendChild(node("h5", "", title));
    const wrap = node("div", "fiscal-ai-data-scroll");
    const table = node("table", "fiscal-ai-data-table");
    const head = node("thead", ""), heading = node("tr", "");
    for (const label of headers) { const cell = node("th", "", label); cell.scope = "col"; heading.appendChild(cell); }
    head.appendChild(heading);
    const body = node("tbody", "");
    for (const values of rows) {
      const row = node("tr", "");
      values.forEach((value, index) => row.appendChild(node("td", ["Débito", "Crédito", "Valor fiscal", "Valor"].includes(headers[index]) ? "fiscal-ai-data-value" : "", value ?? "—")));
      body.appendChild(row);
    }
    table.append(head, body); wrap.appendChild(table); section.appendChild(wrap);
    return section;
  }
  function renderAIComposition(row) {
    const items = accumulatorRows(row);
    if (!items.length) return accumulatorBreakdown(row);
    return renderAIDataTable("Composição dos acumuladores", ["Acumulador", "Descrição", "Valor fiscal"],
      items.map(item => [item.codigo, item.descricao || "Descrição não informada", item.valor === null ? "—" : money.format(item.valor)]), "fiscal-ai-composition");
  }
  function renderAIEvidence(item) {
    return renderAIDataTable(`Lançamentos citados (${item.evidencias.length})`,
      ["Referência", "Data", "Histórico", "Contrapartida", "Débito", "Crédito"],
      item.evidencias.map(row => [row.referencia, row.data || "—", row.historico || "Histórico não informado",
        row.contrapartida || "—", money.format(Number(row.debito || 0)), money.format(Number(row.credito || 0))]), "fiscal-ai-evidence");
  }
  function renderAIEntries(entries) {
      for (const item of entries) {
        if (aiCards.some(entry => keyOf(entry.item) === keyOf(item))) continue;
        const card = node("article", "fiscal-ai-card fiscal-ai-account");
        card.classList.add("fiscal-card-arrive");
        card.addEventListener("animationend", () => card.classList.remove("fiscal-card-arrive"), {once:true});
        const heading = node("div", "fiscal-ai-card-heading fiscal-ai-account-summary");
        const title = node("div", "fiscal-ai-card-title");
        title.appendChild(node("h4", "", `Conta ${item.conta}`));
        if (item.descricao) title.appendChild(node("p", "fiscal-ai-card-description", item.descricao));
        const metadata = node("div", "fiscal-ai-card-meta");
        title.appendChild(node("p", "fiscal-ai-provider", aiSourceLabel(item)));
        if (item.tipo) metadata.appendChild(node("span", "fiscal-ai-type", item.tipo));
        if (item.situacao) metadata.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(item.situacao), statusLabels[item.situacao] || item.situacao));
        const compact = node("div", "fiscal-ai-account-compact");
        if (item.valores && item.valores.diferenca !== undefined && item.valores.diferenca !== null) {
          const preview = node("span", "fiscal-ai-account-difference");
          preview.append(node("small", "", "Diferença"), node("strong", "", money.format(Number(item.valores.diferenca) || 0)));
          compact.appendChild(preview);
        }
        heading.append(title, metadata, compact);
        const content = node("div", "fiscal-ai-account-content");
        const officialRow = (data?.contas || []).find(row => keyOf(row) === keyOf(item)) || item;
        const analysis = renderAIFindings(item);
        const review = node("section", "fiscal-ai-review");
        const reviewHeading = node("div", "fiscal-ai-section-heading");
        reviewHeading.appendChild(node("h5", "", "O que conferir"));
        review.append(reviewHeading, renderAIReviewSteps(item));
        if (item.valores) {
          const metrics = node("div", "fiscal-ai-values");
          [["Fiscal", "fiscal"], ["Total do Razão", "total_conta"],
           ["Contábil considerado", "contabil"]].forEach(([label, key]) => {
            const metric = node("div", "fiscal-ai-value");
            metric.append(node("small", "", label), node("strong", "", money.format(Number(item.valores[key] || 0))));
            metrics.appendChild(metric);
          });
          content.appendChild(metrics);
        }
        content.appendChild(analysis);
        const composition = renderAIComposition(officialRow);
        const reading = node("div", "fiscal-ai-reading");
        reading.appendChild(review);
        content.appendChild(reading);
        if (item.auditoria && item.parecer?.analise_exibicao === undefined) {
          const alerts = Array.isArray(item.auditoria.alertas) ? item.auditoria.alertas : [];
          const audit = node("section", "fiscal-ai-audit" + (alerts.length ? " has-alerts" : ""));
          audit.appendChild(node("strong", "", "Atenção às evidências"));
          for (const alert of alerts) audit.appendChild(node("p", "", String(alert)));
          if (alerts.length) content.appendChild(audit);
        }
        const evidence = node("section", "fiscal-ai-evidence-group");
        evidence.appendChild(node("h5", "", "Base da análise"));
        const considered = renderAIConsidered(item);
        if (considered) evidence.appendChild(considered);
        else if (item.evidencias?.length) evidence.appendChild(renderAIEvidence(item));
        const excluded = renderAIExcluded(item);
        if (excluded) evidence.appendChild(excluded);
        evidence.appendChild(composition);
        content.append(evidence, renderAILimits(item));
        card.append(heading, content);
        aiCards.push({item, card});
        aiResult.append(card);
      }
      for (const item of entries) {
        const existing = aiCards.find(entry => keyOf(entry.item) === keyOf(item));
        if (existing) aiResult.append(existing.card);
      }
      updateAIFilters();
    aiToolbar.hidden = aiCards.length === 0;
    aiTotal.textContent = aiCards.length ? "(" + aiCards.length + ")" : "";
  }
  function normalizeAISearch(value) {
    return String(value ?? "").normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  }
  function filterAIEntries(entries, query, filterStatus) {
    const searchText = normalizeAISearch(query);
    return entries.filter(({item}) => {
      const status = String(item.situacao || "");
      const category = ["REVISAR", "AUSENTE NO CONTÁBIL"].includes(status) ? "revisar"
        : status === "CONFERE COM ALERTAS" ? "alertas"
        : status === "CONFERE" ? "bate" : "outras";
      if (filterStatus !== "todas" && category !== filterStatus) return false;
      if (!searchText) return true;
      const evidencias = (item.evidencias || []).flatMap(e => [
        e.referencia, e.data, e.conta, e.contrapartida, e.historico
      ]);
      return normalizeAISearch([
        item.conta, item.descricao, item.tipo, status, item.explicacao,
        item.verificar, ...evidencias
      ].join(" ")).includes(searchText);
    });
  }
  function updateAIFilters() {
    const matching = new Set(filterAIEntries(aiCards, aiSearch.value, aiFilter.value));
    for (const entry of aiCards) entry.card.hidden = !matching.has(entry);
    aiCount.textContent = aiCards.length === matching.size
      ? aiCards.length + " conta(s)"
      : "Exibindo " + matching.size + " de " + aiCards.length;
    aiEmpty.hidden = matching.size > 0 || !aiCards.length;
    renderAIReader([...matching]);
  }
  function chooseAIKey(entries, activeKey) {
    return entries.some(entry => keyOf(entry.item) === activeKey) ? activeKey : entries.length ? keyOf(entries[0].item) : "";
  }
  function renderAIReader(matching) {
    const previousKey = activeAIKey;
    activeAIKey = chooseAIKey(matching, activeAIKey);
    if (previousKey !== activeAIKey) aiResult.scrollTop = 0;
    aiReader.hidden = matching.length === 0;
    aiAccounts.replaceChildren();
    matching.forEach(({item, card}) => {
      const selected = keyOf(item) === activeAIKey;
      card.classList.toggle("is-reading", selected);
      const button = node("button", "fiscal-ai-nav-account" + (selected ? " is-selected" : ""));
      button.type = "button";
      button.setAttribute("aria-pressed", String(selected));
      button.append(node("strong", "", "Conta " + item.conta), node("span", "fiscal-ai-nav-description", item.descricao || item.tipo || "Parecer da conta"));
      const footer = node("span", "fiscal-ai-nav-meta");
      footer.appendChild(node("small", "", statusLabels[item.situacao] || item.situacao || item.tipo));
      if (item.valores?.diferenca !== undefined) footer.appendChild(node("b", "", money.format(Number(item.valores.diferenca) || 0)));
      button.appendChild(footer);
      button.addEventListener("click", () => {activeAIKey = keyOf(item); renderAIReader(matching); aiResult.scrollTop = 0;});
      aiAccounts.appendChild(button);
    });
  }
  function clearAIAccounts() {
    loadingPanel.hidden = true;
    aiCards = [];
    activeAIKey = "";
    aiAccounts.replaceChildren();
    aiReader.hidden = true;
    aiToolbar.hidden = true;
    aiEmpty.hidden = true;
    aiSearch.value = "";
    aiFilter.value = "todas";
    aiCount.textContent = "";
    aiTotal.textContent = "";
  }
  aiSearch.addEventListener("input", updateAIFilters);
  aiFilter.addEventListener("change", updateAIFilters);
  let pendingAIState = null;
  function discardPendingAI() {
    const old = pendingAIState;
    pendingAIState = null;
    if (old) fetch(old.url, {method:"DELETE", keepalive:true}).catch(() => {});
  }
  function waitForAIQuota(seconds, signal) {
    return new Promise((resolve, reject) => {
      if (signal.aborted) return reject(new DOMException("Cancelado", "AbortError"));
      const cancel = () => { clearTimeout(timer); reject(new DOMException("Cancelado", "AbortError")); };
      const timer = setTimeout(() => { signal.removeEventListener("abort", cancel); resolve(); }, seconds * 1000);
      signal.addEventListener("abort", cancel, {once:true});
    });
  }

  async function analyzeInBatches(snapshot, controller, onProgress, options = {
    get: () => pendingAIState, set: value => { pendingAIState = value; },
    discard: discardPendingAI, endpoint: "/api/v1/conferencia-fiscal/ia/sessoes"
  }) {
    let cached = options.get();
    if (cached && (cached.snapshot !== snapshot || cached.expires <= Date.now())) {
      options.discard(); cached = null;
    }
    if (!cached) {
      const response = await fetch(API() + options.endpoint, {
        method:"POST", body:snapshot, signal:controller.signal
      });
      if (response.status === 404 && !options.documental) {
        const legacy = await fetch(API() + "/api/v1/conferencia-fiscal/ia", {
          method:"POST", body:snapshot, signal:controller.signal
        });
        if (!legacy.ok) throw new Error(await responseError(legacy));
        const result = await legacy.json();
        result.analises = (result.analises || []).map(item => ({...item,
          provedor:item.provedor || result.provedor, modelo_usado:item.modelo_usado || result.modelo_usado}));
        return result;
      }
      if (!response.ok) throw new Error(await responseError(response));
      const session = await response.json();
      const url = API() + "/api/v1/conferencia-fiscal/ia/sessoes/" + encodeURIComponent(session.sessao);
      cached = {snapshot, session, url, results:new Map(), expires:Date.now() + 29 * 60 * 1000};
      options.set(cached);
    }
    const state = cached;
    const {session, url, results} = state;
    const failures = [];
    let completed = [...results.values()].reduce((total, result) => total + result.analises.length, 0);
    const cleanup = () => { if (options.get() === state) options.discard(); };
    onProgress(completed, session.grupos, 0);
    controller.signal.addEventListener("abort", cleanup, {once:true});
    try {
      const providers = [...new Set(session.lotes.map(batch => batch.provedor))];
      await Promise.all(providers.map(async provider => {
        for (const batch of session.lotes.filter(item => item.provedor === provider && !results.has(item.id))) {
          if (controller.signal.aborted) throw new DOMException("Cancelado", "AbortError");
          try {
            for (let attempt = 0; attempt < 2; attempt++) {
              const reply = await fetch(url + "/lotes/" + batch.id, {method:"POST", signal:controller.signal});
              if (reply.status === 429 && attempt === 0) {
                const rawWait = Number(reply.headers?.get?.("Retry-After") || 60);
                const wait = Number.isFinite(rawWait) ? Math.max(15, Math.min(120, rawWait)) : 60;
                onProgress(completed, session.grupos, failures.length, "Aguardando " + wait + " s pela fila ou cota gratuita de " + (provider === "groq" ? "Groq" : provider === "openrouter" ? "OpenRouter" : "Gemini") + ".");
                await waitForAIQuota(wait, controller.signal);
                continue;
              }
              if (!reply.ok) throw new Error(await responseError(reply));
              const result = await reply.json();
              result.analises = result.analises.map(item => ({...item,
                provedor:item.provedor || result.provedor,
                modelo_usado:item.modelo_usado || result.modelo_usado}));
              results.set(batch.id, result);
              completed += result.analises.length;
              break;
            }
          } catch (error) {
            if (controller.signal.aborted) throw error;
            failures.push({lote:batch.id, grupos:batch.grupos, mensagem:error.message});
          }
          onProgress(completed, session.grupos, failures.length, "", [...results.entries()].sort((a,b) => a[0] - b[0]).flatMap(entry => entry[1].analises));
        }
      }));
      if (controller.signal.aborted) throw new DOMException("Cancelado", "AbortError");
      if (!results.size && failures.length) throw new Error(failures[0].mensagem);
      const ordered = [...results.entries()].sort((a,b) => a[0] - b[0]).map(entry => entry[1]);
      const actualProviders = [...new Set(ordered.flatMap(result =>
        result.analises.map(item => item.provedor || result.provedor)))];
      const pending = session.grupos - completed;
      return {
        analises:ordered.flatMap(result => result.analises),
        grupos_pendentes:pending,
        provedor:actualProviders.length > 1 ? "cooperacao" : actualProviders[0],
        nomes_provedores:actualProviders.map(provider => provider === "groq" ? "Groq" : provider === "gemini" ? "Gemini" : "OpenRouter").join(" + "),
        gratuito:ordered.every(result => result.gratuito === true),
        modelo_usado:[...new Set(ordered.map(result => result.modelo_usado).filter(Boolean))].join("; "),
        fallback_usado:ordered.some(result => result.fallback_usado),
        cobertura_documental:session.cobertura_documental,
        aviso:pending ? "Análise parcial: " + completed + " de " + session.grupos + " grupos concluídos; " + pending + " pendentes. " + failures.map(item => item.mensagem).join(" ")
          : "Análise concluída para todos os " + session.grupos + " grupos com alertas/divergências. Sugestões para revisão humana; os cálculos foram preservados.",
        limite:session.registros + " registros disponíveis no processamento local, sem corte global de 1.500 registros ou 12 grupos. " +
          (actualProviders.includes("groq") ? "Groq recebeu até 10 históricos de 180 caracteres por grupo e indicadores locais; não fez leitura integral dos lançamentos. " : "") +
          "Cada lote segue os limites de contexto e cota do provedor."
      };
    } finally {
      controller.signal.removeEventListener("abort", cleanup);
      // Mantém os pareceres até trocar arquivos/filtros ou expirar a sessão.
      if (controller.signal.aborted) cleanup();
    }
  }

  const aiCancelButton = node("button", "secondary-action fiscal-ai-cancel", "Cancelar");
  aiCancelButton.type = "button";
  aiCancelButton.hidden = true;
  aiCancelButton.addEventListener("click", () => {
    if (!aiController) return;
    aiController.abort();
    aiMessage.textContent = "Solicitação cancelada. Os valores da conferência foram preservados.";
    aiInlineStatus.textContent = "Análise cancelada. Você pode iniciar outra quando quiser.";
    showAIProgress("cancelled");
  });
  loadingPanel.querySelector(".fiscal-ai-loading-head").appendChild(aiCancelButton);

  const aiRetry = node("button", "secondary-action", "Repetir lotes pendentes");
  aiRetry.type = "button";
  aiRetry.hidden = true;
  aiRetry.addEventListener("click", () => aiButton.click());
  aiButton.after(aiRetry);

  aiButton.addEventListener("click", async () => {
    if (!previewBody || !aiConfigured) return;
    const resuming = pendingAIState?.snapshot === previewBody;
    if (!resuming) aiReport = null;
    aiRetry.hidden = true;
    aiExport.disabled = true;
    aiController?.abort(); const controller = new AbortController(); aiController = controller;
    const snapshot = previewBody; aiButton.disabled = true;
    if (!resuming) { aiResult.replaceChildren(); clearAIAccounts(); }
    aiResult.setAttribute("aria-busy", "true");
    aiCancelButton.hidden = false;
    loadingCounts = {done:0, total:0};
    byId("fiscal242LoadingTime").textContent = "0 s";
    showAIProgress("preparing", 0, 0);
    aiInlineStatus.hidden = true;
    aiInlineStatus.textContent = "Análise em andamento. Você pode cancelar a espera sem alterar a conferência.";
    aiMessage.textContent = "Enviando dados para análise…";
    const startedAt = Date.now();
    const progressTimer = window.setInterval(() => {
      if (aiController !== controller || controller.signal.aborted) return;
      const secs = Math.floor((Date.now() - startedAt) / 1000);
      byId("fiscal242LoadingTime").textContent = secs + " s";
      if (secs % 4 !== 0) return;
      aiMessage.textContent = "A IA está preparando os pareceres (" + secs + " s). " +
        (secs >= 25 ? "Modelos gratuitos podem ter fila; aguarde ou cancele." : "Validando contas e evidências.");
    }, 1000);
    try {
      const result = await analyzeInBatches(snapshot, controller, (done, total, failed, waiting, ready) => {
        if (aiController !== controller || controller.signal.aborted) return;
        if (ready?.length) renderAIEntries(ready);
        showAIProgress(waiting ? "waiting" : "analyzing", done, total, waiting);
        aiInlineStatus.textContent = done + " de " + total + " grupos concluídos" +
          (failed ? " · " + failed + " lotes pendentes" : "") + ". " +
          (waiting || "As IAs gratuitas dividem os lotes; resultados concluídos são reaproveitados.");
      });
      if (controller.signal.aborted || previewBody !== snapshot) return;
      aiReport = result;
      // Preserva os cartões já recebidos e as contas abertas durante a espera.
      // A troca de provedor é transparente: os mesmos pareceres são renderizados.
      if (result.provedor === "cooperacao") {
        aiProvider.textContent = (result.nomes_provedores || "Gemini + Groq") + " · gratuito";
      } else if (result.provedor === "gemini") {
        aiProvider.textContent = result.gratuito === true ? "Gemini · gratuito" : "Gemini";
      } else if (result.provedor === "openrouter") {
        aiProvider.textContent = "OpenRouter · gratuito";
      } else if (result.provedor === "groq") {
        aiProvider.textContent = "GroqCloud · gratuito";
      }
      aiExport.disabled = !(Array.isArray(result.analises) && result.analises.length);
      const providerLabel = result.provedor === "cooperacao" ? (result.nomes_provedores || "Gemini + Groq") : result.provedor === "groq" ? "GroqCloud" : result.provedor === "openrouter" ? "OpenRouter" : result.provedor === "gemini" ? "Gemini" : "IA";
      aiInlineStatus.textContent = result.analises?.length
        ? "Parecer recebido do " + providerLabel + ". Selecione uma conta para ler a análise ou exporte o Excel."
        : "O " + providerLabel + " concluiu a análise. Não foram identificadas contas a explicar.";
      const entries = Array.isArray(result.analises) ? result.analises : [];
      showAIProgress(result.grupos_pendentes ? "partial" : "complete", entries.length, entries.length + Number(result.grupos_pendentes || 0));
      aiToolbar.hidden = entries.length === 0;
      aiTotal.textContent = entries.length ? "(" + entries.length + ")" : "";
      renderAIEntries(entries);
      aiMessage.textContent = (result.aviso || "Parecer recebido e validado pelo Razync.") +
        (result.limite ? " " + result.limite : "") +
        (result.modelo_usado ? " Modelo utilizado: " + result.modelo_usado + "." : "") +
        (result.fallback_usado ? " A análise foi concluída pelo provedor de reserva." : "");
    } catch (error) {
      if (!controller.signal.aborted && previewBody === snapshot) {
        aiMessage.textContent = error.message || "Não foi possível gerar a análise.";
        aiInlineStatus.textContent = "A análise não foi concluída. Confira o painel e tente novamente.";
        showAIProgress("error");
      }
    } finally {
      window.clearInterval(progressTimer);
      if (aiController === controller) {
        aiInlineStatus.hidden = false;
        aiResult.setAttribute("aria-busy", "false");
        aiController = null;
        aiCancelButton.hidden = true;
        aiButton.disabled = !aiConfigured || !previewBody;
        aiRetry.hidden = !pendingAIState || controller.signal.aborted || pendingAIState.results.size === pendingAIState.session.lotes.length;
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
    loadingPanel.hidden = true;
    aiInlineStatus.hidden = false;
    byId("fiscalSetup").open = true;
    byId("fiscalSetupTitle").textContent = "Preparar conferência";
    resetInvestigation();
    discardPendingAI(); aiRetry.hidden = true;
    aiController?.abort(); aiController = null;
    aiCancelButton.hidden = true;
    aiReport = null;
    aiExport.disabled = true;
    aiInlineStatus.textContent = "Faça uma conferência para iniciar a análise.";
    aiButton.disabled = true; aiResult.replaceChildren(); clearAIAccounts(); aiResult.setAttribute("aria-busy", "false");
    aiMessage.textContent = aiConfigured ? "Faça a conferência antes de analisar com IA." : "IA gratuita ainda não configurada no servidor.";
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
    byId("fiscal242NextStep").hidden = true;
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
    details.appendChild(node("p", "fiscal-difference-reading", differenceMeaning(row.diferenca)));

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

  // Ações rápidas dos indicadores e navegação na própria página.
  // Apenas apresentação: o cálculo e o conjunto de contas não são alterados.
  const quickFilters = [...pane.querySelectorAll("[data-fiscal-filter]")];
  const workflowButtons = [...pane.querySelectorAll("[data-fiscal-target]")];
  function focusFiscalSection(id) {
    const target = byId(id);
    if (!target || target.hidden || results.hidden) return;
    const aiView = id === "fiscal242AISection";
    pane.querySelectorAll("[data-fiscal-panel]").forEach(item => {item.hidden = (item.dataset.fiscalPanel === "ai") !== aiView;});
    workflowButtons.forEach(button => {
      const current = (button.dataset.fiscalTarget === "fiscal242AISection") === aiView;
      button.classList.toggle("is-current", current);
      if (current) button.setAttribute("aria-current", "location");
      else button.removeAttribute("aria-current");
    });
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    target.scrollIntoView?.({behavior:motion, block:"start"});
  }
  function syncQuickFilters() {
    quickFilters.forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.fiscalFilter === filter.value));
    });
  }
  quickFilters.forEach(button => {
    button.addEventListener("click", () => {
      if (!data) return;
      filter.value = button.dataset.fiscalFilter;
      search.value = "";
      selectedKey = "";
      renderTable();
      syncQuickFilters();
      focusFiscalSection("fiscal242ResultsCard");
    });
  });
  workflowButtons.forEach(button => {
    button.addEventListener("click", () => focusFiscalSection(button.dataset.fiscalTarget));
  });
  byId("fiscal242NextStepButton").addEventListener("click", () => focusFiscalSection("fiscal242Investigacao"));

  function sortFiscalRows(rows, key, descending) {
    if (!key) return rows;
    return [...rows].sort((a, b) => {
      const comparison = key === "conta" ? String(a.conta).localeCompare(String(b.conta), "pt-BR", {numeric:true})
        : key === "diferenca" ? Math.abs(Number(a[key] || 0)) - Math.abs(Number(b[key] || 0))
        : Number(a[key] || 0) - Number(b[key] || 0);
      return descending ? -comparison : comparison;
    });
  }
  const sortButtons = [...pane.querySelectorAll("[data-fiscal-sort]")];
  sortButtons.forEach(button => button.addEventListener("click", () => {
    const key = button.dataset.fiscalSort;
    tableSort = {key, descending:tableSort.key === key ? !tableSort.descending : key !== "conta"};
    sortButtons.forEach(control => {
      const active = control.dataset.fiscalSort === key;
      control.parentElement.setAttribute("aria-sort", active ? tableSort.descending ? "descending" : "ascending" : "none");
      control.querySelector("span").textContent = active ? tableSort.descending ? "↓" : "↑" : "↕";
    });
    renderTable();
  }));

  function renderTable() {
    const dock = byId("fiscal242DetailDock");
    dock.appendChild(details);
    const rows = sortFiscalRows(filteredRows(), tableSort.key, tableSort.descending);
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
      account.dataset.label = "Conta";
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
      const accumulatorCount = accumulatorRows(row).length;
      if (accumulatorCount > 1) accumulatorCell.appendChild(node("small", "fiscal-table-secondary", accumulatorCount + " acumuladores"));
      const fiscalValue = cell(tr, money.format(row.fiscal), "fiscal-money fiscal-money-fiscal");
      fiscalValue.dataset.label = "Fiscal";
      const accountingValue = cell(tr, money.format(row.contabil), "fiscal-money fiscal-money-accounting");
      accountingValue.dataset.label = "Contábil";
      const diferenca = cell(tr, "", "fiscal-money fiscal-difference");
      diferenca.appendChild(node("span", "fiscal-difference-number", money.format(row.diferenca)));
      diferenca.dataset.label = "Diferença";
      diferenca.appendChild(node("small", "fiscal-table-secondary", Math.abs(Number(row.diferenca || 0)) <= 0.01 ? "Sem diferença" : row.diferenca < 0 ? "Abaixo do fiscal" : "Acima do fiscal"));
      if (Math.abs(Number(row.diferenca || 0)) <= 0.01) diferenca.classList.add("fiscal-difference-zero");
      const td = cell(tr, "", "fiscal-situation-cell");
      td.dataset.label = "Situação";
      td.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(row.situacao), statusLabels[row.situacao] || row.situacao));
      tableBody.appendChild(tr);
    });
    renderDetails(rows.find(row => keyOf(row) === selectedKey) || null);
    if (selectedKey) {
      const selectedRow = [...tableBody.children].find(row => row.classList.contains("selected"));
      if (selectedRow) {
        const expanded = node("tr", "fiscal-inline-row");
        const host = node("td", "fiscal-inline-host"); host.colSpan = 6;
        host.appendChild(details); expanded.appendChild(host); selectedRow.after(expanded);
      }
    }
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
    byId("fiscal242AIContext").textContent = (report.empresa_nome || "Conferência atual") +
      (parts.length ? " · " + parts.join(" · ") : "");
    const warningBox = byId("fiscal242Warnings");
    warningBox.replaceChildren();
    (report.avisos || []).forEach(aviso => warningBox.appendChild(node("p", "", aviso)));
    byId("fiscal242WarningCount").textContent = "(" + (report.avisos || []).length + ")";
    warningBox.parentElement.hidden = !(report.avisos || []).length;
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
    resetInvestigation();
    investigation.hidden = !(report.contas || []).some(row => ["REVISAR", "AUSENTE NO CONTÁBIL", "CONFERE COM ALERTAS"].includes(row.situacao));
    const attentionCount = (report.contas || []).filter(row =>
      ["REVISAR", "AUSENTE NO CONTÁBIL", "CONFERE COM ALERTAS"].includes(row.situacao)
    ).length;
    byId("fiscal242NextStep").hidden = !attentionCount;
    byId("fiscal242NextStepTitle").textContent = attentionCount === 1
      ? "1 conta precisa de atenção"
      : attentionCount + " contas precisam de atenção";
    aiInlineStatus.textContent = "Conferência pronta. Use a análise inteligente para revisar diferenças e alertas.";
    selectedKey = "";
    filter.value = "todas";
    search.value = "";
    workflowButtons.forEach(button => {
      const current = button.dataset.fiscalTarget === "fiscal242Overview";
      button.classList.toggle("is-current", current);
      if (current) button.setAttribute("aria-current", "location");
      else button.removeAttribute("aria-current");
    });
    syncQuickFilters();
    renderTable();
    byId("fiscalSetup").open = false;
    byId("fiscalSetupTitle").textContent = "Arquivos da conferência · trocar ou conferir";
    focusFiscalSection("fiscal242Overview");
  }

  // A investigação documental é uma segunda etapa. Nenhuma requisição
  // adicional ocorre até o usuário anexar Entradas e/ou Saídas.
  const investigation = byId("fiscal242Investigacao");
  const investigationForm = byId("fiscal242InvestigarForm");
  const investigationButton = byId("fiscal242InvestigarBtn");
  const investigationMessage = byId("fiscal242InvestigarMessage");
  const investigationResults = byId("fiscal242InvestigarResultado");
  let investigationController = null;
  let investigationReport = null;
  let investigationBody = null;
  let docAIController = null;
  let pendingDocAI = null;

  function discardDocAI() {
    const old = pendingDocAI;
    pendingDocAI = null;
    if (old) fetch(old.url, {method:"DELETE", keepalive:true}).catch(() => {});
  }
  function clearDocAI() {
    docAIController?.abort();
    docAIController = null;
    discardDocAI();
    byId("fiscal242InvestigarIA").disabled = false;
    byId("fiscal242InvestigarIA").textContent = "Analisar pendências com IA";
    byId("fiscal242InvestigarIAPareceres").replaceChildren();
    byId("fiscal242InvestigarIAMessage").textContent = "";
  }

  function resetInvestigation() {
    investigationController?.abort();
    investigationController = null;
    investigationReport = null;
    investigationBody = null;
    clearDocAI();
    byId("fiscal242InvestigarIAArea").hidden = true;
    byId("fiscal242InvestigarIAPareceres").replaceChildren();
    byId("fiscal242InvestigarIAMessage").textContent = "";
    investigation.hidden = true;
    investigationResults.hidden = true;
    investigationResults.replaceChildren();
    investigationMessage.textContent = "";
    investigationButton.disabled = false;
    byId("fiscal242Entradas").value = "";
    byId("fiscal242Saidas").value = "";
  }

  function investigationStatus(status) {
    return ({
      CONCILIADO: "Correspondência identificada",
      AMBIGUO: "Correspondência ambígua",
      VALOR_DIFERENTE: "Valor divergente",
      DATA_DIFERENTE: "Data divergente",
      PROVAVEL: "Correspondência provável, confirme o documento",
      SEM_LANCAMENTO_IDENTIFICADO: "Sem lançamento identificado",
      SEM_DOCUMENTO_IDENTIFICADO: "Sem documento identificado",
      CORRESPONDENCIA_EM_ANALISE: "Correspondência em análise",
      DOCUMENTOS_NAO_IDENTIFICAVEIS: "Detalhamento não identificável"
    })[status] || status || "Revisar";
  }

  function investigationTable(headers, rows, renderRow) {
    const wrap = node("div", "fiscal-table-scroll");
    const table = node("table", "fiscal-table fiscal-investigation-table");
    const thead = node("thead");
    const head = node("tr");
    headers.forEach(label => head.appendChild(node("th", "", label)));
    thead.appendChild(head);
    table.appendChild(thead);
    const tbody = node("tbody");
    rows.forEach(row => {
      const tr = node("tr");
      renderRow(tr, row);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderInvestigation(report) {
    investigationResults.replaceChildren();
    const count = report.resumo || {};
    const header = node("div", "fiscal-investigation-summary");
    [
      ["Contas investigadas", count.contas || 0],
      ["Documentos conciliados", count.conciliados || 0],
      ["Pendências para conferir", count.pendentes || 0],
      ["Correspondências ambíguas", count.ambiguos || 0]
    ].forEach(([label, value]) => {
      const metric = node("div", "fiscal-investigation-metric");
      metric.append(node("small", "", label), node("strong", "", value));
      header.appendChild(metric);
    });
    investigationResults.appendChild(header);
    const warningArea = node("div", "fiscal-warnings");
    (report.avisos || []).forEach(message => warningArea.appendChild(node("p", "", message)));
    investigationResults.appendChild(warningArea);
    if (!report.contas?.length) {
      investigationResults.appendChild(node("p", "fiscal-disclaimer",
        "Não há contas divergentes ou com alertas nos tipos anexados. A conferência original permanece disponível."));
    }
    (report.contas || []).forEach(group => {
      const section = node("section", "fiscal-investigation-account");
      const title = node("h4", "", "Conta " + group.conta + " · " + group.tipo);
      section.appendChild(title);
      section.appendChild(node("p", "fiscal-disclaimer",
        "Diferença da conferência inicial: " + money.format(group.diferenca || 0) +
        ". A soma de documentos por acumulador é informativa; igualdade de totais não comprova integração individual."));
      const breakdown = node("div", "fiscal-investigation-accumulators");
      (group.acumuladores || []).forEach(acc => {
        const line = node("div", "fiscal-investigation-accumulator");
        const name = node("div");
        name.append(node("strong", "", "Acumulador " + acc.codigo),
          node("small", "", acc.descricao || "Sem descrição"));
        const amounts = node("div", "fiscal-investigation-accumulator-amount");
        amounts.append(
          node("span", "", "Resumo: " + money.format(acc.valor_resumo)),
          node("span", "", "Documentos: " + money.format(acc.valor_documentos)),
          node("small", "", acc.quantidade_documentos + " linhas documentais · " +
            acc.conciliados + " conciliadas · " + acc.pendentes + " pendentes · " +
            acc.ambiguos + " ambíguas")
        );
        line.append(name, amounts);
        breakdown.appendChild(line);
      });
      section.appendChild(breakdown);
      const docs = (group.documentos || []).filter(item => item.situacao !== "CONCILIADO");
      const docsDetails = node("details", "fiscal-ledger-disclosure");
      docsDetails.appendChild(node("summary", "fiscal-ledger-toggle",
        "Documentos para revisar (" + (group.documentos_total - (group.resumo?.conciliados || 0)) + ")"));
      if (docs.length) {
        docsDetails.appendChild(investigationTable(
          ["Acumulador", "Nota", "Data", "CFOP", "Fiscal", "Razão candidato", "Diferença calculada", "Situação / critério"],
          docs.slice(0, 120), (tr, d) => {
            cell(tr, d.acumulador); cell(tr, d.nota); cell(tr, d.data);
            cell(tr, d.cfop); cell(tr, money.format(d.valor), "fiscal-money");
            cell(tr, d.valor_razao_candidato == null ? "Não identificado" : money.format(d.valor_razao_candidato), "fiscal-money");
            cell(tr, d.diferenca_candidato == null ? "—" : money.format(d.diferenca_candidato), "fiscal-money");
            cell(tr, investigationStatus(d.situacao) + ". " + (d.criterio || ""));
          }
        ));
        if (docs.length > 120 || (group.documentos_total || 0) > (group.documentos || []).length) {
          docsDetails.appendChild(node("p", "fiscal-disclaimer",
            "A visualização mostra apenas uma amostra das pendências; a contagem inclui todos os documentos processados."));
        }
      } else docsDetails.appendChild(node("p", "fiscal-disclaimer", "Nenhuma pendência documental identificada nesta amostra."));
      section.appendChild(docsDetails);
      const ledger = group.razao_pendente || [];
      if (group.razao_pendente_total) {
        const openLedger = node("details", "fiscal-ledger-disclosure");
        openLedger.appendChild(node("summary", "fiscal-ledger-toggle",
          "Movimentos do Razão ainda não conciliados (" + group.razao_pendente_total + ")"));
        openLedger.appendChild(investigationTable(
          ["Data", "Histórico", "Valor", "Situação"],
          ledger.slice(0, 120), (tr, mov) => {
            cell(tr, mov.data); cell(tr, mov.historico);
            cell(tr, money.format(mov.valor), "fiscal-money");
            cell(tr, investigationStatus(mov.situacao));
          }
        ));
        section.appendChild(openLedger);
      }
      investigationResults.appendChild(section);
    });
    investigationResults.hidden = false;
  }

  investigationForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (!previewBody || !data) {
      investigationMessage.textContent = "Conclua a conferência inicial antes de investigar documentos.";
      return;
    }
    const entradas = byId("fiscal242Entradas").files?.[0];
    const saidas = byId("fiscal242Saidas").files?.[0];
    if (!entradas && !saidas) {
      investigationMessage.textContent = "Selecione Entradas, Saídas ou ambos.";
      return;
    }
    clearDocAI();
    investigationReport = null;
    investigationBody = null;
    byId("fiscal242InvestigarIAArea").hidden = true;
    const snapshot = data;
    const body = new FormData();
    const files = selectedFiles();
    body.append("acumuladores", files.acumuladores);
    body.append("razao", files.razao);
    body.append("filial", String(data.filial_aplicada || byId("fiscalFilialCodigo").value || ""));
    if (entradas) body.append("entradas", entradas);
    if (saidas) body.append("saidas", saidas);
    investigationController?.abort();
    const controller = new AbortController();
    investigationController = controller;
    investigationButton.disabled = true;
    investigationMessage.textContent = "Cruzando os documentos com o Razão, por conta e acumulador…";
    try {
      const response = await fetch(API() + "/api/v1/conferencia-fiscal/investigar", {
        method: "POST", body, signal: controller.signal
      });
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      if (controller.signal.aborted || snapshot !== data) return;
      investigationReport = result;
      investigationBody = body;
      renderInvestigation(result);
      byId("fiscal242InvestigarIAArea").hidden = !(result.contas || []).some(row => row.razao_pendente_total || (row.documentos || []).some(doc => doc.situacao !== "CONCILIADO"));
      byId("fiscal242InvestigarIAPareceres").replaceChildren();
      byId("fiscal242InvestigarIAMessage").textContent = "";
      investigationMessage.textContent = "Investigação concluída. Confira as pendências e as correspondências ambíguas abaixo.";
    } catch (error) {
      if (error.name !== "AbortError" && snapshot === data) {
        investigationMessage.textContent = error.message || "Não foi possível investigar os relatórios.";
      }
    } finally {
      if (investigationController === controller) {
        investigationController = null;
        investigationButton.disabled = false;
      }
    }
  });



  const docAi = byId("fiscal242InvestigarIA");
  const docAiMessage = byId("fiscal242InvestigarIAMessage");
  const docAiResults = byId("fiscal242InvestigarIAPareceres");
  ["fiscal242Entradas", "fiscal242Saidas"].forEach(id => byId(id).addEventListener("change", () => {
    investigationController?.abort();
    investigationController = null;
    investigationButton.disabled = false;
    investigationReport = null;
    investigationBody = null;
    clearDocAI();
    investigationResults.replaceChildren();
    investigationResults.hidden = true;
    byId("fiscal242InvestigarIAArea").hidden = true;
    investigationMessage.textContent = "Arquivos alterados. Investigue novamente para atualizar as pendências.";
  }));
  function renderDocAI(entries) {
    docAiResults.replaceChildren();
    entries.forEach(item => {
      const card = node("article", "fiscal-investigation-account");
      card.appendChild(node("h4", "", "Conta " + item.conta + " · " + item.tipo));
      card.appendChild(node("p", "fiscal-ai-provider", aiSourceLabel(item)));
      if (item.valores) card.appendChild(node("p", "fiscal-difference-reading",
        "Fiscal: " + money.format(Number(item.valores.fiscal || 0)) + " · Contábil considerado: " + money.format(Number(item.valores.contabil || 0)) + " · Diferença: " + money.format(Number(item.valores.diferenca || 0))));
      const comparisons = item.parecer?.comparacoes_documentais || [];
      if (comparisons.length) {
        const facts = node("details", "fiscal-ledger-disclosure");
        facts.appendChild(node("summary", "fiscal-ledger-toggle", "Comparação por documento · cálculo do sistema"));
        facts.appendChild(investigationTable(["Referência / nota", "Fiscal", "Razão candidato", "Diferença"], comparisons, (tr, doc) => {
          cell(tr, doc.referencia + " · " + doc.nota);
          cell(tr, doc.valor_brl);
          cell(tr, doc.valor_razao_candidato_brl || "Não identificado");
          cell(tr, doc.diferenca_candidato_brl || "—");
        }));
        facts.appendChild(node("p", "fiscal-disclaimer", "Diferença = valor do candidato no Razão menos fiscal. O candidato é um indício; confirme o vínculo antes de ajustar."));
        card.appendChild(facts);
      }
      card.appendChild(renderAIFindings(item));
      card.appendChild(node("h5", "", "Próximos passos"));
      card.appendChild(renderAIReviewSteps(item));
      if (item.auditoria) {
        const notes = Array.isArray(item.auditoria.alertas) ? item.auditoria.alertas : [];
        const audit = node("div", "fiscal-ai-audit");
        audit.appendChild(node("strong", "", notes.length ? "Auditoria · precisa revisar" : "Auditoria · sem alertas estruturais"));
        for (const note of notes) audit.appendChild(node("p", "", String(note)));
        card.appendChild(audit);
      }
      card.appendChild(renderAILimits(item));
      docAiResults.appendChild(card);
    });
  }
  docAi.addEventListener("click", async () => {
    if (!data || !investigationReport || !investigationBody || !aiConfigured) {
      docAiMessage.textContent = "Verifique a disponibilidade da IA gratuita e conclua a investigação documental.";
      return;
    }
    const snapshot = data;
    const body = investigationBody;
    const controller = new AbortController();
    docAIController?.abort();
    docAIController = controller;
    docAi.disabled = true;
    docAiMessage.textContent = "Enviando somente pendências e evidências necessárias para a IA gratuita…";
    try {
      const report = await analyzeInBatches(body, controller, (done, total, failed, waiting, ready) => {
        if (data !== snapshot || investigationBody !== body || controller.signal.aborted) return;
        docAiMessage.textContent = waiting || "Análise documental: " + done + " de " + total + " grupos concluídos." +
          (failed ? " Há lotes pendentes que poderão ser retomados." : "");
        if (ready) renderDocAI(ready);
      }, {get: () => pendingDocAI, set: value => { pendingDocAI = value; }, discard: discardDocAI,
          endpoint: "/api/v1/conferencia-fiscal/investigar/ia/sessoes", documental:true});
      if (data !== snapshot || investigationBody !== body || controller.signal.aborted) return;
      renderDocAI(report.analises || []);
      const provider = report.provedor === "groq" ? "GroqCloud" :
        report.provedor === "gemini" ? "Gemini" :
        report.provedor === "openrouter" ? "OpenRouter" : report.nomes_provedores || "IA";
      const coverage = Object.entries(report.cobertura_documental || {}).map(([key, c]) =>
        "Conta " + key + ": " + c.documentos_enviados + "/" + c.documentos_pendentes +
        " documentos e " + c.lancamentos_enviados + "/" + c.lancamentos_pendentes + " movimentos enviados" +
        (c.amostra ? " (amostra para economizar a cota; revisão restante necessária)" : "") + ".").join(" ");
      docAiMessage.textContent = (report.aviso || "Análise concluída.") +
        ((report.analises || []).length ? " Provedor: " + provider + "." : "") +
        (report.fallback_usado ? " Foi utilizado um provedor gratuito de reserva." : "") + " " + coverage;
      docAi.textContent = report.grupos_pendentes ? "Retomar lotes pendentes" : "Ver análise já concluída";
    } catch (error) {
      if (error.name !== "AbortError" && data === snapshot && investigationBody === body) {
        docAiMessage.textContent = (error.message || "Não foi possível consultar a IA.") +
          " As pendências documentais calculadas permanecem disponíveis. Você pode tentar novamente mais tarde.";
      }
    } finally {
      if (docAIController === controller) {
        docAIController = null;
        docAi.disabled = false;
      }
    }
  });

  filter.addEventListener("change", () => { renderTable(); syncQuickFilters(); });
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
    discardPendingAI(); aiRetry.hidden = true;
    aiController?.abort(); aiController = null; aiButton.disabled = true; aiResult.replaceChildren(); clearAIAccounts();
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
