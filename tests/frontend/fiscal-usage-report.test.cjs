const {test} = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const root = path.join(__dirname, "../..");
const js = fs.readFileSync(path.join(root, "assets/js/fiscal-242.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "assets/css/fiscal-workspace.css"), "utf8");

class Element {
  constructor(tag = "div", className = "", content = "") {
    this.tag = tag;
    this.className = className;
    this.textContent = String(content);
    this.children = [];
    this.handlers = {};
    this.attributes = {};
    this.disabled = false;
    this.open = false;
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  addEventListener(event, cb) { this.handlers[event] = cb; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  showModal() { this.open = true; }
  focus() {}
  emit(type) { return this.handlers[type]?.(); }
}

test("botão discreto só carrega o relatório quando clicado, em diálogo acessível", async () => {
  const start = js.indexOf("  const usageButton =");
  const end = js.indexOf("  let aiCards = [];", start);
  assert.ok(start >= 0 && end > start);
  const snippet = js.slice(start, end);
  assert.doesNotMatch(snippet, /innerHTML\s*=/);
  const elements = new Map();
  const byId = id => elements.get(id) || elements.set(id, new Element()).get(id);
  const now = new Date().toISOString();
  const providers = ["groq", "gemini", "openrouter"].map((id, index) => ({
    id, nome: ["GroqCloud", "Gemini", "OpenRouter"][index],
    configurado: true, chamadas: 2, respostas: 1, falhas: 1,
    tokens_informados: 150, respostas_sem_tokens: 0,
    controle_local: {requisicoes_minuto: 20, tokens_minuto: null},
    modelos: [{modelo: "modelo-ficticio:free", chamadas: 2,
      respostas: 1, falhas: 1, ultima_chamada: now}]
  }));
  let calls = 0;
  const context = {
    byId, Intl, Date, AbortController,
    setTimeout: () => 1, clearTimeout: () => {},
    node: (tag, cssClass, contents) => new Element(tag, cssClass, contents),
    API: () => "https://api.example.invalid",
    fetch: async (url, options) => {
      calls += 1;
      assert.match(url, /conferencia-fiscal\/ia\/uso$/);
      assert.equal(options.cache, "no-store");
      return {ok: true, json: async () => ({
        data_utc: "2026-10-13", desde_utc: now,
        provedores: providers, observacao: "Histórico local desde reinício."
      })};
    }
  };
  vm.createContext(context);
  vm.runInContext(snippet, context);
  assert.equal(calls, 0);
  byId("fiscal242UsageButton").emit("click");
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 1);
  assert.equal(byId("fiscal242UsageDialog").open, true);
  assert.equal(byId("fiscal242UsageButton").attributes["aria-expanded"], "true");
  assert.equal(byId("fiscal242UsageContent").children.length, 5);
  const groq = byId("fiscal242UsageContent").children[1];
  assert.equal(groq.children[0].children[0].textContent, "GroqCloud");
  assert.equal(groq.children[1].children.length, 4);
  byId("fiscal242UsageDialog").emit("close");
  assert.equal(byId("fiscal242UsageButton").attributes["aria-expanded"], "false");
  byId("fiscal242UsageRefresh").emit("click");
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 2);
});

test("modal não ocupa a interface até ser aberto e mantém suporte mobile", () => {
  assert.match(html, /id="fiscal242UsageButton"[^>]*aria-haspopup="dialog"/);
  assert.match(html, /<dialog id="fiscal242UsageDialog"/);
  assert.match(html, /method="dialog"/);
  assert.match(css, /\.fiscal-usage-trigger[\s{]/);
  assert.match(css, /max-width:680px/);
  assert.match(css, /\.fiscal-usage-dialog:not\(\[open\]\)/);
  assert.match(css, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
});
