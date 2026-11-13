const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
function setup() {
 const node=tag=>({tag,children:[],attributes:{},value:'',open:false,textContent:'',append(...els){this.children.push(...els);},appendChild(el){this.children.push(el);},replaceChildren(){this.children=[];},setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,fn){this[k]=fn;}});
 const scope={document:{createElement:node},brl:v=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'}),formatDailyDate:v=>v};
 vm.createContext(scope);const source=fs.readFileSync('assets/js/reconciliation-preview.js','utf8');vm.runInContext(source.slice(source.indexOf('function renderStatementMovements(')),scope);
 const view=scope.renderStatementMovements([
  {BANCO:'Banco do Brasil',DATA:'2026-03-03','HISTÓRICO':'Pix - Enviado',VALOR:-100},
  {BANCO:'Banco do Brasil',DATA:'2026-03-03','HISTÓRICO':'BB Rende Fácil',VALOR:100},
  {BANCO:'Banco do Brasil',DATA:'2026-03-03','HISTÓRICO':'BB Rende Fácil <texto>',VALOR:100}
 ]);
 const controls=view.children[2], search=controls.children[0], count=controls.children[1], body=view.children[3].children[0].children[1];
 view.open=true;view.toggle();return {view,search,count,body};
}
test('consulta mantém valores e repetições do extrato, separando entrada de saída',()=>{
 const {body}=setup();assert.equal(body.children.length,3);
 assert.equal(body.children[0].children[3].textContent,'—');assert.match(body.children[0].children[4].textContent,/100,00/);
 assert.match(body.children[1].children[3].textContent,/100,00/);assert.equal(body.children[1].children[4].textContent,'—');
 assert.equal(body.children[2].children[2].textContent,'BB Rende Fácil <texto>');
});
test('busca por histórico sem acento e valor com ponto ou vírgula encontra a movimentação',()=>{
 const {search,count,body}=setup();search.value='rende facil';search.input();assert.equal(body.children.length,2);assert.match(count.textContent,/2 de 3/);
 search.value='100.00';search.input();assert.equal(body.children.length,3);
 search.value='100,00';search.input();assert.equal(body.children.length,3);
 search.value='inexistente';search.input();assert.match(body.children[0].children[0].textContent,/Nenhum lançamento/);
});
