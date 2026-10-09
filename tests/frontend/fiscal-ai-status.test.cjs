const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../../assets/js/fiscal-242.js'),'utf8');
const code = source.slice(source.indexOf('  let statusController = null;'),source.indexOf('  const refreshConnection ='));

test('status Gemini reconhece chave adicionada após abrir o site, sem cache',async () => {
  let configured = false;
  const context = {AbortController,Date,setTimeout:()=>1,clearTimeout:()=>{},
    API:()=>'/api',aiConfigured:false,previewBody:{},aiController:null,
    aiButton:{disabled:true},aiMessage:{textContent:''},aiResult:{children:[]},
    fetch:async (url,options)=>{assert.equal(options.cache,'no-store');assert.match(url,/status\?t=/);return {ok:true,json:async()=>({configurado:configured})};}};
  vm.createContext(context);vm.runInContext(code,context);
  await context.refreshAIStatus(); assert.equal(context.aiButton.disabled,true);
  configured = true;
  await context.refreshAIStatus(); assert.equal(context.aiButton.disabled,false);
  assert.match(context.aiMessage.textContent,/Gemini conectado/);
});

test('falha de rede não é apresentada como chave ausente',async () => {
  const context = {AbortController,Date,setTimeout:()=>1,clearTimeout:()=>{},
    API:()=>'/api',aiConfigured:false,previewBody:null,aiController:null,
    aiButton:{disabled:true},aiMessage:{textContent:''},aiResult:{children:[]},
    fetch:async()=>({ok:false})};
  vm.createContext(context);vm.runInContext(code,context);
  await context.refreshAIStatus();
  assert.match(context.aiMessage.textContent,/Não foi possível verificar/);
  assert.doesNotMatch(context.aiMessage.textContent,/não configurado/);
});
