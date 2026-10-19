const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/js/fiscal-242.js','utf8');
function setup({grouped=false}={}) {
  class Element {
    constructor(tag, cls='', text='') { this.tag=tag; this.className=cls; this.textContent=String(text); this.children=[]; this.attributes={}; this.events={}; this.value=''; this.dataset={}; this.open=false; this.isConnected=true; }
    append(...items) {items.forEach(item=>this.appendChild(item));}
    appendChild(item) {this.children.push(item); if(this.tag==='select' && this.children.length===1) this.value=item.value; return item;}
    replaceChildren(...items) {this.children=[];this.append(...items);}
    setAttribute(k,v) {this.attributes[k]=v;}
    addEventListener(k,fn) {this.events[k]=fn;}
    click() {this.events.click?.();}
    insertBefore(item,before) {this.children.splice(this.children.indexOf(before),0,item);}
    showModal() {this.open=true;}
    close() {if(this.open) {this.open=false;this.events.close?.();}}
    focus(options) {this.focusOptions=options;}
  }
  const node=(...args)=>new Element(...args); const root=node('div');
  let exported;
  const classes=new Set();
  const context={node,investigationResults:root,document:{documentElement:{classList:{add:c=>classes.add(c),remove:c=>classes.delete(c)}}},money:new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}),
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
  if(grouped) docs[0].linhas_fiscais.push({...docs[0].linhas_fiscais[0],id:'E-extra',valor:0});
  const group={composicao:{confere_com_inicial:true,itens:[
      {descricao:'Diferenças nos vínculos',valor:1009.99},{descricao:'Fora da conferência inicial',valor:-9.99},{descricao:'Cobertura',valor:0}]},conta:'508',tipo:'ENTRADAS',descricao:'Compras',fiscal:110000,contabil:111000,diferenca:1000,
    documentos_total:1100,comparacoes:docs,acumuladores:[{codigo:'1152',descricao:'Compras',valor_resumo:110000,valor_documentos:110000,detalhamento_disponivel:true}],razao_sem_vinculo:[]};
  context.renderInvestigation({resumo:{contas:2,conciliados:1000,pendentes:100},contas:[group,{...group,conta:'509',comparacoes:[],documentos_total:0}]});
  return {root,all,byClass,context,classes,exportedBlob:()=>exported};
}
test('contador fiscal usa linhas de origem e não quantidade de grupos de notas',()=>{
  const {all,byClass}=setup({grouped:true});
  const metrics=byClass('fiscal-investigation-summary').children;
  assert.equal(metrics[1].children[0].textContent,'Linhas fiscais conciliadas');
  assert.equal(metrics[1].children[1].textContent,'1001');
  assert.equal(metrics[2].children[1].textContent,'100');
  assert.equal(metrics[3].children[1].textContent,'0');
});
test('investigação mantém todos os resultados navegáveis sem renderizar milhares de linhas',()=>{
  const {all,byClass}=setup();
  const body=()=>all(byClass('fiscal-doc-rows')).find(el=>el.tag==='tbody');
  assert.equal(body().children.length,25);
  assert.equal(byClass('fiscal-doc-pagination').hidden,false);
  assert.match(byClass('fiscal-doc-caption').textContent,/1–25 de 100 registros/);
  byClass('fiscal-doc-pagination').children.find(el=>el.textContent==='Próxima').click();
  assert.match(byClass('fiscal-doc-caption').textContent,/26–50 de 100/);
  const filter=byClass('fiscal-doc-filter'); filter.value='all'; filter.events.change();
  assert.match(byClass('fiscal-doc-caption').textContent,/1–25 de 1100/);
  const search=byClass('fiscal-doc-search'); search.value='1100'; search.events.input();
  assert.equal(body().children.length,1);
  assert.equal(byClass('fiscal-doc-pagination').hidden,true);
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
  assert.match(all(byClass('fiscal-doc-total-difference')).find(el=>el.tag==='strong').textContent,/1\.000,00/);
});

test('busca por conta exibe fiscal, Razão considerado e diferença sem depender do filtro de pendências',()=>{
  const {byClass,all}=setup();
  const lookup=byClass('fiscal-doc-lookup-input'); lookup.value='508'; lookup.events.input();
  const values=all(byClass('fiscal-doc-comparison-totals')).filter(el=>el.tag==='strong');
  assert.match(values[0].textContent,/110\.000,00/);
  assert.match(values[1].textContent,/111\.000,00/);
  assert.match(values[2].textContent,/1\.000,00/);
  assert.equal(all(byClass('fiscal-doc-lookup-results')).filter(el=>el.tag==='table').length,0);
  const search=byClass('fiscal-doc-search'); search.value='508'; search.events.input();
  assert.equal(byClass('fiscal-doc-filter').value,'review');
  assert.match(byClass('fiscal-doc-caption').textContent,/de 100 registros/);
});

test('busca por acumulador mantém os totais completos e prioriza pendências',()=>{
  const {byClass,all}=setup();
  const search=byClass('fiscal-doc-search'); search.value='1152'; search.events.input();
  assert.match(byClass('fiscal-doc-caption').textContent,/de 100 registros/);
  const values=all(byClass('fiscal-doc-comparison-totals')).filter(el=>el.tag==='strong');
  assert.match(values[1].textContent,/111\.000,00/);
  assert.match(values[2].textContent,/1\.000,00/);
  assert.match(byClass('fiscal-doc-document-title').textContent,/1152/);
  const lookup=byClass('fiscal-doc-lookup-input'); lookup.value='acumulador 1152'; lookup.events.input();
  assert.equal(all(byClass('fiscal-doc-lookup-results')).filter(el=>el.tag==='table').length,0);
  assert.equal(byClass('fiscal-doc-search').value,'');
  assert.equal(all().filter(el=>el.className==='fiscal-doc-search-totals').length,0);
});

test('pesquisar uma nota dentro do acumulador mantém os totais e a lista no mesmo escopo',()=>{
  const {byClass,all}=setup();
  const lookup=byClass('fiscal-doc-lookup-input'); lookup.value='1152';lookup.events.input();
  const search=byClass('fiscal-doc-search'); search.value='1100';search.events.input();
  assert.match(byClass('fiscal-doc-balance-caption').textContent,/ACUMULADOR 1152/);
  assert.match(byClass('fiscal-doc-document-title').textContent,/1152/);
  assert.match(byClass('fiscal-doc-caption').textContent,/de 1 registros/);
  assert.match(all(byClass('fiscal-doc-comparison-totals')).filter(el=>el.tag==='strong')[1].textContent,/111\.000,00/);
  assert.match(byClass('fiscal-doc-filter').children.find(el=>el.value==='all').textContent,/1100/);
  lookup.value='Compras';lookup.events.input();
  assert.match(byClass('fiscal-doc-balance-caption').textContent,/CONFERÊNCIA INICIAL/);
});

test('totais, contagens, cobertura e exportação usam apenas o acumulador selecionado',async()=>{
  const {context,byClass,all,exportedBlob}=setup();
  const document=(code,note,value)=>({id:note,nota:note,data:'03/08/2026',serie:'1',parceiro:'Fornecedor',situacao:'VALOR_DIFERENTE',
    valor_fiscal:value,valor_razao:value+10,diferenca:10,linhas_fiscais:[{id:note,acumulador:code,cfop:code,valor:value,linha_origem:1}],
    lancamentos:[{id:'R'+note,conta:'470',data:'03/08/2026',valor:value+10,historico:'COMPRA NF '+note}]});
  context.renderInvestigation({contas:[{conta:'470',tipo:'ENTRADAS',descricao:'Compras',fiscal:300,contabil:320,diferenca:20,documentos_total:2,
    acumuladores:[{codigo:'1102',valor_resumo:100,valor_documentos:100,detalhamento_disponivel:true},{codigo:'1403',valor_resumo:200,valor_documentos:200,detalhamento_disponivel:true}],
    comparacoes:[document('1102','NOTA-A',100),document('1403','NOTA-B',200)],razao_sem_vinculo:[]}]});
  const lookup=byClass('fiscal-doc-lookup-input');lookup.value='1403';lookup.events.input();
  const values=all(byClass('fiscal-doc-comparison-totals')).filter(el=>el.tag==='strong').map(el=>el.textContent);
  assert.match(values[0],/200,00/);assert.match(values[1],/210,00/);assert.match(values[2],/10,00/);
  assert.match(byClass('fiscal-doc-filter').children.find(el=>el.value==='all').textContent,/\(1\)/);
  assert.equal(all(byClass('fiscal-doc-coverage')).find(el=>el.tag==='tbody').children.length,1);
  byClass('fiscal-doc-export').click();const csv=await exportedBlob().text();
  assert.match(csv,/NOTA-B/);assert.doesNotMatch(csv,/NOTA-A/);
  const search=byClass('fiscal-doc-search');search.value='NOTA-A';search.events.input();
  assert.match(byClass('fiscal-doc-caption').textContent,/Nenhum registro/);
  assert.match(byClass('fiscal-doc-balance-caption').textContent,/1403/);
});

test('consulta abre a conta encontrada, restringe a lateral e restaura a navegação ao limpar',()=>{
  const {byClass,all}=setup();
  const lookup=byClass('fiscal-doc-lookup-input');
  lookup.value='conta 509'; lookup.events.input();
  assert.match(byClass('fiscal-doc-reader').children[0].textContent,/CONTA 509/);
  const buttons=all().filter(el=>el.className==='fiscal-doc-account');
  assert.equal(buttons[0].hidden,true); assert.equal(buttons[1].hidden,false);
  lookup.value='inexistente';lookup.events.input();
  assert.equal(byClass('fiscal-doc-workspace').hidden,true);
  lookup.value='';lookup.events.input();
  assert.equal(byClass('fiscal-doc-workspace').hidden,false);
  assert.ok(buttons.every(button=>!button.hidden));
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

test('resultados documentais abrem em janela e navegam sem perder a conta de retorno',()=>{
  const {root,all,byClass,classes}=setup();
  const dialog=root.documentDialog;
  assert.equal(dialog.open,false);
  const buttons=all().filter(el=>el.className==='fiscal-doc-account');
  buttons[0].click();
  assert.equal(dialog.open,true);
  assert.equal(classes.has('fiscal-account-dialog-open'),true);
  assert.equal(all().find(el=>el.id==='fiscalDocumentDialogTitle').textContent,'Conta 508');
  assert.equal(byClass('fiscal-account-situation-copy').children[0].textContent,'Resultado com divergência');
  const footer=byClass('fiscal-account-dialog-footer'),nav=footer.children[1];
  assert.equal(nav.children[0].disabled,true);
  assert.equal(nav.children[1].disabled,false);
  nav.children[1].click();
  assert.equal(all().find(el=>el.id==='fiscalDocumentDialogTitle').textContent,'Conta 509');
  assert.equal(nav.children[1].disabled,true);
  dialog.close();
  assert.equal(classes.has('fiscal-account-dialog-open'),false);
  assert.equal(buttons[0].focusOptions.preventScroll,true);
  assert.equal(buttons[1].focusOptions,undefined);
});

test('janela respeita a consulta e abre o recorte do acumulador por teclado',()=>{
  const {root,all,byClass}=setup();
  const lookup=byClass('fiscal-doc-lookup-input');
  lookup.value='conta 509';lookup.events.input();
  let prevented=false;
  lookup.events.keydown({key:'Enter',preventDefault:()=>{prevented=true;}});
  assert.equal(prevented,true);assert.equal(root.documentDialog.open,true);
  const nav=byClass('fiscal-account-dialog-footer').children[1];
  assert.equal(nav.children[0].disabled,true);assert.equal(nav.children[1].disabled,true);
  root.documentDialog.close();
  lookup.value='1152';lookup.events.input();
  all().find(el=>el.className==='fiscal-doc-account'&&!el.hidden).click();
  assert.equal(all().find(el=>el.id==='fiscalDocumentDialogTitle').textContent,'Acumulador 1152');
  assert.match(byClass('fiscal-doc-balance-caption').textContent,/1152/);
  assert.match(byClass('fiscal-doc-caption').textContent,/de 100 registros/);
  lookup.value='inexistente';lookup.events.input();
  assert.equal(root.documentDialog.open,false);
});

test('substituir a investigação fecha a janela antiga e libera a rolagem',()=>{
  const {root,all,context,classes}=setup();
  all().find(el=>el.className==='fiscal-doc-account').click();
  const old=root.documentDialog;
  context.renderInvestigation({contas:[]});
  assert.equal(old.open,false);
  assert.equal(classes.has('fiscal-account-dialog-open'),false);
});
