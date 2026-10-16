const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/fiscal-242.js','utf8');
function setup(){
  class Element {
    constructor(tag,cls='',text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];
      this.classList={add:name=>{this.className+=' '+name;}};}
    append(...items){this.children.push(...items);}appendChild(item){this.children.push(item);return item;}
  }
  const context={node:(...args)=>new Element(...args)};vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function renderAIFindings('),source.indexOf('  function renderAIConsidered(')),context);
  vm.runInContext(source.slice(source.indexOf('  function renderAIReviewSteps('),source.indexOf('  function renderAIExcluded(')),context);
  const all=el=>[el,...el.children.flatMap(all)];return {context,all};
}
test('resumo destaca conclusão e próximo passo preservando a interpretação separada',()=>{
  const {context,all}=setup();
  const root=context.renderAIFindings({parecer:{resumo_executivo:{titulo:'Diferença identificada',conclusao:'O contábil está acima do fiscal.',
    foco:'Confira NF 100',primeiro_passo:'Compare a origem.',cobertura:'Contexto parcial da IA',exemplos:['NF 100 (E-1)']},
    leitura_comparacao:{resultado:'Duas pendências.',documental_especifico:true,observacoes:[]},analise_exibicao:'E-1 pode corresponder a L7.'}});
  assert.ok(all(root).some(el=>el.className==='fiscal-ai-executive'));
  assert.ok(all(root).some(el=>el.className==='fiscal-ai-executive-coverage' && el.textContent==='Contexto parcial da IA'));
  assert.ok(all(root).some(el=>el.textContent==='Confira NF 100'));
  assert.ok(all(root).some(el=>el.className==='fiscal-ai-open-question' && el.textContent.includes('E-1')));
});
test('critérios são opcionais e ficam em detalhe recolhido por orientação',()=>{
  const {context,all}=setup();
  const root=context.renderAIReviewSteps({parecer:{leitura_comparacao:{orientacoes:[
    {acao:'Confira a nota',objetivo:'Compare os campos.',para_concluir:'Confirme a origem.',quando_reavaliar:'Se for outra operação, descarte.'},
    {acao:'Confira a cobertura',objetivo:'Busque o documento original.'}]}}});
  const details=all(root).filter(el=>el.tag==='details');assert.equal(details.length,1);
  assert.equal(details[0].open,undefined);
  assert.ok(all(details[0]).some(el=>el.textContent==='Quando reavaliar a hipótese'));
  assert.ok(all(details[0]).some(el=>el.textContent==='Se for outra operação, descarte.'));
});
