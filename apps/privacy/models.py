"""Registro do consentimento do titular (requisitos 4.4 a 4.7)."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConsentRecord(models.Model):
    """Um aceite da Política de Privacidade, para uma finalidade e uma versão.

    Cada aceite vira uma linha nova, e nenhuma linha é sobrescrita: aceitar uma
    versão nova da política cria outro registro, e revogar só preenche a data de
    revogação. Assim o histórico mostra o que a pessoa aceitou, quando e em qual
    versão do texto, que é o que a LGPD exige para o controlador provar que o
    consentimento foi obtido (Art. 8º, §2º).
    """

    class Purpose(models.TextChoices):
        """Finalidades que dependem de consentimento.

        Só entra aqui o tratamento que de fato se apoia no consentimento. Os
        registros de segurança (IP e horário de acesso) têm outra base legal,
        o legítimo interesse na prevenção a fraudes (Art. 7º, IX), e por isso
        não aparecem como finalidade consentida: não faria sentido oferecer a
        revogação de algo que continuaria acontecendo.
        """

        CONTA = "CONTA", "Criação e manutenção da conta"

    """ Conta que deu o consentimento. Se a conta for excluída, o vínculo fica
    nulo e o registro permanece apenas com finalidade, versão e datas — nenhum
    dado que identifique a pessoa —, preservando o histórico de que houve
    aceite e revogação. """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consent_records",
        verbose_name="usuario",
    )

    purpose = models.CharField("finalidade", max_length=20, choices=Purpose.choices)

    # Versão do texto da política no momento do aceite. É o que permite saber,
    # depois de uma mudança na política, quem ainda não aceitou a versão nova.
    policy_version = models.CharField("versao da politica", max_length=10)

    # auto_now_add grava o instante do aceite e não aceita valor vindo de fora.
    granted_at = models.DateTimeField("aceito em", auto_now_add=True)

    # Nulo enquanto o consentimento vale. A revogação preenche a data em vez de
    # apagar a linha, para que o histórico continue mostrando o aceite anterior.
    revoked_at = models.DateTimeField("revogado em", null=True, blank=True)

    class Meta:
        verbose_name = "registro de consentimento"
        verbose_name_plural = "registros de consentimento"
        ordering = ["-granted_at"]
        indexes = [
            # Sustenta a conferência feita a cada requisição de quem está logado.
            models.Index(fields=["user", "purpose", "policy_version", "revoked_at"]),
        ]

    def __str__(self):
        situacao = "revogado" if self.revoked_at else "vigente"
        return f"{self.get_purpose_display()} v{self.policy_version} ({situacao})"

    @property
    def is_active(self):
        return self.revoked_at is None

    @classmethod
    def registrar_aceite(cls, user, purpose=Purpose.CONTA):
        """Grava o aceite da versão atual da política para uma finalidade."""
        return cls.objects.create(
            user=user,
            purpose=purpose,
            policy_version=settings.PRIVACY_POLICY_VERSION,
        )

    @classmethod
    def tem_consentimento_vigente(cls, user, purpose=Purpose.CONTA):
        """Diz se a conta aceitou a versão atual e não revogou.

        Um aceite de versão anterior não conta: quando a política muda, a pessoa
        precisa ler e aceitar o texto novo antes de continuar usando a conta.
        """
        return cls.objects.filter(
            user=user,
            purpose=purpose,
            policy_version=settings.PRIVACY_POLICY_VERSION,
            revoked_at__isnull=True,
        ).exists()

    @classmethod
    def revogar_todos(cls, user):
        """Revoga todo consentimento vigente da conta e devolve quantos eram."""
        return cls.objects.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
