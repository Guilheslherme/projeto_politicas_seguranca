# Check-list do projeto

Documentação técnico-científica completa: `DocumentaçãoFinal-PoliticasDeSeguranca.docx`, na raiz do repositório.

## 1. Autenticação e Gestão de Credenciais

| Nº | Requisito | Situação | Implementação | Como demonstrar no front-end |
|---|---|---|---|---|
| 1.1 | Uso de hash criptográfico seguro para senhas (Argon2, bcrypt ou PBKDF2) | Atendido | `apps/accounts/hashers.py` e `PASSWORD_HASHERS` no `config/settings.py` | Criar uma conta em `/conta/register/` e consultar a coluna `password` no banco: o valor começa com `argon2$argon2id$` |
| 1.2 | Parâmetros de custo do hash configurados e justificados | Atendido | `ProjectArgon2PasswordHasher`, com `memory_cost=65536` (64 MiB), `time_cost=3` e `parallelism=2`, conforme a segunda configuração recomendada pela RFC 9106. Justificativa na documentação técnico-científica e nos comentários do próprio arquivo | Os parâmetros ficam gravados dentro do hash: `m=65536,t=3,p=2` |
| 1.3 | Uso de salt criptográfico único por usuário | Atendido | Gerado automaticamente pelo Argon2 a cada chamada de `set_password` | Criar duas contas com a mesma senha e comparar os hashes: são diferentes |
| 1.4 | Armazenamento correto do hash + salt | Atendido | Campo `password` do modelo `User`, no formato PHC | A string `argon2$argon2id$v=19$m=65536,t=3,p=2$SALT$HASH` guarda algoritmo, parâmetros, salt e hash no mesmo campo |
| 1.5 | Autenticação de dois fatores (2FA) implementada | Atendido | `otp_setup` em `apps/accounts/views.py`, com `django-otp` e TOTP (RFC 6238) | Entrar em `/conta/perfil/`, ativar a verificação em duas etapas e ler o QR Code com o aplicativo autenticador |
| 1.6 | Validação do 2FA após autenticação primária | Atendido | `TwoFactorLoginView` em `apps/accounts/views.py`: a função `login()` do Django só é chamada depois que o código é validado | Fazer login com a senha correta em uma conta com 2FA: a aplicação para na tela do código, sem criar sessão |
| 1.7 | Fluxo de autenticação documentado | Atendido | Documentação técnico-científica, seção do fluxo de autenticação. Os comentários de `apps/accounts/views.py` descrevem cada etapa no próprio código | — |
| 1.8 | Evidências funcionais (prints, logs ou testes) | Atendido | 17 testes automatizados em `apps/accounts/tests.py` e capturas de tela em [evidencias.md](evidencias.md) | `python manage.py test apps.accounts` |
| 1.9 | Sessões com tempo de expiração | Atendido | `SESSION_COOKIE_AGE = 900` com `SESSION_SAVE_EVERY_REQUEST`, em `config/settings.py` | Ficar 15 minutos sem interagir e recarregar a página: a aplicação pede login de novo |
| 1.10 | Invalidação de sessão no logout | Atendido | `SecureLogoutView` em `apps/accounts/views.py`, que remove o registro da sessão do banco | Sair da conta e tentar voltar em `/conta/perfil/` pelo histórico do navegador |
| 1.11 | Proteção contra força bruta (rate limit, bloqueio, atraso) | Atendido | `django-axes`, com bloqueio de 5 minutos após 5 falhas, aplicado à combinação de conta e endereço de rede | Errar a senha 5 vezes na tela de login: a sexta tentativa mostra a tela de bloqueio |
| 1.12 | Justificativas técnicas documentadas | Atendido | Documentação técnico-científica e comentários em `config/settings.py` e `apps/accounts/hashers.py` | — |

## Blocos seguintes

Os itens abaixo não fazem parte desta entrega e estão registrados no quadro
de atividades do projeto.

| Bloco | Situação |
|---|---|
| 2. Recuperação de senha | Não iniciado |
| 3. Criptografia e comunicação segura | Parcial: HTTPS, HSTS e conexão TLS com o banco já implementados |
| 4. Conformidade com a LGPD | Parcial: coleta mínima e aceite obrigatório da política no cadastro |
| 5. Auditoria e logs | Não iniciado |
| 6. Documentação técnico-científica | Em andamento |
| 7. Resumo científico | Em andamento |
| 8. Pôster científico e apresentação | Não iniciado |
