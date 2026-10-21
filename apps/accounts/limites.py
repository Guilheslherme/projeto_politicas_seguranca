"""Limites de requisição e bloqueio progressivo (risco R03).

O django-axes já bloqueia a combinação de conta e endereço depois de cinco
senhas erradas. Isso não segura quem testa uma senha comum em muitas contas
(password spraying) nem quem dispara logins com e-mails aleatórios: cada um
custa um Argon2id de 64 MiB no servidor. Aqui entram dois limites a mais, por
endereço e no total, e o tempo de bloqueio do axes passa a dobrar a cada
bloqueio repetido no mesmo dia.
"""

import logging
from datetime import timedelta
from functools import wraps

from axes.helpers import get_client_ip_address
from axes.models import AccessAttempt
from django.conf import settings
from django.db.models import Min
from django.shortcuts import render
from django.utils import timezone
from django_ratelimit.core import get_usage, is_ratelimited

logger = logging.getLogger(__name__)

BLOQUEIO_INICIAL = timedelta(minutes=5)
BLOQUEIO_MAXIMO = timedelta(hours=24)
JANELA_DOS_BLOQUEIOS = timedelta(hours=24)


def ip_do_cliente(request):
    """Endereço de quem fez a requisição, com a mesma regra do axes.

    No Render, REMOTE_ADDR é o proxy, igual para todo mundo. O axes já sabe
    ler o X-Forwarded-For com AXES_IPWARE_PROXY_COUNT, e usar a mesma função
    garante que o limite e o bloqueio enxerguem o mesmo endereço.
    """
    ip = get_client_ip_address(request)

    # Diagnóstico temporário, ligado só pela variável de ambiente, para
    # conferir no Render se AXES_IPWARE_PROXY_COUNT escolhe o endereço certo.
    # Registra endereços IP, então deve ser desligado assim que a conferência
    # terminar.
    if settings.DIAGNOSTICO_PROXY:
        logger.info(
            "diagnostico_proxy remote_addr=%s x_forwarded_for=%s escolhido=%s",
            request.META.get("REMOTE_ADDR"),
            request.META.get("HTTP_X_FORWARDED_FOR"),
            ip,
        )
    return ip


def _por_ip(group, request):
    return ip_do_cliente(request)


def _total(group, request):
    # Mesma chave para todas as requisições: o limite vale para o site inteiro.
    return "todos"


def limitar(grupo):
    """Recusa com 429 os envios de formulário acima do limite do grupo.

    Só o POST conta: abrir a página não custa nada ao servidor. Os limites de
    cada grupo ficam em settings.LIMITES_DE_REQUISICAO.
    """

    def decorator(view):
        @wraps(view)
        def envolvida(request, *args, **kwargs):
            if request.method == "POST":
                limites = settings.LIMITES_DE_REQUISICAO[grupo]
                # As duas contagens rodam sempre, para que o total some também
                # as requisições de quem já estourou o limite do próprio IP.
                passou_do_ip = is_ratelimited(
                    request, group=f"{grupo}:ip", key=_por_ip,
                    rate=limites["por_ip"], method="POST", increment=True,
                )
                passou_do_total = is_ratelimited(
                    request, group=f"{grupo}:total", key=_total,
                    rate=limites["total"], method="POST", increment=True,
                )
                if passou_do_ip or passou_do_total:
                    return render(request, "accounts/limite_excedido.html", status=429)
            return view(request, *args, **kwargs)

        return envolvida

    return decorator


# Confirmações erradas aceitas por conta, em telas que pedem a senha de novo
# dentro de uma sessão já aberta (risco R12). Sem limite, quem achasse uma
# sessão aberta poderia testar senhas ali à vontade, fora do alcance do axes.
FALHAS_DE_CONFIRMACAO = "5/15m"


def _pela_conta(group, request):
    return str(request.user.pk)


def confirmacao_bloqueada(request, grupo):
    """Diz se a conta logada esgotou as confirmações erradas do grupo.

    Só lê a contagem, sem somar: quem ainda não errou não gasta tentativa.
    O is_ratelimited sem incrementar só acusaria acima do limite, deixando
    passar uma tentativa a mais; por isso a comparação é feita aqui.
    """
    uso = get_usage(
        request, group=f"{grupo}:falhas", key=_pela_conta,
        rate=FALHAS_DE_CONFIRMACAO, increment=False,
    )
    return uso is not None and uso["count"] >= uso["limit"]


def registrar_confirmacao_errada(request, grupo):
    is_ratelimited(
        request, group=f"{grupo}:falhas", key=_pela_conta,
        rate=FALHAS_DE_CONFIRMACAO, increment=True,
    )


def tempo_de_bloqueio(request=None):
    """Duração do bloqueio do axes: 5 minutos, dobrando a cada repetição.

    Conta os bloqueios da mesma conta e do mesmo endereço nas últimas 24
    horas, a partir da trilha de auditoria (evento CONTA_BLOQUEADA). Entram só
    os bloqueios anteriores à série atual de tentativas: o axes recalcula este
    prazo a cada checagem, e contar o bloqueio em andamento faria a duração
    mudar enquanto ele ainda vale.
    """
    if request is None or request.method != "POST":
        return BLOQUEIO_INICIAL

    # Importados aqui porque o settings aponta para esta função pelo caminho,
    # e os modelos só podem ser carregados depois que o Django sobe.
    from apps.audit.models import AuthEvent

    from .models import User

    email = request.POST.get(settings.AXES_USERNAME_FORM_FIELD, "")
    ip = get_client_ip_address(request)
    agora = timezone.now()

    # Início da série atual: a tentativa válida mais antiga dessa combinação.
    # Sem tentativa válida, todo bloqueio registrado já é anterior.
    inicio_da_serie = AccessAttempt.objects.filter(
        username=email,
        ip_address=ip,
        expiration__expires_at__gt=agora,
    ).aggregate(inicio=Min("attempt_time"))["inicio"] or agora

    anteriores = AuthEvent.objects.filter(
        event=AuthEvent.Event.CONTA_BLOQUEADA,
        user=User.objects.filter(email__iexact=email).first(),
        ip_address=ip,
        created_at__gte=agora - JANELA_DOS_BLOQUEIOS,
        created_at__lt=inicio_da_serie,
    ).count()

    return min(BLOQUEIO_INICIAL * 2 ** min(anteriores, 10), BLOQUEIO_MAXIMO)
