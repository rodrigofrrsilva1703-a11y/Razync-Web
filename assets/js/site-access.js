(() => {
  const root = document.body, screen = document.querySelector('#siteAccess');
  const form = document.querySelector('#siteAccessForm'), status = document.querySelector('#siteAccessStatus');
  const exit = document.querySelector('#siteAccessExit'), retry = document.querySelector('#siteAccessRetry');
  const account = document.querySelector('#siteAccessAccount');
  const accountName = document.querySelector('#siteAccessName');
  const accountInitials = document.querySelector('#siteAccessInitials');
  const base = (window.RAZYNC_CONFIG?.apiBase || '').replace(/\/$/, '');
  const original = window.fetch.bind(window), prefix = '/api/v1/acesso';
  const key = 'razync:private-session:v1', expiredKey = 'razync:session-ended';
  let token = '', identity = '', required = Boolean(base), release;
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
  function unlocked(email) {
    try { sessionStorage.removeItem(expiredKey); } catch {}
    identity = typeof email === 'string' ? email : '';
    const words = typeof email === 'string'
      ? email.split('@', 1)[0].match(/\p{L}[\p{L}\p{M}]*/gu) || []
      : [];
    const name = words.map(word => word[0].toLocaleUpperCase('pt-BR') + word.slice(1)).join(' ') || 'Minha conta';
    accountName.textContent = name;
    accountName.title = name;
    accountInitials.textContent = words.slice(0, 2).map(word => word[0].toLocaleUpperCase('pt-BR')).join('') || 'RZ';
    account.hidden = !required;
    if (identity) window.RazyncWorkspaceResume?.beginTransition();
    delete root.dataset.siteLocked;
    screen.hidden = true;
    release();
  }
  function locked(message, canLogin) {
    account.hidden = true;
    root.dataset.siteLocked = '';
    screen.hidden = false;
    form.hidden = !canLogin;
    retry.hidden = canLogin;
    status.textContent = message;
    window.RazyncWorkspaceResume?.endTransition();
  }
  async function check() {
    if (!base) { required = false; unlocked(); return; }
    retry.disabled = true;
    try {
      const response = await call('/config', { signal:AbortSignal.timeout(20000) });
      // A publicação da interface pode terminar antes da nova versão da API.
      // A API protegida sempre fornece este endpoint; a ausência só atende a versão anterior.
      if (response.status === 404) { required = false; unlocked(); return; }
      if (!response.ok) throw Error();
      const config = await response.json();
      if (typeof config.required !== 'boolean') throw Error();
      const testing = config.available === true && new URLSearchParams(location.search).get('testar-login') === '1';
      if (!config.required && !testing) { required = false; unlocked(); return; }
      required = true;
      persist(stored());
      let expired = Boolean(token);
      try { expired ||= sessionStorage.getItem(expiredKey) === '1'; } catch {}
      if (token) {
        const response = await call('/sessao', { signal:AbortSignal.timeout(10000) });
        if (response.ok) {
          const data = await response.json();
          unlocked(data.email);
          return;
        }
        if (response.status !== 401) throw Error();
        persist('');
      }
      locked(expired ? 'Sua sessão encerrou. Entre novamente para continuar.' : '', true);
    } catch {
      locked('Não foi possível verificar o acesso. Tente novamente.', false);
    } finally { retry.disabled = false; }
  }
  window.RazyncSiteAccess = { isPrivate: () => required, identity: () => identity, ready };
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
      window.RazyncWorkspaceResume?.save();
      try { sessionStorage.setItem(expiredKey, '1'); } catch {}
      persist('');
      location.reload();
    }
    return response;
  };
  const password = document.querySelector('#siteAccessPassword');
  const showPassword = document.querySelector('#siteAccessShow');
  function setPasswordVisible(visible) {
    password.type = visible ? 'text' : 'password';
    showPassword.setAttribute('aria-pressed', String(visible));
    showPassword.setAttribute('aria-label', visible ? 'Ocultar senha' : 'Mostrar senha');
  }
  showPassword.addEventListener('click', () => setPasswordVisible(password.type === 'password'));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const email = document.querySelector('#siteAccessEmail');
    const button = form.querySelector('button[type=submit]');
    if (button.disabled) return;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    status.textContent = 'Validando acesso…';
    try {
      const response = await call('/entrar', { method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ email:email.value, password:password.value }), signal:AbortSignal.timeout(20000) });
      const data = await response.json();
      if (!response.ok || typeof data.session !== 'string') {
        status.textContent = response.status === 401 ? 'E-mail ou senha inválidos.' : response.status === 429 ? 'Muitas tentativas. Aguarde um minuto e tente novamente.' : 'Não foi possível entrar agora. Tente novamente.';
        return;
      }
      persist(data.session);
      unlocked(data.email);
    } catch { status.textContent = 'Não foi possível conectar. Tente novamente.'; }
    finally { password.value = ''; setPasswordVisible(false); button.disabled = false; button.removeAttribute('aria-busy'); }
  });
  exit.addEventListener('click', async () => {
    exit.disabled = true;
    try { await call('/sair', { method:'POST', signal:AbortSignal.timeout(5000) }); }
    finally { identity = ''; persist(''); await window.RazyncWorkspaceResume?.clear(); location.reload(); }
  });
  retry.addEventListener('click', check);
  check();
})();
