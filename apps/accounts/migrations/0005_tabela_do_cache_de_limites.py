"""Cria a tabela do cache em banco usado pelos limites de requisição (R03).

O Django cria essa tabela com o comando createcachetable, que o migrate não
roda. Chamá-lo daqui faz a tabela existir em toda máquina e no Render sem
mudar o build.sh. O comando só cria o que falta, então rodar de novo é seguro.
"""

from django.core.management import call_command
from django.db import migrations


def criar_tabela_do_cache(apps, schema_editor):
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_cifra_segredos_2fa_existentes"),
    ]

    operations = [
        migrations.RunPython(criar_tabela_do_cache, migrations.RunPython.noop),
    ]
