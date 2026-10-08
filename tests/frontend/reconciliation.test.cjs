const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../../assets/js/app.js'), 'utf8').replace(/\r\n/g,'\n');

function harness(kind, banks = ['itau']) {
  const nodes = {};
  const node = key => nodes[key] ||= {
    files: [], textContent: '', hidden: true, checkValidity:()=>true,
    addEventListener(name, callback) { this[name] = callback; },
    replaceChildren() { this.cleared = true; },
    requestSubmit() { this.submitted = true; }
  };
  node('#modelFile').files = ['MODELO_A'];
  node('#ledgerStatement').files = ['EXTRATO_A'];
  node('#ledgerFile').files = ['RAZAO_A'];
  const calls = [], renders = [], downloads = [], timers = new Map();
  let timerId = 0;
  class FormData {
    constructor() { this.values = {}; }
    append(key, value) { this.values[key] = value; }
  }
  const build = () => {
    const data = new FormData();
    data.append('model', node('#modelFile').files[0]);
    data.append('banks', [...banks]);
    data.append('period', node('#reconcileStart').value);
    return data;
  };
  const context = {
    $:node, AbortController, FormData, selected:{codigo:266},
    reconcileForm:node('#reconcileForm'), API:()=>'https://api.example',
    clearTimeout:id=>timers.delete(id),
    setTimeout:callback=> { timers.set(++timerId, callback); return timerId; },
    clearToolResult:key=> { node(key).hidden = true; node(key).replaceChildren(); },
    reconcileSelectionState:()=>({banks:[...banks],missing:[]}),
    bankName:value=>value, buildSingleReconcileData:build, buildReconcileData:build,
    fetch:async(url, options)=> {
      calls.push({url,...options});
      return {ok:true,json:async()=>({rows:[],summary:{}})};
    },
    responseError:async()=> 'error',
    renderDailyReconciliation:(target, preview)=> { target.hidden=false; renders.push(preview); },
    reconciliationBalances:()=>({ok:true}),
    downloadBlob:async(response, name)=>downloads.push(name)
  };
  vm.createContext(context);
  const start = kind === 'ledger' ? source.indexOf('function buildLedgerData()') : source.indexOf('let reconcilePreviewTimer;');
  const end = kind === 'ledger' ? source.indexOf('\nfunction brl(', start) : source.indexOf('\nfunction filterCompanies()', start);
  vm.runInContext((kind === 'ledger' ? 'let ledgerPreviewTimer, ledgerPreviewController;\n' : '') + source.slice(start,end),context);
  return {context,node,calls,renders,downloads,timers,submit:()=>node(kind === 'ledger' ? '#ledgerForm' : '#reconcileForm').submit({preventDefault(){}})};
}

for (const banks of [['itau'], ['itau','bradesco']]) {
  test(`extrato: download preserva modelo, bancos e período (${banks.length} bancos)`, async()=> {
    const h = harness('extrato',banks);
    h.node('#reconcileStart').value='2026-01-01';
    await h.submit();
    h.node('#modelFile').files=['MODELO_B'];
    h.node('#reconcileStart').value='2026-02-01';
    await h.renders[0].download();
    assert.equal(h.calls[1].body,h.calls[0].body);
    assert.equal(h.calls[1].body.values.model,'MODELO_A');
    assert.equal(h.calls[1].body.values.period,'2026-01-01');
  });
}

test('Razão: download preserva o extrato e Razão da prévia',async()=> {
  const h=harness('ledger'); await h.submit();
  h.node('#ledgerStatement').files=['EXTRATO_B'];
  h.node('#ledgerFile').files=['RAZAO_B'];
  await h.renders[0].download();
  assert.equal(h.calls[1].body,h.calls[0].body);
  assert.equal(h.calls[1].body.values.extrato,'EXTRATO_A');
  assert.equal(h.calls[1].body.values.razao,'RAZAO_A');
});

for (const kind of ['ledger','extrato']) {
  test(`${kind}: alteração invalida a prévia e seu download imediatamente`,async()=> {
    const h=harness(kind); await h.submit();
    const oldDownload=h.renders[0].download;
    h.node(kind==='ledger'?'#ledgerForm':'#reconcileForm').change();
    assert.equal(h.node(kind==='ledger'?'#ledgerResult':'#reconcileResult').hidden,true);
    await oldDownload();
    assert.equal(h.calls.length,1);
  });
}

test('extrato: resposta atrasada não preenche outra empresa',async()=> {
  const h=harness('extrato'); let resolve;
  h.context.fetch=()=>new Promise(done=>resolve=done);
  const pending=h.submit();
  h.context.selected={codigo:1396};
  resolve({ok:true,json:async()=>({rows:[]})});
  await pending;
  assert.equal(h.renders.length,0);
});

test('extrato: falha atrasada não mostra erro na nova empresa',async()=> {
  const h=harness('extrato'); let reject;
  h.context.fetch=()=>new Promise((_,fail)=>reject=fail);
  const pending=h.submit(); h.context.selected={codigo:1396};
  h.node('#reconcileMessage').textContent='NOVA EMPRESA';
  reject(new Error('Erro da empresa anterior')); await pending;
  assert.equal(h.node('#reconcileMessage').textContent,'NOVA EMPRESA');
});

test('extrato: cancelar interrompe o timer e a requisição',async()=> {
  const h=harness('extrato'); await h.submit();
  h.node('#reconcileForm').change();
  assert.equal(h.timers.size,1);
  h.context.cancelReconcilePreview();
  assert.equal(h.timers.size,0);
  assert.equal(h.calls[0].signal.aborted,true);
  assert.equal(h.node('#reconcileResult').hidden,true);
});

test('extrato: timer não submete o formulário de outra empresa',()=> {
  const h=harness('extrato'); h.node('#reconcileForm').change();
  h.context.selected={codigo:1396};
  [...h.timers.values()][0]();
  assert.equal(h.node('#reconcileForm').submitted,undefined);
});

test('as transições de empresa cancelam a conferência',()=> {
  for(const name of ['openCompany(company)','closeCompany()','showGlobalView(name)']) {
    const start = source.indexOf(`function ${name} {`);
    assert.ok(start>=0,name);
    const end = source.indexOf('\n}',start);
    assert.ok(end>start,name);
    const body = source.slice(start,end);
    assert.match(body,/cancelReconcilePreview\(\)/,name);
  }
});

test('conferência simples e múltipla enviam o modelo anexado',()=> {
  const original = {name:'original.xlsx'};
  class Body { constructor(){this.values={};} append(key,value){this.values[key]=value;} }
  const context = {
    FormData:Body,
    $:key=>key==='#modelFile'?{files:[original]}:{value:''},
    dateApiValue:()=>'', document:{querySelector:()=>({files:[]})},
    reconcileSelectionState:()=>({banks:['itau','sicredi'],fileBanks:[],files:[]})
  };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function buildSingleReconcileData('),source.indexOf('let reconcilePreviewTimer;')),context);
  assert.equal(context.buildSingleReconcileData('itau').values.model_file,original);
  assert.equal(context.buildReconcileData().values.model_file,original);
});
