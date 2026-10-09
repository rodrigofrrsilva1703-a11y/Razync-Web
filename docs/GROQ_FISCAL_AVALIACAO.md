# GroqCloud na Conferência Fiscal × Contábil — avaliação controlada

Esta integração é **opt-in**. Por padrão o Razync continua usando o provedor já configurado. Nenhuma chamada é feita para a Groq apenas por ter o código publicado.

## Antes de ativar

1. No painel oficial da GroqCloud, confirmar que a organização/conta está **no plano gratuito** e que não existe cobrança habilitada. Consultar as cotas do plano em https://console.groq.com/docs/rate-limits.
2. Em **Data Controls**, habilitar **Zero Data Retention (ZDR)** e verificar a política para a organização em https://console.groq.com/docs/your-data.
3. Obter a chave da API na conta e armazená-la **somente nas variáveis privadas do Railway**, nunca no GitHub, site, chat, logs ou arquivos de teste. Não inserir dados reais antes de revisar autorização e privacidade.
4. Na produção, configurar `GROQ_API_KEY`, `GROQ_FREE_TIER_CONFIRMED=1`, `GROQ_ZDR_CONFIRMED=1`, `GROQ_MODEL=openai/gpt-oss-120b` e, **apenas para iniciar a avaliação**, `RAZYNC_AI_PRIMARY=groq`.

Se a confirmação de ZDR ou do plano gratuito estiver faltando, a integração Groq permanecerá inativa. A variável `GROQ_MODEL` só aceita `openai/gpt-oss-120b` (padrão) ou `openai/gpt-oss-20b`. Não existe seleção paga nem botão de teste novo.

## Comportamento

- O motor fiscal continua calculando a conferência e o Razão. A IA **não altera** os cálculos.
- A Groq recebe até **dois grupos** e até **dez lançamentos selecionados por grupo** em cada chamada; o resumo informa quando a amostra é parcial. CPFs/CNPJs comuns e e-mails dos históricos são suprimidos, mas **não se trata de anonimização completa**.
- As respostas exigem JSON Schema estrito e são validadas com as mesmas contas/valores/referências L no Razync.
- Se a Groq falhar e o Gemini gratuito já estiver configurado, o Gemini permanece como reserva. O OpenRouter já instalado também permanece disponível.
- Erros do provedor são registrados somente por código, sem expor documentos, credenciais ou respostas remotas.
- Os limites publicados do plano gratuito incluem **1.000 chamadas/dia**, **8.000 tokens/minuto** e **200.000 tokens/dia** por modelo nos modelos selecionados, sujeitos à conta e alterações. Solicitações grandes ainda podem receber HTTP 429; **não há garantia de disponibilidade**.

## Avaliação da qualidade

Usar **casos fictícios ou devidamente autorizados e minimizados**, comparar:
1. Divergência, sinal e valores oficiais sem nenhuma mudança;
2. Acumuladores corretos e referências existentes no Razão;
3. Nenhuma causa atribuída sem prova;
4. Checagens específicas de documentos, contrapartidas e períodos;
5. Consistência do JSON e taxa de respostas aceitas, incluindo falhas 429;
6. Latência e número de chamadas por relatório.

**Situação:** integração preparada e testável por mocks no CI. **Não há avaliação real da Groq sem uma chave autorizada e as confirmações do plano/ZDR**. Não afirmar que ela é melhor do que Gemini antes de validar com o mesmo conjunto de casos.


## Diagnóstico em produção — 09/10/2026

A conexão da versão 5af0910 foi validada com planilhas fictícias: HTTP 200, GPT-OSS 120B, 1,38 s. Os registros do servidor mostram falha 429 no quarto lote de uma análise maior. Isso confirma uma falha por quota, não uma chave globalmente inválida. Não foi possível reproduzir o arquivo específico do usuário sem seu erro/caso.

Correção: quando um modelo responde 429, tenta o outro GPT-OSS permitido, enviando somente os grupos ainda pendentes e mantendo os anteriores. Não alterna indefinidamente nem tenta modelos pagos. Prazo de controle de 75 segundos para os lotes Groq, com timeout de rede de no máximo 35 s por chamada; o timeout de socket não garante duração absoluta da leitura. Após falha dos dois modelos, permanece o fallback já existente para Gemini/OpenRouter.

O aviso de cobertura agora informa que a Groq recebe até dez lançamentos por grupo e históricos de até 180 caracteres. Essa integração continua sendo uma revisão de amostra, não leitura integral do arquivo. Documentos intermediários podem estar fora da amostra, e o truncamento de históricos pode omitir contexto relevante.

Também tenta o segundo modelo em caso de finish_reason=length (JSON truncado). Um JSON válido em um único bloco Markdown completo é aceito; referências inexistentes, grupos faltantes e JSON quebrado continuam rejeitados. A Groq foi aceita pelo backend no caso fictício pequeno; a causa exata do arquivo do usuário não foi reproduzida.


Na tentativa de 09/10/2026 às 21:56:59 UTC, após a publicação 6b522a8, o servidor registrou `Groq returned invented evidence`. A resposta Groq foi rejeitada e o provedor reserva concluiu a solicitação com HTTP 200. Esse diagnóstico vem da categoria de validação; o arquivo real e a resposta bruta não foram inspecionados.

Correção posterior: cada lote restringe `grupo` e `evidencias` com enumerações dos IDs enviados, e fornece uma lista explícita de referências por grupo. Lotes sem lançamentos exigem evidências vazias. A validação de pertencimento à conta continua obrigatória, pois a enumeração do lote pode conter referências de duas contas. Testes cobrem referências inventadas, referências de outra conta, amostra parcial e isolamento entre lotes. O teste fictício em produção não substitui a validação do relatório real do usuário.


Tentativas às 22:38 e 22:42 UTC: o 120B concluiu seis grupos antes do HTTP 429. A reserva 20B respondeu HTTP 403 com `model_permission_blocked_org`. O erro permanente da reserva interrompia a solicitação inteira antes do fallback Gemini. A correção classifica essa indisponibilidade da reserva como HTTP 503 para permitir o fallback gratuito já configurado. Um HTTP 403 do modelo principal continua sendo exibido. Quando a reserva está bloqueada, o fallback recalcula o parecer completo; os cálculos fiscais locais não são alterados. Para aproveitar os dois modelos Groq, é necessário habilitar o 20B nas permissões da organização/projeto GroqCloud.


Melhoria do parecer: a Groq recebe orientações para quatro parágrafos (fatos, diferença, hipóteses, limitações), três verificações numeradas e até três referências válidas. A meta é 140–190 palavras no total por grupo, sem aumentar os lotes ou o limite de tokens de saída. O formato efetivamente produzido depende do modelo.

Indicadores locais resumem os registros disponíveis antes da amostra: quantidade examinada, históricos vazios, menções a estorno/cancelamento/devolução, registros negativos, conjuntos com mesma data/histórico/contrapartida/débito/crédito e contagens das classificações do leitor. Não recalculam os totais nem comprovam erro. Valores inválidos ou não finitos e linhas sem data/histórico não entram na comparação de repetições. A entrada permanece limitada aos registros selecionados pelo contexto (até 1.500 no total); não se afirma leitura integral do arquivo. Os históricos enviados à Groq continuam limitados a dez por grupo e 180 caracteres. Testes verificam as contagens, exclusão de dados incompletos e sinais presentes fora dos dez históricos enviados.


## Cooperação Gemini + Groq

O frontend cria uma sessão temporária e distribui lotes de até duas contas alternadamente entre Groq e Gemini gratuito, com uma fila por provedor. Há no máximo dois pedidos de lote ativos por análise; os fallbacks existentes podem usar um provedor reserva. Escolher um provedor por lote não altera variáveis globais de ambiente. Os arquivos são lidos uma vez; as referências L preservam a posição original. Resultados concluídos são cacheados por lote até cancelar/expirar a sessão, sem repetir chamadas de IA em pedidos duplicados. O progresso conta grupos concluídos. Falhas não apagam pareceres de outros lotes e o resultado parcial informa grupos pendentes e erros.

Não há mais corte de 60/12 grupos, de 1.500 registros no contexto local, nem de 15 contas no Excel. O contexto de um pedido continua limitado a 2 MB, a exportação a 8 MB e os textos individuais a 6.000 caracteres; exceder esses limites produz erro explícito, sem truncamento silencioso. A Groq continua usando dez históricos por grupo e indicadores locais calculados sobre todos os registros da conta disponíveis na sessão. Gemini recebe os registros do lote; os limites reais de tokens, tempo, requisições e cotas dos provedores continuam valendo. Não afirmar que dividir trabalho economiza tokens automaticamente ou fornece capacidade ilimitada.

As sessões ficam somente em memória, têm identificador aleatório, expiram em 30 minutos com limpeza temporizada, e são descartadas pelo frontend ao concluir/cancelar. Até oito sessões abertas por processo são permitidas para conter memória do servidor. Reinício ou troca de processo expira a sessão; o usuário precisa anexar novamente. Não registrar tokens de sessão, dados fiscais ou conteúdo bruto do provedor. Não modificar o Razync original.


## Reservas e retomada dos lotes — 09/10/2026

Os registros às 23:10 UTC mostram cotas 429 e reservas OpenRouter indisponíveis ou com JSON inválido. A reserva Groq agora inclui `qwen/qwen3.8-27b`, listado no plano gratuito e compatível com JSON Schema estrito na documentação oficial. Qwen usa reasoning_effort=none, GPT-OSS usa low. Nenhum modelo fora da allowlist é chamado; as confirmações de plano gratuito/ZDR permanecem necessárias. As permissões Qwen foram adicionadas na organização e no Default Project. Fontes: https://console.groq.com/docs/rate-limits e https://console.groq.com/docs/structured-outputs.

Após 429, o modelo entra em espera usando Retry-After (15–300 s; padrão 60 s). Outros lotes evitam esse modelo até o prazo terminar. Parecer inválido é descartado e pode ser tentado em outro modelo permitido, mantendo a mesma validação de contas/referências. Um bloqueio apenas no modelo reserva permite tentar outra reserva; um 403 no principal continua explícito. Nenhuma referência inventada é aceita para concluir um lote.

O frontend aguarda a cota e repete uma vez o lote 429. Se ainda falhar, mantém a sessão e os resultados, oferecendo Repetir lotes pendentes. A retomada não repete upload/leitura ou chamadas de lotes concluídos. Trocar arquivos, cancelar ou concluir tudo descarta a sessão; a sessão incompleta expira no servidor em 30 min. Não há espera infinita, capacidade gratuita ilimitada ou garantia de qualidade igual ao Gemini.

A amostra Groq permanece em dez históricos por grupo, com até 180 caracteres. Em contas grandes, sinais de estorno/devolução, negativos e classificações extras/sem evidência podem substituir parte das linhas de começo/fim para trazer evidências do meio do período. Os indicadores locais ainda examinam todos os registros disponíveis. Essa seleção não é prova de erro, nem leitura integral dos históricos pela IA.


Teste em produção com 18 contas e 180 lançamentos fictícios: os 18 grupos concluíram em 26,84 s, todos em provedores gratuitos, com reservas Gemini. Qwen recebeu 429 nessa primeira tentativa; não afirmar que ele foi aceito por esse teste. O orçamento de saída Qwen foi reduzido de 3.000 para 1.800 tokens porque reasoning_effort=none não consome raciocínio no orçamento. GPT-OSS continua em 3.000. Logs distinguem request too large de outras cotas usando somente uma categoria fixa, sem revelar texto bruto.
