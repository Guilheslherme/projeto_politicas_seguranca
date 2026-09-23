"""Carga dos dez sintomas do escopo do trabalho.

Entra como migração, e não como comando, porque o build.sh roda "migrate" a
cada implantação: assim os sintomas chegam ao servidor sozinhos, sem ninguém
precisar lembrar de executar nada, e ficam versionados junto com o schema.
"""

from django.db import migrations

# (slug, nome, é sinal de alerta?)
#
# O escopo é fechado: seis sintomas comuns e quatro sinais de alerta. Os quatro
# últimos são o que faz a tela de resultado parar e mandar procurar atendimento,
# em vez de listar condição nenhuma.
#
# O slug vai sem acento porque ele aparece na URL; o nome vai com, porque ele
# aparece na tela.
SINTOMAS = [
    ("febre", "Febre", False),
    ("dor-de-cabeca", "Dor de cabeça", False),
    ("tosse", "Tosse", False),
    ("dor-de-garganta", "Dor de garganta", False),
    ("cansaco", "Cansaço", False),
    ("dor-abdominal", "Dor abdominal", False),
    ("dor-no-peito", "Dor no peito", True),
    ("falta-de-ar", "Falta de ar", True),
    ("fraqueza-subita-em-um-lado-do-corpo", "Fraqueza súbita em um lado do corpo", True),
    ("dor-de-cabeca-subita-e-muito-forte", "Dor de cabeça que começou de repente e muito forte", True),
]


def carregar(apps, schema_editor):
    """Cria os dez sintomas, sem tocar no que já existe.

    get_or_create procura pelo slug e só cria quando não acha. Se alguém tiver
    ajustado o nome de um sintoma pelo painel, o ajuste fica de pé.
    """
    Sintoma = apps.get_model("catalog", "Sintoma")
    for slug, nome, alerta in SINTOMAS:
        Sintoma.objects.get_or_create(
            slug=slug,
            defaults={"nome": nome, "alerta": alerta},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        # O caminho de volta não apaga nada, de propósito. Apagar um sintoma
        # levaria junto, em cascata, todas as associações que apontam para ele —
        # e associação é conteúdo cadastrado a mão, lendo a fonte. Desfazer uma
        # migração não pode destruir trabalho que ela nunca criou.
        migrations.RunPython(carregar, migrations.RunPython.noop),
    ]
