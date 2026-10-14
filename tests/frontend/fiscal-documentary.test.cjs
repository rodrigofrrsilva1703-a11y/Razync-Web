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
  const context={node,investigationResults:root,money:new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}),
    cell:(tr,text,cls)=>tr.appendChild(node('td',cls,text)),Blob,URL,setTimeout:fn=>fn()};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function investigationStatus('),source.indexOf('  investigationForm.addEventListener')),context);
  const all=(item=root)=>[item,...item.children.flatMap(child=>all(child))];
  const byClass=cls=>all().find(el=>el.className===cls);
  const docs=Array.from({length:1100},(_,i)=>({id:'E-'+i,nota:String(i+1),data:'03/08/2026',serie:'1',
    parceiro:'Fornecedor '+i,situacao:i<1000?'CONCILIADO':'VALOR_DIFERENTE',criterio:'Documento e valores comparados',
    valor_fiscal:100,valor_razao:i<1000?100:110,diferenca:i<1000?0:10,
    linhas_fiscais:[{id:'E-'+i,acumulador:'1152',cfop:'1102',valor:100,linha_origem:i+1}],
    lancamentos:[{id:'R-'+i,data:'03/08/2026',valor:i<1000?100:110,historico:'COMPRA CF NF '+(i+1),contrapartida:'800'}]}));
  const group={conta:'508',tipo:'ENTRADAS',descricao:'Compras',fiscal:110000,contabil:111000,diferenca:1000,
    documentos_total:1100,comparacoes:docs,acumuladores:[],razao_sem_vinculo:[]};
  context.renderInvestigation({resumo:{contas:2,conciliados:1000,pendentes:100},contas:[group,{...group,conta:'509',comparacoes:[],documentos_total:0}]});
  return {root,all,byClass};
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
