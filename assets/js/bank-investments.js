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
    const button=el('button','bank-investments-download','Gerar e baixar TXT'); button.type='submit';
    const message=el('p','bank-investments-message');message.setAttribute('role','status');message.setAttribute('aria-live','polite');
    form.append(button,message); panel.appendChild(form); target.appendChild(panel);
    let active, revision=0;
    signal?.addEventListener('abort',()=>active?.abort(),{once:true});
    form.addEventListener('input',()=>{revision++;active?.abort();button.disabled=false;message.textContent='';});
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
      button.disabled=true;message.textContent='Validando a conferência e gerando os lançamentos diários…';
      try {
        const response=await fetch(api+'/api/v1/conferencia-extrato/'+company+'/aplicacoes-resgates',{method:'POST',body:data,signal:controller.signal});
        if (!response.ok) throw new Error(await responseError(response));
        if (!isCurrent() || controller.signal.aborted || revision!==currentRevision) return;
        await download(response,'RAZYNC_'+company+'_APLICACOES_RESGATES.txt');
        message.textContent='TXT gerado com as contas e os históricos informados.';
      } catch(error) {
        if (error.name!=='AbortError' && isCurrent() && revision===currentRevision) message.textContent=error.message;
      } finally { if (revision===currentRevision) button.disabled=false; }
    });
    return panel;
  }
  globalThis.RazyncInvestments={mount};
})();
