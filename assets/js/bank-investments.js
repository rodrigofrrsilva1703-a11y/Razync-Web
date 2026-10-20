(function () {
  function mount({target, company, banks, snapshot, summary, rows, balances, isCurrent, signal, api, download, responseError}) {
    if (!rows.length || !banks.length) return;
    const bankStates=new Map(banks.map(bank=>{
      // A prévia multibanco identifica cada conta pelo nome e código contábil.
      // Comparação exata evita misturar duas contas do mesmo banco (ex.: Itaú 508/509).
      const label=[bank.label,String(bank.account || '').trim()].filter(Boolean).join(' ');
      const daily=banks.length===1 ? rows : rows.filter(row=>String(row.BANCO || '').trim()===label);
      const error=(summary?.errors || []).some(item=>!item.bank || item.bank===bank.code);
      const ready=!error && daily.length>0 && daily.every(row=>balances(row).ok);
      const ownSummary=summary?.by_bank?.[bank.code] || (banks.length===1 ? summary : null);
      return [bank.code,{ready,error,hasRows:daily.length>0,summary:ownSummary}];
    }));
    let ready=false;
    const el = (tag, cls, text) => { const item = document.createElement(tag); item.className = cls || ''; if (text) item.textContent = text; return item; };
    const panel = el('details','bank-investments');
    panel.open=true;
    panel.appendChild(el('summary','','Aplicações e resgates · prévia e TXT'));
    const status=el('p','bank-investments-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');panel.appendChild(status);
    const reviewNote=el('p','bank-investments-note','Os totais diários deste banco batem, mas há lançamentos sem correspondência individual no relatório. Revise-os na conferência; o zeramento abaixo usa os totais diários.');
    reviewNote.hidden=true;panel.appendChild(reviewNote);
    const help=el('details','bank-investments-help');help.appendChild(el('summary','','Como funciona o zeramento'));
    help.appendChild(el('p','bank-investments-rule','Zeramento diário: saldo negativo gera resgate (débito no banco); saldo positivo gera aplicação (crédito no banco). A conta informada é a mesma para as duas operações.'));
    const form = el('form','bank-investments-form'), fields = [];
    const bankLabel=el('label','bank-investments-selector','Banco para gerar os lançamentos');
    const bankSelect=el('select','bank-investments-bank-select');bankSelect.setAttribute('aria-label','Banco para aplicações e resgates');
    banks.forEach(bank=>{const state=bankStates.get(bank.code);
      const note=state.ready?'Conferido':state.error?'Erro na conferência':state.hasRows?'Com divergências':'Sem dias conferidos';
      const option=el('option','',bank.label+(bank.account?' · conta '+bank.account:'')+' · '+note);option.value=bank.code;bankSelect.appendChild(option);
    });
    bankSelect.value=(banks.find(bank=>bankStates.get(bank.code).ready) || banks[0]).code;bankLabel.appendChild(bankSelect);form.appendChild(bankLabel);
    for (const bank of banks) {
      const fieldset = el('fieldset','bank-investments-bank'); fieldset.appendChild(el('legend','',bank.label));
      const makeInput = (text,value,pattern,mode) => {
        const label=el('label','',text), input=el('input'); input.type='text'; input.inputMode=mode; input.value=value;
        if (pattern) input.pattern=pattern; input.required=true; input.autocomplete='off'; label.appendChild(input); fieldset.appendChild(label); return input;
      };
      const account = makeInput('Conta do banco',bank.account || '', '[0-9]{1,15}','numeric'); account.readOnly=Boolean(bank.account);
      const investment = makeInput('Conta de aplicação e resgate','','[0-9]{1,15}','numeric');
      const opening = makeInput('Saldo anterior (R$)','0,00','-?(?:[0-9]{1,3}(?:[.][0-9]{3})+|[0-9]+)(?:,[0-9]{1,2})?','decimal');
      opening.title='Saldo anterior ao primeiro dia analisado. Nos dias seguintes, considera o zeramento do dia anterior.';
      fields.push({bank:bank.code,account,investment,opening,fieldset}); form.appendChild(fieldset);
    }
    help.appendChild(el('small','bank-investments-note','Use 0,00 se o banco já estava zerado antes do primeiro dia analisado. O saldo anterior entra somente no primeiro dia; nos seguintes, o cálculo considera o zeramento do dia anterior.'));
    const button=el('button','bank-investments-preview-button','Gerar prévia'); button.type='submit';
    const downloadButton=el('button','bank-investments-download',typeof globalThis.showSaveFilePicker==='function'?'Salvar TXT…':'Baixar TXT'); downloadButton.type='button'; downloadButton.hidden=true; downloadButton.disabled=true;
    const preview=el('section','bank-investments-preview'); preview.hidden=true; preview.setAttribute('aria-label','Prévia dos lançamentos de aplicações e resgates');
    let prepared=null;
    const currency=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});
    function clearPreview() { prepared=null;preview.hidden=true;preview.replaceChildren();downloadButton.hidden=true;downloadButton.disabled=true; }
    function renderPreview(result) {
      preview.replaceChildren();preview.hidden=false;
      preview.appendChild(el('h4','','Prévia dos lançamentos'));
      preview.appendChild(el('p','bank-investments-preview-totals',result.rows.length+(result.rows.length===1?' lançamento · Resgates: ':' lançamentos · Resgates: ')+currency.format(Number(result.summary.total_resgates))+' · Aplicações: '+currency.format(Number(result.summary.total_aplicacoes))));
      const scroll=el('div','bank-investments-preview-scroll');scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','Lançamentos gerados; role para conferir todas as colunas');
      const table=el('table'),caption=el('caption','bank-investments-caption','Descrição: APLICAÇÃO E RESGATE. Lançamentos incluídos no TXT; saldo antes considera o zeramento dos dias anteriores.');table.appendChild(caption);
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
    form.append(button,message); panel.append(form,help,preview,downloadButton); target.prepend(panel);
    let active, revision=0;
    signal?.addEventListener('abort',()=>active?.abort(),{once:true});
    function syncBank() {
      const state=bankStates.get(bankSelect.value),bank=banks.find(item=>item.code===bankSelect.value);
      ready=Boolean(state?.ready);
      status.textContent=ready ? bank.label+': saldos diários conferidos. Prévia e TXT liberados para este banco.'
        : state?.error ? bank.label+': há erro na conferência deste banco. Confira os arquivos e processe novamente.'
        : !state?.hasRows ? bank.label+': não há dias conferidos para gerar os lançamentos deste banco.'
        : bank.label+': a geração será liberada quando todas as entradas e saídas diárias deste banco estiverem batendo.';
      reviewNote.hidden=!ready || state?.summary?.ok!==false;
      fields.forEach(item=>{const chosen=item.bank===bankSelect.value;item.fieldset.hidden=!chosen;
        [item.account,item.investment,item.opening].forEach(input=>input.disabled=!chosen || !ready);
      });
      button.disabled=!ready;
    }
    function invalidate() { revision++;active?.abort();syncBank();clearPreview();message.textContent=ready?'Configuração alterada. Gere a prévia novamente.':''; }
    syncBank();
    bankSelect.addEventListener('change',invalidate);
    form.addEventListener('input',invalidate);
    form.addEventListener('submit',async event=>{
      event.preventDefault();
      if (!ready || !isCurrent() || !form.reportValidity()) return;
      const settings={};
      for (const item of fields.filter(field=>field.bank===bankSelect.value)) {
        if (!Number(item.investment.value) || !Number(item.account.value) || Number(item.account.value)===Number(item.investment.value)) {
          message.textContent='Informe uma conta de aplicação/resgate diferente da conta do banco.';return;
        }
        settings[item.bank]={conta_banco:item.account.value,conta_aplicacao:item.investment.value,saldo_anterior:item.opening.value};
      }
      active?.abort();const controller=new AbortController();active=controller;const currentRevision=revision;
      const data=new FormData(), uploads=[];
      const fileBanks=JSON.parse(snapshot.get('file_banks_json') || '[]');
      let index=0;
      for (const [key,value] of snapshot.entries()) {
        if (key==='files') {if(fileBanks[index]===bankSelect.value) uploads.push(value);index++;}
        else if (!['banks_json','file_banks_json','settings_json'].includes(key)) data.append(key,value);
      }
      if (!uploads.length) {message.textContent='Não há extrato deste banco na conferência. Envie o extrato e confira novamente.';return;}
      data.append('banks_json',JSON.stringify([bankSelect.value]));
      data.append('file_banks_json',JSON.stringify(uploads.map(()=>bankSelect.value)));
      uploads.forEach(file=>data.append('files',file));
      data.append('settings_json',JSON.stringify(settings));
      clearPreview();button.disabled=true;message.textContent='Validando a conferência e montando a prévia…';
      try {
        const response=await fetch(api+'/api/v1/conferencia-extrato/'+company+'/aplicacoes-resgates/preview',{method:'POST',body:data,signal:controller.signal});
        if (!response.ok) throw new Error(await responseError(response));
        if (!isCurrent() || controller.signal.aborted || revision!==currentRevision) return;
        const result=await response.json();
        if (!isCurrent() || controller.signal.aborted || revision!==currentRevision) return;
        if (!Array.isArray(result.rows) || !result.rows.length || typeof result.txt!=='string' || typeof result.txt_base64!=='string' || result.encoding!=='windows-1252' || !result.summary) throw new Error('Não foi possível montar uma prévia válida. Gere novamente.');
        prepared={...result,revision:currentRevision};renderPreview(result);downloadButton.hidden=false;downloadButton.disabled=false;
        message.textContent=typeof globalThis.showSaveFilePicker==='function'?'Confira os lançamentos abaixo e clique em Salvar TXT para escolher a pasta.':'Confira os lançamentos abaixo e clique em Baixar TXT.';
      } catch(error) {
        if (error.name!=='AbortError' && isCurrent() && revision===currentRevision) message.textContent=error.message;
      } finally { if (revision===currentRevision) button.disabled=false; }
    });
    downloadButton.addEventListener('click',async()=>{
      if (!prepared || prepared.revision!==revision || !isCurrent()) return;
      const current=prepared;downloadButton.disabled=true;
      try {
        const txtBytes=()=>Uint8Array.from(atob(current.txt_base64),char=>char.charCodeAt(0));
        const filename='RAZYNC_'+company+'_'+bankSelect.value.toUpperCase()+'_APLICACOES_RESGATES.txt';
        const stillCurrent=()=>prepared===current && current.revision===revision && isCurrent();
        if (typeof globalThis.showSaveFilePicker==='function') {
          // Invocado diretamente no clique, antes de qualquer espera de rede.
          const handle=await globalThis.showSaveFilePicker({id:'razync-investments',suggestedName:filename,
            types:[{description:'TXT para Domínio',accept:{'text/plain':['.txt']}}]});
          if (!stillCurrent()) return;
          let writer;
          try {
            writer=await handle.createWritable();
            if (!stillCurrent()) {await writer.abort();writer=null;return;}
            await writer.write(txtBytes());
            if (!stillCurrent()) {await writer.abort();writer=null;return;}
            await writer.close();writer=null;
          } catch(error) {if(writer) await writer.abort().catch(()=>{});throw error;}
          if (stillCurrent()) message.textContent='TXT salvo na pasta escolhida, com os mesmos lançamentos da prévia.';
        } else {
          await download(new Response(txtBytes(),{headers:{'Content-Type':'text/plain; charset=windows-1252'}}),filename);
          if (stillCurrent()) message.textContent='TXT baixado com os mesmos lançamentos da prévia.';
        }
      } catch(error) {
        if (prepared===current && isCurrent()) message.textContent=error.name==='AbortError'
          ? 'Salvamento cancelado. Você pode escolher a pasta novamente.' : error.message || 'Não foi possível salvar o TXT.';
      }
      finally { if (prepared===current && isCurrent()) downloadButton.disabled=false; }
    });
    return panel;
  }
  globalThis.RazyncInvestments={mount};
})();
