# Razync Web

Nova versão web do Razync.

## Objetivo

Migrar os processadores e ferramentas do Razync em Streamlit para uma arquitetura web com:

- Frontend estático publicado no GitHub Pages;
- Backend Python/API para os processamentos de PDF, Excel e regras contábeis;
- Reaproveitamento e validação dos processadores já existentes no Razync;
- Migração empresa por empresa sem alterar o sistema atual em produção.

## Regra de segurança da migração

O repositório original `Razync` continua sendo a referência funcional e não deve ser alterado por esta migração.

Cada ferramenta migrada deve ser comparada com o resultado da versão atual antes de ser considerada concluída.

## Estrutura inicial

- `index.html` — entrada do frontend;
- `assets/css/app.css` — identidade visual;
- `assets/js/app.js` — navegação e comportamento do frontend;
- `backend/` — API FastAPI publicada no Railway com os processadores originais;
- `assets/js/migration.js` — prévias, relatórios, revisão da base e conector;
- `MIGRATION.md` — controle das etapas da migração.
