/* Optional investigation of the exact classified result, never the original upload. */
(() => {
  let context, controller, generation=0, wantsOpen=false;
  const panel=document.createElement('section');
  panel.id='baseInvestigation';panel.className='base-investigation';panel.hidden=true;
  document.querySelector('#classifyForm').after(panel);
  const launcher=document.createElement('button');launcher.type='button';launcher.className='base-ai-launcher';launcher.hidden=true;
  launcher.textContent='✦ Assistente da Base';launcher.setAttribute('aria-controls','baseInvestigationWindow');launcher.setAttribute('aria-expanded','false');
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
  function reset(){generation++;controller?.abort();context=null;wantsOpen=false;body.replaceChildren();panel.replaceChildren();panel.hidden=true;floating.hidden=true;launcher.hidden=true;launcher.setAttribute('aria-expanded','false');}
  function mount({prepared,company,options,summary}) {
    reset();if(!summary?.cobertura?.pendentes)return;
    context={prepared,company,options};panel.hidden=false;
    const heading=node('div',null,'base-investigation-heading');
    const title=node('div');title.append(node('h3','Investigar pendências'),node('p','Consulte o histórico da empresa e revise sugestões antes de alterar o Excel.'));
    const run=button('✦ Investigar pendentes com IA',openOrInvestigate);
    launcher.hidden=false;
    heading.append(title,run);panel.append(heading,node('p','Python consulta os padrões primeiro. A IA recebe apenas indicadores anônimos para priorizar casos ambíguos.','helper'));
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
      const data=new FormData();data.append('file',current.blob,'classificado.xlsx');data.append('options_json',JSON.stringify(current.options));
      const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/sugerir-pendentes`,{method:'POST',body:data,signal});
      if(!response.ok)throw Error(await responseError(response));
      const result=await response.json();if(signal.aborted || version!==generation)return;
      render(result,current,version);
    }catch(error){if(signal.aborted || version!==generation)return;status.textContent=error.message;cancel.textContent='Tentar novamente';cancel.onclick=null;body.replaceChildren(status,button('Tentar novamente',investigate));}
  }
  function showAccountHistory(account,nature,catalog,target){
    target.replaceChildren();target.hidden=false;
    const item=catalog.find(c=>c.conta===account.trim() && c.natureza===nature);
    if(!item){target.append(node('p','Selecione uma conta histórica desta natureza para consultar seu uso.'));return;}
    target.append(node('strong',`Conta ${item.conta}`),node('p',`${quantity(item.ocorrencias,'ocorrência')} · ${quantity(item.periodos.length,'período')} · ${item.bancos.map(bankLabelUI).join(', ')}`));
    target.append(node('small',`Períodos: ${item.periodos.join(', ') || 'não comprovados'}`));
    for(const example of item.exemplos || []){
      const entry=node('div',null,'base-account-history-entry');
      entry.append(node('p',example.historico),node('small',`${bankLabelUI(example.banco)} · ${example.periodos.join(', ') || 'período não comprovado'} · ${quantity(example.ocorrencias,'ocorrência')}`));target.append(entry);
    }
    target.append(node('small','Exemplos de padrões aprendidos; não representam um razão completo nem comprovam que a conta está ativa.'));
  }
  function render(result,current,version){
    body.replaceChildren();const counts={FORTE:0,MODERADA:0,MANUAL:0};result.sugestoes.forEach(s=>counts[s.situacao]++);
    body.append(node('h3','Revisão das pendências'),node('p',`${quantity(result.total_pendencias,'linha')} · ${quantity(result.grupos_investigados,'grupo')} · ${quantity(counts.FORTE,'forte')} · ${quantity(counts.MODERADA,'moderada')} · ${counts.MANUAL} para revisão manual`));
    if(!result.total_pendencias){body.append(node('p','Não há pendências elegíveis para revisão neste perfil.'));return;}
    const ai=node('p',result.ia?.motivo || 'Evidências consultadas no histórico da empresa.','helper');body.append(ai);
    const scroll=node('div',null,'base-investigation-scroll'),table=document.createElement('table');
    const head=document.createElement('thead'),hr=document.createElement('tr');['Aprovar','Lançamento','Sugestão e evidências','Conta'].forEach(t=>hr.append(node('th',t)));head.append(hr);table.append(head);
    const tbody=document.createElement('tbody'),controls=[];
    const priority=new Set(result.ia?.prioridades || []);
    const suggestions=[...result.sugestoes].sort((a,b)=>Number(priority.has(b.grupo))-Number(priority.has(a.grupo)));
    for(const s of suggestions){
      const tr=document.createElement('tr');const select=document.createElement('input');select.type='checkbox';select.setAttribute('aria-label',`Aprovar ${s._aba}, linha ${s._linha}`);
      const td=node('td');td.append(select);const entry=node('td');entry.append(node('strong',s['Histórico']),node('small',`${s._aba} · linha ${s._linha} · ${s.Data} · ${Number(s.Valor).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}`));
      const evidence=node('td');evidence.append(node('span',({FORTE:'Sugestão forte',MODERADA:'Sugestão moderada',MANUAL:'Revisão manual'})[s.situacao],'base-investigation-grade'),node('p',s.justificativa));
      const details=node('details'),summary=node('summary',`Ver evidências (${s.evidencias.length})`);details.append(summary);
      for(const e of s.evidencias){details.append(node('p',`Conta ${e.conta} · ${bankLabelUI(e.banco)} · ${e.periodos.join(', ') || 'período não comprovado'} · ${e.ocorrencias} ocorrências · ${e.exata?'assinatura exata':'similaridade textual'}`));e.historicos.forEach(h=>details.append(node('small',h)));}
      if(s.evidencias.length)evidence.append(details);
      const account=document.createElement('input');account.type='text';account.inputMode='numeric';account.value=s.conta_sugerida;account.maxLength=15;account.placeholder='Conta revisada';account.setAttribute('aria-label',`Conta para ${s._aba}, linha ${s._linha}`);
      const list=document.createElement('datalist');list.id=`baseAccounts-${s._linha}-${controls.length}`;account.setAttribute('list',list.id);
      for(const item of result.catalogo_contas || []){if(item.natureza!==s.natureza)continue;const option=document.createElement('option');option.value=item.conta;option.label=`${item.bancos.map(bankLabelUI).join(', ')} · ${quantity(item.periodos.length,'período')}`;list.append(option);}
      const historyButton=button('Histórico da conta',()=>showAccountHistory(account.value,s.natureza,result.catalogo_contas || [],historyArea));
      const historyArea=node('section',null,'base-account-history');historyArea.hidden=true;
      account.addEventListener('change',()=>{if(!historyArea.hidden)showAccountHistory(account.value,s.natureza,result.catalogo_contas || [],historyArea);});
      const accountCell=node('td');accountCell.append(account,list,historyButton,historyArea);tr.append(td,entry,evidence,accountCell);tbody.append(tr);controls.push({s,select,account});
    }
    table.append(tbody);scroll.append(table);body.append(scroll);
    const notice=node('p',result.limitacoes.join(' '),'helper');body.append(notice);
    const learn=document.createElement('input');learn.type='checkbox';learn.checked=false;const label=node('label',null,'base-investigation-learn');label.append(learn,document.createTextNode(' Aprender na Base Inteligente somente as revisões aprovadas'));body.append(label);
    const message=node('p',null,'helper');message.setAttribute('role','status');
    const apply=button('Aplicar revisões e atualizar Excel',async()=>{
      const revisions=controls.filter(c=>c.select.checked).map(c=>({_aba:c.s._aba,_linha:c.s._linha,'Conta da contrapartida':c.account.value.trim()}));
      if(!revisions.length){message.textContent='Selecione as linhas que você revisou e deseja aprovar.';return;}
      if(revisions.some(r=>!/^\d+$/.test(r['Conta da contrapartida']))){message.textContent='Informe a conta contábil de todas as linhas aprovadas.';return;}
      let completed=false;
      const remember=learn.checked;apply.disabled=true;controller=new AbortController();const signal=controller.signal;message.textContent='Validando revisões e gerando Excel…';
      const data=new FormData();data.append('file',current.blob,'classificado.xlsx');data.append('revisoes_json',JSON.stringify(revisions));data.append('investigacao_token',result.token);data.append('aprender',String(remember));
      try{
        const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/revisar`,{method:'POST',body:data,signal});
        if(!response.ok)throw Error(await responseError(response));
        const summary=JSON.parse(response.headers.get('x-razync-summary') || '{}');const blob=await response.blob();
        if(signal.aborted || version!==generation)return;
        // Freeze the completed approval, preventing accidental repeated learning.
        controls.forEach(c=>{c.select.disabled=true;c.account.disabled=true;});learn.disabled=true;apply.disabled=true;
        completed=true;
        renderClassificationCoverage(summary.cobertura);
        message.textContent=`Revisões aplicadas: ${summary.aplicadas}. Padrões aprendidos: ${summary.aprendizados || 0}.`;
        const download=button('Baixar Excel revisado',()=>downloadBlob(new Response(blob),`RAZYNC_${current.company}_REVISADO.xlsx`));download.className='preview-download';body.append(download);
        const previewBody=new FormData();previewBody.append('file',blob,'revisado.xlsx');
        const previewResponse=await fetch(`${API()}/api/v1/modelo-preview`,{method:'POST',body:previewBody,signal});
        if(signal.aborted || version!==generation)return;
        if(previewResponse.ok)showWorkflowPreview(await previewResponse.json(),document.querySelector('#classificationPreview'));
      }catch(error){if(signal.aborted || version!==generation)return;message.textContent=completed?'Excel revisado gerado. A prévia não pôde ser atualizada; use Baixar Excel revisado.':error.message;if(!completed)apply.disabled=false;}
    });body.append(apply,message);
  }
  globalThis.RazyncBaseInvestigation={mount,reset};
})();
