"""Trilha de auditoria do processo de recuperação de senha (requisitos 2.6 e 2.7)."""

import logging

from axes.helpers import get_client_ip_address, get_client_user_agent
from django.conf import settings
from django.db import models

# O nome do logger começa com "apps", que é o prefixo configurado em LOGGING.
# Assim cada evento aparece também na saída do servidor, e não só no banco.
logger = logging.getLogger(__name__)


class PasswordResetLog(models.Model):
    """Registro de cada etapa de uma recuperação de senha.

    Guarda tanto a solicitação (requisito 2.6) quanto o desfecho de cada etapa,
    com sucesso ou falha (requisito 2.7). É gravado no banco em vez de só em
    arquivo porque o Render apaga o disco a cada implantação, e um log que some
    junto com o servidor não serve de trilha de auditoria.

    O log identifica a conta pelo identificador interno, nunca pelo e-mail. Um
    log de auditoria é lido por mais gente e guardado por mais tempo que a
    tabela de usuários, então repetir o endereço aqui aumentaria a exposição do
    dado sem necessidade: o identificador já responde às perguntas que a
    auditoria precisa fazer.
    """

    class Event(models.TextChoices):
        """Etapas registradas, do pedido até a troca efetiva da senha."""

        SOLICITADO = "SOLICITADO", "Solicitação recebida"
        EMAIL_ENVIADO = "EMAIL_ENVIADO", "E-mail enviado"
        EMAIL_FALHOU = "EMAIL_FALHOU", "Falha no envio do e-mail"
        LIMITE_EXCEDIDO = "LIMITE_EXCEDIDO", "Limite de solicitações excedido"
        TOKEN_INVALIDO = "TOKEN_INVALIDO", "Token inexistente"
        TOKEN_EXPIRADO = "TOKEN_EXPIRADO", "Token expirado"
        TOKEN_JA_USADO = "TOKEN_JA_USADO", "Token já utilizado"
        SENHA_REDEFINIDA = "SENHA_REDEFINIDA", "Senha redefinida"

    event = models.CharField("evento", max_length=20, choices=Event.choices)

    """ Conta envolvida no evento, ou nulo quando o endereço informado não
    corresponde a conta nenhuma. Fica nulo também se a conta for excluída
    depois: apagar a pessoa não pode apagar a trilha do que aconteceu, e o
    registro segue valendo como contagem de eventos por período e por IP. """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="password_reset_logs",
        verbose_name="usuario",
    )

    # Mesma resolução de endereço usada pelo django-axes no bloqueio por força
    # bruta, então os dois registros falam do mesmo IP mesmo atrás do proxy do
    # Render.
    ip_address = models.GenericIPAddressField("endereco de rede", null=True, blank=True)

    user_agent = models.CharField("navegador", max_length=255, blank=True)

    """ Texto curto com o motivo técnico da falha, quando existe. Nunca recebe
    token, senha, endereço de e-mail nem corpo da mensagem enviada: o que entra
    aqui é escrito pelo próprio código, e não copiado da requisição ou da
    resposta de terceiros. """
    detail = models.CharField("detalhe", max_length=255, blank=True)

    """ auto_now_add grava o instante na criação e não aceita valor vindo de
    fora, então nem o código da aplicação consegue forjar a data de um evento. """
    created_at = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "registro de recuperacao de senha"
        verbose_name_plural = "registros de recuperacao de senha"
        ordering = ["-created_at"]
        indexes = [
            # Sustenta a contagem de solicitações recentes por conta, que é como
            # o limite de pedidos é aplicado.
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.created_at:%d/%m/%Y %H:%M} {self.event} usuario={self.user_id}"

    @classmethod
    def registrar(cls, request, event, user=None, detail=""):
        """Grava um evento e devolve o registro criado.

        Concentrar a gravação aqui evita que cada view repita a extração do IP e
        do navegador, e garante que nenhuma etapa do fluxo escape do log. Também
        deixa um ponto único para conferir o que entra na trilha: a assinatura
        não aceita e-mail nem token, então nenhuma chamada consegue gravá-los
        por descuido.
        """
        registro = cls.objects.create(
            event=event,
            user=user,
            ip_address=get_client_ip_address(request),
            user_agent=get_client_user_agent(request),
            detail=detail[:255],
        )
        logger.info(
            "recuperacao de senha: %s usuario_id=%s ip=%s %s",
            event,
            registro.user_id,
            registro.ip_address,
            detail,
        )
        return registro
