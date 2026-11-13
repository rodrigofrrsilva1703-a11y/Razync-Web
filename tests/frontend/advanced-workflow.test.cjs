const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname,'../../assets/js/app.js'),'utf8');

test('fluxos avançados usam seletores de coleção para opções e bancos',()=> {
  assert.match(source,/for \(const input of \$\$\("\[data-option\]"\)\)/);
  assert.match(source,/const bankOptions=\$\$\("\[data-selected-bank\]"\)/);
  assert.doesNotMatch(source,/for \(const input of \$\("\[data-option\]"\)\)/);
  assert.doesNotMatch(source,/const bankOptions=\$\("\[data-selected-bank\]"\)/);
});
