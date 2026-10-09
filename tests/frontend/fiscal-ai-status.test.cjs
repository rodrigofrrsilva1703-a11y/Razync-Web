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


test('tabela e detalhe preservam códigos, descrição e valor de cada acumulador', () => {
  const start = source.indexOf('  function accumulatorRows(row) {');
  const end = source.indexOf('  const keyOf = row =>', start);
  assert.ok(start >= 0 && end > start);
  const node = (tag, className, content) => ({
    tag, className, textContent: content === undefined ? '' : String(content),
    children: [], title: '',
    appendChild(child) { this.children.push(child); },
    get childElementCount() { return this.children.length; }
  });
  const money = new Intl.NumberFormat('pt-BR', {style: 'currency', currency: 'BRL'});
  const context = {node, money};
  vm.createContext(context);
  vm.runInContext(source.slice(start, end), context);
  const row = {conta:'22643', acumuladores:'1152, 1153', detalhes_fiscais:[
    {codigo:'1152',descricao:'Compras para revenda',valor:1000},
    {codigo:'1153',descricao:'Outras compras',valor:234.56}
  ]};
  const codes = context.accumulatorTags(row);
  assert.deepEqual(Array.from(codes.children, x => x.textContent), ['1152','1153']);
  assert.equal(codes.children[0].title, 'Compras para revenda');
  const detail = context.accumulatorBreakdown(row);
  assert.match(detail.children[0].textContent, /conta 22643/);
  const lines = detail.children[1].children;
  assert.equal(lines.length, 2);
  assert.equal(lines[0].children[0].textContent, '1152');
  assert.equal(lines[0].children[1].textContent, 'Compras para revenda');
  assert.match(lines[0].children[2].textContent, /1\.000,00/);
  assert.equal(lines[1].children[0].textContent, '1153');
});
