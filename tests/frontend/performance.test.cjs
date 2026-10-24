const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
const source=fs.readFileSync('assets/js/workbook-result.js','utf8');
function setup(responses){const calls=[],downloads=[];const context={API:()=>'/api',Response,FormData,Blob,
 responseError:async()=> 'failure',downloadBlob:async(r,n)=>downloads.push({r,n}),
 fetch:async(url,options)=>{calls.push({url,options});const next=responses.shift();if(next instanceof Error)throw next;return next;}};
 vm.createContext(context);vm.runInContext(source,context);return {context,calls,downloads};}
test('resultado pronto evita reenviar Excel e baixa pelo token',async()=>{
 const h=setup([new Response('xlsx')]);const original=new Response(JSON.stringify({preview:{sheets:[{name:'Banco'}]},report_token:'random-token'}),{headers:{'Content-Type':'application/vnd.razync.preview+json'}});
 const result=await h.context.RazyncResults.workbookPreview(original,{endpoint:'/process',snapshot:'files',filename:'report.xlsx'});
 assert.equal(h.calls.length,0);assert.equal(result.preview.sheets[0].name,'Banco');await result.download();
 assert.equal(h.calls.length,1);assert.match(h.calls[0].url,/resultados\/random-token$/);assert.equal(h.downloads.length,1);
});
test('token expirado recalcula com o mesmo snapshot',async()=>{
 const h=setup([new Response('',{status:404}),new Response('new')]);const snapshot={files:'same',period:'same'};
 await h.context.RazyncResults.downloadResponse('expired','/original',{method:'POST',body:snapshot});
 assert.equal(h.calls.length,2);assert.equal(h.calls[1].options.body,snapshot);
});
test('cancelamento e bloqueio de acesso não disparam recálculo',async()=>{
 const h=setup([new Response('',{status:503})]);const response=await h.context.RazyncResults.downloadResponse('token','/original');
 assert.equal(response.status,503);assert.equal(h.calls.length,1);
 const aborted=setup([Object.assign(new Error('cancelled'),{name:'AbortError'})]);
 await assert.rejects(()=>aborted.context.RazyncResults.downloadResponse('token','/original'),{name:'AbortError'});
 assert.equal(aborted.calls.length,1);
});
test('API anterior continua gerando prévia e mantendo download local',async()=>{
 const h=setup([new Response(JSON.stringify({sheets:[{name:'Antigo'}]}))]);
 const result=await h.context.RazyncResults.workbookPreview(new Response('xlsx'),{endpoint:'/old',filename:'old.xlsx'});
 assert.equal(result.preview.sheets[0].name,'Antigo');assert.match(h.calls[0].url,/modelo-preview$/);
 await result.download();assert.equal(h.calls.length,1);assert.equal(h.downloads[0].n,'old.xlsx');
});

test('carregamento opcional compartilha solicitação, mantém ordem e permite repetição após falha',async()=>{
 const events=[];let fail=true;
 const style={tagName:'LINK',dataset:{},handlers:{},addEventListener(name,fn){this.handlers[name]=fn;},set rel(value){if(value==='stylesheet'){events.push('style');queueMicrotask(()=>this.handlers.load());}}};
 const script={tagName:'SCRIPT',dataset:{},getAttribute:()=>'/tool.js'};
 const context={document:{querySelectorAll:()=>[style,script],createElement:()=>({handlers:{},addEventListener(name,fn){this.handlers[name]=fn;},remove(){}}),
 body:{appendChild(el){events.push('script');queueMicrotask(()=>{if(fail){fail=false;el.handlers.error();}else el.handlers.load();});}}}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('assets/js/lazy-assets.js','utf8'),context);
 assert.equal(context.RazyncAssets.isLoaded('fiscal'),false);
 const first=context.RazyncAssets.load('fiscal');assert.equal(first,context.RazyncAssets.load('fiscal'));
 await assert.rejects(first);await context.RazyncAssets.load('fiscal');await context.RazyncAssets.load('fiscal');
 assert.equal(context.RazyncAssets.isLoaded('fiscal'),true);
 assert.deepEqual(events,['style','script','script']);assert.equal(script.dataset.loaded,'true');
});
