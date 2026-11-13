const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const app = fs.readFileSync('assets/js/app.js','utf8');
const start = app.indexOf('function setApiConnectionState(');
const end = app.indexOf('initializeTaskUI();', start);
assert.ok(start > 0 && end > start, 'Missing connection indicator logic');
const source = app.slice(start, end);

function setup(request) {
  const listeners = {}, timers = [], attributes = {}, classes = {};
  const label = {textContent:''};
  const indicator = {
    dataset:{}, title:'',
    querySelector:() => label,
    classList:{toggle:(name,value) => {classes[name]=value;}},
    setAttribute:(name,value) => {attributes[name]=value;},
    addEventListener:(name,fn) => {listeners[name]=fn;},
  };
  const context = {
    apiStatus:indicator,API:()=>'/api',companies:[{codigo:242}],
    loadCompanies:()=>{},fetchAfterWake:request,
    setTimeout:(callback) => {timers.push(callback);return timers.length;},
    clearTimeout:()=>{},
    console,
  };
  vm.createContext(context);
  vm.runInContext(source,context);
  return {context,indicator,label,listeners,timers,attributes,classes};
}

test('conexão comunica início, repouso e retorno sem interromper a carteira', async () => {
  let resolve;
  const pending = new Promise(yes => {resolve=yes;});
  const h = setup(() => pending);
  const result = h.context.checkApi();
  assert.equal(h.indicator.dataset.connection,'checking');
  assert.equal(h.attributes['aria-busy'],'true');
  h.timers[0]();
  assert.equal(h.indicator.dataset.connection,'waking');
  assert.match(h.label.textContent,/Iniciando servidor/);
  resolve({ok:true});
  await result;
  assert.equal(h.indicator.dataset.connection,'online');
  assert.equal(h.attributes['aria-busy'],'false');
  assert.equal(h.classes.online,true);
});

test('falha exibe opção de tentar novamente; clique recupera conexão', async () => {
  let success = false, count = 0;
  const h = setup(async () => {
    count++;
    if (!success) throw Error('Railway em repouso');
    return {ok:true};
  });
  await h.context.checkApi();
  assert.equal(h.indicator.dataset.connection,'offline');
  assert.match(h.label.textContent,/tentar/);
  success = true;
  h.listeners.click();
  // A ação de clique inicia o processamento; aguarda a conclusão real,
  // incluindo o callback final de limpeza de solicitação em andamento.
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.indicator.dataset.connection,'online');
  assert.equal(count,2);
});

test('a mesma verificação não dispara solicitações paralelas', async () => {
  let resolve, count = 0;
  const pending = new Promise(yes => {resolve=yes;});
  const h = setup(() => {count++;return pending;});
  const first = h.context.checkApi();
  h.context.checkApi();
  assert.equal(count,1);
  resolve({ok:true});
  await first;
  assert.equal(h.indicator.dataset.connection,'online');
});
