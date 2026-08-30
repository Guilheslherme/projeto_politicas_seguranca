# Evidências de funcionamento

Documento do requisito 1.8. Todos os itens abaixo são demonstrados pelo
front-end da aplicação, conforme exigido.

Aplicação publicada: https://projeto-politicas-seguranca.onrender.com

> **Como usar este arquivo:** tire cada print indicado, salve na pasta
> `docs/img/` com o nome sugerido e a imagem aparece automaticamente.
> Prints que ainda não foram tirados ficam com o espaço em branco.

---

## 1.1, 1.3 e 1.4 — Hash Argon2id, salt único e armazenamento

**Pelo front-end:** criar duas contas em `/conta/register/` usando a mesma
senha.

**Evidência:** consulta ao banco mostrando as duas linhas.

```sql
SELECT email, LEFT(password, 60) FROM accounts_user;
```

As duas senhas são idênticas, e os hashes são completamente diferentes, porque
o salt é gerado a cada senha. O prefixo `argon2$argon2id$` comprova o
algoritmo, e o trecho `m=65536,t=3,p=2` comprova os parâmetros configurados.

![Hashes no banco](docs/img/Teste Visual - Argon2 - Banco de Dados.jpg)

---

## 1.2 — Parâmetros de custo

**Evidência:** o próprio hash carrega os parâmetros usados.

```
argon2$argon2id$v=19$m=65536,t=3,p=2$SALT$HASH
```

A justificativa de cada valor está em [decisoes-tecnicas.md](decisoes-tecnicas.md).

---

## Validação de senha no cadastro

**Pelo front-end:** tentar criar conta com a senha `123456`.

**Evidência:** a aplicação recusa com três mensagens simultâneas — senha curta
demais, senha comum demais e senha apenas numérica.

![Validação de senha](img/02-senha-fraca-recusada.png)

**Pelo front-end:** tentar criar conta sem marcar a caixa da política de
privacidade.

**Evidência:** o envio é bloqueado.

![Consentimento obrigatório](img/03-consentimento-obrigatorio.png)

---

## 1.5 — Ativação da verificação em duas etapas

**Pelo front-end:** entrar em `/conta/perfil/` e ativar a verificação em duas
etapas.

**Evidência:** o QR Code é exibido na tela e lido pelo aplicativo
autenticador. Após digitar um código válido, o perfil passa a indicar a
verificação como ativa.

![QR Code de ativação](img/04-qrcode-ativacao.png)

![Perfil com 2FA ativo](img/05-perfil-2fa-ativo.png)

---

## 1.6 — Validação do 2FA após a autenticação primária

Este é o item central do bloco. A senha correta **não** cria sessão.

**Pelo front-end:** sair da conta e entrar novamente com e-mail e senha
corretos.

**Evidência:** a aplicação para na tela do código, com o e-mail parcialmente
mascarado, sem autenticar o usuário.

![Etapa 2 de 2](img/06-tela-do-codigo.png)

**Segunda evidência:** tentar acessar `/conta/perfil/` diretamente pela barra
de endereços, nesse momento. A aplicação redireciona para o login, porque não
existe sessão criada.

![Acesso direto recusado](img/07-acesso-direto-recusado.png)

---

## 1.9 — Expiração de sessão

**Pelo front-end:** entrar na conta, permanecer 15 minutos sem interagir e
recarregar a página.

**Evidência:** a aplicação pede login novamente.

![Sessão expirada](img/08-sessao-expirada.png)

Configuração correspondente em `config/settings.py`:

```python
SESSION_COOKIE_AGE = 900
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
```

---

## 1.10 — Invalidação de sessão no logout

**Pelo front-end:** entrar na conta, sair e tentar voltar a `/conta/perfil/`
pelo botão de voltar do navegador ou pelo histórico.

**Evidência:** a aplicação redireciona para o login. A sessão foi removida do
banco de dados, e não apenas o cookie do navegador.

![Logout](img/09-logout.png)

---

## 1.11 — Proteção contra força bruta

**Pelo front-end:** errar a senha cinco vezes seguidas na tela de login.

**Evidência:** a sexta tentativa apresenta a tela de bloqueio, com resposta
HTTP 429.

![Tela de bloqueio](img/10-bloqueio.png)

O registro correspondente na tabela do `django-axes`:

```sql
SELECT attempt_time, failures_since_start FROM axes_accessattempt;
```

![Registro do bloqueio](img/11-registro-bloqueio.png)

---

## 1.8 — Testes automatizados

Além das demonstrações pelo front-end, o projeto possui 17 testes
automatizados.

```
python manage.py test apps.accounts
```

Resultado esperado:

```
Found 17 test(s).
Creating test database for alias 'default'...
System check identified no issues (0 silenced).
.................
----------------------------------------------------------------------
Ran 17 tests in 2.171s

OK
Destroying test database for alias 'default'...
```

![Saída dos testes](img/12-testes.png)

Cobertura por grupo:

| Grupo | Testes | Requisitos |
|---|---|---|
| `ArmazenamentoDeSenhaTests` | 5 | 1.1, 1.2, 1.3, 1.4 |
| `DuasEtapasTests` | 4 | 1.5, 1.6 |
| `SessaoTests` | 3 | 1.9, 1.10 |
| `ForcaBrutaTests` | 2 | 1.11 |
| `CadastroTests` | 3 | 1.1 e consentimento |

---

## 3.1 — Comunicação protegida por TLS

**Pelo front-end:** abrir a aplicação publicada e verificar o cadeado na barra
de endereços.

**Evidência:** conexão em HTTPS, com certificado válido. O acesso por HTTP é
redirecionado automaticamente.

![HTTPS](img/13-https.png)
