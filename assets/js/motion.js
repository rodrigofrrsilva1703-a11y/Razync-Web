/* Presentation only: follows the existing status messages without changing requests. */
(() => {
  const selector = '[id$="Message"], .bank-investments-message';
  function update(element) {
    const text = element.textContent.trim();
    const explicit = element.dataset?.state;
    const busy = explicit === 'loading' || (!['error', 'success', 'cancelled'].includes(explicit) && (
      /^(Analisando|Classificando|Conferindo|Processando|Carregando|Abrindo|Montando|Gerando|Preparando|Validando|Aprendendo|Importando|Lendo|Consultando|Exportando|Salvando|Buscando|Atualizando)\b/i.test(text)
      || /^Arquivos prontos\..*(Montando|Conferindo)/i.test(text)));
    element.classList.toggle('preview-loading', busy);
    element.setAttribute('aria-busy', String(busy));
    if (!element.hasAttribute('role')) element.setAttribute('role', 'status');
    if (!element.hasAttribute('aria-live')) element.setAttribute('aria-live', 'polite');
  }
  document.querySelectorAll(selector).forEach(update);
  new MutationObserver(records => {
    const changed = new Set();
    records.forEach(record => {
      const element = record.target.nodeType === 1 ? record.target : record.target.parentElement;
      const message = element?.closest(selector);
      if (message) changed.add(message);
      record.addedNodes.forEach(node => {
        if (node.nodeType !== 1) return;
        if (node.matches(selector)) changed.add(node);
        node.querySelectorAll(selector).forEach(el => changed.add(el));
      });
    });
    changed.forEach(update);
  }).observe(document.body, {subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:['data-state']});
})();

