const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../assets/js/fiscal-242.js'), 'utf8');

function setup(rows) {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {
      listeners:{}, open:false, disabled:false, textContent:'',
      addEventListener(name, handler) {this.listeners[name] = handler;},
      showModal() {this.open = true;},
      close() {this.open = false;this.listeners.close();},
      focus(options) {this.focusOptions = options;},
    });
    return elements.get(id);
  };
  const classes = new Set();
  const openers = rows.map(row => ({dataset:{detailKey:row.conta + ':' + row.tipo}, focus(options) {this.focusOptions = options;}}));
  const context = vm.createContext({
    byId:get, selectedKey:'', tableSort:{key:'conta',descending:false},
    details:{scrollTop:500}, search:get('search'),
    document:{documentElement:{classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)}}},
    keyOf:row=>row.conta + ':' + row.tipo,
    filteredRows:()=>rows,
    sortFiscalRows:items=>items.slice(),
    tableBody:{querySelectorAll:()=>openers},
    renderTable:()=>{},
  });
  vm.runInContext(source.slice(source.indexOf('  const detailDialog = byId('), source.indexOf('  function statusClass(')), context);
  return {context,get,classes,openers};
}

test('janela navega só pela seleção e diferencia entradas e saídas da mesma conta', () => {
  const {context,get} = setup([{conta:'22643',tipo:'ENTRADAS'},{conta:'22643',tipo:'SAÍDAS'}]);
  context.openAccountDetails('22643:ENTRADAS');
  assert.equal(get('fiscal242DetailDialog').open,true);
  assert.equal(get('fiscal242DetailPrevious').disabled,true);
  assert.equal(get('fiscal242DetailNext').disabled,false);
  assert.equal(get('fiscal242DetailPosition').textContent,'1 de 2 na seleção da tabela');
  context.moveAccountDetails(1);
  assert.equal(context.selectedKey,'22643:SAÍDAS');
  assert.equal(get('fiscal242DetailNext').disabled,true);
  context.moveAccountDetails(1);
  assert.equal(context.selectedKey,'22643:SAÍDAS');
  context.moveAccountDetails(-1);
  assert.equal(context.selectedKey,'22643:ENTRADAS');
});

test('fechar após navegar devolve o foco à conta que abriu a janela sem rolar a página', () => {
  const {context,get,classes,openers} = setup([{conta:'470',tipo:'ENTRADAS'},{conta:'312',tipo:'ENTRADAS'}]);
  context.openAccountDetails('470:ENTRADAS');
  assert.equal(classes.has('fiscal-account-dialog-open'),true);
  assert.equal(context.details.scrollTop,0);
  context.moveAccountDetails(1);
  get('fiscal242DetailDialog').close();
  assert.equal(context.selectedKey,'');
  assert.equal(classes.has('fiscal-account-dialog-open'),false);
  assert.equal(openers[0].focusOptions.preventScroll,true);
  assert.equal(openers[1].focusOptions,undefined);
});

test('seleção com uma conta desabilita as duas direções e ignora chave fora do filtro', () => {
  const {context,get} = setup([{conta:'470',tipo:'ENTRADAS'}]);
  context.openAccountDetails('312:ENTRADAS');
  assert.equal(get('fiscal242DetailDialog').open,false);
  context.openAccountDetails('470:ENTRADAS');
  assert.equal(get('fiscal242DetailPrevious').disabled,true);
  assert.equal(get('fiscal242DetailNext').disabled,true);
});
