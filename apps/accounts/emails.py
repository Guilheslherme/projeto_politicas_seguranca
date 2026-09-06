"""Envio de e-mail transacional pela API HTTP do Brevo (requisito 2.1)."""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"

# O plano gratuito do Render dorme quando fica ocioso e demora a acordar. Um
# limite de tempo evita que a requisição do usuário fique presa esperando o
# Brevo responder; sem ele, a página ficaria carregando indefinidamente.
TIMEOUT_EM_SEGUNDOS = 10


class FalhaNoEnvio(Exception):
    """A mensagem não foi aceita pelo Brevo.

    Existe para que a view distinga uma falha de entrega de qualquer outro erro
    e registre o evento EMAIL_FALHOU no log (requisito 2.7).
    """


def _enviar(destinatario, assunto, conteudo_texto, conteudo_html):
    """Entrega a mensagem à API do Brevo.

    A chamada é feita com urllib, da biblioteca padrão, em vez da biblioteca
    requests: é uma única requisição HTTP, e evitar a dependência mantém o
    tempo de build do Render menor.
    """
    corpo = {
        "sender": {
            "name": settings.BREVO_SENDER_NAME,
            "email": settings.BREVO_SENDER_EMAIL,
        },
        "to": [{"email": destinatario}],
        "subject": assunto,
        "textContent": conteudo_texto,
        "htmlContent": conteudo_html,
    }

    requisicao = urllib.request.Request(
        BREVO_ENDPOINT,
        data=json.dumps(corpo).encode("utf-8"),
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            # A chave vai no cabeçalho, nunca na URL: endereços aparecem em log
            # de servidor e histórico de proxy, cabeçalhos não.
            "api-key": settings.BREVO_API_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_EM_SEGUNDOS) as resposta:
            if resposta.status not in (200, 201, 202):
                raise FalhaNoEnvio(f"Brevo respondeu HTTP {resposta.status}")
    except urllib.error.HTTPError as erro:
        # Só o código da resposta entra na mensagem. O corpo devolvido pelo
        # Brevo costuma repetir o endereço do destinatário, e esta mensagem vai
        # parar na trilha de auditoria, que não guarda e-mail. O motivo
        # detalhado de cada recusa fica no painel do próprio Brevo.
        raise FalhaNoEnvio(f"Brevo recusou a mensagem: HTTP {erro.code}") from erro
    except urllib.error.URLError as erro:
        raise FalhaNoEnvio(f"Brevo inacessivel: {erro.reason}") from erro
    except TimeoutError as erro:
        raise FalhaNoEnvio("Brevo nao respondeu no tempo limite") from erro


def enviar_link_de_recuperacao(user, link):
    """Envia à pessoa o link de redefinição de senha.

    Levanta FalhaNoEnvio se o Brevo não aceitar a mensagem.
    """
    contexto = {
        "nome": user.get_short_name(),
        "link": link,
        "minutos": int(settings.PASSWORD_RESET_TOKEN_TIMEOUT.total_seconds() // 60),
    }
    assunto = "Redefinição de senha - Health In Sight"
    conteudo_texto = render_to_string("emails/password_reset.txt", contexto)
    conteudo_html = render_to_string("emails/password_reset.html", contexto)

    if not settings.BREVO_API_KEY:
        if not settings.DEBUG:
            # Em produção, chave ausente é falha de verdade. Imprimir o link
            # aqui seria gravar um token válido no log do servidor.
            raise FalhaNoEnvio("BREVO_API_KEY nao configurada")

        # Só em desenvolvimento: o link vai para a saída do servidor para que o
        # fluxo possa ser percorrido na máquina local sem consumir a cota de
        # envios. O link carrega o token, então esta linha nunca pode acontecer
        # com DEBUG desligado. O destinatário não é impresso junto.
        logger.warning("BREVO_API_KEY ausente. Link de recuperacao: %s", link)
        return

    _enviar(user.email, assunto, conteudo_texto, conteudo_html)
