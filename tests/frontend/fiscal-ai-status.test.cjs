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
    aiButton:{disabled:true},aiMessage:{textContent:''},aiResult:{children:[]},aiProvider:{textContent:''},
    fetch:async (url,options)=>{assert.equal(options.cache,'no-store');assert.match(url,/status\?t=/);return {ok:true,json:async()=>({configurado:configured})};}};
  vm.createContext(context);vm.runInContext(code,context);
  await context.refreshAIStatus(); assert.equal(context.aiButton.disabled,true);
  configured = true;
  await context.refreshAIStatus(); assert.equal(context.aiButton.disabled,false);
  assert.match(context.aiMessage.textContent,/Gemini configurado/);
  assert.equal(context.aiProvider.textContent, 'Gemini');
});

test('falha de rede não é apresentada como chave ausente',async () => {
  const context = {AbortController,Date,setTimeout:()=>1,clearTimeout:()=>{},
    API:()=>'/api',aiConfigured:false,previewBody:null,aiController:null,
    aiButton:{disabled:true},aiMessage:{textContent:''},aiResult:{children:[]},aiProvider:{textContent:''},
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


test('busca da conferência localiza contas, acumuladores e descrições sem perder filtros', () => {
  const start = source.indexOf('  function normalizeSearch(value) {');
  const end = source.indexOf('  function renderDetails(row) {', start);
  assert.ok(start >= 0 && end > start);
  const entries = [
    {conta:'22643', descricao:'Mercadorias para revenda', tipo:'ENTRADAS',
     acumuladores:'1152', detalhes_fiscais:[{codigo:'1152',descricao:'COMPRAS PARA REVENDA'}],situacao:'REVISAR'},
    {conta:'361', descricao:'Honorários contábeis', tipo:'SERVIÇOS',
     acumuladores:'404', detalhes_fiscais:[{codigo:'404',descricao:'Prestação de serviços'}],situacao:'CONFERE'},
    {conta:'470', descricao:'Fretes', tipo:'ENTRADAS',
     acumuladores:'517', detalhes_fiscais:[{codigo:'517',descricao:'Frete do mês'}],situacao:'CONFERE COM ALERTAS'}
  ];
  const input = {value:''};
  const filter = {value:'todas'};
  const context = {data:{contas:entries},filter,search:input,
    accumulatorRows:row=>row.detalhes_fiscais};
  vm.createContext(context);
  vm.runInContext(source.slice(start,end),context);
  assert.equal(context.filteredRows().length,3);
  input.value='1152';
  assert.deepEqual(Array.from(context.filteredRows(),row=>row.conta),['22643']);
  input.value='honorarios';
  assert.deepEqual(Array.from(context.filteredRows(),row=>row.conta),['361']);
  input.value='Frete';
  filter.value='alertas';
  assert.deepEqual(Array.from(context.filteredRows(),row=>row.conta),['470']);
  filter.value='revisar';
  assert.equal(context.filteredRows().length,0);
});

test('tabela compacta preserva acumuladores e reserva totais técnicos para detalhes', () => {
  const html = fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
  const match = html.match(/<table class="fiscal-table">([\s\S]*?)<\/table>/);
  assert.ok(match);
  const headings = [...match[1].matchAll(/<th\b[^>]*>([^<]+)<\/th>/g)].map(x=>x[1]);
  assert.deepEqual(headings,[
    'Conta / descrição','Acumuladores','Fiscal','Contábil considerado','Diferença','Situação'
  ]);
  assert.ok(html.includes('id="fiscal242Search"'));
  assert.ok(html.includes('id="fiscal242Detail"'));
  assert.ok(html.includes('id="fiscal242CompanyName"'));
  assert.ok(!html.includes('id="fiscalEmpresaCodigo"'));
  assert.match(source, /money\.format\(row\.contabil\).*fiscal-money-accounting/);
  assert.ok(html.includes('id="fiscal242Count"'));
  const renderTable = source.slice(source.indexOf('  function renderTable() {'),
    source.indexOf('  function renderResponse(report) {'));
  assert.ok(renderTable.includes('renderDetails(rows.find(row => keyOf(row) === selectedKey) || null)'));
  assert.doesNotMatch(renderTable,/selectedKey\s*=\s*keyOf\(rows\[0\]\)/);
});


test('painel moderno inclui cartões, indicadores e lançamentos sob demanda', () => {
  const html = fs.readFileSync(path.join(__dirname, '../../index.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../../assets/css/fiscal-242.css'), 'utf8');
  for (const id of ['fiscal242Total', 'fiscal242Matches', 'fiscal242Alerts',
                    'fiscal242Pending', 'fiscal242ProgressMatches',
                    'fiscal242ProgressAlerts', 'fiscal242ProgressPending']) {
    assert.ok(html.includes('id="' + id + '"'), 'Faltou ' + id);
  }
  assert.match(source, /fiscal-ledger-disclosure/);
  assert.match(css, /fiscal-detail-metric-accounting/);
  assert.match(source, /fiscal242ProgressMatches/);
  assert.match(css, /@media\(max-width:760px\)/);
  assert.match(css, /fiscal-results-card \.fiscal-table tbody tr \{\s*display:grid/);
  assert.ok(html.includes('fiscal-summary-card'), 'Cards de resumo não encontrados');
});

test('Gemini apresenta parecer por etapas e checklist sem tratar texto como HTML', () => {
  const start = source.indexOf('  function renderNarrative(textValue) {');
  const end = source.indexOf('  function normalizeAISearch(value) {', start);
  assert.ok(start >= 0 && end > start);
  const node = (tag, className, value) => ({
    tag, className, textContent: value === undefined ? '' : String(value),
    children: [], append(...entries) { this.children.push(...entries); },
    appendChild(entry) { this.children.push(entry); }
  });
  const context = {node};
  vm.createContext(context);
  vm.runInContext(source.slice(start,end), context);
  const explanation = context.renderNarrative(
    'Fatos da conta.\n\nHipótese baseada na divergência.\n\nVerificação necessária.\n\nLimites do relatório.'
  );
  assert.equal(explanation.children.length, 4);
  assert.equal(explanation.children[0].children[0].textContent, 'O que foi encontrado');
  assert.equal(explanation.children[3].children[0].textContent, 'Limitações e cuidados');
  const checklist = context.renderChecklist('1. Confira NF.\n2. Valide o acumulador.\n3. Compare o Razão.');
  const steps = checklist.children[0].children;
  assert.equal(steps.length, 3);
  assert.equal(steps[0].textContent, 'Confira NF.');
  const malicious = context.renderNarrative('<script>alert(1)</script>');
  assert.equal(malicious.children[0].textContent, '<script>alert(1)</script>');
});


test('Gemini exibe análise diretamente na página sem painel flutuante', () => {
  const html = fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
  const css = fs.readFileSync(path.join(__dirname,'../../assets/css/fiscal-242.css'),'utf8');
  const segment = html.slice(html.indexOf('<section class="fiscal-ai">'),html.indexOf('<div class="fiscal-download-row">'));
  for (const id of ['fiscal242AI','fiscal242AIExport','fiscal242AIMessage','fiscal242AIResult']) {
    assert.ok(segment.includes('id="' + id + '"'),id);
  }
  assert.ok(segment.indexOf('id="fiscal242AIResult"') > segment.indexOf('id="fiscal242AI"'));
  for (const modal of ['fiscal242AIDrawer','fiscal242AIBackdrop','fiscal242AIBubble','fiscal242AIOpen']) {
    assert.equal(html.includes('id="' + modal + '"'),false);
    assert.equal(source.includes('"' + modal + '"'),false);
  }
  assert.match(css,/#fiscalView #fiscal242AIResult/);
});

test('exportação Gemini usa relatório pronto, sem nova chamada ao modelo', () => {
  const start = source.indexOf('  aiExport.addEventListener("click"');
  const end = source.indexOf('  function renderNarrative',start);
  assert.ok(start >= 0 && end > start);
  const part = source.slice(start,end);
  assert.match(part, /conferencia-fiscal\/ia\/exportar/);
  assert.match(part, /JSON\.stringify/);
  assert.match(part, /current\.analises/);
  assert.match(part, /\.xlsx/);
  assert.doesNotMatch(part, /conferencia-fiscal\/ia"\s*,/);
});




test('Gemini organiza pareceres completos em contas recolhíveis sem interface flutuante', () => {
  const html = fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
  const css = fs.readFileSync(path.join(__dirname,'../../assets/css/fiscal-242.css'),'utf8');
  for(const id of ['fiscal242AIToolbar','fiscal242AISearch','fiscal242AIFilter',
                   'fiscal242AICount','fiscal242AIExpand','fiscal242AICollapse','fiscal242AIEmpty']) {
    assert.ok(html.includes('id="' + id + '"'), 'Controle não encontrado: ' + id);
  }
  assert.match(source,/node\("details", "fiscal-ai-card fiscal-ai-account"\)/);
  assert.match(source,/node\("summary", "fiscal-ai-card-heading fiscal-ai-account-summary"\)/);
  assert.match(source,/content\.appendChild\(accumulatorInfo\)/);
  assert.match(source,/content\.append\(analysis, review\)/);
  assert.match(source,/content\.append\(details\)/);
  assert.match(source,/aiResult\.append\(card\)/);
  assert.match(css,/\.fiscal-ai-account-summary\s*\{/);
  assert.match(css,/\.fiscal-ai-account-content/);
  assert.doesNotMatch(html,/id="fiscal242AIBubble"|id="fiscal242AIDrawer"/);
});

test('filtro do Gemini localiza explicação e evidência sem descartar análises', () => {
  const start = source.indexOf('  function normalizeAISearch(value) {');
  const end = source.indexOf('  aiSearch.addEventListener("input"', start);
  assert.ok(start > -1 && end > start);
  const context = {};
  vm.createContext(context);
  vm.runInContext(source.slice(start,end).split('  function updateAIFilters() {')[0], context);
  const cards = [
    {item:{conta:'22643',descricao:'Mercadorias',tipo:'ENTRADAS',situacao:'REVISAR',
      explicacao:'A diferença pode envolver compra CF NF 20',
      verificar:'1. Validar NF',evidencias:[{historico:'Estorno em agosto',referencia:'ABC'}]}},
    {item:{conta:'361',descricao:'Serviços prestados',tipo:'SAÍDAS',situacao:'CONFERE',
      explicacao:'Operação confere',verificar:'1. Arquivar comprovação',evidencias:[]}},
    {item:{conta:'470',descricao:'Fretes',tipo:'ENTRADAS',situacao:'CONFERE COM ALERTAS',
      explicacao:'Verificar contrapartida',verificar:'1. Conferir frete',evidencias:[]}}
  ];
  assert.equal(context.filterAIEntries(cards,'','todas').length,3);
  assert.equal(context.filterAIEntries(cards,'compra cf nf','todas').length,1);
  assert.equal(context.filterAIEntries(cards,'estorno','todas').length,1);
  assert.equal(context.filterAIEntries(cards,'servicos','bate').length,1);
  assert.equal(context.filterAIEntries(cards,'','alertas').length,1);
  assert.equal(context.filterAIEntries(cards,'','revisar').length,1);
  assert.equal(context.filterAIEntries(cards,'sem correspondência','todas').length,0);
  assert.equal(cards.length,3);
});


test('status exibe OpenRouter no campo quando nova chave esta conectada',async () => {
  const context = {AbortController,Date,setTimeout:()=>1,clearTimeout:()=>{},
    API:()=>'/api',aiConfigured:false,previewBody:{},aiController:null,
    aiButton:{disabled:true},aiMessage:{textContent:''},aiResult:{children:[]},
    aiProvider:{textContent:''},
    fetch:async()=>({ok:true,json:async()=>({configurado:true,provedor:'openrouter',gratuito:true})})};
  vm.createContext(context);
  vm.runInContext(code,context);
  await context.refreshAIStatus();
  assert.equal(context.aiButton.disabled,false);
  assert.equal(context.aiProvider.textContent,'OpenRouter · gratuito');
  assert.match(context.aiMessage.textContent,/OpenRouter configurado/);
});


test('IA fiscal exibe progresso e cancelamento sem tela flutuante', () => {
  const html = fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
  const css = fs.readFileSync(path.join(__dirname,'../../assets/css/fiscal-242.css'),'utf8');
  assert.match(source,/const aiCancelButton = node\("button", "secondary-action fiscal-ai-cancel", "Cancelar"\)/);
  assert.match(source,/aiCancelButton\.addEventListener\("click"/);
  assert.match(source,/aiController\.abort\(\)/);
  assert.match(source,/progressTimer = window\.setInterval/);
  assert.match(source,/window\.clearInterval\(progressTimer\)/);
  assert.match(css,/\.fiscal-ai-cancel\[hidden\]/);
  assert.doesNotMatch(html,/id="fiscal242AIDrawer"/);
});


test("botão de teste OpenRouter não aparece na conferência fiscal", () => {
  assert.doesNotMatch(source,/Testar OpenRouter/);
  assert.doesNotMatch(source,/teste-openrouter/);
  const html = fs.readFileSync(path.join(__dirname,"../../index.html"),"utf8");
  assert.match(html,/Analisar diferenças com IA/);
  assert.match(source,/Atualizar conexão/);
});


function batchContext(fetch) {
  const context = {fetch, AbortController, DOMException, Map, Set, API:()=>'/api',
    responseError:async response=>response.error || 'Falha no provedor'};
  vm.createContext(context);
  const start = source.indexOf('  async function analyzeInBatches(');
  const end = source.indexOf('  const aiCancelButton =', start);
  vm.runInContext(source.slice(start,end), context);
  return context;
}

test('lotes executam Gemini e Groq juntos, sem duas chamadas simultâneas no mesmo provedor', async()=>{
  const active = new Set(); const maxima = []; const progress = []; const calls=[];
  const manifest={sessao:'ficticia', grupos:8, registros:2001, lotes:[
    {id:0,provedor:'groq',grupos:2}, {id:1,provedor:'gemini',grupos:2},
    {id:2,provedor:'groq',grupos:2}, {id:3,provedor:'gemini',grupos:2}]};
  const context = batchContext(async (url, options)=>{
    calls.push(url);
    if (options.method==='DELETE') return {ok:true};
    if (url.endsWith('/sessoes')) return {ok:true,json:async()=>manifest};
    const id = Number(url.split('/').pop()); const provider=manifest.lotes[id].provedor;
    assert.ok(!active.has(provider)); active.add(provider); maxima.push(active.size);
    await new Promise(resolve=>setImmediate(resolve));
    active.delete(provider);
    return {ok:true,json:async()=>({provedor:provider,gratuito:true,modelo_usado:provider,
      analises:[{conta:String(id*2)},{conta:String(id*2+1)}]})};
  });
  const result = await context.analyzeInBatches({},new AbortController(),(...args)=>progress.push(args));
  assert.equal(Math.max(...maxima),2);
  assert.equal(result.analises.length,8);
  assert.deepEqual(Array.from(result.analises,a=>a.conta),['0','1','2','3','4','5','6','7']);
  assert.equal(result.provedor,'cooperacao');
  assert.equal(result.gratuito,true);
  assert.match(result.limite,/2001 registros/);
  assert.equal(calls.filter(url=>url.endsWith('/sessoes')).length,1);
  assert.deepEqual(progress.at(-1),[8,8,0]);
});

test('falha de um lote mantém os pareceres concluídos e informa análise parcial',async()=>{
  const manifest={sessao:'ficticia', grupos:4, registros:2001, lotes:[
    {id:0,provedor:'groq',grupos:2},{id:1,provedor:'gemini',grupos:2}]};
  const context=batchContext(async (url,options)=>{
    if(options.method==='DELETE')return {ok:true};
    if(url.endsWith('/sessoes'))return {ok:true,json:async()=>manifest};
    if(url.endsWith('/1'))return {ok:false,error:'Cota Gemini esgotada'};
    return {ok:true,json:async()=>({provedor:'groq',gratuito:true,analises:[{conta:'1'},{conta:'2'}]})};
  });
  const result=await context.analyzeInBatches({},new AbortController(),()=>{});
  assert.equal(result.analises.length,2);
  assert.match(result.aviso,/Análise parcial: 2 de 4/);
  assert.match(result.aviso,/Cota Gemini esgotada/);
});

test('publicação gradual usa endpoint anterior enquanto API de sessões não está pronta',async()=>{
  const calls=[];
  const context=batchContext(async(url,options)=>{
    calls.push(url);
    if(url.endsWith('/sessoes'))return {ok:false,status:404};
    return {ok:true,json:async()=>({analises:[{conta:'1'}],provedor:'groq'})};
  });
  const result=await context.analyzeInBatches({},new AbortController(),()=>{});
  assert.equal(result.analises.length,1);
  assert.deepEqual(calls,['/api/api/v1/conferencia-fiscal/ia/sessoes','/api/api/v1/conferencia-fiscal/ia']);
});
