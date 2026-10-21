/* Manutenção do aprendizado: a prévia autoriza apenas o recorte exibido. */
(() => {
  const byId = id => document.getElementById(id);
  const panel=byId('baseCleanup'), load=byId('loadBaseSlices'), bank=byId('baseCleanupBank'), period=byId('baseCleanupPeriod');
  const preview=byId('previewBaseCleanup'), confirm=byId('confirmBaseCleanup'), cancel=byId('cancelBaseCleanup');
  const box=byId('baseCleanupConfirmation'), summary=byId('baseCleanupSummary'), message=byId('baseCleanupMessage');
  if (!panel) return;
  let revision=0, controller, slices=[], prepared=null;
  const label=value=>bankName(value==='bb'?'banco_brasil':value==='itau_512'?'itau':value);
  const periodLabel=value=>/^\d{4}-\d{2}$/.test(value)?value.slice(5)+'/'+value.slice(0,4):value;
  function options(select, items, placeholder) {
    select.replaceChildren();
    for (const [value,text] of [['',placeholder],...items]) {
      const option=document.createElement('option');option.value=value;option.textContent=text;select.appendChild(option);
    }
    select.value='';select.disabled=!items.length;
  }
  function invalidate() {
    revision++;controller?.abort();prepared=null;box.hidden=true;
    preview.disabled=!bank.value || !period.value;confirm.disabled=false;load.disabled=false;
  }
  window.resetBaseMaintenance=()=> {
    invalidate();slices=[];panel.open=false;message.textContent='';
    options(bank,[],'Carregue os dados da base');options(period,[],'Selecione o banco');preview.disabled=true;
  };
  async function request(path, init={}) {
    if (!selected || selected.capabilities?.status!=='api_ready') throw new Error('Abra uma empresa disponível para consultar sua base.');
    controller?.abort();controller=new AbortController();
    const company=selected.codigo, version=revision, signal=controller.signal;
    const headers={...adminHeaders(),...(init.headers||{})};
    const current=()=>!signal.aborted && revision===version && selected?.codigo===company;
    const response=await fetch(`${API()}/api/v1/base-inteligente/${company}/${path}`,{...init,headers,signal});
    if(!current()) return null;
    if(response.status===404) throw new Error('A exclusão por período aguarda a atualização do serviço. Tente novamente quando a publicação no Railway for liberada.');
    if(!response.ok) throw new Error(await responseError(response));
    const data=await response.json();return current()?{data,company,version}:null;
  }
  function report(error) {if(error.name!=='AbortError')message.textContent=error.message;}
  async function loadSlices(keepMessage=false) {
    invalidate();load.disabled=true;if(!keepMessage)message.textContent='Carregando bancos e períodos…';
    options(bank,[],'Carregando…');options(period,[],'Selecione o banco');preview.disabled=true;
    const version=revision;
    try {
      const result=await request('recortes');if(!result)return;
      slices=result.data.banks;
      options(bank,slices.map(item=>[item.bank,label(item.bank)+(item.account?' · conta '+item.account:'')]),'Selecione o banco');
      if(!keepMessage)message.textContent=slices.length?'Selecione o banco e o período que deseja remover.':'Esta empresa não tem períodos salvos na base.';
    } catch(error){if(version===revision){options(bank,[],'Carregue novamente');report(error);}}
    finally {if(version===revision)load.disabled=false;}
  }
  load.addEventListener('click',()=>loadSlices());
  bank.addEventListener('change',()=> {
    invalidate();message.textContent='';
    options(period,(slices.find(item=>item.bank===bank.value)?.periods||[]).map(value=>[value,periodLabel(value)]),'Selecione o período');
    preview.disabled=true;
  });
  period.addEventListener('change',()=>{invalidate();message.textContent='';});
  cancel.addEventListener('click',()=>{invalidate();message.textContent='Exclusão cancelada. Nenhum dado foi removido.';});
  preview.addEventListener('click',async()=> {
    invalidate();preview.disabled=true;const version=revision;
    message.textContent='Conferindo os registros deste período…';
    try {
      const result=await request('exclusao-previa?'+new URLSearchParams({bank:bank.value,period:period.value}));if(!result)return;
      prepared={...result.data,company:result.company,version:result.version};
      summary.textContent=`Empresa ${result.company} · ${label(prepared.bank)} · ${periodLabel(prepared.period)}: ${prepared.affected} registro(s) afetado(s). ${prepared.removed} será(ão) removido(s); ${prepared.retained} continuará(ão) na base pelos outros períodos.`;
      box.hidden=false;message.textContent='Confira o recorte acima antes de confirmar.';
    } catch(error){if(version===revision)report(error);}
    finally {if(version===revision)preview.disabled=!bank.value||!period.value;}
  });
  confirm.addEventListener('click',async()=> {
    const target=prepared;
    if(!target || target.version!==revision || target.company!==selected?.codigo || target.bank!==bank.value || target.period!==period.value)return;
    confirm.disabled=true;preview.disabled=true;load.disabled=true;const version=revision;
    message.textContent='Excluindo o período selecionado…';
    try {
      const result=await request('excluir-recorte',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bank:target.bank,period:target.period,token:target.token})});
      if(!result)return;
      message.textContent=`Aprendizado de ${label(target.bank)} · ${periodLabel(target.period)} excluído da empresa ${target.company}. Os demais períodos e bancos foram preservados.`;
      refreshBaseStats();await loadSlices(true);
    } catch(error){if(version===revision){invalidate();report(error);}}
    finally {if(version===revision){confirm.disabled=false;load.disabled=false;preview.disabled=!bank.value||!period.value;}}
  });
})();
