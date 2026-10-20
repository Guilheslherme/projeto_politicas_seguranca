"""Painel administrativo com verificação em duas etapas (risco R01).

O admin padrão do Django pedia só e-mail e senha. Quem descobrisse a senha de
alguém da equipe abria o painel inteiro: o acervo, a trilha de auditoria e os
dispositivos 2FA de todas as contas.
"""

from django.contrib import admin, messages
from django.shortcuts import redirect
from django_otp.admin import OTPAdminSite
from django_otp.plugins.otp_totp.models import TOTPDevice


class PainelComDoisFatores(OTPAdminSite):
    """Admin que só abre para quem confirmou o código TOTP nesta sessão.

    A regra vem do OTPAdminSite: has_permission exige is_staff e também
    request.user.is_verified(), que só fica verdadeiro depois do otp_login.

    O formulário de login do próprio django-otp não é usado. Ele confere o
    código com o TOTPDevice, que lê o segredo como texto puro, e neste projeto
    o segredo está cifrado (EncryptedTOTPDevice): o código nunca bateria. Por
    isso o login do painel manda para a tela de login do site, que confere o
    segredo decifrado, passa pelo bloqueio do axes e grava a trilha.
    """

    def login(self, request, extra_context=None):
        if self.has_permission(request):
            return redirect(f"{self.name}:index")

        if request.user.is_authenticated:
            # Logado só com senha, ou sem 2FA ativo: não adianta mostrar a tela
            # de login de novo, porque ela mandaria a pessoa de volta ao perfil.
            messages.warning(
                request,
                "O painel administrativo exige a verificação em duas etapas. "
                "Ative o 2FA ou saia e entre de novo usando o código.",
            )
            return redirect("accounts:profile")

        return redirect("accounts:login")


# O cadastro de dispositivos do django-otp grava TOTPDevice sem passar pelo
# EncryptedTOTPDevice: o segredo ficaria em texto puro, e a conta daquele
# dispositivo deixaria de conseguir entrar, porque a decifragem falharia. Os
# dispositivos são criados só pela tela de ativação do 2FA.
if admin.site.is_registered(TOTPDevice):
    admin.site.unregister(TOTPDevice)
