/* A senha existe apenas na memória desta página e é limpa ao trocar de empresa. */
(() => {
  const dialog=document.getElementById('adminAuthDialog'), form=document.getElementById('adminAuthForm');
  const input=document.getElementById('adminAccess'), error=document.getElementById('adminAuthError');
  let cached='', pending=null, previousFocus=null;
  const aborted=()=>new DOMException('Ação administrativa cancelada.','AbortError');
  function finish(token) {
    if(!pending)return;
    const waiting=pending;pending=null;input.value='';dialog.close();
    previousFocus?.focus?.();previousFocus=null;
    if(token)waiting.resolve(token);else waiting.reject(aborted());
  }
  window.clearAdminAccess=()=>{cached='';finish(null);input.value='';};
  window.requestAdminAccess=(retry=false)=> {
    if(cached && !retry)return Promise.resolve(cached);
    if(pending)return pending.promise;
    cached='';input.value='';error.hidden=!retry;
    error.textContent=retry?'Senha inválida. Confira e tente novamente.':'';
    previousFocus=document.activeElement;
    const promise=new Promise((resolve,reject)=>{pending={resolve,reject};});
    pending.promise=promise;dialog.showModal();input.focus();return promise;
  };
  form.addEventListener('submit',event=> {
    event.preventDefault();if(!form.reportValidity())return;
    cached=input.value;finish(cached);
  });
  for(const id of ['adminAuthClose','adminAuthCancel'])document.getElementById(id).addEventListener('click',()=>finish(null));
  dialog.addEventListener('cancel',event=>{event.preventDefault();finish(null);});
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)finish(null);}});
  window.adminFetch=async(url,options={},isCurrent=()=>true)=> {
    let retry=false;
    for(;;) {
      if(!isCurrent()||options.signal?.aborted)throw aborted();
      const token=await window.requestAdminAccess(retry);
      if(!isCurrent()||options.signal?.aborted)throw aborted();
      const response=await fetch(url,{...options,headers:{...(options.headers||{}),Authorization:`Bearer ${token}`}});
      if(!isCurrent()||options.signal?.aborted)throw aborted();
      if(response.status!==401)return response;
      cached='';retry=true;
    }
  };
})();
