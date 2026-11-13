const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function setup() {
  const nodes=new Map(),calls=[];
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',children:[],disabled:false,hidden:true,
    replaceChildren(){this.children=[];},appendChild(child){this.children.push(child);},
    addEventListener(event,callback){this[event]=callback;}});return nodes.get(id);};
  const scope={document:{getElementById:node,createElement:()=>({})},window:{},selected:{codigo:3,capabilities:{status:'api_ready'}},
    AbortController,URLSearchParams,API:()=>'/api',adminHeaders:()=>({Authorization:'Bearer test'}),bankName:x=>x,
    refreshBaseStats:()=>{},responseError:async()=> 'Erro',fetch:async(url,init)=>{
      calls.push({url,init});let data;
      if(url.endsWith('/recortes'))data={banks:[{bank:'itau',account:'508',periods:['2026-09']}]};
      else if(url.includes('exclusao-previa'))data={bank:'itau',period:'2026-09',affected:2,removed:1,retained:1,token:'exact-scope'};
      else data={ok:true};
      return {ok:true,json:async()=>data};
    }};
  scope.window.adminFetch=(url,init,current)=>{if(!current())throw new DOMException('Cancelado','AbortError');return scope.fetch(url,init);};
  vm.createContext(scope);vm.runInContext(fs.readFileSync('assets/js/base-maintenance.js','utf8'),scope);
  async function prepare(){await node('loadBaseSlices').click();node('baseCleanupBank').value='itau';node('baseCleanupBank').change();node('baseCleanupPeriod').value='2026-09';node('baseCleanupPeriod').change();await node('previewBaseCleanup').click();}
  return {node,calls,scope,prepare};
}
test('exclusão só é enviada depois da confirmação e contém empresa, banco, período e prévia',async()=>{
  const {prepare,node,calls}=setup();await prepare();assert.equal(calls.filter(x=>x.init.method==='POST').length,0);
  await node('confirmBaseCleanup').click();const sent=calls.find(x=>x.init.method==='POST');
  assert.match(sent.url,/base-inteligente\/3\/excluir-recorte$/);
  assert.deepEqual(JSON.parse(sent.init.body),{bank:'itau',period:'2026-09',token:'exact-scope'});
});
test('troca de empresa invalida a confirmação e limpa os dados exibidos',async()=>{
  const {prepare,node,calls,scope}=setup();await prepare();scope.selected={codigo:178};scope.window.resetBaseMaintenance();
  await node('confirmBaseCleanup').click();assert.equal(calls.filter(x=>x.init.method==='POST').length,0);
  assert.equal(node('baseCleanupConfirmation').hidden,true);assert.equal(node('baseCleanupBank').disabled,true);
});
test('cancelar ou trocar período não exclui os dados da prévia anterior',async()=>{
  const {prepare,node,calls}=setup();await prepare();node('cancelBaseCleanup').click();await node('confirmBaseCleanup').click();
  assert.equal(calls.filter(x=>x.init.method==='POST').length,0);
  await prepare();node('baseCleanupPeriod').value='2026-08';node('baseCleanupPeriod').change();await node('confirmBaseCleanup').click();
  assert.equal(calls.filter(x=>x.init.method==='POST').length,0);
});
