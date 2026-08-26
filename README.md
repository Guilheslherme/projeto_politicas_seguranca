![CONTRIBUIDOR](https://img.shields.io/github/contributors/guilheslherme/projeto_politicas_seguranca.svg?style=for-the-badge)
![license-shield](https://img.shields.io/github/license/guilheslherme/projeto_politicas_seguranca.svg?style=for-the-badge)


# Health In Sight

**Portal de divulgação de informações confiáveis sobre saúde**

Trabalho da disciplina de Políticas de Informação — Sistemas de Informação, Universidade de Mogi das Cruzes.

---

## Sobre o Projeto

O projeto aborda a circulação desordenada de informações sobre saúde no ambiente digital, fenômeno descrito pela Organização Mundial da Saúde como **infodemia**: o excesso de informação, verdadeira ou não, que dificulta que as pessoas encontrem orientação segura quando dela necessitam.

Órgãos como o Ministério da Saúde, a Fiocruz e as secretarias estaduais produzem material de qualidade, mas esse conteúdo está espalhado por dezenas de portais, com linguagem técnica e navegação pouco intuitiva. O resultado é que o cidadão recorre a buscas genéricas e redes sociais, onde a informação verificada concorre em igualdade com a desinformação.

O Health In Sight (Saúde à Vista) reúne esses conteúdos em um único ambiente, organizados por condição de saúde, área e público-alvo, sempre com atribuição da fonte oficial que os produziu e redirecionamento para a publicação original.

A plataforma tem caráter **estritamente informativo e educativo**: não realiza diagnóstico, não emite prescrição e não presta atendimento clínico.

---

## Decisão de arquitetura: privacidade por concepção

A Lei Geral de Proteção de Dados Pessoais classifica dados de saúde como **dados pessoais sensíveis** (art. 5º, II), sujeitos ao regime mais restritivo do art. 11.

Por essa razão, o projeto adota o princípio da necessidade (art. 6º, III): **a plataforma não coleta, não armazena e não processa dados de saúde de seus usuários**. O acervo é público e idêntico para todos os visitantes, sem personalização por condição de saúde. O risco de vazamento de dado sensível é eliminado na origem, e não apenas mitigado por controles.

Os dados pessoais efetivamente tratados são apenas os necessários à autenticação e à segurança do sistema:

| Dado | Finalidade |
|---|---|
| Nome completo | Identificação na interface |
| E-mail | Login, recuperação de senha, avisos da conta |
| Senha | Autenticação — armazenada apenas como hash Argon2id |
| Segredo do 2FA | Validação do segundo fator  |
| IP e data/hora de acesso | Segurança e rastreabilidade |
| Registro de consentimento | Data, versão do termo e finalidade aceita |

---

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Front-end | HTML5, CSS3, JavaScript |
| Back-end | Python 3.12, Django 5.2 |
| Banco de dados | MySQL 8 (Aiven, conexão TLS) |
| Hash de senhas | Argon2id (`argon2-cffi`) |
| Segundo fator | TOTP — RFC 6238 (`django-otp`) |
| Força bruta | `django-axes` |
| Hospedagem | Render, com TLS gerenciado |

---

## Estrutura

```
projeto_politicas_seguranca/
├── config/              configuração do projeto
│   ├── settings.py      configurações
│   ├── urls.py          rotas principais
│   └── wsgi.py          entrada em produção
├── apps/
│   ├── accounts/        autenticação, credenciais, 2FA e sessões
│   ├── catalog/         conteúdos de saúde, áreas e fontes parceiras
│   ├── privacy/         consentimento e direitos do titular (LGPD)
│   └── audit/           trilha de auditoria
├── templates/           páginas HTML
├── static/              CSS, JavaScript e imagens
├── certs/               certificado da CA do banco (não versionado)
├── docs/                documentação técnica
└── requirements.txt
```

As configurações ficam em `config/settings.py`.

---

## Como executar

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

No Linux ou macOS, troque a ativação por `source .venv/bin/activate`.

O site fica em `http://127.0.0.1:8000`. Variáveis sensíveis são lidas de um arquivo `.env` na raiz, que não é versionado.

---

## Segurança planejada

| Mecanismo | Implementação |
|---|---|
| Hash de senhas | Argon2id, conforme RFC 9106 |
| Parâmetros de custo | m = 64 MiB, t = 3, p = 2 |
| Salt | Aleatório, único por senha |
| Segundo fator | TOTP validado após a autenticação primária |
| Sessão | Expiração de 15 minutos, renovada a cada requisição |
| Logout | Destruição da sessão no servidor |
| Força bruta | Bloqueio após 5 falhas, resfriamento de 15 minutos |
| Transporte | HTTPS obrigatório, HSTS, cookies `Secure` e `HttpOnly` |
| Em repouso | Segredo do 2FA e IPs de auditoria cifrados com AES |
| Segredos | Fora do controle de versão, em variáveis de ambiente |

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
| Catálogo de conteúdos de saúde | Planejada |
| Funcionalidades de LGPD | Planejada |
| Publicação (Render + Aiven) | Planejada |

---

## Referências normativas

- BIRYUKOV, A. et al. *Argon2 Memory-Hard Function for Password Hashing*. RFC 9106, IETF, 2021.
- M'RAIHI, D. et al. *TOTP: Time-Based One-Time Password Algorithm*. RFC 6238, IETF, 2011.
- NIST. *Digital Identity Guidelines: Authentication and Lifecycle Management*. SP 800-63B.
- OWASP. *Password Storage Cheat Sheet*.
- BRASIL. *Lei nº 13.709, de 14 de agosto de 2018* (LGPD).
- ORGANIZAÇÃO MUNDIAL DA SAÚDE. *Infodemic management*.

---

## Equipe

- Guilherme da Silva Bonifácio — [@Guilheslherme](https://github.com/Guilheslherme)
- Cassiano Jesus da Silva — [@Ashketchup13](https://github.com/Ashketchup13)
- Yan Baumgarten Costa — [@Baumgarten1801](https://github.com/Baumgarten1801)

---

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).
