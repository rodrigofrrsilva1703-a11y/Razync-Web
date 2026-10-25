const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const app=fs.readFileSync('assets/js/app.js','utf8');
const source=app.slice(app.indexOf('async function loadCompanies()'),app.indexOf('async function checkApi()'));
const original=[{codigo:242,nome:'Eletro Forte',capabilities:{tools:['organizar']}}];
function setup(cached) {
  let resolve, reject;
  const pending=new Promise((yes,no)=>{resolve=yes;reject=no;});
  const stored=new Map([['razync:companies:v1:/api',cached]]);
  const renders=[];
  const context={companies:[],activePortfolio:null,API:()=>'/api',
    localStorage:{getItem:key=>stored.get(key),setItem:(key,value)=>stored.set(key,value)},
    fetchAfterWake:()=>pending,fetch:()=>{throw Error('fallback inesperado');},
    renderPortfolios:()=>renders.push(context.companies),populateTaskCompanies:()=>{},filterCompanies:()=>{}};
  vm.createContext(context);vm.runInContext(source,context);
  return {context,resolve,reject,stored,renders};
}
test('carteira usa cache completo antes de a API responder e atualiza em segundo plano',async()=>{
  const h=setup(JSON.stringify(original));const done=h.context.loadCompanies();
  assert.equal(h.renders.length,1);assert.equal(h.context.companies[0].capabilities.tools[0],'organizar');
  const updated=[...original,{codigo:999,nome:'Nova empresa'}];
  h.resolve({ok:true,json:async()=>updated});await done;
  assert.equal(h.context.companies.length,2);assert.deepEqual(JSON.parse(h.stored.get('razync:companies:v1:/api')),updated);
});
test('resposta idêntica não reconstrói carteira nem interrompe seleção',async()=>{
  const h=setup(JSON.stringify(original));const done=h.context.loadCompanies();
  h.resolve({ok:true,json:async()=>original});await done;assert.equal(h.renders.length,1);
});
test('falha do servidor mantém catálogo e ferramentas já carregados',async()=>{
  const h=setup(JSON.stringify(original));const done=h.context.loadCompanies();
  h.reject(Error('offline'));await done;assert.equal(h.context.companies[0].codigo,242);
});
test('cache corrompido não impede atualização e armazenamento bloqueado é opcional',async()=>{
  const h=setup('{quebrado');h.context.localStorage.setItem=()=>{throw Error('quota');};
  const done=h.context.loadCompanies();assert.equal(h.renders.length,0);
  h.resolve({ok:true,json:async()=>original});await done;assert.equal(h.renders.length,1);
});
test('atualização do servidor remove empresas excluídas do cache',async()=>{
  const h=setup(JSON.stringify([...original,{codigo:999,nome:'Removida'}]));const done=h.context.loadCompanies();
  h.resolve({ok:true,json:async()=>original});await done;assert.equal(h.context.companies.length,1);
});
