# Decisões técnicas

Documento dos requisitos 1.2 e 1.12. Cada seção registra a escolha feita, a
alternativa descartada e o motivo.

## Argon2id em vez de bcrypt ou PBKDF2

O Django aceita os três. A escolha foi o Argon2id, por três motivos.

O Argon2 venceu a Password Hashing Competition em 2015, uma competição
pública em que os candidatos foram analisados por criptógrafos independentes.
Em 2021 tornou-se recomendação formal na RFC 9106.

O diferencial em relação ao bcrypt é o consumo de memória. O bcrypt usa
aproximadamente 4 KiB por cálculo, valor que uma placa de vídeo moderna
replica milhares de vezes em paralelo. O Argon2 permite exigir dezenas de
megabytes por cálculo, o que reduz drasticamente o paralelismo possível em
hardware dedicado a quebra de senhas.

O PBKDF2, padrão do Django, é considerado o mais fraco dos três justamente
por depender apenas de iterações, sem custo de memória.

Entre as variantes, o Argon2id combina a resistência do Argon2d a ataques com
hardware especializado com a resistência do Argon2i a ataques por canal
lateral. É a variante recomendada pela RFC 9106 para hash de senhas.

## Parâmetros de custo: m = 65536 KiB, t = 3, p = 2

A RFC 9106 apresenta duas configurações recomendadas. A primeira usa 2 GiB de
memória e 1 iteração. A segunda usa 64 MiB e 3 iterações.

A primeira foi descartada porque 2 GiB por cálculo não cabe no plano de
hospedagem utilizado. A segunda foi adotada integralmente.

| Parâmetro | Valor | Função |
|---|---|---|
| `memory_cost` | 65536 KiB (64 MiB) | Custo de memória por cálculo. É o parâmetro que mais encarece ataques em GPU, que possuem muitos núcleos e pouca memória por núcleo |
| `time_cost` | 3 | Número de passagens. Compensa o custo de memória menor da segunda configuração |
| `parallelism` | 2 | Número de faixas processadas em paralelo, compatível com os núcleos disponíveis no servidor |

O consumo de 64 MiB é de memória de processamento, transitória, liberada logo
após o cálculo. No banco de dados, cada senha ocupa cerca de 100 bytes.

Os parâmetros ficam gravados na própria string do hash. Quando forem
atualizados no futuro, o Django regrava automaticamente o hash de cada usuário
no primeiro login bem-sucedido posterior à mudança, sem intervenção manual e
sem exigir troca de senha.

## Salt gerenciado pela biblioteca

O salt é gerado automaticamente pelo Argon2 a cada chamada de `set_password`,
com valor aleatório e único por senha.

A alternativa — gerar o salt manualmente — foi descartada por não trazer
ganho e por introduzir risco de erro de implementação. Geração de valores
aleatórios criptográficos é exatamente o tipo de código que não se deve
reescrever.

O salt fica armazenado junto ao hash, no mesmo campo. Isso é o esperado: o
salt não é um segredo. Sua função é garantir que senhas iguais produzam hashes
diferentes, inutilizando tabelas pré-calculadas.

## Sessão criada apenas após o segundo fator

A implementação mais comum de 2FA autentica o usuário após a senha e pede o
código em seguida. Esse desenho tem uma falha: com a sessão já criada, basta
navegar para outra URL para contornar a verificação.

Neste projeto, `django.contrib.auth.login()` só é chamado depois que o código
TOTP é validado. Entre as duas etapas, a aplicação mantém apenas três valores
na sessão anônima: o identificador do usuário, o backend de autenticação e o
horário de início.

Essa janela expira em 5 minutos. Sem o limite, uma aba deixada aberta após o
acerto da senha permaneceria válida indefinidamente.

## TOTP em vez de código por SMS ou e-mail

O TOTP, definido na RFC 6238, calcula o código localmente a partir de um
segredo compartilhado e do horário atual. O código não trafega pela rede.

O envio por SMS foi descartado por ser vulnerável a interceptação e a fraude
de troca de chip, além de gerar custo por mensagem. O envio por e-mail foi
descartado porque, se a caixa de e-mail for comprometida, o segundo fator
deixa de ser um fator independente — o e-mail já é o identificador de login.

## Expiração de sessão em 15 minutos, com renovação

O prazo é de inatividade, não de uso: `SESSION_SAVE_EVERY_REQUEST` reinicia a
contagem a cada requisição. Um usuário navegando não é desconectado.

A escolha de 15 minutos considera o cenário de computador compartilhado ou de
laboratório. Prazos maiores, como 2 horas, aumentariam a janela em que uma
máquina abandonada permanece autenticada sem ganho relevante de conforto,
já que o prazo se renova sozinho durante o uso.

A sessão também é encerrada ao fechar o navegador.

## Bloqueio por combinação de usuário e endereço de rede

O `django-axes` permite bloquear por nome de usuário, por endereço de rede ou
pela combinação dos dois. A configuração adotada é a combinação.

Bloquear apenas pelo nome de usuário criaria uma vulnerabilidade de negação de
serviço: qualquer pessoa poderia inutilizar a conta de outra errando a senha
cinco vezes. Bloquear apenas pelo endereço afetaria todos os usuários de uma
mesma rede compartilhada.

Com a combinação, o atacante bloqueia apenas o próprio ponto de origem, e o
usuário legítimo continua acessando normalmente.

O limite de 5 tentativas e o resfriamento de 5 minutos reduzem a taxa efetiva
de um ataque automatizado para cerca de 1.400 tentativas por dia, valor
irrelevante diante do espaço de senhas exigido pelos validadores.

## Modelo de usuário customizado com login por e-mail

O modelo padrão do Django usa nome de usuário. A substituição por um modelo
próprio, com o e-mail como identificador, elimina um campo que o usuário
precisaria inventar e memorizar, e que não traz informação nova — o e-mail já
é obrigatório para recuperação de senha e comunicação da conta.

Menos campos coletados também atende ao princípio da minimização previsto no
art. 6º, III da LGPD.

A troca foi feita antes da primeira migração do banco, porque alterar o modelo
de usuário depois exige recriação das tabelas.

## Configuração única, com bloco condicional de produção

A separação em arquivos distintos para desenvolvimento e produção foi
avaliada e descartada por adicionar complexidade sem benefício em um projeto
deste porte, e por dificultar o acompanhamento por parte de todos os
integrantes.

As proteções que só fazem sentido em produção — redirecionamento para HTTPS,
HSTS, cookies `Secure` e compressão de estáticos — ficam em um bloco
condicional ao final do arquivo.

O modo de depuração é desligado por padrão e só é ativado por variável de
ambiente explícita. A inversão dessa lógica é intencional: um esquecimento
resulta em produção segura, e não no contrário.

## Segredos fora do controle de versão

Chave secreta do Django, credenciais do banco e o certificado da autoridade
certificadora são lidos de variáveis de ambiente, carregadas de um arquivo
`.env` que está no `.gitignore`.

O repositório contém um `.env.example` com os nomes das variáveis e nenhum
valor real, para que um novo integrante saiba o que precisa configurar.

Em produção, as mesmas variáveis são cadastradas no painel do serviço de
hospedagem.

## Banco de dados em servidor separado, com TLS

O MySQL está hospedado no Aiven, fora da máquina que executa a aplicação.
A separação segue a prática usual de produção e garante que a indisponibilidade
da aplicação não afete os dados.

Como o tráfego entre aplicação e banco atravessa a rede pública, a conexão
exige TLS com verificação do certificado da autoridade certificadora. Sem o
certificado, a conexão não é estabelecida.

## Limitações conhecidas

Registradas aqui por decisão deliberada de transparência.

O segredo do dispositivo TOTP é armazenado sem cifra no banco de dados, que é
o comportamento padrão do `django-otp`. Um comprometimento do banco permitiria
a geração de códigos válidos, embora não revele senhas. A cifragem em repouso,
com chave mantida fora do banco, está prevista para a etapa correspondente ao
bloco 3 do check-list.

O `django-axes` mascara o identificador do usuário e o endereço de rede ao
gravar as tentativas. O comportamento favorece a privacidade, mas reduz a
utilidade da trilha para auditoria. O tratamento adequado faz parte do bloco 5.

A verificação em duas etapas é opcional. Como a plataforma não trata dados
sensíveis, a obrigatoriedade traria custo de usabilidade sem ganho
proporcional de proteção.

## Referências

- BIRYUKOV, A.; DINU, D.; KHOVRATOVICH, D.; JOSEFSSON, S. *Argon2 Memory-Hard
  Function for Password Hashing and Proof-of-Work Applications*. RFC 9106.
  IETF, 2021.
- M'RAIHI, D.; MACHANI, S.; PEI, M.; RYDELL, J. *TOTP: Time-Based One-Time
  Password Algorithm*. RFC 6238. IETF, 2011.
- NIST. *Digital Identity Guidelines: Authentication and Lifecycle Management*.
  SP 800-63B. 2017.
- OWASP. *Password Storage Cheat Sheet*.
- BRASIL. *Lei nº 13.709, de 14 de agosto de 2018*. Lei Geral de Proteção de
  Dados Pessoais.
