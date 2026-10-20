// Textos vindos de arquivos, cadastros ou API devem permanecer texto no HTML.
const RazyncDOM = Object.freeze({
  escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    })[character]);
  }
});
