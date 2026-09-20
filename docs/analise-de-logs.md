# Análise de logs

Este documento explica a trilha de auditoria da autenticação do Health In Sight:
o que ela grava, como a gente lê, como sabemos que ela não foi alterada e o que
essa proteção **não** cobre.

Atende aos requisitos 5.1 a 5.4. O check-list dos itens está em
[checklist.md](checklist.md) e as capturas de tela em
[evidencias.md](evidencias.md).

Código: `apps/audit/models.py` (modelo `AuthEvent`), `apps/audit/signals.py`
(gravação) e `apps/audit/management/commands/` (os dois comandos).

---

## 1. O que a trilha grava

Cada vez que alguém entra, erra a senha, sai, usa o segundo fator, cria ou
exclui uma conta, o sistema grava uma linha na tabela `audit_authevent`.

Uma linha tem: o evento, a data e a hora, o identificador da conta, o endereço
de rede, o navegador, um detalhe curto e dois campos de hash, que são o assunto
da seção 5.

O que **não** entra: o e-mail digitado na tentativa de login, a senha e o código
do segundo fator. O e-mail é usado só para descobrir de qual conta se trata, e
descartado em seguida. Um log de auditoria é lido por mais gente e guardado por
mais tempo que a tabela de usuários; repetir o endereço aqui espalharia o dado
sem necessidade, e o número da conta já responde o que a auditoria precisa
saber.

### Dicionário dos eventos

| Evento | O que significa | Onde é gravado |
|---|---|---|
| `LOGIN_OK` | Uma sessão foi criada. A senha estava certa e, se a conta tem segundo fator, o código também | Sinal `user_logged_in` do Django |
| `LOGIN_FALHOU` | Senha recusada. Se o e-mail digitado tem conta, o registro aponta para ela; se não tem, fica sem vínculo | Sinal `user_login_failed` |
| `LOGOUT` | Fim da sessão, por clique em "Sair" ou pela exclusão da conta | Sinal `user_logged_out` |
| `OTP_OK` | Código do aplicativo autenticador aceito | `otp_verify`, em `apps/accounts/views.py` |
| `OTP_FALHOU` | Código recusado. A senha já tinha sido aceita: quem falhou foi a segunda etapa | `otp_verify` |
| `OTP_ATIVADO` | A pessoa ligou a verificação em duas etapas | `otp_setup` |
| `OTP_DESATIVADO` | A pessoa desligou a verificação em duas etapas | `otp_disable` |
| `CONTA_BLOQUEADA` | O django-axes travou a conta depois de 5 senhas erradas | Sinal `user_locked_out`, do django-axes |
| `CADASTRO` | Conta criada | `register_view` |
| `CONTA_EXCLUIDA` | A pessoa pediu a exclusão da própria conta | `delete_account`, em `apps/privacy/views.py` |

Os quatro eventos do segundo fator são gravados por chamada direta na view
porque o django-otp não dispara sinal nenhum quando aceita ou recusa um código.

### Por que por sinal, e não dentro da tela de login

O login acontece em mais de um lugar. Além da tela do projeto, existe a tela de
login do painel administrativo do Django, que é por onde entra quem administra o
sistema. Se a gravação ficasse só na view do projeto, justamente esses acessos
não entrariam na trilha — o buraco ficaria na porta mais sensível.

Ligando nos sinais do Django, qualquer caminho que crie uma sessão passa pela
gravação.

---

## 2. Duas tabelas, dois papéis

O projeto tem dois registros de tentativas de login, e eles não são repetição um
do outro. Fazem perguntas diferentes:

| | Tabela do django-axes (`axes_accessattempt`) | Nossa trilha (`audit_authevent`) |
|---|---|---|
| Responde | "esta pessoa pode tentar de novo agora?" | "o que aconteceu nesta conta?" |
| Quando serve | no instante da tentativa | depois, na investigação |
| Precisa esquecer? | **sim** | **não** |

A tabela do axes é um contador com prazo. Ela conta as falhas recentes daquela
conta naquele endereço e, passados os 5 minutos de bloqueio, zera. Ela **tem**
que esquecer: se guardasse para sempre, a quinta falha de hoje somaria com a de
um ano atrás e o bloqueio nunca mais sairia.

A nossa trilha é o contrário. Ela **não pode** esquecer, senão deixa de ser
trilha. É nela que se procura, semanas depois, se aquela conta já vinha sendo
tentada antes do incidente.

Por isso a exclusão de conta apaga os registros do axes (são um contador
identificado pelo e-mail, sem valor histórico) e mantém a trilha, com o vínculo
desfeito. Isso está detalhado na seção 6.

---

## 3. Como a gente lê a trilha

```
python manage.py analisar_logs            # últimas 24 horas
python manage.py analisar_logs --horas 6
```

O comando só lê o banco, e imprime cinco coisas:

1. **Eventos por tipo**, do mais frequente para o menos frequente. É o retrato
   geral do período.
2. **Os 5 endereços com mais senha inválida.** Muitas falhas vindas do mesmo
   endereço é o padrão de quem está tentando adivinhar senha.
3. **As 5 contas mais visadas**, agrupadas pelo identificador da conta.
4. **Tentativas em endereços sem conta no sistema**, contadas à parte.
5. **A proporção entre falha e sucesso**, com alerta acima de 0,30.

### Por que 3 e 4 são listas separadas

Porque contam histórias diferentes.

Insistir numa conta que existe é ataque de senha: alguém escolheu um alvo e está
tentando entrar nele. Espalhar tentativas por endereços que não existem é
reconhecimento: alguém está descobrindo quem tem cadastro aqui, para atacar
depois. Somados num número só, os dois padrões viram "muitas falhas de login" e
a diferença desaparece.

O agrupamento da lista 3 é pelo `usuario_ref`, o número selado da conta, e não
pelo vínculo com a tabela de usuários. O motivo é prático: o vínculo vira nulo
quando a conta é excluída. Se a contagem fosse por ele, os eventos de contas
excluídas cairiam no mesmo balde das tentativas em endereços que nunca
existiram, porque os dois ficam com vínculo nulo. São coisas diferentes.

### Sobre o limiar de 0,30

O comando avisa quando há mais de 0,30 falha para cada login concluído — mais ou
menos uma senha errada a cada três entradas.

**Esse número é escolha nossa, não padrão de mercado.** A gente partiu da ideia
de que errar a senha de vez em quando é normal, errar um terço das vezes já é
muito, e arredondou. Ele serve para separar um dia comum de um dia estranho
neste sistema, e precisaria ser recalibrado depois de alguns meses de uso real,
olhando os números que aparecem de verdade.

As duas pontas da conta são da mesma natureza: senhas recusadas de um lado,
sessões criadas do outro. Dividir as falhas pelo total de eventos daria um
número menor e sem significado, porque o total inclui logout, cadastro e segundo
fator, que não são tentativas de entrar.

### Leitura de uma execução real

<!--
  COLAR AQUI a saída de `python manage.py analisar_logs`, executada depois dos
  testes pelo navegador, e escrever embaixo o que os números mostram.
-->

_(a preencher com a saída da execução feita durante os testes pelo navegador)_

O que olhar nessa saída, quando ela estiver aqui:

- Se as falhas se concentram em **um endereço** e em **uma conta**, foi a nossa
  própria demonstração do bloqueio: cinco senhas erradas de propósito na mesma
  conta.
- O `CONTA_BLOQUEADA` logo depois da quinta falha mostra o django-axes agindo.
- `LOGIN_OK` de outra conta, no mesmo endereço e no mesmo minuto, é a prova de
  que o bloqueio pegou a combinação de conta e endereço, e não o endereço
  inteiro.
- Uma proporção alta num período de teste é esperada: a gente errou senha de
  propósito. O alerta serve para o dia em que ninguém estiver testando.

---

## 4. Como a trilha é protegida (requisito 5.3)

Três camadas, da mais fraca para a mais forte:

**No painel administrativo**, a trilha é somente leitura. `AuthEventAdmin`, em
`apps/audit/admin.py`, devolve `False` nas três permissões de criar, alterar e
excluir, inclusive para o superusuário. Não existe botão de salvar nem de
apagar.

**No código da aplicação**, não existe nenhuma rotina que altere um registro
depois de gravado. Não é esquecimento: é decisão. Se a aplicação soubesse
recalcular hashes em lote, essa rotina seria a ferramenta pronta para o ataque
que este requisito deveria detectar.

**No conteúdo dos registros**, cada linha carrega o hash da anterior. É disso
que trata a seção seguinte.

---

## 5. Como sabemos que a trilha não foi alterada

Hash é um resumo de tamanho fixo calculado a partir de um texto. Mudar uma letra
do texto muda o resumo inteiro, e não dá para voltar do resumo ao texto. A gente
usa SHA-256.

Cada registro guarda dois hashes:

- `hash_anterior`: o resumo do registro que veio antes dele;
- `hash_atual`: o resumo do próprio conteúdo, **incluindo** o `hash_anterior`.

Como o resumo de cada linha entra no cálculo da linha seguinte, as linhas ficam
amarradas em corrente. O primeiro registro de todos aponta para um valor fixo e
conhecido, 64 zeros, que a gente chama de gênese: é como se sabe onde a corrente
começa.

O que entra no cálculo, nesta ordem exata: hash anterior, evento, identificador
da conta, endereço de rede, navegador, detalhe e data. A ordem faz parte do
formato — mudá-la depois invalidaria todos os hashes já gravados.

### O comando de conferência

```
python manage.py verificar_logs
```

Ele percorre os registros do mais antigo para o mais novo e, em cada um, faz
duas perguntas:

1. O `hash_anterior` deste registro é o `hash_atual` do registro anterior?
2. Recalculando o resumo do conteúdo desta linha, dá o `hash_atual` gravado?

Se as duas respostas forem sim até o fim, a saída é `Cadeia integra: N registros
verificados`. Se alguma falhar, o comando mostra o id do registro, a data, e
qual das duas perguntas deu errado — elo quebrado ou conteúdo alterado — e
termina com erro.

Esse comando também só lê. Ele não conserta nada, pelo motivo já dito.

### O que essa proteção cobre

Alterar ou apagar um registro do meio da trilha. Se alguém editar o IP de um
login no banco, o resumo recalculado daquela linha não bate mais com o gravado.
Se alguém apagar uma linha, a linha seguinte passa a apontar para um resumo que
não existe mais. Nos dois casos o comando diz exatamente onde a conta parou de
fechar.

### O que essa proteção NÃO cobre

Três limites, e é importante que estejam escritos:

**Apagar os últimos registros não é detectado.** A cadeia não guarda em lugar
nenhum quantos registros deveriam existir. Se alguém apagar as dez últimas
linhas, as que sobraram continuam batendo perfeitamente entre si, e o comando
diz "cadeia íntegra". É o furo mais sério da nossa solução, e quem quisesse
esconder uma invasão recente faria exatamente isso.

A gente reduz um pouco esse furo ancorando o fim da cadeia em
[evidencias.md](evidencias.md): a cada conferência, anota ali a data, quantos
registros existiam e o hash do último. O arquivo fica no Git, e o Git guarda a
data do commit. Se a trilha aparecer depois com menos registros do que está
escrito lá, alguém apagou do fim. Isso é uma âncora, não uma solução: só cobre
até a última vez que a gente anotou, e depende de a gente lembrar de anotar.

**Quem tem o banco e o código refaz tudo.** O cálculo do hash está em
`apps/audit/models.py`, num repositório público. Quem tiver acesso de escrita ao
banco pode alterar um registro antigo e recalcular a corrente inteira a partir
dali. O resultado passaria na conferência. Nossa proteção é contra alteração
pontual e contra o descuido, não contra quem controla o servidor.

**Quem controla o servidor pode não gravar.** A trilha é escrita pela própria
aplicação. Se alguém invadir o servidor, o evento simplesmente não é registrado,
e um evento que nunca existiu não quebra cadeia nenhuma.

### O que resolveria de verdade

Três caminhos conhecidos, nenhum deles cabia neste projeto:

1. **Mandar o log para fora, em tempo real**, para um servidor de logs separado.
   Quem invade o sistema não alcança a cópia de lá. Exigiria um segundo
   servidor, que o plano gratuito do Render não comporta.
2. **Armazenamento que só aceita escrita** (WORM: grava uma vez, nunca altera).
   O próprio banco recusaria o `UPDATE`. Exigiria serviço pago.
3. **Assinar cada registro com uma chave privada guardada fora do servidor.**
   Aí nem quem tem o banco consegue forjar linha nova. Exigiria gerenciar chave
   fora da aplicação, o que é um projeto por si só.

A gente escolheu a corrente de hashes porque é a única das quatro que funciona
com um banco só, sem custo e sem serviço externo — e porque ela realmente pega o
caso mais provável num trabalho como este: alguém com acesso ao painel ou ao
banco mudando um registro pontual.

---

## 6. Exclusão de conta e integridade da trilha

Quando a pessoa exclui a conta, o vínculo dos eventos com a tabela de usuários
vira nulo. Mas o número da conta continua gravado num campo separado,
`usuario_ref`, que é o que entra no hash.

**Por que não usar o vínculo no hash:** porque ele muda sozinho. Na exclusão, o
Django troca o vínculo por nulo. Se esse campo entrasse no cálculo, o conteúdo
de registros antigos mudaria sem que ninguém adulterasse nada, e a cadeia
inteira passaria a acusar adulteração numa exclusão de conta perfeitamente
legítima.

**Por que não recalcular a cadeia na hora da exclusão**, que seria a outra
saída: porque se a aplicação sabe reselar, a aplicação sabe reescrever. Existiria
no código uma rotina pronta que recalcula hashes em lote — o ataque que o
requisito 5.3 deveria detectar, entregue de bandeja.

**O limite disso, em português claro:** depois que a conta é apagada, o número
não leva a pessoa nenhuma, mas ainda junta os eventos dela entre si. Dá para
dizer "esta conta, que já não existe, teve 40 falhas de login". Não dá para
dizer de quem era. Isso é pseudonimização, não anonimização: separa a trilha da
identidade, mas não desfaz os grupos.

**A ordem das operações importa, e já quebrou uma vez.** A exclusão faz, nesta
ordem: registra `CONTA_EXCLUIDA`, encerra a sessão, apaga os dados. Numa versão
anterior a sessão era encerrada por último, depois do apagamento, e o evento
`LOGOUT` se perdia: o objeto da pessoa já estava sem chave primária, o Django
recusava gravar o vínculo, e o erro só aparecia para quem fosse ler a saída do
servidor. Os testes passavam. Hoje existem dois testes em `apps/audit/tests.py`
cuidando disso — um confere que os dois eventos foram gravados com o número da
conta, e o outro falha se aparecer qualquer linha de erro na saída durante a
exclusão.

**Uma tensão que fica em aberto:** o IP e o navegador dos eventos de uma conta
excluída continuam na trilha, porque entram no hash e apagá-los quebraria a
cadeia. Na trilha de recuperação de senha, que não é encadeada, esses campos são
apagados. É uma diferença real entre os dois registros, e ela é consequência
direta da escolha de encadear. O que resolveria o caso é a retenção, abaixo:
apagar registros por idade, e não por pessoa.

---

## 7. Retenção: hoje indefinida

**Hoje a trilha não é apagada nunca.** Não existe prazo configurado nem rotina de
limpeza. Escrever isso é mais honesto do que deixar o item em branco: indefinido
é uma resposta, ausência de resposta é um buraco.

É uma pendência, e ela tem uma dificuldade própria que não é preguiça nossa:
**apagar registro antigo quebra a cadeia do que vem depois.** Se a gente apagar
os eventos de janeiro, o primeiro evento de fevereiro passa a apontar para um
hash que não existe mais, e a conferência acusa adulteração para sempre.

Sair disso exige uma decisão de projeto, não uma linha de código. Os caminhos que
a gente enxerga:

- **Reancorar depois de limpar:** ao apagar um trecho antigo, gravar um registro
  de fechamento que diga "daqui para trás foi apagado em tal data, o último hash
  era este". A corrente recomeça dali. Mas isso reintroduz no código uma rotina
  que mexe na cadeia, que é justamente o que a gente evitou.
- **Arquivar antes de apagar:** exportar o trecho antigo com os hashes, guardar
  fora, e só então apagar. Depende de ter onde guardar fora.

Para o tamanho deste projeto, a retenção indefinida não é problema prático — a
trilha tem poucas centenas de linhas. Num sistema de verdade seria, e por isso
fica registrado aqui como decisão pendente.

---

## 8. Um achado: o que a configuração dizia e o que o banco mostrava

Vale registrar como este bloco começou, porque foi a consulta ao banco que
mostrou o problema, e não a leitura do código.

O `config/settings.py` configura o bloqueio por força bruta assim:

```python
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
```

Isso deveria significar: bloqueia a combinação de conta e endereço de rede. E a
nossa documentação afirmava isso desde o bloco 1.

Ao consultar a tabela `axes_accessattempt` depois de errar a senha duas vezes de
propósito, a coluna `username` estava **nula**. Na prática a combinação era
(nulo, endereço), ou seja, **o bloqueio era só por IP**.

A causa: o django-axes procura o nome da conta nos dados enviados pelo
formulário usando uma chave configurável. Sem essa configuração, o padrão do
pacote (django-axes 8.3.1, arquivo `axes/conf.py`) é o campo identificador do
modelo de usuário, que aqui é `email`. Só que o formulário de login é o
`AuthenticationForm` do Django, cujo campo se chama `username` mesmo contendo um
e-mail. O axes procurava `email`, não achava, e gravava a tentativa sem
identificar a conta.

A correção é uma linha:

```python
AXES_USERNAME_FORM_FIELD = "username"
```

Duas consequências, além do bloqueio voltar a funcionar como estava escrito:

- O bloqueio deixou de ser por endereço. Antes, cinco erros de uma pessoa
  travavam todo mundo que estivesse saindo pelo mesmo endereço — uma sala de
  aula, um escritório, uma casa.
- O evento `CONTA_BLOQUEADA` da nossa trilha passou a saber de qual conta se
  trata. Sem a correção, ele seria gravado sem vínculo nenhum e a lista de
  "contas mais visadas" nunca encheria.

A lição que a gente tira: configuração que parece certa lida no arquivo pode
estar errada no banco. Conferir o dado gravado é diferente de conferir o código.

---

## Referências

- ABNT NBR ISO/IEC 27002:2022, controle 8.15 (Registro de eventos), que trata do
  registro de atividades e da proteção dos registros contra alteração e acesso
  indevido.
- KENT, K.; SOUPPAYA, M. *Guide to Computer Security Log Management*. NIST
  Special Publication 800-92. Gaithersburg: NIST, 2006.
- NIST. *Secure Hash Standard (SHS)*. FIPS PUB 180-4. Gaithersburg: NIST, 2015.
  Define o SHA-256 usado no encadeamento.
- BRASIL. *Lei nº 13.709, de 14 de agosto de 2018* (LGPD), arts. 16, 37 e 46.
