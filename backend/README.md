# Backend Razync Web

FastAPI executa no Railway; GitHub Pages hospeda a interface JavaScript. O repositório `Razync` é referência somente para leitura.

## Importante

O GitHub Pages NÃO executa este código.

O backend será publicado em um serviço próprio e será responsável por:

- leitura de PDF, XLS e XLSX;
- conversão para Modelo Domínio;
- Base Inteligente;
- conferência com extrato;
- conferência fiscal;
- regras específicas de cada empresa;
- integrações que exijam credenciais.

Nenhuma senha, certificado, token privado ou chave de serviço deve ser exposta no frontend do GitHub Pages.

## Execução e validação

```sh
pip install -r backend/requirements.txt
pip install pytest httpx
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m pytest tests -q
```

O Dockerfile inclui Tesseract em português e dependências de PDF/OCR. O workflow `backend-check.yml` constrói a imagem, verifica `/health`, catálogo e tarefas, e executa a comparação de processadores e arquivos Excel dentro dessa imagem.

## Configuração do Railway

| Variável | Uso |
| --- | --- |
| `PORT` | Railway fornece automaticamente |
| `RAZYNC_DB_PATH` | Caminho SQLite; padrão `/data/razync.db`. Monte volume persistente em `/data` para preservar bases e tarefas nos deploys. |
| `RAZYNC_FRONTEND_ORIGINS` | Origens adicionais de CORS separadas por vírgula. GitHub Pages já incluído. |
| `RAZYNC_ACCESS_TOKEN` | Chave administrativa para copiar a base original, apagar bases e gerenciar A1. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Opcionais: leitura da tabela original `classificacoes_bancarias`. A importação não escreve no banco do Streamlit. |

As chaves ficam somente no backend. A chave administrativa digitada na interface não é gravada no armazenamento do navegador. O pareamento local mantém seu próprio token como no original.

## Motor e contratos

- `app/engine.py`: funções de negócio extraídas de `app.py` e `app_legacy.py`; sem executar Streamlit, com estado isolado por requisição.
- `resources/engine_manifest.json`: proveniência e hashes do código de referência.
- `legacy/razync/`: módulos originais preservados. `resources/Modelo dominio.xlsx`: template original.
- `app/migration_services.py`: arquivos complementares, filtros, consolidados, francesinhas e conciliação original por data/centavos.
- `app/classification_service.py`: Base Inteligente completa, revisão manual, isolamento por empresa, backup JSON e importação somente para leitura.
- `/docs`: contratos OpenAPI; `/api/v1/migration-status`: estado da validação/configuração.

Os testes verificam funções extraídas, contagens, valores, históricos, contas, remoções, abas e estilos do Excel. A homologação com documentos reais continua pendente; veja `MIGRATION.md`. O teste Sicredi 626 com saldo divergente também falha no original e está marcado como falha conhecida estrita, sem mudar o processador.

### Plano de resposta das IAs gratuitas

As três APIs usam o contrato de `app/fiscal_ai_strategy.py`: totais, sentido da diferença e evidências são conferidos localmente; o modelo descreve os indícios dos lançamentos, hipóteses sustentadas, limitações e duas ou três verificações específicas. Contas divergentes recebem alvo de 130–200 palavras (teto 220); valores iguais com alertas, 60–100 (teto 120). O orçamento de saída varia conforme a situação, sem chamadas extras para formatação. O texto original é preservado; respostas não são truncadas localmente para aparentar economia.

O contexto de Gemini/OpenRouter preserva lançamentos, datas, contrapartidas e históricos completos, eliminando apenas valores duplicados já presentes em `valores_brl`. Groq mantém a amostra declarada e os indicadores locais. A saída tem teto por quantidade de grupos, com margem para o raciocínio baixo da Groq. O teto não representa consumo real, nem garante que todos os modelos sigam o limite de palavras.

A formatação e a auditoria são locais. Os resultados validados continuam sendo reaproveitados pelo cache, cuja versão muda com o plano de resposta. Provedores/modelos pagos permanecem bloqueados; cota indisponível usa somente reservas gratuitas ou informa espera. Não são contratadas novas cotas.

O parecer também explica localmente o lado do Razão usado, os movimentos considerados e excluídos, o fechamento apenas por valor e o objetivo de cada conferência. A classificação por histórico é heurística; pagamento não comprova duplicidade. Essa leitura é atualizada nos pareceres em cache sem nova chamada ao modelo.

A leitura do parecer separa conclusão, observações das fontes e hipóteses. Referências citadas são vinculadas somente à própria conta; referências inexistentes permanecem sinalizadas. Hipóteses de antecipação, ajuste interno e duplicidade exigem indícios nos históricos ou pares de movimentos/notas. Pareceres em cache recebem essa revisão local, sem nova geração. A cobertura de meses é apresentada como ponto de investigação, nunca como prova de omissão.
