# Migração Razync → Razync-Web

O original em Streamlit permanece intacto. FastAPI no Railway e JavaScript no GitHub Pages publicam pela `main`.

## Implementação

- Módulos originais em `backend/legacy/razync/`; motor com 65 funções extraídas e comparação automática dos corpos.
- Fluxos completos: Autokraft 3/178/343; Eletro Forte 242/1408; Nova Geração 266/1396; L. Carlos 285; Radani 968; Accede 1000/1001; UP PACK 1096; GZ 1211; RGR 1248; VGV 1402; Dias Pereira/Nibo 1529; adaptadores 47/88/154/625/626/841/912/964/969/1208/1530/1532.
- Arquivos auxiliares, múltiplos PDFs, XLS/XLSX, ZIP, francesinhas, períodos, bancos, lançamentos retirados e relatórios usam as regras originais.
- Base Inteligente persistente: importação de modelos classificados/Razão/ZIP, classificação, revisão, aprendizado e backup JSON; preservação de assinaturas, ocorrências, períodos, conflitos e contas.
- Conferência com Extrato; Conferência Fiscal para 48 empresas; Impostos/DCTFWeb; conversor de extratos; conciliação com Razão; Central de Tarefas; Excel final para TXT Domínio.
- Conector Windows pela API: pareamento, certificado A1 criptografado, eCAC/DCTFWeb, extensão e automação Chrome incluídos no instalador.
- Chaves administrativas no Railway. Volume `/data` mantém a base entre deploys. Nunca incluir classificações reais, certificados ou chaves no Git.

## Validação

Os testes comparam os resultados com funções originais: lançamentos, entradas/saídas, datas, históricos, débito/crédito, remoção de saldos, abas, valores, estilos e Excel final. Também cobrem APIs, múltiplos bancos, classificação, relatórios, certificados sintéticos e TXT.

Um teste `xfail` registra comportamento que também falha no original Valean 626: saldo impresso divergente. A regra original permanece preservada.

Base Inteligente copiada em leitura do Supabase original para o volume do Railway: 12.634 registros, 21 empresas, todos os campos idênticos ao snapshot (inclusive períodos e ocorrências). Hash MD5 dos IDs ordenados: `2501922f8f42dd20b76571773a6396e5`. Dados privados ficam fora do repositório.

**Homologação com documentos reais pendente:** o usuário não possui mais os PDFs/planilhas e Excel finais usados anteriormente. Comparação de código e testes não substituem essa homologação. Adaptadores expõem `validation_status: pending_real_files`.

**eCAC pendente de execução real no Windows:** certificado do usuário, pareamento, login e download no portal. Testes com A1 sintético e pacote do conector não comprovam acesso autenticado ao eCAC.

## Publicação

- Frontend: https://rodrigofrrsilva1703-a11y.github.io/Razync-Web/
- Backend: https://razync-api-production.up.railway.app
- Saúde `/health`; catálogo `/api/v1/companies`; status `/api/v1/migration-status`.
- GitHub Actions verifica JavaScript, Python e runtime Docker. Railway reconectado à `main` após identificar que servia um commit antigo.
