# Comparação dos modelos gratuitos — 19/10/2026

**Resultado: não há evidência para promover uma alternativa a modelo principal.** Dots respondeu pelo fluxo de produção, mas apresentou falhas de mérito. Não confundir JSON válido com orientação contábil correta.

Foram usados exclusivamente quatro casos fictícios fixos: diferença de valor, candidato em outra conta, ausência de documentos individuais e totais iguais com vínculo ambíguo. O prompt, as fontes e as restrições de custo zero e privacidade foram preservados. Não foram enviados anexos reais.

## Rodada pelo fluxo real de produção

Executada com `explain(..., only_openrouter=True)`, modelo fixo sem alternativa de modelo, mesmos filtros de conteúdo, controles de uso e validações do Razync. Os provedores que servem um mesmo modelo podem variar, como em produção.

| Modelo | Retorno nos quatro casos | Avaliação |
| --- | --- | --- |
| Dots3-Note Preview | 4 respostas aceitas pelo contrato; 3,75–7,57 s | Não aprovado como referência de qualidade: afirmou classificação onde havia apenas candidato, sugeriu completar valor a partir de um resumo e produziu orientação incoerente sobre duplicação. Os filtros locais retiraram parte da narrativa. |
| Nemotron 3.5 Lightning | 4 recusas: política de privacidade dos endpoints | Sem respostas para avaliar mérito; não foi flexibilizada a política. |
| Gemma 4 31B | 4 recusas: seleção de endpoints | Sem respostas para avaliar mérito. |

## Sondagem inicial

Uma primeira sondagem usou o mesmo prompt e contexto em pedidos textuais diretos, sem o transporte estruturado da produção. Serve para diagnosticar integração; **não é uma classificação justa do desempenho final do Dots**. Dots retornou quatro respostas fora do contrato; Liquid retornou HTTP 404; MiniMax retornou HTTP 400; Gemma retornou HTTP 429. Na rodada de produção, o transporte estruturado corrigiu os problemas de formato do Dots, mas não eliminou as falhas de análise.

## Decisão aplicada

- Manter a prioridade existente: não há candidato superior demonstrado nesta amostra.
- Retirar Apodex da lista padrão, pois não consta no catálogo gratuito consultado nesta data.
- Impedir que candidato em outra conta seja publicado como classificação confirmada.
- Retirar orientação que deduz duplicação apenas porque há uma nota única com vínculos ambíguos: pode haver desdobramentos legítimos.
- Não alterar a política de privacidade, não habilitar modelos pagos e não executar a comparação automaticamente em produção.

As respostas e os tempos observados estão no JSON adjacente. A amostra é pequena e não comprova desempenho geral, estabilidade futura nem precisão contábil. Limites e disponibilidade refletem a execução desta data. Os tempos incluem transporte e validação; não são uma medição isolada da velocidade do modelo. O ensaio é manual (`python -m app.fiscal_model_benchmark --run`) e não cria endpoint público.
