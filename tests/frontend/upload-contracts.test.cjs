const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const context={document:{querySelectorAll:()=>[],documentElement:{}},MutationObserver:class{observe(){}}};
vm.runInNewContext(fs.readFileSync('assets/js/file-formats.js','utf8'),context);
const {statementAccept}=context.RazyncFileFormats;
const capabilities=JSON.parse(execFileSync('python3',['-c',"import json,runpy;print(json.dumps(runpy.run_path('backend/app/registry.py')['CAPABILITIES']))"],{encoding:'utf8'}));
const company=code=>({codigo:code,capabilities:capabilities[code]});

test('todos os bancos configurados possuem contrato de extrato explícito',()=>{
  for(const [code,cap] of Object.entries(capabilities)){
    for(const bank of Object.keys(cap.banks))assert.ok(statementAccept(company(code),bank),`${code} / ${bank}`);
  }
  assert.equal(statementAccept({codigo:99999,capabilities:{banks:{itau:'508'}}},'itau'),'');
  assert.equal(statementAccept(company(969),'banco_inexistente'),'');
});
test('leitores exclusivos de PDF não anunciam CSV, OFX nem planilhas',()=>{
  for(const code of [47,88,154,285,625,626,734,912,964,969,1208,1211,1248,1522,1532]){
    for(const bank of Object.keys(capabilities[code].banks))assert.equal(statementAccept(company(code),bank),'.pdf',`${code} / ${bank}`);
  }
});
test('1530 exige Excel; Inter aceita PDF e Excel; Radani restringe apenas o Bradesco',()=>{
  assert.equal(statementAccept(company(1530),'itau'),'.xls,.xlsx');
  assert.equal(statementAccept(company(841),'inter'),'.pdf,.xls,.xlsx');
  assert.equal(statementAccept(company(968),'bradesco'),'.pdf');
  assert.equal(statementAccept(company(968),'itau'),'.pdf,.xls,.xlsx,.csv,.ofx');
});
test('campos de planilha, ZIP e PDF usam formatos do papel do documento, não os do banco',()=>{
  assert.equal(capabilities[1211].roles.find(r=>r.name==='boletos').accept,'.pdf');
  assert.equal(capabilities[242].roles.find(r=>r.name==='despesas').accept,'.xls,.xlsx');
  assert.equal(capabilities[1408].roles.find(r=>r.name==='francesinhas').accept,'.zip');
  const migration=fs.readFileSync('assets/js/migration.js','utf8');
  assert.doesNotMatch(migration,/\.zip,\.csv,\.json/);
  const html=fs.readFileSync('index.html','utf8');
  assert.ok(html.indexOf('src="./assets/js/file-formats.js')<html.indexOf('src="./assets/js/app.js'));
});
