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
| 1.8 | Evidências funcionais (prints, logs ou testes) | Atendido | 17 testes automatizados deste bloco em `apps/accounts/tests.py`, dos 36 do arquivo, e capturas de tela em [evidencias.md](evidencias.md) | `python manage.py test apps.accounts` |
| 1.9 | Sessões com tempo de expiração | Atendido | `SESSION_COOKIE_AGE = 900` com `SESSION_SAVE_EVERY_REQUEST`, em `config/settings.py` | Ficar 15 minutos sem interagir e recarregar a página: a aplicação pede login de novo |
| 1.10 | Invalidação de sessão no logout | Atendido | `SecureLogoutView` em `apps/accounts/views.py`, que remove o registro da sessão do banco | Sair da conta e tentar voltar em `/conta/perfil/` pelo histórico do navegador |
| 1.11 | Proteção contra força bruta (rate limit, bloqueio, atraso) | Atendido | `django-axes`, com bloqueio de 5 minutos após 5 falhas, aplicado à combinação de conta e endereço de rede | Errar a senha 5 vezes na tela de login: a sexta tentativa mostra a tela de bloqueio |
| 1.12 | Justificativas técnicas documentadas | Atendido | Documentação técnico-científica e comentários em `config/settings.py` e `apps/accounts/hashers.py` | — |

## 2. Recuperação de Senha

| Nº | Requisito | Situação | Implementação | Como demonstrar no front-end |
|---|---|---|---|---|
| 2.1 | Funcionalidade de recuperação de senha implementada | Atendido | `password_reset_request` e `password_reset_confirm` em `apps/accounts/views.py`, com envio pela API HTTP do Brevo em `apps/accounts/emails.py`. A senha nova passa pelos mesmos `AUTH_PASSWORD_VALIDATORS` e pelo mesmo hasher Argon2id do cadastro | Clicar em "Esqueci minha senha" na tela de entrada, informar o e-mail da conta, abrir o link recebido e definir a senha nova |
| 2.2 | Token criptograficamente seguro | Atendido | `PasswordResetToken.emitir` em `apps/accounts/models.py`: `secrets.token_urlsafe(32)`, 256 bits sorteados pelo gerador criptográfico do sistema operacional. No banco fica apenas o SHA-256 do token, nunca o valor do link | Consultar a coluna `token_hash` da tabela `accounts_passwordresettoken` e comparar com o token que aparece na URL do e-mail: são valores diferentes |
| 2.3 | Token com tempo de expiração | Atendido | Campo `expires_at`, preenchido na emissão com `PASSWORD_RESET_TOKEN_TIMEOUT` (30 minutos), definido em `config/settings.py`. O prazo é gravado no próprio registro, então mudar a configuração depois não estende links já enviados | Comparar as colunas `created_at` e `expires_at` do token: a diferença é de 30 minutos |
| 2.4 | Token invalidado após uso | Atendido | `PasswordResetToken.marcar_como_usado`, chamado logo após a gravação da senha. Preenche `used_at` e cancela os demais tokens pendentes da conta. Pedir um link novo também cancela os anteriores, gravando `invalidated_at` | Abrir duas vezes o mesmo link: na segunda vez aparece a tela "Link não utilizável", com a explicação de que o link serve uma vez só |
| 2.5 | Falha correta para token expirado | Atendido | `PasswordResetToken.resolver` classifica o token em válido, inexistente, expirado ou já usado, e a view devolve HTTP 400 com `accounts/password_reset_invalid.html`. O formulário de senha nova não é renderizado em nenhum dos casos de falha | Esperar os 30 minutos, ou adiantar o vencimento no banco, e abrir o link: a tela explica que expirou e oferece pedir um link novo |
| 2.6 | Registro de solicitação de recuperação em log | Atendido | `PasswordResetLog` em `apps/audit/models.py`, evento `SOLICITADO`, com data e hora, identificador da conta, IP e navegador. O e-mail não é gravado. Toda solicitação é registrada, inclusive as de endereços sem conta, que entram com usuário nulo, e as recusadas pelo limite de pedidos | Entrar no painel administrativo, em "Registros de recuperação de senha", e consultar a lista |
| 2.7 | Registro de sucesso/falha do processo | Atendido | O mesmo modelo registra o desfecho de cada etapa: `EMAIL_ENVIADO`, `EMAIL_FALHOU`, `LIMITE_EXCEDIDO`, `TOKEN_INVALIDO`, `TOKEN_EXPIRADO`, `TOKEN_JA_USADO` e `SENHA_REDEFINIDA`. Os mesmos eventos saem na saída padrão do servidor, que é onde o Render coleta os logs | Filtrar a lista pela coluna "evento" no painel administrativo, ou acompanhar a saída do servidor durante um teste |

### Decisões técnicas do bloco 2

**Por que SHA-256 no token e Argon2id na senha.** São problemas diferentes. Uma
senha escolhida por uma pessoa tem pouca entropia, e o Argon2id compensa isso
tornando cada tentativa cara. O token já nasce com 256 bits aleatórios, e
adivinhá-lo é inviável independentemente da velocidade do ataque — o custo alto
do Argon2 só atrasaria cada clique no link, sem ganho de segurança. O SHA-256
resolve o que importa aqui: quem lesse a tabela não consegue voltar ao token e
montar um link válido.

**Por que 30 minutos.** Tempo suficiente para a mensagem chegar mesmo com a
lentidão do plano gratuito do Render, e curto o bastante para limitar a janela
em que um link vazado — histórico do navegador, e-mail encaminhado, caixa de
entrada compartilhada — ainda serviria para alguém.

**Por que a resposta é sempre igual.** A tela de confirmação diz "se houver uma
conta com o endereço informado" e é a mesma para qualquer e-mail digitado,
inclusive quando o envio falha. Responder de forma diferente para um endereço
cadastrado transformaria o formulário em um verificador de quem tem conta no
sistema. É o mesmo motivo da mensagem genérica "E-mail ou senha incorretos" na
tela de entrada. No log a diferença aparece apenas como um registro sem conta
associada, e não como um campo próprio.

**Por que um limite de pedidos.** Sem ele, o formulário seria um disparador
aberto de mensagens: qualquer pessoa poderia usá-lo para inundar a caixa de
entrada de outra, à custa da cota de envio do projeto. São 3 pedidos por
conta a cada 15 minutos, contados na própria trilha de auditoria.

**Por que o log fica no banco.** O Render apaga o disco a cada implantação, e um
log que some junto com o servidor não serve de trilha de auditoria. O registro
usa `auto_now_add`, que não aceita data vinda de fora, e o painel administrativo
o expõe apenas para leitura, sem botão de criar, salvar ou excluir.

**Por que urllib e não requests.** O envio é uma única requisição HTTP. Usar a
biblioteca padrão evita mais uma dependência para instalar a cada build do
Render. A chave da API vai no cabeçalho `api-key`, nunca na URL, porque
endereços aparecem em log de servidor e histórico de proxy.

**Efeitos colaterais da troca de senha.** Trocar a senha muda o hash de sessão do
Django, então toda sessão aberta daquela conta deixa de valer, inclusive a de
quem tivesse entrado com a senha antiga. O bloqueio do django-axes também é
liberado, porque quem esqueceu a senha costuma ter errado várias vezes antes de
pedir o link e ficaria travado logo após redefini-la; liberar é seguro, já que
só chega a esse ponto quem provou ter acesso à caixa de entrada da conta.

**O que a trilha de auditoria não registra.** A primeira versão do log gravava o
endereço de e-mail em texto puro e um campo booleano `conta_existe`. Os dois
saíram.

O endereço é dado pessoal, e registrá-lo contraria a minimização exigida pela
LGPD. O peso está em quanto o log dura e quantas pessoas o leem: uma trilha de
auditoria é guardada por mais tempo e consultada por mais gente que a tabela de
usuários, então repetir o endereço nela multiplicava a exposição do dado sem
responder nenhuma pergunta nova. O identificador interno responde tudo que a
auditoria precisa — quais eventos são da mesma conta, em que ordem, a partir de
qual IP — e só vira um endereço para quem já tem acesso à tabela de usuários.

O campo `conta_existe` era pior que o e-mail. A resposta HTTP do fluxo é
deliberadamente idêntica para conta existente e inexistente, para que o
formulário não sirva de verificador de quem tem cadastro. O campo reproduzia no
log exatamente a informação que a resposta foi desenhada para esconder, e num
lugar de proteção mais fraca: quem obtivesse o log enumeraria usuários sem
precisar tocar na aplicação. Um controle que existe na interface e é anulado no
armazenamento não é um controle. A informação não se perdeu — um evento com
usuário nulo é, por construção, um pedido para endereço sem conta — apenas
deixou de ser uma coluna pronta para filtrar. Ação, resultado, IP, navegador e
data/hora continuam registrados como antes.

**Consequência: o limite de pedidos passou a ser por conta.** A contagem era
feita pelo endereço digitado, lido da própria trilha. Sem o e-mail no log, passou
a ser por conta. Isso deixa pedidos para endereços sem conta fora do limite, e
está correto: nenhuma mensagem é enviada nesse caso, então não existe caixa de
entrada para inundar. O abuso que o limite previne depende de uma conta real e
continua coberto.

**O que nunca pode entrar no log.** Token, senha e corpo ou destinatário da
mensagem enviada. O token dentro do prazo é a credencial completa, e registrá-lo
daria a quem lê o log exatamente o que falta para trocar a senha de outra pessoa;
a senha não fica em texto puro em lugar nenhum, pelo mesmo motivo que só existe
como hash Argon2id no banco; o corpo da mensagem é o e-mail voltando pela porta
dos fundos. Três pontos precisaram de correção específica:

1. A exceção `FalhaNoEnvio` carregava os primeiros 200 caracteres do corpo da
   resposta do Brevo, e essa mensagem ia para o campo `detail` do log. O Brevo
   repete o endereço do destinatário nas respostas de recusa, então o e-mail
   voltava por esse caminho. Hoje a exceção carrega apenas o código HTTP. O
   motivo detalhado de cada recusa fica no painel do próprio Brevo.
2. Sem `BREVO_API_KEY`, o link era impresso na saída do servidor junto com o
   destinatário — e o link contém o token. Hoje isso só ocorre com `DEBUG`
   ligado e imprime apenas o link; com `DEBUG` desligado, a ausência da chave
   levanta `FalhaNoEnvio` como qualquer outra falha de envio.
3. `PasswordResetLog.registrar` recebe `user`, e não e-mail. Nenhuma chamada
   consegue gravar um endereço por descuido, porque não há parâmetro por onde
   passá-lo.

O teste `test_log_nao_guarda_email_token_nem_senha` percorre o fluxo inteiro,
inclusive os caminhos de falha, e varre todos os campos de todos os registros
procurando o e-mail, o token, a senha antiga e a nova.

**Texto didático fora da interface.** A tela "Verifique seu e-mail" trazia um
parágrafo explicando que a resposta é sempre igual de propósito, para não
permitir descobrir quem tem conta. Foi removido: é conteúdo de documentação, e
documentação na interface de produção confunde quem só quer a senha de volta e
anuncia a existência do controle para quem procura brecha. Uma defesa não
precisa se apresentar para funcionar. A explicação continua em
[evidencias.md](evidencias.md), na seção "Por que a resposta é sempre a mesma",
que é onde a banca vai procurar. A tela ficou com a mensagem genérica, o aviso
sobre spam, o prazo exato e o caminho de volta. O prazo é lido de
`PASSWORD_RESET_TOKEN_TIMEOUT` e passado ao template: "30 minutos" fixado no
HTML seria uma segunda fonte da mesma informação, que passaria a mentir no dia
em que o prazo mudasse.

**Ponto em aberto para o bloco 4.** O vínculo do log com a conta usa
`on_delete=SET_NULL`: excluir um usuário apaga a ligação, mas preserva os
eventos, o IP e as datas. É a escolha certa para auditoria — apagar a pessoa não
pode apagar a trilha do que aconteceu — mas o requisito 4.10 vai precisar
decidir explicitamente se o IP desses eventos também sai, e com qual prazo de
retenção.

## Blocos seguintes

Os itens abaixo não fazem parte desta entrega e estão registrados no quadro
de atividades do projeto.

| Bloco | Situação |
|---|---|
| 3. Criptografia e comunicação segura | Parcial: HTTPS, HSTS e conexão TLS com o banco já implementados |
| 4. Conformidade com a LGPD | Parcial: coleta mínima e aceite obrigatório da política no cadastro |
| 5. Auditoria e logs | Parcial: trilha do bloco 2 gravada em `apps/audit`, somente leitura no painel |
| 6. Documentação técnico-científica | Em andamento |
| 7. Resumo científico | Em andamento |
| 8. Pôster científico e apresentação | Não iniciado |
