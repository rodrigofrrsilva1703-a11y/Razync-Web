// Apresentação da conferência diária; mantém os cálculos e filtros existentes.
function formatDailyDate(value) {
  if (!value) return "—";
  const date = new Date(String(value) + (String(value).length === 10 ? "T00:00:00" : ""));
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat("pt-BR").format(date);
}

function reconciliationBalances(row, kind="modelo") {
  const ledger = kind === "razao";
  const leftIn = Number(row[ledger ? "ENTRADAS_RAZAO" : "ENTRADAS PLANILHA"] || 0);
  const rightIn = Number(
    ledger
      ? (row["ENTRADAS_EXTRATO"] ?? row["ENTRADAS EXTRATO"] ?? 0)
      : (row["ENTRADAS EXTRATO"] ?? row["ENTRADAS_EXTRATO"] ?? 0)
  );
  const leftOut = Number(row[ledger ? "SAIDAS_RAZAO" : "SAÍDAS PLANILHA"] || 0);
  const rightOut = Number(
    ledger
      ? (row["SAIDAS_EXTRATO"] ?? row["SAÍDAS EXTRATO"] ?? 0)
      : (row["SAÍDAS EXTRATO"] ?? row["SAIDAS_EXTRATO"] ?? 0)
  );
  const entryBalance = Math.round((leftIn - rightIn) * 100) / 100;
  const exitBalance = Math.round((leftOut - rightOut) * 100) / 100;
  const entryOk = Math.abs(entryBalance) < 0.01;
  const exitOk = Math.abs(exitBalance) < 0.01;
  return {
    leftIn,rightIn,leftOut,rightOut,
    entryBalance,exitBalance,
    entryOk,exitOk,
    ok:entryOk && exitOk
  };
}

function renderDailyReconciliation(target, {rows=[], kind="modelo", download=null}) {
  if (!target) return;
  target.replaceChildren();
  target.hidden = false;
  target.className = "daily-reconciliation";

  const normalized = rows.map(row => {
    const balances = reconciliationBalances(row,kind);
    return {
      bank:String(row.BANCO || ""),
      date:row.DATA,
      ...balances
    };
  });

  const banks = [...new Set(normalized.map(row => row.bank).filter(Boolean))];
  const multiBank = banks.length > 1;
  const okCount = normalized.filter(row => row.ok).length;
  const reviewCount = normalized.length - okCount;

  const summary = document.createElement("div");
  summary.className = "daily-summary";
  summary.innerHTML = `
    <div><small>${multiBank ? "Banco/dia analisados" : "Dias analisados"}</small><strong>${normalized.length}</strong></div>
    <div><small>Batendo</small><strong>${okCount}</strong></div>
    <div><small>Divergentes</small><strong>${reviewCount}</strong></div>
  `;

  const rule = document.createElement("div");
  rule.className = "daily-rule";
  const sourceLabel = kind === "razao" ? "Razão" : "Modelo";
  rule.innerHTML = `
    <strong>Regra da conferência</strong>
    <span>Saldo entrada = Entrada ${sourceLabel} − Entrada Extrato · Saldo saída = Saída ${sourceLabel} − Saída Extrato · O status só fica <b>Batendo</b> quando os dois saldos forem R$ 0,00.</span>
  `;

  const toolbar = document.createElement("div");
  toolbar.className = "daily-toolbar";
  const toolbarLeft = document.createElement("div");
  toolbarLeft.className = "daily-toolbar-left";

  if (multiBank) {
    const bankFilter = document.createElement("select");
    bankFilter.className = "daily-bank-filter";
    bankFilter.setAttribute("aria-label","Filtrar banco");
    [["","Todos os bancos"],...banks.map(bank => [bank,bank])].forEach(([value,label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      bankFilter.appendChild(option);
    });
    toolbarLeft.appendChild(bankFilter);
  }

  const filters = document.createElement("div");
  filters.className = "daily-filters";
  [
    ["all","Todos"],
    ["ok","Batendo"],
    ["review","Divergentes"]
  ].forEach(([value,label],index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "daily-filter" + (index === 0 ? " active" : "");
    button.dataset.filter = value;
    button.textContent = label;
    filters.appendChild(button);
  });
  toolbarLeft.appendChild(filters);
  toolbar.appendChild(toolbarLeft);

  if (download) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "daily-download";
    button.textContent = "Baixar relatório Excel";
    button.addEventListener("click", async () => {
      button.disabled = true;
      const old = button.textContent;
      button.textContent = "Gerando relatório…";
      try { await download(); }
      finally { button.disabled = false; button.textContent = old; }
    });
    toolbar.appendChild(button);
  }

  const scroll = document.createElement("div");
  scroll.className = "daily-table-scroll";
  const table = document.createElement("table");
  table.className = "daily-table daily-table-reconciliation razync-table";
  const leftLabel = kind === "razao" ? "Razão" : "Modelo";
  const bankHeader = banks.length ? "<th>Banco</th>" : "";
  table.innerHTML = `
    <thead><tr>
      ${bankHeader}
      <th>Data</th>
      <th>Entrada ${leftLabel}</th>
      <th>Entrada Extrato</th>
      <th>Saldo Entrada</th>
      <th>Saída ${leftLabel}</th>
      <th>Saída Extrato</th>
      <th>Saldo Saída</th>
      <th>Status</th>
    </tr></thead>
    <tbody></tbody>
  `;
  const body = table.querySelector("tbody");

  normalized.forEach(row => {
    const tr = document.createElement("tr");
    tr.dataset.status = row.ok ? "ok" : "review";
    tr.dataset.bank = row.bank;
    tr.className = row.ok ? "daily-ok" : "daily-review";
    const status = row.ok ? "Batendo" : "Divergente";

    const values = [];
    if (banks.length) values.push({value:row.bank,type:"bank"});
    values.push(
      {value:formatDailyDate(row.date),type:"date"},
      {value:brl(row.leftIn),type:"numeric"},
      {value:brl(row.rightIn),type:"numeric"},
      {value:brl(row.entryBalance),type:"balance",ok:row.entryOk},
      {value:brl(row.leftOut),type:"numeric"},
      {value:brl(row.rightOut),type:"numeric"},
      {value:brl(row.exitBalance),type:"balance",ok:row.exitOk},
      {value:status,type:"status"}
    );

    values.forEach(cell => {
      const td = document.createElement("td");
      if (cell.type === "numeric") td.className = "numeric";
      if (cell.type === "balance") td.className = "numeric daily-balance " + (cell.ok ? "is-zero" : "is-different");
      if (cell.type === "bank") td.className = "daily-bank-cell";
      if (cell.type === "status") {
        const badge = document.createElement("span");
        badge.className = "daily-status " + (row.ok ? "is-ok" : "is-review");
        badge.textContent = cell.value;
        td.appendChild(badge);
      } else {
        td.textContent = cell.value;
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });

  const applyFilters = () => {
    const activeStatus = filters.querySelector(".daily-filter.active")?.dataset.filter || "all";
    const selectedBank = toolbarLeft.querySelector(".daily-bank-filter")?.value || "";
    body.querySelectorAll("tr").forEach(row => {
      const statusMatch = activeStatus === "all" || row.dataset.status === activeStatus;
      const bankMatch = !selectedBank || row.dataset.bank === selectedBank;
      row.hidden = !statusMatch || !bankMatch;
    });
  };

  filters.addEventListener("click", event => {
    const button = event.target.closest(".daily-filter");
    if (!button) return;
    filters.querySelectorAll(".daily-filter").forEach(item => item.classList.toggle("active",item === button));
    applyFilters();
  });
  toolbarLeft.querySelector(".daily-bank-filter")?.addEventListener("change",applyFilters);

  scroll.appendChild(table);
  target.append(summary,rule,toolbar,scroll);
}

