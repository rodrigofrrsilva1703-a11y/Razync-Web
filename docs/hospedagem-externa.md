# Hospedar o Jaguar Conecta em outro provedor

Use **Code → Download ZIP** na branch `main`. O ZIP contém a interface, a API FastAPI, os processadores, o Modelo Domínio e as migrações de banco. Credenciais, usuários do provedor de autenticação e dados de produção são gerenciados separadamente.

## 1. Subir a API

Na pasta que contém `backend/`, construa a imagem com a raiz do projeto como contexto. O Dockerfile instala as dependências Python e o Tesseract em português.

```sh
docker build -f backend/Dockerfile -t jaguar-conecta .
docker run -d --name jaguar-conecta --restart unless-stopped \
  --env-file /caminho/privado/jaguar.env \
  -v /caminho/privado/jaguar-data:/data \
  -p 127.0.0.1:8000:8000 jaguar-conecta
curl -fsS http://127.0.0.1:8000/health
```

O exemplo pressupõe um proxy HTTPS na mesma VPS, que encaminha o domínio da API para a porta local 8000. Configure o domínio da interface e o da API antes de abrir o acesso aos colaboradores.

| Variável privada | Configuração |
| --- | --- |
| `RAZYNC_LOGIN_REQUIRED` | Use `1` para exigir login. |
| `RAZYNC_AUTH_URL`, `RAZYNC_AUTH_PUBLIC_KEY` | Copie a configuração do provedor de autenticação atual para manter as contas existentes. |
| `RAZYNC_LOGIN_EMAILS`, `RAZYNC_ADMIN_EMAILS`, `RAZYNC_DEFAULT_COMPANY_OWNER` | Reaplique as permissões e o responsável padrão da instalação atual. As listas de e-mails são separadas por vírgula. |
| `RAZYNC_FRONTEND_ORIGINS` | Informe a origem HTTPS exata da nova interface, sem barra final. Separe várias origens por vírgula. |
| `RAZYNC_DB_PATH`, `RAILWAY_VOLUME_MOUNT_PATH` | No exemplo, use `/data/razync.db` e `/data`, respectivamente. O código usa a segunda variável para localizar arquivos persistentes mesmo fora do Railway. |
| `RAZYNC_DATA_BACKEND`, `RAZYNC_DATABASE_URL` | Replique a configuração de persistência atual. Em Postgres, preserve também o SQLite que contém o marcador de migração validado. |

Reaplique separadamente as variáveis das integrações que estiverem habilitadas, inclusive as chaves de IA e as configurações específicas de empresas. Mantenha o arquivo de variáveis fora da raiz pública.

## 2. Preservar o estado da instalação atual

Faça uma cópia consistente do volume da API antes da troca. O volume pode conter o banco SQLite, o marcador de migração do Postgres, os responsáveis pelas empresas, notificações e outras configurações. Use um backup consistente dos bancos SQLite ou copie o volume com o serviço sem escritas. Se mantiver o Postgres atual, conecte a nova API ao mesmo banco com a configuração e o marcador correspondentes. Para migrar para outro banco, restaure um backup compatível e valide o estado antes de apontar a interface para o novo servidor.

### Inventário da produção

| Origem | O que preservar |
| --- | --- |
| Supabase, projeto **Razync Web** | Banco Postgres, esquema privado `razync`: `classification_records`, `classification_imports`, `patterns`, `manual_tasks`, `company_task_status`, `custom_companies` e `migration_state`. A estrutura está em `supabase/migrations/`. Ao manter o projeto atual, a nova API reutiliza esses dados. |
| Provedor de autenticação | Mantenha o projeto de autenticação atual para reutilizar usuários e senhas. Reaplique as permissões definidas nas variáveis privadas da API. |
| Railway, serviço **razync-api**, volume **razync-data** em `/data` | Copie o volume inteiro. Entre os arquivos previstos pelo código estão `razync.db` (inclui o marcador de migração quando ativo), `company-owners.sqlite3` (responsáveis, notificações e configurações de empresas) e `razync_sessions.sqlite3` (sessões e atividade). |

Guarde os backups em armazenamento privado e mantenha as credenciais nas variáveis do novo ambiente. O ZIP contém as migrações e o código que cria as tabelas locais. Na validação da restauração, compare a lista de empresas, responsáveis, tarefas e períodos aprendidos com a instalação atual antes de trocar o DNS.

## 3. Publicar a interface

1. Altere `apiBase` em `assets/js/config.js` para a URL HTTPS da nova API.
2. Na raiz do ZIP extraído, execute `python3 tools/build_frontend.py --output dist --private-catalog`. A pasta de saída deve ser nova.
3. Publique somente o conteúdo de `dist/` como site estático.
4. Antes de mudar o DNS, confira o `/health`, teste o login de um administrador e de um colaborador e valide a carteira, os responsáveis, as tarefas, a Base Inteligente e um fluxo de prévia e download com arquivos de teste.
