const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/js/workspace-ui.js', 'utf8');
const controls = source.slice(source.indexOf('function initializeSidebarControls()'), source.indexOf('function initializeCompanyControls()'));
function setup() {
  const classes = new Set(), handlers = {};
  const document = {activeElement: null, addEventListener: (name, fn) => handlers[name] = fn,
    body: {classList: {toggle: (name, on) => on ? classes.add(name) : classes.delete(name)}}};
  const node = () => ({attrs: {}, inert: false, events: {},
    setAttribute(key, value) { this.attrs[key] = value; },
    addEventListener(name, callback) { this.events[name] = callback; },
    focus() { document.activeElement = this; },
  });
  const toggle = node(), sidebar = node(), close = node(), backdrop = node(), main = node(), footer = node();
  const brand = node(), active = node(), last = node();
  const items = [close, brand, active, last];
  sidebar.querySelector = () => active;
  sidebar.querySelectorAll = () => items;
  sidebar.contains = target => items.includes(target);
  const nodes = {'#sidebarToggle': toggle, '#mainSidebar': sidebar, '#sidebarClose': close,
    '#sidebarBackdrop': backdrop, main, footer};
  document.querySelector = id => nodes[id];
  vm.runInNewContext(controls + '\ninitializeSidebarControls();', {document});
  return {document, classes, handlers, toggle, sidebar, close, backdrop, main, footer, active, last};
}

test('menu começa completamente fechado e abre sem desativar seus próprios atalhos', () => {
  const h = setup();
  assert.ok(h.classes.has('sidebar-collapsed'));
  assert.equal(h.sidebar.inert, true);
  assert.equal(h.sidebar.attrs['aria-hidden'], 'true');
  h.toggle.events.click();
  assert.equal(h.sidebar.inert, false);
  assert.equal(h.main.inert, true);
  assert.equal(h.footer.inert, true);
  assert.equal(h.toggle.attrs['aria-expanded'], 'true');
  assert.equal(h.document.activeElement, h.active);
});

test('clicar fora ou fechar devolve o foco ao botão e libera a página', () => {
  const h = setup();
  for (const control of [h.close, h.backdrop]) {
    h.toggle.events.click();
    control.events.click();
    assert.equal(h.sidebar.inert, true);
    assert.equal(h.main.inert, false);
    assert.equal(h.footer.inert, false);
    assert.equal(h.toggle.attrs['aria-expanded'], 'false');
    assert.equal(h.document.activeElement, h.toggle);
  }
});

test('Escape fecha somente quando o menu está aberto', () => {
  const h = setup(); let prevented = false;
  const event = {key: 'Escape', preventDefault: () => prevented = true};
  h.handlers.keydown(event);
  assert.equal(prevented, false);
  h.toggle.events.click(); h.handlers.keydown(event);
  assert.equal(prevented, true);
  assert.equal(h.sidebar.inert, true);
  assert.equal(h.document.activeElement, h.toggle);
});

test('selecionar uma ferramenta fecha o menu, clicar no restante do painel mantém aberto', () => {
  const h = setup(); h.toggle.events.click();
  h.sidebar.events.click({target: {closest: () => null}});
  assert.equal(h.sidebar.inert, false);
  h.sidebar.events.click({target: {closest: () => h.active}});
  assert.equal(h.sidebar.inert, true);
  assert.equal(h.main.inert, false);
});

test('Tab e Shift+Tab mantêm o foco dentro do painel aberto', () => {
  const h = setup(); h.toggle.events.click(); let prevented = 0;
  h.last.focus();
  h.handlers.keydown({key: 'Tab', shiftKey: false, preventDefault: () => prevented++});
  assert.equal(h.document.activeElement, h.close);
  h.handlers.keydown({key: 'Tab', shiftKey: true, preventDefault: () => prevented++});
  assert.equal(h.document.activeElement, h.last);
  assert.equal(prevented, 2);
});
