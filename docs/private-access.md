# Acesso privado ao Razync

O login usa uma conta de e-mail e senha no Supabase Auth. O Razync não oferece cadastro público. O servidor valida o e-mail na lista de acesso e a senha no Supabase; depois emite uma sessão própria de oito horas. A sessão fica na aba do navegador e é invalidada ao sair ou reiniciar a API. A senha administrativa atual continua protegendo ações administrativas específicas.

## Ativação

1. Em **Authentication → Users**, crie ou confirme a primeira conta no projeto Razync Web. O titular define a senha diretamente no painel ou pelo fluxo de recuperação do Supabase. Não coloque senhas em arquivos, variáveis ou commits.
2. Configure no serviço da API `RAZYNC_AUTH_URL` com a URL HTTPS do projeto Supabase, `RAZYNC_AUTH_PUBLIC_KEY` com sua chave publicável e `RAZYNC_LOGIN_EMAILS` com os e-mails autorizados, separados por vírgula. Não use a chave de serviço.
3. Publique o frontend e a API com `RAZYNC_LOGIN_REQUIRED=0`. Teste o primeiro acesso em `/?testar-login=1`. Após a confirmação da entrada, ative `RAZYNC_LOGIN_REQUIRED=1`.
4. Confira que a página de login abre, que o titular consegue entrar, que a API devolve 401 sem sessão, que sair invalida a sessão e que as ações administrativas continuam exigindo autorização adicional.

A primeira fase dá aos e-mails autorizados acesso geral às ferramentas. Antes de adicionar colaboradores que não possam acessar todas as empresas, implemente autorização por carteira e empresa no servidor. O catálogo de contingência fica fora do pacote publicado, mas a cópia que já existia no histórico do repositório não é removida por essa mudança.
