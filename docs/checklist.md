# Check-list do projeto

## 1. Autenticação e Gestão de Credenciais

| Nº | Requisito | Situação | Implementação | Como demonstrar no front-end |
|---|---|---|---|---|
| 1.1 | Uso de hash criptográfico seguro para senhas (Argon2, bcrypt ou PBKDF2) | Atendido | `apps/accounts/hashers.py` e `PASSWORD_HASHERS` no `config/settings.py` | Criar uma conta em `/conta/register/` e consultar a coluna `password` no banco: o valor começa com `argon2$argon2id$` |
| 1.2 | Parâmetros de custo do hash configurados e justificados | Atendido | `ProjectArgon2PasswordHasher`, com `memory_cost=65536`, `time_cost=3` e `parallelism=2`. Justificativa em [decisoes-tecnicas.md](decisoes-tecnicas.md) | Os parâmetros ficam gravados no próprio hash: `m=65536,t=3,p=2` |
| 1.3 | Uso de salt criptográfico único por usuário | Atendido | Gerado pelo Argon2 a cada chamada de `set_password` | Criar duas contas com a mesma senha e comparar os dois hashes: são diferentes |
| 1.4 | Armazenamento correto do hash + salt | Atendido | Campo `password` do modelo `User`, no formato PHC | A string `argon2$argon2id$v=19$m=65536,t=3,p=2$SALT$HASH` contém algoritmo, parâmetros, salt e hash |
| 1.5 | Autenticação de dois fatores (2FA) implementada | Atendido | `otp_setup` em `apps/accounts/views.py`, com `django-otp` e TOTP | Entrar em `/conta/perfil/`, ativar a verificação em duas etapas e ler o QR Code com o aplicativo autenticador |
| 1.6 | Validação do 2FA após autenticação primária | Atendido | `TwoFactorLoginView`: a função `login()` só é chamada após a validação do código | Fazer login com a senha correta em uma conta com 2FA: a aplicação para na tela do código, sem criar sessão |
| 1.7 | Fluxo de autenticação documentado | Atendido | [fluxo-de-autenticacao.md](fluxo-de-autenticacao.md) | — |
| 1.8 | Evidências funcionais (prints, logs ou testes) | Atendido | 17 testes automatizados em `apps/accounts/tests.py` e prints em [evidencias.md](evidencias.md) | `python manage.py test apps.accounts` |
| 1.9 | Sessões com tempo de expiração | Atendido | `SESSION_COOKIE_AGE = 900` com renovação a cada requisição | Ficar 15 minutos sem interagir e recarregar a página: a aplicação pede login de novo |
| 1.10 | Invalidação de sessão no logout | Atendido | `SecureLogoutView`, que remove o registro da sessão do banco | Sair da conta e tentar voltar em `/conta/perfil/` pelo histórico do navegador |
| 1.11 | Proteção contra força bruta (rate limit, bloqueio, atraso) | Atendido | `django-axes`, com bloqueio de 5 minutos após 5 falhas | Errar a senha 5 vezes na tela de login: a sexta tentativa mostra a tela de bloqueio |
| 1.12 | Justificativas técnicas documentadas | Atendido | [decisoes-tecnicas.md](decisoes-tecnicas.md) e comentários no `config/settings.py` | — |

## Blocos seguintes

Os itens abaixo não fazem parte desta entrega e estão registrados no quadro
de atividades do projeto.

| Bloco | Situação |
|---|---|
| 2. Recuperação de senha | Não iniciado |
| 3. Criptografia e comunicação segura | Parcial: HTTPS, HSTS e TLS no banco já implementados |
| 4. Conformidade com a LGPD | Parcial: coleta mínima e aceite obrigatório no cadastro |
| 5. Auditoria e logs | Não iniciado |
| 6. Documentação técnico-científica | Em andamento |
| 7. Resumo científico | Em andamento |
| 8. Pôster científico e apresentação | Não iniciado |