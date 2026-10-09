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
