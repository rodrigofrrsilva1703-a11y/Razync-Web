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
  const activityKey = 'razync:last-activity', idleLimit = 60 * 60 * 1000;
  let lastActivity = 0, lastSavedActivity = 0, idleTimer, endingSession = false;
  let lastPresence = 0;
  let token = '', identity = '', required = Boolean(base), release;
  const ready = new Promise(resolve => { release = resolve; });
  const stored = () => { try { return sessionStorage.getItem(key) || ''; } catch { return ''; } };
  function persist(value) {
    token = value;
    try {
      if (value) sessionStorage.setItem(key, value);
      else { sessionStorage.removeItem(key); sessionStorage.removeItem(activityKey); }
    } catch {}
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
    delete root.dataset.siteLoading;
    if (token) { checkIdle(); sendPresence(); }
    release();
  }
  function saveActivity() {
    if (!token || !lastActivity) return;
    try { sessionStorage.setItem(activityKey, String(lastActivity)); lastSavedActivity = lastActivity; } catch {}
  }
  async function endIdleSession() {
    if (endingSession || !token) return;
    endingSession = true;
    window.RazyncWorkspaceResume?.save();
    locked('Sua sessão encerrou por inatividade. Entre novamente para continuar.', false);
    try { sessionStorage.setItem(expiredKey, 'idle'); } catch {}
    const signOut = call('/sair', {method:'POST', signal:AbortSignal.timeout(5000)});
    identity = '';
    persist('');
    try { await signOut; } catch {} finally { location.reload(); }
  }
  function checkIdle() {
    clearTimeout(idleTimer);
    if (!token || endingSession) return;
    const remaining = idleLimit - (Date.now() - lastActivity);
    if (remaining <= 0) { void endIdleSession(); return; }
    idleTimer = setTimeout(checkIdle, remaining);
  }
  function recordActivity(event) {
    if (!event.isTrusted || !identity || !token || endingSession) return;
    const now = Date.now();
    if (now - lastActivity >= idleLimit) { void endIdleSession(); return; }
    lastActivity = now;
    sendPresence();
    if (now - lastSavedActivity >= 5000) saveActivity();
  }
  function sendPresence() {
    const now = Date.now();
    if (!identity || !token || endingSession || document.hidden ||
        now - lastActivity > 60000 || now - lastPresence < 30000) return;
    lastPresence = now;
    call("/presenca", {method:"POST", signal:AbortSignal.timeout(5000)}).catch(() => {});
  }
  setInterval(sendPresence, 30000);
  for (const type of ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart']) {
    document.addEventListener(type, recordActivity, {capture:true, passive:true});
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden && identity) { checkIdle(); sendPresence(); } });
  window.addEventListener('pagehide', saveActivity);
  function locked(message, canLogin) {
    account.hidden = true;
    root.dataset.siteLocked = '';
    screen.hidden = false;
    screen.dataset.accessState = canLogin ? (message ? 'notice' : 'ready') : 'unavailable';
    form.hidden = !canLogin;
    retry.hidden = canLogin;
    status.textContent = message;
    delete root.dataset.siteLoading;
    window.RazyncWorkspaceResume?.endTransition();
  }
  async function check() {
    if (!base) { required = false; unlocked(); return; }
    root.dataset.siteLoading = '';
    retry.disabled = true;
    retry.hidden = true;
    screen.dataset.accessState = 'checking';
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
      let ended = '';
      try {
        ended = sessionStorage.getItem(expiredKey) || '';
        lastActivity = Number(sessionStorage.getItem(activityKey)) || Date.now();
      } catch { lastActivity = Date.now(); }
      const expired = Boolean(token) || Boolean(ended);
      if (token) {
        if (Date.now() - lastActivity >= idleLimit) { await endIdleSession(); return; }
        saveActivity();
        const response = await call('/sessao', { signal:AbortSignal.timeout(10000) });
        if (response.ok) {
          const data = await response.json();
          unlocked(data.email);
          return;
        }
        if (response.status !== 401) throw Error();
        persist('');
      }
      locked(ended === 'idle' ? 'Sua sessão encerrou por inatividade. Entre novamente para continuar.'
        : expired ? 'Sua sessão encerrou. Entre novamente para continuar.' : '', true);
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
  const caps = document.querySelector('#siteAccessCaps');
  const updateCaps = event => { caps.hidden = !event.getModifierState?.('CapsLock'); };
  password.addEventListener('keydown', updateCaps);
  password.addEventListener('keyup', updateCaps);
  password.addEventListener('blur', () => { caps.hidden = true; });
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
    screen.dataset.accessState = 'submitting';
    status.textContent = 'Validando acesso…';
    let invalidCredentials = false;
    try {
      const response = await call('/entrar', { method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ email:email.value, password:password.value }), signal:AbortSignal.timeout(20000) });
      const data = await response.json();
      if (!response.ok || typeof data.session !== 'string') {
        invalidCredentials = response.status === 401;
        screen.dataset.accessState = 'error';
        status.textContent = response.status === 401 ? 'E-mail ou senha inválidos.' : response.status === 429 ? 'Muitas tentativas. Aguarde um minuto e tente novamente.' : 'Não foi possível entrar agora. Tente novamente.';
        return;
      }
      persist(data.session);
      lastActivity = Date.now();
      saveActivity();
      unlocked(data.email);
    } catch { screen.dataset.accessState = 'error'; status.textContent = 'Não foi possível conectar. Tente novamente.'; }
    finally {
      password.value = ''; caps.hidden = true; setPasswordVisible(false);
      button.disabled = false; button.removeAttribute('aria-busy');
      if (invalidCredentials) password.focus();
    }
  });
  const changePassword = document.querySelector('#siteAccessChangePassword');
  if (changePassword) {
    const dialog = document.querySelector('#sitePasswordDialog');
    const passwordForm = document.querySelector('#sitePasswordForm');
    const current = document.querySelector('#sitePasswordCurrent');
    const next = document.querySelector('#sitePasswordNew');
    const repeat = document.querySelector('#sitePasswordRepeat');
    const close = document.querySelector('#sitePasswordClose');
    const message = document.querySelector('#sitePasswordMessage');
    const submit = passwordForm.querySelector('[type=submit]');
    let saving = false;

    changePassword.addEventListener('click', () => {
      document.querySelector('#sidebarClose')?.click();
      passwordForm.reset();
      message.textContent = '';
      submit.disabled = false;
      dialog.showModal();
      current.focus();
    });
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
    dialog.addEventListener('close', () => passwordForm.reset());
    passwordForm.addEventListener('submit', async event => {
      event.preventDefault();
      if (saving || submit.disabled) return;
      if (next.value !== repeat.value) {
        message.textContent = 'A confirmação precisa ser igual à nova senha.';
        repeat.focus();
        return;
      }
      saving = submit.disabled = close.disabled = true;
      message.textContent = 'Salvando nova senha…';
      let changed = false;
      try {
        const response = await call('/alterar-senha', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({current_password:current.value, new_password:next.value}),
          signal:AbortSignal.timeout(25000)
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          message.textContent = response.status === 404 ? 'A alteração de senha está indisponível no momento.' : data.detail || 'Não foi possível alterar a senha.';
          return;
        }
        changed = true;
        message.textContent = data.sessions_revoked
          ? 'Senha alterada. As outras sessões foram encerradas.'
          : 'Senha alterada. Não foi possível encerrar as outras sessões.';
      } catch {
        message.textContent = 'A conexão foi interrompida antes de confirmar a troca.';
      } finally {
        passwordForm.reset();
        saving = close.disabled = false;
        submit.disabled = changed;
      }
    });
  }
  exit.addEventListener('click', async () => {
    exit.disabled = true;
    try { await call('/sair', { method:'POST', signal:AbortSignal.timeout(5000) }); }
    finally { identity = ''; persist(''); await window.RazyncWorkspaceResume?.clear(); location.reload(); }
  });
  retry.addEventListener('click', check);
  check();
})();
