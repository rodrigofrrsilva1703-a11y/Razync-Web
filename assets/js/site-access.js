(() => {
  const root = document.body, screen = document.querySelector('#siteAccess');
  const form = document.querySelector('#siteAccessForm'), status = document.querySelector('#siteAccessStatus');
  const exit = document.querySelector('#siteAccessExit'), retry = document.querySelector('#siteAccessRetry');
  const base = (window.RAZYNC_CONFIG?.apiBase || '').replace(/\/$/, '');
  const original = window.fetch.bind(window), prefix = '/api/v1/acesso';
  const key = 'razync:private-session:v1';
  let token = '', required = Boolean(base), release;
  const ready = new Promise(resolve => { release = resolve; });
  const stored = () => { try { return sessionStorage.getItem(key) || ''; } catch { return ''; } };
  function persist(value) {
    token = value;
    try { if (value) sessionStorage.setItem(key, value); else sessionStorage.removeItem(key); } catch {}
  }
  function call(path, options = {}) {
    const headers = new Headers(options.headers);
    if (token) headers.set('X-Razync-Session', token);
    return original(base + prefix + path, { ...options, headers, cache:'no-store', redirect:'error' });
  }
  function unlocked() {
    delete root.dataset.siteLocked;
    screen.hidden = true;
    exit.hidden = !required;
    release();
  }
  function locked(message, canLogin) {
    root.dataset.siteLocked = '';
    screen.hidden = false;
    form.hidden = !canLogin;
    retry.hidden = canLogin;
    status.textContent = message;
  }
  async function check() {
    if (!base) { required = false; unlocked(); return; }
    retry.disabled = true;
    try {
      const response = await call('/config', { signal:AbortSignal.timeout(20000) });
      if (!response.ok) throw Error();
      const config = await response.json();
      if (config.required === false) { required = false; persist(''); unlocked(); return; }
      if (config.required !== true) throw Error();
      required = true;
      persist(stored());
      if (token) {
        const response = await call('/sessao', { signal:AbortSignal.timeout(10000) });
        if (response.ok) { unlocked(); return; }
        if (response.status !== 401) throw Error();
        persist('');
      }
      locked('Entre com seu e-mail autorizado.', true);
    } catch {
      locked('Não foi possível verificar o acesso. Tente novamente.', false);
    } finally { retry.disabled = false; }
  }
  window.RazyncSiteAccess = { isPrivate: () => required };
  window.fetch = async (resource, options) => {
    if (!base) return original(resource, options);
    const url = new URL(resource instanceof Request ? resource.url : resource, location.href);
    const api = new URL(base);
    if (url.origin !== api.origin || !(url.pathname.startsWith('/api/v1/') || url.pathname === '/health')) {
      return original(resource, options);
    }
    await ready;
    const headers = new Headers(options?.headers || (resource instanceof Request ? resource.headers : undefined));
    if (token) headers.set('X-Razync-Session', token);
    const response = await original(resource, { ...options, headers, ...(token ? { cache:'no-store', redirect:'error' } : {}) });
    if (required && response.status === 401 && response.headers.get('X-Razync-Login-Required') === '1') {
      persist('');
      location.reload();
    }
    return response;
  };
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const email = document.querySelector('#siteAccessEmail'), password = document.querySelector('#siteAccessPassword');
    const button = form.querySelector('button');
    if (button.disabled) return;
    button.disabled = true;
    status.textContent = 'Validando acesso…';
    try {
      const response = await call('/entrar', { method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ email:email.value, password:password.value }), signal:AbortSignal.timeout(20000) });
      const data = await response.json();
      if (!response.ok || typeof data.session !== 'string') {
        status.textContent = response.status === 401 ? 'E-mail ou senha inválidos.' : 'Não foi possível entrar agora. Tente novamente.';
        return;
      }
      persist(data.session);
      unlocked();
    } catch { status.textContent = 'Não foi possível conectar. Tente novamente.'; }
    finally { password.value = ''; button.disabled = false; }
  });
  exit.addEventListener('click', async () => {
    exit.disabled = true;
    try { await call('/sair', { method:'POST', signal:AbortSignal.timeout(5000) }); }
    finally { persist(''); location.reload(); }
  });
  retry.addEventListener('click', check);
  check();
})();
