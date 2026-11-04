const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.events={};this.attrs={};this.hidden=false;this.value='';this.checked=false;this.classes=new Set();this.classList={contains:k=>this.classes.has(k),toggle:k=>{if(this.classes.has(k)){this.classes.delete(k);return false;}this.classes.add(k);return true;}};}
 prepend(...items){this.children.unshift(...items);} append(...items){this.children.push(...items);} after(item){this.afterNode=item;} replaceChildren(...items){this.children=items;} setAttribute(k,v){this.attrs[k]=v;} addEventListener(k,v){this.events[k]=v;} focus(){this.focused=true;} hasChildNodes(){return this.children.length>0;}
 querySelectorAll(selector){return flatten(this).filter(e=>selector==='button'?e.tag==='button':['button','input'].includes(e.tag));}
}
function flatten(e){return e.children.flatMap(child=>typeof child==='object'?[child,...flatten(child)]:[]);}
function setup({storage,bytes="synthetic",options={},company=242}={}){
 const nodes={'#classifyForm':new Element(),'#companyPanel':new Element(),'[data-pane="base"]':new Element(),'.app-shell':new Element()};nodes['[data-pane="base"]'].classes.add('active');
 const observers=[];let resolve;const pending=new Promise(r=>resolve=r);const requests=[],workflowStates=[];
 const ctx={sessionStorage:storage,TextEncoder,crypto:{subtle:{digest:async(_,value)=>require('node:crypto').createHash('sha256').update(Buffer.from(value)).digest()}},document:{createElement:t=>new Element(t),createTextNode:t=>t,querySelector:s=>nodes[s]},MutationObserver:class{constructor(fn){observers.push(fn);}observe(){}},AbortController,FormData,Blob,
 API:()=>'',fetch:(url,options)=>{requests.push({url,options});return pending;},responseError:async()=>'',bankName:b=>b};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('assets/js/base-investigation.js','utf8'),ctx);
 const host=nodes['.app-shell'].children[0],launcher=host.children[0],window=host.children[1],header=window.children[0],body=window.children[1];
 const mount=()=>ctx.RazyncBaseInvestigation.mount({company,prepared:{blob:async()=>new Blob([bytes])},options,summary:{cobertura:{pendentes:1}},onState:(state,message)=>workflowStates.push({state,message})});
 return {ctx,nodes,observers,resolve,requests,launcher,window,header,body,mount,workflowStates};
}
const report={total_pendencias:1,grupos_investigados:1,ia:{},limitacoes:[],token:'synthetic',catalogo_contas:[{conta:'412',natureza:'pago',bancos:['itau_508'],periodos:['2026-07'],ocorrencias:2,exemplos:[{historico:'Pago fornecedor de teste',banco:'itau_508',periodos:['2026-07'],ocorrencias:2}]}],sugestoes:[{_aba:'Itaú',_linha:2,natureza:'pago','Histórico':'Teste',Valor:-1,Data:'15/10/2026',grupo:1,_banco:'itau_508',assinatura:'pago|teste',conta_sugerida:'412',situacao:'MODERADA',justificativa:'Evidência',evidencias:[]}]};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function textOf(e){return (e.textContent || '')+(e.children || []).map(c=>typeof c==='string'?c:textOf(c)).join('');}
async function populated(data=report,settings){const h=setup(settings);h.mount();h.launcher.events.click();await flush();h.resolve({ok:true,json:async()=>data});for(let i=0;i<6;i++)await flush();return h;}
test('janela inicia fechada e abre pelo botão flutuante sem chamada duplicada',async()=>{const h=await populated();assert.equal(h.window.hidden,false);assert.equal(h.requests.length,1);h.header.children[1].children[1].events.click();assert.equal(h.window.hidden,true);h.launcher.events.click();await flush();assert.equal(h.requests.length,1);});
test('minimizar e ampliar preservam aprovação e aprendizado começa desmarcado',async()=>{const h=await populated();const inputs=flatten(h.body).filter(e=>e.tag==='input');action(h,'Aprovar e próximo').events.click();const learn=inputs.find(e=>e.type==='checkbox'&&!e.attrs['aria-label']);assert.equal(learn.checked,false);h.header.children[1].children[0].events.click();assert.equal(h.window.classList.contains('is-expanded'),true);h.header.children[1].children[1].events.click();h.launcher.events.click();assert.match(textOf(h.body),/Conta aprovada/);});
test('históricos aparecem automaticamente ao lado do lançamento sem nova consulta',async()=>{const h=await populated();const text=textOf(h.body);assert.match(text,/Referência da base/);assert.match(text,/Pago fornecedor de teste/);assert.match(text,/07\/2026/);assert.equal(h.requests.length,1);assert.equal(h.requests[0].options.body.get('usar_ia'),'false');assert.equal(h.nodes['#classifyForm'].afterNode,undefined);});
test('evidências distinguem assinatura exata, histórico semelhante, banco, períodos e ocorrências',async()=>{
 const data=JSON.parse(JSON.stringify(report));data.sugestoes[0].evidencias=[
  {conta:'412',exata:true,mesmo_banco:true,banco:'itau_508',periodos:['2026-07','2026-08'],ocorrencias:20,historicos:['Pago: Empresa: Fornecedor ABC']},
  {conta:'413',exata:false,mesmo_banco:false,banco:'bb',periodos:['2026-06'],ocorrencias:4,historicos:['Pago: Empresa: Fornecedor ABC contrato']}
 ];
 const h=await populated(data),text=textOf(h.body);
 assert.match(text,/Evidências que fundamentam a análise/);assert.match(text,/Assinatura exata/);assert.match(text,/Histórico semelhante/);
 assert.match(text,/Mesmo banco/);assert.match(text,/Outro banco/);assert.match(text,/07\/2026, 08\/2026/);assert.match(text,/20 ocorrências/);
 assert.match(text,/outras contas apenas em históricos semelhantes/);assert.match(text,/conta continua ativa no plano atual/);
});
test('conflitos exatos explicam que nenhuma conta foi escolhida automaticamente',async()=>{
 const data=JSON.parse(JSON.stringify(report));data.sugestoes[0].situacao='MANUAL';data.sugestoes[0].conta_sugerida='';
 data.sugestoes[0].evidencias=[
  {conta:'412',exata:true,mesmo_banco:true,banco:'itau_508',periodos:['2026-07'],ocorrencias:3,historicos:[]},
  {conta:'413',exata:true,mesmo_banco:true,banco:'itau_508',periodos:['2026-08'],ocorrencias:2,historicos:[]}
 ];
 const h=await populated(data),text=textOf(h.body);
 assert.match(text,/Conflito: há evidências do mesmo nível para 2 contas diferentes/);
 assert.match(text,/Nenhuma conta foi escolhida automaticamente/);
});
test('trocar ferramenta oculta a janela e reset invalida resultados em andamento',async()=>{const h=setup();h.mount();h.launcher.events.click();await flush();h.nodes['[data-pane="base"]'].classes.clear();h.observers[0]();assert.equal(h.window.hidden,true);assert.equal(h.launcher.hidden,true);h.ctx.RazyncBaseInvestigation.reset();h.resolve({ok:true,json:async()=>report});await flush();assert.equal(h.body.children.length,0);assert.equal(h.window.hidden,true);});

function twoRows(){const data=JSON.parse(JSON.stringify(report));data.total_pendencias=2;data.grupos_investigados=2;data.sugestoes.push({...data.sugestoes[0],_linha:3,grupo:2,'Histórico':'Segundo teste'});return data;}
const action=(h,text)=>flatten(h.window).find(e=>e.tag==='button'&&e.textContent===text);
test('aprovar e próximo mantém a decisão anterior e navega sem novas chamadas',async()=>{const h=await populated(twoRows());action(h,'Aprovar e próximo').events.click();let current=flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 3');assert.ok(current);const first=flatten(h.body).find(e=>e.attrs['aria-label']==='Comparar Itaú, linha 2');first.events.click();assert.match(textOf(h.body),/Conta aprovada/);assert.equal(h.requests.length,1);assert.ok(action(h,'Gerar Excel com 1 revisão'));});
test('alterar uma conta aprovada exige nova aprovação',async()=>{const h=await populated();action(h,'Aprovar e próximo').events.click();const account=flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 2');account.value='999';account.events.input();assert.equal(action(h,'Gerar Excel com 0 revisões').disabled,true);assert.equal(action(h,'Gerar Excel com 0 revisões').disabled,true);});
test('IA opcional só reordena a fila sem apagar contas e aprovações',async()=>{const h=await populated(twoRows());action(h,'Aprovar e próximo').events.click();h.ctx.fetch=async(url,options)=>{h.requests.push({url,options});return {ok:true,json:async()=>({...twoRows(),token:'prioritized',ia:{prioridades:[2],motivo:'Prioridade de teste'}})};};await action(h,'Priorizar casos com IA').events.click();assert.equal(h.requests[1].options.body.get('usar_ia'),'true');const first=flatten(h.body).find(e=>e.attrs['aria-label']==='Comparar Itaú, linha 2');first.events.click();assert.match(textOf(h.body),/Conta aprovada/);assert.ok(action(h,'Gerar Excel com 1 revisão'));});

test('prepara pendências locais antes de abrir o assistente',async()=>{const h=setup();h.mount();await flush();assert.equal(h.window.hidden,true);assert.equal(h.requests.length,1);assert.equal(h.requests[0].options.body.get('usar_ia'),'false');h.launcher.events.click();assert.equal(h.requests.length,1);});
test('cancelar preparação não reinicia consultas automaticamente',async()=>{const h=setup();h.mount();await flush();action(h,'Cancelar').events.click();await flush();assert.equal(h.requests.length,1);assert.match(textOf(h.body),/Preparação interrompida/);assert.deepEqual(h.workflowStates.at(-1),{state:'error',message:'Preparação interrompida'});});
test('fila inicia pelos casos com conta candidata única',async()=>{const data=twoRows();data.sugestoes[0].conta_sugerida='';data.sugestoes[0].evidencias=[];const h=await populated(data);assert.ok(flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 3'));assert.ok(action(h,'Contas conflitantes'));assert.ok(action(h,'Sem histórico'));});
function groupRows(){const data=twoRows();data.grupos_investigados=1;data.sugestoes[1]={...data.sugestoes[0],_linha:3};return data;}
test('grupo exige confirmação e permite excluir linha antes de aprovar',async()=>{const h=await populated(groupRows());action(h,'Revisar 2 equivalentes').events.click();assert.ok(action(h,'Gerar Excel com 0 revisões'));const second=flatten(h.body).find(e=>e.attrs['aria-label']==='Incluir Itaú, linha 3 no grupo');second.checked=false;action(h,'Aprovar linhas selecionadas').events.click();assert.ok(action(h,'Gerar Excel com 1 revisão'));});
test('conta alterada impede confirmar um grupo com a conta antiga',async()=>{const h=await populated(groupRows());action(h,'Revisar 2 equivalentes').events.click();const account=flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 2');account.value='999';action(h,'Aprovar linhas selecionadas').events.click();assert.match(textOf(h.window),/A conta mudou/);assert.ok(action(h,'Gerar Excel com 0 revisões'));});
test('grupo não inclui outros bancos, naturezas ou históricos',async()=>{const data=groupRows();data.sugestoes[1]._banco='bb';const h=await populated(data);assert.equal(action(h,'Revisar 2 equivalentes'),undefined);});

test('grupo completo registra aprovações sem enviar Excel nem ensinar à base',async()=>{const h=await populated(groupRows());action(h,'Revisar 2 equivalentes').events.click();action(h,'Aprovar linhas selecionadas').events.click();assert.ok(action(h,'Gerar Excel com 2 revisões'));assert.equal(h.requests.length,1);const learn=flatten(h.body).find(e=>e.type==='checkbox'&&!e.attrs['aria-label']);assert.equal(learn.checked,false);});
test('conta digitada diferente em outra linha não é sobrescrita por padrão',async()=>{const data=groupRows();data.catalogo_contas.push({...data.catalogo_contas[0],conta:'413'});data.sugestoes[1].conta_sugerida='413';const h=await populated(data);action(h,'Revisar 2 equivalentes').events.click();const include=flatten(h.body).find(e=>e.attrs['aria-label']==='Incluir Itaú, linha 3 no grupo');assert.equal(include.checked,false);action(h,'Aprovar linhas selecionadas').events.click();assert.ok(action(h,'Gerar Excel com 1 revisão'));const input=flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 3');assert.equal(input.value,'413');});

test('adiar não conta como aprovação e pode ser retomado no filtro',async()=>{const h=await populated(twoRows());action(h,'Adiar').events.click();assert.match(textOf(h.header),/0 aprovados · 1 adiado · 1 pendente/);assert.ok(action(h,'Gerar Excel com 0 revisões'));action(h,'Adiadas').events.click();assert.ok(flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 2'));action(h,'Aprovar e próximo').events.click();assert.match(textOf(h.header),/1 aprovado · 0 adiados · 1 pendente/);});

test('trocar conta atualiza evidências sem manter sugestão anterior no resumo',async()=>{const data=JSON.parse(JSON.stringify(report));data.catalogo_contas.push({...data.catalogo_contas[0],conta:'413'});data.sugestoes[0].evidencias=[{conta:'412',periodos:['2026-07'],mesmo_banco:true},{conta:'413',periodos:['2026-08','2026-09'],mesmo_banco:false}];const h=await populated(data);const account=flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 2');account.value='413';account.events.input();const summary=flatten(h.body).find(e=>e.className==='base-evidence-summary');assert.match(textOf(summary),/Conta em comparação: 413/);assert.match(textOf(summary),/2 períodos/);assert.match(textOf(summary),/outro banco/);assert.doesNotMatch(textOf(summary),/Conta sugerida: 412/);assert.equal(action(h,'Aprovar e próximo').disabled,false);account.value='999';account.events.input();assert.equal(action(h,'Aprovar e próximo').disabled,true);});


test('fila agrupa equivalentes sem aprovar e permite alternar para linhas',async()=>{const h=await populated(groupRows());const entries=()=>flatten(h.body).filter(e=>e.className==='base-review-item');assert.equal(entries().length,1);assert.match(textOf(entries()[0]),/2 lançamentos/);assert.ok(action(h,'Gerar Excel com 0 revisões'));action(h,'Agrupar equivalentes').events.click();assert.equal(entries().length,2);});

test('busca encontra histórico e valor sem alterar aprovações',async()=>{const h=await populated(twoRows());const search=flatten(h.body).find(e=>e.attrs['aria-label']==='Pesquisar pendências');search.value='Segundo teste';search.events.input();assert.ok(flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 3'));assert.equal(flatten(h.body).filter(e=>e.className==='base-review-item').length,1);assert.ok(action(h,'Gerar Excel com 0 revisões'));});

const memoryStorage=()=>{const map=new Map();return {getItem:key=>map.get(key)||null,setItem:(key,value)=>map.set(key,value),removeItem:key=>map.delete(key),map};};
test('rascunho exige retomada explícita para mesmo arquivo empresa perfil e evidências',async()=>{const storage=memoryStorage();const h=await populated(report,{storage});action(h,'Aprovar e próximo').events.click();assert.equal(storage.map.size,1);assert.doesNotMatch([...storage.map.values()].join(''),/Pago fornecedor/);const next=await populated(report,{storage});assert.ok(action(next,'Gerar Excel com 0 revisões'));assert.ok(action(next,'Retomar revisão salva'));action(next,'Retomar revisão salva').events.click();assert.ok(action(next,'Gerar Excel com 1 revisão'));assert.equal(next.requests.length,1);const changed=await populated(report,{storage,bytes:'different workbook'});assert.equal(action(changed,'Retomar revisão salva'),undefined);const company=await populated(report,{storage,company:3});assert.equal(action(company,'Retomar revisão salva'),undefined);const profile=await populated(report,{storage,options:{modo:'different'}});assert.equal(action(profile,'Retomar revisão salva'),undefined);const evidence=JSON.parse(JSON.stringify(report));evidence.sugestoes[0].justificativa='Nova evidência';const updated=await populated(evidence,{storage});assert.equal(action(updated,'Retomar revisão salva'),undefined);});

test('falha de armazenamento não impede revisão e aprovação',async()=>{const h=await populated(report,{storage:{getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}}});action(h,'Aprovar e próximo').events.click();assert.ok(action(h,'Gerar Excel com 1 revisão'));});


test('busca aceita valor com milhar e centavos no formato brasileiro',async()=>{const data=twoRows();data.sugestoes[0].Valor=-2000;const h=await populated(data);const search=flatten(h.body).find(e=>e.attrs['aria-label']==='Pesquisar pendências');search.value='2.000,00';search.events.input();assert.ok(flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 2'));assert.equal(flatten(h.body).filter(e=>e.className==='base-review-item').length,1);});

test('grupo mostra total em centavos sem alterar valores ou aprovar linhas',async()=>{const data=groupRows();data.sugestoes[0].Valor=-17.53;data.sugestoes[1].Valor=-18.53;const h=await populated(data);const item=flatten(h.body).find(e=>e.className==='base-review-item');assert.match(textOf(item),/Total -R\$\s*36,06/);assert.equal(data.sugestoes[0].Valor,-17.53);assert.ok(action(h,'Gerar Excel com 0 revisões'));});


test('análise explica diferenças numéricas e usa evidência do lançamento em vez de exemplo genérico',async()=>{const data=JSON.parse(JSON.stringify(report));data.sugestoes[0]['Histórico']='Recebido: RESG CDB 2290094';data.sugestoes[0].evidencias=[{conta:'412',exata:true,mesmo_banco:true,banco:'itau_508',periodos:['2026-07'],ocorrencias:2,historicos:['Recebido: RESG CDB 2010094']}];const h=await populated(data);const summary=flatten(h.body).find(e=>e.className==='base-evidence-summary');assert.equal(summary.attrs['data-analysis-state'],'suggested');assert.match(textOf(summary),/Por que considerar/);assert.match(textOf(summary),/Os números do histórico diferem/);const history=flatten(h.body).find(e=>e.className==='base-account-history');assert.match(textOf(history),/2010094/);assert.doesNotMatch(textOf(history),/Pago fornecedor de teste/);assert.ok(action(h,'Gerar Excel com 0 revisões'));});
test('análise destaca outro banco e mantém decisão manual',async()=>{const data=JSON.parse(JSON.stringify(report));data.sugestoes[0].evidencias=[{conta:'412',exata:false,mesmo_banco:false,banco:'bb',periodos:['2026-07'],ocorrencias:1,historicos:['Teste']}];const h=await populated(data);const summary=flatten(h.body).find(e=>e.className==='base-evidence-summary');assert.match(textOf(summary),/A referência é de outro banco/);assert.ok(action(h,'Gerar Excel com 0 revisões'));});

test('desfazer restaura aprovação e retorna ao lançamento sem gravar aprendizado',async()=>{const h=await populated(twoRows());action(h,'Aprovar e próximo').events.click();assert.ok(action(h,'Gerar Excel com 1 revisão'));action(h,'Desfazer última aprovação').events.click();assert.ok(action(h,'Gerar Excel com 0 revisões'));assert.equal(h.requests.length,1);assert.equal(action(h,'Desfazer última aprovação').disabled,true);});
test('exportação exige resumo e envia somente contas explicitamente aprovadas',async()=>{const h=await populated(twoRows());action(h,'Aprovar e próximo').events.click();await action(h,'Gerar Excel com 1 revisão').events.click();assert.equal(h.requests.length,1);const panel=flatten(h.body).find(e=>e.className==='base-export-review');assert.equal(panel.hidden,false);assert.match(textOf(panel),/1 linha\(s\) aprovada/);assert.match(textOf(panel),/Aprendizado: desativado/);action(h,'Confirmar e gerar Excel').events.click();await flush();const request=h.requests.find(r=>r.url.endsWith('/revisar'));assert.ok(request);assert.equal(request.options.body.get('aprender'),'false');const revisions=JSON.parse(request.options.body.get('revisoes_json'));assert.equal(revisions.length,1);assert.equal(revisions[0]['Conta da contrapartida'],'412');});
test('nome de conta é apresentado somente quando fornecido no catálogo',async()=>{const data=JSON.parse(JSON.stringify(report));data.catalogo_contas[0].nome='Fornecedores';const h=await populated(data);assert.match(textOf(h.body),/412 — Fornecedores/);});

test('download externo inclui aprovações sem confirmação adicional e reutiliza Excel revisado',async()=>{const h=await populated(twoRows());assert.equal(await h.ctx.RazyncBaseInvestigation.download(242),false);action(h,'Aprovar e próximo').events.click();let generated=0,downloads=[];h.ctx.Response=Response;h.ctx.renderClassificationCoverage=()=>{};h.ctx.showWorkflowPreview=()=>{};h.ctx.downloadBlob=async response=>downloads.push(await response.text());h.ctx.fetch=async(url,options)=>{if(url.endsWith('/revisar')){generated++;const rows=JSON.parse(options.body.get('revisoes_json'));assert.equal(rows.length,1);assert.equal(rows[0]['Conta da contrapartida'],'412');assert.equal(options.body.get('aprender'),'false');return {ok:true,headers:{get:()=>JSON.stringify({aplicadas:1})},blob:async()=>new Blob(['reviewed'])};}return {ok:true,json:async()=>({})};};assert.equal(await h.ctx.RazyncBaseInvestigation.download(242),true);assert.equal(await h.ctx.RazyncBaseInvestigation.download(242),true);assert.equal(generated,1);assert.deepEqual(downloads,['reviewed','reviewed']);assert.equal(await h.ctx.RazyncBaseInvestigation.download(968),false);h.ctx.RazyncBaseInvestigation.reset();assert.equal(await h.ctx.RazyncBaseInvestigation.download(242),false);});

test('ponto de conferência e números diferentes ficam visíveis sem abrir detalhes',async()=>{const data=JSON.parse(JSON.stringify(report));data.sugestoes[0]['Histórico']='Resgate CDB 2290094';data.sugestoes[0].evidencias=[{conta:'412',exata:true,mesmo_banco:true,banco:'itau_508',periodos:['2026-07'],ocorrencias:1,historicos:['Resgate CDB 2010094']}];const h=await populated(data);const focus=flatten(h.body).find(e=>e.className==='base-check-focus');assert.equal(focus.attrs.role,'note');assert.match(textOf(focus),/Números diferentes no histórico/);assert.match(textOf(focus),/Números diferentes/);const delta=flatten(h.body).find(e=>e.className==='base-comparison-delta');assert.match(textOf(delta),/No lançamento2290094/);assert.match(textOf(delta),/Na referência da base2010094/);assert.equal(delta.hidden,false);});


test('marca animada usa letras separadas e máscaras únicas a cada montagem',async()=>{const h=setup();h.mount();const first=h.launcher.children[0].innerHTML;assert.match(first,/class="base-rz-letter base-rz-r"/);assert.match(first,/class="base-rz-letter base-rz-z"/);const id=first.match(/mask id="([^"]+)"/)[1];h.mount();const second=h.launcher.children[0].innerHTML;assert.notEqual(second.match(/mask id="([^"]+)"/)[1],id);assert.match(second,/razync-logo-original.png/);});


function configureExport(h,{previewPending=false,previewError=false}={}){
  const downloads=[];let generated=0;
  h.ctx.Response=Response;h.ctx.renderClassificationCoverage=()=>{};h.ctx.showWorkflowPreview=()=>{};
  h.ctx.downloadBlob=async response=>downloads.push(await response.text());
  h.ctx.fetch=async(url,options)=>{
    if(url.endsWith('/revisar')){generated++;assert.equal(options.body.get('aprender'),'false');return {ok:true,headers:{get:()=>JSON.stringify({aplicadas:1})},blob:async()=>new Blob(['reviewed'])};}
    if(previewPending)return new Promise(()=>{});
    if(previewError)throw Error('Preview offline');
    return {ok:true,json:async()=>({})};
  };
  return {downloads,generated:()=>generated};
}
test('Excel pronto baixa mesmo quando a atualização da prévia continua pendente',async()=>{
  const h=await populated(twoRows());action(h,'Aprovar e próximo').events.click();const x=configureExport(h,{previewPending:true});
  let finished=false;const task=h.ctx.RazyncBaseInvestigation.download(242).then(()=>{finished=true});
  for(let i=0;i<5;i++)await flush();
  assert.equal(finished,true,'A prévia opcional bloqueou o arquivo pronto');await task;
  assert.deepEqual(x.downloads,['reviewed']);assert.equal(x.generated(),1);
});
test('confirmar geração no assistente já baixa e mantém o arquivo disponível no topo',async()=>{
  const h=await populated(twoRows());action(h,'Aprovar e próximo').events.click();const x=configureExport(h,{previewError:true});
  await action(h,'Gerar Excel com 1 revisão').events.click();assert.equal(x.downloads.length,0);
  action(h,'Confirmar e gerar Excel').events.click();for(let i=0;i<6;i++)await flush();
  assert.deepEqual(x.downloads,['reviewed']);assert.equal(x.generated(),1);
  assert.ok(flatten(h.header).some(e=>e.tag==='button'&&textOf(e)==='Baixar Excel revisado'));
  await h.ctx.RazyncBaseInvestigation.download(242);assert.equal(x.generated(),1);assert.equal(x.downloads.length,2);
});


test('falha da IA libera nova tentativa e preserva as aprovações',async()=>{
  const h=await populated(twoRows());action(h,'Aprovar e próximo').events.click();
  let attempts=0;h.ctx.fetch=async()=>{attempts++;return {ok:true,json:async()=>attempts===1?{ia:{estado:'indisponivel',motivo:'Limite temporário.'}}:{ia:{estado:'concluida',provedor:'groq',modelo:'test',prioridades:[2],motivo:'Ordem conferida.'}}};};
  await action(h,'Priorizar casos com IA').events.click();assert.equal(action(h,'Tentar IA novamente').disabled,false);
  assert.ok(action(h,'Gerar Excel com 1 revisão'));assert.match(textOf(h.body),/Limite temporário/);
  await action(h,'Tentar IA novamente').events.click();assert.equal(attempts,2);assert.ok(action(h,'Gerar Excel com 1 revisão'));
  assert.equal(action(h,'Prioridades atualizadas').disabled,true);assert.match(textOf(h.body),/Groq · test/);
});
test('falha de rede da IA também permite repetir sem refazer a classificação',async()=>{
  const h=await populated(twoRows());h.ctx.fetch=async()=>{throw Error('Conexão interrompida')};
  await action(h,'Priorizar casos com IA').events.click();assert.equal(action(h,'Tentar IA novamente').disabled,false);
  assert.match(textOf(h.body),/Conexão interrompida/);assert.ok(action(h,'Gerar Excel com 0 revisões'));
});


test('análise do lançamento usa apenas sua seleção e preserva aprovações e conta',async()=>{
  const h=await populated(twoRows());let calls=0;h.ctx.fetch=async(url,options)=>{
    calls++;assert.match(url,/\/242\/analisar-pendente$/);const body=JSON.parse(options.body);
    assert.deepEqual(body,{investigacao_token:'synthetic',aba:'Itaú',linha:2});
    return {ok:true,json:async()=>({estado:'concluida',aba:'Itaú',linha:2,provedor:'gemini',modelo:'test',analise:{resumo:'Histórico compatível; confira o documento.',contas:[{conta:'412',explicacao:'Referência histórica.'}],conferir:['Confira a operação no documento.'],limite:'A conta precisa ser aprovada por você.'}})};
  };
  await action(h,'Analisar lançamento com IA').events.click();assert.equal(calls,1);
  assert.match(textOf(h.body),/Histórico compatível/);assert.ok(action(h,'Gerar Excel com 0 revisões'));
  assert.equal(action(h,'Análise pronta').disabled,true);assert.equal(h.requests.length,1);
});
test('falha de análise permite tentar novamente sem aprovar nem editar a conta',async()=>{
  const h=await populated(twoRows());h.ctx.fetch=async()=>({ok:true,json:async()=>({estado:'indisponivel',aba:'Itaú',linha:2,motivo:'Limite temporário.'})});
  await action(h,'Analisar lançamento com IA').events.click();assert.match(textOf(h.body),/Limite temporário/);
  assert.equal(action(h,'Tentar análise novamente').disabled,false);assert.ok(action(h,'Gerar Excel com 0 revisões'));
});
test('resposta atrasada de outra linha nunca aparece na seleção atual',async()=>{
  const h=await populated(twoRows());let resolve;h.ctx.fetch=()=>new Promise(r=>resolve=r);
  const pending=action(h,'Analisar lançamento com IA').events.click();action(h,'Próximo').events.click();
  resolve({ok:true,json:async()=>({estado:'concluida',aba:'Itaú',linha:2,provedor:'gemini',analise:{resumo:'Análise da primeira linha',contas:[],conferir:['Documento'],limite:'Conferir'}})});
  await pending;assert.doesNotMatch(textOf(h.body),/Análise da primeira linha/);assert.ok(action(h,'Gerar Excel com 0 revisões'));
});

test('datas Excel e ISO são legíveis sem alterar os dados da revisão',async()=>{
 for(const value of [46244,'46244','2026-08-10T00:00:00']){
  const data=JSON.parse(JSON.stringify(report));data.sugestoes[0].Data=value;
  const h=await populated(data);assert.match(textOf(h.body),/10\/08\/2026/);
  assert.equal(data.sugestoes[0].Data,value);
 }
});
test('candidata única abre referência sem preencher conta nem aprovar',async()=>{
 const data=JSON.parse(JSON.stringify(report));const s=data.sugestoes[0];s.conta_sugerida='';s.situacao='MANUAL';
 s.evidencias=[{conta:'412',mesmo_banco:true,periodos:['2026-07'],historicos:['Pago fornecedor de teste']}];
 const h=await populated(data);assert.match(textOf(h.body),/Pago fornecedor de teste/);
 const input=flatten(h.body).find(e=>e.attrs['aria-label']==='Conta para Itaú, linha 2');
 assert.equal(input.value,'');assert.equal(action(h,'Aprovar e próximo').disabled,true);assert.equal(h.requests.length,1);
});
test('comparação precede a IA e detalhes da resposta começam recolhidos',async()=>{
 const h=await populated();const grid=flatten(h.body).find(e=>e.className==='base-history-comparison');
 assert.equal(grid.children[0].className,'base-history-received');assert.equal(grid.children[1].className,'base-history-saved');assert.equal(grid.children[2].className,'base-ai-explanation');
 h.ctx.fetch=async()=>({ok:true,json:async()=>({estado:'concluida',aba:'Itaú',linha:2,provedor:'groq',modelo:'test',analise:{resumo:'Conferir natureza.',contas:[],conferir:['Confira o documento'],limite:'Conferência humana'}})});
 await action(h,'Analisar lançamento com IA').events.click();
 const details=flatten(h.body).find(e=>e.className==='base-ai-explain-details');assert.equal(details.open,false);
 assert.match(textOf(h.body),/1 lançamento em 1 grupo/);assert.ok(action(h,'Gerar Excel com 0 revisões'));
});
