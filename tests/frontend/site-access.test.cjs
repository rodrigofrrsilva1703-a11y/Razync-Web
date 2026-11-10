const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/js/site-access.js','utf8');

function fixture() {
  const make = () => ({hidden:false, disabled:false, dataset:{}, events:{}, attrs:{}, value:'',
    addEventListener(k,f){this.events[k]=f;}, setAttribute(k,v){this.attrs[k]=v;},
    removeAttribute(k){delete this.attrs[k];}, focus(){this.focused=true;}});
  const ids = Object.fromEntries(['siteAccess','siteAccessForm','siteAccessStatus','siteAccessExit',
    'siteAccessRetry','siteAccessAccount','siteAccessName','siteAccessInitials','siteAccessEmail',
    'siteAccessPassword','siteAccessShow','siteAccessCaps'].map(id=>[id,make()]));
  const submit=make();
  ids.siteAccessForm.querySelector=()=>submit;
  ids.siteAccessPassword.type='password';
  ids.siteAccessShow.attrs['aria-pressed']='false';
  const body=make(), storage=new Map();
  let configFails=true, loginStatus=401;
  const window={RAZYNC_CONFIG:{apiBase:'https://api.example.test'},addEventListener(){},
    fetch:async url=>url.endsWith('/config')
      ? Response.json(configFails?{}:{required:true,available:true},{status:configFails?503:200})
      : Response.json(loginStatus===200?{session:'synthetic',email:'user@example.test'}:{},{status:loginStatus})};
  vm.runInNewContext(source,{window,document:{body,querySelector:q=>ids[q.slice(1)],addEventListener(){}},
    sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    URL, URLSearchParams, Headers, AbortSignal, Request, location:{search:'',href:'https://razync.example.test/'},
    clearTimeout(){},setTimeout(){return 1;}});
  return {ids,submit,body,storage,window,allowConfig(){configFails=false;},allowLogin(){loginStatus=200;}};
}

test('login passa por espera, nova tentativa, erro de senha e acesso confirmado', async()=>{
  const h=fixture(), {siteAccess:screen,siteAccessForm:form,siteAccessRetry:retry,
    siteAccessPassword:password,siteAccessShow:show,siteAccessCaps:caps} = h.ids;
  assert.equal(screen.dataset.accessState,'checking');
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(screen.dataset.accessState,'unavailable');
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
