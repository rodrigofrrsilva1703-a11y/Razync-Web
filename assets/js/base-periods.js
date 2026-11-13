/* Consulta de meses salvos pela mesma rota protegida da manutenção. */
(() => {
  const root=document.getElementById('baseSavedPeriods');
  if(!root)return;
  const button=document.getElementById('loadSavedPeriods');
  const list=document.getElementById('savedPeriodsList');
  const message=document.getElementById('savedPeriodsMessage');
  let revision=0,controller=null,loadedCompany=null;
  const label=bank=>bankName(bank==='bb'?'banco_brasil':bank==='itau_512'?'itau':bank);
  const month=value=>/^\d{4}-(0[1-9]|1[0-2])$/.test(value)?value.slice(5)+'/'+value.slice(0,4):value;
  function render(banks) {
    list.replaceChildren();
    for(const bank of banks) {
      const row=document.createElement('div');row.className='saved-period-bank';
      const name=document.createElement('strong');name.textContent=label(bank.bank)+(bank.account?' · conta '+bank.account:'');
      const months=document.createElement('div');months.className='saved-period-months';
      for(const period of [...new Set(bank.periods||[])].sort().reverse()) {
        const chip=document.createElement('span');chip.textContent=month(String(period));months.appendChild(chip);
      }
      row.appendChild(name);row.appendChild(months);list.appendChild(row);
    }
    list.hidden=!banks.length;
    message.textContent=banks.length?'Meses com padrões salvos. Um mês listado pode conter apenas parte dos lançamentos.':'Esta empresa ainda não tem períodos gravados na base.';
    button.textContent='Atualizar períodos';
  }
  function reset() {
    revision++;controller?.abort();loadedCompany=null;
    list.replaceChildren();list.hidden=true;button.disabled=false;button.textContent='Consultar períodos';
    root.setAttribute('aria-busy','false');
    message.textContent='Consulte os meses já aprendidos antes de adicionar novos arquivos.';
  }
  async function load() {
    if(!selected || selected.capabilities?.status!=='api_ready')return;
    controller?.abort();controller=new AbortController();
    const company=selected.codigo,version=++revision,signal=controller.signal;
    const current=()=>!signal.aborted && revision===version && selected?.codigo===company;
    button.disabled=true;root.setAttribute('aria-busy','true');message.textContent='Consultando períodos gravados…';
    try {
      const response=await window.adminFetch(`${API()}/api/v1/base-inteligente/${company}/recortes`,{signal},current);
      if(!current())return;
      if(!response.ok)throw new Error(await responseError(response));
      const data=await response.json();if(!current())return;
      render(data.banks||[]);loadedCompany=company;
    } catch(error) {
      if(current())message.textContent=error.name==='AbortError'?'Consulta cancelada. Clique em Consultar períodos para tentar novamente.':error.message;
    } finally {
      if(revision===version){button.disabled=false;root.setAttribute('aria-busy','false');}
    }
  }
  const resetMaintenance=window.resetBaseMaintenance;
  window.resetBaseMaintenance=()=>{resetMaintenance?.();reset();};
  window.refreshSavedBasePeriods=()=>{if(loadedCompany===selected?.codigo)return load();};
  window.updateSavedBasePeriods=(company,banks)=>{if(loadedCompany===company && selected?.codigo===company){revision++;controller?.abort();render(banks);button.disabled=false;root.setAttribute('aria-busy','false');}};
  button.addEventListener('click',load);
})();
