"""Backup cifrado do banco, para guardar fora do Aiven (risco R04).

O dump sai do mysqldump e é cifrado com AES-256-GCM antes de ir para o disco.
A chave do backup (BACKUP_KEY) é outra, separada da chave do 2FA: quem tiver
o arquivo e a FIELD_ENCRYPTION_KEY ainda não lê o backup.
"""

import base64
import binascii
import os
import tempfile
from contextlib import contextmanager

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Início de todo arquivo de backup: identifica o formato e a versão.
MARCA = b"HISBKP1\n"
# Dado associado do GCM: um arquivo cifrado para outro fim não passa por backup.
CONTEXTO = b"health-in-sight backup v1"
TAMANHO_DO_NONCE = 12


class BackupInvalido(Exception):
    """Arquivo que não é um backup deste projeto, alterado ou com a chave errada."""


def ler_chave(valor):
    """Converte a BACKUP_KEY (32 bytes em base64) em bytes."""
    try:
        chave = base64.urlsafe_b64decode(valor or "")
    except (binascii.Error, ValueError):
        chave = b""
    if len(chave) != 32:
        raise BackupInvalido(
            "BACKUP_KEY ausente ou invalida: precisa ter 32 bytes em base64. Gere com: "
            'python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"'
        )
    return chave


def cifrar_backup(dados, chave):
    nonce = os.urandom(TAMANHO_DO_NONCE)
    return MARCA + nonce + AESGCM(chave).encrypt(nonce, dados, CONTEXTO)


def decifrar_backup(conteudo, chave):
    if not conteudo.startswith(MARCA):
        raise BackupInvalido("o arquivo nao e um backup do Health In Sight")
    resto = conteudo[len(MARCA):]
    nonce, cifrado = resto[:TAMANHO_DO_NONCE], resto[TAMANHO_DO_NONCE:]
    try:
        return AESGCM(chave).decrypt(nonce, cifrado, CONTEXTO)
    except InvalidTag as erro:
        raise BackupInvalido("chave errada ou arquivo alterado") from erro


def _aspas(valor):
    # Valores do arquivo de opções do MySQL vão entre aspas, com \ e " escapados.
    return '"' + str(valor).replace("\\", "\\\\").replace('"', '\\"') + '"'


@contextmanager
def arquivo_de_opcoes(banco):
    """Arquivo temporário com usuário e senha para o mysqldump.

    A senha não vai na linha de comando, onde qualquer processo da máquina
    poderia vê-la, nem em variável de ambiente. O arquivo é apagado ao final.
    """
    descritor, caminho = tempfile.mkstemp(suffix=".cnf")
    try:
        with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
            arquivo.write("[client]\n")
            arquivo.write(f"user={_aspas(banco['USER'])}\n")
            arquivo.write(f"password={_aspas(banco['PASSWORD'])}\n")
        yield caminho
    finally:
        os.remove(caminho)


def argumentos_do_mysqldump(banco, opcoes, mysqldump="mysqldump"):
    """Linha de comando do mysqldump para a configuração de banco do Django."""
    argumentos = [
        mysqldump,
        f"--defaults-extra-file={opcoes}",
        f"--host={banco['HOST']}",
        f"--port={banco['PORT']}",
        # Uma foto consistente sem travar as tabelas do site enquanto o dump roda.
        "--single-transaction",
        # Sem isto o dump traz os identificadores de transação do Aiven, que
        # impedem restaurar num MySQL comum.
        "--set-gtid-purged=OFF",
        # O usuário do Aiven não tem o privilégio PROCESS, exigido para isso.
        "--no-tablespaces",
        "--routines",
    ]
    tls = banco.get("OPTIONS", {})
    if tls.get("ssl", {}).get("ca"):
        argumentos += [f"--ssl-ca={tls['ssl']['ca']}", f"--ssl-mode={tls.get('ssl_mode', 'VERIFY_CA')}"]
    argumentos.append(banco["NAME"])
    return argumentos
