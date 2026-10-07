const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const js = fs.readFileSync(path.join(__dirname,'../../assets/js/model-editor.js'),'utf8');
const css = fs.readFileSync(path.join(__dirname,'../../assets/css/model-editor.css'),'utf8');

test('editor da conferência se comporta como planilha',()=> {
  assert.match(js,/const columnLetter = index =>/);
  assert.match(js,/cellAddress = \(row, col\)/);
  assert.match(js,/event\.key === 'Enter'/);
  assert.match(js,/event\.key === 'Tab'/);
  assert.match(js,/key === 'z'/);
  assert.match(js,/key === 'y'/);
  assert.match(js,/key === 's'/);
  assert.match(js,/editor-formula-bar/);
  assert.match(js,/editor-name-box/);
  assert.match(js,/Salvo automaticamente/);
  assert.match(js,/matrix = text/);
  assert.match(css,/\.editor-col-letter/);
  assert.match(css,/position:sticky/);
  assert.match(css,/\.editor-active-cell/);
});

test('editor continua recalculando a conferência automaticamente',()=> {
  assert.match(js,/scheduleReconcilePreview\(\)/);
  assert.match(js,/globalThis\.RazyncModelEditor/);
  assert.match(js,/file: \(\) => corrected/);
});
