"""
Views de autenticacao - requisitos 1.5, 1.6, 1.9 e 1.10.

Fluxo de login em duas etapas:

    1. E-mail e senha sao verificados contra o hash Argon2id.
    2. Se o usuario tem 2FA ativo, login() NAO e chamado. O sistema guarda
       apenas o id em uma chave temporaria de sessao e pede o codigo.
    3. Somente apos verify_token() aprovar e que a sessao autenticada nasce.

Consequencia: uma senha vazada, sozinha, nao produz sessao valida.
"""

import base64
import io
import logging
from datetime import datetime

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice
from .forms import EmailAuthenticationForm, OTPTokenForm
from .models import User
from django.contrib import messages
from .forms import RegistrationForm

def register_view(request):
    """Cadastro de novo usuario. A senha e gravada como hash Argon2id."""
    form = RegistrationForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        user = form.save()
        # TODO: registrar o consentimento em privacy.ConsentRecord (requisito 4.4)
        messages.success(
            request, 'Conta criada com sucesso. Faca login para continuar.'
        )
        return redirect('accounts:login')

    return render(request, 'accounts/register.html', {'form': form})




logger = logging.getLogger(__name__)

PENDING_USER_KEY = "pre_2fa_user_id"
PENDING_BACKEND_KEY = "pre_2fa_backend"
PENDING_TIME_KEY = "pre_2fa_started_at"


# ---------------------------------------------------------------------------
# Etapa 1: e-mail e senha
# ---------------------------------------------------------------------------
class TwoFactorLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()

        if device is not None:
            # Senha correta, mas a sessao ainda NAO e autenticada.
            self.request.session[PENDING_USER_KEY] = user.pk
            self.request.session[PENDING_BACKEND_KEY] = getattr(
                user, "backend", "django.contrib.auth.backends.ModelBackend"
            )
            self.request.session[PENDING_TIME_KEY] = timezone.now().isoformat()
            return redirect("accounts:otp_verify")

        auth_login(self.request, user)
        messages.info(
            self.request,
            "Sua conta ainda nao tem verificacao em duas etapas. "
            "Recomendamos ativar agora.",
        )
        return redirect("accounts:profile")


# ---------------------------------------------------------------------------
# Etapa 2: codigo de verificacao
# ---------------------------------------------------------------------------
def otp_verify(request):
    user_id = request.session.get(PENDING_USER_KEY)
    started_at = request.session.get(PENDING_TIME_KEY)

    if not user_id or not started_at:
        messages.error(request, "Sessao de verificacao invalida. Faca login novamente.")
        return redirect("accounts:login")

    # A janela entre a etapa 1 e a etapa 2 tambem expira.
    if timezone.now() - datetime.fromisoformat(started_at) > settings.TWO_FACTOR_PENDING_TIMEOUT:
        _clear_pending(request)
        messages.error(request, "Tempo esgotado para a verificacao. Faca login novamente.")
        return redirect("accounts:login")

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        _clear_pending(request)
        return redirect("accounts:login")

    form = OTPTokenForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device and device.verify_token(form.cleaned_data["token"]):
            backend = request.session.get(PENDING_BACKEND_KEY)
            _clear_pending(request)
            auth_login(request, user, backend=backend)
            otp_login(request, device)  # marca request.user.is_verified()
            return redirect("accounts:profile")

        form.add_error("token", "Codigo invalido ou expirado.")

    return render(
        request, "accounts/otp_verify.html", {"form": form, "email": user.email}
    )


def _clear_pending(request):
    for key in (PENDING_USER_KEY, PENDING_BACKEND_KEY, PENDING_TIME_KEY):
        request.session.pop(key, None)


# ---------------------------------------------------------------------------
# Ativar o segundo fator (requisito 1.5)
# ---------------------------------------------------------------------------
@login_required
def otp_setup(request):
    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(
            user=request.user, name="default", confirmed=False
        )

    form = OTPTokenForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        if device.verify_token(form.cleaned_data["token"]):
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            request.user.two_factor_enabled = True
            request.user.save(update_fields=["two_factor_enabled"])
            otp_login(request, device)
            messages.success(request, "Verificacao em duas etapas ativada.")
            return redirect("accounts:profile")
        form.add_error("token", "Codigo invalido. Confira o horario do seu celular.")

    return render(
        request,
        "accounts/otp_setup.html",
        {
            "form": form,
            "qr_data_uri": _build_qr_data_uri(device.config_url),
            "secret_url": device.config_url,
        },
    )


@login_required
def otp_disable(request):
    if request.method == "POST":
        TOTPDevice.objects.filter(user=request.user).delete()
        request.user.two_factor_enabled = False
        request.user.save(update_fields=["two_factor_enabled"])
        messages.warning(request, "Verificacao em duas etapas desativada.")
    return redirect("accounts:profile")


def _build_qr_data_uri(config_url):
    """Gera o QR code em PNG embutido na propria pagina, sem salvar arquivo."""
    img = qrcode.make(config_url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# ---------------------------------------------------------------------------
# Perfil e logout
# ---------------------------------------------------------------------------
@login_required
def profile(request):
    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    return render(
        request,
        "accounts/profile.html",
        {
            "has_2fa": device is not None,
            "session_expiry": request.session.get_expiry_date(),
            "hash_algorithm": request.user.hash_algorithm,
            "is_verified": request.user.is_verified(),
        },
    )


class SecureLogoutView(LogoutView):
    """
    Requisito 1.10.

    O logout() do Django chama session.flush(): a linha e removida da tabela
    django_session e uma chave nova e gerada. A sessao antiga deixa de existir
    no servidor - nao basta apagar o cookie do navegador.
    """

    next_page = reverse_lazy("home")