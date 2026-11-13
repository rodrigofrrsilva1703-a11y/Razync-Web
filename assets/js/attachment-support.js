/* Older API versions accept only one file in these fields. Never silently drop the rest. */
(() => {
  const send = window.fetch.bind(window);
  const batchFields = new Set(["file", "model_file", "extrato", "razao", "acumuladores", "entradas", "saidas"]);
  let supportsBatch = false;
  window.fetch = async (url, options = {}) => {
    const base = window.RAZYNC_CONFIG.apiBase.replace(/\/$/, "");
    if (String(url).startsWith(base + "/api/") && options.body instanceof FormData) {
      const counts = new Map();
      for (const [key, value] of options.body.entries()) {
        if (batchFields.has(key) && value instanceof Blob) counts.set(key, (counts.get(key) || 0) + 1);
      }
      if ([...counts.values()].some(count => count > 1) && !supportsBatch) {
        const response = await send(base + "/health", {signal:options.signal, cache:"no-store"});
        if (!response.ok) throw new Error("Não foi possível verificar o suporte a vários anexos. Tente novamente.");
        const health = await response.json();
        supportsBatch = health.capabilities?.multiple_documents === true;
        if (!supportsBatch) throw new Error("Os anexos foram mantidos. O processamento de vários documentos nesta ferramenta aguarda a atualização do serviço no Railway.");
      }
    }
    return send(url, options);
  };
})();
