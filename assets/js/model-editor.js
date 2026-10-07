/* Drafts stay in this tab. Reconciliation always receives the latest valid workbook. */
(() => {
  const host = document.querySelector('#reconcileEditor');
  const input = document.querySelector('#modelFile');
  const form = document.querySelector('#reconcileForm');
  const balanceView = document.querySelector('#reconcileBalanceView');
  let original, corrected, sheets = [], batches = [], redo = [];
  let active = 0, page = 0, chosen = null, revision = 0, timer, controller, pending = false, downloadedRevision = -1;
  const pageSize = 100;
  const operations = () => batches.flat();
  const currentSheet = () => sheets[active];
  const status = text => { const el = host.querySelector('.editor-status'); if (el) el.textContent = text; };
  const button = (label, action, className = '') => {
    const el = document.createElement('button'); el.type = 'button'; el.textContent = label;
    el.className = className; el.addEventListener('click', action); return el;
  };
  function reset(clearFile = true) {
    revision++; controller?.abort(); clearTimeout(timer);
    original = corrected = null; sheets = []; batches = []; redo = [];
    active = page = 0; chosen = null; pending = false;
    host.replaceChildren(); host.hidden = true; balanceView.hidden = false;
    if (clearFile && input.files.length) { input.value = ''; input.dispatchEvent(new Event('change', {bubbles:true})); }
  }
  globalThis.RazyncModelEditor = {reset, file: () => corrected,
    canLeave: () => !batches.length || downloadedRevision === revision || window.confirm('O modelo tem alterações que ainda não foram baixadas. Sair e descartar essas alterações?')};

  function view(name) {
    host.querySelector('.editor-content').hidden = name !== 'editor';
    balanceView.hidden = name === 'editor';
    host.querySelectorAll('[data-editor-view]').forEach(el => {
      const selected = el.dataset.editorView === name;
      el.classList.toggle('active', selected); el.setAttribute('aria-pressed', String(selected));
    });
  }
  function replay() {
    const sheet = currentSheet();
    const rows = sheet.rows.map(row => [...row]);
    for (const op of operations().filter(op => op.sheet === sheet.name)) {
      const index = op.row - sheet.header - 1;
      if (op.kind === 'insert') rows.splice(index, 0, sheet.columns.map(() => ''));
      if (op.kind === 'delete') rows.splice(index, 1);
      if (op.kind === 'set') rows[index][op.col - 1] = op.value;
    }
    return rows;
  }
  function updateControls() {
    host.querySelector('[data-undo]').disabled = !batches.length;
    host.querySelector('[data-redo]').disabled = !redo.length;
    host.querySelector('[data-download]').disabled = pending || !corrected;
    host.querySelectorAll('[data-needs-row]').forEach(el => el.disabled = chosen === null);
  }
  function changed() {
    revision++; pending = true; corrected = null;
    controller?.abort(); clearTimeout(timer); cancelReconcilePreview();
    status('Alterações locais · atualizando modelo e saldos…'); updateControls();
    timer = setTimeout(saveDraft, 650);
  }
  function addBatch(ops, render = false) {
    if (!ops.length) return;
    batches.push(ops); redo = []; changed();
    if (render) renderRows();
  }
  async function saveDraft() {
    timer = null;
    const token = revision, source = original;
    controller = new AbortController();
    const signal = controller.signal;
    try {
      const body = new FormData(); body.append('file', source); body.append('operations_json', JSON.stringify(operations()));
      const response = await fetch(`${API()}/api/v1/model-editor/apply`, {method:'POST', body, signal});
      if (!response.ok) throw new Error(await responseError(response));
      const blob = await response.blob();
      if (token !== revision || signal.aborted) return;
      corrected = new File([blob], source.name.replace(/\.(xlsx|xls)$/i, '') + '_CORRIGIDO.xlsx', {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
      pending = false; status('Modelo atualizado nesta sessão · a conferência usa esta versão e os extratos anexados.');
      updateControls(); scheduleReconcilePreview();
    } catch (error) {
      if (token !== revision || signal.aborted) return;
      pending = true; status(`Corrija a edição para atualizar os saldos: ${error.message}`); updateControls();
    }
  }
  function selectRow(index) {
    chosen = index;
    host.querySelectorAll('[data-editor-row]').forEach(el => el.classList.toggle('editor-selected', Number(el.dataset.editorRow) === index));
    updateControls();
    host.querySelector('.editor-selection').textContent = `Linha ${index + 1} selecionada`;
  }
  function display(value, column) {
    const label = currentSheet().columns[column].normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
    return label === 'VALOR' && typeof value === 'number' ? value.toLocaleString('pt-BR', {maximumFractionDigits:10}) : String(value ?? '');
  }
  function renderRows() {
    const sheet = currentSheet(), rows = replay();
    const query = (host.querySelector('.editor-search')?.value || '').toLocaleLowerCase('pt-BR').trim();
    const visible = rows.map((row,index) => ({row,index})).filter(({row}) => !query || row.some((v,c) => display(v,c).toLocaleLowerCase('pt-BR').includes(query)));
    page = Math.max(0, Math.min(page, Math.ceil(visible.length / pageSize) - 1));
    const table = document.createElement('table'); table.className = 'razync-table editor-table';
    const head = table.createTHead().insertRow();
    ['Linha', ...sheet.columns].forEach(label => { const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; head.append(th); });
    const body = table.createTBody();
    visible.slice(page * pageSize, (page + 1) * pageSize).forEach(({row,index}) => {
      const tr = body.insertRow(); tr.dataset.editorRow = index;
      tr.classList.toggle('editor-selected', chosen === index);
      const pick = button(String(index + 1), () => selectRow(index));
      pick.setAttribute('aria-label', `Selecionar linha ${index + 1}`); tr.insertCell().append(pick);
      sheet.columns.forEach((column, col) => {
        const td = tr.insertCell(), cell = document.createElement('input'); cell.type = 'text';
        let cellBatch = null;
        cell.value = display(row[col], col); cell.setAttribute('aria-label', `${column}, linha ${index + 1}`);
        if (/^(VALOR|D[ÉE]BITO|CR[ÉE]DITO)$/i.test(column)) cell.className = 'editor-number';
        cell.addEventListener('focus', () => selectRow(index));
        cell.addEventListener('input', () => {
          const op = {kind:'set', sheet:sheet.name, row:sheet.header + 1 + index, col:col + 1, value:cell.value};
          if (cellBatch && batches.at(-1) === cellBatch) { cellBatch[0] = op; changed(); }
          else { cellBatch = [op]; addBatch(cellBatch); }
        });
        cell.addEventListener('blur', () => { cellBatch = null; });
        cell.addEventListener('paste', event => {
          const text = event.clipboardData.getData('text/plain');
          if (!/[\t\n]/.test(text)) return;
          event.preventDefault();
          const lines = text.replace(/\r/g, '').replace(/\n$/, '').split('\n').map(line => line.split('\t'));
          if (lines.some(line => col + line.length > sheet.columns.length)) return status('A colagem ultrapassa as colunas da planilha.');
          const ops = [], need = index + lines.length - rows.length;
          for (let i = 0; i < need; i++) ops.push({kind:'insert', sheet:sheet.name, row:sheet.header + 1 + rows.length + i});
          lines.forEach((line, r) => line.forEach((value, c) => ops.push({kind:'set', sheet:sheet.name, row:sheet.header + 1 + index + r, col:col + c + 1, value})));
          addBatch(ops, true);
        });
        td.append(cell);
      });
    });
    host.querySelector('.editor-table-scroll').replaceChildren(table);
    host.querySelector('.editor-page-label').textContent = `${visible.length} de ${rows.length} linha(s) · página ${page + 1} de ${Math.max(1, Math.ceil(visible.length / pageSize))}`;
    host.querySelector('[data-previous]').disabled = page === 0;
    host.querySelector('[data-next]').disabled = (page + 1) * pageSize >= visible.length;
    if (chosen === null) host.querySelector('.editor-selection').textContent = 'Selecione uma linha pelo número ou clique em uma célula.';
    updateControls();
  }
  function insert(where) {
    const rows = replay(), index = where === 'end' ? rows.length : chosen + (where === 'after' ? 1 : 0);
    if (where !== 'end' && chosen === null) return;
    addBatch([{kind:'insert', sheet:currentSheet().name, row:currentSheet().header + 1 + index}]);
    host.querySelector('.editor-search').value = '';
    chosen = index; page = Math.floor(index / pageSize); renderRows();
  }
  function mount() {
    host.replaceChildren(); host.hidden = false;
    const nav = document.createElement('div'); nav.className = 'editor-tabs';
    for (const [name, label] of [['editor','Editar planilha'], ['balance','Conferência de saldos']]) {
      const tab = button(label, () => view(name)); tab.dataset.editorView = name; nav.append(tab);
    }
    const message = document.createElement('p'); message.className = 'editor-status'; message.setAttribute('role','status');
    const content = document.createElement('div'); content.className = 'editor-content';
    const intro = document.createElement('p'); intro.textContent = 'Edite as células: a conferência atualiza após uma pausa na digitação. Selecione uma linha para inserir ou excluir. As alterações ficam nesta sessão: baixe o modelo corrigido antes de sair.';
    const tools = document.createElement('div'); tools.className = 'editor-toolbar';
    const label = document.createElement('label'); label.textContent = 'Aba da planilha';
    const select = document.createElement('select'); select.setAttribute('aria-label','Aba da planilha');
    sheets.forEach((sheet, i) => { const option = document.createElement('option'); option.value = i; option.textContent = sheet.name; select.append(option); });
    select.addEventListener('change', () => { active = Number(select.value); page = 0; chosen = null; renderRows(); }); label.append(select); tools.append(label);
    tools.append(button('Adicionar no final', () => insert('end')));
    for (const [label, where] of [['Inserir acima','before'],['Inserir abaixo','after']]) { const el = button(label, () => insert(where)); el.dataset.needsRow = ''; tools.append(el); }
    const remove = button('Excluir linha', () => {
      if (chosen === null) return;
      addBatch([{kind:'delete', sheet:currentSheet().name, row:currentSheet().header + 1 + chosen}]); chosen = null; renderRows();
    }); remove.dataset.needsRow = ''; tools.append(remove);
    const undoButton = button('Desfazer', () => { if (batches.length) { redo.push(batches.pop()); chosen = null; changed(); renderRows(); } }); undoButton.dataset.undo = ''; tools.append(undoButton);
    const redoButton = button('Refazer', () => { if (redo.length) { batches.push(redo.pop()); chosen = null; changed(); renderRows(); } }); redoButton.dataset.redo = ''; tools.append(redoButton);
    const download = button('Baixar modelo corrigido', () => {
      if (!corrected || pending) return;
      const url = URL.createObjectURL(corrected), a = document.createElement('a'); a.href = url; a.download = corrected.name;
      document.body.appendChild(a); a.click(); a.remove(); downloadedRevision = revision; setTimeout(() => URL.revokeObjectURL(url), 3000);
    }); download.dataset.download = ''; tools.append(download);
    const selection = document.createElement('p'); selection.className = 'editor-selection'; selection.textContent = 'Selecione uma linha pelo número ou clique em uma célula.';
    const scroll = document.createElement('div'); scroll.className = 'preview-table-scroll editor-table-scroll';
    const search = document.createElement('input'); search.type = 'search'; search.className = 'editor-search'; search.placeholder = 'Buscar data, valor, conta ou histórico'; search.setAttribute('aria-label','Buscar no Modelo Final');
    search.addEventListener('input', () => { page = 0; chosen = null; renderRows(); });
    const pager = document.createElement('div'); pager.className = 'editor-pager';
    const previous = button('Anterior', () => { page--; renderRows(); }); previous.dataset.previous = '';
    const next = button('Próxima', () => { page++; renderRows(); }); next.dataset.next = '';
    const pageLabel = document.createElement('span'); pageLabel.className = 'editor-page-label'; pager.append(previous,pageLabel,next);
    content.append(intro,tools,search,selection,scroll,pager); host.append(nav,message,content); renderRows(); view('editor');
  }
  input.addEventListener('change', async () => {
    const source = input.files[0];
    reset(false); cancelReconcilePreview(); original = source;
    if (!original) return;
    const token = revision; pending = true;
    controller = new AbortController(); const signal = controller.signal;
    host.hidden = false; host.textContent = 'Abrindo Modelo Final para edição…';
    try {
      const body = new FormData(); body.append('file', original);
      const response = await fetch(`${API()}/api/v1/model-editor/open`, {method:'POST',body,signal});
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      if (token !== revision || signal.aborted) return;
      sheets = result.sheets; mount(); changed();
    } catch (error) {
      if (token !== revision || signal.aborted) return;
      // Unsupported workbooks can still use the existing upload-and-reconcile flow.
      pending = false; host.textContent = `Editor indisponível para este arquivo: ${error.message} A conferência com o arquivo original continua disponível.`;
      scheduleReconcilePreview();
    }
  });
  form.addEventListener('submit', event => {
    if (!pending) return;
    event.preventDefault(); event.stopImmediatePropagation();
    document.querySelector('#reconcileMessage').textContent = 'Conclua a edição e aguarde a atualização do modelo antes de conferir.';
  }, true);
  window.addEventListener('beforeunload', event => { if (batches.length && downloadedRevision !== revision) { event.preventDefault(); event.returnValue = ''; } });
})();
