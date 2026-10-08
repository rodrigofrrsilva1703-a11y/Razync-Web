const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const app = fs.readFileSync(path.join(__dirname,'../../assets/js/app.js'),'utf8');
const html = fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
const css = fs.readFileSync(path.join(__dirname,'../../assets/css/workspace.css'),'utf8');

test('empresa 266 possui instruções para as três ferramentas',()=> {
  assert.match(app,/266:\s*\{/);
  assert.match(app,/organizar:\s*\{/);
  assert.match(app,/base:\s*\{/);
  assert.match(app,/extrato:\s*\{/);
  assert.match(app,/Itaú 508/);
  assert.match(app,/Bradesco 9/);
  assert.match(app,/Fibra 506/);
  assert.match(app,/Só fica “Batendo” quando os dois saldos forem zero/);
});

test('instruções acompanham a ferramenta ativa e não aparecem em outras empresas',()=> {
  assert.match(app,/renderCompanyToolGuide\(name\)/);
  assert.match(app,/guide\.hidden = !content/);
  assert.match(app,/renderCompanyToolGuide\(""\)/);
  assert.match(html,/id="companyToolGuide"/);
  assert.match(css,/\.company-tool-guide/);
});
