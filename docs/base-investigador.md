# Investigação opcional da Base Inteligente

Ensinar base e Classificar mantêm seu motor original. A investigação aparece após classificar e usa o Blob do Excel efetivamente gerado, sem nova seleção do usuário. A classificação da Base solicita o Excel binário para impedir que a investigação refaça silenciosamente um processamento cujo cache expirou.

O Python identifica pendências conforme os perfis existentes (incluindo 242/1408), exclui Principal nos perfis Eletro, Retirados e destinos com fórmulas. Consulta assinaturas exatas, evidências abaixo de três períodos, conflitos e similaridades em outros bancos da mesma empresa. O catálogo permite consultar contas históricas por natureza. Contas e justificativas são sempre calculadas/validadas localmente.

Somente grupos ambíguos com candidatos podem solicitar uma chamada de IA gratuita, com até 12 descritores anônimos, resposta limitada e timeout de 15 segundos. A IA apenas prioriza revisões: não recebe históricos, valores, nomes, contas, datas ou arquivos e não escolhe contas nem executa ferramentas. Reutiliza a seleção gratuita e o orçamento compartilhado existentes, sem fallback automático nem novas dependências.

Agrupamento conservador por banco, natureza, assinatura e histórico normalizado completo; diferenças materiais de descrição continuam separadas. Forte exige conta única sem conflitos e pelo menos dois períodos comprovados no mesmo banco. Correspondência exata com um período/outro banco é moderada. Similaridade isolada e conflitos exigem revisão manual. Nenhuma linha começa aprovada.

POST /api/v1/base-inteligente/{empresa}/sugerir-pendentes consulta sem escrever. POST /api/v1/base-inteligente/{empresa}/revisar reutiliza o escritor Excel existente e recebe investigacao_token quando originado desta tela. O token vincula empresa, hash do arquivo, versão da base e opções. O servidor revalida destinos, natureza e contas antes de aplicar exclusivamente as linhas selecionadas. Aprendizado é desmarcado por padrão; se aprovado, recebe origem sugestao_agente_aprovada.

Cache e tickets são voláteis, por processo, até 32 investigações por 20 minutos. Reinício/expiração exigem nova investigação; várias instâncias podem invalidar tickets ao alternar servidor. Cancelar aborta a espera no navegador; uma chamada externa já iniciada pode terminar no servidor (máximo 15 segundos). Não existe plano de contas ativo integrado: a interface avisa que o histórico não comprova conta ativa. IA indisponível preserva todas as evidências locais. Não há garantia de acerto de classificação: a decisão é humana.

Testes sintéticos: períodos 1/2/3, conflitos, bancos/empresas/filial, naturezas, placeholders, cache, expiração, resposta externa inválida, cotas sem chamadas reais, aprovação parcial, aprendizado opcional, fórmulas/formatação e abas Principal/Retirados, além do contrato HTTP de investigação/revisão.

## Histórico de contas e janela flutuante
O catálogo retorna até oito exemplos de históricos aprendidos por conta/natureza, acompanhados de banco, períodos e ocorrências. O botão Histórico da conta apresenta exemplos da conta informada, inclusive após uma correção manual. Esses exemplos são referências de padrões salvos, não um razão completo. Nenhum histórico adicional é enviado à IA externa.
A investigação usa janela contextual flutuante com minimizar, ampliar e reabrir, preservando escolhas. Ao trocar empresa/arquivo, invalida a investigação; ao sair da ferramenta, oculta a janela. O painel fica fora de ancestrais animados para preservar seu posicionamento na tela.

## Revisão rápida por comparação
A revisão tem somente a janela flutuante, sem painel duplicado dentro do formulário. O botão indica quantas pendências estão disponíveis. A consulta inicial é local (usar_ia=false), permitindo conferir as evidências sem esperar pelo provedor. A priorização por IA é opcional e altera apenas a ordem da fila, preservando rascunhos e aprovações; o token original continua sujeito à validação de versão da base.
A fila permite filtrar sugestões, casos manuais e aprovações. Cada lançamento é comparado lado a lado com exemplos da conta, abertos automaticamente; palavras compartilhadas são destacadas apenas como auxílio visual. Aprovar e próximo registra uma decisão de revisão, sem aplicar Excel nem aprender até o comando final. Alterar a conta invalida a aprovação anterior. Ensinar base, assinatura, critérios dos três períodos e classificação automática permanecem intactos.

## Preparação automática e revisão de equivalentes
Após classificar, a consulta local de pendências é preparada em segundo plano, sem abrir a janela nem chamar provedores de IA. Abrir ou reabrir reutiliza essa preparação. Cancelamento não reinicia automaticamente; alteração de contexto aborta e invalida o trabalho anterior.
O topo fixo reúne progresso, aprovação individual, pular e geração do Excel. A fila prioriza contas candidatas únicas e separa conflitos e ausência de histórico. O resumo informa os períodos e a relação com o banco, mantendo a justificativa detalhada disponível.
Grupos podem ser aprovados mediante uma confirmação separada com seleção individual, data, valor e referência de cada linha. Somente linhas do mesmo grupo original, banco, natureza, assinatura e histórico normalizado são elegíveis. Contas previamente digitadas diferentes começam desmarcadas. A seleção do grupo não grava dados; aprovações apenas compõem o lote a ser aplicado pelo endpoint já validado. Aprender permanece desmarcado por padrão.
