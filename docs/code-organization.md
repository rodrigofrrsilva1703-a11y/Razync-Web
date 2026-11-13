# Organização do código

## Frontend

Os scripts continuam clássicos, sem uma etapa de build. A ordem de carregamento em
`index.html` é parte do contrato: os arquivos auxiliares são carregados antes de
`app.js`, que mantém o estado das empresas, os fluxos de upload e a inicialização.
Não adicionar inicializações duplicadas nos arquivos auxiliares.

| Arquivo | Responsabilidade |
| --- | --- |
| `dom-utils.js` | Escape de textos e atributos usados em templates HTML |
| `portfolios.js` | Catálogo de carteiras, seleção e retorno à entrada |
| `reconciliation-preview.js` | Cálculos e apresentação das tabelas de conciliação diária |
| `tasks-ui.js` | Exibição de tarefas, cadastro e opções de empresas |
| `app.js` | Coordenação dos fluxos e estado compartilhado; inicializa o catálogo uma vez |
| `fiscal-242.js` | Conferência fiscal e análise por IA, mantidas nesta etapa |

Funções auxiliares que dependem do estado de `app.js` só podem ser chamadas após
sua inicialização. Nomes, históricos e mensagens externos devem usar `textContent`;
em templates existentes, usar `RazyncDOM.escapeHTML` no ponto de interpolação.
Não aplicar escape aos dados enviados à API ou aos cálculos.

## Backend

`app/report_helpers.py` reúne exportação Excel, resposta de download, validação de
período e serialização da prévia. As rotas de `app/main.py` importam os mesmos nomes
para manter compatibilidade. Os processadores específicos, modelos de saída,
integrações de IA e fluxo de upload não foram alterados nesta reorganização.

## Verificação

- `node --test tests/frontend/*.test.cjs`
- `python tests/frontend_fiscal_smoke.py`
- Dentro de `backend/`: `python -m pytest tests -q`
- O workflow de Pages verifica a sintaxe de todos os arquivos `assets/js/*.js`.

A reorganização não adiciona restrições de upload nem altera estilos CSS.
