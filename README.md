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


## Conferência Fiscal × Contábil — IA via OpenRouter

O backend prefere **OpenRouter** quando `OPENROUTER_API_KEY` estiver configurada no
serviço `razync-api` do Railway. Até configurar essa chave, mantém a integração
existente do Gemini (`GEMINI_API_KEY`) para não interromper o site.

### Configuração no Railway

- `OPENROUTER_API_KEY`: chave de acesso, **somente no backend**. Nunca coloque
  essa chave em `index.html`, JavaScript ou repositórios Git.
- `OPENROUTER_MODELS` (opcional): modelos em ordem de prioridade, separados
  por vírgulas. Padrão:
  `openai/gpt-4.1-mini,google/gemini-2.5-flash,anthropic/claude-haiku-4.5`.

O Razync alterna o modelo inicial em cada conferência (rotação circular).
Na mesma solicitação, envia o conjunto de modelos para o OpenRouter, que
automaticamente tenta outro quando o primeiro fica indisponível, sujeito a
limites ou apresenta erros de roteamento. **Todos recebem o mesmo prompt,
período fiscal, acumuladores, Razão e referências dos lançamentos**. As
respostas continuam sendo conferidas pelo Razync antes da exibição, e
valores fiscais/contábeis não são recalculados pela IA.

O pedido exige JSON estruturado e somente provedores que respeitam os
parâmetros; a configuração `data_collection: deny` exclui provedores que
declaram usar os dados para treinamento. Ainda assim, as informações contábeis
são processadas por terceiros: avalie as permissões e políticas de privacidade
antes de enviar arquivos reais.

**Não existe limite infinito garantido:** os modelos gratuitos, saldos de
crédito, limites por minuto, limites do provedor e limites de contexto ainda
se aplicam. Recomenda-se definir um **teto de gastos na chave do OpenRouter**
antes de habilitar a integração. Se não houver saldo ou nenhuma alternativa
puder atender, o sistema mostra o erro e preserva os resultados locais.

A conferência atual continua limitada a **12 grupos e 1.500 lançamentos por
análise**, independentemente do provedor. O filtro temporal do Razão continua
sendo determinado pelo Resumo por Acumulador.
