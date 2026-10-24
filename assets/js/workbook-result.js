/* Reutiliza a saída da prévia; mantém compatibilidade com APIs anteriores. */
globalThis.RazyncResults = Object.freeze({
  async downloadResponse(token, url, options = {}) {
    if (token) {
      const response = await fetch(`${API()}/api/v1/resultados/${encodeURIComponent(token)}`, {
        signal:options.signal, cache:'no-store', referrerPolicy:'no-referrer'
      });
      if (response.status !== 404 && response.status !== 410) return response;
    }
    return fetch(url, options);
  },
  async workbookPreview(response, {endpoint, snapshot, signal, filename}) {
    if ((response.headers.get('content-type') || '').includes('application/vnd.razync.preview+json')) {
      const result = await response.json();
      return {preview:result.preview, download:async()=> {
        const report = await RazyncResults.downloadResponse(result.report_token, endpoint, {method:'POST',body:snapshot,signal});
        if (!report.ok) throw new Error(await responseError(report));
        await downloadBlob(report, filename);
      }};
    }
    const workbook = await response.blob();
    const body = new FormData(); body.append('file', workbook, 'modelo.xlsx');
    const preview = await fetch(`${API()}/api/v1/modelo-preview`, {method:'POST',body,signal});
    if (!preview.ok) throw new Error(await responseError(preview));
    const headers = response.headers.get('content-disposition');
    return {preview:await preview.json(), download:()=>downloadBlob(new Response(workbook, {
      headers:headers ? {'Content-Disposition':headers} : {}
    }), filename)};
  }
});
