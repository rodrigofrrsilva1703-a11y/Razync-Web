const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/fiscal-242.js','utf8');

test('parecer local tem identificação própria e não exibe modelo de IA',()=>{
  const context={};vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function aiSourceLabel('),source.indexOf('  function responsePoints(')),context);
  assert.equal(context.aiSourceLabel({provedor:'local',modelo_usado:'regras_documentais'}),'Conferência local · sem chamada de IA');
  assert.equal(context.aiSourceLabel({provedor:'gemini',modelo_usado:'flash-lite'}),'Gemini · flash-lite');
});
test('a IA principal inclui os anexos e reaproveita a mesma requisição até mudar as fontes',()=>{
  class Body {constructor(){this.values=[];}append(...pair){this.values.push(pair);}entries(){return this.values.values();}}
  const base=new Body();base.append('acumuladores','fiscal');base.append('razao','razao');base.append('filial','242');
  const files={fiscal242Entradas:{files:['entradas']},fiscal242Saidas:{files:[]}};
  const context={FormData:Body,previewBody:base,aiInputBody:null,byId:id=>files[id]};
  vm.createContext(context);vm.runInContext(source.slice(source.indexOf('  function selectedAIRequest()'),source.indexOf('  aiButton.addEventListener("click", async () =>')),context);
  const first=context.selectedAIRequest();assert.equal(context.selectedAIRequest(),first);
  assert.deepEqual(first.values.find(p=>p[0]==='entradas'),['entradas','entradas']);
  assert.equal(first.values.some(p=>p[0]==='saidas'),false);
  files.fiscal242Saidas.files=['saidas'];context.aiInputBody=null;
  const second=context.selectedAIRequest();assert.notEqual(second,first);
  assert.deepEqual(second.values.find(p=>p[0]==='saidas'),['saidas','saidas']);
});
test('existe uma única área de IA e o atalho documental foi removido',()=>{
  const html=fs.readFileSync('index.html','utf8');
  assert.doesNotMatch(html,/id="fiscal242InvestigarIA/);
  assert.doesNotMatch(source,/fiscal242InvestigarIA/);
  assert.match(html,/id="fiscal242AISources"/);
});
test('nenhuma pendência termina localmente e não solicita lotes de IA',async()=>{
  let state=null;const urls=[];
  const context={Date,AbortController,DOMException,setTimeout,clearTimeout,API:()=>'/api',
    fetch:async(url)=>{urls.push(url);return{ok:true,status:200,json:async()=>({sessao:'empty',grupos:0,registros:0,lotes:[],apoio_documental:{conciliados:10}})};}};
  vm.createContext(context);vm.runInContext(source.slice(source.indexOf('  function waitForAIQuota('),source.indexOf('  const aiCancelButton =')),context);
  const result=await context.analyzeInBatches({},new AbortController(),()=>{}, {get:()=>state,set:v=>state=v,discard:()=>state=null,endpoint:'/ia/sessoes'});
  assert.equal(urls.length,1);assert.equal(result.provedor,'local');assert.equal(result.apoio_documental.conciliados,10);
  assert.match(result.aviso,/sem consumir tokens/);assert.equal(state,null);
});
