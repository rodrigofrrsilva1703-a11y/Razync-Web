const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const read = name => fs.readFileSync(`assets/js/${name}.js`, 'utf8');

function taskContext(payload) {
  const nodes = new Map();
  const element = () => ({children:[],innerHTML:'',textContent:'',
    querySelectorAll:()=>[], replaceChildren(...children) {this.children=children;},
    appendChild(child) {this.children.push(child);}});
  const node = key => {if (!nodes.has(key)) nodes.set(key,element());return nodes.get(key);};
  const context = {$:node, API:()=>'/api', responseError:async()=>'',
    document:{createElement:element,querySelector:node},
    fetch:async()=>({ok:true,json:async()=>payload})};
  vm.createContext(context);
  vm.runInContext(read('dom-utils')+'\n'+read('tasks-ui'), context);
  return {context,node};
}

test('nomes e títulos de tarefas são exibidos como texto, inclusive atributos com aspas',async()=> {
  const name='<img src=x onerror="alert(1)"> & João';
  const id='" onclick="alert(1)';
  const {context,node}=taskContext({competencia:'2026-10',resumo:{},
    empresas:[{codigo:242,nome:name,regime:'A & B',classe:id,vencimento:'2026-10-20',status:name}],
    manuais:[{id,titulo:name,status:'Pendente'}]});
  await context.loadTasks();
  for (const selector of ['#companyTasks','#manualTasks']) {
    assert.doesNotMatch(node(selector).innerHTML,/<img|onclick="alert/);
    assert.match(node(selector).innerHTML,/&lt;img/);
    assert.match(node(selector).innerHTML,/&quot;/);
    assert.match(node(selector).innerHTML,/João/);
  }
});

test('seletor de empresas preserva código e nome sem interpretar HTML',()=> {
  const {context,node}=taskContext({});
  const name='João & Maria <Filial>';
  context.populateTaskCompanies([{codigo:242,nome:name}]);
  const options=node('#taskCompany').children;
  assert.equal(options.length,2);
  assert.equal(options[0].value,'');
  assert.equal(options[1].value,242);
  assert.equal(options[1].textContent,`242 · ${name}`);
});

test('carregamento inicial busca empresas uma única vez e preenche o seletor de tarefas',async()=> {
  const app=read('app');
  assert.equal((app.match(/^loadCompanies\(\);/gm)||[]).length,1);
  const catalog=[{codigo:242,nome:'Eletro Forte'}];
  let requests=0,rendered=0,populated;
  const context={API:()=>'/api',companies:[],activePortfolio:null,
    fetchAfterWake:async()=>{requests++;return {ok:true,json:async()=>catalog};},
    renderPortfolios:()=>{rendered++;},populateTaskCompanies:items=>{populated=items;}};
  vm.createContext(context);
  vm.runInContext(app.slice(app.indexOf('async function loadCompanies()'),app.indexOf('async function checkApi()')),context);
  await context.loadCompanies();
  assert.equal(requests,1);assert.equal(rendered,1);assert.equal(populated,catalog);
});

test('conciliação extraída mantém entradas, saídas, sinais e tolerância de centavos',()=> {
  const context={};vm.createContext(context);vm.runInContext(read('reconciliation-preview'),context);
  const result=context.reconciliationBalances({'ENTRADAS PLANILHA':100,'ENTRADAS EXTRATO':90,'SAÍDAS PLANILHA':70,'SAÍDAS EXTRATO':80});
  assert.equal(result.entryBalance,10);assert.equal(result.exitBalance,-10);assert.equal(result.ok,false);
  const ledger=context.reconciliationBalances({ENTRADAS_RAZAO:0.3,ENTRADAS_EXTRATO:0.1+0.2,SAIDAS_RAZAO:20,SAIDAS_EXTRATO:20},'razao');
  assert.equal(ledger.ok,true);
});
