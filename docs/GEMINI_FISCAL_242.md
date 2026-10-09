# Gemini — Conferência Fiscal 242

Configure GEMINI_API_KEY no Railway. Modelo padrão: gemini-3.1-flash-lite.
Não exige senha administrativa. Intervalo mínimo de 15 segundos entre análises.
Se o modelo configurado retornar 404, tenta Flash Lite uma vez.

## Dados e resultado

Mediante autorização do usuário, o Google recebe os dados extraídos dos relatórios: totais fiscais e contábeis, datas, contas, contrapartidas, débitos, créditos e históricos completos (inclusive eventuais nomes e documentos). Os arquivos binários não são enviados. O aviso na interface informa esse tratamento.

A análise considera até 12 grupos com divergências/alertas e 1.500 registros, com cobertura declarada. Os registros pertencem às contas vinculadas aos acumuladores e à filial selecionada. Não representa auditoria integral do razão. Históricos excedendo 2 MB no contexto exigem um período menor.

O fiscal é resumo por acumulador, sem notas individuais. A IA deve distinguir fatos de hipóteses, respeitar diferença = contábil compatível - fiscal e não afirmar uma nota faltante sem evidência. Referências de evidências são verificadas no servidor e exibidas com os registros originais. A IA não altera cálculos ou arquivos; suas conclusões exigem revisão humana.
