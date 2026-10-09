# Gemini — piloto fiscal da 242

No Railway, serviço `razync-api`, configure em Variables:

- `GEMINI_API_KEY`: chave criada no Google AI Studio. Nunca salvar no GitHub ou no frontend.
- `GEMINI_MODEL`: modelo compatível com generateContent e saída JSON; padrão `gemini-3.1-flash-lite`. Confirme disponibilidade e cota no seu projeto Google.

Após a publicação, abra a 242, faça a conferência. Não é necessária senha administrativa. Clique em “Analisar diferenças com IA”. Não informe a chave Gemini no site.

O servidor relê os mesmos arquivos da prévia. Somente categorias anônimas são enviadas ao Google: grupo temporário G1/G2, situação, débito/crédito, falta/excesso/zero e existência de adicionais. Não envia valores, datas, históricos, nomes, números de contas, documentos ou arquivos. O código da conta é associado novamente à resposta somente no servidor.

A IA explica categorias e propõe verificações; não lê os documentos originais, identifica duplicidade como fato nem altera cálculos, classificação ou Excel. As respostas são sugestões para revisão humana. Limite de 60 grupos e intervalo de 15 segundos entre chamadas por processo. Sem cache persistente de relatórios ou respostas.

Sem chave, sem cota, em falha de rede ou resposta inválida, a conferência normal permanece disponível. Testes usam respostas simuladas; é necessária uma chave válida para homologar uma chamada real ao Gemini.

Se o modelo configurado retornar 404, a integração tenta uma vez gemini-3.1-flash-lite. Outros erros não provocam troca de modelo.
