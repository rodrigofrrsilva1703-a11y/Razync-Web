const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.events={};this.attrs={};this.hidden=false;this.value='';this.checked=false;this.classes=new Set();this.classList={contains:k=>this.classes.has(k),toggle:k=>{if(this.classes.has(k)){this.classes.delete(k);return false;}this.classes.add(k);return true;}};}
 append(...items){this.children.push(...items);} after(item){this.afterNode=item;} replaceChildren(...items){this.children=items;} setAttribute(k,v){this.attrs[k]=v;} addEventListener(k,v){this.events[k]=v;} focus(){this.focused=true;} hasChildNodes(){return this.children.length>0;}
 querySelectorAll(selector){return flatten(this).filter(e=>selector==='button'?e.tag==='button':['button','input'].includes(e.tag));}
}
function flatten(e){return e.children.flatMap(child=>typeof child==='object'?[child,...flatten(child)]:[]);}
function setup(){
 const nodes={'#classifyForm':new Element(),'#companyPanel':new Element(),'[data-pane="base"]':new Element(),'.app-shell':new Element()};nodes['[data-pane="base"]'].classes.add('active');
 const observers=[];let resolve;const pending=new Promise(r=>resolve=r);const requests=[];
 const ctx={document:{createElement:t=>new Element(t),createTextNode:t=>t,querySelector:s=>nodes[s]},MutationObserver:class{constructor(fn){observers.push(fn);}observe(){}},AbortController,FormData,Blob,
 API:()=>'',fetch:(url,options)=>{requests.push({url,options});return pending;},responseError:async()=>'',bankName:b=>b};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('assets/js/base-investigation.js','utf8'),ctx);
 const host=nodes['.app-shell'].children[0],launcher=host.children[0],window=host.children[1],header=window.children[0],body=window.children[1];
 const mount=()=>ctx.RazyncBaseInvestigation.mount({company:242,prepared:{blob:async()=>new Blob(['synthetic'])},options:{},summary:{cobertura:{pendentes:1}}});
 return {ctx,nodes,observers,resolve,requests,launcher,window,header,body,mount};
}
const report={total_pendencias:1,grupos_investigados:1,ia:{},limitacoes:[],token:'synthetic',catalogo_contas:[{conta:'412',natureza:'pago',bancos:['itau_508'],periodos:['2026-07'],ocorrencias:2,exemplos:[{historico:'Pago fornecedor de teste',banco:'itau_508',periodos:['2026-07'],ocorrencias:2}]}],sugestoes:[{_aba:'Itaú',_linha:2,natureza:'pago','Histórico':'Teste',Valor:-1,Data:'15/10/2026',grupo:1,conta_sugerida:'412',situacao:'MODERADA',justificativa:'Evidência',evidencias:[]}]};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function populated(){const h=setup();h.mount();h.launcher.events.click();await flush();h.resolve({ok:true,json:async()=>report});await flush();return h;}
test('janela inicia fechada e abre pelo botão flutuante sem chamada duplicada',async()=>{const h=await populated();assert.equal(h.window.hidden,false);assert.equal(h.requests.length,1);h.header.children[1].children[1].events.click();assert.equal(h.window.hidden,true);h.launcher.events.click();await flush();assert.equal(h.requests.length,1);});
test('minimizar e ampliar preservam aprovação e aprendizado começa desmarcado',async()=>{const h=await populated();const inputs=flatten(h.body).filter(e=>e.tag==='input');const approve=inputs.find(e=>e.attrs['aria-label']?.startsWith('Aprovar'));approve.checked=true;const learn=inputs.find(e=>e.type==='checkbox'&&!e.attrs['aria-label']);assert.equal(learn.checked,false);h.header.children[1].children[0].events.click();assert.equal(h.window.classList.contains('is-expanded'),true);h.header.children[1].children[1].events.click();h.launcher.events.click();assert.equal(approve.checked,true);});
test('histórico da conta mostra o exemplo aprendido sem consultar IA novamente',async()=>{const h=await populated();const button=flatten(h.body).find(e=>e.textContent==='Histórico da conta');button.events.click();const text=flatten(h.body).map(e=>e.textContent||'').join(' ');assert.match(text,/Pago fornecedor de teste/);assert.match(text,/2026-07/);assert.equal(h.requests.length,1);});
test('trocar ferramenta oculta a janela e reset invalida resultados em andamento',async()=>{const h=setup();h.mount();h.launcher.events.click();await flush();h.nodes['[data-pane="base"]'].classes.clear();h.observers[0]();assert.equal(h.window.hidden,true);assert.equal(h.launcher.hidden,true);h.ctx.RazyncBaseInvestigation.reset();h.resolve({ok:true,json:async()=>report});await flush();assert.equal(h.body.children.length,0);assert.equal(h.window.hidden,true);});
