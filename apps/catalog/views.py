"""Telas do acervo: marcar sintomas e ver o que as fontes dizem.

Nada do que a pessoa marca é gravado. Os sintomas viajam na URL e são lidos a
cada requisição; nenhuma view aqui escreve no banco.
"""

from django.contrib import messages
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from .models import Associacao, Condicao, Material, Sintoma


def selecionar_sintomas(request):
    """Tela onde a pessoa marca o que está sentindo.

    Os sintomas que chegarem na URL já aparecem marcados. É assim que os
    atalhos da home e o "voltar e rever o que marquei" devolvem a pessoa para
    esta tela com o que ela já tinha escolhido, em vez de tudo em branco.
    """
    return render(
        request,
        "catalog/sintomas.html",
        {
            "comuns": Sintoma.objects.filter(alerta=False),
            "alertas": Sintoma.objects.filter(alerta=True),
            "marcados": request.GET.getlist("s"),
        },
    )


def resultado(request):
    """O que as fontes associam aos sintomas marcados.

    O formulário chega por GET, e não por POST, de propósito: os sintomas viram
    parâmetros na URL. Assim o endereço do resultado pode ser compartilhado, o
    botão de voltar do navegador funciona, e não há CSRF a proteger, porque a
    requisição não muda nada no servidor.
    """
    # Slugs que não existem são ignorados em silêncio. Um link antigo,
    # compartilhado por alguém, não deve virar tela de erro.
    marcados = list(Sintoma.objects.filter(slug__in=request.GET.getlist("s")))

    if not marcados:
        messages.info(request, "Marque pelo menos um sintoma.")
        return redirect("catalog:sintomas")

    # RETORNO ANTECIPADO, e ele é o coração desta tela.
    #
    # Se qualquer sinal de alerta foi marcado, a resposta é uma só: procure
    # atendimento. Nenhuma consulta de condição acontece daqui para baixo, e
    # nenhuma lista é montada. Misturar "pode ser urgente" com uma lista de
    # leitura convidaria a pessoa a ler em vez de ir ao pronto-socorro.
    if any(sintoma.alerta for sintoma in marcados):
        return render(request, "catalog/alerta.html", {"marcados": marcados})

    # As associações que sustentam esta busca: as dos sintomas marcados, e só as
    # que têm material no ar. Material desativado é fonte que saiu da origem, e
    # sem fonte a ligação não existe.
    associacoes = (
        Associacao.objects.filter(sintoma__in=marcados, material__ativo=True)
        .select_related("material")
    )

    # distinct() porque a mesma condição pode chegar por dois sintomas
    # diferentes, e ela deve aparecer uma vez só.
    condicoes = (
        Condicao.objects.filter(
            associacoes__sintoma__in=marcados,
            associacoes__material__ativo=True,
        )
        .distinct()
        .order_by("nome")
        .prefetch_related(Prefetch("associacoes", queryset=associacoes, to_attr="ligacoes"))
    )

    # A ordem é alfabética, sempre. Não existe ordenação por probabilidade,
    # relevância ou gravidade em lugar nenhum deste código.
    condicoes = list(condicoes)
    for condicao in condicoes:
        # Um mesmo material pode afirmar a ligação por mais de um sintoma
        # marcado. O dicionário, com o id do material como chave, faz ele
        # aparecer uma vez só, preservando a ordem em que apareceu.
        unicos = {}
        for ligacao in condicao.ligacoes:
            unicos[ligacao.material_id] = ligacao.material
        condicao.materiais = list(unicos.values())

    return render(
        request,
        "catalog/resultado.html",
        {"marcados": marcados, "condicoes": condicoes},
    )


def condicao(request, slug):
    """Página de uma condição, com os materiais que falam dela.

    O portal não reproduz o texto da fonte: guarda título, resumo e link, e
    manda a pessoa ler no site de quem publicou. Isso é decisão, e não
    esquecimento — evita problema de direito autoral e mantém a fonte como dona
    do que escreveu, inclusive quando ela corrige o texto depois.
    """
    condicao = get_object_or_404(Condicao, slug=slug)

    # Só o que está no ar. distinct() porque o mesmo material pode aparecer em
    # mais de uma associação desta condição, uma para cada sintoma.
    materiais = (
        Material.objects.filter(associacoes__condicao=condicao, ativo=True)
        .distinct()
        .order_by("-publicado_em")
    )

    return render(
        request,
        "catalog/condicao.html",
        {"condicao": condicao, "materiais": materiais},
    )
