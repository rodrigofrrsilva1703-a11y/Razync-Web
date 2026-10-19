const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../assets/js/fiscal-242.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source.slice(source.indexOf('  function fiscalComparisonReading('), source.indexOf('  function renderDetails(')), context);
const read = context.fiscalComparisonReading;
const entry = (natureza, classificacao) => ({conta:'312', natureza, classificacao});

test('zero selecionado distingue movimentos excluídos de ausência de débitos', () => {
  const row = {conta:'312',tipo:'ENTRADAS',contabil:0,total_conta:26489.92,extras:2,situacao:'REVISAR'};
  const result = read(row, [entry('DÉBITO','ALERTA - NÃO FISCAL'), entry('CRÉDITO','FISCAL PROVÁVEL')]);
  assert.equal(result.noneSelected,true);
  assert.equal(result.separated,26489.92);
  assert.match(result.reason,/2 mov. fora da seleção/);
  assert.equal(read({...row,extras:0,total_conta:0,situacao:'AUSENTE NO CONTÁBIL'},[]).reason,'Sem débitos no relatório');
  assert.equal(read(row,[]).noneSelected,false);
});

test('saldo zero por compensação não é descrito como nenhum selecionado', () => {
  const result = read({conta:'312',tipo:'ENTRADAS',contabil:0,total_conta:10,extras:1},
    [entry('DÉBITO','FISCAL PROVÁVEL'),entry('ESTORNO/REDUTOR (DÉBITO)','FISCAL PROVÁVEL'),entry('DÉBITO','ALERTA - NÃO FISCAL')]);
  assert.equal(result.noneSelected,false);
});

test('composição mantém centavos e sinais dos movimentos separados', () => {
  assert.equal(read({contabil:3172898.35,total_conta:3172908.34}).separated,9.99);
  assert.equal(read({contabil:110,total_conta:100}).separated,-10);
  const result = read({tipo:'SAÍDAS',contabil:100,total_conta:100,diferenca:0,sem_evidencia:3});
  assert.equal(result.side,'créditos');
  assert.match(result.reason,/3 histórico\(s\) a validar/);
});

const situationContext = vm.createContext({money:new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'})});
vm.runInContext(source.slice(source.indexOf('  function fiscalAccountSituation('), source.indexOf('  function renderDetails(')), situationContext);
const situation = (row, entries=[]) => situationContext.fiscalAccountSituation(row, read(row, entries));

test('janela distingue divergência, seleção incompleta e ausência de movimentos', () => {
  const divergent = situation({diferenca:-750.50});
  assert.equal(divergent.title,'Conta com divergência');
  assert.match(divergent.explanation,/750,50.*abaixo do fiscal/);
  assert.match(situation({diferenca:100}).explanation,/acima do fiscal/);
  const noSelection = situation({conta:'312',tipo:'ENTRADAS',contabil:0,total_conta:26489.92,extras:1,diferenca:-26489.92},
    [entry('DÉBITO','ALERTA - NÃO FISCAL')]);
  assert.equal(noSelection.title,'Seleção a revisar');
  assert.equal(situation({tipo:'SAÍDAS',situacao:'AUSENTE NO CONTÁBIL'}).title,'Sem movimentos no Razão');
});

test('janela não apresenta igualdade aritmética como conciliação documental', () => {
  const alerts = situation({diferenca:0,extras:4,situacao:'CONFERE COM ALERTAS'});
  assert.equal(alerts.title,'Totais iguais · com alertas');
  assert.match(alerts.explanation,/4 mov. fora da seleção/);
  const equal = situation({diferenca:0,situacao:'CONFERE'});
  assert.equal(equal.title,'Totais iguais');
  assert.match(equal.explanation,/não confirma cada documento/);
});
