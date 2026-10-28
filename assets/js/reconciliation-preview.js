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

function renderDailyReconciliation(target, {rows=[], kind="modelo", download=null, movements=[]}) {
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

  // Filtra somente a visualização; os cálculos da conferência permanecem intactos.
  const periodFilter = document.createElement("div");
  periodFilter.className = "daily-period-filter";
  const startLabel = document.createElement("label");
  startLabel.textContent = "De";
  const startDate = document.createElement("input");
  startDate.type = "date";
  startDate.setAttribute("aria-label", "Data inicial da conferência");
  startLabel.appendChild(startDate);
  const endLabel = document.createElement("label");
  endLabel.textContent = "Até";
  const endDate = document.createElement("input");
  endDate.type = "date";
  endDate.setAttribute("aria-label", "Data final da conferência");
  endLabel.appendChild(endDate);
  const clearPeriod = document.createElement("button");
  clearPeriod.type = "button";
  clearPeriod.className = "daily-period-clear";
  clearPeriod.textContent = "Limpar período";
  clearPeriod.hidden = true;
  periodFilter.append(startLabel, endLabel, clearPeriod);
  toolbarLeft.appendChild(periodFilter);
  const visibleCount = document.createElement("span");
  visibleCount.className = "daily-visible-count";
  visibleCount.setAttribute("role", "status");
  toolbarLeft.appendChild(visibleCount);
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
    tr.dataset.date = /^\d{4}-\d{2}-\d{2}/.test(String(row.date || ""))
      ? String(row.date).slice(0, 10)
      : (/^\d{2}\/\d{2}\/\d{4}/.test(String(row.date || ""))
        ? String(row.date).slice(6, 10) + "-" + String(row.date).slice(3, 5) + "-" + String(row.date).slice(0, 2)
        : "");
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
    let shown = 0;
    body.querySelectorAll("tr").forEach(row => {
      const dateMatch = (!startDate.value || (row.dataset.date && row.dataset.date >= startDate.value))
        && (!endDate.value || (row.dataset.date && row.dataset.date <= endDate.value));
      const statusMatch = activeStatus === "all" || row.dataset.status === activeStatus;
      const bankMatch = !selectedBank || row.dataset.bank === selectedBank;
      row.hidden = !statusMatch || !bankMatch || !dateMatch;
      if (!row.hidden) shown++;
    });
    clearPeriod.hidden = !startDate.value && !endDate.value;
    const invalidRange = startDate.value && endDate.value && startDate.value > endDate.value;
    visibleCount.textContent = invalidRange ? "Período inválido: data inicial posterior à final" : shown + " de " + normalized.length + " dias/bancos exibidos";
  };

  filters.addEventListener("click", event => {
    const button = event.target.closest(".daily-filter");
    if (!button) return;
    filters.querySelectorAll(".daily-filter").forEach(item => item.classList.toggle("active",item === button));
    applyFilters();
  });
  toolbarLeft.querySelector(".daily-bank-filter")?.addEventListener("change",applyFilters);
  startDate.addEventListener("input", applyFilters);
  endDate.addEventListener("input", applyFilters);
  clearPeriod.addEventListener("click", () => { startDate.value = ""; endDate.value = ""; applyFilters(); });
  applyFilters();

  scroll.appendChild(table);
  target.append(summary,rule,toolbar,scroll);
  if (movements.length) target.appendChild(renderStatementMovements(movements));
}


// Consulta do que foi efetivamente lido, sem misturar movimento e saldo bancário.
function renderStatementMovements(movements) {
  const details=document.createElement("details");details.className="statement-reading";
  const summary=document.createElement("summary");summary.textContent=`Lançamentos lidos do extrato · ${movements.length}`;
  const note=document.createElement("p");note.textContent="Confira os movimentos extraídos do documento. Entradas e saídas são os valores dos lançamentos; o saldo bancário não é um lançamento.";
  const search=document.createElement("input");search.type="search";search.placeholder="Buscar histórico, data ou valor";search.setAttribute("aria-label","Buscar lançamentos lidos do extrato");
  const count=document.createElement("span");count.className="statement-reading-count";count.setAttribute("role","status");
  const controls=document.createElement("div");controls.className="statement-reading-controls";controls.append(search,count);
  const wrap=document.createElement("div");wrap.className="statement-reading-scroll";
  const table=document.createElement("table");table.className="statement-reading-table razync-table";
  const head=document.createElement("thead"), heading=document.createElement("tr");
  ["Banco","Data","Histórico","Entrada","Saída"].forEach(text=>{const th=document.createElement("th");th.textContent=text;heading.appendChild(th);});
  head.appendChild(heading);const body=document.createElement("tbody");table.append(head,body);wrap.appendChild(table);
  const normalize=value=>String(value).normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
  const queryKey=value=>normalize(value).replace(/[.,\s]/g,"");
  const index=movements.map(row=> {
    const value=Number(row.VALOR)||0, formatted=brl(Math.abs(value));
    return {row,value,key:queryKey([row.BANCO,formatDailyDate(row.DATA),row["HISTÓRICO"],formatted,String(Math.abs(value)).replace(".",",")].join(" "))};
  });
  const render=()=> {
    const query=queryKey(search.value);let shown=0;body.replaceChildren();
    for(const item of index) {
      if(query && !item.key.includes(query))continue;
      const tr=document.createElement("tr");
      [item.row.BANCO,formatDailyDate(item.row.DATA),item.row["HISTÓRICO"],item.value>0?brl(item.value):"—",item.value<0?brl(-item.value):"—"].forEach((value,i)=> {
        const td=document.createElement("td");td.textContent=String(value||"—");if(i>2)td.className="numeric";tr.appendChild(td);
      });
      body.appendChild(tr);shown++;
    }
    count.textContent=`${shown} de ${movements.length} lançamentos`;
    if(!shown){const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=5;td.textContent="Nenhum lançamento encontrado para esta busca.";tr.appendChild(td);body.appendChild(tr);}
  };
  search.addEventListener("input",render);
  let rendered=false;details.addEventListener("toggle",()=>{if(details.open&&!rendered){rendered=true;render();}});
  details.append(summary,note,controls,wrap);return details;
}
