# Investigador híbrido da Conferência Fiscal × Contábil

O botão **Analisar conta**, no modal existente, usa `/api/v1/conferencia-fiscal/ia/conta`.
Outras ferramentas e a análise geral de IA mantêm seus fluxos. Não há escrita em lançamentos.

## Investigação local

O servidor relê os arquivos usando `conferencia_fiscal_preview`, valida conta/natureza e usa o
cruzamento completo de `investigar_documentos` quando há acompanhamento fiscal. O recorte por
acumulador continua usando `recortar_acumulador_ia`, que rejeita vínculos compartilhados/ambíguos.
Não se usa a seleção de 30 pendências destinada ao antigo prompt para executar a investigação.

`fiscal_hybrid.py` examina os movimentos disponíveis na conta/natureza e os documentos do
acumulador, mantendo os índices R-n da leitura original. Os leitores existentes validam empresa,
filial e período. Todos os valores da investigação são tratados em centavos inteiros, convertidos
com Decimal e arredondamento HALF_UP. Os totais respeitam débito em entradas e crédito em saídas,
inclusive sinais negativos; movimentos descartados pelo leitor não voltam aos totais.

Verificações: totais, registros com data/valor/histórico/contrapartida repetidos, datas inválidas,
competência, notas sem correspondência identificada, diferenças de valores e datas, candidatos
em outra conta e redutores/estornos já identificados pelo cruzamento existente. Correspondências
por valor isolado não são criadas. Registros repetidos são indícios, nunca exclusões automáticas.

A busca de combinações é limitada: até 160 candidatos para valores individuais/pares, trios com
dois elementos entre os primeiros 60 e o terceiro entre os 160, e até cinco soluções por origem.
Sinais são preservados. Documentos fiscais sem vínculo também podem compor uma falta aparente.
O residual é calculado em centavos. Coincidência aritmética não prova vínculo nem causa contábil.

Não há corte de 1.500 lançamentos na investigação local. A apresentação retorna até 80 indícios e
120 evidências, com contagens e aviso explícito quando excedidos. A relação completa permanece
no cruzamento documental e nos arquivos originais. A busca é parcial e não demonstra inexistência
de outras combinações. Sem competências adjacentes, não é possível comprovar deslocamento mensal.

## IA opcional e custo de API

O usuário pode desmarcar a opção de IA. Por padrão, somente uma investigação documental com
mais de uma categoria de indício pode pedir priorização externa. Resumos sem documentos,
contas sem divergência/indícios e verificações locais simples não gastam chamada de IA.

`fiscal_hybrid_ai.py` seleciona um provedor já configurado, elegível e sem espera local:
Groq exige as confirmações existentes de plano gratuito e ZDR; Gemini exige a confirmação de
free tier e modelo Flash-Lite da lista permitida; OpenRouter aceita apenas `:free` ou
`openrouter/free`, com preço máximo zero, coleta desabilitada e sem fallback de endpoint.
Nenhuma chave é enviada ao frontend. O controle compartilhado `ai_budget.request_slot` é reutilizado.

Uma chamada HTTP, sem retries, reparo de JSON, mudança de modelo nem fallback após falha.
Timeout de 20 segundos; contexto limitado a 4.000 bytes; saída de até 384 tokens Gemini ou
512 tokens Groq/OpenRouter. O consumo real depende da tokenização e das cotas do provedor.

Não são enviados relatórios, históricos, nomes, CPF/CNPJ, contas, filiais, valores nem datas.
O contexto contém até oito indícios em forma de categoria/ID anônimo/quantidade de referências.
A resposta aceita somente até três IDs já existentes e um critério fechado de revisão. Texto
livre, referências inventadas e chamadas de ferramentas são rejeitados. A narrativa factual
continua sendo produzida localmente, sem possibilidade de o modelo afirmar nova causa contábil.

As APIs oferecem suporte variável a tool calling (consultado em 28/10/2026):
[Groq](https://console.groq.com/docs/tool-use/overview),
[Gemini](https://ai.google.dev/gemini-api/docs/function-calling),
[OpenRouter gratuito](https://openrouter.ai/docs/guides/routing/routers/free-router).
O fluxo deliberadamente não usa esse recurso: a investigação é orquestrada em Python e não
existe execução de funções decididas pelo modelo.

IA indisponível, cota esgotada ou resposta inválida não eliminam o resultado local. A tela
mostra o estado e a quantidade de chamadas. Não há promessa de disponibilidade gratuita
ilimitada. O Railway continua sujeito à cobrança normal de CPU/RAM/volume/tráfego do projeto.

## Cache e privacidade

Chave HMAC com versão das regras, dados estruturados completos, hashes dos arquivos, empresa,
filial, período, conta, natureza, acumulador e opção de IA. Mudança dos dados/regras invalida
o reaproveitamento. Requisições concorrentes idênticas não disparam duas análises.

Até 64 resultados por processo, por 30 minutos. Falhas de IA ficam em memória por apenas 60
segundos. O cache persistente existente é reutilizado quando o volume Railway e a chave Fernet
`RAZYNC_AI_CACHE_KEY` estão configurados: conteúdo criptografado, até 24 horas. Sem essa chave,
o cache continua em memória. Nenhum serviço externo foi adicionado.

## Apresentação e exportação

Modal existente com resumo, verificações, indícios, referências, tabela de evidências, limites e
conclusão sempre visíveis. Há rolagem local da tabela em telas menores. Históricos são inseridos
como texto, nunca HTML ou instruções. A exportação existente ganha duas abas apenas quando há
investigação híbrida: **Investigação híbrida** e **Fontes da investigação**. Textos que poderiam
virar fórmulas são neutralizados no Excel. As análises anteriores mantêm o formato existente.
