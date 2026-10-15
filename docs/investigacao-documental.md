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

## Economia e validação dos pareceres

O servidor calcula as diferenças documentais em centavos antes da IA. O valor
do Razão mostrado nessa comparação é de um candidato, não um vínculo fiscal
confirmado. Referências E-/S- citadas pela IA precisam existir no próprio grupo.
As evidências e a auditoria numérica incluem os documentos apresentados.

Pareceres são reaproveitados também por conta e natureza (entradas/saídas), com
empresa, filial, período, documentos e lançamentos no identificador do cache.
Uma mudança em outra conta não invalida automaticamente os grupos inalterados.
As referências dos registros fazem parte da chave para evitar reaproveitar
citações após mudar a numeração. O cache mantém os limites existentes: 30 minutos
em memória e até 24 horas no volume criptografado quando configurado.

Pessoas analisando os mesmos dados compartilham o resultado: uma chamada em
andamento bloqueia temporariamente outra chamada idêntica. O serviço admite até
16 sessões temporárias, para seis pessoas manterem ambas as etapas abertas.
A fila considera a pressão local por modelo e pode priorizar um provedor livre,
preservando as restrições de contexto e de custo zero. Cotas oficiais permanecem
sob controle dos provedores; não há promessa de 90 análises diárias.

Validação: testes de datas, transporte, pendências depois de 300 correspondências,
amostragem explícita, referências globais, sessão/cache, cancelamento e retomada.
Os arquivos reais usados na conferência local não fazem parte do repositório.

## Isolamento e publicação dos resultados

Cada consulta externa recebe somente uma conta e uma natureza (entrada ou saída),
mesmo quando a sessão agrupa duas contas em um lote. O sucesso de cada conta é
salvo imediatamente: uma falha na seguinte não exige repetir a primeira consulta.
Esse isolamento pode aumentar o número de chamadas novas por lote; o cache por
conta e a conferência local evitam repetições e consultas desnecessárias.

Quando todos os documentos fiscais já estão conciliados, a cobertura é completa,
a diferença inicial é zero e a composição comprova que restam somente pagamentos
separados na comparação inicial, o sistema apresenta uma conferência local sem
chamar os provedores. Isso não determina a natureza do pagamento nem sugere ajuste.
Qualquer condição incerta mantém a conta no fluxo de revisão por IA.

Fatos, valores e contagens publicados vêm dos cálculos locais. A IA escreve apenas
hipóteses e limitações curtas. Antes de exibir, exportar ou salvar no cache, o
servidor retira interpretações que citam notas de outra conta, referências
inexistentes, somas ou valores narrados pelo modelo, ou causas sem evidência nas
fontes. A tela informa o motivo da retirada e mantém um roteiro de conferência.
Essas verificações reduzem erros conhecidos, sem garantir o mérito contábil de uma
hipótese. A versão `grounded-isolated-v8` invalida pareceres de versões anteriores.

As regressões incluem notas cruzadas entre contas, somas incorretas, documentos já
conciliados e pagamentos iguais em datas diferentes. Respostas reais previamente
gravadas da empresa 242 também podem ser revalidadas localmente, sem reenviar os
arquivos nem consumir novas chamadas dos provedores.
