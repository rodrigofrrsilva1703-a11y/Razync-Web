const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/js/fiscal-242.js','utf8');
function setup() {
  class Element {
    constructor(tag, cls='', text='') { this.tag=tag; this.className=cls; this.textContent=String(text); this.children=[]; this.attributes={}; this.events={}; this.value=''; }
    append(...items) {items.forEach(item=>this.appendChild(item));}
    appendChild(item) {this.children.push(item); if(this.tag==='select' && this.children.length===1) this.value=item.value; return item;}
    replaceChildren(...items) {this.children=[];this.append(...items);}
    setAttribute(k,v) {this.attributes[k]=v;}
    addEventListener(k,fn) {this.events[k]=fn;}
    click() {this.events.click?.();}
  }
  const node=(...args)=>new Element(...args); const root=node('div');
  let exported;
  const context={node,investigationResults:root,money:new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}),
    cell:(tr,text,cls)=>tr.appendChild(node('td',cls,text)),Blob,
    URL:{createObjectURL:blob=>{exported=blob;return 'blob:test';},revokeObjectURL:()=>{}},setTimeout:fn=>fn()};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function differenceMeaning('),source.indexOf('  function aiSourceLabel(')),context);
  vm.runInContext(source.slice(source.indexOf('  function investigationStatus('),source.indexOf('  investigationForm.addEventListener')),context);
  const all=(item=root)=>[item,...item.children.flatMap(child=>all(child))];
  const byClass=cls=>all().find(el=>el.className===cls);
  const docs=Array.from({length:1100},(_,i)=>({id:'E-'+i,nota:String(i+1),data:'03/08/2026',serie:'1',
    parceiro:'Fornecedor '+i,situacao:i<1000?'CONCILIADO':'VALOR_DIFERENTE',criterio:'Documento e valores comparados',
    valor_fiscal:100,valor_razao:i<1000?100:110,diferenca:i<1000?0:10,
    linhas_fiscais:[{id:'E-'+i,acumulador:'1152',cfop:'1102',valor:100,linha_origem:i+1}],
    lancamentos:[{id:'R-'+i,data:'03/08/2026',valor:i<1000?100:110,historico:'COMPRA CF NF '+(i+1),contrapartida:'800'}]}));
  const group={composicao:{confere_com_inicial:true,itens:[
      {descricao:'Diferenças nos vínculos',valor:1009.99},{descricao:'Fora da conferência inicial',valor:-9.99},{descricao:'Cobertura',valor:0}]},conta:'508',tipo:'ENTRADAS',descricao:'Compras',fiscal:110000,contabil:111000,diferenca:1000,
    documentos_total:1100,comparacoes:docs,acumuladores:[{codigo:'1152',descricao:'Compras',valor_resumo:110000,valor_documentos:110000,detalhamento_disponivel:true}],razao_sem_vinculo:[]};
  context.renderInvestigation({resumo:{contas:2,conciliados:1000,pendentes:100},contas:[group,{...group,conta:'509',comparacoes:[],documentos_total:0}]});
  return {root,all,byClass,context,exportedBlob:()=>exported};
}
test('investigação mantém todos os resultados navegáveis sem renderizar milhares de linhas',()=>{
  const {all,byClass}=setup();
  const body=()=>all(byClass('fiscal-doc-rows')).find(el=>el.tag==='tbody');
  assert.equal(body().children.length,25);
  assert.match(byClass('fiscal-doc-caption').textContent,/1–25 de 100 registros/);
  byClass('fiscal-doc-pagination').children.find(el=>el.textContent==='Próxima').click();
  assert.match(byClass('fiscal-doc-caption').textContent,/26–50 de 100/);
  const filter=byClass('fiscal-doc-filter'); filter.value='all'; filter.events.change();
  assert.match(byClass('fiscal-doc-caption').textContent,/1–25 de 1100/);
  const search=byClass('fiscal-doc-search'); search.value='1100'; search.events.input();
  assert.equal(body().children.length,1);
  assert.match(byClass('fiscal-doc-caption').textContent,/de 1 registros/);
  assert.equal(all().filter(el=>el.tag==='details').length,0);
});
test('selecionar outra conta reinicia a leitura mantendo a navegação lateral',()=>{
  const {all,byClass}=setup();
  all().filter(el=>el.className==='fiscal-doc-account')[1].click();
  assert.equal(byClass('fiscal-doc-reader').scrollTop,0);
  assert.match(byClass('fiscal-doc-reader').children[0].textContent,/CONTA 509/);
  assert.equal(all().filter(el=>el.className==='fiscal-doc-account').length,2);
  assert.equal(all().filter(el=>el.className==='fiscal-doc-account')[1].attributes['aria-current'],'true');
});


test('exportação inclui o filtro completo e as linhas de origem, além da página visível',async()=>{
  const {byClass,exportedBlob}=setup();
  const filter=byClass('fiscal-doc-filter'); filter.value='all'; filter.events.change();
  byClass('fiscal-doc-export').click();
  const csv=await exportedBlob().text();
  assert.equal(csv.split('\r\n').length,1101);
  assert.match(csv,/Linhas fiscais \/ origem/);
  assert.match(csv,/"1100";"1";"03\/08\/2026"/);
  assert.match(csv,/E-1099 CFOP 1102/);
});


test('composição do total destaca efeitos não nulos e mantém os sinais',()=>{
  const {byClass,all}=setup();
  assert.equal(byClass('fiscal-doc-balance-lines').children.length,2);
  const amounts=all(byClass('fiscal-doc-balance-lines')).filter(el=>el.tag==='strong').map(el=>el.textContent);
  assert.match(amounts[0],/\+ R\$/);
  assert.match(amounts[1],/-R\$/);
  assert.match(all(byClass('fiscal-doc-balance-head')).find(el=>el.tag==='strong').textContent,/1\.000,00/);
});

test('busca por conta exibe fiscal, Razão considerado e diferença sem depender do filtro de pendências',()=>{
  const {byClass,all}=setup();
  const lookup=byClass('fiscal-doc-lookup-input'); lookup.value='508'; lookup.events.input();
  const cells=all(byClass('fiscal-doc-lookup-results')).filter(el=>el.tag==='td');
  assert.match(cells[1].textContent,/110\.000,00/);
  assert.match(cells[2].textContent,/111\.000,00/);
  assert.match(cells[3].textContent,/1\.000,00/);
  const search=byClass('fiscal-doc-search'); search.value='508'; search.events.input();
  assert.equal(byClass('fiscal-doc-filter').value,'all');
  assert.match(byClass('fiscal-doc-caption').textContent,/de 1100 registros/);
});

test('busca por acumulador mostra o Razão identificado e abre todos os documentos do recorte',()=>{
  const {byClass,all}=setup();
  const search=byClass('fiscal-doc-search'); search.value='1152'; search.events.input();
  assert.match(byClass('fiscal-doc-caption').textContent,/de 1100 registros/);
  const cells=all(byClass('fiscal-doc-search-totals')).filter(el=>el.tag==='td');
  assert.match(cells[2].textContent,/111\.000,00/);
  assert.match(cells[3].textContent,/1\.000,00/);
  const lookup=byClass('fiscal-doc-lookup-input'); lookup.value='acumulador 1152'; lookup.events.input();
  assert.equal(all(byClass('fiscal-doc-lookup-results')).filter(el=>el.tag==='tbody')[0].children.length,2);
});

test('valores por acumulador não rateiam parcelas compartilhadas nem incorporam candidatos de outra conta',()=>{
  const {context}=setup();
  const group={conta:'470',acumuladores:[{codigo:'1102',valor_resumo:100,detalhamento_disponivel:true},{codigo:'1403',valor_resumo:200,detalhamento_disponivel:true}],
    comparacoes:[{situacao:'PROVAVEL',linhas_fiscais:[{acumulador:'1102'},{acumulador:'1403'}],lancamentos:[{id:'R1',conta:'470',valor:300}]}]};
  assert.ok(context.investigationAccumulatorTotals(group).every(a=>a.ledger===null && a.difference===null));
  group.comparacoes=[{situacao:'CONTA_DIFERENTE',linhas_fiscais:[{acumulador:'1102'}],lancamentos:[{id:'R2',conta:'22517',valor:100}]}];
  assert.equal(context.investigationAccumulatorTotals(group)[0].ledger,0);
  group.comparacoes=[{situacao:'AMBIGUO',linhas_fiscais:[{acumulador:'1102'}],lancamentos:[{id:'R3',conta:'470',valor:100},{id:'R4',conta:'470',valor:100}]}];
  assert.equal(context.investigationAccumulatorTotals(group)[0].ledger,null);
});

test('histórico só é resumido quando nota e parceiro já estão visíveis, preservando qualificações',()=>{
  const code=source.slice(source.indexOf('  function compactDocumentHistory('),source.indexOf('  function investigationTable('));
  const context={};vm.createContext(context);vm.runInContext(code,context);
  const d={nota:'100',parceiro:'Fornecedor Teste'};
  assert.equal(context.compactDocumentHistory('COMPRA CF NF 00100 - Fornecedor Teste',d),'COMPRA');
  assert.equal(context.compactDocumentHistory('COMPRA CF NF 100 CANCELADA - Fornecedor Teste',d),'COMPRA CF NF 100 CANCELADA - Fornecedor Teste');
  assert.equal(context.compactDocumentHistory('COMPRA CF NF 100 - Outro Fornecedor',d),'COMPRA CF NF 100 - Outro Fornecedor');
});
