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

Testes sintéticos verificam encaminhamento por tamanho, preservação de todas
as contas e referências, validação dos provedores, orçamento por minuto,
renovação da janela e reutilização de resultados sem chamadas adicionais.
Não houve benchmark com arquivos reais nem medição de economia percentual
em produção. A economia garantida pelo fluxo é evitar chamadas de resultados
já concluídos na sessão e eliminar campos redundantes do contexto Gemini.
Uma segunda opinião seletiva por qualidade ainda exige critérios e benchmark;
não se usa a autoconfiança declarada pela IA como prova de correção.
