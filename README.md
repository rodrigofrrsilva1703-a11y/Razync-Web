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


## Conferência Fiscal × Contábil — IA 100% gratuita no OpenRouter

O Razync usa **exclusivamente o OpenRouter gratuito por padrão**, sem executar
nenhum modelo de IA pago. O Gemini direto permanece desativado, mesmo se a
variável `GEMINI_API_KEY` antiga estiver presente no Railway. A única exceção
de compatibilidade é o modo legado explícito
`RAZYNC_AI_LEGACY_GEMINI=1`, reservado a testes de integração de versões
anteriores — **não configure essa variável na produção**.

### Configuração no Railway

- `OPENROUTER_API_KEY`: chave privada, armazenada nas variáveis de ambiente
  do serviço `razync-api`, nunca no GitHub ou em arquivos JavaScript.
- `OPENROUTER_MODELS` (opcional): lista separada por vírgulas de IDs
  exclusivamente gratuitos, como `openrouter/free` e
  `nvidia/nemotron-3-ultra-550b-a55b:free`. Padrão **`openrouter/free`**.
  Modelos comuns (sem o sufixo `:free`) e `openrouter/auto` são rejeitados.

O roteador `openrouter/free` escolhe entre modelos gratuitos disponíveis e
compatíveis com o formato exigido na análise. Se uma lista de vários modelos
`:free` for configurada, o modelo prioritário também alterna a cada nova
análise, com fallback. Todos os candidatos recebem o mesmo contexto fiscal,
período, acumuladores, Razão e referências.

### Travamentos de custo

1. Uma lista configurada com modelo pago causa erro **antes de enviar dados**.
2. A chamada exige `provider.max_price.prompt=0` e
   `provider.max_price.completion=0`, bloqueando endpoints cobrados.
3. Se nenhum serviço grátis estiver disponível ou a cota se esgotar, o Razync
   mostra um erro, **sem tentar uma IA paga**.
4. Nenhum cálculo contábil é feito pela IA; os resultados e referências
   continuam validados e a exportação Excel usa a análise já concluída.

A política de privacidade mantém `data_collection: deny` e
`require_parameters: true`. Isso reduz o conjunto de modelos elegíveis e
pode fazer a solicitação falhar — intencionalmente — quando não há provedores
gratuitos que respeitem essas condições. Dados contábeis são compartilhados
com o prestador de IA escolhido: verifique autorização, confidencialidade e
políticas de tratamento de dados antes de utilizar relatórios reais.

**Grátis não é ilimitado:** a conta Free do OpenRouter tem limite anunciado
de 50 requisições por dia, além de eventuais limites por modelo/provedor.
A conferência segue limitada a 12 grupos e 1.500 registros por análise.
É possível alterar a lista de modelos gratuitos; isso não remove os limites
compartilhados da conta OpenRouter.
