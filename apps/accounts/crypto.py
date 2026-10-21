"""Criptografia (requisitos 3.4 a 3.6)."""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

# Marca gravada no início de todo valor cifrado. Serve para duas coisas: dizer
# a quem olha o banco qual algoritmo foi usado, do mesmo jeito que o hash da
# senha começa com "argon2$", e permitir trocar de algoritmo no futuro sem
# ambiguidade sobre como ler cada valor já gravado.
PREFIXO = "aes256gcm$"

# 96 bits, o tamanho de nonce recomendado para o GCM pela NIST SP 800-38D.
TAMANHO_DO_NONCE = 12


def id_da_chave(chave):
    """Identificador curto da chave, gravado junto do valor cifrado (R02).

    Permite trocar a chave sem perder o que já foi gravado: cada valor diz com
    qual chave foi cifrado, e a leitura escolhe a chave certa. São os primeiros
    4 caracteres do SHA-256 da chave, que não ajudam a descobrir a chave. Só 4
    porque o campo do django-otp aceita 80 caracteres e o valor cifrado do
    segredo já ocupa 74. O settings recusa uma chave antiga com o mesmo id da
    atual, para a escolha nunca ficar ambígua.
    """
    return hashlib.sha256(chave).hexdigest()[:4]


def _chaves():
    """A chave atual primeiro, depois as antigas que ainda podem ser lidas."""
    return [settings.FIELD_ENCRYPTION_KEY, *getattr(settings, "FIELD_ENCRYPTION_OLD_KEYS", [])]


class FalhaNaDecifragem(Exception):
    """O valor não pôde ser decifrado.

    Acontece quando a chave está errada, quando o texto cifrado foi alterado ou
    quando ele foi copiado de outro contexto. O GCM não distingue os três casos
    de propósito: qualquer detalhe a mais ajudaria quem está tentando forjar um
    valor.
    """


def esta_cifrado(valor):
    """Diz se o valor já está no formato cifrado deste módulo."""
    return isinstance(valor, str) and valor.startswith(PREFIXO)


def cifrar(dados, contexto):
    """Cifra bytes e devolve texto pronto para gravar em um campo do banco.

    O contexto não é secreto e não vai no resultado, mas entra na autenticação
    do GCM. Decifrar com um contexto diferente falha, então um valor cifrado
    para uma conta não pode ser copiado para a linha de outra conta.
    """
    # Um nonce novo e aleatório a cada cifragem. No GCM, repetir o nonce com a
    # mesma chave é catastrófico: expõe a diferença entre os textos e permite
    # forjar a autenticação. Por isso ele nunca é derivado de nada previsível.
    nonce = os.urandom(TAMANHO_DO_NONCE)
    chave = settings.FIELD_ENCRYPTION_KEY
    cifrado = AESGCM(chave).encrypt(nonce, dados, contexto.encode("utf-8"))
    # O nonce precisa ser guardado junto para permitir decifrar, e pode ficar
    # às claras: a segurança depende da chave, não do nonce.
    corpo = base64.urlsafe_b64encode(nonce + cifrado).decode("ascii").rstrip("=")
    # Formato: aes256gcm$<id da chave>$<nonce e texto cifrado>.
    return f"{PREFIXO}{id_da_chave(chave)}${corpo}"


def _partes(valor):
    """Separa o id da chave e o corpo. Valores gravados antes da troca de
    chave não têm id: aes256gcm$<corpo>."""
    resto = valor[len(PREFIXO):]
    # O base64 urlsafe não usa "$", então o separador não se confunde.
    if "$" in resto:
        id_gravado, corpo = resto.split("$", 1)
        return id_gravado, corpo
    return None, resto


def precisa_recifrar(valor):
    """Diz se o valor foi cifrado com outra chave que não a atual."""
    id_gravado, _ = _partes(valor)
    return id_gravado != id_da_chave(settings.FIELD_ENCRYPTION_KEY)


def decifrar(valor, contexto):
    """Devolve os bytes originais de um valor produzido por cifrar()."""
    if not esta_cifrado(valor):
        # Nada em texto puro é aceito como se fosse cifrado. Aceitar seria abrir
        # uma porta para quem conseguisse escrever no banco trocar o valor
        # cifrado por um conhecido.
        raise FalhaNaDecifragem("o valor nao esta no formato cifrado")

    id_gravado, corpo = _partes(valor)
    # O base64 perde o preenchimento "=" na gravação; aqui ele é recomposto.
    bruto = base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4))
    nonce, cifrado = bruto[:TAMANHO_DO_NONCE], bruto[TAMANHO_DO_NONCE:]

    # Com o id, só a chave certa é tentada. Sem ele (valor antigo), cada chave
    # conhecida é tentada, a atual primeiro.
    candidatas = [c for c in _chaves() if id_gravado in (None, id_da_chave(c))]
    for chave in candidatas:
        try:
            # O GCM confere a etiqueta de autenticação antes de devolver
            # qualquer byte. Um valor alterado no banco não é decifrado "quase
            # certo": é recusado inteiro.
            return AESGCM(chave).decrypt(nonce, cifrado, contexto.encode("utf-8"))
        except InvalidTag:
            continue
    raise FalhaNaDecifragem("chave, contexto ou valor cifrado nao conferem")
