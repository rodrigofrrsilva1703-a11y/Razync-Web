const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../../assets/js/workspace-ui.js'),'utf8');
const dates = fs.readFileSync(path.join(__dirname,'../../assets/js/date-fields.js'),'utf8');

function setup(saved='[]', blocked=false) {
  let stored=saved;
  const context={
    localStorage:{getItem:()=>{if(blocked)throw new Error('blocked');return stored;},setItem:(_,value)=>{if(blocked)throw new Error('blocked');stored=value;}},
    window:{matchMedia:()=>({matches:false})}, document:{}, selected:null,
    bankLabel:(bank,account)=>`${bank} ${account}`,bankSelect:{value:'itau'}
  };
  vm.createContext(context);vm.runInContext(dates+'\n'+source,context);
  return {context,stored:()=>stored};
}

test('favoritas persistem somente os códigos e podem ser removidas',()=> {
  const h=setup();assert.equal(h.context.toggleFavoriteCompany(626),true);
  assert.equal(h.context.isFavoriteCompany('626'),true);
  assert.deepEqual(JSON.parse(h.stored()),['626']);
  const restored=setup(h.stored());assert.equal(restored.context.isFavoriteCompany(626),true);
  assert.equal(restored.context.toggleFavoriteCompany(626),false);
  assert.deepEqual(JSON.parse(restored.stored()),[]);
});

test('favoritas continuam funcionando com armazenamento bloqueado ou corrompido',()=> {
  for(const h of [setup('invalid json'),setup('[]',true)]) {
    assert.equal(h.context.toggleFavoriteCompany(266),true);
    assert.equal(h.context.isFavoriteCompany(266),true);
  }
});

test('pendências distinguem conta vazia e data impossível',()=> {
  const h=setup(),headers=['DATA','DÉBITO','CRÉDITO','VALOR'];
  assert.deepEqual([...h.context.previewRowIssues(headers,['31/04/2026','',1155,-100])],['Conta pendente','Data inválida']);
  assert.deepEqual([...h.context.previewRowIssues(headers,['06/10/2026',8,9,100])],[]);
  assert.deepEqual([...h.context.previewRowIssues(headers,['2024-02-29T00:00:00',0,9,100])],['Conta pendente']);
});

test('resumo de arquivos identifica a conta configurada sem inferir bancos desconhecidos',()=> {
  const h=setup();h.context.selected={capabilities:{banks:{sicredi:'1155'}}};
  assert.equal(h.context.selectedFileBankLabel({dataset:{reconcileBank:'sicredi'}}),'sicredi 1155');
  assert.equal(h.context.selectedFileBankLabel({dataset:{},id:'classifyFile'}),'Abas do modelo');
  assert.equal(h.context.selectedFileBankLabel({dataset:{},id:'auxiliar'}),'Identificado no processamento');
});
