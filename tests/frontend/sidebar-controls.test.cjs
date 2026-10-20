const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/js/workspace-ui.js', 'utf8');
const controls = source.slice(source.indexOf('function initializeSidebarControls()'), source.indexOf('function initializeCompanyControls()'));
function setup({small = false, saved = 'false', unavailable = false} = {}) {
  const attrs = {}, classes = new Set(), writes = [];
  const toggle = {setAttribute: (key, value) => attrs[key] = value, addEventListener: (_, fn) => toggle.click = fn};
  const sidebar = {inert: false};
  const media = {matches: small, addEventListener: (_, fn) => media.change = fn};
  vm.runInNewContext(controls + '\ninitializeSidebarControls();', {
    document: {querySelector: id => id === '#sidebarToggle' ? toggle : sidebar,
      body: {classList: {toggle: (name, on) => on ? classes.add(name) : classes.delete(name)}}},
    window: {matchMedia: () => media, dispatchEvent: () => {}}, Event: class {},
    localStorage: {getItem: () => { if (unavailable) throw Error(); return saved; },
      setItem: (key, value) => { if (unavailable) throw Error(); writes.push([key, value]); }},
  });
  return {attrs, classes, writes, toggle, sidebar, media};
}

test('lateral compacta mantém os atalhos acessíveis e salva a escolha', () => {
  const h = setup();
  h.toggle.click();
  assert.equal(h.attrs['aria-expanded'], 'false');
  assert.equal(h.attrs['aria-label'], 'Expandir menu lateral');
  assert.equal(h.sidebar.inert, false);
  assert.ok(h.classes.has('sidebar-collapsed'));
  assert.deepEqual(h.writes[0], ['razync.sidebar-collapsed', 'true']);
  h.toggle.click();
  assert.equal(h.attrs['aria-expanded'], 'true');
  assert.equal(h.attrs['aria-label'], 'Recolher menu lateral');
});

test('menu oculto no celular sai da navegação e volta ao mudar para computador', () => {
  const h = setup({small: true, saved: 'true'});
  assert.equal(h.sidebar.inert, true);
  assert.equal(h.attrs['aria-label'], 'Abrir menu lateral');
  h.media.matches = false; h.media.change();
  assert.equal(h.sidebar.inert, false);
  assert.equal(h.attrs['aria-label'], 'Expandir menu lateral');
  h.media.matches = true; h.media.change();
  assert.equal(h.sidebar.inert, true);
  h.toggle.click();
  assert.equal(h.sidebar.inert, false);
});

test('controle continua funcionando quando o armazenamento está indisponível', () => {
  const h = setup({unavailable: true});
  assert.equal(h.attrs['aria-expanded'], 'true');
  h.toggle.click();
  assert.equal(h.attrs['aria-expanded'], 'false');
});
