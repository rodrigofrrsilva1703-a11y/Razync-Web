const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../assets/js/fiscal-242.js'), 'utf8');

test('loading usa somente contagens recebidas e preserva espera, parcial e cancelamento', () => {
  const element = () => ({textContent:'',hidden:true,dataset:{},style:{},attrs:{},
    classList:{toggle(){}},setAttribute(key,value){this.attrs[key]=value;},removeAttribute(key){delete this.attrs[key];}});
  const elements = new Map();
  const byId = id => {if (!elements.has(id)) elements.set(id,element());return elements.get(id);};
  const loadingPanel = element(), loadingMeter = element(), icon = element();
  const stages = [element(),element(),element()];
  loadingPanel.querySelectorAll = () => stages;
  loadingPanel.querySelector = () => icon;
  const context = {byId,loadingPanel,loadingMeter,loadingCounts:{done:0,total:0}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function showAIProgress('), source.indexOf('  function usageTime(')),context);
  context.showAIProgress('preparing',0,0);
  assert.equal(loadingMeter.attrs['aria-valuenow'],undefined);
  assert.equal(byId('fiscal242LoadingFill').style.width,'');
  assert.equal(loadingPanel.attrs['aria-busy'],'true');
  context.showAIProgress('analyzing',2,5);
  assert.equal(byId('fiscal242LoadingFill').style.width,'40%');
  assert.equal(loadingMeter.attrs['aria-valuenow'],'2');
  context.showAIProgress('waiting',2,5,'Aguardando cota.');
  assert.equal(byId('fiscal242LoadingCaption').textContent,'Aguardando cota.');
  assert.equal(byId('fiscal242LoadingFill').style.width,'40%');
  context.showAIProgress('partial',2,5);
  assert.equal(loadingPanel.attrs['aria-busy'],'false');
  assert.equal(byId('fiscal242LoadingCount').textContent,'2 de 5 grupos concluídos');
  context.showAIProgress('cancelled');
  assert.equal(loadingPanel.dataset.phase,'cancelled');
  assert.equal(loadingMeter.attrs['aria-valuenow'],'2');
  context.showAIProgress('complete',5,5);
  assert.equal(byId('fiscal242LoadingFill').style.width,'100%');
  assert.equal(icon.textContent,'✓');
});

test('ordenação compara códigos numericamente e diferenças pelo tamanho sem alterar dados', () => {
  const context = {};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function sortFiscalRows('), source.indexOf('  const sortButtons =')),context);
  const rows = [{conta:'10',fiscal:5,diferenca:-500},{conta:'2',fiscal:100,diferenca:10},{conta:'20',fiscal:50,diferenca:0}];
  assert.deepEqual(Array.from(context.sortFiscalRows(rows,'conta',false),x=>x.conta),['2','10','20']);
  assert.deepEqual(Array.from(context.sortFiscalRows(rows,'diferenca',true),x=>x.conta),['10','2','20']);
  assert.deepEqual(Array.from(context.sortFiscalRows(rows,'fiscal',true),x=>x.conta),['2','20','10']);
  assert.deepEqual(rows.map(x=>x.conta),['10','2','20']);
  assert.equal(rows[0].diferenca,-500);
});

test('leitor da IA preserva seleção em lotes novos e escolhe conta visível ao filtrar', () => {
  const context = {keyOf:row=>row.conta+':'+row.tipo};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function chooseAIKey('),source.indexOf('  function renderAIReader(')),context);
  const cards = [{item:{conta:'366',tipo:'ENTRADAS'}},{item:{conta:'354',tipo:'ENTRADAS'}}];
  assert.equal(context.chooseAIKey(cards,'354:ENTRADAS'),'354:ENTRADAS');
  assert.equal(context.chooseAIKey(cards.slice(0,1),'354:ENTRADAS'),'366:ENTRADAS');
  assert.equal(context.chooseAIKey([], '366:ENTRADAS'),'');
  assert.equal(context.chooseAIKey(cards,''),'366:ENTRADAS');
});
