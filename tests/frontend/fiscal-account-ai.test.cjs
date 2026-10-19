const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/fiscal-242.js','utf8');
function setup(){
  class Element {
    constructor(tag,cls='',text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.events={};this.attributes={};}
    append(...items){items.forEach(item=>this.appendChild(item));}
    appendChild(item){item.remove();this.children.push(item);item.parentElement=this;return item;}
    replaceChildren(...items){this.children.slice().forEach(item=>item.remove());this.append(...items);}
    insertBefore(item,before){item.remove();this.children.splice(this.children.indexOf(before),0,item);item.parentElement=this;}
    remove(){if(this.parentElement){const parent=this.parentElement;parent.children.splice(parent.children.indexOf(this),1);this.parentElement=null;}}
    setAttribute(k,v){this.attributes[k]=v;}
    addEventListener(k,fn){this.events[k]=fn;}
    focus(options){this.focusOptions=options;}
    async click(){await this.events.click?.();}
  }
  class Form {constructor(){this.values=[];}append(k,v){this.values.push([k,v]);}entries(){return this.values[Symbol.iterator]();}get(k){return this.values.find(e=>e[0]===k)?.[1];}}
  const node=(...args)=>new Element(...args),files={fiscal242Entradas:{files:['entradas.xls']},fiscal242Saidas:{files:['saidas.xls']}};
  const previewBody=new Form();previewBody.append('acumuladores','resumo.xls');previewBody.append('razao','razao.xls');previewBody.append('filial','242');
  const requests=[];
  const context={node,FormData:Form,AbortController,Date,setInterval:()=>1,clearInterval:()=>{},previewBody,byId:id=>files[id],API:()=>'/api',responseError:async()=> 'Indisponível',
    aiSourceLabel:()=> 'Groq · gratuito',renderAIConsidered:()=>null,renderAIExcluded:()=>null,renderAIDocumentary:()=>null,renderAICases:()=>null,renderAILimits:()=>null,
    fetch:async(url,options)=>{requests.push({url,options});const body=options.body;return {ok:true,json:async()=>({
      escopo:{conta:body.get('conta'),tipo:body.get('tipo'),origem:body.get('origem'),acumulador:body.get('acumulador')},
      analises:[{conta:body.get('conta'),tipo:body.get('tipo'),parecer:{resumo_executivo:{conclusao:'Confira o documento original'},leitura_comparacao:{orientacoes:[{acao:'Compare a nota',objetivo:'Confirme a origem'}]}}}]})};}};
  vm.createContext(context);vm.runInContext(source.slice(source.indexOf('  const accountAnalysisCache ='),source.indexOf('  function fiscalAccountSituation(')),context);
  const all=root=>[root,...root.children.flatMap(all)];const find=(root,cls)=>all(root).find(el=>el.className===cls);
  return {context,requests,files,find,all,node};
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


test('botão fica no rodapé e parecer ocupa uma vista separada sem novas chamadas ao alternar',async()=>{
  const {context,requests,find,all,node}=setup();
  const scope={origem:'documentos',conta:'470',tipo:'ENTRADAS',acumulador:'1403'};
  const panel=context.createAccountAnalysis(scope);
  const shell=node('div'),header=node('header'),comparison=node('div'),footer=node('footer'),navigation=node('nav');
  shell.append(header,comparison,footer);footer.appendChild(navigation);comparison.scrollTop=275;
  panel.mount({shell,header,comparison,footer,navigation});
  const tabs=find(header,'fiscal-account-analysis-tabs'),button=find(footer,'fiscal-account-analysis-button');
  assert.ok(button);assert.equal(find(comparison,'fiscal-account-analysis-button'),undefined);
  assert.equal(panel.parentElement,shell);assert.equal(panel.hidden,true);assert.equal(comparison.hidden,false);
  await tabs.children[1].click();assert.equal(requests.length,0);assert.equal(panel.hidden,false);assert.equal(comparison.hidden,true);
  await button.click();assert.equal(requests.length,1);assert.equal(tabs.children[1].attributes['aria-selected'],'true');
  const body=find(panel,'fiscal-account-analysis-body'),rendered=body.children[0];
  await tabs.children[0].click();assert.equal(comparison.hidden,false);assert.equal(comparison.scrollTop,275);
  await button.click();assert.equal(requests.length,1);assert.equal(body.children[0],rendered);
  let prevented=false;tabs.events.keydown({key:'Home',preventDefault:()=>{prevented=true;}});
  assert.equal(prevented,true);assert.equal(comparison.hidden,false);assert.equal(tabs.children[0].tabIndex,0);
  panel.destroy();assert.equal(find(footer,'fiscal-account-analysis-button'),undefined);assert.equal(header.children.length,0);
});

test('carregamento usa tempo real, encerra o timer e não muda a vista escolhida ao concluir',async()=>{
  const {context,find,node}=setup();let clock=0,tick,finish,calls=0;const cleared=[];
  context.Date={now:()=>clock};context.setInterval=fn=>{tick=fn;return 123;};context.clearInterval=id=>cleared.push(id);
  context.fetch=()=>{calls++;return new Promise(resolve=>{finish=resolve;});};
  const panel=context.createAccountAnalysis({origem:'resumo',conta:'470',tipo:'ENTRADAS'});
  const shell=node('div'),header=node('header'),comparison=node('div'),footer=node('footer'),navigation=node('nav');
  shell.append(header,comparison,footer);footer.append(navigation);panel.mount({shell,header,comparison,footer,navigation});
  const button=find(footer,'fiscal-account-analysis-button'),pending=button.click();
  const loading=find(panel,'fiscal-account-loading');assert.equal(loading.hidden,false);
  assert.equal(find(panel,'fiscal-account-loading-meter').attributes['aria-valuenow'],undefined);
  clock=65000;tick();assert.equal(find(panel,'fiscal-account-loading-time').textContent,'1 min 5 s');
  await find(header,'fiscal-account-analysis-tabs').children[0].click();assert.equal(comparison.hidden,false);
  finish({ok:true,json:async()=>({escopo:{conta:'470',tipo:'ENTRADAS',origem:'resumo',acumulador:''},analises:[]})});
  await pending;
  assert.equal(loading.hidden,true);assert.ok(cleared.includes(123));assert.equal(comparison.hidden,false);
  await button.click();assert.equal(calls,1);assert.equal(panel.hidden,false);assert.equal(loading.hidden,true);
});
