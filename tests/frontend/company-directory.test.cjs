const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync('assets/js/company-directory.js','utf8'),context);
const select=(items,options)=>Array.from(context.RazyncDirectory.select(items,options),company=>company.codigo);
const companies=[
  {codigo:1000,nome:'Árvore Comércio',regime:'LUCRO REAL',capabilities:{tools:[],banks:{}}},
  {codigo:285,nome:'L. Carlos',regime:'SIMPLES NACIONAL',capabilities:{tools:['modelo_dominio'],banks:{itau:'1'}}},
  {codigo:242,nome:'Eletro Forte',regime:'LUCRO REAL',capabilities:{tools:['modelo_dominio'],banks:{itau:'2',sicredi:'3'}}},
  {codigo:47,nome:'CRJ Seguros',regime:'LUCRO PRESUMIDO'},
  {codigo:1242,nome:'Eletro Filial',regime:'LUCRO REAL',capabilities:{tools:[],banks:{}}},
];
test('pesquisa combina palavras em qualquer ordem e ignora acentos e pontuação',()=>{
  assert.deepEqual(select(companies,{query:'COMERCIO arvore'}),[1000]);
  assert.deepEqual(select(companies,{query:'carlos l.'}),[285]);
  assert.deepEqual(select(companies,{query:'real eletro'}),[242,1242]);
});
test('código exato vem antes de correspondências parciais e aceita zeros à esquerda',()=>{
  assert.deepEqual(select([...companies].reverse(),{query:'242'}),[242,1242]);
  assert.deepEqual(select(companies,{query:'0242'}),[242]);
});
test('regime, disponibilidade e múltiplos bancos são filtros combináveis',()=>{
  assert.deepEqual(select(companies,{filter:'organizer'}),[242,285]);
  assert.deepEqual(select(companies,{filter:'catalog'}),[47,1000,1242]);
  assert.deepEqual(select(companies,{filter:'multibank',regime:'LUCRO REAL'}),[242]);
  assert.deepEqual(select(companies,{filter:'organizer',regime:'LUCRO REAL',query:'filial'}),[]);
});
test('ordenação numérica e alfabética não alteram os registros da carteira',()=>{
  const before=JSON.stringify(companies);
  assert.deepEqual(select(companies),[47,242,285,1000,1242]);
  assert.deepEqual(select(companies,{sort:'name'}),[1000,47,1242,242,285]);
  assert.deepEqual(select(companies,{sort:'tools'}),[242,285,47,1000,1242]);
  assert.equal(JSON.stringify(companies),before);
});
test('busca vazia ou sem resultados e carteiras vazias são tratadas',()=>{
  assert.deepEqual(select([],{query:'242'}),[]);
  assert.deepEqual(select(companies,{query:'inexistente'}),[]);
  assert.deepEqual(select(companies,{query:'   '}),[47,242,285,1000,1242]);
});
function directoryUI(blocked=false) {
  const nodes=new Map(),buttons=['all','organizer','multibank','catalog'].map(filter=>({dataset:{filter},classList:{toggle(){}},setAttribute(){},addEventListener(k,v){this[k]=v;}}));
  const views=['cards','list'].map(companyView=>({dataset:{companyView},setAttribute(k,v){this[k]=v;},addEventListener(k,v){this[k]=v;}}));
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:id==='#companySort'?'code':'',dataset:{},hidden:true,addEventListener(k,v){this[k]=v;},focus(){this.focused=true;}});return nodes.get(id);};
  const search=node('#companySearch'),grid=node('#companyGrid'),saved=new Map([['razync:directory-view','list']]);
  const ctx={companies,companyFilter:'all',companyBelongsToPortfolio:c=>c.codigo!==1242,search,grid,
    $:node,$$:selector=>selector==='.company-filter'?buttons:views,
    RazyncDirectory:context.RazyncDirectory,render:items=>{ctx.result=items;},
    localStorage:{getItem:k=>{if(blocked)throw Error();return saved.get(k);},setItem:(k,v)=>{if(blocked)throw Error();saved.set(k,v);}}};
  const app=fs.readFileSync('assets/js/app.js','utf8');vm.createContext(ctx);
  vm.runInContext(app.slice(app.indexOf('function filterCompanies()'),app.indexOf('backButton.addEventListener')),ctx);
  return {ctx,node,search,grid,views};
}
test('busca fica restrita à carteira e limpar pesquisa preserva o filtro de regime',()=>{
  const h=directoryUI();h.node('#regimeFilter').value='LUCRO REAL';h.search.value='eletro';h.search.input();
  assert.deepEqual(Array.from(h.ctx.result,c=>c.codigo),[242]);assert.equal(h.node('#companySearchClear').hidden,false);
  h.node('#companySearchClear').click();assert.equal(h.search.value,'');assert.equal(h.search.focused,true);
  assert.equal(h.node('#regimeFilter').value,'LUCRO REAL');assert.deepEqual(Array.from(h.ctx.result,c=>c.codigo),[242,1000]);
});
test('troca de visualização mantém busca e restaura preferência sem exigir armazenamento',()=>{
  const h=directoryUI();assert.equal(h.grid.dataset.view,'list');h.search.value='eletro';h.views[0].click();
  assert.equal(h.grid.dataset.view,'cards');assert.equal(h.search.value,'eletro');assert.equal(h.views[0]['aria-pressed'],'true');
  const blocked=directoryUI(true);blocked.views[1].click();assert.equal(blocked.grid.dataset.view,'list');
});
