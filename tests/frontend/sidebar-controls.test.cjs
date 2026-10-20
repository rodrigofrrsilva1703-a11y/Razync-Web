const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/js/workspace-ui.js', 'utf8');
const controls = source.slice(source.indexOf('function initializeSidebarControls()'), source.indexOf('function initializeCompanyControls()'));
function setup({saved = 'false', unavailable = false} = {}) {
  const attrs = {}, classes = new Set(), writes = [];
  const toggle = {setAttribute: (key, value) => attrs[key] = value, addEventListener: (_, fn) => toggle.click = fn};
  const sidebar = {inert: false};
  vm.runInNewContext(controls + '\ninitializeSidebarControls();', {
    document: {querySelector: id => id === '#sidebarToggle' ? toggle : sidebar,
      body: {classList: {toggle: (name, on) => on ? classes.add(name) : classes.delete(name)}}},
    window: {dispatchEvent: () => {}}, Event: class {},
    localStorage: {getItem: () => { if (unavailable) throw Error(); return saved; },
      setItem: (key, value) => { if (unavailable) throw Error(); writes.push([key, value]); }},
  });
  return {attrs, classes, writes, toggle, sidebar};
}

test('recolher oculta toda a navegação e salva a escolha', () => {
  const h = setup();
  h.toggle.click();
  assert.equal(h.attrs['aria-expanded'], 'false');
  assert.equal(h.attrs['aria-label'], 'Abrir menu lateral');
  assert.equal(h.sidebar.inert, true);
  assert.ok(h.classes.has('sidebar-collapsed'));
  assert.deepEqual(h.writes[0], ['razync.sidebar-collapsed', 'true']);
  h.toggle.click();
  assert.equal(h.attrs['aria-expanded'], 'true');
  assert.equal(h.attrs['aria-label'], 'Recolher menu lateral');
});

test('preferência salva mantém o menu oculto até reabrir pelo controle', () => {
  const h = setup({saved: 'true'});
  assert.equal(h.sidebar.inert, true);
  assert.equal(h.attrs['aria-label'], 'Abrir menu lateral');
  h.toggle.click();
  assert.equal(h.sidebar.inert, false);
  assert.equal(h.attrs['aria-expanded'], 'true');
});

test('controle continua funcionando quando o armazenamento está indisponível', () => {
  const h = setup({unavailable: true});
  assert.equal(h.attrs['aria-expanded'], 'true');
  h.toggle.click();
  assert.equal(h.attrs['aria-expanded'], 'false');
});
