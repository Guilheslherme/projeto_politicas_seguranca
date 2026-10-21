# Operação e continuidade

Passo a passo do que fica fora do código: troca de segredos, rede do banco,
pipeline e continuidade. Cada seção diz qual risco da avaliação ela trata.

## 1. Troca dos segredos (R02)

Os segredos de produção ficaram em várias máquinas, então todos são trocados.
O código aceita a chave antiga durante a troca, para nada se perder.

### Senha do banco (Aiven)

1. No console do Aiven, abra o serviço MySQL e vá em **Users**.
2. No usuário `avnadmin`, clique em **Reset password** e copie a senha nova.
3. No Render, em **Environment**, troque `DB_PASSWORD` pela senha nova e salve.
   O Render faz o deploy de novo sozinho.
4. Quem usa o Aiven localmente troca o `DB_PASSWORD` no próprio `.env`.

### DJANGO_SECRET_KEY

1. Gere uma chave nova:
   `python -c "import secrets; print(secrets.token_urlsafe(50))"`
2. No Render, copie o valor atual de `DJANGO_SECRET_KEY` para
   `DJANGO_SECRET_KEY_FALLBACKS` e ponha a chave nova em `DJANGO_SECRET_KEY`.
3. As sessões abertas e os códigos de reserva do 2FA continuam valendo pela
   chave antiga. Depois de uma semana, apague `DJANGO_SECRET_KEY_FALLBACKS`.

### FIELD_ENCRYPTION_KEY (chave AES do 2FA)

1. Gere uma chave nova:
   `python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
2. No Render, copie o valor atual de `FIELD_ENCRYPTION_KEY` para
   `FIELD_ENCRYPTION_OLD_KEYS` e ponha a chave nova em `FIELD_ENCRYPTION_KEY`.
3. A cada login, o segredo do 2FA daquela conta é cifrado de novo com a chave
   nova. Só apague `FIELD_ENCRYPTION_OLD_KEYS` quando todas as contas com 2FA
   tiverem entrado pelo menos uma vez; antes disso, essas contas não
   conseguiriam entrar.
4. Guarde a chave nova no cofre do grupo (seção 4.4). Sem ela, nenhum segredo
   do 2FA é lido, nem a partir de um backup.

### Chave do Brevo

1. No painel do Brevo, em **SMTP & API → API Keys**, crie uma chave nova.
2. No Render, troque `BREVO_API_KEY` pela nova e salve.
3. Volte ao Brevo e apague a chave antiga.

## 2. Banco aceitando só o Render (R02)

1. No Render, abra o serviço e clique em **Connect → Outbound**. Copie os
   endereços listados.
2. No Aiven, no serviço MySQL, vá em **Overview → Allowed IP addresses**,
   apague `0.0.0.0/0` e adicione os endereços do Render.

Atenção: depois disso, só o Render conecta no banco. Quem roda o projeto
localmente apontando para o Aiven passa a receber erro de conexão. Para
continuar usando o Aiven na própria máquina, adicione também o IP da sua
internet na lista (ele muda de tempos em tempos) ou use um MySQL local.

## 3. Pipeline e deploy (R11)

O arquivo `.github/workflows/devsecops-pipeline.yml` já prende as actions pelo
SHA do commit e tem o job **🧪 Testes e check --deploy**, que roda os testes
com as configurações de produção (`DJANGO_DEBUG=0`).

1. **Deploy só depois do CI.** No Render, em **Settings → Build & Deploy →
   Auto-Deploy**, escolha **After CI Checks Pass**. Funciona também com push
   direto na `main`.
2. **Proteger a `main` (opcional).** No GitHub, em **Settings → Branches → Add
   branch ruleset**, aplique à `main` e marque **Require status checks to
   pass**, escolhendo o job de testes. Com isso, as mudanças passam a entrar
   por pull request: o push direto na `main` é recusado.

Ao atualizar uma action, troque o SHA e a versão do comentário juntos, pegando
o SHA na página de releases da própria action.

## 4. Continuidade (R04)

### 4.1 Metas

- **RPO de 7 dias**: no pior caso, perde-se o que foi gravado desde o último
  backup semanal. Para um projeto acadêmico sem usuários pagantes e no plano
  gratuito, que não garante backup, é o que dá para manter à mão.
- **RTO de 4 horas**: tempo para criar um MySQL novo no Aiven, restaurar o
  backup e trocar as variáveis no Render.

### 4.2 Fazer o backup

Toda segunda-feira e antes de qualquer deploy que tenha migração nova:

1. Tenha a `BACKUP_KEY` no ambiente (ela fica no cofre do grupo). Na primeira
   vez, gere uma com o mesmo comando da `FIELD_ENCRYPTION_KEY` e guarde no cofre.
2. Rode, com o `.env` apontando para o banco de produção:
   `python manage.py backup_cifrado --mysqldump "<caminho do mysqldump>"`
   No WAMP, o mysqldump fica em `F:\Programas\wamp\bin\mysql\mysql8.3.0\bin\mysqldump.exe`.
3. O arquivo sai em `backups/` (que não vai para o Git), já cifrado. Envie-o
   para a pasta do grupo no Google Drive e apague a cópia local.

O backup confere o certificado e o nome do servidor do banco, como o site.

### 4.3 Teste de restauração

Uma vez por mês, ou depois de mudar o backup:

1. Ligue o WAMP e crie um banco vazio `restauracao` no phpMyAdmin.
2. Baixe o backup mais recente e decifre:
   `python manage.py restaurar_backup backups/<arquivo>.sql.enc`
3. Importe no MySQL local:
   `F:\Programas\wamp\bin\mysql\mysql8.3.0\bin\mysql.exe -u root restauracao < backups/<arquivo>.sql`
4. Aponte o projeto para esse banco só no terminal do teste
   (`DB_HOST=127.0.0.1`, `DB_NAME=restauracao`, `DB_USER=root`,
   `DB_PASSWORD=` vazio, `DB_SSL_CA=` vazio), rode
   `python manage.py verificar_logs` e entre no site com uma conta com 2FA.
5. Anote a data e quanto tempo levou, apague o `.sql` e o banco `restauracao`.
   O `.sql` tem dados pessoais em texto puro.

### 4.4 Cofre do grupo

A `FIELD_ENCRYPTION_KEY` e a `BACKUP_KEY` ficam num cofre compartilhado de
senhas (por exemplo, uma organização gratuita do Bitwarden), nunca na mesma
pasta dos backups. Sem a `FIELD_ENCRYPTION_KEY`, o backup volta, mas nenhum
2FA funciona; sem a `BACKUP_KEY`, o backup não abre.

### 4.5 Monitor de disponibilidade

A rota `/saude/` responde `{"status": "ok"}` quando o site e o banco estão no
ar, e 503 quando o banco não responde. Ela não mostra mais nada.

1. Crie uma conta gratuita no UptimeRobot.
2. Adicione um monitor **HTTP(s)** para `https://<endereço do site>/saude/`,
   de 5 em 5 minutos, com alerta para o e-mail do grupo.
3. No Render, em **Settings → Health Check Path**, coloque `/saude/`.
