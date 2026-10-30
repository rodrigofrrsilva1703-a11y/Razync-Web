const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/fiscal-242.js','utf8');
test('folha de estilos fiscal mantém todos os blocos completos na publicação',()=>{
  const css=fs.readFileSync('assets/css/fiscal-account-dialog.css','utf8').replace(/\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g,'');
  let depth=0;for(const char of css){if(char==='{')depth++;if(char==='}')depth--;assert.ok(depth>=0,'Bloco CSS fechado sem abertura');}
  assert.equal(depth,0,'Folha CSS incompleta: bloco sem fechamento');
});
function setup(){
  class Element {
    constructor(tag,cls='',text=''){
      this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.events={};this.attributes={};
      this.classList={
        add:(name)=>{this.className=[...new Set([...this.className.split(' ').filter(Boolean),name])].join(' ');},
        remove:(name)=>{this.className=this.className.split(' ').filter(x=>x!==name).join(' ');},
        toggle:(name,force)=>{
          const has=this.className.split(' ').includes(name), next=force===undefined?!has:Boolean(force);
          next?this.classList.add(name):this.classList.remove(name);return next;
        }
      };
    }
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
      assistente:{disponivel:true,session:'token-para-teste'},
      analises:[{conta:body.get('conta'),tipo:body.get('tipo'),parecer:{resumo_executivo:{conclusao:'Confira o documento original'},leitura_comparacao:{orientacoes:[{acao:'Compare a nota',objetivo:'Confirme a origem'}]}}}]})};}};
  vm.createContext(context);vm.runInContext(source.slice(source.indexOf('  const accountAnalysisCache ='),source.indexOf('  function fiscalAccountSituation(')),context);
  const all=root=>[root,...root.children.flatMap(all)];const find=(root,cls)=>all(root).find(el=>el.className===cls);
  return {context,requests,files,find,all,node};
}

test('assistente envia só token e pergunta, mostra fonte e preserva texto sem HTML',async()=>{
  const {context,all,find}=setup();
  context.setTimeout=()=>1;context.clearTimeout=()=>{};context.money=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});
  const scope={conta:'408',tipo:'SAÍDAS',origem:'documentos',acumulador:''};
  const result={assistente:{disponivel:true,session:'token-temporario'}};
  const state={source:context.previewBody,result};let sent;
  context.fetch=async(url,options)=>{sent={url,body:JSON.parse(options.body)};return {ok:true,json:async()=>({escopo:scope,origem:'local',resumo:{fiscal:100,contabil:110,diferenca:10},explicacao:'<img onerror=evil()>',evidencias:[],proximos_passos:[],ferramenta:'Busca',exibidos:0,encontrados:0})};};
  const root=context.renderFiscalAssistant(result,scope,state);
  all(root).find(e=>e.tag==='textarea').value='Procure a nota 149599';
  await find(root,'fiscal-agent-send').click();
  assert.deepEqual(sent.body,{session:'token-temporario',pergunta:'Procure a nota 149599',usar_ia:false});
  assert.ok(all(root).some(e=>e.textContent==='<img onerror=evil()>'));
  assert.ok(!all(root).some(e=>e.tag==='img'));
  assert.equal(state.agentMessages.length,1);
});

test('somente clique envia a seleção e reabrir o parecer não repete a chamada',async()=>{
  const {context,requests,find,all}=setup();const scope={origem:'resumo',conta:'470',tipo:'ENTRADAS'};
  let root=context.createAccountAnalysis(scope);
  assert.equal(requests.length,0);
  await find(root,'fiscal-account-analysis-button').click();
  assert.equal(requests.length,1);
  assert.equal(requests[0].options.body.get('conta'),'470');assert.equal(requests[0].options.body.get('tipo'),'ENTRADAS');
  assert.equal(requests[0].options.body.get('entradas'),undefined);
  assert.ok(all(root).some(el=>String(el.textContent).includes('Resultado da investigação')));
  assert.ok(all(root).some(el=>el.textContent==='Ver investigação completa'));
  root=context.createAccountAnalysis(scope);await find(root,'fiscal-account-analysis-button').click();await find(root,'fiscal-account-analysis-button').click();
  assert.equal(requests.length,1);
});

test('chat mostra pergunta imediatamente, anima espera e substitui pela resposta sem duplicar mensagem',async()=>{
  const {context,all,find}=setup();let finish;
  context.setTimeout=()=>1;context.clearTimeout=()=>{};context.money=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});
  const scope={conta:'408',tipo:'SAÍDAS',origem:'documentos',acumulador:''};
  const result={assistente:{disponivel:true,session:'token'}},state={source:context.previewBody,result};
  context.fetch=()=>new Promise(resolve=>{finish=resolve;});
  const root=context.renderFiscalAssistant(result,scope,state),input=all(root).find(e=>e.tag==='textarea'),send=find(root,'fiscal-agent-send');
  input.value='Compare a nota 149353';const pending=send.click();
  const thread=find(root,'fiscal-agent-thread');
  assert.equal(thread.children.length,1);
  assert.ok(all(root).some(e=>e.textContent==='Compare a nota 149353'));
  assert.equal(find(root,'fiscal-agent-typing-dots').children.length,3);
  assert.equal(thread.attributes['aria-busy'],'true');assert.equal(send.hidden,true);
  finish({ok:true,json:async()=>({escopo:scope,origem:'local',intencao:'documento',explicacao:'Compare os registros.',ferramenta:'Busca',exibidos:0,encontrados:0})});await pending;
  assert.equal(thread.children.length,1);assert.equal(find(root,'fiscal-agent-typing-dots'),undefined);
  assert.ok(find(root,'fiscal-agent-user'));assert.ok(find(root,'fiscal-agent-answer-content'));
  assert.equal(thread.attributes['aria-busy'],'false');assert.equal(send.hidden,false);
});

test('cancelar espera remove a animação, preserva a pergunta e permite nova tentativa',async()=>{
  const {context,all,find}=setup();context.setTimeout=()=>1;context.clearTimeout=()=>{};
  const result={assistente:{disponivel:true,session:'token'}},state={source:context.previewBody,result};
  context.fetch=(url,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('cancelled'))));
  const root=context.renderFiscalAssistant(result,{conta:'408',tipo:'SAÍDAS'},state),input=all(root).find(e=>e.tag==='textarea'),send=find(root,'fiscal-agent-send');
  input.value='Procure nota 149353';const pending=send.click();await find(root,'fiscal-agent-stop').click();await pending;
  assert.equal(find(root,'fiscal-agent-typing-dots'),undefined);
  assert.ok(find(root,'fiscal-agent-error').textContent.includes('Espera encerrada'));
  assert.equal(find(root,'fiscal-agent-thread').children.length,1);
  assert.equal(input.value,'Procure nota 149353');assert.equal(send.disabled,false);assert.equal(send.hidden,false);
});

test('resposta por nota separa comparação e fatos; ações abrem evidências ou preenchem pergunta sem enviar',async()=>{
  const {context,all,find}=setup();let calls=0;
  context.setTimeout=()=>1;context.clearTimeout=()=>{};context.money=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});
  const scope={conta:'408',tipo:'SAÍDAS',origem:'documentos',acumulador:''};
  const result={assistente:{disponivel:true,session:'token'}};const state={source:context.previewBody,result};
  context.fetch=async()=>{calls++;return{ok:true,json:async()=>({escopo:scope,origem:'local',intencao:'documento',titulo:'Diferença no documento',recorte:'Nota 149353',
    explicacao:'O Razão está abaixo do fiscal.',resumo:{fiscal:900000,contabil:999999,diferenca:99999},
    comparacao:{rotulo:'Nota 149353',fiscal:1095,contabil:915,diferenca:-180},fatos:['S-365 e R-657'],
    proximos_passos:['Compare as parcelas.'],pontos_confirmar:['Causa não comprovada.'],
    evidencias:[{referencia:'R-657',origem:'Razão',conta:'408',nota:'149353',data:'05/08/2026',valor:915,historico:'<img onerror=evil()>'}],
    acoes:[{tipo:'evidencias',rotulo:'Ver lançamentos'},{tipo:'pergunta',rotulo:'Pesquisar em outras contas',pergunta:'Procure a nota 149353 em outras contas'}],
    ferramenta:'Busca',exibidos:1,encontrados:1})};};
  const root=context.renderFiscalAssistant(result,scope,state),input=all(root).find(e=>e.tag==='textarea');
  input.value='Compare a nota 149353';await find(root,'fiscal-agent-send').click();
  assert.ok(find(root,'fiscal-agent-comparison'));
  assert.equal(find(root,'fiscal-agent-totals'),undefined);
  assert.ok(all(root).some(e=>e.textContent==='A confirmar'));
  assert.ok(!all(root).some(e=>e.tag==='img'));
  await all(root).find(e=>e.tag==='button'&&e.textContent==='Ver lançamentos').click();
  assert.equal(find(root,'fiscal-agent-records').open,true);
  await all(root).find(e=>e.tag==='button'&&e.textContent==='Pesquisar em outras contas').click();
  assert.equal(input.value,'Procure a nota 149353 em outras contas');assert.equal(calls,1);
});

test('recorte documental envia apenas o acompanhamento do tipo e preserva o acumulador',async()=>{
  const {context,requests,find}=setup();
  const root=context.createAccountAnalysis({origem:'documentos',conta:'470',tipo:'ENTRADAS',acumulador:'1403'});
  await find(root,'fiscal-account-analysis-button').click();const body=requests[0].options.body;
  assert.equal(body.get('acumulador'),'1403');assert.equal(body.get('entradas'),'entradas.xls');assert.equal(body.get('saidas'),undefined);
  const other=context.createAccountAnalysis({origem:'resumo',conta:'470',tipo:'SAÍDAS'});
  await find(other,'fiscal-account-analysis-button').click();assert.equal(requests.length,2);
});

test('investigação permite desligar IA e invalida cache quando um arquivo auxiliar muda',async()=>{
  const {context,requests,files,find,all}=setup();
  const scope={origem:'documentos',conta:'470',tipo:'ENTRADAS'};
  files.fiscal242Entradas.files=['primeiro.xls','segundo.xls'];
  let root=context.createAccountAnalysis(scope);
  const checkbox=all(root).find(el=>el.tag==='input' && el.type==='checkbox');
  checkbox.checked=false;checkbox.events.change();
  await find(root,'fiscal-account-analysis-button').click();
  assert.equal(requests[0].options.body.get('usar_ia'),'false');
  files.fiscal242Entradas.files=['primeiro.xls','outro.xls'];
  root=context.createAccountAnalysis(scope);
  await find(root,'fiscal-account-analysis-button').click();
  assert.equal(requests.length,2);
});

test('parecer híbrido exibe evidências e limites sem HTML oriundo dos históricos',()=>{
  const {context,all}=setup();context.money=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});
  const result={analises:[{investigacao_hibrida:{
    resumo:{empresa:242,filial:'1',conta:'470',tipo:'ENTRADAS',fiscal:'100.00',contabil:'90.00',diferenca:'-10.00'},
    contagens:{lancamentos_examinados:1,documentos_examinados:0,correspondencias:0,evidencias_exibidas:1,evidencias_disponiveis:1},
    ia:{estado:'dispensada',chamadas:0,motivo:'Sem chamada externa.'},verificacoes:['Precisão em centavos'],hipoteses:[],
    conclusao:{grau:'inconclusiva',texto:'Causa não identificada'},limitacoes:['Faltam documentos'],
    composicao_diferenca:{disponivel:true,itens:[{descricao:'Diferença nos documentos',valor:'-10.00'}],
      residual:'0.00',fecha_aritmeticamente:true,documentos_lidos:'100.00',lacuna_documental:'0.00'},
    evidencias:[{referencia:'R-1',origem:'Razão',historico:'<img src=x onerror=delete_all()>',valor:'90.00'}]
  }}]};
  const root=context.renderAccountOpinion(result,{});
  const nodes=all(root);
  assert.ok(nodes.some(el=>el.textContent==='Causa inconclusiva'));
  assert.ok(nodes.some(el=>el.textContent==='Faltam documentos'));
  assert.ok(nodes.some(el=>el.textContent==='Residual sem composição'));
  assert.ok(nodes.some(el=>el.textContent.includes('Isso não comprova a causa contábil.')));
  assert.ok(nodes.some(el=>el.textContent==='<img src=x onerror=delete_all()>'));
  assert.ok(!nodes.some(el=>el.tag==='img'));
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


test('botão flutuante só é montado para a conta selecionada, abre conversa e reutiliza o parecer',async()=>{
  const {context,requests,find,node}=setup();
  const scope={origem:'documentos',conta:'470',tipo:'ENTRADAS',acumulador:'1403'};
  const panel=context.createAccountAnalysis(scope);
  const shell=node('div'),header=node('header'),comparison=node('div'),footer=node('footer'),navigation=node('nav');
  shell.append(header,comparison,footer);footer.append(navigation);comparison.scrollTop=275;
  assert.equal(find(shell,'fiscal-account-ai-fab'),undefined);
  panel.mount({shell,header,comparison,footer,navigation});
  const launcher=find(shell,'fiscal-account-ai-fab');
  assert.ok(launcher);
  assert.equal(launcher.attributes['aria-controls'],panel.id);
  assert.equal(panel.hidden,true);
  assert.equal(comparison.hidden,false);
  assert.equal(find(header,'fiscal-account-analysis-tabs'),undefined);
  await launcher.click();
  assert.equal(requests.length,1);
  assert.equal(panel.hidden,false);
  assert.equal(launcher.attributes['aria-expanded'],'true');
  assert.ok(shell.className.includes('fiscal-chat-open'));
  assert.equal(comparison.hidden,false);
  const body=find(panel,'fiscal-account-analysis-body'),rendered=body.children[0];
  assert.ok(find(panel,'fiscal-document-assistant'));
  assert.ok(find(panel,'fiscal-agent-chat-composer'));
  assert.equal(find(body,'fiscal-agent-chat-composer'),undefined);
  assert.equal(find(panel,'fiscal-account-analysis-bar').hidden,true);
  const expand=find(panel,'fiscal-account-ai-expand');
  await expand.click();
  assert.equal(expand.attributes['aria-pressed'],'true');
  assert.ok(panel.className.includes('is-expanded'));
  assert.equal(comparison.scrollTop,275);
  await expand.click();
  assert.equal(expand.attributes['aria-pressed'],'false');
  assert.equal(requests.length,1);
  assert.equal(body.children[0],rendered);
  await find(panel,'fiscal-account-ai-close').click();
  assert.equal(panel.hidden,true);
  assert.ok(!shell.className.includes('fiscal-chat-open'));
  assert.equal(comparison.scrollTop,275);
  await launcher.click();
  assert.equal(requests.length,1);
  assert.equal(body.children[0],rendered);
  let prevented=false;
  panel.events.keydown({key:'Escape',preventDefault:()=>{prevented=true;},stopPropagation:()=>{}});
  assert.equal(prevented,true);
  assert.equal(panel.hidden,true);
  panel.destroy();
  assert.equal(find(shell,'fiscal-account-ai-fab'),undefined);
  assert.equal(find(shell,'fiscal-account-ai-chat'),undefined);
});

test('chat pode ser recolhido enquanto analisa sem trocar a conferência',async()=>{
  const {context,find,node}=setup();let clock=0,tick,finish,calls=0;const cleared=[];
  context.Date={now:()=>clock};context.setInterval=fn=>{tick=fn;return 123;};context.clearInterval=id=>cleared.push(id);
  context.fetch=()=>{calls++;return new Promise(resolve=>{finish=resolve;});};
  const panel=context.createAccountAnalysis({origem:'resumo',conta:'470',tipo:'ENTRADAS'});
  const shell=node('div'),header=node('header'),comparison=node('div'),footer=node('footer'),navigation=node('nav');
  shell.append(header,comparison,footer);footer.append(navigation);panel.mount({shell,header,comparison,footer,navigation});
  const launcher=find(shell,'fiscal-account-ai-fab');
  const pending=launcher.click();
  const loading=find(panel,'fiscal-account-loading');assert.equal(loading.hidden,false);
  assert.equal(find(panel,'fiscal-account-loading-meter visually-hidden').attributes['aria-valuenow'],undefined);
  clock=65000;tick();assert.equal(find(panel,'fiscal-account-loading-time').textContent,'1 min 5 s');
  await find(panel,'fiscal-account-ai-close').click();
  assert.equal(comparison.hidden,false);
  assert.equal(panel.hidden,true);
  finish({ok:true,json:async()=>({escopo:{conta:'470',tipo:'ENTRADAS',origem:'resumo',acumulador:''},analises:[]})});
  await pending;
  assert.equal(loading.hidden,true);assert.ok(cleared.includes(123));
  await launcher.click();
  assert.equal(calls,1);assert.equal(panel.hidden,false);
  assert.equal(comparison.hidden,false);
});

test('chat resume a investigação e carrega o parecer completo apenas quando solicitado',()=>{
  const {context,find,all}=setup();
  context.money=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});
  const result={analises:[{conta:'362',tipo:'ENTRADAS',
    valores:{fiscal:130,contabil:120,diferenca:-10},
    parecer:{resumo_executivo:{conclusao:'A diferença de R$ 10 ainda requer documentos.'},leitura_comparacao:{}}
  }]};
  const report=context.renderCompactFiscalChatReport(result,{conta:'362',tipo:'ENTRADAS'});
  assert.ok(all(report).some(n=>n.textContent==='A diferença de R$ 10 ainda requer documentos.'));
  assert.ok(all(report).some(n=>n.textContent==='Ver investigação completa'));
  const full=find(report,'fiscal-chat-full-report');
  assert.equal(find(report,'fiscal-account-opinion'),undefined);
  full.open=true;full.events.toggle();
  assert.ok(find(report,'fiscal-account-opinion'));
});

test('parecer apresenta explicação, confirmação, solução condicional e validação em sequência',()=>{
  const {context,all}=setup();
  const root=context.renderAccountOpinion({analises:[{parecer:{leitura_comparacao:{orientacoes:[{
    acao:'Compare a nota',explicacao_simples:'Os valores diferem; a causa ainda não foi comprovada.',
    objetivo:'Confira a origem',para_concluir:'Confirme a mesma operação',
    solucao_condicional:'Se o documento comprovar erro, corrija a origem.',resultado_esperado:'Refaça a conferência da nota.'
  }]}}}]},{});
  const text=all(root).map(el=>el.textContent);
  const labels=['Confirme primeiro','Solução após confirmar','Como validar'].map(value=>text.indexOf(value));
  assert.ok(labels[0]>0 && labels[0]<labels[1] && labels[1]<labels[2]);
  assert.ok(text.includes('Os valores diferem; a causa ainda não foi comprovada.'));
  assert.ok(text.includes('Se o documento comprovar erro, corrija a origem.'));
});

function reviewFixture(contextId='a'.repeat(64)) {
  return {contexto_revisao:contextId,analises:[{provedor:'groq',parecer:{analise_exibicao:'Há um candidato a confirmar.',leitura_comparacao:{observacoes:['A nota aparece no relatório.'],orientacoes:[{
    categoria:'VALOR_DIFERENTE',ordem_revisao:1,acao:'Confira NF 100',prioridade_motivo:'Diferença de valor identificada.',
    documentos:[{referencia:'E-1',titulo:'NF 100',onde_conferir:'Acumulador 1152; conta candidata 508; L1.',vinculo:'Candidato a confirmar.'}],
    solucao_condicional:'Somente após conferir a operação.',resultado_esperado:'Refaça a conferência.'
  }]}}}]};
}

test('registro exige justificativa, persiste por evidências, filtra e permite reabrir sem chamar IA',async()=>{
  const {context,find,all}=setup();const storage=new Map();
  context.localStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)};
  let root=context.renderAccountOpinion(reviewFixture(),{});
  const text=all(root).map(el=>el.textContent);
  assert.ok(text.indexOf('O que os relatórios mostram')<text.indexOf('Hipótese da IA · a confirmar'));
  assert.ok(text.includes('Acumulador 1152; conta candidata 508; L1.'));
  await find(root,'fiscal-account-resolution-save').click();assert.equal(storage.size,0);
  assert.match(find(root,'fiscal-account-resolution-error').textContent,/Informe/);
  const input=all(root).find(el=>el.tag==='textarea');input.value='Conferi a NF e corrigi o vínculo. <script>texto</script>';
  await find(root,'fiscal-account-resolution-save').click();
  assert.equal(find(root,'fiscal-account-resolution-status').textContent,'Resolvido manualmente');
  assert.match(find(root,'fiscal-account-review-progress').textContent,/0 pendentes · 1 resolvido manualmente/);
  root=context.renderAccountOpinion(reviewFixture(),{});
  assert.ok(find(root,'fiscal-account-resolution-status'));
  await find(root,'fiscal-account-review-filter').click();assert.equal(find(root,'fiscal-account-opinion-reference').hidden,true);
  await find(root,'fiscal-account-review-filter').click();assert.equal(find(root,'fiscal-account-opinion-reference').hidden,false);
  await find(root,'fiscal-account-resolution-link').click();assert.equal(find(root,'fiscal-account-resolution-status'),undefined);
  assert.match(find(root,'fiscal-account-review-progress').textContent,/1 pendente · 0 resolvidos/);
  assert.ok(all(root).find(el=>el.tag==='textarea').value.includes('corrigi o vínculo'));
  root=context.renderAccountOpinion(reviewFixture('b'.repeat(64)),{});
  assert.equal(all(root).find(el=>el.tag==='textarea').value,'');
});

test('falha no armazenamento mantém item pendente e avisa sem registrar sucesso',async()=>{
  const {context,find,all}=setup();context.localStorage={getItem:()=>null,setItem:()=>{throw new Error('quota');}};
  const root=context.renderAccountOpinion(reviewFixture(),{});
  all(root).find(el=>el.tag==='textarea').value='Conferi o documento.';
  await find(root,'fiscal-account-resolution-save').click();
  assert.equal(find(root,'fiscal-account-resolution-status'),undefined);
  assert.match(find(root,'fiscal-account-resolution-error').textContent,/Não foi possível salvar/);
  assert.match(find(root,'fiscal-account-review-progress').textContent,/1 pendente/);
});
