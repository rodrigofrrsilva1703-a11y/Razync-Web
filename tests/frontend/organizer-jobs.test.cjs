const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/organizer-jobs.js','utf8');

function setup(fetch){
  const context={fetch,API:()=> 'https://test',DOMException,AbortController,
    responseError:async r=>`HTTP ${r.status}`,setTimeout:fn=>setTimeout(fn,0),clearTimeout};
  vm.createContext(context);vm.runInContext(source,context);return context.RazyncOrganizer;
}
const accepted={status:202,json:async()=>({job_token:'secret'})};

test('acompanha o mesmo lote e busca o resultado sem reenviar anexos',async()=>{
  const calls=[],stages=[]; let count=0;
  const result={ok:true,status:200};
  const organizer=setup(async(url,options)=>{
    calls.push([url,options]);
    if(url.endsWith('/resultado'))return result;
    return {ok:true,json:async()=>({state:++count===1?'processing':'ready',current:1,total:3})};
  });
  assert.equal(await organizer.wait(accepted,{onProgress:s=>stages.push(s.state)}),result);
  assert.deepEqual(stages,['processing','ready']);
  assert.equal(calls.length,3);
  assert.ok(calls.every(([,options])=>!options.body && !options.method));
});

test('cancelar a espera sinaliza cancelamento ao servidor',async()=>{
  const controller=new AbortController();const calls=[];
  const organizer=setup(async(url,options)=>{
    calls.push(options.method||'GET');
    return {ok:true,json:async()=>({state:'processing'})};
  });
  await assert.rejects(organizer.wait(accepted,{signal:controller.signal,onProgress:()=>controller.abort()}),{name:'AbortError'});
  assert.deepEqual(calls,['GET','DELETE']);
});

test('erro ou expiração não reiniciam o processamento automaticamente',async()=>{
  let calls=0;
  const organizer=setup(async()=>{calls++;return {ok:false,status:404};});
  await assert.rejects(organizer.wait(accepted),/expirou/);
  assert.equal(calls,1);
});

test('anexar vários arquivos prepara o lote sem disparar processamento',()=>{
  const app=fs.readFileSync('assets/js/app.js','utf8');
  const start=app.indexOf('function scheduleAutomaticPreview()');
  const end=app.indexOf('form.addEventListener("change", scheduleAutomaticPreview)',start);
  const form={querySelectorAll:()=>[],checkValidity:()=>true,requestSubmit:()=>{throw Error('Não deve gerar automaticamente');}};
  const message={textContent:''};const stages=[];
  const context={cancelAutomaticPreview:()=>{},updateUploadProgress:()=>{},processMessage:message,
    $:()=>({replaceChildren:()=>{}}),selected:{capabilities:{workflow:'advanced'}},
    form,readPeriod:()=>({}),setProcessStage:(...args)=>stages.push(args),
    setTimeout:()=>{throw Error('Não deve agendar lote');},fileInput:{files:[{},{}]}};
  form.querySelectorAll=()=>[{required:false,disabled:false,files:[{},{}]}];
  vm.createContext(context);vm.runInContext(app.slice(start,end)+'\nscheduleAutomaticPreview();',context);
  assert.equal(stages.at(-1)[1],'2 arquivo(s) prontos');
});
