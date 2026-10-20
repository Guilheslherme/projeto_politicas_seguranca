"""Remove a trilha de autenticação com mais de seis meses.

Uso:

    python manage.py expurgar_eventos_auth

O comando só remove uma faixa antiga no início da cadeia. Se encontrar um
evento vencido depois de um evento ainda dentro do prazo, interrompe sem apagar
nada: remover uma faixa no meio quebraria o encadeamento.
"""

from calendar import monthrange

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuthEvent, AuthEventRetentionCheckpoint

RETENTION_MONTHS = 6


def subtrair_meses(data, meses):
    """Subtrai meses de calendário, limitando o dia ao fim do mês de destino."""
    mes_absoluto = data.year * 12 + data.month - 1 - meses
    ano, mes_zero_based = divmod(mes_absoluto, 12)
    mes = mes_zero_based + 1
    dia = min(data.day, monthrange(ano, mes)[1])
    return data.replace(year=ano, month=mes, day=dia)


class Command(BaseCommand):
    help = "Apaga eventos de autenticacao com mais de seis meses e grava o checkpoint da cadeia."

    def handle(self, *args, **options):
        agora = timezone.now()
        corte = subtrair_meses(agora, RETENTION_MONTHS)

        with transaction.atomic():
            # Trava as linhas existentes para que a expurgação e uma gravação
            # concorrente não disputem o elo que será mantido como checkpoint.
            eventos = AuthEvent.objects.select_for_update().order_by("id").iterator()
            ultimo_antigo = None
            quantidade_antigos = 0
            encontrou_recente = False

            for evento in eventos:
                vencido = evento.created_at < corte
                if vencido and encontrou_recente:
                    raise CommandError(
                        "Ha eventos vencidos depois de eventos dentro do prazo; "
                        "nenhum registro foi apagado para preservar a cadeia."
                    )
                if vencido:
                    ultimo_antigo = evento
                    quantidade_antigos += 1
                else:
                    encontrou_recente = True

            if ultimo_antigo is None:
                self.stdout.write("Nenhum evento de autenticacao venceu o prazo de seis meses.")
                return

            AuthEventRetentionCheckpoint.objects.update_or_create(
                pk=1,
                defaults={
                    "last_event_id": ultimo_antigo.pk,
                    "last_event_hash": ultimo_antigo.hash_atual,
                    "last_event_created_at": ultimo_antigo.created_at,
                    "cutoff_at": corte,
                    "deleted_count": quantidade_antigos,
                    "checkpointed_at": agora,
                },
            )
            AuthEvent.objects.filter(pk__lte=ultimo_antigo.pk).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"{quantidade_antigos} evento(s) removido(s) antes de {corte:%d/%m/%Y %H:%M}; "
                f"checkpoint no evento {ultimo_antigo.pk}."
            )
        )
