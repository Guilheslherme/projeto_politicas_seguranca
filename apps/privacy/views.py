import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuthEvent
from apps.audit.signals import registrar_evento

from .forms import ConsentForm, DeleteAccountForm
from .models import ConsentRecord
from .rights import excluir_conta, reunir_dados_do_titular

#nesta pagina ficam a politica de privacidade, o aceite e os direitos do titular (consulta, exportacao e exclusao)


def privacy_policy(request):
    """Texto da Política de Privacidade, público e sem exigir login."""
    return render(
        request,
        "privacy/policy.html",
        {"versao": settings.PRIVACY_POLICY_VERSION},
    )


@login_required
def consent(request):
    """Aceite da versão vigente da política (requisitos 4.4 e 4.7)."""
    if ConsentRecord.tem_consentimento_vigente(request.user):
        return redirect("privacy:my_data")

    form = ConsentForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        ConsentRecord.registrar_aceite(request.user)
        messages.success(request, "Consentimento registrado.")
        return redirect("accounts:profile")

    return render(
        request,
        "privacy/consent.html",
        {"form": form, "versao": settings.PRIVACY_POLICY_VERSION},
    )


@login_required
def my_data(request):
    """Consulta a todos os dados guardados sobre a conta (requisito 4.8)."""
    return render(
        request,
        "privacy/my_data.html",
        {"dados": reunir_dados_do_titular(request.user)},
    )


@login_required
@require_POST
def export_data(request):
    """Download dos mesmos dados da consulta, em JSON (requisito 4.9).

    Aceita só POST, com o token de CSRF do formulário. Um GET permitiria que
    outro site disparasse o download com um simples link; o navegador não
    entregaria o arquivo a esse site, mas a pessoa receberia um download que
    não pediu.
    """
    dados = reunir_dados_do_titular(request.user)
    conteudo = json.dumps(dados, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)

    resposta = HttpResponse(conteudo, content_type="application/json; charset=utf-8")
    nome_do_arquivo = f"health-in-sight-meus-dados-{timezone.now():%Y%m%d}.json"
    resposta["Content-Disposition"] = f'attachment; filename="{nome_do_arquivo}"'
    # O arquivo tem dados pessoais: nenhum cache intermediário deve guardá-lo.
    resposta["Cache-Control"] = "no-store"
    return resposta


@login_required
def delete_account(request):
    """Revogação do consentimento com exclusão da conta (requisitos 4.6 e 4.10).

    A conta é o único tratamento apoiado em consentimento neste sistema. Por
    isso revogar o consentimento e excluir a conta são o mesmo ato: sem o
    consentimento, deixa de existir base legal para manter os dados, e a LGPD
    determina que eles sejam eliminados ao fim do tratamento (Arts. 15, III, e
    16).
    """
    form = DeleteAccountForm(request.user, request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = request.user

        # A ordem destas três linhas é deliberada, e mexer nela já quebrou a
        # trilha uma vez: registrar, encerrar a sessão, e só então apagar.
        #
        # O logout dispara o sinal que grava o evento de fim de sessão, e esse
        # registro guarda o identificador da conta. Se a conta já tivesse sido
        # apagada, o objeto em memória estaria sem chave primária e o Django
        # recusaria a gravação; o evento se perderia em silêncio, e a última
        # coisa que a pessoa fez no sistema ficaria fora da trilha.
        #
        # O preço da ordem: se a exclusão falhar, a pessoa sai da sessão com a
        # conta ainda de pé. Não fica pela metade, porque excluir_conta roda em
        # uma transação só — basta entrar de novo e repetir.
        registrar_evento(request, AuthEvent.Event.CONTA_EXCLUIDA, user=user)
        logout(request)
        excluir_conta(user)
        messages.success(
            request,
            "Sua conta foi excluída e o consentimento, revogado. "
            "Os dados pessoais ligados a ela foram apagados.",
        )
        return redirect("home")

    return render(request, "privacy/delete_account.html", {"form": form})
