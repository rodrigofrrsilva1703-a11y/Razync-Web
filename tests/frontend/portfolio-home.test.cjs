const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/js/app.js', 'utf8');
const renderSource = source.slice(source.indexOf('function renderPortfolios()'), source.indexOf('function selectPortfolio('));

function setup(companies, portfolios) {
  const nodes = new Map();
  const element = tag => ({tag, children: [], attributes: {}, textContent: '',
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(name, callback) { this[name] = callback; },
  });
  const context = {companies, portfolios, portfolioList: element('div'), document: {createElement: element},
    $: id => { if (!nodes.has(id)) nodes.set(id, element('span')); return nodes.get(id); },
    selectPortfolio: id => { context.selectedId = id; },
  };
  vm.createContext(context);
  vm.runInContext(renderSource, context);
  context.renderPortfolios();
  return {context, nodes};
}

test('carteiras mostram totais reais e contam apenas as empresas do colaborador', () => {
  const {context, nodes} = setup([{codigo: 242}, {codigo: 626}, {codigo: 1000}], [
    {id: 'all', name: 'Rodrigo', companyCodes: null},
    {id: 'one', name: 'Ana', companyCodes: [626]},
  ]);
  assert.equal(nodes.get('#portfolioTotal').textContent, '2 carteiras');
  assert.equal(nodes.get('#portfolioCompanyTotal').textContent, '3 empresas');
  const cards = context.portfolioList.children;
  assert.equal(cards[0].children.find(x => x.className === 'portfolio-entry-quantity').textContent, '3 empresas na carteira');
  assert.equal(cards[1].children.find(x => x.className === 'portfolio-entry-quantity').textContent, '1 empresa na carteira');
  assert.equal(context.portfolioList.attributes['aria-busy'], 'false');
  cards[1].click();
  assert.equal(context.selectedId, 'one');
});

test('carteira vazia e nomes com caracteres especiais continuam acessíveis', () => {
  const {context, nodes} = setup([], [{id: 'empty', name: 'João & Maria', companyCodes: []}]);
  assert.equal(nodes.get('#portfolioTotal').textContent, '1 carteira');
  assert.equal(nodes.get('#portfolioCompanyTotal').textContent, '0 empresas');
  const card = context.portfolioList.children[0];
  assert.equal(card.attributes['aria-label'], 'Abrir carteira de João & Maria');
  assert.equal(card.children.find(x => x.className === 'portfolio-entry-info').children[0].textContent, 'João & Maria');
  assert.equal(card.children.find(x => x.className === 'portfolio-entry-quantity').textContent, '0 empresas na carteira');
});
