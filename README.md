![CONTRIBUIDOR](https://img.shields.io/github/contributors/guilheslherme/projeto_politicas_seguranca.svg?style=for-the-badge)
![license-shield](https://img.shields.io/github/license/guilheslherme/projeto_politicas_seguranca.svg?style=for-the-badge)

# Health In Sight

Portal que reúne informações confiáveis sobre saúde em um só lugar.

Trabalho da disciplina de Políticas de Informação, do curso de Sistemas de Informação da Universidade de Mogi das Cruzes.

Site no ar: https://projeto-politicas-seguranca.onrender.com <br>
KanBan: https://github.com/users/Guilheslherme/projects/3

## O problema

Quando alguém procura informação sobre saúde na internet, o que aparece primeiro raramente é o que veio de um órgão oficial. A Organização Mundial da Saúde chama isso de infodemia: tanta informação circulando, verdadeira e falsa misturadas, que fica difícil achar orientação segura na hora em que ela é necessária.

O conteúdo bom existe. O Ministério da Saúde, a Fiocruz e as secretarias estaduais publicam material sério, só que espalhado por dezenas de sites diferentes, escrito em linguagem técnica e com navegação complicada. Na prática, quase ninguém chega lá.

O Health In Sight junta esse material em um lugar só, organizado por condição de saúde, área e público, sempre dizendo de onde veio e com link para a publicação original.

O site é informativo. Não faz diagnóstico, não receita nada e não substitui consulta.

## A decisão mais importante do projeto

A LGPD trata dado de saúde como dado sensível, com regras mais rígidas que as dos dados comuns.

Em vez de coletar esses dados e proteger com vários controles, o projeto simplesmente não coleta. Nenhum. O acervo é público e igual para todo mundo, sem personalização por condição de saúde. Assim não existe vazamento possível de dado sensível, porque não existe dado sensível guardado.

O que o sistema guarda é só o necessário para a conta funcionar:

- nome e e-mail, para identificar a pessoa e falar com ela
- a senha, e mesmo assim só o hash, que não dá para reverter
- o segredo da verificação em duas etapas
- IP e horário de acesso, para segurança
- o registro de que a pessoa aceitou a política de privacidade, com data e versão

## Como está feito

Python 3.12 com Django 5.2 no servidor, HTML, CSS e JavaScript (ainda não começamos a usar) na tela. O banco é MySQL hospedado no Aiven, com conexão cifrada. O site roda no Render, com HTTPS.

Para as senhas usamos Argon2id, e para a verificação em duas etapas o padrão TOTP, o mesmo dos aplicativos autenticadores como Google Authenticator.

## Rodando na sua máquina

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

O site abre em http://127.0.0.1:8000.

Falta uma coisa antes de rodar: copiar o `.env.example` para `.env` e preencher. Esse arquivo tem a chave do Django e a senha do banco, então ele não vai para o repositório. Cada um do grupo tem o seu, e o certificado do banco também fica de fora.

## Segurança

**Senhas.** Não guardamos senha nenhuma, só o resultado do Argon2id, que é um caminho de mão única. Os valores usados são 64 MiB de memória, 3 iterações e paralelismo 2, que é uma das configurações recomendadas pela RFC 9106. A memória alta é de propósito: ela atrapalha justamente quem tenta quebrar senhas em placa de vídeo.

Cada senha recebe um salt aleatório próprio. Duas pessoas com a mesma senha ficam com hashes completamente diferentes no banco, o que impede que alguém descubra as duas de uma vez.

**Entrada em duas etapas.** Acertar a senha não entra no site. O sistema guarda uma marcação temporária de 5 minutos e só cria a sessão depois que o código de 6 dígitos do celular for conferido. Quem tem a senha mas não tem o telefone fica de fora.

**Sessão.** Expira em 15 minutos parados. Quem está usando não é desconectado, porque o prazo reinicia a cada página aberta. Fechar o navegador também encerra. No logout a sessão é apagada do banco, não só esquecida pelo navegador, então um cookie copiado antes não serve para nada depois.

**Tentativas de invasão.** Depois de 5 senhas erradas, aquela combinação de conta e endereço fica bloqueada por 5 minutos. O bloqueio é da combinação, e não só do e-mail, senão qualquer pessoa poderia travar a conta de outra de propósito.

**Transporte.** Em produção o site força HTTPS e a conexão com o banco é cifrada, com verificação do certificado.

## O que já funciona

Cadastro, login, logout, verificação em duas etapas com QR Code, bloqueio por tentativas repetidas e a tela de perfil.

Tem 17 testes automatizados cobrindo essa parte. Para rodar:

```bash
python manage.py test apps.accounts
```

## O que ainda falta

Recuperação de senha por e-mail, o catálogo de conteúdos de saúde, as telas de exercício dos direitos da LGPD (consultar, exportar e excluir os próprios dados) e a trilha de auditoria.

## Referências

- https://www.boldare.com/blog/how-to-improve-user-password-security-with-argon2/
- M'RAIHI, D. et al. TOTP: Time-Based One-Time Password Algorithm. RFC 6238, IETF, 2011.
- NIST. Digital Identity Guidelines: Authentication and Lifecycle Management. SP 800-63B, 2017.
- OWASP. Password Storage Cheat Sheet.
- BRASIL. Lei nº 13.709, de 14 de agosto de 2018 (LGPD).
- ORGANIZAÇÃO MUNDIAL DA SAÚDE. Infodemic management.

## Utilizamos

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092E20?style=for-the-badge&logo=django&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8-4479A1?style=for-the-badge&logo=mysql&logoColor=white)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css&logoColor=white)
![Render](https://img.shields.io/badge/Render-000000?style=for-the-badge&logo=render&logoColor=white)

## Equipe

- Guilherme da Silva Bonifácio — [@Guilheslherme](https://github.com/Guilheslherme)
- Cassiano Jesus da Silva — [@Ashketchup13](https://github.com/Ashketchup13)
- Yan Baumgarten Costa — [@Baumgarten1801](https://github.com/Baumgarten1801)


## Licença

MIT. O texto está no arquivo [LICENSE](LICENSE).
