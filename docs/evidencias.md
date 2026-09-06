# Evidências de funcionamento

Comprovação prática dos requisitos dos blocos 1 e 2, demonstrados pelo front-end da aplicação.

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
Ran 19 tests in 2.070s

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

A suíte inteira do aplicativo passou a ter 36 testes, somando os 17 do bloco 1.
O envio de e-mail é substituído por um espião nos testes: o token em texto puro
só existe dentro do link, então é ali que o teste precisa olhar, e a substituição
também impede que a suíte consuma a cota do Brevo.
