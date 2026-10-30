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
    "CONFERE": "Totais iguais",
    "CONFERE COM ALERTAS": "Com alertas",
    "REVISAR": "Divergência",
    "AUSENTE NO CONTÁBIL": "Sem razão"
  };
  let data = null;
  let previewBody = null;
  let aiInputBody = null;
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
    const names = {groq:"Groq",gemini:"Gemini",openrouter:"OpenRouter",local:"Conferência local"};
    const name = names[item.provedor] || "IA não identificada";
    if (item.provedor === "local") return name + " · sem chamada de IA";
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
      const documentary = reading.documental_especifico === true;
      const executive = item.parecer?.resumo_executivo;
      if (executive?.conclusao) {
        const overview = node("section", "fiscal-ai-executive");
        const top = node("div", "fiscal-ai-executive-top");
        top.append(node("span", "fiscal-ai-executive-kicker", "LEITURA DA CONTA"),
          node("span", "fiscal-ai-executive-coverage", executive.cobertura));
        overview.append(top, node("h5", "fiscal-ai-executive-title", executive.titulo),
          node("p", "fiscal-ai-executive-conclusion", executive.conclusao));
        const next = node("div", "fiscal-ai-executive-next");
        next.append(node("span", "fiscal-ai-executive-next-label", "COMECE POR AQUI"),
          node("strong", "", executive.foco), node("p", "", executive.primeiro_passo));
        // As notas e valores aparecem uma única vez na tabela de documentos.
        overview.appendChild(next); analysis.appendChild(overview);
        if (!documentary) analysis.appendChild(node("p", "fiscal-ai-diagnostic-caption", reading.resultado));
      } else {
        analysis.append(node("h5", "", documentary ? "Diagnóstico desta conta" : "Resultado da conta"),
          node("p", "fiscal-ai-conclusion", reading.resultado));
      }
      if (reading.observacoes?.length && !documentary) {
        analysis.appendChild(node("h5", "", documentary ? "Tipos de pendência encontrados" : "O que os lançamentos mostram"));
        const facts = node("ul", "fiscal-ai-finding-list");
        for (const observation of reading.observacoes) facts.appendChild(node("li", "", observation));
        analysis.appendChild(facts);
      }
      if (documentary && reading.destaques?.length && !(reading.orientacoes || []).some(step => step.documentos?.length)) {
        analysis.appendChild(node("h5", "", "Documentos para investigar primeiro"));
        const examples = node("div", "fiscal-ai-document-highlights");
        for (const entry of reading.destaques) {
          const row = node("article", "fiscal-ai-document-highlight");
          const head = node("div", "fiscal-ai-document-highlight-heading");
          head.append(node("strong", "", entry.documento || "Documento fiscal"),
            node("span", "", entry.referencia || ""));
          row.appendChild(head);
          row.appendChild(node("p", "fiscal-ai-document-highlight-reason", entry.tipo || ""));
          const details = [];
          if (entry.data) details.push("Data: " + entry.data);
          if (entry.valor_fiscal) details.push("Fiscal: " + entry.valor_fiscal);
          if (entry.conta_candidata) details.push("Candidato na conta " + entry.conta_candidata);
          if (entry.valor_razao_candidato) details.push("Razão candidato: " + entry.valor_razao_candidato);
          if (entry.diferenca_candidata) details.push("Diferença do candidato: " + entry.diferenca_candidata);
          if (details.length) row.appendChild(node("p", "fiscal-ai-document-highlight-details", details.join(" · ")));
          if (entry.como_verificar) row.appendChild(node("p", "fiscal-ai-document-highlight-action", entry.como_verificar));
          examples.appendChild(row);
        }
        analysis.appendChild(examples);
      }
      if (documentary && reading.impactos?.length) {
        const impacts = node("section", "fiscal-ai-impact-details");
        impacts.appendChild(node("h5", "", "Como a diferença se forma"));
        const list = node("ul", "");
        for (const effect of reading.impactos) {
          const li = node("li", "");
          li.append(node("span", "", effect.descricao), node("strong", "", effect.valor));
          list.appendChild(li);
        }
        impacts.appendChild(list);
        analysis.appendChild(impacts);
      }
      const interpretation = String(item.parecer?.analise_exibicao || "").trim();
      const standardAnswer = /^(?:A causa ainda não está comprovada pelas evidências desta conta\.|Os dados disponíveis não sustentam uma causa específica\.|A causa está indeterminada: os lançamentos disponíveis não sustentam uma explicação)/i.test(interpretation);
      if (interpretation && !(documentary && standardAnswer)) {
        analysis.append(node("h5", "", item.provedor === "local" ? "Leitura do sistema" : documentary ? "Interpretação da IA · hipótese a confirmar" : "O que permanece em aberto"),
          node("p", "fiscal-ai-open-question", interpretation));
      }
      if (reading.criterio) analysis.appendChild(node("p", "fiscal-ai-comparison-rule", reading.criterio));
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
    for (const [index, instruction] of instructions.entries()) {
      const step = node("li", "", "");
      if (instruction.categoria) step.classList.add("fiscal-ai-grouped-step");
      const body = node("div", "");
      body.appendChild(node("strong", "", instruction.acao));
      if (instruction.documentos?.length && !item.parecer?.leitura_comparacao?.documental_especifico) {
        const docs = node("ul", "fiscal-ai-step-documents");
        for (const document of instruction.documentos) {
          const example = node("li", "");
          example.appendChild(node("strong", "", document.titulo || document.referencia));
          if (document.detalhes) example.appendChild(node("span", "", document.detalhes));
          docs.appendChild(example);
        }
        body.appendChild(docs);
        if (instruction.amostra) body.appendChild(node("p", "fiscal-ai-step-sample",
          "Exemplos da seleção; os demais documentos desta situação permanecem no cruzamento completo."));
      }
      if (instruction.objetivo && !(index === 0 && item.parecer?.resumo_executivo?.primeiro_passo === instruction.objetivo)) body.appendChild(node("p", "fiscal-ai-step-purpose", instruction.objetivo));
      if (instruction.para_concluir || instruction.quando_reavaliar) {
        const criteria = node("div", "fiscal-ai-decision");
        if (instruction.para_concluir) criteria.append(node("strong", "", "Para concluir"), node("p", "", instruction.para_concluir));
        if (instruction.quando_reavaliar) criteria.append(node("strong", "", "Quando reavaliar a hipótese"), node("p", "", instruction.quando_reavaliar));
        body.appendChild(criteria);
      }
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
      missing.appendChild(node("li", "", item.provedor === "local" ? text.replace(/^Limitação indicada pela IA:\s*/, "Para confirmar: ") : text));
    }
    if (missing.children.length) body.appendChild(missing);
    const coverage = item.parecer?.cobertura;
    if (coverage && !item.cobertura_documental) body.appendChild(node("p", "fiscal-ai-source", `Contexto da IA: ${coverage.enviados} de ${coverage.disponiveis} lançamentos disponíveis nesta conta${coverage.parcial ? " · amostra parcial" : ""}${coverage.historicos_abreviados ? " · históricos abreviados" : ""}.`));
    const revised = item.parecer?.sugestoes_retiradas?.length || item.auditoria?.alertas?.length;
    if (revised && item.parecer?.analise_exibicao !== undefined) {
      body.appendChild(node("p", "fiscal-ai-quality-note", "Resposta revisada: sugestões sem apoio suficiente nas fontes foram desconsideradas na interpretação exibida. Os valores da conferência foram preservados."));
    }
    if (!body.children.length) return null;
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
  function renderAIDocumentary(item, evidence = false) {
    const summary = item.resumo_documental;
    const docs = item.parecer?.comparacoes_documentais || [];
    if ((!summary && !docs.length) || (evidence && !docs.length)) return null;
    const section = node("section", "fiscal-ai-documentary");
    if (!evidence) section.appendChild(node("h5", "", "Cruzamento de Entradas e Saídas"));
    if (summary && !evidence) section.appendChild(node("p", "fiscal-ai-documentary-summary", 
      item.parecer?.leitura_comparacao?.documental_especifico
        ? summary.conciliados + " de " + summary.documentos_lidos + " linhas conciliadas no cruzamento local."
        : summary.conciliados + " de " + summary.documentos_lidos +
          " linhas fiscais conciliadas no cruzamento local · " + summary.documentos_pendentes + " para conferir."));
    if (evidence && docs.length) section.appendChild(renderAIDataTable("Documentos e valores para conferir", ["Nota / acumulador", "Fiscal", "Razão candidato", "Diferença", "Leitura"],
      docs.map(d => [d.nota + " · " + d.acumulador, d.valor_fiscal_grupo_brl || d.valor_brl,
        (d.valor_razao_candidato_brl || "Não identificado") + (d.conta_razao_candidato ? " · conta " + d.conta_razao_candidato : ""),
        d.diferenca_candidato_brl || "—", investigationStatus(d.situacao)]), "fiscal-ai-documents"));
    const coverage = item.cobertura_documental;
    if (coverage && (evidence || !item.parecer?.leitura_comparacao?.documental_especifico)) section.appendChild(node("p", "fiscal-ai-documentary-coverage", "Enviado à IA: " + coverage.documentos_enviados + "/" + coverage.documentos_pendentes +
      " documentos pendentes e " + coverage.lancamentos_enviados + "/" + coverage.lancamentos_pendentes + " movimentos." +
      (coverage.amostra ? " A amostra não representa leitura integral pela IA." : "")));
    return section;
  }

  function renderAICases(item) {
    const cases = item.parecer?.pendencias_explicadas || [];
    if (!cases.length) return null;
    const section = node("details", "fiscal-ai-cases");
    section.appendChild(node("summary", "fiscal-ai-cases-heading", "Ver todas as pendências e evidências (" + cases.length + ")"));
    section.appendChild(node("p", "fiscal-ai-cases-intro",
      cases.length + " caso(s), em ordem de valor envolvido. Os detalhes vêm do cruzamento local; a interpretação da IA é identificada quando disponível."));
    const list = node("div", "fiscal-ai-case-list");
    const caption = node("p", "fiscal-ai-cases-caption");
    const more = node("button", "fiscal-ai-cases-more", "Mostrar mais pendências"); more.type = "button";
    let visible = 0;
    const addPage = () => {
      for (const entry of cases.slice(visible, visible + 20)) {
        const detail = node("details", "fiscal-ai-case");
        const summary = node("summary", "fiscal-ai-case-summary");
        const title = entry.nota ? "Nota " + entry.nota + " · " + entry.titulo : entry.titulo;
        summary.append(node("strong", "", title), node("span", "fiscal-ai-case-strength", entry.grau_evidencia));
        const body = node("div", "fiscal-ai-case-body");
        let built = false;
        detail.addEventListener("toggle", () => {
          if (!detail.open || built) return; built = true;
          body.appendChild(node("p", "fiscal-ai-case-explanation", entry.explicacao_local));
          if (entry.data_fiscal || entry.parceiro || entry.serie) body.appendChild(node("p", "fiscal-ai-case-origin",
            [entry.data_fiscal, entry.serie ? "Série " + entry.serie : "", entry.parceiro].filter(Boolean).join(" · ")));
          const amount = value => value === null || value === undefined ? "Não identificado" : money.format(Number(value));
          body.appendChild(renderAIDataTable("Comparação calculada", ["Fiscal", "Razão candidato", "Diferença (Razão − fiscal)"],
            [[amount(entry.valor_fiscal), amount(entry.valor_razao), amount(entry.diferenca)]], "fiscal-ai-case-values"));
          const candidates = entry.candidatos || [];
          if (candidates.length) body.appendChild(renderAIDataTable("Lançamentos candidatos — vínculo a confirmar",
            ["Referência", "Conta", "Data", "Histórico", "Contrapartida", "Valor"],
            candidates.map(c => [c.referencia,c.conta,c.data,c.historico,c.contrapartida,amount(c.valor)]), "fiscal-ai-case-candidates"));
          if (entry.criterio) body.append(node("h6", "", "Por que este caso foi separado"), node("p", "", entry.criterio));
          for (const [label, values] of [["Campos coincidentes", entry.campos_coincidentes],
            ["Campos divergentes", entry.campos_divergentes], ["Campos a confirmar", entry.campos_a_confirmar]]) {
            if (values?.length) body.append(node("h6", "", label), node("p", "", values.join(" · ")));
          }
          if (entry.interpretacao_ia?.length) {
            body.appendChild(node("h6", "", "Interpretação da IA para este caso"));
            for (const text of entry.interpretacao_ia) body.appendChild(node("p", "", text));
          }
          body.append(node("h6", "", "O que falta confirmar"), node("p", "", entry.falta_confirmar),
            node("h6", "", "Próxima ação"), node("p", "fiscal-ai-case-action", entry.acao));
          if (entry.para_concluir) body.append(node("h6", "", "Para concluir"), node("p", "", entry.para_concluir));
          if (entry.quando_reavaliar) body.append(node("h6", "", "Quando reavaliar a hipótese"), node("p", "", entry.quando_reavaliar));
          for (const step of entry.verificacoes_ia || []) body.appendChild(node("p", "fiscal-ai-case-ai-step", step));
        });
        detail.append(summary, body); list.appendChild(detail);
      }
      visible = Math.min(visible + 20, cases.length);
      caption.textContent = "Mostrando " + visible + " de " + cases.length + " pendências. Abra um caso para ver as evidências.";
      more.hidden = visible >= cases.length;
    };
    more.addEventListener("click", addPage);
    section.addEventListener("toggle", () => { if (section.open && visible === 0) addPage(); });
    section.append(list, caption, more); return section;
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
        const documentary = renderAIDocumentary(item);
        if (documentary) content.appendChild(documentary);
        const composition = renderAIComposition(officialRow);
        const reading = node("div", "fiscal-ai-reading");
        const documentaryEvidence = renderAIDocumentary(item, true);
        if (documentaryEvidence) reading.appendChild(documentaryEvidence);
        reading.appendChild(review);
        content.appendChild(reading);
        const cases = renderAICases(item);
        if (cases) content.appendChild(cases);
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
        content.appendChild(evidence);
        const limits = renderAILimits(item);
        if (limits) content.appendChild(limits);
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
        item.verificar, ...evidencias,
        ...(item.parecer?.leitura_comparacao?.observacoes || []),
        ...(item.parecer?.comparacoes_documentais || []).flatMap(d => [d.referencia, d.nota, d.acumulador, d.conta_razao_candidato, d.criterio])
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
    if (!session.lotes.length) {
      options.discard();
      return {analises:[], provedor:"local", gratuito:true, grupos_pendentes:0,
        apoio_documental:session.apoio_documental, cobertura_documental:session.cobertura_documental,
        aviso:"Não restaram contas com pendências para a IA. Conferência concluída localmente, sem consumir tokens."};
    }
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
        nomes_provedores:actualProviders.map(provider => provider === "local" ? "Conferência local" : provider === "groq" ? "Groq" : provider === "gemini" ? "Gemini" : "OpenRouter").join(" + "),
        gratuito:ordered.every(result => result.gratuito === true),
        modelo_usado:[...new Set(ordered.map(result => result.modelo_usado).filter(Boolean))].join("; "),
        fallback_usado:ordered.some(result => result.fallback_usado),
        cobertura_documental:session.cobertura_documental,
        apoio_documental:session.apoio_documental,
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

  function syncAISources() {
    const area = byId("fiscal242AISources");
    if (!area) return;
    area.replaceChildren();
    [["Resumo fiscal", !!previewBody], ["Razão", !!previewBody],
      ["Entradas", !!byId("fiscal242Entradas").files?.length], ["Saídas", !!byId("fiscal242Saidas").files?.length]]
      .forEach(([label, ready]) => {
        const chip = node("span", "fiscal-ai-source" + (ready ? " is-ready" : ""), (ready ? "✓ " : "+ ") + label);
        area.appendChild(chip);
      });
    const hasDocuments = !!byId("fiscal242Entradas").files?.length || !!byId("fiscal242Saidas").files?.length;
    byId("fiscal242AISourceNote").textContent = hasDocuments ?
      "Os documentos anexados serão cruzados localmente. A IA receberá os totais do cruzamento e uma seleção das pendências." :
      "Resumo e Razão formam a base da análise. Entradas e Saídas anexadas em Resultados complementam as evidências.";
  }
  function selectedAIRequest() {
    if (!previewBody) return null;
    if (aiInputBody) return aiInputBody;
    aiInputBody = new FormData();
    for (const [key, value] of previewBody.entries()) aiInputBody.append(key, value);
    for (const [id, key] of [["fiscal242Entradas", "entradas"], ["fiscal242Saidas", "saidas"]]) {
      [...byId(id).files].forEach(file => aiInputBody.append(key, file));
    }
    return aiInputBody;
  }

  aiButton.addEventListener("click", async () => {
    if (!previewBody || !aiConfigured) return;
    const requestBody = selectedAIRequest();
    const resuming = pendingAIState?.snapshot === requestBody;
    if (!resuming) aiReport = null;
    aiRetry.hidden = true;
    aiExport.disabled = true;
    aiController?.abort(); const controller = new AbortController(); aiController = controller;
    const snapshot = requestBody; aiButton.disabled = true;
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
      if (controller.signal.aborted || selectedAIRequest() !== snapshot) return;
      aiReport = result;
      const support = result.apoio_documental;
      if (support?.tipos?.length) byId("fiscal242AISourceNote").textContent =
        support.documentos_lidos + " linhas fiscais cruzadas localmente · " + support.conciliados + " conciliadas. " +
        (support.contas_resolvidas?.length ? support.contas_resolvidas.length + " conta(s) resolvida(s) sem chamada de IA. " : "") +
        "A IA recebeu somente o contexto necessário e as pendências selecionadas; a cobertura aparece em cada conta.";
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
      } else if (result.provedor === "local") {
        aiProvider.textContent = "Conferência local · sem chamada de IA";
      }
      aiExport.disabled = !(Array.isArray(result.analises) && result.analises.length);
      const providerLabel = result.provedor === "cooperacao" ? (result.nomes_provedores || "Gemini + Groq") : result.provedor === "groq" ? "GroqCloud" : result.provedor === "openrouter" ? "OpenRouter" : result.provedor === "gemini" ? "Gemini" : "IA";
      aiInlineStatus.textContent = result.provedor === "local" ? "Conferência concluída localmente; não há pendências para enviar à IA." : result.analises?.length
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
        (result.fallback_usado ? " Houve uso de provedor de reserva nos pareceres recebidos." : "");
    } catch (error) {
      if (!controller.signal.aborted && selectedAIRequest() === snapshot) {
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
    const acumuladores = [...byId("fiscal242Acumuladores").files];
    const razao = [...byId("fiscal242Razao").files];
    if (!acumuladores.length || !razao.length) throw new Error("Selecione o Resumo por Acumulador e o Razão.");
    return {acumuladores, razao};
  };
  function buildFormData() {
    const files = selectedFiles();
    const body = new FormData();
    files.acumuladores.forEach(file => body.append("acumuladores", file));
    files.razao.forEach(file => body.append("razao", file));
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
    resetAccountAnalyses();
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
    previewBody = null; aiInputBody = null; syncAISources();
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
  function fiscalComparisonReading(row, entries = []) {
    const credit = row.tipo === "SAÍDAS";
    const side = credit ? "créditos" : "débitos";
    const movements = Math.abs(Number(row.contabil || 0)) <= 0.01 && row.extras > 0
      ? entries.filter(item => String(item.conta) === String(row.conta) &&
      String(item.natureza).includes(credit ? "CRÉDITO" : "DÉBITO")) : [];
    const noneSelected = movements.length > 0 && movements.every(item => item.classificacao === "ALERTA - NÃO FISCAL");
    const separated = Math.round((Number(row.total_conta || 0) - Number(row.contabil || 0)) * 100) / 100 || 0;
    const reasons = [];
    if (row.situacao === "AUSENTE NO CONTÁBIL") reasons.push("Sem " + side + " no relatório");
    if (row.extras) reasons.push(row.extras + " mov. fora da seleção");
    if (row.sem_evidencia) reasons.push(row.sem_evidencia + " histórico(s) a validar");
    if (!reasons.length) reasons.push(Math.abs(Number(row.diferenca || 0)) <= 0.01
      ? "Sem diferença nos totais comparados" : "Valores comparados diferentes");
    return {side, noneSelected, separated, reason:reasons.join(" · ")};
  }

  const accountAnalysisCache = new Map();
  function resetAccountAnalyses() {
    for (const state of accountAnalysisCache.values()) { state.controller?.abort(); clearInterval(state.timer); }
    accountAnalysisCache.clear();
  }
  function accountReviewLog(contextId) {
    const valid = /^[a-f0-9]{64}$/.test(contextId || "");
    const storageKey = "razync:fiscal:review:v1:" + contextId;
    function read() {
      try {
        const parsed = JSON.parse(globalThis.localStorage?.getItem(storageKey) || "{}");
        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
      } catch (_) { return {}; }
    }
    return {
      available: valid,
      entries: () => valid ? read() : {},
      get: key => {
        const saved = valid ? read()[key] : null;
        return saved && typeof saved.note === "string" && saved.note.length <= 1200 && ["resolved","pending"].includes(saved.status) ? saved : null;
      },
      save(key, note, title, resolved = true) {
        if (!valid || !globalThis.localStorage) throw new Error("O navegador não permite salvar este registro.");
        const entries = read();
        entries[key] = {status:resolved ? "resolved" : "pending", note:note.trim().slice(0,1200), title:String(title).slice(0,240), updatedAt:new Date().toISOString()};
        globalThis.localStorage.setItem(storageKey, JSON.stringify(entries));
      }
    };
  }
  function accountResolutionControl(log, key, title, onChange) {
    const host = node("div", "fiscal-account-resolution");
    function paint() {
      host.replaceChildren();
      const saved = log.get(key), resolved = saved?.status === "resolved";
      if (resolved) {
        host.append(node("strong", "fiscal-account-resolution-status", "Resolvido manualmente"), node("p", "", saved.note));
        const reopen = node("button", "fiscal-account-resolution-link", "Reabrir item"); reopen.type = "button";
        reopen.addEventListener("click", () => {
          try { log.save(key, saved.note, title, false); paint(); onChange(); }
          catch (_) { host.appendChild(node("p", "fiscal-account-resolution-error", "Não foi possível reabrir o item. O registro anterior foi preservado.")); }
        }); host.appendChild(reopen); return;
      }
      const editor = node("details", "fiscal-account-resolution-editor");
      editor.appendChild(node("summary", "", "Registrar resolução"));
      const label = node("label", "", "O que foi confirmado ou corrigido?");
      const input = node("textarea"); input.rows = 2; input.maxLength = 1200; input.value = saved?.note || "";
      input.setAttribute("aria-label", "Justificativa para " + title); label.appendChild(input);
      const save = node("button", "fiscal-account-resolution-save", "Salvar resolução"); save.type = "button";
      const error = node("p", "fiscal-account-resolution-error"); error.setAttribute("role", "status");
      save.addEventListener("click", () => {
        const note = input.value.trim();
        if (!note) { error.textContent = "Informe a confirmação ou correção realizada."; input.focus(); return; }
        try { log.save(key, note, title); paint(); onChange(); }
        catch (_) { error.textContent = "Não foi possível salvar neste navegador. O item continua pendente."; }
      });
      editor.append(label, save, error); host.appendChild(editor);
    }
    paint(); return host;
  }

  function renderHybridOpinion(item, cached, scope = {}) {
    const report = item.investigacao_hibrida, summary = report.resumo, counts = report.contagens;
    const content = node("div", "fiscal-account-opinion fiscal-hybrid-opinion");
    const ai = report.ia || {};
    content.appendChild(node("p", "fiscal-account-opinion-source", (ai.estado === "concluida" ? "Análise local com priorização por IA externa" : "Análise local · sem participação de IA externa") + (cached ? " · resultado reaproveitado" : "")));
    content.appendChild(node("p", "fiscal-account-analysis-context", [summary.empresa_nome || summary.empresa || "Empresa dos relatórios", "Filial " + (summary.filial || "não identificada"),
      "Conta " + summary.conta, summary.tipo, "Acumulador " + (summary.acumulador || "não identificado"),
      [summary.competencia?.inicio,summary.competencia?.fim].filter(Boolean).join(" a ")].join(" · ")));
    const conclusion = node("section", "fiscal-account-opinion-conclusion");
    const level = {sem_divergencia:"Totais conferem",hipotese:"Hipóteses a confirmar",inconclusiva:"Causa inconclusiva"}[report.conclusao.grau] || "Revisão necessária";
    conclusion.append(node("h5", "", level), node("p", "", report.conclusao.texto));
    const values = node("dl", "fiscal-account-opinion-values");
    for (const [label,key] of [["Fiscal","fiscal"],["Razão considerado","contabil"],["Diferença","diferenca"]]) {
      const entry=node("div", key === "diferenca" ? "is-difference" : "");
      entry.append(node("dt","",label),node("dd","",money.format(Number(summary[key])))); values.appendChild(entry);
    }
    conclusion.appendChild(values); content.appendChild(conclusion);
    const sourceGroup = typeof documentaryGroups === "undefined" ? null : documentaryGroups.find(g => String(g.conta) === String(summary.conta) && g.tipo === summary.tipo);
    const unmatched = scope.acumulador ? [] : (sourceGroup?.razao_sem_vinculo || sourceGroup?.razao_pendente || []);
    if (unmatched.length) {
      const action = node("section", "fiscal-priority-findings");
      action.append(node("h5", "", "Confira primeiro · Razão sem documento vinculado"),
        node("p", "", unmatched.length + " movimento(s) ainda não foram associados aos documentos anexados. Sem vínculo não significa lançamento incorreto."));
      [...unmatched].sort((a,b)=>Math.abs(b.valor)-Math.abs(a.valor)).slice(0,20).forEach(m=>{
        const row=node("p");
        row.append(node("strong","",money.format(Number(m.valor)) + " · " + (m.data || "Data não informada")),
          node("span","",m.historico || "Histórico não informado"),
          node("small","", "Referência " + m.id + ". Localize o documento indicado no histórico e confira período, filial e conta antes de decidir por qualquer ajuste."));
        action.appendChild(row);
      });
      if(unmatched.length>20)action.appendChild(node("small","", "20 de " + unmatched.length + " movimentos exibidos; consulte o filtro Razão sem vínculo para a lista completa."));
      content.appendChild(action);
    }
    const bridge=report.composicao_diferenca;
    if(bridge){
      content.appendChild(node("h5","","Como a diferença se compõe"));
      if(bridge.documentos_lidos != null)content.appendChild(node("p","", "Documentos fiscais lidos: " + money.format(Number(bridge.documentos_lidos)) +
        " · Resumo menos documentos: " + money.format(Number(bridge.lacuna_documental))));
      if(bridge.disponivel){
        const parts=node("dl","fiscal-hybrid-bridge");
        bridge.itens.filter(part=>Math.abs(Number(part.valor))>=.005).forEach(part=>{const entry=node("div");entry.append(node("dt","",part.descricao),node("dd","",money.format(Number(part.valor))));parts.appendChild(entry);});
        const residual=node("div","is-residual");residual.append(node("dt","","Residual sem composição"),node("dd","",money.format(Number(bridge.residual))));parts.appendChild(residual);content.appendChild(parts);
        content.appendChild(node("p","",bridge.fecha_aritmeticamente ? "A composição reproduz a diferença inicial em centavos. Isso não comprova a causa contábil." : "A composição não fecha com a diferença inicial. O residual precisa de investigação adicional."));
      }else content.appendChild(node("p","","Ainda não há detalhamento suficiente para compor a diferença. Anexe o acompanhamento fiscal na etapa documental."));
    }
    content.append(node("h5", "", "Investigação realizada"),node("p", "fiscal-hybrid-coverage",
      counts.lancamentos_examinados + " lançamentos examinados · " + counts.documentos_examinados + " linhas fiscais examinadas · " + counts.correspondencias + " linhas fiscais conciliadas"));
    const checks=node("ul","fiscal-hybrid-checks"); report.verificacoes.forEach(text=>checks.appendChild(node("li","",text))); content.appendChild(checks);
    const aiNames={groq:"Groq",gemini:"Gemini",openrouter:"OpenRouter"};
    const aiStatus=node("p","fiscal-hybrid-ai-status");
    aiStatus.textContent=(ai.estado === "concluida" ? "Prioridade assistida por " + (aiNames[ai.provedor] || "IA gratuita") + ". " : "") + ai.motivo +
      " " + (cached ? "Nenhuma nova chamada nesta consulta." : (ai.chamadas || 0) + " chamada(s) externa(s).") + " Relatórios e históricos não foram enviados.";
    content.appendChild(aiStatus);
    if (report.hipoteses.length) {
      content.appendChild(node("h5","","Indícios e confirmação necessária"));
      const list=node("ol","fiscal-hybrid-hypotheses");
      const priorities=ai.prioridades || [];
      const ordered=[...report.hipoteses].sort((a,b)=>(priorities.includes(a.id)?priorities.indexOf(a.id):99)-(priorities.includes(b.id)?priorities.indexOf(b.id):99));
      ordered.forEach(h=>{
        const li=node("li"); li.append(node("strong","",h.titulo),...(h.comparacao ? [] : [node("p","",h.explicacao)]));
        if(h.comparacao){
          const c=h.comparacao;
          li.appendChild(node("p","","Documento " + (c.nota || "não identificado") + (c.serie ? " · Série " + c.serie : "") +
            " · Fiscal: " + money.format(Number(c.fiscal)) + " · Razão candidato: " + (c.contabil == null ? "vínculo não confirmado" : money.format(Number(c.contabil)))));
          li.appendChild(node("p","","Data fiscal: " + (c.data_fiscal || "não informada") + " · Datas no Razão: " + (c.datas_razao.join(", ") || "não identificadas") +
            " · Contas candidatas: " + (c.contas_candidatas.join(", ") || "nenhuma identificada")));
        }
        if(h.diferenca_documental != null)li.appendChild(node("p","","Diferença documental: " + money.format(Number(h.diferenca_documental))));
        if(h.soma != null)li.appendChild(node("p","","Soma: " + money.format(Number(h.soma)) + " · Residual: " + money.format(Number(h.residual))));
        if(h.criterio)li.appendChild(node("small","",h.criterio));
        li.append(node("p","fiscal-hybrid-refs","Evidências: " + (h.referencias.join(", ") || "sem referência individual")),...(h.comparacao ? [] : [node("p","","Para confirmar: " + h.falta_confirmar)]));
        list.appendChild(li);
      }); content.appendChild(list);
      if(ordered.some(h=>h.comparacao))content.appendChild(node("p","fiscal-hybrid-confirmation","Como conferir as notas acima: compare o valor integral, parcelas, descontos e redutores documentados. Só considere uma correção depois de confirmar os componentes e a contrapartida no documento de origem."));
      if(counts.hipoteses_disponiveis > ordered.length)content.appendChild(node("p","",ordered.length + " de " + counts.hipoteses_disponiveis + " indícios exibidos; consulte o cruzamento documental para a relação integral."));
    }
    const relevantRefs=new Set(report.hipoteses.flatMap(h=>h.referencias || []));
    unmatched.forEach(m=>relevantRefs.add(m.id));
    const focusedEvidence=relevantRefs.size ? report.evidencias.filter(e=>relevantRefs.has(e.referencia)) : report.evidencias;
    if(report.evidencias.length){
      const evidenceDetails=node("details","fiscal-focused-evidence");
      evidenceDetails.appendChild(node("summary","","Consultar evidências das pendências (" + focusedEvidence.length + ")"));
      const scroll=node("div","fiscal-hybrid-evidence-scroll"); scroll.tabIndex=0; scroll.setAttribute("role","region");scroll.setAttribute("aria-label","Evidências da investigação");
      const table=node("table","fiscal-table"); const head=node("thead"),header=node("tr"),body=node("tbody");
      ["Referência / origem","Data","Documento / conta","Histórico","Valor"].forEach(text=>{const th=node("th","",text);th.setAttribute("scope","col");header.appendChild(th);});head.appendChild(header);
      focusedEvidence.forEach(e=>{const tr=node("tr"); [e.referencia + " · " + e.origem,e.data || "Não informada",
        [e.nota && "Nota " + e.nota,e.serie && "Série " + e.serie,e.conta && "Conta " + e.conta,e.acumulador && "Acum. " + e.acumulador].filter(Boolean).join(" · ") || "Não identificado",
        e.historico || "Sem histórico no relatório",e.valor == null ? "—" : money.format(Number(e.valor))].forEach(text=>tr.appendChild(node("td","",text)));body.appendChild(tr);});
      table.append(head,body);scroll.appendChild(table);evidenceDetails.appendChild(scroll);content.appendChild(evidenceDetails);
      content.appendChild(node("small","",focusedEvidence.length + " evidências relacionadas aos indícios exibidos. As demais podem ser consultadas na conferência documental. Os arquivos originais permanecem íntegros."));
    }
    if(report.limitacoes.length){const limits=node("ul","fiscal-hybrid-limits");report.limitacoes.forEach(text=>limits.appendChild(node("li","",text)));content.append(node("h5","","Limites e dados faltantes"),limits);}
    content.appendChild(node("p","fiscal-account-opinion-limit","Nenhum lançamento foi incluído, excluído ou alterado. Confirme os documentos antes de qualquer correção."));
    return content;
  }
  function renderAccountOpinion(result, scope) {
    if(result.analises?.[0]?.investigacao_hibrida)return renderHybridOpinion(result.analises[0],result.cache_reutilizado,scope);
    const content = node("div", "fiscal-account-opinion");
    const item = result.analises?.[0];
    if (!item) {
      const local = node("section", "fiscal-account-opinion-local");
      local.append(node("span", "fiscal-account-opinion-eyebrow", "CONFERÊNCIA LOCAL"),
        node("h5", "", "Sem pendências para enviar à IA"),
        node("p", "", result.aviso || "Não há pendências nesta seleção para enviar à IA."),
        node("small", "", "Resultado obtido pelo cruzamento local, sem chamada de IA."));
      content.appendChild(local); return content;
    }
    const reading = item.parecer?.leitura_comparacao || {};
    const executive = item.parecer?.resumo_executivo || {};
    content.appendChild(node("p", "fiscal-account-opinion-source", aiSourceLabel(item) +
      (result.cache_reutilizado || result.contas_reutilizadas ? " · parecer reaproveitado" : "")));
    const conclusion = node("section", "fiscal-account-opinion-conclusion");
    conclusion.append(node("h5", "", "Conclusão desta seleção"), node("p", "", executive.conclusao || reading.resultado || item.explicacao || "Confira as evidências antes de concluir."));
    if (item.valores) {
      const values = node("dl", "fiscal-account-opinion-values");
      for (const [label,key] of [["Fiscal","fiscal"],["Razão na comparação","contabil"],["Diferença","diferenca"]]) {
        if (item.valores[key] == null || !Number.isFinite(Number(item.valores[key]))) continue;
        const entry = node("div", key === "diferenca" ? "is-difference" : "");
        entry.append(node("dt", "", label), node("dd", "", money.format(Number(item.valores[key])))); values.appendChild(entry);
      }
      if (values.children.length) conclusion.appendChild(values);
    }
    content.appendChild(conclusion);
    const grid = node("div", "fiscal-account-opinion-grid");
    const evidence = node("section", "fiscal-account-opinion-reading");
    const review = node("section", "fiscal-account-opinion-review");
    if (reading.observacoes?.length) {
      const facts = node("ul", "fiscal-account-opinion-facts");
      reading.observacoes.slice(0, 3).forEach(text => facts.appendChild(node("li", "", text)));
      evidence.append(node("h5", "", "O que os relatórios mostram"),
        node("small", "fiscal-account-opinion-origin", "Cruzamento calculado pelo Razync · não comprova a causa"), facts);
    }
    const interpretation = item.parecer?.analise_exibicao;
    if (interpretation && interpretation !== executive.conclusao && interpretation !== reading.resultado) {
      evidence.append(node("h5", "", item.provedor === "local" ? "O que ainda precisa de confirmação" : "Hipótese da IA · a confirmar"));
      evidence.appendChild(node("p", "fiscal-account-opinion-interpretation", interpretation));
    }
    const log = accountReviewLog(result.contexto_revisao);
    const reviewItems = [], reviewGroups = [];
    let pendingOnly = false;
    const progress = node("p", "fiscal-account-review-progress"); progress.setAttribute("role", "status");
    const filter = node("button", "fiscal-account-review-filter", "Só pendentes"); filter.type = "button"; filter.setAttribute("aria-pressed", "false");
    function updateReview() {
      const resolved = reviewItems.filter(entry => log.get(entry.key)?.status === "resolved").length;
      const pending = reviewItems.length - resolved;
      progress.textContent = "Itens exibidos: " + pending + (pending === 1 ? " pendente" : " pendentes") + " · " + resolved + (resolved === 1 ? " resolvido manualmente" : " resolvidos manualmente");
      reviewItems.forEach(entry => { entry.host.hidden = pendingOnly && log.get(entry.key)?.status === "resolved"; });
      reviewGroups.forEach(group => { group.host.hidden = pendingOnly && group.keys.length > 0 && group.keys.every(key => log.get(key)?.status === "resolved"); });
    }
    function track(host, key, title) {
      if (!log.available) return;
      reviewItems.push({host,key}); host.appendChild(accountResolutionControl(log,key,title,updateReview));
    }
    filter.addEventListener("click", () => { pendingOnly = !pendingOnly; filter.setAttribute("aria-pressed", String(pendingOnly)); updateReview(); });
    const steps = reading.orientacoes || [];
    if (steps.length) {
      const checklist = node("ol", "fiscal-account-opinion-steps");
      steps.forEach(step => {
        const li = node("li"), trackedKeys = [];
        if (step.ordem_revisao) li.appendChild(node("small", "fiscal-account-priority", "Prioridade " + step.ordem_revisao));
        li.appendChild(node("strong", "", step.acao));
        if (step.prioridade_motivo) li.appendChild(node("p", "fiscal-account-priority-reason", step.prioridade_motivo));
        if (step.explicacao_simples || step.objetivo) li.appendChild(node("p", "", step.explicacao_simples || step.objetivo));
        if (step.documentos?.length) {
          const references = node("div", "fiscal-account-opinion-refs");
          for (const doc of step.documentos) {
            const reference = node("article", "fiscal-account-opinion-reference");
            reference.appendChild(node("strong", "", doc.titulo || doc.referencia || "Documento"));
            if (doc.detalhes) {
              const fields = node("dl", "fiscal-account-opinion-reference-fields");
              for (const text of String(doc.detalhes).split(" · ")) {
                const colon = text.indexOf(":");
                const field = node("div", colon < 0 ? "is-full" : "");
                if (colon >= 0) field.append(node("dt", "", text.slice(0,colon)), node("dd", "", text.slice(colon+1).trim()));
                else field.appendChild(node("dd", "", text));
                fields.appendChild(field);
              }
              reference.appendChild(fields);
            }
            if (doc.onde_conferir) reference.append(node("small", "fiscal-account-opinion-origin", "Onde conferir"), node("p", "", doc.onde_conferir));
            if (doc.historico_candidato) reference.appendChild(node("p", "", "Histórico do candidato: " + doc.historico_candidato));
            if (doc.campos_a_confirmar) reference.appendChild(node("p", "", doc.campos_a_confirmar));
            if (doc.vinculo) reference.appendChild(node("small", "fiscal-account-opinion-origin", doc.vinculo));
            const reviewKey = JSON.stringify([step.categoria || step.acao, doc.referencia || doc.titulo]);
            trackedKeys.push(reviewKey); track(reference, reviewKey, doc.titulo || doc.referencia || step.acao);
            references.appendChild(reference);
          }
          li.appendChild(references);
        }
        for (const [label, text] of [
          ["Onde conferir", step.onde_conferir],
          ["Confirme primeiro", [step.explicacao_simples ? step.objetivo : "", step.para_concluir].filter(Boolean).join(" ")],
          ["Solução após confirmar", step.solucao_condicional],
          ["Como validar", step.resultado_esperado]
        ]) {
          if (!text) continue;
          const criterion = node("div", "fiscal-account-opinion-criterion");
          criterion.append(node("small", "", label), node("p", "", text)); li.appendChild(criterion);
        }
        if (step.quando_reavaliar) {
          const reconsider = node("p", "fiscal-account-opinion-reconsider");
          reconsider.append(node("strong", "", "Quando reavaliar: "), node("span", "", step.quando_reavaliar)); li.appendChild(reconsider);
        }
        if (!step.documentos?.length) {
          const reviewKey = JSON.stringify(["orientacao",step.categoria || step.acao]);
          trackedKeys.push(reviewKey); track(li,reviewKey,step.acao);
        }
        reviewGroups.push({host:li,keys:trackedKeys});
        checklist.appendChild(li);
      });
      review.append(node("h5", "", "Plano de revisão"));
      if (reading.criterio_prioridade) {
        const criterion = node("details", "fiscal-account-review-order");
        criterion.append(node("summary", "", "Por que esta ordem?"), node("p", "", reading.criterio_prioridade)); review.appendChild(criterion);
      }
      if (log.available) {
        const tracking = node("div", "fiscal-account-review-tracking");
        tracking.append(progress, filter, node("small", "", "Anotações salvas neste navegador para estas evidências. O registro manual não altera totais ou conciliação. O acompanhamento cobre os itens exibidos, não todas as pendências dos arquivos."));
        review.appendChild(tracking); updateReview();
      }
      review.appendChild(checklist);
    } else if (executive.primeiro_passo) review.append(node("h5", "", "O que conferir agora"), node("p", "", executive.primeiro_passo));
    if (evidence.children.length) grid.appendChild(evidence);
    if (review.children.length) grid.appendChild(review);
    if (grid.children.length) content.appendChild(grid);
    const extra = node("details", "fiscal-account-opinion-details");
    extra.appendChild(node("summary", "", "Ver evidências e critérios completos"));
    for (const text of [...(reading.observacoes || []).slice(3), ...(reading.explicacoes || [])]) extra.appendChild(node("p", "", text));
    if (reading.criterio) extra.appendChild(node("p", "", reading.criterio));
    const considered = renderAIConsidered(item), excluded = renderAIExcluded(item), documentary = renderAIDocumentary(item, true);
    if (documentary) extra.appendChild(documentary);
    if (considered) extra.appendChild(considered);
    if (excluded) extra.appendChild(excluded);
    const cases = renderAICases(item); if (cases) extra.appendChild(cases);
    const limits = renderAILimits(item); if (limits) extra.appendChild(limits);
    if (extra.children.length > 1) content.appendChild(extra);
    content.appendChild(node("p", "fiscal-account-opinion-limit", "Sugestões para revisão. A análise não altera os valores nem confirma a natureza contábil dos lançamentos."));
    return content;
  }
  function renderFiscalAssistant(result, scope, state) {
    const host=node("section","fiscal-document-assistant");
    host.append(node("p","fiscal-agent-chat-hint","Pergunte sobre esta conta. Respostas baseadas apenas nos registros consultados."));
    const session=result.assistente;
    if(!session?.disponivel){host.appendChild(node("p","",session?.motivo || "O assistente ficará disponível após uma nova análise nesta versão do servidor."));return host;}
    const thread=node("div","fiscal-agent-thread");thread.setAttribute("role","log");thread.setAttribute("aria-label","Conversa sobre a conta");
    state.agentMessages ||= [];
    const renderMessage=message=>{
      const entry=node("article","fiscal-agent-message");
      entry.append(node("strong","",message.question));
      if(message.error){entry.appendChild(node("p","",message.error));thread.appendChild(entry);return;}
      const answer=message.answer;
      entry.append(node("small","fiscal-agent-source",answer.origem==="ia" ? "Interpretação por " + answer.provedor + " · " + answer.modelo : "Consulta local dos documentos · sem IA externa"),
        node("p","",answer.explicacao));
      if(answer.aviso_ia)entry.appendChild(node("p","fiscal-agent-warning",answer.aviso_ia));
      const totals=node("p","fiscal-agent-totals");
      totals.textContent="Fiscal: " + money.format(Number(answer.resumo.fiscal)) + " · Razão: " + money.format(Number(answer.resumo.contabil)) + " · Diferença: " + money.format(Number(answer.resumo.diferenca));
      entry.appendChild(totals);
      const steps=node("ol");(answer.proximos_passos || []).forEach(text=>steps.appendChild(node("li","",text)));entry.appendChild(steps);
      entry.appendChild(node("small","",answer.ferramenta + " · " + answer.exibidos + " de " + answer.encontrados + " registros exibidos. Ausência na busca não comprova ausência na escrituração."));
      if(answer.evidencias?.length){
        const details=node("details");details.appendChild(node("summary","","Evidências consultadas (" + answer.evidencias.length + ")"));
        answer.evidencias.forEach(r=>details.appendChild(node("p","fiscal-agent-evidence",r.referencia + " · " + r.origem + " · Conta " + r.conta + " · " + (r.nota ? "Nota " + r.nota + " · " : "") + r.data + " · " + money.format(Number(r.valor)) + "\n" + (r.historico || ""))));
        entry.appendChild(details);
      }
      if(answer.limites?.length){const limits=node("details");limits.appendChild(node("summary","","Limites desta consulta"));answer.limites.forEach(text=>limits.appendChild(node("p","",text)));entry.appendChild(limits);}
      thread.appendChild(entry);
    };
    state.agentMessages.forEach(renderMessage);host.appendChild(thread);
    const suggestions=node("div","fiscal-agent-suggestions");
    const input=node("textarea");input.rows=2;input.maxLength=1000;input.placeholder="Ex.: Por que essa conta não bate? Ou: procure a nota 149599";input.setAttribute("aria-label","Pergunta sobre os documentos desta conta");
    for(const [label,text] of [["Explicar diferença","Explique a diferença e as pendências"],["Sem vínculo","Quais movimentos estão sem vínculo?"]]){const b=node("button","",label);b.type="button";b.title=text;b.addEventListener("click",()=>{input.value=text;input.focus();});suggestions.appendChild(b);}
    const permission=node("label","fiscal-agent-permission"),toggle=node("input");toggle.type="checkbox";toggle.checked=false;
    permission.append(toggle,node("span","","Usar IA externa nesta pergunta: envia a pergunta e até 20 evidências estruturadas ao provedor gratuito configurado. Os arquivos, nomes e históricos não são enviados. Evite incluir dados pessoais na pergunta."));
    const send=node("button","fiscal-agent-send","Perguntar");send.type="button";
    const cancel=node("button","","Cancelar espera");cancel.type="button";cancel.hidden=true;
    const status=node("p","fiscal-agent-status");status.setAttribute("role","status");
    send.addEventListener("click",async()=>{
      const question=input.value.trim();if(question.length<3){status.textContent="Escreva uma pergunta com pelo menos três caracteres.";return;}
      if(state.chatPending)return;
      state.chatPending=true;const controller=new AbortController();state.chatController=controller;
      send.disabled=true;cancel.hidden=false;input.disabled=true;toggle.disabled=true;status.textContent="Consultando os registros desta seleção…";
      const timeout=setTimeout(()=>controller.abort(),45000);
      try{
        const response=await fetch(API()+"/api/v1/conferencia-fiscal/ia/conta/conversa",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({session:session.session,pergunta:question,usar_ia:toggle.checked}),signal:controller.signal});
        if(!response.ok){
          if(response.status===410){state.result=null;state.agentMessages=[];state.error="A conversa expirou. Clique em Tentar investigação novamente para preparar os documentos.";state.paint();}
          throw new Error(await responseError(response));
        }
        const answer=await response.json();
        if(controller.signal.aborted || state.source!==previewBody || state.result!==result)return;
        if(answer.escopo?.conta!==String(scope.conta) || answer.escopo?.tipo!==scope.tipo || (answer.escopo?.acumulador || "")!==(scope.acumulador || ""))throw new Error("Resposta de outra seleção bloqueada.");
        const message={question,answer};state.agentMessages.push(message);renderMessage(message);input.value="";status.textContent="Resposta pronta. Confira as evidências antes de decidir um ajuste.";
      }catch(error){status.textContent=controller.signal.aborted ? "Espera encerrada. Nenhum lançamento foi alterado." : error.message || "Não foi possível consultar o assistente.";}
      finally{clearTimeout(timeout);state.chatPending=false;state.chatController=null;send.disabled=false;cancel.hidden=true;input.disabled=false;toggle.disabled=false;}
    });
    cancel.addEventListener("click",()=>state.chatController?.abort());
    const composer = node("div", "fiscal-agent-chat-composer");
    const permissionDetails = node("details", "fiscal-agent-chat-options");
    permissionDetails.append(node("summary", "", "IA externa · opcional"), permission);
    toggle.addEventListener("change",()=>{permissionDetails.querySelector("summary").textContent=toggle.checked ? "IA externa · ativada" : "IA externa · opcional";});
    const sendRow = node("div", "fiscal-agent-chat-send-row");
    sendRow.append(send, cancel);
    const inputRow=node("div","fiscal-agent-input-row");inputRow.append(input,sendRow);
    composer.append(suggestions, inputRow, permissionDetails, status);
    host.append(composer, node("small", "", "Conversa temporária, limitada à empresa, filial, conta e tipo. Confirme as evidências nos documentos originais."));
    host.composer = composer;
    input.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        send.click();
      }
    });
    return host;
  }

  // A conversa mostra primeiro a conclusão e os valores, sem empilhar o relatório
  // inteiro em uma janela pequena. O parecer integral permanece acessível sob demanda.
  function renderCompactFiscalChatReport(result, scope) {
    const item = result.analises?.[0] || {};
    const hybrid = item.investigacao_hibrida || {};
    const summary = hybrid.resumo || item.valores || {};
    const conclusion = hybrid.conclusao?.texto ||
      item.parecer?.resumo_executivo?.conclusao ||
      item.parecer?.leitura_comparacao?.resultado ||
      item.explicacao || "Confira os movimentos e documentos antes de concluir.";
    const report = node("section", "fiscal-account-ai-chat-report");
    report.append(node("span", "fiscal-account-ai-chat-message-head", "✦  Resultado da investigação"),
      node("p", "fiscal-chat-conclusion", conclusion));
    const labels = [["Fiscal", "fiscal"], ["Razão", "contabil"], ["Diferença", "diferenca"]];
    const metrics = node("dl", "fiscal-chat-metrics");
    for (const [label, key] of labels) {
      if (summary[key] == null || !Number.isFinite(Number(summary[key]))) continue;
      const metric = node("div", key === "diferenca" ? "is-difference" : "");
      metric.append(node("dt", "", label), node("dd", "", money.format(Number(summary[key]))));
      metrics.appendChild(metric);
    }
    if (metrics.children.length) report.appendChild(metrics);
    const accuracy = hybrid.conclusao?.grau;
    if (accuracy === "hipotese" || accuracy === "inconclusiva")
      report.appendChild(node("p", "fiscal-chat-caution", "A causa ainda não está comprovada. Confirme as evidências antes de corrigir lançamentos."));
    const detail = node("details", "fiscal-chat-full-report");
    detail.append(node("summary", "", "Ver investigação completa"));
    let fullReportLoaded = false;
    detail.addEventListener("toggle", () => {
      if (!detail.open || fullReportLoaded) return;
      detail.appendChild(renderAccountOpinion(result, scope));
      fullReportLoaded = true;
    });
    report.appendChild(detail);
    return report;
  }

  function createAccountAnalysis(scope) {
    const key = [scope.origem, scope.conta, scope.tipo, scope.acumulador || ""].join(":");
    const fileId = scope.tipo === "SAÍDAS" ? "fiscal242Saidas" : "fiscal242Entradas";
    const file = scope.origem === "documentos" ? byId(fileId).files?.[0] : null;
    const files = scope.origem === "documentos" ? Array.from(byId(fileId).files || []) : [];
    let state = accountAnalysisCache.get(key);
    if (!state || state.source !== previewBody || state.file !== file || files.length !== state.files?.length || files.some((item,index)=>item !== state.files[index])) {
      state?.controller?.abort();
      state = {source:previewBody, file, files, useAI:false, pending:false, result:null, error:"", expanded:false};
      accountAnalysisCache.set(key, state);
    }
    const area = node("section", "fiscal-account-analysis");
    area.setAttribute("aria-label", "Investigação híbrida desta seleção");
    const bar = node("div", "fiscal-account-analysis-bar");
    const button = node("button", "fiscal-account-analysis-button"); button.type = "button";
    const cancel = node("button", "fiscal-account-analysis-cancel", "Cancelar espera"); cancel.type = "button";
    const note = node("p", "fiscal-account-analysis-note", scope.acumulador
      ? "Só este acumulador, nesta conta e tipo. Os filtros de nota não alteram a base da análise."
      : "Só esta conta e este tipo. O parecer é reaproveitado enquanto os arquivos forem os mesmos.");
    const status = node("p", "fiscal-account-analysis-status"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    const aiOption=node("label","fiscal-hybrid-ai-option"),aiToggle=node("input");aiToggle.type="checkbox";aiToggle.checked=state.useAI;
    aiOption.append(aiToggle,node("span","","Permitir IA gratuita para priorizar indícios, sem enviar históricos ou identificação."));
    aiToggle.addEventListener("change",()=>{state.useAI=aiToggle.checked;state.chatController?.abort();state.agentMessages=[];state.result=null;state.paint();});
    const exportButton = node("button", "fiscal-account-analysis-export", "Exportar parecer"); exportButton.type = "button";
    const body = node("div", "fiscal-account-analysis-body");
    const composerSlot = node("div", "fiscal-account-ai-composer-slot");
    const loading = node("section", "fiscal-account-loading"); loading.hidden = true;
    loading.setAttribute("aria-label", "Análise desta seleção em andamento");
    const loadingHead = node("div", "fiscal-account-loading-heading");
    const orbit = node("span", "fiscal-account-loading-orbit"); orbit.setAttribute("aria-hidden", "true");

    const loadingCopy = node("div", "fiscal-account-loading-copy");
    loadingCopy.appendChild(node("h5", "", "Investigando esta seleção…"));
    const elapsed = node("span", "fiscal-account-loading-time"); elapsed.setAttribute("aria-hidden", "true");
    loadingHead.append(orbit, loadingCopy, elapsed);
    const meter = node("div", "fiscal-account-loading-meter visually-hidden");
    meter.setAttribute("role", "progressbar"); meter.setAttribute("aria-label", "Aguardando retorno da análise");
    const loadingHint = node("p", "fiscal-account-loading-hint");
    loading.append(loadingHead, meter, loadingHint);
    const context = node("p", "fiscal-account-analysis-context", "Conta " + scope.conta + " · " + scope.tipo + (scope.acumulador ? " · Acumulador " + scope.acumulador : ""));
    const panelId = "fiscal-chat-" + [scope.origem, scope.conta, scope.tipo === "SAÍDAS" ? "saidas" : "entradas", scope.acumulador || "conta"].join("-");
    area.id = panelId;
    area.setAttribute("role", "region");
    area.setAttribute("aria-label", "Conversa e parecer da conta " + scope.conta);
    area.tabIndex = -1;
    const launcher = node("button", "fiscal-account-ai-fab");
    launcher.type = "button";
    launcher.textContent = "✦  Assistente IA";
    launcher.setAttribute("aria-label", "Abrir assistente da conta " + scope.conta);
    launcher.setAttribute("aria-controls", panelId);
    const chatHeading = node("div", "fiscal-account-ai-chat-heading");
    const chatIdentity = node("div", "fiscal-account-ai-chat-identity");
    const chatTitle = node("div", "fiscal-account-ai-chat-title", "Assistente Razync");
    const chatSubtitle = node("small", "fiscal-account-ai-chat-subtitle", "Conta " + scope.conta + " · " + scope.tipo + (scope.acumulador ? " · Acumulador " + scope.acumulador : ""));
    const titleWrap = node("div", "fiscal-account-ai-title-wrap");
    titleWrap.append(chatTitle, chatSubtitle);
    chatIdentity.append(node("span", "fiscal-account-ai-avatar", "✦"), titleWrap);
    const closeChat = node("button", "fiscal-account-ai-close", "×");
    closeChat.type = "button";
    closeChat.setAttribute("aria-label", "Fechar conversa e voltar à conferência");
    const chatActions = node("div", "fiscal-account-ai-header-actions");
    const expandChat = node("button", "fiscal-account-ai-expand", "⤢");
    expandChat.type="button";expandChat.setAttribute("aria-label","Ampliar assistente");expandChat.setAttribute("aria-pressed","false");
    expandChat.title="Ampliar assistente";
    expandChat.addEventListener("click",()=>{state.chatWide=!state.chatWide;paint();});
    closeChat.textContent="−";closeChat.title="Recolher assistente";
    closeChat.setAttribute("aria-label","Recolher assistente e voltar à conferência");
    exportButton.textContent = "Exportar";
    chatActions.append(exportButton, expandChat, closeChat);
    chatHeading.append(chatIdentity, chatActions);
    const aiSettings = node("details", "fiscal-account-ai-settings");
    aiSettings.append(node("summary", "", "Configurações de investigação"), aiOption);
    bar.append(aiSettings, button, cancel);
    area.append(chatHeading, status, loading, body, composerSlot, bar);
    let layout = null, renderedResult = null;
    function switchView(open, focus = false) {
      state.expanded = open;
      state.paint();
      if (focus) (open ? closeChat : launcher).focus({preventScroll:true});
    }
    launcher.addEventListener("click", async () => {
      if (state.expanded) { switchView(false, true); return; }
      switchView(true, true);
      if (!state.pending && !state.result && !state.error) await button.click();
    });
    closeChat.addEventListener("click", () => switchView(false, true));
    area.addEventListener("keydown", event => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation?.();
      switchView(false, true);
    });
    area.mount = target => {
      layout = target;
      target.comparison.hidden = false;
      area.className = "fiscal-account-analysis fiscal-account-ai-chat";
      target.shell.append(launcher, area);
      state.expanded = false;
      paint();
    };
    area.destroy = () => {
      state.chatController?.abort();
      layout?.shell.classList?.remove("fiscal-chat-open");
      state.expanded = false;
      layout = null;
      area.remove();
      launcher.remove();
    };
    function paint() {
      button.disabled = state.pending || !state.source;
      bar.hidden = Boolean(state.result);
      button.textContent = state.pending ? "Investigando…" : state.result ? "Ver investigação salva" : state.error ? "Tentar investigação novamente" : scope.acumulador ? "Investigar acumulador" : "Investigar conta";
      aiToggle.disabled = state.pending;
      launcher.textContent = state.pending ? "✦  Investigando…" : state.result ? "✦  IA · Parecer pronto" : "✦  Assistente IA";
      launcher.setAttribute("aria-expanded", String(state.expanded));
      launcher.setAttribute("aria-label", (state.expanded ? "Recolher" : "Abrir") + " assistente da conta " + scope.conta);
      cancel.hidden = !state.pending;
      exportButton.hidden = !state.result?.analises?.length;
      status.textContent = state.pending ? "Consultando os registros desta conta…" : state.error || "";
      status.className = "fiscal-account-analysis-status" + (state.pending ? " visually-hidden" : "");
      status.hidden = !status.textContent;
      body.hidden = !state.result;
      composerSlot.hidden = !state.result;
      body.setAttribute("aria-busy", String(state.pending));
      note.hidden = state.pending || Boolean(state.result);
      loading.hidden = !state.pending;
      loading.setAttribute("aria-busy", String(state.pending));
      updateLoadingTime();
      if (layout) {
        area.hidden = !state.expanded;
        area.classList.toggle("is-expanded",Boolean(state.chatWide));
        expandChat.setAttribute("aria-pressed",String(Boolean(state.chatWide)));
        expandChat.setAttribute("aria-label",state.chatWide ? "Restaurar tamanho do assistente" : "Ampliar assistente");
        expandChat.title=state.chatWide ? "Restaurar tamanho" : "Ampliar assistente";
        layout.shell.classList?.toggle("fiscal-chat-open", state.expanded);
      }
      if (state.result && renderedResult !== state.result) {
        const report = renderCompactFiscalChatReport(state.result, scope);
        const assistant = renderFiscalAssistant(state.result, scope, state);
        body.replaceChildren(report, assistant);
        composerSlot.replaceChildren(...(assistant.composer ? [assistant.composer] : []));
        renderedResult = state.result;
      }
    }
    function updateLoadingTime() {
      const seconds = state.pending ? Math.max(0, Math.floor((Date.now() - state.startedAt) / 1000)) : 0;
      elapsed.textContent = seconds < 60 ? seconds + " s" : Math.floor(seconds / 60) + " min " + seconds % 60 + " s";
      const hint = seconds >= 45 ? "O servidor ainda não respondeu. Você pode voltar à conferência enquanto aguarda." : "Aguardando retorno do servidor. Você pode consultar a conferência durante a espera.";
      if (loadingHint.textContent !== hint) loadingHint.textContent = hint;
      loadingHint.hidden = seconds < 45;
    }
    state.paint = paint; state.tick = updateLoadingTime;
    button.addEventListener("click", async () => {
      if (state.pending) return;
      if (state.result) { switchView(true, true); return; }
      if (!state.source || state.source !== previewBody) return;
      const body = new FormData();
      body.append("usar_ia",String(state.useAI));
      for (const [name, value] of state.source.entries()) if (!["entradas", "saidas", "conta", "tipo", "origem", "acumulador"].includes(name)) body.append(name, value);
      for (const name of ["conta", "tipo", "origem", "acumulador"]) body.append(name, scope[name] || "");
      if (file) [...byId(fileId).files].forEach(document => body.append(scope.tipo === "SAÍDAS" ? "saidas" : "entradas", document));
      const controller = new AbortController(); state.controller = controller;
      state.pending = true; state.expanded = true; state.error = ""; state.startedAt = Date.now(); state.paint();
      state.timer = setInterval(() => { if (state.pending) state.tick(); }, 1000);
      try {
        const response = await fetch(API() + "/api/v1/conferencia-fiscal/ia/conta", {method:"POST", body, signal:controller.signal});
        if (!response.ok) throw new Error(await responseError(response));
        const result = await response.json();
        if (controller.signal.aborted || state.source !== previewBody || accountAnalysisCache.get(key) !== state) return;
        if (result.escopo?.conta !== String(scope.conta) || result.escopo?.tipo !== scope.tipo ||
          (result.escopo?.acumulador || "") !== (scope.acumulador || "") || result.escopo?.origem !== scope.origem ||
          (result.analises || []).some(item => String(item.conta) !== String(scope.conta) || item.tipo !== scope.tipo) || (result.analises || []).length > 1) {
          throw new Error("A resposta não corresponde à seleção aberta. Nenhum parecer foi exibido.");
        }
        state.result = result;
      } catch (error) {
        state.error = controller.signal.aborted ? "Espera cancelada. Você pode consultar esta seleção novamente." : error.message || "Não foi possível analisar esta seleção.";
      } finally {
        clearInterval(state.timer); state.timer = null;
        state.pending = false; state.controller = null; state.paint();
      }
    });
    cancel.addEventListener("click", () => state.controller?.abort());
    exportButton.addEventListener("click", async () => {
      if (!state.result?.analises?.length) return;
      exportButton.disabled = true;
      try {
        const response = await fetch(API() + "/api/v1/conferencia-fiscal/ia/exportar", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({empresa_nome:data?.empresa_nome || "GERAL", filial:data?.filial_aplicada || "", analises:state.result.analises, acompanhamento_manual:Object.values(accountReviewLog(state.result.contexto_revisao).entries())})
        });
        if (!response.ok) throw new Error(await responseError(response));
        if (state.source !== previewBody || accountAnalysisCache.get(key) !== state) return;
        await downloadBlob(response, "RAZYNC_PARECER_" + scope.conta + "_" + scope.tipo + (scope.acumulador ? "_ACUM_" + scope.acumulador : "") + ".xlsx");
      } catch (error) { state.error = error.message || "Não foi possível exportar o parecer."; state.paint(); }
      finally { exportButton.disabled = false; }
    });
    paint(); return area;
  }

  function fiscalAccountSituation(row, reading) {
    if (reading.noneSelected) return {tone:"review", symbol:"!", title:"Seleção a revisar",
      explanation:"Há movimentos no Razão, mas nenhum entrou na comparação pelo histórico."};
    if (row.situacao === "AUSENTE NO CONTÁBIL") return {tone:"review", symbol:"!", title:"Sem movimentos no Razão",
      explanation:"Não foram encontrados " + reading.side + " desta conta no relatório enviado."};
    const difference = Number(row.diferenca || 0);
    if (Math.abs(difference) > 0.01) return {tone:"divergence", symbol:"≠", title:"Conta com divergência",
      explanation:"Razão na comparação " + money.format(Math.abs(difference)) +
        (difference < 0 ? " abaixo do fiscal." : " acima do fiscal.") +
        (row.extras || row.sem_evidencia ? " Há movimentos a revisar." : "")};
    if (row.extras || row.sem_evidencia || row.situacao === "CONFERE COM ALERTAS") return {
      tone:"review", symbol:"!", title:"Totais iguais · com alertas", explanation:reading.reason + ". Revise antes de concluir."};
    return {tone:"equal", symbol:"=", title:"Totais iguais", explanation:"Sem diferença nos valores comparados. A igualdade dos totais não confirma cada documento."};
  }

  function renderDetails(row) {
    detailDialog.accountAnalysis?.destroy(); detailDialog.accountAnalysis = null;
    details.replaceChildren();
    if (!row) { details.hidden = true; return; }
    details.hidden = false;
    details.setAttribute("role", "region");
    details.setAttribute("aria-label", "Detalhes da conta " + row.conta);
    const reading = fiscalComparisonReading(row, data.lancamentos || []);

    const situation = fiscalAccountSituation(row, reading);
    detailDialog.dataset.situation = situation.tone;
    const heading = node("div", "fiscal-detail-heading");
    const summary = node("div", "fiscal-detail-title");
    summary.appendChild(node("span", "fiscal-section-eyebrow", "ACUMULADORES × RAZÃO · " + row.tipo));
    const title = node("h3", "", "Conta " + row.conta);
    title.id = "fiscal242DetailTitle";
    summary.appendChild(title);
    const description = node("p", "", "Acumuladores: " + (row.descricao || "Sem descrição"));
    description.id = "fiscal242DetailDescription";
    summary.appendChild(description);
    const headingActions = node("div", "fiscal-detail-heading-actions");
    const close = node("button", "fiscal-detail-close", "Fechar ×");
    close.type = "button";
    close.setAttribute("aria-label", "Fechar detalhes da conta");
    close.addEventListener("click", () => detailDialog.close());
    headingActions.appendChild(close);
    heading.append(summary, headingActions);
    const state = node("div", "fiscal-account-situation");
    const symbol = node("span", "fiscal-account-situation-symbol", situation.symbol);
    symbol.setAttribute("aria-hidden", "true");
    const stateText = node("div", "fiscal-account-situation-copy");
    stateText.append(node("strong", "", situation.title), node("p", "", situation.explanation));
    state.append(symbol, stateText);
    byId("fiscal242DetailHeading").replaceChildren(heading, state);

    const metrics = node("div", "fiscal-detail-metrics fiscal-comparison-metrics");
    [
      ["Valor fiscal", row.fiscal, "fiscal"],
      ["Razão na comparação", row.contabil, "accounting"],
      ["Diferença", row.diferenca, "difference"]
    ].forEach(([label, amount, style]) => {
      const card = node("div", "fiscal-detail-metric fiscal-detail-metric-" + style);
      card.appendChild(node("small", "", label));
      card.appendChild(node("strong", "", money.format(Number(amount || 0))));
      if (style === "difference") {
        card.appendChild(node("span", "fiscal-detail-metric-hint",
          Math.abs(Number(amount || 0)) <= 0.01 ? "Sem diferença aritmética" : "Razão na comparação − fiscal"));
      }
      metrics.appendChild(card);
    });
    details.appendChild(metrics);
    details.appendChild(node("p", "fiscal-difference-reading", reading.noneSelected
      ? "Há movimentos no Razão, mas nenhum foi selecionado pelo histórico. Revise a seleção antes de concluir que existe uma diferença fiscal."
      : differenceMeaning(row.diferenca).replace("Contábil considerado", "Razão na comparação")));

    const bridge = node("section", "fiscal-comparison-bridge");
    bridge.appendChild(node("h4", "", "Do total do Razão ao valor comparado"));
    const bridgeValues = node("dl", "fiscal-comparison-bridge-values");
    [["Total examinado · " + reading.side, row.total_conta],
      ["Valor separado para revisão", reading.separated],
      ["Razão na comparação", row.contabil]].forEach(([label, value]) => {
      const part = node("div");
      part.append(node("dt", "", label), node("dd", "", money.format(Number(value || 0))));
      bridgeValues.appendChild(part);
    });
    bridge.append(bridgeValues, node("p", "", "Total examinado − valor separado = razão na comparação. Valores negativos preservam o efeito de estornos e redutores."));
    details.appendChild(bridge);

    const explanation = node("p", "fiscal-disclaimer fiscal-detail-explanation",
      "A comparação soma os acumuladores desta conta e deste tipo de operação. Entradas usam débitos; saídas usam créditos. " +
      "A seleção se baseia nos históricos. Movimentos separados precisam de revisão; isso não comprova que sejam não fiscais.");
    details.appendChild(explanation);
    details.appendChild(accumulatorBreakdown(row));

    if (row.extras || row.sem_evidencia) {
      const notices = node("div", "fiscal-detail-notices");
      if (row.extras) notices.appendChild(node("p", "", row.extras + " movimento(s) fora da seleção pelo histórico. Confira documentos, histórico e contrapartida antes de incluir ou excluir valores."));
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
        const classification = mov.classificacao === "ALERTA - NÃO FISCAL" ? "Fora da seleção · revisar histórico"
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
    const panel = createAccountAnalysis({origem:"resumo", conta:String(row.conta), tipo:row.tipo});
    const navigation = byId("fiscal242DetailPrevious").parentElement;
    panel.mount({header:byId("fiscal242DetailHeading"), comparison:details, footer:navigation.parentElement,
      navigation, shell:details.parentElement});
    detailDialog.accountAnalysis = panel;
  }

  const detailDialog = byId("fiscal242DetailDialog");
  const detailPrevious = byId("fiscal242DetailPrevious");
  const detailNext = byId("fiscal242DetailNext");
  let detailRows = [];
  let detailReturnKey = "";
  function syncDetailNavigation() {
    const index = detailRows.findIndex(row => keyOf(row) === selectedKey);
    detailPrevious.disabled = index <= 0;
    detailNext.disabled = index < 0 || index >= detailRows.length - 1;
    byId("fiscal242DetailPosition").textContent = (index + 1) + " de " + detailRows.length +
      " na seleção da tabela";
  }
  function openAccountDetails(key) {
    detailRows = sortFiscalRows(filteredRows(), tableSort.key, tableSort.descending);
    if (!detailRows.some(row => keyOf(row) === key)) return;
    detailReturnKey = key;
    selectedKey = key;
    renderTable();
    syncDetailNavigation();
    document.documentElement.classList.add("fiscal-account-dialog-open");
    detailDialog.showModal();
    details.scrollTop = 0;
    byId("fiscal242DetailHeading").focus({preventScroll:true});
  }
  function moveAccountDetails(direction) {
    const index = detailRows.findIndex(row => keyOf(row) === selectedKey);
    const next = index + direction;
    if (index < 0 || next < 0 || next >= detailRows.length) return;
    selectedKey = keyOf(detailRows[next]);
    renderTable();
    details.scrollTop = 0;
    syncDetailNavigation();
  }
  detailPrevious.addEventListener("click", () => moveAccountDetails(-1));
  detailNext.addEventListener("click", () => moveAccountDetails(1));
  detailDialog.addEventListener("close", () => {
    document.documentElement.classList.remove("fiscal-account-dialog-open");
    selectedKey = "";
    detailRows = [];
    renderTable();
    const opener = [...tableBody.querySelectorAll(".fiscal-account-link")]
      .find(button => button.dataset.detailKey === detailReturnKey);
    (opener || search).focus({preventScroll:true});
  });
  let detailBackdropStart = false;
  function outsideDetailPanel(event) {
    const bounds = detailDialog.getBoundingClientRect();
    return event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom;
  }
  detailDialog.addEventListener("pointerdown", event => {
    detailBackdropStart = event.target === detailDialog && outsideDetailPanel(event);
  });
  detailDialog.addEventListener("click", event => {
    if (detailBackdropStart && event.target === detailDialog && outsideDetailPanel(event)) detailDialog.close();
    detailBackdropStart = false;
  });

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
    const rows = sortFiscalRows(filteredRows(), tableSort.key, tableSort.descending);
    tableBody.replaceChildren();
    const total = (data?.contas || []).length;
    resultsCount.textContent = `Exibindo ${rows.length} de ${total} contas. Cada linha reúne uma conta e um tipo de operação. O fiscal soma os acumuladores listados; a diferença usa o razão na comparação.`;
    byId("fiscal242Empty").hidden = rows.length > 0;
    if (!rows.some(row => keyOf(row) === selectedKey)) selectedKey = "";
    rows.forEach(row => {
      const reading = fiscalComparisonReading(row, data.lancamentos || []);
      const tr = node("tr", "fiscal-result-row fiscal-result-row-" + statusClass(row.situacao));
      const id = keyOf(row);
      if (id === selectedKey) tr.classList.add("selected");
      const account = cell(tr, "", "fiscal-account");
      account.dataset.label = "Conta";
      const accountGroup = node("div", "fiscal-account-group");
      const button = node("button", "fiscal-account-link", row.conta);
      button.type = "button";
      button.dataset.detailKey = id;
      button.setAttribute("aria-label", "Ver detalhes da conta " + row.conta + " · " + row.tipo);
      button.setAttribute("aria-haspopup", "dialog");
      button.setAttribute("aria-controls", "fiscal242DetailDialog");
      button.addEventListener("click", () => openAccountDetails(id));
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
      accountingValue.dataset.label = "Razão na comparação";
      if (reading.noneSelected) accountingValue.appendChild(node("small", "fiscal-comparison-selection", "Nenhum selecionado pelo histórico"));
      if (row.extras || Math.abs(reading.separated) > 0.01) {
        accountingValue.appendChild(node("small", "fiscal-comparison-total", "Total examinado: " + money.format(Number(row.total_conta || 0))));
      }
      const diferenca = cell(tr, "", "fiscal-money fiscal-difference");
      diferenca.appendChild(node("span", "fiscal-difference-number", money.format(row.diferenca)));
      diferenca.dataset.label = "Diferença";
      diferenca.appendChild(node("small", "fiscal-table-secondary", Math.abs(Number(row.diferenca || 0)) <= 0.01 ? "Sem diferença" : row.diferenca < 0 ? "Razão abaixo do fiscal" : "Razão acima do fiscal"));
      if (Math.abs(Number(row.diferenca || 0)) <= 0.01) diferenca.classList.add("fiscal-difference-zero");
      const td = cell(tr, "", "fiscal-situation-cell");
      td.dataset.label = "Situação";
      td.appendChild(node("span", "fiscal-status fiscal-status-" + statusClass(row.situacao), reading.noneSelected ? "Revisar seleção" : statusLabels[row.situacao] || row.situacao));
      if (row.situacao !== "CONFERE") td.appendChild(node("small", "fiscal-comparison-reason", reading.reason));
      tableBody.appendChild(tr);
    });
    renderDetails(rows.find(row => keyOf(row) === selectedKey) || null);
    if (detailDialog.open && !selectedKey) detailDialog.close();
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
      ["fiscal242ProgressMatches", report.resumo.conferem, "Totais iguais"],
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
    syncAISources();
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
  function resetInvestigation() {
    documentaryGroups = [];
    investigationController?.abort();
    investigationController = null;
    investigation.hidden = true;
    investigationResults.hidden = true;
    investigationResults.documentDialog?.close();
    investigationResults.replaceChildren();
    investigationMessage.textContent = "";
    investigationButton.disabled = false;
    byId("fiscal242Entradas").value = "";
    byId("fiscal242Saidas").value = "";
  }

  let documentaryGroups = [];
  function investigationStatus(status) {
    return ({
      CONCILIADO: "Conciliado por documento",
      CONTA_DIFERENTE: "Possível outra conta",
      ESTORNO_EM_ANALISE: "Estorno para conferir",
      AMBIGUO: "Correspondência ambígua",
      VALOR_DIFERENTE: "Valor divergente",
      DATA_DIFERENTE: "Data divergente",
      PROVAVEL: "Vínculo provável",
      SEM_LANCAMENTO_IDENTIFICADO: "Sem lançamento identificado",
      SEM_DOCUMENTO_IDENTIFICADO: "Sem documento identificado",
      CORRESPONDENCIA_EM_ANALISE: "Correspondência em análise",
      DOCUMENTOS_NAO_IDENTIFICAVEIS: "Detalhamento não identificável"
    })[status] || status || "Revisar";
  }

  function compactDocumentHistory(history, document) {
    const original = String(history || "");
    const key = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    const separator = original.lastIndexOf(" - ");
    if (separator < 0 || !document.parceiro || key(original.slice(separator + 3)) !== key(document.parceiro)) return original;
    const beginning = original.slice(0, separator);
    // Só resuma quando a nota e o parceiro já estão expostos na coluna fiscal.
    const reference = beginning.match(/(?:CF\s*)?(?:NF|N\.F\.|NOTA(?: FISCAL)?|CTRC|CT-?E)\s*(?:REF\.\s*NF\s*)?(\d+)/i);
    if (reference && reference[1].replace(/^0+/, "") === String(document.nota).replace(/^0+/, "")) {
      if (beginning.slice(reference.index + reference[0].length).trim()) return original;
      const label = beginning.slice(0, reference.index).replace(/[\s.-]+$/, "").trim();
      return !label || /^REF$/i.test(label) ? "Referência à nota " + document.nota : label;
    }
    if (/^\s*\d+\s*$/.test(beginning) && beginning.trim().replace(/^0+/, "") === String(document.nota).replace(/^0+/, "")) return "Número no histórico · confirmar NF";
    return original;
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

  function investigationAccumulatorTotals(group) {
    const comparisons = group.comparacoes || [];
    const owners = new Map();
    for (const d of comparisons) for (const m of d.lancamentos || []) {
      if (String(m.conta || group.conta) !== String(group.conta)) continue;
      if (!owners.has(m.id)) owners.set(m.id, new Set());
      for (const p of d.linhas_fiscais || []) owners.get(m.id).add(String(p.acumulador));
    }
    return (group.acumuladores || []).map(acc => {
      const code = String(acc.codigo), refs = new Map();
      const docs = comparisons.filter(d => (d.linhas_fiscais || []).some(p => String(p.acumulador) === code));
      let inseparable = false;
      for (const d of docs) {
        const own = (d.lancamentos || []).filter(m => String(m.conta || group.conta) === String(group.conta));
        if (own.length && (d.situacao === "AMBIGUO" || new Set((d.linhas_fiscais || []).map(p => String(p.acumulador))).size > 1 ||
          own.some(m => !m.id || owners.get(m.id)?.size > 1))) inseparable = true;
        for (const m of own) refs.set(m.id, m);
      }
      const available = acc.detalhamento_disponivel && !inseparable;
      const cents = [...refs.values()].reduce((sum, m) => sum + Math.round(Number(m.valor || 0) * 100), 0);
      return {acc, group, fiscal:Number(acc.valor_resumo || 0), ledger:available ? cents / 100 : null,
        difference:available ? (cents - Math.round(Number(acc.valor_resumo || 0) * 100)) / 100 : null,
        note:inseparable ? "Há parcelas compartilhadas ou candidatos ambíguos. O Razão não foi rateado entre acumuladores." :
          !acc.detalhamento_disponivel ? "Sem detalhamento fiscal suficiente para identificar o Razão por acumulador." :
          "Só vínculos desta conta; exclui movimentos sem vínculo e candidatos de outras contas. Vínculos em análise exigem confirmação."};
    });
  }

  function renderInvestigation(report) {
    investigationResults.documentDialog?.close();
    investigationResults.replaceChildren();
    const groups = report.contas || [];
    documentaryGroups = groups;
    const header = node("div", "fiscal-investigation-summary");
    const allComparisons = groups.flatMap(g => g.comparacoes || g.documentos || []);
    const lines = allComparisons.flatMap(c => (c.linhas_fiscais?.length ? c.linhas_fiscais : [c]).map(() => c));
    const pendingMovements = groups.reduce((sum, g) => sum + (g.razao_sem_vinculo || g.razao_pendente || []).length, 0);
    [["Contas investigadas", groups.length], ["Linhas fiscais conciliadas", lines.filter(d => d.situacao === "CONCILIADO").length],
      ["Linhas fiscais para revisar", lines.filter(d => d.situacao !== "CONCILIADO").length], ["Movimentos sem vínculo", pendingMovements]]
      .forEach(([label, value]) => {
        const metric = node("div", "fiscal-investigation-metric");
        metric.append(node("small", "", label), node("strong", "", value)); header.appendChild(metric);
      });
    investigationResults.appendChild(header);
    investigationResults.appendChild(node("p", "fiscal-doc-count-note", "Contagem do cruzamento completo. Uma nota pode ocupar várias linhas fiscais e ter mais de uma parcela no Razão. Movimentos sem vínculo são contados separadamente."));
    const warnings = node("div", "fiscal-warnings");
    (report.avisos || []).forEach(text => warnings.appendChild(node("p", "", text)));
    investigationResults.appendChild(warnings);
    if (!groups.length) {
      investigationResults.appendChild(node("p", "fiscal-disclaimer", "Não há contas divergentes ou com alertas nos tipos anexados."));
      investigationResults.hidden = false; return;
    }
    const accumulatorTotals = new Map(groups.map(group => [group, investigationAccumulatorTotals(group)]));
    const lookup = node("section", "fiscal-doc-lookup");
    const lookupLabel = node("label", "", "Consultar valores por conta ou acumulador");
    const lookupInput = node("input", "fiscal-doc-lookup-input"); lookupInput.type = "search";
    lookupInput.id = "fiscal242ConsultaDocumental"; lookupLabel.htmlFor = lookupInput.id;
    lookupInput.placeholder = "Ex.: conta 470 ou acumulador 1403";
    lookupInput.setAttribute("aria-label", "Pesquisar conta ou acumulador na investigação");
    const lookupResults = node("div", "fiscal-doc-lookup-results"); lookupResults.setAttribute("aria-live", "polite");
    lookup.append(lookupLabel, lookupInput, lookupResults);
    const stage = node("div", "fiscal-doc-stage"); stage.appendChild(lookup); investigationResults.appendChild(stage);
    const workspace = node("div", "fiscal-doc-workspace");
    const accounts = node("nav", "fiscal-doc-accounts");
    accounts.setAttribute("aria-label", "Contas da investigação documental");
    const dialog = node("dialog", "fiscal-account-dialog fiscal-document-dialog");
    dialog.setAttribute("aria-labelledby", "fiscalDocumentDialogTitle");
    dialog.setAttribute("aria-describedby", "fiscalDocumentDialogDescription");
    investigationResults.documentDialog = dialog;
    const shell = node("div", "fiscal-account-dialog-shell");
    const dialogHeader = node("div", "fiscal-account-dialog-header");
    dialogHeader.setAttribute("tabindex", "-1");
    const dialogHeading = node("div", "fiscal-detail-heading");
    const dialogTitleArea = node("div", "fiscal-detail-title");
    dialogTitleArea.appendChild(node("span", "fiscal-section-eyebrow", "ENTRADAS E SAÍDAS × RAZÃO"));
    const dialogTitle = node("h3"); dialogTitle.id = "fiscalDocumentDialogTitle";
    const dialogDescription = node("p"); dialogDescription.id = "fiscalDocumentDialogDescription";
    dialogTitleArea.append(dialogTitle, dialogDescription);
    const dialogActions = node("div", "fiscal-detail-heading-actions");
    const close = node("button", "fiscal-detail-close", "Fechar ×"); close.type = "button";
    close.setAttribute("aria-label", "Fechar resultados de Entradas e Saídas");
    close.addEventListener("click", () => dialog.close());
    dialogActions.appendChild(close); dialogHeading.append(dialogTitleArea, dialogActions);
    const situation = node("div", "fiscal-account-situation");
    const situationSymbol = node("span", "fiscal-account-situation-symbol"); situationSymbol.setAttribute("aria-hidden", "true");
    const situationCopy = node("div", "fiscal-account-situation-copy");
    const situationTitle = node("strong"), situationText = node("p");
    situationCopy.append(situationTitle, situationText); situation.append(situationSymbol, situationCopy);
    dialogHeader.append(dialogHeading, situation);
    const reader = node("section", "fiscal-doc-reader");
    reader.setAttribute("aria-label", "Resultados da investigação documental");
    reader.setAttribute("tabindex", "0");
    const dialogBody = node("div", "fiscal-detail fiscal-account-dialog-body"); dialogBody.appendChild(reader);
    const footer = node("footer", "fiscal-account-dialog-footer");
    const position = node("p"); position.setAttribute("role", "status"); position.setAttribute("aria-live", "polite");
    const navigation = node("nav"); navigation.setAttribute("aria-label", "Navegar pelas contas investigadas");
    const previousAccount = node("button", "", "← Anterior"); previousAccount.type = "button";
    const nextAccount = node("button", "", "Próxima →"); nextAccount.type = "button";
    navigation.append(previousAccount, nextAccount); footer.append(position, navigation);
    shell.append(dialogHeader, dialogBody, footer); dialog.appendChild(shell);
    workspace.appendChild(accounts); stage.appendChild(workspace); investigationResults.appendChild(dialog);
    stage.insertBefore(node("p", "fiscal-doc-open-hint", "Selecione uma conta para abrir os valores e documentos na janela de resultados."), workspace);
    let active = groups[0], returnButton = null, mountedAnalysis = null;
    const buttons = new Map();
    const visibleGroups = () => groups.filter(group => !buttons.get(group)?.hidden);
    function syncDocumentNavigation() {
      const visible = visibleGroups(), index = visible.indexOf(active);
      previousAccount.disabled = index <= 0; nextAccount.disabled = index < 0 || index >= visible.length - 1;
      position.textContent = (index + 1) + " de " + visible.length + " na seleção de Entradas e Saídas";
    }
    function openDocumentAccount(group) {
      const query = lookupQuery(lookupInput.value);
      selectAccount(group, (group.acumuladores || []).some(acc => String(acc.codigo) === query) ? query : "");
      if (!dialog.open) {
        returnButton = buttons.get(group);
        dialog.showModal();
        document.documentElement.classList.add("fiscal-account-dialog-open");
      }
      dialogHeader.focus({preventScroll:true});
    }
    function moveDocumentAccount(direction) {
      const visible = visibleGroups(), index = visible.indexOf(active), target = index + direction;
      if (index >= 0 && target >= 0 && target < visible.length) openDocumentAccount(visible[target]);
    }
    previousAccount.addEventListener("click", () => moveDocumentAccount(-1));
    nextAccount.addEventListener("click", () => moveDocumentAccount(1));
    dialog.addEventListener("close", () => {
      document.documentElement.classList.remove("fiscal-account-dialog-open");
      (returnButton?.isConnected && !returnButton.hidden ? returnButton : lookupInput).focus({preventScroll:true});
    });
    let backdropStart = false;
    const outside = event => {
      const bounds = dialog.getBoundingClientRect();
      return event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom;
    };
    dialog.addEventListener("pointerdown", event => { backdropStart = event.target === dialog && outside(event); });
    dialog.addEventListener("click", event => {
      if (backdropStart && event.target === dialog && outside(event)) dialog.close();
      backdropStart = false;
    });
    const lookupQuery = value => String(value || "").trim().toLocaleLowerCase("pt-BR").replace(/^(?:conta|acumulador)\s+/, "");
    function fillScopeBalance(group, acc, balance) {
      balance.replaceChildren();
      balance.appendChild(node("small", "fiscal-doc-balance-caption", acc ? "TOTAIS DO ACUMULADOR " + acc.acc.codigo : "CONFERÊNCIA INICIAL · CONTA " + group.conta));
      const totals = node("div", "fiscal-doc-comparison-totals");
      [["Fiscal", acc ? acc.fiscal : group.fiscal], [acc ? "Razão identificado" : "Razão considerado", acc ? acc.ledger : group.contabil], ["Diferença", acc ? acc.difference : group.diferenca]].forEach(([label, value], index) => {
        const total = node("div", index === 2 ? "fiscal-doc-total-difference" : "");
        total.append(node("small", "", label), node("strong", "", value == null ? "Não separável" : money.format(value)));
        if (index === 2) total.appendChild(node("small", "fiscal-doc-difference-direction", value == null ? "Vínculo não confirmado" : Math.abs(value) < .005 ? "Sem diferença" : value > 0 ? "Acima do fiscal" : "Abaixo do fiscal"));
        totals.appendChild(total);
      });
      balance.append(totals, node("small", "", acc ? "Razão identificado − fiscal deste acumulador." : "Razão − fiscal · Entradas: débitos · Saídas: créditos."));
      if (acc) {
        balance.appendChild(node("small", "fiscal-doc-scope-note", acc.note));
        balance.appendChild(node("p", "fiscal-doc-scope-context", "Recorte do acumulador " + acc.acc.codigo +
          ". A diferença inicial da conta " + group.conta + " inteira é " + money.format(group.diferenca) +
          "; inclui os demais acumuladores e movimentos da comparação inicial."));
      } else if (group.composicao) {
        balance.appendChild(node("h5", "", "Composição da diferença"));
        const lines = node("div", "fiscal-doc-balance-lines");
        const effects = (group.composicao.itens || []).filter(item => Math.abs(item.valor) >= .005);
        effects.forEach(item => {
          const line = node("div");
          const label = node("div");
          const explanations = {
            vinculados:"Soma das diferenças de valor nos registros relacionados; alguns vínculos ainda podem precisar de confirmação.",
            razao_sem_vinculo:"Valores do Razão ainda não associados aos documentos anexados.",
            fiscal_sem_vinculo:"Valores fiscais ainda não associados a lançamentos desta conta. Confira também os candidatos em outras contas.",
            cobertura:"O acompanhamento anexado tem um total diferente do Resumo por Acumulador.",
            fora_inicial:"Estes movimentos ficaram fora da comparação inicial. O ajuste mantém a mesma base do total acima; não significa que estejam errados."
          };
          const labels = {vinculados:"Diferenças entre notas e Razão", razao_sem_vinculo:"Razão sem documento vinculado",
            fiscal_sem_vinculo:"Fiscal sem vínculo nesta conta", cobertura:"Cobertura dos relatórios", fora_inicial:"Fora da comparação inicial"};
          label.appendChild(node("span", "", labels[item.codigo] || item.descricao));
          if (explanations[item.codigo]) label.title = explanations[item.codigo];
          line.append(label, node("strong", "", (item.valor > 0 ? "+ " : "") + money.format(item.valor)));
          lines.appendChild(line);
        });
        if (!effects.length) lines.appendChild(node("p", "", "Os valores dos documentos e do Razão fecham com o resumo fiscal."));
        balance.appendChild(lines);
        balance.appendChild(node("small", "", group.composicao.confere_com_inicial ?
          (group.composicao.vinculos_incertos ? "A soma fecha com a diferença inicial. Há vínculos a confirmar." : "A soma fecha com a diferença inicial. Confira os registros pendentes.") :
          "A composição não fecha com a conferência inicial. Revise a cobertura dos relatórios."));
      } else balance.appendChild(node("small", "", "Diferença = Razão considerado − resumo fiscal."));
    }
    function selectAccount(group, accumulatorCode = "") {
      mountedAnalysis?.destroy(); mountedAnalysis = null;
      active = group;
      buttons.forEach((button, item) => button.setAttribute("aria-current", item === active ? "true" : "false"));
      reader.replaceChildren(); reader.scrollTop = 0; dialogBody.scrollTop = 0;
      syncDocumentNavigation();
      const scopeTitle = node("h4", "", group.descricao || "Cruzamento documental");
      reader.append(node("small", "fiscal-doc-eyebrow", group.tipo + " · CONTA " + group.conta), scopeTitle);
      const balance = node("div", "fiscal-doc-balance");
      reader.appendChild(balance);
      let analysisScope = null;
      const coverageArea = node("div", "fiscal-doc-coverage");
      const comparisons = group.comparacoes || (group.documentos || []).map(d => ({...d,
        valor_fiscal:d.valor, valor_razao:d.valor_razao_candidato, diferenca:d.diferenca_candidato,
        linhas_fiscais:[d], lancamentos:[]}));
      const ledger = group.razao_sem_vinculo || group.razao_pendente || [];
      const controls = node("div", "fiscal-doc-controls");
      const select = node("select", "fiscal-doc-filter"); select.setAttribute("aria-label", "Filtrar correspondências");
      const options = [["review", "Todas as pendências"], ["all", "Todos os documentos"], ["CONCILIADO", "Conciliados"],
        ["VALOR_DIFERENTE", "Valor diferente"], ["DATA_DIFERENTE", "Data diferente"], ["CONTA_DIFERENTE", "Possível outra conta"],
        ["ESTORNO_EM_ANALISE", "Estorno para conferir"],
        ["PROVAVEL", "Vínculo provável"], ["AMBIGUO", "Vínculo ambíguo"],
        ["SEM_LANCAMENTO_IDENTIFICADO", "Fiscal sem lançamento"], ["ledger", "Razão sem vínculo"]];
      options.forEach(([value, label]) => {
        const quantity = value === "all" ? comparisons.length : value === "review" ? comparisons.filter(d => d.situacao !== "CONCILIADO").length + ledger.length :
          value === "ledger" ? ledger.length : comparisons.filter(d => d.situacao === value).length;
        if (!quantity && !["review", "all"].includes(value)) return;
        const option = node("option", "", label + " (" + quantity + ")"); option.value = value; option.baseLabel = label; select.appendChild(option);
      });
      if (!comparisons.some(d => d.situacao !== "CONCILIADO")) select.value = ledger.length ? "ledger" : "all";
      const input = node("input", "fiscal-doc-search"); input.type = "search";
      input.placeholder = "Filtrar nota, parceiro ou histórico neste resultado";
      input.setAttribute("aria-label", "Buscar na investigação documental");
      const exportButton = node("button", "fiscal-doc-export", "Exportar CSV"); exportButton.type = "button";
      const documentTitle = node("h5", "fiscal-doc-document-title");
      controls.append(select, input, exportButton); reader.append(documentTitle, controls);
      const caption = node("p", "fiscal-doc-caption"); caption.setAttribute("aria-live", "polite");
      const rowsArea = node("div", "fiscal-doc-rows");
      const pagination = node("div", "fiscal-doc-pagination");
      const previous = node("button", "", "Anterior"); previous.type = "button";
      const pageLabel = node("span");
      const next = node("button", "", "Próxima"); next.type = "button";
      const pageSize = node("select"); pageSize.setAttribute("aria-label", "Registros por página");
      [25, 50, 100].forEach(n => { const o = node("option", "", n + " por página"); o.value = String(n); pageSize.appendChild(o); });
      pagination.append(previous, pageLabel, next, pageSize); reader.append(caption, pagination, rowsArea, node("h5", "fiscal-doc-coverage-title", "Cobertura dos acumuladores"), coverageArea);
      let page = 0;
      const priority = {VALOR_DIFERENTE:0, ESTORNO_EM_ANALISE:1, CONTA_DIFERENTE:2, DATA_DIFERENTE:3,
        SEM_LANCAMENTO_IDENTIFICADO:4, AMBIGUO:5, PROVAVEL:6, CONCILIADO:7};
      const ordered = [...comparisons].sort((a, b) => (priority[a.situacao] ?? 8) - (priority[b.situacao] ?? 8) ||
        Math.abs(b.diferenca || 0) - Math.abs(a.diferenca || 0));
      const indexed = ordered.map(d => ({item:d, text:[group.conta, d.nota, d.serie, d.parceiro, d.criterio,
        ...(d.linhas_fiscais || []).map(p => p.acumulador + " " + p.cfop),
        ...(d.lancamentos || []).map(m => m.historico + " " + (m.conta || group.conta))].join(" ").toLocaleLowerCase("pt-BR")}));
      const ledgerIndex = ledger.map(m => ({item:m, text:[m.nota, m.historico, m.id, m.data].join(" ").toLocaleLowerCase("pt-BR")}));
      function currentAccumulator() {
        const query = lookupQuery(input.value);
        if (query === String(group.conta)) return null;
        return accumulatorTotals.get(group).find(a => String(a.acc.codigo) === query) ||
          accumulatorTotals.get(group).find(a => String(a.acc.codigo) === accumulatorCode) || null;
      }
      function scopedComparison(item, acc) {
        return !acc || (item.linhas_fiscais || []).some(p => String(p.acumulador) === String(acc.acc.codigo));
      }
      function filtered() {
        const query = lookupQuery(input.value), acc = currentAccumulator();
        const entityQuery = query === String(group.conta) || accumulatorTotals.get(group).some(a => String(a.acc.codigo) === query);
        return (select.value === "ledger" ? ledgerIndex : indexed).filter(({item, text}) =>
          (!acc || select.value !== "ledger" && scopedComparison(item, acc)) &&
          (!query || entityQuery || text.includes(query)) && (select.value === "ledger" || select.value === "all" ||
            (select.value === "review" ? item.situacao !== "CONCILIADO" : item.situacao === select.value))).map(r => r.item);
      }
      function paint() {
        const acc = currentAccumulator();
        scopeTitle.textContent = acc ? "Acumulador " + acc.acc.codigo + " · " + (acc.acc.descricao || "Documentos fiscais") : group.descricao || "Cruzamento documental";
        fillScopeBalance(group, acc, balance);
        const scopeCode = acc ? String(acc.acc.codigo) : "";
        if (scopeCode !== analysisScope) {
          analysisScope = scopeCode;
          mountedAnalysis?.destroy();
          mountedAnalysis = createAccountAnalysis({origem:"documentos", conta:String(group.conta), tipo:group.tipo, acumulador:scopeCode});
          mountedAnalysis.mount({header:dialogHeader, comparison:dialogBody, footer, navigation, shell});
        }
        documentTitle.textContent = acc ? "Documentos e lançamentos · acumulador " + acc.acc.codigo : "Documentos e lançamentos desta conta";
        const scoped = comparisons.filter(d => scopedComparison(d, acc));
        dialogTitle.textContent = acc ? "Acumulador " + acc.acc.codigo : "Conta " + group.conta;
        dialogDescription.textContent = group.tipo + " · Conta " + group.conta + " · " + (acc ? acc.acc.descricao || "Documentos fiscais" : group.descricao || "Cruzamento documental");
        const difference = acc ? acc.difference : group.diferenca;
        const pending = scoped.filter(d => d.situacao !== "CONCILIADO").length;
        const unlinked = acc ? 0 : ledger.length;
        const unknown = difference == null, divergent = !unknown && Math.abs(difference) > .01;
        dialog.dataset.situation = unknown || pending || unlinked ? "review" : divergent ? "divergence" : "equal";
        situationSymbol.textContent = divergent ? "≠" : unknown || pending || unlinked ? "!" : "=";
        situationTitle.textContent = unknown ? "Vínculo a confirmar" : divergent ? "Resultado com divergência" : pending || unlinked ? "Totais iguais · com pendências" : "Totais iguais";
        situationText.textContent = (unknown ? "Não é possível separar o valor do Razão com segurança." :
          (acc ? "Diferença do acumulador: " : "Diferença da conferência inicial: ") + money.format(difference) + ".") +
          " " + pending + " documento(s) para revisar" + (unlinked ? " · " + unlinked + " movimento(s) sem vínculo" : "") + ".";
        for (const option of select.children) {
          const quantity = option.value === "all" ? scoped.length : option.value === "review" ? scoped.filter(d => d.situacao !== "CONCILIADO").length + (acc ? 0 : ledger.length) :
            option.value === "ledger" ? (acc ? 0 : ledger.length) : scoped.filter(d => d.situacao === option.value).length;
          option.hidden = !quantity && !["review", "all"].includes(option.value);
          option.textContent = option.baseLabel + " (" + quantity + ")";
          if (option.value === select.value && option.hidden) select.value = "all";
        }
        coverageArea.replaceChildren(investigationTable(["Acumulador", "Resumo fiscal", "Documentos lidos", "Diferença de cobertura"],
          (group.acumuladores || []).filter(a => !acc || String(a.codigo) === String(acc.acc.codigo)), (tr, a) => {
            cell(tr, a.codigo + " · " + (a.descricao || ""));
            cell(tr, money.format(a.valor_resumo), "fiscal-money");
            cell(tr, a.detalhamento_disponivel ? money.format(a.valor_documentos) : "Sem detalhamento", "fiscal-money");
            cell(tr, a.detalhamento_disponivel ? money.format(a.valor_documentos - a.valor_resumo) : "Não calculada", "fiscal-money");
          }));
        const rows = filtered(); const size = Number(pageSize.value); const pages = Math.max(1, Math.ceil(rows.length / size));
        page = Math.min(page, pages - 1); const start = page * size;
        caption.textContent = rows.length ? (start + 1) + "–" + Math.min(start + size, rows.length) + " de " + rows.length +
          " registros" : "Nenhum registro neste filtro.";
        if (select.value === "review") caption.textContent += " · Documentos fiscais nesta lista; " + (acc ? 0 : ledger.length) + " movimento(s) sem vínculo mostrados acima.";
        pageLabel.textContent = "Página " + (page + 1) + " de " + pages;
        previous.disabled = page === 0; next.disabled = page + 1 >= pages;
        pagination.hidden = rows.length <= 25;
        rowsArea.replaceChildren();
        if (select.value === "review" && !acc && ledger.length) {
          const query=lookupQuery(input.value);
          const pendingLedger=ledgerIndex.filter(m=>!query || query === String(group.conta) || m.text.includes(query)).map(m=>m.item);
          if(pendingLedger.length){
            rowsArea.appendChild(node("h5","fiscal-pending-ledger-title","Razão sem documento vinculado (" + pendingLedger.length + ")"));
            rowsArea.appendChild(investigationTable(["Referência / data","Histórico do Razão","Valor","O que conferir"],pendingLedger,(tr,m)=>{
              cell(tr,m.id + " · " + m.data);cell(tr,m.historico);cell(tr,money.format(m.valor),"fiscal-money");
              cell(tr,"Localize o documento indicado no histórico e confirme período, filial e conta. A ausência de vínculo não comprova erro.");
            }));
          }
        }
        if (!rows.length) { rowsArea.appendChild(node("p", "fiscal-doc-empty", "Nenhum resultado. Consulte os conciliados ou altere a busca.")); return; }
        if (select.value === "ledger") {
          rowsArea.appendChild(investigationTable(["Referência / data", "Histórico do Razão", "Valor", "Leitura"], rows.slice(start, start + size), (tr, m) => {
            cell(tr, m.id + " · " + m.data).setAttribute("data-label", "Referência / data");
            cell(tr, m.historico).setAttribute("data-label", "Histórico");
            cell(tr, money.format(m.valor), "fiscal-money").setAttribute("data-label", "Valor");
            cell(tr, investigationStatus(m.situacao) + ". " + (m.classificacao || "") + ". Confira se este movimento pertence aos documentos anexados.").setAttribute("data-label", "Leitura");
          })); return;
        }
        rowsArea.appendChild(investigationTable(["Documento fiscal", "Lançamentos no Razão", "Diferença / resultado"],
          rows.slice(start, start + size), (tr, d) => {
            const docCell = node("td", "fiscal-doc-source"); docCell.setAttribute("data-label", "Fiscal");
            docCell.append(node("strong", "fiscal-doc-value", money.format(d.valor_fiscal)), node("strong", "", "Nota " + d.nota + (d.serie ? " · série " + d.serie : "")),
              node("span", "", d.data), node("span", "", d.parceiro || "Parceiro não informado"));
            (d.linhas_fiscais || []).forEach(p => docCell.appendChild(node("small", "", p.id + " · acumulador " + p.acumulador +
              " · CFOP " + p.cfop + (d.linhas_fiscais.length > 1 ? " · " + money.format(p.valor) : "") + " · linha " + p.linha_origem)));
            tr.appendChild(docCell);
            const movCell = node("td", "fiscal-doc-source"); movCell.setAttribute("data-label", "Razão");
            movCell.appendChild(node("strong", "fiscal-doc-value", d.valor_razao == null ? "Valor não confirmado" : money.format(d.valor_razao)));
            (d.lancamentos || []).forEach(m => {
              const block = node("div", "fiscal-doc-movement");
              const history = node("span", "", compactDocumentHistory(m.historico, d)); history.title = m.historico;
              if (d.lancamentos.length > 1) block.appendChild(node("strong", "", money.format(m.valor)));
              block.append(history, node("small", "", m.data + " · conta " + (m.conta || group.conta) + " · " + m.id +
                  (m.contrapartida ? " · contrapartida " + m.contrapartida : "")));
              movCell.appendChild(block);
            });
            if (!d.lancamentos?.length) movCell.appendChild(node("span", "fiscal-disclaimer", "Nenhum lançamento identificado pelos critérios disponíveis."));
            tr.appendChild(movCell);
            const statusCell = node("td", "fiscal-doc-status"); statusCell.setAttribute("data-label", "Resultado");
            if (d.diferenca != null) statusCell.appendChild(node("strong", d.diferenca ? "fiscal-doc-difference" : "", money.format(d.diferenca)));
            statusCell.appendChild(node("span", "fiscal-doc-badge fiscal-doc-badge-" + d.situacao.toLowerCase(), investigationStatus(d.situacao)));
            const reason = d.situacao === "VALOR_DIFERENTE" ? "O Razão está " + money.format(Math.abs(d.diferenca || 0)) + (d.diferenca > 0 ? " acima" : " abaixo") + " do documento fiscal. Confira valor integral, parcelas e redutores documentados." :
              d.situacao === "CONCILIADO" ? "Documento, data e valores conferem." : d.criterio || "";
            const criterion = node("small", "", reason); criterion.title = d.criterio || "";
            statusCell.appendChild(criterion); tr.appendChild(statusCell);
          }));
      }
      select.addEventListener("change", () => { page = 0; paint(); });
      input.addEventListener("input", () => {
        if (lookupQuery(input.value) === String(group.conta) || (group.acumuladores || []).some(a => String(a.codigo) === lookupQuery(input.value))) select.value = "review";
        page = 0; paint();
      });
      pageSize.addEventListener("change", () => { page = 0; paint(); });
      previous.addEventListener("click", () => { page--; paint(); }); next.addEventListener("click", () => { page++; paint(); });
      exportButton.addEventListener("click", () => {
        const rows = filtered();
        const values = select.value === "ledger" ? [["Referência", "Data", "Histórico", "Valor", "Situação"], ...rows.map(m => [m.id, m.data, m.historico, m.valor, investigationStatus(m.situacao)])] :
          [["Nota", "Série", "Data fiscal", "Parceiro", "Acumuladores", "Linhas fiscais / origem", "Fiscal", "Razão", "Diferença", "Situação", "Critério", "Lançamentos"],
            ...rows.map(d => [d.nota, d.serie, d.data, d.parceiro, (d.linhas_fiscais || []).map(p => p.acumulador).join(", "),
              (d.linhas_fiscais || []).map(p => p.id + " CFOP " + p.cfop + " " + money.format(p.valor) + " linha " + p.linha_origem).join(" | "), d.valor_fiscal, d.valor_razao, d.diferenca, investigationStatus(d.situacao), d.criterio,
              (d.lancamentos || []).map(m => m.id + " " + m.data + " conta " + (m.conta || group.conta) + " " + m.historico + " " + money.format(m.valor)).join(" | ")])];
        if(select.value === "review" && !currentAccumulator()){
          const query=lookupQuery(input.value);
          ledgerIndex.filter(m=>!query || query===String(group.conta) || m.text.includes(query)).forEach(({item:m})=>{
            values.push([m.nota || "", "", m.data, "", "", m.id, "", m.valor, "", "Razão sem vínculo", "Confirmar documento, período, filial e conta", m.historico]);
          });
        }
        const csvCell = value => '"' + String(value ?? "").replace(/^[=+@\t\r-]/, "'$&").replace(/"/g, '""') + '"';
        const blob = new Blob(["\ufeff" + values.map(row => row.map(csvCell).join(";")).join("\r\n")], {type:"text/csv;charset=utf-8"});
        const url = URL.createObjectURL(blob); const link = node("a"); link.href = url;
        link.download = "investigacao-conta-" + group.conta + "-" + group.tipo.toLowerCase() + ".csv";
        link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
      if (accumulatorCode) select.value = comparisons.some(d => d.situacao !== "CONCILIADO" &&
        (d.linhas_fiscais || []).some(p => String(p.acumulador) === accumulatorCode)) ? "review" : "all";
      paint();
    }
    lookupInput.addEventListener("input", () => {
      lookupResults.replaceChildren();
      const query = lookupQuery(lookupInput.value);
      if (!query) {
        buttons.forEach((button, group) => {
          button.hidden = false;
          button.children[1].textContent = (group.descricao || "Sem descrição").split(" | ")[0];
          button.children[2].textContent = group.documentos_total + " linhas · " + money.format(group.diferenca || 0);
        }); workspace.hidden = false;
        selectAccount(active); return;
      }
      const exactAccounts = groups.filter(g => String(g.conta) === query);
      const exactAccumulators = [...accumulatorTotals.values()].flat().filter(a => String(a.acc.codigo) === query);
      const matches = exactAccounts.length ? exactAccounts.map(group => ({group})) : exactAccumulators.length ? exactAccumulators :
        groups.filter(g => (g.conta + " " + g.descricao).toLocaleLowerCase("pt-BR").includes(query)).map(group => ({group}));
      const matchingGroups = new Set(matches.map(match => match.group));
      buttons.forEach((button, group) => {
        button.hidden = !matchingGroups.has(group);
        const acc = accumulatorTotals.get(group).find(a => String(a.acc.codigo) === query);
        button.children[1].textContent = acc ? acc.acc.descricao || "Acumulador " + query : (group.descricao || "Sem descrição").split(" | ")[0];
        button.children[2].textContent = acc ? "Acum. " + query + " · " + (acc.difference == null ? "Sem valor separado" : money.format(acc.difference)) : group.documentos_total + " linhas · " + money.format(group.diferenca || 0);
      });
      workspace.hidden = !matches.length;
      if (!matches.length && dialog.open) dialog.close();
      if (matches.length) {
        if (matches.length > 1) lookupResults.appendChild(node("p", "fiscal-doc-query-status", matches.length + " resultados. Clique na conta e no tipo desejados na lista."));
        const selected = matches.find(match => match.group === active) || matches[0];
        // Uma busca exata abre o recorte sem exigir mais um clique, preservando o foco na pesquisa.
        selectAccount(selected.group, selected.acc ? String(selected.acc.codigo) : "");
      } else lookupResults.appendChild(node("p", "fiscal-doc-empty", "Nenhuma conta ou acumulador encontrado entre os investigados. Limpe a consulta para voltar aos documentos."));
    });
    lookupInput.addEventListener("keydown", event => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const visible = visibleGroups();
      if (visible.length) openDocumentAccount(visible.includes(active) ? active : visible[0]);
    });
    groups.forEach(group => {
      const button = node("button", "fiscal-doc-account"); button.type = "button";
      const name = node("div", "fiscal-doc-account-head"); name.append(node("strong", "", "Conta " + group.conta), node("small", "", group.tipo));
      const description = node("span", "", (group.descricao || "Sem descrição").split(" | ")[0]); description.title = group.descricao || "";
      button.append(name, description, node("small", "", group.documentos_total + " linhas · " + money.format(group.diferenca || 0)));
      button.setAttribute("aria-haspopup", "dialog");
      button.setAttribute("aria-label", "Abrir resultados da conta " + group.conta + " · " + group.tipo);
      button.addEventListener("click", () => openDocumentAccount(group)); accounts.appendChild(button); buttons.set(group, button);
    });
    selectAccount(active); investigationResults.hidden = false;
  }

  investigationForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (!previewBody || !data) {
      investigationMessage.textContent = "Conclua a conferência inicial antes de investigar documentos.";
      return;
    }
    const entradas = [...byId("fiscal242Entradas").files];
    const saidas = [...byId("fiscal242Saidas").files];
    if (!entradas.length && !saidas.length) {
      investigationMessage.textContent = "Selecione Entradas, Saídas ou ambos.";
      return;
    }
    const snapshot = data;
    const body = new FormData();
    const files = selectedFiles();
    files.acumuladores.forEach(file => body.append("acumuladores", file));
    files.razao.forEach(file => body.append("razao", file));
    body.append("filial", String(data.filial_aplicada || byId("fiscalFilialCodigo").value || ""));
    entradas.forEach(file => body.append("entradas", file));
    saidas.forEach(file => body.append("saidas", file));
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
      renderInvestigation(result);
      investigationMessage.textContent = "Investigação concluída. Clique em uma conta para abrir os resultados e documentos na janela flutuante.";
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



  ["fiscal242Entradas", "fiscal242Saidas"].forEach(id => byId(id).addEventListener("change", () => {
    resetAccountAnalyses();
    investigationController?.abort(); investigationController = null;
    investigationButton.disabled = false;
    investigationResults.documentDialog?.close();
    investigationResults.replaceChildren(); investigationResults.hidden = true;
    investigationMessage.textContent = "Arquivos alterados. Investigue novamente para atualizar as pendências.";
    aiController?.abort(); discardPendingAI(); aiInputBody = null; aiReport = null;
    clearAIAccounts(); aiResult.replaceChildren(); aiExport.disabled = true; aiRetry.hidden = true;
    aiInlineStatus.textContent = "Os documentos foram alterados. Gere uma nova análise para usar os dados atuais.";
    syncAISources();
  }));

  filter.addEventListener("change", () => { renderTable(); syncQuickFilters(); });
  search.addEventListener("input", renderTable);
  function showSelectedFile(inputId, labelId) {
    const input = byId(inputId);
    const label = byId(labelId);
    if (!input || !label) return;
    const file = input.files?.[0];
    label.textContent = input.files.length > 1 ? `${input.files.length} arquivos selecionados` : file ? file.name : "Nenhum arquivo selecionado";
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
    resetAccountAnalyses();
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
        method:"POST", body, signal: controller.signal, headers:{"X-Razync-Reuse":"1"}
      });
      if (!response.ok) throw new Error(await responseError(response));
      const report = await response.json();
      if (controller.signal.aborted) return;
      renderResponse(report);
      previewBody = body; aiInputBody = null; syncAISources();
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
      const response = globalThis.RazyncResults
        ? await RazyncResults.downloadResponse(data.report_token, API() + "/api/v1/conferencia-fiscal/exportar", {method:"POST",body})
        : await fetch(API() + "/api/v1/conferencia-fiscal/exportar", {method:"POST",body});
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
  pane.appendChild(usageDialog);
})();
