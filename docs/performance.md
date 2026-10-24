# Otimizações de processamento e carregamento

## Carregamento

- `lazy-assets.js` carrega fiscal/IA ao abrir a ferramenta; aplicações e resgates
  são carregados na primeira prévia de conciliação. Promessas compartilhadas
  impedem downloads/execuções duplicados; falhas permitem nova tentativa.
- `tools/build_frontend.py` combina apenas folhas de estilo consecutivas com
  a mesma função. Mantém a ordem original da cascata, caminhos relativos e
  scripts. Os bundles recebem uma versão pelo hash do conteúdo.
- A entrada publicada usa três folhas de estilo. CSS/JS iniciais passam de
  aproximadamente 739 KiB para 344 KiB antes da compressão HTTP. Isso mede
  recursos carregados inicialmente, não uma garantia de tempo ou de custo.

## Prévia e download

Clientes podem solicitar `X-Razync-Preview: 1` ao organizar ou classificar.
O backend devolve a prévia e um token para o mesmo Excel, sem baixar o arquivo
no navegador e reenviá-lo apenas para obter a prévia. APIs anteriores continuam
atendidas pelo fluxo binário original.

`X-Razync-Reuse: 1` nas prévias de conferência solicita o relatório para download
sem processar novamente os mesmos documentos. A conferência fiscal usa exatamente
o resultado do mesmo motor para gerar seu Excel.

O cache é privado, somente em memória: até 16 resultados e 32 MiB por processo,
com validade de 15 minutos. Não grava uploads ou resultados no disco, nem no banco.
Esses valores limitam apenas o cache; arquivos maiores continuam processáveis
pelo caminho original. Não foram adicionados limites de upload.

Tokens são aleatórios, não contêm empresa ou documento e não devem ser registrados
em telemetria da aplicação. Respostas usam `Cache-Control: no-store`. Em expiração,
evicção ou reinício, o frontend recalcula usando o snapshot original de arquivos,
bancos e período. Erros de acesso e cancelamentos não geram uma segunda chamada.

## CPU e memória

- Exportações Excel e conciliação do Razão foram movidas para o thread pool.
- A leitura da prévia Excel percorre linhas sem materializar toda a planilha;
  mantém todas as contagens e totais e a mesma amostra visual já existente.
- A exportação não copia novamente DataFrames que não serão modificados.
- A serialização de linhas evita uma lista intermediária de dicionários.

As regras de empresas, IA, formatos de saída e o expediente não foram alterados.
O teste de navegador usa somente uma cópia descartável `_smoke`, com API desligada;
o artefato publicado `_site` mantém o controle de horário original.

## Validação

Testes verificam equivalência dos valores, células, abas e formatos dos Excel;
isolamento, orçamento e expiração do cache; compatibilidade com respostas antigas;
retorno ao caminho original e preservação da cascata CSS. Testes de persistência
PostgreSQL exigem um banco de integração separado; não usar produção para testes.
