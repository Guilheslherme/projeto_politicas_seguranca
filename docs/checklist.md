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
| 1.8 | Evidências funcionais (prints, logs ou testes) | Atendido | 17 testes automatizados deste bloco em `apps/accounts/tests.py`, dos 54 do arquivo, e capturas de tela em [evidencias.md](evidencias.md) | `python manage.py test apps.accounts` |
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

**Vínculo do log com a conta.** O log usa `on_delete=SET_NULL`: apagar a pessoa
não apaga a trilha do que aconteceu. Na exclusão pedida pelo titular (requisito
4.10), o IP e o navegador desses eventos também são apagados, e sobra só o tipo
de evento e a data.

## 3. Criptografia e Comunicação Segura

| Nº | Requisito | Situação | Implementação | Como demonstrar no front-end |
|---|---|---|---|---|
| 3.1 | Comunicação protegida por TLS/HTTPS | Atendido | Certificado TLS do Render, com TLS 1.3 negociado. Com `DEBUG` desligado, o Django ativa `SECURE_SSL_REDIRECT`, cookies `Secure` e HSTS de um ano, em `config/settings.py`. A conexão com o banco no Aiven também usa TLS 1.3, verificado a partir do ambiente local | Acessar https://projeto-politicas-seguranca.onrender.com e abrir os detalhes do cadeado, ou a aba Security do DevTools, que mostra a versão do TLS e o certificado |
| 3.2 | Bloqueio de conexões não seguras | Atendido | Três camadas: a borda do Render responde HTTP com 301 para HTTPS; o Django repete o redirecionamento se a requisição chegar em HTTP; o cabeçalho HSTS faz o navegador recusar HTTP por conta própria nas visitas seguintes. O servidor recusa TLS 1.1 | Digitar `http://projeto-politicas-seguranca.onrender.com` na barra de endereço: o navegador termina em `https://` |
| 3.3 | Evidência de tráfego cifrado | Atendido | Saídas reais de `curl` e `openssl s_client` contra o site publicado, e consulta ao status TLS da conexão com o MySQL, registradas em [evidencias.md](evidencias.md) | Aba Security do DevTools. Os comandos de terminal estão em [evidencias.md](evidencias.md) |
| 3.4 | Dados sensíveis criptografados em repouso | Atendido | `EncryptedTOTPDevice` em `apps/accounts/models.py` cifra o segredo do 2FA, o dado mais perigoso do banco, antes de gravá-lo. A migração `0004_cifra_segredos_2fa_existentes` cifrou os segredos já existentes. Senhas e tokens de recuperação já eram guardados só como hash (blocos 1 e 2). O sistema não coleta dado sensível no sentido da LGPD, ver bloco 4 | Com uma conta de equipe, ativar o 2FA e abrir o perfil: o card "Dados técnicos" mostra "Segredo do 2FA no banco: aes256gcm (cifrado)" |
| 3.5 | Uso de algoritmo criptográfico adequado (ex.: AES) | Atendido | AES-256-GCM, pela biblioteca `cryptography`, em `apps/accounts/crypto.py`: chave de 256 bits, nonce aleatório de 96 bits a cada cifragem e autenticação do texto cifrado | O mesmo card mostra o algoritmo. Os 9 testes de `CriptografiaEmRepousoTests` provam cifragem, integridade e vínculo com a conta |
| 3.6 | Chaves criptográficas protegidas | Atendido | `FIELD_ENCRYPTION_KEY` e `DJANGO_SECRET_KEY` vêm só de variáveis de ambiente: `.env` local, que está no `.gitignore`, e painel do Render. Sem chave válida a aplicação não inicia. Os testes sorteiam uma chave a cada execução, então nenhuma chave fica escrita no repositório | Consultar o `.gitignore` e o `.env.example`, que traz apenas os nomes das variáveis e o comando para gerar a chave |
| 3.7 | Estratégia de criptografia documentada | Atendido | Seção "Estratégia de criptografia" abaixo | — |
| 3.8 | Justificativa técnica das escolhas | Atendido | Seção "Estratégia de criptografia" abaixo, com as referências normativas | — |

### Estratégia de criptografia

O sistema protege os dados em dois estados, com mecanismos diferentes para
cada um.

**Em trânsito: TLS 1.3, com TLS 1.2 como mínimo.** Todo o tráfego entre o
navegador e o servidor, e entre o servidor e o banco de dados, passa por TLS. A
verificação com `openssl s_client` mostrou TLS 1.3 com o conjunto
`TLS_AES_256_GCM_SHA384`, TLS 1.2 ainda aceito e TLS 1.1 recusado pelo servidor.
A conexão com o MySQL, consultada a partir do ambiente local, também usa TLS 1.3. A escolha segue a NIST SP 800-52 Rev. 2, que exige
suporte a TLS 1.2 e recomenda TLS 1.3, e a RFC 8996, que declarou o TLS 1.0 e o
1.1 obsoletos. O TLS 1.3 (RFC 8446) elimina os algoritmos de troca de chaves sem
sigilo futuro (*forward secrecy*): cada sessão usa chaves efêmeras, e a
obtenção da chave privada do servidor no futuro não permite decifrar tráfego
gravado no passado. Manter o TLS 1.2 preserva compatibilidade com navegadores
antigos sem abrir mão de cifradores autenticados.

Garantir que o canal existe não basta: é preciso impedir que ele seja
contornado. O HSTS (RFC 6797), enviado com `max-age` de um ano, faz o navegador
converter qualquer acesso futuro em HTTPS antes de enviar a requisição, o que
fecha a janela do ataque de rebaixamento em que um intermediário intercepta o
primeiro acesso em HTTP. Os cookies de sessão e de CSRF saem com o atributo
`Secure` e nunca trafegam fora do TLS.

**Em repouso: AES-256-GCM.** O dado cifrado é o segredo da verificação em duas
etapas. Senhas e tokens de recuperação não precisam de cifragem porque nem
chegam a ser guardados: o banco tem apenas o hash deles, que não pode ser
revertido. O segredo do 2FA é diferente, porque o sistema precisa do valor
original para conferir cada código, e por isso ele não pode virar hash. Sem
proteção, um vazamento da tabela — por backup exposto, injeção de SQL ou acesso
indevido ao Aiven — permitiria gerar os códigos de todas as contas e anularia a
segunda etapa do login.

O AES (FIPS 197) é o cifrador simétrico padronizado pelo NIST. A chave de 256
bits dá margem inclusive contra o algoritmo de Grover, que em um computador
quântico reduziria a segurança efetiva à metade dos bits. O modo GCM (NIST SP
800-38D) foi escolhido por ser cifragem autenticada: além de esconder o
conteúdo, ele detecta qualquer alteração no texto cifrado e recusa o valor
inteiro. Modos sem autenticação, como o CBC puro, decifram um valor adulterado
e devolvem lixo sem aviso, o que abre espaço para ataques de *padding oracle*.

Três decisões de implementação completam a escolha:

1. **Nonce aleatório de 96 bits a cada cifragem**, o tamanho recomendado pela
   SP 800-38D. Repetir o nonce com a mesma chave anula a segurança do GCM, então
   ele é sorteado pelo gerador criptográfico do sistema operacional e gravado
   junto do texto cifrado.
2. **Contexto de autenticação ligado à conta.** O identificador do usuário
   entra como dado associado (AAD) do GCM. Um segredo cifrado copiado para a
   linha de outra conta não decifra, o que impede transferir o 2FA de alguém
   alterando o banco.
3. **Prefixo `aes256gcm$` no valor gravado**, como o `argon2$` do hash da senha.
   Ele identifica o algoritmo e permite trocá-lo no futuro sem ambiguidade.

**Por que não Fernet.** O Fernet, sugestão comum para Django, usa AES-128 em
modo CBC com HMAC-SHA256, e não AES-256. É uma construção segura, mas o
resultado tem 120 caracteres para um segredo de 20 bytes e não caberia no campo
de 80 caracteres do django-otp. O AES-256-GCM entrega chave maior, autenticação
nativa e 74 caracteres.

**Proteção da chave.** A chave nunca fica no código: vem de variável de
ambiente, o `.env` está no `.gitignore` e, no Render, a variável fica no painel do
serviço, fora do repositório. A aplicação se recusa a iniciar sem uma chave de 32 bytes válida, porque
as alternativas — gravar em texto puro ou deixar o 2FA quebrado — falhariam em
silêncio. O mesmo vale para a `DJANGO_SECRET_KEY`, que antes caía em um valor
fixo escrito no código quando a variável faltava. O painel administrativo passou
a esconder o segredo e o QR Code dos dispositivos (`OTP_ADMIN_HIDE_SENSITIVE_DATA`),
porque nem a equipe precisa vê-los.

Essa separação atende ao Art. 46 da LGPD, que exige medidas técnicas aptas a
proteger os dados de acessos não autorizados, e ao princípio da segurança do
Art. 6º, VII.

**Limitações conhecidas.** A chave é única e não há rotação automática: trocá-la
exige decifrar com a antiga e cifrar com a nova. O ambiente local e o Render
usam o mesmo banco, então precisam da mesma chave. O TLS com o banco foi
verificado a partir do ambiente local; no Render, a validação do certificado do
Aiven depende de a variável `DB_SSL_CA` apontar para o arquivo da autoridade
certificadora, que não vai para o repositório.

**Referências.**

- IETF. *RFC 8446: The Transport Layer Security (TLS) Protocol Version 1.3*. 2018.
- IETF. *RFC 8996: Deprecating TLS 1.0 and TLS 1.1*. 2021.
- IETF. *RFC 6797: HTTP Strict Transport Security (HSTS)*. 2012.
- NIST. *SP 800-52 Rev. 2: Guidelines for the Selection, Configuration, and Use of Transport Layer Security (TLS) Implementations*. 2019.
- NIST. *FIPS 197: Advanced Encryption Standard (AES)*. 2001, atualizado em 2023.
- NIST. *SP 800-38D: Recommendation for Block Cipher Modes of Operation: The Galois/Counter Mode (GCM)*. 2007.
- OWASP. *Cryptographic Storage Cheat Sheet*.
- BRASIL. *Lei nº 13.709, de 14 de agosto de 2018* (LGPD), arts. 6º e 46.

## 4. Conformidade com a LGPD

| Nº | Requisito | Situação | Implementação | Como demonstrar no front-end |
|---|---|---|---|---|
| 4.1 | Listagem completa dos dados pessoais coletados | Atendido | Dicionário de dados abaixo, incluindo as tabelas de bibliotecas de terceiros. A versão para o titular está em `/privacidade/politica/` | Abrir a Política de Privacidade pelo rodapé de qualquer página |
| 4.2 | Associação de cada dado a uma finalidade | Atendido | Colunas "Finalidade" e "Base legal" do dicionário e da tabela da política | Mesma página |
| 4.3 | Evidência de minimização de dados | Atendido | Nenhum dado sensível coletado. O cadastro pede só nome, e-mail e senha. O teste `test_modelo_de_usuario_so_tem_os_campos_necessarios` falha se alguém acrescentar um campo à conta, e `test_cadastro_pede_apenas_nome_email_e_senha` faz o mesmo com o formulário | Abrir `/conta/register/`: apenas três dados e o aceite |
| 4.4 | Registro explícito de consentimento | Atendido | `ConsentRecord` em `apps/privacy/models.py`. O cadastro grava conta e aceite na mesma transação, com caixa obrigatória e desmarcada por padrão. `ConsentRequiredMiddleware` leva contas sem aceite vigente à tela de consentimento | Criar uma conta e abrir `/privacidade/meus-dados/`: o aceite aparece na tabela "Consentimentos". Com conta de equipe, também em "Registros de consentimento" no painel |
| 4.5 | Consentimento associado à finalidade | Atendido | Campo `purpose` do registro, com a finalidade "Criação e manutenção da conta". A tabela da política liga cada dado à finalidade e à base legal | A coluna "Finalidade" da tabela de consentimentos em "Meus dados" |
| 4.6 | Possibilidade de revogação do consentimento | Atendido | `delete_account` em `apps/privacy/views.py`: revoga o consentimento, preenchendo `revoked_at`, e exclui a conta na mesma transação, com confirmação da senha | Em "Meus dados", clicar em "Revogar consentimento e excluir conta" |
| 4.7 | Registro de data e versão do consentimento | Atendido | Campos `granted_at`, gravado automaticamente, e `policy_version`, com o valor de `PRIVACY_POLICY_VERSION`. Mudar a versão faz toda conta aceitar o texto novo, e o aceite antigo continua no histórico | Tabela "Consentimentos" em "Meus dados", com versão e data |
| 4.8 | Funcionalidade de consulta aos dados do titular | Atendido | `my_data` em `apps/privacy/views.py`, sobre `reunir_dados_do_titular` em `apps/privacy/rights.py`: conta, credenciais, consentimentos e registros de segurança | Perfil → "Privacidade e meus dados" |
| 4.9 | Funcionalidade de exportação dos dados | Atendido | `export_data`: arquivo JSON com exatamente os dados da consulta, sem hash de senha nem segredo do 2FA | Botão "Exportar em JSON" em "Meus dados" |
| 4.10 | Funcionalidade de exclusão dos dados pessoais | Atendido | `excluir_conta` em `apps/privacy/rights.py`: apaga conta, credenciais, tokens e registros do django-axes, e anonimiza a trilha de recuperação de senha | "Revogar consentimento e excluir conta", confirmar com a senha e tentar entrar de novo com o mesmo e-mail |
| 4.11 | Fluxo de atendimento aos direitos documentado | Atendido | Seção "Fluxo de atendimento aos direitos do titular" abaixo | — |

### Dicionário de dados

Nenhum dado pessoal sensível (Art. 5º, II) é coletado. O Health In Sight não
guarda condição de saúde, sintoma, histórico, exame nem interesse por doença, e
o acervo é igual para todo mundo. A decisão está descrita no README e é a
principal medida de minimização do projeto: não existe vazamento possível de
dado de saúde, porque não existe dado de saúde guardado.

| Dado | Onde fica | Categoria | Finalidade | Base legal | Minimização |
|---|---|---|---|---|---|
| Nome completo | `accounts_user.full_name` | Comum | Identificar a pessoa na conta e na saudação do e-mail de recuperação | Consentimento (Art. 7º, I) | Um campo só. Não se pede sobrenome separado, apelido nem nome social |
| E-mail | `accounts_user.email` | Comum | Login e envio do link de recuperação de senha | Consentimento (Art. 7º, I) | Substitui o nome de usuário: um único dado cumpre as duas funções |
| Hash da senha | `accounts_user.password` | Comum (credencial) | Autenticação | Consentimento (Art. 7º, I) | A senha não é guardada, só o hash Argon2id |
| Segredo do 2FA | `otp_totp_totpdevice.key` | Comum (credencial) | Segunda etapa do login | Consentimento (Art. 7º, I) | Opcional, cifrado com AES-256-GCM e apagado ao desativar o 2FA |
| Datas de cadastro, último login e última troca de senha | `accounts_user` | Comum | Controle e segurança da conta | Consentimento (Art. 7º, I) | Geradas pelo sistema, nada é pedido à pessoa |
| Registro de consentimento | `privacy_consentrecord` | Comum | Provar o aceite (Art. 8º, §2º) | Exercício regular de direitos (Art. 7º, VI) | Sem IP e sem navegador: só finalidade, versão e datas |
| Acessos bem-sucedidos: e-mail, IP, navegador, entrada e saída | `axes_accesslog` | Comum | Detectar uso indevido da conta | Legítimo interesse (Art. 7º, IX) | Apagados na exclusão da conta |
| Tentativas de login malsucedidas: e-mail digitado, IP, navegador e contagem | `axes_accessattempt` | Comum | Bloqueio por força bruta (requisito 1.11) | Legítimo interesse (Art. 7º, IX) | Senha e e-mail mascarados nos dados do formulário. Apagadas na exclusão |
| Trilha de recuperação de senha: evento, IP, navegador e vínculo com a conta | `audit_passwordresetlog` | Comum | Auditoria do processo (requisitos 2.6 e 2.7) | Legítimo interesse (Art. 7º, IX) | Sem e-mail, token ou senha. Anonimizada na exclusão |
| Token de recuperação: hash, IP da solicitação e datas | `accounts_passwordresettoken` | Comum | Troca de senha sem a senha antiga | Consentimento (Art. 7º, I) | Só o SHA-256 do token. Apagado junto com a conta |
| Sessão: identificador da conta e marcação temporária do 2FA | `django_session` | Comum | Manter a pessoa conectada | Consentimento (Art. 7º, I) | Expira após 15 minutos sem uso |

**Por que só há uma finalidade consentida.** O consentimento cobre apenas o que
de fato depende dele: a conta. Os registros de segurança se apoiam no legítimo
interesse na prevenção a fraudes, e oferecer a revogação de algo que continuaria
acontecendo seria enganoso. Pedir consentimento para finalidades que o sistema
não executa, só para a lista parecer mais completa, também contrariaria o Art.
8º, §4º, que torna nulas as autorizações genéricas.

**Por que revogar e excluir são o mesmo ato.** Como a conta é o único tratamento
baseado em consentimento, a revogação encerra a base legal para manter os dados.
A LGPD determina a eliminação ao término do tratamento (Arts. 15, III, e 16),
então a revogação dispara a exclusão na mesma transação, em vez de deixar dados
guardados sem base legal esperando uma segunda ação.

**Por que a trilha de recuperação é anonimizada, e não apagada.** O Art. 16, IV,
permite conservar dados para uso exclusivo do controlador desde que
anonimizados. A trilha perde o IP, o navegador e o vínculo com a conta, mas
mantém o tipo de evento e a data. Assim, a análise de padrões de ataque do bloco
5 continua possível sem que nada aponte para a pessoa excluída. Isso encerra o
ponto que ficou em aberto no bloco 2.

**Por que a exportação não inclui credenciais.** O arquivo baixado fica fora das
proteções do sistema. O hash da senha permitiria tentar descobri-la por força
bruta fora do servidor, e o segredo do 2FA permitiria gerar os códigos de
acesso. A exportação informa que os dois existem e como são guardados, sem os
valores.

### Fluxo de atendimento aos direitos do titular

Todas as telas exigem login. Quem tem 2FA ativo já passou pelas duas etapas
antes de chegar a elas.

**Aceite, no cadastro ou em uma versão nova da política (Art. 8º)**

1. No cadastro, a pessoa marca a caixa, que vem desmarcada, com link para a
   política. Sem a marcação o formulário é recusado e nada é gravado.
2. `register_view` cria a conta e o `ConsentRecord` na mesma transação, com
   finalidade, versão vigente e data. Se a gravação do aceite falhar, a conta
   também não é criada.
3. A cada requisição, `ConsentRequiredMiddleware` confere se a conta logada tem
   aceite da versão vigente e não revogado. Se não tiver — conta antiga, ou
   política alterada —, leva a pessoa a `/privacidade/consentimento/`, que só
   deixa passar depois de um novo aceite. A política, a saída e a exclusão
   continuam acessíveis, para que recusar não prenda ninguém no sistema.

**Consulta (Art. 18, I e II)**

1. Perfil → "Privacidade e meus dados" → `/privacidade/meus-dados/`.
2. `reunir_dados_do_titular` lê a conta, o estado do 2FA, os consentimentos, os
   acessos e tentativas do django-axes, comparando o e-mail sem diferenciar
   maiúsculas, e a trilha de recuperação de senha.
3. A página mostra tudo agrupado. Hash da senha e segredo do 2FA aparecem apenas
   descritos, nunca com os valores.

**Exportação (Art. 18, V)**

1. Botão "Exportar em JSON" em "Meus dados", enviado por POST com token de CSRF.
2. A view chama a mesma `reunir_dados_do_titular` da consulta, o que garante
   conteúdo idêntico ao da tela.
3. A resposta sai como `application/json`, com `Content-Disposition: attachment`
   e `Cache-Control: no-store`, para que nenhum cache intermediário guarde uma
   cópia.

**Revogação do consentimento e exclusão (Art. 18, VI e IX)**

1. "Revogar consentimento e excluir conta" → `/privacidade/excluir-conta/`, que
   lista o que será apagado e o que será anonimizado e oferece exportar antes.
2. A pessoa confirma com a senha atual. Senha errada não altera nada.
3. `excluir_conta` executa, em uma única transação:
   1. preenche `revoked_at` nos consentimentos vigentes;
   2. apaga IP e navegador da trilha de recuperação de senha da conta;
   3. apaga os registros do django-axes ligados ao e-mail;
   4. apaga a conta. Em cascata saem o dispositivo 2FA e os tokens de
      recuperação; a trilha de recuperação e os consentimentos ficam com o
      vínculo nulo.
4. Só depois da exclusão confirmada a sessão é encerrada. Se algo falhar, a
   transação é desfeita e a pessoa continua logada para tentar de novo.
5. Sessões abertas em outros aparelhos deixam de valer, porque o Django confere
   a sessão contra a conta, que não existe mais.

**Referências.**

- BRASIL. *Lei nº 13.709, de 14 de agosto de 2018* (LGPD), arts. 5º, 6º, 7º, 8º, 9º, 11, 15, 16, 18 e 46.

## Blocos seguintes

Os itens abaixo não fazem parte desta entrega e estão registrados no quadro
de atividades do projeto.

| Bloco | Situação |
|---|---|
| 5. Auditoria e logs | Parcial: trilha do bloco 2 gravada em `apps/audit`, somente leitura no painel |
| 6. Documentação técnico-científica | Em andamento |
| 7. Resumo científico | Em andamento |
| 8. Pôster científico e apresentação | Não iniciado |
