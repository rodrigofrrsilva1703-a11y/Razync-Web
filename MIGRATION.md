# Plano de migração — Razync Web

## Princípio de segurança
O repositório original `Razync` permanece intacto e continua sendo a referência funcional até a homologação completa da nova versão.

## Fase 1 — Fundação
- [x] Criar repositório separado
- [x] Publicar frontend no GitHub Pages
- [x] Deploy automático do frontend pela branch `main`
- [x] Catálogo real com 48 empresas e pesquisa instantânea
- [x] Painel web por empresa
- [x] Estrutura para upload e download do Modelo Domínio

## Fase 2 — Backend/API
- [x] Copiar módulos Python centrais do Razync para `backend/legacy/razync`
- [x] Preservar template do Modelo Domínio em recurso privado do backend
- [x] Criar FastAPI
- [x] Criar Dockerfile
- [x] Preparar configuração Railway
- [x] Criar health-check
- [x] Criar verificação automática de sintaxe no GitHub Actions
- [x] Configurar CORS para o GitHub Pages
- [ ] Publicar API Python
- [ ] Conectar URL pública da API ao frontend

## Adaptadores API já preparados
- [x] 47 — Banco do Brasil · conta 8
- [x] 88 — Itaú
- [x] 154 — Bradesco · conta 9 / Itaú · conta 508
- [x] 625 — Banco do Brasil / Caixa / Sicredi
- [x] 626 — Banco do Brasil / Sicredi
- [x] 841 — Banco Inter · conta 506
- [x] 912 — Sicredi · conta 515
- [x] 964 — Bradesco · conta 9
- [x] 969 — Itaú · conta 508
- [x] 1208 — Itaú / Safra / Bradesco
- [x] 1530 — Itaú XLS/XLSX
- [x] 1532 — Itaú · conta 508

## Fluxos complexos preservados no backend e ainda a ligar à API web
- [ ] Grupo Autokraft
- [ ] 242 — Eletro Forte
- [ ] 266/1396 — Nova Geração
- [ ] 285 — L. Carlos
- [ ] 968 — Radani
- [ ] 1000/1001 — Accede
- [ ] 1096 — UP PACK
- [ ] 1211 — GZ
- [ ] 1402 — VGV
- [ ] 1408 — Eletro Forte Filial
- [ ] 1529 — Dias Pereira
- [ ] Base Inteligente
- [ ] Conferência com Extrato
- [ ] Conferência Fiscal / DCTFWeb
- [ ] Conector Windows / eCAC

## Homologação obrigatória
Cada ferramenta só será marcada como concluída depois de comparar com a versão Streamlit:

- quantidade de lançamentos;
- total de entradas e saídas;
- datas;
- históricos;
- contas de débito/crédito;
- exclusão correta de linhas de saldo;
- arquivo Excel final;
- conferência com extrato;
- comportamento em desktop e mobile.
