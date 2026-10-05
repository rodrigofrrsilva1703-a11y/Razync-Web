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
| `RAZYNC_DB_PATH` | Caminho SQLite; padrão `/data/razync.db`. Monte volume persistente em `/data` para preservar bases, tarefas e certificados nos deploys. |
| `RAZYNC_FRONTEND_ORIGINS` | Origens adicionais de CORS separadas por vírgula. GitHub Pages já incluído. |
| `RAZYNC_ACCESS_TOKEN` | Chave administrativa para copiar a base original, apagar bases e gerenciar A1. |
| `CERTIFICATES_MASTER_KEY` | Segredo de criptografia dos A1; preserve-o nos próximos deploys. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Opcionais: leitura da tabela original `classificacoes_bancarias`. A importação não escreve no banco do Streamlit. |

As chaves ficam somente no backend. A chave administrativa digitada na interface não é gravada no armazenamento do navegador. O pareamento local mantém seu próprio token como no original.

## Motor e contratos

- `app/engine.py`: funções de negócio extraídas de `app.py` e `app_legacy.py`; sem executar Streamlit, com estado isolado por requisição.
- `resources/engine_manifest.json`: proveniência e hashes do código de referência.
- `legacy/razync/`: módulos originais preservados. `resources/Modelo dominio.xlsx`: template original.
- `app/migration_services.py`: arquivos complementares, filtros, consolidados, francesinhas e conciliação original por data/centavos.
- `app/classification_service.py`: Base Inteligente completa, revisão manual, isolamento por empresa, backup JSON e importação somente para leitura.
- `/docs`: contratos OpenAPI; `/api/v1/migration-status`: estado da validação/configuração.
- `/api/v1/connector/download`: instalador Windows com automação e extensão Chrome. O conector continua local em `127.0.0.1:17891`; Railway não acessa certificados instalados no Windows.

Os testes verificam funções extraídas, contagens, valores, históricos, contas, remoções, abas e estilos do Excel. A homologação com documentos reais e eCAC continua pendente; veja `MIGRATION.md`. O teste Sicredi 626 com saldo divergente também falha no original e está marcado como falha conhecida estrita, sem mudar o processador.
