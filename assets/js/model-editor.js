/* Excel-like editor for Modelo Final. Drafts stay in this tab and reconciliation always uses the latest valid workbook. */
(() => {
  const host = document.querySelector('#reconcileEditor');
  const input = document.querySelector('#modelFile');
  const form = document.querySelector('#reconcileForm');
  const balanceView = document.querySelector('#reconcileBalanceView');
  if (!host || !input || !form || !balanceView) return;

  let original, corrected, sheets = [], batches = [], redo = [];
  let active = 0, page = 0, chosen = null, activeCell = null;
  let revision = 0, timer, controller, pending = false, downloadedRevision = -1;
  const pageSize = 200;

  const operations = () => batches.flat();
  const currentSheet = () => sheets[active];
  const status = text => {
    const el = host.querySelector('.editor-status');
    if (el) el.textContent = text;
  };
  const button = (label, action, className = '') => {
    const el = document.createElement('button');
    el.type = 'button';
    el.textContent = label;
    el.className = className;
    el.addEventListener('click', action);
    return el;
  };
  const columnLetter = index => {
    let n = index + 1, out = '';
    while (n > 0) {
      const remainder = (n - 1) % 26;
      out = String.fromCharCode(65 + remainder) + out;
      n = Math.floor((n - 1) / 26);
    }
    return out;
  };
  const cellAddress = (row, col) => `${columnLetter(col)}${row + 1}`;

  function reset(clearFile = true) {
    revision++;
    controller?.abort();
    clearTimeout(timer);
    original = corrected = null;
    sheets = [];
    batches = [];
    redo = [];
    active = page = 0;
    chosen = null;
    activeCell = null;
    pending = false;
    host.replaceChildren();
    host.hidden = true;
    balanceView.hidden = false;
    if (clearFile && input.files.length) {
      input.value = '';
      input.dispatchEvent(new Event('change', {bubbles:true}));
    }
  }

  globalThis.RazyncModelEditor = {
    reset,
    file: () => corrected,
    canLeave: () => !batches.length || downloadedRevision === revision ||
      window.confirm('O modelo tem alterações que ainda não foram baixadas. Sair e descartar essas alterações?')
  };

  function view(name) {
    host.querySelector('.editor-content').hidden = name !== 'editor';
    balanceView.hidden = name === 'editor';
    host.querySelectorAll('[data-editor-view]').forEach(el => {
      const selected = el.dataset.editorView === name;
      el.classList.toggle('active', selected);
      el.setAttribute('aria-pressed', String(selected));
    });
  }

  function replay() {
    const sheet = currentSheet();
    const rows = sheet.rows.map(row => [...row]);
    for (const op of operations().filter(op => op.sheet === sheet.name)) {
      const index = op.row - sheet.header - 1;
      if (op.kind === 'insert') rows.splice(index, 0, sheet.columns.map(() => ''));
      if (op.kind === 'delete') rows.splice(index, 1);
      if (op.kind === 'set' && rows[index]) rows[index][op.col - 1] = op.value;
    }
    return rows;
  }

  function updateControls() {
    const undo = host.querySelector('[data-undo]');
    const redoButton = host.querySelector('[data-redo]');
    const download = host.querySelector('[data-download]');
    if (undo) undo.disabled = !batches.length;
    if (redoButton) redoButton.disabled = !redo.length;
    if (download) download.disabled = pending || !corrected;
    host.querySelectorAll('[data-needs-row]').forEach(el => el.disabled = chosen === null);
  }

  function changed() {
    revision++;
    pending = true;
    corrected = null;
    controller?.abort();
    clearTimeout(timer);
    cancelReconcilePreview();
    status('Salvando alterações automaticamente…');
    updateControls();
    timer = setTimeout(saveDraft, 450);
  }

  function addBatch(ops, render = false) {
    if (!ops.length) return;
    batches.push(ops);
    redo = [];
    changed();
    if (render) renderRows();
  }

  async function saveDraft() {
    timer = null;
    const token = revision;
    const source = original;
    controller = new AbortController();
    const signal = controller.signal;
    try {
      const body = new FormData();
      body.append('file', source);
      body.append('operations_json', JSON.stringify(operations()));
      const response = await fetch(`${API()}/api/v1/model-editor/apply`, {method:'POST', body, signal});
      if (!response.ok) throw new Error(await responseError(response));
      const blob = await response.blob();
      if (token !== revision || signal.aborted) return;
      corrected = new File(
        [blob],
        source.name.replace(/\.(xlsx|xls)$/i, '') + '_CORRIGIDO.xlsx',
        {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
      );
      pending = false;
      status('Salvo automaticamente · a conferência já usa esta versão.');
      updateControls();
      scheduleReconcilePreview();
    } catch (error) {
      if (token !== revision || signal.aborted) return;
      pending = true;
      status(`Corrija a edição para atualizar os saldos: ${error.message}`);
      updateControls();
    }
  }

  function display(value, column) {
    const label = currentSheet().columns[column]
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
    return label === 'VALOR' && typeof value === 'number'
      ? value.toLocaleString('pt-BR', {maximumFractionDigits:10})
      : String(value ?? '');
  }

  function cellElement(row, col) {
    return host.querySelector(`[data-cell-row="${row}"][data-cell-col="${col}"]`);
  }

  function syncCellChrome(focus = false) {
    if (!activeCell) return;
    const {row, col} = activeCell;
    const rows = replay();
    const target = cellElement(row, col);
    host.querySelectorAll('.editor-active-cell').forEach(el => el.classList.remove('editor-active-cell'));
    if (target) {
      target.classList.add('editor-active-cell');
      if (focus) {
        target.focus({preventScroll:true});
        target.select();
        target.scrollIntoView({block:'nearest',inline:'nearest'});
      }
    }
    const nameBox = host.querySelector('.editor-name-box');
    const valueBar = host.querySelector('.editor-value-bar');
    if (nameBox) nameBox.value = cellAddress(row, col);
    if (valueBar) valueBar.value = target ? target.value : display(rows[row]?.[col], col);
    host.querySelectorAll('[data-editor-row]').forEach(el => {
      el.classList.toggle('editor-selected', Number(el.dataset.editorRow) === row);
    });
    const selection = host.querySelector('.editor-selection');
    if (selection) {
      selection.textContent = `${cellAddress(row,col)} · linha ${row + 1} · ${currentSheet().columns[col] || ''}`;
    }
  }

  function selectCell(row, col, element = null) {
    chosen = row;
    activeCell = {row, col};
    updateControls();
    syncCellChrome(false);
    if (element) {
      const valueBar = host.querySelector('.editor-value-bar');
      if (valueBar) valueBar.value = element.value;
    }
  }

  function selectRow(index) {
    chosen = index;
    activeCell = activeCell && activeCell.row === index ? activeCell : {row:index,col:0};
    updateControls();
    syncCellChrome(false);
  }

  function focusCell(row, col) {
    const rows = replay();
    if (!rows.length) return;
    row = Math.max(0, Math.min(row, rows.length - 1));
    col = Math.max(0, Math.min(col, currentSheet().columns.length - 1));
    chosen = row;
    activeCell = {row, col};
    const wantedPage = Math.floor(row / pageSize);
    const search = host.querySelector('.editor-search');
    if ((search?.value || '').trim()) search.value = '';
    if (wantedPage !== page || !cellElement(row,col)) {
      page = wantedPage;
      renderRows();
    }
    requestAnimationFrame(() => syncCellChrome(true));
  }

  function insertAt(index) {
    const rows = replay();
    const bounded = Math.max(0, Math.min(index, rows.length));
    batches.push([{
      kind:'insert',
      sheet:currentSheet().name,
      row:currentSheet().header + 1 + bounded
    }]);
    redo = [];
    changed();
    chosen = bounded;
    activeCell = {row:bounded,col:0};
    page = Math.floor(bounded / pageSize);
    renderRows();
  }

  function moveCell(row, col, direction, backwards = false) {
    const rows = replay();
    const columns = currentSheet().columns.length;
    let nextRow = row, nextCol = col;

    if (direction === 'vertical') nextRow += backwards ? -1 : 1;
    if (direction === 'horizontal') {
      nextCol += backwards ? -1 : 1;
      if (nextCol >= columns) { nextCol = 0; nextRow += 1; }
      if (nextCol < 0) { nextCol = columns - 1; nextRow -= 1; }
    }

    if (nextRow < 0) nextRow = 0;
    if (nextRow >= rows.length) {
      insertAt(rows.length);
      nextRow = rows.length;
      nextCol = Math.max(0, Math.min(nextCol, columns - 1));
    }
    focusCell(nextRow, nextCol);
  }

  function setCellValue(row, col, value, batchRef = null) {
    const op = {
      kind:'set',
      sheet:currentSheet().name,
      row:currentSheet().header + 1 + row,
      col:col + 1,
      value
    };
    if (batchRef && batches.at(-1) === batchRef) {
      batchRef[0] = op;
      changed();
    } else {
      addBatch([op]);
    }
  }

  function undo() {
    if (!batches.length) return;
    redo.push(batches.pop());
    chosen = null;
    activeCell = null;
    changed();
    renderRows();
  }

  function redoChange() {
    if (!redo.length) return;
    batches.push(redo.pop());
    chosen = null;
    activeCell = null;
    changed();
    renderRows();
  }

  function downloadCorrected() {
    if (!corrected || pending) return;
    const url = URL.createObjectURL(corrected);
    const a = document.createElement('a');
    a.href = url;
    a.download = corrected.name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    downloadedRevision = revision;
    setTimeout(() => URL.revokeObjectURL(url), 3000);
  }

  function renderRows() {
    const sheet = currentSheet();
    const rows = replay();
    const query = (host.querySelector('.editor-search')?.value || '')
      .toLocaleLowerCase('pt-BR').trim();
    const visible = rows
      .map((row,index) => ({row,index}))
      .filter(({row}) => !query || row.some((v,c) =>
        display(v,c).toLocaleLowerCase('pt-BR').includes(query)
      ));

    page = Math.max(0, Math.min(page, Math.max(0, Math.ceil(visible.length / pageSize) - 1)));
    const table = document.createElement('table');
    table.className = 'razync-table editor-table';

    const head = table.createTHead().insertRow();
    const corner = document.createElement('th');
    corner.className = 'editor-corner';
    corner.textContent = '#';
    head.append(corner);
    sheet.columns.forEach((label,index) => {
      const th = document.createElement('th');
      th.scope = 'col';
      th.innerHTML = `<span class="editor-col-letter">${columnLetter(index)}</span><strong></strong>`;
      th.querySelector('strong').textContent = label;
      head.append(th);
    });

    const body = table.createTBody();
    visible.slice(page * pageSize, (page + 1) * pageSize).forEach(({row,index}) => {
      const tr = body.insertRow();
      tr.dataset.editorRow = index;
      tr.classList.toggle('editor-selected', chosen === index);

      const rowCell = tr.insertCell();
      rowCell.className = 'editor-row-number';
      const pick = button(String(index + 1), () => selectRow(index));
      pick.setAttribute('aria-label', `Selecionar linha ${index + 1}`);
      rowCell.append(pick);

      sheet.columns.forEach((column, col) => {
        const td = tr.insertCell();
        const cell = document.createElement('input');
        cell.type = 'text';
        cell.dataset.cellRow = String(index);
        cell.dataset.cellCol = String(col);
        let cellBatch = null;
        cell.value = display(row[col], col);
        cell.setAttribute('aria-label', `${column}, linha ${index + 1}`);
        cell.autocomplete = 'off';
        cell.spellcheck = false;
        if (/^(VALOR|D[ÉE]BITO|CR[ÉE]DITO)$/i.test(column)) cell.className = 'editor-number';

        cell.addEventListener('focus', () => selectCell(index, col, cell));
        cell.addEventListener('input', () => {
          selectCell(index, col, cell);
          if (cellBatch && batches.at(-1) === cellBatch) {
            setCellValue(index,col,cell.value,cellBatch);
          } else {
            cellBatch = [{
              kind:'set',
              sheet:sheet.name,
              row:sheet.header + 1 + index,
              col:col + 1,
              value:cell.value
            }];
            addBatch(cellBatch);
          }
          const valueBar = host.querySelector('.editor-value-bar');
          if (valueBar) valueBar.value = cell.value;
        });
        cell.addEventListener('blur', () => { cellBatch = null; });
        cell.addEventListener('keydown', event => {
          if (event.key === 'Enter') {
            event.preventDefault();
            cellBatch = null;
            moveCell(index,col,'vertical',event.shiftKey);
          } else if (event.key === 'Tab') {
            event.preventDefault();
            cellBatch = null;
            moveCell(index,col,'horizontal',event.shiftKey);
          } else if (event.key === 'Escape') {
            cell.blur();
          }
        });
        cell.addEventListener('paste', event => {
          const text = event.clipboardData.getData('text/plain');
          if (!/[\t\n]/.test(text)) return;
          event.preventDefault();
          const matrix = text.replace(/\r/g, '').replace(/\n$/, '')
            .split('\n').map(line => line.split('\t'));
          if (matrix.some(line => col + line.length > sheet.columns.length)) {
            return status('A colagem ultrapassa as colunas da planilha.');
          }
          const ops = [];
          const need = index + matrix.length - rows.length;
          for (let i = 0; i < need; i++) {
            ops.push({kind:'insert',sheet:sheet.name,row:sheet.header + 1 + rows.length + i});
          }
          matrix.forEach((line,r) => line.forEach((value,c) => {
            ops.push({
              kind:'set',
              sheet:sheet.name,
              row:sheet.header + 1 + index + r,
              col:col + c + 1,
              value
            });
          }));
          activeCell = {
            row:index + matrix.length - 1,
            col:col + matrix[matrix.length - 1].length - 1
          };
          chosen = activeCell.row;
          addBatch(ops,true);
          requestAnimationFrame(() => syncCellChrome(true));
        });
        td.append(cell);
      });
    });

    host.querySelector('.editor-table-scroll').replaceChildren(table);
    const pages = Math.max(1, Math.ceil(visible.length / pageSize));
    host.querySelector('.editor-page-label').textContent =
      `${visible.length} de ${rows.length} linha(s) · página ${page + 1} de ${pages}`;
    host.querySelector('[data-previous]').disabled = page === 0;
    host.querySelector('[data-next]').disabled = (page + 1) * pageSize >= visible.length;

    if (!activeCell && rows.length) activeCell = {row:visible[0]?.index ?? 0,col:0};
    if (activeCell) {
      chosen = activeCell.row;
      syncCellChrome(false);
    } else {
      host.querySelector('.editor-selection').textContent = 'Clique em uma célula para editar.';
    }
    updateControls();
  }

  function insert(where) {
    const rows = replay();
    const index = where === 'end'
      ? rows.length
      : chosen + (where === 'after' ? 1 : 0);
    if (where !== 'end' && chosen === null) return;
    insertAt(index);
    requestAnimationFrame(() => focusCell(index,0));
  }

  function mount() {
    host.replaceChildren();
    host.hidden = false;

    const nav = document.createElement('div');
    nav.className = 'editor-tabs';
    for (const [name,label] of [['editor','Editar planilha'],['balance','Conferência de saldos']]) {
      const tab = button(label, () => view(name));
      tab.dataset.editorView = name;
      nav.append(tab);
    }

    const message = document.createElement('p');
    message.className = 'editor-status';
    message.setAttribute('role','status');

    const content = document.createElement('div');
    content.className = 'editor-content';

    const intro = document.createElement('p');
    intro.className = 'editor-hint';
    intro.textContent = 'Edição automática: digite direto nas células. Enter desce, Tab avança, Ctrl+Z desfaz e Ctrl+S baixa o modelo corrigido. A conferência recalcula sozinha.';

    const tools = document.createElement('div');
    tools.className = 'editor-toolbar';

    const label = document.createElement('label');
    label.className = 'editor-sheet-select';
    label.textContent = 'Aba';
    const select = document.createElement('select');
    select.setAttribute('aria-label','Aba da planilha');
    sheets.forEach((sheet,i) => {
      const option = document.createElement('option');
      option.value = i;
      option.textContent = sheet.name;
      select.append(option);
    });
    select.addEventListener('change', () => {
      active = Number(select.value);
      page = 0;
      chosen = null;
      activeCell = null;
      renderRows();
    });
    label.append(select);
    tools.append(label);

    const add = button('+ Linha', () => insert('end'));
    add.title = 'Adicionar uma linha no final';
    tools.append(add);

    const above = button('Inserir acima', () => insert('before'));
    above.dataset.needsRow = '';
    tools.append(above);

    const below = button('Inserir abaixo', () => insert('after'));
    below.dataset.needsRow = '';
    tools.append(below);

    const remove = button('Excluir linha', () => {
      if (chosen === null) return;
      addBatch([{
        kind:'delete',
        sheet:currentSheet().name,
        row:currentSheet().header + 1 + chosen
      }]);
      activeCell = null;
      chosen = null;
      renderRows();
    });
    remove.dataset.needsRow = '';
    tools.append(remove);

    const undoButton = button('Desfazer', undo);
    undoButton.dataset.undo = '';
    undoButton.title = 'Ctrl+Z';
    tools.append(undoButton);

    const redoButton = button('Refazer', redoChange);
    redoButton.dataset.redo = '';
    redoButton.title = 'Ctrl+Y';
    tools.append(redoButton);

    const download = button('Baixar corrigido', downloadCorrected,'editor-download');
    download.dataset.download = '';
    download.title = 'Ctrl+S';
    tools.append(download);

    const formula = document.createElement('div');
    formula.className = 'editor-formula-bar';
    const nameBox = document.createElement('input');
    nameBox.className = 'editor-name-box';
    nameBox.readOnly = true;
    nameBox.setAttribute('aria-label','Célula ativa');
    const valueLabel = document.createElement('span');
    valueLabel.textContent = 'Valor';
    valueLabel.className = 'editor-value-label';
    const valueBar = document.createElement('input');
    valueBar.className = 'editor-value-bar';
    valueBar.setAttribute('aria-label','Valor da célula ativa');
    valueBar.autocomplete = 'off';
    let formulaBatch = null;
    valueBar.addEventListener('focus', () => { formulaBatch = null; });
    valueBar.addEventListener('input', () => {
      if (!activeCell) return;
      const {row,col} = activeCell;
      const cell = cellElement(row,col);
      if (cell) cell.value = valueBar.value;
      if (formulaBatch && batches.at(-1) === formulaBatch) {
        setCellValue(row,col,valueBar.value,formulaBatch);
      } else {
        formulaBatch = [{
          kind:'set',
          sheet:currentSheet().name,
          row:currentSheet().header + 1 + row,
          col:col + 1,
          value:valueBar.value
        }];
        addBatch(formulaBatch);
      }
    });
    valueBar.addEventListener('blur', () => { formulaBatch = null; });
    valueBar.addEventListener('keydown', event => {
      if (event.key === 'Enter' && activeCell) {
        event.preventDefault();
        formulaBatch = null;
        moveCell(activeCell.row,activeCell.col,'vertical',event.shiftKey);
      }
    });
    formula.append(nameBox,valueLabel,valueBar);

    const searchRow = document.createElement('div');
    searchRow.className = 'editor-search-row';
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'editor-search';
    search.placeholder = 'Buscar na planilha';
    search.setAttribute('aria-label','Buscar no Modelo Final');
    search.addEventListener('input', () => {
      page = 0;
      chosen = null;
      activeCell = null;
      renderRows();
    });
    const selection = document.createElement('p');
    selection.className = 'editor-selection';
    selection.textContent = 'Clique em uma célula para editar.';
    searchRow.append(search,selection);

    const scroll = document.createElement('div');
    scroll.className = 'preview-table-scroll editor-table-scroll';

    const pager = document.createElement('div');
    pager.className = 'editor-pager';
    const previous = button('Anterior', () => { page--; renderRows(); });
    previous.dataset.previous = '';
    const next = button('Próxima', () => { page++; renderRows(); });
    next.dataset.next = '';
    const pageLabel = document.createElement('span');
    pageLabel.className = 'editor-page-label';
    pager.append(previous,pageLabel,next);

    content.append(intro,tools,formula,searchRow,scroll,pager);
    host.append(nav,message,content);

    host.addEventListener('keydown', event => {
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === 'z') {
        event.preventDefault();
        event.shiftKey ? redoChange() : undo();
      } else if (key === 'y') {
        event.preventDefault();
        redoChange();
      } else if (key === 's') {
        event.preventDefault();
        downloadCorrected();
      }
    });

    renderRows();
    view('editor');
    status('Pronto para editar · salvamento automático ativado.');
  }

  input.addEventListener('change', async () => {
    const source = input.files[0];
    reset(false);
    cancelReconcilePreview();
    original = source;
    if (!original) return;

    const token = revision;
    pending = true;
    controller = new AbortController();
    const signal = controller.signal;
    host.hidden = false;
    host.textContent = 'Abrindo Modelo Final para edição…';

    try {
      const body = new FormData();
      body.append('file', original);
      const response = await fetch(`${API()}/api/v1/model-editor/open`, {method:'POST',body,signal});
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      if (token !== revision || signal.aborted) return;
      sheets = result.sheets;
      mount();
      changed();
    } catch (error) {
      if (token !== revision || signal.aborted) return;
      pending = false;
      host.textContent = `Editor indisponível para este arquivo: ${error.message} A conferência com o arquivo original continua disponível.`;
      scheduleReconcilePreview();
    }
  });

  form.addEventListener('submit', event => {
    if (!pending) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    document.querySelector('#reconcileMessage').textContent =
      'Aguarde o salvamento automático da edição antes de conferir.';
  }, true);

  window.addEventListener('beforeunload', event => {
    if (batches.length && downloadedRevision !== revision) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
})();
