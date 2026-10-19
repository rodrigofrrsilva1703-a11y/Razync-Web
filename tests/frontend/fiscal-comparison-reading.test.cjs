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
