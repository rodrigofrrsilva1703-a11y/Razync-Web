/* Keep upload instructions aligned with each field's actual accept attribute. */
(() => {
  // Audited against migration_services.statement / main._process_modular.
  // These readers consume PDF bytes directly, regardless of the file picker.
  const pdfOnly = new Set([47,88,154,285,625,626,734,745,803,818,912,964,969,1024,1033,1131,1151,1187,1208,1399,1211,1248,1522,1532]);
  // These companies use engine.processar_extrato_unificado for reconciliation.
  const universalStatements = new Set([3,178,242,266,343,521,968,1000,1001,1064,1096,1396,1402,1408,1529]);
  function statementAccept(company, bank) {
    const code = Number(company?.codigo);
    if (!Object.hasOwn(company?.capabilities?.banks || {}, bank)) return '';
    if (code === 1165 || code === 1166) return '.pdf';
    if (code === 1058) return bank === 'itau' ? '.pdf,.ofx,.xls,.xlsx,.csv' : '.pdf';
    if (code === 977) return bank === 'bradesco' ? '.pdf,.zip' : '.pdf';
    if (pdfOnly.has(code)) return '.pdf';
    if (code === 1530) return '.xls,.xlsx';
    if (code === 841) return '.pdf,.xls,.xlsx';
    if (code === 968 && bank === 'bradesco') return '.pdf';
    if (universalStatements.has(code)) return '.pdf,.xls,.xlsx,.csv,.ofx';
    return '';
  }
  globalThis.RazyncFileFormats = {statementAccept};
  const labels = new WeakMap();
  let sequence = 0;
  const mimeNames = {
    'application/pdf':'PDF',
    'application/vnd.ms-excel':'XLS',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'XLSX',
    'text/csv':'CSV', 'application/json':'JSON', 'text/plain':'TXT',
    'application/zip':'ZIP', 'application/x-zip-compressed':'ZIP',
    'application/x-ofx':'OFX', 'image/*':'Imagens',
    'audio/*':'Áudio', 'video/*':'Vídeo'
  };
  function sync(input) {
    if (input.type !== 'file') return;
    const container = input.closest('.file-drop-shell') || input.parentElement;
    if (!container) return;
    let label = labels.get(input);
    if (!label) {
      label = document.createElement('small');
      label.className = 'file-accepted-formats';
      label.id = `file-accepted-formats-${++sequence}`;
      labels.set(input, label);
      const describedBy = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
      input.setAttribute('aria-describedby', [...new Set([...describedBy, label.id])].join(' '));
    }
    const formats = [...new Set(String(input.accept || '').split(',').map(value => {
      const token = value.trim().toLowerCase();
      if (!token) return '';
      return mimeNames[token] || (token.startsWith('.') ? token.slice(1) : token).toUpperCase();
    }).filter(Boolean))];
    const text = formats.length ? `Formatos aceitos: ${formats.join(', ')}` : 'Consulte os formatos nas instruções da ferramenta.';
    if (label.textContent !== text) label.textContent = text;
    if (label.parentElement !== container) container.appendChild(label);
  }
  function scan(root) {
    if (root.nodeType !== 1) return;
    if (root.matches('input[type="file"]')) sync(root);
    root.querySelectorAll('input[type="file"]').forEach(sync);
  }
  document.querySelectorAll('input[type="file"]').forEach(sync);
  new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'attributes') sync(record.target);
      else record.addedNodes.forEach(scan);
    }
  }).observe(document.documentElement, {subtree:true, childList:true, attributes:true, attributeFilter:['accept','type']});
})();
