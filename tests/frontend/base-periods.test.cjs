const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function setup(fetcher) {
 const nodes=new Map(),calls=[];
 const element=()=>({children:[],attributes:{},textContent:'',hidden:false,disabled:false,
  appendChild(child){this.children.push(child);},replaceChildren(){this.children=[];},
  setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,fn){this[k]=fn;}});
 const node=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
 const scope={document:{getElementById:node,createElement:element},AbortController,
  selected:{codigo:242,capabilities:{status:'api_ready'}},API:()=>'/api',bankName:x=>x,
  responseError:async()=> 'Falha na consulta',window:{adminFetch:async(url,init,current)=>{
   calls.push({url,init,current});return fetcher?fetcher():{ok:true,json:async()=>({banks:[{bank:'bb',account:'8',periods:['2026-01','2026-03','2026-01']} ]})};
  }}};
 vm.createContext(scope);vm.runInContext(fs.readFileSync('assets/js/base-periods.js','utf8'),scope);
 return {node,scope,calls};
}
test('lista meses reais por banco, sem repetir, por ordem mais recente e usando consulta protegida',async()=>{
 const {node,calls}=setup();await node('loadSavedPeriods').click();
 assert.match(calls[0].url,/242\/recortes$/);assert.equal(calls[0].init.signal.aborted,false);
 const row=node('savedPeriodsList').children[0];assert.equal(row.children[0].textContent,'banco_brasil · conta 8');
 assert.deepEqual(row.children[1].children.map(x=>x.textContent),['03/2026','01/2026']);
 assert.match(node('savedPeriodsMessage').textContent,/parte dos lançamentos/);
});
test('resposta atrasada não mostra períodos da empresa anterior',async()=>{
 let finish;const {node,scope}=setup(()=>new Promise(resolve=>finish=resolve));
 const pending=node('loadSavedPeriods').click();scope.selected={codigo:626,capabilities:{status:'api_ready'}};
 scope.window.resetBaseMaintenance();finish({ok:true,json:async()=>({banks:[{bank:'itau',periods:['2026-05']}]})});await pending;
 assert.equal(node('savedPeriodsList').children.length,0);assert.equal(node('savedPeriodsList').hidden,true);
 assert.equal(node('loadSavedPeriods').disabled,false);
});
test('base vazia e erro de autenticação não são apresentados como meses gravados',async()=>{
 const empty=setup(()=>({ok:true,json:async()=>({banks:[]})}));await empty.node('loadSavedPeriods').click();
 assert.match(empty.node('savedPeriodsMessage').textContent,/não tem períodos/);
 const failed=setup(()=>({ok:false}));await failed.node('loadSavedPeriods').click();
 assert.equal(failed.node('savedPeriodsList').children.length,0);assert.equal(failed.node('savedPeriodsMessage').textContent,'Falha na consulta');
});
