"""Códigos de reserva do 2FA, para quem perdeu o celular (risco R05).

Usa o StaticDevice do django-otp, que já estava instalado. Um ponto muda: o
django-otp guarda cada código em texto puro, e quem lesse o banco entraria em
qualquer conta com eles, sem precisar do celular. Aqui a tabela guarda só um
HMAC do código, e o código em si aparece uma única vez, na tela, logo depois
de gerado.
"""

import secrets

from django.conf import settings
from django.db import transaction
from django.utils.crypto import salted_hmac
from django_otp.plugins.otp_static.models import StaticDevice

NOME_DO_DISPOSITIVO = "codigos de reserva"
QUANTIDADE = 10

# 32 símbolos, sem I, O, 0 e 1, que se confundem na hora de digitar. Dez
# símbolos dão 50 bits por código, e o limite de tentativas da tela de
# verificação torna inviável adivinhar um.
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TAMANHO = 10


def _normalizar(codigo):
    return codigo.replace("-", "").replace(" ", "").upper()


def _resumo(codigo, chave=None):
    # O campo token do django-otp aceita 16 caracteres: os primeiros 64 bits
    # do HMAC-SHA256. Sem a SECRET_KEY, o resumo não ajuda a achar o código.
    return salted_hmac(
        "apps.accounts.codigos_reserva", _normalizar(codigo), secret=chave, algorithm="sha256"
    ).hexdigest()[:16]


def _resumos_aceitos(codigo):
    # Depois de uma troca da SECRET_KEY, os códigos gerados com a antiga
    # continuam valendo pelas SECRET_KEY_FALLBACKS (risco R02).
    return [_resumo(codigo)] + [_resumo(codigo, antiga) for antiga in settings.SECRET_KEY_FALLBACKS]


def _novo_codigo():
    simbolos = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO))
    return f"{simbolos[:5]}-{simbolos[5:]}"


@transaction.atomic
def gerar_codigos(user):
    """Troca os códigos da conta por novos e devolve os novos, legíveis.

    Os anteriores deixam de valer. Quem chama mostra a lista uma vez e não a
    guarda em lugar nenhum.
    """
    StaticDevice.objects.filter(user=user, name=NOME_DO_DISPOSITIVO).delete()
    device = StaticDevice.objects.create(user=user, name=NOME_DO_DISPOSITIVO, confirmed=True)

    codigos = [_novo_codigo() for _ in range(QUANTIDADE)]
    for codigo in codigos:
        device.token_set.create(token=_resumo(codigo))
    return codigos


def usar_codigo(user, codigo):
    """Confere e consome um código. Devolve o dispositivo, ou None.

    O delete é a própria conferência: se duas requisições chegarem com o mesmo
    código, só uma apaga a linha, e só ela entra.
    """
    device = StaticDevice.objects.filter(user=user, name=NOME_DO_DISPOSITIVO).first()
    if device is None:
        return None
    apagados, _ = device.token_set.filter(token__in=_resumos_aceitos(codigo)).delete()
    return device if apagados else None


def restantes(user):
    device = StaticDevice.objects.filter(user=user, name=NOME_DO_DISPOSITIVO).first()
    return device.token_set.count() if device else 0


def apagar_codigos(user):
    StaticDevice.objects.filter(user=user, name=NOME_DO_DISPOSITIVO).delete()
