"""Trilhas de auditoria do sistema (requisitos 2.6, 2.7 e 5.1 a 5.3)."""

import hashlib
import logging

from axes.helpers import get_client_ip_address, get_client_user_agent
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

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


class AuthEvent(models.Model):
    """Trilha dos eventos de autenticação, encadeada por hash.

    Responde aos requisitos 5.1 (logins registrados), 5.2 (falhas e segundo
    fator registrados) e 5.3 (proteção contra alteração dos registros).

    Cada registro guarda o hash do registro anterior. Hash é um resumo de
    tamanho fixo calculado a partir de um texto: mudar qualquer letra do texto
    muda o resumo inteiro. Como o resumo de cada linha entra no cálculo da
    linha seguinte, alterar um registro antigo faz o elo com o próximo deixar
    de bater, e o comando `verificar_logs` aponta onde a conta não fecha.

    O que isso não resolve está escrito em docs/analise-de-logs.md: apagar os
    últimos registros da trilha não é detectado, e quem tem acesso ao banco e
    conhece este arquivo consegue recalcular a cadeia a partir do ponto que
    alterou. A proteção é contra alteração pontual, não contra quem controla
    o servidor.
    """

    class Event(models.TextChoices):
        """Eventos registrados, da entrada até a exclusão da conta."""

        LOGIN_OK = "LOGIN_OK", "Login concluído"
        LOGIN_FALHOU = "LOGIN_FALHOU", "Senha inválida"
        LOGOUT = "LOGOUT", "Sessão encerrada"
        OTP_OK = "OTP_OK", "Segundo fator validado"
        OTP_FALHOU = "OTP_FALHOU", "Código do segundo fator inválido"
        OTP_ATIVADO = "OTP_ATIVADO", "Segundo fator ativado"
        OTP_DESATIVADO = "OTP_DESATIVADO", "Segundo fator desativado"
        CONTA_BLOQUEADA = "CONTA_BLOQUEADA", "Conta bloqueada por tentativas"
        CADASTRO = "CADASTRO", "Conta criada"
        CONTA_EXCLUIDA = "CONTA_EXCLUIDA", "Conta excluída pelo titular"

    """ Valor de hash_anterior do primeiro registro da trilha. A cadeia precisa
    começar em algum lugar, e um valor fixo e conhecido deixa explícito onde é
    esse começo: se o registro mais antigo não apontar para a gênese, é porque
    o que vinha antes dele sumiu. """
    GENESE = "0" * 64

    event = models.CharField("evento", max_length=25, choices=Event.choices)

    """ Vínculo com a conta, usado para navegar no painel administrativo. Fica
    nulo quando a tentativa foi em um endereço sem conta, e também quando a
    conta é excluída depois (SET_NULL). Este campo NÃO entra no hash: ele muda
    sozinho na exclusão, e o que entra no hash não pode mudar. """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auth_events",
        verbose_name="usuario",
    )

    """ Cópia do identificador da conta no momento da gravação. Recebe o valor
    uma vez e nunca mais muda, nem quando a conta é excluída, e é este número
    que entra no hash.

    A alternativa seria usar o vínculo acima, mas aí a exclusão de uma conta
    mudaria o conteúdo de registros já gravados e quebraria a cadeia inteira
    sem que ninguém tivesse adulterado nada.

    O limite disso: depois que a conta é apagada, o número não leva a pessoa
    nenhuma, mas continua juntando os eventos dela entre si. É pseudonimização,
    não anonimização: separa a trilha da identidade, mas não desfaz os grupos.
    """
    usuario_ref = models.IntegerField("identificador selado", null=True, blank=True)

    # Mesma resolução de endereço usada pelo django-axes, para que os dois
    # registros falem do mesmo IP mesmo atrás do proxy do Render.
    ip_address = models.GenericIPAddressField("endereco de rede", null=True, blank=True)

    user_agent = models.CharField("navegador", max_length=255, blank=True)

    """ Texto curto escrito pelo próprio código. Nunca recebe o e-mail digitado
    na tentativa de login, senha nem código do segundo fator. """
    detail = models.CharField("detalhe", max_length=255, blank=True)

    """ default=timezone.now, e não auto_now_add, porque o hash é calculado
    antes do save e com auto_now_add a data só passaria a existir depois. A data
    entra no cálculo do hash, então continua protegida pela cadeia: mudá-la
    depois quebra o elo com o registro seguinte. """
    created_at = models.DateTimeField("registrado em", default=timezone.now)

    hash_anterior = models.CharField("hash do registro anterior", max_length=64)

    """ unique=True porque dois registros com o mesmo hash significariam ou uma
    cópia gravada duas vezes, ou uma cadeia bifurcada. O banco recusa antes que
    isso entre. """
    hash_atual = models.CharField("hash deste registro", max_length=64, unique=True)

    class Meta:
        verbose_name = "evento de autenticacao"
        verbose_name_plural = "eventos de autenticacao"
        ordering = ["-created_at"]
        indexes = [
            # Sustenta a consulta "o que aconteceu nesta conta?" no painel.
            models.Index(fields=["user", "created_at"]),
            # Sustenta o agrupamento do comando analisar_logs, que conta por
            # usuario_ref justamente para não perder os eventos das contas já
            # excluídas.
            models.Index(fields=["usuario_ref"]),
        ]

    def __str__(self):
        return f"{self.created_at:%d/%m/%Y %H:%M} {self.event} usuario={self.usuario_ref}"

    def calcular_hash(self):
        """Devolve o hash deste registro, a partir do conteúdo dele."""
        # A ordem dos campos é fixa e faz parte do formato: mudar a ordem, ou
        # acrescentar um campo no meio, invalida toda a cadeia já gravada,
        # porque os hashes antigos foram calculados com a ordem antiga.
        conteudo = "|".join([
            self.hash_anterior,
            self.event,
            str(self.usuario_ref or ""),
            self.ip_address or "",
            self.user_agent,
            self.detail,
            self.created_at.isoformat(),
        ])
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()

    @classmethod
    def registrar(cls, request, event, user=None, detail=""):
        """Grava um evento no fim da cadeia e devolve o registro criado."""
        # O objeto pode chegar sem chave primária quando o sinal dispara logo
        # depois de um delete(): a pessoa ainda existe na memória, mas não no
        # banco. Salvar um vínculo para um objeto assim é recusado pelo Django
        # ("save() prohibited to prevent data loss due to unsaved related
        # object"). Nesse caso o evento é gravado sem vínculo e sem número, que
        # é melhor do que não registrar que ele aconteceu.
        usuario_ref = getattr(user, "pk", None)
        if usuario_ref is None:
            user = None

        # request nulo acontece em sinais disparados fora de uma requisição.
        # Grava sem IP e sem navegador, em vez de deixar de gravar.
        ip_address = get_client_ip_address(request) if request is not None else None
        user_agent = get_client_user_agent(request) if request is not None else ""

        with transaction.atomic():
            # select_for_update trava a leitura do último registro até o fim da
            # transação. Sem isso, dois logins simultâneos leriam o mesmo último
            # hash, gravariam apontando os dois para ele, e a cadeia bifurcaria.
            # O SQLite ignora o comando, porque só permite uma escrita por vez.
            ultimo = cls.objects.select_for_update().order_by("-id").first()
            hash_anterior = ultimo.hash_atual if ultimo else cls.GENESE

            registro = cls(
                event=event,
                user=user,
                usuario_ref=usuario_ref,
                ip_address=ip_address,
                user_agent=user_agent,
                detail=detail[:255],
                hash_anterior=hash_anterior,
            )
            # O hash cobre o registro pronto, com a data já preenchida pelo
            # default do campo, e só então a linha vai para o banco.
            registro.hash_atual = registro.calcular_hash()
            registro.save()

        logger.info(
            "autenticacao: %s usuario_ref=%s ip=%s %s",
            event,
            registro.usuario_ref,
            registro.ip_address,
            detail,
        )
        return registro
