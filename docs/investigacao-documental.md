# Investigação documental fiscal

Etapa opcional depois de conferir Razão × Resumo por Acumulador. Os relatórios
de Entradas e Saídas são cruzados somente nas contas divergentes ou com alertas,
respeitando empresa, CNPJ, filial e período. Arquivos e lançamentos não são alterados.

Uma correspondência automática exige conta, documento explícito (NF, CTRC ou
CT-e), valor e data iguais, além de associação única nos dois sentidos. Datas
diferentes continuam pendentes. Números inferidos, duplicidades possíveis e
valores diferentes exigem revisão. Linhas auxiliares de impostos e totais são
excluídas da leitura documental.

O cruzamento local considera todos os registros. A tela mantém todos os registros e pagina a leitura, priorizando documentos
pendentes. A paginação não limita a seleção de contexto da IA.

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

## Investigação explicativa por pendência

A versão `documentary-evidence-v12` acrescenta um roteiro local para cada
comparação pendente e cada movimento sem vínculo, preservando os documentos
agrupados como um único caso. Cada roteiro traz candidatos, valores calculados,
campos coincidentes/divergentes/a confirmar, leitura dos indícios, informação
faltante e ação de conferência específica. As categorias de evidência são
qualitativas; não são probabilidades nem confirmação da causa contábil.

O contexto externo recebe até três roteiros prioritários cujas referências estão
disponíveis na seleção enviada. Groq remove um roteiro se o candidato da própria
conta não couber nos seus dez históricos. Os detalhes completos permanecem locais,
em uma seção recolhida, com paginação visual de vinte casos e montagem das
evidências ao abrir cada caso. As orientações agrupadas por tipo de divergência
continuam sendo a leitura principal, sem repetir o mesmo roteiro para cada nota.
Não há nova chamada por expansão nem por exportação. Aumenta-se a reserva de saída
somente quando existem roteiros para explicar; o detalhamento numérico fica local.

As interpretações são filtradas por afirmação: trechos válidos permanecem mesmo
quando outro trecho é retirado. Somente trechos validados que citam referências do
próprio caso são associados como interpretação da IA nesse detalhe. O roteiro
local é identificado separadamente e não é apresentado como leitura integral da IA.
As verificações específicas validadas aparecem na tela e no Excel, que passa a
incluir as abas `Pendências explicadas` e `Evidências por pendência`, com históricos
e contrapartidas dos candidatos. O cache anterior é invalidado pela versão.

## Resumo e critérios de conclusão

`explanatory-review-v13` apresenta uma leitura numérica da diferença e a primeira
ação baseada nas prioridades locais, sem pedir uma segunda resposta à IA. Totais
iguais não são apresentados como confirmação de vínculos. Contextos parciais,
inclusive compactação de históricos, mantêm a identificação da cobertura.

Cada tipo de pendência tem critérios para concluir a conferência e situações em
que o candidato ou hipótese deve ser reavaliado. São instruções condicionais,
nunca fatos presumidos. Esses critérios acompanham os casos prioritários enviados
às IAs gratuitas e as orientações exibidas e exportadas. O prompt solicita indícios
contrários à hipótese e proíbe tratar campos desconhecidos como coincidências.
O novo leitor separa conclusão, prioridade, interpretação e evidências; os critérios
ficam recolhidos para manter uma leitura curta, também no celular.


## Leitura e parcelas complementares

`clear-documentary-review-v14` reconhece o parceiro depois da referência explícita
à NF/CTRC, inclusive em históricos `FRETES - #CREF. NF ... - PARCEIRO`. O agrupamento
continua exigindo mesma nota, conta, data, parceiro e série compatível; repetições
indistinguíveis permanecem pendentes.

Os indicadores documentais contam linhas fiscais conciliadas e para revisar,
separando os movimentos sem vínculo. Assim usam a mesma unidade dos totais locais
exibidos na IA. Pesquisas por acumulador priorizam pendências e mostram a diferença
da conta inteira como contexto; documentos conciliados continuam disponíveis no filtro.

A conclusão, composição da diferença e critérios de revisão ficam visíveis.
As notas e valores selecionados aparecem em uma tabela principal, sem repetição
no resumo e no roteiro. Evidências individuais continuam opcionais e paginadas.
Pareceres locais identificam a leitura como gerada pelo sistema. Códigos internos
são traduzidos após a validação das afirmações e o prompt pede frases mais curtas,
sem novas chamadas nem aumento dos limites dos provedores gratuitos.
