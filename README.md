# Project In Sight

**WebSite de divulgação de cursos de terceiros**

Trabalho da disciplina de Políticas de Informação — plataforma web para
centralização e divulgação de cursos EAD de instituições parceiras, com foco em
segurança da informação e conformidade com a LGPD.

---

## Sobre o Projeto

O projeto de Políticas de Informação aborda o crescimento acelerado da educação
a distância (EAD), tendo como objetivo desenvolver e estabelecer uma conexão
segura de uma plataforma web voltada para a centralização, divulgação e
facilitação do acesso à educação online. O sistema facilita o acesso a conteúdos
educacionais, permitindo que usuários realizem cadastro e login e naveguem por
um catálogo diversificado de cursos oferecidos por instituições de terceiros.
As instituições parceiras ganham visibilidade, o que gera receita e mantém o
projeto ativo, tudo em conformidade normativa.

O público-alvo é constituído por estudantes, recém-formados e profissionais que
buscam qualificação contínua ou que estão em transição ou início de carreira por
meio da educação a distância, além das instituições dispostas a se tornarem
parceiras do projeto, prezando pela visibilidade e pelo engajamento de seus
cursos, ajudando os alunos a adquirirem conhecimento e as devidas horas
complementares.

O foco do projeto é a segurança da informação: proteção dos dados sensíveis
coletados, senhas armazenadas com criptografia adequada e validações do lado do
usuário, preservando a integridade, a confiabilidade e a privacidade dos dados.
O sistema também prevê que o usuário possa revogar o acesso aos seus dados a
qualquer momento, alinhando-se às práticas de transparência exigidas pela Lei
Geral de Proteção de Dados Pessoais (LGPD).

---

## Tecnologias Utilizadas

### Front-end
- HTML5
- CSS3
- JavaScript (validações do lado do usuário)

### Back-end
- Python 3.12
- Django 5.2

### Banco de dados
- MySQL 8 (Aiven, conexão obrigatória por TLS)
- SQLite (apenas em desenvolvimento local)

### Segurança
- **Argon2id** (`argon2-cffi`) — hash de senhas
- **TOTP / RFC 6238** (`django-otp`) — autenticação de dois fatores
- **django-axes** — proteção contra ataques de força bruta

### Infraestrutura
- Render — hospedagem da aplicação, com TLS gerenciado
- Gunicorn — servidor de aplicação
- WhiteNoise — entrega de arquivos estáticos

---

## Arquitetura

O projeto segue a arquitetura MVT (Model–View–Template) do Django, com os
módulos separados por responsabilidade.

```
projeto_politicas_seguranca/
├── config/                 configuração do projeto
│   ├── settings/
│   │   ├── base.py         configurações comuns
│   │   ├── development.py  ambiente local (DEBUG ligado)
│   │   └── production.py   servidor (HTTPS obrigatório, HSTS)
│   ├── urls.py             roteamento principal
│   └── wsgi.py             ponto de entrada em produção
├── apps/
│   ├── accounts/           autenticação, credenciais, 2FA e sessões
│   ├── catalog/            cursos, categorias e instituições parceiras
│   ├── privacy/            consentimento e direitos do titular (LGPD)
│   └── audit/              trilha de auditoria de eventos
├── templates/              páginas HTML
├── static/                 CSS, JavaScript e imagens
├── certs/                  certificado da CA do banco (não versionado)
├── docs/                   documentação técnica
└── requirements.txt        dependências com versões travadas
```

### Responsabilidade de cada módulo

| Módulo | Responsabilidade |
|---|---|
| `accounts` | Modelo de usuário customizado (login por e-mail), cadastro, autenticação, hash de senhas, segundo fator, controle de sessão e recuperação de senha |
| `catalog` | Cursos, categorias e instituições parceiras; busca, filtros e redirecionamento para o site do parceiro |
| `privacy` | Registro de consentimento por finalidade, consulta, exportação e exclusão de dados pessoais |
| `audit` | Registro imutável de eventos de autenticação, falhas, bloqueios e ações sobre dados pessoais |

### Separação de ambientes

As configurações são divididas em três arquivos. O `manage.py` carrega
`development` e o `wsgi.py` carrega `production`, de modo que a troca ocorre
automaticamente no deploy. Isso impede que `DEBUG = True` chegue ao servidor —
com ele ativo, qualquer erro exibiria ao visitante caminhos de arquivos, trechos
de código e parte das configurações.

---

## Como executar o projeto

### Pré-requisitos

- Python 3.12
- Git

### Instalação

```bash
git clone https://github.com/Guilheslherme/projeto_politicas_seguranca.git
cd projeto_politicas_seguranca
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

No Linux ou macOS, troque a ativação do ambiente por `source .venv/bin/activate`.

O site fica disponível em `http://127.0.0.1:8000`.

### Configuração de ambiente

Variáveis sensíveis (chave da aplicação, credenciais do banco, e-mail) são lidas
de um arquivo `.env` na raiz do projeto, que **não é versionado**. Use o
`.env.example` como modelo.

---

## Segurança implementada

### Autenticação e gestão de credenciais

| Mecanismo | Implementação |
|---|---|
| Hash de senhas | Argon2id, variante recomendada pela RFC 9106 |
| Parâmetros de custo | m = 64 MiB, t = 3 iterações, p = 2 lanes |
| Salt | Aleatório, gerado por CSPRNG, único por senha |
| Armazenamento | String PHC única: algoritmo, parâmetros, salt e hash |
| Segundo fator | TOTP (RFC 6238), validado após a autenticação primária |
| Sessão | Expiração de 15 minutos, renovada a cada requisição |
| Logout | Destruição da sessão no servidor (`session.flush()`) |
| Força bruta | Bloqueio após 5 falhas, resfriamento de 15 minutos |

### Criptografia e comunicação

| Mecanismo | Implementação |
|---|---|
| Transporte | HTTPS obrigatório, com redirecionamento automático |
| HSTS | 1 ano, incluindo subdomínios |
| Cookies | `Secure`, `HttpOnly` e `SameSite=Lax` |
| Banco de dados | Conexão TLS com verificação do certificado da CA |
| Segredos | Fora do controle de versão, lidos de variáveis de ambiente |

### Conformidade com a LGPD

- Coleta mínima de dados: apenas nome e e-mail
- Consentimento registrado por finalidade, com data e versão da política
- Revogação do consentimento a qualquer momento
- Consulta, exportação e exclusão dos dados pelo próprio titular
- Trilha de auditoria preservada de forma pseudonimizada, conforme o
  artigo 16, incisos I e III

---

## Estado do desenvolvimento

| Etapa | Situação |
|---|---|
| Estrutura do projeto e separação de ambientes | Concluída |
| Proteção de segredos no controle de versão | Concluída |
| Modelo de usuário customizado e Argon2id | Em desenvolvimento |
| Cadastro, login e logout | Planejada |
| Autenticação de dois fatores (TOTP) | Planejada |
| Proteção contra força bruta | Planejada |
| Catálogo de cursos | Planejada |
| Funcionalidades de LGPD | Planejada |
| Publicação (Render + Aiven) | Planejada |

---

## Documentação técnica

A documentação completa está na pasta [`docs/`](docs/):

- `auth-flow.md` — diagramas do fluxo de autenticação
- `technical-decisions.md` — justificativas das escolhas de segurança
- `architecture.md` — visão geral e diagrama de arquitetura

---

## Referências normativas

- BIRYUKOV, A. et al. *Argon2 Memory-Hard Function for Password Hashing*.
  RFC 9106, IETF, 2021.
- M'RAIHI, D. et al. *TOTP: Time-Based One-Time Password Algorithm*.
  RFC 6238, IETF, 2011.
- NIST. *Digital Identity Guidelines: Authentication and Lifecycle Management*.
  SP 800-63B.
- OWASP. *Password Storage Cheat Sheet*.
- BRASIL. *Lei nº 13.709, de 14 de agosto de 2018* (LGPD).

---

## Equipe

- Guilherme Bonifácio — [@Guilheslherme](https://github.com/Guilheslherme)
- Cassiano Jesus da Silva — [@Ashketchup13](https://github.com/Ashketchup13)

---

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE) para mais informações.
