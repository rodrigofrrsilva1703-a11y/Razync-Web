const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const app = fs.readFileSync(path.join(__dirname,'../../assets/js/app.js'),'utf8');
const css = fs.readFileSync(path.join(__dirname,'../../assets/css/workspace.css'),'utf8');

test('Grupo Autokraft usa três cards compactos e abre a empresa selecionada',()=> {
  assert.match(app,/AUTOKRAFT_CODES = new Set\(\[3,178,343\]\)/);
  assert.match(app,/function buildAutokraftGroup\(/);
  assert.match(app,/3:"Autokraft Industrial"/);
  assert.match(app,/178:"Autokraft Projetos"/);
  assert.match(app,/343:"I\.S\.A"/);
  assert.match(app,/requestAnimationFrame\(\(\) => openCompany\(company\)\)/);
  assert.match(css,/\.autokraft-company-cards\{/);
  assert.match(css,/grid-template-columns:repeat\(var\(--autokraft-count,3\),minmax\(0,1fr\)\)/);
  assert.match(css,/\.autokraft-company-card\.selected/);
});
