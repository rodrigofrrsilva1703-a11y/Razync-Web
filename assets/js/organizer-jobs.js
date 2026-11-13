/* Um envio por lote; consultas curtas acompanham o trabalho sem reenviar PDFs. */
globalThis.RazyncOrganizer = Object.freeze({
  async wait(response, {signal, onProgress = () => {}} = {}) {
    if (response.status !== 202) return response;
    const {job_token:token} = await response.json();
    if (!token) throw new Error('O servidor não confirmou o processamento. Tente novamente.');
    const url = `${API()}/api/v1/organizador/${encodeURIComponent(token)}`;
    const cancel = () => { fetch(url, {method:'DELETE',keepalive:true}).catch(() => {}); };
    const pause = () => new Promise((resolve, reject) => {
      if (signal?.aborted) return reject(new DOMException('Cancelado','AbortError'));
      const abort = () => { clearTimeout(timer); reject(new DOMException('Cancelado','AbortError')); };
      const timer = setTimeout(() => { signal?.removeEventListener('abort',abort); resolve(); }, 1500);
      signal?.addEventListener('abort',abort,{once:true});
    });
    signal?.addEventListener('abort',cancel,{once:true});
    try {
      if (signal?.aborted) { cancel(); throw new DOMException('Cancelado','AbortError'); }
      let failures = 0;
      while (true) {
        let status;
        try {
          const poll = await fetch(url, {signal,cache:'no-store',referrerPolicy:'no-referrer'});
          if (!poll.ok) {
            if (poll.status === 404) throw new Error('O processamento expirou ou o servidor reiniciou. Gere o lote novamente.');
            if (poll.status < 500) throw new Error(await responseError(poll));
            status = null;
          } else status = await poll.json();
        } catch (error) {
          if (error.name !== 'TypeError') throw error;
        }
        if (!status) {
          if (++failures >= 5) throw new Error('A conexão com o processamento foi perdida. Tente novamente quando a conexão voltar.');
          onProgress({state:'reconnecting'});
        } else {
          failures = 0;
          onProgress(status);
          if (status.state === 'ready') {
            const result = await fetch(`${url}/resultado`,{signal,cache:'no-store',referrerPolicy:'no-referrer'});
            if (!result.ok) throw new Error(await responseError(result));
            return result;
          }
          if (status.state === 'error') throw new Error(status.error || 'Não foi possível organizar este lote.');
          if (status.state === 'cancelled') throw new DOMException('Cancelado','AbortError');
        }
        await pause();
      }
    } finally { signal?.removeEventListener('abort',cancel); }
  }
});
