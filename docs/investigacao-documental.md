# Investigação documental fiscal

Etapa opcional depois de conferir Razão × Resumo por Acumulador. Os relatórios
de Entradas e Saídas são cruzados somente nas contas divergentes ou com alertas,
respeitando empresa, CNPJ, filial e período. Arquivos e lançamentos não são alterados.

Uma correspondência automática exige conta, documento explícito (NF, CTRC ou
CT-e), valor e data iguais, além de associação única nos dois sentidos. Datas
diferentes continuam pendentes. Números inferidos, duplicidades possíveis e
valores diferentes exigem revisão. Linhas auxiliares de impostos e totais são
excluídas da leitura documental.

O cruzamento local considera todos os registros. A resposta para a tela mostra
até 300 registros por conta, priorizando documentos pendentes. Esse limite de
visualização não é usado para selecionar o contexto da IA.

A IA recebe até 30 documentos pendentes e 30 movimentos por conta/tipo,
priorizando diferenças de valor/data e seus movimentos relacionados. Históricos
selecionados permanecem completos. Documentos conciliados e contas sem alertas
não são enviados. `cobertura_documental` informa os totais pendentes, a quantidade
enviada e se existe amostragem; conclusões não podem ser generalizadas à parte
não enviada. A tela apresenta essa cobertura.

`POST /api/v1/conferencia-fiscal/investigar/ia/sessoes` prepara os lotes usando
o mesmo coordenador gratuito de Gemini, Groq e OpenRouter. Os lotes são executados
em `/api/v1/conferencia-fiscal/ia/sessoes/{token}/lotes/{id}`. Resultados concluídos
são reutilizados por até 30 minutos; retomar falhas não reenvia lotes concluídos.
Trocar arquivos ou recalcular a investigação invalida a sessão da tela. Contextos
temporários são descartados ao cancelar ou expirar. A disponibilidade depende da
cota gratuita dos provedores; falhas da IA preservam a conferência local.

Validação: testes de datas, transporte, pendências depois de 300 correspondências,
amostragem explícita, referências globais, sessão/cache, cancelamento e retomada.
Os arquivos reais usados na conferência local não fazem parte do repositório.
