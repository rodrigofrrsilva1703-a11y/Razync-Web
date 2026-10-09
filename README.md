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


## Conferência Fiscal × Contábil — OpenRouter e Gemini gratuito

O serviço Razync tenta a análise primeiro pelo **OpenRouter gratuito**.
Se o OpenRouter não responder por limite (429/402), indisponibilidade
ou resposta incompleta/inválida, tenta automaticamente a **Gemini API
gratuita** — somente quando autorizada no Railway. O usuário não precisa
trocar a IA manualmente; os pareceres continuam no mesmo painel e no
mesmo formato de Excel.

### Variáveis do Railway (`razync-api`)

- `OPENROUTER_API_KEY`: chave privada do OpenRouter no backend.
- `OPENROUTER_MODELS` (opcional): padrão `openrouter/free`; aceita
  somente `openrouter/free` ou IDs terminados em `:free`. Nunca chama
  modelo pago. O preço máximo permitido é zero para entrada e saída.
- `GEMINI_API_KEY`: chave do Google AI Studio já usada pela integração
  anterior; manter exclusivamente no Railway.
- `GEMINI_FREE_MODEL` (opcional): padrão `gemini-3.1-flash-lite`.
  Só aceita `gemini-3.1-flash-lite` e `gemini-2.5-flash-lite`.
- `GEMINI_FREE_TIER_CONFIRMED=1`: habilita o Gemini como reserva,
  **somente depois de verificar que o projeto da chave está sem
  faturamento associado e permanece no nível gratuito da Gemini API**.
  Sem esta variável, o fallback fica desligado por segurança.

**Não há como verificar programaticamente pelo token API se uma chamada
Gemini será faturada:** o nível de cobrança depende do projeto Google e
da conta vinculada. Não ative a confirmação em projeto pago. Não use
`RAZYNC_AI_LEGACY_GEMINI=1` na produção, pois esse modo não tem a
garantia de modelo restrito ao nível gratuito e existe só para migração
de testes antigos.

### Continuidade e consistência

Os dois provedores recebem os **mesmos dados extraídos**, período,
acumuladores, histórico, lançamentos, referências e instruções técnicas.
O JSON retornado passa pelo mesmo validador: nunca aceita conta de
outro relatório, valores inventados nem referências de lançamentos
inexistentes. Uma resposta parcial/incompleta é descartada; a reserva
refaz a solicitação inteira. As explicações podem variar na redação,
mas têm a mesma estrutura, checklist, evidências, totalizadores oficiais
e exportação Excel. O sistema indica o modelo utilizado discretamente.

Quando ambas as cotas estão esgotadas, a conferência contábil permanece
intacta e o usuário vê um único aviso de indisponibilidade. Não são
cobrados tokens pelo OpenRouter (`max_price=0`). Para o Google, a
garantia de gratuidade depende do projeto confirmado conforme acima.

**Privacidade:** o nível gratuito da Gemini API pode usar os dados
enviados para aprimorar produtos Google. Os históricos contábeis podem
conter nomes e outros dados de terceiros. Antes de habilitar, confirme
a autorização organizacional e a adequação das políticas de privacidade.
O OpenRouter mantém o filtro `data_collection: deny`.

Continuam existindo limites de requisições e processamento: uma análise
cobre até **12 grupos e 1.500 lançamentos**, e as cotas gratuitas de cada
provedor não são ilimitadas.


### Alternância gratuita para a conferência fiscal

Sem lista personalizada, ou com OPENROUTER_MODELS=openrouter/free, o Razync alterna os modelos google/gemma-4-26b-a4b-it:free, nvidia/nemotron-3.5-lightning:free e google/gemma-4-31b-it:free. O roteador openrouter/free fica como reserva. Lista revisada no catálogo público em 09/10/2026; é uma seleção para priorizar latência, não uma classificação de precisão contábil.

Endpoints são ordenados por latência, com preço máximo de entrada/saída zero e data_collection=deny. Mantém limite de geração também no JSON textual e desativa raciocínio estendido nesse modo. Timeout de rede de 18 segundos por tentativa; uma tentativa de reserva em caso de timeout, ou 12 segundos para formato alternativo após erro 400 em modelos personalizados. Esses limites de socket não constituem prazo absoluto de ponta a ponta. Modelo cujo pedido expirou fica fora das novas seleções por 90 segundos, no processo atual. Não contorna cotas da conta.

OPENROUTER_MODELS continua aceitando listas personalizadas apenas gratuitas. Todos os modelos recebem o mesmo contexto e passam pelas mesmas verificações de contas, grupos e evidências. O Gemini permanece reserva somente quando GEMINI_FREE_TIER_CONFIRMED=1. Modelos e disponibilidade gratuitos podem mudar; se todos falharem, a conferência calculada segue disponível.
