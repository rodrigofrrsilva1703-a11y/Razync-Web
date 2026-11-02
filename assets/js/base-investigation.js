/* Optional investigation of the exact classified result, never the original upload. */
(() => {
  let context, controller, priorityController, generation=0, wantsOpen=false;
  const launcher=document.createElement('button');launcher.type='button';launcher.className='base-ai-launcher';launcher.hidden=true;
  launcher.textContent='Revisar pendências';launcher.setAttribute('aria-label','Revisar pendências da Base Inteligente');launcher.setAttribute('aria-controls','baseInvestigationWindow');launcher.setAttribute('aria-expanded','false');
  const floating=document.createElement('section');floating.id='baseInvestigationWindow';floating.className='base-ai-window';floating.hidden=true;
  floating.setAttribute('role','region');floating.setAttribute('aria-label','Assistente da Base Inteligente');
  const windowHeader=document.createElement('header');windowHeader.className='base-ai-window-header';
  const identity=document.createElement('div');identity.className='base-ai-identity';const windowTitle=document.createElement('strong');windowTitle.textContent='Assistente da Base';
  const subtitle=document.createElement('small');subtitle.textContent='Compare históricos e revise suas contas.';const brandCopy=document.createElement('div');brandCopy.append(windowTitle,subtitle);identity.append(brandMark(),brandCopy);
  const windowActions=document.createElement('div');windowActions.className='base-ai-window-actions';
  const expand=document.createElement('button');expand.type='button';expand.textContent='⤢';expand.setAttribute('aria-label','Ampliar assistente');expand.setAttribute('aria-pressed','false');
  const minimize=document.createElement('button');minimize.type='button';minimize.textContent='×';minimize.setAttribute('aria-label','Fechar assistente');minimize.title='Fechar sem perder sua revisão';
  windowActions.append(expand,minimize);windowHeader.append(identity,windowActions);
  const workbar=document.createElement('div');workbar.className='base-ai-workbar';windowHeader.append(workbar);
  const body=document.createElement('div');body.className='base-ai-window-body';floating.append(windowHeader,body);
  const host=document.createElement('div');host.id='baseAiHost';host.append(launcher,floating);document.querySelector('.app-shell').append(host);
  function openWindow(){wantsOpen=true;floating.hidden=false;launcher.hidden=true;launcher.setAttribute('aria-expanded','true');minimize.focus();}
  function minimizeWindow(){wantsOpen=false;floating.hidden=true;launcher.hidden=!context;launcher.setAttribute('aria-expanded','false');if(context)launcher.focus();}
  function openOrInvestigate(){openWindow();if(!body.hasChildNodes())investigate();}
  launcher.addEventListener('click',openOrInvestigate);minimize.addEventListener('click',minimizeWindow);
  expand.addEventListener('click',()=>{const expanded=floating.classList.toggle('is-expanded');expand.setAttribute('aria-pressed',String(expanded));expand.setAttribute('aria-label',expanded?'Restaurar tamanho do assistente':'Ampliar assistente');});
  floating.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();minimizeWindow();}});
  const companyPanel=document.querySelector('#companyPanel'),basePane=document.querySelector('[data-pane="base"]');
  const syncVisibility=()=>{const active=Boolean(context) && !companyPanel.hidden && basePane.classList.contains('active');floating.hidden=!active || !wantsOpen;launcher.hidden=!active || wantsOpen;};
  const visibilityObserver=new MutationObserver(syncVisibility);
  visibilityObserver.observe(companyPanel,{attributes:true,attributeFilter:['hidden']});
  visibilityObserver.observe(basePane,{attributes:true,attributeFilter:['class']});
  function brandMark(){
    const mark=document.createElement('span');mark.className='base-brand-mark';mark.setAttribute('aria-hidden','true');
    const logo=document.createElement('img');logo.src='./assets/razync-logo-original.png';logo.alt='';logo.width=40;logo.height=40;logo.decoding='async';mark.append(logo);return mark;
  }
  const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e;};
  const bankLabelUI=value=>({bb:'Banco do Brasil',itau_508:'Itaú 508',itau_509:'Itaú 509',itau_512:'Itaú 512'}[value] || (typeof bankName==='function'?bankName(value):value));
  const quantity=(n,singular,plural=singular+'s')=>`${n} ${n===1?singular:plural}`;
  const button=(text,fn)=>{const e=node('button',text,'secondary-action');e.type='button';e.addEventListener('click',fn);return e;};
  function reset(){generation++;controller?.abort();priorityController?.abort();context=null;wantsOpen=false;body.replaceChildren();workbar.replaceChildren();floating.hidden=true;launcher.hidden=true;launcher.setAttribute('aria-expanded','false');}
  function mount({prepared,company,options,summary,onState}) {
    reset();
    if(!summary?.cobertura?.pendentes){
      onState?.('complete','Nenhuma pendência para revisar');
      return;
    }
    context={prepared,company,options,onState};subtitle.textContent=`Empresa ${company} · Comparação de históricos`;
    onState?.('preparing',`${Number(summary.cobertura.pendentes).toLocaleString('pt-BR')} pendência(s) em preparação`);
    const launcherCopy=node('span',null,'base-launcher-copy');launcherCopy.append(node('small','ASSISTENTE RAZYNC'),node('strong','Revisar pendências'));launcher.replaceChildren(brandMark(),launcherCopy,node('b',String(summary.cobertura.pendentes),'base-ai-launcher-count'));launcher.title=`Revisar ${summary.cobertura.pendentes} pendências da empresa ${company}`;
    launcher.hidden=false;
    investigate(); // Local-only preparation; never consumes an AI call.
  }
  async function investigate(){
    if(!context)return;
    const current=context, version=generation;controller?.abort();controller=new AbortController();const signal=controller.signal;
    body.querySelectorAll('button').forEach(b=>b.disabled=true);
    body.replaceChildren();
    const loading=node('div',null,'base-ai-loading');loading.setAttribute('aria-busy','true');
    const symbol=brandMark();symbol.className+=' base-ai-loading-symbol';
    const status=node('p','Consultando padrões e evidências…','base-ai-loading-status');status.setAttribute('role','status');
    const orbit=node('div',null,'base-loading-orbit');orbit.append(symbol);for(let i=0;i<3;i++){const dot=node('i');dot.setAttribute('aria-hidden','true');orbit.append(dot);}loading.append(orbit,node('small','BASE INTELIGENTE','base-loading-eyebrow'),node('h3','Conectando os seus históricos'),status,node('p','Estamos preparando os exemplos e as contas da empresa para você comparar com os lançamentos pendentes.'));
    const loadingNote=node('span','Sua revisão começa pelas evidências salvas. Nenhuma conta será aprovada automaticamente.','base-loading-note');loading.append(loadingNote);
    const skeleton=node('div',null,'base-ai-skeleton');skeleton.setAttribute('aria-hidden','true');
    for(let i=0;i<4;i++)skeleton.append(node('i'));loading.append(skeleton);
    const cancel=button('Cancelar',()=>{current.onState?.('error','Preparação interrompida');controller.abort();generation++;body.replaceChildren(node('p','Preparação interrompida.'),button('Preparar novamente',investigate));workbar.replaceChildren();});loading.append(cancel);body.append(loading);
    try {
      current.blob=current.blob || await current.prepared.blob();
      if(signal.aborted || version!==generation)return;
      const data=new FormData();data.append('file',current.blob,'classificado.xlsx');data.append('options_json',JSON.stringify(current.options));data.append('usar_ia','false');
      const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/sugerir-pendentes`,{method:'POST',body:data,signal});
      if(!response.ok)throw Error(await responseError(response));
      const result=await response.json();if(signal.aborted || version!==generation)return;
      if(globalThis.crypto?.subtle){try{const hex=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(b=>b.toString(16).padStart(2,'0')).join('');current.draftKey='razync-base-draft-v1:'+await hex(await current.blob.arrayBuffer())+':'+current.company+':'+await hex(new TextEncoder().encode(JSON.stringify([current.options,result.sugestoes,result.catalogo_contas])));}catch{current.draftKey=null;}}
      if(signal.aborted || version!==generation)return;
      render(result,current,version);
      current.onState?.(result.total_pendencias?'ready':'complete',result.total_pendencias
        ? `${Number(result.total_pendencias).toLocaleString('pt-BR')} pendência(s) prontas para revisão`
        : 'Nenhuma pendência elegível para revisão');
    }catch(error){if(signal.aborted || version!==generation)return;current.onState?.('error','Não foi possível preparar a revisão');status.textContent=error.message;cancel.textContent='Tentar novamente';cancel.onclick=null;body.replaceChildren(status,button('Tentar novamente',investigate));}
  }
  const normalized=value=>String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const words=value=>new Set(normalized(value).split(' ').filter(w=>w.length>2 && !['pago','recebido','empresa','pagamento','recebimento','documento'].includes(w)));
  const periodLabel=value=>/^\d{4}-\d{2}$/.test(value)?`${value.slice(5)}/${value.slice(0,4)}`:value;
  function historyText(text,reference){
    const paragraph=node('p',null,'base-history-text'),matches=words(reference);
    for(const part of String(text || '').split(/(\s+)/)){
      if(matches.has(normalized(part)))paragraph.append(node('mark',part));
      else paragraph.append(document.createTextNode(part));
    }
    return paragraph;
  }
  function showAccountHistory(account,nature,catalog,target,pendingHistory=''){
    target.replaceChildren();
    const item=catalog.find(c=>c.conta===account.trim() && c.natureza===nature);
    if(!item){target.append(node('p','Escolha uma conta para comparar os históricos gravados.','base-comparison-empty'));return;}
    target.append(node('strong',`Conta ${item.conta}`),node('small',`${quantity(item.ocorrencias,'ocorrência')} · ${quantity(item.periodos.length,'período')} · ${item.bancos.map(bankLabelUI).join(', ')}`));
    const tokens=words(pendingHistory),score=e=>{
      const candidate=words(e.historico),common=[...candidate].filter(w=>tokens.has(w)).length;
      return normalized(e.historico)===normalized(pendingHistory)?2:common/Math.max(1,new Set([...tokens,...candidate]).size);
    };
    const examples=[...(item.exemplos || [])].sort((a,b)=>score(b)-score(a));
    const more=node('details',null,'base-more-histories');more.append(node('summary',`Ver mais ${Math.max(0,examples.length-1)} exemplos`));
    examples.forEach((example,index)=>{
      const entry=node('div',null,'base-account-history-entry');
      entry.append(node('strong',index===0?'Exemplo mais próximo pelo texto':'Outro exemplo aprendido'),historyText(example.historico,pendingHistory),node('small',`${bankLabelUI(example.banco)} · ${example.periodos.map(periodLabel).join(', ') || 'período não comprovado'} · ${quantity(example.ocorrencias,'ocorrência')}`));
      if(index===0){target.append(entry);const difference=node('p',null,'base-history-difference');
        const currentOnly=[...tokens].filter(w=>!words(example.historico).has(w)),pastOnly=[...words(example.historico)].filter(w=>!tokens.has(w));
        difference.textContent=normalized(example.historico)===normalized(pendingHistory)?'Texto igual após normalização. Isso não comprova a mesma operação.':`Diferenças de palavras: atual — ${currentOnly.join(', ') || 'nenhuma'}; exemplo — ${pastOnly.join(', ') || 'nenhuma'}. Confira números e o texto completo.`;target.append(difference);
      }else more.append(entry);
    });
    if(examples.length>1)target.append(more);
    if(!examples.length)target.append(node('p','Esta conta não possui exemplos de histórico disponíveis.'));
    target.append(node('small','Exemplos aprendidos, não um razão completo. Palavras destacadas apenas ajudam a comparação; não comprovam a mesma operação.'));
  }
  function showEvidence(suggestion,target){
    const evidence=suggestion.evidencias || [];
    const accounts=[...new Set(evidence.map(item=>item.conta))];
    const exactAccounts=[...new Set(evidence.filter(item=>item.exata).map(item=>item.conta))];
    target.replaceChildren(node('h4','Evidências que fundamentam a análise'));
    if(exactAccounts.length>1 || (accounts.length>1 && !exactAccounts.length)){
      const competingAccounts=exactAccounts.length>1?exactAccounts.length:accounts.length;
      const conflict=node('p',`Conflito: há evidências do mesmo nível para ${competingAccounts} contas diferentes. Nenhuma conta foi escolhida automaticamente.`,'base-evidence-warning');
      conflict.setAttribute('role','note');target.append(conflict);
    }else if(accounts.length>1 && exactAccounts.length===1){
      target.append(node('p','Há outras contas apenas em históricos semelhantes; isso não equivale a uma correspondência exata. Confira os exemplos antes de decidir.','base-evidence-warning'));
    }else if(!evidence.length){
      target.append(node('p','Não há evidência histórica compatível para este lançamento.','base-evidence-empty'));
    }else if(!suggestion.conta_sugerida){
      target.append(node('p','Candidatos do histórico para conferência; nenhum foi escolhido.','base-evidence-warning'));
    }
    for(const item of evidence){
      const card=node('article',null,'base-evidence-card');
      const heading=node('strong',`Conta ${item.conta}`);card.append(heading);
      const badges=node('div',null,'base-evidence-badges');
      badges.append(node('span',item.exata?'Assinatura exata':'Histórico semelhante',item.exata?'is-exact':'is-similar'));
      badges.append(node('span',item.mesmo_banco?'Mesmo banco':'Outro banco',item.mesmo_banco?'is-same-bank':'is-other-bank'));
      card.append(badges);
      const periods=(item.periodos || []).map(periodLabel);
      card.append(node('small',`${bankLabelUI(item.banco)} · ${periods.length?periods.join(', '):'período não comprovado'}`));
      card.append(node('small',quantity(Number(item.ocorrencias)||0,'ocorrência')));
      for(const history of item.historicos || [])card.append(historyText(history,suggestion['Histórico']));
      target.append(card);
    }
    target.append(node('small','O histórico não confirma se a conta continua ativa no plano atual nem comprova, por si só, a operação.'));
  }
  function render(result,current,version){
    body.replaceChildren();workbar.replaceChildren();
    if(!result.total_pendencias){body.append(node('h3','Nenhuma pendência elegível neste perfil.'));return;}
    const intro=node('div',null,'base-review-intro'),progress=node('p',null,'base-review-progress');
    intro.append(node('h3','Compare e revise'));body.append(intro);progress.setAttribute('role','status');progress.setAttribute('aria-live','polite');workbar.append(progress);
    const aiStatus=node('p','Comparação pelos padrões salvos. A IA opcional apenas organiza a fila; não escolhe nem aprova contas.','base-review-status');aiStatus.setAttribute('role','status');
    const aiButton=button('Priorizar casos com IA',async()=>{
      aiButton.disabled=true;priorityController=new AbortController();const signal=priorityController.signal;
      aiBar.setAttribute('aria-busy','true');aiStatus.textContent='Priorizando casos ambíguos. Você pode continuar comparando os históricos.';
      const data=new FormData();data.append('file',current.blob,'classificado.xlsx');data.append('options_json',JSON.stringify(current.options));data.append('usar_ia','true');
      try{
        const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/sugerir-pendentes`,{method:'POST',body:data,signal});
        if(!response.ok)throw Error(await responseError(response));
        const prioritized=await response.json();if(signal.aborted || version!==generation || completed)return;
        // Preserve every draft and approval. Only reorder the navigation queue.
        const ids=new Set(prioritized.ia?.prioridades || []);
        controls.sort((a,b)=>Number(ids.has(b.s.grupo))-Number(ids.has(a.s.grupo)));
        aiStatus.textContent=prioritized.ia?.motivo || 'Prioridade mantida pelas evidências locais.';updateQueue();
      }catch(error){if(!signal.aborted && version===generation)aiStatus.textContent=error.message;}finally{if(version===generation)aiBar.setAttribute('aria-busy','false');}
    });
    const aiBar=node('div',null,'base-review-ai');aiBar.append(aiStatus,aiButton);
    const controls=[],catalog=result.catalogo_contas || [],priority=new Set(result.ia?.prioridades || []);
    const candidateAccounts=s=>[...new Set([s.conta_sugerida,...(s.evidencias || []).map(e=>e.conta)].filter(Boolean))];
    const category=s=>s.conta_sugerida?'single':candidateAccounts(s).length>1?'conflict':candidateAccounts(s).length===1?'single':'none';
    const rank=s=>({single:0,conflict:1,none:2})[category(s)];
    const suggestions=[...result.sugestoes].sort((a,b)=>rank(a)-rank(b) || Number(priority.has(b.grupo))-Number(priority.has(a.grupo)));
    let active=null,filter='all',query='',grouped=true,completed=false,applying=false;
    const search=document.createElement('input');search.type='search';search.placeholder='Pesquisar histórico, banco, conta ou valor';search.setAttribute('aria-label','Pesquisar pendências');
    search.addEventListener('input',()=>{query=normalized(search.value);updateQueue();showDetail();});
    const groupToggle=button('Agrupar equivalentes',()=>{grouped=!grouped;groupToggle.setAttribute('aria-pressed',String(grouped));updateQueue();showDetail();});groupToggle.setAttribute('aria-pressed','true');
    const tools=node('div',null,'base-queue-tools');tools.append(search,groupToggle);
    const filters=node('div',null,'base-review-filters'),filterButtons=[];
    for(const [value,label] of [['all','Todas'],['single','Conta candidata única'],['conflict','Contas conflitantes'],['none','Sem histórico'],['deferred','Adiadas'],['approved','Aprovadas']]){
      const control=button(label,()=>{filter=value;updateQueue();showDetail();});control.setAttribute('aria-pressed',String(value==='all'));filters.append(control);filterButtons.push({value,label,control});
    }

    const layout=node('div',null,'base-review-layout'),queue=node('nav',null,'base-review-queue'),detail=node('section',null,'base-review-detail');
    queue.setAttribute('aria-label','Pendências para revisar');detail.setAttribute('aria-label','Comparação do lançamento com a base');const sidebar=node('aside',null,'base-review-sidebar');sidebar.setAttribute('aria-label','Pesquisar e filtrar pendências');sidebar.append(node('h3','Sua fila de revisão'),tools,filters,queue);layout.append(sidebar,detail);body.append(layout);
    let draftEnabled=false;
    function saveDraft(){if(!draftEnabled || !current.draftKey || completed || applying)return;try{sessionStorage.setItem(current.draftKey,JSON.stringify({time:Date.now(),rows:controls.map(c=>({key:rowKey(c),account:c.account.value,approved:c.select.checked,deferred:c.deferred}))}));}catch{}}
    const message=node('p',null,'helper');message.setAttribute('role','status');
    const matchesFilter=(c,value)=>value==='all' || value==='approved' && c.select.checked || value==='deferred' && c.deferred && !c.select.checked || category(c.s)===value;
    const matchesSearch=c=>!query || normalized([c.s['Histórico'],c.s._aba,c.account.value,c.s.Valor,String(c.s.Valor).replace('.',','),Number(c.s.Valor).toLocaleString('pt-BR',{minimumFractionDigits:2}),c.s.Data].join(' ')).includes(query);
    const visible=()=>controls.filter(c=>matchesFilter(c,filter) && matchesSearch(c));
    const rowKey=c=>`${c.s._aba}:${c.s._linha}`;
    function groupKey(c){return Number.isInteger(c.s.grupo) && c.s._banco && c.s.assinatura?JSON.stringify([c.s.grupo,c.s._banco,c.s.natureza,c.s.assinatura,normalized(c.s['Histórico'])]):rowKey(c);}
    function queueGroups(items){
      const groups=new Map();for(const c of items){const key=grouped?groupKey(c):rowKey(c);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(c);}return [...groups.values()];
    }
    function validAccount(c){return catalog.some(item=>item.conta===c.account.value.trim() && item.natureza===c.s.natureza);}
    function drawHistory(c){showAccountHistory(c.account.value,c.s.natureza,catalog,c.historyArea,c.s['Histórico']);}
    function refreshEvidence(c){
      if(!c.summary)return;
      if(c.approval && !c.select.checked)c.approval.replaceChildren(node('small',c.deferred?'Adiada para conferir depois.':'Confira a conta e use Aprovar e próximo.'));
      if(c.grade){c.grade.textContent=c.account.value.trim() && c.account.value.trim()!==c.s.conta_sugerida?'Conta escolhida para conferir':c.originalGrade;}
      const account=c.account.value.trim(),s=c.s;
      const matching=(s.evidencias || []).filter(e=>e.conta===account);
      const periods=new Set(matching.flatMap(e=>e.periodos || []));
      const suggested=Boolean(account && s.conta_sugerida===account);
      c.summary.replaceChildren(node('strong',account?`${suggested?'Conta sugerida':'Conta em comparação'}: ${account}`:'Escolha uma conta para comparar'));
      if(matching.length)c.summary.append(node('small',`${quantity(periods.size,'período')} · ${matching.some(e=>e.mesmo_banco)?'há evidência no mesmo banco':'evidências em outro banco'}`));
      else if(account)c.summary.append(node('small','Sem evidência específica para este lançamento. Confira os exemplos da conta ao lado.'));
      const reason=node('p',pendingReason(s),'base-pending-reason');c.summary.append(reason);
      const explanation=node('details');explanation.append(node('summary','Ver justificativa original'),node('p',s.justificativa));c.summary.append(explanation);
    }
    function pendingReason(s){
      const exact=(s.evidencias || []).filter(e=>e.exata),accounts=new Set(exact.map(e=>e.conta));
      if(accounts.size>1)return 'Precisa de decisão: a mesma assinatura aparece em contas diferentes.';
      if(!s.evidencias?.length)return 'Sem histórico compatível: escolha uma conta após conferir a operação.';
      if(!exact.length)return 'Somente textos semelhantes: a semelhança não basta para classificar automaticamente.';
      const periods=new Set(exact.filter(e=>e.mesmo_banco).flatMap(e=>e.periodos || []));
      if(!exact.some(e=>e.mesmo_banco))return 'A correspondência exata vem de outro banco; confira a contrapartida.';
      if(periods.size<3)return `Assinatura exata em ${quantity(periods.size,'período')} no mesmo banco. Ainda exige confirmação; confira as datas dos exemplos.`;
      return 'Há evidências históricas, mas esta linha permaneceu pendente no classificador. Confira a justificativa antes de decidir.';
    }
    function equivalents(c){
      if(!Number.isInteger(c.s.grupo) || !c.s._banco || !c.s.assinatura)return [];
      return controls.filter(other=>other.s.grupo===c.s.grupo && other.s._banco===c.s._banco && other.s.natureza===c.s.natureza && other.s.assinatura===c.s.assinatura && normalized(other.s['Histórico'])===normalized(c.s['Histórico']));
    }
    function go(step,markReviewed=false,preferPending=false){
      if(!active)return;
      if(markReviewed){active.deferred=true;active.reviewed=false;}
      const items=visible(),index=items.indexOf(active);
      const ordered=items.map((_,offset)=>items[(index+step+offset+items.length)%items.length]);
      active=(preferPending?ordered.find(c=>!c.select.checked):ordered[0]) || active;updateQueue();showDetail();
    }
    function approveActive(){
      if(!active || active.select.checked || completed || applying)return;
      if(!validAccount(active)){message.textContent='Escolha uma conta histórica compatível antes de aprovar.';active.account.focus();return;}
      active.select.checked=true;active.reviewed=true;active.deferred=false;
      message.textContent='Aprovação registrada para o Excel. Nenhum aprendizado foi gravado.';go(1,false,true);
    }
    const quickActions=node('div',null,'base-workbar-actions');
    const skipTop=button('Adiar',()=>go(1,true)),approveTop=button('Aprovar e próximo',approveActive);
    approveTop.className='base-review-confirm';workbar.append(quickActions);
    function updateQueue(){
      queue.replaceChildren();const items=visible();if(!items.includes(active))active=items[0] || null;
      const approved=controls.filter(c=>c.select.checked).length;
      progress.textContent=`${quantity(approved,'aprovado')} · ${quantity(controls.filter(c=>c.deferred && !c.select.checked).length,'adiado')} · ${quantity(controls.filter(c=>!c.select.checked && !c.deferred).length,'pendente')} · ${completed?quantity(approved,'revisão aplicada','revisões aplicadas'):`${approved} para aplicar`}`;approveTop.disabled=!active || active.select.checked || !validAccount(active) || completed || applying;skipTop.disabled=!active || active.select.checked || completed || applying;
      if(typeof apply!=='undefined'){apply.textContent=completed?'Revisões aplicadas':`Gerar Excel com ${quantity(approved,'revisão','revisões')}`;apply.disabled=completed || applying || !approved;}
      filterButtons.forEach(f=>{f.control.setAttribute('aria-pressed',String(filter===f.value));const count=controls.filter(c=>matchesFilter(c,f.value) && matchesSearch(c)).length;f.control.replaceChildren(node('span',f.label),node('b',String(count),'base-filter-count'));});
      saveDraft();
      if(!items.length){queue.append(node('p','Nenhuma pendência neste filtro.'));return;}
      for(const group of queueGroups(items)){
        const groupValue=group.reduce((sum,item)=>sum+Math.round(Number(item.s.Valor)*100),0)/100;
        const c=group.includes(active)?active:group.find(item=>!item.select.checked && !item.deferred) || group[0];
        const entry=button('',()=>{active=c;updateQueue();showDetail();});entry.className='base-review-item';entry.setAttribute('data-review-state',c.select.checked?'approved':c.deferred?'deferred':'pending');entry.setAttribute('aria-pressed',String(c===active));entry.setAttribute('aria-label',`Comparar ${c.s._aba}, linha ${c.s._linha}`);
        entry.append(node('strong',`${c.select.checked?'✓ ':''}${c.s._aba} · linha ${c.s._linha}`),node('span',c.s['Histórico']),node('small',`${group.length>1?quantity(group.length,'lançamento')+' · Total ':''}${groupValue.toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}`),node('small',c.select.checked?'Aprovada':c.deferred?'Adiada':c.account.value?`${c.s.conta_sugerida===c.account.value?'Sugestão':'Conta em revisão'}: ${c.account.value}`:'Escolher conta'));queue.append(entry);
      }
    }
    function showDetail(){
      detail.replaceChildren();if(!active){detail.append(node('p','Selecione outra opção nos filtros para continuar.'));return;}
      const c=active,s=c.s;
      const position=visible().indexOf(c)+1;
      detail.append(node('small',`${position} de ${quantity(visible().length,'lançamento')} · ${quantity(queueGroups(visible()).length,'item na fila','itens na fila')}`));
      const comparison=node('div',null,'base-history-comparison'),received=node('section',null,'base-history-received'),saved=node('section',null,'base-history-saved');
      received.append(node('h4','Lançamento para revisar'),historyText(s['Histórico'],(s.evidencias || []).flatMap(e=>e.historicos || []).join(' ')),node('small',`${s.Data} · ${Number(s.Valor).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}`),node('small',`${s._aba} · linha ${s._linha} · ${s.natureza==='pago'?'Pagamento / débito':'Recebimento / crédito'}`));
      const grade=s.situacao==='MANUAL'?({single:'Similaridade a conferir',conflict:'Contas conflitantes',none:'Sem histórico compatível'})[category(s)]:({FORTE:'Sugestão forte',MODERADA:'Sugestão moderada'})[s.situacao];
      const gradeBadge=node('span',grade,'base-investigation-grade');gradeBadge.setAttribute('data-grade',s.situacao);c.grade=gradeBadge;c.originalGrade=grade;received.append(gradeBadge);
      c.summary=node('div',null,'base-evidence-summary');refreshEvidence(c);received.append(c.summary);
      const evidencePanel=node('details',null,'base-evidence-list');evidencePanel.append(node('summary','Ver todas as evidências'));const evidenceBody=node('div');showEvidence(s,evidenceBody);evidencePanel.append(evidenceBody);received.append(evidencePanel);
      const candidates=node('div',null,'base-account-candidates');
      for(const account of [...new Set((s.evidencias || []).map(e=>e.conta))]){
        const pick=button(`Comparar conta ${account}`,()=>{if(completed || applying)return;c.account.value=account;c.select.checked=false;c.deferred=false;drawHistory(c);refreshEvidence(c);updateQueue();if(active!==c)showDetail();});pick.disabled=completed || applying;candidates.append(pick);
      }
      if(s.evidencias.length)received.append(candidates);
      const label=node('label','Conta de contrapartida');label.append(c.account);const decision=node('div',null,'base-review-decision');decision.append(label,c.list);detail.append(decision);
      const approval=node('div',null,'base-review-approval');c.approval=approval;
      if(c.select.checked){approval.append(node('strong','✓ Conta aprovada'));const undo=button('Desfazer aprovação',()=>{c.select.checked=false;updateQueue();showDetail();});undo.disabled=completed || applying;approval.append(undo);}
      else approval.append(node('small',c.deferred?'Adiada para conferir depois.':'Confira a conta e use Aprovar e próximo.'));decision.append(approval);
      saved.append(node('h4','Históricos gravados na conta'),c.historyArea);drawHistory(c);
      comparison.append(received,saved);
      const actions=node('div',null,'base-review-navigation');
      actions.append(button('Anterior',()=>go(-1)),button('Próximo',()=>go(1)),skipTop,approveTop);decision.append(actions);
      const members=equivalents(c).filter(other=>!other.select.checked);
      if(members.length>1){
        const groupBox=node('section',null,'base-group-review');groupBox.hidden=true;
        const groupOpen=button(`Revisar ${members.length} equivalentes`,()=>{
          groupBox.replaceChildren();groupBox.hidden=false;
          if(!validAccount(c)){groupBox.append(node('p','Escolha uma conta histórica antes de revisar o grupo.'));return;}
          const account=c.account.value.trim();
          groupBox.append(node('strong',`Usar a conta ${account} nas linhas selecionadas`),node('p','Mesmo grupo, banco, natureza e assinatura. Confira cada linha; nenhuma aprovação acontece ao abrir esta lista.'));
          const selections=[];
          for(const other of members){
            const include=document.createElement('input');include.type='checkbox';include.checked=!other.account.value || other.account.value.trim()===account;
            include.setAttribute('aria-label',`Incluir ${other.s._aba}, linha ${other.s._linha} no grupo`);
            const row=node('label');row.append(include,node('span',`${other.s._aba} · linha ${other.s._linha} · ${other.s.Data} · ${Number(other.s.Valor).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}`),node('small',other.s['Histórico']));
            if(other.account.value && other.account.value!==account)row.append(node('small',`Conta em revisão diferente: ${other.account.value}. Linha desmarcada.`));
            groupBox.append(row);selections.push({other,include});
          }
          const confirm=button('Aprovar linhas selecionadas',()=>{
            if(completed || applying)return;
            const chosen=selections.filter(item=>item.include.checked);
            if(c.account.value.trim()!==account){message.textContent='A conta mudou. Abra novamente a revisão do grupo.';return;}
            if(!chosen.length){message.textContent='Selecione pelo menos uma linha do grupo.';return;}
            const eligible=new Set(equivalents(c));
            if(chosen.some(item=>!eligible.has(item.other) || item.other.select.checked)){message.textContent='O grupo mudou. Confira a seleção novamente.';return;}
            for(const {other} of chosen){other.account.value=account;other.select.checked=true;other.reviewed=true;other.deferred=false;}
            message.textContent=`${chosen.length} aprovações registradas. O Excel e o aprendizado só mudam no comando final.`;
            active=controls.find(other=>!other.select.checked) || active;updateQueue();showDetail();
          });confirm.disabled=completed || applying;groupBox.append(confirm,button('Fechar grupo',()=>{groupBox.hidden=true;}));
        });groupOpen.disabled=completed || applying;actions.append(groupOpen);detail.append(groupBox,comparison);
      }else detail.append(comparison);
    }
    for(const s of suggestions){
      const select=document.createElement('input');select.type='checkbox';select.setAttribute('aria-label',`Aprovar ${s._aba}, linha ${s._linha}`);
      const account=document.createElement('input');account.type='text';account.inputMode='numeric';account.value=s.conta_sugerida;account.maxLength=15;account.placeholder='Escolha ou digite a conta';account.setAttribute('aria-label',`Conta para ${s._aba}, linha ${s._linha}`);
      const list=document.createElement('datalist');list.id=`baseAccounts-${s._linha}-${controls.length}`;account.setAttribute('list',list.id);
      for(const item of catalog){if(item.natureza!==s.natureza)continue;const option=document.createElement('option');option.value=item.conta;option.label=`${item.bancos.map(bankLabelUI).join(', ')} · ${quantity(item.periodos.length,'período')}`;list.append(option);}
      const historyArea=node('div',null,'base-account-history');const control={s,select,account,list,historyArea,reviewed:false,deferred:false};controls.push(control);
      account.addEventListener('input',()=>{select.checked=false;control.reviewed=false;control.deferred=false;drawHistory(control);refreshEvidence(control);updateQueue();if(active!==control)showDetail();});
      account.addEventListener('change',()=>{drawHistory(control);});
      select.addEventListener('change',()=>{if(select.checked && !validAccount(control)){select.checked=false;message.textContent='Escolha uma conta histórica compatível antes de aprovar.';}updateQueue();});
    }
    active=controls[0];
    const notice=node('p',result.limitacoes.join(' '),'base-review-limitations');const assistance=node('details',null,'base-review-options');assistance.append(node('summary','Sobre a comparação e a IA opcional'),notice,aiBar);body.append(assistance);
    const learn=document.createElement('input');learn.type='checkbox';learn.checked=false;const label=node('label',null,'base-investigation-learn');label.append(learn,document.createTextNode(' Aprender na Base Inteligente somente as revisões aprovadas'));body.append(label);
    const footer=node('div',null,'base-review-footer');
    const apply=button('Aplicar revisões e atualizar Excel',async()=>{
      const revisions=controls.filter(c=>c.select.checked).map(c=>({_aba:c.s._aba,_linha:c.s._linha,'Conta da contrapartida':c.account.value.trim()}));
      if(!revisions.length){message.textContent='Selecione as linhas que você revisou e deseja aprovar.';return;}
      if(revisions.some(r=>!/^\d+$/.test(r['Conta da contrapartida']))){message.textContent='Informe a conta contábil de todas as linhas aprovadas.';return;}
      const remember=learn.checked;applying=true;controls.forEach(c=>{c.select.disabled=true;c.account.disabled=true;});learn.disabled=true;priorityController?.abort();aiButton.disabled=true;apply.disabled=true;updateQueue();controller=new AbortController();const signal=controller.signal;message.textContent='Validando revisões e gerando Excel…';
      const data=new FormData();data.append('file',current.blob,'classificado.xlsx');data.append('revisoes_json',JSON.stringify(revisions));data.append('investigacao_token',result.token);data.append('aprender',String(remember));
      try{
        const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/revisar`,{method:'POST',body:data,signal});
        if(!response.ok)throw Error(await responseError(response));
        const summary=JSON.parse(response.headers.get('x-razync-summary') || '{}');const blob=await response.blob();
        if(signal.aborted || version!==generation)return;
        // Freeze the completed approval, preventing accidental repeated learning.
        controls.forEach(c=>{c.select.disabled=true;c.account.disabled=true;});learn.disabled=true;apply.disabled=true;aiButton.disabled=true;priorityController?.abort();
        completed=true;try{if(current.draftKey)sessionStorage.removeItem(current.draftKey);}catch{}updateQueue();showDetail();
        renderClassificationCoverage(summary.cobertura);
        message.textContent=`Revisões aplicadas: ${summary.aplicadas}. Padrões aprendidos: ${summary.aprendizados || 0}.`;
        current.onState?.('complete',`${Number(summary.aplicadas)||0} revisão(ões) aplicada(s)`);
        const download=button('Baixar Excel revisado',()=>downloadBlob(new Response(blob),`RAZYNC_${current.company}_REVISADO.xlsx`));download.className='preview-download';footer.append(download);
        const previewBody=new FormData();previewBody.append('file',blob,'revisado.xlsx');
        const previewResponse=await fetch(`${API()}/api/v1/modelo-preview`,{method:'POST',body:previewBody,signal});
        if(signal.aborted || version!==generation)return;
        if(previewResponse.ok)showWorkflowPreview(await previewResponse.json(),document.querySelector('#classificationPreview'));
      }catch(error){if(signal.aborted || version!==generation)return;message.textContent=completed?'Excel revisado gerado. A prévia não pôde ser atualizada; use Baixar Excel revisado.':error.message;if(!completed){applying=false;controls.forEach(c=>{c.select.disabled=false;c.account.disabled=false;});learn.disabled=false;updateQueue();showDetail();}}
    });quickActions.append(apply);footer.append(message);body.append(footer);
    let priorDraft;try{priorDraft=JSON.parse(sessionStorage.getItem(current.draftKey));}catch{}
    if(current.draftKey && priorDraft?.rows?.length && Date.now()-priorDraft.time<86400000){
      const resume=node('div',null,'base-draft-notice');resume.append(node('p','Há uma revisão salva nesta aba para este arquivo e estas evidências. Nenhum Excel será alterado ao retomá-la.'),button('Retomar revisão salva',()=>{
        const rows=new Map(priorDraft.rows.map(row=>[row.key,row]));
        for(const c of controls){const row=rows.get(rowKey(c));if(!row)continue;c.account.value=String(row.account || '');c.select.checked=Boolean(row.approved && validAccount(c));c.deferred=Boolean(row.deferred && !c.select.checked);}
        draftEnabled=true;resume.hidden=true;updateQueue();showDetail();
      }),button('Começar nova revisão',()=>{draftEnabled=true;resume.hidden=true;saveDraft();}));body.prepend(resume);
    }else draftEnabled=true;
    updateQueue();showDetail();
  }
  globalThis.RazyncBaseInvestigation={mount,open:openOrInvestigate,reset};
})();
