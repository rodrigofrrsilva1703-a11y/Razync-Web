"""Verificações estáticas da interface Fiscal × Contábil sem dependências externas."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text("utf-8")
JS = (ROOT / "assets/js/fiscal-242.js").read_text("utf-8")
CSS = (ROOT / "assets/css/fiscal-results.css").read_text("utf-8")


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []
    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


p = Elements()
p.feed(HTML)
ids = [attrs["id"] for _, attrs in p.elements if "id" in attrs]
duplicates = [ident for ident, count in Counter(ids).items() if count != 1]
assert not duplicates, f"Elementos com ID duplicado: {duplicates}"

required = (
    "fiscal242Form", "fiscal242Results", "fiscal242Overview",
    "fiscal242ResultsCard", "fiscal242Investigacao", "fiscal242AISection",
    "fiscal242NextStep",
    "fiscal242NextStepButton", "fiscal242NextStepTitle",
    "fiscal242Acumuladores", "fiscal242Razao", "fiscalFilialCodigo",
    "fiscal242Entradas", "fiscal242Saidas", "fiscal242InvestigarBtn",
    "fiscal242AI", "fiscal242Download", "fiscal242Rows",
)
assert set(required).issubset(ids), "A interface não preserva controles fiscais essenciais."

anchors = [a.get("data-fiscal-target") for _, a in p.elements if "data-fiscal-target" in a]
assert set(anchors) == {"fiscal242Overview"}
assert "Assistente IA" in JS and "fiscal-account-ai-fab" in JS
assert "renderFiscalAssistant" in JS and "fiscal-account-ai-chat" in JS
assert "fiscal-account-analysis-tabs" not in JS
assert "renderHybridOpinion" in JS and "investigacao_hibrida" in JS
assert 'body.append("usar_ia",String(state.useAI))' in JS
assert "/api/v1/conferencia-fiscal/ia/conta" in JS
assert set(anchors).issubset(ids)

quick = [a.get("data-fiscal-filter") for _, a in p.elements if "data-fiscal-filter" in a]
assert set(quick) == {"todas", "bate", "alertas", "revisar"}
assert all(a in JS for a in ("syncQuickFilters()", 'focusFiscalSection("fiscal242Investigacao")',
                             'focusFiscalSection("fiscal242ResultsCard")',
                             'investigation.hidden', 'renderTable();'))
assert 'id="fiscal242ResultsCard"' in HTML
assert './assets/css/fiscal-results.css?v=' in HTML
assert any(tag == "script" and attrs.get("src", "").startswith("./assets/js/fiscal-242.js?v=")
           and attrs["src"].split("?v=", 1)[1] for tag, attrs in p.elements), "Script fiscal sem versão de cache."

assert "grid-template-columns:repeat(2,minmax(0,1fr))" in CSS
assert "@media (max-width:680px)" in CSS
assert "[hidden] { display:none!important; }" in CSS
assert CSS.count("{") == CSS.count("}"), "Chaves CSS não balanceadas."
assert 'content:attr(data-label)' in CSS
assert "prefers-reduced-motion" in CSS
assert 'document.createElement' in JS, "Linhas dinâmicas devem usar criação segura de nós."

print("Fiscal UI: IDs, navegação, filtros e layout responsivo verificados.")
