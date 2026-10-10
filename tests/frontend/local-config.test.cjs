const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../assets/js/config.js'), 'utf8');
for (const [hostname, origin, expected] of [
  ['127.0.0.1', 'http://127.0.0.1:8000', 'http://127.0.0.1:8000'],
  ['localhost', 'http://localhost:8000', 'http://localhost:8000'],
  ['rodrigofrrsilva1703-a11y.github.io', 'https://rodrigofrrsilva1703-a11y.github.io', 'https://razync-api-production.up.railway.app'],
]) {
  test(`interface ${hostname} usa o backend correto`, () => {
    const context = {window: {location: {hostname, origin}}};
    vm.createContext(context);
    vm.runInContext(source, context);
    assert.equal(context.window.RAZYNC_CONFIG.apiBase, expected);
  });
}
