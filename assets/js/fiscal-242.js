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
  let selectedKey = "";
  let pendingRequest = null;

  const byId = id => document.getElementById(id);
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
    if (pendingRequest) {
      pendingRequest.abort();
      pendingRequest = null;
    }
    data = null;
    previewBody = null;
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
      ["Contábil compatível (prévio)", money.format(row.contabil)],
      ["Total movimentado no lado analisado", money.format(row.total_conta)],
      ["Diferença", money.format(row.diferenca)]
    ].forEach(pair => {
      const card = node("div");
      card.appendChild(node("small", "", pair[0]));
      card.appendChild(node("strong", "", pair[1]));
      metrics.appendChild(card);
    });
    details.appendChild(metrics);
    if (row.extras) {
      details.appendChild(node("p", "fiscal-detail-alert", row.extras + " lançamento(s) sinalizado(s) como adicional(is). Valide os históricos e as contrapartidas."));
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
      cell(tr, mov.classificacao === "ALERTA - NÃO FISCAL" ? "Revisar" : "Fiscal provável");
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
