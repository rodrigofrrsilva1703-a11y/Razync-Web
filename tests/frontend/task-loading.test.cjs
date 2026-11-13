const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../assets/js/motion.js'),'utf8');
function setup(text='',state=''){
  const classes=new Set(),attrs={};
  const node={textContent:text,dataset:{state},classList:{toggle(k,on){on?classes.add(k):classes.delete(k)}},
    hasAttribute:k=>k in attrs,setAttribute(k,v){attrs[k]=v},nodeType:1,closest(){return this}};
  let changed;
  const context={document:{body:{},querySelectorAll:()=>[node]},Set,
    MutationObserver:class {constructor(fn){changed=fn}observe(){}}};
  vm.runInNewContext(source,context);
  return {node,attrs,classes,change(text,state=''){node.textContent=text;node.dataset.state=state;changed([{target:node,addedNodes:[]}])}};
}
test('carregamento cobre leitura, aprendizado e exportação e termina com a tarefa',()=>{
  for(const text of ['Lendo extratos e montando a prévia…','Aprendendo padrões…','Consultando padrões e evidências…','Exportando Excel…','Arquivos prontos. Montando conferência diária…']){
    const h=setup(text);assert.equal(h.attrs['aria-busy'],'true');assert.ok(h.classes.has('preview-loading'));
    h.change('Concluído. Confira os resultados.');assert.equal(h.attrs['aria-busy'],'false');assert.ok(!h.classes.has('preview-loading'));
    h.change('Preparando prévia…');h.change('');assert.equal(h.attrs['aria-busy'],'false');
  }
});
test('erro e cancelamento explícitos encerram o movimento mesmo com verbo de tarefa',()=>{
  const h=setup('Aguardando retorno do servidor…','loading');assert.equal(h.attrs['aria-busy'],'true');
  h.change('Analisando: serviço indisponível.','error');assert.equal(h.attrs['aria-busy'],'false');
  h.change('Preparando contexto…','cancelled');assert.equal(h.attrs['aria-busy'],'false');
  h.change('Classificando modelo concluído.','success');assert.equal(h.attrs['aria-busy'],'false');
  assert.equal(h.attrs.role,'status');assert.equal(h.attrs['aria-live'],'polite');
});
