const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/fiscal-242.js','utf8');
function setup(){
  class Element {
    constructor(tag,cls='',text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.events={};this.attributes={};}
    append(...items){this.children.push(...items);} appendChild(item){this.children.push(item);return item;}
    replaceChildren(...items){this.children=[...items];}
    setAttribute(k,v){this.attributes[k]=v;}
    addEventListener(k,fn){this.events[k]=fn;}
    async click(){await this.events.click?.();}
  }
  class Form {constructor(){this.values=[];}append(k,v){this.values.push([k,v]);}entries(){return this.values[Symbol.iterator]();}get(k){return this.values.find(e=>e[0]===k)?.[1];}}
  const node=(...args)=>new Element(...args),files={fiscal242Entradas:{files:['entradas.xls']},fiscal242Saidas:{files:['saidas.xls']}};
  const previewBody=new Form();previewBody.append('acumuladores','resumo.xls');previewBody.append('razao','razao.xls');previewBody.append('filial','242');
  const requests=[];
  const context={node,FormData:Form,AbortController,previewBody,byId:id=>files[id],API:()=>'/api',responseError:async()=> 'Indisponível',
    aiSourceLabel:()=> 'Groq · gratuito',renderAIConsidered:()=>null,renderAIExcluded:()=>null,renderAIDocumentary:()=>null,renderAICases:()=>null,renderAILimits:()=>null,
    fetch:async(url,options)=>{requests.push({url,options});const body=options.body;return {ok:true,json:async()=>({
      escopo:{conta:body.get('conta'),tipo:body.get('tipo'),origem:body.get('origem'),acumulador:body.get('acumulador')},
      analises:[{conta:body.get('conta'),tipo:body.get('tipo'),parecer:{resumo_executivo:{conclusao:'Confira o documento original'},leitura_comparacao:{orientacoes:[{acao:'Compare a nota',objetivo:'Confirme a origem'}]}}}]})};}};
  vm.createContext(context);vm.runInContext(source.slice(source.indexOf('  const accountAnalysisCache ='),source.indexOf('  function fiscalAccountSituation(')),context);
  const all=root=>[root,...root.children.flatMap(all)];const find=(root,cls)=>all(root).find(el=>el.className===cls);
  return {context,requests,files,find,all};
}

test('somente clique envia a seleção e reabrir o parecer não repete a chamada',async()=>{
  const {context,requests,find,all}=setup();const scope={origem:'resumo',conta:'470',tipo:'ENTRADAS'};
  let root=context.createAccountAnalysis(scope);
  assert.equal(requests.length,0);
  await find(root,'fiscal-account-analysis-button').click();
  assert.equal(requests.length,1);
  assert.equal(requests[0].options.body.get('conta'),'470');assert.equal(requests[0].options.body.get('tipo'),'ENTRADAS');
  assert.equal(requests[0].options.body.get('entradas'),undefined);
  assert.ok(all(root).some(el=>el.textContent==='Conclusão desta seleção'));
  root=context.createAccountAnalysis(scope);await find(root,'fiscal-account-analysis-button').click();await find(root,'fiscal-account-analysis-button').click();
  assert.equal(requests.length,1);
});

test('recorte documental envia apenas o acompanhamento do tipo e preserva o acumulador',async()=>{
  const {context,requests,find}=setup();
  const root=context.createAccountAnalysis({origem:'documentos',conta:'470',tipo:'ENTRADAS',acumulador:'1403'});
  await find(root,'fiscal-account-analysis-button').click();const body=requests[0].options.body;
  assert.equal(body.get('acumulador'),'1403');assert.equal(body.get('entradas'),'entradas.xls');assert.equal(body.get('saidas'),undefined);
  const other=context.createAccountAnalysis({origem:'resumo',conta:'470',tipo:'SAÍDAS'});
  await find(other,'fiscal-account-analysis-button').click();assert.equal(requests.length,2);
});

test('trocar arquivos invalida cache e resposta de outra conta nunca aparece',async()=>{
  const {context,requests,files,find}=setup();const scope={origem:'documentos',conta:'470',tipo:'ENTRADAS'};
  let root=context.createAccountAnalysis(scope);await find(root,'fiscal-account-analysis-button').click();
  files.fiscal242Entradas.files=['nova.xls'];root=context.createAccountAnalysis(scope);await find(root,'fiscal-account-analysis-button').click();
  assert.equal(requests.length,2);
  context.resetAccountAnalyses();
  context.fetch=async()=>({ok:true,json:async()=>({escopo:{...scope,acumulador:''},analises:[{conta:'312',tipo:'ENTRADAS'}]})});
  root=context.createAccountAnalysis(scope);await find(root,'fiscal-account-analysis-button').click();
  assert.match(find(root,'fiscal-account-analysis-status').textContent,/não corresponde/);
  assert.equal(find(root,'fiscal-account-analysis-body').hidden,true);
});
