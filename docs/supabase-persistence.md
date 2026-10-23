# Persistência do Razync Web no Supabase

## Divisão desta etapa

- GitHub Pages: interface existente.
- Railway: API Python, leitura de PDF/Excel, OCR e conferências.
- Supabase Postgres: aprendizado e controle de importações, padrões legados,
  tarefas manuais, tarefas por competência e empresas cadastradas.
- Caches e cotas de IA continuam no volume local.
- Os documentos enviados não são arquivados no Supabase Storage.
- Login de colaboradores e acesso direto do navegador ao Supabase não foram
  acrescentados nesta migração. Não há chave secreta no frontend.

Projeto: `Razync Web`, região São Paulo (`sa-east-1`), plano gratuito.

## Credenciais e esquema

`RAZYNC_DATABASE_URL` é configurada somente nas variáveis privadas do Railway.
O login `razync_api` não é superusuário, não cria bancos/roles e não ignora RLS.
As tabelas ficam no esquema privado `razync`, com RLS e políticas apenas para
esse login. `anon` e `authenticated` não têm acesso ao esquema.

A API usa no máximo três conexões, TLS obrigatório e consultas parametrizadas.
A conexão direta do Supabase usa IPv6; o serviço Railway precisa ter saída IPv6
habilitada. Se for necessário usar o pooler, copiar a conexão exata no painel
Connect do projeto, sem presumir o nome do host.

## Preparar e ativar

1. Aplicar a migração em `supabase/migrations` no projeto separado.
2. Configurar `RAZYNC_DATABASE_URL` e validar a conexão antes da ativação.
3. Publicar o código inicialmente em modo SQLite. A simples presença da URL
   não muda a origem dos dados.
4. Configurar `RAZYNC_MIGRATE_ON_START=1` e publicar a versão validada. Na
   inicialização, `app.migrate_to_supabase` lê o SQLite do volume persistente,
   cria um backup completo e copia as seis tabelas em uma transação Postgres.
5. As contagens e o conteúdo canônico de todas as linhas são comparados por
   SHA-256. Só depois da conferência o marcador local ativa o Postgres.
6. Conferir saúde da API, empresas, tarefas, status da base e um processamento
   sintético. Nunca testar exclusão em dados reais para validar a implantação.

Também é possível executar `python -m app.migrate_to_supabase` dentro do
servidor com o volume montado. Não usar pre-deploy: volumes não estão montados
nessa fase do Railway. Não colocar senhas na linha de comando.

## Integridade e recuperação

A migração bloqueia novas escritas SQLite enquanto copia. Depois da ativação,
triggers impedem escritas locais nas tabelas migradas, inclusive de conexões
abertas antes da troca. O arquivo original e o backup permanecem no volume.

Se o destino estiver ocupado, se a conexão falhar ou se o conteúdo não bater,
a origem não é ativada no Postgres. Uma cópia preparada idêntica pode ser
reutilizada após uma interrupção. Conteúdo diferente exige análise; não é
sobrescrito automaticamente.

Depois da ativação, falhas de conexão nunca fazem fallback para o SQLite.
Isso evita dados divergentes. Para voltar, é necessário reconciliar primeiro
as alterações que ocorreram no Postgres: apagar o marcador ou restaurar o
backup antigo sozinho pode perder dados posteriores à migração.

O backup da migração fica no mesmo volume e não substitui cópias externas.
No plano gratuito, manter exportações periódicas do PostgreSQL fora do
Supabase e acompanhar tamanho do banco, tráfego e pausas por inatividade.

## Verificação

- `node --test tests/frontend/*.test.cjs`
- Em `backend/`: `python -m pytest tests -q`
- O workflow `Postgres persistence check` usa um PostgreSQL 17 descartável:
  testa cópia verificada, bloqueio de escrita local, tarefas, cadastros,
  exclusão por período, deduplicação concorrente e
  ausência de fallback durante indisponibilidade.

O cadastro A1 e o conector Windows foram descontinuados. A inicialização remove a tabela antiga da base local e das cópias pré-migração, preservando os registros contábeis e o marcador de migração.
