# Uso eficiente da IA fiscal

O servidor preserva os cálculos da conferência e todas as contas divergentes.
Cada lote contém até duas contas. Não há chamada dupla obrigatória para obter
dois pareceres sobre a mesma conta.

## Encaminhamento

- Contas com até dez registros e históricos de até 180 caracteres: Groq,
  quando habilitada. Nesse caso a amostra contém todos os registros do lote.
- Mais registros ou históricos extensos: Gemini, quando habilitado, recebendo
  todos os registros do lote. Não se reduz esse contexto a dez exemplos.
- OpenRouter permanece como reserva usando os modelos gratuitos permitidos.
- Respostas inválidas continuam sendo rejeitadas pelo validador de grupos e
  referências; as reservas são acionadas pelo fluxo existente. Permissões ou
  configuração do OpenRouter não impedem tentar Gemini quando disponível.
- Se um provedor não estiver configurado, aplica-se o provedor disponível,
  com as limitações de cobertura já informadas na interface.

## Economia e espera

Gemini deixa de receber conta e valores numéricos repetidos em cada registro:
a conta permanece no resumo, valores exatos permanecem formatados em BRL,
e datas, históricos completos, contrapartidas e referências são preservados.
A estrutura original usada na conferência e validação não é alterada.

Os resultados completos e parciais ficam disponíveis somente na mesma sessão
temporária. Clicar novamente em analisar reutiliza os resultados concluídos.
Trocar arquivos/filtros, cancelar ou expirar descarta a sessão. Não existe cache
compartilhado de dados financeiros entre usuários ou armazenamento permanente.

O controle de pedidos por minuto é compartilhado pelo processo do servidor,
inclusive nas tentativas de reserva. Cada modelo admite uma chamada por vez;
a espera de concorrência é limitada a dez segundos. Ao esgotar o orçamento
estimado por minuto, retorna Retry-After para a espera/repetição da interface.
Tokens reportados pelo provedor substituem a estimativa do controle. Nenhum
prompt, histórico ou resposta é armazenado nesse controle.

Limites locais: Gemini 15 pedidos/250 mil tokens de entrada por minuto;
Groq 30 pedidos/8 mil tokens combinados por minuto por modelo;
OpenRouter 20 pedidos por minuto, sem estimativa de cota de texto.
O upstream continua sendo autoridade. A estimativa não é um tokenizador exato.
Não se promete cota diária: contas têm limites efetivos próprios.

Esse controle exige um único processo/réplica para cobrir todos os usuários.
Se a hospedagem passar a usar várias réplicas, é necessário controle externo
compartilhado antes de ampliar concorrência.

## Validação

### Distribuição coordenada entre três provedores

As sessões admitem somente provedores confirmados como gratuitos. Groq atende
lotes em que cada conta tem até dez históricos de até 180 caracteres. Contas
acima desses critérios usam Gemini ou OpenRouter, preservando o contexto
integral e sem reserva Groq por amostragem. Lotes com mais de 80 lançamentos
por conta ou históricos acima de 500 caracteres priorizam Gemini.

OpenRouter recebe um em quatro lotes curtos ou médios adequados quando existe
outro provedor disponível. O contador é compartilhado entre sessões no processo;
essa proporção conserva sua pequena cota e não representa disponibilidade
garantida. Cada lote contém até duas contas para amortizar o prompt. Falha
temporária ou resposta inválida tenta somente uma reserva disponível por vez;
nenhuma segunda opinião automática é pedida sobre um resultado já aceito.
Contas extensas nunca passam a uma reserva com amostragem. Se as reservas
acabarem, somente os lotes pendentes ficam para repetição.

A compactação sem perda de históricos também se aplica ao OpenRouter:
conta repetida por linha e valores numéricos com equivalentes BRL são retirados
do transporte; o contexto de validação permanece intacto. Não há promessa de
redução percentual de tokens. Dividir a carga não reduz por si só o volume;
reutilizar resultados e evitar análise duplicada reduzem chamadas desnecessárias.

OpenRouter pode ser diagnosticado isoladamente no endpoint multipart
`/api/v1/conferencia-fiscal/ia`, com `provedor=openrouter`. Nesse modo,
Gemini e Groq não assumem a resposta. O fluxo normal mantém suas reservas.
Em 10/10/2026, uma conta fictícia com dez lançamentos produziu uma análise
válida via `dots-studio/dots-3-note-preview:free`, com oito referências
validadas. Dots passou a ser a primeira opção padrão do OpenRouter.
O schema limita evidências às referências existentes; uma resposta inválida
permite uma correção usando o próximo modelo. Os filtros de preço zero e
`data_collection=deny` permanecem ativos. Esse teste confirma a integração,
mas não mede a qualidade em arquivos reais nem garante disponibilidade futura.

Testes sintéticos verificam encaminhamento por tamanho, preservação de todas
as contas e referências, validação dos provedores, orçamento por minuto,
renovação da janela e reutilização de resultados sem chamadas adicionais.
Não houve benchmark com arquivos reais nem medição de economia percentual
em produção. A economia garantida pelo fluxo é evitar chamadas de resultados
já concluídos na sessão e eliminar campos redundantes do contexto Gemini.
Uma segunda opinião seletiva por qualidade ainda exige critérios e benchmark;
não se usa a autoconfiança declarada pela IA como prova de correção.
