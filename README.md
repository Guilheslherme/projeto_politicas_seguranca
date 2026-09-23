![CONTRIBUIDOR](https://img.shields.io/github/contributors/guilheslherme/projeto_politicas_seguranca.svg?style=for-the-badge)
![license-shield](https://img.shields.io/github/license/guilheslherme/projeto_politicas_seguranca.svg?style=for-the-badge)

# Health In Sight

Portal que reúne informações confiáveis sobre saúde em um só lugar.

Trabalho da disciplina de Políticas de Informação, do curso de Sistemas de Informação da Universidade de Mogi das Cruzes.

Site no ar: https://projeto-politicas-seguranca.onrender.com <br>
KanBan: https://github.com/users/Guilheslherme/projects/3

Documentação: [check-list dos requisitos](docs/checklist.md) · [evidências de funcionamento](docs/evidencias.md) · [análise de logs](docs/analise-de-logs.md)

## O problema

Quando alguém procura informação sobre saúde na internet, o que aparece primeiro raramente é o que veio de um órgão oficial. A Organização Mundial da Saúde chama isso de infodemia: tanta informação circulando, verdadeira e falsa misturadas, que fica difícil achar orientação segura na hora em que ela é necessária.

O conteúdo bom existe. O Ministério da Saúde, a Fiocruz e as secretarias estaduais publicam material sério, só que espalhado por dezenas de sites diferentes, escrito em linguagem técnica e com navegação complicada. Na prática, quase ninguém chega lá.

O Health In Sight junta esse material em um lugar só, sempre dizendo de onde veio e com link para a publicação original.

O site é informativo. Não faz diagnóstico, não receita nada e não substitui consulta.

## A decisão mais importante do projeto

A LGPD trata dado de saúde como dado sensível, com regras mais rígidas que as dos dados comuns.

A saída do projeto não foi coletar esses dados e cercá-los de controles: foi não coletar. O acervo é público e igual para todo mundo, sem personalização por condição de saúde, e o filtro de sintomas funciona sem gravar o que a pessoa marcou.

Sobra um ponto em que o dado sensível aparece, e a gente preferiu encarar em vez de esconder: guardar um material na conta indica interesse por um tema de saúde. Por isso essa função vem desligada, tem consentimento próprio, pedido em tela separada, e revogar apaga o que foi guardado. É o Art. 8º, §4º da LGPD virando tela: consentimento genérico não vale, tem que ser para finalidade determinada.

O que o sistema guarda hoje é só o necessário para a conta funcionar:

- nome e e-mail, para identificar a pessoa e falar com ela
- a senha, e mesmo assim só o hash, que não dá para reverter
- o segredo da verificação em duas etapas, cifrado
- IP e horário de acesso, para segurança
- o registro de que a pessoa aceitou a política de privacidade, com data e versão

## Como o filtro funciona

A pessoa marca os sintomas numa lista. O portal mostra as condições que fontes oficiais associam àqueles sintomas, cada uma com quem afirmou a associação e o link para o material original.

Três regras sustentam isso, e as três estão no código, não só no texto:

**Quem liga o sintoma à condição é a fonte.** Toda associação carrega obrigatoriamente o material que a afirma. Sem material, a associação não existe no banco. É isso que separa o portal de um verificador de sintomas: a gente não inventa o vínculo, a gente cita quem fez.

**Sinal de alerta interrompe.** Dor no peito, falta de ar, fraqueza súbita em um lado do corpo e dor de cabeça que começou de repente. Marcando qualquer um deles, o portal não mostra lista nenhuma: manda procurar atendimento e para por ali.

**Nada é ordenado por probabilidade.** Nenhum modelo tem campo de peso, pontuação ou chance, e a lista sai em ordem alfabética. Toda lista vem precedida do aviso de que pode estar incompleta e não diz o que a pessoa tem.

## Como está feito

Python 3.12 com Django 5.2 no servidor, HTML, CSS e JavaScript puro na tela, sem framework de front-end. O banco é MySQL hospedado no Aiven, com conexão cifrada. O site roda no Render, com HTTPS.

O JavaScript é usado em três lugares pequenos: o menu do celular, o modal de consentimento e o botão de mostrar a senha. **O filtro de sintomas não depende dele** — funciona com formulário e recarga de página, e por isso continua funcionando com o JavaScript desligado.

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

O `migrate` já cria o acervo inicial: dez sintomas, quatro condições e cinco materiais do Ministério da Saúde e da OPAS/OMS. Conteúdo novo é cadastrado pelo painel, em `/admin/`.

## Segurança

**Senhas.** Não guardamos senha nenhuma, só o resultado do Argon2id, que é um caminho de mão única. Os valores usados são 64 MiB de memória, 3 iterações e paralelismo 2, que é uma das configurações recomendadas pela RFC 9106. A memória alta é de propósito: ela atrapalha justamente quem tenta quebrar senhas em placa de vídeo.

Cada senha recebe um salt aleatório próprio. Duas pessoas com a mesma senha ficam com hashes completamente diferentes no banco, o que impede que alguém descubra as duas de uma vez.

**Entrada em duas etapas.** Acertar a senha não entra no site. O sistema guarda uma marcação temporária de 5 minutos e só cria a sessão depois que o código de 6 dígitos do celular for conferido. Quem tem a senha mas não tem o telefone fica de fora.

**Sessão.** Expira em 15 minutos parados. Quem está usando não é desconectado, porque o prazo reinicia a cada página aberta. Fechar o navegador também encerra. No logout a sessão é apagada do banco, não só esquecida pelo navegador, então um cookie copiado antes não serve para nada depois.

**Tentativas de invasão.** Depois de 5 senhas erradas, aquela combinação de conta e endereço fica bloqueada por 5 minutos. O bloqueio é da combinação, e não só do e-mail, senão qualquer pessoa poderia travar a conta de outra de propósito.

**Recuperação de senha.** O link enviado por e-mail carrega um token de 256 bits sorteado pelo gerador criptográfico do sistema. No banco fica apenas o SHA-256 dele, nunca o valor do link. Vale 30 minutos, serve uma vez só, e pedir um link novo cancela os anteriores.

**Criptografia em repouso.** O segredo da verificação em duas etapas é o dado mais perigoso do banco, porque com ele dá para gerar os códigos de acesso de alguém. Ele é cifrado com AES-256-GCM antes de ser gravado.

**Transporte.** Em produção o site força HTTPS e a conexão com o banco é cifrada, com verificação do certificado.

**Trilha de auditoria.** Todo login, logout, senha recusada, bloqueio e uso do segundo fator vira um registro. Cada registro guarda o hash do anterior, formando uma corrente: alterar ou apagar um evento do meio faz o elo seguinte deixar de bater, e o comando `python manage.py verificar_logs` aponta onde. O que essa proteção **não** cobre está escrito em [docs/analise-de-logs.md](docs/analise-de-logs.md) — apagar os últimos registros não é detectado, e quem tem o banco e o código consegue recalcular a corrente.

**O e-mail digitado numa tentativa de login não é gravado** na nossa trilha. Ele serve só para descobrir de qual conta se trata, e é descartado em seguida.

## Direitos do titular

Pelo menu "Meus dados", quem tem conta pode:

- **consultar** tudo o que o sistema guarda sobre ela, incluindo as tabelas de bibliotecas de terceiros;
- **exportar** os mesmos dados em JSON;
- **revogar** o consentimento de guardar materiais sem perder a conta;
- **excluir** a conta, o que revoga o consentimento e apaga os dados pessoais na mesma transação.

## O que já funciona

Cadastro, login, logout, verificação em duas etapas com QR Code, bloqueio por tentativas, recuperação de senha por e-mail, as telas de exercício dos direitos da LGPD, a trilha de auditoria encadeada, o filtro de sintomas com o desvio de alerta, as páginas de condição e o guardar material com consentimento por finalidade.

São **92 testes automatizados**. Para rodar todos:

```bash
python manage.py test apps
```

Os testes usam um banco SQLite temporário, em memória, então não encostam no servidor do Aiven.

Dois comandos completam a parte de auditoria:

```bash
python manage.py verificar_logs              # confere a corrente de hashes
python manage.py analisar_logs --horas 24    # resume a trilha do período
```

## O que ainda falta

Avisar quem guardou um material quando a fonte o retira ou revisa — depende de tarefa agendada e envio de e-mail. E a retenção da trilha de auditoria, hoje indefinida: apagar registro antigo quebraria a corrente do que vem depois, e resolver isso é decisão de projeto, não linha de código. As duas pendências estão registradas no [check-list](docs/checklist.md).

## Referências

- https://www.boldare.com/blog/how-to-improve-user-password-security-with-argon2/
- BIRYUKOV, A. et al. Argon2 Memory-Hard Function for Password Hashing. RFC 9106, IETF, 2021.
- M'RAIHI, D. et al. TOTP: Time-Based One-Time Password Algorithm. RFC 6238, IETF, 2011.
- NIST. Digital Identity Guidelines: Authentication and Lifecycle Management. SP 800-63B, 2017.
- NIST. Secure Hash Standard (SHS). FIPS PUB 180-4, 2015.
- KENT, K.; SOUPPAYA, M. Guide to Computer Security Log Management. NIST SP 800-92, 2006.
- ABNT NBR ISO/IEC 27002:2022, controle 8.15 (Registro de eventos).
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
