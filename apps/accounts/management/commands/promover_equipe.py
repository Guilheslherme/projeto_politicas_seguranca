"""Dá acesso de equipe a uma conta que já tem 2FA ativo (risco R05).

Conta da equipe sem 2FA não entra no site. Por isso o caminho para alguém
virar equipe é: criar a conta pelo cadastro, ativar o 2FA no perfil e só
então rodar este comando. O createsuperuser cria uma conta sem 2FA, que
ficaria sem conseguir entrar.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import EncryptedTOTPDevice, User


class Command(BaseCommand):
    help = "Dá acesso de equipe (is_staff) a uma conta que já tem 2FA ativo."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument(
            "--superusuario",
            action="store_true",
            help="Também dá todas as permissões do painel (is_superuser).",
        )

    def handle(self, *args, email, superusuario, **options):
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is None:
            raise CommandError(f"Nenhuma conta ativa com o e-mail {email}.")

        if not EncryptedTOTPDevice.objects.filter(user=user, confirmed=True).exists():
            raise CommandError(
                "Essa conta ainda não tem 2FA ativo. Entre com ela no site, "
                "ative o 2FA no perfil e rode o comando de novo."
            )

        user.is_staff = True
        user.is_superuser = user.is_superuser or superusuario
        user.save(update_fields=["is_staff", "is_superuser"])
        self.stdout.write(self.style.SUCCESS(f"{user.email} agora faz parte da equipe."))
