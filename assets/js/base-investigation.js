/* Optional investigation of the exact classified result, never the original upload. */
(() => {
  let context, controller, priorityController, generation=0, wantsOpen=false;
  const launcher=document.createElement('button');launcher.type='button';launcher.className='base-ai-launcher';launcher.hidden=true;
  launcher.textContent='Revisar pendências';launcher.setAttribute('aria-label','Revisar pendências da Base Inteligente');launcher.setAttribute('aria-controls','baseInvestigationWindow');launcher.setAttribute('aria-expanded','false');
  const floating=document.createElement('section');floating.id='baseInvestigationWindow';floating.className='base-ai-window';floating.hidden=true;
  floating.setAttribute('role','region');floating.setAttribute('aria-label','Assistente da Base Inteligente');
  const windowHeader=document.createElement('header');windowHeader.className='base-ai-window-header';
  const identity=document.createElement('div');const windowTitle=document.createElement('strong');windowTitle.textContent='✦ Assistente da Base';
  const subtitle=document.createElement('small');subtitle.textContent='Histórico, evidências e revisão';identity.append(windowTitle,subtitle);
  const windowActions=document.createElement('div');windowActions.className='base-ai-window-actions';
  const expand=document.createElement('button');expand.type='button';expand.textContent='⤢';expand.setAttribute('aria-label','Ampliar assistente');expand.setAttribute('aria-pressed','false');
  const minimize=document.createElement('button');minimize.type='button';minimize.textContent='−';minimize.setAttribute('aria-label','Minimizar assistente');
  windowActions.append(expand,minimize);windowHeader.append(identity,windowActions);
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
  const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e;};
  const bankLabelUI=value=>({bb:'Banco do Brasil',itau_508:'Itaú 508',itau_509:'Itaú 509',itau_512:'Itaú 512'}[value] || (typeof bankName==='function'?bankName(value):value));
  const quantity=(n,singular,plural=singular+'s')=>`${n} ${n===1?singular:plural}`;
  const button=(text,fn)=>{const e=node('button',text,'secondary-action');e.type='button';e.addEventListener('click',fn);return e;};
  function reset(){generation++;controller?.abort();priorityController?.abort();context=null;wantsOpen=false;body.replaceChildren();floating.hidden=true;launcher.hidden=true;launcher.setAttribute('aria-expanded','false');}
  function mount({prepared,company,options,summary}) {
    reset();if(!summary?.cobertura?.pendentes)return;
    context={prepared,company,options};
    launcher.replaceChildren(node('span','✦','base-ai-launcher-icon'),node('span','Revisar pendências'),node('b',String(summary.cobertura.pendentes),'base-ai-launcher-count'));
    launcher.hidden=false;
  }
  async function investigate(){
    if(!context)return;
    const current=context, version=generation;controller?.abort();controller=new AbortController();const signal=controller.signal;
    body.querySelectorAll('button').forEach(b=>b.disabled=true);
    body.replaceChildren();
    const status=node('p','Consultando padrões e evidências…','helper');status.setAttribute('role','status');
    const cancel=button('Cancelar',()=>{controller.abort();mount({...current,summary:{cobertura:{pendentes:1}}});});body.append(status,cancel);
    try {
      current.blob=current.blob || await current.prepared.blob();
      if(signal.aborted || version!==generation)return;
      const data=new FormData();data.append('file',current.blob,'classificado.xlsx');data.append('options_json',JSON.stringify(current.options));data.append('usar_ia','false');
      const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/sugerir-pendentes`,{method:'POST',body:data,signal});
      if(!response.ok)throw Error(await responseError(response));
      const result=await response.json();if(signal.aborted || version!==generation)return;
      render(result,current,version);
    }catch(error){if(signal.aborted || version!==generation)return;status.textContent=error.message;cancel.textContent='Tentar novamente';cancel.onclick=null;body.replaceChildren(status,button('Tentar novamente',investigate));}
  }
  const normalized=value=>String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const words=value=>new Set(normalized(value).split(' ').filter(w=>w.length>2 && !['pago','recebido','empresa','pagamento','recebimento','documento'].includes(w)));
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
    const tokens=words(pendingHistory),score=e=>[...words(e.historico)].filter(w=>tokens.has(w)).length;
    const examples=[...(item.exemplos || [])].sort((a,b)=>score(b)-score(a));
    for(const example of examples){
      const entry=node('div',null,'base-account-history-entry');
      entry.append(historyText(example.historico,pendingHistory),node('small',`${bankLabelUI(example.banco)} · ${example.periodos.join(', ') || 'período não comprovado'} · ${quantity(example.ocorrencias,'ocorrência')}`));target.append(entry);
    }
    if(!examples.length)target.append(node('p','Esta conta não possui exemplos de histórico disponíveis.'));
    target.append(node('small','Exemplos aprendidos, não um razão completo. Palavras destacadas apenas ajudam a comparação; não comprovam a mesma operação.'));
  }
  function render(result,current,version){
    body.replaceChildren();
    if(!result.total_pendencias){body.append(node('h3','Nenhuma pendência elegível neste perfil.'));return;}
    const intro=node('div',null,'base-review-intro'),progress=node('p',null,'base-review-progress');
    intro.append(node('h3','Compare e revise'),progress);body.append(intro);
    const aiStatus=node('p','Históricos consultados na base da empresa. A comparação não precisa esperar pela IA.','base-review-status');aiStatus.setAttribute('role','status');
    const aiButton=button('Priorizar casos com IA',async()=>{
      aiButton.disabled=true;priorityController=new AbortController();const signal=priorityController.signal;
      aiStatus.textContent='Priorizando casos ambíguos. Você pode continuar comparando os históricos.';
      const data=new FormData();data.append('file',current.blob,'classificado.xlsx');data.append('options_json',JSON.stringify(current.options));data.append('usar_ia','true');
      try{
        const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/sugerir-pendentes`,{method:'POST',body:data,signal});
        if(!response.ok)throw Error(await responseError(response));
        const prioritized=await response.json();if(signal.aborted || version!==generation || completed)return;
        // Preserve every draft and approval. Only reorder the navigation queue.
        const ids=new Set(prioritized.ia?.prioridades || []);
        controls.sort((a,b)=>Number(ids.has(b.s.grupo))-Number(ids.has(a.s.grupo)));
        aiStatus.textContent=prioritized.ia?.motivo || 'Prioridade mantida pelas evidências locais.';updateQueue();
      }catch(error){if(!signal.aborted && version===generation)aiStatus.textContent=error.message;}
    });
    const aiBar=node('div',null,'base-review-ai');aiBar.append(aiStatus,aiButton);body.append(aiBar);
    const controls=[],catalog=result.catalogo_contas || [],priority=new Set(result.ia?.prioridades || []);
    const suggestions=[...result.sugestoes].sort((a,b)=>Number(priority.has(b.grupo))-Number(priority.has(a.grupo)));
    let active=null,filter='all',completed=false,applying=false;
    const filters=node('div',null,'base-review-filters'),filterButtons=[];
    for(const [value,label] of [['all','Todas'],['suggested','Com sugestão'],['manual','Sem sugestão'],['approved','Aprovadas']]){
      const control=button(label,()=>{filter=value;updateQueue();showDetail();});control.setAttribute('aria-pressed',String(value==='all'));filters.append(control);filterButtons.push({value,control});
    }
    body.append(filters);
    const layout=node('div',null,'base-review-layout'),queue=node('nav',null,'base-review-queue'),detail=node('section',null,'base-review-detail');
    queue.setAttribute('aria-label','Pendências para revisar');detail.setAttribute('aria-label','Comparação do lançamento com a base');layout.append(queue,detail);body.append(layout);
    const message=node('p',null,'helper');message.setAttribute('role','status');
    const visible=()=>controls.filter(c=>filter==='all' || filter==='approved' && c.select.checked || filter==='suggested' && Boolean(c.s.conta_sugerida) || filter==='manual' && !c.s.conta_sugerida);
    function validAccount(c){return catalog.some(item=>item.conta===c.account.value.trim() && item.natureza===c.s.natureza);}
    function drawHistory(c){showAccountHistory(c.account.value,c.s.natureza,catalog,c.historyArea,c.s['Histórico']);}
    function updateQueue(){
      queue.replaceChildren();const items=visible();if(!items.includes(active))active=items[0] || null;
      const approved=controls.filter(c=>c.select.checked).length;
      progress.textContent=`${quantity(controls.length,'pendência')} · aprovações: ${approved} · ${quantity(result.grupos_investigados,'grupo')}`;
      if(typeof apply!=='undefined'){apply.textContent=completed?'Revisões aplicadas':`Gerar Excel com ${quantity(approved,'revisão','revisões')}`;apply.disabled=completed || applying || !approved;}
      filterButtons.forEach(f=>f.control.setAttribute('aria-pressed',String(filter===f.value)));
      if(!items.length){queue.append(node('p','Nenhuma pendência neste filtro.'));return;}
      for(const c of items){
        const entry=button('',()=>{active=c;updateQueue();showDetail();});entry.className='base-review-item';entry.setAttribute('aria-pressed',String(c===active));entry.setAttribute('aria-label',`Comparar ${c.s._aba}, linha ${c.s._linha}`);
        entry.append(node('strong',`${c.select.checked?'✓ ':''}${c.s._aba} · linha ${c.s._linha}`),node('span',c.s['Histórico']),node('small',c.select.checked?'Aprovada':c.account.value?`${c.s.conta_sugerida===c.account.value?'Sugestão':'Conta em revisão'}: ${c.account.value}`:'Escolher conta'));queue.append(entry);
      }
    }
    function showDetail(){
      detail.replaceChildren();if(!active){detail.append(node('p','Selecione outra opção nos filtros para continuar.'));return;}
      const c=active,s=c.s;
      const position=visible().indexOf(c)+1;
      detail.append(node('small',`${position} de ${visible().length} nesta seleção`));
      const comparison=node('div',null,'base-history-comparison'),received=node('section',null,'base-history-received'),saved=node('section',null,'base-history-saved');
      received.append(node('h4','Lançamento para revisar'),historyText(s['Histórico'],(s.evidencias || []).flatMap(e=>e.historicos || []).join(' ')),node('small',`${s.Data} · ${Number(s.Valor).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}`),node('small',`${s._aba} · linha ${s._linha} · ${s.natureza==='pago'?'Pagamento / débito':'Recebimento / crédito'}`));
      const grade=({FORTE:'Sugestão forte',MODERADA:'Sugestão moderada',MANUAL:'Revisão manual'})[s.situacao];
      received.append(node('span',grade,'base-investigation-grade'),node('p',s.justificativa));
      const candidates=node('div',null,'base-account-candidates');
      for(const account of [...new Set((s.evidencias || []).map(e=>e.conta))]){
        const pick=button(`Comparar conta ${account}`,()=>{if(completed || applying)return;c.account.value=account;c.select.checked=false;drawHistory(c);updateQueue();if(active!==c)showDetail();});pick.disabled=completed || applying;candidates.append(pick);
      }
      if(s.evidencias.length)received.append(candidates);
      const label=node('label','Conta de contrapartida');label.append(c.account);received.append(label,c.list);
      const approval=node('label',null,'base-review-approval');approval.append(c.select,document.createTextNode(' Aprovar este lançamento'));received.append(approval);
      saved.append(node('h4','Históricos gravados na conta'),c.historyArea);drawHistory(c);
      comparison.append(received,saved);detail.append(comparison);
      const actions=node('div',null,'base-review-navigation');
      const go=step=>{const items=visible(),i=items.indexOf(active);active=items[(i+step+items.length)%items.length];updateQueue();showDetail();};
      actions.append(button('Anterior',()=>go(-1)),button('Pular / próximo',()=>go(1)));
      const approveNext=button('Aprovar e próximo',()=>{if(!validAccount(c)){message.textContent='Escolha uma conta histórica compatível antes de aprovar.';return;}c.select.checked=true;message.textContent='Aprovação registrada para o Excel. Nenhum aprendizado foi gravado.';go(1);});approveNext.disabled=completed || applying;actions.append(approveNext);detail.append(actions);
    }
    for(const s of suggestions){
      const select=document.createElement('input');select.type='checkbox';select.setAttribute('aria-label',`Aprovar ${s._aba}, linha ${s._linha}`);
      const account=document.createElement('input');account.type='text';account.inputMode='numeric';account.value=s.conta_sugerida;account.maxLength=15;account.placeholder='Escolha ou digite a conta';account.setAttribute('aria-label',`Conta para ${s._aba}, linha ${s._linha}`);
      const list=document.createElement('datalist');list.id=`baseAccounts-${s._linha}-${controls.length}`;account.setAttribute('list',list.id);
      for(const item of catalog){if(item.natureza!==s.natureza)continue;const option=document.createElement('option');option.value=item.conta;option.label=`${item.bancos.map(bankLabelUI).join(', ')} · ${quantity(item.periodos.length,'período')}`;list.append(option);}
      const historyArea=node('div',null,'base-account-history');const control={s,select,account,list,historyArea};controls.push(control);
      account.addEventListener('input',()=>{select.checked=false;drawHistory(control);updateQueue();if(active!==control)showDetail();});
      account.addEventListener('change',()=>{drawHistory(control);});
      select.addEventListener('change',()=>{if(select.checked && !validAccount(control)){select.checked=false;message.textContent='Escolha uma conta histórica compatível antes de aprovar.';}updateQueue();});
    }
    active=controls[0];
    const notice=node('p',result.limitacoes.join(' '),'base-review-limitations');body.append(notice);
    const learn=document.createElement('input');learn.type='checkbox';learn.checked=false;const label=node('label',null,'base-investigation-learn');label.append(learn,document.createTextNode(' Aprender na Base Inteligente somente as revisões aprovadas'));body.append(label);
    const footer=node('div',null,'base-review-footer');
    const apply=button('Aplicar revisões e atualizar Excel',async()=>{
      const revisions=controls.filter(c=>c.select.checked).map(c=>({_aba:c.s._aba,_linha:c.s._linha,'Conta da contrapartida':c.account.value.trim()}));
      if(!revisions.length){message.textContent='Selecione as linhas que você revisou e deseja aprovar.';return;}
      if(revisions.some(r=>!/^\d+$/.test(r['Conta da contrapartida']))){message.textContent='Informe a conta contábil de todas as linhas aprovadas.';return;}
      const remember=learn.checked;applying=true;controls.forEach(c=>{c.select.disabled=true;c.account.disabled=true;});learn.disabled=true;priorityController?.abort();apply.disabled=true;controller=new AbortController();const signal=controller.signal;message.textContent='Validando revisões e gerando Excel…';
      const data=new FormData();data.append('file',current.blob,'classificado.xlsx');data.append('revisoes_json',JSON.stringify(revisions));data.append('investigacao_token',result.token);data.append('aprender',String(remember));
      try{
        const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/revisar`,{method:'POST',body:data,signal});
        if(!response.ok)throw Error(await responseError(response));
        const summary=JSON.parse(response.headers.get('x-razync-summary') || '{}');const blob=await response.blob();
        if(signal.aborted || version!==generation)return;
        // Freeze the completed approval, preventing accidental repeated learning.
        controls.forEach(c=>{c.select.disabled=true;c.account.disabled=true;});learn.disabled=true;apply.disabled=true;aiButton.disabled=true;priorityController?.abort();
        completed=true;updateQueue();showDetail();
        renderClassificationCoverage(summary.cobertura);
        message.textContent=`Revisões aplicadas: ${summary.aplicadas}. Padrões aprendidos: ${summary.aprendizados || 0}.`;
        const download=button('Baixar Excel revisado',()=>downloadBlob(new Response(blob),`RAZYNC_${current.company}_REVISADO.xlsx`));download.className='preview-download';footer.append(download);
        const previewBody=new FormData();previewBody.append('file',blob,'revisado.xlsx');
        const previewResponse=await fetch(`${API()}/api/v1/modelo-preview`,{method:'POST',body:previewBody,signal});
        if(signal.aborted || version!==generation)return;
        if(previewResponse.ok)showWorkflowPreview(await previewResponse.json(),document.querySelector('#classificationPreview'));
      }catch(error){if(signal.aborted || version!==generation)return;message.textContent=completed?'Excel revisado gerado. A prévia não pôde ser atualizada; use Baixar Excel revisado.':error.message;if(!completed){applying=false;controls.forEach(c=>{c.select.disabled=false;c.account.disabled=false;});learn.disabled=false;updateQueue();showDetail();}}
    });footer.append(apply,message);body.append(footer);updateQueue();showDetail();
  }
  globalThis.RazyncBaseInvestigation={mount,reset};
})();
