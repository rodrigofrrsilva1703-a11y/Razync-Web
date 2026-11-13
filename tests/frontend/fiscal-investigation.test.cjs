const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/fiscal-242.js','utf8');

function setup(count=25){
  class Element{
    constructor(tag,cls='',text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.events={};}
    append(...items){this.children.push(...items);} appendChild(item){this.children.push(item);return item;}
    addEventListener(name,fn){this.events[name]=fn;}
  }
  const node=(...args)=>new Element(...args);
  const context={node,money:new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}),
    renderAIDataTable:(title,headers,rows)=>{const el=node('table','',title);el.rows=rows;return el;}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function renderAICases('),source.indexOf('  function renderAIEntries(')),context);
  const cases=Array.from({length:count},(_,i)=>({nota:String(i+1),titulo:'Valor diferente',grau_evidencia:'Candidato forte',
    explicacao_local:'Correspondência a confirmar',data_fiscal:'01/09/2026',serie:'1',parceiro:'<img src=x onerror=alert(1)>',
    valor_fiscal:100,valor_razao:110,diferenca:10,criterio:'Nota identificada',
    candidatos:[{referencia:'L7',conta:'470',data:'01/09/2026',historico:'Compra',contrapartida:'508',valor:110}],
    interpretacao_ia:['E-1 pode corresponder a L7.'],verificacoes_ia:['Compare E-1 e L7.'],falta_confirmar:'Confira a origem',acao:'Abra a nota'}));
  const root=context.renderAICases({parecer:{pendencias_explicadas:cases}});
  const all=(el=root)=>[el,...el.children.flatMap(child=>all(child))];
  return {root,all,context};
}

test('pendências são paginadas e as evidências só são montadas quando abertas',()=>{
  const {root,all}=setup();
  assert.equal(all().filter(el=>el.className==='fiscal-ai-case').length,0);
  root.open=true;root.events.toggle();
  assert.equal(all().filter(el=>el.className==='fiscal-ai-case').length,20);
  assert.equal(all().filter(el=>el.tag==='table').length,0);
  const first=all().find(el=>el.className==='fiscal-ai-case');first.open=true;first.events.toggle();
  assert.equal(all().filter(el=>el.tag==='table').length,2);
  first.events.toggle();assert.equal(all().filter(el=>el.tag==='table').length,2);
  const more=all().find(el=>el.tag==='button');more.events.click();
  assert.equal(all().filter(el=>el.className==='fiscal-ai-case').length,25);assert.equal(more.hidden,true);
  assert.match(all().find(el=>el.className==='fiscal-ai-cases-caption').textContent,/25 de 25/);
});

test('detalhes separam interpretação da IA, ação local e fonte sem interpretar HTML',()=>{
  const {root,all}=setup(1);root.open=true;root.events.toggle();
  const detail=all().find(el=>el.className==='fiscal-ai-case');detail.open=true;detail.events.toggle();
  assert.ok(all().some(el=>el.textContent==='Interpretação da IA para este caso'));
  assert.ok(all().some(el=>el.textContent==='O que falta confirmar'));
  assert.ok(all().some(el=>el.textContent==='Abra a nota'));
  assert.ok(all().some(el=>el.textContent.includes('<img src=x')));
  assert.equal(all().filter(el=>el.tag==='img').length,0);
  assert.equal(all().find(el=>el.tag==='table').rows[0][2],'R$\u00a010,00');
});

test('contas sem detalhamento continuam compatíveis',()=>{
  const {context}=setup(0);assert.equal(context.renderAICases({}),null);
});
