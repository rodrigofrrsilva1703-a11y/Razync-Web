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

for (const workflow of ['standard', 'standard_multi_bank', 'advanced']) {
  for (const count of [0, 1, 3]) {
    test(`organizar ${workflow}: ${count} arquivo(s) aguardam clique sem agendar requisição`, () => {
      const app=fs.readFileSync('assets/js/app.js','utf8');
      const start=app.indexOf('function prepareOrganizerPreview()');
      const end=app.indexOf('form.addEventListener("change", prepareOrganizerPreview)',start);
      const input={required:true,disabled:false,files:Array.from({length:count},()=>({}))};
      const stages=[];let cancelled=0,cleared=0;
      const context={cancelOrganizerPreview:()=>cancelled++,updateUploadProgress:()=>{},
        processMessage:{textContent:'prévia anterior'},$:()=>({replaceChildren:()=>cleared++}),
        selected:{capabilities:{workflow}},fileInput:input,
        form:{querySelectorAll:()=>[input],checkValidity:()=>true,
          requestSubmit:()=>{throw Error('Não deve enviar automaticamente');}},
        readPeriod:()=>({}),setProcessStage:(...args)=>stages.push(args),
        setTimeout:()=>{throw Error('Não deve agendar processamento');},
        fetch:()=>{throw Error('Não deve enviar arquivos');}};
      vm.createContext(context);
      vm.runInContext(app.slice(start,end)+'\nprepareOrganizerPreview();',context);
      assert.equal(cancelled,1);
      assert.equal(cleared,1);
      assert.equal(context.processMessage.textContent,'');
      assert.equal(stages.at(-1)[0],'upload');
      assert.match(stages.at(-1)[2],/Gerar prévia/);
      if(count)assert.equal(stages.at(-1)[1],`${count} arquivo(s) prontos`);
    });
  }
}
