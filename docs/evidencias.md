# Evidências de funcionamento

Comprovação prática dos requisitos dos blocos 1 a 4, demonstrados pelo front-end da aplicação.

Aplicação publicada: https://projeto-politicas-seguranca.onrender.com

Check-list dos requisitos: [checklist.md](checklist.md)

---

## Telas da aplicação

Página inicial:

![Página inicial](img/01-home.jpg)

Criação de conta:

![Tela de cadastro](img/02-cadastro.jpg)

Entrada com e-mail e senha:

![Tela de login](img/03-login.jpg)

---

## 1.1, 1.3 e 1.4 — Hash Argon2id, salt único e armazenamento

Consulta à tabela de usuários no banco de dados.

**O que a imagem comprova:**

- o prefixo `argon2$argon2id$` mostra o algoritmo em uso (requisito 1.1)
- o trecho `m=65536,t=3,p=2` mostra os parâmetros de custo configurados (1.2)
- contas diferentes têm hashes completamente diferentes, porque o salt é gerado por senha (requisito 1.3)
- algoritmo, parâmetros, salt e hash ficam gravados no mesmo campo, no formato PHC (requisito 1.4)

![Hashes Argon2id no banco](img/08-hashes-argon2.jpg)

---

## Validação de senha no cadastro

Tentativa de cadastro com a senha `123456`.

**O que a imagem comprova:** a aplicação recusa apresentando três motivos ao mesmo tempo — senha curta demais, senha comum demais e senha inteiramente numérica. São os validadores configurados em `AUTH_PASSWORD_VALIDATORS`, incluindo o mínimo de 10 caracteres.

![Senha fraca recusada](img/12-senha-fraca.png)

---

## 1.5 — Verificação em duas etapas implementada

Tela de ativação, com o QR Code lido pelo aplicativo autenticador.

**O que a imagem comprova:** o segredo é gerado e apresentado em tela. O dispositivo nasce como não confirmado e só passa a valer depois que a pessoa digita um código válido, o que evita que alguém fique trancado fora da própria conta.

![Ativação da verificação em duas etapas](img/05-ativacao-2fa.jpg)

Perfil com a verificação ativa:

![Perfil com 2FA ativo](img/06-perfil-2fa-ativo.jpg)

Perfil com a verificação desativada:

![Perfil com 2FA desativado](img/07-perfil-2fa-desativado.jpg)

---

## 1.6 — Validação do 2FA após a autenticação primária

Este é o item central do bloco: **acertar a senha não cria sessão**.

Após informar e-mail e senha corretos em uma conta com verificação ativa, a aplicação para nesta tela.

**O que a imagem comprova:** a função `login()` do Django ainda não foi chamada neste momento. Não existe usuário autenticado, apenas uma marcação temporária de 5 minutos na sessão anônima. Quem tem a senha e não tem o celular não entra.

![Etapa 2 de 2 — código de verificação](img/04-codigo-2fa.jpg)

---

## 1.9 e 1.10 — Sessão com expiração e invalidação no logout

Configuração aplicada em `config/settings.py`:

```python
SESSION_COOKIE_AGE = 900            # 15 minutos
SESSION_SAVE_EVERY_REQUEST = True   # expiração deslizante
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
```

O prazo é de inatividade e se renova a cada requisição, então quem está navegando não é desconectado. No logout, o registro da sessão é removido do banco de dados, e não apenas o cookie do navegador — um cookie copiado antes do logout deixa de funcionar.

Comprovação automatizada em `apps/accounts/tests.py`, nos testes `test_sessao_expira_em_quinze_minutos` e `test_logout_apaga_a_sessao_do_banco`.

---

## 1.11 — Proteção contra força bruta

Tela apresentada na sexta tentativa, após cinco senhas incorretas.

**O que a imagem comprova:** o acesso é bloqueado por 5 minutos, com resposta HTTP 429. O bloqueio vale para a combinação de conta e endereço de rede, e não apenas para a conta — bloquear só pelo e-mail permitiria que qualquer pessoa travasse a conta de outra de propósito.

![Tela de bloqueio](img/11-bloqueio.png)

---

## 1.8 — Testes automatizados do bloco 1

```
python manage.py test apps.accounts
```

**O que a imagem comprova:** os 17 testes do bloco 1 passam. No meio da saída aparecem os registros do django-axes contabilizando as cinco falhas e aplicando o bloqueio, o que evidencia o requisito 1.11 em execução.

![Saída dos testes](img/09-testes.png)

| Grupo de testes | Quantidade | Requisitos cobertos |
|---|---|---|
| `ArmazenamentoDeSenhaTests` | 5 | 1.1, 1.2, 1.3, 1.4 |
| `DuasEtapasTests` | 4 | 1.5, 1.6 |
| `SessaoTests` | 3 | 1.9, 1.10 |
| `ForcaBrutaTests` | 2 | 1.11 |
| `CadastroTests` | 3 | 1.1 e consentimento |

---

## Comunicação protegida por TLS

Aplicação publicada, acessada pelo navegador.

**O que a imagem comprova:** conexão em HTTPS com certificado válido. O acesso por HTTP é redirecionado automaticamente e a aplicação envia o cabeçalho HSTS em produção.

![Conexão segura](img/10-https.png)

---

# Bloco 2 — Recuperação de senha

## 2.1 — Fluxo completo implementado

O caminho tem três telas: pedido do link, aviso de envio e definição da senha
nova. A entrada em `/conta/entrar/` ganhou o link **Esqueci minha senha**.

O e-mail sai pela API HTTP do Brevo, em `POST https://api.brevo.com/v3/smtp/email`,
com a chave em variável de ambiente. Sem `BREVO_API_KEY` configurada, o link é
impresso na saída do servidor em vez de enviado, o que permite percorrer o fluxo
inteiro na máquina local sem consumir a cota de envios.

A senha escolhida no fim passa pelo mesmo `SetPasswordForm` do Django, pelos
mesmos `AUTH_PASSWORD_VALIDATORS` do cadastro e pelo mesmo hasher Argon2id. Não
existe um caminho paralelo mais fraco para definir senha.

*Capturas a incluir: `img/13-esqueci-senha.png` (link na tela de entrada),
`img/14-pedido-recuperacao.png` (formulário do e-mail), `img/15-email-recebido.png`
(mensagem na caixa de entrada) e `img/16-nova-senha.png` (tela da senha nova).*

---

## 2.2 — Token criptograficamente seguro

O token é gerado por `secrets.token_urlsafe(32)`: 32 bytes, 256 bits, sorteados
pelo gerador criptográfico do sistema operacional, e não pelo `random` comum,
cuja sequência é previsível a partir de saídas anteriores.

O ponto central é o que **não** vai para o banco. A tabela guarda apenas o
SHA-256 do token:

```
token do link  →  SHA-256  →  token_hash gravado
```

Quem lesse a tabela `accounts_passwordresettoken` teria apenas o resumo, e não
há como voltar dele ao valor do link. A busca também é feita pelo hash, então o
token recebido nunca é comparado diretamente com nada armazenado.

Aqui o SHA-256 basta e o Argon2id seria contraproducente: o custo alto do Argon2
existe para proteger segredos fracos, como senhas escolhidas por pessoas. Um
valor de 256 bits aleatórios é inviável de adivinhar por tentativa e erro
independentemente da velocidade do ataque, e o custo só atrasaria cada clique no
link.

*Captura a incluir: `img/17-token-hash-banco.png`, mostrando a coluna
`token_hash` ao lado do token que aparece na URL do e-mail — valores diferentes.*

---

## 2.3, 2.4 e 2.5 — Prazo, uso único e recusa correta

Três campos sustentam as três regras:

| Campo | Papel |
|---|---|
| `expires_at` | Prazo de 30 minutos, gravado na emissão. Mudar a configuração depois não estende links já enviados |
| `used_at` | Preenchido quando o token é gasto para trocar a senha |
| `invalidated_at` | Preenchido quando o token deixa de valer sem ter sido usado, porque a pessoa pediu um link novo |

`PasswordResetToken.resolver` classifica o token em uma de quatro situações —
válido, inexistente, expirado ou já usado — e a view responde de acordo. Em
qualquer situação de falha a resposta é HTTP 400 com a tela
`accounts/password_reset_invalid.html`, que explica o motivo e oferece pedir um
link novo.

**O que prova o requisito 2.5:** a tela de erro não contém o formulário de senha
nova. Um link recusado não abre caminho para trocar coisa alguma, nem por GET
nem por POST. É o que o teste `test_token_expirado_nem_mostra_o_formulario`
verifica, conferindo que o campo `new_password1` não aparece na resposta.

*Captura a incluir: `img/18-link-expirado.png`, com a tela de link não
utilizável.*

---

## 2.6 e 2.7 — Registro em log

Cada etapa vira uma linha em `PasswordResetLog`, no aplicativo `apps/audit`, com
data e hora, identificador interno da conta, IP e navegador. O endereço de
e-mail não entra no log em momento nenhum. O IP é resolvido pelo mesmo helper do django-axes, então o log da
recuperação e o do bloqueio por força bruta falam do mesmo endereço mesmo atrás
do proxy do Render.

| Evento | Quando é gravado |
|---|---|
| `SOLICITADO` | Toda solicitação, inclusive de endereços sem conta (requisito 2.6) |
| `EMAIL_ENVIADO` | O Brevo aceitou a mensagem |
| `EMAIL_FALHOU` | O Brevo recusou ou não respondeu |
| `LIMITE_EXCEDIDO` | Acima de 3 pedidos para o mesmo endereço em 15 minutos |
| `TOKEN_INVALIDO` | Link inexistente ou cancelado por um pedido mais novo |
| `TOKEN_EXPIRADO` | Link fora do prazo |
| `TOKEN_JA_USADO` | Link apresentado uma segunda vez |
| `SENHA_REDEFINIDA` | Troca concluída |

Os mesmos eventos saem na saída padrão do servidor, que é onde o Render coleta
os logs. Trecho real de uma execução dos testes:

```
INFO apps.audit.models recuperacao de senha: SOLICITADO usuario_id=1 ip=127.0.0.1
INFO apps.audit.models recuperacao de senha: EMAIL_ENVIADO usuario_id=1 ip=127.0.0.1
INFO apps.audit.models recuperacao de senha: TOKEN_INVALIDO usuario_id=None ip=127.0.0.1
INFO apps.audit.models recuperacao de senha: SENHA_REDEFINIDA usuario_id=1 ip=127.0.0.1
INFO apps.audit.models recuperacao de senha: TOKEN_JA_USADO usuario_id=1 ip=127.0.0.1
```

A sequência acima é a evidência do requisito 2.7 em um bloco só: o pedido, o
envio, a recusa de um link inventado, a troca concluída e a recusa da segunda
tentativa de usar o mesmo link. Nenhuma linha carrega e-mail, token ou senha.

O log fica no banco, e não em arquivo, porque o Render apaga o disco a cada
implantação. O campo de data usa `auto_now_add`, que não aceita valor vindo de
fora, e o painel administrativo expõe o modelo apenas para leitura, sem botão de
criar, salvar ou excluir, nem para o superusuário.

*Captura a incluir: `img/19-log-recuperacao.png`, com a lista de registros no
painel administrativo.*

---

## Por que a resposta é sempre a mesma

A tela de confirmação diz "se houver uma conta com o endereço informado" e é
idêntica para qualquer e-mail digitado — conta existente, conta inexistente,
limite estourado ou falha no envio. Responder de forma diferente para um
endereço cadastrado transformaria o formulário em um verificador de quem tem
conta no sistema, pelo mesmo motivo que a tela de entrada mostra "E-mail ou
senha incorretos" sem dizer qual dos dois errou.

No log a diferença aparece como um registro com conta associada ou com usuário
nulo. O campo booleano que existia antes foi removido, pelo motivo registrado no
[checklist.md](checklist.md).

O teste `test_resposta_e_igual_para_email_inexistente` compara o código HTTP e o
destino do redirecionamento nos dois casos e exige que sejam iguais.

---

## Testes automatizados do bloco 2

```
python manage.py test apps.accounts.tests.RecuperacaoDeSenhaTests
```

```
Ran 24 tests in 3.655s

OK
```

| Grupo | Quantidade | Requisitos cobertos |
|---|---|---|
| Fluxo completo e anti-enumeração | 4 | 2.1 |
| Token seguro | 2 | 2.2 |
| Prazo de validade | 1 | 2.3 |
| Uso único e cancelamento | 3 | 2.4 |
| Recusa de link inválido, expirado e já usado | 3 | 2.5 |
| Registro em log | 6 | 2.6, 2.7 |
| Privacidade da trilha e texto da tela de envio | 5 | 2.1, 2.6, 2.7 |

O envio de e-mail é substituído por um espião nos testes: o token em texto puro
só existe dentro do link, então é ali que o teste precisa olhar, e a substituição
também impede que a suíte consuma a cota do Brevo.

---

# Bloco 3 — Criptografia e comunicação segura

## 3.1 e 3.2 — HTTPS obrigatório e bloqueio de HTTP

O acesso por HTTP é recusado em três camadas, cada uma cobrindo a falha da
anterior:

| Camada | Onde | O que faz |
|---|---|---|
| 1. Borda do Render | Proxy da Cloudflare, antes do Django | Responde a qualquer requisição HTTP com `301 Moved Permanently` para o endereço `https://` |
| 2. Django | `SECURE_SSL_REDIRECT = True` | Se uma requisição chegar em HTTP mesmo assim, o `SecurityMiddleware` devolve outro 301 para HTTPS |
| 3. Navegador | Cabeçalho `Strict-Transport-Security` | Depois da primeira visita, o próprio navegador converte `http://` em `https://` por um ano, sem nem enviar a requisição insegura |

**Como acontece o 301.** O navegador pede `http://projeto-politicas-seguranca.onrender.com/`.
A borda do Render responde com o código 301 e o cabeçalho `Location` apontando
para a mesma URL em `https://`. O 301 significa redirecionamento permanente, e
por isso o navegador passa a ir direto para o HTTPS. Na nova conexão acontece o
handshake TLS e só então a requisição chega ao Django.

A saída abaixo mostra que o 301 visto de fora vem da borda (`Server: cloudflare`),
e não do Django. A segunda camada não aparece nesse teste justamente porque a
primeira já resolveu. Por isso ela é comprovada por teste automatizado.

O Render encerra o TLS na borda e entrega a requisição ao Django em HTTP, com o
cabeçalho `X-Forwarded-Proto: https`. O `SECURE_PROXY_SSL_HEADER` diz ao Django
para confiar nesse cabeçalho. Sem ele, o Django veria toda requisição como HTTP
e a redirecionaria para HTTPS de novo, para sempre.

**Comando:**

```bash
curl -sI http://projeto-politicas-seguranca.onrender.com/
```

**Saída real:**

```
HTTP/1.1 301 Moved Permanently
Location: https://projeto-politicas-seguranca.onrender.com/
Server: cloudflare
```

**Comando:**

```bash
curl -sI https://projeto-politicas-seguranca.onrender.com/
```

**Saída real** (trecho com os cabeçalhos de segurança):

```
HTTP/1.1 200 OK
strict-transport-security: max-age=31536000; includeSubDomains; preload
x-content-type-options: nosniff
x-frame-options: DENY
```

Estes três cabeçalhos são enviados pelo Django, a partir das configurações do
bloco `if not DEBUG` em `config/settings.py`. Vê-los na resposta prova que o
sistema publicado roda com a configuração de produção.

**Testes automatizados** (`ComunicacaoSeguraTests`):

| Teste | O que prova |
|---|---|
| `test_http_e_redirecionado_para_https_com_301` | A segunda camada: o Django devolve 301 com `Location` em `https://` |
| `test_https_e_atendido_sem_redirecionamento` | Uma requisição HTTPS é atendida normalmente |
| `test_resposta_https_envia_hsts` | O cabeçalho HSTS sai com um ano, subdomínios e preload |
| `test_requisicao_vinda_do_proxy_do_render_nao_entra_em_loop` | Com `X-Forwarded-Proto: https`, o Django não redireciona de novo |

*Captura a incluir: `img/20-http-redireciona.png`, com a barra de endereço após
digitar `http://`, mostrando o endereço final em `https://`.*

---

## 3.3 — Evidência de tráfego cifrado

### Navegador → servidor

**Comando:**

```bash
openssl s_client -connect projeto-politicas-seguranca.onrender.com:443 \
  -servername projeto-politicas-seguranca.onrender.com </dev/null
```

**Saída real** (trecho):

```
subject=CN=onrender.com
issuer=C=US, O=Google Trust Services, CN=WE1
New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
Verify return code: 0 (ok)
```

**O que a saída comprova:** a conexão foi negociada em TLS 1.3, com o conjunto
`TLS_AES_256_GCM_SHA384` — AES de 256 bits em modo GCM para os dados e SHA-384
na derivação das chaves. O certificado é válido (`Verify return code: 0`),
emitido por uma autoridade certificadora reconhecida.

**Versões antigas são recusadas.** Forçando TLS 1.1:

```bash
openssl s_client -connect projeto-politicas-seguranca.onrender.com:443 \
  -servername projeto-politicas-seguranca.onrender.com \
  -tls1_1 -cipher 'DEFAULT@SECLEVEL=0' </dev/null
```

```
SSL routines:ssl3_read_bytes:tlsv1 alert protocol version: SSL alert number 70
New, (NONE), Cipher is (NONE)
```

O alerta 70 (`protocol version`) é a recusa enviada pelo servidor. O parâmetro
`-cipher 'DEFAULT@SECLEVEL=0'` é necessário porque o OpenSSL 3 local, por
padrão, se recusa a tentar TLS 1.1. Sem ele, o erro seria do próprio cliente e
não provaria nada sobre o servidor.

Forçando TLS 1.2, a conexão é aceita com `ECDHE-ECDSA-AES128-GCM-SHA256`, um
conjunto com troca de chaves efêmera e cifragem autenticada:

```bash
openssl s_client -connect projeto-politicas-seguranca.onrender.com:443 \
  -servername projeto-politicas-seguranca.onrender.com -tls1_2 </dev/null
```

```
New, TLSv1.2, Cipher is ECDHE-ECDSA-AES128-GCM-SHA256
```

### Aplicação → banco de dados

Consulta ao status da própria conexão do Django com o MySQL no Aiven, executada
a partir do ambiente local:

```bash
python manage.py shell -c "from django.db import connection; c = connection.cursor(); c.execute(\"SHOW SESSION STATUS WHERE Variable_name IN ('Ssl_version','Ssl_cipher')\"); print(c.fetchall())"
```

**Saída real:**

```
(('Ssl_cipher', 'TLS_AES_256_GCM_SHA384'), ('Ssl_version', 'TLSv1.3'))
```

**O que a saída comprova:** senhas em hash, segredos cifrados e todo o resto
trafegam entre a aplicação e o banco dentro de TLS 1.3. Um valor vazio nessas
variáveis indicaria uma conexão sem criptografia.

*Captura a incluir: `img/21-devtools-security.png`, com a aba Security do
DevTools aberta no site publicado.*

---

## 3.4 e 3.5 — Segredo do 2FA cifrado com AES-256-GCM

O valor gravado na coluna `key` da tabela `otp_totp_totpdevice` passou de
hexadecimal em texto puro para o formato cifrado:

```
Antes:  3a9f...  (40 caracteres hexadecimais: o próprio segredo)
Depois: aes256gcm$<nonce + texto cifrado + etiqueta, em base64>  (74 caracteres)
```

Com o valor antigo, bastava ler a tabela para cadastrar o 2FA de qualquer conta
em outro celular. O valor novo não pode ser usado sem a `FIELD_ENCRYPTION_KEY`,
que não está no banco.

**Pelo front-end:** com uma conta de equipe e o 2FA ativo, o card "Dados
técnicos" do perfil mostra `Segredo do 2FA no banco: aes256gcm (cifrado)`, ao
lado do algoritmo do hash da senha. O 2FA continua funcionando normalmente, o
que prova que o segredo é decifrado corretamente na hora de conferir o código.

**Testes automatizados** (`CriptografiaEmRepousoTests`):

| Teste | O que prova |
|---|---|
| `test_segredo_do_2fa_nao_fica_em_texto_puro` | O valor no banco começa com `aes256gcm$` e não contém o segredo |
| `test_codigo_do_autenticador_continua_valido` | Um código gerado a partir do segredo é aceito |
| `test_texto_cifrado_cabe_no_campo_do_django_otp` | O valor cifrado cabe nos 80 caracteres do campo |
| `test_mesmo_segredo_gera_textos_cifrados_diferentes` | O nonce aleatório torna cada cifragem única |
| `test_valor_alterado_no_banco_e_recusado` | Trocar um único caractere faz o GCM recusar o valor inteiro |
| `test_segredo_copiado_para_outra_conta_nao_decifra` | O contexto amarra o valor à conta dona |
| `test_chave_errada_nao_decifra` | Sem a chave certa, nada é decifrado |
| `test_texto_puro_nao_e_aceito_como_cifrado` | Um segredo em hexadecimal não é aceito no lugar do cifrado |
| `test_migracao_cifra_segredos_gravados_antes` | A migração cifra segredos antigos sem invalidar o celular já configurado |

*Captura a incluir: `img/22-segredo-2fa-cifrado.png`, com o card "Dados técnicos"
do perfil, e opcionalmente a coluna `key` consultada no banco.*

---

## 3.6 — Chaves protegidas

- `FIELD_ENCRYPTION_KEY` e `DJANGO_SECRET_KEY` são lidas apenas de variáveis de ambiente.
- O `.env` está no `.gitignore`. O `.env.example` traz só os nomes das variáveis e o comando para gerar a chave.
- Sem uma chave de 32 bytes válida, a aplicação não inicia: `ImproperlyConfigured: FIELD_ENCRYPTION_KEY ausente ou invalida`.
- Com `DEBUG` desligado, a ausência da `DJANGO_SECRET_KEY` também impede a inicialização.
- Os testes sorteiam uma chave nova a cada execução.
- O painel administrativo esconde o segredo e o QR Code dos dispositivos 2FA.

---

## Testes automatizados do bloco 3

```
python manage.py test apps.accounts.tests.CriptografiaEmRepousoTests apps.accounts.tests.ComunicacaoSeguraTests
```

| Grupo | Quantidade | Requisitos cobertos |
|---|---|---|
| `CriptografiaEmRepousoTests` | 9 | 3.4, 3.5, 3.6 |
| `ComunicacaoSeguraTests` | 4 | 3.1, 3.2 |

---

# Bloco 4 — Conformidade com a LGPD

## 4.1 a 4.3 — Dados coletados, finalidade e minimização

A Política de Privacidade fica em `/privacidade/politica/`, pública e ligada no
rodapé de todas as páginas. Ela traz a tabela de cada dado com finalidade, base
legal e prazo de guarda, e começa pelo que o sistema **não** coleta. O
dicionário técnico completo, com as tabelas do banco, está no
[checklist.md](checklist.md).

**Evidência de minimização:** o cadastro pede só nome, e-mail e senha. Dois
testes transformam isso em regra verificável:

- `test_modelo_de_usuario_so_tem_os_campos_necessarios` compara os campos da conta com uma lista fechada. Acrescentar um CPF ou um dado de saúde faz o teste falhar.
- `test_cadastro_pede_apenas_nome_email_e_senha` faz o mesmo com os campos do formulário.

*Capturas a incluir: `img/23-politica-privacidade.png` (tabela de dados da
política) e `img/24-cadastro-aceite.png` (cadastro com a caixa de aceite e o link
para a política).*

---

## 4.4, 4.5 e 4.7 — Consentimento registrado, com finalidade, data e versão

Cada aceite grava uma linha em `ConsentRecord`:

| Campo | Exemplo |
|---|---|
| `user` | a conta que aceitou |
| `purpose` | `CONTA` — Criação e manutenção da conta |
| `policy_version` | `1.0` |
| `granted_at` | data e hora do aceite, gravadas automaticamente |
| `revoked_at` | vazio enquanto o consentimento vale |

**Pelo front-end:** depois de criar a conta, "Privacidade e meus dados" mostra o
aceite na tabela "Consentimentos", com finalidade, versão, data e situação. Com
conta de equipe, o painel administrativo lista todos os registros em
"Registros de consentimento", sem opção de criar, editar ou excluir.

**Versão nova da política:** alterar `PRIVACY_POLICY_VERSION` em
`config/settings.py` faz toda conta logada ser levada a
`/privacidade/consentimento/` na próxima página que abrir. O aceite novo é
gravado ao lado do antigo, que continua no histórico.

**Testes automatizados** (`ConsentimentoTests`):

| Teste | O que prova |
|---|---|
| `test_cadastro_grava_o_aceite_com_finalidade_versao_e_data` | 4.4, 4.5 e 4.7 no cadastro |
| `test_cadastro_sem_aceite_nao_cria_conta_nem_registro` | Sem aceite, nada é gravado |
| `test_conta_sem_aceite_e_levada_a_tela_de_consentimento` | Contas antigas precisam aceitar |
| `test_aceite_pela_tela_libera_a_conta` | O aceite pela tela libera o acesso |
| `test_tela_de_consentimento_recusa_caixa_desmarcada` | Não existe aceite implícito |
| `test_nova_versao_da_politica_exige_novo_aceite` | 4.7: versão nova, aceite novo, histórico preservado |
| `test_revogacao_registra_a_data_e_preserva_o_historico` | 4.6: a revogação grava a data e o registro permanece |

*Captura a incluir: `img/25-meus-dados-consentimento.png`, com a tabela de
consentimentos em "Meus dados".*

---

## 4.8 — Consulta aos dados

Perfil → "Privacidade e meus dados" → `/privacidade/meus-dados/`.

A página mostra, agrupados: dados da conta, descrição de como as credenciais
são guardadas, consentimentos, acessos realizados, tentativas de acesso
malsucedidas e eventos de recuperação de senha. Hash da senha e segredo do 2FA
aparecem descritos, nunca com os valores.

*Captura a incluir: `img/26-meus-dados.png`.*

---

## 4.9 — Exportação em JSON

Botão "Exportar em JSON" na mesma página. O arquivo baixado tem exatamente os
dados da consulta, porque as duas telas usam a mesma função de coleta.

Estrutura do arquivo:

```json
{
  "gerado_em": "...",
  "conta": { "nome_completo": "...", "email": "...", "cadastrado_em": "...", "ultima_troca_de_senha": "...", "verificacao_em_duas_etapas": "ativa" },
  "credenciais": { "senha": "Guardada apenas como hash Argon2id...", "segredo_do_2fa": "Guardado cifrado com AES-256-GCM..." },
  "consentimentos": [ { "finalidade": "Criação e manutenção da conta", "versao_da_politica": "1.0", "aceito_em": "...", "revogado_em": null } ],
  "registros_de_seguranca": { "acessos_realizados": [...], "tentativas_de_acesso_malsucedidas": [...], "recuperacao_de_senha": [...] }
}
```

*Captura a incluir: `img/27-exportacao-json.png`, com o arquivo baixado aberto.*

---

## 4.6 e 4.10 — Revogação e exclusão

"Revogar consentimento e excluir conta" → `/privacidade/excluir-conta/`. A tela
lista o que será apagado e o que será anonimizado, oferece exportar antes e pede
a senha atual.

| Dado | O que acontece |
|---|---|
| Conta, nome, e-mail, hash da senha | Apagados |
| Segredo do 2FA e tokens de recuperação | Apagados em cascata com a conta |
| Acessos e tentativas do django-axes | Apagados |
| Trilha de recuperação de senha | Anonimizada: fica o evento e a data, sem IP, navegador ou vínculo |
| Registros de consentimento | Marcados como revogados e desvinculados da conta |

**Demonstração:** depois de confirmar, a sessão é encerrada. Tentar entrar com o
mesmo e-mail e senha resulta em "E-mail ou senha incorretos", e o e-mail fica
livre para um novo cadastro.

**Testes automatizados** (`DireitosDoTitularTests`):

| Teste | O que prova |
|---|---|
| `test_consulta_mostra_dados_da_conta_e_registros` | 4.8 |
| `test_consulta_nao_exibe_credenciais` | Hash, segredo cifrado e segredo decifrado não aparecem |
| `test_exportacao_gera_arquivo_json_para_download` | 4.9: JSON, `attachment`, `no-store`, todas as categorias |
| `test_exportacao_nao_inclui_credenciais` | O arquivo também não traz credenciais |
| `test_exportacao_nao_aceita_get` | Download só por POST com CSRF |
| `test_exclusao_exige_a_senha_correta` | Senha errada não apaga nada |
| `test_exclusao_apaga_a_conta_e_os_dados_pessoais` | 4.10: conta, 2FA, tokens e django-axes apagados, sessão encerrada |
| `test_exclusao_anonimiza_a_trilha_de_recuperacao` | O evento fica, sem IP, navegador ou vínculo |
| `test_tela_de_exclusao_continua_acessivel_sem_consentimento` | Recusar a política não impede sair do sistema |

*Capturas a incluir: `img/28-excluir-conta.png` (tela de confirmação) e
`img/29-conta-excluida.png` (mensagem após a exclusão).*

---

## 4.11 — Fluxo de atendimento

O passo a passo de cada direito, do clique na interface até o banco de dados,
está no [checklist.md](checklist.md), na seção "Fluxo de atendimento aos
direitos do titular".

---

## Testes automatizados do bloco 4

```
python manage.py test apps.privacy
```

| Grupo | Quantidade | Requisitos cobertos |
|---|---|---|
| `MinimizacaoTests` | 3 | 4.1, 4.2, 4.3 |
| `ConsentimentoTests` | 7 | 4.4, 4.5, 4.6, 4.7 |
| `DireitosDoTitularTests` | 9 | 4.8, 4.9, 4.10 |

## Suíte completa

```
python manage.py test apps.accounts apps.privacy
```

```
Ran 73 tests

OK
```

São 17 testes do bloco 1, 24 do bloco 2, 13 do bloco 3 e 19 do bloco 4.
