const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
const source=fs.readFileSync('assets/js/app.js','utf8');
function setup(){
  const button={disabled:false},message={textContent:''};let handler,resolveResponse;const calls=[],stats=[],periodRefreshes=[];
  const scope={learnForm:{querySelector:()=>button,addEventListener:(type,fn)=>handler=fn},
    $:selector=>selector==='#learnFiles'?{files:[{name:'one.xlsx'}]}:message,
    window:{refreshSavedBasePeriods:()=>periodRefreshes.push(true)},FormData:class{append(){}},selected:{codigo:3},API:()=>'/api',
    fetch:(url,options)=>{calls.push(url);return new Promise(resolve=>resolveResponse=resolve);},
    responseError:async()=> 'failed',refreshBaseStats:result=>stats.push(result)};
  vm.createContext(scope);vm.runInContext(source.slice(source.indexOf('learnForm.addEventListener("submit"'),source.indexOf('\nlet eletro242ClassificationMode')),scope);
  return {scope,button,message,calls,stats,periodRefreshes,run:()=>handler({preventDefault(){}}),finish:result=>resolveResponse({ok:true,json:async()=>result})};
}
test('aprendizado impede cliques duplicados e reaproveita os totais da resposta',async()=>{
 const state=setup();const pending=state.run();assert.equal(state.button.disabled,true);
 await state.run();assert.equal(state.calls.length,1);
 const result={learned:193,patterns:180,banks:1,periods:2,errors:['two.xlsx: inválido']};
 state.finish(result);await pending;
 assert.equal(state.button.disabled,false);assert.equal(state.stats[0],result);assert.equal(state.periodRefreshes.length,1);
 assert.match(state.message.textContent,/two.xlsx: inválido/);
});
test('resultado do aprendizado anterior não altera outra empresa',async()=>{
 const state=setup();const pending=state.run();state.scope.selected={codigo:88};
 state.message.textContent='Nova empresa';state.finish({learned:193});await pending;
 assert.equal(state.stats.length,0);assert.equal(state.periodRefreshes.length,0);assert.equal(state.message.textContent,'Nova empresa');
 assert.equal(state.button.disabled,false);
});
