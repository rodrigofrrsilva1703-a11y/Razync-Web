const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/js/site-access.js','utf8');

function fixture({activeSession=false, changePassword=false}={}) {
  const make = () => ({hidden:false, disabled:false, dataset:{}, events:{}, attrs:{}, value:'',
    addEventListener(k,f){this.events[k]=f;}, setAttribute(k,v){this.attrs[k]=v;},
    removeAttribute(k){delete this.attrs[k];}, focus(){this.focused=true;}});
  const ids = Object.fromEntries(['siteAccess','siteAccessForm','siteAccessStatus','siteAccessExit',
    'siteAccessRetry','siteAccessAccount','siteAccessName','siteAccessInitials','siteAccessEmail',
    'siteAccessPassword','siteAccessShow','siteAccessCaps'].map(id=>[id,make()]));
  const submit=make();
  const passwordCalls=[];
  if (changePassword) {
    for (const id of ['siteAccessChangePassword','sitePasswordDialog','sitePasswordForm','sitePasswordCurrent',
      'sitePasswordNew','sitePasswordRepeat','sitePasswordClose','sitePasswordMessage','sitePasswordSubmit','sidebarClose']) ids[id]=make();
    ids.sitePasswordDialog.showModal=()=>{ids.sitePasswordDialog.open=true;};
    ids.sitePasswordForm.querySelector=()=>ids.sitePasswordSubmit;
    ids.sitePasswordForm.reset=()=> {
      for (const id of ['sitePasswordCurrent','sitePasswordNew','sitePasswordRepeat']) ids[id].value='';
    };
    ids.sidebarClose.click=()=>{ids.sidebarClose.clicked=true;};
  }
  ids.siteAccessForm.querySelector=()=>submit;
  ids.siteAccessPassword.type='password';
  ids.siteAccessShow.attrs['aria-pressed']='false';
  const body=make(), storage=new Map();
  let configFails=!activeSession, loginStatus=401, confirmSession;
  const sessionResponse=new Promise(resolve=>{confirmSession=resolve;});
  if(activeSession)storage.set('razync:private-session:v1','synthetic');
  const window={RAZYNC_CONFIG:{apiBase:'https://api.example.test'},addEventListener(){},
    fetch:async (url, options)=>url.endsWith('/alterar-senha')
      ? (passwordCalls.push(options),Response.json({ok:true,sessions_revoked:true}))
      : url.endsWith('/config')
      ? Response.json(configFails?{}:{required:true,available:true},{status:configFails?503:200})
      : url.endsWith('/sessao') ? sessionResponse
        : Response.json(loginStatus===200?{session:'synthetic',email:'user@example.test'}:{},{status:loginStatus})};
  vm.runInNewContext(source,{window,document:{body,querySelector:q=>ids[q.slice(1)],addEventListener(){}},
    sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    URL, URLSearchParams, Headers, AbortSignal, Request, location:{search:'',href:'https://razync.example.test/'},
    clearTimeout(){},setTimeout(){return 1;},setInterval(){return 1;}});
  return {ids,submit,body,storage,window,confirmSession,passwordCalls,allowConfig(){configFails=false;},allowLogin(){loginStatus=200;}};
}

test('login passa por espera, nova tentativa, erro de senha e acesso confirmado', async()=>{
  const h=fixture(), {siteAccess:screen,siteAccessForm:form,siteAccessRetry:retry,
    siteAccessPassword:password,siteAccessShow:show,siteAccessCaps:caps} = h.ids;
  assert.equal(screen.dataset.accessState,'checking');
  assert.equal(h.body.dataset.siteLoading,'');
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(screen.dataset.accessState,'unavailable');
  assert.equal('siteLoading' in h.body.dataset,false);
  assert.equal(form.hidden,true);
  h.allowConfig();
  await retry.events.click();
  assert.equal(screen.dataset.accessState,'ready');
  assert.equal(form.hidden,false);
  password.events.keydown({getModifierState:key=>key==='CapsLock'});
  assert.equal(caps.hidden,false);
  show.events.click();
  assert.equal(password.type,'text');
  password.value='synthetic-wrong-password';
  const pending=form.events.submit({preventDefault(){}});
  assert.equal(screen.dataset.accessState,'submitting');
  assert.equal(h.submit.disabled,true);
  await pending;
  assert.equal(screen.dataset.accessState,'error');
  assert.equal(password.focused,true);
  assert.equal(password.type,'password');
  assert.equal(password.value,'');
  assert.equal(caps.hidden,true);
  h.allowLogin();
  await form.events.submit({preventDefault(){}});
  assert.equal(screen.hidden,true);
  assert.equal(h.window.RazyncSiteAccess.identity(),'user@example.test');
  assert.equal(h.storage.get('razync:private-session:v1'),'synthetic');
});

test('Alterar senha abre o formulário e envia a troca com a sessão ativa', async()=>{
  const h=fixture({activeSession:true,changePassword:true});
  h.confirmSession(Response.json({email:'user@example.test'}));
  await h.window.RazyncSiteAccess.ready;
  const {siteAccessChangePassword:trigger,sitePasswordDialog:dialog,sitePasswordForm:form,
    sitePasswordCurrent:current,sitePasswordNew:next,sitePasswordRepeat:repeat,sitePasswordMessage:message,sidebarClose}=h.ids;
  trigger.events.click();
  assert.equal(sidebarClose.clicked,true);
  assert.equal(dialog.open,true);
  assert.equal(current.focused,true);
  current.value='synthetic-current';
  next.value='synthetic-new';
  repeat.value='different';
  await form.events.submit({preventDefault(){}});
  assert.equal(h.passwordCalls.length,0);
  repeat.value=next.value;
  await form.events.submit({preventDefault(){}});
  assert.equal(h.passwordCalls.length,1);
  assert.equal(h.passwordCalls[0].headers.get('X-Razync-Session'),'synthetic');
  assert.deepEqual(JSON.parse(h.passwordCalls[0].body),{current_password:'synthetic-current',new_password:'synthetic-new'});
  assert.match(message.textContent,/Senha alterada/);
  assert.equal(current.value,'');
});

test('recarregar com sessão ativa mantém a tela de carregamento até iniciar a retomada', async()=>{
  const h=fixture({activeSession:true});
  let loadingDuringHandoff;
  h.window.RazyncWorkspaceResume={beginTransition(){loadingDuringHandoff=h.body.dataset.siteLoading;}};
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.body.dataset.siteLoading,'');
  h.confirmSession(Response.json({email:'user@example.test'}));
  await h.window.RazyncSiteAccess.ready;
  assert.equal(loadingDuringHandoff,'');
  assert.equal(h.ids.siteAccess.hidden,true);
  assert.equal('siteLoading' in h.body.dataset,false);
});
