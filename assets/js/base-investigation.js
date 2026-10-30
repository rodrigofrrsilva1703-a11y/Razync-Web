/* Optional investigation of the exact classified result, never the original upload. */
(() => {
  let context, controller, generation=0;
  const panel=document.createElement('section');
  panel.id='baseInvestigation';panel.className='base-investigation';panel.hidden=true;
  document.querySelector('#classifyForm').after(panel);
  const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e;};
  const button=(text,fn)=>{const e=node('button',text,'secondary-action');e.type='button';e.addEventListener('click',fn);return e;};
  function reset(){generation++;controller?.abort();context=null;panel.replaceChildren();panel.hidden=true;}
  function mount({prepared,company,options,summary}) {
    reset();if(!summary?.cobertura?.pendentes)return;
    context={prepared,company,options};panel.hidden=false;
    const heading=node('div',null,'base-investigation-heading');
    const title=node('div');title.append(node('h3','Investigar pendências'),node('p','Consulte o histórico da empresa e revise sugestões antes de alterar o Excel.'));
    const run=button('✦ Investigar pendentes com IA',investigate);
    heading.append(title,run);panel.append(heading,node('p','Python consulta os padrões primeiro. A IA recebe apenas indicadores anônimos para priorizar casos ambíguos.','helper'));
  }
  async function investigate(){
    if(!context)return;
    const current=context, version=generation;controller?.abort();controller=new AbortController();const signal=controller.signal;
    panel.querySelectorAll('button').forEach(b=>b.disabled=true);
    const status=node('p','Consultando padrões e evidências…','helper');status.setAttribute('role','status');
    const cancel=button('Cancelar',()=>{controller.abort();mount({...current,summary:{cobertura:{pendentes:1}}});});panel.append(status,cancel);
    try {
      current.blob=current.blob || await current.prepared.blob();
      if(signal.aborted || version!==generation)return;
      const body=new FormData();body.append('file',current.blob,'classificado.xlsx');body.append('options_json',JSON.stringify(current.options));
      const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/sugerir-pendentes`,{method:'POST',body,signal});
      if(!response.ok)throw Error(await responseError(response));
      const result=await response.json();if(signal.aborted || version!==generation)return;
      render(result,current,version);
    }catch(error){if(signal.aborted || version!==generation)return;status.textContent=error.message;cancel.textContent='Tentar novamente';cancel.onclick=null;panel.replaceChildren(status,button('Tentar novamente',investigate));}
  }
  function render(result,current,version){
    panel.replaceChildren();const counts={FORTE:0,MODERADA:0,MANUAL:0};result.sugestoes.forEach(s=>counts[s.situacao]++);
    panel.append(node('h3','Revisão das pendências'),node('p',`${result.total_pendencias} linhas · ${result.grupos_investigados} grupos · ${counts.FORTE} fortes · ${counts.MODERADA} moderadas · ${counts.MANUAL} para revisão manual`));
    if(!result.total_pendencias){panel.append(node('p','Não há pendências elegíveis para revisão neste perfil.'));return;}
    const ai=node('p',result.ia?.motivo || 'Evidências consultadas no histórico da empresa.','helper');panel.append(ai);
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
      for(const e of s.evidencias){details.append(node('p',`Conta ${e.conta} · ${e.banco} · ${e.periodos.join(', ') || 'período não comprovado'} · ${e.ocorrencias} ocorrências · ${e.exata?'assinatura exata':'similaridade textual'}`));e.historicos.forEach(h=>details.append(node('small',h)));}
      if(s.evidencias.length)evidence.append(details);
      const account=document.createElement('input');account.type='text';account.inputMode='numeric';account.value=s.conta_sugerida;account.maxLength=15;account.placeholder='Conta revisada';account.setAttribute('aria-label',`Conta para ${s._aba}, linha ${s._linha}`);
      const list=document.createElement('datalist');list.id=`baseAccounts-${s._linha}-${controls.length}`;account.setAttribute('list',list.id);
      for(const item of result.catalogo_contas || []){if(item.natureza!==s.natureza)continue;const option=document.createElement('option');option.value=item.conta;option.label=`${item.bancos.join(', ')} · ${item.periodos.length} períodos`;list.append(option);}
      const accountCell=node('td');accountCell.append(account,list);tr.append(td,entry,evidence,accountCell);tbody.append(tr);controls.push({s,select,account});
    }
    table.append(tbody);scroll.append(table);panel.append(scroll);
    const notice=node('p',result.limitacoes.join(' '),'helper');panel.append(notice);
    const learn=document.createElement('input');learn.type='checkbox';learn.checked=false;const label=node('label',null,'base-investigation-learn');label.append(learn,document.createTextNode(' Aprender na Base Inteligente somente as revisões aprovadas'));panel.append(label);
    const message=node('p',null,'helper');message.setAttribute('role','status');
    const apply=button('Aplicar revisões e atualizar Excel',async()=>{
      const revisions=controls.filter(c=>c.select.checked).map(c=>({_aba:c.s._aba,_linha:c.s._linha,'Conta da contrapartida':c.account.value.trim()}));
      if(!revisions.length){message.textContent='Selecione as linhas que você revisou e deseja aprovar.';return;}
      if(revisions.some(r=>!/^\d+$/.test(r['Conta da contrapartida']))){message.textContent='Informe a conta contábil de todas as linhas aprovadas.';return;}
      let completed=false;
      const remember=learn.checked;apply.disabled=true;controller=new AbortController();const signal=controller.signal;message.textContent='Validando revisões e gerando Excel…';
      const body=new FormData();body.append('file',current.blob,'classificado.xlsx');body.append('revisoes_json',JSON.stringify(revisions));body.append('investigacao_token',result.token);body.append('aprender',String(remember));
      try{
        const response=await fetch(`${API()}/api/v1/base-inteligente/${current.company}/revisar`,{method:'POST',body,signal});
        if(!response.ok)throw Error(await responseError(response));
        const summary=JSON.parse(response.headers.get('x-razync-summary') || '{}');const blob=await response.blob();
        if(signal.aborted || version!==generation)return;
        // Freeze the completed approval, preventing accidental repeated learning.
        panel.querySelectorAll('input,button').forEach(e=>e.disabled=true);
        completed=true;
        renderClassificationCoverage(summary.cobertura);
        message.textContent=`${summary.aplicadas} revisões aplicadas. ${summary.aprendizados || 0} padrões aprendidos.`;
        const download=button('Baixar Excel revisado',()=>downloadBlob(new Response(blob),`RAZYNC_${current.company}_REVISADO.xlsx`));download.className='preview-download';panel.append(download);
        const previewBody=new FormData();previewBody.append('file',blob,'revisado.xlsx');
        const previewResponse=await fetch(`${API()}/api/v1/modelo-preview`,{method:'POST',body:previewBody,signal});
        if(signal.aborted || version!==generation)return;
        if(previewResponse.ok)showWorkflowPreview(await previewResponse.json(),document.querySelector('#classificationPreview'));
      }catch(error){if(signal.aborted || version!==generation)return;message.textContent=completed?'Excel revisado gerado. A prévia não pôde ser atualizada; use Baixar Excel revisado.':error.message;if(!completed)apply.disabled=false;}
    });panel.append(apply,message);
  }
  globalThis.RazyncBaseInvestigation={mount,reset};
})();
