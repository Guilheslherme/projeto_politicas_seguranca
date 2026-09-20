"""Gravação automática dos eventos de autenticação (requisitos 5.1 e 5.2).

Por que ligar em sinais em vez de escrever dentro da view de login: o login
acontece em mais de um lugar. Além da tela do projeto, existe a tela de login
do painel administrativo do Django, que é a porta usada por quem administra o
sistema. Se a gravação ficasse só na view do projeto, justamente esses acessos
não entrariam na trilha, deixando o buraco no lugar mais sensível.

O django-otp não dispara sinal quando um código é aceito ou recusado, nem
quando o segundo fator é ativado ou desativado. Esses quatro eventos são
gravados por chamada direta, nas views de apps/accounts. O mesmo vale para o
cadastro e para a exclusão de conta, em apps/privacy.
"""

import logging

from axes.signals import user_locked_out
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .models import AuthEvent

logger = logging.getLogger(__name__)


def registrar_evento(request, event, user=None, detail=""):
    """Grava um evento na trilha sem deixar que uma falha derrube a tela.

    Esta é a porta de entrada da trilha: as views e os receptores abaixo
    chamam esta função, nunca o AuthEvent.registrar direto. O motivo é o
    try/except: se o banco estiver fora do ar ou a cadeia recusar a gravação,
    a pessoa ainda consegue entrar, e a falha aparece na saída do servidor com
    o traço completo, em vez de virar uma tela de erro no meio do login.

    A decisão tem um custo, e é bom estar escrito: um erro aqui significa
    evento perdido. Por isso o traço vai para o log com nível ERROR, que é o
    que a suíte de testes vigia.
    """
    try:
        return AuthEvent.registrar(request, event, user=user, detail=detail)
    except Exception:
        logger.exception("falha ao gravar evento de auditoria: %s", event)
        return None


def _conta_do_email(email):
    """Devolve a conta daquele e-mail, ou None se não existir nenhuma.

    O endereço digitado numa tentativa de login serve só para isto: descobrir
    de qual conta se trata. Ele não é gravado em campo nenhum da trilha. Um
    log de auditoria é lido por mais gente e guardado por mais tempo que a
    tabela de usuários, e repetir o endereço aqui espalharia o dado sem
    necessidade: o identificador já responde o que a auditoria precisa saber.

    A busca é tolerante a falha de propósito. Ela acontece no meio de um login
    que já deu errado, e um erro aqui não pode virar exceção na tela.
    """
    if not email:
        return None
    try:
        return get_user_model().objects.filter(email__iexact=email).first()
    except Exception:
        logger.exception("falha ao procurar a conta de uma tentativa de login")
        return None


@receiver(user_logged_in)
def ao_entrar(sender, request, user, **kwargs):
    """Requisito 5.1: toda sessão criada vira um registro."""
    registrar_evento(request, AuthEvent.Event.LOGIN_OK, user=user)


@receiver(user_logged_out)
def ao_sair(sender, request, user, **kwargs):
    """Requisito 5.1: fim da sessão.

    O Django dispara este sinal mesmo quando ninguém estava logado, e nesse
    caso user chega nulo. O evento é gravado assim mesmo, sem vínculo.
    """
    registrar_evento(request, AuthEvent.Event.LOGOUT, user=user)


@receiver(user_login_failed)
def ao_falhar(sender, credentials, request=None, **kwargs):
    """Requisito 5.2: senha recusada.

    O parâmetro credentials traz o e-mail digitado. Ele é usado só para achar
    a conta e é descartado em seguida. Quando não existe conta com aquele
    endereço, o registro fica sem vínculo e sem número, o que é a informação
    útil: alguém tentou entrar em um endereço que não existe aqui.
    """
    email = (credentials or {}).get("username") or (credentials or {}).get("email")
    registrar_evento(
        request,
        AuthEvent.Event.LOGIN_FALHOU,
        user=_conta_do_email(email),
    )


@receiver(user_locked_out)
def ao_bloquear(sender, request=None, username=None, ip_address=None, **kwargs):
    """Requisito 5.2: bloqueio por tentativas, disparado pelo django-axes.

    Mesma regra do evento acima: o endereço digitado serve para achar a conta e
    não é gravado. O detalhe guarda o limite configurado, que é escrito pelo
    próprio código e não veio da requisição.
    """
    registrar_evento(
        request,
        AuthEvent.Event.CONTA_BLOQUEADA,
        user=_conta_do_email(username),
        detail=f"limite de {settings.AXES_FAILURE_LIMIT} tentativas atingido",
    )
