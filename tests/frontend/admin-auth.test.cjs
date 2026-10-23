const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup(responses=[200]) {
  const nodes=new Map(),calls=[];let restored=0;
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',hidden:true,open:false,
    addEventListener(event,fn){this[event]=fn;},reportValidity:()=>true,focus(){},
    showModal(){this.open=true;},close(){this.open=false;}});return nodes.get(id);};
  const scope={window:{},document:{getElementById:node,activeElement:{focus(){restored++;}}},DOMException,
    fetch:async(url,init)=>{calls.push({url,init});return {status:responses.shift()??200};}};
  vm.createContext(scope);vm.runInContext(fs.readFileSync('assets/js/admin-auth.js','utf8'),scope);
  function submit(value='test-key'){node('adminAccess').value=value;node('adminAuthConfirm').click();}
  return {scope,node,calls,submit,restored:()=>restored};
}
test('senha é solicitada em diálogo antes da requisição e reutilizada só em memória',async()=>{
  const {scope,node,calls,submit,restored}=setup();const request=scope.window.adminFetch('/protected');
  assert.equal(node('adminAuthDialog').open,true);assert.equal(calls.length,0);submit();await request;
  assert.equal(calls[0].init.headers.Authorization,'Bearer test-key');assert.equal(node('adminAccess').value,'');assert.equal(restored(),1);
  await scope.window.adminFetch('/again');assert.equal(calls.length,2);assert.equal(node('adminAuthDialog').open,false);
});
test('cancelar e trocar empresa impedem envio da ação pendente',async()=>{
  for(const cancel of ['adminAuthCancel','reset']){
    const {scope,node,calls}=setup();const request=scope.window.adminFetch('/protected');
    const rejected=assert.rejects(request,{name:'AbortError'});
    if(cancel==='reset')scope.window.clearAdminAccess();else node(cancel).click();
    await rejected;assert.equal(calls.length,0);assert.equal(node('adminAuthDialog').open,false);
  }
});
test('senha recusada abre novamente o diálogo com mensagem de erro',async()=>{
  const {scope,node,calls,submit}=setup([401,200]);const request=scope.window.adminFetch('/protected');
  submit('wrong');await tick();assert.equal(node('adminAuthDialog').open,true);assert.equal(node('adminAuthError').hidden,false);
  submit('correct');await request;assert.equal(calls[1].init.headers.Authorization,'Bearer correct');
});
test('mudança de escopo enquanto pede a senha impede a requisição',async()=>{
  const {scope,calls,submit}=setup();let current=true;const request=scope.window.adminFetch('/old-company',{},()=>current);
  const rejected=assert.rejects(request,{name:'AbortError'});current=false;submit();await rejected;assert.equal(calls.length,0);
});

test('Enter confirma o acesso, mas não interfere na composição de texto',async()=>{
  const {scope,node,calls}=setup();const request=scope.window.adminFetch('/protected');
  node('adminAccess').value='test-key';
  node('adminAccess').keydown({key:'Enter',isComposing:true,preventDefault(){}});
  assert.equal(calls.length,0);assert.equal(node('adminAuthDialog').open,true);
  node('adminAccess').keydown({key:'Enter',isComposing:false,preventDefault(){}});
  await request;assert.equal(calls.length,1);
});

test('cadastro usa o mesmo diálogo e o campo não pede geração de senha',()=>{
  const html=fs.readFileSync('index.html','utf8');
  const field=html.match(/<input id="adminAccess"[^>]+>/)[0];
  assert.match(field,/type="password"/);assert.match(field,/autocomplete="off"/);
  assert.doesNotMatch(field,/name=|new-password/);
  const modal=html.slice(html.indexOf('<dialog id="adminAuthDialog"'),html.indexOf('</dialog>',html.indexOf('<dialog id="adminAuthDialog"')));
  assert.doesNotMatch(modal,/<form|type="submit"/);
  assert.doesNotMatch(html,/companyCreateKey/);
  const workspace=fs.readFileSync('assets/js/workspace-ui.js','utf8');
  assert.match(workspace,/window\.adminFetch\(`\$\{API\(\)\}\/api\/v1\/companies/);
});
