"""Cifra os segredos de 2FA gravados em texto puro antes do requisito 3.4.

A partir da migração 0003, todo segredo novo já nasce cifrado. Esta migração
trata os que existiam antes, para que nenhuma conta fique para trás.
"""

from binascii import hexlify, unhexlify

from django.db import migrations, transaction

from apps.accounts.crypto import cifrar, decifrar, esta_cifrado
from apps.accounts.models import contexto_do_segredo_2fa


def cifrar_segredos(apps, schema_editor):
    TOTPDevice = apps.get_model("otp_totp", "TOTPDevice")
    alias = schema_editor.connection.alias

    # O MySQL não desfaz alterações de estrutura em caso de erro, mas desfaz
    # alterações de dados. A transação garante que ou todos os segredos são
    # cifrados, ou nenhum: não sobra banco com metade das contas em cada formato.
    with transaction.atomic(using=alias):
        for device in TOTPDevice.objects.using(alias).select_for_update():
            if esta_cifrado(device.key):
                continue
            device.key = cifrar(
                unhexlify(device.key), contexto_do_segredo_2fa(device.user_id)
            )
            device.save(update_fields=["key"])


def decifrar_segredos(apps, schema_editor):
    # Caminho de volta, para que a migração possa ser revertida sem deixar o
    # 2FA de ninguém inutilizável.
    TOTPDevice = apps.get_model("otp_totp", "TOTPDevice")
    alias = schema_editor.connection.alias

    with transaction.atomic(using=alias):
        for device in TOTPDevice.objects.using(alias).select_for_update():
            if not esta_cifrado(device.key):
                continue
            segredo = decifrar(device.key, contexto_do_segredo_2fa(device.user_id))
            device.key = hexlify(segredo).decode("ascii")
            device.save(update_fields=["key"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_encryptedtotpdevice"),
    ]

    operations = [
        migrations.RunPython(cifrar_segredos, decifrar_segredos),
    ]
