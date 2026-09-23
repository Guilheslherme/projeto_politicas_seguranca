"""Acervo inicial: quatro condições, cinco materiais e as associações entre eles.

Todo o conteúdo abaixo foi lido nas páginas das fontes, uma a uma, e cada
associação só existe porque a própria fonte afirma aquele sintoma para aquela
condição. Nada aqui é resumo de cabeça nem dedução nossa.

O que a fonte NÃO diz também está respeitado. Dois exemplos:

- a página da dengue cita "dor na barriga intensa", mas como sinal de alarme da
  dengue grave, e não como sintoma comum. Por isso não existe associação entre
  dor abdominal e dengue aqui;
- a página da geo-helmintíase cita "fraqueza", que não é a mesma palavra que
  "cansaço". Na dúvida, a associação ficou de fora.

Os resumos e os textos de "quando procurar atendimento" são escritos por nós, a
partir do que a fonte diz, e não copiados: o portal guarda título, resumo e
link, nunca o conteúdo da fonte.

Nenhuma destas páginas exibia data de publicação quando foram consultadas, em
22/09/2026, então publicado_em fica em branco. É a resposta honesta: inventar
uma data seria forjar a procedência.
"""

from django.db import migrations

CONDICOES = [
    (
        "dengue",
        "Dengue",
        "Doença causada por um vírus transmitido pela picada do mosquito Aedes "
        "aegypti. A febre costuma começar de repente e durar de dois a sete dias.",
        "Febre de início repentino, entre 39°C e 40°C, com pelo menos duas "
        "manifestações como dor de cabeça, prostração, dor muscular ou nas "
        "articulações, pede atendimento imediato. Entre o terceiro e o sétimo "
        "dia, quando a febre cede, qualquer sangramento ou sinal de alarme — dor "
        "na barriga intensa, vômitos frequentes, tontura, dificuldade para "
        "respirar — é urgência.",
    ),
    (
        "gripe-influenza",
        "Gripe (influenza)",
        "Infecção respiratória causada pelo vírus influenza. Começa de forma "
        "abrupta e costuma se resolver sozinha em cerca de uma semana, embora a "
        "tosse e o cansaço possam durar mais tempo.",
        "A fonte consultada não especifica sinais de alarme. Procure um "
        "profissional de saúde se os sintomas piorarem, se a febre não ceder ou "
        "se houver falta de ar.",
    ),
    (
        "tuberculose",
        "Tuberculose",
        "Doença causada por uma bactéria que atinge principalmente os pulmões. O "
        "principal sinal é a tosse que não passa. O diagnóstico e o tratamento "
        "são gratuitos pelo SUS.",
        "Tosse por três semanas ou mais precisa ser investigada. A fonte orienta "
        "procurar a unidade de saúde mais próxima da sua casa para avaliação e "
        "exames.",
    ),
    (
        "geo-helmintiase",
        "Geo-helmintíase",
        "Grupo de verminoses intestinais transmitidas por ovos ou larvas que "
        "estão no solo. Muitas vezes não dá sintoma nenhum, mas infecções "
        "intensas podem levar a desnutrição e anemia.",
        "A fonte consultada não especifica sinais de alarme. Procure um "
        "profissional de saúde diante de desconforto na barriga que não passa, "
        "diarreia persistente ou perda de peso.",
    ),
]

# (apelido, titulo, fonte, endereco)
MATERIAIS = [
    (
        "ms-dengue",
        "Dengue",
        "Ministério da Saúde",
        "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/d/dengue",
        "Página do Ministério da Saúde sobre a dengue: sintomas mais comuns, "
        "sinais de alarme da forma grave, transmissão, tratamento e prevenção.",
    ),
    (
        "opas-dengue",
        "Dengue: Sintomas, Prevenção e Tratamentos",
        "Organização Pan-Americana da Saúde (OPAS/OMS)",
        "https://www.paho.org/pt/topicos/dengue",
        "Página da OPAS/OMS sobre a dengue, com o quadro clínico, a evolução "
        "para a forma grave e as recomendações de acompanhamento.",
    ),
    (
        "ms-gripe",
        "Gripe (influenza)",
        "Ministério da Saúde",
        "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/g/gripe-influenza",
        "Página do Ministério da Saúde sobre a gripe: sintomas, duração, grupos "
        "de risco, vacinação e critérios para o uso de antiviral.",
    ),
    (
        "ms-tuberculose",
        "Tuberculose",
        "Ministério da Saúde",
        "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/t/tuberculose",
        "Página do Ministério da Saúde sobre a tuberculose: sinais da forma "
        "pulmonar, diagnóstico e tratamento gratuito pelo SUS.",
    ),
    (
        "ms-geo-helmintiase",
        "Geo-Helmintíase",
        "Ministério da Saúde",
        "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/g/geo-helmintiase",
        "Página do Ministério da Saúde sobre as verminoses transmitidas pelo "
        "solo: manifestações, diagnóstico por exame de fezes e tratamento.",
    ),
]

# (slug do sintoma, slug da condicao, apelido do material) — e, ao lado, o
# trecho da fonte que sustenta a ligação.
ASSOCIACOES = [
    ("febre", "dengue", "ms-dengue"),                      # "Febre alta"
    ("dor-de-cabeca", "dengue", "ms-dengue"),              # "Dor de cabeça e/ou atrás dos olhos"
    ("febre", "dengue", "opas-dengue"),                    # "febre baixa ou alta"
    ("dor-de-cabeca", "dengue", "opas-dengue"),            # "forte dor de cabeça"
    ("febre", "gripe-influenza", "ms-gripe"),              # "Febre"
    ("dor-de-garganta", "gripe-influenza", "ms-gripe"),    # "Dor de garganta"
    ("tosse", "gripe-influenza", "ms-gripe"),              # "Tosse"
    ("dor-de-cabeca", "gripe-influenza", "ms-gripe"),      # "Dor de cabeça"
    ("cansaco", "gripe-influenza", "ms-gripe"),            # "fadiga" e "prostração"
    ("tosse", "tuberculose", "ms-tuberculose"),            # "tosse por três semanas ou mais"
    ("febre", "tuberculose", "ms-tuberculose"),            # "febre vespertina"
    ("dor-abdominal", "geo-helmintiase", "ms-geo-helmintiase"),  # "Desconforto abdominal"
    ("febre", "geo-helmintiase", "ms-geo-helmintiase"),    # "Febre"
    ("tosse", "geo-helmintiase", "ms-geo-helmintiase"),    # "Tosse"
]


def carregar(apps, schema_editor):
    """Cadastra o acervo sem sobrescrever nada que já exista."""
    Condicao = apps.get_model("catalog", "Condicao")
    Material = apps.get_model("catalog", "Material")
    Sintoma = apps.get_model("catalog", "Sintoma")
    Associacao = apps.get_model("catalog", "Associacao")

    condicoes = {}
    for slug, nome, resumo, quando in CONDICOES:
        condicoes[slug], _ = Condicao.objects.get_or_create(
            slug=slug,
            defaults={"nome": nome, "resumo": resumo, "quando_procurar": quando},
        )

    # O material não tem slug, então a busca é pelo endereço de origem, que é o
    # que identifica um material sem ambiguidade.
    materiais = {}
    for apelido, titulo, fonte, url, resumo in MATERIAIS:
        materiais[apelido], _ = Material.objects.get_or_create(
            url_original=url,
            defaults={"titulo": titulo, "fonte": fonte, "resumo": resumo, "ativo": True},
        )

    for sintoma_slug, condicao_slug, material_apelido in ASSOCIACOES:
        sintoma = Sintoma.objects.filter(slug=sintoma_slug).first()
        if sintoma is None:
            # O sintoma vem da migração 0002. Se alguém o tiver renomeado, a
            # associação é pulada em vez de estourar a migração inteira.
            continue
        Associacao.objects.get_or_create(
            sintoma=sintoma,
            condicao=condicoes[condicao_slug],
            material=materiais[material_apelido],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_publicado_em_opcional"),
    ]

    operations = [
        # Mesmo motivo da migração dos sintomas: o caminho de volta não apaga
        # nada. Desfazer esta migração depois de alguém ter editado o acervo
        # pelo painel destruiria trabalho que ela não criou.
        migrations.RunPython(carregar, migrations.RunPython.noop),
    ]
