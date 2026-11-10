(() => {
  const key = "razync:workspace-files:v1";
  const maxAge = 86400000;
  let database;
  let queue = Promise.resolve();

  function access() {
    if (database) return database;
    database = new Promise((resolve, reject) => {
      const request = indexedDB.open(key, 1);
      request.onupgradeneeded = () => request.result.createObjectStore("drafts");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error("Armazenamento de anexos ocupado"));
    });
    return database;
  }

  function run(mode, operation) {
    const next = queue.then(async () => {
      const db = await access();
      return new Promise((resolve, reject) => {
        const tx = db.transaction("drafts", mode);
        const request = operation(tx.objectStore("drafts"));
        tx.oncomplete = () => resolve(request?.result);
        tx.onabort = () => reject(tx.error);
      });
    });
    queue = next.catch(() => {});
    return next;
  }

  function tabId(create = false) {
    let id = sessionStorage.getItem(key);
    if (!id && create) {
      id = crypto.randomUUID();
      sessionStorage.setItem(key, id);
    }
    return id;
  }

  function prune(store) {
    const cursor = store.openCursor();
    cursor.onsuccess = () => {
      const entry = cursor.result;
      if (!entry) return;
      if (Date.now() - entry.value.time >= maxAge) entry.delete();
      entry.continue();
    };
  }

  window.RazyncWorkspaceFiles = {
    async save(position, scope) {
      const files = [...scope.querySelectorAll('input[type="file"][id]')]
        .filter(input => !input.disabled && input.files.length)
        .map(input => [input.id, [...input.files]]);
      const id = tabId(Boolean(files.length));
      if (!id) return;
      await run("readwrite", store => {
        prune(store);
        return files.length ? store.put({position, files, time:Date.now()}, id) : store.delete(id);
      });
    },
    async restore(position, scope) {
      const id = tabId();
      if (!id) return;
      const draft = await run("readwrite", store => { prune(store); return store.get(id); });
      if (draft?.position !== position || Date.now() - draft.time >= maxAge) return;
      for (const [inputId, files] of draft.files) {
        const input = document.getElementById(inputId);
        if (input && scope.contains(input) && !input.disabled && !input.files.length) {
          replaceInputFiles(input, files);
        }
      }
      return draft.classification;
    },
    async saveClassification(position, classification, isCurrent) {
      const id = tabId();
      if (!id) return;
      await run("readwrite", store => {
        const request = store.get(id);
        request.onsuccess = () => {
          const draft = request.result;
          if (draft?.position === position && isCurrent()) {
            store.put({...draft, classification, time:Date.now()}, id);
          }
        };
      });
    },
    async clear() {
      const id = tabId();
      if (!id) return;
      sessionStorage.removeItem(key);
      await run("readwrite", store => store.delete(id));
    }
  };
})();
