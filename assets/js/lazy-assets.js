/* Recursos opcionais carregam uma vez; falhas permitem nova tentativa. */
globalThis.RazyncAssets = (() => {
  const pending = new Map();
  function loadElement(marker) {
    if (marker.dataset.loaded === 'true') return Promise.resolve();
    return new Promise((resolve,reject) => {
      const script = marker.tagName === 'SCRIPT';
      const element = script ? document.createElement('script') : marker;
      const fail = () => {
        if (script) element.remove(); else element.rel = 'razync-lazy-stylesheet';
        reject(new Error('Não foi possível carregar a ferramenta. Clique novamente para tentar.'));
      };
      element.addEventListener('load',()=> {marker.dataset.loaded='true';resolve();},{once:true});
      element.addEventListener('error',fail,{once:true});
      if (script) {element.src=marker.getAttribute('src');element.async=false;document.body.appendChild(element);}
      else element.rel='stylesheet';
    });
  }
  function load(tool) {
    if (pending.has(tool)) return pending.get(tool);
    const markers=[...document.querySelectorAll(`[data-lazy-tool="${tool}"]`)];
    const styles=markers.filter(item=>item.tagName==='LINK');
    const scripts=markers.filter(item=>item.tagName==='SCRIPT');
    const promise=Promise.all(styles.map(loadElement)).then(async()=> {
      for (const script of scripts) await loadElement(script);
    }).catch(error=> {pending.delete(tool);throw error;});
    pending.set(tool,promise);
    return promise;
  }
  return {load};
})();
