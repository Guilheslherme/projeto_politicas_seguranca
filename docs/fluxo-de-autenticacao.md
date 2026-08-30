# Fluxo de autenticação

Documento do requisito 1.7.

## Visão geral

A autenticação tem duas etapas independentes. A primeira confere a senha, a
segunda confere o código gerado pelo aplicativo autenticador. A sessão do
usuário só é criada ao final da segunda etapa.

Essa separação é o ponto central do desenho: acertar a senha não autentica
ninguém.

## Cadastro

1. O usuário acessa `/conta/register/` e informa nome, e-mail e senha.
2. O formulário exige que a caixa de aceite da política de privacidade esteja
   marcada.
3. O e-mail é normalizado para minúsculas e verificado contra os já
   existentes, evitando contas duplicadas por diferença de maiúsculas.
4. A senha passa pelos validadores configurados: mínimo de 10 caracteres,
   recusa de senhas comuns, recusa de senhas apenas numéricas e recusa de
   senhas parecidas com os dados da conta.
5. `form.save()` chama `set_password`, que aplica o hash Argon2id.
6. O usuário é redirecionado para a tela de login. O cadastro não autentica
   automaticamente, para que a entrada sempre passe pelas duas etapas.

## Entrada — etapa 1: senha

1. O usuário informa e-mail e senha em `/conta/entrar/`.
2. O `django-axes` verifica se aquela combinação de e-mail e endereço de rede
   está bloqueada. Se estiver, a requisição para aqui e a tela de bloqueio é
   exibida.
3. O Django recalcula o hash da senha informada e compara com o armazenado.
4. Se a senha estiver incorreta, a tentativa é registrada e o contador de
   falhas é incrementado.
5. Se a senha estiver correta, a aplicação verifica se a conta possui um
   dispositivo TOTP confirmado.
6. **Sem 2FA:** a sessão é criada e o usuário vai para o perfil, com um aviso
   recomendando a ativação da verificação em duas etapas.
7. **Com 2FA:** a sessão **não** é criada. A aplicação grava três valores
   temporários na sessão anônima — o identificador do usuário, o backend de
   autenticação e o horário — e redireciona para a tela do código.

## Entrada — etapa 2: código

1. A tela `/conta/verificacao/` exibe o e-mail parcialmente mascarado e pede
   os 6 dígitos.
2. A aplicação confere se os valores temporários existem. Se não existirem,
   o acesso direto a essa URL é recusado e o usuário volta ao login.
3. A aplicação confere se passaram menos de 5 minutos desde a etapa 1. Se a
   janela expirou, os valores temporários são descartados e o usuário volta
   ao login.
4. O código informado é validado contra o segredo do dispositivo TOTP.
5. Se o código estiver incorreto, o formulário exibe o erro. Falhas repetidas
   passam a ser atrasadas pelo próprio `django-otp`.
6. Se o código estiver correto, a aplicação chama `login()`, criando a sessão,
   e `otp_login()`, registrando na sessão que o segundo fator foi verificado.

## Ativação da verificação em duas etapas

1. Em `/conta/verificacao/ativar/`, a aplicação cria um dispositivo TOTP
   marcado como **não confirmado**.
2. O segredo é apresentado como QR Code, gerado em memória e embutido na
   página como imagem. Nenhum arquivo é gravado no servidor.
3. O usuário lê o QR Code com o aplicativo autenticador e digita o código
   exibido.
4. Somente após um código válido o dispositivo passa a **confirmado** e o
   campo `two_factor_enabled` do usuário é atualizado.

Essa confirmação evita que o usuário fique trancado fora da própria conta
por ter ativado o recurso sem conseguir configurar o aplicativo.

## Encerramento da sessão

O logout remove o registro da sessão do banco de dados, e não apenas o cookie
do navegador. Um cookie copiado antes do logout deixa de ter validade.

A sessão também expira sozinha após 15 minutos sem interação, com o prazo
renovado a cada requisição, e é encerrada quando o navegador é fechado.

## Diagrama do fluxo

```
CADASTRO
   dados -> validação -> hash Argon2id -> conta criada -> tela de login

ENTRADA
   e-mail + senha
        |
        v
   [conta bloqueada?] --sim--> tela de bloqueio (5 minutos)
        |não
        v
   [senha confere?] --não--> registra falha -> tela de login com erro
        |sim
        v
   [conta tem 2FA?] --não--> cria sessão -> perfil
        |sim
        v
   grava marcação temporária (5 minutos), SEM criar sessão
        |
        v
   tela do código de 6 dígitos
        |
        v
   [janela expirou?] --sim--> descarta marcação -> tela de login
        |não
        v
   [código confere?] --não--> erro no formulário
        |sim
        v
   cria a sessão -> registra o segundo fator -> perfil
```

## Onde cada parte está no código

| Etapa | Arquivo |
|---|---|
| Modelo de usuário | `apps/accounts/models.py` |
| Criação de usuários | `apps/accounts/managers.py` |
| Parâmetros do Argon2id | `apps/accounts/hashers.py` |
| Formulários de cadastro, login e código | `apps/accounts/forms.py` |
| Views das duas etapas | `apps/accounts/views.py` |
| Rotas | `apps/accounts/urls.py` |
| Sessão, bloqueio e 2FA | `config/settings.py` |
