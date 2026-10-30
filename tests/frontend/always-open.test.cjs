const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function run(source, instant) {
  const redirects = [];
  const timers = [];
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [instant])); }
  }
  const setInterval = fn => timers.push(fn);
  const context = {Date: FixedDate, Intl, setInterval, window: {
    location: {replace: path => redirects.push(path)}, setInterval,
  }};
  vm.runInNewContext(source, context);
  return {redirects, timers};
}

const gate = fs.readFileSync('assets/js/operating-hours.js', 'utf8');
for (const instant of ['2026-10-25T09:59:00Z', '2026-10-25T10:00:00Z',
  '2026-10-26T02:59:00Z', '2026-10-26T03:00:00Z']) {
  test(`acesso liberado sem temporizador: ${instant}`, () => {
    const result = run(gate, instant);
    assert.deepEqual(result.redirects, []);
    assert.deepEqual(result.timers, []);
  });
}

test('link antigo da pausa volta imediatamente ao início, inclusive de madrugada', () => {
  const html = fs.readFileSync('indisponivel.html', 'utf8');
  const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const result = run(source, '2026-10-26T03:00:00Z');
  assert.deepEqual(result.redirects, ['./']);
  assert.deepEqual(result.timers, []);
  assert.match(html, /<meta http-equiv="refresh" content="0;url=\.\/">/);
  assert.match(html, /<a href="\.\/">/);
});
