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
  const end = source.indexOf('  aiButton.addEventListener("click"', start);
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


