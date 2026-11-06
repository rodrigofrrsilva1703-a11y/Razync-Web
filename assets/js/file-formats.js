/* Keep upload instructions aligned with each field's actual accept attribute. */
(() => {
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
    const text = formats.length ? `Formatos aceitos: ${formats.join(', ')}` : 'Formatos aceitos: todos os tipos de arquivo';
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
