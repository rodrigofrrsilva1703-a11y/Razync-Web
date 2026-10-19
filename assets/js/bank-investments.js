(function () {
  function mount({target, company, banks, snapshot, summary, rows, balances, isCurrent, signal, api, download, responseError}) {
    if (!rows.length || summary?.ok !== true || summary.errors?.length || !rows.every(row => balances(row).ok)) return;
    const el = (tag, cls, text) => { const item = document.createElement(tag); item.className = cls || ''; if (text) item.textContent = text; return item; };
    const panel = el('details','bank-investments');
    panel.appendChild(el('summary','','Gerar TXT de aplicações e resgates'));
    panel.appendChild(el('p','bank-investments-rule','Zeramento diário: saldo negativo gera resgate (débito no banco); saldo positivo gera aplicação (crédito no banco). A conta informada é a mesma para as duas operações.'));
    const form = el('form','bank-investments-form'), fields = [];
    for (const bank of banks) {
      const fieldset = el('fieldset','bank-investments-bank'); fieldset.appendChild(el('legend','',bank.label));
      const makeInput = (text,value,pattern,mode) => {
        const label=el('label','',text), input=el('input'); input.type='text'; input.inputMode=mode; input.value=value;
        if (pattern) input.pattern=pattern; input.required=true; input.autocomplete='off'; label.appendChild(input); fieldset.appendChild(label); return input;
      };
      const account = makeInput('Conta do banco',bank.account || '', '[0-9]{1,15}','numeric'); account.readOnly=Boolean(bank.account);
      const investment = makeInput('Conta de aplicação e resgate','','[0-9]{1,15}','numeric');
      const opening = makeInput('Saldo anterior ao primeiro dia (R$)','0,00','-?(?:[0-9]{1,3}(?:[.][0-9]{3})+|[0-9]+)(?:,[0-9]{1,2})?','decimal');
      fields.push({bank:bank.code,account,investment,opening}); form.appendChild(fieldset);
    }
    form.appendChild(el('small','bank-investments-note','Use 0,00 se o banco já estava zerado antes do primeiro dia analisado. O saldo anterior entra somente no primeiro dia; nos seguintes, o cálculo considera o zeramento do dia anterior.'));
    const button=el('button','bank-investments-preview-button','Gerar prévia'); button.type='submit';
    const downloadButton=el('button','bank-investments-download','Baixar TXT'); downloadButton.type='button'; downloadButton.hidden=true; downloadButton.disabled=true;
    const preview=el('section','bank-investments-preview'); preview.hidden=true; preview.setAttribute('aria-label','Prévia dos lançamentos de aplicações e resgates');
    let prepared=null;
    const currency=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});
    function clearPreview() { prepared=null;preview.hidden=true;preview.replaceChildren();downloadButton.hidden=true;downloadButton.disabled=true; }
    function renderPreview(result) {
      preview.replaceChildren();preview.hidden=false;
      preview.appendChild(el('h4','','Prévia dos lançamentos'));
      preview.appendChild(el('p','bank-investments-preview-totals',result.rows.length+(result.rows.length===1?' lançamento · Resgates: ':' lançamentos · Resgates: ')+currency.format(Number(result.summary.total_resgates))+' · Aplicações: '+currency.format(Number(result.summary.total_aplicacoes))));
      const scroll=el('div','bank-investments-preview-scroll');scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','Lançamentos gerados; role para conferir todas as colunas');
      const table=el('table'),caption=el('caption','bank-investments-caption','Lançamentos que serão incluídos no TXT. Saldo antes considera as movimentações do dia e o zeramento dos dias anteriores.');table.appendChild(caption);
      const head=el('thead'),heading=el('tr');
      const columns=[['DATA','Data'],['BANCO','Banco'],['TIPO','Operação'],['DÉBITO','Débito'],['CRÉDITO','Crédito'],['VALOR','Valor'],['SALDO_ANTES','Saldo antes'],['SALDO_APOS','Saldo após'],['HISTÓRICO','Histórico']];
      columns.forEach(([,label])=>{const th=el('th','',label);th.setAttribute('scope','col');heading.appendChild(th);});head.appendChild(heading);table.appendChild(head);
      const body=el('tbody');table.appendChild(body);scroll.appendChild(table);preview.appendChild(scroll);
      const pagination=el('div','bank-investments-pagination'),previous=el('button','','Anterior'),next=el('button','','Próxima'),range=el('span');previous.type=next.type='button';
      let page=0;const size=30;
      function draw() {
        body.replaceChildren();const start=page*size;
        result.rows.slice(start,start+size).forEach(row=>{
          const tr=el('tr');columns.forEach(([key])=>{
            const monetary=['VALOR','SALDO_ANTES','SALDO_APOS'].includes(key);
            const value=key==='BANCO' ? (banks.find(bank=>bank.code===row.BANCO)?.label || row.BANCO) : monetary ? currency.format(Number(row[key])) : row[key];
            tr.appendChild(el('td',monetary?'is-money':key==='HISTÓRICO'?'is-history':'',String(value ?? '')));
          });body.appendChild(tr);
        });
        range.textContent=(start+1)+'–'+Math.min(start+size,result.rows.length)+' de '+result.rows.length;
        previous.disabled=page===0;next.disabled=start+size>=result.rows.length;scroll.scrollTop=0;
      }
      previous.addEventListener('click',()=>{if(page>0){page--;draw();}});next.addEventListener('click',()=>{if((page+1)*size<result.rows.length){page++;draw();}});
      pagination.hidden=result.rows.length<=size;pagination.append(previous,range,next);preview.appendChild(pagination);draw();
    }
    const message=el('p','bank-investments-message');message.setAttribute('role','status');message.setAttribute('aria-live','polite');
    form.append(button,message); panel.append(form,preview,downloadButton); target.appendChild(panel);
    let active, revision=0;
    signal?.addEventListener('abort',()=>active?.abort(),{once:true});
    form.addEventListener('input',()=>{revision++;active?.abort();button.disabled=false;clearPreview();message.textContent='Configuração alterada. Gere a prévia novamente.';});
    form.addEventListener('submit',async event=>{
      event.preventDefault();
      if (!isCurrent() || !form.reportValidity()) return;
      const settings={};
      for (const item of fields) {
        if (!Number(item.investment.value) || !Number(item.account.value) || Number(item.account.value)===Number(item.investment.value)) {
          message.textContent='Informe uma conta de aplicação/resgate diferente da conta do banco.';return;
        }
        settings[item.bank]={conta_banco:item.account.value,conta_aplicacao:item.investment.value,saldo_anterior:item.opening.value};
      }
      active?.abort();const controller=new AbortController();active=controller;const currentRevision=revision;
      const data=new FormData(); for (const [key,value] of snapshot.entries()) data.append(key,value);
      data.append('settings_json',JSON.stringify(settings));
      clearPreview();button.disabled=true;message.textContent='Validando a conferência e montando a prévia…';
      try {
        const response=await fetch(api+'/api/v1/conferencia-extrato/'+company+'/aplicacoes-resgates/preview',{method:'POST',body:data,signal:controller.signal});
        if (!response.ok) throw new Error(await responseError(response));
        if (!isCurrent() || controller.signal.aborted || revision!==currentRevision) return;
        const result=await response.json();
        if (!isCurrent() || controller.signal.aborted || revision!==currentRevision) return;
        if (!Array.isArray(result.rows) || !result.rows.length || typeof result.txt!=='string' || !result.summary) throw new Error('Não foi possível montar uma prévia válida. Gere novamente.');
        prepared={...result,revision:currentRevision};renderPreview(result);downloadButton.hidden=false;downloadButton.disabled=false;
        message.textContent='Confira os lançamentos abaixo e clique em Baixar TXT.';
      } catch(error) {
        if (error.name!=='AbortError' && isCurrent() && revision===currentRevision) message.textContent=error.message;
      } finally { if (revision===currentRevision) button.disabled=false; }
    });
    downloadButton.addEventListener('click',async()=>{
      if (!prepared || prepared.revision!==revision || !isCurrent()) return;
      const current=prepared;downloadButton.disabled=true;
      try {
        await download(new Response(current.txt,{headers:{'Content-Type':'text/plain; charset=utf-8'}}),'RAZYNC_'+company+'_APLICACOES_RESGATES.txt');
        if (prepared===current && isCurrent()) message.textContent='TXT baixado com os mesmos lançamentos da prévia.';
      } catch(error) { if (prepared===current && isCurrent()) message.textContent=error.message || 'Não foi possível baixar o TXT.'; }
      finally { if (prepared===current && isCurrent()) downloadButton.disabled=false; }
    });
    return panel;
  }
  globalThis.RazyncInvestments={mount};
})();
